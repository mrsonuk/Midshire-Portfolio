"""
Ask Qbo ED - another way into the SAME scenario workflow, not a separate source
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
* Unsupported questions get an explicit "I can't do that" with what it can do.
* Replies are plain text; the page renders them as text, never as HTML.
Fully offline and deterministic. No language model is used.
"""
from __future__ import annotations

import copy
import re

from . import config as mcfg
from . import metrics as M
from .packages import apply_lever

NAME = "Ask Qbo ED"

HELP = ("I can: explain the position on screen (\"how are we doing?\"); show where waits "
        "build up (\"where do patients wait longest?\"); test a change (\"what if we add 2 "
        "nurses 08:00-20:00?\", \"add 4 cubicles\", \"add a resus bay\", \"keep SDEC open until "
        "midnight\"); and find a package for a target (\"what workforce and space changes "
        "would get 90% through within four hours?\"). Every number I give comes from the "
        "simulation results for the scenario you are viewing.")

GLOSSARY = {
    "sdec": "Same Day Emergency Care: assessment and treatment the same day for patients who would otherwise be admitted. Here it takes patients from streaming and from RAT.",
    "rat": "Rapid Assessment and Treatment: a senior clinician assesses patients early - here ambulance arrivals, and walk-ins streamed to it.",
    "dta": "Decision to admit: the moment a clinician decides the patient needs an inpatient bed. It is an event (counted), not a place patients wait; waiting for the bed comes after it.",
    "decision to admit": "The moment a clinician decides the patient needs an inpatient bed. It is an event (counted), not a place patients wait; waiting for the bed comes after it.",
    "lwbs": "Left without being seen: patients who leave before being seen. Kept separate from discharges and used as a guardrail.",
    "wte": "Whole-time equivalent: extra paid hours divided by the role's contracted weekly hours.",
    "utc": "Urgent Treatment Centre: the minors stream (open 08:00-24:00 here).",
    "four hour": "The share of eligible adult attendances completed within the target time, from arrival to leaving the ED (SDEC time counts inside the ED).",
    "wip": "Work in progress: patients still in the department when a simulated week ends.",
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
    return 8, 20, "assumed 08:00-20:00 (say e.g. '14:00-24:00' to set the hours)"


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
                return None, ["counts must be between 1 and 10"]
            if space not in inputs["capacity"]:
                notes.append(f"this scenario has no {space.replace('_', ' ')}")
                continue
            levers.append({"id": f"ask_{space}", "kind": "estate", "space": space, "add": n,
                           "title": f"+{n} {space.replace('_', ' ')}{'s' if n > 1 else ''} (with any staff needed to open them)"})
    if not levers:
        for pat, role in ROLE_WORDS:
            m = re.search(rf"(?:add|extra|another|hire|put on)\s+{_N}\s+(?:more\s+|extra\s+)?(?:{pat})", q) \
                or re.search(rf"{_N}\s+(?:more|extra|additional)\s+(?:{pat})", q)
            if m:
                n = _n(m.group(1))
                if not 1 <= n <= 10:
                    return None, ["counts must be between 1 and 10"]
                s, e, note = _window(q)
                if note:
                    notes.append(note)
                levers.append({"id": f"ask_{role}", "kind": "shift",
                               "title": f"+{n} {role.replace('_', ' ')} {s:02d}:00-{e:02d}:00 {days}",
                               "shift": {"role": role, "days": days, "start": s, "end": e, "count": n}})
                break
    m = re.search(rf"{_N}\s+(?:more|extra|new)\s+(?:inpatient\s+|ward\s+)?beds", q)
    if m:
        n = _n(m.group(1))
        if not 1 <= n <= 200:
            return None, ["bed changes must be between 1 and 200"]
        levers.append({"id": "ask_beds", "kind": "downstream", "param": "inpatient_beds", "add": n,
                       "estate_item": "inpatient_beds", "title": f"+{n} new inpatient beds"})
    if re.search(r"sdec.*(open|until).*(midnight|24|late)", q) and "sdec" in inputs["areas"]["enabled"]:
        lv = next(l for l in mcfg.fixture()["search"]["levers"] if l["id"] == "sdec_late")
        levers.append(copy.deepcopy(lv))
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


def _fmt(v, unit="%", dp=1):
    if v is None:
        return "not available"
    return f"{v:.{dp}f}{unit}"


def explain_position(result: dict, target: dict, scenario: dict, view: dict | None) -> str:
    s = result["summary"]
    within = None
    try:
        from .runner import target_status
        ts = target_status(result, target)
        within = ts["value"]
    except Exception:
        ts = None
    parts = [f"Scenario \"{scenario['name']}\", {result['replications']} simulated weeks "
             f"(seeds {result['seeds'][0]}-{result['seeds'][-1]})."]
    if within:
        parts.append(f"{within['mean']:.1f}% of adult attendances completed within "
                     f"{target['minutes']} minutes (range {within['min']:.1f}-{within['max']:.1f}% "
                     f"across weeks) against the {target['pct']:g}% planning target: "
                     f"{ts['status']}.")
    parts.append(f"Median time in the department {_fmt(s['duration_median']['mean'], ' min', 0)}; "
                 f"over 12 hours from arrival {_fmt(s['twelve_hour']['mean'])}; "
                 f"left without being seen {_fmt(s['lwbs']['mean'])}; "
                 f"about {s['wip_end']['mean']:.0f} patients still in the department when a week ends.")
    rp = result.get("replay")
    if view and rp:
        i = int(view.get("index", 0))
        if 0 <= i < len(rp["times"]):
            t = rp["times"][i]
            day = int((t - rp["t0"]) // 1440) + 1
            hh = int((t % 1440) // 60); mm = int(t % 60)
            parts.append(f"In the replay (simulated day {day}, {hh:02d}:{mm:02d}, one simulated week "
                         f"- not an average): {rp['census'][i]} patients in the department, "
                         f"{rp['waiting'][i]} of them waiting.")
    return " ".join(parts)


def where_waits(result: dict) -> str:
    top = result["pressure"][:3]
    if not top:
        return "No waiting was recorded in this run."
    bits = [f"{p['label']} ({p['patient_hours_per_day']:.0f} waiting patient-hours a day)" for p in top]
    return ("Measured as waiting patient-hours per day (the number of people waiting, added up "
            "over time), waits build up most at: " + "; ".join(bits) + ". This is the run's own "
            "measure, not a judgement made in advance - see the Patient flow screen for each stage.")


def format_whatif(base: dict, scen: dict, target: dict, notes: list, titles: list) -> str:
    from .runner import within_at
    b = within_at(base, target["minutes"]); s = within_at(scen, target["minutes"])
    d = M.paired_delta(b, s)
    sb, ss = M.summarise(b), M.summarise(s)
    txt = (f"Tested (not saved): {'; '.join(titles)}. On the same {d['n']} simulated weeks, "
           f"completed within {target['minutes']} minutes goes from {sb['mean']:.1f}% to "
           f"{ss['mean']:.1f}%: a change of {d['mean']:+.1f} percentage points")
    if "ci_low" in d:
        txt += f" (simulation-noise interval {d['ci_low']:+.1f} to {d['ci_high']:+.1f})"
    txt += "."
    if "ci_low" in d and d["ci_low"] <= 0 <= d["ci_high"]:
        txt += " That is within the simulation noise: it may have no real effect - a change that is not the binding constraint often doesn't."
    lw = M.paired_delta([r["lwbs"] for r in base["reps"]], [r["lwbs"] for r in scen["reps"]])
    if lw:
        txt += f" Walk-outs change by {lw['mean']:+.1f} points."
    if notes:
        txt += " Note: " + "; ".join(notes) + "."
    return txt


def answer(message: str, ctx: dict) -> dict:
    """``ctx`` (from the server): scenario, inputs, result (or None), target,
    view, search(target) -> cached search or None, start_search(target, mode),
    start_whatif(inputs, titles, notes)."""
    q = (message or "").strip()
    if not q:
        return {"reply": HELP, "intent": "help"}
    if len(q) > 500:
        return {"reply": "That question is too long - please ask in a sentence or two.", "intent": "error"}
    ql = q.lower()
    t = _target(q)
    if t:
        hit = ctx["search"](t)
        if hit:
            return {"reply": hit["headline"] + " Open \"Workforce & investment\" to see the proposed "
                    "rota rows, extra hours, WTE and costs, and the search limits.",
                    "intent": "target", "search_key": hit.get("search_key"), "target": t}
        job = ctx["start_search"](t)
        return {"reply": f"I've started the package search for {t['pct']:g}% within {t['minutes']} "
                f"minutes ({t['mode']} changes). It re-runs the full model for every package it tries, "
                f"so it takes a few minutes - progress is shown below. Ask again when it finishes, "
                f"or open Workforce & investment.",
                "intent": "target", "job": job, "target": t}
    if re.search(r"what if|\badd\b|\bextra\b|\bopen\b.*(sdec|until)|more (beds|cubicles|nurses|doctors)", ql):
        levers, notes = parse_change(q, ctx["inputs"])
        if not levers:
            return {"reply": "I couldn't turn that into a change I can test. " + (
                ("Understood: " + "; ".join(notes) + ". ") if notes else "") + HELP,
                "intent": "unsupported"}
        new = ctx["inputs"]
        titles = []
        for lv in levers:
            new, rec = apply_lever(new, lv)
            titles.append(lv["title"])
        job = ctx["start_whatif"](new, titles, notes)
        return {"reply": f"Testing: {'; '.join(titles)}. This is a speculative run on a copy of "
                         f"the scenario - nothing is saved.", "intent": "what_if", "job": job}
    if re.search(r"where.*wait|bottleneck|pinch|most waiting|queue|stuck|longest", ql):
        if not ctx["result"]:
            return {"reply": "This scenario has not been simulated yet - run it first.", "intent": "where"}
        return {"reply": where_waits(ctx["result"]), "intent": "where"}
    if re.search(r"how are we|position|explain|overview|summary|performance|doing", ql):
        if not ctx["result"]:
            return {"reply": "This scenario has not been simulated yet - run it first.", "intent": "explain"}
        return {"reply": explain_position(ctx["result"], ctx["target"], ctx["scenario"], ctx.get("view")),
                "intent": "explain"}
    for term in sorted(GLOSSARY, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", ql):
            return {"reply": f"{term.upper() if len(term) <= 4 else term.capitalize()}: {GLOSSARY[term]}",
                    "intent": "glossary"}
    return {"reply": "I can't answer that from this model. " + HELP, "intent": "unsupported"}
