"""
The "are you staffed for the demand curve?" view: per staff area, the headcount by
hour against the arrivals shape, the hours where staffing lags demand, plus the
weekly pay-bill — all in plain terms for an ED ops/workforce lead.
"""
from __future__ import annotations

from .rota import staffing_by_hour, weekly_cost, cost_breakdown, understaffed_hours
from .roles import STAFF_RESOURCES, AREA_LABEL, ROLES


def _demand_profile(dept) -> list[float]:
    from ..planning.forecast import HOURLY
    tot = sum(HOURLY) or 1
    return [h * dept.attendances_per_day / tot for h in HOURLY]


def workforce_view(dept) -> dict:
    staffing = staffing_by_hour(dept.rota)
    demand = _demand_profile(dept)
    # which staff areas the department actually has (areas may be switched off)
    from ..department.builder import build
    present = set(build(dept).get("resources", {}))

    areas = []
    for res in STAFF_RESOURCES:
        if res not in present:
            continue
        s = staffing[res]
        under = understaffed_hours(s, demand)
        areas.append({
            "resource": res, "label": AREA_LABEL.get(res, res),
            "staffing": s, "peak": max(s), "overnight": min(s),
            "understaffed_hours": under,
            "roles": [{"id": r, "label": ROLES[r]["label"]} for r in ROLES if ROLES[r]["staffs"] == res],
        })
    # a plain headline about the worst-staffed window
    worst = max(areas, key=lambda a: len(a["understaffed_hours"]), default=None)
    headline = "Your staffing broadly matches demand through the day."
    if worst and worst["understaffed_hours"]:
        hrs = worst["understaffed_hours"]
        span = f"{min(hrs):02d}:00–{(max(hrs)+1) % 24:02d}:00"
        headline = (f"{worst['label']} look light against demand around {span} — "
                    f"the most likely time you’ll fall behind.")
    return {
        "demand": [round(x, 1) for x in demand],
        "areas": areas,
        "weekly_cost": int(weekly_cost(dept.rota)),
        "cost_breakdown": cost_breakdown(dept.rota),
        "headline": headline,
    }
