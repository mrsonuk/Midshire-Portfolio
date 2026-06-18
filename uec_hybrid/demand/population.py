"""
Wider determinants of health -> demand and case-mix.

A parametric (illustrative) model translating population characteristics into the
arrival case-mix, per the brief's "wider determinants of health, e.g. the impact of
age or multiple deprivation on types of presentations". Deprivation lifts overall
attendance and self/999 presentation; age lifts acuity and frailty; the paediatric
share is set directly. These adjust the pathway's arrivals block; everything else in
the model is unchanged.
"""
from __future__ import annotations

import copy

ACUITIES = ["Acuity 1", "Acuity 2", "Acuity 3", "Acuity 4", "Acuity 5"]


def apply_population(raw: dict, older_fraction: float = 0.20, imd_decile: float = 5.0,
                     paediatric_fraction: float = 0.22) -> tuple[dict, float, list]:
    """Return (modified raw, demand_multiplier, summary)."""
    raw = copy.deepcopy(raw)
    arrivals = raw.setdefault("arrivals", {})
    mix = dict(arrivals.get("acuity_mix", {}))
    summary = []

    # deprivation gradient: 1 = most deprived -> higher attendance & self/999 presentation
    demand_mult = 1.0 + 0.05 * (5.5 - float(imd_decile))
    demand_mult = max(0.6, min(1.6, demand_mult))
    summary.append(f"Deprivation (IMD decile {imd_decile:.0f}) -> demand x{demand_mult:.2f}.")

    # age -> acuity skew: shift mass from A4/A5 toward A2/A3 as older_fraction rises
    skew = (older_fraction - 0.20) * 1.5
    if mix:
        moved = max(0.0, skew) * (mix.get("Acuity 4", 0) + mix.get("Acuity 5", 0)) * 0.3
        mix["Acuity 4"] = max(0.0, mix.get("Acuity 4", 0) - moved * 0.7)
        mix["Acuity 5"] = max(0.0, mix.get("Acuity 5", 0) - moved * 0.3)
        mix["Acuity 2"] = mix.get("Acuity 2", 0) + moved * 0.4
        mix["Acuity 3"] = mix.get("Acuity 3", 0) + moved * 0.6
        arrivals["acuity_mix"] = mix
        if abs(skew) > 0.01:
            summary.append(f"Older population ({older_fraction*100:.0f}% 65+) -> higher-acuity case-mix.")

    attrs = arrivals.setdefault("attributes", {})
    # frailty prevalence scales with the older fraction
    base_frailty = {"Acuity 1": 0.30, "Acuity 2": 0.28, "Acuity 3": 0.22, "Acuity 4": 0.10, "Acuity 5": 0.06}
    fmult = older_fraction / 0.20
    attrs["frailty"] = {k: round(min(0.9, v * fmult), 3) for k, v in base_frailty.items()}
    # paediatric share set directly (skewed to low acuity)
    attrs["paediatric"] = {"Acuity 1": round(0.36 * paediatric_fraction / 0.22, 3),
                           "Acuity 2": round(0.45 * paediatric_fraction / 0.22, 3),
                           "Acuity 3": round(0.73 * paediatric_fraction / 0.22, 3),
                           "Acuity 4": round(1.18 * paediatric_fraction / 0.22, 3),
                           "Acuity 5": round(1.55 * paediatric_fraction / 0.22, 3)}
    for k in attrs["paediatric"]:
        attrs["paediatric"][k] = min(0.95, attrs["paediatric"][k])
    summary.append(f"Paediatric share ~{paediatric_fraction*100:.0f}% (skewed to lower acuity).")

    # deprivation -> more arrive by ambulance / self-present
    amb = arrivals["attributes"].get("ambulance", 0.316)
    arrivals["attributes"]["ambulance"] = round(min(0.6, amb * (1 + 0.04 * (5.5 - imd_decile))), 3)

    return raw, demand_mult, summary
