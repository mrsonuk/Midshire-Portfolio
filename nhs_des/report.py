"""
Decision report (PDF) for the planning team.

The beta tool produced a PDF; this restores that as a *decision* document, not a
parameter dump. Two pages:

    1. A plain-English executive summary - headline KPIs, the named bottleneck and
       recommendation, and a ranked scenario table answering "what should we do?".
    2. The full visual dashboard snapshot (flow, occupancy, Monte-Carlo, scenarios).

Run:  python -m nhs_des.report nhs_des/pathways/emergency_department.json out.pdf
"""
from __future__ import annotations

if __package__ in (None, ""):
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
    __package__ = "nhs_des"

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .engine import Pathway, run_pathway
from .metrics import kpis, diagnose, uec_scorecard
from .montecarlo import monte_carlo
from .scenarios import compare_scenarios
from .snapshot import (build_snapshot, _default_scenarios,
                       NHS_BLUE, NHS_DARK_BLUE, NHS_GREY, NHS_GREEN, NHS_RED)


def _clean(text: str) -> str:
    """Strip the lightweight HTML tags the diagnosis uses for the web UI."""
    return text.replace("<b>", "").replace("</b>", "")


def _summary_page(pdf, pathway, base_kpi, mc, diag, cmp, scorecard):
    fig = plt.figure(figsize=(11.69, 8.27), dpi=150)  # A4 landscape
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()

    ax.add_patch(plt.Rectangle((0, 0.92), 1, 0.08, color=NHS_BLUE))
    ax.text(0.03, 0.957, "NHS", fontsize=20, weight="bold", color=NHS_BLUE,
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none"))
    ax.text(0.10, 0.965, "Patient Flow Simulator — Decision Report", fontsize=18,
            color="white", weight="bold", va="center")
    ax.text(0.10, 0.935, pathway.name, fontsize=11, color="#CFE6F7", va="center")

    y = 0.86
    ax.text(0.03, y, "Executive summary", fontsize=14, color=NHS_DARK_BLUE, weight="bold")
    y -= 0.04
    cl = mc["summary"]["target_compliance"]
    ll = mc["summary"]["mean_los"]
    four = "MEETS" if base_kpi['target_compliance'] >= 78 else "BELOW"
    twelve = "MEETS" if base_kpi['pct_over_12h'] < 10 else "BELOW"
    lines = [
        f"Modelled demand: {base_kpi['throughput_per_day']:.0f} attendances/day "
        f"({base_kpi['n_patients']:,} patients over the simulated period).",
        f"4-hour standard: {base_kpi['target_compliance']:.0f}% [{four} the >=78% target]; "
        f"95% CI {cl['ci_low']:.0f}-{cl['ci_high']:.0f}% over {mc['replications']} runs; "
        f"{base_kpi['breaches']:,} breaches.",
        f"Mean time in department: {base_kpi['mean_los']/60:.1f} h "
        f"(95% CI {ll['ci_low']/60:.1f}-{ll['ci_high']/60:.1f} h); "
        f"95th percentile {base_kpi['p95_los']/60:.1f} h.",
        f"Admitted: {base_kpi['admit_rate']:.0f}% of attendances.",
    ]
    for ln in lines:
        ax.text(0.04, y, "•  " + ln, fontsize=10.5, color=NHS_GREY); y -= 0.032

    y -= 0.02
    ax.text(0.03, y, "Bottleneck diagnosis", fontsize=14, color=NHS_DARK_BLUE, weight="bold")
    y -= 0.038
    ax.text(0.04, y, _clean(diag["headline"]), fontsize=10.5, color=NHS_GREY,
            wrap=True); y -= 0.032
    ax.text(0.04, y, "Recommendation: " + _clean(diag["recommendation"]), fontsize=10.5,
            color=NHS_DARK_BLUE, wrap=True); y -= 0.05

    # UEC cohort scorecard (RAG)
    rag = {"green": NHS_GREEN, "amber": "#ED8B00", "red": NHS_RED}
    ax.text(0.03, y, "UEC Plan 2025/26 scorecard", fontsize=14, color=NHS_DARK_BLUE,
            weight="bold"); y -= 0.036
    for s in scorecard:
        arrow = ">=" if s["higher_better"] else "<"
        ax.text(0.04, y, f"{s['label']}: {s['value']:.0f}{s['unit']} "
                f"(target {arrow}{s['target']:.0f}{s['unit']})", fontsize=10, color=NHS_GREY)
        ax.text(0.62, y, s["status"].upper(), fontsize=10, weight="bold",
                color=rag.get(s["status"], NHS_GREY)); y -= 0.026
    y -= 0.02

    # scenario table
    ax.text(0.03, y, "What-if scenarios (ranked)", fontsize=14, color=NHS_DARK_BLUE,
            weight="bold"); y -= 0.04
    ax.text(0.04, y, "Scenario", fontsize=10, weight="bold", color=NHS_GREY)
    ax.text(0.52, y, "4-hr perf.", fontsize=10, weight="bold", color=NHS_GREY)
    ax.text(0.66, y, "vs baseline", fontsize=10, weight="bold", color=NHS_GREY)
    ax.text(0.82, y, "Mean LOS", fontsize=10, weight="bold", color=NHS_GREY); y -= 0.028
    base_val = cmp["rows"][0]["target_compliance"]
    for r in cmp["rows"]:
        delta = r["target_compliance"] - base_val
        col = NHS_GREY if r["scenario"] == "Baseline" else (NHS_GREEN if delta >= 0 else NHS_RED)
        ax.text(0.04, y, r["scenario"], fontsize=10, color=NHS_GREY)
        ax.text(0.52, y, f"{r['target_compliance']:.0f}%", fontsize=10, color=NHS_GREY)
        ax.text(0.66, y, ("—" if r["scenario"] == "Baseline" else f"{delta:+.0f} pts"),
                fontsize=10, color=col, weight="bold")
        ax.text(0.82, y, f"{r['mean_los']/60:.1f} h", fontsize=10, color=NHS_GREY)
        y -= 0.028

    ax.text(0.03, 0.03, "For demonstration — synthetic data seeded from the beta "
            "config.json. Validate against local data before operational use.",
            fontsize=8, color=NHS_GREY)
    pdf.savefig(fig, facecolor="white"); plt.close(fig)


def build_report(pathway_file: str, out_pdf: str, replications: int = 24,
                 scenarios: list | None = None, seed: int = 7) -> str:
    pathway = Pathway.load(pathway_file)
    base = run_pathway(pathway, seed=seed)
    base_kpi = kpis(base, pathway)
    diag = diagnose(base, pathway)
    if scenarios is None:
        scenarios = _default_scenarios(pathway, diag["constraint"])
    mc = monte_carlo(pathway, replications=replications, base_seed=1000)
    cmp = compare_scenarios(pathway, scenarios,
                            replications=max(6, replications // 4), seed=2000)
    scorecard = uec_scorecard(base_kpi, base, pathway)

    Path(out_pdf).parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_pdf) as pdf:
        _summary_page(pdf, pathway, base_kpi, mc, diag, cmp, scorecard)
        # Visual dashboard page (reuse the snapshot figure)
        fig = build_snapshot(pathway_file, "", replications=replications,
                             scenarios=scenarios, seed=seed, return_fig=True)
        pdf.savefig(fig, facecolor=fig.get_facecolor())
        plt.close(fig)
        d = pdf.infodict()
        d["Title"] = f"NHS Patient Flow Simulator — {pathway.name}"
        d["Subject"] = "Decision report"
    return out_pdf


if __name__ == "__main__":
    import sys
    pf = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "pathways" / "emergency_department.json")
    out = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).parent / "outputs" / "decision_report.pdf")
    print("Building decision report...")
    print("Saved:", build_report(pf, out))
