"""测试夹具：每个测试用独立内存 SQLite，TestClient 覆盖鉴权为固定测试用户。"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import models  # noqa: F401  确保模型注册到 metadata


@pytest.fixture(autouse=True)
def _no_real_web_search(monkeypatch):
    """任何测试都不发起真实检索请求（Search API 会产生真实费用）。

    在 HTTP 层拦截：run_search 的逻辑仍可被测试，但不会真的出网。
    """
    import requests

    import web_search

    def blocked_post(*args, **kwargs):
        raise requests.RequestException("测试环境禁止真实网络请求")

    monkeypatch.setattr(web_search.requests, "post", blocked_post)


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="user")
def user_fixture(session):
    from models import User
    u = User(username="tester", password_hash="x")
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture(name="client")
def client_fixture(engine, user):
    from main import app
    from database import get_session
    from auth import get_current_user

    def get_session_override():
        with Session(engine) as session:
            yield session

    def get_current_user_override():
        with Session(engine) as session:
            from models import User
            return session.get(User, user.id)

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_current_user_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
