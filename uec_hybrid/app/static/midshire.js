/* Midshire University Hospitals Trust Control Tower - adult ED demonstrator.
   Every number shown here comes from the server's structured results (the
   metric contract in uec_hybrid/midshire/metrics.py). This script only picks
   the value for the selected scenario, day and time and formats it. All
   untrusted text (scenario names, assistant replies, imported rota cells) is
   inserted as TEXT, never as HTML. */
"use strict";
(function () {
  // ------------------------------------------------------------------ utils
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const svgEl = (tag, attrs) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
    return el;
  };
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const HHMM = (min) => { const m = Math.round(min) % 1440; return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); };
  const DAYNAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const fmt = (v, dp = 1, unit = "") => (v === null || v === undefined || Number.isNaN(v)) ? "not available" : Number(v).toFixed(dp) + unit;
  const fmtInt = (v) => (v === null || v === undefined) ? "not available" : Math.round(v).toLocaleString("en-GB");
  const money = (v) => (v === null || v === undefined) ? "not costed" : (v < 0 ? "-£" : "£") + Math.abs(Math.round(v)).toLocaleString("en-GB");
  const signed = (v, dp = 1, unit = "") => (v === null || v === undefined) ? "not available" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(dp) + unit;
  const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  class ApiError extends Error { constructor(msg, status, details) { super(msg); this.status = status; this.details = details || []; } }
  async function api(path, body, method) {
    const opts = { method: method || (body === undefined ? "GET" : "POST"), headers: {} };
    if (body !== undefined && !(body instanceof FormData)) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    else if (body instanceof FormData) opts.body = body;
    let r;
    try { r = await fetch(path, opts); } catch (e) { throw new ApiError("The server could not be reached. Is it still running?", 0); }
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new ApiError((data && data.error) || ("The server returned an error (" + r.status + ")."), r.status, data && data.details);
    return data;
  }
  function showError(where, err) {
    const box = typeof where === "string" ? $(where) : where;
    if (!box) return;
    box.replaceChildren(h("p", { text: err.message || String(err) }));
    if (err.details && err.details.length) {
      box.append(h("ul", {}, err.details.slice(0, 12).map(d => h("li", { text: (d.field ? d.field + (d.row ? " row " + d.row : "") + ": " : (d.row ? "Row " + d.row + ": " : "")) + (d.error || JSON.stringify(d)) }))));
    }
    box.hidden = false;
  }

  // ------------------------------------------------------------------ state
  const S = {
    meta: null, scenarios: [], applied: "baseline", current: null, result: null,
    baselineResult: null, draft: null, draftHash: null, preview: null,
    mode: "replay", day: 2, slot: 48, openGroup: null, playing: null,
    seq: { result: 0, preview: 0, search: 0, draftcmp: 0 }, searchJob: null, draftJob: null,
    covGroup: null, covDay: 0, compareSel: new Set(),
  };

  // ------------------------------------------------------------------ tabs
  const TABS = ["overview", "flow", "workforce", "scenarios", "setup"];
  function selectTab(name, focus) {
    for (const t of TABS) {
      const on = t === name;
      const tab = $("#tab-" + t);
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
      $("#panel-" + t).hidden = !on;
      if (on && focus) tab.focus();
    }
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    if (name === "overview") renderCharts();
    if (name === "workforce") renderCoverage();
    if (name === "flow") { S.flowKey = null; renderFlow(); }
  }
  function wireTabs() {
    $$("#tabs [role=tab]").forEach((tab, i, all) => {
      tab.addEventListener("click", () => selectTab(tab.id.slice(4)));
      tab.addEventListener("keydown", (e) => {
        let j = null;
        if (e.key === "ArrowRight") j = (i + 1) % all.length;
        if (e.key === "ArrowLeft") j = (i - 1 + all.length) % all.length;
        if (e.key === "Home") j = 0;
        if (e.key === "End") j = all.length - 1;
        if (j !== null) { e.preventDefault(); selectTab(all[j].id.slice(4), true); }
      });
    });
    $$("[data-goto]").forEach(b => b.addEventListener("click", () => selectTab(b.dataset.goto, true)));
    const want = (location.hash || "").slice(1);
    selectTab(TABS.includes(want) ? want : "overview");
  }

  // ------------------------------------------------------------------ charts
  // One y-axis per chart; recessive hairline grid; 2px lines; legend for
  // two or more series plus selective end labels; crosshair + tooltip on
  // hover AND keyboard focus; every chart has a table view elsewhere.
  const tip = () => $("#tooltip");
  function showTip(x, y, title, rows) {
    const t = tip();
    t.replaceChildren(h("div", { class: "tt-title", text: title }),
      ...rows.map(r => h("div", { class: "tt-row" },
        h("span", { class: "tt-key" }), h("span", { class: "tt-v", text: r.value }), h("span", { text: r.name }))));
    $$(".tt-key", t).forEach((k, i) => { k.style.background = rows[i].color; });
    t.hidden = false;
    const w = t.offsetWidth, hgt = t.offsetHeight;
    t.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, x + 14)) + "px";
    t.style.top = Math.max(8, Math.min(window.innerHeight - hgt - 8, y - hgt - 10)) + "px";
  }
  function hideTip() { tip().hidden = true; }

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  function lineChart(box, cfg) {
    // cfg: {labels[], series:[{name,values[],color,fmt}], marker, yTitle, xTick(i)->str|null, height}
    box.replaceChildren();
    const W = Math.max(320, box.clientWidth || 700), H = cfg.height || 240;
    const m = { l: 48, r: 92, t: 12, b: 34 };
    const n = cfg.labels.length;
    const all = cfg.series.flatMap(s => s.values.filter(v => v !== null && v !== undefined));
    const ymax = niceMax(Math.max(1, ...all));
    const x = (i) => m.l + (n <= 1 ? 0 : i * (W - m.l - m.r) / (n - 1));
    const y = (v) => m.t + (H - m.t - m.b) * (1 - v / ymax);
    const legend = h("div", { class: "legend" }, cfg.series.map(s => h("span", {}, h("span", { class: "key" }), s.name)));
    $$(".key", legend).forEach((k, i) => { k.style.background = cfg.series[i].color; });
    if (cfg.series.length > 1) box.append(legend);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, "aria-hidden": "true", focusable: "false" });
    const grid = svgEl("g", { class: "axis" });
    for (let k = 0; k <= 4; k++) {
      const v = ymax * k / 4, yy = y(v);
      grid.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy, stroke: token("--chart-grid"), "stroke-width": 1 }));
      const t = svgEl("text", { x: m.l - 6, y: yy + 4, "text-anchor": "end" }); t.textContent = Math.round(v).toLocaleString("en-GB"); grid.append(t);
    }
    let lastX = -1e9;
    for (let i = 0; i < n; i++) {
      const lab = cfg.xTick(i);
      if (lab === null || x(i) - lastX < 48) continue;          // never overlap labels
      lastX = x(i);
      const t = svgEl("text", { x: x(i), y: H - m.b + 18, "text-anchor": "middle" }); t.textContent = lab; grid.append(t);
    }
    grid.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), stroke: token("--chart-axis"), "stroke-width": 1 }));
    if (cfg.yTitle) { const t = svgEl("text", { x: m.l, y: H - 2, class: "label" }); t.textContent = cfg.yTitle; grid.append(t); }
    svg.append(grid);
    if (cfg.marker !== null && cfg.marker !== undefined) {
      svg.append(svgEl("line", { x1: x(cfg.marker), x2: x(cfg.marker), y1: m.t, y2: H - m.b, stroke: token("--nhs-text"), "stroke-width": 1 }));
    }
    cfg.series.forEach((s) => {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (v === null || v === undefined) { pen = false; return; }
        d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1) + " "; pen = true;
      });
      svg.append(svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      const li = s.values.length - 1;
      if (li >= 0 && s.values[li] !== null) {
        svg.append(svgEl("circle", { cx: x(li), cy: y(s.values[li]), r: 4, fill: s.color, stroke: token("--nhs-surface"), "stroke-width": 2 }));
        const t = svgEl("text", { x: x(li) + 8, y: y(s.values[li]) + 4, class: "label" }); t.textContent = s.name.split(" ")[0] + " " + (s.fmt ? s.fmt(s.values[li]) : s.values[li]); svg.append(t);
      }
      if (cfg.marker !== null && cfg.marker !== undefined && s.values[cfg.marker] !== null && s.values[cfg.marker] !== undefined) {
        svg.append(svgEl("circle", { cx: x(cfg.marker), cy: y(s.values[cfg.marker]), r: 4, fill: s.color, stroke: token("--nhs-surface"), "stroke-width": 2 }));
      }
    });
    const cross = svgEl("line", { y1: m.t, y2: H - m.b, stroke: token("--nhs-secondary-text"), "stroke-width": 1, visibility: "hidden" });
    svg.append(cross);
    const hit = svgEl("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
    svg.append(hit);
    let focusI = cfg.marker || 0;
    const show = (i, cx, cy) => {
      i = Math.max(0, Math.min(n - 1, i));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      showTip(cx, cy, cfg.tipTitle(i), cfg.series.map(s => ({ name: s.name, color: s.color, value: s.values[i] === null || s.values[i] === undefined ? "no observations" : (s.fmt ? s.fmt(s.values[i]) : s.values[i]) })));
    };
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width;
      show(Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, n - 1))), e.clientX, e.clientY);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
    box.tabIndex = 0;
    box.onkeydown = (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault(); focusI = Math.max(0, Math.min(n - 1, focusI + (e.key === "ArrowRight" ? 1 : -1)));
      const r = svg.getBoundingClientRect(); show(focusI, r.left + x(focusI) * r.width / W, r.top + 40);
    };
    box.onblur = () => { cross.setAttribute("visibility", "hidden"); hideTip(); };
    box.append(svg);
  }

  function columnChart(box, cfg) {
    // grouped columns: cfg {labels[], series:[{name,values,color}], yTitle, tipTitle(i), highlight}
    box.replaceChildren();
    const W = Math.max(320, box.clientWidth || 700), H = cfg.height || 200;
    const m = { l: 48, r: 16, t: 10, b: 34 };
    const n = cfg.labels.length, k = cfg.series.length;
    const all = cfg.series.flatMap(s => s.values.filter(v => v !== null && v !== undefined));
    const ymax = niceMax(Math.max(1, ...all));
    const band = (W - m.l - m.r) / n;
    const bw = Math.min(24, Math.max(3, (band - 2) / k - 2));
    const y = (v) => m.t + (H - m.t - m.b) * (1 - v / ymax);
    const legend = h("div", { class: "legend" }, cfg.series.map(s => h("span", {}, h("span", { class: "key bar" }), s.name)));
    $$(".key", legend).forEach((kk, i) => { kk.style.background = cfg.series[i].color; });
    if (k > 1) box.append(legend);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, "aria-hidden": "true", focusable: "false" });
    const g = svgEl("g", { class: "axis" });
    for (let q = 0; q <= 4; q++) {
      const v = ymax * q / 4, yy = y(v);
      g.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy, stroke: token("--chart-grid"), "stroke-width": 1 }));
      const t = svgEl("text", { x: m.l - 6, y: yy + 4, "text-anchor": "end" }); t.textContent = (Math.round(v * 10) / 10).toLocaleString("en-GB"); g.append(t);
    }
    let lastX = -1e9;
    for (let i = 0; i < n; i++) {
      const cx = m.l + band * (i + 0.5);
      if (cfg.xTick(i) === null || cx - lastX < 48) continue;  // never overlap labels
      lastX = cx;
      const t = svgEl("text", { x: cx, y: H - m.b + 18, "text-anchor": "middle" }); t.textContent = cfg.xTick(i); g.append(t);
    }
    svg.append(g);
    const rr = 4;
    for (let i = 0; i < n; i++) {
      const gx = m.l + band * i + (band - (k * bw + (k - 1) * 2)) / 2;
      cfg.series.forEach((s, j) => {
        const v = s.values[i];
        if (v === null || v === undefined) return;
        const x0 = gx + j * (bw + 2), y0 = y(v), y1 = y(0), hgt = Math.max(0, y1 - y0);
        const r = Math.min(rr, bw / 2, hgt);
        const d = `M${x0} ${y1} L${x0} ${y0 + r} Q${x0} ${y0} ${x0 + r} ${y0} L${x0 + bw - r} ${y0} Q${x0 + bw} ${y0} ${x0 + bw} ${y0 + r} L${x0 + bw} ${y1} Z`;
        const p = svgEl("path", { d, fill: s.color, opacity: (cfg.highlight === undefined || cfg.highlight === null || cfg.highlight === i) ? 1 : 0.45 });
        svg.append(p);
      });
      const hit = svgEl("rect", { x: m.l + band * i, y: m.t, width: band, height: H - m.t - m.b, fill: "transparent" });
      hit.addEventListener("pointermove", (e) => showTip(e.clientX, e.clientY, cfg.tipTitle(i),
        cfg.series.map(s => ({ name: s.name, color: s.color, value: s.values[i] === null ? "no observations" : (s.fmt ? s.fmt(s.values[i]) : s.values[i]) }))));
      hit.addEventListener("pointerleave", hideTip);
      svg.append(hit);
    }
    svg.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), stroke: token("--chart-axis"), "stroke-width": 1 }));
    if (cfg.yTitle) { const t = svgEl("text", { x: m.l, y: H - 2, class: "label" }); t.textContent = cfg.yTitle; svg.append(t); }
    let fi = cfg.highlight || 0;
    box.tabIndex = 0;
    box.onkeydown = (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault(); fi = Math.max(0, Math.min(n - 1, fi + (e.key === "ArrowRight" ? 1 : -1)));
      const r = svg.getBoundingClientRect();
      showTip(r.left + (m.l + band * (fi + 0.5)) * r.width / W, r.top + 30, cfg.tipTitle(fi),
        cfg.series.map(s => ({ name: s.name, color: s.color, value: s.values[fi] === null ? "no observations" : (s.fmt ? s.fmt(s.values[fi]) : s.values[fi]) })));
    };
    box.onblur = hideTip;
    box.append(svg);
  }

  function table(caption, head, rows, numCols) {
    const t = h("table", { class: "ms-table" });
    if (caption) t.append(h("caption", { text: caption }));
    t.append(h("thead", {}, h("tr", {}, head.map((c, i) => h("th", { scope: "col", class: (numCols || []).includes(i) ? "num" : null, text: c })))));
    t.append(h("tbody", {}, rows.map(r => h("tr", { class: r._class || null }, (r.cells || r).map((c, i) =>
      (c instanceof Node) ? h("td", { class: (numCols || []).includes(i) ? "num" : null }, c) :
        h(i === 0 ? "th" : "td", { scope: i === 0 ? "row" : null, class: (numCols || []).includes(i) ? "num" : null, text: c === null || c === undefined ? "" : String(c) }))))));
    return h("div", { class: "ms-table-wrap" }, t);
  }

  function renderCharts() { renderChartsImpl(); }
  function renderCoverage() { renderCoverageImpl(); }

  // ================================================================ loading
  const STEPS_PER_DAY = 96;
  function resultBadge(state, text) {
    const b = $("#resultBadge");
    b.className = "ms-badge " + (state || "");
    b.textContent = text;
  }

  async function loadScenarios() {
    const d = await api("/api/m/scenarios");
    S.scenarios = d.scenarios;
    S.applied = d.applied || "baseline";
    const sel = $("#scenarioPick");
    sel.replaceChildren(...S.scenarios.map(sc => h("option", { value: sc.id, text: sc.name + (sc.kind === "baseline" ? " (baseline)" : sc.kind === "precomputed" ? " (precomputed)" : "") })));
    sel.value = S.applied;
    renderScenarioTable();
  }

  async function applyScenario(id) {
    await api("/api/m/apply", { scenario_id: id });
    S.applied = id;
    $("#scenarioPick").value = id;
    await loadCurrent();
  }

  async function loadCurrent() {
    const d = await api("/api/m/scenarios/" + encodeURIComponent(S.applied));
    S.current = d.scenario;
    S.draft = clone(S.current.inputs);
    S.result = null;
    renderAllEmpty();
    renderEditor();
    schedulePreview();
    await requestResult();
  }

  // the result for the APPLIED scenario; stale responses are ignored
  async function requestResult() {
    const my = ++S.seq.result;
    const sid = S.current.id, mh = S.current.model_hash;
    resultBadge("", "Loading results…");
    let d;
    try { d = await api("/api/m/result", { scenario_id: sid, request_id: my }); }
    catch (e) { if (my === S.seq.result) { resultBadge("failed", "Could not load results"); showError("#globalError", e); } return; }
    if (my !== S.seq.result || sid !== S.current.id) return;      // a newer request owns the screen
    if (d.status !== "done") {
      S.result = null;
      resultBadge("missing", "Not yet simulated");
      renderNotSimulated();
      return;
    }
    if (d.result.model_hash !== mh) return;                         // never show numbers for other inputs
    S.result = d.result;
    if (sid === "baseline") S.baselineResult = d.result;
    const src = d.result.result_source === "precomputed" ? "Precomputed result" : "Simulated result";
    resultBadge(d.result.result_source === "precomputed" ? "precomputed" : "", src + " · " + d.result.replications + " simulated weeks");
    $("#globalError").hidden = true;
    renderAll();
  }

  async function simulateApplied() {
    const sid = S.current.id;
    resultBadge("", "Simulating…");
    try {
      const d = await api("/api/m/run", { scenario_id: sid });
      if (d.status === "done") return requestResult();
      await pollJob(d.job.id, (j) => resultBadge("", (j.message || "Simulating") + " (" + Math.round(100 * j.progress) + "%)"));
      if (S.current.id === sid) await requestResult();
      renderScenarioTable();
    } catch (e) { resultBadge("failed", "Simulation failed"); showError("#globalError", e); }
  }

  function pollJob(id, onTick) {
    return new Promise((resolve, reject) => {
      const tick = async () => {
        let j;
        try { j = await api("/api/m/jobs/" + id); } catch (e) { reject(e); return; }
        if (onTick) onTick(j);
        if (j.status === "done") resolve(j);
        else if (j.status === "failed") reject(new ApiError(j.message + " " + (j.error || ""), 500, j.details));
        else if (j.status === "cancelled") reject(new ApiError("Cancelled - nothing was saved.", 499));
        else setTimeout(tick, 900);
      };
      tick();
    });
  }

  // ================================================================ context
  function dayOptions() {
    const rp = S.result && S.result.replay;
    const sel = $("#dayPick");
    if (!rp) { sel.replaceChildren(); return; }
    const ndays = Math.round((rp.times[rp.times.length - 1] - rp.t0) / 1440);
    const opts = [];
    for (let d = 0; d < ndays; d++) {
      const abs = rp.t0 + d * 1440;
      opts.push(h("option", { value: d, text: "Day " + (d + 1) + " (" + DAYNAMES[Math.floor(abs / 1440) % 7] + ")" }));
    }
    sel.replaceChildren(...opts);
    S.day = Math.min(S.day, ndays - 1);
    sel.value = S.day;
  }
  function idx() { return S.day * STEPS_PER_DAY + S.slot; }
  function viewTime() { const rp = S.result.replay; return rp.times[idx()]; }
  function hourOf() { return Math.floor(S.slot / 4); }

  function renderContext() {
    const typ = S.mode === "typical";
    $("#modeReplay").setAttribute("aria-checked", typ ? "false" : "true");
    $("#modeTypical").setAttribute("aria-checked", typ ? "true" : "false");
    $("#modeReplay").tabIndex = typ ? -1 : 0; $("#modeTypical").tabIndex = typ ? 0 : -1;
    $("#dayWrap").hidden = typ;
    const slider = $("#timeSlider");
    slider.step = typ ? 4 : 1;
    if (typ) S.slot = hourOf() * 4;
    slider.value = S.slot;
    $("#timeOut").textContent = HHMM(S.slot * 15);
    slider.setAttribute("aria-valuetext", HHMM(S.slot * 15) + (typ ? " (typical day)" : " on simulated day " + (S.day + 1)));
    $("#timeHelp").textContent = typ ? "Hourly steps (average simulated patients)" : "15-minute steps";
    const r = S.result, eng = S.current && S.current.inputs.engine;
    if (r && eng) {
      const dayTxt = typ ? "Typical day: hour-of-day AVERAGES over the observed days of one simulated week."
        : "Single simulated day: day " + (S.day + 1) + " of " + eng.observed_days + " of ONE simulated week (seed " + r.replay.seed + ") - whole numbers of simulated patients.";
      $("#periodText").textContent = "Scenario: " + S.current.name + ". Each simulated week = " + eng.warmup_days + "-day warm-up, " + eng.observed_days +
        " observed days, " + eng.drain_hours + "-hour drain. " + dayTxt + " Whole-run figures use all " + r.replications + " weeks. Run " + r.run_id + ", " + r.timestamp.replace("T", " ") + ".";
    } else if (S.current) {
      $("#periodText").textContent = "Scenario: " + S.current.name + ". Not simulated yet.";
    }
  }

  function wireContext() {
    $("#scenarioPick").addEventListener("change", (e) => applyScenario(e.target.value).catch(err => showError("#globalError", err)));
    $$(".ms-seg [role=radio]").forEach(b => {
      b.addEventListener("click", () => { S.mode = b.dataset.mode; renderAll(); });
      b.addEventListener("keydown", (e) => {
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
          e.preventDefault(); S.mode = S.mode === "replay" ? "typical" : "replay"; renderAll();
          $(S.mode === "replay" ? "#modeReplay" : "#modeTypical").focus();
        }
      });
    });
    $("#dayPick").addEventListener("change", (e) => { S.day = +e.target.value; renderAll(); });
    $("#timeSlider").addEventListener("input", (e) => { S.slot = +e.target.value; renderTimeDependent(); });
    $("#timePrev").addEventListener("click", () => stepTime(-1));
    $("#timeNext").addEventListener("click", () => stepTime(1));
    $("#timePlay").addEventListener("click", togglePlay);
  }
  function stepTime(dir) {
    const step = S.mode === "typical" ? 4 : 1;
    S.slot = (S.slot + dir * step + STEPS_PER_DAY) % STEPS_PER_DAY;
    renderTimeDependent();
  }
  function togglePlay() {
    const b = $("#timePlay");
    if (S.playing) { clearInterval(S.playing); S.playing = null; b.setAttribute("aria-pressed", "false"); b.textContent = "Play"; return; }
    b.setAttribute("aria-pressed", "true"); b.textContent = "Pause";
    S.playing = setInterval(() => stepTime(1), reducedMotion ? 2000 : 700);
  }

  // ================================================================ overview
  function tile(k, v, unit, scope, sub, cls, extra) {
    return h("div", { class: "ms-tile " + (cls || "") },
      h("p", { class: "k", text: k }),
      h("p", { class: "v" }, v, unit ? h("small", { text: unit }) : null),
      extra || null,
      h("span", { class: "scope", text: scope }),
      sub ? h("p", { class: "s", text: sub }) : null);
  }
  function statusTag(ts) {
    if (!ts || !ts.status) return null;
    const cls = ts.status === "met" ? "met" : ts.status === "not met" ? "not" : "near";
    const icon = cls === "met" ? "✓ " : cls === "not" ? "✗ " : "≈ ";
    return h("span", { class: "ms-status-tag " + cls, text: icon + "Target " + ts.status });
  }
  function sumLast(arr, i, n) { let s = 0; for (let k = Math.max(0, i - n + 1); k <= i; k++) s += arr[k] || 0; return s; }

  function renderOverview() {
    const r = S.result;
    const p = $("#kpiPrimary"), s2 = $("#kpiSecondary");
    if (!r) return;
    const tgt = S.current.inputs.target, ts = r.target_status, sm = r.summary;
    const typ = S.mode === "typical", i = idx(), hr = hourOf(), rp = r.replay, prof = r.profile;
    const when = typ ? "Typical day, " + HHMM(hr * 60) + " (average simulated patients)" : "Simulated day " + (S.day + 1) + ", " + HHMM(viewTime()) + " (one simulated day)";
    const census = typ ? fmt(prof.census_avg[hr], 1) : fmtInt(rp.census[i]);
    const waiting = typ ? fmt(prof.waiting_avg[hr], 1) : fmtInt(rp.waiting[i]);
    const arr = typ ? fmt(prof.arrivals_per_hour[hr], 1) : fmtInt(sumLast(rp.arrivals, i, 4));
    const dep = typ ? fmt(prof.departures_per_hour[hr], 1) : fmtInt(sumLast(rp.departures, i, 4));
    const t4 = ts.value;
    const cls = ts.status === "met" ? "status-met" : ts.status === "not met" ? "status-not" : "status-near";
    p.replaceChildren(
      tile("Patients in the department", census, "", when, "Arrived and not yet left (including SDEC)."),
      tile("Patients waiting", waiting, "", when, "Waiting for streaming, handover, RAT, a space or clinician, diagnostics, results or a decision, a bed or a porter."),
      tile("Completed within " + (tgt.minutes / 60 === Math.round(tgt.minutes / 60) ? (tgt.minutes / 60) + " hours" : tgt.minutes + " minutes"),
        fmt(t4 && t4.mean, 1), "%", "Whole run: " + r.replications + " simulated weeks",
        "Planning target " + tgt.pct + "% (a selected demonstration target). Range across weeks " + fmt(t4 && t4.min, 1) + "–" + fmt(t4 && t4.max, 1) + "%; gap " + fmt(ts.gap_pts, 1) + " percentage points.", cls, statusTag(ts)),
      tile(typ ? "Arrivals and departures per hour" : "Arrivals and departures, hour to " + HHMM(viewTime()),
        arr + " in · " + dep + " out", "", typ ? "Typical day, hour starting " + HHMM(hr * 60) + " (average per day)" : when, "Interval flows, not queue sizes.", "pair"),
      tile("Time in the department (median)", fmt(sm.duration_median && sm.duration_median.mean, 0), " min",
        "Whole run: " + r.replications + " simulated weeks",
        "Arrival to leaving, per patient. Median total waiting " + fmt(sm.total_wait_median && sm.total_wait_median.mean, 0) + " min (each patient's own waiting intervals, added up).")
    );
    const ov = typ ? null : rp.over_target[i];
    s2.replaceChildren(
      tile("Over 12 hours from arrival", fmt(sm.twelve_hour.mean, 1), "%", "Whole run", "Counted from arrival, not from decision to admit."),
      tile("Ambulance handover within 45 min", fmt(sm.handover_45 && sm.handover_45.mean, 1), "%", "Whole run", "Arrival to the start of handover."),
      tile("Left without being seen", fmt(sm.lwbs.mean, 1), "%", "Whole run", "Kept separate from discharges - a guardrail."),
      tile("Unfinished when a week ends", fmt(sm.wip_end.mean, 0), "", "Whole run, per simulated week", "Still in the department after the 12-hour drain - counted as over target, never dropped."),
      tile("Went through SDEC", fmt(sm.sdec_pct.mean, 1), "%", "Whole run", "SDEC time counts inside the ED attendance."),
      typ ? tile("Decisions to admit", fmt(sm.dta_per_day && sm.dta_per_day.mean, 1), " a day", "Whole run (events)", "A decision is an event, not a place - see Patient flow.")
        : tile("In the department longer than " + tgt.minutes + " min", fmtInt(ov), "", when, "Patients present at this moment who arrived more than the target time ago.")
    );
    renderPressure();
    renderCharts();
  }

  function renderPressure() {
    const r = S.result;
    const top = r.pressure.slice(0, 6);
    const mx = Math.max(1, ...top.map(x => x.patient_hours_per_day));
    const groups = Object.fromEntries(S.meta.groups.map(g => [g.id, g.label]));
    const ul = h("ul", { class: "ms-bars" }, top.map(x => {
      const fill = h("span", { class: "fill" });
      fill.style.width = (100 * x.patient_hours_per_day / mx).toFixed(1) + "%";
      return h("li", {},
        h("span", {}, h("strong", { text: x.label }), h("br"), h("span", { class: "ms-hint", text: groups[x.group] || "" })),
        h("span", { class: "track" }, fill),
        h("span", { class: "val", text: fmt(x.patient_hours_per_day, 0) + " patient-hours/day" }));
    }));
    $("#pressureList").replaceChildren(ul, h("p", { class: "ms-hint", text: "Median completed wait at the top stage: " + fmt(top[0] && top[0].completed_median, 0, " min") + ". Values are means across " + r.replications + " simulated weeks." }));
  }

  function renderChartsImpl() {
    const r = S.result;
    if (!r || $("#panel-overview").hidden) return;
    const typ = S.mode === "typical", rp = r.replay, prof = r.profile;
    const c1 = token("--chart-1"), c2 = token("--chart-2"), c3 = token("--chart-3");
    let labels, census, waiting, arr, dep, marker;
    if (typ) {
      labels = [...Array(24).keys()].map(hh => HHMM(hh * 60));
      census = prof.census_avg; waiting = prof.waiting_avg; arr = prof.arrivals_per_hour; dep = prof.departures_per_hour; marker = hourOf();
      $("#dayChartTitle").textContent = "Typical day: average simulated patients by hour";
      $("#dayChartNote").textContent = "Averages over the observed days of one simulated week, sampled every 15 minutes. Arrivals and departures are per hour, divided by the same number of observed days.";
    } else {
      const a = S.day * STEPS_PER_DAY;
      labels = rp.times.slice(a, a + STEPS_PER_DAY + 1).map(t => HHMM(t));
      census = rp.census.slice(a, a + STEPS_PER_DAY + 1); waiting = rp.waiting.slice(a, a + STEPS_PER_DAY + 1); marker = S.slot;
      arr = []; dep = [];
      for (let hh = 0; hh < 24; hh++) { arr.push(sumLast(rp.arrivals, a + (hh + 1) * 4, 4)); dep.push(sumLast(rp.departures, a + (hh + 1) * 4, 4)); }
      $("#dayChartTitle").textContent = "Simulated day " + (S.day + 1) + ": patients in the department and waiting";
      $("#dayChartNote").textContent = "Whole numbers of patients at each 15-minute point of ONE simulated day. The vertical line is the viewing time.";
    }
    lineChart($("#chartCensus"), {
      labels, marker, height: 250, yTitle: "patients",
      series: [{ name: "In the department", values: census, color: c1, fmt: (v) => typ ? v.toFixed(1) : String(v) },
               { name: "Waiting", values: waiting, color: c2, fmt: (v) => typ ? v.toFixed(1) : String(v) }],
      xTick: (i) => (typ ? i % 3 === 0 : i % 12 === 0) ? labels[i] : null,
      tipTitle: (i) => (typ ? "Average at " : "At ") + labels[i],
    });
    $("#chartCensus").setAttribute("aria-label", "Line chart: patients in the department and patients waiting through the day. A table version follows.");
    columnChart($("#chartFlow"), {
      labels: [...Array(24).keys()].map(hh => HHMM(hh * 60)), height: 190, yTitle: typ ? "patients per hour (average)" : "patients per hour",
      series: [{ name: "Arrivals", values: arr, color: c1, fmt: (v) => typ ? v.toFixed(1) : String(v) },
               { name: "Departures", values: dep, color: c3, fmt: (v) => typ ? v.toFixed(1) : String(v) }],
      xTick: (i) => i % 3 === 0 ? HHMM(i * 60) : null, highlight: hourOf(),
      tipTitle: (i) => "Hour " + HHMM(i * 60) + "–" + HHMM((i + 1) * 60),
    });
    $("#chartFlow").setAttribute("aria-label", "Column chart: arrivals and departures per hour. A table version follows.");
    const rows = [];
    for (let hh = 0; hh < 24; hh++) {
      const at = typ ? hh : hh * 4;
      rows.push([HHMM(hh * 60), typ ? fmt(census[hh], 1) : String(census[at]), typ ? fmt(waiting[hh], 1) : String(waiting[at]), typ ? fmt(arr[hh], 1) : String(arr[hh]), typ ? fmt(dep[hh], 1) : String(dep[hh])]);
    }
    $("#dayTable").replaceChildren(table(typ ? "Typical day (averages)" : "Simulated day " + (S.day + 1),
      ["Time", typ ? "In department (average at hh:00)" : "In department at hh:00", typ ? "Waiting (average at hh:00)" : "Waiting at hh:00", "Arrivals in the hour", "Departures in the hour"], rows, [1, 2, 3, 4]));
  }

  // ================================================================ patient flow
  // Control-tower flow maps at three levels, all drawn by flowMap():
  //   * the five summary groups, left to right (the default view);
  //   * one group's areas, opened UNDERNEATH the summary when a group is
  //     selected (the time and scenario stay as they are);
  //   * every modelled step (the expert view).
  // Box numbers are values at the viewing time: one simulated day, or the
  // average at that time of day. Line widths are patients per day moving
  // between boxes over the whole run (result.flows, from the metric layer);
  // the moving dots only show direction and can be paused.
  const FM = { maps: {}, raf: null, last: 0, paused: false };
  const OUTCOME_LABEL = { discharged: "Discharged", admitted: "Admitted (ward transfer complete)", left_without_being_seen: "Left without being seen" };
  const typical = () => S.mode === "typical";

  function kindOf(key) {
    if (!S._kinds) { S._kinds = {}; for (const g of S.meta.groups) for (const st of g.states) S._kinds[st.node + "|" + st.phase] = st.kind; }
    return S._kinds[key];
  }
  function stNow(key) {
    const r = S.result;
    return typical() ? (((r.profile.states_avg || {})[key] || [])[hourOf()] || 0) : (((r.replay.states || {})[key] || [])[idx()] || 0);
  }
  // element-wise sum over the selected day (15-minute steps) or the 24 typical-day averages
  function stDay(keys) {
    const r = S.result, n = typical() ? 24 : STEPS_PER_DAY, a = typical() ? 0 : S.day * STEPS_PER_DAY;
    const out = new Array(n).fill(0);
    for (const k of keys) {
      const s = typical() ? ((r.profile.states_avg || {})[k] || []) : ((r.replay.states || {})[k] || []);
      for (let j = 0; j < n; j++) out[j] += s[a + j] || 0;
    }
    return out;
  }
  function occupancy(keys) {
    let present = 0, waiting = 0;
    for (const k of keys) { const v = stNow(k); present += v; if (kindOf(k) === "waiting") waiting += v; }
    return { present, waiting };
  }
  // events in the hour to the viewing time (one day), or that hour's average per day
  function eventsNow(series, perHour) { return typical() ? ((perHour || [])[hourOf()] || 0) : sumLast(series || [], idx(), 4); }
  function busyStatus(now, series) {
    const peak = Math.max(0, ...series);
    if (peak <= 0) return { cls: "quiet", text: typical() ? "empty at every hour" : "empty all day" };
    const q = now / peak;
    if (q >= 0.8) return { cls: "peak", text: typical() ? "near its usual daily peak" : "near today's peak" };
    if (q >= 0.45) return { cls: "busy", text: "filling" };
    return { cls: "quiet", text: "quiet" };
  }
  const nval = (v) => typical() ? fmt(v, 1) : fmtInt(v);
  const whenText = () => typical() ? "average at " + HHMM(hourOf() * 60) : "at " + HHMM(viewTime());
  const hourText = () => typical() ? "in the hour from " + HHMM(hourOf() * 60) + " (average)" : "in the hour to " + HHMM(viewTime());
  const linkList = (obj) => Object.entries(obj || {}).map(([k, v]) => { const [s, d] = k.split(">"); return { s, d, v }; });
  const keysOf = (states) => states.map(st => typeof st === "string" ? st : st.node + "|" + st.phase);
  const tipRows = (pairs) => pairs.filter(Boolean).map(([name, value]) => ({ name, value: String(value), color: "transparent" }));

  // ------------------------------------------------------------ the renderer
  // spec: {boxes:[{id,col,row,kind,name,content(),onClick?,domId?,controls?,expanded?,flaggable?}],
  //        links:[{s,d,v}], vertical, arch, rowH, stepH, boxW, padA, padX, colWeight(col), flagText, label}
  function flowMap(host, spec) {
    host.replaceChildren();
    host.classList.toggle("fm-vertical", !!spec.vertical);
    host.classList.toggle("fm-compact", !!spec.compact);
    host.classList.toggle("fm-expert", spec.key === "expert");
    const W = Math.max(280, mapWidth(host)), vert = !!spec.vertical;
    const cols = [...new Set(spec.boxes.map(b => b.col))].sort((a, b) => a - b);
    const ci = new Map(cols.map((c, k) => [c, k]));
    const nRows = Math.max(1, ...spec.boxes.map(b => b.row + 1));
    const padA = spec.padA ?? 16, padX = spec.padX ?? 70;
    const uPos = new Map(), colW = new Map();
    let H;
    if (!vert) {
      const wts = cols.map(c => (spec.colWeight ? spec.colWeight(c) : 1)), tot = wts.reduce((a, b) => a + b, 0);
      let acc = 0;
      cols.forEach((c, k) => { const w = (W - 2 * padA) * wts[k] / tot; uPos.set(c, padA + acc + w / 2); colW.set(c, w); acc += w; });
      H = 2 * padX + nRows * spec.rowH;
    } else {
      cols.forEach((c, k) => uPos.set(c, padA + (k + 0.5) * spec.stepH));
      H = 2 * padA + cols.length * spec.stepH;
    }
    const across = (row) => vert ? padX + (row + 0.5) * (W - 2 * padX) / nRows : padX + (row + 0.5) * spec.rowH;
    host.style.height = H + "px";
    const svg = svgEl("svg", { width: W, height: H, class: "fm-svg", "aria-hidden": "true", focusable: "false" });
    host.append(svg);
    const els = new Map(), parts = new Map();
    for (const b of spec.boxes) {
      const u = uPos.get(b.col), v = across(b.row);
      const bw = vert ? Math.min(spec.boxW, (W - 2 * padX) / nRows - 12) : Math.min(spec.boxW, colW.get(b.col) - 16);
      const el = h(b.onClick ? "button" : "div", { type: b.onClick ? "button" : null, class: "fm-box fm-" + b.kind, id: b.domId || null, "aria-controls": b.controls || null });
      el.style.left = (vert ? v : u) + "px"; el.style.top = (vert ? u : v) + "px"; el.style.width = Math.round(bw) + "px";
      const p = { num: h("span", { class: "fm-num" + (b.kind === "group" ? " gnum" : "") }), cap: h("span", { class: "fm-cap" }),
        lines: h("span", { class: "fm-lines" }), status: h("span", { class: "fm-status" }), flag: h("span", { class: "fm-flag", hidden: true }) };
      el.append(h("span", { class: "fm-name", text: b.name }), p.num, p.cap, p.lines, p.status, p.flag);
      if (b.onClick) el.addEventListener("click", b.onClick);
      const enter = () => { highlight(b.id, true); const r = el.getBoundingClientRect(); showTip(r.right - 8, r.top + 4, b.name, b._tip || []); };
      const leave = () => { highlight(b.id, false); hideTip(); };
      el.addEventListener("mouseenter", enter); el.addEventListener("mouseleave", leave);
      el.addEventListener("focus", () => highlight(b.id, true)); el.addEventListener("blur", () => highlight(b.id, false));
      host.append(el);
      els.set(b.id, el); parts.set(b.id, p);
    }
    const linkEls = [];
    function fill() {
      let best = null, bestW = 0;
      for (const b of spec.boxes) {
        const c = b.content(), p = parts.get(b.id), el = els.get(b.id);
        p.num.textContent = c.num ?? "";
        p.cap.textContent = c.cap || "";
        p.lines.replaceChildren(...(c.lines || []).filter(Boolean).map(t => h("span", { text: t })));
        p.status.textContent = c.status ? c.status.text : "";
        p.status.hidden = !c.status;
        el.classList.remove("st-quiet", "st-busy", "st-peak");
        if (c.status) el.classList.add("st-" + c.status.cls);
        b._tip = c.tip || [];
        if (b.expanded) { const on = b.expanded(); el.setAttribute("aria-expanded", on ? "true" : "false"); el.classList.toggle("fm-selected", on); }
        if (b.selected) el.classList.toggle("fm-selected", b.selected());
        if (b.flaggable && (c.waiting || 0) > bestW + 1e-9) { bestW = c.waiting; best = b.id; }
      }
      for (const b of spec.boxes) {
        const p = parts.get(b.id), on = best === b.id;
        p.flag.hidden = !on; p.flag.textContent = on ? spec.flagText : "";
        els.get(b.id).classList.toggle("fm-most", on);
      }
      for (const L of linkEls) for (const d of L.dots) d.el.classList.toggle("hot", !!best && L.l.d === best);
    }
    fill();
    // geometry: u runs along the flow, v across it (swapped when vertical)
    const geo = new Map();
    for (const b of spec.boxes) {
      const el = els.get(b.id), hw = el.offsetWidth / 2, hh = el.offsetHeight / 2;
      geo.set(b.id, { u: uPos.get(b.col), v: across(b.row), hu: vert ? hh : hw, hv: vert ? hw : hh, k: ci.get(b.col) });
    }
    const P = (u, v) => vert ? v.toFixed(1) + " " + u.toFixed(1) : u.toFixed(1) + " " + v.toFixed(1);
    const links = spec.links.filter(l => geo.has(l.s) && geo.has(l.d) && l.s !== l.d && l.v >= (spec.minV ?? 0.05));
    const pairs = new Set(links.map(l => l.s + ">" + l.d));
    const maxV = Math.max(1e-9, ...links.map(l => l.v));
    // arches leave and enter a box's top/bottom edge; spread the attachment points
    // a link arches over (or under) the row only when a box would sit on its straight path
    const blocked = (l, a, b) => {
      for (const [id, g] of geo) {
        if (id === l.s || id === l.d || g.k <= Math.min(a.k, b.k) || g.k >= Math.max(a.k, b.k)) continue;
        const vl = a.v + (g.k - a.k) / (b.k - a.k) * (b.v - a.v);
        if (Math.abs(vl - g.v) < g.hv + 10) return true;
      }
      return false;
    };
    const archOf = (l) => { const a = geo.get(l.s), b = geo.get(l.d), dk = b.k - a.k;
      if (!spec.arch || Math.abs(dk) < 2 || !blocked(l, a, b)) return 0;
      return dk < 0 ? 1 : (b.v > a.v + 5 ? 1 : -1); };
    const attach = new Map();
    for (const l of links) {
      const side = archOf(l);
      if (!side) continue;
      for (const [me, other] of [[l.s, l.d], [l.d, l.s]]) {
        const key = me + "|" + side;
        if (!attach.has(key)) attach.set(key, []);
        attach.get(key).push({ l, other: geo.get(other).u });
      }
    }
    const offset = (id, side, l) => {
      const list = (attach.get(id + "|" + side) || []).slice().sort((x, y) => x.other - y.other);
      const n = list.length, k = list.findIndex(x => x.l === l), g = geo.get(id);
      return n <= 1 ? 0 : (-0.55 + 1.1 * (k + 0.5) / n) * g.hu;
    };
    for (const l of links) {
      const a = geo.get(l.s), b = geo.get(l.d), dk = b.k - a.k, side = archOf(l);
      let d;
      if (side) {
        const v0 = a.v + side * a.hv, v3 = b.v + side * b.hv, u0 = a.u + offset(l.s, side, l), u3 = b.u + offset(l.d, side, l);
        const ext = vert ? W : H;
        const lane = Math.max(6, Math.min(ext - 6, (side > 0 ? Math.max(v0, v3) : Math.min(v0, v3)) + side * (18 + 13 * Math.min(4, Math.abs(dk)))));
        d = `M ${P(u0, v0)} C ${P(u0, lane)}, ${P(u3, lane)}, ${P(u3, v3)}`;
      } else if (dk === 0) {
        const bulge = 40 + Math.abs(b.v - a.v) * 0.15;
        d = `M ${P(a.u + a.hu, a.v)} C ${P(a.u + a.hu + bulge, a.v)}, ${P(b.u + b.hu + bulge, b.v)}, ${P(b.u + b.hu, b.v)}`;
      } else if (Math.abs(dk) === 1 && Math.abs(b.v - a.v) >= (a.hv + b.hv) * 0.6) {
        // neighbouring boxes on different rows (diagnostics below the main line): an elbow
        // out of the facing top/bottom edge, so the way out and the way back stay apart
        const s = Math.sign(b.v - a.v), f = dk;
        const u0 = a.u + f * 0.3 * a.hu, v0 = a.v + s * a.hv;
        const u3 = b.u - f * b.hu, v3 = b.v + (f < 0 ? -s * 0.35 * b.hv : 0);
        d = `M ${P(u0, v0)} C ${P(u0, v3)}, ${P(u0, v3)}, ${P(u3, v3)}`;
      } else {
        const f = dk > 0 ? 1 : -1, off = pairs.has(l.d + ">" + l.s) ? -9 * f : 0;
        const u0 = a.u + f * a.hu, u3 = b.u - f * b.hu, um = (u0 + u3) / 2;
        d = `M ${P(u0, a.v + off)} C ${P(um, a.v + off)}, ${P(um, b.v + off)}, ${P(u3, b.v + off)}`;
      }
      const w = 1.5 + 11 * Math.sqrt(l.v / maxV);
      const path = svgEl("path", { d, class: "fm-link", "stroke-width": w.toFixed(1), fill: "none", "data-s": l.s, "data-d": l.d });
      svg.append(path);
      linkEls.push({ l, path, w, dots: [], pts: [], len: 1 });
    }
    const name = (id) => (spec.boxes.find(b => b.id === id) || {}).name || id;
    for (const L of linkEls) {   // wide invisible hover targets, above the drawn lines
      const hit = svgEl("path", { d: L.path.getAttribute("d"), class: "fm-hit", "stroke-width": Math.max(14, L.w + 6).toFixed(1), fill: "none" });
      hit.addEventListener("mousemove", (e) => {
        L.path.classList.add("on");
        showTip(e.clientX, e.clientY, name(L.l.s) + " → " + name(L.l.d), tipRows([["patients a day moving along this route (whole-run average)", fmt(L.l.v, 1)]]));
      });
      hit.addEventListener("mouseleave", () => { L.path.classList.remove("on"); hideTip(); });
      svg.append(hit);
    }
    for (const L of linkEls) {
      L.len = Math.max(1, L.path.getTotalLength());
      const N = Math.max(16, Math.round(L.len / 6));
      for (let j = 0; j <= N; j++) { const q = L.path.getPointAtLength(L.len * j / N); L.pts.push([q.x, q.y]); }
      const n = L.l.v >= 0.2 ? Math.max(1, Math.min(8, Math.round(1 + 7 * L.l.v / maxV), Math.floor(L.len / 24))) : 0;
      for (let j = 0; j < n; j++) {
        const c = svgEl("circle", { r: 3.2, class: "fm-dot" });
        svg.append(c);
        const dot = { el: c, ph: (j + 0.5) / n };
        L.dots.push(dot); placeDot(L, dot);
      }
    }
    function highlight(id, on) {
      for (const L of linkEls) {
        const touch = on && (L.l.s === id || L.l.d === id);
        L.path.classList.toggle("on", touch);
        L.path.classList.toggle("dim", on && !touch);
      }
    }
    fill();
    const map = { links: linkEls, update: fill };
    FM.maps[spec.key] = map;
    fmStart();
    return map;
  }
  // the width a map can use: its own box, or its container's while it is still empty
  function mapWidth(host) { return host.clientWidth || (host.parentElement && host.parentElement.clientWidth) || 1000; }
  function placeDot(L, d) {
    const q = L.pts[Math.min(L.pts.length - 1, Math.floor(d.ph * (L.pts.length - 1)))];
    if (q) { d.el.setAttribute("cx", q[0].toFixed(1)); d.el.setAttribute("cy", q[1].toFixed(1)); }
  }
  function fmTick(now) {
    FM.raf = null;
    const panel = $("#panel-flow");
    if (!panel || panel.hidden || FM.paused || reducedMotion) return;
    const dt = FM.last ? Math.min(0.1, (now - FM.last) / 1000) : 0;
    FM.last = now;
    for (const m of Object.values(FM.maps)) for (const L of m.links) {
      if (!L.dots.length || !L.path.isConnected) continue;
      const step = dt * 55 / L.len;
      for (const d of L.dots) { d.ph = (d.ph + step) % 1; placeDot(L, d); }
    }
    FM.raf = requestAnimationFrame(fmTick);
  }
  function fmStart() {
    if (!FM.raf && !FM.paused && !reducedMotion) { FM.last = 0; FM.raf = requestAnimationFrame(fmTick); }
  }
  function wireFlowControls() {
    const b = $("#flowPause");
    if (reducedMotion) { b.disabled = true; b.textContent = "Movement off (reduced motion)"; return; }
    b.addEventListener("click", () => {
      FM.paused = !FM.paused;
      b.setAttribute("aria-pressed", FM.paused ? "true" : "false");
      b.textContent = FM.paused ? "Resume movement" : "Pause movement";
      if (!FM.paused) fmStart();
    });
  }

  // ------------------------------------------------------------ box contents
  function groupContent(g) {
    const r = S.result, keys = keysOf(g.states).filter(k => (r.replay.states || {})[k] || (r.profile.states_avg || {})[k]);
    let present, waiting, el = null;
    if (typical()) ({ present, waiting } = occupancy(keys));
    else { const gr = r.replay.groups[g.id]; present = gr.present[idx()]; waiting = gr.waiting[idx()];
      if (gr.elapsed_max[idx()] !== null) el = { med: gr.elapsed_median[idx()], max: gr.elapsed_max[idx()] }; }
    const gs = r.stages.groups[g.id] || {};
    const entering = typical() ? null : sumLast(r.replay.groups[g.id].entries, idx(), 4);
    return { num: nval(present), cap: (typical() ? "average present at " : "present at ") + HHMM(typical() ? hourOf() * 60 : viewTime()),
      lines: [nval(waiting) + (typical() ? " waiting on average" : " waiting") + (el ? " · longest " + el.max + " min" : "")],
      status: busyStatus(present, stDay(keys)), waiting,
      tip: tipRows([["present " + whenText(), nval(present)], ["waiting " + whenText(), nval(waiting)],
        el ? ["longest current wait (median " + el.med + " min)", el.max + " min"] : null,
        entering !== null ? ["came into this group in the hour before", entering] : null,
        ["waiting patient-hours per day (whole run)", fmt(gs.waiting_patient_hours_per_day, 0)],
        ["patients entering per day (whole run)", fmt(gs.entries_per_day, 0)]]) };
  }
  function arrivalsContent() {
    const r = S.result, n = typical() ? r.profile.arrivals_per_hour[hourOf()] : sumLast(r.replay.arrivals, idx(), 4);
    const perDay = linkList(r.flows.group).filter(l => l.s === "arrival").reduce((a, l) => a + l.v, 0);
    return { num: nval(n), cap: "arrived " + hourText(), lines: [fmt(perDay, 0) + " a day (whole run)"],
      tip: tipRows([["arrivals " + hourText(), nval(n)], ["arrivals per day (whole run)", fmt(perDay, 1)]]) };
  }
  function outcomeNodes(summary) {
    const present = new Set(S.result.model.nodes);
    return S.meta.outcomes.filter(o => o.summary === summary && present.has(o.node));
  }
  function outcomeContent(summary) {
    const r = S.result, nodes = outcomeNodes(summary);
    const n = nodes.reduce((a, o) => a + eventsNow((r.replay.departures_by_outcome || {})[o.node], (r.profile.departures_by_outcome_per_hour || {})[o.node]), 0);
    const perDay = linkList(r.flows.group).filter(l => l.d === summary).reduce((a, l) => a + l.v, 0);
    const sub = nodes.map(o => [o.label + " (a day)", fmt(linkList(r.flows.unit).filter(l => l.d === o.node).reduce((a, l) => a + l.v, 0), 1)]);
    return { num: nval(n), cap: "left " + hourText(), lines: [fmt(perDay, 0) + " a day (whole run)"],
      tip: tipRows([["left " + hourText(), nval(n)], ["per day (whole run)", fmt(perDay, 1)], ...sub]) };
  }
  function unitKeys(u) { return (u.states || []).filter(k => (S.result.replay.states || {})[k] !== undefined || (S.result.profile.states_avg || {})[k] !== undefined); }
  function unitContent(u) {
    const r = S.result, um = (r.stages.units || {})[u.id] || {};
    if (u.milestone) {
      const n = eventsNow((r.replay.milestones || {})[u.milestone], (r.profile.milestones_per_hour || {})[u.milestone]);
      return { num: nval(n), cap: "decisions " + hourText(), lines: ["an event, not a place · " + fmt(um.entries_per_day, 1) + " a day"],
        tip: tipRows([["decisions " + hourText(), nval(n)], ["decisions per day (whole run)", fmt(um.entries_per_day, 1)]]) };
    }
    const keys = unitKeys(u), o = occupancy(keys);
    const stay = um.stay_median !== null && um.stay_median !== undefined ? "usual stay " + fmt(um.stay_median, 0) + " min" : null;
    return { num: nval(o.present), cap: (typical() ? "average present at " : "present at ") + HHMM(typical() ? hourOf() * 60 : viewTime()),
      lines: [nval(o.waiting) + (typical() ? " waiting on average" : " waiting") + (stay ? " · " + stay : "")], status: busyStatus(o.present, stDay(keys)), waiting: o.waiting,
      tip: tipRows([["present " + whenText(), nval(o.present)], ["waiting " + whenText(), nval(o.waiting)],
        ["time here, median / 90th percentile (completed stays, whole run)", um.stay_median !== null && um.stay_median !== undefined ? fmt(um.stay_median, 0) + " / " + fmt(um.stay_p90, 0) + " min" : "not available"],
        ["waiting patient-hours per day (whole run)", fmt(um.waiting_patient_hours_per_day, 0)],
        ["patients entering per day (whole run)", fmt(um.entries_per_day, 0)]]) };
  }

  // ------------------------------------------------------------ the three maps
  function buildSummaryMap(host) {
    const vertical = mapWidth(host) < 760, mid = vertical ? 0 : 1;
    const boxes = [{ id: "arrival", col: 0, row: mid, kind: "source", name: "Arrivals", content: arrivalsContent }];
    for (const g of S.meta.groups) boxes.push({ id: g.id, col: g.order, row: g.id === "diagnostics" && !vertical ? 2 : mid, kind: "group", domId: "grp-" + g.id, controls: "groupDetail",
      name: g.order + ". " + g.label, content: () => groupContent(g), onClick: () => toggleGroup(g.id), expanded: () => S.openGroup === g.id, flaggable: true });
    ["discharged", "admitted", "left_without_being_seen"].forEach((o, k) =>
      boxes.push({ id: o, col: vertical ? 6 + k : 6, row: vertical ? 0 : k, kind: "outcome outcome-" + o, name: OUTCOME_LABEL[o], content: () => outcomeContent(o) }));
    return flowMap(host, { key: "summary", boxes, links: linkList(S.result.flows.group), vertical, arch: true,
      rowH: 128, stepH: 165, boxW: vertical ? 300 : 196, padX: vertical ? 56 : 64, colWeight: c => c === 0 ? 0.8 : c === 6 ? 1.05 : 1,
      flagText: typical() ? "Most waiting at this time (average)" : "Most waiting now" });
  }

  // a group's areas, with the groups and outcomes they connect to as stubs
  function buildDetailMap(host, g) {
    const r = S.result, gorder = Object.fromEntries(S.meta.groups.map(x => [x.id, x.order]));
    const units = detailUnits(g);
    const unitGroup = Object.fromEntries(S.meta.flow_units.map(u => [u.id, u.group]));
    const mine = new Set(units.map(u => u.id));
    const outLabel = Object.fromEntries(S.meta.outcomes.map(o => [o.node, o.label]));
    const stubs = new Map(), agg = new Map();
    const stubFor = (id, dir) => {
      if (mine.has(id)) return id;
      let key, label, side;
      if (id === "arrival") { key = "ext:arrival"; label = "Arrivals"; side = "left"; }
      else if (outLabel[id]) { key = "out:" + id; label = outLabel[id]; side = "right"; }
      else { const og = unitGroup[id]; if (!og) return null;
        const G = S.meta.groups.find(x => x.id === og); side = gorder[og] < g.order ? "left" : "right";
        key = "ext:" + og + ":" + side; label = (dir === "in" ? "From " : "To ") + G.order + ". " + G.label;
        if (stubs.has(key) && stubs.get(key).label !== label) stubs.get(key).label = G.order + ". " + G.label + " (to and from)"; }
      if (!stubs.has(key)) stubs.set(key, { key, label, side, dir });
      return key;
    };
    for (const l of linkList(r.flows.unit)) {
      if (!mine.has(l.s) && !mine.has(l.d)) continue;
      const s = stubFor(l.s, "in"), d = stubFor(l.d, "out");
      if (!s || !d || s === d) continue;
      agg.set(s + ">" + d, (agg.get(s + ">" + d) || 0) + l.v);
    }
    const links = [...agg.entries()].map(([k, v]) => { const [s, d] = k.split(">"); return { s, d, v }; });
    const maxCol = Math.max(0, ...units.map(u => u.col)), nRows = Math.max(1, ...units.map(u => Math.ceil(u.row) + 1));
    const boxes = units.map(u => ({ id: u.id, col: u.col, row: u.row, kind: u.milestone ? "milestone" : "unit", name: u.label,
      content: () => unitContent(u), onClick: () => openUnit(u.id), selected: () => S.openUnit === u.id, flaggable: !u.milestone }));
    for (const side of ["left", "right"]) {
      const rowOf = Object.fromEntries(units.map(u => [u.id, u.row]));
      const meanRow = (key) => { let sw = 0, sv = 0; for (const l of links) { const o = l.s === key ? l.d : l.d === key ? l.s : null;
        if (o !== null && rowOf[o] !== undefined) { sw += l.v; sv += l.v * rowOf[o]; } } return sw ? sv / sw : 0; };
      const list = [...stubs.values()].filter(s => s.side === side).sort((a, b) => meanRow(a.key) - meanRow(b.key));
      list.forEach((s, k) => {
        const flowsIn = links.filter(l => l.s === s.key).reduce((a, l) => a + l.v, 0), flowsOut = links.filter(l => l.d === s.key).reduce((a, l) => a + l.v, 0);
        boxes.push({ id: s.key, col: side === "left" ? -1 : maxCol + 1, row: list.length === 1 ? (nRows - 1) / 2 : k * (nRows - 1) / Math.max(1, list.length - 1),
          kind: s.key.startsWith("out:") ? "stub fm-stub-out" : "stub", name: s.label,
          content: () => ({ lines: [flowsIn > 0.05 ? fmt(flowsIn, 1) + " a day into this group" : null, flowsOut > 0.05 ? fmt(flowsOut, 1) + " a day from this group" : null],
            tip: tipRows([flowsIn > 0.05 ? ["patients a day coming into " + g.label + " (whole run)", fmt(flowsIn, 1)] : null,
              flowsOut > 0.05 ? ["patients a day going here from " + g.label + " (whole run)", fmt(flowsOut, 1)] : null]) }) });
      });
    }
    return flowMap(host, { key: "detail", boxes, links, vertical: false, arch: false, compact: true, rowH: 112, padX: 26, boxW: 210,
      colWeight: c => (c < 0 || c > maxCol) ? 0.8 : 1, flagText: typical() ? "Most waiting in this group (average)" : "Most waiting in this group now" });
  }

  function buildExpertMap(host) {
    const r = S.result, ng = S.meta.node_groups, gorder = Object.fromEntries(S.meta.groups.map(x => [x.id, x.order]));
    const labels = S.meta.labels, nodeStates = {};
    for (const g of S.meta.groups) for (const st of g.states) (nodeStates[st.node] = nodeStates[st.node] || []).push(st.node + "|" + st.phase);
    const msNodes = new Set(S.meta.milestones.map(m => m.node));
    const byCol = {};
    for (const n of r.model.pathway) {
      const col = n.type === "source" ? 0 : n.type === "sink" ? 6 : gorder[ng[n.id]];
      if (col === undefined) continue;
      (byCol[col] = byCol[col] || []).push(n);
    }
    const boxes = [];
    for (const [col, list] of Object.entries(byCol)) list.forEach((n, k) => {
      const c = Number(col);
      boxes.push({ id: n.id, col: c, row: k, kind: n.type === "sink" ? "outcome" : n.type === "source" ? "source" : msNodes.has(n.id) ? "milestone" : "unit",
        name: n.type === "source" ? "Arrivals" : labels[n.id] || n.id, flaggable: n.type === "process" && !msNodes.has(n.id),
        content: () => {
          if (n.type === "source") return arrivalsContent();
          if (n.type === "sink") { const v = eventsNow((r.replay.departures_by_outcome || {})[n.id], (r.profile.departures_by_outcome_per_hour || {})[n.id]);
            return { num: nval(v), cap: "left " + hourText(), tip: tipRows([["left " + hourText(), nval(v)]]) }; }
          if (msNodes.has(n.id)) { const v = eventsNow((r.replay.milestones || {})[n.id], (r.profile.milestones_per_hour || {})[n.id]);
            return { num: nval(v), cap: "decisions " + hourText(), tip: tipRows([["decisions or routings " + hourText(), nval(v)]]) }; }
          const o = occupancy(nodeStates[n.id] || []);
          return { num: nval(o.present), cap: nval(o.waiting) + " waiting", waiting: o.waiting, status: busyStatus(o.present, stDay(nodeStates[n.id] || [])),
            tip: tipRows([["present " + whenText(), nval(o.present)], ["waiting " + whenText(), nval(o.waiting)]]) };
        } });
    });
    return flowMap(host, { key: "expert", boxes, links: linkList(r.flows.node), vertical: false, arch: false, compact: true, rowH: 96,
      padX: 24, boxW: 168, colWeight: () => 1, flagText: "Most waiting now" });
  }

  // ------------------------------------------------------------ orchestration
  function renderFlow() {
    const r = S.result;
    if (!r || !S.meta) return;
    const panel = $("#panel-flow");
    if (panel.hidden) { S.flowKey = null; return; }          // drawn when shown (it needs its width)
    if (!r.flows) { $("#groupRow").replaceChildren(h("p", { class: "ms-warning", text: "This result was produced before the flow maps existed. Simulate the scenario again to draw them." })); return; }
    const host = $("#groupRow");
    const wide = mapWidth(host) >= 760;
    const key = [r.run_id, S.mode, wide ? "h" : "v", Math.round(mapWidth(host) / 40)].join("|");
    $("#flowLegend").textContent = (typical()
      ? "Boxes: AVERAGE simulated patients at the selected time of day across the whole run. "
      : "Boxes: whole numbers of patients at the viewing time on simulated day " + (S.day + 1) + ". ")
      + "Lines: patients a day moving between groups over the whole run (thicker = more); the dots only show direction. "
      + "Top border and the word under the number: how full the box is compared with its own busiest moment of the "
      + (typical() ? "typical day." : "day.") + " Arrivals and the outcome boxes count people in an hour, not people waiting.";
    if (S.flowKey !== key) { S.flowKey = key; S.detailKey = null; FM.maps = {}; buildSummaryMap(host); }
    else FM.maps.summary && FM.maps.summary.update();
    renderSummaryTable();
    renderGroupDetail();
    renderOutcomes();
    renderExpert();
  }

  function renderSummaryTable() {
    const r = S.result, name = (id) => id === "arrival" ? "Arrivals" : OUTCOME_LABEL[id] || ((S.meta.groups.find(g => g.id === id) || {}).label) || id;
    const rows = linkList(r.flows.group).sort((a, b) => b.v - a.v).map(l => [name(l.s), name(l.d), fmt(l.v, 1)]);
    const now = S.meta.groups.map(g => { const c = groupContent(g); return [g.order + ". " + g.label, c.num, c.lines[0], c.status.text]; });
    $("#flowTable").replaceChildren(
      table((typical() ? "Average at " + HHMM(hourOf() * 60) : "At " + HHMM(viewTime()) + ", simulated day " + (S.day + 1)), ["Group", "Present", "Waiting", "Compared with its busiest moment"], now, [1]),
      table("Patients moving between groups (whole run, a day)", ["From", "To", "Patients a day"], rows, [2]));
  }

  function toggleGroup(id) {
    S.openGroup = S.openGroup === id ? null : id;
    S.openUnit = null;
    renderFlow();
    if (S.openGroup) $("#groupDetail").focus(); else { const b = $("#grp-" + id); if (b) b.focus(); }
  }
  function openUnit(id) {
    S.openUnit = S.openUnit === id ? null : id;
    if (FM.maps.detail) FM.maps.detail.update();
    renderGroupDetail();
    if (S.openUnit) { const d = $("#unitDrill"); if (d) d.focus(); }
  }

  function renderGroupDetail() {
    const box = $("#groupDetail");
    const g = S.meta.groups.find(x => x.id === S.openGroup);
    if (!g || !S.result || !S.result.flows) { box.hidden = true; box.replaceChildren(); S.detailKey = null; delete FM.maps.detail; return; }
    const r = S.result;
    box.hidden = false;
    const narrow = box.clientWidth < 640;
    const key = [S.flowKey, g.id, narrow].join("|");
    if (S.detailKey === key && (narrow || FM.maps.detail)) {
      if (narrow) renderDetailCards($("#detailMap"), g); else FM.maps.detail.update();
      $("#detailWhen").textContent = detailWhen();
      renderUnitDrill(); renderDetailTables(g);
      return;
    }
    S.detailKey = key;
    const close = h("button", { class: "ms-btn-secondary", type: "button", text: "Close " + g.label });
    close.addEventListener("click", () => toggleGroup(g.id));
    const mapHost = h("div", { class: narrow ? "fm-cards" : "fm-map fm-detail-map", id: "detailMap", role: "group", "aria-label": "Areas inside " + g.label + ": patients present and the routes between them" });
    box.replaceChildren(...[
      h("div", { class: "ms-detail-head" }, h("div", {}, h("h3", { text: g.order + ". " + g.label }), h("p", { class: "ms-hint", text: g.description }),
        h("p", { class: "ms-hint", id: "detailWhen", text: detailWhen() })), close),
      mapHost,
      h("p", { class: "ms-hint", text: "Select an area to see its day, what serves it, and where its patients come from and go to. Boxes on the left and right are the other groups and the outcomes this group connects to; the figures on them are patients a day over the whole run." }),
      h("div", { id: "unitDrill", class: "fm-drill", tabindex: "-1", hidden: true }),
      g.id === "treatment" ? h("p", { class: "ms-info", text: S.meta.sdec.reporting_note + " " + S.meta.sdec.selection_caveat }) : null,
      g.id === "next_destination" ? h("p", { class: "ms-info", text: "The admission sequence is: decision to admit (an event) → waiting for an inpatient bed (patients still occupy their ED trolley) → transfer to the ward → departure. " + S.meta.downstream.aggregate_assumption }) : null,
      h("details", { class: "ms-details", id: "detailTables" }, h("summary", { text: "Table view: every step in " + g.label }), h("div", { id: "detailTablesBody" }))].filter(Boolean));
    if (!narrow) buildDetailMap(mapHost, g);
    else { delete FM.maps.detail; renderDetailCards(mapHost, g); }
    renderUnitDrill(); renderDetailTables(g);
  }
  // narrow screens: the same areas as cards (no lines); routes are in each area's detail
  function detailUnits(g) {
    const present = new Set(S.result.model.nodes);
    return S.meta.flow_units.filter(u => u.group === g.id && (u.milestone ? present.has(u.milestone) : u.states.some(k => present.has(k.split("|")[0]))));
  }
  function renderDetailCards(host, g) {
    host.replaceChildren(...detailUnits(g).map(u => {
      const c = unitContent(u);
      const b = h("button", { type: "button", class: "fm-box fm-card fm-" + (u.milestone ? "milestone" : "unit") + (c.status ? " st-" + c.status.cls : "") + (S.openUnit === u.id ? " fm-selected" : "") },
        h("span", { class: "fm-name", text: u.label }), h("span", { class: "fm-num", text: c.num }), h("span", { class: "fm-cap", text: c.cap }),
        h("span", { class: "fm-lines" }, ...(c.lines || []).filter(Boolean).map(x => h("span", { text: x }))),
        c.status ? h("span", { class: "fm-status", text: c.status.text }) : null);
      b.addEventListener("click", () => openUnit(u.id));
      return b;
    }));
  }
  function detailWhen() {
    return typical() ? "Showing the typical day at " + HHMM(hourOf() * 60) + " (averages across the whole run)."
      : "Showing simulated day " + (S.day + 1) + " at " + HHMM(viewTime()) + " (the same time as the summary above).";
  }

  // the drill-down for one area: its day, who serves it, where patients come from and go to
  function renderUnitDrill() {
    const box = $("#unitDrill");
    if (!box) return;
    const u = S.meta.flow_units.find(x => x.id === S.openUnit);
    if (!u || !S.result) { box.hidden = true; box.replaceChildren(); return; }
    const r = S.result, um = (r.stages.units || {})[u.id] || {}, c = unitContent(u);
    const close = h("button", { class: "ms-btn-secondary", type: "button", text: "Close " + u.label });
    close.addEventListener("click", () => openUnit(u.id));
    const chart = h("div", { class: "ms-chart", id: "unitChart", role: "img" });
    const unitName = (id) => id === "arrival" ? "Arrivals" : ((S.meta.flow_units.find(x => x.id === id) || {}).label) || ((S.meta.outcomes.find(o => o.node === id) || {}).label) || id;
    const flows = linkList(r.flows.unit);
    const inn = flows.filter(l => l.d === u.id).sort((a, b) => b.v - a.v), out = flows.filter(l => l.s === u.id).sort((a, b) => b.v - a.v);
    const nodes = u.milestone ? [] : [...new Set(unitKeys(u).map(k => k.split("|")[0]))];
    const how = Math.floor((viewTime() % 10080) / 60), resRows = [], seen = new Set();
    for (const n of nodes) for (const res of (r.model.node_resources[n] || [])) {
      if (seen.has(res)) continue; seen.add(res);
      const oc = r.model.open_capacity[res], ut = (r.stages.utilisation[res] || {}).utilisation;
      const isStaff = !!Object.values(S.meta.roles).some(ro => ro.staffs === res);
      resRows.push([labelFor(res), isStaff ? "staff on shift" : "spaces open", oc ? String(oc.week[how]) : "–", fmt(ut, 0, "%")]);
    }
    box.replaceChildren(...[
      h("div", { class: "ms-detail-head" }, h("h4", { text: u.label }), close),
      h("div", { class: "fm-drill-stats" },
        ...(c.tip || []).map(t => h("div", { class: "fm-stat" }, h("span", { class: "k", text: t.name }), h("span", { class: "v", text: t.value })))),
      u.milestone ? null : h("h5", { text: typical() ? "Through the typical day (average present at each hour)" : "Through simulated day " + (S.day + 1) + " (present on the hour)" }),
      u.milestone ? null : chart,
      resRows.length ? table("What serves this area at " + HHMM(viewTime()) + " (" + DAYNAMES[Math.floor((viewTime() % 10080) / 1440)] + ")", ["Resource", "Type", "Available now", "Utilisation (whole run)"], resRows, [2, 3]) : null,
      h("div", { class: "fm-drill-flows" },
        h("div", {}, h("h5", { text: "Patients come from" }), h("ul", { class: "ms-list" }, inn.length ? inn.map(l => h("li", { text: unitName(l.s) + ": " + fmt(l.v, 1) + " a day" })) : [h("li", { text: "none in this run" })])),
        h("div", {}, h("h5", { text: "And go on to" }), h("ul", { class: "ms-list" }, out.length ? out.map(l => h("li", { text: unitName(l.d) + ": " + fmt(l.v, 1) + " a day" })) : [h("li", { text: "none in this run" })])))].filter(Boolean));
    box.hidden = false;
    if (!u.milestone) {
      const keys = unitKeys(u), day = stDay(keys);
      const vals = typical() ? day : [...Array(24).keys()].map(hh => day[hh * 4]);
      columnChart(chart, { labels: [...Array(24).keys()].map(hh => HHMM(hh * 60)), height: 150, yTitle: "patients present",
        series: [{ name: "Present", values: vals, color: token("--chart-1"), fmt: (v) => typical() ? fmt(v, 1) : String(v) }],
        xTick: (i) => i % 3 === 0 ? HHMM(i * 60) : null, highlight: hourOf(), tipTitle: (i) => HHMM(i * 60) });
      chart.setAttribute("aria-label", "Column chart: patients present in " + u.label + " at each hour. The table view below lists the same steps.");
    }
  }

  function renderDetailTables(g) {
    const body = $("#detailTablesBody");
    if (!body) return;
    const r = S.result, typ = typical(), i = idx();
    const present = new Set(r.model.nodes);
    // a step that uses no resource has no queue (its "queue" is always zero length)
    const states = g.states.filter(st => present.has(st.node) &&
      !(st.phase === "queue" && !(r.model.node_resources[st.node] || []).length));
    const rows = states.map(st => {
      const key = st.node + "|" + st.phase, sm = r.stages.states[key] || {};
      return [st.label, h("span", { class: "ms-kind " + st.kind, text: st.kind === "waiting" ? "Waiting" : "Being seen / in progress" }),
        typ ? fmt(stNow(key), 1) : String(stNow(key)), fmt(sm.mean_occupancy, 1), st.kind === "waiting" ? fmt(sm.patient_hours_per_day, 0) : "–",
        sm.n_completed ? fmt(sm.completed_median, 0) + " / " + fmt(sm.completed_p90, 0) : "no observations", fmt(sm.entries_per_day, 1)];
    });
    const parts = [table(null, ["Step", "Kind", typ ? "Average at " + HHMM(hourOf() * 60) : "Now (" + HHMM(viewTime()) + ")", "Average present (whole run)", "Waiting patient-hours/day", "Time in step, minutes: median / 90th percentile (completed)", "Entries per day"], rows, [2, 3, 4, 5, 6])];
    const nodes = [...new Set(states.map(s => s.node))], resRows = [], seen = new Set();
    const how = Math.floor((viewTime() % 10080) / 60);
    for (const n of nodes) for (const res of (r.model.node_resources[n] || [])) {
      if (seen.has(res)) continue; seen.add(res);
      const oc = r.model.open_capacity[res], ph = r.model.physical_capacity[res], ut = (r.stages.utilisation[res] || {}).utilisation;
      const isStaff = !!(S.meta.roles && Object.values(S.meta.roles).some(ro => ro.staffs === res));
      resRows.push([labelFor(res), isStaff ? "Staff (on shift)" : "Space / equipment (open)", oc ? String(oc.week[how]) : "–", ph && !isStaff ? String(ph.max) : "–", fmt(ut, 0, "%")]);
    }
    if (resRows.length) parts.push(h("h4", { text: "What serves these steps" }),
      table(null, ["Resource", "Type", "Available at " + HHMM(viewTime()) + " (" + DAYNAMES[Math.floor((viewTime() % 10080) / 1440)] + ")", "Physical spaces", "Utilisation (whole run)"], resRows, [2, 3, 4]),
      h("p", { class: "ms-hint", text: "A space only opens when the staff to cover it are on shift (the space-staffing ratios on the Workforce screen). Utilisation alone does not make a bottleneck - compare it with the waiting measures above." }));
    const ms = S.meta.milestones.filter(m => m.group === g.id && (r.replay.milestones || {})[m.node]);
    if (ms.length) parts.push(h("h4", { text: "Decisions and events (counted, not occupancy)" }),
      table(null, ["Event", typ ? "In the hour from " + HHMM(hourOf() * 60) + " (average)" : "In the hour to " + HHMM(viewTime()), "Per day (whole run)"],
        ms.map(m => [m.label, typ ? fmt(((r.profile.milestones_per_hour || {})[m.node] || [])[hourOf()], 1) : String(sumLast(r.replay.milestones[m.node], i, 4)), fmt(r.stages.milestones_per_day[m.node], 1)]), [1, 2]));
    body.replaceChildren(...parts);
  }

  function labelFor(res) {
    const known = { cubicle: "Majors cubicles", resus_bay: "Resus bays", fit_to_sit_chair: "Fit-to-sit spaces", utc_room: "UTC rooms",
      sdec_chair: "SDEC chairs", handover_bay: "Ambulance handover bays", ct_scanner: "CT scanners", xray_room: "X-ray rooms", fau_bed: "Frailty unit beds" };
    if (known[res]) return known[res];
    const role = Object.values(S.meta.roles).find(ro => ro.staffs === res);
    return role ? role.staffs_label : res.replace(/_/g, " ");
  }

  function renderOutcomes() {
    const r = S.result, typ = S.mode === "typical", i = idx();
    const present = new Set(r.model.nodes);
    const op = {};
    for (const rep of r.reps) for (const [k, v] of Object.entries(rep.outcomes_per_day || {})) op[k] = (op[k] || 0) + v / r.reps.length;
    const groups = { discharged: [], admitted: [], left_without_being_seen: [] };
    for (const o of S.meta.outcomes) if (present.has(o.node)) groups[o.summary].push(o);
    const tileFor = (title, list, note) => {
      const perDay = list.reduce((a, o) => a + (op[o.node] || 0), 0);
      const inHour = list.reduce((a, o) => a + sumLast(r.replay.departures_by_outcome[o.node] || [], i, 4), 0);
      const sub = list.map(o => o.label + ": " + fmt(op[o.node] || 0, 1) + " a day").join(" · ");
      return tile(title, fmt(perDay, 1), " a day", "Whole run (completed departures)" + (typ ? "" : " · " + inHour + " in the hour to " + HHMM(viewTime())), sub + (note ? " " + note : ""));
    };
    $("#outcomeRow").replaceChildren(
      tileFor("Discharged", groups.discharged, ""),
      tileFor("Admitted (transfer complete)", groups.admitted, "Counted when the ward transfer is complete, not at the decision."),
      tileFor("Left without being seen", groups.left_without_being_seen, "Not a successful discharge."));
  }

  function renderExpert() {
    const r = S.result, det = $("#expertView"), host = $("#expertMap");
    if (!det.open || !r.flows) { delete FM.maps.expert; S.expertKey = null; return; }
    if (mapWidth(host) >= 900) {
      $("#expertNote").textContent = "Every modelled step, in the column of its summary group. Decision and routing points (dashed) count events in the hour; outcomes count departures. Lines are patients a day over the whole run.";
      if (S.expertKey !== S.flowKey || !FM.maps.expert) { S.expertKey = S.flowKey; buildExpertMap(host); }
      else FM.maps.expert.update();
    } else {
      delete FM.maps.expert; S.expertKey = null; host.replaceChildren(); host.style.height = "";
      $("#expertNote").textContent = "The full map needs a wider screen. Every step and its routes are listed in the table below.";
    }
    if (S.expertTable === r.run_id) return;
    S.expertTable = r.run_id;
    const labels = S.meta.labels, name = (id) => labels[id] || id;
    const rows = r.model.pathway.map(n => [name(n.id), n.type === "sink" ? "outcome" : n.milestone ? "decision (event)" : "step",
      (n.resources || []).map(labelFor).join(", ") || "–",
      n.open_hours ? HHMM(n.open_hours[0] * 60) + "–" + HHMM(n.open_hours[1] * 60) + " (closed: " + name(n.closed_fallback) + ")" : "always",
      n.routes.map(rt => rt.when + ": " + rt.to.map(([t, p]) => name(t) + " " + Math.round(p * 1000) / 10 + "%").join(", ")).join(" | ") || "–"]);
    $("#expertTable").replaceChildren(table("Every modelled step, its resources and its onward routes", ["Step", "Kind", "Uses", "Open", "Goes to"], rows));
  }

  // ================================================================ render orchestration
  function renderAllEmpty() {
    for (const id of ["#kpiPrimary", "#kpiSecondary", "#pressureList", "#groupRow", "#outcomeRow", "#chartCensus", "#chartFlow", "#flowTable", "#expertMap"]) $(id).replaceChildren();
    $("#groupRow").style.height = ""; $("#expertMap").style.height = "";
    $("#groupDetail").hidden = true;
    S.flowKey = null; S.detailKey = null; S.expertKey = null; FM.maps = {};
  }
  function renderNotSimulated() {
    renderAllEmpty();
    renderContext();
    const btn = h("button", { class: "ms-btn", type: "button", text: "Simulate this scenario" });
    btn.addEventListener("click", simulateApplied);
    $("#kpiPrimary").replaceChildren(h("div", { class: "ms-warning" }, h("p", { text: "\"" + S.current.name + "\" has not been simulated with these inputs yet, so there are no results to show. Nothing old is shown in their place." }), btn));
    $("#groupRow").replaceChildren(h("p", { class: "ms-hint", text: "Simulate the scenario to see patient flow." }));
  }
  function renderTimeDependent() {
    if (!S.result) return;
    renderContext(); renderOverview(); renderFlow();
  }
  function renderAll() {
    if (!S.result) { renderNotSimulated(); return; }
    dayOptions();
    renderContext(); renderOverview(); renderFlow(); renderSetup();
  }
  window.addEventListener("resize", () => { clearTimeout(S._rs); S._rs = setTimeout(() => { renderChartsImpl(); renderCoverageImpl(); if (S.result) renderFlow(); }, 150); });

  // ================================================================ workforce: target search
  function initTargetForm() {
    const t = S.current.inputs.target;
    $("#tgtPct").value = t.pct;
    const mins = $("#tgtMin");
    const opts = [];
    for (let m = 60; m <= 720; m += 15) opts.push(h("option", { value: m, text: (m % 60 ? m + " minutes" : (m / 60) + " hours") }));
    mins.replaceChildren(...opts);
    mins.value = t.minutes;
    $("#tgtMode").replaceChildren(...Object.entries(S.meta.search.modes).map(([k, v]) => h("option", { value: k, text: v })));
    $("#tgtMode").value = "combined";
    $("#targetNote").textContent = S.meta.target.note + " The search re-runs the full model for every package it tries (" +
      S.meta.search.reps + " matched simulated weeks each), so a new search takes a few minutes; results are kept.";
  }

  async function runSearch(ev) {
    if (ev) ev.preventDefault();
    const pct = parseFloat($("#tgtPct").value), minutes = parseInt($("#tgtMin").value, 10), mode = $("#tgtMode").value;
    const errBox = $("#tgtError");
    errBox.hidden = true; $("#tgtPct").removeAttribute("aria-invalid");
    if (!(pct > 0 && pct <= 100)) {
      $("#tgtPct").setAttribute("aria-invalid", "true");
      showError(errBox, new ApiError("Enter a percentage between 1 and 100.")); $("#tgtPct").focus(); return;
    }
    const my = ++S.seq.search, sid = S.current.id;
    $("#searchResult").replaceChildren();
    const note = S.draftHash && S.draftHash !== S.current.model_hash ? h("p", { class: "ms-warning", text: "The search uses the saved scenario \"" + S.current.name + "\", not your unsaved edits below." }) : null;
    try {
      let d = await api("/api/m/search", { scenario_id: sid, target: { pct, minutes }, mode, request_id: my });
      if (d.status !== "done") {
        S.searchJob = d.job.id;
        $("#searchProgress").hidden = false;
        await pollJob(d.job.id, (j) => { $("#searchProgressText").textContent = j.message; $("#searchBar").value = j.progress; });
        d = await api("/api/m/search", { scenario_id: sid, target: { pct, minutes }, mode, request_id: my });
      }
      if (my !== S.seq.search || sid !== S.current.id) return;
      S.search = d.result;
      renderSearch(d.result, note);
    } catch (e) {
      if (my === S.seq.search) showError(errBox, e);
    } finally {
      if (my === S.seq.search) { $("#searchProgress").hidden = true; S.searchJob = null; }
    }
  }

  function measureCell(m) { return m ? fmt(m.mean, 1) + "% (" + fmt(m.min, 1) + "–" + fmt(m.max, 1) + ")" : "not available"; }
  function deltaCell(d) {
    if (!d) return "–";
    return signed(d.mean, 1, " pts") + (d.ci_low !== undefined ? " (" + signed(d.ci_low, 1) + " to " + signed(d.ci_high, 1) + ")" : "");
  }

  function renderSearch(res, note) {
    const box = $("#searchResult");
    const parts = [];
    if (note) parts.push(note);
    const outcomeCls = res.outcome === "not_reached" ? "ms-warning" : "ms-success";
    const label = { already_met: "Target already met", met: "Target met in the tested model", not_reached: "Target not reached within the tested options" }[res.outcome];
    parts.push(h("div", { class: outcomeCls }, h("h4", { text: label }), h("p", { text: res.headline }),
      h("p", { class: "ms-hint", text: (res.result_source === "precomputed" ? "Precomputed search result (labelled; you can re-run it). " : "") +
        res.evaluations.packages + " packages, " + res.evaluations.replications + " simulated weeks in total. " + res.bounds.mode_label + "." })));
    const rec = res.recommended;
    if (rec && rec.ids && rec.ids.length) {
      const f = rec.finance;
      parts.push(h("h4", { text: res.outcome === "met" ? "Lowest-cost package found within the tested options" : "Best tested package" }));
      parts.push(h("ul", { class: "ms-list" }, rec.titles.map(t => h("li", { text: t }))));
      if (!f.rota_rows.length) parts.push(h("p", { class: "ms-info", text: "This package adds no rota rows: the model has no staffing ratio for these items (see the notes against them), or the current rota already covers them." }));
      else parts.push(table("Additional rota (aggregate planning rota - not a named-person or clinically approved roster)",
        ["Role", "Area", "Days", "Hours", "Baseline staff", "Proposed", "Change", "Extra paid hours / week", "WTE", "Weekly cost", "Annual cost", "Why"],
        f.rota_rows.map(rw => [rw.role_label, rw.area, rw.days, HHMM(rw.start * 60) + "–" + HHMM(rw.end * 60), String(rw.baseline_staff), String(rw.proposed_staff),
          "+" + rw.change, fmt(rw.extra_paid_hours_week, 1), fmt(rw.wte, 2), money(rw.weekly_cost), money(rw.annual_cost), rw.why]), [4, 5, 6, 7, 8, 9, 10]));
      if (f.estate_rows.length) parts.push(table("Additional estate and hospital capacity",
        ["Item", "Change", "Before → after", "One-off capital", "Recurring non-pay a year", "Note"],
        f.estate_rows.map(e => [e.label, "+" + e.quantity + " " + e.unit + (e.quantity === 1 ? "" : "s"), e.before + " → " + e.after, money(e.capital), money(e.recurring_non_pay_annual), e.note || ""]), [3, 4]));
      parts.push(table("Cost (same cost tables price the baseline and the proposal)", ["Measure", "Value"], [
        ["Extra pay a week", money(f.weekly_pay_delta)], ["Extra pay a year (" + f.weeks_per_year + " weeks)", money(f.annual_pay_delta)],
        ["Extra paid hours a week", fmt(f.extra_paid_hours_week, 1)], ["Extra whole-time equivalents (WTE)", fmt(f.extra_wte, 2)],
        ["One-off capital", money(f.capital)], ["Recurring non-pay a year", money(f.recurring_non_pay_annual)],
        ["Recurring cost a year (pay + non-pay)", money(f.recurring_annual_total)],
        ["Annualised comparison cost (ranking only)", money(f.annualised_comparison_cost) + " = recurring + capital / " + f.capital_years + " years"],
        ["Not costed", f.not_costed.length ? f.not_costed.join("; ") : "nothing - fully costed"]], [1]));
      parts.push(h("p", { class: "ms-hint", text: f.method }));
      const v = (res.validation && res.validation.packages || []).find(x => JSON.stringify(x.ids) === JSON.stringify(rec.ids));
      parts.push(table("Modelled impact (" + res.bounds.replications_per_package + " matched selection weeks" + (v ? "; and " + res.validation.seeds.length + " separate validation weeks" : "") + ")",
        ["Measure", "Baseline", "Package", "Difference (simulation-noise interval)"], [
          ["Completed within " + res.target.minutes + " min", measureCell(res.baseline.measure), measureCell(rec.measure), deltaCell(rec.delta_vs_baseline_pts)],
          v ? ["… on the separate validation weeks", measureCell(res.validation.baseline.measure), measureCell(v.measure), deltaCell(v.delta_vs_baseline_pts)] : null,
          ["Over 12 hours from arrival", fmt(res.baseline.twelve_hour.mean, 1) + "%", fmt(rec.twelve_hour.mean, 1) + "%", ""],
          ["Left without being seen", fmt(res.baseline.lwbs.mean, 1) + "%", fmt(rec.lwbs.mean, 1) + "%", signed(rec.guardrails.lwbs_delta_pts, 1, " pts")],
          ["Unfinished when a week ends", fmt(res.baseline.wip_end.mean, 0), fmt(rec.wip_end.mean, 0), signed(rec.guardrails.wip_delta, 1)],
          ["Median time in department", fmt(res.baseline.duration_median.mean, 0) + " min", fmt(rec.duration_median.mean, 0) + " min", ""],
          ["Guardrails (walk-outs, unfinished)", "", rec.guardrails.ok ? "kept" : "BREACHED", ""],
        ].filter(Boolean), [1, 2, 3]));
      const openBtn = h("button", { class: "ms-btn-secondary", type: "button", text: "Open this package in the rota editor" });
      openBtn.addEventListener("click", () => { S.draft = clone(res.package_inputs); renderEditor(); schedulePreview(); $("#editorCard").scrollIntoView(); $("#rotaTable").focus(); });
      const saveBtn = h("button", { class: "ms-btn", type: "button", text: "Save as a scenario" });
      saveBtn.addEventListener("click", async () => {
        try {
          const d = await api("/api/m/search/save", { scenario_id: S.current.id, lever_ids: rec.ids, name: (res.outcome === "met" ? "Package for " : "Best tested package for ") + res.target.pct + "% (" + res.bounds.mode + ")" });
          await loadScenarios();
          $("#scenarioMsg").textContent = "Saved \"" + d.scenario.name + "\". Apply it from the Scenarios screen or the scenario picker.";
          saveBtn.replaceWith(h("p", { class: "ms-success", text: "Saved as \"" + d.scenario.name + "\". Choose it in the scenario picker to apply it to every screen." }));
        } catch (e) { showError("#tgtError", e); }
      });
      const retimeBtn = h("button", { class: "ms-btn-secondary", type: "button", text: "Build a re-timing alternative (same paid hours)" });
      retimeBtn.addEventListener("click", async () => {
        try {
          const d = await api("/api/m/retime", { scenario_id: S.current.id, lever_ids: rec.ids });
          S.draft = d.inputs; renderEditor(); schedulePreview();
          $("#draftResult").replaceChildren(h("div", { class: "ms-info" }, h("p", { text: d.note }),
            h("ul", { class: "ms-list" }, d.moves.map(mv => h("li", { text: "Move " + mv.count + " " + mv.role + " (" + mv.days + ") from " + mv.from + " to " + mv.to })),
              d.infeasible.map(x => h("li", { text: "Not re-timed - " + x }))),
            h("p", { class: "ms-hint", text: "Change in paid hours a week: " + fmt(d.paid_hours_delta, 1) + ". Simulate it to see its effect." })));
          $("#editorCard").scrollIntoView();
        } catch (e) { showError("#tgtError", e); }
      });
      parts.push(h("div", { class: "ms-actions" }, openBtn, retimeBtn, saveBtn));
    }
    if (res.limits) {
      parts.push(h("h4", { text: "What limits it (evidence from the best package's run)" }));
      parts.push(h("ul", { class: "ms-list" },
        res.limits.top_waiting_states.slice(0, 3).map(x => h("li", { text: x.label + ": " + fmt(x.patient_hours_per_day, 0) + " waiting patient-hours a day" })),
        res.limits.busy_resources.slice(0, 4).map(x => h("li", { text: labelFor(x.resource) + " busy " + fmt(x.utilisation, 0) + "% of the time" })),
        res.limits.fixed_in_this_model.map(t => h("li", { text: t }))));
    }
    if ((res.feasible || []).length > 1 || (res.partially_costed_feasible || []).length) {
      parts.push(table("Other packages that meet the target and keep the guardrails, ranked by annualised comparison cost",
        ["Rank", "Changes", "Within target", "Recurring a year", "Capital", "Annualised"],
        res.feasible.map((p, k) => [String(k + 1), p.titles.join(" + "), measureCell(p.measure), money(p.finance.recurring_annual_total), money(p.finance.capital), money(p.finance.annualised_comparison_cost)]), [2, 3, 4, 5]));
      if ((res.partially_costed_feasible || []).length) parts.push(table("Meets the target but PARTIALLY COSTED (never ranked as cheapest)",
        ["Changes", "Within target", "Not costed"], res.partially_costed_feasible.map(p => [p.titles.join(" + "), measureCell(p.measure), p.finance.not_costed.join("; ")])));
    }
    if (res.singles) parts.push(h("details", { class: "ms-details" }, h("summary", { text: "Each change tested on its own (" + res.singles.length + ")" }),
      table(null, ["Change", "Within target", "Difference vs baseline", "Reading"], res.singles.map(s => [s.titles[0], measureCell(s.measure), deltaCell(s.delta_vs_baseline_pts),
        s.delta_vs_baseline_pts && s.delta_vs_baseline_pts.ci_low !== undefined && s.delta_vs_baseline_pts.ci_low <= 0 && s.delta_vs_baseline_pts.ci_high >= 0
          ? "No clear effect on its own (may not be the binding constraint; can still matter in combination)" : (s.delta_vs_baseline_pts && s.delta_vs_baseline_pts.mean > 0 ? "Helps on its own" : "Worse on its own")]), [1, 2]),
      h("p", { class: "ms-hint", text: "A change that does nothing on its own is still tried in combination: extra space may only help once the staff to open it are there." })));
    parts.push(h("details", { class: "ms-details" }, h("summary", { text: "Search method, bounds and limits" }),
      h("p", { class: "ms-hint", text: res.bounds.note }),
      h("p", { class: "ms-hint", text: "Changes tested: " + res.bounds.levers.map(l => l.title).join("; ") + ". Up to " + res.bounds.max_steps + " changes per package; a step is kept only if it adds at least " + res.bounds.min_step_gain_pts + " percentage points. Selection seeds " + res.bounds.selection_seeds.join(", ") + "; validation seeds " + res.bounds.validation_seeds.join(", ") + ". Guardrails: walk-outs no more than " + res.bounds.guardrails.max_lwbs_increase_pts + " point higher; unfinished patients no more than " + res.bounds.guardrails.max_wip_increase_pct + "% higher." }),
      h("pre", { class: "ms-hint", text: res.method })));
    box.replaceChildren(...parts);
  }

  // ================================================================ workforce: editor
  const DAY_PATTERNS = ["Mon-Sun", "Mon-Fri", "Sat-Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  function hourSelect(val, isEnd, label) {
    const s = h("select", { "aria-label": label });
    for (let hh = isEnd ? 1 : 0; hh <= (isEnd ? 24 : 23); hh++) s.append(h("option", { value: hh, text: HHMM(hh * 60).replace("00:00", isEnd ? "24:00" : "00:00") }));
    s.value = val;
    return s;
  }
  function renderEditor() {
    const d = S.draft;
    $("#editorSource").textContent = "Editing a draft copy of \"" + S.current.name + "\". Nothing changes on other screens until you simulate and save. Rota provenance: " + S.meta.rota_provenance;
    $("#rotaConvention").textContent = S.meta.rota_convention + " Counts are staff on shift; a blank count is an error (enter 0 if nobody is rostered).";
    const roleOpts = Object.entries(S.meta.roles);
    const tbl = $("#rotaTable");
    const head = h("thead", {}, h("tr", {}, ["Role", "Area", "Days", "Start", "End", "Staff", "Unpaid break (min)", ""].map(c => h("th", { scope: "col", text: c }))));
    const body = h("tbody");
    d.rota.forEach((row, i) => {
      const role = h("select", { class: "role", "aria-label": "Role, row " + (i + 1) }, roleOpts.map(([k, v]) => h("option", { value: k, text: v.label })));
      role.value = row.role;
      const area = h("input", { type: "text", value: row.area || "", "aria-label": "Area, row " + (i + 1), maxlength: 60 });
      const days = h("select", { "aria-label": "Days, row " + (i + 1) }, DAY_PATTERNS.map(p => h("option", { value: p, text: p })));
      if (!DAY_PATTERNS.includes(row.days || "Mon-Sun")) days.append(h("option", { value: row.days, text: row.days }));
      days.value = row.days || "Mon-Sun";
      const start = hourSelect(row.start, false, "Start, row " + (i + 1));
      const end = hourSelect(row.end === 0 ? 24 : row.end, true, "End, row " + (i + 1));
      const count = h("input", { type: "number", min: 0, max: 99, step: 1, value: row.count, "aria-label": "Staff on shift, row " + (i + 1) });
      const brk = h("input", { type: "number", min: 0, max: 240, step: 5, value: row.unpaid_break_minutes || 0, "aria-label": "Unpaid break minutes, row " + (i + 1) });
      const rm = h("button", { type: "button", class: "ms-btn-small", "aria-label": "Remove row " + (i + 1), text: "Remove" });
      const upd = () => {
        row.role = role.value; row.area = area.value; row.days = days.value;
        row.start = parseInt(start.value, 10); row.end = parseInt(end.value, 10);
        row.count = count.value === "" ? "" : Number(count.value);
        row.unpaid_break_minutes = brk.value === "" ? 0 : Number(brk.value);
        schedulePreview();
      };
      [role, area, days, start, end, count, brk].forEach(c => c.addEventListener("change", upd));
      rm.addEventListener("click", () => { d.rota.splice(i, 1); renderEditor(); schedulePreview(); });
      body.append(h("tr", { id: "rota-row-" + (i + 1) }, h("td", {}, role), h("td", {}, area), h("td", {}, days), h("td", {}, start), h("td", {}, end), h("td", {}, count), h("td", {}, brk), h("td", {}, rm)));
    });
    tbl.replaceChildren(h("caption", { class: "ms-visually-hidden", text: "Rota rows" }), head, body);
    tbl.tabIndex = -1;
    renderCostEditor(); renderCapEditor(); renderEstateEditor();
  }

  function numInput(val, label, onset, opts) {
    const i = h("input", { type: "number", step: (opts && opts.step) || "any", min: (opts && opts.min) ?? 0, value: val === null || val === undefined ? "" : val, "aria-label": label });
    i.addEventListener("change", () => { onset(i.value === "" ? null : Number(i.value)); schedulePreview(); });
    return i;
  }
  function renderCostEditor() {
    const ct = S.draft.cost_table;
    $("#costInclusions").textContent = S.meta.cost_status + " " + S.meta.cost_inclusions + " A blank rate means NOT COSTED (never £0); 0 means £0.";
    const rates = (S.preview && S.preview.rates) || {};
    const rows = Object.entries(ct.roles).map(([role, e]) => {
      const lbl = (S.meta.roles[role] || {}).label || role;
      const f = (k, step) => numInput(e[k], k.replace(/_/g, " ") + ", " + lbl, (v) => { e[k] = v; }, { step });
      const er = rates[role];
      return [lbl, f("base_hourly_rate", 0.5), f("employer_on_cost_pct", 1), f("enhancement_pct", 1), f("agency_share_pct", 1), f("agency_hourly_rate", 0.5),
        f("fully_loaded_hourly_rate", 0.5), f("contracted_hours_per_week", 0.5), er ? (er.rate === null ? "not costed" : "£" + er.rate.toFixed(2)) : "–"];
    });
    $("#costTable").replaceChildren(...Array.from(table(null, ["Role", "Basic £/h", "On-cost %", "Enhancement %", "Bank/agency share %", "Agency £/h", "Fully loaded £/h (overrides)", "Contracted h/week", "Effective £/h"], rows).firstChild.childNodes));
  }
  function renderCapEditor() {
    const d = S.draft, prov = S.meta.capacity_provenance;
    $("#capTable").replaceChildren(...Array.from(table("Physical spaces (0 = we don't have this)", ["Space", "Count", "Source"],
      Object.entries(d.capacity).filter(([k]) => k !== "minor_injury_space").map(([k, v]) =>
        [labelFor(k), numInput(v, "Count, " + labelFor(k), (x) => { d.capacity[k] = x === null ? "" : x; }, { step: 1 }), prov[k] || "Scenario input"])).firstChild.childNodes));
    $("#ratioTable").replaceChildren(...Array.from(table("Space-staffing ratios (editable planning assumptions, not safe-staffing standards)", ["Space", "Opened by", "Spaces per member of staff"],
      d.space_staffing.map(e => [labelFor(e.space), labelFor(e.staff), numInput(e.spaces_per_staff, "Spaces per staff, " + labelFor(e.space), (x) => { e.spaces_per_staff = x; }, { step: 0.5, min: 0.5 })])).firstChild.childNodes));
    const sd = d.sdec, ds = d.downstream;
    const sOpen = hourSelect(sd.hours[0], false, "SDEC opens"), sClose = hourSelect(sd.hours[1], true, "SDEC closes");
    const upd = () => { sd.hours = [parseInt(sOpen.value, 10), parseInt(sClose.value, 10)]; d.areas.hours.sdec = sd.hours.slice(); schedulePreview(); };
    sOpen.addEventListener("change", upd); sClose.addEventListener("change", upd);
    const f = (lbl, el) => h("div", { class: "ms-field" }, h("label", { text: lbl }), el);
    const beds = numInput(ds.inpatient_beds, "Inpatient beds", (x) => { ds.inpatient_beds = x; }, { step: 1 });
    const disch = numInput(ds.ward_discharge_capacity_per_hour, "Ward discharges per hour at baseline occupancy", (x) => { ds.ward_discharge_capacity_per_hour = x; }, { step: 0.1 });
    const dem = numInput(d.cohort.demand_scale ?? 1, "Demand scale", (x) => { d.cohort.demand_scale = x; }, { step: 0.05, min: 0.2 });
    $("#otherInputs").replaceChildren(f("SDEC opens", sOpen), f("SDEC closes", sClose), f("Inpatient beds", beds), f("Ward discharges an hour", disch),
      f("Demand scale (1 = baseline demand)", dem), h("p", { class: "ms-hint", text: "Changing demand changes the comparison basis - the baseline keeps 1.0. " + S.meta.downstream.aggregate_assumption }));
  }
  function renderEstateEditor() {
    const it = S.draft.estates.items;
    $("#estateNote").textContent = S.draft.estates.status + " " + S.draft.estates.annualisation.note;
    $("#estateTable").replaceChildren(...Array.from(table(null, ["Item", "Unit", "One-off capital per unit", "Recurring non-pay a year per unit", "Note"],
      Object.entries(it).map(([k, e]) => [e.label, e.unit, numInput(e.capital, "Capital, " + e.label, (x) => { e.capital = x; }, { step: 100 }),
        numInput(e.recurring_non_pay, "Recurring, " + e.label, (x) => { e.recurring_non_pay = x; }, { step: 100 }), e.note || e.staffing_not_modelled || ""])).firstChild.childNodes));
  }

  // instant preview: coverage and cost, no simulation; stale replies dropped
  function schedulePreview() { clearTimeout(S._pv); S._pv = setTimeout(previewDraft, 250); }
  async function previewDraft() {
    const my = ++S.seq.preview;
    let d;
    try { d = await api("/api/m/preview", { inputs: S.draft, scenario_id: S.current.id, request_id: my }); }
    catch (e) { if (my === S.seq.preview) showError("#rotaErrors", e); return; }
    if (my !== S.seq.preview) return;
    S.preview = d; S.draftHash = d.model_hash;
    // validation errors, row by row
    $$("#rotaTable tr").forEach(tr => tr.classList.remove("ms-row-error"));
    const box = $("#rotaErrors");
    if (d.errors && d.errors.length) {
      showError(box, new ApiError("Fix these before simulating:", 400, d.errors));
      d.errors.forEach(e => { if (e.field === "rota" && e.row) { const tr = $("#rota-row-" + e.row); if (tr) tr.classList.add("ms-row-error"); } });
    } else box.hidden = true;
    renderDraftBanner();
    if (!d.errors || !d.errors.length) { renderCoverageImpl(); renderCostSummary(); }
    renderCostEditorRates();
  }
  function renderCostEditorRates() {
    if (!S.preview || !S.preview.rates) return;
    $$("#costTable tbody tr").forEach((tr, i) => {
      const role = Object.keys(S.draft.cost_table.roles)[i], er = S.preview.rates[role], td = tr.lastChild;
      if (td) td.textContent = er ? (er.rate === null ? "not costed" : "£" + er.rate.toFixed(2)) : "–";
    });
  }
  function renderDraftBanner() {
    const b = $("#draftBanner");
    const dirty = S.draftHash && S.draftHash !== S.current.model_hash;
    const finDirty = S.preview && S.preview.finance_hash !== (S.current.finance_hash || S.preview.finance_hash);
    if (!dirty && !finDirty) { b.hidden = true; return; }
    b.hidden = false;
    b.replaceChildren(h("strong", { text: dirty ? "Changes not yet simulated." : "Cost changes only." }), " ",
      dirty ? (S.preview.simulated ? "These inputs have been simulated but not saved: save them as a scenario to apply them to every screen. Overview and Patient flow still show \"" + S.current.name + "\"."
        : "Coverage and cost below update instantly; performance on every screen is still the last completed simulation of \"" + S.current.name + "\".")
        : "Cost edits re-price everything instantly and never change simulated performance.");
  }

  function renderCostSummary() {
    const p = S.preview;
    const c = p.cost, b = p.baseline_cost;
    const nc = c.uncosted_roles.length ? "Not costed: " + c.uncosted_roles.map(r => (S.meta.roles[r] || {}).label || r).join(", ") + " (their hours are counted; their pay is not priced at £0)." : "Every rota role is costed.";
    $("#costSummary").replaceChildren(table("Pay for this rota (instant, from the cost table above)", ["Measure", "This draft", "Demo baseline rota (same rates)", "Difference"], [
      ["Pay a week", money(c.weekly_total), money(b.weekly_total), money(c.weekly_total - b.weekly_total)],
      ["Pay a year (" + c.weeks_per_year + " weeks)", money(c.annual_total), money(b.annual_total), money(c.annual_total - b.annual_total)],
      ["Paid hours a week", fmt(Object.values(c.paid_hours_by_role).reduce((a, x) => a + x, 0), 0), fmt(Object.values(b.paid_hours_by_role).reduce((a, x) => a + x, 0), 0), ""]], [1, 2, 3]),
      h("p", { class: "ms-hint", text: nc + " Annual pay is a cost, not a cashable saving; no return on investment is calculated." }));
  }

  function renderCoverageImpl() {
    const p = S.preview;
    if (!p || !p.staffing || $("#panel-workforce").hidden) return;
    const gsel = $("#covGroup"), dsel = $("#covDay");
    const keys = Object.keys(p.staffing);
    if (gsel.options.length !== keys.length) {
      gsel.replaceChildren(...keys.map(k => h("option", { value: k, text: p.staffing[k].label })));
      dsel.replaceChildren(...DAYNAMES.map((dn, i) => h("option", { value: i, text: dn })));
      gsel.onchange = () => { S.covGroup = gsel.value; renderCoverageImpl(); };
      dsel.onchange = () => { S.covDay = +dsel.value; renderCoverageImpl(); };
    }
    if (!S.covGroup || !keys.includes(S.covGroup)) S.covGroup = keys.includes("ed_nurse") ? "ed_nurse" : keys[0];
    gsel.value = S.covGroup; dsel.value = S.covDay;
    const st = p.staffing[S.covGroup], a = S.covDay * 24;
    columnChart($("#chartCoverage"), {
      labels: [...Array(24).keys()].map(hh => HHMM(hh * 60)), height: 190, yTitle: "staff on shift",
      series: [{ name: "Demo baseline", values: st.baseline_week.slice(a, a + 24), color: token("--chart-1") },
               { name: "This draft", values: st.week.slice(a, a + 24), color: token("--chart-2") }],
      xTick: (i) => i % 3 === 0 ? HHMM(i * 60) : null,
      tipTitle: (i) => st.label + ", " + DAYNAMES[S.covDay] + " " + HHMM(i * 60),
    });
    const rows = Object.entries(p.spaces).map(([k, s]) => {
      const ow = s.open_week || [], bw = s.baseline_open_week || ow, pw = s.physical_week;
      const rng = (w) => w && w.length ? (Math.min(...w) === Math.max(...w) ? String(Math.max(...w)) : Math.min(...w) + "–" + Math.max(...w)) : "–";
      return [labelFor(k), pw ? rng(pw) : "–", rng(ow), rng(bw)];
    });
    $("#spaceSummary").replaceChildren(...[table("Spaces: physical and open (open = covered by staff on shift; ranges over the week; 0 when the area is closed or unstaffed)", ["Space", "Physical", "Open in this draft", "Open in the baseline"], rows, [1, 2, 3]),
      (p.warnings || []).length ? h("div", { class: "ms-warning" }, h("ul", {}, p.warnings.map(w => h("li", { text: w })))) : null].filter(Boolean));
  }

  async function draftRun() {
    if (S.preview && S.preview.errors && S.preview.errors.length) { $("#rotaErrors").focus(); return; }
    const my = ++S.seq.draftcmp, hash = S.draftHash;
    $("#draftResult").replaceChildren();
    try {
      let d = await api("/api/m/run", { inputs: S.draft });
      if (d.status !== "done") {
        S.draftJob = d.job.id; $("#draftProgress").hidden = false;
        await pollJob(d.job.id, (j) => { $("#draftProgressText").textContent = j.message; $("#draftBar").value = j.progress; });
      }
      // the baseline must be simulated too for a matched comparison
      const b = await api("/api/m/run", { scenario_id: "baseline" });
      if (b.status !== "done") await pollJob(b.job.id, (j) => { $("#draftProgressText").textContent = "Baseline: " + j.message; $("#draftBar").value = j.progress; });
      const cmp = await api("/api/m/compare-draft", { inputs: S.draft, request_id: my });
      if (my !== S.seq.draftcmp || cmp.model_hash !== S.draftHash || hash !== S.draftHash) return;     // edited since: discard
      renderComparison($("#draftResult"), cmp);
      schedulePreview();
    } catch (e) { if (my === S.seq.draftcmp) showError($("#draftResult"), e); }
    finally { $("#draftProgress").hidden = true; S.draftJob = null; }
  }

  function renderComparison(box, cmp) {
    const rows = cmp.rows;
    if (!rows.length) { box.replaceChildren(h("p", { class: "ms-warning", text: "Nothing to compare yet: " + (cmp.missing || []).map(m => m.name + " has not been simulated").join("; ") })); return; }
    const t = cmp.target;
    const head = ["Measure", ...rows.map(r => r.name + (r.result_source === "precomputed" ? " (precomputed)" : ""))];
    const line = (label, f) => [label, ...rows.map(f)];
    const body = [
      line("Planning target", () => t.pct + "% within " + t.minutes + " min"),
      line("Completed within target (mean, range across weeks)", r => measureCell(r.target_measure)),
      line("Difference vs baseline (percentage points, noise interval)", r => r.id === "baseline" ? "–" : deltaCell(r.delta_vs_baseline_pts)),
      line("Verdict", r => r.target_status.status),
      line("Remaining gap to target (points)", r => fmt(r.remaining_gap_pts, 1)),
      line("Median time in department", r => fmt(r.duration_median.mean, 0, " min")),
      line("Median total waiting", r => fmt(r.total_wait_median.mean, 0, " min")),
      line("Over 12 hours from arrival", r => fmt(r.twelve_hour.mean, 1, "%")),
      line("Left without being seen", r => fmt(r.lwbs.mean, 1, "%")),
      line("Unfinished when a week ends", r => fmt(r.wip_end.mean, 0)),
      line("Extra shifts a week", r => String(r.extra_shifts_week)),
      line("Extra paid hours a week", r => fmt(r.extra_paid_hours_week, 1)),
      line("Extra pay a year", r => money(r.annual_pay_delta)),
      line("Extra estate", r => r.estate.rows.length ? r.estate.rows.map(e => e.label + " " + (typeof e.change === "number" ? signed(e.change, 0) : e.change)).join("; ") : "none"),
      line("One-off capital", r => money(r.capital)),
      line("Recurring non-pay a year", r => money(r.recurring_non_pay_annual)),
      line("Not costed", r => r.not_costed.length ? r.not_costed.join("; ") : "–"),
      line("Simulated weeks (seeds)", r => r.replications + " (" + r.seeds[0] + "–" + r.seeds[r.seeds.length - 1] + ")"),
    ];
    box.replaceChildren(table("Compared with the demo baseline", head, body), h("p", { class: "ms-hint", text: cmp.note }));
  }

  async function draftSave() {
    const name = window.prompt("Name for this scenario", "My scenario");
    if (name === null) return;
    if (!name.trim()) { showError("#rotaErrors", new ApiError("A scenario needs a name.")); return; }
    try {
      const d = await api("/api/m/scenarios", { name: name.trim(), inputs: S.draft });
      await loadScenarios();
      const apply = h("button", { class: "ms-btn", type: "button", text: "Apply \"" + d.scenario.name + "\" to every screen" });
      apply.addEventListener("click", () => applyScenario(d.scenario.id).then(() => selectTab("overview", true)).catch(e => showError("#globalError", e)));
      $("#draftResult").replaceChildren(h("div", { class: "ms-success" }, h("p", { text: "Saved \"" + d.scenario.name + "\". The demo baseline is unchanged." }), apply));
    } catch (e) { showError("#rotaErrors", e); }
  }

  function draftCsv() {
    const cols = ["role", "area", "days", "start", "end", "count", "unpaid_break_minutes", "note"];
    const esc = (v) => { const s = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const lines = [cols.join(",")].concat(S.draft.rota.map(r => [r.role, r.area || "", r.days || "Mon-Sun", HHMM(r.start * 60), r.end === 24 ? "24:00" : HHMM(r.end * 60), r.count, r.unpaid_break_minutes || 0, r.note || ""].map(esc).join(",")));
    return lines.join("\n") + "\n";
  }

  function wireEditor() {
    $("#rotaAdd").addEventListener("click", () => {
      S.draft.rota.push({ role: "band5_nurse", area: "Majors", days: "Mon-Sun", start: 8, end: 20, count: 1, unpaid_break_minutes: 30 });
      renderEditor(); schedulePreview();
      const sel = $("#rota-row-" + S.draft.rota.length + " select"); if (sel) sel.focus();
    });
    $("#rotaFile").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append("file", f);
      try {
        const d = await api("/api/m/rota/import", fd);
        if (!d.ok) { showError("#rotaErrors", new ApiError("The rota file was not imported:", 400, d.errors)); return; }
        S.draft.rota = d.rows; renderEditor(); schedulePreview();
      } catch (err) { showError("#rotaErrors", err); }
      e.target.value = "";
    });
    $("#rotaExport").addEventListener("click", (e) => {
      e.preventDefault();
      const blob = new Blob([draftCsv()], { type: "text/csv" });
      const a = h("a", { href: URL.createObjectURL(blob), download: "midshire_rota_draft.csv" });
      document.body.append(a); a.click(); a.remove();
    });
    $("#draftRun").addEventListener("click", draftRun);
    $("#draftSave").addEventListener("click", draftSave);
    $("#draftDiscard").addEventListener("click", () => { S.draft = clone(S.current.inputs); renderEditor(); schedulePreview(); $("#draftResult").replaceChildren(); });
    $("#draftCancel").addEventListener("click", () => { if (S.draftJob) api("/api/m/jobs/" + S.draftJob + "/cancel", {}); });
    $("#searchCancel").addEventListener("click", () => { if (S.searchJob) api("/api/m/jobs/" + S.searchJob + "/cancel", {}); });
    $("#targetForm").addEventListener("submit", runSearch);
  }

  // ================================================================ scenarios
  function renderScenarioTable() {
    const tbl = $("#scenarioTable");
    const head = h("thead", {}, h("tr", {}, ["Compare", "Scenario", "Kind", "Last changed", "Note", "Actions"].map(c => h("th", { scope: "col", text: c }))));
    const body = h("tbody", {}, S.scenarios.map(sc => {
      const cb = h("input", { type: "checkbox", "aria-label": "Compare " + sc.name, disabled: sc.id === "baseline" ? true : null, checked: S.compareSel.has(sc.id) ? true : null });
      cb.addEventListener("change", () => { cb.checked ? S.compareSel.add(sc.id) : S.compareSel.delete(sc.id); });
      const apply = h("button", { class: "ms-btn-small", type: "button", text: sc.id === S.applied ? "Applied" : "Apply", disabled: sc.id === S.applied ? true : null });
      apply.addEventListener("click", () => applyScenario(sc.id).then(() => { renderScenarioTable(); $("#scenarioMsg").textContent = "Applied \"" + sc.name + "\" to every screen."; }).catch(e => showError("#globalError", e)));
      const sim = h("button", { class: "ms-btn-small", type: "button", text: "Simulate" });
      sim.addEventListener("click", async () => {
        $("#scenarioMsg").textContent = "Simulating \"" + sc.name + "\"…";
        try { const d = await api("/api/m/run", { scenario_id: sc.id }); if (d.status !== "done") await pollJob(d.job.id, j => { $("#scenarioMsg").textContent = sc.name + ": " + j.message; }); $("#scenarioMsg").textContent = "\"" + sc.name + "\" simulated."; }
        catch (e) { $("#scenarioMsg").textContent = "Simulation failed: " + e.message; }
      });
      const del = sc.id === "baseline" ? null : h("button", { class: "ms-btn-small", type: "button", text: "Delete" });
      if (del) del.addEventListener("click", async () => {
        if (!window.confirm("Delete \"" + sc.name + "\"? The demo baseline is not affected.")) return;
        await api("/api/m/scenarios/" + encodeURIComponent(sc.id), undefined, "DELETE");
        S.compareSel.delete(sc.id);
        await loadScenarios(); if (S.applied !== $("#scenarioPick").value) await loadCurrent();
      });
      return h("tr", {}, h("td", {}, cb), h("th", { scope: "row", text: sc.name }), h("td", { text: sc.kind === "precomputed" ? "precomputed (labelled)" : sc.kind }),
        h("td", { text: sc.updated_at.replace("T", " ") }), h("td", { text: sc.note || "" }), h("td", {}, h("div", { class: "ms-actions" }, apply, sim, del)));
    }));
    tbl.replaceChildren(h("caption", { class: "ms-visually-hidden", text: "Saved scenarios" }), head, body);
    const sid = encodeURIComponent(S.applied);
    $("#exportLinks").replaceChildren(
      h("li", {}, h("a", { href: "/api/m/export/inputs.json?scenario_id=" + sid, text: "Inputs (JSON) for the applied scenario" })),
      h("li", {}, h("a", { href: "/api/m/export/rota.csv?scenario_id=" + sid, text: "Rota (CSV) for the applied scenario" })),
      h("li", {}, h("a", { href: "/api/m/export/results.json?scenario_id=" + sid, text: "Results with metric definitions and run metadata (JSON)" })),
      h("li", {}, h("a", { href: "/api/m/export/comparison.csv?scenario_id=" + sid + "&ids=" + [...S.compareSel].map(encodeURIComponent).join(","), id: "cmpCsv", text: "Comparison with the baseline (CSV)" })));
  }
  function wireScenarios() {
    $("#compareGo").addEventListener("click", async () => {
      $("#compareOut").replaceChildren(h("p", { class: "ms-hint", text: "Comparing…" }));
      try {
        const cmp = await api("/api/m/compare", { scenario_ids: [...S.compareSel], target: S.current.inputs.target });
        renderComparison($("#compareOut"), cmp);
        if (cmp.missing.length) $("#compareOut").prepend(h("p", { class: "ms-warning", text: "Not simulated yet (use Simulate first): " + cmp.missing.map(m => m.name).join(", ") }));
        renderScenarioTable();
      } catch (e) { showError($("#compareOut"), e); }
    });
    $("#resetBaseline").addEventListener("click", async () => {
      if (!window.confirm("Reset to the demo baseline? Your saved scenarios are kept; the applied scenario returns to the baseline.")) return;
      try { const d = await api("/api/m/reset", {}); await loadScenarios(); await loadCurrent(); $("#scenarioMsg").textContent = d.note; }
      catch (e) { showError("#globalError", e); }
    });
  }

  // ================================================================ set up / assumptions
  function renderSetup() {
    const m = S.meta, r = S.result;
    const dl = (pairs) => h("dl", { class: "ms-dl" }, pairs.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]));
    const parts = [
      h("div", { class: "ms-info" }, h("ul", { class: "ms-list" }, m.disclaimers.map(d => h("li", { text: d })))),
      h("h3", { text: "Where the model comes from" }),
      dl([["Foundation", m.foundation.summary], ["Validation status", m.foundation.validation_status],
        ["Source files", m.foundation.source_files.join(", ")], ["Source commit", m.foundation.source_commit],
        ["Demo identifier", m.demo_id + " - " + m.demo_id_note], ["Fixture", m.fixture_version + " (" + m.fixture_hash + ")"],
        ["Storage", m.storage.database + " - " + m.storage.note]]),
      h("h3", { text: "The adult cohort" }),
      dl([["Cohort", m.cohort.label], ["All-ages attendances (source)", m.cohort.all_ages_attendances_per_day.value + "/day - " + m.cohort.all_ages_attendances_per_day.provenance],
        ["Paediatric share removed", (m.cohort.paediatric_share_excluded.value * 100).toFixed(2) + "% - " + m.cohort.paediatric_share_excluded.provenance],
        ["Adult attendances", m.cohort.adult_attendances_per_day.value + "/day - " + m.cohort.adult_attendances_per_day.provenance]]),
      h("ul", { class: "ms-list" }, m.cohort.assumptions.map(a => h("li", { text: a }))),
      h("h3", { text: "Pathway decisions" }),
      dl([["SDEC", m.sdec.routing_note], ["SDEC when closed", m.sdec.closed_note], ["SDEC stay", m.sdec.service_note],
        ["SDEC selection", m.sdec.selection_caveat], ["SDEC and the four-hour clock", m.sdec.reporting_note],
        ["Mental health", m.mental_health.provenance + " " + m.mental_health.not_modelled],
        ["Hospital beds", m.downstream.provenance + " " + m.downstream.aggregate_assumption], ["Community", m.downstream.community_note],
        ["Space staffing", m.space_staffing_note]]),
    ];
    if (r) {
      parts.push(h("h3", { text: "Provenance of every input in the applied scenario" }),
        table(null, ["Input", "Value", "Kind", "Source"], r.model.provenance.map(p => [p.item, p.value === null || p.value === undefined ? "" : String(p.value), p.kind, p.source])));
      if (r.model.warnings.length) parts.push(h("div", { class: "ms-warning" }, h("ul", {}, r.model.warnings.map(w => h("li", { text: w })))));
      parts.push(h("h3", { text: "Run" }), dl([["Run id", r.run_id], ["Seeds", r.seeds.join(", ") + " (" + r.seed_set + " set)"], ["Validation seeds", m.engine.validation_seeds.join(", ")],
        ["Engine", r.engine_version + "; metrics " + r.metrics_version + "; pathway " + r.pathway_version], ["Source commit at run time", r.source_commit],
        ["When", r.timestamp], ["Run length", m.engine.note], ["Model hash", r.model_hash]]));
    }
    parts.push(h("h3", { text: "Metric definitions" }),
      table(null, ["Metric", "Population", "Units", "Time window", "Aggregation", "Starts", "Ends", "Patients still in progress"],
        Object.values(m.definitions).map(d => [d.label, d.population, d.units, d.window, d.aggregation, d.start, d.end, d.in_progress])));
    parts.push(h("p", { class: "ms-hint", text: "Uncertainty: the range shown is the lowest to highest of the simulated weeks; intervals are simulation-noise intervals of a mean (a t-interval over the weeks). Neither is a calibrated forecast of real weeks." }));
    $("#setupBody").replaceChildren(...parts);
    $("#footerText").textContent = m.product_title + " - a fictional adult ED planning demonstrator built on a model derived from a real trust's data (see Set up / assumptions); not a live patient feed, not an NHS service and not a clinically validated staffing tool. Fixture " + m.fixture_version + ".";
  }

  // ================================================================ Ask Qbo ED
  function qboAdd(role, text, meta) {
    const m = h("div", { class: "ms-qbo-msg " + role, text });
    if (meta) m.append(h("span", { class: "meta", text: meta }));
    $("#qboLog").append(m); $("#qboLog").scrollTop = $("#qboLog").scrollHeight;
    return m;
  }
  async function qboAsk(q) {
    qboAdd("user", q);
    const wait = qboAdd("bot", "Checking the model…");
    try {
      const view = S.mode === "replay" && S.result ? { index: idx() } : null;
      const d = await api("/api/m/ask", { message: q, scenario_id: S.current.id, view });
      wait.textContent = d.reply;
      wait.append(h("span", { class: "meta", text: (d.intent || "") + (d.run_id ? " · run " + d.run_id : "") + " · scenario " + (S.current ? S.current.name : "") }));
      const openPkg = (t) => {
        const b = h("button", { class: "ms-link-btn", type: "button", text: "Open the package, rota and costs" });
        b.addEventListener("click", () => { $("#tgtPct").value = t.pct; $("#tgtMin").value = t.minutes; $("#tgtMode").value = t.mode; selectTab("workforce"); runSearch(); });
        return b;
      };
      if (d.intent === "target" && d.search_key && d.target) wait.append(h("br"), openPkg(d.target));
      if (d.job) {
        const prog = qboAdd("bot", "Working…");
        const j = await pollJob(d.job.id, (jj) => { prog.textContent = jj.message + " (" + Math.round(100 * jj.progress) + "%)"; });
        if (d.intent === "what_if") {
          let w;
          for (let k = 0; k < 120; k++) { w = await api("/api/m/ask/whatif/" + j.id); if (w.status === "done") break; await new Promise(r => setTimeout(r, 1000)); }
          prog.textContent = w.reply || w.message || "No answer.";
        } else if (d.intent === "target") {
          const again = await api("/api/m/ask", { message: q, scenario_id: S.current.id });
          prog.textContent = again.reply;
          if (again.target) prog.append(h("br"), openPkg(again.target));
        }
      }
    } catch (e) { wait.textContent = "Sorry - " + e.message; }
  }
  function wireQbo() {
    const open = $("#qboOpen"), panel = $("#qboPanel");
    const setOpen = (on) => {
      panel.hidden = !on; open.setAttribute("aria-expanded", on ? "true" : "false");
      if (on) {
        if (!$("#qboLog").children.length) qboAdd("bot", "Hello. I'm Ask Qbo ED. I answer from the simulation results for the scenario on screen - for example \"how are we doing?\", \"where do patients wait longest?\", \"what if we add 2 nurses 08:00-20:00?\" or \"what workforce and space changes would get 90% through within four hours?\"");
        $("#qboIn").focus();
      } else open.focus();
    };
    open.addEventListener("click", () => setOpen(panel.hidden));
    $("#qboClose").addEventListener("click", () => setOpen(false));
    panel.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
    $("#qboForm").addEventListener("submit", (e) => {
      e.preventDefault(); const q = $("#qboIn").value.trim(); if (!q) return; $("#qboIn").value = ""; qboAsk(q);
    });
  }

  // ================================================================ init
  async function init() {
    try {
      S.meta = await api("/api/m/meta");
      $("#statusMore").textContent = "Fictional demonstration identity. Inputs: a real trust's published and extract data plus labelled illustrative assumptions (rota, costs, SDEC) - see Set up / assumptions.";
      wireTabs(); wireContext(); wireEditor(); wireScenarios(); wireQbo(); wireFlowControls();
      $("#expertView").addEventListener("toggle", () => { S.expertKey = null; if (S.result) renderExpert(); });
      await loadScenarios();
      await loadCurrent();
      initTargetForm();
      renderSetup();
    } catch (e) { showError("#globalError", e); }
  }
  init();
})();
