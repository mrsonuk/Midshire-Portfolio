"""
The flow-model "Figure 1" data builder: the whole UEC pathway as one connected
map. DES stage nodes are laid out left-to-right by acuity x time **band**, sized by
patient volume and traffic-light coloured by queue wait; the System Dynamics stocks
(inpatient beds, MH beds, community) are attached as reservoirs with the feedback
arrow back into the ED. Rendered client-side as animated SVG.
"""
from __future__ import annotations

import numpy as np

from ..des.pathway import Pathway, BANDS
from ..analysis.metrics import (flow_counts, stage_waits, resource_utilisation, diagnose)

BAND_LABEL = {
    "front_door": "Front door (15 min)",
    "core_0_4h": "Core ED (0-4h)",
    "emergency_4_12h": "Emergency / specialist (4-12h)",
    "admission_12h_plus": "Admission (>12h)",
}

# Plain captions so the flow map distinguishes process steps from final outcomes.
NODE_CAPTION = {
    "Discharge": "In ED — final checks",
    "Discharged": "Went home",
    "Discharged to community": "To community / virtual ward",
    "Admitted": "To inpatient ward",
    "Admitted (MH)": "To MH bed",
    "Left without being seen": "Walked out before seen",
    "Arrival": "Incoming",
}


def _hourly_counts(times, warmup, duration) -> list[int]:
    """Bin timestamps into 24 hour-of-day counts (post-warmup)."""
    out = [0] * 24
    if len(times) == 0:
        return out
    t = times[(times >= warmup) & (times < duration)]
    if len(t) == 0:
        return out
    hod = (t / 60 % 24).astype(int)
    for h in range(24):
        out[h] = int((hod == h).sum())
    return out


def flow_model_data(result: dict, pathway: Pathway) -> dict:
    edges = flow_counts(result, pathway)
    if edges.empty:
        return {"nodes": [], "links": [], "stocks": [], "bands": []}
    waits = stage_waits(result).set_index("stage_label")
    util = resource_utilisation(result, pathway).set_index("resource")["utilisation"].to_dict()
    label_to_id = {n.get("label", i): i for i, n in pathway.nodes.items()}
    diag = diagnose(result, pathway)

    labels = sorted(set(edges["source"]) | set(edges["target"]))
    inflow = {n: int(edges[edges["target"] == n]["value"].sum()) for n in labels}
    for n in labels:
        if inflow[n] == 0:
            inflow[n] = int(edges[edges["source"] == n]["value"].sum())

    # column = band index (front-door .. admission); sinks in a final column
    def column(label):
        nid = label_to_id.get(label)
        node = pathway.nodes.get(nid, {})
        if node.get("type") == "sink" or "admit" in label.lower() or "discharg" in label.lower():
            return len(BANDS)
        if label == "Arrival":
            return -1
        if node.get("band"):
            return BANDS.index(node["band"])
        return len(BANDS) - 1

    cols = {}
    for n in labels:
        cols.setdefault(column(n), []).append(n)
    max_col = max(cols)

    def kind(label):
        k = label.lower()
        if "admit" in k:
            return "admitted"
        if "discharg" in k:
            return "discharged"
        if label == "Arrival":
            return "source"
        return "process"

    nodes = []
    for col, members in cols.items():
        members = sorted(members, key=lambda m: -inflow.get(m, 0))
        k = len(members)
        for i, n in enumerate(members):
            nid = label_to_id.get(n)
            node = pathway.nodes.get(nid, {})
            res = pathway.node_resources(node)
            u = max([util.get(r, 0.0) for r in res], default=0.0)
            w = float(waits.loc[n, "mean_wait"]) if n in waits.index else 0.0
            status = "green" if w < 15 else ("amber" if w < 60 else "red")
            nodes.append({
                "id": n, "label": n,
                "caption": NODE_CAPTION.get(n),
                "x": (col + 1) / (max_col + 2),
                "y": 0.5 if k == 1 else 0.06 + 0.88 * (i / (k - 1)),
                "volume": inflow[n], "mean_wait": round(w),
                "utilisation": round(u), "kind": kind(n), "status": status,
                "band": node.get("band"), "is_bottleneck": n == diag.get("worst_stage")})

    links = [{"source": r["source"], "target": r["target"], "value": int(r["value"])}
             for _, r in edges.iterrows()]

    # SD stocks (final SD state) as reservoirs feeding back into admission
    hist = result.get("sd_history") or []
    last = hist[-1][1] if hist else {}
    stocks = [
        {"name": "Inpatient beds", "occupancy": round(last.get("bed_occupancy", 0) * 100),
         "signal": "exit-block", "feeds": "Wait for inpatient bed"},
        {"name": "MH beds", "occupancy": round(last.get("mh_occupancy", 0) * 100),
         "signal": "MH exit-block", "feeds": "Wait for MH bed"},
        {"name": "Community / virtual ward", "occupancy": round(
            100 * last.get("community_used", 0) / max(1, pathway.sd.get("community_capacity", 60))),
         "signal": "active pull", "feeds": "Refer to community / virtual ward"},
    ]
    band_legend = [{"key": b, "label": BAND_LABEL[b]} for b in BANDS]
    return {"nodes": nodes, "links": links, "stocks": stocks, "bands": band_legend,
            "bottleneck": diag.get("worst_stage")}


# --------------------------------------------------------------------------- #
# Control-tower extras: time-of-day occupancy, department census, when-it-bites
# --------------------------------------------------------------------------- #
import numpy as np


def _occ_by_hour(starts, ends, warmup, duration, step=10):
    if len(starts) == 0:
        return [0] * 24
    grid = np.arange(warmup, duration, step)
    hod = (grid / 60 % 24).astype(int)
    counts = np.array([int(((starts <= t) & (ends > t)).sum()) for t in grid])
    # whole numbers throughout - people and patients are counted, not fractional
    return [int(round(float(counts[hod == h].mean()))) if (hod == h).any() else 0 for h in range(24)]


def control_tower(result: dict, pathway: Pathway) -> dict:
    """The flow map plus the time-of-day detail a control tower needs."""
    data = flow_model_data(result, pathway)
    events, patients = result["events"], result["patients"]
    w, dur = pathway.warmup, pathway.sim_duration

    # department census by hour of day (patients physically in the ED)
    census = [0.0] * 24
    if not patients.empty:
        census = _occ_by_hour(patients["arrival"].to_numpy(), patients["exit"].to_numpy(), w, dur)

    # per-area occupancy by hour, and the hour each area is busiest
    label_to_id = {n.get("label", i): i for i, n in pathway.nodes.items()}
    by_hour = {}
    if not events.empty:
        for n in data["nodes"]:
            nid = label_to_id.get(n["label"])
            sub = events[events["stage"] == nid] if nid else events.iloc[0:0]
            if len(sub):
                by_hour[n["label"]] = _occ_by_hour(sub["service_start"].to_numpy(),
                                                   sub["service_end"].to_numpy(), w, dur)

    # Operational bottleneck: the busiest pinch-point across the WORKING DAY
    # (08:00-22:00, when ops teams act), not an overnight low-volume artefact.
    peak_hours, op_bottleneck = [], data.get("bottleneck")
    id_to_label = {nid: n.get("label", nid) for nid, n in pathway.nodes.items()}
    pinch_by_hour = [None] * 24
    if not events.empty:
        ev = events.copy()
        ev["hod"] = (ev["service_start"] / 60 % 24).astype(int)
        day = ev[(ev["hod"] >= 8) & (ev["hod"] < 22)]
        lost = day.groupby("stage")["wait"].sum()
        if len(lost) and lost.max() > 0:
            sid = lost.idxmax()
            op_bottleneck = id_to_label.get(sid, op_bottleneck)
            for n in data["nodes"]:
                n["is_bottleneck"] = (n["label"] == op_bottleneck)
            bs = day[day["stage"] == sid]
            lh = bs.groupby("hod")["wait"].sum()
            peak_hours = sorted(int(h) for h in lh[lh >= lh.max() * 0.6].index)
        # pinch moves through the day: the stage losing the most patient-wait
        # at each hour (so the time slider can retarget the PINCH flag).
        for h in range(24):
            sub = ev[ev["hod"] == h]
            if sub.empty:
                continue
            lh = sub.groupby("stage")["wait"].sum()
            if len(lh) and lh.max() > 0:
                pinch_by_hour[h] = id_to_label.get(lh.idxmax())

    # what serves each area (spaces + staff) so the drill-down can explain WHO
    # and WHAT a patient is waiting for there, and who is on at a given hour
    from ..workforce.roles import STAFF_RESOURCES, ROLES, AREA_LABEL, roles_for
    area_resources, resource_meta = {}, {}
    for nid, node in pathway.nodes.items():
        res = list(node.get("resources") or ([node["resource"]] if node.get("resource") else []))
        res += list(node.get("acquire") or [])
        if res:
            area_resources[node.get("label", nid)] = res
        for r in res:
            if r not in resource_meta:
                resource_meta[r] = {
                    "staff": r in STAFF_RESOURCES,
                    "label": AREA_LABEL.get(r, r.replace("_", " ")),
                    "roles": [ROLES[k]["label"] for k in roles_for(r)],
                    "capacity": pathway.resources.get(r),   # int, or 24-hour roster list
                }

    # hourly arrivals and departures (outcome sinks never appear as event stages,
    # so area_by_hour alone leaves their numbers stuck on the weekly total).
    arrivals_by_hour = [0] * 24
    exits_by_hour: dict[str, list[int]] = {}
    if not patients.empty:
        arrivals_by_hour = _hourly_counts(patients["arrival"].to_numpy(), w, dur)
        for disp, sub in patients.groupby("disposition"):
            exits_by_hour[str(disp)] = _hourly_counts(sub["exit"].to_numpy(), w, dur)

    data["bottleneck"] = op_bottleneck
    data["census_by_hour"] = census
    data["area_by_hour"] = by_hour
    data["arrivals_by_hour"] = arrivals_by_hour
    data["exits_by_hour"] = exits_by_hour
    data["bottleneck_peak_hours"] = peak_hours
    data["pinch_by_hour"] = pinch_by_hour
    data["area_resources"] = area_resources
    data["resource_meta"] = resource_meta
    return data
