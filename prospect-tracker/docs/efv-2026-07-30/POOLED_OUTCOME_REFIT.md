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
| 20 | 0 | 1.000 | - | -0.007 | 0.000 | **0.0000** | sub-floor policy |
| 25 | 0 | 1.000 | - | -0.007 | 0.079 | **0.0060** | sub-floor policy |
| 30 | 0 | 1.000 | - | -0.007 | 0.157 | **0.0281** | sub-floor policy |
| 35 | 694 | 0.041 | 0.038 | 0.035 | 0.236 | **0.0692** | 0.048 - 0.144 |
| 37.5 | 353 | 0.078 | 0.078 | 0.092 | 0.275 | **0.1063** | 0.079 - 0.354 |
| 40 | 1212 | 0.024 | 0.410 | 0.448 | 0.650 | **0.4529** | 0.288 - 0.506 |
| 42.5 | 189 | 0.137 | 1.059 | 0.799 | 1.100 | **0.8403** | 0.618 - 1.407 |
| 45 | 274 | 0.099 | 2.289 | 2.289 | 2.050 | **2.2651** | 1.845 - 2.682 |
| 47.5 | 36 | 0.455 | 3.746 | 3.811 | 2.900 | **3.3971** | 2.582 - 4.031 |
| 50 | 116 | 0.205 | 5.474 | 5.454 | 6.000 | **5.5659** | 4.790 - 6.298 |
| 52.5 | 33 | 0.476 | 7.095 | 6.930 | 6.750 | **6.8444** | 5.925 - 7.590 |
| 55 | 82 | 0.268 | 7.201 | 7.267 | 7.500 | **7.3295** | 6.488 - 8.352 |
| 57.5 | 8 | 0.789 | 7.894 | 7.707 | 9.625 | **9.2213** | 8.748 - 9.848 |
| 60 | 23 | 0.566 | 10.211 | 9.889 | 11.750 | **10.9423** | 10.139 - 12.043 |
| 62.5 | 2 | 0.938 | 7.435 | 11.889 | 12.625 | **12.5790** | 12.236 - 12.691 |
| 65 | 12 | 0.714 | 13.055 | 13.055 | 13.500 | **13.3729** | 12.423 - 14.698 |
| 67.5 | 2 | 0.938 | 27.875 | 27.875 | 20.375 | **20.8438** | 20.375 - 21.652 |
| 70 | 1 | 0.968 | 47.540 | 47.540 | 27.250 | **27.4730** | 27.250 - 27.905 |
| 75 | 0 | 1.000 | - | 47.540 | 27.250 | **27.4830** | prior only |
| 80 | 0 | 1.000 | - | 47.540 | 27.250 | **27.4930** | prior only |

Monotone-repair max knot move 0.4315 WAR, inside Phase 1's own 0.5 threshold (C5).

Read the FV80 row against FACT 2 in the plan: the retired map put FV80 at 20.4 WAR over six
years, this curve puts it at 27.49. The top of the grade scale got HARDER, which is the
mechanism behind the hitter deflation reported in 2.4 and is the opposite of the direction
the plan's Caden Hunter narrative predicted.

Say it as plainly as Phase 1 did: **the top of this curve is not a measurement.** From FV
57.5 up the pooled cell n is 8 / 23 / 2 / 12 / 2 / 1 and `w_prior` runs 0.57 to 0.97, so
those knots are the Clemens 2026 table with a little of our data mixed in. The FV70 cell is
one player (Mike Trout, 47.54 realized) and the shrinkage exists precisely to stop one career
from becoming a scale. Below FV 35 there is no data at all and the values are the concave
display re-spread of 1.2.

Content hash (SHA-1 over the knot/value pairs at 6dp, the identity the board fingerprint
names): **`6dbe8353f3bb`**. `storage.BOARD_BASIS_FINGERPRINT` is now
`xfv_grade|scale=off|grademap=outcome_pooled@6dbe8353f3bb`.

## 2.1 How the measurement was taken, and one correction to how it was taken first

Both captures run `efv_score.run`, `run_live` and `run_backgrade` for both sides, in
`efv_export.regen_all`'s order, with every writer redirected to a scratch directory and the
four real scored artifacts seeded first so the F-SIDE-FIX cross-side reads see production's
inputs. Nothing under `data/` was written. 13,201 rows across the five artifacts.

The first attempt captured BEFORE, edited the code, then captured AFTER as a separate
process. That is not good enough here and the tree said so: re-running the AFTER capture a
few minutes later produced a DIFFERENT artifact (jesus_made's `xfv_war_6yr` moved 11.48 to
11.49, `krp_plus` moved on 1,758 pitchers, and `realized_war` moved on 128 backgrade rows),
because the nightly box pipeline is regenerating inputs live -- 53 data files are churned
uncommitted right now. A two-process before/after diff cannot separate the code change from
that churn.

**The proof below is therefore PAIRED and single-process.** One script loads `efv_score`
TWICE: once from its own source with the three grade-map lines substituted back to the
retired call (so OLD is not a re-implementation of the old behaviour, it IS the old source),
once as shipped, and captures both back to back against one input read. Every difference
between the two is attributable to the grade map and to nothing else. The conclusions from
the sloppier first pass and this one agree to within input churn, which is itself
reassuring, but only the paired numbers are quoted here.

The captures do NOT reproduce the committed `data/xfv.json` exactly (mean |grade|
difference 0.096, max 3.9 on 4,264 shared active rows) for the same reason: that artifact
was written by the box against an earlier input vintage. That does not weaken the diff, and
it is why the board-mix claim in 2.6 is also checked directly against the served artifact.

## 2.2 STOP conditions, scored

| # | condition | result |
| --- | --- | --- |
| 1 | surplus not byte-identical | **0** differing (row, field) pairs across `surplus_mm`, `band_p10_mm`, `band_p90_mm`, `consensus_surplus_mm` and the six `dist` dollar fields, on all 13,201 rows. PASS |
| 2 | the odds move | **0** differing pairs across `p_bust`, `dist.p_bust` and all five `p_bucket` keys. PASS |
| 3 | the row set changes | asserted equal per artifact; 1,971 / 2,293 / 1,882 / 1,988 / 5,067 rows before and after. PASS |
| 4 | within-side monotonicity fails | **0** order violations of `xfv_grade` against `xfv_war_6yr` on all four scored pools. PASS, and see below |
| 5 | a named player moves > 10 FV, or top-100 P > 40 | largest named move **4.6 FV** (luis_hernandez); top-100 pitcher count unchanged at 12. PASS |
| 6 | the persisted curve is not Phase 1's | inverting each served row's `xfv_war_6yr` through it gives top10 10H/0P, top25 24H/1P, top50 47H/3P, top100 92H/8P, which is Phase 1's pooled column exactly. PASS |

**Criterion 4 did more than pass, and this is the result worth reading twice.** The RETIRED
map carried **86 hit / 52 pit** within-side order violations on the live board and **254 /
159** on the resolved pool: `realized_implied_fv` takes `age` and `position`, so two players
with the SAME predicted WAR were graded differently and the ordering could invert. The new
grade is a pure function of predicted WAR, so the count is zero by construction. The
plan's shippability argument (2.2: "within a side the new map is monotone in predicted WAR,
so surplus pricing is byte-identical") was therefore true of the NEW map and had never been
true of the old one.

## 2.3 Surplus byte-identity, and why it holds

The mechanism, read out of the code rather than assumed: `xfv_grade_display` is a
rank-preserving quantile map of `rank_war` onto the pool's consensus-FV distribution, and
`rank_war` is `(1-lambda) * cons_war + lambda * xfv_war`. Neither reads `xfv_grade`.
`_reprice_surplus_on_display` then OVERWRITES `surplus_mm`, the band and the whole `dist`
block off `xfv_grade_display` at the end of every path. So the dollars never touch the board
grade at all, and the odds were pinned to the retired map by hand (1.3).

Measured: 0 differing dollar fields and 0 differing odds fields on 13,201 rows. **Exactly
two fields move anywhere in the three artifacts: `xfv_grade` and `xfv_minus_consensus`.**

The counterfactual 1.3 promised, so the owner can price the follow-up. If the odds DID
follow the new grade: hitters' `p_bust` would move mean -0.0120, max 0.188, with 448 of
1,971 rows moving more than a point of probability; pitchers' `p_bust` mean -0.0400, max
0.185, 722 of 2,293 rows. `p_star` barely moves (hit mean -0.0012, pit +0.0002). That is a
real change to a validated number, in the direction of "everyone looks less likely to bust",
and it is not something this commit measured. It stays out.

## 2.4 Blast radius

Live board (the served surface), grade movement:

| side | rows | grades moved | up / down | mean dFV | mean abs dFV | max abs dFV |
| --- | --- | --- | --- | --- | --- | --- |
| hit | 1,971 | 457 (23.2%) | 264 / 193 | +0.518 | 0.944 | 10.70 |
| pit | 2,293 | 726 (31.7%) | 638 / 88 | +1.839 | 1.916 | 10.80 |

By incumbent grade band, which is where the shape of the change lives:

| old band | hit n | hit mean dFV | pit n | pit mean dFV |
| --- | --- | --- | --- | --- |
| under 35 | 1,641 | +0.61 | 2,000 | +1.73 |
| 35-40 | 75 | **+4.71** | 146 | **+5.00** |
| 40-45 | 76 | +1.17 | 65 | +1.59 |
| 45-50 | 89 | -1.00 | 70 | -0.81 |
| 50-55 | 40 | -3.19 | 9 | -2.10 |
| 55+ | 50 | **-3.99** | 3 | **-3.70** |

Board ranks (joint ordering on `xfv_grade`, ties by `player_key`): **1,060 of 4,264 rows
move, median |move| 4, max |move| 27.** Membership: top 100 **100 held, 0 in, 0 out**; top
50 48 held, 2 in, 2 out; top 25 23 held, 2 in, 2 out; top 10 9 held, 1 in, 1 out. For scale,
the 2026-07-25 basis flip moved ~4.46k of 4.47k rows with a median of ~417 and a max of
~3.5k. This is a re-rank, and it is two orders of magnitude smaller than the one the epoch
machinery was built for.

Distribution: the FV20 floor population is **unchanged at 3,075 of 4,264** (the curve
anchors at exactly 0.0 WAR, as the retired map did). p90 39.4 -> 43.0, p99 55.4 -> 50.9, max
64.8 -> 60.8. The board compresses at the top and lifts in the middle-low.

**The largest movers are the bottom of the board, not the top.** The twelve biggest are all
near-zero-WAR arms and bats (predicted WAR6 0.10 to 0.12) going 26.6-27.0 -> 37.2-37.6
(+10.6 to +10.8), and their ranks move by 0 to 6 spots inside a block around 1,040-1,055.
Cause, stated plainly because it qualifies section 1.2: the concave
re-spread is the same FUNCTION as before but a different DOMAIN. The retired map spread
`[0, war45 ~= 2.2]` across FV 20-45; the curve spreads `[0, value(35) = 0.069]` across FV
20-35 and then hands FV 35-45 to the measured knots. So the shape is preserved and the
anchor is not, and everything with a tiny positive prediction reads higher than it did.

## 2.5 The ten named players

`before` and `after` are the two captures on identical inputs, so these are pure map effects.

| player | side | war6 | consensus | before | after | dFV | rank | surplus |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| jesus_made | H | 11.49 | 60.1 | 64.8 | **60.8** | -4.0 | 1 -> 1 | unchanged |
| franklin_arias | H | 11.17 | 58.1 | 64.2 | **60.3** | -3.9 | 2 -> 2 | unchanged |
| leo_de_vries | H | 11.06 | 59.1 | 64.0 | **60.2** | -3.8 | 3 -> 3 | unchanged |
| kade_anderson | P | 8.12 | 57.8 | 58.8 | **56.0** | -2.8 | 15 -> 14 | unchanged |
| seth_hernandez | P | 6.71 | 58.8 | 56.3 | **52.2** | -4.1 | 29 -> 29 | unchanged |
| luis_hernandez | H | 5.70 | 49.4 | 54.9 | **50.3** | -4.6 | 55 -> 56 | unchanged |
| enrique_bradfield_jr | H | 3.93 | 45.6 | 49.5 | **48.1** | -1.4 | 111 -> 107 | unchanged |
| joseph_dzierwa | P | 3.57 | 48.7 | 48.7 | **47.7** | -1.0 | 127 -> 117 | unchanged |
| caden_hunter | P | 3.60 | 45.3 | 48.7 | **47.7** | -1.0 | 122 -> 116 | unchanged |
| roch_cholowsky | H | 10.84 | 57.5 | 62.8 | **59.9** | -2.9 | backgrade row | unchanged |

**Caden Hunter is the case the whole program was named after, and he goes the wrong way.**
The plan's FACT 2 expected him to read "48.6 today and ~50-51 against the empirical pitcher
outcome curve". He reads **47.7**, a point LOWER. His board rank still improves (121 -> 116),
because the hitters above him fall further than he does. Phase 1 found the same thing on the
per-side curve and said so; the pooled curve reproduces it. The owner's ask is delivered by
deflating the hitter top end, not by lifting pitchers, and any site copy that says otherwise
will be wrong.

## 2.6 Board side mix

| cut | OLD (paired capture) | NEW (paired capture) | served artifact | pooled counterfactual on the served artifact |
| --- | --- | --- | --- | --- |
| top 10 | 10 H / 0 P | 10 H / 0 P | 10 H / 0 P | 10 H / 0 P |
| top 25 | 24 H / 1 P | 24 H / 1 P | 24 H / 1 P | 24 H / 1 P |
| top 50 | 47 H / 3 P | 47 H / 3 P | 48 H / 2 P | 47 H / 3 P |
| top 100 | 88 H / 12 P | 88 H / 12 P | 94 H / 6 P | 92 H / 8 P |

Two readings, both needed. On IDENTICAL inputs the grade map moves the mix by **zero at
every cut**; the 12-versus-6 gap between the capture and the served artifact is the
artifact-refresh effect Phase 1 already flagged in its own section 2.9, not a basis effect.
On the SERVED artifact the counterfactual reproduces Phase 1's pooled column exactly, which
is STOP condition 6.

That the mix does not move while 1,060 ranks do is the whole point of the pooled variant.
The side split was the thing that moved pitchers; refitting on outcomes is not.

`PINNED_MIX` is therefore **deliberately not re-recorded**. It is a tolerance band, the flip
does not come near breaching it, and re-pinning on a statistic that did not move would only
discard the reading it was recorded at. The BASIS change is caught by the fingerprint, which
now names the curve hash for exactly this reason: this change re-ranked 1,051 rows while
leaving both of the fingerprint's original terms identical.

## 2.7 The history repoint (Phase 3.2)

`score_history` now grades each snapshot with `vf.outcome_implied_fv(model_war)` -- the
board's own map -- instead of mapping the guarded blend through the retired per-side
quantile scale. `rank_war` is deliberately not the argument: the board grade is a function
of the MODEL's WAR, and grading history off the consensus-guarded blend is what put it on a
different scale to begin with.

Measured on a scratch rebuild (1,576 players, nothing written to `data/`), tail versus the
new board grade:

| series | tails compared | disagree by > 0.51 FV | mean d | median abs d | max abs d |
| --- | --- | --- | --- | --- | --- |
| committed (retired quantile basis) | 1,571 | 1,443 (**91.9%**) | +6.10 | 3.80 | 23.1 |
| repointed | 1,563 | 417 (**26.7%**) | +1.03 | **0.00** | 26.3 |

franklin_arias 58.1 -> 60.1 against a board 60.4; jesus_made 59.1 -> 60.6 against 60.8;
ryan_sloan 54.8 -> 50.9 against 51.0; seth_hernandez 55.3 -> 52.5 against 52.2.

**The residual 417 is a TILT gap, not a basis gap, and it will not close.** `run_live`
applies the injury, prospect-age, Statcast and reliever-ceiling tilts and the S-XLINE lean
to `xfv_war` before grading; `score_history` has never had as-of values for any of them and
cannot invent them. Of the 417, 138 carry an injury factor and 95 have a board grade sitting
at the FV20 floor, where the curve's low end is near-vertical and a small WAR difference is
many grade points. All 417 are live-board rows; no backgrade row disagrees.

**Two honest consequences, stated rather than tidied.**

1. `data/xfv_history.json` is STILL the old artifact. It only rebuilds when `score_history`
   runs, which is a production regen on the box, and this lane must not run one. The CODE is
   repointed; the ARTIFACT is stale until the next box run.
2. `test_board_basis_coherence::test_history_series_is_on_the_board_basis` KEEPS its
   `xfail(strict=True)` marker, with a rewritten reason. Removing it was the other option and
   it was rejected: the test asserts per-row equality within 0.51 FV, so it fails today on
   the stale artifact AND will still fail after the regen on the tilt gap. A strict xfail
   whose reason states exactly that is more informative than a red. The BASIS half of the
   claim is now carried by a new test, `test_history_median_tail_is_on_the_board_basis`,
   which asserts the MEDIAN disagreement is under 0.5 FV: a basis error shifts every row
   (measured 3.80), a tilt gap shifts a minority (measured 0.00). It skips while the artifact
   is on a foreign basis and activates itself on the first regen.

## 2.8 The movement question, answered

**`load_rank_history`'s strictly-after epoch gate does NOT cover the eFV-delta signal, and
bumping the epoch alone would have left the owner's primary movement signal unguarded.**

- It DOES cover rank movement and the rank-trend arrow: those read
  `metric_snapshots.overall_rank`, append-only dated rows, filtered by
  `snapshot_date > BOARD_RANK_BASIS_EPOCH`. The bump to 2026-07-30 covers the re-rank in
  2.4. This is the Seth Hernandez defect class and it is handled.
- It does NOT reach `movement.xfv_movement`, which reads `data/xfv_history.json` via
  `storage._xfv_series` and never touches `metric_snapshots`. Nothing in the epoch machinery
  can see that file.

What is and is not at risk there, measured rather than assumed. `score_history` REBUILDS the
artifact in full every run, so a basis change rebases every point at once and there is no
within-series discontinuity of the 2026-07-25 kind. The real exposure is the window where
the file on disk was built on one basis while the board serves another -- the one-run lag
`_load_xfv_join` documents, which exists on every basis change and was unguarded on both
previous ones.

Suppression added: `score_history` stamps the artifact with
`storage.board_basis_fingerprint()`, and `storage.xfv_history_is_on_board_basis()` gates the
eFV-delta override. On a mismatch the movement headline falls back to
`compute_genuine_movement`'s consensus same-source step, which is the documented fallback
for a player with no eFV series at all, not a new code path. It clears itself on the first
regen that writes a stamped series. Right now the gate correctly reports the committed
artifact as foreign (it is unstamped), so the eFV-delta movement is suppressed until the box
regenerates.

SCOPE, deliberately narrow: the gate covers the MOVEMENT override only. The `$DvM+`
appreciation rate also reads the series and is NOT gated, because it is a within-series
first-point-to-last-point rate that stays internally consistent even on a foreign basis, and
gating it would swing `$DvM+` for the whole board for one run to fix a coherence problem
that predates this change. That is an owner call, registered here, not taken quietly.

## 2.9 What argues against shipping

1. **The strongest single argument: the measured win is a HITTER-ONLY slope result, and
   pitchers get the change anyway.** The gate is hitter calibration slope 1.001 vs 1.453,
   CI90 excluding zero. On pitchers the same contest is dMAE +0.004 CI90 [-0.011,+0.018] and
   d |slope-1| -0.078 CI90 [-0.218,+0.150] -- a null in both directions. Pitcher grades move
   MORE than hitter grades (mean +1.84 vs +0.54, 31.7% of rows vs 23.5%) on the strength of
   a result measured on the other side. A defensible alternative is to ship the refit for
   hitters only, and it was not tested.
2. **On MAE the shipped anchor is not beaten.** Per-side vs the shipped map is +0.091 MAE
   WORSE on hitters (1 of 6 folds won) and +0.004 on pitchers. The refit wins on SLOPE and
   loses or ties on MAE. Slope was the pre-registered metric and slope is what cleared, but
   a reader who cares about average error is not getting a better number.
3. **The top of the curve is the Clemens table.** From FV 57.5 up, `w_prior` runs 0.57 to
   0.97 on 8 / 23 / 2 / 12 / 2 / 1 rows. The grades of the very players this program was
   commissioned to fix (the top 25) are set mostly by a published FanGraphs table, under our
   name. Phase 1's C4 verdict is unchanged by pooling.
4. **The low end moves most and is measured least.** The largest movers are +10.8 FV at the
   bottom of the board, driven entirely by re-anchoring the concave re-spread from FV45 to
   FV35. Nothing in the bake-off scored that re-anchoring; it falls out of the curve's shape.
   71% of live rows sit below the data floor.
5. **Two grade maps now coexist in one row.** `xfv_grade` is outcome-anchored and `p_bust` is
   not. That is the minimum-blast-radius choice and it is defensible (1.3), but it is also
   the same species of incoherence as the A2 history defect this commit closes, and it
   should not be left standing for long.
6. **The site copy is owed and is not in this commit.** The glossary `xfv` entry, the
   methodology page and `efv_export`'s `meta.grade_scale` string all still describe
   `xfv_grade` as "realized_implied_fv(E[6yr WAR]), deflated". Those files belong to other
   lanes this cycle. Until they are updated, the artifact ships a description of itself that
   is wrong.
7. **The golden is red and stays red.** `test_efv_export::test_xfv_golden_fingerprint` was
   already failing before this lane (the committed `data/xfv.json` differs from the pinned
   hash), it can only be restamped from a production `efv_export.py --all` on the box, and
   this lane must not run one. It is owed, and this change adds a second reason to take it
   once rather than twice.
