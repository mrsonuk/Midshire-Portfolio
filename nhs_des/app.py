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

import glob
import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .engine import Pathway, run_pathway
from .metrics import kpis
from .montecarlo import monte_carlo
from .scenarios import apply_scenario, compare_scenarios
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


def _build(pathway_key: str, overrides: dict | None, arrivals_scale: float) -> Pathway:
    base = Pathway.load(PATHWAY_DIR / f"{pathway_key}.json")
    scenario = {"name": "configured",
                "resources": {k: int(v) for k, v in (overrides or {}).items()},
                "arrivals_scale": arrivals_scale}
    return apply_scenario(base, scenario) if (overrides or arrivals_scale != 1.0) else base


@app.route("/")
def home():
    return render_template("dashboard.html", pathways=list_pathways())


@app.route("/api/pathways")
def api_pathways():
    return jsonify(list_pathways())


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    body = request.get_json(force=True)
    pathway = _build(body["pathway"], body.get("overrides"),
                     float(body.get("arrivals_scale", 1.0)))
    result = run_pathway(pathway, seed=int(body.get("seed", 0)))
    return jsonify({
        "kpis": kpis(result, pathway),
        "figures": {
            "sankey": json.loads(viz.sankey_figure(result, pathway).to_json()),
            "occupancy": json.loads(viz.occupancy_figure(result, pathway).to_json()),
            "utilisation": json.loads(viz.utilisation_figure(result, pathway).to_json()),
            "waits": json.loads(viz.waits_figure(result).to_json()),
        },
    })


@app.route("/api/montecarlo", methods=["POST"])
def api_montecarlo():
    body = request.get_json(force=True)
    pathway = _build(body["pathway"], body.get("overrides"),
                     float(body.get("arrivals_scale", 1.0)))
    reps = int(body.get("replications", 30))
    mc = monte_carlo(pathway, replications=reps, base_seed=1000)
    return jsonify({
        "summary": mc["summary"],
        "figure": json.loads(viz.montecarlo_figure(mc).to_json()),
        "los_figure": json.loads(
            viz.montecarlo_figure(mc, "mean_los", "mean time in dept (min)").to_json()),
    })


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
