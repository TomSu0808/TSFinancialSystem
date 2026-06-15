"""一级界面汇总：总额、今日涨跌、累计盈亏、按币种/平台/类型拆分 + 每日净值快照（按用户隔离）。"""
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Currency,
    Holding,
    Platform,
    Snapshot,
    User,
    cost_basis,
    day_change,
    market_value,
    profit,
)
from routers.fx import get_or_create_rate

router = APIRouter(prefix="/api/summary", tags=["summary"])


def _upsert_daily_snapshot(session: Session, user_id: int, total_cny: float, total_usd: float) -> None:
    """每人每天一条净值快照：当天已有则更新，否则插入。"""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    snap = session.exec(
        select(Snapshot).where(Snapshot.user_id == user_id, Snapshot.day == today)
    ).first()
    if snap:
        snap.ts = datetime.utcnow()
        snap.total_cny = total_cny
        snap.total_usd = total_usd
    else:
        snap = Snapshot(
            user_id=user_id, day=today, total_cny=total_cny, total_usd=total_usd
        )
    session.add(snap)
    session.commit()


@router.get("")
def get_summary(
    currency: Currency = Query(Currency.CNY, description="展示币种 CNY/USD"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    usdcny = get_or_create_rate(session).rate
    # 折算到 CNY 的汇率表（CNY 为基准）
    to_cny = {Currency.CNY: 1.0, Currency.USD: usdcny, Currency.HKD: usdcny / 7.8}

    holdings = session.exec(
        select(Holding).where(Holding.user_id == user.id)
    ).all()
    platforms = {
        p.id: p.name
        for p in session.exec(
            select(Platform).where(Platform.user_id == user.id)
        ).all()
    }

    cur_value: Dict[Currency, float] = {}
    cur_change: Dict[Currency, float] = {}
    plat_value_cny: Dict[int, float] = {}
    type_value_cny: Dict[str, float] = {}

    total_cny = 0.0
    change_cny = 0.0
    cost_cny = 0.0      # 仅统计成本已知的持仓
    profit_cny = 0.0
    for h in holdings:
        mv = market_value(h)
        dc = day_change(h)
        rate = to_cny.get(h.currency, 1.0)
        cur_value[h.currency] = cur_value.get(h.currency, 0.0) + mv
        cur_change[h.currency] = cur_change.get(h.currency, 0.0) + dc
        plat_value_cny[h.platform_id] = plat_value_cny.get(h.platform_id, 0.0) + mv * rate
        type_value_cny[h.asset_type.value] = type_value_cny.get(h.asset_type.value, 0.0) + mv * rate
        total_cny += mv * rate
        change_cny += dc * rate
        cb = cost_basis(h)
        if cb is not None:
            cost_cny += cb * rate
            profit_cny += (profit(h) or 0.0) * rate

    total_usd = total_cny / usdcny if usdcny else 0.0

    _upsert_daily_snapshot(session, user.id, total_cny, total_usd)

    def to_display(amount_cny: float) -> float:
        return amount_cny if currency == Currency.CNY else (
            amount_cny / usdcny if usdcny else 0.0
        )

    total = to_display(total_cny)
    change = to_display(change_cny)
    base = total - change  # 今日开盘基准
    change_pct = (change / base * 100) if base else 0.0

    total_profit = to_display(profit_cny)
    profit_pct = (profit_cny / cost_cny * 100) if cost_cny else 0.0

    by_currency = [
        {
            "currency": c.value,
            "native_total": round(cur_value[c], 2),
            "native_change": round(cur_change.get(c, 0.0), 2),
            "display_total": round(to_display(cur_value[c] * to_cny.get(c, 1.0)), 2),
        }
        for c in cur_value
    ]

    by_platform = [
        {"platform_id": pid, "platform": platforms.get(pid, f"#{pid}"),
         "display_total": round(to_display(v), 2)}
        for pid, v in plat_value_cny.items()
    ]
    by_platform.sort(key=lambda x: x["display_total"], reverse=True)

    by_type = [
        {"asset_type": t, "display_total": round(to_display(v), 2)}
        for t, v in type_value_cny.items()
    ]
    by_type.sort(key=lambda x: x["display_total"], reverse=True)

    return {
        "display_currency": currency.value,
        "total": round(total, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "total_profit": round(total_profit, 2),
        "profit_pct": round(profit_pct, 2),
        "total_cost": round(to_display(cost_cny), 2),
        "rate": round(usdcny, 4),
        "by_currency": by_currency,
        "by_platform": by_platform,
        "by_type": by_type,
    }
