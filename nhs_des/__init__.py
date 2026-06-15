"""
NHS Patient Flow Simulator - a generalised, config-driven redesign of the
DHSC Emergency Department discrete-event simulation beta tool.

Public API:
    Pathway, Simulation, run_pathway   - the engine
    kpis, stage_waits, ...             - metrics
    monte_carlo                        - replication with confidence intervals
    compare_scenarios, apply_scenario  - what-if scenario modelling
"""
from .engine import Pathway, Simulation, run_pathway, sample_time
from .metrics import (
    kpis, stage_waits, resource_utilisation, occupancy_timeseries, flow_counts,
)
from .montecarlo import monte_carlo
from .scenarios import compare_scenarios, apply_scenario

__all__ = [
    "Pathway", "Simulation", "run_pathway", "sample_time",
    "kpis", "stage_waits", "resource_utilisation", "occupancy_timeseries",
    "flow_counts", "monte_carlo", "compare_scenarios", "apply_scenario",
]
