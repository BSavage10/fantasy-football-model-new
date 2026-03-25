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
| Gold (features) | `data/gold/{as_of_date}/` | `ffmodel/features/*.py` | Parquet |
| Outputs | `outputs/{run_id}/` | `ffmodel/export/writer.py` | Parquet + CSV + JSON |

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

## Gold Table Schemas

Canonical column definitions for each gold table are defined as `COLUMNS` lists at the top of their respective modules:

| Table | Module | Grain |
|-------|--------|-------|
| `team_context_features.parquet` | `ffmodel/features/team_context.py` | 1 row per team (target season) |
| `player_role_features.parquet` | `ffmodel/features/player_role.py` | 1 row per player (target season) |
| `player_efficiency_features.parquet` | `ffmodel/features/efficiency.py` | 1 row per player (target season) |
| `availability_features.parquet` | `ffmodel/features/availability.py` | 1 row per player (target season) |
| `manual_factor_features.parquet` | `ffmodel/features/manual_factors.py` | 1 row per entity-factor |

## Scoring Engine

Fantasy point scoring is implemented in `ffmodel/scoring/engine.py` as four pure, stateless functions:

| Function | Inputs | Output |
|----------|--------|--------|
| `score_player(stats, position, config)` | Stats dict (pass_yd, pass_td, interceptions, rush_yd, rush_td, receptions, rec_yd, rec_td, fumbles_lost, return_td, two_pt_conv, off_fumble_return_td) | `float` fantasy points |
| `score_dst(stats, pa_per_game, games, config)` | Stats dict (sacks, interceptions, fumble_recoveries, dst_td, safeties, block_kicks, return_tds, extra_point_returns) + pa/game + games played | `float` fantasy points |
| `score_kicker(stats, config)` | Stats dict (pat_made, fg_0_19, fg_20_29, fg_30_39, fg_40_49, fg_50_plus) | `float` fantasy points |
| `expected_pa_bracket_value(mean_pa, std_pa, brackets, n_samples)` | Mean and std of PA/game + bracket definitions | Expected `float` pts/game from bracket |

Scoring config lives in `configs/scoring.yaml`. All stat-to-point conversions are config-driven (FR-004).

## Position Model Schemas

Projection output is a `StatProjection` dataclass defined in `ffmodel/models/base.py`:

| Field | Type | Description |
|-------|------|-------------|
| `per_game` | `dict[str, float]` | Per-game stat projections (keys vary by position) |
| `season_total` | `dict[str, float]` | `per_game × games_active` |
| `games_active` | `float` | Projected games played |
| `position` | `str` | QB, RB, WR, TE, DEF, K |
| `player_id` | `str` | `canonical_player_id` for offense; team abbr for DST/K |
| `reason_codes` | `list[str]` | e.g., "rookie_prior_used", "team_changer_blend", "mobile_qb" |
| `is_rookie` / `is_team_changer` | `bool` | Player situation flags |

Per-game stat keys by position:

| Position | Stats |
|----------|-------|
| QB | pass_att, pass_cmp, pass_yd, pass_td, interceptions, rush_att, rush_yd, rush_td, fumbles_lost |
| RB | rush_att, rush_yd, rush_td, targets, receptions, rec_yd, rec_td, fumbles_lost |
| WR/TE | targets, receptions, rec_yd, rec_td, rush_att, rush_yd, rush_td, fumbles_lost |
| DEF | sacks, interceptions, fumble_recoveries, dst_td, safeties, block_kicks, return_tds, extra_point_returns, points_allowed, points_allowed_bracket_value |
| K | pat_made, fg_0_19, fg_20_29, fg_30_39, fg_40_49, fg_50_plus |

## Key Algorithms

| Function | Module | Purpose |
|----------|--------|---------|
| `regress_rate()` | `ffmodel/features/efficiency.py` | Empirical Bayes shrinkage: `(observed × N + prior × k) / (N + k)` |
| `_normalize_shares_within_team()` | `ffmodel/features/player_role.py` | Proportionally scale shares to sum ≤1.0 per team |
| `_bracket_lookup()` | `ffmodel/scoring/engine.py` | Direct lookup of DST points-allowed bracket for a given PA total |
| `expected_pa_bracket_value()` | `ffmodel/scoring/engine.py` | Monte Carlo expected bracket value accounting for PA variance (Jensen's inequality) |
| `compute_secondary_rates()` | `ffmodel/models/base.py` | Recency-weighted rush_td_rate and fumble_rate from player_week_fact |
| `compute_uncertainty()` | `ffmodel/models/uncertainty.py` | Bootstrap P25/P50/P75 via position-specific CV perturbation |
| `dampen_score()` | `ffmodel/overlay/applicator.py` | Dampen low-confidence manual factor toward neutral (0.50) |
| `factor_to_multiplier()` | `ffmodel/overlay/applicator.py` | Convert dampened 0-to-1 score to multiplicative adjustment |
| `combine_multipliers()` | `ffmodel/overlay/applicator.py` | Multiplicatively aggregate factors with ±max_total_effect cap |
| `compute_rankings()` | `ffmodel/ranking/ranker.py` | Sort, assign position/overall rank, compute VOR |
| `run_all_checks()` | `ffmodel/qa/checks.py` | Execute all 12 QA checks (QC-001 through QC-012) |

## Overlay, Ranking & Export

| Component | Module | Key Function |
|-----------|--------|-------------|
| Overlay math | `ffmodel/overlay/applicator.py` | `apply_overlays()` — dampens, converts, combines, caps manual factor adjustments |
| Ranking layer | `ffmodel/ranking/ranker.py` | `compute_rankings()` — sorts, assigns ranks, computes VOR |
| QA checks | `ffmodel/qa/checks.py` | `run_all_checks()` — 12 checks (QC-001 through QC-012) |
| Export writer | `ffmodel/export/writer.py` | `write_outputs()` — CSV + Parquet + schema.json + run metadata |
| Pipeline orchestrator | `ffmodel/pipeline.py` | `run_pipeline()` — end-to-end with idempotent caching |

Output schema is defined in `ffmodel/export/writer.py:OUTPUT_SCHEMA` and written to `schema.json` in each run.

Run metadata is captured in `projection_run_fact.parquet` with: run_id, as_of_date, config_hash, git_sha, timestamp, total_players_ranked.

## Manual Factors

Manual overlay inputs are stored in `manual/manual_factors.csv`. Required columns: `entity_id`, `entity_type`, `factor_name`, `score_raw` (0–1), `confidence`, `owner`, `rationale`. Optional: `expires_at`. Validation happens at load time in `ffmodel/features/manual_factors.py`.

## Tests

| Test File | Covers | Count |
|-----------|--------|-------|
| `tests/test_config.py` | Config loading, validation, frozen enforcement, hash determinism | 20 |
| `tests/test_transform.py` | All 5 silver table transforms — uniqueness, schemas, types, normalization | 30 |
| `tests/test_features.py` | All 5 feature modules — share sums, leakage prevention, regress_rate math, rookies, team changers, availability, manual factor validation | 36 |
| `tests/test_scoring.py` | All 4 scoring functions — QB exact total, RB half-PPR, WR cross-position, kicker, DST component+bracket, reconciliation, config change sensitivity | 28 |
| `tests/test_models.py` | All 6 position projectors, baselines, uncertainty — required stats per position, season_total consistency, rookies, team changers, P25≤P50≤P75, orchestrator | 33 |
| `tests/test_overlay.py` | Overlay applicator — dampening, multiplier math, combine caps, integration with overlays enabled/disabled | 20 |
| `tests/test_ranking.py` | Ranking layer — ranking order, position ranks, VOR, upside objective, rookie/team changer flags, replacement levels | 12 |
| `tests/test_qa.py` | QA checks — all 12 QC checks with pass/fail scenarios | 22 |
| `tests/test_pipeline.py` | Pipeline & export — run_id format, file creation, schema.json, run metadata, CLI parsing | 14 |

## Design Document

The implementation plan lives at `docs/implementation-plan.md`. It defines the phase breakdown, data model contracts, algorithm specifications, and exit criteria.

## Requirements

The original requirements specification is at `docs/requirements.md` (887 lines). It covers league settings, scoring rules, feature requirements (FR-001 through FR-025), QA checks (QC-001 through QC-012), and success criteria (SC-001 through SC-006).
