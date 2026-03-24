# Decision Log

Records why specific implementation choices were made. Organized by phase.

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
