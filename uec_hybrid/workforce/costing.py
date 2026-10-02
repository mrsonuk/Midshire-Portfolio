"""
The ONE workforce cost service. Every pound shown for staff - the rota editor's
preview, the baseline pay-bill, the recommendation and target searches, the
assistant and the exports - is computed here, from the same rate table, so two
screens can never price the same rota differently.

(Before this existed the Cambridge pay-bill used the editable ``role_rates()``
while the recommender's ``_shift_cost_per_week`` read the hard-coded default
``ROLES[role]["cost"]``, so a trust's own rates changed one figure and not the
other.)

A rate table is either

* a plain ``{role: hourly_rate}`` map - each rate is a FULLY LOADED hourly
  cost (the Cambridge build's ``role_rates()``); or
* a structured cost table ``{"roles": {role: entry}}`` where an entry may give

  ``fully_loaded_hourly_rate``  - used as given. It must already include
                                  on-costs, enhancements and any bank/agency
                                  mix, so nothing below is added on top (this
                                  is what stops double counting); or
  ``base_hourly_rate``          - basic pay per hour, then
  ``employer_on_cost_pct``      - employer NI, pension etc. as % of pay
  ``enhancement_pct``           - average unsocial-hours uplift as % of pay
  ``agency_share_pct`` +
  ``agency_hourly_rate``        - share of hours filled by bank/agency and its
                                  all-in hourly cost

  effective = (1 - agency share) x base x (1 + on-cost) x (1 + enhancement)
              + agency share x agency rate

MISSING IS NOT ZERO. A role with no rate is "not costed": its hours are
counted, its cost is None, and every total says it is incomplete. An explicit
0 is a real answer (e.g. a post funded elsewhere) and is costed at £0.
"""
from __future__ import annotations

from .rota import _hours_of, parse_days

WEEKS_PER_YEAR = 52.0


def _num(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def effective_rate(entry) -> dict:
    """{rate: float|None, status: costed|not costed, basis: str} for one role."""
    if isinstance(entry, (int, float)) and not isinstance(entry, bool):
        return {"rate": float(entry), "status": "costed",
                "basis": "fully loaded hourly rate"}
    if not isinstance(entry, dict):
        return {"rate": None, "status": "not costed", "basis": "no rate entered"}
    fl = _num(entry.get("fully_loaded_hourly_rate"))
    if fl is not None:
        if fl < 0:
            return {"rate": None, "status": "not costed", "basis": "negative rate rejected"}
        return {"rate": fl, "status": "costed",
                "basis": "fully loaded hourly rate (includes on-costs, enhancements "
                         "and bank/agency mix - nothing added on top)"}
    base = _num(entry.get("base_hourly_rate"))
    if base is None:
        return {"rate": None, "status": "not costed", "basis": "no rate entered"}
    if base < 0:
        return {"rate": None, "status": "not costed", "basis": "negative rate rejected"}
    on = _num(entry.get("employer_on_cost_pct")) or 0.0
    enh = _num(entry.get("enhancement_pct")) or 0.0
    share = (_num(entry.get("agency_share_pct")) or 0.0) / 100.0
    substantive = base * (1 + on / 100.0) * (1 + enh / 100.0)
    if share > 0:
        ag = _num(entry.get("agency_hourly_rate"))
        if ag is None:
            return {"rate": None, "status": "not costed",
                    "basis": f"{share*100:.0f}% bank/agency share but no agency rate"}
        rate = (1 - share) * substantive + share * ag
        basis = (f"£{base:.2f} basic x (1+{on:g}% on-cost) x (1+{enh:g}% enhancement), "
                 f"blended with {share*100:g}% bank/agency at £{ag:.2f}")
    else:
        rate = substantive
        basis = f"£{base:.2f} basic x (1+{on:g}% on-cost) x (1+{enh:g}% enhancement)"
    return {"rate": round(rate, 4), "status": "costed", "basis": basis}


def rate_table(rates) -> dict:
    """Normalise either table form to {role: effective_rate(...)}."""
    if isinstance(rates, dict) and isinstance(rates.get("roles"), dict):
        return {r: effective_rate(e) for r, e in rates["roles"].items()}
    return {r: effective_rate(v) for r, v in (rates or {}).items()}


def shift_hours(shift) -> dict:
    """Rostered and paid hours a rota row represents per WEEK."""
    length = len(_hours_of(shift))
    ndays = len(parse_days(shift.get("days")))
    count = int(shift.get("count", 1))
    brk = (_num(shift.get("unpaid_break_minutes")) or 0.0) / 60.0
    return {"rostered_hours_week": count * length * ndays,
            "paid_hours_week": round(count * max(0.0, length - brk) * ndays, 4),
            "shifts_week": count * ndays, "shift_length": length}


def shift_cost(shift, rates) -> dict:
    """Weekly hours and cost of one rota row (cost None when not costed)."""
    table = rates if _is_normalised(rates) else rate_table(rates)
    h = shift_hours(shift)
    r = table.get(shift.get("role"), {"rate": None, "status": "not costed",
                                      "basis": "no rate entered"})
    cost = None if r["rate"] is None else round(h["paid_hours_week"] * r["rate"], 2)
    return {**h, "rate": r["rate"], "rate_status": r["status"], "weekly_cost": cost}


def _is_normalised(t) -> bool:
    return isinstance(t, dict) and t and all(
        isinstance(v, dict) and "status" in v and "rate" in v for v in t.values())


def rota_cost(rota, rates) -> dict:
    """Cost a whole rota. ``weekly_total`` sums the COSTED rows only;
    ``complete`` is False and ``uncosted_roles`` lists the rest whenever any row
    has no rate - a missing rate is never priced at £0."""
    table = rate_table(rates)
    by_role, hours_by_role, rows = {}, {}, []
    uncosted = set()
    total = 0.0
    for sh in rota or []:
        c = shift_cost(sh, table)
        rows.append(c)
        role = sh.get("role")
        hours_by_role[role] = hours_by_role.get(role, 0.0) + c["paid_hours_week"]
        if c["weekly_cost"] is None:
            uncosted.add(role)
            by_role.setdefault(role, None)
        else:
            total += c["weekly_cost"]
            by_role[role] = (by_role.get(role) or 0.0) + c["weekly_cost"]
    return {"weekly_total": round(total, 2), "annual_total": round(total * WEEKS_PER_YEAR, 2),
            "complete": not uncosted, "uncosted_roles": sorted(r for r in uncosted if r),
            "by_role": by_role, "paid_hours_by_role": hours_by_role, "rows": rows,
            "weeks_per_year": WEEKS_PER_YEAR}


def shift_weekly_cost(role, start, end, count=1, rates=None, days=None) -> float | None:
    """Weekly cost of one added shift at the given rates (None if not costed)."""
    if rates is None:
        from .roles import role_rates
        rates = role_rates()
    return shift_cost({"role": role, "start": start, "end": end, "count": count,
                       "days": days}, rates)["weekly_cost"]
