# Decision Log

Records why specific implementation choices were made. Organized by phase.

---

## Phase 5 — Position Models & Uncertainty

### D-5.1: DST counting stats from league averages scaled by quality factor

**Decision:** DST counting stats (sacks, INTs, fumble recoveries, DST TDs) use league-average per-game rates scaled by a defensive quality factor derived from points-allowed: `quality = (league_avg_pa / team_pa)^0.5`.

**Why:** The silver/gold layers don't contain team-level defensive counting stats (sacks forced, INTs forced, etc.) — `team_week_fact` has offensive stats per team. Deriving defensive stats via schedule-opponent matching would add significant complexity for marginal accuracy in a v1 model. The square-root scaling dampens the quality factor so a slightly-better-than-average defense doesn't get wildly inflated counting stats. This aligns with AD-5 ("lighter-weight models" for DST/K).

### D-5.2: Kicker stats from team scoring rate × league averages

**Decision:** Kicker projections estimate XP and FG volume by scaling league-average rates (3.0 XP/game, 1.85 FG/game) by the team's points-per-game relative to league average. FG distance distribution uses fixed league-average proportions.

**Why:** We don't ingest kicker-specific historical data (FG makes by distance bucket) into the silver layer. Team scoring rate is a good proxy for kicker opportunity volume — higher-scoring teams attempt more XPs and FGs. The distance distribution is stable across teams at the league level, so fixed proportions are a reasonable v1 assumption.

### D-5.3: Secondary rates (rush_td_rate, fumble_rate) computed from player_week_fact

**Decision:** Position projectors receive pre-computed "secondary rates" (rush_td_rate per attempt, fumble_rate per touch) derived from player_week_fact using the same recency-weighting approach as the gold features. Rookies without history fall back to position-specific league averages.

**Why:** The gold-layer efficiency features cover primary rates (YPA, comp%, TD%, INT%, YPC, catch_rate, yards_per_target, rec_TD%) but not rush_td_rate or fumble_rate. These secondary rates are needed to complete the projection (especially rush TDs for QBs and RBs). Computing them from historical data with recency weighting is consistent with the rest of the pipeline.

### D-5.4: Uncertainty via position-specific CV perturbation (not backtest residuals)

**Decision:** Bootstrap uncertainty uses position-specific coefficients of variation (QB 15%, RB 25%, WR 20%, TE 25%) to perturb per-game stats, rather than historical (actual - projected) residuals from a backtest.

**Why:** Backtest residuals require Phase 7's rolling-origin backtest to compute — they're a chicken-and-egg problem for Phase 5. The CV approach produces meaningful uncertainty bands that capture the key insight: RBs are more volatile than QBs, positional injury risk varies, etc. When Phase 7 lands, the uncertainty module can be upgraded to use empirical residuals.

### D-5.5: Projectors take gold features + secondary rates, not raw silver data

**Decision:** Offensive projectors (QB/RB/WR/TE) take pre-built gold DataFrames (team_context, role, efficiency, availability) plus a pre-computed secondary_rates dict. DST/Kicker projectors additionally take team_week_fact since they need team-level historical data not captured in the gold layer.

**Why:** This keeps the projectors focused on the DAG computation (volume × share × efficiency = stats) without re-implementing feature engineering. The gold features already contain recency-weighted, regressed, normalized values. The CLI handler loads both gold and silver data, computes secondary rates once, and passes everything to `run_projections()`.

---

## Phase 4 — Scoring Engine

### D-4.1: score_player applies all rules regardless of position

**Decision:** `score_player` reads every stat key from the stats dict and applies every scoring rule, regardless of the `position` argument. Passing `position="WR"` with `rush_yd=25` will score those rush yards.

**Why:** FR-005 requires cross-category stat support. Branching on position would require a mapping of "which stats apply to which positions," and would silently zero out trick-play stats for non-QB/RB positions. Since the scoring config treats all offensive positions the same way, the cleanest implementation is to apply all rules unconditionally — the `position` argument is accepted for future extensibility but has no effect on scoring logic today.

### D-4.2: yards-per-point as the config unit for yardage scoring

**Decision:** `OffenseScoringConfig` stores `passing_yards_per_point: 25.0` (and similarly for rushing/receiving) rather than storing the per-yard multiplier (0.04).

**Why:** The "1 point per 25 yards" framing maps directly to how Yahoo and most platforms describe yardage scoring. Storing the per-yard multiplier (0.04) would be equivalent mathematically but less legible when reading the config file. The scoring engine divides `stats["pass_yd"] / config.offense.passing_yards_per_point`, which reads naturally.

### D-4.3: score_dst uses direct bracket lookup; expected_pa_bracket_value is a separate utility

**Decision:** `score_dst` does a direct bracket lookup on `pa_per_game` (no Monte Carlo). `expected_pa_bracket_value` is a separate exported function for callers that want to account for PA variance.

**Why:** Phase 4 only needs to score known (projected) stat lines. The direct lookup is exact and fast. The Monte Carlo utility is needed in Phase 5 uncertainty calculations, where projecting a distribution over PA per game matters. Keeping them separate means `score_dst` is a simple pure function with no random state, making it easier to test and reason about.

---

## Phase 3 — Feature Engineering

### D-3.1: Recency-weighted averages for team context

**Decision:** Aggregate team_week_fact to per-game averages per team-season, then apply configurable recency weights (default 50/30/20) across prior seasons. Teams with fewer than 3 seasons of history shrink toward league averages.

**Why:** Team environments shift year to year (coaching changes, roster turnover), so recent seasons should count more. But a single-season sample is noisy — blending with prior years smooths out fluky seasons. The shrinkage toward league average for short-history teams (e.g., expansion or relocation edge cases) prevents extreme projections from a single outlier season.

### D-3.2: Share normalization within teams

**Decision:** After computing all players' recency-weighted rush_share and target_share, proportionally scale shares within each team so they sum to ≤1.0.

**Why:** When a team changer joins a new team, their historical shares (computed against their old team's volume) stack on top of existing players' shares, easily pushing totals above 1.0. Without normalization, the exit criterion (shares ≤1.05 per team) would fail. Proportional scaling preserves relative share ordering while enforcing the budget constraint. This is a projection-time concern — historical per-season shares are computed honestly against actual team totals.

### D-3.3: Team changer blending with positional priors

**Decision:** For team changers, blend recency-weighted historical shares with positional priors using configurable weights (default 70% player history, 30% positional prior).

**Why:** A player's historical shares reflect their talent/role, but the new team's scheme and competition matter too. Pure historical shares ignore the new context; pure positional priors ignore the player's track record. The 70/30 blend is a pragmatic starting point — the model config makes it tunable. The positional priors are conservative defaults (e.g., RB rush_share 0.15) that act as a soft anchor toward the team's typical usage distribution.

### D-3.4: regress_rate as standalone function in efficiency.py

**Decision:** Implement empirical Bayes regression-to-mean as a single pure function `regress_rate(observed, sample_size, prior, regression_sample)` in the efficiency module.

**Why:** This formula — `(observed × N + prior × k) / (N + k)` — is the core shrinkage mechanism used throughout the projection system. Making it a named, testable function (rather than inline math) means: (1) the exact formula is verified by a known-value test (`regress_rate(0.06, 500, 0.045, 1500) == 0.04875`), (2) Phase 5 models can import and reuse it, and (3) the regression_sample values are configurable per stat in `model.yaml`.

### D-3.5: Availability age discounts by position

**Decision:** Apply per-position age discount thresholds (QB 37, RB 28, WR 31, TE 31, K 38) that reduce projected games by 0.5 per year over the threshold.

**Why:** Aging curves differ dramatically by position. RBs decline earliest (late 20s), while QBs and kickers can produce well into their late 30s. A blanket age penalty would over-penalize QBs and under-penalize RBs. The 0.5 games/year discount is conservative — enough to flag old players but not so aggressive that a 30-year-old RB gets projected for 5 games. The thresholds are hardcoded because they reflect well-established football priors, not league-specific settings.

### D-3.6: Manual factors as CSV with validation gates

**Decision:** Store manual factors in a plain CSV with strict validation: reject rows with score_raw outside [0,1], missing owner, or missing rationale. Expire rows past their `expires_at` date.

**Why:** The requirements (FR-009, FR-010, NFR-014) demand that manual inputs be explicit, auditable, and governed. CSV is the simplest format an analyst can edit in any spreadsheet tool. The validation gates enforce the governance requirements at load time — a factor without ownership or rationale is rejected, not silently included. Expiration prevents stale preseason assessments from persisting into later runs.

---

## Phase 2 — Data Ingestion & Canonical Transform

### D-2.1: Registry pattern for source extractors

**Decision:** Use a decorator-based registry (`_SOURCE_EXTRACTORS` dict) in `snapshot.py` rather than a long if/elif chain or dynamic dispatch.

**Why:** Each nfl_data_py function has a slightly different signature (some take seasons, some don't, some have extra kwargs). A registry lets each extractor be a self-contained function with its own argument handling. Adding a new source means writing one decorated function — no changes to the extraction loop. The alternative (a big mapping dict with lambda wrappers) would be less readable and harder to debug.

### D-2.2: gsis_id as canonical_player_id

**Decision:** Use nflverse's `gsis_id` as the canonical player identifier, not `pfr_id` or ESPN ID.

**Why:** `gsis_id` is the most stable and widely populated ID in the nflverse ecosystem. It's the primary key in their players table and is present on weekly stats, PBP, and rosters. PFR IDs are valuable but have gaps for younger/less-notable players. We bridge to `pfr_id` where available but never rely on it as a primary key.

### D-2.3: Single normalize_team_abbr function shared across transforms

**Decision:** Define team abbreviation normalization in `team_dim.py` and have all other transforms import it from there.

**Why:** Team abbreviation inconsistency is one of the most common data quality issues in NFL data. Having a single function ensures every table uses the same mapping. The alternative — each module handling its own normalization — would inevitably lead to inconsistencies. The `TEAM_ABBR_MAP` dict is the single place to update when the NFL has another relocation.

### D-2.4: Neutral pass rate filter (margin ≤ 7, Q1–Q3)

**Decision:** Define "neutral game state" as score margin ≤ 7 points AND quarters 1–3 for the neutral pass rate metric in `team_week.py`.

**Why:** Raw pass rate is heavily influenced by game script — teams that are behind pass more, teams that are ahead run more. Filtering to neutral states (close games, before the 4th quarter) gives a better signal of a team's true offensive tendency. The ≤7 threshold is standard in football analytics (roughly within one score). Excluding Q4 removes late-game situations where teams are running out the clock or in desperation mode. This metric feeds into Phase 3's team context features.

### D-2.5: Red zone drives as distinct drives with yardline_100 ≤ 20

**Decision:** Count red zone drives by counting distinct drive IDs that have at least one play with `yardline_100 ≤ 20`, rather than counting red zone plays.

**Why:** Counting plays would double-count multi-play red zone possessions. We want to know how often a team reaches the red zone, not how many plays they run there. This is a better proxy for scoring opportunity volume, which feeds into TD projection models. The nflverse PBP data provides both `drive` IDs and `yardline_100`, making this aggregation straightforward.

### D-2.6: Idempotent ingest via manifest check

**Decision:** Skip re-extraction if a `_manifest.json` exists with all required sources present, rather than re-downloading and comparing hashes.

**Why:** nfl_data_py downloads from GitHub repos on every call — there's no local cache by default, and downloads can be slow (especially PBP data at ~40M rows). Checking the manifest is instant. The tradeoff is that if upstream data is corrected mid-season, you need to delete the manifest to force a re-pull. This is acceptable because the design document specifies explicit snapshot dates and immutable bronze-layer data.

### D-2.7: team_week_fact derived from PBP, not weekly stats

**Decision:** Build `team_week_fact` from play-by-play data rather than from the weekly stats table.

**Why:** The weekly stats table is player-level and doesn't have team-level aggregates like total plays, dropbacks, or EPA. PBP data is the only source that supports computing neutral pass rate, red zone drive counts, and EPA/play — all of which are critical inputs to the team context feature layer in Phase 3. The cost is that PBP files are much larger (~40M rows across 6 seasons), but we only aggregate once per pipeline run.

### D-2.8: Filter positions early in player_week and player_dim

**Decision:** Filter to fantasy-relevant positions (QB, RB, WR, TE, K, FB) as early as possible in both `player_dim.py` and `player_week.py`.

**Why:** The raw nflverse data includes OL, DL, LB, DB, etc. Carrying those rows through the pipeline wastes memory and creates noise in aggregations. Filtering early reduces the player_week_fact table size significantly. FB is included because some fullbacks have fantasy-relevant receiving or rushing production (and nflverse sometimes classifies them separately from RB).

---

## Phase 1 — Project Foundation

### D-1.1: Frozen dataclasses for config

**Decision:** Use `@dataclass(frozen=True)` for all config classes rather than plain dicts, Pydantic models, or attrs.

**Why:** Frozen dataclasses enforce immutability with zero dependencies (stdlib only). Config should never be mutated after loading — a bug where someone accidentally modifies a scoring value mid-pipeline would be extremely hard to track down. Pydantic would add a dependency and complexity we don't need. Plain dicts provide no structure or type safety. The frozen constraint catches mutation bugs at the point of attempt rather than downstream.

### D-1.2: SHA-256 config hash over file bytes

**Decision:** Compute config hash by hashing raw file bytes (sorted by filename), not by serializing the parsed dataclass.

**Why:** Hashing the raw bytes means the hash changes if whitespace, comments, or formatting changes — even if the parsed values are identical. This is intentional: it makes the hash a strict "did anything in the config files change" check, which is what we want for reproducibility tracking. If we hashed the parsed values, a YAML formatting change could silently produce a different file but the same hash, making it harder to trace exactly which config files produced a given run.

### D-1.3: All subcommands defined upfront in CLI

**Decision:** Define all 7 subcommands (ingest, transform, features, project, rank, run, backtest) in Phase 1, even though most aren't implemented yet.

**Why:** This lets `python -m ffmodel --help` show the full pipeline shape from day one. It also means the CLI contract is stable — later phases just wire up handlers, they don't change the argument structure. Users (and the design document) can reference specific commands immediately.

### D-1.4: Separate config files per concern

**Decision:** Five separate YAML files (`scoring.yaml`, `league.yaml`, `model.yaml`, `ranking.yaml`, `sources.yaml`) rather than one monolithic config.

**Why:** Each config file maps to a distinct concern and changes independently. Scoring rules change when the league commissioner changes settings. Model parameters change during tuning. Source configuration changes when new data becomes available. Separate files mean you can diff, version, and discuss each concern independently. The `ProjectConfig` aggregate class still provides a single entry point for code that needs everything.
