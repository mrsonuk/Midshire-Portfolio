// Browser checks for the Midshire demonstrator (not part of CI - needs Chromium).
//   python3 -m uec_hybrid.midshire --port 5055 &      (then)
//   node docs/midshire/browser_check.js http://127.0.0.1:5055 docs/midshire/screenshots
// Uses the globally installed Playwright. Exits non-zero on any failed check.
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); }
catch (e) { ({ chromium } = require("/opt/node22/lib/node_modules/playwright")); }

const BASE = process.argv[2] || "http://127.0.0.1:5055";
const OUT = process.argv[3] || "docs/midshire/screenshots";
const results = [];
const ok = (name, cond, detail) => { results.push({ name, ok: !!cond, detail: detail || "" }); };

async function newPage(browser, opts) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", m => { if (m.type() === "error") errors.push("console: " + m.text()); });
  page.on("pageerror", e => errors.push("pageerror: " + e.message));
  page.on("response", r => { if (r.status() >= 400 && !r.url().includes("favicon")) errors.push("HTTP " + r.status() + " " + r.url()); });
  page.on("requestfailed", r => errors.push("failed: " + r.url()));
  return { ctx, page, errors };
}

async function ready(page) {
  await page.goto(BASE + "/");
  await page.waitForSelector("#kpiPrimary .ms-tile, #kpiPrimary .ms-warning", { timeout: 60000 });
  const sim = await page.$("text=Simulate this scenario");
  if (sim) { await sim.click(); await page.waitForSelector("#kpiPrimary .ms-tile", { timeout: 180000 }); }
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined }).catch(() =>
    chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" }));
  // ---- 1366 x 768: the main walkthrough, keyboard only where it matters ----
  {
    const { ctx, page, errors } = await newPage(browser, { viewport: { width: 1366, height: 768 } });
    await ready(page);
    ok("title is the Midshire product title", (await page.title()) === "Midshire University Hospitals Trust Control Tower");
    const body = await page.innerText("body");
    ok("no Cambridge branding on the default screen", !/cambridge|\bCUH\b|addenbrooke/i.test(body.replace(/Set up \/ assumptions/g, "")));
    ok("status line says simulated, not live", body.includes("simulated data, not a live patient feed"));
    await page.screenshot({ path: path.join(OUT, "01_overview_1366x768.png") });
    await page.screenshot({ path: path.join(OUT, "01b_overview_full_1366.png"), fullPage: true });
    // keyboard: tab to the tablist, arrow to Patient flow
    await page.focus("#tab-overview");
    await page.keyboard.press("ArrowRight");
    ok("arrow keys move between tabs", await page.$eval("#tab-flow", e => e.getAttribute("aria-selected") === "true" && document.activeElement === e));
    const focusBg = await page.$eval("#tab-flow", e => getComputedStyle(e).backgroundColor);
    ok("visible yellow focus state", focusBg === "rgb(255, 235, 59)", focusBg);
    // the flow map: five groups left to right, routes drawn between them, moving dots that pause
    await page.waitForSelector("#groupRow path.fm-link", { state: "attached" });
    ok("summary flow map draws the routes between groups", (await page.$$("#groupRow path.fm-link")).length >= 8);
    ok("summary map has arrivals, the five groups and the three merged outcomes",
      (await page.$$("#groupRow .fm-group")).length === 5 && (await page.$$("#groupRow .fm-outcome")).length === 3 && !!(await page.$("#groupRow .fm-source")));
    ok("returns from diagnostics are drawn", !!(await page.$('#groupRow path.fm-link[data-s="diagnostics"][data-d="treatment"]')));
    const xs = await page.$$eval("#groupRow #grp-front_door_wait, #groupRow #grp-initial_assessment, #groupRow #grp-treatment, #groupRow #grp-next_destination", els => els.map(e => e.getBoundingClientRect().left));
    ok("groups run left to right", xs.every((x, i) => i === 0 || x > xs[i - 1]), xs.join(","));
    const dotAt = () => page.$eval("#groupRow circle.fm-dot", c => c.getAttribute("cx") + "," + c.getAttribute("cy"));
    const d0 = await dotAt(); await page.waitForTimeout(500);
    ok("dots move along the routes", (await dotAt()) !== d0);
    await page.click("#flowPause");
    const p0 = await dotAt(); await page.waitForTimeout(500);
    ok("Pause movement stops the animation", (await dotAt()) === p0 && (await page.getAttribute("#flowPause", "aria-pressed")) === "true");
    await page.click("#flowPause");
    await page.screenshot({ path: path.join(OUT, "02_flow_map_1366.png"), fullPage: true });
    // time: change via keyboard on the slider; group numbers follow
    const before = await page.textContent("#grp-treatment .gnum");
    await page.focus("#timeSlider");
    for (let i = 0; i < 16; i++) await page.keyboard.press("ArrowRight");
    const after = await page.textContent("#grp-treatment .gnum");
    ok("slider moves the viewing time (4 hours later)", (await page.textContent("#timeOut")) === "16:00");
    // drill-down: Enter on a group opens detail underneath, focus moves into it, keeps the time
    await page.focus("#grp-treatment");
    await page.keyboard.press("Enter");
    await page.waitForSelector("#groupDetail:not([hidden])");
    const grpBox = await page.$eval("#grp-treatment", e => e.getBoundingClientRect().bottom);
    const detBox = await page.$eval("#groupDetail", e => e.getBoundingClientRect().top);
    ok("detail opens UNDERNEATH the summary row", detBox > grpBox, `${detBox} > ${grpBox}`);
    ok("expanded state announced", await page.$eval("#grp-treatment", e => e.getAttribute("aria-expanded") === "true"));
    ok("detail keeps the selected time", (await page.textContent("#groupDetail")).includes("16:00"));
    const det = await page.textContent("#groupDetail");
    ok("treatment detail lists the adult areas incl. SDEC", ["resus", "majors", "fit-to-sit", "UTC", "SDEC"].every(w => det.toLowerCase().includes(w.toLowerCase())));
    ok("the detail is a map of the group's areas with its routes", (await page.$$("#groupDetail .fm-box.fm-unit")).length >= 6 && (await page.$$("#groupDetail path.fm-link")).length >= 10);
    await page.click("#groupDetail .fm-box.fm-unit >> nth=1");
    await page.waitForSelector("#unitDrill:not([hidden])");
    const drill = await page.textContent("#unitDrill");
    ok("selecting an area opens its day, what serves it and where patients come from and go to", /Patients come from/.test(drill) && /And go on to/.test(drill) && /What serves this area/.test(drill));
    ok("no paediatric area anywhere in the flow", !/paed|child/i.test(await page.textContent("#panel-flow")));
    await page.screenshot({ path: path.join(OUT, "02b_flow_treatment_open_1366.png"), fullPage: true });
    await page.click("#grp-diagnostics");
    ok("diagnostics expands into CT and X-ray", /CT/.test(await page.textContent("#groupDetail")) && /X-ray/.test(await page.textContent("#groupDetail")));
    await page.click("#grp-next_destination");
    const nd = await page.textContent("#groupDetail");
    ok("admission detail shows decision -> bed wait -> transfer, MH sub-route", /Decision to admit/.test(nd) && /inpatient bed/.test(nd) && /Transfer to ward/.test(nd) && /mental-health/i.test(nd));
    await page.keyboard.press("Tab");
    await page.click("text=Close Next destination / leaving ED");
    ok("collapse returns focus to the group", await page.$eval("#grp-next_destination", e => document.activeElement === e));
    // expert view: every modelled step as one map
    await page.click("#expertView summary");
    await page.waitForSelector("#expertMap .fm-box");
    ok("expert view draws the full pathway map", (await page.$$("#expertMap .fm-box")).length >= 20 && (await page.$$("#expertMap path.fm-link")).length >= 30);
    await (await page.$("#expertView")).screenshot({ path: path.join(OUT, "02c_flow_expert_1366.png") });
    await page.click("#expertView summary");
    // typical-day mode labels averages
    await page.click("#modeTypical");
    ok("typical mode says 'average'", /average/i.test(await page.textContent("#groupRow")));
    await page.click("#modeReplay");
    // workforce: target result renders with rota rows and costs
    await page.click("#tab-workforce");
    await page.click("#tgtGo");
    await page.waitForSelector("#searchResult h4", { timeout: 900000 });
    const wr = await page.textContent("#searchResult");
    ok("search result names its outcome honestly", /Target (already met|met in the tested model|not reached within the tested options)/.test(wr));
    ok("package shows extra rota, WTE and cost", /Extra paid hours/.test(wr) && /WTE/.test(wr) && /£/.test(wr));
    ok("lowest-cost wording, never 'optimal'", !/optimal|optimum|guarantee/i.test(wr));
    await page.screenshot({ path: path.join(OUT, "03_workforce_search_1366.png"), fullPage: true });
    // rota edit -> 'changes not yet simulated'
    await page.fill("#rota-row-13 input[type=number]", "11");
    await page.dispatchEvent("#rota-row-13 input[type=number]", "change");
    await page.waitForSelector("#draftBanner:not([hidden])");
    ok("editing the rota shows 'Changes not yet simulated'", /Changes not yet simulated/.test(await page.textContent("#draftBanner")));
    await page.fill("#rota-row-13 input[type=number]", "-1");
    await page.dispatchEvent("#rota-row-13 input[type=number]", "change");
    await page.waitForSelector("#rotaErrors:not([hidden])");
    ok("negative staff count is rejected with a message", /negative/i.test(await page.textContent("#rotaErrors")));
    await page.click("#draftDiscard");
    // scenarios tab
    await page.click("#tab-scenarios");
    await page.screenshot({ path: path.join(OUT, "04_scenarios_1366.png"), fullPage: true });
    // Ask Qbo ED: plain text, structured numbers
    await page.click("#qboOpen");
    await page.fill("#qboIn", "<b>where</b> do patients wait longest?");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.querySelectorAll("#qboLog .bot").length >= 2 && !/Checking the model/.test(document.querySelector("#qboLog").lastElementChild.textContent));
    ok("assistant renders untrusted text as text", await page.$eval("#qboLog", e => e.querySelectorAll("b").length === 0));
    ok("assistant answers from the named waiting measure", /waiting patient-hours/.test(await page.textContent("#qboLog")));
    await page.screenshot({ path: path.join(OUT, "05_ask_qbo_1366.png") });
    await page.keyboard.press("Escape");
    // setup tab
    await page.click("#tab-setup");
    await page.screenshot({ path: path.join(OUT, "06_setup_1366.png") });
    ok("no console or network errors (1366)", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }
  // ---- 1920 x 1080 ----
  {
    const { ctx, page, errors } = await newPage(browser, { viewport: { width: 1920, height: 1080 } });
    await ready(page);
    await page.screenshot({ path: path.join(OUT, "07_overview_1920x1080.png") });
    await page.click("#tab-flow");
    await page.screenshot({ path: path.join(OUT, "08_flow_1920x1080.png") });
    ok("no horizontal page scroll at 1920", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    ok("no console or network errors (1920)", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }
  // ---- narrow (390 px phone) + reduced motion ----
  {
    const { ctx, page, errors } = await newPage(browser, { viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
    await ready(page);
    ok("no horizontal page scroll at 390px", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      await page.evaluate(() => document.documentElement.scrollWidth));
    const tiles = await page.$$eval("#kpiPrimary .ms-tile", els => els.map(e => e.getBoundingClientRect()));
    const overlap = tiles.some((a, i) => tiles.some((b, j) => i < j && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom));
    ok("summary tiles do not overlap at 390px", !overlap);
    ok("reduced motion honoured (no transitions)", await page.evaluate(() => getComputedStyle(document.querySelector(".ms-btn")).transitionDuration === "0s"));
    await page.click("#tab-flow");
    await page.waitForSelector("#groupRow circle.fm-dot", { state: "attached" });
    const r0 = await page.$eval("#groupRow circle.fm-dot", c => c.getAttribute("cx") + "," + c.getAttribute("cy"));
    await page.waitForTimeout(500);
    ok("reduced motion: the flow map does not animate", r0 === await page.$eval("#groupRow circle.fm-dot", c => c.getAttribute("cx") + "," + c.getAttribute("cy"))
      && await page.$eval("#flowPause", b => b.disabled));
    ok("flow map fits the phone width", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.click("#tab-overview");
    await page.screenshot({ path: path.join(OUT, "09_overview_390.png"), fullPage: true });
    await page.click("#tab-flow");
    await page.screenshot({ path: path.join(OUT, "10_flow_390.png"), fullPage: true });
    ok("no console or network errors (390)", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }
  // ---- 200% zoom equivalent: 683 x 384 CSS px at device scale 2 ----
  {
    const { ctx, page, errors } = await newPage(browser, { viewport: { width: 683, height: 384 }, deviceScaleFactor: 2 });
    await ready(page);
    ok("no horizontal page scroll at 200% zoom", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.screenshot({ path: path.join(OUT, "11_overview_zoom200.png") });
    ok("no console or network errors (zoom)", errors.length === 0, errors.join(" | "));
    await ctx.close();
  }
  await browser.close();
  for (const r of results) console.log((r.ok ? "PASS " : "FAIL ") + r.name + (r.detail && !r.ok ? "  [" + r.detail + "]" : ""));
  const failed = results.filter(r => !r.ok).length;
  console.log(`\n${results.length - failed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})();
