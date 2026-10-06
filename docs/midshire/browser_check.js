// Browser checks for the Midshire control tower (not part of CI - needs Chromium).
//   python3 -m uec_hybrid.midshire --port 5055 &      (then)
//   node docs/midshire/browser_check.js http://127.0.0.1:5055 docs/midshire/screenshots
// Uses the globally installed Playwright. Exits non-zero on any failed check.
// Page by page: Overview, Patient flow, Workforce & investment, Scenarios and
// Ask My ED; Selected day for every day offered and Typical day; the baseline
// and a scenario; and the stakeholder wording rules (no seeds, run ids,
// timestamps, warm-up or drain, no "Demo baseline", "Precomputed" or en dashes).
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); }
catch (e) { ({ chromium } = require("/opt/node22/lib/node_modules/playwright")); }

const BASE = process.argv[2] || "http://127.0.0.1:5055";
const OUT = process.argv[3] || "docs/midshire/screenshots";
const results = [];
const ok = (name, cond, detail) => { results.push({ name, ok: !!cond, detail: detail || "" }); };
// words a stakeholder should never see on screen
const TECH = /\bseeds?\b|run id|\bRun [0-9a-f]{6,}|warm-up|\bdrain\b|precomputed|demo baseline|simulated weeks?|replication|fixture|Qbo|Set up \/ assumptions|\d{4}-\d{2}-\d{2}T\d{2}|–|Target not met|✗/i;

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
  const sim = await page.$("text=Run this scenario");
  if (sim) { await sim.click(); await page.waitForSelector("#kpiPrimary .ms-tile", { timeout: 300000 }); }
}
const visibleText = (page) => page.evaluate(() => document.body.innerText);
async function techCheck(page, where) {
  const txt = await visibleText(page);
  const m = txt.match(TECH);
  ok("no technical wording on " + where, !m, m ? m[0] + " ... " + txt.slice(Math.max(0, m.index - 60), m.index + 60).replace(/\s+/g, " ") : "");
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined }).catch(() =>
    chromium.launch({ executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" }));
  // ---- 1366 x 768: the main walkthrough ----
  {
    const { ctx, page, errors } = await newPage(browser, { viewport: { width: 1366, height: 768 } });
    await ready(page);
    ok("title is the Midshire product title", (await page.title()) === "Midshire University Hospitals Trust Control Tower");
    const body = await visibleText(page);
    ok("no Cambridge branding on the default screen", !/cambridge|\bCUH\b|addenbrooke/i.test(body));
    ok("footer is the trust name only", (await page.textContent("footer")).trim() === "Midshire University Hospitals Trust Control");
    ok("Ask My ED in the navigation and no Set up tab", (await page.textContent("#myedOpen")).trim() === "Ask My ED" && !(await page.$("#tab-setup")));
    ok("no simulated-data status line on the Overview", !/simulated data, not a live patient feed/i.test(body));
    const opts = await page.$$eval("#scenarioPick option", os => os.map(o => o.textContent));
    ok("only the Baseline is listed at first", opts.length === 1 && opts[0] === "Baseline", opts.join(", "));
    ok("view labels are Selected day and Typical day", (await page.textContent("#modeReplay")) === "Selected day" && (await page.textContent("#modeTypical")) === "Typical day");
    await techCheck(page, "the Overview");
    await page.screenshot({ path: path.join(OUT, "01_overview_1366x768.png") });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, "01b_overview_full_1366.png"), fullPage: true });

    // Selected day: every day offered, and three times of day; the narrative, cards and context follow
    const days = await page.$$eval("#dayPick option", os => os.map(o => ({ v: o.value, t: o.textContent })));
    ok("the day picker offers Tuesday to Sunday", days.map(d => d.t).join(",") === "Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday", days.map(d => d.t).join(","));
    const seen = new Set();
    let allOk = true, detail = "";
    for (const d of days) {
      await page.selectOption("#dayPick", d.v);
      for (const slot of [16, 48, 80]) {
        await page.$eval("#timeSlider", (e, v) => { e.value = v; e.dispatchEvent(new Event("input", { bubbles: true })); }, String(slot));
        const narr = await page.textContent("#ovNarrative");
        const period = await page.textContent("#periodText");
        const tiles = await page.$$eval("#kpiPrimary .ms-tile .v", vs => vs.map(v => v.textContent));
        // the card's whole-day arrivals and the narrative's count are the same patients
        const arrived = (narr.match(/ (\d+) patients arrived/) || [])[1];
        const whole = ((await page.textContent("#kpiPrimary")).match(/Whole day (\d+) \//) || [])[1];
        const good = narr.includes(d.t) && period.includes(d.t) && tiles.length === 5 && tiles.every(v => v && !/not available|NaN|undefined/.test(v)) &&
          arrived !== undefined && arrived === whole;
        if (!good) { allOk = false; detail = d.t + " " + slot + ": " + narr.slice(0, 80) + " | " + tiles.join(";") + " | whole day " + whole; }
        seen.add(narr);
      }
    }
    ok("every day and time shows its own narrative, context line and five cards, and the day totals agree", allOk, detail);
    ok("the narrative changes with the day", seen.size >= days.length, String(seen.size));
    await page.selectOption("#dayPick", "2");
    await page.$eval("#timeSlider", (e) => { e.value = "48"; e.dispatchEvent(new Event("input", { bubbles: true })); });
    const lead = await page.$("#kpiPrimary .ms-tile-lead");
    ok("the 4-hour card shows name, value, target and a plain status", /Left within 4 hours/.test(await lead.textContent()) && /Target 90%/.test(await lead.textContent()) &&
      /^(On target|Close to target|Below target)$/.test((await lead.$eval(".ms-pill", e => e.textContent)) || ""));
    ok("Selected day help explains Monday", /Monday/.test(await page.textContent("#dayHelp")));
    // Typical day
    await page.click("#modeTypical");
    const tn = await page.textContent("#ovNarrative");
    ok("Typical day narrative describes a typical day", /on a typical day/i.test(tn) && !/Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday/.test(tn), tn.slice(0, 120));
    ok("Typical day context line", /typical day/i.test(await page.textContent("#periodText")));
    ok("the day picker is hidden in Typical day", await page.$eval("#dayWrap", e => e.hidden));
    await techCheck(page, "the Overview (typical day)");
    await page.click("#modeReplay");

    // charts: thick lines and a departures line over the arrival bars
    const lw = await page.$$eval("#chartCensus path[stroke-width]", ps => ps.map(p => +p.getAttribute("stroke-width")).filter(w => w > 0));
    ok("through-the-day lines are at least 3px", lw.length >= 2 && Math.min(...lw) >= 3, lw.join(","));
    ok("arrivals as bars with departures as a line", (await page.$$("#chartFlow path")).length > 24 && /Departures/.test(await page.textContent("#chartFlow .legend")));

    // Patient flow
    await page.focus("#tab-overview");
    await page.keyboard.press("ArrowRight");
    ok("arrow keys move between tabs", await page.$eval("#tab-flow", e => e.getAttribute("aria-selected") === "true" && document.activeElement === e));
    const focusBg = await page.$eval("#tab-flow", e => getComputedStyle(e).backgroundColor);
    ok("visible yellow focus state", focusBg === "rgb(255, 235, 59)", focusBg);
    await page.waitForSelector("#groupRow path.fm-link", { state: "attached" });
    ok("summary flow map draws the routes between groups", (await page.$$("#groupRow path.fm-link")).length >= 8);
    ok("summary map has arrivals, the five groups and the three merged outcomes",
      (await page.$$("#groupRow .fm-group")).length === 5 && (await page.$$("#groupRow .fm-outcome")).length === 3 && !!(await page.$("#groupRow .fm-source")));
    ok("returns from diagnostics are drawn", !!(await page.$('#groupRow path.fm-link[data-s="diagnostics"][data-d="treatment"]')));
    const dotAt = () => page.$eval("#groupRow circle.fm-dot", c => c.getAttribute("cx") + "," + c.getAttribute("cy"));
    const d0 = await dotAt(); await page.waitForTimeout(500);
    ok("dots move along the routes", (await dotAt()) !== d0);
    await page.click("#flowPause");
    const p0 = await dotAt(); await page.waitForTimeout(500);
    ok("Pause movement stops the animation", (await dotAt()) === p0 && (await page.getAttribute("#flowPause", "aria-pressed")) === "true");
    await page.click("#flowPause");
    ok("flow legend names the day and time", /on Thursday/.test(await page.textContent("#flowLegend")));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, "02_flow_map_1366.png"), fullPage: true });
    await page.focus("#timeSlider");
    for (let i = 0; i < 16; i++) await page.keyboard.press("ArrowRight");
    ok("slider moves the viewing time (4 hours later)", (await page.textContent("#timeOut")) === "16:00");
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
    ok("selecting an area opens its day, staff and space, and where patients come from and go to", /Patients come from/.test(drill) && /And go on to/.test(drill) && /Staff and space/.test(drill));
    ok("no paediatric area anywhere in the flow", !/paed|child/i.test(await page.textContent("#panel-flow")));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, "02b_flow_treatment_open_1366.png"), fullPage: true });
    await page.click("#grp-diagnostics");
    ok("diagnostics expands into CT and X-ray", /CT/.test(await page.textContent("#groupDetail")) && /X-ray/.test(await page.textContent("#groupDetail")));
    await page.click("#grp-next_destination");
    const nd = await page.textContent("#groupDetail");
    ok("admission detail shows decision -> bed wait -> transfer, MH route", /Decision to admit/.test(nd) && /inpatient bed/.test(nd) && /Transfer to ward/.test(nd) && /mental-health/i.test(nd));
    await page.click("text=Close Next destination / leaving ED");
    ok("collapse returns focus to the group", await page.$eval("#grp-next_destination", e => document.activeElement === e));
    const oc = await page.$$eval("#outcomeRow .ms-tile", ts => ts.map(t => t.textContent));
    ok("leaving cards: short labels and prominent values", oc.length === 3 && /^Went home/.test(oc[0]) && /^Admitted/.test(oc[1]) && /^Left without being seen/.test(oc[2]) && oc.every(t => /% of patients/.test(t)));
    await page.click("#expertView summary");
    await page.waitForSelector("#expertMap .fm-box");
    ok("expert view draws every step", (await page.$$("#expertMap .fm-box")).length >= 20 && (await page.$$("#expertMap path.fm-link")).length >= 30);
    await (await page.$("#expertView")).screenshot({ path: path.join(OUT, "02c_flow_expert_1366.png") });
    await page.click("#expertView summary");
    await techCheck(page, "Patient flow");
    await page.click("#modeTypical");
    ok("typical mode says 'average'", /average/i.test(await page.textContent("#groupRow")) && /typical day/.test(await page.textContent("#flowLegend")));
    ok("typical-day map shows whole patients, not decimals", !/\d\.\d/.test(await page.textContent("#groupRow")), (await page.textContent("#groupRow")).match(/\d\.\d/g));
    await page.click("#modeReplay");

    // Workforce & investment: the decision journey
    await page.click("#tab-workforce");
    ok("the target reads as a sentence", /of patients leave the department within/.test(await page.textContent("#targetForm")) && /Now: .*% of patients/.test(await page.textContent("#targetNow")));
    ok("change options are plain", (await page.$$eval("#tgtMode option", os => os.map(o => o.textContent))).join("|") === "Staffing only|Space and beds, with the staff they need|Staffing, space and beds");
    await page.click("#tgtGo");
    await page.waitForSelector("#searchResult h4", { timeout: 900000 });
    const wr = await page.textContent("#searchResult");
    ok("search result names its outcome plainly", /Already on target|Reaches the [0-9.]+% target|The tested changes don't reach [0-9.]+%/.test(wr));
    ok("package shows changes, effect, cost and staff", /Effect on patients/.test(wr) && /What it costs/.test(wr) && /whole-time equivalent|none/.test(wr) && /£/.test(wr));
    ok("lowest-cost wording, never 'optimal'", !/optimal|optimum|guarantee/i.test(wr));
    const steps = await page.$$eval("#journey .ms-step", s => s.map(x => x.querySelector(".k").textContent + "=" + x.querySelector(".v").textContent));
    ok("journey shows Now -> Target -> Changes -> Expected -> Extra cost", steps.length === 5 && steps[0].startsWith("Now=") && steps[4].startsWith("Extra cost=") && !steps.some(s => s.endsWith("=-")), steps.join(" | "));
    ok("staffing coverage is daily only", (await page.textContent("#editorCard")).includes("Staff on shift through the day") && !/weekly view|instant preview|no simulation/i.test(await page.textContent("#editorCard")));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, "03_workforce_search_1366.png"), fullPage: true });
    await page.fill("#rota-row-13 input[type=number]", "11");
    await page.dispatchEvent("#rota-row-13 input[type=number]", "change");
    await page.waitForSelector("#draftBanner:not([hidden])");
    ok("editing the rota shows 'Changes not run yet'", /Changes not run yet/.test(await page.textContent("#draftBanner")));
    await page.fill("#rota-row-13 input[type=number]", "-1");
    await page.dispatchEvent("#rota-row-13 input[type=number]", "change");
    await page.waitForSelector("#rotaErrors:not([hidden])");
    ok("negative staff count is rejected with a message", /negative/i.test(await page.textContent("#rotaErrors")));
    await page.click("#draftDiscard");
    await techCheck(page, "Workforce & investment");

    // Scenarios: cards; opening one puts it on every page and in the picker
    await page.click("#tab-scenarios");
    const cards = await page.$$eval("#scenarioTable .ms-sc-card", cs => cs.map(c => c.textContent));
    ok("every non-baseline scenario says what changes, why and what to look for",
      cards.length >= 2 && cards.slice(1).every(c => /What changes/.test(c) && /Why test it/.test(c) && /What to look for/.test(c)), String(cards.length));
    await techCheck(page, "Scenarios");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, "04_scenarios_1366.png"), fullPage: true });
    const viewBtn = await page.$("#scenarioTable .ms-sc-card:nth-child(2) button:has-text('View on every page')");
    const scName = await page.$eval("#scenarioTable .ms-sc-card:nth-child(2) .ms-sc-title", e => e.textContent);
    await viewBtn.click();
    await page.waitForFunction((n) => document.querySelector("#periodText").textContent.includes(n), scName, { timeout: 300000 });
    const pick = await page.$$eval("#scenarioPick option", os => os.map(o => o.textContent));
    ok("an opened scenario joins the picker", pick.includes(scName) && pick[0] === "Baseline", pick.join(", "));
    await page.click("#tab-overview");
    await page.waitForSelector("#kpiPrimary .ms-tile", { timeout: 300000 });
    ok("scenario narrative and cards compare with the baseline", (await page.textContent("#ovNarrative")).includes("With \"" + scName + "\"") && /baseline/i.test(await page.textContent("#kpiPrimary")));
    await page.click("#modeTypical");
    ok("scenario typical-day narrative", /on a typical day/.test(await page.textContent("#ovNarrative")) && /The baseline is/.test(await page.textContent("#ovNarrative")));
    await page.click("#modeReplay");
    await techCheck(page, "the Overview with a scenario");

    // Ask My ED: plain text, plain words, suggestions
    await page.click("#myedOpen");
    ok("Ask My ED offers suggested questions", (await page.$$("#myedSuggest .ms-chip")).length >= 3);
    await page.fill("#myedIn", "<b>where</b> do patients wait longest?");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.querySelectorAll("#myedLog .bot").length >= 2 && !/Checking/.test(document.querySelector("#myedLog").lastElementChild.textContent));
    ok("assistant renders untrusted text as text", await page.$eval("#myedLog", e => e.querySelectorAll("b").length === 0));
    const ans = await page.textContent("#myedLog");
    ok("assistant answers in plain words from the waiting measure", /hours a day/.test(ans) && !TECH.test(ans), ans.slice(-200));
    ok("suggestions fold away once the conversation starts", !(await page.$eval("#myedSuggestWrap", e => e.open)));
    await page.click("#myedSuggestWrap > summary");
    await page.click("#myedSuggest .ms-chip >> nth=0");
    await page.waitForFunction(() => !/Checking/.test(document.querySelector("#myedLog").lastElementChild.textContent));
    ok("'How are we doing?' answers for the day on screen", /On Thursday|on Thursday/.test(await page.$eval("#myedLog", e => e.lastElementChild.textContent)));
    await page.screenshot({ path: path.join(OUT, "05_ask_my_ed_1366.png") });
    await page.keyboard.press("Escape");
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
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, "09_overview_390.png"), fullPage: true });
    await page.click("#tab-flow");
    await page.evaluate(() => window.scrollTo(0, 0));
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
