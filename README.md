# Model ED Optimiser

**Help your trust design, staff and run a high-performing Emergency Department — using the NHS Model ED blueprint.**

---

## Objective

Every acute trust is being asked to move its Emergency Department toward the NHS England **Model Emergency Department** — a blueprint for how patients should flow through the department, which areas to provide, and how the ED connects to the rest of the hospital.

**This tool lets you model *your* department before you change anything in real life.**

You can:

- See where patients get stuck and **when in the day** pressure builds
- Check whether your **rota matches demand**
- Test “what if we added beds / staff / a UTC?” and see the effect on **4-hour performance**
- Build a **costed case** for investment
- Produce a **board-ready summary** in one click

You do **not** need to be a data scientist or simulation expert. The product speaks in plain language: flow, pinch-points, standards, and costs — not model jargon.

> **What sits underneath:** a detailed computer model of patient flow through an ED, coupled to ward beds and community services. That engine is hidden; you interact through simple screens.

---

## Who this is for

| Role | What you would use it for |
|---|---|
| **ED matron / operational manager** | Daily flow, staffing gaps, where the pinch-point is |
| **ED consultant / clinical lead** | Whether the department layout and areas match Model ED |
| **COO / divisional director** | Risk level, standards, investment priorities, board paper |
| **ICB / winter planner** | Demand forecast, stress tests (flu, strike, ward closures), options |
| **Analyst / informatics** | Deeper simulation, calibration from real data, validation |

---

## Getting started

### 1. Install and open the product

```bash
pip install -r requirements.txt
python -m uec_hybrid.app.server
```

Open your browser at **http://127.0.0.1:5000**

### 2. Set up your department (do this first)

Go to **Set up my ED** and tell the tool about your trust. Choose whichever route is easiest:

| Route | Best if you… | What it fills in |
|---|---|---|
| **Pick your trust** | Want a quick start from published NHS data | Attendances per day, bed numbers, occupancy |
| **Import a workbook** | Already have a spreadsheet of your department | Areas, hours, rota, costs — everything |
| **Fill in the form by hand** | Prefer to configure step by step | Areas on/off, opening hours, beds, rota |

Click **Save & re-run**. Everything else in the product uses this one saved department.

### 3. Read the Control tower

Open the **Control tower** tab. You will see:

- **How your department is running** — 4-hour standard, walk-outs, ambulance handover, etc., shown as good / typical / tough week
- **Your busiest pinch-point** — the area costing you the most time, and roughly when in the day it bites
- **Live flow map** — boxes for each area; patients moving between them. Use the **time slider** to see the department at different hours. **Click any box** to see where patients come from, where they go next, and who is on shift

### 4. Check your rota

Open **Workforce**. The chart compares **demand by hour** with **staff on by hour**. Red windows mean you are likely under-staffed for the curve. You can edit shifts in the rota editor and see cost update instantly. **Apply & re-run** feeds changes back into the flow map.

### 5. See what you are missing from Model ED

Open **Model ED gaps**. Each missing element (e.g. RAT, SDEC, frailty pathway) shows what it would add to performance and a rough cost band.

### 6. Plan for winter or a bad day

Open **Plan ahead** (`/planner`):

- **Winter plan** — expected demand, whether you meet the 4-hour standard, ranked options (more beds, community capacity, UTC, etc.)
- **Stress tests** — named scenarios (flu, norovirus ward closures, medical strike). Each shows how much performance drops vs a normal week (e.g. “−9 points on 4-hour” means nine percentage points worse)
- **Today** — intraday view: given arrivals so far and how full the hospital is, what helps this afternoon

### 7. Executive summary and board paper

Open **Executive brief** (`/exec`) for a one-page view: risk level, standards, pinch-point, pay-bill, top investment case. Download a PDF for the board.

### 8. Analyst view (optional, for deeper work)

Open **Analyst view** (`/analyst`) if you need more detail: uncertainty ranges, scenario comparison, pathway validation, or calibration from a real attendance file (ECDS-style CSV).

---

## The four main screens

```
  Set up my ED  ──►  Control tower  ──►  Workforce / Gaps
         │                    │
         │                    └──►  Executive brief (PDF)
         │
         └──►  Plan ahead (winter / stress tests / today)
                        │
                        └──►  Analyst view (technical depth)
```

### Control tower — `/`

Your day-to-day operational home.

| Tab | In plain terms |
|---|---|
| **Control tower** | Where are patients? Where is it stuck? What does a typical week look like on the standards? |
| **Workforce** | Are we staffed for when patients actually arrive? What does the rota cost? |
| **Model ED gaps** | Which Model ED building blocks do we lack, and what would each one be worth? |
| **Set up my ED** | Configure the department — areas, hours, beds, rota |

### Executive brief — `/exec`

One screen for senior leaders: risk, standards, bottleneck, money, and a downloadable report.

### Plan ahead — `/planner`

For winter and surge planning. Uses **your** configured department (not a generic template). Stress-test tiles compare a scenario to a normal week:

- **Points on 4-hour** = difference in the percentage of patients seen within 4 hours
- **Long bed-waits per day** = how many more patients per day wait over 12 hours for a ward bed

### Analyst view — `/analyst`

The full model for analysts and informatics. Same department as the control tower, plus levers to change demand, beds, and capacity for what-if runs. Includes charts for uncertainty, scenarios, and a check that simulated patient journeys match the intended Model ED pathway.

---

## Understanding the main outputs

### The 4-hour standard

The share of patients **admitted, transferred or discharged within 4 hours**. Shown as a percentage. The product also shows a **good week** and **tough week** range so you can see natural variation.

### The pinch-point

The single stage where patients lose the most time — often triage, majors, or waiting for a bed. On the control tower this is flagged on the flow map and linked to **time of day** (e.g. worst around 14:00–18:00).

### Flow map colours

| Colour | Meaning (control tower) |
|---|---|
| Green | Flowing — low occupancy for that hour |
| Amber | Busy |
| Red | Stuck — area near its peak load |

On the analyst view, colours reflect **wait time** instead (<15 min / 15–60 min / >60 min).

### Model ED gaps

Compares your configured areas against the Model ED blueprint. Missing items show an estimated benefit (e.g. points on 4-hour or admissions avoided) and a cost band (Low / Moderate / High).

### Business case figures

Costs and benefits use a **cost book** you can edit (hourly rates, value of avoiding a breach). Treat all £ figures as **indicative planning numbers** — validate locally before committing.

---

## Adding your own data (optional)

The product runs out of the box on **typical NHS patterns**. To make it more like your trust:

1. **Pick your trust** or **import a workbook** — fastest way to set attendances, beds, and rota
2. **Analyst → Data & calibration** — upload an ECDS-style CSV to calibrate arrivals by hour, acuity mix, and admission rates from real activity
3. **Edit costs and targets** — adjust hourly rates and RAG targets if your trust uses different assumptions

**Important:** Service times (how long triage or a scan takes) are modelled defaults unless you provide stage-level timestamps. Always **validate against local data** before operational decisions.

---

## AI assist (optional)

Two AI features are built in, designed so **no number is ever invented** — every
figure always comes from the simulation:

- **“Ask your ED” chatbot** (floating button, bottom-right) — ask anything about
  your department at any time: “where is demand?”, “where should I deploy
  staff?”, “what’s the pinch point?”, “how are we doing?”, “what does SDEC
  mean?”, or a what-if. Answers are formatted from the product’s own computed
  data, so the chat can never disagree with a screen. How-to and concept
  questions (“how do I import my data?”, “explain the methodology”) are answered
  by built-in retrieval (RAG) over the glossary, a product guide and these docs —
  still fully offline, and a question it can’t answer confidently gets the help
  text, never a guess.
- **Ask a what-if** (Control tower) — type a change in plain English (“add 2
  doctors”, “add 3 nurses at 1pm”, “remove a doctor overnight”, “10% more
  attendances”, “40 more ward beds”) and the model runs it against your
  department and reports the impact on the standards, with a before/after table.
  Time windows (“at 1pm”, “from 8pm to 8am”, “overnight”) apply the change to
  just those hours; nurse changes work through the nurse-to-cubicle ratio, and
  the answer says so — including when extra nurses would open no extra cubicles.
  Works fully offline via a built-in parser.
- **Auto-calibration** (Analyst → Data & calibration) — enter your real observed
  4-hour % and an automated search tunes the model’s service-time assumption
  until the modelled figure matches. Reversible; the search path is shown.

Optionally, installing the `anthropic` package and setting `ANTHROPIC_API_KEY`
upgrades “Ask a what-if” with Claude: free-form phrasing and better-worded
answers. Without a key the product behaves exactly as before and makes **no
outbound calls** — the offline guarantee for NHS networks is unchanged.

---

## What you do not need to do

- Edit code or JSON files to configure a department
- Understand simulation terminology on the product screens
- Stay online — the product runs fully offline (no external websites at runtime)

The **shape** of the Model ED pathway (which stages exist and how they connect) is fixed to the NHS blueprint and checked automatically. You configure **your** sizes, areas, hours, rota, and data — not the clinical design itself.

---

## Quick reference — web addresses

| Address | Screen |
|---|---|
| http://127.0.0.1:5000/ | Control tower (main product) |
| http://127.0.0.1:5000/exec | Executive brief |
| http://127.0.0.1:5000/planner | Plan ahead |
| http://127.0.0.1:5000/analyst | Analyst view |

Workbook template: `/api/trust/template` (download from Set up my ED)

---

## Limitations — read before you decide

- Results are **modelled**, not predictions. They show direction and trade-offs, not exact next Tuesday.
- Synthetic defaults are clearly flagged; calibrate where you can.
- Small changes in stress tests (±1–2 points) may be within simulation noise.
- One saved department drives all screens — change set-up once, everything updates together.

---

## For developers and technical staff

Technical architecture, API details, engine design (DES + System Dynamics coupling), test suite, and deployment notes are in:

- **[docs/HANDOVER.md](docs/HANDOVER.md)** — engineering handover
- **[docs/PRODUCT_REBUILD_PLAN.md](docs/PRODUCT_REBUILD_PLAN.md)** — product roadmap

Quick technical start:

```bash
pip install -r requirements.txt
python -m uec_hybrid.app.server      # product at http://127.0.0.1:5000
python -m uec_hybrid.tests.run       # end-to-end checks (~8 min)
python -m uec_hybrid.report          # standalone decision-report PDF
```

SQLite database `uec_platform.sqlite3` is created on first run. Set `DATABASE_URL` for Postgres in shared deployments.

---

## Further reading

- NHS England, *The Model Emergency Department: high-performing UEC pathways* (Feb 2026) — the pathway this tool implements
- Product pitch deck: [docs/pitch/index.html](docs/pitch/index.html)
