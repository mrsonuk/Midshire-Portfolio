"""
The Midshire demonstrator's web API and page. A separate Flask app with its
own database - it never imports the Cambridge server or touches its store.

Every response that carries numbers also carries the scenario id, the model
hash they were computed for and the run metadata, so the page can refuse to
show a response that belongs to an older edit or a different scenario.
"""
from __future__ import annotations

import copy
import csv
import gzip
import io
import json
import logging
import os
from pathlib import Path

from flask import Blueprint, Flask, Response, jsonify, render_template, request

from . import config as mcfg
from . import jobs
from . import metrics as M
from . import store
from .assistant import answer as ask_answer, format_whatif, NAME as ASK_NAME, SUGGESTIONS as ASK_SUGGESTIONS
from .build import BuildError, build_model, validate_inputs
from .optimise import MODES, rerank, search as run_search, search_key
from .packages import package_finance, apply_package, describe_changes, describe_package
from .runner import run as run_scenario, target_status, within_at
from ..workforce.costing import rota_cost, rate_table
from ..workforce.roles import ROLES, AREA_LABEL, CONTRACTED_HOURS, RATIO_RESOURCES
from ..workforce.rota import validate_rota, rota_from_csv, rota_to_csv, DAYS

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent.parent / "app"
bp = Blueprint("midshire", __name__)


def _asset_v():
    static = HERE / "static"
    try:
        return int(max(f.stat().st_mtime for f in static.glob("midshire*")))
    except ValueError:
        return 0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _err(msg, code=400, details=None):
    return jsonify({"error": msg, "details": details or []}), code


NOT_FOUND = "That scenario couldn't be found. It may have been deleted."


def _input_error(e):
    """A user-facing message for a request the model can't use. Never the
    Python exception text: that goes to the server log."""
    if isinstance(e, PermissionError):
        return _err(str(e), 403)
    if isinstance(e, BuildError):
        details = getattr(e, "details", None)
        msg = str(e)
        if details or not msg[:1].isupper():
            msg = "These inputs can't be modelled. Please check the highlighted fields."
        return _err(msg, 400, details)
    if isinstance(e, LookupError):
        return _err(NOT_FOUND, 404)
    log.warning("Midshire request refused: %s: %s", type(e).__name__, e)
    return _err("That request couldn't be completed. Please check the inputs and try again.", 400)


def _scenario(sid):
    sc = store.get_scenario(sid or store.BASELINE_ID)
    if sc is None:
        raise LookupError(f"no scenario {sid!r}")
    return sc


def _inputs_from_body(body):
    """Inputs from a request: either a saved scenario id, or explicit draft
    inputs (validated, never trusted). Drafts must keep the scenario shape."""
    if body.get("inputs") is not None:
        inp = body["inputs"]
        if not isinstance(inp, dict):
            raise BuildError("inputs must be an object")
        base = mcfg.baseline_inputs()
        allowed = set(base)
        unknown = set(inp) - allowed
        if unknown:
            raise BuildError(f"unknown input sections: {sorted(unknown)}")
        merged = copy.deepcopy(base)
        merged.update(copy.deepcopy(inp))
        # fixed parts of the demonstrator a draft may not redefine
        merged["fixture_version"] = base["fixture_version"]
        merged["pathway_version"] = base["pathway_version"]
        merged["cohort"]["name"] = "adult"
        merged["areas"]["enabled"] = [a for a in merged["areas"]["enabled"] if a != "paeds"]
        return merged, body.get("scenario_id")
    sc = _scenario(body.get("scenario_id"))
    return sc["inputs"], sc["id"]


def _target(body, inputs):
    t = body.get("target") or inputs.get("target") or mcfg.fixture()["target"]
    try:
        out = {"pct": float(t["pct"]), "minutes": int(t["minutes"])}
    except (TypeError, ValueError, KeyError):
        raise BuildError("Please enter a percentage and a time for the target.")
    if not (0 < out["pct"] <= 100) or out["minutes"] % 15 or not (15 <= out["minutes"] <= 1440):
        raise BuildError("The target must be between 1% and 100%, within a time of up to 24 hours in 15-minute steps.")
    return out


def _cached_run(inputs, seeds=None):
    seeds = list(seeds or inputs["engine"]["selection_seeds"])
    return store.get_run(mcfg.model_hash(inputs), seeds)


def _run_job(inputs, seeds=None, seed_set="selection", label="Running the model"):
    seeds = list(seeds or inputs["engine"]["selection_seeds"])
    mh = mcfg.model_hash(inputs)
    build_model(inputs)                    # fail fast: invalid inputs never start a job

    def fn(progress, cancelled):
        progress(label, 0.02)
        res = run_scenario(inputs, seeds=seeds, seed_set=seed_set, cancel=cancelled,
                           progress=lambda d, n: progress(label, d / n))
        if cancelled():
            return None
        store.put_run(res)
        return {"model_hash": mh, "seeds": seeds}
    return jobs.start("run", f"run:{store.run_key(mh, seeds)}", fn,
                      meta={"model_hash": mh, "seeds": seeds})


def _attach_view(result, inputs, scenario_id):
    """Add the target verdict and finance (cheap, never re-simulated)."""
    out = dict(result)
    out["scenario_id"] = scenario_id
    out["target_status"] = target_status(result, inputs["target"])
    base = store.get_scenario(store.BASELINE_ID)["inputs"]
    out["finance"] = {
        "rota": rota_cost(inputs["rota"], inputs["cost_table"]),
        "baseline_rota": rota_cost(base["rota"], inputs["cost_table"]),
    }
    out["finance"]["rota"].pop("rows", None)
    out["finance"]["baseline_rota"].pop("rows", None)
    out["finance_hash"] = mcfg.finance_hash(inputs)
    return out


# --------------------------------------------------------------------------- #
# page and metadata
# --------------------------------------------------------------------------- #
@bp.route("/")
def page():
    f = mcfg.fixture()
    return render_template("midshire.html", title=f["product_title"], status=f["status_line"],
                           asset_v=_asset_v())


@bp.route("/favicon.ico")
def favicon():
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
           "<rect width='64' height='64' rx='8' fill='#005eb8'/>"
           "<text x='32' y='42' font-family='Arial' font-size='26' font-weight='bold' "
           "fill='#fff' text-anchor='middle'>M</text></svg>")
    return Response(svg, mimetype="image/svg+xml")


@bp.route("/api/m/meta")
def meta():
    f = mcfg.fixture()
    roles = {k: {"label": v["label"], "staffs": v["staffs"],
                 "staffs_label": AREA_LABEL.get(v["staffs"], v["staffs"]),
                 "ratio": v["staffs"] in RATIO_RESOURCES,
                 "contracted_hours": CONTRACTED_HOURS.get(k)}
             for k, v in ROLES.items() if not k.startswith("paeds")}
    return jsonify({
        "product_title": f["product_title"], "positioning": f["positioning"],
        "status_line": f["status_line"], "disclaimers": f["disclaimers"],
        "demo_id": f["demo_id"], "demo_id_note": f["demo_id_note"],
        "fixture_version": f["fixture_version"], "fixture_hash": mcfg.fixture_hash(),
        "foundation": f["foundation"], "cohort": f["cohort"], "areas": f["areas"],
        "capacity_provenance": f["capacity"]["provenance"],
        "space_staffing_note": f["space_staffing"]["note"],
        "downstream": f["downstream"], "sdec": f["sdec"], "mental_health": f["mental_health"],
        "rota_convention": f["rota"]["convention"], "rota_provenance": f["rota"]["provenance"],
        "cost_status": f["cost_table"]["status"], "cost_inclusions": f["cost_table"]["inclusions"],
        "estates": f["estates"], "target": f["target"], "engine": f["engine"],
        "search": {"note": f["search"]["note"], "max_steps": f["search"]["max_steps"],
                   "reps": f["search"]["reps"], "guardrails": f["search"]["guardrails"],
                   "levers": [{"id": l["id"], "title": l["title"], "kind": l["kind"]}
                              for l in f["search"]["levers"]],
                   "modes": {k: v["label"] for k, v in MODES.items()}},
        "groups": f["groups"], "milestones": f["milestones"], "outcomes": f["outcomes"],
        "flow_units": mcfg.flow_units(), "flow_note": f["flow_map"]["note"],
        "lever_text": {k: v for k, v in f.get("lever_text", {}).items() if k != "note"},
        "footer": f.get("footer", f["product_title"]),
        "node_groups": mcfg.node_groups(),
        "labels": f["labels"], "definitions": M.DEFINITIONS, "roles": roles, "days": DAYS,
        "assistant": ASK_NAME, "assistant_suggestions": ASK_SUGGESTIONS, "step_minutes": M.STEP,
        "storage": {"database": store.url().split("///")[-1].split("/")[-1],
                    "note": "Separate from the Cambridge build's database."},
    })


# --------------------------------------------------------------------------- #
# scenarios: list, read, save, delete, reset, apply
# --------------------------------------------------------------------------- #
@bp.route("/api/m/scenarios", methods=["GET", "POST"])
def scenarios():
    if request.method == "GET":
        return jsonify({"scenarios": _scenario_cards(),
                        "applied": store.get_setting("applied") or store.BASELINE_ID})
    body = request.get_json(force=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return _err("Please give the scenario a name.")
    try:
        inputs, _ = _inputs_from_body(body)
        errs = validate_inputs(inputs)
        if errs:
            return _err("Some inputs need fixing before this can run.", 400, errs)
        sc = store.save_scenario(name, inputs, note=str(body.get("note") or ""),
                                 sid=body.get("id") if body.get("id") != store.BASELINE_ID else None)
        store.mark_shown(sc["id"])
    except PermissionError as e:
        return _err(str(e), 403)
    except BuildError as e:
        return _input_error(e)
    return jsonify({"ok": True, "scenario": sc})


def _scenario_info(note: str) -> dict:
    """A scenario's description: {why, look_for} as saved, or a plain note."""
    try:
        d = json.loads(note or "")
        if isinstance(d, dict):
            return {k: str(v) for k, v in d.items() if k in ("why", "look_for") and v}
    except (ValueError, TypeError):
        pass
    return {"why": note} if note else {}


def _scenario_cards() -> list[dict]:
    """Every scenario with what it changes (computed from its inputs), why
    you would test it, whether the picker shows it, and its result if run."""
    base = store.get_scenario(store.BASELINE_ID)
    shown = set(store.shown_ids())
    base_run = _cached_run(base["inputs"])
    out = []
    for row in store.list_scenarios():
        sc = store.get_scenario(row["id"])
        card = {k: v for k, v in row.items() if k != "note"}
        card["info"] = _scenario_info(row.get("note"))
        card["changes"] = [] if row["id"] == store.BASELINE_ID else describe_changes(base["inputs"], sc["inputs"])
        card["shown"] = row["id"] == store.BASELINE_ID or row["id"] in shown
        res = _cached_run(sc["inputs"])
        if res is not None:
            tgt = sc["inputs"]["target"]
            w = within_at(res, tgt["minutes"])
            card["result"] = {"within_pct": M.summarise(w)["mean"], "target": tgt}
            if base_run is not None and row["id"] != store.BASELINE_ID:
                d = M.paired_delta(within_at(base_run, tgt["minutes"]), w)
                card["result"]["delta_pts"] = d["mean"] if d else None
        out.append(card)
    return out


@bp.route("/api/m/scenarios/<sid>", methods=["GET", "DELETE"])
def scenario(sid):
    if request.method == "DELETE":
        try:
            ok = store.delete_scenario(sid)
        except PermissionError as e:
            return _err(str(e), 403)
        if store.get_setting("applied") == sid:
            store.save_setting("applied", store.BASELINE_ID)
        return jsonify({"ok": ok})
    sc = store.get_scenario(sid)
    if sc is None:
        return _err(NOT_FOUND, 404)
    return jsonify({"scenario": sc})


@bp.route("/api/m/reset", methods=["POST"])
def reset():
    sc = store.ensure_baseline(reset=True)
    store.save_setting("applied", store.BASELINE_ID)
    return jsonify({"ok": True, "scenario": sc, "applied": store.BASELINE_ID,
                    "note": "Back to the baseline. Your saved scenarios are still in the list below."})


@bp.route("/api/m/apply", methods=["POST"])
def apply_scenario():
    body = request.get_json(force=True) or {}
    sid = body.get("scenario_id") or store.BASELINE_ID
    if store.get_scenario(sid) is None:
        return _err(NOT_FOUND, 404)
    store.save_setting("applied", sid)
    store.mark_shown(sid)
    return jsonify({"ok": True, "applied": sid})


# --------------------------------------------------------------------------- #
# validation and instant (no-simulation) preview of rota, capacity and cost
# --------------------------------------------------------------------------- #
@bp.route("/api/m/preview", methods=["POST"])
def preview():
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    errs = validate_inputs(inputs)
    out = {"model_hash": mcfg.model_hash(inputs), "finance_hash": mcfg.finance_hash(inputs),
           "errors": errs, "scenario_id": sid, "request_id": body.get("request_id")}
    if errs:
        return jsonify(out)
    try:
        m = build_model(inputs)
    except BuildError as e:
        out["errors"] = e.details or [{"error": str(e)}]
        return jsonify(out)
    base = store.get_scenario(store.BASELINE_ID)["inputs"]
    bm = build_model(base)
    cost = rota_cost(inputs["rota"], inputs["cost_table"])
    bcost = rota_cost(base["rota"], inputs["cost_table"])
    staff = sorted({ROLES[r["role"]]["staffs"] for r in inputs["rota"]} |
                   {ROLES[r["role"]]["staffs"] for r in base["rota"]})
    out.update({
        "warnings": m.warnings,
        "staffing": {s: {"label": AREA_LABEL.get(s, s), "week": m.staffing_week.get(s, [0] * 168),
                         "baseline_week": bm.staffing_week.get(s, [0] * 168)} for s in staff},
        "spaces": {r: {"label": AREA_LABEL.get(r, r.replace("_", " ")),
                       "open_week": m.open_capacity.get(r), "physical_week": m.physical.get(r),
                       "baseline_open_week": bm.open_capacity.get(r)}
                   for r in m.open_capacity if r not in ROLES and not any(
                       ROLES[k]["staffs"] == r for k in ROLES)},
        "cost": {k: v for k, v in cost.items() if k != "rows"},
        "baseline_cost": {k: v for k, v in bcost.items() if k != "rows"},
        "rows_cost": cost["rows"],
        "rates": rate_table(inputs["cost_table"]),
        "simulated": _cached_run(inputs) is not None,
    })
    return jsonify(out)


@bp.route("/api/m/rota/import", methods=["POST"])
def rota_import():
    if "file" in request.files:
        text = request.files["file"].read().decode("utf-8-sig", errors="replace")
    else:
        text = (request.get_json(force=True) or {}).get("csv", "")
    if len(text) > 200_000:
        return _err("That file is too large for a rota (the limit is 200 KB).")
    rows, errors = rota_from_csv(text)
    return jsonify({"rows": rows, "errors": errors, "ok": not errors and bool(rows)})


# --------------------------------------------------------------------------- #
# simulation: cached result, or a background job
# --------------------------------------------------------------------------- #
@bp.route("/api/m/run", methods=["POST"])
def run():
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
        errs = validate_inputs(inputs)
        if errs:
            return _err("Some inputs need fixing before this can run.", 400, errs)
        seeds = None
        seed_set = body.get("seed_set", "selection")
        if seed_set == "validation":
            seeds = inputs["engine"]["validation_seeds"]
        if sid:
            store.mark_shown(sid)
        hit = _cached_run(inputs, seeds)
        if hit is not None:
            return jsonify({"status": "done", "result": _attach_view(hit, inputs, sid),
                            "request_id": body.get("request_id")})
        job = _run_job(inputs, seeds, seed_set)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    return jsonify({"status": "running", "job": job, "model_hash": mcfg.model_hash(inputs),
                    "request_id": body.get("request_id")})


@bp.route("/api/m/result", methods=["POST"])
def result():
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    hit = _cached_run(inputs)
    if hit is None:
        return jsonify({"status": "not_simulated", "model_hash": mcfg.model_hash(inputs),
                        "request_id": body.get("request_id")})
    return jsonify({"status": "done", "result": _attach_view(hit, inputs, sid),
                    "request_id": body.get("request_id")})


@bp.route("/api/m/jobs/<jid>", methods=["GET"])
def job_status(jid):
    j = jobs.get(jid)
    if j is None:
        return _err("That run is no longer available. Please start it again.", 404)
    return jsonify(j)


@bp.route("/api/m/jobs/<jid>/cancel", methods=["POST"])
def job_cancel(jid):
    return jsonify({"ok": jobs.cancel(jid)})


# --------------------------------------------------------------------------- #
# comparison: baseline vs scenarios, from the SAME saved baseline and seeds
# --------------------------------------------------------------------------- #
def _comparison_row(name, sid, kind, inputs, base_sc, base, target):
    res = _cached_run(inputs)
    if res is None:
        return None
    w = within_at(res, target["minutes"])
    bw = within_at(base, target["minutes"])
    recs = [{"rota_rows": [], "estate": [], "title": name, "kind": "scenario"}]
    # money: the scenario's own cost tables price BOTH rotas
    fin = package_finance(base_sc["inputs"], inputs, recs, cost_inputs=inputs)
    est = _estate_diff(base_sc["inputs"], inputs)
    s = res["summary"]
    hrs = lambda rota: rota_cost(rota, {})["rows"]
    return {
        "id": sid, "name": name, "kind": kind, "model_hash": res["model_hash"],
        "result_source": res.get("result_source"), "run_id": res["run_id"],
        "replications": res["replications"], "seeds": res["seeds"],
        "target_measure": M.summarise(w),
        "delta_vs_baseline_pts": M.paired_delta(bw, w) if sid != store.BASELINE_ID else None,
        "target_status": target_status(res, target),
        "remaining_gap_pts": round(target["pct"] - M.summarise(w)["mean"], 2),
        "twelve_hour": s["twelve_hour"], "duration_median": s["duration_median"],
        "total_wait_median": s["total_wait_median"], "lwbs": s["lwbs"],
        "wip_end": s["wip_end"], "handover_45": s["handover_45"],
        "extra_paid_hours_week": round(sum(r["paid_hours_week"] for r in hrs(inputs["rota"]))
                                       - sum(r["paid_hours_week"] for r in hrs(base_sc["inputs"]["rota"])), 1),
        "extra_shifts_week": sum(r["shifts_week"] for r in hrs(inputs["rota"]))
        - sum(r["shifts_week"] for r in hrs(base_sc["inputs"]["rota"])),
        "weekly_pay_delta": fin["weekly_pay_delta"], "annual_pay_delta": fin["annual_pay_delta"],
        "pay_fully_costed": fin["fully_costed"],
        "estate": est, "capital": est["capital"], "recurring_non_pay_annual": est["recurring"],
        "not_costed": sorted(set(est["not_costed"] + ([] if fin["fully_costed"] else fin["not_costed"]))),
    }


COMPARE_NOTE = ("Each scenario is compared with the baseline on the same patient arrivals, so the "
                "difference comes from the changes rather than chance. Differences are in percentage points.")


def comparison_rows(ids: list[str], target: dict, extra: list | None = None) -> dict:
    base_sc = store.get_scenario(store.BASELINE_ID)
    base = _cached_run(base_sc["inputs"])
    rows, missing = [], []
    items = [(store.get_scenario(sid), None) for sid in
             [store.BASELINE_ID] + [i for i in ids if i != store.BASELINE_ID]]
    items = [(sc, None) for sc, _ in items if sc is not None] + [(e, None) for e in (extra or [])]
    for sc, _ in items:
        row = None if base is None else _comparison_row(sc["name"], sc["id"], sc["kind"],
                                                        sc["inputs"], base_sc, base, target)
        if row is None:
            missing.append({"id": sc["id"], "name": sc["name"]})
        else:
            rows.append(row)
    return {"rows": rows, "missing": missing, "target": target, "note": COMPARE_NOTE}


def _estate_diff(base_inputs, inputs):
    items = inputs["estates"]["items"]
    rows, cap, rec, nc = [], 0, 0, []
    for k, v in inputs["capacity"].items():
        b = int(base_inputs["capacity"].get(k, 0))
        if int(v) != b:
            it = items.get(k, {})
            q = int(v) - b
            c = None if it.get("capital") is None else it["capital"] * max(0, q)
            r = None if it.get("recurring_non_pay") is None else it["recurring_non_pay"] * q
            rows.append({"item": k, "label": it.get("label", k), "change": q, "capital": c, "recurring": r})
            cap += c or 0
            rec += r or 0
            if c is None and q > 0:
                nc.append(f"{it.get('label', k)} capital")
            if r is None:
                nc.append(f"{it.get('label', k)} running cost")
    for k in ("inpatient_beds",):
        b, v = base_inputs["downstream"].get(k), inputs["downstream"].get(k)
        if v != b:
            it = items.get(k, {})
            q = v - b
            r = None if it.get("recurring_non_pay") is None else it["recurring_non_pay"] * q
            rows.append({"item": k, "label": it.get("label", k), "change": q, "capital": None, "recurring": r})
            rec += r or 0
            nc.append(f"{it.get('label', k)} capital")
    if inputs["downstream"].get("ward_discharge_capacity_per_hour") != base_inputs["downstream"].get(
            "ward_discharge_capacity_per_hour"):
        rows.append({"item": "ward_discharge_pct", "label": items["ward_discharge_pct"]["label"],
                     "change": None, "capital": None, "recurring": None})
        nc.append(items["ward_discharge_pct"]["label"])
    for a, h in inputs["areas"]["hours"].items():
        if base_inputs["areas"]["hours"].get(a) != h:
            rows.append({"item": f"hours.{a}", "label": f"{a.upper()} opening hours",
                         "change": f"{h[0]:02d}:00-{h[1]:02d}:00", "capital": 0, "recurring": 0})
    return {"rows": rows, "capital": cap, "recurring": rec, "not_costed": sorted(set(nc))}


@bp.route("/api/m/compare-draft", methods=["POST"])
def compare_draft():
    """Baseline vs an unsaved draft (simulated, not saved)."""
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
        target = _target(body, inputs)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    out = comparison_rows([], target, extra=[{"id": "draft", "name": "Your changes",
                                              "kind": "draft", "inputs": inputs}])
    out["changes"] = describe_changes(store.get_scenario(store.BASELINE_ID)["inputs"], inputs)
    out["model_hash"] = mcfg.model_hash(inputs)
    out["request_id"] = body.get("request_id")
    return jsonify(out)


@bp.route("/api/m/compare", methods=["POST"])
def compare():
    body = request.get_json(force=True) or {}
    try:
        base = store.get_scenario(store.BASELINE_ID)["inputs"]
        target = _target(body, base)
    except BuildError as e:
        return _input_error(e)
    ids = [str(i) for i in (body.get("scenario_ids") or [])][:6]
    return jsonify(comparison_rows(ids, target))


# --------------------------------------------------------------------------- #
# package search
# --------------------------------------------------------------------------- #
def _search_cached(inputs, target, mode):
    key = search_key(inputs, target, mode)
    hit = store.get_blob(key)
    if hit is None:
        return None
    # prices are always re-applied from the CURRENT cost tables: a cost edit
    # re-ranks without re-simulating and can never leave stale £ on screen
    out = rerank(hit, inputs["cost_table"], inputs["estates"])
    out["search_key"] = key
    out["result_source"] = hit.get("result_source")
    out["finance_hash"] = mcfg.finance_hash(inputs)
    return out


def _start_search(inputs, target, mode):
    key = search_key(inputs, target, mode)

    def fn(progress, cancelled):
        res = run_search(inputs, target, progress=progress, cancel=cancelled, mode=mode)
        res["search_key"] = key
        store.put_blob(key, mcfg.model_hash(inputs), res)
        store.put_run(res["package_run"])
        return {"search_key": key}
    return jobs.start("search", key, fn, meta={"target": target, "mode": mode,
                                               "model_hash": mcfg.model_hash(inputs)})


@bp.route("/api/m/search", methods=["POST"])
def search():
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
        target = _target(body, inputs)
        mode = body.get("mode", "combined")
        if mode not in MODES:
            return _err("Please choose which kind of changes to test.")
        errs = validate_inputs(inputs)
        if errs:
            return _err("Some inputs need fixing before this can run.", 400, errs)
        hit = _search_cached(inputs, target, mode)
        if hit is not None and not body.get("rerun"):
            hit.pop("package_run", None)
            return jsonify({"status": "done", "result": hit, "scenario_id": sid,
                            "request_id": body.get("request_id")})
        build_model(inputs)
        job = _start_search(inputs, target, mode)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    return jsonify({"status": "running", "job": job, "request_id": body.get("request_id")})


@bp.route("/api/m/search/save", methods=["POST"])
def search_save():
    """Turn a tested package into a named scenario (the actual proposed rota
    and estate). The baseline is untouched."""
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    ids = body.get("lever_ids") or []
    fx = {l["id"]: l for l in mcfg.fixture()["search"]["levers"]}
    if not ids or any(i not in fx for i in ids):
        return _err("There is no package to save yet.")
    pkg, recs = apply_package(inputs, [fx[i] for i in sorted(ids)])
    target = body.get("target")
    d = describe_package(sorted(ids), body.get("mode"), target if isinstance(target, dict) else None,
                         body.get("outcome"))
    name = str(body.get("name") or d["name"]).strip()[:200]
    note = json.dumps({"why": d["why"], "look_for": d["look_for"]})
    sc = store.save_scenario(name, pkg, note=note)
    store.mark_shown(sc["id"])
    return jsonify({"ok": True, "scenario": {k: v for k, v in sc.items() if k != "inputs"}})


@bp.route("/api/m/retime", methods=["POST"])
def retime():
    """The separate re-timing alternative for a tested package (paid hours held
    constant where feasible). Returned as draft inputs - nothing is saved."""
    from .packages import retime_alternative
    body = request.get_json(force=True) or {}
    try:
        inputs, sid = _inputs_from_body(body)
    except (BuildError, LookupError) as e:
        return _input_error(e)
    fx = {l["id"]: l for l in mcfg.fixture()["search"]["levers"]}
    ids = [i for i in body.get("lever_ids") or [] if i in fx]
    if not ids:
        return _err("There is no package to save yet.")
    _, recs = apply_package(inputs, [fx[i] for i in sorted(ids)])
    staff_recs = [r for r in recs if r["rota_rows"] and not r["estate"] and not r["hours"]]
    out = retime_alternative(inputs, staff_recs)
    skipped = [r["title"] for r in recs if r not in staff_recs]
    if skipped:
        out["infeasible"] += [f"{t}: an estate, opening-hours or hospital change cannot be re-timed" for t in skipped]
    return jsonify(out)


# --------------------------------------------------------------------------- #
# Ask My ED
# --------------------------------------------------------------------------- #
@bp.route("/api/m/ask", methods=["POST"])
def ask():
    body = request.get_json(force=True) or {}
    msg = str(body.get("message") or "")
    try:
        inputs, sid = _inputs_from_body(body)
        sc = store.get_scenario(sid) if sid else None
    except (BuildError, LookupError) as e:
        return _input_error(e)
    sc = sc or {"id": sid, "name": "Unsaved draft", "inputs": inputs}
    res = _cached_run(inputs)
    tgt = inputs["target"]

    def start_whatif(new_inputs, titles, notes):
        seeds = inputs["engine"]["selection_seeds"]
        if _cached_run(inputs) is None:
            _run_job(inputs, label="Running the current scenario")
        job = _run_job(new_inputs, label="Testing the change")
        jobs._jobs[job["id"]]["meta"].update({"whatif": True, "titles": titles, "notes": notes,
                                              "base_hash": mcfg.model_hash(inputs),
                                              "new_inputs": new_inputs, "base_inputs": inputs})
        return job

    base_sc = store.get_scenario(store.BASELINE_ID)
    ctx = {"inputs": inputs, "scenario": sc, "result": res, "target": tgt,
           "view": body.get("view"), "baseline_result": _cached_run(base_sc["inputs"]),
           "search": lambda t: _search_cached(inputs, {"pct": t["pct"], "minutes": t["minutes"]}, t["mode"]),
           "start_search": lambda t: _start_search(inputs, {"pct": t["pct"], "minutes": t["minutes"]}, t["mode"]),
           "start_whatif": start_whatif}
    out = ask_answer(msg, ctx)
    out.update({"scenario_id": sid, "model_hash": mcfg.model_hash(inputs),
                "run_id": res["run_id"] if res else None})
    if out.get("job"):
        out["job"] = {k: v for k, v in out["job"].items() if k != "meta"}
    return jsonify(out)


@bp.route("/api/m/ask/whatif/<jid>", methods=["GET"])
def ask_whatif(jid):
    j = jobs._jobs.get(jid)
    if j is None:
        return _err("That run is no longer available. Please start it again.", 404)
    if j["status"] != "done":
        return jsonify({"status": j["status"], "message": j["message"], "error": j.get("error")})
    m = j["meta"]
    base = _cached_run(m["base_inputs"])
    new = _cached_run(m["new_inputs"])
    if base is None:
        return jsonify({"status": "running", "message": "Waiting for the current scenario to finish"})
    reply = format_whatif(base, new, m["base_inputs"]["target"], m.get("notes") or [], m["titles"])
    return jsonify({"status": "done", "reply": reply, "intent": "what_if",
                    "model_hash": m["base_hash"], "run_ids": [base["run_id"], new["run_id"]]})


# --------------------------------------------------------------------------- #
# exports (CSV / JSON) - all from the same structured results
# --------------------------------------------------------------------------- #
def _download(data, name, mime):
    return Response(data, mimetype=mime,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@bp.route("/api/m/export/<kind>", methods=["GET"])
def export(kind):
    sid = request.args.get("scenario_id") or store.BASELINE_ID
    sc = store.get_scenario(sid)
    if sc is None:
        return _err(NOT_FOUND, 404)
    slug = "".join(ch if ch.isalnum() else "_" for ch in sc["name"].lower())[:40]
    inputs = sc["inputs"]
    if kind == "inputs.json":
        return _download(json.dumps({"scenario": {k: v for k, v in sc.items() if k != "inputs"},
                                     "inputs": inputs}, indent=2),
                         f"midshire_{slug}_inputs.json", "application/json")
    if kind == "rota.csv":
        return _download(rota_to_csv(inputs["rota"]), f"midshire_{slug}_rota.csv", "text/csv")
    res = _cached_run(inputs)
    if kind == "results.json":
        if res is None:
            return _err("Run this scenario first.", 409)
        out = _attach_view(res, inputs, sid)
        out["metric_definitions"] = M.DEFINITIONS
        return _download(json.dumps(out), f"midshire_{slug}_results.json", "application/json")
    if kind == "comparison.csv":
        ids = [x for x in (request.args.get("ids") or "").split(",") if x]
        cmp = comparison_rows(ids or [sid], inputs["target"])
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["scenario", "result_source", "replications", "target_pct", "target_minutes",
                    "within_target_mean_pct", "within_target_min", "within_target_max",
                    "delta_vs_baseline_pts", "delta_ci_low", "delta_ci_high", "remaining_gap_pts",
                    "over_12h_pct", "median_duration_min", "median_total_wait_min", "lwbs_pct",
                    "unfinished_at_end", "extra_paid_hours_week", "extra_shifts_week",
                    "weekly_pay_delta_gbp", "annual_pay_delta_gbp", "capital_gbp",
                    "recurring_non_pay_annual_gbp", "not_costed"])
        for r in cmp["rows"]:
            d = r["delta_vs_baseline_pts"] or {}
            w.writerow([r["name"], r["result_source"], r["replications"], cmp["target"]["pct"],
                        cmp["target"]["minutes"], round(r["target_measure"]["mean"], 2),
                        round(r["target_measure"]["min"], 2), round(r["target_measure"]["max"], 2),
                        round(d.get("mean", 0), 2) if d else "", round(d["ci_low"], 2) if "ci_low" in d else "",
                        round(d["ci_high"], 2) if "ci_high" in d else "", r["remaining_gap_pts"],
                        round(r["twelve_hour"]["mean"], 2), round(r["duration_median"]["mean"], 1),
                        round(r["total_wait_median"]["mean"], 1), round(r["lwbs"]["mean"], 2),
                        round(r["wip_end"]["mean"], 1), r["extra_paid_hours_week"], r["extra_shifts_week"],
                        r["weekly_pay_delta"], r["annual_pay_delta"], r["capital"],
                        r["recurring_non_pay_annual"], "; ".join(r["not_costed"])])
        return _download(buf.getvalue(), f"midshire_comparison.csv", "text/csv")
    return _err("That export isn't available.", 404)


# --------------------------------------------------------------------------- #
# app factory + precomputed fixtures
# --------------------------------------------------------------------------- #
def load_precomputed() -> dict:
    """Load the committed, clearly labelled precomputed results. A file whose
    model hash no longer matches the current inputs and engine is NOT loaded
    (it would be a stale result): the page then shows "not yet simulated"
    and rerunning produces fresh numbers."""
    status = {"loaded": [], "stale": []}
    man = mcfg.PRECOMPUTED_DIR / "manifest.json"
    if not man.exists():
        return status
    manifest = json.loads(man.read_text())
    for entry in manifest.get("scenarios", []):
        inputs = json.loads(gzip.decompress((mcfg.PRECOMPUTED_DIR / entry["inputs"]).read_bytes()))
        if entry["id"] != store.BASELINE_ID:
            if entry.get("ids"):          # name and description from the current wording, not a stored copy
                d = describe_package(entry["ids"], entry.get("mode"), entry.get("target"), entry.get("outcome"))
                entry = dict(entry, name=d["name"][:200], note=json.dumps({"why": d["why"], "look_for": d["look_for"]}))
            have = store.get_scenario(entry["id"])
            if have is None or (have["kind"] == "precomputed" and
                                (have["name"] != entry["name"] or have.get("note") != entry.get("note", ""))):
                store.save_scenario(entry["name"], inputs, kind="precomputed", note=entry.get("note", ""),
                                    sid=entry["id"])
    for entry in manifest.get("runs", []) + manifest.get("searches", []):
        payload = json.loads(gzip.decompress((mcfg.PRECOMPUTED_DIR / entry["file"]).read_bytes()))
        inputs = json.loads(gzip.decompress((mcfg.PRECOMPUTED_DIR / entry["inputs"]).read_bytes()))
        if mcfg.model_hash(inputs) != payload.get("model_hash") and entry["kind"] == "run":
            status["stale"].append(entry["file"])
            continue
        if entry["kind"] == "run":
            store.put_run(payload, source="precomputed")
        else:
            key = search_key(inputs, payload["target"], payload["bounds"]["mode"])
            if payload.get("search_key") != key:
                status["stale"].append(entry["file"])
                continue
            store.put_blob(key, mcfg.model_hash(inputs), payload, source="precomputed")
            if payload.get("package_run"):
                store.put_run(payload["package_run"], source="precomputed")
        status["loaded"].append(entry["file"])
    return status


def create_app(db_url: str | None = None, load_fixtures: bool = True) -> Flask:
    app = Flask(__name__, template_folder=str(HERE / "templates"),
                static_folder=str(HERE / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024        # requests are untrusted input
    store.init(db_url, force=db_url is not None)
    if load_fixtures:
        app.config["PRECOMPUTED"] = load_precomputed()
    app.register_blueprint(bp)

    @app.errorhandler(Exception)
    def _unexpected(e):
        """Anything unexpected: a short message on screen, the detail in the log."""
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return jsonify({"error": "That page or request isn't available.", "details": []}), e.code
        log.exception("Midshire: unexpected error")
        return jsonify({"error": "Something went wrong. Please try again.", "details": []}), 500

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'")
        return resp
    return app


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Midshire University Hospitals Trust Control Tower (demo)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5050)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--check", action="store_true", help="start, load fixtures, report and exit")
    a = ap.parse_args()
    app = create_app()
    if a.check:
        c = app.test_client()
        r = c.get("/")
        m = c.get("/api/m/meta").get_json()
        print(f"page HTTP {r.status_code}; {m['product_title']}; fixtures {app.config.get('PRECOMPUTED')}; "
              f"database {store.url()}")
        return 0 if r.status_code == 200 else 1
    print(f"Midshire demonstrator on http://{a.host}:{a.port}  (database: {store.url()})")
    app.run(host=a.host, port=a.port, debug=False, threaded=True)
    return 0
