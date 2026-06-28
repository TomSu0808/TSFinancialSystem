"""投研工作台路由：模板列表、AI 投研任务、报告 CRUD（按用户隔离）。"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models import Holding, HoldingStatus, Note, ResearchReport, ResearchReportCreate, ResearchReportUpdate, ResearchRunCreate, User
from models import Currency, cost_basis, market_value, profit
from ai_berkshire_loader import list_skills
import research_service
from ai_client import AIServiceNotConfigured

router = APIRouter(prefix="/api/research", tags=["research"])


def _owned(session: Session, report_id: int, user: User) -> ResearchReport:
    report = session.get(ResearchReport, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(404, "报告不存在")
    return report


def _holding_context(h: Holding) -> str:
    mv = market_value(h)
    cb = cost_basis(h)
    pnl = profit(h)
    pnl_str = f"{pnl:+.2f} {h.currency.value}" if pnl is not None else "—"
    cost_str = f"{cb:.2f} {h.currency.value}" if cb is not None else "—"
    lines = [
        "",
        "## 持仓数据（平台自动填入）",
        f"- **名称**：{h.name}  **代码**：{h.symbol or '—'}  **市场**：{h.market.value}  **币种**：{h.currency.value}",
        f"- **数量**：{h.quantity or '—'}  **成本价**：{h.cost_price or '—'}  **现价**：{h.current_price or '—'}",
        f"- **成本合计**：{cost_str}  **市值**：{mv:.2f} {h.currency.value}",
        f"- **未实现盈亏**：{pnl_str}  **已实现盈亏**：{h.realized_pnl:+.2f} {h.currency.value}",
        "",
    ]
    return "\n".join(lines)


HKD_PEG = 7.8


def _get_to_cny_rates(session: Session) -> tuple:
    """返回 (to_cny_dict, usdcny, fx_updated_at)。"""
    from models import FxRate
    fx = session.exec(select(FxRate).where(FxRate.pair == "USDCNY")).first()
    usdcny = fx.rate if fx else 7.2
    fx_updated_at = fx.updated_at.isoformat() if fx and fx.updated_at else "unknown"
    to_cny = {
        Currency.CNY: 1.0,
        Currency.USD: usdcny,
        Currency.HKD: usdcny / HKD_PEG,
    }
    return to_cny, usdcny, fx_updated_at


def _portfolio_context(holdings: List[Holding], session: Session) -> str:
    """生成 Portfolio Review 持仓上下文（CNY 统一折算口径）。"""
    if not holdings:
        return "\n**（当前无持仓数据）**\n"

    to_cny, usdcny, fx_updated_at = _get_to_cny_rates(session)

    rows_data = []
    total_cny = 0.0
    for h in holdings:
        mv_native = market_value(h)
        rate = to_cny.get(h.currency, 1.0)
        mv_cny = mv_native * rate
        pnl = profit(h)
        pnl_cny = pnl * rate if pnl is not None else None
        total_cny += mv_cny
        rows_data.append({
            "h": h, "mv_native": mv_native, "mv_cny": mv_cny,
            "pnl": pnl, "pnl_cny": pnl_cny,
        })

    rows = []
    for d in rows_data:
        h = d["h"]
        mv_native = d["mv_native"]
        pnl = d["pnl"]
        w = (d["mv_cny"] / total_cny * 100) if total_cny else 0
        if h.currency == Currency.CNY:
            mv_str = f"{mv_native:.0f} CNY"
        else:
            mv_str = f"{mv_native:.0f} {h.currency.value}（≈{d['mv_cny']:.0f} CNY）"
        pnl_str = f"{pnl:+.2f} {h.currency.value}" if pnl is not None else "—"
        rows.append(
            f"| {h.name} | {h.symbol or '—'} | {h.market.value} | {h.currency.value} "
            f"| {h.quantity or '—'} | {h.cost_price or '—'} | {h.current_price or '—'} "
            f"| {mv_str} | {pnl_str} | {w:.1f}% |"
        )

    header = (
        "\n## 当前持仓（平台自动填入，CNY 统一折算口径）\n\n"
        "| 名称 | 代码 | 市场 | 币种 | 数量 | 成本价 | 现价 | 市值 | 未实现盈亏 | 占比(CNY) |\n"
        "|------|------|------|------|------|-------|------|------|-----------|----------|\n"
    )

    fx_info = (
        f"\n**汇率信息**：USD/CNY = {usdcny:.4f}，HKD/CNY ≈ {usdcny / HKD_PEG:.4f}（联系汇率≈7.8 HKD/USD）\n"
        f"**汇率更新时间**：{fx_updated_at}\n"
    )

    disclaimer = (
        "\n> ⚠️ **数据说明**：以上市值为持仓原币种金额及按 CNY 折算近似值；"
        "组合占比基于 CNY 折算市值计算；行情非实时数据；汇率非实时更新。"
        "请勿将 AI 输出视为确定性投资建议。\n"
    )

    return (
        header
        + "\n".join(rows)
        + f"\n\n**组合总市值（CNY 折算）：约 {total_cny:,.0f} CNY**"
        + fx_info
        + disclaimer
    )


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
        )
    except AIServiceNotConfigured as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except PermissionError as exc:
        raise HTTPException(404, str(exc))


@router.post("/runs/{report_id}/refresh", response_model=ResearchReport)
def refresh_run(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    report = _owned(session, report_id, user)
    return research_service.refresh_run(session, report)


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
        portfolio_ctx = _portfolio_context(list(holdings), session)
    elif req.holding_id is not None:
        h = session.get(Holding, req.holding_id)
        if not h or h.user_id != user.id:
            raise HTTPException(404, "持仓不存在")
        holding_ctx = _holding_context(h)

    prompt = research_prompt_builder.build_prompt(
        skill_md=skill_md,
        target_name=req.target_name or "目标公司",
        symbol=req.symbol or "",
        market=req.market or "",
        holding_ctx=holding_ctx,
        portfolio_ctx=portfolio_ctx,
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
    session.delete(report)
    session.commit()
    return {"ok": True}


def _extract_action_items(report_md: str) -> List[str]:
    """从报告 Markdown 中提取行动项清单（支持中文"行动项"和英文"Action Items"）。"""
    heading_re = re.compile(r'^#{1,3}\s+(行动项|Action\s+Items)\s*$', re.IGNORECASE)
    next_heading_re = re.compile(r'^#{1,3}\s+')
    list_item_re = re.compile(r'^\s*(?:[-*+]|\d+\.)\s+(.+)')

    in_section = False
    items: List[str] = []
    for line in report_md.splitlines():
        stripped = line.strip()
        if heading_re.match(stripped):
            in_section = True
            continue
        if in_section:
            if next_heading_re.match(stripped) and not heading_re.match(stripped):
                break
            m = list_item_re.match(line)
            if m:
                items.append(m.group(1).strip())
    return items


@router.post("/reports/{report_id}/tracking-notes")
def generate_tracking_notes(
    report_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """从 AI 报告的「行动项」章节生成跟踪事项（Note）。重复调用返回已有记录。"""
    report = _owned(session, report_id, user)
    if not report.report_md:
        raise HTTPException(400, "报告尚未生成，无法提取行动项")

    # 防止重复创建：已存在则直接返回
    existing = session.exec(
        select(Note).where(
            Note.user_id == user.id,
            Note.source_report_id == report_id,
            Note.note_type == "action",
        )
    ).all()
    if existing:
        return {"reused": True, "created": False, "notes": [n.model_dump() for n in existing]}

    items = _extract_action_items(report.report_md)
    if not items:
        raise HTTPException(400, "报告中未找到「行动项」或「Action Items」章节，无法提取跟踪事项")

    # 确定 symbol
    symbol = report.symbol
    if not symbol and report.related_holding_id:
        h = session.get(Holding, report.related_holding_id)
        if h and h.user_id == user.id and h.symbol:
            symbol = h.symbol

    report_date = (report.created_at or datetime.utcnow()).strftime("%Y-%m-%d")
    source_label = report.title or report.target_name or f"报告#{report_id}"

    notes: List[Note] = []
    for item in items:
        title = item[:40] + ("…" if len(item) > 40 else "")
        content = f"{item}\n\n---\n来源：{source_label}（{report_date}）"
        note = Note(
            user_id=user.id,
            title=title,
            content=content,
            note_type="action",
            status="active",
            source_report_id=report_id,
            related_holding_id=report.related_holding_id,
            symbol=symbol,
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
    session.add(report)
    session.commit()
    return {"ok": True, "provider_cancelled": cancelled_provider}
