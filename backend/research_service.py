"""投研服务层：加载模板 → 解析标的 → 构建快照 → 调用 AI/Worker → 结构化归档。"""
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlmodel import Session, select

import ai_client
import portfolio_context
import research_events
import research_jobs
import research_prompt_builder
import research_structured
import research_target
import research_usage
import tradingagents_adapter
from ai_client import AIServiceNotConfigured
from ai_berkshire_loader import get_skill_meta, load_skill
from config import ALLOW_SYSTEM_AI_FALLBACK
from crypto_utils import decrypt_secret
from models import (
    Currency, Holding, HoldingStatus, Note, Platform, ResearchPreference,
    ResearchReport, User, UserAIKey, cost_basis, market_value, profit,
)

_EN_TEMPLATE_TITLES = {
    "investment-research": "Deep Company Research",
    "investment-team": "Investment Committee Discussion",
    "investment-checklist": "Pre-Buy Checklist",
    "dyp-ask": "Duan Yongping Questions",
    "earnings-review": "Earnings Deep Dive",
    "earnings-team": "Earnings Committee Discussion",
    "financial-data": "Financial Data Gathering",
    "management-deep-dive": "Management Deep Dive",
    "quality-screen": "Quality Score",
    "industry-research": "Industry Analysis",
    "industry-funnel": "Industry Opportunity Funnel",
    "portfolio-review": "Portfolio Review",
    "thesis-tracker": "Thesis Tracker",
    "news-pulse": "News Pulse",
}


def _holding_context(h: Holding, session: Session) -> str:
    platform = session.get(Platform, h.platform_id)
    platform_name = platform.name if platform else "missing"
    mv = market_value(h)
    cb = cost_basis(h)
    pnl = profit(h)
    return "\n".join([
        "",
        "## 持仓数据（平台自动填入）",
        f"- **名称**：{h.name}  **代码**：{h.symbol or '—'}  **市场**：{h.market.value}  **币种**：{h.currency.value}",
        f"- **资产类型**：{h.asset_type.value}  **平台**：{platform_name}",
        f"- **数量**：{h.quantity if h.quantity is not None else 'missing'}  "
        f"**成本价**：{h.cost_price if h.cost_price is not None else 'missing'}  "
        f"**现价**：{h.current_price if h.current_price is not None else 'missing'}",
        f"- **成本合计**：{f'{cb:.2f} {h.currency.value}' if cb is not None else 'missing'}  "
        f"**市值**：{mv:.2f} {h.currency.value}",
        f"- **未实现盈亏**：{f'{pnl:+.2f} {h.currency.value}' if pnl is not None else 'missing'}  "
        f"**已实现盈亏**：{h.realized_pnl:+.2f} {h.currency.value}  "
        f"**分红收益**：{h.realized_income:+.2f} {h.currency.value}",
        f"- **来源**：{h.source.value}  **状态**：{h.status.value}",
        f"- **行情获取时间**：{h.price_updated_at.isoformat() if h.price_updated_at else '未知'}",
        "",
    ])


def _portfolio_context(holdings: List[Holding], session: Session) -> str:
    """旧组合上下文构造器（保留给已有调用/测试）。"""
    if not holdings:
        return "\n**（当前无持仓数据）**\n"
    to_cny, usdcny, fx_updated_at = portfolio_context.get_to_cny_rates(session)
    rows_data = []
    total_cny = 0.0
    for h in holdings:
        mv_native = market_value(h)
        rate = to_cny.get(h.currency, 1.0)
        mv_cny = mv_native * rate
        pnl = profit(h)
        total_cny += mv_cny
        rows_data.append({"h": h, "mv_native": mv_native, "mv_cny": mv_cny, "pnl": pnl})
    rows = []
    for d in rows_data:
        h = d["h"]
        w = (d["mv_cny"] / total_cny * 100) if total_cny else 0
        rows.append(
            f"| {h.name} | {h.symbol or '—'} | {h.market.value} | {h.currency.value} "
            f"| {h.quantity if h.quantity is not None else '—'} "
            f"| {h.cost_price if h.cost_price is not None else '—'} "
            f"| {h.current_price if h.current_price is not None else '—'} "
            f"| {d['mv_native']:.0f} | "
            f"{d['pnl']:+.2f} | {w:.1f}% |" if d["pnl"] is not None else
            f"| {h.name} | {h.symbol or '—'} | {h.market.value} | {h.currency.value} "
            f"| {h.quantity if h.quantity is not None else '—'} "
            f"| {h.cost_price if h.cost_price is not None else '—'} "
            f"| {h.current_price if h.current_price is not None else '—'} "
            f"| {d['mv_native']:.0f} | — | {w:.1f}% |"
        )
    return (
        "\n## 当前持仓（平台自动填入，CNY 统一折算口径）\n\n"
        "| 名称 | 代码 | 市场 | 币种 | 数量 | 成本价 | 现价 | 市值 | 未实现盈亏 | 占比(CNY) |\n"
        "|------|------|------|------|------|-------|------|------|-----------|----------|\n"
        + "\n".join(rows)
        + f"\n\n**组合总市值（CNY 折算）：约 {total_cny:,.0f} CNY**"
        + f"\n\n**汇率信息**：USD/CNY = {usdcny:.4f}，HKD/CNY ≈ {usdcny / portfolio_context.HKD_PEG:.4f}\n"
        + f"**汇率更新时间**：{fx_updated_at}\n"
        + "\n> 数据说明：行情和汇率可能延迟，均非实时数据；请勿把 AI 输出视为确定性投资建议。\n"
    )


def _get_user_ai_key(session: Session, user_id: int, provider: str) -> Optional[UserAIKey]:
    return session.exec(
        select(UserAIKey).where(UserAIKey.user_id == user_id, UserAIKey.provider == provider)
    ).first()


def _get_user_default_ai_key(session: Session, user_id: int) -> Optional[UserAIKey]:
    return session.exec(
        select(UserAIKey).where(UserAIKey.user_id == user_id, UserAIKey.is_default == True)  # noqa: E712
    ).first()


def _resolve_ai(
    session: Session,
    user: User,
    ai_provider: Optional[str],
    ai_model: Optional[str],
    preferred_key_id: Optional[int] = None,
) -> Tuple[str, Optional[UserAIKey], Optional[str], Optional[str], str]:
    provider = ai_client.normalize_provider(ai_provider)
    user_key: Optional[UserAIKey] = None
    if preferred_key_id:
        candidate = session.get(UserAIKey, preferred_key_id)
        if candidate and candidate.user_id == user.id:
            user_key = candidate
            provider = candidate.provider
    if user_key is None and ai_provider:
        user_key = _get_user_ai_key(session, user.id, provider)
    if user_key is None and not ai_provider:
        user_key = _get_user_default_ai_key(session, user.id)
        if user_key is None:
            user_key = _get_user_ai_key(session, user.id, provider)
        if user_key is None:
            available = session.exec(select(UserAIKey).where(UserAIKey.user_id == user.id)).all()
            if len(available) == 1:
                user_key = available[0]
        if user_key:
            provider = user_key.provider

    user_api_key: Optional[str] = None
    user_base_url: Optional[str] = None
    if user_key:
        user_api_key = decrypt_secret(user_key.encrypted_api_key)
        user_base_url = user_key.base_url
    elif ALLOW_SYSTEM_AI_FALLBACK:
        if not ai_client.is_configured(provider):
            raise AIServiceNotConfigured(
                f"{provider} service is not configured. Set the provider API key in backend/.env "
                "for local development, or with your host's environment/secrets system in production "
                "(for Fly.io, use `fly secrets set`)."
            )
    else:
        raise AIServiceNotConfigured(
            f"请先在个人资料 → AI 设置中配置你的 {provider.upper()} API Key。"
        )

    effective_model = ai_model or (user_key.default_model if user_key else None)
    model = ai_client.choose_model(provider, effective_model)
    return provider, user_key, user_api_key, user_base_url, model


def get_preferences(session: Session, user: User) -> Optional[ResearchPreference]:
    return session.exec(
        select(ResearchPreference).where(ResearchPreference.user_id == user.id)
    ).first()


def save_preferences(session: Session, user: User, data: Dict[str, Any]) -> ResearchPreference:
    pref = get_preferences(session, user)
    if pref is None:
        pref = ResearchPreference(user_id=user.id)
    for key in ("investment_goal", "holding_period", "risk_preference"):
        if key in data:
            setattr(pref, key, data[key])
    pref.updated_at = datetime.utcnow()
    session.add(pref)
    session.commit()
    session.refresh(pref)
    return pref


def _preferences_text(session: Session, user: User) -> str:
    pref = get_preferences(session, user)
    if not pref:
        return ""
    parts = []
    if pref.investment_goal:
        parts.append(f"投资目标：{pref.investment_goal}")
    if pref.holding_period:
        parts.append(f"持有周期：{pref.holding_period}")
    if pref.risk_preference:
        parts.append(f"风险偏好：{pref.risk_preference}")
    return "；".join(parts)


def _relevant_notes(session: Session, user: User, holding: Optional[Holding], symbol: str, limit: int = 6) -> List[Note]:
    stmt = select(Note).where(Note.user_id == user.id)
    if holding is not None and symbol:
        stmt = stmt.where(or_(
            Note.related_holding_id == holding.id,
            Note.symbol == symbol,
        ))
    elif holding is not None:
        stmt = stmt.where(Note.related_holding_id == holding.id)
    elif symbol:
        stmt = stmt.where(Note.symbol == symbol)
    else:
        return []
    return list(session.exec(stmt.order_by(Note.updated_at.desc()).limit(limit)).all())


def _prior_reports(
    session: Session,
    user: User,
    holding: Optional[Holding],
    symbol: str,
    limit: int = 3,
    exclude_report_id: Optional[int] = None,
) -> List[ResearchReport]:
    if not symbol and holding is None:
        return []
    stmt = select(ResearchReport).where(
        ResearchReport.user_id == user.id,
        ResearchReport.status == "completed",
        # Do not feed a just-created report back into a duplicate submission.
        ResearchReport.created_at < datetime.utcnow() - timedelta(minutes=5),
    )
    if exclude_report_id is not None:
        stmt = stmt.where(ResearchReport.id != exclude_report_id)
    if holding is not None and symbol:
        stmt = stmt.where(or_(
            ResearchReport.related_holding_id == holding.id,
            ResearchReport.symbol == symbol,
        ))
    elif holding is not None:
        stmt = stmt.where(ResearchReport.related_holding_id == holding.id)
    else:
        stmt = stmt.where(ResearchReport.symbol == symbol)
    return list(session.exec(stmt.order_by(ResearchReport.created_at.desc()).limit(limit)).all())


def _history_context(
    session: Session,
    user: User,
    holding: Optional[Holding],
    symbol: str,
    enabled: bool,
    exclude_report_id: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    if not enabled or (holding is None and not symbol):
        return "", {"notes": 0, "prior_reports": 0}
    notes = _relevant_notes(session, user, holding, symbol)
    reports = _prior_reports(session, user, holding, symbol, exclude_report_id=exclude_report_id)
    lines = []
    if notes:
        lines.append("## 相关决策日志与笔记（用户历史记录，非外部事实）")
        for note in notes:
            body = (note.content or "").replace("\n", " ").strip()
            lines.append(
                f"- [{note.note_type}/{note.status}] {note.title or note.symbol or '笔记'}："
                f"{body[:240]}"
            )
    if reports:
        lines.append("## 历史研究报告（旧结论，需重新核验）")
        for report in reports:
            summary = ""
            try:
                parsed = json.loads(report.report_json or "{}")
                summary = parsed.get("summary") or ""
            except (TypeError, ValueError):
                pass
            lines.append(
                f"- 报告 #{report.id}（{report.created_at.strftime('%Y-%m-%d') if report.created_at else '日期未知'}）"
                f"{report.title}：{summary[:240] or '无结构化摘要，请查阅原报告'}"
            )
    if not lines:
        return "", {"notes": 0, "prior_reports": 0}
    return "\n\n" + "\n".join(lines) + "\n", {"notes": len(notes), "prior_reports": len(reports)}


def _portfolio_history_context(
    session: Session,
    user: User,
    exclude_report_id: Optional[int] = None,
) -> Tuple[str, int]:
    stmt = select(ResearchReport).where(
        ResearchReport.user_id == user.id,
        ResearchReport.template_key == "portfolio-review",
        ResearchReport.status == "completed",
        ResearchReport.created_at < datetime.utcnow() - timedelta(minutes=5),
    )
    if exclude_report_id is not None:
        stmt = stmt.where(ResearchReport.id != exclude_report_id)
    reports = list(session.exec(
        stmt.order_by(ResearchReport.created_at.desc()).limit(3)
    ).all())
    if not reports:
        return "", 0
    lines = ["", "## 历史组合研究（旧结论，需重新核验）"]
    for report in reports:
        summary = ""
        try:
            parsed = json.loads(report.report_json or "{}")
            summary = parsed.get("summary") or ""
        except (TypeError, ValueError):
            pass
        lines.append(
            f"- 报告 #{report.id}（{report.created_at.strftime('%Y-%m-%d') if report.created_at else '日期未知'}）"
            f"{report.title}：{summary[:240] or '无结构化摘要，请查阅原报告'}"
        )
    return "\n".join(lines) + "\n", len(reports)


def _data_missing(session: Session, user: User, holding: Optional[Holding], is_portfolio: bool) -> Dict[str, Any]:
    if is_portfolio:
        return research_target.preview_holdings_summary(session, user)
    if not holding:
        return {
            "holding_count": 0, "currencies": [], "missing_price_count": 0,
            "missing_cost_count": 0, "missing_price_names": [], "missing_cost_names": [],
        }
    missing = []
    if holding.current_price is None and holding.manual_value is None:
        missing.append("缺少现价/手填市值")
    if cost_basis(holding) is None:
        missing.append("缺少成本")
    if not holding.symbol:
        missing.append("缺少证券代码")
    if holding.market.value == "NONE":
        missing.append("市场为 NONE，无法抓取行情")
    return {
        "holding_count": 1,
        "currencies": [holding.currency.value],
        "missing_price_count": 1 if holding.current_price is None and holding.manual_value is None else 0,
        "missing_cost_count": 1 if cost_basis(holding) is None else 0,
        "missing_fields": missing,
    }


def _validate_execution(
    target: Optional[Dict[str, Any]],
    template_key: str,
    execution_mode: str,
) -> None:
    if execution_mode not in ("standard", "multi_agent"):
        raise ValueError("execution_mode 只能是 standard 或 multi_agent")
    if execution_mode != "multi_agent":
        return
    if template_key != "investment-team":
        raise ValueError("多 Agent 协作只适用于「投资委员会讨论」模板；其他模板请使用标准研究")
    if not target:
        raise ValueError("多 Agent 研究需要明确的单一标的，不能用于组合分析")
    ok, reason = research_target.multi_agent_support(
        target.get("asset_type") or "stock",
        target.get("market") or "",
        target.get("symbol") or "",
    )
    if not ok:
        raise ValueError(reason)
    # Raises when the symbol cannot be mapped safely.
    research_target.to_yahoo_ticker(
        target.get("symbol") or "",
        target.get("market") or "",
        target.get("asset_type") or "stock",
    )


def _not_supported_multi_agent_preview(target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not target:
        return {"supported": False, "reason": "组合分析不支持多 Agent 模式"}
    ok, reason = research_target.multi_agent_support(
        target.get("asset_type") or "stock",
        target.get("market") or "",
        target.get("symbol") or "",
    )
    ticker = None
    if ok:
        try:
            ticker = research_target.to_yahoo_ticker(
                target.get("symbol") or "",
                target.get("market") or "",
                target.get("asset_type") or "stock",
            )
        except ValueError as exc:
            ok, reason = False, str(exc)
    return {"supported": ok, "reason": reason, "ticker": ticker}


def build_preview(
    session: Session,
    user: User,
    template_key: str,
    target_name: Optional[str],
    symbol: Optional[str],
    market: Optional[str],
    related_holding_id: Optional[int],
    report_language: str,
    display_currency: Currency,
    execution_mode: str,
    include_holding_context: bool,
    use_web_search: bool,
    ai_provider: Optional[str] = None,
) -> Dict[str, Any]:
    is_portfolio = template_key == "portfolio-review"
    target: Optional[Dict[str, Any]] = None
    if not is_portfolio:
        target = research_target.resolve_target(
            session, user, target_name, symbol, market, related_holding_id)
        if template_key == "thesis-tracker" and target.get("holding") is None:
            raise ValueError("投资论文追踪需要选择一个已有持仓")
    _validate_execution(target, template_key, execution_mode)

    holding = target.get("holding") if target else None
    data_cutoff = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    context_md = ""
    if include_holding_context:
        if is_portfolio:
            context_md = portfolio_context.build_account_context(session, user, display_currency)
        elif holding is not None:
            context_md = _holding_context(holding, session)
    if is_portfolio and include_holding_context:
        history_md, prior_count = _portfolio_history_context(
            session, user, exclude_report_id=(parent_report.id if parent_report else None))
        note_count = len(session.exec(select(Note).where(
            Note.user_id == user.id,
            Note.note_type.in_(["thesis", "risk", "review", "observation"]),
        )).all())
        history_counts = {"notes": note_count, "prior_reports": prior_count}
    else:
        history_md, history_counts = _history_context(
            session, user, holding,
            (target or {}).get("symbol") or "",
            include_holding_context,
        )
    context_md = (context_md or "") + history_md
    missing = _data_missing(session, user, holding, is_portfolio)
    prefs = get_preferences(session, user)
    warnings = list((target or {}).get("warnings") or [])
    if include_holding_context and holding is not None:
        if holding.current_price is None and holding.manual_value is None:
            warnings.append("关联持仓缺少现价或手填市值，报告中的估值/盈亏可能未知。")
        if holding.market.value == "NONE":
            warnings.append("该持仓市场为 NONE，无法自动抓取行情。")
    if is_portfolio and not include_holding_context:
        warnings.append("组合复盘必须携带持仓数据；提交前请开启。")
    if execution_mode == "multi_agent":
        meta = {} if is_portfolio else None
    if execution_mode == "multi_agent" and target:
        ta_info = research_target.build_ta_portfolio(session, user, target) if include_holding_context else {
            "target_ticker": research_target.to_yahoo_ticker(
                target.get("symbol") or "", target.get("market") or "",
                target.get("asset_type") or "stock"),
            "excluded_holdings": [],
            "limitations": ["用户选择不携带个人持仓；组合输入为空。"],
        }
    else:
        ta_info = {}
    multi_preview = {"supported": True, "reason": "", "ticker": None}
    if execution_mode == "multi_agent" and target:
        engine = tradingagents_adapter.probe_engine()
        multi_preview = {
            "supported": bool(engine.get("available")),
            "reason": "" if engine.get("available") else (
                "TradingAgents 引擎不可用：" + str(engine.get("error") or "未安装")),
            "ticker": ta_info.get("target_ticker"),
            "engine_version": engine.get("version"),
            "excluded_holdings": ta_info.get("excluded_holdings", []),
            "limitations": ta_info.get("limitations", []),
        }
    includes = {
        "holdings": bool(include_holding_context and (is_portfolio or holding is not None)),
        "cost": bool(include_holding_context and (
            is_portfolio or (holding is not None and cost_basis(holding) is not None))),
        "cash": bool(include_holding_context and (
            is_portfolio or (holding is not None and holding.asset_type.value == "cash"))),
        "notes": history_counts["notes"],
        "prior_reports": history_counts["prior_reports"],
        "display_currency": display_currency.value,
    }
    preview_provider = ai_client.normalize_provider(ai_provider)
    return {
        "template_key": template_key,
        "target": {
            "name": (target or {}).get("target_name") or "全账户投资组合",
            "symbol": (target or {}).get("symbol"),
            "market": (target or {}).get("market"),
            "currency": (target or {}).get("currency"),
            "source": (target or {}).get("identity_source"),
            "holding_id": holding.id if holding else None,
        },
        "report_language": report_language,
        "execution_mode": execution_mode,
        "execution_label": "多 Agent 协作（TradingAgents）" if execution_mode == "multi_agent" else "标准研究",
        "data_cutoff": data_cutoff,
        "include_holding_context": include_holding_context,
        "includes": includes,
        "missing": missing,
        "warnings": warnings,
        "preferences": ({
            "investment_goal": prefs.investment_goal if prefs else None,
            "holding_period": prefs.holding_period if prefs else None,
            "risk_preference": prefs.risk_preference if prefs else None,
        }),
        "web_search": {
            "requested": bool(use_web_search),
            "provider": preview_provider,
            "provider_supports": ai_client.provider_supports_web_search(preview_provider),
            "note": (
                "联网开关只表示向 Provider 请求检索，不等于检索成功。"
                if execution_mode != "multi_agent" else
                "多 Agent 使用 TradingAgents 配置的数据工具，来源可访问性仍需自行核验。"
            ),
        },
        "multi_agent": multi_preview,
        "context_preview_md": (context_md or "")[:16000],
    }


_DEDUPE_TIMESTAMP_RE = re.compile(
    r'(?m)^(?:.*?(?:数据截止/快照时点|Data cutoff / snapshot|分析时点)[^\n]*|.*?"data_cutoff"\s*:\s*"[^"]*".*)$'
)


def _dedupe_fingerprint(text: str) -> str:
    """Remove the volatile snapshot timestamp so clicks seconds apart dedupe."""
    return _DEDUPE_TIMESTAMP_RE.sub("", text or "")


def _idempotency_key(
    user_id: int,
    template_key: str,
    target: Optional[Dict[str, Any]],
    provider: str,
    model: str,
    prompt_md: str,
    execution_mode: str,
    parent_report_id: Optional[int],
    explicit: Optional[str],
) -> str:
    if explicit:
        return f"client:{explicit}"
    raw = "|".join([
        str(user_id), template_key, (target or {}).get("symbol") or "",
        (target or {}).get("market") or "", provider, model, execution_mode,
        str(parent_report_id or ""), _dedupe_fingerprint(prompt_md),
    ])
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_existing(session: Session, user_id: int, key: str) -> Optional[ResearchReport]:
    return session.exec(
        select(ResearchReport).where(
            ResearchReport.user_id == user_id,
            ResearchReport.idempotency_key == key,
            ResearchReport.created_at >= datetime.utcnow() - timedelta(minutes=10),
            ResearchReport.status.in_(["queued", "running", "completed"]),
        ).order_by(ResearchReport.id.desc())
    ).first()


def _build_input_snapshot(
    *,
    target: Optional[Dict[str, Any]],
    is_portfolio: bool,
    template_key: str,
    execution_mode: str,
    include_holding_context: bool,
    display_currency: Currency,
    data_cutoff: str,
    missing: Dict[str, Any],
    history_counts: Dict[str, Any],
    preferences: str,
    use_web_search: bool,
    provider: Optional[str],
    report_mode: str,
    parent_report_id: Optional[int],
    ta_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": report_mode,
        "template_key": template_key,
        "execution_mode": execution_mode,
        "target": {
            "name": (target or {}).get("target_name") or "全账户投资组合",
            "symbol": (target or {}).get("symbol"),
            "market": (target or {}).get("market"),
            "currency": (target or {}).get("currency"),
            "holding_id": ((target or {}).get("holding").id
                           if (target or {}).get("holding") else None),
            "identity_source": (target or {}).get("identity_source"),
        },
        "data_cutoff": data_cutoff,
        "display_currency": display_currency.value,
        "include_holding_context": include_holding_context,
        "includes": {
            "holdings": bool(include_holding_context and (is_portfolio or (target or {}).get("holding"))),
            "cost": bool(include_holding_context and (
                is_portfolio or (
                    (target or {}).get("holding") is not None
                    and cost_basis((target or {}).get("holding")) is not None
                ))),
            "cash": bool(include_holding_context and is_portfolio),
            "notes": history_counts.get("notes", 0),
            "prior_reports": history_counts.get("prior_reports", 0),
        },
        "missing": missing,
        "preferences": preferences,
        "web_search": {
            "requested": bool(use_web_search),
            "provider": provider,
            "provider_supports": ai_client.provider_supports_web_search(provider),
        },
        "parent_report_id": parent_report_id,
        "multi_agent": ta_info or None,
    }


def create_run(
    session: Session,
    user: User,
    template_key: str,
    target_name: Optional[str],
    symbol: Optional[str],
    market: Optional[str],
    related_holding_id: Optional[int],
    report_language: str,
    ai_provider: Optional[str],
    ai_model: Optional[str],
    extra_instruction: Optional[str],
    use_web_search: bool,
    display_currency: Currency = Currency.CNY,
    execution_mode: str = "standard",
    include_holding_context: bool = True,
    idempotency_key: Optional[str] = None,
    parent_report: Optional[ResearchReport] = None,
    report_mode: str = "new",
) -> ResearchReport:
    skill_md = load_skill(template_key)
    skill_meta = get_skill_meta(template_key)

    is_portfolio = template_key == "portfolio-review"
    if is_portfolio and not include_holding_context:
        raise ValueError("组合复盘必须携带持仓数据；请开启“携带个人持仓信息”。")

    target: Optional[Dict[str, Any]] = None
    if not is_portfolio:
        target = research_target.resolve_target(
            session, user, target_name, symbol, market, related_holding_id)
        if template_key == "thesis-tracker" and target.get("holding") is None:
            raise ValueError("投资论文追踪需要选择一个已有持仓")
    _validate_execution(target, template_key, execution_mode)

    if report_mode == "update" and parent_report is not None:
        ai_provider = ai_provider or parent_report.provider
        ai_model = ai_model or parent_report.model

    provider, user_key, user_api_key, user_base_url, model = _resolve_ai(
        session, user, ai_provider, ai_model,
        preferred_key_id=parent_report.user_ai_key_id if parent_report else None,
    )
    if execution_mode == "multi_agent" and not (
        user_api_key or tradingagents_adapter.system_api_key(provider, user_base_url)
    ):
        raise ValueError("TradingAgents 缺少可用的 Provider API Key，请先配置个人 AI Key")
    early_limits = research_usage.budget_limits(execution_mode)
    if early_limits.get("max_budget") is not None and not research_usage.has_price(provider, model):
        raise ValueError(
            "已设置 RESEARCH_MAX_BUDGET，但没有配置该 Provider/模型的价格，无法执行可靠的费用预算控制。"
            "请先补充 AI_PRICE_TABLE_JSON，或移除费用上限（调用/时间上限仍生效）。"
        )

    holding = target.get("holding") if target else None
    data_cutoff = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    eff_target = (target or {}).get("target_name") or "全账户投资组合"
    eff_symbol = (target or {}).get("symbol") or ""
    eff_market = (target or {}).get("market") or ""

    preferences = _preferences_text(session, user)
    combined_extra = "\n".join(
        part for part in [
            extra_instruction,
            f"【已保存的研究偏好】{preferences}" if preferences else "",
            (
                f"【研究更新】这是报告 #{parent_report.id} 的新版本。"
                "请基于本次实际获取的新资料核查变化，不要只改日期。"
                if report_mode == "update" and parent_report else ""
            ),
        ] if part
    )

    context_md = ""
    if include_holding_context:
        if is_portfolio:
            assets = session.exec(select(Holding).where(
                Holding.user_id == user.id, Holding.status == "open")).all()
            if not any(portfolio_context._valued(h) and market_value(h) > 0 for h in assets):
                raise ValueError("当前无有效可估值资产，请先添加持仓并更新价格后再分析。")
            context_md = portfolio_context.build_account_context(session, user, display_currency)
        elif holding is not None:
            context_md = _holding_context(holding, session)
    if is_portfolio and include_holding_context:
        history_md, prior_count = _portfolio_history_context(
            session, user, exclude_report_id=(parent_report.id if parent_report else None))
        note_count = len(session.exec(select(Note).where(
            Note.user_id == user.id,
            Note.note_type.in_(["thesis", "risk", "review", "observation"]),
        )).all())
        history_counts = {"notes": note_count, "prior_reports": prior_count}
    else:
        history_md, history_counts = _history_context(
            session, user, holding, eff_symbol, include_holding_context,
            exclude_report_id=(parent_report.id if parent_report else None))
    context_md = (context_md or "") + history_md

    if is_portfolio:
        snapshot_holding = None
    else:
        snapshot_holding = holding

    prompt_md = ""
    if execution_mode == "standard":
        prompt_md = research_prompt_builder.build_prompt(
            skill_md=skill_md,
            target_name=eff_target,
            symbol=eff_symbol,
            market=eff_market,
            holding_ctx=context_md if not is_portfolio else "",
            portfolio_ctx=context_md if is_portfolio else "",
            report_language=report_language,
            extra_instruction=combined_extra,
            is_portfolio=is_portfolio,
            data_cutoff=data_cutoff,
            is_update=report_mode == "update",
            previous_report_md=(parent_report.report_md or "") if parent_report else "",
            preferences=preferences,
            include_holding_context=include_holding_context,
            search_requested=use_web_search,
            search_supported=ai_client.provider_supports_web_search(provider),
        )
        if is_portfolio and len(prompt_md.encode("utf-8")) > 100_000:
            context_md = portfolio_context.build_account_context(
                session, user, display_currency, compact=True)
            prompt_md = research_prompt_builder.build_prompt(
                skill_md=skill_md, target_name=eff_target, symbol=eff_symbol,
                market=eff_market, portfolio_ctx=context_md,
                report_language=report_language, extra_instruction=combined_extra,
                is_portfolio=True, data_cutoff=data_cutoff,
                preferences=preferences, include_holding_context=include_holding_context,
                search_requested=use_web_search,
                search_supported=ai_client.provider_supports_web_search(provider),
            )
        if is_portfolio and len(prompt_md.encode("utf-8")) > 100_000:
            raise ValueError(
                "组合上下文超过本系统单次分析上限（100 KB），未发送 AI 请求，"
                "也未截断持仓。请精简补充要求或分账户研究。"
            )
        if is_portfolio:
            prompt_md += (
                "\n\nExternal search requested: " + str(bool(use_web_search)).lower()
                + ". Only describe external facts as verified when a search actually succeeds.\n"
            )

    missing = _data_missing(session, user, snapshot_holding, is_portfolio)
    ta_info = None
    trade_date = datetime.utcnow().strftime("%Y-%m-%d")
    ticker = None
    if execution_mode == "multi_agent" and target:
        if include_holding_context:
            ta_info = research_target.build_ta_portfolio(session, user, target)
        else:
            ta_info = {
                "target_ticker": research_target.to_yahoo_ticker(
                    target.get("symbol") or "", target.get("market") or "",
                    target.get("asset_type") or "stock"),
                "portfolio": {
                    "cash": None,
                    "currency": (target or {}).get("currency"),
                    "positions": [],
                },
                "excluded_holdings": [],
                "limitations": ["用户选择不携带个人持仓；组合输入为空。"],
            }
            combined_extra = (combined_extra + "\n" if combined_extra else "") + (
                "用户选择不携带个人持仓信息；不要把空组合输入推断为用户没有持仓。")
        ticker = ta_info["target_ticker"]
        probe = tradingagents_adapter.probe_engine()
        if not probe.get("available"):
            raise ValueError(
                "TradingAgents 引擎不可用：" + str(probe.get("error") or "未安装")
                + "。请安装固定版本的 TradingAgents，或改用标准研究。"
            )

    input_snapshot = _build_input_snapshot(
        target=target, is_portfolio=is_portfolio, template_key=template_key,
        execution_mode=execution_mode, include_holding_context=include_holding_context,
        display_currency=display_currency, data_cutoff=data_cutoff,
        missing=missing, history_counts=history_counts, preferences=preferences,
        use_web_search=use_web_search, provider=provider, report_mode=report_mode,
        parent_report_id=parent_report.id if parent_report else None,
        ta_info=ta_info,
    )
    snapshot_json = json.dumps(input_snapshot, ensure_ascii=False)

    key = _idempotency_key(
        user.id, template_key, target, provider, model, prompt_md or snapshot_json,
        execution_mode, parent_report.id if parent_report else None, idempotency_key,
    )
    existing = _find_existing(session, user.id, key)
    if existing:
        return existing

    template_name_zh = skill_meta["name"]
    if report_language == "en":
        t_name = _EN_TEMPLATE_TITLES.get(template_key, template_name_zh)
        title = f"{t_name}: {eff_symbol or eff_target}"
    else:
        title = f"{template_name_zh}：{eff_symbol or eff_target}"

    version = (parent_report.version + 1) if parent_report else 1
    report = ResearchReport(
        user_id=user.id,
        template_key=template_key,
        title=title,
        target_name=eff_target,
        symbol=eff_symbol or None,
        market=eff_market or None,
        related_holding_id=holding.id if holding else None,
        report_language=report_language,
        status="queued",
        input_context_md=context_md or None,
        skill_md=skill_md if execution_mode == "standard" else None,
        prompt_md=prompt_md or None,
        provider=provider,
        model=model,
        base_url=user_base_url,
        user_ai_key_id=user_key.id if user_key else None,
        parent_report_id=parent_report.id if parent_report else None,
        version=version,
        execution_mode=execution_mode,
        engine="TradingAgents" if execution_mode == "multi_agent" else provider,
        engine_version=(tradingagents_adapter.PINNED_VERSION if execution_mode == "multi_agent" else None),
        engine_commit=(tradingagents_adapter.PINNED_COMMIT if execution_mode == "multi_agent" else None),
        input_snapshot_json=snapshot_json,
        data_cutoff=data_cutoff,
        idempotency_key=key,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    research_events.append_event(
        session, report, "context", "completed",
        "研究标的与输入快照已准备；未写入任何持仓、现金或交易。",
        {"includes": input_snapshot["includes"], "missing": missing}, commit=True,
    )

    if execution_mode == "multi_agent":
        report.started_at = datetime.utcnow()
        limits = research_usage.budget_limits("multi_agent")
        task_dir = tradingagents_adapter.make_task_dir(user.id, report.id)
        payload = tradingagents_adapter.build_worker_payload(
            report_id=report.id,
            user_id=user.id,
            ticker=ticker,
            trade_date=trade_date,
            asset_type=target.get("asset_type") or "stock",
            provider=provider,
            model=model,
            base_url=user_base_url,
            report_language=report_language,
            portfolio=ta_info.get("portfolio"),
            limits=limits,
            task_dir=task_dir,
            extra_context=combined_extra,
        )
        payload["portfolio_note"] = {
            "excluded_holdings": ta_info.get("excluded_holdings", []),
            "limitations": ta_info.get("limitations", []),
        }
        report.budget_json = json.dumps({
            "limits": limits, "status": "running", "stop_reasons": [],
        }, ensure_ascii=False)
        session.add(report)
        session.commit()
        research_events.append_event(
            session, report, "engine", "started",
            f"启动 TradingAgents {tradingagents_adapter.PINNED_VERSION} Worker "
            f"（固定提交 {tradingagents_adapter.PINNED_COMMIT[:8]}）",
            {"ticker": ticker, "analysts": ["market", "news", "fundamentals"],
             "social": False, "debate_rounds": 1, "risk_rounds": 1},
            commit=True,
        )
        if user_key:
            user_key.last_used_at = datetime.utcnow()
            session.add(user_key)
            session.commit()
        engine = session.get_bind()
        worker_key = user_api_key or tradingagents_adapter.system_api_key(provider, user_base_url)
        if not worker_key:
            raise ValueError("TradingAgents 缺少可用的 Provider API Key，请先配置个人 AI Key")
        research_jobs.submit(
            engine, report.id, user.id, payload, provider,
            worker_key, user_base_url, limits["max_seconds"],
        )
        session.refresh(report)
        return report

    # Standard path: submit one provider call to a background runner so the
    # browser returns immediately and can poll real events/status.
    report.status = "queued"
    report.started_at = datetime.utcnow()
    report.updated_at = report.started_at
    if user_key:
        user_key.last_used_at = datetime.utcnow()
        session.add(user_key)
    session.add(report)
    session.commit()
    session.refresh(report)
    limits = research_usage.budget_limits("standard")
    engine = session.get_bind()
    report_id = report.id
    thread = research_jobs.submit_standard(
        engine, report_id, user.id, prompt_md, use_web_search, limits["max_seconds"])
    # Short grace period: fast/complete responses (and mock tests) surface the
    # final state immediately; long provider calls return as "running" and the
    # frontend keeps polling real events.
    try:
        grace = float(os.getenv("RESEARCH_SUBMIT_GRACE_SECONDS", "0.6"))
    except ValueError:
        grace = 0.6
    thread.join(max(0.0, grace))
    session.expire_all()
    report = session.get(ResearchReport, report_id)
    session.refresh(report)
    return report


def _update_comparison(parent: ResearchReport, current: ResearchReport, structured: Dict[str, Any]) -> Dict[str, Any]:
    try:
        old = json.loads(parent.report_json or "{}")
    except (TypeError, ValueError):
        old = {}
    old_facts = {item.get("text") for item in old.get("key_facts") or [] if item.get("text")}
    new_facts = [item for item in structured.get("key_facts") or [] if item.get("text") not in old_facts]
    changes = structured.get("changes")
    if changes:
        return changes
    old_summary = old.get("summary") or ""
    new_summary = structured.get("summary") or ""
    conclusion_changes = []
    if old_summary and new_summary and old_summary != new_summary:
        conclusion_changes.append(f"结论由「{old_summary[:160]}」变为「{new_summary[:160]}」")
    return {
        "added_facts": [item.get("text", "")[:300] for item in new_facts[:12]],
        "assumptions_supported": [],
        "assumptions_invalidated": [],
        "conclusion_changes": conclusion_changes,
        "unresolved_tracking": [
            item.get("text") for item in old.get("tracking") or [] if item.get("text")
        ][:12],
        "coverage_gaps": [
            "多 Agent 引擎未接收上一版报告原文，未自动声称假设被支持或推翻；"
            "本对照为结构化字段的确定性差异，请结合两版正文核验。"
        ],
        "comparison_method": "deterministic",
    }


def _new_source_count(parent: Optional[ResearchReport], sources: List[Dict[str, Any]]) -> int:
    if parent is None:
        return len(sources or [])
    old = set()
    try:
        for source in json.loads(parent.sources_json or "[]"):
            key = source.get("url") or source.get("title")
            if key:
                old.add(key)
    except (TypeError, ValueError):
        pass
    return sum(
        1 for source in sources or []
        if (source.get("url") or source.get("title")) not in old
    )


def _apply_update_notes(
    report: ResearchReport,
    structured: Dict[str, Any],
    source_status: Dict[str, Any],
    new_sources: int,
) -> None:
    if not report.parent_report_id:
        return
    changes = structured.get("changes") or {}
    if new_sources == 0 and source_status.get("status") in (
        "no_sources_returned", "unsupported_provider", "agent_data_tools",
    ):
        gaps = list(changes.get("coverage_gaps") or [])
        gaps.append(
            "本次未获得可核验的新来源，无法据此确认新增事实或推翻旧假设；"
            "新版本不应被理解为“资料已更新”。"
        )
        changes["coverage_gaps"] = gaps
        structured["changes"] = changes


def _finalize_standard(
    session: Session,
    report: ResearchReport,
    response: Any,
    provider: str,
    model: str,
    started: datetime,
) -> None:
    text = ai_client.extract_output_text(response) or ""
    now = datetime.utcnow()
    provider_sources = ai_client.extract_sources(response)
    source_supported = ai_client.provider_supports_web_search(provider)
    snapshot = {}
    try:
        snapshot = json.loads(report.input_snapshot_json or "{}")
    except (TypeError, ValueError):
        pass
    requested = bool((snapshot.get("web_search") or {}).get("requested", True))
    structured = research_structured.parse_structured_report(
        text,
        is_update=snapshot.get("mode") == "update" or report.parent_report_id is not None,
    )
    model_sources = structured.get("sources") or []
    merged_sources = []
    seen_source_keys = set()
    for source in list(provider_sources) + list(model_sources):
        key = source.get("url") or source.get("title")
        if not key or key in seen_source_keys:
            continue
        seen_source_keys.add(key)
        merged_sources.append(source)
    sources = research_structured.attach_retrieval_metadata(merged_sources)
    source_status = research_structured.source_status_for_standard(
        provider, requested, sources, source_supported)
    structured["source_status"] = source_status
    if report.parent_report_id and not structured.get("changes"):
        parent = session.get(ResearchReport, report.parent_report_id)
        if parent and parent.user_id == report.user_id:
            structured["changes"] = _update_comparison(parent, report, structured)
    if report.parent_report_id:
        parent = session.get(ResearchReport, report.parent_report_id)
        _apply_update_notes(
            report, structured, source_status,
            _new_source_count(parent, sources),
        )

    usage = ai_client.extract_usage(response, provider=provider, model=model)
    cost = research_usage.calculate_cost(usage, provider, model)
    limits = research_usage.budget_limits(report.execution_mode)
    budget = research_usage.evaluate_budget(usage, cost, limits, started, now)
    report.report_md = research_structured.strip_structured_blocks(text)
    report.sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
    report.source_status_json = json.dumps(source_status, ensure_ascii=False)
    report.report_json = json.dumps(structured, ensure_ascii=False)
    report.usage_json = json.dumps({
        "usage": usage, "cost": cost, "duration_seconds": round((now - started).total_seconds(), 1),
    }, ensure_ascii=False) if usage else json.dumps({
        "usage": None, "cost": cost, "duration_seconds": round((now - started).total_seconds(), 1),
    }, ensure_ascii=False)
    report.budget_json = json.dumps(budget, ensure_ascii=False)
    report.status = "completed"
    report.completed_at = now
    report.updated_at = now
    research_events.append_event(
        session, report, "completed", "completed",
        "报告已生成；结构化摘要" + ("解析成功" if not structured.get("degraded") else "解析失败，已降级为完整 Markdown"),
        {
            "source_status": source_status.get("status"),
            "degraded": structured.get("degraded"),
            "usage": usage,
            "cost": cost,
        },
        commit=False,
    )
    session.add(report)


def refresh_run(session: Session, report: ResearchReport) -> ResearchReport:
    if report.status not in ("running", "queued"):
        return report
    if report.execution_mode == "multi_agent":
        return report
    if not report.provider_response_id:
        return report
    try:
        user_api_key, provider = _resolve_report_ai_key(session, report)
        response = ai_client.retrieve_response(
            report.provider_response_id, api_key=user_api_key, provider=provider)
        if ai_client.is_response_complete(response):
            started = report.started_at or datetime.utcnow()
            _finalize_standard(
                session, report, response, provider, report.model or "", started)
        elif ai_client.is_response_failed(response):
            provider_status = getattr(response, "status", "failed")
            report.status = "cancelled" if provider_status == "cancelled" else "failed"
            report.error_message = f"Provider status: {provider_status}"
            report.completed_at = datetime.utcnow()
            research_events.append_event(
                session, report, "provider", report.status,
                report.error_message, commit=False)
    except AIServiceNotConfigured:
        raise
    except Exception as exc:
        report.error_message = f"刷新失败：{exc}"
    report.updated_at = datetime.utcnow()
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _resolve_report_ai_key(session: Session, report: ResearchReport) -> tuple:
    if report.execution_mode == "multi_agent":
        raise AIServiceNotConfigured("TradingAgents 任务由独立的 Worker 管理，不走标准刷新接口")
    if report.user_ai_key_id is None:
        return None, report.provider
    user_key = session.get(UserAIKey, report.user_ai_key_id)
    if user_key is None:
        raise AIServiceNotConfigured(
            f"创建此报告时使用的 AI Key 已被删除（user_ai_key_id={report.user_ai_key_id}），"
            f"无法刷新。请使用新的 AI Key 重新创建报告。"
        )
    if user_key.user_id != report.user_id:
        raise AIServiceNotConfigured("报告的 AI Key 引用异常，不属于同一用户。")
    try:
        api_key = decrypt_secret(user_key.encrypted_api_key)
    except RuntimeError:
        raise AIServiceNotConfigured(
            "无法解密创建此报告时使用的 AI Key（加密密钥可能已更换）。"
            "请重新配置 API Key 并重新创建报告。"
        )
    return api_key, user_key.provider


def create_update_run(
    session: Session,
    user: User,
    parent: ResearchReport,
    extra_instruction: Optional[str],
    ai_provider: Optional[str],
    ai_model: Optional[str],
    use_web_search: bool,
    idempotency_key: Optional[str],
) -> ResearchReport:
    if parent.user_id != user.id:
        raise PermissionError("报告不存在")
    if parent.status != "completed" or not parent.report_md:
        raise ValueError("只有已完成的报告才能更新")
    display_currency = Currency.CNY
    try:
        snapshot = json.loads(parent.input_snapshot_json or "{}")
        display_currency = Currency(snapshot.get("display_currency") or "CNY")
    except (TypeError, ValueError):
        display_currency = Currency.CNY
    return create_run(
        session=session,
        user=user,
        template_key=parent.template_key,
        target_name=parent.target_name,
        symbol=parent.symbol,
        market=parent.market,
        related_holding_id=parent.related_holding_id,
        report_language=parent.report_language,
        ai_provider=ai_provider,
        ai_model=ai_model,
        extra_instruction=extra_instruction,
        use_web_search=use_web_search,
        display_currency=display_currency,
        execution_mode=parent.execution_mode,
        include_holding_context=True,
        idempotency_key=idempotency_key,
        parent_report=parent,
        report_mode="update",
    )


def finalize_multi_agent(session: Session, report: ResearchReport, result: Dict[str, Any]) -> None:
    now = datetime.utcnow()
    result_status = result.get("status") or "failed"
    cancelled_by_user = report.status == "cancelled"
    usage = result.get("usage")
    snapshot = {}
    try:
        snapshot = json.loads(report.input_snapshot_json or "{}")
    except (TypeError, ValueError):
        pass
    cost = research_usage.calculate_cost(
        usage, report.provider, (result.get("run_settings") or {}).get("quick_think_llm") or report.model)
    limits = research_usage.budget_limits("multi_agent")
    budget = research_usage.evaluate_budget(
        usage, cost, limits, report.started_at, now)
    if result_status == "budget_stopped":
        budget["status"] = "exceeded"
        budget["stop_reasons"] = list(dict.fromkeys(
            (budget.get("stop_reasons") or []) + [result.get("error") or "预算停止"]
        ))
    report.budget_json = json.dumps(budget, ensure_ascii=False)
    if usage:
        report.usage_json = json.dumps({
            "usage": usage,
            "cost": cost,
            "duration_seconds": result.get("elapsed_seconds"),
            "tool_usage": result.get("tool_usage"),
        }, ensure_ascii=False)
    report.engine_version = result.get("engine_version") or report.engine_version
    report.engine_commit = result.get("engine_commit") or report.engine_commit

    if result_status == "completed":
        artifacts = tradingagents_adapter.build_result_artifacts(
            result, report.symbol or report.target_name, report.report_language,
            (snapshot.get("display_currency") or "CNY"),
        )
        report.report_md = artifacts["report_md"]
        report.report_json = json.dumps(artifacts["report_json"], ensure_ascii=False)
        multi_agent = artifacts["multi_agent_json"]
        multi_agent["portfolio_note"] = (snapshot.get("multi_agent") or {}).get(
            "limitations") or (snapshot.get("multi_agent") or {}).get("excluded_holdings")
        report.multi_agent_json = json.dumps(multi_agent, ensure_ascii=False)
        report.sources_json = json.dumps(artifacts["sources"], ensure_ascii=False) if artifacts["sources"] else None
        report.source_status_json = json.dumps(artifacts["source_status"], ensure_ascii=False)
        if report.parent_report_id:
            parent = session.get(ResearchReport, report.parent_report_id)
            if parent and parent.user_id == report.user_id:
                structured = artifacts["report_json"]
                structured["changes"] = _update_comparison(parent, report, structured)
                _apply_update_notes(
                    report, structured, artifacts["source_status"],
                    _new_source_count(parent, artifacts["sources"]))
                report.report_json = json.dumps(structured, ensure_ascii=False)
        report.status = "completed"
        report.completed_at = now
        report.error_message = None
        if report.started_at is None:
            report.started_at = now
        research_events.append_event(
            session, report, "completed", "completed",
            "TradingAgents 多 Agent 研究完成；结果仅用于研究，不产生交易。",
            {"rating": artifacts.get("rating"), "budget": budget, "usage": usage},
            commit=False,
        )
    elif result_status == "cancelled" or cancelled_by_user:
        report.status = "cancelled"
        report.completed_at = now
        report.error_message = (
            result.get("error")
            or ("用户已取消；Worker 后续步骤已停止" if cancelled_by_user else "TradingAgents Worker 已取消")
        )
        research_events.append_event(
            session, report, "cancelled", "cancelled", report.error_message,
            {"provider_cancelled": bool(result.get("provider_cancelled"))}, commit=False)
    else:
        report.status = "failed"
        report.completed_at = now
        report.error_message = (result.get("error") or "TradingAgents 执行失败")[:1500]
        research_events.append_event(
            session, report, "failed", "failed", report.error_message,
            {"budget": budget, "stderr_tail": (result.get("stderr_tail") or "")[-800:]},
            commit=False)
    report.updated_at = now
    session.add(report)
    session.commit()
    session.refresh(report)
