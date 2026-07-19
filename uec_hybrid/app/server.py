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
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

from ..des.pathway import Pathway
from ..coupling.cosim import run_cosim
from ..analysis.metrics import (kpis, uec_metrics, uec_scorecard, scorecard_defaults, diagnose,
                                sd_interpretation, stage_timing)
from ..analysis.montecarlo import monte_carlo
from ..analysis.scenarios import compare_scenarios, tornado, interpret as scenario_interpret
from ..validation.conformance import check as conformance_check
from ..validation.process_map import variant_timing
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


def _apply_resource_override(cap, value):
    """Apply an analyst override without collapsing a by-hour roster to a scalar."""
    if isinstance(value, str):
        from ..planning.planner import _scale_cap
        return _scale_cap(cap, value)
    if isinstance(value, list):
        return [max(0, int(x)) for x in value]
    val = max(0, int(value))
    if isinstance(cap, (list, tuple)):
        return [val] * len(cap)
    return val


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
            raw["resources"][r] = _apply_resource_override(raw["resources"][r], v)
    scale = float(body.get("arrivals_scale", 1.0)) * demand_mult
    if scale != 1.0 and "hourly_profile" in raw.get("arrivals", {}):
        raw["arrivals"]["hourly_profile"] = [h * scale for h in raw["arrivals"]["hourly_profile"]]
    raw = model_params.apply_params(raw, model_params.load_params())   # service-time overrides
    p = Pathway.from_dict(raw); p.name = name
    sd_over = body.get("sd_overrides") or None
    return p, sd_over, bool(body.get("feedback", True)), raw


def J(figure):
    return json.loads(figure.to_json())


@app.route("/")
def home():
    # The product: a flow-first control tower for designing/running the ED.
    return render_template("product.html")


_FAVICON = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
            "<rect width='64' height='64' rx='12' fill='#005EB8'/>"
            "<text x='32' y='43' font-family='Arial,Helvetica,sans-serif' font-size='26' "
            "font-weight='bold' fill='#fff' text-anchor='middle'>ED</text></svg>")


@app.route("/favicon.ico")
def favicon():
    # browsers request this on every page; without it each load logs a 404
    return app.response_class(_FAVICON, mimetype="image/svg+xml",
                              headers={"Cache-Control": "public, max-age=86400"})


@app.route("/planner")
def planner_page():
    return render_template("planner.html")


@app.route("/exec")
def exec_page():
    # the executive brief: one screen for the COO / ED director.
    return render_template("exec.html")


# --- the React shell (web/dist, committed like the vendored Plotly) --------- #
WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


@app.route("/app", defaults={"path": ""})
@app.route("/app/", defaults={"path": ""})
@app.route("/app/<path:path>")
def spa(path):
    """The React front-end. Surfaces migrate here one at a time; until then the
    template pages stay canonical."""
    if not WEB_DIST.exists():
        return ("The new interface is not built - run `npm install && npm run build` "
                "in web/ (or use the existing pages at /).", 503)
    if path and (WEB_DIST / path).is_file():
        return send_from_directory(WEB_DIST, path)
    return send_from_directory(WEB_DIST, "index.html")


@app.route("/api/exec")
def api_exec():
    """One composed payload for the executive brief. Reuses cached results
    where they exist so the page opens fast; the deep dives stay one click away."""
    from ..planning.operational import _opel
    d = _dept()
    ct = _control_tower_payload(seed=2)
    standards = ct.get("standards") or {}
    four = (standards.get("four_hour") or {}).get("typical", 0)
    occ = next((s["occupancy"] for s in ct.get("stocks", []) if "Inpatient" in s["name"]), 0)
    risk = _opel(four, occ)
    wf = workforce_view(d)
    under = sum(len(a["understaffed_hours"]) for a in wf["areas"])
    book = load_cost_book()
    gap = store.cached("gap", {"dept": d.to_dict(), "book": book})
    invest = (gap["missing"][0] if gap and gap.get("missing") else None)
    return jsonify({
        "department": {"name": d.name, "attendances_per_day": round(d.attendances_per_day),
                       "calibrated": _calibration_patch("your_department") is not None},
        "standards": standards,
        "risk": risk,
        "bed_occupancy": occ,
        "bottleneck": ct.get("headline_bottleneck", ""),
        "recommendation": ct.get("recommendation", ""),
        "workforce": {"weekly_cost": wf["weekly_cost"], "understaffed_hours": under,
                      "headline": wf["headline"]},
        "invest": invest,
        "gap_computed": gap is not None,
        "benchmark": _benchmark_position(standards),
    })


@app.route("/api/report")
def api_report():
    """One-click decision report (PDF) for the configured department, including
    the investment case when the gap analysis has been run."""
    import tempfile
    from ..report import build_report
    d = _dept()
    raw = _dept_raw()
    book = load_cost_book()
    gap = store.cached("gap", {"dept": d.to_dict(), "book": book})
    reps = max(2, min(24, int(request.args.get("replications", 8))))
    out = Path(tempfile.mkdtemp()) / "decision_report.pdf"
    build_report(raw, out, replications=reps, seed=7, name=d.name, invest=gap)
    safe = "".join(c if c.isalnum() or c in " -_" else "-" for c in d.name)
    return send_file(out, as_attachment=True, download_name=f"{safe} - decision report.pdf")


# ---- Model ED Optimiser product ------------------------------------------- #
from ..department.config import Department, AREAS, CORE_NOTE
from ..department.builder import build as build_dept
from ..department.model_ed_gap import gap_analysis
from ..workforce.roles import ROLES, AREA_LABEL
from ..workforce.view import workforce_view
from ..ingest import trust_profile as trusts
from ..ingest import workbook as trust_workbook
from .. import model_params
from ..assist import run_what_if, auto_calibrate
from ..assist.nl import parse_question, EXAMPLES as ASK_EXAMPLES
from ..assist import llm as assist_llm
from ..assist import chat as assist_chat
from ..viz.flow_model import control_tower

CURRENT = {"dept": None}


def _dept() -> Department:
    """The saved department - one department shared by every surface, persisted
    across restarts (control tower, workforce, gaps, planner and analyst all
    model the same ED). Reloads from the store when present so multi-worker
    deployments never serve a stale in-memory copy."""
    saved = store.load_department()
    if saved:
        CURRENT["dept"] = Department.from_dict(saved)
    elif CURRENT["dept"] is None:
        CURRENT["dept"] = Department.default()
        store.save_department(CURRENT["dept"].to_dict())
    return CURRENT["dept"]


def _dept_raw():
    """The department's runnable pathway, with any stored calibration and
    service-time (pathway-parameter) overrides applied."""
    raw = build_dept(_dept())
    patch = _calibration_patch("your_department")
    if patch:
        raw = apply_patch(raw, patch)
    return model_params.apply_params(raw, model_params.load_params())


def _standards(dept, reps=5):
    """Plain headline standards for a department: good / typical / tough.
    Cached by configuration hash - the same set-up never simulates twice."""
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
        "lwbs": band("lwbs", hi=False),
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
    store.save_setting("data_source", {"kind": "manual",
                                       "label": "Set up by hand in the product"})
    return jsonify({"ok": True, "department": CURRENT["dept"].to_dict(), "version": version})


# --- data-driven set-up: pick your trust, or import an Excel/CSV workbook ------ #
@app.route("/api/trusts")
def api_trusts():
    """Trusts the product can pre-fill from the bundled NHS open-data snapshot."""
    return jsonify({"trusts": trusts.list_profiles()})


@app.route("/api/trust/select", methods=["POST"])
def api_trust_select():
    """Load a chosen trust's published figures as the saved department."""
    ods = (request.get_json(force=True) or {}).get("ods")
    try:
        profile = trusts.get_profile(ods)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    dept = trusts.to_department(profile)
    CURRENT["dept"] = dept
    version = store.save_department(dept.to_dict())
    store.clear_calibration("your_department")        # a fresh trust starts clean
    store.save_setting("data_source", {
        "kind": "trust", "ods": ods, "label": f"{profile.name} ({ods})",
        "source": profile.source, "as_of": profile.as_of})
    return jsonify({"ok": True, "department": dept.to_dict(), "version": version,
                    "provenance": trusts.provenance(profile), "notes": trusts.notes(profile),
                    "source": profile.source, "as_of": profile.as_of})


@app.route("/api/trust/template")
def api_trust_template():
    """Download the blank Excel set-up workbook (pre-filled with defaults)."""
    return send_file(io.BytesIO(trust_workbook.template_bytes()), as_attachment=True,
                     download_name="model_ed_department_template.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/trust/import", methods=["POST"])
def api_trust_import():
    """Set up the department from an uploaded Excel/CSV workbook (+ any arrivals
    it carries become a calibration)."""
    if "file" not in request.files:
        return jsonify({"error": "no file uploaded"}), 400
    f = request.files["file"]
    try:
        result = trust_workbook.read_workbook(f.read(), filename=f.filename)
    except Exception as e:
        return jsonify({"error": f"could not read workbook: {e}"}), 400
    dept = result["department"]
    CURRENT["dept"] = dept
    version = store.save_department(dept.to_dict())
    if result.get("patch"):
        store.save_calibration("your_department", result["patch"], result["summary"])
    else:
        store.clear_calibration("your_department")
    if result.get("cost_book"):
        save_cost_book(result["cost_book"])           # £ figures from the workbook
    if result.get("role_rates"):
        from ..workforce.roles import save_role_rates
        save_role_rates(result["role_rates"])         # staff hourly rates from the workbook
    if result.get("service_params"):
        model_params.save_params(result["service_params"])   # service-time assumptions
    store.save_setting("data_source", {
        "kind": "workbook", "label": f"Imported workbook: {f.filename or 'upload'}"})
    return jsonify({"ok": True, "department": dept.to_dict(), "version": version,
                    "summary": result["summary"], "provenance": result["provenance"]})


# --- editable Model ED standards (admin-level: the same for every trust) ------- #
def _scorecard_overrides() -> dict:
    return store.get_setting("scorecard_targets") or {}


@app.route("/api/scorecard-targets", methods=["GET", "POST"])
def api_scorecard_targets():
    """View or edit the RAG standard targets (target + amber band per metric).
    Data-driven so the standards can move (e.g. 4-hour 78% -> 95%) without code."""
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        valid = {d["key"] for d in scorecard_defaults()}
        clean = {}
        for key, ov in body.items():
            if key not in valid or not isinstance(ov, dict):
                continue
            row = {}
            for f in ("target", "amber"):
                if ov.get(f) is not None:
                    try:
                        row[f] = float(ov[f])
                    except (TypeError, ValueError):
                        pass
            if row:
                clean[key] = row
        store.save_setting("scorecard_targets", clean)
        return jsonify({"ok": True, "overrides": clean})
    return jsonify({"defaults": scorecard_defaults(), "overrides": _scorecard_overrides()})


@app.route("/api/pathway-params", methods=["GET", "POST"])
def api_pathway_params():
    """View or edit the model's service-time assumptions (global scale + per-stage
    means). Data-driven so the core physics can be tuned/calibrated without code;
    applied to every simulated surface (control tower, standards, analyst)."""
    from ..department.builder import BASE_RAW
    if request.method == "POST":
        saved = model_params.save_params(request.get_json(force=True) or {})
        return jsonify({"ok": True, "params": saved})
    return jsonify({"stages": model_params.service_params(BASE_RAW),
                    "params": model_params.load_params()})


# --- governance: data provenance, decision log, audit trail --------------------- #
@app.route("/api/data-status")
def api_data_status():
    """Where every number on screen comes from, when it last changed, and
    plain warnings when the model is still running on demonstration defaults -
    so nobody mistakes demo data for their own department."""
    src = store.get_setting("data_source")
    meta = store.department_meta()
    cal = store.get_calibration("your_department")
    overrides = {
        "service_times": bool(model_params.load_params()),
        "scorecard_targets": bool(store.get_setting("scorecard_targets")),
        "role_rates": bool(store.get_setting("role_rates")),
        "cost_book": bool(store.get_setting("cost_book")),
    }
    bm = store.get_setting("benchmarks")
    warnings = []
    if not src:
        warnings.append("The department is running on demonstration defaults - pick "
                        "your trust or import your data on “Set up my ED” before "
                        "using any figure operationally.")
    if not cal:
        warnings.append("No attendance calibration is loaded - arrival patterns and "
                        "acuity mix are modelled assumptions, not your recorded activity.")
    return jsonify({
        "source": src or {"kind": "demo", "label": "Demonstration defaults (Model ED, 320/day)"},
        "department": meta,                     # saved version + last-updated
        "calibration": ({"applied": True, "created_at": cal["created_at"],
                         "summary": cal["summary"]} if cal else {"applied": False}),
        "overrides": overrides,
        "benchmarks": {"uploaded": bool(bm and not bm.get("synthetic"))},
        "engine_version": store.ENGINE_VERSION,
        "warnings": warnings,
    })


@app.route("/api/actions", methods=["GET", "POST"])
def api_actions():
    """Operational decision log: append-only record of what the team decided
    (and the model state it was decided against). GET lists, POST records."""
    if request.method == "POST":
        body = request.get_json(force=True) or {}
        note = (body.get("note") or "").strip()
        if not note:
            return jsonify({"error": "a decision note is required"}), 400
        context = {"department": store.department_meta(),
                   "source": store.get_setting("data_source"),
                   "engine_version": store.ENGINE_VERSION}
        entry = store.log_action(note[:2000], author=(body.get("author") or "")[:128],
                                 context=context)
        return jsonify({"ok": True, "action": entry})
    return jsonify({"actions": store.list_actions(limit=int(request.args.get("limit", 100)))})


@app.route("/api/audit")
def api_audit():
    """Append-only audit trail of configuration changes (departments, targets,
    rates, service times) - governance for a shared deployment."""
    return jsonify({"audit": store.audit_trail(limit=int(request.args.get("limit", 100)))})


# --- AI assist ----------------------------------------------------------------- #
@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Ask a what-if in plain English. The question is translated into a scenario
    (rule-based; Claude fallback when configured), simulated against the saved
    department (paired Monte-Carlo vs baseline) and answered in plain language.
    Every number in the answer comes from the engine."""
    body = request.get_json(force=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify({"error": "no question given", "supported": ASK_EXAMPLES}), 400
    reps = max(2, min(24, int(body.get("replications", 6))))
    raw = _dept_raw()
    scenario, _notes = parse_question(question, raw)
    if scenario is None and not assist_llm.available():
        return jsonify({"error": "I couldn't turn that into a change I can simulate. "
                                 "Try phrasings like these:", "supported": ASK_EXAMPLES}), 400
    key = {"raw": raw, "q": question.lower(), "reps": reps, "llm": assist_llm.available()}
    out = store.cached_or_compute("ask", key, lambda: run_what_if(question, raw, reps=reps))
    if out.get("error"):
        return jsonify(out), 400
    return jsonify(out)


def _chat_provider() -> dict:
    """Named data feeds for the chatbot - each returns the product's own computed
    (mostly cached) numbers, so a chat answer can never disagree with a screen."""
    d = _dept()
    raw = _dept_raw()

    def pinch():
        ct = _control_tower_payload()          # cached by config hash after first run
        return {"bottleneck": ct.get("bottleneck"),
                "peak_hours": ct.get("bottleneck_peak_hours"),
                "headline": ct.get("headline_bottleneck"),
                "recommendation": ct.get("recommendation")}

    return {
        "department": lambda: {
            "name": d.name, "attendances_per_day": d.attendances_per_day,
            "inpatient_beds": d.inpatient_beds, "community_capacity": d.community_capacity,
            "areas_on": [AREAS[a]["label"] for a in d.enabled if a in AREAS]},
        "standards": lambda: _standards(d),
        "demand": lambda: {"per_day": round(sum(raw["arrivals"]["hourly_profile"]), 1),
                           "hourly": [round(h, 1) for h in raw["arrivals"]["hourly_profile"]]},
        "staffing": lambda: workforce_view(d),
        "pinch": pinch,
        "gaps": lambda: store.cached("gap", {"dept": d.to_dict(), "book": load_cost_book()}),
        "what_if": lambda q: run_what_if(q, raw, reps=4),
    }


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """The product chatbot: grounded answers about the configured department -
    demand, deployment, pinch point, standards, gaps, glossary, what-ifs.
    Offline router by default; Claude (when configured) for free-form questions."""
    body = request.get_json(force=True) or {}
    message = str(body.get("message", "")).strip()
    history = body.get("history") or []
    if not isinstance(history, list):
        history = []
    out = assist_chat.answer(message, history[-12:], _chat_provider())
    return jsonify(out)


@app.route("/api/auto-calibrate", methods=["POST"])
def api_auto_calibrate():
    """AI-assisted calibration: search the service-time scale until the modelled
    4-hour matches the trust's observed figure, then save it as the same
    data-driven override /api/pathway-params exposes (clear there to undo)."""
    body = request.get_json(force=True) or {}
    d = _dept()
    obs = body.get("observed_four_hour")
    if obs is None:
        m = re.search(r"\(([A-Z0-9]{3})\)", d.name or "")
        if m:
            try:
                obs = trusts.get_profile(m.group(1)).observed_four_hour_pct
            except KeyError:
                obs = None
    if obs is None:
        return jsonify({"error": "provide observed_four_hour (%), or pick a trust "
                                 "with a published 4-hour figure first"}), 400
    raw = build_dept(d)
    patch = _calibration_patch("your_department")
    if patch:
        raw = apply_patch(raw, patch)
    existing = model_params.load_params()
    keep = existing.get("service_mean") or None
    seeds = tuple(int(s) for s in (body.get("seeds") or (2, 3)))[:4] or (2,)
    res = auto_calibrate(raw, float(obs), seeds=seeds,
                         max_iter=max(1, min(10, int(body.get("max_iter", 6)))),
                         keep_means=keep)
    res["saved_params"] = model_params.save_params(
        {"service_scale": res["scale"], "service_mean": keep or {}})
    return jsonify(res)


def _control_tower_payload(seed=2):
    """The control-tower data for the saved department (cached by config hash);
    shared by the product control tower and the executive brief."""
    d = _dept()
    raw = _dept_raw()

    def compute():
        p = Pathway.from_dict(raw)
        res = run_cosim(p, seed=seed)
        ct = control_tower(res, p)
        diag = diagnose(res, p)
        ct["standards"] = _standards(d)
        ct["recommendation"] = diag["recommendation"]
        ct["headline_bottleneck"] = diag["headline"]
        return ct
    return store.cached_or_compute("control_tower", {"raw": raw, "seed": seed}, compute)


@app.route("/api/control-tower", methods=["POST"])
def api_control_tower():
    body = request.get_json(silent=True) or {}
    seed = int(body.get("seed", 2))
    return jsonify(_control_tower_payload(seed))


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
    # intraday: actual arrivals-by-hour so far replace the attendance guess
    projection = None
    so_far = body.get("arrivals_so_far")
    if so_far:
        from ..planning.operational import project_today
        projection = project_today([float(x) for x in so_far], department=d,
                                   calibration=patch)
        body["attendances_today"] = projection["projected_today"]
    args = {"attendances_today": float(body.get("attendances_today", d.attendances_per_day * 1.06)),
            "hospital_fullness_pct": float(body.get("hospital_fullness_pct", 94))}
    try:
        plan = store.cached_or_compute(
            "plan_today", {"dept": d.to_dict(), "patch": patch, **args},
            lambda: today_plan(**args, department=d, calibration=patch))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    if projection:
        plan = {**plan, "projection": projection}
    return jsonify(plan)


@app.route("/api/benchmarks", methods=["GET", "POST"])
def api_benchmarks():
    """Peer benchmark set: upload a CSV (organisation, attendances_per_day,
    four_hour_pct, twelve_hour_pct) or download the flagged synthetic sample."""
    from ..analysis.benchmark import read_benchmarks, generate_sample_benchmarks
    if request.method == "POST":
        if "file" not in request.files:
            return jsonify({"error": "no file uploaded"}), 400
        try:
            rows = read_benchmarks(request.files["file"].read())
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        store.save_setting("benchmarks", {"rows": rows, "synthetic": False})
        return jsonify({"saved": len(rows), "synthetic": False})
    buf = io.StringIO(); generate_sample_benchmarks().to_csv(buf, index=False)
    return app.response_class(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=benchmark_template.csv"})


def _benchmark_position(standards):
    """Position vs peers using the saved (or synthetic) benchmark set."""
    from ..analysis.benchmark import position, generate_sample_benchmarks
    saved = store.get_setting("benchmarks")
    rows = saved["rows"] if saved else generate_sample_benchmarks().to_dict("records")
    four = (standards.get("four_hour") or {}).get("typical")
    twelve = (standards.get("twelve_hour") or {}).get("typical", 0)
    if four is None:
        return None
    return position(rows, four, twelve, _dept().attendances_per_day,
                    synthetic=not bool(saved))


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    """The recommendation engine: CI-gated, costed changes for the configured
    department. Heavy on first run; cached by configuration hash after."""
    from ..optimise import recommend
    d = _dept()
    patch = _calibration_patch("your_department")
    book = load_cost_book()
    return jsonify(store.cached_or_compute(
        "recommend", {"dept": d.to_dict(), "patch": patch, "book": book},
        lambda: recommend(d, calibration=patch, book=book)))


@app.route("/api/surge", methods=["GET", "POST"])
def api_surge():
    """Stress tests: run a surge template against the configured department,
    optionally solving for the staffing that would hold the 4-hour target."""
    from ..planning.surge import TEMPLATES, stress_test, staff_to_hold
    if request.method == "GET":
        return jsonify({"templates": [{"key": k, "label": t["label"], "story": t["story"]}
                                      for k, t in TEMPLATES.items()]})
    body = request.get_json(force=True)
    key = body.get("template", "winter_norm")
    if key not in TEMPLATES:
        return jsonify({"error": f"unknown template {key}"}), 400
    d = _dept()
    patch = _calibration_patch("your_department")
    solve = bool(body.get("solve"))

    def compute():
        out = stress_test(d, key, calibration=patch)
        if solve:
            out["solver"] = staff_to_hold(d, key, calibration=patch, max_moves=4)
        return out
    cache_key = {"dept": d.to_dict(), "patch": patch, "template": key, "solve": solve}
    return jsonify(store.cached_or_compute("surge", cache_key, compute))


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
    # The technical model view, for analysts - defaulting to the user's own
    # department so it is connected to the product, not a separate model.
    pathways = {**_your_department_pathway_entry(), **list_pathways()}
    return render_template("dashboard.html", pathways=pathways)


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(force=True)
    p, sd_over, fb, raw = _build(body)
    seed = int(body.get("seed", 0))
    targets = _scorecard_overrides()

    def compute():
        res = run_cosim(p, seed=seed, feedback=fb, sd_overrides=sd_over)
        m = {**kpis(res, p), **uec_metrics(res, p)}
        conf = conformance_check(res, p)
        return {
            "kpis": m, "scorecard": uec_scorecard(m, targets), "diagnosis": diagnose(res, p),
            "sd_interpretation": sd_interpretation(res),
            "flow_model": flow_model_data(res, p),
            "conformance": {k: conf[k] for k in ("conformance_rate", "n_violations", "passed", "by_type")},
            "figures": {
                "sd_stocks": J(fig.sd_stocks_figure(res, p)),
                "sd_feedback": J(fig.sd_feedback_figure(res)),
                "utilisation": J(fig.utilisation_figure(res, p)),
                "waits": J(fig.waits_figure(res)),
                "sankey": J(fig.sankey_figure(res, p)),
                "heatmap": J(fig.occupancy_heatmap_figure(res, p)),
            }}
    key = {"raw": raw, "seed": seed, "feedback": fb, "sd": sd_over, "targets": targets}
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
                      f"{s['mean']:.1f}% (95% of weeks {s['ci_low']:.1f}-{s['ci_high']:.1f}%). "
                      + ("Wide spread - plan to the lower bound." if spread > 8
                         else "Reasonably tight - behaviour is predictable at this configuration."))
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
        return {"rows": cmp["rows"], "interpretation": scenario_interpret(cmp["rows"], tor),
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
    return jsonify({"conformance": conf, "variants": variant_timing(res),
                    "stage_timing": stage_timing(res, p)})


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
                           f"{round(d.attendances_per_day)} attendances/day - the control "
                           f"tower, workforce view and planner now all use your data.")
    except Exception as e:
        return jsonify({"error": f"could not calibrate: {e}"}), 400
    return jsonify({"summary": summary, "calibrated": True})


@app.route("/api/calibrate/reset", methods=["POST"])
def api_calibrate_reset():
    body = request.get_json(silent=True) or {}
    scope = body.get("pathway") or "your_department"
    store.clear_calibration(scope)
    return jsonify({"summary": ["Reset to synthetic baseline."], "calibrated": False})


def main():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)


if __name__ == "__main__":
    main()
