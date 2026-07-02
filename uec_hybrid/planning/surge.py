"""
Winter-pressure stress tests and the inverse staffing question.

Each surge template is a declarative change-set applied on top of the
department exactly as configured (demand scale, case-mix skew, ward closures,
staff absence), simulated like any other configuration. The inverse solver
answers the question planners actually ask: "what would we need to hold the
4-hour position through this?" by greedily adding the cheapest effective
staffing until the target holds or the options run out.
"""
from __future__ import annotations

import copy

from ..des.pathway import Pathway
from ..workforce.roles import ROLES
from .planner import build_department, _spread, TARGET

# Surge templates: plain-language stress tests. Every number is an editable
# planning assumption, not a prediction.
TEMPLATES = {
    "flu": {
        "label": "Bad flu season",
        "story": "Sustained respiratory surge: more attendances, older and sicker, "
                 "and a fuller hospital for weeks.",
        "arrivals_scale": 1.10,
        "acuity_shift": 0.15,            # move this share of A4/A5 weight up to A2/A3
        "sd": {"baseline_bed_occupancy": "+0.03"},
    },
    "norovirus": {
        "label": "Norovirus ward closures",
        "story": "Infection control closes bays: fewer usable inpatient beds while "
                 "demand stays normal.",
        "sd": {"inpatient_beds": "*0.92", "baseline_bed_occupancy": "+0.02"},
    },
    "strike": {
        "label": "Medical strike day",
        "story": "A third of medical staffing is lost for the period; demand barely falls.",
        "arrivals_scale": 0.97,
        "resources": {"ed_doctor": "*0.67", "specialty_doctor": "*0.67"},
    },
    "heatwave": {
        "label": "Heatwave",
        "story": "More elderly and frail patients over a hot spell.",
        "arrivals_scale": 1.06,
        "acuity_shift": 0.08,
    },
    "winter_norm": {
        "label": "A normal winter",
        "story": "Typical December: the seasonal rise on an ordinary week.",
        "arrivals_scale": 1.12,
        "sd": {"baseline_bed_occupancy": "+0.02"},
    },
}

# Staffing moves the solver may add, cheapest first (rate x hours). Each is one
# incremental step; the solver can take several.
SOLVER_MOVES = [
    {"role": "band5_nurse", "start": 10, "end": 22, "count": 1},
    {"role": "enp", "start": 10, "end": 22, "count": 1},
    {"role": "em_sho", "start": 12, "end": 22, "count": 1},
    {"role": "em_registrar", "start": 12, "end": 22, "count": 1},
    {"role": "sdec_doctor", "start": 10, "end": 20, "count": 1},
    {"role": "ed_consultant", "start": 12, "end": 20, "count": 1},
]


def _move_cost_per_week(move) -> int:
    role = ROLES[move["role"]]
    hours = (move["end"] - move["start"]) % 24 or 24
    return int(role["cost"] * hours * move["count"] * 7)


def _num(v, ch):
    ch = str(ch).strip()
    if ch.startswith("+"):
        return v + float(ch[1:])
    if ch.startswith("-"):
        return v - float(ch[1:])
    if ch.startswith("*"):
        return v * float(ch[1:])
    return float(ch)


def apply_template(raw: dict, template: dict) -> dict:
    """Apply a surge change-set to a built pathway raw (deep-copied)."""
    raw = copy.deepcopy(raw)
    scale = float(template.get("arrivals_scale", 1.0))
    if scale != 1.0:
        raw["arrivals"]["hourly_profile"] = [round(h * scale, 2)
                                             for h in raw["arrivals"]["hourly_profile"]]
    shift = float(template.get("acuity_shift", 0.0))
    if shift > 0:
        from ..demand.streams import skew_stream_mixes
        mix = dict(raw["arrivals"].get("acuity_mix") or {})
        if mix:
            moved = shift * (mix.get("Acuity 4", 0) + mix.get("Acuity 5", 0)) * 0.5
            mix["Acuity 4"] = max(0.0, mix.get("Acuity 4", 0) - moved * 0.75)
            mix["Acuity 5"] = max(0.0, mix.get("Acuity 5", 0) - moved * 0.25)
            mix["Acuity 2"] = mix.get("Acuity 2", 0) + moved * 0.4
            mix["Acuity 3"] = mix.get("Acuity 3", 0) + moved * 0.6
            skew_stream_mixes(raw["arrivals"], mix)
    for r, ch in (template.get("resources") or {}).items():
        if r in raw["resources"]:
            cap = raw["resources"][r]
            if isinstance(cap, list):
                raw["resources"][r] = [max(1, int(round(_num(c, ch)))) for c in cap]
            else:
                raw["resources"][r] = max(1, int(round(_num(cap, ch))))
    sd = raw.setdefault("sd", {})
    for k, ch in (template.get("sd") or {}).items():
        base = sd.get(k, 0.92 if k == "baseline_bed_occupancy" else 0)
        sd[k] = round(_num(float(base), ch), 3)
    return raw


def stress_test(department, template_key: str, calibration=None, reps=5) -> dict:
    """Run one surge template against the configured department."""
    template = TEMPLATES[template_key]
    base_raw, _ = build_department(department=department, calibration=calibration,
                                   winter_uplift_pct=0)
    surged = apply_template(base_raw, template)
    base = _spread(base_raw, reps=reps, seed=900)
    hit = _spread(surged, reps=reps, seed=900)
    return {"key": template_key, "label": template["label"], "story": template["story"],
            "baseline": base, "surge": hit,
            "delta_four_hour": hit["typical"] - base["typical"],
            "delta_corridor": round(hit["corridor_per_day"] - base["corridor_per_day"], 1)}


def staff_to_hold(department, template_key: str, calibration=None,
                  target: int = TARGET, max_moves: int = 6, reps: int = 4) -> dict:
    """The inverse question: which staffing additions hold the 4-hour target
    through this surge? Greedy: repeatedly add the move that buys the most
    4-hour points per pound until the target holds or moves run out."""
    template = TEMPLATES[template_key]
    dept = copy.deepcopy(department)
    added, log = [], []

    def outcome(d):
        raw, _ = build_department(department=d, calibration=calibration, winter_uplift_pct=0)
        return _spread(apply_template(raw, template), reps=reps, seed=950)

    current = outcome(dept)
    log.append({"step": "do nothing", "four_hour": current["typical"], "weekly_cost": 0})
    while current["typical"] < target and len(added) < max_moves:
        best = None
        for move in SOLVER_MOVES:
            trial = copy.deepcopy(dept)
            trial.rota = list(trial.rota) + [dict(move)]
            got = outcome(trial)
            gain = got["typical"] - current["typical"]
            value = gain / max(1, _move_cost_per_week(move))
            if gain > 0.5 and (best is None or value > best["value"]):
                best = {"move": move, "outcome": got, "gain": gain, "value": value}
        if best is None:
            break
        dept.rota = list(dept.rota) + [dict(best["move"])]
        added.append(best["move"])
        current = best["outcome"]
        log.append({"step": f"add {best['move']['count']} x "
                            f"{ROLES[best['move']['role']]['label']} "
                            f"{best['move']['start']:02d}:00-{best['move']['end']:02d}:00",
                    "four_hour": current["typical"],
                    "weekly_cost": _move_cost_per_week(best["move"])})

    weekly = sum(_move_cost_per_week(m) for m in added)
    holds = current["typical"] >= target
    return {"template": template["label"], "target": target, "holds": holds,
            "final_four_hour": current["typical"], "additions": log[1:],
            "weekly_cost": weekly,
            "headline": (f"Holding {target}% through '{template['label']}' takes "
                         f"{len(added)} staffing addition{'s' if len(added) != 1 else ''} "
                         f"(about £{weekly:,}/week)." if holds and added else
                         f"You already hold {target}% through '{template['label']}'." if holds else
                         f"Staffing alone does not hold {target}% through "
                         f"'{template['label']}' (best {current['typical']}%); "
                         f"capacity or flow changes are needed too.")}
