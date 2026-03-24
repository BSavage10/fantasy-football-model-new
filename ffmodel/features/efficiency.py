"""Gold layer: player efficiency features.

Computes regressed efficiency rates per player for the target season.
Contains the regress_rate() function used for empirical Bayes shrinkage.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = [
    "canonical_player_id",
    "season",
    "position",
    "yards_per_attempt",
    "comp_rate",
    "pass_td_rate_regressed",
    "int_rate_regressed",
    "yards_per_carry_regressed",
    "yards_per_target",
    "catch_rate",
    "receiving_td_rate_regressed",
]


def regress_rate(
    observed: float,
    sample_size: float,
    prior: float,
    regression_sample: float,
) -> float:
    """Empirical Bayes regression to mean.

    regressed = (observed * sample_size + prior * regression_sample) /
                (sample_size + regression_sample)
    """
    return (observed * sample_size + prior * regression_sample) / (
        sample_size + regression_sample
    )


def _compute_league_priors(player_season: pd.DataFrame) -> dict[str, float]:
    """Compute league-average rates from all qualifying players."""
    totals = player_season.groupby("position").agg(
        total_pass_att=("total_pass_att", "sum"),
        total_pass_cmp=("total_pass_cmp", "sum"),
        total_pass_yd=("total_pass_yd", "sum"),
        total_pass_td=("total_pass_td", "sum"),
        total_int=("total_int", "sum"),
        total_rush_att=("total_rush_att", "sum"),
        total_rush_yd=("total_rush_yd", "sum"),
        total_targets=("total_targets", "sum"),
        total_receptions=("total_receptions", "sum"),
        total_rec_yd=("total_rec_yd", "sum"),
        total_rec_td=("total_rec_td", "sum"),
    )

    all_pass = totals["total_pass_att"].sum()
    all_rush = totals["total_rush_att"].sum()
    all_tgt = totals["total_targets"].sum()

    return {
        "yards_per_attempt": totals["total_pass_yd"].sum() / max(all_pass, 1),
        "comp_rate": totals["total_pass_cmp"].sum() / max(all_pass, 1),
        "pass_td_rate": totals["total_pass_td"].sum() / max(all_pass, 1),
        "int_rate": totals["total_int"].sum() / max(all_pass, 1),
        "yards_per_carry": totals["total_rush_yd"].sum() / max(all_rush, 1),
        "yards_per_target": totals["total_rec_yd"].sum() / max(all_tgt, 1),
        "catch_rate": totals["total_receptions"].sum() / max(all_tgt, 1),
        "receiving_td_rate": totals["total_rec_td"].sum() / max(all_tgt, 1),
    }


def build_player_efficiency_features(
    player_week_fact: pd.DataFrame,
    target_season: int,
    recency_weights: dict[int, float],
    regression_samples: dict[str, int],
) -> pd.DataFrame:
    """Build player efficiency features for target season.

    Leakage gate: only uses seasons strictly before target_season.
    """
    pw = player_week_fact[player_week_fact["season"] < target_season].copy()

    if pw.empty:
        return pd.DataFrame(columns=COLUMNS)

    player_season = pw.groupby(
        ["canonical_player_id", "season", "position"]
    ).agg(
        total_pass_att=("pass_att", "sum"),
        total_pass_cmp=("pass_cmp", "sum"),
        total_pass_yd=("pass_yd", "sum"),
        total_pass_td=("pass_td", "sum"),
        total_int=("interceptions", "sum"),
        total_rush_att=("rush_att", "sum"),
        total_rush_yd=("rush_yd", "sum"),
        total_targets=("targets", "sum"),
        total_receptions=("receptions", "sum"),
        total_rec_yd=("rec_yd", "sum"),
        total_rec_td=("rec_td", "sum"),
    ).reset_index()

    league_priors = _compute_league_priors(player_season)

    player_season["raw_ypa"] = np.where(
        player_season["total_pass_att"] > 0,
        player_season["total_pass_yd"] / player_season["total_pass_att"],
        np.nan,
    )
    player_season["raw_comp_rate"] = np.where(
        player_season["total_pass_att"] > 0,
        player_season["total_pass_cmp"] / player_season["total_pass_att"],
        np.nan,
    )
    player_season["raw_pass_td_rate"] = np.where(
        player_season["total_pass_att"] > 0,
        player_season["total_pass_td"] / player_season["total_pass_att"],
        np.nan,
    )
    player_season["raw_int_rate"] = np.where(
        player_season["total_pass_att"] > 0,
        player_season["total_int"] / player_season["total_pass_att"],
        np.nan,
    )
    player_season["raw_ypc"] = np.where(
        player_season["total_rush_att"] > 0,
        player_season["total_rush_yd"] / player_season["total_rush_att"],
        np.nan,
    )
    player_season["raw_ypt"] = np.where(
        player_season["total_targets"] > 0,
        player_season["total_rec_yd"] / player_season["total_targets"],
        np.nan,
    )
    player_season["raw_catch_rate"] = np.where(
        player_season["total_targets"] > 0,
        player_season["total_receptions"] / player_season["total_targets"],
        np.nan,
    )
    player_season["raw_rec_td_rate"] = np.where(
        player_season["total_targets"] > 0,
        player_season["total_rec_td"] / player_season["total_targets"],
        np.nan,
    )

    reg_ypa = regression_samples.get("yards_per_attempt", 600)
    reg_pass_td = regression_samples.get("pass_td_rate", 1500)
    reg_int = regression_samples.get("int_rate", 800)
    reg_ypc = regression_samples.get("yards_per_carry", 600)
    reg_catch = regression_samples.get("catch_rate", 150)
    reg_rec_td = regression_samples.get("receiving_td_rate", 300)

    results = []
    for pid in player_season["canonical_player_id"].unique():
        pdata = player_season[player_season["canonical_player_id"] == pid].sort_values(
            "season", ascending=False
        )
        pos = pdata.iloc[0]["position"]

        rate_cols = [
            "raw_ypa", "raw_comp_rate", "raw_pass_td_rate", "raw_int_rate",
            "raw_ypc", "raw_ypt", "raw_catch_rate", "raw_rec_td_rate",
        ]
        sample_cols = [
            "total_pass_att", "total_pass_att", "total_pass_att", "total_pass_att",
            "total_rush_att", "total_targets", "total_targets", "total_targets",
        ]

        weighted_rates = {}
        weighted_samples = {}
        total_weight = 0.0

        for _, row in pdata.iterrows():
            years_ago = target_season - int(row["season"])
            w = recency_weights.get(years_ago, 0.0)
            if w == 0.0:
                continue
            total_weight += w
            for rc, sc in zip(rate_cols, sample_cols):
                val = row[rc]
                samp = row[sc]
                if pd.notna(val):
                    weighted_rates[rc] = weighted_rates.get(rc, 0.0) + w * val
                    weighted_samples[rc] = weighted_samples.get(rc, 0.0) + w * samp

        if total_weight > 0:
            for rc in rate_cols:
                if rc in weighted_rates:
                    weighted_rates[rc] /= total_weight
                    weighted_samples[rc] /= total_weight

        pass_att_w = weighted_samples.get("raw_ypa", 0)
        rush_att_w = weighted_samples.get("raw_ypc", 0)
        tgt_w = weighted_samples.get("raw_ypt", 0)

        ypa = regress_rate(
            weighted_rates.get("raw_ypa", league_priors["yards_per_attempt"]),
            pass_att_w, league_priors["yards_per_attempt"], reg_ypa,
        ) if pass_att_w > 0 else league_priors["yards_per_attempt"]

        comp_rate = weighted_rates.get("raw_comp_rate", league_priors["comp_rate"])

        pass_td_rate = regress_rate(
            weighted_rates.get("raw_pass_td_rate", league_priors["pass_td_rate"]),
            pass_att_w, league_priors["pass_td_rate"], reg_pass_td,
        ) if pass_att_w > 0 else league_priors["pass_td_rate"]

        int_rate = regress_rate(
            weighted_rates.get("raw_int_rate", league_priors["int_rate"]),
            pass_att_w, league_priors["int_rate"], reg_int,
        ) if pass_att_w > 0 else league_priors["int_rate"]

        ypc = regress_rate(
            weighted_rates.get("raw_ypc", league_priors["yards_per_carry"]),
            rush_att_w, league_priors["yards_per_carry"], reg_ypc,
        ) if rush_att_w > 0 else league_priors["yards_per_carry"]

        ypt = weighted_rates.get("raw_ypt", league_priors["yards_per_target"])

        catch_rate = regress_rate(
            weighted_rates.get("raw_catch_rate", league_priors["catch_rate"]),
            tgt_w, league_priors["catch_rate"], reg_catch,
        ) if tgt_w > 0 else league_priors["catch_rate"]

        rec_td_rate = regress_rate(
            weighted_rates.get("raw_rec_td_rate", league_priors["receiving_td_rate"]),
            tgt_w, league_priors["receiving_td_rate"], reg_rec_td,
        ) if tgt_w > 0 else league_priors["receiving_td_rate"]

        results.append({
            "canonical_player_id": pid,
            "season": target_season,
            "position": pos,
            "yards_per_attempt": ypa,
            "comp_rate": comp_rate,
            "pass_td_rate_regressed": pass_td_rate,
            "int_rate_regressed": int_rate,
            "yards_per_carry_regressed": ypc,
            "yards_per_target": ypt,
            "catch_rate": catch_rate,
            "receiving_td_rate_regressed": rec_td_rate,
        })

    df = pd.DataFrame(results, columns=COLUMNS)
    logger.info("player_efficiency_features: %d rows for season %d", len(df), target_season)
    return df


def write_player_efficiency_features(
    silver_dir: Path,
    gold_dir: Path,
    target_season: int,
    recency_weights: dict[int, float],
    regression_samples: dict[str, int],
) -> Path:
    """Build and write player_efficiency_features.parquet to the gold directory."""
    player_week = pd.read_parquet(silver_dir / "player_week_fact.parquet")
    features = build_player_efficiency_features(
        player_week, target_season, recency_weights, regression_samples,
    )
    gold_dir.mkdir(parents=True, exist_ok=True)
    out_path = gold_dir / "player_efficiency_features.parquet"
    features.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
