"""集中配置：全部从环境变量 / .env 读取，密钥绝不写进代码。

本地开发：复制 .env.example 为 .env 并按需修改。
上云：在服务器/容器里设置同名环境变量即可（无需 .env 文件）。
"""
import base64
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv

# 加载 backend/.env（存在才加载；上云用真实环境变量时可不放此文件）
load_dotenv(Path(__file__).resolve().parent / ".env")

ENV = os.getenv("ENV", "development")  # "production" | "development"
IS_PROD = ENV == "production"

# JWT 签名密钥。生产环境必须通过环境变量显式设置；
# 开发环境缺省时随机生成（进程重启会让已签发的 token 失效）。
SECRET_KEY = os.getenv("SECRET_KEY") or (
    None if IS_PROD else secrets.token_urlsafe(32)
)

# API Key 加密密钥（Fernet 格式）。
# 生成命令：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 生产环境必须显式设置；开发环境未配置时使用固定 dev 密钥（仅用于本地开发，不安全）。
_DEV_FERNET_KEY = base64.urlsafe_b64encode(b"dev-only-key-not-for-production!").decode()
APP_ENCRYPTION_KEY: str = os.getenv("APP_ENCRYPTION_KEY", "")
if not APP_ENCRYPTION_KEY and not IS_PROD:
    APP_ENCRYPTION_KEY = _DEV_FERNET_KEY
    print(
        "[WARN] APP_ENCRYPTION_KEY 未设置，使用开发默认密钥（不安全，仅限本地开发）。\n"
        "       生成正式密钥：python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\"",
        file=sys.stderr,
    )

# 是否允许在用户未配置自己的 API Key 时回退到系统全局 Key。
# false（默认）：用户没有 Key 时直接提示去配置，不使用系统 Key。
# true：用户没有 Key 时可以使用环境变量里的全局 AI Key（站长模式）。
ALLOW_SYSTEM_AI_FALLBACK: bool = os.getenv("ALLOW_SYSTEM_AI_FALLBACK", "false").lower() == "true"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", "7"))

CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]

ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() != "false"

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173")

# 邮件发送配置
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@example.com")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_TLS = os.getenv("SMTP_TLS", "false").lower() == "true"


def check_production_config() -> None:
    """生产环境启动时校验必要配置，缺失则立即退出。"""
    if not IS_PROD:
        return

    errors = []

    if not os.getenv("SECRET_KEY"):
        errors.append("SECRET_KEY 未设置（生产环境禁止随机生成）")

    if not os.getenv("APP_BASE_URL"):
        errors.append("APP_BASE_URL 未设置")

    if not os.getenv("APP_ENCRYPTION_KEY"):
        errors.append(
            "APP_ENCRYPTION_KEY 未设置（生产环境必须配置）。\n"
            "  生成命令：python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )

    if EMAIL_ENABLED:
        for var in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM"):
            if not os.getenv(var):
                errors.append(f"{var} 未设置（EMAIL_ENABLED=true 时必须配置）")

    if CORS_ORIGINS == ["*"]:
        # 警告，不强制退出
        print("[WARN] CORS_ORIGINS=* 在生产环境中不安全，建议收紧为具体域名", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"[FATAL] 生产配置缺失: {e}", file=sys.stderr)
        sys.exit(1)
