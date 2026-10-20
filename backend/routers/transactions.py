"""交易及持仓校准记录增删改查，按用户隔离并驱动持仓重算。"""
import csv
import io
from datetime import datetime as _dt
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_
from sqlmodel import Session, select

from auth import get_current_user
from cash_service import (
    CASH_ACTIONS, cash_transactions, check_cash, recalc_cash, replay_cash,
    settlement_currency,
)
from database import get_session
from fx_utils import rate_between
from models import (
    Currency,
    Holding,
    HoldingSource,
    Platform,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    TxnAction,
    User,
)
from position import (recompute_holding, resolve_derived_holding, replay_transactions,
                      resolve_position, opening_transaction, prepare_position)
from transaction_validation import validate_transaction

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


def _check_oversell(
    session: Session,
    user: User,
    txn: Transaction,
    exclude_txn_id: Optional[int] = None,
) -> None:
    """按时间线检查校准及买卖；移动交易时也检查原持仓。"""
    actions = (TxnAction.buy, TxnAction.sell, TxnAction.adjust)
    holding = resolve_position(session, user, txn) if txn.action in actions else None
    with session.no_autoflush:
        if txn.holding_id is not None and (holding is None or txn.holding_id != holding.id):
            old_txns = session.exec(select(Transaction).where(
                Transaction.holding_id == txn.holding_id,
                Transaction.id != exclude_txn_id,
            )).all()
            replay_transactions(old_txns, check_oversell=True)
        if txn.action not in actions:
            return
        if holding is None and txn.action == TxnAction.sell:
            raise HTTPException(400, "尚无可用持仓，请先在交易记录中选择「持仓校准」，填入卖出前数量。")
        if holding is not None and holding.source == HoldingSource.derived:
            txns = session.exec(select(Transaction).where(
                Transaction.holding_id == holding.id,
                Transaction.id != exclude_txn_id if exclude_txn_id is not None else True,
            )).all()
        elif holding is not None and txn.action != TxnAction.adjust:
            txns = [opening_transaction(holding, txn.date, before_existing=txn.id is not None)]
        else:
            txns = []
        candidate = txn.model_copy(update={"id": txn.id or (max((t.id or 0 for t in txns), default=0) + 1)})
        replay_transactions([*txns, candidate], check_oversell=True)


def _sync_txn_holding(session: Session, txn: Transaction, user: User) -> None:
    """(重新)绑定 buy/sell/adjust/dividend 流水并重算受影响的持仓。
    买入及校准可自动建仓；卖出/分红绑定已有持仓。改了 symbol/platform/currency
    会重绑到新持仓，新旧持仓都会重算。非持仓动作清空 holding_id，避免悬空 FK。

    deposit / withdraw / cash_adjust / buy / sell / dividend 通过 cash_service.recalc_cash
    统一重算现金余额（现金与持仓在同一 DB 事务内，幂等）。
    """
    affected = set()
    if txn.holding_id is not None:
        affected.add(txn.holding_id)  # 旧绑定总要重算（动作/标的变更后释放其影响）
    if txn.action in (TxnAction.buy, TxnAction.sell, TxnAction.adjust, TxnAction.dividend):
        holding = resolve_derived_holding(
            session, user, txn.platform_id, txn.symbol, txn.currency,
            name=txn.name, create_if_missing=(txn.action in (TxnAction.buy, TxnAction.adjust)),
        )
        if holding is not None:
            if txn.holding_id != holding.id:
                txn.holding_id = holding.id
                session.add(txn)
                session.flush()
            affected.add(holding.id)
        elif txn.holding_id is not None:
            txn.holding_id = None
            session.add(txn)
            session.flush()
    else:
        # deposit / withdraw / cash_adjust / other：非持仓动作，清空 holding_id
        if txn.holding_id is not None:
            affected.add(txn.holding_id)  # 原 buy/sell 重算
            txn.holding_id = None
            session.add(txn)
            session.flush()
    # 卖出自动进入现金账本；现金相关动作按结算币种统一重算。
    if txn.action in CASH_ACTIONS and txn.platform_id is not None and txn.currency is not None:
        recalc_cash(session, user, txn.platform_id, settlement_currency(txn))
    for hid in affected:
        recompute_holding(session, hid)


def _normalize_settlement(session: Session, txn: Transaction) -> None:
    """规范结算币种：仅买卖/分红可用；同币种清空；缺汇率时按缓存汇率折算并存档。

    港股通：currency=HKD（报价/持仓），cash_currency=CNY（现金收付），
    fx_rate 表示 1 HKD 折合多少 CNY。
    """
    if txn.action not in (TxnAction.buy, TxnAction.sell, TxnAction.dividend):
        txn.cash_currency = None
        txn.fx_rate = None
        return
    if txn.cash_currency is None or txn.cash_currency == txn.currency:
        txn.cash_currency = None
        txn.fx_rate = None
        return
    if txn.fx_rate is None:
        txn.fx_rate = round(rate_between(session, txn.currency, txn.cash_currency), 10)


# ─── CSV import helpers ───────────────────────────────────────────────────────

def _platforms_by_name(session: Session, user: User) -> dict:
    return {
        p.name: p.id
        for p in session.exec(select(Platform).where(Platform.user_id == user.id)).all()
    }


def _parse_csv_bytes(data: bytes) -> list:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _validate_row(row_num: int, row: dict, plat_map: dict) -> tuple:
    """校验单行 CSV，返回 (errors, data_dict)；有错误时 data_dict 为 None。"""
    errors: list = []
    d: dict = {}

    # date
    date_str = (row.get("date") or "").strip()
    if not date_str:
        errors.append("date 不能为空")
    else:
        try:
            _dt.strptime(date_str, "%Y-%m-%d")
            d["date"] = date_str
        except ValueError:
            errors.append(f"date 格式错误（应为 YYYY-MM-DD）：{date_str}")

    # action
    action_str = (row.get("action") or "").strip().lower()
    if not action_str:
        errors.append("action 不能为空")
    else:
        try:
            d["action"] = TxnAction(action_str)
        except ValueError:
            errors.append(f"action 无效：{action_str}，可选：buy/sell/adjust/dividend/deposit/withdraw/cash_adjust/other")

    # platform（可选；若填写必须匹配当前用户的平台名称）
    plat_str = (row.get("platform") or "").strip()
    if plat_str:
        if plat_str not in plat_map:
            errors.append(f"平台「{plat_str}」不存在，请先在账户管理中创建")
        else:
            d["platform_id"] = plat_map[plat_str]
    else:
        d["platform_id"] = None

    # currency
    cur_str = (row.get("currency") or "").strip().upper() or "CNY"
    try:
        d["currency"] = Currency(cur_str)
    except ValueError:
        errors.append(f"currency 无效：{cur_str}，可选：CNY/USD/HKD")

    # cash_currency（结算币种，可选；港股通填 CNY）
    cash_str = (row.get("cash_currency") or "").strip().upper()
    if cash_str:
        try:
            d["cash_currency"] = Currency(cash_str)
        except ValueError:
            errors.append(f"cash_currency 无效：{cash_str}，可选：CNY/USD/HKD")
    else:
        d["cash_currency"] = None

    fx_str = (row.get("fx_rate") or "").strip()
    if fx_str:
        try:
            d["fx_rate"] = float(fx_str)
        except ValueError:
            errors.append(f"fx_rate 不是有效数字：{fx_str}")
    else:
        d["fx_rate"] = None

    # 文本字段
    d["name"] = (row.get("name") or "").strip()
    d["symbol"] = (row.get("symbol") or "").strip()
    note = (row.get("note") or "").strip()
    d["note"] = note or None

    # 数字字段
    for field in ("quantity", "price", "fee", "amount"):
        val = (row.get(field) or "").strip()
        if val:
            try:
                d[field] = float(val)
            except ValueError:
                errors.append(f"{field} 不是有效数字：{val}")
        else:
            d[field] = None

    return errors, (None if errors else d)


def _build_preview(rows_raw: list, plat_map: dict, holdings_state: Optional[dict] = None) -> tuple:
    """返回 (preview_dict, all_valid_rows_data)。preview_dict 的 rows 最多 100 行。

    holdings_state: {(platform_id, symbol, currency): quantity} 用于检测超卖。
    """
    total = len(rows_raw)
    result_rows = []
    valid_count = 0
    error_count = 0
    all_data: list = []

    # 跟踪导入期间的模拟仓位变动（仅在同一次导入内）
    running_positions: dict = {}

    def _get_available(platform_id, symbol, currency_str):
        """返回某标的的可用数量（DB + 本次导入已处理的变动）。"""
        key = (platform_id, symbol, currency_str)
        base = (holdings_state or {}).get(key, 0.0) if holdings_state else 0.0
        return base + running_positions.get(key, 0.0)

    for i, row in enumerate(rows_raw, 1):
        errors, data = _validate_row(i, row, plat_map)
        if errors:
            error_count += 1
        else:
            valid_count += 1
            # 超卖检测：sell 数量不得超过可用数量
            if data.get("action") == TxnAction.adjust and data.get("quantity") is not None:
                key = (data.get("platform_id"), data.get("symbol", ""), str(data.get("currency", Currency.CNY)))
                base = (holdings_state or {}).get(key, 0.0)
                running_positions[key] = data["quantity"] - base
            elif data.get("action") == TxnAction.sell and data.get("quantity") is not None:
                cur_str = str(data.get("currency", Currency.CNY))
                avail = _get_available(
                    data.get("platform_id"),
                    data.get("symbol", ""),
                    cur_str,
                )
                sell_qty = data["quantity"]
                if sell_qty > avail + 1e-9:
                    errors = [f"超卖：卖出 {sell_qty} 超过可用 {avail}"]
                    error_count += 1
                    valid_count -= 1
                    all_data.append(data)  # still include for preview display
                    if i <= 100:
                        result_rows.append({
                            "row_number": i,
                            "valid": False,
                            "data": data,
                            "errors": errors,
                        })
                    continue
                # 更新运行仓位
                key = (data.get("platform_id"), data.get("symbol", ""), cur_str)
                running_positions[key] = running_positions.get(key, 0.0) - sell_qty
            elif data.get("action") == TxnAction.buy and data.get("quantity") is not None:
                key = (data.get("platform_id"), data.get("symbol", ""),
                       str(data.get("currency", Currency.CNY)))
                running_positions[key] = running_positions.get(key, 0.0) + data["quantity"]
            all_data.append(data)
        if i <= 100:
            result_rows.append({
                "row_number": i,
                "valid": not bool(errors),
                "data": data,
                "errors": errors,
            })

    preview = {
        "total_rows": total,
        "valid_rows": valid_count,
        "error_rows": error_count,
        "rows": result_rows,
    }
    return preview, all_data


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[Transaction])
def list_transactions(
    platform_id: Optional[int] = Query(None),
    action: Optional[TxnAction] = Query(None),
    currency: Optional[Currency] = Query(None),
    keyword: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if platform_id is not None:
        stmt = stmt.where(Transaction.platform_id == platform_id)
    if action is not None:
        stmt = stmt.where(Transaction.action == action)
    if currency is not None:
        stmt = stmt.where(Transaction.currency == currency)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Transaction.name.like(kw),
                Transaction.symbol.like(kw),
                Transaction.note.like(kw),
            )
        )
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
    _normalize_settlement(session, txn)
    # 统一校验
    validate_transaction(
        session, user,
        action=txn.action,
        platform_id=txn.platform_id,
        currency=txn.currency,
        cash_currency=txn.cash_currency,
        fx_rate=txn.fx_rate,
        symbol=txn.symbol,
        name=txn.name,
        quantity=txn.quantity,
        price=txn.price,
        fee=txn.fee,
        amount=txn.amount,
        date=txn.date,
    )
    _check_oversell(session, user, txn)  # 禁止超卖
    check_cash(session, user, txn)  # 现金时间线校验：出金/买入不能导致负余额
    prepare_position(session, user, txn)
    session.add(txn)
    session.flush()
    _sync_txn_holding(session, txn, user)
    session.commit()
    session.refresh(txn)
    return txn


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    plat_map = _platforms_by_name(session, user)

    # 交易驱动及按数量维护的手填持仓均可卖出
    holdings_state = {
        (h.platform_id, h.symbol, str(h.currency)): (h.quantity or 0.0)
        for h in session.exec(
            select(Holding).where(
                Holding.user_id == user.id,
                Holding.manual_value.is_(None),
            )
        ).all()
    }

    try:
        rows_raw = _parse_csv_bytes(contents)
    except Exception as e:
        raise HTTPException(400, f"CSV 解析失败：{e}")
    preview, _ = _build_preview(rows_raw, plat_map, holdings_state)
    return preview


@router.post("/import/commit")
async def commit_import(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    plat_map = _platforms_by_name(session, user)

    # 按数量维护的手填持仓也可作为卖出起点
    holdings_state = {
        (h.platform_id, h.symbol, str(h.currency)): (h.quantity or 0.0)
        for h in session.exec(
            select(Holding).where(
                Holding.user_id == user.id,
                Holding.manual_value.is_(None),
            )
        ).all()
    }

    try:
        rows_raw = _parse_csv_bytes(contents)
    except Exception as e:
        raise HTTPException(400, f"CSV 解析失败：{e}")
    preview, all_data = _build_preview(rows_raw, plat_map, holdings_state)

    if preview["error_rows"] > 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"存在 {preview['error_rows']} 行错误，已取消导入",
                **preview,
            },
        )

    imported = 0
    for d in all_data:
        tc = TransactionCreate(**d)
        txn = Transaction.model_validate(tc, update={"user_id": user.id})
        txn.holding_id = None
        _normalize_settlement(session, txn)
        # 统一校验
        try:
            validate_transaction(
                session, user,
                action=txn.action,
                platform_id=txn.platform_id,
                currency=txn.currency,
                cash_currency=txn.cash_currency,
                fx_rate=txn.fx_rate,
                symbol=txn.symbol,
                name=txn.name,
                quantity=txn.quantity,
                price=txn.price,
                fee=txn.fee,
                amount=txn.amount,
                date=txn.date,
            )
        except HTTPException:
            raise  # 向上传播校验错误
        _check_oversell(session, user, txn)  # CSV 导入也禁止超卖
        check_cash(session, user, txn)  # 现金时间线校验
        prepare_position(session, user, txn)
        session.add(txn)
        session.flush()
        _sync_txn_holding(session, txn, user)
        imported += 1

    session.commit()
    return {"imported": imported}


@router.put("/{txn_id}", response_model=Transaction)
def update_transaction(
    txn_id: int,
    data: TransactionUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    txn = _owned(session, txn_id, user)
    old_platform_id = txn.platform_id
    old_cash_currency = settlement_currency(txn)
    old_action = txn.action
    previous_txn = txn.model_copy()
    values = data.model_dump(exclude_unset=True)
    values.pop("holding_id", None)  # holding_id is system-managed; ignore client input
    if "platform_id" in values:
        _check_platform(session, values["platform_id"], user)
    for key, value in values.items():
        setattr(txn, key, value)
    _normalize_settlement(session, txn)
    new_cash_currency = settlement_currency(txn)

    # 统一校验（合并后的字段）
    validate_transaction(
        session, user,
        action=txn.action,
        platform_id=txn.platform_id,
        currency=txn.currency,
        cash_currency=txn.cash_currency,
        fx_rate=txn.fx_rate,
        symbol=txn.symbol,
        name=txn.name,
        quantity=txn.quantity,
        price=txn.price,
        fee=txn.fee,
        amount=txn.amount,
        date=txn.date,
        exclude_txn_id=txn_id,
    )
    _check_oversell(session, user, txn, exclude_txn_id=txn_id)  # 禁止超卖
    check_cash(session, user, txn, exclude_txn_id=txn_id, previous_txn=previous_txn)
    prepare_position(session, user, txn)
    session.add(txn)
    session.flush()
    _sync_txn_holding(session, txn, user)
    # 移出旧现金账户或改成非现金动作时，撤销旧现金影响并验证余额。
    if (old_action in CASH_ACTIONS
            and ((old_platform_id, old_cash_currency) != (txn.platform_id, new_cash_currency)
                 or txn.action not in CASH_ACTIONS)
            and old_platform_id is not None and old_cash_currency is not None):
        with session.no_autoflush:
            old_cash_txns = cash_transactions(
                session, user.id, old_platform_id, old_cash_currency, exclude_txn_id=txn_id,
            )
        replay_cash(old_cash_txns, check_negative=True, previous_txns=[*old_cash_txns, previous_txn])
        recalc_cash(session, user, old_platform_id, old_cash_currency)
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
    holding_id = txn.holding_id
    action = txn.action
    platform_id = txn.platform_id
    currency = settlement_currency(txn)
    if holding_id is not None:
        remaining = session.exec(select(Transaction).where(
            Transaction.holding_id == holding_id, Transaction.id != txn_id,
        )).all()
        replay_transactions(remaining, check_oversell=True)
    # 现金时间线校验：删除后（剔除自身）任一中间时点负余额即拒绝
    if action in CASH_ACTIONS and platform_id is not None and currency is not None:
        with session.no_autoflush:
            remaining_cash = cash_transactions(
                session, user.id, platform_id, currency, exclude_txn_id=txn_id,
            )
        replay_cash(remaining_cash, check_negative=True, previous_txns=[*remaining_cash, txn])
    session.delete(txn)
    session.flush()
    if holding_id is not None:
        recompute_holding(session, holding_id)
    # 删除现金相关动作后重算现金
    if action in CASH_ACTIONS and platform_id is not None and currency is not None:
        recalc_cash(session, user, platform_id, currency)
    session.commit()
    return {"ok": True}
