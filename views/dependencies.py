"""Dependencies: the blocker graph and hotspot ranking."""

from __future__ import annotations

import streamlit as st

from src import analytics
from src import visualizations as viz
from src.datasource import get_active
from src.ui import components as ui

data, meta = get_active()

ui.page_header("Dependencies", "Who blocks whom — node size scales with blast radius.")

deps = analytics.dependency_edges(data.issues)
hotspots = analytics.blocker_hotspots(data.issues)

if not hotspots.empty and int(hotspots.iloc[0]["blocks_count"]) >= 3:
    top = hotspots.iloc[0]
    st.error(
        f"**{top['blocker']}** ({top['status']}) blocks **{int(top['blocks_count'])} issues** — "
        f"“{top['summary']}”. Unblocking it has the widest impact of any single action.",
        icon="⛔",
    )

st.plotly_chart(viz.dependency_graph(data.issues, deps), theme=None, width="stretch")
st.caption("Hover a node for the issue, status, and blast radius. Red = blocked, green = done.")

ui.insight_card("dependencies")

col1, col2 = st.columns(2)
with col1:
    st.markdown("##### Blocker hotspots")
    if hotspots.empty:
        st.info("No active blockers.")
    else:
        st.dataframe(hotspots, width="stretch", hide_index=True)
with col2:
    st.markdown("##### All dependency edges")
    if deps.empty:
        st.info("No dependencies recorded.")
    else:
        st.dataframe(
            deps.rename(columns={"source": "blocker", "target": "blocked issue"}),
            width="stretch",
            hide_index=True,
        )
