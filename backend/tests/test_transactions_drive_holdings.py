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


def test_summary_exposes_realized_split(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 100, "price": 12})
    s = client.get("/api/summary?currency=USD").json()
    assert "realized_pnl" in s and "realized_income" in s and "total_return" in s
    assert round(s["realized_pnl"], 2) == 200.0


def test_backup_roundtrip_preserves_derived(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD",
        "quantity": 100, "price": 10})
    dump = client.get("/api/backup").json()
    assert dump["holdings"][0]["source"] == "derived"
    assert dump["transactions"][0]["holding_ref"] is not None

    r = client.post("/api/backup/import", json=dump)
    assert r.status_code == 200
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 100
    assert derived[0]["cost_price"] == 10


def test_import_legacy_backup_without_new_fields(client):
    legacy = {
        "platforms": [{"ref": 1, "name": "OldP", "note": None}],
        "holdings": [{
            "platform_ref": 1, "currency": "CNY", "asset_type": "cash",
            "market": "NONE", "symbol": "", "name": "现金",
            "quantity": None, "manual_value": 1000, "cost_price": None,
        }],
        "transactions": [],
        "notes": [],
    }
    r = client.post("/api/backup/import", json=legacy)
    assert r.status_code == 200
    holds = client.get("/api/holdings").json()
    assert len(holds) == 1
    assert holds[0]["source"] == "manual"
    assert holds[0]["manual_value"] == 1000


def test_dividend_updates_realized_income(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    client.post("/api/transactions", json={**base, "action": "dividend", "date": "2026-03-01", "amount": 88})
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert derived["realized_income"] == 88.0


def test_editing_action_to_deposit_recomputes_holding(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    r = client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    # change the buy into a deposit (no longer drives the position)
    client.put(f"/api/transactions/{r.json()['id']}", json={"action": "deposit"})
    derived = [h for h in client.get("/api/holdings?include_closed=true").json() if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 0.0          # buy no longer counts
    assert derived[0]["status"] == "closed"


def test_editing_symbol_rebinds_to_new_holding(client):
    pid = _platform(client)
    r = client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "TSL", "name": "typo", "currency": "USD", "quantity": 10, "price": 5})
    client.put(f"/api/transactions/{r.json()['id']}", json={"symbol": "TSLA"})
    holds = client.get("/api/holdings?include_closed=true").json()
    derived = {h["symbol"]: h for h in holds if h["source"] == "derived"}
    # old TSL holding emptied (closed), new TSLA holding holds the 10 shares
    assert derived["TSLA"]["quantity"] == 10
    assert derived["TSL"]["status"] == "closed"


def test_derived_holding_rejects_symbol_edit(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 100, "price": 10})
    hid = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]["id"]
    assert client.put(f"/api/holdings/{hid}", json={"symbol": "BABA"}).status_code == 400


def test_derived_holding_cannot_be_deleted(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 100, "price": 10})
    hid = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]["id"]
    assert client.delete(f"/api/holdings/{hid}").status_code == 400
