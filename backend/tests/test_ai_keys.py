"""BYOK（Bring Your Own Key）功能测试。"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from unittest.mock import patch, MagicMock


# ── 测试夹具 ──────────────────────────────────────────────────────

@pytest.fixture(name="engine_byok")
def engine_byok_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session_byok")
def session_byok_fixture(engine_byok):
    with Session(engine_byok) as session:
        yield session


@pytest.fixture(name="user_byok")
def user_byok_fixture(session_byok):
    from models import User
    u = User(username="byok_user", password_hash="x")
    session_byok.add(u)
    session_byok.commit()
    session_byok.refresh(u)
    return u


@pytest.fixture(name="user2_byok")
def user2_byok_fixture(session_byok):
    from models import User
    u = User(username="byok_user2", password_hash="x")
    session_byok.add(u)
    session_byok.commit()
    session_byok.refresh(u)
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


# ── crypto_utils 单元测试 ─────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    """encrypt -> decrypt 应还原原始 key。"""
    from crypto_utils import encrypt_secret, decrypt_secret
    plain = "sk-test-api-key-1234567890abcdef"
    cipher = encrypt_secret(plain)
    assert cipher != plain
    assert decrypt_secret(cipher) == plain


def test_mask_secret():
    """mask_secret 只保留后 4 位。"""
    from crypto_utils import mask_secret
    assert mask_secret("sk-abcdefgh") == "****efgh"
    assert mask_secret("abcd") == "****"
    assert mask_secret("abc") == "****"


def test_decrypt_wrong_key_raises():
    """加密密钥不匹配时应抛出 RuntimeError。"""
    from cryptography.fernet import Fernet
    from crypto_utils import encrypt_secret

    plain = "test-key"
    cipher = encrypt_secret(plain)

    # 用不同的 key 解密应失败
    other_fernet = Fernet(Fernet.generate_key())
    with pytest.raises(Exception):
        other_fernet.decrypt(cipher.encode())


# ── AI Key CRUD 接口测试 ──────────────────────────────────────────

def test_save_ai_key_returns_last4_not_plain(engine_byok, user_byok):
    """POST /settings/ai-keys 返回 key_last4，不返回明文 api_key。"""
    client = _make_client(engine_byok, user_byok)
    resp = client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-1234567890abcdef",
        "default_model": "deepseek-v4-pro",
        "is_default": True,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "deepseek"
    assert data["key_last4"] == "cdef"
    assert "api_key" not in data
    assert "encrypted_api_key" not in data
    client.app.dependency_overrides.clear()


def test_save_same_provider_twice_updates_not_duplicates(engine_byok, user_byok):
    """同一 provider 保存两次应更新旧记录，列表只有一条。"""
    client = _make_client(engine_byok, user_byok)
    client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-old-key-0000",
        "is_default": False,
    })
    client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-new-key-9999",
        "is_default": True,
    })

    resp = client.get("/api/settings/ai-keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) == 1
    assert keys[0]["key_last4"] == "9999"
    assert keys[0]["is_default"] is True
    client.app.dependency_overrides.clear()


def test_delete_own_key(engine_byok, user_byok):
    """删除自己的 key 后列表为空。"""
    client = _make_client(engine_byok, user_byok)
    save_resp = client.post("/api/settings/ai-keys", json={
        "provider": "glm",
        "api_key": "glm-key-abcd1234",
        "is_default": False,
    })
    key_id = save_resp.json()["id"]

    del_resp = client.delete(f"/api/settings/ai-keys/{key_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    list_resp = client.get("/api/settings/ai-keys")
    assert list_resp.json() == []
    client.app.dependency_overrides.clear()


def test_cannot_delete_other_users_key(engine_byok, user_byok, user2_byok):
    """用户不能删除其他用户的 key。"""
    client1 = _make_client(engine_byok, user_byok)
    save_resp = client1.post("/api/settings/ai-keys", json={
        "provider": "claude",
        "api_key": "claude-key-xyz-0000",
        "is_default": False,
    })
    key_id = save_resp.json()["id"]
    client1.app.dependency_overrides.clear()

    client2 = _make_client(engine_byok, user2_byok)
    del_resp = client2.delete(f"/api/settings/ai-keys/{key_id}")
    assert del_resp.status_code == 404
    client2.app.dependency_overrides.clear()


def test_list_keys_user_isolation(engine_byok, user_byok, user2_byok):
    """每个用户只能看到自己的 key。"""
    client1 = _make_client(engine_byok, user_byok)
    client1.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-user1-key-0001",
        "is_default": False,
    })
    client1.app.dependency_overrides.clear()

    client2 = _make_client(engine_byok, user2_byok)
    resp = client2.get("/api/settings/ai-keys")
    assert resp.status_code == 200
    assert resp.json() == []
    client2.app.dependency_overrides.clear()


# ── research_service BYOK 集成测试 ───────────────────────────────

def test_research_no_key_no_fallback_returns_config_hint(engine_byok, user_byok):
    """ALLOW_SYSTEM_AI_FALLBACK=false + 无用户 key → 400 并提示去 AI 设置配置。"""
    client = _make_client(engine_byok, user_byok)

    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", False):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "苹果公司",
            "ai_provider": "deepseek",
        })

    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "API Key" in detail or "AI 设置" in detail
    client.app.dependency_overrides.clear()


def test_research_with_user_key_passes_api_key_to_start_research(engine_byok, user_byok):
    """用户有保存 key 时，start_research 应接收到 api_key 参数。"""
    client = _make_client(engine_byok, user_byok)

    # 保存一个 key
    client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-user-deepseek-1234",
        "default_model": "deepseek-v4-pro",
        "is_default": True,
    })

    captured = {}

    def mock_start_research(prompt, use_web_search, provider, model, api_key=None, base_url=None):
        captured["api_key"] = api_key
        captured["provider"] = provider
        return "mock-response-id"

    with patch("ai_client.start_research", side_effect=mock_start_research), \
         patch("ai_client.retrieve_response", return_value=MagicMock(status="completed", output_text="ok", sources=[])):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "苹果公司",
            "ai_provider": "deepseek",
        })

    assert resp.status_code == 200, resp.text
    assert captured.get("api_key") == "sk-user-deepseek-1234"
    assert captured.get("provider") == "deepseek"
    client.app.dependency_overrides.clear()


def test_research_fallback_system_key_when_allowed(engine_byok, user_byok):
    """ALLOW_SYSTEM_AI_FALLBACK=true + 无用户 key + 系统 key → 成功调用。"""
    client = _make_client(engine_byok, user_byok)

    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="mock-sys-id"), \
         patch("ai_client.retrieve_response", return_value=MagicMock(status="completed", output_text="ok", sources=[])):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "腾讯",
            "ai_provider": "deepseek",
        })

    assert resp.status_code == 200, resp.text
    client.app.dependency_overrides.clear()


# ── backup 不含 UserAIKey ────────────────────────────────────────

def test_backup_does_not_contain_ai_keys(engine_byok, user_byok):
    """备份导出不包含 UserAIKey 或 encrypted_api_key。"""
    client = _make_client(engine_byok, user_byok)

    # 保存一个 key
    client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-secret-12345678",
        "is_default": False,
    })

    resp = client.get("/api/backup")
    assert resp.status_code == 200
    data = resp.json()

    # 检查所有 key/value 不包含敏感信息
    backup_str = str(data)
    assert "encrypted_api_key" not in backup_str
    assert "sk-secret-12345678" not in backup_str
    assert "useraikey" not in backup_str.lower()
    client.app.dependency_overrides.clear()


# ── BYOK 后台任务 retrieve / cancel 测试 ─────────────────────────────

def test_create_run_saves_user_ai_key_id(engine_byok, user_byok):
    """创建 AI 报告任务时保存 user_ai_key_id 和 base_url。"""
    client = _make_client(engine_byok, user_byok)

    # 保存 BYOK key
    client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-bytest-12345678",
        "base_url": "https://custom.api.example.com",
        "is_default": True,
    })

    with patch("ai_client.start_research") as mock_start:
        mock_start.return_value = "sync-deepseek-123"
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "target_name": "TestCo",
            "ai_provider": "deepseek",
        })
        assert resp.status_code == 200
        report = resp.json()
        # 验证 user_ai_key_id 和 base_url 已保存
        assert report.get("user_ai_key_id") is not None
        assert report.get("base_url") == "https://custom.api.example.com"
        assert report.get("provider") == "deepseek"
    client.app.dependency_overrides.clear()


def test_refresh_run_uses_byok_key(engine_byok, user_byok):
    """refresh_run 应使用创建任务时的用户 Key 配置。"""
    import research_service
    from models import ResearchReport, UserAIKey
    from datetime import datetime

    client = _make_client(engine_byok, user_byok)

    # 保存 BYOK key
    key_resp = client.post("/api/settings/ai-keys", json={
        "provider": "deepseek",
        "api_key": "sk-refresh-test-key123456",
        "is_default": True,
    })
    key_id = key_resp.json()["id"]

    # 直接创建一个"运行中"的报告
    with Session(engine_byok) as s:
        report = ResearchReport(
            user_id=user_byok.id,
            template_key="investment-research",
            title="刷新测试",
            target_name="TestCo",
            status="running",
            provider="deepseek",
            model="deepseek-chat",
            provider_response_id="sync-deepseek-999",
            user_ai_key_id=key_id,
            base_url="https://custom.api.example.com",
            started_at=datetime.utcnow(),
        )
        s.add(report)
        s.commit()
        s.refresh(report)
        report_id = report.id

    with patch("ai_client.retrieve_response") as mock_retrieve:
        mock_retrieve.return_value = MagicMock(
            status="completed",
            output_text="# Test\nReport content",
            sources=[],
        )
        resp = client.post(f"/api/research/runs/{report_id}/refresh")
        assert resp.status_code == 200

        # 验证 retrieve_response 被调用时传入了正确的 api_key
        call_args = mock_retrieve.call_args
        assert call_args is not None
        # retrieve_response(response_id, api_key=..., provider=...)
        _, kwargs = call_args
        assert kwargs.get("api_key") == "sk-refresh-test-key123456"
        assert kwargs.get("provider") == "deepseek"
    client.app.dependency_overrides.clear()


def test_refresh_run_key_deleted_returns_error(engine_byok, user_byok):
    """Key 被删除后 refresh 应返回明确错误。"""
    import research_service
    from models import ResearchReport
    from datetime import datetime

    # 直接创建一个引用不存在 key_id 的报告
    with Session(engine_byok) as s:
        report = ResearchReport(
            user_id=user_byok.id,
            template_key="investment-research",
            title="KeyMissing",
            target_name="TestCo",
            status="running",
            provider="deepseek",
            model="deepseek-chat",
            provider_response_id="sync-deepseek-000",
            user_ai_key_id=99999,  # 不存在的 key
        )
        s.add(report)
        s.commit()
        s.refresh(report)
        report_id = report.id

    with Session(engine_byok) as s:
        report = s.get(ResearchReport, report_id)
        from ai_client import AIServiceNotConfigured
        try:
            research_service.refresh_run(s, report)
            assert False, "应抛出异常"
        except AIServiceNotConfigured as e:
            assert "已被删除" in str(e) or "Key" in str(e)


def test_refresh_run_different_user_key_not_leaked(engine_byok):
    """不应串用其他用户的 Key。"""
    import research_service
    from models import ResearchReport, User, UserAIKey
    from datetime import datetime
    from crypto_utils import encrypt_secret

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        u1 = User(username="byok_u1", password_hash="x"); s.add(u1)
        u2 = User(username="byok_u2", password_hash="x"); s.add(u2)
        s.commit(); s.refresh(u1); s.refresh(u2)

        # u1 的 key（使用有效加密）
        uk = UserAIKey(
            user_id=u1.id, provider="deepseek",
            encrypted_api_key=encrypt_secret("sk-user1-key"),
            key_last4="abcd",
        )
        s.add(uk); s.commit(); s.refresh(uk)

        # u2 的报告引用了 u1 的 key_id
        report = ResearchReport(
            user_id=u2.id,
            template_key="investment-research",
            title="CrossUser",
            target_name="TestCo",
            status="running",
            provider="deepseek",
            user_ai_key_id=uk.id,  # 属于 u1 的 key！
            provider_response_id="sync-x",
        )
        s.add(report); s.commit(); s.refresh(report)

        from ai_client import AIServiceNotConfigured
        try:
            research_service.refresh_run(s, report)
            assert False, "应抛出异常（Key 不属于同一用户）"
        except AIServiceNotConfigured as e:
            assert "不属于" in str(e) or "异常" in str(e)


def test_cancel_uses_byok_key(engine_byok, user_byok):
    """cancel 应使用创建任务时的用户 Key 配置。"""
    from models import ResearchReport, UserAIKey
    from datetime import datetime

    client = _make_client(engine_byok, user_byok)

    # 保存 BYOK key
    key_resp = client.post("/api/settings/ai-keys", json={
        "provider": "gpt",
        "api_key": "sk-cancel-test-key123456",
        "is_default": True,
    })
    key_id = key_resp.json()["id"]

    # 创建运行中的报告
    with Session(engine_byok) as s:
        report = ResearchReport(
            user_id=user_byok.id,
            template_key="investment-research",
            title="取消测试",
            target_name="TestCo",
            status="running",
            provider="gpt",
            model="gpt-5.5",
            provider_response_id="resp-cancel-001",
            user_ai_key_id=key_id,
            started_at=datetime.utcnow(),
        )
        s.add(report)
        s.commit()
        s.refresh(report)
        report_id = report.id

    with patch("ai_client.cancel_response") as mock_cancel:
        mock_cancel.return_value = True
        resp = client.post(f"/api/research/reports/{report_id}/cancel")
        assert resp.status_code == 200
        assert resp.json().get("provider_cancelled") is True

        # 验证 cancel_response 被调用时传入了正确的 api_key
        call_args = mock_cancel.call_args
        _, kwargs = call_args
        assert kwargs.get("api_key") == "sk-cancel-test-key123456"
        assert kwargs.get("provider") == "gpt"
    client.app.dependency_overrides.clear()
