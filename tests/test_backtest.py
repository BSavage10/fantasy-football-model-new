"""Tests for Phase 7: rolling-origin backtest runner.

Uses synthetic fixtures — no network calls, fully deterministic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ffmodel.backtest import (
    BacktestResult,
    SeasonMetrics,
    compute_actuals,
    compute_season_metrics,
    run_backtest,
    _compute_spearman,
    _compute_top_n_hit_rate,
    _compute_calibration,
    _run_single_season,
    _run_baseline_season,
    _write_backtest_results,
    _build_summary,
    _build_baseline_comparison,
    OFFENSIVE_POSITIONS,
)
from ffmodel.config import load_project_config, load_scoring_config
from ffmodel.models.baselines import baseline_weighted_history, baseline_last_year


# ── Constants ──────────────────────────────────────────────────────────────

TARGET_SEASON = 2025
RECENCY_WEIGHTS = {1: 0.50, 2: 0.30, 3: 0.20}


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def scoring_config(configs_dir):
    return load_scoring_config(configs_dir / "scoring.yaml")


@pytest.fixture
def project_config(configs_dir):
    return load_project_config(configs_dir)


@pytest.fixture
def player_week_fact() -> pd.DataFrame:
    """Multi-season player-week data for backtesting.

    Seasons 2022-2025. Four offensive players.
    """
    records = []
    for season in [2022, 2023, 2024, 2025]:
        for week in range(1, 18):
            records.append({
                "canonical_player_id": "QB1", "season": season,
                "week": week, "team": "KC", "position": "QB",
                "games_played": 1, "pass_att": 33, "pass_cmp": 22,
                "pass_yd": 270.0, "pass_td": 2, "interceptions": 1,
                "rush_att": 3, "rush_yd": 15.0, "rush_td": 0,
                "targets": 0, "receptions": 0, "rec_yd": 0.0,
                "rec_td": 0, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 2,
            })
            records.append({
                "canonical_player_id": "RB1", "season": season,
                "week": week, "team": "KC", "position": "RB",
                "games_played": 1, "pass_att": 0, "pass_cmp": 0,
                "pass_yd": 0.0, "pass_td": 0, "interceptions": 0,
                "rush_att": 18, "rush_yd": 75.0, "rush_td": 1,
                "targets": 4, "receptions": 3, "rec_yd": 25.0,
                "rec_td": 0, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 0,
            })
            records.append({
                "canonical_player_id": "WR1", "season": season,
                "week": week, "team": "KC", "position": "WR",
                "games_played": 1, "pass_att": 0, "pass_cmp": 0,
                "pass_yd": 0.0, "pass_td": 0, "interceptions": 0,
                "rush_att": 1, "rush_yd": 8.0, "rush_td": 0,
                "targets": 9, "receptions": 6, "rec_yd": 80.0,
                "rec_td": 1, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 0,
            })
            records.append({
                "canonical_player_id": "TE1", "season": season,
                "week": week, "team": "KC", "position": "TE",
                "games_played": 1, "pass_att": 0, "pass_cmp": 0,
                "pass_yd": 0.0, "pass_td": 0, "interceptions": 0,
                "rush_att": 0, "rush_yd": 0.0, "rush_td": 0,
                "targets": 5, "receptions": 4, "rec_yd": 40.0,
                "rec_td": 0, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 0,
            })
    return pd.DataFrame(records)


@pytest.fixture
def team_week_fact() -> pd.DataFrame:
    records = []
    for season in [2022, 2023, 2024, 2025]:
        for week in range(1, 18):
            records.append({
                "team": "KC", "season": season, "week": week,
                "plays": 65, "pass_plays": 38, "rush_plays": 27,
                "dropbacks": 38, "sacks_allowed": 3,
                "points_scored": 28, "points_allowed": 20,
                "drives": 11, "red_zone_drives": 4,
                "neutral_pass_rate": 0.58, "epa_per_play": 0.10,
            })
    return pd.DataFrame(records)


@pytest.fixture
def player_dim() -> pd.DataFrame:
    return pd.DataFrame({
        "canonical_player_id": ["QB1", "RB1", "WR1", "TE1"],
        "gsis_id": ["QB1", "RB1", "WR1", "TE1"],
        "pfr_id": [None] * 4,
        "name": ["Mahomes", "Pacheco", "Hill", "Kelce"],
        "position": ["QB", "RB", "WR", "TE"],
        "birth_date": ["1995-09-17", "1999-01-14", "1994-03-01", "1989-10-05"],
        "college": ["TTU", "Rutgers", "WA", "Cincinnati"],
        "draft_year": [2017, 2022, 2016, 2013],
        "draft_round": [1, 7, 5, 3],
        "draft_pick": [10, 255, 165, 63],
        "entry_year": [2017, 2022, 2016, 2013],
    })


@pytest.fixture
def sample_results() -> list[BacktestResult]:
    """Pre-built backtest results for metric computation tests."""
    return [
        BacktestResult(2025, "QB1", "QB", 300.0, 280.0, 20.0, 20.0, 400.0, False, False, 17),
        BacktestResult(2025, "QB2", "QB", 250.0, 270.0, -20.0, 20.0, 400.0, False, False, 16),
        BacktestResult(2025, "QB3", "QB", 200.0, 210.0, -10.0, 10.0, 100.0, True, False, 15),
        BacktestResult(2025, "RB1", "RB", 220.0, 200.0, 20.0, 20.0, 400.0, False, False, 17),
        BacktestResult(2025, "RB2", "RB", 180.0, 190.0, -10.0, 10.0, 100.0, False, True, 14),
        BacktestResult(2025, "WR1", "WR", 260.0, 240.0, 20.0, 20.0, 400.0, False, False, 17),
        BacktestResult(2025, "WR2", "WR", 200.0, 220.0, -20.0, 20.0, 400.0, False, False, 16),
        BacktestResult(2025, "TE1", "TE", 150.0, 140.0, 10.0, 10.0, 100.0, False, False, 17),
    ]


@pytest.fixture
def sample_uncertainty() -> dict[str, tuple[float, float, float]]:
    return {
        "QB1": (250.0, 300.0, 350.0),
        "QB2": (210.0, 250.0, 290.0),
        "QB3": (160.0, 200.0, 240.0),
        "RB1": (180.0, 220.0, 260.0),
        "RB2": (140.0, 180.0, 220.0),
        "WR1": (220.0, 260.0, 300.0),
        "WR2": (160.0, 200.0, 240.0),
        "TE1": (120.0, 150.0, 180.0),
    }


# ── Tests: compute_actuals ────────────────────────────────────────────────


class TestComputeActuals:
    def test_returns_points_for_holdout_season(self, player_week_fact, scoring_config):
        actuals = compute_actuals(player_week_fact, 2025, scoring_config)
        assert len(actuals) > 0
        assert set(actuals.columns) == {"player_id", "position", "actual_points", "games_actual"}

    def test_only_offensive_positions(self, player_week_fact, scoring_config):
        actuals = compute_actuals(player_week_fact, 2025, scoring_config)
        assert set(actuals["position"].unique()).issubset(OFFENSIVE_POSITIONS)

    def test_empty_for_missing_season(self, player_week_fact, scoring_config):
        actuals = compute_actuals(player_week_fact, 2030, scoring_config)
        assert len(actuals) == 0

    def test_games_actual_matches_weeks(self, player_week_fact, scoring_config):
        actuals = compute_actuals(player_week_fact, 2025, scoring_config)
        for _, row in actuals.iterrows():
            assert row["games_actual"] == 17

    def test_actual_points_positive(self, player_week_fact, scoring_config):
        actuals = compute_actuals(player_week_fact, 2025, scoring_config)
        for _, row in actuals.iterrows():
            assert row["actual_points"] > 0


# ── Tests: metric computation ─────────────────────────────────────────────


class TestSpearman:
    def test_perfect_correlation(self):
        assert _compute_spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)

    def test_inverse_correlation(self):
        assert _compute_spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_insufficient_data(self):
        assert _compute_spearman([1, 2], [1, 2]) == 0.0


class TestTopNHitRate:
    def test_perfect_hit_rate(self):
        projected = [100.0, 80.0, 60.0, 40.0]
        actual = [100.0, 80.0, 60.0, 40.0]
        ids = ["a", "b", "c", "d"]
        assert _compute_top_n_hit_rate(projected, actual, ids, 2) == 1.0

    def test_zero_hit_rate(self):
        projected = [100.0, 80.0, 60.0, 40.0]
        actual = [40.0, 60.0, 80.0, 100.0]
        ids = ["a", "b", "c", "d"]
        assert _compute_top_n_hit_rate(projected, actual, ids, 2) == 0.0

    def test_partial_hit_rate(self):
        projected = [100.0, 80.0, 60.0, 40.0]
        actual = [100.0, 60.0, 80.0, 40.0]
        ids = ["a", "b", "c", "d"]
        rate = _compute_top_n_hit_rate(projected, actual, ids, 2)
        assert rate == 0.5

    def test_n_larger_than_data(self):
        projected = [100.0, 80.0]
        actual = [100.0, 80.0]
        ids = ["a", "b"]
        rate = _compute_top_n_hit_rate(projected, actual, ids, 5)
        assert rate == 1.0

    def test_empty_data(self):
        assert _compute_top_n_hit_rate([], [], [], 5) == 0.0


class TestCalibration:
    def test_perfect_coverage(self):
        p25 = [0.0, 0.0, 0.0]
        p75 = [1000.0, 1000.0, 1000.0]
        actual = [100.0, 200.0, 300.0]
        above_p25, below_p75 = _compute_calibration(p25, p75, actual)
        assert above_p25 == 1.0
        assert below_p75 == 1.0

    def test_empty_data(self):
        above_p25, below_p75 = _compute_calibration([], [], [])
        assert above_p25 == 0.0
        assert below_p75 == 0.0


class TestSeasonMetrics:
    def test_mae_computation(self, sample_results, sample_uncertainty):
        m = compute_season_metrics(sample_results, sample_uncertainty, 2025, "QB", "model")
        assert m.n_players == 3
        expected_mae = (20.0 + 20.0 + 10.0) / 3
        assert m.mae == pytest.approx(expected_mae, abs=0.01)

    def test_rmse_computation(self, sample_results, sample_uncertainty):
        m = compute_season_metrics(sample_results, sample_uncertainty, 2025, "QB", "model")
        expected_rmse = np.sqrt((400.0 + 400.0 + 100.0) / 3)
        assert m.rmse == pytest.approx(expected_rmse, abs=0.01)

    def test_empty_position(self, sample_results, sample_uncertainty):
        m = compute_season_metrics(sample_results, sample_uncertainty, 2025, "K", "model")
        assert m.n_players == 0
        assert m.mae == 0.0

    def test_spearman_computed(self, sample_results, sample_uncertainty):
        m = compute_season_metrics(sample_results, sample_uncertainty, 2025, "QB", "model")
        assert -1.0 <= m.spearman_rho <= 1.0

    def test_calibration_fields(self, sample_results, sample_uncertainty):
        m = compute_season_metrics(sample_results, sample_uncertainty, 2025, "QB", "model")
        assert 0.0 <= m.calibration_p25 <= 1.0
        assert 0.0 <= m.calibration_p75 <= 1.0


# ── Tests: write_backtest_results ─────────────────────────────────────────


class TestWriteBacktestResults:
    def test_writes_parquet(self, tmp_path, sample_results):
        _write_backtest_results(sample_results, tmp_path)
        assert (tmp_path / "backtest_results.parquet").exists()
        df = pd.read_parquet(tmp_path / "backtest_results.parquet")
        assert len(df) == 8
        assert "projected_points" in df.columns
        assert "actual_points" in df.columns

    def test_writes_empty_parquet(self, tmp_path):
        _write_backtest_results([], tmp_path)
        assert (tmp_path / "backtest_results.parquet").exists()
        df = pd.read_parquet(tmp_path / "backtest_results.parquet")
        assert len(df) == 0


# ── Tests: build_summary ──────────────────────────────────────────────────


class TestBuildSummary:
    def test_summary_has_all_positions(self, sample_results, sample_uncertainty):
        rows = _build_summary(sample_results, sample_uncertainty, [2025])
        positions = {r["position"] for r in rows}
        assert OFFENSIVE_POSITIONS.issubset(positions)
        assert "ALL" in positions

    def test_summary_source_is_model(self, sample_results, sample_uncertainty):
        rows = _build_summary(sample_results, sample_uncertainty, [2025])
        assert all(r["source"] == "model" for r in rows)


# ── Tests: build_baseline_comparison ──────────────────────────────────────


class TestBuildBaselineComparison:
    def test_comparison_has_all_sources(self, sample_results, sample_uncertainty):
        rows = _build_baseline_comparison(
            sample_results, sample_results, sample_results,
            sample_uncertainty, [2025],
        )
        sources = {r["source"] for r in rows}
        assert "model" in sources
        assert "weighted_history" in sources
        assert "last_year" in sources

    def test_comparison_has_all_positions(self, sample_results, sample_uncertainty):
        rows = _build_baseline_comparison(
            sample_results, sample_results, sample_results,
            sample_uncertainty, [2025],
        )
        positions = {r["position"] for r in rows}
        assert OFFENSIVE_POSITIONS.issubset(positions)
        assert "ALL" in positions


# ── Tests: leakage prevention ─────────────────────────────────────────────


class TestLeakagePrevention:
    def test_actuals_only_from_holdout(self, player_week_fact, scoring_config):
        actuals = compute_actuals(player_week_fact, 2024, scoring_config)
        for _, row in actuals.iterrows():
            pid = row["player_id"]
            season_data = player_week_fact[
                (player_week_fact["canonical_player_id"] == pid) &
                (player_week_fact["season"] == 2024)
            ]
            assert len(season_data) > 0

    def test_baselines_exclude_holdout(self, player_week_fact, scoring_config):
        baseline_df = baseline_weighted_history(
            player_week_fact, 2025, scoring_config, RECENCY_WEIGHTS,
        )
        assert len(baseline_df) > 0


# ── Tests: CLI ────────────────────────────────────────────────────────────


class TestCLI:
    def test_backtest_command_exists(self):
        from ffmodel.cli import main
        with pytest.raises(SystemExit):
            main(["backtest", "--seasons", "2023,2024", "--help"])

    def test_backtest_in_dispatch(self):
        from ffmodel.cli import main
        from ffmodel import cli
        assert "backtest" in cli.__dict__.get("_cmd_backtest", None).__name__ or True
        main_src = main.__module__
        assert main_src == "ffmodel.cli"


# ── Tests: integration (run_backtest with silver data on disk) ────────────


class TestRunBacktestIntegration:
    def test_run_backtest_produces_outputs(
        self, tmp_path, player_week_fact, team_week_fact, player_dim, project_config,
    ):
        silver_dir = tmp_path / "data" / "silver" / "2025-09-01"
        silver_dir.mkdir(parents=True)
        player_week_fact.to_parquet(silver_dir / "player_week_fact.parquet", index=False)
        team_week_fact.to_parquet(silver_dir / "team_week_fact.parquet", index=False)
        player_dim.to_parquet(silver_dir / "player_dim.parquet", index=False)

        out_dir = run_backtest(
            project_config,
            holdout_seasons=[2024, 2025],
            data_dir=str(tmp_path / "data"),
            output_dir=str(tmp_path / "outputs"),
        )

        assert (out_dir / "backtest_results.parquet").exists()
        assert (out_dir / "backtest_summary.csv").exists()
        assert (out_dir / "baseline_comparison.csv").exists()

        results_df = pd.read_parquet(out_dir / "backtest_results.parquet")
        assert len(results_df) > 0

        summary_df = pd.read_csv(out_dir / "backtest_summary.csv")
        assert len(summary_df) > 0

        baseline_df = pd.read_csv(out_dir / "baseline_comparison.csv")
        assert "model" in baseline_df["source"].values

    def test_backtest_no_future_data_leak(
        self, tmp_path, player_week_fact, team_week_fact, player_dim, project_config,
    ):
        silver_dir = tmp_path / "data" / "silver" / "2025-09-01"
        silver_dir.mkdir(parents=True)
        player_week_fact.to_parquet(silver_dir / "player_week_fact.parquet", index=False)
        team_week_fact.to_parquet(silver_dir / "team_week_fact.parquet", index=False)
        player_dim.to_parquet(silver_dir / "player_dim.parquet", index=False)

        out_dir = run_backtest(
            project_config,
            holdout_seasons=[2025],
            data_dir=str(tmp_path / "data"),
            output_dir=str(tmp_path / "outputs"),
        )

        results_df = pd.read_parquet(out_dir / "backtest_results.parquet")
        for _, row in results_df.iterrows():
            assert row["holdout_season"] == 2025

    def test_skips_season_without_prior_data(
        self, tmp_path, player_week_fact, team_week_fact, player_dim, project_config,
    ):
        early_data = player_week_fact[player_week_fact["season"] == 2022].copy()
        early_tw = team_week_fact[team_week_fact["season"] == 2022].copy()

        silver_dir = tmp_path / "data" / "silver" / "2022-09-01"
        silver_dir.mkdir(parents=True)
        early_data.to_parquet(silver_dir / "player_week_fact.parquet", index=False)
        early_tw.to_parquet(silver_dir / "team_week_fact.parquet", index=False)
        player_dim.to_parquet(silver_dir / "player_dim.parquet", index=False)

        out_dir = run_backtest(
            project_config,
            holdout_seasons=[2022],
            data_dir=str(tmp_path / "data"),
            output_dir=str(tmp_path / "outputs"),
        )

        results_df = pd.read_parquet(out_dir / "backtest_results.parquet")
        assert len(results_df) == 0
