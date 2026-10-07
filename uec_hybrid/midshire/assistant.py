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
from .optimise import num
from .packages import ROLE_WORDS as ROLE_NAMES, SPACE_WORDS as SPACE_NAMES

NAME = "Ask My ED"

SUGGESTIONS = ["How are we doing?", "Where do patients wait longest?",
               "What if we add 2 nurses 08:00-20:00?",
               "What would it take to reach 90% within 4 hours?",
               "What could we do with no extra resources?"]

HELP = ("You can ask how the department is doing, where patients wait longest, what a change "
        "would do (for example \"add 2 nurses 08:00-20:00\" or \"keep SDEC open until "
        "midnight\"), or what it would take to reach a target (for example \"what would it take "
        "to reach 90% within 4 hours?\", or \"... with no extra resources?\").")

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
    mode = "no_extra" if NO_EXTRA.search(q) else (
        "workforce" if re.search(r"workforce only|staff(?:ing)? only|current estate", q) else (
            "estate" if re.search(r"estate only|space only|building", q) else "combined"))
    return {"pct": pct, "minutes": mins, "mode": mode}


# "no budget" in the ways people say it
NO_EXTRA = re.compile(r"no (?:extra |more |new |additional )?(?:budget|money|funding|resources?|cost|staff|beds)|"
                      r"without (?:any )?(?:extra |more |new |additional )?(?:budget|money|funding|resources?|staff|beds|cost)|"
                      r"existing (?:staff|resources|rota)|cost.?neutral|for free")

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


def _day_index(result: dict, view: dict | None):
    """The selected day on screen, or None for a typical day."""
    rp = result.get("replay") or {}
    if view and view.get("mode") == "replay" and rp.get("days") and view.get("day") is not None:
        return max(0, min(int(view["day"]), len(rp["days"]) - 1))
    return None


def _day_name(result: dict, d: int) -> str:
    rp = result["replay"]
    return DAYS[int((rp["t0"] + d * 1440) // 1440) % 7]


def _clock(minutes) -> str:
    t = int(minutes) % 1440
    return f"{t // 60:02d}:{t % 60:02d}"


def explain_position(result: dict, target: dict, scenario: dict, view: dict | None,
                     baseline: dict | None = None) -> str:
    """How the department is doing, for what is on screen: the selected day or
    a typical day. The figures and rounding match the Overview."""
    from .optimise import wait_phrase
    within = _time_words(target["minutes"])
    rp = result.get("replay") or {}
    who = "" if scenario.get("id") in (None, "baseline") else f"With \"{scenario['name']}\", "
    other = baseline is not None and scenario.get("id") not in (None, "baseline")
    d = _day_index(result, view)
    if d is not None:
        k = rp["days"][d]
        dayname = _day_name(result, d)
        w = _within(result, target["minutes"], d)
        txt = (f"{who}on {dayname} {k['n_cohort']} patients arrived and {num(w, 1)}% left within {within}, "
               f"{_vs_aim(w, target['pct'])}.")
        txt = txt[0].upper() + txt[1:]
        if other and (baseline.get("replay") or {}).get("days"):
            txt += f" The baseline on the same day was {num(_within(baseline, target['minutes'], d), 1)}%."
        if k.get("duration_median") is not None:
            txt += f" The typical patient spent {num(k['duration_median'])} minutes in the department"
            txt += f" and {num(k['twelve_hour'], 1)}% were there for more than 12 hours."
        i = view.get("index")
        if i is not None and 0 <= int(i) < len(rp.get("times", [])):
            i = int(i)
            txt += (f" At {_clock(rp['times'][i])} there were {rp['census'][i]} patients "
                    f"in the department and {rp['waiting'][i]} of them were waiting.")
        return txt
    s = result["summary"]
    w = _within(result, target["minutes"])
    per_day = (s.get("per_day") or {}).get("mean")
    arrive = f"about {num(per_day)} patients arrive and " if per_day else ""
    txt = f"{who}on a typical day {arrive}{num(w, 1)}% leave within {within}, {_vs_aim(w, target['pct'])}."
    txt = txt[0].upper() + txt[1:]
    if other:
        bw = _within(baseline, target["minutes"])
        txt += f" The baseline is {num(bw, 1)}%, so that is {num(w - bw, 1, sign=True)} points."
    if s.get("duration_median") and s["duration_median"].get("mean") is not None:
        txt += f" The typical patient spends {num(s['duration_median']['mean'])} minutes in the department"
        txt += f", {num(s['twelve_hour']['mean'], 1)}% stay more than 12 hours"
        txt += f" and {num(s['lwbs']['mean'], 1)}% leave without being seen."
    h = (view or {}).get("hour")
    prof = result.get("profile") or {}
    if h is not None and 0 <= int(h) < 24 and prof.get("census_avg"):
        h = int(h)
        txt += (f" At {h:02d}:00 there are about {num(prof['census_avg'][h])} patients in the department "
                f"and {num(prof['waiting_avg'][h])} of them are waiting.")
    top = (result.get("pressure") or [{}])[0].get("label")
    if top:
        txt += f" Most waiting time goes on {wait_phrase(top)}."
    return txt


def _waiting_by_stage(result: dict, day: int | None) -> list[tuple[str, float]]:
    """Hours spent waiting at each stage, added up across all patients: for a
    typical day the daily average, for a selected day that day only. The same
    calculation as "Where waits build up" on the Overview."""
    by: dict[str, float] = {}
    if day is None:
        for p in result.get("pressure") or []:
            by[p["label"]] = by.get(p["label"], 0.0) + p["patient_hours_per_day"]
    else:
        table = mcfg.state_table()
        a = day * 96
        for key, ser in ((result.get("replay") or {}).get("states") or {}).items():
            node, _, phase = key.partition("|")
            st = table.get((node, phase))
            if not st or st["kind"] != "waiting":
                continue
            tot = sum(v or 0 for v in ser[a:a + 96]) * 0.25
            if tot > 0:
                by[st["label"]] = by.get(st["label"], 0.0) + tot
    return sorted(by.items(), key=lambda kv: -kv[1])


def where_waits(result: dict, view: dict | None = None) -> str:
    from .optimise import wait_phrase
    d = _day_index(result, view)
    top = _waiting_by_stage(result, d)[:3]
    if not top:
        return "There was no waiting to report in this scenario."
    (label, hours), rest = top[0], top[1:]
    if d is None:
        txt = (f"On a typical day most waiting time goes on {wait_phrase(label)}: about {num(hours)} hours a "
               f"day across all patients, which is roughly {num(hours / 24)} patients waiting at any one time.")
    else:
        txt = (f"On {_day_name(result, d)} most waiting time went on {wait_phrase(label)}: about {num(hours)} "
               f"hours across all patients, which is roughly {num(hours / 24)} patients waiting at any one time.")
    if rest:
        txt += (" Next come " if d is None else " Next came ") + " and ".join(
            f"{wait_phrase(lb)} ({num(hr)} hours)" for lb, hr in rest) + "."
    txt += " The Patient flow page shows each stage in detail."
    return txt


def format_whatif(base: dict, scen: dict, target: dict, notes: list, titles: list) -> str:
    from .optimise import perf_words, wait_phrase
    from .runner import within_at
    b = within_at(base, target["minutes"]); s = within_at(scen, target["minutes"])
    d = M.paired_delta(b, s)
    sb, ss = M.summarise(b), M.summarise(s)
    change = "; ".join(titles)
    change = change[0].upper() + change[1:]
    perf = perf_words(target["minutes"])
    noise = "ci_low" in d and d["ci_low"] <= 0 <= d["ci_high"]
    if abs(d["mean"]) < 0.05:
        txt = f"{change} makes no measurable difference to {perf} on a typical day ({num(ss['mean'], 1)}% either way)."
    else:
        txt = (f"{change} {'improves' if d['mean'] > 0 else 'worsens'} {perf} on a typical day from "
               f"{num(sb['mean'], 1)}% to {num(ss['mean'], 1)}% ({num(d['mean'], 1, sign=True)} points)")
        txt += (f", {_vs_aim(ss['mean'], target['pct'])}." if ss["mean"] >= target["pct"]
                else f", still below the {target['pct']:g}% target.")
        if noise:
            txt += " That is within the normal week-to-week variation, so it may not make a real difference."
    lw = M.paired_delta([r["lwbs"] for r in base["reps"]], [r["lwbs"] for r in scen["reps"]])
    if lw and abs(lw["mean"]) >= 0.1:
        txt += (f" Fewer patients leave without being seen ({num(abs(lw['mean']), 1)} points)." if lw["mean"] < 0
                else f" More patients leave without being seen (+{num(lw['mean'], 1)} points).")
    top = (scen.get("pressure") or [{}])[0].get("label")
    if top and ss["mean"] < target["pct"]:
        txt += f" The main remaining constraint is {wait_phrase(top)}."
    if notes:
        txt += " Note: " + "; ".join(notes) + "."
    txt += " This was a test only; nothing has been saved."
    return txt


def _retest(hit: dict) -> str:
    """The page's re-test sentence for a search's best package (not-reached
    outcomes; a met verdict already says whether it held up)."""
    if hit.get("outcome") != "not_reached":
        return ""
    rec = hit.get("recommended") or {}
    v = next((x for x in (hit.get("validation") or {}).get("packages", []) if x.get("ids") == rec.get("ids")), None)
    d = (v or {}).get("delta_vs_baseline_pts")
    if not d:
        return ""
    if d.get("ci_low") is not None and d["ci_low"] > 0:
        return f" We re-tested this package on different weeks and the improvement held up ({num(d['mean'], 1, sign=True)} points)."
    if d["mean"] > 0:
        return (f" On different test weeks the improvement was smaller ({num(d['mean'], 1, sign=True)} points) "
                f"and could be down to chance.")
    return " On different test weeks this package made no clear difference, so treat the result with caution."


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
    if not t and NO_EXTRA.search(ql) and re.search(r"what (?:can|could|would|should)|how (?:can|could|do|would) we|improve|better|optimi", ql):
        # "what could we do with no extra resources?": the current target, nothing added
        tg = ctx["target"]
        t = {"pct": float(tg["pct"]), "minutes": int(tg["minutes"]), "mode": "no_extra"}
    if t:
        hit = ctx["search"](t)
        if hit:
            if t["mode"] == "no_extra":
                ids = set((hit.get("recommended") or {}).get("ids") or [])
                reply = "With no extra staff, space or beds: " + hit["headline"] + _retest(hit)
                if ids & {"decide_10", "discharge_10"}:
                    reply += (" That includes process changes (faster discharges or quicker decisions) that assume a "
                              "10% improvement the trust would need to deliver.")
                return {"reply": reply + " Workforce & investment shows the changes.",
                        "intent": "target", "search_key": hit.get("search_key"), "target": t}
            return {"reply": hit["headline"] + _retest(hit) + " Workforce & investment shows the extra shifts, "
                    "space and costs.",
                    "intent": "target", "search_key": hit.get("search_key"), "target": t}
        job = ctx["start_search"](t)
        if t["mode"] == "no_extra":
            return {"reply": f"I'm looking for the best the model can do for {t['pct']:g}% within {_time_words(t['minutes'])} "
                    f"without adding staff, space or beds. This takes a few minutes; you can follow it below.",
                    "intent": "target", "job": job, "target": t}
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
        return {"reply": where_waits(ctx["result"], ctx.get("view")), "intent": "where"}
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
