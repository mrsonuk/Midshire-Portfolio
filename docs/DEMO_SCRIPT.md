# CUH ED Control Tower — demo script and narration

**Audience:** Cambridge University Hospitals (clinical, operational, flow programme)
**Running time:** 14 minutes, in seven acts. A 7-minute cut is marked at the end.
**Everything quoted here was measured on this build.** No number in this script is
illustrative — each one is reproducible with the commands in the appendix.

---

## Before you start — pre-flight (do this 15 minutes ahead)

The tool simulates a real week every time it answers. Cold, that is 12 seconds for
the control tower and about 30 for the recommender. Warm, it is instant. **Warm the
cache before anyone is watching:**

```bash
python3 -m uec_hybrid.ingest.seed RGT --warm     # loads Cambridge + pre-runs the screens
python3 -m uec_hybrid.app.server                 # then open http://127.0.0.1:5000
```

Then click through once yourself: Control tower → the hour slider → **What should we
change?** → one what-if. Everything you touch in the demo will then answer instantly.

Three practical notes:

* **The goal query ("what would it take to reach 90%?") takes ~33 seconds even warm**,
  because it stacks and re-tests combinations. Ask it, then talk over it — the script
  below gives you the words.
* Have a second browser tab already on **Design my ED** so you are not hunting for it.
* If you re-seed, the cache clears. Warm it again.

---

## Act 1 — The problem, and what this is (0:00–1:15)

> *"Every emergency department in the country is asked the same question: if we had
> one more cubicle, one more doctor, one more hour of SDEC — what would it actually
> buy us? And almost nobody can answer it, because the only way to find out has been
> to try it and wait a quarter.*
>
> *This is a simulation of Addenbrooke's emergency department. Not a generic one —
> yours. Your areas, your opening hours, your cubicle counts, your arrival pattern
> hour by hour, your acuity mix, your imaging rates. It runs a full week of your
> department in about ten seconds, and it lets you ask 'what if' before you commit
> to anything.*
>
> *I want to show you three things: that it is built on your data, that it reproduces
> what your department actually does, and — just as importantly — where it does not
> yet, and why."*

**On screen:** the header — CUH lockup, "Addenbrooke's Emergency Department".

---

## Act 2 — Loading Cambridge's own data (1:15–3:00)

**Click:** Design my ED → scroll to **Start from your trust**.

> *"Let me start from nothing and load Cambridge in front of you.*
>
> *There are two ways in. The dropdown loads a trust from published NHS figures —
> that is the cold start for any trust in England. But for Cambridge we have
> something much better, so let me use the second route: the filled workbook."*

**Click:** choose the file `rgt_cuh_workbook.xlsx` → **Import**.

> *"That is one spreadsheet, and it just configured the entire department.*
>
> *Behind it sit thirty-two extracts your team sent us — Joshua's CHEQS pulls — plus
> nine national NHS England publications. The workbook is the readable front end to
> all of it.*
>
> *Concretely, that upload just set: your arrival curve for all twenty-four hours of
> the day, from forty-six thousand real arrivals. Your acuity mix — two and a half
> percent resus, nineteen percent majors trolleys, forty-two percent majors ambulant.
> Ambulance conveyance at nineteen point one percent. Paediatrics at thirteen point
> four. Your admission rate for every acuity band. And your real physical capacity —
> thirty-four majors cubicles, six resus bays, fifteen UTC rooms, twelve paediatric
> cubicles — which your operational team gave us in August."*

**Click:** open the workbook's **Status** tab (have it open in Excel on a second screen).

> *"This tab is the honesty register, and it is the thing I would most like you to
> hold me to. Thirty-six model inputs, one row each, colour-coded.*
>
> *Green is real: twelve inputs from your CHEQS extracts, seven from national
> publications, six from your operational return. Amber is a modelled assumption —
> there are two. Grey is real data we hold but the engine cannot yet use — there are
> seven of those, and I will come back to them. Red is what we still need from you.*
>
> *There is one red row. One. We will talk about it at the end."*

---

## Act 3 — The control tower (3:00–5:00)

**Click:** Control tower.

> *"This is the department running. Four hundred attendances a day.*
>
> *Five headline tiles. Four-hour performance, typically fifty-six percent — and the
> dot on each slider shows the spread across simulated weeks: a good week sixty-two,
> a tough week fifty. That range matters more than the middle number, because it is
> the difference between a department that is coping and one that is not.*
>
> *Over twelve hours, ten percent. Ambulance handover within forty-five minutes,
> ninety-three. Walked out unseen, one percent."*

**Point at the green provenance banner above the tiles.**

> *"And this line is on every screen: Cambridge University Hospitals, figures as of
> June 2026 for A&E and Q4 for beds, and in amber, what is still an assumption —
> service times, the cost book, staff hourly rates. The tool tells you what it does
> not know, on the same screen as the answer. That is deliberate."*

---

## Act 4 — The flow map: where it actually hurts (5:00–7:30)

**Scroll to** the live flow map.

> *"Here is the whole department as one picture. Twenty-five areas, forty flows
> between them. Every box is real — because you told us which areas you run. You will
> notice there is no CDU and no EEMAC on this map, because Cambridge does not run
> them. EEMAC is in trial and CDU does not exist, so they are not here. The model
> matches your department, not a textbook one.*
>
> *The number in each box is how many patients are in that area. Green is flowing,
> amber is busy, red is stuck."*

**Drag the hour slider from 04:00 to 14:00, slowly.**

> *"Now watch the department wake up. At four in the morning it is quiet. By ten it
> is filling. By two in the afternoon the cubicles are full and the waits are
> building. This is your own arrival curve driving it — not an average, the real
> shape of your day.*
>
> *And the pinch point moves with the clock. It is not the same bottleneck at
> midnight as at midday, which is exactly why 'where is our bottleneck' is the wrong
> question and 'where is it at 2pm on a Monday' is the right one."*

**Click one area — ED ambulatory — to open the drill-down.**

> *"Click any area and it tells you what that queue is waiting for: the spaces, the
> staff, who is on at this hour, and where those patients came from and go to."*

**Point at the pinch banner.**

> *"And here is the headline. Biggest delay: ED ambulatory, fit-to-sit — mean wait
> ninety-seven minutes, one thousand three hundred and fifty-seven patient-hours lost
> in a week. That is the number I would take to a board."*

---

## Act 5 — The tool answers back (7:30–10:30)

**Click:** *What should we change? Search staffing, capacity and hours.*

> *"This is the part I find most useful. It has just simulated fourteen different
> changes — more doctors, more nurses, more chairs, longer opening hours, more ward
> beds — each one against the same random weeks as the baseline, so the comparison is
> paired and fair.*
>
> *Fourteen candidates. Thirteen of them it threw away as within the noise. It
> recommends one: add four fit-to-sit chairs, worth five point seven points on the
> four-hour standard.*
>
> *Notice what just happened. It found the bottleneck independently — ED ambulatory —
> and the change it recommends is chairs in that same area. Those two agreed without
> being told to. And notice it is capacity, not staffing: the tool is not reaching for
> 'hire more people' as a reflex.*
>
> *The thirteen it rejected matter as much. A tool that recommends something every
> time you ask is a tool that is guessing."*

**Type into What-if:** `add 2 doctors` → Run scenario. *(~5s)*

> *"You can also ask it directly, in plain English."*

**Read the result.** *(It will show roughly +1.1 points; read whatever it actually says.)*

> *"Two more doctors: about one point on four-hour performance. Compare that with four
> chairs at five point seven. That is a genuinely counter-intuitive result, and it is
> the kind of thing that is very hard to see from a spreadsheet — the constraint was
> never the doctors."*

**Type:** `what would it take to reach 90% in 4 hours?` → Run. *(~33s — talk over it)*

> *"While that runs — this one is a goal query. Instead of testing one change, it
> stacks combinations until it either hits the target or runs out of things that
> clear statistical significance.*
>
> *And I want to be straight with you about what it is about to say. It will not get
> to ninety. It gets to about sixty-one, and then it tells you it cannot get further —
> that even stacking every change that clears the confidence bar is not enough. A tool
> that cheerfully told you ninety percent was two nurses away would be lying to you."*

**Click:** the *Ask your ED* chat bubble → type `where is the pinch point?`

It answers: **"Pinch point: Paediatric area. Bites hardest 08:00–10:00."**

> *"And there is a chatbot, grounded in the same numbers. It can only answer from what
> the simulation actually computed, so it cannot contradict the screen behind it."*

**Two more worth showing** (both answer instantly):

* `where is demand?` → *"~400 attendances a day. Heaviest around 11:00–14:00, ~29/hour at peak."*
* `what if we add 3 nurses at 1pm?` → it runs the scenario from the chat box.

> ⚠️ **Know this before someone asks.** The chat says the pinch point is the
> **paediatric area at 08:00–10:00**, while the banner above says the biggest delay is
> **ED ambulatory**. Both are right and they measure different things: the chat gives
> the worst *hour-by-hour* pinch, the banner gives the largest *total* patient-hours
> lost across the week. If someone spots it, that is a good answer to have ready —
> "one is the sharpest moment, the other is the biggest total cost".

---

## Act 6 — Does it match reality? (10:30–12:30)

> *"Everything I have shown you is worthless unless it reproduces your department. So
> here is the validation, and here is where I am going to be uncomfortable in public."*

**Show this table on a slide:**

| Measure | Model | Cambridge actual | |
|---|---|---|---|
| 4-hour performance | 56.1% | 52.93% | ✅ |
| 12-hour waits (from arrival) | 10.9% | 9.98% | ✅ |
| Ambulance handover ≤45 min | 92.5% | 84.19% | ⚠️ optimistic |

| Time in department | Model | Cambridge actual | |
|---|---|---|---|
| Resus | 349 min | 324 | 1.08× |
| **Majors trolleys** | **727 min** | **725** | **1.00×** |
| Majors ambulant | 224 min | 254 | 0.88× |
| Minors | 173 min | 164 | 1.05× |
| Paediatrics | 222 min | 176 | 1.26× |

> *"Four-hour performance: fifty-six against your fifty-three. Twelve-hour waits: ten
> point nine against ten.*
>
> *But the row I would look at is majors trolleys. Your patients on a trolley wait a
> median of seven hundred and twenty-five minutes — twelve hours. The model says seven
> hundred and twenty-seven. That is not a fitted number; that emerged from modelling
> the mechanism properly — a patient waiting for a bed occupies the trolley, not a
> doctor. When we got that wrong the model said two hundred and fifty minutes and was
> confidently useless.*
>
> *Every area is now within about ten percent except paediatrics, which runs
> twenty-six percent long. I do not yet know why, and I would rather say that than
> explain it away."*

---

## Act 7 — What it cannot do yet (12:30–14:00)

> *"Four limitations. All of them are data or engine gaps, and none of them are
> hidden in a footnote — they are in the Status tab you saw at the start.*
>
> **One. The 'seen within fifteen minutes' tile — please ignore it.** *It reads
> eighty-four percent against your forty-two. That is not the model being wrong, it is
> us measuring different things: our clock starts at triage, yours for minors starts
> at a clinician assessment thirty-seven minutes into the visit. Same word, different
> event. Until we align the definition, that tile is not comparable and should not be
> quoted.*
>
> **Two. Day of week does not exist in this model.** *Your own data shows Sunday
> discharges run at twenty-nine percent of Monday's. That weekend collapse in bed
> releases is probably the single biggest driver of your Monday exit block — and this
> engine literally cannot represent it. Every day is the same day. That is the most
> valuable thing we could build next.*
>
> **Three. Long-stay patients are invisible.** *Sixty percent of your occupied beds
> are held by patients staying seven days or more. The bed model has no compartment
> for that, so it is more optimistic about bed turnover than reality.*
>
> **Four. The rota is not yours.** *Staffing is a template scaled to your size, because
> workforce was out of scope. So treat any staffing recommendation as directional, not
> a roster.*
>
> *And one thing we need from you: arrivals into each area by hour. Everything else on
> the red list is closed.*
>
> *What you have is a model that reproduces your four-hour position, your twelve-hour
> position, and your length of stay area by area — and that tells you honestly where
> it stops. I would rather show you that than a demo where everything is green."*

---

## The 7-minute cut

Keep Acts 1, 2 (drop the Status tab detail), 4, 5 (drop the goal query and chatbot),
6, and the first two limitations. Skip Act 3 — the tiles are visible behind the flow
map anyway.

## If something goes wrong

* **Spinner does not finish** — the cache went cold. Say "it is simulating a full week
  live" and wait; it is 12 seconds, not a hang.
* **A number differs from this script** — the simulation is stochastic; the four-hour
  figure moves ±3 points between runs. Say so. It is a feature, not an excuse: that
  spread is the good-week/tough-week range.
* **Never** quote the 15-minute tile or per-area volumes (those sit ~0.85× by a
  published-versus-internal counting difference, not an error).

## Appendix — reproducing every number here

```bash
python3 -m uec_hybrid.validation.against_trust RGT   # the Act 6 tables
python3 -m uec_hybrid.tests.run                      # the whole suite
```

Provenance for every input: the workbook's **Status** and **Sources** tabs, and
`docs/CUH_DATA_LOG.md`.
