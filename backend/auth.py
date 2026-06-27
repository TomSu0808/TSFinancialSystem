"""认证核心：密码哈希（bcrypt）、JWT 签发/校验、当前用户依赖。"""
import hashlib
import re as _re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlmodel import Session

from config import ACCESS_TOKEN_EXPIRE_DAYS, ALGORITHM, SECRET_KEY
from database import get_session
from models import User

# bcrypt 单次最长 72 字节，超出部分会被忽略 → 显式截断，避免长密码行为不一致
_BCRYPT_MAX = 72

bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pw = plain.encode("utf-8")[:_BCRYPT_MAX]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.utcnow()
    expire = now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire, "iat": now}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def make_auth_token() -> Tuple[str, str]:
    """生成随机 token。返回 (明文, sha256_hex)。明文发给用户，hash 存库。"""
    plain = secrets.token_urlsafe(32)
    h = hashlib.sha256(plain.encode()).hexdigest()
    return plain, h


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def normalize_security_answer(answer: str) -> str:
    """去除首尾空白、转小写、移除所有空白字符。"""
    return _re.sub(r'\s+', '', answer.strip().lower())


def hash_security_answer(plain: str) -> str:
    normalized = normalize_security_answer(plain)
    pw = normalized.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_security_answer(plain: str, hashed: str) -> bool:
    try:
        normalized = normalize_security_answer(plain)
        pw = normalized.encode("utf-8")[:_BCRYPT_MAX]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    """从 Authorization: Bearer <token> 解析出当前登录用户，失败一律 401。"""
    unauth = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauth
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise unauth

    user = session.get(User, user_id)
    if user is None:
        raise unauth

    if user.status != "active":
        raise unauth

    # 密码修改后，旧 token 立即失效
    iat_ts = payload.get("iat")
    if iat_ts is not None and user.password_changed_at is not None:
        token_issued_at = datetime.utcfromtimestamp(iat_ts)
        if token_issued_at < user.password_changed_at:
            raise unauth

    return user
