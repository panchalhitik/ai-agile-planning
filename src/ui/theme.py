"""Design system: semantic colors, one CSS injection, one Plotly template.

Everything visual funnels through here so charts, cards, and chips stay
consistent. Native Streamlit theming (config.toml) does the heavy lifting;
the CSS below only adds what the theme can't express.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

COLOR = {
    "primary": "#7C8CF8",
    "accent": "#4ED8C7",
    "ok": "#5BC689",
    "warn": "#F2B25C",
    "danger": "#E5685C",
    "critical": "#C2455C",
    "muted": "#8B93A8",
    "bg": "#0B0E17",
    "bg2": "#141A29",
    "border": "#232B41",
    "text": "#E8EAF2",
    "text_dim": "#A6ADC2",
}

STATUS_COLOR = {
    "Done": COLOR["ok"],
    "In Progress": COLOR["primary"],
    "To Do": COLOR["muted"],
    "Blocked": COLOR["danger"],
}

BAND_COLOR = {
    "Low": COLOR["ok"],
    "Medium": COLOR["warn"],
    "High": COLOR["danger"],
    "Critical": COLOR["critical"],
}

PLOTLY_TEMPLATE = "agile_dark"


def register_plotly_template() -> None:
    if PLOTLY_TEMPLATE in pio.templates:
        pio.templates.default = PLOTLY_TEMPLATE
        return
    pio.templates[PLOTLY_TEMPLATE] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(
                family="'Source Sans Pro', 'Segoe UI', sans-serif",
                color=COLOR["text_dim"],
                size=13,
            ),
            colorway=[
                COLOR["primary"], COLOR["accent"], COLOR["ok"],
                COLOR["warn"], COLOR["danger"], COLOR["muted"],
            ],
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor=COLOR["bg2"],
                bordercolor=COLOR["border"],
                font=dict(color=COLOR["text"], size=12),
            ),
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis=dict(gridcolor=COLOR["border"], zerolinecolor=COLOR["border"],
                       showline=False, automargin=True),
            yaxis=dict(gridcolor=COLOR["border"], zerolinecolor=COLOR["border"],
                       showline=False, automargin=True),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
            bargap=0.25,
        )
    )
    pio.templates.default = PLOTLY_TEMPLATE


_CSS = f"""
<style>
/* ---- layout tightening ---------------------------------------------- */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; }}

/* ---- hero band -------------------------------------------------------- */
.agl-hero {{
    background: linear-gradient(120deg, #151b34 0%, #1a2140 45%, #14263a 100%);
    border: 1px solid {COLOR["border"]};
    border-radius: 16px;
    padding: 1.4rem 1.6rem 1.2rem;
    margin-bottom: 1.1rem;
    animation: agl-fade 0.5s ease-out;
}}
.agl-hero h1 {{
    font-size: 1.65rem; margin: 0 0 0.15rem; padding: 0;
    color: {COLOR["text"]}; letter-spacing: -0.01em;
}}
.agl-hero .agl-sub {{ color: {COLOR["text_dim"]}; font-size: 0.95rem; margin: 0; }}
.agl-hero .agl-chips {{ margin-top: 0.7rem; display: flex; gap: 0.45rem; flex-wrap: wrap; }}

/* ---- chips / badges --------------------------------------------------- */
.agl-chip {{
    display: inline-flex; align-items: center; gap: 0.3rem;
    font-size: 0.74rem; font-weight: 600; letter-spacing: 0.02em;
    padding: 0.18rem 0.6rem; border-radius: 999px;
    border: 1px solid {COLOR["border"]};
    background: rgba(124, 140, 248, 0.08); color: {COLOR["text_dim"]};
    white-space: nowrap;
}}
.agl-chip.ok     {{ color: {COLOR["ok"]};     border-color: rgba(91,198,137,0.35);  background: rgba(91,198,137,0.08); }}
.agl-chip.warn   {{ color: {COLOR["warn"]};   border-color: rgba(242,178,92,0.35);  background: rgba(242,178,92,0.08); }}
.agl-chip.danger {{ color: {COLOR["danger"]}; border-color: rgba(229,104,92,0.35);  background: rgba(229,104,92,0.08); }}
.agl-chip.ai     {{ color: {COLOR["accent"]}; border-color: rgba(78,216,199,0.35);  background: rgba(78,216,199,0.08); }}

/* ---- KPI cards -------------------------------------------------------- */
.agl-kpi {{
    background: {COLOR["bg2"]};
    border: 1px solid {COLOR["border"]};
    border-radius: 14px;
    padding: 0.85rem 1rem 0.8rem;
    height: 100%;
    transition: transform 0.15s ease, border-color 0.15s ease;
    animation: agl-fade 0.5s ease-out;
}}
.agl-kpi:hover {{ transform: translateY(-2px); border-color: {COLOR["primary"]}55; }}
.agl-kpi .label {{
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: {COLOR["text_dim"]}; margin-bottom: 0.25rem;
}}
.agl-kpi .value {{
    font-size: 1.55rem; font-weight: 700; color: {COLOR["text"]};
    line-height: 1.15; letter-spacing: -0.01em;
}}
.agl-kpi .delta {{ font-size: 0.78rem; margin-top: 0.2rem; color: {COLOR["text_dim"]}; }}
.agl-kpi .delta.ok {{ color: {COLOR["ok"]}; }}
.agl-kpi .delta.warn {{ color: {COLOR["warn"]}; }}
.agl-kpi .delta.danger {{ color: {COLOR["danger"]}; }}

/* ---- anomaly / link cards -------------------------------------------- */
.agl-callout {{
    border-left: 3px solid {COLOR["warn"]};
    background: {COLOR["bg2"]};
    border-radius: 0 12px 12px 0;
    padding: 0.7rem 0.9rem;
    margin-bottom: 0.6rem;
}}
.agl-callout .t {{ font-weight: 600; color: {COLOR["text"]}; font-size: 0.92rem; }}
.agl-callout .d {{ color: {COLOR["text_dim"]}; font-size: 0.84rem; margin-top: 0.15rem; }}

/* ---- bordered containers get a subtle lift ---------------------------- */
div[data-testid="stVerticalBlockBorderWrapper"] {{
    transition: border-color 0.15s ease;
}}

/* ---- page header ------------------------------------------------------ */
.agl-page-title {{ display: flex; align-items: baseline; gap: 0.7rem; flex-wrap: wrap; }}
.agl-page-title h2 {{ margin: 0; padding: 0; font-size: 1.45rem; letter-spacing: -0.01em; }}
.agl-page-title .sub {{ color: {COLOR["text_dim"]}; font-size: 0.9rem; }}

@keyframes agl-fade {{
    from {{ opacity: 0; transform: translateY(4px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
