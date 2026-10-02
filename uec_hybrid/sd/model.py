"""
The UEC System Dynamics model: the whole-system stocks the ED is embedded in.

Design note on the inpatient-bed stock
--------------------------------------
A hospital sits ~90% full from *all* sources (elective, other specialties); ED
admissions are a marginal inflow on top. Modelling only ED admissions would drain
the stock to empty. So each bedded stock carries a **background inflow** and a
**homeostatic discharge** (discharge rate proportional to how full it is, scaled by
an "active pull" boost from community headroom). Equilibrium therefore sits near a
baseline occupancy; an ED admission surge pushes occupancy up (exit-block feedback
strengthens), while extra beds, faster discharge or community pull push it down.

Each simulated hour the co-simulator calls ``step(dt, flows, ed_census)``.
"""
from __future__ import annotations

from .stocks import Stock
from . import feedback as fb


class _BedStock:
    """A homeostatic bedded stock (acute or MH).

    ``initial_occupied`` (optional) starts the stock with that many occupied
    beds instead of ``baseline x beds``. A scenario that OPENS NEW beds sets it
    to the occupied count of the original hospital, so the new beds start empty
    rather than being born at the same occupancy fraction as the old ones."""

    def __init__(self, name, beds, baseline, background_per_hour, discharge_cap_per_hour,
                 initial_occupied=None):
        level = baseline * beds if initial_occupied is None else min(beds, float(initial_occupied))
        self.stock = Stock(name, level=level, capacity=beds)
        self.baseline = baseline
        self.background = background_per_hour / 60.0          # per minute
        self.discharge_cap = discharge_cap_per_hour / 60.0    # per minute, at baseline

    def integrate(self, ed_inflow_per_min, dt, substeps, pull_boost):
        sub = dt / substeps
        for _ in range(substeps):
            occ = self.stock.occupancy
            # proportional discharge: = capacity at baseline occupancy, slowing
            # below it and (mildly) faster above it; accelerated by community pull
            discharge = self.discharge_cap * (occ / self.baseline) * pull_boost
            net = ed_inflow_per_min + self.background - discharge
            self.stock.integrate(net, sub)

    @property
    def occupancy(self):
        return self.stock.occupancy


class SDModel:
    def __init__(self, cfg: dict, feedback: bool = True,
                 substeps: int = 8, smoothing_tau: float = 90.0):
        self.cfg = cfg
        self.substeps = max(1, int(substeps))
        self.tau = float(smoothing_tau)
        self.feedback_on = feedback

        self.inpatient = _BedStock(
            "inpatient_beds", cfg.get("inpatient_beds", 320),
            cfg.get("baseline_bed_occupancy", 0.92),
            cfg.get("background_admissions_per_hour", 3.2),
            cfg.get("ward_discharge_capacity_per_hour", 6.4),
            cfg.get("initial_occupied_beds"))
        self.mh = _BedStock(
            "mh_beds", cfg.get("mh_beds", 22),
            cfg.get("baseline_mh_occupancy", 0.90),
            cfg.get("mh_background_per_hour", 0.25),
            cfg.get("mh_discharge_capacity_per_hour", 0.62))
        self.community = Stock("community", level=cfg.get("community_capacity", 60) * 0.3,
                               capacity=cfg.get("community_capacity", 60))
        self.community_clear = float(cfg.get("community_clearance_per_hour", 4.0)) / 60.0
        self.comfort = cfg.get("ed_comfort_census", 45)
        self.crush = cfg.get("ed_crush_census", 110)
        self.signals = self._signals(0.0)

    def _signals(self, crowding):
        bwm = fb.bed_wait_multiplier(self.inpatient.occupancy)
        mwm = fb.bed_wait_multiplier(self.mh.occupancy, max_extra=10)
        if not self.feedback_on:
            bwm, mwm = 1.0, 1.0
        pull = fb.community_pull(self.community.level, self.community.capacity) if self.feedback_on else 0.0
        return {
            "bed_wait_multiplier": bwm,
            "mh_bed_wait_multiplier": mwm,
            "community_pull": pull,
            "handover_delay": fb.handover_delay(crowding),
            "crowding": crowding,
            "bed_occupancy": self.inpatient.occupancy,
            "mh_occupancy": self.mh.occupancy,
            "community_used": self.community.level,
        }

    def step(self, dt: float, flows: dict, ed_census: int) -> dict:
        adm_in = flows.get("admissions", 0.0) / dt          # per minute over the tick
        mh_in = flows.get("mh_admissions", 0.0) / dt
        com_in = flows.get("diversions_to_community", 0.0) / dt
        # active pull: community headroom lets the ward discharge modestly faster.
        # Gated off in the no-feedback counterfactual so the baseline is clean.
        pull_boost = 1.0
        if self.feedback_on:
            pull_boost += 0.25 * fb.community_pull(self.community.level,
                                                   self.community.capacity, 1.0)

        self.inpatient.integrate(adm_in, dt, self.substeps, pull_boost)
        self.mh.integrate(mh_in, dt, self.substeps, 1.0)
        sub = dt / self.substeps
        for _ in range(self.substeps):
            clear = self.community_clear * min(1.0, self.community.level
                                               / max(1e-6, self.community_clear * 60))
            self.community.integrate(com_in - clear, sub)

        crowding = fb.crowding_index(ed_census, self.comfort, self.crush)
        targets = self._signals(crowding)
        # first-order smoothing on the feedback signals (anti-oscillation)
        for k, tgt in targets.items():
            tau = self.tau if k in ("bed_wait_multiplier", "mh_bed_wait_multiplier",
                                    "handover_delay") else 0.0
            self.signals[k] = fb.smooth(self.signals[k], tgt, dt, tau)
        return dict(self.signals)
