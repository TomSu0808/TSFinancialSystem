"""认证接口：注册 / 登录 / 当前用户。

首个注册成功的用户会自动认领历史无主数据（user_id 为空的平台/资产/心得）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import create_access_token, get_current_user, hash_password, verify_password
from config import ALLOW_REGISTRATION
from database import get_session
from models import (
    Holding,
    Note,
    PasswordChange,
    Platform,
    Token,
    User,
    UserCreate,
    UserLogin,
    UserRead,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _claim_orphan_data(session: Session, user_id: int) -> None:
    """把历史无主数据（user_id 为空）归到指定用户。仅首个用户会触发。"""
    for model in (Platform, Holding, Note):
        rows = session.exec(select(model).where(model.user_id.is_(None))).all()
        for row in rows:
            row.user_id = user_id
            session.add(row)
    session.commit()


@router.post("/register", response_model=Token)
def register(data: UserCreate, session: Session = Depends(get_session)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "当前未开放注册")
    username = data.username.strip()
    if not username or not data.password:
        raise HTTPException(400, "用户名和密码不能为空")
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(409, "用户名已被注册")

    is_first = session.exec(select(User)).first() is None
    user = User(
        username=username,
        email=(data.email or None),
        password_hash=hash_password(data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    if is_first:
        _claim_orphan_data(session, user.id)

    return Token(access_token=create_access_token(user.id), user=UserRead.model_validate(user, from_attributes=True))


@router.post("/login", response_model=Token)
def login(data: UserLogin, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == data.username.strip())).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return Token(access_token=create_access_token(user.id), user=UserRead.model_validate(user, from_attributes=True))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(
    data: PasswordChange,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "原密码不正确")
    if not data.new_password:
        raise HTTPException(400, "新密码不能为空")
    user.password_hash = hash_password(data.new_password)
    session.add(user)
    session.commit()
    return {"ok": True}
