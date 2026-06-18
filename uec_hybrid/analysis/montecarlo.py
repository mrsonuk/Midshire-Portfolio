"""
Monte-Carlo replication: run the coupled SD+DES many times with different seeds to
quantify the variability the brief requires ("uncertainty explicitly modelled using
a Monte-Carlo simulation"). Each replication returns the merged headline + cohort
metrics plus the bed-occupancy time-series, all summarised with 95% confidence
intervals.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from functools import partial

import numpy as np
import pandas as pd

from ..des.pathway import Pathway
from ..coupling.cosim import run_cosim
from .metrics import kpis, uec_metrics


def _single(seed: int, raw: dict, feedback: bool, sd_overrides: dict | None) -> dict:
    pathway = Pathway.from_dict(raw)
    result = run_cosim(pathway, seed=seed, feedback=feedback, sd_overrides=sd_overrides)
    m = {**kpis(result, pathway), **uec_metrics(result, pathway)}
    # carry a coarse bed-occupancy series for the SD uncertainty band
    hist = result.get("sd_history") or []
    m["_occ_series"] = [s["bed_occupancy"] * 100 for _, s in hist]
    return m


def monte_carlo(pathway: Pathway, replications: int = 30, base_seed: int = 1000,
                feedback: bool = True, sd_overrides: dict | None = None,
                parallel: bool = True) -> dict:
    seeds = [base_seed + i for i in range(replications)]
    worker = partial(_single, raw=pathway.raw, feedback=feedback, sd_overrides=sd_overrides)
    runs = []
    if parallel and replications > 1:
        try:
            with ProcessPoolExecutor() as pool:
                runs = list(pool.map(worker, seeds))
        except Exception:
            runs = [worker(s) for s in seeds]
    else:
        runs = [worker(s) for s in seeds]

    occ_series = [r.pop("_occ_series", []) for r in runs]
    table = pd.DataFrame(runs)
    summary = {}
    for col in table.columns:
        v = pd.to_numeric(table[col], errors="coerce").dropna().to_numpy()
        if len(v) == 0:
            continue
        summary[col] = {
            "mean": float(np.mean(v)), "std": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
            "ci_low": float(np.percentile(v, 2.5)), "ci_high": float(np.percentile(v, 97.5)),
            "min": float(np.min(v)), "max": float(np.max(v))}
    return {"table": table, "summary": summary, "replications": replications,
            "occ_series": occ_series}
