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
        "admit_rate": float(admitted.mean() * 100),
        "mean_los_admitted": float(los[admitted].mean()) if admitted.any() else 0.0,
        "mean_los_discharged": float(los[~admitted].mean()) if (~admitted).any() else 0.0,
        "throughput_per_day": float(len(patients) / sim_days),
    }


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
