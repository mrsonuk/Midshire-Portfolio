# Model ED Optimiser

A product to help any NHS trust **implement the Model Emergency Department** — design,
staff and run a high-performing ED. It is flow-first and plain-language; a hybrid
simulation (Discrete-Event Simulation + System Dynamics + Monte-Carlo) is the hidden
engine and none of its vocabulary appears on the product surface.

```bash
pip install -r requirements.txt
python -m uec_hybrid.app.server     # product at http://127.0.0.1:5000
python -m uec_hybrid.tests.run      # end-to-end checks
```

Open `/` for the product (control tower). The other surfaces are `/exec`,
`/planner` and `/analyst`.

---

## 1. Purpose

Every acute trust is being asked to move its ED toward the NHS England **Model
Emergency Department** blueprint. This product lets a trust **model its own ED**,
see where flow breaks, test what would fix it, and build the costed case — without
needing a modeller. Under the surface it runs a faithful patient-level simulation
of the Model ED pathway coupled to the whole hospital around it, so the answers
reflect real ED physics (crowding, exit-block, time-of-day staffing) rather than
spreadsheet averages.

## 2. Outcomes — what you get out of it

- **A performance scorecard** RAG-rated against Model ED / UEC Plan standards:
  4-hour (toward 95%), initial assessment ≤15 min, 12-hour waits, ambulance
  handover ≤45 min, MH liaison ≤1h, MH >24h, children's 4-hour, EEMAC
  conversion-to-admission, bed occupancy.
- **The pinch point** — the single stage costing you the most, *and when in the
  day it bites* — with a recommendation.
- **A staffing answer** — are you staffed for the demand curve, hour by hour, and
  what the weekly pay-bill is.
- **The investment case** — which Model ED elements you're missing, what each would
  add, and a costed business case (annual benefit, ROI, payback) with every
  assumption printed.
- **A board-ready decision report (PDF)** in one click.
- **Honest uncertainty** — Monte-Carlo confidence intervals, scenario comparison,
  and a validation that the simulation faithfully reproduces the Model ED design.

## 3. Data input — how your ED gets into the model

You should **never need to edit code or JSON** to configure a department. There are
four ways in, in increasing order of effort/precision:

| Route | What it sets | Where |
|---|---|---|
| **Pick your trust** | Attendances/day, bed occupancy, beds (from published NHS open data, by ODS code) | *Set up my ED → Start from your trust* |
| **Import an Excel workbook** | Everything: department, areas, opening hours, rota, costs, and optional arrivals/acuity/service-times | *Set up my ED → import*, template at `/api/trust/template` |
| **Set up by hand** | Areas on/off, opening hours, beds, community, rota | *Set up my ED* form + rota editor |
| **Calibrate from real activity** | Real arrivals-by-hour, acuity mix, cohort prevalence, admission rates | *Analyst → Data & calibration* (ECDS CSV) |

Three things are also editable **as data** (no code), for when the defaults need to
change:

- **Costs** — the cost book (£ per admission/breach avoided, agency premium) and
  per-role hourly rates: cost book UI, or the workbook's **Costs** tab.
- **Standards** — the RAG targets (e.g. move 4-hour from 78% toward 95%):
  `GET/POST /api/scorecard-targets`.
- **Service-time assumptions** — the model's core "physics": a global scale or
  per-stage means, via `GET/POST /api/pathway-params` or the workbook's
  **ServiceTimes** tab.

**The one thing still in code:** the *shape* of the Model ED pathway itself
(`uec_hybrid/pathways/model_ed.json` — which nodes exist and how they connect).
That defines what "the Model ED" is and stays version-controlled so it always
passes clinical conformance. Service-time *values* are editable as data (above);
only the graph *structure* is code.

Everything is connected through **one saved department**: set-up, rota,
calibration, costs and assumptions persist across restarts (SQLite by default;
`DATABASE_URL` for Postgres), a change updates every surface at once, and repeat
runs of an identical configuration are answered instantly from the run cache.

## 4. The surfaces — how to navigate, and what each does

The product has four top-level surfaces. The first three are the plain-language
product; the analyst view is the technical model behind them.

### Control tower — `/` (tabs across the top)

| Tab | What it does |
|---|---|
| **Control tower** | A live flow map of *your* department: patients moving through your areas, queue colours (green <15 min, amber 15–60, red >60), and the pinch point flagged. A **time-of-day slider** shows the department at any hour; **click any block** to drill into it. The four headline standards show as a typical / good / tough week. |
| **Workforce** | "Are you staffed for the demand curve?" — staffing by role and hour against the demand shape, under-staffed windows in red, the weekly pay-bill and where it goes. A **live rota editor** updates the staffing curve and cost instantly; **Apply & re-run** feeds it back into the control tower. |
| **Model ED gaps** | Which Model ED elements you have vs are missing, and what each missing one would add (front-door areas judged on the 4-hour standard; same-day/assessment areas on the admissions they avoid), each with a cost band and a **costed business case**. |
| **Set up my ED** | The configuration surface. **Start from your trust** (dropdown) or **import an Excel workbook**, or set it by hand: switch areas on/off (UTC, RAT, fit-to-sit, PAU, EEMAC, SDEC, CDU, frailty, MH), set each area's **opening hours**, and set attendances, beds and community capacity. Save & re-run. |

### Executive brief — `/exec`

One screen for the COO / ED director: OPEL-style risk, the four headline standards
as typical/good/tough, the pinch point and what to do, the weekly pay-bill, the
biggest investment case, and a **one-click board-ready PDF** (`/api/report`).

### Plan ahead — `/planner`

The winter & "today" demand/capacity planner. Plans model *your department exactly
as set up* (areas, opening hours, rota, beds), not a generic template. Includes an
intraday "today" projection from arrivals-so-far and surge stress tests.

### Analyst view — `/analyst`

The full technical model, defaulting to the same configured department so its
numbers line up with the control tower. Its tabs:

| Tab | What it shows |
|---|---|
| **Live simulation** | The UEC scorecard, the bottleneck diagnosis, and the flow model ("Figure 1") by acuity×time band with the SD stocks. **Click any block** for its volume, wait, utilisation and whether it's the binding constraint. Plus resource utilisation, stage waits, Sankey and occupancy heatmap. |
| **System Dynamics** | Bed/MH occupancy, ED-crowding index and the feedback signals over time — **with a plain-language interpretation** of what the stocks and feedback plots actually mean (occupancy vs the 92% exit-block line, the bed-wait multiplier, community pull). Turn feedback off in the sidebar for the counterfactual. |
| **Monte-Carlo** | Distributions with 95% confidence intervals over many simulated weeks, and what the spread means for planning. |
| **Scenarios & sensitivity** | Compare what-if scenarios against baseline (each Monte-Carlo'd) with a tornado sensitivity — **and a written impact read-out**: which lever helps 4-hour most, which is the biggest risk, and the top sensitivity. |
| **Validation** | Process-map conformance (every simulated journey checked against the Model ED graph); a **per-stage timing table** (patient count, wait + treatment + time-in-stage per stage, and the true end-to-end total); and the **observed pathway variants — each route annotated with the mean time at every stage and the average total time (length of stay) for patients on that path**. Within a route the stage times reconcile to the total. |
| **Data & calibration** | Upload an ECDS-style extract to replace synthetic arrivals/case-mix/admission rates with your real data; reset to synthetic. |

The analyst sidebar exposes the model levers: whole-system feedback on/off,
population determinants (older %, IMD, paediatric %), demand scale, SD levers
(beds, community) and per-resource capacities.

---

## 5. The engine — System Dynamics + Discrete-Event Simulation

A principled, evidence-based model of NHS Urgent & Emergency Care that **couples a
patient-level Discrete-Event Simulation (DES) with a whole-system System-Dynamics
(SD) model**, grounded in two NHS design documents:

- **NHS England, "The Model Emergency Department: high-performing UEC pathways"
  (Feb 2026)** — the ED operational pathway, structured as **acuity × time**.
- **Sussex, "Urgent and Emergency Care Model" (Aug 2025)** — the whole-system
  context (navigation, community, downstream beds, mental health).

![Flow model](docs/flow_model.png)

### Why a hybrid, and how the two solvers couple

A pure DES cannot represent the dominant cause of ED crowding — **exit-block**, where
a near-full hospital cannot accept admissions, so patients board in the ED. That is a
*system* behaviour: a stock (occupied inpatient beds) with feedback. The hybrid:

- **DES (patient level):** every patient flows through the Model ED pathway
  contending for limited spaces and clinicians, with **acuity priority queues**
  (sickest first), span-held beds, variable durations by acuity and time-of-day
  demand, reneging (LWBS) and time-varying staffing.
- **SD (whole system):** homeostatic stocks for inpatient beds, MH beds and
  community capacity. High bed occupancy raises a **bed-wait multiplier** that slows
  ED admissions (exit-block); community headroom **pulls** patients out and
  accelerates discharge.
- **Coupling:** a `CoSimulator` runs an **hourly zero-order-hold co-simulation** —
  each simulated hour the DES flows (admissions, diversions, ED census) are drained
  into the SD model, the SD integrates, and the new signals are published back for
  the DES to read. Zero-order hold + smooth bounded feedback + first-order smoothing
  keep the loop stable (verified by a self-test).

**Verified behaviour:** with the bed feedback on, admitted length of stay rises from
~270 to ~595 minutes — exit-block *emerges from the bed stock*, not from a static
fudge factor. Turning feedback off recovers the naïve DES.

## 6. Architecture

```
uec_hybrid/
├── des/         DES engine (priority queues, span beds, dynamic SD-coupled params,
│                band/time enforcement, reneging), distributions, pathway (+ schema)
├── sd/          stocks, model (homeostatic bed/MH/community stocks + integrator),
│                feedback (smooth bounded transfer functions + smoothing)
├── coupling/    system_state (held signals + accumulators, zero-order hold),
│                cosim (hourly master clock), adapters (channel map)
├── pathways/    model_ed.json  — THE data definition of the Model ED (structure)
├── model_params.py             — editable service-time overlay (scale / per-stage)
├── department/  config (Department + AREAS catalogue), builder (Department -> raw),
│                model_ed_gap (gap analysis)
├── ingest/      trust_profile (pick your trust, from data/nhs_trust_snapshot.csv),
│                nhs_open_data (fetch-by-ODS seam), workbook (Excel/CSV import + template)
├── data/        nhs_trust_snapshot.csv (trust registry), sample_ecds.csv
├── demand/      population (age/IMD/paediatric -> case-mix), ecds_seam (calibration),
│                streams (arrival streams)
├── analysis/    metrics (KPIs -> standards, RAG scorecard, bottleneck, SD & stage
│                interpretations), montecarlo, scenarios (+ tornado + interpretation)
├── validation/  reference_map, conformance (process-map check), process_map (variants)
├── viz/         flow_model ("Figure 1" + control-tower detail), figures (Plotly), palette
├── workforce/   roles (+ editable rates), rota, defaults, view
├── finance/     cost book (trust-editable) + business-case maths (benefit, ROI, payback)
├── planning/    forecast, planner, operational (today), surge
├── optimise/    recommend (CI-gated recommendation engine)
├── platform/    store (SQLite/Postgres: saved department, calibrations, run cache
│                keyed by config hash, settings — costs, standards, service-times)
├── report.py    board-ready decision PDF
├── app/         server (Flask, JSON APIs), templates (product/exec/planner/dashboard),
│                static (product.js, dashboard.js, vendored Plotly)
└── tests/       run.py — end-to-end suite (engine, SD, coupling, conformance, every
                 data seam, endpoints)
../web/          React + TypeScript shell (Vite) at /app; dist/ committed (vendored)
```

Data flow for "your department":
`Department` (saved) → `builder.build` → apply ECDS calibration patch → apply
service-time overrides (`model_params`) → `Pathway` → `run_cosim` (DES↔SD) → metrics
→ surfaces. Costs and scorecard targets are applied at the finance/scorecard layer.

## 7. Run it programmatically

```bash
python - <<'PY'
from uec_hybrid import Pathway, run_cosim, kpis, uec_scorecard, conformance_check
p = Pathway.load("uec_hybrid/pathways/model_ed.json")
res = run_cosim(p, seed=0)                 # coupled SD+DES
print(uec_scorecard({**kpis(res, p)}))
print("pathway validated:", conformance_check(res, p)["passed"])
PY
```

## 8. A note on data and faithfulness

The model ships on **synthetic** parameters. Structure is taken from the NHS design
documents; service-time distributions are modelled/expert-set and clearly flagged as
such (they are not identifiable from attendance data). The bundled trust snapshot
carries published, cited figures; observed 4-hour/12-hour percentages are used only
to *validate* the model, never as inputs. Calibrate arrivals, case-mix, cohort
prevalence and admission rates from a real ECDS extract, and validate against local
data before any operational use. Colours follow the official NHS identity palette.

Everything is offline-capable by design: no CDNs, no external calls at runtime.
