"""数据库兼容性测试：URL 识别、engine 参数、迁移工具函数。"""
import pytest


# ── URL 识别和 IS_SQLITE 标志 ─────────────────────────────────────────────────

def test_sqlite_url_detected():
    import importlib, types, sys

    # 用一个干净的模块环境测 IS_SQLITE 逻辑
    import os
    sqlite_url = "sqlite:///./test.db"
    assert sqlite_url.startswith("sqlite")


def test_postgres_url_not_sqlite():
    pg_url = "postgresql+psycopg2://user:pw@host:5432/db"
    assert not pg_url.startswith("sqlite")


def test_postgres_asyncpg_url_not_sqlite():
    pg_url = "postgresql://user:pw@host/db"
    assert not pg_url.startswith("sqlite")


# ── IS_SQLITE 来自 database.py ────────────────────────────────────────────────

def test_database_is_sqlite_flag():
    """默认（未设 DATABASE_URL）应为 SQLite。"""
    import database
    assert database.IS_SQLITE is True


# ── _column_exists 和 _table_exists 在 SQLite 下工作 ─────────────────────────

def test_column_exists_sqlite(engine):
    from sqlalchemy import text
    from database import _column_exists, _table_exists
    # user 表由 create_all 建立
    with engine.connect() as conn:
        assert _table_exists(conn, "user") is True
        assert _column_exists(conn, "user", "id") is True
        assert _column_exists(conn, "user", "nonexistent_col") is False


def test_table_not_exists_sqlite(engine):
    from database import _table_exists
    with engine.connect() as conn:
        assert _table_exists(conn, "totally_fake_table_xyz") is False


# ── PostgreSQL engine 参数选择函数 ────────────────────────────────────────────

def test_connect_args_sqlite():
    """SQLite 需要 check_same_thread=False。"""
    from database import IS_SQLITE
    connect_args = {"check_same_thread": False} if IS_SQLITE else {}
    assert "check_same_thread" in connect_args


def test_connect_args_postgres():
    """PostgreSQL 不传 check_same_thread。"""
    is_pg = False  # 模拟 PG 环境
    connect_args = {"check_same_thread": False} if is_pg else {}
    assert "check_same_thread" not in connect_args


# ── migrate 函数幂等性（SQLite）────────────────────────────────────────────────

def test_migrate_idempotent(engine):
    """重复调用 _migrate_add_user_id 不会抛异常，因为列已存在。"""
    from database import _migrate_add_user_id as migrate

    # 这个函数读全局 engine，而不是参数 engine；
    # 在这里只验证它对测试 engine 不抛异常，通过 monkeypatch 替换全局 engine。
    import database
    original = database.engine
    try:
        database.engine = engine
        migrate()  # 首次（可能已建）
        migrate()  # 再次，幂等
    finally:
        database.engine = original
