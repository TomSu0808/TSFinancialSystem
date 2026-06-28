"""Note 新字段（投资决策日志）测试。"""
import pytest


def _platform(client, name="TestP"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _holding(client, pid, symbol="AAPL"):
    r = client.post("/api/holdings", json={
        "platform_id": pid, "currency": "USD", "symbol": symbol,
        "name": "Apple", "quantity": 100, "cost_price": 10,
    })
    assert r.status_code == 200
    return r.json()["id"]


# ─── 创建含新字段 ─────────────────────────────────────────────────────────────

def test_note_create_with_new_fields(client):
    r = client.post("/api/notes", json={
        "title": "AAPL 买入逻辑",
        "content": "增长势头不错",
        "symbol": "AAPL",
        "note_type": "thesis",
        "status": "active",
        "tags": "成长股,科技",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAPL"
    assert body["note_type"] == "thesis"
    assert body["status"] == "active"
    assert body["tags"] == "成长股,科技"


def test_note_defaults(client):
    r = client.post("/api/notes", json={"content": "简单一条笔记"})
    assert r.status_code == 200
    body = r.json()
    assert body["note_type"] == "general"
    assert body["status"] == "active"
    assert body["symbol"] is None


def test_note_update_new_fields(client):
    r = client.post("/api/notes", json={"content": "初始", "note_type": "general"})
    nid = r.json()["id"]
    r2 = client.put(f"/api/notes/{nid}", json={"note_type": "risk", "status": "resolved"})
    assert r2.status_code == 200
    assert r2.json()["note_type"] == "risk"
    assert r2.json()["status"] == "resolved"


# ─── 按字段筛选 ───────────────────────────────────────────────────────────────

def test_filter_by_symbol(client):
    client.post("/api/notes", json={"content": "A", "symbol": "AAPL"})
    client.post("/api/notes", json={"content": "B", "symbol": "BABA"})
    client.post("/api/notes", json={"content": "C"})

    r = client.get("/api/notes?symbol=AAPL")
    assert r.status_code == 200
    notes = r.json()
    assert len(notes) == 1
    assert notes[0]["symbol"] == "AAPL"


def test_filter_by_note_type(client):
    client.post("/api/notes", json={"content": "1", "note_type": "thesis"})
    client.post("/api/notes", json={"content": "2", "note_type": "risk"})
    client.post("/api/notes", json={"content": "3", "note_type": "thesis"})

    r = client.get("/api/notes?note_type=thesis")
    assert r.status_code == 200
    notes = r.json()
    assert len(notes) == 2
    assert all(n["note_type"] == "thesis" for n in notes)


def test_filter_by_status(client):
    client.post("/api/notes", json={"content": "A", "status": "active"})
    client.post("/api/notes", json={"content": "B", "status": "resolved"})
    client.post("/api/notes", json={"content": "C", "status": "active"})

    r = client.get("/api/notes?status=resolved")
    notes = r.json()
    assert len(notes) == 1
    assert notes[0]["status"] == "resolved"


def test_filter_by_source_report_id(client, session):
    from models import ResearchReport, User
    u = session.exec(__import__('sqlmodel').select(User).where(User.username == "tester")).first()
    rep = ResearchReport(user_id=u.id, template_key="t", title="R1", target_name="X")
    session.add(rep)
    session.commit()
    session.refresh(rep)

    client.post("/api/notes", json={"content": "from report", "source_report_id": rep.id})
    client.post("/api/notes", json={"content": "unrelated"})

    r = client.get(f"/api/notes?source_report_id={rep.id}")
    notes = r.json()
    assert len(notes) == 1
    assert notes[0]["source_report_id"] == rep.id


def test_filter_by_related_holding_id(client):
    pid = _platform(client)
    hid = _holding(client, pid)
    client.post("/api/notes", json={"content": "holding note", "related_holding_id": hid})
    client.post("/api/notes", json={"content": "no holding"})

    r = client.get(f"/api/notes?related_holding_id={hid}")
    notes = r.json()
    assert len(notes) == 1
    assert notes[0]["related_holding_id"] == hid


def test_filter_by_keyword(client):
    client.post("/api/notes", json={"title": "苹果分析", "content": "买入理由..."})
    client.post("/api/notes", json={"title": "阿里研究", "content": "观察中"})

    r = client.get("/api/notes?keyword=苹果")
    notes = r.json()
    assert len(notes) == 1
    assert "苹果" in notes[0]["title"]


# ─── 用户隔离 ─────────────────────────────────────────────────────────────────

def test_related_holding_wrong_user(client):
    """related_holding_id 不属于当前用户时应返回 404。"""
    # 持仓 ID 99999 不存在
    r = client.post("/api/notes", json={"content": "x", "related_holding_id": 99999})
    assert r.status_code == 404


def test_notes_user_isolation(client, session):
    """只能查到自己的笔记。"""
    from models import Note, User
    u2 = User(username="other_user", password_hash="x")
    session.add(u2)
    session.commit()
    other_note = Note(user_id=u2.id, content="other user note")
    session.add(other_note)
    session.commit()

    client.post("/api/notes", json={"content": "my note"})
    r = client.get("/api/notes")
    notes = r.json()
    assert all(n["content"] != "other user note" for n in notes)
    assert len(notes) == 1
