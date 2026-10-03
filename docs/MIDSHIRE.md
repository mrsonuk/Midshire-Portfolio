# Midshire University Hospitals Trust Control Tower

An **adult ED simulation and planning demonstrator** for the South East Region
show-and-tell (16 October 2026). Midshire is a **fictional** demonstration
identity: not a real trust, not a live patient-monitoring service, not a
clinically validated staffing tool and not a connected digital twin. It is built
on the Cambridge (RGT) control tower in this repository and leaves that build
intact.

```
python3 -m uec_hybrid.midshire                 # http://127.0.0.1:5050
```

## 1. Branch and sources

| | |
|---|---|
| Branch | `ccr-ae0984af-leeqpw` (the session's designated branch; the brief suggested `claude/midshire-control-tower-se-demo`) |
| Cambridge base | `claude/cambridge-control-tower-setup` @ `8dd0117e9e0d460630bfefc4fb522eadca8b2436` (this branch descends from it; checked by test 1) |
| Workforce reference | `claude/affectionate-euler-u0dhnz` @ `df0ddd206e700f038c272f108bf9463aaf90844f` (read only; UI ideas ported, backend not) |

Neither source branch was changed, merged into, reset or force-pushed.

## 2. Meeting requirements → where they are

| Requirement | Implemented in |
|---|---|
| Midshire name, Cambridge branding removed | `app/templates/midshire.html` (exact title, no logo), `midshire.js`; branding test (2). Provenance kept on Set up / assumptions |
| Adult pathway only | `midshire/build.py` `adult_patch` + `make_adult`: demand reduced by the source trust's paediatric-area share (400.5 → 347.0/day), paediatric area, staff, routes, attribute and metrics removed; test 3 |
| Overall performance first, then the day's pattern | Overview: five primary tiles (present, waiting, within target, arrivals/departures, median time), secondary row, through-the-day chart, "Where waits build up" |
| Left-to-right pathway, ≤5 groups, detail below | Patient flow: a Cambridge-style animated **flow map** of the five groups (arrivals on the left, the three merged outcomes on the right, diagnostics drawn as the branch patients go to and return from). Selecting a group opens a **map of its areas underneath**; selecting an area opens its day, what serves it and where its patients come from and go to. The **full pathway map** is the expert view. Groups and map boxes (`groups`, `flow_map.units` in `data/midshire/midshire_demo.json`) are by stable node id; moving dots can be paused and are off under reduced motion; every map has a table view |
| Present / waiting / time waiting / arrivals / departures distinguished | `midshire/metrics.py` metric contract (`DEFINITIONS`); every tile states snapshot vs whole run |
| SDEC from streaming and from RAT | `build.add_sdec`: streaming → SDEC, streaming → RAT → SDEC, handover → RAT → SDEC; explicit closed redirect `sdec_closed`; 90-minute wait limit redirect; test 4 |
| Discharge outcomes merged in summary, admission detail merged, MH sub-route kept | Outcomes row (Discharged / Admitted / Left without being seen); group 5 detail |
| Decision to admit → waiting for bed → transfer to ward | `build.add_decision_to_admit`: DTA is a zero-length milestone (event count), the bed wait is an occupied state, ward transfer completes the departure; test 5 |
| Data shows where waits accumulate | "Waiting patient-hours per day" ranking (named measure); no stage pre-selected |
| Workforce and estates layers with an investment story | Workforce & investment: target → package search → extra rota rows, WTE, pay, estate, capital, recurring, annualised comparison cost → save / apply / compare |
| Rota and cost inputs end to end | Rota editor, CSV import/export, cost table, estates costs, instant preview, simulate, save; `workforce/rota.py`, `workforce/costing.py` |

## 3. What changed

**New (Midshire):** `uec_hybrid/midshire/` — `config.py` (fixture, groups, hashes),
`build.py` (the one build pipeline), `metrics.py` (metric contract), `runner.py`
(matched-seed replications, replay, cache), `store.py` (separate database),
`packages.py` (levers, staffing dependencies, costing, re-timing),
`optimise.py` (package search), `jobs.py` (progress / cancel),
`assistant.py` (Ask Qbo ED), `server.py` (API + page), `precompute.py`,
`validate.py`; `app/templates/midshire.html`, `app/static/midshire.{js,css}`;
`data/midshire/midshire_demo.json` and `data/midshire/precomputed/`;
`tests/midshire.py`; `docs/midshire/browser_check.js`.

**Shared fixes (also affect the Cambridge build; see `docs/CUH_DATA_LOG.md`,
"Engine 0.5.0"):**

* `des/engine.py` — rota reductions take effect at once (all off-shift requests
  lodged together); a zero capacity or zero-everywhere roster is a parked unit,
  never a fictitious member of staff; 168-hour (hour-of-week) rosters; an
  RNG-neutral state trace (carry-in and unfinished journeys included); opt-in
  patience for a space (`renege_includes_space`).
* `workforce/rota.py` — no floor of one; day patterns (`days`), overnight
  convention (a shift belongs to the day it starts), unpaid breaks, row
  validation, CSV import/export, legacy rows migrate to "every day".
* `workforce/costing.py` — **one cost service** (fully loaded or basic +
  on-cost + enhancement + agency blend; blank = not costed, 0 = £0) used by the
  Cambridge pay-bill, the recommender and everything in Midshire.
* `department/config.py`, `department/builder.py` — explicit rota provenance
  (`rota_source`, with a tested migration rule); `resolved_rota` is the one place
  the template is scaled, so engine, view and cost use the same rota; a general
  space-staffing table (open = min(physical, staff × ratio)); explicit zeros kept;
  zero-capacity warnings.
* `optimise/recommend.py` — shift costs from the cost service; candidate shifts
  are added to the resolved rota (they used to un-scale the whole template).
* `workforce/view.py` — shows the resolved rota; the demand-shape "light
  against demand" hours are labelled a secondary heuristic.
* `sd/model.py` — optional `initial_occupied_beds` so new beds start empty.

**Ported from the workforce reference branch (rewritten, not merged):** the rota
table editor with add/remove rows, hourly coverage bars per staff group, and
"apply and re-run". Its backend modules were not copied: the Cambridge versions
are newer.

**Cambridge behaviours preserved:** the Cambridge app, seed, calibration patch,
`rgt_published.json`, `model_ed.json`, the seed workbook and `data/cuh/` are
unchanged (hash-checked by test 1); the full Cambridge suite still passes.

## 4. How the numbers are made (the metric contract)

Every number comes from patient-level **state intervals**: for each patient,
when they entered and left each step, split into "waiting" and "being seen".

* **Snapshot** (single simulated day): integer counts from ONE replication at a
  15-minute point; census = arrived and not yet left; group counts sum exactly to
  the census; census at t = census at the day start + arrivals − departures
  (checked on every run).
* **Typical day**: averages by hour of day, labelled "average simulated
  patients"; arrivals/departures divided by the observed days.
* **Whole run**: each simulated week reduced first, then mean, range, and the
  simulation-noise interval of the mean across weeks.
* **Total time waiting** is the union of a patient's waiting intervals; **time in
  the department** is per patient. Neither is a sum of stage averages.
* **Within the target time**: eligible adult attendances = everyone arriving in
  the observed days, no exclusions; SDEC time counts inside the ED attendance;
  a 12-hour drain follows; anyone still present has exceeded the target and is
  counted as not met and reported as unfinished.
* **Where waits build up** = waiting patient-hours per day by step (never an
  area's own peak, never volume).
* **Flow-map lines** = patients a day moving between boxes over the whole run
  (`metrics.flow_links`, from the same state intervals): at group, area and step
  level, arrivals in, outcomes out, returns included. A box's moves in minus moves
  out equal its change in occupancy, and the group lines are the area lines added
  up (checked by test 6). A box's top border compares it with its own busiest
  moment of the day; the "most waiting now" badge is the box with the most
  patients waiting at the viewing time.

## 5. The package search

See the docstring of `uec_hybrid/midshire/optimise.py`, shown on screen under
"Search method, bounds and limits". In short: matched selection seeds, every
candidate package re-simulated in full, two greedy paths (largest effect;
best value per £), pruning, guardrails (walk-outs, unfinished patients),
ranking by a named **annualised comparison cost** (recurring + capital / 15
years), partially costed packages never ranked as cheapest, and the shortlist
re-run on a **separate validation seed set**. Staffing dependencies of space
are computed, not hard-coded. Possible outcomes: target already met; met in the
tested model; not reached within the tested options (with best tested, gap,
bounds and the limiting evidence). It is the "lowest-cost package found within
the tested options", never a proven optimum, and "not reached" never means
impossible in a real hospital.

## 6. Results (filled from the committed runs)

All figures below are simulation outputs of the fictional Midshire build, not
observations. "Weeks" are simulated weeks (1-day warm-up, 6 observed days,
12-hour drain); ± and intervals are simulation noise only.

**Baseline** (committed precomputed run, selection seeds 101-106)

| Measure | Mean | Range over 6 weeks |
|---|---|---|
| Within 4 hours (eligible adults) | 66.5% | 63.0-70.0% |
| Over 12 hours from arrival | 10.0% | 9.2-12.0% |
| Median time in department | 182 min | 173-193 |
| Median total time waiting | 52 min | 43-67 |
| Left without being seen | 1.2% | 0.4-2.2% |
| Admitted | 17.9% | 16.5-18.9% |
| Streamed to SDEC | 6.8% | 6.2-7.7% |
| Ambulance handover within 45 min | 94.7% | 90.5-98.2% |
| Initial assessment within 15 min | 85.1% | 83.6-87.1% |
| Decision to admit → departure, median | 421 min | |

Where waits build up (waiting patient-hours per day): waiting for an inpatient
bed ≈ 406, awaiting results/review/decision ≈ 286, then the UTC and majors
queues. These two are modelled durations that no lever in the search shortens,
which is why every search below stops short of 90%.

**Package searches** (precomputed; every candidate re-simulated on the same 6
selection weeks, the shortlist re-run on 8 separate validation weeks 9001-9008,
validation baseline 68.6%)

| Search | Outcome | Package found | Selection weeks | Validation weeks | Cost |
|---|---|---|---|---|---|
| Combined, 90% | Not reached | +1 CT scanner, +4 fit-to-sit spaces | 70.4% (+3.9 pts, 95% CI +0.9 to +7.0) | 70.3% (+1.7 pts, CI +0.1 to +3.3) | £1.224m capital, £152k/yr recurring; annualised comparison cost £233.6k/yr |
| Workforce only, 90% | Not reached | +1 RAT senior decision-maker 10:00-22:00, every day (84 paid h/week, 2.1 WTE) | 68.5% (+2.0, CI −0.3 to +4.3) | 67.9% (−0.6, CI −2.7 to +1.5) | £300.5k/yr pay |
| Estate with staffing, 90% | Not reached | +20 inpatient beds, +1 CT, +4 fit-to-sit, +1 resus bay (+ resus nurses), +3 UTC rooms (+ UTC practitioners) | 71.0% (+4.5, CI +1.5 to +7.4) | 69.7% (+1.1, CI −0.1 to +2.3) | **Partially costed**: bed capital not supplied; £1.524m costed capital, £3.67m/yr recurring incl. 7.5 WTE |
| Combined, 70% | Met in the tested model | the same CT + fit-to-sit package | 70.4% | 70.3% | as above |

Read honestly: the workforce-only package's gain does not survive the
validation weeks (its interval crosses zero), and the estate package's
validation interval also crosses zero. Only the CT + fit-to-sit package
shows a validated gain, and that gain is small (+1.7 points). None of these is a
proven optimum or a forecast.

**Validation and conformance** (`python3 -m uec_hybrid.midshire.validate`)

* Conformance: 12,735 simulated journeys, 0 pathway violations.
* Per-area median time in department vs the source trust's June 2026 figures
  (the source trust's areas, all ages; a reference, not a target): resus 393 min
  (1.21x), majors trolleys 759 (1.05x), majors ambulant 164 (0.64x), minors 162
  (0.99x), SDEC 224 vs the illustrative 247 (0.91x). Ambulant is short because
  adults no longer queue behind children for shared streaming and imaging.
* Why Midshire's 4-hour figure is higher than Cambridge's, computed on 16
  matched weeks (standard error about ±0.6-0.9 per step): source model all ages
  52.6% → adults within it 53.1% → children removed from demand 58.9% →
  Midshire pathway/rota/capacity with every MH patient admitted 59.0% → real
  MH admission rate 62.8% → illustrative SDEC streaming 67.1%.

**Cambridge (RGT) after the shared engine fixes**
(`python3 -m uec_hybrid.validation.against_trust RGT`): 4-hour 55.3% vs
published 52.9%; 12-hour 11.0% vs 10.0%; handover within 45 min 93.1% vs
84.2%; LWBS 1.9%; per-area time in department resus 1.11x, majors trolleys
0.94x, majors ambulant 0.88x, minors 1.00x, paediatrics 1.49x (still outside
tolerance, as before this work; see `docs/CUH_DATA_LOG.md`, "Engine 0.5.0").

**Tests**

* `python3 -m uec_hybrid.tests.run`: the full Cambridge suite plus the 18
  Midshire acceptance checks (`uec_hybrid/tests/midshire.py`) pass.
* Browser checks (`docs/midshire/browser_check.js`, Playwright + Chromium, run
  locally): 42 passed, 0 failed, at 1366×768, 1920×1080, 390 px with reduced
  motion and a 200% zoom equivalent; no console or network errors.

| Brief acceptance test | Where it is checked |
|---|---|
| 1 Descends from Cambridge, protected data unchanged | `tests/midshire.py` check 1 (ancestry of `8dd0117e`, hashes of protected files and `data/cuh/`) |
| 2 Exact name, adult-only, provenance, no Cambridge branding | check 2; browser: title, branding, status line |
| 3 Paediatrics excluded everywhere | checks 3a (build: no node, route, resource, attribute, rota row) and 3b (cohort, denominator); browser: no paediatric area in the flow |
| 4 Both SDEC routes, closed fallback, distinct outcomes | check 4a |
| 5 Decision to admit → bed wait → transfer | check 5 |
| 6 Snapshot reconciles, carry-in and unfinished included | check 6 (and the flow maps: every box balances, arrivals and departures match at three levels) |
| 7 Durations and waiting from patient intervals | check 7 (controlled three-patient fixture) |
| 8 Groups expand underneath, keep time, adult detail | browser checks (flow map routes and order, detail map below the summary, `aria-expanded`, time kept, area drill, diagnostics / treatment / admission content, focus returns on close, expert map) |
| 9 Rota overnight, day patterns, rejects, blank ≠ 0, no floor | check 9; browser: negative count rejected |
| 10 One resolved staffing for editor, engine and cost | check 10 |
| 11 Cost-only edits move money, not performance; uncosted ≠ £0 | check 11 |
| 12 Non-binding capacity, closure, no lost patients | check 12/14 |
| 13 Target workflow honest, no hard-coded 90% | check 13/14; browser: outcome wording, rota/WTE/£ shown, never "optimal" |
| 14 Full re-runs, guardrails, variation; nurses cannot make space | checks 12/14 and 13/14 |
| 15 Save / apply / reload / reset; stale results; out-of-order responses | check 15; request sequence guards in `midshire.js` |
| 16 Qbo and exports reconcile; untrusted input safe | check 16; browser: markup rendered as text |
| 17 Keyboard, drill-down, reduced motion, contrast, zoom, responsive | check 17 (static) plus the browser script |
| 18 Fresh checkout starts from committed files | check 18 |

**Screenshots** (`docs/midshire/screenshots/`): `01_overview_1366x768.png`,
`01b_overview_full_1366.png`, `02_flow_map_1366.png`, `02b_flow_treatment_open_1366.png`, `02c_flow_expert_1366.png`,
`03_workforce_search_1366.png`, `04_scenarios_1366.png`,
`05_ask_qbo_1366.png`, `06_setup_1366.png`, `07_overview_1920x1080.png`,
`08_flow_1920x1080.png`, `09_overview_390.png`, `10_flow_390.png`,
`11_overview_zoom200.png`.

**Fixtures:** `uec_hybrid/data/midshire/midshire_demo.json` (the demo identity,
adult cohort, capacity, illustrative rota, costs, estates, levers; every value
sourced or labelled) and `uec_hybrid/data/midshire/precomputed/` (baseline and
four searches, stamped with model hash, engine 0.5.0, seeds and source commit;
ignored as stale if the inputs or engine change).

## 7. Presenter walkthrough (about 8 minutes)

Before the session: `python3 -m uec_hybrid.midshire`, open http://127.0.0.1:5050,
and if anything was changed in rehearsal use Scenarios → **Reset to demo
baseline**. Everything below opens on committed, labelled precomputed results.

1. **Overview (1 min).** Point at the yellow status line: *adult ED planning
   demonstrator, simulated data, not a live patient feed*. The scenario badge
   says "Precomputed result · 6 simulated weeks". Read the five tiles left to
   right: patients in the department and waiting **now** (one simulated day, at
   the viewing time); the share completed within four hours against the 90%
   planning target (whole run, with its range and "target not met"); arrivals
   and departures in the last hour; median time in the department.
2. **Select a time (30 s).** Drag the viewing-time slider to about 16:00 (or
   press Play). The census and waiting lines and the tiles move together; the
   vertical line marks the time. Switch "Typical day (average)" to show the
   averaged profile is labelled differently, then switch back.
3. **Find where waits accumulate (1 min).** "Where waits build up" ranks steps
   by waiting patient-hours per day. Say what it is measured by, and that the
   model chose it - the bed wait and the results/decision wait lead in the
   baseline, not because they were assumed.
4. **Walk the flow map, then expand a stage (2 min).** Patient flow: the
   department as one picture - arrivals, the five groups left to right, the
   three outcomes, with diagnostics as the loop patients go out to and come back
   from. Line width is patients a day; the badge marks where most patients are
   waiting *now*. Drag the slider from 04:00 to 16:00 and watch the boxes fill
   and the badge move. Open *Clinical assessment and treatment* - a map of its
   areas opens underneath (resus, majors, fit-to-sit, UTC, SDEC, frailty unit,
   results and decision), with the groups and outcomes it connects to. Select
   *Majors cubicles*: its day, the staff and spaces serving it now, and where its
   patients come from and go to. Open *Next destination*: decision to admit (an
   event count), waiting for a bed (patients still on their trolley), transfer
   to the ward, and the mental-health sub-route. The expert view draws every
   modelled step.
5. **Set the 90% target (1 min).** Workforce & investment → 90% within 4 hours,
   "Combined workforce and estate packages" → Find a package. It returns
   "Target not reached within the tested options", the best tested package, the
   gap, the separate validation-week result, and what limits it.
6. **Inspect the added shifts, space and costs (1.5 min).** Walk the rota rows
   (role, days, hours, baseline → proposed, extra paid hours, WTE, weekly and
   annual cost, why), the estate rows (capital, recurring), and the cost table
   (recurring, capital, annualised comparison cost; nothing priced at £0 that is
   not costed). Change the target to 70%: "Target met in the tested model" and
   the **lowest-cost package found within the tested options**, with the other
   ranked packages.
7. **Apply and compare (1 min).** "Save as a scenario", pick it in the scenario
   picker (every screen switches; the baseline is untouched), then Scenarios →
   tick it → Compare: target, difference in percentage points with its noise
   interval, 12-hour, walk-outs, unfinished patients, extra shifts, hours, pay,
   estate, capital. Optionally ask Ask Qbo ED "what workforce and space changes
   would get 90% through within four hours?".
8. **Explain the remaining constraints (1 min).** No staffing or space lever in
   the tested set shortens the results/decision step or the aggregate bed wait,
   so 90% is not reached *in this model*; that is not a claim about a real
   hospital. Set up / assumptions lists what is illustrative (rota, costs, SDEC
   size and streaming, space-staffing ratios) and that the adult build is not
   validated against a real adult-only department.

## 8. Residual limitations

* **Not validated.** The adult-only, SDEC-extended build does not inherit the
  Cambridge validation. `python3 -m uec_hybrid.midshire.validate` reports
  conformance and a per-area comparison, but nothing confirms it matches a real
  adult department.
* **Removing children frees shared capacity.** In the source build children
  share imaging, streaming and the bed model with adults; removing them lifts
  the adults' four-hour figure (measured in the decomposition above). No
  paediatric "background load" is simulated, because that would reintroduce the
  incomplete paediatric detail the meeting asked to drop.
* **SDEC benefit is an upper bound.** SDEC patients are picked at random within
  acuity 2-3 (the model cannot pick the clinically suitable ones), skip the ED
  imaging and results/decision steps and are admitted at SDEC's 16.1% rate. The
  streaming shares are illustrative.
* **Fixed durations.** Time awaiting results/review/decision and the bed-wait
  multiplier are modelled durations; no lever in the search shortens them, which
  is what caps the tested packages.
* **Aggregate bed model.** One bed stock; discharges scale with occupancy, so new
  beds tend to fill to the same occupancy fraction (they start empty here). The
  inherited bed stock also drifts from 89% to about 80-85% occupancy over a
  simulated week. No ward allocation, no day-of-week discharge pattern.
* **No community route.** The source trust's 1 virtual-ward place a day cannot be
  represented by the hourly community-pull signal without over-diverting, so
  Midshire models none.
* **Hourly rota granularity**; the engine treats everyone rostered as present
  for the whole shift (breaks covered); the ED doctor pool treats consultants,
  registrars and juniors as interchangeable (stated on screen); radiographer
  staffing is not modelled.
* **Uncertainty** is simulation noise only (6 selection weeks, 8 validation
  weeks); the ranges and intervals are not forecasts of real weeks.
* **Browser checks** run locally with Playwright (`docs/midshire/browser_check.js`),
  not in CI. Frutiger is not shipped (no licence); Arial is used.
