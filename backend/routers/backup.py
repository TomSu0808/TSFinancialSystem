"""数据备份：导出当前用户全部数据为 JSON；从 JSON 恢复（覆盖式）。"""
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Holding, Note, Platform, ResearchMessage, ResearchPreference, ResearchReport,
    ResearchRunEvent, Transaction, User, DailyPnl, Snapshot,
)

router = APIRouter(prefix="/api/backup", tags=["backup"])

VERSION = 2


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
        "daily_pnl": [r.model_dump(mode="json", exclude={"id", "user_id"}) for r in session.exec(select(DailyPnl).where(DailyPnl.user_id == user.id)).all()],
        "snapshots": [r.model_dump(mode="json", exclude={"id", "user_id"}) for r in session.exec(select(Snapshot).where(Snapshot.user_id == user.id)).all()],
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
                "cost_value": h.cost_value,
                "current_price": h.current_price,
                "prev_close": h.prev_close,
                "ref": h.id,
                "source": h.source.value,
                "status": h.status.value,
                "realized_pnl": h.realized_pnl,
                "realized_pnl_incomplete": h.realized_pnl_incomplete,
                "realized_income": h.realized_income,
            }
            for h in holds
        ],
        "notes": [
            {
                "title": n.title, "content": n.content,
                "note_type": n.note_type, "status": n.status, "tags": n.tags,
                "symbol": n.symbol,
                "metric": n.metric,
                "review_date": n.review_date,
                "trigger_condition": n.trigger_condition,
                "report_version": n.report_version,
                "related_holding_ref": n.related_holding_id,
                "source_report_ref": n.source_report_id,
                "created_at": _dt(n.created_at), "updated_at": _dt(n.updated_at),
            }
            for n in notes
        ],
        "transactions": [
            {
                "platform_ref": t.platform_id,
                "date": t.date, "action": t.action.value,
                "name": t.name, "symbol": t.symbol, "currency": t.currency.value,
                "cash_currency": t.cash_currency.value if t.cash_currency else None,
                "fx_rate": t.fx_rate,
                "quantity": t.quantity, "price": t.price, "fee": t.fee,
                "amount": t.amount, "note": t.note, "created_at": _dt(t.created_at),
                "holding_ref": t.holding_id,
            }
            for t in txns
        ],
        "research_reports": [
            {
                "ref": r.id,
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
                "parent_ref": r.parent_report_id,
                "version": r.version,
                "execution_mode": r.execution_mode,
                "engine": r.engine,
                "engine_version": r.engine_version,
                "engine_commit": r.engine_commit,
                "report_json": r.report_json,
                "multi_agent_json": r.multi_agent_json,
                "input_snapshot_json": r.input_snapshot_json,
                "usage_json": r.usage_json,
                "budget_json": r.budget_json,
                "source_status_json": r.source_status_json,
                "data_cutoff": r.data_cutoff,
                "created_at": _dt(r.created_at),
                "updated_at": _dt(r.updated_at),
                "completed_at": _dt(r.completed_at) if r.completed_at else None,
            }
            for r in reports
        ],
        "research_messages": [
            {
                "report_ref": m.report_id,
                "role": m.role,
                "content": m.content,
                "status": m.status,
                "request_id": m.request_id,
                "sources_json": m.sources_json,
                "new_sources_json": m.new_sources_json,
                "data_as_of": m.data_as_of,
                "used_web_search": m.used_web_search,
                "search_status": m.search_status,
                "context_compressed": m.context_compressed,
                "error_message": m.error_message,
                "usage_json": m.usage_json,
                "budget_json": m.budget_json,
                "cancelled_at": _dt(m.cancelled_at) if m.cancelled_at else None,
                "created_at": _dt(m.created_at),
                "updated_at": _dt(m.updated_at),
            }
            for m in session.exec(select(ResearchMessage).where(
                ResearchMessage.user_id == user.id)).all()
        ],
        "research_preferences": [
            {
                "investment_goal": pref.investment_goal,
                "holding_period": pref.holding_period,
                "risk_preference": pref.risk_preference,
                "updated_at": _dt(pref.updated_at),
            }
            for pref in session.exec(select(ResearchPreference).where(
                ResearchPreference.user_id == user.id)).all()
        ],
    }


class ImportPayload(BaseModel):
    platforms: List[Dict[str, Any]] = []
    holdings: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    transactions: List[Dict[str, Any]] = []
    research_reports: List[Dict[str, Any]] = []
    research_messages: List[Dict[str, Any]] = []
    research_preferences: List[Dict[str, Any]] = []
    daily_pnl: List[Dict[str, Any]] = []
    snapshots: List[Dict[str, Any]] = []


@router.post("/import")
def import_backup(
    data: ImportPayload,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """覆盖式恢复：先清空当前用户的全部数据，再按备份重建。"""
    # 1) 清空当前用户数据（先子后父）
    for model in (
        ResearchMessage, ResearchRunEvent, ResearchPreference, DailyPnl, Snapshot,
        ResearchReport, Transaction, Holding, Note, Platform,
    ):
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
            cost_price=h.get("cost_price"), cost_value=h.get("cost_value"),
            current_price=h.get("current_price"),
            prev_close=h.get("prev_close"),
            source=h.get("source", "manual"), status=h.get("status", "open"),
            realized_pnl=h.get("realized_pnl", 0.0),
            realized_pnl_incomplete=h.get("realized_pnl_incomplete", False),
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
            currency=t.get("currency", "CNY"),
            cash_currency=t.get("cash_currency"), fx_rate=t.get("fx_rate"),
            quantity=t.get("quantity"),
            price=t.get("price"), fee=t.get("fee"), amount=t.get("amount"),
            note=t.get("note"), created_at=_parse_dt(t.get("created_at")),
        ))

    # 5) 重建心得（报告引用在报告恢复后再映射）
    pending_note_report_refs = []
    for n in data.notes:
        note = Note(
            user_id=user.id, title=n.get("title"), content=n.get("content", ""),
            note_type=n.get("note_type", "general"), status=n.get("status", "active"),
            tags=n.get("tags"), symbol=n.get("symbol"),
            metric=n.get("metric"), review_date=n.get("review_date"),
            trigger_condition=n.get("trigger_condition"),
            report_version=n.get("report_version"),
            related_holding_id=hold_map.get(n.get("related_holding_ref")),
            created_at=_parse_dt(n.get("created_at")), updated_at=_parse_dt(n.get("updated_at")),
        )
        session.add(note)
        if n.get("source_report_ref") is not None:
            pending_note_report_refs.append((note, n.get("source_report_ref")))

    session.commit()

    # 6) derived 持仓按导入的交易重算（manual 持仓会被 recompute 跳过）
    from position import recompute_holding
    for hid in hold_map.values():
        recompute_holding(session, hid)
    from cash_service import rebuild_sale_cash
    rebuild_sale_cash(session, user.id)

    # 7) 重建投研报告（先建记录，再恢复版本关系；provider_response_id 不恢复）
    report_map: Dict[Any, int] = {}
    for r in data.research_reports:
        completed_at_raw = r.get("completed_at")
        report = ResearchReport(
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
            parent_report_id=None,
            version=r.get("version", 1),
            execution_mode=r.get("execution_mode", "standard"),
            engine=r.get("engine"),
            engine_version=r.get("engine_version"),
            engine_commit=r.get("engine_commit"),
            report_json=r.get("report_json"),
            multi_agent_json=r.get("multi_agent_json"),
            input_snapshot_json=r.get("input_snapshot_json"),
            usage_json=r.get("usage_json"),
            budget_json=r.get("budget_json"),
            source_status_json=r.get("source_status_json"),
            data_cutoff=r.get("data_cutoff"),
            created_at=_parse_dt(r.get("created_at")),
            updated_at=_parse_dt(r.get("updated_at")),
            completed_at=_parse_dt(completed_at_raw) if completed_at_raw else None,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        if r.get("ref") is not None:
            report_map[r.get("ref")] = report.id
    for r in data.research_reports:
        old_ref = r.get("ref")
        parent_ref = r.get("parent_ref")
        if old_ref in report_map and parent_ref in report_map:
            report = session.get(ResearchReport, report_map[old_ref])
            if report:
                report.parent_report_id = report_map[parent_ref]
                session.add(report)
    for note, old_report_ref in pending_note_report_refs:
        if old_report_ref in report_map:
            note.source_report_id = report_map[old_report_ref]
            session.add(note)
    session.commit()

    # 7b) 恢复报告追问消息与研究偏好
    for m in data.research_messages:
        report_id = report_map.get(m.get("report_ref"))
        if report_id is None:
            continue
        cancelled_raw = m.get("cancelled_at")
        session.add(ResearchMessage(
            user_id=user.id,
            report_id=report_id,
            role=m.get("role", "assistant"),
            content=m.get("content", ""),
            status=m.get("status", "completed"),
            request_id=m.get("request_id"),
            sources_json=m.get("sources_json"),
            new_sources_json=m.get("new_sources_json"),
            data_as_of=m.get("data_as_of"),
            used_web_search=bool(m.get("used_web_search")),
            search_status=m.get("search_status"),
            context_compressed=bool(m.get("context_compressed")),
            error_message=m.get("error_message"),
            usage_json=m.get("usage_json"),
            budget_json=m.get("budget_json"),
            cancelled_at=_parse_dt(cancelled_raw) if cancelled_raw else None,
            created_at=_parse_dt(m.get("created_at")),
            updated_at=_parse_dt(m.get("updated_at")),
        ))
    for pref in data.research_preferences:
        session.add(ResearchPreference(
            user_id=user.id,
            investment_goal=pref.get("investment_goal"),
            holding_period=pref.get("holding_period"),
            risk_preference=pref.get("risk_preference"),
            updated_at=_parse_dt(pref.get("updated_at")),
        ))
    session.commit()

    # 历史盈亏保留；恢复后的持仓 ID 已变化，下一日重建计算基准。
    from routers.snapshots import _valid_day
    seen = set()
    for entry in data.daily_pnl:
        if not _valid_day(entry.get("day")) or entry["day"] in seen:
            continue
        seen.add(entry["day"])
        session.add(DailyPnl(
            user_id=user.id, day=entry["day"], updated_at=_parse_dt(entry.get("updated_at")),
            returns_json=entry.get("returns_json", "{}"), basis_json="{}",
            details_json=entry.get("details_json", "[]"),
            pnl_cny=entry.get("pnl_cny"), pnl_usd=entry.get("pnl_usd"),
            status=entry.get("status", "baseline"), note=entry.get("note", ""),
            coverage_complete=False,
        ))
    seen.clear()
    for entry in data.snapshots:
        if not _valid_day(entry.get("day")) or entry["day"] in seen:
            continue
        seen.add(entry["day"])
        session.add(Snapshot(user_id=user.id, day=entry["day"], ts=_parse_dt(entry.get("ts")),
                             total_cny=entry.get("total_cny", 0), total_usd=entry.get("total_usd", 0)))
    session.commit()

    return {
        "ok": True,
        "platforms": len(data.platforms),
        "holdings": len(data.holdings),
        "transactions": len(data.transactions),
        "notes": len(data.notes),
        "research_reports": len(data.research_reports),
    }
