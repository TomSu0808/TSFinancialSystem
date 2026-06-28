"""自动化任务服务：行情/汇率/快照批量刷新，可被调度器和 API 调用。

设计原则：
- 纯同步函数，不依赖 HTTP 请求层；调度器通过 asyncio.to_thread 调用。
- 单用户失败不中断其他用户。
- 每次运行写入 AutomationRun 记录，供前端查询状态。
"""
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from models import (
    AutomationRun, Currency, Holding, Snapshot, User,
    market_value,
)
from price_provider import fetch_quote

logger = logging.getLogger(__name__)


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _refresh_fx(session: Session) -> bool:
    """刷新 USD/CNY 汇率，返回是否成功。复用 fx_provider 避免 HTTP 依赖。"""
    from fx_provider import fetch_usdcny
    from models import FxRate
    value = fetch_usdcny()
    if value is None:
        return False
    rate = session.get(FxRate, "USDCNY")
    if not rate:
        rate = FxRate(pair="USDCNY", rate=value, updated_at=datetime.utcnow())
    else:
        rate.rate = value
        rate.updated_at = datetime.utcnow()
    session.add(rate)
    session.commit()
    return True


def _get_usdcny(session: Session) -> float:
    from models import FxRate
    rate = session.get(FxRate, "USDCNY")
    return rate.rate if rate else 7.2


def _refresh_user_holdings(session: Session, user_id: int) -> tuple[int, int]:
    """刷新某用户的持仓行情。返回 (total, updated)。"""
    holdings = session.exec(
        select(Holding).where(Holding.user_id == user_id)
    ).all()
    total = 0
    updated = 0
    for h in holdings:
        if h.manual_value is not None or not h.symbol:
            continue
        total += 1
        try:
            quote = fetch_quote(h.market, h.symbol)
            if quote and quote.get("price") is not None:
                h.current_price = quote["price"]
                h.prev_close = quote.get("prev_close")
                h.price_updated_at = datetime.utcnow()
                session.add(h)
                updated += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("刷新行情失败 user=%s symbol=%s: %s", user_id, h.symbol, exc)
    session.commit()
    return total, updated


def _upsert_snapshot(session: Session, user_id: int) -> bool:
    """为用户保存/更新当日快照。返回是否成功写入。"""
    usdcny = _get_usdcny(session)
    to_cny = {Currency.CNY: 1.0, Currency.USD: usdcny, Currency.HKD: usdcny / 7.8}
    holdings = session.exec(select(Holding).where(Holding.user_id == user_id)).all()
    total_cny = sum(market_value(h) * to_cny.get(h.currency, 1.0) for h in holdings)
    total_usd = total_cny / usdcny if usdcny else 0.0

    today = datetime.utcnow().strftime("%Y-%m-%d")
    snap = session.exec(
        select(Snapshot).where(Snapshot.user_id == user_id, Snapshot.day == today)
    ).first()
    if snap:
        snap.ts = datetime.utcnow()
        snap.total_cny = total_cny
        snap.total_usd = total_usd
    else:
        snap = Snapshot(user_id=user_id, day=today, total_cny=total_cny, total_usd=total_usd)
    session.add(snap)
    session.commit()
    return True


# ── 公开接口 ──────────────────────────────────────────────────────────────────

def run_all_users_job(session: Session, triggered_by: str = "scheduler") -> AutomationRun:
    """全量任务：刷新汇率 + 刷新所有用户行情 + 保存快照 + 评估提醒。
    单用户失败不中断其他用户。返回 AutomationRun 记录。
    """
    from config import ALERTS_ENABLED

    run = AutomationRun(
        job_name="daily_refresh",
        triggered_by=triggered_by,
        started_at=datetime.utcnow(),
        status="running",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        # 1. 刷新汇率（一次，全局）
        fx_ok = _refresh_fx(session)
        run.fx_updated = fx_ok

        # 2. 获取所有用户
        users = session.exec(select(User)).all()
        run.users_total = len(users)

        h_total = 0
        h_updated = 0
        snaps_saved = 0
        succeeded = 0

        for user in users:
            try:
                ht, hu = _refresh_user_holdings(session, user.id)
                h_total += ht
                h_updated += hu
                _upsert_snapshot(session, user.id)
                snaps_saved += 1
                if ALERTS_ENABLED:
                    try:
                        from alert_service import evaluate_alerts_for_user
                        evaluate_alerts_for_user(session, user.id)
                    except Exception as ae:  # noqa: BLE001
                        logger.warning("提醒评估失败 user=%s: %s", user.id, ae)
                succeeded += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("用户 %s 任务失败: %s", user.id, exc)

        run.holdings_total = h_total
        run.holdings_updated = h_updated
        run.snapshots_saved = snaps_saved
        run.users_succeeded = succeeded
        run.status = (
            "success" if succeeded == len(users)
            else "partial_failed" if succeeded > 0
            else "failed"
        )
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        logger.error("自动化任务异常: %s", exc)

    run.finished_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_single_user_job(session: Session, user_id: int) -> AutomationRun:
    """单用户手动触发刷新：行情 + 快照 + 提醒评估。"""
    from config import ALERTS_ENABLED

    run = AutomationRun(
        job_name="daily_refresh",
        triggered_by="manual",
        started_at=datetime.utcnow(),
        status="running",
        users_total=1,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        fx_ok = _refresh_fx(session)
        run.fx_updated = fx_ok

        ht, hu = _refresh_user_holdings(session, user_id)
        run.holdings_total = ht
        run.holdings_updated = hu

        _upsert_snapshot(session, user_id)
        run.snapshots_saved = 1

        if ALERTS_ENABLED:
            try:
                from alert_service import evaluate_alerts_for_user
                evaluate_alerts_for_user(session, user_id)
            except Exception as ae:  # noqa: BLE001
                logger.warning("提醒评估失败: %s", ae)

        run.users_succeeded = 1
        run.status = "success"
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_message = str(exc)
        logger.error("单用户任务异常: %s", exc)

    run.finished_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_last_run(session: Session) -> Optional[AutomationRun]:
    """返回最近一次已完成的 AutomationRun。"""
    return session.exec(
        select(AutomationRun)
        .where(AutomationRun.status != "running")
        .order_by(AutomationRun.started_at.desc())
    ).first()
