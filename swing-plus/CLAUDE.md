# Instructions for Claude Code

This file gives Claude Code orientation for working on the Swing+ project. Read it before making changes.

## Project state

The model is **production-ready** as of v1.0.0. The deployable artifact is `swing_plus_model_v1.joblib` and the inference module is `swing_plus.py`. The pipeline directory contains the modules used to build the artifact.

Phase 1 is the final metric. Phase 2 (path reconstruction) was attempted but didn't improve the metric — those modules are kept for transparency.

## Most likely next tasks

1. **Adding 2026 data.** When 2026 Statcast bat-tracking becomes available:
   - Pull pitch-level data via pybaseball (`statcast()` function with date range)
   - Cache to parquet under `data/raw/statcast_2026_H1.parquet`
   - Run `model.score_pitch_level(df)` to get scored leaderboards
   - No retraining required; 2026 scores will be comparable to 2023-2025

2. **Wiring this into a website.** The inference module is a plain Python class. Wrap it however your stack prefers — Flask, FastAPI, Django, etc. The model loads in ~10ms and scores are fast (single batch matrix operations).

3. **Periodic retraining.** Once a full season completes, you may want to retrain to keep the 100-mean anchor calibrated. The pipeline modules 01 → 02 → 04 → 07 → 09 → 20 reproduce the full training run.

## Important conventions

- The model expects raw Statcast column names verbatim (e.g., `intercept_ball_minus_batter_pos_x_inches`). Don't rename them on the way in.
- The `half` column is just a string label (e.g., `"2026_H1"`). The model doesn't parse it — it's used for grouping in `score_pitch_level()`.
- The `score_pitch_level()` method does the full pipeline: filter → aggregate → score. Use it as the main entry point unless you have a specific reason to do steps separately.

## What NOT to do

- **Don't try to "improve" the metric by adding the top-down path features back in.** We tested this in modules 18-19 and confirmed it overfits — CV R² goes up, but stability drops and held-out predictive power doesn't move. The Phase 1 feature set is the right one for this data.
- **Don't change `rv_nonbip_constant` without retraining.** It's calibrated against the same swings the models were fit on.
- **Don't try to score swings without the bat-tracking columns.** Pre-2023-H2 data doesn't have them and the model will fail.

## Things worth doing if you have time

- A FastAPI endpoint wrapper exposing `score_pitch_level` over HTTP
- A "compare two halves" function for player profile views (e.g., show how Bleday's profile changed between 2025 and 2026)
- CI tests that load the artifact and verify it produces known outputs on a small fixture
- Caching/memoization for the leaderboard given the same input data

## Things to be careful about

- The training data is roughly 1700 player-halves. If you retrain on substantially more data, the polynomial features (54 cross-terms from 9 inputs) will start to look sparse. Consider switching to a richer feature engineering approach (or just more regularization) before retraining at scale.
- `pybaseball.statcast()` is rate-limited. Pulls of >1 month at a time tend to time out. Always chunk by week when scripting bulk pulls (see `pipeline/01_ingest.py` for the pattern).
- The competitive-swing filter is critical. About 30-50% of rows with `bat_speed` populated in Statcast are garbage measurements (check swings, tip swings, tracking failures). The filter thresholds in the artifact were tuned against the training data — don't loosen them without re-checking the filter's effect on the model.

## If something breaks

- The artifact is small (~4KB) and self-contained; if loading fails, check Python/joblib/sklearn versions match training (Python 3.10+, joblib 1.x, sklearn 1.3+).
- If predictions look completely wrong, check the input column schema first. Missing or misnamed columns are the most common cause of silent failure.
- If the leaderboard has fewer players than expected, check the `min_swings` threshold (180). Mid-season pulls will have many players below threshold.
