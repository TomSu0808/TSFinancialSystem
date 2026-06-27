"""认证系统测试。

覆盖：注册（邮箱可选）、安全问题、email_verified、token 机制、防枚举、旧 JWT 失效、限流核心逻辑。
"""
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import models  # noqa: F401 — 确保所有表注册到 metadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(name="auth_engine")
def auth_engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="auth_client")
def auth_client_fixture(auth_engine):
    from main import app
    from database import get_session
    import rate_limit

    def override():
        with Session(auth_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    rate_limit._store.clear()  # 每个测试独立限流状态
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_session, None)


VALID_USER = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123",
    "security_question_key": "favorite_game",
    "security_answer": "minecraft",
}

VALID_USER_NO_EMAIL = {
    "username": "testuser",
    "password": "password123",
    "security_question_key": "favorite_game",
    "security_answer": "minecraft",
}


def _register(client, **overrides):
    return client.post("/api/auth/register", json={**VALID_USER, **overrides})


def _register_no_email(client, **overrides):
    return client.post("/api/auth/register", json={**VALID_USER_NO_EMAIL, **overrides})


def _login(client, username="testuser", password="password123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _auth_header(client, username="testuser", password="password123"):
    r = _login(client, username, password)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# 注册测试：邮箱可选
# ---------------------------------------------------------------------------

def test_register_no_email_succeeds(auth_client):
    """不填邮箱也能成功注册。"""
    r = _register_no_email(auth_client)
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["username"] == "testuser"
    assert data["user"]["email"] is None
    assert data["user"]["has_email"] is False
    assert data["user"]["email_verified"] is False


def test_register_no_email_no_verification_email_sent(auth_client):
    """不填邮箱时不应发送验证邮件。"""
    send_calls = []
    with patch("routers.auth.send_verification_email", side_effect=lambda *a: send_calls.append(a)):
        r = _register_no_email(auth_client)
    assert r.status_code == 200
    assert len(send_calls) == 0


def test_register_with_email_sends_verification(auth_client):
    """填写邮箱时发送验证邮件。"""
    send_calls = []
    with patch("routers.auth.send_verification_email", side_effect=lambda to, token: send_calls.append((to, token)) or "http://x"):
        r = _register(auth_client)
    assert r.status_code == 200
    assert len(send_calls) == 1
    assert send_calls[0][0] == "test@example.com"


def test_register_with_email_email_verified_false(auth_client):
    """新注册用户 email_verified 应为 false。"""
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client)
    assert r.status_code == 200
    assert r.json()["user"]["email_verified"] is False
    assert r.json()["user"]["has_email"] is True


def test_register_no_security_question_fails(auth_client):
    """缺少安全问题时注册应失败（422 schema 错误）。"""
    r = auth_client.post("/api/auth/register", json={
        "username": "u1",
        "password": "password123",
        # 缺 security_question_key 和 security_answer
    })
    assert r.status_code == 422


def test_register_invalid_security_question_key(auth_client):
    """安全问题 key 不在允许列表中时返回 400。"""
    r = _register(auth_client, security_question_key="not_a_valid_key")
    assert r.status_code == 400


def test_register_security_question_stored(auth_client):
    """注册后 /me 应显示 has_security_question=true 和正确的问题文本。"""
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client)
    token = r.json()["access_token"]
    me = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["has_security_question"] is True
    assert me["security_question_key"] == "favorite_game"
    assert "游戏" in me["security_question_text"]


def test_register_duplicate_username(auth_client):
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)
        r = _register(auth_client, email="other@example.com")
    assert r.status_code == 409


def test_register_duplicate_email(auth_client):
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)
        r = _register(auth_client, username="otheruser")
    assert r.status_code == 409


def test_register_invalid_username(auth_client):
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client, username="ab")          # 太短
        assert r.status_code == 400
        r = _register(auth_client, username="bad user!")   # 含非法字符
        assert r.status_code == 400


def test_register_password_min_8(auth_client):
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client, password="short")
    assert r.status_code == 400


def test_register_invalid_email(auth_client):
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client, email="notanemail")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /me 不暴露 security_answer_hash
# ---------------------------------------------------------------------------

def test_me_does_not_expose_answer_hash(auth_client):
    """UserRead 不应包含 security_answer_hash。"""
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client)
    token = r.json()["access_token"]
    me = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert "security_answer_hash" not in me


# ---------------------------------------------------------------------------
# 邮箱验证测试
# ---------------------------------------------------------------------------

def test_verify_email_success(auth_client):
    """提交正确 token → email_verified=true。"""
    captured = {}

    def mock_send(to, token):
        captured["token"] = token

    with patch("routers.auth.send_verification_email", mock_send):
        _register(auth_client)

    assert "token" in captured
    r = auth_client.post("/api/auth/verify-email", json={"token": captured["token"]})
    assert r.status_code == 200

    headers = _auth_header(auth_client)
    me = auth_client.get("/api/auth/me", headers=headers).json()
    assert me["email_verified"] is True


def test_verify_email_invalid_token(auth_client):
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)
    r = auth_client.post("/api/auth/verify-email", json={"token": "badtoken"})
    assert r.status_code == 400


def test_verify_email_token_reuse_rejected(auth_client):
    """token 已使用后不能再次使用。"""
    captured = {}

    def mock_send(to, token):
        captured["token"] = token

    with patch("routers.auth.send_verification_email", mock_send):
        _register(auth_client)

    auth_client.post("/api/auth/verify-email", json={"token": captured["token"]})
    r = auth_client.post("/api/auth/verify-email", json={"token": captured["token"]})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 安全问题找回密码
# ---------------------------------------------------------------------------

def test_recovery_question_returns_question(auth_client):
    """recovery-question 能返回已设置的问题。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    r = auth_client.post("/api/auth/recovery-question", json={"username": "testuser"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["question_key"] == "favorite_game"
    assert "游戏" in data["question_text"]


def test_recovery_question_nonexistent_user(auth_client):
    """不存在的用户返回 ok=false，不泄露账号信息。"""
    r = auth_client.post("/api/auth/recovery-question", json={"username": "nobody"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_recovery_question_no_sq_via_engine(auth_client, auth_engine):
    """未设置安全问题的用户，recovery-question 返回 ok=false。"""
    with patch("routers.auth.send_verification_email"):
        _register_no_email(auth_client)

    # 把安全问题清掉，模拟迁移前的老用户
    with Session(auth_engine) as s:
        from sqlmodel import select
        from models import User
        u = s.exec(select(User).where(User.username == "testuser")).first()
        u.security_question_key = None
        u.security_answer_hash = None
        s.add(u)
        s.commit()

    r = auth_client.post("/api/auth/recovery-question", json={"username": "testuser"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_reset_by_security_question_correct_answer(auth_client):
    """正确答案可以重置密码。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    r = auth_client.post("/api/auth/reset-password-by-security-question", json={
        "username": "testuser",
        "security_question_key": "favorite_game",
        "security_answer": "minecraft",
        "new_password": "newpassword123",
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 能用新密码登录
    r = _login(auth_client, password="newpassword123")
    assert r.status_code == 200


def test_reset_by_security_question_wrong_answer(auth_client):
    """错误答案返回 400。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    r = auth_client.post("/api/auth/reset-password-by-security-question", json={
        "username": "testuser",
        "security_question_key": "favorite_game",
        "security_answer": "wrong_answer",
        "new_password": "newpassword123",
    })
    assert r.status_code == 400


def test_reset_by_security_question_wrong_key(auth_client):
    """问题 key 不匹配返回 400。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    r = auth_client.post("/api/auth/reset-password-by-security-question", json={
        "username": "testuser",
        "security_question_key": "primary_school",  # 注册时选的是 favorite_game
        "security_answer": "minecraft",
        "new_password": "newpassword123",
    })
    assert r.status_code == 400


def test_reset_by_security_question_invalidates_old_jwt(auth_client):
    """通过安全问题重置密码后，旧 JWT 应 401。"""
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client)
    old_jwt = r.json()["access_token"]

    time.sleep(1.1)

    auth_client.post("/api/auth/reset-password-by-security-question", json={
        "username": "testuser",
        "security_question_key": "favorite_game",
        "security_answer": "minecraft",
        "new_password": "newpassword456",
    })

    r = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_jwt}"})
    assert r.status_code == 401


def test_reset_by_security_question_answer_case_insensitive(auth_client):
    """答案比对应大小写不敏感。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    r = auth_client.post("/api/auth/reset-password-by-security-question", json={
        "username": "testuser",
        "security_question_key": "favorite_game",
        "security_answer": "MINECRAFT",  # 大写，应该匹配
        "new_password": "newpassword123",
    })
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# set-security-question（登录后修改）
# ---------------------------------------------------------------------------

def test_set_security_question_success(auth_client):
    """登录后可修改安全问题。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)
    headers = _auth_header(auth_client)

    r = auth_client.post("/api/auth/set-security-question", json={
        "current_password": "password123",
        "security_question_key": "primary_school",
        "security_answer": "育才小学",
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 验证新答案生效
    r2 = auth_client.post("/api/auth/reset-password-by-security-question", json={
        "username": "testuser",
        "security_question_key": "primary_school",
        "security_answer": "育才小学",
        "new_password": "newpassword456",
    })
    assert r2.status_code == 200


def test_set_security_question_wrong_password(auth_client):
    """当前密码错误时返回 400。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)
    headers = _auth_header(auth_client)

    r = auth_client.post("/api/auth/set-security-question", json={
        "current_password": "wrongpassword",
        "security_question_key": "primary_school",
        "security_answer": "育才小学",
    }, headers=headers)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 忘记密码 / 防枚举（保留邮箱找回）
# ---------------------------------------------------------------------------

def test_forgot_password_no_enumeration(auth_client):
    """无论账号是否存在，响应体必须相同。"""
    with patch("routers.auth.send_verification_email"), \
         patch("routers.auth.send_reset_password_email"):
        _register(auth_client)

    r_exist = auth_client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
    r_missing = auth_client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})

    assert r_exist.status_code == 200
    assert r_missing.status_code == 200
    assert r_exist.json() == r_missing.json()


def test_forgot_password_unverified_no_email(auth_client):
    """邮箱未验证时不发送重置邮件（但响应相同）。"""
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    send_calls = []
    with patch("routers.auth.send_reset_password_email", side_effect=lambda *a: send_calls.append(a)):
        auth_client.post("/api/auth/forgot-password", json={"email": "test@example.com"})

    assert len(send_calls) == 0


# ---------------------------------------------------------------------------
# 重置密码（邮件方式）→ 旧 JWT 失效
# ---------------------------------------------------------------------------

def test_reset_password_invalidates_old_jwt(auth_client):
    """reset-password 后，旧 JWT 访问 /me 应返回 401。"""
    verify_captured = {}
    reset_captured = {}

    with patch("routers.auth.send_verification_email", lambda to, t: verify_captured.update(token=t)):
        r = _register(auth_client)
    old_jwt = r.json()["access_token"]

    auth_client.post("/api/auth/verify-email", json={"token": verify_captured["token"]})

    time.sleep(1.1)

    with patch("routers.auth.send_reset_password_email", lambda to, t: reset_captured.update(token=t)):
        auth_client.post("/api/auth/forgot-password", json={"email": "test@example.com"})

    auth_client.post("/api/auth/reset-password", json={
        "token": reset_captured["token"],
        "new_password": "newpassword123",
    })

    r = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_jwt}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 修改密码 → 旧 JWT 失效
# ---------------------------------------------------------------------------

def test_change_password_invalidates_old_jwt(auth_client):
    """change-password 后，旧 JWT 访问 /me 应返回 401。"""
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client)
    old_jwt = r.json()["access_token"]

    time.sleep(1.1)

    headers = {"Authorization": f"Bearer {old_jwt}"}
    auth_client.post("/api/auth/change-password", json={
        "old_password": "password123",
        "new_password": "newpassword456",
    }, headers=headers)

    r = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_jwt}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# disabled 用户
# ---------------------------------------------------------------------------

def test_disabled_user_cannot_login(auth_client, auth_engine):
    with patch("routers.auth.send_verification_email"):
        _register(auth_client)

    with Session(auth_engine) as s:
        from sqlmodel import select
        from models import User
        u = s.exec(select(User).where(User.username == "testuser")).first()
        u.status = "disabled"
        s.add(u)
        s.commit()

    r = _login(auth_client)
    assert r.status_code == 403


def test_disabled_user_jwt_rejected(auth_client, auth_engine):
    """已签发的 JWT，用户被禁用后也应 401。"""
    with patch("routers.auth.send_verification_email"):
        r = _register(auth_client)
    token = r.json()["access_token"]

    with Session(auth_engine) as s:
        from sqlmodel import select
        from models import User
        u = s.exec(select(User).where(User.username == "testuser")).first()
        u.status = "disabled"
        s.add(u)
        s.commit()

    r = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 基础限流
# ---------------------------------------------------------------------------

def test_rate_limiter_core():
    """直接测试 rate_limit 模块：超限后抛 429。"""
    import rate_limit as rl

    rl._store.clear()

    from fastapi import HTTPException

    key = "test_rl_key_unique_xyz"
    for _ in range(3):
        rl.check_rate_limit(key, max_calls=3, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        rl.check_rate_limit(key, max_calls=3, window_seconds=60)

    assert exc_info.value.status_code == 429
