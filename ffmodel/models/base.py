"""Base utilities for position models.

Contains StatProjection dataclass, weighted averaging, secondary rate
computation, and league-average constants used by all position projectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StatProjection:
    """A single player's stat projection for a season."""
    per_game: dict[str, float]
    season_total: dict[str, float]
    games_active: float
    position: str
    player_id: str
    reason_codes: list[str] = field(default_factory=list)
    qc_flags: list[str] = field(default_factory=list)
    is_rookie: bool = False
    is_team_changer: bool = False


@dataclass
class UncertaintyResult:
    """P25/P50/P75 fantasy point totals for a player."""
    player_id: str
    position: str
    fantasy_points_p25: float
    fantasy_points_p50: float
    fantasy_points_p75: float


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def weighted_mean(values: list[float], weights: list[float]) -> float:
    """Compute weighted mean. Returns 0.0 if total weight is zero."""
    total_w = sum(weights)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def make_season_totals(per_game: dict[str, float], games_active: float) -> dict[str, float]:
    """Multiply per-game stats by games_active to get season totals."""
    return {k: v * games_active for k, v in per_game.items()}


def get_eff(eff_vals: dict, key: str, default: float) -> float:
    """Get efficiency value, falling back to default if missing or NaN."""
    val = eff_vals.get(key, default)
    if pd.isna(val):
        return default
    return float(val)


def recency_weighted_avg(
    team_data: pd.DataFrame,
    col: str,
    target_season: int,
    recency_weights: dict[int, float],
) -> float | None:
    """Compute recency-weighted average of a column from team-season data."""
    total_w = 0.0
    total_val = 0.0
    for _, row in team_data.iterrows():
        years_ago = target_season - int(row["season"])
        w = recency_weights.get(years_ago, 0.0)
        if w == 0.0:
            continue
        val = row[col]
        if pd.notna(val):
            total_w += w
            total_val += w * val
    if total_w == 0:
        return None
    return total_val / total_w


# ---------------------------------------------------------------------------
# League-average constants
# ---------------------------------------------------------------------------

LEAGUE_AVG_RUSH_TD_RATE: dict[str, float] = {
    "QB": 0.035, "RB": 0.042, "WR": 0.020, "TE": 0.010,
}

LEAGUE_AVG_FUMBLE_RATE = 0.006

LEAGUE_AVG_EFFICIENCY: dict[str, float] = {
    "yards_per_attempt": 7.0,
    "comp_rate": 0.64,
    "pass_td_rate_regressed": 0.045,
    "int_rate_regressed": 0.025,
    "yards_per_carry_regressed": 4.3,
    "yards_per_target": 7.5,
    "catch_rate": 0.65,
    "receiving_td_rate_regressed": 0.06,
}


# ---------------------------------------------------------------------------
# Secondary rate computation
# ---------------------------------------------------------------------------

def compute_secondary_rates(
    player_week_fact: pd.DataFrame,
    target_season: int,
    recency_weights: dict[int, float],
) -> dict[str, dict[str, float]]:
    """Compute per-player rush_td_rate and fumble_rate from historical data.

    These rates supplement the gold-layer efficiency features which cover
    the primary passing/rushing/receiving efficiency metrics.
    """
    pw = player_week_fact[player_week_fact["season"] < target_season].copy()
    if pw.empty:
        return {}

    player_season = pw.groupby(["canonical_player_id", "season", "position"]).agg(
        rush_att=("rush_att", "sum"),
        rush_td=("rush_td", "sum"),
        receptions=("receptions", "sum"),
        pass_att=("pass_att", "sum"),
        fumbles_lost=("fumbles_lost", "sum"),
    ).reset_index()

    results: dict[str, dict[str, float]] = {}
    for pid in player_season["canonical_player_id"].unique():
        pdata = player_season[player_season["canonical_player_id"] == pid].sort_values(
            "season", ascending=False,
        )
        pos = str(pdata.iloc[0]["position"])

        total_weight = 0.0
        w_rush_td = 0.0
        w_fumble = 0.0

        for _, row in pdata.iterrows():
            years_ago = target_season - int(row["season"])
            w = recency_weights.get(years_ago, 0.0)
            if w == 0.0:
                continue
            total_weight += w

            ra = row["rush_att"]
            if ra > 0:
                w_rush_td += w * (row["rush_td"] / ra)
            else:
                w_rush_td += w * LEAGUE_AVG_RUSH_TD_RATE.get(pos, 0.03)

            touches = ra + row["receptions"] + row["pass_att"]
            if touches > 0:
                w_fumble += w * (row["fumbles_lost"] / touches)
            else:
                w_fumble += w * LEAGUE_AVG_FUMBLE_RATE

        if total_weight > 0:
            w_rush_td /= total_weight
            w_fumble /= total_weight
        else:
            w_rush_td = LEAGUE_AVG_RUSH_TD_RATE.get(pos, 0.03)
            w_fumble = LEAGUE_AVG_FUMBLE_RATE

        results[pid] = {"rush_td_rate": w_rush_td, "fumble_rate": w_fumble}

    return results
