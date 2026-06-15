def _platform(client):
    r = client.post("/api/platforms", json={"name": "Futu"})
    assert r.status_code == 200
    return r.json()["id"]


def test_buy_creates_derived_holding(client):
    pid = _platform(client)
    r = client.post("/api/transactions", json={
        "platform_id": pid, "date": "2026-01-01", "action": "buy",
        "symbol": "AAPL", "name": "Apple", "currency": "USD",
        "quantity": 100, "price": 10,
    })
    assert r.status_code == 200
    holdings = client.get("/api/holdings").json()
    derived = [h for h in holdings if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 100
    assert derived[0]["cost_price"] == 10


def test_second_buy_updates_average_cost(client):
    pid = _platform(client)
    base = {"platform_id": pid, "action": "buy", "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "date": "2026-01-02", "quantity": 100, "price": 20})
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert derived["quantity"] == 200
    assert derived["cost_price"] == 15


def test_delete_transaction_recomputes(client):
    pid = _platform(client)
    base = {"platform_id": pid, "action": "buy", "symbol": "AAPL", "currency": "USD"}
    r1 = client.post("/api/transactions", json={**base, "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "date": "2026-01-02", "quantity": 100, "price": 20})
    client.delete(f"/api/transactions/{r1.json()['id']}")
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert derived["quantity"] == 100
    assert derived["cost_price"] == 20


def test_closed_holding_hidden_by_default(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 100, "price": 12})
    assert all(h["status"] != "closed" for h in client.get("/api/holdings").json())
    with_closed = client.get("/api/holdings?include_closed=true").json()
    assert any(h["status"] == "closed" for h in with_closed)


def test_derived_holding_rejects_manual_quantity_edit(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 100, "price": 10})
    hid = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]["id"]
    r = client.put(f"/api/holdings/{hid}", json={"quantity": 999})
    assert r.status_code == 400
