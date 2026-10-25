"""Explicit live smoke check. Uses the project .env; never prints credentials."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from culturefit.qloo import Qloo

async def run():
    client = Qloo()
    try:
        hit = await client.search('Radiohead')
        if not hit:
            raise RuntimeError('Radiohead was not found')
        print('Search OK:', hit['name'], hit.get('subtype'))
        for city, lat, lon, radius in [('Zurich',47.3717,8.5423,1200),('Almaty',43.2565,76.9455,1500)]:
            places = await client.places_near(lat,lon,radius,[hit['entity_id']])
            print(city, 'places:', len(places))
            for e in places[:2]:
                print(json.dumps({'name':e.get('name'),'affinity':(e.get('query') or {}).get('affinity'),'tags':(e.get('tags') or [])[:2],'has_explanation':bool((e.get('query') or {}).get('explainability'))},ensure_ascii=False))
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(run())
    from fastapi.testclient import TestClient
    from culturefit.main import app
    report = []
    with TestClient(app) as c:
        assert c.get('/').status_code == 200
        for city in ['Zurich', 'Almaty']:
            request = {'city': city, 'people': [
                {'name':'You','favorites':['Blade Runner','Radiohead','Studio Ghibli']},
                {'name':'Partner','favorites':['Metallica','Peaky Blinders','Guinness']},
            ]}
            response = c.post('/api/rank', json=request)
            assert response.status_code == 200
            events = {}
            for block in response.text.strip().split('\n\n'):
                lines = block.splitlines()
                events[lines[0][7:]] = json.loads(lines[1][6:])
            if 'error' in events:
                raise RuntimeError(events['error']['message'])
            assert 'result' in events and 'explanation' in events
            result = events['result']
            row = {'city':city, 'area_count':len(result['areas']),
                   'top_area':result['areas'][0]['area'],
                   'group_fit':result['areas'][0]['group_fit'],
                   'venue_counts':result['areas'][0]['venue_counts'],
                   'explanation_source':events['explanation']['source']}
            print('Full API flow OK:',json.dumps(row,ensure_ascii=False))
            report.append(row)
        refinement=c.post('/api/refine',json={'city':'Zurich','text':'quiet, no bars, avoid Altstadt'})
        assert refinement.status_code==200
        assert 'bar' in refinement.json()['exclude']
        assert refinement.json()['avoid_areas']==['Altstadt']
        print('Refine OK (rules, no LLM required)')
    (ROOT/'artifacts').mkdir(exist_ok=True)
    (ROOT/'artifacts/live-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
