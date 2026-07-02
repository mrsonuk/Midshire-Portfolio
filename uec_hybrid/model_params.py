"""
Editable model assumptions: the pathway's service-time means.

Service times are the model's core "physics" and the parameters most clearly
flagged as synthetic/expert-set (they are not identifiable from attendance data).
This module makes them **data**, not code: a stored override (or a workbook
tab) can scale all service times or set a specific stage's mean, and the overlay
is applied to the pathway raw before it runs - so the control tower, standards
and analyst all reflect it, and the run cache invalidates automatically because
the raw it hashes has changed.

An override is::

    {"service_scale": 1.1,               # multiply every stage's mean (and stdev)
     "service_mean": {"ed_cubicles": 90}}  # or pin a specific stage's mean (minutes)

Structural editing (adding/removing nodes, rewiring routes) is deliberately NOT
here - that changes what "the Model ED" is and would break conformance; it stays
in pathways/model_ed.json under version control.
"""
from __future__ import annotations

import copy

_SETTING_KEY = "pathway_params"


def _mean_of(spec):
    if isinstance(spec, (int, float)):
        return float(spec)
    if isinstance(spec, dict):
        if "mean" in spec:
            return float(spec["mean"])
        if "value" in spec:
            return float(spec["value"])
        if all(k in spec for k in ("low", "mode", "high")):
            return round((spec["low"] + spec["mode"] + spec["high"]) / 3.0, 2)
    return None


def service_params(raw: dict) -> list[dict]:
    """The editable service-time rows for a pathway: one per process stage."""
    rows = []
    for n in raw.get("nodes", []):
        if n.get("type") != "process":
            continue
        sv = n.get("service")
        if sv is not None:
            m = _mean_of(sv)
            dist = sv.get("dist", "constant") if isinstance(sv, dict) else "constant"
            if m is not None:
                rows.append({"node": n["id"], "label": n.get("label", n["id"]),
                             "mean": m, "dist": dist, "by_class": False})
        elif n.get("service_by_class"):
            means = [_mean_of(s) for s in n["service_by_class"].values()]
            means = [x for x in means if x is not None]
            if means:
                rows.append({"node": n["id"], "label": n.get("label", n["id"]),
                             "mean": round(sum(means) / len(means), 1),
                             "dist": "by acuity", "by_class": True})
    return rows


def _scale_spec(spec, scale):
    if isinstance(spec, dict):
        for k in ("mean", "stdev", "value", "low", "mode", "high"):
            if k in spec and isinstance(spec[k], (int, float)):
                spec[k] = round(spec[k] * scale, 3)
    return spec


def apply_params(raw: dict, params: dict | None) -> dict:
    """Overlay a service-time override onto a pathway raw (deep-copied)."""
    if not params:
        return raw
    raw = copy.deepcopy(raw)
    scale = float(params.get("service_scale", 1.0) or 1.0)
    node_mean = params.get("service_mean", {}) or {}
    for n in raw.get("nodes", []):
        if n.get("type") != "process":
            continue
        nid = n["id"]
        sv = n.get("service")
        # pin a stage's mean first (absolute), then apply the global scale
        if nid in node_mean and node_mean[nid] is not None:
            m = float(node_mean[nid])
            if isinstance(sv, dict):
                n["service"]["mean"] = m
            else:
                n["service"] = {"dist": "lognormal", "mean": m,
                                "stdev": round(m * 0.4, 2)}
            sv = n["service"]
        if scale != 1.0:
            if isinstance(sv, dict):
                _scale_spec(sv, scale)
            elif isinstance(sv, (int, float)):
                n["service"] = round(float(sv) * scale, 3)
            for cls, spec in (n.get("service_by_class") or {}).items():
                _scale_spec(spec, scale)
    return raw


# --- persistence (a stored setting, editable without code) ------------------- #
def load_params() -> dict:
    from .platform import store
    return store.get_setting(_SETTING_KEY) or {}


def save_params(params: dict) -> dict:
    """Persist a validated override (global scale + per-stage means)."""
    from .platform import store
    clean = {}
    try:
        scale = float((params or {}).get("service_scale", 1.0))
        if scale > 0 and scale != 1.0:
            clean["service_scale"] = round(scale, 4)
    except (TypeError, ValueError):
        pass
    means = {}
    for node, v in ((params or {}).get("service_mean") or {}).items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > 0:
            means[str(node)] = round(fv, 3)
    if means:
        clean["service_mean"] = means
    store.save_setting(_SETTING_KEY, clean)
    return clean
