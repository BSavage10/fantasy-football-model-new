"""Bronze layer: extract source data via nfl_data_py and snapshot to Parquet."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import nfl_data_py as nfl
import pandas as pd

from ffmodel.config import SourcesConfig

logger = logging.getLogger(__name__)

# ── Source extraction registry ──────────────────────────────────────────────
# Maps source name (from sources.yaml) → callable that returns a DataFrame.
# Each callable receives the list of seasons to fetch.

_SOURCE_EXTRACTORS: dict[str, callable] = {}


def _register(name: str):
    def decorator(fn):
        _SOURCE_EXTRACTORS[name] = fn
        return fn
    return decorator


@_register("pbp")
def _extract_pbp(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_pbp_data(seasons, downcast=False, include_participation=False)


@_register("weekly_stats")
def _extract_weekly_stats(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_weekly_data(seasons, downcast=False)


@_register("seasonal_stats")
def _extract_seasonal_stats(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_seasonal_data(seasons)


@_register("rosters")
def _extract_rosters(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_seasonal_rosters(seasons)


@_register("players")
def _extract_players(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_players()


@_register("schedules")
def _extract_schedules(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_schedules(seasons)


@_register("draft_picks")
def _extract_draft_picks(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_draft_picks()


@_register("depth_charts")
def _extract_depth_charts(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_depth_charts(seasons)


@_register("snap_counts")
def _extract_snap_counts(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_snap_counts(seasons)


@_register("combine")
def _extract_combine(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_combine_data()


@_register("contracts")
def _extract_contracts(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_contracts()


@_register("nextgen_passing")
def _extract_ngs_passing(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_ngs_data("passing")


@_register("nextgen_rushing")
def _extract_ngs_rushing(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_ngs_data("rushing")


@_register("nextgen_receiving")
def _extract_ngs_receiving(_seasons: list[int]) -> pd.DataFrame:
    return nfl.import_ngs_data("receiving")


@_register("pfr_passing")
def _extract_pfr_passing(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_seasonal_pfr("pass", seasons)


@_register("pfr_rushing")
def _extract_pfr_rushing(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_seasonal_pfr("rush", seasons)


@_register("pfr_receiving")
def _extract_pfr_receiving(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_seasonal_pfr("rec", seasons)


@_register("ff_opportunity")
def _extract_ff_opportunity(seasons: list[int]) -> pd.DataFrame:
    return nfl.import_ftn_data(seasons, downcast=False)


@_register("ff_rankings")
def _extract_ff_rankings(_seasons: list[int]) -> pd.DataFrame:
    # nfl_data_py does not have a direct ff_rankings import;
    # use draft values as a proxy for market priors
    return nfl.import_draft_picks()


# ── Hashing ─────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Public API ──────────────────────────────────────────────────────────────

def run_ingest(
    sources_config: SourcesConfig,
    as_of_date: str,
    data_dir: str | Path = "data",
) -> Path:
    """Extract all configured sources and write Parquet snapshots.

    Returns the output directory path.
    """
    data_dir = Path(data_dir)
    out_dir = data_dir / "raw" / as_of_date
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "_manifest.json"

    seasons = list(range(sources_config.seasons.min, sources_config.seasons.max + 1))
    all_sources = list(sources_config.required) + list(sources_config.optional)

    # Check for existing manifest — idempotent skip
    if manifest_path.exists():
        logger.info("Manifest already exists at %s — checking for completeness", manifest_path)
        existing = json.loads(manifest_path.read_text())
        existing_sources = set(existing.get("files", {}).keys())
        required_present = all(s in existing_sources for s in sources_config.required)
        if required_present:
            logger.info("All required sources present in existing snapshot — skipping ingest")
            return out_dir

    manifest: dict = {
        "as_of_date": as_of_date,
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "nfl_data_py_version": getattr(nfl, "__version__", "unknown"),
        "files": {},
    }

    for source_name in all_sources:
        extractor = _SOURCE_EXTRACTORS.get(source_name)
        if extractor is None:
            logger.warning("No extractor registered for source '%s' — skipping", source_name)
            continue

        is_required = source_name in sources_config.required
        parquet_path = out_dir / f"{source_name}.parquet"

        try:
            logger.info("Extracting source: %s", source_name)
            df = extractor(seasons)
            df.to_parquet(parquet_path, index=False)
            file_hash = _sha256_file(parquet_path)
            manifest["files"][source_name] = {
                "path": parquet_path.name,
                "rows": len(df),
                "columns": len(df.columns),
                "sha256": file_hash,
            }
            logger.info("  → %s: %d rows, %d columns", source_name, len(df), len(df.columns))
        except Exception as exc:
            if is_required:
                if sources_config.fallback_behavior.required_missing == "fail":
                    raise RuntimeError(
                        f"Required source '{source_name}' failed: {exc}"
                    ) from exc
            else:
                logger.warning("Optional source '%s' failed: %s — continuing", source_name, exc)

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    logger.info("Manifest written to %s", manifest_path)
    return out_dir
