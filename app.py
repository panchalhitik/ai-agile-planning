"""Sprint Copilot — AI-assisted agile planning dashboard.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.datasource import init_session_state  # noqa: E402
from src.ui import theme  # noqa: E402

st.set_page_config(
    page_title="Sprint Copilot",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

theme.register_plotly_template()
theme.inject_css()
init_session_state()

pages = {
    "Analyze": [
        st.Page("views/overview.py", title="Overview", icon=":material/space_dashboard:", default=True),
        st.Page("views/sprint.py", title="Sprint deep-dive", icon=":material/sprint:"),
        st.Page("views/epics_risk.py", title="Epics & risk", icon=":material/flag:"),
        st.Page("views/dependencies.py", title="Dependencies", icon=":material/account_tree:"),
        st.Page("views/forecast.py", title="Forecast", icon=":material/query_stats:"),
    ],
    "AI": [
        st.Page("views/copilot.py", title="Copilot", icon=":material/forum:"),
        st.Page("views/briefings.py", title="Briefings", icon=":material/description:"),
    ],
    "Data": [
        st.Page("views/data_hub.py", title="Data hub", icon=":material/database:"),
    ],
}

with st.sidebar:
    st.markdown("### 🧭 Sprint Copilot")
    st.caption(
        "AI-assisted agile planning. The model narrates; the tested "
        "analytics layer computes every number."
    )

nav = st.navigation(pages, position="sidebar")
nav.run()
