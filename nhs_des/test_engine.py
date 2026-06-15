"""
Lightweight end-to-end checks for the redesigned engine. Run with:

    python -m nhs_des.test_engine

Validates that every bundled pathway simulates, that capacities are never
exceeded (the bug that span-held resources must respect), that Monte-Carlo and
scenario comparison run, and that headline KPIs are sane.
"""
from __future__ import annotations

# Allow running directly (``python test_engine.py`` / ``python -m test_engine``)
# as well as ``python -m nhs_des.test_engine``.
if __package__ in (None, ""):
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
    __package__ = "nhs_des"

import glob
from pathlib import Path

import numpy as np

from .engine import Pathway, Simulation
from .metrics import kpis, resource_utilisation, diagnose
from .montecarlo import monte_carlo
from .scenarios import compare_scenarios

PATHWAY_DIR = Path(__file__).parent / "pathways"


def _max_concurrency(holds, resource) -> int:
    sub = holds[holds["resource"] == resource]
    if sub.empty:
        return 0
    starts = sub["start"].to_numpy()
    ends = sub["end"].to_numpy()
    return int(max(((starts <= t) & (ends > t)).sum() for t in starts))


def check_pathway(path: str) -> None:
    pathway = Pathway.load(path)
    sim = Simulation(pathway, seed=42)
    result = sim.run()

    assert not result["patients"].empty, f"{pathway.name}: no patients completed"
    k = kpis(result, pathway)
    assert k["n_patients"] > 50, f"{pathway.name}: too few patients ({k['n_patients']})"
    assert 0 <= k["target_compliance"] <= 100
    assert k["mean_los"] > 0

    # Capacities must never be exceeded, including span-held beds.
    for res, cap in pathway.resources.items():
        peak = _max_concurrency(result["holds"], res)
        assert peak <= cap, f"{pathway.name}: {res} peak {peak} > capacity {cap}"

    util = resource_utilisation(result, pathway)
    assert (util["utilisation"] <= 100.5).all(), f"{pathway.name}: utilisation > 100%"

    # Bottleneck diagnosis must name a worst stage and give a recommendation.
    diag = diagnose(result, pathway)
    assert diag["worst_stage"] and diag["recommendation"], \
        f"{pathway.name}: diagnosis incomplete"

    # Animation tracks must cover every patient and stay on-canvas.
    from .animation import build_tracks
    _, tracks, _ = build_tracks(result, pathway)
    assert len(tracks) == k["n_patients"], f"{pathway.name}: animation track count mismatch"
    for tr in tracks:
        assert (tr["x"] >= -0.01).all() and (tr["x"] <= 1.01).all()
    print(f"  OK  {pathway.name}: {k['n_patients']} patients, "
          f"{k['target_compliance']:.0f}% 4-hr, peak capacities respected")


def main() -> None:
    print("Checking pathways...")
    files = sorted(glob.glob(str(PATHWAY_DIR / "*.json")))
    for f in files:
        check_pathway(f)

    print("Checking Monte-Carlo...")
    p = Pathway.load(files[0])
    mc = monte_carlo(p, replications=6, base_seed=0, parallel=False)
    assert mc["summary"]["target_compliance"]["ci_low"] <= mc["summary"]["target_compliance"]["ci_high"]
    print("  OK  Monte-Carlo produced confidence intervals")

    print("Checking scenarios...")
    cmp = compare_scenarios(p, [{"name": "test", "resources": {list(p.resources)[0]: "+1"}}],
                            replications=1, seed=0)
    assert len(cmp["rows"]) == 2
    print("  OK  Scenario comparison ran")

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
