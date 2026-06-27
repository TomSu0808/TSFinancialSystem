"""邮件发送服务。

EMAIL_ENABLED=false（默认）时，将链接打印到控制台，方便本地开发测试。
EMAIL_ENABLED=true 时，通过 SMTP 真实发送。

SMTP 端口说明：
  - 587 + SMTP_TLS=false → STARTTLS（推荐，Gmail/163/QQ 默认）
  - 465 + SMTP_TLS=true  → SMTP_SSL（隐式 TLS）
"""
import logging
import smtplib
from email.message import EmailMessage

from config import (
    APP_BASE_URL,
    EMAIL_ENABLED,
    EMAIL_FROM,
    ENV,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TLS,
    SMTP_USERNAME,
)

logger = logging.getLogger(__name__)


def _check_smtp_config() -> None:
    """EMAIL_ENABLED=true 时检查 SMTP 配置是否完整，不完整则抛出明确错误。"""
    missing = [v for v, val in [
        ("SMTP_HOST", SMTP_HOST),
        ("SMTP_USERNAME", SMTP_USERNAME),
        ("SMTP_PASSWORD", SMTP_PASSWORD),
        ("EMAIL_FROM", EMAIL_FROM),
    ] if not val or val == "noreply@example.com" and v == "EMAIL_FROM" and not EMAIL_FROM]
    # 只要 SMTP_HOST / USERNAME / PASSWORD 有空就报错
    actually_missing = [v for v, val in [
        ("SMTP_HOST", SMTP_HOST),
        ("SMTP_USERNAME", SMTP_USERNAME),
        ("SMTP_PASSWORD", SMTP_PASSWORD),
    ] if not val]
    if actually_missing:
        raise ValueError(
            f"EMAIL_ENABLED=true 但 SMTP 配置不完整，缺少: {', '.join(actually_missing)}。"
            "请在 .env 中配置 SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD，"
            "或设置 EMAIL_ENABLED=false 使用控制台调试模式。"
        )


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if SMTP_TLS:
        # 隐式 TLS（SMTP_SSL），适用于端口 465
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            s.send_message(msg)
    else:
        # STARTTLS，适用于端口 587（更常见）
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            s.send_message(msg)


def _deliver(to: str, subject: str, body: str) -> None:
    if not EMAIL_ENABLED:
        if ENV != "production":
            print(f"\n{'='*60}")
            print(f"[DEV EMAIL] To: {to}")
            print(f"Subject: {subject}")
            print(body)
            print(f"{'='*60}\n", flush=True)
        else:
            logger.warning("EMAIL_ENABLED=false but ENV=production, email not sent to %s", to)
        return

    _check_smtp_config()
    try:
        _send_smtp(to, subject, body)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.exception("Failed to send email to %s: %s", to, exc)
        raise


def should_expose_dev_email_links() -> bool:
    return not EMAIL_ENABLED and ENV != "production"


def send_verification_email(to: str, token: str) -> str:
    url = f"{APP_BASE_URL}/verify-email?token={token}"
    subject = "请验证你的邮箱 - 资产管理平台"
    body = (
        f"你好，\n\n"
        f"请点击以下链接验证邮箱（24 小时内有效）：\n\n"
        f"{url}\n\n"
        f"如非本人操作，请忽略此邮件。\n"
    )
    _deliver(to, subject, body)
    return url


def send_reset_password_email(to: str, token: str) -> str:
    url = f"{APP_BASE_URL}/reset-password?token={token}"
    subject = "重置密码 - 资产管理平台"
    body = (
        f"你好，\n\n"
        f"请点击以下链接重置密码（30 分钟内有效）：\n\n"
        f"{url}\n\n"
        f"如非本人操作，请立即忽略此邮件，你的账号仍然安全。\n"
    )
    _deliver(to, subject, body)
    return url
