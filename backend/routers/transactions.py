"""交易流水增删改查（独立账本，不自动改持仓；按用户隔离）。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Platform,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    User,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _check_platform(session: Session, platform_id: Optional[int], user: User) -> None:
    if platform_id is None:
        return
    platform = session.get(Platform, platform_id)
    if not platform or platform.user_id != user.id:
        raise HTTPException(404, "平台不存在")


def _owned(session: Session, txn_id: int, user: User) -> Transaction:
    txn = session.get(Transaction, txn_id)
    if not txn or txn.user_id != user.id:
        raise HTTPException(404, "交易记录不存在")
    return txn


@router.get("", response_model=List[Transaction])
def list_transactions(
    platform_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if platform_id is not None:
        stmt = stmt.where(Transaction.platform_id == platform_id)
    # 日期倒序，同日按创建倒序
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    return session.exec(stmt).all()


@router.post("", response_model=Transaction)
def create_transaction(
    data: TransactionCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _check_platform(session, data.platform_id, user)
    txn = Transaction.model_validate(data, update={"user_id": user.id})
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


@router.put("/{txn_id}", response_model=Transaction)
def update_transaction(
    txn_id: int,
    data: TransactionUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    txn = _owned(session, txn_id, user)
    values = data.model_dump(exclude_unset=True)
    if "platform_id" in values:
        _check_platform(session, values["platform_id"], user)
    for key, value in values.items():
        setattr(txn, key, value)
    session.add(txn)
    session.commit()
    session.refresh(txn)
    return txn


@router.delete("/{txn_id}")
def delete_transaction(
    txn_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    txn = _owned(session, txn_id, user)
    session.delete(txn)
    session.commit()
    return {"ok": True}
