"""Config-driven fantasy point scoring engine.

Three pure functions translate projected stats into fantasy points:
  score_player  — offensive players (QB/RB/WR/TE); applies all stat
                  multipliers regardless of position (FR-005).
  score_dst     — defense/special teams; component events + nonlinear
                  points-allowed bracket.
  score_kicker  — kicker; XP + field-goal distance buckets.

Plus a utility:
  expected_pa_bracket_value — Monte Carlo expected value of points-allowed
                               bracket given a distribution of PA per game.
"""

from __future__ import annotations

import numpy as np

from ffmodel.config import ScoringConfig


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bracket_lookup(pa: float, brackets: tuple) -> float:
    """Return the bracket points value for the given points-allowed total."""
    for lower, upper, pts in brackets:
        if lower <= pa <= upper:
            return float(pts)
    return float(brackets[-1][2])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_player(stats: dict, position: str, config: ScoringConfig) -> float:
    """Score an offensive player's season stats.

    Applies all offensive scoring rules regardless of position, so cross-
    category stats (WR rushing, RB passing trick plays) are credited correctly.

    Stats dict keys match player_week_fact column names:
        pass_yd, pass_td, interceptions, rush_yd, rush_td,
        receptions, rec_yd, rec_td, fumbles_lost, return_td,
        two_pt_conv, off_fumble_return_td
    """
    o = config.offense
    total = 0.0

    total += stats.get("pass_yd", 0.0) / o.passing_yards_per_point
    total += stats.get("pass_td", 0.0) * o.passing_td
    total += stats.get("interceptions", 0.0) * o.interception

    total += stats.get("rush_yd", 0.0) / o.rushing_yards_per_point
    total += stats.get("rush_td", 0.0) * o.rushing_td

    total += stats.get("receptions", 0.0) * o.reception
    total += stats.get("rec_yd", 0.0) / o.receiving_yards_per_point
    total += stats.get("rec_td", 0.0) * o.receiving_td

    total += stats.get("return_td", 0.0) * o.return_td
    total += stats.get("two_pt_conv", 0.0) * o.two_pt_conversion
    total += stats.get("fumbles_lost", 0.0) * o.fumble_lost
    total += stats.get("off_fumble_return_td", 0.0) * o.offensive_fumble_return_td

    return total


def expected_pa_bracket_value(
    mean_pa: float,
    std_pa: float,
    brackets: tuple,
    n_samples: int = 10000,
) -> float:
    """Expected per-game fantasy points from the DST points-allowed bracket.

    Because the bracket is nonlinear (concave in points-allowed), Jensen's
    inequality means E[bracket(PA)] != bracket(E[PA]).  When std_pa > 0 this
    function uses Monte Carlo sampling to compute the true expectation.

    Args:
        mean_pa:   Mean points allowed per game.
        std_pa:    Standard deviation of points allowed per game.
                   Pass 0.0 for a deterministic direct lookup.
        brackets:  Tuple of (lower, upper, points) bracket definitions from
                   DSTScoringConfig.points_allowed_brackets.
        n_samples: Number of Monte Carlo samples (ignored when std_pa == 0).

    Returns:
        Expected fantasy points per game from the points-allowed component.
    """
    if std_pa == 0.0:
        return _bracket_lookup(mean_pa, brackets)

    rng = np.random.default_rng(42)
    samples = rng.normal(mean_pa, std_pa, n_samples)
    samples = np.clip(samples, 0.0, None)
    values = np.array([_bracket_lookup(float(pa), brackets) for pa in samples])
    return float(values.mean())


def score_dst(
    stats: dict,
    pa_per_game: float,
    games: float,
    config: ScoringConfig,
) -> float:
    """Score a DST unit's season stats.

    Component event keys:
        sacks, interceptions, fumble_recoveries, dst_td,
        safeties, block_kicks, return_tds, extra_point_returns

    Args:
        stats:       Dict of DST counting stats for the season.
        pa_per_game: Expected points allowed per game (used for bracket lookup).
        games:       Projected games played.
        config:      ScoringConfig with DST rules.
    """
    d = config.dst
    total = 0.0

    total += stats.get("sacks", 0.0) * d.sack
    total += stats.get("interceptions", 0.0) * d.interception
    total += stats.get("fumble_recoveries", 0.0) * d.fumble_recovery
    total += stats.get("dst_td", 0.0) * d.touchdown
    total += stats.get("safeties", 0.0) * d.safety
    total += stats.get("block_kicks", 0.0) * d.block_kick
    total += stats.get("return_tds", 0.0) * d.return_td
    total += stats.get("extra_point_returns", 0.0) * d.extra_point_return

    bracket_value = _bracket_lookup(pa_per_game, d.points_allowed_brackets)
    total += bracket_value * games

    return total


def score_kicker(stats: dict, config: ScoringConfig) -> float:
    """Score a kicker's season stats.

    Stats dict keys:
        pat_made, fg_0_19, fg_20_29, fg_30_39, fg_40_49, fg_50_plus
    """
    k = config.kicker
    total = 0.0

    total += stats.get("pat_made", 0.0) * k.pat_made
    total += stats.get("fg_0_19", 0.0) * k.fg_0_19
    total += stats.get("fg_20_29", 0.0) * k.fg_20_29
    total += stats.get("fg_30_39", 0.0) * k.fg_30_39
    total += stats.get("fg_40_49", 0.0) * k.fg_40_49
    total += stats.get("fg_50_plus", 0.0) * k.fg_50_plus

    return total
