"""
The ECDS calibration seam - the clean point where synthetic placeholders are
replaced by real Emergency Care Data Set attendance extracts.

Identifiable-from-attendance-data parameters (arrival profile, acuity mix,
ambulance/paediatric/frailty/MH prevalence, admission rate) are re-derived from the
upload; per-stage service times are NOT identifiable from between-event timestamps
and are left at modelled values - stated explicitly, never silently assumed.
"""
from __future__ import annotations

import copy
import io

import numpy as np
import pandas as pd


def read_table(file_or_bytes) -> pd.DataFrame:
    if isinstance(file_or_bytes, bytes):
        file_or_bytes = io.BytesIO(file_or_bytes)
    return pd.read_csv(file_or_bytes)


def _estimate_days(df):
    if "day" in df:
        return max(1, int(df["day"].nunique()))
    return max(1, round(len(df) / 300))


def derive_patch(df: pd.DataFrame) -> tuple[dict, list]:
    """Derive the attendance-identifiable parameters from an ECDS extract.

    Returns a JSON-able patch (independent of any particular pathway) plus a
    plain-language summary. Because the patch is stored separately and applied
    to a *freshly built* pathway each run, a calibration keeps following the
    department through later set-up changes (areas toggled, rota edited).
    """
    patch: dict = {"arrivals": {}, "attributes": {}, "admission_rates": {}}
    summary = [f"Loaded {len(df):,} attendance records."]

    if "arrival_hour" in df:
        days = _estimate_days(df)
        counts = (df["arrival_hour"].astype(int) % 24).value_counts().reindex(range(24), fill_value=0).sort_index()
        patch["arrivals"]["hourly_profile"] = [round(c / days, 2) for c in counts]
        summary.append(f"Arrival profile re-derived (peak {int(max(patch['arrivals']['hourly_profile']))}/h).")

    if "acuity" in df:
        ac = pd.to_numeric(df["acuity"], errors="coerce").dropna().astype(int)
        mix = {f"Acuity {i}": round(float((ac == i).mean() * 100), 2) for i in range(1, 6)}
        if sum(mix.values()) > 0:
            patch["arrivals"]["acuity_mix"] = mix
            summary.append("Acuity mix updated from data.")

    attrs = patch["attributes"]
    if "arrival_mode" in df:
        attrs["ambulance"] = round(float(df["arrival_mode"].astype(str).str.lower().str.contains("amb").mean()), 4)
        summary.append(f"Ambulance arrivals {attrs['ambulance']*100:.0f}%.")
    if "age" in df:
        attrs["paediatric"] = round(float((pd.to_numeric(df["age"], errors="coerce") < 16).mean()), 4)
    if "mental_health" in df:
        attrs["mental_health"] = round(float(pd.to_numeric(df["mental_health"], errors="coerce").fillna(0).mean()), 4)

    if "acuity" in df and "disposition" in df:
        ac = pd.to_numeric(df["acuity"], errors="coerce")
        adm = df["disposition"].astype(str).str.lower().str.contains("admit")
        changed = []
        for i in range(1, 6):
            sel = ac == i
            if sel.sum() >= 20:
                rate = float(adm[sel].mean())
                patch["admission_rates"][f"Acuity {i}"] = round(rate, 3)
                changed.append(f"A{i} {rate*100:.0f}%")
        if changed:
            summary.append("Admission rate by acuity updated: " + ", ".join(changed) + ".")

    summary.append("Per-stage service times unchanged - not identifiable from attendance "
                   "data; provide stage-level timestamps to calibrate these.")
    return patch, summary


def apply_patch(raw: dict, patch: dict) -> dict:
    """Apply a derived calibration patch to any pathway raw (deep-copied)."""
    raw = copy.deepcopy(raw)
    arrivals = raw.setdefault("arrivals", {})
    for k, v in (patch.get("arrivals") or {}).items():
        arrivals[k] = copy.deepcopy(v)
    attrs = arrivals.setdefault("attributes", {})
    for k, v in (patch.get("attributes") or {}).items():
        attrs[k] = v
    rates = patch.get("admission_rates") or {}
    if rates:
        node = next((n for n in raw.get("nodes", []) if n.get("id") == "disposition_general"), None)
        if node and "routes_by_class" in node:
            for cls, rate in rates.items():
                if cls in node["routes_by_class"]:
                    # scale the admit-vs-discharge split toward the observed rate
                    node["routes_by_class"][cls] = [
                        ["await_inpatient_bed", round(rate, 3)],
                        ["discharge", round(1 - rate, 3)]]
    return raw


def calibrate(df: pd.DataFrame, raw: dict) -> tuple[dict, list]:
    patch, summary = derive_patch(df)
    return apply_patch(raw, patch), summary


def generate_sample(days: int = 14, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    profile = np.array([6, 4, 4, 3, 3, 4, 4, 6, 13, 20, 23, 25, 25, 22, 21, 21,
                        21, 21, 20, 17, 16, 14, 10, 8], dtype=float)
    acuity_p = np.array([0.0088, 0.055, 0.2465, 0.6068, 0.0829])
    admit_p = {1: 0.55, 2: 0.45, 3: 0.22, 4: 0.08, 5: 0.03}
    rows = []
    for day in range(days):
        for hour in range(24):
            for _ in range(rng.poisson(profile[hour])):
                a = int(rng.choice([1, 2, 3, 4, 5], p=acuity_p))
                rows.append({"day": day, "arrival_hour": hour, "acuity": a,
                             "arrival_mode": "ambulance" if rng.random() < (0.6 if a <= 2 else 0.25) else "walk-in",
                             "age": int(rng.integers(0, 16)) if rng.random() < 0.22 else int(rng.integers(16, 95)),
                             "imd_decile": int(rng.integers(1, 11)),
                             "referral_source": rng.choice(["self", "GP", "111", "999"], p=[0.55, 0.18, 0.12, 0.15]),
                             "mental_health": int(rng.random() < 0.04),
                             "disposition": "admitted" if rng.random() < admit_p[a] else "discharged"})
    return pd.DataFrame(rows)
