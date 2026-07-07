# WS-R: run_monthly runtime cuts + d5e gamelogs wiring

Reference for the final before/after Day-2 pipeline comparison. All second
figures are the MEASURED baseline (TOTAL WALL 52m49s = 3169s).

## Measured baseline (slowest steps)

| step | measured | WS-R action |
|------|---------:|-------------|
| 3a-ii. Positional versatility (fielding) | 437s | R-VERS: 7-day whole-artifact freshness gate |
| 6b4b. gmLI consistency lab (subprocess)  | 271s | R2: 30-day eval-artifact cadence gate |
| d9. Rebuild timeseries (chained)         | 244s | KEEP (by design: final eFV regen) |
| 6b4c. reliever lab (subprocess)          | 185s | R2: 30-day cadence gate |
| d5d. Incremental Statcast (chained)      | 167s | R1: skipped when chained (monthly 3d-ter just ran) |
| 6b4h. Leverage Leaderboards (export)     | 145s | KEEP (leaderboard export) |
| 6b4d. bullpen history (export)           | 128s | KEEP (leaderboard export) |
| d5c. Current-season stat lines (chained) |  68s | R1: skipped when chained (monthly 3a/3b just ran) |
| 6b4g-lab. hitter lab (hem + xhem)        |  47s | R2: 30-day cadence gate (both sub-labs) |

Also gated by R2 (not in the slow list, small measured cost): 6b4e starter
lab (sem_plus). 2b bulk draft / 2b.v pools / d7 / d2 came in small on the warm
cache; the R3 draft-window trim was judged not worth the churn and is skipped.

## Expected per-item savings vs the measured table

Two savings classes:

- UNCONDITIONAL (fires on every monthly run):
  - R1 chained d5c + d5d dedupe: 68s + 167s = **235s** off the chained-daily
    tail. main() calls run_daily(chained=True); those two steps were pure
    duplication of the monthly 3a/3b (statlines) + 3d-ter (Statcast) passes
    that ran minutes earlier in the SAME process. Standalone `--daily`
    (chained=False) is byte-for-byte unchanged.

- CONDITIONAL on artifact freshness (fires only when the output is already
  recent; skips redundant RE-derivation, never the first build of a cadence):
  - R2 eval-lab gates (30-day): leverage 271s + reliever 185s + hitter 47s =
    **503s** when all three are fresh (+ the small starter-lab cost). The
    leaderboard EXPORTS they feed (6b4, 6b4d, 6b4f, 6b4g, 6b4h) still run
    every run; only the slow re-validation is gated. EEPHUS_LABS=1 forces.
  - R-VERS gate (7-day): **~437s** when positions_played.json is fresh (task
    target ~400s). versa is season-cumulative fielding G/GS that barely moves
    day to day. --force / EEPHUS_FULL=1 override.

Gross conditional + unconditional cut when the gates fire:
235 + 503 + 437 = **1175s ~= 19.6 min ~= 37%** of the 3169s baseline (matches
the target).

## New cost: d5e gamelogs

`tools/build_leaderboard_gamelogs.py` was wired into nothing; the committed
`data/leaderboard_gamelogs.json` had gone stale (Jun 16). New run_daily step
d5e (after d5d, runs when chained=True too) rebuilds it in-process for the top
**200** prospects by overall_rank, REUSING the feed cache the d5d Statcast scan
just primed (same `statcast_metrics._game_logs` feed). Soft **210s** budget: on
a cache-miss storm the remainder is skipped and a partial slice is written
(fail-open; the frontend staleness notice covers gaps).

- Estimated warm cost (most of the top-200 at Statcast-tracked levels, cache
  primed by d5d): ~60-120s.
- Hard ceiling: the 210s soft budget.

Net expected cut on the FINAL Day-2 run (all lab + versa artifacts are fresh
because today's baseline run just regenerated them):
3169 - 1175 (cuts) + ~120 (d5e) ~= **2114s ~= 35 min**, a ~17.5 min / ~33% net
reduction vs 52m49s.

Note on conditions: on a genuinely COLD monthly run (30+ days since the last
full, e.g. a rebuild after a long gap), the lab gates and versa gate do NOT
fire (artifacts stale) and the run returns toward baseline plus d5e. That is
intended: WS-R removes redundant re-derivation, not first builds.

## GRPO decision: LEFT ALONE (no retrain_grpo knob threaded)

`grpo_prospect.export_grpo_scores(retrain=True)` (called by rebuild_only, which
run_daily chains via d9) ALREADY elides the redundant monthly->daily retrain
via a training-data fingerprint (grpo_prospect.py `_training_fingerprint` +
the reuse branch in `export_grpo_scores`): training is deterministic, so when
the graduate set is byte-identical to the saved model's fingerprint it reuses
the saved model and skips the refit, output-neutrally.

Threading `retrain=False` from chained runs would be strictly WORSE, not
better:
1. No real savings: the fingerprint reuse already makes the chained retrain a
   near-zero load-and-score when the graduate set is unchanged.
2. Correctness risk: when the daily d7 debut/graduation pass legitimately
   changes the graduate set, retrain=True + fingerprint retrains on the NEW
   data (correct), whereas retrain=False would score against a STALE model.

The existing fingerprint mechanism is the superior, data-driven form of the
same dedupe, so GRPO is left untouched.
