"""
Care-pathway model: a pathway is pure data (a directed graph of nodes), so the
same engine drives any NHS UEC configuration with no code change.

Node fields
-----------
Core:
    id, type (source|process|sink), label
    resource | resources (transient holds for a stage's service)
    acquire | release       (span-held resources, e.g. a cubicle held across stages)
    service | service_by_class
    routes | routes_by_class | routes_by_attribute | routes_by_signal
    stops_clock             (freeze the performance clock at transfer)

Model ED additions (see NHS England "The Model Emergency Department", Feb 2026):
    band            front_door | core_0_4h | emergency_4_12h | admission_12h_plus
    acuity_levels   acuity classes that legitimately enter this node (validation)
    bedded_care     bool; validator asserts False for UTC/RAT/ambulatory/minors
    max_band_minutes  hard cap, e.g. EEMAC = 720 (12h); patient must exit by then
    priority        lower value = higher clinical priority (sickest first)
    disposition_intent  e.g. EEMAC -> "expected_discharge" (not admission boarding)

Coupling hooks (resolved live from the SystemState each time a patient enters):
    service_signal  name of an SD signal that scales this node's service time
    routes_by_signal  {signal_name: {"target": id, "high": p_hi, "low": p_lo}}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

BANDS = ["front_door", "core_0_4h", "emergency_4_12h", "admission_12h_plus"]


@dataclass
class Pathway:
    name: str
    raw: dict
    nodes: dict[str, dict]
    resources: dict[str, int]
    arrivals: dict
    sim_duration: float            # minutes
    warmup: float                  # minutes excluded from metrics
    target_minutes: float = 240.0  # NHS 4-hour standard
    uec: dict = field(default_factory=dict)
    sd: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Pathway":
        nodes = {n["id"]: n for n in data["nodes"]}
        return cls(
            name=data.get("name", "Unnamed pathway"),
            raw=data,
            nodes=nodes,
            resources=dict(data.get("resources", {})),
            arrivals=data.get("arrivals", {}),
            sim_duration=float(data.get("sim_duration_minutes", 7 * 24 * 60)),
            warmup=float(data.get("warmup_minutes", 0)),
            target_minutes=float(data.get("target_minutes", 240.0)),
            uec=data.get("uec", {}),
            sd=data.get("sd", {}),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Pathway":
        with open(path) as fh:
            return cls.from_dict(json.load(fh))

    def source_node(self) -> dict:
        for node in self.nodes.values():
            if node.get("type") == "source":
                return node
        raise ValueError("Pathway has no source node")

    def node_resources(self, node: dict) -> list[str]:
        """All resources a node touches (span-acquired + transient)."""
        res = list(node.get("acquire", []) or [])
        res += node.get("resources") or ([node["resource"]] if node.get("resource") else [])
        return [r for r in res if r in self.resources]

    def copy(self) -> "Pathway":
        return Pathway.from_dict(json.loads(json.dumps(self.raw)))


def validate_schema(pathway: Pathway) -> list[str]:
    """Static structural checks; returns a list of problems (empty = valid)."""
    problems = []
    ids = set(pathway.nodes)
    sources = [n for n in pathway.nodes.values() if n.get("type") == "source"]
    sinks = [n for n in pathway.nodes.values() if n.get("type") == "sink"]
    if len(sources) != 1:
        problems.append(f"expected exactly 1 source node, found {len(sources)}")
    if not sinks:
        problems.append("pathway has no sink nodes")

    for nid, node in pathway.nodes.items():
        if node.get("band") and node["band"] not in BANDS:
            problems.append(f"{nid}: unknown band {node['band']!r}")
        for key in ("routes",):
            for r in node.get(key, []) or []:
                if r[0] not in ids:
                    problems.append(f"{nid}: route target {r[0]!r} does not exist")
        for routes in (node.get("routes_by_class") or {}).values():
            for r in routes:
                if r[0] not in ids:
                    problems.append(f"{nid}: class route target {r[0]!r} does not exist")
        for routes in (node.get("routes_by_attribute") or {}).values():
            for r in routes:
                if r[0] not in ids:
                    problems.append(f"{nid}: attribute route target {r[0]!r} does not exist")
        for r in pathway.node_resources(node):
            if r not in pathway.resources:
                problems.append(f"{nid}: uses undefined resource {r!r}")
    return problems
