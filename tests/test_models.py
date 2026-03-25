"""Tests for Phase 5: position models, uncertainty, and baselines.

Uses synthetic gold-layer and silver-layer fixtures — no network calls,
fully deterministic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ffmodel.config import load_scoring_config
from ffmodel.models import run_projections, projections_to_dataframe
from ffmodel.models.base import (
    StatProjection,
    UncertaintyResult,
    compute_secondary_rates,
    make_season_totals,
    weighted_mean,
)
from ffmodel.models.baselines import baseline_last_year, baseline_weighted_history
from ffmodel.models.dst import project_dst
from ffmodel.models.kicker import project_kicker
from ffmodel.models.qb import project_qb
from ffmodel.models.rb import project_rb
from ffmodel.models.te import project_te
from ffmodel.models.uncertainty import compute_all_uncertainty, compute_uncertainty
from ffmodel.models.wr import project_wr


# ── Shared constants ────────────────────────────────────────────────────────

TARGET_SEASON = 2026

RECENCY_WEIGHTS = {1: 0.50, 2: 0.30, 3: 0.20}


# ── Gold-layer fixtures ────────────────────────────────────────────────────


@pytest.fixture
def team_context_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"team": "KC", "season": 2026, "team_plays_proj": 65.0,
         "team_dropbacks_proj": 38.0, "team_rushes_proj": 27.0,
         "team_targets_proj": 35.0, "neutral_pass_rate_proj": 0.58,
         "proe_proj": 0.0, "red_zone_drives_per_game_proj": 4.0,
         "points_per_drive_proj": 2.5, "epa_per_play_proj": 0.10},
        {"team": "BUF", "season": 2026, "team_plays_proj": 62.0,
         "team_dropbacks_proj": 35.0, "team_rushes_proj": 27.0,
         "team_targets_proj": 33.0, "neutral_pass_rate_proj": 0.58,
         "proe_proj": 0.0, "red_zone_drives_per_game_proj": 3.5,
         "points_per_drive_proj": 2.3, "epa_per_play_proj": 0.08},
    ])


@pytest.fixture
def role_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"canonical_player_id": "QB1", "season": 2026, "position": "QB",
         "team": "KC", "rush_share": 0.0, "target_share": 0.0,
         "starter_share_of_dropbacks": 0.95,
         "qb_rush_attempts_per_game": 3.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "RB1", "season": 2026, "position": "RB",
         "team": "KC", "rush_share": 0.65, "target_share": 0.12,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "WR1", "season": 2026, "position": "WR",
         "team": "KC", "rush_share": 0.03, "target_share": 0.25,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "WR2", "season": 2026, "position": "WR",
         "team": "KC", "rush_share": 0.0, "target_share": 0.17,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "RB2", "season": 2026, "position": "RB",
         "team": "KC", "rush_share": 0.30, "target_share": 0.08,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": True},
        {"canonical_player_id": "QB2", "season": 2026, "position": "QB",
         "team": "BUF", "rush_share": 0.0, "target_share": 0.0,
         "starter_share_of_dropbacks": 0.90,
         "qb_rush_attempts_per_game": 5.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "WR3", "season": 2026, "position": "WR",
         "team": "BUF", "rush_share": 0.0, "target_share": 0.24,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "TE1", "season": 2026, "position": "TE",
         "team": "KC", "rush_share": 0.0, "target_share": 0.14,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 51,
         "is_rookie": False, "is_team_changer": False},
        {"canonical_player_id": "ROOKIE1", "season": 2026, "position": "RB",
         "team": "KC", "rush_share": 0.15, "target_share": 0.04,
         "starter_share_of_dropbacks": 0.0,
         "qb_rush_attempts_per_game": 0.0, "games_played": 0,
         "is_rookie": True, "is_team_changer": False},
    ])


@pytest.fixture
def efficiency_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"canonical_player_id": "QB1", "season": 2026, "position": "QB",
         "yards_per_attempt": 7.5, "comp_rate": 0.66,
         "pass_td_rate_regressed": 0.055, "int_rate_regressed": 0.025,
         "yards_per_carry_regressed": 5.0, "yards_per_target": 0.0,
         "catch_rate": 0.0, "receiving_td_rate_regressed": 0.0},
        {"canonical_player_id": "RB1", "season": 2026, "position": "RB",
         "yards_per_attempt": 0.0, "comp_rate": 0.0,
         "pass_td_rate_regressed": 0.0, "int_rate_regressed": 0.0,
         "yards_per_carry_regressed": 4.2, "yards_per_target": 6.3,
         "catch_rate": 0.75, "receiving_td_rate_regressed": 0.04},
        {"canonical_player_id": "WR1", "season": 2026, "position": "WR",
         "yards_per_attempt": 0.0, "comp_rate": 0.0,
         "pass_td_rate_regressed": 0.0, "int_rate_regressed": 0.0,
         "yards_per_carry_regressed": 8.0, "yards_per_target": 8.9,
         "catch_rate": 0.67, "receiving_td_rate_regressed": 0.08},
        {"canonical_player_id": "WR2", "season": 2026, "position": "WR",
         "yards_per_attempt": 0.0, "comp_rate": 0.0,
         "pass_td_rate_regressed": 0.0, "int_rate_regressed": 0.0,
         "yards_per_carry_regressed": 4.3, "yards_per_target": 9.2,
         "catch_rate": 0.67, "receiving_td_rate_regressed": 0.06},
        {"canonical_player_id": "RB2", "season": 2026, "position": "RB",
         "yards_per_attempt": 0.0, "comp_rate": 0.0,
         "pass_td_rate_regressed": 0.0, "int_rate_regressed": 0.0,
         "yards_per_carry_regressed": 4.3, "yards_per_target": 6.0,
         "catch_rate": 0.67, "receiving_td_rate_regressed": 0.04},
        {"canonical_player_id": "QB2", "season": 2026, "position": "QB",
         "yards_per_attempt": 7.2, "comp_rate": 0.64,
         "pass_td_rate_regressed": 0.050, "int_rate_regressed": 0.028,
         "yards_per_carry_regressed": 6.0, "yards_per_target": 0.0,
         "catch_rate": 0.0, "receiving_td_rate_regressed": 0.0},
        {"canonical_player_id": "WR3", "season": 2026, "position": "WR",
         "yards_per_attempt": 0.0, "comp_rate": 0.0,
         "pass_td_rate_regressed": 0.0, "int_rate_regressed": 0.0,
         "yards_per_carry_regressed": 4.3, "yards_per_target": 8.8,
         "catch_rate": 0.63, "receiving_td_rate_regressed": 0.07},
        {"canonical_player_id": "TE1", "season": 2026, "position": "TE",
         "yards_per_attempt": 0.0, "comp_rate": 0.0,
         "pass_td_rate_regressed": 0.0, "int_rate_regressed": 0.0,
         "yards_per_carry_regressed": 4.3, "yards_per_target": 7.0,
         "catch_rate": 0.70, "receiving_td_rate_regressed": 0.05},
    ])


@pytest.fixture
def availability_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"canonical_player_id": "QB1", "season": 2026, "position": "QB",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 31,
         "years_pro": 9, "games_active_proj": 16.2},
        {"canonical_player_id": "RB1", "season": 2026, "position": "RB",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 27,
         "years_pro": 4, "games_active_proj": 15.5},
        {"canonical_player_id": "WR1", "season": 2026, "position": "WR",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 32,
         "years_pro": 10, "games_active_proj": 14.9},
        {"canonical_player_id": "WR2", "season": 2026, "position": "WR",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 26,
         "years_pro": 3, "games_active_proj": 15.5},
        {"canonical_player_id": "RB2", "season": 2026, "position": "RB",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 31,
         "years_pro": 9, "games_active_proj": 14.1},
        {"canonical_player_id": "QB2", "season": 2026, "position": "QB",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 30,
         "years_pro": 8, "games_active_proj": 16.2},
        {"canonical_player_id": "WR3", "season": 2026, "position": "WR",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 33,
         "years_pro": 11, "games_active_proj": 14.5},
        {"canonical_player_id": "TE1", "season": 2026, "position": "TE",
         "games_played_y1": 17, "games_played_y2": 17, "games_played_y3": 17,
         "career_games_played": 51, "age_at_season_start": 28,
         "years_pro": 5, "games_active_proj": 15.0},
        {"canonical_player_id": "ROOKIE1", "season": 2026, "position": "RB",
         "games_played_y1": None, "games_played_y2": None,
         "games_played_y3": None, "career_games_played": 0,
         "age_at_season_start": 23, "years_pro": 0,
         "games_active_proj": 14.5},
    ])


@pytest.fixture
def secondary_rates() -> dict[str, dict[str, float]]:
    return {
        "QB1": {"rush_td_rate": 0.035, "fumble_rate": 0.005},
        "RB1": {"rush_td_rate": 0.056, "fumble_rate": 0.007},
        "WR1": {"rush_td_rate": 0.020, "fumble_rate": 0.004},
        "WR2": {"rush_td_rate": 0.020, "fumble_rate": 0.004},
        "RB2": {"rush_td_rate": 0.042, "fumble_rate": 0.006},
        "QB2": {"rush_td_rate": 0.035, "fumble_rate": 0.005},
        "WR3": {"rush_td_rate": 0.020, "fumble_rate": 0.004},
        "TE1": {"rush_td_rate": 0.010, "fumble_rate": 0.004},
    }


# ── Silver-layer fixtures (for baselines, DST, Kicker, secondary rates) ──


@pytest.fixture
def team_week_fact() -> pd.DataFrame:
    records = []
    for season in [2023, 2024, 2025]:
        for week in range(1, 18):
            for team, pts_scored, pts_allowed in [("KC", 28, 20), ("BUF", 25, 22)]:
                records.append({
                    "team": team, "season": season, "week": week,
                    "plays": 65, "pass_plays": 38, "rush_plays": 27,
                    "dropbacks": 38, "sacks_allowed": 3,
                    "points_scored": pts_scored,
                    "points_allowed": pts_allowed,
                    "drives": 11, "red_zone_drives": 4,
                    "neutral_pass_rate": 0.58, "epa_per_play": 0.10,
                })
    return pd.DataFrame(records)


@pytest.fixture
def player_week_fact() -> pd.DataFrame:
    records = []
    for season in [2023, 2024, 2025]:
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
            changer_team = "BUF" if season <= 2024 else "KC"
            records.append({
                "canonical_player_id": "RB2", "season": season,
                "week": week, "team": changer_team, "position": "RB",
                "games_played": 1, "pass_att": 0, "pass_cmp": 0,
                "pass_yd": 0.0, "pass_td": 0, "interceptions": 0,
                "rush_att": 14, "rush_yd": 60.0, "rush_td": 0,
                "targets": 3, "receptions": 2, "rec_yd": 18.0,
                "rec_td": 0, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 0,
            })
            records.append({
                "canonical_player_id": "QB2", "season": season,
                "week": week, "team": "BUF", "position": "QB",
                "games_played": 1, "pass_att": 31, "pass_cmp": 20,
                "pass_yd": 250.0, "pass_td": 2, "interceptions": 1,
                "rush_att": 5, "rush_yd": 30.0, "rush_td": 0,
                "targets": 0, "receptions": 0, "rec_yd": 0.0,
                "rec_td": 0, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 1,
            })
            records.append({
                "canonical_player_id": "WR3", "season": season,
                "week": week, "team": "BUF", "position": "WR",
                "games_played": 1, "pass_att": 0, "pass_cmp": 0,
                "pass_yd": 0.0, "pass_td": 0, "interceptions": 0,
                "rush_att": 0, "rush_yd": 0.0, "rush_td": 0,
                "targets": 8, "receptions": 5, "rec_yd": 70.0,
                "rec_td": 1, "fumbles_lost": 0, "two_pt_conv": 0,
                "return_td": 0, "sacks_taken": 0,
            })
    return pd.DataFrame(records)


@pytest.fixture
def scoring_config(configs_dir):
    return load_scoring_config(configs_dir / "scoring.yaml")


@pytest.fixture
def model_config():
    from ffmodel.config import load_model_config
    from pathlib import Path
    return load_model_config(
        Path(__file__).resolve().parent.parent / "configs" / "model.yaml"
    )


# ── Base Utility Tests ──────────────────────────────────────────────────────


class TestBaseUtilities:
    def test_weighted_mean_basic(self):
        assert abs(weighted_mean([10, 20], [0.5, 0.5]) - 15.0) < 1e-10

    def test_weighted_mean_empty(self):
        assert weighted_mean([], []) == 0.0

    def test_make_season_totals(self):
        pg = {"rush_yd": 75.0, "rush_td": 0.8}
        totals = make_season_totals(pg, 15.0)
        assert abs(totals["rush_yd"] - 1125.0) < 0.01
        assert abs(totals["rush_td"] - 12.0) < 0.01

    def test_compute_secondary_rates(self, player_week_fact):
        rates = compute_secondary_rates(player_week_fact, TARGET_SEASON, RECENCY_WEIGHTS)
        assert "QB1" in rates
        assert "rush_td_rate" in rates["QB1"]
        assert "fumble_rate" in rates["QB1"]
        assert rates["RB1"]["rush_td_rate"] > 0


# ── QB Projection Tests ────────────────────────────────────────────────────


class TestQBProjection:
    def test_qb_has_required_stats(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        assert len(projs) >= 1
        required = ["pass_att", "pass_cmp", "pass_yd", "pass_td",
                     "interceptions", "rush_att", "rush_yd", "rush_td", "fumbles_lost"]
        for p in projs:
            assert p.position == "QB"
            for stat in required:
                assert stat in p.per_game, f"Missing {stat} in QB per_game"
                assert stat in p.season_total, f"Missing {stat} in QB season_total"

    def test_qb_pass_att_from_team_volume(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        qb1 = [p for p in projs if p.player_id == "QB1"][0]
        expected_att = 35.0 * 0.95
        assert abs(qb1.per_game["pass_att"] - expected_att) < 0.01

    def test_mobile_qb_reason_code(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        qb2 = [p for p in projs if p.player_id == "QB2"][0]
        assert "mobile_qb" in qb2.reason_codes

    def test_games_active_set(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        qb1 = [p for p in projs if p.player_id == "QB1"][0]
        assert qb1.games_active == 16.2


# ── RB Projection Tests ────────────────────────────────────────────────────


class TestRBProjection:
    def test_rb_has_required_stats(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        assert len(projs) >= 1
        required = ["rush_att", "rush_yd", "rush_td", "targets",
                     "receptions", "rec_yd", "rec_td", "fumbles_lost"]
        for p in projs:
            assert p.position == "RB"
            for stat in required:
                assert stat in p.per_game, f"Missing {stat} in RB per_game"

    def test_rb_rush_att_from_team_volume(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        rb1 = [p for p in projs if p.player_id == "RB1"][0]
        expected = 27.0 * 0.65
        assert abs(rb1.per_game["rush_att"] - expected) < 0.01

    def test_high_rush_volume_reason_code(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        rb1 = [p for p in projs if p.player_id == "RB1"][0]
        assert "high_rush_volume" in rb1.reason_codes


# ── WR Projection Tests ────────────────────────────────────────────────────


class TestWRProjection:
    def test_wr_has_required_stats(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_wr(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        assert len(projs) >= 1
        required = ["targets", "receptions", "rec_yd", "rec_td",
                     "rush_att", "rush_yd", "rush_td", "fumbles_lost"]
        for p in projs:
            assert p.position == "WR"
            for stat in required:
                assert stat in p.per_game, f"Missing {stat} in WR per_game"

    def test_wr_targets_from_team_volume(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_wr(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        wr1 = [p for p in projs if p.player_id == "WR1"][0]
        expected = 35.0 * 0.25
        assert abs(wr1.per_game["targets"] - expected) < 0.01


# ── TE Projection Tests ────────────────────────────────────────────────────


class TestTEProjection:
    def test_te_has_required_stats(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_te(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        assert len(projs) >= 1
        required = ["targets", "receptions", "rec_yd", "rec_td"]
        for p in projs:
            assert p.position == "TE"
            for stat in required:
                assert stat in p.per_game, f"Missing {stat} in TE per_game"

    def test_te_targets_from_team_volume(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_te(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        te1 = [p for p in projs if p.player_id == "TE1"][0]
        expected = 35.0 * 0.14
        assert abs(te1.per_game["targets"] - expected) < 0.01


# ── DST Projection Tests ───────────────────────────────────────────────────


class TestDSTProjection:
    def test_dst_has_required_stats(
        self, team_context_df, team_week_fact, scoring_config, model_config,
    ):
        projs = project_dst(
            team_context_df, team_week_fact, scoring_config, model_config, TARGET_SEASON,
        )
        assert len(projs) >= 1
        required = ["sacks", "interceptions", "fumble_recoveries",
                     "dst_td", "points_allowed_bracket_value"]
        for p in projs:
            assert p.position == "DEF"
            for stat in required:
                assert stat in p.per_game, f"Missing {stat} in DST per_game"

    def test_dst_games_active_is_17(
        self, team_context_df, team_week_fact, scoring_config, model_config,
    ):
        projs = project_dst(
            team_context_df, team_week_fact, scoring_config, model_config, TARGET_SEASON,
        )
        for p in projs:
            assert p.games_active == 17.0

    def test_dst_bracket_value_reasonable(
        self, team_context_df, team_week_fact, scoring_config, model_config,
    ):
        projs = project_dst(
            team_context_df, team_week_fact, scoring_config, model_config, TARGET_SEASON,
        )
        for p in projs:
            bv = p.per_game["points_allowed_bracket_value"]
            assert -5.0 <= bv <= 11.0


# ── Kicker Projection Tests ────────────────────────────────────────────────


class TestKickerProjection:
    def test_kicker_has_required_stats(
        self, team_context_df, team_week_fact, model_config,
    ):
        projs = project_kicker(
            team_context_df, team_week_fact, model_config, TARGET_SEASON,
        )
        assert len(projs) >= 1
        required = ["pat_made", "fg_0_19", "fg_20_29",
                     "fg_30_39", "fg_40_49", "fg_50_plus"]
        for p in projs:
            assert p.position == "K"
            for stat in required:
                assert stat in p.per_game, f"Missing {stat} in K per_game"

    def test_kicker_games_active_is_17(
        self, team_context_df, team_week_fact, model_config,
    ):
        projs = project_kicker(
            team_context_df, team_week_fact, model_config, TARGET_SEASON,
        )
        for p in projs:
            assert p.games_active == 17.0


# ── Rookie Projection Tests ────────────────────────────────────────────────


class TestRookieProjection:
    def test_rookie_gets_non_null_projection(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        rookie = [p for p in projs if p.player_id == "ROOKIE1"]
        assert len(rookie) == 1
        assert rookie[0].is_rookie is True
        for v in rookie[0].per_game.values():
            assert v is not None
            assert v >= 0

    def test_rookie_uses_league_avg_efficiency(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        rookie = [p for p in projs if p.player_id == "ROOKIE1"][0]
        assert "rookie_prior_used" in rookie.reason_codes


# ── Team Changer Projection Tests ──────────────────────────────────────────


class TestTeamChangerProjection:
    def test_team_changer_uses_new_team(
        self, role_df, team_context_df, efficiency_df, availability_df, secondary_rates,
    ):
        projs = project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        rb2 = [p for p in projs if p.player_id == "RB2"][0]
        assert rb2.is_team_changer is True
        assert "team_changer_blend" in rb2.reason_codes
        # RB2 is on KC — rush_att should use KC's team_rushes_proj (27)
        expected_rush_att = 27.0 * 0.30
        assert abs(rb2.per_game["rush_att"] - expected_rush_att) < 0.01


# ── Season Total Consistency ───────────────────────────────────────────────


class TestSeasonTotalConsistency:
    def test_per_game_times_games_equals_season_total(
        self, role_df, team_context_df, efficiency_df, availability_df,
        secondary_rates, team_week_fact, scoring_config, model_config,
    ):
        all_projs: list[StatProjection] = []
        all_projs.extend(project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
        all_projs.extend(project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
        all_projs.extend(project_wr(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
        all_projs.extend(project_te(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
        all_projs.extend(project_dst(team_context_df, team_week_fact, scoring_config, model_config, TARGET_SEASON))
        all_projs.extend(project_kicker(team_context_df, team_week_fact, model_config, TARGET_SEASON))

        assert len(all_projs) > 0
        for p in all_projs:
            for stat in p.per_game:
                expected = p.per_game[stat] * p.games_active
                actual = p.season_total[stat]
                assert abs(actual - expected) < 0.1, (
                    f"{p.player_id} ({p.position}) {stat}: "
                    f"season_total={actual:.4f} != per_game*games={expected:.4f}"
                )


# ── Uncertainty Tests ──────────────────────────────────────────────────────


class TestUncertainty:
    def test_p25_lt_p50_lt_p75(
        self, role_df, team_context_df, efficiency_df, availability_df,
        secondary_rates, scoring_config,
    ):
        projs = project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        projs.extend(project_rb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates))
        results = compute_all_uncertainty(projs, scoring_config, n_samples=1000, seed=42)
        assert len(results) > 0
        for u in results:
            assert u.fantasy_points_p25 <= u.fantasy_points_p50, (
                f"{u.player_id}: P25={u.fantasy_points_p25} > P50={u.fantasy_points_p50}"
            )
            assert u.fantasy_points_p50 <= u.fantasy_points_p75, (
                f"{u.player_id}: P50={u.fantasy_points_p50} > P75={u.fantasy_points_p75}"
            )

    def test_deterministic_with_seed(
        self, role_df, team_context_df, efficiency_df, availability_df,
        secondary_rates, scoring_config,
    ):
        projs = project_qb(role_df, team_context_df, efficiency_df, availability_df, secondary_rates)
        r1 = compute_all_uncertainty(projs, scoring_config, n_samples=500, seed=99)
        r2 = compute_all_uncertainty(projs, scoring_config, n_samples=500, seed=99)
        for u1, u2 in zip(r1, r2):
            assert abs(u1.fantasy_points_p50 - u2.fantasy_points_p50) < 0.01

    def test_uncertainty_for_dst(
        self, team_context_df, team_week_fact, scoring_config, model_config,
    ):
        projs = project_dst(team_context_df, team_week_fact, scoring_config, model_config, TARGET_SEASON)
        results = compute_all_uncertainty(projs, scoring_config, n_samples=500, seed=42)
        for u in results:
            assert u.fantasy_points_p25 <= u.fantasy_points_p50 <= u.fantasy_points_p75

    def test_uncertainty_for_kicker(
        self, team_context_df, team_week_fact, scoring_config, model_config,
    ):
        projs = project_kicker(team_context_df, team_week_fact, model_config, TARGET_SEASON)
        results = compute_all_uncertainty(projs, scoring_config, n_samples=500, seed=42)
        for u in results:
            assert u.fantasy_points_p25 <= u.fantasy_points_p50 <= u.fantasy_points_p75


# ── Baseline Tests ─────────────────────────────────────────────────────────


class TestBaselines:
    def test_weighted_history_non_empty(self, player_week_fact, scoring_config):
        result = baseline_weighted_history(
            player_week_fact, TARGET_SEASON, scoring_config, RECENCY_WEIGHTS,
        )
        assert len(result) > 0
        assert "player_id" in result.columns
        assert "fantasy_points_proj" in result.columns
        assert (result["fantasy_points_proj"] > 0).any()

    def test_last_year_non_empty(self, player_week_fact, scoring_config):
        result = baseline_last_year(player_week_fact, TARGET_SEASON, scoring_config)
        assert len(result) > 0
        assert "fantasy_points_proj" in result.columns

    def test_baselines_have_all_positions(self, player_week_fact, scoring_config):
        result = baseline_weighted_history(
            player_week_fact, TARGET_SEASON, scoring_config, RECENCY_WEIGHTS,
        )
        positions = set(result["position"])
        assert "QB" in positions
        assert "RB" in positions
        assert "WR" in positions


# ── Orchestrator Tests ─────────────────────────────────────────────────────


class TestRunProjections:
    def test_produces_all_positions(
        self, team_context_df, role_df, efficiency_df, availability_df,
        player_week_fact, team_week_fact, scoring_config, model_config,
    ):
        projs = run_projections(
            team_context_df, role_df, efficiency_df, availability_df,
            player_week_fact, team_week_fact,
            scoring_config, model_config, TARGET_SEASON,
        )
        positions = {p.position for p in projs}
        assert "QB" in positions
        assert "RB" in positions
        assert "WR" in positions
        assert "TE" in positions
        assert "DEF" in positions
        assert "K" in positions

    def test_projections_to_dataframe(
        self, team_context_df, role_df, efficiency_df, availability_df,
        player_week_fact, team_week_fact, scoring_config, model_config,
    ):
        projs = run_projections(
            team_context_df, role_df, efficiency_df, availability_df,
            player_week_fact, team_week_fact,
            scoring_config, model_config, TARGET_SEASON,
        )
        df = projections_to_dataframe(projs)
        assert len(df) == len(projs)
        assert "player_id" in df.columns
        assert "position" in df.columns
        assert "games_active" in df.columns
