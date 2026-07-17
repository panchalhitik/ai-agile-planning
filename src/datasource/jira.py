"""Jira Cloud connector (read-only, best-effort).

Basic auth with email + API token against the Jira Cloud REST APIs. Every
failure raises JiraError with a human-readable message; the Data hub keeps
the current source active on any error, so the demo path is never blocked.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from src.data_loader import AgileData
from src.datasource.csv_upload import derive_team
from src.datasource.schema import clean_issues

TIMEOUT = 10
MAX_SPRINTS = 12
PAGE_SIZE = 50


class JiraError(Exception):
    """A human-readable connection/fetch problem."""


def _auth(email: str, token: str) -> tuple[str, str]:
    return (email.strip(), token.strip())


def _base(site: str) -> str:
    site = site.strip().rstrip("/")
    if not site.startswith("http"):
        site = f"https://{site}"
    return site


def _get(site: str, email: str, token: str, path: str, params: dict | None = None) -> dict | list:
    url = f"{_base(site)}{path}"
    try:
        resp = requests.get(url, auth=_auth(email, token), params=params, timeout=TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise JiraError(f"Could not reach {_base(site)} — check the site URL.") from exc
    except requests.exceptions.Timeout as exc:
        raise JiraError("Jira did not respond within 10 seconds — try again.") from exc
    if resp.status_code == 401:
        raise JiraError("Authentication failed (401) — check the email and API token.")
    if resp.status_code == 403:
        raise JiraError("Access denied (403) — the token lacks permission for this resource.")
    if resp.status_code == 404:
        raise JiraError(f"Not found (404) at {path} — is this a Jira Cloud site with software boards?")
    if resp.status_code >= 400:
        raise JiraError(f"Jira returned HTTP {resp.status_code} for {path}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise JiraError("Jira returned a non-JSON response — check the site URL.") from exc


def test_connection(site: str, email: str, token: str) -> str:
    """Returns the authenticated user's display name."""
    me = _get(site, email, token, "/rest/api/3/myself")
    return me.get("displayName") or me.get("emailAddress") or "connected"


def list_boards(site: str, email: str, token: str) -> list[dict]:
    boards: list[dict] = []
    start = 0
    while True:
        page = _get(
            site, email, token, "/rest/agile/1.0/board",
            {"startAt": start, "maxResults": PAGE_SIZE},
        )
        boards += [
            {"id": b["id"], "name": b["name"], "type": b.get("type", "")}
            for b in page.get("values", [])
        ]
        if page.get("isLast", True) or not page.get("values"):
            break
        start += PAGE_SIZE
    if not boards:
        raise JiraError("No software boards visible to this account.")
    return boards


def _story_points_field(site: str, email: str, token: str) -> str | None:
    fields = _get(site, email, token, "/rest/api/3/field")
    for name in ("story point estimate", "story points"):
        for f in fields:
            if str(f.get("name", "")).lower() == name:
                return f["id"]
    return None


def _sprints(site: str, email: str, token: str, board_id: int) -> list[dict]:
    sprints: list[dict] = []
    start = 0
    while True:
        try:
            page = _get(
                site, email, token,
                f"/rest/agile/1.0/board/{board_id}/sprint",
                {"state": "active,closed", "startAt": start, "maxResults": PAGE_SIZE},
            )
        except JiraError as exc:
            if not sprints:
                raise JiraError(
                    "This board has no sprints (is it a Kanban board?)."
                ) from exc
            break
        sprints += page.get("values", [])
        if page.get("isLast", True) or not page.get("values"):
            break
        start += PAGE_SIZE
    if not sprints:
        raise JiraError("This board has no sprints (is it a Kanban board?).")
    return sprints[-MAX_SPRINTS:]


def _normalize_status(fields: dict) -> str:
    status = fields.get("status") or {}
    name = str(status.get("name", "")).lower()
    if "block" in name or "hold" in name or "imped" in name:
        return "Blocked"
    category = ((status.get("statusCategory") or {}).get("key") or "").lower()
    return {"done": "Done", "indeterminate": "In Progress", "new": "To Do"}.get(
        category, "To Do"
    )


def _blocked_by(fields: dict) -> str:
    for link in fields.get("issuelinks") or []:
        if str((link.get("type") or {}).get("name", "")).lower() == "blocks":
            inward = link.get("inwardIssue")
            if inward:
                return inward.get("key", "")
    return ""


def _epic_of(fields: dict) -> tuple[str, str]:
    epic = fields.get("epic")
    if epic and epic.get("key"):
        return epic["key"], epic.get("name") or epic["key"]
    parent = fields.get("parent")
    if parent:
        ptype = ((parent.get("fields") or {}).get("issuetype") or {}).get("name", "")
        if str(ptype).lower() == "epic":
            name = ((parent.get("fields") or {}).get("summary")) or parent.get("key", "")
            return parent.get("key", ""), name
    return "No epic", "No epic"


def fetch_board_data(
    site: str, email: str, token: str, board_id: int, board_name: str = ""
) -> tuple[AgileData, dict]:
    """Pull sprints + issues for a board and normalize into AgileData."""
    sp_field = _story_points_field(site, email, token)
    sprints_raw = _sprints(site, email, token, board_id)

    warnings: list[str] = []
    if sp_field is None:
        warnings.append("No 'Story Points' field found — all points set to 0.")

    issue_rows: list[dict] = []
    sprint_rows: list[dict] = []
    epic_names: dict[str, str] = {}

    field_list = "summary,issuetype,status,assignee,priority,issuelinks,epic,parent,created,updated"
    if sp_field:
        field_list += f",{sp_field}"

    for sprint in sprints_raw:
        sid = str(sprint["id"])
        sprint_rows.append(
            {
                "sprint_id": sid,
                "sprint_name": sprint.get("name", sid),
                "start_date": str(sprint.get("startDate", ""))[:10] or None,
                "end_date": str(sprint.get("endDate", sprint.get("completeDate", "")))[:10] or None,
                "capacity_points": 0,  # filled after committed totals are known
            }
        )
        start = 0
        while True:
            page = _get(
                site, email, token,
                f"/rest/agile/1.0/sprint/{sprint['id']}/issue",
                {"startAt": start, "maxResults": PAGE_SIZE, "fields": field_list},
            )
            for issue in page.get("issues", []):
                fields = issue.get("fields") or {}
                epic_id, epic_name = _epic_of(fields)
                epic_names.setdefault(epic_id, epic_name)
                points = fields.get(sp_field) if sp_field else 0
                issue_rows.append(
                    {
                        "issue_key": issue.get("key", ""),
                        "summary": fields.get("summary", ""),
                        "issue_type": ((fields.get("issuetype") or {}).get("name")) or "Story",
                        "epic_id": epic_id,
                        "sprint_id": sid,
                        "story_points": points if points is not None else 0,
                        "status": _normalize_status(fields),
                        "assignee": ((fields.get("assignee") or {}).get("displayName")) or "Unassigned",
                        "priority": ((fields.get("priority") or {}).get("name")) or "Medium",
                        "blocked_by": _blocked_by(fields),
                        "created_at": str(fields.get("created", ""))[:10],
                        "updated_at": str(fields.get("updated", ""))[:10],
                    }
                )
            total = page.get("total", 0)
            start += PAGE_SIZE
            if start >= total or not page.get("issues"):
                break

    if not issue_rows:
        raise JiraError("The selected board's sprints contain no issues.")

    issues = clean_issues(pd.DataFrame(issue_rows))

    sprints = pd.DataFrame(sprint_rows)
    committed = issues.groupby("sprint_id")["story_points"].sum()
    median_commit = int(committed.median()) if len(committed) else 0
    sprints["capacity_points"] = median_commit
    sprints["start_date"] = pd.to_datetime(sprints["start_date"], errors="coerce").dt.date
    sprints["end_date"] = pd.to_datetime(sprints["end_date"], errors="coerce").dt.date
    # Sprints without dates can't drive time math — drop them and their issues.
    dated = sprints.dropna(subset=["start_date", "end_date"])
    if dated.empty:
        raise JiraError("None of the board's sprints have start/end dates.")
    if len(dated) < len(sprints):
        warnings.append(f"Dropped {len(sprints) - len(dated)} sprint(s) without dates.")
        issues = issues[issues["sprint_id"].isin(dated["sprint_id"])]
    sprints = dated.sort_values("start_date").reset_index(drop=True)

    epics = pd.DataFrame(
        [
            {"epic_id": k, "epic_name": v, "owner_team": "—", "priority": "Medium"}
            for k, v in epic_names.items()
        ]
    )

    data = AgileData(
        sprints=sprints,
        team=derive_team(issues),
        epics=epics,
        issues=issues,
    )
    meta = {
        "name": board_name or f"Board {board_id}",
        "project_name": board_name or f"Jira board {board_id}",
        "blurb": f"Live data from Jira board {board_name or board_id}.",
        "anomalies": [],
        "today": date.today(),
        "warnings": warnings,
    }
    return data, meta
