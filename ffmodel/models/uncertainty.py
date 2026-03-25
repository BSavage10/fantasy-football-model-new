"""Uncertainty estimation via bootstrap resampling.

For each player projection, perturbs per-game stats and games_active,
scores each sample, and returns P25/P50/P75 fantasy point totals.

Uses position-specific coefficients of variation rather than historical
backtest residuals (which require Phase 7). This is a reasonable v1
approximation that produces meaningful uncertainty bands.
"""

from __future__ import annotations

import numpy as np

from ffmodel.config import ScoringConfig
from ffmodel.models.base import StatProjection, UncertaintyResult
from ffmodel.scoring.engine import score_dst, score_kicker, score_player

# Position-specific coefficient of variation for per-game stat perturbation
_POSITION_CV: dict[str, float] = {
    "QB": 0.15,
    "RB": 0.25,
    "WR": 0.20,
    "TE": 0.25,
    "K": 0.20,
    "DEF": 0.25,
}

# Position-specific games_active standard deviation
_GAMES_STD: dict[str, float] = {
    "QB": 2.0,
    "RB": 3.0,
    "WR": 2.5,
    "TE": 2.5,
    "K": 1.5,
    "DEF": 0.5,
}


def compute_uncertainty(
    projection: StatProjection,
    scoring_config: ScoringConfig,
    n_samples: int = 5000,
    rng: np.random.Generator | None = None,
) -> UncertaintyResult:
    """Compute P25/P50/P75 fantasy point totals via bootstrap perturbation."""
    if rng is None:
        rng = np.random.default_rng(42)

    pos = projection.position
    cv = _POSITION_CV.get(pos, 0.20)
    games_std = _GAMES_STD.get(pos, 2.0)

    samples = []
    for _ in range(n_samples):
        perturbed_pg: dict[str, float] = {}
        for stat, mean in projection.per_game.items():
            std = abs(mean) * cv
            perturbed_pg[stat] = max(0.0, float(rng.normal(mean, std)))

        perturbed_games = max(0.0, min(17.0, float(rng.normal(projection.games_active, games_std))))

        season = {k: v * perturbed_games for k, v in perturbed_pg.items()}

        if pos in ("QB", "RB", "WR", "TE"):
            pts = score_player(season, pos, scoring_config)
        elif pos == "DEF":
            pa_pg = perturbed_pg.get("points_allowed", 22.0)
            pts = score_dst(season, pa_pg, perturbed_games, scoring_config)
        elif pos == "K":
            pts = score_kicker(season, scoring_config)
        else:
            pts = 0.0

        samples.append(pts)

    arr = np.array(samples)
    p25, p50, p75 = float(np.percentile(arr, 25)), float(np.percentile(arr, 50)), float(np.percentile(arr, 75))

    return UncertaintyResult(
        player_id=projection.player_id,
        position=pos,
        fantasy_points_p25=p25,
        fantasy_points_p50=p50,
        fantasy_points_p75=p75,
    )


def compute_all_uncertainty(
    projections: list[StatProjection],
    scoring_config: ScoringConfig,
    n_samples: int = 5000,
    seed: int = 42,
) -> list[UncertaintyResult]:
    """Compute uncertainty for all projections with a shared seed."""
    rng = np.random.default_rng(seed)
    return [
        compute_uncertainty(p, scoring_config, n_samples, rng)
        for p in projections
    ]
