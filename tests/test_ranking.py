"""Tests for the ranking layer module."""

import pandas as pd
import pytest

from ffmodel.config import RankingConfig
from ffmodel.overlay.applicator import OverlayResult
from ffmodel.ranking.ranker import (
    RankedPlayer,
    _compute_replacement_points,
    compute_rankings,
    rankings_to_dataframe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ranking_config():
    return RankingConfig(
        ranking_objective="median",
        replacement_level={"QB": 2, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
        vor_method="simple",
    )


@pytest.fixture
def overlay_results():
    return [
        OverlayResult("QB1", "QB", 300.0, 300.0, 0.0, 1.0, False, 0),
        OverlayResult("QB2", "QB", 250.0, 250.0, 0.0, 1.0, False, 0),
        OverlayResult("QB3", "QB", 200.0, 200.0, 0.0, 1.0, False, 0),
        OverlayResult("RB1", "RB", 280.0, 280.0, 0.0, 1.0, False, 0),
        OverlayResult("RB2", "RB", 220.0, 220.0, 0.0, 1.0, False, 0),
        OverlayResult("WR1", "WR", 260.0, 260.0, 0.0, 1.0, False, 0),
        OverlayResult("WR2", "WR", 210.0, 210.0, 0.0, 1.0, False, 0),
        OverlayResult("TE1", "TE", 180.0, 180.0, 0.0, 1.0, False, 0),
        OverlayResult("K1", "K", 130.0, 130.0, 0.0, 1.0, False, 0),
        OverlayResult("DEF1", "DEF", 120.0, 120.0, 0.0, 1.0, False, 0),
    ]


@pytest.fixture
def projections_df():
    return pd.DataFrame([
        {"player_id": "QB1", "position": "QB", "games_active": 17.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "QB2", "position": "QB", "games_active": 16.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "QB3", "position": "QB", "games_active": 15.0, "is_rookie": True, "is_team_changer": False},
        {"player_id": "RB1", "position": "RB", "games_active": 16.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "RB2", "position": "RB", "games_active": 14.0, "is_rookie": False, "is_team_changer": True},
        {"player_id": "WR1", "position": "WR", "games_active": 17.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "WR2", "position": "WR", "games_active": 15.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "TE1", "position": "TE", "games_active": 16.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "K1", "position": "K", "games_active": 17.0, "is_rookie": False, "is_team_changer": False},
        {"player_id": "DEF1", "position": "DEF", "games_active": 17.0, "is_rookie": False, "is_team_changer": False},
    ])


@pytest.fixture
def uncertainty_df():
    return pd.DataFrame([
        {"player_id": "QB1", "position": "QB", "fantasy_points_p25": 250.0, "fantasy_points_p50": 300.0, "fantasy_points_p75": 350.0},
        {"player_id": "QB2", "position": "QB", "fantasy_points_p25": 200.0, "fantasy_points_p50": 250.0, "fantasy_points_p75": 300.0},
        {"player_id": "QB3", "position": "QB", "fantasy_points_p25": 150.0, "fantasy_points_p50": 200.0, "fantasy_points_p75": 250.0},
        {"player_id": "RB1", "position": "RB", "fantasy_points_p25": 230.0, "fantasy_points_p50": 280.0, "fantasy_points_p75": 330.0},
        {"player_id": "RB2", "position": "RB", "fantasy_points_p25": 180.0, "fantasy_points_p50": 220.0, "fantasy_points_p75": 270.0},
        {"player_id": "WR1", "position": "WR", "fantasy_points_p25": 210.0, "fantasy_points_p50": 260.0, "fantasy_points_p75": 310.0},
        {"player_id": "WR2", "position": "WR", "fantasy_points_p25": 170.0, "fantasy_points_p50": 210.0, "fantasy_points_p75": 250.0},
        {"player_id": "TE1", "position": "TE", "fantasy_points_p25": 140.0, "fantasy_points_p50": 180.0, "fantasy_points_p75": 220.0},
        {"player_id": "K1", "position": "K", "fantasy_points_p25": 100.0, "fantasy_points_p50": 130.0, "fantasy_points_p75": 160.0},
        {"player_id": "DEF1", "position": "DEF", "fantasy_points_p25": 90.0, "fantasy_points_p50": 120.0, "fantasy_points_p75": 150.0},
    ])


# ---------------------------------------------------------------------------
# Tests: compute_rankings
# ---------------------------------------------------------------------------

class TestComputeRankings:
    def test_overall_rank_order(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        assert ranked[0].player_id == "QB1"
        assert ranked[0].overall_rank == 1
        for i in range(len(ranked) - 1):
            assert ranked[i].total_points >= ranked[i + 1].total_points

    def test_position_ranks_contiguous(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        by_pos: dict[str, list[int]] = {}
        for r in ranked:
            by_pos.setdefault(r.position, []).append(r.position_rank)
        for pos, ranks in by_pos.items():
            assert sorted(ranks) == list(range(1, len(ranks) + 1)), f"{pos} ranks not contiguous"

    def test_overall_ranks_contiguous(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        overall_ranks = [r.overall_rank for r in ranked]
        assert sorted(overall_ranks) == list(range(1, len(ranked) + 1))

    def test_vor_computed(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        qb1 = [r for r in ranked if r.player_id == "QB1"][0]
        qb2 = [r for r in ranked if r.player_id == "QB2"][0]
        assert qb1.vor > qb2.vor

    def test_replacement_level_player_has_zero_vor(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        qb2 = [r for r in ranked if r.player_id == "QB2"][0]
        assert qb2.vor == 0.0

    def test_rookie_flag_preserved(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        qb3 = [r for r in ranked if r.player_id == "QB3"][0]
        assert qb3.is_rookie is True

    def test_team_changer_flag_preserved(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        rb2 = [r for r in ranked if r.player_id == "RB2"][0]
        assert rb2.is_team_changer is True

    def test_upside_objective_uses_p75(self, overlay_results, projections_df, uncertainty_df):
        upside_config = RankingConfig(
            ranking_objective="upside",
            replacement_level={"QB": 2, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
            vor_method="simple",
        )
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, upside_config)
        qb1 = [r for r in ranked if r.player_id == "QB1"][0]
        assert qb1.total_points == 350.0


# ---------------------------------------------------------------------------
# Tests: _compute_replacement_points
# ---------------------------------------------------------------------------

class TestComputeReplacementPoints:
    def test_replacement_at_nth_player(self):
        entries = [
            {"position": "QB", "total_points": 300.0},
            {"position": "QB", "total_points": 250.0},
            {"position": "QB", "total_points": 200.0},
        ]
        result = _compute_replacement_points(entries, {"QB": 2})
        assert result["QB"] == 250.0

    def test_replacement_when_n_exceeds_pool(self):
        entries = [
            {"position": "K", "total_points": 130.0},
        ]
        result = _compute_replacement_points(entries, {"K": 5})
        assert result["K"] == 130.0


# ---------------------------------------------------------------------------
# Tests: rankings_to_dataframe
# ---------------------------------------------------------------------------

class TestRankingsToDataframe:
    def test_produces_correct_columns(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        df = rankings_to_dataframe(ranked)
        required = {"player_id", "position", "overall_rank", "position_rank", "total_points", "vor", "games_active"}
        assert required.issubset(set(df.columns))

    def test_row_count_matches(self, overlay_results, projections_df, uncertainty_df, ranking_config):
        ranked = compute_rankings(overlay_results, projections_df, uncertainty_df, ranking_config)
        df = rankings_to_dataframe(ranked)
        assert len(df) == len(ranked)
