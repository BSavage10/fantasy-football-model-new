"""Gold layer: player role features.

Computes share-based opportunity features per player for the target season.
Handles recency weighting, team changers, and rookies.
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
    "team",
    "rush_share",
    "target_share",
    "starter_share_of_dropbacks",
    "qb_rush_attempts_per_game",
    "games_played",
    "is_rookie",
    "is_team_changer",
]

_ROOKIE_PRIORS = {
    "QB": {"rush_share": 0.0, "target_share": 0.0, "starter_share_of_dropbacks": 0.30, "qb_rush_attempts_per_game": 3.0},
    "RB": {"rush_share": 0.15, "target_share": 0.04, "starter_share_of_dropbacks": 0.0, "qb_rush_attempts_per_game": 0.0},
    "WR": {"rush_share": 0.01, "target_share": 0.10, "starter_share_of_dropbacks": 0.0, "qb_rush_attempts_per_game": 0.0},
    "TE": {"rush_share": 0.0, "target_share": 0.06, "starter_share_of_dropbacks": 0.0, "qb_rush_attempts_per_game": 0.0},
    "K":  {"rush_share": 0.0, "target_share": 0.0, "starter_share_of_dropbacks": 0.0, "qb_rush_attempts_per_game": 0.0},
}


def _compute_raw_shares(
    player_week: pd.DataFrame,
    team_week: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-player per-team-season share metrics."""
    player_season = player_week.groupby(
        ["canonical_player_id", "season", "team", "position"]
    ).agg(
        games_played=("games_played", "sum"),
        total_rush_att=("rush_att", "sum"),
        total_pass_att=("pass_att", "sum"),
        total_targets=("targets", "sum"),
    ).reset_index()

    team_season = team_week.groupby(["team", "season"]).agg(
        team_rush_plays=("rush_plays", "sum"),
        team_dropbacks=("dropbacks", "sum"),
        team_sacks=("sacks_allowed", "sum"),
    ).reset_index()

    team_season["team_pass_att"] = team_season["team_dropbacks"] - team_season["team_sacks"]

    merged = player_season.merge(team_season, on=["team", "season"], how="left")

    merged["rush_share"] = np.where(
        merged["team_rush_plays"] > 0,
        merged["total_rush_att"] / merged["team_rush_plays"],
        0.0,
    )
    merged["target_share"] = np.where(
        merged["team_pass_att"] > 0,
        merged["total_targets"] / merged["team_pass_att"],
        0.0,
    )
    merged["starter_share_of_dropbacks"] = np.where(
        (merged["position"] == "QB") & (merged["team_pass_att"] > 0),
        merged["total_pass_att"] / merged["team_pass_att"],
        0.0,
    )
    merged["qb_rush_attempts_per_game"] = np.where(
        (merged["position"] == "QB") & (merged["games_played"] > 0),
        merged["total_rush_att"] / merged["games_played"],
        0.0,
    )

    return merged


def _normalize_shares_within_team(df: pd.DataFrame) -> pd.DataFrame:
    """Cap rush_share and target_share sums to 1.0 per team via proportional scaling."""
    df = df.copy()
    for team in df["team"].dropna().unique():
        mask = (df["team"] == team) & (~df["is_rookie"])
        for col in ["rush_share", "target_share"]:
            total = df.loc[mask, col].sum()
            if total > 1.0:
                df.loc[mask, col] = df.loc[mask, col] / total
    return df


def _detect_team_changer(player_history: pd.DataFrame) -> bool:
    """A player is a team changer if their most recent team differs from prior."""
    if len(player_history) < 2:
        return False
    sorted_h = player_history.sort_values("season", ascending=False)
    latest_team = sorted_h.iloc[0]["team"]
    prior_team = sorted_h.iloc[1]["team"]
    return latest_team != prior_team


def build_player_role_features(
    player_week_fact: pd.DataFrame,
    team_week_fact: pd.DataFrame,
    player_dim: pd.DataFrame,
    target_season: int,
    recency_weights: dict[int, float],
    team_changer_config: dict,
) -> pd.DataFrame:
    """Build player role features for target season.

    Leakage gate: only uses seasons strictly before target_season.
    """
    pw = player_week_fact[player_week_fact["season"] < target_season].copy()
    tw = team_week_fact[team_week_fact["season"] < target_season].copy()

    if pw.empty:
        return pd.DataFrame(columns=COLUMNS)

    raw_shares = _compute_raw_shares(pw, tw)

    share_cols = ["rush_share", "target_share", "starter_share_of_dropbacks", "qb_rush_attempts_per_game"]

    players_with_history = raw_shares["canonical_player_id"].unique()

    all_players = player_dim[["canonical_player_id", "position"]].drop_duplicates("canonical_player_id")

    player_hist_weight = team_changer_config.get("player_history_weight", 0.70)
    team_prior_weight = team_changer_config.get("team_prior_weight", 0.30)

    results = []
    for _, player_row in all_players.iterrows():
        pid = player_row["canonical_player_id"]
        pos = player_row["position"]

        player_data = raw_shares[raw_shares["canonical_player_id"] == pid].sort_values(
            "season", ascending=False
        )

        is_rookie = pid not in players_with_history
        is_team_changer = False if is_rookie else _detect_team_changer(player_data)

        if is_rookie:
            priors = _ROOKIE_PRIORS.get(pos, _ROOKIE_PRIORS["WR"])
            latest_team = None
            for _, r in pw.drop_duplicates("canonical_player_id").iterrows():
                pass
            results.append({
                "canonical_player_id": pid,
                "season": target_season,
                "position": pos,
                "team": None,
                "rush_share": priors["rush_share"],
                "target_share": priors["target_share"],
                "starter_share_of_dropbacks": priors["starter_share_of_dropbacks"],
                "qb_rush_attempts_per_game": priors["qb_rush_attempts_per_game"],
                "games_played": 0,
                "is_rookie": True,
                "is_team_changer": False,
            })
            continue

        latest_team = player_data.iloc[0]["team"]

        weighted = {col: 0.0 for col in share_cols}
        total_weight = 0.0
        total_games = 0

        for _, row in player_data.iterrows():
            years_ago = target_season - int(row["season"])
            w = recency_weights.get(years_ago, 0.0)
            if w == 0.0:
                continue
            total_weight += w
            total_games += int(row["games_played"])
            for col in share_cols:
                weighted[col] += w * row[col]

        if total_weight > 0:
            for col in share_cols:
                weighted[col] /= total_weight

        if is_team_changer:
            pos_priors = _ROOKIE_PRIORS.get(pos, _ROOKIE_PRIORS["WR"])
            for col in share_cols:
                weighted[col] = (
                    player_hist_weight * weighted[col]
                    + team_prior_weight * pos_priors[col]
                )

        results.append({
            "canonical_player_id": pid,
            "season": target_season,
            "position": pos,
            "team": latest_team,
            "rush_share": weighted["rush_share"],
            "target_share": weighted["target_share"],
            "starter_share_of_dropbacks": weighted["starter_share_of_dropbacks"],
            "qb_rush_attempts_per_game": weighted["qb_rush_attempts_per_game"],
            "games_played": total_games,
            "is_rookie": False,
            "is_team_changer": is_team_changer,
        })

    df = pd.DataFrame(results, columns=COLUMNS)

    df = _normalize_shares_within_team(df)

    logger.info("player_role_features: %d rows for season %d", len(df), target_season)
    return df


def write_player_role_features(
    silver_dir: Path,
    gold_dir: Path,
    target_season: int,
    recency_weights: dict[int, float],
    team_changer_config: dict,
) -> Path:
    """Build and write player_role_features.parquet to the gold directory."""
    player_week = pd.read_parquet(silver_dir / "player_week_fact.parquet")
    team_week = pd.read_parquet(silver_dir / "team_week_fact.parquet")
    player_dim = pd.read_parquet(silver_dir / "player_dim.parquet")
    features = build_player_role_features(
        player_week, team_week, player_dim,
        target_season, recency_weights, team_changer_config,
    )
    gold_dir.mkdir(parents=True, exist_ok=True)
    out_path = gold_dir / "player_role_features.parquet"
    features.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
