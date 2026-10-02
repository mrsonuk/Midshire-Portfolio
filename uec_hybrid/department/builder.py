"""
Turn a Department into a runnable model: scale to size, switch off the areas the
trust doesn't have (re-routing patients safely), and fold the workforce rota into
by-hour staffing the engine consumes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import math

from .config import AREAS, ZERO_CAPACITY_NODES, Department
from ..workforce.rota import staffing_by_hour, to_week
from ..workforce.roles import STAFF_RESOURCES, AREA_LABEL

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


def resolved_rota(dept: Department) -> tuple[list, dict]:
    """The rota the engine actually runs, plus its provenance.

    The TEMPLATE rota is written for a BASELINE-sized department, so a trust
    running 400/day against a 320/day roster was silently ~25% short of every
    staff group while its physical capacity had already been scaled up - so a
    template rota is scaled with the department. A rota somebody SUPPLIED is
    their real roster and is used exactly as given. Which one it is comes from
    the department's explicit ``rota_source``, not from comparing lists."""
    scale = max(0.3, float(dept.attendances_per_day) / BASELINE)
    src = getattr(dept, "rota_source", "supplied")
    if src == "template" and scale != 1.0:
        rota = [{**s, "count": max(1, int(round(int(s["count"]) * scale)))} for s in dept.rota]
        prov = {"source": "template", "scaled_by": round(scale, 4),
                "note": (f"Model ED template rota (written for {BASELINE:.0f}/day) scaled "
                         f"x{scale:.3f} to {dept.attendances_per_day:g} attendances/day - "
                         f"a modelled assumption, not a real roster.")}
    else:
        rota = [dict(s) for s in dept.rota]
        prov = {"source": src, "scaled_by": 1.0,
                "note": ("Model ED template rota at its native size - a modelled assumption."
                         if src == "template" else "Rota as supplied, used exactly as given.")}
    return rota, prov


def space_staffing_table(dept: Department, raw: dict) -> list[dict]:
    """The space-staffing ratios in force for this department."""
    table = getattr(dept, "space_staffing", None)
    if table is not None:
        return [dict(e) for e in table]
    ratio = (raw.get("uec") or {}).get("nurse_to_cubicle_ratio")
    return [{"space": "cubicle", "staff": "ed_nurse", "spaces_per_staff": ratio}] if ratio else []


def apply_space_staffing(raw: dict, staffing: dict, table: list[dict]) -> None:
    """Cap each staffed space at floor(staff on shift x spaces per staff),
    never above the physical count. Mutates ``raw``; stashes the physical
    counts and the staff rosters in raw["uec"] so a later what-if can recompute
    the cap exactly (the min() would otherwise make them unrecoverable)."""
    uec = raw.setdefault("uec", {})
    uec["space_staffing"] = table
    phys_all, staff_all = {}, {}
    for e in table:
        space, staff_res = e.get("space"), e.get("staff")
        k = float(e.get("spaces_per_staff") or 0)
        if space not in raw["resources"] or k <= 0:
            continue
        cap = raw["resources"][space]
        n = staffing.get(staff_res)
        if n is None:                      # nobody can staff it -> nothing opens
            n = [0] * 24
        weekly = len(n) == 168 or (isinstance(cap, list) and len(cap) == 168)
        cap_l = list(cap) if isinstance(cap, list) else [int(cap)] * 24
        if weekly:
            cap_l, n = to_week(cap_l), to_week(n)
        phys_all[space] = [int(c) for c in cap_l]
        staff_all[space] = [int(x) for x in n]
        raw["resources"][space] = [max(0, min(int(c), int(math.floor(int(x) * k + 1e-9))))
                                   for c, x in zip(cap_l, n)]
    uec["physical_spaces"] = phys_all
    uec["space_staff"] = staff_all
    # backward-compatible keys read by the what-if layer (analysis/scenarios)
    if "cubicle" in phys_all and any(e.get("space") == "cubicle" and e.get("staff") == "ed_nurse"
                                     for e in table):
        uec["physical_cubicles"] = phys_all["cubicle"]
        uec["ed_nurse_staffing"] = staff_all["cubicle"]


def zero_capacity_warnings(raw: dict) -> list[str]:
    """Resources a reachable node uses that have NO capacity at any hour.
    Patients routed there queue (or walk out where the node allows it) - a
    real consequence of a real zero, said out loud rather than papered over."""
    users = {}
    for n in raw.get("nodes", []):
        for r in (list(n.get("acquire") or []) + list(n.get("resources") or [])
                  + ([n["resource"]] if n.get("resource") else [])):
            users.setdefault(r, []).append(n.get("label", n["id"]))
    out = []
    for r, cap in raw.get("resources", {}).items():
        peak = max(cap) if isinstance(cap, list) else int(cap)
        if peak <= 0 and r in users:
            out.append(f"{AREA_LABEL.get(r, r.replace('_', ' '))} has no capacity at any hour, "
                       f"but {', '.join(sorted(set(users[r])))} uses it: patients sent there "
                       f"will wait (or leave) rather than be seen.")
    return out


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

    # --- core nodes declared out of existence via an explicit capacity of 0 ---
    # (e.g. CUH has no ED minor-injury spaces - minors are seen in the UTC).
    # Folded into the same disable/rewrite pass, keyed as a pseudo-area. Only
    # applies when the inheriting fallback node itself survives; otherwise the
    # template node stays (floored to 1 below) rather than routing into a void.
    zero_removed = {}                     # removed node id -> its config entry
    for res, cfg in ZERO_CAPACITY_NODES.items():
        if (getattr(dept, "capacity", None) or {}).get(res) != 0:
            continue
        fb = cfg["fallback"]
        fb_disabled = fb in disabled_nodes or any(
            fb in AREAS[a]["nodes"] for a in disabled_areas)
        if fb_disabled:
            continue
        key = f"zero:{cfg['node']}"
        disabled_nodes.add(cfg["node"]); node_area[cfg["node"]] = key
        fallback[key] = fb; mode[key] = "reroute"
        zero_removed[cfg["node"]] = cfg
        # NOTE: the removed node's STAFF are deliberately NOT moved to the
        # fallback. Doing so was tried and reverted: giving CUH's minors ENPs to
        # the UTC makes the ENP the binding constraint, and the template roster
        # is sized for a department where minors split across two areas - the
        # UTC then queues so hard that a quarter of the department walks out,
        # which contradicts CUH's observed minors flow (61-minute wait to be
        # treated). Sizing the roster properly needs CUH's UTC staffing, which
        # they have not given: they said only that not all 15 rooms are staffed
        # at once. Until that number arrives the UTC stays room-constrained.

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
        if fb in zero_removed:
            # the area's usual closed-hours fallback was declared out of
            # existence (capacity 0) - divert to its stated substitute instead
            fb = next((s for s in zero_removed[fb].get("closed_substitute", [])
                       if s in nodes_by_id), fb)
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

    # --- real physical capacity: the trust's own counts replace the scaled
    # template exactly (counts for disabled areas are inert - their resource is
    # already gone). Applied BEFORE the space-staffing ratios so staffing still
    # gates how many of the REAL spaces can open. An explicit 0 stays 0 ("we
    # don't have this"); it is never floored to a fictitious single space.
    for r, v in (getattr(dept, "capacity", None) or {}).items():
        if r in raw["resources"] and r not in STAFF_RESOURCES:
            raw["resources"][r] = max(0, int(v))

    # --- workforce rota -> by-hour staffing for the staff areas present ---
    # resolved_rota() is the ONE place the template is scaled, so the rota the
    # engine runs, the rota the workforce view shows and the rota that is
    # costed are the same list.
    rota, _rota_prov = resolved_rota(dept)
    staffing = staffing_by_hour(rota)
    for r in list(raw["resources"]):
        if r in STAFF_RESOURCES and r in staffing:
            raw["resources"][r] = list(staffing[r])
    uec = raw.setdefault("uec", {})
    uec["resolved_rota"] = rota
    uec["rota_provenance"] = _rota_prov

    # --- space staffing: a space only opens if there are staff to cover it ---
    # (cutting the nurse rota closes cubicles; adding nurses opens no more
    # cubicles than physically exist). The template's single nurse-to-cubicle
    # ratio is the default table; a department may supply its own.
    apply_space_staffing(raw, staffing, space_staffing_table(dept, raw))

    # --- say plainly where the department has NO capacity at all ---
    uec["build_warnings"] = zero_capacity_warnings(raw)

    # --- demand and whole-hospital levers ---
    profile = raw["arrivals"]["hourly_profile"]
    tot = sum(profile) or 1
    raw["arrivals"]["hourly_profile"] = [round(h * dept.attendances_per_day / tot, 2) for h in profile]
    sd = raw.setdefault("sd", {})
    sd["inpatient_beds"] = int(dept.inpatient_beds)
    sd["community_capacity"] = int(dept.community_capacity)
    if getattr(dept, "baseline_bed_occupancy", None) is not None:
        # a real observed occupancy (e.g. from a trust's bed-availability return)
        # sets where the exit-block feedback sits for THIS hospital
        sd["baseline_bed_occupancy"] = round(float(dept.baseline_bed_occupancy), 4)
    for k in ("background_admissions_per_hour", "ward_discharge_capacity_per_hour",
              "community_clearance_per_hour", "mh_beds"):
        if k in sd:
            sd[k] = round(sd[k] * scale, 2) if isinstance(sd[k], float) else max(1, int(round(sd[k] * scale)))
    return raw
