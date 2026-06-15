"""汇率接口：读取缓存 + 刷新。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from auth import get_current_user
from database import get_session
from fx_provider import fetch_usdcny
from models import FxRate, User

router = APIRouter(prefix="/api/fx", tags=["fx"])

DEFAULT_PAIR = "USDCNY"


def get_or_create_rate(session: Session) -> FxRate:
    rate = session.get(FxRate, DEFAULT_PAIR)
    if not rate:
        rate = FxRate(pair=DEFAULT_PAIR, rate=7.2, updated_at=None)
        session.add(rate)
        session.commit()
        session.refresh(rate)
    return rate


@router.get("/rate", response_model=FxRate)
def get_rate(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return get_or_create_rate(session)


@router.post("/refresh", response_model=FxRate)
def refresh_rate(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    value = fetch_usdcny()
    if value is None:
        raise HTTPException(502, "汇率获取失败，请稍后重试")
    rate = get_or_create_rate(session)
    rate.rate = value
    rate.updated_at = datetime.utcnow()
    session.add(rate)
    session.commit()
    session.refresh(rate)
    return rate
