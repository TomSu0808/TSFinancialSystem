"""AI provider client abstraction for research reports.

Supported providers:
- gpt: OpenAI Responses API, with optional web_search.
- deepseek: OpenAI-compatible Chat Completions.
- glm: OpenAI-compatible Chat Completions.
- claude: Anthropic Messages API via requests.
"""
import os
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import requests

AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gpt")
AI_MODEL: str = os.getenv("AI_MODEL", "")
AI_ENABLE_WEB_SEARCH: bool = os.getenv("AI_ENABLE_WEB_SEARCH", "true").lower() == "true"
AI_BACKGROUND_MODE: bool = os.getenv("AI_BACKGROUND_MODE", "true").lower() == "true"
AI_MAX_INPUT_CHARS: int = int(os.getenv("AI_MAX_INPUT_CHARS", "60000"))

_SYNC_RESPONSES: Dict[str, Dict[str, Any]] = {}

DEFAULT_MODELS = {
    "gpt": os.getenv("OPENAI_MODEL", os.getenv("AI_MODEL_GPT", "gpt-5.5")),
    "deepseek": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    "glm": os.getenv("GLM_MODEL", "glm-4.6"),
    "claude": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"),
}

PROVIDER_ALIASES = {
    "openai": "gpt",
    "gpt": "gpt",
    "deepseek": "deepseek",
    "glm": "glm",
    "claude": "claude",
    "anthropic": "claude",
}


class AIServiceNotConfigured(Exception):
    pass


def normalize_provider(provider: Optional[str] = None) -> str:
    raw = (provider or AI_PROVIDER or "gpt").strip().lower()
    return PROVIDER_ALIASES.get(raw, raw)


def choose_model(provider: Optional[str] = None, model: Optional[str] = None) -> str:
    provider_key = normalize_provider(provider)
    if model:
        return model
    if AI_MODEL and normalize_provider() == provider_key:
        return AI_MODEL
    return DEFAULT_MODELS.get(provider_key, AI_MODEL or "gpt-5.5")


def is_configured(provider: Optional[str] = None, api_key: Optional[str] = None) -> bool:
    """Check if provider is usable. If api_key is explicitly provided, always returns True."""
    if api_key:
        return True
    provider_key = normalize_provider(provider)
    if provider_key == "gpt":
        return bool(os.getenv("OPENAI_API_KEY", ""))
    if provider_key == "deepseek":
        return bool(os.getenv("DEEPSEEK_API_KEY", ""))
    if provider_key == "glm":
        return bool(os.getenv("GLM_API_KEY", ""))
    if provider_key == "claude":
        return bool(os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("CLAUDE_API_KEY", ""))
    return False


def _truncate(prompt: str) -> str:
    return prompt[:AI_MAX_INPUT_CHARS] if len(prompt) > AI_MAX_INPUT_CHARS else prompt


def _openai_client(api_key: str, base_url: Optional[str] = None) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AIServiceNotConfigured(
            "openai package is not installed. Run: pip install openai>=2.0.0"
        ) from exc
    kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _sync_id(provider: str) -> str:
    return f"sync-{provider}-{int(time.time() * 1000)}"


def _store_sync_response(provider: str, model: str, text: str, sources: Optional[List[Dict[str, str]]] = None) -> str:
    response_id = _sync_id(provider)
    _SYNC_RESPONSES[response_id] = {
        "id": response_id,
        "status": "completed",
        "provider": provider,
        "model": model,
        "output_text": text,
        "sources": sources or [],
    }
    return response_id


def start_research(
    prompt: str,
    use_web_search: bool = True,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """Submit a research prompt. Returns the provider response ID.

    api_key and base_url are user-supplied keys (BYOK). When provided they take
    priority over the system environment variables.
    """
    provider_key = normalize_provider(provider)
    chosen_model = choose_model(provider_key, model)
    prompt = _truncate(prompt)

    if provider_key == "gpt":
        return _start_openai(prompt, use_web_search, chosen_model, api_key=api_key)
    if provider_key == "deepseek":
        return _start_openai_compatible(
            provider="deepseek",
            prompt=prompt,
            model=chosen_model,
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    if provider_key == "glm":
        return _start_openai_compatible(
            provider="glm",
            prompt=prompt,
            model=chosen_model,
            api_key=api_key or os.getenv("GLM_API_KEY", ""),
            base_url=base_url or os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        )
    if provider_key == "claude":
        return _start_claude(prompt, chosen_model, api_key=api_key)
    raise AIServiceNotConfigured(f"Unsupported AI provider: {provider_key}")


def _start_openai(prompt: str, use_web_search: bool, model: str, api_key: Optional[str] = None) -> str:
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise AIServiceNotConfigured("GPT service is not configured. Please set OPENAI_API_KEY.")
    client = _openai_client(key)

    tools: List[Dict[str, str]] = []
    if use_web_search and AI_ENABLE_WEB_SEARCH:
        tools = [{"type": "web_search_preview"}]

    kwargs: Dict[str, Any] = {"model": model, "input": prompt}
    if tools:
        kwargs["tools"] = tools
    if AI_BACKGROUND_MODE:
        kwargs["background"] = True

    response = client.responses.create(**kwargs)
    return response.id


def _start_openai_compatible(provider: str, prompt: str, model: str, api_key: str, base_url: str) -> str:
    if not api_key:
        raise AIServiceNotConfigured(f"{provider} service is not configured. Please set {provider.upper()}_API_KEY.")
    client = _openai_client(api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content or ""
    return _store_sync_response(provider, model, text)


def _start_claude(prompt: str, model: str, api_key: Optional[str] = None) -> str:
    key = api_key or os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("CLAUDE_API_KEY", "")
    if not key:
        raise AIServiceNotConfigured("Claude service is not configured. Please set ANTHROPIC_API_KEY.")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": int(os.getenv("CLAUDE_MAX_TOKENS", "8192")),
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=int(os.getenv("AI_REQUEST_TIMEOUT", "300")),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Claude API error {response.status_code}: {response.text[:500]}")
    data = response.json()
    text = "\n".join(
        item.get("text", "")
        for item in data.get("content", [])
        if item.get("type") == "text"
    )
    return _store_sync_response("claude", model, text)


def test_provider_connection(
    provider: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """轻量连接测试：发送最小 prompt，不保存结果。

    成功：{"ok": True, "message": "连接成功"}
    失败：{"ok": False, "message": "..."}  (错误信息不包含 api_key)
    """
    provider_key = normalize_provider(provider)
    test_model = model or DEFAULT_MODELS.get(provider_key, "")

    try:
        if provider_key == "gpt":
            client = _openai_client(api_key, base_url=base_url)
            client.chat.completions.create(
                model=test_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
        elif provider_key in ("deepseek", "glm"):
            _base = base_url or (
                os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                if provider_key == "deepseek"
                else os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
            )
            client = _openai_client(api_key, base_url=_base)
            client.chat.completions.create(
                model=test_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
        elif provider_key == "claude":
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": test_model,
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=30,
            )
            if resp.status_code >= 400:
                err = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
                raise RuntimeError(str(err)[:150])
        else:
            raise AIServiceNotConfigured(f"不支持的 provider: {provider_key}")

        return {"ok": True, "message": "连接成功"}

    except AIServiceNotConfigured as exc:
        return {"ok": False, "message": str(exc)}
    except Exception as exc:
        # 截断错误并移除可能包含 key 的内容
        msg = str(exc)[:200]
        if api_key and api_key in msg:
            msg = msg.replace(api_key, "***")
        return {"ok": False, "message": f"连接失败：{msg}"}


def retrieve_response(
    response_id: str,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
) -> Any:
    """Retrieve a response by its ID.

    When BYOK api_key and provider are provided, use the user's own key.
    Falls back to system env key only for sync (non-OpenAI) responses.
    """
    if response_id in _SYNC_RESPONSES:
        return SimpleNamespace(**_SYNC_RESPONSES[response_id])

    # BYOK: use the user's key if provided
    if api_key and provider:
        provider_key = normalize_provider(provider)
        if provider_key == "gpt":
            client = _openai_client(api_key)
            return client.responses.retrieve(response_id)
        # Non-GPT providers are sync — response should be in _SYNC_RESPONSES
        raise AIServiceNotConfigured(
            f"Cannot retrieve remote response for {provider_key}: "
            f"this provider returned a synchronous response."
        )

    api_key_env = os.getenv("OPENAI_API_KEY", "")
    if not api_key_env:
        raise AIServiceNotConfigured("GPT service is not configured. Please set OPENAI_API_KEY.")
    client = _openai_client(api_key_env)
    return client.responses.retrieve(response_id)


def extract_output_text(response: Any) -> str:
    """Extract the text content from a completed response."""
    try:
        if hasattr(response, "output_text") and response.output_text:
            return response.output_text
        texts: List[str] = []
        for item in (getattr(response, "output", None) or []):
            if getattr(item, "type", None) == "message":
                for content in (getattr(item, "content", None) or []):
                    if getattr(content, "type", None) == "output_text":
                        texts.append(getattr(content, "text", "") or "")
        return "\n".join(texts)
    except Exception:
        return ""


def extract_sources(response: Any) -> List[Dict[str, str]]:
    """Extract URL citations from a completed response. Returns [] on any error."""
    if hasattr(response, "sources"):
        return getattr(response, "sources", []) or []
    sources: List[Dict[str, str]] = []
    try:
        for item in (getattr(response, "output", None) or []):
            if getattr(item, "type", None) == "message":
                for content in (getattr(item, "content", None) or []):
                    for ann in (getattr(content, "annotations", None) or []):
                        if getattr(ann, "type", None) == "url_citation":
                            sources.append({
                                "url": getattr(ann, "url", "") or "",
                                "title": getattr(ann, "title", "") or "",
                            })
    except Exception:
        pass
    return sources


def is_response_complete(response: Any) -> bool:
    return getattr(response, "status", None) == "completed"


def is_response_failed(response: Any) -> bool:
    return getattr(response, "status", None) in ("failed", "cancelled", "incomplete")


def cancel_response(
    response_id: str,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
) -> bool:
    """Attempt to cancel a background response. Returns True on success.

    When BYOK api_key and provider are provided, use the user's own key.
    """
    if response_id in _SYNC_RESPONSES:
        _SYNC_RESPONSES[response_id]["status"] = "cancelled"
        return True

    # BYOK: use the user's key if provided
    if api_key and provider:
        provider_key = normalize_provider(provider)
        try:
            if provider_key == "gpt":
                client = _openai_client(api_key)
                client.responses.cancel(response_id)
                return True
            # Non-GPT providers are sync — already completed
            return True
        except Exception:
            return False

    try:
        api_key_env = os.getenv("OPENAI_API_KEY", "")
        if not api_key_env:
            return False
        client = _openai_client(api_key_env)
        client.responses.cancel(response_id)
        return True
    except Exception:
        return False
