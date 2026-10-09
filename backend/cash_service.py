"""统一现金重算服务：按 (user, platform, currency) 从现金流水重放现金余额。

现金流语义（现金账本）：
- cash_adjust：现金校准/初始化，amount 为该时点的绝对余额（覆盖此前全部流水）
- deposit / withdraw：+amount / -amount（amount 缺失则取 quantity）
- dividend：+amount（实际到账）
- buy / sell：-(量×价+费) / +(量×价-费)；手填 amount 时按实际净额（不重复计费）
- adjust（持仓校准）/ other：无现金流

锚定规则：首笔卖出即开始追踪实际到账现金，无需先初始化。
在首笔卖出或显式现金记录之前的买入不扣现金（历史入金可能未录入）；其后按现金流累计。
cash_adjust 出现时把余额重置为绝对金额（后续校准），之前的流水被其覆盖、不重复计。

未追踪（只有历史买入）→ cash holding.manual_value = None，前端提示校准。
新增或扩大负余额在写入时按时间线拒绝；历史缺口允许校准修复，重算不截断负数。
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
        self.started = False                 # 已出现卖出或显式现金记录
        self.cash_adjust_count = 0
        self.last_anchor_date: Optional[str] = None


def replay_cash(
    txns: Iterable[Transaction], *, check_negative: bool = False,
    previous_txns: Optional[Iterable[Transaction]] = None,
) -> CashState:
    """按 (date, id) 升序重放现金流水，返回 CashState。

    check_negative=True 时拒绝负余额；升级前已存在的缺口允许保持或缩小，
    以便补录现金校准。新流水或移动日期产生的负余额仍拒绝。
    """
    st = CashState()
    previous_deficits = {
        (entry['id'], entry['date']): to_d(entry['balance'])
        for entry in cash_ledger(previous_txns or [])
        if entry['balance'] is not None and entry['balance'] < 0
    } if check_negative else {}
    for t in sorted(txns, key=lambda x: (x.date or "", x.id or 0)):
        if t.action == TxnAction.cash_adjust:
            st.balance = _explicit_amount(t)
            st.started = True
            st.cash_adjust_count += 1
            st.last_anchor_date = t.date
        elif t.action in (TxnAction.deposit, TxnAction.withdraw, TxnAction.dividend, TxnAction.sell):
            st.balance += cash_flow(t)
            st.started = True
        elif t.action == TxnAction.buy:
            if st.started:
                st.balance += cash_flow(t)
            # 现金开始追踪之前，不推测历史买入所用资金的来源。
        # adjust / other：无现金流

        if check_negative and st.balance < previous_deficits.get((t.id, t.date), Decimal('0')):
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


def rebuild_sale_cash(session: Session, user_id: Optional[int] = None) -> None:
    """升级/恢复备份时重建卖出现金投影；不修改流水，重复执行不会重复入账。

    不完整历史可能产生负余额，保留真实重放结果以便用户校准，不伪造入金。
    """
    stmt = select(Transaction.user_id, Transaction.platform_id, Transaction.currency).where(
        Transaction.action == TxnAction.sell,
        Transaction.platform_id.is_not(None),
    ).distinct()
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    for uid, pid, currency in session.exec(stmt).all():
        user = session.get(User, uid)
        if user is not None:
            recalc_cash(session, user, pid, currency)


def check_cash(
    session: Session,
    user: User,
    txn: Transaction,
    exclude_txn_id: Optional[int] = None,
    previous_txn: Optional[Transaction] = None,
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
    previous = list(txns)
    if previous_txn is not None and (previous_txn.platform_id, previous_txn.currency) == (txn.platform_id, txn.currency):
        previous.append(previous_txn)
    replay_cash([*txns, candidate], check_negative=True, previous_txns=previous)


def cash_ledger(txns: Iterable[Transaction]) -> list:
    """逐条现金流水：带符号 flow 与运行余额。开始追踪前的 buy 计 flow=None、余额为 None。

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
        elif t.action in (TxnAction.deposit, TxnAction.withdraw, TxnAction.dividend, TxnAction.sell):
            flow = cash_flow(t)
            balance += flow
            started = True
        elif t.action == TxnAction.buy:
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
