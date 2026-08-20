# CUH data log

This is the record of what Cambridge (CUH) has actually sent us, where each
file lives, and which model input each one feeds. Batch 1 arrived on 12 August
2026 from Joshua at CUH as a single zip of 25 CHEQS extracts. The files are
committed under `data/cuh/` and every number the model takes from them is
cited back to its file in `uec_hybrid/data/rgt_published.json`, so nothing in
the build is more local than its source.

One file needed handling before it could enter the repository. The patient
moves extract arrived with row-level identifiers (CSN and MRN columns). Those
are patient-identifiable, so the committed copy, `Patient moves 4 weeks
(deidentified).xlsx`, has the MRN column removed entirely and the CSN replaced
with a sequential visit id (the same visit keeps the same id, so pathways can
still be followed). The original file with identifiers was not committed and
should stay inside CUH and on the machine of whoever needs it, nowhere else.

## What each file is used for

| File in `data/cuh/` | What it holds | Period | Feeds |
|---|---|---|---|
| `Arrivals and departures by hour May to Aug 26.xlsx` | All front-door arrivals and departures per hour of day (46,132 arrivals; excludes direct-to-SDEC) | May to Aug 2026 | `hourly_shares` in `rgt_published.json`, the model's 24-hour arrival shape. Also the denominator of `ambulance_share` |
| `Arrivals Ambulance May to Aug 2026.xlsx` | Ambulance arrivals per hour (8,830) | May to Aug 2026 | Numerator of `ambulance_share` (19.14%) |
| `arrivals ambulant May to Aug 2026.xlsx` | Walk-in arrivals per hour (34,088) | May to Aug 2026 | Cross-check: ambulance plus walk-in plus other reconciles to the total within 3,214 (other modes) |
| `Arrivals Other.xlsx` | Other-mode arrivals, roughly one an hour | May to Aug 2026 | Confirms the residual arrival mode is small; not a model input |
| `Arrivals area by hour.xlsx` | Average daily departures by area (despite the name there is no hourly split inside) | period average | Cross-check of the area mix; sums to about 590/day including SDEC |
| `Performance Resus.xlsx`, `Performance Majors Trolleys.xlsx`, `Performance Majors Ambulant.xlsx`, `Performance Minors.xlsx` | Monthly attendances, admissions, 4-hour breaches and median stage times per area | Feb to Aug 2026 (Aug is a part month, so sums use Feb to Jul) | `acuity_mix_pct` (area-proxy bands), `admission_rate_by_acuity`, stage-time medians for calibration checks, per-area 4-hour rates for validation |
| `Performance Paeds.xlsx` | Same, paediatric ED area | Feb to Aug 2026 | `paediatric_share` (13.35% of the front door) plus paeds admission rate (13.4%) |
| `Performance SDEC.xlsx` | Same, SDEC | Feb to Aug 2026 | SDEC reference block: 143.8 attendances/day, 16.1% admitted. SDEC is modelled as a streamed destination, so this validates the stream rather than the front door |
| `TID Resus.xlsx`, `TID Majors Trolleys.xlsx`, `TID Majors Ambulant.xlsx`, `TID Minors.xlsx`, `TID Paeds.xlsx`, `TID SDEC.xlsx` | Monthly time-in-department stats (max, mean, median, 95th percentile) split by admitted, non-admitted, unknown | Feb to Aug 2026 | Validation targets. June 2026 medians and 95th percentiles are transcribed into the `cuh_extracts` block of `rgt_published.json` |
| `Discharges Resus.xlsx`, `Discharges Majors Trolleys.xlsx`, `Discharges Majors Ambulant.xlsx`, `Discharges Minors.xlsx`, `Discharges Paeds.xlsx`, `Discharges SDEC.xlsx` | Average departures per weekday by disposal destination, per area | period average | Admission-route reading: EAU3/EAU4/N2 rows are assessment-unit admissions, Admit rows are direct ward admissions, so trolleys admit mostly direct (41 vs 12) while majors ambulant admits mostly via assessment units (32 vs 6). Not yet auto-consumed |
| `Discharge Destinatoin.xlsx` | The same disposal table for the whole department | period average | Overall sanity check on the per-area tables (about 602 departures per weekday) |
| `Patient moves 4 weeks (deidentified).xlsx` | 4,474 area-to-area moves for 3,960 visits, identifiers removed | 10 Jul to 9 Aug 2026 | Length of stay in SAU SDEC, Clinic 5 SDEC, EAU3 and EAU4, and ED-to-ward transfer timing. Feeds the downstream (bed) side checks; not yet auto-consumed |

### Batch 2 (received 13 Aug 2026)

| File in `data/cuh/` | What it holds | Period | Feeds |
|---|---|---|---|
| `Investigation types.xlsx` | Weekly counts per SNOMED-coded investigation (225,053 over the 14 complete weeks; CT 8,065, plain radiography 17,284) | w/e 3 May to 16 Aug 2026 | **`investigation_rates` in `rgt_published.json` — the only batch-2 file wired into the model.** CT 0.1828 and X-ray 0.3918 per attendance replace an invented `imaging_decision` routing |
| `Procedure type.xlsx` | Weekly counts per SNOMED-coded procedure (80,079 over 14 complete weeks; drug administration 17,725 leads) | w/e 3 May to 16 Aug 2026 | Reference only. No procedure seam exists yet |
| `4-hour perf.xlsx` | Weekly 4-hour performance, split CUH on-site vs MIU (50 weekly points each) | 7 Sep 2025 to 16 Aug 2026 | Validation. First real week-to-week spread the build has had: typical 60.9%, best 69.5%, worst 54.7% |
| `12-hour perf.xlsx` | Weekly 12-hour performance, same split | 7 Sep 2025 to 16 Aug 2026 | Validation. Typical 10.0% over 12 hours, best 3.3%, worst 13.1% |
| `MH Disposals.xlsx` | Daily mental-health disposal counts across 15 destinations (1,067 attendances) | 1 May to 12 Aug 2026 | Reference. MH admission rate 18.3%, did-not-wait 12.2%, 10.3 attendances/day. No MH-specific parameter exists to consume it |
| `Discharges by day.xlsx` | Whole-trust inpatient discharges by day of week (19,352) | period total | **Not consumable.** The engine has no day-of-week dimension. Sunday is 29% of Monday |

Two counting traps in batch 2, both easy to walk into:

* `4-hour perf.xlsx` is CUH's **internal** basis. Its 60.9% mean sits about seven
  points above the published Type 1 series (52.93%), the same gap already logged
  for the Feb to Jul figure of 59.5%. Do not compare it with the published target.
* `12-hour perf.xlsx` measures **12 hours from arrival**, the ECDS basis (11.32%),
  not the decision-to-admit basis the model's `twelve_hour_pct` target uses (3.7%).
  The two differ by roughly a factor of three; they are not interchangeable.

The imaging rates are **workload** figures — investigations per attendance, so a
patient scanned twice counts twice. That is the right basis for a capacity model,
because it reproduces demand on the CT scanner and the X-ray room, but it is an
upper bound on the proportion of patients imaged. Their denominator is the
five-area front door (450.1/day, May to Jul 2026), which is the population the
model's imaging step serves. If CUH's extract also counts SDEC activity the
correct rates are CT 0.139 and X-ray 0.297; **CUH to confirm the footprint.**

## Reconciliation notes, written down so nobody trips on them later

The extracts and the national publications count differently, and the gaps are
real rather than errors. The build keeps the published figures as anchors and
validation targets, and uses the extracts for shapes, mixes and rates, which
are robust to the counting basis.

CUH's own front-door count (resus, trolleys, majors ambulant, minors, paeds)
is 80,771 attendances over Feb to Jul 2026, which is 446.2/day. The published
Type 1 figure for June is 400.5/day. The 11% gap will be a counting-basis
difference (planned returns and did-not-waits sit differently in the two
series). The model's volume anchor stays the published 400.5/day.

The internal 4-hour position looks better than the published one for the same
department: 59.5% of front-door attendances within 4 hours over Feb to Jul on
the CHEQS basis, against 52.93% published for June. Did-not-waits leave early
and so count as within-4-hours internally. The published figure remains the
validation target.

The paediatric share differs by definition. The paeds ED area sees 13.35% of
front-door attendances, while the published age-based measure says 19.71% of
attendances are children, because children treated in minors or majors still
count by age. The model routes by area, so it uses 13.35% and keeps the
published figure as the age-based cross-check.

The hourly arrivals file reconciles with the front-door footprint, not the
SDEC-inclusive one: 46,132 arrivals over roughly 103 days is about 448/day,
which matches the 446/day front-door count and confirms direct-to-SDEC
referrals are not in it.

Departures per weekday in the disposal tables sum to about 602, above the
arrival rate, most likely because a patient who moves between areas departs
each area once. Treat those tables as destination shares, not volumes.

## Batch 2 against what was actually asked for

CUH's covering note said "not all available quite as asked". Mapping the two
batches onto the nine numbered items of the request, so the residue is explicit:

| # | Asked for | Status | What is actually missing |
|---|---|---|---|
| 1 | Arrivals by hour, split ambulance / walk-in / other | **Covered** (batch 1) | Nothing material. The exact date range is not stamped in the files |
| 2 | Arrivals into each ED **area** by hour | **Not delivered** | `Arrivals area by hour.xlsx` has no hourly split — it is six rows of average departures per area. The model therefore applies ONE department-wide arrival shape to every area |
| 3 | Discharge destination per area, plus attendances by **triage category** | **Half** | Area × destination is complete. **Triage category is absent from both batches** — no file anywhere carries one |
| 4 | Patient moves, 4 full weeks, pseudonymised | **Covered** (batch 1) | — |
| 5 | Stage timings, monthly, median + 95th/max | **Most** | No split of initial **nursing** vs initial **medical** assessment (one combined "Arr to Init Asst"). 95th/max exist for time-in-department only, not per stage |
| 6 | CT / X-ray counts **split by area**, plus **number per visit** | **Half** | Delivered department-wide only. Neither the area split nor the per-visit count came, which is exactly what would settle the denominator and the workload-vs-proportion question |
| 7 | MH presentations and disposal split | **Covered, better than asked** | Daily rather than monthly, full 15-way disposal split |
| 8 | Monthly 12 months: 4-hour, 12-hour, handovers >30/>60, LWBS | **Half, now topped up from public data** | 4-hour and 12-hour came weekly for 50 weeks (better than asked). Handover >30/>60 did not come from CHEQS but has been filled from the NHSE UEC SitRep (see below). No standalone LWBS series, and none is published nationally |
| 9 | Trust discharges by hour of day **and** day of week | **Half** | Day of week only. **Hour of day did not come** |

### Ambulance handover: filled from public data, not CHEQS

CUH did not send handover times, but NHS England publishes them per trust in the
UEC Daily SitRep ambulance collection, so **this gap is closed without going back
to CUH**. Committed as `data/Web-File-Timeseries-Ambulance-Collection-dpkj63.xlsx`:

| Measure | RGT, winter 2025-26 |
|---|---|
| Handovers (known time) | 11,028 of 11,571 |
| Over 30 minutes | 22.45% |
| Over 45 minutes | 15.81% |
| Over 60 minutes | 13.14% |
| **Within 45 minutes** | **84.19%** — the figure the control tower's handover tile is judged against |
| Handovers per day | 91.8 |

Two things to hold onto. The collection runs **24 Nov to 29 Mar only**, so these
are winter figures at the tough end of the year and are not comparable
like-for-like with the May-Aug CHEQS extracts. And the file repeats its column
labels — counts sit at block offsets 0-6, proportions at 9-13 — so reading by
label alone silently returns proportions; read the count columns.

Volume cross-check: 91.8 ambulance arrivals/day here against 19.14% x 450.1/day
= 86/day from CHEQS. Consistent, and higher in winter as expected.

Three items would close nearly everything else, and all three are small:

1. **Attendances by triage category.** Until this arrives, `acuity_mix_pct` is
   an area-proxy: resus→Acuity 1, trolleys→2, majors ambulant→3, minors→4, and
   Acuity 5 is set to zero rather than invented.
2. **CT / X-ray split by area, and distinct visits with at least one scan.**
   Turns the imaging figures from a workload rate into a true per-patient
   probability and settles whether SDEC sits in the denominator. The NHSE
   Diagnostic Imaging Dataset publishes provider-level CT and plain-radiography
   counts by referral source, which can corroborate the ED total, but it cannot
   supply the per-area or per-visit split — only CUH can.
3. **Trust discharges by hour of day.** The day-of-week half is already here.
   Not published nationally at trust level; CUH only.

None of the three is available from any national publication, so all three have
to come from CUH. By contrast the handover gap above did NOT need CUH, and it is
worth checking a national source first before adding to a trust's data burden.

### Footprint question — answered

CUH confirmed (13 Aug 2026) that **paediatrics are included in the CHEQS
dataset**, as its own area rather than as a separate return. That matches how
the build already reads the extracts: `Performance Paeds.xlsx` is one of the
five front-door areas, `acuity_mix_pct` is computed over the four ADULT areas
only, and paediatric arrivals are routed separately by `paediatric_share`
(13.35%). No change needed.

It does **not** settle whether SDEC activity sits inside the investigations
extract, which is the open question on the imaging denominator (see above).

## Public cross-checks (three national files, none of them model inputs)

| Source | What it settled |
|---|---|
| **Diagnostic Imaging Dataset**, Table 1 modality × provider | CUH's ED imaging is ~⅓ of ALL trust imaging on both modalities (CT 32.3%, plain radiography 33.2%) — internally consistent, so `investigation_rates` is the right order of magnitude. It does **not** resolve the SDEC denominator: both readings land near a third. Also an adjacent-year comparison (DID is FY 2025/26, CHEQS is May–Aug 2026), so a magnitude check, not a reconciliation |
| **ECDS Activity**, Frailty tabs | **Dead end.** RGT records *no* Clinical Frailty Scale score at all — "No CFS Score Recorded" is 100% on both tabs (3,230 T1&2 and 4,160 all-types eligible attendances). The model's frailty area cannot be calibrated from ECDS and stays a template assumption. This is a CUH data-quality gap, not a modelling choice, and no other national file will fix it |
| **UEC SitRep beds**, Apr–Jun 2026 | Adds two things KH03 does not carry: **11.76 escalation beds** on top of 1,086.67 core, and the **length-of-stay mix** — 60% of occupied beds held by 7+ day stayers, 38% by 14+, 27% by 21+. Occupancy 0.90 corroborates the KH03 89.26% the model uses |

The length-of-stay mix is the significant one. The SD model has a single
`ward_discharge_capacity_per_hour` (template default 6.4) and no long-stay
compartment, so it cannot represent a ward where 60% of beds are held by
patients who will not leave this week. That is the real brake on bed turnover
at CUH, and it is invisible to the model today — the same shape of gap as the
day-of-week one, and it wants the same fix in the SD bed model.

Beds and occupancy deliberately stay on KH03 by agreement (one consistent
national definition); the SitRep figures corroborate but do not override them.

## The ops return (20 Aug 2026) — the biggest single change to the build

CUH's operational team returned the capacity template, plus an SDEC capacity
analysis. Committed as `data/cuh/CUH_ED_Operational_Inputs.xlsx` and
`data/cuh/SDEC_Capacity_and_ED_Streaming.pptx`. This closed the three red rows
that had been bounding everything else.

**Areas — three the model was running are not real.** EEMAC is a trial only
(piloted 08:00–00:00, 22 spaces, needs a staffing uplift), CUH runs **no CDU**,
and there is **no dedicated mental-health area** (one assessment room exists,
but no area). Six areas are live: RAT, UTC, fit-to-sit, paeds, SDEC, frailty.

**Hours — the template was wrong on three of them.** Fit-to-sit, paeds and SDEC
all run **24/7**, against template assumptions of 08–22, 08–22 and 08–20. UTC
runs two streams: minor injuries 08:00–00:30 and GP stream 08:00–22:30.

**Capacity — real counts at last:**

| Resource | Template | CUH real |
|---|---|---|
| Majors cubicles / trolleys | 24 | **34** (excl. resus and ambulance bay) |
| Resus bays | 5 | **6** |
| UTC rooms | 8 | **15** (not all staffed simultaneously) |
| Paediatric cubicles | 10 | **12** |
| Fit-to-sit chairs | 12 | **8** |
| CT scanners | 2 | **3** (shared with all inpatients, not ED-exclusive) |
| X-ray rooms | 3 | **3** |
| Handover bays | 5 | **3** |
| CDU beds | 8 | **0** |
| EEMAC spaces | 10 | **0** |
| Community / virtual ward | 60/day | **1/day** |

That community figure is not a typo. CUH's note: the number is virtual ward
only, and the virtual ward is mostly step-down after discharge rather than
admission avoidance from ED — so ED-facing community capacity is effectively
nil.

### What it did to the simulation

| | 4-hour | 12-hour | LWBS |
|---|---|---|---|
| Before (template areas/capacity) | 51.0% | 18.7% | 10.2% |
| After (real CUH ops data) | **61.9%** | 19.1% | **1.2%** |
| Published / internal target | 52.93% / **60.88%** | 3.7% (DTA) | — |

The 4-hour result is the striking one. Configured with CUH's own areas, hours
and capacity, the model lands at **61.9% against CUH's own internal 4-hour
basis of 60.88%** — a point apart. It sits ~9 points above the *published* Type
1 figure (52.93%), which is the same ~7-point counting gap already logged
between the two bases. The model is now reproducing the basis it is actually
configured to represent.

LWBS collapsing from 10.2% to 1.2% is real capacity relieving a queue that was
an artefact of under-stating the department by ten cubicles and seven UTC rooms.

**12-hour did not move** (18.7% → 19.1%) and remains far above the 3.7% DTA
target. That is the expected result and it localises the problem: 12-hour waits
are driven by bed availability and exit block, not by ED floor space, and the
engine still has no day-of-week dimension and no long-stay bed compartment —
the two gaps already logged above.

### SDEC: the model independently reproduced CUH's own finding

`sdec_chair` is set to **60** (EAU3 30 + SAU 30). EAU4 is excluded at 93–96%
occupied continuously, and Clinic 5 is excluded because only **0.5%** of its
attendances arrive from ED (40 of 7,896 over six months). Full per-unit detail
is in the workbook's `SDEC_Detail` tab.

Two checks worth recording. Sixty chairs at the observed ~4.4h median SDEC stay
implies roughly 327/day of theoretical throughput against 143.8 observed
attendances/day — about 44% utilisation, sitting squarely inside the 35–69% the
deck measures. And rerunning with `sdec_chair` back at 12 moved the 4-hour
figure by **0.0 points**: SDEC chairs are not the binding constraint in the
model either. That is the deck's own conclusion — "there is some capacity but
it's not consistent, and operational issues stop effective streaming" — arrived
at independently.

### RAT made ambulance-only — a 20-hour queue artefact removed

The ops return's one-line definition — *"at CUH this [RAT] is for assessment of
patients arriving by ambulance only"* — turned out to matter more than it
looked. The template routed **every** Acuity 1–3 patient through RAT. At the
template's acuity mix that was borderline; at Cambridge's real mix (A2 18.9% +
A3 42.2%) it pushed ~63% of adults (~250/day) into a step staffed for ~127/day.
The queue grew for four simulated days without clearing, priority let sicker
patients overtake, and the starving low-acuity tail produced a **20-hour mean
RAT wait on the control tower** — while polluting the 12-hour figure upward.

The fix routes ambulance patients to RAT by **attribute** (the same mechanism
that routes children to paeds — paediatric stays first, so an ambulance-arriving
child still goes to the paeds area) and sends walk-ins directly to the same
downstream mix, composed through RAT's old onward splits — no new numbers
invented. RAT covers all five acuities because ambulance A4/A5 are assessed
there too.

After the fix, on the full Cambridge build: RAT wait mean **6 min** (median 0,
p95 29, max 167) — which is what CUH's own CHEQS medians say (arrival to initial
assessment 0.5–2.3 min in the ambulance-fed areas). The 12-hour figure fell from
19.1% to **8.0%** against the observed from-arrival ~10% — the old figure was
mostly the artefact. 4-hour moved 61.9% → 65.6% (internal basis 60.9%); the
residual is service-time calibration, which is what auto-calibration is for.

The control-tower map was also made honest by the same investigation: per-area
counts now include patients **waiting** in the area (in-service-only counts had
hidden every queue and left the map near-constant), and each area carries a
24-hour wait series so the wait caption follows the time slider instead of
repeating one whole-week mean at every hour.

### The picker and the seed CLI must produce the same department

A 7-hour ED-cubicle wait on the control tower turned out not to be a modelling
error at all: **"Use this trust → Cambridge" was not loading the CUH set-up.**
`/api/trust/select` applied only the published aggregate distributions and
reimplemented the rest of `seed()`, so it left the department on template
capacity with `enabled = [rat, sdec, paeds, mh]`. Two consequences did the
damage: `fit_to_sit` was OFF, so every ambulatory patient fell back into the
cubicles, and `community_capacity` stayed at 60/day instead of CUH's 1.

The banner said so all along — *"Still assumptions: physical capacity"* — while
the map showed an ED minors node and an MH liaison node that Cambridge does not
have. Selecting the trust now delegates to `seed()` whenever a committed set-up
workbook exists, so the drop-down and `python -m uec_hybrid.ingest.seed RGT`
give byte-identical departments.

| ED cubicles, after picking Cambridge | Before | After |
|---|---|---|
| Mean wait | 454 min | **26 min** |
| At 21:00 | 670 min | **28 min** |
| `assumed` list | includes physical capacity | capacity is real |

### What the search recommends, and why it is not always a nurse

On the broken configuration the only move clearing the confidence gate was
"add a triage nurse", which made the search look one-note. On the corrected
Cambridge department the ranking is quite different:

| Move | Δ 4-hour | 95% lower bound |
|---|---|---|
| **20 more community / virtual-ward discharge places** | **+5.1** | **+2.0** |
| Add 1 triage nurse 10:00–14:00 | +2.5 | −0.3 |
| Add 1 EM junior doctor 08:00–15:00 | **−1.9** | −3.5 |

That top result is the model reading CUH's own data back: community capacity is
**1/day**, so discharge places are the binding lever. And note the SHO scoring
*worse* than baseline while `ed_doctor` sits at 94% utilisation — with the wards
full, processing patients through the front door faster only moves them into the
"wait for inpatient bed" queue. The pinch-point copy used to assert "add
capacity here first" on the saturated resource; it now states where the queue
forms and points at the ranked search, because the saturated resource is not
always where the fix is.

Also fixed: capacity moves for resources the department does not have are no
longer offered. "Add 2 minor-injury spaces" was being simulated against a
Cambridge build with no minors node, then reported as "+0.0, within the noise" —
which reads as a considered rejection rather than an impossible move.

### Whole-flow sweep (20 Aug 2026) — two more found, and the build validated

Fixing one visible number twice in a row is not a method, so every node was
swept for implausible waits, growing queues and saturated resources, and every
model output compared against a CUH figure. Two more real defects surfaced.

**Ambulatory capacity was half the story.** `fit_to_sit_chair` was set to 8 from
CUH's "fit-to-sit chairs", while their "ambulatory majors consultation rooms: 9"
had been filed as having no model equivalent. It has one — `ed_ambulatory` IS
the ambulatory majors area, and the model holds that space from entering the
area until the clinical decision (through imaging). With 8, the mean wait to
*enter* ambulatory was **642 min — longer than CUH's entire 254-min median stay
for majors ambulant**, against a real 163/day. Both numbers are CUH's own, so
the pool is 8 + 9 = **17**; wait falls to 46 min. Flagged for CUH to confirm the
two are one pool.

**"Seen within 15 min" had no observed target**, while the answer sat unused in
the extracts: the Performance files carry `Arr-Init Ass <=15` / `>15` columns
giving **41.8%** across the front door (resus 80.3%, trolleys 77.6%, paeds
44.8%, ambulant 41.8%, minors 20.9%). Now recorded. The steep gradient — fast
for resus, slow for minors — is something the model does *not* reproduce,
because its streaming step treats the front door as a single queue.

With real capacity the model then ran *optimistic on every metric at once*,
which is the signature of uncalibrated service times rather than a new bug.
Running the documented auto-calibration (service scale x1.05) lands the build
here:

| Tile | Model | Observed |
|---|---|---|
| 4-hour | 59% | 52.9% |
| Seen within 15 min | 46% | 41.8% |
| Over 12 hours | 3% | 3.7% |
| Ambulance handover within 45 min | 81% | 84.2% |

Every one within about six points, and 12-hour and handover close to exact.
That is the first time the build has agreed with CUH across the board.

Checks that came back clean: admitted rate 14.9% against an observed 14.1%;
ambulance share 19.9% against 19.1%; paediatric share 13.5% against 13.4%; no
queue growing without clearing; no area from a component CUH does not run. One
known discrepancy is benign — throughput reads ~374/day against 400.5
configured because patients still in the department when the run ends are not
counted as completed.

### Left deliberately unset

CUH answered **0** for ED minor-injury spaces: minor injuries are physically
seen in the UTC. That cell is left BLANK rather than set to 0, on purpose. The
model streams 35% of Acuity 4 and 30% of Acuity 5 to `ed_minor_injury`, and the
builder floors a 0 to 1, so entering the real answer would build a fake
single-space queue instead of modelling reality (tested: LWBS jumps to 26%).
What it needs is those streaming splits re-pointed at the UTC — a routing
change, not a capacity number, and one worth making deliberately.

An explicit zero is now kept rather than dropped (`Department.from_dict` and
`_read_capacity` both used to discard it), because "0" and "blank" are
different claims: CUH runs no CDU beds, which is not the same as CUH not having
told us.

### Still outstanding from the ops side

* **Frailty / FAU beds** — marked `***`, needs the frailty team.
* **Frailty opening hours** — CUH to cross-check.
* **Clinic 23, Clinic 24 and PSU SDEC capacity** — marked `***`. These are in
  operation with real hours, so excluding them understates SDEC.
* **EAU3 capacity is stated three ways** — 26 core / 30 extended on one slide,
  "36-chair capacity confirmed" on another, and 30 in the ops template. The
  build uses 30; CUH to reconcile.

## Cambridge-first product (from the ops return)

The front end is now CUH's: **CUH ED Control Tower** (text lockup in NHS blue —
no trademark artwork is used or recreated), subtitle naming Cambridge University
Hospitals / Addenbrooke's, and a fresh install auto-seeds the RGT build through
the product's own seed path, so the product opens on Cambridge rather than the
generic template. The trust picker and workbook import remain available on the
**Design my ED** screen (renamed from "Set up my ED").

The live patient flow shows only components CUH actually runs; Design my ED
keeps the full nine-component catalogue as toggles, and enabling one re-runs the
tower with it in the flow. Optional components carry data-backed defaults where
data exists:

* **EEMAC** — off, but its capacity is recorded as the REAL pilot (22 spaces,
  08:00–00:00), so enabling it later starts from the pilot, not a guess.
* **CDU** — off, with deliberately NO count (the `cdu: no` toggle carries
  nonexistence; if ever enabled, the template default applies and is labelled an
  assumption — no CUH figure exists).
* **MH area** — off; the 1 real assessment room is recorded for if it opens.

**Minors are re-routed.** CUH's explicit `minor_injury_space = 0` now REMOVES
the ED minors node (new `ZERO_CAPACITY_NODES` seam in `department/config.py` /
`builder.py` — an explicit 0 declares a core node out of existence, distinct
from a blank which keeps the template estimate). Acuity 4/5 minors stream to the
UTC in its open hours; overnight, with UTC minors shut, they divert to the 24/7
fit-to-sit area — a **LABELLED ASSUMPTION**, since no data says where CUH's
overnight minors actually go. That question joins the CUH ask list:

* **Where are minor injuries seen between 00:30 and 08:00?** (UTC minors hours
  are 08:00–00:30; arrivals data shows minors do arrive overnight.)

Effect on the simulated Cambridge build: 4-hour 59.1% (vs 61.9% before the
re-route; CUH internal basis 60.88%), LWBS 0.4%, 12-hour unchanged — and no
fake single-space minors queue.

## Per-area validation (20 Aug 2026) — three real bugs, and what is still wrong

Checking the model against CUH's **per-area** behaviour, rather than against
headline KPIs, found three genuine defects. The headline KPIs had been agreeing
all along *through compensating errors*.

**1. The calibrated acuity mix never reached the department.**
`skew_stream_mixes` multiplied each stream's acuity split by a per-class ratio
but never renormalised, leaving Cambridge's four streams summing to 145 / 71 /
136 / 84 instead of 100. The engine renormalises on the way in, so the
department actually ran at **Acuity 1 1.3% / Acuity 4 51%** against a calibrated
2.5% / 36% — and resus saw half the patients CUH sees. Fixed with iterative
proportional fitting (rows sum to 100, share-weighted columns hit the target),
plus a re-fit after the ambulance share moves, since that changes the weights the
fit was solved against. **This bug affected every trust, not just Cambridge.**

**2. Acuity was routed by template crossover, not to CUH's areas.**
`acuity_mix_pct` is *derived* from CUH's per-area counts (resus→A1, trolleys→A2,
ambulant→A3, minors→A4), so routing each band back to its own area is correct by
construction. The template instead sent 30% of Acuity 2 to resus and split
Acuity 3 across two areas, giving resus 1.77x and majors ambulant 0.50x of CUH's
real volumes. Now a trust-level calibration (`area_routing`), not a template edit.

**3. Admitted patients vacated their trolley before waiting for a bed.**
The ED space was released at `disposition`, so a patient waiting hours for an
inpatient bed occupied *nothing* — removing the single most important mechanism
in ED crowding, and the one CUH's 12-hour DTA problem consists of. Bedded spaces
(cubicle, resus bay, paeds cubicle) are now held until the patient physically
leaves; ambulant space still frees at the decision, because `bedded_care=False`
patients wait in a waiting area, not on a trolley.

### Where it now stands (6 replications)

| | Model | CUH observed |
|---|---|---|
| 4-hour | 54.4% ±4.0 | 52.93% |
| 12-hour (DTA) | 6.9% ±1.2 | 3.7% |
| Acuity mix | 2.67 / 18.8 / 41.5 / 37.0 | 2.51 / 18.88 / 42.21 / 36.41 |
| Per-area volumes | 0.73–0.89x | — |

Volumes and case-mix are now right. The residual ~0.85x on volumes is the
documented counting-basis gap (model runs at the published 400.5/day, CUH's
internal area counts total 446/day).

### Second pass (20 Aug 2026): two of the three closed

**Per-area bed waits — closed.** One pooled `await_inpatient_bed` could not
represent a trust whose post-DTA wait runs 460 min on a majors trolley and 66 in
minors. Because acuity maps 1:1 to area here, the per-area waits are now carried
as `service_by_class` (the engine already supported it). Result against CUH's
observed `dta_to_departure`:

| Band / area | Model | CUH | |
|---|---|---|---|
| Acuity 1 / resus | 130 | 131 | 0.99x |
| Acuity 2 / majors trolleys | 457 | 460 | 0.99x |
| Acuity 3 / majors ambulant | 117 | 138 | 0.85x |
| Acuity 4 / minors | 73 | 66 | 1.12x |

**Ambulance handover — closed, and it needed a structural fix, not a number.**
Two things were wrong. The bay was released at `streaming`, so a crowded ED
never backed up into the ambulance queue; and CUH's own note ("RAT is for
assessment of patients arriving by ambulance only") means ambulance patients are
assessed *on arrival*, not queued through the walk-in streaming desk. Ambulance
arrivals now route handover -> RAT directly, and the crew holds the bay until
RAT accepts the patient. Handover is now **88.1% within 45 min against CUH's
84.19%**, and it responds to crowding through the RAT queue as it should.

Per-area treatment times were then calibrated against each area's observed TID
median. Length of stay improved from (1.59 / 0.50 / 1.11 / 0.55 / 1.79) to
**(1.01 / 0.56 / 1.22 / 0.61 / 1.29)** for resus / trolleys / ambulant / minors
/ paeds.

**Seen within 15 minutes — NOT closed, and it should not be quoted.** The model
reads ~77% against CUH's 41.8%, and the gap is a definition mismatch rather than
a tuning error. The model's `initial_assessment` is the front-door event
(streaming for walk-ins, RAT for ambulance arrivals). CUH's recorded
"Arr-Init Ass" is that same event for the ambulance-fed areas — trolleys 0.5 min,
resus 2.3, which the model now reproduces — but for minors it is a *clinician*
assessment 37 min into the visit, inside the minors area, not triage. The two
series measure different events for low-acuity patients, so forcing them to
agree would mean modelling the wrong thing. Slowing the front door to hit the
headline number was tested and rejected: it reaches 42% overall but drives
Acuity 4 to 0% against CUH's 20.9% and collapses the 4-hour figure.

### Still wrong, and stated plainly

* **Majors trolleys length of stay: 0.56x** (408 vs 725 min). The bed wait is
  now right, so the shortfall is upstream - CUH's trolley patients spend longer
  in the department before the decision than the model does. Lengthening
  treatment further destabilises the queue before it closes the gap.
* **Minors length of stay: 0.61x** (100 vs 164 min) and **paeds 1.29x**.
* **12-hour waits: 6.9% against 3.7% observed** - still about double.
* **Seen within 15 minutes** - a definition mismatch, see above. Do not quote.

None of these three needs anything further from CUH — the data to close them is
already in `data/cuh/`.

## Still open, and not from CHEQS

1. **Physical capacity counts** — cubicles, trolleys, resus bays, SDEC chairs,
   CDU and FAU beds. Every one is still a size-scaled template guess. In a
   queueing model these set the queues, so they bound how much anything else
   is worth. Capacity tab of `docs/cuh_minimum_data.xlsx`, with the ops team.
2. **Which areas CUH actually runs, and their opening hours** — the seed
   workbook's Areas tab is entirely blank, so the build runs on the template's
   area list. Whether CUH has a UTC, a fit-to-sit area, an EEMAC or a frailty
   unit, and what hours SDEC and paeds keep, changes the routing before any
   number matters. Same workbook.
3. **Day-of-week variation** — batch 2 proves it is large (Sunday discharges
   are 29% of Monday's) and the engine cannot represent it. This is an engine
   change, not a data gap.
4. **Service times per stage** — never published and not derivable from the
   extracts; they stay auto-calibrated against the observed 4-hour figure.

Beds and occupancy are deliberately NOT coming from CHEQS: the published KH03
return supplies both on a consistent national definition (1,068 G&A beds,
89.26% occupancy, Q4 2025-26), which is what the build already uses. The rota
stays out of scope by agreement.
