# Information Content Report — Phase 1B

Answers Phase 1B's Question 1 ("what baseball information is actually present — not merely fields, information") and Deliverable 1. Phase 1A established field *presence*; this report establishes whether presence translates to usable information, using the full Phase 1B dataset: 408,606 pitches, 2,524 distinct pitchers, 4 levels, built from 1,402 cached games (`data_cache/derived/pitch_dataset.parquet`; per-level breakdown in `scripts/phase1b/build_pitch_dataset.py`'s run log).

## Observed evidence

**Presence** (extends Phase 1A's venue-level finding to the pooled dataset): `tracked_share` by level — AAA 99.99%, AA 0.00%, High-A 0.00%, Low-A 80.34% (the Phase 1B sample deliberately over-weights the 10 tracked Low-A venues relative to Phase 1A's flatter venue-coverage sample — see `DECISION_LEDGER.md`). Outcome fields (`call_description`, count, batter/pitcher handedness, player IDs) are present at 100% of pitches regardless of tracking, at every level.

**Completeness within tracked venues**: not literally 100% even where tracking exists. `avg_spin_rate` reliability is computed over slightly fewer pitchers than `avg_start_speed` at both AAA (820 vs. 822) and Low-A (395 vs. 398) — spin is measured less completely than velocity even at fully-tracked venues, consistent with Phase 1A's single-venue finding (The Ballpark at America First Square: 68.9% spin coverage vs. 99.9% velocity).

**Precision**: velocity/movement/spin fields carry real decimal precision (not rounded/bucketed) — `pitchData.coordinates`/`breaks` fields in the raw feed show values like `pfxX: -0.9858...`, not integers. No evidence of precision loss.

**Temporal stability** (of the *field itself*, not the pitcher trait it measures — see `NOISE_AND_STABILITY_REPORT.md` for trait stability): Phase 1A already established coverage is all-or-nothing per venue and stable within the 2025 season (no venue was "mixed" across early/mid/late samples). Phase 1B's deeper per-venue sampling (up to 30 games/venue vs. 3) is consistent with that — tracked-share by level didn't fragment into partial values, it stayed near 0% or near 100%/80%.

**Predictive information** (does the field predict anything beyond itself): established per-metric in `RELIABILITY_STATS.json` and `VARIANCE_STATS.json`. Headline: velocity/spin/movement fields carry substantial pitcher-level predictive information (split-half reliability 0.91–0.99, between-pitcher ICC 12–35%). Outcome-derived fields (whiff/called-strike/swing/in-play/foul) carry much less at the single-pitch grain (between-pitcher ICC 0.1–1.5% — see `VARIANCE_DECOMPOSITION.md` for why this isn't a contradiction of the moderate season-aggregate reliability).

**Potential leakage**: none identified in the fields used here. All extracted fields (`scripts/phase1b/build_pitch_dataset.py`) are pre-outcome or same-pitch descriptors (pitch physics, count state, call result) — no field encodes information from a later point in the game or season. `game_date`/`season_third` are used only for temporal splitting, not as features.

**Measurement source**: the public MLB Stats API's live-feed endpoint (`/api/v1.1/game/{gamePk}/feed/live`) — the same endpoint used throughout Phase 1A. No secondary tracking-provider metadata (e.g. Hawkeye vs. TrackMan install identity) is exposed in this feed, so *which* vendor/system produced a tracked pitch's numbers can't be distinguished from this data source alone.

**Measurement uncertainty**: not directly reported by the feed (no per-pitch confidence interval on `startSpeed`, etc., beyond the `typeConfidence` field on pitch-type classification, which itself is only present when tracking exists). Uncertainty here is inferred indirectly, via reliability/variance analysis, not read from the source.

## Inference

- The presence/absence boundary from Phase 1A (venue-driven) is the dominant determinant of information content — a field being "present" at a venue is close to binary (tracked venues: ~99-100% complete on core fields; untracked: 0%), so there isn't a large "partially informative" middle ground to characterize field-by-field beyond the spin-rate exception noted above.
- Outcome fields being present everywhere but only weakly predictive at the pitch grain (Question 1's "information," not just "fields") means the real information-content story is less about presence and more about **stability at the pitcher-aggregate grain**, which is `NOISE_AND_STABILITY_REPORT.md`'s subject, not this report's alone — the two are complementary, per the charter's own five-part decomposition (Question 1 vs. Questions 3-5).

## Speculation

- The spin-rate completeness gap (measured, real) may reflect a genuine measurement-difficulty difference between vendors/hardware generations rather than a data-pipeline artifact — this pilot cannot distinguish those two explanations, since vendor identity isn't exposed in the public feed.

## Future work

- Cross-reference specific tracked venues against known public installation timelines (Trackman vs. Hawkeye) to explain the spin-completeness gap, if that information becomes available from a source outside the MLB Stats API.
- A dedicated missingness-mechanism study (MCAR/MAR/MNAR) for the spin-rate gap specifically, since it's the one field showing partial (not all-or-nothing) completeness even within tracked venues.
