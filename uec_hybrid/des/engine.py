"""
Discrete-event simulation engine for NHS UEC pathways (clean-room).

Patients flow through a data-defined graph of nodes, contending for limited
resources. Distinctive features required by the Model ED:

* **Acuity prioritisation** - every resource is a SimPy ``PriorityResource`` whose
  queue is ordered by clinical priority (sickest first), so a higher-acuity patient
  jumps the queue for a cubicle/clinician. This is the "prioritisation of clinical
  care based on urgency" the brief calls for.
* **Span-held spaces** - a node may ``acquire`` a space (cubicle, bed) and hold it
  across several downstream nodes until a later node ``release``s it, while
  clinicians are seized transiently per stage. So a space and a clinician are
  contended simultaneously.
* **Dynamic, SD-coupled parameters** - a node's service time and routing can be
  scaled live by signals read from the shared ``SystemState`` at the moment the
  patient enters the node (never baked at construction). This is the seam through
  which downstream bed occupancy slows admissions (exit-block) etc.
* **Band/time enforcement** - ``max_band_minutes`` caps time in a band (e.g. EEMAC
  12h), and band-crossing timestamps are recorded for the 4h/12h standards.

Outputs are three tidy logs: events (one row per patient/stage), patients (one row
per completed journey) and holds (one row per resource occupancy interval).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import simpy

from . import distributions as dist
from .pathway import Pathway
from ..coupling.system_state import SystemState


def _priority_of(acuity: str, node: dict) -> int:
    """Lower = higher clinical priority (served first). Derived from the acuity
    label's trailing digit, overridable per node."""
    if "priority" in node:
        return int(node["priority"])
    for tok in str(acuity).replace("-", " ").split():
        if tok.isdigit():
            return int(tok)
    return 5


@dataclass
class Simulation:
    pathway: Pathway
    seed: int = 0
    state: SystemState = None
    event_log: list = field(default_factory=list)
    patient_log: list = field(default_factory=list)
    holds: list = field(default_factory=list)

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)
        self.env = simpy.Environment()
        if self.state is None:
            self.state = SystemState()
        # A capacity may be a fixed integer OR a 24-length by-hour roster (staffing
        # that varies through the day). For a roster we build the resource at its
        # peak and a shift-manager parks the off-shift units each hour.
        self.resources = {}
        self.rosters = {}
        for name, cap in self.pathway.resources.items():
            if isinstance(cap, (list, tuple)):
                roster = [int(round(c)) for c in cap]
                peak = max(1, max(roster))
                self.rosters[name] = roster
                self.resources[name] = simpy.PriorityResource(self.env, capacity=peak)
            else:
                self.resources[name] = simpy.PriorityResource(self.env, capacity=int(cap))
        self._pid = 0

    def _shift_manager(self, name, roster):
        """Hold (peak - roster[hour]) units off-shift each hour via top-priority
        dummy requests, so the available units track the staffing rota."""
        res = self.resources[name]
        peak = res.capacity
        held = []
        while True:
            hour = int((self.env.now / 60) % 24)
            target = peak - max(0, min(peak, roster[hour]))   # units to park off-shift
            while len(held) < target:
                req = res.request(priority=-10 ** 9)          # always wins a freed unit
                yield req
                held.append(req)
            while len(held) > target:
                res.release(held.pop())
            # re-evaluate every 15 min so staffing reductions take effect as units
            # free, rather than only on the hour
            yield self.env.timeout(15)


    # -- arrivals ---------------------------------------------------------- #
    def _acuity_for(self) -> str:
        mix = self.pathway.arrivals.get("acuity_mix")
        if not mix:
            return "default"
        labels = list(mix)
        w = np.array([mix[k] for k in labels], dtype=float)
        return str(self.rng.choice(labels, p=w / w.sum()))

    def _attributes_for(self, acuity: str) -> set:
        attrs = set()
        for name, prob in (self.pathway.arrivals.get("attributes") or {}).items():
            p = float(prob.get(acuity, 0.0)) if isinstance(prob, dict) else float(prob)
            if self.rng.random() < p:
                attrs.add(name)
        return attrs

    def _arrival_generator(self):
        arrivals = self.pathway.arrivals
        profile = arrivals.get("hourly_profile")
        source = self.pathway.source_node()
        while True:
            hour = int((self.env.now / 60) % 24)
            rate = max(1e-6, float(profile[hour]) if profile
                       else float(arrivals.get("rate_per_hour", 10)))
            yield self.env.timeout(self.rng.exponential(60.0 / rate))
            self._pid += 1
            acuity = self._acuity_for()
            self.env.process(self._patient(self._pid, acuity, source,
                                           self._attributes_for(acuity)))

    # -- routing ----------------------------------------------------------- #
    def _service_spec(self, node, acuity):
        by_class = node.get("service_by_class")
        if by_class and acuity in by_class:
            return by_class[acuity]
        return node.get("service")

    def _resolve_open(self, target):
        """If the chosen target is a part-time area that is closed at the current
        sim hour, divert to its fallback. ``open_hours`` is [open, close] (24h);
        close<open wraps past midnight. No ``open_hours`` ⇒ always open."""
        if target is None:
            return target
        node = self.pathway.nodes.get(target)
        if not node:
            return target
        oh = node.get("open_hours")
        if not oh:
            return target
        o, c = int(oh[0]), int(oh[1])
        hour = int((self.env.now / 60) % 24)
        if o == c:
            is_open = True
        elif o < c:
            is_open = o <= hour < c
        else:                                 # wraps midnight (e.g. 22-06)
            is_open = hour >= o or hour < c
        return target if is_open else node.get("closed_fallback", target)

    def _route(self, node, acuity, attrs):
        # SD-signal diversion takes first refusal (e.g. community pull),
        # then attribute, then class, then default routes.
        for div in node.get("routes_by_signal", []) or []:
            p = self.state.get(div["signal"], 0.0) * float(div.get("scale", 1.0))
            if self.rng.random() < min(1.0, max(0.0, p)):
                return self._resolve_open(div["target"])
        routes = None
        by_attr = node.get("routes_by_attribute")
        if by_attr:
            for name, r in by_attr.items():
                if name in attrs:
                    routes = r
                    break
        if routes is None:
            by_class = node.get("routes_by_class")
            routes = by_class[acuity] if (by_class and acuity in by_class) else node.get("routes")
        if not routes:
            return None
        targets = [r[0] for r in routes]
        probs = np.array([r[1] for r in routes], dtype=float)
        return self._resolve_open(str(self.rng.choice(targets, p=probs / probs.sum())))

    # -- patient journey --------------------------------------------------- #
    def _patient(self, pid, acuity, source, attrs):
        arrival = self.env.now
        prio = _priority_of(acuity, source)
        node_id = self._route(source, acuity, attrs)
        held = {}                 # resource -> (request, start)
        clock_stop = None
        in_ed = False
        bands_seen = set()

        while node_id is not None:
            node = self.pathway.nodes[node_id]

            if node.get("type") == "sink":
                for res, (req, start) in held.items():
                    self.resources[res].release(req)
                    self._hold(pid, res, start, self.env.now)
                if in_ed:
                    self.state.leave_ed()
                stop = clock_stop if clock_stop is not None else self.env.now
                disp = node.get("label", node_id)
                self._record_disposition(disp)
                row = {"pid": pid, "acuity": acuity, "arrival": arrival,
                       "exit": stop, "los": stop - arrival, "disposition": disp,
                       "priority": prio, "bands": ",".join(sorted(bands_seen))}
                for name in (self.pathway.arrivals.get("attributes") or {}):
                    row[f"attr_{name}"] = name in attrs
                self.patient_log.append(row)
                return

            if not in_ed and node.get("band"):
                self.state.enter_ed(); in_ed = True
            if node.get("band"):
                bands_seen.add(node["band"])

            node_entry = self.env.now

            # span-acquire: hold a space until a later node releases it
            for res in [r for r in node.get("acquire", []) if r in self.resources]:
                if res not in held:
                    req = self.resources[res].request(priority=prio)
                    yield req
                    held[res] = (req, self.env.now)

            # transient seize: a space and/or clinician for this stage's service
            needed = node.get("resources") or (
                [node["resource"]] if node.get("resource") else [])
            needed = [r for r in needed if r in self.resources and r not in held]
            reqs = [self.resources[r].request(priority=prio) for r in needed]
            for req in reqs:
                yield req
            wait = self.env.now - node_entry

            service = dist.sample(self.rng, self._service_spec(node, acuity))
            sig = node.get("service_signal")
            if sig:
                service *= max(0.0, self.state.get(sig, 1.0))
            cap = node.get("max_band_minutes")
            if cap is not None:                      # e.g. EEMAC 12h total cap
                service = max(0.0, min(service, cap - (self.env.now - arrival)))
            service_start = self.env.now
            yield self.env.timeout(service)

            for r, req in zip(needed, reqs):
                self.resources[r].release(req)
                self._hold(pid, r, service_start, self.env.now)
            self._record(pid, acuity, node, node_entry, service_start,
                         self.env.now, wait, service, needed)

            for res in [r for r in node.get("release", []) if r in held]:
                req, start = held.pop(res)
                self.resources[res].release(req)
                self._hold(pid, res, start, self.env.now)

            if node.get("stops_clock") and clock_stop is None:
                clock_stop = self.env.now

            node_id = self._route(node, acuity, attrs)

    def _record_disposition(self, disp: str):
        d = disp.lower()
        if "admit" in d and "mh" in d:
            self.state.record("mh_admissions")
        elif "admit" in d:
            self.state.record("admissions")
        elif "communit" in d:
            self.state.record("diversions_to_community")
        else:
            self.state.record("discharges")

    def _record(self, pid, acuity, node, q, ss, se, wait, service, resources):
        self.event_log.append({
            "pid": pid, "acuity": acuity, "stage": node["id"],
            "stage_label": node.get("label", node["id"]),
            "band": node.get("band"), "bedded_care": node.get("bedded_care"),
            "resources": resources, "queue_entry": q, "service_start": ss,
            "service_end": se, "wait": wait, "service": service})

    def _hold(self, pid, resource, start, end):
        if end > start:
            self.holds.append({"pid": pid, "resource": resource,
                               "start": start, "end": end})

    # -- run --------------------------------------------------------------- #
    def run(self, processes=None) -> dict:
        """Run to completion. ``processes`` is an optional list of extra SimPy
        generator functions (e.g. the co-simulation tick) to start alongside."""
        self.env.process(self._arrival_generator())
        for name, roster in self.rosters.items():       # staffing schedules
            self.env.process(self._shift_manager(name, roster))
        for proc in processes or []:
            self.env.process(proc(self.env, self.state))
        self.env.run(until=self.pathway.sim_duration)
        return self._frames()

    def _frames(self) -> dict:
        events = pd.DataFrame(self.event_log)
        patients = pd.DataFrame(self.patient_log)
        holds = pd.DataFrame(self.holds)
        w = self.pathway.warmup
        if w > 0 and not patients.empty:
            keep = set(patients.loc[patients["arrival"] >= w, "pid"])
            patients = patients[patients["arrival"] >= w].reset_index(drop=True)
            if not events.empty:
                events = events[events["pid"].isin(keep)].reset_index(drop=True)
            if not holds.empty:
                holds = holds[holds["pid"].isin(keep)].reset_index(drop=True)
        return {"events": events, "patients": patients, "holds": holds,
                "sd_history": list(self.state.history)}


def run_pathway(pathway: Pathway, seed: int = 0, state: SystemState = None) -> dict:
    return Simulation(pathway=pathway, seed=seed, state=state).run()
