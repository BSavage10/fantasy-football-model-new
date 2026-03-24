"""Gold layer: manual factor features.

Loads the manual_factors.csv, validates schema, rejects invalid entries,
expires stale factors, normalizes scores, and writes to Parquet.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = [
    "entity_id",
    "entity_type",
    "factor_name",
    "score_raw",
    "score_normalized",
    "confidence",
    "owner",
    "rationale",
    "expires_at",
]

REQUIRED_CSV_COLUMNS = [
    "entity_id",
    "entity_type",
    "factor_name",
    "score_raw",
    "confidence",
    "owner",
    "rationale",
]


def build_manual_factor_features(
    csv_path: Path,
    as_of_date: str,
) -> pd.DataFrame:
    """Load and validate manual factors from CSV.

    Rejects rows with:
    - score_raw outside [0, 1]
    - missing owner
    - missing rationale
    Expires rows past expires_at date.
    """
    if not csv_path.exists():
        logger.info("No manual factors file at %s — returning empty", csv_path)
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(csv_path)

    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    for col in REQUIRED_CSV_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"Manual factors CSV missing required column: {col}")

    if "expires_at" not in df.columns:
        df["expires_at"] = None

    initial_count = len(df)

    invalid_score = ~df["score_raw"].between(0.0, 1.0)
    if invalid_score.any():
        logger.warning(
            "Rejecting %d rows with score_raw outside [0, 1]",
            invalid_score.sum(),
        )
        df = df[~invalid_score].copy()

    missing_owner = df["owner"].isna() | (df["owner"].astype(str).str.strip() == "")
    if missing_owner.any():
        logger.warning("Rejecting %d rows with missing owner", missing_owner.sum())
        df = df[~missing_owner].copy()

    missing_rationale = df["rationale"].isna() | (df["rationale"].astype(str).str.strip() == "")
    if missing_rationale.any():
        logger.warning("Rejecting %d rows with missing rationale", missing_rationale.sum())
        df = df[~missing_rationale].copy()

    if df["expires_at"].notna().any():
        cutoff = pd.Timestamp(as_of_date)
        expires = pd.to_datetime(df["expires_at"], errors="coerce")
        expired = expires.notna() & (expires < cutoff)
        if expired.any():
            logger.info("Expiring %d stale manual factor entries", expired.sum())
            df = df[~expired].copy()

    df["score_normalized"] = df["score_raw"]

    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce").fillna(0.5)

    logger.info(
        "manual_factors: %d valid of %d total entries",
        len(df), initial_count,
    )

    result = df[[c for c in COLUMNS if c in df.columns]].copy()
    for col in COLUMNS:
        if col not in result.columns:
            result[col] = None

    return result[COLUMNS]


def write_manual_factor_features(
    manual_dir: Path,
    gold_dir: Path,
    as_of_date: str,
) -> Path:
    """Build and write manual_factor_features.parquet to the gold directory."""
    csv_path = manual_dir / "manual_factors.csv"
    features = build_manual_factor_features(csv_path, as_of_date)
    gold_dir.mkdir(parents=True, exist_ok=True)
    out_path = gold_dir / "manual_factor_features.parquet"
    features.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)
    return out_path
