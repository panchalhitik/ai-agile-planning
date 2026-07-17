"""Mission Control: the landing page. Hero, KPIs, trend charts, seeded
anomaly callouts, and a hand-off into the copilot."""

from __future__ import annotations

import streamlit as st

from src import analytics
from src import visualizations as viz
from src.datasource import get_active
from src.ui import components as ui
from src.ui.chat import SUGGESTED

data, meta = get_active()
today = meta["today"]

sm = analytics.sprint_metrics(data.issues, data.sprints)
kpis = analytics.headline_kpis(data.issues, data.sprints)
health = analytics.sprint_health(data.issues, data.sprints, today)
forecast = analytics.monte_carlo_forecast(data.issues, data.sprints, today)

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
health_chip = (
    ui.chip("● sprint on track", "ok")
    if health["on_track"]
    else ui.chip("● sprint behind the clock", "danger")
)
chips = [
    ui.chip(f"🗓 {health['sprint_name']} · day {health['days_elapsed']}/{health['days_total']}"),
    health_chip,
    ui.chip(f"⛔ {kpis['blocked_points']} pts blocked", "danger" if kpis["blocked_points"] else "ok"),
    ui.source_chip(),
    ui.ai_mode_chip(),
]
subtitle = meta.get("blurb") or "Sprint analytics with an AI copilot grounded in tested math."
codename = f" · {meta['codename']}" if meta.get("codename") else ""
ui.hero(f"{meta['project_name']}{codename}", subtitle, chips)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
done_pct = kpis["done_points"] / kpis["total_points"] * 100 if kpis["total_points"] else 0
p85 = forecast["percentiles"]["p85"] if forecast.get("ok") else None
cards = [
    {
        "label": "Scope delivered",
        "value": f"{done_pct:.0f}%",
        "delta": f"{kpis['done_points']} of {kpis['total_points']} pts",
    },
    {
        "label": "Rolling velocity",
        "value": f"{kpis['velocity_3']:.0f} pts",
        "delta": "3-sprint average",
    },
    {
        "label": "Blocked now",
        "value": f"{kpis['blocked_points']} pts",
        "delta": "needs unblocking",
        "tone": "danger" if kpis["blocked_points"] > 20 else "warn",
    },
    {
        "label": "Current sprint",
        "value": f"{health['completion_pct']:.0f}%",
        "delta": f"vs {health['time_pct']:.0f}% of time gone",
        "tone": "ok" if health["on_track"] else "danger",
    },
]
if p85:
    cards.append(
        {
            "label": "Backlog done by (p85)",
            "value": p85["finish_date"].strftime("%d %b"),
            "delta": f"{p85['sprints']} sprints at current velocity",
        }
    )
ui.kpi_row(cards)

st.markdown("")

# ---------------------------------------------------------------------------
# Charts + insight
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    st.markdown("##### Commit vs completed")
    st.plotly_chart(viz.burn_chart(sm), theme=None, width="stretch")
with col2:
    st.markdown("##### Velocity trend")
    st.plotly_chart(viz.velocity_trend(sm), theme=None, width="stretch")

ui.insight_card("overview")

# ---------------------------------------------------------------------------
# Anomaly callouts + copilot hand-off
# ---------------------------------------------------------------------------
ui.anomaly_callouts(
    {
        "overload": "views/sprint.py",
        "blocker_chain": "views/dependencies.py",
        "critical_epic": "views/epics_risk.py",
    }
)

st.markdown("##### Ask the copilot")


def _overview_pill() -> None:
    ss = st.session_state
    if ss.get("overview_pills"):
        ss["copilot_pending"] = ss["overview_pills"]
        ss["overview_pills"] = None
        ss["_go_copilot"] = True


st.pills(
    "Ask the copilot",
    SUGGESTED,
    key="overview_pills",
    on_change=_overview_pill,
    label_visibility="collapsed",
)
if st.session_state.pop("_go_copilot", False):
    st.switch_page("views/copilot.py")
