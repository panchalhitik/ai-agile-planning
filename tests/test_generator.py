"""The demo dataset is the product: these tests pin the seeded anomalies so
a future tweak to the generator can't silently kill the demo story."""

from __future__ import annotations

import json

import networkx as nx
import pytest

from data.generate_data import BLOCKER_KEY, CURRENT_SPRINT_ID, write_outputs
from src import analytics, data_loader


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo_data")
    write_outputs(out)
    data = data_loader.load_data(out)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    return data, meta


def test_overloaded_engineer(generated):
    data, meta = generated
    cap = analytics.capacity_vs_load(data.issues, data.team, CURRENT_SPRINT_ID)
    cap = cap.set_index("member")
    priya = cap.loc["Priya Sharma"]
    assert priya["utilisation_pct"] > 130
    # Priya must be the clear outlier, not one of many.
    others = cap.drop("Priya Sharma")
    assert (others["utilisation_pct"] <= 130).all()
    assert priya["utilisation_pct"] >= others["utilisation_pct"].max() + 25


def test_blocker_chain(generated):
    data, _ = generated
    hot = analytics.blocker_hotspots(data.issues)
    top = hot.iloc[0]
    assert top["blocker"] == BLOCKER_KEY
    assert top["blocks_count"] >= 4
    assert "SDK v3" in top["summary"]
    # The anchor itself is live, not resolved.
    sdk = data.issues.set_index("issue_key").loc[BLOCKER_KEY]
    assert sdk["status"] == "In Progress"


def test_critical_epic(generated):
    data, meta = generated
    risk = analytics.delivery_risk(data.issues, data.epics).set_index("epic_id")
    critical_epic = next(
        a["epic_id"] for a in meta["anomalies"] if a["id"] == "critical_epic"
    )
    assert risk.loc[critical_epic, "band"] == "Critical"
    # And it is the only Critical epic, so it stands out.
    assert (risk["band"] == "Critical").sum() == 1


def test_velocity_dip_and_overcommit(generated):
    data, _ = generated
    sm = analytics.sprint_metrics(data.issues, data.sprints).set_index("sprint_id")
    assert sm.loc["S05", "completion_pct"] < 70
    assert sm.loc["S04", "completion_pct"] >= 75
    assert sm.loc["S06", "completion_pct"] >= 75
    # Sprint 7 is the over-commit spike.
    assert sm.loc["S07", "over_commit_pct"] > 10
    past = sm.drop(CURRENT_SPRINT_ID)
    assert sm.loc["S07", "over_commit_pct"] == past["over_commit_pct"].max()


def test_dependencies_are_coherent(generated):
    data, _ = generated
    issues = data.issues
    deps = analytics.dependency_edges(issues)
    known = set(issues["issue_key"])
    assert set(deps["source"]).issubset(known)

    g = nx.DiGraph()
    for _, row in deps.iterrows():
        g.add_edge(row["source"], row["target"])
    assert nx.is_directed_acyclic_graph(g)

    # Every blocked issue can explain itself.
    blocked = issues[issues["status"] == "Blocked"]
    assert (blocked["blocked_by"].str.len() > 0).all()


def test_meta_shape(generated):
    _, meta = generated
    assert meta["project_name"]
    assert meta["current_sprint_id"] == CURRENT_SPRINT_ID
    assert meta["demo_today"]
    ids = {a["id"] for a in meta["anomalies"]}
    assert {"overload", "blocker_chain", "critical_epic"} <= ids
