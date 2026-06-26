"""数据备份：导出当前用户全部数据为 JSON；从 JSON 恢复（覆盖式）。"""
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Holding, Note, Platform, ResearchReport, Transaction, User

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
    reports = session.exec(select(ResearchReport).where(ResearchReport.user_id == user.id)).all()

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
                "ref": h.id,
                "source": h.source.value,
                "status": h.status.value,
                "realized_pnl": h.realized_pnl,
                "realized_income": h.realized_income,
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
                "holding_ref": t.holding_id,
            }
            for t in txns
        ],
        "research_reports": [
            {
                "template_key": r.template_key,
                "title": r.title,
                "target_name": r.target_name,
                "symbol": r.symbol,
                "market": r.market,
                "report_language": r.report_language,
                "status": r.status,
                "input_context_md": r.input_context_md,
                "skill_md": r.skill_md,
                "prompt_md": r.prompt_md,
                "report_md": r.report_md,
                "sources_json": r.sources_json,
                "provider": r.provider,
                "model": r.model,
                "created_at": _dt(r.created_at),
                "updated_at": _dt(r.updated_at),
                "completed_at": _dt(r.completed_at) if r.completed_at else None,
            }
            for r in reports
        ],
    }


class ImportPayload(BaseModel):
    platforms: List[Dict[str, Any]] = []
    holdings: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    transactions: List[Dict[str, Any]] = []
    research_reports: List[Dict[str, Any]] = []


@router.post("/import")
def import_backup(
    data: ImportPayload,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """覆盖式恢复：先清空当前用户的全部数据，再按备份重建。"""
    # 1) 清空当前用户数据（先子后父）
    for model in (ResearchReport, Transaction, Holding, Note, Platform):
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

    # 3) 重建持仓，记录 旧holding ref -> 新id
    hold_map: Dict[Any, int] = {}
    for h in data.holdings:
        pid = ref_map.get(h.get("platform_ref"))
        if pid is None:
            continue  # 平台缺失则跳过该持仓
        holding = Holding(
            user_id=user.id, platform_id=pid,
            currency=h.get("currency", "CNY"), asset_type=h.get("asset_type", "stock"),
            market=h.get("market", "A"), symbol=h.get("symbol", ""), name=h.get("name", ""),
            quantity=h.get("quantity"), manual_value=h.get("manual_value"),
            cost_price=h.get("cost_price"), current_price=h.get("current_price"),
            prev_close=h.get("prev_close"),
            source=h.get("source", "manual"), status=h.get("status", "open"),
            realized_pnl=h.get("realized_pnl", 0.0),
            realized_income=h.get("realized_income", 0.0),
        )
        session.add(holding)
        session.commit()
        session.refresh(holding)
        if h.get("ref") is not None:
            hold_map[h.get("ref")] = holding.id

    # 4) 重建交易（平台可空）
    for t in data.transactions:
        session.add(Transaction(
            user_id=user.id, platform_id=ref_map.get(t.get("platform_ref")),
            holding_id=hold_map.get(t.get("holding_ref")),
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

    # 6) derived 持仓按导入的交易重算（manual 持仓会被 recompute 跳过）
    from position import recompute_holding
    for hid in hold_map.values():
        recompute_holding(session, hid)

    # 7) 重建投研报告（provider_response_id 不恢复，相关联 holding 不重映射）
    for r in data.research_reports:
        completed_at_raw = r.get("completed_at")
        session.add(ResearchReport(
            user_id=user.id,
            template_key=r.get("template_key", ""),
            title=r.get("title", ""),
            target_name=r.get("target_name", ""),
            symbol=r.get("symbol"),
            market=r.get("market"),
            report_language=r.get("report_language", "zh"),
            status=r.get("status", "draft"),
            input_context_md=r.get("input_context_md"),
            skill_md=r.get("skill_md"),
            prompt_md=r.get("prompt_md"),
            report_md=r.get("report_md"),
            sources_json=r.get("sources_json"),
            provider=r.get("provider"),
            model=r.get("model"),
            created_at=_parse_dt(r.get("created_at")),
            updated_at=_parse_dt(r.get("updated_at")),
            completed_at=_parse_dt(completed_at_raw) if completed_at_raw else None,
        ))

    session.commit()

    return {
        "ok": True,
        "platforms": len(data.platforms),
        "holdings": len(data.holdings),
        "transactions": len(data.transactions),
        "notes": len(data.notes),
        "research_reports": len(data.research_reports),
    }
