"""Data-source registry: demo / CSV / Jira all produce the same AgileData
bundle and flow through one activation path.

Session-state contract (initialised by init_session_state, read everywhere):
    source_kind     "demo" | "csv" | "jira"
    agile_data      AgileData
    source_meta     {name, project_name, today: date, blurb, anomalies, loaded_at}
    data_version    int nonce — bumped on every successful source switch
    copilot_history API-shaped message list
    copilot_pending question handed off from another page's pills
    insight_cache   {(page, data_version): (text, source)}
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from src.data_loader import AgileData
from src.datasource.schema import validate_agile_data


def init_session_state() -> None:
    ss = st.session_state
    if "data_version" not in ss:
        ss["data_version"] = 0
        ss["copilot_history"] = []
        ss["copilot_pending"] = None
        ss["insight_cache"] = {}
    if "agile_data" not in ss:
        from src.datasource.demo import load_demo

        data, meta = load_demo()
        ss["agile_data"] = data
        ss["source_meta"] = meta
        ss["source_kind"] = "demo"


def set_active_data(data: AgileData, meta: dict, kind: str) -> list[str]:
    """Validate and activate a dataset. Returns warnings (raises on errors)."""
    errors, warnings = validate_agile_data(data)
    if errors:
        raise ValueError("; ".join(errors))
    ss = st.session_state
    meta.setdefault("today", date.today())
    meta.setdefault("loaded_at", datetime.now().isoformat(timespec="seconds"))
    ss["agile_data"] = data
    ss["source_meta"] = meta
    ss["source_kind"] = kind
    ss["data_version"] += 1
    ss["copilot_history"] = []
    return warnings


def reset_to_demo() -> None:
    from src.datasource.demo import load_demo

    data, meta = load_demo()
    set_active_data(data, meta, "demo")


def get_active() -> tuple[AgileData, dict]:
    ss = st.session_state
    return ss["agile_data"], ss["source_meta"]
