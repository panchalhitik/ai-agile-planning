"""The copilot chat surface, shared by the Copilot page (full) and the
Overview page (embedded)."""

from __future__ import annotations

import streamlit as st

from src.ai import copilot
from src.ai.client import ai_available
from src.datasource import get_active
from src.ui.components import chip

SUGGESTED = [
    "Who is overloaded this sprint?",
    "What's blocking us right now?",
    "Which epics are at risk?",
    "When will we finish the backlog?",
    "How's our velocity trending?",
]


def _pill_selected() -> None:
    ss = st.session_state
    if ss.get("copilot_pills"):
        ss["copilot_pending"] = ss["copilot_pills"]
        ss["copilot_pills"] = None


def _render_history() -> None:
    for msg in st.session_state["copilot_history"]:
        content = msg.get("content")
        if isinstance(content, str):
            blocks = [{"type": "text", "text": content}]
        else:
            blocks = content
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        if msg["role"] == "user":
            if not texts:  # pure tool_result round-trip — not a visible turn
                continue
            with st.chat_message("user"):
                st.markdown("\n\n".join(texts))
        else:
            with st.chat_message("assistant"):
                if tool_uses:
                    st.markdown(
                        " ".join(chip(f"⚙ {b['name']}", "ai") for b in tool_uses),
                        unsafe_allow_html=True,
                    )
                if texts:
                    st.markdown("\n\n".join(t for t in texts if t))


def render_copilot(embedded: bool = False) -> None:
    ss = st.session_state
    data, meta = get_active()

    if not embedded:
        left, right = st.columns([5, 1])
        with left:
            st.pills(
                "Suggested questions",
                SUGGESTED,
                key="copilot_pills",
                on_change=_pill_selected,
                label_visibility="collapsed",
            )
        with right:
            if st.button("Clear chat", disabled=not ss["copilot_history"]):
                ss["copilot_history"] = []
                st.rerun()

    _render_history()

    question = None
    if ss.get("copilot_pending"):
        question = ss["copilot_pending"]
        ss["copilot_pending"] = None

    placeholder = (
        "Ask about sprints, capacity, risk, blockers, forecasts…"
        if not embedded
        else "Ask the copilot…"
    )
    typed = st.chat_input(placeholder, key="copilot_input" if not embedded else "copilot_input_embedded")
    if typed:
        question = typed

    if not question:
        if not embedded and not ss["copilot_history"]:
            mode = (
                "Answers are written by Claude and grounded in tool calls."
                if ai_available()
                else "No API key configured — a deterministic rules engine answers "
                "using the same analytics tools."
            )
            st.caption(
                f"Every number comes from the tested analytics layer, never from "
                f"the model's memory. {mode}"
            )
        return

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.status("Consulting the analytics layer…", expanded=True) as status:
            def on_tool(name: str, args: dict) -> None:
                arg_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                st.write(f"→ `{name}({arg_str})`")

            result = copilot.answer(
                question,
                ss["copilot_history"],
                data,
                meta["project_name"],
                meta["today"],
                on_tool=on_tool,
            )
            label = (
                f"{'✦ Claude' if result.source == 'anthropic' else '⚙ rules mode'} · "
                f"{len(result.tool_calls)} tool call(s)"
            )
            status.update(label=label, state="complete", expanded=False)
        st.markdown(result.text)

    ss["copilot_history"] = result.history
