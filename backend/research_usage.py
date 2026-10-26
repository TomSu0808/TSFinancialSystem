"""研究任务的 token 用量、费用与预算控制。

只使用模型返回的原始 usage；不同提供商的缓存字段按各自定义记录，不重复
累加到普通输入 token。没有价格配置或 usage 不完整时不估算费用。
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def empty_usage() -> Dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "total_tokens": 0,
        "calls": 0,
        "output_chars": 0,
        "models": [],
    }


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_fields(raw: Dict[str, Any]) -> Dict[str, int]:
    input_tokens = raw.get("input_tokens", raw.get("prompt_tokens"))
    output_tokens = raw.get("output_tokens", raw.get("completion_tokens"))
    total_tokens = raw.get("total_tokens")

    input_details = raw.get("input_tokens_details") or raw.get("prompt_tokens_details") or {}
    output_details = raw.get("output_tokens_details") or raw.get("completion_tokens_details") or {}

    cached = (
        raw.get("cached_input_tokens")
        or raw.get("cache_read_input_tokens")
        or input_details.get("cached_tokens")
        or 0
    )
    cache_creation = raw.get("cache_creation_input_tokens") or 0
    reasoning = (
        raw.get("reasoning_tokens")
        or output_details.get("reasoning_tokens")
        or 0
    )
    return {
        "input_tokens": _as_int(input_tokens),
        "output_tokens": _as_int(output_tokens),
        "reasoning_tokens": _as_int(reasoning),
        "cached_input_tokens": _as_int(cached),
        "cache_creation_input_tokens": _as_int(cache_creation),
        # total_tokens 是提供商给出的计费总量；若缺失才用 input+output 补齐。
        "total_tokens": _as_int(total_tokens) or (_as_int(input_tokens) + _as_int(output_tokens)),
    }


def normalize_usage(
    raw: Optional[Dict[str, Any]],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    calls: int = 1,
    output_chars: int = 0,
) -> Dict[str, Any]:
    """把不同 SDK 的 usage 归一化；不会把缓存 token 重复加到 input。"""
    usage = empty_usage()
    if raw:
        fields = _usage_fields(raw)
        for key, value in fields.items():
            usage[key] = value
    usage["calls"] = max(0, calls)
    usage["output_chars"] = max(0, output_chars)
    if model:
        usage["models"] = [{"provider": provider, "model": model}]
    return usage


def merge_usage(*items: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    total = empty_usage()
    models: List[Dict[str, Any]] = []
    for item in items:
        if not item:
            continue
        for key in (
            "input_tokens", "output_tokens", "reasoning_tokens",
            "cached_input_tokens", "cache_creation_input_tokens",
            "total_tokens", "calls", "output_chars",
        ):
            total[key] += _as_int(item.get(key))
        for model in item.get("models") or []:
            if model not in models:
                models.append(model)
    total["models"] = models
    return total


def _price_table() -> Dict[str, Any]:
    raw = os.getenv("AI_PRICE_TABLE_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def has_price(provider: Optional[str], model: Optional[str]) -> bool:
    table = _price_table()
    return bool(((table.get(provider or "") or {}).get(model or "")))


def calculate_cost(
    usage: Optional[Dict[str, Any]],
    provider: Optional[str],
    model: Optional[str],
) -> Dict[str, Any]:
    """返回可核验的费用或明确的未知原因。

    价格配置示例（AI_PRICE_TABLE_JSON）：
    {"deepseek": {"deepseek-v4-pro": {"input_per_1m": 0.28,
      "output_per_1m": 0.42, "cached_input_per_1m": 0.028, "currency": "USD"}}}
    """
    if not usage or not _as_int(usage.get("calls")):
        return {"amount": None, "currency": None, "basis": None, "reason": "无模型用量记录"}
    table = _price_table()
    price = ((table.get(provider or "") or {}).get(model or "")) or {}
    if not price:
        return {
            "amount": None, "currency": None, "basis": None,
            "reason": f"未配置 {provider}/{model} 的价格，无法计算费用",
        }

    input_tokens = _as_int(usage.get("input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    cached = _as_int(usage.get("cached_input_tokens"))
    cache_creation = _as_int(usage.get("cache_creation_input_tokens"))
    # 缓存输入通常是 input 的子集；按“未缓存输入 + 缓存读取 + 缓存写入”计价。
    uncached = max(0, input_tokens - cached)

    required = [("input_per_1m", uncached), ("output_per_1m", output_tokens)]
    if cached:
        required.append(("cached_input_per_1m", cached))
    if cache_creation:
        required.append(("cache_creation_per_1m", cache_creation))
    missing = [key for key, tokens in required if tokens and price.get(key) is None]
    if missing:
        return {
            "amount": None, "currency": price.get("currency"), "basis": None,
            "reason": "价格配置缺少字段：" + ", ".join(missing),
        }

    amount = 0.0
    for key, tokens in required:
        if tokens:
            amount += tokens * float(price[key]) / 1_000_000.0
    return {
        "amount": round(amount, 6),
        "currency": price.get("currency") or "USD",
        "basis": "按 AI_PRICE_TABLE_JSON 的每百万 token 单价计算",
        "reason": None,
        "price_snapshot": {k: price.get(k) for k in (
            "input_per_1m", "output_per_1m", "cached_input_per_1m",
            "cache_creation_per_1m", "currency",
        )},
    }


def budget_limits(execution_mode: str = "standard") -> Dict[str, Any]:
    multi = execution_mode == "multi_agent"
    max_calls_default = 60 if multi else 12
    max_seconds_default = 3600 if multi else 1800
    raw_budget = os.getenv("RESEARCH_MAX_BUDGET", "").strip()
    try:
        max_budget = float(raw_budget) if raw_budget else None
    except ValueError:
        max_budget = None
    return {
        "max_calls": int(os.getenv("RESEARCH_MAX_LLM_CALLS", str(max_calls_default))),
        "max_output_tokens": int(os.getenv("RESEARCH_MAX_OUTPUT_TOKENS", "120000")),
        "max_seconds": int(os.getenv("RESEARCH_MAX_SECONDS", str(max_seconds_default))),
        "max_budget": max_budget,
        "budget_currency": os.getenv("RESEARCH_BUDGET_CURRENCY", "USD"),
    }


def _elapsed_seconds(started_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    if not started_at:
        return 0.0
    return max(0.0, ((now or datetime.utcnow()) - started_at).total_seconds())


def evaluate_budget(
    usage: Optional[Dict[str, Any]],
    cost: Optional[Dict[str, Any]],
    limits: Dict[str, Any],
    started_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    usage = usage or empty_usage()
    stops: List[str] = []
    if usage.get("calls", 0) >= limits["max_calls"]:
        stops.append(f"调用次数达到上限 {limits['max_calls']}")
    if usage.get("output_tokens", 0) >= limits["max_output_tokens"]:
        stops.append(f"输出 token 达到上限 {limits['max_output_tokens']}")
    elapsed = _elapsed_seconds(started_at, now)
    if elapsed >= limits["max_seconds"]:
        stops.append(f"执行时间达到上限 {limits['max_seconds']} 秒")
    if limits.get("max_budget") is not None:
        if not cost or cost.get("amount") is None:
            # 预算存在但费用未知时不能声称“未超预算”，也不能假装已精确核算。
            stops.append("设置了预算上限，但缺少价格配置或完整用量，无法确认费用")
        elif cost.get("currency") != limits.get("budget_currency"):
            stops.append("费用币种与预算币种不一致，无法比较")
        elif cost["amount"] >= limits["max_budget"]:
            stops.append(f"费用达到预算上限 {limits['max_budget']} {limits['budget_currency']}")
    return {
        "status": "exceeded" if stops else "ok",
        "stop_reasons": stops,
        "elapsed_seconds": round(elapsed, 1),
        "limits": limits,
    }


def aggregate_usage(usages: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    return merge_usage(*usages)
