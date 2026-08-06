// Data-provenance banner, shared by every surface (control tower, exec brief,
// planner, analyst): where the numbers come from, what is still an assumption,
// or a clear demonstration-data warning. Advisory - never blocks a page.
async function renderDataStatus(){
 try{
  const d=await fetch('/api/data-status').then(r=>r.json());
  const b=document.querySelector('#dataStatus');if(!b)return;
  const demo=(d.source||{}).kind==='demo';
  const bits=[(d.source||{}).label||''];
  if((d.source||{}).as_of)bits.push('figures as of '+d.source.as_of);
  if(d.calibration&&d.calibration.applied)bits.push('calibrated '+d.calibration.created_at.slice(0,10));
  if(d.department&&d.department.updated_at)bits.push('set-up saved '+d.department.updated_at.slice(0,10)+' (v'+d.department.version+')');
  bits.push('engine '+d.engine_version);
  const assumed=(d.assumed||[]).length
   ?' <span style="color:#b25900">Still assumptions: '+d.assumed.join(', ')+'.</span>':'';
  b.style.display='block';
  if(demo){
   b.style.background='#fff4e5';b.style.border='1px solid #ffb81c';b.style.color='#3b3b3b';
   b.innerHTML='<b>Demonstration data.</b> '+(d.warnings||[]).join(' ')+assumed;
  }else{
   b.style.background='#eef6ee';b.style.border='1px solid #007f3b';b.style.color='#212b32';
   b.innerHTML='<b>Your data:</b> '+bits.filter(Boolean).join(' · ')+assumed;
  }
 }catch(e){/* banner is advisory; never block the page */}
}
document.addEventListener('DOMContentLoaded',()=>{
 if(document.querySelector('#dataStatus'))renderDataStatus();
});
