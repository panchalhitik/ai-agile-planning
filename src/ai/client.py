"""Anthropic client + key/model resolution.

The key is looked up in the environment first, then Streamlit secrets. The
model defaults to Haiku (fast + cheap for chat) and can be overridden with
AGILE_AI_MODEL. Everything degrades to None so callers can fall back to the
deterministic rules mode — the demo must never crash without a key.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-haiku-4-5"


def _secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name) or None
    except Exception:
        return None


def get_api_key() -> str | None:
    return _secret("ANTHROPIC_API_KEY")


def get_model() -> str:
    return _secret("AGILE_AI_MODEL") or DEFAULT_MODEL


def ai_available() -> bool:
    return get_api_key() is not None


def get_client():
    """An Anthropic client, or None when no key is configured."""
    key = get_api_key()
    if not key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=key)
