"""
Turn a Department into a runnable model: scale to size, switch off the areas the
trust doesn't have (re-routing patients safely), and fold the workforce rota into
by-hour staffing the engine consumes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .config import AREAS, Department
from ..workforce.rota import staffing_by_hour
from ..workforce.roles import STAFF_RESOURCES

BASE_RAW = json.load(open(Path(__file__).resolve().parent.parent / "pathways" / "model_ed.json"))
BASELINE = 320.0


def _rewrite(routes, disabled_nodes, node_area, fallback, mode, source_id):
    """Rewrite a [[target, prob], …] list around disabled targets."""
    out = []
    for tgt, prob in routes:
        if tgt in disabled_nodes:
            area = node_area[tgt]
            fb, md = fallback[area], mode[area]
            if md in ("reroute", "attribute") and fb and fb != source_id:
                out.append([fb, prob])          # divert to the fallback area
            # 'option' or self-loop: drop the edge (renormalised below)
        else:
            out.append([tgt, prob])
    merged = {}
    for t, p in out:
        merged[t] = merged.get(t, 0) + p
    s = sum(merged.values())
    return [[t, (p / s if s else p)] for t, p in merged.items()]


def build(dept: Department) -> dict:
    raw = copy.deepcopy(BASE_RAW)
    scale = max(0.3, dept.attendances_per_day / BASELINE)

    # --- disable areas the trust does not have ---
    disabled_areas = [a for a in AREAS if a not in dept.enabled]
    disabled_nodes, node_area, fallback, mode = set(), {}, {}, {}
    for a in disabled_areas:
        for n in AREAS[a]["nodes"]:
            disabled_nodes.add(n); node_area[n] = a
        fallback[a] = AREAS[a]["fallback"]; mode[a] = AREAS[a]["mode"]

    if disabled_nodes:
        for node in raw["nodes"]:
            sid = node["id"]
            if "routes" in node:
                node["routes"] = _rewrite(node["routes"], disabled_nodes, node_area, fallback, mode, sid)
            for cls, r in (node.get("routes_by_class") or {}).items():
                node["routes_by_class"][cls] = _rewrite(r, disabled_nodes, node_area, fallback, mode, sid)
            for at, r in (node.get("routes_by_attribute") or {}).items():
                node["routes_by_attribute"][at] = _rewrite(r, disabled_nodes, node_area, fallback, mode, sid)
            if node.get("routes_by_signal"):
                node["routes_by_signal"] = [d for d in node["routes_by_signal"]
                                            if d["target"] not in disabled_nodes]
        raw["nodes"] = [n for n in raw["nodes"] if n["id"] not in disabled_nodes]

    # --- opening hours: enabled part-time areas divert to their fallback when closed ---
    nodes_by_id = {n["id"]: n for n in raw["nodes"]}
    for a in dept.enabled:
        if a not in AREAS:
            continue
        o, c = dept.hours_for(a)
        if [o, c] == [0, 24]:
            continue                       # 24/7: nothing to gate
        entry = AREAS[a]["nodes"][0]       # the area's entry node
        fb = AREAS[a]["fallback"]
        node = nodes_by_id.get(entry)
        if node is not None and fb in nodes_by_id and fb != entry:
            node["open_hours"] = [int(o), int(c)]
            node["closed_fallback"] = fb

    # --- resources: drop those only used by disabled areas; scale spaces by size ---
    used = set()
    for n in raw["nodes"]:
        used |= set(n.get("acquire", []) or [])
        used |= set(n.get("resources") or ([n["resource"]] if n.get("resource") else []))
    for r in list(raw["resources"]):
        if r not in used:
            del raw["resources"][r]
        elif r not in STAFF_RESOURCES:
            raw["resources"][r] = max(1, int(round(raw["resources"][r] * scale)))

    # --- workforce rota -> by-hour staffing for the staff areas present ---
    staffing = staffing_by_hour(dept.rota)
    for r in list(raw["resources"]):
        if r in STAFF_RESOURCES and r in staffing:
            raw["resources"][r] = list(staffing[r])

    # --- demand and whole-hospital levers ---
    profile = raw["arrivals"]["hourly_profile"]
    tot = sum(profile) or 1
    raw["arrivals"]["hourly_profile"] = [round(h * dept.attendances_per_day / tot, 2) for h in profile]
    sd = raw.setdefault("sd", {})
    sd["inpatient_beds"] = int(dept.inpatient_beds)
    sd["community_capacity"] = int(dept.community_capacity)
    for k in ("background_admissions_per_hour", "ward_discharge_capacity_per_hour",
              "community_clearance_per_hour", "mh_beds"):
        if k in sd:
            sd[k] = round(sd[k] * scale, 2) if isinstance(sd[k], float) else max(1, int(round(sd[k] * scale)))
    return raw
