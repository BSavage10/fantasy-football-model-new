# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

2026 preseason fantasy football projection system. Pure Python data pipeline — **not a HubSpot project**. Extracts NFL data via `nfl_data_py`, normalizes into canonical tables, and will produce fantasy projections/rankings.

Python 3.11+, managed with `uv`. No linter/formatter configured.

## Commands

```bash
make install          # uv sync
make test             # uv run pytest tests/ -v
make clean            # rm generated data + __pycache__

# Single test
uv run pytest tests/test_config.py::TestScoringConfig::test_loads_offense -v

# Pipeline steps (require --as-of-date YYYY-MM-DD)
uv run python -m ffmodel ingest --as-of-date 2025-09-01
uv run python -m ffmodel transform --as-of-date 2025-09-01
uv run python -m ffmodel features --as-of-date 2025-09-01
```

## Architecture

### Data Pipeline Layers

```
Bronze (raw)   → data/raw/{as_of_date}/     ← nfl_data_py extracts + _manifest.json
Silver (canon) → data/silver/{as_of_date}/   ← 5 normalized Parquet tables
Gold (features)→ data/gold/{as_of_date}/     ← 5 feature Parquet tables + manual factors
Outputs        → outputs/{run_id}/           ← Phase 6 (planned)
```

Ingest is idempotent: skips re-extraction if `_manifest.json` exists. Delete manifest to force re-pull.

### Silver Tables

| Table | Module | Primary Key |
|-------|--------|-------------|
| `player_dim` | `ffmodel/transform/player_dim.py` | `gsis_id` (canonical player ID) |
| `team_dim` | `ffmodel/transform/team_dim.py` | `{team_abbr}_{season}` |
| `schedule_fact` | `ffmodel/transform/schedule.py` | `game_id` |
| `player_week_fact` | `ffmodel/transform/player_week.py` | (`gsis_id`, `season`, `week`, `team`) |
| `team_week_fact` | `ffmodel/transform/team_week.py` | (`team`, `season`, `week`) |

Each module defines its schema as a `COLUMNS` list at the top of the file.

### Key Patterns

- **Config**: 5 YAML files in `configs/` → frozen dataclasses via `ffmodel/config.py`. `ProjectConfig.config_hash` (SHA-256 over raw YAML bytes) tracks changes. Mutation raises `FrozenInstanceError`.
- **Source extractors**: Registry pattern in `ffmodel/ingest/snapshot.py` — each `@_register("name")` decorated function handles one nfl_data_py source. Add new sources by writing one function.
- **Team normalization**: Single `normalize_team_abbr()` in `team_dim.py`, imported everywhere. Maps: OAK→LV, SD→LAC, STL→LA, WSH→WAS.
- **team_week_fact**: Derived from play-by-play (~40M rows), not weekly stats. Includes neutral pass rate (margin ≤7, Q1–Q3) and red zone drive counts (distinct drives, not plays).

### CLI

Entry point: `ffmodel.cli:main`. Seven subcommands defined; `ingest`, `transform`, and `features` are wired. Others print "not yet implemented". Dispatch table in `cli.py`.

### Gold Tables

| Table | Module | Grain |
|-------|--------|-------|
| `team_context_features` | `ffmodel/features/team_context.py` | 1 row per team (target season) |
| `player_role_features` | `ffmodel/features/player_role.py` | 1 row per player (target season) |
| `player_efficiency_features` | `ffmodel/features/efficiency.py` | 1 row per player (target season) |
| `availability_features` | `ffmodel/features/availability.py` | 1 row per player (target season) |
| `manual_factor_features` | `ffmodel/features/manual_factors.py` | 1 row per entity-factor |

Key functions: `regress_rate()` in `efficiency.py` (empirical Bayes shrinkage), share normalization in `player_role.py` (caps team shares at 1.0).

### Phase Status

Phases 1–3 (foundation, ingest + transform, features) are complete. Phases 4–7 (scoring, models, ranking/export, backtest) are planned. See `docs/implementation-plan.md` for full spec.

## Testing

86 tests (20 config, 30 transform, 36 features). All use synthetic Parquet fixtures in temp directories — no network calls, fully deterministic. Tests live in `tests/`, fixtures built in `conftest.py`.

## Key Docs

- `docs/implementation-plan.md` — phase breakdown, data contracts, algorithm specs (design spec — do not modify after implementation)
- `docs/requirements.md` — original spec (FR-001–FR-025, QC-001–QC-012, SC-001–SC-006)
- `docs/sources_of_truth.md` — where authoritative info lives
- `docs/decisions.md` — why specific implementation choices were made
- `docs/changelog.md` — what was built, organized by phase
- `docs/dependencies.md` — how components connect

## Post-Phase Checklist

After completing any implementation phase (passing all exit criteria), update these files before considering the phase done:

1. **`CLAUDE.md`** — update Architecture, CLI, Phase Status, Testing sections to reflect new modules and counts
2. **`docs/changelog.md`** — add a phase section listing all added/changed files
3. **`docs/decisions.md`** — add entries for non-obvious implementation choices (with "Decision" + "Why" format)
4. **`docs/dependencies.md`** — update pipeline flow, module dependencies, and data dependency tables
5. **`docs/sources_of_truth.md`** — add new table schemas, key algorithms, and update test counts

Do **not** modify `docs/implementation-plan.md` — it is the design contract. Deviations from the plan should be recorded in `docs/decisions.md`.
