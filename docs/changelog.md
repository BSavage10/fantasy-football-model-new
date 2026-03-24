# Changelog

All notable changes to the ffmodel projection system, organized by implementation phase.

---

## Phase 2 — Data Ingestion & Canonical Transform (2026-03-24)

### Added
- **Ingest layer** (`ffmodel/ingest/snapshot.py`): Extracts all sources configured in `sources.yaml` via `nfl_data_py`, writes Parquet snapshots to `data/raw/{as_of_date}/`, and produces a `_manifest.json` with SHA-256 content hashes per file. Supports 16 source types (7 required, 9 optional).
- **Transform layer** — five silver-table modules that read bronze Parquet and write canonical tables to `data/silver/{as_of_date}/`:
  - `player_dim.py` — One row per player keyed on `gsis_id`. Bridges to `pfr_id`, filters to fantasy-relevant positions (QB/RB/WR/TE/K/FB).
  - `team_dim.py` — One row per franchise-season. Normalizes historical abbreviations (OAK→LV, SD→LAC, STL→LA, WSH→WAS). Exports `normalize_team_abbr()` shared across all transforms.
  - `schedule.py` — One row per game with standardized teams, spread/total lines, and scores.
  - `player_week.py` — One row per player-team-week with all counting stats. Aggregates 2pt conversions across pass/rush/rec, extracts return TDs from `special_teams_tds`.
  - `team_week.py` — PBP-derived team-week aggregates: play counts, dropbacks, neutral pass rate (margin ≤7, Q1–Q3), red zone drives (distinct drives with yardline_100 ≤ 20), EPA/play, points scored/allowed.
- **CLI dispatch** for `ingest` and `transform` subcommands — previously printed "not yet implemented".
- `--data-dir` CLI flag on all subcommands (defaults to `data`).
- `-v` / `--verbose` flag for debug logging.
- **30 transform tests** (`tests/test_transform.py`): uniqueness constraints, schema correctness, type enforcement, abbreviation normalization, data integrity.

### Changed
- `ffmodel/cli.py` — Refactored from stub dispatch to real command handlers with logging configuration.

---

## Phase 1 — Project Foundation (2026-03-24)

### Added
- Project skeleton: `pyproject.toml` (uv, Python 3.11+), `Makefile`, `.gitignore`.
- **Config system** (`ffmodel/config.py`): Frozen dataclasses for all 5 YAML config files — `ScoringConfig`, `LeagueConfig`, `ModelConfig`, `RankingConfig`, `SourcesConfig`. Aggregate `ProjectConfig` with deterministic SHA-256 config hash.
- Config files: `configs/scoring.yaml`, `configs/league.yaml`, `configs/model.yaml`, `configs/ranking.yaml`, `configs/sources.yaml` — all values verified against Yahoo league export.
- CLI entry point (`ffmodel/cli.py`) with argparse subcommands for all 7 pipeline steps.
- `ffmodel/__main__.py` for `python -m ffmodel` invocation.
- Data directory scaffolding: `data/raw/.gitkeep`, `data/silver/.gitkeep`, `data/gold/.gitkeep`, `outputs/.gitkeep`.
- **20 config tests** (`tests/test_config.py`): loading, validation, frozen enforcement, hash determinism.
