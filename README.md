# ffmodel — Fantasy Football Projection System

A preseason season-long fantasy football projection system for the 2026 NFL season. Projects underlying football statistics first, then translates them into fantasy points via a config-driven scoring engine. Designed for a 10-team, 2-QB, half-PPR Yahoo league.

## Overview

ffmodel forecasts the football events that create fantasy points — team environment, player role, efficiency, and availability — rather than predicting fantasy points directly. Rankings are a downstream product of projections, never hard-coded into the stat model.

**Positions supported:** QB, RB, WR, TE, DST, K

**Key outputs:**
- Per-player projected component stats (pass yards, rush attempts, targets, etc.)
- Fantasy point projections with P25 / P50 / P75 uncertainty bands
- Position ranks, overall ranks, and value-over-replacement (VOR)
- Model-only and model-plus-overlay comparison for transparency

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

```bash
make install
# or
uv sync
```

### Run the Full Pipeline

```bash
# Full end-to-end: ingest -> transform -> features -> project -> rank -> export
uv run python -m ffmodel run --as-of-date 2025-09-01
```

The `--as-of-date` parameter controls the point-in-time snapshot. Set it to your league's draft date or the NFL season opener. Running with the same date is idempotent — previously completed steps are skipped.

### Run Individual Steps

```bash
uv run python -m ffmodel ingest    --as-of-date 2025-09-01   # Extract NFL data
uv run python -m ffmodel transform --as-of-date 2025-09-01   # Normalize into canonical tables
uv run python -m ffmodel features  --as-of-date 2025-09-01   # Build model-ready features
uv run python -m ffmodel project   --as-of-date 2025-09-01   # Generate stat projections
uv run python -m ffmodel rank      --as-of-date 2025-09-01   # Overlay + rank + export
```

### Run the Backtest

```bash
uv run python -m ffmodel backtest --seasons 2023,2024,2025
```

### Run Tests

```bash
make test
# or
uv run pytest tests/ -v

# Single test
uv run pytest tests/test_config.py::TestScoringConfig::test_loads_offense -v
```

## Architecture

### Data Pipeline

The system follows a medallion architecture with four layers:

```
Bronze (raw)    -> data/raw/{as_of_date}/      Immutable nfl_data_py extracts + manifest
Silver (canon)  -> data/silver/{as_of_date}/    5 normalized Parquet tables
Gold (features) -> data/gold/{as_of_date}/      5 model-ready feature tables
Outputs         -> outputs/{run_id}/            Rankings (CSV + Parquet) + run metadata
```

### Modeling DAG

For each player, projections flow through a layered dependency graph:

```
Team Context (weighted avg of team history)
    |
    +-> Player Role (player share x team volume)
    |       |
    |       +-> Efficiency (regressed rates x volume = per-game stats)
    |               |
    |               +-> Availability (games_active projection)
    |                       |
    |                       +-> Season Totals = per_game x games_active
    |                               |
    |                               +-> Scoring Engine(stats) -> fantasy_points
    |                                       |
    |                                       +-> Manual Overlay -> Ranking -> Export
```

### Silver Tables

| Table | Key | Description |
|-------|-----|-------------|
| `player_dim` | `gsis_id` | One row per player. Canonical IDs, position, draft metadata |
| `team_dim` | `team_abbr_season` | One row per franchise-season. Normalized abbreviations |
| `schedule_fact` | `game_id` | One row per game. Spread/total lines, scores |
| `player_week_fact` | `(gsis_id, season, week, team)` | Player counting stats per week |
| `team_week_fact` | `(team, season, week)` | PBP-derived team aggregates (plays, pass rate, EPA, red zone) |

### Gold Tables (Features)

| Table | Grain | Description |
|-------|-------|-------------|
| `team_context_features` | 1 row/team | Recency-weighted team environment (plays, targets, pass rate, red zone) |
| `player_role_features` | 1 row/player | Share-based roles (rush_share, target_share, starter_share) |
| `player_efficiency_features` | 1 row/player | Regressed efficiency rates (YPA, comp%, TD%, catch_rate) |
| `availability_features` | 1 row/player | Games-active projection with age discounts |
| `manual_factor_features` | 1 row/entity-factor | Validated manual overlay inputs |

### Position Models

Six position-specific projectors, each following the team context -> role -> efficiency -> availability pattern:

| Position | Key Projection Logic |
|----------|---------------------|
| **QB** | team_targets x starter_share x efficiency rates |
| **RB** | team_rushes x rush_share + team_targets x target_share |
| **WR** | team_targets x target_share + optional rushing component |
| **TE** | team_targets x target_share |
| **DST** | League-avg counting stats x defensive quality factor + PA bracket |
| **K** | League-avg FG/XP x team scoring factor |

### Key Algorithms

- **Recency-weighted projection:** Per-game rates from prior seasons weighted 50/30/20 (configurable)
- **Empirical Bayes shrinkage:** `regressed = (observed x N + prior x k) / (N + k)` for noisy rates (TD%, INT%, YPC)
- **Rookie priors:** Draft-capital bucketed positional medians anchored to the new team's context
- **Team changer blending:** 70% player history / 30% positional prior (configurable)
- **Uncertainty:** Bootstrap P25/P50/P75 via position-specific CV perturbation of per-game stats and games_active
- **Manual overlays:** Post-model multiplicative adjustment, dampened by confidence, capped at +/-25% total effect
- **DST points-allowed:** Monte Carlo expected bracket value to handle Jensen's inequality from nonlinear scoring

## Configuration

All behavior is driven by five YAML config files in `configs/`:

| File | Purpose |
|------|---------|
| `scoring.yaml` | Fantasy point values per stat event (offense, kicker, DST brackets) |
| `league.yaml` | League size (10), roster slots (2-QB), half-PPR, flex eligibility |
| `model.yaml` | Recency weights, shrinkage settings, regression samples, overlay caps, uncertainty params |
| `ranking.yaml` | Ranking objective (P50 or P75), VOR method, replacement levels by position |
| `sources.yaml` | Which nfl_data_py sources to pull, season range, fallback behavior |

Changes to scoring or ranking config do not require re-running the stat model — just re-run the `rank` step.

A SHA-256 hash over all config file bytes is included in every run's metadata for reproducibility.

## League Settings

Configured for Yahoo Fantasy League "STOP!" (ID: 1221676):

| Setting | Value |
|---------|-------|
| Teams | 10 |
| Scoring | Half-PPR, Head-to-Head |
| Roster | QB, QB, WR, WR, RB, RB, TE, W/R/T, K, DEF, 6xBN, IR |
| Interception penalty | -2 (custom; Yahoo default is -1) |
| FG 40-49 | 4 pts |
| FG 50+ | 5 pts |
| Draft | Live standard, Mon Sep 1 2026, 60s picks |

## Manual Factors

Qualitative inputs (coaching quality, injury recovery confidence, scheme fit) are stored as CSV in `manual/manual_factors.csv` with governance rules:

- Each factor requires `owner`, `rationale`, and `confidence` (0-1)
- `score_raw` is 0.0 to 1.0 (0.5 = neutral)
- Low-confidence factors (<0.30) are dampened toward neutral
- Factors expire after their `expires_at` date
- The delta between model-only and overlay-adjusted output is always published

See the [Runbook](docs/runbook.md) for instructions on editing manual factors.

## Outputs

Each pipeline run produces outputs in `outputs/{run_id}/`:

```
outputs/{run_id}/
  rankings/
    combined_rankings.csv      # All positions ranked with VOR
    player_projection.csv      # Offensive player stat projections
    player_projection.parquet
    dst_projection.csv         # DST projections
    dst_projection.parquet
    kicker_projection.csv      # Kicker projections
    kicker_projection.parquet
    schema.json                # Output field definitions
  projections/
    projection_run_fact.parquet  # Run metadata (run_id, config_hash, git SHA, timestamp)
```

The run ID format is `{as_of_date}_{YYYYMMDD_HHMMSS}_{config_hash[:8]}`.

## Backtest & Evaluation

The rolling-origin backtest framework evaluates model accuracy by holding out each season and training only on prior data:

```bash
uv run python -m ffmodel backtest --seasons 2023,2024,2025
```

**Metrics computed:**
- MAE and RMSE (fantasy point error by position)
- Spearman rank correlation
- Top-N hit rate (QB top-20, RB top-20, WR top-30, TE top-10)
- P25/P75 calibration coverage

**Baselines compared against:**
- Weighted historical average
- Last-year fantasy points

Manual factors are excluded from backtest headline numbers since they cannot be reconstructed historically. DST and kicker are excluded from headline evaluation — the model's measurable value-add is in offensive player projections.

**Backtest outputs** in `outputs/backtest/`:
- `backtest_results.parquet` — per-player per-season detail
- `backtest_summary.csv` — metrics by position and season
- `baseline_comparison.csv` — model vs. baselines

## Quality Assurance

12 automated QA checks run as part of the pipeline (warn but don't block):

| Check | Description |
|-------|-------------|
| QC-001 | No duplicate keys in any output table |
| QC-002 | Canonical player IDs resolve for all players |
| QC-003 | Team-level shares sum within tolerance |
| QC-004 | Stats within plausible ranges |
| QC-005 | Fantasy points reconcile to component stats x scoring weights |
| QC-006 | Critical features below missingness thresholds |
| QC-007 | No target-season data leakage |
| QC-008 | Every manual factor has owner/rationale/timestamp |
| QC-009 | Player opportunities don't exceed team totals |
| QC-010 | DST points-allowed bracket logic matches config |
| QC-011 | Kicker FG bucket totals match config |
| QC-012 | Output schemas match versioned contract |

## Testing

248 tests covering all pipeline layers. All tests use synthetic Parquet fixtures in temp directories — no network calls, fully deterministic.

```
tests/
  test_config.py      # 20 tests — config loading, validation, frozen enforcement, hash determinism
  test_transform.py   # 30 tests — silver table uniqueness, schemas, types, normalization
  test_features.py    # 36 tests — share sums, leakage, regress_rate, rookies, team changers
  test_scoring.py     # 28 tests — exact point totals, cross-position credit, config sensitivity
  test_models.py      # 33 tests — all 6 projectors, baselines, uncertainty, orchestrator
  test_overlay.py     # 20 tests — dampening, multiplier math, combination caps
  test_ranking.py     # 12 tests — rank ordering, VOR, upside objective
  test_qa.py          # 22 tests — all 12 QC checks pass/fail scenarios
  test_pipeline.py    # 14 tests — run_id format, file creation, schema, metadata
  test_backtest.py    # 33 tests — actuals, Spearman, top-N, calibration, leakage prevention
```

## Project Structure

```
ffmodel/
  __init__.py
  __main__.py
  cli.py                    # argparse CLI with 7 subcommands
  config.py                 # YAML -> frozen dataclasses, config hash
  pipeline.py               # End-to-end orchestrator with idempotent caching
  backtest.py               # Rolling-origin backtest runner
  ingest/
    snapshot.py             # nfl_data_py extraction with registry pattern
  transform/
    player_dim.py           # Player dimension table
    team_dim.py             # Team normalization + normalize_team_abbr()
    schedule.py             # Schedule fact table
    player_week.py          # Player-week counting stats
    team_week.py            # PBP-derived team aggregates
  features/
    team_context.py         # Recency-weighted team environment
    player_role.py          # Share-based role features
    efficiency.py           # Regressed efficiency rates + regress_rate()
    availability.py         # Games-active projection with age discounts
    manual_factors.py       # CSV loading + validation
  models/
    base.py                 # StatProjection dataclass, shared utilities
    qb.py / rb.py / wr.py / te.py / dst.py / kicker.py
    baselines.py            # Weighted-history and last-year challengers
    uncertainty.py          # Bootstrap P25/P50/P75
  scoring/
    engine.py               # Pure stateless scoring functions
  overlay/
    applicator.py           # Manual factor dampening + multiplicative adjustment
  ranking/
    ranker.py               # Sort, assign ranks, compute VOR
  qa/
    checks.py               # 12 QA checks (QC-001 through QC-012)
  export/
    writer.py               # CSV + Parquet + schema.json output
configs/
  scoring.yaml / league.yaml / model.yaml / ranking.yaml / sources.yaml
manual/
  manual_factors.csv        # Qualitative overlay inputs
tests/
  conftest.py               # Shared fixtures
  test_config.py / test_transform.py / test_features.py / test_scoring.py
  test_models.py / test_overlay.py / test_ranking.py / test_qa.py
  test_pipeline.py / test_backtest.py
docs/
  requirements.md           # Original specification (FR-001 through FR-025)
  implementation-plan.md    # Design document and phase breakdown
  runbook.md                # Operational guide
  decisions.md              # Implementation choice rationale
  decision_log.md           # Expanded decision log by phase
  changelog.md              # What was built, by phase
  dependencies.md           # How components connect
  sources_of_truth.md       # Where authoritative info lives
```

## Dependencies

| Package | Purpose |
|---------|---------|
| nfl_data_py | NFL data extraction (nflverse ecosystem) |
| pandas >= 2.0 | Data manipulation |
| pyarrow >= 14.0 | Parquet I/O |
| numpy >= 1.24 | Numerical operations |
| scipy >= 1.11 | Spearman correlation in backtest |
| pyyaml >= 6.0 | Config file loading |
| pytest >= 7.0 | Testing (dev) |

No scikit-learn, no XGBoost, no heavy ML frameworks. The entire modeling layer uses numpy/scipy/pandas.

## Common Operations

### Force re-download of NFL data
```bash
rm data/raw/YYYY-MM-DD/_manifest.json
uv run python -m ffmodel run --as-of-date YYYY-MM-DD
```

### Re-score with different league settings
Edit `configs/scoring.yaml`, then:
```bash
uv run python -m ffmodel rank --as-of-date YYYY-MM-DD
```

### Add a manual overlay factor
Edit `manual/manual_factors.csv`, then:
```bash
uv run python -m ffmodel features --as-of-date YYYY-MM-DD
uv run python -m ffmodel rank --as-of-date YYYY-MM-DD
```

### Clean all generated data
```bash
make clean
```

## Documentation

| Document | Description |
|----------|-------------|
| [Requirements](docs/requirements.md) | Full specification — league settings, feature requirements, QA checks, success criteria |
| [Implementation Plan](docs/implementation-plan.md) | Design document — architecture decisions, file manifest, phase breakdown |
| [Runbook](docs/runbook.md) | Operational guide — data refresh, reruns, manual factors, release checklist |
| [Decisions](docs/decisions.md) | Why specific implementation choices were made |
| [Decision Log](docs/decision_log.md) | Expanded decision log organized by phase |
| [Changelog](docs/changelog.md) | What was built, organized by implementation phase |
| [Dependencies](docs/dependencies.md) | Pipeline flow, module relationships, data dependencies |
| [Sources of Truth](docs/sources_of_truth.md) | Where authoritative information lives for each system area |

## Design Principles

1. **Stats first, points second.** Project underlying football events, then convert to fantasy points via config.
2. **Opportunity over efficiency.** Role and volume are more projectable than per-play efficiency.
3. **Separate concerns.** Team environment, player role, efficiency, and availability are distinct problems.
4. **Explicit over hidden.** Manual factors are auditable with owner, rationale, and confidence. No silent hand-tuning.
5. **Reproducible from an as-of date.** Same inputs + same config = same outputs. Every run is traceable via config hash and git SHA.
6. **Rankings are downstream.** The scoring/ranking layer can be re-run under different league settings without retraining the stat model.

## License

Private project. Not for redistribution.
