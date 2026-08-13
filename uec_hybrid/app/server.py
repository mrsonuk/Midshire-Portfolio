"""
Flask app for the Model ED Optimiser, trimmed to two screens: the control
tower (live flow map, standards, what-if, chatbot) and Set up my ED (pick a
trust, import a workbook, or configure by hand). Everything runs offline.
"""
from __future__ import annotations

import copy
import io
import os
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

from ..des.pathway import Pathway
from ..coupling.cosim import run_cosim
from ..analysis.metrics import (kpis, diagnose,
                                sd_interpretation, stage_timing)
from ..analysis.montecarlo import monte_carlo
from ..demand.ecds_seam import apply_patch
from ..platform import store
from ..finance import load_cost_book, save_cost_book

app = Flask(__name__)
PATHWAY_DIR = Path(__file__).resolve().parent.parent / "pathways"
store.init_db()


def _calibration_patch(scope):
    cal = store.get_calibration(scope)
    return cal["patch"] if cal else None


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


# ---- Model ED Optimiser product ------------------------------------------- #
from ..department.config import Department, AREAS, CORE_NOTE
from ..department.builder import build as build_dept
from ..workforce.roles import ROLES, AREA_LABEL
from ..workforce.view import workforce_view
from ..ingest import published
from ..ingest import trust_profile as trusts
from ..ingest import workbook as trust_workbook
from .. import model_params
from ..assist import run_what_if, auto_calibrate
from ..assist.nl import parse_question, parse_target, EXAMPLES as ASK_EXAMPLES
from ..assist import llm as assist_llm
from ..assist import chat as assist_chat
from ..viz.flow_model import control_tower

CURRENT = {"dept": None}


def _dept() -> Department:
    """The saved department, shared by the control tower and Set up my ED and
    persisted across restarts. Reloads from the store when present so
    multi-worker deployments never serve a stale in-memory copy."""
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
    store.save_setting("provenance", None)      # hand edits invalidate field-level provenance
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
    # a fresh trust starts clean, then any committed aggregates for it (the
    # trust's own extracts or published distributions, e.g. data/cuh/ for RGT
    # via rgt_published.json) are applied as the calibration - picking your
    # trust must load everything the build already knows about it
    store.clear_calibration("your_department")
    cal_summary = []
    agg = published.load_aggregates(ods)
    if agg:
        patch, cal_summary = published.patch_from_aggregates(
            agg, dept.attendances_per_day)
        store.save_calibration("your_department", patch, cal_summary)
    store.save_setting("data_source", {
        "kind": "trust", "ods": ods, "label": f"{profile.name} ({ods})",
        "source": profile.source, "as_of": profile.as_of})
    store.save_setting("provenance", {"rows": trusts.provenance(profile),
                                      "notes": trusts.notes(profile)})
    return jsonify({"ok": True, "department": dept.to_dict(), "version": version,
                    "provenance": trusts.provenance(profile), "notes": trusts.notes(profile),
                    "calibration_summary": cal_summary,
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
    # like picking the trust from the list: any committed aggregates for the
    # workbook's ODS code fill in whatever the workbook itself didn't carry
    # (ambulance share, admission rates...) - the workbook wins where both have
    # a value, so an upload is never poorer than the drop-down
    patch, summary = result.get("patch"), list(result["summary"])
    ods = result.get("ods_code")
    agg = published.load_aggregates(ods) if ods else None
    if agg:
        from ..ingest.seed import _merge_patch
        apatch, asummary = published.patch_from_aggregates(agg, dept.attendances_per_day)
        patch = _merge_patch(apatch, patch or {})
        summary += asummary
    from ..ingest.seed import PATCH_PARTS
    if patch and any(patch.get(k) for k in PATCH_PARTS):
        store.save_calibration("your_department", patch, summary)
    else:
        store.clear_calibration("your_department")
    result["summary"] = summary
    if result.get("cost_book"):
        save_cost_book(result["cost_book"])           # £ figures from the workbook
    if result.get("role_rates"):
        from ..workforce.roles import save_role_rates
        save_role_rates(result["role_rates"])         # staff hourly rates from the workbook
    if result.get("service_params"):
        model_params.save_params(result["service_params"])   # service-time assumptions
    store.save_setting("data_source", {
        "kind": "workbook", "label": f"Imported workbook: {f.filename or 'upload'}"})
    store.save_setting("provenance", {"rows": result["provenance"], "notes": []})
    return jsonify({"ok": True, "department": dept.to_dict(), "version": version,
                    "summary": result["summary"], "provenance": result["provenance"]})


# --- editable Model ED standards (admin-level: the same for every trust) ------- #
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
    d = _dept()
    prov = store.get_setting("provenance") or {}
    warnings = []
    if not src:
        warnings.append("The department is running on demonstration defaults - pick "
                        "your trust or import your data on “Set up my ED” before "
                        "using any figure operationally.")
    if not cal:
        warnings.append("No attendance calibration is loaded - arrival patterns and "
                        "acuity mix are modelled assumptions, not your recorded activity.")
    # a calibration built from labelled synthetic placeholders must never pass
    # for real recorded activity - keep saying so until real data replaces it
    cal_synthetic = bool(cal and any("SYNTHETIC" in s for s in (cal.get("summary") or [])))
    if cal_synthetic:
        warnings.append("The loaded calibration is built from SYNTHETIC placeholder "
                        "figures - arrival patterns and case mix are illustrative "
                        "until the trust's real extracts replace them.")
    if not (d.capacity or {}):
        warnings.append("Physical capacity (cubicles, CDU beds, resus bays…) is "
                        "scaled from the Model ED template, not your real counts - "
                        "fill the Capacity sheet of the set-up workbook.")
    # what is still an assumption, at a glance - the honest label the demo wears
    assumed = []
    if not (d.capacity or {}):
        assumed.append("physical capacity")
    if not cal:
        assumed.append("arrival profile & acuity mix")
    elif cal_synthetic:
        assumed.append("arrival profile & case mix (SYNTHETIC calibration)")
    if not overrides["service_times"]:
        assumed.append("service times")
    if not overrides["cost_book"]:
        assumed.append("cost book (£)")
    if not overrides["role_rates"]:
        assumed.append("staff hourly rates")
    assumed += sorted({str(r.get("field")) for r in (prov.get("rows") or [])
                       if str(r.get("source", "")).startswith("template default")
                       and not str(r.get("field")).startswith("capacity")})
    return jsonify({
        "source": src or {"kind": "demo", "label": "Demonstration defaults (Model ED, 320/day)"},
        "department": meta,                     # saved version + last-updated
        "calibration": ({"applied": True, "created_at": cal["created_at"],
                         "summary": cal["summary"]} if cal else {"applied": False}),
        "overrides": overrides,
        "benchmarks": {"uploaded": bool(bm and not bm.get("synthetic"))},
        "engine_version": store.ENGINE_VERSION,
        "provenance": prov,                     # per-field rows from the last import
        "assumed": assumed,                     # plain-language "still assumptions"
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
def _target_plan(target: float, reps: int = 4) -> dict:
    """The "what would it take" answer for the saved department, cached like
    every other heavy result (and reusing the cached recommendation run)."""
    from ..optimise.recommend import recommend, target_plan
    d = _dept()
    patch = _calibration_patch("your_department")
    book = load_cost_book()
    rec = store.cached_or_compute(
        "recommend", {"dept": d.to_dict(), "patch": patch, "book": book, "reps": reps},
        lambda: recommend(d, calibration=patch, book=book, reps=reps))
    return store.cached_or_compute(
        "target_plan", {"dept": d.to_dict(), "patch": patch, "book": book,
                        "target": float(target), "reps": reps},
        lambda: target_plan(d, target, calibration=patch, book=book,
                            reps=reps, rec=rec))


@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Ask a what-if in plain English. The question is translated into a scenario
    (rule-based;  fallback when configured), simulated against the saved
    department (paired Monte-Carlo vs baseline) and answered in plain language.
    Every number in the answer comes from the engine."""
    body = request.get_json(force=True) or {}
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify({"error": "no question given", "supported": ASK_EXAMPLES}), 400
    reps = max(2, min(24, int(body.get("replications", 6))))
    target = parse_target(question)
    if target is not None:
        return jsonify(_target_plan(target, reps=max(2, min(4, reps))))
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
        "target": lambda q: (lambda t: _target_plan(t) if t is not None else None)(parse_target(q)),
    }


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """The product chatbot: grounded answers about the configured department -
    demand, deployment, pinch point, standards, gaps, glossary, what-ifs.
    Offline router by default;  (when configured) for free-form questions."""
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


@app.route("/api/control-tower", methods=["POST"])
def api_control_tower():
    body = request.get_json(silent=True) or {}
    seed = int(body.get("seed", 2))
    return jsonify(_control_tower_payload(seed))


def main():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)


if __name__ == "__main__":
    main()
