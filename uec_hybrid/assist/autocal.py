"""
AI-assisted calibration: tune the model's physics to reproduce reality.

The product ships with expert-set service times and validates itself against a
trust's real observed 4-hour performance (see ingest.validate_against_observed).
This module closes the loop automatically: a monotonic search over the global
service-time scale (slower service -> worse 4-hour, so the objective is
monotone) finds the scale at which the modelled 4-hour matches the observed
figure, and the result is saved as the same data-driven override the workbook
and /api/pathway-params use.

Honesty properties: deterministic (fixed seeds), bounded (scale clamped to a
plausible band), fully recorded (every evaluation returned in ``history``),
and reversible (clear /api/pathway-params to undo).
"""
from __future__ import annotations

from ..des.pathway import Pathway
from ..coupling.cosim import run_cosim
from ..analysis.metrics import kpis
from ..model_params import apply_params

LO, HI = 0.6, 1.8            # plausible band for a global service-time scale


def _modelled(base_raw: dict, scale: float, seeds, keep_means) -> float:
    params = {"service_scale": scale}
    if keep_means:
        params["service_mean"] = keep_means
    raw = apply_params(base_raw, params)
    p = Pathway.from_dict(raw)
    vals = [kpis(run_cosim(p, seed=s), p).get("four_hour", 0.0) for s in seeds]
    return sum(vals) / len(vals)


def auto_calibrate(base_raw: dict, observed_four_hour: float, seeds=(2, 3),
                   tol: float = 0.75, max_iter: int = 6,
                   keep_means: dict | None = None) -> dict:
    """Find the service-time scale at which modelled 4-hour ~= observed.

    ``base_raw`` must be the department raw WITHOUT a service-scale override
    already applied (per-stage means, if any, are passed via ``keep_means`` so
    they are preserved). Returns scale, modelled/observed, and the search
    history; does NOT persist anything - the caller saves via model_params.
    """
    obs = float(observed_four_hour)
    history = []

    def f(scale):
        m = _modelled(base_raw, scale, seeds, keep_means)
        history.append({"scale": round(scale, 4), "modelled": round(m, 2)})
        return m

    baseline = f(1.0)
    if abs(baseline - obs) <= tol:
        return {"scale": 1.0, "modelled": baseline, "observed": obs,
                "baseline_modelled": baseline, "within_tolerance": True,
                "history": history,
                "note": "The model already matches the observed figure - no tuning needed."}

    # 4-hour decreases as service times stretch: pick the half-interval that
    # brackets the target, clamping when even the band's edge can't reach it.
    lo, hi = (LO, 1.0) if obs > baseline else (1.0, HI)
    f_lo, f_hi = (f(lo), baseline) if obs > baseline else (baseline, f(hi))
    if obs > f_lo:              # even the fastest plausible service can't reach it
        best, modelled, clamped = lo, f_lo, True
    elif obs < f_hi:            # even the slowest plausible service can't reach it
        best, modelled, clamped = hi, f_hi, True
    else:
        clamped = False
        best, modelled = (lo, f_lo) if abs(f_lo - obs) < abs(f_hi - obs) else (hi, f_hi)
        for _ in range(max_iter):
            mid = (lo + hi) / 2
            fm = f(mid)
            if abs(fm - obs) < abs(modelled - obs):
                best, modelled = mid, fm
            if abs(fm - obs) <= tol:
                break
            if fm > obs:        # model too optimistic at mid -> need slower service
                lo = mid
            else:
                hi = mid

    within = abs(modelled - obs) <= tol
    note = (f"Tuned service times x{best:.2f}: modelled 4-hour {modelled:.1f}% vs "
            f"observed {obs:.1f}%.")
    if clamped:
        note += (" The observed figure sits outside what service-time tuning alone can "
                 "reach - check demand, staffing and bed occupancy inputs too.")
    elif not within:
        note += " Residual gap exceeds tolerance; consider more iterations or seeds."
    return {"scale": round(best, 4), "modelled": round(modelled, 2), "observed": obs,
            "baseline_modelled": round(baseline, 2), "within_tolerance": within,
            "clamped": clamped, "history": history, "note": note}
