"""测试夹具：每个测试用独立内存 SQLite，TestClient 覆盖鉴权为固定测试用户。"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import models  # noqa: F401  确保模型注册到 metadata


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
