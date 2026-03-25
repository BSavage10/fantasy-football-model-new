"""Baseline projection models for comparison.

Two challenger baselines:
  baseline_weighted_history — recency-weighted average of historical fantasy points
  baseline_last_year       — last season's actual fantasy points
"""

from __future__ import annotations

import pandas as pd

from ffmodel.config import ScoringConfig
from ffmodel.scoring.engine import score_player


def _score_player_season(row: pd.Series, scoring_config: ScoringConfig) -> float:
    """Score a player-season aggregate row using the scoring engine."""
    stats = {
        "pass_yd": row.get("pass_yd", 0.0),
        "pass_td": row.get("pass_td", 0.0),
        "interceptions": row.get("interceptions", 0.0),
        "rush_yd": row.get("rush_yd", 0.0),
        "rush_td": row.get("rush_td", 0.0),
        "receptions": row.get("receptions", 0.0),
        "rec_yd": row.get("rec_yd", 0.0),
        "rec_td": row.get("rec_td", 0.0),
        "fumbles_lost": row.get("fumbles_lost", 0.0),
        "return_td": row.get("return_td", 0.0),
        "two_pt_conv": row.get("two_pt_conv", 0.0),
    }
    return score_player(stats, str(row["position"]), scoring_config)


def _aggregate_player_seasons(player_week_fact: pd.DataFrame) -> pd.DataFrame:
    """Aggregate player_week_fact to player-season level."""
    return player_week_fact.groupby(
        ["canonical_player_id", "season", "position"],
    ).agg(
        games=("games_played", "sum"),
        pass_yd=("pass_yd", "sum"),
        pass_td=("pass_td", "sum"),
        interceptions=("interceptions", "sum"),
        rush_yd=("rush_yd", "sum"),
        rush_td=("rush_td", "sum"),
        receptions=("receptions", "sum"),
        rec_yd=("rec_yd", "sum"),
        rec_td=("rec_td", "sum"),
        fumbles_lost=("fumbles_lost", "sum"),
        return_td=("return_td", "sum"),
        two_pt_conv=("two_pt_conv", "sum"),
    ).reset_index()


def baseline_weighted_history(
    player_week_fact: pd.DataFrame,
    target_season: int,
    scoring_config: ScoringConfig,
    weights: dict[int, float],
) -> pd.DataFrame:
    """Baseline: weighted average of historical fantasy points.

    Returns DataFrame with columns: player_id, position, fantasy_points_proj
    """
    pw = player_week_fact[player_week_fact["season"] < target_season].copy()
    if pw.empty:
        return pd.DataFrame(columns=["player_id", "position", "fantasy_points_proj"])

    player_season = _aggregate_player_seasons(pw)

    results = []
    for pid in player_season["canonical_player_id"].unique():
        pdata = player_season[player_season["canonical_player_id"] == pid].sort_values(
            "season", ascending=False,
        )
        pos = str(pdata.iloc[0]["position"])

        total_weight = 0.0
        weighted_pts = 0.0

        for _, row in pdata.iterrows():
            years_ago = target_season - int(row["season"])
            w = weights.get(years_ago, 0.0)
            if w == 0.0:
                continue
            total_weight += w
            weighted_pts += w * _score_player_season(row, scoring_config)

        if total_weight > 0:
            weighted_pts /= total_weight
            results.append({
                "player_id": pid,
                "position": pos,
                "fantasy_points_proj": weighted_pts,
            })

    return pd.DataFrame(results)


def baseline_last_year(
    player_week_fact: pd.DataFrame,
    target_season: int,
    scoring_config: ScoringConfig,
) -> pd.DataFrame:
    """Baseline: last season's actual fantasy points.

    Returns DataFrame with columns: player_id, position, fantasy_points_proj
    """
    last_season = target_season - 1
    pw = player_week_fact[player_week_fact["season"] == last_season].copy()
    if pw.empty:
        return pd.DataFrame(columns=["player_id", "position", "fantasy_points_proj"])

    player_season = _aggregate_player_seasons(pw)

    results = []
    for _, row in player_season.iterrows():
        pts = _score_player_season(row, scoring_config)
        results.append({
            "player_id": row["canonical_player_id"],
            "position": str(row["position"]),
            "fantasy_points_proj": pts,
        })

    return pd.DataFrame(results)
