"""Tests for QA checks module."""

import pandas as pd
import pytest

from ffmodel.config import (
    DSTScoringConfig,
    KickerScoringConfig,
    OffenseScoringConfig,
    ScoringConfig,
)
from ffmodel.qa.checks import (
    QAResult,
    qc_001_no_duplicate_keys,
    qc_002_canonical_ids,
    qc_003_team_shares,
    qc_004_range_checks,
    qc_006_missingness,
    qc_007_no_leakage,
    qc_008_manual_factor_metadata,
    qc_010_dst_brackets,
    qc_011_kicker_reconciliation,
    qc_012_output_schema,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scoring_config():
    return ScoringConfig(
        offense=OffenseScoringConfig(
            passing_yards_per_point=25.0, passing_td=4.0, interception=-2.0,
            rushing_yards_per_point=10.0, rushing_td=6.0, reception=0.5,
            receiving_yards_per_point=10.0, receiving_td=6.0, return_td=6.0,
            two_pt_conversion=2.0, fumble_lost=-2.0, offensive_fumble_return_td=6.0,
        ),
        kicker=KickerScoringConfig(
            fg_0_19=3.0, fg_20_29=3.0, fg_30_39=3.0,
            fg_40_49=4.0, fg_50_plus=5.0, pat_made=1.0,
        ),
        dst=DSTScoringConfig(
            sack=1.0, interception=2.0, fumble_recovery=2.0, touchdown=6.0,
            safety=2.0, block_kick=2.0, return_td=6.0, extra_point_return=2.0,
            points_allowed_brackets=(
                (0, 0, 10.0), (1, 6, 7.0), (7, 13, 4.0),
                (14, 20, 1.0), (21, 27, 0.0), (28, 34, -1.0), (35, 999, -4.0),
            ),
        ),
    )


@pytest.fixture
def valid_rankings_df():
    return pd.DataFrame([
        {"player_id": "P1", "position": "QB", "overall_rank": 1,
         "position_rank": 1, "total_points": 300.0, "vor": 50.0,
         "games_active": 16.0},
        {"player_id": "P2", "position": "RB", "overall_rank": 2,
         "position_rank": 1, "total_points": 280.0, "vor": 60.0,
         "games_active": 15.0},
    ])


# ---------------------------------------------------------------------------
# QC-001: No duplicate keys
# ---------------------------------------------------------------------------

class TestQC001:
    def test_pass_no_duplicates(self, valid_rankings_df):
        result = qc_001_no_duplicate_keys(valid_rankings_df)
        assert result.passed is True

    def test_fail_with_duplicates(self):
        df = pd.DataFrame([
            {"player_id": "P1", "position": "QB"},
            {"player_id": "P1", "position": "QB"},
        ])
        result = qc_001_no_duplicate_keys(df)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-002: Canonical IDs
# ---------------------------------------------------------------------------

class TestQC002:
    def test_pass_all_ids_present(self, valid_rankings_df):
        result = qc_002_canonical_ids(valid_rankings_df)
        assert result.passed is True

    def test_fail_missing_id(self):
        df = pd.DataFrame([
            {"player_id": "P1", "position": "QB"},
            {"player_id": "", "position": "RB"},
        ])
        result = qc_002_canonical_ids(df)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-003: Team shares
# ---------------------------------------------------------------------------

class TestQC003:
    def test_pass_valid_shares(self):
        df = pd.DataFrame([
            {"team": "KC", "target_share": 0.30},
            {"team": "KC", "target_share": 0.40},
            {"team": "KC", "target_share": 0.25},
        ])
        result = qc_003_team_shares(df)
        assert result.passed is True

    def test_fail_shares_exceed_tolerance(self):
        df = pd.DataFrame([
            {"team": "KC", "target_share": 0.60},
            {"team": "KC", "target_share": 0.60},
        ])
        result = qc_003_team_shares(df)
        assert result.passed is False

    def test_pass_empty_df(self):
        result = qc_003_team_shares(pd.DataFrame())
        assert result.passed is True


# ---------------------------------------------------------------------------
# QC-004: Range checks
# ---------------------------------------------------------------------------

class TestQC004:
    def test_pass_valid_ranges(self):
        df = pd.DataFrame([
            {"games_active": 16.0, "pass_yd_season_total": 4000.0},
            {"games_active": 14.0, "rush_yd_season_total": 1200.0},
        ])
        result = qc_004_range_checks(df)
        assert result.passed is True

    def test_fail_games_over_17(self):
        df = pd.DataFrame([{"games_active": 18.0}])
        result = qc_004_range_checks(df)
        assert result.passed is False

    def test_fail_negative_games(self):
        df = pd.DataFrame([{"games_active": -1.0}])
        result = qc_004_range_checks(df)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-006: Missingness
# ---------------------------------------------------------------------------

class TestQC006:
    def test_pass_no_missing(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result = qc_006_missingness(df)
        assert result.passed is True

    def test_fail_high_missingness(self):
        df = pd.DataFrame({"a": [1, None, None, None, None]})
        result = qc_006_missingness(df, threshold=0.10)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-007: No leakage
# ---------------------------------------------------------------------------

class TestQC007:
    def test_pass_no_season_column(self):
        df = pd.DataFrame({"player_id": ["P1"]})
        result = qc_007_no_leakage(df, 2026)
        assert result.passed is True

    def test_fail_future_season(self):
        df = pd.DataFrame({"season": [2025, 2026]})
        result = qc_007_no_leakage(df, 2026)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-008: Manual factor metadata
# ---------------------------------------------------------------------------

class TestQC008:
    def test_pass_empty(self):
        result = qc_008_manual_factor_metadata(pd.DataFrame())
        assert result.passed is True

    def test_pass_valid(self):
        df = pd.DataFrame([{
            "owner": "bsavage", "rationale": "Scheme fit upgrade",
        }])
        result = qc_008_manual_factor_metadata(df)
        assert result.passed is True

    def test_fail_missing_owner(self):
        df = pd.DataFrame([{
            "owner": "", "rationale": "Scheme fit",
        }])
        result = qc_008_manual_factor_metadata(df)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-010: DST brackets
# ---------------------------------------------------------------------------

class TestQC010:
    def test_pass_valid_brackets(self, scoring_config):
        result = qc_010_dst_brackets(scoring_config)
        assert result.passed is True

    def test_fail_inverted_bracket(self):
        bad_config = ScoringConfig(
            offense=OffenseScoringConfig(
                passing_yards_per_point=25.0, passing_td=4.0, interception=-2.0,
                rushing_yards_per_point=10.0, rushing_td=6.0, reception=0.5,
                receiving_yards_per_point=10.0, receiving_td=6.0, return_td=6.0,
                two_pt_conversion=2.0, fumble_lost=-2.0, offensive_fumble_return_td=6.0,
            ),
            kicker=KickerScoringConfig(
                fg_0_19=3.0, fg_20_29=3.0, fg_30_39=3.0,
                fg_40_49=4.0, fg_50_plus=5.0, pat_made=1.0,
            ),
            dst=DSTScoringConfig(
                sack=1.0, interception=2.0, fumble_recovery=2.0, touchdown=6.0,
                safety=2.0, block_kick=2.0, return_td=6.0, extra_point_return=2.0,
                points_allowed_brackets=((10, 0, 10.0),),
            ),
        )
        result = qc_010_dst_brackets(bad_config)
        assert result.passed is False


# ---------------------------------------------------------------------------
# QC-011: Kicker reconciliation
# ---------------------------------------------------------------------------

class TestQC011:
    def test_pass_valid_kicker(self):
        df = pd.DataFrame([{
            "position": "K",
            "fg_0_19_season_total": 2.0,
            "fg_20_29_season_total": 5.0,
            "fg_30_39_season_total": 8.0,
            "fg_40_49_season_total": 6.0,
            "fg_50_plus_season_total": 3.0,
        }])
        result = qc_011_kicker_reconciliation(df)
        assert result.passed is True

    def test_pass_no_kickers(self):
        df = pd.DataFrame([{"position": "QB"}])
        result = qc_011_kicker_reconciliation(df)
        assert result.passed is True


# ---------------------------------------------------------------------------
# QC-012: Output schema
# ---------------------------------------------------------------------------

class TestQC012:
    def test_pass_valid_schema(self, valid_rankings_df):
        result = qc_012_output_schema(valid_rankings_df)
        assert result.passed is True

    def test_fail_missing_columns(self):
        df = pd.DataFrame([{"player_id": "P1"}])
        result = qc_012_output_schema(df)
        assert result.passed is False


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------

class TestRunAllChecks:
    def test_returns_12_results(self, scoring_config):
        rankings_df = pd.DataFrame([{
            "player_id": "P1", "position": "QB", "overall_rank": 1,
            "position_rank": 1, "total_points": 300.0, "vor": 50.0,
            "games_active": 16.0,
        }])
        proj_df = pd.DataFrame([{
            "player_id": "P1", "position": "QB", "games_active": 16.0,
        }])
        unc_df = pd.DataFrame([{
            "player_id": "P1", "position": "QB",
            "fantasy_points_p25": 250.0, "fantasy_points_p50": 300.0,
            "fantasy_points_p75": 350.0,
        }])
        manual_df = pd.DataFrame()
        role_df = pd.DataFrame()
        team_ctx_df = pd.DataFrame()

        results = run_all_checks(
            rankings_df, proj_df, unc_df, manual_df,
            role_df, team_ctx_df, scoring_config, 2026,
        )
        assert len(results) == 12
        assert all(isinstance(r, QAResult) for r in results)
