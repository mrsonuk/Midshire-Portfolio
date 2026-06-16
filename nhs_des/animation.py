"""
Animated patient-flow visualisation.

The beta tool's one strong feature was watching patients physically move through
the department. This recreates that - generalised to any pathway - by turning the
engine's event log into moving dots: every patient is a dot that travels from
station to station over simulation time, coloured by acuity/class. Stations are
laid out automatically from the pathway graph (longest-path layering), so it works
for an Emergency Department, an Acute Medical Unit or any future pathway.

Two renderers share the same track-building logic:
    * ``animation_figure``  - interactive Plotly figure (play / pause / scrub) for
                              the web dashboard.
    * ``render_gif``        - a self-contained animated GIF artefact for slides.
"""
from __future__ import annotations

# Allow running directly (``python animation.py`` / ``python -m animation``)
# as well as ``python -m nhs_des.animation``.
if __package__ in (None, ""):
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
    __package__ = "nhs_des"

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .engine import Pathway

NHS_BLUE = "#005EB8"
NHS_DARK_BLUE = "#003087"
NHS_GREY = "#425563"
NHS_LIGHT_GREY = "#E8EDEE"
# Acuity / class colour key (red = sickest, blue = least urgent) and a fallback
# cycle for non-ED pathways whose classes are referrals rather than acuities.
ACUITY_COLOURS = {
    "Acuity 1": "#DA291C", "Acuity 2": "#ED8B00", "Acuity 3": "#FFB81C",
    "Acuity 4": "#009639", "Acuity 5": "#0072CE",
}
FALLBACK_CYCLE = ["#0072CE", "#00A9CE", "#8A1538", "#330072", "#ED8B00"]


def _node_layers(pathway: Pathway) -> dict[str, int]:
    """Assign each node a column = longest path length from the source."""
    succ: dict[str, set] = {nid: set() for nid in pathway.nodes}
    for nid, node in pathway.nodes.items():
        for r in node.get("routes", []) or []:
            succ[nid].add(r[0])
        for routes in (node.get("routes_by_class") or {}).values():
            for r in routes:
                succ[nid].add(r[0])
    source = pathway.source_node()["id"]
    layer = {nid: 0 for nid in pathway.nodes}
    layer[source] = 0
    for _ in range(len(pathway.nodes) + 1):
        changed = False
        for nid in pathway.nodes:
            for t in succ[nid]:
                if layer[t] < layer[nid] + 1:
                    layer[t] = layer[nid] + 1
                    changed = True
        if not changed:
            break
    return layer


def station_layout(pathway: Pathway) -> dict[str, tuple]:
    """{node_id: (x, y, label)} laid out left-to-right by pathway stage."""
    layer = _node_layers(pathway)
    max_layer = max(layer.values()) or 1
    cols: dict[int, list] = {}
    for nid, lay in layer.items():
        cols.setdefault(lay, []).append(nid)
    pos = {}
    for lay, members in cols.items():
        members = sorted(members)
        k = len(members)
        for i, nid in enumerate(members):
            x = lay / max_layer
            y = 0.5 if k == 1 else 0.08 + 0.84 * (i / (k - 1))
            pos[nid] = (x, y, pathway.nodes[nid].get("label", nid))
    return pos


def _colour(cls: str, classes: list) -> str:
    if cls in ACUITY_COLOURS:
        return ACUITY_COLOURS[cls]
    return FALLBACK_CYCLE[classes.index(cls) % len(FALLBACK_CYCLE)] if cls in classes \
        else NHS_GREY


def build_tracks(result: dict, pathway: Pathway):
    """For each patient, a set of (time -> x, y) waypoints describing the journey:
    arrival at the source, each station visited, then the exit. Returns the layout,
    per-patient waypoint arrays and the class list."""
    pos = station_layout(pathway)
    events = result["events"]
    patients = result["patients"]
    if events.empty or patients.empty:
        return pos, [], []

    source_id = pathway.source_node()["id"]
    sx, sy, _ = pos[source_id]
    disp_pos = {}  # disposition label -> sink position
    for nid, (x, y, label) in pos.items():
        if pathway.nodes[nid].get("type") == "sink":
            disp_pos[label] = (x, y)

    arr = patients.set_index("pid")["arrival"].to_dict()
    exit_t = patients.set_index("pid")["exit"].to_dict()
    disp = patients.set_index("pid")["disposition"].to_dict()
    classes = sorted(patients["acuity"].unique())

    # ordered station visits per patient
    ev = events.sort_values(["pid", "service_start"])
    tracks = []
    for pid, grp in ev.groupby("pid"):
        if pid not in arr:
            continue
        ts = [arr[pid]]
        xs = [sx]
        ys = [sy]
        for r in grp.itertuples():
            if r.stage in pos:
                x, y, _ = pos[r.stage]
                # Dwell at the station for the whole service (two waypoints),
                # then glide to the next station over the intervening queue time.
                ts.append(r.service_start); xs.append(x); ys.append(y)
                ts.append(r.service_end); xs.append(x); ys.append(y)
        ex = exit_t.get(pid, ts[-1])
        end_pos = disp_pos.get(disp.get(pid), (xs[-1], ys[-1]))
        ts.append(ex)
        xs.append(end_pos[0])
        ys.append(end_pos[1])
        # ensure strictly increasing times for interpolation
        ts = np.maximum.accumulate(np.array(ts, dtype=float))
        tracks.append({
            "pid": pid, "t": ts, "x": np.array(xs), "y": np.array(ys),
            "cls": grp["acuity"].iloc[0], "arr": arr[pid], "exit": ex,
        })
    return pos, tracks, classes


def _busiest_window(tracks, hours=18.0):
    """Pick a representative window centred on peak concurrent occupancy."""
    if not tracks:
        return 0.0, hours * 60
    starts = np.array([t["arr"] for t in tracks])
    lo, hi = starts.min(), starts.max()
    span = hours * 60
    # slide a window and find max patients present at its centre
    best_start, best = lo, -1
    for s in np.linspace(lo, max(lo, hi - span), 24):
        c = ((starts >= s) & (starts <= s + span)).sum()
        if c > best:
            best, best_start = c, s
    return best_start, best_start + span


def _patient_jitter(tracks):
    """A small, stable per-patient offset so overlapping dots stay legible."""
    rng = np.random.default_rng(0)
    return {t["pid"]: rng.uniform(-0.018, 0.018, 2) for t in tracks}


def animation_figure(result: dict, pathway: Pathway, hours=18.0, step=12.0,
                     max_frames=90) -> go.Figure:
    pos, tracks, classes = build_tracks(result, pathway)
    fig = go.Figure(layout=dict(paper_bgcolor="white", plot_bgcolor="white"))
    if not tracks:
        return fig

    t0, t1 = _busiest_window(tracks, hours)
    grid = np.arange(t0, t1, step)
    if len(grid) > max_frames:
        grid = np.linspace(t0, t1, max_frames)
    jit = _patient_jitter(tracks)

    # station markers + labels (static background)
    bg = []
    for nid, (x, y, label) in pos.items():
        ntype = pathway.nodes[nid].get("type")
        bg.append((x, y, label, ntype))
    bx = [b[0] for b in bg]
    by = [b[1] for b in bg]
    station_trace = go.Scatter(
        x=bx, y=by, mode="markers+text",
        marker=dict(size=26, color=NHS_LIGHT_GREY, line=dict(color=NHS_BLUE, width=2),
                    symbol="square"),
        text=[b[2] for b in bg], textposition="top center",
        textfont=dict(size=10, color=NHS_DARK_BLUE), hoverinfo="text", showlegend=False,
    )

    def dots_at(t):
        xs, ys, cs, txt = [], [], [], []
        for tr in tracks:
            if tr["arr"] <= t <= tr["exit"]:
                x = float(np.interp(t, tr["t"], tr["x"])) + jit[tr["pid"]][0]
                y = float(np.interp(t, tr["t"], tr["y"])) + jit[tr["pid"]][1]
                xs.append(x); ys.append(y)
                cs.append(_colour(tr["cls"], classes))
                txt.append(f"Patient {tr['pid']} · {tr['cls']}")
        return xs, ys, cs, txt

    xs, ys, cs, txt = dots_at(grid[0])
    patient_trace = go.Scatter(x=xs, y=ys, mode="markers",
                               marker=dict(size=9, color=cs, opacity=0.85,
                                           line=dict(color="white", width=0.5)),
                               text=txt, hoverinfo="text", showlegend=False)

    frames = []
    for gi, t in enumerate(grid):
        xs, ys, cs, txt = dots_at(t)
        present = len(xs)
        frames.append(go.Frame(
            name=str(gi),
            data=[station_trace,
                  go.Scatter(x=xs, y=ys, mode="markers",
                             marker=dict(size=9, color=cs, opacity=0.85,
                                         line=dict(color="white", width=0.5)),
                             text=txt, hoverinfo="text", showlegend=False)],
            layout=dict(title=f"Patient flow — hour {(t-t0)/60:5.1f}   ·   "
                              f"{present} patients in department"),
        ))

    fig.add_trace(station_trace)
    fig.add_trace(patient_trace)
    fig.frames = frames

    # acuity legend (proxy traces)
    for cls in classes:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                                 marker=dict(size=9, color=_colour(cls, classes)),
                                 name=cls, showlegend=True))

    fig.update_layout(
        height=520, title=f"Patient flow — hour 0.0   ·   {len(dots_at(grid[0])[0])} patients in department",
        xaxis=dict(visible=False, range=[-0.08, 1.08]),
        yaxis=dict(visible=False, range=[-0.05, 1.12]),
        font=dict(family="Frutiger, Arial, sans-serif", color=NHS_GREY),
        legend=dict(orientation="h", y=-0.05, title="Acuity / class"),
        updatemenus=[dict(
            type="buttons", showactive=False, x=0.02, y=1.12, xanchor="left",
            buttons=[
                dict(label="Play", method="animate",
                     args=[None, dict(frame=dict(duration=120, redraw=True),
                                      fromcurrent=True, transition=dict(duration=60))]),
                dict(label="Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate")]),
            ])],
        sliders=[dict(
            active=0, x=0.12, len=0.86, y=0, pad=dict(t=30),
            currentvalue=dict(prefix="hour ", font=dict(color=NHS_DARK_BLUE)),
            steps=[dict(method="animate", label=f"{(t-t0)/60:.0f}",
                        args=[[str(gi)], dict(mode="immediate",
                                              frame=dict(duration=0, redraw=True))])
                   for gi, t in enumerate(grid)])],
    )
    return fig


def render_gif(result: dict, pathway: Pathway, out_path: str,
               hours=14.0, step=12.0, max_frames=70, fps=12) -> str:
    """Render the same animation to a standalone GIF for slide decks."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    from matplotlib.patches import FancyBboxPatch

    pos, tracks, classes = build_tracks(result, pathway)
    t0, t1 = _busiest_window(tracks, hours)
    grid = np.linspace(t0, t1, min(max_frames, max(2, int((t1 - t0) / step))))
    jit = _patient_jitter(tracks)

    fig, ax = plt.subplots(figsize=(13, 6.2), dpi=110)
    fig.patch.set_facecolor("#F0F4F7")
    ax.set_facecolor("white")
    ax.set_xlim(-0.08, 1.10); ax.set_ylim(-0.06, 1.16); ax.axis("off")

    # header band
    ax.add_patch(plt.Rectangle((-0.08, 1.04), 1.18, 0.14, color=NHS_BLUE,
                               transform=ax.transAxes, clip_on=False))
    ax.text(-0.05, 1.10, "NHS  Patient Flow Simulator", color="white", fontsize=14,
            weight="bold", transform=ax.transAxes, va="center")
    ax.text(1.07, 1.10, pathway.name, color="#CFE6F7", fontsize=10, ha="right",
            transform=ax.transAxes, va="center")

    # static stations
    for nid, (x, y, label) in pos.items():
        ntype = pathway.nodes[nid].get("type")
        face = "#FBE9E7" if ntype == "sink" else NHS_LIGHT_GREY
        edge = "#DA291C" if "Admit" in label else ("#009639" if "Discharg" in label else NHS_BLUE)
        ax.add_patch(FancyBboxPatch((x - 0.028, y - 0.028), 0.056, 0.056,
                                    boxstyle="round,pad=0.004,rounding_size=0.01",
                                    facecolor=face, edgecolor=edge, lw=1.4, zorder=2))
        ax.text(x, y + 0.05, label, ha="center", va="bottom", fontsize=7.5,
                color=NHS_DARK_BLUE, zorder=2)

    scat = ax.scatter([], [], s=42, zorder=3, edgecolor="white", linewidth=0.4)
    title = ax.text(0.5, 1.005, "", ha="center", va="bottom", fontsize=11,
                    color=NHS_DARK_BLUE, weight="bold", transform=ax.transAxes)
    # legend
    handles = [plt.Line2D([0], [0], marker="o", ls="", markersize=8,
                          markerfacecolor=_colour(c, classes), markeredgecolor="white",
                          label=c) for c in classes]
    ax.legend(handles=handles, loc="lower center", ncol=len(classes), fontsize=8,
              frameon=False, bbox_to_anchor=(0.5, -0.06))

    def positions_at(t):
        xs, ys, cs = [], [], []
        for tr in tracks:
            if tr["arr"] <= t <= tr["exit"]:
                xs.append(float(np.interp(t, tr["t"], tr["x"])) + jit[tr["pid"]][0])
                ys.append(float(np.interp(t, tr["t"], tr["y"])) + jit[tr["pid"]][1])
                cs.append(_colour(tr["cls"], classes))
        return xs, ys, cs

    def update(i):
        t = grid[i]
        xs, ys, cs = positions_at(t)
        scat.set_offsets(np.c_[xs, ys] if xs else np.empty((0, 2)))
        scat.set_color(cs if cs else "none")
        title.set_text(f"hour {(t-t0)/60:.1f}   ·   {len(xs)} patients in department")
        return scat, title

    anim = FuncAnimation(fig, update, frames=len(grid), interval=1000 / fps, blit=False)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    anim.save(out_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    import sys
    from .engine import run_pathway
    pf = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "pathways" / "emergency_department.json")
    out = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(__file__).parent / "outputs" / "patient_flow_animation.gif")
    p = Pathway.load(pf)
    print("Simulating + rendering animation...")
    print("Saved:", render_gif(run_pathway(p, seed=5), p, out))
