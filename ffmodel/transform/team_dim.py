"""Silver layer: team dimension table.

Normalizes team abbreviations (OAK→LV, SD→LAC, STL→LA) and produces
team_dim.parquet with one row per franchise-season.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Historical abbreviation mappings → current franchise abbreviation.
# These reflect franchise relocations / rebranding.
TEAM_ABBR_MAP: dict[str, str] = {
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
    "WSH": "WAS",
}

# All 32 current NFL franchise abbreviations (2024+).
CURRENT_TEAMS = frozenset({
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
})

COLUMNS = ["team_key", "team_abbr", "season", "historical_aliases"]


def normalize_team_abbr(abbr: str) -> str:
    """Map a possibly-historical abbreviation to its current standard form."""
    if abbr is None:
        return abbr
    cleaned = str(abbr).strip().upper()
    return TEAM_ABBR_MAP.get(cleaned, cleaned)


def build_team_dim(raw_dir: Path, seasons: list[int]) -> pd.DataFrame:
    """Build team dimension table: one row per franchise-season.

    Sources team list from schedule or rosters; normalizes abbreviations.
    """
    # Collect all team abbreviations observed per season
    team_seasons: set[tuple[str, int]] = set()

    schedules_path = raw_dir / "schedules.parquet"
    rosters_path = raw_dir / "rosters.parquet"

    if schedules_path.exists():
        sched = pd.read_parquet(schedules_path)
        for col in ["home_team", "away_team"]:
            if col in sched.columns and "season" in sched.columns:
                pairs = sched[[col, "season"]].dropna().drop_duplicates()
                for _, row in pairs.iterrows():
                    team_seasons.add((str(row[col]), int(row["season"])))

    if rosters_path.exists():
        rosters = pd.read_parquet(rosters_path)
        team_col = "team" if "team" in rosters.columns else "recent_team"
        if team_col in rosters.columns and "season" in rosters.columns:
            pairs = rosters[[team_col, "season"]].dropna().drop_duplicates()
            for _, row in pairs.iterrows():
                team_seasons.add((str(row[team_col]), int(row["season"])))

    if not team_seasons:
        # Fallback: generate from CURRENT_TEAMS × requested seasons
        for team in sorted(CURRENT_TEAMS):
            for season in seasons:
                team_seasons.add((team, season))

    # Build records with normalization
    records = []
    for raw_abbr, season in sorted(team_seasons):
        norm = normalize_team_abbr(raw_abbr)
        aliases = raw_abbr if raw_abbr != norm else None
        records.append({
            "team_key": f"{norm}_{season}",
            "team_abbr": norm,
            "season": season,
            "historical_aliases": aliases,
        })

    df = pd.DataFrame(records, columns=COLUMNS)

    # Deduplicate — after normalization, (OAK, 2019) and (LV, 2019) might
    # both map to LV_2019. Keep first (which has the alias).
    df = df.drop_duplicates(subset=["team_key"], keep="first")
    df = df.sort_values(["season", "team_abbr"]).reset_index(drop=True)

    logger.info("team_dim: %d rows", len(df))
    return df


def write_team_dim(raw_dir: Path, silver_dir: Path, seasons: list[int]) -> Path:
    """Build and write team_dim.parquet to the silver directory."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    df = build_team_dim(raw_dir, seasons)
    out_path = silver_dir / "team_dim.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
