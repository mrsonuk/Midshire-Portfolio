"""
Ingest: turn a real NHS trust's published figures into a runnable department, so
the product opens on a trust's OWN numbers instead of an imagined 320/day
template. This is the "pick your trust" (Tier-0) seam - the first step away from
hand-editing model parameters toward data-driven set-up.
"""
from .trust_profile import (
    TrustProfile, TRUSTS, get_profile, to_department, provenance, validate_against_observed,
)

__all__ = [
    "TrustProfile", "TRUSTS", "get_profile", "to_department", "provenance",
    "validate_against_observed",
]
