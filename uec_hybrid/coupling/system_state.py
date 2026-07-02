"""
SystemState - the single shared object across the SD<->DES seam.

Two halves with deliberately opposite update disciplines:

* **Held signals (SD -> DES):** piecewise-constant. The co-simulator overwrites
  them once per tick; the DES only ever *reads* them, and they are held constant
  between ticks (zero-order hold). This is what keeps the coupled loop well-posed
  and non-oscillatory - the two solvers never mutate each other mid-interval.

* **Accumulators (DES -> SD):** monotone counters and a live census the DES writes
  to as events happen; the co-simulator *drains* them at each tick to form the SD
  inflow rates for the next interval.

Everything runs inside one cooperative SimPy environment (single-threaded), so no
locking is required; the discipline above - not locks - is what guarantees
correctness.

Signals default to neutral values, so a pathway runs as a pure DES (no SD attached)
unchanged.
"""
from __future__ import annotations

NEUTRAL = {
    "bed_availability": 1.0,      # 1.0 = beds freely available; ->0 = full exit-block
    "mh_bed_availability": 1.0,
    "community_pull": 0.0,        # 0 = no extra community discharge; ->1 = strong pull
    "handover_delay": 0.0,        # additional ambulance handover minutes
    "crowding": 0.0,              # 0..1 ED crowding index (for reporting)
}


class SystemState:
    def __init__(self):
        self.signals = dict(NEUTRAL)
        self._acc = {
            "admissions": 0.0,
            "mh_admissions": 0.0,
            "diversions_to_community": 0.0,
            "discharges": 0.0,
        }
        self.ed_census = 0          # live count of patients currently inside the ED
        self.history = []           # (time, signals snapshot) for charts

    # -- SD -> DES (held) --------------------------------------------------- #
    def get(self, name: str, default: float = 0.0) -> float:
        return self.signals.get(name, NEUTRAL.get(name, default))

    def publish(self, time: float, signals: dict) -> None:
        self.signals.update(signals)
        self.history.append((time, dict(self.signals)))

    # -- DES -> SD (accumulate, then drain at tick) ------------------------- #
    def record(self, channel: str, amount: float = 1.0) -> None:
        if channel in self._acc:
            self._acc[channel] += amount

    def enter_ed(self) -> None:
        self.ed_census += 1

    def leave_ed(self) -> None:
        self.ed_census = max(0, self.ed_census - 1)

    def drain(self) -> dict:
        """Return accumulated flows since the last drain and reset them."""
        flows = dict(self._acc)
        for k in self._acc:
            self._acc[k] = 0.0
        return flows
