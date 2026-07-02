"""
Demand & capacity planner - translates the simulation into the answers an ICB
winter / investment planner actually wants, in plain language:

  * what winter looks like at the current set-up (good week / typical / tough week);
  * what is driving the pressure (in operational terms, not model terms);
  * a short list of realistic options, ranked by how much they help, with a rough
    cost/effort band so the planner can see what is worth it.

The simulation does the sums; none of its vocabulary (Monte-Carlo, DES, system
dynamics, utilisation, multipliers) appears in anything this module returns.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from ..des.pathway import Pathway
from ..analysis.montecarlo import monte_carlo
from .forecast import forecast

BASE_RAW = json.load(open(Path(__file__).resolve().parent.parent / "pathways" / "model_ed.json"))
BASELINE_ATTEND = 320          # the reference department the template represents
TARGET = 78                    # operational 4-hour standard (toward 95% constitutional)

# Plain-English options a planner can actually choose between.
# delta_* applied on top of the configured department.
OPTIONS = [
    {"id": "sdec", "label": "Expand same-day emergency care (more space, longer hours)",
     "resources": {"sdec_chair": "*1.5", "specialty_doctor": "+2"},
     "cost": "Moderate", "kind": "Space + staffing", "build": "No new building"},
    {"id": "discharge", "label": "Get more inpatients discharged by late morning",
     "sd": {"ward_discharge_capacity_per_hour": "*1.25"},
     "cost": "Low", "kind": "Ward process change", "build": "No cost, needs ward routine change"},
    {"id": "community", "label": "More community / virtual-ward capacity to pull patients out",
     "sd": {"community_capacity": "*1.6", "community_clearance_per_hour": "*1.6"},
     "cost": "Moderate", "kind": "Commissioning", "build": "Commission community capacity"},
    {"id": "beds", "label": "Add inpatient (ward) beds",
     "sd": {"inpatient_beds": "+18"},
     "cost": "High", "kind": "Capital", "build": "Capital / staffing for new beds"},
    {"id": "utc", "label": "Co-located urgent treatment centre to redirect minor cases",
     "divert": {"classes": ["Acuity 4", "Acuity 5"], "fraction": 0.18},
     "cost": "High", "kind": "Capital / commissioning", "build": "New/located UTC"},
    {"id": "doctors", "label": "More medical staffing at the evening peak",
     "resources": {"ed_doctor": "+3"},
     "cost": "Moderate", "kind": "Staffing", "build": "Recurring staffing cost"},
]


def _scale_cap(v, ch):
    if isinstance(v, list):
        # a by-hour staffing roster: apply the change to every hour
        return [_scale_cap(x, ch) for x in v]
    if isinstance(ch, str):
        ch = ch.strip()
        if ch[0] == "+":
            return max(1, int(round(v + float(ch[1:]))))
        if ch[0] == "-":
            return max(1, int(round(v - float(ch[1:]))))
        if ch[0] == "*":
            return max(1, int(round(v * float(ch[1:]))))
    return int(round(float(ch)))


def build_department(attendances_now=None, winter_uplift_pct=12.0, yoy_growth_pct=0.0,
                     extra=None, department=None, calibration=None):
    """Build the model for the winter demand, plus any option changes in ``extra``
    ({resources, sd, divert}).

    When ``department`` (a department.config.Department) is given the plan models
    *that* ED - its areas, opening hours, rota, beds and community capacity, plus
    any stored ECDS ``calibration`` patch - with only demand scaled to the
    forecast. Without one it falls back to the generic template scaled by size."""
    if department is not None:
        from ..department.builder import build as build_dept
        raw = build_dept(department)
        if calibration:
            from ..demand.ecds_seam import apply_patch
            raw = apply_patch(raw, calibration)
        if attendances_now is None:
            attendances_now = float(department.attendances_per_day)
        fc = forecast(attendances_now, winter_uplift_pct, yoy_growth_pct)
        # scale the department's own arrival shape to the forecast total -
        # demand changes this winter; the department's capacity does not.
        prof = raw["arrivals"]["hourly_profile"]
        tot = sum(prof) or 1
        raw["arrivals"]["hourly_profile"] = [round(h * fc["expected_per_day"] / tot, 2) for h in prof]
    else:
        attendances_now = BASELINE_ATTEND if attendances_now is None else attendances_now
        raw = copy.deepcopy(BASE_RAW)
        fc = forecast(attendances_now, winter_uplift_pct, yoy_growth_pct)
        scale = max(0.3, attendances_now / BASELINE_ATTEND)
        # scale the department's areas/staff and the whole-hospital beds with its size
        for r, c in raw["resources"].items():
            raw["resources"][r] = max(1, int(round(c * scale)))
        for key in ("inpatient_beds", "mh_beds", "community_capacity"):
            if key in raw.get("sd", {}):
                raw["sd"][key] = int(round(raw["sd"][key] * scale))
        for key in ("background_admissions_per_hour", "ward_discharge_capacity_per_hour",
                    "community_clearance_per_hour"):
            if key in raw.get("sd", {}):
                raw["sd"][key] = round(raw["sd"][key] * scale, 2)
        raw["arrivals"]["hourly_profile"] = fc["hourly_profile"]

    extra = extra or {}
    for r, ch in extra.get("resources", {}).items():
        if r in raw["resources"]:
            raw["resources"][r] = _scale_cap(raw["resources"][r], ch)
    for k, ch in extra.get("sd", {}).items():
        if k in raw["sd"]:
            raw["sd"][k] = (round(_scale_cap(raw["sd"][k], ch), 2)
                            if isinstance(raw["sd"][k], float) else _scale_cap(raw["sd"][k], ch))
    div = extra.get("divert")
    if div and div.get("fraction", 0) > 0:
        from ..demand.streams import skew_stream_mixes
        mix = dict(raw["arrivals"]["acuity_mix"]); f = float(div["fraction"])
        classes = [c for c in div.get("classes", []) if c in mix]
        diverted = sum(mix[c] for c in classes) / (sum(mix.values()) or 1) * f
        for c in classes:
            mix[c] *= (1 - f)
        skew_stream_mixes(raw["arrivals"], mix)   # streams carry the case-mix now
        raw["arrivals"]["hourly_profile"] = [h * (1 - diverted) for h in raw["arrivals"]["hourly_profile"]]
    return raw, fc


def _spread(raw, reps=6, seed=500):
    p = Pathway.from_dict(raw)
    days = max(1, (p.sim_duration - p.warmup) / 1440)
    mc = monte_carlo(p, replications=reps, base_seed=seed, feedback=True)
    s = mc["summary"]
    table = mc["table"]
    four = s.get("four_hour", {"mean": 0, "min": 0, "max": 0})
    miss = float((table["four_hour"] < TARGET).mean()) if "four_hour" in table else 0.0
    twelve_day = s.get("n_twelve_hour", {"mean": 0})["mean"] / days
    return {
        "typical": round(four["mean"]),
        "good": round(four["max"]),
        "tough": round(four["min"]),
        "meets": four["mean"] >= TARGET,
        "miss_weeks": round(miss * 10),
        "corridor_per_day": round(twelve_day, 1),
        "bed_occupancy": round(s.get("bed_occupancy", {"mean": 0})["mean"]),
        "occ_series": mc["occ_series"][0] if mc.get("occ_series") else [],
    }


def _constraint(outcome, raw):
    """Plain-English statement of what is driving the pressure."""
    if outcome["bed_occupancy"] >= 90:
        return ("Not enough ward beds to admit into - admitted patients back up in "
                "the ED waiting for a bed. This is the main cause of long waits and "
                "corridor care.")
    if outcome["typical"] >= TARGET:
        return "The department broadly copes with the expected demand."
    return ("The ED itself is the pinch point at busy times (assessment space and "
            "medical staffing at the evening peak), rather than ward beds.")


def make_plan(attendances_now=None, winter_uplift_pct=12.0, yoy_growth_pct=0.0,
              department=None, calibration=None) -> dict:
    base_raw, fc = build_department(attendances_now, winter_uplift_pct, yoy_growth_pct,
                                    department=department, calibration=calibration)
    base = _spread(base_raw, reps=6)
    base["constraint"] = _constraint(base, base_raw)

    options = []
    for opt in OPTIONS:
        raw, _ = build_department(attendances_now, winter_uplift_pct, yoy_growth_pct, extra=opt,
                                  department=department, calibration=calibration)
        res = _spread(raw, reps=4, seed=700)
        options.append({
            "id": opt["id"], "label": opt["label"], "cost": opt["cost"],
            "kind": opt["kind"], "build": opt["build"],
            "four_hour": res["typical"], "delta": res["typical"] - base["typical"],
            "corridor_per_day": res["corridor_per_day"], "meets": res["meets"]})
    options.sort(key=lambda o: o["delta"], reverse=True)

    # recommendation: cheapest option that gets to target; else the biggest mover
    rank = {"Low": 0, "Moderate": 1, "High": 2}
    meeters = [o for o in options if o["four_hour"] >= TARGET and o["delta"] > 0]
    if meeters:
        pick = sorted(meeters, key=lambda o: (rank.get(o["cost"], 3), -o["delta"]))[0]
        rec = (f"The most cost-effective way to protect the 4-hour standard this winter "
               f"is to <b>{pick['label'].lower()}</b> - it gets you to about "
               f"{pick['four_hour']}% ({pick['cost'].lower()} cost). ")
    else:
        pick = options[0] if options else None
        rec = (f"No single change reaches the {TARGET}% standard at this demand; the "
               f"biggest improvement comes from <b>{pick['label'].lower()}</b> "
               f"(+{pick['delta']} points). A combination will be needed. " if pick else "")
    if base["meets"]:
        rec = ("At the expected winter demand the department broadly meets the 4-hour "
               "standard, but with little headroom on a tough week. " + rec)
    return {"forecast": fc, "outcome": base, "options": options,
            "recommendation": rec, "target": TARGET,
            "modelled": (f"Modelled on {department.name} as set up in the product"
                         + (", calibrated from your uploaded data" if calibration else "")
                         if department is not None else "Modelled on a typical department of this size")}
