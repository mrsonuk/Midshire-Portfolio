"""
Workforce and estates packages: what a change adds, the staff it needs, and
what it costs - all from the scenario's own inputs and the ONE cost service.

A package is a list of levers applied to scenario inputs. Applying one is a
pure function (inputs in, inputs out); the change record says exactly which
rota rows and spaces were added and why. Staffing dependencies are COMPUTED
from the space-staffing table and the current rota (never hard-coded): adding
4 cubicles adds the nurses needed to open them only in the hours the current
rota could not already cover them.
"""
from __future__ import annotations

import copy
import math

from ..workforce.costing import rate_table, rota_cost, shift_hours, WEEKS_PER_YEAR
from ..workforce.roles import ROLES, CONTRACTED_HOURS, AREA_LABEL
from ..workforce.rota import (staffing_by_week, parse_days, days_label, DAYS, _hours_of,
                              hours_of_week)

# the role added when a ratio-staffed space needs more cover
STAFF_ROLE = {"ed_nurse": "band5_nurse", "resus_nurse": "resus_nurse",
              "utc_clinician": "utc_practitioner", "sdec_nurse": "sdec_nurse"}
AREA_OF_STAFF = {"ed_nurse": "Majors", "resus_nurse": "Resus", "utc_clinician": "UTC",
                 "sdec_nurse": "SDEC"}


def _profile_to_rows(extra: list[int], role: str, area: str, reason: str) -> list[dict]:
    """168-hour extra-headcount profile -> rota rows (cut at midnight, then
    identical windows merged across days into one row with a day pattern)."""
    runs = {}
    for d in range(7):
        h = 0
        while h < 24:
            v = extra[d * 24 + h]
            if v <= 0:
                h += 1
                continue
            s = h
            while h < 24 and extra[d * 24 + h] == v:
                h += 1
            runs.setdefault((s, h, v), []).append(d)
    rows = []
    for (s, e, v), days in sorted(runs.items(), key=lambda kv: (kv[1][0], kv[0][0])):
        rows.append({"role": role, "area": area, "days": days_label(days),
                     "start": s, "end": e if e < 24 else 24, "count": int(v), "note": reason})
    return rows


def staff_needed_for_space(inputs: dict, space: str, new_physical: int) -> list[dict]:
    """Rota rows needed so ``new_physical`` spaces can open wherever the
    current rota already opens the space (it is not opened in hours the area
    is currently unstaffed - opening hours are a separate lever)."""
    rule = next((e for e in inputs.get("space_staffing") or [] if e["space"] == space), None)
    if rule is None:
        return []
    k = float(rule["spaces_per_staff"])
    staff = staffing_by_week(inputs["rota"]).get(rule["staff"], [0] * 168)
    need = [0] * 168
    for h in range(168):
        n = staff[h]
        if n <= 0:
            continue
        want = math.ceil(new_physical / k - 1e-9)
        need[h] = max(0, want - n)
    if not any(need):
        return []
    role = STAFF_ROLE.get(rule["staff"])
    if role is None:
        return []
    return _profile_to_rows(need, role, AREA_OF_STAFF.get(rule["staff"], ""),
                            f"needed to open {new_physical} {space.replace('_', ' ')}s at "
                            f"1 : {k:g}")


def apply_lever(inputs: dict, lever: dict) -> tuple[dict, dict]:
    """Return (new inputs, change record). Pure."""
    new = copy.deepcopy(inputs)
    rec = {"lever": lever["id"], "title": lever["title"], "kind": lever["kind"],
           "rota_rows": [], "estate": [], "hours": None, "downstream": None}
    kind = lever["kind"]
    if kind == "shift":
        row = dict(lever["shift"], note=lever["title"])
        new["rota"].append(row)
        rec["rota_rows"].append(row)
    elif kind == "estate":
        space, add = lever["space"], int(lever["add"])
        before = int(new["capacity"].get(space, 0))
        new["capacity"][space] = before + add
        rows = staff_needed_for_space(new, space, before + add)
        for r in rows:
            new["rota"].append(r)
        rec["rota_rows"] += rows
        rec["estate"].append({"item": space, "quantity": add, "before": before, "after": before + add})
    elif kind == "hours":
        area = lever["area"]
        before = list(new["areas"]["hours"].get(area, [0, 24]))
        new["areas"]["hours"][area] = list(lever["hours"])
        if area == "sdec":
            new["sdec"]["hours"] = list(lever["hours"])
        for r in lever.get("staff") or []:
            row = dict(r, note=lever["title"])
            new["rota"].append(row)
            rec["rota_rows"].append(row)
        rec["hours"] = {"area": area, "before": before, "after": list(lever["hours"])}
    elif kind == "downstream":
        param = lever["param"]
        before = new["downstream"].get(param)
        if "add" in lever:
            new["downstream"][param] = before + lever["add"]
            qty = lever["add"]
        else:
            new["downstream"][param] = round(before * float(lever["scale"]), 4)
            qty = lever.get("units", round((float(lever["scale"]) - 1) * 100))
        rec["downstream"] = {"param": param, "before": before, "after": new["downstream"][param]}
        if lever.get("estate_item"):
            rec["estate"].append({"item": lever["estate_item"], "quantity": qty,
                                  "before": before, "after": new["downstream"][param]})
    else:
        raise ValueError(f"unknown lever kind {kind!r}")
    return new, rec


def apply_package(inputs: dict, levers: list[dict]) -> tuple[dict, list[dict]]:
    cur, recs = inputs, []
    for lv in levers:
        cur, r = apply_lever(cur, lv)
        recs.append(r)
    return cur, recs


# --------------------------------------------------------------------------- #
# costing
# --------------------------------------------------------------------------- #
def _headcount_in_window(rota, role, start, end, days):
    """Min and max headcount of ``role`` on shift across a window (baseline)."""
    week = staffing_by_week([r for r in rota if r.get("role") == role]).get(
        ROLES[role]["staffs"], [0] * 168)
    hrs = hours_of_week({"start": start, "end": end, "days": days})
    vals = [week[h] for h in hrs] or [0]
    return min(vals), max(vals)


def contracted_hours(inputs: dict, role: str) -> float:
    entry = ((inputs.get("cost_table") or {}).get("roles") or {}).get(role) or {}
    v = entry.get("contracted_hours_per_week")
    return float(v) if v else float(CONTRACTED_HOURS.get(role, 37.5))


def rota_delta_rows(base_inputs: dict, records: list[dict], cost_inputs: dict | None = None) -> list[dict]:
    """One row per added shift: role, day/time window, baseline staff, proposed,
    change, extra rostered and paid hours per week, WTE, weekly and annual cost."""
    cost_inputs = cost_inputs or base_inputs
    rates = rate_table(cost_inputs["cost_table"])
    out = []
    for rec in records:
        for r in rec["rota_rows"]:
            lo, hi = _headcount_in_window(base_inputs["rota"], r["role"], r["start"], r["end"],
                                          r.get("days"))
            h = shift_hours(r)
            rate = rates.get(r["role"], {}).get("rate")
            wk = None if rate is None else round(h["paid_hours_week"] * rate, 2)
            out.append({
                "role": r["role"], "role_label": ROLES[r["role"]]["label"],
                "area": r.get("area", ""), "days": days_label(parse_days(r.get("days"))),
                "start": int(r["start"]), "end": int(r["end"]),
                "baseline_staff": lo if lo == hi else f"{lo}-{hi}",
                "proposed_staff": (lo + r["count"]) if lo == hi else f"{lo + r['count']}-{hi + r['count']}",
                "change": int(r["count"]),
                "extra_rostered_hours_week": h["rostered_hours_week"],
                "extra_paid_hours_week": h["paid_hours_week"],
                "wte": round(h["paid_hours_week"] / contracted_hours(cost_inputs, r["role"]), 2),
                "contracted_hours_week": contracted_hours(cost_inputs, r["role"]),
                "weekly_cost": wk, "annual_cost": None if wk is None else round(wk * WEEKS_PER_YEAR),
                "costed": wk is not None,
                "why": f"{rec['title']}" + (f" - {r['note']}" if r.get("note") and r["note"] != rec["title"] else "")})
    return out


def estate_rows(records: list[dict], cost_inputs: dict) -> list[dict]:
    items = (cost_inputs.get("estates") or {}).get("items") or {}
    out = []
    for rec in records:
        if rec.get("hours"):
            hb, ha = rec["hours"]["before"], rec["hours"]["after"]
            out.append({"item": f"hours.{rec['hours']['area']}",
                        "label": f"{rec['hours']['area'].upper()} opening hours", "unit": "hours",
                        "quantity": (ha[1] - ha[0]) - (hb[1] - hb[0]),
                        "before": f"{hb[0]:02d}:00-{hb[1]:02d}:00", "after": f"{ha[0]:02d}:00-{ha[1]:02d}:00",
                        "capital": 0, "recurring_non_pay_annual": 0, "capital_costed": True,
                        "recurring_costed": True,
                        "note": "No building. The staff for the extra hours are in the rota rows; other "
                                "running costs of longer opening are not modelled.",
                        "lever": rec["title"]})
        for e in rec["estate"]:
            it = items.get(e["item"], {})
            q = e["quantity"]
            cap, rec_np = it.get("capital"), it.get("recurring_non_pay")
            out.append({
                "item": e["item"], "label": it.get("label", e["item"].replace("_", " ")),
                "unit": it.get("unit", "unit"), "quantity": q,
                "before": e["before"], "after": e["after"],
                "capital": None if cap is None else round(cap * q),
                "recurring_non_pay_annual": None if rec_np is None else round(rec_np * q),
                "capital_costed": cap is not None, "recurring_costed": rec_np is not None,
                "note": it.get("note") or it.get("staffing_not_modelled") or "",
                "lever": rec["title"]})
    return out


def package_finance(base_inputs: dict, pkg_inputs: dict, records: list[dict],
                    cost_inputs: dict | None = None) -> dict:
    """Baseline cost, proposed cost and the difference from the SAME cost
    tables (``cost_inputs``, default: the package's own). Capital and recurring
    are kept separate; they are combined only through the named annualisation."""
    cost_inputs = cost_inputs or pkg_inputs
    rates = cost_inputs["cost_table"]
    base_cost = rota_cost(base_inputs["rota"], rates)
    pkg_cost = rota_cost(pkg_inputs["rota"], rates)
    est = estate_rows(records, cost_inputs)
    rows = rota_delta_rows(base_inputs, records, cost_inputs)
    years = float(((cost_inputs.get("estates") or {}).get("annualisation") or {}).get("capital_years", 15))
    wk_delta = round(pkg_cost["weekly_total"] - base_cost["weekly_total"], 2)
    workforce_complete = base_cost["complete"] and pkg_cost["complete"]
    capital = sum(e["capital"] for e in est if e["capital"] is not None)
    recurring_np = sum(e["recurring_non_pay_annual"] for e in est if e["recurring_non_pay_annual"] is not None)
    uncosted = sorted(set(
        [f"{e['label']} capital" for e in est if not e["capital_costed"]]
        + [f"{e['label']} running cost" for e in est if not e["recurring_costed"]]
        + [f"{ROLES[r]['label']} pay" for r in pkg_cost["uncosted_roles"]]))
    fully_costed = workforce_complete and not uncosted
    recurring_annual = wk_delta * WEEKS_PER_YEAR + recurring_np
    return {
        "baseline_weekly_pay": base_cost["weekly_total"], "proposed_weekly_pay": pkg_cost["weekly_total"],
        "weekly_pay_delta": wk_delta, "annual_pay_delta": round(wk_delta * WEEKS_PER_YEAR),
        "extra_paid_hours_week": round(sum(r["extra_paid_hours_week"] for r in rows), 1),
        "extra_shifts_week": sum(shift_hours(r)["shifts_week"] for rec in records for r in rec["rota_rows"]),
        "extra_wte": round(sum(r["wte"] for r in rows), 2),
        "capital": round(capital), "recurring_non_pay_annual": round(recurring_np),
        "recurring_annual_total": round(recurring_annual),
        "annualised_comparison_cost": round(recurring_annual + capital / years) if years else None,
        "capital_years": years,
        "fully_costed": fully_costed, "not_costed": uncosted,
        "rota_rows": rows, "estate_rows": est,
        "weeks_per_year": WEEKS_PER_YEAR,
        "method": (f"Pay: the same cost table prices the baseline and proposed rotas; the "
                   f"difference is the extra pay (x{WEEKS_PER_YEAR:g} weeks for a year). Estates: unit "
                   f"costs x quantity. Ranking uses the ANNUALISED COMPARISON COST = recurring annual "
                   f"cost + capital / {years:g} years (straight line, no discounting). This is a cost "
                   f"comparison, not a return on investment: annual pay is not a cashable saving.")}


def retime_alternative(base_inputs: dict, records: list[dict]) -> dict:
    """A SEPARATE re-timing scenario that holds paid hours constant where it can:
    for each added shift, move an existing shift of the same role and the same
    length (and break) into the new window instead of adding one. It is never
    applied automatically - it is offered as its own scenario, with every move
    listed, because it takes staff away from the hours they move from."""
    new = copy.deepcopy(base_inputs)
    moves, infeasible = [], []
    for rec in records:
        for r in rec["rota_rows"]:
            length = len(_hours_of(r))
            brk = r.get("unpaid_break_minutes") or 0
            cands = [x for x in new["rota"] if x["role"] == r["role"] and len(_hours_of(x)) == length
                     and (x.get("unpaid_break_minutes") or 0) == brk and int(x["count"]) >= int(r["count"])
                     and parse_days(x.get("days")) == parse_days(r.get("days"))
                     and (int(x["start"]), int(x["end"])) != (int(r["start"]), int(r["end"]))]
            if not cands:
                infeasible.append(f"{ROLES[r['role']]['label']} {r['start']:02d}:00-{r['end']:02d}:00: "
                                  f"no existing shift of the same role, length, break and days to move")
                continue
            src = max(cands, key=lambda x: int(x["count"]))
            src["count"] = int(src["count"]) - int(r["count"])
            row = {k: v for k, v in r.items() if k != "note"}
            row["note"] = f"re-timed from {int(src['start']):02d}:00-{int(src['end']):02d}:00"
            new["rota"].append(row)
            moves.append({"role": ROLES[r["role"]]["label"], "count": int(r["count"]),
                          "days": days_label(parse_days(r.get("days"))),
                          "from": f"{int(src['start']):02d}:00-{int(src['end']):02d}:00",
                          "to": f"{int(r['start']):02d}:00-{int(r['end']):02d}:00"})
    # a shift moved away entirely stays as a 0-count row: an explicit, visible zero
    # estate changes cannot be re-timed: they are carried over unchanged
    from ..workforce.costing import rota_cost
    paid = lambda rota: sum(r["paid_hours_week"] for r in rota_cost(rota, {})["rows"])
    return {"inputs": new, "moves": moves, "infeasible": infeasible,
            "paid_hours_delta": round(paid(new["rota"]) - paid(base_inputs["rota"]), 2),
            "note": "Re-timing moves existing shifts into the window the package needed, keeping paid "
                    "hours the same. It takes cover away from the hours the shifts move FROM - check "
                    "those hours before using it. Simulate it like any other scenario."}
