"""
Midshire validation and conformance report - run it after ANY change:

    python3 -m uec_hybrid.midshire.validate [--seeds 6]

The adult-only, SDEC-extended demonstrator does NOT inherit the source
(Cambridge) build's validation. This report states what can be checked:

1. Conformance - every simulated journey follows the pathway definition (legal
   transitions, no regression across bands, capped stays respected).
2. Per-area comparison with the source trust's own observed figures, labelled
   for what they are: the source figures are for the source trust's areas; the
   demonstrator is not expected to match them exactly once its cohort and
   pathway differ.
3. A COMPUTED decomposition of how far the demonstrator's four-hour figure sits
   from the source model's, step by step (children removed, mental-health
   route, SDEC streaming), so the difference is explained by measurement, not
   asserted.
"""
from __future__ import annotations

import argparse
import copy
import json
import statistics as st

import numpy as np

from . import config as mcfg, metrics as M
from .build import build_model
from ..coupling.cosim import run_cosim
from ..des.pathway import Pathway
from ..validation.conformance import check

AREAS = {"ed_resus": "resus", "ed_cubicles": "majors_trolleys",
         "ed_ambulatory": "majors_ambulant", "utc_minor_illness": "minors", "sdec": "sdec"}


def _source_raw():
    """The source trust's pathway as its seed builds it (pure; no database)."""
    from ..ingest.workbook import read_workbook
    from ..ingest import published
    from ..ingest.seed import find_seed_workbook, _merge_patch
    from ..department.builder import build
    from ..demand.ecds_seam import apply_patch
    wb = find_seed_workbook("RGT")
    r = read_workbook(wb.read_bytes(), filename=wb.name)
    d = r["department"]
    d.attendances_per_day, d.inpatient_beds, d.baseline_bed_occupancy = 400.5, 1068, 0.8926
    pp, _ = published.patch_from_aggregates(published.load_aggregates("RGT"), attendances_per_day=400.5)
    raw = apply_patch(build(d), _merge_patch(pp, r.get("patch") or {}))
    raw["sim_duration_minutes"] = 10080 + 720                 # same drain as Midshire
    raw.setdefault("uec", {})["cohort_window"] = [1440, 10080]
    return raw


def _four_one(args):
    raw, s, adults_only = args
    tr = run_cosim(Pathway.from_dict(raw), seed=s, trace=True)["trace"]
    p = M.patients_frame(tr)
    a, b = raw["uec"]["cohort_window"]
    c = p[(p["arrival"] >= a) & (p["arrival"] < b)]
    if adults_only:
        c = c[~c["attrs"].fillna("").str.contains("paediatric")]
    dur = np.where(c["ed_end"].notna(), c["ed_end"] - c["arrival"], np.inf)
    return float(100 * (dur <= 240).mean())


def _four(raw, seeds, adults_only=False):
    """Mean four-hour % and the standard error over the seeds."""
    from .runner import get_pool
    pool = get_pool()
    jobs = [(raw, s, adults_only) for s in seeds]
    vals = list(pool.map(_four_one, jobs)) if pool else [_four_one(j) for j in jobs]
    return st.mean(vals), (st.stdev(vals) / len(vals) ** 0.5 if len(vals) > 1 else 0.0)


def report(n_seeds: int = 6, n_decomp: int = 16) -> dict:
    base = mcfg.baseline_inputs()
    seeds = list(base["engine"]["selection_seeds"])[:n_seeds]
    m = build_model(base)
    p = m.pathway
    conf, area_los, area_vol, sdec_los = [], {k: [] for k in AREAS}, {k: [] for k in AREAS}, []
    four = []
    for s in seeds:
        res = run_cosim(p, seed=s, trace=True)
        conf.append(check(res, p))
        tr = res["trace"]
        k = M.replication_kpis(tr, m.raw, 240)
        four.append(k["four_hour"])
        pf = M.patients_frame(tr).set_index("pid")
        a, b = m.raw["uec"]["cohort_window"]
        stt = tr["states"]
        for node in AREAS:
            first = stt[(stt["node"] == node)].groupby("pid")["start"].min()
            first = first[(pf.loc[first.index, "arrival"] >= a) & (pf.loc[first.index, "arrival"] < b)]
            area_vol[node].append(len(first) / ((b - a) / 1440))
            start = first if node == "sdec" else pf.loc[first.index, "arrival"]
            los = (pf.loc[first.index, "departure"] - start).dropna()
            if len(los):
                area_los[node].append(float(los.median()))
    agg = json.load(open(mcfg.DATA_DIR.parent / "rgt_published.json"))
    tid = agg["cuh_extracts"]["time_in_department_june_2026_mins"]
    obs_vol = {"resus": 1754 / 181, "majors_trolleys": 13211 / 181, "majors_ambulant": 29544 / 181,
               "minors": 25481 / 181, "sdec": None}
    rows = []
    for node, area in AREAS.items():
        mv = st.mean(area_los[node]) if area_los[node] else None
        ov = tid[area][0] if area in tid else None
        rows.append({"area": area, "model_los_median": mv, "source_los_median": ov,
                     "ratio": (mv / ov) if (mv and ov) else None,
                     "model_per_day": st.mean(area_vol[node]),
                     "source_per_day_internal_basis": obs_vol.get(area)})
    # decomposition, step by step, on the same seeds
    seeds_d = list(range(201, 201 + n_decomp))
    src = _source_raw()
    no_kids = copy.deepcopy(src)
    no_kids["arrivals"]["attributes"]["paediatric"] = 0.0
    no_kids["arrivals"]["hourly_profile"] = [h * (1 - 0.1335) for h in no_kids["arrivals"]["hourly_profile"]]
    nosdec = copy.deepcopy(base)
    nosdec["sdec"]["routing"] = {"from_streaming": {}, "from_rat": {}, "streaming_to_rat": {}}
    mh_fallback = copy.deepcopy(nosdec)
    mh_fallback["mental_health"]["admission_rate"] = 1.0
    steps = [
        ("Source model, all ages (the Cambridge build)", *_four(src, seeds_d)),
        ("Source model, adults only within it", *_four(src, seeds_d, adults_only=True)),
        ("Source model with children removed from demand", *_four(no_kids, seeds_d)),
        ("Midshire pathway, rota and capacity; no SDEC streaming; every MH patient admitted as at source",
         *_four(build_model(mh_fallback).raw, seeds_d)),
        ("... with the source trust's real MH admission rate (18.3%)", *_four(build_model(nosdec).raw, seeds_d)),
        ("... with the illustrative SDEC streaming = Midshire demo baseline", *_four(m.raw, seeds_d)),
    ]
    return {"conformance": {"patients": sum(c["n_patients"] for c in conf),
                            "violations": sum(c["n_violations"] for c in conf),
                            "by_type": {k: sum(c["by_type"].get(k, 0) for c in conf)
                                        for k in set().union(*[c["by_type"] for c in conf])}},
            "four_hour": {"mean": st.mean(four), "min": min(four), "max": max(four), "seeds": seeds},
            "areas": rows, "decomposition": steps, "decomposition_seeds": seeds_d,
            "source_four_hour_published": agg["four_hour_pct"]["value"],
            "source_four_hour_internal_basis": agg["cuh_extracts"]["weekly_performance"]["four_hour_within_pct"]["mean"]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--decomp-seeds", type=int, default=16)
    a = ap.parse_args(argv)
    r = report(a.seeds, a.decomp_seeds)
    c = r["conformance"]
    print("\nMidshire adult ED demonstrator - validation and conformance")
    print("-" * 74)
    print(f"  conformance: {c['patients']} journeys, {c['violations']} violations {c['by_type'] or ''}")
    f = r["four_hour"]
    print(f"  four-hour (eligible adults, {len(f['seeds'])} weeks): {f['mean']:.1f}% "
          f"(range {f['min']:.1f}-{f['max']:.1f})")
    print(f"  source trust, all ages: published {r['source_four_hour_published']}% (Type 1); "
          f"internal basis {r['source_four_hour_internal_basis']}%  - not a target for Midshire")
    print("-" * 74)
    print(f"  {'area':<18}{'model LOS':>11}{'source':>9}{'ratio':>8}{'model/day':>11}{'source/day':>12}")
    for row in r["areas"]:
        ratio = f"{row['ratio']:.2f}x" if row["ratio"] else "  -"
        src = f"{row['source_los_median']:.0f}" if row["source_los_median"] else "-"
        sv = f"{row['source_per_day_internal_basis']:.1f}" if row["source_per_day_internal_basis"] else "-"
        mv = f"{row['model_los_median']:.0f}" if row["model_los_median"] else "-"
        print(f"  {row['area']:<18}{mv:>11}{src:>9}{ratio:>8}{row['model_per_day']:>11.1f}{sv:>12}")
    print("  (LOS = median minutes from arrival to leaving for patients who used the area; SDEC is")
    print("   measured from entering SDEC. Source figures: June 2026 TID medians; volumes Feb-Jul 2026")
    print("   on the source trust's internal counting basis, which runs ~11% above the published one.)")
    print("-" * 74)
    print(f"  How the four-hour figure moves from the source model to Midshire "
          f"({len(r['decomposition_seeds'])} simulated weeks each, same seeds; +/- = standard error):")
    prev = None
    for name, v, se in r["decomposition"]:
        d = "" if prev is None else f"  ({v - prev:+.1f})"
        print(f"    {v:5.1f}% +/-{se:3.1f}  {name}{d}")
        prev = v
    print("  Steps smaller than about twice the standard errors are within simulation noise.")
    print("  Children share imaging, streaming and the bed model in the source build, so removing")
    print("  them frees capacity that adults then use; that, the real mental-health admission rate,")
    print("  and the illustrative SDEC streaming are the measured steps above. None is validated")
    print("  against a real adult-only department.")
    return 0 if c["violations"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
