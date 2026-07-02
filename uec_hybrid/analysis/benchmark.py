"""
Benchmarking: where does this department sit against its peers?

Works from an uploaded benchmark table (one row per organisation: attendances,
4-hour and 12-hour performance) - the published NHSE monthly A&E statistics
reshape to this in a spreadsheet in minutes. Until real data is uploaded a
clearly-flagged SYNTHETIC peer set shaped like recent national distributions
is used, so the surface works on day one and never presents invented numbers
as real benchmarks.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

COLUMNS = ["organisation", "attendances_per_day", "four_hour_pct", "twelve_hour_pct"]


def generate_sample_benchmarks(n: int = 120, seed: int = 3) -> pd.DataFrame:
    """A synthetic peer set with realistic spread (median 4-hour in the low 70s,
    long tail of pressured trusts). Placeholder only - clearly flagged."""
    rng = np.random.default_rng(seed)
    attend = rng.lognormal(mean=np.log(280), sigma=0.45, size=n).clip(80, 1200)
    four = (86 - 22 * rng.beta(2.2, 3.2, size=n)).clip(48, 95)
    twelve = (np.maximum(0, (78 - four)) * rng.uniform(0.08, 0.25, size=n)).round(1)
    return pd.DataFrame({
        "organisation": [f"Synthetic peer {i + 1:03d}" for i in range(n)],
        "attendances_per_day": attend.round(0).astype(int),
        "four_hour_pct": four.round(1),
        "twelve_hour_pct": twelve,
    })


def read_benchmarks(file_or_bytes) -> list[dict]:
    if isinstance(file_or_bytes, bytes):
        file_or_bytes = io.BytesIO(file_or_bytes)
    df = pd.read_csv(file_or_bytes)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"benchmark file needs columns {COLUMNS} (missing {missing})")
    return df[COLUMNS].dropna().to_dict("records")


def position(benchmarks: list[dict], four_hour: float, twelve_hour: float,
             attendances_per_day: float, synthetic: bool) -> dict:
    """Percentile position vs all peers and vs the similar-size band."""
    df = pd.DataFrame(benchmarks)
    if df.empty:
        return {}
    band = df[(df["attendances_per_day"] >= attendances_per_day * 0.7)
              & (df["attendances_per_day"] <= attendances_per_day * 1.3)]
    if len(band) < 8:
        band = df

    def pct_rank(series, value, higher_better=True):
        r = float((series < value).mean() * 100) if higher_better \
            else float((series > value).mean() * 100)
        return round(r)

    p4 = pct_rank(band["four_hour_pct"], four_hour)
    p12 = pct_rank(band["twelve_hour_pct"], twelve_hour, higher_better=False)
    quartile = 1 + min(3, int((100 - p4) // 25))
    return {
        "n_peers": int(len(df)), "n_band": int(len(band)),
        "synthetic": bool(synthetic),
        "four_hour_percentile": p4,
        "twelve_hour_percentile": p12,
        "band_median_four_hour": round(float(band["four_hour_pct"].median()), 1),
        "band_best_quartile_four_hour": round(float(band["four_hour_pct"].quantile(0.75)), 1),
        "quartile": quartile,
        "summary": (f"Your 4-hour position ({four_hour:.0f}%) sits at the {p4}th percentile "
                    f"of {len(band)} similar-sized peers (median "
                    f"{band['four_hour_pct'].median():.0f}%, best quartile from "
                    f"{band['four_hour_pct'].quantile(0.75):.0f}%). On 12-hour waits you are "
                    f"better than {p12}% of them."
                    + (" Peer set is SYNTHETIC until you upload real benchmark data."
                       if synthetic else "")),
    }
