"""Tests for the overlay applicator module."""

import pandas as pd
import pytest

from ffmodel.config import OverlayConfig
from ffmodel.overlay.applicator import (
    OverlayResult,
    apply_overlays,
    combine_multipliers,
    dampen_score,
    factor_to_multiplier,
)


# ---------------------------------------------------------------------------
# Unit tests: dampen_score
# ---------------------------------------------------------------------------

class TestDampenScore:
    def test_high_confidence_no_dampening(self):
        result = dampen_score(0.80, 0.50, 0.30)
        assert result == 0.80

    def test_neutral_score_unchanged(self):
        result = dampen_score(0.50, 0.10, 0.30)
        assert result == 0.50

    def test_low_confidence_dampens_toward_neutral(self):
        result = dampen_score(1.0, 0.15, 0.30)
        expected = 0.50 + (0.15 / 0.30) * (1.0 - 0.50)
        assert abs(result - expected) < 1e-9

    def test_zero_confidence_returns_neutral(self):
        result = dampen_score(0.80, 0.0, 0.30)
        assert result == 0.50

    def test_at_threshold_no_dampening(self):
        result = dampen_score(0.80, 0.30, 0.30)
        assert result == 0.80

    def test_low_score_dampens_upward(self):
        result = dampen_score(0.0, 0.15, 0.30)
        expected = 0.50 + (0.15 / 0.30) * (0.0 - 0.50)
        assert abs(result - expected) < 1e-9


# ---------------------------------------------------------------------------
# Unit tests: factor_to_multiplier
# ---------------------------------------------------------------------------

class TestFactorToMultiplier:
    def test_neutral_score_gives_one(self):
        result = factor_to_multiplier(0.50, 0.15)
        assert result == 1.0

    def test_max_score_gives_positive_boost(self):
        result = factor_to_multiplier(1.0, 0.15)
        assert abs(result - 1.15) < 1e-9

    def test_min_score_gives_negative_adjustment(self):
        result = factor_to_multiplier(0.0, 0.15)
        assert abs(result - 0.85) < 1e-9

    def test_custom_max_effect(self):
        result = factor_to_multiplier(0.75, 0.20)
        expected = 1.0 + (0.75 - 0.50) * 2 * 0.20
        assert abs(result - expected) < 1e-9


# ---------------------------------------------------------------------------
# Unit tests: combine_multipliers
# ---------------------------------------------------------------------------

class TestCombineMultipliers:
    def test_empty_returns_one(self):
        assert combine_multipliers([], 0.25) == 1.0

    def test_single_multiplier(self):
        assert combine_multipliers([1.10], 0.25) == 1.10

    def test_multiple_multiply(self):
        result = combine_multipliers([1.10, 1.05], 0.25)
        expected = 1.10 * 1.05
        assert abs(result - expected) < 1e-9

    def test_cap_upper(self):
        result = combine_multipliers([1.20, 1.20], 0.25)
        assert result == 1.25

    def test_cap_lower(self):
        result = combine_multipliers([0.70, 0.80], 0.25)
        assert result == 0.75


# ---------------------------------------------------------------------------
# Integration tests: apply_overlays
# ---------------------------------------------------------------------------

class TestApplyOverlays:
    @pytest.fixture
    def overlay_config(self):
        return OverlayConfig(
            enabled=True,
            max_effect_per_factor=0.15,
            max_total_effect=0.25,
            low_confidence_threshold=0.30,
        )

    @pytest.fixture
    def projections_df(self):
        return pd.DataFrame([
            {"player_id": "P1", "position": "QB", "games_active": 16.0,
             "is_rookie": False, "is_team_changer": False},
            {"player_id": "P2", "position": "RB", "games_active": 14.0,
             "is_rookie": False, "is_team_changer": False},
        ])

    @pytest.fixture
    def uncertainty_df(self):
        return pd.DataFrame([
            {"player_id": "P1", "position": "QB",
             "fantasy_points_p25": 200.0, "fantasy_points_p50": 250.0, "fantasy_points_p75": 300.0},
            {"player_id": "P2", "position": "RB",
             "fantasy_points_p25": 100.0, "fantasy_points_p50": 150.0, "fantasy_points_p75": 200.0},
        ])

    def test_no_factors_returns_model_only(self, projections_df, uncertainty_df, overlay_config):
        empty_factors = pd.DataFrame(columns=[
            "entity_id", "entity_type", "factor_name", "score_normalized", "confidence",
        ])
        results = apply_overlays(projections_df, uncertainty_df, empty_factors, overlay_config)
        assert len(results) == 2
        assert results[0].overlay_delta == 0.0
        assert results[0].overlay_adjusted_points == 250.0
        assert results[0].factors_applied == 0

    def test_player_factor_applied(self, projections_df, uncertainty_df, overlay_config):
        factors = pd.DataFrame([{
            "entity_id": "P1", "entity_type": "player",
            "factor_name": "scheme_fit", "score_normalized": 0.80,
            "confidence": 0.50,
        }])
        results = apply_overlays(projections_df, uncertainty_df, factors, overlay_config)
        p1 = [r for r in results if r.player_id == "P1"][0]
        assert p1.factors_applied == 1
        assert p1.overlay_adjusted_points > 250.0
        assert p1.overlay_delta > 0.0

    def test_disabled_overlay_returns_model_only(self, projections_df, uncertainty_df):
        disabled = OverlayConfig(
            enabled=False,
            max_effect_per_factor=0.15,
            max_total_effect=0.25,
            low_confidence_threshold=0.30,
        )
        factors = pd.DataFrame([{
            "entity_id": "P1", "entity_type": "player",
            "factor_name": "scheme_fit", "score_normalized": 1.0,
            "confidence": 1.0,
        }])
        results = apply_overlays(projections_df, uncertainty_df, factors, disabled)
        assert all(r.overlay_delta == 0.0 for r in results)

    def test_manual_heavy_flag(self, projections_df, uncertainty_df, overlay_config):
        factors = pd.DataFrame([{
            "entity_id": "P1", "entity_type": "player",
            "factor_name": "scheme_fit", "score_normalized": 1.0,
            "confidence": 1.0,
        }])
        results = apply_overlays(projections_df, uncertainty_df, factors, overlay_config)
        p1 = [r for r in results if r.player_id == "P1"][0]
        assert p1.manual_heavy is True

    def test_low_confidence_dampening_reduces_effect(self, projections_df, uncertainty_df, overlay_config):
        high_conf = pd.DataFrame([{
            "entity_id": "P1", "entity_type": "player",
            "factor_name": "scheme_fit", "score_normalized": 1.0,
            "confidence": 1.0,
        }])
        low_conf = pd.DataFrame([{
            "entity_id": "P1", "entity_type": "player",
            "factor_name": "scheme_fit", "score_normalized": 1.0,
            "confidence": 0.10,
        }])
        high_results = apply_overlays(projections_df, uncertainty_df, high_conf, overlay_config)
        low_results = apply_overlays(projections_df, uncertainty_df, low_conf, overlay_config)
        high_delta = [r for r in high_results if r.player_id == "P1"][0].overlay_delta
        low_delta = [r for r in low_results if r.player_id == "P1"][0].overlay_delta
        assert abs(high_delta) > abs(low_delta)
