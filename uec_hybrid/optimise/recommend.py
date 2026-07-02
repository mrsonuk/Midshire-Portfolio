"""
The recommendation engine: "what should we change?"

Candidate moves are generated from the department's own weak points (the
understaffed windows in its rota, its pinch resources, its part-time areas),
then each is evaluated against the baseline with PAIRED Monte-Carlo seeds so
the comparison subtracts the shared randomness. A move is only recommended
when its improvement is statistically defensible (the one-sided 95% interval
on the paired delta excludes zero) - the engine would rather say nothing than
recommend noise.
"""
from __future__ import annotations

import copy

import numpy as np

from ..des.pathway import Pathway
from ..analysis.montecarlo import monte_carlo
from ..department.builder import build as build_dept
from ..demand.ecds_seam import apply_patch
from ..workforce.roles import ROLES
from ..workforce.view import workforce_view

# roles the engine can add per staff area, cheapest sensible option first
AREA_ROLE = {"streaming_nurse": "streaming_nurse", "rat_clinician": "rat_consultant",
             "ed_doctor": "em_sho", "paeds_doctor": "paeds_doctor",
             "specialty_doctor": "sdec_doctor", "frailty_team": "frailty_pract",
             "mh_clinician": "mh_liaison", "ed_nurse": "band5_nurse",
             "minors_enp": "enp", "porter_pool": "porter"}

PHYSICAL_MOVES = [
    {"kind": "capacity", "resource": "cubicle", "add": 2,
     "title": "Open 2 more majors cubicles", "cost_band": "Moderate"},
    {"kind": "capacity", "resource": "minor_injury_space", "add": 2,
     "title": "Add 2 minor-injury spaces", "cost_band": "Low"},
    {"kind": "capacity", "resource": "handover_bay", "add": 1,
     "title": "Add an ambulance handover bay", "cost_band": "Low"},
]


def _shift_cost_per_week(role_id, start, end, count=1):
    hours = (end - start) % 24 or 24
    return int(ROLES[role_id]["cost"] * hours * count * 7)


def _candidates(dept, wf) -> list:
    out = []
    # staffing: cover each understaffed window with one more of the area's role
    for a in wf["areas"]:
        hrs = a["understaffed_hours"]
        role = AREA_ROLE.get(a["resource"])
        if not hrs or not role:
            continue
        start = max(0, min(hrs) - 1)
        end = min(24, max(hrs) + 2)
        if (end - start) < 4:
            end = min(24, start + 4)
        out.append({"kind": "shift", "role": role, "start": start, "end": end, "count": 1,
                    "title": f"Add 1 {ROLES[role]['label']} {start:02d}:00-{end:02d}:00",
                    "weekly_cost": _shift_cost_per_week(role, start, end)})
    out.extend(copy.deepcopy(PHYSICAL_MOVES))
    # part-time areas: two more opening hours
    for area in ("sdec", "eemac", "fit_to_sit"):
        if area in dept.enabled:
            o, c = dept.hours_for(area)
            if [o, c] != [0, 24] and c < 23:
                out.append({"kind": "hours", "area": area, "open": o, "close": min(24, c + 2),
                            "title": f"Keep {area.upper().replace('_', '-')} open two hours later "
                                     f"(to {min(24, c + 2):02d}:00)", "cost_band": "Low"})
    return out


def _apply(dept, move):
    d = copy.deepcopy(dept)
    if move["kind"] == "shift":
        d.rota = list(d.rota) + [{"role": move["role"], "start": move["start"],
                                  "end": move["end"], "count": move["count"]}]
    elif move["kind"] == "hours":
        d.hours = {**(d.hours or {}), move["area"]: [move["open"], move["close"]]}
    return d


def _raw_for(dept, move, calibration):
    raw = build_dept(_apply(dept, move) if move else dept)
    if calibration:
        raw = apply_patch(raw, calibration)
    if move and move["kind"] == "capacity":
        cap = raw["resources"].get(move["resource"])
        if isinstance(cap, list):
            raw["resources"][move["resource"]] = [c + move["add"] for c in cap]
        elif cap is not None:
            raw["resources"][move["resource"]] = cap + move["add"]
    return raw


def _table(raw, reps, base_seed):
    mc = monte_carlo(Pathway.from_dict(raw), replications=reps,
                     base_seed=base_seed, feedback=True)
    return mc["table"]


def recommend(dept, calibration=None, reps=4, base_seed=1200, limit=None,
              book=None) -> dict:
    """Ranked, CI-gated recommendations for the configured department."""
    from ..finance import business_case, load_cost_book
    book = book or load_cost_book()
    wf = workforce_view(dept)
    moves = _candidates(dept, wf)
    if limit:
        moves = moves[:limit]

    base_raw = _raw_for(dept, None, calibration)
    days = max(1.0, (base_raw.get("sim_duration_minutes", 10080)
                     - base_raw.get("warmup_minutes", 1440)) / 1440.0)
    base = _table(base_raw, reps, base_seed)

    def corridor_per_day(tab):
        return float(tab["n_twelve_hour"].mean() / days) if "n_twelve_hour" in tab else 0.0

    results = []
    for move in moves:
        cand = _table(_raw_for(dept, move, calibration), reps, base_seed)
        d4 = cand["four_hour"].to_numpy() - base["four_hour"].to_numpy()
        mean, se = float(d4.mean()), float(d4.std(ddof=1) / np.sqrt(len(d4))) if len(d4) > 1 else 0.0
        lo = mean - 1.64 * se                       # one-sided 95% lower bound
        lwbs_d = (float(cand["lwbs"].mean() - base["lwbs"].mean())
                  if "lwbs" in cand and "lwbs" in base else 0.0)
        fin = business_case(
            {"delta": mean, "corridor_per_day": corridor_per_day(cand),
             "cost": move.get("cost_band", "Low")},
            {"corridor_per_day": corridor_per_day(base)},
            attendances_per_day=dept.attendances_per_day, book=book)
        weekly = move.get("weekly_cost")
        net = (fin["annual_benefit"] - weekly * 52) if weekly else None
        results.append({
            "title": move["title"], "kind": move["kind"],
            "delta_four_hour": round(mean, 1), "delta_low": round(lo, 1),
            "delta_lwbs": round(lwbs_d, 1),
            "confident": bool(lo > 0),
            "weekly_cost": weekly, "cost_band": move.get("cost_band"),
            "annual_benefit": fin["annual_benefit"],
            "net_annual": round(net) if net is not None else None,
            "summary": (f"+{mean:.1f} points on the 4-hour standard "
                        f"(at least +{lo:.1f} with 95% confidence)" if lo > 0 else
                        f"about +{mean:.1f} points, but within the noise - not recommended"),
        })

    confident = sorted([r for r in results if r["confident"]],
                       key=lambda r: (r["net_annual"] if r["net_annual"] is not None
                                      else r["annual_benefit"]), reverse=True)
    rejected = [r for r in results if not r["confident"]]
    return {"recommendations": confident, "rejected": rejected,
            "reps": reps, "n_candidates": len(moves),
            "note": ("Every candidate is simulated against the same random weeks as the "
                     "baseline; only changes whose improvement clears the noise are "
                     "recommended. Costs are indicative and editable in the cost book.")}
