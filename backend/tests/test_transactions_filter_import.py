"""交易筛选 + CSV 导入测试。"""
import io


def _platform(client, name="Futu"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _buy(client, pid, **kw):
    base = {"platform_id": pid, "action": "buy", "symbol": "AAPL",
            "name": "Apple", "currency": "USD", "date": "2026-01-01", "quantity": 10, "price": 10}
    return client.post("/api/transactions", json={**base, **kw})


# ─── 筛选测试 ────────────────────────────────────────────────────────────────

def test_filter_by_action(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 10, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "sell", "date": "2026-02-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 5, "price": 12})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "deposit", "date": "2026-03-01", "currency": "CNY", "amount": 5000})

    buys = client.get("/api/transactions?action=buy").json()
    assert len(buys) == 1 and buys[0]["action"] == "buy"

    sells = client.get("/api/transactions?action=sell").json()
    assert len(sells) == 1 and sells[0]["action"] == "sell"

    deposits = client.get("/api/transactions?action=deposit").json()
    assert len(deposits) == 1


def test_filter_by_currency(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 10, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-02",
        "symbol": "600519", "currency": "CNY", "quantity": 1, "price": 1800})

    usd = client.get("/api/transactions?currency=USD").json()
    assert all(t["currency"] == "USD" for t in usd)
    assert len(usd) == 1

    cny = client.get("/api/transactions?currency=CNY").json()
    assert len(cny) == 1


def test_filter_by_keyword(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "name": "Apple Inc", "currency": "USD", "quantity": 10, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-02",
        "symbol": "BABA", "name": "Alibaba", "currency": "USD", "quantity": 5, "price": 80,
        "note": "长期持有BABA"})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "deposit", "date": "2026-01-03",
        "currency": "CNY", "amount": 1000})

    r = client.get("/api/transactions?keyword=Apple").json()
    assert len(r) == 1 and r[0]["symbol"] == "AAPL"

    r2 = client.get("/api/transactions?keyword=BABA").json()
    assert len(r2) == 1  # matches symbol

    r3 = client.get("/api/transactions?keyword=长期").json()
    assert len(r3) == 1  # matches note


def test_filter_by_date_range(client):
    pid = _platform(client)
    for date in ("2026-01-01", "2026-02-15", "2026-03-31"):
        client.post("/api/transactions", json={
            "platform_id": pid, "action": "deposit", "date": date, "currency": "CNY", "amount": 100})

    r = client.get("/api/transactions?date_from=2026-02-01&date_to=2026-03-01").json()
    assert len(r) == 1 and r[0]["date"] == "2026-02-15"

    r2 = client.get("/api/transactions?date_from=2026-01-01").json()
    assert len(r2) == 3

    r3 = client.get("/api/transactions?date_to=2026-01-31").json()
    assert len(r3) == 1 and r3[0]["date"] == "2026-01-01"


def test_filter_by_platform(client):
    pid1 = _platform(client, "富途")
    pid2 = _platform(client, "老虎")
    client.post("/api/transactions", json={
        "platform_id": pid1, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "currency": "USD", "quantity": 10, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid2, "action": "buy", "date": "2026-01-02",
        "symbol": "BABA", "currency": "USD", "quantity": 5, "price": 80})

    r = client.get(f"/api/transactions?platform_id={pid1}").json()
    assert len(r) == 1 and r[0]["platform_id"] == pid1

    r2 = client.get(f"/api/transactions?platform_id={pid2}").json()
    assert len(r2) == 1 and r2[0]["platform_id"] == pid2


def test_filter_no_params_returns_all(client):
    pid = _platform(client)
    for i in range(3):
        client.post("/api/transactions", json={
            "platform_id": pid, "action": "deposit", "date": f"2026-0{i+1}-01",
            "currency": "CNY", "amount": 100})
    r = client.get("/api/transactions").json()
    assert len(r) == 3


def test_filter_combined(client):
    pid = _platform(client)
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-01-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 10, "price": 10})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "buy", "date": "2026-06-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 5, "price": 15})
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "sell", "date": "2026-03-01",
        "symbol": "AAPL", "name": "Apple", "currency": "USD", "quantity": 3, "price": 12})

    # buy + date range should return 1
    r = client.get("/api/transactions?action=buy&date_from=2026-05-01").json()
    assert len(r) == 1 and r[0]["date"] == "2026-06-01"


# ─── CSV preview 测试 ────────────────────────────────────────────────────────

def _csv(rows, header="date,action,name,symbol,platform,currency,quantity,price,fee,amount,note"):
    lines = [header] + rows
    return "\n".join(lines).encode("utf-8")


def test_csv_preview_valid(client):
    _platform(client, "富途")
    csv_content = _csv([
        "2026-01-01,buy,Apple,AAPL,富途,USD,100,10,,,",
        "2026-02-01,dividend,Apple,AAPL,富途,USD,,,, 50,分红",
    ])
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 2
    assert body["error_rows"] == 0
    assert len(body["rows"]) == 2
    assert all(row["valid"] for row in body["rows"])


def test_csv_preview_invalid_action(client):
    csv_content = _csv(["2026-01-01,purchase,Apple,AAPL,,USD,100,10,,,"])
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["error_rows"] == 1
    assert not body["rows"][0]["valid"]
    assert any("action" in e for e in body["rows"][0]["errors"])


def test_csv_preview_unknown_platform(client):
    # 平台"不存在的平台"未创建
    csv_content = _csv(["2026-01-01,buy,Apple,AAPL,不存在的平台,USD,100,10,,,"])
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["error_rows"] == 1
    assert any("不存在" in e for e in body["rows"][0]["errors"])


def test_csv_preview_invalid_number(client):
    csv_content = _csv(["2026-01-01,buy,Apple,AAPL,,USD,abc,10,,,"])
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["error_rows"] == 1
    assert any("quantity" in e for e in body["rows"][0]["errors"])


def test_csv_preview_missing_date(client):
    csv_content = _csv([",buy,Apple,AAPL,,USD,100,10,,,"])
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    assert r.json()["error_rows"] == 1


def test_csv_preview_bom_encoding(client):
    # Excel-style UTF-8 BOM
    csv_bytes = b"\xef\xbb\xbfdate,action,name,symbol,platform,currency,quantity,price,fee,amount,note\n2026-01-01,deposit,,,, CNY,,,, 500,\n"
    r = client.post("/api/transactions/import/preview",
                    files={"file": ("t.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200
    assert r.json()["valid_rows"] == 1


# ─── CSV commit 测试 ─────────────────────────────────────────────────────────

def test_csv_commit_with_errors_returns_400(client):
    csv_content = _csv([
        "2026-01-01,buy,Apple,AAPL,,USD,100,10,,,",
        "bad-date,buy,Apple,AAPL,,USD,100,10,,,",  # invalid date
    ])
    r = client.post("/api/transactions/import/commit",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 400
    # 一条都不应该导入
    txns = client.get("/api/transactions").json()
    assert len(txns) == 0


def test_csv_commit_all_valid_imports(client):
    _platform(client, "富途")
    csv_content = _csv([
        "2026-01-01,buy,Apple,AAPL,富途,USD,100,10,,,",
        "2026-02-01,deposit,,,, CNY,,,, 5000,入金",
    ])
    r = client.post("/api/transactions/import/commit",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    assert r.json()["imported"] == 2
    txns = client.get("/api/transactions").json()
    assert len(txns) == 2


def test_csv_commit_syncs_derived_holding(client):
    _platform(client, "富途")
    csv_content = _csv([
        "2026-01-01,buy,Apple,AAPL,富途,USD,100,10,,,",
    ])
    r = client.post("/api/transactions/import/commit",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    holdings = client.get("/api/holdings").json()
    derived = [h for h in holdings if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 100
    assert derived[0]["cost_price"] == 10


def test_csv_commit_buy_sell_syncs_correctly(client):
    _platform(client, "富途")
    csv_content = _csv([
        "2026-01-01,buy,Apple,AAPL,富途,USD,100,10,,,",
        "2026-02-01,sell,Apple,AAPL,富途,USD,50,15,,,",
    ])
    r = client.post("/api/transactions/import/commit",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    holdings = client.get("/api/holdings?include_closed=true").json()
    derived = [h for h in holdings if h["source"] == "derived"]
    assert len(derived) == 1
    assert derived[0]["quantity"] == 50
    # realized pnl = 50*(15-10) = 250
    assert derived[0]["realized_pnl"] == 250.0


def test_csv_commit_without_platform_column(client):
    """platform 列为空时应正常导入，不绑定平台。"""
    csv_content = _csv([
        "2026-01-01,deposit,,,,CNY,,,, 1000,",
    ])
    r = client.post("/api/transactions/import/commit",
                    files={"file": ("t.csv", csv_content, "text/csv")})
    assert r.status_code == 200
    txns = client.get("/api/transactions").json()
    assert len(txns) == 1
    assert txns[0]["platform_id"] is None
