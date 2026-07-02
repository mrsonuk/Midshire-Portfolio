"""
Demand forecast for UEC / ED planning - in planners' terms, not modelling terms.

A planner describes their department today (attendances a day, current 4-hour
performance, size) and the expected winter pressure (a percent uplift and any
year-on-year growth). This produces the expected attendances for the planning
period and a plain description of when the department is busiest. No history file
is required to start; if one is later supplied via the data tab it simply replaces
these assumptions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

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
                    f"Busiest on {busiest_day}s and around {peak_hour}:00-"
                    f"{(peak_hour+3) % 24}:00."),
    }


# --------------------------------------------------------------------------- #
# Forecast from the planner's own attendance history (replaces the % guess)
# --------------------------------------------------------------------------- #
def forecast_from_history(df: pd.DataFrame) -> dict:
    """Derive the winter forecast from a daily attendance history.

    Expects a 'date' column and an 'attendances' column (or one row per
    attendance with a 'date'). Produces the same forecast a planner would get
    from the sliders, but read from their own data, with a plain note explaining
    what the data showed (recent level, growth, how much higher winter runs).
    """
    df = df.copy()
    if "date" not in df:
        raise ValueError("history needs a 'date' column")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if "attendances" in df:
        daily = df.groupby("date")["attendances"].sum().sort_index()
    else:
        daily = df.groupby("date").size().sort_index()
    if len(daily) < 28:
        raise ValueError("need at least ~4 weeks of daily history")

    recent_level = float(daily.tail(56).mean())                # last 8 weeks
    annual_mean = float(daily.mean())
    by_month = daily.groupby(daily.index.month).mean()
    winter_factor = float(by_month.reindex([12, 1, 2]).dropna().mean() / annual_mean) \
        if not by_month.reindex([12, 1, 2]).dropna().empty else 1.12
    recent_month = int(daily.index[-1].month)
    recent_factor = float(by_month.get(recent_month, annual_mean) / annual_mean)

    # year-on-year growth (last 90 days vs the same period a year earlier, else slope)
    yoy = 0.0
    if (daily.index[-1] - daily.index[0]).days > 400:
        last = daily.tail(90).mean()
        prev = daily[(daily.index >= daily.index[-1] - pd.Timedelta(days=455)) &
                     (daily.index <= daily.index[-1] - pd.Timedelta(days=365))].mean()
        if prev and not np.isnan(prev):
            yoy = (last / prev - 1) * 100
    else:
        slope = np.polyfit(np.arange(len(daily)), daily.values, 1)[0]
        yoy = slope * 365 / max(1.0, annual_mean) * 100

    # project the recent level forward, adjusting from its season to winter
    expected = recent_level * (1 + yoy / 100.0) * (winter_factor / max(0.5, recent_factor))
    winter_uplift_pct = (expected / recent_level - 1) * 100

    # hour-of-day shape from data if present, else the standard shape
    profile = HOURLY
    if "arrival_hour" in df:
        h = (df["arrival_hour"].astype(int) % 24).value_counts().reindex(range(24), fill_value=0).sort_index()
        if h.sum() > 0:
            profile = list(h.values)
    scale = expected / sum(profile)
    hourly = [round(x * scale, 2) for x in profile]

    busiest_day = max(DOW, key=DOW.get)
    peak_hour = int(np.argmax(profile))
    note = (f"Based on your data: about {round(recent_level)} attendances a day "
            f"recently, growing roughly {yoy:+.0f}% a year, and running about "
            f"{(winter_factor-1)*100:+.0f}% versus the yearly average in winter. "
            f"Forecast for this winter: about {round(expected)} a day.")
    return {
        "now_per_day": round(recent_level),
        "expected_per_day": round(expected),
        "busiest_day": busiest_day,
        "busiest_day_per_day": round(expected * DOW[busiest_day] / (sum(DOW.values()) / len(DOW))),
        "peak_hour": peak_hour,
        "winter_uplift_pct": round(winter_uplift_pct, 1),
        "yoy_growth_pct": round(yoy, 1),
        "hourly_profile": hourly,
        "summary": note,
        "from_data": True,
    }


def generate_daily_history(years: float = 2.0, base: float = 320.0, seed: int = 0) -> pd.DataFrame:
    """A realistic synthetic daily attendance history (the placeholder a real
    extract replaces): trend, winter seasonality, weekly pattern and noise."""
    rng = np.random.default_rng(seed)
    n = int(years * 365)
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    dow = {0: 1.10, 1: 1.03, 2: 1.00, 3: 1.00, 4: 1.02, 5: 0.95, 6: 0.90}
    rows = []
    for i, d in enumerate(dates):
        trend = 1 + 0.03 * (i / 365)                       # +3% / year
        # seasonal: winter peak, summer trough (cosine on day-of-year)
        seasonal = 1 + 0.12 * np.cos(2 * np.pi * (d.dayofyear - 15) / 365)
        val = base * trend * seasonal * dow[d.dayofweek] * rng.normal(1.0, 0.07)
        rows.append({"date": d.date().isoformat(), "attendances": max(1, int(round(val)))})
    return pd.DataFrame(rows)
