"use strict";
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const SVGNS="http://www.w3.org/2000/svg";
let SETUP=null, TOWER=null, fmRAF=null, curHour=12, loaded={};

function rag(v,hi,a,b){return hi?(v>=a?'green':v>=b?'amber':'red'):(v<=a?'green':v<=b?'amber':'red');}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});if(!r.ok)throw new Error('server '+r.status);return r.json();}

// ---- nav ----
$$('#nav a[data-tab]').forEach(a=>a.onclick=()=>{
 $$('#nav a').forEach(x=>x.classList.remove('active'));a.classList.add('active');
 $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-'+a.dataset.tab).classList.add('active');
 if(a.dataset.tab==='workforce'&&!loaded.wf)loadWorkforce();
 if(a.dataset.tab==='gaps'&&!loaded.gap)loadGaps();
});

// ---- init ----
(async function init(){
 SETUP=await fetch('/api/setup').then(r=>r.json());
 const d=SETUP.department;
 $('#dName').value=d.name;$('#dAttend').value=Math.round(d.attendances_per_day);
 $('#dBeds').value=d.inpatient_beds;$('#dComm').value=d.community_capacity;$('#coreNote').textContent=SETUP.core_note;
 const grid=$('#areaToggles');grid.innerHTML='';
 for(const[k,a] of Object.entries(SETUP.areas)){
  const on=d.enabled.includes(k);
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
 loadTower();
})();

// ---- control tower ----
async function loadTower(){
 $('#towerBody').innerHTML='<div class="loading"><span class="spin"></span> Running your department…</div>';
 try{TOWER=await post('/api/control-tower',{});renderTower(TOWER);}
 catch(e){$('#towerBody').innerHTML='<div class="card">Could not run: '+e.message+'</div>';}
}
function renderTower(d){
 const s=d.standards;
 const tiles=[
  std('4-hour standard',s.four_hour,true,78,72,'%','admitted, transferred or discharged in 4h'),
  std('Seen within 15 min',s.initial_assessment,true,90,80,'%','initial assessment at the front door'),
  std('Over 12 hours',s.twelve_hour,false,10,15,'%','waiting over 12 hours'),
  std('Ambulance handover',s.ambulance_handover,true,95,85,'%','handed over within 45 min'),
 ].join('');
 const ph=d.bottleneck_peak_hours||[];
 const when=ph.length?`worst around ${String(Math.min(...ph)).padStart(2,'0')}:00–${String((Math.max(...ph)+1)%24).padStart(2,'0')}:00`:'';
 $('#towerBody').innerHTML=`
  <div class="card"><h2>How your department is running</h2>
   <p class="sub">${Math.round(s.attendances_per_day)} attendances a day. Figures shown as a typical week, with the good and tough weeks in brackets.</p>
   <div class="tiles">${tiles}</div></div>
  <div class="pinch"><div class="h">Your busiest pinch-point: ${strip(d.bottleneck)} ${when?'('+when+')':''}</div>
   <p>${d.headline_bottleneck||''}</p><p>${d.recommendation||''}</p></div>
  <div class="card"><h2>Live flow through your department</h2>
   <p class="sub">Each box is an area; the number is how many patients are in it. The pinch-point pulses red.
    <span class="legend"><i class="g"></i>flowing<i class="a"></i>busy<i class="r"></i>stuck</span></p>
   <div class="ctrl"><span class="when" id="whenLbl"></span>
    <input type="range" id="hour" min="0" max="23" value="12"><span class="census" id="censusLbl"></span></div>
   <div id="flow"></div><div class="drill" id="drill"></div></div>`;
 $('#hour').oninput=e=>{curHour=+e.target.value;updateHour();};
 renderFlow(d);curHour=12;updateHour();
}
function std(k,b,hi,a,c,unit,sub){
 if(!b)return '';const cls=rag(b.typical,hi,a,c);
 return `<div class="tile ${cls}"><div class="k">${k}</div><div class="v">${b.typical}${unit}</div>
   <div class="s">good ${b.good}${unit} · tough ${b.tough}${unit}<br>${sub}</div></div>`;
}
function strip(t){return (t||'').replace(/<[^>]+>/g,'');}

function renderFlow(data){
 if(fmRAF){cancelAnimationFrame(fmRAF);fmRAF=null;}
 const host=$('#flow');host.innerHTML='';
 const W=host.clientWidth||1000,H=440,px=n=>60+n.x*(W-120),py=n=>40+n.y*(H-80);
 const byId={};data.nodes.forEach(n=>byId[n.id]=n);
 const maxV=Math.max(...data.links.map(l=>l.value),1);
 const svg=document.createElementNS(SVGNS,'svg');svg.setAttribute('width',W);svg.setAttribute('height',H);
 svg.style.position='absolute';svg.style.left=0;svg.style.top=0;host.append(svg);
 const li=[];
 for(const l of data.links){const a=byId[l.source],b=byId[l.target];if(!a||!b)continue;
  const x1=px(a)+46,y1=py(a),x2=px(b)-46,y2=py(b),mx=(x1+x2)/2;
  const p=document.createElementNS(SVGNS,'path');
  p.setAttribute('d',`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
  p.setAttribute('fill','none');p.setAttribute('stroke','#cfd8dc');p.setAttribute('stroke-width',1+5*Math.sqrt(l.value/maxV));p.setAttribute('opacity',.7);svg.append(p);
  const nd=Math.max(1,Math.round(5*l.value/maxV)),dots=[];
  for(let i=0;i<nd;i++){const c=document.createElementNS(SVGNS,'circle');c.setAttribute('r',2.6);c.setAttribute('fill',b.is_bottleneck?'#DA291C':'#0072CE');svg.append(c);dots.push({el:c,ph:Math.random()});}
  li.push({path:p,len:p.getTotalLength(),dots,sp:.09+.05*Math.random()});}
 for(const n of data.nodes){
  const kind=(n.kind==='source'||n.kind==='admitted'||n.kind==='discharged')?n.kind:n.status;
  const c=el('div','fmnode '+kind);if(n.is_bottleneck)c.classList.add('bottleneck');
  c.style.left=px(n)+'px';c.style.top=py(n)+'px';c.dataset.label=n.label;
  c.innerHTML=`<div class="nm">${n.label}</div><div class="vol" data-vol>${Math.round(n.volume).toLocaleString()}</div>`+
    (n.kind==='process'?`<div class="wt">wait ${Math.round(n.mean_wait)}m</div>`:'')+(n.is_bottleneck?'<div class="flag">PINCH</div>':'');
  c.onclick=()=>drill(n);host.append(c);}
 let last=performance.now();
 (function f(now){const dt=(now-last)/1000;last=now;for(const L of li)for(const d of L.dots){d.ph=(d.ph+dt*L.sp)%1;const p=L.path.getPointAtLength(d.ph*L.len);d.el.setAttribute('cx',p.x);d.el.setAttribute('cy',p.y);}fmRAF=requestAnimationFrame(f);})(last);
}
function updateHour(){
 const H=curHour;$('#whenLbl').textContent='Your department at '+String(H).padStart(2,'0')+':00';
 const cen=(TOWER.census_by_hour||[])[H]||0;$('#censusLbl').textContent='about '+Math.round(cen)+' patients in the department';
 const by=TOWER.area_by_hour||{};
 $$('#flow .fmnode').forEach(node=>{
  const lab=node.dataset.label, arr=by[lab];
  if(!arr){return;}
  const now=arr[H], peak=Math.max(...arr,1);
  const v=node.querySelector('[data-vol]');if(v)v.textContent=Math.round(now).toLocaleString();
  if(node.classList.contains('source')||node.classList.contains('admitted')||node.classList.contains('discharged'))return;
  const r=now/peak;node.classList.remove('green','amber','red');
  node.classList.add(r>=0.8?'red':r>=0.45?'amber':'green');
 });
}
function drill(n){
 const by=(TOWER.area_by_hour||{})[n.label]||[];
 const peak=by.length?by.indexOf(Math.max(...by)):0;
 let bars='';
 if(by.length){const mx=Math.max(...by,1);bars='<div class="hours">'+by.map((v,h)=>`<div style="flex:1"><div class="b" style="height:${Math.round(80*v/mx)}px" title="${h}:00 — ${Math.round(v)} in area"></div><div class="lab">${h%6===0?h:''}</div></div>`).join('')+'</div>';}
 $('#drill').style.display='block';
 $('#drill').innerHTML=`<b>${n.label}</b> — ${Math.round(n.volume).toLocaleString()} patients over the week`+
   (n.kind==='process'?`, average wait ${Math.round(n.mean_wait)} min, ${Math.round(n.utilisation)}% busy. Busiest around ${peak}:00.`:'.')+
   (by.length?'<div class="sub" style="margin-top:8px">Patients in this area through the day:</div>'+bars:'');
}

// ---- workforce ----
let ROTA=null;
async function loadWorkforce(){
 loaded.wf=true;
 ROTA=JSON.parse(JSON.stringify(SETUP.department.rota||[]));
 renderRota();
 $('#wfAreas').innerHTML='<div class="loading"><span class="spin"></span> Checking your rota against demand…</div>';
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
   <td><button class="rm" title="Remove shift">✕</button></td></tr>`).join('');
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
function renderWorkforce(d){
 WF=d;
 $('#wfHeadline').innerHTML=d.headline;
 $('#wfDrill').style.display='none';
 $('#wfAreas').innerHTML=d.areas.map((a,ai)=>{
  const smax=Math.max(...a.staffing,1);
  const bars=a.staffing.map((s,h)=>{
   const under=a.understaffed_hours.includes(h);
   return `<div style="flex:1"><div class="b ${under?'under':''}" data-ai="${ai}" data-h="${h}" style="height:${Math.round(80*s/smax)}px;cursor:pointer" title="${h}:00 — ${s} on shift${under?' (light vs demand)':''}"></div><div class="lab">${h%6===0?h:''}</div></div>`;
  }).join('');
  const win=a.understaffed_hours.length?`Light vs demand around ${String(Math.min(...a.understaffed_hours)).padStart(2,'0')}:00–${String((Math.max(...a.understaffed_hours)+1)%24).padStart(2,'0')}:00.`:'Broadly matches demand.';
  return `<div class="wfarea"><div class="t">${a.label}</div>
    <div class="m">Peak ${a.peak} · overnight ${a.overnight}. ${win}</div>
    <div class="hours">${bars}</div></div>`;
 }).join('');
 $$('#wfAreas .b').forEach(b=>b.onclick=()=>wfDrill(+b.dataset.ai,+b.dataset.h));
 $('#wfCost').innerHTML=`Estimated weekly staffing cost (these roles): <b>£${d.weekly_cost.toLocaleString()}</b> · about £${Math.round(d.weekly_cost*52/1e6*10)/10}m a year.`;
}
function wfDrill(ai,h){
 const a=WF.areas[ai], on=a.staffing[h], dem=Math.round(WF.demand[h]);
 const dmax=Math.max(...WF.demand,1), share=Math.round(100*WF.demand[h]/dmax);
 const under=a.understaffed_hours.includes(h);
 const roles=a.roles&&a.roles.length?a.roles.map(r=>r.label).join(', '):'—';
 const hh=String(h).padStart(2,'0'), nh=String((h+1)%24).padStart(2,'0');
 $('#wfDrill').style.display='block';
 $('#wfDrill').innerHTML=`<b>${a.label} — ${hh}:00–${nh}:00</b><br>
   <b>${on}</b> on shift this hour. Roles that staff this area: ${roles}.<br>
   Demand at this hour is about <b>${dem}</b> arrivals (${share}% of the daily peak). `+
   (under?`<span style="color:var(--red);font-weight:700">This is one of the hours staffing looks light against demand — the most likely time to fall behind.</span>`
        :`Staffing broadly matches demand this hour.`)+
   `<div class="hint" style="margin-top:6px">Adjust this in the rota below, then “Apply &amp; re-run”.</div>`;
}

// ---- gaps ----
async function loadGaps(){
 loaded.gap=true;$('#gapMiss').innerHTML='<div class="loading"><span class="spin"></span> Comparing against the Model ED…</div>';
 try{const d=await post('/api/gap',{});renderGaps(d);}catch(e){$('#gapMiss').innerHTML='Error: '+e.message;}
}
function renderGaps(d){
 $('#gapSummary').innerHTML=`You have <b>${d.have} of ${d.total}</b> Model ED elements. Current 4-hour performance about <b>${d.baseline_four_hour}%</b>, with about <b>${d.baseline_admit}%</b> of attendances admitted.`;
 $('#gapHave').innerHTML=d.present.map(p=>`<div class="gap have"><div class="imp"><span class="tick">✓ have</span></div><div class="body"><div class="t">${p.label}</div><div class="w">${p.why}</div></div></div>`).join('')||'<p class="sub">No Model ED elements enabled yet.</p>';
 $('#gapMiss').innerHTML=d.missing.length?d.missing.map(m=>{
   const sign=(typeof m.value==='number'&&m.unit.includes('4-hr')&&m.value>=0)?'+':'';
   return `<div class="gap miss">
   <div class="imp"><div class="d">${sign}${Math.round(m.value)}</div><div class="r">${m.unit}</div></div>
   <div class="body"><div class="t">${m.label}</div><div class="w">${m.benefit}</div></div>
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
 $('#rotaStatus').innerHTML='<span class="spin"></span> Applying and re-running…';
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
 $('#setupStatus').innerHTML='<span class="spin"></span> Saving and re-running…';
 try{await post('/api/department',dept);SETUP.department=dept;loaded={};
  $('#setupStatus').textContent='Saved. Updated the control tower.';
  $$('#nav a').forEach(x=>x.classList.remove('active'));$('#nav a[data-tab=tower]').classList.add('active');
  $$('.panel').forEach(p=>p.classList.remove('active'));$('#panel-tower').classList.add('active');
  loadTower();
 }catch(e){$('#setupStatus').textContent='Error: '+e.message;}
};
