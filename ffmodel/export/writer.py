"""Export writer: CSV, Parquet, schema.json, and projection_run_fact.

Writes:
  - player_projection.csv + .parquet  (offensive players: QB/RB/WR/TE)
  - dst_projection.csv + .parquet     (DEF)
  - kicker_projection.csv + .parquet  (K)
  - combined_rankings.csv             (all positions merged, sorted by overall_rank)
  - schema.json                       (field documentation)
  - projection_run_fact.parquet       (run metadata)
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ffmodel.ranking.ranker import RankedPlayer

logger = logging.getLogger(__name__)

OUTPUT_SCHEMA = {
    "player_id": "Canonical player identifier (gsis_id for offense, team abbreviation for DST/K)",
    "position": "Position group: QB, RB, WR, TE, DEF, K",
    "overall_rank": "1-indexed rank across all positions",
    "position_rank": "1-indexed rank within position group",
    "total_points": "Projected season fantasy points (used for ranking)",
    "model_only_points": "Fantasy points from model only (no overlay)",
    "overlay_adjusted_points": "Fantasy points after manual overlay application",
    "overlay_delta": "overlay_adjusted_points - model_only_points",
    "vor": "Value over replacement: total_points - replacement_level_points",
    "games_active": "Projected games played (0-17)",
    "is_rookie": "True if player is a rookie",
    "is_team_changer": "True if player changed teams",
    "manual_heavy": "True if |overlay_delta| / model_only > 10%",
    "factors_applied": "Number of manual overlay factors applied",
    "combined_multiplier": "Product of all overlay multipliers (capped)",
}


def _get_git_sha() -> str:
    """Get current git SHA, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def write_outputs(
    ranked: list[RankedPlayer],
    run_id: str,
    as_of_date: str,
    config_hash: str,
    output_base: Path | str = "outputs",
) -> Path:
    """Write all output files for a projection run.

    Args:
        ranked: Sorted list of RankedPlayer from the ranking layer.
        run_id: Unique run identifier.
        as_of_date: Data freeze date (YYYY-MM-DD).
        config_hash: SHA-256 of config files.
        output_base: Base directory for outputs (default: "outputs").

    Returns:
        Path to the run's output directory.
    """
    output_base = Path(output_base)
    run_dir = output_base / run_id
    rankings_dir = run_dir / "rankings"
    projections_dir = run_dir / "projections"
    rankings_dir.mkdir(parents=True, exist_ok=True)
    projections_dir.mkdir(parents=True, exist_ok=True)

    from ffmodel.ranking.ranker import rankings_to_dataframe
    combined_df = rankings_to_dataframe(ranked)

    player_df = combined_df[combined_df["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    dst_df = combined_df[combined_df["position"] == "DEF"].copy()
    kicker_df = combined_df[combined_df["position"] == "K"].copy()

    _write_pair(player_df, rankings_dir, "player_projection")
    _write_pair(dst_df, rankings_dir, "dst_projection")
    _write_pair(kicker_df, rankings_dir, "kicker_projection")

    combined_df.to_csv(rankings_dir / "combined_rankings.csv", index=False)
    logger.info("Wrote combined_rankings.csv (%d rows)", len(combined_df))

    with open(rankings_dir / "schema.json", "w") as f:
        json.dump(OUTPUT_SCHEMA, f, indent=2)
    logger.info("Wrote schema.json")

    run_fact = pd.DataFrame([{
        "run_id": run_id,
        "as_of_date": as_of_date,
        "config_hash": config_hash,
        "git_sha": _get_git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_players_ranked": len(ranked),
    }])
    run_fact.to_parquet(projections_dir / "projection_run_fact.parquet", index=False)
    logger.info("Wrote projection_run_fact.parquet")

    return run_dir


def _write_pair(df: pd.DataFrame, directory: Path, name: str) -> None:
    """Write a DataFrame as both CSV and Parquet."""
    df.to_csv(directory / f"{name}.csv", index=False)
    df.to_parquet(directory / f"{name}.parquet", index=False)
    logger.info("Wrote %s (.csv + .parquet, %d rows)", name, len(df))
