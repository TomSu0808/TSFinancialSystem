"""平台增删改查（按登录用户隔离）。"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Holding, Platform, PlatformCreate, PlatformUpdate, User

router = APIRouter(prefix="/api/platforms", tags=["platforms"])


def _owned(session: Session, platform_id: int, user: User) -> Platform:
    """取出属于当前用户的平台，否则 404（不泄露他人数据是否存在）。"""
    platform = session.get(Platform, platform_id)
    if not platform or platform.user_id != user.id:
        raise HTTPException(404, "平台不存在")
    return platform


@router.get("", response_model=List[Platform])
def list_platforms(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return session.exec(select(Platform).where(Platform.user_id == user.id)).all()


@router.post("", response_model=Platform)
def create_platform(
    data: PlatformCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    platform = Platform.model_validate(data, update={"user_id": user.id})
    session.add(platform)
    session.commit()
    session.refresh(platform)
    return platform


@router.put("/{platform_id}", response_model=Platform)
def update_platform(
    platform_id: int,
    data: PlatformUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    platform = _owned(session, platform_id, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(platform, key, value)
    session.add(platform)
    session.commit()
    session.refresh(platform)
    return platform


@router.delete("/{platform_id}")
def delete_platform(
    platform_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    platform = _owned(session, platform_id, user)
    # 连带删除该平台下的持仓，避免孤儿数据
    holdings = session.exec(
        select(Holding).where(Holding.platform_id == platform_id)
    ).all()
    for h in holdings:
        session.delete(h)
    session.delete(platform)
    session.commit()
    return {"ok": True, "deleted_holdings": len(holdings)}
