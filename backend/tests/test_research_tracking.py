"""tracking-notes 端点、holding research brief 和 prompt 闭环要求测试。"""
import pytest
from sqlmodel import Session, select


def _platform(client, name="Futu"):
    r = client.post("/api/platforms", json={"name": name})
    assert r.status_code == 200
    return r.json()["id"]


def _holding(client, pid, symbol="AAPL", name="Apple"):
    r = client.post("/api/holdings", json={
        "platform_id": pid, "currency": "USD", "symbol": symbol,
        "name": name, "quantity": 10, "cost_price": 100,
    })
    assert r.status_code == 200
    return r.json()["id"]


def _report(session, user_id, report_md=None, symbol=None, related_holding_id=None, title="测试报告"):
    from models import ResearchReport
    rep = ResearchReport(
        user_id=user_id,
        template_key="investment-research",
        title=title,
        target_name=title,
        symbol=symbol,
        related_holding_id=related_holding_id,
        status="completed",
        report_md=report_md,
    )
    session.add(rep)
    session.commit()
    session.refresh(rep)
    return rep.id


# ─── _extract_action_items 提取逻辑 ──────────────────────────────────────────

def test_extract_action_items_chinese(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    md = """# 报告标题

## 结论摘要
不错的公司。

## 行动项
- 下周复盘财报数据
- 跌破 150 再补仓
- 更新 DCF 模型

## 来源
略。
"""
    rid = _report(session, u.id, report_md=md)
    r = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert len(body["notes"]) == 3
    titles = [n["title"] for n in body["notes"]]
    assert any("财报" in t for t in titles)


def test_extract_action_items_english(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    md = """# Research Report

## Summary
Strong company.

## Action Items
- Review Q4 earnings within one week
- Set price alert at 150
* Update DCF model

## Sources
N/A.
"""
    rid = _report(session, u.id, report_md=md)
    r = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert len(body["notes"]) == 3


def test_tracking_notes_no_report_md(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    rid = _report(session, u.id, report_md=None)
    r = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r.status_code == 400
    assert "尚未生成" in r.json()["detail"]


def test_tracking_notes_no_action_items(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    md = "# 报告\n\n## 结论摘要\n没有行动项章节。"
    rid = _report(session, u.id, report_md=md)
    r = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r.status_code == 400
    assert "行动项" in r.json()["detail"]


def test_tracking_notes_duplicate_reuses(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    md = "## 行动项\n- 买入\n- 观察\n"
    rid = _report(session, u.id, report_md=md)

    # First call → creates
    r1 = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r1.json()["created"] is True
    assert len(r1.json()["notes"]) == 2

    # Second call → reuses
    r2 = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r2.json()["reused"] is True
    assert len(r2.json()["notes"]) == 2


def test_tracking_notes_symbol_from_holding(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    pid = _platform(client)
    hid = _holding(client, pid, symbol="TSLA", name="Tesla")

    md = "## 行动项\n- 买入 TSLA\n"
    rid = _report(session, u.id, report_md=md, related_holding_id=hid)

    r = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r.status_code == 200
    notes = r.json()["notes"]
    assert notes[0]["symbol"] == "TSLA"


def test_tracking_notes_symbol_from_report(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    md = "## Action Items\n- Monitor quarterly results\n"
    rid = _report(session, u.id, report_md=md, symbol="NVDA")
    r = client.post(f"/api/research/reports/{rid}/tracking-notes")
    assert r.status_code == 200
    assert r.json()["notes"][0]["symbol"] == "NVDA"


# ─── holding research brief ──────────────────────────────────────────────────

def test_holding_research_brief_basic(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    pid = _platform(client)
    hid = _holding(client, pid, symbol="AAPL")

    # Add a note linked to holding
    client.post("/api/notes", json={
        "content": "AAPL thesis", "related_holding_id": hid, "note_type": "thesis"
    })
    # Add a report linked to holding
    _report(session, u.id, report_md="## 行动项\n- 买\n", related_holding_id=hid)

    r = client.get(f"/api/holdings/{hid}/research-brief")
    assert r.status_code == 200
    body = r.json()
    assert "holding" in body
    assert "notes" in body
    assert "reports" in body
    assert len(body["notes"]) >= 1
    assert len(body["reports"]) >= 1


def test_holding_research_brief_by_symbol(client, session):
    from models import User
    u = session.exec(select(User).where(User.username == "tester")).first()
    pid = _platform(client)
    hid = _holding(client, pid, symbol="BABA")

    # Note linked only by symbol (not holding_id)
    client.post("/api/notes", json={"content": "BABA obs", "symbol": "BABA", "note_type": "observation"})

    r = client.get(f"/api/holdings/{hid}/research-brief")
    assert r.status_code == 200
    notes = r.json()["notes"]
    assert any(n["symbol"] == "BABA" for n in notes)


def test_holding_research_brief_user_isolation(client, session):
    from models import Note, ResearchReport, User
    u2 = User(username="other2", password_hash="x")
    session.add(u2)
    session.commit()

    pid = _platform(client)
    hid = _holding(client, pid, symbol="MSFT")

    # Note and report from other user
    other_note = Note(user_id=u2.id, content="other note", symbol="MSFT")
    session.add(other_note)
    other_report = ResearchReport(user_id=u2.id, template_key="t", title="R", target_name="R", symbol="MSFT")
    session.add(other_report)
    session.commit()

    r = client.get(f"/api/holdings/{hid}/research-brief")
    assert r.status_code == 200
    body = r.json()
    assert all(n["content"] != "other note" for n in body["notes"])
    assert len(body["reports"]) == 0


# ─── Prompt 研究闭环要求 ──────────────────────────────────────────────────────

def test_prompt_contains_research_loop_zh():
    import research_prompt_builder
    prompt = research_prompt_builder.build_prompt(
        skill_md="# Skill\nContent",
        target_name="腾讯",
        report_language="zh",
    )
    for keyword in ["结论摘要", "核心假设", "主要风险", "待验证问题", "跟踪指标", "行动项"]:
        assert keyword in prompt, f"中文 prompt 缺少章节：{keyword}"


def test_prompt_contains_research_loop_en():
    import research_prompt_builder
    prompt = research_prompt_builder.build_prompt(
        skill_md="# Skill\nContent",
        target_name="Tencent",
        report_language="en",
    )
    for keyword in ["Summary", "Core Assumptions", "Key Risks", "Questions to Verify", "Tracking Metrics", "Action Items"]:
        assert keyword in prompt, f"English prompt missing section: {keyword}"


def test_prompt_action_items_bullet_requirement_zh():
    import research_prompt_builder
    prompt = research_prompt_builder.build_prompt(
        skill_md="test", target_name="X", report_language="zh"
    )
    assert "清单列表" in prompt


def test_prompt_action_items_bullet_requirement_en():
    import research_prompt_builder
    prompt = research_prompt_builder.build_prompt(
        skill_md="test", target_name="X", report_language="en"
    )
    assert "bullet list" in prompt
