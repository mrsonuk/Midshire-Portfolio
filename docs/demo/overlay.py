# -*- coding: utf-8 -*-
"""The caption / act-chip / title-card / full-screen-panel overlay injected into
the live page, so the recording carries its own subtitles and the viewer never
sees a bare screen with a voice over it."""

CSS = """
#__act{position:fixed;top:10px;right:14px;z-index:2147483400;pointer-events:none;background:#0b2038;
 color:#fff;font:700 13px/1 -apple-system,Segoe UI,Roboto,sans-serif;
 letter-spacing:.04em;text-transform:uppercase;padding:8px 13px;border-radius:5px;
 box-shadow:0 3px 14px rgba(0,0,0,.28);opacity:.96}
#__cap{position:fixed;left:0;right:0;bottom:0;z-index:2147483400;pointer-events:none;
 background:linear-gradient(180deg,rgba(11,32,56,.0) 0,rgba(11,32,56,.94) 22%,rgba(11,32,56,.98) 100%);
 color:#fff;font:400 22px/1.42 Georgia,"Times New Roman",serif;
 padding:30px 78px 26px;text-align:center;min-height:104px;
 display:flex;align-items:flex-end;justify-content:center}
#__cap b{font-weight:400}
#__hlring{position:fixed;z-index:2147482000;border:3px solid #00a3ad;border-radius:8px;
 box-shadow:0 0 0 4px rgba(0,163,173,.22),0 0 30px rgba(0,163,173,.35);
 pointer-events:none;transition:all .45s cubic-bezier(.4,0,.2,1);opacity:0}
#__card,#__panel{position:fixed;inset:0;z-index:2147483200;pointer-events:none;background:#0b2038;
 color:#fff;display:none;flex-direction:column;align-items:center;
 justify-content:center;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
#__panel{background:#f4f7fa;color:#0b2038;justify-content:flex-start;padding:46px 56px 130px}
#__card h1{font-size:46px;margin:0 0 14px;font-weight:700;letter-spacing:-.5px}
#__card h2{font-size:24px;margin:0;font-weight:400;color:#cfe3ef}
#__card img{height:62px;width:auto;background:#fff;padding:9px 13px;border-radius:7px;margin-bottom:32px;display:block}
#__card .rule{width:110px;height:4px;background:#00a3ad;margin:26px 0}
#__card .foot{position:absolute;bottom:130px;font-size:15px;opacity:.6}
#__panel h1{font-size:30px;margin:0 0 6px}
#__panel .sub{font-size:15px;color:#4a6076;margin:0 0 22px}
#__panel table{border-collapse:collapse;font-size:14.5px;width:100%}
#__panel td,#__panel th{padding:5px 10px;text-align:left;border-bottom:1px solid #dbe3ea}
#__panel th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#5b7189}
#__panel .chip{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11.5px;
 font-weight:700;white-space:nowrap}
#__panel .g{background:#d6f0dd;color:#1c6b33}
#__panel .a{background:#fdeccd;color:#8a5a06}
#__panel .r{background:#fbd9d9;color:#9c2020}
#__panel .n{background:#e3e8ed;color:#4a6076}
#__panel .cols{display:flex;gap:34px;align-items:flex-start;width:100%}
#__panel .cols>div{flex:1;min-width:0}
#__panel .big td{font-size:17px;padding:8px 10px}
#__panel .big .num{font-variant-numeric:tabular-nums;font-weight:700}
#__panel .ok{color:#1c6b33;font-weight:700}
#__panel .warn{color:#8a5a06;font-weight:700}
#__panel ol{font-size:17.5px;line-height:1.58;margin:4px 0 0 4px;padding-left:24px}
#__panel ol li{margin-bottom:15px}
#__panel ol b{color:#0b2038}

/* the caption bar owns the bottom 110px of the frame, so lift the app's own
   bottom-anchored furniture clear of it - otherwise the chat's input row and
   the last line of a scrolled card record as hidden behind the subtitles. */
body{padding-bottom:112px !important}
#chatFab{bottom:126px !important}
#chatPanel.open{bottom:182px !important;max-height:calc(100vh - 300px) !important}
"""

JS = r"""
(() => {
  if (window.__demoReady) return;
  const mk = (id, tag) => { const e = document.createElement(tag||'div'); e.id = id;
                            document.body.appendChild(e); return e; };
  const card = mk('__card');
  card.innerHTML = '<img src="/static/cuh-logo.png" alt="">' +
                   '<h1></h1><div class="rule"></div><h2></h2>' +
                   '<div class="foot"></div>';
  const panel = mk('__panel');
  mk('__hlring');
  mk('__act').textContent = '';
  mk('__cap');

  window.__act  = t => { document.getElementById('__act').textContent = t || ''; };
  window.__cap  = t => { document.getElementById('__cap').textContent = t || ''; };
  window.__card = (h1, h2, foot) => {
    const c = document.getElementById('__card');
    if (h1 === null) { c.style.display = 'none'; return; }
    c.querySelector('h1').textContent = h1;
    c.querySelector('h2').textContent = h2 || '';
    c.querySelector('.foot').textContent = foot || '';
    c.style.display = 'flex';
  };
  window.__panel = html => {
    const p = document.getElementById('__panel');
    if (html === null) { p.style.display = 'none'; return; }
    p.innerHTML = html; p.style.display = 'flex';
  };
  window.__hi = sel => {
    const r = document.getElementById('__hlring');
    if (!sel) { r.style.opacity = 0; return; }
    const e = document.querySelector(sel);
    if (!e) { r.style.opacity = 0; return; }
    const b = e.getBoundingClientRect();
    if (!b.width && !b.height) { r.style.opacity = 0; return; }
    r.style.left = (b.left - 7) + 'px';  r.style.top = (b.top - 7) + 'px';
    r.style.width = (b.width + 14) + 'px'; r.style.height = (b.height + 14) + 'px';
    r.style.opacity = 1;
  };
  window.__demoReady = true;
})();
"""
