"""
Run a Midshire scenario: build it through the one pipeline, simulate every
seed (matched seeds: the baseline and every scenario use the same list), and
reduce each replication to the metric contract BEFORE summarising across
replications. One replication - the first seed - is kept as the replay
(snapshot) day; nothing from different replications is blended into it.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import subprocess
import uuid
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import config as mcfg
from . import metrics as M
from .build import build_model, Model
from ..coupling.cosim import run_cosim
from ..des.pathway import Pathway
from ..platform.store import ENGINE_VERSION

THRESHOLDS = list(range(0, 1441, 15))          # minutes, for any target time


@lru_cache(maxsize=1)
def source_commit() -> str:
    try:
        root = Path(__file__).resolve().parent.parent.parent
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _within_curve(trace, raw):
    """Share of the cohort completed within each threshold (per replication),
    so a change of target TIME needs no re-simulation."""
    uec = raw.get("uec") or {}
    a, b = uec["cohort_window"]
    p = M.patients_frame(trace, uec.get("sdec_boundary", "inside_ed"),
                         M.states_frame(trace) if uec.get("sdec_boundary") == "transfer_ends_ed" else None)
    c = p[(p["arrival"] >= a) & (p["arrival"] < b)]
    if len(c) == 0:
        return [None] * len(THRESHOLDS)
    dur = np.where(c["ed_end"].notna(), c["ed_end"] - c["arrival"], np.inf)
    return [float(100.0 * (dur <= t).mean()) for t in THRESHOLDS]


def _one(args):
    raw, seed, want_replay = args
    p = Pathway.from_dict(raw)
    res = run_cosim(p, seed=seed, trace=True)
    tr = res["trace"]
    out = {"seed": seed,
           "kpis": M.replication_kpis(tr, raw, raw.get("target_minutes", 240)),
           "within": _within_curve(tr, raw),
           "stages": M.stage_metrics(tr, raw),
           "profile": M.hour_profile(tr, raw),
           "flows": M.flow_links(tr, raw)}
    hist = res.get("sd_history") or []
    if hist:
        occ = [s["bed_occupancy"] for _, s in hist]
        out["kpis"]["bed_occupancy_mean"] = float(np.mean(occ) * 100)
    if want_replay:
        out["replay"] = M.replay_series(tr, raw)
        out["replay"]["days"] = M.day_summaries(tr, raw, THRESHOLDS)
        out["bed_occupancy_series"] = [[float(t), float(s["bed_occupancy"])] for t, s in hist]
    return out


def _workers(n):
    env = os.environ.get("MIDSHIRE_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(n, os.cpu_count() or 1))


_POOL = None
_POOL_LOCK = __import__("threading").Lock()
_POOL_DISABLED = False            # set once a pool cannot be started or breaks: run in-process
log = logging.getLogger(__name__)


def start_method() -> str | None:
    """The process start method this platform supports, safest first.

    * 'forkserver' (Linux, macOS): workers come from a clean single-threaded
      parent, never from a fork of the multi-threaded web server.
    * 'spawn' (Windows has only this): a fresh interpreter per worker.
    * 'fork' only when the main module cannot be re-imported (a script read
      from stdin), where the others cannot start.
    ``MIDSHIRE_START_METHOD`` overrides when that method exists. None means
    run in-process."""
    import multiprocessing as mp
    import sys
    avail = mp.get_all_start_methods()
    want = os.environ.get("MIDSHIRE_START_METHOD")
    if want:
        return want if want in avail else None
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    importable = bool(path and os.path.exists(path)) or bool(getattr(getattr(main, "__spec__", None), "name", None))
    for m in (("forkserver", "spawn") if importable else ()) + ("fork",):
        if m in avail:
            return m
    return None


def get_pool():
    """One shared worker pool for the whole process, or None to run
    in-process (one worker, no usable start method, or a pool that failed)."""
    global _POOL, _POOL_DISABLED
    n = _workers(os.cpu_count() or 1)
    if n <= 1 or _POOL_DISABLED:
        return None
    with _POOL_LOCK:
        if _POOL is None:
            import multiprocessing as mp
            method = start_method()
            if method is None:
                return None
            try:
                _POOL = ProcessPoolExecutor(max_workers=n, mp_context=mp.get_context(method))
            except (ValueError, OSError, RuntimeError, NotImplementedError) as e:
                log.warning("Midshire: cannot start a %s worker pool (%s); running in-process.", method, e)
                _POOL_DISABLED = True
                return None
        return _POOL


def reset_pool(disable: bool = False):
    global _POOL, _POOL_DISABLED
    with _POOL_LOCK:
        if _POOL is not None:
            try:
                _POOL.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        _POOL = None
        if disable:
            _POOL_DISABLED = True


def simulate(model: Model, seeds: list[int], progress=None, cancel=None,
             replay: bool = True, pool=None) -> list[dict]:
    """Per-replication results for a built model. ``progress(done, total)``
    and ``cancel()`` let a background job report and stop. ``pool`` reuses an
    existing process pool (the package search runs hundreds of these)."""
    jobs = [(model.raw, int(s), replay and i == 0) for i, s in enumerate(seeds)]
    results = [None] * len(jobs)
    ex = None if _POOL_DISABLED else (pool if pool is not None else (get_pool() if len(jobs) > 1 else None))
    done = 0
    if ex is not None:
        from concurrent.futures import as_completed
        from concurrent.futures.process import BrokenProcessPool
        try:
            futs = {ex.submit(_one, j): i for i, j in enumerate(jobs)}
            for f in as_completed(futs):
                if cancel and cancel():
                    for g in futs:
                        g.cancel()
                    raise Cancelled()
                results[futs[f]] = f.result()
                done += 1
                if progress:
                    progress(done, len(jobs))
        except (BrokenProcessPool, OSError, RuntimeError) as e:
            # the worker pool itself failed (could not start workers, or a worker
            # died): finish the remaining replications in this process instead
            log.warning("Midshire: worker pool failed (%s: %s); finishing in-process.", type(e).__name__, e)
            reset_pool(disable=True)
    for i, j in enumerate(jobs):
        if results[i] is not None:
            continue
        if cancel and cancel():
            raise Cancelled()
        results[i] = _one(j)
        done += 1
        if progress:
            progress(done, len(jobs))
    return results


class Cancelled(Exception):
    pass


def reduce(model: Model, inputs: dict, reps: list[dict], seeds: list[int],
           seed_set: str = "selection") -> dict:
    """Summaries across replications + run metadata. Pure."""
    kp = [r["kpis"] for r in reps]
    stages = M.summarise_stage_metrics([r["stages"] for r in reps])
    profile = {}
    for key in ("census_avg", "waiting_avg", "arrivals_per_hour", "departures_per_hour"):
        profile[key] = [float(np.mean([r["profile"][key][h] for r in reps])) for h in range(24)]
    for key in ("states_avg", "milestones_per_hour", "departures_by_outcome_per_hour"):
        names = set().union(*[r["profile"].get(key, {}).keys() for r in reps])
        # a state nobody entered in a replication had zero patients in it
        profile[key] = {k: [float(np.mean([(r["profile"].get(key, {}).get(k) or [0.0] * 24)[h] for r in reps]))
                            for h in range(24)] for k in sorted(names)}
    flows = {}
    for level in ("group", "unit", "node"):
        names = set().union(*[r["flows"][level].keys() for r in reps])
        flows[level] = {k: float(np.mean([r["flows"][level].get(k, 0.0) for r in reps])) for k in sorted(names)}
    replay = next((r for r in reps if "replay" in r), None)
    uec = model.raw.get("uec") or {}
    open_cap = {r: {"min": int(min(v)), "max": int(max(v)), "week": v}
                for r, v in model.open_capacity.items()}
    phys = {r: ({"min": int(min(v)), "max": int(max(v))} if v else None)
            for r, v in model.physical.items()}
    present_nodes = [n["id"] for n in model.raw["nodes"]]
    node_res = {}
    pathway = []
    for n in model.raw["nodes"]:
        res = list(n.get("acquire") or []) + list(n.get("resources") or []) + (
            [n["resource"]] if n.get("resource") else [])
        node_res[n["id"]] = [r for r in res if r in model.raw["resources"]]
        routes = []
        if n.get("routes"):
            routes.append({"when": "otherwise", "to": [[t, round(p, 4)] for t, p in n["routes"]]})
        for cls, lst in (n.get("routes_by_class") or {}).items():
            routes.append({"when": cls, "to": [[t, round(p, 4)] for t, p in lst]})
        for att, lst in (n.get("routes_by_attribute") or {}).items():
            routes.append({"when": f"if {att.replace('_', ' ')}", "to": [[t, round(p, 4)] for t, p in lst]})
        pathway.append({"id": n["id"], "label": n.get("label", n["id"]), "type": n.get("type"),
                        "resources": node_res[n["id"]], "holds_until_release": list(n.get("acquire") or []),
                        "open_hours": n.get("open_hours"), "closed_fallback": n.get("closed_fallback"),
                        "renege_to": (n.get("renege") or {}).get("to"), "routes": routes,
                        "milestone": bool(n.get("milestone")) or (
                            n.get("type") == "process" and isinstance(n.get("service"), dict)
                            and n["service"].get("dist") == "constant" and not n["service"].get("value")
                            and not node_res[n["id"]])})
    return {
        "run_id": uuid.uuid4().hex[:12],
        "model_hash": model.model_hash,
        "fixture_version": inputs.get("fixture_version"),
        "pathway_version": mcfg.PATHWAY_VERSION, "metrics_version": mcfg.METRICS_VERSION,
        "engine_version": ENGINE_VERSION, "source_commit": source_commit(),
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "seeds": list(seeds), "seed_set": seed_set, "replications": len(reps),
        "engine": {k: v for k, v in inputs["engine"].items()},
        "target_minutes_simulated": model.raw.get("target_minutes"),
        "reps": kp,
        "within": {"thresholds": THRESHOLDS, "by_rep": [r["within"] for r in reps]},
        "summary": M.summarise_reps(kp),
        "stages": stages,
        "pressure": M.pressure_ranking(stages),
        "profile": profile,
        "flows": flows,
        "replay": ({"seed": replay["seed"], **replay["replay"],
                    "bed_occupancy": replay.get("bed_occupancy_series")} if replay else None),
        "model": {"warnings": model.warnings, "pruned_nodes": uec.get("pruned_nodes"),
                  "nodes": present_nodes, "node_resources": node_res, "pathway": pathway,
                  "provenance": model.provenance,
                  "calibration_summary": uec.get("calibration_summary"),
                  "open_capacity": open_cap, "physical_capacity": phys,
                  "staffing_week": model.staffing_week,
                  "cohort_window": uec.get("cohort_window"),
                  "sdec_boundary": uec.get("sdec_boundary")},
    }


def run(inputs: dict, seeds=None, progress=None, cancel=None, seed_set="selection",
        replay=True, pool=None) -> dict:
    model = build_model(inputs)
    seeds = list(seeds or inputs["engine"]["selection_seeds"])
    reps = simulate(model, seeds, progress=progress, cancel=cancel, replay=replay, pool=pool)
    return reduce(model, inputs, reps, seeds, seed_set)


# --------------------------------------------------------------------------- #
# target verdict (cheap; recomputed whenever the target changes)
# --------------------------------------------------------------------------- #
def within_at(result: dict, minutes: float) -> list:
    th = result["within"]["thresholds"]
    m = int(minutes)
    if m not in th:
        raise ValueError(f"target time must be a multiple of 15 minutes up to 1440 (got {minutes})")
    i = th.index(m)
    return [row[i] for row in result["within"]["by_rep"]]


def target_status(result: dict, target: dict) -> dict:
    vals = within_at(result, target["minutes"])
    s = M.summarise(vals)
    pct = float(target["pct"])
    if s is None:
        return {"status": "no observations", "target": target}
    lo = s.get("ci_low", s["mean"])
    if s["mean"] >= pct and lo >= pct:
        status = "met"
    elif s["mean"] >= pct:
        status = "met on average, within simulation noise"
    else:
        status = "not met"
    return {"status": status, "target": target, "value": s,
            "gap_pts": round(pct - s["mean"], 2),
            "note": ("Percentage of eligible adult attendances completed within "
                     f"{int(target['minutes'])} minutes, mean of {s['n']} simulated weeks; "
                     "the interval is the simulation-noise interval of that mean.")}
