# Model ED Optimiser - Engineering Handover

**Audience:** the next engineer or team taking this on.
**State:** Phases 0-3 of the rebuild plan complete (benchmarking + intraday
prediction), plus a **data-input layer** so a department is configured with no
code/JSON: pick-your-trust from an open-data snapshot, Excel/CSV workbook import,
and editable-as-data costs, scorecard targets and service-time assumptions; the
analyst surfaces now carry interpretations, clickable flow blocks and per-stage
timing. Companion documents: `docs/PRODUCT_REBUILD_PLAN.md` (strategy and
roadmap), `README.md` (product overview + full tab-by-tab guide).

---

## 1. What this is

A commercial-track product that helps NHS trusts design, staff and run a
high-performing emergency department, built on the NHS England "Model
Emergency Department" blueprint. Under the surface it is a hybrid
simulation: a patient-level Discrete-Event Simulation (SimPy) coupled hourly
to a System-Dynamics model of the hospital around the ED, wrapped in
Monte-Carlo for honest uncertainty. None of that vocabulary appears on the
product surfaces.

Four user surfaces, one Flask app, one saved department shared by all:

| Surface | Route | Audience |
|---|---|---|
| Executive brief | `/exec` | COO / ED director: OPEL risk, RAG standards, peer position, investment case, one-click board PDF |
| Control tower | `/` | ED ops: live flow map with drill-downs, workforce studio, Model ED gap analysis, department set-up, recommendation engine |
| Demand & capacity planner | `/planner` | ICB / winter planning: forecast, costed options, surge stress tests, intraday "today" mode |
| Analyst view | `/analyst` | Analysts: the full technical model - scorecard, SD charts, Monte-Carlo, scenarios, Sankey/heatmap, conformance validation, ECDS calibration |
| React shell | `/app` | The strangler-fig migration target (exec brief ported so far) |

## 2. Quick start

```bash
pip install -r requirements.txt
python -m uec_hybrid.app.server      # product at http://127.0.0.1:5000
python -m uec_hybrid.tests.run       # end-to-end suite (29 checks, ~8 min)

cd web && npm install && npm run build   # only when changing the React app
python -m uec_hybrid.report              # standalone decision-report PDF
```

- SQLite database `uec_platform.sqlite3` is created at the repo root on first
  run (gitignored). Set `DATABASE_URL` (or `UEC_DATABASE_URL`) for Postgres.
- `web/dist` is committed (vendored, like `plotly.min.js`) so the product runs
  with pip alone on locked-down NHS networks. Rebuild it whenever `web/src`
  changes.
- Everything is offline-capable by design: no CDNs, no external calls.

## 3. Architecture

```
templates (product/planner/exec/analyst) + static JS     web/ (React+TS at /app)
                       |                                        |
                 Flask app/server.py  <-- one route file, JSON APIs
                       |
   +----------- domain services ------------+
   | analysis/  (KPIs, scorecard, MC,       |
   |            scenarios, benchmark)       |
   | planning/  (forecast, planner,         |
   |            operational, surge)         |
   | optimise/  (recommendation engine)     |
   | finance/   (cost book, business cases) |
   | viz/       (flow model, Plotly figs)   |
   | report.py  (board PDF)                 |
   +--------------------+-------------------+
                        |
   ingest/: pick-your-trust (data/nhs_trust_snapshot.csv) + Excel/CSV workbook import
                        |
        department/ builder: Department config -> runnable pathway raw
        model_params.py: editable service-time overlay (global scale / per-stage means)
                        |
   simulation kernel: des/ (SimPy engine) <-> sd/ (hospital stocks)
                      coupled by coupling/ (CoSimulator, SystemState)
                      validated by validation/ (conformance vs reference map)
                        |
        demand/: streams, population determinants, ECDS calibration seam
        pathways/model_ed.json: THE data definition of the Model ED (structure only)
                        |
        platform/store.py: SQLite/Postgres persistence + run cache + settings
                          (cost book, role rates, scorecard targets, service-time params)
```

### 3.1 The kernel (do not casually rewrite)

- **`des/engine.py`** - the SimPy engine. Key physics:
  - Acuity **priority queues** (sickest first) on every resource.
  - **Span-held spaces** (`acquire`/`release`): a cubicle is held across
    imaging until disposition releases it.
  - **Time-varying staffing**: a resource whose capacity is a 24-list becomes
    a rostered resource (a shift manager parks off-shift units).
  - **Arrival streams** (`arrivals.streams`): per-hour SHARE partitions of the
    one `hourly_profile`, each with its own acuity mix and pinned attributes.
    Because they are shares, all demand scaling stays a single knob.
  - **Reneging** (`node.renege`): patients abandon the queue when a sampled
    patience runs out -> the LWBS outcome. Partial acquisitions are released
    or cancelled; exits are conformance-legal via renege edges.
  - **Ambulance handover**: ambulance-stream patients pass through
    `ambulance_handover`, seizing a `handover_bay` that is HELD until
    streaming completes - crowding physically blocks bays and queues vehicles.
  - **Holds** are logged from each resource's grant time, so utilisation
    includes time blocked on a node's other resources.
- **`sd/`** - homeostatic stocks (inpatient beds, MH beds, community) with
  smooth bounded feedback. High occupancy raises `bed_wait_multiplier`, which
  stretches the `await_inpatient_bed` service: **exit-block emerges** (LOS for
  admitted patients roughly doubles with feedback on - see the test).
- **`coupling/cosim.py`** - hourly zero-order-hold exchange through
  `SystemState`. `run_cosim(pathway, ...)` is the single entry point every
  analysis uses.
- **`validation/`** - the pathway's routes ARE the reference process map;
  `conformance.check` proves each simulated journey is legal (illegal
  transitions, band regressions, in-unit time caps). A clean run passes at
  100%; injected errors are caught. This is the clinical-credibility spine.

### 3.2 The pathway definition

`uec_hybrid/pathways/model_ed.json` is the single source of truth: ~33 nodes
over four time bands (front door, 0-4h core, 4-12h, 12h+), resources,
streams, SD config, and `uec` metadata (which node is initial assessment,
nurse-to-cubicle ratio, handover stages). The engine is generic; this file is
what makes it the Model ED. Schema notes:

- Routing precedence per node: `routes_by_signal` (SD-driven) ->
  `routes_by_attribute` -> `routes_by_class` -> `routes`.
- `open_hours` + `closed_fallback` gate part-time areas safely.
- `max_band_minutes` caps time IN a unit (EEMAC 12h, CDU 24h).
- `renege: {patience: <dist>, to: <sink>}` enables LWBS at a node.

### 3.3 Department builder

`department/config.py` defines `Department` (which of 9 Model ED areas the
trust has, sizes, opening hours, rota, beds, community capacity).
`department/builder.py -> build(dept)` turns it into a runnable raw:
disables missing areas (re-routing patients safely), gates part-time areas,
scales physical spaces, folds the rota into per-hour rosters for staff
resources, and applies the **nurse-to-cubicle ratio** (open cubicles capped by
ED nurses on shift x ratio). ENPs and porters are real engine resources;
HCA/reception are cost-only (`SUPPORT_RESOURCES`); ED nursing is
ratio-constrained (`RATIO_RESOURCES`).

### 3.3a Data input (no code/JSON to configure a department)

Four routes in, all landing on a saved `Department` (and, where relevant, a
calibration patch / settings):

- **Pick your trust** - `ingest/trust_profile.py` loads a registry from
  `data/nhs_trust_snapshot.csv` (keyed by ODS code), so trusts are *data rows*,
  not Python. `to_department` maps published INPUTS (attendances/day, bed
  occupancy, beds) onto a `Department`; observed OUTCOMES (4-hour/12-hour %) are
  kept for validation only. Missing fields fall back to the template default,
  flagged in `notes`/`provenance`. `ingest/nhs_open_data.fetch_trust(ods)` is the
  automatic API-pull seam (reads the snapshot; documented live adapter).
- **Import a workbook** - `ingest/workbook.py`: `write_template()` builds a blank
  `.xlsx` (Overview / Areas / Rota / optional Arrivals / AcuityMix / Costs /
  ServiceTimes); `read_workbook()` returns a `Department` + optional calibration
  patch + cost book + role rates + service params. CSV Overview also accepted.
- **Set up by hand** - the product's *Set up my ED* form + rota editor.
- **Calibrate** - the ECDS seam (3.5), replacing synthetic arrivals/case-mix/
  admission rates with a real extract.

Three parameter groups are **editable as data** (stored settings, no code), each
applied at the right layer so every surface reflects them and the cache
invalidates:

- **Costs** - `finance/costbook.py` (cost book) + `workforce/roles.role_rates()`
  (per-role hourly rates as a stored override over defaults).
- **Standards** - `analysis/metrics.uec_scorecard(m, overrides)`; overrides via
  `/api/scorecard-targets`.
- **Service times** - `model_params.py` overlays a global scale / per-stage means
  onto the pathway raw in `_dept_raw()` and `_build()`; via `/api/pathway-params`
  or the workbook's ServiceTimes tab. Only the pathway *structure* stays in
  `model_ed.json`.

### 3.4 Platform (persistence + caching)

`platform/store.py` (SQLAlchemy): versioned department rows, calibrations,
settings (cost book, benchmarks), and the **run cache**: results keyed by
`sha256(kind + ENGINE_VERSION + exact config)`. Identical questions answer
instantly; changing anything that affects a result (department, calibration,
cost book, engine version) changes the hash. **Bump `ENGINE_VERSION` whenever
you change simulation behaviour or cached payload shapes** - that is the
cache-invalidation mechanism.

### 3.5 Demand seams (order matters)

For "your department": `build(dept)` -> apply ECDS calibration patch -> apply
service-time overrides (`model_params.apply_params`) ->
(analyst-only: population determinants, overrides, arrival scaling) ->
`Pathway.from_dict`. Rules that keep streams truthful:

- Anything that changes the global `acuity_mix` must go through
  `demand/streams.skew_stream_mixes` (population, calibration, scenarios,
  planner diverts, surge all do).
- Anything that changes ambulance conveyance must move the ambulance stream's
  share via `scale_stream_share` (calibration and deprivation do).
- Demand volume changes only ever touch `hourly_profile`.

### 3.6 Finance

`finance/costbook.py`: trust-editable assumptions with flagged indicative
defaults (never presented as benchmarks). `finance/business_case.py` prices
ONLY what the simulation showed (breaches/admissions avoided) and returns the
assumptions with every case. Role hourly rates default in `workforce/roles.py`
but are **editable via `role_rates()`** (a stored override merged over the
defaults); `rota.weekly_cost`/`cost_breakdown` read it, so an edited rate moves
the pay-bill everywhere. Cost book + role rates are also settable from the
workbook's Costs tab.

### 3.7 Decision support

- `analysis/metrics.py` - KPIs incl. LWBS, measured handover + vehicle-hours,
  per-stream stats; RAG `uec_scorecard` (editable targets); `diagnose` (pinch
  point + binding resource); `sd_interpretation` (plain read of the SD plots);
  `stage_timing` (per-stage wait/treatment/time-in-stage + end-to-end LOS).
- `analysis/montecarlo.py` - parallel replications, 95% CIs.
- `docs/review/three-agent-review.md` - the full stakeholder-panel review,
  evidence-based capability assessment, gap register, implemented fixes, live
  scenario test results and the operational-readiness recommendation
  (currently: suitable for controlled pilot only).
- `analysis/scenarios.py` - declarative what-ifs + tornado sensitivity +
  `interpret` (which lever helps/hurts, top sensitivity).
- `analysis/benchmark.py` - percentile position vs a peer CSV (synthetic
  flagged sample until real data uploaded).
- `planning/forecast.py` - covariate regression (trend, weekday, seasonality,
  bank holidays) with a 28-day holdout backtest; accuracy always shown.
- `planning/planner.py` / `operational.py` - winter options / today actions,
  built ON the configured department; `project_today` = intraday projection.
- `planning/surge.py` - stress templates + greedy inverse staffing solver.
- `optimise/recommend.py` - candidates from the department's own weak points,
  paired-seed Monte-Carlo, Student-t CI gate: silence over noise.

### 3.8 Surfaces & tabs (what each does, and the endpoint behind it)

**Control tower `/`** (`product.html` + `product.js`):
- *Control tower* - live flow map of the saved department, time-of-day slider,
  clickable blocks, pinch point + when it bites, headline standards
  typical/good/tough. `POST /api/control-tower`.
- *Workforce* - staffing vs demand by hour, under-staffed windows, weekly
  pay-bill; live rota editor (`/api/rota-preview`, no sim) + Apply & re-run.
  `POST /api/workforce`.
- *Model ED gaps* - have vs missing elements + costed business case.
  `POST /api/gap`.
- *Set up my ED* - **Start from your trust** (`/api/trusts`, `/api/trust/select`)
  or **import Excel** (`/api/trust/template`, `/api/trust/import`), or the form +
  areas/hours. Saves via `POST /api/department`.

**Executive brief `/exec`** (`exec.html`): one composed screen; `GET /api/exec`,
board PDF `GET /api/report`.

**Plan ahead `/planner`** (`planner.html`): winter plan `POST /api/plan`, intraday
`POST /api/plan-today`, surge `GET/POST /api/surge`, forecast upload
`POST /api/forecast-data`.

**Analyst view `/analyst`** (`dashboard.html` + `dashboard.js`), tabs:
- *Live simulation* - scorecard + diagnosis + flow model (clickable blocks) +
  utilisation/waits/Sankey/heatmap. `POST /api/simulate` (returns
  `sd_interpretation` used on the SD tab).
- *System Dynamics* - stock + feedback plots with a computed interpretation.
- *Monte-Carlo* - CI distributions. `POST /api/montecarlo`.
- *Scenarios & sensitivity* - comparison + tornado + `interpretation`.
  `POST /api/scenarios`.
- *Validation* - conformance + **per-stage timing table** (`stage_timing`) +
  **per-variant timing** (`process_map.variant_timing`: each observed route with
  mean time per stage + total LOS). `POST /api/validate`.
- *Data & calibration* - ECDS upload. `POST /api/calibrate[/reset]`.

### 3.9 AI assist (`assist/`)

Two AI features, chosen so neither can ever invent a number:

- **Ask a what-if** (`assist/nl.py`) - plain English -> scenario (rule-based
  parser, fully offline) -> `compare_scenarios` (paired Monte-Carlo vs
  baseline) -> plain-language answer + before/after table. The parser handles
  staff/space changes, demand, ward beds, diverts, winter - plus **time
  windows** ("at 1pm", "from 8pm to 8am", "overnight" -> hour-windowed
  capacity via `scenarios._windowed`) and **nurses** ("add 3 nurses at 1pm"),
  which work through the nurse-to-cubicle ratio: the builder stashes the
  physical cubicle roster and nurse rota in `raw["uec"]` so the scenario layer
  recomputes the cap exactly, and the answer says when extra nurses would open
  no extra cubicles. If `anthropic` is installed and `ANTHROPIC_API_KEY` is
  set (`assist/llm.py`), Claude becomes a fallback parser for free-form
  phrasing (schema-constrained, validated against the department's real
  resources) and a better narrator (prompted to use only the computed numbers;
  the computed table is always shown). No key -> identical numbers, templated
  wording. Neither `anthropic` nor a key ships in requirements - locked-down
  NHS installs never make an outbound call.
- **Chatbot** (`assist/chat.py`, the floating "Ask your ED" widget) - answers
  operational questions any time ("where is demand", "where should I deploy",
  "what's the pinch point", standards, gaps, glossary, what-ifs). A rule-based
  intent router formats answers from a ``provider`` of the product's own
  computed feeds (server `_chat_provider`) - a chat answer can never disagree
  with a screen. How-to/concept questions the router can't match fall back to
  **offline retrieval (RAG)** (`assist/retrieval.py`): IDF-weighted keyword
  search (no dependencies, no network) over the glossary, a curated product
  guide and the README/handover, answering only on a confident match - and a
  what-if that almost parsed explains what it understood plus example
  phrasings instead of shrugging. With Claude configured, free-form questions
  are answered from a compact JSON context of the same computed numbers plus
  the top retrieved passages, and change-questions are handed back to the real
  engine via a `WHATIF:` handshake.
- **Auto-calibration** (`assist/autocal.py`) - monotonic search over the
  global service-time scale until modelled 4-hour matches the trust's
  observed figure; saves through `model_params` (same override as the
  workbook ServiceTimes tab; clear `/api/pathway-params` to undo). Every
  evaluation is returned in `history`; clamping to the plausible band is
  reported honestly.

Rejected on purpose: LLM-written board narratives (hallucination risk in a
clinical/financial document - computed interpretations already exist) and an
ML forecaster (the regression forecaster with a backtest already covers it).

## 4. API reference (all JSON unless noted)

| Route | Method | Purpose |
|---|---|---|
| `/api/setup` | GET | Department, areas catalogue, roles |
| `/api/department` | POST | Save department (new version) |
| `/api/trusts` | GET | Trusts pre-fillable from the open-data snapshot |
| `/api/trust/select` | POST | Load a trust (`{ods}`) as the department |
| `/api/trust/template` | GET | Blank Excel set-up workbook (xlsx) |
| `/api/trust/import` | POST | Set up department from an uploaded workbook |
| `/api/control-tower` | POST | Flow map + standards + pinch (cached) |
| `/api/recommend` | POST | CI-gated recommendations (cached, minutes first run) |
| `/api/workforce` `/api/rota-preview` | POST | Staffing vs demand; instant no-sim preview |
| `/api/gap` | POST | Model ED gap analysis + finance (cached, slow) |
| `/api/exec` | GET | Composed executive brief incl. benchmark position |
| `/api/report` | GET | Board PDF (`?replications=`) |
| `/api/plan` `/api/plan-today` | POST | Winter plan / today plan (+`arrivals_so_far` intraday) |
| `/api/surge` | GET/POST | Templates / stress test (+`solve` for staffing answer) |
| `/api/forecast-data` `/api/sample-history` | POST/GET | History upload -> forecast; template CSV |
| `/api/benchmarks` | GET/POST | Template download / peer upload |
| `/api/costbook` | GET/POST | Trust-editable finance assumptions |
| `/api/scorecard-targets` | GET/POST | Editable RAG standard targets (data-driven, admin-level) |
| `/api/pathway-params` | GET/POST | Editable service-time assumptions (global scale + per-stage means) |
| `/api/data-status` | GET | Data provenance: source (demo/trust/workbook/manual), dates, overrides, engine version, warnings |
| `/api/actions` | GET/POST | Append-only operational decision log, stamped with the model state (no edit/delete) |
| `/api/audit` | GET | Append-only audit trail of configuration changes (departments, targets, rates, params) |
| `/api/ask` | POST | Plain-English what-if (`{question}`) -> scenario -> engine -> grounded answer (cached) |
| `/api/auto-calibrate` | POST | AI-assisted calibration: tune service-time scale to the observed 4-hour % |
| `/api/chat` | POST | Product chatbot (`{message, history}`): demand/deploy/pinch/standards/gaps/glossary/what-ifs |
| `/api/simulate` `/api/montecarlo` `/api/scenarios` `/api/validate` | POST | Analyst engine (cached) |
| `/api/calibrate` `/api/calibrate/reset` | POST | ECDS calibration (scope: pathway key or `your_department`) |
| `/api/sample-data` | GET | ECDS-shaped template CSV |

## 5. Testing

`python -m uec_hybrid.tests.run` - the end-to-end suite covering engine
safety (capacity never exceeded), physics (exit-block emergence, LWBS under
starvation, nurse-ratio capping, acuity priority), validation (clean run 100%
conformant, injected errors caught), every seam (streams x calibration x
population x scenarios), the data-input layer (trust snapshot, workbook
round-trip, editable costs/standards/service-times), analyst interpretations
(SD read, stage timing, scenario impact), platform (persistence, cache), finance
maths, forecast component recovery, surge, recommender CI gate, and all surfaces
+ endpoints via the Flask test client. **Add a check for every new behaviour**;
the suite is the contract. Style: plain asserts + one printed line per area.

## 6. Known limitations and honest assumptions

- **Synthetic until calibrated**: service times, patience (lognormal, mean
  180 min), nurse ratio (1:4), surge template magnitudes, cost-book defaults
  and the benchmark sample are flagged planning assumptions. Costs, scorecard
  targets and service-time means are now editable as **data** (settings /
  workbook); the pathway *structure* (`model_ed.json`) and the remaining Python
  constants (population coefficients, surge templates, forecast seasonality) are
  still code — edited only to change what the model *is*, not to configure a trust.
- **Single tenant, no auth**: one department, no users/RBAC yet; Flask dev
  server (put gunicorn + a reverse proxy in front for anything shared).
- **HCA/reception are cost-only**; nursing constrains via ratio, not tasks.
- **Governance work not started**: DPIA/DSPT pack, DCB0129 clinical-safety
  case, audit-log surface (run rows exist; no UI). Required before any trust
  pilot with real data - see plan doc section 10.
- The gap analysis and recommender are compute-heavy on first run (minutes);
  results cache until the configuration changes.

## 7. Where to take it next (Phase 3 remainder)

1. React ports of control tower / planner / analyst (dedicated block;
   `/app` shell + typed API client are in place).
2. Auth + multi-department tenancy (store schema already keys by department).
3. EPR/FHIR live feed -> `project_today` becomes continuous; the ECDS batch
   seam is the designed hook.
4. Optimisation v2: budget-constrained multi-move search over the existing
   paired-seed evaluator.
5. Governance pack (sales-blocking, not engineering-blocking).

## 8. Key files if you read only ten

`uec_hybrid/des/engine.py` · `uec_hybrid/pathways/model_ed.json` ·
`uec_hybrid/coupling/cosim.py` · `uec_hybrid/department/builder.py` ·
`uec_hybrid/ingest/` (trust_profile, workbook) · `uec_hybrid/model_params.py` ·
`uec_hybrid/platform/store.py` · `uec_hybrid/app/server.py` ·
`uec_hybrid/analysis/metrics.py` · `uec_hybrid/tests/run.py`
