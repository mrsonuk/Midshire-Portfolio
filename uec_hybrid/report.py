"""
PDF decision report for the planning team. Two pages: an executive summary
(headline KPIs, UEC scorecard, bottleneck, exit-block status, ranked scenarios)
and a System-Dynamics page (bed occupancy and feedback over time).

Run: python -m uec_hybrid.report [pathway.json] [out.pdf]
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .des.pathway import Pathway
from .coupling.cosim import run_cosim
from .analysis.metrics import kpis, uec_metrics, uec_scorecard, diagnose
from .analysis.montecarlo import monte_carlo
from .analysis.scenarios import compare_scenarios
from .viz.palette import NHS_BLUE, NHS_DARK, NHS_GREEN, NHS_ORANGE, NHS_RED, NHS_GREY, NHS_AQUA

RAG = {"green": NHS_GREEN, "amber": NHS_ORANGE, "red": NHS_RED}


def _clean(t):
    return t.replace("<b>", "").replace("</b>", "")


def build_report(pathway_file, out_pdf, replications=16, seed=7):
    p = Pathway.load(pathway_file)
    res = run_cosim(p, seed=seed)
    m = {**kpis(res, p), **uec_metrics(res, p)}
    diag = diagnose(res, p)
    scorecard = uec_scorecard(m)
    mc = monte_carlo(p, replications=replications, base_seed=1000)
    cmp = compare_scenarios(p, [
        {"name": "+40 inpatient beds", "sd": {"inpatient_beds": p.sd.get("inpatient_beds", 320) + 40}},
        {"name": "+30% community capacity", "sd": {"community_capacity": int(p.sd.get("community_capacity", 60) * 1.3),
                                                   "community_clearance_per_hour": 6}},
        {"name": "Winter +15% demand", "arrivals_scale": 1.15},
    ], replications=max(6, replications // 2))

    Path(out_pdf).parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_pdf) as pdf:
        _summary_page(pdf, p, m, diag, scorecard, mc, cmp)
        _sd_page(pdf, p, res)
        d = pdf.infodict()
        d["Title"] = f"UEC Hybrid Simulator — {p.name}"
    return out_pdf


def _summary_page(pdf, p, m, diag, scorecard, mc, cmp):
    fig = plt.figure(figsize=(11.69, 8.27), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.add_patch(plt.Rectangle((0, 0.92), 1, 0.08, color=NHS_BLUE))
    ax.text(0.03, 0.957, "NHS", fontsize=19, weight="bold", color=NHS_BLUE, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none"))
    ax.text(0.10, 0.963, "UEC Hybrid Simulator — Decision Report", fontsize=17, color="white", weight="bold", va="center")
    ax.text(0.10, 0.935, p.name, fontsize=11, color="#CFE6F7", va="center")

    y = 0.87
    s4 = mc["summary"].get("four_hour", {})
    lines = [
        f"Modelled demand: {m['throughput_per_day']:.0f} attendances/day ({m['n_patients']:,} over the simulated period).",
        f"4-hour standard: {m['four_hour']:.0f}% (95% CI {s4.get('ci_low',0):.0f}-{s4.get('ci_high',0):.0f}% over {mc['replications']} weeks); {m['breaches']:,} breaches.",
        f"12-hour waits {m['twelve_hour']:.1f}%; admitted {m['admit_rate']:.0f}%; mean LOS {m['mean_los']/60:.1f} h.",
        f"Inpatient bed occupancy {m.get('bed_occupancy',0):.0f}% — the System-Dynamics driver of ED exit-block.",
    ]
    ax.text(0.03, y, "Executive summary", fontsize=14, color=NHS_DARK, weight="bold"); y -= 0.038
    for ln in lines:
        ax.text(0.04, y, "•  " + ln, fontsize=10.5, color=NHS_GREY); y -= 0.03

    y -= 0.015
    ax.text(0.03, y, "Bottleneck diagnosis", fontsize=14, color=NHS_DARK, weight="bold"); y -= 0.034
    ax.text(0.04, y, _clean(diag["headline"]), fontsize=10.5, color=NHS_GREY); y -= 0.028
    ax.text(0.04, y, "Recommendation: " + _clean(diag["recommendation"]), fontsize=10.5, color=NHS_DARK); y -= 0.045

    ax.text(0.03, y, "UEC scorecard vs national standards", fontsize=14, color=NHS_DARK, weight="bold"); y -= 0.032
    for s in scorecard:
        a = "≥" if s["higher_better"] else "<"
        ax.text(0.04, y, f"{s['label']}: {s['value']:.0f}{s['unit']} (target {a}{s['target']:.0f}{s['unit']})",
                fontsize=9.5, color=NHS_GREY)
        ax.text(0.62, y, s["status"].upper(), fontsize=9.5, weight="bold", color=RAG[s["status"]]); y -= 0.0235
    y -= 0.01

    ax.text(0.03, y, "What-if scenarios", fontsize=14, color=NHS_DARK, weight="bold"); y -= 0.032
    base = cmp["rows"][0]["four_hour"]
    ax.text(0.04, y, "Scenario", fontsize=9.5, weight="bold", color=NHS_GREY)
    ax.text(0.55, y, "4-hour", fontsize=9.5, weight="bold", color=NHS_GREY)
    ax.text(0.72, y, "vs baseline", fontsize=9.5, weight="bold", color=NHS_GREY)
    ax.text(0.88, y, "bed occ", fontsize=9.5, weight="bold", color=NHS_GREY); y -= 0.026
    for r in cmp["rows"]:
        d = r["four_hour"] - base
        col = NHS_GREY if r["scenario"] == "Baseline" else (NHS_GREEN if d >= 0 else NHS_RED)
        ax.text(0.04, y, r["scenario"], fontsize=9.5, color=NHS_GREY)
        ax.text(0.55, y, f"{r['four_hour']:.0f}%", fontsize=9.5, color=NHS_GREY)
        ax.text(0.72, y, "—" if r["scenario"] == "Baseline" else f"{d:+.0f} pts", fontsize=9.5, weight="bold", color=col)
        ax.text(0.88, y, f"{r.get('bed_occupancy',0):.0f}%", fontsize=9.5, color=NHS_GREY); y -= 0.024

    ax.text(0.03, 0.03, "Hybrid SD+DES model — synthetic data grounded in the NHS Model ED. "
            "Validate against local data before operational use.", fontsize=8, color=NHS_GREY)
    pdf.savefig(fig, facecolor="white"); plt.close(fig)


def _sd_page(pdf, p, res):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11.69, 8.27), dpi=150)
    fig.suptitle("System Dynamics — whole-system stocks and feedback", fontsize=15,
                 color=NHS_DARK, weight="bold", x=0.12, ha="left")
    hist = res.get("sd_history") or []
    hours = [t / 60 for t, _ in hist]
    a1.plot(hours, [s["bed_occupancy"] * 100 for _, s in hist], color=NHS_BLUE, label="Inpatient bed occupancy %")
    a1.plot(hours, [s["mh_occupancy"] * 100 for _, s in hist], color=NHS_AQUA, label="MH bed occupancy %")
    a1.plot(hours, [s["crowding"] * 100 for _, s in hist], color=NHS_ORANGE, ls=":", label="ED crowding %")
    a1.axhline(92, color=NHS_RED, ls="--", lw=1); a1.set_ylabel("%"); a1.legend(fontsize=8); a1.set_title("Stocks over time", fontsize=11)
    a2.plot(hours, [s["bed_wait_multiplier"] for _, s in hist], color=NHS_RED, label="Bed-wait multiplier (exit-block)")
    a2.plot(hours, [1 + s["community_pull"] * 5 for _, s in hist], color=NHS_GREEN, label="Community pull (rel.)")
    a2.set_xlabel("hours"); a2.set_ylabel("× / rel."); a2.legend(fontsize=8); a2.set_title("Feedback signals (SD → DES)", fontsize=11)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    pdf.savefig(fig, facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    import sys
    pf = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "pathways" / "model_ed.json")
    out = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent.parent / "docs" / "decision_report.pdf")
    print("Saved:", build_report(pf, out))
