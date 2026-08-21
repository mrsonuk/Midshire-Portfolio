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
// ---- data provenance banner: shared renderer in provenance.js ----
async function loadDataStatus(){
 if(window.renderDataStatus)return renderDataStatus();
}

// ---- decision log (append-only) ----
async function loadActions(){
 try{
  const {actions}=await fetch('/api/actions').then(r=>r.json());
  const box=$('#actList');if(!box)return;box.innerHTML='';
  if(!(actions||[]).length){box.innerHTML='<p class="sub">No decisions recorded yet.</p>';return;}
  actions.forEach(a=>{
   const row=el('div','pinch');row.style.marginTop='6px';
   row.innerHTML='<b>'+a.at.slice(0,16).replace('T',' ')+'</b>'
    +(a.author?' - '+a.author:'')+'<br>'+a.note
    +'<span class="sub" style="display:block">model v'+(((a.context||{}).department||{}).version||'?')
    +' · '+((((a.context||{}).source)||{}).label||'demo data')+'</span>';
   box.append(row);
  });
 }catch(e){/* optional */}
}
async function addAction(){
 const note=($('#actNote').value||'').trim();
 if(!note){$('#actStatus').textContent='Type the decision first.';return;}
 $('#actStatus').textContent='Saving…';
 const r=await fetch('/api/actions',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({note,author:($('#actAuthor').value||'').trim()})});
 if(r.ok){$('#actNote').value='';$('#actStatus').textContent='Recorded (entries cannot be edited or deleted).';loadActions();}
 else{$('#actStatus').textContent='Could not save the decision.';}
}

(async function init(){
 SETUP=await fetch('/api/setup').then(r=>r.json());
 applyDeptToUI(SETUP.department);
 loadTrustPicker();
 loadTower();
 loadDataStatus();
 loadActions();
 const ab=$('#actAdd');if(ab)ab.onclick=addAction;
})();

// re-run everything after the department changes underneath us (trust / import)
function afterDeptChanged(dept){
 SETUP.department=dept;loaded={};applyDeptToUI(dept);
 $$('#nav a').forEach(x=>x.classList.remove('active'));$('#nav a[data-tab=tower]').classList.add('active');
 $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-tower').classList.add('active');
 loadTower();
 loadDataStatus();
}
// ---- chatbot ----
const CHAT={hist:[],busy:false};
function chatAdd(role,text,tag){
 const m=el('div','cmsg '+role,'');m.textContent=text;
 if(tag&&role==='bot'){const t=el('span','tag',tag);m.appendChild(document.createElement('br'));m.appendChild(t);}
 $('#chatMsgs').append(m);$('#chatMsgs').scrollTop=$('#chatMsgs').scrollHeight;
 return m;
}
async function chatSend(){
 if(CHAT.busy)return;
 const q=($('#chatIn').value||'').trim();
 if(!q)return;
 $('#chatIn').value='';chatAdd('user',q);
 CHAT.busy=true;
 const wait=chatAdd('bot','Checking your model…');
 try{
  const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({message:q,history:CHAT.hist})});
  const d=await r.json();
  wait.textContent=d.reply||'Sorry - something went wrong.';
  if(d.intent&&d.intent!=='help'){
   const t=el('span','tag',d.intent.replace(/_/g,' ')+(d.llm_used?' · AI wording':''));
   wait.appendChild(document.createElement('br'));wait.appendChild(t);
  }
  CHAT.hist.push({role:'user',content:q},{role:'assistant',content:d.reply||''});
  if(CHAT.hist.length>16)CHAT.hist=CHAT.hist.slice(-16);
 }catch(e){wait.textContent='Error: '+e.message;}
 CHAT.busy=false;$('#chatIn').focus();
}
$('#chatFab').onclick=()=>{
 const p=$('#chatPanel');p.classList.toggle('open');
 if(p.classList.contains('open')){
  if(!$(‘#chatMsgs’).children.length)
   chatAdd(‘bot’,’Hello - ask me anything about your department. Try “where is demand?”, “where should I deploy staff?”, “what’s the pinch point?”, or “what if we add 3 nurses at 1pm?”’);
  $(‘#chatIn’).focus();
 }
};
$('#chatClose').onclick=()=>$('#chatPanel').classList.remove('open');
$('#chatSend').onclick=chatSend;
$('#chatIn').addEventListener('keydown',e=>{if(e.key==='Enter')chatSend();});

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
  if(d.kind==='target'){
   $('#askStatus').textContent='';
   let steps='';
   (d.steps||[]).forEach((s,i)=>{
    const cost=s.weekly_cost?(' · ~£'+s.weekly_cost.toLocaleString()+'/wk'):(s.cost_band?(' · '+s.cost_band+' cost'):'');
    steps+='<tr><td>'+(i+1)+'. '+s.title+'</td><td style="text-align:right">+'+s.delta_four_hour+' pts'+cost+'</td>'+
     '<td style="text-align:right;font-weight:700">'+s.cumulative_four_hour+'%</td></tr>';
   });
   $('#askOut').style.display='block';
   $('#askOut').innerHTML='<div class="h">'+(d.reached?'Reaching ':'Toward ')+d.target+'% in 4 hours (from '+d.baseline+'%)</div>'+
    (steps?'<table style="width:100%;font-size:13px;margin:8px 0"><tr><th style="text-align:left">Change (stacked in order)</th>'+
     '<th style="text-align:right">Effect</th><th style="text-align:right">Running 4-hour</th></tr>'+steps+'</table>':'')+
    '<p>'+(d.note||'')+'</p>';
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
   '<p class="hint">Every number comes from the simulation (scenario vs baseline over paired simulated weeks). This is a what-if - it does not change your saved department.</p>';
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
 const recsHTML=(d.recommendations||[]).length?'<div style="margin-top:10px"><b style="font-size:13px">What should change:</b>'+
  d.recommendations.map(r=>{
   const rejected=r.rejected||false;
   const borderColor=rejected?'#cbd5e0':'var(--aqua)';
   const bgColor=rejected?'#f7fafc':'#f0f9ff';
   const rejectedBadge=rejected?'<span style="display:inline-block;margin-left:6px;font-size:10px;font-weight:600;color:#718096;background:#e2e8f0;padding:2px 6px;border-radius:3px">INCONCLUSIVE</span>':'';
   return '<div style="margin:6px 0;padding:8px 10px;background:'+bgColor+';border-left:3px solid '+borderColor+';border-radius:6px'+(rejected?';opacity:0.85':'')+'>'+
    '<div style="font-weight:700;font-size:12.5px">'+r.title+rejectedBadge+'</div>'+
    '<div style="font-size:12px;color:var(--grey);margin-top:2px">'+r.summary+'</div>'+
    (r.weekly_cost?'<div style="font-size:11px;color:var(--grey);margin-top:2px">~£'+r.weekly_cost.toLocaleString()+'/week</div>':'')
   +'</div>';
  }).join('')+'</div>':'<p style="font-size:12.5px;color:var(--grey);margin-top:8px">'+
   (d.recommendation_note||'No statistically confident improvements found in the standard search.')+'</p>';
 $('#towerBody').innerHTML=`
  <div class="card"><h2>How your department is running</h2>
   <p class="sub">${Math.round(s.attendances_per_day)} attendances a day. Each dot shows a typical week on the good-to-tough range.</p>
   <div class="tiles">${tiles}</div></div>
  <div class="pinch"><div class="h">Your busiest pinch-point: ${strip(d.bottleneck)} ${when?'('+when+')':''}</div>
   <p>${d.headline_bottleneck||''}</p>
   ${d.diagnostic?'<p style="font-size:12.5px;color:var(--grey)">'+d.diagnostic+'</p>':''}
   ${recsHTML}
   <button id="recBtn" class="sec" style="margin-top:10px">Search all staffing, capacity and hours changes</button>
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
 // the caption reads "tough week ... to good week ...", so the dot must sit on
 // a tough(left)-to-good(right) axis whichever direction the metric runs -
 // for lower-is-better tiles (12-hour waits, walk-outs) good is the SMALLER
 // number and a raw low-to-high scale would render the dot inverted
 const span=b.good-b.tough;
 const pos=Math.abs(span)<1e-9?50:Math.max(0,Math.min(100,100*(b.typical-b.tough)/span));
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
  if(n.severe_wait){
   c.classList.add('severe');
   c.style.animation='pulse 1.6s infinite';
  }
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
  // the wait caption follows the slider: mean queue wait for patients arriving
  // into this area at hour H (whole-week mean stays the fallback)
  const wbh=(TOWER.waits_by_hour||{})[lab];
  const wEl=node.querySelector('.wt');
  if(wEl&&wbh&&wbh.length)wEl.textContent='wait '+Math.round(wbh[H])+'m at '+HH(H);
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
// ---- gaps ----
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
