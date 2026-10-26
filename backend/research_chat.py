"""报告内追问：独立保存消息，不覆盖原报告。

一个报告一条连续对话。追问默认只使用原报告、输入快照和历史消息；只有用户
明确开启“补充检索”且 Provider 支持时才请求新资料，并标注新增来源与时间。
"""
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

import ai_client
import research_events
import research_prompt_builder
import research_structured
import research_usage
from config import ALLOW_SYSTEM_AI_FALLBACK
from crypto_utils import decrypt_secret
from models import ResearchMessage, ResearchReport, User, UserAIKey

_GUARD = threading.RLock()
_THREADS: Dict[int, threading.Thread] = {}
_CANCEL: Dict[int, threading.Event] = {}
MAX_HISTORY_CHARS = 24000


def _load_snapshot(report: ResearchReport) -> Dict[str, Any]:
    try:
        return json.loads(report.input_snapshot_json or "{}")
    except (TypeError, ValueError):
        return {}


def _data_as_of(report: ResearchReport) -> str:
    snapshot = _load_snapshot(report)
    return snapshot.get("data_cutoff") or (
        report.completed_at.strftime("%Y-%m-%d %H:%M UTC") if report.completed_at else "未知"
    )


def _usage_from_json(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw or "{}")
        return data.get("usage") if isinstance(data, dict) else None
    except (TypeError, ValueError):
        return None


def aggregate_usage(session: Session, report: ResearchReport) -> Dict[str, Any]:
    usages = [_usage_from_json(report.usage_json)]
    messages = session.exec(
        select(ResearchMessage).where(
            ResearchMessage.report_id == report.id,
            ResearchMessage.user_id == report.user_id,
            ResearchMessage.role == "assistant",
        )
    ).all()
    usages.extend(_usage_from_json(m.usage_json) for m in messages)
    return research_usage.merge_usage(*usages)


def list_messages(session: Session, report: ResearchReport) -> List[ResearchMessage]:
    return list(session.exec(
        select(ResearchMessage).where(
            ResearchMessage.report_id == report.id,
            ResearchMessage.user_id == report.user_id,
        ).order_by(ResearchMessage.id.asc())
    ).all())


def _history_for_prompt(messages: List[ResearchMessage]) -> Tuple[str, bool]:
    completed = [m for m in messages if m.status == "completed" and m.content]
    if not completed:
        return "", False
    lines = []
    for message in completed:
        label = "用户" if message.role == "user" else "助手"
        lines.append(f"### {label}（{message.created_at.strftime('%Y-%m-%d %H:%M')}）\n{message.content}")
    text = "\n\n".join(lines)
    if len(text) <= MAX_HISTORY_CHARS:
        return text, False
    # Traceable deterministic compression: keep opening intent and latest turns,
    # plus explicit markers for every dropped message. Original rows are retained.
    kept = completed[:2] + completed[-6:]
    lines = []
    for message in kept:
        label = "用户" if message.role == "user" else "助手"
        lines.append(f"### {label}（{message.created_at.strftime('%Y-%m-%d %H:%M')}）\n{message.content[:4000]}")
    lines.append(
        f"\n> 已压缩：原对话共 {len(completed)} 条消息，此处保留最早 2 条与最近 6 条；"
        "完整消息仍保存在数据库中。"
    )
    return "\n\n".join(lines)[:MAX_HISTORY_CHARS], True


def _resolve_key(session: Session, report: ResearchReport) -> Tuple[Optional[str], str, Optional[str], str]:
    provider = report.provider or ai_client.normalize_provider(None)
    api_key = None
    base_url = report.base_url
    model = report.model or ai_client.choose_model(provider, None)
    if report.user_ai_key_id:
        key = session.get(UserAIKey, report.user_ai_key_id)
        if not key or key.user_id != report.user_id:
            raise RuntimeError("原报告使用的 AI Key 已不可用，请重新配置 API Key")
        api_key = decrypt_secret(key.encrypted_api_key)
        provider = key.provider
        base_url = key.base_url or base_url
    elif not ALLOW_SYSTEM_AI_FALLBACK:
        raise RuntimeError("原报告没有关联的 AI Key，且系统未开启全局 Key 回退")
    return api_key, provider, base_url, model


def _new_sources(report: ResearchReport, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    old = set()
    try:
        for source in json.loads(report.sources_json or "[]"):
            if source.get("url"):
                old.add(source["url"])
    except (TypeError, ValueError):
        pass
    out = []
    for source in sources or []:
        url = source.get("url")
        if url and url not in old:
            item = dict(source)
            item["new_in_followup"] = True
            item.setdefault("retrieved_at", datetime.utcnow().isoformat() + "Z")
            out.append(item)
            old.add(url)
    return out


def start_exchange(
    session: Session,
    user: User,
    report: ResearchReport,
    question: str,
    use_web_search: bool,
    request_id: Optional[str],
    run_inline: bool = False,
) -> ResearchMessage:
    question = (question or "").strip()
    if not question:
        raise ValueError("请输入追问内容")
    if len(question) > 4000:
        raise ValueError("单次追问最多 4000 字")
    if report.status != "completed" or not report.report_md:
        raise ValueError("报告尚未完成，暂时无法追问")

    if request_id:
        existing = session.exec(
            select(ResearchMessage).where(
                ResearchMessage.user_id == user.id,
                ResearchMessage.report_id == report.id,
                ResearchMessage.role == "assistant",
                ResearchMessage.request_id == request_id,
            )
        ).first()
        if existing:
            return existing

    active = session.exec(
        select(ResearchMessage).where(
            ResearchMessage.user_id == user.id,
            ResearchMessage.report_id == report.id,
            ResearchMessage.role == "assistant",
            ResearchMessage.status.in_(["queued", "running"]),
        )
    ).first()
    if active:
        raise ValueError("该报告已有一条追问正在生成，请等待或先停止它")

    limits = research_usage.budget_limits(report.execution_mode)
    total = aggregate_usage(session, report)
    if total.get("calls", 0) >= limits["max_calls"]:
        raise ValueError(f"本报告累计模型调用已达到上限 {limits['max_calls']}，无法继续追问")
    if total.get("output_tokens", 0) >= limits["max_output_tokens"]:
        raise ValueError(f"本报告累计输出 token 已达到上限 {limits['max_output_tokens']}，无法继续追问")
    if limits.get("max_budget") is not None:
        cost = research_usage.calculate_cost(total, report.provider, report.model)
        if cost.get("amount") is None:
            raise ValueError(
                "已设置费用预算，但本报告缺少价格配置或完整用量，无法确认剩余预算；"
                "请补充价格配置或移除费用上限。"
            )
        if cost.get("currency") != limits.get("budget_currency"):
            raise ValueError("费用币种与预算币种不一致，无法继续追问")
        if cost["amount"] >= limits["max_budget"]:
            raise ValueError(
                f"本报告累计费用已达到预算上限 {limits['max_budget']} {limits['budget_currency']}"
            )

    user_message = ResearchMessage(
        user_id=user.id, report_id=report.id, role="user", content=question,
        status="completed", request_id=(request_id + ":user") if request_id else None,
        data_as_of=_data_as_of(report),
    )
    assistant = ResearchMessage(
        user_id=user.id, report_id=report.id, role="assistant", content="",
        status="queued", request_id=request_id,
        data_as_of=_data_as_of(report), used_web_search=bool(use_web_search),
        search_status=(
            "requested" if use_web_search and ai_client.provider_supports_web_search(report.provider)
            else "unsupported_provider" if use_web_search else "not_requested"
        ),
    )
    session.add(user_message)
    session.add(assistant)
    session.commit()
    session.refresh(assistant)
    research_events.append_event(
        session, report, "followup", "started",
        "收到报告内追问；原报告不会被覆盖。",
        {"message_id": assistant.id, "use_web_search": bool(use_web_search)},
        commit=True,
    )
    if run_inline:
        _run_exchange(session, assistant.id, user.id, report.id, question, use_web_search)
        session.refresh(assistant)
        return assistant
    engine = session.get_bind()
    with _GUARD:
        cancel_flag = threading.Event()
        _CANCEL[assistant.id] = cancel_flag
        thread = threading.Thread(
            target=_run_thread,
            args=(engine, assistant.id, user.id, report.id, question, use_web_search, cancel_flag),
            name=f"research-followup-{assistant.id}",
            daemon=True,
        )
        _THREADS[assistant.id] = thread
        thread.start()
    session.refresh(assistant)
    return assistant


def _run_thread(engine, assistant_id, user_id, report_id, question, use_web_search, cancel_flag):
    with Session(engine) as session:
        try:
            _run_exchange(
                session, assistant_id, user_id, report_id, question,
                use_web_search, cancel_flag=cancel_flag,
            )
        finally:
            with _GUARD:
                _THREADS.pop(assistant_id, None)
                _CANCEL.pop(assistant_id, None)


def _is_cancelled(session: Session, assistant_id: int, cancel_flag: Optional[threading.Event]) -> bool:
    if cancel_flag and cancel_flag.is_set():
        return True
    session.expire_all()
    message = session.get(ResearchMessage, assistant_id)
    return bool(message and message.status == "cancelled")


def _run_exchange(
    session: Session,
    assistant_id: int,
    user_id: int,
    report_id: int,
    question: str,
    use_web_search: bool,
    cancel_flag: Optional[threading.Event] = None,
) -> None:
    assistant = session.get(ResearchMessage, assistant_id)
    report = session.get(ResearchReport, report_id)
    user = session.get(User, user_id)
    if not assistant or not report or not user or assistant.user_id != user.id or report.user_id != user.id:
        return
    started = datetime.utcnow()
    assistant.status = "running"
    assistant.updated_at = started
    session.add(assistant)
    session.commit()

    try:
        api_key, provider, base_url, model = _resolve_key(session, report)
        messages = session.exec(
            select(ResearchMessage).where(
                ResearchMessage.report_id == report.id,
                ResearchMessage.user_id == user.id,
                ResearchMessage.id < assistant.id,
            ).order_by(ResearchMessage.id.asc())
        ).all()
        history, compressed = _history_for_prompt(messages)
        data_as_of = _data_as_of(report)
        prompt = research_prompt_builder.build_followup_prompt(
            report_md=report.report_md or "",
            input_context_md=report.input_context_md or "",
            report_title=report.title or report.target_name,
            question=question,
            history=history,
            report_language=report.report_language,
            use_web_search=use_web_search,
            data_as_of=data_as_of,
            context_compressed=compressed,
            search_supported=ai_client.provider_supports_web_search(provider),
        )
        if _is_cancelled(session, assistant_id, cancel_flag):
            session.expire_all()
            assistant = session.get(ResearchMessage, assistant_id)
            if assistant:
                assistant.status = "cancelled"
                assistant.cancelled_at = datetime.utcnow()
                assistant.error_message = "取消发生在提交前，未向 Provider 发起调用"
                assistant.updated_at = datetime.utcnow()
                session.add(assistant)
                session.commit()
            return
        response_id = ai_client.start_research(
            prompt,
            use_web_search=use_web_search,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        assistant.provider_response_id = response_id
        assistant.updated_at = datetime.utcnow()
        session.add(assistant)
        session.commit()

        deadline = time.monotonic() + int(
            research_usage.budget_limits(report.execution_mode)["max_seconds"])
        response = None
        provider_cancelled = False
        while True:
            if _is_cancelled(session, assistant_id, cancel_flag):
                provider_cancelled = ai_client.cancel_response(
                    response_id, api_key=api_key, provider=provider)
                session.expire_all()
                assistant = session.get(ResearchMessage, assistant_id)
                if assistant:
                    assistant.status = "cancelled"
                    assistant.cancelled_at = datetime.utcnow()
                    assistant.error_message = (
                        "已取消；Provider 已确认中断" if provider_cancelled else
                        "已取消；Provider 不支持中断或未确认，在途调用可能仍会计费"
                    )
                    assistant.updated_at = datetime.utcnow()
                    session.add(assistant)
                    session.commit()
                    research_events.append_event(
                        session, report, "followup_cancelled", "cancelled",
                        assistant.error_message,
                        {"message_id": assistant.id, "provider_cancelled": provider_cancelled},
                        commit=True,
                    )
                return
            response = ai_client.retrieve_response(response_id, api_key=api_key, provider=provider)
            if ai_client.is_response_complete(response) or ai_client.is_response_failed(response):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("追问超过执行时间上限")
            time.sleep(2)

        if ai_client.is_response_failed(response):
            status = getattr(response, "status", "failed")
            raise RuntimeError(f"Provider status: {status}")

        text = ai_client.extract_output_text(response) or ""
        sources = research_structured.attach_retrieval_metadata(
            ai_client.extract_sources(response))
        new_sources = _new_sources(report, sources)
        usage = ai_client.extract_usage(response, provider=provider, model=model)
        cost = research_usage.calculate_cost(usage, provider, model)
        search_supported = ai_client.provider_supports_web_search(provider)
        if not use_web_search:
            search_status = "not_requested"
        elif not search_supported:
            search_status = "unsupported_provider"
        elif sources:
            search_status = "sources_returned"
        else:
            search_status = "no_sources_returned"

        snapshot = _load_snapshot(report)
        report_as_of = snapshot.get("data_cutoff") or data_as_of
        answer_as_of = (
            f"原报告数据时点 {report_as_of}；补充检索完成于 "
            + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            if use_web_search and new_sources else
            f"原报告数据时点 {report_as_of}"
        )
        if use_web_search and new_sources:
            text = text.rstrip() + "\n\n---\n**新增来源（本次补充检索）**：\n" + "\n".join(
                f"- [{s.get('title') or s.get('url')}]({s.get('url')})（获取于 {s.get('retrieved_at')}）"
                for s in new_sources
            )
        elif use_web_search and not sources:
            text = text.rstrip() + (
                "\n\n---\n> 本次请求了补充检索，但未返回可核验来源；回答不包含新增外部事实。"
            )

        session.expire_all()
        assistant = session.get(ResearchMessage, assistant_id)
        if assistant and assistant.status == "cancelled":
            return
        assistant.status = "completed"
        assistant.content = text
        assistant.sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
        assistant.new_sources_json = json.dumps(new_sources, ensure_ascii=False) if new_sources else None
        assistant.data_as_of = answer_as_of
        assistant.search_status = search_status
        assistant.context_compressed = compressed
        assistant.usage_json = json.dumps({"usage": usage, "cost": cost}, ensure_ascii=False)
        assistant.updated_at = datetime.utcnow()
        session.add(assistant)
        session.commit()
        research_events.append_event(
            session, report, "followup_completed", "completed",
            "追问回答已独立保存，未覆盖原报告。",
            {
                "message_id": assistant.id,
                "search_status": search_status,
                "new_sources": len(new_sources),
                "usage": usage,
            },
            commit=True,
        )
    except Exception as exc:
        session.rollback()
        assistant = session.get(ResearchMessage, assistant_id)
        if not assistant:
            return
        assistant.status = "failed"
        assistant.error_message = str(exc)[:1200]
        assistant.updated_at = datetime.utcnow()
        session.add(assistant)
        session.commit()
        research_events.append_event(
            session, report, "followup_failed", "failed",
            "追问生成失败；用户问题已保留。",
            {"message_id": assistant.id, "error": assistant.error_message},
            commit=True,
        )


def cancel_message(
    session: Session,
    user: User,
    message: ResearchMessage,
) -> Dict[str, Any]:
    if message.user_id != user.id:
        raise PermissionError("消息不存在")
    if message.role != "assistant":
        return {"ok": False, "provider_cancelled": False, "message": "只能取消助手回答"}
    if message.status not in ("queued", "running"):
        return {"ok": True, "provider_cancelled": False, "message": "回答已结束，无需取消"}
    with _GUARD:
        flag = _CANCEL.get(message.id)
        if flag:
            flag.set()
    provider_cancelled = False
    if message.provider_response_id:
        report = session.get(ResearchReport, message.report_id)
        if report and report.user_id == user.id:
            try:
                api_key, provider, _base_url, _model = _resolve_key(session, report)
                provider_cancelled = ai_client.cancel_response(
                    message.provider_response_id, api_key=api_key, provider=provider)
            except Exception:
                provider_cancelled = False
    message.status = "cancelled"
    message.cancelled_at = datetime.utcnow()
    message.error_message = (
        "已取消；Provider 已确认中断" if provider_cancelled else
        "已取消；在途请求可能仍会计费，Provider 未确认中断"
    )
    message.updated_at = datetime.utcnow()
    session.add(message)
    session.commit()
    return {"ok": True, "provider_cancelled": provider_cancelled, "message": message.error_message}
