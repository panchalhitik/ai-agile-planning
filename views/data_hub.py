"""Data hub: switch between demo data, an uploaded CSV, and a live Jira
board. Every path funnels through the same validation + activation."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from src import analytics
from src.datasource import get_active, reset_to_demo, set_active_data
from src.datasource import csv_upload, demo as demo_src
from src.datasource.jira import JiraError, fetch_board_data, list_boards, test_connection
from src.datasource.schema import CANONICAL_STATUSES, normalize_status, validate_agile_data
from src.ui import components as ui

data, meta = get_active()
ss = st.session_state

ui.page_header("Data hub", "Bring your own data — or stay on the demo. Nothing leaves your machine.")

kind_labels = {"demo": "demo dataset", "csv": "uploaded CSV", "jira": "Jira board"}
banner_col, reset_col = st.columns([5, 1])
banner_col.info(
    f"**Active source:** {meta['name']} ({kind_labels.get(ss['source_kind'], '?')}) — "
    f"{len(data.issues)} issues across {len(data.sprints)} sprints.",
    icon="🗃️",
)
if ss["source_kind"] != "demo" and reset_col.button("Reset to demo"):
    reset_to_demo()
    st.rerun()

tab_demo, tab_csv, tab_jira, tab_export = st.tabs(
    ["🎬 Demo", "📄 CSV upload", "🔗 Jira Cloud", "📤 Export"]
)

# ---------------------------------------------------------------------------
# Demo tab
# ---------------------------------------------------------------------------
with tab_demo:
    st.markdown(
        "The demo dataset is a **story, not noise**: Nova Commerce, an "
        "e-commerce platform team of 8, nine sprints in — with realistic "
        "trouble deliberately seeded for the dashboard to find."
    )
    for anomaly in meta.get("anomalies", []) or demo_src.load_demo()[1]["anomalies"]:
        st.markdown(f"- **{anomaly['title']}** — {anomaly['detail']}")
    col1, col2 = st.columns(2)
    if col1.button("Use demo data", type="primary", disabled=ss["source_kind"] == "demo"):
        reset_to_demo()
        st.rerun()
    if col2.button("Regenerate demo data"):
        demo_src.regenerate_demo()
        reset_to_demo()
        st.toast("Demo data regenerated.")
        st.rerun()

# ---------------------------------------------------------------------------
# CSV tab — mapping wizard
# ---------------------------------------------------------------------------
with tab_csv:
    st.markdown(
        "Upload an **issues export** (Jira, Linear, or any tracker). Sprints, "
        "team, and epics are derived automatically; column names are guessed "
        "and can be corrected below."
    )
    uploaded = st.file_uploader("Issues CSV", type=["csv"], key="csv_file")

    if uploaded is not None:
        try:
            raw = pd.read_csv(uploaded)
        except Exception as exc:  # noqa: BLE001 — user-supplied file
            st.error(f"Could not read that CSV: {exc}")
            raw = None

        if raw is not None and raw.empty:
            st.error("That CSV has no rows.")
        elif raw is not None:
            st.caption(f"{len(raw)} rows · {len(raw.columns)} columns. First rows:")
            st.dataframe(raw.head(5), width="stretch", hide_index=True)

            # ---- column mapping -----------------------------------------
            st.markdown("##### 1 · Map columns")
            suggestion = csv_upload.suggest_mapping(list(raw.columns))
            options = ["(none)"] + list(raw.columns)
            mapping: dict[str, str | None] = {}
            fields = csv_upload.REQUIRED_TARGETS + csv_upload.OPTIONAL_TARGETS
            cols = st.columns(3)
            for i, field in enumerate(fields):
                required = field in csv_upload.REQUIRED_TARGETS
                guess = suggestion.get(field)
                label = f"{field}{' *' if required else ''}"
                with cols[i % 3]:
                    choice = st.selectbox(
                        label,
                        options,
                        index=options.index(guess) if guess in options else 0,
                        key=f"csvmap_{field}",
                    )
                mapping[field] = None if choice == "(none)" else choice

            missing = [f for f in csv_upload.REQUIRED_TARGETS if not mapping.get(f)]
            if missing:
                st.warning(f"Required fields not mapped yet: {', '.join(missing)}")
            else:
                issues = csv_upload.apply_mapping(raw, mapping)

                # ---- status mapping -------------------------------------
                source_statuses = sorted(
                    raw[mapping["status"]].astype(str).str.strip().unique()
                )
                unknown = [s for s in source_statuses if normalize_status(s) is None]
                status_map: dict[str, str] = {}
                if unknown:
                    st.markdown("##### 2 · Map unrecognised statuses")
                    mcols = st.columns(min(len(unknown), 4))
                    for i, value in enumerate(unknown):
                        with mcols[i % len(mcols)]:
                            status_map[value] = st.selectbox(
                                f"“{value}” →", CANONICAL_STATUSES, key=f"csvstatus_{value}"
                            )
                    raw_statuses = raw[mapping["status"]].astype(str).str.strip()
                    issues = issues.copy()
                    issues["status"] = [
                        status_map.get(s, normalize_status(s) or "To Do") for s in raw_statuses
                    ]

                # ---- validate + activate --------------------------------
                st.markdown("##### 3 · Validate & activate")
                candidate = csv_upload.build_agile_data(issues, today=date.today())
                errors, warnings = validate_agile_data(candidate)
                for e in errors:
                    st.error(e)
                for w in warnings:
                    st.warning(w)
                if not errors:
                    st.success(
                        f"Ready: {len(candidate.issues)} issues, "
                        f"{len(candidate.sprints)} sprints, {len(candidate.team)} people, "
                        f"{len(candidate.epics)} epics."
                    )
                    if st.button("Use this data", type="primary", key="csv_activate"):
                        set_active_data(
                            candidate,
                            {
                                "name": uploaded.name,
                                "project_name": uploaded.name.rsplit(".", 1)[0],
                                "blurb": f"Uploaded from {uploaded.name}.",
                                "anomalies": [],
                                "today": date.today(),
                            },
                            "csv",
                        )
                        st.toast(f"Now analysing {uploaded.name}")
                        st.switch_page("views/overview.py")

# ---------------------------------------------------------------------------
# Jira tab
# ---------------------------------------------------------------------------
with tab_jira:
    st.markdown(
        "Connect **read-only** to a Jira Cloud site with an "
        "[API token](https://id.atlassian.com/manage-profile/security/api-tokens). "
        "The token stays in this session's memory only — it is never written to disk."
    )
    col1, col2 = st.columns(2)
    site = col1.text_input("Site", placeholder="your-team.atlassian.net", key="jira_site")
    email = col2.text_input("Account email", placeholder="you@company.com", key="jira_email")
    token = st.text_input("API token", type="password", key="jira_token_input")

    if st.button("Test connection", disabled=not (site and email and token)):
        try:
            with st.spinner("Connecting…"):
                who = test_connection(site, email, token)
                boards = list_boards(site, email, token)
            ss["jira_boards"] = boards
            st.success(f"Connected as **{who}** — {len(boards)} board(s) visible.")
        except JiraError as exc:
            ss.pop("jira_boards", None)
            st.error(str(exc))

    boards = ss.get("jira_boards")
    if boards:
        board_label = st.selectbox(
            "Board", [f"{b['name']} (#{b['id']}, {b['type']})" for b in boards]
        )
        board = boards[[f"{b['name']} (#{b['id']}, {b['type']})" for b in boards].index(board_label)]
        if st.button("Fetch board data", type="primary"):
            try:
                with st.spinner("Pulling sprints and issues…"):
                    jira_data, jira_meta = fetch_board_data(
                        site, email, token, board["id"], board["name"]
                    )
                warnings = set_active_data(jira_data, jira_meta, "jira")
                for w in list(jira_meta.get("warnings", [])) + warnings:
                    st.warning(w)
                st.toast(f"Now analysing {board['name']}")
                st.switch_page("views/overview.py")
            except JiraError as exc:
                st.error(f"{exc} The current data source is unchanged.")
            except ValueError as exc:
                st.error(f"Fetched data failed validation: {exc}. Current source unchanged.")

# ---------------------------------------------------------------------------
# Export tab
# ---------------------------------------------------------------------------
with tab_export:
    st.markdown(
        "Flat CSVs of the **active dataset** — computed metrics included, "
        "ready for Tableau, Power BI, or a spreadsheet."
    )
    exports = {
        "issues.csv": data.issues,
        "sprint_metrics.csv": analytics.sprint_metrics(data.issues, data.sprints),
        "epic_progress.csv": analytics.epic_progress(data.issues, data.epics),
        "epic_risk.csv": analytics.delivery_risk(data.issues, data.epics),
        "dependencies.csv": analytics.dependency_edges(data.issues),
    }
    for name, df in exports.items():
        col1, col2 = st.columns([4, 1])
        col1.markdown(f"**{name}** — {len(df)} rows × {len(df.columns)} cols")
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        col2.download_button("Download", data=buf.getvalue(), file_name=name,
                             mime="text/csv", key=f"dl-{name}")
