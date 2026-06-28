"""投研服务层：加载 AI Berkshire skill → 构建 prompt → 调用 AI → 同步状态。"""
import json
import os
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

import ai_client
from ai_client import AIServiceNotConfigured
from ai_berkshire_loader import load_skill, get_skill_meta
from config import ALLOW_SYSTEM_AI_FALLBACK
from crypto_utils import decrypt_secret
from models import Holding, HoldingStatus, Platform, ResearchReport, User, UserAIKey, Currency, cost_basis, market_value, profit
import research_prompt_builder

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
        "",
    ])


# 汇率折算表：HKD 按联系汇率 ~7.8 近似折算为 USD 后再折算 CNY
HKD_PEG = 7.8


def _get_to_cny_rates(session: Session) -> dict:
    """返回 {Currency: rate_to_cny} 字典，CNY 始终为 1.0。"""
    from models import FxRate
    fx = session.exec(select(FxRate).where(FxRate.pair == "USDCNY")).first()
    usdcny = fx.rate if fx else 7.2
    fx_updated_at = fx.updated_at.isoformat() if fx and fx.updated_at else "unknown"
    return {
        Currency.CNY: 1.0,
        Currency.USD: usdcny,
        Currency.HKD: usdcny / HKD_PEG,
    }, usdcny, fx_updated_at


def _portfolio_context(holdings: List[Holding], session: Session) -> str:
    """生成 Portfolio Review 持仓上下文（CNY 统一折算口径）。

    所有持仓按 CNY 折算后计算总市值和组合权重，并在 prompt 中标注
    原币种金额、折算汇率和汇率更新时间。
    """
    if not holdings:
        return "\n**（当前无持仓数据）**\n"

    to_cny, usdcny, fx_updated_at = _get_to_cny_rates(session)

    # 计算每个持仓的 CNY 折算市值和未实现盈亏
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
            "h": h,
            "mv_native": mv_native,
            "mv_cny": mv_cny,
            "pnl": pnl,
            "pnl_cny": pnl_cny,
            "rate": rate,
        })

    # 按 CNY 折算市值加权
    rows = []
    for d in rows_data:
        h = d["h"]
        mv_native = d["mv_native"]
        pnl = d["pnl"]
        w = (d["mv_cny"] / total_cny * 100) if total_cny else 0
        # 标注币种：CNY 只显示原值；非 CNY 额外显示折算值
        if h.currency == Currency.CNY:
            mv_str = f"{mv_native:.0f} CNY"
        else:
            mv_str = f"{mv_native:.0f} {h.currency.value}（≈{d['mv_cny']:.0f} CNY）"
        pnl_str = f"{pnl:+.2f} {h.currency.value}" if pnl is not None else "—"
        rows.append(
            f"| {h.name} | {h.symbol or '—'} | {h.market.value} | {h.currency.value} "
            f"| {h.quantity if h.quantity is not None else '—'} "
            f"| {h.cost_price if h.cost_price is not None else '—'} "
            f"| {h.current_price if h.current_price is not None else '—'} "
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
        "\n> ⚠️ **数据说明**：\n"
        "> - 以上市值为持仓原币种金额及按 CNY 折算的近似值。\n"
        "> - 组合占比（权重）基于 CNY 折算市值计算，已统一币种口径。\n"
        "> - 行情数据非实时数据，可能存在延迟。\n"
        "> - 汇率并非实时更新，具体更新时间见上方标注。\n"
        "> - 请勿将 AI 输出视为确定性投资建议。\n"
    )

    return (
        header
        + "\n".join(rows)
        + f"\n\n**组合总市值（CNY 折算）：约 {total_cny:,.0f} CNY**"
        + fx_info
        + disclaimer
    )


def _get_user_ai_key(session: Session, user_id: int, provider: str) -> Optional[UserAIKey]:
    """查找用户指定 provider 的 key；未指定 provider 时返回 is_default key。"""
    return session.exec(
        select(UserAIKey).where(
            UserAIKey.user_id == user_id,
            UserAIKey.provider == provider,
        )
    ).first()


def _get_user_default_ai_key(session: Session, user_id: int) -> Optional[UserAIKey]:
    """返回用户标记为 is_default 的 key。"""
    return session.exec(
        select(UserAIKey).where(
            UserAIKey.user_id == user_id,
            UserAIKey.is_default == True,  # noqa: E712
        )
    ).first()


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
) -> ResearchReport:
    # 1. Load AI Berkshire skill markdown (raises ValueError / FileNotFoundError)
    skill_md = load_skill(template_key)
    skill_meta = get_skill_meta(template_key)

    # 2. Resolve provider and user API key
    provider = ai_client.normalize_provider(ai_provider)

    # Look up user's key for this provider; fall back to their default key
    user_key: Optional[UserAIKey] = _get_user_ai_key(session, user.id, provider)
    if user_key is None and not ai_provider:
        user_key = _get_user_default_ai_key(session, user.id)
        if user_key:
            provider = user_key.provider  # align provider to the default key

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

    # 3. Resolve model: request > user default_model > ai_client default
    effective_model = ai_model or (user_key.default_model if user_key else None)
    model = ai_client.choose_model(provider, effective_model)

    # 4. Validate holding ownership
    holding: Optional[Holding] = None
    if related_holding_id is not None:
        holding = session.get(Holding, related_holding_id)
        if not holding or holding.user_id != user.id:
            raise PermissionError("持仓不存在或不属于当前用户")

    # 5. Build context
    is_portfolio = template_key == "portfolio-review"
    input_context_md = ""
    if is_portfolio:
        holdings = list(session.exec(
            select(Holding).where(
                Holding.user_id == user.id,
                Holding.status != HoldingStatus.closed,
            )
        ).all())
        input_context_md = _portfolio_context(holdings, session)
    elif holding:
        input_context_md = _holding_context(holding, session)

    # 6. Resolve effective values
    eff_target = target_name or (holding.name if holding else None) or "目标公司"
    eff_symbol = symbol or (holding.symbol if holding else "") or ""
    eff_market = market or (holding.market.value if holding else "") or ""

    # 7. Build prompt using AI Berkshire skill + platform context
    prompt_md = research_prompt_builder.build_prompt(
        skill_md=skill_md,
        target_name=eff_target,
        symbol=eff_symbol,
        market=eff_market,
        holding_ctx=input_context_md if not is_portfolio else "",
        portfolio_ctx=input_context_md if is_portfolio else "",
        report_language=report_language,
        extra_instruction=extra_instruction or "",
    )

    # 8. Generate title
    template_name_zh = skill_meta["name"]
    if report_language == "en":
        t_name = _EN_TEMPLATE_TITLES.get(template_key, template_name_zh)
        title = f"{t_name}: {eff_symbol or eff_target}"
    else:
        title = f"{template_name_zh}：{eff_symbol or eff_target}"

    # 9. Persist (status=queued, snapshot skill_md for reproducibility)
    report = ResearchReport(
        user_id=user.id,
        template_key=template_key,
        title=title,
        target_name=eff_target,
        symbol=eff_symbol or None,
        market=eff_market or None,
        related_holding_id=related_holding_id,
        report_language=report_language,
        status="queued",
        input_context_md=input_context_md or None,
        skill_md=skill_md,
        prompt_md=prompt_md,
        provider=provider,
        model=model,
        base_url=user_base_url,
        user_ai_key_id=user_key.id if user_key else None,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    # 10. Submit to AI provider
    try:
        response_id = ai_client.start_research(
            prompt_md,
            use_web_search=use_web_search,
            provider=provider,
            model=model,
            api_key=user_api_key,
            base_url=user_base_url,
        )
        report.provider_response_id = response_id
        report.started_at = datetime.utcnow()
        response = ai_client.retrieve_response(response_id)
        if ai_client.is_response_complete(response):
            text = ai_client.extract_output_text(response)
            sources = ai_client.extract_sources(response)
            report.report_md = text
            report.sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
            report.status = "completed"
            report.completed_at = datetime.utcnow()
        else:
            report.status = "running"

        # Update last_used_at for the user key
        if user_key:
            user_key.last_used_at = datetime.utcnow()
            session.add(user_key)

    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)

    report.updated_at = datetime.utcnow()
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _resolve_report_ai_key(session: Session, report: ResearchReport) -> tuple:
    """解析报告的 BYOK 配置，返回 (api_key, provider)。

    报告有 user_ai_key_id → 解密用户 Key；否则返回 (None, report.provider)。
    如果 Key 已被删除，抛出明确错误。
    """
    if report.user_ai_key_id is None:
        return None, report.provider

    user_key = session.get(UserAIKey, report.user_ai_key_id)
    if user_key is None:
        raise AIServiceNotConfigured(
            f"创建此报告时使用的 AI Key 已被删除（user_ai_key_id={report.user_ai_key_id}），"
            f"无法刷新。请使用新的 AI Key 重新创建报告。"
        )
    if user_key.user_id != report.user_id:
        raise AIServiceNotConfigured(
            "报告的 AI Key 引用异常，不属于同一用户。"
        )
    try:
        api_key = decrypt_secret(user_key.encrypted_api_key)
    except RuntimeError:
        raise AIServiceNotConfigured(
            "无法解密创建此报告时使用的 AI Key（加密密钥可能已更换）。"
            "请重新配置 API Key 并重新创建报告。"
        )
    return api_key, user_key.provider


def refresh_run(session: Session, report: ResearchReport) -> ResearchReport:
    """Poll the AI provider and update the report. No-op if not in a running state.

    使用创建报告时的 BYOK 配置（如果存在）进行 refresh。
    """
    if report.status not in ("running", "queued"):
        return report
    if not report.provider_response_id:
        return report

    try:
        user_api_key, provider = _resolve_report_ai_key(session, report)
        response = ai_client.retrieve_response(
            report.provider_response_id,
            api_key=user_api_key,
            provider=provider,
        )
        if ai_client.is_response_complete(response):
            text = ai_client.extract_output_text(response)
            sources = ai_client.extract_sources(response)
            report.report_md = text
            report.sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
            report.status = "completed"
            report.completed_at = datetime.utcnow()
        elif ai_client.is_response_failed(response):
            provider_status = getattr(response, "status", "failed")
            report.status = "cancelled" if provider_status == "cancelled" else "failed"
            report.error_message = f"Provider status: {provider_status}"
            report.completed_at = datetime.utcnow()
    except AIServiceNotConfigured:
        raise  # BYOK 配置错误必须传播，不能静默吞掉
    except Exception as exc:
        report.error_message = f"刷新失败：{exc}"

    report.updated_at = datetime.utcnow()
    session.add(report)
    session.commit()
    session.refresh(report)
    return report
