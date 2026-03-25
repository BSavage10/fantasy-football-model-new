"""Position models and projection orchestrator."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ffmodel.config import ModelConfig, ScoringConfig
from ffmodel.models.base import StatProjection, UncertaintyResult, compute_secondary_rates
from ffmodel.models.dst import project_dst
from ffmodel.models.kicker import project_kicker
from ffmodel.models.qb import project_qb
from ffmodel.models.rb import project_rb
from ffmodel.models.te import project_te
from ffmodel.models.uncertainty import compute_all_uncertainty
from ffmodel.models.wr import project_wr

logger = logging.getLogger(__name__)


def run_projections(
    team_context_df: pd.DataFrame,
    role_df: pd.DataFrame,
    efficiency_df: pd.DataFrame,
    availability_df: pd.DataFrame,
    player_week_fact: pd.DataFrame,
    team_week_fact: pd.DataFrame,
    scoring_config: ScoringConfig,
    model_config: ModelConfig,
    target_season: int,
) -> list[StatProjection]:
    """Run all position projectors and return combined projections."""
    secondary_rates = compute_secondary_rates(
        player_week_fact, target_season, model_config.recency_weights,
    )

    projections: list[StatProjection] = []
    projections.extend(project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
    projections.extend(project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
    projections.extend(project_wr(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
    projections.extend(project_te(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
    projections.extend(project_dst(team_context_df, team_week_fact, scoring_config, model_config, target_season))
    projections.extend(project_kicker(team_context_df, team_week_fact, model_config, target_season))

    logger.info("run_projections: %d total projections", len(projections))
    return projections


def projections_to_dataframe(projections: list[StatProjection]) -> pd.DataFrame:
    """Flatten StatProjection list into a DataFrame for Parquet output."""
    records = []
    for p in projections:
        row: dict = {
            "player_id": p.player_id,
            "position": p.position,
            "games_active": p.games_active,
            "is_rookie": p.is_rookie,
            "is_team_changer": p.is_team_changer,
        }
        for k, v in p.per_game.items():
            row[f"{k}_per_game"] = v
        for k, v in p.season_total.items():
            row[f"{k}_season_total"] = v
        row["reason_codes"] = ",".join(p.reason_codes)
        row["qc_flags"] = ",".join(p.qc_flags)
        records.append(row)
    return pd.DataFrame(records)
