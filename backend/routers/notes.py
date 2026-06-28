"""投资决策日志增删改查（按登录用户隔离）。"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Holding, Note, NoteCreate, NoteUpdate, ResearchReport, User

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _owned(session: Session, note_id: int, user: User) -> Note:
    note = session.get(Note, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(404, "心得不存在")
    return note


def _validate_refs(session: Session, data_dict: dict, user: User) -> None:
    """校验 related_holding_id / source_report_id 属于当前用户。"""
    hid = data_dict.get("related_holding_id")
    if hid is not None:
        h = session.get(Holding, hid)
        if not h or h.user_id != user.id:
            raise HTTPException(404, "关联持仓不存在")
    rid = data_dict.get("source_report_id")
    if rid is not None:
        r = session.get(ResearchReport, rid)
        if not r or r.user_id != user.id:
            raise HTTPException(404, "关联报告不存在")


@router.get("", response_model=List[Note])
def list_notes(
    symbol: Optional[str] = Query(None),
    note_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    related_holding_id: Optional[int] = Query(None),
    source_report_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Note).where(Note.user_id == user.id)
    if symbol:
        stmt = stmt.where(Note.symbol == symbol)
    if note_type:
        stmt = stmt.where(Note.note_type == note_type)
    if status:
        stmt = stmt.where(Note.status == status)
    if related_holding_id is not None:
        stmt = stmt.where(Note.related_holding_id == related_holding_id)
    if source_report_id is not None:
        stmt = stmt.where(Note.source_report_id == source_report_id)
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(or_(Note.title.like(kw), Note.content.like(kw)))
    return session.exec(stmt.order_by(Note.updated_at.desc())).all()


@router.post("", response_model=Note)
def create_note(
    data: NoteCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _validate_refs(session, data.model_dump(), user)
    note = Note.model_validate(data, update={"user_id": user.id})
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


@router.put("/{note_id}", response_model=Note)
def update_note(
    note_id: int,
    data: NoteUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    note = _owned(session, note_id, user)
    patch = data.model_dump(exclude_unset=True)
    _validate_refs(session, patch, user)
    for key, value in patch.items():
        setattr(note, key, value)
    note.updated_at = datetime.utcnow()
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    note = _owned(session, note_id, user)
    session.delete(note)
    session.commit()
    return {"ok": True}
