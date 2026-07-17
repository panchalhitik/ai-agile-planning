"""Audience-specific briefings: sprint review, backlog refinement, leadership."""

from __future__ import annotations

import streamlit as st

from src import analytics
from src.ai import briefings
from src.datasource import get_active
from src.ui import components as ui

data, meta = get_active()
ss = st.session_state

ui.page_header(
    "Briefings",
    "Three audiences, one dataset. The model writes the narrative; the analytics layer supplies every number.",
)

labels = {
    "sprint": "🏃 Sprint review",
    "backlog": "🪜 Backlog refinement",
    "leadership": "🧑‍💼 Leadership briefing",
}
audience_label = st.segmented_control(
    "Audience",
    options=list(labels.values()),
    default=labels["sprint"],
    label_visibility="collapsed",
)
audience = next(k for k, v in labels.items() if v == audience_label) if audience_label else "sprint"

kpis = analytics.headline_kpis(data.issues, data.sprints)
sm = analytics.sprint_metrics(data.issues, data.sprints)
risk = analytics.delivery_risk(data.issues, data.epics)
blockers = analytics.blocker_hotspots(data.issues)
payload = briefings.build_payload(kpis, sm, risk, blockers)

if st.button("Generate briefing", type="primary"):
    stream, source, model = briefings.summarise_stream(audience, payload)
    with st.container(border=True):
        text = st.write_stream(stream)
    ss["briefing_text"] = text if isinstance(text, str) else "".join(text)
    ss["briefing_audience"] = audience
    ss["briefing_source"] = (source, model)

if ss.get("briefing_text") and ss.get("briefing_audience") == audience:
    source, model = ss.get("briefing_source", ("", None))
    st.caption(
        f"Source: {'✦ Claude (' + str(model) + ')' if source == 'anthropic' else '⚙ deterministic rules'}"
    )
    st.download_button(
        "Download as Markdown",
        data=ss["briefing_text"],
        file_name=f"briefing_{audience}.md",
        mime="text/markdown",
    )

with st.expander("Show the structured data sent to the model"):
    st.json(payload, expanded=False)
