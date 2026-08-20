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
from scipy import stats as _st

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
    # extra cubicles come WITH the nursing to cover them, otherwise the
    # 1:N nurse-to-cubicle ratio the kernel enforces would just close them
    {"kind": "capacity", "resource": "cubicle", "add": 2,
     "with_shift": {"role": "band5_nurse", "start": 8, "end": 20, "count": 1},
     "title": "Open 2 more majors cubicles, staffed (+1 Band 5 nurse 08:00-20:00)",
     "cost_band": "Moderate"},
    {"kind": "capacity", "resource": "minor_injury_space", "add": 2,
     "title": "Add 2 minor-injury spaces", "cost_band": "Low"},
    {"kind": "capacity", "resource": "handover_bay", "add": 1,
     "title": "Add an ambulance handover bay", "cost_band": "Low"},
]

# fallbacks matching the what-if defaults, for a raw built without an sd block
_SD_DEFAULTS = {"inpatient_beds": 320, "community_capacity": 60}


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
    # downstream levers: at high ward occupancy the front door is exit-block
    # bound and no amount of ED staffing clears the noise - the honest search
    # must include the whole-hospital levers the what-if box already models
    beds_add = max(10, int(round((dept.inpatient_beds or 320) * 0.02)))
    out.append({"kind": "sd", "param": "inpatient_beds", "add": beds_add,
                "title": f"Open {beds_add} more inpatient beds (or free the equivalent "
                         f"through earlier ward discharge)", "cost_band": "High"})
    out.append({"kind": "sd", "param": "community_capacity", "add": 20,
                "title": "Add 20 community / virtual-ward discharge places a day "
                         "(pull admitted patients out sooner)", "cost_band": "Moderate"})
    return out


def _apply(dept, move):
    d = copy.deepcopy(dept)
    if move["kind"] == "shift":
        d.rota = list(d.rota) + [{"role": move["role"], "start": move["start"],
                                  "end": move["end"], "count": move["count"]}]
    elif move["kind"] == "hours":
        d.hours = {**(d.hours or {}), move["area"]: [move["open"], move["close"]]}
    if move.get("with_shift"):
        d.rota = list(d.rota) + [dict(move["with_shift"])]
    return d


def _apply_raw(raw, move):
    """Moves that act on the built pathway rather than the Department config:
    exact physical counts, and the SD-layer (whole-hospital) levers."""
    if move["kind"] == "capacity":
        cap = raw["resources"].get(move["resource"])
        if isinstance(cap, list):
            raw["resources"][move["resource"]] = [c + move["add"] for c in cap]
        elif cap is not None:
            raw["resources"][move["resource"]] = cap + move["add"]
    elif move["kind"] == "sd":
        sd = raw.setdefault("sd", {})
        sd[move["param"]] = (sd.get(move["param"], _SD_DEFAULTS.get(move["param"], 0))
                             + move["add"])
    return raw


def _raw_for(dept, move, calibration):
    raw = build_dept(_apply(dept, move) if move else dept)
    if calibration:
        raw = apply_patch(raw, calibration)
    if move:
        raw = _apply_raw(raw, move)
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
    baseline_four_hour = float(base["four_hour"].mean())

    def corridor_per_day(tab):
        return float(tab["n_twelve_hour"].mean() / days) if "n_twelve_hour" in tab else 0.0

    def evaluate(move, base_tab, n_reps):
        cand = _table(_raw_for(dept, move, calibration), n_reps, base_seed)
        d4 = cand["four_hour"].to_numpy() - base_tab["four_hour"].to_numpy()
        mean = float(d4.mean())
        se = float(d4.std(ddof=1) / np.sqrt(len(d4))) if len(d4) > 1 else 0.0
        tcrit = float(_st.t.ppf(0.95, df=max(1, len(d4) - 1)))
        lo = mean - tcrit * se                      # one-sided 95% lower bound (Student t)
        # gate on the ROUNDED bound the user is shown: a raw lo of +0.04 would
        # otherwise be recommended as "at least +0.0 with 95% confidence"
        lo = round(lo, 1)
        lwbs_d = (float(cand["lwbs"].mean() - base_tab["lwbs"].mean())
                  if "lwbs" in cand and "lwbs" in base_tab else 0.0)
        fin = business_case(
            {"delta": mean, "corridor_per_day": corridor_per_day(cand),
             "cost": move.get("cost_band", "Low")},
            {"corridor_per_day": corridor_per_day(base_tab)},
            attendances_per_day=dept.attendances_per_day, book=book)
        weekly = move.get("weekly_cost")
        ws = move.get("with_shift")
        if ws:
            weekly = (weekly or 0) + _shift_cost_per_week(
                ws["role"], ws["start"], ws["end"], ws.get("count", 1))
        net = (fin["annual_benefit"] - weekly * 52) if weekly else None
        return {
            "move": move,
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
        }

    results = [evaluate(move, base, reps) for move in moves]

    # nothing cleared at this replication count? before saying nothing, give
    # the promising candidates (positive mean effect) a tighter look with more
    # paired weeks - a real effect clears the narrower interval, noise still fails
    escalated = None
    if not any(r["confident"] for r in results):
        near = sorted([r for r in results if r["delta_four_hour"] > 0],
                      key=lambda r: r["delta_four_hour"], reverse=True)[:6]
        if near:
            escalated = min(12, max(8, reps * 2))
            base_hi = _table(base_raw, escalated, base_seed)
            for r in near:
                results[results.index(r)] = evaluate(r["move"], base_hi, escalated)

    confident = sorted([r for r in results if r["confident"]],
                       key=lambda r: (r["net_annual"] if r["net_annual"] is not None
                                      else r["annual_benefit"]), reverse=True)
    rejected = [r for r in results if not r["confident"]]
    note = ("Every candidate is simulated against the same random weeks as the "
            "baseline; only changes whose improvement clears the noise are "
            "recommended. Costs are indicative and editable in the cost book.")
    if escalated:
        note += (f" Nothing cleared at {reps} simulated weeks, so the most promising "
                 f"changes were re-tested against {escalated} paired weeks.")
    return {"recommendations": confident, "rejected": rejected,
            "baseline_four_hour": round(baseline_four_hour, 1),
            "reps": reps, "reps_escalated": escalated, "n_candidates": len(moves),
            "note": note}


def _raw_for_stack(dept, moves, calibration):
    """Build the department with a whole stack of moves applied cumulatively."""
    d = dept
    for m in moves:
        d = _apply(d, m)
    raw = build_dept(d)
    if calibration:
        raw = apply_patch(raw, calibration)
    for m in moves:
        raw = _apply_raw(raw, m)
    return raw


def target_plan(dept, target, calibration=None, book=None, reps=4,
                base_seed=1200, rec=None, max_steps=6, limit=None) -> dict:
    """Answer "what would it take to reach X% in 4 hours": stack the CI-gated
    recommendations, largest first, re-simulating each cumulative package with
    the same paired seeds, until the modelled 4-hour reaches the target or the
    confident moves run out. The answer is honest in both directions: it never
    stacks a change that failed the noise gate, and it says plainly when even
    everything together cannot reach the target."""
    target = float(target)
    rec = rec or recommend(dept, calibration=calibration, reps=reps,
                           base_seed=base_seed, book=book, limit=limit)
    reps = rec.get("reps_escalated") or reps       # stack at the reps that judged the moves
    baseline = float(rec.get("baseline_four_hour") or 0.0)
    out = {"kind": "target", "target": round(target, 1), "baseline": round(baseline, 1),
           "steps": [], "modelled": round(baseline, 1), "reached": baseline >= target}
    if baseline >= target:
        out["note"] = (f"The department is already modelled at {baseline:.1f}% within "
                       f"4 hours, at or above the {target:.0f}% goal.")
        return out
    ranked = sorted([r for r in rec.get("recommendations", []) if r.get("move")],
                    key=lambda r: r.get("delta_four_hour", 0), reverse=True)
    if not ranked:
        out["note"] = ("No change in the searched set (staffing, capacity, opening "
                       "hours, downstream beds and discharge) clears statistical "
                       "noise, even after re-testing the promising ones with more "
                       "simulated weeks. The remaining gap likely needs demand "
                       "diversion or service-time transformation - try those in the "
                       "what-if box (e.g. \"divert 20% of minors\").")
        return out
    stack, modelled = [], baseline
    for r in ranked[:max_steps]:
        stack.append(r["move"])
        tab = _table(_raw_for_stack(dept, stack, calibration), reps, base_seed)
        stacked = float(tab["four_hour"].mean())
        if stacked < modelled:
            # good alone, worse in combination (interaction or noise) - a step
            # only stays in the plan if the stacked result actually improves
            stack.pop()
            continue
        modelled = stacked
        out["steps"].append({
            "title": r["title"], "delta_four_hour": r["delta_four_hour"],
            "weekly_cost": r.get("weekly_cost"), "cost_band": r.get("cost_band"),
            "cumulative_four_hour": round(modelled, 1)})
        if modelled >= target:
            break
    out["modelled"] = round(modelled, 1)
    out["reached"] = modelled >= target
    weekly = sum(s["weekly_cost"] or 0 for s in out["steps"])
    out["weekly_cost"] = weekly or None
    if out["reached"]:
        out["note"] = (f"Stacking {len(out['steps'])} change(s) that each clear "
                       f"statistical noise takes the modelled 4-hour position from "
                       f"{baseline:.1f}% to {modelled:.1f}%, meeting the {target:.0f}% goal."
                       + (f" Added staffing costs about £{weekly:,} a week." if weekly else ""))
    else:
        out["note"] = (f"Even stacking every change that clears statistical noise "
                       f"reaches {modelled:.1f}%, short of the {target:.0f}% goal from a "
                       f"{baseline:.1f}% baseline. Closing the rest needs levers outside "
                       f"this search, such as demand diversion or service-time "
                       f"transformation - try them in the what-if box.")
    return out
