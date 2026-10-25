"""Browser regression checks against the real app with deterministic Qloo responses."""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
(ROOT/'artifacts').mkdir(exist_ok=True)
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH','/tmp/culturefit-browsers')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from culturefit import main
from culturefit import llm

class FakeQloo:
    def __init__(self):pass
    async def close(self):pass
    async def search(self,q):return {'name':q,'entity_id':'id'}
    async def places_near(self,*args):return [{'name':'Test cafe','query':{'affinity':.8},'tags':[{'name':'Coffee'}]}]

async def no_llm(prompt):return None,'none'
main.Qloo=FakeQloo
llm.ask=no_llm

with TestClient(main.app) as client, sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    page=browser.new_page(viewport={'width':1280,'height':900})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    state={'rank_calls':0,'mode':'ok','refine_calls':0}
    def route_app(route):
        req=route.request
        path=req.url.split('culturefit.test',1)[1] or '/'
        if path=='/api/rank':
            state['rank_calls']+=1
            if state['mode']=='http_error':
                route.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'Test service unavailable'}));return
            if state['mode']=='offline':route.abort('failed');return
        if path=='/api/refine':state['refine_calls']+=1
        response=client.request(req.method,path,content=req.post_data,headers={'Content-Type':'application/json'})
        route.fulfill(status=response.status_code,content_type=response.headers.get('content-type','text/plain'),body=response.content)
    page.route('http://culturefit.test/**',route_app)
    # Missing map CDN must not break ranking.
    page.route('https://cdn.jsdelivr.net/**',lambda r:r.abort())
    page.goto('http://culturefit.test/')
    page.wait_for_function('!busy && document.querySelector("#city").options.length===2')
    assert 'Map unavailable' in page.locator('#map').inner_text()
    page.evaluate('run();run();')
    page.wait_for_function('!busy')
    assert state['rank_calls']==1
    assert page.locator('#results h3').count()==7
    assert 'Test cafe' in page.locator('#expl').inner_text()
    page.locator('#ref').fill('no bars')
    page.get_by_role('button',name='Apply',exact=True).click()
    page.wait_for_function('!busy')
    assert 'bar' in page.locator('#cons').inner_text()
    page.locator('#city').select_option('Almaty')
    assert page.locator('#cons').inner_text()==''
    assert page.locator('#results').inner_text()==''
    page.evaluate('run()');page.wait_for_function('!busy')
    assert page.locator('#results h3').count()==4
    state['mode']='http_error'
    page.evaluate('run()');page.wait_for_function('!busy')
    assert 'Test service unavailable' in page.locator('#trace').inner_text()
    assert page.get_by_role('button',name='Find our neighborhood').is_enabled()
    state['mode']='offline'
    page.evaluate('run()');page.wait_for_function('!busy')
    assert 'Failed to fetch' in page.locator('#trace').inner_text()
    # Verify missing-data rendering with real scoring output.
    from culturefit.scoring import rank_areas
    d=rank_areas({'You':{'A':[]}})
    d['radius']=1200
    d['areas'][0].update(lat=47.37,lon=8.54)
    page.evaluate('(d)=>show(d)',d)
    assert 'insufficient data' in page.locator('#results').inner_text().lower()
    assert 'null' not in page.locator('#results').inner_text()
    assert not errors,errors
    (ROOT/'artifacts').mkdir(exist_ok=True)
    page.screenshot(path=str(ROOT/'artifacts/browser-check.png'),full_page=True)
    print('PASS: ranking (7/4 areas), double-click guard, refine, city reset, HTTP/network errors, missing map, missing data; no JS exceptions')
    # Use the actual CDN/map library in a second page, when reachable.
    real=browser.new_page()
    real.route('http://culturefit.test/**',route_app)
    real.goto('http://culturefit.test/')
    real.wait_for_function('!busy')
    if real.evaluate('typeof maplibregl!=="undefined"'):
        real.wait_for_function('ready && map.areTilesLoaded()',timeout=30000)
    real.screenshot(path=str(ROOT/'artifacts/design-desktop-empty.png'),full_page=True)
    if real.evaluate('typeof maplibregl!=="undefined"'):
        state['mode']='ok'
        real.evaluate('run()')
        real.wait_for_function('!busy')
        real.wait_for_function('ready && !!map.getSource("a")',timeout=30000)
        real.wait_for_function('!map.isMoving() && map.areTilesLoaded()',timeout=30000)
        assert real.evaluate('map.getSource("a")._data.features.length')==7
        real.screenshot(path=str(ROOT/'artifacts/design-desktop-results.png'),full_page=True)
        assert real.evaluate('document.body.scrollWidth<=window.innerWidth')
        real.locator('.map-pin').first.click()
        assert real.locator('.result-card.area-selected').count()==1
        real.set_viewport_size({'width':390,'height':844})
        real.wait_for_function('!map.isMoving() && map.areTilesLoaded()',timeout=30000)
        real.screenshot(path=str(ROOT/'artifacts/design-mobile-results.png'),full_page=True)
        assert real.evaluate('document.body.scrollWidth<=window.innerWidth')
        assert real.get_by_role('button',name='Find our neighborhood').is_visible()
        print('PASS: desktop/mobile layouts have no horizontal overflow; map pins select result cards')
        print('PASS: real MapLibre loaded and rendered 7 area polygons')
    else:
        print('LIMITATION: CDN unavailable; map rendering not verified')
    browser.close()
