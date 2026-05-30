"""Sprint / epic / capacity / risk analytics.

All functions are pure - they accept the AgileData bundle (or dataframes)
and return new dataframes / dicts. This keeps the Streamlit layer thin
and makes everything easy to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DONE = "Done"
BLOCKED = "Blocked"
IN_PROGRESS = "In Progress"
TODO = "To Do"


# ---------------------------------------------------------------------------
# Sprint-level metrics
# ---------------------------------------------------------------------------
def sprint_metrics(issues: pd.DataFrame, sprints: pd.DataFrame) -> pd.DataFrame:
    """Per-sprint committed / completed / blocked points + completion ratio."""
    grouped = issues.groupby("sprint_id")["story_points"].sum().rename("committed_points")
    done = (
        issues[issues["status"] == DONE]
        .groupby("sprint_id")["story_points"]
        .sum()
        .rename("completed_points")
    )
    blocked = (
        issues[issues["status"] == BLOCKED]
        .groupby("sprint_id")["story_points"]
        .sum()
        .rename("blocked_points")
    )
    df = sprints.merge(grouped, on="sprint_id", how="left").merge(
        done, on="sprint_id", how="left"
    ).merge(blocked, on="sprint_id", how="left")

    for c in ("committed_points", "completed_points", "blocked_points"):
        df[c] = df[c].fillna(0).astype(int)

    df["completion_pct"] = (
        df["completed_points"] / df["committed_points"].replace(0, pd.NA) * 100
    ).fillna(0).round(1)
    df["over_commit_pct"] = (
        (df["committed_points"] - df["capacity_points"])
        / df["capacity_points"]
        * 100
    ).round(1)
    return df


def velocity(sprint_df: pd.DataFrame, window: int = 3) -> float:
    """Average completed points over the last `window` completed sprints."""
    completed = sprint_df[sprint_df["completed_points"] > 0].tail(window)
    if completed.empty:
        return 0.0
    return float(completed["completed_points"].mean().round(1))


# ---------------------------------------------------------------------------
# Capacity by role / assignee
# ---------------------------------------------------------------------------
def capacity_vs_load(issues: pd.DataFrame, team: pd.DataFrame, sprint_id: str) -> pd.DataFrame:
    sprint_issues = issues[issues["sprint_id"] == sprint_id]
    load = (
        sprint_issues.groupby("assignee")["story_points"]
        .sum()
        .rename("assigned_points")
        .reset_index()
    )
    merged = team.merge(load, left_on="member", right_on="assignee", how="left")
    merged["assigned_points"] = merged["assigned_points"].fillna(0).astype(int)
    merged["utilisation_pct"] = (
        merged["assigned_points"] / merged["capacity_per_sprint"] * 100
    ).round(1)
    merged["is_overloaded"] = merged["utilisation_pct"] > 110
    return merged.drop(columns=["assignee"])


# ---------------------------------------------------------------------------
# Epic progress
# ---------------------------------------------------------------------------
def epic_progress(issues: pd.DataFrame, epics: pd.DataFrame) -> pd.DataFrame:
    total = issues.groupby("epic_id")["story_points"].sum().rename("total_points")
    done = (
        issues[issues["status"] == DONE]
        .groupby("epic_id")["story_points"]
        .sum()
        .rename("done_points")
    )
    blocked = (
        issues[issues["status"] == BLOCKED]
        .groupby("epic_id")["story_points"]
        .sum()
        .rename("blocked_points")
    )
    df = epics.merge(total, on="epic_id", how="left").merge(
        done, on="epic_id", how="left"
    ).merge(blocked, on="epic_id", how="left")

    for c in ("total_points", "done_points", "blocked_points"):
        df[c] = df[c].fillna(0).astype(int)

    df["progress_pct"] = (
        df["done_points"] / df["total_points"].replace(0, pd.NA) * 100
    ).fillna(0).round(1)
    return df


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def dependency_edges(issues: pd.DataFrame) -> pd.DataFrame:
    """Return a tidy edges dataframe: source (blocker) -> target (blocked)."""
    deps = issues[issues["blocked_by"].astype(str).str.len() > 0][
        ["issue_key", "blocked_by", "status", "sprint_id"]
    ].copy()
    deps = deps.rename(columns={"issue_key": "target", "blocked_by": "source"})
    return deps


def blocker_hotspots(issues: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Issues that block the most other issues - planning hotspots."""
    deps = dependency_edges(issues)
    if deps.empty:
        return pd.DataFrame(columns=["blocker", "blocks_count", "summary"])
    counts = deps.groupby("source").size().rename("blocks_count").reset_index()
    counts = counts.sort_values("blocks_count", ascending=False).head(top_n)
    enriched = counts.merge(
        issues[["issue_key", "summary", "status", "sprint_id"]],
        left_on="source",
        right_on="issue_key",
        how="left",
    ).drop(columns=["issue_key"]).rename(columns={"source": "blocker"})
    return enriched


# ---------------------------------------------------------------------------
# Delivery risk scoring
# ---------------------------------------------------------------------------
@dataclass
class RiskScore:
    epic_id: str
    score: float          # 0 (safe) -> 100 (very risky)
    band: str             # Low / Medium / High / Critical
    drivers: list[str]


def _band(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def delivery_risk(issues: pd.DataFrame, epics: pd.DataFrame) -> pd.DataFrame:
    """Compute a delivery-risk score per epic from blockers, scope, and progress."""
    rows: list[RiskScore] = []
    progress = epic_progress(issues, epics).set_index("epic_id")

    for epic_id, p in progress.iterrows():
        drivers: list[str] = []
        score = 0.0

        if p["total_points"] == 0:
            rows.append(RiskScore(epic_id, 0, "Low", ["No scope committed"]))
            continue

        blocked_ratio = p["blocked_points"] / p["total_points"]
        score += min(blocked_ratio * 100, 40)
        if blocked_ratio > 0.1:
            drivers.append(f"{blocked_ratio:.0%} of scope is blocked")

        # Progress vs sprints elapsed
        epic_issues = issues[issues["epic_id"] == epic_id]
        sprints_touched = epic_issues["sprint_id"].nunique()
        if sprints_touched > 0:
            expected_progress = min(100, sprints_touched * 20)
            gap = max(0, expected_progress - p["progress_pct"])
            score += min(gap * 0.3, 25)
            if gap > 20:
                drivers.append(
                    f"Progress {p['progress_pct']:.0f}% trails expected ~{expected_progress:.0f}%"
                )

        # Scope size penalty
        if p["total_points"] > 60:
            score += 15
            drivers.append(f"Large scope ({int(p['total_points'])} points)")

        # Priority bump
        if str(p["priority"]).lower() in ("critical", "high"):
            score += 10
            drivers.append(f"{p['priority']} priority")

        # Dependency count
        epic_keys = set(epic_issues["issue_key"])
        deps = dependency_edges(issues)
        cross_deps = deps[deps["target"].isin(epic_keys) & ~deps["source"].isin(epic_keys)]
        if len(cross_deps) > 2:
            score += min(len(cross_deps) * 2, 10)
            drivers.append(f"{len(cross_deps)} external dependencies")

        score = round(min(score, 100), 1)
        rows.append(
            RiskScore(
                epic_id=epic_id,
                score=score,
                band=_band(score),
                drivers=drivers or ["On track"],
            )
        )

    return pd.DataFrame([r.__dict__ for r in rows])


# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------
def headline_kpis(issues: pd.DataFrame, sprints: pd.DataFrame) -> dict:
    sm = sprint_metrics(issues, sprints)
    return {
        "total_issues": int(len(issues)),
        "total_points": int(issues["story_points"].sum()),
        "done_points": int(issues.loc[issues["status"] == DONE, "story_points"].sum()),
        "blocked_points": int(issues.loc[issues["status"] == BLOCKED, "story_points"].sum()),
        "velocity_3": velocity(sm, window=3),
        "average_completion_pct": float(sm["completion_pct"].replace(0, pd.NA).mean(skipna=True) or 0),
    }
