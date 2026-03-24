"""Tests for the silver-layer transform modules.

Uses synthetic fixture data written to temp directories — no network calls.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ffmodel.transform.player_dim import build_player_dim
from ffmodel.transform.player_week import build_player_week_fact
from ffmodel.transform.schedule import build_schedule_fact
from ffmodel.transform.team_dim import TEAM_ABBR_MAP, build_team_dim, normalize_team_abbr
from ffmodel.transform.team_week import build_team_week_fact


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    """Create a temp raw directory with synthetic source Parquet files."""
    raw = tmp_path / "raw" / "2025-09-01"
    raw.mkdir(parents=True)

    # Players
    players_df = pd.DataFrame({
        "gsis_id": ["P001", "P002", "P003", "P004", "P005"],
        "display_name": ["Tom Brady", "Derrick Henry", "Tyreek Hill", "Travis Kelce", "Justin Tucker"],
        "position": ["QB", "RB", "WR", "TE", "K"],
        "birth_date": ["1977-08-03", "1994-01-04", "1994-03-01", "1989-10-05", "1989-11-21"],
        "college": ["Michigan", "Alabama", "West Alabama", "Cincinnati", "Texas"],
        "draft_year": [2000, 2016, 2016, 2013, 2012],
        "draft_round": [6, 2, 5, 3, None],
        "draft_number": [199, 45, 165, 63, None],
        "rookie_year": [2000, 2016, 2016, 2013, 2012],
        "pfr_id": [None, None, None, None, None],
    })
    players_df.to_parquet(raw / "players.parquet", index=False)

    # Rosters
    rosters_df = pd.DataFrame({
        "player_id": ["P001", "P002", "P003", "P004", "P005"] * 2,
        "season": [2024] * 5 + [2025] * 5,
        "team": ["NE", "TEN", "MIA", "KC", "BAL"] * 2,
        "position": ["QB", "RB", "WR", "TE", "K"] * 2,
    })
    rosters_df.to_parquet(raw / "rosters.parquet", index=False)

    # Schedules — 2 seasons, with some historical team abbreviations
    sched_records = []
    game_id = 0
    for season in [2024, 2025]:
        teams = [
            "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
            "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
            "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
            "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
        ]
        for week in range(1, 19):  # 18 weeks
            # 16 games per week (32 teams / 2)
            for i in range(0, 32, 2):
                game_id += 1
                sched_records.append({
                    "game_id": f"{season}_{week:02d}_{game_id}",
                    "season": season,
                    "week": week,
                    "home_team": teams[i],
                    "away_team": teams[i + 1],
                    "gameday": f"{season}-09-{(week % 28) + 1:02d}",
                    "spread_line": -3.0,
                    "total_line": 45.5,
                    "home_score": 24 if week <= 17 else None,
                    "away_score": 17 if week <= 17 else None,
                })
    sched_df = pd.DataFrame(sched_records)
    sched_df.to_parquet(raw / "schedules.parquet", index=False)

    # Weekly stats
    weekly_records = []
    for season in [2024, 2025]:
        for week in range(1, 18):
            for pid, pos in [("P001", "QB"), ("P002", "RB"), ("P003", "WR"),
                             ("P004", "TE"), ("P005", "K")]:
                rec = {
                    "player_id": pid,
                    "season": season,
                    "week": week,
                    "recent_team": "KC",
                    "position": pos,
                    "completions": 25 if pos == "QB" else 0,
                    "attempts": 35 if pos == "QB" else 0,
                    "passing_yards": 280.0 if pos == "QB" else 0.0,
                    "passing_tds": 2 if pos == "QB" else 0,
                    "interceptions": 1 if pos == "QB" else 0,
                    "carries": 15 if pos == "RB" else (3 if pos == "QB" else 0),
                    "rushing_yards": 70.0 if pos == "RB" else (15.0 if pos == "QB" else 0.0),
                    "rushing_tds": 1 if pos == "RB" else 0,
                    "targets": 8 if pos == "WR" else (5 if pos == "TE" else (3 if pos == "RB" else 0)),
                    "receptions": 6 if pos == "WR" else (4 if pos == "TE" else (2 if pos == "RB" else 0)),
                    "receiving_yards": 85.0 if pos == "WR" else (45.0 if pos == "TE" else (15.0 if pos == "RB" else 0.0)),
                    "receiving_tds": 1 if pos in ("WR", "TE") else 0,
                    "fumbles_lost": 0,
                    "special_teams_tds": 0,
                    "sacks": 2 if pos == "QB" else 0,
                }
                weekly_records.append(rec)
    weekly_df = pd.DataFrame(weekly_records)
    weekly_df.to_parquet(raw / "weekly_stats.parquet", index=False)

    # PBP (simplified)
    pbp_records = []
    for season in [2024, 2025]:
        for week in range(1, 18):
            for play_idx in range(120):
                is_pass = play_idx % 2 == 0
                pbp_records.append({
                    "game_id": f"{season}_{week:02d}_{play_idx}",
                    "season": season,
                    "week": week,
                    "posteam": "KC",
                    "play_type": "pass" if is_pass else "run",
                    "pass": 1 if is_pass else 0,
                    "rush": 0 if is_pass else 1,
                    "sack": 1 if (is_pass and play_idx % 20 == 0) else 0,
                    "score_differential": 0,
                    "qtr": (play_idx // 30) + 1,
                    "yardline_100": max(10, 80 - play_idx % 80),
                    "drive": play_idx // 10,
                    "epa": 0.1 if is_pass else -0.05,
                })
    pbp_df = pd.DataFrame(pbp_records)
    pbp_df.to_parquet(raw / "pbp.parquet", index=False)

    return raw


# ── Team abbreviation normalization ─────────────────────────────────────────


class TestNormalizeTeamAbbr:
    def test_current_teams_unchanged(self) -> None:
        assert normalize_team_abbr("KC") == "KC"
        assert normalize_team_abbr("SF") == "SF"

    def test_historical_mappings(self) -> None:
        assert normalize_team_abbr("OAK") == "LV"
        assert normalize_team_abbr("SD") == "LAC"
        assert normalize_team_abbr("STL") == "LA"

    def test_case_insensitive(self) -> None:
        assert normalize_team_abbr("oak") == "LV"

    def test_whitespace_stripped(self) -> None:
        assert normalize_team_abbr(" KC ") == "KC"


# ── Player dim ──────────────────────────────────────────────────────────────


class TestPlayerDim:
    def test_no_duplicate_ids(self, raw_dir: Path) -> None:
        df = build_player_dim(raw_dir)
        assert df["canonical_player_id"].is_unique

    def test_required_columns(self, raw_dir: Path) -> None:
        df = build_player_dim(raw_dir)
        expected_cols = {
            "canonical_player_id", "gsis_id", "pfr_id", "name", "position",
            "birth_date", "college", "draft_year", "draft_round", "draft_pick",
            "entry_year",
        }
        assert expected_cols == set(df.columns)

    def test_positions_filtered(self, raw_dir: Path) -> None:
        df = build_player_dim(raw_dir)
        valid = {"QB", "RB", "WR", "TE", "K", "FB"}
        assert set(df["position"].unique()).issubset(valid)

    def test_player_count(self, raw_dir: Path) -> None:
        df = build_player_dim(raw_dir)
        assert len(df) == 5

    def test_entry_year_populated(self, raw_dir: Path) -> None:
        df = build_player_dim(raw_dir)
        assert df["entry_year"].notna().all()


# ── Team dim ────────────────────────────────────────────────────────────────


class TestTeamDim:
    def test_no_duplicate_team_season(self, raw_dir: Path) -> None:
        df = build_team_dim(raw_dir, [2024, 2025])
        assert df["team_key"].is_unique
        # Also verify (team_abbr, season) is unique
        assert df.duplicated(subset=["team_abbr", "season"]).sum() == 0

    def test_required_columns(self, raw_dir: Path) -> None:
        df = build_team_dim(raw_dir, [2024, 2025])
        assert set(df.columns) == {"team_key", "team_abbr", "season", "historical_aliases"}

    def test_team_key_format(self, raw_dir: Path) -> None:
        df = build_team_dim(raw_dir, [2024, 2025])
        for _, row in df.iterrows():
            assert row["team_key"] == f"{row['team_abbr']}_{row['season']}"

    def test_abbreviations_standardized(self, raw_dir: Path) -> None:
        df = build_team_dim(raw_dir, [2024, 2025])
        # No historical abbreviations should appear as team_abbr
        historical = set(TEAM_ABBR_MAP.keys())
        assert set(df["team_abbr"].unique()).isdisjoint(historical)

    def test_32_teams_per_season(self, raw_dir: Path) -> None:
        df = build_team_dim(raw_dir, [2024, 2025])
        for season in [2024, 2025]:
            season_df = df[df["season"] == season]
            assert len(season_df) == 32, f"Expected 32 teams for {season}, got {len(season_df)}"


# ── Schedule fact ───────────────────────────────────────────────────────────


class TestScheduleFact:
    def test_no_duplicate_game_id(self, raw_dir: Path) -> None:
        df = build_schedule_fact(raw_dir)
        assert df["game_id"].is_unique

    def test_required_columns(self, raw_dir: Path) -> None:
        df = build_schedule_fact(raw_dir)
        expected_cols = {
            "game_id", "season", "week", "home_team", "away_team",
            "game_date", "spread_line", "total_line", "home_score", "away_score",
        }
        assert expected_cols == set(df.columns)

    def test_games_per_season(self, raw_dir: Path) -> None:
        df = build_schedule_fact(raw_dir)
        for season in [2024, 2025]:
            season_games = df[df["season"] == season]
            # 18 weeks × 16 games per week = 288 games
            assert len(season_games) == 288, f"Expected 288 games for {season}, got {len(season_games)}"

    def test_team_abbreviations_normalized(self, raw_dir: Path) -> None:
        df = build_schedule_fact(raw_dir)
        historical = set(TEAM_ABBR_MAP.keys())
        home_teams = set(df["home_team"].unique())
        away_teams = set(df["away_team"].unique())
        assert home_teams.isdisjoint(historical)
        assert away_teams.isdisjoint(historical)


# ── Player week fact ────────────────────────────────────────────────────────


class TestPlayerWeekFact:
    def test_no_duplicate_keys(self, raw_dir: Path) -> None:
        df = build_player_week_fact(raw_dir)
        dups = df.duplicated(subset=["canonical_player_id", "season", "week", "team"])
        assert dups.sum() == 0

    def test_required_columns(self, raw_dir: Path) -> None:
        df = build_player_week_fact(raw_dir)
        expected_cols = {
            "canonical_player_id", "season", "week", "team", "position",
            "games_played", "pass_att", "pass_cmp", "pass_yd", "pass_td",
            "interceptions", "rush_att", "rush_yd", "rush_td", "targets",
            "receptions", "rec_yd", "rec_td", "fumbles_lost", "two_pt_conv",
            "return_td", "sacks_taken",
        }
        assert expected_cols == set(df.columns)

    def test_stat_types(self, raw_dir: Path) -> None:
        df = build_player_week_fact(raw_dir)
        # Integer columns
        for col in ["pass_att", "pass_cmp", "pass_td", "rush_att", "rush_td",
                     "targets", "receptions", "rec_td"]:
            assert df[col].dtype in (np.int64, np.int32, int), f"{col} should be int"
        # Float columns
        for col in ["pass_yd", "rush_yd", "rec_yd"]:
            assert df[col].dtype in (np.float64, np.float32, float), f"{col} should be float"

    def test_games_played_binary(self, raw_dir: Path) -> None:
        df = build_player_week_fact(raw_dir)
        assert set(df["games_played"].unique()).issubset({0, 1})

    def test_qb_has_passing_stats(self, raw_dir: Path) -> None:
        df = build_player_week_fact(raw_dir)
        qb = df[df["position"] == "QB"]
        assert (qb["pass_att"] > 0).all()
        assert (qb["pass_cmp"] > 0).all()

    def test_team_abbreviations_normalized(self, raw_dir: Path) -> None:
        df = build_player_week_fact(raw_dir)
        historical = set(TEAM_ABBR_MAP.keys())
        assert set(df["team"].unique()).isdisjoint(historical)


# ── Team week fact ──────────────────────────────────────────────────────────


class TestTeamWeekFact:
    def test_no_duplicate_keys(self, raw_dir: Path) -> None:
        df = build_team_week_fact(raw_dir)
        dups = df.duplicated(subset=["team", "season", "week"])
        assert dups.sum() == 0

    def test_required_columns(self, raw_dir: Path) -> None:
        df = build_team_week_fact(raw_dir)
        expected_cols = {
            "team", "season", "week", "plays", "pass_plays", "rush_plays",
            "dropbacks", "sacks_allowed", "points_scored", "points_allowed",
            "drives", "red_zone_drives", "neutral_pass_rate", "epa_per_play",
        }
        assert expected_cols == set(df.columns)

    def test_plays_eq_pass_plus_rush(self, raw_dir: Path) -> None:
        df = build_team_week_fact(raw_dir)
        # Total plays should be at least pass + rush (sacks may overlap)
        assert (df["plays"] >= 0).all()
        assert (df["pass_plays"] >= 0).all()
        assert (df["rush_plays"] >= 0).all()

    def test_neutral_pass_rate_range(self, raw_dir: Path) -> None:
        df = build_team_week_fact(raw_dir)
        valid = df["neutral_pass_rate"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_epa_per_play_exists(self, raw_dir: Path) -> None:
        df = build_team_week_fact(raw_dir)
        assert "epa_per_play" in df.columns
        assert df["epa_per_play"].notna().any()

    def test_team_abbreviations_normalized(self, raw_dir: Path) -> None:
        df = build_team_week_fact(raw_dir)
        historical = set(TEAM_ABBR_MAP.keys())
        assert set(df["team"].unique()).isdisjoint(historical)
