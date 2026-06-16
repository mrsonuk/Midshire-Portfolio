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


def edge_frequencies(result: dict, pathway: Pathway) -> pd.DataFrame:
    from ..analysis.metrics import flow_counts
    return flow_counts(result, pathway).sort_values("value", ascending=False).reset_index(drop=True)
