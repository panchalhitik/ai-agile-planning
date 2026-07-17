"""Plotly chart builders. Layout boilerplate lives in the shared template
(src.ui.theme.register_plotly_template); these functions only encode data."""

from __future__ import annotations

from datetime import date, timedelta

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

from src.ui.theme import BAND_COLOR, COLOR, STATUS_COLOR


def burn_chart(sprint_metrics: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        name="Committed",
        x=sprint_metrics["sprint_name"],
        y=sprint_metrics["committed_points"],
        marker_color=COLOR["primary"],
        opacity=0.85,
    )
    fig.add_bar(
        name="Completed",
        x=sprint_metrics["sprint_name"],
        y=sprint_metrics["completed_points"],
        marker_color=COLOR["ok"],
    )
    fig.add_scatter(
        name="Capacity",
        x=sprint_metrics["sprint_name"],
        y=sprint_metrics["capacity_points"],
        mode="lines",
        line=dict(color=COLOR["warn"], dash="dash", width=2),
    )
    fig.update_layout(barmode="group", yaxis_title="Story points", height=340)
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
        line=dict(color=COLOR["ok"], width=2),
        marker=dict(size=7),
    )
    fig.add_scatter(
        x=df["sprint_name"],
        y=df["rolling_velocity"],
        name="3-sprint rolling velocity",
        mode="lines",
        line=dict(color=COLOR["primary"], width=3),
    )
    fig.update_layout(yaxis_title="Story points", height=340)
    return fig


def capacity_utilisation(cap_df: pd.DataFrame) -> go.Figure:
    df = cap_df.sort_values("utilisation_pct", ascending=True)
    colors = [
        COLOR["danger"] if v > 110 else (COLOR["warn"] if v > 90 else COLOR["ok"])
        for v in df["utilisation_pct"]
    ]
    fig = go.Figure(
        go.Bar(
            x=df["utilisation_pct"],
            y=df["member"],
            orientation="h",
            marker_color=colors,
            marker_line_width=0,
            text=[f"{v:.0f}%" for v in df["utilisation_pct"]],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.add_vline(x=100, line_dash="dash", line_color=COLOR["muted"], opacity=0.7)
    fig.update_layout(
        xaxis_title="Utilisation (assigned / capacity)",
        hovermode="y unified",
        height=max(300, 40 * len(df) + 80),
        xaxis_range=[0, max(130, float(df["utilisation_pct"].max()) * 1.2)],
    )
    return fig


def sprint_burndown(
    issues: pd.DataFrame, sprint_row: pd.Series, today: date
) -> go.Figure:
    """Ideal vs actual remaining points for one sprint, from Done issues'
    completion dates (updated_at)."""
    start = pd.to_datetime(sprint_row["start_date"]).date()
    end = pd.to_datetime(sprint_row["end_date"]).date()
    sprint_issues = issues[issues["sprint_id"] == sprint_row["sprint_id"]]
    committed = float(sprint_issues["story_points"].sum())

    done = sprint_issues[sprint_issues["status"] == "Done"].copy()
    done_dates = pd.to_datetime(done["updated_at"]).dt.date

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    last_real = min(today, end)
    actual_x, actual_y = [], []
    for day in days:
        if day > last_real:
            break
        burned = float(done.loc[[d <= day for d in done_dates], "story_points"].sum())
        actual_x.append(day)
        actual_y.append(committed - burned)

    fig = go.Figure()
    fig.add_scatter(
        x=[start, end],
        y=[committed, 0],
        name="Ideal",
        mode="lines",
        line=dict(color=COLOR["muted"], dash="dot", width=2),
    )
    fig.add_scatter(
        x=actual_x,
        y=actual_y,
        name="Actual",
        mode="lines+markers",
        line=dict(color=COLOR["accent"], width=3),
        marker=dict(size=5),
    )
    if today <= end:
        fig.add_vline(x=today, line_color=COLOR["warn"], line_dash="dash", opacity=0.6)
    fig.update_layout(yaxis_title="Points remaining", height=320)
    return fig


def epic_progress_chart(epic_df: pd.DataFrame) -> go.Figure:
    df = epic_df.sort_values("progress_pct", ascending=True)
    remaining = df["total_points"] - df["done_points"] - df["blocked_points"]
    fig = go.Figure()
    fig.add_bar(name="Done", x=df["done_points"], y=df["epic_name"],
                orientation="h", marker_color=COLOR["ok"])
    fig.add_bar(name="Blocked", x=df["blocked_points"], y=df["epic_name"],
                orientation="h", marker_color=COLOR["danger"])
    fig.add_bar(name="Remaining", x=remaining, y=df["epic_name"],
                orientation="h", marker_color=COLOR["border"])
    fig.update_layout(
        barmode="stack",
        xaxis_title="Story points",
        hovermode="y unified",
        height=max(300, 44 * len(df) + 80),
    )
    return fig


def risk_bars(risk_df: pd.DataFrame, epic_df: pd.DataFrame) -> go.Figure:
    merged = risk_df.merge(epic_df[["epic_id", "epic_name"]], on="epic_id", how="left")
    merged = merged.sort_values("score", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=merged["score"],
            y=merged["epic_name"],
            orientation="h",
            marker_color=[BAND_COLOR.get(b, COLOR["muted"]) for b in merged["band"]],
            marker_line_width=0,
            text=[f"{s:.0f} · {b}" for s, b in zip(merged["score"], merged["band"])],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        xaxis_title="Delivery risk (0 safe → 100 critical)",
        xaxis_range=[0, 118],
        hovermode="y unified",
        height=max(300, 44 * len(merged) + 80),
    )
    return fig


def dependency_graph(issues: pd.DataFrame, deps: pd.DataFrame) -> go.Figure:
    if deps.empty:
        fig = go.Figure()
        fig.update_layout(
            annotations=[dict(text="No dependencies", showarrow=False, font_size=14)]
        )
        return fig

    g = nx.DiGraph()
    for _, row in deps.iterrows():
        g.add_edge(row["source"], row["target"])
    pos = nx.spring_layout(g, seed=7, k=0.6)

    info = issues.set_index("issue_key")
    blocks_count = deps.groupby("source").size().to_dict()

    edge_x, edge_y = [], []
    for src, tgt in g.edges():
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.8, color=COLOR["border"]),
        hoverinfo="none", mode="lines", showlegend=False,
    )

    node_x, node_y, colors, sizes, texts = [], [], [], [], []
    for node in g.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        status = info.loc[node, "status"] if node in info.index else "?"
        summary = info.loc[node, "summary"] if node in info.index else ""
        n_blocks = blocks_count.get(node, 0)
        colors.append(STATUS_COLOR.get(status, COLOR["muted"]))
        sizes.append(10 + 5 * n_blocks)
        blocks_note = f"<br>blocks {n_blocks} issue(s)" if n_blocks else ""
        texts.append(f"<b>{node}</b> · {status}{blocks_note}<br>{summary}")

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers",
        hovertext=texts, hoverinfo="text", showlegend=False,
        marker=dict(size=sizes, color=colors, line=dict(width=1, color=COLOR["bg"])),
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        hovermode="closest",
        height=460,
    )
    return fig


def issue_type_breakdown(issues: pd.DataFrame) -> go.Figure:
    df = (
        issues.groupby(["sprint_id", "issue_type"])["story_points"]
        .sum()
        .reset_index()
    )
    type_color = {
        "Story": COLOR["primary"],
        "Task": COLOR["accent"],
        "Bug": COLOR["danger"],
        "Spike": COLOR["warn"],
    }
    fig = go.Figure()
    for issue_type in ("Story", "Task", "Bug", "Spike"):
        sub = df[df["issue_type"] == issue_type]
        fig.add_bar(
            name=issue_type,
            x=sub["sprint_id"],
            y=sub["story_points"],
            marker_color=type_color.get(issue_type, COLOR["muted"]),
        )
    fig.update_layout(barmode="stack", yaxis_title="Story points", height=320)
    return fig


def forecast_histogram(forecast: dict, compare: dict | None = None) -> go.Figure:
    """Distribution of sprints-to-finish from the Monte Carlo simulation."""
    fig = go.Figure()
    dist = forecast["distribution"]
    total = sum(dist.values())
    fig.add_bar(
        name="Baseline",
        x=list(dist.keys()),
        y=[v / total * 100 for v in dist.values()],
        marker_color=COLOR["primary"],
        opacity=0.9,
    )
    if compare and compare.get("ok"):
        dist2 = compare["distribution"]
        total2 = sum(dist2.values())
        fig.add_bar(
            name="Scenario",
            x=list(dist2.keys()),
            y=[v / total2 * 100 for v in dist2.values()],
            marker_color=COLOR["accent"],
            opacity=0.75,
        )
    p85 = forecast["percentiles"]["p85"]["sprints"]
    fig.add_vline(
        x=p85, line_color=COLOR["warn"], line_dash="dash",
        annotation_text="p85", annotation_font_color=COLOR["warn"],
    )
    fig.update_layout(
        barmode="overlay",
        xaxis_title="Sprints to finish remaining backlog",
        yaxis_title="% of simulations",
        height=360,
    )
    return fig
