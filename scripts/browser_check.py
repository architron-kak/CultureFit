"""Browser checks for the night UI using synthetic Qloo/LLM data, never paid API calls."""
import copy,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH','/tmp/culturefit-browsers')
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from culturefit import main,llm

sample=json.loads((ROOT/'tests/fixtures/qloo_places.json').read_text())
raw_why=sample['venues'][0]['why']

class FakeQloo:
    def __init__(self): pass
    async def close(self): pass
    async def search(self,query):return {'name':query,'entity_id':query}
    async def places_near(self,lat,lon,radius,ids):
        affinity=max(.1,min(.95,.6+(lat-47.37)*3)) if ids[0]!='Metallica' else max(.1,min(.95,.75-(lat-47.37)*3))
        return [{'name':v['name'],'query':{'affinity':affinity-i*.02,'explainability':v['why']},'tags':v['tags']} for i,v in enumerate(sample['venues'])]

async def no_llm(prompt):return None,'none'
main.Qloo=FakeQloo
llm.ask=no_llm

with TestClient(main.app) as client, sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    state={'calls':0,'mode':'ok','last_body':None}
    def app_route(route):
        req=route.request
        path=req.url.split('culturefit.test',1)[1] or '/'
        if path=='/api/rank':
            state['calls']+=1
            state['last_body']=json.loads(req.post_data)
            if state['mode']=='http-error':
                route.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'Test service unavailable'}));return
            if state['mode']=='offline':route.abort('failed');return
        r=client.request(req.method,path,content=req.post_data,headers={'Content-Type':'application/json'})
        route.fulfill(status=r.status_code,content_type=r.headers.get('content-type','text/plain'),body=r.content)

    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];why_logs=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda msg:why_logs.append(msg.text) if msg.text.startswith('CultureFit raw venue.why:') else None)
    page.route('http://culturefit.test/**',app_route)
    page.route('https://cdn.jsdelivr.net/**',lambda route:route.abort())
    page.goto('http://culturefit.test/')
    page.wait_for_function('!busy && document.querySelector("#city").options.length===2')
    assert page.locator('#map-fallback').is_visible()
    assert page.locator('meta[name=author]').get_attribute('content')=='architron-kak'
    assert page.locator('.author-credit a').get_attribute('href')=='https://github.com/architron-kak'
    page.evaluate('run();run();')
    page.wait_for_function('!busy')
    assert state['calls']==1
    assert set(state['last_body'])=={'city','people','exclude','avoid_areas'}
    assert page.locator('#results .result-card').count()==7
    assert 'Test cafe' in page.locator('#expl').inner_text()
    assert 'not percentages' in page.locator('.score-note').inner_text()
    assert len(why_logs)==1
    page.locator('.card-button').first.click()
    assert page.locator('#why-drawer').is_visible()
    assert page.locator('.why-diagram').count()==1
    assert page.locator('.why-diagram path[stroke-dasharray]').count()>0
    assert sample['favorite']['entity_id'] in page.locator('#why-records').inner_text()
    assert 'Radiohead' not in page.locator('#diagram-scroll').inner_text()
    assert 'not favorite names' in page.locator('#diagram-note').inner_text()
    page.get_by_role('button',name='Partner',exact=True).click()
    assert page.get_by_role('button',name='Partner',exact=True).get_attribute('aria-pressed')=='true'
    page.keyboard.press('Escape')
    assert page.locator('#why-drawer').is_hidden()
    page.locator('#ref').fill('no bars')
    page.get_by_role('button',name='Apply',exact=True).click()
    page.wait_for_function('!busy')
    assert 'No bar' in page.locator('#cons').inner_text()
    assert 'bar' in state['last_body']['exclude']
    page.locator('#cons button').first.click()
    page.wait_for_function('!busy')
    assert len(why_logs)==1
    page.locator('#city').select_option('Almaty')
    assert page.locator('#cons').inner_text()==''
    assert page.locator('#results').inner_text()==''
    page.evaluate('run()');page.wait_for_function('!busy')
    assert page.locator('#results .result-card').count()==4
    state['mode']='http-error'
    page.evaluate('run()');page.wait_for_function('!busy')
    assert 'Test service unavailable' in page.locator('#trace').inner_text()
    assert page.locator('#search-button').is_enabled()
    state['mode']='offline'
    page.evaluate('run()');page.wait_for_function('!busy')
    assert 'Failed to fetch' in page.locator('#trace').inner_text()
    state['mode']='ok'
    # Missing scores, low confidence, unknown why shapes, and untrusted strings.
    fixture={'areas':[{'area':'<img src=x onerror="window.xss=1">','group_fit':None,'weakest_person':None,'scores':{'You':None},'gives_up':{'You':None},'evidence':{'You':[{'name':'<svg onload="window.xss=1">','affinity':.5,'tags':['<script>x</script>'],'why':{'unknown':[{'name':'Invented favorite'}]}}]},'lat':47.37,'lon':8.54}], 'low_confidence_for':['You'], 'spread':{'You':0},'radius':1200,'trace':[]}
    page.evaluate('(data)=>show(data)',fixture)
    assert page.locator('#confidence-notice').is_visible()
    assert 'Judge by the venues' in page.locator('#confidence-notice').inner_text()
    assert page.locator('#results img,#results svg,#results script').count()==0
    assert page.evaluate('window.xss') is None
    assert 'Insufficient data' in page.locator('#results').inner_text()
    page.locator('.card-button').first.click()
    assert page.locator('.why-diagram path[stroke-dasharray]').count()==0
    assert 'No supported' in page.locator('#why-records').inner_text()
    page.keyboard.press('Escape')
    # Byte-split SSE, CRLF separators, Unicode, and a final block without a separator.
    fixture['areas'][0]['area']='Zürich — <safe>'
    events='event: step\r\ndata: '+json.dumps({'text':'Café <safe>'},ensure_ascii=False)+'\r\n\r\nevent: result\r\ndata: '+json.dumps(fixture,ensure_ascii=False)+'\r\n\r\nevent: explanation\r\ndata: '+json.dumps({'text':'Évidence <safe>','source':'template'},ensure_ascii=False)
    page.evaluate('''async text=>{
      const bytes=new TextEncoder().encode(text);let index=0;
      const stream=new ReadableStream({pull(controller){if(index>=bytes.length){controller.close();return;}controller.enqueue(bytes.slice(index,index+3));index+=3;}});
      await consumeStream(new Response(stream,{headers:{'Content-Type':'text/event-stream'}}));
    }''',events)
    assert 'Zürich — <safe>' in page.locator('#results').inner_text()
    assert page.locator('#expl').inner_text()=='Évidence <safe>'
    page.evaluate('show({areas:[],low_confidence_for:[],radius:1200})')
    assert page.locator('#results-state').is_visible()
    assert 'No places' in page.locator('#results-state').inner_text()
    assert not errors,errors
    print('PASS: API contract, SSE chunks/Unicode, duplicate runs, filters, errors, empty/missing data, low confidence, raw why, drawer, untrusted text',flush=True)

    real=browser.new_page(viewport={'width':1440,'height':1000})
    real.on('pageerror',lambda e:errors.append(str(e)))
    real.route('http://culturefit.test/**',app_route)
    real.goto('http://culturefit.test/')
    real.wait_for_function('!busy')
    if not real.evaluate('typeof maplibregl!=="undefined"'):
        print('LIMITATION: CDN unavailable; real map rendering could not be checked',flush=True)
        browser.close()
        raise SystemExit(0)
    real.wait_for_function('ready && map.areTilesLoaded()',timeout=45000)
    assert real.locator('script[src*="maplibre-gl@4.7.1"]').count()==1
    assert real.evaluate('map.getStyle().sources.osm.tiles')==['https://tile.openstreetmap.org/{z}/{x}/{y}.png']
    assert real.evaluate('map.getPaintProperty("night-basemap","raster-saturation")')==-1
    assert real.evaluate('map.getPaintProperty("night-basemap","raster-brightness-min")')>real.evaluate('map.getPaintProperty("night-basemap","raster-brightness-max")')
    assert 'OpenStreetMap' in real.locator('.maplibregl-ctrl-attrib').inner_text()
    assert real.locator('#basemap-status,#basemap-dialog,#map-settings').count()==0
    print('PASS: real OpenStreetMap raster tiles loaded with dark styling and attribution; no extra key or setup needed',flush=True)
    real.screenshot(path=str(ROOT/'artifacts/night-desktop-empty.png'))
    real.evaluate('run()')
    real.wait_for_function('!busy')
    real.wait_for_function('map.getSource("areas") && map.getSource("areas")._data.features.length===7 && !map.isMoving() && map.areTilesLoaded()',timeout=45000)
    assert real.locator('.map-marker').count()==7
    assert 'Wheelchair accessible parking lot' not in real.locator('#results').inner_text()
    assert 'AGENT LIVE' in real.locator('.log-panel').inner_text()
    real.screenshot(path=str(ROOT/'artifacts/night-desktop-results.png'))
    real.locator('.map-marker').first.click()
    assert real.locator('#why-drawer').is_visible()
    assert 'Wheelchair accessible parking lot' not in real.locator('#diagram-scroll').inner_text()
    real.screenshot(path=str(ROOT/'artifacts/night-desktop-drawer.png'))
    real.keyboard.press('Escape')
    # Reduced motion reveals all polygons immediately and skips score count-up.
    real.emulate_media(reduced_motion='reduce')
    data=real.evaluate('lastResult')
    real.evaluate('(data)=>show(data)',data)
    assert real.evaluate('map.getSource("areas")._data.features.length')==7
    assert real.locator('.group-score>span').first.inner_text()==str(data['areas'][0]['group_fit'])
    real.set_viewport_size({'width':390,'height':844})
    real.locator('#tab-map').click()
    real.wait_for_function('!map.isMoving() && map.areTilesLoaded()',timeout=45000)
    assert real.locator('#preferences').is_hidden()
    assert real.locator('#results-panel').is_hidden()
    assert real.locator('#map').bounding_box()['height']==844
    real.screenshot(path=str(ROOT/'artifacts/night-mobile-map.png'))
    real.locator('#tab-results').click()
    assert real.locator('#results-panel').is_visible()
    assert real.locator('#preferences').is_hidden()
    real.screenshot(path=str(ROOT/'artifacts/night-mobile-results.png'))
    real.locator('.card-button').first.click()
    assert real.locator('#why-drawer').is_visible()
    real.screenshot(path=str(ROOT/'artifacts/night-mobile-drawer.png'))
    real.keyboard.press('Escape')
    real.locator('#tab-taste').click()
    assert real.locator('#preferences').is_visible()
    assert real.locator('#results-panel').is_hidden()
    real.screenshot(path=str(ROOT/'artifacts/night-mobile-taste.png'))
    for selector in ['#preferences','.sheet-nav','.log-panel']:
        box=real.locator(selector).bounding_box()
        assert box['x']>=0 and box['x']+box['width']<=391,(selector,box)
    assert not errors,errors
    print('PASS: full-screen map, 7 polygons/markers, map drawer, reduced motion, mobile taste/map/results sheets, no JS exceptions',flush=True)
    browser.close()
