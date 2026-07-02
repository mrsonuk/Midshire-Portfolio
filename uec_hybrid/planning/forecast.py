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
# England & Wales bank holidays (shipped list; extend for later years).
BANK_HOLIDAYS = {
    "2022-01-03", "2022-04-15", "2022-04-18", "2022-05-02", "2022-06-02", "2022-06-03",
    "2022-08-29", "2022-09-19", "2022-12-26", "2022-12-27",
    "2023-01-02", "2023-04-07", "2023-04-10", "2023-05-01", "2023-05-08", "2023-05-29",
    "2023-08-28", "2023-12-25", "2023-12-26",
    "2024-01-01", "2024-03-29", "2024-04-01", "2024-05-06", "2024-05-27",
    "2024-08-26", "2024-12-25", "2024-12-26",
    "2025-01-01", "2025-04-18", "2025-04-21", "2025-05-05", "2025-05-26",
    "2025-08-25", "2025-12-25", "2025-12-26",
    "2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25",
    "2026-08-31", "2026-12-25", "2026-12-28",
    "2027-01-01", "2027-03-26", "2027-03-29", "2027-05-03", "2027-05-31",
    "2027-08-30", "2027-12-27", "2027-12-28",
}


def _design(dates: pd.DatetimeIndex, t0) -> np.ndarray:
    """Regression features: trend, weekday, annual seasonality (two harmonics),
    bank holiday and the day after (both run hot in EDs)."""
    t = (dates - t0).days.to_numpy() / 365.0
    doy = dates.dayofyear.to_numpy()
    dow = dates.dayofweek.to_numpy()
    bh = np.array([d.strftime("%Y-%m-%d") in BANK_HOLIDAYS for d in dates], float)
    after = np.array([(d - pd.Timedelta(days=1)).strftime("%Y-%m-%d") in BANK_HOLIDAYS
                      for d in dates], float)
    cols = [np.ones(len(dates)), t,
            np.sin(2 * np.pi * doy / 365), np.cos(2 * np.pi * doy / 365),
            np.sin(4 * np.pi * doy / 365), np.cos(4 * np.pi * doy / 365),
            bh, after]
    cols += [(dow == d).astype(float) for d in range(1, 7)]   # Monday is baseline
    return np.column_stack(cols)


def forecast_from_history(df: pd.DataFrame) -> dict:
    """Winter forecast from a daily attendance history via a small regression:
    trend + weekday + annual seasonality + bank-holiday effects, backtested on
    a 28-day holdout so the accuracy is shown, never implied.

    Expects a 'date' column and an 'attendances' column (or one row per
    attendance with a 'date'). Returns the same keys the sliders produce, plus
    'accuracy' and 'components'.
    """
    df = df.copy()
    if "date" not in df:
        raise ValueError("history needs a 'date' column")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    daily = (df.groupby("date")["attendances"].sum() if "attendances" in df
             else df.groupby("date").size()).sort_index()
    if len(daily) < 28:
        raise ValueError("need at least ~4 weeks of daily history")

    dates, y = daily.index, daily.to_numpy(dtype=float)
    t0 = dates[0]

    def fit(idx):
        X = _design(dates[idx], t0)
        beta, *_ = np.linalg.lstsq(X, y[idx], rcond=None)
        return beta

    # backtest: hold out the most recent 28 days when there is enough history
    accuracy = None
    if len(daily) >= 120:
        train = np.arange(len(daily) - 28)
        beta_bt = fit(train)
        pred = _design(dates[-28:], t0) @ beta_bt
        mape = float(np.mean(np.abs(pred - y[-28:]) / np.maximum(1.0, y[-28:])) * 100)
        accuracy = {"mape_pct": round(mape, 1), "holdout_days": 28}

    beta = fit(np.arange(len(daily)))

    def predict(ds):
        return _design(pd.DatetimeIndex(ds), t0) @ beta

    # recent level: the model's view of a typical day right now
    recent_level = float(np.mean(predict(pd.date_range(dates[-1] - pd.Timedelta(days=27),
                                                       dates[-1]))))
    # winter: a typical day across the NEXT Dec-Feb window
    winter_start = pd.Timestamp(year=dates[-1].year if dates[-1].month < 12 else dates[-1].year + 1,
                                month=12, day=1)
    winter_days = pd.date_range(winter_start, winter_start + pd.Timedelta(days=89))
    expected = float(np.mean(predict(winter_days)))
    winter_uplift_pct = (expected / max(1.0, recent_level) - 1) * 100

    annual_mean = float(np.mean(y))
    yoy = float(beta[1] / max(1.0, annual_mean) * 100)          # trend %/year
    bh_pct = float(beta[6] / max(1.0, annual_mean) * 100)       # bank-holiday lift

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
    note = (f"Based on your data: about {round(recent_level)} attendances a day now, "
            f"trend {yoy:+.0f}% a year, bank holidays running about {bh_pct:+.0f}%. "
            f"Forecast for this winter: about {round(expected)} a day.")
    if accuracy:
        note += (f" Backtested on your last {accuracy['holdout_days']} days: typically "
                 f"within {accuracy['mape_pct']:.0f}% of the actual daily figure.")
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
        "accuracy": accuracy,
        "components": {"trend_pct_per_year": round(yoy, 1),
                       "bank_holiday_pct": round(bh_pct, 1),
                       "winter_vs_now_pct": round(winter_uplift_pct, 1)},
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
        bh = 1.15 if d.strftime("%Y-%m-%d") in BANK_HOLIDAYS else 1.0
        val = base * trend * seasonal * dow[d.dayofweek] * bh * rng.normal(1.0, 0.07)
        rows.append({"date": d.date().isoformat(), "attendances": max(1, int(round(val)))})
    return pd.DataFrame(rows)
