"""
Trust profiles: a real NHS trust's PUBLISHED, trust-level figures mapped into a
runnable ``Department`` - the "pick your trust" (Tier-0) set-up.

The distinction that keeps this honest (mirrors the ECDS seam):

* **Inputs we can fill from open data** -> the department set-up. Attendances
  per day (A&E monthly stats), whole-hospital bed occupancy (UEC SitRep / bed
  availability). These drive the model.
* **Observed OUTCOMES** (4-hour %, 12-hour %) are NOT inputs. They are what the
  model should reproduce - kept here only to (a) validate the build and (b) seed
  a real peer benchmark. See ``validate_against_observed``.
* **What no open dataset contains** (service-time distributions, routing, the
  nurse-to-cubicle ratio, the exact rota, which areas the trust runs) is left at
  the template default and flagged in ``provenance`` - never silently invented.

Every field carries its source and date in ``SOURCES`` so nothing is presented
as real that isn't. Figures below are transcribed from public documents; verify
against the live sources before any operational use.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..department.config import Department


@dataclass
class TrustProfile:
    ods_code: str                       # NHS Organisation Data Service code (e.g. RFF)
    name: str
    attendances_per_day: float          # INPUT: mean daily ED attendances
    baseline_bed_occupancy: float | None = None   # INPUT: whole-hospital G&A occupancy (0-1)
    inpatient_beds: int | None = None   # INPUT if known; else keep template default
    # observed OUTCOMES - for validation / benchmarking only, never model inputs:
    observed_four_hour_pct: float | None = None
    observed_twelve_hour_pct: float | None = None
    # per-field provenance: field name -> "source, date"
    sources: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Registry of real trusts. Start with one single-site Type 1 ED (clean 1:1 map
# to a single department). Add more by transcribing their published figures.
# --------------------------------------------------------------------------- #
TRUSTS: dict[str, TrustProfile] = {
    "RFF": TrustProfile(
        ods_code="RFF",
        name="Barnsley Hospital NHS Foundation Trust",
        # ~106,000 ED attendances in 2024-25 -> ~290/day
        attendances_per_day=290,
        # G&A bed occupancy ~91.8% (Sept 2024); national Q4 24/25 ran at 92.5%
        baseline_bed_occupancy=0.918,
        # bed count is NOT in the figures pulled - needs the G&A bed-availability
        # return; left None so the template default (and its flag) stands.
        inpatient_beds=None,
        observed_four_hour_pct=67.5,        # full-year 2024-25 (81% in March 2025)
        observed_twelve_hour_pct=None,
        sources={
            "attendances_per_day": "Barnsley Hospital 2024-25 Annual Report "
                                   "(~106,000 ED attendances) - accessed 2026-07",
            "baseline_bed_occupancy": "G&A bed occupancy ~91.8% (Sept 2024), "
                                      "UEC SitRep / bed-availability data - accessed 2026-07",
            "observed_four_hour_pct": "Barnsley Hospital 2024-25 Annual Report "
                                      "(67.5% full year; 81% March) - accessed 2026-07",
        },
        notes=[
            "Single-site Type 1 ED - maps to one department cleanly.",
            "Inpatient bed count not sourced from open data pulled; using template "
            "default until the G&A bed-availability return is added.",
            "Enabled areas, opening hours and rota are trust configuration, not "
            "open data - left at the template default for the trust to confirm.",
        ],
    ),
}


def get_profile(ods_code: str) -> TrustProfile:
    key = (ods_code or "").strip().upper()
    if key not in TRUSTS:
        raise KeyError(f"no profile for '{ods_code}'. Known: {', '.join(sorted(TRUSTS))}")
    return TRUSTS[key]


def to_department(profile: TrustProfile, base: Department | None = None) -> Department:
    """Map a trust's published INPUTS onto a Department. Anything open data can't
    supply (areas, rota, hours, and beds when unknown) keeps the template default,
    so the result is a plausible model of THIS trust the user can then refine."""
    base = base or Department.default()
    d = Department.from_dict(base.to_dict())      # copy - never mutate the caller's
    d.name = f"{profile.name} ({profile.ods_code})"
    d.attendances_per_day = float(profile.attendances_per_day)
    if profile.baseline_bed_occupancy is not None:
        d.baseline_bed_occupancy = float(profile.baseline_bed_occupancy)
    if profile.inpatient_beds is not None:
        d.inpatient_beds = int(profile.inpatient_beds)
    return d


def provenance(profile: TrustProfile) -> list[dict]:
    """Per-field record of what was filled, its value and its source - so every
    autofilled number is traceable and the residual defaults are visible."""
    def row(field_name, value, kind):
        return {"field": field_name, "value": value, "kind": kind,
                "source": profile.sources.get(field_name, "template default (not open data)")}
    rows = [
        row("attendances_per_day", profile.attendances_per_day, "input"),
        row("baseline_bed_occupancy", profile.baseline_bed_occupancy, "input"),
        row("inpatient_beds",
            profile.inpatient_beds if profile.inpatient_beds is not None else "template default",
            "input"),
        row("observed_four_hour_pct", profile.observed_four_hour_pct, "validation-target"),
    ]
    return rows


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
    return {"department": dept.to_dict(), "version": version,
            "provenance": provenance(profile), "notes": profile.notes}


def main(argv=None):
    """CLI: `python -m uec_hybrid.ingest.trust_profile RFF` sets Barnsley as the
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

    print(f"\n{profile.name} ({profile.ods_code}) -> department")
    print("-" * 64)
    for r in provenance(profile):
        print(f"  {r['field']:<24} {str(r['value']):<16} [{r['kind']}]  {r['source']}")
    for n in profile.notes:
        print(f"  note: {n}")

    p = Pathway.from_dict(build_dept(dept))
    res = run_cosim(p, seed=2)
    modelled = kpis(res, p).get("four_hour", 0.0)
    v = validate_against_observed(profile, modelled)
    print("-" * 64)
    print(f"  modelled 4-hour {v['modelled']}%  vs observed {v['observed']}%  "
          f"(delta {v.get('delta_pct_points')} pts)")
    print(f"  {v['note']}")
    return v


if __name__ == "__main__":
    main()
