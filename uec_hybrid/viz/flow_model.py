"""
The flow-model "Figure 1" data builder: the whole UEC pathway as one connected
map. DES stage nodes are laid out left-to-right by acuity x time **band**, sized by
patient volume and traffic-light coloured by queue wait; the System Dynamics stocks
(inpatient beds, MH beds, community) are attached as reservoirs with the feedback
arrow back into the ED. Rendered client-side as animated SVG.
"""
from __future__ import annotations

from ..des.pathway import Pathway, BANDS
from ..analysis.metrics import (flow_counts, stage_waits, resource_utilisation, diagnose)

BAND_LABEL = {
    "front_door": "Front door (15 min)",
    "core_0_4h": "Core ED (0–4h)",
    "emergency_4_12h": "Emergency / specialist (4–12h)",
    "admission_12h_plus": "Admission (>12h)",
}


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
                "x": (col + 1) / (max_col + 2),
                "y": 0.5 if k == 1 else 0.06 + 0.88 * (i / (k - 1)),
                "volume": inflow[n], "mean_wait": round(w, 1),
                "utilisation": round(u, 1), "kind": kind(n), "status": status,
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
