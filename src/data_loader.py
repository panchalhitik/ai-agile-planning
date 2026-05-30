"""Load CSV data and provide a typed bundle for the rest of the app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class AgileData:
    sprints: pd.DataFrame
    team: pd.DataFrame
    epics: pd.DataFrame
    issues: pd.DataFrame


def _parse_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    return df


def load_data(data_dir: Path | None = None) -> AgileData:
    base = Path(data_dir) if data_dir else DATA_DIR
    sprints = _parse_dates(pd.read_csv(base / "sprints.csv"), ["start_date", "end_date"])
    team = pd.read_csv(base / "team.csv")
    epics = pd.read_csv(base / "epics.csv")
    issues = _parse_dates(
        pd.read_csv(base / "issues.csv"), ["created_at", "updated_at"]
    )
    # Tidy types
    issues["story_points"] = issues["story_points"].fillna(0).astype(int)
    issues["blocked_by"] = issues["blocked_by"].fillna("").astype(str)
    return AgileData(sprints=sprints, team=team, epics=epics, issues=issues)


def ensure_data_exists() -> bool:
    """Return True if all expected CSVs are present."""
    needed = ["sprints.csv", "team.csv", "epics.csv", "issues.csv"]
    return all((DATA_DIR / f).exists() for f in needed)
