"""
Flask web dashboard for the redesigned NHS Patient Flow Simulator.

A single-page, NHS-styled interface that replaces the original canvas animation
with decision-grade analytics:

    * choose any pathway (config-driven - no code change to add one)
    * adjust resource capacities and demand, run a simulation
    * see headline KPIs, an interactive patient-flow Sankey, live occupancy,
      utilisation and queue-wait charts
    * run a Monte-Carlo batch for confidence intervals
    * compare what-if scenarios side by side

Run:  python -m nhs_des.app   (then open http://127.0.0.1:5000)
"""
from __future__ import annotations

# Allow running directly (``python app.py`` / ``python -m app``) as well as
# ``python -m nhs_des.app``.
if __package__ in (None, ""):
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
    __package__ = "nhs_des"

import copy
import glob
import io
import json
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from .engine import Pathway, run_pathway
from .metrics import kpis, diagnose, uec_scorecard, flow_map_data
from .montecarlo import monte_carlo
from .scenarios import apply_scenario, compare_scenarios
from .animation import animation_figure
from .report import build_report
from .calibration import read_table, calibrate, generate_sample
from . import visualize as viz

app = Flask(__name__)
PATHWAY_DIR = Path(__file__).parent / "pathways"


def list_pathways() -> dict:
    out = {}
    for f in sorted(glob.glob(str(PATHWAY_DIR / "*.json"))):
        key = Path(f).stem
        with open(f) as fh:
            data = json.load(fh)
        out[key] = {
            "key": key,
            "name": data.get("name", key),
            "description": data.get("description", ""),
            "resources": data.get("resources", {}),
            "file": f,
        }
    return out


def _occupancy_factor(occ: float) -> float:
    """Map hospital bed occupancy (%) to a multiplier on the time admitted
    patients wait for an inpatient bed. Waits stay flat up to ~85% then climb
    steeply as the hospital fills - the classic exit-block / corridor-care curve
    the UEC Plan targets. 85%→x1.0, 92%→~x1.4, 95%→~x2, 99%→~x3.7."""
    occ = max(70.0, min(99.5, float(occ)))
    return 1.0 + 1.8 * (max(0.0, occ - 85.0) / 10.0) ** 1.7


# Calibration overlays keyed by pathway: a full pathway dict re-derived from an
# uploaded data extract. Replaces the synthetic defaults until reset.
CALIBRATIONS: dict[str, dict] = {}


def _base_raw(pathway_key: str) -> dict:
    if pathway_key in CALIBRATIONS:
        return copy.deepcopy(CALIBRATIONS[pathway_key])
    return copy.deepcopy(Pathway.load(PATHWAY_DIR / f"{pathway_key}.json").raw)


def _build(pathway_key: str, overrides: dict | None, arrivals_scale: float,
           size: float = 1.0, occupancy: float | None = None) -> Pathway:
    raw = _base_raw(pathway_key)
    base_name = raw.get("name", pathway_key)

    # ED size preset: scale every physical/staff capacity together.
    if size and abs(size - 1.0) > 1e-6:
        for r, cap in raw.get("resources", {}).items():
            raw["resources"][r] = max(1, int(round(cap * size)))

    # Bed occupancy: stretch the time admitted patients wait for an inpatient bed.
    if occupancy is not None:
        f = _occupancy_factor(occupancy)
        for node in raw.get("nodes", []):
            if "await" in node.get("id", "") and isinstance(node.get("service"), dict):
                for k in ("mean", "stdev"):
                    if k in node["service"]:
                        node["service"][k] = node["service"][k] * f

    pathway = Pathway.from_dict(raw)
    scenario = {"name": "configured",
                "resources": {k: int(v) for k, v in (overrides or {}).items()},
                "arrivals_scale": arrivals_scale}
    if overrides or arrivals_scale != 1.0:
        pathway = apply_scenario(pathway, scenario)
    pathway.name = base_name
    return pathway


@app.route("/")
def home():
    return render_template("dashboard.html", pathways=list_pathways())


@app.route("/api/pathways")
def api_pathways():
    return jsonify(list_pathways())


def _pathway_from_body(body):
    return _build(body["pathway"], body.get("overrides"),
                  float(body.get("arrivals_scale", 1.0)),
                  size=float(body.get("size", 1.0)),
                  occupancy=(float(body["occupancy"]) if body.get("occupancy") else None))


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(force=True)
    pathway = _pathway_from_body(body)
    result = run_pathway(pathway, seed=int(body.get("seed", 0)))
    kpi = kpis(result, pathway)
    return jsonify({
        "kpis": kpi,
        "scorecard": uec_scorecard(kpi, result, pathway),
        "diagnosis": diagnose(result, pathway),
        "flow_map": flow_map_data(result, pathway),
        "figures": {
            "occupancy": json.loads(viz.occupancy_figure(result, pathway).to_json()),
            "utilisation": json.loads(viz.utilisation_figure(result, pathway).to_json()),
            "waits": json.loads(viz.waits_figure(result).to_json()),
        },
    })


def _simulate_payload(pathway):
    result = run_pathway(pathway, seed=0)
    kpi = kpis(result, pathway)
    return {
        "kpis": kpi,
        "scorecard": uec_scorecard(kpi, result, pathway),
        "diagnosis": diagnose(result, pathway),
        "flow_map": flow_map_data(result, pathway),
        "figures": {
            "occupancy": json.loads(viz.occupancy_figure(result, pathway).to_json()),
            "utilisation": json.loads(viz.utilisation_figure(result, pathway).to_json()),
            "waits": json.loads(viz.waits_figure(result).to_json()),
        },
    }


@app.route("/api/sample-data")
def api_sample_data():
    """Download the synthetic ECDS-style template, so the expected schema for
    real hospital data is self-documenting."""
    buf = io.StringIO()
    generate_sample().to_csv(buf, index=False)
    return app.response_class(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sample_ecds_template.csv"})


@app.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    """Calibrate a pathway from an uploaded attendance extract, replacing the
    synthetic defaults, then return a fresh simulation with the change summary."""
    key = request.form.get("pathway")
    if "file" not in request.files:
        return jsonify({"error": "no file uploaded"}), 400
    try:
        df = read_table(request.files["file"].read())
        base = copy.deepcopy(Pathway.load(PATHWAY_DIR / f"{key}.json").raw)
        calibrated, summary = calibrate(df, base)
        CALIBRATIONS[key] = calibrated
    except Exception as e:  # surface a clean message to the UI
        return jsonify({"error": f"could not calibrate: {e}"}), 400
    payload = _simulate_payload(_build(key, None, 1.0))
    payload["summary"] = summary
    payload["calibrated"] = True
    return jsonify(payload)


@app.route("/api/calibrate/reset", methods=["POST"])
def api_calibrate_reset():
    key = request.get_json(force=True).get("pathway")
    CALIBRATIONS.pop(key, None)
    payload = _simulate_payload(_build(key, None, 1.0))
    payload["summary"] = ["Reset to synthetic baseline parameters."]
    payload["calibrated"] = False
    return jsonify(payload)


@app.route("/api/animation", methods=["POST"])
def api_animation():
    body = request.get_json(force=True)
    pathway = _pathway_from_body(body)
    result = run_pathway(pathway, seed=int(body.get("seed", 5)))
    return jsonify({"figure": json.loads(animation_figure(result, pathway).to_json())})


@app.route("/api/montecarlo", methods=["POST"])
def api_montecarlo():
    body = request.get_json(force=True)
    pathway = _pathway_from_body(body)
    reps = int(body.get("replications", 30))
    mc = monte_carlo(pathway, replications=reps, base_seed=1000)
    c = mc["summary"]["target_compliance"]
    spread = c["ci_high"] - c["ci_low"]
    interpretation = (
        f"Across {reps} independent runs (each a different random week), 4-hour "
        f"performance averaged {c['mean']:.1f}% and fell between "
        f"{c['ci_low']:.1f}% and {c['ci_high']:.1f}% on 95% of runs "
        f"(range {c['min']:.0f}-{c['max']:.0f}%). "
        + ("That is a wide spread, so a single simulation can mislead — plan to the "
           "lower end of the interval." if spread > 8 else
           "The spread is fairly tight, so the system behaves predictably at this "
           "configuration."))
    return jsonify({
        "summary": mc["summary"],
        "interpretation": interpretation,
        "figure": json.loads(viz.montecarlo_figure(mc).to_json()),
        "los_figure": json.loads(
            viz.montecarlo_figure(mc, "mean_los", "mean time in dept (min)").to_json()),
    })


@app.route("/api/report")
def api_report():
    key = request.args.get("pathway")
    overrides = json.loads(request.args.get("overrides", "{}"))
    scale = float(request.args.get("arrivals_scale", 1.0))
    pathway = _build(key, overrides, scale)
    # Persist the configured pathway so the report renderers can load it by path.
    tmp_json = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(pathway.raw, tmp_json)
    tmp_json.close()
    out_pdf = os.path.join(tempfile.gettempdir(), f"{key}_decision_report.pdf")
    build_report(tmp_json.name, out_pdf, replications=16)
    return send_file(out_pdf, as_attachment=True,
                     download_name=f"{key}_decision_report.pdf")


@app.route("/api/scenarios", methods=["POST"])
def api_scenarios():
    body = request.get_json(force=True)
    base = Pathway.load(PATHWAY_DIR / f"{body['pathway']}.json")
    scenarios = body.get("scenarios", [])
    reps = int(body.get("replications", 10))
    cmp = compare_scenarios(base, scenarios, replications=reps, seed=2000)
    return jsonify({
        "rows": cmp["rows"],
        "compliance_fig": json.loads(viz.scenario_figure(cmp).to_json()),
        "los_fig": json.loads(viz.scenario_figure(
            cmp, "mean_los", "mean time in dept (min)", higher_better=False).to_json()),
    })


def main():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
