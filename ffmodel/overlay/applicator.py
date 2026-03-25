"""Manual overlay math: dampen, convert, combine, cap, apply.

Each manual factor (0-to-1 score) is converted to a multiplicative adjustment
on a player's projected fantasy points.  Low-confidence factors are dampened
toward neutral (0.50).  All factors for a player combine multiplicatively,
with total effect capped at ±max_total_effect (default ±25%).

The overlay is applied to the model-only fantasy point total, producing an
overlay-adjusted total and a delta that shows the impact of manual factors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from ffmodel.config import OverlayConfig

logger = logging.getLogger(__name__)


@dataclass
class OverlayResult:
    """Result of applying manual overlays to a single player."""
    player_id: str
    position: str
    model_only_points: float
    overlay_adjusted_points: float
    overlay_delta: float
    combined_multiplier: float
    manual_heavy: bool
    factors_applied: int


def dampen_score(
    score_raw: float,
    confidence: float,
    low_confidence_threshold: float,
) -> float:
    """Dampen a factor score toward neutral (0.50) if confidence is low.

    If confidence < threshold:
        effective = 0.50 + (confidence / threshold) * (score - 0.50)
    Otherwise: effective = score_raw
    """
    if confidence < low_confidence_threshold:
        return 0.50 + (confidence / low_confidence_threshold) * (score_raw - 0.50)
    return score_raw


def factor_to_multiplier(
    dampened_score: float,
    max_effect_per_factor: float,
) -> float:
    """Convert a dampened 0-to-1 score to a multiplicative factor.

    multiplier = 1.0 + (dampened_score - 0.50) * 2 * max_effect
    A score of 0.50 → multiplier 1.0 (neutral).
    A score of 1.0 → multiplier 1 + max_effect.
    A score of 0.0 → multiplier 1 - max_effect.
    """
    return 1.0 + (dampened_score - 0.50) * 2 * max_effect_per_factor


def combine_multipliers(
    multipliers: list[float],
    max_total_effect: float,
) -> float:
    """Combine multiple multiplicative factors, capping total effect.

    All factors multiply together. The combined effect is capped so the
    final multiplier stays within [1 - max_total_effect, 1 + max_total_effect].
    """
    if not multipliers:
        return 1.0
    combined = 1.0
    for m in multipliers:
        combined *= m
    lower = 1.0 - max_total_effect
    upper = 1.0 + max_total_effect
    return max(lower, min(upper, combined))


def apply_overlays(
    projections_df: pd.DataFrame,
    uncertainty_df: pd.DataFrame,
    manual_factors_df: pd.DataFrame,
    overlay_config: OverlayConfig,
) -> list[OverlayResult]:
    """Apply manual overlays to projections and return overlay results.

    Args:
        projections_df: DataFrame from projections_to_dataframe() with player_id,
                        position, and season_total stat columns.
        uncertainty_df: DataFrame with player_id, fantasy_points_p50.
        manual_factors_df: DataFrame from manual_factor_features with entity_id,
                           entity_type, factor_name, score_normalized, confidence.
        overlay_config: Overlay settings from model.yaml.

    Returns:
        List of OverlayResult, one per player in projections_df.
    """
    if not overlay_config.enabled:
        logger.info("Overlays disabled — returning model-only points")
        results = []
        for _, row in uncertainty_df.iterrows():
            results.append(OverlayResult(
                player_id=row["player_id"],
                position=row["position"],
                model_only_points=row["fantasy_points_p50"],
                overlay_adjusted_points=row["fantasy_points_p50"],
                overlay_delta=0.0,
                combined_multiplier=1.0,
                manual_heavy=False,
                factors_applied=0,
            ))
        return results

    player_factors: dict[str, list[tuple[float, float]]] = {}
    team_factors: dict[str, list[tuple[float, float]]] = {}

    for _, frow in manual_factors_df.iterrows():
        entity_id = str(frow["entity_id"])
        entity_type = str(frow["entity_type"])
        score = float(frow["score_normalized"])
        confidence = float(frow.get("confidence", 0.5))

        if entity_type == "player":
            player_factors.setdefault(entity_id, []).append((score, confidence))
        elif entity_type == "team":
            team_factors.setdefault(entity_id, []).append((score, confidence))

    proj_teams: dict[str, str] = {}
    for _, row in projections_df.iterrows():
        pid = str(row["player_id"])
        if row["position"] == "DEF":
            proj_teams[pid] = pid
        elif "team" in projections_df.columns:
            proj_teams[pid] = str(row["team"])

    results: list[OverlayResult] = []
    for _, urow in uncertainty_df.iterrows():
        pid = str(urow["player_id"])
        pos = str(urow["position"])
        model_pts = float(urow["fantasy_points_p50"])

        all_factor_pairs: list[tuple[float, float]] = []
        if pid in player_factors:
            all_factor_pairs.extend(player_factors[pid])
        team_id = proj_teams.get(pid)
        if team_id and team_id in team_factors:
            all_factor_pairs.extend(team_factors[team_id])

        if not all_factor_pairs:
            results.append(OverlayResult(
                player_id=pid,
                position=pos,
                model_only_points=model_pts,
                overlay_adjusted_points=model_pts,
                overlay_delta=0.0,
                combined_multiplier=1.0,
                manual_heavy=False,
                factors_applied=0,
            ))
            continue

        multipliers = []
        for score, confidence in all_factor_pairs:
            dampened = dampen_score(score, confidence, overlay_config.low_confidence_threshold)
            mult = factor_to_multiplier(dampened, overlay_config.max_effect_per_factor)
            multipliers.append(mult)

        combined = combine_multipliers(multipliers, overlay_config.max_total_effect)
        adjusted = model_pts * combined
        delta = adjusted - model_pts
        manual_heavy = abs(delta) / max(abs(model_pts), 0.001) > 0.10

        results.append(OverlayResult(
            player_id=pid,
            position=pos,
            model_only_points=model_pts,
            overlay_adjusted_points=adjusted,
            overlay_delta=delta,
            combined_multiplier=combined,
            manual_heavy=manual_heavy,
            factors_applied=len(all_factor_pairs),
        ))

    logger.info(
        "apply_overlays: %d players, %d with factors applied",
        len(results), sum(1 for r in results if r.factors_applied > 0),
    )
    return results
