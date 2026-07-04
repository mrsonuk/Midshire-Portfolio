"""
Observed process map from the simulated event log: the distinct pathway *variants*
(ordered stage sequences) and their frequencies, plus directed edge frequencies.
This is the data behind the side-by-side observed-vs-intended process-map view.
"""
from __future__ import annotations

import pandas as pd

from ..des.pathway import Pathway


def variants(result: dict, top: int = 12) -> pd.DataFrame:
    events = result["events"]
    patients = result["patients"]
    if events.empty:
        return pd.DataFrame(columns=["variant", "count"])
    seq = events.sort_values(["pid", "service_start"]).groupby("pid")["stage_label"].apply(
        lambda s: " → ".join(s))
    disp = patients.set_index("pid")["disposition"]
    full = seq + " → " + disp.reindex(seq.index).fillna("")
    vc = full.value_counts().head(top).reset_index()
    vc.columns = ["variant", "count"]
    return vc


def variant_timing(result: dict, top: int = 12) -> list[dict]:
    """For each of the most common pathway variants, the mean time patients spent
    at each stage along that path (queue + treatment) and the total (mean length
    of stay) for that variant. This ties the timing to the actual route taken."""
    events, patients = result["events"], result["patients"]
    if events.empty or patients.empty:
        return []
    ev = events.sort_values(["pid", "service_start"]).copy()
    ev["in_stage"] = ev["wait"] + ev["service"]
    seq = ev.groupby("pid")["stage_label"].apply(lambda s: " → ".join(s))
    disp = patients.set_index("pid")["disposition"]
    full = seq + " → " + disp.reindex(seq.index).fillna("")
    los = patients.set_index("pid")["los"]
    groups = full.groupby(full).groups                 # variant string -> pids
    out = []
    for variant, count in full.value_counts().head(top).items():
        pids = list(groups[variant])
        sub = ev[ev["pid"].isin(pids)]
        stage_mean = sub.groupby("stage_label")["in_stage"].mean()
        stage_seq = variant.split(" → ")[:-1]          # drop the disposition token
        stages, seen = [], set()
        for s in stage_seq:                             # keep the route's own order
            if s in seen:
                continue
            seen.add(s)
            if s in stage_mean.index:
                stages.append({"stage": s, "mean_min": round(float(stage_mean[s]), 1)})
        out.append({"variant": variant, "count": int(count),
                    "disposition": variant.split(" → ")[-1],
                    "stages": stages,
                    "total_min": round(float(los.reindex(pids).mean()), 1)})
    return out


def edge_frequencies(result: dict, pathway: Pathway) -> pd.DataFrame:
    from ..analysis.metrics import flow_counts
    return flow_counts(result, pathway).sort_values("value", ascending=False).reset_index(drop=True)
