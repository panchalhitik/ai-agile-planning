"""Plotly chart builders. Kept here so app.py focuses on layout."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


COLORWAY = {
    "primary": "#6C7AE0",
    "accent": "#36C2CE",
    "warn": "#F4B860",
    "danger": "#E26D5C",
    "ok": "#67C29B",
    "muted": "#7C8194",
}


def burn_chart(sprint_metrics: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        name="Committed",
        x=sprint_metrics["sprint_name"],
        y=sprint_metrics["committed_points"],
        marker_color=COLORWAY["primary"],
    )
    fig.add_bar(
        name="Completed",
        x=sprint_metrics["sprint_name"],
        y=sprint_metrics["completed_points"],
        marker_color=COLORWAY["ok"],
    )
    fig.add_scatter(
        name="Capacity",
        x=sprint_metrics["sprint_name"],
        y=sprint_metrics["capacity_points"],
        mode="lines+markers",
        line=dict(color=COLORWAY["warn"], dash="dash"),
    )
    fig.update_layout(
        barmode="group",
        title="Sprint commit vs completed vs capacity",
        yaxis_title="Story points",
        legend_orientation="h",
        legend=dict(y=-0.2),
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig


def velocity_trend(sprint_metrics: pd.DataFrame) -> go.Figure:
    df = sprint_metrics.copy()
    df["rolling_velocity"] = (
        df["completed_points"].rolling(window=3, min_periods=1).mean().round(1)
    )
    fig = go.Figure()
    fig.add_scatter(
        x=df["sprint_name"],
        y=df["completed_points"],
        name="Completed",
        mode="lines+markers",
        line=dict(color=COLORWAY["ok"]),
    )
    fig.add_scatter(
        x=df["sprint_name"],
        y=df["rolling_velocity"],
        name="3-sprint rolling velocity",
        mode="lines",
        line=dict(color=COLORWAY["primary"], width=3),
    )
    fig.update_layout(
        title="Velocity trend",
        yaxis_title="Story points",
        legend_orientation="h",
        legend=dict(y=-0.2),
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig


def capacity_utilisation(cap_df: pd.DataFrame) -> go.Figure:
    df = cap_df.sort_values("utilisation_pct", ascending=True)
    colors = [
        COLORWAY["danger"] if v > 110 else (COLORWAY["warn"] if v > 90 else COLORWAY["ok"])
        for v in df["utilisation_pct"]
    ]
    fig = go.Figure(
        go.Bar(
            x=df["utilisation_pct"],
            y=df["member"],
            orientation="h",
            marker_color=colors,
            text=[f"{v:.0f}%" for v in df["utilisation_pct"]],
            textposition="outside",
        )
    )
    fig.add_vline(x=100, line_dash="dash", line_color=COLORWAY["muted"])
    fig.update_layout(
        title="Per-person utilisation (assigned / capacity)",
        xaxis_title="%",
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig


def epic_progress_chart(epic_df: pd.DataFrame) -> go.Figure:
    df = epic_df.sort_values("progress_pct", ascending=True)
    fig = go.Figure()
    fig.add_bar(
        name="Done",
        x=df["done_points"],
        y=df["epic_name"],
        orientation="h",
        marker_color=COLORWAY["ok"],
    )
    fig.add_bar(
        name="Blocked",
        x=df["blocked_points"],
        y=df["epic_name"],
        orientation="h",
        marker_color=COLORWAY["danger"],
    )
    fig.add_bar(
        name="Remaining",
        x=df["total_points"] - df["done_points"] - df["blocked_points"],
        y=df["epic_name"],
        orientation="h",
        marker_color=COLORWAY["muted"],
    )
    fig.update_layout(
        barmode="stack",
        title="Epic delivery progress (story points)",
        xaxis_title="Story points",
        legend_orientation="h",
        legend=dict(y=-0.2),
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig


def risk_heatmap(risk_df: pd.DataFrame, epic_df: pd.DataFrame) -> go.Figure:
    merged = risk_df.merge(epic_df[["epic_id", "epic_name"]], on="epic_id", how="left")
    merged = merged.sort_values("score", ascending=True)
    band_color = {
        "Low": COLORWAY["ok"],
        "Medium": COLORWAY["warn"],
        "High": COLORWAY["danger"],
        "Critical": "#8B1E3F",
    }
    fig = go.Figure(
        go.Bar(
            x=merged["score"],
            y=merged["epic_name"],
            orientation="h",
            marker_color=[band_color.get(b, COLORWAY["muted"]) for b in merged["band"]],
            text=[f"{s:.0f} - {b}" for s, b in zip(merged["score"], merged["band"])],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Delivery risk by epic (0 safe, 100 critical)",
        xaxis_title="Risk score",
        xaxis_range=[0, 110],
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig


def dependency_graph(issues: pd.DataFrame, deps: pd.DataFrame) -> go.Figure:
    if deps.empty:
        return go.Figure().update_layout(title="No dependencies")
    g = nx.DiGraph()
    for _, row in deps.iterrows():
        g.add_edge(row["source"], row["target"])
    pos = nx.spring_layout(g, seed=7, k=0.5)

    status_map = issues.set_index("issue_key")["status"].to_dict()
    status_color = {
        "Done": COLORWAY["ok"],
        "In Progress": COLORWAY["primary"],
        "To Do": COLORWAY["muted"],
        "Blocked": COLORWAY["danger"],
    }

    edge_x, edge_y = [], []
    for src, tgt in g.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.8, color=COLORWAY["muted"]),
        hoverinfo="none", mode="lines",
    )

    node_x, node_y, colors, texts = [], [], [], []
    for n in g.nodes():
        x, y = pos[n]
        node_x.append(x)
        node_y.append(y)
        colors.append(status_color.get(status_map.get(n, ""), COLORWAY["muted"]))
        texts.append(f"{n}<br>{status_map.get(n, 'unknown')}")

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers",
        hovertext=texts, hoverinfo="text",
        marker=dict(size=10, color=colors, line=dict(width=1, color="#000")),
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        title="Issue dependency graph (hover for status)",
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig


def issue_type_breakdown(issues: pd.DataFrame) -> go.Figure:
    df = issues.groupby(["sprint_id", "issue_type"])["story_points"].sum().reset_index()
    fig = px.bar(
        df, x="sprint_id", y="story_points", color="issue_type",
        title="Work type mix by sprint",
        labels={"sprint_id": "Sprint", "story_points": "Story points"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        legend_orientation="h",
        legend=dict(y=-0.2),
        margin=dict(l=10, r=10, t=50, b=20),
    )
    return fig
