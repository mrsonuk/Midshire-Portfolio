"""
Channel map for the SD<->DES seam (documentation + helpers).

The coupling is by convention: a DES node names an SD signal in ``service_signal``
or ``routes_by_signal`` and reads it live from SystemState; a DES sink records a
flow channel that the SD drains. This module documents that contract and provides
small helpers, so the wiring is auditable in one place.
"""
from __future__ import annotations

# SD -> DES : held signals read by DES nodes
SD_TO_DES = {
    "bed_wait_multiplier": "scales 'await_inpatient_bed' service time (exit-block)",
    "mh_bed_wait_multiplier": "scales 'await_mh_bed' service time",
    "community_pull": "uplift on routing to community_referral (active pull)",
    "handover_delay": "additional ambulance handover minutes (Cat-2 feedback)",
}

# DES -> SD : flow channels recorded at sinks/decisions, drained each tick
DES_TO_SD = {
    "admissions": "inflow to inpatient_beds stock",
    "mh_admissions": "inflow to mh_beds stock",
    "diversions_to_community": "inflow to community stock",
    "discharges": "informational",
}


def census_thresholds(pathway) -> tuple[int, int]:
    """Comfort / crush ED census from the bedded-area capacities, if not set."""
    bedded = sum(c for r, c in pathway.resources.items()
                 if r in ("cubicle", "resus_bay", "paeds_cubicle", "fit_to_sit_chair"))
    return int(bedded * 0.8), int(bedded * 1.8)
