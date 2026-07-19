# Three-Agent Review: Model ED Optimiser
### NHS Emergency Department management, planning and forecasting tool

*Review date: 2026-07-19 · Engine version reviewed: 0.3.8 → 0.4.0 (after implementation) ·
Method: stakeholder panel (Agent 1) → evidence-based capability assessment (Agent 2) →
prioritised implementation, testing and re-assessment (Agent 3).*

**Evidence rule applied throughout:** no capability is claimed unless it is demonstrated in
the code, the automated test suite (`uec_hybrid/tests/run.py`), a live run, or the
documentation. File paths are given as evidence. "Not answered" means exactly that.

---

## 1. Executive summary

The Model ED Optimiser is a hybrid simulation product (patient-level discrete-event
simulation coupled hourly to a whole-hospital system-dynamics model) that lets an ED team
configure their own department without code, calibrate it from their own data, and test
demand, staffing, capacity and whole-system scenarios with Monte-Carlo uncertainty. It is
strong on **scenario planning, capacity-demand analysis, whole-system flow physics and
explainability**, and honest by design (every number comes from the engine; assumptions and
provenance are surfaced).

The stakeholder panel raised **48 questions**. Before this review's implementation phase the
evidence supported: **21 fully answered, 15 partially answered, 12 not answered**. The most
serious findings were: no visible data provenance (a user could mistake demonstration data
for their own ED), no staff-sickness scenario, no time-of-day demand surges, no decision/audit
logging, forecasts shown without uncertainty bands, no access control, no clinical safety
case, and no live system integrations.

Agent 3 implemented and tested **five gaps** in this review cycle (data provenance and
freshness status with demo-data warnings; staff sickness/absence scenarios; time-windowed
demand surges; an append-only decision log plus configuration audit trail; forecast
uncertainty bands with a stated basis). After re-assessment: **26 fully answered, 14
partially answered, 8 not answered**.

**Conclusion: Suitable for controlled pilot only** (section 16). The blocking items for
operational deployment are organisational as much as technical: a DCB0129 clinical safety
case, a DPIA/IG review, user authentication and role-based access, and live (or scheduled)
data feeds with failure alerting.

---

## 2. Description of the tool

| Aspect | What exists (evidence) |
|---|---|
| Engine | Patient-level DES (SimPy; `des/engine.py`) coupled hourly to a whole-hospital SD model (beds, discharges, community; `sd/`, `coupling/cosim.py`); exit-block feedback emerges rather than being asserted (test: admitted LOS 272→596 min under bed pressure) |
| Pathway | NHS "Model Emergency Department" blueprint: streaming, RAT, majors/resus, minors/UTC, paediatrics, SDEC, EEMAC, CDU, frailty, mental health, imaging (CT/X-ray), handover (`pathways/model_ed.json`, 27 editable service stages) |
| Surfaces | Control tower `/`, Executive brief `/exec` (+PDF), Planner `/planner`, Analyst `/analyst`, React shell `/app` |
| Configuration without code | Trust picker (published NHS figures, cited: `data/nhs_trust_snapshot.csv`), Excel/CSV workbook import/export (`ingest/workbook.py`), ECDS calibration (`demand/ecds_seam.py`), auto-calibration to an observed 4-hour %, editable costs/targets/service times |
| Workforce | 16 roles with grades and hourly rates (`workforce/roles.py`), rota editor, staffing-vs-demand by hour, pay-bill, nurse-to-cubicle ratio (1:4), costed recommendations with confidence flags (`optimise/recommend.py`) |
| Planning | Winter forecast (regression: trend, weekday, annual seasonality, bank-holiday effects, 28-day backtest; `planning/forecast.py`), intraday projection, OPEL-style risk with ranked no-capital actions and owners (`planning/operational.py`), surge templates (flu, strike) |
| Uncertainty | Monte-Carlo replication with confidence intervals everywhere; scorecards show good/typical/tough weeks |
| Validation | Conformance checking of every simulated journey (`validation/conformance.py`); per-stage and per-variant timing; external check against a real trust (Barnsley: modelled 71.3% vs observed 67.5% four-hour, untuned) |
| AI assist | Plain-English what-ifs run on the real engine; chatbot grounded in computed data + offline RAG; optional Claude tier that never invents numbers (`assist/`) |
| Persistence | SQLite/Postgres; versioned department configs; run cache keyed by config hash + engine version (`platform/store.py`) |

---

## 3. Agent 1 — Stakeholder panel questions

### Theme 1: Purpose and operational value
| ID | Stakeholder | Question |
|---|---|---|
| Q1 | Executive sponsor | What specific ED decisions does this tool support, and at which horizon — real-time, short-term, strategic? |
| Q2 | ED manager | Who uses it during normal operations, and who during escalation? |
| Q3 | ED manager | What should I decide differently because of it, versus my Excel trackers and daily dashboards? |
| Q4 | Performance/BI analyst | Which measurable outcomes should improve (4-hour, 12-hour, handover, LWBS, time to assessment, LOS, corridor care)? |
| Q5 | Executive sponsor | How do we know its numbers resemble OUR hospital and not a textbook one? |

### Theme 2: Demand forecasting
| ID | Stakeholder | Question |
|---|---|---|
| Q6 | Data scientist | What exactly is forecast (attendances, acuity, admissions, staffing demand), at what granularity, and how far ahead? |
| Q7 | Data scientist | How are day-of-week, time-of-day, seasonality and public holidays handled? |
| Q8 | Operational command | How is winter pressure handled? Extreme weather, outbreaks, major incidents? |
| Q9 | Ambulance liaison | Can it distinguish ambulance arrivals from walk-ins? Forecast them separately? |
| Q10 | ED consultant | Can it forecast by acuity/triage category? Paediatric and adult separately? Mental health separately? |
| Q11 | Bed management | Can it predict how many patients will need admission? |
| Q12 | Data scientist | Are confidence intervals or ranges provided? How accurate is it, and how was accuracy validated? |
| Q13 | Operational command | What happens when the forecast is wrong on the day? |

### Theme 3: Capacity and workforce planning
| ID | Stakeholder | Question |
|---|---|---|
| Q14 | Workforce planning | How does forecast demand translate into required staffing, and which staff groups are covered? |
| Q15 | Workforce planning | Does it account for grade and skill mix, not just headcount? Substantive vs bank vs agency? |
| Q16 | Senior nurse/matron | Does it consider breaks, sickness, training and unplanned absence? |
| Q17 | ED manager | Can it identify the hours where staffing is insufficient, and recommend safer levels? |
| Q18 | Senior nurse/matron | Does it respect safe nurse-to-space ratios (cutting nurses should close cubicles)? |
| Q19 | Finance | Can managers test rotas and see the cost impact of extra staffing? |
| Q20 | ED consultant | Does it identify when more staff will NOT help because the constraint is beds, diagnostics or downstream capacity? |
| Q21 | Clinical site manager | Does it cover treatment spaces — resus, cubicles, escalation spaces — as well as staff? |

### Theme 4: Patient flow and whole-system dependencies
| ID | Stakeholder | Question |
|---|---|---|
| Q22 | Bed management | Does it include downstream capacity — inpatient beds, delayed discharges, community? |
| Q23 | Clinical site manager | Does it include SDEC, UTC, frailty, CDU — and what happens if a site doesn't have one? |
| Q24 | ED consultant | Does it model diagnostic delays (radiology, pathology, specialty review)? |
| Q25 | Operational command | Can it identify WHICH pathway stage is causing congestion, and distinguish an ED problem from a hospital flow problem? |
| Q26 | Ambulance liaison | Does it model handover delays and the 45-minute standard? |
| Q27 | Clinical site manager | Can it estimate boarding / corridor-care risk, and the effect of opening escalation capacity? |

### Theme 5: Scenario planning
| ID | Stakeholder | Question |
|---|---|---|
| Q28 | Operational command | Can it model the panel's 12 scenarios (+15% attendances, evening ambulance surge, 10 nurses sick, >95% occupancy, SDEC cut, bank holiday, flu surge, new assessment area, slower diagnostics, >60-min handovers, paediatric rise, local event)? |
| Q29 | ED manager | For each scenario: what assumptions, what output, what recommended action — and can I change the assumptions? |
| Q30 | Operational command | Can scenarios be compared side by side, saved, and shared with the site team? |
| Q31 | Finance | Are operational AND financial consequences shown? |

### Theme 6: Usability and practicality
| ID | Stakeholder | Question |
|---|---|---|
| Q32 | UX/accessibility rep | Can a busy ED manager use it without data-science knowledge? Is the important thing visible first? |
| Q33 | ED manager | Does it clearly distinguish actual, forecast and planned capacity — and explain WHY pressure is expected? |
| Q34 | Clinical site manager | Can users override assumptions and add local intelligence? Record decisions and actions? |
| Q35 | ED manager | Can output be used in site meetings / bed meetings / escalation calls, and exported? |
| Q36 | UX/accessibility rep | NHS-familiar terminology? Desktop/tablet? WCAG accessibility? |

### Theme 7: Data quality and integration
| ID | Stakeholder | Question |
|---|---|---|
| Q37 | Data engineer | Which systems supply the tool (ED system/EPR, roster, bed management, ambulance)? Refresh frequency? |
| Q38 | Data engineer | How are missing/duplicate/late records handled? What happens when a feed fails? |
| Q39 | BI analyst | How does the user know when data was last refreshed, and whether they are looking at demo or real data? |
| Q40 | BI analyst | Can a metric be traced to its source? Are local coding differences manageable? |

### Theme 8: Forecast reliability and explainability
| ID | Stakeholder | Question |
|---|---|---|
| Q41 | Data scientist | What method, why, and what alternatives were tested? Where is error highest? |
| Q42 | Data scientist | Is performance monitored over time? Is drift detected? Retraining cadence? |
| Q43 | Solution architect | Can users see the drivers and assumptions? Is a forecast prevented from reading as certainty? |
| Q44 | BI analyst | Can actual outcomes be compared with previous forecasts? |

### Theme 9: Safety, governance and accountability
| ID | Stakeholder | Question |
|---|---|---|
| Q45 | Clinical safety officer | Information or recommendation? Could a wrong recommendation create clinical risk? Has DCB0129 clinical safety assessment been done? Is human review required? |
| Q46 | IG/DPO | Is patient-identifiable data displayed or stored? Access controls? Audit trail? Retention rules? |
| Q47 | Equality rep | Health-inequality review? Could it systematically underestimate demand from particular groups? |

### Theme 10: Implementation and adoption
| ID | Stakeholder | Question |
|---|---|---|
| Q48 | Executive sponsor | Ownership, support, training, out-of-hours cover, defect reporting, multi-site scaling, benefit measurement? |

### The 10 questions most important for safe operational use
**Q39** (demo vs real data), **Q45** (clinical safety case + human review), **Q46** (IG, access
control, audit), **Q12** (forecast uncertainty), **Q13** (forecast wrong on the day), **Q16**
(sickness/absence), **Q20** (when staff won't fix it), **Q28** (core scenarios), **Q34**
(overrides + decision recording), **Q38** (feed failure behaviour).

### Questions that could prevent deployment
**Q45** (no DCB0129 safety case), **Q46** (no authentication/RBAC; audit trail was absent),
**Q37** (no live integrations — acceptable for planning, blocking for real-time use),
**Q39** (was unanswered pre-implementation: nothing told a user they were on demo data).

---

## 4–6. Agent 2 — Evidence-based answers

*Statuses below are PRE-implementation (the "before" position). Section 13 shows what changed.*

### Output A: Questions fully answered (21)

| ID | Question (short) | Existing capability | Evidence | Residual risk |
|---|---|---|---|---|
| Q1 | Decisions & horizons | Short-term ops (today/this week: OPEL risk, ranked actions), tactical (rota, winter), strategic (business cases, Model ED gaps). Not real-time (no live feeds) | `planning/operational.py`, `planning/planner.py`, `department/model_ed_gap.py` | Users may expect real-time; must be stated in training |
| Q3 | Better than Excel? | Excel can't simulate queues, exit-block feedback, or paired-seed scenario deltas with CIs; tool adds conformance-validated pathway + costed actions | whole engine; test suite | Value depends on calibration quality |
| Q4 | Which outcomes | 4-hour, 12-hour, LWBS, handover≤45, time-to-assessment (15-min), bed occupancy, corridor/boarding count, pay-bill | `analysis/metrics.py` scorecard; exec brief | LOS by admission class shown in validation, not on scorecard |
| Q5 | Resembles OUR hospital? | Trust picker with cited published figures; ECDS calibration; auto-calibrate to observed 4-hour; external validation vs Barnsley (71.3% vs 67.5% observed, untuned) | `ingest/trust_profile.py`, `tests/run.py` trust-ingest test | One-trust validation; each site should validate locally |
| Q7 | DoW/season/holidays | Regression: trend + weekday + 2-harmonic annual seasonality + bank-holiday and day-after terms; shipped BH list 2022–2027 | `planning/forecast.py` `_design()` | BH list needs annual maintenance |
| Q9 | Ambulance vs walk-in | Four arrival streams (ambulance 29%/walk-in 56%/GP 8%/111 7%), each with own acuity mix; calibratable from ECDS `arrival_mode` | `demand/streams.py`; streams test | Streams share one intraday shape unless calibrated |
| Q11 | Admissions | Disposition modelled per patient (admit/discharge/transfer) from acuity-dependent probabilities; admitted flow drives SD bed stock; boarding measured | `pathways/model_ed.json` routes, `sd/` | It's a simulation estimate, not a per-patient prediction |
| Q14 | Demand→staffing | Staffing-vs-demand by hour per staff area; understaffed hours flagged; rota edits re-run engine; costed recommendations with "within noise" honesty | `workforce/view.py`, `optimise/recommend.py` | Required-staffing formula is ratio/utilisation-based, not acuity-weighted |
| Q17 | Insufficient hours | Understaffed-hours per area surfaced in UI and chat ("where should I deploy?") | `workforce/view.py`; chat deploy intent | — |
| Q18 | Nurse ratios | 1:4 nurse-to-cubicle ratio enforced in builder: cutting nurse rota closes cubicles; verified by test | `department/builder.py`; Phase-2a test | Ratio is configurable but one-dimensional |
| Q19 | Rota cost | Rota editor + weekly pay-bill; role hourly rates editable via workbook/costbook; business cases priced with assumptions attached | `workforce/roles.py`, `finance/` | Bank/agency premiums not distinguished (see B) |
| Q20 | When staff won't help | Pinch-point analysis by hour; tornado sensitivity; recommendation engine reports "no confident gain"; SD makes bed-constrained cases visible (e.g. escalation cubicles +0.0 pts when cubicles aren't binding) | `optimise/recommend.py`, `analysis/scenarios.tornado`; scenario battery #8 | Needs user education: "0 points" is an answer, not a bug |
| Q21 | Spaces | Cubicles, resus, handover bays, SDEC chairs, escalation via scenario/action (+4 cubicles), paediatric area | `pathways/model_ed.json` resources | Waiting-room capacity not a hard constraint |
| Q22 | Downstream | SD layer: inpatient beds, discharge rate, community capacity, baseline occupancy from trust data; exit-block feedback emerges; discharge-push and community levers exist | `sd/`, `coupling/`, operational ACTIONS | Ward-level detail is aggregate, by design |
| Q23 | SDEC/UTC/etc | Each area is a toggle with opening hours; disabled areas re-route patients safely and conformance still passes | `department/config.py AREAS`, builder tests | — |
| Q24 | Diagnostics | Imaging decision, CT, X-ray are pathway stages with editable service times (per-stage means); slowing CT/X-ray measurably drops 4-hour (−1.9 pts in battery) | `model_params.py`; scenario battery #9 | Pathology/specialty review not separate stages |
| Q25 | Which stage congests | Hourly pinch point (moves through the day); per-stage timing; SD interpretation distinguishes ED vs flow problem | `analysis/metrics.py stage_timing`, hourly-pinch test | — |
| Q26 | Handover | Handover bays + handover≤45 metric; halving bays −25.2 pts on the standard in battery | scenario battery #10 | Crew-release time not separately modelled |
| Q27 | Boarding/corridor | Boarding measured (12-hour bed waits, corridor count/day in plan-today); escalation-cubicle action quantified | `planning/operational.py` | — |
| Q32 | Non-technical use | Plain-language surfaces, chatbot, what-ifs in English, glossary; no simulation jargon on product screens | product UI; RAG battery (47/47) | Formal usability testing not yet done |
| Q33 | Why pressure expected | Interpretations everywhere (SD read, scenario impact text, pinch recommendation, forecast components: trend/BH/winter %) | `analysis/*` interpret functions | — |
| Q35 | Meetings/export | Exec brief one-pager + 52 KB PDF decision report incl. investment page; planner outputs actions with owners | `report.py`; report test | No editable/Word export; no daily-plan PDF |

### Output B: Questions partially answered (15)

| ID | Existing functionality | Missing element | Impact on ED operations | Recommended improvement | Priority |
|---|---|---|---|---|---|
| Q2 | Roles implied by surface (manager/exec/planner/analyst) | No named user roles or per-role views; nothing distinguishes escalation use | Confusion over who acts on what | Role-based views after auth lands | Medium |
| Q6 | Daily attendances forecast + hourly shape + winter horizon + intraday projection | No explicit acuity/admissions forecast series; horizon fixed to winter window | Planning beyond winter needs manual work | Parameterise horizon; derive admissions series from sim | Medium |
| Q8 | Winter uplift (learned or slider); flu + strike surge templates | No extreme-weather/outbreak/major-incident templates | Incident planning done by analogy | Add templates (heatwave, norovirus, MI standby) — same seam as flu | Medium |
| Q10 | Acuity mix 1–5 modelled + calibratable; paeds and MH as attributes | Cannot *forecast* acuity/paeds/MH shares forward; fixed shares between calibrations | Case-mix shifts missed until recalibrated | Attribute-share scaling in scenarios + trend per stream | High |
| Q12 | Monte-Carlo CIs on all sim outputs; backtest MAPE (5.3% synthetic) exists | **Forecast displayed without a range**; MAPE only in a note | Numbers can read as certainty | **Implemented this cycle: `range` with basis on every forecast** | **Critical** |
| Q13 | Intraday re-projection from arrivals-so-far (×1.5 morning → 479/day + escalation advice) | Not automatic (user must enter arrivals); no alerting | Late reaction if nobody checks | Feed arrivals via API; threshold alerts | High |
| Q15 | Grades exist (consultant/registrar/SHO; Band 5/6; ENP; HCA) with distinct costs | Substantive vs bank vs agency not distinguished; skills beyond grade absent | Premium-cost decisions unpriced | Add employment-type multipliers to role rates | Medium |
| Q16 | Rota is editable; nurses removable via what-if | **No sickness/absence concept** | The most common operational shock unmodellable in one step | **Implemented this cycle: `staff_scale` + "10% staff sickness" phrasing** | **High** |
| Q28 | 10 of 12 scenarios modellable (see §12) | Evening-window surges and sickness were missing; paeds-share still missing | Core escalation scenarios needed workarounds | **Windowed surges + sickness implemented**; paeds-share on roadmap | **High** |
| Q29 | Assumptions listed in every what-if reply ("I modelled: …"); editable via params/targets/costbook | Scenario assumptions not editable inline in one place | Slower iteration | Scenario builder UI | Medium |
| Q30 | Side-by-side comparison with CIs + interpretation (analyst) | **No save/name/share of scenario sets**; run cache is invisible to users | Site meetings can't reuse yesterday's analysis | Named saved scenarios | High |
| Q31 | Pay-bill deltas, action costs, business cases with ROI | Financial delta not printed on every scenario row | Finance asks twice | Join cost model to scenario table | Medium |
| Q36 | NHS terminology throughout; responsive layout | **Zero ARIA attributes; no WCAG audit; no keyboard-path testing** | Excludes users; NHS standards non-compliance | Accessibility pass (labels landmarks, contrast, keyboard) | High |
| Q41 | Method documented in code (regression + rationale); backtest per upload | No alternative-model comparison recorded; error not broken down by hour/season | Unknown weak spots | Backtest by weekday/season; record baseline naive model | Medium |
| Q44 | Backtest at upload time compares model vs last 28 days | No persistent forecast log to compare with later actuals | Accuracy can't be tracked over months | Persist forecasts; add forecast-vs-actual view | High |

### Output C: Questions not answered (12)

| ID | Missing feature | Why it matters | Affected users | Operational/clinical risk | Priority |
|---|---|---|---|---|---|
| Q34a | Decision/action recording | Site teams must evidence decisions; nothing records them | Site managers, ED managers | Untraceable decisions in incident reviews | **Critical** → **implemented** |
| Q37 | Live integrations (ED system/EPR, roster, bed state, ambulance feeds) | Tool is file-fed (CSV/Excel/ECDS extract); real-time management impossible | All operational users | Stale data driving today's decisions | **Critical** (for real-time use) |
| Q38 | Feed-failure handling & data-quality warnings | No feeds to fail, but nothing warned about stale/absent data either | All | Silent staleness | **High** → warnings **implemented** (feed alerting still future) |
| Q39 | Demo-vs-real indicator, last-refresh visibility | A user could read demonstration numbers as their own ED | Everyone | **The single largest mis-use risk found** | **Critical** → **implemented** |
| Q42 | Model monitoring / drift detection / retrain cadence | Forecast quality degrades silently | BI, data science | Slow drift into bad plans | High |
| Q45 | DCB0129 clinical safety case; hazard log; human-in-the-loop statement | Mandatory for NHS clinical deployment | CSO, trust board | **Deployment blocker** | **Critical** |
| Q46a | Authentication + role-based access | Anyone reaching the URL can change every assumption | IG, all | Config tampering, no accountability | **Critical** |
| Q46b | Config change audit trail | Who changed the 4-hour target from 95 to 78? | IG, BI | Was unanswerable | **Critical** → **implemented** |
| Q46c | DPIA / retention policy docs | Row-level (pseudonymous) ECDS uploads processed in memory; policy not documented | IG/DPO | Governance gap (note: raw uploads are NOT persisted — only derived aggregate patches; `server.py` calibrate) | High |
| Q47 | Equality/health-inequality review | ECDS sample carries `imd_decile`, unused in outputs; under-forecasting deprived groups undetectable | Equality rep | Inequitable planning | High |
| Q48a | Support model, training, out-of-hours ownership | No named owner/support路径 beyond docs | Adopting trust | Orphaned tool risk | High |
| Q48b | Multi-site side-by-side | One department per instance (config swap works; concurrent sites don't) | ICS/region users | Limits system-level use | Medium |

### Output D: Consolidated feature-gap register (ranked)

| Gap ID | Missing functionality | Related Qs | Current state | Required future state | User benefit | Risk if absent | Complexity | Priority |
|---|---|---|---|---|---|---|---|---|
| **G-01** | Data provenance/freshness status + demo-data warning | Q38 Q39 Q40 | **Was:** nothing distinguished demo from real | Visible source, dates, engine version, warnings on every visit | Trust in every number | Mistaking demo for real data | Low | **Critical — IMPLEMENTED** |
| **G-02** | Clinical safety case (DCB0129), hazard log, human-review statement | Q45 | Absent | Safety case owned by a named CSO before any operational use | Deployable at all | Deployment blocker | Organisational | **Critical — not code; must precede deployment** |
| **G-03** | Authentication + RBAC | Q46a Q2 | Absent (open app) | Login, roles (viewer/planner/admin), per-role permissions | Accountability | Tampering, no attribution | Medium-High | **Critical** |
| **G-04** | Config audit trail + decision log | Q46b Q34 | **Was:** absent | Append-only audit of config changes; append-only operational decision log | Incident-review evidence | Untraceable changes | Low | **Critical — IMPLEMENTED** |
| **G-05** | Staff sickness/absence scenarios | Q16 Q28 | **Was:** rota edits only | One-step "10% staff sickness" across all groups incl. nurse-ratio knock-on | Most common shock, one step | Core workflow gap | Low | **High — IMPLEMENTED** |
| **G-06** | Time-windowed demand surges | Q28 Q8 | **Was:** whole-day scaling only | "+30% in the evening", windowed by hour | Evening ambulance peaks, local events | Core workflow gap | Low | **High — IMPLEMENTED** |
| **G-07** | Forecast uncertainty bands + basis | Q12 Q43 | **Was:** point figures | Range with explicit basis (backtest or stated assumption) on every forecast | Prevents false certainty | Overconfident plans | Low | **High — IMPLEMENTED** |
| G-08 | Live/scheduled data feeds + failure alerting | Q37 Q38 Q13 | File-based | Nightly ECDS/roster pulls; freshness alerts; intraday arrivals via API | Real-time relevance | Stale-data decisions | High | High |
| G-09 | Forecast log + accuracy/drift monitoring | Q42 Q44 Q41 | Backtest at upload only | Persisted forecasts vs actuals; error by weekday/season; drift alert | Measured trust | Silent degradation | Medium | High |
| G-10 | Attribute-share scenario scaling (paeds, MH, ambulance share) | Q10 Q28#11 | Fixed shares between calibrations | "paediatric attendances +20%" as a scenario | Case-mix planning | Battery FAIL #11 | Medium | High |
| G-11 | Accessibility (WCAG 2.2 AA) | Q36 | 0 ARIA attributes (measured) | Audit + labels/contrast/keyboard | Inclusive use; NHS standard | Excluded staff | Medium | High |
| G-12 | Saved/named/shared scenario sets | Q30 Q35 | Re-run each time | Save, name, share, export scenario packs | Site-meeting workflow | Rework, lost analysis | Medium | Medium |
| G-13 | Bank/agency employment types; acuity-weighted staffing requirement | Q15 Q14 | Grades + rates only | Employment-type premiums; acuity-weighted requirements | Truer costs | Under-priced plans | Medium | Medium |
| G-14 | Equality lens (IMD/age analysis of demand + outcomes) | Q47 | `imd_decile` ingested, unused | Demand/outcome splits by deprivation & age; under-forecast check | Fair planning | Inequity invisible | Medium | Medium |
| G-15 | Multi-site / ICS view | Q48b | One department per instance | Parallel site configs + side-by-side | Regional planning | Limited scope | High | Low |

**Agent 2 summary (pre-implementation).** The tool **can**: simulate a configurable ED
with whole-hospital feedback; forecast daily demand from history with backtested accuracy;
plan rotas, costs and winter; rank today's escalation actions under OPEL; run rich what-ifs
with CIs; validate itself against the blueprint and one real trust; explain everything in
plain English. It **partially** covers acuity/stream forecasting, financial deltas in
scenarios, and meeting exports. It **cannot** (pre-cycle): show data provenance, model
sickness in one step, model intra-day surges, log decisions or config changes, band its
forecasts, authenticate users, or claim clinical-safety sign-off. **Ready for operational
use?** Not yet. **Decision support?** Yes, with human oversight and the five fixes below.
**Multi-site?** No. **Minimum before deployment:** G-01…G-07 plus DPIA (G-01, G-04…G-07
delivered this cycle; G-02/G-03 remain).

---

## 7–11. Agent 3 — Selection, requirements, design, implementation

### Step 1: Selected for implementation this cycle (rationale)

Selected: **G-01, G-04, G-05, G-06, G-07** — all Critical/High; all required by the core
workflow (or by safe use of it); all rely only on data already inside the product; all
implementable without new infrastructure; each independently testable. **Not selected:**
G-02 (organisational artefact — cannot be "coded"; drafted as a requirement below), G-03
(auth: needs trust identity provider decisions — designed, not built), G-08 (needs real
feeds), G-09/G-10/G-11/G-12 (next phase; G-10 has a designed seam).

### Step 2–3: Requirements and design (implemented features)

**G-01 — Data provenance & freshness** — *"As an ED manager, I need to see whose data the
model is running on and how old it is, so that I never act on demonstration numbers."*
Acceptance: banner on the control tower; source kind (demo/trust/workbook/manual) + dates +
engine version; explicit warnings on defaults; refreshes after any set-up change.
Design: settings key `data_source` stamped by the three set-up endpoints; new
`GET /api/data-status` composes source, department version/updated-at, calibration
timestamp, override flags, warnings; UI banner (`role="status"`, `aria-live="polite"`).

**G-04 — Decision log & audit trail** — *"As a site manager, I need decisions recorded
against the model state they were made on, so incident reviews can reconstruct the day."*
Acceptance: append-only (no edit/delete endpoints exist); each entry stamps department
version + data source + engine version; config changes logged automatically.
Design: `actions` and `audit` tables (`platform/store.py`); `save_setting`/`save_department`
write audit rows; `GET/POST /api/actions`, `GET /api/audit`; decision-log card on Set-up tab.

**G-05 — Staff sickness** — *"As an ED manager, I need to test '10% of staff off sick', so
that I can see tomorrow's risk and pre-book cover."* Acceptance: one phrase; applies to all
staff groups; nurse reduction closes cubicles via the 1:4 ratio; honest note about rounding.
Design: `staff_scale` scenario modifier (`analysis/scenarios.py`) scaling every
`STAFF_RESOURCES` roster and the stashed nurse rota (ratio recompute); parser phrases in
`assist/nl.py`; surfaced in what-if examples.

**G-06 — Time-windowed demand surges** — *"As a flow manager, I need 'evening arrivals up
30%', so that I can plan the 16:00–22:00 pressure that actually happens."* Acceptance:
windowed scaling touches only the window; parser accepts dayparts and explicit windows.
Design: `arrivals_scale` accepts `{"scale": f, "hours": [...]}`; parser converts a demand
change + time window into that form.

**G-07 — Forecast uncertainty bands** — *"As a data scientist, I need every forecast to
carry a range and its basis, so that no one plans on a point estimate."* Acceptance: both
forecast paths return `range {low, high, basis}`; basis says *backtest ±x%* or *stated
assumption ±15%*; summary sentence carries the band.
Design: `planning/forecast.py` — measured band from 28-day-holdout MAPE when history
suffices, otherwise an explicitly-labelled assumption; `from_data` flag on both.

**G-02 (specified, not coded) — DCB0129 requirements:** named Clinical Safety Officer;
hazard log seeded with: H1 demo-data mistaken for real (mitigated by G-01), H2 forecast
read as certainty (mitigated by G-07), H3 untracked config change skews results (mitigated
by G-04), H4 recommendation followed without review (mitigation: information-only labelling
+ human-review statement in UI — next phase); safety case report before pilot.
**G-03 (designed, not coded):** Flask-Login or trust SSO (OIDC) → roles viewer/planner/admin;
decision log gains verified authorship; write endpoints gated to planner+; audit gains user IDs.

### Step 4: What was actually implemented (all tested)

| Change | Files |
|---|---|
| `staff_scale` + windowed `arrivals_scale` modifiers, nurse-ratio recompute under sickness | `uec_hybrid/analysis/scenarios.py` |
| Sickness + windowed-demand + "goes up/down" parsing; new examples | `uec_hybrid/assist/nl.py` |
| Forecast `range` with basis on both paths; `from_data` flag | `uec_hybrid/planning/forecast.py` |
| `AuditRow`, `ActionRow`, `department_meta`, `setting_meta`, `audit_trail`, `log_action`, `list_actions`; calibration timestamps; audited saves | `uec_hybrid/platform/store.py` |
| `/api/data-status`, `/api/actions`, `/api/audit`; `data_source` stamping on department/trust/workbook endpoints | `uec_hybrid/app/server.py` |
| Provenance banner (aria-live) + decision-log card | `app/templates/product.html`, `app/static/product.js` |
| 30+ new assertions incl. governance endpoints, sickness physics, windowed surges, forecast bands | `uec_hybrid/tests/run.py` |
| `ENGINE_VERSION` 0.3.8 → 0.4.0 (cache invalidation) | `uec_hybrid/platform/store.py` |

---

## 12. Test results (Step 5 — live scenario battery, 3 Monte-Carlo reps)

| # | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|
| 1 | Attendances +15% for a week | 4h/12h worsen | 4h −6.1 pts, 12h +0.8 pts vs 72% base | **PASS** |
| 2 | Ambulance arrivals rise 16:00–22:00 | evening-window surge | windowed +30%: 4h −4.4 pts, handover −0.4 | **PARTIAL** — applies to all streams, not ambulances alone (G-10) |
| 3 | 10 registered nurses off sick | cubicles close via ratio | 4h −7.2 pts, 12h +15.5 pts, LWBS +1.1 | **PASS** |
| 4 | Bed occupancy > 95% | OPEL raised; discharge push ranked | OPEL 3; top action = push discharges | **PASS** |
| 5 | SDEC capacity reduced | flow worsens | 4h +2.0 pts *(within ±2-pt noise at 3 reps; rerun with ≥10 reps for decisions)* | **PASS** with noise caveat |
| 6 | Bank holiday Monday | learned uplift | +13.9% learned from history; band ±5% backtested | **PASS** |
| 7 | Flu / respiratory surge | template runs | `flu` stress-test runs (baseline vs surge deltas) | **PASS** |
| 8 | Open additional assessment area | quantified | +0.0 pts — cubicles not the binding constraint at baseline (matches pinch-point analysis: minors/streaming binds) | **PASS** (honest zero) |
| 9 | Diagnostics +30% (CT, X-ray) | 4h falls | −1.9 pts via per-stage service-time override | **PASS** |
| 10 | Handover delays > 60 min | handover metric worsens | handover≤45 −25.2 pts, 4h −2.4 pts | **PASS** |
| 11 | Paediatric attendances rise | share scaling | **not modellable** — fixed paediatric fraction | **FAIL** → G-10 roadmap |
| 12 | Major local event (evening) | windowed surge | 4h −3.1 pts, LWBS +2.2 pts | **PASS** |
| 13 | Missing/delayed data feed | warnings shown | 2 warnings incl. demonstration-defaults notice | **PASS** |
| 14 | Actuals above forecast | reprojection + escalation | ×1.5 of expected → 479/day, escalation advised | **PASS** |
| 15 | User overrides an assumption | applied AND audited | target changed; audit captured the change | **PASS** |

**13 PASS / 1 PARTIAL / 1 FAIL.** Full automated suite (60+ checks incl. every prior
feature): **all green** after implementation. Defects found during the cycle: one JS syntax
slip caught by `node --check` before commit; no runtime defects surfaced by the battery.

---

## 13. Before-and-after assessment (Step 6)

| Question | Original status | Updated status | Change implemented | Remaining limitation |
|---|---|---|---|---|
| Q39 demo vs real / freshness | Not answered | **Fully answered** | `/api/data-status` + banner + warnings | Feed-level freshness needs G-08 |
| Q34 record decisions | Not answered | **Fully answered** | Append-only decision log with model-state stamps | Authorship unverified until auth (G-03) |
| Q46b audit trail | Not answered | **Fully answered** | Append-only config audit | User identity needs G-03 |
| Q16 sickness/absence | Partial | **Fully answered** | `staff_scale` + one-phrase what-if | Breaks/training patterns still implicit |
| Q28 core scenarios | Partial (8/12) | **Partial (11/12)** | windowed surges + sickness | Paeds share (G-10) |
| Q12 forecast uncertainty | Partial | **Fully answered** | `range` + basis on every forecast | Persistent accuracy tracking is G-09 |
| Q38 feed failure | Not answered | **Partial** | staleness/default warnings | Alerting needs real feeds (G-08) |
| Q43 certainty guard | Partial | **Fully answered** | bands + "plan for X–Y" phrasing | — |
| Q8 surge coverage | Partial | **Partial+** | evening windows now covered | weather/outbreak templates pending |
| Q13 forecast wrong | Partial | **Partial+** | (existing intraday) + demo warnings | auto-ingest of arrivals pending |

**Net position: 26 fully answered · 14 partial · 8 not answered** (was 21/15/12).
Still open and blocking: **Q45 (clinical safety case), Q46a (auth/RBAC), Q37 (live feeds
for real-time use), Q47 (equality review)**.

---

## 14. Remaining risks and limitations

1. **No clinical safety case (DCB0129)** — the tool is information/decision-support, but NHS
   deployment requires the safety case regardless. Hazard log seeded in §11.
2. **No authentication or RBAC** — anyone with the URL can reconfigure the model. Audit rows
   exist but cannot name the actor.
3. **File-fed, not live** — right tool for planning; not yet for minute-to-minute command.
4. **Forecast accuracy** is backtested per upload (±5% on the synthetic history) but not
   monitored over time; bank-holiday list needs annual refresh; no drift detection.
5. **Single external validation point** (Barnsley). Each adopting site must validate locally
   (the workflow exists: trust picker → calibrate → compare observed).
6. **Small-N noise**: at low replication counts scenario deltas under ~2 points can be noise;
   the UI says so, but meeting decisions should use ≥10 replications.
7. **Accessibility** unaudited (two aria attributes added this cycle; a proper WCAG pass is G-11).
8. **Equality**: deprivation/age data is ingested but not analysed (G-14).

## 15. Recommended next development phase (in order)

1. **G-03 auth + RBAC** (unblocks named audit, per-role views) and **G-02 safety case** in parallel — both deployment gates.
2. **G-08 scheduled data feeds + freshness alerting** (nightly ECDS/roster pulls; intraday arrivals endpoint already exists to receive them).
3. **G-09 forecast log + accuracy/drift monitoring** (persist every forecast; nightly compare).
4. **G-10 attribute-share scenarios** (fixes the one FAIL: paediatric/MH/ambulance share scaling).
5. **G-11 accessibility pass**, **G-12 saved scenario packs**, **G-14 equality lens**.

## 16. Operational readiness recommendation

> ### Suitable for controlled pilot only
>
> **Basis.** The engine physics are validated (conformance-checked pathway, emergent
> exit-block, one real-trust comparison within 3.8 points untuned), the planning and
> scenario workflow now covers 11 of the panel's 12 scenarios with honest uncertainty, and
> this cycle closed the worst mis-use risk (invisible demo data) and the governance basics
> (decision log, audit trail). It is genuinely useful **today** for winter planning, rota
> testing, business cases and escalation rehearsal — **with a human between the tool and
> any action**, which its information-only framing already assumes.
>
> **Why not "operational decision support with human oversight" yet:** that grade requires
> the DCB0129 clinical safety case, user authentication with role-based access, and a
> DPIA — none of which exist. These are organisational gates, not engineering ones, and a
> pilot is the correct vehicle to produce them.
>
> **Pilot definition proposed:** one trust, planning/meeting use only (no real-time
> command), named CSO and information-asset owner, local calibration + validation against
> three months of observed performance, decision log in active use, exit criteria = safety
> case signed + G-03 delivered + forecast accuracy tracked for the pilot period. On exit,
> re-grade to **"suitable for operational decision support with human oversight."**
