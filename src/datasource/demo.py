"""Demo source: the Nova Commerce narrative dataset."""

from __future__ import annotations

import json
from datetime import date

from src import data_loader
from src.data_loader import DATA_DIR, AgileData


def load_demo() -> tuple[AgileData, dict]:
    if not data_loader.ensure_data_exists():
        from data.generate_data import write_outputs

        write_outputs()
    data = data_loader.load_data()

    meta_path = DATA_DIR / "meta.json"
    raw = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta = {
        "name": raw.get("project_name", "Demo"),
        "project_name": raw.get("project_name", "Demo project"),
        "codename": raw.get("project_codename", ""),
        "blurb": raw.get("blurb", ""),
        "anomalies": raw.get("anomalies", []),
        # Frozen so the demo is deterministic forever.
        "today": date.fromisoformat(raw["demo_today"]) if "demo_today" in raw else date.today(),
        "current_sprint_id": raw.get("current_sprint_id"),
    }
    return data, meta


def regenerate_demo() -> None:
    from data.generate_data import write_outputs

    write_outputs()
