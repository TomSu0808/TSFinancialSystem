"""TradingAgents 适配层（父进程侧）。

上游固定到审核过的提交，不在运行时追踪 main。实际研究在独立子进程中执行：
- 子进程只收到权限校验后的数据快照、模型配置和用户 Key；
- 子进程没有资产数据库连接，也无法调用资产写入接口；
- 子进程环境只注入当前用户的 Provider Key，不改写共享进程环境；
- 用户记忆、缓存、检查点和日志按 user_id 隔离。
"""
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import research_structured

PINNED_COMMIT = "e8f5503e9b86d5c2710b0c76b1f686703968c9df"
PINNED_VERSION = "0.7.0"
PROVIDER_MAP = {
    "gpt": "openai",
    "openai": "openai",
    "deepseek": "deepseek",
    "claude": "anthropic",
    "anthropic": "anthropic",
    "glm": "glm-cn",
}
KEY_ENV = {
    "gpt": "OPENAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "glm": "ZHIPU_CN_API_KEY",
}
ALL_PROVIDER_KEYS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
    "ZHIPU_API_KEY", "ZHIPU_CN_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY",
    "DASHSCOPE_API_KEY", "DASHSCOPE_CN_API_KEY", "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY",
    "MOONSHOT_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY", "TYPESAFE_API_KEY",
)
_BACKEND_DIR = Path(__file__).resolve().parent
_PROBE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROBE_LOCK = threading.Lock()


class TradingAgentsUnavailable(RuntimeError):
    pass


class WorkerHandle:
    def __init__(self, process: subprocess.Popen):
        self.process = process
        self.cancelled = False

    def cancel(self) -> bool:
        if self.process.poll() is not None:
            return False
        self.cancelled = True
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                self.process.terminate()
            except OSError:
                return False
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    self.process.kill()
                except OSError:
                    return False
        return True


def worker_python() -> str:
    return os.getenv("TRADINGAGENTS_PYTHON", sys.executable)


def data_root() -> Path:
    configured = os.getenv("TRADINGAGENTS_DATA_ROOT")
    if configured:
        root = Path(configured)
    else:
        base = os.getenv("DATA_DIR") or str(_BACKEND_DIR)
        root = Path(base) / "tradingagents_data"
    return root


def user_root(user_id: int) -> Path:
    root = data_root() / "users" / str(int(user_id))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _clean_env() -> Dict[str, str]:
    env = os.environ.copy()
    for key in ALL_PROVIDER_KEYS:
        env.pop(key, None)
    for key in list(env):
        if key.startswith("TRADINGAGENTS_"):
            env.pop(key, None)
    env["PYTHONUNBUFFERED"] = "1"
    env["TRADINGAGENTS_NO_UPDATE_CHECK"] = "1"
    return env


def _provider_for(provider: str, base_url: Optional[str]) -> str:
    provider = (provider or "").lower()
    if provider in ("gpt", "openai"):
        if base_url and "api.openai.com" not in base_url:
            return "openai_compatible"
        return "openai"
    if provider in ("claude", "anthropic"):
        return "anthropic"
    if provider == "deepseek":
        return "deepseek"
    if provider == "glm":
        if not base_url or "bigmodel" in base_url:
            return "glm-cn"
        if "z.ai" in base_url:
            return "glm"
        return "openai_compatible"
    return provider


def _key_env_for(provider: str, base_url: Optional[str]) -> str:
    ta_provider = _provider_for(provider, base_url)
    if ta_provider == "openai_compatible":
        return "OPENAI_COMPATIBLE_API_KEY"
    if ta_provider == "anthropic":
        return "ANTHROPIC_API_KEY"
    if ta_provider == "openai":
        return "OPENAI_API_KEY"
    if ta_provider == "deepseek":
        return "DEEPSEEK_API_KEY"
    if ta_provider == "glm-cn":
        return "ZHIPU_CN_API_KEY"
    if ta_provider == "glm":
        return "ZHIPU_API_KEY"
    return KEY_ENV.get(provider, "OPENAI_API_KEY")


def _worker_env(provider: str, api_key: str, base_url: Optional[str], extra_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    env = _clean_env()
    key_env = _key_env_for(provider, base_url)
    env[key_env] = api_key
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items()})
    return env


def system_api_key(provider: str, base_url: Optional[str]) -> str:
    """The system fallback key for this provider, never mutating os.environ."""
    return os.getenv(_key_env_for(provider, base_url), "")


def probe_engine(
    python_executable: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Verify the pinned package is importable before creating a paid task."""
    python = python_executable or worker_python()
    cache_key = python + "|" + json.dumps(extra_env or {}, sort_keys=True)
    with _PROBE_LOCK:
        cached = _PROBE_CACHE.get(cache_key)
        if cached and not force and time.time() - cached["at"] < 30:
            return cached["result"]
    env = _clean_env()
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            [python, "-c",
             "import json, tradingagents; "
             "from tradingagents.graph.trading_graph import TradingAgentsGraph; "
             "print(json.dumps({'version': getattr(tradingagents, '__version__', 'unknown')}))"],
            cwd=str(_BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result = {"available": False, "error": f"无法启动 TradingAgents Python：{exc}"}
    else:
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout.strip().splitlines()[-1])
                result = {"available": True, "version": data.get("version") or "unknown"}
            except (ValueError, IndexError):
                result = {"available": False, "error": "TradingAgents 探测返回无法解析"}
        else:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            result = {
                "available": False,
                "error": "TradingAgents 未安装或无法导入"
                + (("：" + tail[-1][:300]) if tail else ""),
            }
    with _PROBE_LOCK:
        _PROBE_CACHE[cache_key] = {"at": time.time(), "result": result}
    return result


def build_worker_payload(
    report_id: int,
    user_id: int,
    ticker: str,
    trade_date: str,
    asset_type: str,
    provider: str,
    model: str,
    base_url: Optional[str],
    report_language: str,
    portfolio: Optional[Dict[str, Any]],
    limits: Dict[str, Any],
    task_dir: Path,
    extra_context: Optional[str] = None,
) -> Dict[str, Any]:
    root = user_root(user_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(task_dir, 0o700)
    except OSError:
        pass
    ta_provider = _provider_for(provider, base_url)
    config = {
        "results_dir": str(root / "results"),
        "data_cache_dir": str(root / "cache"),
        "memory_log_path": str(root / "memory" / "trading_memory.md"),
        "llm_provider": ta_provider,
        "deep_think_llm": model,
        "quick_think_llm": model,
        "backend_url": base_url if base_url else None,
        "deep_think_backend_url": base_url if base_url else None,
        "quick_think_backend_url": base_url if base_url else None,
        "output_language": "Chinese" if report_language == "zh" else "English",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "max_tool_rounds": int(os.getenv("TRADINGAGENTS_MAX_TOOL_ROUNDS", "8")),
        "checkpoint_enabled": True,
        "temperature": None,
        "max_tokens": int(os.getenv("TRADINGAGENTS_MAX_OUTPUT_TOKENS", "8192")),
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "sec_edgar,yfinance",
            "news_data": "yfinance",
            "macro_data": "fred",
            "prediction_markets": "polymarket",
        },
        "tool_vendors": {},
    }
    return {
        "report_id": int(report_id),
        "user_id": int(user_id),
        "ticker": ticker,
        "trade_date": trade_date,
        "asset_type": asset_type if asset_type in ("stock", "crypto") else "stock",
        "analysts": ["market", "news", "fundamentals"],  # social 默认关闭
        "config": config,
        "portfolio": portfolio,
        "report_language": report_language,
        "billing_provider": provider,
        "billing_model": model,
        "limits": limits,
        "result_path": str(task_dir / "result.json"),
        "extra_context": (extra_context or "")[:12000],
    }


def _stderr_tail(path: Path, limit: int = 2000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:]


def run_worker(
    payload: Dict[str, Any],
    provider: str,
    api_key: str,
    base_url: Optional[str],
    on_event: Callable[[Dict[str, Any]], None],
    on_started: Optional[Callable[[WorkerHandle], None]] = None,
    cancel_requested: Optional[Callable[[], bool]] = None,
    timeout_seconds: int = 3600,
    python_executable: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run the worker and stream its real JSONL events to the callback."""
    python = python_executable or worker_python()
    env = _worker_env(provider, api_key, base_url, extra_env)
    task_dir = Path(payload["result_path"]).parent
    input_path = task_dir / "input.json"
    stderr_path = task_dir / "worker.stderr.log"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(input_path, 0o600)
    except OSError:
        pass

    cmd = [python, str(_BACKEND_DIR / "tradingagents_worker.py"), str(input_path)]
    stderr_file = open(stderr_path, "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_BACKEND_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as exc:
        stderr_file.close()
        return {"status": "failed", "error": f"无法启动 TradingAgents Worker：{exc}"}

    handle = WorkerHandle(proc)
    if on_started:
        on_started(handle)
    started = time.monotonic()
    stage_seen = set()
    try:
        assert proc.stdout is not None
        while True:
            if cancel_requested and cancel_requested():
                handle.cancel()
                return {
                    "status": "cancelled",
                    "provider_cancelled": handle.cancelled,
                    "error": "用户取消，已终止 TradingAgents Worker 子进程",
                }
            line = proc.stdout.readline()
            if line == "" and proc.poll() is not None:
                break
            if not line:
                if time.monotonic() - started > timeout_seconds:
                    handle.cancel()
                    return {
                        "status": "budget_stopped",
                        "provider_cancelled": True,
                        "error": f"执行超过时间上限 {timeout_seconds} 秒，Worker 已终止",
                    }
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "stage" and event.get("stage") not in stage_seen:
                stage_seen.add(event.get("stage"))
            on_event(event)
            if event.get("type") == "budget_exceeded":
                # Stop the process even if the callback exception was swallowed
                # by the agent framework; this is a real budget stop.
                handle.cancel()
                return {
                    "status": "budget_stopped",
                    "provider_cancelled": True,
                    "error": str(event.get("message") or "预算上限已触发"),
                    "usage": event.get("usage"),
                    "engine_commit": PINNED_COMMIT,
                    "engine_version": PINNED_VERSION,
                }
        returncode = proc.wait(timeout=10)
    except Exception as exc:
        handle.cancel()
        return {"status": "failed", "error": f"Worker 通信失败：{exc}"}
    finally:
        stderr_file.close()
        try:
            if proc.stdout:
                proc.stdout.close()
        except OSError:
            pass

    result_path = Path(payload["result_path"])
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            result = {"status": "failed", "error": f"Worker 结果无法解析：{exc}"}
    else:
        result = {"status": "failed", "error": "Worker 未写入结果文件"}
    if returncode != 0 and result.get("status") not in ("failed", "cancelled", "budget_stopped"):
        result["status"] = "failed"
        result["error"] = result.get("error") or _stderr_tail(stderr_path) or f"Worker 退出码 {returncode}"
    result["stderr_tail"] = _stderr_tail(stderr_path)
    result["engine_commit"] = PINNED_COMMIT
    result["engine_version"] = result.get("engine_version") or PINNED_VERSION
    return result


_URL_RE = re.compile(r"https?://[^\s\)\]\}<>\"']+", re.IGNORECASE)


def extract_url_sources(text: str) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        out.append({
            "url": url,
            "title": url,
            "verified": False,
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    return out


def build_result_artifacts(
    result: Dict[str, Any],
    ticker: str,
    report_language: str,
    display_currency: Optional[str] = None,
) -> Dict[str, Any]:
    state = result.get("state") or {}
    role_views = {
        "analysts": {
            "fundamentals": state.get("fundamentals_report"),
            "market": state.get("market_report"),
            "news": state.get("news_report"),
        },
        "research_debate": {
            "bull": (state.get("investment_debate_state") or {}).get("bull_history"),
            "bear": (state.get("investment_debate_state") or {}).get("bear_history"),
        },
        "risk_debate": {
            "aggressive": (state.get("risk_debate_state") or {}).get("aggressive_history"),
            "conservative": (state.get("risk_debate_state") or {}).get("conservative_history"),
            "neutral": (state.get("risk_debate_state") or {}).get("neutral_history"),
        },
        "manager": state.get("investment_plan"),
        "strategy": state.get("trader_investment_plan"),
        "decision": state.get("final_trade_decision"),
        "memory_note": state.get("memory_note"),
    }
    report_md = research_structured.build_multi_agent_report(
        state, ticker, report_language)
    structured = research_structured.build_multi_agent_structured(
        state, role_views, report_language)
    all_text = "\n".join(
        str(v) for v in (
            state.get("fundamentals_report"), state.get("market_report"),
            state.get("news_report"), state.get("final_trade_decision"),
            state.get("investment_plan"),
        ) if v
    )
    sources = extract_url_sources(all_text)
    structured["sources"] = sources
    structured["source_status"]["source_count"] = len(sources)
    multi_agent = {
        "engine": "TradingAgents",
        "engine_version": result.get("engine_version") or PINNED_VERSION,
        "engine_commit": result.get("engine_commit") or PINNED_COMMIT,
        "rating": result.get("rating"),
        "roles": role_views,
        "run_settings": result.get("run_settings") or {},
        "tool_usage": result.get("tool_usage") or {},
        "memory_note": state.get("memory_note"),
        "no_execution": True,
        "display_currency": display_currency,
        "portfolio_note": result.get("portfolio_note"),
    }
    return {
        "report_md": report_md,
        "report_json": structured,
        "multi_agent_json": multi_agent,
        "sources": sources,
        "source_status": structured.get("source_status") or {},
        "usage": result.get("usage"),
        "engine_version": result.get("engine_version") or PINNED_VERSION,
        "engine_commit": result.get("engine_commit") or PINNED_COMMIT,
        "rating": result.get("rating"),
    }


def make_task_dir(user_id: int, report_id: int) -> Path:
    base = Path(user_root(user_id)) / "tasks"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{report_id}-{secrets.token_hex(6)}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def cleanup_task_dir(path: Path) -> None:
    """Never used for user memory/checkpoints; reserved for optional input cleanup."""
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass
