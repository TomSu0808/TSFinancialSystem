"""DeepSeek 联网检索（Search API）。

DeepSeek 的 Responses API 服务端 `web_search` 工具只对 deepseek-v4-pro 生效，
flash 上不会真正检索。因此本模块直接调用 DeepSeek 独立的 Search API：
    POST https://api.deepseek.com/v1/tools/search

计费按“成功请求”次数（HTTP 200 且返回非空 results），不是按 token，也不是按条数。
失败的请求不计费，所以这里只把真正拿到结果的查询计入 billed_requests。
"""
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = "https://api.deepseek.com"
SEARCH_PATH = "/v1/tools/search"
DEFAULT_COUNT = 5
MAX_RESULTS = 8
MAX_SUMMARY_CHARS = 700


def search_enabled() -> bool:
    """全局开关，与 GPT 的联网开关共用 AI_ENABLE_WEB_SEARCH。"""
    return os.getenv("AI_ENABLE_WEB_SEARCH", "true").lower() == "true"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _template_hint(template_key: str, report_language: str) -> str:
    zh = report_language != "en"
    if template_key in ("earnings-review", "earnings-team"):
        return "最新财报 业绩 营收 净利润 指引" if zh else "latest earnings results revenue guidance"
    if template_key == "news-pulse":
        return "最新新闻 公告 重大事项" if zh else "latest news announcements"
    if template_key in ("industry-research", "industry-funnel"):
        return "行业 最新 数据 政策" if zh else "industry latest data policy"
    return "最新财报 业绩 重大消息" if zh else "latest earnings material news"


def build_queries(
    target_name: str,
    symbol: str = "",
    market: str = "",
    template_key: str = "",
    report_language: str = "zh",
    is_portfolio: bool = False,
) -> List[str]:
    """最多两条查询：一条偏财报/业绩，一条偏最新消息。"""
    zh = report_language != "en"
    if is_portfolio:
        return [
            "全球市场 本周 重大事件 央行 利率",
            "A股 港股 美股 最新 市场表现",
        ] if zh else [
            "global markets this week central banks rates",
            "US HK A-share market latest",
        ]
    name = (target_name or "").strip()
    id_part = " ".join(part for part in [(symbol or "").strip(), (market or "").strip()] if part)
    subject = f"{name} {id_part}".strip() or name
    hint = _template_hint(template_key, report_language)
    first = f"{subject} {hint}".strip()
    second = (
        f"{subject} 最新消息 公告 2026"
        if zh else f"{subject} latest news filings 2026"
    )
    queries = [first]
    if second != first:
        queries.append(second)
    return [q[:128] for q in queries if q.strip()]


def _clean_result(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = (item.get("url") or "").strip()
    title = (item.get("title") or "").strip()
    if not url and not title:
        return None
    summary = (item.get("summary") or item.get("snippet") or "").strip()
    if len(summary) > MAX_SUMMARY_CHARS:
        summary = summary[:MAX_SUMMARY_CHARS] + "…"
    return {
        "title": title or url,
        "url": url,
        "date": (item.get("date") or "").strip() or None,
        "site_name": (item.get("site_name") or "").strip() or None,
        "summary": summary,
        "via": "deepseek_search",
        "verified": False,
    }


def run_search(
    queries: List[str],
    api_key: str,
    base_url: Optional[str] = None,
    count: int = DEFAULT_COUNT,
    timeout: Optional[int] = None,
    ori_question: str = "",
) -> Dict[str, Any]:
    """逐条查询；任何网络/接口错误都记录在 errors 里，不向调用方抛异常。"""
    retrieved_at = datetime.utcnow().isoformat() + "Z"
    outcome: Dict[str, Any] = {
        "ok": False,
        "results": [],
        "queries": list(queries or []),
        "billed_requests": 0,
        "errors": [],
        "retrieved_at": retrieved_at,
    }
    if not queries:
        outcome["errors"].append("没有可用的检索查询")
        return outcome
    if not api_key:
        outcome["errors"].append("缺少可用于检索的 API Key")
        return outcome

    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    # 用户可能把 base_url 填成 https://api.deepseek.com/v1（OpenAI 兼容写法）。
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    url = root + SEARCH_PATH
    if timeout is None:
        timeout = _int_env("DEEPSEEK_SEARCH_TIMEOUT", 20)
    seen = set()
    for query in queries:
        payload: Dict[str, Any] = {"query": query, "count": int(count), "need_content": False}
        if ori_question:
            payload["ori_question"] = ori_question[:128]
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            outcome["errors"].append(f"{query}: 请求失败 {str(exc)[:160]}")
            continue

        if resp.status_code >= 400:
            outcome["errors"].append(f"{query}: HTTP {resp.status_code} {resp.text[:160]}")
            continue
        try:
            data = resp.json()
        except ValueError:
            outcome["errors"].append(f"{query}: 返回内容不是 JSON")
            continue

        items = data.get("results") or []
        if not items:
            # 空结果不计费，也不算检索成功。
            outcome["errors"].append(f"{query}: 无结果")
            continue
        outcome["billed_requests"] += 1
        for item in items:
            cleaned = _clean_result(item)
            if not cleaned:
                continue
            key = cleaned["url"] or cleaned["title"]
            if key in seen:
                continue
            seen.add(key)
            outcome["results"].append(cleaned)
            if len(outcome["results"]) >= MAX_RESULTS:
                break
        if len(outcome["results"]) >= MAX_RESULTS:
            break

    outcome["ok"] = bool(outcome["results"])
    return outcome


def retrieval_block(retrieval: Optional[Dict[str, Any]], report_language: str = "zh") -> str:
    """把检索结果拼成注入提示词的一段，明确区分“系统抓取”与模型自有知识。"""
    if not retrieval:
        return ""
    results = retrieval.get("results") or []
    zh = report_language != "en"
    if not results:
        if zh:
            return (
                "\n\n## 系统联网检索结果\n\n"
                "本次已请求联网检索，但没有取得可用结果。"
                "不要声称掌握了最新行情或最新财报；缺失部分标注为“未能检索到”。\n"
            )
        return (
            "\n\n## System Web Retrieval\n\n"
            "Search was requested but returned no usable results. Do not claim access to "
            "current prices or the latest filings; mark missing items as not retrieved.\n"
        )

    lines: List[str] = []
    if zh:
        lines.append("\n\n## 系统联网检索结果（由本平台调用 DeepSeek Search 抓取）\n")
        lines.append(
            f"检索时间：{retrieval.get('retrieved_at')}；查询：{'；'.join(retrieval.get('queries') or [])}\n"
        )
        lines.append(
            "以下内容为系统抓取的外部资料原文摘要，不是模型记忆。"
            "请优先据此作答，引用时注明标题、日期与链接。"
            "资料未覆盖的部分必须说明“未能检索到”，不得编造数字或链接。\n"
        )
    else:
        lines.append("\n\n## System Web Retrieval (fetched by this platform via DeepSeek Search)\n")
        lines.append(
            f"Retrieved at: {retrieval.get('retrieved_at')}; queries: "
            f"{'; '.join(retrieval.get('queries') or [])}\n"
        )
        lines.append(
            "The items below are summaries of externally fetched material, not model memory. "
            "Prefer them, and cite title, date and URL. Where they do not cover something, "
            "state that it was not retrieved; never fabricate figures or links.\n"
        )

    for index, item in enumerate(results, start=1):
        date = item.get("date") or ("未知日期" if zh else "date unknown")
        lines.append(
            f"{index}. **{item.get('title')}** — {date} — {item.get('url')}\n"
            f"   {item.get('summary') or ''}\n"
        )
    return "".join(lines)


def to_sources(retrieval: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """转成报告 sources_json 的结构；保留抓取时间，不标记为已核验。"""
    if not retrieval:
        return []
    retrieved_at = retrieval.get("retrieved_at")
    out = []
    for item in retrieval.get("results") or []:
        source = {
            "title": item.get("title"),
            "url": item.get("url"),
            "date": item.get("date"),
            "site_name": item.get("site_name"),
            "via": "deepseek_search",
            "verified": False,
        }
        if retrieved_at:
            source["retrieved_at"] = retrieved_at
        out.append(source)
    return out
