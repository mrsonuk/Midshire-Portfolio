"use strict";
let PATHWAYS={}, KEYS=[], current="", busy=false, fmRAF=null, lastFlow=null;
const $=s=>document.querySelector(s);
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
const SVGNS="http://www.w3.org/2000/svg";

function initDashboard(pathways){
  PATHWAYS=pathways; KEYS=Object.keys(pathways);
  current=KEYS.includes("your_department")?"your_department":(KEYS.includes("model_ed")?"model_ed":KEYS[0]);
  const sel=$("#pathway"); sel.innerHTML="";
  for(const k of KEYS){const o=document.createElement("option");o.value=k;o.textContent=pathways[k].name;sel.append(o);}
  sel.value=current; sel.onchange=()=>{current=sel.value;renderPathway();runSim();};
  bindSlider("older","olderV","%"); bindSlider("imd","imdV",""); bindSlider("paed","paedV","%");
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>switchTab(t.dataset.tab));
  $("#runBtn").onclick=runSim; $("#mcBtn").onclick=runMC;
  $("#scnAdd").onclick=()=>addScenarioRow(); $("#scnRun").onclick=runScenarios;
  $("#calibBtn").onclick=runCalibrate; $("#resetBtn").onclick=resetCalib;
  let rT;addEventListener("resize",()=>{clearTimeout(rT);rT=setTimeout(()=>{if(lastFlow)renderFlowMap(lastFlow);},250);});
  renderPathway(); buildScenarioPresets(); runSim();
}
function bindSlider(id,vid,suf){const s=$("#"+id);const u=()=>$("#"+vid).textContent=s.value+suf;s.oninput=u;s.onchange=runSim;u();}
function renderPathway(){
  const p=PATHWAYS[current]; $("#pdesc").textContent=p.description;
  if(p.sd&&p.sd.inpatient_beds)$("#sd_beds").value=p.sd.inpatient_beds;
  if(p.sd&&p.sd.community_capacity)$("#sd_comm").value=p.sd.community_capacity;
  const box=$("#resources"); box.innerHTML="";
  for(const[n,c] of Object.entries(p.resources)){
    const r=el("div","row"); r.append(el("span",null,n.replace(/_/g," ")));
    if(Array.isArray(c)){
      // a by-hour staffing rota (set in the product) - show its peak, keep the rota
      r.append(el("span",null,"rota · peak "+Math.max.apply(null,c)));
    }else{
      const i=el("input");i.type="number";i.min=0;i.value=c;i.dataset.res=n;r.append(i);
    }
    box.append(r);
  }
}
function overrides(){const o={};document.querySelectorAll("#resources input").forEach(i=>o[i.dataset.res]=+i.value);return o;}
function cfg(extra){return Object.assign({pathway:current,overrides:overrides(),
  arrivals_scale:+$("#demand").value,feedback:$("#feedback").value==="1",
  population:{older_fraction:+$("#older").value/100,imd_decile:+$("#imd").value,paediatric_fraction:+$("#paed").value/100},
  sd_overrides:{inpatient_beds:+$("#sd_beds").value,community_capacity:+$("#sd_comm").value}},extra||{});}

function setBusy(on,msg,cls){busy=on;document.querySelectorAll("button").forEach(b=>b.disabled=on);
  const s=$("#status");s.className="status "+(cls||(on?"run":"ok"));s.innerHTML=on?'<span class="spin"></span> '+(msg||"Working…"):(msg||"");}
async function post(u,b){const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});if(!r.ok)throw new Error("server "+r.status);return r.json();}
function loading(id,m){Plotly.purge(id);$("#"+id).innerHTML='<div class="loading"><span class="spin"></span> '+(m||"Simulating…")+'</div>';}
function plot(id,f){Plotly.purge(id);$("#"+id).innerHTML="";return Plotly.newPlot(id,f.data,f.layout,{responsive:true,displayModeBar:false});}
function switchTab(n){document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.dataset.tab===n));
  document.querySelectorAll(".panel").forEach(p=>p.classList.toggle("active",p.id==="panel-"+n));}

function renderScorecard(cards){
  const box=$("#scorecard");box.innerHTML="";
  for(const c of cards){const d=el("div","sc "+c.status);const a=c.higher_better?"≥":"<";
    d.innerHTML='<div class="ring">'+c.value.toFixed(0)+c.unit+'</div><div><div class="lbl">'+c.label+
      '</div><div class="tgt">Target '+a+" "+c.target+c.unit+" · "+c.note+'</div></div><div class="badge">'+c.status.toUpperCase()+'</div>';
    box.append(d);}
}
function showDiag(d){$("#diagnosis").innerHTML='<div class="dh">Bottleneck diagnosis</div><p>'+d.headline+'</p><p>'+d.recommendation+'</p>';}

async function runSim(){
  if(busy)return;
  try{setBusy(true,"Simulating (SD+DES)…");loading("utilisation");loading("waits");loading("sd_stocks");loading("sd_feedback");
    const d=await post("/api/simulate",cfg());
    renderScorecard(d.scorecard);showDiag(d.diagnosis);renderFlowMap(d.flow_model);
    await plot("utilisation",d.figures.utilisation);await plot("waits",d.figures.waits);
    await plot("sd_stocks",d.figures.sd_stocks);await plot("sd_feedback",d.figures.sd_feedback);
    renderValSummary(d.conformance,null);
    setBusy(false,"Simulation complete ("+(d.conformance.passed?"pathway validated":"validation: "+d.conformance.n_violations+" violations")+")","ok");
  }catch(e){setBusy(false,"Error: "+e.message,"err");}
}
async function runMC(){
  if(busy)return;switchTab("mc");
  try{setBusy(true,"Monte-Carlo (24 weeks)…");loading("mc_four");loading("mc_twelve");loading("mc_occ");
    const d=await post("/api/montecarlo",cfg({replications:24}));
    const ip=$("#mcInterp");ip.style.display="block";ip.innerHTML='<div class="dh">What this means</div><p>'+d.interpretation+'</p>';
    await plot("mc_four",d.four_hour);await plot("mc_twelve",d.twelve);await plot("mc_occ",d.occ_band);
    setBusy(false,"Monte-Carlo complete","ok");
  }catch(e){setBusy(false,"Error: "+e.message,"err");}
}

// ---- flow model (SVG links + animated dots + HTML cards + SD stocks) ----
function renderFlowMap(data){
  lastFlow=data;const host=$("#flowmap");
  if(fmRAF){cancelAnimationFrame(fmRAF);fmRAF=null;}host.innerHTML="";
  if(!data||!data.nodes.length){host.innerHTML='<div class="loading">No flow</div>';return;}
  const W=host.clientWidth||1000,H=host.clientHeight||430,px=n=>60+n.x*(W-120),py=n=>40+n.y*(H-80);
  const byId={};data.nodes.forEach(n=>byId[n.id]=n);
  const maxV=Math.max(...data.links.map(l=>l.value),1);
  const svg=document.createElementNS(SVGNS,"svg");svg.setAttribute("width",W);svg.setAttribute("height",H);
  svg.style.position="absolute";svg.style.left=0;svg.style.top=0;host.append(svg);
  const li=[];
  for(const l of data.links){const s=byId[l.source],t=byId[l.target];if(!s||!t)continue;
    const x1=px(s)+46,y1=py(s),x2=px(t)-46,y2=py(t),mx=(x1+x2)/2;
    const path=document.createElementNS(SVGNS,"path");
    path.setAttribute("d",`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
    path.setAttribute("fill","none");path.setAttribute("stroke","#cfd8dc");
    path.setAttribute("stroke-width",1+5*Math.sqrt(l.value/maxV));path.setAttribute("opacity",.7);svg.append(path);
    const nd=Math.max(1,Math.round(5*l.value/maxV)),dots=[];
    for(let i=0;i<nd;i++){const c=document.createElementNS(SVGNS,"circle");c.setAttribute("r",2.6);
      c.setAttribute("fill",t.is_bottleneck?"#DA291C":"#0072CE");svg.append(c);dots.push({el:c,ph:Math.random()});}
    li.push({path,len:path.getTotalLength(),dots,sp:.09+.05*Math.random()});}
  for(const n of data.nodes){
    const kind=(n.kind==="source"||n.kind==="admitted"||n.kind==="discharged")?n.kind:n.status;
    const c=el("div","fmnode "+kind);if(n.is_bottleneck)c.classList.add("bottleneck");
    c.style.left=px(n)+"px";c.style.top=py(n)+"px";
    let h='<div class="nm">'+n.label+'</div><div class="vol">'+n.volume.toLocaleString()+'</div>';
    if(n.kind==="process")h+='<div class="wt">wait '+n.mean_wait.toFixed(0)+"m · "+n.utilisation.toFixed(0)+'% busy</div>';
    if(n.is_bottleneck)h+='<div class="flag">BOTTLENECK</div>';
    c.innerHTML=h;host.append(c);}
  let last=performance.now();
  (function frame(now){const dt=(now-last)/1000;last=now;
    for(const L of li)for(const d of L.dots){d.ph=(d.ph+dt*L.sp)%1;const p=L.path.getPointAtLength(d.ph*L.len);d.el.setAttribute("cx",p.x);d.el.setAttribute("cy",p.y);}
    fmRAF=requestAnimationFrame(frame);})(last);
  // SD stock reservoirs
  const sb=$("#stocks");sb.innerHTML="";
  for(const s of data.stocks||[]){const col=s.occupancy>92?"var(--red)":s.occupancy>80?"var(--orange)":"var(--green)";
    const d=el("div","stock");d.innerHTML='<div class="sn">'+s.name+'</div><div class="so" style="color:'+col+'">'+s.occupancy+
      '%</div><div class="bar"><i style="width:'+Math.min(100,s.occupancy)+'%;background:'+col+'"></i></div><div class="sf">'+s.signal+" → "+s.feeds+'</div>';sb.append(d);}
}

// ---- scenarios ----
function buildScenarioPresets(){
  const p=[
   {name:"+40 inpatient beds",sd:{inpatient_beds:360}},
   {name:"+30% community capacity",sd:{community_capacity:90,community_clearance_per_hour:6}},
   {name:"Redirect 20% low-acuity to UTC",divert:{classes:["Acuity 4","Acuity 5"],fraction:.20}},
   {name:"Winter +15% demand",arrivals_scale:1.15},
  ];
  $("#scnList").innerHTML="";p.forEach(addScenarioRow);
}
function addScenarioRow(pre){
  if(!pre||pre instanceof Event)pre={name:"New scenario"};
  const d=el("div","chart");d.style.padding="10px";d.dataset.scn="1";
  const nm=el("input");nm.type="text";nm.value=pre.name;nm.dataset.k="name";nm.style.marginBottom="6px";d.append(nm);
  const res=PATHWAYS[current].resources;
  const r1=el("div","row");const sel=el("select");sel.dataset.k="res";
  sel.append(new Option("- ED resource -",""));for(const r in res)sel.append(new Option(r.replace(/_/g," "),r));
  const dl=el("input");dl.type="number";dl.value=pre.resources?(""+Object.values(pre.resources)[0]).replace("+",""):0;dl.dataset.k="delta";dl.style.width="62px";
  sel.value=pre.resources?Object.keys(pre.resources)[0]:"";r1.append(el("span",null,"Δ capacity"),sel,dl);d.append(r1);
  const r2=el("div","row");const beds=el("input");beds.type="number";beds.dataset.k="beds";beds.placeholder="beds";beds.style.width="62px";
  if(pre.sd&&pre.sd.inpatient_beds)beds.value=pre.sd.inpatient_beds;
  const comm=el("input");comm.type="number";comm.dataset.k="comm";comm.placeholder="comm";comm.style.width="62px";
  if(pre.sd&&pre.sd.community_capacity)comm.value=pre.sd.community_capacity;
  r2.append(el("span",null,"SD beds / community"),beds,comm);d.append(r2);
  const r3=el("div","row");const dm=el("input");dm.type="number";dm.step="0.05";dm.value=pre.arrivals_scale||1;dm.dataset.k="scale";dm.style.width="62px";
  const utc=el("input");utc.type="number";utc.dataset.k="utc";utc.placeholder="% UTC";utc.style.width="62px";
  if(pre.divert)utc.value=Math.round(pre.divert.fraction*100);
  r3.append(el("span",null,"demand × / redirect %"),dm,utc);d.append(r3);
  $("#scnList").append(d);
}
function collectScenarios(){
  return Array.from(document.querySelectorAll("[data-scn]")).map(d=>{
    const g=k=>d.querySelector('[data-k='+k+']');const s={name:g("name").value};
    const res=g("res").value,delta=+g("delta").value;if(res&&delta)s.resources={[res]:(delta>0?"+":"")+delta};
    const sc=+g("scale").value;if(sc&&sc!==1)s.arrivals_scale=sc;
    const sd={};if(+g("beds").value)sd.inpatient_beds=+g("beds").value;
    if(+g("comm").value){sd.community_capacity=+g("comm").value;sd.community_clearance_per_hour=+g("comm").value/15;}
    if(Object.keys(sd).length)s.sd=sd;
    const u=+g("utc").value;if(u>0)s.divert={classes:["Acuity 4","Acuity 5"],fraction:u/100};
    return s;});
}
async function runScenarios(){
  if(busy)return;
  try{setBusy(true,"Comparing scenarios…");loading("scn_four");loading("scn_twelve");loading("scn_tornado");
    const d=await post("/api/scenarios",cfg({scenarios:collectScenarios(),replications:8}));
    await plot("scn_four",d.four_hour);await plot("scn_twelve",d.twelve);
    if(d.tornado)await plot("scn_tornado",d.tornado);else $("#scn_tornado").innerHTML="";
    renderScnTable(d.rows);setBusy(false,"Comparison complete","ok");
  }catch(e){setBusy(false,"Error: "+e.message,"err");}
}
function renderScnTable(rows){
  const cols=[["four_hour","4-hr %",true,0],["twelve_hour","12-hr %",false,1],["bed_occupancy","Bed occ %",false,0],
   ["mh_over_24h","MH>24h %",false,0],["child_four_hour","Child 4-hr %",true,0]].filter(c=>rows[0][c[0]]!==undefined);
  const base=rows[0];let h='<div class="head">Scenario impact across measures (vs baseline)</div><table><tr><th>Scenario</th>'+
    cols.map(c=>'<th style="text-align:right">'+c[1]+'</th>').join("")+"</tr>";
  rows.forEach((r,i)=>{h+="<tr"+(i===0?' style="font-weight:700"':"")+'><td>'+r.scenario+"</td>";
    for(const[k,,hb,dp] of cols){const v=r[k];let c=v.toFixed(dp);
      if(i>0){const dd=v-base[k],good=hb?dd>=0:dd<=0,col=Math.abs(dd)<.5?"var(--grey)":good?"var(--green)":"var(--red)";
        c+=' <span style="color:'+col+';font-weight:700">('+(dd>=0?"+":"")+dd.toFixed(dp)+")</span>";}
      h+='<td style="text-align:right">'+c+"</td>";}h+="</tr>";});
  $("#scnTable").innerHTML=h+"</table>";
}

// ---- validation ----
function renderValSummary(conf,variants){
  const col=conf.passed?"var(--green)":"var(--red)";
  let h='<div class="dh">Process-map conformance</div><p style="color:'+col+';font-weight:700">'+
    (conf.passed?"PASS - simulated pathway faithfully reproduces the Model ED design":
     "ISSUES - "+conf.n_violations+" violations")+'</p><p>Conformance rate: '+conf.conformance_rate.toFixed(1)+"% of patients.</p>";
  if(conf.by_type&&Object.keys(conf.by_type).length)h+="<p>By type: "+JSON.stringify(conf.by_type)+"</p>";
  $("#valSummary").innerHTML=h;
  if(variants){let t="<table><tr><th>Count</th><th>Variant</th></tr>";
    for(const v of variants)t+="<tr><td>"+v.count.toLocaleString()+"</td><td>"+v.variant+"</td></tr>";
    $("#variants").innerHTML=t+"</table>";}
}
async function loadValidation(){
  try{setBusy(true,"Validating pathway…");
    const d=await post("/api/validate",cfg());renderValSummary(d.conformance,d.variants);
    setBusy(false,d.conformance.passed?"Validation passed":"Validation found issues","ok");
  }catch(e){setBusy(false,"Error: "+e.message,"err");}
}

// ---- calibration ----
function setCalib(on){const e=$("#calibState");e.textContent="Data source: "+(on?"uploaded extract (calibrated)":"synthetic (placeholder)");e.style.color=on?"var(--green)":"var(--grey)";}
async function runCalibrate(){
  if(busy)return;const f=$("#dataFile").files[0];if(!f){setBusy(false,"Choose a CSV first","err");return;}
  try{setBusy(true,"Calibrating…");const fd=new FormData();fd.append("file",f);fd.append("pathway",current);
    const r=await fetch("/api/calibrate",{method:"POST",body:fd});const d=await r.json();
    if(!r.ok||d.error)throw new Error(d.error||"failed");
    const b=$("#calibSummary");b.style.display="block";
    b.innerHTML='<div class="dh">Calibration applied</div><ul>'+d.summary.map(s=>"<li>"+s+"</li>").join("")+"</ul>";
    setCalib(true);await runSim();setBusy(false,"Calibrated from data","ok");
  }catch(e){setBusy(false,"Error: "+e.message,"err");}
}
async function resetCalib(){
  if(busy)return;
  try{setBusy(true,"Resetting…");await post("/api/calibrate/reset",{pathway:current});
    $("#calibSummary").style.display="none";setCalib(false);await runSim();setBusy(false,"Reset to synthetic","ok");
  }catch(e){setBusy(false,"Error: "+e.message,"err");}
}
// validation tab loads on click
document.addEventListener("click",e=>{if(e.target.dataset&&e.target.dataset.tab==="val")loadValidation();});
