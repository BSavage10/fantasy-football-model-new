"""Silver layer: team-week fact table.

Aggregate play-by-play data at the team-week level to produce
team_week_fact.parquet with offensive volume metrics, EPA, and
situational stats.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ffmodel.transform.team_dim import normalize_team_abbr

logger = logging.getLogger(__name__)

COLUMNS = [
    "team",
    "season",
    "week",
    "plays",
    "pass_plays",
    "rush_plays",
    "dropbacks",
    "sacks_allowed",
    "points_scored",
    "points_allowed",
    "drives",
    "red_zone_drives",
    "neutral_pass_rate",
    "epa_per_play",
]


def _compute_from_pbp(pbp: pd.DataFrame) -> pd.DataFrame:
    """Aggregate PBP data to team-week level."""
    # Filter to regular plays (no kickoffs, penalties-only, etc.)
    play_mask = pd.Series(True, index=pbp.index)

    if "play_type" in pbp.columns:
        valid_types = {"pass", "run", "qb_kneel", "qb_spike"}
        play_mask = pbp["play_type"].isin(valid_types)

    plays = pbp[play_mask].copy()

    # Ensure posteam (offensive team) exists
    if "posteam" not in plays.columns:
        raise ValueError("PBP data missing 'posteam' column")

    plays["posteam"] = plays["posteam"].apply(normalize_team_abbr)

    # ── Offensive play counts per team-week ─────────────────────────────
    is_pass = plays.get("pass", pd.Series(0, index=plays.index)).fillna(0).astype(bool)
    is_rush = plays.get("rush", pd.Series(0, index=plays.index)).fillna(0).astype(bool)
    is_sack = plays.get("sack", pd.Series(0, index=plays.index)).fillna(0).astype(bool)

    plays["_is_pass_play"] = is_pass | is_sack
    plays["_is_rush_play"] = is_rush
    plays["_is_sack"] = is_sack
    plays["_is_dropback"] = is_pass | is_sack

    # ── Neutral game state for pass rate ────────────────────────────────
    # Neutral = score margin ≤ 7, Q1–Q3
    score_diff = plays.get("score_differential", pd.Series(np.nan, index=plays.index))
    qtr = plays.get("qtr", pd.Series(0, index=plays.index))
    neutral_mask = (score_diff.abs() <= 7) & (qtr.between(1, 3))
    plays["_neutral"] = neutral_mask
    plays["_neutral_pass"] = neutral_mask & plays["_is_pass_play"]

    # ── Red zone drives ─────────────────────────────────────────────────
    yardline = plays.get("yardline_100", pd.Series(np.nan, index=plays.index))
    drive_col = plays.get("drive", pd.Series(np.nan, index=plays.index))
    plays["_is_red_zone"] = yardline <= 20

    # EPA
    epa_col = plays.get("epa", pd.Series(np.nan, index=plays.index))
    plays["_epa"] = epa_col

    # ── Group by team-season-week ───────────────────────────────────────
    grouped = plays.groupby(["posteam", "season", "week"])

    agg = grouped.agg(
        plays=("_is_pass_play", "size"),
        pass_plays=("_is_pass_play", "sum"),
        rush_plays=("_is_rush_play", "sum"),
        dropbacks=("_is_dropback", "sum"),
        sacks_allowed=("_is_sack", "sum"),
        neutral_plays=("_neutral", "sum"),
        neutral_pass_plays=("_neutral_pass", "sum"),
        epa_total=("_epa", "sum"),
    ).reset_index()

    agg = agg.rename(columns={"posteam": "team"})

    # Neutral pass rate
    agg["neutral_pass_rate"] = np.where(
        agg["neutral_plays"] > 0,
        agg["neutral_pass_plays"] / agg["neutral_plays"],
        np.nan,
    )
    agg["epa_per_play"] = np.where(
        agg["plays"] > 0,
        agg["epa_total"] / agg["plays"],
        np.nan,
    )

    # ── Red zone drives (distinct drives with a play at yardline_100 ≤ 20) ──
    rz_plays = plays[plays["_is_red_zone"]].copy()
    if "drive" in rz_plays.columns:
        rz_drives = (
            rz_plays.groupby(["posteam", "season", "week"])["drive"]
            .nunique()
            .reset_index()
            .rename(columns={"posteam": "team", "drive": "red_zone_drives"})
        )
        agg = agg.merge(rz_drives, on=["team", "season", "week"], how="left")
        agg["red_zone_drives"] = agg["red_zone_drives"].fillna(0).astype(int)
    else:
        agg["red_zone_drives"] = 0

    # ── Drives count ────────────────────────────────────────────────────
    if "drive" in plays.columns:
        drive_counts = (
            plays.groupby(["posteam", "season", "week"])["drive"]
            .nunique()
            .reset_index()
            .rename(columns={"posteam": "team", "drive": "drives"})
        )
        agg = agg.merge(drive_counts, on=["team", "season", "week"], how="left")
        agg["drives"] = agg["drives"].fillna(0).astype(int)
    else:
        agg["drives"] = 0

    return agg


def _add_scores(team_week: pd.DataFrame, raw_dir: Path) -> pd.DataFrame:
    """Add points_scored and points_allowed from the schedule."""
    sched_path = raw_dir / "schedules.parquet"
    if not sched_path.exists():
        team_week["points_scored"] = np.nan
        team_week["points_allowed"] = np.nan
        return team_week

    sched = pd.read_parquet(sched_path)

    # Normalize schedule team abbreviations
    for col in ["home_team", "away_team"]:
        if col in sched.columns:
            sched[col] = sched[col].apply(normalize_team_abbr)

    # Build home and away score mappings
    records = []
    for _, row in sched.iterrows():
        season = row.get("season")
        week = row.get("week")
        home = row.get("home_team")
        away = row.get("away_team")
        hs = row.get("home_score")
        aws = row.get("away_score")

        if pd.notna(hs) and pd.notna(aws):
            records.append({"team": home, "season": season, "week": week,
                            "points_scored": hs, "points_allowed": aws})
            records.append({"team": away, "season": season, "week": week,
                            "points_scored": aws, "points_allowed": hs})

    if records:
        scores_df = pd.DataFrame(records)
        scores_df["season"] = scores_df["season"].astype(int)
        scores_df["week"] = scores_df["week"].astype(int)
        team_week = team_week.merge(
            scores_df, on=["team", "season", "week"], how="left"
        )
    else:
        team_week["points_scored"] = np.nan
        team_week["points_allowed"] = np.nan

    return team_week


def build_team_week_fact(raw_dir: Path) -> pd.DataFrame:
    """Build team-week fact table from PBP + schedule data."""
    pbp_path = raw_dir / "pbp.parquet"
    if not pbp_path.exists():
        raise FileNotFoundError(f"Required source missing: {pbp_path}")

    pbp = pd.read_parquet(pbp_path)
    logger.info("Loaded pbp: %d rows", len(pbp))

    team_week = _compute_from_pbp(pbp)
    team_week = _add_scores(team_week, raw_dir)

    # ── Ensure all output columns + types ───────────────────────────────
    for col in COLUMNS:
        if col not in team_week.columns:
            team_week[col] = 0 if col in ("plays", "pass_plays", "rush_plays",
                                           "dropbacks", "sacks_allowed",
                                           "drives", "red_zone_drives") else np.nan

    int_cols = [
        "season", "week", "plays", "pass_plays", "rush_plays",
        "dropbacks", "sacks_allowed", "drives", "red_zone_drives",
    ]
    for col in int_cols:
        team_week[col] = pd.to_numeric(team_week[col], errors="coerce").fillna(0).astype(int)

    for col in ["points_scored", "points_allowed"]:
        team_week[col] = pd.to_numeric(team_week[col], errors="coerce")

    # ── Deduplicate ─────────────────────────────────────────────────────
    team_week = team_week.drop_duplicates(
        subset=["team", "season", "week"], keep="first"
    )
    team_week = team_week.sort_values(
        ["season", "week", "team"]
    ).reset_index(drop=True)

    # Drop temp columns
    result = team_week[[c for c in COLUMNS if c in team_week.columns]].copy()
    logger.info("team_week_fact: %d rows", len(result))
    return result


def write_team_week_fact(raw_dir: Path, silver_dir: Path) -> Path:
    """Build and write team_week_fact.parquet to the silver directory."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    df = build_team_week_fact(raw_dir)
    out_path = silver_dir / "team_week_fact.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
