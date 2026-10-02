"""
Rota → staffing by hour, cost, and the "are you staffed for the curve?" check.

A rota is a list of shift rows::

    {"role": "ed_consultant", "start": 8, "end": 20, "count": 2,
     "days": "Mon-Sun", "unpaid_break_minutes": 30, "area": "Majors"}

Conventions, stated once and applied everywhere (editor, engine, cost):

* **Hours are whole hours, 0-24.** ``end <= start`` means the shift runs past
  midnight into the next day, and the shift BELONGS TO THE DAY IT STARTS: a
  ``Mon 20-08`` row covers Monday 20:00-24:00 and Tuesday 00:00-08:00.
  ``start 0, end 24`` is a 24-hour shift.
* **days** (optional) is the day pattern the row repeats on: a list such as
  ``["Mon", "Wed"]`` or a string ``"Mon-Fri"``, ``"Sat,Sun"``, ``"weekdays"``,
  ``"weekends"``, ``"Mon-Sun"``/``"daily"``. A row WITHOUT days is a legacy
  daily row and repeats seven days a week - that is the documented migration
  rule for existing rota files. A Monday-only row is one shift a week, never
  seven.
* **count** is the headcount on shift. 0 is a real answer (nobody rostered)
  and is kept; a blank count is MISSING and the row is rejected, never read
  as 0 or as 1.
* **unpaid_break_minutes** (optional, default 0) reduces PAID hours for costing.
  The engine treats everyone rostered as present for the whole rostered window
  (breaks covered by colleagues) - a stated simplification.

Staffing is whatever the rota says: an hour nobody is rostered for has ZERO
staff. (It used to be silently floored to one, which put a fictitious member of
staff on every empty hour.)
"""
from __future__ import annotations

import csv
import io
import re

from .roles import ROLES, STAFF_RESOURCES, SUPPORT_RESOURCES, RATIO_RESOURCES, role_rates

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY_ALIASES = {d.lower(): i for i, d in enumerate(DAYS)}
_DAY_ALIASES.update({"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                     "friday": 4, "saturday": 5, "sunday": 6, "tues": 1, "weds": 2,
                     "thur": 3, "thurs": 3})
ALL_DAYS = list(range(7))


class RotaError(ValueError):
    """A rota row that cannot be used as given."""


def parse_days(value) -> list[int]:
    """Day pattern -> sorted day indices (Mon=0). None/blank -> all seven days
    (the legacy daily rule). Raises RotaError on anything it cannot read."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return list(ALL_DAYS)
    if isinstance(value, (list, tuple)):
        out = set()
        for v in value:
            if isinstance(v, int) and 0 <= v <= 6:
                out.add(v)
            else:
                out.update(parse_days(str(v)))
        if not out:
            raise RotaError("day pattern is empty")
        return sorted(out)
    s = str(value).strip().lower().replace(" ", "")
    if s in ("daily", "everyday", "all", "mon-sun", "7days"):
        return list(ALL_DAYS)
    if s in ("weekdays", "mon-fri"):
        return [0, 1, 2, 3, 4]
    if s in ("weekends", "weekend", "sat-sun", "sat,sun"):
        return [5, 6]
    out = set()
    for part in s.split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if a not in _DAY_ALIASES or b not in _DAY_ALIASES:
                raise RotaError(f"unknown day range {part!r}")
            i, j = _DAY_ALIASES[a], _DAY_ALIASES[b]
            k = i
            while True:                       # ranges may wrap (Sat-Mon)
                out.add(k)
                if k == j:
                    break
                k = (k + 1) % 7
        elif part in _DAY_ALIASES:
            out.add(_DAY_ALIASES[part])
        else:
            raise RotaError(f"unknown day {part!r}")
    if not out:
        raise RotaError("day pattern is empty")
    return sorted(out)


def days_label(days: list[int]) -> str:
    days = sorted(set(days))
    if days == ALL_DAYS:
        return "Mon-Sun"
    if days == [0, 1, 2, 3, 4]:
        return "Mon-Fri"
    if days == [5, 6]:
        return "Sat-Sun"
    return ",".join(DAYS[d] for d in days)


def _hours_of(shift) -> list[int]:
    """Hours of the DAY a shift covers (0-23), in order from its start."""
    s, e = int(shift["start"]) % 24, int(shift["end"]) % 24
    if shift["end"] == shift["start"]:
        return list(range(24))
    if e > s:
        return list(range(s, e))
    return list(range(s, 24)) + list(range(0, e))      # wraps midnight


def shift_length(shift) -> int:
    return len(_hours_of(shift))


def hours_of_week(shift) -> list[int]:
    """Hours of the WEEK (0-167, Monday 00:00 = 0) a shift covers. The part
    after midnight lands on the following day (Sunday night -> Monday)."""
    start = int(shift["start"]) % 24
    out = []
    for d in parse_days(shift.get("days")):
        for h in _hours_of(shift):
            # hours numerically before the start time are past midnight, so
            # they belong to the following day
            day = (d + 1) % 7 if h < start else d
            out.append(day * 24 + h)
    return out


def is_daily(shift) -> bool:
    return parse_days(shift.get("days")) == ALL_DAYS


def _all_resources():
    return list(dict.fromkeys(STAFF_RESOURCES + sorted(RATIO_RESOURCES) + SUPPORT_RESOURCES))


def staffing_by_hour(rota: list[dict]) -> dict[str, list[int]]:
    """Per staff area, the headcount on shift each hour (sum of its roles).

    Returns 24 values per area (hour of day) when every row repeats daily, and
    168 values (hour of week, Monday 00:00 first) as soon as any row has a day
    pattern - so a Monday-only shift is staffed on Mondays only. ZERO STAYS
    ZERO: an hour nobody is rostered for has no staff."""
    weekly = any(not is_daily(sh) for sh in rota if sh.get("role") in ROLES)
    return staffing_by_week(rota) if weekly else _staffing_daily(rota)


def _staffing_daily(rota):
    cap = {r: [0] * 24 for r in _all_resources()}
    for sh in rota:
        role = ROLES.get(sh.get("role"))
        if not role:
            continue
        res = role["staffs"]
        cap.setdefault(res, [0] * 24)
        for h in _hours_of(sh):
            cap[res][h] += int(sh.get("count", 1))
    return cap


def staffing_by_week(rota: list[dict]) -> dict[str, list[int]]:
    """168-hour (hour of week) headcount per staff area."""
    cap = {r: [0] * 168 for r in _all_resources()}
    for sh in rota:
        role = ROLES.get(sh.get("role"))
        if not role:
            continue
        res = role["staffs"]
        cap.setdefault(res, [0] * 168)
        for h in hours_of_week(sh):
            cap[res][h] += int(sh.get("count", 1))
    return cap


def to_week(series: list) -> list:
    """A 24-value daily series repeated to 168 (hour of week); 168 unchanged."""
    if len(series) == 168:
        return list(series)
    if len(series) == 24:
        return list(series) * 7
    raise ValueError(f"expected 24 or 168 values, got {len(series)}")


def day_profile(series: list) -> list[float]:
    """Average by hour of day of a 24- or 168-value series."""
    if len(series) == 24:
        return list(series)
    return [sum(series[d * 24 + h] for d in range(7)) / 7.0 for h in range(24)]


# --------------------------------------------------------------------------- #
# Validation, import and export (shared by the Midshire editor and workbooks)
# --------------------------------------------------------------------------- #
ROTA_COLUMNS = ["role", "area", "days", "start", "end", "count",
                "unpaid_break_minutes", "note"]


def _hour(value, field):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise RotaError(f"{field} is blank")
    if isinstance(value, str):
        v = value.strip()
        m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", v)
        if not m:
            raise RotaError(f"{field} {value!r} is not an hour (use 0-24 or HH:00)")
        if m.group(2) not in (None, "00"):
            raise RotaError(f"{field} {value!r}: the model works in whole hours (HH:00)")
        value = int(m.group(1))
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise RotaError(f"{field} {value!r} is not a number")
    if f != int(f):
        raise RotaError(f"{field} {value!r}: the model works in whole hours")
    h = int(f)
    if not 0 <= h <= 24:
        raise RotaError(f"{field} {h} is outside 0-24")
    return h


def clean_shift(row: dict) -> dict:
    """Validate one rota row and return its canonical form. Raises RotaError."""
    role = str(row.get("role") or "").strip()
    if not role:
        raise RotaError("role is blank")
    if role not in ROLES:
        raise RotaError(f"unknown role {role!r}")
    start = _hour(row.get("start"), "start")
    end = _hour(row.get("end"), "end")
    if start == 24:
        raise RotaError("start must be 0-23")
    if start == end:
        raise RotaError("start and end are the same hour - use 0 to 24 for a 24-hour shift")
    cnt = row.get("count")
    if cnt is None or (isinstance(cnt, str) and not cnt.strip()):
        raise RotaError("count is blank (enter 0 if nobody is rostered)")
    try:
        cf = float(cnt)
    except (TypeError, ValueError):
        raise RotaError(f"count {cnt!r} is not a number")
    if cf < 0:
        raise RotaError("count cannot be negative")
    if cf != int(cf):
        raise RotaError("count must be a whole number of staff")
    brk = row.get("unpaid_break_minutes")
    if brk is None or (isinstance(brk, str) and not brk.strip()):
        brk = 0
    try:
        brk = float(brk)
    except (TypeError, ValueError):
        raise RotaError(f"unpaid break {brk!r} is not a number")
    if brk < 0:
        raise RotaError("unpaid break cannot be negative")
    length = len(_hours_of({"start": start, "end": end}))
    if brk >= length * 60:
        raise RotaError("unpaid break is as long as the shift")
    days = parse_days(row.get("days"))
    out = {"role": role, "start": start, "end": end, "count": int(cf),
           "days": days_label(days)}
    if brk:
        out["unpaid_break_minutes"] = int(brk) if brk == int(brk) else brk
    if row.get("area"):
        out["area"] = str(row["area"]).strip()[:60]
    if row.get("note"):
        out["note"] = str(row["note"]).strip()[:200]
    return out


def validate_rota(rows) -> tuple[list[dict], list[dict]]:
    """Validate a whole rota. Returns (clean rows, errors) where each error is
    {"row": index (1-based), "error": message}. Invalid rows are NOT silently
    dropped by callers - an editor must refuse to apply a rota with errors."""
    clean, errors = [], []
    for i, row in enumerate(rows or [], 1):
        try:
            clean.append(clean_shift(row))
        except RotaError as e:
            errors.append({"row": i, "error": str(e)})
    return clean, errors


def rota_to_csv(rota: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(ROTA_COLUMNS)
    for sh in rota:
        w.writerow([sh.get("role", ""), sh.get("area", ""),
                    days_label(parse_days(sh.get("days"))),
                    f"{int(sh['start']):02d}:00", f"{int(sh['end']):02d}:00",
                    sh.get("count", ""), sh.get("unpaid_break_minutes", 0),
                    sh.get("note", "")])
    return buf.getvalue()


def rota_from_csv(text: str) -> tuple[list[dict], list[dict]]:
    """Read a rota CSV (the export format above; ``days`` and the break column
    are optional so a legacy role/start/end/count file still imports)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or "role" not in [f.strip().lower() for f in reader.fieldnames]:
        return [], [{"row": 0, "error": "the file has no 'role' column"}]
    rows = []
    for r in reader:
        r = {(k or "").strip().lower(): v for k, v in r.items()}
        if not any((v or "").strip() for v in r.values() if isinstance(v, str)):
            continue                              # skip blank lines
        if str(r.get("role", "")).strip().startswith("#"):
            continue                              # comment rows
        rows.append(r)
    return validate_rota(rows)


# --------------------------------------------------------------------------- #
# Cost (the canonical service lives in workforce/costing.py)
# --------------------------------------------------------------------------- #
def weekly_cost(rota: list[dict]) -> float:
    from .costing import rota_cost
    out = rota_cost(rota, role_rates())
    return round(out["weekly_total"] or 0.0, 0)


def cost_breakdown(rota: list[dict]) -> dict:
    from .costing import rota_cost
    out = rota_cost(rota, role_rates())
    return {"weekly_total": round(out["weekly_total"] or 0.0, 0),
            "by_role": {k: round(v) for k, v in out["by_role"].items() if v is not None}}


def understaffed_hours(staffing: list[int], demand_profile: list[float]) -> list[int]:
    """SECONDARY demand-shape heuristic, not a sufficiency test: hours where the
    demand curve's share of the day materially exceeds staffing's share of the
    day. It says nothing about whether a headcount is ENOUGH or whether a target
    will be met - only that the shape of staffing and the shape of demand
    differ. Model-required staffing comes from simulating a package."""
    staffing = day_profile(staffing)
    sd, dd = sum(staffing) or 1, sum(demand_profile) or 1
    out = []
    for h in range(24):
        if demand_profile[h] / dd - staffing[h] / sd > 0.012:   # demand-heavy, staff-light
            out.append(h)
    return out
