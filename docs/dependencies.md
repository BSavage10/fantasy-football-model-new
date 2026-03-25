# Dependencies & Relationships

How the system's components connect. Updated as the project evolves.

---

## Package Dependencies

```
nfl_data_py ──→ snapshot.py (data extraction)
pandas ────────→ all transform & feature modules
pyarrow ───────→ Parquet I/O throughout
numpy ─────────→ team_week.py, team_context.py, player_role.py, efficiency.py, scoring/engine.py, models/uncertainty.py
scipy ─────────→ backtest.py (Spearman rank correlation)
pyyaml ────────→ config.py (config loading)
```

## Pipeline Flow

```
CLI (cli.py)
  │
  ├─ ingest ──→ snapshot.py ──→ data/raw/{as_of_date}/*.parquet
  │                               + _manifest.json
  │
  ├─ transform ──→ player_dim.py ───→ data/silver/{as_of_date}/player_dim.parquet
  │                team_dim.py ─────→ data/silver/{as_of_date}/team_dim.parquet
  │                schedule.py ─────→ data/silver/{as_of_date}/schedule_fact.parquet
  │                player_week.py ──→ data/silver/{as_of_date}/player_week_fact.parquet
  │                team_week.py ────→ data/silver/{as_of_date}/team_week_fact.parquet
  │
  ├─ features ──→ team_context.py ────→ data/gold/{as_of_date}/team_context_features.parquet
  │               player_role.py ────→ data/gold/{as_of_date}/player_role_features.parquet
  │               efficiency.py ─────→ data/gold/{as_of_date}/player_efficiency_features.parquet
  │               availability.py ───→ data/gold/{as_of_date}/availability_features.parquet
  │               manual_factors.py ─→ data/gold/{as_of_date}/manual_factor_features.parquet
  ├─ score    ──→ scoring/engine.py (stateless; no file I/O)
  │
  ├─ project ──→ models/qb.py ──────→ outputs/projections_{as_of_date}/projections.parquet
  │              models/rb.py
  │              models/wr.py
  │              models/te.py
  │              models/dst.py
  │              models/kicker.py
  │              models/uncertainty.py → outputs/projections_{as_of_date}/uncertainty.parquet
  │
  ├─ rank    ──→ overlay/applicator.py ──→ ranking/ranker.py ──→ export/writer.py
  │              qa/checks.py            outputs/{run_id}/rankings/
  │
  ├─ run     ──→ pipeline.py (orchestrates all above steps end-to-end)
  │              outputs/{run_id}/rankings/ + projections/
  │
  └─ backtest ──→ backtest.py ──→ outputs/backtest/
                    │               ├─ backtest_results.parquet
                    │               ├─ backtest_summary.csv
                    │               └─ baseline_comparison.csv
                    │
                    ├─ features/*.build_*()  (reused for each holdout season)
                    ├─ models/run_projections()
                    ├─ models/baselines.py
                    ├─ scoring/engine.py
                    └─ silver data (player_week_fact, team_week_fact, player_dim)
```

## Module Dependencies

### Ingest Layer

```
config.py (SourcesConfig)
    │
    └──→ snapshot.py
             │
             └──→ nfl_data_py (16 registered extractors)
```

`snapshot.py` depends only on `SourcesConfig` and `nfl_data_py`. It has no dependency on any transform module.

### Transform Layer

```
team_dim.py ─── normalize_team_abbr() ──→ schedule.py
                                     ──→ player_week.py
                                     ──→ team_week.py

player_dim.py (standalone — reads players.parquet, optionally rosters.parquet)
```

Key relationship: `team_dim.py` exports `normalize_team_abbr()` which is imported by `schedule.py`, `player_week.py`, and `team_week.py`. This keeps abbreviation normalization in one place.

Transform execution order in `cli.py`:
1. `player_dim` — no transform dependencies
2. `team_dim` — no transform dependencies
3. `schedule` — imports from `team_dim`
4. `player_week` — imports from `team_dim`
5. `team_week` — imports from `team_dim`

Steps 1–2 could run in parallel; steps 3–5 could run in parallel (they only depend on `team_dim` being importable, not its output file).

### Raw → Silver Data Dependencies

| Silver Table | Required Raw Sources | Optional Raw Sources |
|-------------|---------------------|---------------------|
| `player_dim` | `players.parquet` | `rosters.parquet` (for `entry_year` fallback), IDs table (for `pfr_id` bridging) |
| `team_dim` | — | `schedules.parquet`, `rosters.parquet` (for team enumeration; falls back to hardcoded 32 teams) |
| `schedule_fact` | `schedules.parquet` | — |
| `player_week_fact` | `weekly_stats.parquet` | — |
| `team_week_fact` | `pbp.parquet` | `schedules.parquet` (for points scored/allowed) |

### Feature Layer

```
Silver tables ──→ Feature modules
                    │
                    ├─ team_context.py:  team_week_fact
                    ├─ player_role.py:   player_week_fact + team_week_fact + player_dim
                    ├─ efficiency.py:    player_week_fact
                    ├─ availability.py:  player_week_fact + player_dim
                    └─ manual_factors.py: manual/manual_factors.csv
```

Feature execution order in `cli.py`:
1. `team_context` — reads team_week_fact
2. `player_role` — reads player_week_fact + team_week_fact + player_dim
3. `efficiency` — reads player_week_fact
4. `availability` — reads player_week_fact + player_dim
5. `manual_factors` — reads manual/manual_factors.csv

Steps 1–5 are independent (each reads only from silver); they could run in parallel.

### Silver → Gold Data Dependencies

| Gold Table | Silver Sources | Config Sources |
|-----------|---------------|---------------|
| `team_context_features` | `team_week_fact` | `ModelConfig.recency_weights` |
| `player_role_features` | `player_week_fact`, `team_week_fact`, `player_dim` | `ModelConfig.recency_weights`, `ModelConfig.team_changer` |
| `player_efficiency_features` | `player_week_fact` | `ModelConfig.recency_weights`, `ModelConfig.regression_samples` |
| `availability_features` | `player_week_fact`, `player_dim` | `ModelConfig.recency_weights`, `ModelConfig.games_active` |
| `manual_factor_features` | `manual/manual_factors.csv` | — |

### Scoring Layer (Phase 4 — complete)

```
config.py (ScoringConfig)
    │
    └──→ scoring/engine.py
              │
              ├─ score_player(stats, position, config) → float
              ├─ score_dst(stats, pa_per_game, games, config) → float
              ├─ score_kicker(stats, config) → float
              └─ expected_pa_bracket_value(mean_pa, std_pa, brackets) → float
```

`scoring/engine.py` is a pure functions module. It has no file I/O and no dependencies on pandas or data tables — only `ScoringConfig` (from `config.py`) and `numpy`.

### Model Layer (Phase 5 — complete)

```
Gold features + Silver data ──→ Position models
                                   │
                                   ├─ base.py (StatProjection, compute_secondary_rates, league avg constants)
                                   ├─ qb.py:     role_df + team_context + efficiency + availability + secondary_rates
                                   ├─ rb.py:     role_df + team_context + efficiency + availability + secondary_rates
                                   ├─ wr.py:     role_df + team_context + efficiency + availability + secondary_rates
                                   ├─ te.py:     role_df + team_context + efficiency + availability + secondary_rates
                                   ├─ dst.py:    team_context + team_week_fact + scoring_config + model_config
                                   ├─ kicker.py: team_context + team_week_fact + model_config
                                   ├─ baselines.py: player_week_fact + scoring_config
                                   └─ uncertainty.py: projections + scoring_config → P25/P50/P75
```

`__init__.py` contains `run_projections()` which orchestrates all six projectors and `projections_to_dataframe()` for serialization.

### Overlay, Ranking, QA & Export Layer (Phase 6 — complete)

```
Projections + Uncertainty ──→ overlay/applicator.py
                                 │  (manual_factor_features + OverlayConfig)
                                 │
                                 └──→ ranking/ranker.py
                                         │  (RankingConfig — objective, replacement levels)
                                         │
                                         ├──→ qa/checks.py (12 QA checks)
                                         │
                                         └──→ export/writer.py
                                                  │
                                                  └──→ outputs/{run_id}/
                                                         ├─ rankings/ (CSV + Parquet + schema.json)
                                                         └─ projections/ (projection_run_fact.parquet)
```

`pipeline.py` orchestrates the full end-to-end flow (ingest → transform → features → project → overlay → rank → QA → export) with idempotent caching.

### Backtest Layer (Phase 7 — complete)

```
Silver data + Config ──→ backtest.py
                            │
                            ├─ features/*.build_*() (per holdout season, data filtered to seasons < holdout)
                            ├─ models/run_projections() + compute_all_uncertainty()
                            ├─ scoring/engine.score_player() (compute actuals)
                            ├─ models/baselines.py (weighted_history, last_year)
                            └─ scipy.stats.spearmanr (rank correlation)
                            │
                            └──→ outputs/backtest/
                                   ├─ backtest_results.parquet
                                   ├─ backtest_summary.csv
                                   └─ baseline_comparison.csv
```

## Config → Module Relationships

| Config | Consumed By |
|--------|------------|
| `ScoringConfig` | `scoring/engine.py`, `models/uncertainty.py`, `models/baselines.py`, `models/dst.py`, `qa/checks.py`, `backtest.py` |
| `LeagueConfig` | (future: roster-count-based replacement levels) |
| `ModelConfig` | `features/*.py`, `models/dst.py`, `models/kicker.py`, `overlay/applicator.py` (OverlayConfig) |
| `RankingConfig` | `ranking/ranker.py` |
| `SourcesConfig` | `ingest/snapshot.py` |

## Test Dependencies

| Test File | Fixtures From | Modules Under Test |
|-----------|---------------|-------------------|
| `test_config.py` | `conftest.py` (`configs_dir`) | `config.py` |
| `test_transform.py` | Own `raw_dir` fixture (synthetic Parquet) | All 5 transform modules |
| `test_features.py` | Own fixtures (synthetic DataFrames) | All 5 feature modules + `regress_rate()` |
| `test_scoring.py` | `conftest.py` (`configs_dir`) | `scoring/engine.py` — all 4 scoring functions |
| `test_models.py` | Own fixtures (gold-layer DFs + silver-layer DFs) + `conftest.py` (`configs_dir`) | All 10 model modules — 6 projectors, baselines, uncertainty, base utils, orchestrator |
| `test_overlay.py` | Own fixtures (synthetic DFs + OverlayConfig) | `overlay/applicator.py` — dampening, multiplier math, combination caps, integration |
| `test_ranking.py` | Own fixtures (OverlayResults + DFs + RankingConfig) | `ranking/ranker.py` — ranking order, position ranks, VOR, upside objective |
| `test_qa.py` | Own fixtures (synthetic DFs + ScoringConfig) | `qa/checks.py` — all 12 QC checks pass/fail scenarios |
| `test_pipeline.py` | Own fixtures (RankedPlayer list) + `tmp_path` | `pipeline.py`, `export/writer.py`, `cli.py` — run_id format, file creation, schema, metadata |
| `test_backtest.py` | Own fixtures (synthetic player/team DFs, pre-built results) + `conftest.py` (`configs_dir`, `project_root`) | `backtest.py` — actuals computation, metrics, summary, comparison, leakage prevention, integration |
