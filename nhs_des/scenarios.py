"""
Scenario modelling: define "what-if" changes to a pathway and compare KPIs
against the baseline. This is the feature the beta tool lacked entirely - it
could only run one configuration at a time and overwrote previous outputs.

A scenario is expressed as a small set of declarative modifiers, e.g.::

    {"name": "+4 doctors, +6 beds",
     "resources": {"ed_doctor": "+4", "majors_bed": "+6"},
     "arrivals_scale": 1.0}

Modifiers
---------
* ``resources``      - per-resource capacity change. Values may be absolute
                       integers or relative strings like "+4" / "-2" / "*1.2".
* ``arrivals_scale`` - multiply every hourly arrival rate (demand surge / winter).
"""
from __future__ import annotations

import copy

from .engine import Pathway, run_pathway
from .metrics import kpis, uec_metrics
from .montecarlo import monte_carlo


def _apply_capacity(current: float, change) -> int:
    if isinstance(change, str):
        change = change.strip()
        if change.startswith("+"):
            return int(round(current + float(change[1:])))
        if change.startswith("-"):
            return int(round(current - float(change[1:])))
        if change.startswith("*"):
            return int(round(current * float(change[1:])))
        return int(round(float(change)))
    return int(round(change))


def apply_scenario(pathway: Pathway, scenario: dict) -> Pathway:
    """Return a new Pathway with the scenario's modifiers applied."""
    raw = copy.deepcopy(pathway.raw)

    for res, change in scenario.get("resources", {}).items():
        if res in raw.get("resources", {}):
            raw["resources"][res] = max(0, _apply_capacity(raw["resources"][res], change))

    scale = scenario.get("arrivals_scale")
    if scale and "hourly_profile" in raw.get("arrivals", {}):
        raw["arrivals"]["hourly_profile"] = [
            max(0.0, h * float(scale)) for h in raw["arrivals"]["hourly_profile"]
        ]

    # Care-setting redirection: a fraction of a cohort is managed elsewhere
    # (UTC/SDEC for low-acuity, or 'call before convey' / see-and-treat for
    # ambulances), so total demand falls and the case-mix shifts.
    _apply_divert(raw, scenario.get("divert"))

    new = Pathway.from_dict(raw)
    new.name = f"{pathway.name} - {scenario.get('name', 'scenario')}"
    return new


def _attr_prevalence(attributes: dict, attr: str, mix: dict) -> float:
    p = attributes.get(attr, 0)
    if isinstance(p, dict):
        tot = sum(mix.values()) or 1
        return sum(mix.get(c, 0) / tot * p.get(c, 0) for c in mix)
    return float(p)


def _apply_divert(raw: dict, divert) -> None:
    if not divert:
        return
    arrivals = raw.get("arrivals", {})
    mix = arrivals.get("acuity_mix", {})
    fraction = float(divert.get("fraction", 0.0))
    if fraction <= 0:
        return

    if divert.get("classes") and mix:
        classes = [c for c in divert["classes"] if c in mix]
        tot = sum(mix.values()) or 1
        diverted_share = sum(mix[c] for c in classes) / tot * fraction
        for c in classes:
            mix[c] = mix[c] * (1 - fraction)
    elif divert.get("attribute"):
        attr = divert["attribute"]
        attrs = arrivals.get("attributes", {})
        prev = _attr_prevalence(attrs, attr, mix)
        diverted_share = prev * fraction
        cur = attrs.get(attr)
        if isinstance(cur, dict):
            attrs[attr] = {k: v * (1 - fraction) for k, v in cur.items()}
        elif cur is not None:
            attrs[attr] = float(cur) * (1 - fraction)
    else:
        return

    if "hourly_profile" in arrivals:
        arrivals["hourly_profile"] = [max(0.0, h * (1 - diverted_share))
                                      for h in arrivals["hourly_profile"]]


def compare_scenarios(pathway: Pathway, scenarios: list[dict],
                      replications: int = 1, seed: int = 0) -> dict:
    """Run a baseline and each scenario, returning KPI rows for comparison.

    When ``replications`` > 1 each scenario is Monte-Carlo'd and the mean KPI
    (with confidence interval) is reported, so comparisons reflect uncertainty
    rather than a single lucky/unlucky run.
    """
    definitions = [{"name": "Baseline"}] + list(scenarios)
    rows = []
    for sc in definitions:
        variant = pathway if sc["name"] == "Baseline" else apply_scenario(pathway, sc)
        if replications > 1:
            mc = monte_carlo(variant, replications=replications, base_seed=seed)
            summary = mc["summary"]
            row = {"scenario": sc["name"]}
            for kpi, stats in summary.items():
                row[kpi] = stats["mean"]
                row[f"{kpi}_lo"] = stats["ci_low"]
                row[f"{kpi}_hi"] = stats["ci_high"]
            rows.append(row)
        else:
            result = run_pathway(variant, seed=seed)
            row = {"scenario": sc["name"]}
            row.update(kpis(result, variant))
            row.update(uec_metrics(result, variant))
            rows.append(row)
    return {"rows": rows, "replications": replications}
