"""AI 投研 v2：预览、结构化摘要、追问、更新、跟踪事项与 TradingAgents 适配。

TradingAgents 测试使用 fake 上游包执行真实 Worker 子进程路径，不访问外部
模型或行情服务，也不产生费用；这不代表线上 TradingAgents 已经实测通过。
"""
import json
import os
import textwrap
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlmodel import Session, select

from models import (
    Holding, Note, Platform, ResearchMessage, ResearchReport, ResearchRunEvent,
    Transaction, User,
)


def _make_holding(session, user, *, symbol="AAPL", name="Apple", market="US",
                  currency="USD", asset_type="stock", quantity=10,
                  cost_price=100, current_price=120, platform_id=None):
    if platform_id is None:
        platform = Platform(user_id=user.id, name="Test Platform")
        session.add(platform)
        session.commit()
        session.refresh(platform)
        platform_id = platform.id
    holding = Holding(
        user_id=user.id, platform_id=platform_id, symbol=symbol, name=name,
        market=market, currency=currency, asset_type=asset_type,
        quantity=quantity, cost_price=cost_price, current_price=current_price,
    )
    session.add(holding)
    session.commit()
    session.refresh(holding)
    return holding


def _completed_report(session, user, md, *, symbol="AAPL", template="investment-research",
                      report_json=None, sources=None, version=1, parent_id=None):
    report = ResearchReport(
        user_id=user.id,
        template_key=template,
        title="Test Report",
        target_name="Apple",
        symbol=symbol,
        market="US",
        related_holding_id=None,
        status="completed",
        report_md=md,
        report_json=json.dumps(report_json, ensure_ascii=False) if report_json else None,
        sources_json=json.dumps(sources or [], ensure_ascii=False),
        provider="deepseek",
        model="deepseek-v4-pro",
        input_snapshot_json=json.dumps({
            "data_cutoff": "2026-10-26 00:00 UTC",
            "display_currency": "USD",
            "web_search": {"requested": False, "provider": "deepseek"},
        }),
        data_cutoff="2026-10-26 00:00 UTC",
        version=version,
        parent_report_id=parent_id,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


class _CompletedResponse(SimpleNamespace):
    pass


def _response(text, *, sources=None, usage=None):
    return _CompletedResponse(
        status="completed",
        output_text=text,
        sources=sources or [],
        usage=usage or {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )


# ── 结构化摘要 ──────────────────────────────────────────────────────

def test_structured_summary_parses_in_same_response_and_strips_block():
    from research_structured import parse_structured_report, strip_structured_blocks
    md = """# 报告

## 结论摘要
公司经营稳健。

```research-json
{
  "summary": "核心结论：估值合理",
  "key_facts": [
    {"text": "收入增长 10%", "kind": "fact", "source": "2025 年报", "period": "FY2025"},
    {"text": "利润率可能继续提升", "kind": "analysis"}
  ],
  "risks": [{"text": "需求下滑", "kind": "assumption"}],
  "impact": "对持仓影响有限",
  "next_watch": ["下一季财报"],
  "tracking": [{"text": "跟踪 FCF", "metric": "FCF 利润率", "review_date": null,
                "trigger_condition": "下一次财报后"}],
  "questions": ["毛利率能否维持"],
  "sources": [{"title": "年报", "url": "https://example.com/a", "publisher": "公司"}]
}
```
"""
    parsed = parse_structured_report(md)
    assert parsed["degraded"] is False
    assert parsed["summary"] == "核心结论：估值合理"
    assert parsed["key_facts"][0]["kind"] == "fact"
    assert parsed["sources"][0]["url"] == "https://example.com/a"
    body = strip_structured_blocks(md)
    assert "research-json" not in body
    assert "结论摘要" in body


def test_structured_summary_failure_degrades_without_fabricating():
    from research_structured import parse_structured_report
    parsed = parse_structured_report("## 结论摘要\n只有正文，没有 JSON。")
    assert parsed["degraded"] is True
    assert parsed["summary"] is None
    assert parsed["key_facts"] == []


def test_prompt_contains_structured_update_and_boundary_requirements():
    from research_prompt_builder import build_prompt
    prompt = build_prompt(
        skill_md="# Skill", target_name="Apple", report_language="zh",
        is_update=True, previous_report_md="# 上一版\n旧结论", data_cutoff="2026-10-26",
    )
    for keyword in ("research-json", "kind: fact", "平台边界", "研究更新要求", "上一版报告"):
        assert keyword in prompt
    assert "不得输出可执行交易指令" in prompt


# ── 输入预览 / 标的歧义 ──────────────────────────────────────────────

def test_preview_shows_holdings_flags_and_does_not_mutate(client, session, user):
    holding = _make_holding(session, user)
    before = (
        len(session.exec(select(Holding)).all()),
        len(session.exec(select(Transaction)).all()),
        len(session.exec(select(ResearchReport)).all()),
    )
    resp = client.post("/api/research/preview", json={
        "template_key": "investment-research",
        "related_holding_id": holding.id,
        "target_name": holding.name,
        "symbol": holding.symbol,
        "market": holding.market.value,
        "execution_mode": "standard",
        "include_holding_context": True,
        "use_web_search": True,
        "ai_provider": "deepseek",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["includes"]["holdings"] is True
    assert data["includes"]["cost"] is True
    assert data["target"]["holding_id"] == holding.id
    assert data["web_search"]["provider_supports"] is False
    after = (
        len(session.exec(select(Holding)).all()),
        len(session.exec(select(Transaction)).all()),
        len(session.exec(select(ResearchReport)).all()),
    )
    assert before == after


def test_preview_rejects_ambiguous_symbol_without_holding(client, session, user):
    _make_holding(session, user, symbol="0700", name="Tencent HK", market="HK", currency="HKD")
    _make_holding(session, user, symbol="0700", name="Tencent US", market="US", currency="USD")
    resp = client.post("/api/research/preview", json={
        "template_key": "investment-research",
        "symbol": "0700",
        "target_name": "Tencent",
    })
    assert resp.status_code == 400
    assert "多个持仓" in resp.json()["detail"] or "无法自动确定" in resp.json()["detail"]


def test_preview_multi_agent_rejects_unsupported_asset(client, session, user):
    holding = _make_holding(
        session, user, symbol="FUND001", name="A Fund", market="FUND",
        currency="CNY", asset_type="fund")
    resp = client.post("/api/research/preview", json={
        "template_key": "investment-team",
        "related_holding_id": holding.id,
        "target_name": holding.name,
        "symbol": holding.symbol,
        "market": holding.market.value,
        "execution_mode": "multi_agent",
    })
    assert resp.status_code == 400
    assert "暂不支持" in resp.json()["detail"]


def test_yahoo_ticker_mapping_is_explicit():
    from research_target import to_yahoo_ticker
    assert to_yahoo_ticker("700", "HK") == "0700.HK"
    assert to_yahoo_ticker("600519", "A") == "600519.SS"
    assert to_yahoo_ticker("000001", "A") == "000001.SZ"
    assert to_yahoo_ticker("BTC", "CRYPTO", "crypto") == "BTC-USD"
    with pytest.raises(ValueError):
        to_yahoo_ticker("ABC", "FUND", "fund")


# ── 标准研究：资产不变 + 来源状态 + 结构化 ─────────────────────────────

def test_standard_run_does_not_mutate_assets_and_records_source_status(client, session, user):
    holding = _make_holding(session, user)
    before = (
        len(session.exec(select(Holding)).all()),
        len(session.exec(select(Transaction)).all()),
        len(session.exec(select(Note)).all()),
    )
    text = """# Apple\n\n## 结论摘要\n经营稳健。\n\n```research-json
{"summary":"估值合理","key_facts":[{"text":"营收增长","kind":"fact","source":"年报"}],
 "risks":[{"text":"需求下滑","kind":"analysis"}],"impact":"影响有限",
 "next_watch":["财报"],"tracking":[],"questions":[],"sources":[]}
```"""
    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="mock-id"), \
         patch("ai_client.retrieve_response", return_value=_response(text)):
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
    assert report["status"] == "completed"
    parsed = json.loads(report["report_json"])
    assert parsed["summary"] == "估值合理"
    status = json.loads(report["source_status_json"])
    assert status["status"] == "unsupported_provider"
    assert status["verified"] is False
    after = (
        len(session.exec(select(Holding)).all()),
        len(session.exec(select(Transaction)).all()),
        len(session.exec(select(Note)).all()),
    )
    assert before == after


# ── 追问：不覆盖原报告 ──────────────────────────────────────────────

def test_followup_saves_separately_and_keeps_original_report(session, user):
    import research_chat
    original = "# Original report\n\nKeep this exact text."
    report = _completed_report(session, user, original, sources=[])
    question = "如果资本开支继续增长，原结论会怎样变化？"
    answer = "资本开支上升会压低自由现金流，但需结合订单验证。"
    with patch("research_chat.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.provider_supports_web_search", return_value=False), \
         patch("ai_client.start_research", return_value="chat-id"), \
         patch("ai_client.retrieve_response", return_value=_response(answer, sources=[])):
        assistant = research_chat.start_exchange(
            session, user, report, question, use_web_search=True,
            request_id="req-1", run_inline=True,
        )
    session.refresh(report)
    assert report.report_md == original
    messages = session.exec(select(ResearchMessage).where(
        ResearchMessage.report_id == report.id).order_by(ResearchMessage.id)).all()
    assert len(messages) == 2
    assert messages[0].role == "user" and messages[0].content == question
    assert messages[1].role == "assistant"
    assert messages[1].status == "completed"
    assert answer in messages[1].content
    assert messages[1].search_status == "unsupported_provider"


def test_followup_budget_stops_before_call(session, user, monkeypatch):
    import research_chat
    report = _completed_report(session, user, "# Report")
    report.usage_json = json.dumps({"usage": {"calls": 12}})
    session.add(report)
    session.commit()
    monkeypatch.setenv("RESEARCH_MAX_LLM_CALLS", "12")
    with pytest.raises(ValueError, match="上限"):
        research_chat.start_exchange(
            session, user, report, "继续问", use_web_search=False,
            request_id="req-budget", run_inline=True,
        )


# ── 更新版本链 ──────────────────────────────────────────────────────

def test_update_creates_new_version_and_keeps_parent(client, session, user):
    parent = _completed_report(
        session, user, "# v1\n\n旧结论。", report_json={
            "degraded": False, "summary": "旧结论", "key_facts": [],
            "risks": [], "tracking": [],
        })
    text = """# v2\n\n新资料显示需求改善。\n\n```research-json
{"summary":"新结论","key_facts":[{"text":"订单增长","kind":"fact","source":"公告"}],
 "risks":[],"impact":"上调观察","next_watch":["下季财报"],"tracking":[],
 "questions":[],"sources":[{"title":"公告","url":"https://example.com/new"}],
 "changes":{"added_facts":["订单增长"],"assumptions_supported":["需求稳定"],
 "assumptions_invalidated":[],"conclusion_changes":["旧结论→新结论"],
 "unresolved_tracking":[],"coverage_gaps":[]}}
```"""
    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="update-id"), \
         patch("ai_client.retrieve_response", return_value=_response(text)):
        resp = client.post(f"/api/research/reports/{parent.id}/update", json={
            "use_web_search": True,
        })
    assert resp.status_code == 200, resp.text
    child = resp.json()
    assert child["id"] != parent.id
    assert child["parent_report_id"] == parent.id
    assert child["version"] == 2
    assert "上一版报告" in child["prompt_md"]
    session.refresh(parent)
    assert parent.report_md == "# v1\n\n旧结论。"
    chain = client.get(f"/api/research/reports/{child['id']}/versions").json()
    assert [item["version"] for item in chain] == [1, 2]


# ── 跟踪事项：预览 + 选择保存 ──────────────────────────────────────

def test_tracking_candidates_preview_and_selected_save(client, session, user):
    md = """# 报告

## 跟踪指标
- FCF 利润率是否维持在 20% 以上
- 2026-11-15 复查资本开支

## 行动项
- 下一次财报后核对订单
"""
    report = _completed_report(session, user, md, report_json={
        "degraded": True, "summary": None, "key_facts": [], "risks": [], "tracking": [],
    })
    preview = client.get(f"/api/research/reports/{report.id}/tracking-candidates")
    assert preview.status_code == 200
    items = preview.json()["items"]
    assert len(items) >= 3
    chosen = [items[0], items[2]]
    resp = client.post(f"/api/research/reports/{report.id}/tracking-notes", json={
        "items": [
            {"text": item["text"], "metric": item.get("metric"),
             "review_date": item.get("review_date"),
             "trigger_condition": item.get("trigger_condition"), "status": "active"}
            for item in chosen
        ]
    })
    assert resp.status_code == 200, resp.text
    notes = resp.json()["notes"]
    assert len(notes) == 2
    assert all(n["report_version"] == 1 for n in notes)
    saved = session.exec(select(Note).where(Note.source_report_id == report.id)).all()
    assert len(saved) == 2
    # Repeated save reuses instead of duplicating.
    again = client.post(f"/api/research/reports/{report.id}/tracking-notes", json={"items": []})
    assert again.json()["reused"] is True
    assert len(session.exec(select(Note).where(Note.source_report_id == report.id)).all()) == 2


def test_tracking_does_not_invent_review_date():
    from research_structured import tracking_candidates
    items = tracking_candidates("## 行动项\n- 下一次财报后复查订单\n", None)
    assert items
    assert items[0]["review_date"] is None
    assert "下一次财报" in (items[0]["trigger_condition"] or "")


# ── 用户隔离 ────────────────────────────────────────────────────────

def test_messages_events_are_user_isolated(client, session, user):
    report = _completed_report(session, user, "# R")
    other = User(username="other_v2", password_hash="x")
    session.add(other)
    session.commit()
    session.refresh(other)
    other_report = ResearchReport(
        user_id=other.id, template_key="investment-research", title="Other",
        target_name="Other", status="completed", report_md="# Other")
    session.add(other_report)
    session.commit()
    session.refresh(other_report)
    assert client.get(f"/api/research/reports/{other_report.id}/messages").status_code == 404
    assert client.get(f"/api/research/reports/{other_report.id}/events").status_code == 404
    assert client.post(f"/api/research/reports/{other_report.id}/messages", json={
        "question": "test", "request_id": "x"}).status_code == 404


# ── TradingAgents：真实 Worker 子进程 + fake 上游包 ────────────────────

def _write_fake_tradingagents(tmp_path):
    package = tmp_path / "fake_ta" / "tradingagents"
    graph = package / "graph"
    graph.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "0.7.0-fake"\n', encoding="utf-8")
    (graph / "__init__.py").write_text("", encoding="utf-8")
    (graph / "trading_graph.py").write_text(textwrap.dedent('''
        from types import SimpleNamespace

        class TradingAgentsGraph:
            def __init__(self, selected_analysts=(), debug=False, config=None, callbacks=None):
                self.selected_analysts = selected_analysts
                self.config = config or {}
                self.callbacks = callbacks or []

            def run_settings(self):
                return {"version": "0.7.0-fake", "analysts": list(self.selected_analysts)}

            def propagate(self, ticker, trade_date, asset_type="stock", portfolio=None):
                portfolio_text = portfolio.render(ticker) if portfolio is not None else "no portfolio"
                for cb in self.callbacks:
                    cb.on_chain_start({"name": "Memory Log"}, {}, run_id="m",
                                      metadata={"langgraph_node": "Memory Log"})
                    cb.on_chain_end({}, run_id="m")
                    cb.on_chain_start({"name": "Fundamentals Analyst"}, {}, run_id="f",
                                      metadata={"langgraph_node": "Fundamentals Analyst"})
                    cb.on_tool_start({"name": "get_fundamentals"}, ticker, run_id="tool-1")
                    cb.on_llm_end(SimpleNamespace(
                        llm_output={"token_usage": {"prompt_tokens": 120, "completion_tokens": 45}},
                        generations=[[SimpleNamespace(
                            text="fundamentals " + ticker,
                            message=SimpleNamespace(usage_metadata=None),
                        )]],
                    ), run_id="llm-1")
                    cb.on_chain_end({}, run_id="f")
                    cb.on_chain_start({"name": "Portfolio Manager"}, {}, run_id="p",
                                      metadata={"langgraph_node": "Portfolio Manager"})
                    cb.on_chain_end({}, run_id="p")
                state = {
                    "company_of_interest": ticker,
                    "trade_date": trade_date,
                    "market_report": "Market " + ticker + " " + trade_date
                        + " https://example.com/market",
                    "fundamentals_report": "Fundamentals " + ticker,
                    "news_report": "News " + ticker,
                    "sentiment_report": "",
                    "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear"},
                    "investment_plan": "Plan",
                    "trader_investment_plan": "Research scenario only; no order",
                    "risk_debate_state": {"aggressive_history": "Aggressive",
                                           "conservative_history": "Conservative",
                                           "neutral_history": "Neutral"},
                    "final_trade_decision": "Rating: Hold\\n\\nResearch view "
                        + ticker + " " + trade_date + "\\n" + portfolio_text,
                    "final_rating": "Hold",
                    "memory_note": "",
                }
                return state, "Hold"
    '''), encoding="utf-8")
    return str(tmp_path / "fake_ta")


def test_tradingagents_worker_executes_actual_adapter_path(tmp_path, monkeypatch):
    """Runs the real Worker subprocess with a fake upstream package.

    This verifies adapter wiring, event streaming, isolation and result parsing.
    It does not verify live TradingAgents market/news vendors.
    """
    from pathlib import Path
    import tradingagents_adapter

    monkeypatch.setenv("TRADINGAGENTS_DATA_ROOT", str(tmp_path / "ta-data"))
    fake_root = _write_fake_tradingagents(tmp_path)
    payload = tradingagents_adapter.build_worker_payload(
        report_id=7,
        user_id=42,
        ticker="AAPL",
        trade_date="2026-10-26",
        asset_type="stock",
        provider="gpt",
        model="gpt-test",
        base_url=None,
        report_language="zh",
        portfolio={
            "cash": 1000,
            "currency": "USD",
            "positions": [{"ticker": "AAPL", "quantity": 10, "average_price": 150}],
        },
        limits={"max_calls": 20, "max_output_tokens": 10000, "max_seconds": 60},
        task_dir=Path(tmp_path / "task"),
        extra_context="如果资本开支继续增长？",
    )
    events = []
    result = tradingagents_adapter.run_worker(
        payload,
        provider="gpt",
        api_key="sk-test-not-real",
        base_url=None,
        on_event=events.append,
        extra_env={"PYTHONPATH": fake_root},
        timeout_seconds=60,
    )
    assert result["status"] == "completed", result.get("error")
    assert result["rating"] == "Hold"
    assert result["usage"]["input_tokens"] == 120
    assert result["tool_usage"]["tools"]["get_fundamentals"] == 1
    assert "AAPL" in result["state"]["final_trade_decision"]
    assert "2026-10-26" in result["state"]["final_trade_decision"]
    assert "如果资本开支继续增长" in result["state"]["final_trade_decision"]
    stage_names = {event.get("stage") for event in events if event.get("type") == "stage"}
    assert {"Fundamentals Analyst", "Portfolio Manager"} <= stage_names

    artifacts = tradingagents_adapter.build_result_artifacts(
        result, "AAPL", "zh", "USD")
    assert "最终研究结论" in artifacts["report_md"]
    assert "非交易指令" in artifacts["report_md"]
    assert artifacts["report_json"]["degraded"] is False
    assert artifacts["source_status"]["status"] == "agent_data_tools"
    assert artifacts["multi_agent_json"]["no_execution"] is True
    assert any("example.com" in s["url"] for s in artifacts["sources"])


def test_tradingagents_worker_isolated_dirs_and_no_db_access(tmp_path, monkeypatch):
    """Worker input has no database path; memory/cache live under the user dir."""
    from pathlib import Path
    import tradingagents_adapter

    monkeypatch.setenv("TRADINGAGENTS_DATA_ROOT", str(tmp_path / "ta-data"))
    payload = tradingagents_adapter.build_worker_payload(
        report_id=8, user_id=555, ticker="0700.HK", trade_date="2026-10-26",
        asset_type="stock", provider="deepseek", model="deepseek-v4-pro",
        base_url=None, report_language="zh", portfolio=None,
        limits={"max_calls": 5, "max_output_tokens": 1000, "max_seconds": 30},
        task_dir=Path(tmp_path / "task2"),
    )
    blob = json.dumps(payload)
    assert "data.db" not in blob
    assert "DATABASE_URL" not in blob
    cfg = payload["config"]
    assert str(555) in cfg["data_cache_dir"]
    assert str(555) in cfg["memory_log_path"]
    assert payload["analysts"] == ["market", "news", "fundamentals"]
    assert "social" not in payload["analysts"]
    assert payload["config"]["max_debate_rounds"] == 1
    assert payload["config"]["max_risk_discuss_rounds"] == 1


# ── 多 Agent 服务接线与取消 ─────────────────────────────────────────

def test_multi_agent_service_submits_snapshot_and_finalizes(client, session, user):
    import research_jobs
    import research_service

    holding = _make_holding(session, user, symbol="AAPL", name="Apple", market="US", currency="USD")
    other = _make_holding(session, user, symbol="0700", name="Tencent", market="HK",
                          currency="HKD", platform_id=holding.platform_id)
    captured = {}

    def fake_submit(engine, report_id, user_id, payload, provider, api_key,
                    base_url, timeout_seconds):
        captured.update({
            "engine": engine, "report_id": report_id, "user_id": user_id,
            "payload": payload, "provider": provider, "api_key": api_key,
            "timeout": timeout_seconds,
        })

    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("tradingagents_adapter.probe_engine", return_value={"available": True, "version": "0.7.0"}), \
         patch("tradingagents_adapter.system_api_key", return_value="sk-system"), \
         patch("research_jobs.submit", side_effect=fake_submit):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-team",
            "related_holding_id": holding.id,
            "target_name": holding.name,
            "symbol": holding.symbol,
            "market": holding.market.value,
            "execution_mode": "multi_agent",
            "ai_provider": "deepseek",
        })
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["status"] == "queued"
    assert report["execution_mode"] == "multi_agent"
    assert report["engine"] == "TradingAgents"
    assert report["engine_commit"]
    payload = captured["payload"]
    assert payload["ticker"] == "AAPL"
    assert payload["analysts"] == ["market", "news", "fundamentals"]
    assert payload["config"]["max_debate_rounds"] == 1
    assert payload["config"]["max_risk_discuss_rounds"] == 1
    assert all(p["ticker"] != "0700.HK" for p in payload["portfolio"]["positions"])
    assert "data.db" not in json.dumps(payload)
    assert captured["api_key"] == "sk-system"

    # Simulate the real worker result crossing the adapter boundary.
    state = {
        "company_of_interest": "AAPL", "trade_date": "2026-10-26",
        "market_report": "Market", "fundamentals_report": "Fundamentals",
        "news_report": "News", "sentiment_report": "",
        "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear"},
        "investment_plan": "Plan", "trader_investment_plan": "Scenario only",
        "risk_debate_state": {"aggressive_history": "A", "conservative_history": "C",
                               "neutral_history": "N"},
        "final_trade_decision": "Rating: Hold\n\nResearch view", "final_rating": "Hold",
    }
    from models import ResearchReport
    db_report = session.get(ResearchReport, report["id"])
    before = (
        len(session.exec(select(Holding)).all()),
        len(session.exec(select(Transaction)).all()),
        len(session.exec(select(Note)).all()),
    )
    research_service.finalize_multi_agent(session, db_report, {
        "status": "completed", "state": state, "rating": "Hold",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "calls": 1},
        "engine_version": "0.7.0", "engine_commit": "e8f5503e9b86d5c2710b0c76b1f686703968c9df",
        "run_settings": {"quick_think_llm": "deepseek-v4-pro"}, "tool_usage": {"calls": 2},
    })
    session.refresh(db_report)
    assert db_report.status == "completed"
    assert db_report.report_md and "最终研究结论" in db_report.report_md
    assert json.loads(db_report.multi_agent_json)["no_execution"] is True
    after = (
        len(session.exec(select(Holding)).all()),
        len(session.exec(select(Transaction)).all()),
        len(session.exec(select(Note)).all()),
    )
    assert before == after


def test_multi_agent_cancel_records_provider_result(client, session, user):
    import threading
    import research_jobs

    report = ResearchReport(
        user_id=user.id, template_key="investment-team", title="Committee",
        target_name="Apple", symbol="AAPL", market="US", status="running",
        execution_mode="multi_agent", engine="TradingAgents",
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    class FakeHandle:
        def __init__(self):
            self.cancelled = False
        def cancel(self):
            self.cancelled = True
            return True

    handle = FakeHandle()
    with research_jobs._lock:
        research_jobs._handles[report.id] = handle
        research_jobs._cancel_flags[report.id] = threading.Event()
    try:
        resp = client.post(f"/api/research/reports/{report.id}/cancel")
    finally:
        with research_jobs._lock:
            research_jobs._handles.pop(report.id, None)
            research_jobs._cancel_flags.pop(report.id, None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider_cancelled"] is True
    assert handle.cancelled is True
    session.refresh(report)
    assert report.status == "cancelled"
    events = session.exec(select(ResearchRunEvent).where(
        ResearchRunEvent.report_id == report.id)).all()
    assert any(e.stage == "cancelled" for e in events)


# ── 备份：报告版本、追问与偏好 ─────────────────────────────────────

def test_backup_roundtrip_preserves_research_continuity(client, session, user):
    from models import ResearchPreference
    parent = _completed_report(
        session, user, "# v1", symbol="AAPL", report_json={
            "degraded": False, "summary": "旧结论", "key_facts": [], "risks": [], "tracking": [],
        })
    child = _completed_report(
        session, user, "# v2", symbol="AAPL", version=2, parent_id=parent.id,
        report_json={"degraded": False, "summary": "新结论", "key_facts": [], "risks": [],
                     "tracking": [], "changes": {"added_facts": ["订单增长"]}})
    session.add(ResearchPreference(
        user_id=user.id, investment_goal="长期增值", holding_period="3-5 年",
        risk_preference="稳健"))
    session.add(ResearchMessage(
        user_id=user.id, report_id=child.id, role="user", content="追问",
        status="completed", request_id="backup-1"))
    session.add(ResearchMessage(
        user_id=user.id, report_id=child.id, role="assistant", content="回答",
        status="completed", request_id="backup-1", data_as_of="2026-10-26",
        sources_json=json.dumps([{"url": "https://example.com"}])))
    session.commit()

    dump = client.get("/api/backup").json()
    assert dump["research_preferences"][0]["investment_goal"] == "长期增值"
    assert len(dump["research_messages"]) == 2
    assert any(r.get("version") == 2 for r in dump["research_reports"])

    assert client.post("/api/backup/import", json=dump).status_code == 200
    reports = session.exec(select(ResearchReport).where(
        ResearchReport.user_id == user.id)).all()
    assert len(reports) == 2
    by_version = {r.version: r for r in reports}
    assert by_version[2].parent_report_id == by_version[1].id
    assert json.loads(by_version[2].report_json)["changes"]["added_facts"] == ["订单增长"]
    messages = session.exec(select(ResearchMessage).where(
        ResearchMessage.user_id == user.id)).all()
    assert {m.content for m in messages} == {"追问", "回答"}
    assert all(m.report_id == by_version[2].id for m in messages)
    pref = session.exec(select(ResearchPreference).where(
        ResearchPreference.user_id == user.id)).first()
    assert pref.holding_period == "3-5 年"


def test_tradingagents_worker_stops_when_call_budget_exceeded(tmp_path, monkeypatch):
    from pathlib import Path
    import tradingagents_adapter

    monkeypatch.setenv("TRADINGAGENTS_DATA_ROOT", str(tmp_path / "ta-data"))
    fake_root = _write_fake_tradingagents(tmp_path)
    payload = tradingagents_adapter.build_worker_payload(
        report_id=9, user_id=43, ticker="MSFT", trade_date="2026-10-26",
        asset_type="stock", provider="gpt", model="gpt-test", base_url=None,
        report_language="zh", portfolio=None,
        limits={"max_calls": 1, "max_output_tokens": 10000, "max_seconds": 60},
        task_dir=Path(tmp_path / "task-budget"),
    )
    result = tradingagents_adapter.run_worker(
        payload, provider="gpt", api_key="sk-test-not-real", base_url=None,
        on_event=lambda event: None, extra_env={"PYTHONPATH": fake_root},
        timeout_seconds=60,
    )
    assert result["status"] == "budget_stopped"
    assert "上限" in result["error"]
    assert result["usage"]["calls"] == 1


def test_idempotency_key_prevents_duplicate_paid_tasks(client, session, user):
    holding = _make_holding(session, user, symbol="NVDA", name="NVIDIA", market="US")
    text = "# R\n\n```research-json\n{\"summary\":\"ok\",\"key_facts\":[],\"risks\":[],\"tracking\":[],\"sources\":[]}\n```"
    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", return_value="idem-id") as start, \
         patch("ai_client.retrieve_response", return_value=_response(text)):
        payload = {
            "template_key": "investment-research",
            "related_holding_id": holding.id,
            "target_name": holding.name,
            "symbol": holding.symbol,
            "market": holding.market.value,
            "ai_provider": "deepseek",
            "idempotency_key": "same-click-123",
        }
        first = client.post("/api/research/runs", json=payload)
        second = client.post("/api/research/runs", json=payload)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert start.call_count == 1
    reports = session.exec(select(ResearchReport).where(
        ResearchReport.user_id == user.id)).all()
    assert len(reports) == 1


def test_standard_run_returns_before_completion_and_completes_in_background(client, session, user):
    """The browser gets a running report immediately and can poll to completion."""
    import time
    holding = _make_holding(session, user, symbol="SLOW", name="Slow Co", market="US")

    def slow_start(prompt, **kwargs):
        time.sleep(1.2)
        return "slow-response-id"

    text = "# Slow\n\n```research-json\n{\"summary\":\"ok\",\"key_facts\":[],\"risks\":[],\"tracking\":[],\"sources\":[]}\n```"
    with patch("research_service.ALLOW_SYSTEM_AI_FALLBACK", True), \
         patch("ai_client.is_configured", return_value=True), \
         patch("ai_client.start_research", side_effect=slow_start), \
         patch("ai_client.retrieve_response", return_value=_response(text)):
        resp = client.post("/api/research/runs", json={
            "template_key": "investment-research",
            "related_holding_id": holding.id,
            "target_name": holding.name,
            "symbol": holding.symbol,
            "market": holding.market.value,
            "ai_provider": "deepseek",
        })
        assert resp.status_code == 200, resp.text
        first = resp.json()
        assert first["status"] in ("queued", "running")
        report_id = first["id"]
        deadline = time.time() + 8
        final = None
        while time.time() < deadline:
            listing = client.get("/api/research/reports").json()
            final = next((r for r in listing if r["id"] == report_id), None)
            if final and final["status"] == "completed":
                break
            time.sleep(0.4)
        assert final and final["status"] == "completed", final
        assert json.loads(final["report_json"])["summary"] == "ok"
        events = client.get(f"/api/research/reports/{report_id}/events").json()
        stages = {e["stage"] for e in events}
        assert "provider" in stages
