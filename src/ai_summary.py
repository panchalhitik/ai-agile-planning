"""AI-assisted summaries for sprint, backlog, and leadership audiences.

If an ANTHROPIC_API_KEY is configured (env var or Streamlit secrets), summaries
are produced by Claude via the Anthropic SDK with a curated system prompt.
Otherwise the module falls back to a deterministic, rules-based template so
the dashboard always renders something useful - good for demos and CI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

import pandas as pd

Audience = Literal["sprint", "backlog", "leadership"]

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPTS: dict[Audience, str] = {
    "sprint": (
        "You are an experienced Agile delivery lead. Given sprint metrics, "
        "write a concise (max 6 bullet points) sprint review covering: "
        "completion vs commit, top blockers, capacity issues, and one concrete "
        "action for the next sprint. Be specific about numbers; do not invent data."
    ),
    "backlog": (
        "You are a senior product manager. Given epic progress and risk data, "
        "produce a backlog-refinement note. Identify (a) epics that need scope "
        "cut, (b) epics that should be promoted, and (c) candidate stories to "
        "groom next. Keep it under 8 bullets. Do not invent data."
    ),
    "leadership": (
        "You are a director-level engineering leader briefing executives. "
        "Summarise delivery health in 4-6 short paragraphs: portfolio status, "
        "top 3 delivery risks with mitigations, capacity outlook, and a "
        "recommendation. Use plain business language - no Jira jargon."
    ),
}


@dataclass
class SummaryResult:
    text: str
    source: Literal["anthropic", "fallback"]
    model: str | None = None


def _get_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("ANTHROPIC_API_KEY") or None
    except Exception:
        return None


def _build_user_prompt(audience: Audience, payload: dict) -> str:
    return (
        f"Audience: {audience}\n"
        "Below is structured sprint / epic data as JSON. "
        "Use ONLY these numbers - do not invent issues, names, or counts.\n\n"
        f"```json\n{json.dumps(payload, default=str, indent=2)}\n```"
    )


def _anthropic_summary(audience: Audience, payload: dict) -> SummaryResult | None:
    key = _get_api_key()
    if not key:
        return None
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
        resp = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=900,
            system=SYSTEM_PROMPTS[audience],
            messages=[{"role": "user", "content": _build_user_prompt(audience, payload)}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return SummaryResult(text=text.strip(), source="anthropic", model=DEFAULT_MODEL)
    except Exception as exc:  # pragma: no cover - network/credential errors
        return SummaryResult(
            text=f"_Anthropic call failed ({exc.__class__.__name__}); using fallback summary._\n\n"
            + _fallback_summary(audience, payload),
            source="fallback",
        )


def _fallback_summary(audience: Audience, payload: dict) -> str:
    """Deterministic, rules-based summary so the app always renders."""
    kpi = payload.get("kpis", {})
    sprint_rows = payload.get("sprint_metrics", [])
    risks = payload.get("epic_risks", [])
    blockers = payload.get("blockers", [])

    if audience == "sprint":
        latest = sprint_rows[-1] if sprint_rows else {}
        lines = [
            f"- **{latest.get('sprint_name', 'Latest sprint')}** committed "
            f"{latest.get('committed_points', 0)} pts, completed "
            f"{latest.get('completed_points', 0)} pts "
            f"({latest.get('completion_pct', 0)}%).",
            f"- Capacity was {latest.get('capacity_points', 0)} pts; "
            f"over-commit was {latest.get('over_commit_pct', 0)}%.",
            f"- {latest.get('blocked_points', 0)} pts were blocked at end of sprint.",
            f"- 3-sprint rolling velocity: **{kpi.get('velocity_3', 0)} pts**.",
        ]
        if blockers:
            top = blockers[0]
            lines.append(
                f"- Top blocker: `{top.get('blocker')}` is blocking "
                f"{top.get('blocks_count')} other issues."
            )
        lines.append("- **Action:** trim next-sprint commit to the rolling velocity and unblock the top hotspot first.")
        return "\n".join(lines)

    if audience == "backlog":
        cuts = [r for r in risks if r.get("band") in ("High", "Critical")]
        promote = [r for r in risks if r.get("band") == "Low" and r.get("score", 0) < 10]
        lines = ["**Backlog refinement notes**", ""]
        if cuts:
            lines.append("**Cut or de-scope:**")
            for r in cuts[:3]:
                drivers = "; ".join(r.get("drivers", [])[:2])
                lines.append(f"- `{r['epic_id']}` (risk {r['score']}, {r['band']}): {drivers}")
        if promote:
            lines.append("")
            lines.append("**Safe to promote / accelerate:**")
            for r in promote[:3]:
                lines.append(f"- `{r['epic_id']}` (risk {r['score']})")
        lines += [
            "",
            "**Suggested groom-next stories:** any `To Do` issues attached to "
            "the high-risk epics above - estimate, split if > 8 pts, and confirm "
            "acceptance criteria before next planning.",
        ]
        return "\n".join(lines)

    # leadership
    total = kpi.get("total_points", 0)
    done = kpi.get("done_points", 0)
    blocked = kpi.get("blocked_points", 0)
    pct_done = (done / total * 100) if total else 0
    critical = [r for r in risks if r.get("band") in ("High", "Critical")][:3]

    paras = [
        f"**Portfolio status** - {pct_done:.0f}% of committed scope is delivered "
        f"across {len(payload.get('sprint_metrics', []))} sprints "
        f"({done} of {total} pts). Rolling velocity is "
        f"{kpi.get('velocity_3', 0)} pts/sprint.",
        f"**Risk** - {blocked} pts are currently blocked. "
        + (
            "Top exposures: "
            + "; ".join(f"{r['epic_id']} ({r['band']})" for r in critical)
            if critical
            else "No epics in the High/Critical band."
        ),
        "**Capacity outlook** - planned commits track within +/-10% of capacity; "
        "no team is structurally over-allocated, though next sprint should "
        "absorb carry-over before adding new scope.",
        "**Recommendation** - hold commit to rolling velocity, focus the next "
        "sprint on unblocking the highest-risk epic, and re-baseline scope on "
        "any epic in the Critical band.",
    ]
    return "\n\n".join(paras)


def summarise(audience: Audience, payload: dict) -> SummaryResult:
    result = _anthropic_summary(audience, payload)
    if result is not None:
        return result
    return SummaryResult(text=_fallback_summary(audience, payload), source="fallback")


def build_payload(
    kpis: dict,
    sprint_metrics_df: pd.DataFrame,
    epic_risks_df: pd.DataFrame,
    blocker_df: pd.DataFrame,
) -> dict:
    return {
        "kpis": kpis,
        "sprint_metrics": sprint_metrics_df.assign(
            start_date=sprint_metrics_df["start_date"].astype(str),
            end_date=sprint_metrics_df["end_date"].astype(str),
        ).to_dict(orient="records"),
        "epic_risks": epic_risks_df.to_dict(orient="records"),
        "blockers": blocker_df.to_dict(orient="records"),
    }
