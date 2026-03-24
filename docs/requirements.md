# Fantasy Football Points Projection Model

## 2026 Pre-Draft Requirements Specification

**Prepared for:** Savage
**Prepared on:** March 18, 2026
**Updated:** March 19, 2026 (redline revisions incorporated)

This specification prioritizes a thin, reproducible, point-in-time-correct v1 over a maximally rich but historically unreconstructable or operationally fragile system.

This document defines the end-to-end requirements for a season-long preseason fantasy football projection system intended to support 2026 pre-draft rankings for quarterback, running back, wide receiver, tight end, defense/special teams, and kicker. It is written to let a senior engineer implement the system correctly on the first pass, with clear scope, explicit modeling choices, a detailed source register, feature dictionaries, QA rules, and release requirements.

| Scope | Outputs | Design stance |
|-------|---------|---------------|
| 6 position groups | Projected stats | Stats first |
| Preseason season-long model | Fantasy points | Config-driven scoring |
| 2-QB league context | Ranks + uncertainty | Auditable manual overlays |

**Implementation north star:** Build a projection engine that forecasts the underlying football events that create fantasy points, not a brittle direct-points model that overfits last year's finishes. Preserve transparency, keep manual factors explicit, and make every release reproducible from an as-of date.

---

## 1. Document control and how to use this specification

| Field | Value |
|-------|-------|
| Version | 1.1 |
| Status | Architecture draft — implementation-ready after release blockers in Section 12 are resolved |
| Chosen implementation stack | Python |
| Primary objective | Define the data, modeling, evaluation, and operational requirements for a 2026 preseason fantasy football projection system |
| Primary reader | Senior engineer responsible for end-to-end implementation |
| Secondary readers | Data engineer, analyst, and future maintainer |
| Primary output | Season-long preseason projections, uncertainty bands, and pre-draft rankings for QB, RB, WR, TE, DST, and K |
| Key design stance | Project football statistics first, then convert them into configurable fantasy points |
| League context | 2 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE), 1 DST, 1 K; half-PPR; 10-team league; 6 bench spots; custom DST and kicker scoring per user description |

**How to read this document:** Sections 1-13 define the implementation contract. The appendices provide the source register, feature dictionaries, manual-factor rubric, and release requirements that the engineer should treat as the operational reference.

---

## 2. Executive summary

The requested product is a preseason season-long projection system for the 2026 fantasy football draft. The system must support quarterback, running back, wide receiver, tight end, defense/special teams, and kicker.

The correct implementation approach is a layered model that forecasts team environment first, then player role, then player efficiency, then availability, and only after that translates projected underlying statistics into fantasy points.

The ranking layer must remain separate from the projection layer. That matters because league settings can change, scarcity in a 2-QB league is real, and value-over-replacement logic depends on configurable league assumptions such as league size and bench depth.

- Role and opportunity should drive the model before raw efficiency does.
- Team environment, player role, efficiency, and availability are separate problems and should remain separate in the data model.
- Manual qualitative inputs are allowed, but hidden hand-tuning is not.
- Every projection run must be reproducible from an as-of date, versioned data snapshot, and explicit configuration.
- Rankings are a downstream product of projections; do not hard-code rankings logic into the stat model.
- Because this is a 2-QB league, replacement value and scarcity must be configurable in the ranking layer.

---

## 3. Goals, non-goals, and working assumptions

### 3.1 Goals

- Produce preseason season-long median projections for QB, RB, WR, TE, DST, and K.
- Project component football statistics first, then translate them into fantasy points.
- Output both season total points and points per game.
- For v1, support P25 / P50 / P75 outputs or an equivalent simple uncertainty contract.
- Support qualitative 0-to-1 manual inputs such as coaching quality, continuity, scheme fit, role clarity, and injury recovery confidence.
- Create outputs that can drive pre-draft rankings and later value-over-replacement calculations.

### 3.2 Non-goals for v1

- Weekly start/sit recommendations in v1.
- DFS pricing or betting market prediction.
- Real-time injury-news scraping with natural-language parsing in v1.
- A black-box model that cannot explain why a player moved up or down.
- A one-off notebook with no reproducibility, QA, or version control.

### 3.3 Working assumptions

| ID | Assumption |
|----|------------|
| A1 | The initial product is a preseason season-long model, not a weekly in-season optimizer. |
| A2 | Exact DST and kicker settings should be confirmed against the actual Yahoo league export before final production lock. |
| A3 | League size is 10 teams with 6 bench spots. The ranking layer must still be configurable for future flexibility. |
| A4 | The model should support manual 0-to-1 qualitative inputs, but those inputs must remain explicit and auditable. |

### 3.4 V1 scope lock

The following scope tiers govern what must be delivered versus what is optional or deferred.

**Must ship in v1:**
- Offensive projections for QB, RB, WR, and TE
- Config-driven scoring engine
- Separate projection and ranking layers
- Model-only and model-plus-overlay output comparison
- Reproducible rolling preseason backtest
- CSV/Parquet outputs

**Should ship if time allows:**
- DST and kicker projections
- Uncertainty bands (P25/P50/P75)
- Explainability reason codes

**Deferred beyond v1:**
- Full player-level feature attribution
- Weekly simulation layer
- Advanced DST weekly environment modeling
- Fully automated premium-source enrichment
- Any dependency on historically hard-to-reconstruct data

---

## 4. League context and scoring translation requirements

### 4.1 League settings

| Setting | Value |
|---------|-------|
| Platform | Yahoo Fantasy |
| League ID | 1221676 |
| League name | STOP! |
| Teams | 10 |
| Divisions | 2 |
| Scoring type | Head-to-Head |
| Fractional points | Yes |
| Negative points | Yes |
| Roster positions | QB, QB, WR, WR, RB, RB, TE, W/R/T, K, DEF, BN, BN, BN, BN, BN, BN, BN, IR |
| Waiver type | FAB w/ Reverse order of standings tiebreak |
| Playoffs | 6 teams — Weeks 15, 16, and 17 |
| Playoff seeding | All teams seeded according to overall standings |

### 4.2 Scoring rules

Scoring should be treated as configuration, not as hard-coded model logic. The model should project football statistics first and let a scoring engine convert those projections into fantasy points. That keeps the system reusable and makes later scoring changes much cheaper.

**Offense (applies to all offensive positions: QB, RB, WR, TE, W/R/T)**

| Scoring event | Points | Notes |
|--------------|--------|-------|
| Passing yards | 1 point per 25 yards (0.04/yard) | |
| Passing touchdowns | 4 | |
| Interceptions thrown | -2 | Yahoo default is -1; this league doubles the penalty |
| Rushing yards | 1 point per 10 yards (0.10/yard) | |
| Rushing touchdowns | 6 | |
| Receptions | 0.5 | Half-PPR |
| Receiving yards | 1 point per 10 yards (0.10/yard) | |
| Receiving touchdowns | 6 | |
| Return touchdowns | 6 | |
| 2-point conversions | 2 | |
| Fumbles lost | -2 | |
| Offensive fumble return TD | 6 | |

**Kickers**

| Scoring event | Points |
|--------------|--------|
| Field goals 0-19 yards | 3 |
| Field goals 20-29 yards | 3 |
| Field goals 30-39 yards | 3 |
| Field goals 40-49 yards | 4 |
| Field goals 50+ yards | 5 |
| Point after attempt made | 1 |

**Defense / Special Teams**

| Scoring event | Points |
|--------------|--------|
| Sack | 1 |
| Interception | 2 |
| Fumble recovery | 2 |
| Touchdown | 6 |
| Safety | 2 |
| Block kick | 2 |
| Kickoff and punt return touchdowns | 6 |
| Extra point returned | 2 |

| Points allowed | Points |
|---------------|--------|
| 0 points | 10 |
| 1-6 points | 7 |
| 7-13 points | 4 |
| 14-20 points | 1 |
| 21-27 points | 0 |
| 28-34 points | -1 |
| 35+ points | -4 |

---

## 5. High-level solution architecture

The system should be implemented as a data pipeline plus a modeling pipeline. The data pipeline produces canonical historical facts and feature layers. The modeling pipeline projects component statistics, translates them into fantasy points, and then applies ranking logic.

| Step | Layer | Purpose | Typical assets | Notes |
|------|-------|---------|---------------|-------|
| 1 | Bronze / raw | Source snapshots exactly as received | Raw files, snapshots, retrieval metadata | Never overwrite. Keep immutable extracts by as-of date. |
| 2 | Silver / canonical | Normalized football entities and facts | player_dim, team_dim, schedules, pbp, player_week, team_week | Resolve IDs, team abbreviations, seasons, and transaction splits here. |
| 3 | Gold / features | Model-ready datasets | team_context_features, player_role_features, efficiency_features, availability_features, manual_factors | Every feature should be timestamp-safe and traceable. |
| 4 | Model outputs | Projected underlying stats and uncertainty | projection_run, player_projection, dst_projection, kicker_projection | Persist component stats before fantasy-point translation. |
| 5 | Serving / ranking | Fantasy points, ranks, VOR-ready tables | player_fantasy_points, rankings, explanations | Keep scoring and scarcity logic configurable. |

### 5.1 Core entities and tables

| Entity | Grain | Key fields | Notes |
|--------|-------|-----------|-------|
| player_dim | 1 row per player | canonical_player_id, gsis_id, name, position, birth_date, college, draft metadata | Use a stable canonical player key plus bridges to fantasy and source-specific IDs. |
| team_dim | 1 row per franchise-season | team_key, team_abbr, season, historical aliases | Must handle relocation / abbreviation changes cleanly. |
| schedule_fact | 1 row per game | game_id, season, week, home_team, away_team, date, line, total | Used for schedule strength, DST, kicker, and future weekly extensibility. |
| pbp_fact | 1 row per play | game_id, play_id, passer, rusher, receiver, down/distance, EPA, xYAC, etc. | Primary source for usage shares and context derivations. |
| player_week_fact | 1 row per player-week | player_id, season, week, team, pos, stat totals | Useful for season aggregation and rolling windows. |
| team_week_fact | 1 row per team-week | team, season, week, plays, PROE, pace, points, red-zone trips | Team environment anchor. |
| manual_factor_fact | 1 row per entity-factor-as_of_date | entity_id, factor_name, score_raw, score_normalized, confidence, rationale | Auditable human inputs only; no silent spreadsheet edits. |
| projection_run_fact | 1 row per model run | run_id, as_of_date, source_snapshot_ids, code_version, config_hash | Critical for reproducibility and debugging. |

### 5.2 Dependency graph and target derivation rules

The following table defines whether each key output is modeled directly or derived from upstream outputs. Any derived output must reconcile exactly to published fantasy points under the active scoring config. Any player-level opportunity outputs must reconcile to team-level opportunity budgets within tolerance.

| Output field | Modeled directly vs. derived | Upstream inputs | Reconciliation rule |
|-------------|------------------------------|----------------|-------------------|
| team_dropbacks | Modeled directly | Historical team tendencies, pace, PROE | Sum across games must match team total |
| pass_attempts | Derived | team_dropbacks - sacks + starter_share | Player attempts must reconcile to team dropbacks minus sacks |
| pass_yards | Derived | pass_attempts × yards_per_attempt (modeled) | Must reconcile to fantasy points via scoring engine |
| pass_td | Derived | pass_attempts × td_rate (modeled, regressed) | Regressed rate applied to projected attempts |
| interceptions | Derived | pass_attempts × int_rate (modeled, regressed) | Regressed rate applied to projected attempts |
| rush_attempts (QB) | Modeled directly | Historical QB rushing tendencies, designed run rate | Must not exceed plausible team rushing budget |
| rush_attempts (RB) | Derived | team_rushes × rush_share (modeled) | Player shares must sum to ~1.0 within team |
| rush_yards | Derived | rush_attempts × yards_per_carry (modeled, regressed) | Regressed efficiency applied to projected attempts |
| rush_td | Derived | rush_attempts × goal_line_share × td_rate | Sensitive to goal-line usage; regress td_rate |
| targets | Derived | team_targets × target_share (modeled) | Player shares must sum to ~1.0 within team |
| receptions | Derived | targets × catch_rate (modeled) | Must reconcile: receptions ≤ targets |
| receiving_yards | Derived | targets × yards_per_target (modeled) | Alternative: receptions × yards_per_reception |
| receiving_td | Derived | targets × red_zone_share × td_rate | Regress td_rate; sensitive to end-zone usage |
| games_active | Modeled directly | Historical availability, injury context, manual overlay | Season total = games_active × per_game stats |
| season_total_stats | Derived | games_active × per_game_stat | Core decomposition for all positions |
| fantasy_points | Derived | scoring_engine(component_stats) | Must equal sum of component × scoring weight exactly |

---

## 6. Core product requirements

The following functional requirements define what the senior engineer must deliver. These are not suggestions. If a requirement is intentionally deferred, the deferral should be explicit in release notes.

| ID | Requirement | Acceptance criteria |
|----|------------|-------------------|
| FR-001 | The system shall support a configurable as-of date and only use information that would have been available on or before that date. | Running the same as-of date twice yields identical source snapshots, features, and outputs. |
| FR-002 | The system shall produce projections for QB, RB, WR, TE, DST, and K. | Each supported position has a valid output table and rank field. |
| FR-003 | The system shall project football statistics before translating them to fantasy points. | Output includes component stat projections as well as final fantasy-point projections. |
| FR-004 | The scoring engine shall be configuration-driven rather than hard-coded. | A scoring config file can change point rules without changing model code. |
| FR-005 | The scoring engine shall support rare cross-category stats for all offensive positions. | A WR/TE/RB can receive fantasy credit for trick-play passing or rushing as configured. |
| FR-006 | The system shall output both season total fantasy points and projected points per game, defined as projected fantasy points per projected active game. | Final tables include total_points_proj and ppg_proj where ppg_proj = total_points_proj / games_active_proj. |
| FR-007 | The system shall produce P25, P50, and P75 uncertainty outputs for every player and team defense/kicker. | Each output row includes P25, P50, and P75 projections. Method may be bootstrap-, residual-, or simulation-based but must be documented. |
| FR-008 | The system shall treat availability as a separate prediction problem from per-game efficiency or volume. | Games-active or games-played projections are stored separately from per-game stat rates. |
| FR-009 | The system shall support explicit manual overlay factors scored on a 0-to-1 scale, applied as post-model overlays with transparent delta reporting. | A manual factor table exists, is applied after model inference, and the delta between model-only and model-plus-overlay outputs is published. |
| FR-010 | The system shall preserve an audit trail for every manual factor. | Each manual input stores author, timestamp, rationale, and confidence. |
| FR-011 | The system shall support rookies and low-history players via separate prior logic. | Rookies appear in outputs with non-null projections and clear provenance. |
| FR-012 | The system shall support players changing teams, playcallers, or depth-chart environments. | Historical features and current team context are combined without data leakage or null outputs. |
| FR-013 | The system shall include fallback logic when a source is missing or stale. | Missing-source flags and fallback feature paths are persisted for inspection. |
| FR-014 | The system shall output machine-readable projection tables. | At minimum, CSV and Parquet outputs are available for each projection run. |
| FR-015 | The system shall output position ranks, overall ranks, and fields required for later value-over-replacement calculations. | Outputs include position_rank, overall_rank, and configurable replacement metadata. |
| FR-016 | The system shall separate the projection layer from the ranking layer. | Fantasy points can be regenerated under new league settings without retraining the stat model. |
| FR-017 | The system shall store run metadata, source versions, and configuration hashes for every projection run. | A projection_run record can reconstruct how any output row was produced. |
| FR-018 | The system shall emit reason codes and manual adjustment deltas for each run and each player. Full feature attribution is optional unless the model class supports it cleanly. | Each player output includes reason codes explaining major projection drivers and any manual overlay deltas. |
| FR-019 | The system shall calculate DST scoring using component events plus points-allowed logic. DST may use a lighter-weight v1 model if it does not delay offensive model delivery. | DST outputs are not based solely on last-year fantasy points. |
| FR-020 | The system shall calculate kicker scoring using field-goal distance buckets and extra points. K may use a lighter-weight v1 model if it does not delay offensive model delivery. | Kicker outputs contain XP and field-goal bucket components. |
| FR-021 | The system shall include QA flags for suspicious or unstable outputs. | Outputs expose flags such as low_sample, missing_source, manual_heavy, or volatile_touchdown_dependence. |
| FR-022 | The system shall allow configurable recency weighting and shrinkage settings. | Weights can be changed via configuration and are logged with the run. |
| FR-023 | The system shall support both model-only outputs and model-plus-manual-overlay outputs. | An analyst can compare raw model projections versus adjusted projections within the same run. |
| FR-024 | The system shall require final verification of exact Yahoo league settings before production ranking release. | A scoring verification checklist is completed and stored with the release run. |
| FR-025 | The system shall publish output field names, types, nullability, and definitions as part of the output tables. | Output tables include a header or companion schema file documenting every column. |

---

## 7. Non-functional and operational requirements

| ID | Topic | Requirement |
|----|-------|------------|
| NFR-001 | Reproducibility | A full run is reproducible from raw snapshots, code version, and config hash; no hidden spreadsheet edits. |
| NFR-002 | No leakage | No actual target-season post-freeze information may enter training features or evaluation datasets. |
| NFR-003 | Traceability | Every projection row can be traced back to features, manual inputs, source snapshots, and model version. |
| NFR-004 | Config-driven behavior | Scoring, recency weights, manual-factor toggles, and ranking assumptions are externalized in config files. |
| NFR-005 | Idempotent ingestion | Repeated extraction of the same source/as-of-date does not create duplicate canonical records. |
| NFR-006 | Graceful degradation | If a secondary source fails, the run may continue with fallback features while clearly flagging coverage loss. |
| NFR-007 | Data quality enforcement | Runs fail fast on critical integrity errors such as duplicate keys, broken joins, or impossible scoring outputs. |
| NFR-008 | Explainability | The system must expose interpretable feature families, manual adjustments, and reason codes. |
| NFR-009 | Portability | The implementation should run in a reproducible local or containerized environment without proprietary desktop steps. |
| NFR-010 | Reasonable runtime | Incremental preseason reruns should be analyst-friendly; historical full rebuilds should be cached and automated. |
| NFR-011 | Schema stability | Output schemas must be versioned so downstream ranking tools do not silently break. |
| NFR-012 | Test coverage | Core scoring logic, feature transforms, joins, and leakage rules must have automated tests. |
| NFR-013 | Source compliance | Attribution and license requirements from public data sources must be respected in code and documentation. |
| NFR-014 | Manual governance | Manual overlays require ownership, rationale, and optional expiration dates. |
| NFR-015 | Safe defaults | Directionality of normalized manual scores must be consistent; 1.0 should always mean more favorable unless explicitly documented otherwise. |

---

## 8. Modeling design requirements

The system should use separate position families, with shared team-context inputs but position-specific role and efficiency submodels. Do not force a single monolithic model across all positions.

Season totals should generally be decomposed into at least two parts: projected games active and projected per-game production. This prevents injury/availability risk from being hidden inside volume or efficiency estimates.

The engineer should keep challenger baselines alive throughout development. A sophisticated model that does not beat a simple weighted-history or market-prior baseline is not production-ready.

All baselines must remain operational throughout development: weighted-history, last-year points, and market-prior challenger where historically available.

Any feature not reconstructable at the historical preseason freeze point is disallowed from primary backtest evaluation, even if used in live 2026 inference.

### 8.1 Target variables by position

| Position | Projected component stats | Notes |
|----------|--------------------------|-------|
| QB | pass attempts, completions/comp rate, pass yards, pass TD, INT, rush attempts, rush yards, rush TD, fumbles, games active | Fantasy points are downstream of projected passing and rushing components. |
| RB | rush attempts, rush yards, rush TD, targets, receptions, receiving yards, receiving TD, fumbles, games active | Receiving role matters materially and must not be reduced to carries only. |
| WR | targets, receptions, receiving yards, receiving TD, rush attempts, rush yards, rush TD, rare passing stats, fumbles, games active | Air-yards and route usage should inform the target and yardage submodels. |
| TE | targets, receptions, receiving yards, receiving TD, rush attempts if any, rare passing stats, fumbles, games active | Route participation and blocking-vs-route behavior matter more than raw snap share. |
| DST | points allowed distribution, sacks, INT, fumble recoveries, safeties, DST/ST TD | Nonlinear points-allowed scoring should be modeled explicitly, not approximated with last-year fantasy points. |
| K | XP made, FG made 0-39, FG made 40-49, FG made 50+ | Distance buckets are part of the target definition, not an afterthought. |

### 8.1A Position-level modeling DAG

For each position, the model follows a team context → role/opportunity → efficiency → availability → derived stats flow.

**QB:**
1. Team context: team_dropbacks (from pace, PROE, plays)
2. Role: starter_share_of_dropbacks → player pass_attempts; QB rushing role → rush_attempts
3. Efficiency: yards_per_attempt, comp_rate, td_rate (regressed), int_rate (regressed), rush yards_per_carry
4. Availability: games_active projection
5. Derivation: per_game_stats × games_active → season totals → scoring_engine → fantasy points

**RB:**
1. Team context: team_rushes, team_targets, team_run_rate
2. Role: rush_share, target_share, goal_line_share, route_participation
3. Efficiency: yards_per_carry (regressed), yards_per_target, catch_rate, td_rates (regressed)
4. Availability: games_active projection
5. Derivation: per_game_stats × games_active → season totals → scoring_engine → fantasy points

**WR:**
1. Team context: team_dropbacks, team_targets, team pass_rate
2. Role: target_share, air_yards_share, route_participation, end_zone_target_share
3. Efficiency: yards_per_target, catch_rate, td_rate (regressed), YAC
4. Availability: games_active projection
5. Derivation: per_game_stats × games_active → season totals → scoring_engine → fantasy points

**TE:**
1. Team context: team_dropbacks, team_targets, personnel tendencies (12-personnel)
2. Role: route_participation (not snap share), target_share, route_vs_block_rate, end_zone_target_share
3. Efficiency: yards_per_route_run, catch_rate, td_rate (regressed)
4. Availability: games_active projection
5. Derivation: per_game_stats × games_active → season totals → scoring_engine → fantasy points

**DST:**
1. Team context: defensive quality priors, schedule/opponent context
2. Components: projected sacks, INTs, fumble recoveries, safeties (minor), DST TDs (regressed hard)
3. Points allowed: opponent offensive quality → expected points allowed → bucket scoring
4. Derivation: component events + points_allowed_bucket_value → fantasy points

**K:**
1. Team context: projected team points, drives into FG range, red_zone_stall_rate
2. Components: extra_point_volume (from team TDs), FG attempts by distance bucket
3. Efficiency: FG accuracy (minor weight)
4. Derivation: XP + FG_bucket_points → fantasy points

### 8.2 Feature tier philosophy

| Tier | Definition | Examples |
|------|-----------|----------|
| Highest Weight | Stable opportunity, role, and team-context variables that repeatedly explain future workload or fantasy opportunity. | target share, route participation, goal-line share, team plays, team pass rate, QB rush volume |
| Strong Secondary | Useful context or efficiency inputs that add signal but should not dominate without strong evidence. | separation, cushion, CPOE, run-block quality, draft capital, contract commitment, market prior |
| Regress Hard | Noisy or descriptive variables with weak year-to-year stability; use only after shrinkage or as low-weight context. | touchdown spikes, yards per carry spikes, long-play rates, DST touchdowns, raw prior-year fantasy finish |
| Manual Overlay | Human-entered 0-to-1 context scores that remain explicit and auditable. | playcaller quality, role clarity, team-change fit, injury recovery confidence |

### 8.3 Feature-engineering rules

| ID | Rule |
|----|------|
| T-001 | Use prior-season, two-year, and three-year weighted windows where history exists; weights must be configurable, not hard-coded. |
| T-002 | Prefer market-share features (target share, rush share, goal-line share) over raw totals when projecting role. |
| T-003 | Model season totals as games_active_projection × per_game_projection whenever practical. |
| T-004 | Regress low-sample rates such as TD rate, INT rate, YPC spikes, long-play rate, and DST touchdown rate toward appropriate priors. |
| T-005 | For rookies, replace missing NFL history with draft/age/athletic/college priors rather than zero values. |
| T-006 | Store all manual factors in raw and normalized directional form. |
| T-007 | Any feature that depends on actual target-season realized outcomes is disallowed in preseason model training. |
| T-008 | Where a premium source is missing, fall back to a simpler public proxy and raise a coverage flag rather than silently dropping the signal. |
| T-009 | Keep per-team and per-position opportunity budgets internally consistent (for example: target shares should not sum above plausible limits). |
| T-010 | Persist both raw features and transformed features so debugging does not require recomputing from scratch. |

### 8.4 Predictive signal summary

| Feature family | Public takeaway | Model implication |
|---------------|----------------|-------------------|
| WR / TE usage | Target share, air-yards share, route-driven opportunity are among the stickier public receiving signals. | Place heavy weight on role and route opportunity before touchdown outcomes. |
| QB fantasy production | Team dropbacks and QB rushing volume drive a large share of fantasy value; pure passing efficiency matters, but less than role and rushing for many archetypes. | Model volume/rushing first, then layer efficiency. |
| RB forecasting | Receiving role, goal-line work, and team scoring environment are more projectable than raw yards per carry. | Weight targets, routes, and high-value touches ahead of rushing efficiency spikes. |
| Rushing efficiency | Yards per carry and long-run rates are noisy year over year. | Regress explosive rushing efficiency heavily; keep it secondary. |
| DST | Defensive touchdowns and fumble-luck outcomes are volatile. | Project component events and points-allowed context, then regress touchdowns hard. |
| K | Kicker scoring is driven heavily by team scoring environment, red-zone behavior, and job security rather than last-year fantasy finish alone. | Use offense and coaching context as anchors; treat raw prior-year kicker rank as low signal. |

---

## 9. Source register and extraction requirements

The project should prefer the nflreadpy / nflreadr ecosystem for public structured football data. A separate manual layer is still required for qualitative context such as playcaller quality, injury recovery outlook, and role clarity.

**Source selection guardrail:** Prefer nflreadpy or nflreadr over deprecated wrappers. Where a source has known coverage or refresh caveats, capture those caveats in the ingestion metadata and expose them to downstream QA.

**Backtest integrity rule:** If market priors, depth charts, or manual context are used in evaluation, point-in-time archived snapshots must exist; otherwise exclude them from headline backtest claims.

| Source family | Extraction method | Coverage / cadence | Primary use | Dependency tier | Historically reconstructable? | Fallback if unavailable | Failure severity |
|--------------|-------------------|-------------------|-------------|----------------|------------------------------|------------------------|-----------------|
| nflverse play-by-play | nflreadpy: load_pbp | 1999+; nightly refresh | Core play-level usage, context, team tendencies, red-zone, EPA, xYAC, fantasy reconstruction | Required | Yes | Run fails | Run fails |
| Player and team stats | load_player_stats | Weekly / season summaries | Fast stat rollups, backfill, reconciliation | Required | Yes | Run fails | Run fails |
| Players / rosters / depth charts / snap counts | load_players, load_rosters_weekly, load_depth_charts, load_snap_counts | Mixed historical coverage | ID mapping, incumbency, position group, roster status, snap context | Required | Partial | Degrade to prior-year rosters with flag | Warn only |
| League settings export | Yahoo manual export / screenshot / entered config | Current league season | Exact scoring rules, roster slots, and draft constraints | Required | N/A (current season only) | Run fails | Run fails |
| Next Gen Stats weekly | load_nextgen_stats | 2016+; player weekly | Passing, receiving, and rushing tracking metrics | Optional | Yes (2016+) | Use pbp-derived proxies | Warn only |
| Participation data | load_participation | Historical; 2023+ caveat | Routes, formations, defenders in box, pressure context | Optional | Partial | Use snap counts as proxy | Warn only |
| PFR advanced stats | load_pfr_advstats | 2018+ by stat family | Additional advanced passing, rushing, receiving context | Optional | Yes (2018+) | Omit enrichment features | Warn only |
| Expected fantasy opportunity | load_ff_opportunity | Public expected fantasy points | Opportunity-quality anchor, xFP style features | Optional | Partial | Use raw pbp opportunity metrics | Warn only |
| Market priors | load_ff_rankings or ADP equivalent | Current and archived consensus | Consensus sanity check, prior, and model challenger baseline | Optional | Partial (archived years vary) | Omit market prior feature; keep as challenger only | Warn only |
| Draft / combine / contracts | load_draft_picks, load_combine, load_contracts | Draft 1980+, combine 2000+, contracts varies | Rookie priors, organizational investment | Optional | Yes | Use draft capital only | Warn only |
| Schedules and lines | load_schedules | Past and future games | Schedule strength, home/away, DST and kicker context | Required | Yes | Run fails | Run fails |
| FTN charting | load_ftn_charting | 2022+; charted data | Motion, play action, catchability, contested balls | Experimental | No (too recent) | Omit; do not use in backtest | Warn only |
| Manual curated context tables | CSV / YAML / database seed files | As maintained by analyst | Coaching quality, continuity, role clarity, injury recovery | Required (structure); Optional (content) | No (subjective, point-in-time) | Use neutral defaults (0.50) | Warn only |

---

## 10. Data quality, evaluation, and release readiness

### 10.1 Quality-control contract

| ID | Check | Requirement |
|----|-------|------------|
| QC-001 | No duplicate keys | No duplicate canonical player-season, player-week, or projection output rows. |
| QC-002 | ID bridge completeness | Canonical player IDs resolve for all draftable offensive players, kickers, and DST rows. |
| QC-003 | Share sanity | Team-level rush share, target share, or route-based shares sum to acceptable tolerances. |
| QC-004 | Range checks | Projected games, attempts, targets, sacks, and scores remain within plausible bounds. |
| QC-005 | Scoring reconciliation | Fantasy-point outputs equal the sum of the projected stat components under the active scoring config. |
| QC-006 | Missingness threshold | Critical features do not exceed agreed missingness thresholds without triggering fallback flags. |
| QC-007 | No leakage | Holdout evaluations confirm that no target-season realized stats leaked into features. |
| QC-008 | Manual audit | Every manual factor used in a run has owner, rationale, and timestamp. |
| QC-009 | Team-volume consistency | Projected player opportunities do not materially exceed projected team opportunity totals. |
| QC-010 | DST scoring logic | Points-allowed bucket calculations reconcile with the active DST config. |
| QC-011 | Kicker distance buckets | FG bucket totals reconcile with the active kicker config. |
| QC-012 | Schema check | Output schemas match the versioned contract expected by downstream ranking tools. |

### 10.2 Backtest and evaluation requirements

| Evaluation item | Requirement | Why it matters |
|----------------|------------|----------------|
| Rolling-origin preseason backtests | For each holdout season, train only on earlier seasons and features available before that season's opener or configured draft date. | Prevents leakage and mirrors real usage. |
| MAE / RMSE | Evaluate fantasy-point error by position and overall. | Captures absolute and squared error. |
| Rank correlation | Compute Spearman or Kendall rank correlation for preseason ranks. | Useful for pre-draft ordering quality. |
| Top-N hit rate | Measure how often projected top finishers actually finish in top tiers. Use 2-QB league context: QB top-20, RB top-20, WR top-30, TE top-10. | Good sanity check for ranking usefulness in a 10-team, 2-QB league. |
| Calibration | Assess whether P25/P75 intervals have the expected empirical coverage. Observed coverage should fall within a reasonable tolerance band. | Needed if floor/ceiling outputs are surfaced. |
| Archetype error slices | Report errors by rookies, team changers, injured returnees, committee backs, mobile QBs, elite WRs, streaming DSTs, and uncertain kickers. | Prevents aggregate metrics from hiding failure modes. |
| Baseline comparison | Compare against simple baselines: last-year fantasy points, weighted historical averages, and market prior rankings. | The model should beat naive baselines in a meaningful share of cases. |

### 10.3 Success criteria

| ID | Definition |
|----|-----------|
| SC-001 | Projection run completes without critical QA failures and produces outputs for all supported positions. |
| SC-002 | Model outperforms weighted-history baseline on aggregate offensive MAE. Model does not underperform baseline for any core offensive position group. Rank correlation exceeds baseline on the offensive pool. Specific thresholds to be set after initial baseline runs are complete. |
| SC-003 | Feature, run, and manual-factor lineage is sufficient to explain any notable player movement. |
| SC-004 | The ranking layer can be rerun under a new scoring or league-size config without retraining the stat model. |
| SC-005 | The engineer can hand the system to another maintainer with a runbook, test suite, and schema documentation. |
| SC-006 | Model-only and overlay-adjusted results are both published and evaluated separately. |

---

## 11. Deliverables, repo structure, and implementation plan

### 11.1 Required deliverables

| ID | Deliverable | Description |
|----|------------|-------------|
| D-001 | Versioned codebase | Source-controlled project with reproducible environment and config structure. |
| D-002 | Data source register | Documented extraction methods, caveats, and ownership for every source. |
| D-003 | Canonical data model | Defined tables, keys, and transformation rules for raw, canonical, and feature layers. |
| D-004 | Feature dictionary | Position-specific feature definitions, tiers, grains, and engineering notes. |
| D-005 | Scoring engine | Config-driven translation from projected stats to fantasy points. |
| D-006 | Projection outputs | Player projections, DST projections, kicker projections, ranks, and uncertainty bands. |
| D-007 | Evaluation report | Backtest results, baseline comparisons, error slices, and known limitations. |
| D-008 | Runbook | Instructions to refresh data, rerun models, apply manual factors, and release a new ranking set. |
| D-009 | Test suite | Automated tests for joins, scoring, feature transforms, and leakage prevention. |
| D-010 | Release checklist | Pre-release verification including Yahoo scoring confirmation and manual-factor review. |
| D-011 | Output schema | Documentation of output table field names, types, nullability, and definitions. |
| D-012 | Config contract | Documentation of all configurable parameters: scoring, league size, bench, ranking objective, replacement-level, recency weights, shrinkage. |
| D-013 | Decision log | Lightweight markdown file tracking key design and implementation decisions with rationale. |

### 11.2 Suggested repository structure

| Path | Purpose |
|------|---------|
| /configs | Scoring rules, recency weights, ranking assumptions, and environment-specific settings. |
| /configs/templates | Template configs for common league formats. |
| /data/raw | Immutable source snapshots by as-of date. |
| /data/silver | Canonical normalized tables with standardized keys. |
| /data/gold | Feature tables and training datasets. |
| /manual | Curated coaching, role, injury, and qualitative factor inputs. |
| /models | Training, inference, calibration, and ensembling code. |
| /outputs | Projection files, rankings, backtest results, and release artifacts. |
| /tests | Unit tests, integration tests, scoring tests, and data-quality checks. |
| /docs | Runbook, schema docs, decision log, and release notes. |
| /docs/decision_log | Individual decision records with rationale. |

### 11.3 Suggested milestone plan

| Phase | Milestone | Exit criteria |
|-------|----------|---------------|
| Phase 0 | Requirement and config lock | Confirm scope, scoring config, league settings (10-team, 6 bench), ranking assumptions, and manual-factor schema. Resolve all release blockers in Section 12. |
| Phase 1 | Data ingestion and canonical modeling | All core sources extract cleanly; canonical keys and tables pass QA. |
| Phase 2 | Exploration and feature report | Historical feature stability, missingness, and baseline relationships documented. |
| Phase 3 | Baseline stat models | Simple but reproducible preseason baselines exist for every position. |
| Phase 4 | Advanced features and manual overlays | Role/context/NGS/manual factors are added with auditability. |
| Phase 5 | Evaluation and challenger testing | Rolling backtests, baseline comparisons, and error slices complete. |
| Phase 6 | Ranking layer and release workflow | Scoring/ranking configs, VOR-ready outputs, and release checklist operational. |
| Phase 7 | Handoff | Runbook, documentation, and maintainer handoff complete. |

---

## 12. Release blockers and required decisions

The following items must be resolved before implementation proceeds past Phase 0. Items marked as resolved reflect confirmed decisions.

| ID | Issue | Status | Default if unresolved | Blocks |
|----|-------|--------|----------------------|--------|
| OI-001 | League size and bench size | **Resolved: 10 teams, 6 bench spots** | N/A | Ranking, replacement-level |
| OI-002 | Exact Yahoo DST and any nonstandard player scoring should be verified from the live league settings. | Open — verify before final release | Use Yahoo standard defaults; flag as unverified | Final ranking release |
| OI-003 | The draft-date freeze point has not been defined. | Open — keep configurable | Default to 1 week before draft date; as-of date is a runtime parameter | Training, evaluation |
| OI-004 | Ranking objective: whether draft ranks should optimize median projection, upside, or risk-adjusted value. | Open — keep configurable | Default to median (P50) projection ranking; support alternate objectives via config | Ranking layer |
| OI-005 | Coaching and injury context may require manual or alternate-source maintenance. | Open — document refresh process | Document ownership and refresh cadence for manual tables | Manual factor quality |
| OI-006 | DST and kicker season-long modeling may later benefit from a distinct weekly simulation layer. | Deferred beyond v1 | Design data model to support weekly extension later without restructuring | Future extensibility |

---

## 13. Manual-factor schema and governance

Because the user explicitly wants qualitative 0-to-1 inputs, the manual-factor layer is a first-class product requirement. This layer should be narrow, governed, and transparent. It should enrich the model rather than silently replace it.

**Governance rules:**
- Every manual factor must be stored as data, not embedded directly inside model code.
- Every manual factor must preserve both the raw score and a directionally normalized score.
- Every manual factor must include owner, rationale, timestamp, and optional expiration.
- Analyst confidence should be stored so low-confidence factors can be dampened or ignored.
- The release process should compare model-only outputs versus model-plus-overlay outputs before publish.
- **Insertion point:** Manual factors are applied as post-model overlays by default. They are not training features and are not used during model inference. They adjust projections after the statistical model has produced its output.
- **Max-effect policy:** No single manual factor may move a player's final projection by more than 15% without explicit override logging. This prevents a single subjective score from dominating the statistical model.
- **Low-confidence dampening:** Manual factors with confidence below 0.30 are dampened toward the neutral default (0.50) before application.

**Manual factor schema:**

| Field | Format | Purpose |
|-------|--------|---------|
| entity_type | player / team / coach / unit | What the factor applies to. |
| entity_id | Canonical key | Stable join key. |
| factor_name | String | Example: playcaller_quality_score. |
| score_raw | 0.00 to 1.00 | Human-entered raw score. |
| score_normalized | 0.00 to 1.00 | Directionally normalized so 1.00 is more favorable. |
| confidence | 0.00 to 1.00 | Optional confidence in the input score. |
| rationale | Text | Why the score was assigned. |
| source_note | Text | Reference note, article, or observation. |
| owner | Text | Who entered the score. |
| updated_at | Timestamp | Audit trail. |
| expires_at | Timestamp or null | Optional sunset for stale context. |

---

## Appendix A. Feature dictionary legend

The following appendices list the **candidate feature library** for the preseason model. These are a candidate library, not a requirement that every feature be implemented in v1. The engineer should prioritize features marked "Required for v1" and treat others as optional enrichment that can be added incrementally.

- **Grain legend:** P/S = player-season, P/W = player-week, T/S = team-season, T/W = team-week.
- **Tier legend:** Highest Weight = core anchor, Strong Secondary = useful but not dominant, Regress Hard = noisy and should be shrunk heavily, Manual Overlay = human-entered context score.
- **v1 Priority:** Required = must implement for v1, Optional = implement if time allows, Defer = skip for v1.
- **Backtest safe?:** Yes = historically available for point-in-time backtests, Partial = available for some years, No = not reconstructable.
- Primary source / extraction is the preferred source family; exact implementation can choose nflreadpy or nflreadr equivalents.
- Engineering notes describe transformation expectations, fallbacks, or caveats that matter to model design.

---

## Appendix B. Cross-position and team-context features

These features apply across multiple offensive positions or define the environment in which individual role shares sit.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| age_at_season_start | Player age on September 1 of the target season. | P/S | players | Strong Secondary | Required | Yes | Use for aging curves; interact with position and workload. |
| years_pro | NFL experience entering the target season. | P/S | players / draft picks | Strong Secondary | Required | Yes | Helpful for rookies, breakout timing, and decline modeling. |
| career_games_played | Career games played before the target season. | P/S | player stats | Strong Secondary | Required | Yes | Useful for availability priors and sample-size context. |
| games_active_projection | Projected regular-season games in which the player is active. | P/S | historical player-week + manual injury context | Highest Weight | Required | Yes | Model separately from per-game production; critical for season totals. |
| team_plays_proj | Projected offensive plays run by the player's team. | T/S | pbp -> team aggregation | Highest Weight | Required | Yes | Base team-volume anchor for all offensive positions. |
| neutral_pace | Situation-neutral pace / seconds per snap proxy. | T/S | pbp -> team/week | Strong Secondary | Optional | Yes | Use with plays projection; avoid double counting. |
| pass_rate_over_expected | Team pass tendency versus expectation. | T/S | pbp -> team/week | Highest Weight | Required | Yes | Key offensive context for QB/WR/TE; inverse relevance for RB rushing volume. |
| neutral_pass_rate | Pass rate in neutral game states. | T/S | pbp -> team/week | Highest Weight | Required | Yes | Useful when PROE is not stable enough alone. |
| points_per_drive | Team scoring efficiency per offensive drive. | T/S | pbp drives | Strong Secondary | Optional | Yes | Helpful for TD opportunity, DST, and kicker context. |
| red_zone_drives_per_game | Expected red-zone opportunities generated by the team. | T/S | pbp red-zone aggregation | Highest Weight | Required | Yes | Strong input for TD and field-goal opportunity. |
| playcaller_continuity_score | Continuity of head coach / OC / primary playcaller. | T/S | manual table | Manual Overlay | Optional | No | Use explicit scoring rubric; do not infer silently. |
| playcaller_quality_score | Analyst view of fantasy-friendliness of the playcaller. | T/S | manual table | Manual Overlay | Optional | No | Keep separate from continuity so they are independently tunable. |
| qb_stability_score | Stability and quality certainty of the team's starting QB. | T/S | manual + roster/depth chart | Manual Overlay | Optional | No | Especially important for WR/TE/DST/K context. |
| offensive_line_run_block_score | Expected run-block quality entering the season. | T/S | PFR adv / manual / prior team stats | Strong Secondary | Optional | Partial | Good context feature; should not dominate the RB model alone. |
| offensive_line_pass_block_score | Expected pass-protection quality entering the season. | T/S | PFR adv / manual / prior team stats | Strong Secondary | Optional | Partial | Important for QB pressure and longer-developing routes. |
| offensive_line_stability_score | Returner continuity and injury stability of the OL. | T/S | manual + roster snaps | Manual Overlay | Defer | No | Useful because line quality can change materially year to year. |
| competition_clearance_score | How clear the path is to meaningful volume. | P/S | manual + depth charts + rosters | Manual Overlay | Optional | No | Normalize so 1.00 means low competition / favorable access. |
| team_change_fit_score | How favorable the new team and scheme fit appear. | P/S | manual + roster/coaching context | Manual Overlay | Optional | No | Use only for team changers or as neutral default 0.50. |
| injury_recovery_desirability_score | Outlook for returning to full performance after injury. | P/S | manual + injury history | Manual Overlay | Optional | No | Normalize so 1.00 means low concern. |
| market_prior_rank | Consensus rank or ADP-style market prior. | P/S | ff_rankings / ADP feed | Strong Secondary | Optional | Partial | Use as one feature or benchmark; never let it be the only answer. |
| contract_commitment_score | Signal of organizational investment via contract or draft capital. | P/S | contracts / draft picks | Strong Secondary | Optional | Yes | Can help break ties in uncertain role battles. |
| schedule_desirability_score | Optional coarse preseason schedule attractiveness. | P/S | schedules + external team strength priors | Regress Hard | Defer | Yes | Keep low weight for season-long preseason models; schedules move. |

---

## Appendix C. Quarterback feature dictionary

QB projection should weight team dropbacks and rushing opportunity more heavily than raw passing-efficiency spikes.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| projected_team_dropbacks | Projected team dropbacks available for the starting QB(s). | T/S | pbp -> team aggregation | Highest Weight | Required | Yes | Fundamental passing volume anchor. |
| starter_share_of_dropbacks | Expected share of team dropbacks handled by the player. | P/S | depth chart + player history | Highest Weight | Required | Partial | Critical for avoiding split-QB ambiguity. |
| projected_pass_attempts | Projected pass attempts for the player. | P/S | derived | Highest Weight | Required | Yes | Can be direct output or derived from dropbacks and sacks. |
| projected_qb_rush_attempts | Projected QB rushing attempts including scrambles and designed runs. | P/S | player history + pbp | Highest Weight | Required | Yes | One of the strongest fantasy differentiators among QBs. |
| designed_run_rate | Share of QB rushes that are designed rather than scramble-driven. | P/W | pbp / charting | Strong Secondary | Optional | Partial | Designed runs are often more stable near the goal line. |
| scramble_rate | Rate of scrambles per dropback. | P/W | pbp | Strong Secondary | Optional | Yes | Useful for mobile-QB upside and sack-avoidance context. |
| goal_line_rush_share_qb | QB share of team rushes at the goal line or inside the five. | P/W | pbp | Highest Weight | Required | Yes | Directly tied to rushing-TD upside. |
| red_zone_pass_share | QB share of team red-zone pass attempts. | P/W | pbp | Highest Weight | Required | Yes | Strong TD-opportunity feature. |
| completion_pct_above_expectation | Passing accuracy over expectation. | P/W | nextgen | Strong Secondary | Optional | Yes (2016+) | Useful, but still secondary to volume and rushing. |
| epa_per_dropback | Efficiency per pass play including sacks. | P/W | pbp | Strong Secondary | Optional | Yes | Regress to reduce single-season noise. |
| avg_intended_air_yards | Average intended depth of target on QB throws. | P/W | nextgen | Strong Secondary | Optional | Yes (2016+) | Useful for aggression, yardage profile, and receiver dependence. |
| aggressiveness_rate | How often a QB throws into tighter windows. | P/W | nextgen | Regress Hard | Defer | Yes (2016+) | Can add context but is not a primary fantasy driver alone. |
| avg_time_to_throw | Average time from snap to pass release. | P/W | nextgen | Strong Secondary | Optional | Yes (2016+) | Interact with sack risk and scheme. |
| pressure_rate_faced | Pressure rate on QB dropbacks. | P/W | participation / charting | Strong Secondary | Optional | Partial | Team and QB interaction feature. |
| pressure_to_sack_rate | Share of pressured plays that become sacks. | P/W | pbp + pressure data | Strong Secondary | Optional | Partial | More informative than raw sack totals alone. |
| interception_rate_regressed | Regressed version of prior interception rate. | P/S | player stats | Regress Hard | Required | Yes | Avoid overreacting to single-season pick spikes. |
| passing_td_rate_regressed | Regressed version of prior passing TD rate. | P/S | player stats | Regress Hard | Required | Yes | Touchdown rate is noisy without strong supporting context. |
| receiver_room_quality_score | Overall quality/stability of pass-catching support. | T/S | manual + depth charts + prior production | Manual Overlay | Optional | No | Capture ecosystem effects without hiding them in the model. |

---

## Appendix D. Running back feature dictionary

RB projection is mostly an opportunity problem before it is an efficiency problem.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| snap_share_rb | Projected share of offensive snaps played by the RB. | P/S | snap counts / player stats | Highest Weight | Required | Yes | Foundational but should be paired with route and touch shares. |
| rush_share | Projected share of team rushing attempts. | P/S | pbp -> player/team aggregation | Highest Weight | Required | Yes | Core rushing workload signal. |
| route_participation_rb | Projected routes run or route participation rate. | P/S | participation / snap counts | Highest Weight | Required | Partial | Key separator between empty snaps and fantasy-valuable snaps. |
| target_share_rb | Projected share of team targets. | P/S | pbp -> player/team aggregation | Highest Weight | Required | Yes | Receiving role is disproportionately valuable for RB fantasy scoring. |
| targets_per_route_run_rb | Targets earned per route run. | P/S | pbp + routes | Strong Secondary | Optional | Partial | Good skill/context measure after stable route volume. |
| third_down_share | Share of backfield snaps/touches on third downs. | P/W | pbp situational splits | Highest Weight | Optional | Yes | Strong receiving and hurry-up proxy. |
| two_minute_share | Share of backfield work in hurry-up situations. | P/W | pbp situational splits | Strong Secondary | Defer | Yes | Useful for receiving-driven spike weeks. |
| goal_line_share_rb | Share of team rushing attempts near the goal line. | P/W | pbp | Highest Weight | Required | Yes | Direct TD opportunity feature. |
| inside_five_share | Share of rushes or touches inside the five-yard line. | P/W | pbp | Highest Weight | Required | Yes | One of the cleanest TD-usage features. |
| red_zone_touch_share_rb | Share of team red-zone touches. | P/W | pbp | Highest Weight | Required | Yes | Captures both rushing and receiving scoring opportunity. |
| team_run_rate | Team run tendency in relevant game states. | T/S | pbp -> team aggregation | Highest Weight | Required | Yes | Context anchor for backfield volume. |
| qb_rush_siphon_score | How much the QB is likely to steal red-zone rushing volume. | T/S | manual + QB history | Manual Overlay | Optional | No | Important negative context for some RBs. |
| run_block_context_score | Composite run-block environment. | T/S | PFR adv / manual | Strong Secondary | Optional | Partial | Use as context, not a substitute for workload. |
| defenders_in_box_rate | How often the RB faces stacked boxes. | P/W | participation / nextgen | Strong Secondary | Defer | Partial | Useful but noisy when isolated from team context. |
| expected_rush_yards | Model-based expected rushing yards from carry context. | P/W | nextgen | Strong Secondary | Optional | Yes (2016+) | Summarizes carry difficulty. |
| rush_yards_over_expected | Rushing yards above expectation. | P/W | nextgen | Regress Hard | Defer | Yes (2016+) | Add after shrinkage; do not let it overpower workload. |
| yards_per_carry_regressed | Regressed prior yards per carry. | P/S | player stats | Regress Hard | Required | Yes | Classic trap metric if overweighted. |
| receiving_yards_per_route_rb | Receiving output per route for RBs. | P/S | pbp + routes | Strong Secondary | Optional | Partial | Helpful for satellite backs and pass-game specialists. |
| backfield_competition_clearance_score | How clear the player is from serious backfield competition. | P/S | manual + depth charts | Manual Overlay | Optional | No | Normalize so higher means more secure role. |
| rookie_receiving_profile_score | Receiving upside prior for rookie RBs. | P/S | college stats / draft / manual | Strong Secondary | Optional | Yes | Important because receiving often determines fantasy ceiling. |

---

## Appendix E. Wide receiver feature dictionary

WR projection should center on route participation, target-earning ability, and air-yards role.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| route_participation_wr | Projected route participation when the team drops back. | P/S | participation / snap counts | Highest Weight | Required | Partial | Better than raw snap share for pass catchers. |
| target_share_wr | Projected share of team targets. | P/S | pbp -> player/team aggregation | Highest Weight | Required | Yes | One of the most stable public opportunity features. |
| targets_per_route_run_wr | Targets earned per route run. | P/S | pbp + routes | Highest Weight | Required | Partial | Strong role-efficiency bridge for WRs. |
| air_yards_share | Projected share of team intended air yards. | P/S | nextgen / pbp | Highest Weight | Required | Yes | Powerful indicator of yardage and TD opportunity. |
| average_depth_of_target | Average target depth. | P/S | nextgen / pbp | Strong Secondary | Optional | Yes | Good context for volatility and yardage profile. |
| end_zone_target_share | Share of team end-zone targets. | P/W | pbp | Highest Weight | Required | Yes | Strong TD-opportunity feature. |
| red_zone_target_share | Share of team red-zone targets. | P/W | pbp | Highest Weight | Required | Yes | Complements end-zone usage with larger sample size. |
| slot_rate | Share of routes from the slot. | P/W | participation / charting | Strong Secondary | Optional | Partial | Important for role type and target quality. |
| outside_rate | Share of routes aligned outside. | P/W | participation / charting | Strong Secondary | Defer | Partial | Useful alongside slot rate; avoid redundant overweighting. |
| motion_usage_rate | How often the WR is used in motion or schemed movement. | P/W | FTN charting | Strong Secondary | Defer | No (2022+) | Helpful for role creativity and manufactured touches. |
| average_separation | Average receiver separation at target/catch point. | P/W | nextgen | Strong Secondary | Optional | Yes (2016+) | Useful but context-sensitive. |
| average_cushion | Average defensive cushion faced. | P/W | nextgen | Regress Hard | Defer | Yes (2016+) | Adds role context; not a primary signal alone. |
| catchable_target_rate | Rate of targets deemed catchable/on-target. | P/W | FTN charting / target quality proxy | Strong Secondary | Defer | No (2022+) | Important quarterback-context interaction. |
| expected_yac | Expected yards after catch. | P/W | nextgen | Strong Secondary | Optional | Yes (2016+) | Role and target-quality summary feature. |
| yac_above_expectation | Yards after catch above expectation. | P/W | nextgen | Regress Hard | Defer | Yes (2016+) | Explosiveness can be noisy; regress heavily. |
| gadget_rush_share_wr | Projected rushing/gadget touch share for WRs. | P/S | pbp + charting | Strong Secondary | Defer | Yes | Important for select archetypes only; keep zero for most players. |
| target_competition_clearance_score | How clear the player is from competing target earners. | P/S | manual + depth charts | Manual Overlay | Optional | No | Useful when pass-catching rooms materially change. |
| new_team_fit_score_wr | Analyst view of scheme and QB fit for WR team changers. | P/S | manual | Manual Overlay | Optional | No | Keep explicit and low-to-moderate weight. |

---

## Appendix F. Tight end feature dictionary

TE projection should explicitly separate being on the field from actually running routes.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| route_participation_te | Projected route participation on team dropbacks. | P/S | participation / snap counts | Highest Weight | Required | Partial | Critical because TE snaps often include blocking. |
| route_vs_block_rate | Balance of routes run versus blocking usage. | P/S | participation / charting | Highest Weight | Required | Partial | One of the most important TE-specific role features. |
| target_share_te | Projected share of team targets. | P/S | pbp -> player/team aggregation | Highest Weight | Required | Yes | Still a primary TE opportunity metric. |
| targets_per_route_run_te | Targets earned per route run. | P/S | pbp + routes | Highest Weight | Required | Partial | Useful because TE opportunity must be normalized by route volume. |
| air_yards_share_te | Projected share of team air yards. | P/S | nextgen / pbp | Strong Secondary | Optional | Yes | Helpful for distinguishing shallow-volume TEs from spike-week types. |
| yards_per_route_run_te | Receiving production per route. | P/S | pbp + routes | Strong Secondary | Optional | Partial | Good all-in-one efficiency marker after route volume is set. |
| end_zone_target_share_te | Share of team end-zone targets. | P/W | pbp | Highest Weight | Required | Yes | Very important in a position where TDs move ranks materially. |
| red_zone_route_share_te | Share of TE routes inside the red zone. | P/W | participation + pbp | Strong Secondary | Optional | Partial | Useful for teams that lean on TEs near the goal line. |
| slot_rate_te | Share of TE routes from the slot. | P/W | participation / charting | Strong Secondary | Optional | Partial | Often more fantasy-friendly than pure in-line usage. |
| inline_rate_te | Share of TE snaps or routes aligned in-line. | P/W | participation / charting | Strong Secondary | Defer | Partial | Interpret together with block rate. |
| twelve_personnel_dependency | Dependence on 12-personnel-heavy usage. | T/S | pbp / participation / personnel | Strong Secondary | Defer | Partial | Can matter when coaching staffs change. |
| middle_of_field_target_tendency_qb | How friendly the QB historically is to TE-like areas. | T/S | manual + target splits | Manual Overlay | Defer | No | Useful context when TE role is otherwise stable. |
| te_competition_clearance_score | How clear the TE is from other target competition. | P/S | manual + depth charts | Manual Overlay | Optional | No | Helpful because TE markets can be very concentrated or very crowded. |
| rookie_te_readiness_score | Readiness prior for rookie TEs. | P/S | draft / combine / manual | Strong Secondary | Optional | Yes | TE rookies deserve a separate prior rather than direct extrapolation. |

---

## Appendix G. Defense / special teams feature dictionary

DST should be modeled through component events and points-allowed logic rather than raw prior-year fantasy points.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| projected_points_allowed | Expected points allowed by the defense. | T/S | team model derived from schedule and priors | Highest Weight | Required | Yes | Needed to map expected points-allowed bucket value. |
| projected_sacks_dst | Projected sacks. | T/S | defensive history + opponent context | Highest Weight | Required | Yes | Most stable recurring DST scoring event. |
| projected_interceptions_dst | Projected interceptions generated. | T/S | defensive + opponent turnover tendencies | Highest Weight | Required | Yes | Important component event. |
| projected_fumble_recoveries_dst | Projected fumble recoveries. | T/S | defensive + opponent ball-security tendencies | Strong Secondary | Required | Yes | Some recovery component is luck-driven; keep moderate weight. |
| projected_safeties_dst | Projected safeties. | T/S | historical rarity + pressure context | Regress Hard | Optional | Yes | Very low-frequency event; include only as a minor component. |
| projected_dst_td_regressed | Regressed expectation for DST/ST touchdowns. | T/S | historical component model | Regress Hard | Required | Yes | Do not carry forward prior TD spikes directly. |
| pressure_rate_def | Pressure rate or pass-rush disruption created. | T/S | charting / participation / sack proxies | Highest Weight | Optional | Partial | Supports sacks and turnover generation. |
| opponent_sack_rate_allowed | Aggregate opponent tendency to allow sacks. | T/S | pbp -> opponent history + schedule | Strong Secondary | Optional | Yes | Good DST opponent-context feature. |
| opponent_turnover_rate | Aggregate opponent INT/fumble tendency. | T/S | pbp + schedule | Strong Secondary | Optional | Yes | Useful for preseason schedule-weighted DST context. |
| home_game_environment_score | Advantage from home games, weather, and travel. | T/S | schedule + venue manual | Strong Secondary | Defer | Yes | More important for weekly use; still relevant season-long. |
| defensive_continuity_score | Continuity of defensive coordinator and key personnel. | T/S | manual + rosters | Manual Overlay | Optional | No | Useful when scheme/roster stability is meaningful. |
| special_teams_quality_score | Return and coverage quality for special teams. | T/S | manual + historical ST performance | Strong Secondary | Defer | Partial | Small but relevant for DST touchdown and field-position context. |

---

## Appendix H. Kicker feature dictionary

Kicker projection is mostly about team scoring opportunity, drive endings, coach tendency, and job security.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| projected_team_points | Expected team scoring output. | T/S | team model | Highest Weight | Required | Yes | Primary driver of XP and field-goal opportunities. |
| drives_into_fg_range | Projected drives ending within field-goal range. | T/S | pbp drives + team model | Highest Weight | Required | Yes | Better than team points alone for kicker usage. |
| red_zone_stall_rate | How often drives reach the red zone but fail to score TDs. | T/S | pbp red-zone aggregation | Highest Weight | Required | Yes | Creates field-goal opportunity. |
| coach_fg_preference_score | Analyst score for coach tendency to kick rather than go for it. | T/S | manual | Manual Overlay | Optional | No | Needed because 4th-down aggressiveness materially changes kicker outcomes. |
| extra_point_volume | Projected extra-point attempts or makes. | P/S | derived from team TD expectation | Highest Weight | Required | Yes | Stable team-offense-driven component. |
| fg_bucket_share_short | Projected share of FGs from 0-39 yards. | P/S | historical drive endings + kicker/team context | Strong Secondary | Required | Yes | Useful because scoring is bucketed. |
| fg_bucket_share_mid | Projected share of FGs from 40-49 yards. | P/S | historical drive endings + kicker/team context | Strong Secondary | Required | Yes | Important for custom scoring. |
| fg_bucket_share_long | Projected share of FGs from 50+ yards. | P/S | historical drive endings + kicker/team context | Strong Secondary | Required | Yes | High-value but lower-frequency attempts. |
| fg_accuracy_over_expected | Kicker skill relative to attempt difficulty. | P/S | manual / official kicking data | Strong Secondary | Optional | Partial | Use carefully; role and volume still dominate fantasy scoring. |
| stadium_weather_score | Venue and weather-friendliness of the kicker's environment. | T/S | schedule + venue manual | Strong Secondary | Defer | Yes | More useful for weekly modeling but still relevant season-long. |
| job_security_score_k | Confidence that the player will keep the job all season. | P/S | manual + roster/depth chart | Highest Weight | Required | No | Essential because some kickers lose the job quickly. |

---

## Appendix I. Manual 0-to-1 overlay feature dictionary

These manual features are allowed because the user explicitly wants a place for qualitative context. They should remain explicit, auditable, low-friction to edit, and directionally consistent.

| Feature | Definition | Grain | Source | Tier | v1 Priority | Backtest safe? | Engineering notes |
|---------|-----------|-------|--------|------|-------------|---------------|-------------------|
| playcaller_quality_score | Analyst score for fantasy-friendliness of the primary playcaller. | T/S | manual entry | Manual Overlay | Optional | No | 0.00 poor, 0.50 neutral/unknown, 1.00 elite. |
| playcaller_continuity_score | Stability of the playcalling environment year over year. | T/S | manual entry | Manual Overlay | Optional | No | 1.00 means same or highly similar system. |
| offensive_line_stability_score | Expected continuity and health of the OL. | T/S | manual entry | Manual Overlay | Defer | No | Use even when objective line metrics exist. |
| qb_stability_score | Certainty and quality of the QB environment. | T/S | manual entry | Manual Overlay | Optional | No | Especially important for pass catchers and kickers. |
| role_clarity_score | How clearly the player projects into an actionable fantasy role. | P/S | manual entry | Manual Overlay | Optional | No | High score means low ambiguity in workload pathway. |
| competition_clearance_score | How free the player is from meaningful same-position competition. | P/S | manual entry | Manual Overlay | Optional | No | Normalize so high score means low competitive pressure. |
| team_change_fit_score | Scheme, personnel, and coaching fit after a team change. | P/S | manual entry | Manual Overlay | Optional | No | Set to neutral when no team change occurred. |
| injury_recovery_desirability_score | Expected functional recovery entering the season. | P/S | manual entry | Manual Overlay | Optional | No | High score means low concern. |
| rookie_readiness_score | How quickly a rookie can command usable NFL opportunity. | P/S | manual entry | Manual Overlay | Optional | No | Useful because college production does not fully answer early-role questions. |
| job_security_score | How likely the player is to retain role/team designation all season. | P/S | manual entry | Manual Overlay | Optional | No | Important for kickers, committees, and fragile starters. |
| contract_commitment_score | Organizational investment in the player. | P/S | contracts / manual entry | Strong Secondary | Optional | Yes | Can be manual or derived, but store it explicitly if curated. |
| manual_factor_confidence | Confidence attached to a manual factor input. | P/S | manual entry | Manual Overlay | Required | No | Used to dampen or gate manual factor impact when confidence is low. |

---

## Appendix J. Public reference basis

| Reference family | Why it matters |
|-----------------|---------------|
| nflreadr / nflreadpy documentation | Primary public extraction interfaces for nflverse, Next Gen Stats, schedules, participation, FantasyPros, and ffopportunity data. |
| nflverse data docs | Coverage windows, refresh cadence, and source caveats such as participation, depth charts, and injuries. |
| NFL Next Gen Stats glossary / operations notes | Official description of tracking-based features like separation, cushion, completion probability, and expected rushing yards. |
| Public expected fantasy points work | Useful support for opportunity-quality features rather than raw fantasy points alone. |
| Public stability studies on NFL metrics | Support for weighting role/opportunity metrics over noisy touchdown or efficiency spikes. |
| Yahoo default scoring references | Reference point for verifying DST and kicker defaults before final production lock. |

---

## Appendix K. Final release checklist

1. Confirm exact Yahoo league settings and archive the scoring config used for the release.
2. Lock the as-of date and confirm no post-freeze information leaked into features.
3. Review source coverage flags and document any degraded-source fallbacks.
4. Review model-only versus model-plus-manual-overlay rank differences.
5. Confirm that all manual factors have owner, rationale, timestamp, and acceptable confidence.
6. Confirm no duplicate output rows and no null canonical IDs in the draftable player pool.
7. Reconcile fantasy-point outputs against projected component stats under the active scoring config.
8. Produce export files and release notes, including known caveats.

---

## Appendix L. Output schema

The following defines the primary output table structure. All fields are non-null unless marked optional.

### player_projection table

| Field | Type | Description |
|-------|------|-------------|
| run_id | string | Projection run identifier |
| as_of_date | date | Data freeze date for this run |
| canonical_player_id | string | Primary key — stable player identifier |
| player_name | string | Display name |
| position | string | QB, RB, WR, TE |
| team | string | Current team abbreviation |
| games_active_proj | float | Projected games active |
| {stat}_per_game_proj | float | Per-game stat projection (one column per component stat) |
| {stat}_season_proj | float | Season total stat projection (one column per component stat) |
| total_points_proj_p50 | float | Median season total fantasy points |
| total_points_proj_p25 | float | 25th percentile fantasy points |
| total_points_proj_p75 | float | 75th percentile fantasy points |
| ppg_proj | float | total_points_proj_p50 / games_active_proj |
| total_points_model_only | float | Fantasy points before manual overlay |
| total_points_overlay_adjusted | float | Fantasy points after manual overlay |
| overlay_delta | float | Difference: overlay_adjusted - model_only |
| position_rank | int | Rank within position group |
| overall_rank | int | Rank across all positions |
| replacement_level_points | float (optional) | Configurable replacement-level threshold |
| vor | float (optional) | Value over replacement |
| reason_codes | string | Comma-separated reason codes explaining major drivers |
| qc_flags | string (optional) | Comma-separated QA flags (low_sample, missing_source, manual_heavy, etc.) |

### dst_projection table

| Field | Type | Description |
|-------|------|-------------|
| run_id | string | Projection run identifier |
| canonical_team_id | string | Team identifier |
| team_name | string | Display name |
| projected_sacks | float | Season sack projection |
| projected_interceptions | float | Season INT projection |
| projected_fumble_recoveries | float | Season fumble recovery projection |
| projected_safeties | float | Season safety projection |
| projected_dst_td | float | Regressed DST/ST TD projection |
| points_allowed_bucket_value | float | Expected fantasy points from points-allowed scoring |
| total_points_proj_p50 | float | Median season fantasy points |
| total_points_proj_p25 | float | 25th percentile |
| total_points_proj_p75 | float | 75th percentile |
| position_rank | int | DST rank |
| reason_codes | string | Major projection drivers |

### kicker_projection table

| Field | Type | Description |
|-------|------|-------------|
| run_id | string | Projection run identifier |
| canonical_player_id | string | Player identifier |
| player_name | string | Display name |
| team | string | Team abbreviation |
| xp_made_proj | float | Projected extra points made |
| fg_made_0_39_proj | float | Projected FGs made 0-39 yards |
| fg_made_40_49_proj | float | Projected FGs made 40-49 yards |
| fg_made_50_plus_proj | float | Projected FGs made 50+ yards |
| total_points_proj_p50 | float | Median season fantasy points |
| total_points_proj_p25 | float | 25th percentile |
| total_points_proj_p75 | float | 75th percentile |
| position_rank | int | Kicker rank |
| reason_codes | string | Major projection drivers |

### Config structure

The following configuration files govern system behavior:

| Config file | Key parameters |
|-------------|---------------|
| scoring.yaml | Points per stat event by position (see Section 4) |
| league.yaml | league_size: 10, bench_spots: 6, roster_slots, flex_eligible_positions |
| ranking.yaml | ranking_objective (median/upside/risk_adjusted), replacement_level_by_position, vor_method |
| model.yaml | recency_weights, shrinkage_settings, manual_factor_toggles, uncertainty_method |
| sources.yaml | Source paths, as_of_date, refresh settings, fallback behavior |

---

**Bottom line:** If the engineer implements the system described here, they will have a reusable preseason fantasy projection engine rather than a fragile one-off ranking spreadsheet. That is the standard this document is trying to enforce.
