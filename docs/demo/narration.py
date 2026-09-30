# -*- coding: utf-8 -*-
"""Narration segments for the CUH demo recording.

Each segment is (act, action, caption). The caption is BOTH the spoken line and
the on-screen subtitle, so what a viewer hears and reads never diverge. Wording
is taken from docs/DEMO_SCRIPT.md - every figure in it was measured on this
build, so nothing here is illustrative.
"""

SEGMENTS = [
 # ---------------------------------------------------------------- Act 1
 ("Title", "titlecard",
  "Cambridge University Hospitals. Emergency department control tower. "
  "A working simulation, built on the trust's own data."),

 ("Act 1 - The question", "none",
  "Every emergency department in the country is asked the same question. "
  "If we had one more cubicle, one more doctor, one more hour of S-DEC, "
  "what would it actually buy us?"),
 ("Act 1 - The question", "none",
  "And almost nobody can answer it, because the only way to find out has been "
  "to try it and wait a quarter."),
 ("Act 1 - The question", "hi:header",
  "This is a simulation of Addenbrooke's emergency department. Not a generic one. "
  "Yours. Your areas, your opening hours, your cubicle counts, your arrival "
  "pattern hour by hour, your acuity mix, your imaging rates."),
 ("Act 1 - The question", "none",
  "It runs a full week of your department in about ten seconds, and it lets you "
  "ask what if, before you commit to anything."),
 ("Act 1 - The question", "none",
  "I want to show you three things. That it is built on your data. That it "
  "reproduces what your department actually does. And, just as importantly, "
  "where it does not yet, and why."),

 # ---------------------------------------------------------------- Act 2
 ("Act 2 - Loading Cambridge's data", "goto_setup",
  "Let me start from nothing, and load Cambridge in front of you."),
 ("Act 2 - Loading Cambridge's data", "hi:#trustPick",
  "There are two ways in. This dropdown loads a trust from published NHS "
  "figures. That is the cold start for any trust in England."),
 ("Act 2 - Loading Cambridge's data", "hi:#trustFile",
  "But for Cambridge we have something much better, so let me use the second "
  "route. The filled workbook."),
 ("Act 2 - Loading Cambridge's data", "upload_workbook",
  "That is one spreadsheet, and it just configured the entire department."),
 ("Act 2 - Loading Cambridge's data", "hi:#importStatus",
  "Behind it sit thirty-two extracts your team sent us, Joshua's C-HEQS pulls, "
  "plus nine national NHS England publications. The workbook is the readable "
  "front end to all of it."),
 ("Act 2 - Loading Cambridge's data", "none",
  "Concretely, that upload just set your arrival curve for all twenty-four "
  "hours of the day, from forty-six thousand real arrivals."),
 ("Act 2 - Loading Cambridge's data", "none",
  "Your acuity mix. Two and a half percent resus, nineteen percent majors "
  "trolleys, forty-two percent majors ambulant. Ambulance conveyance at "
  "nineteen point one percent. Paediatrics at thirteen point four."),
 ("Act 2 - Loading Cambridge's data", "none",
  "Your admission rate for every acuity band. And your real physical capacity. "
  "Thirty-four majors cubicles, six resus bays, fifteen U-T-C rooms, twelve "
  "paediatric cubicles, which your operational team gave us in August."),
 ("Act 2 - The honesty register", "status_overlay",
  "This is the honesty register, and it is the thing I would most like you to "
  "hold me to. Thirty-six model inputs, one row each."),
 ("Act 2 - The honesty register", "none",
  "Green is real. Twelve inputs from your C-HEQS extracts, seven from national "
  "publications, six from your operational return."),
 ("Act 2 - The honesty register", "none",
  "Amber is a modelled assumption. There are two. Grey is real data we hold "
  "but the engine cannot yet use. There are seven of those, and I will come "
  "back to them."),
 ("Act 2 - The honesty register", "none",
  "Red is what we still need from you. There is one red row. One. "
  "We will talk about it at the end."),

 # ---------------------------------------------------------------- Act 3
 ("Act 3 - The control tower", "goto_tower",
  "This is the department running. Four hundred attendances a day. "
  "It is simulating a full week live, right now."),
 ("Act 3 - The control tower", "hi:.tiles",
  "Five headline tiles. Four-hour performance, typically fifty-six percent. "
  "And the dot on each slider shows the spread across simulated weeks. "
  "A good week sixty-two, a tough week fifty."),
 ("Act 3 - The control tower", "none",
  "That range matters more than the middle number, because it is the "
  "difference between a department that is coping and one that is not."),
 ("Act 3 - The control tower", "none",
  "Over twelve hours, ten percent. Ambulance handover within forty-five "
  "minutes, ninety-three. Walked out unseen, one percent."),
 ("Act 3 - The control tower", "hi:#dataStatus",
  "And this line is on every screen. Cambridge University Hospitals, figures "
  "as of June twenty twenty-six for A and E, and Q four for beds."),
 ("Act 3 - The control tower", "none",
  "And in amber, what is still an assumption. Service times, the cost book, "
  "staff hourly rates. The tool tells you what it does not know, on the same "
  "screen as the answer. That is deliberate."),

 # ---------------------------------------------------------------- Act 4
 ("Act 4 - Where it actually hurts", "scroll_to:#flow",
  "Here is the whole department as one picture. Twenty-five areas, forty flows "
  "between them."),
 ("Act 4 - Where it actually hurts", "none",
  "Every box is real, because you told us which areas you run. You will notice "
  "there is no C-D-U and no E-E-M-A-C on this map, because Cambridge does not "
  "run them."),
 ("Act 4 - Where it actually hurts", "none",
  "E-E-M-A-C is in trial and C-D-U does not exist, so they are not here. "
  "The model matches your department, not a textbook one."),
 ("Act 4 - Where it actually hurts", "none",
  "The number in each box is how many patients are in that area. "
  "Green is flowing, amber is busy, red is stuck."),
 ("Act 4 - Where it actually hurts", "slider:4",
  "Now watch the department wake up. At four in the morning it is quiet."),
 ("Act 4 - Where it actually hurts", "slider_sweep:10",
  "By ten it is filling."),
 ("Act 4 - Where it actually hurts", "slider_sweep:14",
  "By two in the afternoon the cubicles are full and the waits are building. "
  "This is your own arrival curve driving it. Not an average. The real shape "
  "of your day."),
 ("Act 4 - Where it actually hurts", "hi:#hourPinch",
  "And the pinch point moves with the clock. It is not the same bottleneck at "
  "midnight as at midday."),
 ("Act 4 - Where it actually hurts", "none",
  "Which is exactly why, where is our bottleneck, is the wrong question, and "
  "where is it at two p-m on a Monday, is the right one."),
 ("Act 4 - Where it actually hurts", "click_area:ED ambulatory (fit to sit)",
  "Click any area and it tells you what that queue is waiting for. The spaces, "
  "the staff, who is on at this hour, and where those patients came from and "
  "go to."),
 ("Act 4 - Where it actually hurts", "close_drill",
  "And here is the headline the banner gives you. Across the working day the "
  "pinch point is the paediatric area. A mean wait of two hundred and "
  "forty-seven minutes, biting hardest between eight and ten in the morning."),
 ("Act 4 - Where it actually hurts", "hi:.fmnode[data-label=\"ED ambulatory (fit to sit)\"]",
  "E-D ambulatory is the other half of the story. A shorter wait, ninety-seven "
  "minutes. But eight hundred and forty-two patients a week pass through it, so "
  "it loses more patient-hours than anywhere else in the department. "
  "One thousand three hundred and fifty-seven of them in a week, and the "
  "banner puts that figure on the screen next to the pinch point."),
 ("Act 4 - Where it actually hurts", "none",
  "Those are two different questions. Where does it hurt most sharply, and "
  "where does it cost the most in total. The tool answers both, and they do "
  "not have to give the same area."),

 # ---------------------------------------------------------------- Act 5
 ("Act 5 - The tool answers back", "recommend",
  "This is the part I find most useful. It has just simulated fourteen "
  "different changes. More doctors, more nurses, more chairs, longer opening "
  "hours, more ward beds."),
 ("Act 5 - The tool answers back", "none",
  "Each one against the same random weeks as the baseline, so the comparison "
  "is paired and fair. That is why it takes half a minute rather than an "
  "instant. It is running the department fourteen more times."),
 ("Act 5 - The tool answers back", "wait_rec",
  "Fourteen candidates. Thirteen of them it threw away as within the noise. "
  "It recommends one. Add four fit to sit chairs, worth five point seven "
  "points on the four-hour standard."),
 ("Act 5 - The tool answers back", "none",
  "Notice where those chairs are. E-D ambulatory. That is the area carrying "
  "the largest total patient-hours lost, and the recommender got there on its "
  "own, by simulation. Nobody pointed it at that area."),
 ("Act 5 - The tool answers back", "none",
  "And let me be precise, because it matters. The banner's working-day pinch "
  "is paediatrics. The recommender's best move is in ambulatory. Those are two "
  "different measures, and I would rather show you both than pick the one that "
  "tells the tidier story."),
 ("Act 5 - The tool answers back", "none",
  "And notice it is capacity, not staffing. The tool is not reaching for, "
  "hire more people, as a reflex."),
 ("Act 5 - The tool answers back", "none",
  "The thirteen it rejected matter as much. A tool that recommends something "
  "every time you ask, is a tool that is guessing."),
 ("Act 5 - The tool answers back", "whatif:add 2 doctors",
  "You can also ask it directly, in plain English. Add two doctors."),
 ("Act 5 - The tool answers back", "none",
  "Two more doctors. About one point on four-hour performance. Compare that "
  "with four chairs at five point seven."),
 ("Act 5 - The tool answers back", "none",
  "That is a genuinely counter-intuitive result, and it is the kind of thing "
  "that is very hard to see from a spreadsheet. The constraint was never "
  "the doctors."),
 ("Act 5 - The tool answers back", "whatif:what would it take to reach 90% in 4 hours?",
  "This one is a goal query. Instead of testing one change, it stacks "
  "combinations until it either hits the target, or runs out of things that "
  "clear statistical significance."),
 ("Act 5 - The tool answers back", "none",
  "And I want to be straight with you about what it is about to say. "
  "It will not get to ninety."),
 ("Act 5 - The tool answers back", "none",
  "It reaches sixty point eight percent from a fifty-five point three "
  "baseline, and then it tells you, in writing, that closing the rest needs "
  "levers outside this search. Demand diversion, or service-time change."),
 ("Act 5 - The tool answers back", "none",
  "A tool that cheerfully told you ninety percent was two nurses away "
  "would be lying to you."),
 ("Act 5 - The tool answers back", "chat:where is the pinch point?",
  "And there is a chatbot, grounded in the same numbers."),
 ("Act 5 - The tool answers back", "chat:where is demand?",
  "It can only answer from what the simulation actually computed, so it "
  "cannot contradict the screen behind it."),
 ("Act 5 - The tool answers back", "close_chat",
  "And it agrees with the banner. Paediatric area, eight to ten in the "
  "morning. It is reading the same simulation, so it cannot tell you a "
  "different story from the screen behind it."),

 # ---------------------------------------------------------------- Act 6
 ("Act 6 - Does it match reality?", "validation_overlay",
  "Everything I have shown you is worthless unless it reproduces your "
  "department. So here is the validation, and here is where I am going to be "
  "uncomfortable in public."),
 ("Act 6 - Does it match reality?", "none",
  "Four-hour performance. Fifty-six percent against your fifty-three. "
  "Twelve-hour waits, ten point nine against ten."),
 ("Act 6 - Does it match reality?", "none",
  "But the row I would look at is majors trolleys. Your patients on a trolley "
  "wait a median of seven hundred and twenty-five minutes. Twelve hours. "
  "The model says seven hundred and twenty-seven."),
 ("Act 6 - Does it match reality?", "none",
  "That is not a fitted number. That emerged from modelling the mechanism "
  "properly. A patient waiting for a bed occupies the trolley, not a doctor."),
 ("Act 6 - Does it match reality?", "none",
  "When we got that wrong, the model said two hundred and fifty minutes, and "
  "was confidently useless. The headline four-hour figure agreed the whole "
  "time, through compensating errors."),
 ("Act 6 - Does it match reality?", "none",
  "Every area is now within about ten percent except paediatrics, which runs "
  "twenty-six percent long. I do not yet know why, and I would rather say that "
  "than explain it away."),

 # ---------------------------------------------------------------- Act 7
 ("Act 7 - What it cannot do yet", "limits_overlay",
  "Four limitations. All of them are data or engine gaps, and none of them are "
  "hidden in a footnote. They are in the register you saw at the start."),
 ("Act 7 - What it cannot do yet", "none",
  "One. The seen within fifteen minutes tile. Please ignore it. It reads "
  "eighty-four percent against your forty-two."),
 ("Act 7 - What it cannot do yet", "none",
  "That is not the model being wrong, it is us measuring different things. "
  "Our clock starts at triage. Yours, for minors, starts at a clinician "
  "assessment thirty-seven minutes into the visit."),
 ("Act 7 - What it cannot do yet", "none",
  "Same word, different event. Until we align the definition, that tile is "
  "not comparable and should not be quoted."),
 ("Act 7 - What it cannot do yet", "none",
  "Two. Day of week does not exist in this model. Your own data shows Sunday "
  "discharges run at twenty-nine percent of Monday's."),
 ("Act 7 - What it cannot do yet", "none",
  "That weekend collapse in bed releases is probably the single biggest driver "
  "of your Monday exit block, and this engine literally cannot represent it. "
  "Every day is the same day. That is the most valuable thing we could "
  "build next."),
 ("Act 7 - What it cannot do yet", "none",
  "Three. Long-stay patients are invisible. Sixty percent of your occupied "
  "beds are held by patients staying seven days or more. The bed model has no "
  "compartment for that, so it is more optimistic about bed turnover "
  "than reality."),
 ("Act 7 - What it cannot do yet", "none",
  "Four. The rota is not yours. Staffing is a template scaled to your size, "
  "because workforce was out of scope. So treat any staffing recommendation "
  "as directional, not a roster."),
 ("Act 7 - What it cannot do yet", "none",
  "And one thing we need from you. Arrivals into each area, by hour. "
  "Everything else on the red list is closed."),
 ("Act 7 - What it cannot do yet", "closing",
  "What you have is a model that reproduces your four-hour position, your "
  "twelve-hour position, and your length of stay area by area. And that tells "
  "you honestly where it stops."),
 ("Act 7 - What it cannot do yet", "none",
  "I would rather show you that, than a demo where everything is green. "
  "Thank you."),
]
