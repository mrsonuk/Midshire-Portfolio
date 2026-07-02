"""
CoSimulator - the master clock binding the DES and SD solvers.

It owns one SimPy environment (inside the DES ``Simulation``), one ``SDModel`` and
the shared ``SystemState``. A recurring SimPy process fires every ``dt`` simulated
minutes and performs the zero-order-hold exchange:

    1. DES -> SD : drain the flow accumulators since the last tick.
    2. advance SD by dt (sub-stepped).
    3. SD -> DES : publish the new held signals into SystemState.

Between ticks the DES runs freely, reading the held signals; the two solvers never
mutate one another mid-interval, which is what keeps the loop stable.
"""
from __future__ import annotations

from ..des.engine import Simulation
from ..des.pathway import Pathway
from ..sd.model import SDModel
from .system_state import SystemState


class CoSimulator:
    def __init__(self, pathway: Pathway, seed: int = 0, dt: float = 60.0,
                 feedback: bool = True, sd_overrides: dict | None = None):
        self.pathway = pathway
        self.dt = float(dt)
        self.state = SystemState()
        cfg = dict(pathway.sd or {})
        cfg.setdefault("ed_comfort_census", 45)
        cfg.setdefault("ed_crush_census", 110)
        if sd_overrides:
            cfg.update(sd_overrides)
        self.sd = SDModel(cfg, feedback=feedback)
        self.sim = Simulation(pathway=pathway, seed=seed, state=self.state)
        # seed the held signals so the very first hour already sees the SD state
        self.state.publish(0.0, dict(self.sd.signals))

    def _tick(self, env, state):
        while True:
            yield env.timeout(self.dt)
            flows = state.drain()
            signals = self.sd.step(self.dt, flows, state.ed_census)
            state.publish(env.now, signals)

    def run(self) -> dict:
        result = self.sim.run(processes=[self._tick])
        result["sd_model"] = self.sd
        return result


def run_cosim(pathway: Pathway, seed: int = 0, feedback: bool = True,
              sd_overrides: dict | None = None) -> dict:
    return CoSimulator(pathway, seed=seed, feedback=feedback,
                       sd_overrides=sd_overrides).run()
