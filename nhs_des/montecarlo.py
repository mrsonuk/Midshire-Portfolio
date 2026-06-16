"""
Monte-Carlo replication: run the same pathway many times with different random
seeds to quantify the variability the beta tool ignored. The original README's
top priority was *"Explore variability of simulations. This would require
Monte-Carlo modelling."* - this delivers it as a first-class, parallelised
feature with confidence intervals on every KPI.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from functools import partial

import numpy as np
import pandas as pd

from .engine import Pathway, run_pathway
from .metrics import kpis, uec_metrics


def _single_run(seed: int, pathway_raw: dict) -> dict:
    pathway = Pathway.from_dict(pathway_raw)
    result = run_pathway(pathway, seed=seed)
    # Carry the cohort UEC measures alongside the headline KPIs so Monte-Carlo
    # and scenario comparison get confidence intervals on them too.
    return {**kpis(result, pathway), **uec_metrics(result, pathway)}


def monte_carlo(pathway: Pathway, replications: int = 50, base_seed: int = 0,
                parallel: bool = True) -> dict:
    """Run ``replications`` independent simulations and summarise each KPI.

    Returns a dict with the per-run table and a summary of mean, standard
    deviation and a 95% confidence interval (percentile method) for every KPI.
    """
    seeds = [base_seed + i for i in range(replications)]
    worker = partial(_single_run, pathway_raw=pathway.raw)

    runs = []
    if parallel and replications > 1:
        try:
            with ProcessPoolExecutor() as pool:
                runs = list(pool.map(worker, seeds))
        except Exception:
            runs = [worker(s) for s in seeds]
    else:
        runs = [worker(s) for s in seeds]

    table = pd.DataFrame(runs)
    summary = {}
    for col in table.columns:
        values = table[col].to_numpy(dtype=float)
        summary[col] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            "ci_low": float(np.percentile(values, 2.5)),
            "ci_high": float(np.percentile(values, 97.5)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }
    return {"table": table, "summary": summary, "replications": replications}
