"""Monte Carlo forecast and sprint-health analytics."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src import analytics


@pytest.fixture
def sprints() -> pd.DataFrame:
    rows = []
    for i in range(1, 5):
        rows.append(
            {
                "sprint_id": f"S{i:02d}",
                "sprint_name": f"Sprint {i}",
                "start_date": (date(2026, 1, 5) + pd.Timedelta(days=(i - 1) * 14)).isoformat(),
                "end_date": (date(2026, 1, 18) + pd.Timedelta(days=(i - 1) * 14)).isoformat(),
                "capacity_points": 30,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def issues() -> pd.DataFrame:
    """Three finished sprints at velocity 30/25/28; S04 in flight with a
    100-point remaining backlog."""
    rows = []

    def add(sprint, points, status, n):
        for i in range(n):
            rows.append(
                {
                    "issue_key": f"{sprint}-{status[:2]}{i}",
                    "summary": "x",
                    "issue_type": "Story",
                    "epic_id": "E1",
                    "sprint_id": sprint,
                    "story_points": points,
                    "status": status,
                    "assignee": "A",
                    "priority": "Medium",
                    "blocked_by": "",
                }
            )

    add("S01", 5, "Done", 6)        # 30 done
    add("S02", 5, "Done", 5)        # 25 done
    add("S03", 4, "Done", 7)        # 28 done
    add("S04", 5, "In Progress", 8)  # 40 remaining
    add("S04", 5, "To Do", 12)       # 60 remaining
    return pd.DataFrame(rows)


TODAY = date(2026, 2, 20)  # inside S04 (Feb 16 - Mar 1)


def test_current_sprint_and_health(issues, sprints):
    assert analytics.current_sprint_id(sprints, TODAY) == "S04"
    h = analytics.sprint_health(issues, sprints, TODAY)
    assert h["sprint_id"] == "S04"
    assert h["days_total"] == 14
    assert 0 < h["days_elapsed"] <= 14
    assert h["committed_points"] == 100

    # After every sprint has ended, fall back to the last one.
    assert analytics.current_sprint_id(sprints, date(2027, 1, 1)) == "S04"


def test_forecast_percentiles_monotonic(issues, sprints):
    fc = analytics.monte_carlo_forecast(issues, sprints, TODAY)
    assert fc["ok"]
    assert fc["remaining_points"] == 100
    assert sorted(fc["velocity_samples"]) == [25.0, 28.0, 30.0]
    p = fc["percentiles"]
    assert p["p50"]["sprints"] <= p["p70"]["sprints"] <= p["p85"]["sprints"] <= p["p95"]["sprints"]
    # 100 pts at velocity 25-30 needs about 4 sprints.
    assert 3 <= p["p50"]["sprints"] <= 5
    assert p["p95"]["finish_date"] >= p["p50"]["finish_date"]


def test_forecast_is_deterministic(issues, sprints):
    a = analytics.monte_carlo_forecast(issues, sprints, TODAY)
    b = analytics.monte_carlo_forecast(issues, sprints, TODAY)
    assert a["percentiles"] == b["percentiles"]
    assert a["distribution"] == b["distribution"]


def test_what_if_moves_the_right_direction(issues, sprints):
    more_scope = analytics.what_if_forecast(issues, sprints, TODAY, scope_delta_pct=30)
    assert (
        more_scope["scenario"]["percentiles"]["p85"]["sprints"]
        >= more_scope["baseline"]["percentiles"]["p85"]["sprints"]
    )
    more_people = analytics.what_if_forecast(issues, sprints, TODAY, capacity_delta_pct=40)
    assert (
        more_people["scenario"]["percentiles"]["p85"]["sprints"]
        <= more_people["baseline"]["percentiles"]["p85"]["sprints"]
    )


def test_forecast_edge_cases(sprints):
    # All work done -> zero sprints, finish now.
    done = pd.DataFrame(
        [
            {
                "issue_key": "A-1", "summary": "x", "issue_type": "Story",
                "epic_id": "E1", "sprint_id": "S01", "story_points": 10,
                "status": "Done", "assignee": "A", "priority": "High",
                "blocked_by": "",
            }
        ]
    )
    fc = analytics.monte_carlo_forecast(done, sprints, TODAY)
    assert fc["ok"] and fc["percentiles"]["p85"]["sprints"] == 0

    # No finished sprints -> graceful refusal.
    fresh = done.assign(status="To Do")
    fc2 = analytics.monte_carlo_forecast(fresh, sprints, date(2026, 1, 6))
    assert not fc2["ok"] and "reason" in fc2
