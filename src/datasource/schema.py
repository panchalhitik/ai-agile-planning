"""Canonical schema + validation for every data source."""

from __future__ import annotations

import pandas as pd

from src.data_loader import AgileData

CANONICAL_STATUSES = ["Done", "In Progress", "To Do", "Blocked"]

# Lowercased alias -> canonical status. Sources map their own vocab here.
STATUS_ALIASES = {
    "done": "Done", "closed": "Done", "resolved": "Done", "complete": "Done",
    "completed": "Done", "finished": "Done",
    "in progress": "In Progress", "in development": "In Progress",
    "in dev": "In Progress", "in review": "In Progress", "review": "In Progress",
    "doing": "In Progress", "active": "In Progress", "started": "In Progress",
    "to do": "To Do", "todo": "To Do", "open": "To Do", "backlog": "To Do",
    "new": "To Do", "selected for development": "To Do", "ready": "To Do",
    "blocked": "Blocked", "impediment": "Blocked", "on hold": "Blocked",
    "waiting": "Blocked",
}

REQUIRED_COLUMNS = {
    "issues": [
        "issue_key", "summary", "issue_type", "epic_id", "sprint_id",
        "story_points", "status", "assignee", "priority", "blocked_by",
    ],
    "sprints": ["sprint_id", "sprint_name", "start_date", "end_date", "capacity_points"],
    "epics": ["epic_id", "epic_name", "owner_team", "priority"],
    "team": ["member", "role", "capacity_per_sprint"],
}


def normalize_status(value: str) -> str | None:
    if value in CANONICAL_STATUSES:
        return value
    return STATUS_ALIASES.get(str(value).strip().lower())


def validate_agile_data(data: AgileData) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors block activation; warnings inform."""
    errors: list[str] = []
    warnings: list[str] = []

    for name, df in (
        ("issues", data.issues),
        ("sprints", data.sprints),
        ("epics", data.epics),
        ("team", data.team),
    ):
        missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
        if missing:
            errors.append(f"{name}: missing column(s) {', '.join(missing)}")

    if errors:
        return errors, warnings

    issues = data.issues
    if issues.empty:
        errors.append("issues: no rows")
        return errors, warnings

    if issues["issue_key"].duplicated().any():
        dupes = issues.loc[issues["issue_key"].duplicated(), "issue_key"].head(3).tolist()
        warnings.append(f"issues: duplicate keys (e.g. {', '.join(map(str, dupes))})")

    unknown_status = ~issues["status"].isin(CANONICAL_STATUSES)
    if unknown_status.any():
        vals = issues.loc[unknown_status, "status"].unique()[:4]
        warnings.append(
            "issues: unrecognised status value(s) "
            f"{', '.join(map(repr, vals))} — treated as 'To Do'"
        )

    known_sprints = set(data.sprints["sprint_id"].astype(str))
    orphan_sprints = ~issues["sprint_id"].astype(str).isin(known_sprints)
    if orphan_sprints.any():
        warnings.append(
            f"issues: {int(orphan_sprints.sum())} row(s) reference sprints "
            "not present in the sprint list"
        )

    known_keys = set(issues["issue_key"].astype(str))
    has_dep = issues["blocked_by"].astype(str).str.len() > 0
    dangling = has_dep & ~issues["blocked_by"].astype(str).isin(known_keys)
    if dangling.any():
        warnings.append(
            f"issues: {int(dangling.sum())} blocked_by reference(s) point at "
            "unknown issues (ignored in the dependency graph)"
        )

    if not pd.api.types.is_numeric_dtype(issues["story_points"]):
        warnings.append("issues: story_points was not numeric — coerced, blanks = 0")

    return errors, warnings


def clean_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce types + normalize statuses; unknown statuses become 'To Do'."""
    out = df.copy()
    out["story_points"] = (
        pd.to_numeric(out["story_points"], errors="coerce").fillna(0).astype(int)
    )
    out["blocked_by"] = out["blocked_by"].fillna("").astype(str).str.strip()
    out["status"] = (
        out["status"].map(lambda s: normalize_status(s) or "To Do").astype(str)
    )
    out["assignee"] = out["assignee"].fillna("Unassigned").replace("", "Unassigned")
    for col in ("issue_key", "summary", "epic_id", "sprint_id", "priority"):
        out[col] = out[col].fillna("").astype(str)
    return out
