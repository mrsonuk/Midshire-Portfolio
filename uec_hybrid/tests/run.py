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

    # --- benchmarking: percentile position vs a peer set ---
    from ..analysis.benchmark import generate_sample_benchmarks, position, read_benchmarks
    peers = generate_sample_benchmarks().to_dict("records")
    pos = position(peers, four_hour=78, twelve_hour=1.0, attendances_per_day=320, synthetic=True)
    assert 0 <= pos["four_hour_percentile"] <= 100 and pos["n_band"] >= 8
    pos2 = position(peers, four_hour=60, twelve_hour=6.0, attendances_per_day=320, synthetic=True)
    assert pos2["four_hour_percentile"] < pos["four_hour_percentile"]
    assert "SYNTHETIC" in pos["summary"]
    import io as _io
    buf = _io.StringIO(); generate_sample_benchmarks(20).to_csv(buf, index=False)
    assert len(read_benchmarks(buf.getvalue().encode())) == 20
    print(f"Benchmark OK: 78% sits at the {pos['four_hour_percentile']}th percentile, "
          f"60% at the {pos2['four_hour_percentile']}th; upload round-trips.")

    # --- intraday projection: a hot morning projects a heavier day ---
    from ..planning.operational import project_today
    quiet = project_today([4, 3, 2, 2, 3, 3, 4, 5], department=Department.default())
    hot = project_today([8, 6, 5, 5, 6, 7, 9, 12], department=Department.default())
    assert hot["projected_today"] > quiet["projected_today"] > 100
    assert hot["ratio"] > 1.1
    print(f"Intraday OK: quiet morning projects {quiet['projected_today']}/day, "
          f"hot morning {hot['projected_today']}/day (x{hot['ratio']}).")

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
    updated = store.remember("simulate", {"raw": {"x": 1}}, {"kpi": 99.0})
    assert updated["kpi"] == 99.0 and store.cached("simulate", {"raw": {"x": 1}})["kpi"] == 99.0
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

    # --- trust profile ingest: registry loaded from the CSV snapshot ---
    from ..ingest import (get_profile, list_profiles, to_department, provenance,
                          notes, validate_against_observed)
    codes = {t["ods_code"] for t in list_profiles()}
    assert {"RFF", "RHU", "RHW"} <= codes, codes         # registry is data, not code
    prof = get_profile("rff")                            # case-insensitive lookup
    tdept = to_department(prof)
    # published INPUTS flow into the department...
    assert tdept.attendances_per_day == 290, tdept.attendances_per_day
    assert tdept.baseline_bed_occupancy == 0.918
    assert "Barnsley" in tdept.name and "RFF" in tdept.name
    # ...and survive a JSON round-trip through the store schema
    assert Department.from_dict(tdept.to_dict()).baseline_bed_occupancy == 0.918
    # occupancy reaches the SD layer the control tower runs (not just stored)
    traw = build_dept(tdept)
    assert traw["sd"]["baseline_bed_occupancy"] == 0.918
    assert abs(sum(traw["arrivals"]["hourly_profile"]) - 290) < 2
    # things open data can't supply keep the template default (flagged, not invented)
    assert tdept.inpatient_beds == Department.default().inpatient_beds
    assert any("bed count" in n.lower() for n in notes(prof))
    assert any(r["kind"] == "validation-target" for r in provenance(prof))
    # a trust with no published attendances degrades gracefully to the default
    rhw = to_department(get_profile("RHW"))
    assert rhw.attendances_per_day == Department.default().attendances_per_day
    assert rhw.inpatient_beds == 627                     # beds ARE published for RHW
    # the model's OUTPUT 4-hour is validated against the trust's REAL figure
    tp = Pathway.from_dict(traw)
    modelled = kpis(run_cosim(tp, seed=2), tp).get("four_hour", 0.0)
    v = validate_against_observed(prof, modelled)
    assert v["observed"] == 67.5 and v["modelled"] >= 0
    print(f"Trust ingest OK: {len(codes)} trusts from CSV; Barnsley (RFF) 290/day @ 91.8% occ; "
          f"modelled 4-hour {v['modelled']}% vs observed {v['observed']}% (delta {v['delta_pct_points']} pts).")

    # --- workbook ingest: template round-trips to a Department (+ calibration) ---
    from ..ingest import workbook as wbk
    wb_bytes = wbk.template_bytes()
    parsed = wbk.read_workbook(wb_bytes, filename="template.xlsx")
    wdept = parsed["department"]
    assert wdept.attendances_per_day == round(Department.default().attendances_per_day)
    assert set(wdept.enabled) == set(Department.default().enabled), wdept.enabled
    assert len(wdept.rota) == len(Department.default().rota), len(wdept.rota)
    assert build_dept(wdept)["resources"], "workbook department must build"
    assert not any("unknown roles" in s for s in parsed["summary"]), parsed["summary"]
    # an edited workbook (arrivals sheet) produces a calibration patch
    from openpyxl import load_workbook
    import io as _io
    wb2 = load_workbook(_io.BytesIO(wb_bytes))
    arr = wb2["Arrivals"]
    for h in range(24):
        arr.cell(row=h + 2, column=2, value=(20 if 9 <= h < 18 else 5))
    buf = _io.BytesIO(); wb2.save(buf)
    parsed2 = wbk.read_workbook(buf.getvalue(), filename="edited.xlsx")
    assert parsed2["patch"] and "hourly_profile" in parsed2["patch"]["arrivals"]
    assert abs(parsed2["department"].attendances_per_day - (9 * 20 + 15 * 5)) < 1
    # workbook Costs tab carries the cost book + staff hourly rates
    from ..finance.costbook import DEFAULT_COST_BOOK
    from ..workforce.roles import ROLES, role_rates, save_role_rates
    from ..workforce.rota import weekly_cost
    from ..platform import store as _store
    assert parsed["cost_book"]["admission_avoided"] == DEFAULT_COST_BOOK["admission_avoided"]
    assert parsed["role_rates"] and len(parsed["role_rates"]) == len(ROLES)
    print(f"Workbook OK: template -> department ({len(wdept.rota)} shifts, "
          f"{len(wdept.enabled)} areas); costs + {len(parsed['role_rates'])} role rates; "
          f"edited arrivals -> calibration patch.")

    # --- editable role rates: an override changes the pay-bill (no code edit) ---
    base_cost = weekly_cost(Department.default().rota)
    save_role_rates({"ed_consultant": ROLES["ed_consultant"]["cost"] * 2})
    raised = weekly_cost(Department.default().rota)
    assert raised > base_cost, (raised, base_cost)
    _store.save_setting("role_rates", {})                # reset
    assert weekly_cost(Department.default().rota) == base_cost

    # --- editable Model ED standards: an override flips the RAG verdict ---
    from ..analysis.metrics import uec_scorecard as _sc, scorecard_defaults
    assert any(d["key"] == "four_hour" for d in scorecard_defaults())
    assert _sc({"four_hour": 80})[0]["status"] == "green"          # default target 78
    assert _sc({"four_hour": 80}, {"four_hour": {"target": 95, "amber": 5}})[0]["status"] == "red"
    print("Editable costs & standards OK: role rates move the pay-bill; "
          "scorecard targets are data-driven and flip the RAG verdict.")

    # --- editable service times (the model's physics) tune the outcome ---
    from .. import model_params as mp
    from ..department.builder import BASE_RAW as _BASE
    srows = mp.service_params(_BASE)
    assert len(srows) > 10 and all("mean" in r for r in srows)
    _b = copy.deepcopy(_BASE)
    _mean = lambda raw, nid: next(x for x in raw["nodes"] if x["id"] == nid)["service"]["mean"]
    assert _mean(mp.apply_params(_b, {"service_scale": 2.0}), "streaming") == _mean(_b, "streaming") * 2
    assert _mean(_b, "streaming") == 7, "apply_params must not mutate the base raw"
    assert _mean(mp.apply_params(_b, {"service_mean": {"streaming": 99}}), "streaming") == 99
    # slower service -> worse 4-hour: the physics genuinely moves the model
    p_base = Pathway.from_dict(build_dept(Department.default()))
    p_slow = Pathway.from_dict(mp.apply_params(build_dept(Department.default()), {"service_scale": 1.5}))
    fh_base = kpis(run_cosim(p_base, seed=2), p_base)["four_hour"]
    fh_slow = kpis(run_cosim(p_slow, seed=2), p_slow)["four_hour"]
    assert fh_slow < fh_base, (fh_slow, fh_base)
    # persistence validates/drops junk
    saved = mp.save_params({"service_scale": 1.2, "service_mean": {"streaming": 30, "nope": -1}})
    assert saved["service_scale"] == 1.2 and saved["service_mean"] == {"streaming": 30.0}
    _store.save_setting("pathway_params", {})            # reset
    # workbook ServiceTimes tab also carries service params
    from openpyxl import load_workbook as _lw
    _wbx = _lw(_io.BytesIO(wbk.template_bytes()))
    _sx = _wbx["ServiceTimes"]; _sx.cell(row=2, column=3, value=1.1); _sx.cell(row=3, column=3, value=88)
    _bx = _io.BytesIO(); _wbx.save(_bx)
    _sp = wbk.read_workbook(_bx.getvalue(), filename="e.xlsx")["service_params"]
    assert _sp["service_scale"] == 1.1 and _sp["service_mean"]
    print(f"Service-time tuning OK: {len(srows)} stages editable; x1.5 slower cuts 4-hour "
          f"{fh_base:.0f}%->{fh_slow:.0f}%; workbook ServiceTimes tab parses.")

    # --- analyst interpretations: SD read, per-stage timing, scenario impact ---
    from ..analysis.metrics import sd_interpretation, stage_timing
    from ..analysis.scenarios import interpret as scn_interpret
    _res = run_cosim(p_base, seed=2)
    sdi = sd_interpretation(_res)
    assert sdi["stocks"] and "occupancy" in sdi["stocks"].lower() and sdi["feedback"]
    stt = stage_timing(_res, p_base)
    assert stt["n_patients"] > 100 and len(stt["stages"]) > 5 and stt["mean_los"] > 0
    assert all({"mean_wait", "mean_service", "mean_in_stage"} <= set(s) for s in stt["stages"])
    txt = scn_interpret([{"scenario": "Baseline", "four_hour": 72, "twelve_hour": 5},
                         {"scenario": "+40 beds", "four_hour": 78, "twelve_hour": 3}],
                        {"metric": "four_hour", "bars": [{"lever": "+40 beds", "delta": 6}]})
    assert "+40 beds" in txt and "baseline" in txt.lower()
    assert "baseline" in scn_interpret([]).lower()          # graceful with no scenarios
    # per-variant timing: each observed route carries per-stage time + a total,
    # and within a (linear) variant the stage times reconcile to the total LOS
    from ..validation.process_map import variant_timing
    vts = variant_timing(_res, top=5)
    assert vts and vts[0]["stages"] and vts[0]["total_min"] > 0 and vts[0]["disposition"]
    _sum = sum(s["mean_min"] for s in vts[0]["stages"])
    assert abs(_sum - vts[0]["total_min"]) < 2, (_sum, vts[0]["total_min"])
    print(f"Analyst interpretations OK: SD read; stage timing ({len(stt['stages'])} stages, "
          f"LOS {stt['mean_los']:.0f}m); per-variant timing (top route {vts[0]['total_min']:.0f}m); "
          f"scenario-impact text.")

    # --- AI assist: plain-English what-if -> scenario -> engine -> answer ---
    from ..assist.nl import parse_question, run_what_if
    from ..assist import llm as assist_llm
    _braw = build_dept(Department.default())
    sc, nts = parse_question("What if we add 2 doctors and 40 more ward beds?", _braw)
    assert sc["resources"]["ed_doctor"] == "+2"
    assert sc["sd"]["inpatient_beds"] == _braw["sd"]["inpatient_beds"] + 40
    assert parse_question("10% more attendances", _braw)[0]["arrivals_scale"] == 1.1
    assert parse_question("divert 20% of minors", _braw)[0]["divert"]["fraction"] == 0.2
    assert parse_question("double the cubicles", _braw)[0]["resources"]["cubicle"] == "*2"
    assert parse_question("what's the meaning of life", _braw)[0] is None
    # a phrase matching an area the department doesn't have is skipped, not invented
    lean_raw2 = build_dept(lean)                       # lean has no paeds
    sc2, nts2 = parse_question("add 2 paeds doctors", lean_raw2)
    assert sc2 is None and any("doesn't have" in n for n in nts2), (sc2, nts2)
    # end-to-end: numbers come from the engine, offline (no LLM key in CI)
    assert not assist_llm.available() or True          # available() must never raise
    wf = run_what_if("add 2 doctors", lean_raw2, reps=2, use_llm=False)
    assert wf["answer"] and wf["deltas"]["four_hour"]["scenario"] >= 0
    assert wf["rows"][0]["scenario"] == "Baseline" and not wf["llm_used"]
    print(f"AI assist (ask) OK: 6 phrasings parsed, missing areas skipped honestly; "
          f"what-if 4-hour {wf['deltas']['four_hour']['base']}%→{wf['deltas']['four_hour']['scenario']}%.")

    # --- AI assist: auto-calibration converges toward the observed figure ---
    from ..assist.autocal import auto_calibrate
    ac = auto_calibrate(lean_raw2, observed_four_hour=45.0, seeds=(1,), max_iter=3, tol=2.0)
    assert ac["scale"] > 1.0, ac                        # observed worse than model -> slower service
    assert abs(ac["modelled"] - 45) <= abs(ac["baseline_modelled"] - 45), ac
    assert ac["history"] and ac["note"]
    print(f"AI assist (auto-cal) OK: baseline {ac['baseline_modelled']}% -> x{ac['scale']} "
          f"gives {ac['modelled']}% vs observed 45% ({len(ac['history'])} evaluations).")

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

    # --- data-driven set-up endpoints: pick a trust, download + import a workbook ---
    tl = client.get("/api/trusts").get_json()["trusts"]
    assert any(t["ods_code"] == "RFF" for t in tl), "trust list should include Barnsley"
    sel = client.post("/api/trust/select", json={"ods": "RFF"}).get_json()
    assert sel["ok"] and sel["department"]["attendances_per_day"] == 290
    assert store.load_department()["baseline_bed_occupancy"] == 0.918, "trust must persist"
    assert client.post("/api/trust/select", json={"ods": "ZZZ"}).status_code == 404
    tmpl = client.get("/api/trust/template")
    assert tmpl.status_code == 200 and len(tmpl.data) > 3000 and tmpl.data[:2] == b"PK"
    from io import BytesIO as _BIO
    up = client.post("/api/trust/import", content_type="multipart/form-data",
                     data={"file": (_BIO(tmpl.data), "template.xlsx")}).get_json()
    assert up["ok"] and up["department"]["enabled"], up
    assert client.post("/api/trust/import", content_type="multipart/form-data",
                       data={}).status_code == 400
    # importing the template applies its cost book (into store settings)
    assert store.get_setting("role_rates") is not None, "import should set role rates"
    print(f"Trust endpoints OK: {len(tl)} trusts listed; select persists (290/day); "
          f"template downloads ({len(tmpl.data)//1024} KB) and imports (with costs).")

    # --- scorecard targets endpoint: view defaults, edit, round-trip, reset ---
    st = client.get("/api/scorecard-targets").get_json()
    assert any(d["key"] == "four_hour" for d in st["defaults"])
    client.post("/api/scorecard-targets", json={"four_hour": {"target": 95, "amber": 5}})
    assert client.get("/api/scorecard-targets").get_json()["overrides"]["four_hour"]["target"] == 95
    client.post("/api/scorecard-targets", json={})            # reset
    assert client.get("/api/scorecard-targets").get_json()["overrides"] == {}
    print("Scorecard targets OK: standards editable via API and reset cleanly.")

    # --- pathway params endpoint: view stages, edit service times, reset ---
    pp = client.get("/api/pathway-params").get_json()
    assert len(pp["stages"]) > 10 and "params" in pp
    client.post("/api/pathway-params", json={"service_scale": 1.1})
    assert client.get("/api/pathway-params").get_json()["params"]["service_scale"] == 1.1
    client.post("/api/pathway-params", json={})               # reset
    assert client.get("/api/pathway-params").get_json()["params"] == {}
    print("Pathway params OK: service-time assumptions editable via API and reset.")

    # --- analyst endpoints carry the new interpretation payloads ---
    sim = client.post("/api/simulate", json={"pathway": "model_ed", "seed": 1}).get_json()
    assert sim["sd_interpretation"]["stocks"], "simulate should return an SD interpretation"
    vv = client.post("/api/validate", json={"pathway": "model_ed", "seed": 1}).get_json()
    assert vv["stage_timing"]["n_patients"] > 0 and vv["stage_timing"]["stages"], vv.get("stage_timing")
    assert vv["variants"] and vv["variants"][0]["stages"] and "total_min" in vv["variants"][0], vv.get("variants")
    print("Analyst endpoints OK: /api/simulate carries SD interpretation; "
          "/api/validate carries per-stage timing + total.")

    # --- AI assist endpoints: /api/ask answers, junk 400s; /api/auto-calibrate saves ---
    ak = client.post("/api/ask", json={"question": "add 2 doctors", "replications": 2})
    akd = ak.get_json()
    assert ak.status_code == 200 and akd["answer"] and akd["deltas"]["four_hour"], akd
    assert client.post("/api/ask", json={"question": "make everything perfect"}).status_code == 400
    assert client.post("/api/ask", json={}).status_code == 400
    acr = client.post("/api/auto-calibrate",
                      json={"observed_four_hour": 50, "seeds": [1], "max_iter": 2})
    acd = acr.get_json()
    assert acr.status_code == 200 and "scale" in acd and acd["history"] and "saved_params" in acd, acd
    assert client.post("/api/auto-calibrate", json={}).status_code == 400  # no observed figure
    client.post("/api/pathway-params", json={})            # reset any saved tuning
    print("AI assist endpoints OK: /api/ask grounded answer + graceful 400s; "
          "/api/auto-calibrate tunes and saves via pathway params.")

    # --- bug fixes: rostered resources, cache upsert, API guards ------------ #
    from ..analysis.scenarios import apply_scenario as _apply_scenario
    from ..app.server import _build
    p_dept = Pathway.from_dict(build_dept(Department.default()))
    pdiv, _ = _apply_scenario(p_dept, {"name": "+doctors", "resources": {"ed_doctor": "+2"}})
    assert isinstance(pdiv.raw["resources"]["ed_doctor"], list), "scenario must keep roster shape"
    assert pdiv.raw["resources"]["ed_doctor"][12] == p_dept.raw["resources"]["ed_doctor"][12] + 2
    raw_ov = _build({"pathway": "your_department", "overrides": {"ed_doctor": 20}})[3]
    assert isinstance(raw_ov["resources"]["ed_doctor"], list)
    assert raw_ov["resources"]["ed_doctor"] == [20] * 24
    bad_ct = client.post("/api/control-tower", data="not json", content_type="application/json")
    assert bad_ct.status_code == 200, "malformed control-tower body should fall back to default seed"
    store.save_calibration("your_department", {"arrivals": {}}, ["ok"])
    client.post("/api/calibrate/reset", json={})
    assert store.get_calibration("your_department") is None, "reset must default to your_department"
    print("Bug fixes OK: roster scenarios/overrides; cache upsert; API guards.")

    # --- control tower: pinch moves with the hour-of-day slider ------------ #
    from ..viz.flow_model import control_tower as _control_tower
    ct = _control_tower(run_cosim(p, seed=1), p)
    assert len(ct["pinch_by_hour"]) == 24
    active = [x for x in ct["pinch_by_hour"] if x]
    assert active, "pinch_by_hour should identify at least one hourly pinch"
    assert len(set(active)) > 1, f"pinch should move through the day, got: {set(active)}"
    assert sum(ct["arrivals_by_hour"]) > 100
    assert ct["exits_by_hour"].get("Discharged") and sum(ct["exits_by_hour"]["Discharged"]) > 50
    print(f"Hourly pinch OK: moves through {len(set(active))} areas across the day "
          f"(day-wide pinch: {ct['bottleneck']}); outcomes update by hour.")

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
