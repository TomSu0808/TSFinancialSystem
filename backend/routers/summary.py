"""一级界面汇总：总额、今日涨跌、累计盈亏、按币种/平台/类型拆分 + 每日净值快照（按用户隔离）。"""
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Currency,
    Holding,
    HoldingStatus,
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
    realized_pnl_cny = 0.0
    realized_income_cny = 0.0
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
        realized_pnl_cny += (h.realized_pnl or 0.0) * rate
        realized_income_cny += (h.realized_income or 0.0) * rate

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
    realized_pnl = to_display(realized_pnl_cny)
    realized_income = to_display(realized_income_cny)
    total_return = total_profit + realized_pnl + realized_income

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

    # ── top_movers ────────────────────────────────────────────────────────────
    open_holdings = [h for h in holdings if h.status == HoldingStatus.open]
    movers = []
    for h in open_holdings:
        dc = day_change(h)
        if dc == 0.0 or h.prev_close is None or h.current_price is None:
            continue
        rate = to_cny.get(h.currency, 1.0)
        display_change = to_display(dc * rate)
        display_val = to_display(market_value(h) * rate)
        change_pct_h = (h.current_price - h.prev_close) / h.prev_close * 100
        movers.append({
            "holding_id": h.id,
            "name": h.name,
            "symbol": h.symbol,
            "platform": platforms.get(h.platform_id, f"#{h.platform_id}"),
            "currency": h.currency.value,
            "display_change": round(display_change, 2),
            "display_value": round(display_val, 2),
            "change_pct": round(change_pct_h, 2),
        })
    movers.sort(key=lambda x: abs(x["display_change"]), reverse=True)
    top_movers = movers[:5]

    # ── return_breakdown ──────────────────────────────────────────────────────
    return_breakdown = {
        "unrealized_pnl": round(total_profit, 2),
        "realized_pnl": round(realized_pnl, 2),
        "realized_income": round(realized_income, 2),
        "total_return": round(total_return, 2),
    }

    # ── data_freshness ────────────────────────────────────────────────────────
    now = datetime.utcnow()
    stale_threshold = now - timedelta(hours=24)
    priced_count = sum(1 for h in open_holdings if h.current_price is not None)
    stale_open = [
        h for h in open_holdings
        if h.price_updated_at is None or h.price_updated_at < stale_threshold
    ]
    data_freshness = {
        "priced_count": priced_count,
        "stale_count": len(stale_open),
        "stale_items": [
            {
                "name": h.name,
                "symbol": h.symbol,
                "platform": platforms.get(h.platform_id, f"#{h.platform_id}"),
                "currency": h.currency.value,
                "price_updated_at": h.price_updated_at.isoformat() if h.price_updated_at else None,
            }
            for h in stale_open[:5]
        ],
    }

    return {
        "display_currency": currency.value,
        "total": round(total, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "total_profit": round(total_profit, 2),
        "profit_pct": round(profit_pct, 2),
        "realized_pnl": round(realized_pnl, 2),
        "realized_income": round(realized_income, 2),
        "total_return": round(total_return, 2),
        "total_cost": round(to_display(cost_cny), 2),
        "rate": round(usdcny, 4),
        "by_currency": by_currency,
        "by_platform": by_platform,
        "by_type": by_type,
        "top_movers": top_movers,
        "return_breakdown": return_breakdown,
        "data_freshness": data_freshness,
    }


# ── 数据状态中心 ─────────────────────────────────────────────────────────

# 过期规则（保守默认值，后续可集中调整）
STALE_HOURS_PRICE = 24       # 行情超过 24h 视为过期
STALE_HOURS_FX = 12          # 汇率超过 12h 视为过期
STALE_HOURS_MANUAL = 72      # 手填资产超过 72h 未更新视为过期
STALE_HOURS_AI_REPORT = 168  # AI 报告超过 7 天未更新视为过期


def _is_stale(updated_at: Optional[datetime], stale_hours: int) -> bool:
    if updated_at is None:
        return True
    return (datetime.utcnow() - updated_at).total_seconds() > stale_hours * 3600


@router.get("/data-status")
def get_data_status(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """汇总所有数据的状态：行情、汇率、手填资产、AI 报告。"""
    now = datetime.utcnow()

    # ── 1. 汇率状态 ─────────────────────────────────────────────
    fx = get_or_create_rate(session)
    fx_status = {
        "data_type": "汇率",
        "source": "open.er-api.com（回退：中行）",
        "rate": round(fx.rate, 4),
        "updated_at": fx.updated_at.isoformat() if fx.updated_at else None,
        "is_stale": _is_stale(fx.updated_at, STALE_HOURS_FX),
        "description": (
            f"USD/CNY = {fx.rate:.4f}，"
            f"更新于 {fx.updated_at.strftime('%Y-%m-%d %H:%M UTC') if fx.updated_at else '未知时间'}"
        ),
    }

    # ── 2. 持仓行情状态 ──────────────────────────────────────────
    holdings = session.exec(
        select(Holding).where(Holding.user_id == user.id)
    ).all()

    price_items = []
    manual_items = []
    for h in holdings:
        is_stale = _is_stale(h.price_updated_at, STALE_HOURS_PRICE)
        if h.source == "manual" and h.manual_value is not None:
            manual_items.append({
                "id": h.id,
                "name": h.name,
                "asset_type": h.asset_type.value,
                "currency": h.currency.value,
                "manual_value": h.manual_value,
                "updated_at": h.price_updated_at.isoformat() if h.price_updated_at else None,
                "is_stale": _is_stale(h.price_updated_at, STALE_HOURS_MANUAL),
            })
        if h.current_price is not None:
            source_map = {
                "A": "akshare（东方财富快照）",
                "HK": "akshare（东方财富快照）",
                "US": "akshare（东方财富快照）",
                "FUND": "akshare（基金净值）",
                "CRYPTO": "CoinGecko 免费接口",
                "NONE": "手动维护",
            }
            price_items.append({
                "id": h.id,
                "name": h.name,
                "symbol": h.symbol,
                "asset_type": h.asset_type.value,
                "market": h.market.value,
                "currency": h.currency.value,
                "current_price": h.current_price,
                "source": source_map.get(h.market.value, "未知"),
                "price_updated_at": h.price_updated_at.isoformat() if h.price_updated_at else None,
                "is_stale": is_stale,
            })

    priced_count = len(price_items)
    stale_count = sum(1 for p in price_items if p["is_stale"])

    # ── 3. AI 报告状态 ───────────────────────────────────────────
    from models import ResearchReport as RR
    reports = session.exec(
        select(RR).where(
            RR.user_id == user.id,
            RR.status.in_(["completed", "running"]),
        ).order_by(RR.updated_at.desc()).limit(10)
    ).all()

    ai_items = []
    for r in reports:
        ai_items.append({
            "id": r.id,
            "title": r.title,
            "template_key": r.template_key,
            "status": r.status,
            "provider": r.provider or "unknown",
            "model": r.model or "unknown",
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "is_stale": _is_stale(r.completed_at or r.created_at, STALE_HOURS_AI_REPORT),
            "has_byok": r.user_ai_key_id is not None,
        })

    # ── 4. 汇总 ─────────────────────────────────────────────────
    return {
        "generated_at": now.isoformat(),
        "fx": fx_status,
        "holdings": {
            "priced_count": priced_count,
            "stale_count": stale_count,
            "total_open": len([h for h in holdings if h.status == "open"]),
            "stale_threshold_hours": STALE_HOURS_PRICE,
            "items": price_items[:20],  # 最多返回 20 条
        },
        "manual_assets": {
            "count": len(manual_items),
            "stale_count": sum(1 for m in manual_items if m["is_stale"]),
            "stale_threshold_hours": STALE_HOURS_MANUAL,
            "items": manual_items[:10],
        },
        "ai_reports": {
            "count": len(ai_items),
            "stale_count": sum(1 for a in ai_items if a["is_stale"]),
            "stale_threshold_hours": STALE_HOURS_AI_REPORT,
            "items": ai_items,
        },
        "stale_thresholds": {
            "price_hours": STALE_HOURS_PRICE,
            "fx_hours": STALE_HOURS_FX,
            "manual_hours": STALE_HOURS_MANUAL,
            "ai_report_hours": STALE_HOURS_AI_REPORT,
        },
    }
