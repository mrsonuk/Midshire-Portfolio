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


def _apply_area_routing(raw: dict, routing: dict) -> None:
    """Send each acuity band to the treatment area the trust actually uses for it.

    Where a trust's acuity bands ARE its areas (CUH derives its acuity mix from
    per-area attendance counts), the Model ED template's crossover splits are
    invented and measurably wrong - they gave resus 1.77x and majors ambulant
    0.50x of CUH's observed volumes. This replaces the class splits on the
    front-door nodes with the trust's own mapping.

    Applied to every node that already routes by acuity into a treatment area
    (streaming for walk-ins, RAT for ambulance arrivals), so both front doors
    reach the same places. Targets the trust does not run are skipped, leaving
    the builder's disabled-area rewrite to handle them. Mutates ``raw``.
    """
    present = {n["id"] for n in raw.get("nodes", [])}
    live = {cls: tgt for cls, tgt in routing.items() if tgt in present}
    if not live:
        return
    for node in raw.get("nodes", []):
        rbc = node.get("routes_by_class")
        if not rbc:
            continue
        # only rewrite front-door nodes: those whose class routes currently lead
        # into the treatment areas this mapping covers
        targets = {t for lst in rbc.values() for t, _ in lst}
        if not (targets & set(routing.values())):
            continue
        for cls, tgt in live.items():
            if cls in rbc:
                rbc[cls] = [[tgt, 1.0]]


def _apply_imaging(raw: dict, imaging: dict) -> None:
    """Move the imaging_decision routing onto an observed CT / X-ray workload.

    The trust's extract gives one department-wide rate per modality (imaging
    events per attendance), with no acuity breakdown - so the assumed CLINICAL
    GRADIENT across acuity is what we keep, and only its level is calibrated:
    every class's probability for that modality is scaled by a single factor
    that puts the acuity-mix-weighted average onto the observed rate. Sicker
    patients stay imaged more often than minors; the department as a whole now
    images as much as the trust really does.

    Mutates ``raw`` in place (the caller has already deep-copied it).
    """
    node = next((n for n in raw.get("nodes", []) if n.get("id") == "imaging_decision"), None)
    if not node or "routes_by_class" not in node:
        return
    routes = node["routes_by_class"]
    mix = (raw.get("arrivals", {}) or {}).get("acuity_mix") or {}
    total_mix = sum(float(v) for v in mix.values()) or 0.0

    def weight(cls):
        # weight classes by the (already calibrated) acuity mix; fall back to an
        # equal split so a pathway without a mix still calibrates sensibly
        if total_mix <= 0:
            return 1.0 / max(1, len(routes))
        return float(mix.get(cls, 0.0)) / total_mix

    for modality, target in imaging.items():
        target = float(target)
        current = sum(weight(cls) * dict((t, p) for t, p in lst).get(modality, 0.0)
                      for cls, lst in routes.items())
        if current <= 0 or target <= 0:
            continue
        k = target / current
        for cls, lst in routes.items():
            by_target = dict((t, p) for t, p in lst)
            if modality not in by_target:
                continue
            # scale this modality, then give/take the difference from the
            # straight-to-disposition remainder so each class still sums to 1
            scaled = min(1.0, by_target[modality] * k)
            delta = scaled - by_target[modality]
            by_target[modality] = scaled
            rest = [t for t in by_target if t != modality and t != "disposition"]
            slack = by_target.get("disposition", 0.0) - delta
            if slack < 0:
                # not enough room in disposition: take the shortfall off the
                # other imaging modality rather than letting the split exceed 1
                by_target["disposition"] = 0.0
                for t in rest:
                    take = min(by_target[t], -slack)
                    by_target[t] -= take
                    slack += take
            else:
                by_target["disposition"] = slack
            routes[cls] = [[t, round(p, 4)] for t, p in by_target.items()]


def apply_patch(raw: dict, patch: dict) -> dict:
    """Apply a derived calibration patch to any pathway raw (deep-copied)."""
    from .streams import skew_stream_mixes
    raw = copy.deepcopy(raw)
    arrivals = raw.setdefault("arrivals", {})
    for k, v in (patch.get("arrivals") or {}).items():
        if k == "acuity_mix":
            skew_stream_mixes(arrivals, copy.deepcopy(v))  # streams follow the data
        else:
            arrivals[k] = copy.deepcopy(v)
    attrs = arrivals.setdefault("attributes", {})
    for k, v in (patch.get("attributes") or {}).items():
        attrs[k] = v
    # streams pin the ambulance attribute, so a calibrated conveyance rate must
    # move the ambulance stream's SHARE, not just the (inert) global attribute
    if "ambulance" in (patch.get("attributes") or {}) and arrivals.get("streams"):
        from .streams import daily_stream_split, scale_stream_share
        current = daily_stream_split(arrivals).get("ambulance", 0.0)
        target = float(patch["attributes"]["ambulance"])
        if current > 0:
            scale_stream_share(arrivals, "ambulance", target / current)
            # the mix was fitted against the OLD stream weights; moving the
            # ambulance share moves those weights, so re-fit or the department
            # drifts off the calibrated mix (Cambridge landed on Acuity 1 2.0%
            # against a calibrated 2.51%, and resus saw the shortfall)
            if arrivals.get("acuity_mix"):
                skew_stream_mixes(arrivals, dict(arrivals["acuity_mix"]))
    routing = patch.get("area_routing") or {}
    if routing:
        _apply_area_routing(raw, routing)
    for node_id, spec in (patch.get("service_means") or {}).items():
        node = next((n for n in raw.get("nodes", []) if n.get("id") == node_id), None)
        if not node or not isinstance(node.get("service"), dict) or not spec:
            continue
        if isinstance(spec, dict):
            # per-acuity service: where a trust's acuity bands ARE its areas, a
            # single pooled time cannot represent a department whose post-DTA
            # wait runs 460 min on a majors trolley and 66 in minors
            base = node["service"]
            node["service_by_class"] = {
                cls: {**base, "mean": round(float(m), 1)}
                for cls, m in spec.items() if m}
        else:
            node["service"] = {**node["service"], "mean": round(float(spec), 1)}
    imaging = patch.get("imaging") or {}
    if imaging:
        _apply_imaging(raw, imaging)
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
