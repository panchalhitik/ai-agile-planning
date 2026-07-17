"""Datasource layer: CSV mapping, schema validation, Jira normalization."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.datasource import csv_upload, schema
from src.datasource import jira as jira_mod


# ---------------------------------------------------------------------------
# CSV mapping
# ---------------------------------------------------------------------------
def test_suggest_mapping_recognises_jira_export_headers():
    cols = [
        "Issue key", "Issue id", "Summary", "Issue Type", "Status",
        "Priority", "Assignee", "Custom field (Story Points)",
        "Sprint", "Epic Link", "Created", "Updated",
    ]
    mapping = csv_upload.suggest_mapping(cols)
    assert mapping["issue_key"] == "Issue key"
    assert mapping["summary"] == "Summary"
    assert mapping["issue_type"] == "Issue Type"
    assert mapping["story_points"] == "Custom field (Story Points)"
    assert mapping["sprint_id"] == "Sprint"
    assert mapping["epic_id"] == "Epic Link"
    assert mapping["status"] == "Status"
    assert mapping["assignee"] == "Assignee"


def test_apply_mapping_and_build_agile_data():
    raw = pd.DataFrame(
        {
            "Key": ["T-1", "T-2", "T-3", "T-4"],
            "Title": ["Login API", "Login UI", "Search fix", "Search index"],
            "Sprint": ["Sprint 1", "Sprint 1", "Sprint 2", "Sprint 2"],
            "State": ["Closed", "In Development", "Impediment", "Open"],
            "Points": ["5", "3", None, "8"],
            "Owner": ["Ana", "Ben", "Ana", ""],
        }
    )
    mapping = {
        "issue_key": "Key", "summary": "Title", "sprint_id": "Sprint",
        "status": "State", "story_points": "Points", "assignee": "Owner",
    }
    issues = csv_upload.apply_mapping(raw, mapping)
    # Status aliases normalize to canonical values.
    assert issues["status"].tolist() == ["Done", "In Progress", "Blocked", "To Do"]
    assert issues["story_points"].tolist() == [5, 3, 0, 8]
    assert issues.loc[3, "assignee"] == "Unassigned"

    data = csv_upload.build_agile_data(issues, today=date(2026, 7, 15))
    assert list(data.sprints["sprint_id"]) == ["Sprint 1", "Sprint 2"]
    assert set(data.team["member"]) == {"Ana", "Ben", "Unassigned"}
    errors, _ = schema.validate_agile_data(data)
    assert errors == []


def test_validation_flags_problems():
    issues = pd.DataFrame(
        {
            "issue_key": ["A-1", "A-1"],
            "summary": ["x", "y"],
            "issue_type": ["Story", "Story"],
            "epic_id": ["E", "E"],
            "sprint_id": ["S1", "S-unknown"],
            "story_points": [3, 5],
            "status": ["Done", "Weird Status"],
            "assignee": ["A", "B"],
            "priority": ["High", "Low"],
            "blocked_by": ["", "GHOST-9"],
        }
    )
    data = csv_upload.build_agile_data(issues)
    # build_agile_data derives sprints from labels, so fake a mismatch:
    data.sprints = data.sprints[data.sprints["sprint_id"] == "S1"]
    errors, warnings = schema.validate_agile_data(data)
    assert errors == []
    joined = " | ".join(warnings)
    assert "duplicate keys" in joined
    assert "unknown issues" in joined
    assert "sprints" in joined


def test_validation_errors_on_missing_columns():
    bad = csv_upload.build_agile_data(
        pd.DataFrame(
            {
                "issue_key": ["A-1"], "summary": ["x"], "issue_type": ["Story"],
                "epic_id": ["E"], "sprint_id": ["S1"], "story_points": [1],
                "status": ["Done"], "assignee": ["A"], "priority": ["High"],
                "blocked_by": [""],
            }
        )
    )
    bad.issues = bad.issues.drop(columns=["status"])
    errors, _ = schema.validate_agile_data(bad)
    assert any("missing column" in e for e in errors)


# ---------------------------------------------------------------------------
# Jira fixture -> AgileData
# ---------------------------------------------------------------------------
JIRA_FIXTURE = {
    "/rest/api/3/myself": {"displayName": "Test User"},
    "/rest/api/3/field": [
        {"id": "customfield_10016", "name": "Story point estimate"},
        {"id": "summary", "name": "Summary"},
    ],
    "/rest/agile/1.0/board": {
        "isLast": True,
        "values": [{"id": 7, "name": "Web Board", "type": "scrum"}],
    },
    "/rest/agile/1.0/board/7/sprint": {
        "isLast": True,
        "values": [
            {"id": 101, "name": "Sprint A", "startDate": "2026-06-01T00:00:00Z",
             "endDate": "2026-06-14T00:00:00Z"},
            {"id": 102, "name": "Sprint B", "startDate": "2026-06-15T00:00:00Z",
             "endDate": "2026-06-28T00:00:00Z"},
        ],
    },
    "/rest/agile/1.0/sprint/101/issue": {
        "total": 2,
        "issues": [
            {
                "key": "WEB-1",
                "fields": {
                    "summary": "Build login",
                    "issuetype": {"name": "Story"},
                    "status": {"name": "Done", "statusCategory": {"key": "done"}},
                    "assignee": {"displayName": "Ana"},
                    "priority": {"name": "High"},
                    "issuelinks": [],
                    "epic": {"key": "WEB-100", "name": "Auth"},
                    "customfield_10016": 5,
                    "created": "2026-05-20T10:00:00Z",
                    "updated": "2026-06-10T10:00:00Z",
                },
            },
            {
                "key": "WEB-2",
                "fields": {
                    "summary": "Login blocked work",
                    "issuetype": {"name": "Task"},
                    "status": {"name": "Blocked", "statusCategory": {"key": "indeterminate"}},
                    "assignee": None,
                    "priority": None,
                    "issuelinks": [
                        {"type": {"name": "Blocks"}, "inwardIssue": {"key": "WEB-1"}}
                    ],
                    "parent": {
                        "key": "WEB-100",
                        "fields": {"issuetype": {"name": "Epic"}, "summary": "Auth"},
                    },
                    "customfield_10016": None,
                    "created": "2026-05-22T10:00:00Z",
                    "updated": "2026-06-12T10:00:00Z",
                },
            },
        ],
    },
    "/rest/agile/1.0/sprint/102/issue": {
        "total": 1,
        "issues": [
            {
                "key": "WEB-3",
                "fields": {
                    "summary": "Search v1",
                    "issuetype": {"name": "Story"},
                    "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
                    "assignee": {"displayName": "Ben"},
                    "priority": {"name": "Medium"},
                    "issuelinks": [],
                    "customfield_10016": 8,
                    "created": "2026-06-16T10:00:00Z",
                    "updated": "2026-06-20T10:00:00Z",
                },
            }
        ],
    },
}


@pytest.fixture
def fake_jira(monkeypatch):
    def _fake_get(site, email, token, path, params=None):
        assert path in JIRA_FIXTURE, f"unexpected path {path}"
        return JIRA_FIXTURE[path]

    monkeypatch.setattr(jira_mod, "_get", _fake_get)


def test_jira_fixture_normalizes(fake_jira):
    assert jira_mod.test_connection("x.atlassian.net", "e@x.com", "tok") == "Test User"
    boards = jira_mod.list_boards("x.atlassian.net", "e@x.com", "tok")
    assert boards == [{"id": 7, "name": "Web Board", "type": "scrum"}]

    data, meta = jira_mod.fetch_board_data("x.atlassian.net", "e@x.com", "tok", 7, "Web Board")
    issues = data.issues.set_index("issue_key")
    assert issues.loc["WEB-1", "status"] == "Done"
    assert issues.loc["WEB-2", "status"] == "Blocked"          # name beats category
    assert issues.loc["WEB-2", "blocked_by"] == "WEB-1"        # Blocks link -> dep
    assert issues.loc["WEB-2", "epic_id"] == "WEB-100"         # parent-epic fallback
    assert issues.loc["WEB-2", "assignee"] == "Unassigned"
    assert issues.loc["WEB-3", "story_points"] == 8
    assert list(data.sprints["sprint_id"]) == ["101", "102"]
    assert meta["name"] == "Web Board"

    errors, _ = schema.validate_agile_data(data)
    assert errors == []


def test_jira_error_taxonomy(monkeypatch):
    class _Resp:
        status_code = 401

    monkeypatch.setattr(
        jira_mod.requests, "get", lambda *a, **k: _Resp()
    )
    with pytest.raises(jira_mod.JiraError, match="Authentication failed"):
        jira_mod.test_connection("x.atlassian.net", "e@x.com", "bad")
