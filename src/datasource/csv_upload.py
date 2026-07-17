"""CSV upload: fuzzy header mapping + derivation of sprints/team/epics when
only an issues export is provided (the common case with Jira CSV exports)."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd

from src.data_loader import AgileData
from src.datasource.schema import clean_issues

# target field -> lowercase header fragments that suggest it (checked in order)
HEADER_HINTS: dict[str, list[str]] = {
    "issue_key": ["issue key", "issue id", "key", "id", "ticket"],
    "summary": ["summary", "title", "name", "description"],
    "issue_type": ["issue type", "issuetype", "type", "work item type"],
    "epic_id": ["epic link", "epic", "parent", "initiative", "feature"],
    "sprint_id": ["sprint", "iteration", "cycle", "milestone"],
    "story_points": ["story points", "story point estimate", "points", "estimate", "effort", "size"],
    "status": ["status", "state", "column"],
    "assignee": ["assignee", "assigned to", "owner", "responsible"],
    "priority": ["priority", "severity", "importance"],
    "blocked_by": ["blocked by", "is blocked by", "inward issue link (blocks)", "depends on", "dependency"],
    "created_at": ["created", "creation date", "opened"],
    "updated_at": ["updated", "last updated", "resolved", "modified"],
}

REQUIRED_TARGETS = ["issue_key", "summary", "sprint_id", "status"]
OPTIONAL_TARGETS = [
    "issue_type", "epic_id", "story_points", "assignee", "priority",
    "blocked_by", "created_at", "updated_at",
]


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    """Best-guess mapping target -> source column via fuzzy header matching."""
    normalized = {c: re.sub(r"[^a-z0-9 ]", "", str(c).lower()).strip() for c in columns}
    used: set[str] = set()
    mapping: dict[str, str | None] = {}
    for target, hints in HEADER_HINTS.items():
        found = None
        for hint in hints:
            for col, norm in normalized.items():
                if col in used:
                    continue
                if norm == hint or hint in norm:
                    found = col
                    break
            if found:
                break
        if found:
            used.add(found)
        mapping[target] = found
    return mapping


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    """Build a canonical issues frame from the raw upload + column mapping."""
    out = pd.DataFrame()
    for target in REQUIRED_TARGETS + OPTIONAL_TARGETS:
        source = mapping.get(target)
        if source and source in raw.columns:
            out[target] = raw[source]
        else:
            out[target] = "" if target != "story_points" else 0
    if "issue_type" in out and (out["issue_type"] == "").all():
        out["issue_type"] = "Story"
    if (out["epic_id"] == "").all():
        out["epic_id"] = "General"
    out["priority"] = out["priority"].replace("", "Medium")
    return clean_issues(out)


def apply_status_mapping(issues: pd.DataFrame, status_map: dict[str, str]) -> pd.DataFrame:
    out = issues.copy()
    out["status"] = out["status"].map(lambda s: status_map.get(s, s))
    return clean_issues(out)


# ---------------------------------------------------------------------------
# Derivation of the supporting tables from issues alone
# ---------------------------------------------------------------------------
def derive_sprints(issues: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    labels = [s for s in issues["sprint_id"].astype(str).unique() if s.strip()]

    def _sort_key(label: str):
        nums = re.findall(r"\d+", label)
        return (int(nums[-1]) if nums else 10**9, label)

    labels.sort(key=_sort_key)
    committed = issues.groupby("sprint_id")["story_points"].sum()
    capacity = int(committed.median()) if len(committed) else 0

    rows = []
    n = len(labels)
    for i, label in enumerate(labels):
        # Without real dates, lay sprints on a 2-week cadence ending today.
        start = today - timedelta(days=14 * (n - i) - 1)
        end = start + timedelta(days=13)
        rows.append(
            {
                "sprint_id": label,
                "sprint_name": label,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "capacity_points": capacity,
            }
        )
    return pd.DataFrame(rows)


def derive_team(issues: pd.DataFrame) -> pd.DataFrame:
    per_sprint = (
        issues.groupby(["assignee", "sprint_id"])["story_points"].sum().reset_index()
    )
    capacity = per_sprint.groupby("assignee")["story_points"].median()
    rows = [
        {
            "member": member,
            "role": "—",
            "capacity_per_sprint": max(int(cap), 1),
        }
        for member, cap in capacity.items()
        if str(member).strip()
    ]
    return pd.DataFrame(rows or [{"member": "Unassigned", "role": "—", "capacity_per_sprint": 1}])


def derive_epics(issues: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"epic_id": str(e), "epic_name": str(e), "owner_team": "—", "priority": "Medium"}
        for e in issues["epic_id"].astype(str).unique()
        if str(e).strip()
    ]
    return pd.DataFrame(rows or [{"epic_id": "General", "epic_name": "General",
                                  "owner_team": "—", "priority": "Medium"}])


def build_agile_data(issues: pd.DataFrame, today: date | None = None) -> AgileData:
    """Canonical issues frame -> full AgileData with derived support tables."""
    issues = clean_issues(issues)
    sprints = derive_sprints(issues, today)
    sprints["start_date"] = pd.to_datetime(sprints["start_date"]).dt.date
    sprints["end_date"] = pd.to_datetime(sprints["end_date"]).dt.date
    return AgileData(
        sprints=sprints,
        team=derive_team(issues),
        epics=derive_epics(issues),
        issues=issues,
    )
