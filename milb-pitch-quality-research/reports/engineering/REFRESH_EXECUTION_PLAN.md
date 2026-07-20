# Refresh Execution Plan

Phase 5. Concrete execution ordering, building on `reports/architecture/REFRESH_ARCHITECTURE.md`'s cadence recommendations.

## Execution order (within a single daily run)

1. Tracking-status gate check (cheap — reuses the seasonal-cadence classification, not recomputed daily; a no-op most days).
2. Raw pull (`scripts/pull_game_feeds.py`-equivalent, incremental — only new `gamePk`s since last run).
3. `pitch_dataset_v2` rebuild (incremental append, not full rebuild — a real engineering change from this research's pilot script, which always rebuilt from the full cache).
4. Module 1 (Physical Stuff) and Module 2 (Arsenal) — parallelizable with each other (independent outputs, same input, per `MODULE_INTERACTION.md`'s confirmed no-circular-dependency finding).
5. Module 3a/3b/6 (Miss-Inducing Ability variants) — depends on Modules 1-2 as covariates for the tracked variant; the outcome-only variant (3b/6) has no such dependency and could run in parallel with step 4, not after it.
6. Module 4 (Ground-Ball) — depends on Module 1's movement output as a covariate; can run parallel to Module 3.
7. Reliability/stabilization indicators recomputed last, over the full current-season sample (not incrementally — a reliability coefficient isn't meaningfully computed on just today's increment).

## Caching

Reuses the pilot's proven per-`gamePk` cache convention (`scripts/common.py`'s `cache_path`), promoted to a production retention policy: keep the current season's raw cache indefinitely (cheap, and needed for any reliability recomputation), evict prior seasons' raw cache after their derived artifacts are archived (per the archive strategy below) — mirroring `prospect-tracker`'s `actions/cache` 7-day-idle-eviction pattern but at a season, not a run, grain, since this research's raw cache is much larger and less frequently re-read than `prospect-tracker`'s.

## Parallelization

Steps 4 and 6 (Modules 1-2, and independently Module 4) can run in parallel; step 5's outcome-only variant (3b/6) can also run in parallel with step 4. Steps 3 and 7 are strictly sequential (rebuild before anything reads it; reliability after everything else). This ordering was derived directly from `MODULE_INTERACTION.md`'s confirmed-DAG finding — no module here has a circular dependency that would force different ordering.

## Publication order

Follows the existing `deploy/nightly-build.sh` pattern exactly: pipeline stages (above) → `build_site.py` → pytest gate → `rsync` per `deploy/publish_paths.txt`. This research's modules are new stages appended to the existing pipeline, not a parallel publish path (per `REFRESH_ARCHITECTURE.md`'s "no parallel systems" instruction).

## Rollback strategy

If the pytest gate fails after this research's modules run, the existing `deploy/nightly-build.sh` behavior already prevents publish (nothing rsyncs). If a bad value *does* publish (a schema-valid but substantively wrong value — the pytest gate wouldn't catch this), rollback means restoring yesterday's `data/physical_stuff.json` (etc.) from the archive mechanism recommended in `REFRESH_ARCHITECTURE.md` — a file-level restore, not a recomputation, matching the lesson from the documented July 2026 incident (`CURRENT_ECOSYSTEM_MAP.md`).

## Failure isolation

A failure in Module 4 (say, a batted-ball-volume edge case) should not block Module 1 from publishing — each module's pipeline stage should fail independently and report its own status, not share a single try/except boundary with every other module. This is a real engineering requirement this plan introduces (not established by prior charters), motivated directly by the DAG structure confirmed in `MODULE_INTERACTION.md`: since modules aren't circularly dependent, there's no correctness reason for their failure handling to be coupled either.

## Recovery strategy

Resume from the last successfully cached `gamePk` (already a proven pattern from the research pilot's resumable puller) — no module needs a bespoke recovery mechanism beyond what `scripts/pull_game_feeds.py`'s skip-if-cached logic already demonstrated works.

## Cadence summary

| Layer | Cadence |
|---|---|
| Tracking-status gate | Seasonal, manual-override path |
| Raw pull, `pitch_dataset_v2` rebuild | Daily |
| Modules 1, 2, 3a, 3b/6 | Daily |
| Module 4 | Weekly (once promoted past research-only) |
| Module 5 | Not scheduled — on-demand research use only |
| Reliability/stabilization recompute | Daily (cheap relative to the pull itself) |
| Archive/snapshot | Seasonal (end-of-season freeze, matching `pitcher_ewar`'s pattern per `REFRESH_ARCHITECTURE.md`) |

## Observed evidence / Inference / Speculation

The execution-order and parallelization claims are Inference built directly on `MODULE_INTERACTION.md`'s confirmed dependency structure (Observed evidence). The specific caching/rollback mechanisms are Inference extending already-observed `prospect-tracker` conventions to this research's larger-scale raw cache — not yet tested at production scale.

## Future work

Actual implementation of incremental (not full-rebuild) `pitch_dataset_v2` construction is a real engineering task not yet started — the research pilot's script always rebuilds from the full cache, which won't scale to a daily-refresh production cadence without this change.
