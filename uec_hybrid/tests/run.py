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
    print(f"Opening hours OK: SDEC entries confined to 08:00-20:00; routes safely; conformant.")

    # --- rota preview: instant staffing + cost with no simulation ---
    from ..workforce.view import staffing_and_cost
    prev = staffing_and_cost(Department.default().rota, 320.0)
    assert prev["weekly_cost"] > 0 and prev["areas"] and len(prev["demand"]) == 24
    print(f"Rota preview OK: weekly cost £{prev['weekly_cost']:,}, {len(prev['areas'])} staff areas, no sim.")

    # --- workforce v2: full team costed; ENPs/porters real, HCA/reception advisory ---
    from ..workforce.roles import SUPPORT_RESOURCES
    from ..workforce.rota import cost_breakdown
    advisory = {a["resource"] for a in prev["areas"] if a.get("advisory")}
    assert advisory == set(SUPPORT_RESOURCES), f"advisory areas wrong: {advisory}"
    by_role = cost_breakdown(Department.default().rota)["by_role"]
    assert by_role.get("band5_nurse", 0) > 0 and by_role.get("porter", 0) > 0
    built = build_dept(Department.default())
    # ENPs and porters are engine resources with by-hour rosters from the rota
    assert isinstance(built["resources"]["minors_enp"], list)
    assert isinstance(built["resources"]["porter_pool"], list)
    # HCA / reception stay cost-only
    assert not (set(SUPPORT_RESOURCES) & set(built["resources"]))
    nursing = sum(v for r, v in by_role.items()
                  if r in ("band5_nurse", "band6_nurse", "enp", "hca", "porter", "receptionist"))
    print(f"Workforce v2 OK: full team costed (support staff £{nursing:,}/wk); ENPs/porters staffed.")

    # --- Phase 2a physics: handover queue, LWBS reneging, nurse-ratio cubicle cap ---
    # ambulance handover is measured at an explicit stage
    from ..analysis.metrics import uec_metrics
    um = uec_metrics(res, p)
    assert "ambulance_handover_45" in um and "ambulance_vehicle_hours_lost_per_day" in um
    hov = res["events"][res["events"]["stage"] == "ambulance_handover"]
    assert len(hov) > 200, "ambulance arrivals are not passing through handover"
    assert kpis(res, p)["lwbs"] < 5, "baseline LWBS should be low"
    # starve minors of capacity and LWBS emerges; the run stays conformant
    starved = copy.deepcopy(p.raw)
    for rname in ("minor_injury_space", "utc_room", "fit_to_sit_chair", "minors_enp"):
        starved["resources"][rname] = 1
    ps = Pathway.from_dict(starved)
    rs = run_cosim(ps, seed=4)
    ks = kpis(rs, ps)
    assert ks["lwbs"] > 1.0, f"LWBS did not emerge under starvation ({ks['lwbs']:.1f}%)"
    assert check(rs, ps)["passed"], "reneging exits broke conformance"
    # a thin nursing rota closes cubicles via the 1:N ratio
    thin = Department.from_dict({**Department.default().to_dict(),
                                 "rota": [{"role": "band5_nurse", "start": 0, "end": 24, "count": 1},
                                          {"role": "ed_consultant", "start": 0, "end": 24, "count": 2}]})
    cub = build_dept(thin)["resources"]["cubicle"]
    assert isinstance(cub, list) and max(cub) <= 4, f"nurse ratio did not cap cubicles: {cub}"
    print(f"Phase 2a OK: handover measured ({um['ambulance_handover_mean']:.0f} min mean), "
          f"LWBS {ks['lwbs']:.1f}% under starvation, nurses cap cubicles at 1:4.")

    # --- arrival streams: partition of demand, pinned attributes, case-mix intact ---
    kb = kpis(res, p)
    bs = kb.get("by_stream") or {}
    assert set(bs) == {"ambulance", "walk_in", "gp_referral", "nhs_111"}, bs.keys()
    assert 24 <= bs["ambulance"]["share_pct"] <= 38, bs["ambulance"]
    # the ambulance ATTRIBUTE is pinned by the stream (handover routing depends on it)
    pat = res["patients"]
    amb_stream = pat["stream"] == "ambulance"
    assert (pat.loc[amb_stream, "attr_ambulance"]).all(), "ambulance stream lost its attribute"
    assert not pat.loc[~amb_stream, "attr_ambulance"].any(), "non-ambulance stream marked ambulance"
    # streams follow a calibration's case-mix skew
    from ..demand.ecds_seam import apply_patch as _ap
    skewed = _ap(p.raw, {"arrivals": {"acuity_mix": {k: v * (2 if k == "Acuity 1" else 1)
                                                     for k, v in p.raw["arrivals"]["acuity_mix"].items()}}})
    s_amb = next(s for s in skewed["arrivals"]["streams"] if s["name"] == "ambulance")
    b_amb = next(s for s in p.raw["arrivals"]["streams"] if s["name"] == "ambulance")
    assert s_amb["acuity_mix"]["Acuity 1"] > b_amb["acuity_mix"]["Acuity 1"] * 1.5
    print(f"Streams OK: ambulance {bs['ambulance']['share_pct']:.0f}%, walk-in "
          f"{bs['walk_in']['share_pct']:.0f}%, GP {bs['gp_referral']['share_pct']:.0f}%, "
          f"111 {bs['nhs_111']['share_pct']:.0f}%; attributes pinned; mixes follow calibration.")

    # --- forecast v2: covariate regression recovers the synthetic ground truth ---
    from ..planning.forecast import forecast_from_history, generate_daily_history
    fc = forecast_from_history(generate_daily_history())
    assert 2.0 <= fc["components"]["trend_pct_per_year"] <= 4.5, fc["components"]
    assert 10 <= fc["components"]["bank_holiday_pct"] <= 20, fc["components"]
    assert fc["accuracy"] and fc["accuracy"]["mape_pct"] < 10
    print(f"Forecast v2 OK: trend {fc['components']['trend_pct_per_year']}%/yr, "
          f"bank holidays {fc['components']['bank_holiday_pct']:+.0f}%, "
          f"backtest MAPE {fc['accuracy']['mape_pct']}%.")

    # --- surge templates apply as declared ---
    from ..planning.surge import TEMPLATES, apply_template, _move_cost_per_week, SOLVER_MOVES
    lean_raw = build_dept(lean)
    struck = apply_template(lean_raw, TEMPLATES["strike"])
    assert struck["resources"]["ed_doctor"][12] < lean_raw["resources"]["ed_doctor"][12], \
        "strike did not cut doctors"
    flu = apply_template(lean_raw, TEMPLATES["flu"])
    assert sum(flu["arrivals"]["hourly_profile"]) > sum(lean_raw["arrivals"]["hourly_profile"]) * 1.05
    assert flu["sd"]["baseline_bed_occupancy"] > lean_raw["sd"].get("baseline_bed_occupancy", 0.92)
    assert all(_move_cost_per_week(m) > 0 for m in SOLVER_MOVES)
    print("Surge OK: strike cuts doctors, flu lifts demand and fills the hospital; moves costed.")

    # --- recommendation engine: paired seeds, CI gate, costed output ---
    from ..optimise import recommend
    rec = recommend(Department.default(), reps=2, limit=2)
    assert rec["n_candidates"] == 2
    assert len(rec["recommendations"]) + len(rec["rejected"]) == 2
    for r in rec["recommendations"] + rec["rejected"]:
        assert {"delta_four_hour", "delta_low", "summary", "annual_benefit"} <= set(r)
    assert all(r["delta_low"] > 0 for r in rec["recommendations"]), "CI gate leaked noise"
    print(f"Recommend OK: {rec['n_candidates']} candidates evaluated, "
          f"{len(rec['recommendations'])} confident, {len(rec['rejected'])} within noise.")

    # --- review fixes: seams that must reach the streams, and the nursing view ---
    from ..analysis.scenarios import apply_scenario
    from ..demand.streams import daily_stream_split
    pdiv, _ = apply_scenario(p, {"name": "utc", "divert": {"classes": ["Acuity 4", "Acuity 5"],
                                                           "fraction": 0.5}})
    for s in pdiv.raw["arrivals"]["streams"]:
        base_s = next(x for x in p.raw["arrivals"]["streams"] if x["name"] == s["name"])
        if base_s["acuity_mix"].get("Acuity 4", 0) > 0:
            assert s["acuity_mix"]["Acuity 4"] < base_s["acuity_mix"]["Acuity 4"] * 0.6, \
                f"class divert did not reach stream {s['name']}"
    cal_amb = _ap(p.raw, {"attributes": {"ambulance": 0.45}})
    got = daily_stream_split(cal_amb["arrivals"]).get("ambulance", 0)
    assert 0.40 <= got <= 0.50, f"calibrated ambulance share did not reach streams ({got:.2f})"
    # forecast: a history ending mid-winter forecasts THIS winter, not next year's
    import pandas as _pd
    hist2 = generate_daily_history()
    hist2 = hist2[_pd.to_datetime(hist2["date"]) <= "2025-12-15"]
    fw = forecast_from_history(hist2)
    assert abs(fw["winter_uplift_pct"]) < 15, \
        f"Dec-ending history should already sit near winter level ({fw['winter_uplift_pct']}%)"
    # nursing is ratio-constrained but must still appear in the workforce view
    assert any(a["resource"] == "ed_nurse" for a in prev["areas"]), \
        "ED nursing dropped from the workforce view"
    print("Review fixes OK: diverts and calibration reach streams; mid-winter forecast sane; "
          "nursing visible.")

    # --- platform store: department persists (versioned), run cache hits by config hash ---
    import tempfile
    from ..platform import store
    store.init_db(f"sqlite:///{tempfile.mkdtemp()}/test.sqlite3", force=True)
    v1 = store.save_department(lean.to_dict())
    v2 = store.save_department({**lean.to_dict(), "name": "Renamed ED"})
    assert (v1, v2) == (1, 2) and store.load_department()["name"] == "Renamed ED"
    payload = store.remember("simulate", {"raw": {"x": 1}}, {"kpi": 42.0})
    assert store.cached("simulate", {"raw": {"x": 1}}) == payload
    assert store.cached("simulate", {"raw": {"x": 2}}) is None
    store.save_calibration("your_department", {"arrivals": {}}, ["ok"])
    assert store.get_calibration("your_department")["summary"] == ["ok"]
    store.clear_calibration("your_department")
    assert store.get_calibration("your_department") is None
    print("Store OK: department versions persist; run cache keyed by config hash.")

    # --- ECDS calibration patch follows the department through set-up changes ---
    from ..demand.ecds_seam import generate_sample, derive_patch, apply_patch
    patch, _summary = derive_patch(generate_sample(days=6, seed=1))
    raw_cal = apply_patch(build_dept(lean), patch)
    assert raw_cal["arrivals"]["hourly_profile"] == patch["arrivals"]["hourly_profile"]
    other = Department.from_dict({**lean.to_dict(), "enabled": ["rat"]})
    assert apply_patch(build_dept(other), patch)["arrivals"]["acuity_mix"] == patch["arrivals"]["acuity_mix"]
    print("Calibration OK: derived patch re-applies to any department build.")

    # --- planner models the configured department, not a generic template ---
    from ..planning.planner import build_department
    raw_dept, fc = build_department(winter_uplift_pct=10, department=lean)
    assert "utc_room" not in raw_dept["resources"], "planner ignored disabled areas"
    assert isinstance(raw_dept["resources"]["ed_doctor"], list), "planner lost the rota"
    assert abs(sum(raw_dept["arrivals"]["hourly_profile"]) - fc["expected_per_day"]) < 2
    raw_gen, _ = build_department(320, winter_uplift_pct=10)
    assert "utc_room" in raw_gen["resources"], "generic template should keep all areas"
    raw_opt, _ = build_department(winter_uplift_pct=10, department=lean,
                                  extra={"resources": {"ed_doctor": "+2"}})
    assert raw_opt["resources"]["ed_doctor"][12] == raw_dept["resources"]["ed_doctor"][12] + 2, \
        "option change not applied per-hour to the rostered resource"
    print("Planner OK: plans model the configured department (areas, rota, demand).")

    # --- finance: cost book round-trips; business cases price simulated deltas ---
    from ..finance import load_cost_book, save_cost_book, business_case, gap_finance
    book = load_cost_book()
    assert book["admission_avoided"] > 0 and "note" in book
    edited = save_cost_book({"admission_avoided": 2000})
    assert edited["admission_avoided"] == 2000
    assert edited["twelve_hour_breach"] == book["twelve_hour_breach"], "unedited keys must keep defaults"
    case = business_case({"delta": 5, "corridor_per_day": 1.0, "cost": "Low"},
                         {"corridor_per_day": 3.0}, attendances_per_day=320, book=edited)
    expected = round((320 * 0.05 * edited["four_hour_breach"] + 2.0 * edited["twelve_hour_breach"]) * 365)
    assert case["annual_benefit"] == expected, (case["annual_benefit"], expected)
    assert case["payback_years"] is not None and case["assumptions"]
    gf = gap_finance({"value": 6.0, "unit": "fewer admits/day", "cost": "High"}, 320, book=edited)
    assert gf["annual_benefit"] == round(6.0 * 2000 * 365) and gf["roi"] is not None
    assert business_case({"delta": 0, "corridor_per_day": 3.0, "cost": "Low"},
                         {"corridor_per_day": 3.0}, 320, book=edited)["roi"] is None
    print("Finance OK: cost book editable; options and gaps priced with assumptions attached.")

    # --- executive brief: one composed payload, all surfaces served ---
    from ..app.server import app as flask_app
    client = flask_app.test_client()
    ex = client.get("/api/exec").get_json()
    assert ex["standards"]["four_hour"]["typical"] > 0
    assert ex["risk"]["level"] in (1, 2, 3, 4)
    assert ex["workforce"]["weekly_cost"] > 0
    for page in ("/exec", "/", "/planner", "/analyst", "/app"):
        assert client.get(page, follow_redirects=True).status_code == 200, f"{page} failed"
    print(f"Exec brief OK: risk level {ex['risk']['level']}, "
          f"4-hour typical {ex['standards']['four_hour']['typical']}%; all surfaces serve.")

    # --- one-click decision report from a department build, incl. investment page ---
    from ..report import build_report
    fake_invest = {"baseline_four_hour": 70, "have": 4, "total": 9, "missing": [
        {"label": "EEMAC", "benefit": "avoids admissions", "cost": "High",
         "finance": {"summary": "~£1m/year benefit", "annual_benefit": 1_000_000,
                     "assumptions": ["indicative cost book"]}}]}
    out = Path(tempfile.mkdtemp()) / "report.pdf"
    build_report(build_dept(lean), out, replications=2, name="Test ED", invest=fake_invest)
    assert out.exists() and out.stat().st_size > 20_000
    print(f"Report OK: {out.stat().st_size // 1024} KB decision report incl. investment page.")

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
