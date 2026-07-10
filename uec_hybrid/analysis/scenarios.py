"""
Scenario modelling and sensitivity analysis vs a baseline.

A scenario is declarative; modifiers:
    resources       {name: "+4" | "-2" | "*1.2" | 26}      DES capacity changes
    arrivals_scale  float                                   demand surge
    divert          {"classes":[...]|"attribute":..., "fraction":f}  UTC/SDEC/community redirect
    sd              {sd_param: value}                       SD-layer change (beds, discharge, community)

Comparison runs the baseline and each scenario (Monte-Carlo'd) so differences carry
confidence intervals, not single-run noise.
"""
from __future__ import annotations

import copy

from ..des.pathway import Pathway
from .montecarlo import monte_carlo


def _cap(current, change):
    if isinstance(current, (list, tuple)):
        # by-hour staffing roster: apply the change to every hour
        return [_cap(x, change) for x in current]
    if isinstance(change, str):
        change = change.strip()
        if change[0] == "+":
            return int(round(current + float(change[1:])))
        if change[0] == "-":
            return int(round(current - float(change[1:])))
        if change[0] == "*":
            return int(round(current * float(change[1:])))
    return int(round(float(change)))


def apply_scenario(pathway: Pathway, scenario: dict) -> tuple[Pathway, dict]:
    """Return (modified pathway, sd_overrides) for the scenario."""
    raw = copy.deepcopy(pathway.raw)
    for r, ch in scenario.get("resources", {}).items():
        if r in raw.get("resources", {}):
            cap = _cap(raw["resources"][r], ch)
            if isinstance(cap, list):
                raw["resources"][r] = [max(0, c) for c in cap]
            else:
                raw["resources"][r] = max(0, cap)

    arrivals = raw.get("arrivals", {})
    scale = scenario.get("arrivals_scale")
    if scale and "hourly_profile" in arrivals:
        arrivals["hourly_profile"] = [max(0.0, h * float(scale)) for h in arrivals["hourly_profile"]]

    div = scenario.get("divert")
    if div and float(div.get("fraction", 0)) > 0:
        from ..demand.streams import skew_stream_mixes, scale_stream_share, daily_stream_split
        f = float(div["fraction"])
        mix = arrivals.get("acuity_mix", {})
        diverted = 0.0
        if div.get("classes") and mix:
            classes = [c for c in div["classes"] if c in mix]
            tot = sum(mix.values()) or 1
            diverted = sum(mix[c] for c in classes) / tot * f
            new_mix = dict(mix)
            for c in classes:
                new_mix[c] = mix[c] * (1 - f)
            # streams draw their own acuity mixes, so the skew must reach them
            skew_stream_mixes(arrivals, new_mix)
        elif div.get("attribute"):
            attrs = arrivals.get("attributes", {})
            cur = attrs.get(div["attribute"])
            prev = (sum(mix.get(c, 0) / (sum(mix.values()) or 1) * cur.get(c, 0) for c in mix)
                    if isinstance(cur, dict) else float(cur or 0))
            if arrivals.get("streams") and div["attribute"] == "ambulance":
                prev = daily_stream_split(arrivals).get("ambulance", prev)
                scale_stream_share(arrivals, "ambulance", 1 - f)
            diverted = prev * f
            if isinstance(cur, dict):
                attrs[div["attribute"]] = {k: v * (1 - f) for k, v in cur.items()}
            elif cur is not None:
                attrs[div["attribute"]] = float(cur) * (1 - f)
        if "hourly_profile" in arrivals:
            arrivals["hourly_profile"] = [max(0.0, h * (1 - diverted)) for h in arrivals["hourly_profile"]]

    new = Pathway.from_dict(raw)
    new.name = f"{pathway.name} - {scenario.get('name', 'scenario')}"
    return new, scenario.get("sd")


def compare_scenarios(pathway: Pathway, scenarios: list[dict], replications: int = 10,
                      seed: int = 2000, feedback: bool = True) -> dict:
    rows = []
    for sc in [{"name": "Baseline"}] + list(scenarios):
        if sc["name"] == "Baseline":
            variant, sd_over = pathway, None
        else:
            variant, sd_over = apply_scenario(pathway, sc)
        mc = monte_carlo(variant, replications=replications, base_seed=seed,
                         feedback=feedback, sd_overrides=sd_over)
        row = {"scenario": sc["name"]}
        for kpi, st in mc["summary"].items():
            row[kpi] = st["mean"]
            row[f"{kpi}_lo"], row[f"{kpi}_hi"] = st["ci_low"], st["ci_high"]
        rows.append(row)
    return {"rows": rows, "replications": replications}


def interpret(rows: list[dict], tor: dict | None = None) -> str:
    """Plain-language read of the scenario comparison: which lever helps the 4-hour
    position most, which hurts, the biggest 12-hour win, and the top sensitivity."""
    if not rows or len(rows) < 2:
        return "Add one or more scenarios to compare against the baseline."
    base, out = rows[0], []
    if "four_hour" in base:
        d = [(r["scenario"], r["four_hour"] - base["four_hour"]) for r in rows[1:]]
        best, worst = max(d, key=lambda x: x[1]), min(d, key=lambda x: x[1])
        if best[1] >= 0.5:
            out.append(f"‘{best[0]}’ improves the 4-hour standard most: +{best[1]:.1f} points "
                       f"on the {base['four_hour']:.0f}% baseline.")
        else:
            out.append(f"No scenario materially lifts the 4-hour standard above the "
                       f"{base['four_hour']:.0f}% baseline.")
        if worst[1] <= -0.5 and worst[0] != best[0]:
            out.append(f"‘{worst[0]}’ is the biggest risk ({worst[1]:.1f} points).")
    if "twelve_hour" in base:
        d12 = min(((r["scenario"], r["twelve_hour"] - base["twelve_hour"]) for r in rows[1:]),
                  key=lambda x: x[1])
        if d12[1] <= -0.5:
            out.append(f"12-hour waits fall most under ‘{d12[0]}’ ({d12[1]:.1f} points).")
    if tor and tor.get("bars"):
        top = tor["bars"][0]
        out.append(f"Sensitivity: the {tor.get('metric', 'four_hour').replace('_', ' ')} result is "
                   f"most sensitive to ‘{top['lever']}’ ({top['delta']:+.1f} points) — the lever that "
                   f"moves the number most.")
    out.append("Bracketed figures are change vs baseline; each is a Monte-Carlo mean, so "
               "small differences may be within noise.")
    return " ".join(out)


def tornado(pathway: Pathway, levers: list[dict], replications: int = 8,
            seed: int = 3000, metric: str = "four_hour") -> dict:
    """One-at-a-time sensitivity: each lever's effect on a metric vs baseline."""
    base = monte_carlo(pathway, replications=replications, base_seed=seed)["summary"][metric]["mean"]
    bars = []
    for lever in levers:
        variant, sd_over = apply_scenario(pathway, lever)
        m = monte_carlo(variant, replications=replications, base_seed=seed,
                        sd_overrides=sd_over)["summary"].get(metric)
        if m:
            bars.append({"lever": lever["name"], "value": m["mean"], "delta": m["mean"] - base})
    bars.sort(key=lambda b: abs(b["delta"]), reverse=True)
    return {"baseline": base, "metric": metric, "bars": bars}
