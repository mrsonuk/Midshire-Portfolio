"""
The "are you staffed for the demand curve?" view: per staff area, the headcount by
hour against the arrivals shape, the hours where staffing lags demand, plus the
weekly pay-bill - all in plain terms for an ED ops/workforce lead.

``staffing_and_cost`` is pure and simulation-free, so the rota editor can preview a
change instantly; ``workforce_view`` wraps it for a whole department.
"""
from __future__ import annotations

from .rota import staffing_by_hour, weekly_cost, cost_breakdown, understaffed_hours
from .roles import STAFF_RESOURCES, SUPPORT_RESOURCES, AREA_LABEL, ROLES


def _demand_profile(attendances_per_day: float) -> list[float]:
    from ..planning.forecast import HOURLY
    tot = sum(HOURLY) or 1
    return [h * attendances_per_day / tot for h in HOURLY]


def staffing_and_cost(rota, attendances_per_day: float, present=None) -> dict:
    """Staffing-vs-demand and cost for a rota - no simulation, instant.

    ``present`` optionally restricts the staff areas shown (e.g. only those the
    department actually has); ``None`` shows every staffed area in the rota.
    """
    staffing = staffing_by_hour(rota)
    demand = _demand_profile(attendances_per_day)

    areas = []
    for res in STAFF_RESOURCES + SUPPORT_RESOURCES:
        # engine-constraining areas follow the department's set-up; the support
        # workforce (nursing, ENPs, HCAs, porters, reception) is always shown -
        # it is rostered and costed even though it doesn't limit flow yet.
        if res in STAFF_RESOURCES and present is not None and res not in present:
            continue
        if res not in staffing:
            continue
        s = staffing[res]
        under = understaffed_hours(s, demand)
        areas.append({
            "resource": res, "label": AREA_LABEL.get(res, res),
            "staffing": s, "peak": max(s), "overnight": min(s),
            "understaffed_hours": under,
            "advisory": res in SUPPORT_RESOURCES,
            "roles": [{"id": r, "label": ROLES[r]["label"]} for r in ROLES if ROLES[r]["staffs"] == res],
        })
    # a plain headline about the worst-staffed window
    worst = max(areas, key=lambda a: len(a["understaffed_hours"]), default=None)
    headline = "Your staffing broadly matches demand through the day."
    if worst and worst["understaffed_hours"]:
        hrs = worst["understaffed_hours"]
        span = f"{min(hrs):02d}:00-{(max(hrs)+1) % 24:02d}:00"
        headline = (f"{worst['label']} look light against demand around {span} - "
                    f"the most likely time you’ll fall behind.")
    return {
        "demand": [round(x, 1) for x in demand],
        "areas": areas,
        "weekly_cost": int(weekly_cost(rota)),
        "cost_breakdown": cost_breakdown(rota),
        "headline": headline,
    }


def workforce_view(dept) -> dict:
    # which staff areas the department actually has (areas may be switched off)
    from ..department.builder import build
    present = set(build(dept).get("resources", {}))
    return staffing_and_cost(dept.rota, dept.attendances_per_day, present=present)
