# Dependencies & Relationships

How the system's components connect. Updated as the project evolves.

---

## Package Dependencies

```
nfl_data_py ──→ snapshot.py (data extraction)
pandas ────────→ all transform & feature modules
pyarrow ───────→ Parquet I/O throughout
numpy ─────────→ team_week.py, future models
scipy ─────────→ future models (regression, bootstrap)
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
  ├─ features (Phase 3) ──→ data/gold/{as_of_date}/*.parquet
  ├─ project  (Phase 5) ──→ outputs/{run_id}/projections/
  ├─ rank     (Phase 6) ──→ outputs/{run_id}/rankings/
  └─ backtest (Phase 7) ──→ outputs/backtest/
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

### Future Dependencies (Phases 3–7)

These are planned but not yet built:

```
Silver tables ──→ Feature modules (Phase 3)
                    │
                    ├─ team_context.py:  team_week_fact
                    ├─ player_role.py:   player_week_fact + team_week_fact
                    ├─ efficiency.py:    player_week_fact
                    ├─ availability.py:  player_week_fact + player_dim
                    └─ manual_factors.py: manual/manual_factors.csv

Gold features ──→ Position models (Phase 5)
                    │
                    ├─ Each model reads: team_context + player_role + efficiency + availability
                    └─ All models share: base.py (weighted_mean, regress_rate, StatProjection)

Projections ──→ Scoring engine (Phase 4)
            ──→ Overlay applicator (Phase 6)
            ──→ Ranking layer (Phase 6)
            ──→ QA checks (Phase 6)
            ──→ Export writer (Phase 6)
```

## Config → Module Relationships

| Config | Consumed By |
|--------|------------|
| `ScoringConfig` | `scoring/engine.py` (Phase 4), `models/uncertainty.py` (Phase 5) |
| `LeagueConfig` | `ranking/ranker.py` (Phase 6) |
| `ModelConfig` | `features/*.py` (Phase 3), `models/*.py` (Phase 5), `overlay/applicator.py` (Phase 6) |
| `RankingConfig` | `ranking/ranker.py` (Phase 6) |
| `SourcesConfig` | `ingest/snapshot.py` |

## Test Dependencies

| Test File | Fixtures From | Modules Under Test |
|-----------|---------------|-------------------|
| `test_config.py` | `conftest.py` (`configs_dir`) | `config.py` |
| `test_transform.py` | Own `raw_dir` fixture (synthetic Parquet) | All 5 transform modules |
