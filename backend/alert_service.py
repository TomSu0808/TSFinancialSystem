"""提醒评估服务：根据 AlertRule 检查持仓状态并生成 AlertEvent。

支持类型：
  price_above / price_below              价格阈值
  day_change_pct_above / below           今日涨跌幅阈值（%）
  allocation_above / allocation_below    仓位占总资产比例阈值（%）
  price_stale                            行情超过 stale_hours 小时未更新
  refresh_failed                         最近一次自动刷新任务失败

去重规则：同一 rule_id 当天已有 unread 事件则跳过，避免重复刷屏。
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, select

from models import (
    AlertEvent, AlertRule, AutomationRun, Currency, Holding,
    HoldingStatus, market_value,
)

logger = logging.getLogger(__name__)

_ALERT_TYPES_PRICE = {"price_above", "price_below"}
_ALERT_TYPES_PCT = {"day_change_pct_above", "day_change_pct_below"}
_ALERT_TYPES_ALLOC = {"allocation_above", "allocation_below"}


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _already_fired_today(session: Session, rule_id: int) -> bool:
    """同一规则当天已有 unread 事件则返回 True。"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = session.exec(
        select(AlertEvent).where(
            AlertEvent.rule_id == rule_id,
            AlertEvent.status == "unread",
            AlertEvent.triggered_at >= today_start,
        )
    ).first()
    return existing is not None


def _get_usdcny(session: Session) -> float:
    from models import FxRate
    rate = session.get(FxRate, "USDCNY")
    return rate.rate if rate else 7.2


def _compute_total_cny(session: Session, user_id: int) -> float:
    usdcny = _get_usdcny(session)
    to_cny = {Currency.CNY: 1.0, Currency.USD: usdcny, Currency.HKD: usdcny / 7.8}
    holdings = session.exec(
        select(Holding).where(
            Holding.user_id == user_id,
            Holding.status == HoldingStatus.open,
        )
    ).all()
    return sum(market_value(h) * to_cny.get(h.currency, 1.0) for h in holdings)


def _create_event(
    session: Session,
    user_id: int,
    rule: AlertRule,
    title: str,
    message: str,
    severity: str = "warning",
    value: float = None,
    holding_id: int = None,
    symbol: str = None,
) -> AlertEvent:
    ev = AlertEvent(
        user_id=user_id,
        rule_id=rule.id,
        alert_type=rule.alert_type,
        severity=severity,
        title=title,
        message=message,
        holding_id=holding_id or rule.holding_id,
        symbol=symbol or rule.symbol,
        value=value,
        threshold_value=rule.threshold_value,
        triggered_at=datetime.utcnow(),
        status="unread",
    )
    session.add(ev)
    return ev


def evaluate_alerts_for_user(session: Session, user_id: int) -> List[AlertEvent]:
    """评估该用户所有启用的提醒规则，返回本次新生成的事件列表。"""
    from config import ALERTS_ENABLED
    if not ALERTS_ENABLED:
        return []

    rules = session.exec(
        select(AlertRule).where(
            AlertRule.user_id == user_id,
            AlertRule.enabled == True,  # noqa: E712
        )
    ).all()

    if not rules:
        return []

    open_holdings = session.exec(
        select(Holding).where(
            Holding.user_id == user_id,
            Holding.status == HoldingStatus.open,
        )
    ).all()

    total_cny = _compute_total_cny(session, user_id)
    usdcny = _get_usdcny(session)
    to_cny = {Currency.CNY: 1.0, Currency.USD: usdcny, Currency.HKD: usdcny / 7.8}

    new_events: List[AlertEvent] = []

    for rule in rules:
        try:
            events = _evaluate_rule(
                session, user_id, rule, open_holdings, total_cny, to_cny
            )
            new_events.extend(events)
        except Exception as exc:  # noqa: BLE001
            logger.warning("规则 %s 评估异常: %s", rule.id, exc)

    if new_events:
        session.commit()

    return new_events


def _evaluate_rule(
    session: Session,
    user_id: int,
    rule: AlertRule,
    open_holdings: List[Holding],
    total_cny: float,
    to_cny: dict,
) -> List[AlertEvent]:
    """评估单条规则，返回本次新生成的事件（0 或 1 条）。"""
    t = rule.alert_type
    events = []

    if t in _ALERT_TYPES_PRICE:
        ev = _eval_price(session, user_id, rule, open_holdings)
        if ev:
            events.append(ev)

    elif t in _ALERT_TYPES_PCT:
        ev = _eval_change_pct(session, user_id, rule, open_holdings)
        if ev:
            events.append(ev)

    elif t in _ALERT_TYPES_ALLOC:
        ev = _eval_allocation(session, user_id, rule, open_holdings, total_cny, to_cny)
        if ev:
            events.append(ev)

    elif t == "price_stale":
        ev = _eval_stale(session, user_id, rule, open_holdings)
        if ev:
            events.append(ev)

    elif t == "refresh_failed":
        ev = _eval_refresh_failed(session, user_id, rule)
        if ev:
            events.append(ev)

    return events


def _get_target_holdings(rule: AlertRule, holdings: List[Holding]) -> List[Holding]:
    """根据规则的 holding_id / symbol / currency 过滤目标持仓。"""
    if rule.holding_id:
        return [h for h in holdings if h.id == rule.holding_id]
    if rule.symbol:
        return [h for h in holdings if h.symbol and h.symbol.upper() == rule.symbol.upper()]
    if rule.currency:
        return [h for h in holdings if h.currency.value == rule.currency]
    return holdings


def _eval_price(session, user_id, rule, holdings) -> Optional[AlertEvent]:
    targets = _get_target_holdings(rule, holdings)
    for h in targets:
        if h.current_price is None or rule.threshold_value is None:
            continue
        triggered = (
            (rule.alert_type == "price_above" and h.current_price > rule.threshold_value)
            or (rule.alert_type == "price_below" and h.current_price < rule.threshold_value)
        )
        if not triggered:
            continue
        if _already_fired_today(session, rule.id):
            continue
        direction = "突破" if rule.alert_type == "price_above" else "跌破"
        return _create_event(
            session, user_id, rule,
            title=f"{h.name or h.symbol} 价格提醒",
            message=(
                f"{h.name or h.symbol} 当前价 {h.current_price:.4g} "
                f"{direction} 阈值 {rule.threshold_value:.4g}"
            ),
            severity="warning",
            value=h.current_price,
            holding_id=h.id,
            symbol=h.symbol,
        )
    return None


def _eval_change_pct(session, user_id, rule, holdings) -> Optional[AlertEvent]:
    targets = _get_target_holdings(rule, holdings)
    for h in targets:
        if h.current_price is None or h.prev_close is None or rule.threshold_value is None:
            continue
        pct = (h.current_price - h.prev_close) / h.prev_close * 100
        triggered = (
            (rule.alert_type == "day_change_pct_above" and pct > rule.threshold_value)
            or (rule.alert_type == "day_change_pct_below" and pct < rule.threshold_value)
        )
        if not triggered:
            continue
        if _already_fired_today(session, rule.id):
            continue
        return _create_event(
            session, user_id, rule,
            title=f"{h.name or h.symbol} 涨跌幅提醒",
            message=(
                f"{h.name or h.symbol} 今日涨跌 {pct:+.2f}%，"
                f"阈值 {rule.threshold_value:+.2f}%"
            ),
            severity="warning",
            value=round(pct, 2),
            holding_id=h.id,
            symbol=h.symbol,
        )
    return None


def _eval_allocation(session, user_id, rule, holdings, total_cny, to_cny) -> Optional[AlertEvent]:
    if total_cny == 0 or rule.threshold_value is None:
        return None
    targets = _get_target_holdings(rule, holdings)
    for h in targets:
        mv_cny = market_value(h) * to_cny.get(h.currency, 1.0)
        alloc_pct = mv_cny / total_cny * 100
        triggered = (
            (rule.alert_type == "allocation_above" and alloc_pct > rule.threshold_value)
            or (rule.alert_type == "allocation_below" and alloc_pct < rule.threshold_value)
        )
        if not triggered:
            continue
        if _already_fired_today(session, rule.id):
            continue
        direction = "超过" if rule.alert_type == "allocation_above" else "低于"
        return _create_event(
            session, user_id, rule,
            title=f"{h.name or h.symbol} 仓位提醒",
            message=(
                f"{h.name or h.symbol} 仓位 {alloc_pct:.1f}% "
                f"{direction} 阈值 {rule.threshold_value:.1f}%"
            ),
            severity="info",
            value=round(alloc_pct, 2),
            holding_id=h.id,
            symbol=h.symbol,
        )
    return None


def _eval_stale(session, user_id, rule, holdings) -> Optional[AlertEvent]:
    stale_hours = rule.stale_hours or 24
    threshold_dt = datetime.utcnow() - timedelta(hours=stale_hours)
    targets = _get_target_holdings(rule, holdings)
    stale = [
        h for h in targets
        if h.symbol and h.manual_value is None
        and (h.price_updated_at is None or h.price_updated_at < threshold_dt)
    ]
    if not stale:
        return None
    if _already_fired_today(session, rule.id):
        return None
    names = "、".join((h.name or h.symbol) for h in stale[:3])
    return _create_event(
        session, user_id, rule,
        title="行情数据过期提醒",
        message=f"以下持仓行情超过 {stale_hours}h 未更新：{names}",
        severity="info",
    )


def _eval_refresh_failed(session, user_id, rule) -> Optional[AlertEvent]:
    last_run = session.exec(
        select(AutomationRun)
        .where(AutomationRun.status != "running")
        .order_by(AutomationRun.started_at.desc())
    ).first()
    if not last_run or last_run.status not in ("failed", "partial_failed"):
        return None
    if _already_fired_today(session, rule.id):
        return None
    return _create_event(
        session, user_id, rule,
        title="自动刷新失败提醒",
        message=(
            f"最近一次自动刷新状态：{last_run.status}，"
            f"完成于 {last_run.finished_at.strftime('%H:%M') if last_run.finished_at else '未知'}"
        ),
        severity="critical",
    )
