"""TE position projector.

Same structure as WR — combines team passing volume, target share,
and efficiency rates into per-game and season-total projections.
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


def project_te(
    role_df: pd.DataFrame,
    team_context_df: pd.DataFrame,
    efficiency_df: pd.DataFrame,
    availability_df: pd.DataFrame,
    secondary_rates: dict[str, dict[str, float]],
) -> list[StatProjection]:
    """Project TE stats for the target season."""
    tes = role_df[role_df["position"] == "TE"]
    projections: list[StatProjection] = []

    for _, te in tes.iterrows():
        pid = te["canonical_player_id"]
        team = te["team"]
        is_rookie = bool(te["is_rookie"])
        is_tc = bool(te["is_team_changer"])
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
        rush_td_rate = sec.get("rush_td_rate", LEAGUE_AVG_RUSH_TD_RATE["TE"])
        fumble_rate = sec.get("fumble_rate", LEAGUE_AVG_FUMBLE_RATE)

        targets = tc["team_targets_proj"] * te["target_share"]
        catch_rate = get_eff(eff_vals, "catch_rate", LEAGUE_AVG_EFFICIENCY["catch_rate"])
        receptions = targets * catch_rate
        rush_att = tc["team_rushes_proj"] * te["rush_share"]

        per_game = {
            "targets": float(targets),
            "receptions": float(receptions),
            "rec_yd": float(targets * get_eff(eff_vals, "yards_per_target", LEAGUE_AVG_EFFICIENCY["yards_per_target"])),
            "rec_td": float(targets * get_eff(eff_vals, "receiving_td_rate_regressed", LEAGUE_AVG_EFFICIENCY["receiving_td_rate_regressed"])),
            "rush_att": float(rush_att),
            "rush_yd": float(rush_att * get_eff(eff_vals, "yards_per_carry_regressed", LEAGUE_AVG_EFFICIENCY["yards_per_carry_regressed"])),
            "rush_td": float(rush_att * rush_td_rate),
            "fumbles_lost": float((receptions + rush_att) * fumble_rate),
        }

        if is_rookie and "rookie_prior_used" not in reasons:
            reasons.append("rookie_prior_used")
        if is_tc:
            reasons.append("team_changer_blend")
        reasons.append("td_regression_applied")

        projections.append(StatProjection(
            per_game=per_game,
            season_total=make_season_totals(per_game, games_active),
            games_active=games_active,
            position="TE",
            player_id=pid,
            reason_codes=reasons,
            is_rookie=is_rookie,
            is_team_changer=is_tc,
        ))

    return projections
