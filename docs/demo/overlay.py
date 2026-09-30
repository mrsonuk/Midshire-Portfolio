# -*- coding: utf-8 -*-
"""What gets injected into the live page for the recording.

A caption bar with a step chip, a title and the spoken line; a visible cursor
that follows the real mouse with a ring on every click; a yellow highlight
outline for whatever the voice is describing; and eased scrolling, so the page
never jumps. Everything here is pointer-events:none - an overlay that swallows
a click costs a whole take.
"""

CSS = """
:root{--demo-ink:#0b2038;--demo-hi:#ffd21f}

#__bar{position:fixed;left:0;right:0;bottom:0;z-index:2147483400;pointer-events:none;
 background:linear-gradient(180deg,rgba(11,32,56,0) 0,rgba(11,32,56,.93) 26%,rgba(11,32,56,.98) 100%);
 padding:34px 60px 20px;display:flex;flex-direction:column;align-items:center;
 min-height:120px;justify-content:flex-end}
#__head{display:flex;align-items:center;gap:11px;margin-bottom:7px}
#__chip{background:#00a3ad;color:#042027;font:800 11.5px/1 -apple-system,Segoe UI,Roboto,sans-serif;
 letter-spacing:.07em;text-transform:uppercase;padding:5px 10px;border-radius:4px}
#__title{color:#9fc4dd;font:600 13px/1 -apple-system,Segoe UI,Roboto,sans-serif;
 letter-spacing:.05em;text-transform:uppercase}
#__sub{color:#fff;font:400 21px/1.44 Georgia,"Times New Roman",serif;text-align:center;
 max-width:1080px;text-wrap:balance}

#__cursor{position:fixed;z-index:2147483500;pointer-events:none;width:22px;height:22px;
 margin:-2px 0 0 -2px;opacity:0;transition:opacity .25s;
 filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
#__ring{position:fixed;z-index:2147483450;pointer-events:none;width:14px;height:14px;
 margin:-7px 0 0 -7px;border-radius:50%;border:3px solid #00a3ad;opacity:0}
@keyframes __clickring{0%{transform:scale(.5);opacity:.95}100%{transform:scale(4.2);opacity:0}}
#__ring.go{animation:__clickring .55s ease-out}

#__hl{position:fixed;z-index:2147482000;pointer-events:none;border:3px solid var(--demo-hi);
 border-radius:8px;box-shadow:0 0 0 3px rgba(255,210,31,.28),0 0 26px rgba(255,210,31,.45);
 opacity:0;transition:all .5s cubic-bezier(.4,0,.2,1)}

#__card,#__panel{position:fixed;inset:0;z-index:2147483200;pointer-events:none;
 background:#0b2038;color:#fff;display:none;flex-direction:column;align-items:center;
 justify-content:center;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
#__panel{background:#f4f7fa;color:var(--demo-ink);justify-content:flex-start;padding:24px 44px 132px}
#__card img{height:58px;width:auto;background:#fff;padding:9px 13px;border-radius:7px;
 margin-bottom:30px;display:block}
#__card h1{font-size:40px;margin:0 0 12px;font-weight:700;letter-spacing:-.4px}
#__card h2{font-size:21px;margin:0;font-weight:400;color:#cfe3ef}
#__card .rule{width:96px;height:4px;background:#00a3ad;margin:22px 0}
#__card .foot{position:absolute;bottom:150px;font-size:14px;color:#7fa3bd}
#__panel h1{font-size:24px;margin:0 0 4px}
#__panel .sub{font-size:12.5px;color:#4a6076;margin:0 0 12px}
#__panel table{border-collapse:collapse;font-size:12px;width:100%}
#__panel tr.need td{background:#fdf0f0}
#__panel td,#__panel th{padding:2.5px 8px;font-size:12px;text-align:left;border-bottom:1px solid #dbe3ea}
#__panel th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#5b7189}
#__panel .chip{display:inline-block;padding:2px 7px;border-radius:20px;font-size:10.5px;
 font-weight:700;white-space:nowrap}
#__panel .g{background:#d6f0dd;color:#1c6b33}
#__panel .a{background:#fdeccd;color:#8a5a06}
#__panel .r{background:#fbd9d9;color:#9c2020}
#__panel .n{background:#e3e8ed;color:#4a6076}
#__panel .cols{display:flex;gap:28px;align-items:flex-start;width:100%}
#__panel .cols>div{flex:1;min-width:0}
#__panel .big td{font-size:15.5px;padding:6px 9px}
#__panel .big .num{font-variant-numeric:tabular-nums;font-weight:700}
#__panel .ok{color:#1c6b33;font-weight:700}
#__panel .warn{color:#8a5a06;font-weight:700}
#__panel ol{font-size:15.5px;line-height:1.55;margin:2px 0 0 2px;padding-left:22px}
#__panel ol li{margin-bottom:12px}

/* the caption bar owns the bottom 120px, so lift the app's bottom-anchored
   furniture clear of it or the chat's input row records as hidden */
body{padding-bottom:124px !important}
#chatFab{bottom:138px !important}
#chatPanel.open{bottom:194px !important;max-height:calc(100vh - 320px) !important}
"""

JS = r"""
(() => {
  if (window.__demoReady) return;
  const add = (id, tag) => { const e = document.createElement(tag || 'div'); e.id = id;
                             document.body.appendChild(e); return e; };

  const card = add('__card');
  card.innerHTML = '<img src="/static/cuh-logo.png" alt="">' +
                   '<h1></h1><div class="rule"></div><h2></h2><div class="foot"></div>';
  add('__panel');
  add('__hl');
  add('__ring');

  // a real arrow, drawn where the real mouse is - Chromium does not record one
  const cur = add('__cursor');
  cur.innerHTML =
    '<svg viewBox="0 0 22 22" width="22" height="22">' +
    '<path d="M2 1 L2 17 L6.2 13.2 L9 19.6 L12 18.2 L9.2 12 L15 12 Z" ' +
    'fill="#fff" stroke="#0b2038" stroke-width="1.4" stroke-linejoin="round"/></svg>';

  const bar = add('__bar');
  bar.innerHTML = '<div id="__head"><span id="__chip"></span><span id="__title"></span></div>' +
                  '<div id="__sub"></div>';

  document.addEventListener('mousemove', e => {
    cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px';
    cur.style.opacity = 1;
  }, true);
  document.addEventListener('mousedown', e => {
    const r = document.getElementById('__ring');
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    r.classList.remove('go'); void r.offsetWidth; r.classList.add('go');
  }, true);

  window.__step = (chip, title) => {
    document.getElementById('__chip').textContent = chip || '';
    document.getElementById('__title').textContent = title || '';
  };
  window.__say = t => { document.getElementById('__sub').textContent = t || ''; };

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
    const h = document.getElementById('__hl');
    if (!sel) { h.style.opacity = 0; return; }
    const e = document.querySelector(sel);
    if (!e) { h.style.opacity = 0; return; }
    const b = e.getBoundingClientRect();
    if (!b.width && !b.height) { h.style.opacity = 0; return; }
    h.style.left = (b.left - 6) + 'px';  h.style.top = (b.top - 6) + 'px';
    h.style.width = (b.width + 12) + 'px'; h.style.height = (b.height + 12) + 'px';
    h.style.opacity = 1;
  };

  // eased scroll - a jump reads as a glitch on video, so every move is driven
  // over 2 to 2.5 seconds and the highlight is re-anchored as the page moves.
  window.__scroll = (sel, block, ms) => new Promise(done => {
    const e = document.querySelector(sel);
    if (!e) { done(false); return; }
    const b = e.getBoundingClientRect();
    const margin = block === 'start' ? 90 : Math.max(90, (innerHeight - 124 - b.height) / 2);
    const to = Math.max(0, scrollY + b.top - margin);
    const from = scrollY, d = to - from, t0 = performance.now();
    if (Math.abs(d) < 4) { done(true); return; }
    const ease = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
    (function f(now) {
      const p = Math.min(1, (now - t0) / ms);
      scrollTo(0, from + d * ease(p));
      if (window.__hlsel) window.__hi(window.__hlsel);
      p < 1 ? requestAnimationFrame(f) : done(true);
    })(t0);
  });

  window.__demoReady = true;
})();
"""
