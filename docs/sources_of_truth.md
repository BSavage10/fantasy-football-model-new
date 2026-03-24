# Sources of Truth

Where authoritative information lives for each area of the system. Updated as the project evolves.

---

## Configuration

| What | Location | Notes |
|------|----------|-------|
| Fantasy scoring rules | `configs/scoring.yaml` | Verified against Yahoo league export screenshots. Only non-default: INT at -2 |
| League structure | `configs/league.yaml` | 10-team, 2-QB, half-PPR, league ID 1221676 |
| Model parameters | `configs/model.yaml` | Recency weights, regression samples, overlay caps, uncertainty settings |
| Ranking settings | `configs/ranking.yaml` | VOR method, replacement levels, ranking objective |
| Data source list | `configs/sources.yaml` | Which nfl_data_py sources to pull, season range, fallback behavior |

All config values are loaded into frozen dataclasses via `ffmodel/config.py`. The `ProjectConfig.config_hash` (SHA-256 over all YAML files) is the canonical way to detect config changes.

## Data Layers

| Layer | Path Pattern | Authoritative Module | Format |
|-------|-------------|---------------------|--------|
| Bronze (raw) | `data/raw/{as_of_date}/` | `ffmodel/ingest/snapshot.py` | Parquet + `_manifest.json` |
| Silver (canonical) | `data/silver/{as_of_date}/` | `ffmodel/transform/*.py` | Parquet |
| Gold (features) | `data/gold/{as_of_date}/` | `ffmodel/features/*.py` (Phase 3) | Parquet |
| Outputs | `outputs/{run_id}/` | `ffmodel/export/writer.py` (Phase 6) | Parquet + CSV |

## Silver Table Schemas

Canonical column definitions for each silver table are defined as `COLUMNS` lists at the top of their respective modules:

| Table | Module | Primary Key |
|-------|--------|-------------|
| `player_dim.parquet` | `ffmodel/transform/player_dim.py` | `canonical_player_id` (= `gsis_id`) |
| `team_dim.parquet` | `ffmodel/transform/team_dim.py` | `team_key` (= `{team_abbr}_{season}`) |
| `schedule_fact.parquet` | `ffmodel/transform/schedule.py` | `game_id` |
| `player_week_fact.parquet` | `ffmodel/transform/player_week.py` | (`canonical_player_id`, `season`, `week`, `team`) |
| `team_week_fact.parquet` | `ffmodel/transform/team_week.py` | (`team`, `season`, `week`) |

## Team Abbreviation Normalization

The authoritative mapping of historical → current abbreviations lives in `ffmodel/transform/team_dim.py:TEAM_ABBR_MAP`. The `normalize_team_abbr()` function is the single source of truth — all transforms import and use it.

Current mappings: OAK→LV, SD→LAC, STL→LA, WSH→WAS.

## External Data

| Source | Provider | Access | Notes |
|--------|----------|--------|-------|
| All NFL statistical data | nflverse via `nfl_data_py` | Python package, free | 16 registered extractors in `snapshot.py` |
| Player IDs | nflverse `import_players()` | Bundled with nfl_data_py | `gsis_id` is the canonical key |
| PFR cross-reference | nflverse `import_ids()` | Bundled with nfl_data_py | Used for `pfr_id` bridging in `player_dim` |

## Tests

| Test File | Covers | Count |
|-----------|--------|-------|
| `tests/test_config.py` | Config loading, validation, frozen enforcement, hash determinism | 20 |
| `tests/test_transform.py` | All 5 silver table transforms — uniqueness, schemas, types, normalization | 30 |

## Design Document

The implementation plan lives at `~/.claude/plans/merry-doodling-token.md`. It defines the phase breakdown, data model contracts, algorithm specifications, and exit criteria.

## Requirements

The original requirements specification is at `docs/requirements.md` (887 lines). It covers league settings, scoring rules, feature requirements (FR-001 through FR-025), QA checks (QC-001 through QC-012), and success criteria (SC-001 through SC-006).
