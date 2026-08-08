# Lane C2 gate: recalibrating the served eFV outcome distribution

Master plan: `docs/master-plan-2026-08-07b-efv-audit.md`, defect D3.
Upstream input: Lane C1, `data/xfv_dist_calibration_eval.json`, gate
`docs/efv-2026-08-07b/DISTRIBUTION_CALIBRATION_GATE.md`, verdict SURVIVES.

**Sections 0 to 5 of this file are written BEFORE `tools/efv_dist_recalibration_lab.py`
exists and therefore before any number in section 6 can be known. Section 6 is a literal
placeholder and is the ONLY section that may be edited after the run.** Nothing in 0 to 5
is touched afterwards. This is the Lane A1 / Lane C1 discipline.

---

## 0. Scope limit. Not negotiable, and the reason is operational.

This lane FITS a recalibration, GATES it, and PREPARES a re-anchor. **It does not ship it.**

The full pytest suite cannot currently be run to completion on this machine: chunks die
with Windows access violations and each chunk passes only in isolation. A change that
moves board-wide dollars cannot be verified today, and shipping an unverifiable
board-wide dollar move is how a cycle is lost.

Files this lane may write:

- `tools/efv_dist_recalibration_lab.py` (new)
- `data/xfv_dist_recalibration_eval.json` (new)
- this document (new)

Files this lane may NOT write, and every proposed change to which is reported as an
`edits_requested` entry with exact old and new text: `value_framework_config.yaml`,
`value_framework.py`, `efv_odds_calibration.py`, `efv_score.py`, `efv_reliability.py`,
`efv_ungraded.py`, any test, and every served artifact
(`data/xfv.json`, `data/xfv_eval*.json`, `data/xfv_reliability.json`, `data/timeseries.json`,
`data/players.json`, `data/source_backtest.json`, `data/fv_outcome_curves_pooled.json`).

No pytest is run by this lane. No write to `prospects.db`.

## 1. What is being recalibrated, stated precisely, because the plan's wording hides a fork

`efv_score` builds the served outcome distribution in two steps at each of its three
scoring seams (`:1488-1498`, `:2070-2080`, `:2546-2556`):

    raw   = vf.p_bucket_given_fv(_odds_grade, is_pit)            # ordered logit on the CONSENSUS-FV scale
    served = _odds_cal.recalibrate_bucket(raw, is_pit,
                                          provisional=not src.get("milb"))

`_odds_grade` is `vf.realized_implied_fv(...)`, a WAR-inversion grade whose dispersion on
the served frame is 15.54 FV against the 6.57 FV the curve was fitted on. That mismatch is
why `recalibrate_bucket` exists. It is a Platt map in log odds applied to the BUST MASS
ONLY; the four non-bust buckets are then rescaled proportionally, so

    S'_k = S_k * (1 - p'_bust) / (1 - p_bust)   for k >= 1,   S_k = P(Y >= k)

which leaves the conditional distribution of `bench / regular / good / star` GIVEN
non-bust exactly as the raw ordered logit put it. **The incumbent correction is
structurally incapable of moving the top-of-board defect C1 handed forward**, which is an
over-prediction of `good` and `star` WITHIN the non-bust mass.

So there are two distinct places a recalibration could land, and they have completely
different blast radii:

- **PATH A, the odds seam.** Generalise `recalibrate_bucket` from one threshold to all
  four. Consumers: `p_bucket` and `p_bust` on the board, and `efv_reliability`. **The
  surplus dollars do NOT read this map.** `vf.expected_surplus_usd` prices through
  `_pipeline_surplus_from_svs` (`value_framework.py:1371-1376`), which calls
  `p_bucket_given_fv` itself, at the DISPLAY grade, and never sees the Platt output.
- **PATH B, the curve.** Refit `p_bucket_given_fv` in `value_framework_config.yaml`. That
  moves every dollar on the board and requires the `prospx_current` re-capture and the
  20-cell grid re-stamp described in section 5.

This lane fits PATH A, for a reason fixed here before any number is known: D3 is measured
at the realized-implied grade, and `efv_odds_calibration.py:79-82` already records that on
its NATIVE consensus key the same curve shows a nearly FLAT +0.11 to +0.17 gap across every
band, a level error and not a slope error. Correcting a defect measured on one key by
editing a curve consumed on a different key is the wrong instrument. Section 5 nevertheless
delivers the PATH B checklist in full, because the orchestrator, not this lane, decides
whether the odds and the dollars are unified (plan item D6).

**Verification owed before and after, and reported whatever it says:**
`vf.apply_calibration` must be applied EXACTLY ONCE, at the reprice seam
(`efv_score.py:1097-1111` via `_reprice_surplus_on_display` at `:1583-1585`). And the odds
must stay on `_odds_grade` while the dollars stay on `xfv_grade_display`
(`efv_score.py:1137-1139`). This lane does not unify them.

## 2. The frame and the candidate family

### 2.1 Frame

An exact mirror of `efv_reliability._oof_rows` for both sides: forward-chained
out-of-fold, `CHAIN_YEARS = range(2016, 2024)`, `MIN_TRAIN = 60`, `MIN_TEST = 10`, ridge
plus linear output calibration on `target_censored`, grade inversion through
`vf.realized_implied_fv` at `exposure_seasons = 6`, then `vf.p_bucket_given_fv`. The
mirror must reproduce the shipped `data/xfv_reliability.json` pooled bust ECE to within
0.005 or the lane stops (section 4.0).

Each row carries `p_raw`, the shipped served `p_after`, `y` (`_realized_bucket`, the
divisor-6 label C1 cleared), the consensus `fv`, `decision_year`, `side`, and the
`provisional` flag. **Provisional rows are OUT OF SCOPE and receive no map from any arm**,
exactly as `recalibrate_bucket` no-ops on them, because `efv_ungraded.thin_sample_p_bust`
owns those rows and stacking would undo that lane's fix.

### 2.2 The family

Work in cumulative-logit space on the RAW curve. With `S_k = P(Y >= k)`, `k = 1..4`, and
`z_k = logit(S_k)`:

    z'_k = A_k + B_k * z_k ,   S'_k = sigmoid(z'_k) ,   S'_k <- running-min over k

The running minimum enforces `S'_1 >= S'_2 >= S'_3 >= S'_4`, so the output is always a
valid distribution. Buckets are recovered by differencing. Parameters are fit per side by
maximum multinomial likelihood on the recalibration TRAIN fold.

- **ARM-0 INCUMBENT-SHIPPED.** The served `p_after`. Fixed constants
  (`_PLATT`, hit `(0.7268, 0.3749)`, pit `(0.7269, 0.3553)`), fitted off-frame on the
  2014-2020 resolved rows. This is the incumbent the ship decision is against.
- **ARM-1 SHARED.** One `(A, B)` for all four thresholds. 2 params per side.
- **ARM-2 PER-THRESHOLD.** `(A_k, B_k)` for each of the four thresholds. 8 params per
  side. **This is the PRIMARY candidate**, named now.
- **ARM-3 LEVEL-ONLY.** `(A_k, B_k = 1)`. 4 params per side. Isolates level from slope.
- **ARM-4 CONTROL, MARGINAL CONSTANT.** Serve the TRAIN fold's pooled bucket marginal to
  every test row. Carries zero information about the player.
- **ARM-5 CONTROL, INCUMBENT FAMILY REFIT PER FOLD.** `(A_1, B_1)` free, thresholds 2 to 4
  held at identity. 2 params per side. This is the incumbent's own family, refit honestly
  on each train fold. It exists because substituting a production calibration for a
  per-fold one has FLIPPED THE SIGN of a headline in this program.

### 2.3 Forward chaining

For test year `t`, every arm is fit on the out-of-fold rows with `decision_year < t`, per
side, and applied to the rows at `t`. A fold enters the evaluable frame only when its
recalibration train set has at least **MIN_RECAL_TRAIN = 150 non-provisional rows on that
side**. 150 is a threshold this gate ADDS; the plan does not contain one. Every arm,
including ARM-0, is scored on the IDENTICAL surviving frame, and the frame's `n` and the
list of surviving folds are printed.

## 3. Metrics. Calibration decides; log score sits beside it; MAE is a diagnostic.

Per the 2026-07-31 owner ruling that surplus is an expected-value quantity, the arbiter is
calibration. Computed with the SHIPPED functions where they exist
(`efv_reliability._reliability_bins`, `_tier_reliability`, `_tier`, `MIN_TIER_N = 15`).

- **M1, pooled `bust` ECE.** The tripwire's own quantity. **PRIMARY.**
- **M2, n-weighted mean per-tier gap.** Unweighted reported beside it. **PRIMARY.**
- **M3, per-bucket pooled ECE, all five.** Mean over the five reported as `ECE_mean5`.
- **M4, reliability slope and intercept for `bust`**: IRLS logistic fit of the bust
  indicator on `logit(p_bust)`. Ideal slope 1.000, intercept 0.000.
- **M5, held-out bias**, `mean(p_b) - mean(y_b)`, per bucket, pooled and split into the
  tier bands `<= 45` and `>= 50`. The `good + star` bias in the `>= 50` band is the
  top-of-board statistic C1 handed forward and is named here as **M5T**.
- **Reported beside, never the arbiter:** multiclass log score (mean negative log
  likelihood) and multiclass Brier.
- **Diagnostic only:** MAE of `E_p[annual WAR]` against realized annual WAR, with the
  bucket representatives fixed now at `(0.25, 1.00, 2.00, 3.25, 5.00)` WAR per season,
  the representative points of the `BUCKET_EDGES = (0.5, 1.5, 2.5, 4.0)` bands.

### 3.1 The floor, derived for THIS statistic on THESE rows

No floor is borrowed from another experiment. For each gated statistic the paired delta
`M(ARM-0) - M(ARM-2)` is bootstrapped on this lane's own frame under BOTH registered
instruments, and both are reported. `MDE95 = 1.645 * sd`, one-sided.

- **E_cond** (registered primary, `data/xfv_power_eval.json`): every per-fold
  recalibration fit is held FIXED at its real-data value, and only the scored rows are
  resampled i.i.d. with replacement. `B = 2000`.
- **E_refit** (shipped instrument): the pooled out-of-fold frame is resampled with
  replacement and the forward-chained recalibration is REFIT on each draw before scoring.
  `B = 400`. **Disclosed limitation, fixed here:** the underlying ridge and its output
  calibration are inputs to this lane and are held fixed, so this is a RESTRICTED E_refit.
  It resamples the recalibration's training corpus, not the model's. It is therefore a
  lower bound on the full refit variance and it is labelled as such everywhere it appears.

If the two instruments disagree about a clause, **the conservative one decides and the
disagreement goes in the headline.**

### 3.2 Multiplicity, declared now

Five clauses are tested on one frame (P1 to P5 below). Every primary statistic is reported
against BOTH its unadjusted `MDE95` (one-sided alpha 0.05, z = 1.645) and a
Bonferroni-adjusted floor at `k = 5` (one-sided alpha 0.01, z = 2.326). The family is not
narrowed after the run. Per-tier and per-bucket tables are DESCRIPTIVE and no clause is
built on a cell selected after seeing it.

## 4. Decision rule, fixed now

### 4.0 Stop conditions. Any one means NO-SHIP and the section 5 checklist is unnecessary.

- The frame mirror fails to reproduce the shipped `xfv_reliability.json` pooled bust ECE
  to within 0.005.
- Any arm emits a vector that is not a valid distribution (negative mass, or a sum off 1
  by more than 1e-9), or violates monotonicity of `S'_k`.
- Any arm changes a provisional row's distribution.
- ARM-2 makes the multiclass LOG SCORE worse than ARM-0 by more than its own E_cond
  `MDE95`. A calibration map that buys ECE by flattening the distribution is not shippable
  and this clause is what would catch it.

### 4.1 The clauses

- **P1, PRIMARY.** `M1(ARM-0) - M1(ARM-2) > MDE95` under BOTH E_cond and restricted
  E_refit.
- **P2.** `M2(ARM-0) - M2(ARM-2) > MDE95` under E_cond, with E_refit reported beside it.
- **P3, TOP OF BOARD.** `|M5T(ARM-2)| < |M5T(ARM-0)|` AND the improvement
  `|M5T(ARM-0)| - |M5T(ARM-2)|` exceeds its own E_cond `MDE95`. No fixed percentage bar is
  used; the floor is derived on the statistic.
- **P4, DO NO HARM.** No individual bucket's pooled ECE worsens by more than that bucket's
  own E_cond `MDE95`.
- **P5, ZERO-INFORMATION CONTROL.** ARM-2 must beat ARM-4 on BOTH M1 and log score. And if
  ARM-4 reproduces **80 percent or more** of ARM-2's M1 improvement over ARM-0, the result
  is reported as a LEVEL effect, "the served distribution's average was wrong", NOT as a
  shape recalibration. 80 percent is a threshold this gate ADDS.
- **P6, PERMUTED-TIER TWIN.** Within each train fold and each side, permute the predicted
  probability vectors among the training rows, destroying the correspondence between the
  predicted tier and the realized outcome while preserving both marginals. Refit ARM-2 on
  the permuted train fold and apply it to the REAL, unpermuted test rows. `B = 200`.
  ARM-2's actual M1 improvement must exceed the **95th percentile** of the twin's, i.e.
  one-sided permutation `p < 0.05`.
- **P7, INCUMBENT REFIT.** Reported, and it can change the recommendation. If ARM-5, the
  incumbent's own two-parameter family refit per fold, reproduces **80 percent or more**
  of ARM-2's M1 improvement over ARM-0, then the correct fix is "the shipped Platt
  constants are stale and in-sample", not "extend the map to all four thresholds", and
  this lane says so and hands THAT as the recommendation. 80 percent is a threshold this
  gate ADDS.
- **P8, HELD-OUT FOLDS.** Report ARM-0 and ARM-2 M1 on every surviving fold separately,
  and the fraction of folds in which ARM-2 improves. Reported for honesty; a fold split of
  this size cannot carry a clause on its own and none is built on it.

### 4.2 Verdict

- **GATED-READY.** P1, P2, P3, P4, P5, P6 all pass and no stop condition fired. Section 6
  publishes the recalibration, the before and after on every tier, the dollar impact, and
  the section 5 checklist becomes live.
- **PARTIAL.** P1 and P6 pass but P2 or P3 fails. The passing part is published with its
  scope stated; the checklist is published marked PARTIAL.
- **NO-SHIP.** P1 fails, or P6 fails, or a stop condition fires. Section 6 says so and the
  section 5 checklist is explicitly declared unnecessary.
- **REDIRECT.** P7 trips. The recommendation becomes "refresh the incumbent constants",
  and it inherits the same gate.

Any clause whose verdict is decided by a threshold this gate ADDED (`MIN_RECAL_TRAIN`
150, the two 80 percent shares, the 0.05 permutation alpha, `k = 5` Bonferroni) is named
in the headline.

## 5. The re-anchor checklist, written before the result so it cannot be shaped by it

Live only if section 6 returns GATED-READY or PARTIAL. Two paths, because section 1 shows
they are genuinely different changes.

### 5.1 PATH A, the odds seam. What this lane fits.

Blast radius: `p_bucket` and `p_bust` on the board and in the exports, plus
`data/xfv_reliability.json`. **No dollar figure moves**, because
`vf.expected_surplus_usd` never reads this map. That claim is MEASURED in section 6 and is
not asserted here.

Execute in this order, all in one commit, with the suite green:

1. `efv_odds_calibration.py`: add the fitted per-threshold constants and a
   `recalibrate_bucket_full(probs, is_pitcher, *, provisional=False)` beside the existing
   `recalibrate_bucket`. Do NOT edit `recalibrate_p_bust` or `_PLATT`; the single-threshold
   map has other callers (`efv_ungraded.py:704` region, `storage.py:6590` region) and its
   scope limit at `efv_odds_calibration.py:73-83` still binds. Keep the `provisional` hard
   no-op byte for byte.
2. `efv_score.py`: swap the call at ALL THREE seams, `:1498`, `:2080`, `:2556`. Missing one
   seam is the exact failure that produced the 2026-08-03 "monitor grading the wrong
   distribution" defect. Leave `_odds_grade` and `xfv_grade_display` as they are: the odds
   stay on the realized grade and the dollars stay on the display grade (`:1137-1139`).
   Do not touch `_cal_mm`.
3. `efv_reliability.py`: swap the call in `_oof_rows` at `:222-223`. Then re-derive
   `BUST_ECE_TRIPWIRE` (`:118`), because the served baseline the wire is anchored to has
   moved. `test_efv_levers.py:51-52` requires `0.0754 < bar < 0.1281` and
   `test_reliability_surface.py:118-125` pins the same two literals; both are DOCUMENTED
   MEASUREMENTS of the pre-change tree and both must be re-stamped with the new served
   value and a comment saying which commit moved it.
4. `test_reliability_surface.py:96-106`: the wiring assertion greps `_oof_rows` for the
   literal string `recalibrate_bucket`. `recalibrate_bucket_full` contains that substring,
   so the test passes without an edit. Tighten it anyway to name the function actually
   wired, or it will keep passing after a future regression.
5. Regenerate `data/xfv_reliability.json` on the BOX, not locally (degraded-local-data
   rule), and re-run the eFV export so `data/xfv.json` `p_bucket` and `p_bust` carry the
   new map.
6. Add a registry row and point it at `data/xfv_dist_recalibration_eval.json`
   (model-audit-program rule: every model needs a registry row, an eval artifact and a
   freshness entry).
7. Tests to run, and there is no substitute for running them: `test_efv_levers.py`,
   `test_reliability_surface.py`, `test_efv_export.py`, `test_value_framework.py`,
   `test_pitcher_roles.py`, `test_bayes.py`, `test_debuted.py`, `test_config_base_verification.py`.
   The suite is currently unrunnable in one process on this machine; the chunked runner is
   the only honest way to clear it.

**What PATH A does NOT do, stated plainly:** it leaves the site displaying odds that price
one distribution while the dollars beside them price another. That inconsistency is
measured in section 6 and handed to the orchestrator as a decision, not resolved here.

### 5.2 PATH B, the curve. NOT recommended by this lane, delivered because it was asked for.

Only if the orchestrator decides the odds and the dollars must be unified (plan D6).

1. `value_framework_config.yaml`: `p_bucket_given_fv_hitter` / `p_bucket_given_fv_pitcher`
   (`:63-77`) and/or the `fit.bayes` block (`:110+`). Any change here moves the fitted
   ordered logit and therefore EVERY dollar on the board.
2. Re-capture `prospx_current.yaml` **inside `with vf.valuation_set("prospx_current")`.**
   Capturing on the DEFAULT set silently yields a different grid: pitcher FV60 reads 75.2
   rather than the correct 81.3. This has cost a full cycle before.
3. Re-stamp the 20-cell acceptance grid at `test_valuation_sets.py:66-79`
   (`test_prospx_current_table_mode_matches_production`, 10 FV labels x 2 sides, tolerance
   `abs=0.05`).
4. Re-stamp the FV50 literal at `test_valuation_sets.py:150`,
   `vf.surplus_value_mm(50.0, False) == pytest.approx(47.4, abs=0.1)`, and update the
   comment block above it that records WHY it moved. That comment is currently the R7 dpw
   re-anchor note; do not overwrite the history, append to it.
5. `test_config_base_verification.py:85, 171-223, 316-317` reads the config rows directly,
   checks monotonicity and pins `p45 / p475 / p50` ordering. Re-verify, do not re-stamp
   blindly.
6. Everything downstream that reads the curve at a CONSENSUS key also moves and must be
   re-checked: `backtest.py:610`, `proj_export.py:928`, `prospect_path.py:183`,
   `storage.py:6590`, `efv_ungraded.py:704`, `test_bayes.py:56-59`,
   `test_pitcher_roles.py:79-163`, `test_value_framework.py:161-370`.
7. Re-run the surplus calibration layer. `vf.apply_calibration` was fitted against RAW
   engine outputs; changing the curve changes those outputs, so the isotonic breakpoints
   are stale the moment the curve moves.
8. Re-run the full suite. Not a chunk of it.

## 6. RESULT (appended after the run)

Lab: `tools/efv_dist_recalibration_lab.py`. Artifact: `data/xfv_dist_recalibration_eval.json`.
Every number below is a key in that file.

### 6.1 Verdict: NO-SHIP for ARM-2, the pre-registered primary.

P6, the permuted-tier twin, FAILS on M1: ARM-2's real M1 improvement is +0.01625 while its
own permuted twin averages +0.02602 over 200 draws, one-sided permutation `p = 0.995`.
P5 also fails, and P3 fails. Per section 4.2 that is NO-SHIP, and the section 5 checklist
is NOT live.

| clause | result |
|---|---|
| P1, M1 both instruments | PASS. E_cond margin 1.50x, restricted E_refit 1.09x, and they agree |
| P2, M2 tier gap | PASS. E_cond margin 8.88x, restricted E_refit 3.41x |
| P3, top of board M5T | **FAIL.** improvement 0.03125 against an E_cond floor of 0.08312, 0.38x |
| P4, do no harm | PASS. no bucket worsens beyond its own floor |
| P5, zero-information control | **FAIL.** ARM-4 beats ARM-2 on M1 |
| P6, permuted-tier twin | **FAIL.** p = 0.995 |
| P7, incumbent refit redirect | does not trip AS REGISTERED. See 6.5, the registration was wrong |
| P8, folds | 3 of 5 improved |
| STOP, log score | not tripped. ARM-2 improves log score by 0.02667 |

**No threshold this gate added determined the verdict.** The permutation alpha of 0.05 did
not: `p = 0.995`, so the clause fails at any conventional alpha. The 0.80 control-share bar
did not: P5's failing condition is a strict inequality with no bar in it. `MIN_RECAL_TRAIN`
= 150 sets the frame and not the answer; re-running at 100, 250 and 400
(`posthoc.min_recal_train_sensitivity`, n = 2,022 / 1,425 / 977) leaves ARM-2 losing to
ARM-4 on M1 at every value.

### 6.2 The frame, and the stop conditions

The mirror reproduces the shipped monitor: pooled bust ECE 0.07908 against
`xfv_reliability.json`'s 0.07907 on 2,822 rows against 2,823, one row of regeneration
drift. The lab's fast metric implementations reproduce `efv_reliability._reliability_bins`
and `_tier_reliability` to 1e-4 on the same rows. Every arm emits a valid distribution
(max sum error 0.0, no negative mass, survivor sequence monotone) and no arm touches a
provisional row. No stop condition fired.

Of the 2,822 out-of-fold rows, 1,142 are provisional and receive no map from any arm.
The evaluable frame after `MIN_RECAL_TRAIN` is **1,828 rows**, hitter folds 2019-2023 and
pitcher folds 2020-2023, of which 498 are provisional. Tier counts: 35 (575), 40 (862),
45 (192), 50 (125), 55 (44), 60 (22). Tier 50 and above is 199 rows, 10.9 percent.

### 6.3 Every arm, measured on the identical 1,828 rows

| arm | M1 bust ECE | M2 tier gap | log score | Brier | M4 slope | M5T good+star bias, tier >= 50 | MAE diag |
|---|---|---|---|---|---|---|---|
| raw, no map | 0.10613 | 0.04591 | 0.51964 | 0.25024 | 0.708 | +0.24635 | 0.5894 |
| **ARM-0 shipped** | 0.06713 | 0.03860 | 0.48246 | 0.22861 | **1.576** | **+0.08757** | 0.5404 |
| ARM-1 shared | 0.02560 | 0.01889 | 0.45921 | 0.22086 | **0.973** | **+0.02135** | 0.4885 |
| **ARM-2 per-threshold (primary)** | 0.05088 | 0.02256 | 0.45579 | 0.22120 | 1.270 | -0.05632 | 0.4893 |
| ARM-3 level only | 0.03551 | 0.00909 | 0.45613 | 0.21897 | 0.717 | -0.01903 | 0.4570 |
| ARM-4 marginal constant | 0.04232 | 0.05395 | 0.53745 | 0.25785 | 0.955 | -0.11948 | 0.5787 |
| ARM-5 as registered | 0.08220 | 0.04310 | 0.51698 | 0.24378 | 0.799 | +0.24635 | 0.5804 |

Ideal M4 slope is 1.000. The raw curve reads 0.708, over-sharp, which is the defect
`efv_odds_calibration` was built to fix. **The shipped map does not land on 1.000, it
overshoots to 1.576.** Nothing measured that before, because the monitor watches ECE and
ECE is blind to slope.

### 6.4 Per tier, before and after. This is the requested before/after table.

`n` and realized frequencies are common to every arm; only the predictions move.

| tier | n | realized bust | ARM-0 p(bust) | ARM-1 | ARM-2 | realized good+star | ARM-0 p(g+s) | ARM-1 | ARM-2 |
|---|---|---|---|---|---|---|---|---|---|
| 35 | 575 | 0.9791 | 0.9273 | 0.9736 | 0.9524 | 0.0000 | 0.0073 | 0.0048 | 0.0045 |
| 40 | 862 | 0.9142 | 0.8211 | 0.8919 | 0.8596 | 0.0046 | 0.0234 | 0.0219 | 0.0161 |
| 45 | 192 | 0.7083 | 0.6315 | 0.7098 | 0.6818 | 0.0260 | 0.0829 | 0.0734 | 0.0491 |
| 50 | 125 | 0.3840 | 0.5244 | 0.5403 | 0.5533 | 0.1360 | 0.1913 | 0.1479 | 0.0921 |
| 55 | 44 | 0.4318 | 0.4794 | 0.4465 | 0.4937 | 0.1363 | 0.2849 | 0.2099 | 0.1171 |
| 60 | 22 | 0.4091 | 0.3724 | 0.3041 | 0.3702 | 0.2727 | 0.4808 | 0.3358 | 0.2039 |

n-weighted tier gap by tier, ARM-0 to ARM-2: 0.02074/0.01069 (35), 0.03721/0.02180 (40),
0.05193/0.02356 (45), 0.08375/0.06997 (50), 0.07844/0.02474 (55), 0.10781/0.07971 (60).

**A correction to the brief C1 handed forward.** C1 described the top of the board as an
over-prediction of `good` and `star`. On this frame the larger top-of-board error is
`bench`, biased **-0.20313** at tier 50 and above against `good+star` at +0.08757, and
`bust` is over-predicted there by +0.10531. The shape is "too much mass at both ends and
far too little in the middle", not simply "over-priced stars". Any C2 successor should fit
that shape, not the one in the brief.

### 6.5 The controls, including the two that embarrass this lane

**CTRL, zero information (P5).** ARM-4 serves each test row its train fold's pooled bucket
marginal. It reaches M1 = 0.04232 against ARM-2's 0.05088, i.e. it reproduces **152.7
percent** of ARM-2's M1 gain and BEATS it. ARM-2 does beat it on log score (0.45579 against
0.53745) and on M2 (0.02256 against 0.05395). So ARM-2 is genuinely informative and the
PRIMARY METRIC CANNOT SEE IT.

**Why M1 is the wrong arbiter, measured.** Murphy decomposition of the bust-bucket Brier
over the same 10 bins (`posthoc.M1_is_degenerate`):

| arm | reliability | resolution | occupied bins |
|---|---|---|---|
| ARM-0 shipped | 0.005482 | 0.030505 | 8 |
| ARM-2 | 0.004510 | 0.032366 | 8 |
| ARM-1 | 0.001587 | 0.030974 | 9 |
| **ARM-4 constant** | **0.004148** | **0.006429** | 6 |

A constant predictor is well calibrated BY CONSTRUCTION, because it emits the base rate.
Its resolution is 0.0064 against 0.0305 for everything else, and pooled ECE does not
penalise that. Gating a distribution recalibration on calibration alone therefore admits
a zero-information predictor. That is a defect in this gate's own design, inherited from
reading the 2026-07-31 owner ruling as "gate on calibration", and it is the direct cause of
the NO-SHIP.

**CTRL, permuted-tier twin (P6).** ARM-2 fails at p = 0.995 on M1 and passes at p = 0.000
on M2 (real improvement +0.01604, permuted twin AVERAGES -0.01324, i.e. shuffling makes the
tier gap worse). Post-hoc, and not part of the verdict, the same twin run against ARM-1 and
ARM-3 gives p = 0.000 on BOTH M1 and M2. **Disclosure of a confound in this control:** its
power depends on the arm's capacity to collapse. ARM-2 has per-threshold slopes, so under
permutation it can drive every `B_k` to zero and become a constant, which then scores well
on the degenerate M1. ARM-1 shares one `B` across all four thresholds and structurally
cannot reach that degenerate optimum. Some of the gap between the two arms' permutation
p-values is capacity, not signal.

**CTRL, incumbent family refit (P7), and a MIS-SPECIFICATION IN THIS GATE'S OWN
REGISTRATION.** Section 2.2 registers ARM-5 as "(A_1, B_1) free, thresholds 2 to 4 held at
identity" AND calls it "the incumbent's own family". Those are two different maps.
`recalibrate_bucket` rescales the non-bust buckets PROPORTIONALLY,
`S'_k = S_k * S'_1 / S_1`; it does not hold the upper cumulative logits fixed. ARM-5 was
run exactly as registered and its P7 answer stands as registered, but the answer is about
the wrong family. Symptom: ARM-5's M5T is +0.24635, byte-identical to the raw curve's,
because holding thresholds 2 to 4 at identity leaves the good+star mass literally unchanged
whenever `S'_1 >= S_2`.

ARM-5b, the faithful proportional-rescale refit, was added after the primary run. It
reaches M1 = 0.05026 and reproduces **103.8 percent** of ARM-2's M1 gain, so **P7 WOULD
HAVE TRIPPED had it been specified correctly.** Its M2 is 0.02702 and its M5T is +0.07937
against ARM-0's +0.08757, a 9 percent improvement on the top-of-board bias where ARM-1
gets 76 percent. That is the section 1 structural claim confirmed by measurement: a
bust-only map, however well refit, cannot move the top of the board.

### 6.6 The floors, derived on this statistic on these rows

| statistic | point | E_cond sd | E_cond MDE95 | margin | restricted E_refit sd | MDE95 | margin |
|---|---|---|---|---|---|---|---|
| M1 bust ECE | +0.01625 | 0.006604 | 0.010864 | 1.50x | 0.009051 | 0.014888 | 1.09x |
| M2 tier gap | +0.01604 | 0.001098 | 0.001806 | 8.88x | 0.002857 | 0.004700 | 3.41x |
| M5T abs bias, tier >= 50 | +0.03125 | 0.050527 | 0.083117 | **0.38x** | 0.047381 | 0.077942 | **0.40x** |
| log score | +0.02667 | 0.009421 | 0.015497 | 1.72x | not run | | |

Both instruments agree on every clause. Under the Bonferroni floor at k = 5 (z = 2.326)
M1 clears E_cond at 1.06x but NOT restricted E_refit (0.77x); M2 clears both.

**What the top of the board can and cannot support.** M5T is measured on 199 rows, of which
tier 60 is 22. Its E_cond sd is 0.0505, so the smallest detectable improvement is 0.0831
against a defect of 0.0876. The top-of-board cell can barely detect the total elimination
of its own defect. No re-anchor may be driven by it, which is what the lane brief said
about C1's n = 32 cell and it is still true here.

### 6.7 Serve-path integrity, verified before and after

- `_odds_cal.recalibrate_bucket` is called at exactly **three** seams, `efv_score.py:1498`,
  `:2080`, `:2571`. The module docstring and `efv_odds_calibration.py:4-6` still name
  1292 / 1812 / 2191, which are stale by 300 to 400 lines.
- The recalibrated vector is consumed at those seams by `p_bucket` and `p_bust` and by
  **nothing else** (lines 1514, 1521, 2118, 2125, 2128, 2588, 2594, 2596).
- `vf.expected_surplus_usd` takes no probability argument. It re-derives
  `p_bucket_given_fv` itself, at the display grade, inside `_pipeline_surplus_from_svs`.
  **No odds-seam map can reach a dollar.**
- `vf.apply_calibration` is called from exactly one place in `efv_score`, `_cal_mm` at
  `:1111`. `_reprice_surplus_on_display` recomputes from `vf.expected_surplus_usd` and
  `vf.sv_distribution` rather than reading back an already-calibrated field, so the
  earlier `_cx` calibration at `:1516-1520` is discarded and not compounded. **Applied
  exactly once**, as required, and this change would not alter that.
- Odds stay on `realized_implied_fv`, dollars stay on `xfv_grade_display`. Not unified.

**A defect found while building the pricing instrument, and it is not this lane's to fix.**
`efv_export.py:44-45` sets both `xfv_grade` and `xfv_grade_realized` to the scored dict's
`xfv_grade`, which `efv_score.py:1473` builds from `vf.outcome_implied_fv`. The odds are
keyed on `_odds_grade = vf.realized_implied_fv` (`:1480`, `:1488`). The export comment at
`efv_export.py:41-42` states that `xfv_grade_realized` IS `realized_implied_fv` and "still
drives p_bucket / p_bust". It is not and it does not. Recovering the true odds grade by
inverting the served vector against the curve (inversion residual median 0.00039, max
0.00054, which is the 3 dp export rounding floor) shows the recovered grade agrees with the
exported one within 0.1 FV on only **48.7 percent** of 9,382 rows, with a 5th percentile of
**-8.21 FV**. Anyone auditing the served odds from `data/xfv.json` reads them at the wrong
key on half the board.

### 6.8 Dollar impact by FV band

**PATH A moves no dollar. The figure is 0.00, and it is structural rather than estimated**
(section 6.7). Every number below is a COUNTERFACTUAL: what would happen if the served odds
vector replaced `p_bucket_given_fv` inside `_pipeline_surplus_from_svs`.

First, a fact that reframes the whole question: **8,199 of the 9,382 board rows price below
the bridge** (`xfv_grade_quantile < 45.0`), where `expected_surplus_usd` uses the flat
low-tier anchor and reads no bucket probability at all. Only **1,183 rows** have dollars
that depend on the outcome distribution in any way.

On those 1,183 rows, mean per-row move in $M by consensus-FV band:

| band | n | mean served surplus | EXISTING odds-vs-dollars gap | ARM-2 on top | ARM-1 on top |
|---|---|---|---|---|---|
| 42.5-45 | 220 | 19.89 | -3.99 | -6.23 | -2.88 |
| 47.5-50 | 603 | 28.96 | -6.47 | -7.79 | -2.17 |
| 52.5-55 | 189 | 47.47 | -11.09 | -12.08 | -1.94 |
| >= 57.5 | 169 | 68.14 | -11.36 | -18.65 | -4.96 |

The EXISTING column is the headline. **Before any recalibration, the odds the site displays
already price the top band $11.36M lower than the dollars printed beside them**, because the
served odds carry a `p_bust` 0.32 higher at `>= 57.5` than the pricing distribution does.
That is 17 percent of the served surplus at that band. Limitation, stated: per-row position
and age are not in `data/xfv.json`, so the per-bucket SVs use the generic curve and default
timing, and this reconstruction reproduces the served `surplus_mm` to a median absolute
error of 1.45 $M (p95 6.24). These are band-level magnitudes, not per-player restatements.

### 6.9 What is handed forward

1. **The re-anchor checklist in section 5 is NOT LIVE.** Nothing is shipped. The checklist
   is family-agnostic, it is about where a map lands rather than which map, so a successor
   inherits it unchanged.
2. **ARM-1, the two-parameter shared map on all four thresholds, is the candidate.** It
   improves M1, M2, log score, Brier, the M4 slope (1.576 to 0.973) and M5T (+0.0876 to
   +0.0214) simultaneously, and it beats its permuted twin at p = 0.000 on both statistics.
   It was NOT the pre-registered primary. Promoting it because the arm table says so is
   selection on outcome, and this lane does not do it. It needs a fresh registration.
3. **That registration must not gate on ECE.** Section 6.5 measures why. The successor
   should gate on a proper score (log score or Brier) with the reliability and resolution
   components reported separately, and treat ECE as a component rather than the arbiter.
4. **The top-of-board cell cannot carry a gate.** Section 6.6. If the top of the board is
   the objective, the frame must be widened or the statistic must be pooled differently.
5. **P7 is unresolved and matters.** ARM-5b captures 103.8 percent of ARM-2's M1 gain but
   only 9 percent of its top-of-board move. A successor must separate "the shipped Platt
   constants are stale" from "the map needs more thresholds", and ARM-5b is the right
   comparator for that, not ARM-5.
6. **Two edits are owed to other owners** and are filed as edit requests, not made here:
   the stale seam line numbers in `efv_odds_calibration.py`, and the incorrect
   `xfv_grade_realized` comment in `efv_export.py`.
