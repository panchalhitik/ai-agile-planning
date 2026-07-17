"""Per-page AI insight cards: one compact Claude call per page per dataset,
with a deterministic fallback sentence assembled from the same dataframes."""

from __future__ import annotations

import json
from datetime import date

from src import analytics
from src.data_loader import AgileData
from src.ai.client import get_client, get_model

INSIGHT_SYSTEM = (
    "You are a delivery lead writing a 2-3 sentence 'what matters here' note "
    "for one dashboard page. Use ONLY the numbers in the JSON payload — never "
    "invent values. Bold the single most important number or name. No "
    "preamble, no headers; plain confident prose with one concrete "
    "recommendation."
)


def build_page_payload(page: str, data: AgileData, today: date) -> dict:
    sm = analytics.sprint_metrics(data.issues, data.sprints)
    payload: dict = {"page": page}
    if page == "overview":
        payload["kpis"] = analytics.headline_kpis(data.issues, data.sprints)
        payload["sprint_health"] = analytics.sprint_health(data.issues, data.sprints, today)
        payload["last_4_sprints"] = json.loads(
            sm.tail(4).to_json(orient="records", date_format="iso")
        )
    elif page == "sprint":
        payload["sprint_health"] = analytics.sprint_health(data.issues, data.sprints, today)
        sid = payload["sprint_health"]["sprint_id"]
        payload["capacity"] = json.loads(
            analytics.capacity_vs_load(data.issues, data.team, sid).to_json(orient="records")
        )
    elif page == "epics":
        payload["risk"] = json.loads(
            analytics.delivery_risk(data.issues, data.epics).to_json(orient="records")
        )
        payload["progress"] = json.loads(
            analytics.epic_progress(data.issues, data.epics).to_json(orient="records")
        )
    elif page == "dependencies":
        payload["hotspots"] = json.loads(
            analytics.blocker_hotspots(data.issues).to_json(orient="records")
        )
        payload["blocked_points"] = int(
            data.issues.loc[data.issues["status"] == "Blocked", "story_points"].sum()
        )
    elif page == "forecast":
        payload["forecast"] = analytics.monte_carlo_forecast(data.issues, data.sprints, today)
        payload["kpis"] = analytics.headline_kpis(data.issues, data.sprints)
    return payload


def deterministic_insight(page: str, data: AgileData, today: date) -> str:
    payload = build_page_payload(page, data, today)
    if page == "sprint":
        cap = sorted(payload["capacity"], key=lambda m: -m["utilisation_pct"])
        h = payload["sprint_health"]
        worst = cap[0]
        note = (
            f"**{worst['member']}** is at {worst['utilisation_pct']:.0f}% utilisation — "
            "rebalance before adding scope." if worst["utilisation_pct"] > 110
            else "No one is over capacity."
        )
        return (
            f"{h['sprint_name']} is {h['time_pct']:.0f}% through its timebox with "
            f"{h['completion_pct']:.0f}% of committed points done. {note}"
        )
    if page == "epics":
        risks = sorted(payload["risk"], key=lambda r: -r["score"])
        top = risks[0]
        drivers = top["drivers"] if isinstance(top["drivers"], list) else []
        return (
            f"**{top['epic_id']}** carries the highest delivery risk "
            f"({top['score']:.0f}, {top['band']})"
            + (f" — {drivers[0].lower()}" if drivers else "")
            + ". Review its scope before the next planning session."
        )
    if page == "dependencies":
        hot = payload["hotspots"]
        if not hot:
            return "No active blockers — the dependency graph is clean."
        top = hot[0]
        return (
            f"**{top['blocker']}** blocks {top['blocks_count']} other issues "
            f"({payload['blocked_points']} pts sit blocked overall). Unblocking it "
            "has the widest impact of any single action."
        )
    if page == "forecast":
        fc = payload["forecast"]
        if not fc.get("ok"):
            return f"Forecast unavailable: {fc.get('reason')}"
        p = fc["percentiles"]
        if p["p50"]["sprints"] == p["p85"]["sprints"]:
            return (
                f"The remaining **{fc['remaining_points']:.0f} pts** land in "
                f"{p['p85']['sprints']} sprints across most simulations — a tight "
                f"spread; only the p95 tail stretches to {p['p95']['sprints']}. "
                "Quote the p85 date externally."
            )
        return (
            f"The remaining **{fc['remaining_points']:.0f} pts** land in "
            f"{p['p50']['sprints']} sprints at 50% confidence but "
            f"{p['p85']['sprints']} at 85% — quote the later date externally."
        )
    # overview default
    k = analytics.headline_kpis(data.issues, data.sprints)
    h = analytics.sprint_health(data.issues, data.sprints, today)
    state = "on track" if h["on_track"] else "behind the clock"
    return (
        f"{h['sprint_name']} is {state}: {h['completion_pct']:.0f}% done with "
        f"{h['time_pct']:.0f}% of time gone, and **{k['blocked_points']} pts are "
        f"blocked** portfolio-wide. Clearing blockers is this week's highest-leverage move."
    )


def generate_insight(
    page: str, data: AgileData, project_name: str, today: date
) -> tuple[str, str]:
    """Returns (markdown, source) where source is 'anthropic' or 'rules'."""
    client = get_client()
    if client is None:
        return deterministic_insight(page, data, today), "rules"
    try:
        payload = build_page_payload(page, data, today)
        resp = client.messages.create(
            model=get_model(),
            max_tokens=300,
            system=INSIGHT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Project: {project_name}. Today: {today.isoformat()}.\n"
                        f"Page payload:\n```json\n{json.dumps(payload, default=str)}\n```"
                    ),
                }
            ],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text:
            return text, "anthropic"
    except Exception:  # noqa: BLE001 — degrade silently to rules
        pass
    return deterministic_insight(page, data, today), "rules"
