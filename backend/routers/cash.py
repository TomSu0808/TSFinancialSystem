"""现金账户与流水查询：按 (platform, currency) 汇总现金状态，供账户详情现金区展示。

余额口径与 cash_service.replay_cash 完全一致；未初始化的账户也返回（balance=None），
前端据此提示「初始化现金」。入金/出金/校准走既有 /api/transactions 接口。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from auth import get_current_user
from cash_service import CASH_ACTIONS, cash_ledger, replay_cash
from database import get_session
from decimal_utils import to_float
from models import Currency, Platform, Transaction, User

router = APIRouter(prefix="/api/cash", tags=["cash"])


@router.get("")
def list_cash(
    platform_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """按 (platform, currency) 返回现金状态（含未初始化提示）。"""
    stmt = select(Transaction).where(
        Transaction.user_id == user.id,
        Transaction.action.in_(CASH_ACTIONS),
    )
    if platform_id is not None:
        stmt = stmt.where(Transaction.platform_id == platform_id)
    txns = session.exec(stmt).all()

    platforms = {
        p.id: p.name
        for p in session.exec(select(Platform).where(Platform.user_id == user.id)).all()
    }

    groups: dict = {}
    for t in txns:
        if t.platform_id is None:
            continue
        groups.setdefault((t.platform_id, t.currency), []).append(t)

    result = []
    for (pid, cur), t_list in groups.items():
        st = replay_cash(t_list)
        result.append({
            "platform_id": pid,
            "platform": platforms.get(pid, f"#{pid}"),
            "currency": cur.value,
            "initialized": st.started,
            "balance": to_float(st.balance) if st.started else None,
            "cash_adjust_count": st.cash_adjust_count,
            "last_anchor_date": st.last_anchor_date,
            "txn_count": len(t_list),
        })
    result.sort(key=lambda x: (x["platform"], x["currency"]))
    return result


@router.get("/ledger")
def get_cash_ledger(
    platform_id: int = Query(...),
    currency: Currency = Query(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """某 (platform, currency) 的现金流水（按时间序，含运行余额）。"""
    platform = session.get(Platform, platform_id)
    if not platform or platform.user_id != user.id:
        raise HTTPException(404, "平台不存在")

    txns = session.exec(select(Transaction).where(
        Transaction.user_id == user.id,
        Transaction.platform_id == platform_id,
        Transaction.currency == currency,
        Transaction.action.in_(CASH_ACTIONS),
    )).all()

    st = replay_cash(txns)
    return {
        "platform_id": platform_id,
        "platform": platform.name,
        "currency": currency.value,
        "initialized": st.started,
        "balance": to_float(st.balance) if st.started else None,
        "entries": cash_ledger(txns),
    }
