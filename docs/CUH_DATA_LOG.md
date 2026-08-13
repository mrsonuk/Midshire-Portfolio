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
