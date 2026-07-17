"""Headless smoke test: every page must render without exceptions in the
default demo condition — no API key configured."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

PAGES = [
    "views/overview.py",
    "views/sprint.py",
    "views/epics_risk.py",
    "views/dependencies.py",
    "views/forecast.py",
    "views/copilot.py",
    "views/briefings.py",
    "views/data_hub.py",
]


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.switch_page(page)
    at.run()
    assert not at.exception, f"{page} raised: {at.exception}"


def test_copilot_answers_in_rules_mode():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.switch_page("views/copilot.py")
    at.run()
    at.chat_input[0].set_value("Who is overloaded this sprint?").run()
    assert not at.exception
    # The fallback answer lands in the transcript and names the anomaly.
    markdown = " ".join(str(m.value) for m in at.markdown)
    assert "Priya Sharma" in markdown


def test_briefing_generates_in_rules_mode():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.switch_page("views/briefings.py")
    at.run()
    at.button[0].click().run()
    assert not at.exception
