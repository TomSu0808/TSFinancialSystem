"""持仓派生计算：交易流水驱动 derived 持仓的数量 / 移动加权成本 / 已实现盈亏。

设计：纯逻辑 replay_transactions（无副作用，便于单测）与带 DB 副作用的
recompute_holding 分离。详见 docs/superpowers/specs/2026-06-15-transaction-driven-holdings-design.md

精度：核心计算使用 Decimal 避免二进制浮点累积误差（如 0.1 + 0.2）。
"""
from decimal import Decimal
from typing import Iterable, Optional

from sqlmodel import Session, select

from decimal_utils import d_div, d_mul, d_sub, d_sum, to_d, to_float
from models import Currency, Holding, HoldingSource, HoldingStatus, Transaction, TxnAction, User

CLOSE_EPS_D = Decimal("1e-9")  # 数量小于此阈值视为清仓


class PositionState:
    def __init__(self) -> None:
        self.quantity = 0.0
        self.avg_cost = 0.0
        self.realized_pnl = 0.0
        self.realized_income = 0.0


def replay_transactions(txns: Iterable[Transaction]) -> PositionState:
    """按 (date, id) 升序重放流水，返回派生状态。买/卖驱动数量与成本，
    分红计入已实现收益，入金/出金/其它跳过。

    内部使用 Decimal 保证精度，对外返回 float（兼容现有接口）。
    """
    st = PositionState()
    # 内部 Decimal 状态
    qty_d = Decimal("0")
    avg_d = Decimal("0")
    pnl_d = Decimal("0")
    inc_d = Decimal("0")

    for t in sorted(txns, key=lambda x: (x.date or "", x.id or 0)):
        q = to_d(t.quantity)
        price = to_d(t.price)
        fee = to_d(t.fee)

        if t.action == TxnAction.buy:
            # 移动加权平均：新总成本 = 旧总成本 + 买入量×价 + 费用
            total_cost = d_sum(d_mul(qty_d, avg_d), d_mul(q, price), fee)
            qty_d += q
            avg_d = d_div(total_cost, qty_d) if qty_d > CLOSE_EPS_D else Decimal("0")
        elif t.action == TxnAction.sell:
            # 已实现盈亏 = 卖出量×(卖出价 - 均价) - 费用
            pnl_d += d_sub(d_mul(q, price), d_mul(q, avg_d)) - fee
            qty_d -= q
            if abs(qty_d) < CLOSE_EPS_D:
                qty_d = Decimal("0")
                avg_d = Decimal("0")
        elif t.action == TxnAction.dividend:
            inc_d += to_d(t.amount)

    # 转回 float 保持接口兼容
    st.quantity = to_float(qty_d, ndigits=10)
    st.avg_cost = to_float(avg_d, ndigits=10)
    st.realized_pnl = to_float(pnl_d, ndigits=10)
    st.realized_income = to_float(inc_d, ndigits=10)
    return st


def recompute_holding(session: Session, holding_id: int) -> None:
    """重放该持仓的全部流水并回写。manual 持仓直接跳过。"""
    holding = session.get(Holding, holding_id)
    if holding is None or holding.source != HoldingSource.derived:
        return
    txns = session.exec(
        select(Transaction).where(Transaction.holding_id == holding_id)
    ).all()
    st = replay_transactions(txns)
    holding.quantity = st.quantity
    holding.cost_price = st.avg_cost if abs(st.quantity) > float(CLOSE_EPS_D) else None
    holding.realized_pnl = st.realized_pnl
    holding.realized_income = st.realized_income
    holding.status = (
        HoldingStatus.closed if abs(st.quantity) < float(CLOSE_EPS_D) else HoldingStatus.open
    )
    session.add(holding)
    session.commit()


def resolve_derived_holding(
    session: Session,
    user: User,
    platform_id: Optional[int],
    symbol: str,
    currency: Currency,
    name: str = "",
    create_if_missing: bool = False,
) -> Optional[Holding]:
    """按 (user, platform, symbol, currency) 找 derived 持仓；
    create_if_missing 时不存在则新建一条。返回持仓或 None。"""
    if not symbol or platform_id is None:
        return None
    holding = session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.platform_id == platform_id,
            Holding.symbol == symbol,
            Holding.currency == currency,
            Holding.source == HoldingSource.derived,
        )
    ).first()
    if holding is None and create_if_missing:
        holding = Holding(
            user_id=user.id,
            platform_id=platform_id,
            currency=currency,
            symbol=symbol,
            name=name,
            source=HoldingSource.derived,
            status=HoldingStatus.open,
        )
        session.add(holding)
        session.commit()
        session.refresh(holding)
    return holding
