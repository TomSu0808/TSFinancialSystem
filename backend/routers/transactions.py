"""交易流水增删改查（独立账本，不自动改持仓；按用户隔离）。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Currency,
    Holding,
    Platform,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    TxnAction,
    User,
)
from position import recompute_holding, resolve_derived_holding

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


def _sync_txn_holding(session: Session, txn: Transaction, user: User) -> None:
    """(重新)绑定 buy/sell/dividend 流水到其 derived 持仓，并重算受影响的持仓。
    买入可自动建仓；卖出/分红只绑定已存在的 derived 持仓。改了 symbol/platform/currency
    会重绑到新持仓，新旧持仓都会重算。非持仓动作清空 holding_id，避免悬空 FK。"""
    affected = set()
    if txn.holding_id is not None:
        affected.add(txn.holding_id)  # 旧绑定总要重算（动作/标的变更后释放其影响）
    if txn.action in (TxnAction.buy, TxnAction.sell, TxnAction.dividend):
        holding = resolve_derived_holding(
            session, user, txn.platform_id, txn.symbol, txn.currency,
            name=txn.name, create_if_missing=(txn.action == TxnAction.buy),
        )
        if holding is not None:
            if txn.holding_id != holding.id:
                txn.holding_id = holding.id
                session.add(txn)
                session.commit()
            affected.add(holding.id)
    else:
        # Non-position action: clear any dangling holding_id FK
        if txn.holding_id is not None:
            txn.holding_id = None
            session.add(txn)
            session.commit()
    for hid in affected:
        recompute_holding(session, hid)


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
    txn.holding_id = None  # always system-resolved; never trust client input
    session.add(txn)
    session.commit()
    session.refresh(txn)
    _sync_txn_holding(session, txn, user)
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
    values.pop("holding_id", None)  # holding_id is system-managed; ignore client input
    if "platform_id" in values:
        _check_platform(session, values["platform_id"], user)
    for key, value in values.items():
        setattr(txn, key, value)
    session.add(txn)
    session.commit()
    session.refresh(txn)
    _sync_txn_holding(session, txn, user)
    session.refresh(txn)
    return txn


@router.delete("/{txn_id}")
def delete_transaction(
    txn_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    txn = _owned(session, txn_id, user)
    holding_id = txn.holding_id
    session.delete(txn)
    session.commit()
    if holding_id is not None:
        recompute_holding(session, holding_id)
    return {"ok": True}
