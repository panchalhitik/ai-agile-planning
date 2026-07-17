"""Copilot tool layer: every tool must return JSON-serializable output, the
fallback router must answer every keyword class, and the tool-use loop must
terminate against a mocked client."""

from __future__ import annotations

import json
from datetime import date

import pytest

from data.generate_data import write_outputs
from src import data_loader
from src.ai import copilot


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("copilot_data")
    write_outputs(out)
    data = data_loader.load_data(out)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    today = date.fromisoformat(meta["demo_today"])
    return data, today


def test_every_tool_returns_json(demo):
    data, today = demo
    schemas, dispatch = build = copilot.build_tools(data, today)
    assert {s["name"] for s in schemas} == set(dispatch)
    for name, fn in dispatch.items():
        out = fn()
        json.dumps(out, default=str)  # must not raise
        assert out is not None, name


def test_tool_filters_and_caps(demo):
    data, today = demo
    _, dispatch = copilot.build_tools(data, today)
    result = dispatch["list_issues"](status="Blocked", limit=999)
    assert result["returned"] <= 50
    assert result["total_matches"] >= result["returned"]
    assert all(i["status"] == "Blocked" for i in result["issues"])

    unknown = dispatch["get_sprint_metrics"](sprint_id="S99")
    assert "error" in unknown

    one = dispatch["get_epic_progress"](epic_id="EPIC-101")
    assert len(one) == 1 and one[0]["epic_id"] == "EPIC-101"


@pytest.mark.parametrize(
    "question, expect",
    [
        ("Who is overloaded this sprint?", "overloaded"),
        ("What's blocking us?", "blocker"),
        ("Which epics are at risk?", "risk"),
        ("When will we finish the backlog?", "confidence"),
        ("How's our velocity trending?", "velocity"),
        ("Show me epic progress", "done"),
        ("How is the current sprint going?", "day"),
        ("hello there", "sprint health"),
    ],
)
def test_fallback_router_covers_keyword_classes(demo, question, expect):
    data, today = demo
    text, calls = copilot.fallback_answer(question, data, today)
    assert expect.lower() in text.lower()
    assert calls  # every answer is grounded in at least one tool


def test_fallback_names_the_seeded_anomalies(demo):
    data, today = demo
    overload, _ = copilot.fallback_answer("who is overloaded?", data, today)
    assert "Priya Sharma" in overload
    blockers, _ = copilot.fallback_answer("top blockers?", data, today)
    assert "NOVA-2107" in blockers


class _FakeBlock:
    def __init__(self, d):
        self._d = d

    def model_dump(self):
        return self._d


class _FakeResponse:
    def __init__(self, blocks, stop_reason):
        self.content = [_FakeBlock(b) for b in blocks]
        self.stop_reason = stop_reason


class _EndlessToolClient:
    """Always asks for another tool call — the loop must cut it off."""

    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        return _FakeResponse(
            [{"type": "tool_use", "id": f"t{self.calls}",
              "name": "get_headline_kpis", "input": {}}],
            "tool_use",
        )


class _OneToolThenText:
    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return _FakeResponse(
                [{"type": "tool_use", "id": "t1", "name": "get_velocity",
                  "input": {"window": 3}}],
                "tool_use",
            )
        # The tool_result from the previous round must be in the history.
        last = kwargs["messages"][-1]
        assert last["role"] == "user"
        assert last["content"][0]["type"] == "tool_result"
        return _FakeResponse(
            [{"type": "text", "text": "Velocity is fine."}], "end_turn"
        )


def test_loop_terminates_at_iteration_cap(demo):
    data, today = demo
    tools, dispatch = copilot.build_tools(data, today)
    client = _EndlessToolClient()
    result = copilot.run_anthropic_turn(
        client, "test-model", "sys", tools, dispatch,
        [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )
    assert client.calls == copilot.MAX_TOOL_ITERATIONS
    assert "limit" in result.text


def test_loop_round_trips_tool_results(demo):
    data, today = demo
    tools, dispatch = copilot.build_tools(data, today)
    seen: list[str] = []
    result = copilot.run_anthropic_turn(
        _OneToolThenText(), "test-model", "sys", tools, dispatch,
        [{"role": "user", "content": [{"type": "text", "text": "velocity?"}]}],
        on_tool=lambda name, args: seen.append(name),
    )
    assert result.text == "Velocity is fine."
    assert seen == ["get_velocity"]
    assert result.tool_calls == ["get_velocity"]
    # History alternates and is JSON-serializable for session storage.
    json.dumps(result.history)


def test_history_trim_drops_dangling_tool_results(demo, monkeypatch):
    data, today = demo
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # A history that starts with a tool_result fragment must be cleaned.
    dirty = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "{}"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "old answer"}]},
    ]
    result = copilot.answer("velocity?", dirty, data, "Test", today)
    assert result.source == "fallback"
    assert result.history[0]["role"] == "user"
    assert result.history[0]["content"][0]["type"] == "text"
