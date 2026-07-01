# Model ED Optimiser

A product to help any NHS trust **implement the Model Emergency Department** — design,
staff and run a high-performing ED. It is flow-first and plain-language; the hybrid
simulation (DES + System Dynamics + Monte-Carlo) is the hidden engine and none of its
vocabulary appears on the product surface.

Open `/` for the product. It has:

- **Control tower** — a live flow map of *your* department: patients moving through your
  areas, queues, and the busiest pinch-point (with *when* it bites). A time-of-day slider
  shows the department at any hour; click an area to drill in. Headline standards
  (4-hour, 15-minute assessment, 12-hour, ambulance handover) as a typical / good / tough
  week.
- **Workforce** — "are you staffed for the demand curve?": staffing by role and hour
  against demand, the under-staffed windows in red, and the weekly pay-bill. (The engine
  models **staffing that varies by hour**, so the bottleneck is time-aware.) A **live rota
  editor** lets you change shifts and watch the staffing curve and weekly cost move
  instantly, then "Apply & re-run" to see the standards and pinch-point shift.
- **Model ED gaps** — which Model ED elements you have vs are missing, and what each
  missing one would add (front-door areas judged on the 4-hour standard; same-day /
  assessment areas on the **admissions they avoid**), with an indicative cost band — the
  investment case.
- **Set up my ED** — switch the areas you actually have on/off (UTC, RAT, fit-to-sit,
  EEMAC, SDEC, PAU, CDU, frailty, MH), set each area's **opening hours** (e.g. SDEC 08–20
  rather than 24/7), set its size and beds; patients re-route safely when an area is off
  or closed.
- **Plan ahead** (`/planner`) — the winter & today demand/capacity planner. Plans
  model *your department exactly as set up in the product* (areas, opening hours,
  rota, beds), not a generic template.
- **Analyst view** (`/analyst`) — the full technical model, defaulting to the same
  configured department so its numbers line up with the control tower.

Everything is connected through one saved department: the set-up, rota and any
ECDS calibration persist across restarts (SQLite by default; `DATABASE_URL` for
Postgres), calibrating with real data updates every surface at once, and repeat
runs of an identical configuration are answered instantly from the run cache.

```bash
pip install -r requirements.txt
python -m uec_hybrid.app.server     # product at http://127.0.0.1:5000
python -m uec_hybrid.tests.run      # end-to-end checks (incl. time-varying staffing)
```

```bash
pip install -r requirements.txt
python -m uec_hybrid.app.server     # planner at http://127.0.0.1:5000  (analyst view at /analyst)
```

---

## The engine — System Dynamics + Discrete-Event Simulation

A principled, evidence-based model of NHS Urgent & Emergency Care that **couples a
patient-level Discrete-Event Simulation (DES) with a whole-system System-Dynamics
(SD) model**. It is grounded in two NHS design documents:

- **NHS England, "The Model Emergency Department: high-performing UEC pathways"
  (Feb 2026)** — the ED operational pathway, structured as **acuity × time**.
- **Sussex, "Urgent and Emergency Care Model" (Aug 2025)** — the whole-system
  context (navigation, community, downstream beds, mental health).

The DES assesses the impact of **resource-capacity limits and acuity prioritisation**
at the patient level; the SD layer models the **whole hospital the ED sits inside**
(inpatient beds, mental-health beds, community/virtual-ward capacity) with the
**feedback loops** that drive real ED behaviour. Uncertainty is explicit via
**Monte-Carlo**; changes are tested with **scenario and sensitivity analysis** against
a baseline; and the simulated pathway is **validated by process-map conformance**.

![Flow model](docs/flow_model.png)

## Why a hybrid, and how the two solvers couple

A pure DES cannot represent the dominant cause of ED crowding — **exit-block**, where
a near-full hospital cannot accept admissions, so patients board in the ED. That is a
*system* behaviour: a stock (occupied inpatient beds) with feedback. The hybrid:

- **DES (patient level):** every patient flows through the Model ED pathway
  contending for limited spaces and clinicians, with **acuity priority queues**
  (sickest first), span-held beds, variable durations by acuity and time-of-day demand.
- **SD (whole system):** homeostatic stocks for inpatient beds, MH beds and community
  capacity. High bed occupancy raises a **bed-wait multiplier** that slows ED
  admissions (exit-block); community headroom **pulls** patients out and accelerates
  discharge.
- **Coupling:** a `CoSimulator` runs an **hourly zero-order-hold co-simulation** —
  each simulated hour the DES flows (admissions, diversions, ED census) are drained
  into the SD model, the SD integrates, and the new signals are published back for the
  DES to read. Zero-order hold + smooth, bounded feedback + first-order smoothing keep
  the loop stable (verified by a self-test).

**Verified behaviour:** with the bed feedback on, admitted length of stay rises from
~270 to ~595 minutes — exit-block *emerges from the bed stock*, not from a static fudge
factor. Turning feedback off recovers the naïve DES.

## What it produces

- **UEC scorecard** RAG-rated against Model ED / UEC Plan standards: 4-hour (toward
  95%), initial assessment ≤15 min, 12-hour waits, ambulance handover ≤45 min, MH
  liaison ≤1h, MH >24h, children's 4-hour, EEMAC conversion-to-admission, bed occupancy.
- **Flow model "Figure 1":** the whole pathway by acuity×time band with the SD stocks
  and feedback, the bottleneck highlighted, patients animated along the links.
- **System-Dynamics charts:** bed/MH occupancy, crowding and feedback signals over time.
- **Monte-Carlo** distributions with 95% confidence intervals.
- **Scenario comparison + tornado sensitivity** vs baseline.
- **Process-map validation:** conformance of the simulated event order to the intended
  Model ED graph (a clean pass validates faithfulness; injected errors are caught).
- **Population & determinants:** age, deprivation (IMD) and paediatric share drive
  demand and case-mix; **ECDS calibration seam** to replace synthetic data with real
  attendance extracts.

## Architecture

```
uec_hybrid/
├── des/         DES engine (priority queues, span beds, dynamic SD-coupled params,
│                band/time enforcement), distributions, pathway (+ schema validation)
├── sd/          stocks, model (homeostatic bed/MH/community stocks + integrator),
│                feedback (smooth bounded transfer functions + smoothing)
├── coupling/    system_state (held signals + accumulators, zero-order hold),
│                cosim (hourly master clock), adapters (channel map)
├── demand/      population (age/IMD/paediatric -> case-mix), ecds_seam (calibration)
├── pathways/    model_ed.json (faithful Model ED acuity×time pathway)
├── analysis/    metrics (KPIs -> standards, RAG scorecard, bottleneck), montecarlo,
│                scenarios (+ tornado sensitivity)
├── validation/  reference_map, conformance (process-map check), process_map (variants)
├── viz/         flow_model ("Figure 1" data), figures (Plotly), palette
├── platform/    store (SQLite/Postgres persistence: saved department, ECDS
│                calibrations, run cache keyed by configuration hash)
├── app/         server (Flask), templates/dashboard.html, static (dashboard.js + Plotly)
└── tests/       run.py (engine, SD, coupling stability + mass-balance, conformance)
```

## Run it

```bash
pip install -r requirements.txt

python -m uec_hybrid.app.server      # dashboard at http://127.0.0.1:5000
python -m uec_hybrid.tests.run       # end-to-end checks

python - <<'PY'
from uec_hybrid import Pathway, run_cosim, kpis, uec_scorecard, conformance_check
p = Pathway.load("uec_hybrid/pathways/model_ed.json")
res = run_cosim(p, seed=0)                 # coupled SD+DES
print(uec_scorecard({**kpis(res,p)}))
print("pathway validated:", conformance_check(res,p)["passed"])
PY
```

## A note on data and faithfulness

The model ships on **synthetic** parameters. Structure is taken from the NHS design
documents; service-time distributions are modelled/expert-set and clearly flagged as
such (they are not identifiable from attendance data). Calibrate arrivals, case-mix,
cohort prevalence and admission rates from a real ECDS extract via the **Data &
calibration** tab. Validate against local data before any operational use. Colours
follow the official NHS identity palette.
