# Fantasy Football Projection Model — Design Document

## Context

This document defines the implementation plan for a 2026 preseason fantasy football projection system. The target league is a 10-team, 2-QB, half-PPR Yahoo league (ID 1221676, "STOP!"). Draft is Mon Sep 1 2026 at 9:00pm EDT (live standard draft, 1-minute picks). Full requirements are in `docs/requirements.md` (887 lines). League scoring and settings verified from Yahoo export screenshots.

The core design principle is: **project underlying football statistics first, then translate to fantasy points via a config-driven scoring engine.** Rankings are a downstream product of projections — never hard-coded into the stat model.

This document will be handed to Claude Code for phase-by-phase implementation. Each phase has explicit scope, file list, and exit criteria.

---

## 1. Architectural Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| AD-1 | Python packaging | **uv** with Python 3.11+ | Fastest resolver, modern, simple `pyproject.toml` |
| AD-2 | Intermediate storage | **Parquet on disk** for all layers | No database dependency; sufficient for ~40M PBP rows; pandas reads Parquet natively |
| AD-3 | Orchestration | **argparse CLI + Makefile** | No framework overhead; each pipeline step is a CLI subcommand; Makefile wraps common workflows |
| AD-4 | Modeling approach | **Weighted historical averages + empirical Bayes regression-to-mean** | Simple, transparent, configurable; no ML framework dependency; matches what top projection systems use as their foundation |
| AD-5 | DST & Kicker | **In scope for v1** with lighter-weight models | Requirements have "Required" features for both; using same weighted-average approach with heavier regression on volatile stats |
| AD-6 | Uncertainty | **Bootstrap from historical residuals** | Simple; no distributional assumptions; samples both per-game variance and games-active variance |
| AD-7 | Environment | **Local machine only** | No containerization for v1; reproducibility via `uv.lock` + config hash |
| AD-8 | Manual factors | **CSV files** in `manual/` directory | Simplest edit format; analyst can use any spreadsheet tool |
| AD-9 | Raw data snapshots | **Explicit snapshot step** separate from nfl_data_py cache | Bronze layer is a deliberate immutable copy, not an ephemeral cache; required for reproducibility |
| AD-10 | Package name | **ffmodel** | Short, unambiguous, importable |

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| nfl_data_py | latest | NFL data extraction (nflverse ecosystem) |
| pandas | >=2.0 | Data manipulation |
| pyarrow | >=14.0 | Parquet I/O |
| numpy | >=1.24 | Numerical operations |
| scipy | >=1.11 | Stats functions (used in regression/bootstrap) |
| pyyaml | >=6.0 | Config file loading |
| pytest | >=7.0 | Testing (dev dependency) |

No scikit-learn, no XGBoost, no heavy ML frameworks. The entire modeling layer uses numpy/scipy/pandas.

---

## 2. System Architecture

### Pipeline Flow

```
CLI (argparse)
  │
  ├─ ingest    → data/raw/{as_of_date}/        [Bronze: immutable source snapshots]
  ├─ transform → data/silver/{as_of_date}/      [Silver: canonical normalized tables]
  ├─ features  → data/gold/{as_of_date}/        [Gold: model-ready feature tables]
  ├─ project   → outputs/{run_id}/projections/  [Model: component stat projections]
  ├─ rank      → outputs/{run_id}/rankings/     [Serving: fantasy points, ranks, VOR]
  └─ backtest  → outputs/backtest/              [Evaluation: historical accuracy]
```

Each step reads the previous layer's Parquet files and writes to its own directory. Steps are idempotent: re-running with the same inputs produces identical outputs.

### Modeling DAG (per player)

```
team_context (weighted avg of team history)
    │
    ├─→ player_role (player share × team volume)
    │       │
    │       └─→ efficiency (regressed rates × volume = per-game stats)
    │               │
    │               └─→ availability (games_active projection)
    │                       │
    │                       └─→ season_totals = per_game × games_active
    │                               │
    │                               └─→ scoring_engine(stats) → fantasy_points
    │                                       │
    │                                       └─→ overlay → ranking → export
```

### Key Algorithms

**Recency-weighted projection:** For each stat, compute per-game rates for each prior season, then weight them (default: 50% year-1, 30% year-2, 20% year-3). Configurable in `model.yaml`.

**Empirical Bayes regression-to-mean:** For noisy rates (TD rate, INT rate, YPC):
```
regressed = (observed × sample_size + prior × regression_sample) / (sample_size + regression_sample)
```
Where `regression_sample` is the "credibility weight" in pseudo-observations (configurable per stat).

**Rookie priors:** Draft-capital bucketed positional medians from historical data. A 1st-round RB gets a different opportunity prior than a 5th-round RB, anchored to the new team's context.

**Team changers:** Convert old-team shares to per-game volume, re-anchor to new team's projected volume, blend with scheme positional prior (configurable weight, default 70/30 player/team).

**Uncertainty (P25/P50/P75):** Bootstrap N=5000 samples by perturbing both per-game stats (from historical residual distribution) and games_active, score each sample, take percentiles.

**Manual overlays:** Post-model multiplicative adjustment. Each factor maps [0,1] to [1-15%, 1+15%] multiplier. Low-confidence (<0.30) factors are dampened toward neutral (0.50). Factors combine multiplicatively, capped at ±25% total effect. Delta between model-only and overlay-adjusted is published.

**DST points-allowed:** Monte Carlo over a normal distribution of game-level points-allowed (handles Jensen's inequality for nonlinear bracket scoring).

---

## 3. File Manifest

### Project Root

| File | Purpose | Phase |
|------|---------|-------|
| `pyproject.toml` | Project config, dependencies, build metadata | 1 |
| `Makefile` | Common CLI shortcuts (`make install`, `make test`, `make run`, `make backtest`) | 1 |
| `.gitignore` | Ignore data/, outputs/, .venv/, __pycache__/ | 1 |
| `CLAUDE.md` | **Modify** — update with implementation-specific guidance after each phase | 1 |

### Configuration (`configs/`)

| File | Purpose | Phase |
|------|---------|-------|
| `configs/scoring.yaml` | Fantasy point values per stat event (offense, kicker, DST brackets) | 1 |
| `configs/league.yaml` | League size, roster slots, flex eligibility, bench spots | 1 |
| `configs/model.yaml` | Recency weights, shrinkage settings, regression samples, overlay caps, uncertainty params | 1 |
| `configs/ranking.yaml` | Ranking objective, replacement level by position, VOR method | 1 |
| `configs/sources.yaml` | Data source list, season ranges, optional source toggles, fallback behavior | 1 |

### Data Directories

| Path | Purpose | Phase |
|------|---------|-------|
| `data/raw/.gitkeep` | Bronze layer — immutable source snapshots by as_of_date | 1 |
| `data/silver/.gitkeep` | Silver layer — canonical normalized tables | 1 |
| `data/gold/.gitkeep` | Gold layer — model-ready feature tables | 1 |

### Manual Input (`manual/`)

| File | Purpose | Phase |
|------|---------|-------|
| `manual/manual_factors.csv` | Template CSV with schema from Section 13 of requirements | 3 |

### Output Directory

| Path | Purpose | Phase |
|------|---------|-------|
| `outputs/.gitkeep` | Projection runs, rankings, backtest results | 1 |

### Documentation (`docs/`)

| File | Purpose | Phase |
|------|---------|-------|
| `docs/requirements.md` | **Exists** — source specification | — |
| `docs/decision_log.md` | Lightweight record of key design/implementation decisions | 7 |
| `docs/runbook.md` | Instructions for data refresh, reruns, manual factors, release | 7 |

### Source Code (`ffmodel/`)

#### Core

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/__init__.py` | Package init with version | 1 |
| `ffmodel/cli.py` | argparse CLI entry point: subcommands for ingest, transform, features, project, rank, run, backtest | 1 |
| `ffmodel/config.py` | YAML loading → frozen dataclasses (ScoringConfig, LeagueConfig, ModelConfig, RankingConfig, SourcesConfig); config hash computation | 1 |
| `ffmodel/pipeline.py` | Pipeline orchestrator: chains ingest→transform→features→project→overlay→score→rank→qa→export | 6 |

#### Ingest Layer

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/ingest/__init__.py` | — | 2 |
| `ffmodel/ingest/snapshot.py` | Extract all sources via nfl_data_py, write Parquet to `data/raw/{as_of_date}/`, create `_manifest.json` with content hashes; idempotent (skip if manifest hash matches) | 2 |

#### Transform Layer (Silver)

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/transform/__init__.py` | — | 2 |
| `ffmodel/transform/player_dim.py` | Raw players/rosters → `player_dim.parquet`. Stable canonical_player_id (gsis_id), ID bridges, position, draft metadata | 2 |
| `ffmodel/transform/team_dim.py` | Team normalization → `team_dim.parquet`. Handle abbreviation changes (OAK→LV, etc.), one row per franchise-season | 2 |
| `ffmodel/transform/schedule.py` | Raw schedules → `schedule_fact.parquet`. Game-level with spread/total lines | 2 |
| `ffmodel/transform/player_week.py` | Raw stats → `player_week_fact.parquet`. One row per player-team-week with all counting stats | 2 |
| `ffmodel/transform/team_week.py` | PBP aggregation → `team_week_fact.parquet`. Plays, dropbacks, rush plays, pass rate, red zone, EPA | 2 |

#### Feature Layer (Gold)

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/features/__init__.py` | — | 3 |
| `ffmodel/features/team_context.py` | team_week_fact → `team_context_features.parquet`. Team-season level: projected plays, dropbacks, rushes, targets, pass rate, PROE, red zone drives, points per drive | 3 |
| `ffmodel/features/player_role.py` | player_week_fact + team_week_fact → `player_role_features.parquet`. Player-season: rush_share, target_share, goal_line_share, snap_share, route_participation, air_yards_share, starter_share (QB), end_zone/red_zone shares | 3 |
| `ffmodel/features/efficiency.py` | player_week_fact → `player_efficiency_features.parquet`. Player-season: regressed rates (YPA, comp_rate, td_rate, int_rate, YPC, yards_per_target, catch_rate). Contains the `regress_rate()` function | 3 |
| `ffmodel/features/availability.py` | player_week_fact + player_dim → `availability_features.parquet`. Player-season: historical games played, age, years_pro, career_games_played, games_active_proj | 3 |
| `ffmodel/features/manual_factors.py` | Load CSV, validate schema (reject out-of-range scores, missing owner/rationale), expire stale entries, normalize direction, write `manual_factor_features.parquet` | 3 |

#### Models

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/models/__init__.py` | — | 5 |
| `ffmodel/models/base.py` | `StatProjection` dataclass (per_game, season_total, games_active, position, player_id, reason_codes, qc_flags, is_rookie, is_team_changer). Shared utility functions: `weighted_mean()`, `regress_rate()` (moved here from features for reuse), `detect_team_changer()`, `get_rookie_prior()` | 5 |
| `ffmodel/models/qb.py` | QB projector: team_dropbacks × starter_share → pass_attempts; separate rush model; efficiency rates; games_active; season totals | 5 |
| `ffmodel/models/rb.py` | RB projector: team_rushes × rush_share + team_targets × target_share; goal_line_share for TDs; efficiency rates; games_active | 5 |
| `ffmodel/models/wr.py` | WR projector: team_targets × target_share; air_yards_share; end_zone targets; efficiency rates; games_active | 5 |
| `ffmodel/models/te.py` | TE projector: route_participation × target_share; route_vs_block_rate; efficiency rates; games_active | 5 |
| `ffmodel/models/dst.py` | DST projector: sacks, INTs, fumble recoveries (regressed), DST TDs (heavily regressed), points-allowed via Monte Carlo bracket expectation | 5 |
| `ffmodel/models/kicker.py` | Kicker projector: team_points → XP volume; drives_into_fg_range × red_zone_stall_rate → FG attempts by 5 distance buckets (0-19, 20-29, 30-39, 40-49, 50+); FG accuracy | 5 |
| `ffmodel/models/baselines.py` | Three challenger baselines: weighted-history, last-year-points, market-prior. Each returns projections in the same format as position models | 5 |
| `ffmodel/models/uncertainty.py` | Bootstrap P25/P50/P75: sample per-game residuals + games_active variance from historical data, score each sample, take percentiles | 5 |

#### Scoring

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/scoring/__init__.py` | — | 4 |
| `ffmodel/scoring/engine.py` | Pure functions: `score_player(stats, position, config) → float`, `score_dst(stats, pa_per_game, games, config) → float`, `score_kicker(stats, config) → float`. Also `expected_pa_bracket_value()` for DST nonlinear scoring. Zero state, zero side effects | 4 |

#### Overlay

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/overlay/__init__.py` | — | 6 |
| `ffmodel/overlay/applicator.py` | `apply_manual_overlays(projections, manual_factors, config)`. Dampens low-confidence scores, converts to multipliers (±15% per factor), aggregates multiplicatively (±25% total cap), returns both model_only and overlay_adjusted columns with delta | 6 |

#### Ranking

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/ranking/__init__.py` | — | 6 |
| `ffmodel/ranking/ranker.py` | `compute_rankings(projections, league_config, ranking_config)`. Adds position_rank, overall_rank, replacement_level_points, VOR. Ranking objective is configurable (median/upside/risk-adjusted) | 6 |

#### QA

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/qa/__init__.py` | — | 6 |
| `ffmodel/qa/checks.py` | Implements QC-001 through QC-012 from requirements Section 10.1. Returns pass/fail per check with details. Computes QA flags (low_sample, missing_source, manual_heavy, volatile_touchdown_dependence). Pipeline fails fast on critical check failures | 6 |

#### Export

| File | Purpose | Phase |
|------|---------|-------|
| `ffmodel/export/__init__.py` | — | 6 |
| `ffmodel/export/writer.py` | Writes final output tables to CSV + Parquet. Generates `schema.json` with field names, types, nullability, and definitions (FR-025). Creates `projection_run_fact` with run_id, as_of_date, source manifest hash, git SHA, config hash | 6 |

### Tests (`tests/`)

| File | Purpose | Phase |
|------|---------|-------|
| `tests/__init__.py` | — | 1 |
| `tests/conftest.py` | Shared fixtures: sample DataFrames for player_week_fact, team_week_fact, player_dim; sample configs; temp directory management | 1 |
| `tests/test_config.py` | Config loading, validation, missing fields, config hash determinism | 1 |
| `tests/test_scoring.py` | Known stat lines → exact fantasy points for all positions; cross-position stats; scoring reconciliation; config change produces different points | 4 |
| `tests/test_transform.py` | Canonical table schema correctness, deduplication, ID bridging, team abbreviation normalization | 2 |
| `tests/test_features.py` | Recency weighting math, share sums ≈1.0 per team, regression-to-mean calculation, no future data leakage, rookie feature fill | 3 |
| `tests/test_models.py` | All positions produce required stat columns; rookie gets non-null projection; team changer uses new team context; per_game × games_active ≈ season_total; DST bracket scoring; kicker distance buckets | 5 |
| `tests/test_overlay.py` | Neutral factor (0.50) → no change; max effect capped at 15%; low confidence dampened; aggregate cap at 25%; delta correctly computed; model_only and overlay_adjusted both present; manual_heavy flag triggered | 6 |
| `tests/test_ranking.py` | Position ranks contiguous starting at 1; overall ranks contiguous; higher points → better rank; VOR calculation correct; replacement level configurable | 6 |
| `tests/test_qa.py` | Duplicate key detection; range check flags; scoring reconciliation check; share sanity check; missing source flags | 6 |
| `tests/test_pipeline.py` | End-to-end integration test on small fixture data: full pipeline produces expected output schema; run metadata captured; outputs reproducible with same inputs | 6 |

### File Count Summary

| Category | Count |
|----------|-------|
| Python source (ffmodel/) | 30 |
| Tests | 11 |
| Config YAML | 5 |
| Documentation | 3 (1 existing, 2 new) |
| Project files (pyproject.toml, Makefile, .gitignore) | 3 |
| Data/output .gitkeep files | 4 |
| Manual CSV | 1 |
| **Total** | **57** |

---

## 4. Configuration Contracts

### scoring.yaml

> All values verified against Yahoo league export screenshot (March 2026). The only non-default setting is interceptions at -2 (Yahoo default: -1).

```yaml
offense:
  passing_yards_per_point: 25.0    # 0.04 per yard
  passing_td: 4.0
  interception: -2.0               # Custom: Yahoo default is -1
  rushing_yards_per_point: 10.0    # 0.10 per yard
  rushing_td: 6.0
  reception: 0.5                   # Half-PPR
  receiving_yards_per_point: 10.0
  receiving_td: 6.0
  return_td: 6.0
  two_pt_conversion: 2.0
  fumble_lost: -2.0
  offensive_fumble_return_td: 6.0

kicker:
  fg_0_19: 3.0
  fg_20_29: 3.0
  fg_30_39: 3.0
  fg_40_49: 4.0
  fg_50_plus: 5.0
  pat_made: 1.0

dst:
  sack: 1.0
  interception: 2.0
  fumble_recovery: 2.0
  touchdown: 6.0
  safety: 2.0
  block_kick: 2.0
  return_td: 6.0
  extra_point_return: 2.0
  points_allowed_brackets:
    - [0, 0, 10.0]
    - [1, 6, 7.0]
    - [7, 13, 4.0]
    - [14, 20, 1.0]
    - [21, 27, 0.0]
    - [28, 34, -1.0]
    - [35, 999, -4.0]
```

### league.yaml

```yaml
league_id: 1221676
league_name: "STOP!"
platform: yahoo
teams: 10
divisions: 2
scoring_type: head_to_head
fractional_points: true
negative_points: true
roster_slots:
  QB: 2
  WR: 2
  RB: 2
  TE: 1
  FLEX: 1      # W/R/T
  K: 1
  DEF: 1
  BN: 6
  IR: 1
flex_eligible: [RB, WR, TE]
draft:
  type: live_standard
  date: "2026-09-01"    # Mon Sep 1 — as_of_date should be before this
  pick_time_seconds: 60
playoffs:
  teams: 6
  weeks: [15, 16, 17]
  tie_breaker: higher_seed_wins
  reseeding: true
  seeding: overall_standings
waiver:
  type: fab_reverse_standings
  time_days: 2
  weekly_deadline: game_time_tuesday
```

> **Verified:** Roster is 6 bench spots + 1 IR, confirmed from Yahoo league export screenshot. The requirements doc (A3) was correct. Scoring screenshot also confirms all values match this config exactly — the only non-default setting is interceptions at -2 (Yahoo default: -1).

### model.yaml

```yaml
recency_weights:
  1: 0.50    # Most recent season
  2: 0.30
  3: 0.20

regression_samples:     # Pseudo-observations for Bayes shrinkage
  pass_td_rate: 1500    # Pass attempts
  int_rate: 800
  yards_per_carry: 600
  catch_rate: 150       # Targets
  receiving_td_rate: 300
  yards_per_attempt: 600
  dst_td_rate: 500      # Defensive plays

games_active:
  default_max: 17
  shrinkage: 0.20       # Blend 80% player history, 20% position average
  position_prior:
    QB: 16.0
    RB: 14.5
    WR: 15.5
    TE: 15.0
    K: 16.5
    DEF: 17.0
  low_sample_threshold: 8   # Games; below this, flag as low_sample

overlay:
  enabled: true
  max_effect_per_factor: 0.15
  max_total_effect: 0.25
  low_confidence_threshold: 0.30

uncertainty:
  method: bootstrap_residual
  n_samples: 5000
  percentiles: [25, 50, 75]

team_changer:
  player_history_weight: 0.70
  team_prior_weight: 0.30

rookie:
  draft_round_buckets: ["1.01-1.12", "1.13-1.32", "2", "3", "4-5", "6-7", "UDFA"]
```

### ranking.yaml

```yaml
ranking_objective: median   # median | upside | risk_adjusted
replacement_level:
  QB: 20     # 10 teams × 2 starters
  RB: 20
  WR: 30
  TE: 10
  K: 10
  DEF: 10
vor_method: simple
```

### sources.yaml

```yaml
seasons:
  min: 2020
  max: 2025
  target: 2026

required:
  - pbp
  - weekly_stats
  - seasonal_stats
  - rosters
  - players
  - schedules
  - draft_picks

optional:
  - depth_charts
  - snap_counts
  - combine
  - contracts
  - nextgen_passing
  - nextgen_rushing
  - nextgen_receiving
  - pfr_passing
  - pfr_rushing
  - pfr_receiving
  - ff_opportunity
  - ff_rankings

fallback_behavior:
  optional_missing: warn_and_continue
  required_missing: fail
```

---

## 5. Data Model

### Silver Layer Tables

**player_dim** — 1 row per player

| Column | Type | Notes |
|--------|------|-------|
| canonical_player_id | str | Primary key (gsis_id from nflverse) |
| gsis_id | str | NFL GSIS identifier |
| pfr_id | str (nullable) | Pro Football Reference ID |
| name | str | Display name |
| position | str | QB, RB, WR, TE, K |
| birth_date | date (nullable) | For age calculation |
| college | str (nullable) | |
| draft_year | int (nullable) | |
| draft_round | int (nullable) | |
| draft_pick | int (nullable) | |
| entry_year | int | First NFL season |

**team_dim** — 1 row per franchise-season

| Column | Type | Notes |
|--------|------|-------|
| team_key | str | Primary key (e.g., "KC_2025") |
| team_abbr | str | Standardized abbreviation |
| season | int | |
| historical_aliases | str (nullable) | Comma-separated prior abbreviations |

**schedule_fact** — 1 row per game

| Column | Type | Notes |
|--------|------|-------|
| game_id | str | Primary key |
| season | int | |
| week | int | |
| home_team | str | Standardized abbreviation |
| away_team | str | |
| game_date | date | |
| spread_line | float (nullable) | |
| total_line | float (nullable) | |
| home_score | int (nullable) | Null for future games |
| away_score | int (nullable) | |

**player_week_fact** — 1 row per player-team-week

| Column | Type | Notes |
|--------|------|-------|
| canonical_player_id | str | FK → player_dim |
| season | int | |
| week | int | |
| team | str | |
| position | str | |
| games_played | int | 0 or 1 |
| pass_att | int | |
| pass_cmp | int | |
| pass_yd | float | |
| pass_td | int | |
| interceptions | int | |
| rush_att | int | |
| rush_yd | float | |
| rush_td | int | |
| targets | int | |
| receptions | int | |
| rec_yd | float | |
| rec_td | int | |
| fumbles_lost | int | |
| two_pt_conv | int | |
| return_td | int | |
| sacks_taken | int | QB only |

**team_week_fact** — 1 row per team-week

| Column | Type | Notes |
|--------|------|-------|
| team | str | |
| season | int | |
| week | int | |
| plays | int | Total offensive plays |
| pass_plays | int | Including sacks |
| rush_plays | int | |
| dropbacks | int | Pass attempts + sacks |
| sacks_allowed | int | |
| points_scored | int | |
| points_allowed | int | |
| drives | int | |
| red_zone_drives | int | |
| neutral_pass_rate | float | Pass rate in neutral game states |
| epa_per_play | float | |

### Gold Layer Tables

**team_context_features** — 1 row per team-season (projected into target season)

Key fields: `team_plays_proj`, `team_dropbacks_proj`, `team_rushes_proj`, `team_targets_proj`, `neutral_pass_rate_proj`, `proe_proj`, `red_zone_drives_per_game_proj`, `points_per_drive_proj`

**player_role_features** — 1 row per player-season

Key fields (vary by position): `rush_share`, `target_share`, `goal_line_share`, `snap_share`, `route_participation`, `air_yards_share`, `end_zone_target_share`, `red_zone_target_share`, `starter_share_of_dropbacks` (QB), `route_vs_block_rate` (TE), `qb_rush_attempts_per_game` (QB)

**player_efficiency_features** — 1 row per player-season

Key fields: `yards_per_attempt` (regressed), `comp_rate`, `pass_td_rate_regressed`, `int_rate_regressed`, `yards_per_carry_regressed`, `yards_per_target`, `catch_rate`, `receiving_td_rate_regressed`

**availability_features** — 1 row per player-season

Key fields: `games_played_y1`, `games_played_y2`, `games_played_y3`, `career_games_played`, `age_at_season_start`, `years_pro`, `games_active_proj`

---

## 6. Implementation Phases

### Phase 1: Project Foundation

**Scope:** Project skeleton, config system, CLI structure, test infrastructure.

**Files created:**
- `pyproject.toml`
- `Makefile`
- `.gitignore`
- `configs/scoring.yaml`, `configs/league.yaml`, `configs/model.yaml`, `configs/ranking.yaml`, `configs/sources.yaml`
- `data/raw/.gitkeep`, `data/silver/.gitkeep`, `data/gold/.gitkeep`, `outputs/.gitkeep`
- `ffmodel/__init__.py`, `ffmodel/cli.py`, `ffmodel/config.py`
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_config.py`

**Exit criteria:**
1. `uv sync` installs all dependencies
2. `python -m ffmodel --help` prints subcommand list
3. `python -m ffmodel ingest --help` prints ingest options
4. `pytest tests/test_config.py` passes: configs load, validate, produce deterministic hash
5. Config dataclasses are frozen (immutable)

---

### Phase 2: Data Ingestion & Canonical Transform

**Scope:** Bronze snapshot extraction, silver canonical tables, transform tests.

**Files created:**
- `ffmodel/ingest/__init__.py`, `ffmodel/ingest/snapshot.py`
- `ffmodel/transform/__init__.py`, `ffmodel/transform/player_dim.py`, `ffmodel/transform/team_dim.py`, `ffmodel/transform/schedule.py`, `ffmodel/transform/player_week.py`, `ffmodel/transform/team_week.py`
- `tests/test_transform.py`

**Key implementation details:**

`snapshot.py`:
- Calls nfl_data_py functions for each source in sources.yaml
- Writes raw DataFrames to `data/raw/{as_of_date}/{source_name}.parquet`
- Creates `_manifest.json` with extraction timestamp, nfl_data_py version, and SHA-256 hash of each file
- Idempotent: if manifest exists and hashes match, skip re-extraction
- Optional sources that fail → log warning, continue

`player_dim.py`:
- Use gsis_id as canonical_player_id (most stable nflverse key)
- Bridge to pfr_id where available
- Handle duplicate entries via deduplication on gsis_id

`team_dim.py`:
- Normalize team abbreviations (OAK→LV, SD→LAC, STL→LA)
- One row per franchise-season

`team_week.py`:
- Aggregate PBP data at team-week level
- Compute derived fields: neutral_pass_rate (filter to neutral game states: score margin ≤ 7, Q1-Q3)
- red_zone_drives: count distinct drives with plays at yardline_100 ≤ 20

**Exit criteria:**
1. `python -m ffmodel ingest --as-of-date 2025-09-01` creates Parquet files in `data/raw/2025-09-01/`
2. `python -m ffmodel transform --as-of-date 2025-09-01` creates silver tables
3. `pytest tests/test_transform.py` passes:
   - No duplicate canonical_player_id in player_dim
   - No duplicate (team, season) in team_dim
   - No duplicate (canonical_player_id, season, week, team) in player_week_fact
   - Schedule has 272 games per season (17 weeks × 32 teams / 2)
   - Team abbreviations are standardized

---

### Phase 3: Feature Engineering

**Scope:** Gold-layer feature computation, manual factor loading.

**Files created:**
- `ffmodel/features/__init__.py`, `ffmodel/features/team_context.py`, `ffmodel/features/player_role.py`, `ffmodel/features/efficiency.py`, `ffmodel/features/availability.py`, `ffmodel/features/manual_factors.py`
- `manual/manual_factors.csv` (template with header row + example entries)
- `tests/test_features.py`

**Key implementation details:**

All feature functions take `target_season: int` and filter to `season < target_season`. This is the **leakage gate**.

`team_context.py`:
- For each team, aggregate team_week_fact by season, then apply recency-weighted average across prior seasons
- Handle teams with <3 seasons of history by shrinking toward league average
- Output: one row per team for target_season

`player_role.py`:
- Compute share-based features per player-season-team stint (handles mid-season trades)
- Weight shares by recency
- For team changers: convert shares to per-game volume, re-anchor to new team, blend with positional prior
- For rookies: use draft-capital bucketed historical medians

`efficiency.py`:
- Contains `regress_rate(observed, sample_size, prior, regression_sample)` function
- Compute all efficiency rates then apply regression
- League prior rates computed from all qualifying players in the training window

`availability.py`:
- Weighted average of prior season games-played counts
- Age discount for players over position-specific threshold (e.g., 28 for RB)
- Shrink toward position average
- Cap at 17 games

`manual_factors.py`:
- Load CSV, validate schema
- Reject: score_raw outside [0,1], missing owner, missing rationale
- Expire entries past expires_at
- Compute score_normalized (all factors already defined as 1.0 = favorable)
- Write validated factors to Parquet

**Exit criteria:**
1. `python -m ffmodel features --as-of-date 2025-09-01` creates gold tables
2. `pytest tests/test_features.py` passes:
   - Target shares sum to ≤1.05 per team-season (tolerance for rounding)
   - Rush shares sum to ≤1.05 per team-season
   - No feature contains data from target_season (leakage test)
   - `regress_rate(0.06, 500, 0.045, 1500)` produces expected value
   - Rookie features are non-null for players with years_pro=0
   - Team changer features use new team context

---

### Phase 4: Scoring Engine

**Scope:** Config-driven fantasy point translation. This is the most testable module.

**Files created:**
- `ffmodel/scoring/__init__.py`, `ffmodel/scoring/engine.py`
- `tests/test_scoring.py`

**Key implementation details:**

Three pure functions:
1. `score_player(stats: dict, position: str, config: ScoringConfig) → float`
2. `score_dst(stats: dict, pa_per_game: float, games: float, config: ScoringConfig) → float`
3. `score_kicker(stats: dict, config: ScoringConfig) → float`

Plus `expected_pa_bracket_value(mean_pa, std_pa, brackets, n_samples=10000)` for DST nonlinear scoring.

All functions are stateless. Config is the only parameter that controls scoring behavior.

FR-005 compliance: any position can receive credit for any stat (WR rushing yards, RB passing TD). The `score_player` function applies all stat multipliers regardless of position.

**Exit criteria:**
1. `pytest tests/test_scoring.py` passes with these exact test cases:

   **QB test:** Patrick Mahomes 2023-style season: 4183 pass_yd, 27 pass_td, 14 int, 389 rush_yd, 0 rush_td, 0 receptions, 0 fumbles_lost → expected: 4183×0.04 + 27×4 + 14×(-2) + 389×0.1 + 0 = 167.32 + 108 + (-28) + 38.9 = **286.22**

   **RB test (half-PPR):** A stat line with rushing and receiving → verify component breakdown sums to total

   **WR rushing play:** WR with 3 rush_att, 25 rush_yd, 1 rush_td → rushing points correctly added

   **DST test:** Known component events + points-allowed bracket → exact total

   **Kicker test:** 35 XP + 2 FG 0-19 + 3 FG 20-29 + 3 FG 30-39 + 6 FG 40-49 + 2 FG 50+ → 35×1 + 2×3 + 3×3 + 3×3 + 6×4 + 2×5 = 35 + 6 + 9 + 9 + 24 + 10 = **93.0**

   **Reconciliation:** `score_player(projection.season_stats)` == `projection.total_points_proj_p50` within 0.01

   **Config change:** Changing `interception` from -2 to -1 changes QB points by exactly `INT_count × 1`

---

### Phase 5: Position Models & Uncertainty

**Scope:** All six position projectors, baselines, uncertainty bands.

**Files created:**
- `ffmodel/models/__init__.py`, `ffmodel/models/base.py`, `ffmodel/models/qb.py`, `ffmodel/models/rb.py`, `ffmodel/models/wr.py`, `ffmodel/models/te.py`, `ffmodel/models/dst.py`, `ffmodel/models/kicker.py`, `ffmodel/models/baselines.py`, `ffmodel/models/uncertainty.py`
- `tests/test_models.py`

**Key implementation details:**

`base.py`:
- `StatProjection` dataclass with per_game dict, season_total dict, games_active, position, player_id, reason_codes, qc_flags, is_rookie, is_team_changer
- `weighted_mean(values, weights)` utility
- `regress_rate()` (shared with features)
- `detect_team_changer(player_id, player_dim, player_week_fact, target_season)` → bool
- `get_rookie_prior(position, draft_round_bucket, historical_data)` → dict of per-game stat priors

Each position projector (`qb.py`, `rb.py`, etc.):
- Function signature: `project_position(players_df, team_context_df, role_df, efficiency_df, availability_df, config) → list[StatProjection]`
- Iterates over players at that position
- Follows the DAG: team volume × player share × efficiency = per-game stats
- `season_total = per_game × games_active`
- Generates reason_codes (e.g., "high_rush_volume", "td_regression_applied", "rookie_prior_used")

`baselines.py`:
- `baseline_weighted_history(player_week_fact, target_season, scoring_config, weights)` — project as weighted-average of historical fantasy points
- `baseline_last_year(player_week_fact, target_season, scoring_config)` — project as last season's total
- `baseline_market_prior(ff_rankings, target_season)` — use archived ADP/consensus (when available)
- Each returns a DataFrame matching the projection output schema

`uncertainty.py`:
- `compute_uncertainty(projection, historical_residuals, scoring_config, n_samples, rng)` → (p25, p50, p75)
- Historical residuals: for each position, compute (actual_per_game - projected_per_game) for each player-season in the backtest window
- Bootstrap: for each sample, perturb per_game stats by a random residual + perturb games_active, then score
- Use numpy random Generator for reproducibility

**Exit criteria:**
1. `python -m ffmodel project --as-of-date 2025-09-01` produces projections for all positions
2. `pytest tests/test_models.py` passes:
   - QB projection has: pass_att, pass_cmp, pass_yd, pass_td, interceptions, rush_att, rush_yd, rush_td, fumbles_lost, games_active
   - RB projection has: rush_att, rush_yd, rush_td, targets, receptions, rec_yd, rec_td, fumbles_lost, games_active
   - WR/TE projections have receiving + optional rushing stats
   - DST projection has: sacks, interceptions, fumble_recoveries, dst_td, points_allowed_bucket_value
   - Kicker projection has: xp_made, fg_made_0_19, fg_made_20_29, fg_made_30_39, fg_made_40_49, fg_made_50_plus
   - Rookie player gets non-null projections with `is_rookie=True`
   - Team changer uses new team's context features
   - `per_game × games_active ≈ season_total` within 0.1 for each stat
   - P25 < P50 < P75 for all players
   - Baselines produce non-empty projections

---

### Phase 6: Overlay, Ranking, QA & Export

**Scope:** Manual overlay application, ranking layer, QA checks, output writer, pipeline orchestrator.

**Files created:**
- `ffmodel/overlay/__init__.py`, `ffmodel/overlay/applicator.py`
- `ffmodel/ranking/__init__.py`, `ffmodel/ranking/ranker.py`
- `ffmodel/qa/__init__.py`, `ffmodel/qa/checks.py`
- `ffmodel/export/__init__.py`, `ffmodel/export/writer.py`
- `ffmodel/pipeline.py`
- `tests/test_overlay.py`, `tests/test_ranking.py`, `tests/test_qa.py`, `tests/test_pipeline.py`

**Key implementation details:**

`applicator.py` (manual overlay math):
1. Dampen low-confidence: `if confidence < 0.30: effective_score = 0.50 + (confidence/0.30) × (score - 0.50)`
2. Factor → multiplier: `1.0 + (dampened_score - 0.50) × 2 × max_effect`
3. Aggregate multiplicatively across all factors for a player (team-level + player-level)
4. Cap total at ±max_total_effect (default ±25%)
5. `overlay_adjusted = model_only × combined_multiplier`
6. `overlay_delta = overlay_adjusted - model_only`
7. Flag `manual_heavy` if `|delta| / model_only > 0.10`

`ranker.py`:
- Sort by total_points_proj_p50 (or p75 for "upside" objective)
- Assign position_rank (1-indexed, within position)
- Assign overall_rank (1-indexed, across all positions)
- Compute VOR: `vor = total_points - replacement_level_points[position]`
- replacement_level_points = points of the Nth-ranked player at that position (N from ranking.yaml)

`checks.py` — implements QC-001 through QC-012:
- QC-001: No duplicate keys in output tables
- QC-002: All draftable players have resolved canonical IDs
- QC-003: Team-level shares sum within tolerance (±5%)
- QC-004: Range checks (games 0-17, attempts ≥0, etc.)
- QC-005: Scoring reconciliation (recompute points from stats, compare)
- QC-006: Missingness below threshold
- QC-007: No leakage (verify feature seasons < target)
- QC-008: Every manual factor has owner + rationale + timestamp
- QC-009: Player opportunities ≤ team totals
- QC-010: DST bracket values match config
- QC-011: Kicker bucket totals reconcile
- QC-012: Output schema matches versioned contract

Returns: list of (check_id, pass/fail, details). Pipeline fails on any critical failure.

`writer.py`:
- Writes player_projection, dst_projection, kicker_projection to both Parquet and CSV
- Writes combined_rankings.csv (all positions merged)
- Writes schema.json documenting every field
- Writes projection_run_fact with run_id, as_of_date, manifest hash, git SHA, config hash, timestamp

`pipeline.py`:
- Orchestrates: ingest → transform → features → project → overlay → score → rank → QA → export
- Each step checks for cached results (idempotent)
- `run_id` format: `{as_of_date}_{YYYYMMDD_HHMMSS}_{config_hash[:8]}`
- Full `run` command executes all steps; individual steps can run via CLI subcommands

**Exit criteria:**
1. `python -m ffmodel run --as-of-date 2025-09-01` completes end-to-end and produces:
   - `outputs/{run_id}/rankings/player_projection.csv` + `.parquet`
   - `outputs/{run_id}/rankings/dst_projection.csv` + `.parquet`
   - `outputs/{run_id}/rankings/kicker_projection.csv` + `.parquet`
   - `outputs/{run_id}/rankings/combined_rankings.csv`
   - `outputs/{run_id}/rankings/schema.json`
   - `outputs/{run_id}/projections/projection_run_fact.parquet`
2. All QA checks pass (or failures are documented with reason)
3. `pytest tests/test_overlay.py tests/test_ranking.py tests/test_qa.py tests/test_pipeline.py` all pass

---

### Phase 7: Evaluation & Documentation

**Scope:** Backtest framework, baseline comparison, documentation.

**Files modified:**
- `ffmodel/cli.py` — add `backtest` subcommand
- `ffmodel/models/baselines.py` — ensure baselines produce full backtest-compatible output

**Files created:**
- `ffmodel/backtest.py` — rolling-origin backtest runner
- `docs/decision_log.md`
- `docs/runbook.md`

**Key implementation details:**

`backtest.py`:
- Rolling-origin protocol: for each holdout season in [first_available + min_train_seasons ... last_available]:
  1. Set as_of_date to Sept 1 of holdout season
  2. Filter all data to seasons < holdout
  3. Run full pipeline (features → project → score)
  4. Load actuals for holdout season (compute actual fantasy points from player_week_fact)
  5. Join projections to actuals, compute errors
- **Manual factors excluded** from headline backtest numbers (not historically reconstructable)
- Market-prior baseline only included for seasons where archived ADP exists
- Compute per holdout season: MAE, RMSE, Spearman rank correlation, top-N hit rate, calibration
- Archetype slices: rookies, team changers, injured returnees, committee RBs, mobile QBs
- Compare model vs all three baselines on every metric
- Output to `outputs/backtest/`: backtest_results.parquet, backtest_summary.csv, baseline_comparison.csv

Leakage prevention:
- Every feature function filters `season < target_season` (enforced in function signature)
- No future rosters used for historical backtests
- No actual game scores used as features
- Automated leakage test verifies no features from target_season or later

**Exit criteria:**
1. `python -m ffmodel backtest --seasons 2023,2024,2025` completes and produces evaluation files
2. Model outperforms weighted-history baseline on aggregate offensive MAE (SC-002)
3. Rank correlation exceeds baseline on offensive pool
4. `docs/runbook.md` covers: data refresh, model rerun, manual factor editing, release checklist
5. `docs/decision_log.md` captures key decisions made during implementation

---

## 7. Test & Verification Plan

This section provides the step-by-step verification procedure that Claude Code should execute after each phase and at the end of the full implementation.

### Per-Phase Verification

After each phase, run: `pytest tests/ -v` and verify all tests pass for that phase's test files.

### Full System Verification (after Phase 7)

Execute these steps in order. Each step must pass before proceeding.

**Step 1: Environment**
```
uv sync
python -m ffmodel --help
```
Verify: clean install, help text lists all subcommands.

**Step 2: Config Loading**
```
pytest tests/test_config.py -v
```
Verify: all config files load, validate, produce deterministic hashes.

**Step 3: Data Ingestion (single season)**
```
python -m ffmodel ingest --as-of-date 2025-09-01
ls data/raw/2025-09-01/
```
Verify: Parquet files exist for all required sources; `_manifest.json` exists.

**Step 4: Canonical Transform**
```
python -m ffmodel transform --as-of-date 2025-09-01
pytest tests/test_transform.py -v
```
Verify: silver tables exist; no duplicate keys; team abbreviations normalized.

**Step 5: Feature Engineering**
```
python -m ffmodel features --as-of-date 2025-09-01
pytest tests/test_features.py -v
```
Verify: gold tables exist; shares sum to ≤1.05; no leakage; rookies have features.

**Step 6: Scoring Engine**
```
pytest tests/test_scoring.py -v
```
Verify: all known stat lines produce exact expected fantasy points.

**Step 7: Position Models**
```
python -m ffmodel project --as-of-date 2025-09-01
pytest tests/test_models.py -v
```
Verify: all positions produce projections; per_game × games_active ≈ season_total; P25 < P50 < P75.

**Step 8: Full Pipeline**
```
python -m ffmodel run --as-of-date 2025-09-01
pytest tests/test_overlay.py tests/test_ranking.py tests/test_qa.py tests/test_pipeline.py -v
```
Verify: output files exist in CSV + Parquet; schema.json exists; QA checks pass; run metadata captured.

**Step 9: Output Spot Checks**
Read `combined_rankings.csv` and verify:
- Top 5 QBs are plausible NFL starters
- Top 5 RBs are known bellcow/high-volume backs
- No player has >17 games_active
- No player has negative fantasy points (except possibly fringe players)
- position_rank starts at 1 and is contiguous per position
- overall_rank starts at 1 and is contiguous
- overlay_delta is 0.0 for players with no manual factors

**Step 10: Reproducibility**
```
python -m ffmodel run --as-of-date 2025-09-01
```
Verify: second run with same as_of_date produces identical outputs (same run_id pattern, same config hash, same projection values).

**Step 11: Scoring Config Change**
Modify `configs/scoring.yaml` to change `interception: -1` (from -2).
```
python -m ffmodel run --as-of-date 2025-09-01
```
Verify: QB fantasy points change by exactly `interceptions × 1` per player; no model retraining needed (FR-016).

**Step 12: Backtest**
```
python -m ffmodel backtest --seasons 2023,2024,2025
```
Verify: backtest completes; model MAE ≤ weighted-history baseline MAE for offensive positions; backtest output files exist.

**Step 13: Full Test Suite**
```
pytest tests/ -v --tb=short
```
Verify: all tests pass.

---

## 8. Edge Cases & Known Risks

| Edge Case | Handling | QA Check |
|-----------|----------|----------|
| Player with <1 season of data | Heavier regression toward positional prior; `low_sample` flag | QC-006 |
| Mid-season trade (historical) | Split by team stint when computing shares; use most recent stint for projection | Verify shares don't exceed 1.0 (QC-003) |
| Position change (TE→WR) | Use current roster position; fill missing position-specific features with prior | `position_change` reason code |
| Retired/unsigned free agent | Excluded from projections via roster status filter | Logged exclusion |
| QB competition (two starters) | Both get starter_share_of_dropbacks < 1.0; sum across team QBs ≈ 1.0 | QC-009 |
| DST roster turnover | Recency-weighted team stats + defensive_continuity_score manual overlay | Documented v1 limitation |
| Rookie with no NFL data | Draft-capital bucketed positional priors + manual rookie_readiness_score | Non-null projections required |
| nfl_data_py API changes | Snapshot step wraps all calls; errors produce clear messages | Required source failure → run fails |
| Optional source unavailable | Warn + continue; features fall back to simpler proxies; `missing_source` flag set | QC-006 |
| DST points-allowed nonlinearity | Monte Carlo expected bracket value (not naive plug-in of mean) | QC-010 |
| Very low volume player | May produce near-zero projections; filtered from rankings below a minimum threshold | Range check in QC-004 |
| Manual factor stacking (5+ factors) | Total effect capped at ±25% regardless of factor count | `manual_heavy` flag if >10% total effect |

---

## 9. Open Items (resolve before production release)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| OI-001 | Bench spots | **Resolved: 6 BN + 1 IR** | Confirmed from Yahoo league export screenshot |
| OI-002 | Exact Yahoo scoring settings | **Resolved: all values verified** | Confirmed from Yahoo scoring screenshot; only non-default is INT at -2 (Yahoo default: -1) |
| OI-003 | Draft-date freeze point | **Resolved: Sep 1, keep configurable** | Yahoo draft is Mon Sep 1 9pm EDT; as_of_date is a runtime parameter, default to draft day |
| OI-004 | Ranking objective default | **Default to median (P50)** | Configurable via ranking.yaml |
| OI-005 | nfl_data_py exact function names | **Verify during Phase 2** | API may have changed; check current docs |
| OI-006 | Historical residual distribution shape | **Assess during Phase 7** | If residuals are heavily skewed, bootstrap may need adjustment |
