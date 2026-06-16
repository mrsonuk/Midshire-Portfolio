"""
uec_hybrid — a hybrid System-Dynamics + Discrete-Event Simulation model of NHS
Urgent & Emergency Care, grounded in the NHS England "Model Emergency Department"
(Feb 2026) and the Sussex "Urgent and Emergency Care Model" (Aug 2025).
"""
from .des.pathway import Pathway, validate_schema
from .coupling.cosim import CoSimulator, run_cosim
from .analysis.metrics import kpis, uec_metrics, uec_scorecard, diagnose
from .analysis.montecarlo import monte_carlo
from .analysis.scenarios import compare_scenarios, apply_scenario, tornado
from .validation.conformance import check as conformance_check

__all__ = [
    "Pathway", "validate_schema", "CoSimulator", "run_cosim",
    "kpis", "uec_metrics", "uec_scorecard", "diagnose", "monte_carlo",
    "compare_scenarios", "apply_scenario", "tornado", "conformance_check",
]
