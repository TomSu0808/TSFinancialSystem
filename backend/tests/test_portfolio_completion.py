from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import select

from models import Holding, Platform, ResearchReport, UserAIKey


@pytest.fixture
def fake_ai(monkeypatch):
    calls = []
    monkeypatch.setattr('research_service.ALLOW_SYSTEM_AI_FALLBACK', True)
    monkeypatch.setattr('ai_client.is_configured', lambda provider: True)
    def start(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return 'mock-response'
    monkeypatch.setattr('ai_client.start_research', start)
    monkeypatch.setattr('ai_client.retrieve_response', lambda *args, **kwargs: SimpleNamespace(status='completed', output_text='## 结论摘要\n- **现状**：测试\n## 行动项\n- 核实资料', sources=[]))
    return calls


def asset(session, user):
    p = Platform(user_id=user.id, name='Account')
    session.add(p)
    session.commit()
    h = Holding(user_id=user.id, platform_id=p.id, name='Test', market='US', symbol='TEST', quantity=10, cost_price=10, current_price=12)
    session.add(h)
    session.commit()
    return h


def test_default_provider_and_model_and_duplicate_launch(client, session, user, fake_ai):
    from crypto_utils import encrypt_secret
    asset(session, user)
    for provider, default in [('deepseek', False), ('gpt', True)]:
        session.add(UserAIKey(user_id=user.id, provider=provider, encrypted_api_key=encrypt_secret('test-only-key'),
                              is_default=default, default_model='user-chosen-model'))
    session.commit()
    r = client.post('/api/research/runs', json={'template_key': 'portfolio-review'})
    assert r.status_code == 200, r.text
    assert r.json()['provider'] == 'gpt'
    assert r.json()['model'] == 'user-chosen-model'
    repeat = client.post('/api/research/runs', json={'template_key': 'portfolio-review'})
    assert repeat.json()['id'] == r.json()['id']
    assert len(fake_ai) == 1


def test_empty_and_oversize_portfolios_do_not_call_ai(client, session, user, fake_ai):
    assert client.post('/api/research/runs', json={'template_key': 'portfolio-review'}).status_code == 400
    asset(session, user)
    r = client.post('/api/research/runs', json={'template_key': 'portfolio-review', 'extra_instruction': 'x' * 100001})
    assert r.status_code == 400
    assert '未发送 AI' in r.json()['detail']
    assert fake_ai == []


def test_summary_uses_input_time_and_keeps_previous_success(client, session, user):
    now = datetime.utcnow()
    old = ResearchReport(user_id=user.id, template_key='portfolio-review', title='Old', status='completed',
                         created_at=now - timedelta(hours=2), completed_at=now - timedelta(hours=1),
                         input_context_md='- 分析时点：2026-09-01 12:00 UTC\n- 展示币种：USD',
                         report_md='## 结论摘要\n- **现状**：已分散\n')
    new = ResearchReport(user_id=user.id, template_key='portfolio-review', title='New', status='failed', error_message='mock failure')
    session.add(old)
    session.add(new)
    session.commit()
    response = client.get('/api/research/portfolio-summary').json()
    assert response['report']['id'] == old.id
    assert response['report']['as_of'] == '2026-09-01 12:00 UTC'
    assert response['report']['display_currency'] == 'USD'
    assert response['latest_task']['status'] == 'failed'


def test_portfolio_action_links_only_known_symbols_and_deduplicates(client, session, user):
    h = asset(session, user)
    report = ResearchReport(user_id=user.id, template_key='portfolio-review', title='Portfolio', status='completed',
                            report_md='## 行动项\n- US:TEST — 核实财报\n- US:TEST — 核实财报\n- US:UNKNOWN — 核实代码')
    session.add(report)
    session.commit()
    result = client.post(f'/api/research/reports/{report.id}/tracking-notes').json()
    assert len(result['notes']) == 2
    assert result['notes'][0]['related_holding_id'] == h.id
    assert result['notes'][1]['symbol'] is None
    assert client.post(f'/api/research/reports/{report.id}/tracking-notes').json()['reused']


def test_failed_ai_can_retry_without_reusing_failure(client, session, user, fake_ai, monkeypatch):
    asset(session, user)
    def fail(*args, **kwargs):
        raise RuntimeError('mock provider failure')
    monkeypatch.setattr('ai_client.start_research', fail)
    first = client.post('/api/research/runs', json={'template_key': 'portfolio-review'}).json()
    assert first['status'] == 'failed'
    second = client.post('/api/research/runs', json={'template_key': 'portfolio-review'}).json()
    assert first['id'] != second['id']


def test_editorial_contract_is_portfolio_only():
    from research_prompt_builder import build_prompt
    normal = build_prompt(skill_md='test', target_name='Test')
    portfolio = build_prompt(skill_md='test', target_name='Portfolio', is_portfolio=True)
    assert '最终组合报告排版规范' in portfolio
    assert '最终组合报告排版规范' not in normal
    assert '恰好 3 条' in portfolio
