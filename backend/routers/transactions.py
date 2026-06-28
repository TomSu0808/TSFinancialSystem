"""交易流水增删改查（独立账本，不自动改持仓；按用户隔离）。"""
import csv
import io
from datetime import datetime as _dt
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Currency,
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
        if txn.holding_id is not None:
            txn.holding_id = None
            session.add(txn)
            session.commit()
    for hid in affected:
        recompute_holding(session, hid)


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
            errors.append(f"action 无效：{action_str}，可选：buy/sell/dividend/deposit/withdraw/other")

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


def _build_preview(rows_raw: list, plat_map: dict) -> tuple:
    """返回 (preview_dict, all_valid_rows_data)。preview_dict 的 rows 最多 100 行。"""
    total = len(rows_raw)
    result_rows = []
    valid_count = 0
    error_count = 0
    all_data: list = []

    for i, row in enumerate(rows_raw, 1):
        errors, data = _validate_row(i, row, plat_map)
        if errors:
            error_count += 1
        else:
            valid_count += 1
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
    session.add(txn)
    session.commit()
    session.refresh(txn)
    _sync_txn_holding(session, txn, user)
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
    try:
        rows_raw = _parse_csv_bytes(contents)
    except Exception as e:
        raise HTTPException(400, f"CSV 解析失败：{e}")
    preview, _ = _build_preview(rows_raw, plat_map)
    return preview


@router.post("/import/commit")
async def commit_import(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    contents = await file.read()
    plat_map = _platforms_by_name(session, user)
    try:
        rows_raw = _parse_csv_bytes(contents)
    except Exception as e:
        raise HTTPException(400, f"CSV 解析失败：{e}")
    preview, all_data = _build_preview(rows_raw, plat_map)

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
        session.add(txn)
        session.commit()
        session.refresh(txn)
        _sync_txn_holding(session, txn, user)
        imported += 1

    return {"imported": imported}


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
