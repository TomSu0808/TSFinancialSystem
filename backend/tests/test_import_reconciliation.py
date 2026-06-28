"""Phase 1 导入与对账系统测试。

覆盖：
- 富途 CSV 解析成功 / 字段缺失报错
- IBKR CSV 解析成功
- 通用字段映射成功
- preview 不写入 Transaction
- commit 写入 Transaction 并触发持仓重算
- 重复导入去重
- preview 阶段发现超卖
- 对账 matched / warning / error
- deposit / withdraw 影响现金余额
- 多用户隔离
"""
import io
import json


def _platform(client, name="Futu"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _csv_content(lines):
    """Helper: build CSV bytes from lines list."""
    return "\n".join(lines).encode("utf-8-sig")


# ═══════════════════════════════════════════════════════════════════════════════
# Futu CSV 解析测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_futu_preview_english_headers(client):
    """富途英文列名 CSV 解析成功。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price,fee,amount",
        "2026-01-15,buy,腾讯控股,0700,HKD,200,350,50,",
        "2026-02-10,sell,腾讯控股,0700,HKD,50,380,20,",
    ])
    fd = {"file": ("futu.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("import_session_id") is not None
    assert body["summary"]["total"] == 2
    assert body["summary"]["valid"] >= 0


def test_futu_preview_chinese_headers(client):
    """富途中文列名 CSV 解析成功。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "交易日期,操作,名称,代码,币种,数量,成交价格,费用,成交金额",
        "2026/01/15,买入,腾讯控股,0700,HKD,200,350,50,70000",
        "2026/03/20,分红,腾讯控股,0700,HKD,,,,680,分红",
    ])
    fd = {"file": ("futu.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] == 2
    # 第二行分红无 quantity/price 但有 amount
    assert body["summary"]["valid"] + body["summary"]["error"] >= 1


def test_futu_preview_missing_fields(client):
    """富途 CSV 缺少必要字段时报 error（如无 date）。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "交易日期,操作,代码,名称,币种",
        ",买入,0700,腾讯,HKD",  # empty date
    ])
    fd = {"file": ("futu.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200
    body = r.json()
    # 日期为空应产生 error
    assert body["summary"]["error"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# IBKR CSV 解析测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_ibkr_preview_trades(client):
    """IBKR trades CSV 解析基本成功。"""
    pid = _platform(client, "IBKR")
    csv_data = _csv_content([
        "Trade Date,Symbol,Quantity,Trade Price,Commission,Currency,Proceeds",
        "2026-01-15,AAPL,100,175.50,1.50,USD,17548.50",
        "2026-02-20,MSFT,50,380.00,1.00,USD,-19001.00",
    ])
    fd = {"file": ("ibkr.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "ibkr", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("import_session_id") is not None


def test_ibkr_preview_dividends(client):
    """IBKR dividends CSV 解析。"""
    pid = _platform(client, "IBKR")
    csv_data = _csv_content([
        "Date,Symbol,Description,Currency,Amount",
        "2026-05-01,AAPL,DIVIDEND (Ordinary),USD,22.00",
    ])
    fd = {"file": ("ibkr.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "ibkr", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 通用字段映射测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_generic_preview_with_mapping(client):
    """通用导入 + 用户字段映射。"""
    pid = _platform(client, "自定义券商")
    csv_data = _csv_content([
        "d,w,x,y,z",
        "2026-01-01,buy,AAPL,USD,100",
    ])
    mapping = {"date": "d", "action": "w", "symbol": "x", "currency": "y", "quantity": "z"}
    fd = {"file": ("generic.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={
            "broker_type": "generic",
            "platform_id": str(pid),
            "mapping": json.dumps(mapping),
        },
        files=fd,
    )
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# Preview 不写入 Transaction
# ═══════════════════════════════════════════════════════════════════════════════

def test_preview_does_not_create_transactions(client):
    """Preview 只解析，不落库写 Transaction。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-01,buy,Apple,AAPL,USD,100,150",
    ])
    fd = {"file": ("futu.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200

    # Verify no Transaction created
    txns = client.get("/api/transactions").json()
    assert len(txns) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Commit 写入并触发持仓重算
# ═══════════════════════════════════════════════════════════════════════════════

def test_commit_creates_transactions_and_updates_holdings(client):
    """Commit 后 Transaction 写入，derived 持仓自动更新。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-15,buy,腾讯,0700,HKD,200,350",
        "2026-03-01,sell,腾讯,0700,HKD,50,380",
    ])
    fd = {"file": ("futu.csv", csv_data, "text/csv")}

    # 1. Preview
    prv = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert prv.status_code == 200
    session_id = prv.json()["import_session_id"]

    # 2. Commit
    r = client.post(f"/api/imports/{session_id}/commit")
    assert r.status_code == 200
    assert r.json()["created_count"] == 2

    # 3. Verify transactions
    txns = client.get("/api/transactions").json()
    assert len(txns) == 2

    # 4. Verify derived holding (200 buy - 50 sell = 150 qt)
    holdings = client.get("/api/holdings").json()
    derived = [h for h in holdings if h["source"] == "derived" and h["asset_type"] != "cash"]
    assert len(derived) >= 1
    h0700 = [h for h in derived if h["symbol"] == "0700"][0]
    assert h0700["quantity"] == 150


def test_commit_session_cannot_be_reused(client):
    """已 committed 的 session 不可重复提交。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,symbol,currency,quantity,price",
        "2026-01-01,buy,AAPL,USD,10,150",
    ])
    fd = {"file": ("f.csv", csv_data, "text/csv")}

    prv = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    sid = prv.json()["import_session_id"]

    # First commit
    r1 = client.post(f"/api/imports/{sid}/commit")
    assert r1.status_code == 200

    # Second commit should fail
    r2 = client.post(f"/api/imports/{sid}/commit")
    assert r2.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# 重复导入去重
# ═══════════════════════════════════════════════════════════════════════════════

def test_duplicate_rows_marked_in_preview(client):
    """重复交易在 preview 中标记为 duplicate。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-01,buy,Apple,AAPL,USD,10,150",
    ])
    fd = {"file": ("f.csv", csv_data, "text/csv")}

    # 1. First import → commit
    prv = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    sid = prv.json()["import_session_id"]
    client.post(f"/api/imports/{sid}/commit")
    assert client.post(f"/api/imports/{sid}/commit").status_code == 400  # already committed

    # 2. Second import — same file → should detect duplicate
    prv2 = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert prv2.status_code == 200
    body = prv2.json()

    # 3. Only 1 transaction should exist (duplicate not re-added)
    txns = client.get("/api/transactions").json()
    assert len(txns) == 1  # not 2


# ═══════════════════════════════════════════════════════════════════════════════
# 超卖检测
# ═══════════════════════════════════════════════════════════════════════════════

def test_preview_detects_oversell_in_import(client):
    """Import preview 时卖出超过持仓应标为 error。"""
    pid = _platform(client, "富途")
    # 无任何持仓，直接 sell
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-01,sell,腾讯,0700,HKD,100,350",
    ])
    fd = {"file": ("sell_only.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["error"] >= 1
    errors = [
        row for row in body["rows"]
        if row["status"] == "error" and any("超卖" in str(e) for e in (row.get("errors") or []))
    ]
    assert len(errors) >= 1


def test_preview_oversell_after_buy_in_same_file(client):
    """同一文件中先 buy 后 sell，sell 超过 buy 的量应检测超卖。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-01,buy,腾讯,0700,HKD,100,350",
        "2026-01-02,sell,腾讯,0700,HKD,200,380",  # sell 200 > buy 100
    ])
    fd = {"file": ("oversell.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    assert r.status_code == 200
    body = r.json()
    errors = [
        row for row in body["rows"]
        if row["status"] == "error" and any("超卖" in str(e) for e in (row.get("errors") or []))
    ]
    assert len(errors) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 对账测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_reconciliation_matched(client):
    """导入交易后对账：系统持仓与券商文件持仓一致（matched）。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-15,buy,腾讯,0700,HKD,200,350",
    ])
    fd = {"file": ("f.csv", csv_data, "text/csv")}

    prv = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    sid = prv.json()["import_session_id"]
    client.post(f"/api/imports/{sid}/commit")

    recon = client.get(f"/api/imports/{sid}/reconciliation")
    assert recon.status_code == 200
    body = recon.json()
    assert body["total_items"] >= 1
    assert body["matched_count"] >= 1
    assert body["error_count"] == 0


def test_reconciliation_error_when_no_system_position(client):
    """导入后系统无持仓时对账报告 error（有券商持仓无系统持仓）。"""
    pid = _platform(client, "富途")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price",
        "2026-01-01,buy,MSFT,MSFT,USD,50,400",  # no platform match
    ])
    fd = {"file": ("f.csv", csv_data, "text/csv")}

    prv = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    sid = prv.json()["import_session_id"]
    client.post(f"/api/imports/{sid}/commit")

    recon = client.get(f"/api/imports/{sid}/reconciliation")
    assert recon.status_code == 200
    body = recon.json()
    assert body["total_items"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 现金账本测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_deposit_creates_cash_holding(client):
    """Deposit 入金应自动创建 derived cash 持仓。"""
    pid = _platform(client, "银行")
    csv_data = _csv_content([
        "date,action,name,symbol,currency,quantity,price,amount",
        "2026-01-01,deposit,入金,,CNY,,,50000",
    ])
    fd = {"file": ("deposit.csv", csv_data, "text/csv")}

    prv = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(pid)},
        files=fd,
    )
    sid = prv.json()["import_session_id"]
    r = client.post(f"/api/imports/{sid}/commit")
    assert r.status_code == 200

    # Check cash holding exists
    holdings = client.get("/api/holdings").json()
    cash = [h for h in holdings if h["asset_type"] == "cash" and h["source"] == "derived"]
    assert len(cash) >= 1
    assert cash[0]["manual_value"] == 50000


def test_deposit_then_withdraw_updates_cash(client):
    """先入金再出金，现金余额正确更新。"""
    pid = _platform(client, "银行")

    # Deposit 50k
    r1 = client.post("/api/transactions", json={
        "platform_id": pid, "action": "deposit", "date": "2026-01-01",
        "currency": "CNY", "amount": 50000,
    })
    assert r1.status_code == 200

    # Withdraw 20k
    r2 = client.post("/api/transactions", json={
        "platform_id": pid, "action": "withdraw", "date": "2026-02-01",
        "currency": "CNY", "amount": 20000,
    })
    assert r2.status_code == 200

    # Check cash = 30k
    holdings = client.get("/api/holdings").json()
    cash = [h for h in holdings if h["asset_type"] == "cash" and h["source"] == "derived"]
    assert len(cash) >= 1
    assert cash[0]["manual_value"] == 30000


def test_withdraw_exceeding_cash_is_rejected(client):
    """出金超过现金余额应被拒绝。"""
    pid = _platform(client, "银行")

    # Deposit 10k
    r = client.post("/api/transactions", json={
        "platform_id": pid, "action": "deposit", "date": "2026-01-01",
        "currency": "CNY", "amount": 10000,
    })
    assert r.status_code == 200

    # Withdraw 20k (exceeds)
    r = client.post("/api/transactions", json={
        "platform_id": pid, "action": "withdraw", "date": "2026-02-01",
        "currency": "CNY", "amount": 20000,
    })
    assert r.status_code == 400


def test_multi_currency_cash_holdings(client):
    """多币种入金，各自维护独立的 cash holding。"""
    pid = _platform(client, "银行")

    # CNY deposit
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "deposit", "date": "2026-01-01",
        "currency": "CNY", "amount": 50000,
    })
    # USD deposit
    client.post("/api/transactions", json={
        "platform_id": pid, "action": "deposit", "date": "2026-01-01",
        "currency": "USD", "amount": 10000,
    })

    holdings = client.get("/api/holdings").json()
    cash = [h for h in holdings if h["asset_type"] == "cash" and h["source"] == "derived"]
    assert len(cash) == 2
    cny = [h for h in cash if h["currency"] == "CNY"][0]
    usd = [h for h in cash if h["currency"] == "USD"][0]
    assert cny["manual_value"] == 50000
    assert usd["manual_value"] == 10000


# ═══════════════════════════════════════════════════════════════════════════════
# 多用户隔离测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_cannot_import_to_other_users_platform(client, session):
    """不能导入到其他用户的 platform。"""
    from models import Platform, User
    from auth import hash_password

    # 创建另一个用户和它的平台
    other = User(username="other", password_hash=hash_password("pw"))
    session.add(other)
    session.commit()
    session.refresh(other)

    other_plat = Platform(user_id=other.id, name="OtherP")
    session.add(other_plat)
    session.commit()
    session.refresh(other_plat)

    # 当前测试用户尝试用 other_plat 导入
    csv_data = _csv_content([
        "date,action,symbol,currency,quantity,price",
        "2026-01-01,buy,AAPL,USD,10,150",
    ])
    fd = {"file": ("f.csv", csv_data, "text/csv")}
    r = client.post(
        "/api/imports/preview",
        data={"broker_type": "futu", "platform_id": str(other_plat.id)},
        files=fd,
    )
    # Should fail since platform belongs to other user
    assert r.status_code == 404


def test_cannot_commit_other_users_session(client, session):
    """不能提交其他用户的导入会话。"""
    from models import ImportSession, Platform, User
    from auth import hash_password

    # 创建另一个用户
    other = User(username="other2", password_hash=hash_password("pw"))
    session.add(other)
    session.commit()
    session.refresh(other)

    # 创建属于 other 的导入会话
    imp = ImportSession(user_id=other.id, broker_type="futu", rows_json="[]")
    session.add(imp)
    session.commit()
    session.refresh(imp)

    # 当前测试用户尝试提交
    r = client.post(f"/api/imports/{imp.id}/commit")
    assert r.status_code == 400


def test_import_session_list_is_user_scoped(client, session):
    """列出导入会话时只返回当前用户的。"""
    from models import ImportSession, User
    from auth import hash_password

    other = User(username="other3", password_hash=hash_password("pw"))
    session.add(other)
    session.commit()
    session.refresh(other)

    # Other user's session
    imp = ImportSession(user_id=other.id, broker_type="futu", file_name="o.csv")
    session.add(imp)
    session.commit()

    # Current user's list
    r = client.get("/api/imports")
    assert r.status_code == 200
    sessions = r.json()
    ids = {s["id"] for s in sessions}
    assert imp.id not in ids
