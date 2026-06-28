"""summary 新字段测试：top_movers、return_breakdown、data_freshness。"""
import pytest
from datetime import datetime, timedelta
from models import Holding, HoldingStatus


def _platform(client, name="TestP"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _holding(client, pid, **kw):
    base = {
        "platform_id": pid, "currency": "USD", "symbol": "AAPL",
        "name": "Apple", "quantity": 100, "cost_price": 10,
    }
    r = client.post("/api/holdings", json={**base, **kw})
    assert r.status_code == 200
    return r.json()["id"]


# ─── 结构测试（空数据）────────────────────────────────────────────────────────

def test_summary_new_fields_present_when_empty(client):
    s = client.get("/api/summary").json()
    assert "top_movers" in s
    assert isinstance(s["top_movers"], list)
    assert "return_breakdown" in s
    rb = s["return_breakdown"]
    for key in ("unrealized_pnl", "realized_pnl", "realized_income", "total_return"):
        assert key in rb
    assert "data_freshness" in s
    df = s["data_freshness"]
    assert "priced_count" in df
    assert "stale_count" in df
    assert "stale_items" in df
    assert isinstance(df["stale_items"], list)


# ─── top_movers 测试 ──────────────────────────────────────────────────────────

def test_top_movers_with_price_data(client, session):
    pid = _platform(client)
    hid = _holding(client, pid, currency="USD", symbol="AAPL", name="Apple", quantity=100, cost_price=10)
    # 直接设置价格
    h = session.get(Holding, hid)
    h.current_price = 12.0
    h.prev_close = 10.0
    session.add(h)
    session.commit()

    s = client.get("/api/summary?currency=USD").json()
    movers = s["top_movers"]
    assert len(movers) == 1
    m = movers[0]
    assert m["symbol"] == "AAPL"
    assert m["display_change"] == pytest.approx(200.0, abs=0.5)   # 100 * (12-10) = 200 USD
    assert m["change_pct"] == pytest.approx(20.0, abs=0.1)
    assert "holding_id" in m
    assert "platform" in m


def test_top_movers_no_prev_close_excluded(client, session):
    pid = _platform(client)
    hid = _holding(client, pid)
    h = session.get(Holding, hid)
    h.current_price = 12.0
    h.prev_close = None  # no prev_close → excluded
    session.add(h)
    session.commit()

    s = client.get("/api/summary").json()
    assert len(s["top_movers"]) == 0


def test_top_movers_sorted_by_abs_change(client, session):
    pid = _platform(client)
    # AAPL: 100 * (12-10) = 200 USD change
    hid1 = _holding(client, pid, symbol="AAPL", name="Apple", quantity=100)
    h1 = session.get(Holding, hid1)
    h1.current_price = 12.0
    h1.prev_close = 10.0
    session.add(h1)

    # BABA: 10 * (70-100) = -300 USD change (larger absolute)
    hid2 = _holding(client, pid, symbol="BABA", name="Alibaba", quantity=10, cost_price=100)
    h2 = session.get(Holding, hid2)
    h2.current_price = 70.0
    h2.prev_close = 100.0
    session.add(h2)
    session.commit()

    s = client.get("/api/summary?currency=USD").json()
    movers = s["top_movers"]
    assert len(movers) == 2
    # BABA has larger absolute change
    assert abs(movers[0]["display_change"]) >= abs(movers[1]["display_change"])
    assert movers[0]["symbol"] == "BABA"


def test_top_movers_max_5(client, session):
    pid = _platform(client)
    for i in range(7):
        sym = f"SYM{i}"
        hid = _holding(client, pid, symbol=sym, name=sym, quantity=100)
        h = session.get(Holding, hid)
        h.current_price = 12.0 + i
        h.prev_close = 10.0
        session.add(h)
        session.commit()  # commit each iteration to avoid StaticPool identity-map issues

    s = client.get("/api/summary").json()
    assert len(s["top_movers"]) == 5


def test_top_movers_closed_holding_excluded(client, session):
    pid = _platform(client)
    hid = _holding(client, pid)
    h = session.get(Holding, hid)
    h.current_price = 12.0
    h.prev_close = 10.0
    h.status = HoldingStatus.closed  # closed → should not appear
    session.add(h)
    session.commit()

    s = client.get("/api/summary").json()
    assert len(s["top_movers"]) == 0


# ─── return_breakdown 测试 ────────────────────────────────────────────────────

def test_return_breakdown_values(client):
    pid = _platform(client)
    # buy then sell to create realized_pnl
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "sell", "date": "2026-02-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 100, "price": 12})

    s = client.get("/api/summary?currency=USD").json()
    rb = s["return_breakdown"]
    # realized pnl = 100 * (12-10) = 200 USD
    assert rb["realized_pnl"] == pytest.approx(200.0, abs=0.5)
    assert rb["realized_income"] == 0.0
    assert "unrealized_pnl" in rb
    assert "total_return" in rb


def test_return_breakdown_with_dividend(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "dividend", "date": "2026-03-01",
        "symbol": "AAPL", "currency": "USD", "amount": 88})

    s = client.get("/api/summary?currency=USD").json()
    rb = s["return_breakdown"]
    assert rb["realized_income"] == pytest.approx(88.0, abs=0.5)


# ─── data_freshness 测试 ──────────────────────────────────────────────────────

def test_data_freshness_priced_count(client, session):
    pid = _platform(client)
    hid1 = _holding(client, pid, symbol="AAPL", name="A")
    hid2 = _holding(client, pid, symbol="BABA", name="B")
    # set price on first only
    h1 = session.get(Holding, hid1)
    h1.current_price = 10.0
    h1.price_updated_at = datetime.utcnow()
    session.add(h1)
    session.commit()

    s = client.get("/api/summary").json()
    df = s["data_freshness"]
    assert df["priced_count"] == 1
    assert df["stale_count"] >= 1  # BABA has no price


def test_data_freshness_stale_threshold(client, session):
    pid = _platform(client)
    hid = _holding(client, pid)
    h = session.get(Holding, hid)
    h.current_price = 10.0
    h.price_updated_at = datetime.utcnow() - timedelta(hours=25)  # stale
    session.add(h)
    session.commit()

    s = client.get("/api/summary").json()
    df = s["data_freshness"]
    assert df["stale_count"] >= 1
    assert len(df["stale_items"]) >= 1


def test_data_freshness_fresh_not_stale(client, session):
    pid = _platform(client)
    hid = _holding(client, pid)
    h = session.get(Holding, hid)
    h.current_price = 10.0
    h.price_updated_at = datetime.utcnow() - timedelta(hours=1)  # fresh
    session.add(h)
    session.commit()

    s = client.get("/api/summary").json()
    df = s["data_freshness"]
    assert df["stale_count"] == 0
    assert len(df["stale_items"]) == 0


def test_data_freshness_stale_items_max_5(client, session):
    pid = _platform(client)
    for i in range(7):
        hid = _holding(client, pid, symbol=f"SYM{i}", name=f"Stock{i}")
        h = session.get(Holding, hid)
        h.price_updated_at = None  # all stale
        session.add(h)
        session.commit()  # commit each iteration

    s = client.get("/api/summary").json()
    df = s["data_freshness"]
    assert df["stale_count"] == 7
    assert len(df["stale_items"]) == 5  # capped at 5


def test_data_freshness_closed_excluded(client, session):
    pid = _platform(client)
    hid = _holding(client, pid)
    h = session.get(Holding, hid)
    h.price_updated_at = None
    h.status = HoldingStatus.closed  # closed → should NOT count in data_freshness
    session.add(h)
    session.commit()

    s = client.get("/api/summary").json()
    df = s["data_freshness"]
    assert df["stale_count"] == 0
