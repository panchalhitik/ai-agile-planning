"""Monte Carlo completion forecast with what-if controls."""

from __future__ import annotations

import streamlit as st

from src import analytics
from src import visualizations as viz
from src.datasource import get_active
from src.ui import components as ui

data, meta = get_active()
today = meta["today"]

ui.page_header(
    "Forecast",
    "When does the remaining backlog land? Simulated from your own velocity history.",
)

baseline = analytics.monte_carlo_forecast(data.issues, data.sprints, today)
if not baseline.get("ok"):
    st.info(f"Forecast unavailable: {baseline.get('reason')}")
    st.stop()

# ---------------------------------------------------------------------------
# What-if controls
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("##### What-if scenario")
    col1, col2 = st.columns([2, 1])
    scope_delta = col1.slider(
        "Scope change (%)",
        min_value=-30,
        max_value=30,
        value=0,
        step=5,
        help="Cut or add remaining scope before simulating.",
    )
    team_size = max(len(data.team), 1)
    eng_delta = col2.segmented_control(
        "Team",
        options=["-1 engineer", "same team", "+1 engineer"],
        default="same team",
    )
    capacity_delta = {"-1 engineer": -100 / team_size, "same team": 0.0, "+1 engineer": 100 / team_size}[
        eng_delta or "same team"
    ]

scenario_active = scope_delta != 0 or capacity_delta != 0
scenario = (
    analytics.monte_carlo_forecast(
        data.issues, data.sprints, today,
        scope_delta_pct=scope_delta, capacity_delta_pct=capacity_delta,
    )
    if scenario_active
    else None
)

# ---------------------------------------------------------------------------
# Percentile cards
# ---------------------------------------------------------------------------
def _cards(fc: dict) -> list[dict]:
    cards = []
    for p, tone in (("p50", "warn"), ("p70", ""), ("p85", "ok"), ("p95", "")):
        row = fc["percentiles"][p]
        cards.append(
            {
                "label": f"{p} confidence",
                "value": row["finish_date"].strftime("%d %b %Y"),
                "delta": f"{row['sprints']} sprint(s)",
                "tone": tone,
            }
        )
    return cards


st.markdown(
    f"##### Baseline — remaining **{baseline['remaining_points']:.0f} pts**, "
    f"mean velocity {baseline['velocity_mean']:.0f} pts/sprint"
)
ui.kpi_row(_cards(baseline))

if scenario and scenario.get("ok"):
    st.markdown(
        f"##### Scenario — scope {scope_delta:+d}%, capacity {capacity_delta:+.0f}% "
        f"→ remaining **{scenario['remaining_points']:.0f} pts**"
    )
    ui.kpi_row(_cards(scenario))
    delta_sprints = (
        scenario["percentiles"]["p85"]["sprints"] - baseline["percentiles"]["p85"]["sprints"]
    )
    if delta_sprints:
        direction = "later" if delta_sprints > 0 else "earlier"
        st.caption(f"At 85% confidence the scenario lands **{abs(delta_sprints)} sprint(s) {direction}**.")

st.markdown("")
st.markdown("##### Distribution of outcomes")
st.plotly_chart(
    viz.forecast_histogram(baseline, scenario if scenario_active else None),
    theme=None,
    width="stretch",
)

ui.insight_card("forecast")

with st.expander("How this forecast works"):
    st.markdown(
        """
        **Monte Carlo over your own history — no assumptions about ideal teams.**

        1. Take completed points from every *finished* sprint
          (`{samples}` in this dataset).
        2. Run 4,000 simulations. Each one repeatedly draws a random historical
           sprint velocity until the remaining backlog is burned down.
        3. Count how many sprints each simulation needed; read percentiles off
           that distribution.

        The p50 date is a coin flip. The p85 date is what you should say out
        loud to stakeholders. What-if deltas simply scale the remaining scope
        or the sampled velocities before simulating — capacity scaling is a
        rough proxy that assumes even skill distribution.
        """.format(samples=", ".join(f"{v:.0f}" for v in baseline["velocity_samples"]))
    )
