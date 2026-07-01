"""
Rota → staffing by hour, cost, and the "are you staffed for the curve?" check.

A rota is a list of shifts::

    {"role": "ed_consultant", "start": 8, "end": 20, "count": 2}

Shifts may wrap past midnight (end <= start means it runs into the next day).
From the rota we build, for every staff area, a 24-length by-hour headcount the
engine consumes directly, plus the weekly pay-bill and the hours where staffing
falls behind demand.
"""
from __future__ import annotations

from .roles import ROLES, STAFF_RESOURCES, SUPPORT_RESOURCES


def _hours_of(shift) -> list[int]:
    s, e = int(shift["start"]) % 24, int(shift["end"]) % 24
    if shift["end"] == shift["start"]:
        return list(range(24))
    if e > s:
        return list(range(s, e))
    return list(range(s, 24)) + list(range(0, e))      # wraps midnight


def staffing_by_hour(rota: list[dict]) -> dict[str, list[int]]:
    """Per staff area, the headcount on shift each hour (sum of its roles)."""
    cap = {r: [0] * 24 for r in STAFF_RESOURCES + SUPPORT_RESOURCES}
    for sh in rota:
        role = ROLES.get(sh["role"])
        if not role:
            continue
        res = role["staffs"]
        for h in _hours_of(sh):
            cap[res][h] += int(sh.get("count", 1))
    # never below 1 (a department always has someone on)
    for r in cap:
        cap[r] = [max(1, c) for c in cap[r]]
    return cap


def weekly_cost(rota: list[dict]) -> float:
    daily = 0.0
    for sh in rota:
        role = ROLES.get(sh["role"])
        if not role:
            continue
        daily += int(sh.get("count", 1)) * len(_hours_of(sh)) * role["cost"]
    return round(daily * 7, 0)


def cost_breakdown(rota: list[dict]) -> dict:
    by_role = {}
    for sh in rota:
        role = ROLES.get(sh["role"])
        if not role:
            continue
        c = int(sh.get("count", 1)) * len(_hours_of(sh)) * role["cost"] * 7
        by_role[sh["role"]] = by_role.get(sh["role"], 0) + c
    return {"weekly_total": weekly_cost(rota), "by_role": {k: round(v) for k, v in by_role.items()}}


def understaffed_hours(staffing: list[int], demand_profile: list[float]) -> list[int]:
    """Hours where staffing lags demand: compares each as a share of its daily
    total and flags hours where demand's share materially exceeds staffing's."""
    sd, dd = sum(staffing) or 1, sum(demand_profile) or 1
    out = []
    for h in range(24):
        if demand_profile[h] / dd - staffing[h] / sd > 0.012:   # demand-heavy, staff-light
            out.append(h)
    return out
