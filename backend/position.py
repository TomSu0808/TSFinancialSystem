"""持仓派生计算：交易流水驱动 derived 持仓的数量 / 移动加权成本 / 已实现盈亏。

设计：纯逻辑 replay_transactions（无副作用，便于单测）与带 DB 副作用的
recompute_holding 分离。详见 docs/superpowers/specs/2026-06-15-transaction-driven-holdings-design.md
"""
from typing import Iterable

from models import Transaction, TxnAction

CLOSE_EPS = 1e-9  # 数量小于此阈值视为清仓，避免浮点残留


class PositionState:
    def __init__(self) -> None:
        self.quantity = 0.0
        self.avg_cost = 0.0
        self.realized_pnl = 0.0
        self.realized_income = 0.0


def replay_transactions(txns: Iterable[Transaction]) -> PositionState:
    """按 (date, id) 升序重放流水，返回派生状态。买/卖驱动数量与成本，
    分红计入已实现收益，入金/出金/其它跳过。"""
    st = PositionState()
    for t in sorted(txns, key=lambda x: (x.date or "", x.id or 0)):
        q = t.quantity or 0.0
        price = t.price or 0.0
        fee = t.fee or 0.0
        if t.action == TxnAction.buy:
            total_cost = st.quantity * st.avg_cost + q * price + fee
            st.quantity += q
            st.avg_cost = total_cost / st.quantity if st.quantity > CLOSE_EPS else 0.0
        elif t.action == TxnAction.sell:
            st.realized_pnl += q * price - q * st.avg_cost - fee
            st.quantity -= q
            if abs(st.quantity) < CLOSE_EPS:
                st.quantity = 0.0
                st.avg_cost = 0.0
        elif t.action == TxnAction.dividend:
            st.realized_income += t.amount if t.amount is not None else 0.0
        # deposit / withdraw / other: 不影响持仓
    return st
