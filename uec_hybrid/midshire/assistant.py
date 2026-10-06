"""
Ask My ED - another way into the SAME scenario workflow, not a separate source
of numbers.

Contract:
* Every number in a reply is read from a stored structured result (a run or a
  package search) for the scenario the user is looking at. The assistant
  formats; it never computes a figure of its own.
* A "what if" is parsed into a VALIDATED change (known roles, bounded counts,
  whole hours), applied to a copy of the current inputs through the one build
  pipeline, and simulated on the same seeds as the scenario. It is speculative:
  it never changes the saved baseline or the applied scenario.
* A target question starts (or reuses) the structured package search.
* Unsupported questions get an explicit "I can't answer that" with what it can do.
* Replies are plain text in plain operational language; the page renders them
  as text, never as HTML. No seeds, run ids or simulation terms in replies.
Fully offline and deterministic. No language model is used.
"""
from __future__ import annotations

import copy
import re

from . import config as mcfg
from . import metrics as M
from .packages import apply_lever, _clock, _count_words, _days_words
from .packages import ROLE_WORDS as ROLE_NAMES, SPACE_WORDS as SPACE_NAMES

NAME = "Ask My ED"

SUGGESTIONS = ["How are we doing?", "Where do patients wait longest?",
               "What if we add 2 nurses 08:00-20:00?",
               "What would it take to reach 90% within 4 hours?"]

HELP = ("You can ask how the department is doing, where patients wait longest, what a change "
        "would do (for example \"add 2 nurses 08:00-20:00\" or \"keep SDEC open until "
        "midnight\"), or what it would take to reach a target (for example \"what would it take "
        "to reach 90% within 4 hours?\").")

GLOSSARY = {
    "sdec": "SDEC is Same Day Emergency Care: patients who would otherwise be admitted are assessed and treated the same day. Here it takes patients from streaming and from RAT.",
    "rat": "RAT is Rapid Assessment and Treatment: a senior clinician sees patients early. Here that is ambulance arrivals and some walk-ins.",
    "dta": "A decision to admit is the point a clinician decides the patient needs an inpatient bed. The wait for the bed starts after it.",
    "decision to admit": "The point a clinician decides the patient needs an inpatient bed. The wait for the bed starts after it.",
    "lwbs": "Left without being seen: patients who leave before they are seen. They are counted separately from discharges.",
    "wte": "Whole-time equivalent: the extra paid hours divided by a full-time contract for that role.",
    "utc": "The Urgent Treatment Centre sees minor illness and injury. Here it is open 08:00 to midnight.",
    "four hour": "The share of patients who leave the emergency department within 4 hours of arriving, whether admitted, transferred or discharged. Time in SDEC counts.",
}

ROLE_WORDS = [
    (r"streaming nurses?|triage nurses?", "streaming_nurse"),
    (r"resus nurses?", "resus_nurse"),
    (r"sdec nurses?", "sdec_nurse"),
    (r"sdec doctors?|specialty doctors?", "sdec_doctor"),
    (r"utc (?:practitioners?|clinicians?|doctors?)|enps?|nurse practitioners?", "utc_practitioner"),
    (r"rat (?:consultants?|doctors?|seniors?)|senior assessors?", "rat_consultant"),
    (r"consultants?", "ed_consultant"),
    (r"registrars?", "em_registrar"),
    (r"(?:junior doctors?|shos?|doctors?)", "em_sho"),
    (r"(?:band ?6 )nurses?", "band6_nurse"),
    (r"(?:ed |band ?5 )?nurses?", "band5_nurse"),
    (r"porters?", "porter"),
]
SPACE_WORDS = [
    (r"(?:majors )?cubicles?|trolley spaces?", "cubicle"),
    (r"resus bays?", "resus_bay"),
    (r"utc rooms?", "utc_room"),
    (r"sdec chairs?|sdec spaces?", "sdec_chair"),
    (r"fit.to.sit (?:chairs?|spaces?)|ambulatory (?:chairs?|spaces?)", "fit_to_sit_chair"),
    (r"ct scanners?", "ct_scanner"),
    (r"x.?ray rooms?", "xray_room"),
    (r"handover bays?", "handover_bay"),
]
NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
       "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_N = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"


def _n(tok):
    return int(tok) if tok.isdigit() else NUM[tok]


def _window(q):
    m = re.search(r"(\d{1,2})(?::00)?\s*(?:-|to|until)\s*(\d{1,2})(?::00)?", q)
    if m:
        s, e = int(m.group(1)), int(m.group(2))
        if 0 <= s <= 23 and 0 <= e <= 24 and s != e:
            return s, e, None
    if "overnight" in q or "at night" in q or "night" in q:
        return 20, 8, None
    if "evening" in q:
        return 14, 24, None
    return 8, 20, "I assumed 08:00 to 20:00 (say, for example, '14:00-24:00' to choose the hours)"


def parse_change(question: str, inputs: dict):
    """Question -> (levers, notes) or (None, notes). Only known roles and
    spaces, counts 1-10, whole hours."""
    q = " " + question.lower().strip() + " "
    levers, notes = [], []
    days = "Mon-Fri" if "weekday" in q else ("Sat-Sun" if "weekend" in q else "Mon-Sun")
    for pat, space in SPACE_WORDS:
        m = re.search(rf"(?:add|extra|another|open|build)\s+{_N}\s+(?:more\s+|extra\s+|new\s+)?(?:{pat})", q) \
            or re.search(rf"{_N}\s+(?:more|extra|new)\s+(?:{pat})", q)
        if m:
            n = _n(m.group(1))
            if not 1 <= n <= 10:
                return None, ["I can test between 1 and 10 at a time"]
            if space not in inputs["capacity"]:
                notes.append(f"this department has no {space.replace('_', ' ')}")
                continue
            if days != "Mon-Sun" and "spaces are added for the whole week" not in notes:
                notes.append("spaces are added for the whole week")
            levers.append({"id": f"ask_{space}", "kind": "estate", "space": space, "add": n,
                           "title": f"adding {_count_words(n, SPACE_NAMES.get(space, space))}"})
    if not levers:
        for pat, role in ROLE_WORDS:
            m = re.search(rf"(?:add|extra|another|hire|put on)\s+{_N}\s+(?:more\s+|extra\s+)?(?:{pat})", q) \
                or re.search(rf"{_N}\s+(?:more|extra|additional)\s+(?:{pat})", q)
            if m:
                n = _n(m.group(1))
                if not 1 <= n <= 10:
                    return None, ["I can test between 1 and 10 at a time"]
                s, e, note = _window(q)
                if note:
                    notes.append(note)
                levers.append({"id": f"ask_{role}", "kind": "shift",
                               "title": f"adding {_count_words(n, ROLE_NAMES.get(role, role))}, "
                                        f"{_clock(s)} to {_clock(e, end=True)}, {_days_words(days)}",
                               "shift": {"role": role, "days": days, "start": s, "end": e, "count": n}})
                break
    m = re.search(rf"{_N}\s+(?:more|extra|new)\s+(?:inpatient\s+|ward\s+)?beds", q)
    if m:
        n = _n(m.group(1))
        if not 1 <= n <= 200:
            return None, ["I can test between 1 and 200 extra beds"]
        levers.append({"id": "ask_beds", "kind": "downstream", "param": "inpatient_beds", "add": n,
                       "estate_item": "inpatient_beds", "title": f"opening {n} more inpatient beds"})
    if re.search(r"sdec.*(open|until).*(midnight|24|late)", q) and "sdec" in inputs["areas"]["enabled"]:
        lv = copy.deepcopy(next(l for l in mcfg.fixture()["search"]["levers"] if l["id"] == "sdec_late"))
        lv["title"] = "keeping SDEC open until midnight"
        levers.append(lv)
    return (levers or None), notes


def _target(question: str):
    q = question.lower()
    if not re.search(r"what (?:would|will|does) it take|what .{0,40}(?:needed|need)|how (?:do|can|could) we (?:get|reach|hit)|changes? .{0,30}(?:get|reach)", q):
        return None
    m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", q)
    if not m:
        return None
    pct = float(m.group(1))
    mins = 240
    mm = re.search(r"(\d{1,2}|four|six|twelve)\s*hours?", q)
    if mm:
        h = {"four": 4, "six": 6, "twelve": 12}.get(mm.group(1)) or int(mm.group(1))
        mins = h * 60
    mm = re.search(r"(\d{2,4})\s*min", q)
    if mm:
        mins = int(mm.group(1))
    if not (0 < pct <= 100) or mins % 15 or not 15 <= mins <= 1440:
        return None
    mode = "workforce" if re.search(r"workforce only|staff(?:ing)? only|current estate", q) else (
        "estate" if re.search(r"estate only|space only|building", q) else "combined")
    return {"pct": pct, "minutes": mins, "mode": mode}


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _time_words(minutes) -> str:
    m = int(minutes)
    return f"{m // 60} hours" if m % 60 == 0 else f"{m} minutes"


def _vs_aim(value: float, pct: float) -> str:
    if value >= pct:
        return f"meeting the {pct:g}% target"
    return f"below the {pct:g}% target"


def _within(result: dict, minutes: int, day: int | None = None):
    from .runner import THRESHOLDS
    i = THRESHOLDS.index(int(minutes))
    if day is None:
        vals = [row[i] for row in result["within"]["by_rep"]]
        s = M.summarise(vals)
        return s["mean"] if s else None
    d = result["replay"]["days"][day]
    return d["within"][i]


def explain_position(result: dict, target: dict, scenario: dict, view: dict | None,
                     baseline: dict | None = None) -> str:
    """How the department is doing, for what is on screen: the selected day or
    a typical day."""
    from .optimise import wait_phrase
    within = _time_words(target["minutes"])
    rp = result.get("replay") or {}
    who = "" if scenario.get("id") in (None, "baseline") else f"With \"{scenario['name']}\", "
    if view and view.get("mode") == "replay" and rp.get("days") and view.get("day") is not None:
        d = max(0, min(int(view["day"]), len(rp["days"]) - 1))
        k = rp["days"][d]
        dayname = DAYS[int((rp["t0"] + d * 1440) // 1440) % 7]
        w = _within(result, target["minutes"], d)
        txt = (f"{who}on {dayname} {k['n_cohort']} patients arrived and {w:.1f}% left within {within}, "
               f"{_vs_aim(w, target['pct'])}. ")
        txt = txt[0].upper() + txt[1:]
        txt += f"{k['twelve_hour']:.1f}% were in the department for more than 12 hours."
        i = view.get("index")
        if i is not None and 0 <= int(i) < len(rp.get("times", [])):
            i = int(i)
            tt = rp["times"][i] % 1440
            txt += (f" At {int(tt // 60):02d}:{int(tt % 60):02d} there were {rp['census'][i]} patients "
                    f"in the department and {rp['waiting'][i]} of them were waiting.")
        return txt
    s = result["summary"]
    w = _within(result, target["minutes"])
    txt = f"{who}on a typical day {w:.1f}% of patients leave within {within}, {_vs_aim(w, target['pct'])}."
    txt = txt[0].upper() + txt[1:]
    if baseline is not None and scenario.get("id") not in (None, "baseline"):
        bw = _within(baseline, target["minutes"])
        txt += f" The baseline is {bw:.1f}%, so that is {w - bw:+.1f} points."
    if s.get("duration_median") and s["duration_median"].get("mean") is not None:
        txt += f" The typical patient spends {s['duration_median']['mean']:.0f} minutes in the department"
        txt += f", {s['twelve_hour']['mean']:.1f}% stay more than 12 hours"
        txt += f" and {s['lwbs']['mean']:.1f}% leave without being seen."
    top = (result.get("pressure") or [{}])[0].get("label")
    if top:
        txt += f" Most waiting time goes on {wait_phrase(top)}."
    return txt


def where_waits(result: dict) -> str:
    from .optimise import wait_phrase
    top = result["pressure"][:3]
    if not top:
        return "There was no waiting to report in this scenario."
    first = top[0]
    txt = (f"Most waiting time goes on {wait_phrase(first['label'])}: about "
           f"{first['patient_hours_per_day']:.0f} hours a day across all patients, which is "
           f"roughly {first['patient_hours_per_day'] / 24:.0f} patients waiting at any one time.")
    if len(top) > 1:
        rest = [f"{wait_phrase(x['label'])} ({x['patient_hours_per_day']:.0f} hours)" for x in top[1:]]
        txt += " Next come " + " and ".join(rest) + "."
    txt += " The Patient flow page shows each stage in detail."
    return txt


def format_whatif(base: dict, scen: dict, target: dict, notes: list, titles: list) -> str:
    from .optimise import wait_phrase
    from .runner import within_at
    b = within_at(base, target["minutes"]); s = within_at(scen, target["minutes"])
    d = M.paired_delta(b, s)
    sb, ss = M.summarise(b), M.summarise(s)
    change = "; ".join(titles)
    change = change[0].upper() + change[1:]
    m = int(target["minutes"])
    perf = f"{m // 60}-hour performance" if m % 60 == 0 else f"{m}-minute performance"
    noise = "ci_low" in d and d["ci_low"] <= 0 <= d["ci_high"]
    if abs(d["mean"]) < 0.05:
        txt = f"{change} makes no measurable difference to {perf} ({ss['mean']:.1f}% either way)."
    else:
        txt = (f"{change} {'improves' if d['mean'] > 0 else 'worsens'} {perf} from "
               f"{sb['mean']:.1f}% to {ss['mean']:.1f}% ({d['mean']:+.1f} points)")
        txt += (f", {_vs_aim(ss['mean'], target['pct'])}." if ss["mean"] >= target["pct"]
                else f", still below the {target['pct']:g}% target.")
        if noise:
            txt += " That is within the normal week-to-week variation, so it may not make a real difference."
    lw = M.paired_delta([r["lwbs"] for r in base["reps"]], [r["lwbs"] for r in scen["reps"]])
    if lw and abs(lw["mean"]) >= 0.1:
        txt += (f" Fewer patients leave without being seen ({abs(lw['mean']):.1f} points)." if lw["mean"] < 0
                else f" More patients leave without being seen (+{lw['mean']:.1f} points).")
    top = (scen.get("pressure") or [{}])[0].get("label")
    if top and ss["mean"] < target["pct"]:
        txt += f" The main remaining constraint is {wait_phrase(top)}."
    if notes:
        txt += " Note: " + "; ".join(notes) + "."
    txt += " This was a test only; nothing has been saved."
    return txt


def answer(message: str, ctx: dict) -> dict:
    """``ctx`` (from the server): scenario, inputs, result (or None), target,
    view, search(target) -> cached search or None, start_search(target, mode),
    start_whatif(inputs, titles, notes)."""
    q = (message or "").strip()
    if not q:
        return {"reply": HELP, "intent": "help"}
    if len(q) > 500:
        return {"reply": "That question is too long. Please ask in a sentence or two.", "intent": "error"}
    ql = q.lower()
    if re.fullmatch(r"\s*(help|hi|hello|what can (?:you|i) (?:do|ask)( you)?|how does this work)\s*[.!?]*\s*", ql):
        return {"reply": HELP, "intent": "help"}
    t = _target(q)
    if t:
        hit = ctx["search"](t)
        if hit:
            return {"reply": hit["headline"] + " Workforce & investment shows the extra shifts, "
                    "space and costs.",
                    "intent": "target", "search_key": hit.get("search_key"), "target": t}
        job = ctx["start_search"](t)
        return {"reply": f"I'm looking for the lowest-cost set of changes that gets "
                f"{t['pct']:g}% of patients out within {_time_words(t['minutes'])}. This takes a few "
                f"minutes; you can follow it below.",
                "intent": "target", "job": job, "target": t}
    if re.search(r"what if|\badd\b|\bextra\b|\bopen\b.*(sdec|until)|more (beds|cubicles|nurses|doctors)", ql):
        levers, notes = parse_change(q, ctx["inputs"])
        if not levers:
            return {"reply": "I couldn't turn that into a change I can test. " + (
                ("Note: " + "; ".join(notes) + ". ") if notes else "") + HELP,
                "intent": "unsupported"}
        new = ctx["inputs"]
        titles = []
        for lv in levers:
            new, rec = apply_lever(new, lv)
            titles.append(lv["title"])
        job = ctx["start_whatif"](new, titles, notes)
        return {"reply": f"Testing: {'; '.join(titles)}. This is a test only; nothing will be saved.",
                "intent": "what_if", "job": job}
    if re.search(r"where.*wait|bottleneck|pinch|most waiting|queue|stuck|longest", ql):
        if not ctx["result"]:
            return {"reply": "This scenario hasn't been run yet. Run it first and ask me again.", "intent": "where"}
        return {"reply": where_waits(ctx["result"]), "intent": "where"}
    if re.search(r"how are we|position|explain|overview|summary|performance|doing", ql):
        if not ctx["result"]:
            return {"reply": "This scenario hasn't been run yet. Run it first and ask me again.", "intent": "explain"}
        return {"reply": explain_position(ctx["result"], ctx["target"], ctx["scenario"], ctx.get("view"),
                                          ctx.get("baseline_result")),
                "intent": "explain"}
    for term in sorted(GLOSSARY, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", ql):
            return {"reply": GLOSSARY[term],
                    "intent": "glossary"}
    return {"reply": "I can't answer that from this model. " + HELP, "intent": "unsupported"}
