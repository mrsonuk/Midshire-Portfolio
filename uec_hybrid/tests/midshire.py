"""
Checks for the Midshire adult ED demonstrator. Run:

    python3 -m uec_hybrid.tests.midshire          (also run by uec_hybrid.tests.run)

Controlled fixtures for arithmetic and semantics; short simulations (2 observed
days, 2 replications) where behaviour has to be exercised end to end. These
prove the demonstrator does what it says; they do NOT validate it against a
real hospital (see python3 -m uec_hybrid.midshire.validate for that report).
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_COMMIT = "8dd0117e9e0d460630bfefc4fb522eadca8b2436"
# sha256 of protected Cambridge files at the source commit: the Midshire work
# must not have changed them
PROTECTED = {
    "uec_hybrid/data/rgt_published.json": "527679c4d664c103175ffedca837d831c1be74e52ad4f6778402b5658c1c077f",
    "uec_hybrid/data/seeds/rgt_cuh_workbook.xlsx": "5c2174e4161e6b3997f31abce9ca53929de588023688b026b93e6da12593be8e",
    "uec_hybrid/pathways/model_ed.json": "0bddec5825aa6bc0338fee81ad2f27b2fd2464173a858ca9f0436e4e3dfc6171",
    "uec_hybrid/data/nhs_trust_snapshot.csv": "c32e9c6331d4964b517cd3618aefb48d2f65fa6c77d76a69099820365373ee2f",
}
PROTECTED_TREES = {"data/cuh": "cb6fcbf3bc3170cd5e001a95f07794ffb162c45a"}


def _short(inputs, days=2, seeds=(101, 102)):
    """A quicker run of the same model: fewer observed days and seeds."""
    inp = copy.deepcopy(inputs)
    inp["engine"]["observed_days"] = days
    inp["engine"]["selection_seeds"] = list(seeds)
    inp["engine"]["validation_seeds"] = [9001, 9002]
    return inp


def _sequences(trace):
    st = trace["states"].sort_values(["pid", "start", "end"])
    seq = st.groupby("pid")["node"].apply(lambda s: [n for i, n in enumerate(s) if i == 0 or n != s.iloc[i - 1]])
    return seq


def check_sources():
    # 1. descends from the Cambridge source commit; protected data unchanged
    for rel, want in PROTECTED.items():
        got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert got == want, f"protected source file changed: {rel}"
    r = subprocess.run(["git", "cat-file", "-e", SOURCE_COMMIT], cwd=ROOT, capture_output=True)
    if r.returncode == 0:
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"], cwd=ROOT,
                             capture_output=True)
        assert anc.returncode == 0, "this branch must descend from the Cambridge source commit"
        for rel, tree in PROTECTED_TREES.items():
            cur = subprocess.run(["git", "rev-parse", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True)
            diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=ROOT)
            assert cur.stdout.strip() == tree and diff.returncode == 0, f"{rel} changed"
        msg = "ancestry and data/cuh tree verified"
    else:
        msg = "source commit not in this clone (shallow checkout) - file hashes verified only"
    print(f"Midshire 1 OK: protected Cambridge files unchanged; {msg}.")


def check_build_adult():
    from ..midshire import config as mcfg
    from ..midshire.build import build_model
    from ..midshire.optimise import levers_for
    base = mcfg.baseline_inputs()
    m = build_model(base)
    raw = m.raw
    txt = json.dumps({"nodes": raw["nodes"], "resources": raw["resources"], "arrivals": raw["arrivals"],
                      "uec": {k: v for k, v in raw["uec"].items() if k not in ("calibration_summary",)}})
    assert "paed" not in txt.lower(), "a paediatric element survived the adult build"
    assert not any(r["role"].startswith("paeds") for r in m.rota)
    assert not any("paed" in json.dumps(lv).lower() for lv in levers_for(base, mode="combined"))
    per_day = sum(raw["arrivals"]["hourly_profile"])
    assert abs(per_day - 347.0) < 0.5, per_day
    # demand REMOVED, not re-routed: adult demand is the all-ages volume minus the paediatric share
    f = mcfg.fixture()["cohort"]
    assert abs(f["all_ages_attendances_per_day"]["value"] * (1 - f["paediatric_share_excluded"]["value"]) - per_day) < 0.5
    print(f"Midshire 3a OK: adult build has no paediatric node, route, resource, attribute, rota row or "
          f"search lever; demand {per_day:.1f}/day (children removed, not re-routed).")
    return base, m


def check_runs(base):
    from ..midshire import config as mcfg, metrics as M
    from ..midshire.build import build_model
    from ..coupling.cosim import run_cosim
    inp = _short(base, days=3)
    m = build_model(inp)
    res = run_cosim(m.pathway, seed=101, trace=True)
    tr = res["trace"]
    # 3b: no patient is a child; the KPI denominator is every arrival in the cohort window
    assert not tr["arrivals"]["attrs"].fillna("").str.contains("paediatric").any()
    k = M.replication_kpis(tr, m.raw, 240)
    w = m.raw["uec"]["cohort_window"]
    a = tr["arrivals"]
    assert k["n_cohort"] == int(((a["arrival"] >= w[0]) & (a["arrival"] < w[1])).sum())
    print(f"Midshire 3b OK: {k['n_cohort']} adult attendances in the cohort, all counted in the denominator.")

    # 4: both SDEC routes, distinct SDEC / admission / discharge outcomes
    seq = _sequences(tr)
    joined = seq.apply(lambda s: ">".join(s))
    assert joined.str.contains("streaming>sdec").any(), "streaming -> SDEC route missing"
    assert joined.str.contains("streaming>rat>sdec").any(), "streaming -> RAT -> SDEC route missing"
    assert joined.str.contains("ambulance_handover>rat>sdec").any(), "handover -> RAT -> SDEC missing"
    sinks = set(tr["departures"]["sink"])
    assert {"discharged_sdec", "discharged", "admitted"} <= sinks, sinks
    sd = tr["states"][(tr["states"]["node"] == "sdec") & (tr["states"]["phase"] == "queue")]
    hrs = ((sd["start"] // 60) % 24).astype(int)
    o, c = inp["sdec"]["hours"]
    assert hrs.between(o, c - 1).all(), f"SDEC accepted patients while closed: {sorted(set(hrs))}"
    via_sdec_adm = joined.str.contains("sdec_outcome>decision_to_admit").any()
    assert via_sdec_adm, "SDEC admissions must go through the decision to admit"
    print("Midshire 4a OK: streaming->SDEC, streaming->RAT->SDEC and handover->RAT->SDEC all occur; "
          "SDEC takes no new patients while closed; SDEC discharge, admission and ED discharge are distinct.")

    # 5: decision to admit -> bed wait -> transfer -> departure; decisions are events
    st = tr["states"]
    dep = tr["departures"].set_index("pid")
    adm = dep[dep["sink"] == "admitted"].index
    checked = 0
    for pid in list(adm)[:200]:
        s = st[st["pid"] == pid]
        t_dta = s.loc[s["node"] == "decision_to_admit", "start"].min()
        t_bed = s.loc[s["node"] == "await_inpatient_bed", "start"].min()
        t_tr = s.loc[s["node"] == "transfer_to_ward", "start"].min()
        assert t_dta <= t_bed <= t_tr <= dep.loc[pid, "time"], pid
        checked += 1
    dta = st[st["node"].isin(["decision_to_admit", "decision_to_admit_mh"])]
    assert len(dta) and ((dta["end"] - dta["start"]) == 0).all(), "a decision must hold nobody"
    rs = M.replay_series(tr, m.raw)
    assert not any(k.startswith("decision_to_admit") for k in rs["states"]), "decisions are not occupancy"
    assert sum(rs["milestones"]["decision_to_admit"]) > 0
    print(f"Midshire 5 OK: decision to admit precedes the bed wait, transfer and departure ({checked} "
          f"admissions checked); decisions are zero-length events counted separately.")

    # 6: snapshot reconciles; carry-in and unfinished patients included
    assert rs["checks"]["conservation"] and rs["checks"]["groups_sum_to_census"]
    assert rs["census"][0] > 0, "carry-in patients from the warm-up must be in the first snapshot"
    unfinished = st["end"].isna().sum()
    assert unfinished > 0 and k["wip_end"] >= 0
    prof = M.hour_profile(tr, m.raw)
    days = prof["days"]
    arr_window = int(((a["arrival"] >= w[0]) & (a["arrival"] < w[1])).sum())
    assert abs(sum(prof["arrivals_per_hour"]) * days - arr_window) <= 2, "profile exposure mismatch"
    # every positive-duration state is in the central group table
    table = mcfg.state_table()
    pos = st[(st["end"].fillna(np.inf) - st["start"]) > 0]
    unmapped = {(n, p) for n, p in zip(pos["node"], pos["phase"]) if (n, p) not in table}
    assert not unmapped, f"states without a summary group: {unmapped}"
    print(f"Midshire 6 OK: census = initial + arrivals - departures at every 15 minutes; groups sum to "
          f"the census; {rs['census'][0]} carried in; {unfinished} unfinished intervals kept; hourly "
          f"profile normalised by {days:.0f} observed days.")

    # 6 (flow maps): the lines and boxes of the Patient flow maps come from the same intervals
    units = mcfg.flow_units()                       # raises unless every state is in exactly one box
    fl = M.flow_links(tr, m.raw)
    d = fl["days"]
    stf = M.states_frame(tr)
    keyset = [f"{n}|{p}" for n, p in zip(stf["node"], stf["phase"])]
    stf = stf.assign(key=keyset)
    worst = 0.0
    for u in units:
        sel = stf[stf["key"].isin(u.get("states", []))]
        n_at = lambda t: int(((sel["start"] <= t) & (sel["end"] > t)).sum())
        inn = sum(v for kk, v in fl["unit"].items() if kk.split(">")[1] == u["id"])
        out = sum(v for kk, v in fl["unit"].items() if kk.split(">")[0] == u["id"])
        worst = max(worst, abs((inn - out) * d - (n_at(w[1]) - n_at(w[0]))))
    assert worst < 0.5, f"a flow-map box does not balance: in - out differs from its change by {worst}"
    dep_t = tr["departures"]["time"]
    n_dep = int(((dep_t >= w[0]) & (dep_t < w[1])).sum())
    for level in ("group", "unit", "node"):
        into = sum(v for kk, v in fl[level].items() if kk.startswith("arrival>")) * d
        assert abs(into - arr_window) < 0.5, f"{level} map: arrivals {into} vs {arr_window}"
    outcomes = {"discharged", "admitted", "left_without_being_seen"}
    leave = sum(v for kk, v in fl["group"].items() if kk.split(">")[1] in outcomes) * d
    assert abs(leave - n_dep) < 0.5, f"summary map: departures {leave} vs {n_dep}"
    # the summary lines are the box-level lines added up across groups (moves inside a group drop out)
    ug = {u["id"]: u["group"] for u in units}
    summary = {o["node"]: o["summary"] for o in mcfg.fixture()["outcomes"]}
    agg = {}
    for kk, v in fl["unit"].items():
        s, t = kk.split(">")
        gs, gt = ug.get(s, s), ug.get(t, summary.get(t, t))
        if gs != gt:
            agg[f"{gs}>{gt}"] = agg.get(f"{gs}>{gt}", 0.0) + v
    assert set(agg) == set(fl["group"]) and all(abs(agg[kk] - fl["group"][kk]) < 1e-9 for kk in agg), "summary lines disagree with the detail lines"
    assert fl["group"].get("diagnostics>treatment", 0) > 0, "returns from diagnostics must be drawn"
    # the typical-day boxes add up to the typical-day census
    for hh in range(24):
        tot = sum(v[hh] for v in prof["states_avg"].values())
        assert abs(tot - prof["census_avg"][hh]) < 1e-6, f"typical-day boxes do not sum to the census at {hh}:00"
    # the Selected day figures: each day's patients, the same definitions as the week, adding up to it
    from ..midshire.runner import THRESHOLDS
    ds = M.day_summaries(tr, m.raw, THRESHOLDS)
    assert len(ds) == inp["engine"]["observed_days"] and sum(x["n_cohort"] for x in ds) == k["n_cohort"]
    wk = sum(x["four_hour"] * x["n_cohort"] for x in ds) / k["n_cohort"]
    assert abs(wk - k["four_hour"]) < 1e-9, "the days add up to the week"
    assert all(abs(x["within"][THRESHOLDS.index(240)] - x["four_hour"]) < 1e-9 for x in ds)
    # what a scenario changes, in words, from its inputs
    from ..midshire.packages import apply_package, describe_changes
    fxl = {l["id"]: l for l in mcfg.fixture()["search"]["levers"]}
    rat, _ = apply_package(inp, [fxl["rat_day"]])
    assert describe_changes(inp, rat) == ["Add one senior RAT clinician, 10:00 to 22:00, every day."]
    assert describe_changes(inp, inp) == ["No changes from the baseline."]
    print(f"Midshire 6 OK (flow maps): {len(units)} map boxes partition the states; every box's patients in - "
          f"out equals its change in occupancy; arrivals and departures match at all three levels; summary "
          f"lines are the detail lines added up ({len(fl['group'])} routes, including returns from diagnostics).")
    return m, res


def check_patient_metrics():
    from ..midshire import metrics as M
    # 7: controlled fixture - three patients, known intervals
    trace = {
        "arrivals": pd.DataFrame([(1, 0.0, "Acuity 3", "walk_in", ""), (2, 10.0, "Acuity 2", "walk_in", ""),
                                  (3, 20.0, "Acuity 2", "ambulance", "ambulance")],
                                 columns=["pid", "arrival", "acuity", "stream", "attrs"]),
        "states": pd.DataFrame([
            (1, "streaming", "queue", 0.0, 30.0), (1, "streaming", "service", 30.0, 40.0),
            (1, "ed_cubicles", "queue", 40.0, 100.0), (1, "ed_cubicles", "service", 100.0, 200.0),
            (2, "streaming", "queue", 10.0, 20.0), (2, "streaming", "service", 20.0, 25.0),
            (2, "disposition", "service", 25.0, 400.0),
            (3, "ambulance_handover", "queue", 20.0, 80.0), (3, "ambulance_handover", "service", 80.0, np.nan)],
            columns=["pid", "node", "phase", "start", "end"]),
        "departures": pd.DataFrame([(1, 200.0, "discharged"), (2, 400.0, "discharged")], columns=["pid", "time", "sink"]),
        "end": 500.0, "warmup": 0.0}
    raw = {"warmup_minutes": 0, "sim_duration_minutes": 500, "target_minutes": 240,
           "uec": {"cohort_window": [0, 100]}}
    k = M.replication_kpis(trace, raw, 240)
    assert k["n_cohort"] == 3
    # durations 200, 390, unfinished (480 elapsed > 240): 1 of 3 within 240
    assert abs(k["four_hour"] - 100 / 3) < 1e-9, k["four_hour"]
    assert k["duration_median"] == 390.0, k["duration_median"]       # censored ranked longest
    # total waiting: p1 = 30 + 60 = 90; p2 = 10 + 375 (results/decision is waiting) = 385;
    # p3 = 60, unfinished (ranked longest) -> median 385
    assert k["total_wait_median"] == 385.0, k["total_wait_median"]
    assert k["wip_end"] == 1 and k["handover_45"] == 0.0
    assert M.summarise([]) is None and M.summarise([None, None]) is None
    assert M._quantile_censored(np.array([10.0, np.inf, np.inf]), 0.5) is None, "median among unfinished must be unavailable"
    print("Midshire 7 OK: duration and total waiting are per-patient (union of waiting intervals, not "
          "stage averages); unfinished patients ranked longest; no observations -> not available.")


def check_rota():
    from ..workforce.rota import (validate_rota, clean_shift, RotaError, staffing_by_hour, staffing_by_week,
                                  hours_of_week, rota_from_csv, rota_to_csv)
    # 9: overnight belongs to the start day; day patterns; rejects; blank != 0; zero stays zero
    night = {"role": "band5_nurse", "start": 20, "end": 8, "count": 2, "days": "Mon"}
    how = hours_of_week(night)
    assert 20 in how and 23 in how and 24 in how and 31 in how and 32 not in how and 168 - 1 not in how
    week = staffing_by_week([night])["ed_nurse"]
    assert sum(week) == 2 * 12 and week[24 + 7] == 2 and week[2 * 24 + 7] == 0, "Monday-only is one shift a week"
    mon = staffing_by_hour([{"role": "sdec_doctor", "start": 8, "end": 20, "count": 1, "days": "Mon"}])
    assert len(mon["specialty_doctor"]) == 168 and sum(mon["specialty_doctor"]) == 12
    zero = staffing_by_hour([{"role": "streaming_nurse", "start": 8, "end": 20, "count": 1}])["streaming_nurse"]
    assert zero[3] == 0 and zero[9] == 1, "an hour nobody is rostered for must stay ZERO"
    bad = [{"role": "band5_nurse", "start": 8, "end": 20, "count": -1},
           {"role": "nonsense", "start": 8, "end": 20, "count": 1},
           {"role": "band5_nurse", "start": 8, "end": 20, "count": ""},
           {"role": "band5_nurse", "start": "8:30", "end": 20, "count": 1},
           {"role": "band5_nurse", "start": 8, "end": 8, "count": 1},
           {"role": "band5_nurse", "start": 8, "end": 20, "count": 1, "days": "Funday"}]
    clean, errs = validate_rota(bad)
    assert not clean and [e["row"] for e in errs] == [1, 2, 3, 4, 5, 6], errs
    ok = clean_shift({"role": "band5_nurse", "start": "20:00", "end": "08:00", "count": 0})
    assert ok["count"] == 0 and ok["days"] == "Mon-Sun", "zero is a real answer; legacy rows repeat daily"
    csv_text = rota_to_csv([night, {"role": "em_sho", "start": 0, "end": 24, "count": 3}])
    back, errs = rota_from_csv(csv_text)
    assert not errs and back[0]["days"] == "Mon" and back[1]["end"] == 24
    legacy, errs = rota_from_csv("role,start,end,count\nband5_nurse,8,20,4\n")
    assert not errs and legacy[0]["days"] == "Mon-Sun"
    print("Midshire 9 OK: overnight shifts belong to their start day; day patterns respected; negative, "
          "unknown, blank and part-hour values rejected; 0 kept as 0; legacy rows migrate to daily.")


def check_resolved_staffing(m):
    from ..workforce.rota import staffing_by_week
    from ..workforce.roles import STAFF_RESOURCES
    from ..department.config import Department
    from ..department.builder import build as build_dept, resolved_rota
    from ..optimise.recommend import _apply
    from ..workforce.defaults import DEFAULT_ROTA
    # 10: the engine runs exactly the rota shown and costed
    week = staffing_by_week(m.rota)
    for r, cap in m.raw["resources"].items():
        if r in STAFF_RESOURCES:
            assert list(cap) == week[r], f"{r}: engine roster differs from the rota"
    # ratio spaces: open = min(physical, staff x ratio), never more than physical
    for e in m.raw["uec"]["space_staffing"]:
        open_ = m.raw["resources"][e["space"]]
        phys = m.raw["uec"]["physical_spaces"][e["space"]]
        st = m.raw["uec"]["space_staff"][e["space"]]
        assert all(o == min(p, int(s * e["spaces_per_staff"])) for o, p, s in zip(open_, phys, st))
    # a SUPPLIED rota identical to the template is NOT scaled; a template rota is
    d = Department.default(); d.attendances_per_day = 400.5
    tmpl, _ = resolved_rota(d)
    assert tmpl[0]["count"] == round(DEFAULT_ROTA[0]["count"] * 400.5 / 320)
    d2 = Department.from_dict({**d.to_dict(), "rota_source": "supplied"})
    assert resolved_rota(d2)[0] == list(DEFAULT_ROTA), "a supplied rota is used exactly as given"
    legacy = Department.from_dict({k: v for k, v in d.to_dict().items() if k != "rota_source"})
    assert legacy.rota_source == "template", "migration rule: an unmarked template rota stays the template"
    # adding a shift keeps the scaled template (it used to silently drop to 320/day sizing)
    moved = _apply(d, {"kind": "shift", "role": "em_sho", "start": 10, "end": 20, "count": 1, "title": "x"})
    raw_m, raw_b = build_dept(moved), build_dept(d)
    assert sum(raw_m["resources"]["ed_doctor"]) == sum(raw_b["resources"]["ed_doctor"]) + 10, \
        "adding one 10-hour shift must add exactly 10 doctor-hours to the engine roster"
    print("Midshire 10 OK: engine rosters equal the resolved rota hour by hour; staffed spaces never exceed "
          "physical; template scaling keyed on explicit provenance; adding a shift no longer un-scales the template.")


def check_costs_and_capacity(base):
    from ..midshire import config as mcfg, runner
    from ..midshire.packages import apply_lever, package_finance, staff_needed_for_space
    from ..midshire.build import build_model
    from ..workforce.costing import rota_cost, effective_rate
    # 11: cost-only change - same model hash, same simulation; money moves
    inp = _short(base)
    priced = copy.deepcopy(inp)
    priced["cost_table"]["roles"]["band5_nurse"]["base_hourly_rate"] *= 2
    assert mcfg.model_hash(priced) == mcfg.model_hash(inp), "a cost edit must not change the model"
    assert mcfg.finance_hash(priced) != mcfg.finance_hash(inp)
    r1 = runner.run(inp, replay=False)
    r2 = runner.run(priced, replay=False)
    assert [x["four_hour"] for x in r1["reps"]] == [x["four_hour"] for x in r2["reps"]], \
        "same model + same seeds must give the same performance"
    assert rota_cost(priced["rota"], priced["cost_table"])["weekly_total"] > \
        rota_cost(inp["rota"], inp["cost_table"])["weekly_total"]
    assert effective_rate({"base_hourly_rate": None})["rate"] is None
    assert effective_rate({"base_hourly_rate": 0})["rate"] == 0.0, "an explicit 0 is £0, blank is not costed"
    assert effective_rate({"base_hourly_rate": 10, "agency_share_pct": 10})["status"] == "not costed"
    assert effective_rate({"fully_loaded_hourly_rate": 50, "base_hourly_rate": 10,
                           "employer_on_cost_pct": 30})["rate"] == 50.0, "fully loaded rates are not added to"
    lv = {"id": "hb", "kind": "estate", "space": "handover_bay", "add": 1, "title": "+1 handover bay"}
    pkg, rec = apply_lever(inp, lv)
    fin = package_finance(inp, pkg, [rec])
    assert not fin["fully_costed"] and any("handover" in x.lower() for x in fin["not_costed"]), \
        "an uncosted estate item must be reported as not costed, never £0"
    print("Midshire 11 OK: cost-only edits leave the model hash and matched-seed performance identical; "
          "blank rates are 'not costed', 0 is £0, fully loaded rates are not added to; uncosted estate flagged.")

    # 12 + 14: non-binding staff, space needs staff, zero coverage queues safely
    extra = copy.deepcopy(inp)
    extra["rota"].append({"role": "band5_nurse", "start": 20, "end": 8, "count": 2, "days": "Mon-Sun"})
    mb, me = build_model(inp), build_model(extra)
    assert mb.raw["resources"]["cubicle"] == me.raw["resources"]["cubicle"], \
        "extra nurses must not open more cubicles than physically exist"
    re_ = runner.run(extra, replay=False)
    assert [x["four_hour"] for x in re_["reps"]] == [x["four_hour"] for x in r1["reps"]], \
        "a non-binding staff increase legitimately changes nothing"
    thin = copy.deepcopy(inp)
    thin["rota"] = [r for r in thin["rota"] if r["role"] not in ("band5_nurse", "band6_nurse")] + [
        {"role": "band5_nurse", "start": 0, "end": 24, "count": 5, "days": "Mon-Sun"}]
    rows = staff_needed_for_space(thin, "cubicle", 34)
    assert rows and rows[0]["role"] == "band5_nurse" and rows[0]["count"] == 4, rows
    nosdec = copy.deepcopy(inp)
    for r in nosdec["rota"]:
        if r["role"] == "sdec_doctor":
            r["count"] = 0
    mz = build_model(nosdec)
    assert max(mz.raw["resources"]["specialty_doctor"]) == 0, "zero SDEC doctors must stay zero"
    assert any("no capacity" in w for w in mz.warnings), mz.warnings
    rz = runner.run(nosdec, replay=True)
    assert rz["replay"]["checks"]["conservation"], "zero coverage must not lose patients"
    assert rz["summary"]["n_cohort"]["mean"] > 0
    assert rz["stages"]["states"].get("sdec|service", {}).get("entries_per_day", 0) == 0, \
        "nobody can be seen in SDEC with no SDEC doctor"
    print("Midshire 12/14 OK: extra nurses cannot open more cubicles than exist and a non-binding increase "
          "changes nothing; added spaces get exactly the staff needed to open them; zero SDEC doctors stays "
          "zero - patients wait and are redirected, none lost, no deadlock.")


def check_no_extra(base):
    """13c: the "No extra resources" option adds nothing and says what it assumes."""
    from ..midshire import config as mcfg, build
    from ..midshire.optimise import levers_for, search, search_key
    from ..midshire.packages import apply_package, package_finance, describe_changes
    from ..workforce.costing import rota_cost
    lv = levers_for(base, mode="no_extra")
    kinds = {l["kind"] for l in lv}
    assert kinds <= {"move", "process", "downstream"} and {l["id"] for l in lv if l["kind"] == "downstream"} == {"discharge_10"}, kinds
    assert {"move", "process"} <= kinds
    pkg, recs = apply_package(base, lv)
    fin = package_finance(base, pkg, recs)
    assert pkg["capacity"] == base["capacity"] and pkg["downstream"]["inpatient_beds"] == base["downstream"]["inpatient_beds"]
    ct = base["cost_table"]
    assert abs(rota_cost(pkg["rota"], ct)["weekly_total"] - rota_cost(base["rota"], ct)["weekly_total"]) < 0.01
    assert fin["extra_paid_hours_week"] == 0 and fin["extra_wte"] == 0 and not fin["rota_rows"]
    assert not fin["fully_costed"] and "Quicker results and decisions" in fin["not_costed"], fin["not_costed"]
    # each moved shift keeps its role's staff-hours: the same people at other times
    def staff_hours(rota, role):
        return sum(int(r["count"]) * (((int(r["end"]) - int(r["start"])) % 24) or 24) for r in rota if r["role"] == role)
    for l in lv:
        if l["kind"] == "move":
            assert staff_hours(pkg["rota"], l["move"]["role"]) == staff_hours(base["rota"], l["move"]["role"]), l["id"]
    # quicker decisions reach the engine through the per-acuity times it actually uses
    n0 = build.build_model(base).pathway.nodes["disposition"]
    n1 = build.build_model(pkg).pathway.nodes["disposition"]
    for k, spec in n0["service_by_class"].items():
        assert abs(n1["service_by_class"][k]["mean"] - 0.9 * spec["mean"]) < 1e-6, k
    assert mcfg.model_hash(pkg) != mcfg.model_hash(base)
    words = " ".join(describe_changes(base, pkg))
    assert "Move two ED registrars from the 08:00 to 22:00 shift to a 12:00 to 02:00 shift" in words, words
    assert words.count("an assumed improvement, not costed") == 2 and "Remove" not in words and "Add " not in words, words
    # adding a change for one option leaves the other options' stored results valid
    fx = copy.deepcopy(mcfg.fixture()["search"])
    k1 = search_key(base, {"pct": 90, "minutes": 240}, "combined", fx)
    fx["levers"].append({"id": "move_test", "kind": "move", "title": "t",
                         "move": {"role": "em_sho", "days": "Mon-Sun", "from": [10, 23], "to": [11, 0], "count": 1}})
    assert search_key(base, {"pct": 90, "minutes": 240}, "combined", fx) == k1
    assert search_key(base, {"pct": 90, "minutes": 240}, "no_extra", fx) != search_key(base, {"pct": 90, "minutes": 240}, "no_extra")
    # a small search in this option: honest outcome, nothing added, the assumption said out loud
    inp = _short(base, days=2, seeds=(101, 102))
    bounds = copy.deepcopy(mcfg.fixture()["search"])
    bounds["levers"] = [l for l in bounds["levers"] if l["id"] in ("move_reg_late", "decide_10", "sho_late")]
    bounds["max_steps"], bounds["reps"] = 2, 2
    r = search(inp, {"pct": 99.5, "minutes": 240}, bounds=bounds, mode="no_extra")
    assert {l["id"] for l in r["bounds"]["levers"]} == {"move_reg_late", "decide_10"}, "no added shift in this option"
    assert r["outcome"] == "not_reached" and "99.5%" in r["headline"]
    rec = r["recommended"]
    assert not rec["finance"]["capital"] and abs(rec["finance"]["annual_pay_delta"]) < 1
    assert any("assumed 10% improvement" in x for x in r["limits"]["fixed_in_this_model"]) or "decide_10" not in [l["id"] for l in r["bounds"]["levers"]]
    print("Midshire 13c OK: 'No extra resources' adds no staff hours, space or beds; moved shifts keep each role's "
          "hours; quicker decisions reach the engine's per-acuity times; process changes are labelled as assumptions "
          "and not costed; other options' stored results are unaffected.")


def check_search(base):
    from ..midshire import config as mcfg
    from ..midshire.optimise import search, rerank
    # 13 + 14: target workflow on a small, explicit search space
    inp = _short(base, days=2, seeds=(101, 102))
    fx = mcfg.fixture()["search"]
    bounds = copy.deepcopy(fx)
    bounds["levers"] = [l for l in fx["levers"] if l["id"] in ("sho_late", "sdec_chairs_4")]
    bounds["max_steps"], bounds["reps"] = 2, 2
    easy = search(inp, {"pct": 10, "minutes": 240}, bounds=bounds)
    assert easy["outcome"] == "already_met"
    hard = search(inp, {"pct": 99.5, "minutes": 240}, bounds=bounds)
    assert hard["outcome"] == "not_reached" and "none of the tested packages reaches" in hard["headline"].lower()
    assert "99.5%" in hard["headline"] and "90%" not in hard["headline"], "nothing about 90% is hard-coded"
    assert "points short" in hard["headline"] and not re.search(r"seed|simulat|replication", hard["headline"], re.I)
    best = hard["best_tested"]
    assert best and best["measure"]["n"] == 2 and "ci_low" in best["delta_vs_baseline_pts"]
    assert hard["evaluations"]["replications"] >= 2 * hard["evaluations"]["packages"], \
        "every package is a full re-run of every seed"
    assert hard["validation"]["seeds"] == inp["engine"]["validation_seeds"]
    rows = [r for p in [hard["singles"][0]] for r in p["finance"]["rota_rows"]] + \
        [r for s in hard["singles"] for r in s["finance"]["rota_rows"]]
    assert rows and all({"role", "days", "start", "end", "baseline_staff", "proposed_staff", "change",
                         "extra_paid_hours_week", "wte", "weekly_cost", "annual_cost"} <= set(r) for r in rows)
    # a cost edit re-prices and re-ranks WITHOUT re-simulating
    ct = copy.deepcopy(inp["cost_table"])
    for e in ct["roles"].values():
        if e.get("base_hourly_rate"):
            e["base_hourly_rate"] *= 3
    rr = rerank(hard, ct, inp["estates"])
    a = [s["finance"]["annual_pay_delta"] for s in hard["singles"]]
    b = [s["finance"]["annual_pay_delta"] for s in rr["singles"]]
    assert all(y > x for x, y in zip(a, b) if x), (a, b)
    assert [s["measure"] for s in rr["singles"]] == [s["measure"] for s in hard["singles"]]
    print(f"Midshire 13/14 OK: already-met and not-reached targets handled honestly; best tested "
          f"{best['measure']['mean']:.1f}% with a noise interval; {hard['evaluations']['packages']} packages "
          f"each fully re-run; validation seeds separate; cost edits re-price without re-simulating.")


def check_app_and_assistant(base):
    from ..midshire import config as mcfg, store
    from ..midshire.server import create_app
    db = f"sqlite:///{tempfile.mkdtemp()}/midshire_test.sqlite3"
    os.environ["MIDSHIRE_TEST"] = "1"
    app = create_app(db, load_fixtures=False)
    c = app.test_client()
    # 2: identity and labels; no Cambridge-facing branding on the demo surfaces
    page = c.get("/")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "<title>Midshire University Hospitals Trust Control Tower</title>" in html
    assert ">Midshire University Hospitals Trust Control</div></footer>" in html, "the footer is the trust name only"
    assert "Ask My ED" in html and "Qbo" not in html and 'id="tab-setup"' not in html, "Ask My ED; no Set up tab"
    for bad in ("simulated data", "Demo baseline", "Precomputed", "warm-up", "seed"):
        assert bad.lower() not in html.lower(), f"technical wording on the page: {bad!r}"
    assert "\u2013" not in html and "\u2013" not in (ROOT / "uec_hybrid" / "app" / "static" / "midshire.js").read_text(), "no en dashes"
    static = ROOT / "uec_hybrid" / "app" / "static"
    js = (static / "midshire.js").read_text(); css = (static / "midshire.css").read_text()
    for name, txt in (("page", html), ("script", js), ("styles", css)):
        assert not re.search(r"cambridge|\bcuh\b|addenbrooke|cuh-logo", txt, re.I), f"Cambridge branding in the {name}"
    meta = c.get("/api/m/meta").get_json()
    assert meta["product_title"] == "Midshire University Hospitals Trust Control Tower"
    assert "Cambridge-derived" in meta["foundation"]["summary"], "technical provenance must stay accurate"
    assert meta["demo_id"] == "MIDSHIRE-DEMO" and not re.fullmatch(r"R[A-Z0-9]{2}", meta["demo_id"])
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js, \
        "untrusted text must never be inserted as HTML"
    print("Midshire 2 OK: exact product title and footer; Ask My ED, no Set up tab, no technical wording or en "
          "dashes on the page; no Cambridge name, logo or greeting; the provenance still records the source.")

    # 15: save, apply, reload, reset; the baseline never changes
    short = _short(base)
    r = c.post("/api/m/scenarios", json={"name": "Short baseline", "inputs": short})
    assert r.status_code == 200, r.get_json()
    sid = r.get_json()["scenario"]["id"]
    edited = copy.deepcopy(short)
    edited["rota"].append({"role": "em_sho", "start": 14, "end": 2, "count": 1, "days": "Mon-Sun"})
    r2 = c.post("/api/m/scenarios", json={"name": "Plus one SHO", "inputs": edited}).get_json()["scenario"]
    before = store.get_scenario("baseline")["inputs"]
    assert c.post("/api/m/apply", json={"scenario_id": r2["id"]}).get_json()["applied"] == r2["id"]
    assert c.post("/api/m/scenarios", json={"name": "x", "id": "baseline", "inputs": edited}).status_code in (200, 403)
    assert store.get_scenario("baseline")["inputs"] == before, "the baseline must never change"
    bad = c.post("/api/m/scenarios", json={"name": "bad", "inputs": {**short, "rota": [{"role": "band5_nurse", "start": 8, "end": 20, "count": -2}]}})
    assert bad.status_code == 400 and bad.get_json()["details"], "invalid inputs are refused with details"
    run = c.post("/api/m/run", json={"scenario_id": sid}).get_json()
    if run["status"] == "running":
        from ..midshire import jobs
        j = jobs.wait(run["job"]["id"], 600)
        assert j["status"] == "done", j
    res = c.post("/api/m/result", json={"scenario_id": sid, "request_id": 7}).get_json()
    assert res["status"] == "done" and res["request_id"] == 7
    assert res["result"]["model_hash"] == mcfg.model_hash(short)
    other = c.post("/api/m/result", json={"scenario_id": r2["id"]}).get_json()
    assert other["status"] == "not_simulated", "a result must never be shown for different inputs"
    reset = c.post("/api/m/reset").get_json()
    assert reset["applied"] == "baseline" and store.get_scenario(sid) is not None, "reset keeps saved scenarios"
    assert c.delete("/api/m/scenarios/baseline").status_code == 403
    print("Midshire 15 OK: save, apply, reload and reset work; the baseline is read-only; invalid inputs are "
          "refused; a result is only ever served for the inputs that produced it.")

    # 10b: "are we staffed for when patients arrive?" - the preview's per-group panels
    pv = c.post("/api/m/preview", json={"scenario_id": "baseline"}).get_json()
    adult = mcfg.baseline_inputs()["cohort"]["adult_attendances_per_day"]
    assert abs(sum(pv["demand"]) - adult) < 1.0, (sum(pv["demand"]), adult)
    from ..workforce.rota import understaffed_hours
    for key, g in pv["staffing"].items():
        for d in range(7):
            day = g["week"][d * 24:(d + 1) * 24]
            assert all(day[hh] > 0 or hh not in g["light_days"][d] for hh in range(24)) or key not in (
                "utc_clinician", "sdec_nurse", "specialty_doctor", "frailty_team"), (key, d, "closed hours are never light")
            assert all(sum(wk[d * 24 + hh] for wk in g["roles"].values()) == day[hh] for hh in range(24)), (key, d)
    ed = pv["staffing"]["ed_nurse"]
    assert ed["light_days"][3] == understaffed_hours(ed["week"][72:96], pv["demand"]), "the shared heuristic, unchanged"
    assert not any(k.startswith("paeds") for k in pv["staffing"])
    print("Midshire 10b OK: staffing panels use the adult arrival curve and the shared shape heuristic; closed hours "
          "are never flagged; who is on adds up to the bars.")

    # 16: Ask My ED and exports reconcile with the structured result
    c.post("/api/m/apply", json={"scenario_id": sid})
    a1 = c.post("/api/m/ask", json={"message": "how are we doing?", "scenario_id": sid}).get_json()
    tv = res["result"]["target_status"]["value"]["mean"]
    assert f"{tv:.1f}%" in a1["reply"], (tv, a1["reply"])
    a2 = c.post("/api/m/ask", json={"message": "where do patients wait longest?", "scenario_id": sid}).get_json()
    top = res["result"]["pressure"][0]
    from ..midshire.optimise import wait_phrase
    assert wait_phrase(top["label"]) in a2["reply"] and f"{top['patient_hours_per_day']:.0f}" in a2["reply"]
    # the same figures as the page for the view on screen: a selected day, then a typical day at a set hour
    rr = res["result"]
    day_view = {"mode": "replay", "day": 0, "index": 40}
    a5 = c.post("/api/m/ask", json={"message": "how are we doing?", "scenario_id": sid, "view": day_view}).get_json()
    k0 = rr["replay"]["days"][0]
    from ..midshire.runner import THRESHOLDS
    w0 = k0["within"][THRESHOLDS.index(int(short["target"]["minutes"]))]
    for want in (f"{k0['n_cohort']} patients arrived", f"{w0:.1f}%", f"{rr['replay']['census'][40]} patients in the department"):
        assert want in a5["reply"], (want, a5["reply"])
    a6 = c.post("/api/m/ask", json={"message": "where do patients wait longest?", "scenario_id": sid, "view": day_view}).get_json()
    kinds = {(st["node"] + "|" + st["phase"]): (st["kind"], st["label"]) for g in mcfg.groups() for st in g["states"]}
    by = {}
    for key, ser in rr["replay"]["states"].items():       # the Overview's "Where waits build up" for day 0
        if kinds.get(key, ("", ""))[0] == "waiting":
            by[kinds[key][1]] = by.get(kinds[key][1], 0) + sum(ser[0:96]) * 0.25
    lab, hrs_day = max(by.items(), key=lambda kv: kv[1])
    assert wait_phrase(lab) in a6["reply"] and f"about {hrs_day:.0f} hours" in a6["reply"], (lab, hrs_day, a6["reply"])
    a7 = c.post("/api/m/ask", json={"message": "how are we doing?", "scenario_id": sid,
                                    "view": {"mode": "typical", "day": 0, "index": None, "hour": 12}}).get_json()
    assert f"about {rr['profile']['census_avg'][12]:.0f} patients in the department" in a7["reply"], a7["reply"]
    assert "on a typical day" in a7["reply"].lower() and "on a typical day" in a2["reply"].lower(), (a7["reply"], a2["reply"])
    for a in (a1, a2, a5, a6, a7):
        assert not re.search(r"seed|run id|simulat|replication|Qbo", a["reply"], re.I), a["reply"]
    a3 = c.post("/api/m/ask", json={"message": "<img src=x onerror=alert(1)> tell me a joke", "scenario_id": sid}).get_json()
    assert a3["intent"] == "unsupported" and "can't" in a3["reply"]
    a4 = c.post("/api/m/ask", json={"message": "what if we add 99 nurses", "scenario_id": sid}).get_json()
    assert a4["intent"] in ("unsupported", "what_if") and not a4.get("job"), "out-of-range changes are refused"
    exp = c.get(f"/api/m/export/results.json?scenario_id={sid}")
    ej = json.loads(exp.get_data(as_text=True))
    assert exp.headers["Content-Disposition"].startswith('attachment; filename="midshire_')
    assert ej["summary"]["four_hour"]["mean"] == res["result"]["summary"]["four_hour"]["mean"]
    assert "metric_definitions" in ej
    rota_csv = c.get(f"/api/m/export/rota.csv?scenario_id={sid}").get_data(as_text=True)
    from ..workforce.rota import rota_from_csv
    back, errs = rota_from_csv(rota_csv)
    assert not errs and len(back) == len(short["rota"])
    print("Midshire 16 OK: Ask My ED quotes the structured result exactly in plain words, refuses unsupported or "
          "out-of-range questions explicitly, returns plain text; exports match the result and re-import.")


def check_accessibility_static():
    # 17 (static half): contrast of the token pairs in use, labels, focus and motion rules
    css = (ROOT / "uec_hybrid" / "app" / "static" / "midshire.css").read_text()
    html = (ROOT / "uec_hybrid" / "app" / "templates" / "midshire.html").read_text()
    tok = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css))

    def lum(hx):
        c = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)
    pairs = [("nhs-text", "nhs-surface", 4.5), ("nhs-text", "nhs-background", 4.5),
             ("nhs-secondary-text", "nhs-surface", 4.5), ("nhs-secondary-text", "nhs-background", 4.5),
             ("nhs-blue", "nhs-surface", 4.5), ("nhs-text", "nhs-focus", 4.5), ("nhs-text", "nhs-warm-yellow", 4.5),
             ("nhs-text", "nhs-pale-yellow", 4.5), ("nhs-dark-blue", "nhs-pale-blue", 4.5),
             ("chart-1", "nhs-surface", 3), ("chart-2", "nhs-surface", 3), ("chart-3", "nhs-surface", 3)]
    for a, b, need in pairs:
        r = ratio(tok[a], tok[b])
        assert r >= need, f"contrast {a} on {b} is {r:.2f}, needs {need}"
    assert ratio("#ffffff", tok["nhs-blue"]) >= 4.5 and ratio("#ffffff", tok["nhs-green"]) >= 4.5
    # flow-map status words and the "most waiting" badge
    for fg in ("#00401e", "#5c4200", "#8a1538"):
        assert ratio(fg, tok["nhs-surface"]) >= 4.5 and ratio(fg, tok["nhs-background"]) >= 4.5, fg
    assert ratio("#ffffff", tok["nhs-red"]) >= 4.5 and ratio(tok["nhs-dark-blue"], tok["nhs-surface"]) >= 4.5
    assert 'id="flowPause"' in html and 'id="flowTableView"' in html, "the flow map needs a pause control and a table view"
    assert "prefers-reduced-motion" in css and ":focus-visible" in css and "--nhs-focus" in css
    assert '<html lang="en-GB">' in html and 'class="ms-skip"' in html
    for m in re.finditer(r"<(input|select)\b([^>]*)>", html):
        attrs = m.group(2)
        idm = re.search(r'id="([^"]+)"', attrs)
        if 'type="file"' in attrs:
            continue
        assert 'aria-label' in attrs or (idm and f'for="{idm.group(1)}"' in html), f"unlabelled control: {m.group(0)}"
    assert 'role="tablist"' in html and 'aria-live' in html and 'role="dialog"' in html
    print(f"Midshire 17 OK (static): {len(pairs) + 10} colour pairs meet WCAG AA contrast; every control "
          "is labelled; yellow focus state, skip link, reduced-motion rule and live regions present. "
          "(Keyboard, zoom and viewport checks run in the browser script.)")


def check_fresh_checkout():
    # 18: the demo starts from committed files only, no external AI service
    from ..midshire.server import create_app
    from ..midshire import config as mcfg
    os.environ.pop("ANTHROPIC_API_KEY", None)
    db = f"sqlite:///{tempfile.mkdtemp()}/fresh.sqlite3"
    app = create_app(db, load_fixtures=True)
    c = app.test_client()
    assert c.get("/").status_code == 200
    pre = app.config.get("PRECOMPUTED") or {}
    man = mcfg.PRECOMPUTED_DIR / "manifest.json"
    if man.exists():
        assert not pre.get("stale"), f"committed precomputed results are stale: {pre['stale']}"
        res = c.post("/api/m/result", json={"scenario_id": "baseline"}).get_json()
        assert res["status"] == "done" and res["result"]["result_source"] == "precomputed"
        msg = f"{len(pre.get('loaded', []))} precomputed result files load and match the current model"
    else:
        msg = "no precomputed fixtures committed (the demo would simulate on first open)"
    # the scenario picker starts with the baseline only; library scenarios join it once opened
    cards = c.get("/api/m/scenarios").get_json()["scenarios"]
    assert [x["id"] for x in cards if x["shown"]] == ["baseline"], "only the baseline is listed at first"
    base_card = next(x for x in cards if x["id"] == "baseline")
    assert base_card["name"] == "Baseline" and base_card["info"].get("why")
    lib = [x for x in cards if x["kind"] == "precomputed"]
    for x in lib:
        assert "(precomputed)" not in x["name"] and x["changes"] and x["info"].get("why") and x["info"].get("look_for"), x
    if lib:
        c.post("/api/m/apply", json={"scenario_id": lib[0]["id"]})
        shown = [x["id"] for x in c.get("/api/m/scenarios").get_json()["scenarios"] if x["shown"]]
        assert lib[0]["id"] in shown
        c.post("/api/m/reset", json={})
        assert [x["id"] for x in c.get("/api/m/scenarios").get_json()["scenarios"] if x["shown"]] == ["baseline"]
    print(f"Midshire 18 OK: a fresh database starts the demo from committed files; {msg}; the scenario list "
          f"starts with the baseline only and every library scenario says what changes, why and what to look for.")


def check_runtime_fallback(base):
    """No forkserver (Windows) or a broken worker pool: runs still finish, in
    the same results; a failed job shows a plain message, never Python."""
    import multiprocessing as mp
    from ..midshire import runner, jobs
    inp = _short(base, days=1, seeds=(101, 102))
    ref = runner.run(inp)["summary"]["four_hour"]["mean"]
    saved = (mp.get_all_start_methods, runner._POOL, runner._POOL_DISABLED)
    try:
        runner.reset_pool()
        runner._POOL_DISABLED = False
        mp.get_all_start_methods = lambda: ["spawn"]            # what Windows offers
        assert runner.start_method() == "spawn"
        mp.get_all_start_methods = lambda: []                   # nothing usable at all
        runner.reset_pool(); runner._POOL_DISABLED = False
        assert runner.start_method() is None and runner.get_pool() is None
        assert runner.run(inp)["summary"]["four_hour"]["mean"] == ref
        mp.get_all_start_methods = saved[0]
        from concurrent.futures.process import BrokenProcessPool

        class Broken:
            def submit(self, *a, **k):
                raise BrokenProcessPool("worker died")

            def shutdown(self, **k):
                pass
        runner._POOL, runner._POOL_DISABLED = Broken(), False
        assert runner.run(inp)["summary"]["four_hour"]["mean"] == ref, "a broken pool finishes in-process"
    finally:
        mp.get_all_start_methods = saved[0]
        runner.reset_pool()
        runner._POOL_DISABLED = False

    def boom(progress, cancelled):
        raise ValueError("cannot find context for 'forkserver'")
    j = jobs.start("run", "test-failure", boom)
    j = jobs.wait(j["id"], 10)
    assert j["status"] == "failed" and j["message"] == jobs.FAILED_MESSAGE and not j.get("error")
    assert "ValueError" not in json.dumps(j) and "forkserver" not in json.dumps(j), "no Python errors on screen"
    print("Midshire 18b OK: runs finish identically with no forkserver (Windows), no usable start method, or a "
          "broken worker pool; a failed run shows a plain message and never a Python error.")


def main():
    os.environ.setdefault("MIDSHIRE_WORKERS", "2")
    check_sources()
    base, m = check_build_adult()
    check_runs(base)
    check_patient_metrics()
    check_rota()
    check_resolved_staffing(m)
    check_costs_and_capacity(base)
    check_search(base)
    check_no_extra(base)
    check_app_and_assistant(base)
    check_accessibility_static()
    check_fresh_checkout()
    check_runtime_fallback(base)
    print("\nAll Midshire checks passed.")


if __name__ == "__main__":
    main()
