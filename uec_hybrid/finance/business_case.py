"""
Business-case maths: turn a simulated improvement into pounds.

Benefits are computed ONLY from what the simulation actually showed (breaches
avoided, admissions avoided) priced by the trust-editable cost book; costs come
from the option's cost band priced by the same book. The assumptions used are
returned with every case so they can be printed alongside the numbers — a case
is never shown without the figures it rests on.
"""
from __future__ import annotations

from .costbook import load_cost_book


def _band(book, cost_band):
    lo, hi = book["option_cost_bands"].get(cost_band, book["option_cost_bands"]["Moderate"])
    return lo, hi, (lo + hi) / 2


def _case(annual_benefit, cost_band, book, drivers, assumptions):
    lo, hi, mid = _band(book, cost_band)
    annual_benefit = round(annual_benefit)
    out = {
        "annual_benefit": annual_benefit,
        "annual_cost_low": lo, "annual_cost_high": hi,
        "drivers": drivers,
        "assumptions": assumptions + [book["note"]],
    }
    if annual_benefit > 0:
        out["roi"] = round(annual_benefit / mid, 2)
        out["payback_years"] = round(mid / annual_benefit, 1)
        out["summary"] = (f"~£{annual_benefit:,}/year benefit against an indicative "
                          f"£{lo:,}–£{hi:,}/year cost"
                          + (f" — pays back in about {out['payback_years']:g} years."
                             if out["payback_years"] >= 1.05 else " — pays back within the year."))
    else:
        out["roi"] = None
        out["payback_years"] = None
        out["summary"] = "No measurable financial benefit at this demand."
    return out


def business_case(option: dict, baseline: dict, attendances_per_day: float,
                  book: dict | None = None) -> dict:
    """Finance for a winter-plan option: what the simulated deltas are worth.

    ``option`` is a make_plan option row (delta, corridor_per_day, cost band);
    ``baseline`` is the plan's do-nothing outcome.
    """
    book = book or load_cost_book()
    four_pts = max(0.0, float(option.get("delta", 0)))
    four_avoided_day = attendances_per_day * four_pts / 100.0
    twelve_avoided_day = max(0.0, float(baseline.get("corridor_per_day", 0))
                             - float(option.get("corridor_per_day", 0)))
    annual = (four_avoided_day * book["four_hour_breach"]
              + twelve_avoided_day * book["twelve_hour_breach"]) * 365
    drivers = []
    if four_avoided_day > 0.05:
        drivers.append(f"~{four_avoided_day:.0f} fewer 4-hour breaches a day "
                       f"(£{book['four_hour_breach']}/breach)")
    if twelve_avoided_day > 0.05:
        drivers.append(f"~{twelve_avoided_day:.1f} fewer 12-hour waits a day "
                       f"(£{book['twelve_hour_breach']}/breach)")
    assumptions = [f"{attendances_per_day:.0f} attendances/day; benefits annualised ×365",
                   f"'{option.get('cost', 'Moderate')}' cost band priced from the cost book"]
    return _case(annual, option.get("cost", "Moderate"), book, drivers, assumptions)


def gap_finance(item: dict, attendances_per_day: float, book: dict | None = None) -> dict:
    """Finance for a missing Model ED element from the gap analysis.

    Front-door areas are valued on the 4-hour breaches they avoid; same-day /
    assessment areas on the admissions they avoid — the same measure the gap
    analysis itself uses.
    """
    book = book or load_cost_book()
    drivers, annual = [], 0.0
    if item.get("unit") == "fewer admits/day":
        avoided = max(0.0, float(item.get("value", 0)))
        annual = avoided * book["admission_avoided"] * 365
        if avoided > 0.05:
            drivers.append(f"~{avoided:.1f} admissions avoided a day "
                           f"(£{book['admission_avoided']:,}/admission)")
    else:
        pts = max(0.0, float(item.get("value", 0)))
        four_avoided_day = attendances_per_day * pts / 100.0
        annual = four_avoided_day * book["four_hour_breach"] * 365
        if four_avoided_day > 0.05:
            drivers.append(f"~{four_avoided_day:.0f} fewer 4-hour breaches a day "
                           f"(£{book['four_hour_breach']}/breach)")
    assumptions = [f"{attendances_per_day:.0f} attendances/day; benefits annualised ×365",
                   f"'{item.get('cost', 'Moderate')}' cost band priced from the cost book"]
    return _case(annual, item.get("cost", "Moderate"), book, drivers, assumptions)
