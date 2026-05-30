"""
Generates a deterministic, Jira-style synthetic dataset for the dashboard.

Outputs (CSV):
    data/epics.csv     - epic-level metadata
    data/issues.csv    - story/task-level rows with sprint, points, status, assignee
    data/sprints.csv   - sprint metadata with capacity (story points)
    data/team.csv      - team members with role and capacity per sprint

Run:
    python data/generate_data.py
"""

from __future__ import annotations

import os
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RNG_SEED = 42
DATA_DIR = Path(__file__).resolve().parent

NUM_SPRINTS = 8
SPRINT_LENGTH_DAYS = 14
SPRINT_START = date(2026, 1, 6)

TEAM = [
    ("Alice Chen", "Backend", 10),
    ("Bilal Ahmed", "Backend", 9),
    ("Carla Diaz", "Frontend", 9),
    ("Devon Park", "Frontend", 8),
    ("Esha Rao", "Data", 10),
    ("Finn O'Brien", "QA", 7),
    ("Grace Lim", "Design", 6),
    ("Hugo Martin", "DevOps", 8),
]

EPICS = [
    ("EPIC-101", "Checkout Redesign", "Frontend", "High"),
    ("EPIC-102", "Search Relevance v2", "Data", "High"),
    ("EPIC-103", "Payments Reliability", "Backend", "Critical"),
    ("EPIC-104", "Mobile Performance", "Frontend", "Medium"),
    ("EPIC-105", "Internal Admin Tools", "Backend", "Low"),
    ("EPIC-106", "Observability Uplift", "DevOps", "Medium"),
]

ISSUE_TYPES = ["Story", "Task", "Bug", "Spike"]
ISSUE_TYPE_WEIGHTS = [0.55, 0.2, 0.2, 0.05]

STATUSES = ["Done", "In Progress", "To Do", "Blocked"]


def _rng() -> random.Random:
    return random.Random(RNG_SEED)


def build_sprints() -> pd.DataFrame:
    rows = []
    for i in range(1, NUM_SPRINTS + 1):
        start = SPRINT_START + timedelta(days=(i - 1) * SPRINT_LENGTH_DAYS)
        end = start + timedelta(days=SPRINT_LENGTH_DAYS - 1)
        capacity = sum(c for _, _, c in TEAM)
        rows.append(
            {
                "sprint_id": f"S{i:02d}",
                "sprint_name": f"Sprint {i}",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "capacity_points": capacity,
            }
        )
    return pd.DataFrame(rows)


def build_team() -> pd.DataFrame:
    rows = [
        {"member": name, "role": role, "capacity_per_sprint": cap}
        for name, role, cap in TEAM
    ]
    return pd.DataFrame(rows)


def build_epics() -> pd.DataFrame:
    rows = [
        {
            "epic_id": eid,
            "epic_name": name,
            "owner_team": team,
            "priority": prio,
        }
        for eid, name, team, prio in EPICS
    ]
    return pd.DataFrame(rows)


def build_issues(sprints: pd.DataFrame) -> pd.DataFrame:
    rng = _rng()
    np_rng = np.random.default_rng(RNG_SEED)

    issues = []
    issue_counter = 1
    today = SPRINT_START + timedelta(days=SPRINT_LENGTH_DAYS * 5)

    for sprint in sprints.itertuples():
        sprint_index = int(sprint.sprint_id[1:])
        sprint_start = date.fromisoformat(sprint.start_date)
        sprint_end = date.fromisoformat(sprint.end_date)
        is_past = sprint_end < today
        is_current = sprint_start <= today <= sprint_end

        # Aim for slight over-commitment in some sprints to surface risk.
        target_commit = sprint.capacity_points + rng.choice([-6, -3, 0, 4, 8])
        committed = 0

        while committed < target_commit:
            epic = rng.choice(EPICS)
            issue_type = rng.choices(ISSUE_TYPES, weights=ISSUE_TYPE_WEIGHTS, k=1)[0]
            points = int(np_rng.choice([1, 2, 3, 5, 8, 13], p=[0.1, 0.2, 0.3, 0.25, 0.1, 0.05]))
            if committed + points > target_commit + 5:
                points = max(1, target_commit - committed)

            assignee_name, assignee_role, _ = rng.choice(TEAM)

            if is_past:
                # 80% Done, rest split between Bug-carryover and Blocked
                status = rng.choices(STATUSES, weights=[0.82, 0.05, 0.05, 0.08], k=1)[0]
            elif is_current:
                status = rng.choices(STATUSES, weights=[0.35, 0.4, 0.15, 0.1], k=1)[0]
            else:
                status = rng.choices(STATUSES, weights=[0.0, 0.05, 0.9, 0.05], k=1)[0]

            issues.append(
                {
                    "issue_key": f"AGL-{issue_counter:04d}",
                    "summary": f"{issue_type} for {epic[1]}",
                    "issue_type": issue_type,
                    "epic_id": epic[0],
                    "sprint_id": sprint.sprint_id,
                    "story_points": points,
                    "status": status,
                    "assignee": assignee_name,
                    "assignee_role": assignee_role,
                    "priority": rng.choices(
                        ["Critical", "High", "Medium", "Low"],
                        weights=[0.08, 0.27, 0.5, 0.15],
                        k=1,
                    )[0],
                    "created_at": (sprint_start - timedelta(days=rng.randint(1, 21))).isoformat(),
                    "updated_at": sprint_end.isoformat(),
                }
            )
            committed += points
            issue_counter += 1

    df = pd.DataFrame(issues)

    # Add cross-issue dependencies: ~12% of issues depend on another issue
    # Use the second issue in the list as a stable seed.
    dep_targets = []
    keys = df["issue_key"].tolist()
    for k in keys:
        if rng.random() < 0.12:
            candidate = rng.choice(keys)
            if candidate == k:
                candidate = ""
            dep_targets.append(candidate)
        else:
            dep_targets.append("")
    df["blocked_by"] = dep_targets
    return df


def write_outputs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sprints = build_sprints()
    team = build_team()
    epics = build_epics()
    issues = build_issues(sprints)

    sprints.to_csv(DATA_DIR / "sprints.csv", index=False)
    team.to_csv(DATA_DIR / "team.csv", index=False)
    epics.to_csv(DATA_DIR / "epics.csv", index=False)
    issues.to_csv(DATA_DIR / "issues.csv", index=False)

    print(f"Wrote {len(sprints)} sprints, {len(team)} team members, "
          f"{len(epics)} epics, {len(issues)} issues to {DATA_DIR}")


if __name__ == "__main__":
    write_outputs()
