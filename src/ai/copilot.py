"""The AI copilot: Claude tool-use grounded in the analytics layer.

The model never computes numbers itself — every figure comes from a tool
backed by the pure-pandas functions in `src.analytics`. When no API key is
configured (or any API call fails), a deterministic keyword router answers
using the *same* tool functions, so the chat always works.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from src import analytics
from src.data_loader import AgileData

MAX_TOOL_ITERATIONS = 6
MAX_HISTORY_MESSAGES = 16  # ~8 turns


def _dump(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _records(df) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


# ---------------------------------------------------------------------------
# Tools: thin JSON wrappers over the analytics layer
# ---------------------------------------------------------------------------
def build_tools(
    data: AgileData, today: date
) -> tuple[list[dict], dict[str, Callable[..., Any]]]:
    """Anthropic tool schemas plus a name -> callable dispatch table."""

    def get_headline_kpis() -> dict:
        return analytics.headline_kpis(data.issues, data.sprints)

    def get_sprint_metrics(sprint_id: str | None = None) -> Any:
        sm = analytics.sprint_metrics(data.issues, data.sprints)
        if sprint_id:
            sm = sm[sm["sprint_id"] == sprint_id]
            if sm.empty:
                return {"error": f"Unknown sprint_id {sprint_id!r}"}
        return _records(sm)

    def get_sprint_health() -> dict:
        return analytics.sprint_health(data.issues, data.sprints, today)

    def get_velocity(window: int = 3) -> dict:
        sm = analytics.sprint_metrics(data.issues, data.sprints)
        return {"window": window, "velocity": analytics.velocity(sm, window=window)}

    def get_capacity_vs_load(sprint_id: str | None = None) -> Any:
        sid = sprint_id or analytics.current_sprint_id(data.sprints, today)
        cap = analytics.capacity_vs_load(data.issues, data.team, sid)
        return {"sprint_id": sid, "members": _records(cap)}

    def get_epic_progress(epic_id: str | None = None) -> Any:
        ep = analytics.epic_progress(data.issues, data.epics)
        if epic_id:
            ep = ep[ep["epic_id"] == epic_id]
            if ep.empty:
                return {"error": f"Unknown epic_id {epic_id!r}"}
        return _records(ep)

    def get_delivery_risk() -> Any:
        return _records(analytics.delivery_risk(data.issues, data.epics))

    def get_blockers() -> Any:
        deps = analytics.dependency_edges(data.issues)
        return {
            "hotspots": _records(analytics.blocker_hotspots(data.issues)),
            "total_dependency_edges": int(len(deps)),
        }

    def get_forecast(
        scope_delta_pct: float = 0.0, capacity_delta_pct: float = 0.0
    ) -> dict:
        return analytics.monte_carlo_forecast(
            data.issues,
            data.sprints,
            today,
            scope_delta_pct=scope_delta_pct,
            capacity_delta_pct=capacity_delta_pct,
        )

    def list_issues(
        sprint_id: str | None = None,
        epic_id: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
        limit: int = 25,
    ) -> dict:
        df = data.issues
        if sprint_id:
            df = df[df["sprint_id"] == sprint_id]
        if epic_id:
            df = df[df["epic_id"] == epic_id]
        if assignee:
            df = df[df["assignee"].str.contains(assignee, case=False, na=False)]
        if status:
            df = df[df["status"].str.lower() == status.lower()]
        limit = max(1, min(int(limit), 50))
        cols = [
            "issue_key", "summary", "issue_type", "epic_id", "sprint_id",
            "story_points", "status", "assignee", "priority", "blocked_by",
        ]
        return {
            "total_matches": int(len(df)),
            "returned": int(min(len(df), limit)),
            "issues": _records(df[cols].head(limit)),
        }

    dispatch: dict[str, Callable[..., Any]] = {
        "get_headline_kpis": get_headline_kpis,
        "get_sprint_metrics": get_sprint_metrics,
        "get_sprint_health": get_sprint_health,
        "get_velocity": get_velocity,
        "get_capacity_vs_load": get_capacity_vs_load,
        "get_epic_progress": get_epic_progress,
        "get_delivery_risk": get_delivery_risk,
        "get_blockers": get_blockers,
        "get_forecast": get_forecast,
        "list_issues": list_issues,
    }

    no_args = {"type": "object", "properties": {}}
    schemas = [
        {
            "name": "get_headline_kpis",
            "description": "Portfolio totals: issues, points, done, blocked, rolling velocity.",
            "input_schema": no_args,
        },
        {
            "name": "get_sprint_metrics",
            "description": "Per-sprint committed/completed/blocked points, completion % and over-commit %. Optionally one sprint.",
            "input_schema": {
                "type": "object",
                "properties": {"sprint_id": {"type": "string", "description": "e.g. 'S09'"}},
            },
        },
        {
            "name": "get_sprint_health",
            "description": "The current sprint: days elapsed/remaining, time vs work progress, on-track flag.",
            "input_schema": no_args,
        },
        {
            "name": "get_velocity",
            "description": "Rolling average of completed points over the last N finished sprints.",
            "input_schema": {
                "type": "object",
                "properties": {"window": {"type": "integer", "default": 3}},
            },
        },
        {
            "name": "get_capacity_vs_load",
            "description": "Per-person assigned points vs capacity and utilisation % for a sprint (defaults to the current one). Use for overload questions.",
            "input_schema": {
                "type": "object",
                "properties": {"sprint_id": {"type": "string"}},
            },
        },
        {
            "name": "get_epic_progress",
            "description": "Per-epic total/done/blocked points and progress %. Optionally one epic.",
            "input_schema": {
                "type": "object",
                "properties": {"epic_id": {"type": "string", "description": "e.g. 'EPIC-101'"}},
            },
        },
        {
            "name": "get_delivery_risk",
            "description": "Explainable delivery-risk score (0-100) and band per epic, with driver explanations.",
            "input_schema": no_args,
        },
        {
            "name": "get_blockers",
            "description": "Blocker hotspots: which issues block the most other issues.",
            "input_schema": no_args,
        },
        {
            "name": "get_forecast",
            "description": "Monte Carlo forecast of sprints needed to finish the remaining backlog, with p50/p70/p85/p95 finish dates. Supports what-if deltas.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "scope_delta_pct": {"type": "number", "description": "Grow/shrink remaining scope by this percent."},
                    "capacity_delta_pct": {"type": "number", "description": "Scale velocity by this percent (proxy for team change)."},
                },
            },
        },
        {
            "name": "list_issues",
            "description": "List issues filtered by sprint, epic, assignee, and/or status. Returns at most 50 with a total count.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sprint_id": {"type": "string"},
                    "epic_id": {"type": "string"},
                    "assignee": {"type": "string", "description": "Substring match on the assignee name."},
                    "status": {"type": "string", "enum": ["Done", "In Progress", "To Do", "Blocked"]},
                    "limit": {"type": "integer", "default": 25, "maximum": 50},
                },
            },
        },
    ]
    return schemas, dispatch


# ---------------------------------------------------------------------------
# System prompt with a compact data dictionary
# ---------------------------------------------------------------------------
def system_prompt(data: AgileData, project_name: str, today: date) -> str:
    sprints = "; ".join(
        f"{r.sprint_id}={r.sprint_name} ({r.start_date}..{r.end_date})"
        for r in data.sprints.itertuples()
    )
    epics = "; ".join(
        f"{r.epic_id}={r.epic_name} [{r.priority}]" for r in data.epics.itertuples()
    )
    team = "; ".join(
        f"{r.member} ({r.role}, cap {r.capacity_per_sprint})"
        for r in data.team.itertuples()
    )
    current = analytics.current_sprint_id(data.sprints, today)
    return (
        "You are the delivery copilot for an agile engineering team's sprint "
        "dashboard. You answer planning questions: sprint health, velocity, "
        "capacity and overload, epic progress, delivery risk, blockers, and "
        "completion forecasts.\n\n"
        "HARD RULES:\n"
        "- Always compute numbers by calling tools. Never estimate, recall, or "
        "invent numbers, issue keys, names, or counts.\n"
        "- If tools cannot answer the question, say so plainly.\n"
        "- Be concise: short paragraphs or tight bullet lists, bold the key "
        "numbers, and finish with one actionable takeaway when relevant.\n"
        "- When a tool returns 'total_matches' larger than 'returned', say the "
        "list is truncated.\n\n"
        f"DATA DICTIONARY (for entity resolution only — fetch numbers via tools):\n"
        f"Project: {project_name}. Today: {today.isoformat()}. "
        f"Current sprint: {current}.\n"
        f"Sprints: {sprints}\n"
        f"Epics: {epics}\n"
        f"Team: {team}\n"
        f"Issue statuses: Done, In Progress, To Do, Blocked."
    )


# ---------------------------------------------------------------------------
# Manual tool-use loop
# ---------------------------------------------------------------------------
@dataclass
class TurnResult:
    text: str
    source: str  # "anthropic" | "fallback"
    tool_calls: list[str]
    history: list[dict]


def run_anthropic_turn(
    client,
    model: str,
    system: str,
    tools: list[dict],
    dispatch: dict[str, Callable[..., Any]],
    history: list[dict],
    on_tool: Callable[[str, dict], None] | None = None,
) -> TurnResult:
    """One user turn: loop create() -> execute tool_use blocks -> repeat.

    `history` must already end with the user's message. Returns the final
    text plus the updated (API-shaped) history.
    """
    tool_calls: list[str] = []
    for _ in range(MAX_TOOL_ITERATIONS):
        resp = client.messages.create(
            model=model,
            max_tokens=1200,
            system=system,
            tools=tools,
            messages=history,
        )
        blocks = [
            b.model_dump() if hasattr(b, "model_dump") else dict(b)
            for b in resp.content
        ]
        history.append({"role": "assistant", "content": blocks})

        if resp.stop_reason != "tool_use":
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return TurnResult(text.strip(), "anthropic", tool_calls, history)

        results = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            name, args = block["name"], block.get("input") or {}
            tool_calls.append(name)
            if on_tool:
                on_tool(name, args)
            try:
                output = dispatch[name](**args)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": _dump(output),
                    }
                )
            except Exception as exc:  # noqa: BLE001 — surfaced to the model
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": f"Tool error: {exc}",
                        "is_error": True,
                    }
                )
        history.append({"role": "user", "content": results})

    text = (
        "I hit the tool-call limit for a single question — try asking a more "
        "specific question."
    )
    history.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
    return TurnResult(text, "anthropic", tool_calls, history)


# ---------------------------------------------------------------------------
# Deterministic fallback router (no API key / API failure)
# ---------------------------------------------------------------------------
def fallback_answer(question: str, data: AgileData, today: date) -> tuple[str, list[str]]:
    """Keyword-routed answer built from the same tool functions."""
    _, dispatch = build_tools(data, today)
    q = question.lower()

    def fmt_pct(v: float) -> str:
        return f"{v:.0f}%"

    if any(w in q for w in ("overload", "capacity", "utilis", "utiliz", "workload", "who is over")):
        result = dispatch["get_capacity_vs_load"]()
        rows = sorted(result["members"], key=lambda m: -m["utilisation_pct"])
        lines = [f"**Capacity in {result['sprint_id']}** (assigned vs capacity):", ""]
        for m in rows:
            flag = " ⚠️ overloaded" if m["utilisation_pct"] > 110 else ""
            lines.append(
                f"- {m['member']}: **{m['assigned_points']} pts** of "
                f"{m['capacity_per_sprint']} ({fmt_pct(m['utilisation_pct'])}){flag}"
            )
        worst = rows[0]
        if worst["utilisation_pct"] > 110:
            lines += ["", f"**Takeaway:** rebalance work away from {worst['member']} first."]
        return "\n".join(lines), ["get_capacity_vs_load"]

    if any(w in q for w in ("block", "depend", "stuck", "hotspot")):
        result = dispatch["get_blockers"]()
        hot = result["hotspots"]
        if not hot:
            return "No active blockers in the data. 🎉", ["get_blockers"]
        lines = ["**Top blocker hotspots:**", ""]
        for h in hot[:5]:
            lines.append(
                f"- `{h['blocker']}` ({h.get('status', '?')}) blocks "
                f"**{h['blocks_count']}** issue(s) — {h.get('summary', '')}"
            )
        lines += ["", f"**Takeaway:** unblock `{hot[0]['blocker']}` first; it has the widest impact."]
        return "\n".join(lines), ["get_blockers"]

    if any(w in q for w in ("risk", "danger", "trouble", "late epic", "at risk")):
        risks = dispatch["get_delivery_risk"]()
        risks = sorted(risks, key=lambda r: -r["score"])
        lines = ["**Delivery risk by epic** (0 safe → 100 critical):", ""]
        for r in risks:
            drivers = r["drivers"] if isinstance(r["drivers"], list) else [str(r["drivers"])]
            lines.append(f"- {r['epic_id']}: **{r['score']:.0f} ({r['band']})** — {'; '.join(drivers[:2])}")
        top = risks[0]
        lines += ["", f"**Takeaway:** focus mitigation on {top['epic_id']} ({top['band']})."]
        return "\n".join(lines), ["get_delivery_risk"]

    if any(w in q for w in ("forecast", "when", "finish", "eta", "how long", "done by", "complete by")):
        fc = dispatch["get_forecast"]()
        if not fc.get("ok"):
            return f"Can't forecast yet: {fc.get('reason')}", ["get_forecast"]
        p = fc["percentiles"]
        lines = [
            f"**Completion forecast** for the remaining **{fc['remaining_points']:.0f} pts** "
            f"(Monte Carlo over historical velocity, mean {fc['velocity_mean']} pts/sprint):",
            "",
            f"- 50% confidence: **{p['p50']['sprints']} sprints** (~{p['p50']['finish_date']})",
            f"- 85% confidence: **{p['p85']['sprints']} sprints** (~{p['p85']['finish_date']})",
            f"- 95% confidence: **{p['p95']['sprints']} sprints** (~{p['p95']['finish_date']})",
            "",
            "**Takeaway:** plan external commitments on the 85% date, not the 50% one.",
        ]
        return "\n".join(lines), ["get_forecast"]

    if any(w in q for w in ("velocity", "trend", "throughput")):
        vel = dispatch["get_velocity"]()
        sm = dispatch["get_sprint_metrics"]()
        recent = sm[-4:]
        lines = [f"**Rolling velocity ({vel['window']} sprints): {vel['velocity']} pts.**", ""]
        for r in recent:
            lines.append(
                f"- {r['sprint_name']}: committed {r['committed_points']}, "
                f"completed **{r['completed_points']}** ({r['completion_pct']}%)"
            )
        lines += ["", "**Takeaway:** commit next sprint to roughly the rolling velocity."]
        return "\n".join(lines), ["get_velocity", "get_sprint_metrics"]

    if any(w in q for w in ("epic", "progress", "initiative")):
        eps = dispatch["get_epic_progress"]()
        lines = ["**Epic progress:**", ""]
        for e in sorted(eps, key=lambda e: e["progress_pct"]):
            lines.append(
                f"- {e['epic_name']}: **{e['progress_pct']:.0f}%** done "
                f"({e['done_points']}/{e['total_points']} pts, {e['blocked_points']} blocked)"
            )
        return "\n".join(lines), ["get_epic_progress"]

    if any(w in q for w in ("sprint", "current", "today", "health", "status", "how are we")):
        h = dispatch["get_sprint_health"]()
        state = "on track" if h["on_track"] else "**behind the clock**"
        lines = [
            f"**{h['sprint_name']}** — day {h['days_elapsed']} of {h['days_total']} "
            f"({h['days_remaining']} days left).",
            "",
            f"- Committed **{h['committed_points']} pts**, completed "
            f"**{h['completed_points']}** ({h['completion_pct']}%), "
            f"{h['blocked_points']} blocked.",
            f"- Time elapsed {h['time_pct']}% vs work done {h['completion_pct']}% → {state}.",
        ]
        return "\n".join(lines), ["get_sprint_health"]

    # Default: capabilities + headline numbers.
    k = dispatch["get_headline_kpis"]()
    lines = [
        "I can answer questions about **sprint health**, **velocity**, "
        "**capacity/overload**, **epic progress**, **delivery risk**, "
        "**blockers**, and **completion forecasts**.",
        "",
        f"Right now: **{k['total_issues']} issues / {k['total_points']} pts** in the "
        f"dataset, **{k['done_points']} pts done**, **{k['blocked_points']} blocked**, "
        f"rolling velocity **{k['velocity_3']} pts**.",
        "",
        "_Try: “Who is overloaded this sprint?” or “When will we finish the backlog?”_",
    ]
    return "\n".join(lines), ["get_headline_kpis"]


# ---------------------------------------------------------------------------
# Entry point used by the UI
# ---------------------------------------------------------------------------
def answer(
    question: str,
    history: list[dict],
    data: AgileData,
    project_name: str,
    today: date,
    on_tool: Callable[[str, dict], None] | None = None,
) -> TurnResult:
    """Answer one question, preferring Claude, falling back to rules.

    `history` is the API-shaped message list (without the new question);
    the returned TurnResult carries the updated history.
    """
    from src.ai.client import get_client, get_model

    history = history[-MAX_HISTORY_MESSAGES:]
    # History slices must start at a plain user text message, never a
    # dangling tool_result.
    while history and not _starts_clean(history[0]):
        history.pop(0)
    history.append({"role": "user", "content": [{"type": "text", "text": question}]})

    client = get_client()
    if client is not None:
        tools, dispatch = build_tools(data, today)
        system = system_prompt(data, project_name, today)
        try:
            return run_anthropic_turn(
                client, get_model(), system, tools, dispatch, history, on_tool
            )
        except Exception:  # noqa: BLE001 — any API failure degrades to rules
            pass

    text, calls = fallback_answer(question, data, today)
    for name in calls:
        if on_tool:
            on_tool(name, {})
    history.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
    return TurnResult(text, "fallback", calls, history)


def _starts_clean(message: dict) -> bool:
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    return all(b.get("type") == "text" for b in content)
