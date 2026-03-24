"""Tests for the gold-layer feature engineering modules.

Uses synthetic fixture data — no network calls, fully deterministic.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ffmodel.features.availability import build_availability_features
from ffmodel.features.efficiency import build_player_efficiency_features, regress_rate
from ffmodel.features.manual_factors import build_manual_factor_features
from ffmodel.features.player_role import build_player_role_features
from ffmodel.features.team_context import build_team_context_features


# ── Shared test constants ────────────────────────────────────────────────────

TARGET_SEASON = 2026

RECENCY_WEIGHTS = {1: 0.50, 2: 0.30, 3: 0.20}

REGRESSION_SAMPLES = {
    "pass_td_rate": 1500,
    "int_rate": 800,
    "yards_per_carry": 600,
    "catch_rate": 150,
    "receiving_td_rate": 300,
    "yards_per_attempt": 600,
}

GAMES_ACTIVE_CONFIG = {
    "default_max": 17,
    "shrinkage": 0.20,
    "position_prior": {"QB": 16.0, "RB": 14.5, "WR": 15.5, "TE": 15.0, "K": 16.5},
    "low_sample_threshold": 8,
}

TEAM_CHANGER_CONFIG = {
    "player_history_weight": 0.70,
    "team_prior_weight": 0.30,
}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def team_week_fact() -> pd.DataFrame:
    """Synthetic team_week_fact for two teams across three seasons."""
    records = []
    for season in [2023, 2024, 2025]:
        for week in range(1, 18):
            for team, plays, dropbacks, rushes, sacks in [
                ("KC", 65, 38, 27, 3),
                ("BUF", 62, 35, 27, 2),
            ]:
                records.append({
                    "team": team,
                    "season": season,
                    "week": week,
                    "plays": plays,
                    "pass_plays": dropbacks,
                    "rush_plays": rushes,
                    "dropbacks": dropbacks,
                    "sacks_allowed": sacks,
                    "points_scored": 28,
                    "points_allowed": 20,
                    "drives": 11,
                    "red_zone_drives": 4,
                    "neutral_pass_rate": 0.58,
                    "epa_per_play": 0.10,
                })
    return pd.DataFrame(records)


@pytest.fixture
def player_week_fact() -> pd.DataFrame:
    """Synthetic player_week_fact: multiple players per team, multiple seasons.

    Includes:
    - QB1 (starter on KC, all 3 seasons)
    - RB1 (KC, all 3 seasons)
    - WR1 (KC, all 3 seasons)
    - WR2 (KC, all 3 seasons)
    - RB2 (team changer: BUF in 2023-2024, KC in 2025)
    - No history for ROOKIE1 (will be in player_dim only)
    """
    records = []
    for season in [2023, 2024, 2025]:
        for week in range(1, 18):
            # QB1 on KC
            records.append({
                "canonical_player_id": "QB1",
                "season": season,
                "week": week,
                "team": "KC",
                "position": "QB",
                "games_played": 1,
                "pass_att": 33,
                "pass_cmp": 22,
                "pass_yd": 270.0,
                "pass_td": 2,
                "interceptions": 1,
                "rush_att": 3,
                "rush_yd": 15.0,
                "rush_td": 0,
                "targets": 0,
                "receptions": 0,
                "rec_yd": 0.0,
                "rec_td": 0,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 2,
            })
            # RB1 on KC
            records.append({
                "canonical_player_id": "RB1",
                "season": season,
                "week": week,
                "team": "KC",
                "position": "RB",
                "games_played": 1,
                "pass_att": 0,
                "pass_cmp": 0,
                "pass_yd": 0.0,
                "pass_td": 0,
                "interceptions": 0,
                "rush_att": 18,
                "rush_yd": 75.0,
                "rush_td": 1,
                "targets": 4,
                "receptions": 3,
                "rec_yd": 25.0,
                "rec_td": 0,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 0,
            })
            # WR1 on KC
            records.append({
                "canonical_player_id": "WR1",
                "season": season,
                "week": week,
                "team": "KC",
                "position": "WR",
                "games_played": 1,
                "pass_att": 0,
                "pass_cmp": 0,
                "pass_yd": 0.0,
                "pass_td": 0,
                "interceptions": 0,
                "rush_att": 1,
                "rush_yd": 8.0,
                "rush_td": 0,
                "targets": 9,
                "receptions": 6,
                "rec_yd": 80.0,
                "rec_td": 1,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 0,
            })
            # WR2 on KC
            records.append({
                "canonical_player_id": "WR2",
                "season": season,
                "week": week,
                "team": "KC",
                "position": "WR",
                "games_played": 1,
                "pass_att": 0,
                "pass_cmp": 0,
                "pass_yd": 0.0,
                "pass_td": 0,
                "interceptions": 0,
                "rush_att": 0,
                "rush_yd": 0.0,
                "rush_td": 0,
                "targets": 6,
                "receptions": 4,
                "rec_yd": 55.0,
                "rec_td": 0,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 0,
            })
            # RB2: team changer — BUF in 2023-2024, KC in 2025
            changer_team = "BUF" if season <= 2024 else "KC"
            records.append({
                "canonical_player_id": "RB2",
                "season": season,
                "week": week,
                "team": changer_team,
                "position": "RB",
                "games_played": 1,
                "pass_att": 0,
                "pass_cmp": 0,
                "pass_yd": 0.0,
                "pass_td": 0,
                "interceptions": 0,
                "rush_att": 14,
                "rush_yd": 60.0,
                "rush_td": 0,
                "targets": 3,
                "receptions": 2,
                "rec_yd": 18.0,
                "rec_td": 0,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 0,
            })
            # BUF QB
            records.append({
                "canonical_player_id": "QB2",
                "season": season,
                "week": week,
                "team": "BUF",
                "position": "QB",
                "games_played": 1,
                "pass_att": 31,
                "pass_cmp": 20,
                "pass_yd": 250.0,
                "pass_td": 2,
                "interceptions": 1,
                "rush_att": 5,
                "rush_yd": 30.0,
                "rush_td": 0,
                "targets": 0,
                "receptions": 0,
                "rec_yd": 0.0,
                "rec_td": 0,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 1,
            })
            # BUF WR
            records.append({
                "canonical_player_id": "WR3",
                "season": season,
                "week": week,
                "team": "BUF",
                "position": "WR",
                "games_played": 1,
                "pass_att": 0,
                "pass_cmp": 0,
                "pass_yd": 0.0,
                "pass_td": 0,
                "interceptions": 0,
                "rush_att": 0,
                "rush_yd": 0.0,
                "rush_td": 0,
                "targets": 8,
                "receptions": 5,
                "rec_yd": 70.0,
                "rec_td": 1,
                "fumbles_lost": 0,
                "two_pt_conv": 0,
                "return_td": 0,
                "sacks_taken": 0,
            })

    return pd.DataFrame(records)


@pytest.fixture
def player_dim() -> pd.DataFrame:
    """Player dimension with existing players + a rookie."""
    return pd.DataFrame({
        "canonical_player_id": ["QB1", "RB1", "WR1", "WR2", "RB2", "QB2", "WR3", "ROOKIE1"],
        "gsis_id": ["QB1", "RB1", "WR1", "WR2", "RB2", "QB2", "WR3", "ROOKIE1"],
        "pfr_id": [None] * 8,
        "name": ["Mahomes", "Pacheco", "Hill", "Rice", "Cook", "Allen", "Diggs", "NewGuy"],
        "position": ["QB", "RB", "WR", "WR", "RB", "QB", "WR", "RB"],
        "birth_date": [
            "1995-09-17", "1999-01-14", "1994-03-01", "2000-11-07",
            "1995-08-10", "1996-05-21", "1993-11-04", "2003-06-15",
        ],
        "college": ["TTU", "Rutgers", "WA", "USC", "Minnesota", "Wyoming", "Maryland", "Alabama"],
        "draft_year": [2017, 2022, 2016, 2023, 2017, 2018, 2015, 2026],
        "draft_round": [1, 7, 5, 1, 2, 1, 5, 1],
        "draft_pick": [10, 255, 165, 31, 41, 7, 146, 15],
        "entry_year": [2017, 2022, 2016, 2023, 2017, 2018, 2015, 2026],
    })


# ── Team Context Tests ───────────────────────────────────────────────────────


class TestTeamContext:
    def test_produces_one_row_per_team(self, team_week_fact):
        result = build_team_context_features(team_week_fact, TARGET_SEASON, RECENCY_WEIGHTS)
        assert len(result) == 2
        assert set(result["team"]) == {"KC", "BUF"}

    def test_season_is_target(self, team_week_fact):
        result = build_team_context_features(team_week_fact, TARGET_SEASON, RECENCY_WEIGHTS)
        assert (result["season"] == TARGET_SEASON).all()

    def test_no_leakage(self, team_week_fact):
        tw = team_week_fact.copy()
        tw_with_future = pd.concat([
            tw,
            pd.DataFrame([{
                "team": "KC", "season": TARGET_SEASON, "week": 1,
                "plays": 999, "pass_plays": 999, "rush_plays": 0,
                "dropbacks": 999, "sacks_allowed": 0, "points_scored": 100,
                "points_allowed": 0, "drives": 20, "red_zone_drives": 20,
                "neutral_pass_rate": 1.0, "epa_per_play": 1.0,
            }]),
        ])
        result = build_team_context_features(tw_with_future, TARGET_SEASON, RECENCY_WEIGHTS)
        kc = result[result["team"] == "KC"].iloc[0]
        assert kc["team_plays_proj"] < 100

    def test_proe_sums_near_zero(self, team_week_fact):
        result = build_team_context_features(team_week_fact, TARGET_SEASON, RECENCY_WEIGHTS)
        assert abs(result["proe_proj"].sum()) < 0.01

    def test_all_columns_present(self, team_week_fact):
        from ffmodel.features.team_context import COLUMNS
        result = build_team_context_features(team_week_fact, TARGET_SEASON, RECENCY_WEIGHTS)
        for col in COLUMNS:
            assert col in result.columns, f"Missing column: {col}"


# ── Player Role Tests ────────────────────────────────────────────────────────


class TestPlayerRole:
    def test_target_shares_sum_within_tolerance(
        self, player_week_fact, team_week_fact, player_dim
    ):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        non_rookie = result[~result["is_rookie"]]
        for team in non_rookie["team"].dropna().unique():
            team_players = non_rookie[non_rookie["team"] == team]
            tgt_sum = team_players["target_share"].sum()
            assert tgt_sum <= 1.05, (
                f"Target shares for {team} sum to {tgt_sum:.3f}, exceeds 1.05"
            )

    def test_rush_shares_sum_within_tolerance(
        self, player_week_fact, team_week_fact, player_dim
    ):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        non_rookie = result[~result["is_rookie"]]
        for team in non_rookie["team"].dropna().unique():
            team_players = non_rookie[non_rookie["team"] == team]
            rush_sum = team_players["rush_share"].sum()
            assert rush_sum <= 1.05, (
                f"Rush shares for {team} sum to {rush_sum:.3f}, exceeds 1.05"
            )

    def test_no_leakage(self, player_week_fact, team_week_fact, player_dim):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        assert (result["season"] == TARGET_SEASON).all()

    def test_rookie_has_non_null_features(
        self, player_week_fact, team_week_fact, player_dim
    ):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        rookie = result[result["canonical_player_id"] == "ROOKIE1"]
        assert len(rookie) == 1
        assert rookie.iloc[0]["is_rookie"] == True
        assert pd.notna(rookie.iloc[0]["rush_share"])
        assert pd.notna(rookie.iloc[0]["target_share"])

    def test_team_changer_detected(
        self, player_week_fact, team_week_fact, player_dim
    ):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        rb2 = result[result["canonical_player_id"] == "RB2"].iloc[0]
        assert rb2["is_team_changer"] == True
        assert rb2["team"] == "KC"

    def test_team_changer_blends_with_prior(
        self, player_week_fact, team_week_fact, player_dim
    ):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        rb2 = result[result["canonical_player_id"] == "RB2"].iloc[0]
        non_changer = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS,
            {"player_history_weight": 1.0, "team_prior_weight": 0.0},
        )
        rb2_raw = non_changer[non_changer["canonical_player_id"] == "RB2"].iloc[0]
        assert rb2["rush_share"] != rb2_raw["rush_share"]

    def test_qb_has_starter_share(
        self, player_week_fact, team_week_fact, player_dim
    ):
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        qb1 = result[result["canonical_player_id"] == "QB1"].iloc[0]
        assert qb1["starter_share_of_dropbacks"] > 0

    def test_all_columns_present(
        self, player_week_fact, team_week_fact, player_dim
    ):
        from ffmodel.features.player_role import COLUMNS
        result = build_player_role_features(
            player_week_fact, team_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, TEAM_CHANGER_CONFIG,
        )
        for col in COLUMNS:
            assert col in result.columns, f"Missing column: {col}"


# ── Efficiency Tests ─────────────────────────────────────────────────────────


class TestEfficiency:
    def test_regress_rate_known_value(self):
        result = regress_rate(0.06, 500, 0.045, 1500)
        expected = (0.06 * 500 + 0.045 * 1500) / (500 + 1500)
        assert abs(result - expected) < 1e-10
        assert abs(result - 0.04875) < 1e-10

    def test_regress_rate_heavy_regression(self):
        result = regress_rate(0.10, 50, 0.04, 1500)
        assert result < 0.10
        assert result > 0.04

    def test_regress_rate_large_sample(self):
        result = regress_rate(0.06, 10000, 0.04, 100)
        assert abs(result - 0.06) < 0.005

    def test_no_leakage(self, player_week_fact):
        result = build_player_efficiency_features(
            player_week_fact, TARGET_SEASON, RECENCY_WEIGHTS, REGRESSION_SAMPLES,
        )
        assert (result["season"] == TARGET_SEASON).all()

    def test_all_columns_present(self, player_week_fact):
        from ffmodel.features.efficiency import COLUMNS
        result = build_player_efficiency_features(
            player_week_fact, TARGET_SEASON, RECENCY_WEIGHTS, REGRESSION_SAMPLES,
        )
        for col in COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_qb_has_passing_efficiency(self, player_week_fact):
        result = build_player_efficiency_features(
            player_week_fact, TARGET_SEASON, RECENCY_WEIGHTS, REGRESSION_SAMPLES,
        )
        qb = result[result["canonical_player_id"] == "QB1"].iloc[0]
        assert qb["yards_per_attempt"] > 0
        assert 0 < qb["comp_rate"] < 1
        assert qb["pass_td_rate_regressed"] > 0
        assert qb["int_rate_regressed"] > 0

    def test_regression_pulls_toward_prior(self, player_week_fact):
        result = build_player_efficiency_features(
            player_week_fact, TARGET_SEASON, RECENCY_WEIGHTS, REGRESSION_SAMPLES,
        )
        qb = result[result["canonical_player_id"] == "QB1"].iloc[0]
        raw_td_rate = 2 / 33
        assert qb["pass_td_rate_regressed"] != raw_td_rate

    def test_rb_has_rushing_efficiency(self, player_week_fact):
        result = build_player_efficiency_features(
            player_week_fact, TARGET_SEASON, RECENCY_WEIGHTS, REGRESSION_SAMPLES,
        )
        rb = result[result["canonical_player_id"] == "RB1"].iloc[0]
        assert rb["yards_per_carry_regressed"] > 0
        assert rb["catch_rate"] > 0


# ── Availability Tests ───────────────────────────────────────────────────────


class TestAvailability:
    def test_games_active_capped_at_17(
        self, player_week_fact, player_dim
    ):
        result = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        assert (result["games_active_proj"] <= 17).all()

    def test_games_active_non_negative(
        self, player_week_fact, player_dim
    ):
        result = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        assert (result["games_active_proj"] >= 0).all()

    def test_no_leakage(self, player_week_fact, player_dim):
        result = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        assert (result["season"] == TARGET_SEASON).all()

    def test_prior_season_games_populated(
        self, player_week_fact, player_dim
    ):
        result = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        qb1 = result[result["canonical_player_id"] == "QB1"].iloc[0]
        assert qb1["games_played_y1"] == 17
        assert qb1["games_played_y2"] == 17
        assert qb1["games_played_y3"] == 17

    def test_rookie_gets_position_prior(
        self, player_week_fact, player_dim
    ):
        result = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        rookie = result[result["canonical_player_id"] == "ROOKIE1"].iloc[0]
        assert rookie["years_pro"] == 0
        assert pd.notna(rookie["games_active_proj"])
        assert rookie["games_active_proj"] > 0

    def test_age_discount_applied(self, player_week_fact, player_dim):
        old_player_dim = player_dim.copy()
        old_player_dim.loc[
            old_player_dim["canonical_player_id"] == "RB1", "birth_date"
        ] = "1993-01-01"

        result = build_availability_features(
            player_week_fact, old_player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        rb1 = result[result["canonical_player_id"] == "RB1"].iloc[0]
        result_young = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        rb1_young = result_young[result_young["canonical_player_id"] == "RB1"].iloc[0]
        assert rb1["games_active_proj"] < rb1_young["games_active_proj"]

    def test_all_columns_present(self, player_week_fact, player_dim):
        from ffmodel.features.availability import COLUMNS
        result = build_availability_features(
            player_week_fact, player_dim,
            TARGET_SEASON, RECENCY_WEIGHTS, GAMES_ACTIVE_CONFIG,
        )
        for col in COLUMNS:
            assert col in result.columns, f"Missing column: {col}"


# ── Manual Factors Tests ─────────────────────────────────────────────────────


class TestManualFactors:
    def test_valid_entries_loaded(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
            "P001,player,coaching_quality,0.70,0.80,analyst,Good coach,2027-01-01\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert len(result) == 1
        assert result.iloc[0]["score_raw"] == 0.70

    def test_rejects_out_of_range_score(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
            "P001,player,coaching_quality,1.50,0.80,analyst,Good coach,\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert len(result) == 0

    def test_rejects_missing_owner(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
            "P001,player,coaching_quality,0.70,0.80,,Good coach,\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert len(result) == 0

    def test_rejects_missing_rationale(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
            "P001,player,coaching_quality,0.70,0.80,analyst,,\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert len(result) == 0

    def test_expires_stale_entries(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
            "P001,player,coaching_quality,0.70,0.80,analyst,Good coach,2025-01-01\n"
            "P002,player,role_clarity,0.85,0.90,analyst,Clear role,2027-01-01\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert len(result) == 1
        assert result.iloc[0]["entity_id"] == "P002"

    def test_empty_file_returns_empty(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert len(result) == 0

    def test_missing_file_returns_empty(self, tmp_path):
        result = build_manual_factor_features(tmp_path / "nonexistent.csv", "2026-09-01")
        assert len(result) == 0

    def test_score_normalized_equals_raw(self, tmp_path):
        csv = tmp_path / "manual_factors.csv"
        csv.write_text(
            "entity_id,entity_type,factor_name,score_raw,confidence,owner,rationale,expires_at\n"
            "P001,player,coaching_quality,0.70,0.80,analyst,Good coach,\n"
        )
        result = build_manual_factor_features(csv, "2026-09-01")
        assert result.iloc[0]["score_normalized"] == result.iloc[0]["score_raw"]
