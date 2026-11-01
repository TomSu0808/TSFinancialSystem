"""DeepSeek 联网检索（Search API）与 Provider 收敛的行为测试。

所有 HTTP 都由 monkeypatch 替换，不产生真实检索费用。
"""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import ai_client
import web_search


class _FakeResp:
    def __init__(self, status_code=200, payload=None, text_body=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text_body or json.dumps(payload or {}, ensure_ascii=False)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _results_payload(titles):
    return {
        "results": [
            {
                "title": title,
                "url": f"https://example.com/{i}",
                "date": "2026-07-30T16:00:00+00:00",
                "site_name": "Example",
                "summary": "季度营收同比增长 16%。",
            }
            for i, title in enumerate(titles)
        ]
    }


# ── 查询构造 ──────────────────────────────────────────────────────

def test_build_queries_uses_symbol_and_template_hint():
    queries = web_search.build_queries(
        "Apple", "AAPL", "US", "earnings-review", "zh")
    assert len(queries) == 2
    assert "Apple" in queries[0] and "AAPL" in queries[0]
    assert "财报" in queries[0]
    assert all(len(q) <= 128 for q in queries)


def test_build_queries_portfolio_uses_market_queries():
    queries = web_search.build_queries(
        "", "", "", "portfolio-review", "zh", is_portfolio=True)
    assert any("市场" in q for q in queries)


# ── 检索执行 ──────────────────────────────────────────────────────

def test_run_search_dedupes_and_counts_only_billable(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json["query"])
        # 两条查询返回重叠的 URL，最终应去重。
        return _FakeResp(200, _results_payload(["A", "B"]))

    monkeypatch.setattr(web_search.requests, "post", fake_post)
    outcome = web_search.run_search(["q1", "q2"], api_key="k")
    assert outcome["ok"] is True
    assert outcome["billed_requests"] == 2
    assert len(outcome["results"]) == 2  # 同一个 URL 只保留一条
    assert outcome["errors"] == []
    assert calls == ["q1", "q2"]


def test_run_search_empty_results_not_billed(monkeypatch):
    monkeypatch.setattr(
        web_search.requests, "post",
        lambda *a, **kw: _FakeResp(200, {"results": []}))
    outcome = web_search.run_search(["q"], api_key="k")
    assert outcome["ok"] is False
    assert outcome["billed_requests"] == 0
    assert outcome["errors"]


def test_run_search_http_error_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        web_search.requests, "post",
        lambda *a, **kw: _FakeResp(429, None, "rate limited"))
    outcome = web_search.run_search(["q"], api_key="k")
    assert outcome["ok"] is False
    assert outcome["billed_requests"] == 0
    assert "429" in outcome["errors"][0]


def test_run_search_without_key_makes_no_request(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("不应发起请求")

    monkeypatch.setattr(web_search.requests, "post", boom)
    outcome = web_search.run_search(["q"], api_key="")
    assert outcome["ok"] is False
    assert "API Key" in outcome["errors"][0]


def test_run_search_strips_v1_from_base_url(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        return _FakeResp(200, _results_payload(["A"]))

    monkeypatch.setattr(web_search.requests, "post", fake_post)
    web_search.run_search(["q"], api_key="k", base_url="https://api.deepseek.com/v1")
    assert seen["url"] == "https://api.deepseek.com/v1/tools/search"


# ── 提示词与来源 ───────────────────────────────────────────────────

def test_retrieval_block_marks_items_as_system_fetched():
    retrieval = {
        "results": [{"title": "Apple 季报", "url": "https://x", "date": "2026-07-30",
                     "summary": "营收 1094 亿美元", "via": "deepseek_search"}],
        "queries": ["Apple 财报"],
        "retrieved_at": "2026-11-01T00:00:00Z",
    }
    block = web_search.retrieval_block(retrieval, "zh")
    assert "系统联网检索结果" in block
    assert "Apple 季报" in block
    assert "2026-07-30" in block
    assert "不得编造" in block


def test_retrieval_block_says_not_retrieved_when_empty():
    block = web_search.retrieval_block(
        {"results": [], "queries": ["q"], "retrieved_at": "x"}, "zh")
    assert "没有取得可用结果" in block
    assert "未能检索到" in block


def test_to_sources_keeps_via_and_retrieval_time():
    sources = web_search.to_sources({
        "results": [{"title": "t", "url": "u", "date": "d", "site_name": "s"}],
        "retrieved_at": "2026-11-01T00:00:00Z",
    })
    assert sources[0]["via"] == "deepseek_search"
    assert sources[0]["verified"] is False
    assert sources[0]["retrieved_at"] == "2026-11-01T00:00:00Z"


# ── Provider 收敛 ─────────────────────────────────────────────────

def test_only_gpt_and_deepseek_are_supported():
    assert ai_client.SUPPORTED_PROVIDERS == ("gpt", "deepseek")
    assert ai_client.is_supported_provider("deepseek") is True
    assert ai_client.is_supported_provider("openai") is True   # 别名
    assert ai_client.is_supported_provider("glm") is False
    assert ai_client.is_supported_provider("claude") is False


def test_deepseek_default_model_is_flash():
    assert ai_client.DEFAULT_MODELS["deepseek"] == "deepseek-flash"


def test_deepseek_reports_search_support(monkeypatch):
    monkeypatch.setenv("AI_ENABLE_WEB_SEARCH", "true")
    monkeypatch.setenv("DEEPSEEK_SEARCH_ENABLED", "true")
    assert ai_client.provider_supports_web_search("deepseek") is True
    monkeypatch.setenv("DEEPSEEK_SEARCH_ENABLED", "false")
    assert ai_client.provider_supports_web_search("deepseek") is False


def test_removed_provider_cannot_start_research(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    with pytest.raises(ai_client.AIServiceNotConfigured):
        ai_client.start_research("hi", provider="claude")


# ── 系统检索接入研究报告 ───────────────────────────────────────────

def _mock_search(monkeypatch, results):
    def fake_run_search(queries, api_key, base_url=None, count=5,
                        timeout=None, ori_question=""):
        return {
            "ok": bool(results),
            "results": results,
            "queries": list(queries),
            "billed_requests": 1 if results else 0,
            "errors": [] if results else ["无结果"],
            "retrieved_at": "2026-11-01T00:00:00Z",
        }
    monkeypatch.setattr(web_search, "run_search", fake_run_search)


def test_create_run_injects_retrieval_and_records_sources(
        client, session, user, monkeypatch):
    from tests.test_research_v2 import _make_holding, _response

    holding = _make_holding(session, user)
    _mock_search(monkeypatch, [
        {"title": "Apple 季报", "url": "https://apple.com/earnings",
         "date": "2026-07-30", "summary": "营收同比增长 16%。",
         "via": "deepseek_search", "verified": False},
    ])
    text = (
        "# Apple\n\n## 结论摘要\n稳健。\n\n```research-json\n"
        '{"summary":"估值合理","key_facts":[],"risks":[],"impact":"有限",'
        '"next_watch":[],"tracking":[],"questions":[],"sources":[]}\n```'
    )
    with monkeypatch.context() as m:
        m.setattr("research_service.ALLOW_SYSTEM_AI_FALLBACK", True)
        m.setattr("ai_client.is_configured", lambda *a, **kw: True)
        captured = {}
        m.setattr("ai_client.start_research", lambda *a, **kw: captured.update(
            {"prompt": a[0] if a else kw.get("prompt")}) or "mock-id")
        m.setattr("ai_client.retrieve_response", lambda *a, **kw: _response(text))
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "related_holding_id": holding.id,
            "target_name": holding.name,
            "symbol": holding.symbol,
            "market": holding.market.value,
            "ai_provider": "deepseek",
            "use_web_search": True,
        })
    assert resp.status_code == 200, resp.text
    report = resp.json()

    # 检索结果真的进了提示词。
    assert "系统联网检索结果" in captured["prompt"]
    assert "https://apple.com/earnings" in captured["prompt"]

    # 来源落库并标注为系统抓取。
    sources = json.loads(report["sources_json"])
    assert sources[0]["url"] == "https://apple.com/earnings"
    assert sources[0]["via"] == "deepseek_search"

    status = json.loads(report["source_status_json"])
    assert status["status"] == "sources_returned"
    assert status["system_search"] is True
    assert status["verified"] is False

    usage = json.loads(report["usage_json"])["usage"]
    assert usage["search_requests"] == 1


def test_create_run_without_web_search_skips_retrieval(
        client, session, user, monkeypatch):
    from tests.test_research_v2 import _make_holding, _response

    holding = _make_holding(session, user)
    called = []
    monkeypatch.setattr(
        web_search, "run_search",
        lambda **kw: called.append(kw) or {"results": [], "queries": [],
                                           "billed_requests": 0, "errors": [],
                                           "retrieved_at": "x"})
    text = (
        "# Apple\n\n```research-json\n"
        '{"summary":"s","key_facts":[],"risks":[],"impact":"","next_watch":[],'
        '"tracking":[],"questions":[],"sources":[]}\n```'
    )
    with monkeypatch.context() as m:
        m.setattr("research_service.ALLOW_SYSTEM_AI_FALLBACK", True)
        m.setattr("ai_client.is_configured", lambda *a, **kw: True)
        m.setattr("ai_client.start_research", lambda *a, **kw: "mock-id")
        m.setattr("ai_client.retrieve_response", lambda *a, **kw: _response(text))
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "related_holding_id": holding.id,
            "target_name": holding.name,
            "symbol": holding.symbol,
            "market": holding.market.value,
            "ai_provider": "deepseek",
            "use_web_search": False,
        })
    assert resp.status_code == 200, resp.text
    assert called == []
    status = json.loads(resp.json()["source_status_json"])
    assert status["status"] == "not_requested"


# ── 启动迁移 ──────────────────────────────────────────────────────

def test_migration_removes_glm_and_claude_keys_and_fixes_model(engine, user):
    """迁移：删除已停用 Provider 的 Key，并把 DeepSeek 默认模型收敛到 flash。"""
    import database
    from crypto_utils import encrypt_secret
    from models import UserAIKey
    from sqlmodel import Session

    from sqlalchemy import text

    with Session(engine) as session:
        for provider, model in (
            ("glm", "glm-4.6"),
            ("claude", "claude-sonnet-4-5"),
            ("deepseek", "deepseek-v4-pro"),
        ):
            session.add(UserAIKey(
                user_id=user.id, provider=provider,
                encrypted_api_key=encrypt_secret("k"),
                key_last4="abcd", default_model=model,
            ))
        session.commit()

    original = database.engine
    database.engine = engine
    try:
        database._migrate_ai_providers()
    finally:
        database.engine = original

    with engine.connect() as conn:
        rows = conn.execute(
            text('SELECT provider, default_model FROM "useraikey" ORDER BY id')
        ).fetchall()
    assert [r[0] for r in rows] == ["deepseek"]
    assert rows[0][1] == "deepseek-flash"


def test_migration_is_idempotent(engine):
    import database

    original = database.engine
    database.engine = engine
    try:
        database._migrate_ai_providers()
        database._migrate_ai_providers()
    finally:
        database.engine = original


# ── 成本：检索按每千次计价 ─────────────────────────────────────────

def test_cost_includes_search_requests_per_thousand(monkeypatch):
    import research_usage

    monkeypatch.setenv("AI_PRICE_TABLE_JSON", json.dumps({
        "deepseek": {"deepseek-flash": {
            "input_per_1m": 0.15, "output_per_1m": 0.6,
            "cached_input_per_1m": 0.003, "search_per_1k": 0.75,
            "currency": "USD"}}
    }))
    usage = {"calls": 1, "input_tokens": 0, "output_tokens": 0,
             "cached_input_tokens": 0, "search_requests": 1000}
    cost = research_usage.calculate_cost(usage, "deepseek", "deepseek-flash")
    assert cost["amount"] == pytest.approx(0.75, abs=1e-6)
    assert cost["price_snapshot"]["search_per_1k"] == 0.75


def test_cost_reports_missing_search_price(monkeypatch):
    import research_usage

    monkeypatch.setenv("AI_PRICE_TABLE_JSON", json.dumps({
        "deepseek": {"deepseek-flash": {
            "input_per_1m": 0.15, "output_per_1m": 0.6, "currency": "USD"}}
    }))
    usage = {"calls": 1, "input_tokens": 10, "output_tokens": 5,
             "cached_input_tokens": 0, "search_requests": 3}
    cost = research_usage.calculate_cost(usage, "deepseek", "deepseek-flash")
    assert cost["amount"] is None
    assert "search_per_1k" in cost["reason"]


# ── Key 接口白名单 ────────────────────────────────────────────────

def test_saving_removed_provider_returns_400(client):
    resp = client.post("/api/settings/ai-keys", json={
        "provider": "glm", "api_key": "glm-key-1234"})
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


def test_saving_gpt_and_deepseek_ok(client):
    for provider in ("gpt", "deepseek"):
        resp = client.post("/api/settings/ai-keys", json={
            "provider": provider, "api_key": f"sk-{provider}-0000"})
        assert resp.status_code == 200, resp.text
