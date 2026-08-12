# Model ED Optimiser, technical reference

This document explains the whole system to a technical reader who has never
seen it: the architecture, the mathematics of the three modelling layers
(discrete event simulation, system dynamics, Monte Carlo), the calibration and
recommendation machinery, the backend API, the front end, and the invariants
the test suite enforces. It describes the control tower edition of the
codebase, the branch trimmed to two screens. File paths are relative to the
repository root. Everything here was written from the code itself, so an
answer sourced from this document can be checked against the named file.

## 1. What the system is

The product is a digital twin of an NHS emergency department. A hybrid
simulation sits underneath: a discrete event simulation (DES) moves individual
patients through a data-defined graph of care stages while they contend for
limited resources, and a system dynamics (SD) model integrates the whole
hospital around the ED (inpatient beds, mental health beds, community and
virtual ward capacity) as continuous stocks. The two are co-simulated on one
clock so that a full hospital genuinely slows ED admissions (exit block) and
community capacity genuinely relieves it. Monte Carlo replication wraps the
coupled model to quantify variability. Everything a screen shows is computed
from this engine; the chatbot and what-if features format engine output and
never invent numbers.

The technology is deliberately plain. The backend is one Flask app in Python
(`uec_hybrid/app/server.py`) with SimPy for the DES, NumPy and pandas for
statistics, SQLAlchemy over SQLite for persistence. The front end is one
server-rendered page (`uec_hybrid/app/templates/product.html`) driven by
vanilla JavaScript (`uec_hybrid/app/static/product.js`), with the flow map
drawn as hand-built SVG and HTML, no charting library. The app runs fully
offline, which matters on locked-down NHS networks.

## 2. Architecture and data flow

The layers, from the screen downwards:

    product.html + product.js + provenance.js      the two-tab page
        |  JSON over HTTP
    app/server.py                                  routes, caching, composition
        |
    department/config.py + department/builder.py   Department -> runnable raw dict
    demand/ecds_seam.py (apply_patch)               calibration overlay
    model_params.py (apply_params)                  service-time overlay
        |
    des/pathway.py (Pathway.from_dict)              validated pathway object
    coupling/cosim.py (run_cosim)                   the coupled engine
        des/engine.py        the DES
        sd/model.py          the SD
        coupling/system_state.py                    the shared seam
        |
    analysis/metrics.py, analysis/montecarlo.py     KPIs, replication
    viz/flow_model.py                               control tower payload
    platform/store.py                               SQLite persistence + run cache

One saved department drives everything. `server._dept()` loads it from the
store (or creates the default), and `server._dept_raw()` turns it into the
runnable dictionary by composing three overlays in a fixed order: first
`department.builder.build(dept)` produces the sized, area-correct pathway,
then `demand.ecds_seam.apply_patch` overlays any stored calibration, then
`model_params.apply_params` overlays any stored service-time override. The
order is load-bearing. The calibration patch is stored separately from the
department precisely so it can be re-applied to a freshly built pathway after
every set-up change, and the service-time override comes last so a pinned
stage mean survives calibration.

Results are cached by configuration hash. `platform/store.py` hashes the JSON
of (kind, engine version, exact input config) with SHA-256 and stores the
payload in a `runs` table. Because the department raw is part of the key, any
change to set-up, calibration or parameters silently invalidates every cached
result, and two different trusts can never collide. The engine version
constant (`store.ENGINE_VERSION`) must be bumped whenever simulation behaviour
changes, which flushes the cache by construction.

## 3. The pathway data model

A pathway is pure data, a directed graph in
`uec_hybrid/pathways/model_ed.json` (33 nodes for the NHS Model Emergency
Department). `des/pathway.py` parses it into a `Pathway` object and
`validate_schema` checks structure statically: exactly one source, at least
one sink, every route target exists, every referenced resource is declared,
bands come from the fixed list `front_door, core_0_4h, emergency_4_12h,
admission_12h_plus`.

A node carries, among others: `id`, `type` (source, process, sink), `label`,
`band`, a transient resource need (`resource` or `resources`), span holds
(`acquire` and `release`), a service specification (`service` or
`service_by_class` keyed by acuity), routing (`routes`, `routes_by_class`,
`routes_by_attribute`, `routes_by_signal`), reneging (`renege`), opening hours
(`open_hours` plus `closed_fallback`), a hard band cap (`max_band_minutes`,
for example 720 for a 12 hour ambulatory unit), `stops_clock` to freeze the
performance clock at transfer, and `service_signal` naming an SD signal that
scales this node's service time live.

The file also carries the `resources` catalogue (integer capacities, or a
24-element list for staffing rosters), the `arrivals` block (hourly profile,
acuity mix, attribute probabilities, and four arrival streams), an `sd` block
(whole-hospital parameters) and a `uec` metadata block that names the special
nodes indirection-style (initial assessment node, ambulance handover stages,
the ambulance, paediatric, mental health and frailty attribute names, the
EEMAC node, and the nurse-to-cubicle ratio).

Total simulated time defaults to one week (10080 minutes) with a warmup
period (1440 minutes in the shipped pathway) whose patients are excluded from
all metrics. The 4 hour target is `target_minutes`, 240 by default.

## 4. The discrete event simulation

`des/engine.py` implements the DES on SimPy. The design decisions that
matter:

Arrivals are a nonhomogeneous Poisson process. The arrival generator reads
the hourly profile, takes the rate for the current simulated hour (arrivals
per hour), and sleeps an exponential inter-arrival time with mean 60/rate
minutes. Sampling the exponential fresh each iteration approximates the
piecewise-constant-rate NHPP well at these rates.

Each arriving patient draws an acuity from the acuity mix (a categorical
distribution over labels such as "Acuity 3"), and boolean attributes
(ambulance, paediatric, mental health, frailty) as independent Bernoulli
draws whose probabilities may be flat or per-acuity. Before acuity is drawn,
an arrival stream is picked for the current hour: the four streams
(ambulance, walk in, GP referral, NHS 111) partition each hour's demand by
`share_by_hour` weights, and a stream can carry its own acuity mix and pinned
attribute probabilities. Because streams are shares of the one hourly
profile, scaling total demand remains a single knob and the streams follow.

Every resource is a SimPy `PriorityResource`. Priority is the acuity's
trailing digit (lower number is served first), overridable per node, so a
resuscitation patient overtakes a minors patient in any queue. This is the
clinical prioritisation the Model ED asks for, and the test suite checks the
resulting inversion of length of stay by acuity.

Staffing rosters get a shift manager per rostered resource. The resource is
built at the roster's peak, and a background process holds (peak minus
roster[hour]) units off shift using dummy requests at priority minus one
billion, re-evaluated every 15 simulated minutes so a staffing cut takes
effect as units free rather than only on the hour. This makes time-varying
capacity work on top of a fixed-capacity resource primitive.

Two holding disciplines coexist. A node may `acquire` a space (a cubicle, a
bed) that is then held across every subsequent node until some later node
`release`s it, while clinicians are seized transiently per stage. So a
boarding patient blocks a cubicle while also waiting for a ward bed, which is
exactly the physical mechanism of corridor care. The holds log records every
occupancy interval for utilisation math.

Reneging models patients who leave without being seen. A node with a
`renege` block samples a patience from its distribution; if the patient's
wait for that node's resources would exceed the patience, they stop waiting,
release anything already granted, and jump to the renege target (a "left
without being seen" sink). Waiting is implemented as a race between the
resource request and a timeout for the remaining patience.

Opening hours gate part-time areas. Routing resolves the chosen target
through `_resolve_open`: if the target node has `open_hours` [open, close)
and the current simulated hour falls outside (with wrap past midnight
supported), the patient diverts to the node's `closed_fallback`. The builder
sets these fields from the department's configured hours.

Routing itself has a strict precedence: signal-based diversion first (each
`routes_by_signal` entry fires with probability equal to the named SD signal
value times a scale, which is how community pull lifts diversions when
community capacity has headroom), then attribute routes (first matching
attribute wins), then per-acuity class routes, then the default route list.
Probabilities are renormalised at draw time.

Service is sampled from the node's distribution (per-acuity spec wins when
present), then optionally multiplied by a live SD signal named in
`service_signal`. This is the exit-block seam: the "await inpatient bed" node
names `bed_wait_multiplier`, so a full hospital stretches boarding time. A
`max_band_minutes` cap truncates service so the patient leaves the unit by
the cap, measured from node entry.

The engine emits three tidy frames: events (one row per patient per stage,
with queue entry, service start and end, wait, service, resources), patients
(one row per journey, with arrival, exit, length of stay, disposition,
priority, stream, attributes, bands seen), and holds (one row per resource
occupancy interval). Warmup filtering keeps only patients who arrived after
the warmup and their events and holds. Sinks record their disposition into
the SD flow accumulators by keyword: an "admit" disposition increments
admissions (mental health admissions if the label also mentions MH),
"communit" increments diversions to community, anything else counts as a
discharge. An ED census counter increments when a patient first enters a
banded node and decrements at their sink; the SD reads it for crowding.

## 5. Service time distributions

`des/distributions.py` samples a spec that is either a bare number (constant
minutes) or a dict naming one of: constant, exponential, normal (clamped at
zero), uniform, triangular, lognormal. The lognormal is parameterised by the
real-world mean m and standard deviation s, converted internally to the
underlying normal parameters:

    phi   = sqrt(s^2 + m^2)
    mu    = ln(m^2 / phi)
    sigma = sqrt(ln(phi^2 / m^2))

so an editor can type "mean 70, stdev 25" and get exactly that mean. All
draws are non-negative. Most clinical stages in the shipped pathway use
lognormal, the standard choice for service durations with a long right tail.

## 6. The system dynamics layer

`sd/model.py`, `sd/stocks.py` and `sd/feedback.py` implement the
whole-hospital context as stocks and flows integrated with a fixed-step Euler
scheme (8 substeps per exchange interval).

A `Stock` is a level clamped to [0, capacity], integrated as
level += net_rate * dt. Two bedded stocks (acute inpatient and mental health
beds) are homeostatic: modelling only ED admissions would drain them, since a
hospital sits about 90% full from all sources, so each carries a constant
background inflow and a proportional discharge

    discharge_rate = discharge_capacity * (occupancy / baseline_occupancy) * pull_boost

which equals the configured capacity exactly at baseline occupancy, slows
below it and accelerates above it. Equilibrium therefore sits near the
baseline (which is why the trust's real published occupancy is a model
input), an ED admission surge pushes occupancy up, and extra beds or faster
discharge push it down. The pull boost is 1 plus 0.25 times the community
pull signal, so community headroom lets wards discharge modestly faster.
The community stock fills from ED diversions and clears at a configured
hourly rate.

Feedback signals are smooth, bounded, monotone transfer functions, never
steps, which is what keeps the coupled loop from oscillating
(`sd/feedback.py`):

    logistic(x, knee, sharpness) = 1 / (1 + exp(-sharpness * (x - knee)))

    bed_wait_multiplier(occ) = 1 + 8 * logistic(occ, 0.90, 12)

so boarding time is roughly unchanged with headroom and up to nine times
longer as occupancy approaches 100%, with the knee at the NHS 92% guidance
region. The mental health variant uses max extra 10. Community pull is
0.45 * available_fraction. Ambulance handover delay is 60 * crowding minutes.
The crowding index is a linear ramp of ED census between a comfort census and
a crush census (defaults 45 and 110), clamped to [0, 1].

Every hazard signal then passes through first-order exponential smoothing
with a 90 minute time constant,

    new = previous + (1 - exp(-dt / tau)) * (target - previous)

a classic SD information delay that limits how fast a signal can move per
tick. Turning feedback off pins the multipliers at 1 and pull at 0, giving
the clean counterfactual the tests use to prove exit block emerges from the
coupling rather than being baked in.

## 7. The coupling

`coupling/cosim.py` binds the two solvers with a zero-order hold exchange on
one SimPy clock, every dt = 60 simulated minutes:

    1. DES to SD: drain the flow accumulators (admissions, MH admissions,
       community diversions, discharges) collected since the last tick.
    2. Advance the SD by dt with substeps, feeding it those flows as rates
       and the current ED census.
    3. SD to DES: publish the new signal values into the shared SystemState.

Between ticks the DES runs freely and only reads the held signals; the SD
only sees drained totals. The two solvers never mutate each other
mid-interval, and everything runs in one cooperative single-threaded SimPy
environment, so the discipline, not locking, guarantees correctness
(`coupling/system_state.py` documents the two halves: held signals
overwritten once per tick, monotone accumulators drained once per tick).
Signals default to neutral values so a pathway also runs as a pure DES.
The seam's channel map lives in `coupling/adapters.py`.

## 8. Monte Carlo

`analysis/montecarlo.py` runs the coupled model N times with consecutive
seeds (base_seed + i), in parallel through a process pool where available,
falling back to serial. Each replication returns the merged headline and
cohort metrics plus the bed-occupancy time series. The summary reports, per
metric, the mean, the sample standard deviation, and a 95% interval taken as
the 2.5th and 97.5th percentiles of the replication values (an empirical
band, deliberately distribution-free), plus min and max. The control tower's
"good week, typical, tough week" cards are the max, mean and min across
replications of each standard, which reads naturally for operational
audiences. Seeds are fixed and consecutive so any run is exactly
reproducible, and paired comparisons elsewhere reuse the same seed list.

## 9. Metrics, standards and the pinch point

`analysis/metrics.py` computes everything from the three frames.

The headline KPIs from the patients frame: the 4 hour standard is the share
of journeys with length of stay at or under `target_minutes` (dispositions
with `stops_clock` freeze the clock at transfer, so a boarding admission
counts at its decision-to-admit handoff where the pathway says so). Twelve
hour waits are the share over 720 minutes. Left without being seen is the
share of dispositions containing "without being seen". Admit rate matches
dispositions containing "Admit". Initial assessment within 15 minutes takes,
per patient, the first service start at the node named by
`uec.initial_assessment_node` minus arrival.

Cohort measures only compute where the pathway models the cohort. Ambulance
handover takes, for patients with the ambulance attribute, the first service
start among the declared handover stages minus arrival; reported as the share
within 45 minutes, the mean, and vehicle hours lost per day, defined as the
sum of (handover minus 15 minutes, clipped at zero) divided by 60 per
simulated day. Mental health gets the share over 24 hours and the one hour
liaison response (wait at the liaison node under 60 minutes). Children get
their own 4 hour share and senior review within 120 minutes. EEMAC conversion
is the share of patients who passed the EEMAC node and ended admitted, a
Model ED audit metric that should stay low.

Resource utilisation is total held time from the holds frame divided by
capacity times the horizon; a rostered capacity is averaged over the day
rather than taken at peak. Stage waits aggregate the events frame.

The bottleneck diagnosis ranks stages by lost patient hours, mean wait times
patient count divided by 60, then looks up the utilisation of the resources
that stage touches. At 80% or more utilisation the verdict is a binding
constraint (add capacity here first), at 60% busy and likely driving the
queue, otherwise the delay is attributed to downstream exit block and the
reader is pointed at bed occupancy. The control tower refines this
operationally: the pinch is recomputed over the working day only (08:00 to
22:00) so an overnight low-volume artefact cannot claim the flag, the peak
hours are those with at least 60% of the stage's maximum hourly lost wait,
and a per-hour pinch series lets the time slider retarget the flag as the day
replays.

The RAG scorecard is a data table (`SCORECARD_SPEC`) of target, direction and
amber band per standard, for example 4 hour target 78% with amber band 6,
handover 95%/10, LWBS 5%/3, bed occupancy 92%/3. Green means meeting target,
amber within the band, red beyond it, and stored overrides can change any
target without code.

The flow counts that feed the Sankey-style map walk each patient's ordered
stage labels as a chain from "Arrival" through their stages to their
disposition, counting each adjacent pair as an edge. The map therefore shows
what the simulated patients actually did, not what the pathway file declares.

## 10. From a Department to a runnable model

`department/config.py` defines the `Department` dataclass, the whole
configurable surface: name, attendances per day, enabled areas, rota,
inpatient beds, community capacity, per-area opening hours, baseline bed
occupancy, and a capacity dict of real physical counts keyed by resource.
The AREAS catalogue lists the nine toggleable Model ED elements (RAT,
co-located UTC, fit to sit, paediatric area, EEMAC, SDEC, CDU, frailty unit,
MH liaison), each naming the pathway nodes it owns, its resources, a safe
fallback node and a mode.

`department/builder.py` turns that into a raw pathway dict:

First, disabled areas are removed. Every route list that pointed at a
disabled node is rewritten: reroute-mode areas divert the probability to the
area's fallback node (same-day areas fall back to the inpatient bed wait,
which is exactly why having them improves flow), option-mode edges are
dropped, then targets are merged and probabilities renormalised to sum to
one. The nodes themselves are deleted afterwards, so no patient can ever be
routed into a void, and the conformance validator re-derives its legal
transition set from the built pathway.

Second, enabled part-time areas get `open_hours` and `closed_fallback`
stamped onto their entry node from the department's hours.

Third, resources: anything only used by removed nodes is dropped; physical
(non-staff) capacities scale linearly by size,

    scale = max(0.3, attendances_per_day / 320)

reflecting that the template describes a 320 a day department; then the
trust's own capacity counts replace the scaled figures exactly (a count for a
disabled area is inert because its resource is already gone).

Fourth, the workforce rota folds into 24-hour staffing lists per staff
resource, replacing the template staffing.

Fifth, the nurse-to-cubicle ratio: cubicles only open if nurses cover them,

    open_cubicles[h] = max(1, min(physical_cubicles[h], nurses[h] * ratio))

with the ratio (1 to 4 by default) read from the `uec` block. The pre-ratio
physical count and the nurse roster are stashed in `uec` so what-ifs can
recompute this cap exactly rather than trying to invert a min().

Sixth, demand: the template hourly profile is renormalised so it sums to the
department's attendances per day. Whole-hospital SD parameters get the
inpatient bed count, the community capacity, the trust's real baseline
occupancy where known, and the background flow rates scaled by size.

## 11. Workforce mathematics

`workforce/rota.py` expands shifts (role, start, end, count, with wrap past
midnight) into per-staff-area hourly headcounts, holding a floor of one so a
department never has literally nobody. Weekly cost is count times shift
length times the role's hourly rate times seven, with rates editable as
stored settings. The understaffed test is share-based: hour h is flagged
when demand's share of its daily total exceeds staffing's share by more than
0.012, which highlights shape mismatch (a rota flat across the day against
an afternoon-heavy demand curve) independent of absolute levels. The demand
curve is the canonical 24-hour arrival shape in `demand/profile.py` scaled
to the department's daily attendances.

## 12. Calibration

There are three inputs of increasing fidelity, all producing the same patch
shape that `demand/ecds_seam.apply_patch` overlays onto any freshly built
pathway.

A row-level ECDS-style extract (columns day, arrival_hour, acuity,
arrival_mode, age, mental_health, disposition) is reduced by `derive_patch`:
the hourly profile is arrivals per hour of day divided by the number of
distinct days, the acuity mix is the observed shares, the ambulance share is
the fraction of arrival modes containing "amb", the paediatric share is age
under 16, and admission rates per acuity come from dispositions containing
"admit" wherever a band has at least 20 records. Service times are explicitly
not derived, since between-event timestamps do not identify them.

Published aggregates (`ingest/published.py`) map the same quantities from
open NHS publications when no extract exists: hourly shares times attendances
per day give the absolute profile, and every block carries its own source
citation with the granularity stated, so a national shape scaled to trust
volume is labelled as exactly that. Null blocks are skipped and the model
keeps its flagged default.

`apply_patch` is careful about two couplings. A new acuity mix is pushed
through `demand.streams.skew_stream_mixes`, scaling every stream's own mix by
the ratio of new to old global shares so each stream keeps its case-mix
character. A calibrated ambulance share moves the ambulance stream's
share-by-hour via `scale_stream_share` (walk-in absorbing the slack) rather
than only setting the attribute, because streams pin the attribute and would
otherwise make it inert. Admission rates rewrite the admit-versus-discharge
split on the clinical decision node per acuity.

Auto-calibration (`assist/autocal.py`) closes the loop against reality. The
observed 4 hour figure is the target; the knob is a single global
service-time scale applied by `model_params.apply_params` (which multiplies
every stage's mean and spread, or pins specific stage means first). Because
stretching service times monotonically worsens the 4 hour share, the search
is a bracketing bisection on the scale within a plausible band of 0.6 to 1.8,
evaluating the modelled 4 hour as the mean over fixed seeds, stopping within
a tolerance of 0.75 percentage points or after six iterations, and clamping
honestly at the band's edge with a note that demand, staffing and bed inputs
should be checked when even the edge cannot reach the observed figure. Every
evaluation is returned in a history list, and the result persists as the same
data-driven override the workbook writes, so it is reversible.

Validation is separate from calibration by design. Published outcomes (the
observed 4 hour and 12 hour positions) are never model inputs; they are held
back and compared with the modelled output
(`ingest/trust_profile.validate_against_observed`, a ten point band), which
is the product's single strongest credibility check.

## 13. The what-if and scenario algebra

`analysis/scenarios.py` applies a declarative scenario to a pathway copy.
Resource changes accept "+n", "-n", "*f" or an absolute number, applied
element-wise to rosters; a dict form applies the change only inside a set of
24-hour-clock hours, roster-ifying a scalar capacity first. A nurses change
is special-cased through the exact builder formula, recomputing the cubicle
cap from the stashed physical cubicles and nurse roster, so "add 3 nurses at
1pm" opens precisely the cubicles those nurses cover and the answer can also
say when extra nurses open nothing because the physical spaces are the
binding term. A staff_scale multiplies every staffed group (sickness or
strike), routing the nursing effect through the same ratio. Arrival scaling
multiplies the hourly profile globally or inside a window. A divert removes
a fraction of chosen acuity classes or an attribute cohort: the acuity mix
(and every stream's mix, via the skew helper) is reduced, the ambulance
stream share is scaled where relevant, and the total profile is scaled down
by the diverted fraction, which is why the UTC divert lever models demand
removal rather than an internal transfer, a phrasing caveat the sales team
is briefed on. SD parameters pass through as overrides.

`compare_scenarios` Monte Carlos the baseline and each scenario with the
same seed base so differences carry confidence intervals. The tornado runs
one-at-a-time levers and sorts by absolute effect on the chosen metric.
The natural-language layer (`assist/nl.py`) parses plain English ("remove a
doctor overnight", "10% more attendances in the evening") into exactly these
scenario dicts, with a vocabulary map from phrases to resource names and
time-window words to hour sets, and `assist/run_what_if` executes scenario
versus baseline with paired seeds and formats the before-and-after table.

## 14. The recommendation engine

`optimise/recommend.py` answers "what should we change". Candidates are
generated from the department's own weak points: one extra person of the
area's cheapest sensible role covering each understaffed window (widened to
at least four hours), physical moves (two staffed majors cubicles including
the nurse to cover them, so the ratio does not silently close them; two
minors spaces; one handover bay), and two more evening hours for each
part-time same-day area. Each candidate is evaluated against the baseline
with paired Monte Carlo seeds, so the per-seed difference in the 4 hour share
subtracts the shared randomness. The gate is a one-sided 95% lower confidence
bound on the paired delta using the Student t quantile,

    lower = mean(d) - t(0.95, n-1) * sd(d) / sqrt(n)

and a move is only recommended when that bound exceeds zero; anything else is
reported as within the noise and rejected. Recommended moves are ranked by
net annual value, the annualised benefit from the business case minus 52
times the weekly staffing cost.

## 15. Finance

`finance/costbook.py` holds the editable planning assumptions: pounds per
4 hour breach avoided, per 12 hour wait avoided, per admission avoided,
agency premium and share, and Low, Moderate and High option cost bands.
`finance/business_case.py` prices only what the simulation showed: avoided
4 hour breaches per day are attendances times the percentage-point gain over
100, avoided 12 hour waits are the baseline-versus-option corridor counts,
each priced from the book and annualised times 365; the option's cost band
gives a low and high annual cost, ROI is benefit over the band midpoint and
payback is its reciprocal. Every case returns its drivers and assumptions so
a figure is never shown without what it rests on.

## 16. The backend API

The routes on this branch, all JSON unless noted. GET `/` serves the page and
GET `/favicon.ico` an inline SVG. GET `/api/setup` returns the saved
department plus the areas and roles catalogues. POST `/api/department` saves
a hand-edited department. GET `/api/trusts` lists the published-data
registry; POST `/api/trust/select` installs a trust from it; GET
`/api/trust/template` downloads the Excel set-up workbook; POST
`/api/trust/import` ingests a filled workbook (multipart), saving the
department, any calibration patch, cost book, role rates and service
parameters it carries. GET `/api/data-status` is the provenance endpoint:
source of the current set-up, calibration state with a synthetic-calibration
warning, per-field provenance rows, and a plain list of what is still an
assumption; the banner on the page renders it. GET and POST `/api/actions`
is the append-only decision log, GET `/api/audit` the configuration audit
trail. POST `/api/ask` runs the plain-English what-if; POST `/api/chat` the
grounded chatbot; POST `/api/auto-calibrate` the service-time search. POST
`/api/control-tower` returns the composed tower payload (cached), and POST
`/api/recommend` the CI-gated recommendations (cached). The heavy endpoints
all cache through the configuration-hash store.

Persistence (`platform/store.py`) uses six tables: departments (versioned,
append-only per key), calibrations (one per scope), runs (the cache),
settings (cost book, role rates, service params, data source, provenance),
audit (append-only change trail, with details truncated to 2000 characters
and a reader that degrades truncated JSON to text), and actions (the decision
log). SQLite is created on first run next to the repo; a DATABASE_URL
switches to Postgres unchanged.

## 17. The front end

One page, two tabs, no framework. `product.html` carries the markup and CSS;
`product.js` (vanilla, about 450 lines here) does everything else;
`provenance.js` renders the shared data-status banner.

On load the page fetches `/api/setup`, fills the set-up form and area
toggles, populates the trust picker, kicks off the tower, banner and decision
log. The tower call posts `/api/control-tower` and renders three things from
its payload. The standards cards show each metric's typical value with its
good-week and tough-week range on a small track. The flow map lays every node
out with the x coordinate precomputed server-side as (band column + 1) over
(columns + 2), Arrival on the left, outcome sinks in the final column, and y
spread evenly within a column ordered by volume; the client multiplies by the
canvas size, draws SVG curves for the links with width scaled by patient
volume, and colours each node green, amber or red by mean wait under 15,
under 60, or over. The hour slider replays the day: per-area occupancy by
hour, arrivals and exits by hour, and the pinch-by-hour series retarget the
counts, the highlight and the pulsing bottleneck flag as the hour changes,
all from arrays shipped once in the payload (occupancy is computed
server-side by sampling a 10-minute grid and averaging by hour of day).
Clicking a node opens a drill-down showing where its patients come from and
go (from the links), its wait and utilisation, which spaces and staff serve
it, and who is on shift at the selected hour from the resource rosters.

The what-if box posts the question to `/api/ask` and renders the returned
before-and-after deltas with colour by direction. The chat panel keeps a
16-turn history and posts to `/api/chat`, showing the answering intent as a
tag. Set-up changes (form save, trust pick, workbook import) all call
`afterDeptChanged`, which resets caches client-side, reapplies the form, and
reloads the tower and banner, keeping the one-department invariant visible.

## 18. The assistant layer

The chatbot (`assist/chat.py`) is an intent router over named data feeds
supplied by the server (`_chat_provider`): department facts, standards,
demand, staffing, the pinch, and the what-if executor. Every numeric answer
is formatted from those feeds, so the chat cannot disagree with a screen. A
how-to or concept question falls through to offline retrieval
(`assist/retrieval.py`): a keyword-IDF scorer over a 49-term NHS glossary,
curated product cards, and the README chunked by heading, with a confidence
gate that prefers admitting ignorance over guessing. Optionally, installing
the `anthropic` package and setting an API key upgrades the what-if parsing
and answer wording through ; without it nothing goes out over the
network and the offline parser handles the documented phrasings.

## 19. Testing and invariants

`python -m uec_hybrid.tests.run` is one end-to-end suite of plain asserts
(a few minutes on this branch). The invariants it enforces are the ones that
matter for trusting the model: resource capacities are never exceeded even
with span holds (checked by reconstructing peak concurrency from the holds
log), occupancy stays in [0, 1] and the feedback signal does not oscillate or
blow up, exit block emerges only with feedback on, conformance passes on a
clean run and catches an injected illegal transition, rostered staffing never
exceeds the roster's peak and falls overnight, disabled areas still validate
and route safely, part-time areas take no patients while closed, the nurse
ratio caps open cubicles at nurses times four while the physical count is
stashed, real capacity counts replace the scaled template exactly and junk or
staff keys are ignored, the workbook round-trips including the capacity
sheet and the ODS code, calibration patches re-apply across set-up changes
and reach the arrival streams, the published-aggregates maths normalises
correctly and the RGT file mixes cited real figures with labelled synthetic
distributions (validation targets real only), the seed CLI reproduces the
Cambridge department and persists provenance, auto-calibration converges
toward an observed figure, the recommender's gate rejects noise, and the
store's cache keys by configuration hash while truncated audit details
degrade safely.

## 20. Honesty principles and limitations

The design keeps three lines bright. Inputs versus outcomes: published
inputs (attendances, beds, occupancy) configure the model; published
outcomes (4 hour, 12 hour) are only validation targets, and the code refuses
to let a synthetic value stand in for one. Data versus assumption: anything
not supplied is a template default and the provenance banner on every screen
lists exactly what is still assumed, including a specific warning when a
loaded calibration is synthetic. Structure versus parameters: sizes, hours,
rotas, service times and demand are data and editable at runtime; the stage
graph itself is version-controlled JSON and deliberately has no API, because
changing it changes what is being claimed about the pathway.

Known limitations worth stating to any technical audience: service times are
expert-set unless calibrated (auto-calibration tunes one global scale, not
per-stage truth); the SD hospital is a two-stock homeostat, not a bed-level
model; arrival streams for GP referral and NHS 111 keep template shares, as
no extract identifies them; results are modelled distributions, not
forecasts of a particular day; and small deltas in comparisons can sit
within Monte Carlo noise, which is exactly why the recommendation gate
exists.
