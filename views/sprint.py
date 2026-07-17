"""Sprint deep-dive: one sprint's burn-down, capacity, and issues."""

from __future__ import annotations

import streamlit as st

from src import analytics
from src import visualizations as viz
from src.datasource import get_active
from src.ui import components as ui

data, meta = get_active()
today = meta["today"]
ss = st.session_state

ui.page_header("Sprint deep-dive", "Capacity, burn-down, and every issue in one sprint.")

sm = analytics.sprint_metrics(data.issues, data.sprints)
current_id = analytics.current_sprint_id(data.sprints, today)

# Sprint picker: last five sprints as segments, default = current.
recent = sm.tail(5)
options = recent["sprint_name"].tolist()
default_name = sm.loc[sm["sprint_id"] == current_id, "sprint_name"].iloc[0]
picker_key = f"sprint_pick_{ss['data_version']}"
selected_name = st.segmented_control(
    "Sprint",
    options,
    default=default_name if default_name in options else options[-1],
    key=picker_key,
    label_visibility="collapsed",
)
if selected_name is None:
    selected_name = default_name if default_name in options else options[-1]
row = sm[sm["sprint_name"] == selected_name].iloc[0]
sprint_id = row["sprint_id"]
is_current = sprint_id == current_id

# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------
over = float(row["over_commit_pct"])
ui.kpi_row(
    [
        {"label": "Capacity", "value": int(row["capacity_points"]), "delta": "team pts"},
        {
            "label": "Committed",
            "value": int(row["committed_points"]),
            "delta": f"{over:+.0f}% vs capacity",
            "tone": "danger" if over > 15 else ("warn" if over > 5 else "ok"),
        },
        {
            "label": "Completed",
            "value": int(row["completed_points"]),
            "delta": f"{row['completion_pct']:.0f}% of commit",
            "tone": "ok" if row["completion_pct"] >= 75 else "warn",
        },
        {
            "label": "Blocked",
            "value": int(row["blocked_points"]),
            "delta": "pts stuck",
            "tone": "danger" if row["blocked_points"] > 10 else "warn",
        },
    ]
)

st.markdown("")
col1, col2 = st.columns(2)
with col1:
    st.markdown("##### Burn-down (ideal vs actual)")
    st.plotly_chart(viz.sprint_burndown(data.issues, row, today), theme=None, width="stretch")
with col2:
    st.markdown("##### Per-person utilisation")
    cap_df = analytics.capacity_vs_load(data.issues, data.team, sprint_id)
    st.plotly_chart(viz.capacity_utilisation(cap_df), theme=None, width="stretch")

overloaded = cap_df[cap_df["is_overloaded"]].sort_values("utilisation_pct", ascending=False)
if not overloaded.empty:
    names = ", ".join(
        f"**{r.member}** ({r.utilisation_pct:.0f}%)" for r in overloaded.itertuples()
    )
    st.warning(f"Overloaded (>110% of capacity): {names}. Rebalance before adding scope.")

if is_current:
    ui.insight_card("sprint")

# ---------------------------------------------------------------------------
# Issues table
# ---------------------------------------------------------------------------
sprint_issues = data.issues[data.issues["sprint_id"] == sprint_id]
st.markdown(f"##### Issues in {selected_name} ({len(sprint_issues)})")

status_icon = {"Done": "✅", "In Progress": "🔵", "To Do": "⚪", "Blocked": "⛔"}
table = sprint_issues[
    ["issue_key", "summary", "issue_type", "epic_id", "assignee",
     "story_points", "status", "priority", "blocked_by"]
].copy()
table["status"] = table["status"].map(lambda s: f"{status_icon.get(s, '')} {s}")

st.dataframe(
    table,
    width="stretch",
    hide_index=True,
    column_config={
        "issue_key": st.column_config.TextColumn("Key", width="small"),
        "summary": st.column_config.TextColumn("Summary", width="large"),
        "issue_type": st.column_config.TextColumn("Type", width="small"),
        "epic_id": st.column_config.TextColumn("Epic", width="small"),
        "story_points": st.column_config.NumberColumn("Pts", width="small"),
        "status": st.column_config.TextColumn("Status", width="small"),
        "priority": st.column_config.TextColumn("Priority", width="small"),
        "blocked_by": st.column_config.TextColumn("Blocked by", width="small"),
    },
)
