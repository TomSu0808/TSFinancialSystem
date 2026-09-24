"""统一现金重算服务：按 (user, platform, currency) 从现金流水重放现金余额。

现金流语义（现金账本）：
- cash_adjust：现金校准/初始化，amount 为该时点的绝对余额（覆盖此前全部流水）
- deposit / withdraw：+amount / -amount（amount 缺失则取 quantity）
- dividend：+amount（实际到账）
- buy / sell：-(量×价+费) / +(量×价-费)；手填 amount 时按实际净额（不重复计费）
- adjust（持仓校准）/ other：无现金流

锚定规则：在第一条「显式现金记录」（cash_adjust/deposit/withdraw/dividend）之前，
buy/sell 不参与计现金（避免把不完整的历史买卖当成真实现金）；其后按现金流累计。
cash_adjust 出现时把余额重置为绝对金额（后续校准），之前的流水被其覆盖、不重复计。

未初始化（无任何显式现金记录）→ cash holding.manual_value = None，前端提示初始化。
负余额在写入时按时间线校验拒绝，绝不在重算时用 max(balance, 0) 掩盖账目问题。
"""
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from decimal_utils import to_d, to_float
from models import Currency, Holding, HoldingSource, Transaction, TxnAction, User

# 参与现金账本的动作
CASH_ACTIONS = (
    TxnAction.cash_adjust,
    TxnAction.deposit,
    TxnAction.withdraw,
    TxnAction.dividend,
    TxnAction.buy,
    TxnAction.sell,
)
# 建立账户基线（让 buy/sell 开始计现金）的显式现金记录
EXPLICIT_CASH_ACTIONS = (
    TxnAction.cash_adjust,
    TxnAction.deposit,
    TxnAction.withdraw,
    TxnAction.dividend,
)

_ACTION_LABEL = {
    TxnAction.buy: "买入",
    TxnAction.sell: "卖出",
    TxnAction.deposit: "入金",
    TxnAction.withdraw: "出金",
    TxnAction.dividend: "分红/利息",
    TxnAction.cash_adjust: "现金校准",
}


def _explicit_amount(txn: Transaction) -> Decimal:
    """deposit/withdraw/dividend/cash_adjust 的金额：优先 amount，其次 quantity。"""
    amt = txn.amount
    if amt is None or amt <= 0:
        amt = txn.quantity
    return to_d(amt or 0.0)


def _trade_net(txn: Transaction) -> Decimal:
    """buy/sell 的净现金流（正数）：手填 amount 为实际净额，否则 量×价 ± 费。"""
    if txn.amount is not None:
        return to_d(txn.amount)
    gross = to_d(txn.quantity) * to_d(txn.price)
    fee = to_d(txn.fee)
    return gross + fee if txn.action == TxnAction.buy else gross - fee


def cash_flow(txn: Transaction) -> Optional[Decimal]:
    """返回该交易的带符号现金流；无现金流的动作返回 None。

    cash_adjust 是绝对金额（特殊处理），这里返回 None。
    """
    if txn.action == TxnAction.deposit:
        return _explicit_amount(txn)
    if txn.action == TxnAction.withdraw:
        return -_explicit_amount(txn)
    if txn.action == TxnAction.dividend:
        return _explicit_amount(txn)
    if txn.action == TxnAction.buy:
        return -_trade_net(txn)
    if txn.action == TxnAction.sell:
        return _trade_net(txn)
    return None  # cash_adjust / adjust / other


class CashState:
    def __init__(self) -> None:
        self.balance = Decimal("0")
        self.started = False                 # 已出现显式现金记录（此后 buy/sell 计入）
        self.cash_adjust_count = 0
        self.last_anchor_date: Optional[str] = None


def replay_cash(txns: Iterable[Transaction], *, check_negative: bool = False) -> CashState:
    """按 (date, id) 升序重放现金流水，返回 CashState。

    check_negative=True 时，任一中间时点余额为负即抛 HTTPException(400)。
    """
    st = CashState()
    for t in sorted(txns, key=lambda x: (x.date or "", x.id or 0)):
        if t.action == TxnAction.cash_adjust:
            st.balance = _explicit_amount(t)
            st.started = True
            st.cash_adjust_count += 1
            st.last_anchor_date = t.date
        elif t.action in (TxnAction.deposit, TxnAction.withdraw, TxnAction.dividend):
            st.balance += cash_flow(t)
            st.started = True
        elif t.action in (TxnAction.buy, TxnAction.sell):
            if st.started:
                st.balance += cash_flow(t)
            # 首条显式现金记录之前：历史买卖被锚定覆盖，不参与计现金
        # adjust / other：无现金流

        if check_negative and st.balance < 0:
            label = _ACTION_LABEL.get(t.action, "交易")
            if t.action == TxnAction.withdraw:
                msg = f"{t.date} 出金后现金余额为 {to_float(st.balance)}，超过当前现金余额"
            else:
                msg = (f"{t.date} {label}后现金余额为 {to_float(st.balance)}，现金余额不足；"
                       f"请先校准/初始化现金余额，或检查是否漏记入金")
            raise HTTPException(400, msg)
    return st


def recalc_cash(
    session: Session,
    user: User,
    platform_id: int,
    currency: Currency,
) -> Optional[Holding]:
    """按 (user, platform, currency) 从现金流水重算现金余额并回写 cash holding。

    未初始化时把已有 cash holding 的 manual_value 置 None（不删除），不新建；
    已初始化时按余额回写（不 clamp）。只 flush，由调用方统一提交。
    """
    txns = session.exec(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.platform_id == platform_id,
            Transaction.currency == currency,
            Transaction.action.in_(CASH_ACTIONS),
        )
    ).all()
    st = replay_cash(txns)

    cash = session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.platform_id == platform_id,
            Holding.currency == currency,
            Holding.asset_type == "cash",
            Holding.source == HoldingSource.derived,
        )
    ).first()

    if not st.started:
        if cash is None:
            return None
        cash.manual_value = None
        cash.price_updated_at = datetime.utcnow()
        session.add(cash)
        session.flush()
        return cash

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

    cash.manual_value = to_float(st.balance)
    cash.price_updated_at = datetime.utcnow()
    session.add(cash)
    session.flush()
    return cash


def get_cash_balance(
    session: Session,
    user: User,
    platform_id: int,
    currency: Currency,
) -> float:
    """按流水重放得到现金余额（只读，不修改 DB）。未初始化返回 0.0。"""
    txns = session.exec(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.platform_id == platform_id,
            Transaction.currency == currency,
            Transaction.action.in_(CASH_ACTIONS),
        )
    ).all()
    st = replay_cash(txns)
    return to_float(st.balance) if st.started else 0.0


def check_cash(
    session: Session,
    user: User,
    txn: Transaction,
    exclude_txn_id: Optional[int] = None,
) -> None:
    """按时间线校验现金：把候选交易并入现有流水重放，任一中间时点负余额即拒绝。

    镜像 position._check_oversell：候选交易未入库时给它一个临时 id 参与同日排序。
    """
    if txn.action not in CASH_ACTIONS:
        return
    if txn.platform_id is None or txn.currency is None:
        return
    with session.no_autoflush:
        txns = session.exec(select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.platform_id == txn.platform_id,
            Transaction.currency == txn.currency,
            Transaction.action.in_(CASH_ACTIONS),
            Transaction.id != exclude_txn_id if exclude_txn_id is not None else True,
        )).all()
    max_id = max((t.id or 0 for t in txns), default=0)
    candidate = txn.model_copy(update={"id": txn.id or (max_id + 1)})
    replay_cash([*txns, candidate], check_negative=True)


def cash_ledger(txns: Iterable[Transaction]) -> list:
    """逐条现金流水：带符号 flow 与运行余额。未初始化期间的 buy/sell 计 flow=None、余额为 None。

    cash_adjust 的 flow 记其绝对余额（语义为「校准至 X」）。
    """
    entries = []
    balance = Decimal("0")
    started = False
    for t in sorted(txns, key=lambda x: (x.date or "", x.id or 0)):
        flow = None
        if t.action == TxnAction.cash_adjust:
            balance = _explicit_amount(t)
            started = True
            flow = balance
        elif t.action in (TxnAction.deposit, TxnAction.withdraw, TxnAction.dividend):
            flow = cash_flow(t)
            balance += flow
            started = True
        elif t.action in (TxnAction.buy, TxnAction.sell):
            if started:
                flow = cash_flow(t)
                balance += flow
        entries.append({
            "id": t.id,
            "date": t.date,
            "action": t.action.value,
            "symbol": t.symbol,
            "name": t.name,
            "currency": t.currency.value,
            "quantity": t.quantity,
            "price": t.price,
            "fee": t.fee,
            "amount": t.amount,
            "flow": to_float(flow) if flow is not None else None,
            "balance": to_float(balance) if started else None,
            "note": t.note,
        })
    return entries
