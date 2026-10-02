"""
The "are you staffed for the demand curve?" view: per staff area, the headcount by
hour against the arrivals shape, the hours where staffing lags demand, plus the
weekly pay-bill - all in plain terms for an ED ops/workforce lead.

``staffing_and_cost`` is pure and simulation-free, so the rota editor can preview a
change instantly; ``workforce_view`` wraps it for a whole department.
"""
from __future__ import annotations

from .rota import staffing_by_hour, weekly_cost, cost_breakdown, understaffed_hours, day_profile
from .roles import STAFF_RESOURCES, SUPPORT_RESOURCES, RATIO_RESOURCES, AREA_LABEL, ROLES


def _demand_profile(attendances_per_day: float) -> list[float]:
    from ..demand.profile import HOURLY
    tot = sum(HOURLY) or 1
    return [h * attendances_per_day / tot for h in HOURLY]


def staffing_and_cost(rota, attendances_per_day: float, present=None,
                      ratio_staff=None) -> dict:
    """Staffing-vs-demand and cost for a rota - no simulation, instant.

    ``present`` optionally restricts the staff areas shown (e.g. only those the
    department actually has); ``None`` shows every staffed area in the rota.
    ``ratio_staff`` names the ratio-constrained staff areas in force (default:
    ED nursing, plus any other ratio area the rota actually rosters).

    The "light against demand" hours are a SECONDARY demand-shape indicator
    (see ``understaffed_hours``): they compare the shape of staffing with the
    shape of arrivals and say nothing about whether a headcount is enough.
    """
    staffing = staffing_by_hour(rota)
    demand = _demand_profile(attendances_per_day)
    rostered = {ROLES[sh["role"]]["staffs"] for sh in rota if sh.get("role") in ROLES}
    ratio_on = set(ratio_staff) if ratio_staff is not None else (
        {"ed_nurse"} | (RATIO_RESOURCES & rostered))

    areas = []
    for res in STAFF_RESOURCES + SUPPORT_RESOURCES:
        # engine-constraining areas follow the department's set-up; ratio-
        # constrained nursing and the cost-only support workforce are always
        # shown (they never appear in a built pathway's resource list).
        if res in RATIO_RESOURCES and res not in ratio_on:
            continue
        if (res in STAFF_RESOURCES and res not in RATIO_RESOURCES
                and present is not None and res not in present):
            continue
        if res not in staffing:
            continue
        s = [int(round(x)) for x in day_profile(staffing[res])]
        under = understaffed_hours(s, demand)
        areas.append({
            "resource": res, "label": AREA_LABEL.get(res, res),
            "staffing": s, "peak": max(s), "overnight": min(s),
            "understaffed_hours": under,
            "understaffed_basis": "demand-shape heuristic (secondary indicator)",
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
    """The workforce view of the rota the ENGINE runs (the resolved rota: the
    template scaled to the department, or the supplied rota as given) - so the
    staffing shown and the pay-bill quoted are the staffing simulated."""
    from ..department.builder import build
    raw = build(dept)
    present = set(raw.get("resources", {}))
    uec = raw.get("uec") or {}
    ratio_staff = {e.get("staff") for e in uec.get("space_staffing") or []}
    out = staffing_and_cost(uec.get("resolved_rota", dept.rota), dept.attendances_per_day,
                            present=present, ratio_staff=ratio_staff or {"ed_nurse"})
    out["rota_provenance"] = uec.get("rota_provenance")
    return out
