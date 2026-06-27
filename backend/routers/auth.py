"""认证接口：注册 / 登录 / 邮箱验证 / 忘记密码 / 重置密码 / 更改邮箱 / 安全问题。

首个注册成功的用户会自动认领历史无主数据（user_id 为空的平台/资产/心得）。
"""
import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    hash_security_answer,
    hash_token,
    make_auth_token,
    verify_password,
    verify_security_answer,
)
from config import ALLOW_REGISTRATION
from database import get_session
from email_service import (
    send_reset_password_email,
    send_verification_email,
    should_expose_dev_email_links,
)
from models import (
    AuthToken,
    ChangeEmailInput,
    ForgotPassword,
    Holding,
    Note,
    PasswordChange,
    Platform,
    RecoveryQuestionInput,
    ResetBySecurityQuestionInput,
    ResetPassword,
    SECURITY_QUESTIONS,
    SetSecurityQuestionInput,
    Token,
    User,
    UserCreate,
    UserLogin,
    UserRead,
    VerifyEmailInput,
    _EMAIL_RE,
    _USERNAME_RE,
)
from rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_VERIFICATION_TTL = timedelta(hours=24)
_RESET_TTL = timedelta(minutes=30)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _claim_orphan_data(session: Session, user_id: int) -> None:
    """把历史无主数据（user_id 为空）归到指定用户。仅首个用户会触发。"""
    for model in (Platform, Holding, Note):
        rows = session.exec(select(model).where(model.user_id.is_(None))).all()
        for row in rows:
            row.user_id = user_id
            session.add(row)
    session.commit()


def _issue_verification_token(session: Session, user: User, ip: str | None = None) -> str:
    plain, h = make_auth_token()
    token = AuthToken(
        user_id=user.id,
        token_hash=h,
        purpose="email_verification",
        expires_at=datetime.utcnow() + _VERIFICATION_TTL,
        created_ip=ip,
    )
    session.add(token)
    session.commit()
    return plain


def _user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        email_verified=user.email_verified,
        status=user.status,
        has_email=bool(user.email),
        has_security_question=bool(user.security_question_key and user.security_answer_hash),
        security_question_key=user.security_question_key,
        security_question_text=SECURITY_QUESTIONS.get(user.security_question_key) if user.security_question_key else None,
    )


def _dev_url(value) -> str | None:
    if should_expose_dev_email_links() and isinstance(value, str):
        return value
    return None


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

@router.post("/register", response_model=Token)
def register(data: UserCreate, request: Request, session: Session = Depends(get_session)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "当前未开放注册")

    ip = request.client.host if request.client else None
    check_rate_limit(f"register:{ip}", max_calls=10, window_seconds=3600)

    username = data.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(400, "用户名只能包含字母、数字、下划线和短横线，长度 3-32")

    if len(data.password) < 8:
        raise HTTPException(400, "密码至少 8 位")

    # 安全问题校验
    sq_key = data.security_question_key.strip()
    if sq_key not in SECURITY_QUESTIONS:
        raise HTTPException(400, "安全问题不合法，请选择预设问题")
    sq_answer = data.security_answer.strip()
    if not sq_answer or len(sq_answer) > 100:
        raise HTTPException(400, "安全问题答案长度需在 1-100 字符之间")

    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(409, "用户名已被注册")

    # 邮箱可选处理
    email_raw = None
    email_normalized = None
    if data.email:
        email_raw = data.email.strip()
        if not _EMAIL_RE.match(email_raw):
            raise HTTPException(400, "邮箱格式不正确")
        email_normalized = email_raw.lower()
        if session.exec(select(User).where(User.email_normalized == email_normalized)).first():
            raise HTTPException(409, "该邮箱已被注册")

    is_first = session.exec(select(User)).first() is None
    user = User(
        username=username,
        email=email_raw,
        email_normalized=email_normalized,
        email_verified=False,
        password_hash=hash_password(data.password),
        security_question_key=sq_key,
        security_answer_hash=hash_security_answer(sq_answer),
        security_question_updated_at=datetime.utcnow(),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    if is_first:
        _claim_orphan_data(session, user.id)

    # 只有填写了邮箱才发送验证邮件
    dev_verification_url = None
    if email_raw:
        try:
            plain_token = _issue_verification_token(session, user, ip)
            verification_url = send_verification_email(user.email, plain_token)
            dev_verification_url = _dev_url(verification_url)
        except Exception as exc:
            logger.warning("注册后发送验证邮件失败 user_id=%s email=%s: %s", user.id, user.email, exc)

    return Token(
        access_token=create_access_token(user.id),
        user=_user_read(user),
        dev_verification_url=dev_verification_url,
    )


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------

@router.post("/login", response_model=Token)
def login(data: UserLogin, request: Request, session: Session = Depends(get_session)):
    ip = request.client.host if request.client else None
    username = data.username.strip()
    check_rate_limit(f"login:{ip}:{username}", max_calls=10, window_seconds=300)

    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if user.status != "active":
        raise HTTPException(403, "账号已被禁用")

    user.last_login_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    return Token(access_token=create_access_token(user.id), user=_user_read(user))


# ---------------------------------------------------------------------------
# 当前用户
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return _user_read(user)


# ---------------------------------------------------------------------------
# 修改密码（需登录）
# ---------------------------------------------------------------------------

@router.post("/change-password")
def change_password(
    data: PasswordChange,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "原密码不正确")
    if len(data.new_password) < 8:
        raise HTTPException(400, "新密码至少 8 位")
    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = datetime.utcnow()
    session.add(user)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 更改邮箱（需登录）
# ---------------------------------------------------------------------------

@router.post("/change-email")
def change_email(
    data: ChangeEmailInput,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    email_raw = data.new_email.strip()
    if not _EMAIL_RE.match(email_raw):
        raise HTTPException(400, "邮箱格式不正确")
    email_normalized = email_raw.lower()

    if email_normalized == (user.email_normalized or ""):
        raise HTTPException(400, "新邮箱与当前邮箱相同")

    conflict = session.exec(
        select(User).where(User.email_normalized == email_normalized)
    ).first()
    if conflict and conflict.id != user.id:
        raise HTTPException(409, "该邮箱已被其他账号使用")

    user.email = email_raw
    user.email_normalized = email_normalized
    user.email_verified = False
    user.email_verified_at = None
    session.add(user)
    session.commit()
    session.refresh(user)

    ip = request.client.host if request.client else None
    dev_verification_url = None
    try:
        plain_token = _issue_verification_token(session, user, ip)
        verification_url = send_verification_email(user.email, plain_token)
        dev_verification_url = _dev_url(verification_url)
    except Exception as exc:
        logger.error("更改邮箱后发送验证邮件失败 user_id=%s email=%s: %s", user.id, user.email, exc)
        raise HTTPException(500, f"邮箱已更新，但验证邮件发送失败：{exc}")

    return {
        "user": _user_read(user),
        "dev_verification_url": dev_verification_url,
    }


# ---------------------------------------------------------------------------
# 设置/修改安全问题（需登录）
# ---------------------------------------------------------------------------

@router.post("/set-security-question")
def set_security_question(
    data: SetSecurityQuestionInput,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")

    sq_key = data.security_question_key.strip()
    if sq_key not in SECURITY_QUESTIONS:
        raise HTTPException(400, "安全问题不合法，请选择预设问题")

    sq_answer = data.security_answer.strip()
    if not sq_answer or len(sq_answer) > 100:
        raise HTTPException(400, "安全问题答案长度需在 1-100 字符之间")

    user.security_question_key = sq_key
    user.security_answer_hash = hash_security_answer(sq_answer)
    user.security_question_updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 重新发送验证邮件（需登录）
# ---------------------------------------------------------------------------

@router.post("/resend-verification")
def resend_verification(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if user.email_verified:
        return {"ok": True, "message": "邮箱已验证"}
    if not user.email:
        raise HTTPException(400, "账号未绑定邮箱，请先在个人资料中设置邮箱")

    ip = request.client.host if request.client else None
    check_rate_limit(f"resend:{user.id}", max_calls=3, window_seconds=3600)

    dev_verification_url = None
    try:
        plain_token = _issue_verification_token(session, user, ip)
        verification_url = send_verification_email(user.email, plain_token)
        dev_verification_url = _dev_url(verification_url)
    except Exception as exc:
        logger.error("重发验证邮件失败 user_id=%s: %s", user.id, exc)
        raise HTTPException(500, f"验证邮件发送失败：{exc}")

    return {
        "ok": True,
        "message": "验证邮件已发送",
        "dev_verification_url": dev_verification_url,
    }


# ---------------------------------------------------------------------------
# 验证邮箱
# ---------------------------------------------------------------------------

@router.post("/verify-email")
def verify_email(data: VerifyEmailInput, session: Session = Depends(get_session)):
    token_hash = hash_token(data.token)
    row = session.exec(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == "email_verification",
        )
    ).first()

    if not row or row.used_at is not None or row.expires_at < datetime.utcnow():
        raise HTTPException(400, "验证链接无效或已过期")

    user = session.get(User, row.user_id)
    if not user:
        raise HTTPException(400, "用户不存在")

    user.email_verified = True
    user.email_verified_at = datetime.utcnow()
    row.used_at = datetime.utcnow()
    session.add(user)
    session.add(row)
    session.commit()
    return {"ok": True, "message": "邮箱验证成功"}


# ---------------------------------------------------------------------------
# 固定安全问题列表（公开）
# ---------------------------------------------------------------------------

@router.get("/security-questions")
def list_security_questions():
    return [{"key": k, "text": v} for k, v in SECURITY_QUESTIONS.items()]


# ---------------------------------------------------------------------------
# 查询用户的安全问题（安全问题找回密码：Step 1）
# ---------------------------------------------------------------------------

@router.post("/recovery-question")
def recovery_question(
    data: RecoveryQuestionInput,
    request: Request,
    session: Session = Depends(get_session),
):
    ip = request.client.host if request.client else None
    check_rate_limit(f"recovery:{ip}", max_calls=10, window_seconds=3600)

    username = data.username.strip()
    user = session.exec(select(User).where(User.username == username)).first()

    if (
        not user
        or not user.security_question_key
        or not user.security_answer_hash
        or user.status != "active"
    ):
        return {"ok": False, "message": "无法使用安全问题找回该账号"}

    return {
        "ok": True,
        "question_key": user.security_question_key,
        "question_text": SECURITY_QUESTIONS.get(user.security_question_key, ""),
    }


# ---------------------------------------------------------------------------
# 通过安全问题重置密码（安全问题找回密码：Step 2）
# ---------------------------------------------------------------------------

@router.post("/reset-password-by-security-question")
def reset_password_by_security_question(
    data: ResetBySecurityQuestionInput,
    request: Request,
    session: Session = Depends(get_session),
):
    ip = request.client.host if request.client else None
    check_rate_limit(f"reset_sq:{ip}:{data.username}", max_calls=5, window_seconds=3600)

    _FAIL = HTTPException(400, "安全问题答案错误或请求无效")

    if len(data.new_password) < 8:
        raise HTTPException(400, "新密码至少 8 位")

    username = data.username.strip()
    user = session.exec(select(User).where(User.username == username)).first()

    if not user or user.status != "active":
        raise _FAIL
    if not user.security_question_key or not user.security_answer_hash:
        raise _FAIL
    if user.security_question_key != data.security_question_key:
        raise _FAIL
    if not verify_security_answer(data.security_answer, user.security_answer_hash):
        raise _FAIL

    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = datetime.utcnow()
    session.add(user)
    session.commit()
    return {"ok": True, "message": "密码已重置，请重新登录"}


# ---------------------------------------------------------------------------
# 忘记密码（防枚举：无论账号是否存在都返回同样响应）
# ---------------------------------------------------------------------------

@router.post("/forgot-password")
def forgot_password(
    data: ForgotPassword, request: Request, session: Session = Depends(get_session)
):
    ip = request.client.host if request.client else None
    check_rate_limit(f"forgot:{ip}", max_calls=5, window_seconds=3600)

    _UNIFORM_RESPONSE = {
        "ok": True,
        "message": "如果该邮箱已注册并完成验证，我们会发送重置密码邮件，请查收",
    }

    email_normalized = data.email.strip().lower()
    user = session.exec(
        select(User).where(User.email_normalized == email_normalized)
    ).first()

    if not user or not user.email_verified or user.status != "active":
        return _UNIFORM_RESPONSE

    plain, h = make_auth_token()
    token = AuthToken(
        user_id=user.id,
        token_hash=h,
        purpose="password_reset",
        expires_at=datetime.utcnow() + _RESET_TTL,
        created_ip=ip,
    )
    session.add(token)
    session.commit()

    try:
        reset_url = send_reset_password_email(user.email, plain)
        if _dev_url(reset_url):
            return {**_UNIFORM_RESPONSE, "dev_reset_url": reset_url}
    except Exception as exc:
        logger.error("发送重置密码邮件失败 user_id=%s: %s", user.id, exc)

    return _UNIFORM_RESPONSE


# ---------------------------------------------------------------------------
# 重置密码（邮箱 token 方式）
# ---------------------------------------------------------------------------

@router.post("/reset-password")
def reset_password(data: ResetPassword, session: Session = Depends(get_session)):
    if len(data.new_password) < 8:
        raise HTTPException(400, "新密码至少 8 位")

    token_hash = hash_token(data.token)
    row = session.exec(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.purpose == "password_reset",
        )
    ).first()

    if not row or row.used_at is not None or row.expires_at < datetime.utcnow():
        raise HTTPException(400, "重置链接无效或已过期")

    user = session.get(User, row.user_id)
    if not user:
        raise HTTPException(400, "用户不存在")

    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = datetime.utcnow()
    row.used_at = datetime.utcnow()
    session.add(user)
    session.add(row)
    session.commit()
    return {"ok": True, "message": "密码已重置，请重新登录"}
