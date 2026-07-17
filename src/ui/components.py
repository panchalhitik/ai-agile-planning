"""Reusable UI building blocks. All of them read the session-state contract
set up in app.py: agile_data, source_meta, source_kind, data_version."""

from __future__ import annotations

import html
import re

import streamlit as st

from src.ai.client import ai_available
from src.ai.insights import generate_insight
from src.ui.theme import COLOR


def _md_bold_to_html(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


# ---------------------------------------------------------------------------
# Badges / chips
# ---------------------------------------------------------------------------
def chip(label: str, tone: str = "") -> str:
    return f'<span class="agl-chip {tone}">{html.escape(label)}</span>'


def ai_mode_chip() -> str:
    if ai_available():
        return chip("✦ Claude connected", "ai")
    return chip("⚙ rules mode — add ANTHROPIC_API_KEY for Claude", "")


def source_chip() -> str:
    meta = st.session_state["source_meta"]
    kind = st.session_state["source_kind"]
    labels = {"demo": "demo data", "csv": "uploaded CSV", "jira": "Jira"}
    return chip(f"⛁ {meta['name']} · {labels.get(kind, kind)}", "")


# ---------------------------------------------------------------------------
# Page scaffolding
# ---------------------------------------------------------------------------
def page_header(title: str, subtitle: str = "") -> None:
    sub = f'<span class="sub">{html.escape(subtitle)}</span>' if subtitle else ""
    st.markdown(
        f'<div class="agl-page-title"><h2>{html.escape(title)}</h2>{sub}</div>'
        f'<div style="margin:0.35rem 0 1rem; display:flex; gap:0.4rem; flex-wrap:wrap;">'
        f"{source_chip()}{ai_mode_chip()}</div>",
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, chips_html: list[str]) -> None:
    st.markdown(
        f'<div class="agl-hero"><h1>{html.escape(title)}</h1>'
        f'<p class="agl-sub">{html.escape(subtitle)}</p>'
        f'<div class="agl-chips">{"".join(chips_html)}</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
def kpi_row(cards: list[dict]) -> None:
    """cards: [{label, value, delta?, tone?}] — tone in ok/warn/danger/''."""
    cols = st.columns(len(cards))
    for col, card in zip(cols, cards):
        delta = card.get("delta", "")
        tone = card.get("tone", "")
        delta_html = f'<div class="delta {tone}">{_md_bold_to_html(delta)}</div>' if delta else ""
        col.markdown(
            f'<div class="agl-kpi"><div class="label">{html.escape(card["label"])}</div>'
            f'<div class="value">{html.escape(str(card["value"]))}</div>{delta_html}</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# AI insight card (cached per page + data_version)
# ---------------------------------------------------------------------------
def insight_card(page: str) -> None:
    ss = st.session_state
    cache: dict = ss.setdefault("insight_cache", {})
    key = (page, ss["data_version"])

    with st.container(border=True):
        head, refresh = st.columns([6, 1])
        if refresh.button("↻", key=f"insight-refresh-{page}", help="Regenerate this insight"):
            cache.pop(key, None)
        if key not in cache:
            with st.spinner("Reading the data…"):
                cache[key] = generate_insight(
                    page,
                    ss["agile_data"],
                    ss["source_meta"]["project_name"],
                    ss["source_meta"]["today"],
                )
        text, source = cache[key]
        badge = (
            chip("✦ AI insight", "ai") if source == "anthropic" else chip("⚙ rules insight", "")
        )
        head.markdown(badge, unsafe_allow_html=True)
        st.markdown(text)


# ---------------------------------------------------------------------------
# Anomaly callouts (demo narrative -> deep links)
# ---------------------------------------------------------------------------
def anomaly_callouts(pages_by_id: dict[str, str]) -> None:
    """Render 'worth a look' cards deep-linking to the page that shows each
    seeded anomaly. pages_by_id maps anomaly id -> st.Page path/label."""
    meta = st.session_state["source_meta"]
    anomalies = meta.get("anomalies") or []
    if not anomalies:
        return
    st.markdown("##### Worth a look")
    cols = st.columns(len(anomalies))
    for col, anomaly in zip(cols, anomalies):
        with col:
            st.markdown(
                f'<div class="agl-callout"><div class="t">{html.escape(anomaly["title"])}</div>'
                f'<div class="d">{html.escape(anomaly["detail"])}</div></div>',
                unsafe_allow_html=True,
            )
            target = pages_by_id.get(anomaly["id"])
            if target:
                st.page_link(target, label="Open →")


def utilisation_tone(pct: float) -> str:
    if pct > 110:
        return "danger"
    if pct > 90:
        return "warn"
    return "ok"


def risk_color(band: str) -> str:
    from src.ui.theme import BAND_COLOR

    return BAND_COLOR.get(band, COLOR["muted"])
