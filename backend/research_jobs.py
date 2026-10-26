"""TradingAgents 后台任务管理（最小可用、可取消）。

每个任务一个独立 Worker 子进程。父进程只负责持久化事件和最终结果；Worker
不接触资产数据库。取消会终止 Worker 进程组，并如实记录是否成功中断。
"""
import json
import time
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from sqlmodel import Session

import tradingagents_adapter

_lock = threading.Lock()
_handles: Dict[int, tradingagents_adapter.WorkerHandle] = {}
_threads: Dict[int, threading.Thread] = {}
_cancel_flags: Dict[int, threading.Event] = {}


def submit_standard(
    engine: Any,
    report_id: int,
    user_id: int,
    prompt: str,
    use_web_search: bool,
    timeout_seconds: int,
) -> threading.Thread:
    """Run a standard provider call in the background so the UI can poll progress.

    Returns the thread; callers may join briefly so fast responses (and tests)
    still surface the final state without a second round trip.
    """
    with _lock:
        cancel_flag = threading.Event()
        _cancel_flags[report_id] = cancel_flag
        thread = threading.Thread(
            target=_run_standard,
            name=f"research-standard-{report_id}",
            daemon=True,
            args=(engine, report_id, user_id, prompt, use_web_search, timeout_seconds, cancel_flag),
        )
        _threads[report_id] = thread
        thread.start()
        return thread


def wait_for(report_id: int, timeout: float) -> None:
    thread = _threads.get(report_id)
    if thread:
        thread.join(timeout)


def _run_standard(
    engine: Any,
    report_id: int,
    user_id: int,
    prompt: str,
    use_web_search: bool,
    timeout_seconds: int,
    cancel_flag: threading.Event,
) -> None:
    import ai_client
    import research_events
    import research_service
    from models import ResearchReport

    def emit(session, report, stage, status, message, payload=None):
        try:
            research_events.append_event(
                session, report, stage, status, message, payload, commit=True)
        except Exception:
            pass

    with Session(engine) as session:
        report = session.get(ResearchReport, report_id)
        if not report or report.user_id != user_id:
            with _lock:
                _threads.pop(report_id, None)
                _cancel_flags.pop(report_id, None)
            return
        started = datetime.utcnow()
        report.status = "running"
        report.started_at = started
        session.add(report)
        session.commit()
        emit(
            session, report, "provider", "started",
            f"已提交 {report.provider}/{report.model}；联网请求={bool(use_web_search)}",
            {"search_supported": ai_client.provider_supports_web_search(report.provider)},
        )
        provider_cancelled = False
        response_id = None
        try:
            api_key, provider = research_service._resolve_report_ai_key(session, report)
            response_id = ai_client.start_research(
                prompt,
                use_web_search=use_web_search,
                provider=provider,
                model=report.model or "",
                api_key=api_key,
                base_url=report.base_url,
            )
            report.provider_response_id = response_id
            report.updated_at = datetime.utcnow()
            session.add(report)
            session.commit()

            deadline = time.monotonic() + max(30, int(timeout_seconds))
            while True:
                if cancel_flag.is_set():
                    provider_cancelled = ai_client.cancel_response(
                        response_id, api_key=api_key, provider=provider)
                    session.expire_all()
                    report = session.get(ResearchReport, report_id)
                    if report:
                        report.status = "cancelled"
                        report.completed_at = datetime.utcnow()
                        report.updated_at = datetime.utcnow()
                        report.error_message = (
                            "已取消；Provider 已确认中断" if provider_cancelled else
                            "已取消；Provider 不支持中断或未确认，在途调用可能仍会计费"
                        )
                        session.add(report)
                        session.commit()
                        emit(
                            session, report, "cancelled", "cancelled",
                            report.error_message,
                            {"provider_cancelled": provider_cancelled},
                        )
                    return
                response = ai_client.retrieve_response(
                    response_id, api_key=api_key, provider=provider)
                if ai_client.is_response_complete(response):
                    research_service._finalize_standard(
                        session, report, response, provider, report.model or "", started)
                    session.add(report)
                    session.commit()
                    return
                if ai_client.is_response_failed(response):
                    status = getattr(response, "status", "failed")
                    report.status = "cancelled" if status == "cancelled" else "failed"
                    report.error_message = f"Provider status: {status}"
                    report.completed_at = datetime.utcnow()
                    report.updated_at = datetime.utcnow()
                    session.add(report)
                    session.commit()
                    emit(session, report, "provider", report.status, report.error_message)
                    return
                if time.monotonic() >= deadline:
                    report.status = "failed"
                    report.error_message = f"研究超过执行时间上限 {timeout_seconds} 秒"
                    report.completed_at = datetime.utcnow()
                    report.updated_at = datetime.utcnow()
                    session.add(report)
                    session.commit()
                    emit(session, report, "provider", "failed", report.error_message)
                    return
                time.sleep(1.5)
        except Exception as exc:
            session.expire_all()
            report = session.get(ResearchReport, report_id)
            if report:
                report.status = "failed"
                report.error_message = str(exc)[:1200]
                report.completed_at = datetime.utcnow()
                report.updated_at = datetime.utcnow()
                session.add(report)
                session.commit()
                emit(session, report, "provider", "failed", report.error_message)
        finally:
            with _lock:
                _threads.pop(report_id, None)
                _cancel_flags.pop(report_id, None)


def is_active(report_id: int) -> bool:
    with _lock:
        thread = _threads.get(report_id)
        return bool(thread and thread.is_alive())


def submit(
    engine: Any,
    report_id: int,
    user_id: int,
    payload: Dict[str, Any],
    provider: str,
    api_key: str,
    base_url: Optional[str],
    timeout_seconds: int,
) -> None:
    with _lock:
        existing = _threads.get(report_id)
        if existing and existing.is_alive():
            return
        cancel_flag = threading.Event()
        _cancel_flags[report_id] = cancel_flag
        thread = threading.Thread(
            target=_run,
            name=f"tradingagents-report-{report_id}",
            daemon=True,
            args=(engine, report_id, user_id, payload, provider, api_key, base_url, timeout_seconds, cancel_flag),
        )
        _threads[report_id] = thread
        thread.start()


def _record_event(engine: Any, report_id: int, user_id: int, event: Dict[str, Any]) -> None:
    from models import ResearchReport
    import research_events

    with Session(engine) as session:
        report = session.get(ResearchReport, report_id)
        if not report or report.user_id != user_id:
            return
        payload = {
            k: v for k, v in event.items()
            if k not in ("type", "stage", "status", "message")
        }
        research_events.append_event(
            session,
            report,
            stage=str(event.get("stage") or "engine"),
            status=str(event.get("status") or "info"),
            message=str(event.get("message") or ""),
            payload=payload or None,
            commit=True,
        )


def _run(
    engine: Any,
    report_id: int,
    user_id: int,
    payload: Dict[str, Any],
    provider: str,
    api_key: str,
    base_url: Optional[str],
    timeout_seconds: int,
    cancel_flag: threading.Event,
) -> None:
    import research_service

    def on_event(event: Dict[str, Any]) -> None:
        try:
            _record_event(engine, report_id, user_id, event)
        except Exception:
            # Progress persistence must never take down the paid run.
            pass

    def on_started(handle: tradingagents_adapter.WorkerHandle) -> None:
        with _lock:
            _handles[report_id] = handle

    def cancel_requested() -> bool:
        return cancel_flag.is_set()

    try:
        result = tradingagents_adapter.run_worker(
            payload,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            on_event=on_event,
            on_started=on_started,
            cancel_requested=cancel_requested,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        result = {"status": "failed", "error": str(exc)[:1000]}

    with Session(engine) as session:
        from models import ResearchReport
        report = session.get(ResearchReport, report_id)
        if not report or report.user_id != user_id:
            return
        research_service.finalize_multi_agent(session, report, result)
    with _lock:
        _handles.pop(report_id, None)
        _threads.pop(report_id, None)
        _cancel_flags.pop(report_id, None)


def request_cancel(report_id: int) -> bool:
    """Ask a running background task to stop without changing the report."""
    with _lock:
        flag = _cancel_flags.get(report_id)
        if flag:
            flag.set()
            return True
    return False


def cancel(engine: Any, report_id: int, user_id: int) -> Dict[str, Any]:
    """Stop the worker if it is ours; mark the task cancelled when it is."""
    with _lock:
        handle = _handles.get(report_id)
        flag = _cancel_flags.get(report_id)
        if flag:
            flag.set()
    provider_cancelled = bool(handle and handle.cancel())
    stale = handle is None and not is_active(report_id)
    if handle is None and flag is not None:
        # Standard background task: the flag stops the polling loop; an
        # in-flight synchronous provider call cannot be interrupted mid-request.
        provider_cancelled = False
    from models import ResearchReport
    import research_events

    with Session(engine) as session:
        report = session.get(ResearchReport, report_id)
        if report and report.user_id == user_id and report.status in ("running", "queued"):
            report.status = "cancelled"
            report.completed_at = datetime.utcnow()
            report.updated_at = datetime.utcnow()
            if provider_cancelled:
                report.error_message = "已终止 TradingAgents Worker 子进程"
            elif stale:
                report.error_message = "进程已不在运行（可能因服务重启或任务已退出）；已标记为取消"
            elif report.execution_mode == "multi_agent":
                report.error_message = "已请求取消；Worker 未确认中断，结果可能仍会计费"
            else:
                report.error_message = (
                    "已请求取消；已停止后续轮询。若 Provider 不支持中断，"
                    "在途请求可能仍会计费"
                )
            research_events.append_event(
                session, report, "cancelled", "cancelled",
                report.error_message,
                {"provider_cancelled": provider_cancelled},
            )
            session.add(report)
            session.commit()
    return {
        "ok": True,
        "provider_cancelled": provider_cancelled,
        "message": (
            "已终止 Worker" if provider_cancelled else
            "任务进程已不在运行，已标记取消" if stale else
            "已标记取消，未确认 Provider 中断"
        ),
    }
