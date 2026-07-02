# ED Optimisation Platform - Rebuild Plan & Target Architecture

**Status:** Proposed design, v1.0 - for review before build starts.
**Baseline:** the existing `uec_hybrid` hybrid DES + System-Dynamics engine and Flask app.
**Goal:** rebuild the current research-grade tool into a commercial, multi-trust
**ED Optimisation Platform** covering the 20-module product specification:
operational decision-making, workforce planning, and business-case development.

---

## 1. Product thesis

We do not sell "a simulation model". We sell answers to the questions NHS trusts
are already asking, priced against the money and harm at stake:

| Trust problem | Platform answer | Value lever |
|---|---|---|
| 4-hour / 12-hour performance | Digital twin + bottleneck diagnosis + ranked interventions | Fewer breaches, better CQC position |
| Crowding & ambulance handover delays | Emergent exit-block modelling + ambulance offload module | Handover hours returned to the road |
| Agency spend & rota gaps | Workforce studio + optimiser ("move the consultant to 10:00") | Agency/overtime reduction |
| Capital & winter funding bids | Business-case generator with ROI, payback, CIs | Board/ICB-ready evidence |
| "Will tonight be safe?" | Daily prediction + OPEL risk + escalation triggers | Earlier, cheaper escalation |

Two properties of the existing engine are the credibility spine of the pitch and
must be preserved through the rebuild:

1. **Exit-block is emergent** - admissions slow because a modelled hospital bed
   stock fills, not because of a fudge factor (verified by the test suite).
2. **The model proves its own faithfulness** - process-map conformance checking
   validates every simulated patient journey against the intended pathway.

---

## 2. Architectural strategy: keep the physics, rebuild the product

A ground-up rewrite of the DES/SD kernel would be the riskiest and least valuable
work in the programme. The kernel (≈ `des/`, `sd/`, `coupling/`, `validation/`)
already implements the hardest science in the spec (modules 2, 9, 14) and has an
end-to-end assertion suite.

**Decision: strangler-fig re-platform.**

- The simulation kernel is retained and *extended* (see §7) as a pure-Python
  compute library with no web/product dependencies.
- Everything around it - API, persistence, auth, jobs, financials, forecasting,
  optimisation, front-end, reporting - is rebuilt as a proper product platform.
- The existing Flask app keeps working during the migration; surfaces are moved
  to the new platform one at a time, then the Flask app is retired.
- The legacy `nhs_des/` bytecode directory and committed `.pyc` files are removed
  in the first commit of Phase 0.

---

## 3. Target architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  WEB APP  (React + TypeScript, NHS.UK design system, vendored Plotly)  │
│  Exec dashboard · Twin studio · Workforce studio · Scenario builder    │
│  Planner · Business-case generator · Reports · Admin                   │
└───────────────▲────────────────────────────────────────────────────────┘
                │ REST + SSE (OpenAPI)
┌───────────────┴────────────────────────────────────────────────────────┐
│  PLATFORM API  (FastAPI + Pydantic)                                    │
│  AuthN/AuthZ (OIDC/Entra ID, RBAC) · tenancy · audit log               │
├────────────────────────────────────────────────────────────────────────┤
│  DOMAIN SERVICES                                                       │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ forecast │ │ finance  │ │optimise │ │analytics │ │  reporting   │   │
│  │ streams, │ │ costbook,│ │ rota &  │ │ KPIs,    │ │ board papers,│   │
│  │covariates│ │ ROI,     │ │capacity │ │ flow,    │ │ SITREP, PDF  │   │
│  │ backtest │ │ payback  │ │ search  │ │bottleneck│ │              │   │
│  └──────────┘ └──────────┘ └─────────┘ └──────────┘ └──────────────┘   │
├────────────────────────────────────────────────────────────────────────┤
│  RUN ORCHESTRATOR  (job queue + worker pool)                           │
│  Monte-Carlo fan-out · result cache keyed by config hash · progress    │
├────────────────────────────────────────────────────────────────────────┤
│  SIMULATION KERNEL  (evolved uec_hybrid - pure Python, no web deps)    │
│  DES engine (SimPy) ⇄ SD hospital model via CoSimulator                │
│  Pathway schema v2 · conformance validation · department builder       │
├────────────────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                            │
│  Postgres (SQLAlchemy + Alembic) · object store for reports/uploads    │
│  Ingestion: ECDS batch upload → calibration; later EPR/FHIR live feed  │
└────────────────────────────────────────────────────────────────────────┘
```

Deployment: Docker Compose, self-hostable on-prem or UK-region cloud. No CDN
dependencies (all JS vendored) - the platform must run inside locked-down NHS
networks, as the current app already does.

### Repository layout (monorepo)

```
edplatform/
├── kernel/        # evolved uec_hybrid: des/, sd/, coupling/, pathways/,
│                  # validation/, department/, demand/
├── forecast/      # arrival-stream forecasting + covariates + backtesting
├── analytics/     # KPIs, scorecards, bottleneck chains, flow analytics, MC, scenarios
├── finance/       # cost book, scenario costing, ROI/payback, business-case maths
├── optimise/      # constrained rota/capacity search, recommendation engine
├── platform/      # FastAPI app, db models/migrations, auth, jobs, audit
├── web/           # React + TS front-end (NHS.UK design system)
├── reports/       # HTML→PDF board papers, SITREP, scenario packs
├── data/          # pathway JSONs, default cost book, sample ECDS, benchmark loaders
└── tests/         # kernel physics tests + API tests + golden-master report tests
```

---

## 4. Technology stack and rationale

| Layer | Choice | Why |
|---|---|---|
| Kernel | Python 3.12, SimPy, NumPy/pandas/SciPy | Already proven here; zero rewrite risk |
| API | FastAPI + Pydantic v2 | Typed contracts, OpenAPI docs for trust IT due diligence, async |
| DB | Postgres + SQLAlchemy + Alembic | Boring, self-hostable, NHS-familiar |
| Jobs | Postgres-backed queue (e.g. Procrastinate); Redis optional | Fewest moving parts for on-prem trust deployment; MC runs are CPU-bound batch work |
| Front-end | React + TypeScript + Vite, **nhsuk-frontend** design system, vendored Plotly | Product-grade UI velocity; NHS.UK look signals credibility instantly |
| Auth | OIDC (Microsoft Entra ID first), RBAC | Trusts run on Entra; roles: Executive / Analyst / Admin / Consultant |
| Reports | HTML templates → PDF (WeasyPrint) | Board papers share templates with the web UI; one source of truth |
| Packaging | Docker Compose; single-VM friendly | On-prem or UK cloud; no external SaaS dependencies |

---

## 5. Core data model

Versioned, auditable entities - every number shown to a board must be traceable
to the run and configuration that produced it.

- **Trust** → has many **Users** (role-scoped) and **Departments**
- **Department** (versioned config: areas on/off, sizes, opening hours, rota,
  beds, community capacity) - today's in-memory `CURRENT` dict becomes rows
- **CostBook** (versioned: substantive/agency rates by role & band, tariff and
  breach-cost assumptions - all trust-editable, shipped with flagged defaults)
- **Calibration** (uploaded ECDS extract summary + derived parameters + data-quality report)
- **Scenario** (declarative change-set vs a department baseline)
- **Run** (config hash, seeds, engine version, status, KPI results, event-log
  artefacts) - the result cache: identical config hash ⇒ no recompute
- **Forecast** (per-stream models, covariates, backtest metrics)
- **Recommendation** (optimiser output: change, expected deltas + CIs, rationale)
- **Report** (generated artefact + the run/scenario ids it cites)
- **AuditEvent** (who ran/changed/exported what, when)

---

## 6. Build plan mapped to the 20-module specification

| Spec module | Build approach | Base in current code |
|---|---|---|
| 1. Executive dashboard | New exec surface: RAG scorecard, today/7-day prediction, capacity-risk (OPEL) score, bottleneck alerts, breach-reason breakdown, LWBS | Control tower + scorecard + `diagnose` + OPEL logic in `planning/operational.py` |
| 2. Digital twin of ED | Pathway schema v2: adds registration, lab/pathology, specialty review, explicit ward handoff; per-trust editable in Twin Studio | `model_ed.json` + `department/builder.py` (strong base) |
| 3. Demand forecasting | New `forecast/` service: per-stream (ambulance, walk-in, GP, 111, paeds, frailty) harmonic/GAM regression with covariates (DOW, season, bank holidays, school terms, flu index); backtested, accuracy shown | `planning/forecast.py` (shapes + history upload) |
| 4. Workforce planning | Role model v2: nursing bands 5/6, ENPs, HCAs, ACPs, porters, reception; per-role utilisation/idle/queue-impact analytics; breaks & overtime in rota maths | `workforce/` (roles→resources→cost, live rota editor, time-varying rosters already enforced in engine) |
| 5. Capacity planning | Capacity sweep tool ("cubicles needed for X% performance" = automated scenario sweep + frontier chart) | Scenario capacity modifiers (`analysis/scenarios.py`) |
| 6. Process optimisation | Per-step queue/wait/service/variation analytics surfaced as a step table + control charts | `metrics.stage_waits`, `resource_utilisation`, event log |
| 7. What-if scenario builder | UI scenario composer over the declarative scenario engine; side-by-side current vs future with CIs | `apply_scenario`/`compare_scenarios`/`tornado` (strong base) |
| 8. Financial module | **New `finance/` engine**: cost book × scenario deltas → agency/overtime savings, breach costs avoided, income effects, ROI, payback, cost per attendance. All assumptions visible and editable | Pay-bill maths + option cost bands only - biggest functional gap |
| 9. Bottleneck analysis | Causal-chain narrative (lab → cubicles → queue → handover → 4hr) generated from stage/resource dependencies; current + future (per scenario) bottleneck | `diagnose` + time-aware control-tower bottleneck (strong base) |
| 10. Patient flow analytics | Sankey, hour×area occupancy heatmap, path analytics (common/longest paths) from the event log | `flow_counts`, `process_map.variants`, flow-map data (data exists; viz to build) |
| 11. Real-time prediction | Intraday re-forecast: this morning's actual arrivals → conditional forecast for tonight (4hr risk, breaches, crowding, escalation trigger). Batch CSV first; EPR feed in Phase 3 | `today_plan` OPEL read (coarse base) |
| 12. Winter pressure planning | Named surge templates (flu, norovirus, strike, mass casualty, heatwave) + **inverse solver**: staff/beds required to hold a target | Winter uplift + ranked options (`planning/planner.py`) |
| 13. Ambulance modelling | Explicit DES entities: vehicle queue, offload/handover resource, turnaround time, hours-lost-at-door metric | Ambulance attribute + crowding→handover-delay signal (partial) |
| 14. Admission flow | Decision-to-admit → bed request → allocation (SD-coupled) → porter transport → ward; boarding census and DTOC surfaced | Emergent exit-block via bed stock (strongest asset); granularity to add |
| 15. KPI module | Add LWBS (queue reneging), time-to-treatment, mortality-proxy (long-wait harm index); everything else exists | `kpis` + `uec_metrics` + RAG scorecard (strong base) |
| 16. Recommendation engine | `optimise/`: constrained local search / Bayesian optimisation over rota & capacity space, Monte-Carlo scored with common random numbers; output = "move X to Y ⇒ +Z% 4hr, −£W agency (95% CI)" with tornado-style explanation | Planner's simulated option ranking (rule-based precursor) |
| 17. Benchmarking | Ingest published NHSE monthly A&E statistics for peer/median/quartile comparison; opt-in cross-client consortium benchmarking later | None - new |
| 18. Business-case generator | One-click board paper: baseline vs scenario, benefits, financials (from `finance/`), CIs, recommendation - templated per audience (Board / ICB / NHSE) | `report.py` 2-page PDF + gap-analysis investment case |
| 19. Interactive simulation | Keep instant no-sim previews (rota editor pattern), background MC jobs with live progress via SSE; result cache makes repeat questions instant | Rota preview + apply-and-re-run (good base) |
| 20. Reporting suite | `reports/`: board paper, scenario pack, workforce report, capacity report, daily SITREP - scheduled or on-demand, all citing run ids | `report.py` (CLI PDF) |

---

## 7. Kernel extensions required (the only "physics" work)

1. **Arrival streams** - ambulance / walk-in / GP referral / 111 / paeds as
   first-class streams with independent profiles (feeds modules 3, 13).
2. **Queue reneging** - patience thresholds so LWBS emerges (module 15).
3. **Ambulance offload sub-model** - vehicle queue + handover resource (13).
4. **Admission chain** - bed request → allocation → transport steps with porter
   resource (14).
5. **New pathway nodes** - registration, lab/pathology, specialty review (2, 6).
6. **Schema v2 + migrator** - versioned pathway schema, automatic upgrade of
   existing pathway JSONs; conformance validation extended to new nodes.

Everything else in the programme is product engineering around an unchanged
co-simulation core. Kernel changes land behind the existing test suite plus new
physics tests (e.g. "LWBS rises when streaming is understaffed").

---

## 8. Phased roadmap

Durations are indicative for a small focused team; each phase ends demoable.

### Phase 0 - Platform foundation (~2-3 weeks)
Monorepo restructure; delete `nhs_des` bytecode; FastAPI + Postgres + Alembic +
job queue + OIDC scaffold; port kernel unchanged with tests green in CI; result
cache; existing Flask surfaces still functional (strangler starts).

### Phase 1 - Pilot-sellable MVP (~6-8 weeks) → covers spec 1, 2, 4, 5, 6, 7, 8, 9, 15, 18, 19, 20
Exec dashboard; Twin Studio (department config v2); workforce studio with full
role model; scenario builder UI; **financial engine + cost book**; business-case
generator v1; reporting suite v1; LWBS + KPI completions.
**Exit criterion: a trust pilot can run discovery → calibration → validated
baseline → costed board paper entirely in-product.**

### Phase 2 - Differentiation (~6-8 weeks) → covers spec 3, 10, 12, 13, 14, 16
Forecasting engine with covariates + backtesting; ambulance offload module;
admission-chain granularity; winter surge templates + inverse solver;
recommendation engine v1; Sankey/heatmap flow analytics.

### Phase 3 - Platform & scale (ongoing) → covers spec 11, 17 + advanced capabilities
Intraday prediction from live feeds (EPR/FHIR ingestion); benchmarking vs
published NHSE statistics, then consortium benchmarking; optimisation under
budget/workforce constraints v2; whole-system extension (per-ward stocks,
diagnostics, discharge teams); multi-site ICB view.

---

## 9. Commercial & engagement alignment

The consultancy engagement model maps 1:1 onto product surfaces, so delivery
teams demo the methodology from the product itself:

| Engagement stage | Product surface |
|---|---|
| Discovery | Twin Studio + ECDS upload & data-quality report |
| Digital-twin build | Department builder + calibration |
| Validation | Conformance report + calibration accuracy (shown to clinicians) |
| Scenario testing | Scenario builder (co-design workshop mode) |
| Optimisation | Recommendation engine + capacity/rota sweeps |
| Roadmap & business case | Business-case generator |
| Continuous improvement | Exec dashboard + daily prediction + SITREP (recurring licence) |

Pricing shape (to refine commercially): fixed-fee pilot (8-12 weeks) → annual
platform licence per site → consultancy days for scenario/optimisation cycles.
All financial figures shown by the product come from the trust-editable cost
book - we never present invented benchmarks as fact.

## 10. Governance, security & clinical-safety workstream (sales-critical)

Runs alongside Phase 1 - trusts cannot buy without it:

- **No patient-identifiable data**: ECDS extracts pseudonymised/aggregated at
  ingestion; enforced by schema validation on upload.
- **DPIA template + DSPT alignment** shipped with the deployment pack.
- **Clinical safety**: DCB0129 (manufacturer) safety case for a decision-support
  tool; DCB0160 support pack for deploying trusts; a named clinical safety
  officer requirement flagged in the engagement model.
- **Auditability**: every displayed figure traceable to run id + config hash +
  engine version; full audit log of user actions.
- **Honesty by design**: uncalibrated/synthetic parameters visibly flagged in
  every report (the current codebase's flagged-synthetic discipline, preserved).

## 11. Key risks & mitigations

| Risk | Mitigation |
|---|---|
| Rebuild stalls the working demo | Strangler-fig: Flask app stays alive until each surface is replaced |
| Kernel regressions during extension | Existing physics test suite in CI + golden-master KPI comparisons per engine version |
| Optimiser recommends noise | Common random numbers + CI-aware ranking; recommendations only surfaced when the CI excludes zero |
| Trust data quality derails pilots | Data-quality report at ingestion; calibration falls back per-parameter to flagged defaults |
| Fabricated-looking financials destroy credibility | Cost book is trust-editable, assumptions printed on every business case |
| IG blocks procurement | §10 workstream starts in Phase 1, not after |

---

## 12. Delivery log

- **Phase 0 (done):** repo hygiene; persistence (SQLite/Postgres store: versioned
  department, calibrations, settings, run cache by config hash); every surface
  connected to the one saved department; calibration reaches the product.
- **Phase 1 (done):** finance engine + trust-editable cost book; executive brief;
  one-click board-report PDF with investment page; full-team workforce model;
  React + TypeScript shell at /app (exec brief ported); interactive redesign
  (flow-map drill-downs, workforce charts with demand overlay, who-is-on drill).
- **Phase 2 (done):** kernel physics: measured ambulance handover with held bays,
  LWBS via queue reneging, porter-staffed ward transfers, ENPs on minors,
  1:4 nurse-to-cubicle ratio; arrival streams (ambulance/walk-in/GP/111) as
  share partitions; covariate forecasting with 28-day backtest; surge stress
  tests + inverse staffing solver; CI-gated recommendation engine; Sankey and
  hour-by-area heatmap.
- **Next (Phase 3):** intraday prediction from live feeds, benchmarking vs
  published NHSE statistics, remaining React ports, multi-site ICB view,
  optimisation under budget constraints v2.
