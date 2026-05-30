"""AI-Assisted Agile Planning & Analytics Dashboard - Streamlit entry point.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import ai_summary, analytics, data_loader, visualizations as viz

st.set_page_config(
    page_title="AI-Assisted Agile Planning Dashboard",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Boot-strap data
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load() -> data_loader.AgileData:
    return data_loader.load_data()


if not data_loader.ensure_data_exists():
    st.error(
        "Sample data is missing. Run `python data/generate_data.py` once "
        "(or click the button below) to create the synthetic Jira dataset."
    )
    if st.button("Generate sample data now", type="primary"):
        from data.generate_data import write_outputs

        write_outputs()
        st.cache_data.clear()
        st.rerun()
    st.stop()

data = _load()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🧭 Agile Planning")
st.sidebar.caption(
    "Jira-style sprint analytics with AI-assisted summaries. "
    "Synthetic data — replace `data/issues.csv` with your own export to use it for real."
)

view = st.sidebar.radio(
    "View",
    ["Overview", "Sprint deep-dive", "Epics & risk", "Dependencies", "AI summaries", "Tableau export"],
)

sprint_options = data.sprints["sprint_name"].tolist()
selected_sprint_name = st.sidebar.selectbox(
    "Focus sprint",
    sprint_options,
    index=max(0, len(sprint_options) - 4),
)
selected_sprint_id = data.sprints.loc[
    data.sprints["sprint_name"] == selected_sprint_name, "sprint_id"
].iloc[0]

st.sidebar.markdown("---")
key_present = bool(
    ai_summary._get_api_key()  # internal helper — fine in the same package
)
st.sidebar.markdown(
    "**AI summaries**: "
    + ("✅ Anthropic key detected" if key_present else "⚙️ Using rules-based fallback")
)
st.sidebar.caption(
    "Add `ANTHROPIC_API_KEY` to `.streamlit/secrets.toml` to enable Claude-generated summaries."
)


# ---------------------------------------------------------------------------
# Precompute analytics
# ---------------------------------------------------------------------------
sprint_metrics = analytics.sprint_metrics(data.issues, data.sprints)
epic_progress_df = analytics.epic_progress(data.issues, data.epics)
risk_df = analytics.delivery_risk(data.issues, data.epics)
blockers_df = analytics.blocker_hotspots(data.issues)
deps_df = analytics.dependency_edges(data.issues)
kpis = analytics.headline_kpis(data.issues, data.sprints)


def _kpi_row():
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total issues", kpis["total_issues"])
    c2.metric("Total points", kpis["total_points"])
    c3.metric("Done points", kpis["done_points"])
    c4.metric("Blocked points", kpis["blocked_points"], delta_color="inverse")
    c5.metric("Rolling velocity (3 sprints)", kpis["velocity_3"])


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
def view_overview() -> None:
    st.title("Delivery overview")
    st.caption("Portfolio health across all in-flight sprints and epics.")
    _kpi_row()
    st.markdown("###")
    col1, col2 = st.columns(2)
    col1.plotly_chart(viz.burn_chart(sprint_metrics), use_container_width=True)
    col2.plotly_chart(viz.velocity_trend(sprint_metrics), use_container_width=True)

    st.plotly_chart(viz.issue_type_breakdown(data.issues), use_container_width=True)

    st.subheader("Sprint metrics")
    st.dataframe(
        sprint_metrics[
            [
                "sprint_name", "start_date", "end_date",
                "capacity_points", "committed_points",
                "completed_points", "blocked_points",
                "completion_pct", "over_commit_pct",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def view_sprint() -> None:
    st.title(f"Sprint deep-dive · {selected_sprint_name}")
    sprint_row = sprint_metrics[sprint_metrics["sprint_id"] == selected_sprint_id].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capacity", int(sprint_row["capacity_points"]))
    c2.metric("Committed", int(sprint_row["committed_points"]),
              delta=f"{sprint_row['over_commit_pct']}% vs capacity")
    c3.metric("Completed", int(sprint_row["completed_points"]),
              delta=f"{sprint_row['completion_pct']}% of commit")
    c4.metric("Blocked", int(sprint_row["blocked_points"]), delta_color="inverse")

    st.markdown("###")
    cap_df = analytics.capacity_vs_load(data.issues, data.team, selected_sprint_id)
    st.plotly_chart(viz.capacity_utilisation(cap_df), use_container_width=True)

    overloaded = cap_df[cap_df["is_overloaded"]]
    if not overloaded.empty:
        st.warning(
            "Overloaded (>110% utilisation): "
            + ", ".join(overloaded["member"].tolist())
        )

    sprint_issues = data.issues[data.issues["sprint_id"] == selected_sprint_id]
    st.subheader(f"Issues in {selected_sprint_name} ({len(sprint_issues)})")
    st.dataframe(
        sprint_issues[
            ["issue_key", "summary", "issue_type", "epic_id",
             "assignee", "story_points", "status", "priority", "blocked_by"]
        ],
        use_container_width=True,
        hide_index=True,
    )


def view_epics() -> None:
    st.title("Epics & delivery risk")
    _kpi_row()
    st.markdown("###")
    col1, col2 = st.columns(2)
    col1.plotly_chart(viz.epic_progress_chart(epic_progress_df), use_container_width=True)
    col2.plotly_chart(viz.risk_heatmap(risk_df, data.epics), use_container_width=True)

    st.subheader("Risk drivers")
    merged = risk_df.merge(data.epics, on="epic_id")
    for _, row in merged.sort_values("score", ascending=False).iterrows():
        with st.expander(f"{row['epic_id']} · {row['epic_name']} — risk {row['score']} ({row['band']})"):
            st.write(f"**Priority:** {row['priority']} · **Owner team:** {row['owner_team']}")
            st.write("**Drivers:**")
            for d in row["drivers"]:
                st.write(f"- {d}")


def view_dependencies() -> None:
    st.title("Dependencies")
    st.caption("Hover nodes for issue status. Red = blocked.")
    st.plotly_chart(viz.dependency_graph(data.issues, deps_df), use_container_width=True)

    st.subheader("Top blocker hotspots")
    if blockers_df.empty:
        st.info("No active blockers detected.")
    else:
        st.dataframe(blockers_df, use_container_width=True, hide_index=True)

    st.subheader("All dependency edges")
    st.dataframe(deps_df, use_container_width=True, hide_index=True)


def view_ai() -> None:
    st.title("AI-assisted summaries")
    st.caption(
        "Three audiences, one dataset. Generated by Claude when an API key is "
        "configured; deterministic fallback otherwise. Numbers come from the "
        "analytics layer, not the model — the model only writes the narrative."
    )

    audience = st.radio(
        "Audience",
        ["sprint", "backlog", "leadership"],
        horizontal=True,
        format_func=lambda x: {
            "sprint": "🏃 Sprint review",
            "backlog": "🪜 Backlog refinement",
            "leadership": "🧑‍💼 Leadership briefing",
        }[x],
    )

    payload = ai_summary.build_payload(kpis, sprint_metrics, risk_df, blockers_df)

    if st.button("Generate summary", type="primary"):
        with st.spinner("Composing…"):
            result = ai_summary.summarise(audience, payload)
        st.markdown(result.text)
        st.caption(
            f"_Source: {result.source}"
            + (f" · model: {result.model}" if result.model else "")
            + "_"
        )

    with st.expander("Show the structured data that was sent to the model"):
        st.json(payload)


def view_export() -> None:
    st.title("Tableau export")
    st.caption(
        "Download flat CSVs ready to load into Tableau. Use `sprint_metrics.csv` "
        "for a dashboard of velocity and over-commit, and `epic_risk.csv` to "
        "drive a risk heatmap."
    )

    exports = {
        "issues.csv": data.issues,
        "sprint_metrics.csv": sprint_metrics,
        "epic_progress.csv": epic_progress_df,
        "epic_risk.csv": risk_df,
        "dependencies.csv": deps_df,
    }

    for name, df in exports.items():
        col1, col2 = st.columns([3, 1])
        col1.write(f"**{name}** — {len(df)} rows × {len(df.columns)} cols")
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        col2.download_button(
            label="Download",
            data=buf.getvalue(),
            file_name=name,
            mime="text/csv",
            key=f"dl-{name}",
        )

    st.markdown("---")
    st.subheader("Suggested Tableau views")
    st.markdown(
        """
        - **Burn-down by sprint** — `sprint_metrics.csv`: rows = sprint, dual-axis bar of `committed_points` vs `completed_points`, line for `capacity_points`.
        - **Velocity trend** — `sprint_metrics.csv`: running average of `completed_points` over the last 3 sprints.
        - **Epic risk matrix** — `epic_risk.csv`: heatmap of `epic_id` vs `band`, size by `score`.
        - **Capacity vs assignment** — `issues.csv`: bar of `story_points` grouped by `assignee` filtered to a single sprint.
        """
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
ROUTES = {
    "Overview": view_overview,
    "Sprint deep-dive": view_sprint,
    "Epics & risk": view_epics,
    "Dependencies": view_dependencies,
    "AI summaries": view_ai,
    "Tableau export": view_export,
}

ROUTES[view]()

st.markdown("---")
st.caption(
    "Built with Streamlit · Pandas · Plotly · Anthropic. "
    "Synthetic data is regenerated by `python data/generate_data.py`."
)
