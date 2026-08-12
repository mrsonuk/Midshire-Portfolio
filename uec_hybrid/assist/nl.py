"""
Ask a what-if: plain English -> scenario -> engine -> plain-English answer.

The contract that keeps this trustworthy:
- The language layer only ever TRANSLATES (question -> scenario) and NARRATES
  (computed results -> sentences). All numbers come from the simulation.
- A rule-based parser handles the common phrasings fully offline. When 
  is available (see ``llm``) it is used as a fallback parser for free-form
  phrasing and as a better narrator - but its output is validated against the
  department's real resources, and the computed table is always shown.
"""
from __future__ import annotations

import re

from ..des.pathway import Pathway
from ..analysis.scenarios import compare_scenarios, _cap

NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"

# phrase pattern -> engine resource (only applied if the built raw has it).
# "ed_nurse" is special: nurses limit flow through the nurse-to-cubicle ratio,
# not as an engine resource, so it is handled by add_resource below.
RESOURCE_WORDS = [
    (r"rat\s+(?:clinician|consultant|doctor)s?|rapid\s+assessment", "rat_clinician"),
    (r"paed(?:iatric|s)?\s+doctors?", "paeds_doctor"),
    (r"sdec\s+doctors?|specialty\s+doctors?", "specialty_doctor"),
    (r"streaming(?:\s+nurses?)?|triage\s+nurses?", "streaming_nurse"),
    (r"enps?|nurse\s+practitioners?", "minors_enp"),
    (r"(?:ed\s+|band\s*[56]\s+)?nurses?\b", "ed_nurse"),
    (r"porters?", "porter_pool"),
    (r"handover\s+bays?", "handover_bay"),
    (r"cubicles?", "cubicle"),
    (r"doctors?|consultants?|registrars?|shos?|medics?|clinicians?", "ed_doctor"),
]

EXAMPLES = ["what would it take to reach 90% in 4 hours",
            "add 2 doctors", "add 3 nurses at 1pm", "remove a doctor overnight",
            "double the cubicles", "10% more attendances", "10% staff sickness",
            "20% more attendances in the evening", "40 more ward beds",
            "20 extra community places", "divert 20% of minors to the UTC",
            "a winter surge"]

# time-of-day words -> (start hour, end hour) on a 24h clock (end may wrap)
DAYPARTS = {"overnight": (20, 8), "tonight": (20, 8), "at night": (20, 8),
            "in the morning": (8, 14), "in the afternoon": (12, 20),
            "in the evening": (16, 24), "over lunch": (12, 14)}
_CLOCK = r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?"
_SHIFT_HOURS = 8                            # assumed length when only a start is given


def _n(tok: str) -> int:
    return int(tok) if tok.isdigit() else NUM_WORDS[tok.lower()]


def _hour(h, ap) -> int | None:
    h = int(h)
    if ap == "pm" and h != 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    return h if 0 <= h <= 23 else None


def _span(s: int, e: int) -> list[int]:
    e = e if e > s else e + 24              # wrap past midnight ("8pm to 8am")
    return [h % 24 for h in range(s, e)]


def parse_window(q: str):
    """Find a time-of-day window in the question. Returns (hours, label, note)
    or (None, "", None). Label goes into the understood-changes notes."""
    m = re.search(rf"(?:from|between)\s+{_CLOCK}\s*(?:to|until|till|and|-)\s*{_CLOCK}", q)
    if m:
        s, e = _hour(m.group(1), m.group(3)), _hour(m.group(4), m.group(6))
        if s is not None and e is not None and s != e:
            return _span(s, e), f" {s:02d}:00-{e % 24:02d}:00", None
    m = re.search(rf"\bat\s+{_CLOCK}(?=\W|$)", q)
    if m and (m.group(2) or m.group(3) or int(m.group(1)) > 9):   # "at 1" alone: too ambiguous
        s = _hour(m.group(1), m.group(3))
        if s is not None:
            e = (s + _SHIFT_HOURS) % 24
            return (_span(s, s + _SHIFT_HOURS), f" {s:02d}:00-{e:02d}:00",
                    f"assumed an {_SHIFT_HOURS}h shift from {s:02d}:00 - say "
                    f"'from {s:02d}:00 to HH:00' to set the window")
    for word, (s, e) in DAYPARTS.items():
        if word in q:
            return _span(s, e), f" {s:02d}:00-{e % 24:02d}:00", None
    return None, "", None


def _resource_for(phrase: str, raw: dict):
    for pat, res in RESOURCE_WORDS:
        if re.search(pat, phrase, re.I):
            if res == "ed_nurse":           # ratio-based, never in raw resources
                return res
            return res if res in raw.get("resources", {}) else (res, "missing")
    return None


_STOP = r"(?=[,.?]| and | at | over| to | from | between |$)"


_TARGET = re.compile(
    r"(what\s+(?:would|will|does)\s+it\s+take|what(?:'s| is)\s+needed|"
    r"how\s+(?:do|can|could|would)\s+we\s+(?:get\s+to|reach|hit|achieve)|"
    r"(?:to\s+)?(?:reach|hit|achieve)\b).{0,60}?(\d{1,3})(?:\.\d+)?\s*%")


def parse_target(question: str) -> float | None:
    """A goal-seeking question ("what would it take to achieve 90% in 4 hours?")
    names a TARGET, not a change - it is answered by stacking the CI-gated
    recommendations (optimise.recommend.target_plan), not by the scenario
    parser. Returns the target percentage, or None if this is not one."""
    m = _TARGET.search(" " + question.lower().strip())
    if not m:
        return None
    pct = float(m.group(2))
    return pct if 1.0 <= pct <= 100.0 else None


def parse_question(question: str, raw: dict):
    """Parse a plain-English what-if into a scenario dict (see analysis/scenarios).
    Returns (scenario | None, notes) - notes say what was understood/skipped."""
    q = " " + question.lower().strip() + " "
    scenario: dict = {}
    notes: list[str] = []
    hours, wlabel, wnote = parse_window(q)

    def _nurse_ready():
        uec = raw.get("uec") or {}
        return (uec.get("nurse_to_cubicle_ratio") and uec.get("ed_nurse_staffing")
                and "cubicle" in raw.get("resources", {}))

    def add_resource(res, change, label):
        if isinstance(res, tuple):        # matched a phrase but the ED doesn't have it
            note = f"skipped '{label.strip()}' - your department doesn't have that area/resource"
            if note not in notes:
                notes.append(note)
            return
        if res == "ed_nurse":             # via the nurse-to-cubicle ratio, not a resource
            if not _nurse_ready():
                note = ("skipped nurses - no nurse-to-cubicle ratio is configured, so "
                        "nurses don't limit flow in this model (edit the rota on the "
                        "rota in Set up my ED instead)")
                if note not in notes:
                    notes.append(note)
                return
            if scenario.get("nurses") == {"change": change, "hours": hours}:
                return                     # two phrasing patterns caught the same change
            scenario["nurses"] = {"change": change, "hours": hours}
            uec, ratio = raw["uec"], int(raw["uec"]["nurse_to_cubicle_ratio"])
            note = (f"ED nurses: {change}{wlabel} - opens/closes cubicles through the "
                    f"1:{ratio} nurse-to-cubicle ratio, where physical spaces allow")
            # honesty check: at the current rota, does this nurse change actually
            # move the cubicle roster in the window?
            cur = raw["resources"]["cubicle"]
            cur24 = list(cur) if isinstance(cur, (list, tuple)) else [cur] * 24
            phys = uec.get("physical_cubicles") or cur24
            p24 = list(phys) if isinstance(phys, (list, tuple)) else [int(phys)] * 24
            win = set(hours or range(24))
            moved = any(max(1, min(int(p24[h]), max(0, _cap(n, change)) * ratio)) != int(round(cur24[h]))
                        for h, n in enumerate(uec["ed_nurse_staffing"]) if h in win)
            if not moved:
                note += (". Note: at your current rota every physical cubicle in that window "
                         "is already nurse-covered, so this change adds no cubicle capacity - "
                         "expect little movement")
            notes.append(note)
            return
        val = {"change": change, "hours": hours} if hours else change
        if scenario.get("resources", {}).get(res) == val:
            return                         # two phrasing patterns caught the same change
        scenario.setdefault("resources", {})[res] = val
        pretty = res.replace("_", " ")
        notes.append(f"{pretty}: {change}{wlabel}")

    # --- staffing / spaces: add / remove / double / halve --------------------
    for m in re.finditer(rf"(?:add|extra|another|hire|bring in|put on)\s+{_NUM}\s+(?:more\s+|extra\s+)?([a-z ]+?){_STOP}", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"+{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"{_NUM}\s+(?:more|extra|additional)\s+([a-z ]+?){_STOP}", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"+{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"(?:remove|cut|lose|drop|take away)\s+{_NUM}\s+([a-z ]+?){_STOP}", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"-{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"{_NUM}\s+fewer\s+([a-z ]+?){_STOP}", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"-{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"(?:double)\s+(?:the\s+)?([a-z ]+?){_STOP}", q):
        res = _resource_for(m.group(1), raw)
        if res is not None:
            add_resource(res, "*2", m.group(1))
    for m in re.finditer(rf"(?:halve)\s+(?:the\s+)?([a-z ]+?){_STOP}", q):
        res = _resource_for(m.group(1), raw)
        if res is not None:
            add_resource(res, "*0.5", m.group(1))
    if wnote and (scenario.get("resources") or scenario.get("nurses")):
        notes.append(wnote)

    # --- whole-hospital levers: ward beds / community ------------------------
    sd_now = raw.get("sd", {})
    m = re.search(rf"{_NUM}\s+(?:more|extra|additional)\s+(?:ward\s+|inpatient\s+)?beds", q)
    if m:
        beds = int(sd_now.get("inpatient_beds", 320)) + _n(m.group(1))
        scenario.setdefault("sd", {})["inpatient_beds"] = beds
        notes.append(f"ward beds: {sd_now.get('inpatient_beds', 320)} -> {beds}")
    m = re.search(rf"{_NUM}\s+fewer\s+(?:ward\s+|inpatient\s+)?beds", q)
    if m:
        beds = max(1, int(sd_now.get("inpatient_beds", 320)) - _n(m.group(1)))
        scenario.setdefault("sd", {})["inpatient_beds"] = beds
        notes.append(f"ward beds: {sd_now.get('inpatient_beds', 320)} -> {beds}")
    m = re.search(rf"{_NUM}\s+(?:more|extra|additional)\s+(?:community|virtual[- ]ward)\s*(?:places|slots|beds|capacity)?", q)
    if m:
        comm = int(sd_now.get("community_capacity", 60)) + _n(m.group(1))
        scenario.setdefault("sd", {})["community_capacity"] = comm
        notes.append(f"community capacity: {sd_now.get('community_capacity', 60)} -> {comm}")

    # --- demand ---------------------------------------------------------------
    m = (re.search(r"(\d+)\s*%\s+(?:more|extra|higher|increase in)\s+(?:demand|attendances|arrivals|patients)", q)
         or re.search(r"(?:demand|attendances|arrivals)\s+(?:goes\s+up|go(?:es)?\s+up|up|rises?|increases?|grows?|climbs?)\s+(?:by\s+)?(\d+)\s*%", q))
    if m:
        scenario["arrivals_scale"] = round(1 + int(m.group(1)) / 100, 3)
        notes.append(f"demand x{scenario['arrivals_scale']}")
    m = (re.search(r"(\d+)\s*%\s+(?:less|fewer|lower)\s+(?:demand|attendances|arrivals|patients)", q)
         or re.search(r"(?:demand|attendances|arrivals)\s+(?:goes?\s+down|down|falls?|drops?|decreases?)\s+(?:by\s+)?(\d+)\s*%", q))
    if m:
        scenario["arrivals_scale"] = round(max(0.1, 1 - int(m.group(1)) / 100), 3)
        notes.append(f"demand x{scenario['arrivals_scale']}")
    if "winter" in q and "arrivals_scale" not in scenario:
        scenario["arrivals_scale"] = 1.12
        notes.append("winter surge assumed as +12% demand")
    # a time window on a demand change makes it an intra-day surge (evening peak, event)
    if hours and isinstance(scenario.get("arrivals_scale"), float):
        scenario["arrivals_scale"] = {"scale": scenario["arrivals_scale"], "hours": hours}
        notes[-1] += wlabel + " only"

    # --- workforce sickness / absence ------------------------------------------
    m = (re.search(r"(\d+)\s*%\s+(?:staff\s+)?(?:sickness|absence|absent|off\s+sick)", q)
         or re.search(r"(?:staff\s+)?(?:sickness|absence)\s+(?:at|of)\s+(\d+)\s*%", q)
         or re.search(r"(\d+)\s*%\s+of\s+(?:the\s+)?staff\s+(?:are\s+)?(?:off|sick|absent)", q))
    if m:
        pct = min(90, int(m.group(1)))
        scenario["staff_scale"] = round(1 - pct / 100, 3)
        notes.append(f"staff sickness/absence: every staff group scaled to "
                     f"{100 - pct}% of the rota (rounded to whole staff; fewer "
                     f"nurses also close cubicles through the nurse-to-cubicle ratio)")

    # --- redirect minors --------------------------------------------------------
    m = re.search(r"(?:divert|redirect|send|stream)\s+(\d+)\s*%\s+(?:of\s+)?(?:the\s+)?(?:minors|low[- ]acuity|acuity\s*[45])", q)
    if m:
        scenario["divert"] = {"classes": ["Acuity 4", "Acuity 5"], "fraction": int(m.group(1)) / 100}
        notes.append(f"redirect {m.group(1)}% of low-acuity patients away from the ED")

    return (scenario or None), notes


# ------------------------------------------------------------------------------
# Run + narrate
# ------------------------------------------------------------------------------
ANSWER_KEYS = [("four_hour", "4-hour standard", "%", True),
               ("twelve_hour", "12-hour waits", "%", False),
               ("lwbs", "walk-outs (LWBS)", "%", False),
               ("ambulance_handover_45", "handover ≤45 min", "%", True),
               ("bed_occupancy", "bed occupancy", "%", False)]


def _narrate(notes, deltas, reps) -> str:
    changed = [f"{label} {d['base']:.1f}% → {d['scenario']:.1f}% ({d['delta']:+.1f} points)"
               for key, label, _, _ in ANSWER_KEYS
               if (d := deltas.get(key)) and abs(d["delta"]) >= 0.5]
    body = ("; ".join(changed) if changed
            else "no standard moved by more than half a point - this change is within the model's noise at this demand")
    fh = deltas.get("four_hour")
    verdict = ""
    if fh and fh["delta"] >= 1:
        verdict = " Overall this change helps."
    elif fh and fh["delta"] <= -1:
        verdict = " Overall this change makes the 4-hour position worse."
    return (f"I modelled: {'; '.join(notes)}. Across {reps} simulated weeks: {body}.{verdict} "
            f"Differences under ~1 point may be Monte-Carlo noise.")


def run_what_if(question: str, raw: dict, reps: int = 6, use_llm: bool = True) -> dict:
    """Parse -> simulate (scenario vs baseline, paired seeds) -> answer.
    Returns {answer, notes, deltas, rows, llm_used} or {error, supported}."""
    from . import llm
    scenario, notes = parse_question(question, raw)
    llm_used = False
    if scenario is None and use_llm and llm.available():
        parsed = llm.parse_with_llm(question, raw)
        if parsed:
            scenario, notes = parsed
            llm_used = True
    if scenario is None:
        return {"error": "I couldn't turn that into a change I can simulate.",
                "notes": notes, "supported": EXAMPLES}

    p = Pathway.from_dict(raw)
    cmp = compare_scenarios(p, [{**scenario, "name": "What-if"}], replications=max(2, int(reps)))
    base, scn = cmp["rows"][0], cmp["rows"][1]
    deltas = {}
    for key, label, unit, higher_better in ANSWER_KEYS:
        if key in base and key in scn:
            deltas[key] = {"label": label, "unit": unit, "higher_better": higher_better,
                           "base": round(float(base[key]), 1),
                           "scenario": round(float(scn[key]), 1),
                           "delta": round(float(scn[key]) - float(base[key]), 1)}

    answer = _narrate(notes, deltas, cmp["replications"])
    if use_llm and llm.available():
        better = llm.narrate({"understood": notes, "replications": cmp["replications"],
                              "results": deltas})
        if better:
            answer, llm_used = better, True
    return {"answer": answer, "notes": notes, "deltas": deltas,
            "rows": cmp["rows"], "llm_used": llm_used}
