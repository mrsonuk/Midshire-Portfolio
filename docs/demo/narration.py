# -*- coding: utf-8 -*-
"""Narration for the CUH demo recording.

One short clip per scene beat, in plain English - the way you would say it to a
manager standing next to you, not the way you would write it down. Short
sentences, contractions, one idea per clip. The clip text is also the subtitle,
so what a viewer hears and what they read can never diverge.

Every figure quoted here was read off the running product, not from notes.
"""

STEPS = {
    1: "What this is",
    2: "Loading Cambridge's own data",
    3: "The control tower",
    4: "Where it actually hurts",
    5: "Asking it questions",
    6: "Does it match reality?",
    7: "What it can't do yet",
}

# (step, action, text)
SEGMENTS = [
 (0, "titlecard",
  "Cambridge University Hospitals. The emergency department control tower."),

 # ------------------------------------------------ 1. what this is
 (1, "none",
  "Every emergency department gets asked the same question. If we had one more "
  "cubicle, or one more doctor, what would it actually buy us?"),
 (1, "none",
  "Normally you can't answer that. You try it, and you wait a quarter to see "
  "what happened."),
 (1, "hi:header",
  "This is a simulation of Addenbrooke's emergency department. Not a generic "
  "one. Yours."),
 (1, "none",
  "Your areas. Your opening hours. Your cubicle counts. Your arrival pattern, "
  "hour by hour."),
 (1, "none",
  "It runs a full week of your department in about ten seconds."),
 (1, "none",
  "I'll show you three things. That it's built on your data. That it matches "
  "what your department actually does. And where it doesn't, and why."),

 # ------------------------------------------------ 2. loading the data
 (2, "goto_setup",
  "Let's load Cambridge from scratch."),
 (2, "hi:#trustPick",
  "Two ways in. This dropdown pulls a trust from published NHS figures. That's "
  "the cold start for anyone in England."),
 (2, "hi:#trustFile",
  "For Cambridge we've got something better. The filled workbook."),
 (2, "upload_workbook",
  "One spreadsheet. That just configured the whole department."),
 (2, "hi:#importStatus",
  "Behind it sit thirty-two extracts your team sent us, and nine national "
  "publications."),
 (2, "none",
  "It set your arrival curve for all twenty-four hours of the day, from "
  "forty-six thousand real arrivals."),
 (2, "none",
  "Your acuity mix. Two and a half percent resus. Nineteen percent majors "
  "trolleys. Forty-two percent majors ambulant."),
 (2, "none",
  "Ambulance at nineteen percent. Paediatrics at thirteen."),
 (2, "none",
  "And your real capacity. Thirty-four majors cubicles. Six resus bays. "
  "Fifteen U-T-C rooms. Twelve paediatric cubicles. Your ops team gave us "
  "those in August."),
 (2, "status_overlay",
  "This is the honesty register. Thirty-six inputs, one row each. I'd like you "
  "to hold me to it."),
 (2, "none",
  "Green is real. Twelve from your C-HEQS extracts. Seven from national "
  "publications. Six from your ops return."),
 (2, "none",
  "Amber is an assumption. There are two."),
 (2, "none",
  "Grey is data we hold but the engine can't use yet. Seven of those."),
 (2, "none",
  "Red is what we still need from you. There's one red row. One. We'll come "
  "back to it at the end."),

 # ------------------------------------------------ 3. the control tower
 (3, "goto_tower",
  "Here's the department running. Four hundred attendances a day."),
 (3, "hi:.tiles",
  "Five tiles. Four-hour performance, typically fifty-six percent."),
 (3, "none",
  "The dot shows the spread across simulated weeks. A good week, sixty-two. A "
  "tough week, fifty."),
 (3, "none",
  "That range matters more than the middle number. It's the difference between "
  "a department that's coping and one that isn't."),
 (3, "none",
  "Twelve-hour waits, ten percent. Handover within forty-five minutes, "
  "ninety-three. Walked out unseen, one percent."),
 (3, "hi:#dataStatus",
  "And this line is on every screen. What's real, and in amber, what's still "
  "an assumption."),
 (3, "none",
  "It tells you what it doesn't know, right next to the answer. That's "
  "deliberate."),

 # ------------------------------------------------ 4. the flow map
 (4, "scroll_to:#flow",
  "Here's the whole department in one picture."),
 (4, "none",
  "Every box is an area you actually run."),
 (4, "none",
  "There's no C-D-U and no E-E-M-A-C, because Cambridge doesn't have them. "
  "The model matches your department, not a textbook one."),
 (4, "none",
  "The number is how many patients are in that area. Green is flowing, amber "
  "is busy, red is stuck."),
 (4, "slider:4",
  "Four in the morning. Quiet."),
 (4, "slider_sweep:10",
  "By ten it's filling up."),
 (4, "slider_sweep:14",
  "By two, the cubicles are full and the waits are building."),
 (4, "none",
  "That's your own arrival curve driving it. Not an average. The real shape of "
  "your day."),
 (4, "hi:#hourPinch",
  "And the pinch point moves with the clock."),
 (4, "none",
  "So, where's our bottleneck, is the wrong question. Where is it at two on a "
  "Monday, is the right one."),
 (4, "click_area:ED ambulatory (fit to sit)",
  "Click any area and it opens up."),
 (4, "none",
  "E-D ambulatory, at two o'clock. Twenty-one people in there. Ninety-seven "
  "minutes average wait. Eighty-four percent of capacity."),
 (4, "none",
  "Eight hundred and forty-two patients that week. Busiest at seven in the "
  "evening."),
 (4, "none",
  "It tells you who's on. Eighteen doctors. And what the space is. Seventeen "
  "fit-to-sit chairs."),
 (4, "none",
  "And where those patients came from, and where they go next."),
 (4, "close_drill",
  "Now, the banner gives you two lines, and they're not the same area."),
 (4, "none",
  "Across the working day the pinch is paediatrics. Two hundred and forty-seven "
  "minutes, worst between eight and ten in the morning."),
 (4, "hi:.fmnode[data-label=\"ED ambulatory (fit to sit)\"]",
  "But E-D ambulatory loses the most hours in total. Ninety-seven minutes each, "
  "times eight hundred and forty-two people."),
 (4, "none",
  "One thousand three hundred and fifty-seven patient-hours, in a week."),
 (4, "none",
  "Two different questions. Where does it hurt most. And where does it cost "
  "the most. They don't have to give the same answer."),

 # ------------------------------------------------ 5. asking it questions
 (5, "recommend",
  "Now the part I find most useful."),
 (5, "none",
  "It's simulating fourteen changes. More doctors. More nurses. More chairs. "
  "Longer opening hours. More ward beds."),
 (5, "none",
  "Each one against the same weeks as the baseline, so the comparison is fair. "
  "That's why it takes a moment - it's running your department fourteen more "
  "times."),
 (5, "wait_rec",
  "Fourteen tried. Thirteen thrown out as noise."),
 (5, "none",
  "One recommendation. Add four fit-to-sit chairs. Worth five point seven "
  "points on the four-hour standard."),
 (5, "none",
  "Look where those chairs are. E-D ambulatory. The area losing the most hours."),
 (5, "none",
  "Nobody pointed it at that area. It found it by simulating."),
 (5, "none",
  "And it's capacity, not staffing. It isn't reaching for, hire more people."),
 (5, "scroll_to:#askQ",
  "The thirteen it rejected matter just as much. A tool that recommends "
  "something every time you ask is guessing."),
 (5, "whatif:add 2 doctors",
  "You can also just ask it, in plain English. Add two doctors."),
 (5, "none",
  "About one point. Against four chairs at five point seven."),
 (5, "scroll_to:#askQ",
  "That's counter-intuitive, and it's hard to see in a spreadsheet. The "
  "constraint was never the doctors."),
 (5, "whatif:what would it take to reach 90% in 4 hours?",
  "This one's a goal question. What would it take to hit ninety percent?"),
 (5, "none",
  "It stacks changes until it hits the target, or runs out of things that "
  "clear the noise."),
 (5, "none",
  "I'll tell you now, it doesn't get there. Sixty point eight, from a "
  "fifty-five point three baseline."),
 (5, "none",
  "And it says so in writing. The rest needs levers outside this search."),
 (5, "none",
  "A tool that told you ninety percent was two nurses away would be lying to "
  "you."),
 (5, "chat:where is the pinch point?",
  "There's a chatbot too, on the same numbers."),
 (5, "chat:where is demand?",
  "Paediatric area, eight to ten. The same answer the banner gave."),
 (5, "close_chat",
  "And demand. About four hundred a day, heaviest between eleven and two."),
 (5, "none",
  "It can only answer from what the simulation computed. It can't contradict "
  "the screen behind it."),

 # ------------------------------------------------ 6. validation
 (6, "validation_overlay",
  "None of this matters unless it reproduces your department."),
 (6, "none",
  "So here's the validation. And here's where I'm going to be uncomfortable in "
  "public."),
 (6, "none",
  "Four-hour. Fifty-six percent, against your fifty-three."),
 (6, "none",
  "Twelve-hour waits. Ten point nine, against ten."),
 (6, "none",
  "Handover is optimistic. Ninety-two against eighty-four. That one's on my "
  "list, not yours."),
 (6, "none",
  "But look at majors trolleys. Your patients on a trolley wait a median of "
  "seven hundred and twenty-five minutes. Twelve hours."),
 (6, "none",
  "The model says seven hundred and twenty-seven."),
 (6, "none",
  "That's not a fitted number. It came out of getting the mechanism right. A "
  "patient waiting for a bed is holding a trolley, not a doctor."),
 (6, "none",
  "When we had that wrong, the model said two hundred and fifty. And the "
  "four-hour figure still looked fine. Compensating errors."),
 (6, "none",
  "Every area is within about ten percent now, except paediatrics, which runs "
  "twenty-six percent long. I don't know why yet, and I'd rather say that."),

 # ------------------------------------------------ 7. limits
 (7, "limits_overlay",
  "Four limitations. None of them hidden in a footnote."),
 (7, "none",
  "One. The seen-within-fifteen-minutes tile. Please ignore it."),
 (7, "none",
  "It reads eighty-four percent against your forty-two. We're measuring "
  "different things."),
 (7, "none",
  "Our clock starts at triage. Yours, for minors, starts at a clinician "
  "assessment thirty-seven minutes in. Same word, different event."),
 (7, "none",
  "Two. Day of week doesn't exist in this model."),
 (7, "none",
  "Your own data shows Sunday discharges at twenty-nine percent of Monday's."),
 (7, "none",
  "That's probably your single biggest driver of Monday exit block, and this "
  "engine can't represent it. Every day is the same day."),
 (7, "none",
  "That's the most valuable thing we could build next."),
 (7, "none",
  "Three. Long-stay patients are invisible. Sixty percent of your occupied "
  "beds are held by people staying a week or more, and the bed model has no "
  "compartment for them."),
 (7, "none",
  "Four. The rota isn't yours. It's a template scaled to your size, because "
  "workforce was out of scope. So treat any staffing suggestion as "
  "directional, not a roster."),
 (7, "none",
  "And one thing we need from you. Arrivals into each area, by hour. "
  "Everything else on the red list is closed."),
 (7, "closing",
  "So. It reproduces your four-hour position, your twelve-hour position, and "
  "your length of stay area by area. And it tells you where it stops."),
 (7, "none",
  "I'd rather show you that than a demo where everything's green. Thank you."),
]
