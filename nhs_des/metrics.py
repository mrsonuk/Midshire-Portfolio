"""
KPI and time-series computation from the engine's tidy event log.

Everything an NHS planner cares about - 4-hour standard, length of stay,
queue waits, resource utilisation and live occupancy - is derived here from the
two DataFrames the engine returns. Keeping analysis separate from simulation
means new metrics never require touching the engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Pathway


def kpis(result: dict[str, pd.DataFrame], pathway: Pathway) -> dict:
    """Headline KPIs for a single simulation run."""
    patients = result["patients"]
    events = result["events"]
    target = pathway.target_minutes

    if patients.empty:
        return {
            "n_patients": 0, "mean_los": 0.0, "median_los": 0.0, "p95_los": 0.0,
            "target_compliance": 0.0, "breaches": 0, "admit_rate": 0.0,
            "mean_los_admitted": 0.0, "mean_los_discharged": 0.0, "throughput_per_day": 0.0,
        }

    los = patients["los"]
    admitted = patients["disposition"].str.contains("Admit", case=False, na=False)
    sim_days = max(1e-9, (pathway.sim_duration - pathway.warmup) / 1440.0)

    return {
        "n_patients": int(len(patients)),
        "mean_los": float(los.mean()),
        "median_los": float(los.median()),
        "p95_los": float(los.quantile(0.95)),
        "target_compliance": float((los <= target).mean() * 100),
        "breaches": int((los > target).sum()),
        # NHS UEC Plan 2025/26: patients waiting >12h for admission/discharge,
        # which should occur on <10% of attendances.
        "pct_over_12h": float((los > 720).mean() * 100),
        "n_over_12h": int((los > 720).sum()),
        "admit_rate": float(admitted.mean() * 100),
        "mean_los_admitted": float(los[admitted].mean()) if admitted.any() else 0.0,
        "mean_los_discharged": float(los[~admitted].mean()) if (~admitted).any() else 0.0,
        "throughput_per_day": float(len(patients) / sim_days),
    }


# NHS UEC Plan 2025/26 headline standards, used to RAG-rate the scorecard.
UEC_TARGETS = {
    "target_compliance": {"label": "4-hour standard", "target": 78.0,
                          "unit": "%", "higher_better": True,
                          "note": "≥78% admitted, transferred or discharged within 4h"},
    "pct_over_12h": {"label": "12-hour waits", "target": 10.0,
                     "unit": "%", "higher_better": False,
                     "note": "<10% of attendances wait over 12h for a bed/decision"},
}


def uec_scorecard(kpi: dict) -> list:
    """Rate the run against the UEC Plan 2025/26 national standards (RAG)."""
    out = []
    for key, spec in UEC_TARGETS.items():
        val = kpi.get(key, 0.0)
        if spec["higher_better"]:
            status = "green" if val >= spec["target"] else (
                "amber" if val >= spec["target"] - 6 else "red")
        else:
            status = "green" if val <= spec["target"] else (
                "amber" if val <= spec["target"] + 5 else "red")
        out.append({"key": key, "label": spec["label"], "value": val,
                    "target": spec["target"], "unit": spec["unit"],
                    "status": status, "note": spec["note"],
                    "higher_better": spec["higher_better"]})
    return out


def stage_waits(result: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Mean queue wait and service time per stage (the bottleneck table)."""
    events = result["events"]
    if events.empty:
        return pd.DataFrame(columns=["stage_label", "n", "mean_wait", "p95_wait", "mean_service"])
    grouped = events.groupby(["stage", "stage_label"], sort=False).agg(
        n=("pid", "count"),
        mean_wait=("wait", "mean"),
        p95_wait=("wait", lambda s: s.quantile(0.95)),
        mean_service=("service", "mean"),
    ).reset_index()
    return grouped.sort_values("mean_wait", ascending=False).reset_index(drop=True)


def resource_utilisation(result: dict[str, pd.DataFrame], pathway: Pathway) -> pd.DataFrame:
    """Time-weighted utilisation (% of capacity busy) for each resource,
    computed from the unified resource-hold log (covers both transient service
    holds and span-held beds)."""
    holds = result.get("holds")
    rows = []
    horizon = pathway.sim_duration - pathway.warmup
    if holds is None or holds.empty or horizon <= 0:
        return pd.DataFrame(columns=["resource", "capacity", "utilisation"])
    busy_by_res = (holds["end"] - holds["start"]).groupby(holds["resource"]).sum()
    for res_name, capacity in pathway.resources.items():
        busy = float(busy_by_res.get(res_name, 0.0))
        util = 100.0 * busy / (capacity * horizon) if capacity else 0.0
        rows.append({"resource": res_name, "capacity": capacity, "utilisation": util})
    df = pd.DataFrame(rows)
    return df.sort_values("utilisation", ascending=False).reset_index(drop=True)


def occupancy_timeseries(result: dict[str, pd.DataFrame], pathway: Pathway,
                         resources: list[str] | None = None,
                         step: float = 30.0) -> pd.DataFrame:
    """Number of patients occupying each resource over time (for the live
    occupancy chart). Sampled every ``step`` minutes."""
    holds = result.get("holds")
    if holds is None or holds.empty:
        return pd.DataFrame()
    resources = resources or list(pathway.resources.keys())
    grid = np.arange(pathway.warmup, pathway.sim_duration + step, step)
    data = {"time": grid, "hour": (grid / 60.0)}
    for res_name in resources:
        sub = holds.loc[holds["resource"] == res_name, ["start", "end"]].to_numpy()
        counts = np.array([
            np.sum((sub[:, 0] <= t) & (sub[:, 1] > t)) if len(sub) else 0
            for t in grid
        ])
        data[res_name] = counts
    return pd.DataFrame(data)


def flow_counts(result: dict[str, pd.DataFrame], pathway: Pathway) -> pd.DataFrame:
    """Patient counts on each pathway edge - drives the Sankey flow diagram."""
    events = result["events"]
    patients = result["patients"]
    if events.empty or patients.empty:
        return pd.DataFrame(columns=["source", "target", "value"])

    # Reconstruct each patient's ordered stage sequence.
    seq = (events.sort_values(["pid", "service_start"])
                 .groupby("pid")["stage_label"].apply(list))
    disposition = patients.set_index("pid")["disposition"].to_dict()

    edges: dict[tuple[str, str], int] = {}
    for pid, stages in seq.items():
        chain = ["Arrival"] + stages
        end = disposition.get(pid)
        if end:
            chain = chain + [end]
        for a, b in zip(chain[:-1], chain[1:]):
            if a == b:
                continue
            edges[(a, b)] = edges.get((a, b), 0) + 1

    rows = [{"source": a, "target": b, "value": v} for (a, b), v in edges.items()]
    return pd.DataFrame(rows)


def flow_map_data(result: dict[str, pd.DataFrame], pathway: Pathway) -> dict:
    """Nodes + links for the animated patient-flow map (the Sankey replacement).

    Each node carries its position (auto-laid-out left-to-right), patient volume,
    mean queue wait and a traffic-light status; each link carries the patient
    count flowing along it. Rendered as a living, colour-coded process map.
    """
    edges = flow_counts(result, pathway)
    if edges.empty:
        return {"nodes": [], "links": []}

    labels = sorted(set(edges["source"]) | set(edges["target"]))
    # longest-path layering for left-to-right columns
    succ = {n: [] for n in labels}
    for _, r in edges.iterrows():
        succ[r["source"]].append(r["target"])
    layer = {n: 0 for n in labels}
    for _ in range(len(labels)):
        changed = False
        for s in labels:
            for t in succ[s]:
                if layer[t] < layer[s] + 1:
                    layer[t] = layer[s] + 1
                    changed = True
        if not changed:
            break
    max_layer = max(layer.values()) or 1
    cols: dict[int, list] = {}
    for n in labels:
        cols.setdefault(layer[n], []).append(n)

    inflow = {n: int(edges[edges["target"] == n]["value"].sum()) for n in labels}
    for n in labels:
        if inflow[n] == 0:
            inflow[n] = int(edges[edges["source"] == n]["value"].sum())

    waits = stage_waits(result).set_index("stage_label")
    util = resource_utilisation(result, pathway).set_index("resource")["utilisation"].to_dict()
    label_to_id = {nd.get("label", nid): nid for nid, nd in pathway.nodes.items()}
    diag = diagnose(result, pathway)

    nodes = []
    for n in labels:
        members = sorted(cols[layer[n]])
        i, k = members.index(n), len(members)
        nid = label_to_id.get(n)
        node = pathway.nodes.get(nid, {})
        res_list = list(node.get("acquire", []) or []) + (
            node.get("resources") or ([node["resource"]] if node.get("resource") else []))
        u = max([util.get(r, 0.0) for r in res_list], default=0.0)
        mean_wait = float(waits.loc[n, "mean_wait"]) if n in waits.index else 0.0
        ntype = node.get("type", "process")
        if "admit" in n.lower():
            ntype = "admitted"
        elif "discharg" in n.lower():
            ntype = "discharged"
        elif n == "Arrival" or "referral" in n.lower():
            ntype = "source"
        # traffic-light status by queue wait
        status = "green" if mean_wait < 15 else ("amber" if mean_wait < 60 else "red")
        nodes.append({
            "id": n, "label": n, "layer": layer[n],
            "x": layer[n] / max_layer,
            "y": 0.5 if k == 1 else 0.08 + 0.84 * (i / (k - 1)),
            "volume": inflow[n], "mean_wait": round(mean_wait, 1),
            "utilisation": round(u, 1), "type": ntype, "status": status,
            "is_bottleneck": (n == diag.get("worst_stage")),
        })
    links = [{"source": r["source"], "target": r["target"], "value": int(r["value"])}
             for _, r in edges.iterrows()]
    return {"nodes": nodes, "links": links, "bottleneck": diag.get("worst_stage")}


def diagnose(result: dict[str, pd.DataFrame], pathway: Pathway) -> dict:
    """Plain-English bottleneck diagnosis for the planning team.

    Ranks stages by *total patient-hours lost to queueing* (mean wait x patients
    seen) - the right way to prioritise, since a long wait at a rarely-used stage
    matters less than a moderate wait everywhere. Names the binding resource and
    gives an actionable recommendation.
    """
    util = resource_utilisation(result, pathway)
    waits = stage_waits(result)
    if waits.empty:
        return {"headline": "No activity simulated.", "recommendation": "",
                "constraint": None, "constraint_util": 0.0,
                "worst_stage": None, "worst_wait": 0.0, "lost_hours": 0.0,
                "table": []}

    waits = waits.assign(lost_hours=lambda d: d["mean_wait"] * d["n"] / 60.0)
    waits = waits.sort_values("lost_hours", ascending=False).reset_index(drop=True)
    worst = waits.iloc[0]

    # Which resource does the worst-wait stage depend on?
    node = pathway.nodes.get(worst["stage"], {})
    stage_resources = list(node.get("acquire", []) or []) + (
        node.get("resources") or ([node["resource"]] if node.get("resource") else []))
    constraint, constraint_util = None, 0.0
    if not util.empty:
        if stage_resources:
            cand = util[util["resource"].isin(stage_resources)]
            row = (cand.iloc[0] if not cand.empty else util.iloc[0])
        else:
            row = util.iloc[0]
        constraint, constraint_util = row["resource"], float(row["utilisation"])

    pretty = (constraint or "").replace("_", " ")
    headline = (f"Biggest delay: <b>{worst['stage_label']}</b> — patients wait "
                f"{worst['mean_wait']:.0f} min on average "
                f"({worst['lost_hours']:.0f} patient-hours lost over the run).")
    if constraint and constraint_util >= 80:
        rec = (f"<b>{pretty}</b> is the binding constraint at "
               f"{constraint_util:.0f}% utilisation. Adding {pretty} capacity is "
               f"the highest-impact lever — test it under Scenario comparison.")
    elif constraint and constraint_util >= 60:
        rec = (f"<b>{pretty}</b> is busy ({constraint_util:.0f}% utilisation) and "
               f"likely drives this queue; trial extra capacity in Scenario comparison.")
    else:
        rec = (f"No single resource is saturated (top is {pretty} at "
               f"{constraint_util:.0f}%); the delay is structural — review routing "
               f"or demand timing rather than headcount.")

    table = (waits[["stage_label", "n", "mean_wait", "p95_wait", "lost_hours"]]
             .head(6).to_dict("records"))
    return {"headline": headline, "recommendation": rec,
            "constraint": constraint, "constraint_util": constraint_util,
            "worst_stage": worst["stage_label"], "worst_wait": float(worst["mean_wait"]),
            "lost_hours": float(worst["lost_hours"]), "table": table}
