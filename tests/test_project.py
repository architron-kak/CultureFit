import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from culturefit import main
from culturefit import llm
from culturefit.qloo import Qloo
from culturefit.scoring import evidence, good_tags, is_venue, rank_areas


def venue(name='Cafe', affinity=.8, tags=()):
    return {'name': name, 'query': {'affinity': affinity}, 'tags': [{'name': t} for t in tags]}


@pytest.fixture
def client(monkeypatch):
    class FakeQloo:
        def __init__(self): pass
        async def close(self): pass
        async def search(self, query):
            return None if query == 'missing' else {'entity_id': 'test-id', 'name': query}
        async def places_near(self, *args): return [venue()]
    monkeypatch.setattr(main, 'Qloo', FakeQloo)
    monkeypatch.setattr(llm, 'ask', no_llm)
    with TestClient(main.app) as c:
        yield c


async def no_llm(prompt):
    return None, 'none'


def payload(**kwargs):
    return {'city':'Zurich', 'people':[{'name':'You', 'favorites':['Radiohead']}], **kwargs}


def events(response):
    return [(b.splitlines()[0][7:], json.loads(b.splitlines()[1][6:]))
            for b in response.text.strip().split('\n\n')]


def test_home_and_cities(client):
    assert client.get('/').status_code == 200
    assert 'CultureFit' in client.get('/').text
    assert set(client.get('/api/cities').json()) == {'Zurich', 'Almaty'}
    assert client.get('/.env').status_code == 404


@pytest.mark.parametrize('change', [
    {'people':[]}, {'people':[{'name':'You','favorites':[]}]},
    {'people':[{'name':' ','favorites':['Radiohead']}]},
    {'people':[{'name':'You','favorites':['x']},{'name':'you','favorites':['y']}]},
    {'people':[{'name':str(i),'favorites':['x']} for i in range(3)]},
    {'people':[{'name':'You','favorites':['x']*7}]},
    {'city':'Unknown'}, {'avoid_areas':['Unknown']},
    {'avoid_areas': list(main.CITIES['Zurich']['areas'])},
])
def test_invalid_requests(client, change):
    assert client.post('/api/rank',json=payload(**change)).status_code == 422


def test_ranking_and_explanation(client):
    response = client.post('/api/rank',json=payload())
    assert response.headers['content-type'].startswith('text/event-stream')
    result = dict(events(response))
    assert 'error' not in result
    assert len(result['result']['areas']) == 7
    assert result['explanation']['source'] == 'template'
    assert result['result']['areas'][0]['evidence']['You'][0]['name'] == 'Cafe'


def test_two_people_and_avoid_area(client):
    req=payload(people=[{'name':n,'favorites':['x']} for n in ['You','Partner']],avoid_areas=['altstadt'])
    result=dict(events(client.post('/api/rank',json=req)))['result']
    assert len(result['areas'])==6
    assert set(result['areas'][0]['scores'])=={'You','Partner'}


def test_missing_favorite(client):
    result=dict(events(client.post('/api/rank',json=payload(people=[{'name':'You','favorites':['missing']}]))))
    assert 'error' in result and 'result' not in result


def test_refine_validation(client):
    assert client.post('/api/refine',json={'text':'no bars','city':'Unknown'}).status_code==422
    assert client.post('/api/refine',json={'text':''}).status_code==422
    assert 'bar' in client.post('/api/refine',json={'text':'no bars'}).json()['exclude']


@pytest.mark.parametrize('text,excluded', [('quiet',True),('too noisy',True),('хочу тихий район',True),('хочу шумный район',False),('I want loud nightlife',False),('not quiet',False),('не тихий район',False)])
def test_rules_intent(text,excluded):
    assert bool(llm._rules(text)['exclude'])==excluded


def test_rules_clubs_and_areas():
    assert 'club' in llm._rules('no clubs')['exclude']
    assert llm._rules('avoid Altstadt',['Altstadt','Enge'])['avoid_areas']==['Altstadt']
    assert llm._rules('I love Altstadt',['Altstadt'])['avoid_areas']==[]


def test_gemini_header_and_multiple_text_parts(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')

    def handler(request):
        assert request.headers['x-goog-api-key'] == 'test-gemini-key'
        assert request.url.path.endswith(':generateContent')
        assert json.loads(request.content)['contents'][0]['parts'][0]['text'] == 'Test prompt'
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'text': 'internal reasoning', 'thought': True},
            {'text': 'First '}, {'text': 'second'},
        ]}}]})

    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(llm._gemini('Test prompt')) == 'First second'


def test_missing_data_is_not_fifty():
    r=rank_areas({'You':{'A':[],'B':[venue()]},'Partner':{'A':[venue()],'B':[venue()]}})
    assert r['areas'][0]['area']=='B'
    a=r['areas'][1]
    assert a['group_fit'] is None and a['scores']['You'] is None
    assert a['status']=='insufficient_data'
    assert rank_areas({'You':{'A':[]}})['areas'][0]['group_fit'] is None


def test_scoring_and_invalid_affinity():
    r=rank_areas({'You':{'A':[venue(affinity=.9)],'B':[venue(affinity=.5)]}})
    assert [a['group_fit'] for a in r['areas']]==[100,0]
    assert rank_areas({'You':{'A':[venue(affinity=None)]}})['areas'][0]['group_fit'] is None
    with pytest.raises(ValueError):rank_areas({})


@pytest.mark.parametrize('lower, expected', [(.79, 50), (.81, 75), (.829, 99)])
def test_small_differences_are_not_stretched_to_zero(lower, expected):
    result = rank_areas({'You': {'Best': [venue(affinity=.83)], 'Other': [venue(affinity=lower)]}})
    assert result['areas'][0]['scores']['You'] == 100
    assert result['areas'][1]['scores']['You'] == expected
    assert result['areas'][1]['gives_up']['You'] == 100 - expected
    assert result['low_confidence_for'] == ['You']


def test_equal_affinities_are_tied_best_with_warning():
    result = rank_areas({'You': {'A': [venue()], 'B': [venue()]}})
    assert [area['group_fit'] for area in result['areas']] == [100, 100]
    assert result['low_confidence_for'] == ['You']


def test_group_fit_remains_the_weakest_person_with_minimum_spread():
    result = rank_areas({
        'You': {'A': [venue(affinity=.83)], 'B': [venue(affinity=.79)]},
        'Partner': {'A': [venue(affinity=.78)], 'B': [venue(affinity=.80)]},
    })
    for area in result['areas']:
        assert area['group_fit'] == min(area['scores'].values())
    assert set(result['low_confidence_for']) == {'You', 'Partner'}
    assert all(area['group_fit'] > 0 for area in result['areas'])


def test_utility_tags_are_removed_before_the_evidence_limit():
    entry = venue(tags=['Mastercard', 'Visa', 'Wheelchair accessible parking lot',
                        'Chf 10 to chf 20', 'Nfc mobile payments', 'Ok to order just coffee',
                        'Wi-Fi', 'Reservations', 'Delivery', 'Laundry',
                        'Art', 'Coffee', 'Bohemian', 'Live music', 'Jazz', 'Historic'])
    assert evidence([entry])[0]['tags'] == ['Art', 'Coffee', 'Bohemian', 'Live music', 'Jazz']
    assert good_tags(venue(tags=['Improvisation', 'Cashmere', 'Jazz', 'jazz'])) == ['Improvisation', 'Cashmere', 'Jazz']


def test_clean_tags_reach_the_explanation(client, monkeypatch):
    async def places(*args):
        return [venue(tags=['Visa', 'Wi-Fi', 'Art', 'Coffee'])]
    prompts = []
    async def capture(prompt):
        prompts.append(prompt)
        return None, 'none'
    monkeypatch.setattr(main.qloo, 'places_near', places)
    monkeypatch.setattr(llm, 'ask', capture)
    result = dict(events(client.post('/api/rank', json=payload())))['result']
    assert result['radius'] == 700
    assert result['areas'][0]['evidence']['You'][0]['tags'] == ['Art', 'Coffee']
    assert prompts and 'Visa' not in prompts[0] and 'Wi-Fi' not in prompts[0]
    assert 'Art' in prompts[0] and 'Coffee' in prompts[0]


def test_plural_and_cyrillic_filters():
    assert not is_venue(venue(tags=['Bars']), ['bar'])
    assert not is_venue(venue(tags=['Bar']), ['bars'])
    assert not is_venue(venue(tags=['Nightclub']), ['nightclubs'])
    assert not is_venue(venue(tags=['Nightclubs']), ['nightclub'])
    assert not is_venue(venue(name='Барная стойка'), ['бар'])
    assert is_venue(venue(name='Barbara'), ['bar'])
    assert not is_venue(venue(name='Grand Hotel'))


def test_qloo_contract_cache_retry_and_404():
    async def check():
        calls=[]
        def handler(req):
            calls.append(req)
            assert req.headers['X-Api-Key']=='test-key'
            if req.url.path=='/search':
                if req.url.params['query']=='missing':return httpx.Response(404)
                return httpx.Response(200,json={'results':[{'name':'Other','entity_id':'a'},{'name':'Radiohead','entity_id':'b'}]})
            assert req.url.params['filter.location']=='POINT(8.54 47.37)'
            assert req.url.params['signal.interests.entities']=='b,c'
            if len([x for x in calls if x.url.path=='/v2/insights'])==1:
                return httpx.Response(429,headers={'Retry-After':'0'})
            return httpx.Response(200,json={'results':{'entities':[venue()]}})
        c=Qloo(key='test-key',transport=httpx.MockTransport(handler),rps=10000)
        try:
            assert (await c.search('Radiohead'))['entity_id']=='b'
            await c.search('Radiohead')
            assert len(calls)==1
            assert await c.search('missing') is None
            assert len(await c.places_near(47.37,8.54,1200,['b','c']))==1
        finally:await c.close()
    asyncio.run(check())


def test_upstream_error_is_safe(client,monkeypatch):
    async def fail(query):
        req=httpx.Request('GET','https://example.com')
        raise httpx.HTTPStatusError('sensitive detail',request=req,response=httpx.Response(401,request=req))
    monkeypatch.setattr(main.qloo,'search',fail)
    result=dict(events(client.post('/api/rank',json=payload())))
    assert '401' in result['error']['message']
    assert 'sensitive' not in result['error']['message']
