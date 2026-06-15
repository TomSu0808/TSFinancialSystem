"""净值快照查询：供总资产走势图（按用户隔离）。"""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Snapshot, User

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    days: int = Query(90, ge=1, le=3650, description="取最近多少天"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[dict]:
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = session.exec(
        select(Snapshot)
        .where(Snapshot.user_id == user.id, Snapshot.day >= since)
        .order_by(Snapshot.day)
    ).all()
    return [
        {"day": r.day, "total_cny": round(r.total_cny, 2), "total_usd": round(r.total_usd, 2)}
        for r in rows
        if r.day  # 跳过历史无 day 的旧记录
    ]
