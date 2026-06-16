"""
Presentation snapshot generator.

Produces a single, NHS-branded composite image that looks like a screenshot of
the redesigned tool's dashboard - the artefact used to demonstrate the rebuild
to clients. It runs a baseline simulation, a Monte-Carlo batch and a set of
what-if scenarios, then lays everything out on one canvas:

    * a header band and a row of headline KPI cards (with Monte-Carlo CIs)
    * a patient-flow diagram (auto-laid-out from the realised flows)
    * resource occupancy over time against capacity
    * a Monte-Carlo distribution of 4-hour performance
    * a scenario-comparison panel
    * a bottleneck / utilisation panel

Run:  python -m nhs_des.snapshot
"""
from __future__ import annotations

# Allow running this file directly (``python snapshot.py`` or, from inside the
# package directory, ``python -m snapshot``) as well as the canonical
# ``python -m nhs_des.snapshot``. When run as a loose script there is no parent
# package for the relative imports below, so register it on the fly.
if __package__ in (None, ""):
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
    __package__ = "nhs_des"

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, PathPatch
from matplotlib.path import Path as MplPath
import numpy as np

from .engine import Pathway, run_pathway
from .metrics import (kpis, stage_waits, resource_utilisation,
                      occupancy_timeseries, flow_counts)
from .montecarlo import monte_carlo
from .scenarios import compare_scenarios

# NHS identity palette (https://www.england.nhs.uk/nhsidentity/)
NHS_BLUE = "#005EB8"
NHS_DARK_BLUE = "#003087"
NHS_BRIGHT_BLUE = "#0072CE"
NHS_LIGHT_BLUE = "#41B6E6"
NHS_AQUA = "#00A9CE"
NHS_GREEN = "#009639"
NHS_WARM_YELLOW = "#FFB81C"
NHS_ORANGE = "#ED8B00"
NHS_RED = "#DA291C"
NHS_GREY = "#425563"
NHS_LIGHT_GREY = "#E8EDEE"
PANEL_BG = "#FFFFFF"
PAGE_BG = "#F0F4F7"


def _layer_nodes(edges) -> dict:
    """Assign each flow node to a column = longest path length from 'Arrival'."""
    nodes = set(edges["source"]) | set(edges["target"])
    succ: dict[str, list] = {n: [] for n in nodes}
    for _, r in edges.iterrows():
        succ[r["source"]].append(r["target"])
    layer = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for src, targets in succ.items():
            for t in targets:
                if layer[t] < layer[src] + 1:
                    layer[t] = layer[src] + 1
                    changed = True
        if not changed:
            break
    return layer


def _draw_flow(ax, edges, palette):
    """Draw a left-to-right weighted patient-flow diagram (a readable Sankey)."""
    ax.set_axis_off()
    if edges.empty:
        ax.text(0.5, 0.5, "No flow recorded", ha="center", va="center")
        return

    layer = _layer_nodes(edges)
    max_layer = max(layer.values())
    inflow: dict[str, float] = {}
    for _, r in edges.iterrows():
        inflow[r["target"]] = inflow.get(r["target"], 0) + r["value"]
    # 'Arrival' inflow = total it sends out
    out_arr = edges[edges["source"] == "Arrival"]["value"].sum()
    inflow["Arrival"] = max(inflow.get("Arrival", 0), out_arr)
    total = max(inflow.values()) if inflow else 1

    # group nodes by layer and lay them out vertically
    cols: dict[int, list] = {}
    for n, lay in layer.items():
        cols.setdefault(lay, []).append(n)
    node_box: dict[str, tuple] = {}
    x_gap = 1.0 / (max_layer + 1)
    box_w = x_gap * 0.32
    for lay, members in cols.items():
        members = sorted(members, key=lambda n: -inflow.get(n, 0))
        k = len(members)
        for i, n in enumerate(members):
            x = lay * x_gap + x_gap * 0.18
            h = 0.04 + 0.42 * (inflow.get(n, 0) / total)
            y_centre = 0.12 + 0.76 * ((i + 0.5) / k)
            node_box[n] = (x, y_centre, box_w, h)

    def colour_for(name):
        key = name.lower()
        if "admit" in key:
            return NHS_RED
        if "discharg" in key:
            return NHS_GREEN
        if "arrival" in key or "referral" in key:
            return NHS_GREY
        return palette[hash(name) % len(palette)]

    # draw flows first (so boxes sit on top)
    for _, r in edges.iterrows():
        if r["source"] not in node_box or r["target"] not in node_box:
            continue
        x0, y0, w0, h0 = node_box[r["source"]]
        x1, y1, w1, h1 = node_box[r["target"]]
        sx = x0 + w0
        ex = x1
        lw = max(0.4, 6.0 * (r["value"] / total))
        mid = (sx + ex) / 2
        verts = [(sx, y0), (mid, y0), (mid, y1), (ex, y1)]
        codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4]
        ax.add_patch(PathPatch(MplPath(verts, codes), fill=False,
                               edgecolor=colour_for(r["source"]),
                               lw=lw, alpha=0.35, capstyle="round"))

    for n, (x, y, w, h) in node_box.items():
        col = colour_for(n)
        ax.add_patch(FancyBboxPatch((x, y - h / 2), w, h,
                                    boxstyle="round,pad=0.002,rounding_size=0.01",
                                    facecolor=col, edgecolor="white", lw=1.2))
        label = n if len(n) <= 20 else n[:19] + "."
        # Label centred above each box - avoids horizontal collisions between
        # adjacent columns regardless of how many stages the pathway has.
        ax.text(x + w / 2, y + h / 2 + 0.015,
                f"{label}\n{int(inflow.get(n,0)):,}", ha="center", va="bottom",
                fontsize=7.5, color=NHS_GREY, linespacing=0.95)

    ax.set_xlim(-0.02, 1.04)
    ax.set_ylim(-0.04, 1.16)


def _kpi_card(fig, x, y, w, h, title, value, sub, accent):
    ax = fig.add_axes([x, y, w, h])
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.0,rounding_size=0.06",
                                facecolor=PANEL_BG, edgecolor=NHS_LIGHT_GREY,
                                lw=1, transform=ax.transAxes))
    ax.add_patch(plt.Rectangle((0, 0), 0.06, 1, color=accent, transform=ax.transAxes))
    ax.text(0.14, 0.74, title, fontsize=9.5, color=NHS_GREY, va="center",
            transform=ax.transAxes, weight="bold")
    ax.text(0.14, 0.40, value, fontsize=21, color=NHS_DARK_BLUE, va="center",
            transform=ax.transAxes, weight="bold")
    ax.text(0.14, 0.13, sub, fontsize=8, color=NHS_GREY, va="center",
            transform=ax.transAxes)


def build_snapshot(pathway_file: str, out_path: str, replications: int = 40,
                   scenarios: list | None = None, seed: int = 7,
                   return_fig: bool = False):
    pathway = Pathway.load(pathway_file)
    base = run_pathway(pathway, seed=seed)
    base_kpi = kpis(base, pathway)
    if scenarios is None:
        from .metrics import diagnose
        scenarios = _default_scenarios(pathway, diagnose(base, pathway)["constraint"])
    mc = monte_carlo(pathway, replications=replications, base_seed=1000)
    util = resource_utilisation(base, pathway)
    flows = flow_counts(base, pathway)
    cmp = compare_scenarios(pathway, scenarios, replications=max(8, replications // 4),
                            seed=2000)

    fig = plt.figure(figsize=(19.2, 10.8), dpi=110)
    fig.patch.set_facecolor(PAGE_BG)
    palette = [NHS_BRIGHT_BLUE, NHS_LIGHT_BLUE, NHS_AQUA, NHS_WARM_YELLOW,
               NHS_ORANGE, NHS_GREY, "#8A1538", "#330072"]

    # ---- header -------------------------------------------------------- #
    head = fig.add_axes([0, 0.925, 1, 0.075]); head.set_axis_off()
    head.add_patch(plt.Rectangle((0, 0), 1, 1, color=NHS_BLUE))
    head.add_patch(FancyBboxPatch((0.012, 0.22), 0.052, 0.56,
                                  boxstyle="round,pad=0.0,rounding_size=0.02",
                                  facecolor="white", transform=head.transAxes))
    head.text(0.038, 0.5, "NHS", fontsize=20, color=NHS_BLUE, weight="bold",
              ha="center", va="center", transform=head.transAxes)
    head.text(0.08, 0.62, "Patient Flow Simulator", fontsize=20, color="white",
              weight="bold", va="center", transform=head.transAxes)
    head.text(0.08, 0.28, "Discrete-event simulation for emergency & urgent care planning",
              fontsize=10.5, color="#CFE6F7", va="center", transform=head.transAxes)
    head.text(0.985, 0.66, pathway.name, fontsize=13, color="white", weight="bold",
              ha="right", va="center", transform=head.transAxes)
    days = (pathway.sim_duration - pathway.warmup) / 1440
    head.text(0.985, 0.30,
              f"{int(round(base_kpi['throughput_per_day']))} attendances/day  ·  "
              f"{days:.0f}-day run  ·  {replications} Monte-Carlo replications",
              fontsize=9.5, color="#CFE6F7", ha="right", va="center",
              transform=head.transAxes)

    # ---- KPI cards ----------------------------------------------------- #
    def ci(metric):
        s = mc["summary"][metric]
        return s["ci_low"], s["ci_high"]
    cl, ch = ci("target_compliance")
    ll, lh = ci("mean_los")
    cards = [
        ("4-HOUR PERFORMANCE", f"{base_kpi['target_compliance']:.0f}%",
         f"95% CI {cl:.0f}-{ch:.0f}%", NHS_BLUE),
        ("MEAN TIME IN DEPT", f"{base_kpi['mean_los']/60:.1f}h",
         f"95% CI {ll/60:.1f}-{lh/60:.1f}h", NHS_BRIGHT_BLUE),
        ("95TH PERCENTILE LOS", f"{base_kpi['p95_los']/60:.1f}h",
         "longest typical wait", NHS_WARM_YELLOW),
        ("ADMITTED", f"{base_kpi['admit_rate']:.0f}%",
         f"{base_kpi['mean_los_admitted']/60:.1f}h mean LOS", NHS_ORANGE),
        ("DAILY ATTENDANCES", f"{base_kpi['throughput_per_day']:.0f}",
         f"{base_kpi['n_patients']:,} simulated", NHS_AQUA),
    ]
    cw, gap = 0.183, 0.012
    x0 = 0.014
    for i, (t, v, s, a) in enumerate(cards):
        _kpi_card(fig, x0 + i * (cw + gap), 0.80, cw, 0.10, t, v, s, a)

    # ---- patient flow (large, left) ------------------------------------ #
    axf = fig.add_axes([0.014, 0.40, 0.56, 0.37])
    axf.set_title("Patient flow  ·  arrival to disposition",
                  loc="left", fontsize=12, color=NHS_DARK_BLUE, weight="bold", pad=8)
    _panel_bg(fig, 0.014, 0.40, 0.56, 0.37)
    _draw_flow(axf, flows, palette)

    # ---- occupancy over time (right) ----------------------------------- #
    axo = fig.add_axes([0.60, 0.555, 0.385, 0.215])
    _panel_bg(fig, 0.595, 0.40, 0.405, 0.37)
    top_res = util.head(4)["resource"].tolist()
    occ = occupancy_timeseries(base, pathway, resources=top_res, step=30)
    if not occ.empty:
        day_hours = occ["hour"] - occ["hour"].min()
        for i, res in enumerate(top_res):
            axo.plot(day_hours, occ[res], lw=1.6, color=palette[i % len(palette)],
                     label=res.replace("_", " "))
            cap = pathway.resources.get(res)
            if cap:
                axo.axhline(cap, color=palette[i % len(palette)], lw=0.8,
                            ls=":", alpha=0.6)
    axo.set_title("Resource occupancy vs capacity (dotted)", loc="left",
                  fontsize=11, color=NHS_DARK_BLUE, weight="bold")
    axo.set_xlabel("hours", fontsize=8); axo.set_ylabel("in use", fontsize=8)
    axo.legend(fontsize=7, loc="upper right", ncol=2, framealpha=0.9)
    _style(axo)

    # ---- bottleneck / utilisation panel -------------------------------- #
    axu = fig.add_axes([0.60, 0.43, 0.385, 0.095])
    u = util.head(6).iloc[::-1]
    colours = [NHS_RED if v > 85 else NHS_ORANGE if v > 70 else NHS_AQUA
               for v in u["utilisation"]]
    axu.barh(range(len(u)), u["utilisation"], color=colours, height=0.62)
    axu.set_yticks(range(len(u)))
    axu.set_yticklabels([r.replace("_", " ") for r in u["resource"]], fontsize=7.5)
    axu.set_xlim(0, 100)
    for i, v in enumerate(u["utilisation"]):
        axu.text(min(v + 1.5, 96), i, f"{v:.0f}%", va="center", fontsize=7.5,
                 color=NHS_GREY)
    axu.set_title("Resource utilisation  ·  bottlenecks in red", loc="left",
                  fontsize=11, color=NHS_DARK_BLUE, weight="bold")
    _style(axu); axu.set_xlabel("% busy", fontsize=8)

    # ---- Monte-Carlo distribution -------------------------------------- #
    axm = fig.add_axes([0.014, 0.06, 0.30, 0.27])
    _panel_bg(fig, 0.014, 0.045, 0.31, 0.305)
    vals = mc["table"]["target_compliance"].to_numpy()
    axm.hist(vals, bins=12, color=NHS_LIGHT_BLUE, edgecolor="white")
    axm.axvline(vals.mean(), color=NHS_DARK_BLUE, lw=2,
                label=f"mean {vals.mean():.1f}%")
    axm.axvspan(cl, ch, color=NHS_BLUE, alpha=0.12, label="95% CI")
    axm.set_title("Monte-Carlo: 4-hour performance variability", loc="left",
                  fontsize=11, color=NHS_DARK_BLUE, weight="bold")
    axm.set_xlabel("4-hour compliance (%)", fontsize=8)
    axm.set_ylabel("replications", fontsize=8)
    axm.legend(fontsize=8, loc="upper right"); _style(axm)

    # ---- scenario comparison ------------------------------------------- #
    axs = fig.add_axes([0.355, 0.06, 0.30, 0.27])
    _panel_bg(fig, 0.345, 0.045, 0.31, 0.305)
    rows = cmp["rows"]
    names = [r["scenario"] for r in rows]
    comp = [r["target_compliance"] for r in rows]
    base_val = comp[0]
    bar_cols = [NHS_GREY] + [NHS_GREEN if c >= base_val else NHS_RED
                             for c in comp[1:]]
    ypos = range(len(names))
    axs.barh(list(ypos), comp, color=bar_cols, height=0.6)
    axs.axvline(base_val, color=NHS_GREY, lw=1, ls="--", alpha=0.7)
    axs.set_yticks(list(ypos))
    axs.set_yticklabels(_wrap(names), fontsize=7.5)
    axs.invert_yaxis()
    for i, c in enumerate(comp):
        delta = c - base_val
        txt = f"{c:.0f}%" + (f"  ({delta:+.0f})" if i else "")
        axs.text(min(c + 1, 92), i, txt, va="center", fontsize=7.5, color=NHS_GREY)
    axs.set_xlim(0, 100)
    axs.set_title("Scenario comparison  ·  4-hour performance", loc="left",
                  fontsize=11, color=NHS_DARK_BLUE, weight="bold")
    axs.set_xlabel("4-hour compliance (%)", fontsize=8); _style(axs)

    # ---- bottleneck waits table ---------------------------------------- #
    axw = fig.add_axes([0.69, 0.06, 0.295, 0.27])
    _panel_bg(fig, 0.68, 0.045, 0.32, 0.305)
    axw.set_axis_off()
    waits = stage_waits(base).head(6)
    axw.text(0.02, 0.96, "Where patients wait  ·  mean queue time",
             fontsize=11, color=NHS_DARK_BLUE, weight="bold", transform=axw.transAxes)
    axw.text(0.02, 0.85, "STAGE", fontsize=8, color=NHS_GREY, weight="bold",
             transform=axw.transAxes)
    axw.text(0.72, 0.85, "WAIT", fontsize=8, color=NHS_GREY, weight="bold",
             transform=axw.transAxes)
    axw.text(0.88, 0.85, "SEEN", fontsize=8, color=NHS_GREY, weight="bold",
             transform=axw.transAxes)
    maxw = max(waits["mean_wait"].max(), 1)
    for i, r in enumerate(waits.itertuples()):
        yy = 0.74 - i * 0.122
        axw.add_patch(plt.Rectangle((0.02, yy - 0.03), 0.62 * (r.mean_wait / maxw),
                                    0.055, color=NHS_LIGHT_BLUE, alpha=0.45,
                                    transform=axw.transAxes))
        axw.text(0.02, yy, r.stage_label, fontsize=8.5, color=NHS_GREY,
                 va="center", transform=axw.transAxes)
        axw.text(0.78, yy, f"{r.mean_wait:.0f}m", fontsize=8.5, color=NHS_DARK_BLUE,
                 va="center", ha="right", weight="bold", transform=axw.transAxes)
        axw.text(0.99, yy, f"{int(r.n):,}", fontsize=8.5, color=NHS_GREY,
                 va="center", ha="right", transform=axw.transAxes)

    fig.text(0.014, 0.018,
             "Redesigned NHS Patient Flow Simulator  ·  generalised, config-driven "
             "DES engine  ·  scenario modelling + Monte-Carlo uncertainty",
             fontsize=8.5, color=NHS_GREY)
    fig.text(0.985, 0.018, "For demonstration — synthetic data", fontsize=8.5,
             color=NHS_GREY, ha="right")

    if return_fig:
        return fig
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def _panel_bg(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h], zorder=-1); ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.0,rounding_size=0.04",
                                facecolor=PANEL_BG, edgecolor=NHS_LIGHT_GREY, lw=1,
                                transform=ax.transAxes))


def _style(ax):
    ax.set_facecolor(PANEL_BG)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(NHS_LIGHT_GREY)
    ax.tick_params(colors=NHS_GREY, labelsize=7.5)


def _wrap(names):
    out = []
    for n in names:
        if len(n) > 16 and " " in n:
            words = n.split(" ")
            mid = len(words) // 2
            out.append(" ".join(words[:mid]) + "\n" + " ".join(words[mid:]))
        else:
            out.append(n)
    return out


def _default_scenarios(pathway: Pathway, constraint: str | None = None) -> list:
    """Heuristic scenarios that actually target the diagnosed bottleneck: relieve
    the binding resource, add beds, and stress with a demand surge. When a
    ``constraint`` resource is supplied (from ``metrics.diagnose``), the first
    scenario adds capacity there so the report's recommendation and its evidence
    agree."""
    res = pathway.resources
    scenarios = []
    if constraint and constraint in res:
        scenarios.append({"name": f"+3 {constraint.replace('_',' ')}",
                          "resources": {constraint: "+3"}})
    else:
        doctor = next((r for r in ("ed_doctor", "junior_doctor", "consultant",
                                   "sdec_doctor") if r in res), None)
        if doctor:
            scenarios.append({"name": f"+3 {doctor.replace('_',' ')}",
                              "resources": {doctor: "+3"}})
    bed = next((r for r in ("inpatient_bed", "ward_bed", "majors_bed", "amu_bed")
                if r in res and r != constraint), None)
    if bed:
        scenarios.append({"name": f"+8 {bed.replace('_',' ')}",
                          "resources": {bed: "+8"}})
    scenarios.append({"name": "Winter +15% demand", "arrivals_scale": 1.15})
    return scenarios


if __name__ == "__main__":
    import sys
    pf = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "pathways" / "emergency_department.json")
    out = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).parent / "outputs" / "dashboard_snapshot.png")
    print("Building snapshot...")
    path = build_snapshot(pf, out)
    print("Saved:", path)
