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
    # change the buy into a deposit (no longer drives the stock position; cash holding created)
    client.put(f"/api/transactions/{r.json()['id']}", json={"action": "deposit"})
    derived = [h for h in client.get("/api/holdings?include_closed=true").json() if h["source"] == "derived"]
    # Now includes 1 stock holding (closed) + 1 cash holding
    stock_holdings = [h for h in derived if h["asset_type"] != "cash"]
    assert len(stock_holdings) == 1
    assert stock_holdings[0]["quantity"] == 0.0          # buy no longer counts
    assert stock_holdings[0]["status"] == "closed"
    # Cash holding should exist
    cash = [h for h in derived if h["asset_type"] == "cash"]
    assert len(cash) == 1
    assert cash[0]["manual_value"] > 0


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


def test_client_supplied_holding_id_is_ignored_on_create(client):
    pid = _platform(client)
    # bogus holding_id 99999 must not stick; system resolves its own derived holding
    r = client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 100, "price": 10,
        "holding_id": 99999})
    assert r.status_code == 200
    derived = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    txns = client.get("/api/transactions").json()
    assert txns[0]["holding_id"] == derived["id"]      # bound to the real holding, not 99999


def test_action_change_to_deposit_clears_holding_id(client):
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    r = client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    client.put(f"/api/transactions/{r.json()['id']}", json={"action": "deposit"})
    txn = [t for t in client.get("/api/transactions").json() if t["id"] == r.json()["id"]][0]
    assert txn["holding_id"] is None


# ── 超卖禁止测试 ───────────────────────────────────────────────────

def test_sell_exceeding_available_quantity_is_rejected(client):
    """卖出数量超过持仓应返回 400 错误。"""
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "TSLA", "currency": "USD"}
    # 先买入 50 股
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 50, "price": 10})
    # 尝试卖出 100 股 → 应被拒绝
    r = client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 100, "price": 15})
    assert r.status_code == 400
    assert "超卖" in str(r.json().get("detail", "")) or "超过" in r.text


def test_full_sell_is_allowed(client):
    """全部清仓应允许（卖出 == 当前持仓数量）。"""
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "AAPL", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    r = client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 100, "price": 12})
    assert r.status_code == 200
    # 清仓后持仓状态应为 closed
    h = [h for h in client.get("/api/holdings?include_closed=true").json() if h["source"] == "derived"][0]
    assert h["status"] == "closed"


def test_partial_sell_is_allowed(client):
    """部分卖出应允许。"""
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "NVDA", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    r = client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 30, "price": 12})
    assert r.status_code == 200
    h = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert h["quantity"] == 70


def test_sell_without_holding_is_rejected(client):
    """没有持仓时卖出应被拒绝。"""
    pid = _platform(client)
    r = client.post("/api/transactions", json={
        "platform_id": pid, "symbol": "MSFT", "currency": "USD",
        "action": "sell", "date": "2026-01-01", "quantity": 10, "price": 100,
    })
    assert r.status_code == 400


def test_update_transaction_to_oversell_rejected(client):
    """修改历史交易导致超卖应被拒绝。"""
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "BABA", "currency": "USD"}
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 80})
    sell_r = client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 50, "price": 90})
    assert sell_r.status_code == 200

    # 尝试把卖出数量改为 200 → 应被拒绝
    r = client.put(f"/api/transactions/{sell_r.json()['id']}", json={"quantity": 200})
    assert r.status_code == 400


def test_update_buy_to_sell_causing_oversell_rejected(client):
    """把买入改为卖出导致超卖应被拒绝。"""
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "PDD", "currency": "USD"}
    # 只有一笔买入 10 股
    buy_r = client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 10, "price": 100})
    assert buy_r.status_code == 200

    # 再买入 5 股
    client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-02", "quantity": 5, "price": 110})

    # 现在持仓 15 股。把第一笔买入改为卖出 20 股 → 应被拒绝
    r = client.put(f"/api/transactions/{buy_r.json()['id']}", json={"action": "sell", "quantity": 20, "price": 120})
    assert r.status_code == 400


def test_delete_transaction_then_recompute_still_correct(client):
    """删除交易后持仓重算仍正确（不是超卖的回归测试）。"""
    pid = _platform(client)
    base = {"platform_id": pid, "symbol": "GOOGL", "currency": "USD"}
    r1 = client.post("/api/transactions", json={**base, "action": "buy", "date": "2026-01-01", "quantity": 100, "price": 10})
    r2 = client.post("/api/transactions", json={**base, "action": "sell", "date": "2026-02-01", "quantity": 30, "price": 12})
    assert r2.status_code == 200
    client.delete(f"/api/transactions/{r2.json()['id']}")
    h = [h for h in client.get("/api/holdings").json() if h["source"] == "derived"][0]
    assert h["quantity"] == 100
    assert h["cost_price"] == 10


def test_csv_preview_detects_oversell(client):
    """CSV 预览应在卖出超过持仓时标记错误。"""
    pid = _platform(client)
    # 无任何持仓时，CSV 只有 sell 应立即被标记
    platform_name = client.get(f"/api/platforms").json()[0]["name"]
    csv_content = "date,action,name,symbol,platform,currency,quantity,price,fee,amount,note\n"
    csv_content += f"2026-03-01,sell,Apple,AAPL,{platform_name},USD,100,150,,,"
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    preview = r.json()
    assert preview["error_rows"] >= 1
    # 错误信息应包含"超卖"
    errors = [row for row in preview["rows"] if not row["valid"]]
    assert any("超卖" in str(e) for e in errors[0].get("errors", []))
