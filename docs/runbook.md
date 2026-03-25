# Runbook

Operational guide for the fantasy football projection system.

## Data Refresh

### Full refresh (new season)

1. Update `configs/sources.yaml`:
   - Bump `seasons.max` to include the new season
   - Set `seasons.target` to the projection year
2. Run the full pipeline:
   ```bash
   uv run python -m ffmodel run --as-of-date YYYY-MM-DD
   ```
   The `as-of-date` should be set to the NFL opener date or your league's draft date.

### Incremental refresh (same season, updated data)

Delete the ingest manifest to force re-pull, then rerun:
```bash
rm data/raw/YYYY-MM-DD/_manifest.json
uv run python -m ffmodel run --as-of-date YYYY-MM-DD
```

## Model Rerun

To rerun projections without re-ingesting or re-transforming:
```bash
uv run python -m ffmodel features --as-of-date YYYY-MM-DD
uv run python -m ffmodel project --as-of-date YYYY-MM-DD
uv run python -m ffmodel rank    --as-of-date YYYY-MM-DD
```

To rerun only scoring/ranking (e.g., after changing `configs/scoring.yaml`):
```bash
uv run python -m ffmodel rank --as-of-date YYYY-MM-DD
```

## Manual Factor Editing

1. Edit or create CSV files in `manual/`:
   - Each file must have columns: `entity_id`, `entity_type`, `factor_name`, `score_raw`, `confidence`, `owner`, `rationale`, `timestamp`
   - `entity_type` is either `player` (using canonical player ID) or `team` (using team abbreviation)
   - `score_raw` is 0.0 to 1.0 (0.5 = neutral)
   - `confidence` is 0.0 to 1.0
2. Rerun features and downstream:
   ```bash
   uv run python -m ffmodel features --as-of-date YYYY-MM-DD
   uv run python -m ffmodel rank --as-of-date YYYY-MM-DD
   ```

Manual factors are excluded from backtest headline numbers since they are not historically reconstructable.

## Backtest Evaluation

```bash
uv run python -m ffmodel backtest --seasons 2023,2024,2025
```

Outputs in `outputs/backtest/`:
- `backtest_results.parquet` — per-player per-season detail
- `backtest_summary.csv` — MAE, RMSE, Spearman rho, top-N hit rate, calibration by position
- `baseline_comparison.csv` — model vs weighted-history and last-year baselines

## Scoring Config Changes

The scoring engine is config-driven. To change scoring rules:
1. Edit `configs/scoring.yaml`
2. Rerun `rank` (no model retraining needed):
   ```bash
   uv run python -m ffmodel rank --as-of-date YYYY-MM-DD
   ```
3. Verify: QB points change by exactly `interceptions × delta` for interception weight changes.

## Release Checklist

Before publishing rankings:

1. Run full pipeline with target as-of-date
2. Run QA checks (automatic in full pipeline; review any warnings)
3. Run backtest to verify model accuracy:
   ```bash
   uv run python -m ffmodel backtest --seasons 2023,2024,2025
   ```
4. Verify model MAE <= weighted-history baseline MAE for offensive positions
5. Spot-check `combined_rankings.csv`:
   - Top 5 QBs are plausible NFL starters
   - Top 5 RBs are known bellcow/high-volume backs
   - No player has >17 games_active
   - position_rank starts at 1 and is contiguous
6. Verify scoring config matches your league's Yahoo settings
7. Review manual factors: confirm each has owner, rationale, and timestamp
8. Run full test suite: `uv run pytest tests/ -v`

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `FileNotFoundError: No silver data` | Run `ffmodel ingest` and `ffmodel transform` first |
| Stale data after roster moves | Delete `_manifest.json` and rerun ingest |
| QA check fails on share tolerance | Review `player_role_features` for the flagged team |
| Empty projections for a position | Check that `player_dim` has players at that position |
| Backtest shows 0 matched players | Verify holdout season exists in silver data |
