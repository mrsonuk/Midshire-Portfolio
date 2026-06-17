"""
Demand forecast for UEC / ED planning — in planners' terms, not modelling terms.

A planner describes their department today (attendances a day, current 4-hour
performance, size) and the expected winter pressure (a percent uplift and any
year-on-year growth). This produces the expected attendances for the planning
period and a plain description of when the department is busiest. No history file
is required to start; if one is later supplied via the data tab it simply replaces
these assumptions.
"""
from __future__ import annotations

# A typical ED day-of-week shape (Mon highest, weekend lower) and hour-of-day shape.
DOW = {"Monday": 1.10, "Tuesday": 1.03, "Wednesday": 1.00, "Thursday": 1.00,
       "Friday": 1.02, "Saturday": 0.95, "Sunday": 0.90}
HOURLY = [6, 4, 4, 3, 3, 4, 4, 6, 13, 20, 23, 25, 25, 22, 21, 21, 21, 21, 20, 17, 16, 14, 10, 8]


def forecast(attendances_per_day: float, winter_uplift_pct: float = 12.0,
             yoy_growth_pct: float = 0.0) -> dict:
    """Return the expected demand for the planning period, described plainly."""
    grown = attendances_per_day * (1 + yoy_growth_pct / 100.0)
    winter = grown * (1 + winter_uplift_pct / 100.0)
    busiest_day = max(DOW, key=DOW.get)
    peak_hour = HOURLY.index(max(HOURLY))
    busiest_day_attendances = winter * DOW[busiest_day] / (sum(DOW.values()) / len(DOW))
    # scale the standard hourly shape to the forecast daily total
    scale = winter / sum(HOURLY)
    profile = [round(h * scale, 2) for h in HOURLY]
    return {
        "now_per_day": round(attendances_per_day),
        "expected_per_day": round(winter),
        "busiest_day": busiest_day,
        "busiest_day_per_day": round(busiest_day_attendances),
        "peak_hour": peak_hour,
        "winter_uplift_pct": winter_uplift_pct,
        "hourly_profile": profile,
        "summary": (f"About {round(winter)} attendances a day this winter, "
                    f"up from {round(attendances_per_day)} now "
                    f"(a {winter_uplift_pct:.0f}% winter rise). "
                    f"Busiest on {busiest_day}s and around {peak_hour}:00–"
                    f"{(peak_hour+3) % 24}:00."),
    }
