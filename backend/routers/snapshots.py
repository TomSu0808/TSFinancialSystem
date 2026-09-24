"""净值快照查询：供总资产走势图（按用户隔离）。"""
import calendar
import json
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Snapshot, User, DailyPnl, Currency

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

RANGE_KEYS = ("max", "1y", "6m", "3m", "1m", "1w")
_RANGE_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12}


def _back_months(today: date, months: int) -> date:
    m = today.month - 1 - months
    y = today.year + m // 12
    mm = m % 12 + 1
    last = calendar.monthrange(y, mm)[1]
    return date(y, mm, min(today.day, last))


def _range_start(range_key: str, today: date) -> Optional[str]:
    """返回区间起始日（含）；max 返回 None 表示无下限（最早有效快照）。"""
    if range_key == "max":
        return None
    if range_key == "1w":
        return (today - timedelta(days=6)).isoformat()
    return _back_months(today, _RANGE_MONTHS[range_key]).isoformat()


@router.get("")
def list_snapshots(
    days: int = Query(90, ge=1, le=3650, description="取最近多少天（旧参数，保留兼容）"),
    range_key: Optional[str] = Query(None, alias="range", description="时间范围：max/1y/6m/3m/1m/1w"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[dict]:
    today = datetime.utcnow().date()
    stmt = select(Snapshot).where(Snapshot.user_id == user.id, Snapshot.day <= today.isoformat())
    if range_key is not None:
        if range_key not in RANGE_KEYS:
            raise HTTPException(400, f"非法 range：{range_key}，可选 {', '.join(RANGE_KEYS)}")
        since = _range_start(range_key, today)
        if since is not None:
            stmt = stmt.where(Snapshot.day >= since)
    else:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        stmt = stmt.where(Snapshot.day >= since)
    rows = session.exec(stmt.order_by(Snapshot.day)).all()
    return [
        {"day": r.day, "total_cny": round(r.total_cny, 2), "total_usd": round(r.total_usd, 2)}
        for r in rows
        if _valid_day(r.day)
    ]


def _valid_day(value):
    try:
        return bool(value) and date.fromisoformat(value).isoformat() == value
    except (ValueError, TypeError):
        return False


@router.get("/daily-pnl")
def daily_pnl(
    days: int = Query(90, ge=1, le=3650),
    currency: Currency = Query(Currency.CNY),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    today = datetime.utcnow().date()
    since = (today - timedelta(days=days - 1)).isoformat()
    rows = session.exec(select(DailyPnl).where(
        DailyPnl.user_id == user.id, DailyPnl.day >= since, DailyPnl.day <= today.isoformat(),
    ).order_by(DailyPnl.day.desc())).all()
    return {
        "timezone": "UTC", "currency": currency.value,
        "method": "按 UTC 日记录累计持仓收益变化，含已实现盈亏与分红，排除入出金和汇兑变动。今日为截至最近更新的暂计值；跨市场未必对应同一交易日。",
        "items": [{"day": r.day, "pnl": r.pnl_cny if currency == Currency.CNY else (
            r.pnl_usd if currency == Currency.USD else (round(r.pnl_usd * 7.8, 2) if r.pnl_usd is not None else None)),
            "status": r.status, "note": r.note, "updated_at": r.updated_at.isoformat() + "Z",
            "provisional": r.day == today.isoformat()} for r in rows if _valid_day(r.day)],
    }


def _pick_pnl(cny, usd, currency: Currency):
    """按展示币种取当日记录时的历史金额，不用最新汇率重算。"""
    if currency == Currency.CNY:
        return cny
    if currency == Currency.USD:
        return usd
    return round(usd * 7.8, 2) if usd is not None else None


@router.get("/daily-pnl/{day}")
def daily_pnl_detail(
    day: str,
    currency: Currency = Query(Currency.CNY),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """按日查看逐仓位盈亏明细（只返回当前用户该日记录，避免一次加载全年明细）。"""
    if not _valid_day(day):
        raise HTTPException(400, "非法日期格式，应为 YYYY-MM-DD")
    r = session.exec(select(DailyPnl).where(
        DailyPnl.user_id == user.id, DailyPnl.day == day,
    )).first()
    if r is None:
        raise HTTPException(404, "该日期无每日盈亏记录")

    details = json.loads(r.details_json or "[]")
    has_details = bool(details)
    positions = []
    excluded_count = 0
    details_total = 0.0
    for d in details:
        pnl = _pick_pnl(d.get("pnl_cny"), d.get("pnl_usd"), currency)
        if pnl is not None:
            details_total += pnl
        if d.get("excluded"):
            excluded_count += 1
        positions.append({
            "holding_id": d.get("holding_id"),
            "position_key": d.get("position_key"),
            "platform": d.get("platform"),
            "symbol": d.get("symbol"),
            "name": d.get("name"),
            "asset_type": d.get("asset_type"),
            "currency": d.get("currency"),
            "pnl": pnl,
            "pnl_native": d.get("pnl_native"),
            "status": d.get("status"),
            "excluded": d.get("excluded", False),
            "reason": d.get("reason"),
            "fx_rate": d.get("fx_rate"),
            "fx_time": d.get("fx_time"),
        })
    # 按盈亏绝对值降序，无值（待确认）排最后。
    positions.sort(key=lambda x: (x["pnl"] is None, -abs(x["pnl"] or 0.0)))

    total = _pick_pnl(r.pnl_cny, r.pnl_usd, currency)
    rounding_diff = (round(details_total - total, 2)
                     if (total is not None and has_details) else 0.0)

    return {
        "timezone": "UTC",
        "day": r.day,
        "currency": currency.value,
        "total": total,
        "status": r.status,
        "note": r.note,
        "updated_at": r.updated_at.isoformat() + "Z",
        "has_details": has_details,
        "no_detail_message": None if has_details else "该日期未记录持仓明细（历史仅有汇总，无法反推逐仓位明细）",
        "coverage_complete": r.coverage_complete,
        "excluded_count": excluded_count,
        "positions": positions,
        "details_total": round(details_total, 2),
        "rounding_diff": rounding_diff,
    }
