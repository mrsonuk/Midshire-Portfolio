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

## Still open after batch 2

Batch 2 closed the imaging gap and gave the build its first real validation
spread, but it did **not** touch the things that actually block a defensible
Cambridge run. Still outstanding, in priority order:

1. **Physical capacity counts** — cubicles, trolleys, resus bays, SDEC chairs,
   CDU and FAU beds. Every one is still a size-scaled template guess. In a
   queueing model these set the queues, so they bound how much anything else
   is worth. Capacity tab of `docs/cuh_minimum_data.xlsx`.
2. **Which areas CUH actually runs, and their opening hours** — the seed
   workbook's Areas tab is entirely blank, so the build runs on the template's
   area list. Whether CUH has a UTC, a fit-to-sit area, an EEMAC or a frailty
   unit, and what hours SDEC and paeds keep, changes the routing before any
   number matters.
3. **Ambulance handover times** — no source yet; the winter SitRep can supply
   it when it resumes.
4. **Day-of-week variation** — batch 2 proves it is large (Sunday discharges
   are 29% of Monday's) and the engine cannot represent it. This is an engine
   change, not a data gap.
5. **Service times per stage** — never published and not derivable from the
   extracts; they stay auto-calibrated against the observed 4-hour figure.

The rota stays out of scope by agreement. Internal mental-health activity is
now covered as reference data (`MH Disposals.xlsx`) but has no parameter to
land in, and imaging *turnaround* (as opposed to imaging *volume*, which
batch 2 supplied) is still uncovered.
