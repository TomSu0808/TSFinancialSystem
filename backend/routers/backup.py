"""数据备份：导出当前用户全部数据为 JSON；从 JSON 恢复（覆盖式）。"""
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Holding, Note, Platform, Transaction, User

router = APIRouter(prefix="/api/backup", tags=["backup"])

VERSION = 1


def _dt(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def _parse_dt(v: Any) -> datetime:
    try:
        return datetime.fromisoformat(v) if isinstance(v, str) else datetime.utcnow()
    except ValueError:
        return datetime.utcnow()


@router.get("")
def export_backup(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    plats = session.exec(select(Platform).where(Platform.user_id == user.id)).all()
    holds = session.exec(select(Holding).where(Holding.user_id == user.id)).all()
    notes = session.exec(select(Note).where(Note.user_id == user.id)).all()
    txns = session.exec(select(Transaction).where(Transaction.user_id == user.id)).all()

    return {
        "version": VERSION,
        "exported_at": datetime.utcnow().isoformat(),
        "username": user.username,
        "platforms": [{"ref": p.id, "name": p.name, "note": p.note} for p in plats],
        "holdings": [
            {
                "platform_ref": h.platform_id,
                "currency": h.currency.value,
                "asset_type": h.asset_type.value,
                "market": h.market.value,
                "symbol": h.symbol,
                "name": h.name,
                "quantity": h.quantity,
                "manual_value": h.manual_value,
                "cost_price": h.cost_price,
                "current_price": h.current_price,
                "prev_close": h.prev_close,
            }
            for h in holds
        ],
        "notes": [
            {"title": n.title, "content": n.content,
             "created_at": _dt(n.created_at), "updated_at": _dt(n.updated_at)}
            for n in notes
        ],
        "transactions": [
            {
                "platform_ref": t.platform_id,
                "date": t.date, "action": t.action.value,
                "name": t.name, "symbol": t.symbol, "currency": t.currency.value,
                "quantity": t.quantity, "price": t.price, "fee": t.fee,
                "amount": t.amount, "note": t.note, "created_at": _dt(t.created_at),
            }
            for t in txns
        ],
    }


class ImportPayload(BaseModel):
    platforms: List[Dict[str, Any]] = []
    holdings: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    transactions: List[Dict[str, Any]] = []


@router.post("/import")
def import_backup(
    data: ImportPayload,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """覆盖式恢复：先清空当前用户的全部数据，再按备份重建。"""
    # 1) 清空当前用户数据（先子后父）
    for model in (Transaction, Holding, Note, Platform):
        for row in session.exec(select(model).where(model.user_id == user.id)).all():
            session.delete(row)
    session.commit()

    # 2) 重建平台并记录 旧ref -> 新id
    ref_map: Dict[Any, int] = {}
    for p in data.platforms:
        plat = Platform(user_id=user.id, name=p.get("name", ""), note=p.get("note"))
        session.add(plat)
        session.commit()
        session.refresh(plat)
        ref_map[p.get("ref")] = plat.id

    # 3) 重建持仓
    for h in data.holdings:
        pid = ref_map.get(h.get("platform_ref"))
        if pid is None:
            continue  # 平台缺失则跳过该持仓
        session.add(Holding(
            user_id=user.id, platform_id=pid,
            currency=h.get("currency", "CNY"), asset_type=h.get("asset_type", "stock"),
            market=h.get("market", "A"), symbol=h.get("symbol", ""), name=h.get("name", ""),
            quantity=h.get("quantity"), manual_value=h.get("manual_value"),
            cost_price=h.get("cost_price"), current_price=h.get("current_price"),
            prev_close=h.get("prev_close"),
        ))

    # 4) 重建交易（平台可空）
    for t in data.transactions:
        session.add(Transaction(
            user_id=user.id, platform_id=ref_map.get(t.get("platform_ref")),
            date=t.get("date", ""), action=t.get("action", "buy"),
            name=t.get("name", ""), symbol=t.get("symbol", ""),
            currency=t.get("currency", "CNY"), quantity=t.get("quantity"),
            price=t.get("price"), fee=t.get("fee"), amount=t.get("amount"),
            note=t.get("note"), created_at=_parse_dt(t.get("created_at")),
        ))

    # 5) 重建心得
    for n in data.notes:
        session.add(Note(
            user_id=user.id, title=n.get("title"), content=n.get("content", ""),
            created_at=_parse_dt(n.get("created_at")), updated_at=_parse_dt(n.get("updated_at")),
        ))

    session.commit()
    return {
        "ok": True,
        "platforms": len(data.platforms),
        "holdings": len(data.holdings),
        "transactions": len(data.transactions),
        "notes": len(data.notes),
    }
