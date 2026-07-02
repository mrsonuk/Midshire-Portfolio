"""
Ingest: turn a real NHS trust's data into a runnable department, so the product
opens on a trust's OWN numbers instead of an imagined 320/day template. Two ways
in, neither of which needs a Python or JSON edit:

* **Pick your trust** (``trust_profile`` / ``nhs_open_data``) - published,
  trust-level figures from the bundled open-data snapshot, keyed by ODS code.
* **Import a workbook** (``workbook``) - a trust fills in an Excel/CSV template
  (areas, beds, rota, optional arrivals) and uploads it.
"""
from .trust_profile import (
    TrustProfile, TRUSTS, get_profile, list_profiles, to_department, provenance,
    notes, validate_against_observed, install,
)
from .nhs_open_data import fetch_trust, list_trusts
from . import workbook

__all__ = [
    "TrustProfile", "TRUSTS", "get_profile", "list_profiles", "to_department",
    "provenance", "notes", "validate_against_observed", "install",
    "fetch_trust", "list_trusts", "workbook",
]
