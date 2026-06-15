"""投资心得（备忘录）增删改查（按登录用户隔离）。"""
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Note, NoteCreate, NoteUpdate, User

router = APIRouter(prefix="/api/notes", tags=["notes"])


def _owned(session: Session, note_id: int, user: User) -> Note:
    note = session.get(Note, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(404, "心得不存在")
    return note


@router.get("", response_model=List[Note])
def list_notes(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # 最新在前
    return session.exec(
        select(Note).where(Note.user_id == user.id).order_by(Note.created_at.desc())
    ).all()


@router.post("", response_model=Note)
def create_note(
    data: NoteCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
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
    for key, value in data.model_dump(exclude_unset=True).items():
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
