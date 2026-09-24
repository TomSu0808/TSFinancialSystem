"""统一现金重算服务：按 (user, platform, currency) 从 deposit/withdraw 交易流水重算现金余额。

设计要点：
- 重算后现金余额 = sum(deposit.amount) - sum(withdraw.amount)
- deposit 取 txn.amount，若 amount 缺失则取 txn.quantity；withdraw 同理
- 重算后金额为 0 时保留 cash holding 并设 manual_value=0.0，不删除
- withdraw 不能导致余额为负（校验在 transaction_validation 中做）
- 修改/删除/导入 commit 后统一调用 recalc_cash 触发重算
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from models import Currency, Holding, HoldingSource, Transaction, TxnAction, User


def _get_txn_cash_amount(txn: Transaction) -> float:
    """从交易记录中提取现金金额：优先 amount，其次 quantity。"""
    amount = txn.amount or 0.0
    if amount <= 0:
        amount = txn.quantity or 0.0
    return amount


def recalc_cash(
    session: Session,
    user: User,
    platform_id: int,
    currency: Currency,
) -> Holding:
    """按 (user, platform, currency) 从 deposit/withdraw 交易流水重算现金余额。

    返回更新后的 cash holding（一定存在）；只 flush，由调用方统一提交。
    """
    # 查找所有该维度的 deposit/withdraw 交易
    txns = session.exec(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.platform_id == platform_id,
            Transaction.currency == currency,
            Transaction.action.in_([TxnAction.deposit, TxnAction.withdraw]),
        )
    ).all()

    # 从流水重算
    balance = 0.0
    for t in txns:
        amt = _get_txn_cash_amount(t)
        if t.action == TxnAction.deposit:
            balance += amt
        elif t.action == TxnAction.withdraw:
            balance -= amt

    # 查找或创建 cash holding
    cash = session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.platform_id == platform_id,
            Holding.currency == currency,
            Holding.asset_type == "cash",
            Holding.source == HoldingSource.derived,
        )
    ).first()

    if cash is None:
        cash = Holding(
            user_id=user.id,
            platform_id=platform_id,
            currency=currency,
            asset_type="cash",
            market="NONE",
            name=f"现金余额 ({currency.value})",
            symbol="",
            source=HoldingSource.derived,
            status="open",
            manual_value=0.0,
        )
        session.add(cash)
        session.flush()
        session.refresh(cash)

    cash.manual_value = max(balance, 0.0)
    cash.price_updated_at = datetime.utcnow()
    session.add(cash)
    session.flush()
    session.refresh(cash)
    return cash


def get_cash_balance(
    session: Session,
    user: User,
    platform_id: int,
    currency: Currency,
) -> float:
    """按流水重算得到现金余额（只读，不修改 DB）。用于校验 withdraw 是否超额。"""
    txns = session.exec(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.platform_id == platform_id,
            Transaction.currency == currency,
            Transaction.action.in_([TxnAction.deposit, TxnAction.withdraw]),
        )
    ).all()

    balance = 0.0
    for t in txns:
        amt = _get_txn_cash_amount(t)
        if t.action == TxnAction.deposit:
            balance += amt
        elif t.action == TxnAction.withdraw:
            balance -= amt
    return balance
