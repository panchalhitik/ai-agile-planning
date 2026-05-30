"""Pytest coverage for the analytics layer.

These tests use hand-crafted dataframes so they don't depend on the synthetic
data generator - they pin the maths.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import analytics


@pytest.fixture
def sprints() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sprint_id": "S01", "sprint_name": "Sprint 1",
             "start_date": "2026-01-06", "end_date": "2026-01-19",
             "capacity_points": 50},
            {"sprint_id": "S02", "sprint_name": "Sprint 2",
             "start_date": "2026-01-20", "end_date": "2026-02-02",
             "capacity_points": 50},
        ]
    )


@pytest.fixture
def epics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"epic_id": "EPIC-1", "epic_name": "Login", "owner_team": "Backend", "priority": "High"},
            {"epic_id": "EPIC-2", "epic_name": "Search", "owner_team": "Data", "priority": "Critical"},
        ]
    )


@pytest.fixture
def issues() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Sprint 1 - 40 pts committed, 30 done, 5 blocked
            {"issue_key": "A-1", "summary": "Login API", "epic_id": "EPIC-1", "sprint_id": "S01",
             "story_points": 20, "status": "Done", "assignee": "Alice",
             "issue_type": "Story", "priority": "High", "blocked_by": ""},
            {"issue_key": "A-2", "summary": "Login UI", "epic_id": "EPIC-1", "sprint_id": "S01",
             "story_points": 10, "status": "Done", "assignee": "Bob",
             "issue_type": "Story", "priority": "High", "blocked_by": ""},
            {"issue_key": "A-3", "summary": "Search bug", "epic_id": "EPIC-2", "sprint_id": "S01",
             "story_points": 5, "status": "Blocked", "assignee": "Bob",
             "issue_type": "Bug", "priority": "High", "blocked_by": "A-1"},
            {"issue_key": "A-4", "summary": "Search indexing", "epic_id": "EPIC-2", "sprint_id": "S01",
             "story_points": 5, "status": "In Progress", "assignee": "Bob",
             "issue_type": "Story", "priority": "Medium", "blocked_by": "A-1"},
            # Sprint 2 - 30 pts committed, 0 done
            {"issue_key": "B-1", "summary": "Search ranking", "epic_id": "EPIC-2", "sprint_id": "S02",
             "story_points": 30, "status": "To Do", "assignee": "Alice",
             "issue_type": "Story", "priority": "Critical", "blocked_by": ""},
        ]
    )


@pytest.fixture
def team() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"member": "Alice", "role": "Backend", "capacity_per_sprint": 25},
            {"member": "Bob", "role": "Backend", "capacity_per_sprint": 15},
        ]
    )


def test_sprint_metrics_totals(issues, sprints):
    df = analytics.sprint_metrics(issues, sprints).set_index("sprint_id")
    assert df.loc["S01", "committed_points"] == 40
    assert df.loc["S01", "completed_points"] == 30
    assert df.loc["S01", "blocked_points"] == 5
    assert df.loc["S01", "completion_pct"] == 75.0
    assert df.loc["S02", "completed_points"] == 0


def test_velocity_uses_completed_only(issues, sprints):
    sm = analytics.sprint_metrics(issues, sprints)
    # Only S01 has completed points, so velocity = 30
    assert analytics.velocity(sm) == 30.0


def test_capacity_vs_load_flags_overload(issues, team):
    cap = analytics.capacity_vs_load(issues, team, "S01")
    bob = cap[cap["member"] == "Bob"].iloc[0]
    # Bob has 10+5+5 = 20 assigned vs capacity 15 -> 133%
    assert bob["assigned_points"] == 20
    assert bob["utilisation_pct"] == pytest.approx(133.3, rel=1e-2)
    assert bool(bob["is_overloaded"]) is True

    alice = cap[cap["member"] == "Alice"].iloc[0]
    assert alice["assigned_points"] == 20
    assert bool(alice["is_overloaded"]) is False


def test_epic_progress_percentages(issues, epics):
    ep = analytics.epic_progress(issues, epics).set_index("epic_id")
    assert ep.loc["EPIC-1", "total_points"] == 30
    assert ep.loc["EPIC-1", "done_points"] == 30
    assert ep.loc["EPIC-1", "progress_pct"] == 100.0
    assert ep.loc["EPIC-2", "blocked_points"] == 5


def test_blocker_hotspots_ranks_by_count(issues):
    hot = analytics.blocker_hotspots(issues)
    # A-1 blocks both A-3 and A-4
    assert not hot.empty
    top = hot.iloc[0]
    assert top["blocker"] == "A-1"
    assert top["blocks_count"] == 2


def test_delivery_risk_flags_blocked_critical(issues, epics):
    risk = analytics.delivery_risk(issues, epics).set_index("epic_id")
    # EPIC-2 has 25% blocked + Critical priority -> non-zero
    assert risk.loc["EPIC-2", "score"] > 10
    assert risk.loc["EPIC-2", "band"] in {"Medium", "High", "Critical"}
    # EPIC-1 is fully done -> low risk
    assert risk.loc["EPIC-1", "band"] == "Low"


def test_headline_kpis_keys(issues, sprints):
    k = analytics.headline_kpis(issues, sprints)
    for key in ("total_issues", "total_points", "done_points",
                "blocked_points", "velocity_3"):
        assert key in k
    assert k["total_issues"] == 5
    assert k["done_points"] == 30
