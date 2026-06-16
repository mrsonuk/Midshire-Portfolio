"""
Feedback transfer functions for the System Dynamics layer.

Every function that turns an SD stock level into a signal the DES reads is a
**smooth, bounded, monotone** curve - never a step. Smoothness is what keeps the
coupled SD<->DES loop from oscillating. A first-order smoother (`smooth`) further
damps how fast a signal can move between ticks.
"""
from __future__ import annotations

import math


def logistic(x: float, knee: float, sharpness: float) -> float:
    """Smooth 0->1 step centred on ``knee``."""
    return 1.0 / (1.0 + math.exp(-sharpness * (x - knee)))


def bed_wait_multiplier(occupancy: float, max_extra: float = 8.0,
                        knee: float = 0.90, sharpness: float = 12.0) -> float:
    """Inpatient-bed occupancy -> multiplier on the ED 'wait for a bed' time.

    ~1.0 while there is headroom, climbing steeply as occupancy approaches 100%
    (the exit-block / corridor-care curve). This is the core feedback: the fuller
    the hospital, the longer admitted patients board in the ED."""
    occupancy = min(1.0, max(0.0, occupancy))
    return 1.0 + max_extra * logistic(occupancy, knee, sharpness)


def community_pull(used: float, capacity: float, strength: float = 0.45) -> float:
    """Available community/virtual-ward capacity -> probability uplift that an
    appropriate patient is pulled to community instead of admitted (active pull)."""
    if capacity <= 0:
        return 0.0
    available = max(0.0, 1.0 - used / capacity)
    return strength * available


def handover_delay(crowding: float, max_delay: float = 60.0) -> float:
    """ED crowding -> additional ambulance handover minutes (which in turn degrade
    Category-2 response as ambulances are held at the hospital)."""
    return max_delay * min(1.0, max(0.0, crowding))


def crowding_index(census: int, comfort: int, crush: int) -> float:
    """ED census -> 0..1 crowding index."""
    if crush <= comfort:
        return 0.0
    return min(1.0, max(0.0, (census - comfort) / (crush - comfort)))


def smooth(previous: float, target: float, dt: float, tau: float) -> float:
    """First-order exponential smoothing (a 'material/information delay'). Limits
    how fast a signal can change per tick; tau is the time constant in minutes."""
    if tau <= 0:
        return target
    alpha = 1.0 - math.exp(-dt / tau)
    return previous + alpha * (target - previous)
