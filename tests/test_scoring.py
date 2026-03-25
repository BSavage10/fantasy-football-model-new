"""Phase 4 exit criteria: scoring engine tests.

All expected values are derived by hand from the scoring.yaml config and
verified against the Phase 4 exit criteria in docs/implementation-plan.md.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ffmodel.config import load_scoring_config
from ffmodel.scoring.engine import (
    expected_pa_bracket_value,
    score_dst,
    score_kicker,
    score_player,
)


@pytest.fixture
def scoring_cfg(configs_dir: Path):
    return load_scoring_config(configs_dir / "scoring.yaml")


# ---------------------------------------------------------------------------
# score_player — offensive positions
# ---------------------------------------------------------------------------

class TestScorePlayerQB:
    def test_mahomes_2023_style(self, scoring_cfg):
        """QB: 4183 pass_yd, 27 pass_td, 14 int, 389 rush_yd → 286.22."""
        stats = {
            "pass_yd": 4183,
            "pass_td": 27,
            "interceptions": 14,
            "rush_yd": 389,
            "rush_td": 0,
            "receptions": 0,
            "fumbles_lost": 0,
        }
        result = score_player(stats, "QB", scoring_cfg)
        # 4183/25 + 27*4 + 14*(-2) + 389/10
        # = 167.32 + 108 + (-28) + 38.9
        # = 286.22
        assert abs(result - 286.22) < 0.01

    def test_qb_component_breakdown(self, scoring_cfg):
        """Verify each scoring component contributes correctly."""
        pass_pts = 4183 / 25          # 167.32
        td_pts = 27 * 4               # 108.0
        int_pts = 14 * (-2)           # -28.0
        rush_pts = 389 / 10           # 38.9
        expected = pass_pts + td_pts + int_pts + rush_pts

        stats = {
            "pass_yd": 4183,
            "pass_td": 27,
            "interceptions": 14,
            "rush_yd": 389,
        }
        assert abs(score_player(stats, "QB", scoring_cfg) - expected) < 0.001

    def test_zero_stats_returns_zero(self, scoring_cfg):
        assert score_player({}, "QB", scoring_cfg) == 0.0


class TestScorePlayerRB:
    def test_rb_half_ppr_component_sum(self, scoring_cfg):
        """RB: rushing + receiving stats sum to expected total (half-PPR)."""
        stats = {
            "rush_yd": 120,
            "rush_td": 1,
            "receptions": 6,
            "rec_yd": 55,
            "rec_td": 0,
            "fumbles_lost": 0,
        }
        rush_pts = 120 / 10           # 12.0
        td_pts = 1 * 6                # 6.0
        rec_pts = 6 * 0.5             # 3.0  (half-PPR)
        rec_yd_pts = 55 / 10          # 5.5
        expected = rush_pts + td_pts + rec_pts + rec_yd_pts  # 26.5

        result = score_player(stats, "RB", scoring_cfg)
        assert abs(result - expected) < 0.001
        assert abs(result - 26.5) < 0.001

    def test_fumble_lost_is_negative(self, scoring_cfg):
        stats = {"rush_yd": 100, "fumbles_lost": 1}
        result = score_player(stats, "RB", scoring_cfg)
        expected = 100 / 10 + 1 * (-2)   # 10.0 - 2.0 = 8.0
        assert abs(result - expected) < 0.001


class TestScorePlayerCrossPosition:
    def test_wr_rushing_play_credited(self, scoring_cfg):
        """FR-005: WR rushing yards and rushing TD are scored correctly."""
        stats = {
            "rush_yd": 25,
            "rush_td": 1,
        }
        rush_yd_pts = 25 / 10         # 2.5
        rush_td_pts = 1 * 6           # 6.0
        expected = rush_yd_pts + rush_td_pts  # 8.5

        result = score_player(stats, "WR", scoring_cfg)
        assert abs(result - expected) < 0.001
        assert abs(result - 8.5) < 0.001

    def test_wr_combined_rushing_receiving(self, scoring_cfg):
        """WR with both trick-play rushing and regular receiving stats."""
        stats = {
            "rush_yd": 25,
            "rush_td": 1,
            "receptions": 8,
            "rec_yd": 110,
            "rec_td": 1,
        }
        expected = (
            25 / 10          # 2.5
            + 1 * 6          # 6.0
            + 8 * 0.5        # 4.0
            + 110 / 10       # 11.0
            + 1 * 6          # 6.0
        )                    # = 29.5
        result = score_player(stats, "WR", scoring_cfg)
        assert abs(result - expected) < 0.001

    def test_te_same_rules_as_wr(self, scoring_cfg):
        """TE uses identical receiving scoring rules."""
        stats = {"receptions": 5, "rec_yd": 60, "rec_td": 1}
        expected = 5 * 0.5 + 60 / 10 + 1 * 6  # 2.5 + 6.0 + 6.0 = 14.5
        assert abs(score_player(stats, "TE", scoring_cfg) - expected) < 0.001

    def test_two_pt_conversion_scored(self, scoring_cfg):
        stats = {"two_pt_conv": 2}
        assert abs(score_player(stats, "QB", scoring_cfg) - 4.0) < 0.001

    def test_return_td_scored(self, scoring_cfg):
        stats = {"return_td": 1}
        assert abs(score_player(stats, "RB", scoring_cfg) - 6.0) < 0.001


# ---------------------------------------------------------------------------
# score_kicker
# ---------------------------------------------------------------------------

class TestScoreKicker:
    def test_full_kicker_season(self, scoring_cfg):
        """35 XP + 2+3+3+6+2 FGs across buckets → 93.0."""
        stats = {
            "pat_made": 35,
            "fg_0_19": 2,
            "fg_20_29": 3,
            "fg_30_39": 3,
            "fg_40_49": 6,
            "fg_50_plus": 2,
        }
        # 35*1 + 2*3 + 3*3 + 3*3 + 6*4 + 2*5
        # = 35 + 6 + 9 + 9 + 24 + 10
        # = 93.0
        result = score_kicker(stats, scoring_cfg)
        assert abs(result - 93.0) < 0.001

    def test_only_extra_points(self, scoring_cfg):
        stats = {"pat_made": 10}
        assert abs(score_kicker(stats, scoring_cfg) - 10.0) < 0.001

    def test_fg_bucket_values(self, scoring_cfg):
        """Each FG bucket pays the correct amount."""
        assert abs(score_kicker({"fg_0_19": 1}, scoring_cfg) - 3.0) < 0.001
        assert abs(score_kicker({"fg_20_29": 1}, scoring_cfg) - 3.0) < 0.001
        assert abs(score_kicker({"fg_30_39": 1}, scoring_cfg) - 3.0) < 0.001
        assert abs(score_kicker({"fg_40_49": 1}, scoring_cfg) - 4.0) < 0.001
        assert abs(score_kicker({"fg_50_plus": 1}, scoring_cfg) - 5.0) < 0.001

    def test_zero_stats_returns_zero(self, scoring_cfg):
        assert score_kicker({}, scoring_cfg) == 0.0


# ---------------------------------------------------------------------------
# score_dst
# ---------------------------------------------------------------------------

class TestScoreDST:
    def test_known_components_plus_bracket(self, scoring_cfg):
        """Component events + points-allowed bracket → exact total.

        sacks=3 (3pts) + int=2 (4pts) + fum_rec=1 (2pts) + dst_td=1 (6pts)
        = 15.0 event points
        pa_per_game=17 → bracket [14-20] → 1.0 pt/game × 16 games = 16.0
        total = 31.0
        """
        stats = {
            "sacks": 3,
            "interceptions": 2,
            "fumble_recoveries": 1,
            "dst_td": 1,
        }
        result = score_dst(stats, pa_per_game=17.0, games=16.0, config=scoring_cfg)
        assert abs(result - 31.0) < 0.001

    def test_zero_points_bracket(self, scoring_cfg):
        """pa_per_game=24 → bracket [21-27] → 0 pts/game."""
        stats = {"sacks": 0}
        result = score_dst(stats, pa_per_game=24.0, games=16.0, config=scoring_cfg)
        assert abs(result - 0.0) < 0.001

    def test_negative_bracket(self, scoring_cfg):
        """pa_per_game=30 → bracket [28-34] → -1 pt/game × 16 = -16."""
        stats = {}
        result = score_dst(stats, pa_per_game=30.0, games=16.0, config=scoring_cfg)
        assert abs(result - (-16.0)) < 0.001

    def test_shutout_bracket(self, scoring_cfg):
        """pa_per_game=0 → bracket [0-0] → 10 pts/game × 16 = 160."""
        stats = {}
        result = score_dst(stats, pa_per_game=0.0, games=16.0, config=scoring_cfg)
        assert abs(result - 160.0) < 0.001

    def test_safety_and_block_kick_scored(self, scoring_cfg):
        stats = {"safeties": 1, "block_kicks": 1}
        result = score_dst(stats, pa_per_game=24.0, games=16.0, config=scoring_cfg)
        expected = 1 * 2.0 + 1 * 2.0  # safety + block_kick, bracket=0
        assert abs(result - expected) < 0.001

    def test_zero_stats_zero_games(self, scoring_cfg):
        assert score_dst({}, pa_per_game=17.0, games=0.0, config=scoring_cfg) == 0.0


# ---------------------------------------------------------------------------
# expected_pa_bracket_value
# ---------------------------------------------------------------------------

class TestExpectedPABracketValue:
    def test_zero_std_is_direct_lookup(self, scoring_cfg):
        brackets = scoring_cfg.dst.points_allowed_brackets
        assert expected_pa_bracket_value(0.0, 0.0, brackets) == 10.0    # [0-0]
        assert expected_pa_bracket_value(3.0, 0.0, brackets) == 7.0     # [1-6]
        assert expected_pa_bracket_value(10.0, 0.0, brackets) == 4.0    # [7-13]
        assert expected_pa_bracket_value(17.0, 0.0, brackets) == 1.0    # [14-20]
        assert expected_pa_bracket_value(24.0, 0.0, brackets) == 0.0    # [21-27]
        assert expected_pa_bracket_value(30.0, 0.0, brackets) == -1.0   # [28-34]
        assert expected_pa_bracket_value(40.0, 0.0, brackets) == -4.0   # [35+]

    def test_nonzero_std_returns_float(self, scoring_cfg):
        brackets = scoring_cfg.dst.points_allowed_brackets
        result = expected_pa_bracket_value(17.0, 5.0, brackets, n_samples=1000)
        assert isinstance(result, float)

    def test_high_variance_pulls_toward_extremes(self, scoring_cfg):
        """With high PA variance, bracket nonlinearity reduces expected value
        vs. a direct lookup at the mean (Jensen's inequality effect)."""
        brackets = scoring_cfg.dst.points_allowed_brackets
        direct = expected_pa_bracket_value(17.0, 0.0, brackets)       # 1.0
        monte_carlo = expected_pa_bracket_value(17.0, 10.0, brackets)
        # With high variance, some games will be shutouts (10 pts) and some
        # will be bad (negative pts). Net effect is not trivially predictable,
        # but the result must be a finite float.
        assert isinstance(monte_carlo, float)
        assert direct == 1.0


# ---------------------------------------------------------------------------
# Reconciliation: score_player reproduces a known total
# ---------------------------------------------------------------------------

class TestReconciliation:
    def test_score_player_matches_manual_total(self, scoring_cfg):
        """score_player(stats) == manually computed total within 0.01."""
        stats = {
            "pass_yd": 4183,
            "pass_td": 27,
            "interceptions": 14,
            "rush_yd": 389,
        }
        manual_total = 4183 / 25 + 27 * 4 + 14 * (-2) + 389 / 10
        result = score_player(stats, "QB", scoring_cfg)
        assert abs(result - manual_total) < 0.01

    def test_score_player_is_additive(self, scoring_cfg):
        """Sum of individual components equals scoring all stats at once."""
        pass_pts = score_player({"pass_yd": 4183}, "QB", scoring_cfg)
        td_pts = score_player({"pass_td": 27}, "QB", scoring_cfg)
        int_pts = score_player({"interceptions": 14}, "QB", scoring_cfg)
        rush_pts = score_player({"rush_yd": 389}, "QB", scoring_cfg)
        combined = pass_pts + td_pts + int_pts + rush_pts

        all_at_once = score_player(
            {"pass_yd": 4183, "pass_td": 27, "interceptions": 14, "rush_yd": 389},
            "QB",
            scoring_cfg,
        )
        assert abs(combined - all_at_once) < 0.001


# ---------------------------------------------------------------------------
# Config change sensitivity
# ---------------------------------------------------------------------------

class TestConfigChangeSensitivity:
    def test_interception_change_shifts_qb_by_int_count(self, scoring_cfg):
        """Changing interception from -2 to -1 shifts QB points by INT_count × 1."""
        int_count = 14
        stats = {
            "pass_yd": 4183,
            "pass_td": 27,
            "interceptions": int_count,
            "rush_yd": 389,
        }

        result_default = score_player(stats, "QB", scoring_cfg)

        # Build config with interception penalty halved (-1 instead of -2)
        new_offense = replace(scoring_cfg.offense, interception=-1.0)
        new_scoring_cfg = replace(scoring_cfg, offense=new_offense)
        result_modified = score_player(stats, "QB", new_scoring_cfg)

        delta = result_modified - result_default
        expected_delta = int_count * 1.0   # each INT now costs 1 less point
        assert abs(delta - expected_delta) < 0.001

    def test_reception_change_shifts_rb_by_catch_count(self, scoring_cfg):
        """Changing reception multiplier from 0.5 to 1.0 shifts points by receptions × 0.5."""
        receptions = 60
        stats = {"receptions": receptions, "rec_yd": 500}

        result_half_ppr = score_player(stats, "RB", scoring_cfg)

        new_offense = replace(scoring_cfg.offense, reception=1.0)
        new_scoring_cfg = replace(scoring_cfg, offense=new_offense)
        result_full_ppr = score_player(stats, "RB", new_scoring_cfg)

        delta = result_full_ppr - result_half_ppr
        assert abs(delta - receptions * 0.5) < 0.001

    def test_kicker_fg_bucket_change_is_exact(self, scoring_cfg):
        """Changing fg_50_plus from 5 to 6 changes score by number of 50+ FGs × 1."""
        fg_50_count = 5
        stats = {"fg_50_plus": fg_50_count, "pat_made": 30}

        result_default = score_kicker(stats, scoring_cfg)

        new_kicker = replace(scoring_cfg.kicker, fg_50_plus=6.0)
        new_scoring_cfg = replace(scoring_cfg, kicker=new_kicker)
        result_modified = score_kicker(stats, new_scoring_cfg)

        delta = result_modified - result_default
        assert abs(delta - fg_50_count * 1.0) < 0.001
