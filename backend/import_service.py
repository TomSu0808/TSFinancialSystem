"""导入编排层：preview / commit / 去重。

导入流程：
1. preview: 解析文件 → 字段映射 → 行校验 → 存 ImportSession → 返回预览
2. commit: 加载 session → 逐行写 Transaction → 触发持仓重算 → 返回结果
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from importers import BROKER_IMPORTERS, BaseImporter, ImportedTransactionDraft
from models import (
    Currency,
    Holding,
    HoldingSource,
    ImportSession,
    Platform,
    Transaction,
    TransactionCreate,
    TxnAction,
    User,
)
from position import recompute_holding, resolve_derived_holding


def _platforms_by_name(session: Session, user: User) -> dict:
    """当前用户平台名称 → id。"""
    return {
        p.name: p.id
        for p in session.exec(
            select(Platform).where(Platform.user_id == user.id)
        ).all()
    }


def _get_or_create_importer(broker_type: str, mapping: Optional[Dict[str, str]] = None) -> BaseImporter:
    """获取指定类型的导入器实例。"""
    if broker_type not in BROKER_IMPORTERS:
        # Fallback to generic
        from importers.generic import GenericImporter
        return GenericImporter(mapping)

    importer_cls = BROKER_IMPORTERS[broker_type]
    if broker_type == "generic" and mapping is not None:
        return importer_cls(mapping)
    return importer_cls()


def _existing_txn_hashes(session: Session, user: User) -> set:
    """获取当前用户所有已导入交易的 normalized hash 集合（用于去重）。"""
    # We store the hash in the note field for import-created transactions
    # or we compute on the fly from existing transactions
    # For efficiency, we compute hashes from existing transactions
    txns = session.exec(
        select(Transaction).where(Transaction.user_id == user.id)
    ).all()

    hashes = set()
    for t in txns:
        parts = [
            (t.symbol or "").strip().upper(),
            str(t.currency or ""),
            (t.date or "").strip(),
            str(t.action or ""),
        ]
        for v in (t.quantity, t.price, t.amount):
            if v is not None:
                parts.append(f"{v:.6f}")
            else:
                parts.append("")
        import hashlib
        raw = "|".join(parts).encode("utf-8")
        hashes.add(hashlib.sha256(raw).hexdigest())
    return hashes


def preview_import(
    session: Session,
    user: User,
    broker_type: str,
    file_data: bytes,
    file_name: str,
    platform_id: Optional[int] = None,
    user_mapping: Optional[Dict[str, str]] = None,
) -> dict:
    """解析文件并生成预览。

    Returns:
        {import_session_id, detected_fields, rows, summary}
    """
    importer = _get_or_create_importer(broker_type, user_mapping)
    drafts = importer.parse(file_data, file_name)

    if not drafts:
        return {"error": "文件中没有可解析的数据行"}

    # 自动检测字段映射
    detected_fields = {}
    if hasattr(importer, 'detect_fields') and drafts:
        # 从第一个 draft 的 raw_payload 获取 headers
        first = drafts[0]
        if first.raw_payload:
            detected_fields = importer.detect_fields(list(first.raw_payload.keys()))

    # 加载平台映射和持仓状态（用于超卖检测）
    plat_map = _platforms_by_name(session, user)
    holdings_state = {
        (h.platform_id, h.symbol, str(h.currency)): (h.quantity or 0.0)
        for h in session.exec(
            select(Holding).where(
                Holding.user_id == user.id,
                Holding.source == HoldingSource.derived,
            )
        ).all()
    }

    # 加载已有交易哈希用于去重
    existing_hashes = _existing_txn_hashes(session, user)

    # 逐行处理
    preview_rows = []
    running_positions: dict = {}  # (pid, symbol, currency) -> cumulative qty change
    summary = {"valid": 0, "error": 0, "warning": 0, "duplicate": 0, "total": 0}

    # 推导 platform_id
    effective_platform_id = platform_id

    for d in drafts:
        row_entry = {
            "row_number": d.row_number,
            "status": d.status,
            "data": {
                "date": d.date,
                "action": d.action,
                "name": d.name,
                "symbol": d.symbol,
                "currency": d.currency,
                "market": d.market,
                "quantity": d.quantity,
                "price": d.price,
                "fee": d.fee,
                "amount": d.amount,
            },
            "warnings": d.warnings.copy(),
            "errors": d.errors.copy(),
            "hash": d.normalized_hash(),
        }

        if d.status == "error":
            summary["error"] += 1
            preview_rows.append(row_entry)
            summary["total"] += 1
            continue

        # 已跳过 status=error，下面都是 valid/warning
        # 确定 platform_id
        # 尝试从 draft 推断平台（如果 draft 中有原始列叫 platform/平台）
        pid = effective_platform_id
        if pid is None and d.raw_payload:
            plat_name = (d.raw_payload.get("platform") or
                         d.raw_payload.get("Platform") or
                         d.raw_payload.get("平台") or "").strip()
            if plat_name and plat_name in plat_map:
                pid = plat_map[plat_name]
        row_entry["resolved_platform_id"] = pid

        # 校验 platform 归属
        if pid is not None:
            plat = session.get(Platform, pid)
            if plat is None or plat.user_id != user.id:
                d.errors.append(f"平台 {pid} 不存在或不属于当前用户")
                d.status = "error"
                row_entry["status"] = "error"
                row_entry["errors"] = d.errors
                summary["error"] += 1
                preview_rows.append(row_entry)
                summary["total"] += 1
                continue

        # 超卖检测
        if d.action == "sell" and d.quantity is not None and pid is not None:
            pos_key = (pid, d.symbol, str(d.currency))
            base_qty = holdings_state.get(pos_key, 0.0)
            running_delta = running_positions.get(pos_key, 0.0)
            available = base_qty + running_delta
            if d.quantity > available + 1e-9:
                d.errors.append(f"超卖：卖出 {d.quantity} 超过可用 {available}")
                d.status = "error"
                row_entry["status"] = "error"
                row_entry["errors"] = d.errors
                summary["error"] += 1
                preview_rows.append(row_entry)
                summary["total"] += 1
                continue
            # 更新 running positions
            running_positions[pos_key] = running_delta - d.quantity
        elif d.action == "buy" and d.quantity is not None and pid is not None:
            pos_key = (pid, d.symbol, str(d.currency))
            running_positions[pos_key] = running_positions.get(pos_key, 0.0) + d.quantity

        # 去重检测
        h = d.normalized_hash()
        if h in existing_hashes:
            d.warnings.append("疑似重复交易（与已有交易完全一致）")
            d.status = "duplicate"
            row_entry["status"] = "duplicate"
            row_entry["warnings"] = d.warnings
            summary["duplicate"] += 1
            preview_rows.append(row_entry)
            summary["total"] += 1
            continue

        # 统计
        if d.status == "warning":
            summary["warning"] += 1
        else:
            d.status = "valid"
            row_entry["status"] = "valid"
            summary["valid"] += 1

        preview_rows.append(row_entry)
        summary["total"] += 1

    # 存 ImportSession
    imp_session = ImportSession(
        user_id=user.id,
        platform_id=effective_platform_id,
        broker_type=broker_type,
        file_name=file_name,
        detected_fields=json.dumps(detected_fields, ensure_ascii=False),
        user_mapping=json.dumps(user_mapping, ensure_ascii=False) if user_mapping else None,
        rows_json=json.dumps(preview_rows, ensure_ascii=False),
        summary_json=json.dumps(summary),
        status="previewed",
    )
    session.add(imp_session)
    session.commit()
    session.refresh(imp_session)

    return {
        "import_session_id": imp_session.id,
        "detected_fields": detected_fields,
        "rows": preview_rows,
        "summary": summary,
    }


def commit_import(
    session: Session,
    user: User,
    import_session_id: int,
    selected_rows: Optional[List[int]] = None,
    edited_rows: Optional[Dict[int, dict]] = None,
) -> dict:
    """确认导入：将 preview 中的有效行写入 Transaction 表。

    Args:
        selected_rows: 要导入的行号列表（None = 所有 valid 行）
        edited_rows: {row_number: {field: new_value}} 用户修正的行

    Returns:
        {created_count, skipped_count, errors, reconciliation_id}
    """
    imp_session = session.get(ImportSession, import_session_id)
    if imp_session is None:
        return {"error": "导入会话不存在"}
    if imp_session.user_id != user.id:
        return {"error": "无权操作此导入会话"}
    if imp_session.status == "committed":
        return {"error": "此会话已经提交过"}

    rows = json.loads(imp_session.rows_json or "[]")
    if not rows:
        return {"error": "没有可导入的数据行"}

    # 应用用户修改
    edited = edited_rows or {}
    selected = set(selected_rows) if selected_rows else None

    created = 0
    skipped_duplicate = 0
    error_details = []
    created_txn_ids = []

    for row in rows:
        rn = row["row_number"]

        # 跳过未选中的行
        if selected is not None and rn not in selected:
            skipped_duplicate += 1
            continue

        # 跳过 error 行
        if row["status"] == "error":
            skipped_duplicate += 1
            continue

        # 跳过 duplicate 行（除非用户强选）
        if row["status"] == "duplicate" and (selected is None or rn not in selected):
            skipped_duplicate += 1
            continue

        data = row["data"].copy()

        # 应用用户修改
        if rn in edited:
            data.update(edited[rn])

        pid = row.get("resolved_platform_id")
        action_str = data.get("action", "")

        # 校验 action
        try:
            action = TxnAction(action_str)
        except ValueError:
            error_details.append({"row": rn, "error": f"无效的 action: {action_str}"})
            continue

        # 校验 currency
        try:
            currency = Currency(data.get("currency", "CNY"))
        except ValueError:
            error_details.append({"row": rn, "error": f"无效的 currency: {data.get('currency')}"})
            continue

        # 创建 Transaction
        try:
            txn = Transaction(
                user_id=user.id,
                platform_id=pid,
                date=data.get("date", ""),
                action=action,
                name=data.get("name", ""),
                symbol=data.get("symbol", ""),
                currency=currency,
                quantity=data.get("quantity"),
                price=data.get("price"),
                fee=data.get("fee"),
                amount=data.get("amount"),
            )
            txn.holding_id = None
        except Exception as e:
            error_details.append({"row": rn, "error": f"创建交易失败: {e}"})
            continue

        session.add(txn)
        session.commit()
        session.refresh(txn)

        # 同步持仓
        try:
            _sync_txn_holding(session, txn, user)
        except Exception as e:
            error_details.append({"row": rn, "error": f"同步持仓失败: {e}"})
            # 删除已创建的交易
            session.delete(txn)
            session.commit()
            continue

        created_txn_ids.append(txn.id)
        created += 1

    # 更新 ImportSession
    imp_session.status = "committed"
    imp_session.created_transaction_count = created
    imp_session.skipped_duplicate_count = skipped_duplicate
    session.add(imp_session)
    session.commit()

    return {
        "import_session_id": import_session_id,
        "created_count": created,
        "skipped_duplicate_count": skipped_duplicate,
        "errors": error_details,
        "created_transaction_ids": created_txn_ids,
    }


def _sync_txn_holding(session, txn, user):
    """本地导入：复用 transactions router 的同名函数逻辑。"""
    from position import recompute_holding, resolve_derived_holding

    affected = set()
    if txn.holding_id is not None:
        affected.add(txn.holding_id)

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
    elif txn.action in (TxnAction.deposit, TxnAction.withdraw):
        # 现金账本：更新 derived cash holding
        if txn.holding_id is not None:
            affected.add(txn.holding_id)
            txn.holding_id = None
            session.add(txn)
            session.commit()
        _update_cash_holding(session, user, txn)
    else:
        if txn.holding_id is not None:
            txn.holding_id = None
            session.add(txn)
            session.commit()

    for hid in affected:
        recompute_holding(session, hid)


def _update_cash_holding(session, user, txn):
    """deposit / withdraw：更新 derived cash 持仓的 manual_value。

    每个 (platform_id, currency) 维护一个 cash holding：
    - deposit: manual_value += amount
    - withdraw: manual_value -= amount（不低于 0）
    - buy / sell 第一版不联动现金
    """
    if txn.action not in (TxnAction.deposit, TxnAction.withdraw):
        return
    if txn.platform_id is None:
        return  # 没有平台的入金/出金无法归属

    amount = txn.amount or 0.0
    if amount <= 0:
        # 尝试从 quantity 取
        amount = txn.quantity or 0.0

    if amount <= 0:
        return  # 无效金额，跳过

    # 查找现有 cash holding
    cash = session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.platform_id == txn.platform_id,
            Holding.currency == txn.currency,
            Holding.asset_type == "cash",
            Holding.source == HoldingSource.derived,
        )
    ).first()

    if cash is None:
        # 创建 cash holding
        cash = Holding(
            user_id=user.id,
            platform_id=txn.platform_id,
            currency=txn.currency,
            asset_type="cash",
            market="NONE",
            name=f"现金余额 ({txn.currency.value})",
            symbol="",
            source=HoldingSource.derived,
            status="open",
            manual_value=0.0,
        )
        session.add(cash)
        session.commit()
        session.refresh(cash)

    current_mv = cash.manual_value or 0.0

    if txn.action == TxnAction.deposit:
        cash.manual_value = current_mv + amount
    elif txn.action == TxnAction.withdraw:
        new_val = current_mv - amount
        if new_val < -1e-9:
            raise ValueError(
                f"出金 {amount} {txn.currency.value} 超过当前现金余额 "
                f"{current_mv} {txn.currency.value}"
            )
        cash.manual_value = max(new_val, 0.0)

    cash.price_updated_at = datetime.utcnow()
    session.add(cash)
    session.commit()
