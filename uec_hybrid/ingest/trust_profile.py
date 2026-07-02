"""
Trust profiles: real NHS trusts' PUBLISHED, trust-level figures mapped into a
runnable ``Department`` - the "pick your trust" (Tier-0) set-up.

The registry is DATA, not code: profiles live in ``data/nhs_trust_snapshot.csv``,
so adding or refreshing a trust is a spreadsheet edit (or an automatic refresh of
the snapshot), never a Python change. Each row carries its ``source`` and
``as_of`` so nothing is presented as real that isn't.

The distinction that keeps this honest (mirrors the ECDS seam):

* **Inputs we can fill from open data** -> the department set-up: attendances
  per day (A&E monthly stats), whole-hospital bed occupancy (UEC SitRep / bed
  availability), inpatient beds where published. These drive the model.
* **Observed OUTCOMES** (4-hour %, 12-hour %) are NOT inputs - they are what the
  model should reproduce; kept only to validate the build and seed a real peer
  benchmark. See ``validate_against_observed``.
* **What no open dataset contains** (service-time distributions, routing, the
  nurse-to-cubicle ratio, the exact rota, which areas the trust runs) stays the
  template default and is flagged in ``notes``/``provenance`` - never invented.

Figures are transcribed from public documents; verify against the live sources
before any operational use.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ..department.config import Department

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "nhs_trust_snapshot.csv"


@dataclass
class TrustProfile:
    ods_code: str                       # NHS Organisation Data Service code (e.g. RFF)
    name: str
    attendances_per_day: float | None = None      # INPUT: mean daily ED attendances
    baseline_bed_occupancy: float | None = None    # INPUT: whole-hospital G&A occupancy (0-1)
    inpatient_beds: int | None = None              # INPUT if published; else template default
    observed_four_hour_pct: float | None = None    # OUTCOME: validation / benchmark only
    observed_twelve_hour_pct: float | None = None
    source: str = ""
    as_of: str = ""


def _num(v, cast=float):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return cast(v)
    except (TypeError, ValueError):
        return None


def _load_snapshot(path: Path = SNAPSHOT) -> dict[str, TrustProfile]:
    """Load the trust registry from the CSV snapshot (keyed by ODS code)."""
    out: dict[str, TrustProfile] = {}
    if not path.exists():
        return out
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("ods_code") or "").strip().upper()
            if not code:
                continue
            out[code] = TrustProfile(
                ods_code=code,
                name=(row.get("name") or code).strip(),
                attendances_per_day=_num(row.get("attendances_per_day")),
                baseline_bed_occupancy=_num(row.get("bed_occupancy")),
                inpatient_beds=_num(row.get("inpatient_beds"), int),
                observed_four_hour_pct=_num(row.get("four_hour_pct")),
                observed_twelve_hour_pct=_num(row.get("twelve_hour_pct")),
                source=(row.get("source") or "").strip(),
                as_of=(row.get("as_of") or "").strip(),
            )
    return out


TRUSTS: dict[str, TrustProfile] = _load_snapshot()


def get_profile(ods_code: str) -> TrustProfile:
    key = (ods_code or "").strip().upper()
    if key not in TRUSTS:
        raise KeyError(f"no profile for '{ods_code}'. Known: {', '.join(sorted(TRUSTS))}")
    return TRUSTS[key]


def list_profiles() -> list[dict]:
    """Compact list for a picker UI - which inputs each trust can pre-fill."""
    rows = []
    for p in sorted(TRUSTS.values(), key=lambda x: x.name):
        rows.append({
            "ods_code": p.ods_code, "name": p.name, "as_of": p.as_of,
            "attendances_per_day": p.attendances_per_day,
            "baseline_bed_occupancy": p.baseline_bed_occupancy,
            "inpatient_beds": p.inpatient_beds,
            "observed_four_hour_pct": p.observed_four_hour_pct,
            "has_attendances": p.attendances_per_day is not None,
        })
    return rows


def to_department(profile: TrustProfile, base: Department | None = None) -> Department:
    """Map a trust's published INPUTS onto a Department. Anything open data can't
    supply (attendances when unknown, beds when unknown, areas, rota, hours) keeps
    the template default, so the result is a plausible model of THIS trust the
    user can then refine."""
    base = base or Department.default()
    d = Department.from_dict(base.to_dict())      # copy - never mutate the caller's
    d.name = f"{profile.name} ({profile.ods_code})"
    if profile.attendances_per_day is not None:
        d.attendances_per_day = float(profile.attendances_per_day)
    if profile.baseline_bed_occupancy is not None:
        d.baseline_bed_occupancy = float(profile.baseline_bed_occupancy)
    if profile.inpatient_beds is not None:
        d.inpatient_beds = int(profile.inpatient_beds)
    return d


def provenance(profile: TrustProfile) -> list[dict]:
    """Per-field record of what was filled, its value and its source - so every
    autofilled number is traceable and the residual defaults are visible."""
    src = profile.source or "template default (not open data)"
    def row(field_name, value, kind):
        filled = value is not None
        return {"field": field_name, "value": value, "kind": kind,
                "filled": filled,
                "source": (src if filled else "template default (not open data)")}
    return [
        row("attendances_per_day", profile.attendances_per_day, "input"),
        row("baseline_bed_occupancy", profile.baseline_bed_occupancy, "input"),
        row("inpatient_beds", profile.inpatient_beds, "input"),
        row("observed_four_hour_pct", profile.observed_four_hour_pct, "validation-target"),
    ]


def notes(profile: TrustProfile) -> list[str]:
    """Plain-language flags: what the trust still needs to confirm/upload."""
    out = []
    if profile.attendances_per_day is None:
        out.append("Attendances per day not in the figures pulled - using the template "
                   "default until the A&E return or a workbook is uploaded.")
    if profile.inpatient_beds is None:
        out.append("Inpatient bed count not in the figures pulled - using the template default.")
    if profile.baseline_bed_occupancy is None:
        out.append("Bed occupancy not in the figures pulled - using the model default.")
    out.append("Enabled areas, opening hours and rota are trust configuration, not open "
               "data - left at the template default for the trust to confirm.")
    return out


def validate_against_observed(profile: TrustProfile, modelled_four_hour_pct: float) -> dict:
    """Compare the model's OUTPUT 4-hour performance to the trust's real reported
    figure. A large gap means the residual (un-derivable) assumptions - service
    times especially - need calibrating for this trust; it does not mean the
    inputs are wrong. This is the single strongest credibility check."""
    obs = profile.observed_four_hour_pct
    if obs is None:
        return {"observed": None, "modelled": round(modelled_four_hour_pct, 1),
                "note": "no observed figure to validate against."}
    delta = modelled_four_hour_pct - obs
    return {
        "observed": obs,
        "modelled": round(modelled_four_hour_pct, 1),
        "delta_pct_points": round(delta, 1),
        "within_10pp": abs(delta) <= 10,
        "note": ("Model reproduces the trust's 4-hour position within 10 points."
                 if abs(delta) <= 10 else
                 "Gap > 10 points: calibrate the residual assumptions (service "
                 "times) for this trust - the inputs are real, the internals need tuning."),
    }


def install(ods_code: str, key: str = "default") -> dict:
    """Save a trust's profile as THE department, so the control tower (and every
    surface) opens on the trust's real numbers. Local persistence only."""
    from ..platform import store
    profile = get_profile(ods_code)
    dept = to_department(profile)
    version = store.save_department(dept.to_dict(), key=key)
    store.clear_calibration("your_department")     # a fresh trust starts clean
    return {"department": dept.to_dict(), "version": version,
            "provenance": provenance(profile), "notes": notes(profile)}


def main(argv=None):
    """CLI: `python -m uec_hybrid.ingest.trust_profile RFF` sets the trust as the
    saved department and prints what was filled, where it came from, and how the
    model's 4-hour output compares to the trust's real figure."""
    import sys
    from ..des.pathway import Pathway
    from ..coupling.cosim import run_cosim
    from ..analysis.metrics import kpis
    from ..department.builder import build as build_dept

    ods = (argv or sys.argv[1:] or ["RFF"])[0]
    profile = get_profile(ods)
    dept = to_department(profile)

    print(f"\n{profile.name} ({profile.ods_code}) -> department   [source as of {profile.as_of}]")
    print("-" * 68)
    for r in provenance(profile):
        tag = "" if r["filled"] else "  (default)"
        print(f"  {r['field']:<24} {str(r['value']):<10} [{r['kind']}]{tag}")
    for n in notes(profile):
        print(f"  note: {n}")

    p = Pathway.from_dict(build_dept(dept))
    res = run_cosim(p, seed=2)
    modelled = kpis(res, p).get("four_hour", 0.0)
    v = validate_against_observed(profile, modelled)
    print("-" * 68)
    if v["observed"] is not None:
        print(f"  modelled 4-hour {v['modelled']}%  vs observed {v['observed']}%  "
              f"(delta {v.get('delta_pct_points')} pts)")
    else:
        print(f"  modelled 4-hour {v['modelled']}%  ({v['note']})")
    print(f"  {v['note']}")
    return v


if __name__ == "__main__":
    main()
