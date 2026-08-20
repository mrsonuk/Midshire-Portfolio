"""
Validate a built department against the trust's OWN observed data, area by area.

Every defect found in the Cambridge build was found by this comparison, and
none of them by the test suite - the model was internally consistent and green
throughout while resus ran at 1.77x and majors trolleys at 0.35x of the volumes
and stays the trust actually sees. Headline KPIs agreed the whole time, through
compensating errors.

So: after ANY change to routing, capacity, service times or the engine, run

    python3 -m uec_hybrid.validation.against_trust RGT

and read the per-area block, not just the KPIs.

Two traps this module exists to stop you walking into, both of which produced
"defects" that were really comparison errors:

* **Measurement basis.** ``twelve_hour`` is ``los > 720`` - measured FROM
  ARRIVAL. Comparing it to a decision-to-admit figure makes a matching model
  look three times too bad. The targets below name their basis.
* **Which function computes it.** ``kpis()`` and ``uec_metrics()`` return
  different measures; a metric missing from one is not a broken metric.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# node -> the trust extract's area name
AREA_OF = {"ed_resus": "resus", "ed_cubicles": "majors_trolleys",
           "ed_ambulatory": "majors_ambulant", "utc_minor_illness": "minors",
           "paeds_assessment": "paeds"}


def _targets(ods: str) -> dict:
    """Observed per-area volumes and stays, from the committed trust file."""
    path = DATA / f"{ods.strip().lower()}_published.json"
    if not path.exists():
        raise SystemExit(f"no published aggregates for {ods}")
    j = json.load(open(path))
    ex = j.get("cuh_extracts") or {}
    tid = ex.get("time_in_department_june_2026_mins") or {}
    wk = (ex.get("weekly_performance") or {})
    return {
        "los": {n: tid[a][0] for n, a in AREA_OF.items() if a in tid},
        "four_hour": j.get("four_hour_pct", {}).get("value"),
        # the FROM-ARRIVAL basis, which is what the model computes
        "twelve_hour_from_arrival": (wk.get("twelve_hour_over_pct") or {}).get("mean"),
        "handover_45": j.get("ambulance_handover_over_30_min_pct", {}).get("within_45_min_pct"),
    }


def compare(ods: str = "RGT", seeds=(2, 3, 4, 5, 6), volumes: dict | None = None) -> dict:
    """Run the trust's saved department and compare it with its own figures."""
    from ..app.server import app
    from ..platform import store
    from ..department.config import Department
    from ..department.builder import build as build_dept
    from ..demand.ecds_seam import apply_patch
    from ..des.pathway import Pathway
    from ..coupling.cosim import run_cosim
    from ..analysis.metrics import kpis, uec_metrics

    client = app.test_client()
    r = client.post("/api/trust/select", json={"ods": ods})
    if r.status_code != 200:                      # a 500 here used to pass silently
        raise SystemExit(f"/api/trust/select failed: {r.status_code} {r.get_data(as_text=True)[:200]}")
    dept = Department.from_dict(store.load_department())
    cal = store.get_calibration("your_department") or {"patch": {}}
    raw = apply_patch(build_dept(dept), cal["patch"])

    tgt = _targets(ods)
    acc = {"four": [], "twelve": [], "lwbs": [], "hand": []}
    los = {n: [] for n in AREA_OF}
    vol = {n: [] for n in AREA_OF}
    for seed in seeds:
        p = Pathway.from_dict(raw)
        res = run_cosim(p, seed=seed)
        ev, pt = res["events"], res["patients"]
        k, u = kpis(res, p), uec_metrics(res, p)
        acc["four"].append(k.get("four_hour", 0.0))
        acc["twelve"].append(k.get("twelve_hour", 0.0))
        acc["lwbs"].append(k.get("lwbs", 0.0))
        acc["hand"].append(u.get("ambulance_handover_45", 0.0))
        days = max(1e-9, (p.sim_duration - p.warmup) / 1440.0)
        idx = pt.set_index("pid")
        for node in AREA_OF:
            pids = ev[ev["stage"] == node]["pid"].unique()
            vol[node].append(len(pids) / days)
            sub = idx.reindex(pids).dropna(subset=["exit"])
            if len(sub):
                los[node].append(float((sub["exit"] - sub["arrival"]).median()))
    mean = statistics.mean
    return {"kpis": {k: mean(v) for k, v in acc.items()},
            "los": {n: mean(v) for n, v in los.items() if v},
            "volume": {n: mean(v) for n, v in vol.items() if v},
            "targets": tgt, "observed_volume": volumes or {}}


def main(argv=None):
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    ods = (args[0] if args else "RGT").upper()
    out = compare(ods)
    t = out["targets"]
    print(f"\n{ods}: model vs the trust's own observed figures")
    print("-" * 66)
    print(f"  {'4-hour %':<32}{out['kpis']['four']:>8.1f}{(t['four_hour'] or 0):>10.2f}")
    print(f"  {'12-hour % (FROM ARRIVAL)':<32}{out['kpis']['twelve']:>8.1f}"
          f"{(t['twelve_hour_from_arrival'] or 0):>10.2f}")
    print(f"  {'handover <=45 min %':<32}{out['kpis']['hand']:>8.1f}{(t['handover_45'] or 0):>10.2f}")
    print(f"  {'LWBS %':<32}{out['kpis']['lwbs']:>8.1f}{'-':>10}")
    print("-" * 66)
    print(f"  {'area':<22}{'model':>10}{'trust':>10}{'ratio':>9}")
    for node, obs in t["los"].items():
        m = out["los"].get(node)
        if m:
            flag = "" if 0.75 <= m / obs <= 1.35 else "   <-- OFF"
            print(f"  {AREA_OF[node]:<22}{m:>10.0f}{obs:>10.0f}{m / obs:>8.2f}x{flag}")
    print("\n  (per-area VOLUME ratios sit below 1.0 by the published-versus-internal")
    print("   counting basis; check the trust's data log before calling that an error)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
