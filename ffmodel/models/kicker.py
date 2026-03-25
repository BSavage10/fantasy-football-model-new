"""Kicker position projector.

Lighter-weight model (AD-5): estimates XP and FG volume from team
scoring rate, distributes FGs across distance buckets using
league-average proportions.
"""

from __future__ import annotations

import pandas as pd

from ffmodel.config import ModelConfig
from ffmodel.models.base import StatProjection, make_season_totals, recency_weighted_avg

# League-average kicker stats per game
_LEAGUE_XP_PG = 3.0
_LEAGUE_FG_PG = 1.85

# League-average FG distance distribution
_FG_DIST = {
    "fg_0_19": 0.03,
    "fg_20_29": 0.22,
    "fg_30_39": 0.30,
    "fg_40_49": 0.28,
    "fg_50_plus": 0.17,
}


def project_kicker(
    team_context_df: pd.DataFrame,
    team_week_fact: pd.DataFrame,
    model_config: ModelConfig,
    target_season: int,
) -> list[StatProjection]:
    """Project kicker stats for each team in team_context_df."""
    hist = team_week_fact[team_week_fact["season"] < target_season].copy()
    if hist.empty:
        return []

    team_season = hist.groupby(["team", "season"]).agg(
        points_scored=("points_scored", "sum"),
        games=("week", "count"),
    ).reset_index()
    team_season["ppg"] = team_season["points_scored"] / team_season["games"]

    league_avg_ppg = float(team_season["ppg"].mean()) if len(team_season) > 0 else 22.0

    projections: list[StatProjection] = []

    for team in team_context_df["team"].unique():
        td = team_season[team_season["team"] == team].sort_values("season", ascending=False)

        ppg = recency_weighted_avg(td, "ppg", target_season, model_config.recency_weights)
        if ppg is None:
            ppg = league_avg_ppg

        scoring_factor = ppg / league_avg_ppg if league_avg_ppg > 0 else 1.0

        xp_pg = _LEAGUE_XP_PG * scoring_factor * 0.95
        fg_pg = _LEAGUE_FG_PG * scoring_factor

        per_game: dict[str, float] = {"pat_made": float(xp_pg)}
        for bucket, pct in _FG_DIST.items():
            per_game[bucket] = float(fg_pg * pct)

        games_active = 17.0

        projections.append(StatProjection(
            per_game=per_game,
            season_total=make_season_totals(per_game, games_active),
            games_active=games_active,
            position="K",
            player_id=team,
            reason_codes=["league_avg_distribution"],
        ))

    return projections
