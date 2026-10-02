"""
The Midshire demonstrator's committed configuration: the fixture file, the
central summary-group definitions (by stable node id) and the scenario-input
shape every other module agrees on.

Scenario inputs are ONE self-contained JSON object. Everything that changes a
simulation lives in it, and only the "model" part is hashed for the run cache -
so a cost edit can never trigger (or alter) a simulation, and a model edit
always does.
"""
from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "midshire"
FIXTURE = DATA_DIR / "midshire_demo.json"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"

PATHWAY_VERSION = "midshire-adult-pathway-v1"
METRICS_VERSION = "midshire-metrics-v1"

# parts of the scenario inputs that drive the SIMULATION (hashed for the cache)
MODEL_KEYS = ("cohort", "areas", "capacity", "space_staffing", "rota", "downstream",
              "sdec", "mental_health", "engine", "reporting")
# parts that only change FINANCE or the TARGET verdict (never re-simulated)
FINANCE_KEYS = ("cost_table", "estates")


@lru_cache(maxsize=1)
def _fixture_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def fixture() -> dict:
    """The committed Midshire fixture (a fresh copy every call)."""
    return json.loads(_fixture_text())


def fixture_hash() -> str:
    return hashlib.sha256(_fixture_text().encode()).hexdigest()[:16]


def groups() -> list[dict]:
    return copy.deepcopy(fixture()["groups"])


def state_table() -> dict:
    """(node, phase) -> {group, label, kind, area} for every occupancy state."""
    out = {}
    for g in fixture()["groups"]:
        for st in g["states"]:
            out[(st["node"], st["phase"])] = {"group": g["id"], "label": st["label"],
                                              "kind": st["kind"], "area": st.get("area")}
    return out


def baseline_inputs() -> dict:
    """The saved demo baseline as scenario inputs (pure; no store access)."""
    f = fixture()
    return {
        "fixture_version": f["fixture_version"],
        "pathway_version": PATHWAY_VERSION,
        "cohort": {"name": "adult",
                   "adult_attendances_per_day": f["cohort"]["adult_attendances_per_day"]["value"],
                   "demand_scale": 1.0},
        "areas": {"enabled": list(f["areas"]["enabled"]),
                  "hours": copy.deepcopy(f["areas"]["hours"])},
        "capacity": dict(f["capacity"]["values"]),
        "space_staffing": copy.deepcopy(f["space_staffing"]["rows"]),
        "rota": copy.deepcopy(f["rota"]["rows"]),
        "downstream": {**copy.deepcopy(f["downstream"]["sd"]),
                       "reference_beds": f["downstream"]["sd"]["inpatient_beds"]},
        "sdec": {"hours": list(f["areas"]["hours"]["sdec"]),
                 "routing": copy.deepcopy(f["sdec"]["routing"]),
                 "closed_fallback": dict(f["sdec"]["closed_fallback"]),
                 "assessment_service": dict(f["sdec"]["assessment_service"]),
                 "care_service": dict(f["sdec"]["care_service"]),
                 "admission_rate": f["sdec"]["admission_rate"],
                 "max_wait": dict(f["sdec"]["max_wait"])},
        "mental_health": {"admission_rate": f["mental_health"]["admission_rate"]},
        "engine": {k: copy.deepcopy(v) for k, v in f["engine"].items() if k != "note"},
        "reporting": {"sdec_boundary": f["sdec"]["reporting_boundary"]},
        "cost_table": copy.deepcopy(f["cost_table"]),
        "estates": copy.deepcopy(f["estates"]),
        "target": {"pct": f["target"]["pct"], "minutes": f["target"]["minutes"]},
    }


def model_part(inputs: dict) -> dict:
    return {k: inputs.get(k) for k in MODEL_KEYS}


def _canonical(obj):
    """Numbers that are whole are hashed as integers, so 1.0 (Python) and 1
    (after a round trip through a browser) are the same input."""
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, float):
        return int(obj) if obj.is_integer() else round(obj, 9)
    if isinstance(obj, dict):
        return {str(k): _canonical(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


def stable_hash(obj) -> str:
    blob = json.dumps(_canonical(obj), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def model_hash(inputs: dict) -> str:
    """Hash of everything that changes the simulation (plus the engine and
    metric versions, so a code change invalidates cached results)."""
    from ..platform.store import ENGINE_VERSION
    return stable_hash({"model": model_part(inputs), "engine": ENGINE_VERSION,
                        "pathway": PATHWAY_VERSION, "metrics": METRICS_VERSION,
                        "fixture": inputs.get("fixture_version")})


def finance_hash(inputs: dict) -> str:
    return stable_hash({k: inputs.get(k) for k in FINANCE_KEYS})
