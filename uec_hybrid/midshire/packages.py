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
           "rota_rows": [], "estate": [], "hours": None, "downstream": None, "moves": [], "process": None}
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
    elif kind == "move":
        # move existing staff to other hours: same role, shift length, break and
        # days, so paid hours do not change and nothing is added
        mv = lever["move"]
        src = move_source(new["rota"], mv)
        if src is None:
            raise ValueError(f"{lever['title']}: there is no existing shift to move")
        src["count"] = int(src["count"]) - int(mv["count"])
        row = {k: v for k, v in src.items() if k != "note"}
        row.update({"start": int(mv["to"][0]), "end": int(mv["to"][1]), "count": int(mv["count"]),
                    "note": lever["title"]})
        new["rota"].append(row)
        rec["moves"].append({"role": mv["role"], "count": int(mv["count"]), "days": mv.get("days") or "Mon-Sun",
                             "from": list(mv["from"]), "to": list(mv["to"])})
    elif kind == "process":
        # a change in how the department works; its size is an assumption
        param = lever["param"]
        proc = new.setdefault("process", {})
        before = float(proc.get(param, 1.0))
        proc[param] = round(before * float(lever["scale"]), 4)
        rec["process"] = {"param": param, "before": before, "after": proc[param]}
        if lever.get("estate_item"):
            rec["estate"].append({"item": lever["estate_item"], "quantity": lever.get("units", 0),
                                  "before": before, "after": proc[param]})
    else:
        raise ValueError(f"unknown lever kind {kind!r}")
    return new, rec


def move_source(rota: list, mv: dict):
    """The existing shift a move takes staff from: same role, days, start and
    end, with enough staff on it. The new hours must be the same length."""
    def length(s, e):
        return (int(e) - int(s)) % 24 or 24
    if length(*mv["from"]) != length(*mv["to"]):
        raise ValueError("a moved shift must keep its length")
    for r in rota:
        if (r.get("role") == mv["role"] and parse_days(r.get("days")) == parse_days(mv.get("days"))
                and (int(r["start"]), int(r["end"])) == (int(mv["from"][0]), int(mv["from"][1]))
                and int(r.get("count") or 0) >= int(mv["count"])):
            return r
    return None


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
    # the pay difference straight from the change in paid hours by role: the same
    # rates, but without the per-row penny rounding, so moving staff between shifts
    # (same hours) is exactly £0 rather than a penny either way
    table = rate_table(rates)
    hb, hp = base_cost["paid_hours_by_role"], pkg_cost["paid_hours_by_role"]
    wk_delta = round(sum((hp.get(r, 0.0) - hb.get(r, 0.0)) * table[r]["rate"] for r in set(hb) | set(hp)
                         if table.get(r, {}).get("rate") is not None), 2) + 0.0
    workforce_complete = base_cost["complete"] and pkg_cost["complete"]
    capital = sum(e["capital"] for e in est if e["capital"] is not None)
    recurring_np = sum(e["recurring_non_pay_annual"] for e in est if e["recurring_non_pay_annual"] is not None)
    uncosted = sorted(set(
        [e["label"] for e in est if not e["capital_costed"] and not e["recurring_costed"]]
        + [f"{e['label']} capital" for e in est if not e["capital_costed"] and e["recurring_costed"]]
        + [f"{e['label']} running cost" for e in est if not e["recurring_costed"] and e["capital_costed"]]
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


# --------------------------------------------------------------------------- #
# plain-language descriptions (what a scenario or package changes)
# --------------------------------------------------------------------------- #
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
                8: "eight", 9: "nine", 10: "ten", 20: "twenty"}
SPACE_WORDS = {"cubicle": "majors cubicle", "resus_bay": "resus bay", "fit_to_sit_chair": "fit-to-sit space",
               "utc_room": "UTC room", "sdec_chair": "SDEC chair", "handover_bay": "ambulance handover bay",
               "ct_scanner": "CT scanner", "xray_room": "X-ray room", "fau_bed": "frailty unit bed",
               "minor_injury_space": "minor injury space"}
ROLE_WORDS = {"streaming_nurse": "streaming nurse", "rat_consultant": "senior RAT clinician",
              "ed_consultant": "ED consultant", "em_registrar": "ED registrar", "em_sho": "ED junior doctor",
              "sdec_doctor": "SDEC doctor", "frailty_pract": "frailty practitioner",
              "mh_liaison": "mental health liaison clinician", "band6_nurse": "Band 6 ED nurse",
              "band5_nurse": "Band 5 ED nurse", "enp": "emergency nurse practitioner",
              "hca": "healthcare assistant", "porter": "porter", "receptionist": "receptionist",
              "resus_nurse": "resus nurse", "utc_practitioner": "UTC practitioner", "sdec_nurse": "SDEC nurse"}
STAFF_WORDS = {"ed_nurse": "nurse", "resus_nurse": "resus nurse", "utc_clinician": "UTC practitioner",
               "sdec_nurse": "SDEC nurse"}
AREA_WORDS = {"sdec": "SDEC", "utc": "the UTC", "frailty": "the frailty unit", "rat": "RAT",
              "fit_to_sit": "fit-to-sit"}
DAY_WORDS = {"Mon-Sun": "every day", "Mon-Fri": "Monday to Friday", "Sat-Sun": "at weekends",
             "Mon": "on Mondays", "Tue": "on Tuesdays", "Wed": "on Wednesdays", "Thu": "on Thursdays",
             "Fri": "on Fridays", "Sat": "on Saturdays", "Sun": "on Sundays"}


def _count_words(n: int, noun: str) -> str:
    word = NUMBER_WORDS.get(n, str(n))
    return f"{word} {noun}{'' if n == 1 else 's'}"


def _clock(h: int, end: bool = False) -> str:
    h = int(h)
    if end and h in (0, 24):
        return "midnight"
    return f"{h % 24:02d}:00"


def _days_words(days) -> str:
    return DAY_WORDS.get(days or "Mon-Sun", f"on {days}")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def describe_changes(base: dict, inputs: dict) -> list[str]:
    """What a scenario changes compared with the baseline, as short sentences
    a stakeholder can read. Computed from the inputs themselves, so it is
    right for every scenario: searched, saved, or edited by hand."""
    out = []
    agg = {}
    for sign, rota in ((-1, base.get("rota", [])), (1, inputs.get("rota", []))):
        for r in rota:
            key = (r["role"], r.get("days") or "Mon-Sun", int(r["start"]), int(r["end"]))
            try:
                n = int(r.get("count") or 0)
            except (TypeError, ValueError):
                n = 0
            agg[key] = agg.get(key, 0) + sign * n
    def hours_words(s, e):
        return "around the clock" if s == 0 and e in (0, 24) else f"{_clock(s)} to {_clock(e, end=True)}"
    agg = {k: n for k, n in agg.items() if n}
    # the same role and days losing staff on one shift and gaining them on another
    # shift of the same length is a move, not a cut plus an addition
    for k_from in sorted([k for k, n in agg.items() if n < 0], key=lambda k: (k[0], k[2])):
        for k_to in sorted([k for k, n in agg.items() if n > 0], key=lambda k: (k[0], k[2])):
            same = k_from[0] == k_to[0] and k_from[1] == k_to[1] and \
                ((k_from[3] - k_from[2]) % 24 or 24) == ((k_to[3] - k_to[2]) % 24 or 24)
            m = min(-agg[k_from], agg[k_to]) if same else 0
            if m > 0:
                who = ROLE_WORDS.get(k_from[0], k_from[0].replace("_", " "))
                out.append(f"Move {_count_words(m, who)} from the {hours_words(k_from[2], k_from[3])} shift to "
                           f"a {hours_words(k_to[2], k_to[3])} shift, {_days_words(k_from[1])}. No extra hours.")
                agg[k_from] += m
                agg[k_to] -= m
    for (role, days, s, e), n in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        if n == 0:
            continue
        who = ROLE_WORDS.get(role, role.replace("_", " "))
        span = f"{hours_words(s, e)}, {_days_words(days)}"
        out.append(f"{'Add' if n > 0 else 'Remove'} {_count_words(abs(n), who)}, {span}.")
    for k, v in inputs.get("capacity", {}).items():
        try:
            d = int(v or 0) - int(base.get("capacity", {}).get(k) or 0)
        except (TypeError, ValueError):
            continue
        if d:
            out.append(f"{'Add' if d > 0 else 'Remove'} {_count_words(abs(d), SPACE_WORDS.get(k, k.replace('_', ' ')))}.")
    bss = {r["space"]: r for r in base.get("space_staffing", [])}
    for r in inputs.get("space_staffing", []):
        b = bss.get(r["space"])
        if b and b.get("spaces_per_staff") != r.get("spaces_per_staff"):
            out.append(f"Each {STAFF_WORDS.get(r['staff'], r['staff'].replace('_', ' '))} opens "
                       f"{r['spaces_per_staff']:g} {SPACE_WORDS.get(r['space'], r['space'])}s "
                       f"(was {b['spaces_per_staff']:g}).")
    for a, h in inputs.get("areas", {}).get("hours", {}).items():
        bh = base.get("areas", {}).get("hours", {}).get(a)
        if bh and list(bh) != list(h):
            out.append(f"Open {AREA_WORDS.get(a, a)} {_clock(h[0])} to {_clock(h[1], end=True)} "
                       f"(was {_clock(bh[0])} to {_clock(bh[1], end=True)}).")
    bd, dd = base.get("downstream", {}), inputs.get("downstream", {})
    if dd.get("inpatient_beds") != bd.get("inpatient_beds") and dd.get("inpatient_beds") is not None:
        d = int(dd["inpatient_beds"]) - int(bd.get("inpatient_beds") or 0)
        out.append(f"{'Open' if d > 0 else 'Close'} {abs(d)} {'more ' if d > 0 else ''}inpatient bed{'' if abs(d) == 1 else 's'}.")
    if dd.get("mh_beds") != bd.get("mh_beds") and dd.get("mh_beds") is not None:
        d = int(dd["mh_beds"]) - int(bd.get("mh_beds") or 0)
        out.append(f"{'Open' if d > 0 else 'Close'} {abs(d)} mental health bed{'' if abs(d) == 1 else 's'}.")
    if dd.get("ward_discharge_capacity_per_hour") != bd.get("ward_discharge_capacity_per_hour") and bd.get("ward_discharge_capacity_per_hour"):
        pct = round(100 * (dd["ward_discharge_capacity_per_hour"] / bd["ward_discharge_capacity_per_hour"] - 1))
        out.append(f"Wards discharge patients {abs(pct)}% {'faster' if pct > 0 else 'slower'} "
                   f"(an assumed improvement, not costed).")
    dts = float((inputs.get("process") or {}).get("decision_time_scale", 1.0))
    bdts = float((base.get("process") or {}).get("decision_time_scale", 1.0))
    if abs(dts - bdts) > 1e-9:
        pct = round(100 * (1 - dts / bdts))
        out.append(f"Results, reviews and decisions take {abs(pct)}% {'less' if pct > 0 else 'more'} time "
                   f"(an assumed improvement, not costed).")
    ds = (inputs.get("cohort") or {}).get("demand_scale", 1.0) or 1.0
    bs = (base.get("cohort") or {}).get("demand_scale", 1.0) or 1.0
    if abs(ds - bs) > 1e-9:
        pct = round(100 * (ds / bs - 1))
        out.append(f"{abs(pct)}% {'more' if pct > 0 else 'fewer'} patients arriving than in the baseline.")
    if not out and (inputs.get("cost_table") != base.get("cost_table") or inputs.get("estates") != base.get("estates")):
        out.append("Cost rates changed. Patient flow is the same as the baseline.")
    return out or ["No changes from the baseline."]


def lever_text(lever_id: str) -> dict:
    from . import config as mcfg
    lt = mcfg.fixture().get("lever_text", {})
    return lt.get(lever_id) or {"name": lever_id, "short": lever_id, "change": "", "why": "", "look_for": ""}


def _join(words: list[str]) -> str:
    words = [w for w in words if w]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


MODE_WORDS = {"workforce": "staffing changes only", "estate": "space and bed changes, with the staff they need",
              "combined": "staffing, space and bed changes",
              "no_extra": "no extra staff, space or beds"}


def describe_package(ids: list[str], mode: str | None = None, target: dict | None = None,
                     outcome: str | None = None) -> dict:
    """A name and short descriptions for a package of tested changes."""
    from . import config as mcfg
    cat = {lv["id"]: lv for lv in mcfg.fixture()["search"]["levers"]}
    levers = [cat.get(i, {}) for i in ids]
    texts = [lever_text(i) for i in ids]
    if len(texts) == 1:
        t = texts[0]
        return {"name": t["name"], "what": [t["change"]], "why": t["why"], "look_for": t["look_for"]}
    additive = all(lv.get("kind") in ("shift", "estate") or lv.get("add") for lv in levers)
    shorts = [t["short"] for t in texts]
    name = ("Add " + _join(shorts)) if additive else _cap(_join(shorts))
    aim = (f"{target['pct']:g}% within {int(target['minutes']) // 60} hours"
           if target and int(target["minutes"]) % 60 == 0 else
           (f"{target['pct']:g}% within {int(target['minutes'])} minutes" if target else "the target"))
    why = ("The lowest-cost combination the model found that reaches " + aim
           if outcome in ("met", "already_met") else
           "The strongest combination the model found when aiming for " + aim)
    if mode in MODE_WORDS:
        why += ", using " + MODE_WORDS[mode]
    looks = []
    for t in texts:
        if t["look_for"] and t["look_for"] not in looks:
            looks.append(t["look_for"])
    return {"name": name, "what": [t["change"] for t in texts], "why": why + ".",
            "look_for": " ".join(looks[:3])}
