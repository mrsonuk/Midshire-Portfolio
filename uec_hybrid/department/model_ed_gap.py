"""
Model ED gap analysis: which high-performing Model ED elements the department has,
which it's missing, and - for each gap - its modelled benefit **measured the right
way**. Front-door areas (UTC, RAT, fit-to-sit, children's) are judged on 4-hour
flow; same-day / assessment areas (SDEC, EEMAC, CDU, frailty, MH) are judged on the
admissions they avoid and the long (12-hour) waits they cut, because those patients
are inherently a >4-hour cohort.
"""
from __future__ import annotations

import numpy as np

from .config import AREAS, Department
from .builder import build
from ..des.pathway import Pathway
from ..coupling.cosim import run_cosim
from ..analysis.metrics import kpis, uec_metrics

ADD_COST = {"rat": "Moderate", "utc": "High", "fit_to_sit": "Low", "paeds": "High",
            "eemac": "High", "sdec": "High", "cdu": "Moderate", "frailty": "Moderate", "mh": "Moderate"}
FLOW = {"utc", "rat", "fit_to_sit", "paeds"}      # judged on 4-hour
ADMIT_AVOID = {"sdec", "eemac", "cdu", "frailty", "mh"}   # judged on admissions / 12-hour


def _bundle(dept: Department, reps=3, seed=400) -> dict:
    p = Pathway.from_dict(build(dept))
    runs = []
    for i in range(reps):
        r = run_cosim(p, seed=seed + i)
        runs.append({**kpis(r, p), **uec_metrics(r, p)})
    return {k: float(np.mean([x.get(k, 0) for x in runs]))
            for k in ("four_hour", "twelve_hour", "admit_rate", "bed_occupancy")}


def gap_analysis(dept: Department) -> dict:
    base = _bundle(dept)
    att = dept.attendances_per_day
    present, missing = [], []
    for key, a in AREAS.items():
        if key in dept.enabled:
            present.append({"key": key, "label": a["label"], "why": a["why"]})
            continue
        after = _bundle(Department.from_dict({**dept.to_dict(), "enabled": dept.enabled + [key]}))
        four_delta = round(after["four_hour"] - base["four_hour"])
        adm_avoided = round(max(0.0, (base["admit_rate"] - after["admit_rate"]) / 100 * att), 1)
        twelve_delta = round(base["twelve_hour"] - after["twelve_hour"], 1)
        if key in FLOW:
            value, unit = four_delta, "pts on 4-hr"
            benefit = f"Speeds front-door flow - about {four_delta:+d} points on the 4-hour standard."
            score = four_delta
        else:
            value, unit = adm_avoided, "fewer admits/day"
            extra = f" and cuts long (12-hour) waits by {twelve_delta:.1f} points" if twelve_delta > 0.2 else ""
            benefit = f"Same-day / assessment pathway - avoids about {adm_avoided:.0f} admissions a day{extra}, easing bed pressure."
            score = adm_avoided * 4 + max(0, twelve_delta)   # comparable magnitude
        missing.append({"key": key, "label": a["label"], "why": a["why"], "cost": ADD_COST.get(key, "Moderate"),
                        "value": value, "unit": unit, "benefit": benefit, "four_after": round(after["four_hour"]),
                        "_score": score})
    missing.sort(key=lambda m: m["_score"], reverse=True)
    for m in missing:
        m.pop("_score", None)
    return {"baseline_four_hour": round(base["four_hour"]),
            "baseline_admit": round(base["admit_rate"]),
            "have": len(present), "total": len(AREAS), "present": present, "missing": missing}
