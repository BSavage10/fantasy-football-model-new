"""Rolling-origin backtest runner.

For each holdout season, trains only on earlier seasons and features available
before that season's opener, runs the full pipeline (features -> project -> score),
loads actuals, and computes error metrics.

Manual factors are excluded from headline backtest numbers because they are not
historically reconstructable.

Output to outputs/backtest/:
  - backtest_results.parquet   — per-player per-holdout-season detail rows
  - backtest_summary.csv       — aggregate metrics by position and holdout season
  - baseline_comparison.csv    — model vs baselines on every metric
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from ffmodel.config import ProjectConfig
from ffmodel.features.availability import build_availability_features
from ffmodel.features.efficiency import build_player_efficiency_features
from ffmodel.features.player_role import build_player_role_features
from ffmodel.features.team_context import build_team_context_features
from ffmodel.models import run_projections, projections_to_dataframe
from ffmodel.models.base import compute_secondary_rates
from ffmodel.models.baselines import (
    baseline_last_year,
    baseline_weighted_history,
    _aggregate_player_seasons,
    _score_player_season,
)
from ffmodel.models.uncertainty import compute_all_uncertainty
from ffmodel.scoring.engine import score_player

logger = logging.getLogger(__name__)

OFFENSIVE_POSITIONS = {"QB", "RB", "WR", "TE"}

TOP_N_THRESHOLDS = {
    "QB": 20,
    "RB": 20,
    "WR": 30,
    "TE": 10,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Per-player result for one holdout season."""
    holdout_season: int
    player_id: str
    position: str
    projected_points: float
    actual_points: float
    error: float
    abs_error: float
    squared_error: float
    is_rookie: bool
    is_team_changer: bool
    games_actual: int


@dataclass
class SeasonMetrics:
    """Aggregate metrics for one position in one holdout season."""
    holdout_season: int
    position: str
    source: str
    n_players: int
    mae: float
    rmse: float
    spearman_rho: float
    top_n_hit_rate: float
    calibration_p25: float
    calibration_p75: float


# ---------------------------------------------------------------------------
# Actuals computation
# ---------------------------------------------------------------------------

def compute_actuals(
    player_week_fact: pd.DataFrame,
    holdout_season: int,
    scoring_config,
) -> pd.DataFrame:
    """Compute actual fantasy points for a holdout season.

    Returns DataFrame with: player_id, position, actual_points, games_actual
    """
    season_data = player_week_fact[player_week_fact["season"] == holdout_season].copy()
    if season_data.empty:
        return pd.DataFrame(columns=["player_id", "position", "actual_points", "games_actual"])

    player_season = _aggregate_player_seasons(season_data)

    results = []
    for _, row in player_season.iterrows():
        pos = str(row["position"])
        if pos not in OFFENSIVE_POSITIONS:
            continue
        pts = _score_player_season(row, scoring_config)
        results.append({
            "player_id": row["canonical_player_id"],
            "position": pos,
            "actual_points": pts,
            "games_actual": int(row["games"]),
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Feature building for a holdout season
# ---------------------------------------------------------------------------

def _build_features_for_holdout(
    player_week_fact: pd.DataFrame,
    team_week_fact: pd.DataFrame,
    player_dim: pd.DataFrame,
    holdout_season: int,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build gold-layer features for a holdout season using only prior data.

    Returns (team_context_df, role_df, efficiency_df, availability_df)
    """
    recency_weights = config.model.recency_weights

    team_context_df = build_team_context_features(
        team_week_fact, holdout_season, recency_weights,
    )

    team_changer_cfg = {
        "player_history_weight": config.model.team_changer.player_history_weight,
        "team_prior_weight": config.model.team_changer.team_prior_weight,
    }
    role_df = build_player_role_features(
        player_week_fact, team_week_fact, player_dim,
        holdout_season, recency_weights, team_changer_cfg,
    )

    efficiency_df = build_player_efficiency_features(
        player_week_fact, holdout_season, recency_weights,
        config.model.regression_samples,
    )

    games_active_cfg = {
        "default_max": config.model.games_active.default_max,
        "shrinkage": config.model.games_active.shrinkage,
        "position_prior": config.model.games_active.position_prior,
        "low_sample_threshold": config.model.games_active.low_sample_threshold,
    }
    availability_df = build_availability_features(
        player_week_fact, player_dim, holdout_season,
        recency_weights, games_active_cfg,
    )

    return team_context_df, role_df, efficiency_df, availability_df


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _compute_spearman(projected: list[float], actual: list[float]) -> float:
    """Compute Spearman rank correlation. Returns 0.0 if insufficient data."""
    if len(projected) < 3:
        return 0.0
    rho, _ = scipy_stats.spearmanr(projected, actual)
    return float(rho) if not np.isnan(rho) else 0.0


def _compute_top_n_hit_rate(
    projected: list[float],
    actual: list[float],
    player_ids: list[str],
    n: int,
) -> float:
    """Fraction of projected top-N who actually finish in the top-N."""
    if len(projected) < n:
        n = len(projected)
    if n == 0:
        return 0.0

    proj_order = sorted(range(len(projected)), key=lambda i: projected[i], reverse=True)
    actual_order = sorted(range(len(actual)), key=lambda i: actual[i], reverse=True)

    proj_top_n = set(proj_order[:n])
    actual_top_n = set(actual_order[:n])

    return len(proj_top_n & actual_top_n) / n


def _compute_calibration(
    p25_values: list[float],
    p75_values: list[float],
    actual_values: list[float],
) -> tuple[float, float]:
    """Compute empirical coverage for P25 and P75 intervals.

    Returns (frac_above_p25, frac_below_p75).
    Expected: ~75% above P25, ~75% below P75.
    """
    if not actual_values:
        return 0.0, 0.0
    n = len(actual_values)
    above_p25 = sum(1 for a, p in zip(actual_values, p25_values) if a >= p)
    below_p75 = sum(1 for a, p in zip(actual_values, p75_values) if a <= p)
    return above_p25 / n, below_p75 / n


def compute_season_metrics(
    results: list[BacktestResult],
    uncertainty_lookup: dict[str, tuple[float, float, float]],
    holdout_season: int,
    position: str,
    source: str = "model",
) -> SeasonMetrics:
    """Compute aggregate metrics for a position in a holdout season."""
    pos_results = [r for r in results if r.position == position and r.holdout_season == holdout_season]

    if not pos_results:
        return SeasonMetrics(
            holdout_season=holdout_season, position=position, source=source,
            n_players=0, mae=0.0, rmse=0.0, spearman_rho=0.0,
            top_n_hit_rate=0.0, calibration_p25=0.0, calibration_p75=0.0,
        )

    mae = np.mean([r.abs_error for r in pos_results])
    rmse = np.sqrt(np.mean([r.squared_error for r in pos_results]))
    projected = [r.projected_points for r in pos_results]
    actual = [r.actual_points for r in pos_results]
    player_ids = [r.player_id for r in pos_results]
    spearman = _compute_spearman(projected, actual)

    top_n = TOP_N_THRESHOLDS.get(position, 10)
    hit_rate = _compute_top_n_hit_rate(projected, actual, player_ids, top_n)

    p25_vals = []
    p75_vals = []
    actual_vals = []
    for r in pos_results:
        unc = uncertainty_lookup.get(r.player_id)
        if unc:
            p25_vals.append(unc[0])
            p75_vals.append(unc[2])
            actual_vals.append(r.actual_points)
    cal_p25, cal_p75 = _compute_calibration(p25_vals, p75_vals, actual_vals)

    return SeasonMetrics(
        holdout_season=holdout_season,
        position=position,
        source=source,
        n_players=len(pos_results),
        mae=float(mae),
        rmse=float(rmse),
        spearman_rho=spearman,
        top_n_hit_rate=hit_rate,
        calibration_p25=cal_p25,
        calibration_p75=cal_p75,
    )


# ---------------------------------------------------------------------------
# Single-season backtest
# ---------------------------------------------------------------------------

def _run_single_season(
    holdout_season: int,
    player_week_fact: pd.DataFrame,
    team_week_fact: pd.DataFrame,
    player_dim: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[list[BacktestResult], dict[str, tuple[float, float, float]]]:
    """Run the model for one holdout season and compare to actuals.

    Returns (results, uncertainty_lookup) where uncertainty_lookup maps
    player_id -> (p25, p50, p75).
    """
    logger.info("Backtesting holdout season %d", holdout_season)

    team_context_df, role_df, efficiency_df, availability_df = _build_features_for_holdout(
        player_week_fact, team_week_fact, player_dim, holdout_season, config,
    )

    if role_df.empty:
        logger.warning("No features built for season %d — skipping", holdout_season)
        return [], {}

    projections = run_projections(
        team_context_df, role_df, efficiency_df, availability_df,
        player_week_fact[player_week_fact["season"] < holdout_season],
        team_week_fact[team_week_fact["season"] < holdout_season],
        config.scoring, config.model, holdout_season,
    )

    uncertainty = compute_all_uncertainty(
        projections, config.scoring,
        n_samples=config.model.uncertainty.n_samples,
    )

    proj_df = projections_to_dataframe(projections)

    proj_lookup: dict[str, tuple[float, str, bool, bool]] = {}
    for _, row in proj_df.iterrows():
        pid = str(row["player_id"])
        pos = str(row["position"])
        if pos not in OFFENSIVE_POSITIONS:
            continue
        season_total = {k.replace("_season_total", ""): v
                        for k, v in row.items()
                        if str(k).endswith("_season_total")}
        pts = score_player(season_total, pos, config.scoring)
        proj_lookup[pid] = (pts, pos, bool(row["is_rookie"]), bool(row["is_team_changer"]))

    uncertainty_lookup: dict[str, tuple[float, float, float]] = {}
    for u in uncertainty:
        uncertainty_lookup[u.player_id] = (
            u.fantasy_points_p25, u.fantasy_points_p50, u.fantasy_points_p75,
        )

    actuals = compute_actuals(player_week_fact, holdout_season, config.scoring)

    actual_lookup: dict[str, tuple[float, int]] = {}
    for _, row in actuals.iterrows():
        actual_lookup[str(row["player_id"])] = (float(row["actual_points"]), int(row["games_actual"]))

    results: list[BacktestResult] = []
    common_pids = set(proj_lookup.keys()) & set(actual_lookup.keys())
    for pid in common_pids:
        proj_pts, pos, is_rookie, is_tc = proj_lookup[pid]
        actual_pts, games_actual = actual_lookup[pid]

        error = proj_pts - actual_pts
        results.append(BacktestResult(
            holdout_season=holdout_season,
            player_id=pid,
            position=pos,
            projected_points=proj_pts,
            actual_points=actual_pts,
            error=error,
            abs_error=abs(error),
            squared_error=error ** 2,
            is_rookie=is_rookie,
            is_team_changer=is_tc,
            games_actual=games_actual,
        ))

    logger.info(
        "Season %d: %d projections, %d actuals, %d matched",
        holdout_season, len(proj_lookup), len(actual_lookup), len(results),
    )
    return results, uncertainty_lookup


def _run_baseline_season(
    holdout_season: int,
    player_week_fact: pd.DataFrame,
    config: ProjectConfig,
    baseline_fn,
    baseline_name: str,
    **kwargs,
) -> list[BacktestResult]:
    """Run a baseline for one holdout season and compare to actuals."""
    baseline_df = baseline_fn(
        player_week_fact, holdout_season, config.scoring, **kwargs,
    )

    actuals = compute_actuals(player_week_fact, holdout_season, config.scoring)
    actual_lookup: dict[str, tuple[float, int]] = {}
    for _, row in actuals.iterrows():
        actual_lookup[str(row["player_id"])] = (float(row["actual_points"]), int(row["games_actual"]))

    results: list[BacktestResult] = []
    for _, row in baseline_df.iterrows():
        pid = str(row["player_id"])
        if pid not in actual_lookup:
            continue
        pos = str(row["position"])
        if pos not in OFFENSIVE_POSITIONS:
            continue
        proj_pts = float(row["fantasy_points_proj"])
        actual_pts, games_actual = actual_lookup[pid]
        error = proj_pts - actual_pts
        results.append(BacktestResult(
            holdout_season=holdout_season,
            player_id=pid,
            position=pos,
            projected_points=proj_pts,
            actual_points=actual_pts,
            error=error,
            abs_error=abs(error),
            squared_error=error ** 2,
            is_rookie=False,
            is_team_changer=False,
            games_actual=games_actual,
        ))
    return results


# ---------------------------------------------------------------------------
# Full backtest runner
# ---------------------------------------------------------------------------

def run_backtest(
    config: ProjectConfig,
    holdout_seasons: list[int],
    data_dir: str = "data",
    output_dir: str = "outputs",
) -> Path:
    """Run rolling-origin backtest across multiple holdout seasons.

    For each holdout season:
    1. Build features using only data from seasons < holdout
    2. Run full projection pipeline
    3. Load actuals for holdout season
    4. Compute error metrics
    5. Run baselines for comparison

    Args:
        config: Full project config.
        holdout_seasons: List of seasons to evaluate (e.g. [2023, 2024, 2025]).
        data_dir: Path to data directory with silver/ subdirectory.
        output_dir: Base output directory.

    Returns:
        Path to backtest output directory.
    """
    data_path = Path(data_dir)
    out_path = Path(output_dir) / "backtest"
    out_path.mkdir(parents=True, exist_ok=True)

    silver_candidates = sorted(data_path.glob("silver/*/player_week_fact.parquet"))
    if not silver_candidates:
        raise FileNotFoundError(
            f"No silver data found in {data_path / 'silver'}. "
            "Run `ffmodel ingest` and `ffmodel transform` first."
        )

    latest_silver = silver_candidates[-1].parent
    logger.info("Using silver data from %s", latest_silver)

    player_week_fact = pd.read_parquet(latest_silver / "player_week_fact.parquet")
    team_week_fact = pd.read_parquet(latest_silver / "team_week_fact.parquet")
    player_dim = pd.read_parquet(latest_silver / "player_dim.parquet")

    all_model_results: list[BacktestResult] = []
    all_uncertainty: dict[str, tuple[float, float, float]] = {}
    all_weighted_results: list[BacktestResult] = []
    all_lastyear_results: list[BacktestResult] = []

    for season in holdout_seasons:
        available_seasons = sorted(player_week_fact["season"].unique())
        if season not in available_seasons:
            logger.warning("Season %d not in data — skipping", season)
            continue

        prior_seasons = [s for s in available_seasons if s < season]
        if len(prior_seasons) < 1:
            logger.warning("No prior seasons for %d — skipping", season)
            continue

        results, unc_lookup = _run_single_season(
            season, player_week_fact, team_week_fact, player_dim, config,
        )
        all_model_results.extend(results)
        all_uncertainty.update(unc_lookup)

        weighted_results = _run_baseline_season(
            season, player_week_fact, config,
            baseline_weighted_history, "weighted_history",
            weights=config.model.recency_weights,
        )
        all_weighted_results.extend(weighted_results)

        lastyear_results = _run_baseline_season(
            season, player_week_fact, config,
            baseline_last_year, "last_year",
        )
        all_lastyear_results.extend(lastyear_results)

    _write_backtest_results(all_model_results, out_path)

    summary_rows = _build_summary(
        all_model_results, all_uncertainty, holdout_seasons,
    )

    baseline_rows = _build_baseline_comparison(
        all_model_results, all_weighted_results, all_lastyear_results,
        all_uncertainty, holdout_seasons,
    )

    pd.DataFrame(summary_rows).to_csv(out_path / "backtest_summary.csv", index=False)
    pd.DataFrame(baseline_rows).to_csv(out_path / "baseline_comparison.csv", index=False)

    logger.info("Backtest complete → %s", out_path)
    return out_path


def _write_backtest_results(results: list[BacktestResult], out_path: Path) -> None:
    """Write per-player backtest detail to parquet."""
    if not results:
        pd.DataFrame(columns=[
            "holdout_season", "player_id", "position", "projected_points",
            "actual_points", "error", "abs_error", "squared_error",
            "is_rookie", "is_team_changer", "games_actual",
        ]).to_parquet(out_path / "backtest_results.parquet", index=False)
        return

    records = []
    for r in results:
        records.append({
            "holdout_season": r.holdout_season,
            "player_id": r.player_id,
            "position": r.position,
            "projected_points": round(r.projected_points, 2),
            "actual_points": round(r.actual_points, 2),
            "error": round(r.error, 2),
            "abs_error": round(r.abs_error, 2),
            "squared_error": round(r.squared_error, 2),
            "is_rookie": r.is_rookie,
            "is_team_changer": r.is_team_changer,
            "games_actual": r.games_actual,
        })
    pd.DataFrame(records).to_parquet(out_path / "backtest_results.parquet", index=False)


def _build_summary(
    model_results: list[BacktestResult],
    uncertainty_lookup: dict[str, tuple[float, float, float]],
    holdout_seasons: list[int],
) -> list[dict]:
    """Build summary metrics by position and season."""
    rows = []
    for season in holdout_seasons:
        for pos in sorted(OFFENSIVE_POSITIONS):
            m = compute_season_metrics(
                model_results, uncertainty_lookup, season, pos, source="model",
            )
            rows.append({
                "holdout_season": m.holdout_season,
                "position": m.position,
                "source": m.source,
                "n_players": m.n_players,
                "mae": round(m.mae, 2),
                "rmse": round(m.rmse, 2),
                "spearman_rho": round(m.spearman_rho, 4),
                "top_n_hit_rate": round(m.top_n_hit_rate, 4),
                "calibration_p25": round(m.calibration_p25, 4),
                "calibration_p75": round(m.calibration_p75, 4),
            })

        all_pos_results = [r for r in model_results if r.holdout_season == season]
        if all_pos_results:
            mae = np.mean([r.abs_error for r in all_pos_results])
            rmse = np.sqrt(np.mean([r.squared_error for r in all_pos_results]))
            projected = [r.projected_points for r in all_pos_results]
            actual = [r.actual_points for r in all_pos_results]
            spearman = _compute_spearman(projected, actual)
            rows.append({
                "holdout_season": season,
                "position": "ALL",
                "source": "model",
                "n_players": len(all_pos_results),
                "mae": round(float(mae), 2),
                "rmse": round(float(rmse), 2),
                "spearman_rho": round(spearman, 4),
                "top_n_hit_rate": 0.0,
                "calibration_p25": 0.0,
                "calibration_p75": 0.0,
            })

    return rows


def _build_baseline_comparison(
    model_results: list[BacktestResult],
    weighted_results: list[BacktestResult],
    lastyear_results: list[BacktestResult],
    uncertainty_lookup: dict[str, tuple[float, float, float]],
    holdout_seasons: list[int],
) -> list[dict]:
    """Build comparison of model vs baselines across all metrics."""
    rows = []
    empty_unc: dict[str, tuple[float, float, float]] = {}

    for season in holdout_seasons:
        for pos in sorted(OFFENSIVE_POSITIONS):
            model_m = compute_season_metrics(
                model_results, uncertainty_lookup, season, pos, "model",
            )
            weighted_m = compute_season_metrics(
                weighted_results, empty_unc, season, pos, "weighted_history",
            )
            lastyear_m = compute_season_metrics(
                lastyear_results, empty_unc, season, pos, "last_year",
            )

            for m in [model_m, weighted_m, lastyear_m]:
                rows.append({
                    "holdout_season": m.holdout_season,
                    "position": m.position,
                    "source": m.source,
                    "n_players": m.n_players,
                    "mae": round(m.mae, 2),
                    "rmse": round(m.rmse, 2),
                    "spearman_rho": round(m.spearman_rho, 4),
                    "top_n_hit_rate": round(m.top_n_hit_rate, 4),
                })

        for source_name, source_results in [
            ("model", model_results),
            ("weighted_history", weighted_results),
            ("last_year", lastyear_results),
        ]:
            all_pos = [r for r in source_results if r.holdout_season == season]
            if all_pos:
                mae = np.mean([r.abs_error for r in all_pos])
                rmse = np.sqrt(np.mean([r.squared_error for r in all_pos]))
                projected = [r.projected_points for r in all_pos]
                actual = [r.actual_points for r in all_pos]
                spearman = _compute_spearman(projected, actual)
                rows.append({
                    "holdout_season": season,
                    "position": "ALL",
                    "source": source_name,
                    "n_players": len(all_pos),
                    "mae": round(float(mae), 2),
                    "rmse": round(float(rmse), 2),
                    "spearman_rho": round(spearman, 4),
                    "top_n_hit_rate": 0.0,
                })

    return rows
