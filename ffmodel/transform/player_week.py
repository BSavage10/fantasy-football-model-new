"""Silver layer: player-week fact table.

Raw weekly stats → player_week_fact.parquet with one row per
player-team-week, all counting stats normalized.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ffmodel.transform.team_dim import normalize_team_abbr

logger = logging.getLogger(__name__)

COLUMNS = [
    "canonical_player_id",
    "season",
    "week",
    "team",
    "position",
    "games_played",
    "pass_att",
    "pass_cmp",
    "pass_yd",
    "pass_td",
    "interceptions",
    "rush_att",
    "rush_yd",
    "rush_td",
    "targets",
    "receptions",
    "rec_yd",
    "rec_td",
    "fumbles_lost",
    "two_pt_conv",
    "return_td",
    "sacks_taken",
]

# nflverse weekly data column mapping → our canonical names
_WEEKLY_COL_MAP = {
    "player_id": "canonical_player_id",
    "recent_team": "team",
    "completions": "pass_cmp",
    "attempts": "pass_att",
    "passing_yards": "pass_yd",
    "passing_tds": "pass_td",
    "interceptions": "interceptions",
    "carries": "rush_att",
    "rushing_yards": "rush_yd",
    "rushing_tds": "rush_td",
    "targets": "targets",
    "receptions": "receptions",
    "receiving_yards": "rec_yd",
    "receiving_tds": "rec_td",
    "fumbles_lost": "fumbles_lost",
    "passing_2pt_conversions": "pass_2pt",
    "rushing_2pt_conversions": "rush_2pt",
    "receiving_2pt_conversions": "rec_2pt",
    "sacks": "sacks_taken",
}


def build_player_week_fact(raw_dir: Path) -> pd.DataFrame:
    """Build the player-week fact table from raw weekly stats."""
    path = raw_dir / "weekly_stats.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Required source missing: {path}")

    weekly = pd.read_parquet(path)
    logger.info("Loaded weekly_stats: %d rows", len(weekly))

    # ── Filter to relevant positions ────────────────────────────────────
    relevant_positions = {"QB", "RB", "WR", "TE", "K", "FB"}
    if "position" in weekly.columns:
        weekly = weekly[weekly["position"].isin(relevant_positions)].copy()

    # ── Rename columns ──────────────────────────────────────────────────
    rename_map = {k: v for k, v in _WEEKLY_COL_MAP.items() if k in weekly.columns}
    weekly = weekly.rename(columns=rename_map)

    # ── Normalize team abbreviations ────────────────────────────────────
    if "team" in weekly.columns:
        weekly["team"] = weekly["team"].apply(normalize_team_abbr)

    # ── Compute derived fields ──────────────────────────────────────────
    # two_pt_conv = sum of all 2pt conversion types
    two_pt_cols = [c for c in ["pass_2pt", "rush_2pt", "rec_2pt"] if c in weekly.columns]
    if two_pt_cols:
        weekly["two_pt_conv"] = weekly[two_pt_cols].fillna(0).sum(axis=1).astype(int)
    elif "two_pt_conv" not in weekly.columns:
        weekly["two_pt_conv"] = 0

    # return_td: special teams return touchdowns
    if "special_teams_tds" in weekly.columns:
        weekly["return_td"] = weekly["special_teams_tds"].fillna(0).astype(int)
    elif "return_td" not in weekly.columns:
        weekly["return_td"] = 0

    # games_played: 1 if the player had any stats in that week, else 0
    stat_cols = ["pass_att", "rush_att", "targets", "receptions", "pass_cmp"]
    available_stat_cols = [c for c in stat_cols if c in weekly.columns]
    if available_stat_cols:
        weekly["games_played"] = (weekly[available_stat_cols].fillna(0).sum(axis=1) > 0).astype(int)
    else:
        weekly["games_played"] = 1

    # ── Ensure canonical_player_id exists ───────────────────────────────
    if "canonical_player_id" not in weekly.columns:
        if "player_id" in weekly.columns:
            weekly["canonical_player_id"] = weekly["player_id"]
        else:
            raise ValueError("weekly_stats missing player_id / canonical_player_id")

    # Drop rows without a valid player ID
    weekly = weekly.dropna(subset=["canonical_player_id"]).copy()

    # ── Ensure all output columns exist with correct types ──────────────
    for col in COLUMNS:
        if col not in weekly.columns:
            weekly[col] = 0 if col not in ("canonical_player_id", "team", "position") else None

    int_cols = [
        "season", "week", "games_played", "pass_att", "pass_cmp", "pass_td",
        "interceptions", "rush_att", "rush_td", "targets", "receptions",
        "rec_td", "fumbles_lost", "two_pt_conv", "return_td", "sacks_taken",
    ]
    for col in int_cols:
        weekly[col] = pd.to_numeric(weekly[col], errors="coerce").fillna(0).astype(int)

    float_cols = ["pass_yd", "rush_yd", "rec_yd"]
    for col in float_cols:
        weekly[col] = pd.to_numeric(weekly[col], errors="coerce").fillna(0.0)

    # ── Deduplicate on (canonical_player_id, season, week, team) ────────
    weekly = weekly.drop_duplicates(
        subset=["canonical_player_id", "season", "week", "team"], keep="first"
    )
    weekly = weekly.sort_values(
        ["season", "week", "canonical_player_id"]
    ).reset_index(drop=True)

    result = weekly[COLUMNS].copy()
    logger.info("player_week_fact: %d rows", len(result))
    return result


def write_player_week_fact(raw_dir: Path, silver_dir: Path) -> Path:
    """Build and write player_week_fact.parquet to the silver directory."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    df = build_player_week_fact(raw_dir)
    out_path = silver_dir / "player_week_fact.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
