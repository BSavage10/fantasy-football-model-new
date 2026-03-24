"""Silver layer: schedule fact table.

Raw schedules → schedule_fact.parquet with one row per game,
standardized team abbreviations, and spread/total lines.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ffmodel.transform.team_dim import normalize_team_abbr

logger = logging.getLogger(__name__)

COLUMNS = [
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "game_date",
    "spread_line",
    "total_line",
    "home_score",
    "away_score",
]


def build_schedule_fact(raw_dir: Path) -> pd.DataFrame:
    """Build the schedule fact table from raw schedules."""
    path = raw_dir / "schedules.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Required source missing: {path}")

    sched = pd.read_parquet(path)
    logger.info("Loaded schedules: %d rows", len(sched))

    # ── Map to canonical columns ────────────────────────────────────────
    result = pd.DataFrame()

    result["game_id"] = sched["game_id"]
    result["season"] = sched["season"].astype(int)
    result["week"] = sched["week"].astype(int)
    result["home_team"] = sched["home_team"].apply(normalize_team_abbr)
    result["away_team"] = sched["away_team"].apply(normalize_team_abbr)

    # Game date
    if "gameday" in sched.columns:
        result["game_date"] = pd.to_datetime(sched["gameday"], errors="coerce")
    elif "game_date" in sched.columns:
        result["game_date"] = pd.to_datetime(sched["game_date"], errors="coerce")
    else:
        result["game_date"] = pd.NaT

    # Spread and total lines
    result["spread_line"] = pd.to_numeric(sched.get("spread_line"), errors="coerce")
    result["total_line"] = pd.to_numeric(
        sched.get("total_line", sched.get("total")), errors="coerce"
    )

    # Scores (null for future games)
    result["home_score"] = pd.to_numeric(sched.get("home_score"), errors="coerce")
    result["away_score"] = pd.to_numeric(sched.get("away_score"), errors="coerce")

    # ── Filter to regular season + postseason (no preseason) ────────────
    result = result[result["week"] <= 22].copy()

    # ── Deduplicate on game_id ──────────────────────────────────────────
    result = result.drop_duplicates(subset=["game_id"], keep="first")
    result = result.sort_values(["season", "week", "game_id"]).reset_index(drop=True)

    logger.info("schedule_fact: %d rows", len(result))
    return result[COLUMNS]


def write_schedule_fact(raw_dir: Path, silver_dir: Path) -> Path:
    """Build and write schedule_fact.parquet to the silver directory."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    df = build_schedule_fact(raw_dir)
    out_path = silver_dir / "schedule_fact.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
