"""Full-page AI copilot chat."""

from __future__ import annotations

from src.ui import components as ui
from src.ui.chat import render_copilot

ui.page_header(
    "Copilot",
    "Ask anything about the plan — every number is computed by tools, not the model.",
)
render_copilot(embedded=False)
