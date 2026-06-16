"""
Generalised, config-driven Discrete Event Simulation engine for NHS pathways.

Unlike the original beta tool (which hard-coded a single Emergency Department
layout into ~2,000 lines of SimPy), this engine treats *any* care pathway as a
directed graph of nodes. A pathway is pure data (see ``pathways/*.json``), so the
same engine simulates an Emergency Department, a Surgical Assessment Unit, an
outpatient clinic, or any bespoke NHS hospital flow without code changes.

Node types
----------
* ``source``  - generates patient arrivals (hourly profile or fixed rate).
* ``process`` - optionally seizes a shared resource, holds the patient for a
                sampled service time, then routes onward.
* ``sink``    - patient leaves the system with a disposition label
                (e.g. "Admitted", "Discharged").

The engine records a tidy event log (one row per patient/stage) plus arrival and
exit rows. Everything downstream (metrics, Monte-Carlo, scenarios, charts) is
computed from that single tidy structure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import simpy


# --------------------------------------------------------------------------- #
# Probability distributions
# --------------------------------------------------------------------------- #
def sample_time(rng: np.random.Generator, spec: Any) -> float:
    """Sample a non-negative service time from a distribution spec.

    ``spec`` may be a number (constant) or a dict such as::

        {"dist": "lognormal", "mean": 65, "stdev": 20}
        {"dist": "exponential", "mean": 12}
        {"dist": "triangular", "low": 5, "mode": 10, "high": 30}
        {"dist": "uniform", "low": 5, "high": 15}
        {"dist": "normal", "mean": 30, "stdev": 10}
        {"dist": "constant", "value": 2}
    """
    if spec is None:
        return 0.0
    if isinstance(spec, (int, float)):
        return float(max(0.0, spec))

    dist = str(spec.get("dist", "constant")).lower()

    if dist == "constant":
        value = spec.get("value", spec.get("mean", 0.0))
        return float(max(0.0, value))
    if dist == "exponential":
        return float(rng.exponential(spec.get("mean", 1.0)))
    if dist == "normal":
        return float(max(0.0, rng.normal(spec.get("mean", 0.0), spec.get("stdev", 0.0))))
    if dist == "uniform":
        return float(rng.uniform(spec.get("low", 0.0), spec.get("high", 1.0)))
    if dist == "triangular":
        return float(rng.triangular(spec["low"], spec["mode"], spec["high"]))
    if dist == "lognormal":
        # Parameterise by the desired mean/stdev of the resulting distribution.
        mean = float(spec.get("mean", 1.0))
        stdev = float(spec.get("stdev", 0.0))
        if mean <= 0:
            return 0.0
        if stdev <= 0:
            return mean
        phi = np.sqrt(stdev ** 2 + mean ** 2)
        mu = np.log(mean ** 2 / phi)
        sigma = np.sqrt(np.log(phi ** 2 / mean ** 2))
        return float(rng.lognormal(mu, sigma))
    raise ValueError(f"Unknown distribution: {dist!r}")


# --------------------------------------------------------------------------- #
# Pathway model
# --------------------------------------------------------------------------- #
@dataclass
class Pathway:
    """A data-driven description of an NHS care pathway."""

    name: str
    raw: dict
    sim_duration: float          # minutes
    warmup: float                # minutes excluded from metrics
    nodes: dict[str, dict]
    resources: dict[str, int]
    arrivals: dict
    target_minutes: float = 240.0  # NHS 4-hour standard by default

    @classmethod
    def from_dict(cls, data: dict) -> "Pathway":
        nodes = {n["id"]: n for n in data["nodes"]}
        return cls(
            name=data.get("name", "Unnamed pathway"),
            raw=data,
            sim_duration=float(data.get("sim_duration_minutes", 7 * 24 * 60)),
            warmup=float(data.get("warmup_minutes", 0)),
            nodes=nodes,
            resources=dict(data.get("resources", {})),
            arrivals=data.get("arrivals", {}),
            target_minutes=float(data.get("target_minutes", 240.0)),
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

    def copy(self) -> "Pathway":
        return Pathway.from_dict(json.loads(json.dumps(self.raw)))


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
@dataclass
class Simulation:
    pathway: Pathway
    seed: int = 0
    event_log: list = field(default_factory=list)
    patient_log: list = field(default_factory=list)
    holds: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.env = simpy.Environment()
        self.resources = {
            name: simpy.Resource(self.env, capacity=int(cap))
            for name, cap in self.pathway.resources.items()
        }
        self._pid = 0

    # -- arrivals ---------------------------------------------------------- #
    def _acuity_for(self) -> str:
        mix = self.pathway.arrivals.get("acuity_mix")
        if not mix:
            return "default"
        labels = list(mix.keys())
        weights = np.array([mix[k] for k in labels], dtype=float)
        weights = weights / weights.sum()
        return str(self.rng.choice(labels, p=weights))

    def _attributes_for(self, acuity: str) -> set:
        """Independent patient flags (e.g. ambulance, paediatric, mental_health)
        drawn from ``arrivals.attributes`` prevalences. A prevalence may be a flat
        probability or a per-class dict, letting a cohort correlate with acuity
        (e.g. children skewing to lower-acuity presentations)."""
        attrs = set()
        for name, prob in (self.pathway.arrivals.get("attributes") or {}).items():
            p = float(prob.get(acuity, 0.0)) if isinstance(prob, dict) else float(prob)
            if self.rng.random() < p:
                attrs.add(name)
        return attrs

    def _arrival_generator(self):
        """Generate arrivals following an hourly profile (patients/hour) or a
        constant Poisson rate."""
        arrivals = self.pathway.arrivals
        profile = arrivals.get("hourly_profile")
        source = self.pathway.source_node()

        while True:
            hour = int((self.env.now / 60) % 24)
            if profile:
                rate_per_hour = max(1e-6, float(profile[hour]))
            else:
                rate_per_hour = max(1e-6, float(arrivals.get("rate_per_hour", 10)))
            # exponential inter-arrival time (minutes) for a Poisson process
            inter = self.rng.exponential(60.0 / rate_per_hour)
            yield self.env.timeout(inter)
            self._pid += 1
            acuity = self._acuity_for()
            self.env.process(self._patient(self._pid, acuity, source,
                                           self._attributes_for(acuity)))

    # -- patient journey --------------------------------------------------- #
    def _service_spec(self, node: dict, acuity: str):
        by_class = node.get("service_by_class")
        if by_class and acuity in by_class:
            return by_class[acuity]
        return node.get("service")

    def _route(self, node: dict, acuity: str, attrs: set) -> str | None:
        # Attribute-specific routing wins (e.g. mental-health patients diverting
        # to an MH branch), then class-specific, then the default "routes" list.
        routes = None
        by_attr = node.get("routes_by_attribute")
        if by_attr:
            for name, r in by_attr.items():
                if name in attrs:
                    routes = r
                    break
        if routes is None:
            by_class = node.get("routes_by_class")
            if by_class and acuity in by_class:
                routes = by_class[acuity]
            else:
                routes = node.get("routes")
        if not routes:
            return None
        targets = [r[0] for r in routes]
        probs = np.array([r[1] for r in routes], dtype=float)
        probs = probs / probs.sum()
        return str(self.rng.choice(targets, p=probs))

    def _patient(self, pid: int, acuity: str, source: dict, attrs: set):
        arrival = self.env.now
        node_id = self._route(source, acuity, attrs)
        # Resources held across several nodes (e.g. a bed occupied for the whole
        # stay) live here until a node releases them: {resource: (request, start)}.
        held: dict[str, tuple] = {}
        # The patient's performance clock (e.g. NHS 4-hour standard) can be frozen
        # at a transfer point even though the process keeps modelling bed turnover.
        clock_stop = None

        while node_id is not None:
            node = self.pathway.nodes[node_id]

            if node.get("type") == "sink":
                for res, (req, start) in held.items():
                    self.resources[res].release(req)
                    self._hold(pid, res, start, self.env.now)
                stop = clock_stop if clock_stop is not None else self.env.now
                row = {
                    "pid": pid,
                    "acuity": acuity,
                    "arrival": arrival,
                    "exit": stop,
                    "los": stop - arrival,
                    "disposition": node.get("label", node_id),
                }
                for name in (self.pathway.arrivals.get("attributes") or {}):
                    row[f"attr_{name}"] = name in attrs
                self.patient_log.append(row)
                return

            node_entry = self.env.now

            # Span-acquire: seize resources now and keep them until a later node
            # releases them (a bed is held across assessment, imaging and decision).
            # The hold is recorded from the moment it is *granted*, so queue time
            # for the bed counts as a wait, not as occupancy.
            for res in [r for r in node.get("acquire", []) if r in self.resources]:
                if res not in held:
                    req = self.resources[res].request()
                    yield req
                    held[res] = (req, self.env.now)

            # A node may also transiently seize a single resource ("resource") or
            # several ("resources", all held for that node's service only). This
            # lets a clinical area contend for both a space and a clinician at once
            # - the contention that resource-planning hinges on.
            needed = node.get("resources")
            if not needed:
                single = node.get("resource")
                needed = [single] if single else []
            needed = [r for r in needed if r in self.resources and r not in held]

            requests = [self.resources[r].request() for r in needed]
            for req in requests:
                yield req
            # Total wait at this node = time spent queueing for the bed plus time
            # queueing for the clinician.
            wait = self.env.now - node_entry
            service_start = self.env.now
            service = sample_time(self.rng, self._service_spec(node, acuity))
            yield self.env.timeout(service)
            for r, req in zip(needed, requests):
                self.resources[r].release(req)
                self._hold(pid, r, service_start, self.env.now)
            self._record(pid, acuity, node, node_entry, service_start,
                         self.env.now, wait, service, needed)

            # Span-release: free resources this node was holding open.
            for res in [r for r in node.get("release", []) if r in held]:
                req, start = held.pop(res)
                self.resources[res].release(req)
                self._hold(pid, res, start, self.env.now)

            if node.get("stops_clock") and clock_stop is None:
                clock_stop = self.env.now

            node_id = self._route(node, acuity, attrs)

    def _hold(self, pid, resource, start, end) -> None:
        if end > start:
            self.holds.append({"pid": pid, "resource": resource,
                               "start": start, "end": end})

    def _record(self, pid, acuity, node, queue_entry, service_start,
                service_end, wait, service, resources) -> None:
        self.event_log.append({
            "pid": pid,
            "acuity": acuity,
            "stage": node["id"],
            "stage_label": node.get("label", node["id"]),
            "resource": "+".join(resources) if resources else None,
            "resources": resources,
            "queue_entry": queue_entry,
            "service_start": service_start,
            "service_end": service_end,
            "wait": wait,
            "service": service,
        })

    # -- run --------------------------------------------------------------- #
    def run(self) -> dict[str, pd.DataFrame]:
        self.env.process(self._arrival_generator())
        self.env.run(until=self.pathway.sim_duration)
        events = pd.DataFrame(self.event_log)
        patients = pd.DataFrame(self.patient_log)
        holds = pd.DataFrame(self.holds)
        # Drop warm-up period (judged on arrival time) so metrics reflect
        # steady-state behaviour.
        if self.pathway.warmup > 0 and not patients.empty:
            keep = patients["arrival"] >= self.pathway.warmup
            kept_pids = set(patients.loc[keep, "pid"])
            patients = patients[keep].reset_index(drop=True)
            if not events.empty:
                events = events[events["pid"].isin(kept_pids)].reset_index(drop=True)
            if not holds.empty:
                holds = holds[holds["pid"].isin(kept_pids)].reset_index(drop=True)
        return {"events": events, "patients": patients, "holds": holds}


def run_pathway(pathway: Pathway, seed: int = 0) -> dict[str, pd.DataFrame]:
    """Convenience one-shot runner."""
    return Simulation(pathway=pathway, seed=seed).run()
