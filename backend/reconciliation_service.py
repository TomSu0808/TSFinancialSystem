"""对账服务：导入后对比券商文件持仓与系统交易回放持仓。

流程：
1. 从导入文件提取券商持仓摘要（若无显式持仓则基于导入交易推算）
2. 计算系统端 replay 持仓
3. 逐标的对比 quantity 和 cost
4. 返回 matched / warning / error 状态
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from models import (
    Currency,
    Holding,
    HoldingSource,
    ImportSession,
    Platform,
    ReconSnapshot,
    Transaction,
    TxnAction,
    User,
)
from position import replay_transactions


# 对账阈值
QUANTITY_EPS = 1e-6   # 数量差异在此以内视为 matched
COST_EPS = 0.01        # 成本差异在此以内视为 matched
QUANTITY_WARN_EPS = 0.01  # 超过此阈值视为 error


def compute_reconciliation(
    session: Session,
    user: User,
    import_session_id: int,
) -> dict:
    """计算导入后对账结果并存入 ReconSnapshot。"""
    imp_session = session.get(ImportSession, import_session_id)
    if imp_session is None:
        return {"error": "导入会话不存在"}
    if imp_session.user_id != user.id:
        return {"error": "无权查看此对账"}

    platform_name = "—"
    if imp_session.platform_id:
        plat = session.get(Platform, imp_session.platform_id)
        if plat:
            platform_name = plat.name

    # 1. 从导入文件构建券商侧持仓
    broker_positions = _build_broker_positions(session, user, imp_session)

    # 2. 获取系统侧持仓
    system_positions = _get_system_positions(session, user, imp_session)

    # 3. 合并所有标的
    all_symbols = set(broker_positions.keys()) | set(system_positions.keys())

    # 清理旧对账快照
    old_snapshots = session.exec(
        select(ReconSnapshot).where(
            ReconSnapshot.import_session_id == import_session_id,
        )
    ).all()
    for s in old_snapshots:
        session.delete(s)
    session.commit()

    # 4. 逐标的对账
    recon_items = []
    for key in sorted(all_symbols):
        bp = broker_positions.get(key, {})
        sp = system_positions.get(key, {})

        broker_qty = bp.get("quantity")
        sys_qty = sp.get("quantity")
        broker_cost = bp.get("cost")
        sys_cost = sp.get("cost")

        qty_diff = None
        cost_diff = None
        if broker_qty is not None and sys_qty is not None:
            qty_diff = broker_qty - sys_qty
        if broker_cost is not None and sys_cost is not None:
            cost_diff = broker_cost - sys_cost

        # 状态判定
        status = "matched"
        if qty_diff is not None and abs(qty_diff) > QUANTITY_WARN_EPS:
            status = "error"
        elif qty_diff is not None and abs(qty_diff) > QUANTITY_EPS:
            status = "warning"
        elif cost_diff is not None and abs(cost_diff) > COST_EPS:
            status = "warning"

        # 保存快照
        snap = ReconSnapshot(
            user_id=user.id,
            import_session_id=import_session_id,
            platform_id=imp_session.platform_id,
            symbol=key[0] if isinstance(key, tuple) else key,
            name=bp.get("name", sp.get("name", "")),
            currency=bp.get("currency", sp.get("currency", "")),
            broker_quantity=broker_qty,
            system_quantity=sys_qty,
            quantity_diff=qty_diff,
            broker_cost=broker_cost,
            system_cost=sys_cost,
            cost_diff=cost_diff,
            status=status,
            detail_json=json.dumps({
                "broker_side": bp,
                "system_side": sp,
            }, ensure_ascii=False),
        )
        session.add(snap)

        recon_items.append({
            "symbol": snap.symbol,
            "name": snap.name,
            "currency": snap.currency,
            "broker_quantity": broker_qty,
            "system_quantity": sys_qty,
            "quantity_diff": round(qty_diff, 6) if qty_diff is not None else None,
            "broker_cost": round(broker_cost, 4) if broker_cost is not None else None,
            "system_cost": round(sys_cost, 4) if sys_cost is not None else None,
            "cost_diff": round(cost_diff, 4) if cost_diff is not None else None,
            "status": status,
        })

    session.commit()

    # 统计
    total = len(recon_items)
    matched = sum(1 for r in recon_items if r["status"] == "matched")
    warnings = sum(1 for r in recon_items if r["status"] == "warning")
    errors = sum(1 for r in recon_items if r["status"] == "error")

    return {
        "import_session_id": import_session_id,
        "platform_name": platform_name,
        "total_items": total,
        "matched_count": matched,
        "warning_count": warnings,
        "error_count": errors,
        "items": recon_items,
    }


def _build_broker_positions(
    session: Session,
    user: User,
    imp_session: ImportSession,
) -> Dict[tuple, dict]:
    """从导入文件构建券商侧持仓摘要。

    解析逻辑：
    - 如果 rows_json 中有 buy/sell，按 symbol 汇总数量
    - 不包含 dividend
    """
    rows = json.loads(imp_session.rows_json or "[]")
    positions: Dict[tuple, dict] = {}

    for row in rows:
        if row.get("status") == "error":
            continue
        data = row.get("data", {})
        action = data.get("action", "")
        if action not in ("buy", "sell"):
            continue
        symbol = (data.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        name = data.get("name", "")
        currency = data.get("currency", "")
        qty = data.get("quantity") or 0.0
        price = data.get("price") or 0.0

        key = (symbol, currency)
        if key not in positions:
            positions[key] = {"symbol": symbol, "name": name, "currency": currency,
                              "quantity": 0.0, "total_cost": 0.0}

        if action == "buy":
            positions[key]["quantity"] += qty
            positions[key]["total_cost"] += qty * price
        elif action == "sell":
            positions[key]["quantity"] -= qty
            # Sell reduces total cost proportionally
            if positions[key]["quantity"] > 0:
                avg = positions[key]["total_cost"] / positions[key]["quantity"] if positions[key]["quantity"] > 0 else 0
                positions[key]["total_cost"] -= qty * avg

    # 计算平均成本
    for key, pos in positions.items():
        if pos["quantity"] > 0:
            pos["cost"] = round(pos["total_cost"] / pos["quantity"], 4)
        else:
            pos["cost"] = None
        pos.pop("total_cost", None)

    return positions


def _get_system_positions(
    session: Session,
    user: User,
    imp_session: ImportSession,
) -> Dict[tuple, dict]:
    """获取系统侧（交易回放）持仓。"""
    positions: Dict[tuple, dict] = {}

    holdings = session.exec(
        select(Holding).where(
            Holding.user_id == user.id,
            Holding.platform_id == imp_session.platform_id,
            Holding.source == HoldingSource.derived,
            Holding.asset_type != "cash",
        )
    ).all()

    for h in holdings:
        if not h.symbol:
            continue
        symbol = h.symbol.strip().upper()
        key = (symbol, str(h.currency.value))
        positions[key] = {
            "symbol": h.symbol,
            "name": h.name,
            "currency": h.currency.value,
            "quantity": h.quantity or 0.0,
            "cost": h.cost_price,
        }

    return positions
