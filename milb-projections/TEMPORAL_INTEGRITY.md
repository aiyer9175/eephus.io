# Temporal Integrity

Status: scaffolded in Phase 2; full snapshot-by-snapshot audit completed in Phase 7 (`reports/HISTORICAL_SNAPSHOT_AUDIT.md`). This document carries the standing rules; the audit report carries the per-asset classification.

## The core risk

The future MiLB pitch-quality model will be evaluated, in part, by comparing its predictions to Eephus benchmarks (pitcher eWAR, park factors, identity/level). If any benchmark row contains information that would not have been available at the row's nominal "as of" time, a walk-forward evaluation using that benchmark silently leaks the future into the past and overstates the challenger's (or the champion's) apparent skill.

## Standing rules

1. **No row in any export carries information from after its stated `as_of_date`/season without that being explicitly labeled.** Where an export is a current-model backfill (i.e., today's model applied retroactively to historical seasons) rather than a genuine point-in-time historical forecast, it is labeled `CURRENT_MODEL_BACKFILL`, never `TRUE_HISTORICAL_SNAPSHOT`.
2. **Neither Eephus identity system supports true effective-dated joins today.** `eephus_identity.parquet` is current-state only (one row per player, last-write-wins); the team/affiliate/park mapping is season-grain, not date-grain, and isn't joined to player identity anywhere in the codebase. Any join that assumes "the team/level a player was on as of date X" is not something these systems can honestly answer — this is a hard limitation, not an edge case, and it is documented here rather than worked around with an invented join.
3. **A current-model backfill may be used for descriptive comparison ("how would today's metric have rated 2022"), never represented as what a real-time system would have produced in 2022.**
4. **Restatements are not backfills.** The MiLB pitcher eWAR v1.1.0 restatement (park-factor correction) is a genuine, ledgered before/after diff (`MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet`) of a real methodology fix applied to real historical rows — it changes what the historical value *is*, and is labeled `RECONSTRUCTED_AS_OF` with the ledger kept as the audit trail, not silently overwritten.
5. **No feature or benchmark export may embed information from a later season/date into an earlier row.** Where this cannot be verified (e.g., because a source system doesn't stamp per-row `as_of_date`), the export is marked `UNKNOWN` in the historical-status audit rather than assumed safe.

## Per-asset classification

See `reports/HISTORICAL_SNAPSHOT_AUDIT.md` (Phase 7) for the row: `TRUE_HISTORICAL_SNAPSHOT | SEASON_END_DESCRIPTIVE | CURRENT_MODEL_BACKFILL | RECONSTRUCTED_AS_OF | UNKNOWN` classification of every benchmark asset, plus earliest/latest snapshot, update cadence, and allowed use.
