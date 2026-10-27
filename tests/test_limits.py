import asyncio
import json

import httpx
import pytest

from culturefit import llm
from culturefit import main
from culturefit.limits import DailyBudget, RequestLimiter
from fastapi.testclient import TestClient


@pytest.fixture
def provider(monkeypatch):
    """Real provider functions, with HTTP replaced so no credentials leave the tests."""
    real_client = httpx.AsyncClient
    state = {'calls': [], 'gemini_status': 200, 'openrouter_status': 200}

    async def handler(request):
        state['calls'].append(request)
        await asyncio.sleep(0)  # Allow another request to compete for the budget.
        if request.url.host == 'generativelanguage.googleapis.com':
            return httpx.Response(state['gemini_status'], json={
                'candidates': [{'content': {'parts': [{'text': 'LLM answer'}]}}],
            })
        return httpx.Response(state['openrouter_status'], json={
            'choices': [{'message': {'content': 'LLM answer'}}],
        })

    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-openrouter-key')
    monkeypatch.setattr(llm, 'OR_MODELS', ['first', 'second', 'third'])
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))
    return state


def sample_result():
    return {'areas': [{'area': 'Enge', 'scores': {'You': 85}, 'gives_up': {'You': 15},
                      'evidence': {'You': [{'name': 'Cafe', 'tags': ['Art']}]}}],
            'low_confidence_for': []}


def test_global_150_attempt_budget_and_exact_utc_reset(provider, clock):
    async def check():
        for number in range(150):
            assert await llm.ask(f'unique prompt {number}') == ('LLM answer', 'gemini')
        assert len(provider['calls']) == 150
        assert await llm.ask('over budget') == (None, 'none')
        result = sample_result()
        assert await llm.explain(result) == {'text': llm._template(result), 'source': 'template'}
        assert (await llm.parse_constraint('no bars', ['Enge']))['source'] == 'rules'
        assert len(provider['calls']) == 150

        clock.advance(12 * 3600 - 1)
        assert await llm.ask('still today') == (None, 'none')
        clock.advance(1)
        assert await llm.ask('new UTC day') == ('LLM answer', 'gemini')
        assert len(provider['calls']) == 151
    asyncio.run(check())


def test_cached_responses_and_missing_keys_do_not_spend_budget(provider, monkeypatch, clock):
    monkeypatch.setattr(llm, '_llm_budget', DailyBudget(limit=1, clock=clock))

    async def check():
        with monkeypatch.context() as patch:
            patch.delenv('GEMINI_API_KEY')
            patch.delenv('OPENROUTER_API_KEY')
            assert await llm.ask('no credentials') == (None, 'none')
        assert await llm.ask('cached') == ('LLM answer', 'gemini')
        assert await llm.ask('cached') == ('LLM answer', 'gemini')
        assert await llm.ask('new generation') == (None, 'none')
        assert len(provider['calls']) == 1
    asyncio.run(check())


def test_failures_and_each_openrouter_model_share_the_budget(provider, monkeypatch, clock):
    monkeypatch.setattr(llm, '_llm_budget', DailyBudget(limit=3, clock=clock))
    provider.update(gemini_status=503, openrouter_status=503)

    async def check():
        assert await llm.ask('provider failures') == (None, 'none')
        assert len(provider['calls']) == 3
        assert [json.loads(r.content)['model'] for r in provider['calls'][1:]] == ['first', 'second']
        assert await llm.ask('no more attempts') == (None, 'none')
        assert len(provider['calls']) == 3
        clock.advance(12 * 3600)
        provider['openrouter_status'] = 200
        assert await llm.ask('fallback tomorrow') == ('LLM answer', 'openrouter')
        assert len(provider['calls']) == 5
    asyncio.run(check())


def test_concurrent_generations_reserve_slots_before_network_io(provider, monkeypatch, clock):
    monkeypatch.setattr(llm, '_llm_budget', DailyBudget(limit=1, clock=clock))

    async def check():
        results = await asyncio.gather(llm.ask('first'), llm.ask('second'))
        assert results.count(('LLM answer', 'gemini')) == 1
        assert results.count((None, 'none')) == 1
        assert len(provider['calls']) == 1
    asyncio.run(check())


def test_refinements_and_explanations_share_the_budget(provider, monkeypatch, clock):
    monkeypatch.setattr(llm, '_llm_budget', DailyBudget(limit=1, clock=clock))

    async def check():
        await llm.parse_constraint('quiet', ['Enge'])
        assert len(provider['calls']) == 1
        assert (await llm.explain(sample_result()))['source'] == 'template'
        assert len(provider['calls']) == 1
    asyncio.run(check())


def test_inactive_ip_buckets_are_discarded(clock):
    limiter = RequestLimiter(clock=clock)
    assert limiter.retry_after(('/api/rank', 'old-ip'), 6) == 0
    clock.advance(3600)
    assert limiter.retry_after(('/api/rank', 'new-ip'), 6) == 0
    assert ('/api/rank', 'old-ip') not in limiter._requests


def test_exhausted_daily_budget_preserves_sse_and_refine_contracts(provider, monkeypatch, clock):
    class FakeQloo:
        async def close(self): pass
        async def search(self, query):
            return {'entity_id': 'test-id', 'name': query}
        async def places_near(self, *args):
            return [{'name': 'Cafe', 'query': {'affinity': .8}, 'tags': [{'name': 'Art'}]}]

    monkeypatch.setattr(main, 'Qloo', FakeQloo)
    monkeypatch.setattr(llm, '_llm_budget', DailyBudget(limit=0, clock=clock))
    with TestClient(main.app) as client:
        response = client.post('/api/rank', json={
            'city': 'Zurich', 'people': [{'name': 'You', 'favorites': ['Radiohead']}],
            'exclude': [], 'avoid_areas': [],
        })
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        events = [(block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:]))
                  for block in response.text.strip().split('\n\n')]
        assert set(name for name, data in events) == {'step', 'result', 'explanation'}
        result = dict(events)['result']
        assert len(result['areas']) == 7
        assert dict(events)['explanation'] == {'text': llm._template(result), 'source': 'template'}
        refined = client.post('/api/refine', json={'city': 'Zurich', 'text': 'no bars'})
        assert refined.status_code == 200
        assert refined.json()['source'] == 'rules' and 'bar' in refined.json()['exclude']
        assert provider['calls'] == []
