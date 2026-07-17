"""Epics & delivery risk: progress, explainable risk scores, per-epic detail."""

from __future__ import annotations

import streamlit as st

from src import analytics
from src import visualizations as viz
from src.datasource import get_active
from src.ui import components as ui

data, meta = get_active()
today = meta["today"]

ui.page_header("Epics & risk", "Progress per epic and an explainable 0-100 delivery-risk score.")

progress = analytics.epic_progress(data.issues, data.epics)
risk = analytics.delivery_risk(data.issues, data.epics)

col1, col2 = st.columns(2)
with col1:
    st.markdown("##### Delivery progress (story points)")
    st.plotly_chart(viz.epic_progress_chart(progress), theme=None, width="stretch")
with col2:
    st.markdown("##### Delivery risk")
    st.plotly_chart(viz.risk_bars(risk, data.epics), theme=None, width="stretch")

ui.insight_card("epics")

# ---------------------------------------------------------------------------
# Risk drivers with per-epic detail
# ---------------------------------------------------------------------------
st.markdown("##### Why each score is what it is")
merged = risk.merge(data.epics, on="epic_id").sort_values("score", ascending=False)
band_tone = {"Critical": "danger", "High": "danger", "Medium": "warn", "Low": "ok"}

for _, row in merged.iterrows():
    label = f"{row['epic_name']} — risk {row['score']:.0f} ({row['band']})"
    with st.expander(label, expanded=row["band"] == "Critical"):
        st.markdown(
            ui.chip(row["band"], band_tone.get(row["band"], ""))
            + ui.chip(f"{row['priority']} priority")
            + ui.chip(f"owner: {row['owner_team']}"),
            unsafe_allow_html=True,
        )
        for driver in row["drivers"]:
            st.markdown(f"- {driver}")

        epic_issues = data.issues[data.issues["epic_id"] == row["epic_id"]]
        open_issues = epic_issues[epic_issues["status"] != "Done"]
        if not open_issues.empty:
            st.markdown(f"**Open issues ({len(open_issues)}):**")
            st.dataframe(
                open_issues[
                    ["issue_key", "summary", "sprint_id", "story_points", "status", "assignee", "blocked_by"]
                ],
                width="stretch",
                hide_index=True,
            )
