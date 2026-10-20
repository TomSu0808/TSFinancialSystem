"""港股通等跨币种结算：股票按港币计价，现金按人民币收付。

覆盖验收口径：
- 人民币现金初始化后，用人民币买入港币计价股票：持仓为 HKD，现金从 CNY 扣减
- 手填实际结算金额优先，不再乘汇率
- 卖出所得按人民币入账
- 人民币不足按时间线拒绝
- 未填汇率时使用缓存的 USD/CNY 汇率折算并落库
- 编辑结算币种时同时重算新旧现金账户
"""
import pytest

from models import FxRate


def _platform(client, name="国信金证"):
    return client.post("/api/platforms", json={"name": name}).json()["id"]


def _txn(client, **kw):
    return client.post("/api/transactions", json=kw)


def _cash(client, pid, currency="CNY"):
    rows = client.get(f"/api/cash?platform_id={pid}").json()
    return next((r for r in rows if r["currency"] == currency), None)


def test_hk_stock_bought_with_cny_cash(client):
    """腾讯 200 股 @410.2 HKD，用人民币结算：持仓 HKD，现金扣 CNY。"""
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="CNY", amount=100000)

    r = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
             symbol="00700", name="腾讯控股", currency="HKD",
             cash_currency="CNY", fx_rate=0.91,
             quantity=200, price=410.2)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["currency"] == "HKD"
    assert body["cash_currency"] == "CNY"

    # 现金：只有 CNY 一个账户，且按人民币扣减
    rows = client.get(f"/api/cash?platform_id={pid}").json()
    assert [row["currency"] for row in rows] == ["CNY"]
    assert rows[0]["balance"] == pytest.approx(100000 - 200 * 410.2 * 0.91, abs=0.01)

    # 持仓仍按港币计价，数量/成本不受结算币种影响
    holding = next(h for h in client.get("/api/holdings").json() if h["symbol"] == "00700")
    assert holding["currency"] == "HKD"
    assert holding["quantity"] == 200
    assert holding["cost_price"] == pytest.approx(410.2)


def test_explicit_settlement_amount_is_used_as_is(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="CNY", amount=100000)
    r = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
             symbol="00700", name="腾讯控股", currency="HKD",
             cash_currency="CNY", fx_rate=0.91,
             quantity=200, price=410.2, amount=76000)
    assert r.status_code == 200, r.text
    assert _cash(client, pid)["balance"] == pytest.approx(24000)


def test_sell_credits_cny_cash(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="CNY", amount=100000)
    _txn(client, platform_id=pid, action="buy", date="2026-01-02",
         symbol="00700", name="腾讯控股", currency="HKD",
         cash_currency="CNY", quantity=200, price=410.2, amount=76000)
    sold = _txn(client, platform_id=pid, action="sell", date="2026-01-03",
                symbol="00700", name="腾讯控股", currency="HKD",
                cash_currency="CNY", quantity=100, price=450, amount=41000)
    assert sold.status_code == 200, sold.text
    assert _cash(client, pid)["balance"] == pytest.approx(24000 + 41000)


def test_cross_currency_buy_rejected_when_cny_insufficient(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="CNY", amount=1000)
    r = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
             symbol="00700", name="腾讯控股", currency="HKD",
             cash_currency="CNY", fx_rate=0.91, quantity=200, price=410.2)
    assert r.status_code == 400
    assert "现金余额不足" in r.json()["detail"]


def test_missing_rate_uses_cached_usdcny(client, session):
    session.add(FxRate(pair="USDCNY", rate=7.8, updated_at=None))
    session.commit()
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="CNY", amount=100000)
    r = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
             symbol="00700", name="腾讯控股", currency="HKD",
             cash_currency="CNY", quantity=200, price=410.2)
    assert r.status_code == 200, r.text
    # 1 USD = 7.8 CNY，联系汇率 7.8 HKD/USD → HKD/CNY = 1.0
    assert r.json()["fx_rate"] == pytest.approx(1.0)
    assert _cash(client, pid)["balance"] == pytest.approx(100000 - 200 * 410.2)


def test_editing_cash_currency_recalcs_both_accounts(client):
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="CNY", amount=100000)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="USD", amount=100000)
    bought = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
                  symbol="00700", name="腾讯控股", currency="HKD",
                  cash_currency="CNY", fx_rate=0.91, quantity=200, price=410.2).json()
    assert _cash(client, pid, "CNY")["balance"] == pytest.approx(100000 - 82040 * 0.91)

    r = client.put(f"/api/transactions/{bought['id']}",
                   json={"cash_currency": "USD", "fx_rate": 0.128})
    assert r.status_code == 200, r.text
    assert _cash(client, pid, "CNY")["balance"] == pytest.approx(100000)
    assert _cash(client, pid, "USD")["balance"] == pytest.approx(100000 - 200 * 410.2 * 0.128)


def test_same_currency_trade_unchanged(client):
    """未设置结算币种时行为与旧版完全一致。"""
    pid = _platform(client)
    _txn(client, platform_id=pid, action="cash_adjust", date="2026-01-01",
         currency="HKD", amount=100000)
    r = _txn(client, platform_id=pid, action="buy", date="2026-01-02",
             symbol="00700", name="腾讯控股", currency="HKD",
             quantity=200, price=410.2)
    assert r.status_code == 200, r.text
    assert r.json()["cash_currency"] is None
    assert _cash(client, pid, "HKD")["balance"] == pytest.approx(100000 - 200 * 410.2)
