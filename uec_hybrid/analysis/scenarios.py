"""
Scenario modelling and sensitivity analysis vs a baseline.

A scenario is declarative; modifiers:
    resources       {name: "+4" | "-2" | "*1.2" | 26}      DES capacity changes
                    a value may also be {"change": "+3", "hours": [13..20]} to
                    apply the change only in a time window (24h clock)
    nurses          {"change": "+3", "hours": [...] | None}  ED nursing change -
                    recomputed through the nurse-to-cubicle ratio the builder
                    applied (uses the roster/spaces it stashed in raw["uec"])
    staff_scale     float                                   whole-workforce scale
                    (e.g. 0.9 = 10% sickness/absence across every staff group,
                    nursing included via the nurse-to-cubicle ratio)
    arrivals_scale  float                                   demand surge
                    or {"scale": 1.3, "hours": [16..21]} for a time-windowed
                    surge (an evening peak, a local event)
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


def _windowed(current, change, hours):
    """Apply a change only inside a set of 24h-clock hours (roster-ifying a
    scalar capacity if needed). A 168-value (hour-of-week) roster is changed
    at those clock hours on every day."""
    cur = list(current) if isinstance(current, (list, tuple)) else [current] * 24
    return [max(0, _cap(c, change)) if (h % 24) in hours else max(0, int(round(c)))
            for h, c in enumerate(cur)]


def apply_scenario(pathway: Pathway, scenario: dict) -> tuple[Pathway, dict]:
    """Return (modified pathway, sd_overrides) for the scenario."""
    raw = copy.deepcopy(pathway.raw)
    for r, ch in scenario.get("resources", {}).items():
        if r not in raw.get("resources", {}):
            continue
        if isinstance(ch, dict):           # time-windowed: {"change": "+3", "hours": [...]}
            hours = set(ch.get("hours") or range(24))
            raw["resources"][r] = _windowed(raw["resources"][r], ch["change"], hours)
        else:
            cap = _cap(raw["resources"][r], ch)
            if isinstance(cap, list):
                raw["resources"][r] = [max(0, c) for c in cap]
            else:
                raw["resources"][r] = max(0, cap)

    # whole-workforce sickness/absence: scale every rostered staff group, and the
    # nurse rota with it (fewer nurses close cubicles through the ratio below)
    ss = scenario.get("staff_scale")
    uec = raw.get("uec") or {}
    if ss:
        from ..workforce.roles import STAFF_RESOURCES
        for r in raw.get("resources", {}):
            if r in STAFF_RESOURCES:
                raw["resources"][r] = _windowed(raw["resources"][r], f"*{float(ss)}", set(range(24)))
        if uec.get("ed_nurse_staffing"):
            uec["ed_nurse_staffing"] = [max(0, int(round(n * float(ss))))
                                        for n in uec["ed_nurse_staffing"]]
            scenario = {**scenario, "nurses": scenario.get("nurses")
                        or {"change": "*1", "hours": None}}   # force the ratio recompute

    # ED nursing: nurses limit flow through the nurse-to-cubicle ratio the builder
    # applied, so a nurse change is recomputed through that exact formula using the
    # roster and physical spaces the builder stashed in raw["uec"].
    nrs = scenario.get("nurses")
    if (nrs and uec.get("nurse_to_cubicle_ratio") and uec.get("ed_nurse_staffing")
            and "cubicle" in raw.get("resources", {})):
        ratio = int(uec["nurse_to_cubicle_ratio"])
        hours = set(nrs.get("hours") or range(24))
        n24 = [max(0, _cap(n, nrs["change"])) if (h % 24) in hours else int(n)
               for h, n in enumerate(uec["ed_nurse_staffing"])]
        phys = uec.get("physical_cubicles") or raw["resources"]["cubicle"]
        p24 = list(phys) if isinstance(phys, (list, tuple)) else [int(phys)] * len(n24)
        # no floor: zero nurses on shift opens zero cubicles
        raw["resources"]["cubicle"] = [max(0, min(int(p), n * ratio))
                                       for p, n in zip(p24, n24)]
        uec["ed_nurse_staffing"] = n24     # keep raw self-consistent for chained use

    arrivals = raw.get("arrivals", {})
    scale = scenario.get("arrivals_scale")
    if scale and "hourly_profile" in arrivals:
        if isinstance(scale, dict):        # time-windowed surge (evening peak, event)
            hours = set(scale.get("hours") or range(24))
            f = float(scale.get("scale", 1.0))
            arrivals["hourly_profile"] = [max(0.0, v * (f if h in hours else 1.0))
                                          for h, v in enumerate(arrivals["hourly_profile"])]
        else:
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
            out.append(f"'{best[0]}' improves the 4-hour standard most: +{best[1]:.1f} points "
                       f"on the {base['four_hour']:.0f}% baseline.")
        else:
            out.append(f"No scenario materially lifts the 4-hour standard above the "
                       f"{base['four_hour']:.0f}% baseline.")
        if worst[1] <= -0.5 and worst[0] != best[0]:
            out.append(f"'{worst[0]}' is the biggest risk ({worst[1]:.1f} points).")
    if "twelve_hour" in base:
        d12 = min(((r["scenario"], r["twelve_hour"] - base["twelve_hour"]) for r in rows[1:]),
                  key=lambda x: x[1])
        if d12[1] <= -0.5:
            out.append(f"12-hour waits fall most under '{d12[0]}' ({d12[1]:.1f} points).")
    if tor and tor.get("bars"):
        top = tor["bars"][0]
        out.append(f"Sensitivity: the {tor.get('metric', 'four_hour').replace('_', ' ')} result is "
                   f"most sensitive to '{top['lever']}' ({top['delta']:+.1f} points) - the lever that "
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
