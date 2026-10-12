# Midshire University Hospitals Trust Control Tower (demonstrator)

> **First time using AWS with $100 credits?** Start with [the Lightsail step-by-step beginner guide](docs/AWS_LIGHTSAIL_START_HERE.md) (about $24/month for the recommended starter server). For the larger, more expensive Elastic Beanstalk/RDS architecture see [AWS deployment and security checklist](docs/AWS_PUBLIC_DEMO.md). The local Flask server must never be exposed directly to the internet.

This branch adds an **adult ED simulation and planning demonstrator** under the
fictional name *Midshire University Hospitals Trust*. It is built on the
Cambridge (RGT) control tower below and leaves that build intact. Midshire is a
**demonstration identity**: it is not a real trust, not a live patient feed, not
a connected digital twin and not a clinically validated staffing tool.

## Run the demonstrator

```
pip install -r requirements.txt
python3 -m uec_hybrid.midshire            # http://127.0.0.1:5050
```

No external AI service, API key or network access is needed. The demo opens on
committed results computed in advance (the baseline and five package searches,
including one that adds no staff, space or beds)
so a presentation never waits on a cold run; everything can be re-run from the
page. It runs on Linux, macOS and Windows: the model picks a process start
method the platform supports and falls back to running in one process if it
cannot start workers. Useful commands:

| Command | What it does |
|---|---|
| `python3 -m uec_hybrid.midshire --check` | start, load fixtures, report, exit |
| `python3 -m uec_hybrid.midshire.precompute` | regenerate the precomputed fixtures (~30 min) |
| `python3 -m uec_hybrid.midshire.validate` | conformance + per-area comparison + four-hour decomposition |
| `python3 -m uec_hybrid.tests.midshire` | the Midshire checks (also run by `uec_hybrid.tests.run`) |

**Reset the demo:** Scenarios → "Back to the baseline" (keeps saved scenarios),
or stop the server and delete `uec_midshire.sqlite3` for a completely fresh
start. Midshire stores everything in that file (or `MIDSHIRE_DATABASE_URL`); it
never reads or writes the Cambridge database `uec_platform.sqlite3`.

## What it shows

Overview → Patient flow → Workforce & investment → Scenarios, and **Ask My ED**
as another way into the same workflow. Every page can show a **Selected day**
(one modelled day, Tuesday to Sunday; each modelled week starts empty on Monday)
or a **Typical day** (the average of every modelled day). Patient flow is an animated flow map like the Cambridge control
tower's, simplified to five groups left to right; selecting a group opens a map
of its areas underneath, and the full step-by-step map is the expert view.
The whole project from scratch (the problem, methodology, logic, outputs,
checks and limitations) is in [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md);
details, the requirement mapping and a presenter walkthrough are in
[`docs/MIDSHIRE.md`](docs/MIDSHIRE.md).

## Data boundaries

* Inputs trace to the Cambridge build's committed files (`data/cuh/`, NHS
  England publications under `data/`, `uec_hybrid/data/rgt_published.json`), or
  are labelled **illustrative** in `uec_hybrid/data/midshire/midshire_demo.json`
  (rota, staff costs, estates unit costs, SDEC size, hours and streaming shares,
  space-staffing ratios). Every input's kind and source is listed in the
  fixture and in `docs/MIDSHIRE.md`; the on-screen data sources page is kept
  in the code but is not in the navigation.
* Adult only: children are removed from demand (400.5 × (1 − 0.1335) = 347.0
  adult attendances a day, using the source trust's own paediatric-area share),
  with the paediatric area, staff and routes; they are not re-routed.
* Outputs are simulated. The adult, SDEC-extended build does not inherit the
  Cambridge validation; see `python3 -m uec_hybrid.midshire.validate`.

## Metric definitions (short form)

The four-hour measure is the share of **eligible adult attendances** (everyone
arriving in the observed days; no exclusions; left-without-being-seen included)
completed within the target time, from arrival to leaving the ED. SDEC time
counts **inside** the ED attendance. Each simulated week runs a 12-hour drain;
anyone still in the department then has already exceeded the target and counts
as not met (and as unfinished work in progress). Snapshot counts come from **one**
simulated day; whole-run figures are per simulated week, then summarised across
weeks (mean, range, and a simulation-noise interval of the mean). Every metric's
population, units, window, start, end and treatment of unfinished patients is
in `uec_hybrid/midshire/metrics.py` (`DEFINITIONS`).

---

# Model ED Optimiser, control tower edition

This branch carries a focused build of the Model ED Optimiser. It has two
screens and nothing else: the control tower, which shows how patients flow
through an emergency department hour by hour, and Set up my ED, where you tell
the tool about your department. The full product with the planner, the
executive brief and the analyst view lives on the main branch.

## Running it

```
pip install -r requirements.txt
python -m uec_hybrid.app.server
```

Open http://127.0.0.1:5000 in a browser. Everything runs offline; the app
makes no outbound calls.

## The control tower

The opening screen simulates the department you have configured and shows the
headline standards (the 4 hour position, waits over 12 hours, ambulance
handover, walk-outs) as a typical week with a good-week and tough-week spread.
Below that sits the live flow map. Each box is an area of the department, the
lines are patients moving between areas, and the time slider replays the day
hour by hour. Click any box to see where its patients come from, where they go
next, and who is on shift. The box with the pulsing border is the pinch point,
the stage costing patients the most time.

Two assistants sit on this screen. "Ask a what-if" takes a change in plain
English, for example "add 3 nurses at 1pm" or "10% more attendances", runs it
against your department and shows a before and after table. The chat button in
the corner answers questions about the department from the model's own
computed numbers, so it can never disagree with the screen. There is also a
button that searches staffing, capacity and opening-hour changes and returns
the ones that pass a statistical check, with costs.

## Set up my ED

Three ways to describe your department, from quickest to most complete.

1. Pick your trust. The registry in `uec_hybrid/data/nhs_trust_snapshot.csv`
   holds published NHS figures per trust (attendances a day, beds, occupancy,
   and the observed 4 hour position kept back for validation). Selecting a
   trust fills the model from those figures. Adding a trust is a row in that
   file, not a code change.
2. Import a workbook. Download the Excel template from the screen, fill in
   the tabs and upload it. The tabs cover the department name and ODS code,
   which areas you run and their opening hours, the rota, your real physical
   capacity (cubicles, resus bays, CDU beds and so on, which no public data
   source can supply), arrivals by hour, acuity mix, costs and measured
   service times. Blank cells keep a sensible default.
3. Fill in the form by hand.

Whichever route you use, one saved department drives both screens, and a
provenance banner on every page says where each number came from and which
values are still assumptions. Anything the tool had to assume is labelled on
screen rather than silently guessed.

## The Cambridge build

This branch is seeded for Cambridge University Hospitals (ODS code RGT).
Real published inputs were transcribed from the primary files kept under
`data/` in this repository: attendances of 400.5 a day and a 4 hour position
of 52.93% from the NHS England monthly A&E return for June 2026, and 1,068
general and acute beds at 89.26% occupancy from the KH03 bed return for the
quarter ending March 2026. Per-figure citations sit in
`uec_hybrid/data/rgt_published.json`. Distribution shapes that are not
published (arrivals by hour, acuity mix, ambulance share, admission rates by
acuity) are synthetic placeholders and the banner says so until the trust's
own extracts replace them.

To stand the Cambridge department up from the committed files:

```
python -m uec_hybrid.ingest.seed RGT --warm
```

The `--warm` flag precomputes the control tower so the first page load is
instant.

## Checks

```
python -m uec_hybrid.tests.run
```

One end-to-end suite, roughly six to eight minutes. It covers the simulation
engine, the department builder, the data ingest paths and the two screens.

## What sits underneath

A discrete event simulation of patient flow through the ED, coupled to a
system dynamics model of the wider hospital (ward beds, discharges, community
capacity), so bed pressure genuinely feeds back into ED waits. The pathway
definition lives in `uec_hybrid/pathways/model_ed.json`. Results are modelled,
not predictions: they show direction and trade-offs, and every figure should
be validated against local data before an operational decision rests on it.
