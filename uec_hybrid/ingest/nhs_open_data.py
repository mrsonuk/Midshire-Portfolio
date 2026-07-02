"""
API-pull seam: fetch a trust's set-up figures by ODS code, automatically.

Today this reads the bundled, refreshable NHS open-data snapshot
(``data/nhs_trust_snapshot.csv``) - keyed by ODS code, it is the "automatic"
path that needs no manual JSON or Python edit. The snapshot is transcribed from
public, trust-level NHS statistics:

* A&E Attendances & Emergency Admissions (monthly) -> attendances/day, 4-hour %
* UEC Daily SitRep / bed-availability returns       -> bed occupancy, beds

``fetch_live`` is the documented hook for a deployment that HAS outbound access
to pull those publications directly and refresh the snapshot; it is intentionally
not wired to a live scrape here, so the product keeps working offline on
locked-down NHS networks (a design requirement). Refreshing the snapshot is a
data task (replace the CSV), never a code change.
"""
from __future__ import annotations

from .trust_profile import TrustProfile, get_profile, list_profiles


def list_trusts() -> list[dict]:
    """Trusts available to pick, with which inputs each can pre-fill."""
    return list_profiles()


def fetch_trust(ods_code: str) -> TrustProfile:
    """Return a trust's published figures by ODS code (from the snapshot)."""
    return get_profile(ods_code)


def fetch_live(ods_code: str):   # pragma: no cover - requires outbound access
    """Placeholder for a live pull from NHS England publications. Implement per
    deployment: download the latest A&E monthly file + bed-availability return,
    filter to this ODS code, and write the row back into the snapshot CSV. Kept
    unimplemented so nothing silently depends on network access at runtime."""
    raise NotImplementedError(
        "Live NHS open-data pull is not enabled in this build. Refresh "
        "data/nhs_trust_snapshot.csv from the published A&E and bed-availability "
        "statistics, or upload a trust workbook via the product.")
