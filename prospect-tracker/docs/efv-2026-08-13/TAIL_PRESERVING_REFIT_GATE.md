# C-1b: a tail-preserving level correction. Pre-registration.

Pre-registered 2026-08-14 BEFORE any candidate family was fitted. Results section
deliberately empty at commit so git timestamps this.

Supersedes the affine correction shipped hours earlier in
`GRADE_BASIS_EPOCH_GATE.md` IF and only if a candidate clears every clause below.
If none clears, the affine map stays and this document becomes its loss ledger.

## Why this lane exists, and why it is not spec-shopping

The stop clause in `DISPERSION_REPAIR_GATE.md` bans fitting a second family "in
search of a pass". That ban is respected here, and this lane is opened for a
different reason: **new evidence about the SERVED consequence of a clause that was
already measured as failed.**

The affine map passed all three registered clauses and FAILED the tail-MAE clause
(+15.8% hit, +8.5% pit). That failure was reported, referred, and accepted as a
disclosed cost. What the gate did NOT measure, and what the owner found on the live
board, is what the tail failure does to the served grade:

| cohort by consensus FV | eFV minus consensus, affine | uncorrected | n |
| --- | --- | --- | --- |
| >= 55 | **-4.95** | **+0.14** | 14 |
| 50 to 55 | -2.90 | +0.02 | 35 |
| 45 to 50 | -0.78 | +0.84 | 139 |
| < 45 | **-4.99** | **-10.97** | 4,470 |

**11 of the 14 elite prospects flipped from above-consensus to below.** The
flagship case is Jesus Made: raw model 12.08 WAR against a pooled curve that puts
consensus FV 60 at 10.94 WAR, so the model liked him slightly MORE than his grade,
consistent with his five all-positive drivers. The affine map shrank him to 8.49
WAR and FV 56.5, i.e. -4.3 against a consensus of 60.8.

The mechanism is not subtle: the map is fitted where the mass is (71% of rows sit
at or below 0 WAR) and applied where it is not. A single slope cannot serve both
ends, which is exactly what the failed clause was warning about. Reporting a failed
clause and then discovering it inverts the top tier is new information, not a
second bite at the same measurement.

## What is being fitted

A monotone, strictly increasing map `g: war -> war` replacing
`apply_dispersion_correction`, fitted OUT OF FOLD on the production frame
(`efv_model.SCORED_YEARS`, 11 folds), exactly as the affine map was.

Candidate families, all monotone, declared in advance so the set cannot grow after
seeing results:

1. **Isotonic regression** of realized on predicted, monotone by construction,
   with linear extrapolation above the highest fitted knot so the sparse top is not
   pinned to a constant.
2. **WAR-weighted affine**: the same affine family, least squares weighted by
   `1 + realized_war` so the tail is not outvoted by the mass at zero.
3. **Monotone piecewise-linear on prediction quantile knots** (deciles), with the
   top knot's slope constrained to >= 1 so the correction cannot shrink the top.

All three are fitted the same way, judged by the same clauses, and reported
together. No family is added after the first look.

## HARD clauses. All four must hold. A partial pass is a NO_SHIP.

1. **Slope CI95 covers 1.0 on BOTH sides.** Unchanged from the original gate.
2. **TAIL MAE MUST NOT WORSEN, on either side.** Top decile of realized WAR.
   PROMOTED from reported to GATING. This is the clause the affine map failed and
   the reason this lane exists; it is not permitted to be reported and waived twice.
3. **The elite tier must not invert.** Mean `eFV - consensus` over served rows with
   `consensus_fv >= 55` must be `>= 0`. Measured on the served board, not on the
   fold pool, because the defect was found on the served board.
4. **The low-end repair must be retained.** Rows pinned at the -2.0 floor must stay
   materially below the uncorrected count, and the sub-45 cohort's mean
   `eFV - consensus` must stay better than the uncorrected -10.97.

Clause 4 exists so this lane cannot "pass" by quietly reverting to the identity
map. Clause 3 exists because the affine map satisfied every error metric that was
gated while inverting the thing a reader actually looks at.

## Controls

- **Identity control.** The identity map must FAIL clause 4. If it passes, clause 4
  is not discriminating and the gate is void.
- **The affine incumbent is re-measured in the same run**, at the same folds and
  seeds, and reported beside the candidates. Never compare a fresh candidate to a
  stored incumbent figure.
- **Monotonicity is asserted, not assumed**, on a dense lattice for every shipped
  family. A non-monotone map reorders the board and is an abort.

## Abort conditions

- ABORT if no family clears all four clauses. The affine map stays, this document
  becomes its loss ledger, and the elite deflation is disclosed in copy instead.
- ABORT if a winning family is not strictly increasing.
- ABORT on any attempt to widen the candidate set after results are seen.

## If a family ships

It is another GRADE-BASIS EPOCH on top of tonight's: epoch bump, a fingerprint term
naming the family and its parameters, `prospx_current` re-capture, golden restamp,
and a full margin re-read. The routed cohort must again be preserved exactly
(routing decided on the UNCORRECTED grade), and the served surplus and re-rank must
be re-measured rather than inherited from tonight's run.

## Separately, and regardless of the outcome: the factor explainer is incoherent

Made's five factor chips all read `up` while the served delta is -4.3. The chips
explain the model's deviation from the consensus anchor in WAR space; the displayed
delta is a difference between two different FV scales, and that scale offset is not
any driver. So the explainer cannot reconcile with the number beside it no matter
which family wins. Tracked as its own fix, not gated here.

## Results

Measured 2026-08-14, `tools/efv_tail_preserving_lab.py 400`, artifact
`data/xfv_tail_preserving_eval.json`, production frame, leave-one-fold-out.

**ABORT. No family clears all four clauses.**

| family | slope hit / pit | c1 | tail MAE hit | c2 | elite eFV-cons | c3 | c4 | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| identity (control) | 0.689 / 0.674 | FAIL | 7.44 -> 7.44 | PASS | +0.14 | PASS | **FAIL** | NO_SHIP |
| affine (incumbent) | 0.985 / 1.077 | PASS | 7.44 -> 8.69 | FAIL | -4.95 | FAIL | PASS | NO_SHIP |
| war-weighted affine | 0.569 / 0.422 | FAIL | 7.44 -> 5.38 | PASS | +7.91 | PASS | PASS | NO_SHIP |
| isotonic + lin extrap | 0.880 / 0.719 | FAIL | 7.44 -> 8.31 | FAIL | -3.47 | FAIL | PASS | NO_SHIP |
| quantile piecewise | 1.200 / 1.170 | PASS | 7.44 -> 9.24 | FAIL | -6.36 | FAIL | PASS | NO_SHIP |

The identity control FAILED clause 4 as the gate required, so clause 4 discriminates
and the abort is clean rather than an artifact of an inert gate.

### The negative result has a shape, and the shape is the finding

**Every family that calibrates the slope deflates the elite. Every family that
preserves the elite fails the slope.** Five families, no exceptions, and the split
is exact:

- slope in CI of 1.0: affine (0.985/1.077), quantile piecewise (1.200/1.170).
  Elite: -4.95 and -6.36.
- elite preserved: identity (+0.14), war-weighted (+7.91). Slope: 0.689 and 0.569.

This is not five coincidences. Driving the OOS slope to 1.0 REQUIRES shrinking high
predictions, because the model genuinely over-predicts at the top out of sample.
Preserving the elite tier means declining to shrink a prediction the out-of-sample
evidence says is too high. **On this predictor the two goals are in direct conflict,
and no monotone map resolves it.** That is a fact about the model, not about the
functional forms tried.

The uncomfortable reading, stated plainly: eFV serving Jesus Made 4.3 FV below
consensus may be eFV being RIGHT and disagreeing with scouts, rather than eFV being
broken. The model's raw 12.08 WAR for him is the number the OOS record says is
inflated. What the affine map costs is not accuracy at the top, it is agreement
with the industry at the top, and this lane cannot tell those apart because the
elite cohort is 14 rows.

### A flaw in my own clause 3, recorded rather than fixed

Clause 3 was written one-sided (`mean elite eFV - consensus >= 0`). The
war-weighted family satisfies it at **+7.91**, i.e. by inflating every grade about
eight points ABOVE consensus, which is plainly not what the clause intended. It
fails clause 1 anyway so nothing turns on it operationally.

The clause is NOT amended, because amending a clause after seeing which family
exploits it is the exact move this programme bans. It is recorded here so the next
registration writes a two-sided band instead.

### What ships

Per the pre-registered abort condition: nothing. The affine map stays in place, and
this document is its loss ledger. Note that the incumbent it leaves in place fails
two of these four clauses; the alternative (identity) fails two different ones. **No
option available tonight is clean**, which is why the choice between them is
referred rather than taken by this lane.
