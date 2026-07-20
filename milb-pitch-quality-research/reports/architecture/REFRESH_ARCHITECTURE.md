# Refresh Architecture

Phase 10. Modeled on `prospect-tracker`'s existing, working refresh system (`run_monthly.py`, `deploy/nightly-build.sh`) rather than inventing a parallel one — per Governing Philosophy #3 (no parallel systems).

## Update cadence, by module

| Module | Cadence | Rationale |
|---|---|---|
| Module 1 (Stuff) | **Daily** (matches `run_monthly.py --daily`) | Cheapest to refresh (a straightforward per-pitch aggregation); highest reliability means new data changes the estimate meaningfully game-to-game early in a pitcher's sample. |
| Module 2 (Arsenal) | **Daily** | Same aggregation cost as Module 1; shares its input data. |
| Module 3 (Miss, tracked + outcome-only) | **Daily** | Same reasoning; moderate reliability makes frequent shrinkage-aware updates more valuable, not less. |
| Module 4 (Ground-Ball) | **Weekly**, once promoted out of research-only status | Batted-ball volume accrues slower than pitch volume; daily refresh would mostly show sampling noise. |
| Module 5 (Damage Suppression) | **Not refreshed in production** | Research-only (`PRODUCTION_CLASSIFICATION.md`) — refresh only on-demand for research purposes, not on a production cadence. |
| Tracking-status gate itself | **Seasonal** (start-of-season re-check), with a manual override path | Venue tracking installs don't change mid-season under normal circumstances (Phase 1A found no within-season variation in the pilot) — but `TRACKING_BRANCH_ARCHITECTURE.md` flags this as a real open gap if it ever does. |

## Refresh order

Matches the dependency graph (`DEPENDENCY_GRAPH.md`) directly: tracking-status gate → raw pull → Modules 1-2 → Module 3-4 (which depend on 1-2 as covariates, not hard inputs, but should refresh after them for consistency) → reliability/stabilization indicators recomputed last (they depend on the full current-season sample, not just the newest increment).

## Dependencies on existing infrastructure

This research's refresh should be a **new stage appended to `run_monthly.py`'s existing daily/monthly split**, not a standalone cron job — reusing the proven single-writer nginx-box model (`deploy/nightly-build.sh`) rather than introducing a second refresh path that could race with it. Concretely: a new `--pitch-quality` flag (or unconditional new stage, TBD at implementation time) inside the existing `run_monthly.py` invocation, gated behind the same pytest publish gate.

## Cache strategy

This research's pilot already established a caching convention worth carrying forward: raw per-game API responses cached by `gamePk`, resumable, never re-fetched once present (`scripts/pull_game_feeds.py`). In production this becomes the module's persistent cache, not a throwaway pilot artifact — but needs a real retention/eviction policy (unlike the pilot, which never deletes anything), sized against `prospect-tracker`'s existing `.cache/` + `actions/cache` (7-day idle eviction) conventions.

## Archive strategy

`milb_pitcher_ewar` has **no archive/snapshot directory at all** (a documented gap since Phase 1A, `milb-projections/KNOWN_GAPS.md`) — this research's modules should not repeat that gap. Follow `pitcher_ewar`'s (the MLB stack's) pattern instead: a frozen, checksummed snapshot directory plus a dated `archive/` of prior states, enabling the kind of `TRUE_HISTORICAL_SNAPSHOT` classification `TEMPORAL_INTEGRITY.md` requires for any future walk-forward evaluation.

## Publication

Follows `PUBLICATION_ARCHITECTURE.md`'s gates directly — a module only publishes once it clears its reliability/stabilization threshold for a given pitcher, using the existing `rsync` + `deploy/publish_paths.txt` manifest mechanism (not a new publish path), with the same pytest-gate-blocks-a-bad-publish discipline already proven in `deploy/nightly-build.sh`.

## Versioning

Reuse `milb-projections`' `model-name-X.Y.Z` convention (e.g. `pitch-quality-stuff-1.0.0`) and `prospect-tracker`'s `model_registry.json` freshness-stamp pattern (`last_checked`, `stale`, `artifact_age_days`) rather than inventing a third versioning scheme.

## Rollback procedures

Directly modeled on the documented July 2026 incident (`deploy/README.md`) that led to `EEPHUS_CI_PUBLISH` being off by default: any refresh of this research's modules must be able to roll back to the immediately-prior published state without a cold rebuild, since (per that incident) a cold rebuild has already once regressed live production numbers. Concretely: this research's modules' published JSON should be included in the same archive/snapshot mechanism recommended above, so a rollback is "restore yesterday's file," not "recompute from scratch."

## Observed evidence / Inference / Speculation

The cadence and infrastructure-reuse recommendations are Inference built on `CURRENT_ECOSYSTEM_MAP.md`'s observed facts about `run_monthly.py`, `deploy/nightly-build.sh`, and the documented July 2026 incident. No new refresh mechanism is proposed anywhere in this document — every recommendation reuses an already-observed, already-working pattern.

## Future work

The exact flag/stage name for wiring this research into `run_monthly.py` is an implementation detail properly decided at implementation time, not architecture time — flagged here as the concrete next step, not resolved.
