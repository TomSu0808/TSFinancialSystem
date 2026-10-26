"""研究任务事件记录。前端进度只使用这些真实事件。"""
import json
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from models import ResearchReport, ResearchRunEvent


def append_event(
    session: Session,
    report: ResearchReport,
    stage: str,
    status: str,
    message: str = "",
    payload: Optional[Dict[str, Any]] = None,
    commit: bool = False,
) -> ResearchRunEvent:
    current = session.exec(
        select(func.max(ResearchRunEvent.seq)).where(
            ResearchRunEvent.report_id == report.id,
            ResearchRunEvent.user_id == report.user_id,
        )
    ).one()
    event = ResearchRunEvent(
        user_id=report.user_id,
        report_id=report.id,
        seq=int(current or 0) + 1,
        stage=stage,
        status=status,
        message=message,
        payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
    )
    session.add(event)
    report.progress_stage = stage
    report.updated_at = event.created_at
    session.add(report)
    if commit:
        session.commit()
        session.refresh(event)
    return event


def list_events(session: Session, report_id: int, user_id: int) -> list:
    return list(session.exec(
        select(ResearchRunEvent).where(
            ResearchRunEvent.report_id == report_id,
            ResearchRunEvent.user_id == user_id,
        ).order_by(ResearchRunEvent.seq.asc(), ResearchRunEvent.id.asc())
    ).all())
