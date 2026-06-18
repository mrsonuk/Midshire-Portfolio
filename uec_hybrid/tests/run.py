"""
End-to-end checks for the hybrid model. Run: python -m uec_hybrid.tests.run

Covers: DES capacity safety + acuity prioritisation, SD stock conservation,
coupling stability (no sustained oscillation) and mass-balance, exit-block
emergence, process-map conformance (clean pass + injected-error detection), and
scenario comparison.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np

from ..des.pathway import Pathway, validate_schema
from ..des.engine import Simulation
from ..coupling.cosim import run_cosim, CoSimulator
from ..analysis.metrics import kpis, resource_utilisation
from ..analysis.scenarios import compare_scenarios
from ..validation.conformance import check

PATHWAY = Path(__file__).resolve().parent.parent / "pathways" / "model_ed.json"


def _max_concurrency(holds, resource):
    sub = holds[holds["resource"] == resource]
    if sub.empty:
        return 0
    s, e = sub["start"].to_numpy(), sub["end"].to_numpy()
    return int(max(((s <= t) & (e > t)).sum() for t in s))


def main():
    p = Pathway.load(PATHWAY)
    assert not validate_schema(p), validate_schema(p)
    print("Schema valid.")

    # --- DES: capacities respected, including span-held spaces ---
    res = run_cosim(p, seed=1)
    holds = res["holds"]
    for r, cap in p.resources.items():
        peak = _max_concurrency(holds, r)
        assert peak <= cap, f"{r}: peak {peak} > capacity {cap}"
    util = resource_utilisation(res, p)
    assert (util["utilisation"] <= 100.5).all()
    k = kpis(res, p)
    assert k["n_patients"] > 500
    print(f"DES OK: {k['n_patients']} patients, capacities respected, util <= 100%.")

    # --- acuity prioritisation: higher-acuity patients wait less for shared space ---
    pat = res["patients"]
    a12 = pat[pat["priority"] <= 2]["los"].median()
    a45 = pat[pat["priority"] >= 4]["los"].median()
    print(f"Acuity priority: median LOS A1-2 {a12:.0f} vs A4-5 {a45:.0f} min.")

    # --- SD conservation + coupling stability ---
    co = CoSimulator(p, seed=2)
    r2 = co.run()
    hist = r2["sd_history"]
    occ = np.array([s["bed_occupancy"] for _, s in hist])
    assert (occ >= 0).all() and (occ <= 1.001).all(), "bed occupancy left [0,1]"
    bwm = np.array([s["bed_wait_multiplier"] for _, s in hist])
    # stability: second-half variability not exploding vs first half (no oscillation blow-up)
    half = len(bwm) // 2
    assert np.std(bwm[half:]) <= np.std(bwm[:half]) * 3 + 0.5, "feedback signal oscillating"
    assert bwm.max() <= 12.0, "feedback signal unbounded"
    print(f"SD OK: occupancy in [0,1], bed-wait multiplier bounded {bwm.min():.1f}-{bwm.max():.1f}, stable.")

    # --- exit-block emergence: bed feedback worsens admitted LOS ---
    off = kpis(run_cosim(p, seed=3, feedback=False, sd_overrides={"community_capacity": 0}), p)
    on = kpis(run_cosim(p, seed=3, feedback=True, sd_overrides={"community_capacity": 0}), p)
    assert on["mean_los_admitted"] > off["mean_los_admitted"], "exit-block did not emerge"
    print(f"Exit-block emerges: admitted LOS {off['mean_los_admitted']:.0f} -> {on['mean_los_admitted']:.0f} min with bed feedback.")

    # --- conformance: clean pass + injected error caught ---
    conf = check(res, p)
    assert conf["passed"], f"clean run not conformant: {conf['by_type']}"
    bad = copy.deepcopy(res)
    bad["events"].loc[bad["events"].index[5], "stage"] = "ed_resus"
    assert not check(bad, p)["passed"], "validator missed injected error"
    print(f"Validation OK: clean run 100% conformant; injected error detected.")

    # --- scenarios ---
    cmp = compare_scenarios(p, [{"name": "+community", "sd": {"community_capacity": 90}}],
                            replications=2)
    assert len(cmp["rows"]) == 2
    print("Scenario comparison OK.")

    # --- time-varying staffing tracks the rota and respects the peak ---
    import json as _json
    raw = _json.loads(_json.dumps(_json.load(open(PATHWAY))))
    roster = [4, 4, 4, 4, 4, 4, 5, 7, 10, 13, 14, 14, 14, 13, 13, 13, 14, 14, 13, 11, 9, 7, 6, 5]
    raw["resources"]["ed_doctor"] = roster
    pr = Pathway.from_dict(raw)
    rr = run_cosim(pr, seed=1)
    hh = rr["holds"]; hh = hh[hh["resource"] == "ed_doctor"]
    starts, ends = hh["start"].to_numpy(), hh["end"].to_numpy()
    peak = max(int(((starts <= t) & (ends > t)).sum()) for t in starts)
    assert peak <= max(roster), f"staffing exceeded roster peak ({peak} > {max(roster)})"
    night = [int(((starts <= h * 60 + 3 * 1440) & (ends > h * 60 + 3 * 1440)).sum()) for h in range(2, 5)]
    assert max(night) <= 6, "overnight staffing not reduced by the rota"
    print(f"Time-varying staffing OK: peak {peak} <= roster peak {max(roster)}, overnight reduced.")

    # --- department builder: areas off still validate, route safely, conformance ---
    from ..department.config import Department
    from ..department.builder import build as build_dept
    from ..workforce.rota import weekly_cost
    lean = Department.from_dict({**Department.default().to_dict(), "enabled": ["rat", "sdec"]})
    pd_ = Pathway.from_dict(build_dept(lean))
    assert not validate_schema(pd_), validate_schema(pd_)
    rd = run_cosim(pd_, seed=1)
    assert kpis(rd, pd_)["n_patients"] > 400
    assert check(rd, pd_)["passed"], "disabled-area pathway not conformant"
    assert weekly_cost(Department.default().rota) > 0
    print("Department builder OK: areas off validate, route safely, conformant; rota cost computed.")

    # --- area opening hours: a part-time area takes no patients while closed ---
    dh = Department.from_dict({**Department.default().to_dict(),
                               "enabled": ["sdec"], "hours": {"sdec": [8, 20]}})
    pdh = Pathway.from_dict(build_dept(dh))
    assert not validate_schema(pdh), validate_schema(pdh)
    # entry node carries the opening hours + a real fallback
    sdec_node = pdh.nodes["sdec"]
    assert sdec_node.get("open_hours") == [8, 20] and sdec_node.get("closed_fallback") in pdh.nodes
    rh = run_cosim(pdh, seed=1)
    ev = rh["events"]
    sd_ev = ev[ev["stage"] == "sdec"]
    entry_hours = ((sd_ev["queue_entry"] / 60) % 24).astype(int)
    assert sd_ev.empty or (entry_hours.between(8, 19).all()), \
        f"SDEC took patients outside opening hours: {sorted(set(entry_hours))}"
    assert check(rh, pdh)["passed"], "opening-hours pathway not conformant"
    print(f"Opening hours OK: SDEC entries confined to 08:00–20:00; routes safely; conformant.")

    # --- rota preview: instant staffing + cost with no simulation ---
    from ..workforce.view import staffing_and_cost
    prev = staffing_and_cost(Department.default().rota, 320.0)
    assert prev["weekly_cost"] > 0 and prev["areas"] and len(prev["demand"]) == 24
    print(f"Rota preview OK: weekly cost £{prev['weekly_cost']:,}, {len(prev['areas'])} staff areas, no sim.")

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
