# C-1 gate: the rank-preserving level correction for Defect A

Pre-registered 2026-08-13 BEFORE the correction was fitted. Results section is
deliberately empty at commit so git timestamps the pre-registration.

This gate EXECUTES a repair that was pre-registered on 2026-07-29 and never
built. It does not re-open the diagnosis and it does not invent new PASS
conditions: the three below are copied from
`docs/efv-2026-07-29/CALIBRATION_FINDINGS.md` section "Pre-registered repair and
gates", item 2. Registry row `xfv_pred_dispersion`, artifact
`data/xfv_pred_dispersion_eval.json`.

## The defect, as already measured

`xfv_war_6yr` is over-dispersed out of sample. OLS slope of realized first-6yr
WAR on the OOS prediction, where 1.0 is calibrated:

| side | slope | CI95 | consensus FV on the same rows |
| --- | --- | --- | --- |
| hit | 0.6540 | [0.3624, 0.7637] | 0.9210 |
| pit | 0.5868 | [0.2326, 0.7210] | 1.1920 |

Neither CI covers 1.0. The permuted-prediction zero-information control sits at
[-0.070, +0.092] hit and [-0.087, +0.124] pit, so the measurement resolves and
is not an artifact of the estimator.

Mechanism, and why the existing layer does not already fix it: `efv_score`
serves `clamp(-2, a + b * ridge_pred)` where `(a, b)` come from
`_fit_linear_calibration` fitted on that fold's TRAINING rows. A calibration
fitted in-sample on train does not transfer: out of fold the predictions spread
wider than the outcomes they are calibrated against. So the served number is
systematically too extreme in both directions.

## What is being repaired, and what is deliberately untouched

REPAIRED: the level of the published `xfv_war_6yr`.

NOT TOUCHED: anything that decides order. This is a level fix and the gate below
exists to stop it becoming a rank change. Also not touched: feature composition,
model class, pooling, alpha, ensembling and blend lambda, all closed by prior
ledgers, per the same section that registered this repair.

## Why this cannot move a single dollar, stated in advance

Served surplus prices off `xfv_grade_quantile`, a rank-quantile map of a frozen
`rank_war`. A strictly increasing transform of the predicted WAR leaves every
quantile position identical, so the dollar effect is exactly $0.00 by
construction, not approximately zero. The 2026-07-29 record makes the same point
and it is re-verified here rather than assumed: the lane reports the served
surplus diff and it must be zero rows moved.

The value of the repair is therefore the honesty of the published WAR number,
the negative-row count, and MAE, which is the metric eFV has a standing
committed loss on. No rank claim is made and none may be made from this lane.

## The correction

An affine, strictly increasing map fitted OUT OF FOLD:

    war_corrected = a_c + b_c * war_pred      with b_c > 0 enforced

Estimated leave-one-fold-out: for scored fold Y the correction is fitted on the
OOS rows of every OTHER fold and applied to Y, so no row contributes to the
correction that is applied to it. A global in-sample refit would report a slope
of 1.0 by construction and prove nothing.

`b_c <= 0` is an ABORT, not a clamp: a non-increasing correction would reorder
the board, which is out of scope for this lane by its own definition.

## PASS conditions (copied from the 2026-07-29 pre-registration, item 2)

1. **Slope CI95 covers 1.0 on BOTH sides** after correction.
2. **Spearman unchanged within the registered MDE95 floors on both sides.** This
   is the clause that stops a level fix becoming a rank change.
3. **Negative-WAR row count materially reduced, with the -2.0 floor no longer
   binding.**

All three must hold. A partial pass is a NO_SHIP with a loss ledger, except that
per the 2026-07-29 precedent a side-split outcome (one side passing, one not) is
reported and referred rather than half-shipped silently.

## Mandatory controls (from the same pre-registration)

- **Zero-information twin**: permute the predictions and re-fit. The corrected
  slope must NOT reproduce on permuted input.
- **Rank-identical level twin**: a correction that shifts level without changing
  order must reproduce the rank metrics exactly. This distinguishes a level
  effect from a rank effect.
- **Permutation null with a reported p-value.**
- Any arm whose effect sits inside its own null band is a non-ship and gets a
  loss ledger.

## Additional clauses this lane adds, and why

- **TAIL MAE MUST NOT WORSEN.** Not in the 2026-07-29 list, added here because
  E2b failed on exactly this in 2026-08-12 and the 2026-06-25 global linear
  recalibration failed on it before that. Fitting a level map on a pool whose
  mass sits near zero WAR drags the sparse high end toward the crowd, and the
  tail is where the board order and the dollars live. Reported for the top
  decile of realized WAR, both sides.
- **The clamp is measured, not assumed.** `clamp(-2, .)` is flat below the floor,
  so rows pinned at exactly -2.0 are TIED. If the correction lifts them off the
  floor those ties break, which can move Spearman slightly even though the affine
  map itself is rank-preserving. The lane reports tie counts before and after and
  attributes any Spearman movement to the clamp rather than to the map.

## Abort conditions

- ABORT if `b_c <= 0` on either side.
- ABORT if the parity check fails: the lane must first reproduce the registered
  uncorrected slopes (0.6540 hit, 0.5868 pit) on its own reconstruction of the
  pool before it is allowed to report a corrected one.

## Stop clause

This gate tests ONE functional form, affine, chosen because it is the minimal
rank-preserving level correction and because the defect is a slope. If it fails,
the lane records a loss ledger. It does NOT proceed to fit a second family in
search of a pass. That is the failure mode the FV45 band correction was banned
for on 2026-08-12.

## Results

Measured 2026-08-13. `tools/efv_dispersion_repair_lab.py 2000`, artifact
`data/xfv_dispersion_repair_eval.json`, folds 2016-2020 (the registered
protocol), B=2000, seed 7, 274s.

### Parity passed

Reproduced the registered uncorrected slopes on this lane's own pool
reconstruction: **hit 0.6491 against 0.6540 registered, pit 0.5624 against
0.5868**. The lane is measuring the same quantity.

### The correction works, and it works well

| | hit | pit |
| --- | --- | --- |
| slope, before | 0.6491 | 0.5624 |
| **slope, after** | **1.0080** | **0.9351** |
| slope CI95 after | [0.7821, 1.1858] | [0.0677, 1.1341] |
| overall MAE | 2.4415 to **2.1365** (-12.5%) | 1.7193 to **1.5701** (-8.7%) |
| rows with negative WAR | 270 to 167 | 195 to 49 |
| rows pinned at the -2.0 floor | 51 to **6** | 22 to **10** |
| Spearman shift | -0.0032 (floor 0.0206) | -0.0099 (floor 0.0212) |
| tail MAE, top decile of realized | 7.132 to **8.387** | 5.807 to **6.711** |

Leave-one-fold-out coefficients are stable in sign and magnitude across folds
(hit b_c 0.577 to 0.644; pit 0.308 to 0.651), so no fold is driving it.

Controls all clean. The corrected slope is NOT reproducible from zero
information: permuted-prediction CI95 is [-2.881, 0.565] hit and [-3.322, 0.656]
pit, and the permutation null is [-2.966, 0.659] / [-3.000, 0.654]. The achieved
1.008 and 0.935 sit outside both bands.

### Verdict under the gate AS WRITTEN: NO_SHIP

| clause | hit | pit |
| --- | --- | --- |
| 1. slope CI95 covers 1.0 | PASS | PASS |
| 2. Spearman unchanged within floor | PASS | PASS |
| 3. floor no longer binds | PASS | PASS |
| 4. tail MAE not worse (ADDED by this gate) | **FAIL** | **FAIL** |

**All three clauses the 2026-07-29 programme pre-registered PASS on both sides.
The only failing clause is the one this gate added today.**

### The added clause is reported as failed, and its stated rationale does not transfer

Recording this rather than quietly dropping it, because dropping a clause after
seeing it fail is the exact move this program bans.

The clause was justified in the pre-registration by "the tail is where the board
order and the dollars live". **That justification does not hold for this lane.**
The correction is affine and strictly increasing, so it moves the board order by
nothing, and served surplus prices off `xfv_grade_quantile`, a rank-quantile map,
so it moves dollars by exactly $0.00. The clause was imported from E2b, where the
change DID move served grades, and its reason did not come with it.

What remains true after removing the bad justification is the fact itself: the
published WAR number would read further BELOW the outcome for players who went on
to be stars, by about 1.25 WAR hit and 0.90 WAR pit over six years, in exchange
for the level being right everywhere else.

That trade is intrinsic and not a defect of this functional form. A slope-1
correction is the linear map that minimises squared error overall; on a noisy
predictor it necessarily pulls the extremes toward the middle, and the top decile
of REALIZED outcomes is exactly where predictions were already low. No affine map
can improve the level and the tail at once, so re-fitting a different family in
search of a pass is banned by this gate's own stop clause and would be the FV45
mistake again.

### What this is worth if shipped

The published WAR number becomes calibrated in level (slope 1.008 / 0.935 against
0.649 / 0.562), overall MAE improves 12.5% and 8.7% on the metric eFV carries a
standing committed loss on, and the number stops claiming that 270 hitters and
195 pitchers will produce negative six-year WAR, with rows pinned at the -2.0
floor falling from 51 to 6 on the hitter side. Nothing about the board moves.

### Referred, not shipped

Under the gate as written this is a NO_SHIP and it is recorded as one. Because
the sole failing clause is one this gate added today under a rationale that does
not apply to a rank-neutral and dollar-neutral change, the ship decision is
referred to the owner with both halves stated, rather than being resolved by the
lane in either direction.

## SHIP BLOCKED: the gate measured a quantity production does not serve in isolation

Found 2026-08-13 while implementing the owner's decision to ship, by tracing where
the corrected value would actually go. **This corrects a claim made earlier in
this same document and repeated to the owner**: that board order and dollars
provably do not move. That is true of the statistic the gate measured. It is NOT
true of the field the correction would have to be applied to.

`xfv_war` is not an output. At `efv_score.py:1473` it is the input to the board
grade, `xfv_grade = vf.outcome_implied_fv(xfv_war)`, and the module docstring
states plainly that `xfv_grade` is monotone in `xfv_war`. At `:1923` it is also
the model leg of the blend, `rank_war = (1 - lam) * cons_war + lam * xfv_war`.

So there are three places to apply it and all three are blocked:

1. **At source, to `xfv_war`.** Moves EVERY displayed board grade, because the
   grade is a strictly increasing function of it. Worse, it silently re-weights
   the blend: substituting `a_c + b_c * xfv_war` makes the model leg carry
   `lam * b_c` against the consensus leg's `1 - lam`, and with b_c near 0.63 that
   is a 37% de facto reduction in the blend lambda. **Blend-lambda shifts are a
   banned lane** (TOST RULED OUT for 0.65 / 0.60 / 0.51). Shipping this would
   re-open a closed lane by side effect and without a gate.
2. **To the exported `xfv_war_6yr` only.** Leaves the grade derived from the
   UNCORRECTED value, so the page would publish a projected WAR and a grade that
   no longer correspond through the curve that is supposed to connect them. That
   is a coherence defect of the same family as the three-grade-bases problem this
   programme has been closing, and introducing a fourth disagreement to fix a
   calibration one is a bad trade.
3. **To both, coherently.** This is the correct fix and it is a GRADE-BASIS
   EPOCH: every served grade moves, so it needs a coordinated epoch bump, a
   fingerprint term, a `prospx_current` re-capture, a golden restamp, and a
   re-read of every margin measured on the old basis. That is a far larger change
   than this gate scoped or measured, and the surplus neutrality claimed above
   would have to be re-verified rather than inherited, because the dollar path
   prices off a rank-quantile of `rank_war` and `rank_war` moves under option 1.

**Nothing is shipped.** The measurement stands and is registered; the application
is referred back with the three options above, because the owner's ship decision
was taken on my statement that order and dollars could not move, and that
statement was wrong for the field the correction has to touch.

## Limits

- The pitcher slope CI is wide, [0.0677, 1.1341]. It covers 1.0, which is the
  clause, but it also covers 0.07, so the pitcher correction is imprecise even
  though its point estimate is good. The hitter CI is much tighter.
- Folds are the registered 2016-2020 set, not the current 11-fold SCORED_YEARS.
  That is deliberate for parity with the registered measurement; a ship would
  re-fit the coefficients on the production frame.
- Spearman moves slightly negative on both sides. Both shifts are inside their
  floors, and the mechanism is the -2.0 clamp rather than the affine map: rows
  pinned at the floor are tied, and lifting them off it breaks those ties.
