# Changelog

All notable changes to the ffmodel projection system, organized by implementation phase.

---

## Phase 4 — Scoring Engine (2026-03-24)

### Added
- **Scoring engine** (`ffmodel/scoring/engine.py`): Three pure, stateless functions that translate projected season stats into fantasy points under a `ScoringConfig`:
  - `score_player(stats, position, config)` — Offensive players (QB/RB/WR/TE). Applies all scoring rules regardless of position (FR-005 cross-category support: WR rushing yards, RB passing TDs, etc.). Stats keys match `player_week_fact` column names.
  - `score_dst(stats, pa_per_game, games, config)` — DST unit. Scores component events (sacks, INTs, fumble recoveries, TDs, safeties, block kicks, return TDs, XP returns) plus a per-game bracket lookup on `pa_per_game` × `games`.
  - `score_kicker(stats, config)` — Kicker. XP + five FG distance buckets (0-19, 20-29, 30-39, 40-49, 50+).
  - `expected_pa_bracket_value(mean_pa, std_pa, brackets, n_samples)` — Monte Carlo expected value of the DST points-allowed bracket given a distribution of PA per game. Falls back to direct lookup when `std_pa == 0`.
- **Scoring package init** (`ffmodel/scoring/__init__.py`): Re-exports all four public functions.
- **28 scoring tests** (`tests/test_scoring.py`): QB exact total (286.22), RB half-PPR component sum (26.5), WR cross-position rushing credit (8.5), kicker full season (93.0), DST component+bracket (31.0), bracket boundary coverage, reconciliation (additivity), config-change sensitivity (INT -2→-1 shifts QB by INT_count×1, reception 0.5→1.0 shifts RB by catches×0.5, FG bucket change exact).

---

## Phase 3 — Feature Engineering (2026-03-24)

### Added
- **Feature layer** — five gold-table modules that read silver Parquet and write model-ready features to `data/gold/{as_of_date}/`:
  - `team_context.py` — One row per team for target season. Recency-weighted team environment projections (plays, dropbacks, rushes, targets, neutral pass rate, PROE, red zone drives/game, points/drive, EPA/play). Teams with <3 seasons of history shrink toward league averages.
  - `player_role.py` — One row per player for target season. Share-based role features (rush_share, target_share, starter_share_of_dropbacks, qb_rush_attempts_per_game). Detects team changers (blends historical shares with positional priors at configurable 70/30 weight) and rookies (draft-capital bucketed positional priors). Normalizes within-team shares to sum ≤1.0.
  - `efficiency.py` — One row per player for target season. Regressed efficiency rates via empirical Bayes shrinkage (`regress_rate()` function). Covers: yards_per_attempt, comp_rate, pass_td_rate, int_rate, yards_per_carry, yards_per_target, catch_rate, receiving_td_rate. League priors computed from all qualifying players in the training window.
  - `availability.py` — One row per player for target season. Games-active projection from weighted historical games-played, position-based shrinkage (configurable), per-position age discounts (RB threshold at 28, QB at 37, etc.), capped at 17 games.
  - `manual_factors.py` — Loads `manual/manual_factors.csv`, validates schema (rejects out-of-range scores, missing owner/rationale), expires stale entries past `expires_at`, writes validated factors to Parquet.
- **Manual factors template** (`manual/manual_factors.csv`) with header row and example entries.
- **CLI dispatch** for `features` subcommand — reads silver tables, calls all feature builders, writes gold tables.
- **36 feature tests** (`tests/test_features.py`): share sum constraints, leakage prevention, regress_rate known-value verification, rookie non-null features, team changer detection and blending, availability caps and age discounts, manual factor validation and expiration.

### Changed
- `ffmodel/cli.py` — Added `_cmd_features` handler and wired it into dispatch table.
- `CLAUDE.md` — Updated architecture, CLI, phase status, and test counts.

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
