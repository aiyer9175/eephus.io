# The pooled outcome refit: pre-registration and results

Lane: LANE-P2. Phase 2 (POOLED variant) + Phase 3.2 (the A2 history repoint) of
`docs/master-plan-2026-07-30-fv-calibration.md`. Gate standard: `docs/EFV_GATE_STANDARD.md`.
Phase-1 input: `docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md` + `data/fv_outcome_curves.json`.
New artifact: `data/fv_outcome_curves_pooled.json`. Registry row: `fv_outcome_pooled_grade`.

**PART 1 was written and committed to disk BEFORE any production module was edited.**
PART 2 is appended after. This lane CHANGES A SERVED NUMBER (`xfv_grade`, and therefore the
board ordering), which is why the stop conditions in 1.5 are written first.

---

# PART 1. Pre-registration

## 1.0 The owner decision this lane implements, and what it excludes

Phase 1 fit per-side FV-to-outcome curves and ran a nine-candidate bake-off. Its own
pre-registered reject criteria fired: **the side split is a measured NULL against its own
zero-information control** (side-label-permuted training is +0.043 MAE BETTER on hitters and
-0.007 on pitchers, both inside the gate standard's MAE MDE95; the slope advantage CI90
straddles zero on both sides), it does not beat a pooled refit of the same data on both
sides, and the entire top-100 pitcher move 6 -> 17 is attributable to the split and to
nothing else (a pooled curve reproduces the incumbent board at 6 -> 8).

Exactly one contest in the whole bake-off cleared its floor with a CI excluding zero:
**refitting the WAR-to-grade map on RESOLVED OUTCOMES beats the shipped anchor on hitter
calibration slope, 1.001 vs 1.453, d |slope-1| -0.452 CI90 [-0.519, -0.114].** That result
is available with or without the side split.

The owner therefore chose the **POOLED outcome refit only**. This lane does NOT ship the
side split, does NOT re-run the bake-off, and does NOT re-litigate Phase 1.

## 1.1 What ships

1. **`data/fv_outcome_curves_pooled.json`** - the pooled (side-neutral) curve
   `E[first-6yr total bWAR | consensus FV]`, fit by exactly the Phase-1 pipeline on the
   POOLED primary pool (hit + pit uncensored, n = 3,037), with per-knot `n_cell`,
   `w_prior`, the Clemens per-side prior averaged 50/50 as the pooled prior, and
   player-clustered bootstrap CI90 bands. This is the same object the Phase-1 lab already
   computed for its `empirical_pooled` bake-off arm and for the pooled column of the
   board-mix table; it was never persisted, so this lane persists it and pins it with a
   content hash. Produced by `tools/fv_outcome_curve_pooled.py`, which imports the Phase-1
   lab rather than re-implementing it.
2. **`value_framework.outcome_implied_fv(war)`** - the inversion of that curve. Strictly
   increasing by construction (Phase 1 forces a +0.01 WAR minimum per knot step), so the
   inverse is single-valued; clamps to [20, 80].
3. **`efv_score`** uses it for `xfv_grade` on all three scoring paths (`run`, `run_live`,
   `run_backgrade`), replacing `value_framework.realized_implied_fv`. All three flip
   together: `data/xfv.json` carries active, debuted and bust rows in one file, and leaving
   two of them on the retired map would create exactly the third-basis defect Phase 3.2 is
   here to close.
4. **`efv_score.score_history`** grades each historical snapshot through the same function
   (Phase 3.2, the A2 repoint), replacing the retired per-side quantile map.
5. **Coordinated ship mechanics**: `storage.BOARD_RANK_BASIS_EPOCH` -> 2026-07-30,
   `storage.BOARD_BASIS_FINGERPRINT` restamped, `storage.board_basis_fingerprint()`
   EXTENDED to name the outcome-curve content hash (the grade scale is now part of the
   board's identity and the incumbent fingerprint would not notice a curve change), and
   `PINNED_MIX` re-recorded if the measured mix breaches its tolerance band.

## 1.2 The low end stays as it is, and is NOT outcome-calibrated

The measured curve is nearly flat below FV 45 (pooled: 0.069 total WAR at FV35, 0.453 at
FV40) and **71% of live board rows sit below the data floor** (the pool has no row under
consensus FV 34.9). Inverting a flat curve there is a near-vertical jump, so the outcome
basis carries no FV 20-45 display granularity of its own.

Phase 1 therefore shipped the sub-floor knots as the PRODUCTION concave re-spread,
`value(fv) = value(35) * ((fv - 20) / 15) ** (1 / 0.45)`, the exact inverse of
`value_framework._LOWEND_FG_EXP = 0.45`. Keeping the existing low-end behaviour is
consequently a NO-OP against the curve rather than a departure from it. This lane keeps it.

**A grade below about 45 is a display re-spread, not an outcome-calibrated number, and must
never be presented as one.** This is stated in the code comment at the inversion, in the
artifact, and here.

## 1.3 What this lane deliberately does NOT re-key: the outcome odds

`p_bucket` and `p_bust` are produced by `vf.p_bucket_given_fv(xfv_grade)` /
`vf.sv_distribution(xfv_grade)`. They would move if they followed the new grade.

They are PINNED to the retired `realized_implied_fv` grade, computed alongside the new one
as `_odds_grade`. Reasons, in order:

1. They are validated, ground-truthed probabilities. `_reprice_surplus_on_display`'s
   standing rule already says so in its docstring: the display re-pricing never touches the
   odds because "they are probabilities, not a dollar value, and were ground-truthed on that
   basis." Re-keying them is an UNMEASURED change to a validated number, and this commit's
   gate was measured on calibration slope, not on odds.
2. Pinning them makes the blast radius of this ship exactly `xfv_grade`,
   `xfv_minus_consensus` and the board ORDERING - which is what the owner asked to move.
3. The coherence cost is real and is registered as a follow-up, not hidden: the board grade
   and the odds now key off two different maps of the same predicted WAR. The counterfactual
   magnitude of re-keying is MEASURED and reported in PART 2 so the owner can call it.

## 1.4 What this lane measures

1. **Surplus byte-identity.** The claim under test: surplus prices off the per-side rank
   quantile (`xfv_grade_display`, a rank-preserving map of `rank_war`, which does not read
   `xfv_grade`), so served surplus must be BYTE-IDENTICAL. Method: capture all three
   scoring paths for both sides into a scratch directory BEFORE the code change and again
   AFTER, on identical inputs and in `efv_export.regen_all`'s order with the real artifacts
   seeded so the F-SIDE-FIX cross-side reads see production's inputs, then diff every field
   of every row. Reported as an exact per-field diff COUNT, not a summary statistic.
2. **Blast radius**: rows whose grade moved, mean and max |dFV| per side, ranks moved,
   the top-10/25/50/100 side mix before and after, and the ten named players.
3. **Within-side monotonicity**: order violations of `xfv_grade` against `xfv_war_6yr`
   within each side (Phase 1 measured 0 on 4,520 live rows; re-measured here on the rows
   this lane actually produces).
4. **History repoint**: how far the repointed history tail sits from the board grade, and
   what remains (the tilt and vintage difference `score_history` has always carried).

## 1.5 What would make this lane STOP and not ship

Written before the code change. Any one of these is a STOP-and-report, not a re-frame:

1. **Surplus is not byte-identical.** Any row whose `surplus_mm`, `band_p10_mm`,
   `band_p90_mm` or `dist.*` dollar field differs by any amount. This is the plan's own
   shippability condition (2.2) and the owner's explicit instruction.
2. **The odds move.** Any row whose `p_bucket` or `p_bust` differs, given the 1.3 pinning.
   A difference means the pinning is not actually in force.
3. **The row set changes.** Any player graded before and ungraded after (or the reverse) on
   any path. The inversion must never return None where the old one returned a number.
4. **Monotonicity fails.** Any within-side order violation of the new grade against
   `xfv_war_6yr`. The whole surplus-neutrality argument rests on this.
5. **A named player moves more than 10 FV, or the top-100 pitcher count passes 40.**
   Phase 1's C6 tripwire, carried forward unchanged. Phase 1's pooled column predicts a mix
   of 92 H / 8 P at the top 100, so a large pitcher move would mean the pooled curve is not
   what was measured.
6. **The pooled curve this lane persists does not reproduce Phase 1's.** The persisted
   curve must reproduce the pooled board mix Phase 1 recorded (top100 92 H / 8 P) on the
   same live artifact. If it does not, the fit is not the one the owner approved.

## 1.6 Movement-engine suppression: what is actually at risk

`storage.load_rank_history`'s strictly-after `BOARD_RANK_BASIS_EPOCH` gate covers
`metric_snapshots.overall_rank` - the rank-movement signal and the rank-trend arrow. Bumping
the epoch therefore covers the board RE-ORDERING this lane causes, which is the Seth
Hernandez defect class.

It does NOT cover the eFV-DELTA signal (`movement.xfv_movement`), which reads
`data/xfv_history.json` through `storage._xfv_series` and never touches
`metric_snapshots`. That is checked, and the honest finding plus whatever suppression it
needs is reported in PART 2 rather than assumed here.

## 1.7 Scope limits

No pytest run (a concurrent lane edits the tree; conftest git-checkouts files dirtied during
a run). No exporter, `run_monthly`, `build_site`, scraper, matrix rebuild or artifact regen:
every measurement is a `persist=False` / scratch-redirected in-memory scoring run on the
committed inputs. `data/xfv.json`, `data/xfv_history.json` and every other served artifact
are left exactly as the nightly box wrote them; the golden restamp owed on
`test_efv_export.py::test_xfv_golden_fingerprint` can only come from a production
`efv_export.py --all` on the box and is NOT taken here.

---

# PART 2. Results

Appended after the measurement. Baseline captured 2026-07-30 BEFORE the first code edit.

## 2.0 The persisted pooled curve

`data/fv_outcome_curves_pooled.json`, produced by `tools/fv_outcome_curve_pooled.py`, which
imports `tools/fv_outcome_curves_lab.py` and calls the same `fit_war_curve` on the same
pooled primary pool with the same 50/50-averaged Clemens prior. n = 3,037 uncensored rows
(1,500 hit + 1,537 pit), data floor consensus FV 35.0, max 70.0.

| FV | n_cell | w_prior | cell mean | isotonic | prior | **VALUE** | CI90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | 0 | - | - | - | - | **0.000** | sub-floor policy |
| 25 | 0 | - | - | - | - | **0.006** | sub-floor policy |
| 30 | 0 | - | - | - | - | **0.028** | sub-floor policy |
| 35 | 694 | 0.041 | 0.038 | 0.035 | 0.236 | **0.069** | 0.043 - 0.128 |
| 37.5 | 353 | 0.078 | 0.078 | 0.092 | 0.275 | **0.106** | 0.073 - 0.235 |
| 40 | 1212 | 0.024 | 0.410 | 0.448 | 0.650 | **0.453** | 0.334 - 0.531 |
| 42.5 | 189 | 0.137 | 1.059 | 0.799 | 1.100 | **0.840** | 0.660 - 1.222 |
| 45 | 274 | 0.099 | 2.289 | 2.289 | 2.050 | **2.265** | 1.860 - 2.639 |
| 47.5 | 36 | 0.455 | 3.746 | 3.811 | 2.900 | **3.397** | 2.909 - 3.727 |
| 50 | 116 | 0.205 | 5.474 | 5.454 | 6.000 | **5.566** | 4.899 - 6.176 |
| 52.5 | 33 | 0.476 | 7.095 | 6.930 | 6.750 | **6.844** | 6.269 - 7.297 |
| 55 | 82 | 0.268 | 7.201 | 7.267 | 7.500 | **7.330** | 6.694 - 8.032 |
| 57.5 | 8 | 0.789 | 7.894 | 7.707 | 9.625 | **9.221** | 8.795 - 9.606 |
| 60 | 23 | 0.566 | 10.211 | 9.889 | 11.750 | **10.942** | 10.041 - 11.687 |
| 62.5 | 2 | 0.938 | 7.435 | 11.889 | 12.625 | **12.579** | 12.223 - 12.796 |
| 65 | 12 | 0.714 | 13.055 | 13.055 | 13.500 | **13.373** | 12.799 - 13.966 |
| 67.5 | 2 | 0.938 | 27.875 | 27.875 | 20.375 | **20.844** | 20.386 - 21.435 |
| 70 | 1 | 0.968 | 47.540 | 47.540 | 27.250 | **27.473** | 27.250 - 27.930 |
| 75 | 0 | 1.000 | - | 47.540 | 27.250 | **27.483** | prior only |
| 80 | 0 | 1.000 | - | 47.540 | 27.250 | **27.493** | prior only |

Monotone-repair max knot move 0.4315 WAR, inside Phase 1's own 0.5 threshold (C5).

Say it as plainly as Phase 1 did: **the top of this curve is not a measurement.** From FV
57.5 up the pooled cell n is 8 / 23 / 2 / 12 / 2 / 1 and `w_prior` runs 0.57 to 0.97, so
those knots are the Clemens 2026 table with a little of our data mixed in. The FV70 cell is
one player (Mike Trout, 47.54 realized) and the shrinkage exists precisely to stop one career
from becoming a scale. Below FV 35 there is no data at all and the values are the concave
display re-spread of 1.2.

Content hash (SHA-1 over the knot/value pairs at 6dp, the identity the board fingerprint
names): `POOLED_HASH`.

## 2.1 STOP conditions, scored

`SCORED_STOPS`

## 2.2 Surplus byte-identity

`SURPLUS_PROOF`

## 2.3 Blast radius

`BLAST_RADIUS`

## 2.4 The ten named players

`NAMED_PLAYERS`

## 2.5 Board side mix

`SIDE_MIX`

## 2.6 The history repoint (Phase 3.2)

`HISTORY`

## 2.7 The movement question, answered

`MOVEMENT`

## 2.8 What argues against shipping

`AGAINST`
