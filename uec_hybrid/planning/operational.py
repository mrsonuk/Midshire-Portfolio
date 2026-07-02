"""
Operational "today / this week" view.

A different audience and decision from winter planning: a site / flow manager
asking "today is shaping up badly - what do I flex now?" The levers here cost no
capital (discharge push, SDEC hours, staff flex, escalation space, redirect to
UTC, community calls), framed by effort and who owns them, with an OPEL-style risk
read that operational teams recognise. Same hidden engine; same plain language.
"""
from __future__ import annotations

from .planner import build_department, _spread, TARGET

# No-capital actions a manager can take today, each as an engine change.
ACTIONS = [
    {"id": "discharge", "label": "Push discharges - get more inpatients out by midday",
     "sd": {"ward_discharge_capacity_per_hour": "*1.3"},
     "effort": "Board round + criteria-to-reside review", "owner": "Ward / discharge teams"},
    {"id": "sdec", "label": "Open SDEC longer today / pull the SDEC consultant forward",
     "resources": {"sdec_chair": "*1.4", "specialty_doctor": "+1"},
     "effort": "Roster / specialty pull", "owner": "Site + specialties"},
    {"id": "doctors", "label": "Flex an extra doctor to the evening peak",
     "resources": {"ed_doctor": "+1"},
     "effort": "Rota flex", "owner": "ED rota coordinator"},
    {"id": "escalation", "label": "Open escalation cubicles",
     "resources": {"cubicle": "+4"},
     "effort": "Open escalation area + staff it", "owner": "Site manager"},
    {"id": "redirect", "label": "Stream more minors to fit-to-sit / UTC",
     "divert": {"classes": ["Acuity 4", "Acuity 5"], "fraction": 0.15},
     "effort": "Front-door streaming", "owner": "Front door / navigation"},
    {"id": "community", "label": "Call community / UCR to take referrals today",
     "sd": {"community_capacity": "*1.4", "community_clearance_per_hour": "*1.4"},
     "effort": "Phone referrals", "owner": "ICB / community teams"},
]


def _opel(four_hour, fullness):
    if four_hour >= 85 and fullness < 92:
        return {"level": 1, "label": "OPEL 1 - manageable", "colour": "green"}
    if four_hour >= TARGET and fullness < 95:
        return {"level": 2, "label": "OPEL 2 - under pressure", "colour": "amber"}
    if four_hour >= 68:
        return {"level": 3, "label": "OPEL 3 - serious pressure", "colour": "orange"}
    return {"level": 4, "label": "OPEL 4 - critical (corridor care / divert risk)", "colour": "red"}


def _with_fullness(raw, fullness):
    raw["sd"]["baseline_bed_occupancy"] = max(0.6, min(0.99, fullness / 100.0))
    return raw


def today_plan(attendances_today=340, hospital_fullness_pct=94.0,
               department=None, calibration=None) -> dict:
    base_raw, fc = build_department(attendances_today, winter_uplift_pct=0,
                                    department=department, calibration=calibration)
    _with_fullness(base_raw, hospital_fullness_pct)
    base = _spread(base_raw, reps=5)
    risk = _opel(base["typical"], hospital_fullness_pct)

    actions = []
    for a in ACTIONS:
        raw, _ = build_department(attendances_today, winter_uplift_pct=0, extra=a,
                                  department=department, calibration=calibration)
        _with_fullness(raw, hospital_fullness_pct)
        res = _spread(raw, reps=4, seed=800)
        actions.append({
            "id": a["id"], "label": a["label"], "effort": a["effort"], "owner": a["owner"],
            "four_hour": res["typical"], "delta": res["typical"] - base["typical"],
            "corridor_relief": round(base["corridor_per_day"] - res["corridor_per_day"], 1)})
    actions.sort(key=lambda x: x["delta"], reverse=True)

    top = actions[0] if actions else None
    if base["bed_occupancy"] >= 92 and top and top["id"] != "discharge":
        # if the hospital is full, getting people OUT is the lever that counts
        disc = next((x for x in actions if x["id"] == "discharge"), None)
        if disc and disc["delta"] >= top["delta"] - 1:
            top = disc
    first = (f"Do this first: <b>{top['label'].lower()}</b> - it buys you about "
             f"{max(0, top['delta'])} points on the 4-hour standard today "
             f"({top['owner']})." if top else "")
    headline = (f"Today is shaping up as a {'tough' if risk['level'] >= 3 else 'busy'} day: "
                f"about {fc['expected_per_day']} attendances and the hospital "
                f"{hospital_fullness_pct:.0f}% full. Do nothing and you're heading for "
                f"about {base['typical']}% on the 4-hour standard, with around "
                f"{base['corridor_per_day']} patients waiting over 12 hours for a bed.")
    return {"expected_today": fc["expected_per_day"], "fullness": round(hospital_fullness_pct),
            "risk": risk, "do_nothing": {"four_hour": base["typical"],
            "corridor_per_day": base["corridor_per_day"]},
            "headline": headline, "actions": actions, "first": first, "target": TARGET,
            "modelled": (f"Modelled on {department.name} as set up in the product"
                         + (", calibrated from your uploaded data" if calibration else "")
                         if department is not None else "Modelled on a typical department of this size")}
