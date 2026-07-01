"""
Flask dashboard for the hybrid SD+DES UEC model.

Tabs: Live simulation (scorecard + flow model + diagnosis), System Dynamics
(stocks/feedback/occupancy band), Monte-Carlo, Scenarios & sensitivity, Validation
(process-map conformance), and Data & population (determinants + ECDS calibration).
Plotly is vendored locally so it runs offline / on locked-down NHS networks.
"""
from __future__ import annotations

import copy
import glob
import io
import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from ..des.pathway import Pathway
from ..coupling.cosim import run_cosim
from ..analysis.metrics import (kpis, uec_metrics, uec_scorecard, diagnose)
from ..analysis.montecarlo import monte_carlo
from ..analysis.scenarios import compare_scenarios, tornado
from ..validation.conformance import check as conformance_check
from ..validation.process_map import variants
from ..viz import figures as fig
from ..viz.flow_model import flow_model_data
from ..demand.population import apply_population
from ..demand.ecds_seam import read_table, derive_patch, apply_patch, generate_sample
from ..planning.planner import make_plan
from ..planning.operational import today_plan
from ..planning.forecast import forecast_from_history, generate_daily_history
from ..platform import store
from ..finance import load_cost_book, save_cost_book, business_case, gap_finance

app = Flask(__name__)
PATHWAY_DIR = Path(__file__).resolve().parent.parent / "pathways"
store.init_db()


def _calibration_patch(scope):
    cal = store.get_calibration(scope)
    return cal["patch"] if cal else None


def list_pathways():
    out = {}
    for f in sorted(glob.glob(str(PATHWAY_DIR / "*.json"))):
        key = Path(f).stem
        data = json.load(open(f))
        out[key] = {"key": key, "name": data.get("name", key),
                    "description": data.get("description", ""),
                    "resources": data.get("resources", {}), "sd": data.get("sd", {})}
    return out


def _build(body):
    key = body["pathway"]
    if key == "your_department":
        # the analyst view runs the SAME department configured in the product,
        # so its numbers line up with the control tower.
        raw = copy.deepcopy(build_dept(_dept()))
    else:
        raw = copy.deepcopy(Pathway.load(PATHWAY_DIR / f"{key}.json").raw)
    patch = _calibration_patch(key)
    if patch:
        raw = apply_patch(raw, patch)
    name = raw.get("name", key)
    pop = body.get("population") or {}
    demand_mult = 1.0
    if pop:
        raw, demand_mult, _ = apply_population(
            raw, float(pop.get("older_fraction", 0.20)),
            float(pop.get("imd_decile", 5.0)), float(pop.get("paediatric_fraction", 0.22)))
    for r, v in (body.get("overrides") or {}).items():
        if r in raw.get("resources", {}):
            raw["resources"][r] = max(0, int(v))
    scale = float(body.get("arrivals_scale", 1.0)) * demand_mult
    if scale != 1.0 and "hourly_profile" in raw.get("arrivals", {}):
        raw["arrivals"]["hourly_profile"] = [h * scale for h in raw["arrivals"]["hourly_profile"]]
    p = Pathway.from_dict(raw); p.name = name
    sd_over = body.get("sd_overrides") or None
    return p, sd_over, bool(body.get("feedback", True)), raw


def J(figure):
    return json.loads(figure.to_json())


@app.route("/")
def home():
    # The product: a flow-first control tower for designing/running the ED.
    return render_template("product.html")


@app.route("/planner")
def planner_page():
    return render_template("planner.html")


# ---- Model ED Optimiser product ------------------------------------------- #
from ..department.config import Department, AREAS, CORE_NOTE
from ..department.builder import build as build_dept
from ..department.model_ed_gap import gap_analysis
from ..workforce.roles import ROLES, AREA_LABEL
from ..workforce.view import workforce_view
from ..viz.flow_model import control_tower

CURRENT = {"dept": None}


def _dept() -> Department:
    """The saved department — one department shared by every surface, persisted
    across restarts (control tower, workforce, gaps, planner and analyst all
    model the same ED)."""
    if CURRENT["dept"] is None:
        saved = store.load_department()
        CURRENT["dept"] = Department.from_dict(saved) if saved else Department.default()
        if saved is None:
            store.save_department(CURRENT["dept"].to_dict())
    return CURRENT["dept"]


def _dept_raw():
    """The department's runnable pathway, with any stored calibration applied."""
    raw = build_dept(_dept())
    patch = _calibration_patch("your_department")
    return apply_patch(raw, patch) if patch else raw


def _standards(dept, reps=5):
    """Plain headline standards for a department: good / typical / tough.
    Cached by configuration hash — the same set-up never simulates twice."""
    raw = _dept_raw()
    key = {"raw": raw, "reps": reps}
    hit = store.cached("standards", key)
    if hit is not None:
        return hit

    p = Pathway.from_dict(raw)
    mc = monte_carlo(p, replications=reps, base_seed=1000, feedback=True)
    s = mc["summary"]

    def band(key, hi=True):
        v = s.get(key)
        if not v:
            return None
        return {"typical": round(v["mean"]), "good": round(v["max"] if hi else v["min"]),
                "tough": round(v["min"] if hi else v["max"])}
    return store.remember("standards", key, {
        "four_hour": band("four_hour"),
        "initial_assessment": band("initial_assessment_15min"),
        "twelve_hour": band("twelve_hour", hi=False),
        "ambulance_handover": band("ambulance_handover_45"),
        "attendances_per_day": round(dept.attendances_per_day),
    })


@app.route("/api/setup")
def api_setup():
    d = _dept()
    return jsonify({
        "department": d.to_dict(),
        "areas": {k: {"label": v["label"], "why": v["why"]} for k, v in AREAS.items()},
        "core_note": CORE_NOTE,
        "roles": {k: {"label": v["label"], "staffs": v["staffs"], "cost": v["cost"]} for k, v in ROLES.items()},
        "area_labels": AREA_LABEL,
    })


@app.route("/api/department", methods=["POST"])
def api_set_department():
    CURRENT["dept"] = Department.from_dict(request.get_json(force=True))
    version = store.save_department(CURRENT["dept"].to_dict())
    return jsonify({"ok": True, "department": CURRENT["dept"].to_dict(), "version": version})


@app.route("/api/control-tower", methods=["POST"])
def api_control_tower():
    d = _dept()
    raw = _dept_raw()
    seed = int(request.get_json(silent=True, force=True).get("seed", 2) if request.data else 2)

    def compute():
        p = Pathway.from_dict(raw)
        res = run_cosim(p, seed=seed)
        ct = control_tower(res, p)
        diag = diagnose(res, p)
        ct["standards"] = _standards(d)
        ct["recommendation"] = diag["recommendation"]
        ct["headline_bottleneck"] = diag["headline"]
        return ct
    return jsonify(store.cached_or_compute("control_tower", {"raw": raw, "seed": seed}, compute))


@app.route("/api/workforce", methods=["POST"])
def api_workforce():
    return jsonify(workforce_view(_dept()))


@app.route("/api/rota-preview", methods=["POST"])
def api_rota_preview():
    """Instant (no-simulation) staffing-vs-demand + cost for an edited rota, so the
    rota editor updates live as shifts are changed."""
    from ..workforce.view import staffing_and_cost
    body = request.get_json(force=True)
    d = _dept()
    rota = body.get("rota", d.rota)
    att = float(body.get("attendances_per_day", d.attendances_per_day))
    present = set(build_dept(d).get("resources", {}))   # the areas this ED has
    return jsonify(staffing_and_cost(rota, att, present=present))


@app.route("/api/costbook", methods=["GET", "POST"])
def api_costbook():
    """The trust-editable cost book behind every £ figure the product shows."""
    if request.method == "POST":
        return jsonify(save_cost_book(request.get_json(force=True)))
    return jsonify(load_cost_book())


@app.route("/api/gap", methods=["POST"])
def api_gap():
    d = _dept()
    book = load_cost_book()

    def compute():
        gap = gap_analysis(d)
        for item in gap["missing"]:
            item["finance"] = gap_finance(item, d.attendances_per_day, book)
        return gap
    return jsonify(store.cached_or_compute("gap", {"dept": d.to_dict(), "book": book}, compute))


@app.route("/api/plan", methods=["POST"])
def api_plan():
    body = request.get_json(force=True)
    d = _dept()
    patch = _calibration_patch("your_department")
    args = {"attendances_now": float(body.get("attendances_now", d.attendances_per_day)),
            "winter_uplift_pct": float(body.get("winter_uplift_pct", 12)),
            "yoy_growth_pct": float(body.get("yoy_growth_pct", 0))}
    book = load_cost_book()

    def compute():
        plan = make_plan(**args, department=d, calibration=patch)
        for opt in plan["options"]:
            opt["finance"] = business_case(opt, plan["outcome"], args["attendances_now"], book)
        return plan
    try:
        plan = store.cached_or_compute(
            "plan", {"dept": d.to_dict(), "patch": patch, "book": book, **args}, compute)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(plan)


@app.route("/api/plan-today", methods=["POST"])
def api_plan_today():
    body = request.get_json(force=True)
    d = _dept()
    patch = _calibration_patch("your_department")
    args = {"attendances_today": float(body.get("attendances_today", d.attendances_per_day * 1.06)),
            "hospital_fullness_pct": float(body.get("hospital_fullness_pct", 94))}
    try:
        plan = store.cached_or_compute(
            "plan_today", {"dept": d.to_dict(), "patch": patch, **args},
            lambda: today_plan(**args, department=d, calibration=patch))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(plan)


@app.route("/api/forecast-data", methods=["POST"])
def api_forecast_data():
    """Derive the winter forecast from an uploaded daily attendance history."""
    if "file" not in request.files:
        return jsonify({"error": "no file uploaded"}), 400
    try:
        df = read_table(request.files["file"].read())
        return jsonify(forecast_from_history(df))
    except Exception as e:
        return jsonify({"error": f"could not read history: {e}"}), 400


@app.route("/api/sample-history")
def api_sample_history():
    buf = io.StringIO(); generate_daily_history().to_csv(buf, index=False)
    return app.response_class(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_attendance_history.csv"})


def _your_department_pathway_entry():
    """The product's configured department, exposed to the analyst view so both
    surfaces run the same ED."""
    d = _dept()
    raw = _dept_raw()
    calibrated = _calibration_patch("your_department") is not None
    return {"your_department": {
        "key": "your_department",
        "name": f"{d.name} (as set up in the product)",
        "description": ("This is the department you configured in the product "
                        "(Set up my ED): same areas, sizes, beds and rota, so the "
                        "analyst figures match the control tower."
                        + (" Calibrated from your uploaded attendance data." if calibrated else "")),
        "resources": raw.get("resources", {}), "sd": raw.get("sd", {})}}


@app.route("/analyst")
def analyst():
    # The technical model view, for analysts — defaulting to the user's own
    # department so it is connected to the product, not a separate model.
    pathways = {**_your_department_pathway_entry(), **list_pathways()}
    return render_template("dashboard.html", pathways=pathways)


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(force=True)
    p, sd_over, fb, raw = _build(body)
    seed = int(body.get("seed", 0))

    def compute():
        res = run_cosim(p, seed=seed, feedback=fb, sd_overrides=sd_over)
        m = {**kpis(res, p), **uec_metrics(res, p)}
        conf = conformance_check(res, p)
        return {
            "kpis": m, "scorecard": uec_scorecard(m), "diagnosis": diagnose(res, p),
            "flow_model": flow_model_data(res, p),
            "conformance": {k: conf[k] for k in ("conformance_rate", "n_violations", "passed", "by_type")},
            "figures": {
                "sd_stocks": J(fig.sd_stocks_figure(res, p)),
                "sd_feedback": J(fig.sd_feedback_figure(res)),
                "utilisation": J(fig.utilisation_figure(res, p)),
                "waits": J(fig.waits_figure(res)),
            }}
    key = {"raw": raw, "seed": seed, "feedback": fb, "sd": sd_over}
    return jsonify(store.cached_or_compute("simulate", key, compute))


@app.route("/api/montecarlo", methods=["POST"])
def api_montecarlo():
    body = request.get_json(force=True)
    p, sd_over, fb, raw = _build(body)
    reps = int(body.get("replications", 24))

    def compute():
        mc = monte_carlo(p, replications=reps, base_seed=1000, feedback=fb, sd_overrides=sd_over)
        s = mc["summary"].get("four_hour", {})
        interp = ""
        if s:
            spread = s["ci_high"] - s["ci_low"]
            interp = (f"Across {reps} independent simulated weeks, 4-hour performance averaged "
                      f"{s['mean']:.1f}% (95% of weeks {s['ci_low']:.1f}–{s['ci_high']:.1f}%). "
                      + ("Wide spread — plan to the lower bound." if spread > 8
                         else "Reasonably tight — behaviour is predictable at this configuration."))
        return {"summary": mc["summary"], "interpretation": interp,
                "four_hour": J(fig.montecarlo_figure(mc, "four_hour", "4-hour compliance (%)")),
                "twelve": J(fig.montecarlo_figure(mc, "twelve_hour", "12-hour waits (%)")),
                "occ_band": J(fig.occupancy_band_figure(mc))}
    key = {"raw": raw, "reps": reps, "feedback": fb, "sd": sd_over}
    return jsonify(store.cached_or_compute("montecarlo", key, compute))


@app.route("/api/scenarios", methods=["POST"])
def api_scenarios():
    body = request.get_json(force=True)
    p, _, fb, raw = _build(body)
    scenarios = body.get("scenarios", [])
    reps = int(body.get("replications", 8))

    def compute():
        cmp = compare_scenarios(p, scenarios, replications=reps, feedback=fb)
        tor = tornado(p, scenarios, replications=max(6, reps // 2)) if scenarios else {"bars": []}
        return {"rows": cmp["rows"],
                "four_hour": J(fig.scenario_figure(cmp, "four_hour", "4-hour compliance (%)")),
                "twelve": J(fig.scenario_figure(cmp, "twelve_hour", "12-hour waits (%)", higher_better=False)),
                "tornado": J(fig.tornado_figure(tor)) if tor["bars"] else None}
    key = {"raw": raw, "scenarios": scenarios, "reps": reps, "feedback": fb}
    return jsonify(store.cached_or_compute("scenarios", key, compute))


@app.route("/api/validate", methods=["POST"])
def api_validate():
    body = request.get_json(force=True)
    p, sd_over, fb, _raw = _build(body)
    res = run_cosim(p, seed=int(body.get("seed", 0)), feedback=fb, sd_overrides=sd_over)
    conf = conformance_check(res, p)
    v = variants(res).to_dict("records")
    return jsonify({"conformance": conf, "variants": v})


@app.route("/api/sample-data")
def api_sample_data():
    buf = io.StringIO(); generate_sample().to_csv(buf, index=False)
    return app.response_class(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_ecds_template.csv"})


@app.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    key = request.form.get("pathway")
    if "file" not in request.files:
        return jsonify({"error": "no file uploaded"}), 400
    try:
        df = read_table(request.files["file"].read())
        patch, summary = derive_patch(df)
        store.save_calibration(key, patch, summary)
        if key == "your_department" and patch.get("arrivals", {}).get("hourly_profile"):
            # keep the saved department's demand in step with the observed data,
            # so the workforce view and planner read the same daily total.
            d = _dept()
            d.attendances_per_day = round(sum(patch["arrivals"]["hourly_profile"]), 1)
            store.save_department(d.to_dict())
            summary.append(f"Department demand set to the observed "
                           f"{round(d.attendances_per_day)} attendances/day — the control "
                           f"tower, workforce view and planner now all use your data.")
    except Exception as e:
        return jsonify({"error": f"could not calibrate: {e}"}), 400
    return jsonify({"summary": summary, "calibrated": True})


@app.route("/api/calibrate/reset", methods=["POST"])
def api_calibrate_reset():
    store.clear_calibration(request.get_json(force=True).get("pathway"))
    return jsonify({"summary": ["Reset to synthetic baseline."], "calibrated": False})


def main():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)


if __name__ == "__main__":
    main()
