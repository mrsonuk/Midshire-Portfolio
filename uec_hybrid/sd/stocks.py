"""
Stock-and-flow primitives for the System Dynamics layer.

A ``Stock`` is a level that accumulates inflows minus outflows. Integration is
done by the ``SDModel`` (see model.py) with fixed sub-steps; a Stock just holds
its level and clamps to [0, capacity].
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Stock:
    name: str
    level: float
    capacity: float = float("inf")

    def integrate(self, net_rate_per_min: float, dt: float) -> None:
        self.level = min(self.capacity, max(0.0, self.level + net_rate_per_min * dt))

    @property
    def occupancy(self) -> float:
        if self.capacity in (0, float("inf")):
            return 0.0
        return self.level / self.capacity
