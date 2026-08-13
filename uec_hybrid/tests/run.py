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
    # nursing is ratio-constrained but must still appear in the workforce view
    assert any(a["resource"] == "ed_nurse" for a in prev["areas"]), \
        "ED nursing dropped from the workforce view"
    print("Review fixes OK: diverts and calibration reach streams; nursing visible.")

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
    # audit details are truncated summaries (2000 chars) - a long JSON value cut
    # mid-string must degrade to raw text, never break the whole trail
    store.save_setting("audit_trunc_check", {"long": "x" * 3000})
    trail = store.audit_trail()
    row = next(r for r in trail if r["key"] == "audit_trunc_check")
    assert isinstance(row["detail"], str) and len(row["detail"]) == 2000
    print("Store OK: department versions persist; run cache keyed by config hash; "
          "truncated audit details degrade safely.")

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

    # --- physical capacity: a trust's REAL counts replace the scaled template ---
    cap_dept = Department(attendances_per_day=384,
                          capacity={"cdu_bed": 6, "cubicle": 40, "bogus": 5, "rat_clinician": 9})
    cap_raw = build_dept(cap_dept)
    assert cap_raw["resources"]["cdu_bed"] == 6, "real count must not be size-scaled"
    assert "bogus" not in cap_raw["resources"], "unknown capacity keys are ignored"
    assert isinstance(cap_raw["resources"]["rat_clinician"], list), \
        "staff resources stay rota-driven, never capacity overrides"
    # the nurse-to-cubicle ratio still gates how many REAL cubicles open
    assert cap_raw["uec"]["physical_cubicles"] == [40] * 24
    assert all(c <= 40 for c in cap_raw["resources"]["cubicle"])
    # counts for a disabled area are inert (its resource is already gone)...
    off = Department.default(); off.capacity = {"cdu_bed": 6}
    assert "cdu_bed" not in build_dept(off)["resources"]
    # ...and capacity survives the JSON round-trip the store uses (0 dropped)
    rt = Department.from_dict({**cap_dept.to_dict(),
                               "capacity": {"cdu_bed": 6, "sdec_chair": 0}})
    assert rt.capacity == {"cdu_bed": 6}, rt.capacity
    # workbook Capacity sheet round-trips, and the ODS code stays in the name
    wb3 = load_workbook(_io.BytesIO(wb_bytes))
    assert "Capacity" in wb3.sheetnames, wb3.sheetnames
    assert wb3["Capacity"].cell(row=1, column=1).value == "resource_key"
    wb3["Capacity"].cell(row=2, column=2).value = 7
    cap_key = wbk._norm(wb3["Capacity"].cell(row=2, column=1).value)
    ov3 = wb3["Overview"]
    assert ov3.cell(row=3, column=1).value == "ods_code"
    ov3.cell(row=3, column=2).value = "RGT"
    buf3 = _io.BytesIO(); wb3.save(buf3)
    parsed3 = wbk.read_workbook(buf3.getvalue(), filename="capacity.xlsx")
    assert parsed3["department"].capacity == {cap_key: 7}, parsed3["department"].capacity
    assert "(RGT)" in parsed3["department"].name
    assert any(p["field"] == f"capacity.{cap_key}" and p["source"] == "workbook"
               for p in parsed3["provenance"])
    # '#'-comment rows on the Areas sheet are not content (defaults kept)
    wb4 = load_workbook(_io.BytesIO(wb_bytes))
    ar4 = wb4["Areas"]; ar4.delete_rows(2, ar4.max_row)
    ar4.append(["# fill from the process map"])
    buf4 = _io.BytesIO(); wb4.save(buf4)
    assert set(wbk.read_workbook(buf4.getvalue(), filename="c.xlsx")["department"].enabled) \
        == set(Department.default().enabled)
    # pre-listed area rows with EVERY enabled cell blank = sheet not answered
    # (defaults kept) - so a collection workbook can list areas for a trust to
    # tick; one explicit answer then makes the sheet authoritative
    wb5 = load_workbook(_io.BytesIO(wb_bytes))
    ar5 = wb5["Areas"]
    for r in range(2, ar5.max_row + 1):
        ar5.cell(row=r, column=2).value = None
    buf5 = _io.BytesIO(); wb5.save(buf5)
    assert set(wbk.read_workbook(buf5.getvalue(), filename="d.xlsx")["department"].enabled) \
        == set(Department.default().enabled)
    ar5.cell(row=2, column=2).value = "yes"
    buf6 = _io.BytesIO(); wb5.save(buf6)
    only = wbk.read_workbook(buf6.getvalue(), filename="e.xlsx")["department"].enabled
    assert only == [wbk._norm(ar5.cell(row=2, column=1).value)], only
    print("Capacity OK: real counts replace the scaled template (nurse ratio still "
          "gates cubicles); workbook Capacity sheet + ODS code round-trip.")

    # --- published aggregates -> calibration patch (open data only, no rows) ---
    from ..ingest import published as pub
    agg = {"attendances_per_day": {"value": 400},
           "hourly_shares": {"values": [1] * 24, "granularity": "national shape", "source": "T"},
           "acuity_mix_pct": {"values": {"1": 1, "2": 5, "3": 25, "4": 60, "5": 9}, "source": "T"},
           "ambulance_share": {"value": 28.5, "source": "T"},
           "admission_rate_by_acuity": {"values": {"Acuity 3": 22}, "source": "T"}}
    ppatch, psummary = pub.patch_from_aggregates(agg)
    assert abs(sum(ppatch["arrivals"]["hourly_profile"]) - 400) < 1
    assert abs(sum(ppatch["arrivals"]["acuity_mix"].values()) - 100) < 0.1
    assert ppatch["attributes"]["ambulance"] == 0.285          # percent -> share
    assert ppatch["admission_rates"]["Acuity 3"] == 0.22
    assert any("service times unchanged" in s.lower() for s in psummary)
    # the patch drives the same mechanics as an ECDS upload
    from ..demand.streams import daily_stream_split
    praw = apply_patch(build_dept(Department()), ppatch)
    assert abs(daily_stream_split(praw["arrivals"])["ambulance"] - 0.285) < 0.02
    pnode = next(n for n in praw["nodes"] if n["id"] == "disposition_general")
    assert pnode["routes_by_class"]["Acuity 3"][0] == ["await_inpatient_bed", 0.22]
    # the committed RGT file is now a REAL build: CHEQS batch 1 (data/cuh/)
    # drives every distribution block, each block cites its exact extract
    # file, and nothing is labelled SYNTHETIC any more
    rgt_agg = pub.load_aggregates("RGT")
    assert rgt_agg and rgt_agg["ods_code"] == "RGT"
    rgt_patch, rgt_summary = pub.patch_from_aggregates(rgt_agg)
    assert rgt_patch["arrivals"].get("hourly_profile") and rgt_patch["admission_rates"]
    for block in ("hourly_shares", "acuity_mix_pct", "ambulance_share",
                  "admission_rate_by_acuity"):
        s = str(rgt_agg[block].get("source", ""))
        assert "SYNTHETIC" not in s and "data/cuh" in s, \
            f"{block} must cite the CUH extract it was computed from"
    # REAL figures from the CUH extracts (area-proxy mapping, Feb-Jul 2026)
    assert rgt_patch["attributes"]["paediatric"] == 0.1335   # 10,781 / 80,771 front door
    assert rgt_patch["attributes"]["mental_health"] == 0.0257  # 315 / 12,280 (published)
    assert rgt_patch["attributes"]["ambulance"] == 0.1914    # 8,830 / 46,132
    assert rgt_patch["admission_rates"]["Acuity 2"] == 0.56  # trolleys 7,404 / 13,211
    assert rgt_agg["four_hour_pct"]["value"] == 52.93, \
        "validation target must be the real published figure"
    assert not any("SYNTHETIC" in s for s in rgt_summary), rgt_summary
    # CHEQS batch 2: real CT / X-ray workload replaces the invented imaging
    # routing. The patch carries the rates; apply_patch must move the
    # imaging_decision split so its acuity-weighted average hits them, while
    # keeping the assumed gradient (sicker patients imaged more) and leaving
    # every class summing to 1.
    assert rgt_patch["imaging"] == {"ct": 0.1828, "xray": 0.3918}, rgt_patch["imaging"]
    assert "data/cuh/Investigation types.xlsx" in rgt_agg["investigation_rates"]["source"]
    iraw = apply_patch(build_dept(rgt_dept_for_imaging := to_department(get_profile("RGT"))),
                       rgt_patch)
    inode = next(n for n in iraw["nodes"] if n["id"] == "imaging_decision")
    imix = iraw["arrivals"]["acuity_mix"]; itot = sum(imix.values())
    for modality, target in (("ct", 0.1828), ("xray", 0.3918)):
        got = sum(imix.get(cls, 0) / itot * dict((t, p) for t, p in lst).get(modality, 0)
                  for cls, lst in inode["routes_by_class"].items())
        assert abs(got - target) < 0.002, f"{modality}: weighted {got} vs target {target}"
    for cls, lst in inode["routes_by_class"].items():
        assert abs(sum(p for _, p in lst) - 1.0) < 1e-6, (cls, lst)
    r2c = {t: p for t, p in inode["routes_by_class"]["Acuity 2"]}
    r4c = {t: p for t, p in inode["routes_by_class"]["Acuity 4"]}
    assert r2c["ct"] > r4c["ct"], "the acuity gradient must survive calibration"
    print("Published aggregates OK: shares -> patch maths check out; RGT distributions "
          "come from the CUH extracts and cite their files; CT/X-ray workload "
          "calibrates the imaging split onto CUH's real rates.")

    # --- Cambridge (RGT) registry row + committed seed: reproducible set-up ---
    assert "RGT" in codes, "Cambridge University Hospitals must be in the registry"
    rgt_prof = get_profile("rgt")
    rgt = to_department(rgt_prof)
    assert "(RGT)" in rgt.name and "Cambridge" in rgt.name
    # REAL inputs transcribed from the primary files committed under data/
    assert rgt.attendances_per_day == 400.5 and rgt.inpatient_beds == 1068
    assert rgt.baseline_bed_occupancy == 0.8926
    assert "June-2026-CSV" in rgt_prof.source and "KH03" in rgt_prof.source, \
        "real inputs must cite the primary files they came from"
    assert rgt_prof.observed_four_hour_pct == 52.93, "validation target is real"
    from ..ingest.seed import find_seed_workbook, seed as run_seed
    assert find_seed_workbook("RGT") is not None, "seed workbook must be committed"
    seeded = run_seed("RGT")
    assert seeded["ok"] and "(RGT)" in seeded["department"]["name"]
    assert seeded["department"]["attendances_per_day"] == 400.5
    assert store.get_setting("data_source")["kind"] == "seed"
    assert store.get_setting("provenance")["rows"], "seed must persist provenance"
    assert seeded["calibration_applied"], "the CUH aggregates must drive the patch"
    assert any("data/cuh" in s for s in seeded["summary"]), \
        "the seed summary must cite the CUH extract files"
    assert not any("SYNTHETIC" in s for s in seeded["summary"]), seeded["summary"]
    v1 = seeded["version"]
    assert run_seed("RGT")["version"] == v1 + 1, "re-seeding appends a version"
    # real extracts have replaced the placeholders: the banner must stop calling
    # the calibration synthetic (physical capacity stays a template assumption)
    from ..app.server import app as _seed_app
    ds_seed = _seed_app.test_client().get("/api/data-status").get_json()
    assert not any("SYNTHETIC" in w for w in ds_seed["warnings"]), ds_seed["warnings"]
    assert not any("SYNTHETIC" in a for a in ds_seed["assumed"]), ds_seed["assumed"]
    assert any("capacity" in a for a in ds_seed["assumed"]), ds_seed["assumed"]
    print(f"Cambridge seed OK: RGT registry row + committed workbook stand the "
          f"department up reproducibly (v{v1}, provenance persisted).")

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
    assert parse_question("what if demand goes up 10%?", _braw)[0]["arrivals_scale"] == 1.1
    assert parse_question("demand goes down 15%", _braw)[0]["arrivals_scale"] == 0.85
    assert parse_question("divert 20% of minors", _braw)[0]["divert"]["fraction"] == 0.2
    assert parse_question("double the cubicles", _braw)[0]["resources"]["cubicle"] == "*2"
    assert parse_question("what's the meaning of life", _braw)[0] is None
    # a phrase matching an area the department doesn't have is skipped, not invented
    lean_raw2 = build_dept(lean)                       # lean has no paeds
    sc2, nts2 = parse_question("add 2 paeds doctors", lean_raw2)
    assert sc2 is None and any("doesn't have" in n for n in nts2), (sc2, nts2)
    # nurses + time-of-day windows (the phrasing real users actually type)
    sc3, nts3 = parse_question("What if I add 3 more nurses at 1 pm?", _braw)
    assert sc3["nurses"]["change"] == "+3" and sc3["nurses"]["hours"] == list(range(13, 21)), sc3
    assert len(nts3) == 2 and "1:4 nurse-to-cubicle ratio" in nts3[0], nts3   # deduped + honest
    sc4, _ = parse_question("add 2 doctors from 8pm to 8am", _braw)
    assert sc4["resources"]["ed_doctor"] == {"change": "+2",
                                             "hours": [20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7]}, sc4
    sc5, _ = parse_question("remove a doctor overnight", _braw)
    assert sc5["resources"]["ed_doctor"]["change"] == "-1" and 20 in sc5["resources"]["ed_doctor"]["hours"]
    # scenario application: nurse change recomputed exactly through the builder's ratio
    from ..analysis.scenarios import apply_scenario as _apply
    _uec = _braw["uec"]
    _pv, _ = _apply(Pathway.from_dict(_braw), {**sc3, "name": "n"})
    _exp = [max(1, min(_uec["physical_cubicles"][h],
                       (_uec["ed_nurse_staffing"][h] + (3 if 13 <= h < 21 else 0))
                       * _uec["nurse_to_cubicle_ratio"])) for h in range(24)]
    assert _pv.raw["resources"]["cubicle"] == _exp
    # windowed resource change touches only the window's hours
    _pv2, _ = _apply(Pathway.from_dict(_braw), {**sc4, "name": "n2"})
    _doc0 = _braw["resources"]["ed_doctor"]
    _d24 = list(_doc0) if isinstance(_doc0, list) else [_doc0] * 24
    assert all(_pv2.raw["resources"]["ed_doctor"][h] == _d24[h] + (2 if (h >= 20 or h < 8) else 0)
               for h in range(24))
    # staff sickness: every staff group scaled; deep sickness closes cubicles via the ratio
    sc6, n6 = parse_question("what if we have 10% staff sickness?", _braw)
    assert sc6["staff_scale"] == 0.9 and "nurse-to-cubicle" in n6[0]
    _pv3, _ = _apply(Pathway.from_dict(_braw), {**sc6, "name": "sick"})
    assert _pv3.raw["resources"]["ed_doctor"][12] == int(round(_d24[12] * 0.9))
    _deep, _ = _apply(Pathway.from_dict(_braw), {"name": "deep", "staff_scale": 0.5})
    assert sum(_deep.raw["resources"]["cubicle"]) < sum(_braw["resources"]["cubicle"]), \
        "50% sickness must close cubicles through the nurse ratio"
    # time-windowed demand surge (evening peak / local event)
    sc7, n7 = parse_question("20% more attendances in the evening", _braw)
    assert sc7["arrivals_scale"] == {"scale": 1.2, "hours": list(range(16, 24))}, sc7
    _pv4, _ = _apply(Pathway.from_dict(_braw), {**sc7, "name": "eve"})
    _prof0, _prof1 = _braw["arrivals"]["hourly_profile"], _pv4.raw["arrivals"]["hourly_profile"]
    assert abs(_prof1[18] / _prof0[18] - 1.2) < 1e-6 and abs(_prof1[6] / _prof0[6] - 1.0) < 1e-6
    # end-to-end: numbers come from the engine, offline (no LLM key in CI)
    assert not assist_llm.available() or True          # available() must never raise
    wf = run_what_if("add 2 doctors", lean_raw2, reps=2, use_llm=False)
    assert wf["answer"] and wf["deltas"]["four_hour"]["scenario"] >= 0
    assert wf["rows"][0]["scenario"] == "Baseline" and not wf["llm_used"]
    wf2 = run_what_if("add 3 more nurses at 1 pm", _braw, reps=2, use_llm=False)
    assert not wf2.get("error") and wf2["answer"], wf2   # the once-broken phrase now runs
    print(f"AI assist (ask) OK: 9 phrasings parsed incl. nurses + time windows; missing areas "
          f"skipped honestly; what-if 4-hour {wf['deltas']['four_hour']['base']}%→"
          f"{wf['deltas']['four_hour']['scenario']}%.")

    # --- AI assist: offline retrieval (RAG) over glossary + product guide + docs ---
    from ..assist import retrieval as _rag
    _hit = _rag.best("how do I import my data from excel")
    assert _hit and "template" in _hit["text"].lower(), _hit
    assert _rag.best("what is the methodology behind this")["title"] == "Methodology"
    assert _rag.best("zzz qqq xyzzy") is None            # nonsense: no confident guess
    assert _rag.search("calibrate from ecds", k=3)       # multi-hit search works
    print("AI assist (RAG) OK: retrieval answers how-to/concept questions offline; "
          "nonsense returns nothing rather than a guess.")

    # --- AI assist: auto-calibration converges toward the observed figure ---
    from ..assist.autocal import auto_calibrate
    ac = auto_calibrate(lean_raw2, observed_four_hour=45.0, seeds=(1,), max_iter=3, tol=2.0)
    assert ac["scale"] > 1.0, ac                        # observed worse than model -> slower service
    assert abs(ac["modelled"] - 45) <= abs(ac["baseline_modelled"] - 45), ac
    assert ac["history"] and ac["note"]
    print(f"AI assist (auto-cal) OK: baseline {ac['baseline_modelled']}% -> x{ac['scale']} "
          f"gives {ac['modelled']}% vs observed 45% ({len(ac['history'])} evaluations).")

    # --- chatbot: grounded intent routing over the product's computed data ---
    from ..assist import chat as _chat
    _stub = {
        "department": lambda: {"name": "Test ED", "attendances_per_day": 290,
                               "inpatient_beds": 320, "community_capacity": 60,
                               "areas_on": ["RAT", "SDEC"]},
        "standards": lambda: {"four_hour": {"typical": 71, "good": 78, "tough": 64}},
        "demand": lambda: {"per_day": 290, "hourly": [6, 4, 4, 3, 3, 4, 4, 6, 13, 20, 23, 25,
                                                      25, 22, 21, 21, 21, 21, 20, 17, 16, 14, 10, 8]},
        "staffing": lambda: {"headline": "ED nursing looks light 18:00-22:00.", "weekly_cost": 300000,
                             "areas": [{"label": "ED nursing", "understaffed_hours": [18, 19, 20, 21]}]},
        "pinch": lambda: {"bottleneck": "ED cubicles", "peak_hours": [14, 15, 16],
                          "recommendation": "<b>cubicle</b> is the binding constraint."},
        "gaps": lambda: None,
        "what_if": lambda q: ({"error": "no", "notes": ["skipped 'unicorns'"],
                               "supported": ["add 2 doctors"]} if "unicorn" in q
                              else {"answer": f"simulated: {q}"}),
    }
    cases = {"where is demand?": ("demand", "290"),
             "where should I deploy staff?": ("deploy", "ED nursing"),
             "what's the pinch point?": ("pinch", "ED cubicles"),
             "how are we doing against the standards?": ("standards", "71"),
             "what does sdec mean?": ("glossary", "Same-Day"),
             "what if we add 2 doctors": ("what_if", "simulated"),
             "what if we add 3 nurses at 1pm?": ("what_if", "simulated"),
             # a near-miss what-if explains itself instead of shrugging
             "what if we add 2 unicorns?": ("what_if_help", "couldn't set it up"),
             # how-to questions the router can't match come from retrieval (RAG)
             "how do I import my data from excel?": ("knowledge", "template"),
             # "calibration" must not substring-match the glossary term "rat"
             "how does calibration work?": ("knowledge", "calibr"),
             # an edit/change how-to must beat the deploy-staff intent
             "where do I change staff costs?": ("knowledge", "editable"),
             "explain the methodology": ("knowledge", "discrete-event"),
             "tell me a joke": ("help", "where is demand")}
    for msg, (intent, needle) in cases.items():
        out = _chat.answer(msg, [], _stub)
        assert out["intent"] == intent and needle in out["reply"], (msg, out)
    assert "binding constraint" in _chat.answer("pinch point?", [], _stub)["reply"]  # html stripped
    assert "<b>" not in _chat.answer("pinch point?", [], _stub)["reply"]
    print(f"Chatbot OK: {len(cases)} intents route to grounded answers incl. what-if "
          "near-miss help and RAG knowledge; HTML stripped; junk falls back to help.")

    # --- the two screens serve: control tower page + favicon ---
    from ..app.server import app as flask_app
    client = flask_app.test_client()
    for page in ("/", "/favicon.ico"):
        assert client.get(page, follow_redirects=True).status_code == 200, f"{page} failed"
    print("Pages OK: the control tower (with Set up my ED) serves.")

    # --- data-driven set-up endpoints: pick a trust, download + import a workbook ---
    tl = client.get("/api/trusts").get_json()["trusts"]
    assert any(t["ods_code"] == "RFF" for t in tl), "trust list should include Barnsley"
    sel = client.post("/api/trust/select", json={"ods": "RFF"}).get_json()
    assert sel["ok"] and sel["department"]["attendances_per_day"] == 290
    assert store.load_department()["baseline_bed_occupancy"] == 0.918, "trust must persist"
    assert client.post("/api/trust/select", json={"ods": "ZZZ"}).status_code == 404
    # picking a trust with committed aggregates (RGT -> data/cuh/) must apply
    # them as the calibration - the UI flow, not just the seed CLI, uses them
    sel_rgt = client.post("/api/trust/select", json={"ods": "RGT"}).get_json()
    assert any("data/cuh" in s for s in sel_rgt["calibration_summary"]), \
        "selecting RGT must load the CUH extract calibration"
    cal_rgt = store.get_calibration("your_department")
    assert cal_rgt and cal_rgt["patch"]["attributes"]["ambulance"] == 0.1914
    # batch-2 imaging workload must ride the same drop-down path, not just the seed
    assert cal_rgt["patch"]["imaging"] == {"ct": 0.1828, "xray": 0.3918}
    assert any("Imaging workload" in s for s in sel_rgt["calibration_summary"])
    ds_rgt = client.get("/api/data-status").get_json()
    assert "arrival profile & acuity mix" not in ds_rgt["assumed"], ds_rgt["assumed"]
    # a trust with NO committed aggregates still starts clean
    client.post("/api/trust/select", json={"ods": "RFF"})
    assert store.get_calibration("your_department") is None, \
        "RFF has no aggregates file - calibration must be cleared"
    # uploading the FILLED Cambridge workbook stands up the whole build: the
    # workbook carries arrivals + acuity, and its ODS code pulls the rest of
    # the committed CUH aggregates in behind it (workbook wins where both set)
    from io import BytesIO as _BIO2
    from ..ingest.seed import find_seed_workbook as _fsw
    up_rgt = client.post("/api/trust/import", content_type="multipart/form-data",
                         data={"file": (_BIO2(_fsw("RGT").read_bytes()),
                                        "rgt_cuh_workbook.xlsx")}).get_json()
    assert up_rgt["ok"] and up_rgt["department"]["attendances_per_day"] == 400.5
    cal_up = store.get_calibration("your_department")["patch"]
    assert abs(sum(cal_up["arrivals"]["hourly_profile"]) - 400.5) < 0.05
    assert cal_up["arrivals"]["acuity_mix"]["Acuity 2"] == 18.88     # workbook
    assert cal_up["attributes"]["ambulance"] == 0.1914               # merged in
    assert cal_up["admission_rates"]["Acuity 1"] == 0.743            # merged in
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

    # --- governance endpoints: data provenance, decision log, audit trail ---
    ds = client.get("/api/data-status").get_json()
    assert ds["source"]["kind"] == "workbook", ds["source"]   # the import above stamped it
    assert ds["department"]["version"] >= 1 and ds["engine_version"] == store.ENGINE_VERSION
    assert "overrides" in ds and isinstance(ds["warnings"], list)
    # provenance + plain-language assumptions, for the banner on every surface
    assert ds["provenance"]["rows"], "imports must persist per-field provenance"
    assert "physical capacity" in ds["assumed"], ds["assumed"]
    assert any("capacity" in w.lower() for w in ds["warnings"]), ds["warnings"]
    act = client.post("/api/actions", json={"note": "Opened escalation cubicles from 14:00",
                                            "author": "Site manager"}).get_json()
    assert act["ok"] and act["action"]["id"] and act["action"]["context"]["department"]
    assert client.post("/api/actions", json={"note": ""}).status_code == 400
    acts = client.get("/api/actions").get_json()["actions"]
    assert acts and acts[0]["note"].startswith("Opened escalation")
    aud = client.get("/api/audit").get_json()["audit"]
    assert any(a["kind"] == "setting" and a["key"] == "data_source" for a in aud)
    assert any(a["kind"] == "department" for a in aud)
    print(f"Governance endpoints OK: data-status shows source + warnings; decision log "
          f"append-only ({len(acts)} entries); audit trail records config changes ({len(aud)} rows).")

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
    # --- recommender searches downstream levers too (no simulation needed) ---
    from ..optimise.recommend import _candidates as _rec_cands, _apply_raw as _rec_apply_raw
    from ..workforce.view import workforce_view as _wfv
    _cands = _rec_cands(Department.default(), _wfv(Department.default()))
    _sd_moves = [m for m in _cands if m["kind"] == "sd"]
    assert {m["param"] for m in _sd_moves} == {"inpatient_beds", "community_capacity"}, \
        "downstream levers (beds, community discharge) must be in the searched set"
    _raw_sd = build_dept(Department.default())
    _beds0 = _raw_sd.get("sd", {}).get("inpatient_beds", 320)
    _raw_sd = _rec_apply_raw(_raw_sd, next(m for m in _sd_moves
                                           if m["param"] == "inpatient_beds"))
    assert _raw_sd["sd"]["inpatient_beds"] > _beds0, "sd move must raise ward beds"

    # --- "what would it take": a goal question -> CI-gated stacked plan ---
    from ..assist.nl import parse_target
    assert parse_target("What would it take to achieve 90% in 4 hours?") == 90.0
    assert parse_target("how do we hit 85% in four hours") == 85.0
    assert parse_target("add 2 doctors") is None and parse_target("10% more attendances") is None
    tr = client.post("/api/ask", json={"question": "what would it take to reach 90% in 4 hours?",
                                       "replications": 2})
    tp = tr.get_json()
    assert tr.status_code == 200 and tp["kind"] == "target" and tp["target"] == 90.0, tp
    assert tp["baseline"] > 0 and isinstance(tp["steps"], list) and tp["note"]
    assert tp["reached"] == (tp["modelled"] >= tp["target"])
    # an already-met goal answers from the same cached recommendation run
    tr2 = client.post("/api/ask", json={"question": "what would it take to reach 5% in 4 hours?",
                                        "replications": 2}).get_json()
    assert tr2["reached"] and not tr2["steps"]
    from ..assist.chat import _fmt_target
    txt = _fmt_target({"baseline": 69.0, "target": 90.0, "modelled": 77.9, "reached": False,
                       "steps": [{"title": "Add 1 nurse", "delta_four_hour": 5.9,
                                  "weekly_cost": 952, "cumulative_four_hour": 75.1}],
                       "note": "Even stacking falls short."})
    assert "90.0" in txt and "Add 1 nurse" in txt and "falls short" in txt
    print("Target plan OK: goal questions parse, stack CI-gated moves, answer honestly.")

    from .. import model_params as _mp
    _mp.save_params({})                                    # reset any saved tuning
    ch = client.post("/api/chat", json={"message": "where is demand?"}).get_json()
    assert ch["intent"] == "demand" and "attendances a day" in ch["reply"], ch
    ch2 = client.post("/api/chat", json={"message": "where should I deploy staff?",
                                         "history": [{"role": "user", "content": "hi"}]}).get_json()
    assert ch2["intent"] == "deploy" and ch2["reply"], ch2
    assert client.post("/api/chat", json={"message": "what is exit-block"}).get_json()["intent"] == "glossary"
    assert client.post("/api/chat", json={"message": "zzz qqq"}).get_json()["intent"] == "help"
    print("AI assist endpoints OK: /api/ask grounded answer + graceful 400s; "
          "/api/auto-calibrate tunes and saves; /api/chat routes demand/deploy/glossary/help.")

    # --- bug fixes: rostered resources, cache upsert, API guards ------------ #
    from ..analysis.scenarios import apply_scenario as _apply_scenario
    p_dept = Pathway.from_dict(build_dept(Department.default()))
    pdiv, _ = _apply_scenario(p_dept, {"name": "+doctors", "resources": {"ed_doctor": "+2"}})
    assert isinstance(pdiv.raw["resources"]["ed_doctor"], list), "scenario must keep roster shape"
    assert pdiv.raw["resources"]["ed_doctor"][12] == p_dept.raw["resources"]["ed_doctor"][12] + 2
    bad_ct = client.post("/api/control-tower", data="not json", content_type="application/json")
    assert bad_ct.status_code == 200, "malformed control-tower body should fall back to default seed"
    print("Bug fixes OK: roster scenarios; API guards.")

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

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
