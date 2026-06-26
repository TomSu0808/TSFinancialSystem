"""投研工作台模块测试。"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from unittest.mock import patch, MagicMock


@pytest.fixture(name="engine2")
def engine2_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session2")
def session2_fixture(engine2):
    with Session(engine2) as session:
        yield session


@pytest.fixture(name="user_a")
def user_a_fixture(session2):
    from models import User
    u = User(username="user_a", password_hash="x")
    session2.add(u)
    session2.commit()
    session2.refresh(u)
    return u


@pytest.fixture(name="user_b")
def user_b_fixture(session2):
    from models import User
    u = User(username="user_b", password_hash="x")
    session2.add(u)
    session2.commit()
    session2.refresh(u)
    return u


def _make_client(engine, user):
    from main import app
    from database import get_session
    from auth import get_current_user

    def get_session_override():
        with Session(engine) as s:
            yield s

    def get_user_override():
        with Session(engine) as s:
            from models import User
            return s.get(User, user.id)

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_user_override
    return TestClient(app)


# ── AI Berkshire Loader 测试 ─────────────────────────────────────

def test_load_vendored_skill():
    """能读取 vendored AI Berkshire skill markdown。"""
    from ai_berkshire_loader import load_skill
    content = load_skill("investment-research")
    assert isinstance(content, str)
    assert len(content) > 100
    assert "Investment Research" in content or "investment" in content.lower()


def test_load_all_skills():
    """所有 14 个 AI Berkshire skill 文件都存在且可读。"""
    from ai_berkshire_loader import AI_BERKSHIRE_SKILLS, load_skill
    for key in AI_BERKSHIRE_SKILLS:
        content = load_skill(key)
        assert len(content) > 50, f"Skill file for '{key}' is too short"


def test_load_unknown_skill_raises():
    """缺少 skill key 时返回清晰的 ValueError。"""
    from ai_berkshire_loader import load_skill
    with pytest.raises(ValueError, match="Unknown AI Berkshire skill key"):
        load_skill("nonexistent-key-xyz")


def test_load_missing_file_raises(tmp_path, monkeypatch):
    """skill 文件缺失时返回清晰的 FileNotFoundError。"""
    from ai_berkshire_loader import AI_BERKSHIRE_SKILLS
    import ai_berkshire_loader as loader

    # Point SKILLS_DIR to empty tmp directory
    monkeypatch.setattr(loader, "SKILLS_DIR", tmp_path)
    from ai_berkshire_loader import load_skill
    with pytest.raises(FileNotFoundError, match="Skill file not found"):
        load_skill("investment-research")


def test_list_skills_returns_all():
    """list_skills() 包含所有模板且每个有 source 字段。"""
    from ai_berkshire_loader import list_skills, AI_BERKSHIRE_SKILLS
    skills = list_skills()
    assert len(skills) == len(AI_BERKSHIRE_SKILLS)
    for s in skills:
        assert "key" in s
        assert "name" in s
        assert "source" in s
        assert s["source"] == "AI Berkshire"


# ── Prompt Builder 测试 ──────────────────────────────────────────

def test_prompt_builder_zh_contains_chinese_instruction():
    """中文任务 prompt 包含中文输出要求。"""
    from research_prompt_builder import build_prompt
    prompt = build_prompt(
        skill_md="# Test Skill\nDo analysis.",
        target_name="苹果公司",
        report_language="zh",
    )
    assert "简体中文" in prompt or "中文" in prompt


def test_prompt_builder_en_contains_english_instruction():
    """英文任务 prompt 包含英文输出要求。"""
    from research_prompt_builder import build_prompt
    prompt = build_prompt(
        skill_md="# Test Skill\nDo analysis.",
        target_name="Apple Inc",
        report_language="en",
    )
    assert "English" in prompt


def test_prompt_builder_contains_skill_md():
    """最终 prompt 包含原始 skill markdown。"""
    from research_prompt_builder import build_prompt
    skill = "# My Skill\nVery specific framework content."
    prompt = build_prompt(skill_md=skill, target_name="Test Corp")
    assert "Very specific framework content." in prompt


def test_prompt_builder_contains_attribution():
    """最终 prompt 包含 AI Berkshire attribution。"""
    from research_prompt_builder import build_prompt
    prompt = build_prompt(skill_md="# Skill", target_name="Test")
    assert "xbtlin/ai-berkshire" in prompt


def test_prompt_builder_zh_disclaimer():
    """中文 prompt 包含中文免责声明。"""
    from research_prompt_builder import build_prompt
    prompt = build_prompt(skill_md="# Skill", target_name="T", report_language="zh")
    assert "免责声明" in prompt


def test_prompt_builder_en_disclaimer():
    """英文 prompt 包含英文免责声明。"""
    from research_prompt_builder import build_prompt
    prompt = build_prompt(skill_md="# Skill", target_name="T", report_language="en")
    assert "Disclaimer" in prompt


# ── Templates 接口 ───────────────────────────────────────────────

def test_templates_public(engine2, user_a):
    """GET /templates 返回 AI Berkshire 模板列表，含 source 字段。"""
    client = _make_client(engine2, user_a)
    resp = client.get("/api/research/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    keys = [t["key"] for t in data]
    assert "investment-research" in keys
    assert "portfolio-review" in keys
    # All have source = "AI Berkshire"
    for t in data:
        assert t.get("source") == "AI Berkshire"
    client.app.dependency_overrides.clear()


# ── 报告接口需要登录 ──────────────────────────────────────────

def test_reports_require_auth():
    """未注入鉴权时，访问 /reports 应返回 401。"""
    from main import app
    from database import get_session
    from auth import get_current_user
    from fastapi import HTTPException

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_session_override():
        with Session(engine) as s:
            yield s

    def auth_fail():
        raise HTTPException(status_code=401, detail="Unauthorized")

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = auth_fail
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/research/reports")
    app.dependency_overrides.clear()
    assert resp.status_code == 401


# ── 创建 AI 投研任务（mock AI）──────────────────────────────────

def test_create_run_saves_skill_md_and_language(engine2, user_a):
    """POST /runs 创建任务时保存 skill_md 和 report_language（mock AI）。"""
    client = _make_client(engine2, user_a)

    with patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="mock-response-id-123"):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "苹果公司",
            "symbol": "AAPL",
            "market": "US",
            "report_language": "zh",
        })

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["skill_md"] is not None
    assert len(data["skill_md"]) > 50
    assert data["report_language"] == "zh"
    assert data["status"] in ("running", "queued", "failed")
    client.app.dependency_overrides.clear()


def test_create_run_en_language(engine2, user_a):
    """英文任务 prompt 包含英文输出要求。"""
    client = _make_client(engine2, user_a)

    with patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="mock-id-en"):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "Apple Inc",
            "report_language": "en",
        })

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["report_language"] == "en"
    assert data["prompt_md"] is not None
    assert "English" in data["prompt_md"]
    client.app.dependency_overrides.clear()


def test_create_run_no_ai_configured(engine2, user_a):
    """AI 未配置时返回 400 错误，不创建报告。"""
    client = _make_client(engine2, user_a)

    with patch("ai_client.is_configured", return_value=False):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "苹果公司",
        })

    assert resp.status_code == 400
    assert "not configured" in resp.json().get("detail", "").lower()
    client.app.dependency_overrides.clear()


def test_create_run_unknown_skill(engine2, user_a):
    """未知 skill key 返回 400。"""
    client = _make_client(engine2, user_a)

    with patch("ai_client.is_configured", return_value=True):
        resp = client.post("/api/research/runs", json={
            "template_key": "totally-unknown-skill",
            "target_name": "Test",
        })

    assert resp.status_code == 400
    client.app.dependency_overrides.clear()


# ── 用户隔离 ─────────────────────────────────────────────────────

def test_report_isolation(engine2, user_a, user_b):
    client_a = _make_client(engine2, user_a)
    resp = client_a.post("/api/research/reports", json={
        "template_key": "investment-research",
        "title": "测试报告 A",
        "target_name": "苹果",
    })
    assert resp.status_code == 200
    report_id = resp.json()["id"]

    from main import app
    from database import get_session
    from auth import get_current_user

    def get_session_override():
        with Session(engine2) as s:
            yield s

    def get_user_b():
        with Session(engine2) as s:
            from models import User
            return s.get(User, user_b.id)

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_user_b
    client_b = TestClient(app)

    resp_b = client_b.get("/api/research/reports")
    assert resp_b.status_code == 200
    ids_b = [r["id"] for r in resp_b.json()]
    assert report_id not in ids_b
    app.dependency_overrides.clear()


def test_cross_user_access_denied(engine2, user_a, user_b):
    client_b = _make_client(engine2, user_b)
    resp = client_b.post("/api/research/reports", json={
        "template_key": "investment-research",
        "title": "用户B的报告",
        "target_name": "腾讯",
    })
    assert resp.status_code == 200
    rid = resp.json()["id"]

    client_a = _make_client(engine2, user_a)
    assert client_a.get(f"/api/research/reports/{rid}").status_code == 404
    assert client_a.put(f"/api/research/reports/{rid}", json={"title": "hacked"}).status_code == 404
    assert client_a.delete(f"/api/research/reports/{rid}").status_code == 404
    client_a.app.dependency_overrides.clear()


def test_holding_ownership_check_on_runs(engine2, user_a, user_b):
    """用户不能使用其他用户的持仓创建投研任务。"""
    from models import Platform, Holding

    with Session(engine2) as s:
        plat = Platform(user_id=user_b.id, name="B平台")
        s.add(plat)
        s.commit()
        s.refresh(plat)
        h = Holding(user_id=user_b.id, platform_id=plat.id, name="B的持仓", symbol="TEST")
        s.add(h)
        s.commit()
        s.refresh(h)
        holding_b_id = h.id

    client_a = _make_client(engine2, user_a)
    with patch("ai_client.is_configured", return_value=True):
        resp = client_a.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "TEST",
            "related_holding_id": holding_b_id,
        })
    assert resp.status_code in (400, 404)
    client_a.app.dependency_overrides.clear()


def test_holding_ownership_check_on_reports(engine2, user_a, user_b):
    """用户不能通过 /reports 关联其他用户的持仓。"""
    from models import Platform, Holding

    with Session(engine2) as s:
        plat = Platform(user_id=user_b.id, name="B平台2")
        s.add(plat)
        s.commit()
        s.refresh(plat)
        h = Holding(user_id=user_b.id, platform_id=plat.id, name="B持仓2", symbol="TST2")
        s.add(h)
        s.commit()
        s.refresh(h)
        holding_b_id = h.id

    client_a = _make_client(engine2, user_a)
    resp = client_a.post("/api/research/reports", json={
        "template_key": "investment-research",
        "title": "尝试关联B持仓",
        "target_name": "TEST",
        "related_holding_id": holding_b_id,
    })
    assert resp.status_code in (400, 404)
    client_a.app.dependency_overrides.clear()


# ── Prompt 生成接口（旧接口保留）────────────────────────────────

def test_prompt_single_holding_context(engine2, user_a):
    from models import Platform, Holding

    with Session(engine2) as s:
        plat = Platform(user_id=user_a.id, name="平台A")
        s.add(plat)
        s.commit()
        s.refresh(plat)
        h = Holding(
            user_id=user_a.id, platform_id=plat.id,
            name="苹果公司", symbol="AAPL", market="US",
            quantity=10.0, cost_price=150.0, current_price=180.0,
        )
        s.add(h)
        s.commit()
        s.refresh(h)
        holding_id = h.id

    client = _make_client(engine2, user_a)
    resp = client.post("/api/research/prompts", json={
        "template_key": "investment-research",
        "target_name": "苹果公司",
        "symbol": "AAPL",
        "market": "US",
        "holding_id": holding_id,
    })
    assert resp.status_code == 200
    prompt = resp.json()["prompt"]
    assert "苹果公司" in prompt
    assert "AAPL" in prompt
    client.app.dependency_overrides.clear()


def test_prompt_portfolio_review(engine2, user_a):
    from models import Platform, Holding

    with Session(engine2) as s:
        plat = Platform(user_id=user_a.id, name="平台X")
        s.add(plat)
        s.commit()
        s.refresh(plat)
        for name, sym in [("腾讯", "0700"), ("阿里", "9988")]:
            s.add(Holding(
                user_id=user_a.id, platform_id=plat.id,
                name=name, symbol=sym, market="HK",
                quantity=100.0, cost_price=50.0, current_price=60.0,
            ))
        s.commit()

    client = _make_client(engine2, user_a)
    resp = client.post("/api/research/prompts", json={
        "template_key": "portfolio-review",
        "target_name": "",
    })
    assert resp.status_code == 200
    prompt = resp.json()["prompt"]
    assert "腾讯" in prompt
    assert "阿里" in prompt
    client.app.dependency_overrides.clear()


# ── Backup 测试 ────────────────────────────────────────────────

def test_backup_includes_research_reports_with_new_fields(engine2, user_a):
    """backup export 包含 skill_md、report_language 等新字段。"""
    client = _make_client(engine2, user_a)

    client.post("/api/research/reports", json={
        "template_key": "investment-research",
        "title": "备份测试报告",
        "target_name": "测试公司",
        "report_language": "en",
    })

    resp = client.get("/api/backup")
    assert resp.status_code == 200
    data = resp.json()
    assert "research_reports" in data
    assert len(data["research_reports"]) == 1
    r = data["research_reports"][0]
    assert r["title"] == "备份测试报告"
    assert "report_language" in r
    assert r["report_language"] == "en"
    assert "skill_md" in r
    assert "input_context_md" in r
    assert "sources_json" in r
    assert "completed_at" in r
    client.app.dependency_overrides.clear()


def test_backup_import_restores_skill_md_and_language(engine2, user_a):
    """backup import 恢复 skill_md 和 report_language。"""
    client = _make_client(engine2, user_a)

    client.post("/api/research/reports", json={
        "template_key": "investment-research",
        "title": "原始报告",
        "target_name": "公司A",
        "report_language": "en",
    })

    export_resp = client.get("/api/backup")
    data = export_resp.json()
    # Manually set skill_md in the export payload
    data["research_reports"][0]["skill_md"] = "# Archived Skill\nTest content."
    data["research_reports"][0]["report_md"] = "## Report\nTest report."

    import_resp = client.post("/api/backup/import", json={
        "platforms": [],
        "holdings": [],
        "transactions": [],
        "notes": [],
        "research_reports": data["research_reports"],
    })
    assert import_resp.status_code == 200

    reports_resp = client.get("/api/research/reports")
    assert reports_resp.status_code == 200
    reports = reports_resp.json()
    assert len(reports) == 1
    assert reports[0]["title"] == "原始报告"
    assert reports[0]["report_language"] == "en"
    assert reports[0]["skill_md"] == "# Archived Skill\nTest content."
    assert reports[0]["report_md"] == "## Report\nTest report."
    client.app.dependency_overrides.clear()
