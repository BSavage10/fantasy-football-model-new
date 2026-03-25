"""QB position projector.

Combines team context (volume), role features (starter share, rush rate),
and efficiency features (completion rate, TD rate, etc.) into per-game
and season-total stat projections for quarterbacks.
"""

from __future__ import annotations

import pandas as pd

from ffmodel.models.base import (
    LEAGUE_AVG_EFFICIENCY,
    LEAGUE_AVG_FUMBLE_RATE,
    LEAGUE_AVG_RUSH_TD_RATE,
    StatProjection,
    get_eff,
    make_season_totals,
)


def project_qb(
    role_df: pd.DataFrame,
    team_context_df: pd.DataFrame,
    efficiency_df: pd.DataFrame,
    availability_df: pd.DataFrame,
    secondary_rates: dict[str, dict[str, float]],
) -> list[StatProjection]:
    """Project QB stats for the target season."""
    qbs = role_df[role_df["position"] == "QB"]
    projections: list[StatProjection] = []

    for _, qb in qbs.iterrows():
        pid = qb["canonical_player_id"]
        team = qb["team"]
        is_rookie = bool(qb["is_rookie"])
        is_tc = bool(qb["is_team_changer"])
        reasons: list[str] = []

        if team is None or pd.isna(team):
            continue

        tc = team_context_df[team_context_df["team"] == team]
        if tc.empty:
            continue
        tc = tc.iloc[0]

        avail = availability_df[availability_df["canonical_player_id"] == pid]
        if avail.empty:
            continue
        games_active = float(avail.iloc[0]["games_active_proj"])

        eff = efficiency_df[efficiency_df["canonical_player_id"] == pid]
        if eff.empty:
            eff_vals = LEAGUE_AVG_EFFICIENCY
            reasons.append("rookie_prior_used")
        else:
            eff_vals = eff.iloc[0].to_dict()

        sec = secondary_rates.get(pid, {})
        rush_td_rate = sec.get("rush_td_rate", LEAGUE_AVG_RUSH_TD_RATE["QB"])
        fumble_rate = sec.get("fumble_rate", LEAGUE_AVG_FUMBLE_RATE)

        pass_att = tc["team_targets_proj"] * qb["starter_share_of_dropbacks"]
        rush_att = qb["qb_rush_attempts_per_game"]

        per_game = {
            "pass_att": float(pass_att),
            "pass_cmp": float(pass_att * get_eff(eff_vals, "comp_rate", LEAGUE_AVG_EFFICIENCY["comp_rate"])),
            "pass_yd": float(pass_att * get_eff(eff_vals, "yards_per_attempt", LEAGUE_AVG_EFFICIENCY["yards_per_attempt"])),
            "pass_td": float(pass_att * get_eff(eff_vals, "pass_td_rate_regressed", LEAGUE_AVG_EFFICIENCY["pass_td_rate_regressed"])),
            "interceptions": float(pass_att * get_eff(eff_vals, "int_rate_regressed", LEAGUE_AVG_EFFICIENCY["int_rate_regressed"])),
            "rush_att": float(rush_att),
            "rush_yd": float(rush_att * get_eff(eff_vals, "yards_per_carry_regressed", LEAGUE_AVG_EFFICIENCY["yards_per_carry_regressed"])),
            "rush_td": float(rush_att * rush_td_rate),
            "fumbles_lost": float((pass_att + rush_att) * fumble_rate),
        }

        if is_rookie and "rookie_prior_used" not in reasons:
            reasons.append("rookie_prior_used")
        if is_tc:
            reasons.append("team_changer_blend")
        if rush_att >= 5:
            reasons.append("mobile_qb")
        reasons.append("td_regression_applied")

        projections.append(StatProjection(
            per_game=per_game,
            season_total=make_season_totals(per_game, games_active),
            games_active=games_active,
            position="QB",
            player_id=pid,
            reason_codes=reasons,
            is_rookie=is_rookie,
            is_team_changer=is_tc,
        ))

    return projections
