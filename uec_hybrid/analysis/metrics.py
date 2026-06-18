"""
Metrics and KPIs, each tied to a Model ED / UEC Plan standard, computed from the
co-simulation result frames (events, patients, holds, sd_history).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..des.pathway import Pathway


# --------------------------------------------------------------------------- #
# Headline KPIs
# --------------------------------------------------------------------------- #
def kpis(result: dict, pathway: Pathway) -> dict:
    patients = result["patients"]
    events = result["events"]
    if patients.empty:
        return {"n_patients": 0}
    los = patients["los"]
    admitted = patients["disposition"].str.contains("Admit", case=False, na=False)
    sim_days = max(1e-9, (pathway.sim_duration - pathway.warmup) / 1440.0)
    k = {
        "n_patients": int(len(patients)),
        "throughput_per_day": float(len(patients) / sim_days),
        "mean_los": float(los.mean()),
        "median_los": float(los.median()),
        "p95_los": float(los.quantile(0.95)),
        "four_hour": float((los <= pathway.target_minutes).mean() * 100),
        "breaches": int((los > pathway.target_minutes).sum()),
        "twelve_hour": float((los > 720).mean() * 100),
        "n_twelve_hour": int((los > 720).sum()),
        "admit_rate": float(admitted.mean() * 100),
        "mean_los_admitted": float(los[admitted].mean()) if admitted.any() else 0.0,
    }
    # initial assessment within 15 minutes (Model ED front-door standard)
    node = pathway.uec.get("initial_assessment_node")
    if node and not events.empty:
        first = events[events["stage"] == node].groupby("pid")["service_start"].min()
        arr = patients.set_index("pid")["arrival"]
        ttia = (first - arr.reindex(first.index)).dropna()
        if len(ttia):
            k["initial_assessment_15min"] = float((ttia <= 15).mean() * 100)
            k["mean_initial_assessment"] = float(ttia.mean())
    return k


# --------------------------------------------------------------------------- #
# Cohort UEC measures (only where the pathway models the cohort)
# --------------------------------------------------------------------------- #
def uec_metrics(result: dict, pathway: Pathway) -> dict:
    patients = result["patients"]
    events = result["events"]
    uec = pathway.uec
    out = {}
    if patients.empty:
        return out
    arr = patients.set_index("pid")["arrival"]

    amb = uec.get("ambulance_attr")
    if amb and f"attr_{amb}" in patients.columns and not events.empty:
        pids = set(patients.loc[patients[f"attr_{amb}"], "pid"])
        ev = events[events["pid"].isin(pids) & events["stage"].isin(uec.get("ambulance_handover_stages", []))]
        if not ev.empty:
            first = ev.sort_values("service_start").groupby("pid").first()
            handover = first["service_start"] - arr.reindex(first.index)
            out["ambulance_handover_45"] = float((handover <= 45).mean() * 100)
            out["ambulance_handover_mean"] = float(handover.mean())

    mh = uec.get("mental_health_attr")
    if mh and f"attr_{mh}" in patients.columns:
        sub = patients[patients[f"attr_{mh}"]]
        if len(sub):
            out["mh_over_24h"] = float((sub["los"] > 1440).mean() * 100)
            out["mh_n"] = int(len(sub))
        # MH liaison 1-hour response standard (wait at mh_liaison)
        liaison = events[(events["stage"] == "mh_liaison") & events["pid"].isin(sub["pid"])]
        if not liaison.empty:
            out["mh_liaison_1h"] = float((liaison["wait"] <= 60).mean() * 100)

    paed = uec.get("paediatric_attr")
    if paed and f"attr_{paed}" in patients.columns:
        sub = patients[patients[f"attr_{paed}"]]
        if len(sub):
            out["child_four_hour"] = float((sub["los"] <= pathway.target_minutes).mean() * 100)
            out["child_n"] = int(len(sub))
        sr = events[(events["stage"] == "paeds_assessment") & events["pid"].isin(sub["pid"])]
        if not sr.empty:
            tt = sr.groupby("pid")["service_start"].min() - arr.reindex(sr["pid"].unique())
            tt = tt.dropna()
            if len(tt):
                out["child_senior_review_120"] = float((tt <= 120).mean() * 100)

    fr = uec.get("frailty_attr")
    if fr and f"attr_{fr}" in patients.columns:
        sub = patients[patients[f"attr_{fr}"]]
        if len(sub):
            out["frailty_n"] = int(len(sub))
            fau = events[(events["stage"] == "fau") & events["pid"].isin(sub["pid"])]
            out["frailty_fau_rate"] = float(len(set(fau["pid"])) / len(sub) * 100)

    # EEMAC conversion-to-admission rate (Model ED audit metric)
    en = uec.get("eemac_node")
    if en and not events.empty:
        epids = set(events.loc[events["stage"] == en, "pid"])
        if epids:
            disp = patients.set_index("pid")["disposition"]
            adm = disp.reindex(epids).str.contains("Admit", case=False, na=False)
            out["eemac_conversion"] = float(adm.mean() * 100)

    # whole-system signals from the SD history
    hist = result.get("sd_history") or []
    if hist:
        occ = [s["bed_occupancy"] for _, s in hist]
        out["bed_occupancy"] = float(np.mean(occ) * 100)
        out["handover_delay_mean"] = float(np.mean([s["handover_delay"] for _, s in hist]))
    return out


# --------------------------------------------------------------------------- #
# Resource utilisation, stage waits, bottleneck diagnosis, flow counts
# --------------------------------------------------------------------------- #
def resource_utilisation(result: dict, pathway: Pathway) -> pd.DataFrame:
    holds = result.get("holds")
    horizon = pathway.sim_duration - pathway.warmup
    if holds is None or holds.empty or horizon <= 0:
        return pd.DataFrame(columns=["resource", "capacity", "utilisation"])
    busy = (holds["end"] - holds["start"]).groupby(holds["resource"]).sum()
    rows = []
    for r, c in pathway.resources.items():
        # a capacity may be a by-hour roster; utilisation is measured against the
        # average staffing over the day, not the peak
        cap = (sum(c) / len(c)) if isinstance(c, (list, tuple)) else c
        rows.append({"resource": r, "capacity": round(cap, 1),
                     "utilisation": 100.0 * float(busy.get(r, 0.0)) / (cap * horizon) if cap else 0.0})
    return pd.DataFrame(rows).sort_values("utilisation", ascending=False).reset_index(drop=True)


def stage_waits(result: dict) -> pd.DataFrame:
    events = result["events"]
    if events.empty:
        return pd.DataFrame(columns=["stage", "stage_label", "n", "mean_wait", "p95_wait"])
    g = events.groupby(["stage", "stage_label"], sort=False).agg(
        n=("pid", "count"), mean_wait=("wait", "mean"),
        p95_wait=("wait", lambda s: s.quantile(0.95))).reset_index()
    return g.sort_values("mean_wait", ascending=False).reset_index(drop=True)


def flow_counts(result: dict, pathway: Pathway) -> pd.DataFrame:
    events, patients = result["events"], result["patients"]
    if events.empty or patients.empty:
        return pd.DataFrame(columns=["source", "target", "value"])
    seq = events.sort_values(["pid", "service_start"]).groupby("pid")["stage_label"].apply(list)
    disp = patients.set_index("pid")["disposition"].to_dict()
    edges = {}
    for pid, stages in seq.items():
        chain = ["Arrival"] + stages + ([disp[pid]] if pid in disp else [])
        for a, b in zip(chain[:-1], chain[1:]):
            if a != b:
                edges[(a, b)] = edges.get((a, b), 0) + 1
    return pd.DataFrame([{"source": a, "target": b, "value": v} for (a, b), v in edges.items()])


# --------------------------------------------------------------------------- #
# RAG scorecard against Model ED / UEC Plan standards
# --------------------------------------------------------------------------- #
# (metric_key, label, target, unit, higher_better, amber_band, note)
SCORECARD_SPEC = [
    ("four_hour", "4-hour standard", 78.0, "%", True, 6,
     "interim 78% en route to the 95% constitutional standard"),
    ("initial_assessment_15min", "Initial assessment ≤15 min", 90.0, "%", True, 10,
     "Model ED front-door streaming within 15 minutes"),
    ("twelve_hour", "12-hour waits", 10.0, "%", False, 5,
     "<10% of attendances over 12 hours"),
    ("ambulance_handover_45", "Ambulance handover ≤45 min", 95.0, "%", True, 10,
     "Release-to-Rescue 45-minute handover"),
    ("mh_liaison_1h", "MH liaison ≤1 hour", 90.0, "%", True, 15,
     "Core24 1-hour mental-health liaison response"),
    ("mh_over_24h", "Mental health >24h in ED", 5.0, "%", False, 10,
     "reduce patients waiting >24h for MH admission"),
    ("child_four_hour", "Children's 4-hour", 80.0, "%", True, 6,
     "more children seen within 4 hours"),
    ("eemac_conversion", "EEMAC conversion to admission", 20.0, "%", False, 10,
     "EEMAC is for expected discharge, not boarding"),
    ("bed_occupancy", "Inpatient bed occupancy", 92.0, "%", False, 3,
     ">92% drives ED exit-block / corridor care"),
]


def _rag(val, target, higher_better, amber):
    if higher_better:
        return "green" if val >= target else ("amber" if val >= target - amber else "red")
    return "green" if val <= target else ("amber" if val <= target + amber else "red")


def uec_scorecard(metrics: dict) -> list:
    """RAG cards for every standard the run produced a value for."""
    out = []
    for key, label, target, unit, hb, amber, note in SCORECARD_SPEC:
        if key not in metrics:
            continue
        val = metrics[key]
        out.append({"key": key, "label": label, "value": val, "target": target,
                    "unit": unit, "higher_better": hb, "note": note,
                    "status": _rag(val, target, hb, amber)})
    return out


def diagnose(result: dict, pathway: Pathway) -> dict:
    util = resource_utilisation(result, pathway)
    waits = stage_waits(result)
    if waits.empty:
        return {"headline": "No activity simulated.", "recommendation": "", "worst_stage": None}
    waits = waits.assign(lost_hours=lambda d: d["mean_wait"] * d["n"] / 60.0)
    waits = waits.sort_values("lost_hours", ascending=False).reset_index(drop=True)
    worst = waits.iloc[0]
    node = pathway.nodes.get(worst["stage"], {})
    res = pathway.node_resources(node)
    constraint, cu = (None, 0.0)
    if not util.empty:
        cand = util[util["resource"].isin(res)] if res else util
        row = cand.iloc[0] if not cand.empty else util.iloc[0]
        constraint, cu = row["resource"], float(row["utilisation"])
    pretty = (constraint or "").replace("_", " ")
    headline = (f"Biggest delay: <b>{worst['stage_label']}</b> — mean wait "
                f"{worst['mean_wait']:.0f} min ({worst['lost_hours']:.0f} patient-hours lost).")
    if constraint and cu >= 80:
        rec = f"<b>{pretty}</b> is the binding constraint ({cu:.0f}% utilisation); add capacity here first."
    elif constraint and cu >= 60:
        rec = f"<b>{pretty}</b> is busy ({cu:.0f}% utilisation) and likely drives this queue."
    else:
        rec = (f"No single resource is saturated (top {pretty} {cu:.0f}%); the delay is "
               f"likely downstream exit-block — see bed occupancy on the System Dynamics tab.")
    return {"headline": headline, "recommendation": rec, "worst_stage": worst["stage_label"],
            "constraint": constraint, "constraint_util": cu,
            "table": waits[["stage_label", "n", "mean_wait", "lost_hours"]].head(6).to_dict("records")}
