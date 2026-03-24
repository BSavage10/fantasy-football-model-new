"""Silver layer: player dimension table.

Reads raw players and rosters → produces player_dim.parquet with one row per
player, keyed on canonical_player_id (gsis_id).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = [
    "canonical_player_id",
    "gsis_id",
    "pfr_id",
    "name",
    "position",
    "birth_date",
    "college",
    "draft_year",
    "draft_round",
    "draft_pick",
    "entry_year",
]


def build_player_dim(raw_dir: Path) -> pd.DataFrame:
    """Build the player dimension table from raw sources.

    Uses the players table as the primary source, enriched with roster data
    for any missing fields.
    """
    players_path = raw_dir / "players.parquet"
    rosters_path = raw_dir / "rosters.parquet"

    if not players_path.exists():
        raise FileNotFoundError(f"Required source missing: {players_path}")

    players = pd.read_parquet(players_path)
    logger.info("Loaded players: %d rows", len(players))

    # ── Normalize column names ──────────────────────────────────────────
    # nflverse players table has gsis_id, display_name, position, etc.
    col_map = {}
    if "display_name" in players.columns:
        col_map["display_name"] = "name"
    elif "player_name" in players.columns:
        col_map["player_name"] = "name"

    # Draft info may be in various column names
    for raw_col, target_col in [
        ("draft_number", "draft_pick"),
        ("draft_club", "draft_team"),
    ]:
        if raw_col in players.columns:
            col_map[raw_col] = target_col

    if col_map:
        players = players.rename(columns=col_map)

    # ── Filter to relevant positions ────────────────────────────────────
    relevant_positions = {"QB", "RB", "WR", "TE", "K", "FB"}
    if "position" in players.columns:
        players = players[players["position"].isin(relevant_positions)].copy()

    # ── Extract gsis_id as canonical key ────────────────────────────────
    if "gsis_id" not in players.columns:
        raise ValueError("players table missing gsis_id column")

    players = players.dropna(subset=["gsis_id"]).copy()
    players["canonical_player_id"] = players["gsis_id"]

    # ── Compute entry_year from rosters if not available ────────────────
    if "entry_year" not in players.columns:
        if "rookie_year" in players.columns:
            players["entry_year"] = players["rookie_year"]
        elif rosters_path.exists():
            rosters = pd.read_parquet(rosters_path)
            if "player_id" in rosters.columns and "season" in rosters.columns:
                # Use gsis_id to match
                id_col = "player_id"
                if "gsis_id" in rosters.columns:
                    id_col = "gsis_id"
                entry = rosters.groupby(id_col)["season"].min().reset_index()
                entry.columns = [id_col, "entry_year"]
                players = players.merge(entry, left_on="gsis_id", right_on=id_col, how="left")
                if id_col != "gsis_id":
                    players = players.drop(columns=[id_col], errors="ignore")

    # ── Ensure all output columns exist ─────────────────────────────────
    for col in COLUMNS:
        if col not in players.columns:
            players[col] = None

    # ── Handle pfr_id bridging ──────────────────────────────────────────
    # nflverse IDs table provides cross-references
    ids_path = raw_dir / "ids.parquet"
    if ids_path.exists() and players["pfr_id"].isna().all():
        try:
            ids_df = pd.read_parquet(ids_path)
            if "gsis_id" in ids_df.columns and "pfr_id" in ids_df.columns:
                bridge = ids_df[["gsis_id", "pfr_id"]].dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")
                players = players.drop(columns=["pfr_id"], errors="ignore")
                players = players.merge(bridge, on="gsis_id", how="left")
        except Exception as exc:
            logger.warning("Could not load IDs table for pfr_id bridging: %s", exc)

    # ── Deduplicate on canonical_player_id ──────────────────────────────
    players = players.sort_values("canonical_player_id")
    players = players.drop_duplicates(subset=["canonical_player_id"], keep="first")

    # ── Cast types ──────────────────────────────────────────────────────
    for int_col in ["draft_year", "draft_round", "draft_pick", "entry_year"]:
        if int_col in players.columns:
            players[int_col] = pd.to_numeric(players[int_col], errors="coerce")

    if "birth_date" in players.columns:
        players["birth_date"] = pd.to_datetime(players["birth_date"], errors="coerce")

    result = players[COLUMNS].copy().reset_index(drop=True)
    logger.info("player_dim: %d rows", len(result))
    return result


def write_player_dim(raw_dir: Path, silver_dir: Path) -> Path:
    """Build and write player_dim.parquet to the silver directory."""
    silver_dir.mkdir(parents=True, exist_ok=True)
    df = build_player_dim(raw_dir)
    out_path = silver_dir / "player_dim.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
