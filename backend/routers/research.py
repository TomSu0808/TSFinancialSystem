"""投研工作台路由：模板、研究任务、报告、追问、更新、跟踪事项（按用户隔离）。"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import (
    Holding, HoldingStatus, Note, ResearchMessage, ResearchMessageCreate,
    ResearchPreference, ResearchPreferenceUpdate, ResearchPreviewRequest,
    ResearchReport, ResearchReportCreate, ResearchReportUpdate,
    ResearchRunCreate, ResearchRunEvent, ResearchUpdateRequest, TrackingSaveRequest,
    User,
)
from models import Currency
from ai_berkshire_loader import list_skills
import research_chat
import research_events
import research_jobs
import research_service
import research_structured
from threading import Lock
from ai_client import AIServiceNotConfigured

router = APIRouter(prefix="/api/research", tags=["research"])
_launches = set()
_launch_guard = Lock()


def _owned(session: Session, report_id: int, user: User) -> ResearchReport:
    report = session.get(ResearchReport, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(404, "报告不存在")
    return report


# ── 模板列表 ──────────────────────────────────────────────────────

@router.get("/templates")
def list_templates() -> List[Dict[str, Any]]:
    return list_skills()


# ── AI 投研任务 ───────────────────────────────────────────────────

@router.post("/runs", response_model=ResearchReport)
def create_run(
    data: ResearchRunCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    with _launch_guard:
        if user.id in _launches:
            raise HTTPException(409, "分析正在提交，请勿重复点击")
        _launches.add(user.id)
    try:
        return research_service.create_run(
            session=session,
            user=user,
            template_key=data.template_key,
            target_name=data.target_name,
            symbol=data.symbol,
            market=data.market,
            related_holding_id=data.related_holding_id,
            report_language=data.report_language.value,
            ai_provider=data.ai_provider,
            ai_model=data.ai_model,
            extra_instruction=data.extra_instruction,
            use_web_search=data.use_web_search,
            display_currency=data.display_currency,
            execution_mode=data.execution_mode,
            include_holding_context=data.include_holding_context,
            idempotency_key=data.idempotency_key,
        )
    except AIServiceNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except PermissionError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"研究任务启动失败：{str(exc)[:500]}")
    finally:
        with _launch_guard:
            _launches.discard(user.id)


@router.post("/preview")
def preview_run(
    data: ResearchPreviewRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """提交前预览实际会携带的数据；不调用模型、不写数据库。"""
    try:
        return research_service.build_preview(
            session=session,
            user=user,
            template_key=data.template_key,
            target_name=data.target_name,
            symbol=data.symbol,
            market=data.market,
            related_holding_id=data.related_holding_id,
            report_language=data.report_language.value,
            display_currency=data.display_currency,
            execution_mode=data.execution_mode,
            include_holding_context=data.include_holding_context,
            use_web_search=data.use_web_search,
            ai_provider=data.ai_provider,
        )
    except PermissionError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/preferences")
def get_research_preferences(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    pref = research_service.get_preferences(session, user)
    return {
        "investment_goal": pref.investment_goal if pref else None,
        "holding_period": pref.holding_period if pref else None,
        "risk_preference": pref.risk_preference if pref else None,
    }


@router.put("/preferences")
def save_research_preferences(
    data: ResearchPreferenceUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    pref = research_service.save_preferences(
        session, user, data.model_dump(exclude_unset=True))
    return {
        "investment_goal": pref.investment_goal,
        "holding_period": pref.holding_period,
        "risk_preference": pref.risk_preference,
    }


@router.post("/runs/{report_id}/refresh", response_model=ResearchReport)
def refresh_run(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    return research_service.refresh_run(session, report)


@router.post("/reports/{report_id}/update", response_model=ResearchReport)
def update_research(
    report_id: int,
    data: ResearchUpdateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """以旧报告为基线，核查新资料并生成新版本，保留版本链。"""
    parent = _owned(session, report_id, user)
    with _launch_guard:
        if user.id in _launches:
            raise HTTPException(409, "已有研究正在提交，请勿重复点击")
        _launches.add(user.id)
    try:
        return research_service.create_update_run(
            session=session,
            user=user,
            parent=parent,
            extra_instruction=data.extra_instruction,
            ai_provider=data.ai_provider,
            ai_model=data.ai_model,
            use_web_search=data.use_web_search,
            idempotency_key=data.idempotency_key,
        )
    except AIServiceNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except PermissionError as exc:
        raise HTTPException(404, str(exc))
    finally:
        with _launch_guard:
            _launches.discard(user.id)


@router.get("/reports/{report_id}/versions")
def list_versions(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    chain: List[ResearchReport] = []
    seen = set()
    current: Optional[ResearchReport] = report
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current)
        current = session.get(ResearchReport, current.parent_report_id) if current.parent_report_id else None
        if current is not None and current.user_id != user.id:
            current = None
    # Include later versions so opening v1 still shows the forward chain.
    queue = list(chain)
    while queue:
        node = queue.pop(0)
        children = session.exec(
            select(ResearchReport).where(
                ResearchReport.user_id == user.id,
                ResearchReport.parent_report_id == node.id,
            )
        ).all()
        for child in children:
            if child.id not in seen:
                seen.add(child.id)
                chain.append(child)
                queue.append(child)
    chain.sort(key=lambda r: (r.version or 1, r.id))
    return [
        {
            "id": r.id, "version": r.version, "title": r.title,
            "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None,
            "parent_report_id": r.parent_report_id,
        }
        for r in chain
    ]


@router.get("/reports/{report_id}/events")
def list_run_events(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _owned(session, report_id, user)
    events = research_events.list_events(session, report_id, user.id)
    return [
        {
            "id": e.id, "seq": e.seq, "stage": e.stage, "status": e.status,
            "message": e.message,
            "payload": json.loads(e.payload_json) if e.payload_json else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/reports/{report_id}/messages")
def list_report_messages(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    return [m.model_dump() for m in research_chat.list_messages(session, report)]


@router.post("/reports/{report_id}/messages", response_model=ResearchMessage)
def create_report_message(
    report_id: int,
    data: ResearchMessageCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    try:
        return research_chat.start_exchange(
            session, user, report, data.question, data.use_web_search, data.request_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@router.post("/reports/{report_id}/messages/{message_id}/cancel")
def cancel_report_message(
    report_id: int,
    message_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    _owned(session, report_id, user)
    message = session.get(ResearchMessage, message_id)
    if not message or message.report_id != report_id or message.user_id != user.id:
        raise HTTPException(404, "消息不存在")
    return research_chat.cancel_message(session, user, message)


# ── Prompt 生成（保留旧接口，不再作为主流程）────────────────────────

class PromptRequest(BaseModel):
    template_key: str
    target_name: str = ""
    symbol: Optional[str] = None
    market: Optional[str] = None
    holding_id: Optional[int] = None


@router.post("/prompts")
def generate_prompt(
    req: PromptRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    from ai_berkshire_loader import load_skill
    import research_prompt_builder

    try:
        skill_md = load_skill(req.template_key)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))

    holding_ctx = ""
    portfolio_ctx = ""

    if req.template_key == "portfolio-review":
        holdings = session.exec(
            select(Holding).where(
                Holding.user_id == user.id,
                Holding.status != HoldingStatus.closed,
            )
        ).all()
        portfolio_ctx = research_service._portfolio_context(list(holdings), session)
    elif req.holding_id is not None:
        h = session.get(Holding, req.holding_id)
        if not h or h.user_id != user.id:
            raise HTTPException(404, "持仓不存在")
        holding_ctx = research_service._holding_context(h, session)

    prompt = research_prompt_builder.build_prompt(
        skill_md=skill_md,
        target_name=req.target_name or "目标公司",
        symbol=req.symbol or "",
        market=req.market or "",
        holding_ctx=holding_ctx,
        portfolio_ctx=portfolio_ctx,
        is_portfolio=req.template_key == "portfolio-review",
    )
    return {"prompt": prompt}


# ── 报告 CRUD ─────────────────────────────────────────────────────

@router.get("/reports", response_model=List[ResearchReport])
def list_reports(
    template_key: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(ResearchReport).where(ResearchReport.user_id == user.id)
    if template_key:
        stmt = stmt.where(ResearchReport.template_key == template_key)
    return session.exec(stmt.order_by(ResearchReport.updated_at.desc())).all()


@router.get("/portfolio-summary")
def portfolio_summary(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """返回最新成功组合报告的派生摘要，供首页总览卡片使用。"""
    base = select(ResearchReport).where(
        ResearchReport.user_id == user.id, ResearchReport.template_key == "portfolio-review")
    latest = session.exec(base.order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())).first()
    report = session.exec(base.where(ResearchReport.status == "completed", ResearchReport.report_md != None,
                                     ResearchReport.report_md != "")
                          .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())).first()
    task = {"id": latest.id, "status": latest.status, "error_message": latest.error_message} if latest else None
    if not report:
        return {"report": None, "latest_task": task}
    structured = {}
    try:
        structured = json.loads(report.report_json or "{}")
    except (TypeError, ValueError):
        structured = {}
    conclusions = [item.get("text") for item in structured.get("key_facts") or [] if item.get("text")]
    risks = [item.get("text") for item in structured.get("risks") or [] if item.get("text")]
    actions = [item.get("text") for item in structured.get("tracking") or [] if item.get("text")]
    if not conclusions:
        conclusions = _extract_bullets(report.report_md, ("结论摘要", "Summary"))
    if not risks:
        risks = _extract_bullets(report.report_md, ("主要风险", "Key Risks"))
    if not actions:
        actions = _extract_bullets(report.report_md, ("行动项", "Action Items"))
    match = re.search(r"分析时点：([^\n]+)", report.input_context_md or "")
    currency = re.search(r"展示币种：([A-Z]+)", report.input_context_md or "")
    return {
        "latest_task": task,
        "report": {
            "id": report.id, "title": report.title,
            "as_of": report.data_cutoff or (match.group(1).strip() if match else None),
            "display_currency": currency.group(1) if currency else None,
            "status": report.status, "conclusions": conclusions[:3], "risks": risks[:5],
            "actions": actions[:5], "degraded": not conclusions or structured.get("degraded", False),
            "version": report.version,
        }
    }


@router.get("/reports/{report_id}", response_model=ResearchReport)
def get_report(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return _owned(session, report_id, user)


@router.post("/reports", response_model=ResearchReport)
def create_report(
    data: ResearchReportCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    if data.related_holding_id is not None:
        h = session.get(Holding, data.related_holding_id)
        if not h or h.user_id != user.id:
            raise HTTPException(404, "持仓不存在")
    report = ResearchReport(
        user_id=user.id,
        template_key=data.template_key,
        title=data.title,
        target_name=data.target_name,
        symbol=data.symbol,
        market=data.market,
        related_holding_id=data.related_holding_id,
        report_language=data.report_language.value,
        status="draft",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


@router.put("/reports/{report_id}", response_model=ResearchReport)
def update_report(
    report_id: int,
    data: ResearchReportUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(report, key, value)
    report.updated_at = datetime.utcnow()
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


@router.delete("/reports/{report_id}")
def delete_report(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    # Child versions keep their content but lose a dangling parent reference.
    children = session.exec(
        select(ResearchReport).where(
            ResearchReport.user_id == user.id,
            ResearchReport.parent_report_id == report_id,
        )
    ).all()
    for child in children:
        child.parent_report_id = None
        session.add(child)
    linked_notes = session.exec(
        select(Note).where(
            Note.user_id == user.id,
            Note.source_report_id == report_id,
        )
    ).all()
    for note in linked_notes:
        note.source_report_id = None
        session.add(note)
    for message in session.exec(
        select(ResearchMessage).where(ResearchMessage.report_id == report_id)
    ).all():
        session.delete(message)
    for event in session.exec(
        select(ResearchRunEvent).where(ResearchRunEvent.report_id == report_id)
    ).all():
        session.delete(event)
    session.delete(report)
    session.commit()
    return {"ok": True}


def _extract_bullets(md: str, headings: tuple) -> List[str]:
    """提取给定标题（如「行动项」「主要风险」）下的清单条目。"""
    heading_re = re.compile(
        r'^#{1,3}\s+(' + "|".join(re.escape(x) for x in headings) + r')\s*$',
        re.IGNORECASE,
    )
    next_heading_re = re.compile(r'^#{1,3}\s+')
    list_re = re.compile(r'^\s*(?:[-*+]|\d+\.)\s+(.+)')
    in_section = False
    out: List[str] = []
    for line in md.splitlines():
        s = line.strip()
        if heading_re.match(s):
            in_section = True
            continue
        if in_section:
            if next_heading_re.match(s) and not heading_re.match(s):
                break
            m = list_re.match(line)
            if m:
                out.append(m.group(1).strip())
    return out


def _extract_action_items(report_md: str) -> List[str]:
    return _extract_bullets(report_md, ("行动项", "Action Items"))


def _tracking_candidates(report: ResearchReport) -> List[Dict[str, Any]]:
    structured = {}
    try:
        structured = json.loads(report.report_json or "{}")
    except (TypeError, ValueError):
        structured = {}
    return research_structured.tracking_candidates(report.report_md, structured)


@router.get("/reports/{report_id}/tracking-candidates")
def list_tracking_candidates(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """预览跟踪事项；用户勾选/编辑后才写入决策日志。"""
    report = _owned(session, report_id, user)
    if not report.report_md:
        raise HTTPException(400, "报告尚未生成，无法提取跟踪事项")
    existing = session.exec(
        select(Note).where(
            Note.user_id == user.id,
            Note.source_report_id == report_id,
            Note.note_type == "action",
        )
    ).all()
    return {
        "items": _tracking_candidates(report),
        "existing": [n.model_dump() for n in existing],
        "report_version": report.version,
        "note": (
            "只保存用户选择的条目；没有明确日期的条目不会编造复查日期，"
            "“下一次财报后”等会保存为事件条件。"
        ),
    }


@router.post("/reports/{report_id}/tracking-notes")
def generate_tracking_notes(
    report_id: int,
    data: Optional[TrackingSaveRequest] = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """保存用户选择的跟踪事项（复用 Note）。

    无 body 时保留旧接口行为（保存全部提取项），便于已有调用兼容；新界面始终
    先预览并提交勾选结果。
    """
    report = _owned(session, report_id, user)
    if not report.report_md:
        raise HTTPException(400, "报告尚未生成，无法提取行动项")

    existing = session.exec(
        select(Note).where(
            Note.user_id == user.id,
            Note.source_report_id == report_id,
            Note.note_type == "action",
        )
    ).all()
    if existing:
        return {"reused": True, "created": False, "notes": [n.model_dump() for n in existing]}

    if data is not None:
        items = [
            {
                "text": item.text,
                "metric": item.metric,
                "review_date": item.review_date,
                "trigger_condition": item.trigger_condition,
                "symbol": item.symbol,
                "status": item.status,
            }
            for item in data.items
            if item.text.strip()
        ]
    else:
        items = _tracking_candidates(report)
    if not items:
        raise HTTPException(400, "未找到可保存的跟踪事项（行动项/跟踪指标章节）")

    symbol = report.symbol
    if not symbol and report.related_holding_id:
        h = session.get(Holding, report.related_holding_id)
        if h and h.user_id == user.id and h.symbol:
            symbol = h.symbol

    report_date = (report.created_at or datetime.utcnow()).strftime("%Y-%m-%d")
    source_label = report.title or report.target_name or f"报告#{report_id}"

    notes: List[Note] = []
    holdings = session.exec(select(Holding).where(Holding.user_id == user.id)).all()
    for item in items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        item_symbol = item.get("symbol") or symbol
        item_holding_id = report.related_holding_id
        if report.template_key == "portfolio-review":
            matches = re.findall(r"\b(A|HK|US|FUND|CRYPTO):([A-Za-z0-9.\-]+)", text)
            matched = [h for h in holdings if (h.market.value, h.symbol) in matches]
            if len({(h.market, h.symbol) for h in matched}) == 1:
                item_symbol = matched[0].symbol
                item_holding_id = matched[0].id if len(matched) == 1 else None
        title = text[:40] + ("…" if len(text) > 40 else "")
        content = f"{text}\n\n---\n来源：{source_label}（{report_date}，v{report.version}）"
        review_date = item.get("review_date")
        if review_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(review_date)):
            # Never silently keep a malformed/guessed date.
            review_date = None
        note = Note(
            user_id=user.id,
            title=title,
            content=content,
            note_type="action",
            status=item.get("status") or "active",
            source_report_id=report_id,
            related_holding_id=item_holding_id,
            symbol=item_symbol,
            metric=item.get("metric"),
            review_date=review_date,
            trigger_condition=item.get("trigger_condition"),
            report_version=report.version,
        )
        session.add(note)
        notes.append(note)

    session.commit()
    for n in notes:
        session.refresh(n)

    return {"reused": False, "created": True, "notes": [n.model_dump() for n in notes]}


@router.post("/reports/{report_id}/cancel")
def cancel_report(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    if report.status not in ("running", "queued"):
        return {"ok": True, "message": "任务已结束，无需取消"}
    if report.execution_mode == "multi_agent":
        engine = session.get_bind()
        result = research_jobs.cancel(engine, report.id, user.id)
        session.expire_all()
        return result

    # Standard background task: stop its polling loop before provider cancel,
    # so a late provider response cannot overwrite the cancelled status.
    research_jobs.request_cancel(report.id)

    # 解析 BYOK 配置用于 cancel
    from research_service import _resolve_report_ai_key
    from ai_client import cancel_response, AIServiceNotConfigured

    user_api_key = None
    provider = report.provider
    if report.user_ai_key_id is not None:
        try:
            user_api_key, provider = _resolve_report_ai_key(session, report)
        except AIServiceNotConfigured:
            # Key 不可用但 cancel 仍执行（标记为平台侧取消）
            pass

    cancelled_provider = False
    if report.provider_response_id:
        cancelled_provider = cancel_response(
            report.provider_response_id,
            api_key=user_api_key,
            provider=provider,
        )

    report.status = "cancelled"
    report.completed_at = datetime.utcnow()
    report.updated_at = datetime.utcnow()
    if not cancelled_provider:
        report.error_message = "已在平台侧标记取消（Provider 不支持或取消失败）"
    research_events.append_event(
        session, report, "cancelled", "cancelled",
        report.error_message or "Provider 已确认取消",
        {"provider_cancelled": cancelled_provider}, commit=False)
    session.add(report)
    session.commit()
    return {"ok": True, "provider_cancelled": cancelled_provider}
