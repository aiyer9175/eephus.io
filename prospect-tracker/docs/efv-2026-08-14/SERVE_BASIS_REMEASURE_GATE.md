# SERVE-BASIS RE-MEASUREMENT GATE (Lane S-1, 2026-08-14)

Pre-registered 2026-08-14, committed ALONE with the Results section EMPTY so git
timestamps it, BEFORE `tools/efv_serve_basis_lab.py` exists. Clauses are frozen
from this commit. No clause is amended after it answers.

Artifact: `data/xfv_serve_basis_eval.json`. Lab: `tools/efv_serve_basis_lab.py`.
Supersedes clause G2 of `docs/efv-2026-08-07b/SERVE_PATH_INTEGRITY.md`.

---

## WHY THIS IS A NEW GATE AND NOT AN AMENDMENT

`SERVE_PATH_INTEGRITY.md` states "Clauses below are frozen ... No clause is
amended after it answers." G2 has answered. Its floor is wrong. So this gate
supersedes it with a named retraction, the same way `EFV_GATE_STANDARD.md`
section 7.5 was superseded rather than edited.

## RETRACTION 1: G2 USED A FLOOR FROM A DIFFERENT EXPERIMENT

G2 gated on `MDE95_POOLED_RHO[side] = 0.044` and defended the choice as "the
repo's own measured floor for this protocol; it is not a number this lane chose."

**0.044 is the E_refit floor for the MODEL-vs-CONSENSUS contest**, in which the
two arms come from two different fits and the refit variance (measured at 0.504
of total on hit full_pool) dominates the floor.

Served-vs-blend is a **paired same-fit contrast**: both arms are computed from
the identical ridge fit, on the identical rows, in the identical folds. Only the
post-fit transform differs. **The refit variance that dominates 0.044 is not in
this contrast at all.** Importing that floor makes the gate roughly 2-3x too
permissive, which is why a pitcher gap that may be a resolvable loss was
published as a PASS.

**This gate derives its own floor in the same run, and never borrows one.**

## RETRACTION 2: G4's C-c FAILED AND ITS STATED CAUSE IS REFUTED BY ITS OWN DATA

C-c asserts `rho(a_f + b_f * ridge_pred)` unclamped must equal `rho(ridge)` to
4dp "since a strictly increasing affine map cannot change Spearman", and says it
"fails if any fold fits `b_f <= 0`".

Measured: **C_c_pass is False on BOTH sides** (hit 0.3963 vs 0.3959, pit 0.2369
vs 0.2387) and **`C_c_bad_slope_folds` is `[]` on both**. No fold had a
non-positive slope, so the stated cause did not occur and the real one was never
identified.

**The real cause is cross-fold affine heterogeneity.** A strictly increasing
affine cannot change Spearman *within* a fold. The replay fits a DIFFERENT
`(a_f, b_f)` per fold and then pools 11 folds, so the pooled grade is not a
monotone function of the pooled prediction. Production does not do this: it fits
ONE `(a, b)` on the full labeled pool (`efv_model.py:1364`, `efv_score.py:1633`)
and applies it to every scored row.

## THE ANALYTIC CLAIM THIS GATE MUST TEST, NOT ASSERT

Under a SINGLE global affine, the served grade
`round(outcome_implied_fv(max(-2, a + b*ridge_pred)), 1)` is a non-decreasing
function of `ridge_pred` over the whole pooled set. Therefore

    rho(served_grade) == rho(ridge)   exactly, up to 1dp rounding ties.

If that holds, the served-vs-blend question **collapses to ridge-vs-blend**, a
quantity `xfv_eval*.json` already publishes, and the gap is the DROPPED CONSENSUS
LEG rather than the grade map.

Supporting evidence already on disk (2026-08-08 artifact): on pitchers
ridge-vs-blend is **-0.0174** and served-vs-blend is **-0.0172**, a difference of
0.0002. On hitters they diverge (-0.0034 vs +0.0008), which is exactly the
per-fold heterogeneity this gate blames.

**The claim is PRE-REGISTERED AS A HYPOTHESIS AND CAN FAIL.** If A2a's rho does
not equal A4's to within the rounding-tie bound, the collapse does not hold, this
section is reported as REFUTED, and the gate falls back to gating A2a directly.

## A LIMIT THIS GATE ACCEPTS UP FRONT

**Production's single-affine property cannot be reproduced leak-free in a
forward-chained replay.** Any expanding-window scheme necessarily refits per
fold. So:

* **A2a (gated)** fits ONE affine on the earliest train window only
  (`decision_year < min(SCORED_YEARS)`) and applies it to every fold. Leak-free
  and single-affine, at the cost of being fit on the least data.
* **A2b (reference only, never gated)** fits ONE affine on the full labeled pool,
  which is production exactly and **LEAKS**. Reported with an explicit
  `leaks: true` field so it can never be quoted as out-of-sample.

Both are reported. A verdict is read only off A2a.

## SCOPE INHERITED FROM G2, RESTATED SO IT IS NOT LOST

The live multiplicative tilts, the A/CPX additive overlay, `route_floor_grade`,
and the E-STALE `fv_effective` discount have no resolved-cohort analogue and are
outside every clause here. **Every gap this gate measures is a LOWER BOUND on the
served-vs-published divergence**, because each of those is a further penalty or
substitution applied on top of the graded model leg. On the live board
`route_floor_grade` alone re-bases 55.01% of rows.

---

## ARMS

All scored by `prospect_path._score` with the identical pair weights, on the
identical rows, in the identical folds, on the `debuted_km` cut both sides.

| arm | definition | role |
| --- | --- | --- |
| A0 `blend` | `(1-lam)*max(0, OLS(fv)) + lam*max(-2, a_f + b_f*ridge)` | the PUBLISHED arm |
| A1 `served_foldcal` | G2's arm, per-fold `(a_f, b_f)` | regression control against the 2026-08-08 artifact |
| **A2a `served_prodcal`** | single affine from the earliest train window | **THE GATED ARM** |
| A2b `served_prodcal_leaked` | single affine from the full pool | reference only, `leaks: true` |
| A3 `blend_graded` | the grade map applied to the BLEND WAR | isolates tie/clamp/round cost |
| A4 `ridge` | the raw model leg, ungraded | isolates the dropped consensus leg |
| A5 `baseline` | within-fold `OLS(WAR ~ consensus_fv_raw)` | the consensus bar |

## CLAUSES

### S0 REPRODUCTION (blocking)

The replay must reproduce, to within 0.0010 absolute with `n` equal exactly:
`baseline` and `blend` from `evals.debuted_km.pooled_oos` in `xfv_eval.json` and
`xfv_eval_pitcher.json`, AND `served_grade` from
`xfv_serve_path_eval.json.clauses.G3_attribution.<side>.rho`.

FAIL means the lane is BLOCKED and every clause below is void. Reproducing the
OLD artifact as well as the CURRENT one is deliberate: the basis moved under C-4
and C-7 between them, so a lane that cannot hit both cannot tell a basis move
from its own defect.

### S1 THE FLOOR, DERIVED HERE (blocking, and it precedes every verdict)

Derive MDE95 for the **paired same-fit** contrast `A4 - A0` and for `A2a - A0`,
under BOTH estimators, in this run, at B=2000, player-clustered, seeds declared
in the artifact:

* **E_cond** holds the fit and resamples the scored rows only. This is the
  primary here, because the contrast is same-fit by construction.
* **E_refit** resamples train and test and refits per draw. Reported alongside.

Two-sided coverage must be checked and reported for both, as
`docs/EFV_GATE_STANDARD.md` requires. **A floor that cannot resolve a known
LOSS is not a floor**, so the derivation includes the standard legitimacy check.

**No verdict may be read before S1 answers.** Borrowing `MDE95_POOLED_RHO` is
forbidden by name.

### S2 THE LANE VERDICT

On each side, with the S1 floor:

* **SERVED LOSES**: `rho(A2a) < rho(A0) - MDE95`. The published accuracy figure
  describes an ordering better than the one the board serves, by more than the
  protocol can resolve.
* **NOT RESOLVABLE**: otherwise, reported with the margin as a multiple of the
  floor. Under the equivalence margin Delta = 0.02 Spearman, a gap whose CI lies
  entirely inside +/- Delta is reported as **RULED OUT**, not as a null.

Reported alongside, not gated on, because it is a strictly stronger statement:
**`rho(A2a) < rho(A5)`**, i.e. the served grade loses to plain consensus FV.
The 2026-08-08 artifact already records this as TRUE on pitchers.

### S3 ATTRIBUTION (read only if S2 resolves)

Permitted only where the arms separate by more than the S1 floor:

* dropped consensus leg = `rho(A4) - rho(A0)`
* tie/clamp/round cost   = `rho(A3) - rho(A0)`

If they do not separate, the report says the causes are not separable at this
power and stops. No attribution sentence is written otherwise.

### S4 CONTROLS THAT CAN FAIL

* **C-1 AFFINE INVARIANCE, THE CORRECTED FORM.** `rho(A2a)` must equal `rho(A4)`
  to within the rounding-tie bound, and `rho` of the UNCLAMPED single-affine
  prediction must equal `rho(A4)` to 4dp exactly. This is the analytic claim
  above and it is the one control that, if it fails, invalidates the collapse
  rather than the lane. Report the count of folds with `b <= 0` so the G4 error
  cannot recur silently.
* **C-2 PERMUTATION.** A2a permuted within fold, `random.Random(20260814)`,
  iterating a SORTED LIST of integer indices, never a set and never `hash()` of a
  string. PASS if `abs(rho) < 0.05` both sides.
* **C-3 TIE MASS.** Share of pooled test rows whose A2a sits exactly on the
  `outcome_implied_fv` floor knot, plus the count of distinct served values.
  Reported unconditionally. Above 0.50 the rho must be described as substantially
  a tie artifact rather than a ranking. **C-7 raised the live floor population
  784 -> 1,149, so expect this to be materially higher than the 0.1722 / 0.1360
  G4 measured, and say so.**
* **C-4 BASIS DRIFT.** Report `board_basis_fingerprint` and the matrix mtimes at
  read time. Never mix a floor derived in one run with a delta from another.

### STOP CLAUSES

1. If S0 fails, stop. Report BLOCKED.
2. If S1's coverage check fails on the primary estimator, stop. Do not shop for a
   third estimator; that is floor-shopping and is banned by name.
3. **This lane measures. It ships nothing.** Any remedy is a separate,
   separately-gated epoch. In particular the obvious remedy below is NOT
   authorised by this gate.

## THE REMEDY THIS GATE POINTS AT, RECORDED SO IT IS NOT INVENTED LATER

If S2 resolves as a loss, the indicated fix is to derive the board grade from
`rank_war` (the blend) rather than `xfv_war` (the model leg):

    xfv_grade = outcome_implied_fv(rank_war)   # instead of outcome_implied_fv(xfv_war)

Its properties, to be MEASURED and not argued if it is ever proposed:

* it makes the grade and the dollars coherent for the first time, since surplus
  already prices off a quantile ordered by `rank_war`;
* it **re-ranks the board**, because `rank_war` and `xfv_war` do not share an
  ordering. That is a full grade-basis epoch: `BOARD_RANK_BASIS_EPOCH` bump,
  `board_basis_fingerprint` term, `prospx_current` re-capture INSIDE
  `vf.valuation_set`, golden restamp, every margin re-read;
* it must NOT be confused with a blend-lambda change, which is a banned lane. The
  lambda is untouched; only which leg the GRADE reads changes.

## RESULT (appended after the run)

*(empty at pre-registration)*
