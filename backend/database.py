"""数据库连接与初始化。

默认单文件 SQLite（data.db），地址可由环境变量覆盖：
  - DATABASE_URL：直接指定完整连接串（如上云切到 PostgreSQL）。
  - DATA_DIR：只改 SQLite 文件所在目录（上云时指向挂载的持久卷，
    数据就不会随容器重建而丢失）。
两者都不设时，落在 backend/ 目录下，本地开发行为不变。
"""
import os
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    data_dir = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent)
    data_dir.mkdir(parents=True, exist_ok=True)
    DB_PATH = data_dir / "data.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# check_same_thread=False 允许 FastAPI 多线程访问同一 SQLite 连接（仅 SQLite 需要）
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)


def _migrate_add_user_id() -> None:
    """给历史已存在的表补 user_id 列（SQLite 的 create_all 不会改已有表）。

    幂等：列已存在则跳过。新增的列允许为空，存量数据 user_id 为 NULL，
    由「首个注册用户」在注册时认领。
    """
    # 表名 -> 需要补的列（列名: SQL 类型）
    wanted = {
        "user": {
            "email_normalized": "VARCHAR",
            "email_verified": "INTEGER DEFAULT 0",
            "email_verified_at": "DATETIME",
            "password_changed_at": "DATETIME",
            "last_login_at": "DATETIME",
            "status": "VARCHAR DEFAULT 'active'",
            "security_question_key": "VARCHAR",
            "security_answer_hash": "VARCHAR",
            "security_question_updated_at": "DATETIME",
        },
        "platform": {"user_id": "INTEGER"},
        "holding": {
            "user_id": "INTEGER",
            "source": "VARCHAR DEFAULT 'manual'",
            "status": "VARCHAR DEFAULT 'open'",
            "realized_pnl": "FLOAT DEFAULT 0",
            "realized_income": "FLOAT DEFAULT 0",
        },
        "note": {"user_id": "INTEGER"},
        "snapshot": {"user_id": "INTEGER", "day": "VARCHAR"},
        "transaction": {"holding_id": "INTEGER"},
        "researchreport": {
            "user_id": "INTEGER",
            "template_key": "VARCHAR DEFAULT ''",
            "title": "VARCHAR DEFAULT ''",
            "target_name": "VARCHAR DEFAULT ''",
            "symbol": "VARCHAR",
            "market": "VARCHAR",
            "report_language": "VARCHAR DEFAULT 'zh'",
            "related_holding_id": "INTEGER",
            "status": "VARCHAR DEFAULT 'draft'",
            "input_context_md": "TEXT",
            "skill_md": "TEXT",
            "prompt_md": "TEXT",
            "report_md": "TEXT",
            "sources_json": "TEXT",
            "error_message": "TEXT",
            "provider": "VARCHAR",
            "model": "VARCHAR",
            "provider_response_id": "VARCHAR",
            "started_at": "DATETIME",
            "completed_at": "DATETIME",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
    }
    with engine.connect() as conn:
        for table, columns in wanted.items():
            existing = {
                row[1]  # PRAGMA table_info 第 2 列是列名
                for row in conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
            }
            if not existing:
                continue  # 表还不存在（首次启动由 create_all 负责）
            for col, col_type in columns.items():
                if col not in existing:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {col} {col_type}'))
        conn.commit()


def init_db() -> None:
    """建表（已存在则跳过）+ 轻量迁移。在应用启动时调用。"""
    # 确保模型已被导入并注册到 SQLModel.metadata
    import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    if IS_SQLITE:  # PRAGMA / ALTER 写法是 SQLite 专属
        _migrate_add_user_id()


def get_session():
    """FastAPI 依赖：每个请求一个 Session。"""
    with Session(engine) as session:
        yield session
