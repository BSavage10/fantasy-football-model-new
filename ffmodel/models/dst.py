"""DST position projector.

Lighter-weight model (AD-5): uses historical points-allowed with recency
weighting and league-average defensive counting stats scaled by a team
quality factor derived from PA relative to league average.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ffmodel.config import ModelConfig, ScoringConfig
from ffmodel.models.base import StatProjection, make_season_totals, recency_weighted_avg
from ffmodel.scoring.engine import expected_pa_bracket_value

# League-average defensive stats per game
_LEAGUE_SACKS = 2.5
_LEAGUE_INTS = 0.9
_LEAGUE_FR = 0.7
_LEAGUE_DST_TD = 0.12
_LEAGUE_SAFETIES = 0.02
_LEAGUE_BLOCKS = 0.05
_LEAGUE_RET_TD = 0.05
_LEAGUE_XP_RET = 0.005


def project_dst(
    team_context_df: pd.DataFrame,
    team_week_fact: pd.DataFrame,
    scoring_config: ScoringConfig,
    model_config: ModelConfig,
    target_season: int,
) -> list[StatProjection]:
    """Project DST stats for each team in team_context_df."""
    hist = team_week_fact[team_week_fact["season"] < target_season].copy()
    if hist.empty:
        return []

    team_season = hist.groupby(["team", "season"]).agg(
        points_allowed=("points_allowed", "sum"),
        games=("week", "count"),
    ).reset_index()
    team_season["pa_pg"] = team_season["points_allowed"] / team_season["games"]

    league_avg_pa = float(team_season["pa_pg"].mean()) if len(team_season) > 0 else 22.0

    # Per-team weekly PA std for Monte Carlo bracket value
    team_pa_std = hist.groupby("team")["points_allowed"].std().to_dict()

    projections: list[StatProjection] = []

    for team in team_context_df["team"].unique():
        td = team_season[team_season["team"] == team].sort_values("season", ascending=False)

        pa_pg = recency_weighted_avg(td, "pa_pg", target_season, model_config.recency_weights)
        if pa_pg is None:
            pa_pg = league_avg_pa

        pa_std = team_pa_std.get(team, 7.0)

        # Quality factor: lower PA → better defense → more counting stats
        quality = (league_avg_pa / pa_pg) ** 0.5 if pa_pg > 0 else 1.0

        bracket_value = expected_pa_bracket_value(
            pa_pg, pa_std, scoring_config.dst.points_allowed_brackets,
        )

        per_game = {
            "sacks": float(_LEAGUE_SACKS * quality),
            "interceptions": float(_LEAGUE_INTS * quality),
            "fumble_recoveries": float(_LEAGUE_FR * quality),
            "dst_td": float(_LEAGUE_DST_TD * quality),
            "safeties": float(_LEAGUE_SAFETIES * quality),
            "block_kicks": float(_LEAGUE_BLOCKS * quality),
            "return_tds": float(_LEAGUE_RET_TD * quality),
            "extra_point_returns": float(_LEAGUE_XP_RET * quality),
            "points_allowed": float(pa_pg),
            "points_allowed_bracket_value": float(bracket_value),
        }

        games_active = 17.0
        reasons = ["league_avg_counting_stats"]

        projections.append(StatProjection(
            per_game=per_game,
            season_total=make_season_totals(per_game, games_active),
            games_active=games_active,
            position="DEF",
            player_id=team,
            reason_codes=reasons,
        ))

    return projections
