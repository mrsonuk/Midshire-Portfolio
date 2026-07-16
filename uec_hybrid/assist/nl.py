"""
Ask a what-if: plain English -> scenario -> engine -> plain-English answer.

The contract that keeps this trustworthy:
- The language layer only ever TRANSLATES (question -> scenario) and NARRATES
  (computed results -> sentences). All numbers come from the simulation.
- A rule-based parser handles the common phrasings fully offline. When Claude
  is available (see ``llm``) it is used as a fallback parser for free-form
  phrasing and as a better narrator - but its output is validated against the
  department's real resources, and the computed table is always shown.
"""
from __future__ import annotations

import re

from ..des.pathway import Pathway
from ..analysis.scenarios import compare_scenarios

NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"

# phrase pattern -> engine resource (only applied if the built raw has it)
RESOURCE_WORDS = [
    (r"rat\s+(?:clinician|consultant|doctor)s?|rapid\s+assessment", "rat_clinician"),
    (r"paed(?:iatric|s)?\s+doctors?", "paeds_doctor"),
    (r"sdec\s+doctors?|specialty\s+doctors?", "specialty_doctor"),
    (r"streaming(?:\s+nurses?)?|triage\s+nurses?", "streaming_nurse"),
    (r"enps?|nurse\s+practitioners?", "minors_enp"),
    (r"porters?", "porter_pool"),
    (r"handover\s+bays?", "handover_bay"),
    (r"cubicles?", "cubicle"),
    (r"doctors?|consultants?|registrars?|shos?|medics?|clinicians?", "ed_doctor"),
]

EXAMPLES = ["add 2 doctors", "remove a porter", "double the cubicles",
            "10% more attendances", "40 more ward beds", "20 extra community places",
            "divert 20% of minors to the UTC", "a winter surge"]


def _n(tok: str) -> int:
    return int(tok) if tok.isdigit() else NUM_WORDS[tok.lower()]


def _resource_for(phrase: str, raw: dict):
    for pat, res in RESOURCE_WORDS:
        if re.search(pat, phrase, re.I):
            return res if res in raw.get("resources", {}) else (res, "missing")
    return None


def parse_question(question: str, raw: dict):
    """Parse a plain-English what-if into a scenario dict (see analysis/scenarios).
    Returns (scenario | None, notes) - notes say what was understood/skipped."""
    q = " " + question.lower().strip() + " "
    scenario: dict = {}
    notes: list[str] = []

    def add_resource(res, change, label):
        if isinstance(res, tuple):        # matched a phrase but the ED doesn't have it
            notes.append(f"skipped '{label.strip()}' - your department doesn't have that area/resource")
            return
        scenario.setdefault("resources", {})[res] = change
        pretty = res.replace("_", " ")
        notes.append(f"{pretty}: {change}")

    # --- staffing / spaces: add / remove / double / halve --------------------
    for m in re.finditer(rf"(?:add|extra|another|hire|bring in|put on)\s+{_NUM}\s+(?:more\s+|extra\s+)?([a-z ]+?)(?=[,.?]| and | at | over| to |$)", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"+{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"{_NUM}\s+(?:more|extra|additional)\s+([a-z ]+?)(?=[,.?]| and |$)", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"+{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"(?:remove|cut|lose|drop|take away)\s+{_NUM}\s+([a-z ]+?)(?=[,.?]| and |$)", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"-{_n(m.group(1))}", m.group(2))
    for m in re.finditer(rf"{_NUM}\s+fewer\s+([a-z ]+?)(?=[,.?]| and |$)", q):
        res = _resource_for(m.group(2), raw)
        if res is not None:
            add_resource(res, f"-{_n(m.group(1))}", m.group(2))
    for m in re.finditer(r"(?:double)\s+(?:the\s+)?([a-z ]+?)(?=[,.?]| and |$)", q):
        res = _resource_for(m.group(1), raw)
        if res is not None:
            add_resource(res, "*2", m.group(1))
    for m in re.finditer(r"(?:halve)\s+(?:the\s+)?([a-z ]+?)(?=[,.?]| and |$)", q):
        res = _resource_for(m.group(1), raw)
        if res is not None:
            add_resource(res, "*0.5", m.group(1))

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
         or re.search(r"(?:demand|attendances|arrivals)\s+(?:up|rises?|increases?|grows?)\s+(?:by\s+)?(\d+)\s*%", q))
    if m:
        scenario["arrivals_scale"] = round(1 + int(m.group(1)) / 100, 3)
        notes.append(f"demand x{scenario['arrivals_scale']}")
    m = (re.search(r"(\d+)\s*%\s+(?:less|fewer|lower)\s+(?:demand|attendances|arrivals|patients)", q)
         or re.search(r"(?:demand|attendances|arrivals)\s+(?:down|falls?|drops?|decreases?)\s+(?:by\s+)?(\d+)\s*%", q))
    if m:
        scenario["arrivals_scale"] = round(max(0.1, 1 - int(m.group(1)) / 100), 3)
        notes.append(f"demand x{scenario['arrivals_scale']}")
    if "winter" in q and "arrivals_scale" not in scenario:
        scenario["arrivals_scale"] = 1.12
        notes.append("winter surge assumed as +12% demand (edit in Plan ahead for other levels)")

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
