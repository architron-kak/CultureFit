const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const fav = text => text.split(',').map(item => item.trim()).filter(Boolean);
const cityViews = {Zurich: {center:[8.54,47.377],zoom:11.8}, Almaty:{center:[76.934,43.25],zoom:11.5}};
const initialExplanation = 'The places we find tell a story. Your explanation will connect your tastes to the neighborhoods that bring them together.';
let st = {exclude:[],avoid:[]}, map, ready = false, busy = false, lastResult = null, markers = [], hadError = false;

function setBusy(value) {
  busy = value;
  document.body.classList.toggle('loading', value);
  document.querySelectorAll('.sidebar button,.sidebar input,.sidebar textarea,.sidebar select').forEach(el => el.disabled = value);
  $('#search-label').textContent = value ? 'Connecting the dots…' : 'Find our neighborhood';
  $('#results').setAttribute('aria-busy', String(value));
  $('#journey-status').textContent = value ? 'Exploring' : hadError ? 'Try again' : lastResult ? 'Complete' : 'Standby';
}
function report(error) {
  hadError = true;
  $('#trace').insertAdjacentHTML('beforeend', `<li class="warn">${esc(error.message || error)}</li>`);
  $('#trace-details').open = true;
  $('#progress-label').textContent = 'Something needs another look';
  if (!lastResult) { $('#empty-state').hidden = false; $('#empty-state h3').textContent = 'Let’s try that again.'; }
}
async function checked(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = typeof data.detail === 'string' ? data.detail : (data.detail || []).map(item => item.msg).join('; ') || message;
    } catch {}
    throw new Error(message);
  }
  return response;
}
function updateCounts() {
  ['f1','f2'].forEach((id,index) => {
    const count = fav($('#'+id).value).length;
    $('#count'+(index+1)).textContent = `${count} / 6`;
    $('#count'+(index+1)).classList.toggle('is-over', count > 6);
  });
}
function showMapFallback() {
  $('#map').textContent = 'Map unavailable. You can still compare neighborhoods below.';
  $('#map-fallback').hidden = false;
}
async function init() {
  const cities = await (await checked('/api/cities')).json();
  $('#city').innerHTML = Object.keys(cities).map(city => `<option>${esc(city)}</option>`).join('');
  $('#coverage').textContent = `${Object.keys(cities).length} cities. ${Object.values(cities).reduce((sum,areas) => sum+areas.length,0)} neighborhoods. Your next chapter.`;
  updateCity();
  if (typeof maplibregl === 'undefined') { showMapFallback(); return; }
  try {
    const view = cityViews[$('#city').value] || cityViews.Zurich;
    map = new maplibregl.Map({
      container:'map', ...view, attributionControl:true,
      style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},
        layers:[{id:'base',type:'raster',source:'osm',paint:{'raster-saturation':-.85,'raster-contrast':-.05,'raster-opacity':.85}}]}
    });
    map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right');
    map.on('load', () => { ready = true; if (lastResult) draw(lastResult); });
  } catch { map = null; showMapFallback(); }
}
function clearMap() {
  markers.forEach(marker => marker.remove()); markers = [];
  if (ready && map?.getSource('a')) map.getSource('a').setData({type:'FeatureCollection',features:[]});
}
function circle(lat, lon, radius) {
  const points = [];
  for (let i=0;i<=64;i++) {
    const angle = i/64*2*Math.PI;
    points.push([lon+radius*Math.cos(angle)/(111320*Math.cos(lat*Math.PI/180)),lat+radius*Math.sin(angle)/110540]);
  }
  return [points];
}
function focusArea(index) {
  const area = lastResult?.areas[index];
  if (!area) return;
  document.querySelectorAll('.result-card').forEach(card => card.classList.remove('area-selected'));
  const card = $('#area-'+index);
  card?.classList.add('area-selected');
  card?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'nearest'});
  if (map) map.flyTo({center:[area.lon,area.lat],zoom:13,duration:650});
}
function draw(data) {
  if (!map || !ready) return;
  clearMap();
  const collection = {type:'FeatureCollection',features:data.areas.map(area => ({type:'Feature',properties:{fit:area.group_fit??0,area:area.area,missing:area.group_fit===null},geometry:{type:'Polygon',coordinates:circle(area.lat,area.lon,data.radius)}}))};
  if (map.getSource('a')) map.getSource('a').setData(collection);
  else {
    map.addSource('a',{type:'geojson',data:collection});
    map.addLayer({id:'f',type:'fill',source:'a',paint:{'fill-opacity':.18,'fill-color':['interpolate',['linear'],['get','fit'],0,'#d1c8df',100,'#7956d9']}});
    map.addLayer({id:'l',type:'line',source:'a',paint:{'line-color':'#a18aba','line-width':1,'line-opacity':.65}});
    map.on('click','f',event => {
      const properties = event.features[0].properties;
      new maplibregl.Popup().setLngLat(event.lngLat).setText(`${properties.area}: ${properties.missing?'insufficient data':properties.fit}`).addTo(map);
    });
    map.on('mouseenter','f',() => map.getCanvas().style.cursor='pointer');
    map.on('mouseleave','f',() => map.getCanvas().style.cursor='');
  }
  data.areas.forEach((area,index) => {
    const button = document.createElement('button');
    button.className = 'map-pin'+(index===0 && area.group_fit!==null?' top-pin':'');
    button.textContent = area.group_fit??'—';
    button.setAttribute('aria-label',`${area.area}: ${area.group_fit??'insufficient data'}. View neighborhood`);
    button.addEventListener('click',() => focusArea(index));
    markers.push(new maplibregl.Marker({element:button}).setLngLat([area.lon,area.lat]).addTo(map));
  });
  const bounds = new maplibregl.LngLatBounds();
  data.areas.forEach(area => bounds.extend([area.lon,area.lat]));
  if (data.areas.length) map.fitBounds(bounds,{padding:60,maxZoom:13,duration:800});
}
function resultCard(area,index) {
  const top = index===0 && area.group_fit!==null;
  const scores = Object.entries(area.scores).map(([person,score],personIndex) => `<div class="person-score ${personIndex?'partner':''}"><div class="person-score-heading"><span><i></i>${esc(person)}</span><b>${score??'—'}</b></div><div class="bar"><i style="width:${score??0}%"></i></div><p class="gives-up">${score===null?'Insufficient data':`${area.gives_up[person]} points below your best area`}</p></div>`).join('');
  const venues = Object.entries(area.evidence).map(([person,entries]) => `<div class="venue-section"><h4 class="venue-heading">PLACES FOR ${esc(person.toUpperCase())}</h4><ul class="venue-list">${entries.map(entry=>`<li><div>${esc(entry.name)}<span class="venue-tags">${entry.tags.map(esc).join(' · ')}</span></div><span class="venue-affinity" title="Qloo affinity">${esc(entry.affinity)}</span></li>`).join('')||'<li class="venue-empty">No strong venues found for these preferences.</li>'}</ul></div>`).join('');
  return `<article class="result-card ${top?'is-top':''}" id="area-${index}" style="animation-delay:${Math.min(index*40,240)}ms"><div class="result-topline"><span class="rank-index">${String(index+1).padStart(2,'0')}</span><span class="match-badge">${top?'YOUR COMMON GROUND':area.group_fit===null?'MORE DATA NEEDED':'ANOTHER PERSPECTIVE'}</span><button class="area-link" type="button" data-area="${index}" aria-label="Show ${esc(area.area)} on map">↗</button></div><div class="result-title-row"><div><h3>${esc(area.area)}</h3><p class="result-subtitle">${esc($('#city').value)} <span aria-hidden="true">·</span> ${lastResult.radius/1000} km search radius</p></div>${area.group_fit===null?'<div class="group-score no-data">Insufficient data</div>':`<div class="group-score"><strong>${area.group_fit}</strong><small>GROUP<br>FIT</small></div>`}</div><div class="people-scores">${scores}</div>${venues}<div class="card-footer"><span>BUILT AROUND YOUR TASTE</span><span class="compromise">${area.weakest_person?'Compromise: '+esc(area.weakest_person):'More venues needed'}</span></div></article>`;
}
function show(data) {
  lastResult = data;
  $('#empty-state').hidden = true;
  $('#score-note').hidden = false;
  $('#result-count').textContent = `${data.areas.length} neighborhoods`;
  $('#map-caption').textContent = 'Your neighborhoods, mapped';
  $('#results').innerHTML = (data.low_confidence_for.length?`<div class="notice">Differences between areas are small for ${esc(data.low_confidence_for.join(', '))}. Explore the places behind the scores.</div>`:'')+
    (data.insufficient_data_for?.length?`<div class="notice">Insufficient venue data for ${esc(data.insufficient_data_for.join(', '))} in some areas. Those neighborhoods appear last.</div>`:'')+
    data.areas.map(resultCard).join('');
  if (ready) draw(data);
}
function handle(block) {
  const lines = block.split(/\r?\n/), event = lines.find(line => line.startsWith('event:'));
  const payload = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
  if (!payload) return;
  const type = event?event.slice(6).trim():'message', data = JSON.parse(payload);
  if (type==='step') {
    $('#trace').insertAdjacentHTML('beforeend',`<li>${esc(data.text)}</li>`);
    $('#trace').scrollTop = $('#trace').scrollHeight;
    $('#progress-label').textContent = data.text==='writing the explanation'?'Putting the story together':'Exploring your possibilities';
  } else if (type==='error') throw new Error(data.message);
  else if (type==='result') show(data);
  else if (type==='explanation') {
    $('#expl').textContent = data.text;
    $('.insight-panel').classList.add('has-explanation');
    const source = {gemini:'Gemini',openrouter:'AI',template:'Place notes'}[data.source] || 'Place notes';
    $('#explanation-source').textContent = source;
    $('#explanation-source').hidden = false;
    $('#progress-label').textContent = 'Your neighborhood story is ready';
  }
}
function resetResults() {
  lastResult = null;
  clearMap();
  $('#results').innerHTML = '';
  $('#trace').innerHTML = '';
  $('#expl').textContent = '';
  $('#explanation-source').hidden = true;
  $('.insight-panel').classList.remove('has-explanation');
  $('#score-note').hidden = true;
  $('#result-count').textContent = 'Ready when you are';
}
async function performRun() {
  const people = [{name:'You',favorites:fav($('#f1').value)}];
  if ($('#f2').value.trim()) people.push({name:'Partner',favorites:fav($('#f2').value)});
  if (!people[0].favorites.length) throw new Error('Add some favorites first');
  if (people.some(person => person.favorites.length>6)) throw new Error('Use at most 6 favorites per person');
  resetResults();
  $('#empty-state').hidden = true;
  $('#cons').textContent = st.exclude.length||st.avoid.length?`Leaving out: ${st.exclude.join(', ')||'no venue filters'}. Skipping: ${st.avoid.join(', ')||'no areas'}.`:'';
  $('#expl').textContent = 'Finding the places that connect you. Your explanation will appear here.';
  const response = await checked('/api/rank',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({city:$('#city').value,people,exclude:st.exclude,avoid_areas:st.avoid})});
  if (!response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('Unexpected server response');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const {done,value} = await reader.read();
      if (done) { buffer += decoder.decode(); if (buffer.trim()) handle(buffer); break; }
      buffer += decoder.decode(value,{stream:true});
      let match;
      while ((match=/\r?\n\r?\n/.exec(buffer))) { handle(buffer.slice(0,match.index)); buffer=buffer.slice(match.index+match[0].length); }
    }
    if (!lastResult) throw new Error('The search ended before results arrived. Please try again.');
  } finally { await reader.cancel(); reader.releaseLock(); }
}
async function run() {
  if (busy) return;
  hadError = false; setBusy(true);
  try { await performRun(); } catch(error) { report(error); } finally { setBusy(false); }
}
async function refine() {
  if (busy) return;
  const text = $('#ref').value.trim(); if (!text) { $('#ref').focus(); return; }
  hadError = false; setBusy(true);
  try {
    const data = await (await checked('/api/refine',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({city:$('#city').value,text})})).json();
    st.exclude = [...new Set([...st.exclude,...data.exclude])];
    st.avoid = [...new Set([...st.avoid,...data.avoid_areas])];
    await performRun();
    $('#trace').insertAdjacentHTML('afterbegin',`<li>${esc(data.message)}</li>`);
  } catch(error) { report(error); } finally { setBusy(false); }
}
function reset() { if (busy) return; st={exclude:[],avoid:[]}; $('#ref').value=''; run(); }
function updateCity() {
  $('#map-city').textContent = $('#city').value;
  $('#map-caption').textContent = 'A new point of view';
  if (map && cityViews[$('#city').value]) map.flyTo({...cityViews[$('#city').value],duration:700});
}
$('#city').addEventListener('change',() => {
  st={exclude:[],avoid:[]}; hadError=false; $('#cons').textContent=''; $('#ref').value=''; resetResults(); updateCity();
  $('#expl').textContent=initialExplanation; $('#empty-state').hidden=false; $('#empty-state h3').textContent='Your next chapter starts here.';
  $('#progress-label').textContent='Follow the search'; $('#journey-status').textContent='Standby';
});
$('#results').addEventListener('click', event => { const button=event.target.closest('[data-area]'); if(button)focusArea(Number(button.dataset.area)); });
['f1','f2'].forEach(id => $('#'+id).addEventListener('input',updateCounts));
$('#ref').addEventListener('keydown', event => { if(event.key==='Enter'){event.preventDefault();refine();} });
updateCounts(); setBusy(true); init().catch(report).finally(() => setBusy(false));
