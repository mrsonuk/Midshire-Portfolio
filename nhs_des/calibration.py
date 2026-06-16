"""
Data-driven calibration.

Today the model runs on synthetic parameters seeded from the beta ``config.json``.
This module is the seam where **real hospital data replaces the synthetic
placeholder**: drop in an ECDS-style attendance extract and the tool re-derives
the parameters it can robustly identify from data, leaving the rest at their
modelled defaults.

Expected columns (one row per A&E attendance) - all optional; whatever is present
is used:

    arrival_hour        int 0-23   (or arrival_datetime, from which hour is taken)
    acuity              1-5        (ECDS acuity / triage category)
    arrival_mode        'ambulance' | 'walk-in'   (or ambulance 0/1)
    age                 years      (age < 16 counts as paediatric)
    mental_health       0/1        (mental-health presentation)
    disposition         'admitted' | 'discharged' | ...
    total_time_minutes  number     (time in department; used for validation only)

From this it calibrates the parameters that are *identifiable* from attendance
data - arrival profile, acuity mix, ambulance/paediatric/mental-health prevalence
and admission rate by acuity. Per-stage service times are NOT inferred (they are
not identifiable from between-event data) and stay at their modelled values; this
is called out in the calibration summary so it is never silently assumed.
"""
from __future__ import annotations

import copy
import io

import numpy as np
import pandas as pd

ACUITIES = ["Acuity 1", "Acuity 2", "Acuity 3", "Acuity 4", "Acuity 5"]


def read_table(file_or_buffer) -> pd.DataFrame:
    """Read a CSV from a path, file object or bytes."""
    if isinstance(file_or_buffer, bytes):
        file_or_buffer = io.BytesIO(file_or_buffer)
    return pd.read_csv(file_or_buffer)


def _hour_series(df: pd.DataFrame) -> pd.Series | None:
    if "arrival_hour" in df:
        return df["arrival_hour"].astype(int) % 24
    if "arrival_datetime" in df:
        return pd.to_datetime(df["arrival_datetime"], errors="coerce").dt.hour
    return None


def calibrate(df: pd.DataFrame, base_raw: dict) -> tuple[dict, list]:
    """Return (calibrated pathway dict, human-readable change summary)."""
    raw = copy.deepcopy(base_raw)
    arrivals = raw.setdefault("arrivals", {})
    summary = []
    n = len(df)
    summary.append(f"Loaded {n:,} attendance records.")

    # ---- arrival profile (mean attendances per hour-of-day) ----
    hours = _hour_series(df)
    if hours is not None and hours.notna().any():
        n_days = max(1, int(np.ceil(hours.notna().sum() /
                     max(1, hours.value_counts().sum()) * 0)) or
                     _estimate_days(df))
        counts = hours.value_counts().reindex(range(24), fill_value=0).sort_index()
        profile = (counts / max(1, _estimate_days(df))).round(2).tolist()
        arrivals["hourly_profile"] = profile
        summary.append(f"Arrival profile updated from data "
                       f"(peak {int(max(profile))}/h around {int(np.argmax(profile))}:00).")

    # ---- acuity mix (only for acuity-based pathways; ECDS acuity 1-5 must not
    # overwrite a pathway whose classes are referral types, e.g. the AMU) ----
    base_classes = set(arrivals.get("acuity_mix", {}))
    acuity_based = bool(base_classes & {f"Acuity {i}" for i in range(1, 6)})
    if "acuity" in df and acuity_based:
        ac = pd.to_numeric(df["acuity"], errors="coerce").dropna().astype(int)
        mix = {}
        for i in range(1, 6):
            mix[f"Acuity {i}"] = round(float((ac == i).mean() * 100), 2)
        if sum(mix.values()) > 0:
            arrivals["acuity_mix"] = mix
            summary.append("Acuity mix updated: " +
                           ", ".join(f"A{i} {mix[f'Acuity {i}']:.0f}%" for i in range(1, 6)) + ".")
    elif "acuity" in df and not acuity_based:
        summary.append("Acuity mix not changed — this pathway uses non-acuity patient "
                       "classes (e.g. referral source); acuity data was ignored.")

    # ---- attribute prevalences ----
    attrs = arrivals.get("attributes", {})
    if "arrival_mode" in df:
        amb = df["arrival_mode"].astype(str).str.lower().str.contains("amb").mean()
        attrs["ambulance"] = round(float(amb), 4)
        summary.append(f"Ambulance arrivals: {amb*100:.0f}%.")
    elif "ambulance" in df:
        attrs["ambulance"] = round(float(pd.to_numeric(df["ambulance"], errors="coerce").mean()), 4)
    if "age" in df:
        paed = (pd.to_numeric(df["age"], errors="coerce") < 16).mean()
        attrs["paediatric"] = round(float(paed), 4)
        summary.append(f"Paediatric (age<16): {paed*100:.0f}%.")
    if "mental_health" in df:
        mh = pd.to_numeric(df["mental_health"], errors="coerce").fillna(0).mean()
        attrs["mental_health"] = round(float(mh), 4)
        summary.append(f"Mental-health presentations: {mh*100:.1f}%.")
    if attrs:
        arrivals["attributes"] = attrs

    # ---- admission rate by acuity -> patch the clinical-decision node ----
    if "acuity" in df and "disposition" in df:
        ac = pd.to_numeric(df["acuity"], errors="coerce")
        admit = df["disposition"].astype(str).str.lower().str.contains("admit")
        node = next((nd for nd in raw["nodes"] if nd.get("id") == "outcome"), None)
        if node and "routes_by_class" in node:
            changed = []
            for i in range(1, 6):
                sel = ac == i
                if sel.sum() >= 20:
                    rate = float(admit[sel].mean())
                    cls = f"Acuity {i}"
                    if cls in node["routes_by_class"]:
                        node["routes_by_class"][cls] = [
                            ["await_bed", round(rate, 3)],
                            ["discharge", round(1 - rate, 3)]]
                        changed.append(f"A{i} {rate*100:.0f}%")
            if changed:
                summary.append("Admission rate by acuity updated: " + ", ".join(changed) + ".")

    summary.append("Per-stage service times were NOT changed — they are not "
                   "identifiable from attendance data and remain at modelled values. "
                   "Provide stage-level timestamps to calibrate these.")
    return raw, summary


def _estimate_days(df: pd.DataFrame) -> int:
    if "arrival_datetime" in df:
        dt = pd.to_datetime(df["arrival_datetime"], errors="coerce").dropna()
        if len(dt):
            return max(1, (dt.max() - dt.min()).days + 1)
    if "day" in df:
        return max(1, int(df["day"].nunique()))
    return max(1, round(len(df) / 300))  # assume ~300 attendances/day if unknown


# --------------------------------------------------------------------------- #
# Synthetic sample dataset (the placeholder a real ECDS extract replaces)
# --------------------------------------------------------------------------- #
def generate_sample(days: int = 14, seed: int = 0) -> pd.DataFrame:
    """A realistic synthetic ECDS-style extract, so the upload path is
    demonstrable before real data arrives and the schema is self-documenting."""
    rng = np.random.default_rng(seed)
    profile = np.array([6, 4, 4, 3, 3, 4, 4, 6, 13, 20, 23, 25, 25, 22, 21, 21,
                        21, 21, 20, 17, 16, 14, 10, 8], dtype=float)
    acuity_p = np.array([0.0088, 0.055, 0.2465, 0.6068, 0.0829])
    admit_p = {1: 0.585, 2: 0.489, 3: 0.264, 4: 0.103, 5: 0.036}
    rows = []
    for day in range(days):
        for hour in range(24):
            for _ in range(rng.poisson(profile[hour])):
                acuity = int(rng.choice([1, 2, 3, 4, 5], p=acuity_p))
                ambulance = rng.random() < (0.6 if acuity <= 2 else 0.25)
                age = int(rng.integers(0, 16)) if rng.random() < 0.22 else int(rng.integers(16, 95))
                mh = rng.random() < 0.019
                admitted = rng.random() < admit_p[acuity]
                rows.append({
                    "day": day,
                    "arrival_hour": hour,
                    "acuity": acuity,
                    "arrival_mode": "ambulance" if ambulance else "walk-in",
                    "age": age,
                    "mental_health": int(mh),
                    "disposition": "admitted" if admitted else "discharged",
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    out = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "data" / "sample_ecds.csv")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    generate_sample().to_csv(out, index=False)
    print("Wrote sample extract:", out)
