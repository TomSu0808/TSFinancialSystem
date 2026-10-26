#!/usr/bin/env python3
"""TradingAgents 研究 Worker。

独立进程运行，只读取由父进程校验并写入的输入快照；不导入资产数据库模块，
也不接收任何写资产接口。事件通过 stdout JSONL 实时发送，最终结果写入文件。

该脚本在安装 TradingAgents 的 Python 环境（>=3.11）中运行；后端主进程可以是
较旧的 Python。测试会用 fake `tradingagents` 包执行同一条 Worker 路径。
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import research_usage


class BudgetExceeded(RuntimeError):
    pass


class WorkerPortfolio:
    """与 TradingAgents 的 PortfolioContext 同形，避免依赖其 Pydantic 版本。"""

    def __init__(self, data: Dict[str, Any], extra_context: str = ""):
        self.cash = data.get("cash")
        self.currency = data.get("currency")
        self.positions = list(data.get("positions") or [])
        self.extra_context = extra_context

    def position_in(self, ticker: str) -> Optional[Dict[str, Any]]:
        return next(
            (p for p in self.positions
             if str(p.get("ticker", "")).upper() == ticker.strip().upper()),
            None,
        )

    def render(self, ticker: str) -> str:
        symbol = ticker.strip().upper()
        held = self.position_in(symbol)
        if held is None:
            lines = [f"- No current position in {symbol}"]
        else:
            qty = held.get("quantity")
            avg = held.get("average_price")
            extra = f", average price {avg:,.2f}" if isinstance(avg, (int, float)) else ""
            lines = [f"- Current position in {symbol}: {qty:,.4g} units{extra}"
                     if isinstance(qty, (int, float)) else f"- Current position in {symbol}: {qty} units"]
        if self.cash is not None:
            lines.append(f"- Cash available: {self.cash:,.2f}"
                         + (f" {self.currency}" if self.currency else ""))
        others = [p for p in self.positions if p is not held]
        if others:
            lines.append("- Other positions: " + ", ".join(
                f"{str(p.get('ticker', '')).upper()} {p.get('quantity')}" for p in others))
        if self.extra_context:
            lines.append("- User research question and preferences (context only; no execution): "
                         + self.extra_context[:6000])
        return "Portfolio at the analysis date:\n" + "\n".join(lines)

    def fingerprint(self) -> str:
        return str(hash(json.dumps(
            {"cash": self.cash, "currency": self.currency,
             "positions": self.positions, "extra": self.extra_context},
            sort_keys=True, default=str,
        )))


_EMIT_LOCK = threading.Lock()


def _emit(event: Dict[str, Any]) -> None:
    if "ts" not in event:
        event["ts"] = datetime.utcnow().isoformat() + "Z"
    with _EMIT_LOCK:
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def _write_result(path: str, result: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _generation_text(response: Any) -> str:
    texts: List[str] = []
    try:
        for batch in getattr(response, "generations", None) or []:
            for generation in batch:
                content = getattr(generation, "text", None)
                if not content:
                    message = getattr(generation, "message", None)
                    content = getattr(message, "content", None) if message is not None else None
                if isinstance(content, list):
                    content = "\n".join(
                        str(item.get("text", "")) if isinstance(item, dict) else str(item)
                        for item in content
                    )
                if content:
                    texts.append(str(content))
    except Exception:
        pass
    return "\n".join(texts)


def _message_usage(response: Any) -> Optional[Dict[str, Any]]:
    try:
        for batch in getattr(response, "generations", None) or []:
            for generation in batch:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) if message is not None else None
                if usage:
                    if hasattr(usage, "model_dump"):
                        return usage.model_dump()
                    if isinstance(usage, dict):
                        return usage
    except Exception:
        pass
    return None


class WorkerCallback:
    def __init__(
        self,
        limits: Dict[str, Any],
        started_at: float,
        usage: Dict[str, Any],
        provider: str,
        model: str,
        language: str,
        billing_provider: Optional[str] = None,
        billing_model: Optional[str] = None,
    ):
        self.limits = limits
        self.started_at = started_at
        self.usage = usage
        self.provider = provider
        self.model = model
        self.billing_provider = billing_provider or provider
        self.billing_model = billing_model or model
        self.language = language
        self.tool_usage: Dict[str, int] = {}
        self.stop_reason: Optional[str] = None
        self._runs: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._stage_labels = {
            "Memory Log": "读取研究记忆",
            "Market Analyst": "行情分析",
            "News Analyst": "机构新闻分析",
            "Fundamentals Analyst": "基本面分析",
            "Bull Researcher": "多方研究",
            "Bear Researcher": "空方研究",
            "Research Manager": "研究经理汇总",
            "Trader": "策略观点与情景",
            "Aggressive Analyst": "风险讨论（激进）",
            "Conservative Analyst": "风险讨论（保守）",
            "Neutral Analyst": "风险讨论（中性）",
            "Portfolio Manager": "最终研究结论",
        }

    def _check_budget(self) -> None:
        elapsed = time.monotonic() - self.started_at
        if self.usage.get("calls", 0) >= self.limits.get("max_calls", 999999):
            self.stop_reason = f"LLM 调用次数达到上限 {self.limits.get('max_calls')}"
        elif self.usage.get("output_tokens", 0) >= self.limits.get("max_output_tokens", 10**12):
            self.stop_reason = f"输出 token 达到上限 {self.limits.get('max_output_tokens')}"
        elif elapsed >= self.limits.get("max_seconds", 10**9):
            self.stop_reason = f"执行时间达到上限 {self.limits.get('max_seconds')} 秒"
        if not self.stop_reason and self.limits.get("max_budget") is not None:
            if self.usage.get("calls", 0) <= 0:
                pass
            else:
                cost = research_usage.calculate_cost(
                    self.usage, self.billing_provider, self.billing_model)
                if cost.get("amount") is None:
                    self.stop_reason = (
                        "设置了费用预算，但当前用量/价格无法计算费用："
                        + str(cost.get("reason") or "未知")
                    )
                elif cost.get("currency") != self.limits.get("budget_currency"):
                    self.stop_reason = "费用币种与预算币种不一致，无法比较"
                elif cost["amount"] >= self.limits.get("max_budget"):
                    self.stop_reason = (
                        f"费用达到预算上限 {self.limits.get('max_budget')} "
                        f"{self.limits.get('budget_currency')}"
                    )
        if self.stop_reason:
            _emit({
                "type": "budget_exceeded",
                "stage": "budget",
                "status": "failed",
                "message": self.stop_reason,
                "usage": self.usage,
            })
            raise BudgetExceeded(self.stop_reason)

    def on_chain_start(self, serialized=None, inputs=None, run_id=None, metadata=None, **kwargs):
        name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
        node = (metadata or {}).get("langgraph_node") or name or ""
        stage = node if node in self._stage_labels else None
        if stage:
            with self._lock:
                self._runs[str(run_id)] = stage
            _emit({
                "type": "stage",
                "stage": stage,
                "status": "started",
                "message": self._stage_labels.get(stage, stage),
            })
        self._check_budget()

    def on_chain_end(self, outputs=None, run_id=None, **kwargs):
        with self._lock:
            stage = self._runs.pop(str(run_id), None)
        if stage:
            _emit({
                "type": "stage",
                "stage": stage,
                "status": "completed",
                "message": self._stage_labels.get(stage, stage),
            })

    def on_tool_start(self, serialized=None, input_str=None, run_id=None, **kwargs):
        name = (serialized or {}).get("name") if isinstance(serialized, dict) else None
        name = name or "data_tool"
        with self._lock:
            self.tool_usage[name] = self.tool_usage.get(name, 0) + 1
        _emit({
            "type": "tool",
            "stage": "data_tools",
            "status": "started",
            "message": f"数据工具：{name}",
            "tool": name,
        })

    def on_llm_end(self, response=None, run_id=None, **kwargs):
        raw = None
        llm_output = getattr(response, "llm_output", None) if response is not None else None
        if isinstance(llm_output, dict):
            raw = llm_output.get("token_usage") or llm_output.get("usage")
        if raw is None:
            raw = _message_usage(response)
        text = _generation_text(response)
        normalized = research_usage.normalize_usage(
            raw, provider=self.provider, model=self.model,
            calls=1, output_chars=len(text),
        )
        with self._lock:
            merged = research_usage.merge_usage(self.usage, normalized)
            self.usage.update(merged)
        _emit({
            "type": "usage",
            "stage": "model_usage",
            "status": "info",
            "message": "模型调用用量",
            "usage": normalized,
            "totals": self.usage,
        })
        self._check_budget()


def _safe_state(state: Dict[str, Any]) -> Dict[str, Any]:
    allowed = (
        "company_of_interest", "trade_date", "market_report", "fundamentals_report",
        "news_report", "sentiment_report", "investment_plan",
        "trader_investment_plan", "final_trade_decision", "final_rating",
        "memory_note", "past_context",
    )
    out: Dict[str, Any] = {key: state.get(key) for key in allowed}
    for key in ("investment_debate_state", "risk_debate_state"):
        value = state.get(key) or {}
        out[key] = {
            k: v for k, v in value.items()
            if k in (
                "bull_history", "bear_history", "history", "current_response",
                "aggressive_history", "conservative_history", "neutral_history",
                "latest_speaker",
            ) and isinstance(v, (str, int, float, bool, type(None)))
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    args = parser.parse_args()
    with open(args.input_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    result_path = payload["result_path"]
    started = time.monotonic()
    usage = research_usage.empty_usage()
    provider = (payload.get("config") or {}).get("llm_provider") or ""
    model = (payload.get("config") or {}).get("quick_think_llm") or ""

    def on_signal(signum, frame):
        _emit({
            "type": "cancelled",
            "stage": "cancelled",
            "status": "cancelled",
            "message": "Worker 收到终止信号，已停止后续步骤",
        })
        _write_result(result_path, {
            "status": "cancelled",
            "error": "Worker 收到终止信号",
            "usage": usage,
            "engine_version": "unknown",
        })
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        import tradingagents
        try:
            from tradingagents.default_config import DEFAULT_CONFIG
        except Exception:
            DEFAULT_CONFIG = {}

        version = getattr(tradingagents, "__version__", "unknown")
        _emit({
            "type": "stage", "stage": "engine",
            "status": "started",
            "message": f"TradingAgents {version} 启动（固定提交）",
        })
        callback = WorkerCallback(
            limits=payload.get("limits") or {},
            started_at=started,
            usage=usage,
            provider=provider,
            model=model,
            language=payload.get("report_language") or "zh",
            billing_provider=(payload.get("billing_provider") or provider),
            billing_model=(payload.get("billing_model") or model),
        )
        config = dict(DEFAULT_CONFIG or {})
        config.update(payload.get("config") or {})
        portfolio_data = payload.get("portfolio")
        portfolio = WorkerPortfolio(
            portfolio_data, payload.get("extra_context") or ""
        ) if portfolio_data else None
        graph = TradingAgentsGraph(
            selected_analysts=tuple(payload.get("analysts") or ("market", "news", "fundamentals")),
            debug=False,
            config=config,
            callbacks=[callback],
        )
        state, rating = graph.propagate(
            payload["ticker"],
            payload["trade_date"],
            asset_type=payload.get("asset_type") or "stock",
            portfolio=portfolio,
        )
        if not state:
            raise RuntimeError("TradingAgents 未返回最终状态")
        callback.usage["elapsed_seconds"] = round(time.monotonic() - started, 1)
        if callback.stop_reason:
            _write_result(result_path, {
                "status": "budget_stopped",
                "error": callback.stop_reason,
                "usage": callback.usage,
                "engine_version": version,
            })
            return 2
        result = {
            "status": "completed",
            "state": _safe_state(state),
            "rating": str(rating) if rating is not None else state.get("final_rating"),
            "run_settings": graph.run_settings() if hasattr(graph, "run_settings") else {},
            "tool_usage": {
                "calls": sum(callback.tool_usage.values()),
                "tools": callback.tool_usage,
            },
            "usage": callback.usage,
            "engine_version": version,
            "elapsed_seconds": round(time.monotonic() - started, 1),
        }
        _emit({
            "type": "stage", "stage": "completed",
            "status": "completed",
            "message": "TradingAgents 研究完成",
            "usage": callback.usage,
        })
        _write_result(result_path, result)
        return 0
    except BudgetExceeded as exc:
        _emit({
            "type": "budget_exceeded", "stage": "budget",
            "status": "failed", "message": str(exc),
        })
        _write_result(result_path, {
            "status": "budget_stopped",
            "error": str(exc),
            "usage": usage,
            "engine_version": "unknown",
        })
        return 2
    except SystemExit:
        raise
    except Exception as exc:
        safe_error = str(exc)[:1000]
        for key in ("api_key", "API_KEY", "sk-"):
            if key in safe_error:
                safe_error = safe_error.replace(key, "***")
        _emit({
            "type": "error", "stage": "failed",
            "status": "failed", "message": safe_error,
            "traceback": traceback.format_exc(limit=5)[-3000:],
        })
        _write_result(result_path, {
            "status": "failed",
            "error": safe_error,
            "usage": usage,
            "engine_version": "unknown",
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
