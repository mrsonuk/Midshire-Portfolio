"""
Published-aggregates seam: turn PUBLISHED NHS aggregate distributions into the
same calibration patch the ECDS upload produces - so a trust can be calibrated
from open data alone, before it shares a single record.

Row-level extracts (the ECDS seam) stay the gold standard. But national/provider
AGGREGATES - hour-of-arrival shape, acuity mix, ambulance conveyance share,
admission rate by acuity - are published (NHS Digital "Hospital Accident &
Emergency Activity", ECDS-based), and this module maps them onto the model
WITHOUT inventing any row-level data. Every block carries its own ``source``
citation and the summary states the granularity used ("national shape, trust
volume"), so nothing is presented as more local than it really is.

Aggregate files live in ``data/<ods>_published.json``; see
``data/rgt_published.json`` for the expected shape. A block whose value is
null/missing is simply skipped - the model keeps its template default and the
product's provenance banner keeps flagging it as an assumption.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_aggregates(ods_code: str) -> dict | None:
    """The committed published-aggregates file for a trust, or None."""
    path = DATA_DIR / f"{(ods_code or '').strip().lower()}_published.json"
    if not path.exists():
        return None
    return json.load(open(path))


def _block(agg: dict, key: str):
    """(value(s), source) for a block; (None, '') when absent/unfilled."""
    b = agg.get(key) or {}
    v = b.get("values", b.get("value"))
    if isinstance(v, list) and not any(x is not None for x in v):
        v = None
    if isinstance(v, dict) and not any(x is not None for x in v.values()):
        v = None
    return v, str(b.get("source") or "")


def patch_from_aggregates(agg: dict, attendances_per_day: float | None = None
                          ) -> tuple[dict, list]:
    """Convert published aggregate distributions into an ECDS-seam calibration
    patch (see demand/ecds_seam.apply_patch for the contract):

    * ``hourly_shares`` (24 shares summing to ~1) x attendances/day
      -> ``arrivals.hourly_profile`` (ABSOLUTE arrivals per hour of day)
    * ``acuity_mix_pct`` -> ``arrivals.acuity_mix`` (percentages)
    * ``ambulance_share`` -> ``attributes.ambulance`` (apply_patch moves the
      ambulance STREAM share, so conveyance genuinely changes who arrives how)
    * ``admission_rate_by_acuity`` -> ``admission_rates``
    * ``paediatric_share`` / ``mental_health_share`` -> attributes
    * ``investigation_rates`` (CT / X-ray per attendance) -> ``imaging``, which
      scales the imaging_decision routing (apply_patch keeps the assumed
      gradient across acuity and moves its weighted average onto the observed
      workload - see ecds_seam.apply_patch)

    Returns (patch, summary). Blocks that are null are skipped and reported.
    """
    patch: dict = {"arrivals": {}, "attributes": {}, "admission_rates": {}, "imaging": {}}
    summary: list[str] = []
    skipped: list[str] = []

    apd = attendances_per_day
    if apd is None:
        apd, _src = _block(agg, "attendances_per_day")
    apd = float(apd) if apd else None

    shares, src = _block(agg, "hourly_shares")
    if shares and apd:
        shares = [max(0.0, float(x or 0.0)) for x in list(shares)[:24]]
        if len(shares) == 24 and sum(shares) > 0:
            tot = sum(shares)
            profile = [round(s / tot * apd, 2) for s in shares]
            patch["arrivals"]["hourly_profile"] = profile
            gran = (agg.get("hourly_shares") or {}).get("granularity", "published")
            summary.append(f"Arrival profile applied ({gran} hour-of-arrival shape "
                           f"x {round(apd)}/day). {src}".strip())
    elif shares and not apd:
        skipped.append("hourly shape (no attendances/day to scale it by)")
    else:
        skipped.append("hour-of-arrival shape")

    mix, src = _block(agg, "acuity_mix_pct")
    if mix:
        clean = {}
        for k, v in mix.items():
            if v is None:
                continue
            label = k if str(k).lower().startswith("acuity") else f"Acuity {k}"
            clean[label] = float(v)
        tot = sum(clean.values())
        if tot > 0:
            patch["arrivals"]["acuity_mix"] = {k: round(v / tot * 100, 2)
                                               for k, v in clean.items()}
            summary.append(f"Acuity mix applied. {src}".strip())
    else:
        skipped.append("acuity mix")

    amb, src = _block(agg, "ambulance_share")
    if amb is not None:
        amb = float(amb)
        if amb > 1.5:              # entered as a percent
            amb = amb / 100.0
        patch["attributes"]["ambulance"] = round(amb, 4)
        summary.append(f"Ambulance arrivals {amb*100:.0f}%. {src}".strip())
    else:
        skipped.append("ambulance conveyance share")

    for key, attr, label in (("paediatric_share", "paediatric", "paediatric share"),
                             ("mental_health_share", "mental_health", "mental-health share")):
        v, src = _block(agg, key)
        if v is not None:
            v = float(v)
            if v > 1.5:
                v = v / 100.0
            patch["attributes"][attr] = round(v, 4)
            summary.append(f"{label.capitalize()} {v*100:.1f}%. {src}".strip())
        else:
            skipped.append(label)

    imaging, src = _block(agg, "investigation_rates")
    if imaging:
        clean = {}
        for k in ("ct", "xray"):
            v = imaging.get(k)
            if v is None:
                continue
            v = float(v)
            if v > 1.5:                # entered as a percent
                v = v / 100.0
            clean[k] = round(v, 4)
        if clean:
            patch["imaging"] = clean
            bits = ", ".join(f"{k.upper() if k == 'ct' else 'X-ray'} {v*100:.0f}%"
                             for k, v in clean.items())
            summary.append(f"Imaging workload per attendance applied ({bits}). {src}".strip())
    else:
        skipped.append("imaging (CT / X-ray) rates")

    rates, src = _block(agg, "admission_rate_by_acuity")
    if rates:
        for k, v in rates.items():
            if v is None:
                continue
            label = k if str(k).lower().startswith("acuity") else f"Acuity {k}"
            r = float(v)
            if r > 1.5:
                r = r / 100.0
            patch["admission_rates"][label] = round(r, 3)
        if patch["admission_rates"]:
            summary.append(f"Admission rate by acuity applied. {src}".strip())
    else:
        skipped.append("admission rate by acuity")

    if skipped:
        summary.append("Not in the published figures (template assumption kept): "
                       + ", ".join(skipped) + ".")
    summary.append("Per-stage service times unchanged - never published; calibrate "
                   "from the trust's observed 4-hour figure (auto-calibration) or "
                   "stage timestamps.")
    return patch, summary
