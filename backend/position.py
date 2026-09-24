"""持仓派生计算：交易流水驱动 derived 持仓的数量 / 移动加权成本 / 已实现盈亏。

设计：纯逻辑 replay_transactions（无副作用，便于单测）与带 DB 副作用的
recompute_holding 分离。详见 docs/superpowers/specs/2026-06-15-transaction-driven-holdings-design.md

精度：核心计算使用 Decimal 避免二进制浮点累积误差（如 0.1 + 0.2）。
"""
from decimal import Decimal
from datetime import date as Date, timedelta
from typing import Iterable, Optional

from fastapi import HTTPException
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
        self.realized_pnl_incomplete = False


def replay_transactions(txns: Iterable[Transaction], *, check_oversell: bool = False) -> PositionState:
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

        if t.action == TxnAction.adjust:
            qty_d = q
            avg_d = (price if t.price is not None else None) if q > CLOSE_EPS_D else Decimal("0")
        elif t.action == TxnAction.buy:
            # 移动加权平均：新总成本 = 旧总成本 + 买入量×价 + 费用
            total_cost = (d_sum(d_mul(qty_d, avg_d), d_mul(q, price), fee)
                          if avg_d is not None else None)
            qty_d += q
            avg_d = (d_div(total_cost, qty_d) if total_cost is not None else None) if qty_d > CLOSE_EPS_D else Decimal("0")
        elif t.action == TxnAction.sell:
            if check_oversell and q > qty_d + CLOSE_EPS_D:
                raise HTTPException(400, f"{t.date} 卖出数量（{q}）超过可用持仓（{qty_d}）。如有漏记买入，请先校准卖出前的持仓数量。")
            # 已实现盈亏 = 卖出量×(卖出价 - 均价) - 费用
            if avg_d is None:
                st.realized_pnl_incomplete = True
            else:
                pnl_d += d_sub(d_mul(q, price), d_mul(q, avg_d)) - fee
            qty_d -= q
            if abs(qty_d) < CLOSE_EPS_D:
                qty_d = Decimal("0")
                avg_d = Decimal("0")
        elif t.action == TxnAction.dividend:
            inc_d += to_d(t.amount)

    # 转回 float 保持接口兼容
    st.quantity = to_float(qty_d, ndigits=10)
    st.avg_cost = to_float(avg_d, ndigits=10) if avg_d is not None else None
    st.realized_pnl = to_float(pnl_d, ndigits=10)
    st.realized_income = to_float(inc_d, ndigits=10)
    return st


def recompute_holding(session: Session, holding_id: int) -> None:
    """重放流水并回写；manual 跳过。只 flush，由调用方统一提交交易。"""
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
    holding.realized_pnl_incomplete = st.realized_pnl_incomplete
    holding.realized_income = st.realized_income
    holding.status = (
        HoldingStatus.closed if abs(st.quantity) < float(CLOSE_EPS_D) else HoldingStatus.open
    )
    session.add(holding)
    session.flush()


def resolve_position(session: Session, user: User, txn: Transaction) -> Optional[Holding]:
    """交易身份只匹配一个持仓；同标的多个手填/流水持仓不能猜测或合并。"""
    if not txn.symbol or txn.platform_id is None:
        return None
    with session.no_autoflush:
        matches = session.exec(select(Holding).where(
            Holding.user_id == user.id, Holding.platform_id == txn.platform_id,
            Holding.symbol == txn.symbol, Holding.currency == txn.currency,
        )).all()
    if len(matches) > 1:
        raise HTTPException(400, "该平台存在多个同代码、同币种持仓，请先整理重复持仓后再记交易或校准。")
    return matches[0] if matches else None


def opening_transaction(holding: Holding, date: str, *, before_existing: bool = False) -> Transaction:
    """把手填数量和成本保存为期初事实，避免伪造买入或重复计算投入成本。"""
    quantity = holding.quantity or 0.0
    cost = holding.cost_price
    if holding.cost_value is not None and quantity > 0:
        cost = holding.cost_value / quantity
    if before_existing:
        # 编辑旧流水时其 ID 比新建期初记录小，需把期初放在前一日。
        day = Date.fromisoformat(date)
        if day == Date.min:
            raise HTTPException(400, "无法在最早日期前建立期初持仓，请调整交易日期。")
        date = (day - timedelta(days=1)).isoformat()
    return Transaction(
        user_id=holding.user_id, platform_id=holding.platform_id, holding_id=holding.id,
        date=date, action=TxnAction.adjust, symbol=holding.symbol, name=holding.name,
        currency=holding.currency, quantity=quantity, price=cost,
        note="期初持仓：由手填持仓转入，不产生现金流；数量为当次交易前持仓。",
    )


def prepare_position(session: Session, user: User, txn: Transaction) -> None:
    """在交易入库前保存手填持仓的期初状态，与本次交易一起提交。"""
    if txn.action not in (TxnAction.buy, TxnAction.sell, TxnAction.adjust):
        return
    holding = resolve_position(session, user, txn)
    if holding is None or holding.source == HoldingSource.derived:
        return
    if holding.manual_value is not None or holding.asset_type == "cash":
        raise HTTPException(400, "该资产按金额维护，请先改为按数量和现价维护，再校准持仓。")
    if txn.action != TxnAction.adjust:
        if holding.quantity is None or holding.quantity < 0:
            raise HTTPException(400, "该持仓尚无有效数量，请先校准持仓数量。")
        session.add(opening_transaction(holding, txn.date, before_existing=txn.id is not None))
        session.flush()  # 同日先期初校准、后本次买卖
    holding.source = HoldingSource.derived
    holding.cost_value = None
    session.add(holding)


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
    create_if_missing 时不存在则新建一条。只 flush，由调用方提交。返回持仓或 None。"""
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
        session.flush()
        session.refresh(holding)
    return holding
