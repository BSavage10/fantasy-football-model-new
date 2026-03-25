# Decision Log

Key design and implementation decisions made during development.

## Phase 1: Foundation

### Decision: Frozen dataclasses for config
**Why:** Prevents accidental mutation during pipeline execution. Config changes require explicit reload, making the pipeline deterministic and auditable via `config_hash`.

### Decision: SHA-256 config hash over raw YAML bytes
**Why:** File-content hashing ensures any config change — even whitespace — produces a different hash. This makes run_id reproducible and catches unintended config edits.

### Decision: Single `normalize_team_abbr()` function
**Why:** Centralized team name mapping (OAK→LV, SD→LAC, etc.) eliminates inconsistency. Every module imports from `team_dim.py` rather than maintaining its own mapping.

## Phase 2: Data Ingestion & Transform

### Decision: Derive team_week_fact from play-by-play, not weekly stats
**Why:** Play-by-play provides neutral pass rate (margin ≤7, Q1–Q3) and red zone drive counts (distinct drives, not plays), which are not available in weekly aggregates. The cost is ~40M rows of PBP processing per season.

### Decision: Idempotent ingest via manifest file
**Why:** Prevents redundant nfl_data_py API calls. Deleting `_manifest.json` is the explicit re-pull mechanism.

## Phase 3: Feature Engineering

### Decision: Empirical Bayes shrinkage (regress_rate) for efficiency features
**Why:** Small-sample players (backups, rookies) get pulled toward league averages rather than showing extreme rates. The pseudo-observation count per metric is configurable in `model.yaml`.

### Decision: Cap team shares at 1.0 with proportional normalization
**Why:** Recency-weighted shares can exceed 1.0 when players join a team. Capping and proportional redistribution maintains physical consistency without losing relative ordering.

## Phase 4: Scoring Engine

### Decision: Apply all offensive scoring rules regardless of position (FR-005)
**Why:** Cross-category stats (WR rushing TDs, QB receiving trick plays) are real and should be credited. Applying all rules to all players simplifies the engine and ensures nothing is missed.

### Decision: Monte Carlo for DST points-allowed brackets
**Why:** The PA bracket is concave/nonlinear, so Jensen's inequality means E[bracket(PA)] ≠ bracket(E[PA]). Monte Carlo with 10K samples captures the true expectation under PA uncertainty.

## Phase 5: Position Models

### Decision: Six separate position projectors instead of one unified model
**Why:** Each position has fundamentally different stat profiles and projection logic (team_targets × target_share for WR vs team_rushes × rush_share for RB). Separate projectors are clearer and easier to debug per position.

### Decision: Bootstrap residual perturbation for uncertainty
**Why:** Position-specific CV perturbation of per-game stats and games_active captures the two main sources of projection uncertainty (rate volatility and health) without requiring historical residual data.

## Phase 6: Overlay, Ranking, QA & Export

### Decision: Multiplicative overlay combination with ±25% cap
**Why:** Multiplicative combination ensures factors compound naturally (two bullish factors amplify each other). The cap prevents manual factors from dominating the model output.

### Decision: Low-confidence dampening toward 0.50 neutral
**Why:** A factor with 0.10 confidence and 0.90 score should barely move projections. Dampening toward neutral scales the effect proportionally to confidence.

### Decision: 12 QA checks that warn but don't block export
**Why:** QA failures are logged as warnings. A strict fail-on-any-QA-failure policy would block output for known edge cases (e.g., a team with unusual roster composition). The user reviews warnings and decides.

## Phase 7: Evaluation & Documentation

### Decision: Rolling-origin backtest protocol
**Why:** For each holdout season, using only data from prior seasons mirrors real preseason usage and prevents any form of leakage. This is the gold standard for time-series evaluation.

### Decision: Exclude manual factors from headline backtest numbers
**Why:** Manual factors (coaching changes, injury returns, qualitative assessments) are not historically reconstructable. Including them would inflate backtest accuracy in ways that don't generalize.

### Decision: Offensive-only backtest evaluation
**Why:** DST and kicker projections depend heavily on league-average counting stats and team scoring context rather than individual player models. Backtesting them against individual actuals is not meaningful in the same way. Offensive positions (QB, RB, WR, TE) are where the model's value-add is measurable.

### Decision: Reuse pipeline build_* functions directly in backtest
**Why:** The backtest calls the same `build_team_context_features()`, `build_player_role_features()`, etc. functions as the live pipeline. This ensures the backtest tests the actual production code path, not a separate backtest-specific reimplementation.

### Decision: Use latest available silver data for all holdout seasons
**Why:** The backtest reads silver-layer data once and filters by `season < holdout` for features. This avoids requiring separate ingest/transform runs per holdout year while still enforcing the leakage gate (features never see holdout data).
