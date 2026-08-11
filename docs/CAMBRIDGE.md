# Cambridge University Hospitals (CUH / RGT) — working file

Goal: a **Cambridge version of the Model ED Optimiser for the CUH COO in ~2 weeks**,
built from published data plus the ED pathway the Moorhouse team has already
mapped — presented as *their* department, never as a mock-up, with every
assumption labelled on screen.

**Nothing in this repo carries an unverified number.** Every CUH figure below is
a named slot pointing at the primary publication it must be transcribed from.
The product skips empty slots and keeps flagging them as assumptions.

---

## 0. CURRENT BUILD STATE — real published inputs + labelled synthetic distributions

The primary publication files are now **committed under `data/`** (pushed by
the team) and the headline figures are transcribed from them with per-figure
citations in `data/rgt_published.json`. Distribution blocks stay SYNTHETIC
(labelled on the banner) until the CUH CHEQS extracts land.

| Value in the build | Status | Source |
|---|---|---|
| Attendances **400.5/day** (Type 1, Jun 2026; all-types 595/day) | **REAL** | `data/June-2026-CSV-Wfg38l.csv`, row RGT (12,015 T1 / 30) |
| 4-hour **52.93%** T1 (validation) | **REAL** | same file; ECDS provisional corroborates 53.58% T1&2 |
| 12-hour **3.7%** (445 DTA 12h+ waits / T1; ECDS 12h-from-arrival 11.32%) | **REAL** | same file + `ECDS_Performance_Provisional_Jun_26…xlsx` |
| G&A beds **1,068**, occupancy **89.26%** (Q4 2025-26) | **REAL** | `data/Beds-Open-Overnight-Web_File-Q4-2025-26.xlsx`, NHS Trust by Sector, RGT |
| Paediatric share **19.71%** (T1 footprint includes the paeds ED) | **REAL** | ECDS Paediatric Performance, RGT (2,420 / 12,280) |
| MH share **2.57%** | **REAL** | ECDS Mental Health, RGT (315 / 12,280) |
| Hourly shape, acuity mix, ambulance 30%, admission-by-acuity | SYNTHETIC, labelled | REPLACE: CHEQS extracts 1/3 |
| Areas, capacity, rota, service times | template defaults, flagged | ops workbook + CHEQS moves extract |

Modelled-vs-observed: run `python3 -m uec_hybrid.ingest.trust_profile RGT` —
with a real 52.93% target, expect a gap >10pp until service times are
calibrated (auto-calibration or CHEQS dwell times).

**Drop-in map when real data lands** (then `python3 -m uec_hybrid.ingest.seed RGT --warm`):

| Incoming | Goes into |
|---|---|
| CHEQS 1 (arrivals hour × mode) | `rgt_published.json` → `hourly_shares` (+`ambulance_share`), granularity 'provider' |
| CHEQS 2 (arrivals by area) | Areas confirm + streaming splits (pathway config) |
| CHEQS 3 (area × destination, triage) | `admission_rate_by_acuity` / `acuity_mix_pct` + routing |
| CHEQS 4 (moves extract) | transitions + per-area dwell → ServiceTimes tab of the seed workbook |
| CHEQS 5 (timings) | ServiceTimes tab cross-check |
| CHEQS 7 (MH) | `mental_health_share` |
| CHEQS 8 (monthly performance) | snapshot CSV `four_hour_pct`/`twelve_hour_pct` (validation) |
| CHEQS 9 (discharges by hour) | Downstream answers → SD block |
| NHSE monthly A&E + KH03 | snapshot CSV attendances/beds/occupancy (replace synthetic) |
| Ops workbook (Capacity + Questions) | seed workbook Capacity sheet + community_capacity |

## 1. How the Cambridge version is stood up (reproducible)

```bash
python3 -m uec_hybrid.ingest.seed RGT --warm
python3 -m uec_hybrid.app.server        # product on http://127.0.0.1:5000
```

The seed composes three committed files through the product's own ingest paths:

| File | Carries | Status |
|---|---|---|
| `uec_hybrid/data/nhs_trust_snapshot.csv` (row `RGT`) | attendances/day, beds, occupancy (INPUTS); 4-hour %, 12-hour % (VALIDATION targets) | **to transcribe** |
| `uec_hybrid/data/rgt_published.json` | hour-of-arrival shape, acuity mix, ambulance share, admission rate by acuity → calibration patch | **to transcribe** |
| `uec_hybrid/data/seeds/rgt_cuh_workbook.xlsx` | areas + hours, rota, REAL physical capacity, costs, service times | **fill at the Moorhouse/CUH sessions** |

Re-running the seed after editing any of the three refreshes the department.
`--warm` pre-computes the control tower, exec brief and gap view so the demo
opens instantly.

---

## 2. Published-data transcription checklist (≈30–60 min with normal internet)

Work through in order; record the period ("May 2026") next to each number.

1. **NHS England, A&E Attendances and Emergency Admissions (monthly)** —
   provider-level file, row RGT.
   → `attendances_per_day` (state Type 1 vs all types), `four_hour_pct`,
   `twelve_hour_pct` → snapshot CSV + `rgt_published.json`.
   https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/
   ⚠ CUH was a UEC field-testing site **May 2019 – May 2023** (4-hour data not
   reported in that window) — use recent months and say so if asked.
2. **NHS England, Bed Availability and Occupancy (KH03, quarterly, overnight)** —
   provider RGT → `inpatient_beds` (G&A available), `bed_occupancy` → snapshot CSV.
   https://www.england.nhs.uk/statistics/statistical-work-areas/bed-availability-and-occupancy/
3. **NHS Digital, Hospital Accident & Emergency Activity (annual, ECDS-based)** —
   provider-level CSV/dashboard → hour-of-arrival distribution, acuity mix,
   ambulance-arrival share, admitted share by acuity, under-16 share
   → `rgt_published.json`. Where only national distributions are open, use them
   and set `granularity` — the product will say "national shape, trust volume".
   https://digital.nhs.uk/data-and-information/publications/statistical/hospital-accident--emergency-activity
4. **Winter/UEC Daily SitRep (seasonal) or Ambulance Quality Indicators** —
   handover >30/>60 min for context/validation → `rgt_published.json`.
5. Optional: refresh peer figures for the exec-brief benchmark upload
   (`/api/benchmarks`, CSV: organisation, attendances_per_day, four_hour_pct,
   twelve_hour_pct) with real East-of-England / London peers from source 1.

Then re-run the seed and check `validate_against_observed`:
`python3 -m uec_hybrid.ingest.trust_profile RGT` prints modelled vs observed
4-hour. Gap > 10 points → run auto-calibration (Analyst → Data & calibration,
or `/api/auto-calibrate`) against the observed figure.

---

## 3. What only Cambridge can tell us — the one-hour session checklist

The Moorhouse team has already process-mapped the CUH ED; this converts their
map into the seed workbook. Nothing here is in any open dataset.

**A. Pathway shape (drives everything else)**
- Walk the process map against the Model ED blueprint. Which of the 9 areas
  exist: RAT · co-located UTC · fit-to-sit · paeds area · EEMAC · SDEC · CDU ·
  frailty (FAU) · MH liaison? Opening hours for each?
- Anything the map has that the blueprint lacks (or wires differently)?
  → decision gate: subset = pure config; extra/re-wired stages = small,
  additive code change (new area entry, default-off).

**B. Physical capacity → workbook `Capacity` sheet**
- Majors cubicles · resus bays · CDU beds · SDEC chairs · FAU beds · EEMAC
  spaces · UTC rooms · paeds cubicles · minors spaces · fit-to-sit chairs ·
  ambulance handover bays · CT scanners · X-ray rooms.

**C. Workforce → workbook `Rota` sheet** *(EXPLICITLY DEFERRED — agreed with the
team: the first CUH build is demand + activity + service capacity only, no
workforce anything. Staffing stays template defaults, flagged as assumptions.
The tool is visibly ready for workforce data when the COO offers it.)*
- Later: shifts per role (role, start, end, count); nurse-to-cubicle ratio if not 1:4.

**D. Whole-hospital context**
- Community / virtual-ward pull (default 60/day is synthetic), ward discharge
  reality, escalation triggers.

**E. Scope + validation**
- Is the modelled footprint the adult Type 1 ED only? (Addenbrooke's runs a
  **separate paediatric ED** — the paeds area toggle is not the same thing.)
- Their observed 4-hour/12-hour (they have the data and offered comparison) —
  used only to validate/calibrate, shown as such.

---

## 3a. The one-shot data ask (sent via Yasmin — control tower first, aggregate only)

Agreed scope: recreate the **control tower / ED flow diagram** from demand,
patient activity and service capacity — **no workforce data**. All extracts are
aggregate counts from CUH's self-service dashboard (no identifiers, no clinical
detail; small-number suppression fine). Suggested period: most recent 13 full
weeks for profiles; 12 months monthly for performance. Capacity/layout is
confirmed in a 30–45 min session with the ED ops manager (Claire Hanford —
name from the call, verify), not a data extract.

| # | Extract | Shape | Feeds |
|---|---|---|---|
| 1 | Arrivals by hour × mode (ambulance/walk-in/other) | hour 0–23 × mode × count | `hourly_shares` + ambulance stream share |
| 2 | Arrivals into each ED area by hour | area × hour × count | streaming splits + flow-map calibration |
| 3 | Acuity (1–5) × disposition (admit/discharge/transfer) | counts | `acuity_mix_pct` + `admission_rate_by_acuity` |
| 4 | Area→area transition counts (incl. ward/discharge sinks) | from × to × count | Sankey/flow-map link volumes |
| 5 | Timings: median + p95 for arrival→triage, →first clinician, →DTA, DTA→departure, total (admit vs discharge) | minutes | per-stage service-time calibration (ServiceTimes tab) |
| 6 | Monthly 4h %, 12h DTA, LBBS %, handover >30/>60 (12 months) | monthly | validation targets (snapshot CSV + `validate_against_observed`) |
| 7 | *Optional:* daily attendance totals, 24 months | date × count | `/api/forecast-data` (planner, later) |
| 8 | Imaging activity: attendances receiving X-ray / CT (count or %), median request→completion turnaround | counts + minutes | imaging nodes (`ct_scanner`/`xray_room` demand + service time) — capacity alone comes from the Claire session |
| 9 | Attendances flagged as mental-health presentations (count) | count | `mental_health_share` attribute → MH liaison node demand |

Item 4 destinations must include admitted / discharged / transferred / referred
to community, and CUH should use their own location names verbatim — we map
them to the process map (and the journey-string fallback parses that same
vocabulary). Note: imaging is often not a location move in ED systems, so it
needs its own extract (item 8) rather than relying on transitions.

**Part B must also cover downstream flow** (the exit-block mechanism — the
bottleneck the control tower exists to show): typical inpatient discharges per
day (+ morning/afternoon skew), community / virtual-ward pull per day (model
default 60/day is synthetic), and their own G&A beds + occupancy figure
(otherwise published KH03). Feeds `sd.ward_discharge_capacity_per_hour`,
`sd.community_clearance_per_hour`, `community_capacity`, `inpatient_beds`,
`baseline_bed_occupancy`. Optional Part A line: daily inpatient discharges
(date, count) for the same 13 weeks.

**Fallback for 2 + 4**: CUH holds a patient-level extract with each attendance's
location sequence comma-delimited in one field. If aggregates are harder to
produce, a de-identified 3-column cut (arrival date+hour, location sequence,
final disposition) lets us derive both — parse the sequence, count transitions,
and build the calibration patch. Only one of the two routes is needed.

**Scope question asked once**: adult Type 1 ED only vs including the separate
paediatric ED — decides every denominator above.

**CHEQS inventory outcome (Josh, via Yas)** — final pull agreed, nothing further:
arrivals by hour × mode ✓ · arrivals by area by hour ✓ · area × discharge
destination ✓ (replaces acuity × disposition; acuity falls back to published if
absent) · patient-moves extract, pseudonymised, 4 weeks ✓ (replaces aggregate
transitions AND yields per-area dwell → real service-time calibration) ·
timings monthly, by majors/minors ✓ · X-ray/CT counts, no turnaround (stays a
labelled assumption) · MH monthly counts from their MH dashboard ✓ · monthly
performance 12 months ✓ (their "left without being seen" = LBBS). Non-CHEQS
piece: docs/cuh_minimum_data.xlsx (Areas / Capacity / Downstream) with the ops
team. Remaining assumptions after landing: imaging turnaround, workforce
(agreed), renege/patience.

---

## 4. Assumptions register — what the banner will still flag, and why that's fine

Until the sessions fill them, these stay template values and the product's
provenance banner (now on every surface: control tower, exec brief, planner,
analyst) lists them as assumptions:

- physical capacity (all counts) — **the exact gap the Portsmouth demo Q&A
  called out; the Capacity sheet is its fix**
- enabled areas + hours, rota, community capacity
- arrival profile / acuity / admission rates (until `rgt_published.json` is filled)
- per-stage service times (never published — auto-calibrate to observed 4-hour)
- cost book £ and staff rates (finance must confirm before any business case)

## 5. Demo cautions (say it before they ask)

- "Every number's provenance is on screen — green = published/provided,
  amber = still an assumption. Give us the counts and the banner shrinks."
- The 4-hour reporting gap 2019–2023 (field-test site) — we use recent months.
- The "divert to UTC" planning lever models *demand removed from the ED*, not a
  routed UTC co-location — phrase it as "redirect away from the front door".
- Model ED gap benefits are simulated counterfactuals (that's the strength);
  their cost bands are editable planning assumptions.

## 6. Branch / preservation

- `main` = the original build (Portsmouth demo was `main` + selecting RHU at
  runtime; nothing Portsmouth-specific exists in code).
- **All Cambridge work lives on `claude/cambridge-data-plugin-feedback-hjrm3r`.**
- Side-by-side demo of both: two checkouts, two databases, two ports.
  (True multi-department in one instance is roadmap G-15 — the store already
  keys by department; not needed for this demo.)
