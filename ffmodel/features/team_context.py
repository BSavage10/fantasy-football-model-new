"""Gold layer: team context features.

Aggregate team_week_fact by season, then apply recency-weighted averages
across prior seasons to produce one projected row per team for the target season.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = [
    "team",
    "season",
    "team_plays_proj",
    "team_dropbacks_proj",
    "team_rushes_proj",
    "team_targets_proj",
    "neutral_pass_rate_proj",
    "proe_proj",
    "red_zone_drives_per_game_proj",
    "points_per_drive_proj",
    "epa_per_play_proj",
]

_PER_GAME_METRICS = [
    "plays_pg",
    "dropbacks_pg",
    "rushes_pg",
    "targets_pg",
    "neutral_pass_rate",
    "rz_drives_pg",
    "ppd",
    "epa_pp",
]


def _aggregate_team_seasons(team_week: pd.DataFrame) -> pd.DataFrame:
    """Aggregate team_week_fact to per-game averages per team-season."""
    agg = team_week.groupby(["team", "season"]).agg(
        games=("week", "count"),
        total_plays=("plays", "sum"),
        total_dropbacks=("dropbacks", "sum"),
        total_rushes=("rush_plays", "sum"),
        total_sacks=("sacks_allowed", "sum"),
        total_points=("points_scored", "sum"),
        total_drives=("drives", "sum"),
        total_rz_drives=("red_zone_drives", "sum"),
        neutral_pass_rate=("neutral_pass_rate", "mean"),
        epa_pp=("epa_per_play", "mean"),
    ).reset_index()

    agg["plays_pg"] = agg["total_plays"] / agg["games"]
    agg["dropbacks_pg"] = agg["total_dropbacks"] / agg["games"]
    agg["rushes_pg"] = agg["total_rushes"] / agg["games"]
    agg["targets_pg"] = (agg["total_dropbacks"] - agg["total_sacks"]) / agg["games"]
    agg["rz_drives_pg"] = agg["total_rz_drives"] / agg["games"]
    agg["ppd"] = np.where(
        agg["total_drives"] > 0,
        agg["total_points"] / agg["total_drives"],
        np.nan,
    )

    return agg


def build_team_context_features(
    team_week_fact: pd.DataFrame,
    target_season: int,
    recency_weights: dict[int, float],
) -> pd.DataFrame:
    """Build team context features for target season.

    Leakage gate: only uses seasons strictly before target_season.
    """
    hist = team_week_fact[team_week_fact["season"] < target_season].copy()

    if hist.empty:
        return pd.DataFrame(columns=COLUMNS)

    team_season = _aggregate_team_seasons(hist)

    league_avgs = {col: team_season[col].mean() for col in _PER_GAME_METRICS}

    results = []
    for team in team_season["team"].unique():
        team_data = team_season[team_season["team"] == team].sort_values(
            "season", ascending=False
        )

        weighted = {col: 0.0 for col in _PER_GAME_METRICS}
        total_weight = 0.0

        for _, row in team_data.iterrows():
            years_ago = target_season - int(row["season"])
            w = recency_weights.get(years_ago, 0.0)
            if w == 0.0:
                continue
            total_weight += w
            for col in _PER_GAME_METRICS:
                val = row[col]
                if pd.notna(val):
                    weighted[col] += w * val

        if total_weight > 0:
            for col in _PER_GAME_METRICS:
                weighted[col] /= total_weight

        seasons_available = len(team_data[
            team_data["season"] >= target_season - len(recency_weights)
        ])
        max_seasons = len(recency_weights)
        if seasons_available < max_seasons:
            shrink = seasons_available / max_seasons
            for col in _PER_GAME_METRICS:
                weighted[col] = (
                    shrink * weighted[col] + (1 - shrink) * league_avgs[col]
                )

        results.append({
            "team": team,
            "season": target_season,
            "team_plays_proj": weighted["plays_pg"],
            "team_dropbacks_proj": weighted["dropbacks_pg"],
            "team_rushes_proj": weighted["rushes_pg"],
            "team_targets_proj": weighted["targets_pg"],
            "neutral_pass_rate_proj": weighted["neutral_pass_rate"],
            "proe_proj": weighted["neutral_pass_rate"] - league_avgs["neutral_pass_rate"],
            "red_zone_drives_per_game_proj": weighted["rz_drives_pg"],
            "points_per_drive_proj": weighted["ppd"],
            "epa_per_play_proj": weighted["epa_pp"],
        })

    df = pd.DataFrame(results, columns=COLUMNS)
    logger.info("team_context_features: %d rows for season %d", len(df), target_season)
    return df


def write_team_context_features(
    silver_dir: Path,
    gold_dir: Path,
    target_season: int,
    recency_weights: dict[int, float],
) -> Path:
    """Build and write team_context_features.parquet to the gold directory."""
    team_week = pd.read_parquet(silver_dir / "team_week_fact.parquet")
    features = build_team_context_features(team_week, target_season, recency_weights)
    gold_dir.mkdir(parents=True, exist_ok=True)
    out_path = gold_dir / "team_context_features.parquet"
    features.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
