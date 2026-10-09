"""现金自动联动：按 (user, platform, currency) 重放现金账本。

覆盖验收口径：
- init 1000 → sell 成交额 10000 fee 5 → 10995 → buy 成交额 6000 fee 5 → 4990
- 部分/全部卖出、分红、修改/撤销、跨账户/币种编辑、回填、CSV/券商导入、备份往返
- 未初始化不凭空造现金；初始化后买入/出金不得负余额（时间线校验，非最终余额）
- 现金变动不污染日盈亏/投资收益
"""
from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from models import Currency, FxRate, Holding, Platform, Transaction


# ── helpers ──────────────────────────────────────────────────────────────────

def _platform(client, name="券商"):
    return client.post("/api/platforms", json={"name": name}).json()["id"]


def _txn(client, **kw):
    return client.post("/api/transactions", json=kw)


def _cash(client, pid, currency="USD"):
    hs = client.get("/api/holdings?include_closed=true").json()
    return next((h for h in hs if h.get("asset_type") == "cash"
                 and h.get("platform_id") == pid
                 and h.get("currency") == currency), None)


def _cash_value(client, pid, currency="USD"):
    c = _cash(client, pid, currency)
    return c["manual_value"] if c else None


# ── 验收口径：init → sell → buy ───────────────────────────────────────────────

def test_cash_init_sell_buy_acceptance(client):
    pid = _platform(client)
    assert _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
                currency="USD", amount=1000).status_code == 200
    # adjust 建立持仓（无现金流），再卖出
    assert _txn(client, platform_id=pid, action="adjust", date="2026-01-02",
                symbol="AAPL", name="Apple", currency="USD", quantity=100, price=100).status_code == 200
    assert _txn(client, platform_id=pid, action="sell", date="2026-01-03",
                symbol="AAPL", name="Apple", currency="USD", quantity=100, price=100, fee=5).status_code == 200
    assert _cash_value(client, pid) == 10995  # 1000 + (10000 - 5)
    assert _txn(client, platform_id=pid, action="buy", date="2026-01-04",
                symbol="AAPL", name="Apple", currency="USD", quantity=100, price=60, fee=5).status_code == 200
    assert _cash_value(client, pid) == 4990  # 10995 - (6000 + 5)


def test_partial_and_full_sell_cash_flow(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=10000)
    _txn(client, platform_id=pid, action="buy", date="2026-01-02",
         symbol="AAPL", name="Apple", currency="USD", quantity=100, price=50, fee=10)
    assert _cash_value(client, pid) == 4990  # 10000 - (5000 + 10)
    _txn(client, platform_id=pid, action="sell", date="2026-01-03",
         symbol="AAPL", name="Apple", currency="USD", quantity=40, price=60, fee=5)
    assert _cash_value(client, pid) == 7385  # 4990 + (2400 - 5)
    _txn(client, platform_id=pid, action="sell", date="2026-01-04",
         symbol="AAPL", name="Apple", currency="USD", quantity=60, price=60, fee=5)
    assert _cash_value(client, pid) == 10980  # 7385 + (3600 - 5)


def test_sell_without_cash_initialization_preserves_assets_until_withdrawal(client, session):
    pid = _platform(client)
    holding = client.post('/api/holdings', json={
        'platform_id': pid, 'symbol': 'AAPL', 'name': 'Apple',
        'currency': 'USD', 'market': 'US', 'quantity': 100,
        'cost_price': 50, 'current_price': 60,
    })
    assert holding.status_code == 200
    h = session.get(Holding, holding.json()['id'])
    h.current_price = 60
    session.add(h)
    session.commit()
    before = client.get('/api/summary?currency=USD').json()['total']
    sold = _txn(client, platform_id=pid, action='sell', date='2026-01-02',
                symbol='AAPL', currency='USD', quantity=40, price=60, fee=5)
    assert sold.status_code == 200, sold.text
    assert _cash_value(client, pid) == 2395
    assert client.get('/api/summary?currency=USD').json()['total'] == before - 5
    ledger = client.get(f'/api/cash/ledger?platform_id={pid}&currency=USD').json()
    assert ledger['balance'] == ledger['entries'][-1]['balance'] == 2395
    assert ledger['entries'][-1]['flow'] == 2395
    withdrawn = _txn(client, platform_id=pid, action='withdraw', date='2026-01-03',
                     currency='USD', amount=1000)
    assert withdrawn.status_code == 200, withdrawn.text
    assert _cash_value(client, pid) == 1395
    assert client.get('/api/summary?currency=USD').json()['total'] == before - 1005


def test_uninitialized_sale_cash_can_be_reinvested_edited_and_reversed(client):
    pid = _platform(client)
    base = dict(platform_id=pid, symbol='AAPL', currency='USD')
    assert _txn(client, **base, action='buy', date='2026-01-01', quantity=10, price=100).status_code == 200
    sold = _txn(client, **base, action='sell', date='2026-01-02', quantity=10, price=120).json()
    assert _cash_value(client, pid) == 1200
    bought = _txn(client, **base, action='buy', date='2026-01-03', quantity=5, price=100)
    assert bought.status_code == 200, bought.text
    assert _cash_value(client, pid) == 700
    assert client.put(f"/api/transactions/{sold['id']}", json={'price': 110}).status_code == 200
    assert _cash_value(client, pid) == 600
    assert client.delete(f"/api/transactions/{bought.json()['id']}").status_code == 200
    assert _cash_value(client, pid) == 1100
    assert client.delete(f"/api/transactions/{sold['id']}").status_code == 200
    assert _cash_value(client, pid) is None


def test_changing_cash_action_to_other_recalculates_balance(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action='cash_adjust', date='2026-01-01', currency='USD', amount=1000)
    deposit = _txn(client, platform_id=pid, action='deposit', date='2026-01-02', currency='USD', amount=500).json()
    assert client.put(f"/api/transactions/{deposit['id']}", json={'action': 'other'}).status_code == 200
    assert _cash_value(client, pid) == 1000


def test_startup_rebuilds_historical_sale_cash_idempotently(client, session, monkeypatch):
    import database
    pid = _platform(client)
    user_id = session.exec(select(Platform)).first().user_id
    session.add(Transaction(user_id=user_id, platform_id=pid, action='sell',
                            date='2026-01-01', currency='USD', quantity=10, price=100, fee=5))
    session.commit()
    monkeypatch.setattr(database, 'engine', session.bind)
    database.init_db()
    database.init_db()
    assert _cash_value(client, pid) == 995
    cash = [h for h in client.get('/api/holdings').json() if h['asset_type'] == 'cash']
    assert len(cash) == 1


def test_old_backup_without_cash_holding_rebuilds_sale_proceeds(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, symbol='AAPL', currency='USD',
         action='adjust', date='2026-01-01', quantity=10, price=100)
    _txn(client, platform_id=pid, symbol='AAPL', currency='USD',
         action='sell', date='2026-01-02', quantity=10, price=120)
    backup = client.get('/api/backup').json()
    backup['holdings'] = [h for h in backup['holdings'] if h['asset_type'] != 'cash']
    assert client.post('/api/backup/import', json=backup).status_code == 200
    restored = client.get('/api/cash').json()[0]
    assert _cash_value(client, restored['platform_id']) == 1200


@pytest.mark.parametrize('existing_anchor', [False, True])
def test_legacy_deficits_allow_calibration_and_future_trades(client, session, user, existing_anchor):
    from cash_service import rebuild_sale_cash
    pid = _platform(client)
    base = dict(user_id=user.id, platform_id=pid, symbol='AAPL', currency='USD', quantity=1)
    session.add(Transaction(**base, action='sell', date='2026-01-01', price=100))
    session.add(Transaction(**base, action='buy', date='2026-01-02', price=200))
    if existing_anchor:
        session.add(Transaction(user_id=user.id, platform_id=pid, currency='USD',
                                action='cash_adjust', date='2026-02-01', amount=1000))
    session.commit()
    rebuild_sale_cash(session, user.id)
    session.commit()
    if not existing_anchor:
        calibrated = _txn(client, platform_id=pid, currency='USD', action='cash_adjust',
                          date='2026-02-01', amount=1000)
        assert calibrated.status_code == 200, calibrated.text
    bought = _txn(client, platform_id=pid, symbol='MSFT', currency='USD', action='buy',
                  date='2026-03-01', quantity=1, price=10)
    assert bought.status_code == 200, bought.text
    assert _cash_value(client, pid) == 990
    # A new deficit in historical or current cash must still be rejected.
    for date, amount in [('2026-01-03', 1), ('2026-03-02', 2000)]:
        assert _txn(client, platform_id=pid, currency='USD', action='withdraw',
                    date=date, amount=amount).status_code == 400


def test_legacy_deficit_edits_and_deletes_cannot_worsen_history(client, session, user):
    pid = _platform(client)
    base = dict(user_id=user.id, platform_id=pid, currency='USD')
    deposit = Transaction(**base, action='deposit', date='2026-01-01', amount=50)
    other_deposit = Transaction(**base, action='deposit', date='2026-01-01', amount=50)
    bought = Transaction(**base, symbol='AAPL', action='buy', date='2026-01-02', quantity=1, price=200)
    anchor = Transaction(**base, action='cash_adjust', date='2026-02-01', amount=1000)
    session.add_all([deposit, other_deposit, bought, anchor])
    session.commit()
    improved = client.put(f'/api/transactions/{bought.id}', json={'price': 190})
    assert improved.status_code == 200, improved.text
    assert client.put(f'/api/transactions/{bought.id}', json={'price': 210}).status_code == 400
    assert client.put(f'/api/transactions/{bought.id}', json={'date': '2026-01-03'}).status_code == 400
    assert client.delete(f'/api/transactions/{deposit.id}').status_code == 400
    # Removing an unrelated later positive cash record must not be blocked by old deficits.
    added = _txn(client, platform_id=pid, currency='USD', action='deposit', date='2026-03-01', amount=10)
    assert added.status_code == 200
    assert client.delete(f"/api/transactions/{added.json()['id']}").status_code == 200
    assert _cash_value(client, pid) == 1000


# ── 未初始化 / 锚定规则 ──────────────────────────────────────────────────────

def test_buy_before_init_is_not_fabricated_as_cash(client):
    pid = _platform(client)
    assert _txn(client, platform_id=pid, action="buy", date="2026-01-01",
                symbol="AAPL", name="Apple", currency="USD", quantity=10, price=100).status_code == 200
    assert _cash(client, pid) is None  # 不凭空造现金
    # 之后初始化：历史买入被锚定覆盖，不计现金
    assert _txn(client, platform_id=pid, action="cash_adjust", date="2026-02-01",
                currency="USD", amount=5000).status_code == 200
    assert _cash_value(client, pid) == 5000


def test_cash_list_reports_uninitialized(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="buy", date="2026-01-01",
         symbol="AAPL", name="Apple", currency="USD", quantity=10, price=100)
    lst = client.get(f"/api/cash?platform_id={pid}").json()
    assert len(lst) == 1
    assert lst[0]["initialized"] is False
    assert lst[0]["balance"] is None


# ── 负余额时间线校验 ────────────────────────────────────────────────────────

def test_buy_exceeding_cash_after_init_rejected(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    r = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
             symbol="AAPL", name="Apple", currency="USD", quantity=10, price=200, fee=5)
    assert r.status_code == 400
    assert "现金余额不足" in r.json()["detail"]


def test_withdraw_exceeding_cash_rejected(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    r = _txn(client, platform_id=pid, action="withdraw", date="2026-01-02", currency="USD", amount=2000)
    assert r.status_code == 400
    assert "超过当前现金余额" in r.json()["detail"]


def test_backfill_withdraw_before_anchor_rejected(client):
    """回填在锚点之前的出金会破坏时间线，即使最终余额为正也应拒绝。"""
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-10", currency="USD", amount=1000)
    r = _txn(client, platform_id=pid, action="withdraw", date="2026-01-05", currency="USD", amount=2000)
    assert r.status_code == 400
    assert "超过当前现金余额" in r.json()["detail"]


# ── 分红 / 校准 ─────────────────────────────────────────────────────────────

def test_dividend_adds_cash(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=pid, action="dividend", date="2026-01-02", currency="USD", amount=88)
    assert _cash_value(client, pid) == 1088


def test_cash_adjust_recalibrates_absolute(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=pid, action="deposit", date="2026-01-02", currency="USD", amount=100)
    assert _cash_value(client, pid) == 1100
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-03", currency="USD", amount=800)
    assert _cash_value(client, pid) == 800


def test_handfilled_amount_respected_no_double_fee(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=pid, action="adjust", date="2026-01-02",
         symbol="AAPL", name="Apple", currency="USD", quantity=100, price=100)
    # 手填净额 9990（不是 100*100-5=9995），直接采用，不再叠加手续费
    _txn(client, platform_id=pid, action="sell", date="2026-01-03",
         symbol="AAPL", name="Apple", currency="USD", quantity=100, price=100, fee=5, amount=9990)
    assert _cash_value(client, pid) == 10990


# ── 账户/币种隔离与跨账户编辑 ───────────────────────────────────────────────

def test_cash_isolated_by_account_and_currency(client):
    p1 = _platform(client, "A")
    p2 = _platform(client, "B")
    _txn(client, platform_id=p1, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=p1, action="cash_adjust", date="2026-01-01", currency="CNY", amount=500)
    _txn(client, platform_id=p2, action="cash_adjust", date="2026-01-01", currency="USD", amount=300)
    assert _cash_value(client, p1, "USD") == 1000
    assert _cash_value(client, p1, "CNY") == 500
    assert _cash_value(client, p2, "USD") == 300


def test_edit_move_txn_recalcs_both_accounts(client):
    p1 = _platform(client, "A")
    p2 = _platform(client, "B")
    d = _txn(client, platform_id=p1, action="deposit", date="2026-01-01", currency="USD", amount=500).json()
    assert _cash_value(client, p1) == 500
    assert client.put(f"/api/transactions/{d['id']}", json={"platform_id": p2}).status_code == 200
    assert _cash_value(client, p1) is None  # 旧账户不再有显式现金
    assert _cash_value(client, p2) == 500


def test_edit_change_currency_recalcs_both(client):
    pid = _platform(client)
    d = _txn(client, platform_id=pid, action="deposit", date="2026-01-01", currency="USD", amount=500).json()
    assert _cash_value(client, pid, "USD") == 500
    assert client.put(f"/api/transactions/{d['id']}", json={"currency": "CNY"}).status_code == 200
    assert _cash_value(client, pid, "USD") is None
    assert _cash_value(client, pid, "CNY") == 500


def test_delete_recalcs_cash(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    d = _txn(client, platform_id=pid, action="deposit", date="2026-01-02", currency="USD", amount=500).json()
    assert _cash_value(client, pid) == 1500
    assert client.delete(f"/api/transactions/{d['id']}").status_code == 200
    assert _cash_value(client, pid) == 1000


# ── 导入与备份 ──────────────────────────────────────────────────────────────

def test_csv_import_recalcs_cash(client):
    pid = _platform(client, "CSVBroker")
    content = ('date,action,name,symbol,platform,currency,quantity,price,amount\n'
               '2026-01-01,cash_adjust,,,CSVBroker,USD,,,1000\n'
               '2026-01-02,deposit,,,CSVBroker,USD,,,500')
    r = client.post('/api/transactions/import/commit',
                    files={'file': ('cash.csv', content.encode(), 'text/csv')})
    assert r.status_code == 200, r.text
    assert _cash_value(client, pid, "USD") == 1500


def test_broker_import_recalcs_cash(client):
    pid = _platform(client, "BrokerX")
    content = ('date,action,name,symbol,currency,quantity,price,amount\n'
               '2026-01-01,cash_adjust,,,USD,,,1000\n'
               '2026-01-02,deposit,,,USD,,,500')
    preview = client.post('/api/imports/preview',
                          data={'broker_type': 'generic', 'platform_id': pid},
                          files={'file': ('cash.csv', content.encode(), 'text/csv')})
    assert preview.status_code == 200, preview.text
    assert preview.json()['summary']['error'] == 0, preview.json()
    committed = client.post(f"/api/imports/{preview.json()['import_session_id']}/commit")
    assert committed.json()['created_count'] == 2, committed.json()
    assert _cash_value(client, pid, "USD") == 1500


def test_backup_roundtrip_preserves_cash(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=pid, action="deposit", date="2026-01-02", currency="USD", amount=500)
    backup = client.get("/api/backup").json()
    assert client.post("/api/backup/import", json=backup).status_code == 200
    assert _cash_value(client, pid) == 1500


def test_cash_ledger_endpoint(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=pid, action="deposit", date="2026-01-02", currency="USD", amount=500)
    body = client.get(f"/api/cash/ledger?platform_id={pid}&currency=USD").json()
    assert body["initialized"] is True
    assert body["balance"] == 1500
    assert [e["flow"] for e in body["entries"]] == [1000, 500]
    assert body["entries"][-1]["balance"] == 1500


# ── 现金不污染投资收益 / 日盈亏 ─────────────────────────────────────────────

def test_cash_in_total_but_not_investment_income(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01", currency="USD", amount=1000)
    _txn(client, platform_id=pid, action="deposit", date="2026-01-02", currency="USD", amount=500)
    s = client.get("/api/summary?currency=USD").json()
    assert s["realized_pnl"] == 0
    assert s["realized_income"] == 0
    assert s["total_return"] == 0
    assert s["total"] == 1500  # 现金计入总资产
    types = {t["asset_type"]: t["display_total"] for t in s["by_type"]}
    assert types["cash"] == 1500


def test_cash_adjust_does_not_pollute_daily_pnl(session, user):
    from daily_pnl_service import record_daily_pnl
    now = datetime(2026, 9, 10, 23, 55)
    platform = Platform(user_id=user.id, name="Broker")
    session.add(platform)
    session.commit()
    h = Holding(user_id=user.id, platform_id=platform.id, name="Test", symbol="TEST",
                market="US", currency=Currency.USD, quantity=10, cost_price=100,
                current_price=110, price_updated_at=now)
    session.add(h)
    session.add(FxRate(pair="USDCNY", rate=7, updated_at=now))
    session.commit()
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.current_price = 115
    h.price_updated_at = tomorrow
    session.add(h)
    # 现金校准 10000：计入总资产但不计入日盈亏
    session.add(Holding(user_id=user.id, platform_id=platform.id, asset_type="cash",
                        name="现金", currency=Currency.USD, manual_value=10000))
    session.add(Transaction(user_id=user.id, platform_id=platform.id, currency=Currency.USD,
                            date=tomorrow.date().isoformat(), action="cash_adjust", amount=10000))
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.pnl_usd == 50  # 仅股票 10×(115-110)，现金校准不参与


def test_uninitialized_cash_rejected_when_no_explicit_record(client):
    pid = _platform(client)
    # 只有买入，未初始化现金：卖出不得凭空产生负现金
    _txn(client, platform_id=pid, action="buy", date="2026-01-01",
         symbol="AAPL", name="Apple", currency="USD", quantity=100, price=50)
    r = _txn(client, platform_id=pid, action="withdraw", date="2026-01-02", currency="USD", amount=100)
    assert r.status_code == 400
