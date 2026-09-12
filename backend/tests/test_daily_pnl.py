from datetime import datetime, timedelta

from sqlmodel import select

from daily_pnl_service import record_daily_pnl
from models import Currency, DailyPnl, FxRate, Holding, Platform, Transaction, User


def seed(session, user, now, **kwargs):
    platform = Platform(user_id=user.id, name="Broker")
    session.add(platform)
    session.commit()
    h = Holding(user_id=user.id, platform_id=platform.id, name="Test", symbol="TEST",
                market="US", currency=Currency.USD, quantity=10, cost_price=100,
                current_price=110, price_updated_at=now, **kwargs)
    session.add(h)
    session.add(FxRate(pair="USDCNY", rate=7, updated_at=now))
    session.commit()
    return h


def advance(session, h, now, price=115, rate=7):
    h.current_price = price
    h.price_updated_at = now
    fx = session.get(FxRate, "USDCNY")
    fx.rate = rate
    fx.updated_at = now
    session.add(h)
    session.add(fx)
    session.commit()


def test_daily_pnl_excludes_deposits_and_fx_and_is_idempotent(session, user):
    now = datetime(2026, 9, 10, 23, 55)
    h = seed(session, user, now)
    first = record_daily_pnl(session, user.id, now)
    assert first.pnl_cny is None and first.status == "baseline"
    tomorrow = now + timedelta(days=1)
    advance(session, h, tomorrow, rate=8)
    session.add(Holding(user_id=user.id, platform_id=h.platform_id, asset_type="cash",
                        name="Deposit", currency="USD", manual_value=10000))
    session.add(Transaction(user_id=user.id, date=tomorrow.date().isoformat(), action="deposit", amount=10000))
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.pnl_cny == 400  # 10 * (115 - 110) * 8, not portfolio value growth
    assert row.pnl_usd == 50
    record_daily_pnl(session, user.id, tomorrow)
    assert len(session.exec(select(DailyPnl)).all()) == 2


def test_closed_position_preserves_daily_realized_profit_and_income(session, user):
    now = datetime(2026, 9, 10, 23, 55)
    h = seed(session, user, now, source="derived")
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    advance(session, h, tomorrow)
    h.status = "closed"
    h.quantity = 0
    h.realized_pnl = 150
    h.realized_income = 10
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.pnl_usd == 60  # cumulative 160 - yesterday's unrealized 100


def test_missing_stale_and_gaps_are_not_zero_profit(session, user):
    now = datetime(2026, 9, 10, 23, 55)
    h = seed(session, user, now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.current_price = None
    session.add(h)
    session.commit()
    assert record_daily_pnl(session, user.id, tomorrow).status == "missing"
    advance(session, h, tomorrow)
    assert record_daily_pnl(session, user.id, tomorrow).pnl_usd == 50
    later = now + timedelta(days=3)
    advance(session, h, later)
    assert record_daily_pnl(session, user.id, later).pnl_usd is None
    assert record_daily_pnl(session, user.id, later + timedelta(hours=25)).status == "stale"


def test_manual_capital_change_rebaselines(session, user):
    now = datetime(2026, 9, 10, 23, 55)
    h = seed(session, user, now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    advance(session, h, tomorrow)
    h.quantity = 20
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "adjusted" and row.pnl_cny is None


def _fund(session, user, now, cost_value=12000.0, price=13.0):
    platform = Platform(user_id=user.id, name="Fund")
    session.add(platform)
    session.commit()
    h = Holding(user_id=user.id, platform_id=platform.id, name="某基金", symbol="110022",
                market="FUND", currency=Currency.CNY, asset_type="fund",
                quantity=1000.0, cost_value=cost_value,
                current_price=price, price_updated_at=now)
    session.add(h)
    session.commit()
    return h


def test_daily_pnl_for_fund_with_shares_and_total_cost(session, user):
    """场外基金：份额 + 投入总成本 + 抓到的净值，日盈亏 = 份额×(今日净值−昨日净值)。"""
    now = datetime(2026, 9, 10, 23, 55)
    h = _fund(session, user, now)
    first = record_daily_pnl(session, user.id, now)
    assert first.status == "baseline"
    tomorrow = now + timedelta(days=1)
    h.current_price = 13.2
    h.price_updated_at = tomorrow
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.pnl_cny == 200  # 1000 × (13.2 − 13.0)


def test_manual_total_cost_change_rebaselines(session, user):
    """投入总成本变化应触发重新建立基准，而不是把成本变化当作当日盈亏。"""
    now = datetime(2026, 9, 10, 23, 55)
    h = _fund(session, user, now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.current_price = 13.2
    h.price_updated_at = tomorrow
    h.cost_value = 12500.0
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "adjusted" and row.pnl_cny is None


def test_backup_roundtrip_preserves_cost_value(client, session, user):
    """备份/恢复应保留基金的投入总成本。"""
    _fund(session, user, datetime.utcnow(), cost_value=12000.0)
    backup = client.get('/api/backup').json()
    assert backup['holdings'][0]['cost_value'] == 12000.0
    assert client.post('/api/backup/import', json=backup).status_code == 200
    hs = session.exec(select(Holding).where(Holding.user_id == user.id)).all()
    assert any(h.cost_value == 12000.0 for h in hs)


def test_api_isolation_and_backup_roundtrip(client, session, user):
    now = datetime.utcnow()
    h = seed(session, user, now - timedelta(days=1))
    record_daily_pnl(session, user.id, now - timedelta(days=1))
    advance(session, h, now)
    record_daily_pnl(session, user.id, now)
    other = User(username="pnl_other", password_hash="x")
    session.add(other)
    session.commit()
    session.add(DailyPnl(user_id=other.id, day=now.date().isoformat(), pnl_cny=99999))
    session.commit()
    body = client.get('/api/snapshots/daily-pnl', params={"currency": "USD"}).json()
    assert body['items'][0]['pnl'] == 50
    assert len(body['items']) == 2
    backup = client.get('/api/backup').json()
    assert len(backup['daily_pnl']) == 2
    assert client.post('/api/backup/import', json=backup).status_code == 200
    assert client.get('/api/snapshots/daily-pnl', params={"currency": "USD"}).json()['items'][0]['pnl'] == 50
    assert session.get(DailyPnl, session.exec(select(DailyPnl.id).where(DailyPnl.user_id == other.id)).first()) is not None


def test_summary_and_ai_agree_with_missing_prices(client, session, user):
    now = datetime.utcnow()
    h = seed(session, user, now)
    h.current_price = None
    session.add(h)
    session.commit()
    from portfolio_context import build_account_context
    summary = client.get('/api/summary').json()
    context = build_account_context(session, user, Currency.CNY)
    assert summary['total_profit'] == 0
    assert summary['total_cost'] == 0
    assert "未实现盈亏：0.00 CNY" in context
