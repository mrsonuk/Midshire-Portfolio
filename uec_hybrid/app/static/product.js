"use strict";
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const SVGNS="http://www.w3.org/2000/svg";
let SETUP=null, TOWER=null, fmRAF=null, curHour=12, loaded={}, SEL=null;

function rag(v,hi,a,b){return hi?(v>=a?'green':v>=b?'amber':'red'):(v<=a?'green':v<=b?'amber':'red');}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});if(!r.ok)throw new Error('server '+r.status);return r.json();}
const HH=h=>String(h).padStart(2,'0')+':00';

// ---- nav ----
$$('#nav a[data-tab]').forEach(a=>a.onclick=()=>{
 $$('#nav a').forEach(x=>x.classList.remove('active'));a.classList.add('active');
 $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-'+a.dataset.tab).classList.add('active');
 if(a.dataset.tab==='workforce'&&!loaded.wf)loadWorkforce();
 if(a.dataset.tab==='gaps'&&!loaded.gap)loadGaps();
});

// ---- init ----
// fill the Set-up fields + area toggles from a department object (reused when a
// trust is picked or a workbook is imported, so the form always reflects the data)
function applyDeptToUI(d){
 $('#dName').value=d.name;$('#dAttend').value=Math.round(d.attendances_per_day);
 $('#dBeds').value=d.inpatient_beds;$('#dComm').value=d.community_capacity;$('#coreNote').textContent=SETUP.core_note;
 const grid=$('#areaToggles');grid.innerHTML='';
 for(const[k,a] of Object.entries(SETUP.areas)){
  const on=(d.enabled||[]).includes(k);
  const hrs=(d.hours&&d.hours[k])||[0,24];
  const w=el('label','areatog');
  w.innerHTML=`<input type="checkbox" data-area="${k}" ${on?'checked':''}>
   <div><div style="font-weight:700">${a.label}</div><div class="x">${a.why}</div>
    <div class="x" style="margin-top:6px">Open
     <input type="number" data-hopen="${k}" value="${hrs[0]}" min="0" max="24" style="width:56px;padding:4px 6px;margin:0">
     to
     <input type="number" data-hclose="${k}" value="${hrs[1]}" min="0" max="24" style="width:56px;padding:4px 6px;margin:0"></div></div>`;
  grid.append(w);
 }
}
async function loadTrustPicker(){
 try{
  const {trusts}=await fetch('/api/trusts').then(r=>r.json());
  const sel=$('#trustPick');
  (trusts||[]).forEach(t=>{
   const bits=[];
   if(t.attendances_per_day)bits.push(Math.round(t.attendances_per_day)+'/day');
   if(t.observed_four_hour_pct)bits.push(t.observed_four_hour_pct+'% 4-hr');
   const o=el('option');o.value=t.ods_code;
   o.textContent=t.name+(bits.length?'  ('+bits.join(', ')+')':'');
   sel.append(o);
  });
 }catch(e){/* picker is optional; ignore */}
}
(async function init(){
 SETUP=await fetch('/api/setup').then(r=>r.json());
 applyDeptToUI(SETUP.department);
 loadTrustPicker();
 loadTower();
})();

// re-run everything after the department changes underneath us (trust / import)
function afterDeptChanged(dept){
 SETUP.department=dept;loaded={};applyDeptToUI(dept);
 $$('#nav a').forEach(x=>x.classList.remove('active'));$('#nav a[data-tab=tower]').classList.add('active');
 $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-tower').classList.add('active');
 loadTower();
}
// ---- ask a what-if ----
async function runAsk(){
 const q=($('#askQ').value||'').trim();
 if(!q){$('#askStatus').textContent='Type a change first.';return;}
 $('#askStatus').innerHTML='<span class="spin"></span> Simulating your what-if (scenario vs baseline)...';
 $('#askOut').style.display='none';
 try{
  const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({question:q})});
  const d=await r.json();
  if(!r.ok){
   $('#askStatus').textContent='';
   $('#askOut').style.display='block';
   $('#askOut').innerHTML='<div class="h">I didn\'t understand that</div><p>'+(d.error||'')+'</p>'+
    (d.supported?'<p class="hint">Try: '+d.supported.map(s=>'“'+s+'”').join(' · ')+'</p>':'');
   return;
  }
  $('#askStatus').textContent='';
  let rows='';
  for(const k in (d.deltas||{})){
   const x=d.deltas[k];
   const good=x.higher_better?x.delta>0:x.delta<0;
   const col=Math.abs(x.delta)<0.5?'var(--grey)':(good?'var(--green)':'var(--red)');
   rows+='<tr><td>'+x.label+'</td><td style="text-align:right">'+x.base.toFixed(1)+x.unit+
    '</td><td style="text-align:right">'+x.scenario.toFixed(1)+x.unit+
    '</td><td style="text-align:right;font-weight:800;color:'+col+'">'+(x.delta>0?'+':'')+x.delta.toFixed(1)+'</td></tr>';
  }
  $('#askOut').style.display='block';
  $('#askOut').innerHTML='<div class="h">What the model says'+(d.llm_used?' <span class="advis">AI-assisted wording</span>':'')+'</div>'+
   '<p>'+d.answer+'</p>'+
   '<table class="rota"><tr><th>Standard</th><th style="text-align:right">Now</th><th style="text-align:right">With change</th><th style="text-align:right">Δ points</th></tr>'+rows+'</table>'+
   '<p class="hint">Every number comes from the simulation (scenario vs baseline over paired simulated weeks). This is a what-if — it does not change your saved department.</p>';
 }catch(e){$('#askStatus').textContent='Error: '+e.message;}
}
$('#askBtn').onclick=runAsk;
$('#askQ').addEventListener('keydown',e=>{if(e.key==='Enter')runAsk();});

// ---- pick your trust ----
$('#useTrust').onclick=async()=>{
 const ods=$('#trustPick').value;
 if(!ods){$('#trustStatus').textContent='Choose a trust first.';return;}
 $('#trustStatus').innerHTML='<span class="spin"></span> Loading your trust and re-running...';
 $('#trustProv').textContent='';
 try{
  const r=await post('/api/trust/select',{ods});
  const filled=(r.provenance||[]).filter(p=>p.filled&&p.kind==='input').map(p=>p.field.replace(/_/g,' '));
  $('#trustStatus').textContent='Loaded '+r.department.name+'. Updated the control tower.';
  $('#trustProv').textContent=(filled.length?'From published data: '+filled.join(', ')+'. ':'')
   +(r.notes&&r.notes.length?r.notes[0]:'');
  afterDeptChanged(r.department);
 }catch(e){$('#trustStatus').textContent='Error: '+e.message;}
};
// ---- import a workbook ----
$('#importTrust').onclick=async()=>{
 const f=$('#trustFile').files[0];
 if(!f){$('#importStatus').textContent='Choose a file first.';return;}
 $('#importStatus').innerHTML='<span class="spin"></span> Importing and re-running...';
 try{
  const fd=new FormData();fd.append('file',f);
  const r=await fetch('/api/trust/import',{method:'POST',body:fd});
  const d=await r.json();
  if(!r.ok)throw new Error(d.error||('server '+r.status));
  $('#importStatus').textContent='Imported '+d.department.name+'. '+((d.summary||[]).slice(0,2).join(' '));
  afterDeptChanged(d.department);
 }catch(e){$('#importStatus').textContent='Error: '+e.message;}
};

// ---- control tower ----
async function loadTower(){
 $('#towerBody').innerHTML='<div class="loading"><span class="spin"></span> Running your department...</div>';
 try{TOWER=await post('/api/control-tower',{});SEL=null;renderTower(TOWER);}
 catch(e){$('#towerBody').innerHTML='<div class="card">Could not run: '+e.message+'</div>';}
}
function renderTower(d){
 const s=d.standards;
 const tiles=[
  std('4-hour standard',s.four_hour,true,78,72,'%','admitted, transferred or discharged in 4h'),
  std('Seen within 15 min',s.initial_assessment,true,90,80,'%','initial assessment at the front door'),
  std('Over 12 hours',s.twelve_hour,false,10,15,'%','waiting over 12 hours'),
  std('Ambulance handover',s.ambulance_handover,true,95,85,'%','handed over within 45 min'),
  std('Walked out unseen',s.lwbs,false,5,8,'%','left without being seen'),
 ].join('');
 const ph=d.bottleneck_peak_hours||[];
 const when=ph.length?`worst around ${HH(Math.min(...ph))}-${HH((Math.max(...ph)+1)%24)}`:'';
 $('#towerBody').innerHTML=`
  <div class="card"><h2>How your department is running</h2>
   <p class="sub">${Math.round(s.attendances_per_day)} attendances a day. Each dot shows a typical week on the good-to-tough range.</p>
   <div class="tiles">${tiles}</div></div>
  <div class="pinch"><div class="h">Your busiest pinch-point: ${strip(d.bottleneck)} ${when?'('+when+')':''}</div>
   <p>${d.headline_bottleneck||''}</p><p>${d.recommendation||''}</p>
   <button id="recBtn" class="sec" style="margin-top:10px">What should we change? Search staffing, capacity and hours</button>
   <div class="status" id="recStatus"></div><div id="recOut"></div></div>
  <div class="card"><h2>Live flow through your department</h2>
   <p class="sub">Each box is an area; the number is how many patients are in it right now (or
    how many left/arrived that hour for the outcome boxes on the right). Click any area
    for its full picture: waits, staffing, and where its patients come from and go to.
    <span class="legend"><i class="g"></i>flowing<i class="a"></i>busy<i class="r"></i>stuck</span></p>
   <div class="ctrl"><span class="when" id="whenLbl"></span>
    <input type="range" id="hour" min="0" max="23" value="12"><span class="census" id="censusLbl"></span>
    <span class="hint" id="hourPinch" style="margin-left:8px"></span></div>
   <div id="flow"></div><div class="drill" id="drill"></div></div>`;
 $('#hour').oninput=e=>{curHour=+e.target.value;updateHour();};
 renderFlow(d);curHour=12;updateHour();
 $('#recBtn').onclick=loadRecommendations;
}
async function loadRecommendations(){
 $('#recBtn').disabled=true;
 $('#recStatus').innerHTML='<span class="spin"></span> Simulating every candidate change against the same random weeks (a few minutes the first time)...';
 try{
  const d=await post('/api/recommend',{});
  $('#recStatus').textContent='';
  const rows=d.recommendations.map((r,i)=>`
   <div class="gap ${i===0?'have':'miss'}" style="border-left-color:${i===0?'var(--green)':'var(--aqua)'}">
    <div class="imp"><div class="d" style="color:var(--green)">+${r.delta_four_hour}</div><div class="r">pts on 4-hr</div></div>
    <div class="body"><div class="t">${r.title}</div>
     <div class="w">${r.summary}${r.delta_lwbs<-0.05?` Cuts walk-outs by ${Math.abs(r.delta_lwbs).toFixed(1)} points.`:''}</div>
     <div class="w" style="color:#003087;font-weight:600;margin-top:3px">
      ${r.weekly_cost?`About £${r.weekly_cost.toLocaleString()}/week to staff; `:''}~£${r.annual_benefit.toLocaleString()}/year benefit${r.net_annual!=null?` (net ~£${r.net_annual.toLocaleString()}/year)`:''}.</div></div>
    <div style="text-align:right">${r.cost_band?`<span class="pill ${r.cost_band}">${r.cost_band} cost</span>`:''}</div>
   </div>`).join('');
  $('#recOut').innerHTML=(rows||'<p class="sub" style="margin-top:10px">No change cleared the confidence bar at this demand: the simulation would rather say nothing than recommend noise.</p>')
   +(d.rejected.length?`<p class="hint">${d.rejected.length} other candidate${d.rejected.length===1?' was':'s were'} tried and rejected as within the noise.</p>`:'')
   +`<p class="hint">${d.note}</p>`;
 }catch(e){$('#recStatus').innerHTML='<span style="color:#DA291C">Could not search: '+e.message+'</span>';}
 $('#recBtn').disabled=false;
}
function std(k,b,hi,a,c,unit,sub){
 if(!b)return '';const cls=rag(b.typical,hi,a,c);
 const lo=Math.min(b.good,b.tough),hi2=Math.max(b.good,b.tough),span=Math.max(1,hi2-lo);
 const pos=Math.max(0,Math.min(100,100*(b.typical-lo)/span));
 return `<div class="tile ${cls}"><div class="k">${k}</div><div class="v">${b.typical}${unit}</div>
   <div class="range"><b style="left:0;width:100%;background:var(--line)"></b><i style="left:${pos}%"></i></div>
   <div class="s">tough week ${b.tough}${unit} &nbsp;to&nbsp; good week ${b.good}${unit}<br>${sub}</div></div>`;
}
function strip(t){return (t||'').replace(/<[^>]+>/g,'');}

let LINKS=[];
function renderFlow(data){
 if(fmRAF){cancelAnimationFrame(fmRAF);fmRAF=null;}
 const host=$('#flow');host.innerHTML='';
 const W=host.clientWidth||1000,H=460,px=n=>60+n.x*(W-120),py=n=>40+n.y*(H-80);
 const byId={};data.nodes.forEach(n=>byId[n.id]=n);
 const maxV=Math.max(...data.links.map(l=>l.value),1);
 const svg=document.createElementNS(SVGNS,'svg');svg.setAttribute('width',W);svg.setAttribute('height',H);
 svg.style.position='absolute';svg.style.left=0;svg.style.top=0;host.append(svg);
 LINKS=[];
 for(const l of data.links){const a=byId[l.source],b=byId[l.target];if(!a||!b)continue;
  const x1=px(a)+46,y1=py(a),x2=px(b)-46,y2=py(b),mx=(x1+x2)/2;
  const p=document.createElementNS(SVGNS,'path');
  p.setAttribute('d',`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
  p.setAttribute('fill','none');p.setAttribute('stroke','#cfd8dc');p.setAttribute('stroke-width',1+5*Math.sqrt(l.value/maxV));p.setAttribute('opacity',.7);svg.append(p);
  const nd=Math.max(1,Math.round(5*l.value/maxV)),dots=[];
  for(let i=0;i<nd;i++){const c=document.createElementNS(SVGNS,'circle');c.setAttribute('r',2.6);c.setAttribute('fill','#0072CE');svg.append(c);dots.push({el:c,ph:Math.random()});}
  LINKS.push({path:p,len:p.getTotalLength(),dots,sp:.09+.05*Math.random(),source:l.source,target:l.target,value:l.value});}
 for(const n of data.nodes){
  const kind=(n.kind==='source'||n.kind==='admitted'||n.kind==='discharged')?n.kind:n.status;
  const c=el('div','fmnode '+kind);
  c.style.left=px(n)+'px';c.style.top=py(n)+'px';c.dataset.label=n.label;c.dataset.id=n.id;
  c.dataset.kind=n.kind||'process';
  c.innerHTML=`<div class="nm">${n.label}</div>`+
    (n.caption?`<div class="cap">${n.caption}</div>`:'')+
    `<div class="vol" data-vol>${Math.round(n.volume).toLocaleString()}</div>`+
    (n.kind==='process'?`<div class="wt">wait ${Math.round(n.mean_wait)}m</div>`:'');
  c.onclick=()=>{SEL=n;markSelected();drill(n);};
  c.onmouseenter=()=>highlight(n.id,true);
  c.onmouseleave=()=>highlight(null,false);
  host.append(c);}
 let last=performance.now();
 (function f(now){const dt=(now-last)/1000;last=now;for(const L of LINKS)for(const d of L.dots){d.ph=(d.ph+dt*L.sp)%1;const p=L.path.getPointAtLength(d.ph*L.len);d.el.setAttribute('cx',p.x);d.el.setAttribute('cy',p.y);}fmRAF=requestAnimationFrame(f);})(last);
}
function highlight(id,on){
 for(const L of LINKS){
  const touch=on&&(L.source===id||L.target===id);
  L.path.setAttribute('stroke',touch?'#005EB8':'#cfd8dc');
  L.path.setAttribute('opacity',on?(touch?0.95:0.18):0.7);
 }
}
function markSelected(){
 $$('#flow .fmnode').forEach(nd=>nd.classList.toggle('selected',SEL&&nd.dataset.id===SEL.id));
}
function pinchAt(h){
 const ph=(TOWER.pinch_by_hour||[])[h];
 return ph||TOWER.bottleneck||null;
}
function applyPinch(h){
 const pinch=pinchAt(h);
 $$('#flow .fmnode').forEach(node=>{
  const on=pinch&&node.dataset.label===pinch;
  node.classList.toggle('bottleneck',!!on);
  let flag=node.querySelector('.flag');
  if(on&&!flag){
   flag=el('div','flag');flag.textContent='PINCH';node.append(flag);
  }else if(!on&&flag){flag.remove();}
 });
 for(const L of LINKS){
  const hot=pinch&&L.target===pinch;
  for(const d of L.dots){d.el.setAttribute('fill',hot?'#DA291C':'#0072CE');}
 }
 const hp=$('#hourPinch');
 if(hp){
  hp.textContent=pinch?`Pinch at ${HH(h)}: ${pinch}`:'';
 }
}
function hourlySeries(label){
 const by=(TOWER.area_by_hour||{})[label];
 if(by&&by.length) return {data:by, mode:'occupancy'};
 const ex=(TOWER.exits_by_hour||{})[label];
 if(ex&&ex.length) return {data:ex, mode:'exits'};
 if(label==='Arrival'&&(TOWER.arrivals_by_hour||[]).length){
  return {data:TOWER.arrivals_by_hour, mode:'arrivals'};
 }
 return {data:[], mode:null};
}
function hourStatLabel(mode,h){
 if(mode==='exits') return 'Left ED at '+HH(h);
 if(mode==='arrivals') return 'Arrivals at '+HH(h);
 return 'In area at '+HH(h);
}
function updateHour(){
 const H=curHour;$('#whenLbl').textContent='Your department at '+HH(H);
 const cen=(TOWER.census_by_hour||[])[H]||0;$('#censusLbl').textContent='about '+Math.round(cen)+' patients in the department';
 $$('#flow .fmnode').forEach(node=>{
  const lab=node.dataset.label;
  const series=hourlySeries(lab);
  const arr=series.data;
  if(!arr.length){return;}
  const now=arr[H], peak=Math.max(...arr,1);
  const v=node.querySelector('[data-vol]');if(v)v.textContent=Math.round(now).toLocaleString();
  if(node.classList.contains('source')||node.classList.contains('admitted')||node.classList.contains('discharged'))return;
  const r=now/peak;node.classList.remove('green','amber','red');
  node.classList.add(r>=0.8?'red':r>=0.45?'amber':'green');
 });
 applyPinch(H);
 if(SEL)drill(SEL);
}

// what serves an area, and who is on at the current hour
function servedBy(label){
 const res=(TOWER.area_resources||{})[label]||[];
 return res.map(r=>{
  const m=(TOWER.resource_meta||{})[r]||{};
  const cap=m.capacity;
  const capNow=Array.isArray(cap)?cap[curHour]:cap;
  if(m.staff){
   const roles=(m.roles||[]).join(', ');
   return `<span class="chip staff"><b>${m.label||r}</b>: ${capNow!=null?capNow+' on at '+HH(curHour):''}${roles?' ('+roles+')':''}</span>`;
  }
  // physical spaces can carry a 24-hour roster too (e.g. nurse-capped cubicles)
  return `<span class="chip"><b>${m.label||r}</b>${capNow!=null?': '+capNow+' space'+(capNow===1?'':'s')+(Array.isArray(cap)?' open at '+HH(curHour):''):''}</span>`;
 }).join('');
}
function flowsFor(id,dir){
 const arr=LINKS.filter(l=>dir==='in'?l.target===id:l.source===id)
   .sort((a,b)=>b.value-a.value).slice(0,4);
 const byId={};TOWER.nodes.forEach(n=>byId[n.id]=n);
 return arr.map(l=>{
  const other=byId[dir==='in'?l.source:l.target];
  return `<span class="chip"><b>${other?other.label:'?'}</b>: ${Math.round(l.value).toLocaleString()}/wk</span>`;
 }).join('')||'<span class="chip">none</span>';
}
function drill(n){
 const series=hourlySeries(n.label);
 const by=series.data;
 const now=by.length?Math.round(by[curHour]):null;
 const peak=by.length?by.indexOf(Math.max(...by)):null;
 const barHint=series.mode==='exits'?' departures':series.mode==='arrivals'?' arrivals':' in area';
 let bars='';
 if(by.length){const mx=Math.max(...by,1);bars='<div class="hours">'+by.map((v,h)=>
  `<div style="flex:1"><div class="b ${h===curHour?'now':''}" style="height:${Math.max(2,Math.round(80*v/mx))}px" title="${HH(h)}: ${Math.round(v)}${barHint}"></div><div class="lab">${h%6===0?h:''}</div></div>`).join('')+'</div>';}
 const stats=[
  now!=null&&series.mode?`<div class="dstat"><div class="k">${hourStatLabel(series.mode,curHour)}</div><div class="v">${now}</div></div>`:'',
  n.caption?`<div class="dstat"><div class="k">What this means</div><div class="v" style="font-size:13px;font-weight:600">${n.caption}</div></div>`:'',
  n.kind==='process'?`<div class="dstat"><div class="k">Average wait</div><div class="v">${Math.round(n.mean_wait)}<small> min</small></div></div>`:'',
  n.kind==='process'?`<div class="dstat"><div class="k">How busy</div><div class="v">${Math.round(n.utilisation)}<small>% of capacity</small></div></div>`:'',
  `<div class="dstat"><div class="k">Patients this week</div><div class="v">${Math.round(n.volume).toLocaleString()}</div></div>`,
  peak!=null?`<div class="dstat"><div class="k">Busiest hour</div><div class="v">${HH(peak)}</div></div>`:'',
 ].join('');
 const pinch=pinchAt(curHour);
 const served=servedBy(n.label);
 $('#drill').style.display='block';
 $('#drill').innerHTML=`
  <div class="dhead"><span class="t">${n.label}${pinch&&n.label===pinch?' &nbsp;<span class="pill High" style="background:var(--red)">PINCH at '+HH(curHour)+'</span>':''}</span>
   <button class="close" id="drillClose">Close</button></div>
  <div class="dstats">${stats}</div>
  ${by.length?'<div class="dsec">Through the day (dark bar = the hour on the slider)</div>'+bars:''}
  ${served?'<div class="dsec">Served by</div><div class="chips">'+served+'</div>':''}
  <div class="dsec">Patients arrive from</div><div class="chips">${flowsFor(n.id,'in')}</div>
  <div class="dsec">And go on to</div><div class="chips">${flowsFor(n.id,'out')}</div>`;
 $('#drillClose').onclick=()=>{SEL=null;markSelected();$('#drill').style.display='none';};
}

// ---- workforce ----
let ROTA=null;
function hourIn(sh,h){
 const s=sh.start%24,e=sh.end%24;
 if(sh.end===sh.start)return true;
 return e>s?(h>=s&&h<e):(h>=s||h<e);
}
async function loadWorkforce(){
 loaded.wf=true;
 ROTA=JSON.parse(JSON.stringify(SETUP.department.rota||[]));
 renderRota();
 $('#wfAreas').innerHTML='<div class="loading"><span class="spin"></span> Checking your rota against demand...</div>';
 refreshWorkforce();
}
async function refreshWorkforce(){
 try{const d=await post('/api/rota-preview',{rota:ROTA,attendances_per_day:SETUP.department.attendances_per_day});renderWorkforce(d);}
 catch(e){$('#wfAreas').innerHTML='Error: '+e.message;}
}
function roleOptions(sel){
 return Object.entries(SETUP.roles).map(([id,r])=>`<option value="${id}" ${id===sel?'selected':''}>${r.label}</option>`).join('');
}
function renderRota(){
 const rows=ROTA.map((sh,i)=>`<tr data-i="${i}">
   <td><select data-f="role">${roleOptions(sh.role)}</select></td>
   <td><input type="number" data-f="start" min="0" max="24" value="${sh.start}"></td>
   <td><input type="number" data-f="end" min="0" max="24" value="${sh.end}"></td>
   <td><input type="number" data-f="count" min="0" max="40" value="${sh.count}"></td>
   <td><button class="rm">Remove</button></td></tr>`).join('');
 $('#rotaTable').innerHTML=`<table class="rota"><thead><tr>
   <th>Role</th><th>Start</th><th>End</th><th>How many</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
 $$('#rotaTable [data-f]').forEach(inp=>inp.onchange=onRotaEdit);
 $$('#rotaTable .rm').forEach((b,i)=>b.onclick=()=>{ROTA.splice(i,1);renderRota();refreshWorkforce();});
}
function onRotaEdit(e){
 const i=+e.target.closest('tr').dataset.i, f=e.target.dataset.f, v=e.target.value;
 ROTA[i][f]=(f==='role')?v:Math.max(0,+v);
 refreshWorkforce();
}
let WF=null;
function wfChart(a,ai){
 // inline SVG: staffing bars + the demand shape behind + red understaffed hours
 const w=312,h=96,bw=10,gap=3,base=h-14;
 const smax=Math.max(...a.staffing,1),dmax=Math.max(...WF.demand,1);
 const dpts=WF.demand.map((d,i)=>`${i*(bw+gap)+bw/2},${base-70*d/dmax}`);
 const area=`M 0,${base} L ${dpts.join(' L ')} L ${23*(bw+gap)+bw/2},${base} Z`;
 const bars=a.staffing.map((s,i)=>{
  const bh=Math.max(2,70*s/smax), under=a.understaffed_hours.includes(i);
  return `<rect data-ai="${ai}" data-h="${i}" x="${i*(bw+gap)}" y="${base-bh}" width="${bw}" height="${bh}" rx="1.5"
    fill="${under?'#DA291C':'#0072CE'}" style="cursor:pointer"><title>${HH(i)}: ${s} on shift${under?' (light vs demand)':''}</title></rect>`;
 }).join('');
 const ticks=[0,6,12,18].map(t=>`<text x="${t*(bw+gap)+bw/2}" y="${h-2}" font-size="8" fill="#425563" text-anchor="middle">${HH(t)}</text>`).join('');
 return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
   <path d="${area}" fill="rgba(0,169,206,.16)" stroke="#00A9CE" stroke-width="1.2"/>
   ${bars}${ticks}</svg>`;
}
function renderWorkforce(d){
 WF=d;
 $('#wfHeadline').innerHTML=d.headline;
 $('#wfDrill').style.display='none';
 // summary tiles
 const underTotal=d.areas.reduce((t,a)=>t+a.understaffed_hours.length,0);
 const underAreas=d.areas.filter(a=>a.understaffed_hours.length).length;
 const totByHour=Array.from({length:24},(_,h)=>d.areas.reduce((t,a)=>t+a.staffing[h],0));
 const peakOn=Math.max(...totByHour), peakAt=totByHour.indexOf(peakOn);
 $('#wfTiles').innerHTML=
  `<div class="tile"><div class="k">Weekly pay-bill</div><div class="v">£${d.weekly_cost.toLocaleString()}</div><div class="s">all rostered roles</div></div>
   <div class="tile"><div class="k">A year</div><div class="v">£${(Math.round(d.weekly_cost*52/1e5)/10).toLocaleString()}m</div><div class="s">52 weeks at this rota</div></div>
   <div class="tile ${underTotal?'amber':'green'}"><div class="k">Light-staffed hours</div><div class="v">${underTotal}</div><div class="s">across ${underAreas} area${underAreas===1?'':'s'} today</div></div>
   <div class="tile"><div class="k">Most staff on</div><div class="v">${peakOn}</div><div class="s">at ${HH(peakAt)}</div></div>`;
 $('#wfAreas').innerHTML=d.areas.map((a,ai)=>{
  const win=a.understaffed_hours.length?`Light vs demand around ${HH(Math.min(...a.understaffed_hours))}-${HH((Math.max(...a.understaffed_hours)+1)%24)}.`:'Broadly matches demand.';
  const adv=a.advisory?` <span class="advis" title="Rostered and costed in the pay-bill; does not yet limit patient flow in the model">costed, not yet flow-limiting</span>`:'';
  return `<div class="wfarea"><div class="t">${a.label}${adv}</div>
    <div class="m">Peak ${a.peak}, overnight ${a.overnight}. ${win}</div>
    <div class="wfchart">${wfChart(a,ai)}</div></div>`;
 }).join('');
 $$('#wfAreas rect[data-ai]').forEach(r=>r.onclick=()=>wfDrill(+r.dataset.ai,+r.dataset.h));
 $('#wfCost').innerHTML=`Weekly cost by role at this rota. Every rate is an indicative planning figure and editable.`;
 const br=(d.cost_breakdown&&d.cost_breakdown.by_role)||{};
 const rows=Object.entries(br).sort((x,y)=>y[1]-x[1]);
 const mx=rows.length?rows[0][1]:1;
 $('#wfBreakdown').innerHTML=rows.map(([id,v])=>{
  const lbl=(SETUP.roles[id]||{}).label||id;
  return `<div class="row"><div class="lbl">${lbl}</div>
    <div class="track"><i style="width:${Math.max(2,Math.round(100*v/mx))}%"></i></div>
    <div class="amt">£${v.toLocaleString()}</div></div>`;
 }).join('');
}
function whoIsOn(a,h){
 // role-level headcount for this area at this hour, read from the live rota
 const counts={};
 for(const sh of ROTA){
  const role=SETUP.roles[sh.role];
  if(!role||role.staffs!==a.resource||!hourIn(sh,h))continue;
  const n=(sh.count==null||sh.count==='')?1:Math.max(0,+sh.count);
  if(n>0)counts[role.label]=(counts[role.label]||0)+n;
 }
 return Object.entries(counts).map(([l,c])=>`<span class="chip staff"><b>${c}</b> ${l}${c>1?'s':''}</span>`).join('')
  ||'<span class="chip">nobody rostered</span>';
}
function wfDrill(ai,h){
 const a=WF.areas[ai], on=a.staffing[h], dem=Math.round(WF.demand[h]);
 const dmax=Math.max(...WF.demand,1), share=Math.round(100*WF.demand[h]/dmax);
 const under=a.understaffed_hours.includes(h);
 const firstRole=a.roles&&a.roles.length?a.roles[a.roles.length-1].label:'staff member';
 $('#wfDrill').style.display='block';
 $('#wfDrill').innerHTML=`
  <div class="dhead"><span class="t">${a.label}, ${HH(h)} to ${HH((h+1)%24)}</span>
   <button class="close" id="wfClose">Close</button></div>
  <div class="dstats">
   <div class="dstat"><div class="k">On shift</div><div class="v">${on}</div></div>
   <div class="dstat"><div class="k">Arrivals this hour</div><div class="v">${dem}</div></div>
   <div class="dstat"><div class="k">Vs daily peak</div><div class="v">${share}<small>%</small></div></div>
  </div>
  <div class="dsec">Who is on</div><div class="chips">${whoIsOn(a,h)}</div>
  <div style="margin-top:10px">${under
    ?`<span style="color:var(--red);font-weight:700">Staffing looks light against demand this hour, the most likely time to fall behind.</span>
      <div class="hint">Try adding a ${firstRole} shift covering ${HH(Math.max(0,h-1))} to ${HH((h+3)%24)} in the rota below; the charts and pay-bill update instantly.</div>`
    :`Staffing broadly matches demand this hour.`}</div>`;
 $('#wfClose').onclick=()=>$('#wfDrill').style.display='none';
 $('#wfDrill').scrollIntoView({behavior:'smooth',block:'nearest'});
}

// ---- gaps ----
async function loadGaps(){
 loaded.gap=true;$('#gapMiss').innerHTML='<div class="loading"><span class="spin"></span> Comparing against the Model ED...</div>';
 try{const d=await post('/api/gap',{});renderGaps(d);}catch(e){$('#gapMiss').innerHTML='Error: '+e.message;}
}
function renderGaps(d){
 $('#gapSummary').innerHTML=`You have <b>${d.have} of ${d.total}</b> Model ED elements. Current 4-hour performance about <b>${d.baseline_four_hour}%</b>, with about <b>${d.baseline_admit}%</b> of attendances admitted.`;
 $('#gapHave').innerHTML=d.present.map(p=>`<div class="gap have"><div class="imp"><span class="badge">IN PLACE</span></div><div class="body"><div class="t">${p.label}</div><div class="w">${p.why}</div></div></div>`).join('')||'<p class="sub">No Model ED elements enabled yet.</p>';
 $('#gapMiss').innerHTML=d.missing.length?d.missing.map(m=>{
   const sign=(typeof m.value==='number'&&m.unit.includes('4-hr')&&m.value>=0)?'+':'';
   return `<div class="gap miss">
   <div class="imp"><div class="d">${sign}${Math.round(m.value)}</div><div class="r">${m.unit}</div></div>
   <div class="body"><div class="t">${m.label}</div><div class="w">${m.benefit}</div>${m.finance&&m.finance.annual_benefit>0?`<div class="w" style="color:#003087;font-weight:600;margin-top:4px">${m.finance.summary}</div>`:''}</div>
   <div style="text-align:right"><span class="pill ${m.cost}">${m.cost} cost</span></div></div>`;}).join(''):'<p class="sub">You have every Model ED element in place.</p>';
}

// ---- rota editor buttons ----
$('#addShift').onclick=()=>{
 if(!ROTA)ROTA=[];
 ROTA.push({role:Object.keys(SETUP.roles)[0],start:8,end:20,count:1});
 renderRota();refreshWorkforce();
};
$('#applyRota').onclick=async()=>{
 const dept={...SETUP.department,rota:ROTA};
 $('#rotaStatus').innerHTML='<span class="spin"></span> Applying and re-running...';
 try{await post('/api/department',dept);SETUP.department=dept;loaded={};
  $('#rotaStatus').textContent='Applied. Updated the control tower.';
  $$('#nav a').forEach(x=>x.classList.remove('active'));$('#nav a[data-tab=tower]').classList.add('active');
  $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-tower').classList.add('active');
  loadTower();
 }catch(e){$('#rotaStatus').textContent='Error: '+e.message;}
};

// ---- setup save ----
$('#saveDept').onclick=async()=>{
 const enabled=[...$$('#areaToggles input[type=checkbox]:checked')].map(i=>i.dataset.area);
 const hours={...(SETUP.department.hours||{})};
 $$('#areaToggles [data-hopen]').forEach(inp=>{
  const k=inp.dataset.hopen, c=$(`#areaToggles [data-hclose="${k}"]`);
  hours[k]=[Math.max(0,Math.min(24,+inp.value)),Math.max(0,Math.min(24,+c.value))];
 });
 const dept={...SETUP.department,name:$('#dName').value,attendances_per_day:+$('#dAttend').value,
   inpatient_beds:+$('#dBeds').value,community_capacity:+$('#dComm').value,enabled,hours};
 $('#setupStatus').innerHTML='<span class="spin"></span> Saving and re-running...';
 try{await post('/api/department',dept);SETUP.department=dept;loaded={};
  $('#setupStatus').textContent='Saved. Updated the control tower.';
  $$('#nav a').forEach(x=>x.classList.remove('active'));$('#nav a[data-tab=tower]').classList.add('active');
  $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-tower').classList.add('active');
  loadTower();
 }catch(e){$('#setupStatus').textContent='Error: '+e.message;}
};
