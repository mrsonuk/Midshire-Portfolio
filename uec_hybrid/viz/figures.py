"""Interactive Plotly figures. Each returns a go.Figure the Flask app serialises."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from . import palette as P
from ..analysis.metrics import resource_utilisation, stage_waits


def sd_stocks_figure(result, pathway) -> go.Figure:
    hist = result.get("sd_history") or []
    fig = go.Figure()
    if hist:
        hours = [t / 60.0 for t, _ in hist]
        fig.add_trace(go.Scatter(x=hours, y=[s["bed_occupancy"] * 100 for _, s in hist],
                                 name="Inpatient bed occupancy %", line=dict(color=P.NHS_BLUE, width=2),
                                 hovertemplate="Hour %{x:.0f}<br>Inpatient beds: %{y:.1f}%<extra></extra>"))
        fig.add_trace(go.Scatter(x=hours, y=[s["mh_occupancy"] * 100 for _, s in hist],
                                 name="MH bed occupancy %", line=dict(color=P.NHS_AQUA, width=2),
                                 hovertemplate="Hour %{x:.0f}<br>MH beds: %{y:.1f}%<extra></extra>"))
        fig.add_trace(go.Scatter(x=hours, y=[s["crowding"] * 100 for _, s in hist],
                                 name="ED crowding index %", line=dict(color=P.NHS_ORANGE, width=2, dash="dot"),
                                 hovertemplate="Hour %{x:.0f}<br>ED crowding: %{y:.1f}%<extra></extra>"))
        fig.add_hline(y=92, line=dict(color=P.NHS_RED, width=1, dash="dash"),
                      annotation_text="92% exit-block threshold")
    fig.update_layout(P.LAYOUT, height=360, title="System Dynamics - stocks over time",
                      xaxis_title="hours", yaxis_title="%",
                      legend=dict(orientation="h", y=-0.2))
    return fig


def sd_feedback_figure(result) -> go.Figure:
    hist = result.get("sd_history") or []
    fig = go.Figure()
    if hist:
        hours = [t / 60.0 for t, _ in hist]
        fig.add_trace(go.Scatter(x=hours, y=[s["bed_wait_multiplier"] for _, s in hist],
                                 name="Bed-wait multiplier (exit-block)", line=dict(color=P.NHS_RED, width=2),
                                 hovertemplate="Hour %{x:.0f}<br>Bed-wait multiplier: %{y:.2f}×<extra></extra>"))
        fig.add_trace(go.Scatter(x=hours, y=[1 + s["community_pull"] * 5 for _, s in hist],
                                 name="Community pull (rel.)", line=dict(color=P.NHS_GREEN, width=2),
                                 hovertemplate="Hour %{x:.0f}<br>Community pull: %{y:.2f} (rel.)<extra></extra>"))
    fig.update_layout(P.LAYOUT, height=300, title="Feedback signals (SD → DES)",
                      xaxis_title="hours", yaxis_title="× / relative",
                      legend=dict(orientation="h", y=-0.25))
    return fig


def utilisation_figure(result, pathway) -> go.Figure:
    u = resource_utilisation(result, pathway).head(12).iloc[::-1]
    colours = [P.NHS_RED if v > 85 else P.NHS_ORANGE if v > 70 else P.NHS_AQUA
               for v in u["utilisation"]]
    fig = go.Figure(go.Bar(x=u["utilisation"], y=[r.replace("_", " ") for r in u["resource"]],
                           orientation="h", marker_color=colours,
                           text=[f"{v:.0f}%" for v in u["utilisation"]], textposition="outside",
                           hovertemplate="%{y}<br>%{x:.0f}% of capacity<extra></extra>"))
    fig.update_layout(P.LAYOUT, height=380, title="Resource utilisation - bottlenecks in red",
                      xaxis_title="% of capacity in use", xaxis_range=[0, 105])
    return fig


def waits_figure(result) -> go.Figure:
    w = stage_waits(result).head(10).iloc[::-1]
    fig = go.Figure(go.Bar(x=w["mean_wait"], y=w["stage_label"], orientation="h",
                           marker_color=P.NHS_BRIGHT,
                           text=[f"{v:.0f}" for v in w["mean_wait"]], textposition="outside",
                           hovertemplate="%{y}<br>Mean queue wait: %{x:.0f} min<extra></extra>"))
    fig.update_layout(P.LAYOUT, height=380, title="Where patients wait - mean queue (min)",
                      xaxis_title="minutes")
    return fig


def montecarlo_figure(mc, metric="four_hour", label="4-hour compliance (%)") -> go.Figure:
    s = mc["summary"].get(metric)
    fig = go.Figure()
    if s:
        vals = mc["table"][metric].dropna().to_numpy()
        fig.add_trace(go.Histogram(x=vals, nbinsx=14, marker_color=P.NHS_LIGHT,
                                   marker_line=dict(color="white", width=1),
                                   hovertemplate="%{x:.1f}%<br>%{y} simulated weeks<extra></extra>"))
        fig.add_vline(x=s["mean"], line=dict(color=P.NHS_DARK, width=2),
                      annotation_text=f"mean {s['mean']:.1f}")
        fig.add_vrect(x0=s["ci_low"], x1=s["ci_high"], fillcolor=P.NHS_BLUE, opacity=0.12,
                      line_width=0, annotation_text="95% CI", annotation_position="top left")
    fig.update_layout(P.LAYOUT, height=340, title=f"Monte-Carlo - {label}",
                      xaxis_title=label, yaxis_title="replications")
    return fig


def occupancy_band_figure(mc) -> go.Figure:
    """Mean inpatient occupancy over time across MC replications with a CI band."""
    series = [s for s in mc.get("occ_series", []) if s]
    fig = go.Figure()
    if series:
        L = min(len(s) for s in series)
        arr = np.array([s[:L] for s in series])
        hours = np.arange(L)
        mean = arr.mean(0); lo = np.percentile(arr, 2.5, 0); hi = np.percentile(arr, 97.5, 0)
        fig.add_trace(go.Scatter(x=np.r_[hours, hours[::-1]], y=np.r_[hi, lo[::-1]],
                                 fill="toself", fillcolor="rgba(0,94,184,0.15)",
                                 line=dict(width=0), name="95% CI", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=hours, y=mean, line=dict(color=P.NHS_BLUE, width=2),
                                 name="mean occupancy",
                                 hovertemplate="Hour %{x}<br>Occupancy: %{y:.1f}%<extra></extra>"))
        fig.add_hline(y=92, line=dict(color=P.NHS_RED, width=1, dash="dash"))
    fig.update_layout(P.LAYOUT, height=340, title="Bed occupancy across replications",
                      xaxis_title="hours", yaxis_title="occupancy %")
    return fig


def scenario_figure(cmp, metric="four_hour", label="4-hour compliance (%)",
                    higher_better=True) -> go.Figure:
    rows = cmp["rows"]
    names = [r["scenario"] for r in rows]
    vals = [r.get(metric, 0) for r in rows]
    base = vals[0]
    colours = [P.NHS_GREY] + [(P.NHS_GREEN if (v >= base) == higher_better else P.NHS_RED)
                              for v in vals[1:]]
    err = None
    if f"{metric}_lo" in rows[0]:
        err = dict(type="data", symmetric=False,
                   array=[r[f"{metric}_hi"] - r[metric] for r in rows],
                   arrayminus=[r[metric] - r[f"{metric}_lo"] for r in rows],
                   color=P.NHS_GREY, thickness=1.2, width=4)
    fig = go.Figure(go.Bar(x=names, y=vals, marker_color=colours, error_y=err,
                           text=[f"{v:.0f}" for v in vals], textposition="outside",
                           hovertemplate="%{x}<br>%{y:.0f}%<extra></extra>"))
    fig.add_hline(y=base, line=dict(color=P.NHS_GREY, width=1, dash="dash"), opacity=0.6)
    fig.update_layout(P.LAYOUT, height=380, title=f"Scenario comparison - {label}",
                      yaxis_title=label)
    return fig


def tornado_figure(tor) -> go.Figure:
    bars = tor["bars"][::-1]
    colours = [P.NHS_GREEN if b["delta"] >= 0 else P.NHS_RED for b in bars]
    fig = go.Figure(go.Bar(x=[b["delta"] for b in bars], y=[b["lever"] for b in bars],
                           orientation="h", marker_color=colours,
                           text=[f"{b['delta']:+.1f}" for b in bars], textposition="outside",
                           hovertemplate="%{y}<br>Change: %{x:+.1f} percentage points<extra></extra>"))
    fig.update_layout(P.LAYOUT, height=360,
                      title=f"Sensitivity - change in {tor['metric'].replace('_',' ')} vs baseline",
                      xaxis_title="percentage-point change")
    return fig


def sankey_figure(result, pathway) -> go.Figure:
    """Patient flow as a Sankey: every stage-to-stage volume in one picture."""
    from ..analysis.metrics import flow_counts
    edges = flow_counts(result, pathway)
    fig = go.Figure()
    if not edges.empty:
        labels = sorted(set(edges["source"]) | set(edges["target"]))
        idx = {l: i for i, l in enumerate(labels)}
        fig.add_trace(go.Sankey(
            arrangement="snap",
            node=dict(label=labels, pad=12, thickness=13,
                      color=[P.NHS_RED if "Admitted" in l else P.NHS_GREEN if "Discharged" in l
                             else P.NHS_ORANGE if "without being seen" in l else P.NHS_BLUE
                             for l in labels]),
            link=dict(source=[idx[s] for s in edges["source"]],
                      target=[idx[t] for t in edges["target"]],
                      value=list(edges["value"]),
                      color="rgba(0,94,184,.18)",
                      hovertemplate="%{source.label} → %{target.label}<br>"
                                    "%{value:.0f} patients/week<extra></extra>")))
    fig.update_layout(P.LAYOUT, height=460, title="Patient flow (weekly volumes)")
    return fig


def occupancy_heatmap_figure(result, pathway) -> go.Figure:
    """Hour-of-day x area heatmap of average concurrent occupancy: where the
    department runs hot, and when."""
    from .flow_model import _occ_by_hour
    events = result["events"]
    w, dur = pathway.warmup, pathway.sim_duration
    rows, names = [], []
    for nid, node in pathway.nodes.items():
        if node.get("type") != "process":
            continue
        sub = events[events["stage"] == nid]
        if len(sub) < 10:
            continue
        rows.append(_occ_by_hour(sub["service_start"].to_numpy(),
                                 sub["service_end"].to_numpy(), w, dur))
        names.append(node.get("label", nid))
    fig = go.Figure(go.Heatmap(
        z=rows, x=[f"{h:02d}:00" for h in range(24)], y=names,
        colorscale=[[0, "#F0F4F7"], [0.5, "#41B6E6"], [1, P.NHS_DARK]],
        colorbar=dict(title="patients"),
        hovertemplate="%{y}<br>%{x}<br>%{z:.0f} patients (average)<extra></extra>"))
    fig.update_layout(P.LAYOUT, height=max(340, 26 * len(names) + 100),
                      title="Who is where, by hour of day (average patients in area)",
                      margin=dict(l=180))
    return fig
