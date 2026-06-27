"""汇率接口：读取缓存 + 刷新。"""
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from auth import get_current_user
from database import get_session
from fx_provider import fetch_usdcny
from models import FxRate, User

router = APIRouter(prefix="/api/fx", tags=["fx"])

DEFAULT_PAIR = "USDCNY"
DEFAULT_RATE = 7.2
FX_REFRESH_INTERVAL_SECONDS = int(os.getenv("FX_REFRESH_INTERVAL_SECONDS", "21600"))


def _is_stale(rate: FxRate) -> bool:
    if rate.updated_at is None:
        return True
    return datetime.utcnow() - rate.updated_at > timedelta(seconds=FX_REFRESH_INTERVAL_SECONDS)


def _refresh_cached_rate(session: Session, rate: FxRate) -> FxRate:
    value = fetch_usdcny()
    if value is None:
        return rate
    rate.rate = value
    rate.updated_at = datetime.utcnow()
    session.add(rate)
    session.commit()
    session.refresh(rate)
    return rate


def get_or_create_rate(session: Session) -> FxRate:
    rate = session.get(FxRate, DEFAULT_PAIR)
    if not rate:
        rate = FxRate(pair=DEFAULT_PAIR, rate=DEFAULT_RATE, updated_at=None)
        session.add(rate)
        session.commit()
        session.refresh(rate)
    if _is_stale(rate):
        rate = _refresh_cached_rate(session, rate)
    return rate


def get_or_create_rate_without_refresh(session: Session) -> FxRate:
    rate = session.get(FxRate, DEFAULT_PAIR)
    if not rate:
        rate = FxRate(pair=DEFAULT_PAIR, rate=DEFAULT_RATE, updated_at=None)
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
    rate = get_or_create_rate_without_refresh(session)
    rate.rate = value
    rate.updated_at = datetime.utcnow()
    session.add(rate)
    session.commit()
    session.refresh(rate)
    return rate
