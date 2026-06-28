"""提醒规则和事件 CRUD（按登录用户隔离）。"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import AlertEvent, AlertRule, AlertRuleCreate, AlertRuleUpdate, Holding, User

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _owned_rule(session: Session, rule_id: int, user: User) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if not rule or rule.user_id != user.id:
        raise HTTPException(404, "提醒规则不存在")
    return rule


def _owned_event(session: Session, event_id: int, user: User) -> AlertEvent:
    ev = session.get(AlertEvent, event_id)
    if not ev or ev.user_id != user.id:
        raise HTTPException(404, "提醒事件不存在")
    return ev


def _validate_holding(session: Session, holding_id: Optional[int], user: User) -> None:
    """校验 holding_id 属于当前用户。"""
    if holding_id is None:
        return
    h = session.get(Holding, holding_id)
    if not h or h.user_id != user.id:
        raise HTTPException(404, "持仓不存在")


# ── 规则 ──────────────────────────────────────────────────────────────────────

@router.get("/rules", response_model=List[AlertRule])
def list_rules(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return session.exec(
        select(AlertRule)
        .where(AlertRule.user_id == user.id)
        .order_by(AlertRule.created_at.desc())
    ).all()


@router.post("/rules", response_model=AlertRule)
def create_rule(
    data: AlertRuleCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _validate_holding(session, data.holding_id, user)
    rule = AlertRule.model_validate(data, update={"user_id": user.id})
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
def update_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rule = _owned_rule(session, rule_id, user)
    values = data.model_dump(exclude_unset=True)
    if "holding_id" in values:
        _validate_holding(session, values["holding_id"], user)
    for k, v in values.items():
        setattr(rule, k, v)
    rule.updated_at = datetime.utcnow()
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    rule = _owned_rule(session, rule_id, user)
    session.delete(rule)
    session.commit()
    return {"ok": True}


# ── 事件 ──────────────────────────────────────────────────────────────────────

@router.get("/events")
def list_events(
    status: Optional[str] = Query(None, description="unread/read/dismissed"),
    alert_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[dict]:
    stmt = select(AlertEvent).where(AlertEvent.user_id == user.id)
    if status:
        stmt = stmt.where(AlertEvent.status == status)
    if alert_type:
        stmt = stmt.where(AlertEvent.alert_type == alert_type)
    events = session.exec(
        stmt.order_by(AlertEvent.triggered_at.desc()).limit(limit)
    ).all()
    return [e.model_dump() for e in events]


@router.get("/events/unread-count")
def unread_count(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    events = session.exec(
        select(AlertEvent).where(
            AlertEvent.user_id == user.id,
            AlertEvent.status == "unread",
        )
    ).all()
    return {"count": len(events)}


@router.post("/events/{event_id}/read")
def mark_read(
    event_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    ev = _owned_event(session, event_id, user)
    ev.status = "read"
    session.add(ev)
    session.commit()
    return {"ok": True}


@router.post("/events/read-all")
def mark_all_read(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    events = session.exec(
        select(AlertEvent).where(
            AlertEvent.user_id == user.id,
            AlertEvent.status == "unread",
        )
    ).all()
    for ev in events:
        ev.status = "read"
        session.add(ev)
    session.commit()
    return {"ok": True, "updated": len(events)}


@router.post("/events/{event_id}/dismiss")
def dismiss(
    event_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    ev = _owned_event(session, event_id, user)
    ev.status = "dismissed"
    session.add(ev)
    session.commit()
    return {"ok": True}


@router.post("/evaluate")
def evaluate(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """手动触发当前用户的提醒规则评估，返回新生成事件数。"""
    from alert_service import evaluate_alerts_for_user
    new_events = evaluate_alerts_for_user(session, user.id)
    return {"triggered": len(new_events)}
