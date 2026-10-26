"""报告结构化摘要、证据标签与跟踪事项提取。

结构化摘要在同一次模型生成中返回（`research-json` 代码块），不额外调用
模型。解析失败时保留完整 Markdown，并明确标记降级；绝不补造缺失字段。
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_JSON_BLOCK_RE = re.compile(
    r"```(?:research-json|json)\s*\n(.*?)\n```",
    re.IGNORECASE | re.DOTALL,
)
_HTML_JSON_RE = re.compile(
    r"<!--\s*RESEARCH_JSON\s*(.*?)\s*RESEARCH_JSON\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_ITEM_KINDS = {"fact", "analysis", "assumption"}


def structured_output_requirements(lang: str, is_update: bool = False) -> str:
    update_fields = (
        '"changes": {'
        '"added_facts": ["本次新增且可核验的事实；没有就写空数组"], '
        '"assumptions_supported": ["得到支持的原有假设"], '
        '"assumptions_invalidated": ["被推翻的原有假设及依据"], '
        '"conclusion_changes": ["结论变化及依据"], '
        '"unresolved_tracking": ["仍未解决的跟踪事项"], '
        '"coverage_gaps": ["本次资料覆盖不足的部分"]'
        "}, "
        if is_update else ""
    )
    if lang == "en":
        return (
            "## Structured Summary (same response, no second call)\n\n"
            "After the complete Markdown report, append exactly one fenced block:\n\n"
            "```research-json\n"
            "{"
            '"summary": "one-sentence core conclusion", '
            '"key_facts": [{"text": "...", "kind": "fact", "source": "publisher/document", '
            '"period": "FY2025Q3", "as_of": "YYYY-MM-DD"}], '
            '"risks": [{"text": "...", "kind": "analysis", "source": "..."}], '
            '"impact": "impact on the user\'s holding or research objective", '
            '"next_watch": ["observable next step"], '
            '"tracking": [{"text": "...", "metric": "...", "review_date": null, '
            '"trigger_condition": "..."}], '
            '"questions": ["unverified question"], '
            '"sources": [{"title": "...", "url": "https://...", "publisher": "...", '
            '"published_at": null, "period": null}]'
            f"{', ' + update_fields if update_fields else ''}"
            "}\n```\n\n"
            "Use `kind: fact` only when the item has a source; use `kind: analysis` for "
            "inference and `kind: assumption` for unverified assumptions. Never invent a "
            "source, date, URL, period or tracking date. When a value is unknown, use null or "
            "an empty array. The fenced block is data for the UI; the Markdown body must still "
            "stand on its own."
        )
    return (
        "## 结构化摘要（同一次回答内完成，不额外调用模型）\n\n"
        "在完整 Markdown 报告末尾，追加且只追加一个如下代码块：\n\n"
        "```research-json\n"
        "{"
        '"summary": "一句话核心结论", '
        '"key_facts": [{"text": "...", "kind": "fact", "source": "机构/公告名称", '
        '"period": "2025Q3", "as_of": "YYYY-MM-DD"}], '
        '"risks": [{"text": "...", "kind": "analysis", "source": "..."}], '
        '"impact": "对用户持仓或本次研究目标的影响", '
        '"next_watch": ["下一步可观察事项"], '
        '"tracking": [{"text": "...", "metric": "...", "review_date": null, '
        '"trigger_condition": "..."}], '
        '"questions": ["待验证问题"], '
        '"sources": [{"title": "...", "url": "https://...", "publisher": "...", '
        '"published_at": null, "period": null}]'
        f"{', ' + update_fields if update_fields else ''}"
        "}\n```\n\n"
        "只有真正有来源的条目才能使用 `kind: fact`；推理判断使用 `kind: analysis`，"
        "待验证假设使用 `kind: assumption`。不得编造来源、日期、URL、所属期间或跟踪日期；"
        "未知时使用 null 或空数组。代码块是给界面读取的数据，正文仍须独立完整可读。"
    )


def update_requirements(lang: str) -> str:
    if lang == "en":
        return (
            "## Research Update Requirements\n\n"
            "This is a new version based on the previously saved report. Verify what changed "
            "using newly retrieved material. Explicitly separate:\n"
            "1. new verifiable facts;\n"
            "2. assumptions supported by new evidence;\n"
            "3. assumptions invalidated and why;\n"
            "4. conclusions that changed and the evidence;\n"
            "5. tracking items still unresolved;\n"
            "6. areas where current material is insufficient.\n\n"
            "Do not merely change the old report's date. If no new material was retrieved, "
            "state that plainly and keep the old conclusions only as previously reported."
        )
    return (
        "## 研究更新要求\n\n"
        "这是一份基于旧报告的新版本。请用本次实际获取的新资料核查变化，并明确区分：\n"
        "1. 新增的可核验事实；\n"
        "2. 得到新证据支持的原有假设；\n"
        "3. 被推翻的原有假设及依据；\n"
        "4. 发生变化的结论及改变依据；\n"
        "5. 仍未解决的跟踪事项；\n"
        "6. 当前资料覆盖不足的部分。\n\n"
        "不得只把旧报告改日期后重新输出。如果本次没有获取到新资料，必须直接说明，"
        "旧结论只能标注为“此前报告结论”，不能包装成最新事实。"
    )


def followup_requirements(lang: str, use_search: bool) -> str:
    if lang == "en":
        search_line = (
            "If you requested new evidence, list only sources actually returned in this turn, "
            "with their retrieval time. If retrieval failed, say so."
            if use_search else
            "This answer uses the saved report, its input snapshot and prior conversation only; "
            "do not imply that new external data was fetched."
        )
        return (
            "## Follow-up Answer Requirements\n\n"
            "Answer the user's specific question. Do not rewrite the whole report unless asked. "
            "Use the saved report and its input snapshot as context. Separate facts from "
            "inferences and assumptions. " + search_line + "\n"
            "End with a short `Data as of` line and, only when new material was actually "
            "retrieved, a `New sources` list with retrieval time."
        )
    search_line = (
        "如果本轮实际发起了补充检索，只列出真正返回的来源，并注明获取时间；检索失败必须说明。"
        if use_search else
        "本轮只使用已保存报告、输入快照和既有对话，不得暗示获取了新的外部数据。"
    )
    return (
        "## 追问回答要求\n\n"
        "只回答用户提出的具体问题，不默认重写整篇报告。以已保存报告和输入快照为上下文，"
        "区分有来源事实、分析判断和待验证假设。" + search_line + "\n"
        "结尾用一行注明“数据时点”；只有确实获取到新资料时，才列出“新增来源”及获取时间。"
    )


def _normalise_item(item: Any, default_kind: str = "analysis") -> Optional[Dict[str, Any]]:
    if isinstance(item, str):
        text = item.strip()
        return {"text": text, "kind": default_kind, "source": None} if text else None
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or item.get("summary") or item.get("statement") or "").strip()
    if not text:
        return None
    kind = str(item.get("kind") or default_kind).lower()
    if kind not in _ITEM_KINDS:
        kind = default_kind
    return {
        "text": text,
        "kind": kind,
        "source": item.get("source") or item.get("source_title") or None,
        "period": item.get("period") or None,
        "as_of": item.get("as_of") or item.get("published_at") or None,
        "url": item.get("url") or None,
        "source_missing": kind == "fact" and not (item.get("source") or item.get("url")),
    }


def _normalise_items(value: Any, default_kind: str = "analysis") -> List[Dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value:
        normalised = _normalise_item(item, default_kind)
        if normalised:
            out.append(normalised)
    return out


def _normalise_summary(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return "；".join(parts) or None
    return None


def _normalise_changes(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    keys = (
        "added_facts", "assumptions_supported", "assumptions_invalidated",
        "conclusion_changes", "unresolved_tracking", "coverage_gaps",
    )
    out: Dict[str, Any] = {}
    for key in keys:
        raw = value.get(key)
        if isinstance(raw, str):
            out[key] = [raw] if raw.strip() else []
        elif isinstance(raw, list):
            out[key] = [str(v).strip() for v in raw if str(v).strip()]
        else:
            out[key] = []
    if not any(out.values()):
        return None
    return out


def strip_structured_blocks(markdown: Optional[str]) -> str:
    """Remove the UI-only structured block from the readable Markdown body."""
    text = markdown or ""

    def repl(match: "re.Match[str]") -> str:
        raw = match.group(1).strip()
        if not raw.startswith("{"):
            return match.group(0)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return match.group(0)
        return "" if isinstance(data, dict) and any(
            key in data for key in ("summary", "key_facts", "tracking", "impact")
        ) else match.group(0)

    text = _JSON_BLOCK_RE.sub(repl, text)
    text = _HTML_JSON_RE.sub(repl, text)
    return text.rstrip() + "\n" if text.strip() else ""


def _normalise_source(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    url = item.get("url")
    title = item.get("title") or item.get("text") or url
    if not url and not title:
        return None
    return {
        "title": title,
        "url": url,
        "publisher": item.get("publisher"),
        "published_at": item.get("published_at"),
        "period": item.get("period"),
        "verified": False,
    }


def _extract_json_payload(markdown: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    candidates: List[str] = []
    candidates.extend(m.group(1).strip() for m in _JSON_BLOCK_RE.finditer(markdown or ""))
    candidates.extend(m.group(1).strip() for m in _HTML_JSON_RE.finditer(markdown or ""))
    # Prefer the last block: models sometimes show a schema example earlier.
    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict):
            return data, None
    if candidates:
        return None, "找到结构化数据块，但不是合法 JSON"
    return None, "模型未返回结构化摘要数据块"


def parse_structured_report(
    markdown: Optional[str],
    *,
    is_update: bool = False,
    source_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """解析同一次生成末尾的结构化块；失败时只返回降级标记。"""
    data, parse_error = _extract_json_payload(markdown or "")
    model_sources = []
    if data:
        normalised_sources = [_normalise_source(item) for item in (data.get("sources") or [])]
        model_sources = [item for item in normalised_sources if item]
    return {
        "degraded": data is None,
        "degradation_reason": parse_error,
        "summary": _normalise_summary(data.get("summary")) if data else None,
        "key_facts": _normalise_items(data.get("key_facts"), "analysis") if data else [],
        "risks": _normalise_items(data.get("risks"), "analysis") if data else [],
        "impact": _normalise_summary(data.get("impact")) if data else None,
        "next_watch": _normalise_items(data.get("next_watch"), "analysis") if data else [],
        "tracking": _normalise_items(data.get("tracking"), "assumption") if data else [],
        "questions": _normalise_items(data.get("questions"), "assumption") if data else [],
        "changes": _normalise_changes(data.get("changes")) if data and is_update else None,
        "sources": model_sources,
        "source_status": source_status or {},
        "parsed_at": datetime.utcnow().isoformat() + "Z",
    }


_HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _sections(markdown: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in (markdown or "").splitlines():
        match = _HEADING_RE.match(line.strip())
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def _bullets(lines: List[str]) -> List[str]:
    out = []
    for line in lines:
        match = _LIST_RE.match(line)
        if match:
            text = match.group(1).strip()
            if text:
                out.append(text)
    return out


def extract_tracking_candidates(markdown: Optional[str]) -> List[Dict[str, Any]]:
    """从正文中提取预览候选；只使用原文里真实出现的日期。"""
    sections = _sections(markdown or "")
    candidates: List[Dict[str, Any]] = []
    seen = set()

    def add(text: str, kind: str) -> None:
        key = re.sub(r"\s+", " ", text).strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        date_match = _DATE_RE.search(text)
        trigger = None
        lowered = text.lower()
        if any(word in lowered for word in ("财报", "earnings", "发布", "公告", "分红", "股东大会")):
            trigger = text
        candidates.append({
            "text": text,
            "metric": text if kind == "metric" else None,
            "review_date": date_match.group(1) if date_match else None,
            "trigger_condition": trigger,
            "status": "active",
            "kind": kind,
        })

    for heading, lines in sections.items():
        lowered = heading.lower()
        if "跟踪指标" in heading or "tracking metric" in lowered:
            for text in _bullets(lines):
                add(text, "metric")
        elif "行动项" in heading or "action item" in lowered:
            for text in _bullets(lines):
                add(text, "action")
        elif "待验证" in heading or "question" in lowered:
            for text in _bullets(lines):
                add(text, "question")
    return candidates


def extract_structured_tracking(report_json: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not report_json or report_json.get("degraded"):
        return []
    out = []
    for item in report_json.get("tracking") or []:
        text = item.get("text")
        if not text:
            continue
        out.append({
            "text": text,
            "metric": item.get("metric"),
            "review_date": item.get("review_date"),
            "trigger_condition": item.get("trigger_condition"),
            "status": "active",
            "kind": "tracking",
        })
    return out


def tracking_candidates(report_md: Optional[str], report_json: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined = extract_structured_tracking(report_json)
    seen = {re.sub(r"\s+", " ", item["text"]).strip().lower() for item in combined}
    for item in extract_tracking_candidates(report_md):
        key = re.sub(r"\s+", " ", item["text"]).strip().lower()
        if key not in seen:
            combined.append(item)
            seen.add(key)
    return combined


def source_status_for_standard(
    provider: Optional[str],
    use_web_search: bool,
    sources: List[Dict[str, Any]],
    search_supported: bool,
) -> Dict[str, Any]:
    retrieved_at = datetime.utcnow().isoformat() + "Z"
    if not use_web_search:
        status = "not_requested"
        message = "本次未请求联网检索，仅使用平台上下文与模型知识。"
    elif not search_supported:
        status = "unsupported_provider"
        message = (
            "当前 Provider 未接入本系统联网检索；报告中的来源是模型引用，"
            "未由系统抓取或核验。"
            if sources else
            "当前 Provider 未接入联网检索；本次结果中没有新增可核验来源。"
        )
    elif sources:
        status = "sources_returned"
        message = "Provider 返回了来源引用；引用可访问性尚未逐一核验。"
    else:
        status = "no_sources_returned"
        message = "已请求联网检索，但 Provider 未返回来源引用；不能视为检索成功。"
    return {
        "requested": bool(use_web_search),
        "provider_supports_search": bool(search_supported),
        "status": status,
        "message": message,
        "source_count": len(sources or []),
        "retrieved_at": retrieved_at,
        "verified": False,
    }


def attach_retrieval_metadata(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = datetime.utcnow().isoformat() + "Z"
    out = []
    for source in sources or []:
        item = dict(source)
        item.setdefault("retrieved_at", now)
        item.setdefault("verified", False)
        out.append(item)
    return out


def build_multi_agent_report(state: Dict[str, Any], ticker: str, lang: str = "zh") -> str:
    """把 TradingAgents 各阶段报告拼成可读 Markdown（不改变角色原文）。"""
    zh = lang != "en"
    title = f"# 投资委员会多 Agent 研究：{ticker}" if zh else f"# Investment Committee Multi-Agent Research: {ticker}"
    lines = [
        title, "",
        ("> 本报告由 TradingAgents 多 Agent 流程生成，用于研究与复盘；"
         "策略节点仅输出研究观点和情景，不包含下单、撤单或转账指令。") if zh else
        ("> Generated by the TradingAgents multi-agent workflow for research and review. "
         "The strategy node contains research views and scenarios only, not order instructions."),
        "",
    ]

    def section(heading: str, body: Optional[str]) -> None:
        if body and str(body).strip():
            lines.extend([f"## {heading}", "", str(body).strip(), ""])

    if zh:
        section("最终研究结论", state.get("final_trade_decision"))
        section("基本面分析", state.get("fundamentals_report"))
        section("市场与行情分析", state.get("market_report"))
        section("机构新闻分析", state.get("news_report"))
        debate = state.get("investment_debate_state") or {}
        section("多方研究观点", debate.get("bull_history"))
        section("空方研究观点", debate.get("bear_history"))
        section("研究经理观点", state.get("investment_plan"))
        section("策略观点与情景（非交易指令）", state.get("trader_investment_plan"))
        risk = state.get("risk_debate_state") or {}
        section("风险讨论：激进视角", risk.get("aggressive_history"))
        section("风险讨论：保守视角", risk.get("conservative_history"))
        section("风险讨论：中性视角", risk.get("neutral_history"))
        section("来源与核验说明", state.get("source_note") or (
            "数据来自 TradingAgents 配置的行情、监管披露与新闻数据源。"
            "本轮未逐条核验引用可访问性；请以公司公告、财报和监管披露为准。"
        ))
    else:
        section("Final Research Conclusion", state.get("final_trade_decision"))
        section("Fundamentals", state.get("fundamentals_report"))
        section("Market Analysis", state.get("market_report"))
        section("Institutional News", state.get("news_report"))
        debate = state.get("investment_debate_state") or {}
        section("Bull Case", debate.get("bull_history"))
        section("Bear Case", debate.get("bear_history"))
        section("Research Manager", state.get("investment_plan"))
        section("Strategy Views and Scenarios (Not Orders)", state.get("trader_investment_plan"))
        risk = state.get("risk_debate_state") or {}
        section("Risk Discussion: Aggressive", risk.get("aggressive_history"))
        section("Risk Discussion: Conservative", risk.get("conservative_history"))
        section("Risk Discussion: Neutral", risk.get("neutral_history"))
        section("Sources and Verification", state.get("source_note") or (
            "Data comes from the market, filing and news vendors configured in TradingAgents. "
            "Citation accessibility was not individually verified in this run. Prefer company "
            "filings, exchange disclosures and regulator publications."
        ))
    return "\n".join(lines).strip() + "\n"


def build_multi_agent_structured(
    state: Dict[str, Any],
    role_views: Dict[str, Any],
    lang: str = "zh",
) -> Dict[str, Any]:
    """确定性提取结构化摘要；不额外调用模型，也不把角色观点伪装成已核验事实。"""
    decision = (state.get("final_trade_decision") or "").strip()
    summary = decision.split("\n\n")[0].strip() if decision else None
    risk = state.get("risk_debate_state") or {}
    debate = state.get("investment_debate_state") or {}
    risks = []
    for label, key in (("激进", "aggressive_history"), ("保守", "conservative_history"), ("中性", "neutral_history")):
        text = (risk.get(key) or "").strip()
        if text:
            risks.append({
                "text": text.split("\n\n")[0][:500],
                "kind": "analysis",
                "source": f"TradingAgents 风险讨论·{label}",
            })
    facts = []
    for label, key in (("基本面", "fundamentals_report"), ("行情", "market_report"), ("新闻", "news_report")):
        text = (state.get(key) or "").strip()
        if text:
            facts.append({
                "text": text.split("\n\n")[0][:500],
                "kind": "analysis",
                "source": f"TradingAgents {label}分析师（数据源未逐条核验）",
            })
    return {
        "degraded": not bool(decision),
        "degradation_reason": None if decision else "TradingAgents 未返回最终研究结论",
        "summary": summary,
        "key_facts": facts,
        "risks": risks,
        "impact": summary,
        "next_watch": [],
        "tracking": [],
        "questions": [],
        "changes": None,
        "sources": [],
        "source_status": {
            "requested": True,
            "provider_supports_search": True,
            "status": "agent_data_tools",
            "message": "TradingAgents 通过配置的数据工具获取行情、财报与新闻；未逐条核验引用可访问性。",
            "source_count": 0,
            "verified": False,
        },
        "role_views": role_views,
        "debate": {
            "bull": (debate.get("bull_history") or "")[:4000],
            "bear": (debate.get("bear_history") or "")[:4000],
            "manager": (state.get("investment_plan") or "")[:4000],
        },
    }
