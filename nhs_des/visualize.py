"""
Interactive Plotly figure builders for the web dashboard.

Each function returns a ``plotly.graph_objects.Figure``; the Flask app serialises
them with ``fig.to_json()`` and the browser renders them with Plotly.js. Keeping
these pure (figure in, figure out) means they are equally usable from notebooks.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from .engine import Pathway
from .metrics import (stage_waits, resource_utilisation,
                      occupancy_timeseries, flow_counts)

NHS_BLUE = "#005EB8"
NHS_DARK_BLUE = "#003087"
NHS_BRIGHT_BLUE = "#0072CE"
NHS_LIGHT_BLUE = "#41B6E6"
NHS_AQUA = "#00A9CE"
NHS_GREEN = "#009639"
NHS_YELLOW = "#FFB81C"
NHS_ORANGE = "#ED8B00"
NHS_RED = "#DA291C"
NHS_GREY = "#425563"
PALETTE = [NHS_BRIGHT_BLUE, NHS_LIGHT_BLUE, NHS_AQUA, NHS_YELLOW, NHS_ORANGE,
           NHS_GREY, "#8A1538", "#330072", "#78BE20"]

_LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="Frutiger, Arial, sans-serif", color=NHS_GREY, size=12),
    margin=dict(l=50, r=20, t=50, b=40),
    title=dict(font=dict(color=NHS_DARK_BLUE, size=16)),
)


def _node_colour(name: str) -> str:
    key = name.lower()
    if "admit" in key:
        return NHS_RED
    if "discharg" in key:
        return NHS_GREEN
    if "arrival" in key or "referral" in key:
        return NHS_GREY
    return PALETTE[hash(name) % len(PALETTE)]


def _layer_of(edges, labels):
    """Longest-path depth of each node from a source, so the Sankey can be laid
    out strictly left-to-right instead of collapsing into one overlapping row."""
    succ = {n: [] for n in labels}
    indeg = {n: 0 for n in labels}
    for _, r in edges.iterrows():
        succ[r["source"]].append(r["target"])
        indeg[r["target"]] += 1
    layer = {n: 0 for n in labels}
    for _ in range(len(labels)):
        changed = False
        for s in labels:
            for t in succ[s]:
                if layer[t] < layer[s] + 1:
                    layer[t] = layer[s] + 1
                    changed = True
        if not changed:
            break
    return layer


def sankey_figure(result, pathway: Pathway) -> go.Figure:
    edges = flow_counts(result, pathway)
    if edges.empty:
        return go.Figure(layout=_LAYOUT)
    labels = sorted(set(edges["source"]) | set(edges["target"]))
    idx = {n: i for i, n in enumerate(labels)}
    layer = _layer_of(edges, labels)
    max_layer = max(layer.values()) or 1
    # Spread nodes within each column so labels don't stack.
    col_members: dict[int, list] = {}
    for n in labels:
        col_members.setdefault(layer[n], []).append(n)
    xs, ys = [], []
    for n in labels:
        members = col_members[layer[n]]
        i = members.index(n)
        k = len(members)
        xs.append(min(0.95, max(0.01, layer[n] / max_layer)))
        ys.append(0.5 if k == 1 else 0.05 + 0.9 * (i / (k - 1)))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=[f"{n} ({_inflow(edges, n):,})" for n in labels],
            color=[_node_colour(n) for n in labels],
            x=xs, y=ys,
            pad=16, thickness=16, line=dict(color="white", width=1),
        ),
        link=dict(
            source=[idx[s] for s in edges["source"]],
            target=[idx[t] for t in edges["target"]],
            value=list(edges["value"]),
            color="rgba(0,114,206,0.22)",
        ),
    ))
    fig.update_layout(_LAYOUT, title="Patient flow (process map) — arrival to disposition",
                      height=460, font_size=11)
    return fig


def _inflow(edges, node) -> int:
    inc = edges[edges["target"] == node]["value"].sum()
    if inc == 0:  # source node
        inc = edges[edges["source"] == node]["value"].sum()
    return int(inc)


def occupancy_figure(result, pathway: Pathway, resources=None) -> go.Figure:
    util = resource_utilisation(result, pathway)
    resources = resources or util.head(5)["resource"].tolist()
    occ = occupancy_timeseries(result, pathway, resources=resources, step=30)
    fig = go.Figure()
    if not occ.empty:
        hours = occ["hour"] - occ["hour"].min()
        for i, res in enumerate(resources):
            col = PALETTE[i % len(PALETTE)]
            fig.add_trace(go.Scatter(x=hours, y=occ[res], name=res.replace("_", " "),
                                     mode="lines", line=dict(color=col, width=2)))
            cap = pathway.resources.get(res)
            if cap:
                fig.add_hline(y=cap, line=dict(color=col, width=1, dash="dot"),
                              opacity=0.5)
    fig.update_layout(_LAYOUT, title="Resource occupancy vs capacity (dotted)",
                      height=380, xaxis_title="hours", yaxis_title="patients in use",
                      legend=dict(orientation="h", y=-0.2))
    return fig


def utilisation_figure(result, pathway: Pathway) -> go.Figure:
    util = resource_utilisation(result, pathway).head(10).iloc[::-1]
    colours = [NHS_RED if v > 85 else NHS_ORANGE if v > 70 else NHS_AQUA
               for v in util["utilisation"]]
    fig = go.Figure(go.Bar(
        x=util["utilisation"], y=[r.replace("_", " ") for r in util["resource"]],
        orientation="h", marker_color=colours,
        text=[f"{v:.0f}%" for v in util["utilisation"]], textposition="outside",
    ))
    fig.update_layout(_LAYOUT, title="Resource utilisation — bottlenecks in red",
                      height=380, xaxis_title="% of capacity in use",
                      xaxis_range=[0, 105])
    return fig


def waits_figure(result) -> go.Figure:
    waits = stage_waits(result).head(8).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=waits["mean_wait"], y=waits["stage_label"], orientation="h",
        marker_color=NHS_BRIGHT_BLUE,
        text=[f"{v:.0f} min" for v in waits["mean_wait"]], textposition="outside",
    ))
    fig.update_layout(_LAYOUT, title="Where patients wait — mean queue time",
                      height=380, xaxis_title="mean wait (minutes)")
    return fig


def montecarlo_figure(mc: dict, metric="target_compliance",
                      label="4-hour compliance (%)") -> go.Figure:
    vals = mc["table"][metric].to_numpy()
    s = mc["summary"][metric]
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=vals, nbinsx=15, marker_color=NHS_LIGHT_BLUE,
                               marker_line=dict(color="white", width=1),
                               name="replications"))
    fig.add_vline(x=s["mean"], line=dict(color=NHS_DARK_BLUE, width=2),
                  annotation_text=f"mean {s['mean']:.1f}")
    fig.add_vrect(x0=s["ci_low"], x1=s["ci_high"], fillcolor=NHS_BLUE, opacity=0.12,
                  line_width=0, annotation_text="95% CI", annotation_position="top left")
    fig.update_layout(_LAYOUT, height=380,
                      title=f"Monte-Carlo distribution — {label}",
                      xaxis_title=label, yaxis_title="replications")
    return fig


def scenario_figure(cmp: dict, metric="target_compliance",
                    label="4-hour compliance (%)", higher_better=True) -> go.Figure:
    rows = cmp["rows"]
    names = [r["scenario"] for r in rows]
    vals = [r[metric] for r in rows]
    base = vals[0]
    colours = [NHS_GREY]
    for v in vals[1:]:
        better = v >= base if higher_better else v <= base
        colours.append(NHS_GREEN if better else NHS_RED)
    err = None
    if f"{metric}_lo" in rows[0]:
        err = dict(type="data", symmetric=False,
                   array=[r[f"{metric}_hi"] - r[metric] for r in rows],
                   arrayminus=[r[metric] - r[f"{metric}_lo"] for r in rows],
                   color=NHS_GREY, thickness=1.2, width=4)
    fig = go.Figure(go.Bar(
        x=names, y=vals, marker_color=colours, error_y=err,
        text=[f"{v:.0f}" for v in vals], textposition="outside",
    ))
    fig.add_hline(y=base, line=dict(color=NHS_GREY, width=1, dash="dash"), opacity=0.6)
    fig.update_layout(_LAYOUT, height=400,
                      title=f"Scenario comparison — {label}", yaxis_title=label)
    return fig
