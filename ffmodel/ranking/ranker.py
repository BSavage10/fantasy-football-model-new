"""Ranking layer: position ranks, overall ranks, and VOR.

Sorts players by projected fantasy points (P50 by default, P75 for "upside"
objective), assigns position and overall ranks, and computes value-over-
replacement (VOR) using configurable replacement levels per position.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from ffmodel.config import RankingConfig
from ffmodel.overlay.applicator import OverlayResult

logger = logging.getLogger(__name__)


@dataclass
class RankedPlayer:
    """A player with ranking metadata attached."""
    player_id: str
    position: str
    total_points: float
    model_only_points: float
    overlay_adjusted_points: float
    overlay_delta: float
    combined_multiplier: float
    manual_heavy: bool
    factors_applied: int
    position_rank: int
    overall_rank: int
    vor: float
    games_active: float
    is_rookie: bool
    is_team_changer: bool


def compute_rankings(
    overlay_results: list[OverlayResult],
    projections_df: pd.DataFrame,
    uncertainty_df: pd.DataFrame,
    ranking_config: RankingConfig,
) -> list[RankedPlayer]:
    """Rank players by fantasy points and compute VOR.

    Args:
        overlay_results: List of OverlayResult from the overlay layer.
        projections_df: DataFrame with player_id, position, games_active,
                        is_rookie, is_team_changer.
        uncertainty_df: DataFrame with player_id, fantasy_points_p25/p50/p75.
        ranking_config: Ranking objective, replacement levels, VOR method.

    Returns:
        Sorted list of RankedPlayer (best to worst by total_points).
    """
    proj_lookup = {}
    for _, row in projections_df.iterrows():
        proj_lookup[str(row["player_id"])] = row

    unc_lookup = {}
    for _, row in uncertainty_df.iterrows():
        unc_lookup[str(row["player_id"])] = row

    objective = ranking_config.ranking_objective
    sort_key = _get_sort_key(objective)

    entries: list[dict] = []
    for ov in overlay_results:
        proj_row = proj_lookup.get(ov.player_id)
        unc_row = unc_lookup.get(ov.player_id)
        if proj_row is None or unc_row is None:
            continue

        if objective == "upside":
            total_points = float(unc_row["fantasy_points_p75"])
        else:
            total_points = ov.overlay_adjusted_points

        entries.append({
            "player_id": ov.player_id,
            "position": ov.position,
            "total_points": total_points,
            "model_only_points": ov.model_only_points,
            "overlay_adjusted_points": ov.overlay_adjusted_points,
            "overlay_delta": ov.overlay_delta,
            "combined_multiplier": ov.combined_multiplier,
            "manual_heavy": ov.manual_heavy,
            "factors_applied": ov.factors_applied,
            "games_active": float(proj_row["games_active"]),
            "is_rookie": bool(proj_row["is_rookie"]),
            "is_team_changer": bool(proj_row["is_team_changer"]),
            "p25": float(unc_row["fantasy_points_p25"]),
            "p50": float(unc_row["fantasy_points_p50"]),
            "p75": float(unc_row["fantasy_points_p75"]),
        })

    entries.sort(key=lambda e: e["total_points"], reverse=True)

    replacement_levels = _compute_replacement_points(entries, ranking_config.replacement_level)

    position_counters: dict[str, int] = {}
    ranked: list[RankedPlayer] = []
    for i, e in enumerate(entries, start=1):
        pos = e["position"]
        position_counters[pos] = position_counters.get(pos, 0) + 1

        repl = replacement_levels.get(pos, 0.0)
        vor = e["total_points"] - repl

        ranked.append(RankedPlayer(
            player_id=e["player_id"],
            position=pos,
            total_points=e["total_points"],
            model_only_points=e["model_only_points"],
            overlay_adjusted_points=e["overlay_adjusted_points"],
            overlay_delta=e["overlay_delta"],
            combined_multiplier=e["combined_multiplier"],
            manual_heavy=e["manual_heavy"],
            factors_applied=e["factors_applied"],
            position_rank=position_counters[pos],
            overall_rank=i,
            vor=vor,
            games_active=e["games_active"],
            is_rookie=e["is_rookie"],
            is_team_changer=e["is_team_changer"],
        ))

    logger.info(
        "compute_rankings: %d players ranked, objective=%s",
        len(ranked), objective,
    )
    return ranked


def _get_sort_key(objective: str) -> str:
    if objective == "upside":
        return "fantasy_points_p75"
    return "fantasy_points_p50"


def _compute_replacement_points(
    entries: list[dict],
    replacement_level: dict[str, int],
) -> dict[str, float]:
    """Find the total_points of the Nth-ranked player at each position."""
    position_points: dict[str, list[float]] = {}
    for e in entries:
        pos = e["position"]
        position_points.setdefault(pos, []).append(e["total_points"])

    replacement: dict[str, float] = {}
    for pos, pts_list in position_points.items():
        pts_list.sort(reverse=True)
        n = replacement_level.get(pos, len(pts_list))
        if n <= len(pts_list):
            replacement[pos] = pts_list[n - 1]
        else:
            replacement[pos] = pts_list[-1] if pts_list else 0.0

    return replacement


def rankings_to_dataframe(ranked: list[RankedPlayer]) -> pd.DataFrame:
    """Convert ranked players to a DataFrame for export."""
    records = []
    for r in ranked:
        records.append({
            "player_id": r.player_id,
            "position": r.position,
            "overall_rank": r.overall_rank,
            "position_rank": r.position_rank,
            "total_points": round(r.total_points, 2),
            "model_only_points": round(r.model_only_points, 2),
            "overlay_adjusted_points": round(r.overlay_adjusted_points, 2),
            "overlay_delta": round(r.overlay_delta, 2),
            "vor": round(r.vor, 2),
            "games_active": round(r.games_active, 1),
            "is_rookie": r.is_rookie,
            "is_team_changer": r.is_team_changer,
            "manual_heavy": r.manual_heavy,
            "factors_applied": r.factors_applied,
            "combined_multiplier": round(r.combined_multiplier, 4),
        })
    return pd.DataFrame(records)
