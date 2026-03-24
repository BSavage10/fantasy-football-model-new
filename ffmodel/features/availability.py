"""Gold layer: availability features.

Projects games_active per player for the target season using weighted
historical games-played, age discounts, and position-based shrinkage.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = [
    "canonical_player_id",
    "season",
    "position",
    "games_played_y1",
    "games_played_y2",
    "games_played_y3",
    "career_games_played",
    "age_at_season_start",
    "years_pro",
    "games_active_proj",
]

_AGE_DISCOUNT_THRESHOLDS = {
    "QB": 37,
    "RB": 28,
    "WR": 31,
    "TE": 31,
    "K": 38,
}

_AGE_DISCOUNT_PER_YEAR = 0.5


def build_availability_features(
    player_week_fact: pd.DataFrame,
    player_dim: pd.DataFrame,
    target_season: int,
    recency_weights: dict[int, float],
    games_active_config: dict,
) -> pd.DataFrame:
    """Build availability features for target season.

    Leakage gate: only uses seasons strictly before target_season.
    """
    pw = player_week_fact[player_week_fact["season"] < target_season].copy()

    if pw.empty:
        return pd.DataFrame(columns=COLUMNS)

    default_max = games_active_config.get("default_max", 17)
    shrinkage = games_active_config.get("shrinkage", 0.20)
    position_prior = games_active_config.get("position_prior", {})

    games_per_season = pw.groupby(
        ["canonical_player_id", "season"]
    ).agg(
        games_played=("games_played", "sum"),
    ).reset_index()

    career_games = games_per_season.groupby("canonical_player_id").agg(
        career_total=("games_played", "sum"),
    ).reset_index()

    players = player_dim[["canonical_player_id", "position", "birth_date", "entry_year"]].copy()
    players = players.drop_duplicates("canonical_player_id")

    results = []
    for _, player in players.iterrows():
        pid = player["canonical_player_id"]
        pos = player["position"]

        player_games = games_per_season[
            games_per_season["canonical_player_id"] == pid
        ].sort_values("season", ascending=False)

        gp_y1 = None
        gp_y2 = None
        gp_y3 = None

        for _, row in player_games.iterrows():
            years_ago = target_season - int(row["season"])
            if years_ago == 1:
                gp_y1 = int(row["games_played"])
            elif years_ago == 2:
                gp_y2 = int(row["games_played"])
            elif years_ago == 3:
                gp_y3 = int(row["games_played"])

        career = career_games.loc[
            career_games["canonical_player_id"] == pid, "career_total"
        ]
        career_gp = int(career.iloc[0]) if len(career) > 0 else 0

        entry_year = player["entry_year"]
        if pd.notna(entry_year):
            years_pro = target_season - int(entry_year)
        else:
            years_pro = 0

        age = None
        if pd.notna(player["birth_date"]):
            try:
                bd = pd.Timestamp(player["birth_date"])
                age = target_season - bd.year
            except Exception:
                pass

        weighted_games = 0.0
        total_weight = 0.0
        for yr_ago, gp in [(1, gp_y1), (2, gp_y2), (3, gp_y3)]:
            if gp is not None:
                w = recency_weights.get(yr_ago, 0.0)
                weighted_games += w * gp
                total_weight += w

        if total_weight > 0:
            raw_proj = weighted_games / total_weight
        else:
            raw_proj = position_prior.get(pos, 15.0)

        pos_avg = position_prior.get(pos, 15.0)
        proj = (1 - shrinkage) * raw_proj + shrinkage * pos_avg

        if age is not None:
            threshold = _AGE_DISCOUNT_THRESHOLDS.get(pos, 33)
            if age > threshold:
                discount = (age - threshold) * _AGE_DISCOUNT_PER_YEAR
                proj = proj - discount

        proj = max(0.0, min(proj, float(default_max)))

        results.append({
            "canonical_player_id": pid,
            "season": target_season,
            "position": pos,
            "games_played_y1": gp_y1,
            "games_played_y2": gp_y2,
            "games_played_y3": gp_y3,
            "career_games_played": career_gp,
            "age_at_season_start": age,
            "years_pro": years_pro,
            "games_active_proj": round(proj, 1),
        })

    df = pd.DataFrame(results, columns=COLUMNS)
    logger.info("availability_features: %d rows for season %d", len(df), target_season)
    return df


def write_availability_features(
    silver_dir: Path,
    gold_dir: Path,
    target_season: int,
    recency_weights: dict[int, float],
    games_active_config: dict,
) -> Path:
    """Build and write availability_features.parquet to the gold directory."""
    player_week = pd.read_parquet(silver_dir / "player_week_fact.parquet")
    player_dim = pd.read_parquet(silver_dir / "player_dim.parquet")
    features = build_availability_features(
        player_week, player_dim, target_season, recency_weights, games_active_config,
    )
    gold_dir.mkdir(parents=True, exist_ok=True)
    out_path = gold_dir / "availability_features.parquet"
    features.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
