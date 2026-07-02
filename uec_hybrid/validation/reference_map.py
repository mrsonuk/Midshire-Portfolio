"""
The intended Model ED process map, derived from the pathway definition itself.

The pathway's routes ARE the ground-truth directed graph. This module extracts the
set of legal stage->stage transitions, the band index of each stage, and the bedded-
care flags, so the conformance checker can prove the simulated event order
reproduces the intended pathway (the brief's "process mapping used to validate the
simulated pathway").
"""
from __future__ import annotations

from ..des.pathway import Pathway, BANDS


def _targets(node: dict) -> set[str]:
    out = set()
    for r in node.get("routes", []) or []:
        out.add(r[0])
    for routes in (node.get("routes_by_class") or {}).values():
        for r in routes:
            out.add(r[0])
    for routes in (node.get("routes_by_attribute") or {}).values():
        for r in routes:
            out.add(r[0])
    for div in node.get("routes_by_signal", []) or []:
        out.add(div["target"])
    return out


def reference_map(pathway: Pathway) -> dict:
    legal = set()                 # (from_id, to_id)
    band_index = {}
    bedded = {}
    labels = {}
    for nid, node in pathway.nodes.items():
        labels[nid] = node.get("label", nid)
        if node.get("band"):
            band_index[nid] = BANDS.index(node["band"])
        bedded[nid] = node.get("bedded_care")
        for t in _targets(node):
            legal.add((nid, t))
    # part-time areas: when closed, a router that targets the area's entry node
    # diverts straight to its fallback, so that transition is legal too.
    closed_fb = {nid: node["closed_fallback"] for nid, node in pathway.nodes.items()
                 if node.get("open_hours") and node.get("closed_fallback")}
    for (a, b) in list(legal):
        if b in closed_fb:
            legal.add((a, closed_fb[b]))
    # reneging: a patient who gives up at a node exits from its PREDECESSOR's
    # event chain straight to the renege sink, so that hop is legal too.
    renege_to = {nid: node["renege"]["to"] for nid, node in pathway.nodes.items()
                 if node.get("renege")}
    for (a, b) in list(legal):
        if b in renege_to:
            legal.add((a, renege_to[b]))
    sinks = {nid: node.get("label", nid) for nid, node in pathway.nodes.items()
             if node.get("type") == "sink"}
    return {"legal": legal, "band_index": band_index, "bedded": bedded,
            "labels": labels, "sinks": sinks,
            "eemac_cap": {nid: node["max_band_minutes"] for nid, node in pathway.nodes.items()
                          if node.get("max_band_minutes")}}
