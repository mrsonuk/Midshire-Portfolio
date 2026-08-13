"""
Committed department seeds: stand up a named trust's department from files in
the repo, reproducibly, with one command:

    python3 -m uec_hybrid.ingest.seed RGT [--warm]

The saved department normally lives only in the local (gitignored) database, so
a configuration built by clicking is not reproducible on another machine. A
seed fixes that for demo/pilot trusts. It composes the product's OWN ingest
paths - nothing is bypassed:

1. ``data/seeds/<ods>_*.xlsx``  - the trust's filled set-up workbook
   (areas, hours, rota, REAL physical capacity, costs, service times).
2. ``data/nhs_trust_snapshot.csv``  - published headline figures fill anything
   the workbook left blank (attendances/day, beds, occupancy).
3. ``data/<ods>_published.json``  - published aggregate distributions become a
   calibration patch (hour-of-arrival shape, acuity mix, ambulance share,
   admission rates) via ``ingest.published``.

Everything is stamped with provenance, so the product's data-status banner can
say exactly which numbers are published, which the trust provided, and which
remain template assumptions. Running a seed changes only the local database -
never the repo, never any other machine.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..department.config import Department
from . import published, trust_profile
from .workbook import read_workbook

SEEDS_DIR = Path(__file__).resolve().parent.parent / "data" / "seeds"

# Department fields the trust snapshot can backfill when the workbook left them
# at the template default (workbook wins when it set a real value).
_PROFILE_FIELDS = ("attendances_per_day", "inpatient_beds", "baseline_bed_occupancy")


def find_seed_workbook(ods_code: str) -> Path | None:
    ods = (ods_code or "").strip().lower()
    if not SEEDS_DIR.exists():
        return None
    hits = sorted(SEEDS_DIR.glob(f"{ods}*.xlsx"))
    return hits[0] if hits else None


def _merge_patch(base: dict, overlay: dict) -> dict:
    """Merge two calibration patches; the overlay (workbook) wins per key."""
    out = {"arrivals": {}, "attributes": {}, "admission_rates": {}, "imaging": {}}
    for part in out:
        out[part].update((base or {}).get(part) or {})
        out[part].update((overlay or {}).get(part) or {})
    return out


PATCH_PARTS = ("arrivals", "attributes", "admission_rates", "imaging")


def _patch_is_empty(patch: dict) -> bool:
    return not any((patch or {}).get(k) for k in PATCH_PARTS)


def seed(ods_code: str, warm: bool = False) -> dict:
    """Install the seed as THE saved department (local database only)."""
    from ..platform import store

    ods = (ods_code or "").strip().upper()
    profile = trust_profile.get_profile(ods)          # raises for unknown codes
    summary: list[str] = []
    prov: list[dict] = []

    # 1) the committed workbook, through the product's own reader
    wb_path = find_seed_workbook(ods)
    if wb_path is not None:
        result = read_workbook(wb_path.read_bytes(), filename=wb_path.name)
        dept: Department = result["department"]
        wb_patch = result.get("patch") or {}
        summary += result["summary"]
        prov += result["provenance"]
    else:
        result = {}
        dept = trust_profile.to_department(profile)
        wb_patch = {}
        summary.append(f"No seed workbook in {SEEDS_DIR.name}/ - department starts "
                       "from the trust's published headline figures + template defaults.")
        prov += trust_profile.provenance(profile)

    # 2) published headline figures backfill whatever the workbook left blank
    wb_set = {p["field"] for p in (result.get("provenance") or [])
              if p.get("source") == "workbook"}
    for f in _PROFILE_FIELDS:
        v = getattr(profile, f, None)
        if f not in wb_set and v is not None:
            setattr(dept, f, float(v) if f != "inpatient_beds" else int(v))
            prov.append({"field": f, "value": v, "source": profile.source or "trust snapshot"})
            summary.append(f"{f} backfilled from the published snapshot ({v}).")
    if f"({ods})" not in dept.name:
        dept.name = f"{dept.name} ({ods})"            # auto-calibration finds the
                                                      # trust's observed 4-hour by
                                                      # this suffix

    # 3) published aggregate distributions -> calibration patch
    agg = published.load_aggregates(ods)
    pub_patch: dict = {}
    if agg is not None:
        pub_patch, pub_summary = published.patch_from_aggregates(
            agg, attendances_per_day=dept.attendances_per_day)
        summary += pub_summary
    patch = _merge_patch(pub_patch, wb_patch)
    if patch["arrivals"].get("hourly_profile"):
        # mirror /api/calibrate: the department's daily total follows the profile
        dept.attendances_per_day = round(sum(patch["arrivals"]["hourly_profile"]), 1)

    # 4) persist through the same store calls the HTTP endpoints use
    version = store.save_department(dept.to_dict())
    if not _patch_is_empty(patch):
        store.save_calibration("your_department", patch, summary)
    else:
        store.clear_calibration("your_department")
        summary.append("No calibration applied - arrival patterns stay modelled "
                       "assumptions until published aggregates or an extract arrive.")
    if result.get("cost_book"):
        from ..finance.costbook import save_cost_book
        save_cost_book(result["cost_book"])
    if result.get("role_rates"):
        from ..workforce.roles import save_role_rates
        save_role_rates(result["role_rates"])
    if result.get("service_params"):
        from .. import model_params
        model_params.save_params(result["service_params"])
    store.save_setting("data_source", {
        "kind": "seed", "ods": ods,
        "label": f"{profile.name} ({ods}) - committed seed"
                 + (f" [{wb_path.name}]" if wb_path else ""),
        "source": profile.source, "as_of": profile.as_of})
    store.save_setting("provenance", {"rows": prov,
                                      "notes": trust_profile.notes(profile)})

    out = {"ok": True, "ods": ods, "department": dept.to_dict(), "version": version,
           "workbook": (wb_path.name if wb_path else None),
           "calibration_applied": not _patch_is_empty(patch),
           "summary": summary, "provenance": prov}

    if warm:
        # pre-compute the demo surfaces through the real endpoints so the run
        # cache is hot and the product opens instantly
        from ..app.server import app
        client = app.test_client()
        for method, url in (("post", "/api/control-tower"), ("get", "/api/exec"),
                            ("post", "/api/gap")):
            r = getattr(client, method)(url, json={} if method == "post" else None)
            summary.append(f"warmed {url}: HTTP {r.status_code}")
    return out


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    warm = "--warm" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        print("usage: python3 -m uec_hybrid.ingest.seed <ODS_CODE> [--warm]")
        return 2
    res = seed(args[0], warm=warm)
    print(f"\nSeeded {res['department']['name']} (v{res['version']})"
          + (f" from {res['workbook']}" if res['workbook'] else ""))
    print("-" * 68)
    for line in res["summary"]:
        print(f"  {line}")
    print("-" * 68)
    filled = [p for p in res["provenance"] if p.get("source") not in
              (None, "template default", "template default (not open data)")]
    print(f"  {len(filled)} field(s) from data, "
          f"{len(res['provenance']) - len(filled)} still template assumptions "
          "(see the product's data-status banner).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
