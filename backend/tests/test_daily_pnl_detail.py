"""逐仓位每日盈亏明细：多平台/多币种、正负收益、明细合计、历史无明细、
价格/成本缺失、同日刷新幂等、历史汇率不变、用户隔离、备份恢复。"""
import json
from datetime import datetime, timedelta

from sqlmodel import select

from daily_pnl_service import record_daily_pnl
from models import Currency, DailyPnl, FxRate, Holding, Platform, User


def _platform(session, user, name):
    p = Platform(user_id=user.id, name=name)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _fx(session, now, rate=7.0):
    fx = session.get(FxRate, "USDCNY")
    if fx is None:
        fx = FxRate(pair="USDCNY", rate=rate, updated_at=now)
        session.add(fx)
    else:
        fx.rate = rate
        fx.updated_at = now
    session.commit()
    return fx


def _holding(session, user, platform, *, symbol, name=None, currency="USD", market="US",
             quantity=None, cost_price=None, cost_value=None, current_price=None,
             asset_type="stock", source="manual", status="open", price_updated_at=None,
             realized_pnl=0.0, realized_income=0.0):
    h = Holding(
        user_id=user.id, platform_id=platform.id, name=name or symbol, symbol=symbol,
        market=market, currency=currency, asset_type=asset_type,
        quantity=quantity, cost_price=cost_price, cost_value=cost_value,
        current_price=current_price, price_updated_at=price_updated_at,
        source=source, status=status, realized_pnl=realized_pnl, realized_income=realized_income,
    )
    session.add(h)
    session.commit()
    session.refresh(h)
    return h


def test_detail_per_position_multi_currency_matches_total(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "BrokerA")
    pb = _platform(session, user, "BrokerB")
    h_usd = _holding(session, user, pa, symbol="TEST", name="Test US", currency="USD",
                     quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    h_cny = _holding(session, user, pb, symbol="000001", name="平安银行", currency="CNY",
                     market="A", quantity=100, cost_price=10, current_price=11, price_updated_at=now)
    assert record_daily_pnl(session, user.id, now).status == "baseline"

    tomorrow = now + timedelta(days=1)
    h_usd.current_price = 115
    h_usd.price_updated_at = tomorrow
    h_cny.current_price = 12
    h_cny.price_updated_at = tomorrow
    session.add(h_usd)
    session.add(h_cny)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "recorded"
    assert row.pnl_cny == 450                     # 50*7 + 100
    assert row.pnl_usd == round(450 / 7, 2)       # 64.29

    day = tomorrow.date().isoformat()
    body = client.get(f"/api/snapshots/daily-pnl/{day}", params={"currency": "USD"}).json()
    assert body["has_details"] is True
    assert body["total"] == row.pnl_usd
    by_platform = {p["platform"]: p for p in body["positions"]}
    assert set(by_platform) == {"BrokerA", "BrokerB"}
    assert by_platform["BrokerA"]["pnl"] == 50
    assert by_platform["BrokerA"]["currency"] == "USD"
    assert by_platform["BrokerB"]["pnl"] == round(100 / 7, 2)
    assert by_platform["BrokerB"]["currency"] == "CNY"
    # 明细合计与当日总额一致（允许浮点/舍入差 < 0.02）
    assert abs(sum(p["pnl"] for p in body["positions"]) - body["total"]) < 0.02

    body_cny = client.get(f"/api/snapshots/daily-pnl/{day}", params={"currency": "CNY"}).json()
    assert body_cny["total"] == 450
    by_platform_cny = {p["platform"]: p for p in body_cny["positions"]}
    assert by_platform_cny["BrokerA"]["pnl"] == 350
    assert by_platform_cny["BrokerB"]["pnl"] == 100


def test_detail_same_symbol_different_platforms_separated(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "BrokerA")
    pb = _platform(session, user, "BrokerB")
    h1 = _holding(session, user, pa, symbol="TEST", name="Test", currency="USD",
                  quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    h2 = _holding(session, user, pb, symbol="TEST", name="Test", currency="USD",
                  quantity=20, cost_price=100, current_price=105, price_updated_at=now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h1.current_price = 115
    h1.price_updated_at = tomorrow
    h2.current_price = 103
    h2.price_updated_at = tomorrow
    session.add(h1)
    session.add(h2)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "recorded"

    body = client.get(f"/api/snapshots/daily-pnl/{tomorrow.date().isoformat()}", params={"currency": "USD"}).json()
    pnl = {p["platform"]: p["pnl"] for p in body["positions"]}
    assert set(pnl) == {"BrokerA", "BrokerB"}
    assert pnl["BrokerA"] == 50        # 10 × (115-110)
    assert pnl["BrokerB"] == -40       # 20 × (103-105)
    assert body["total"] == 10         # 50 - 40
    # 默认按绝对值降序
    assert [abs(p["pnl"]) for p in body["positions"]] == [50, 40]


def test_detail_closed_position_and_dividend_captured(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "Broker")
    h = _holding(session, user, pa, symbol="TEST", name="Test", currency="USD",
                 quantity=10, cost_price=100, current_price=110, price_updated_at=now,
                 source="derived")
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.status = "closed"
    h.quantity = 0
    h.realized_pnl = 150
    h.realized_income = 10
    h.current_price = None
    h.price_updated_at = tomorrow
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "recorded"
    assert row.pnl_usd == 60            # 累计 160 − 昨日未实现 100
    body = client.get(f"/api/snapshots/daily-pnl/{tomorrow.date().isoformat()}", params={"currency": "USD"}).json()
    assert len(body["positions"]) == 1
    assert body["positions"][0]["pnl"] == 60


def test_detail_excluded_position_reason(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "Broker")
    good = _holding(session, user, pa, symbol="GOOD", name="Good", currency="USD",
                    quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    missing = _holding(session, user, pa, symbol="MISS", name="Miss", currency="USD",
                       quantity=5, cost_price=None, current_price=None, price_updated_at=now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    good.current_price = 115
    good.price_updated_at = tomorrow
    session.add(good)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "recorded"
    assert row.pnl_usd == 50

    body = client.get(f"/api/snapshots/daily-pnl/{tomorrow.date().isoformat()}", params={"currency": "USD"}).json()
    assert body["excluded_count"] == 1
    p_missing = next(p for p in body["positions"] if p["symbol"] == "MISS")
    assert p_missing["excluded"] is True
    assert p_missing["status"] == "excluded"
    assert p_missing["pnl"] == 0        # 缺价/成本：未实现不计入，已实现+分红差为 0
    assert "缺价格或成本" in (p_missing["reason"] or "")


def test_detail_old_history_has_no_detail(client, session, user):
    now = datetime.utcnow()
    session.add(DailyPnl(user_id=user.id, day=now.date().isoformat(),
                         returns_json='{"USD": 100}', basis_json='{}',
                         pnl_cny=700, pnl_usd=100, status="recorded", note="旧记录"))
    session.commit()
    body = client.get(f"/api/snapshots/daily-pnl/{now.date().isoformat()}", params={"currency": "CNY"}).json()
    assert body["has_details"] is False
    assert body["positions"] == []
    assert body["total"] == 700
    assert "未记录持仓明细" in body["no_detail_message"]


def test_detail_transition_day_no_per_position_baseline(client, session, user):
    """旧历史（只有汇总）之后的第一天：总额可算，但逐仓位无前一日基准。"""
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "Broker")
    h = _holding(session, user, pa, symbol="TEST", name="Test", currency="USD",
                 quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    first = record_daily_pnl(session, user.id, now)
    assert first.status == "baseline"
    # 模拟旧历史：把昨日逐仓位明细清空（只保留 per-currency 汇总与 basis）
    first.details_json = "[]"
    session.add(first)
    session.commit()

    tomorrow = now + timedelta(days=1)
    h.current_price = 115
    h.price_updated_at = tomorrow
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.status == "recorded"     # 总额仍可算（通过 per-currency 汇总）
    assert row.pnl_usd == 50
    body = client.get(f"/api/snapshots/daily-pnl/{tomorrow.date().isoformat()}", params={"currency": "USD"}).json()
    assert body["has_details"] is True
    p = body["positions"][0]
    assert p["status"] == "no_baseline"
    assert p["pnl"] is None
    assert "前一日未记录持仓明细" in p["reason"]


def test_detail_idempotent_same_day(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "Broker")
    h = _holding(session, user, pa, symbol="TEST", name="Test", currency="USD",
                 quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.current_price = 115
    h.price_updated_at = tomorrow
    session.add(h)
    session.commit()
    record_daily_pnl(session, user.id, tomorrow)
    record_daily_pnl(session, user.id, tomorrow)  # 同日重复刷新幂等
    assert len(session.exec(select(DailyPnl)).all()) == 2
    body = client.get(f"/api/snapshots/daily-pnl/{tomorrow.date().isoformat()}", params={"currency": "USD"}).json()
    assert len(body["positions"]) == 1
    assert body["positions"][0]["pnl"] == 50


def test_detail_historical_rate_preserved_on_currency_switch(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=8.0)
    pa = _platform(session, user, "Broker")
    h = _holding(session, user, pa, symbol="TEST", name="Test", currency="USD",
                 quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.current_price = 115
    h.price_updated_at = tomorrow
    session.add(h)
    session.commit()
    row = record_daily_pnl(session, user.id, tomorrow)
    assert row.pnl_usd == 50
    assert row.pnl_cny == 400            # 50 × 8

    _fx(session, now + timedelta(days=2), rate=7.0)  # 之后汇率变动
    day = tomorrow.date().isoformat()
    body = client.get(f"/api/snapshots/daily-pnl/{day}", params={"currency": "USD"}).json()
    assert body["total"] == 50
    assert body["positions"][0]["pnl"] == 50
    assert body["positions"][0]["fx_rate"] == 8.0
    body_cny = client.get(f"/api/snapshots/daily-pnl/{day}", params={"currency": "CNY"}).json()
    assert body_cny["total"] == 400


def test_detail_user_isolation(client, session, user):
    now = datetime.utcnow()
    other = User(username="detail_other", password_hash="x")
    session.add(other)
    session.commit()
    session.add(DailyPnl(user_id=other.id, day=now.date().isoformat(),
                         details_json='[{"platform":"X","symbol":"Y","pnl_cny":1,"pnl_usd":0.1}]',
                         pnl_cny=99999, pnl_usd=9999, status="recorded"))
    session.commit()
    assert client.get(f"/api/snapshots/daily-pnl/{now.date().isoformat()}").status_code == 404


def test_detail_invalid_day_returns_400(client):
    assert client.get("/api/snapshots/daily-pnl/not-a-date").status_code == 400


def test_backup_roundtrip_preserves_detail(client, session, user):
    now = datetime(2026, 9, 10, 23, 55)
    _fx(session, now, rate=7.0)
    pa = _platform(session, user, "Broker")
    h = _holding(session, user, pa, symbol="TEST", name="Test", currency="USD",
                 quantity=10, cost_price=100, current_price=110, price_updated_at=now)
    record_daily_pnl(session, user.id, now)
    tomorrow = now + timedelta(days=1)
    h.current_price = 115
    h.price_updated_at = tomorrow
    session.add(h)
    session.commit()
    record_daily_pnl(session, user.id, tomorrow)

    backup = client.get('/api/backup').json()
    recorded = next(d for d in backup['daily_pnl'] if d['day'] == tomorrow.date().isoformat())
    assert 'details_json' in recorded
    assert json.loads(recorded['details_json'])[0]['platform'] == 'Broker'

    assert client.post('/api/backup/import', json=backup).status_code == 200
    body = client.get(f"/api/snapshots/daily-pnl/{tomorrow.date().isoformat()}", params={"currency": "USD"}).json()
    assert body['has_details'] is True
    assert body['positions'][0]['platform'] == 'Broker'
