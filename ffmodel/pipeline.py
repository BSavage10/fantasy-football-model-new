"""Full pipeline orchestrator: ingest → transform → features → project → overlay → rank → QA → export.

Each step checks for cached results (idempotent). The run_id format is:
    {as_of_date}_{YYYYMMDD_HHMMSS}_{config_hash[:8]}
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ffmodel.config import ProjectConfig

logger = logging.getLogger(__name__)


def generate_run_id(as_of_date: str, config_hash: str) -> str:
    """Generate a unique run ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{as_of_date}_{ts}_{config_hash[:8]}"


def run_pipeline(
    config: ProjectConfig,
    as_of_date: str,
    data_dir: str = "data",
    output_dir: str = "outputs",
    manual_dir: str = "manual",
) -> Path:
    """Execute the full pipeline end-to-end.

    Returns the output directory path for this run.
    """
    from ffmodel.export.writer import write_outputs
    from ffmodel.ingest.snapshot import run_ingest
    from ffmodel.models import (
        compute_all_uncertainty,
        projections_to_dataframe,
        run_projections,
    )
    from ffmodel.overlay.applicator import apply_overlays
    from ffmodel.qa.checks import run_all_checks
    from ffmodel.ranking.ranker import compute_rankings

    data_path = Path(data_dir)
    raw_dir = data_path / "raw" / as_of_date
    silver_dir = data_path / "silver" / as_of_date
    gold_dir = data_path / "gold" / as_of_date

    # Step 1: Ingest
    if not (raw_dir / "_manifest.json").exists():
        logger.info("Running ingest...")
        run_ingest(config.sources, as_of_date, data_dir=data_dir)
    else:
        logger.info("Ingest cached — skipping")

    # Step 2: Transform
    from ffmodel.transform.player_dim import write_player_dim
    from ffmodel.transform.player_week import write_player_week_fact
    from ffmodel.transform.schedule import write_schedule_fact
    from ffmodel.transform.team_dim import write_team_dim
    from ffmodel.transform.team_week import write_team_week_fact

    if not silver_dir.exists() or not (silver_dir / "player_week_fact.parquet").exists():
        logger.info("Running transform...")
        seasons = list(range(config.sources.seasons.min, config.sources.seasons.max + 1))
        write_player_dim(raw_dir, silver_dir)
        write_team_dim(raw_dir, silver_dir, seasons)
        write_schedule_fact(raw_dir, silver_dir)
        write_player_week_fact(raw_dir, silver_dir)
        write_team_week_fact(raw_dir, silver_dir)
    else:
        logger.info("Transform cached — skipping")

    # Step 3: Features
    from ffmodel.features.availability import write_availability_features
    from ffmodel.features.efficiency import write_player_efficiency_features
    from ffmodel.features.manual_factors import write_manual_factor_features
    from ffmodel.features.player_role import write_player_role_features
    from ffmodel.features.team_context import write_team_context_features

    if not gold_dir.exists() or not (gold_dir / "team_context_features.parquet").exists():
        logger.info("Running features...")
        target_season = config.sources.seasons.target
        recency_weights = config.model.recency_weights

        write_team_context_features(silver_dir, gold_dir, target_season, recency_weights)
        team_changer_cfg = {
            "player_history_weight": config.model.team_changer.player_history_weight,
            "team_prior_weight": config.model.team_changer.team_prior_weight,
        }
        write_player_role_features(silver_dir, gold_dir, target_season, recency_weights, team_changer_cfg)
        write_player_efficiency_features(silver_dir, gold_dir, target_season, recency_weights, config.model.regression_samples)
        games_active_cfg = {
            "default_max": config.model.games_active.default_max,
            "shrinkage": config.model.games_active.shrinkage,
            "position_prior": config.model.games_active.position_prior,
            "low_sample_threshold": config.model.games_active.low_sample_threshold,
        }
        write_availability_features(silver_dir, gold_dir, target_season, recency_weights, games_active_cfg)
        write_manual_factor_features(Path(manual_dir), gold_dir, as_of_date)
    else:
        logger.info("Features cached — skipping")

    # Step 4: Project
    team_context_df = pd.read_parquet(gold_dir / "team_context_features.parquet")
    role_df = pd.read_parquet(gold_dir / "player_role_features.parquet")
    efficiency_df = pd.read_parquet(gold_dir / "player_efficiency_features.parquet")
    availability_df = pd.read_parquet(gold_dir / "availability_features.parquet")
    player_week_fact = pd.read_parquet(silver_dir / "player_week_fact.parquet")
    team_week_fact = pd.read_parquet(silver_dir / "team_week_fact.parquet")

    logger.info("Running projections...")
    projections = run_projections(
        team_context_df, role_df, efficiency_df, availability_df,
        player_week_fact, team_week_fact,
        config.scoring, config.model, config.sources.seasons.target,
    )

    logger.info("Computing uncertainty...")
    uncertainty = compute_all_uncertainty(
        projections, config.scoring,
        n_samples=config.model.uncertainty.n_samples,
    )

    proj_df = projections_to_dataframe(projections)
    unc_records = [
        {"player_id": u.player_id, "position": u.position,
         "fantasy_points_p25": u.fantasy_points_p25,
         "fantasy_points_p50": u.fantasy_points_p50,
         "fantasy_points_p75": u.fantasy_points_p75}
        for u in uncertainty
    ]
    unc_df = pd.DataFrame(unc_records)

    # Step 5: Overlay
    manual_factors_path = gold_dir / "manual_factor_features.parquet"
    if manual_factors_path.exists():
        manual_factors_df = pd.read_parquet(manual_factors_path)
    else:
        manual_factors_df = pd.DataFrame(columns=[
            "entity_id", "entity_type", "factor_name",
            "score_normalized", "confidence",
        ])

    logger.info("Applying overlays...")
    overlay_results = apply_overlays(proj_df, unc_df, manual_factors_df, config.model.overlay)

    # Step 6: Rank
    logger.info("Computing rankings...")
    ranked = compute_rankings(overlay_results, proj_df, unc_df, config.ranking)

    # Step 7: QA
    from ffmodel.ranking.ranker import rankings_to_dataframe
    rankings_df = rankings_to_dataframe(ranked)

    logger.info("Running QA checks...")
    qa_results = run_all_checks(
        rankings_df, proj_df, unc_df, manual_factors_df,
        role_df, team_context_df, config.scoring,
        config.sources.seasons.target,
    )

    critical_failures = [r for r in qa_results if not r.passed]
    if critical_failures:
        for f in critical_failures:
            logger.error("QA FAIL: %s — %s", f.check_id, f.details)
        logger.warning("%d QA checks failed — continuing with export", len(critical_failures))

    # Step 8: Export
    run_id = generate_run_id(as_of_date, config.config_hash)
    logger.info("Exporting to run_id=%s", run_id)
    run_dir = write_outputs(ranked, run_id, as_of_date, config.config_hash, output_dir)

    logger.info("Pipeline complete → %s", run_dir)
    return run_dir
