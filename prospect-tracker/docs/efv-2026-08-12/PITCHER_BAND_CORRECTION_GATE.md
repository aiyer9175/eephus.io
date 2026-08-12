# E2b-narrow: correct the FV 45 band where pitchers are under-graded

Pre-registered 2026-08-12, BEFORE the lab existed. Committed alone so git
timestamps it. Producer: `tools/efv_side_correction_lab.py`. Artifact:
`data/xfv_side_correction_eval.json`.

## Where this comes from

E2a (`SIDE_CALIBRATION_GATE.md`) measured, against realized WAR:

- At consensus FV 55, pitchers realize 8.58 WAR LESS than hitters. The industry
  over-grades top pitchers; eFV's low top-end pitcher share is vindicated.
- **At eFV 45, pitchers realize +1.13 [0.19, 2.04] WAR MORE than hitters holding
  the same eFV grade.** On eFV's own value scale those pitchers are undervalued.

Owner decision after seeing it: **narrow fix plus publish**, explicitly rejecting
blanket cross-side parity because it would promote the cohort measured to
underdeliver. The publish half shipped. This is the fix half.

## The reopen burden, discharged in the open

A **global per-fold linear recalibration of predicted WAR was tested
forward-chained on 2026-06-25 and REJECTED** (it worsened FV55+ MAE and bias),
and the standing instruction is not to re-attempt the tail fix blind. This lane
is deliberately not that, and the differences are the reason it is allowed to
run at all:

- that one was **global**; this is **per side**, and the effect being corrected
  is a side difference that a global map cannot see by construction;
- that one targeted the **FV55+ tail**; this targets the **FV 45 middle**;
- that one was **linear**; this is **monotone/isotonic**, so it cannot invert an
  ordering;
- and it is opened by **new evidence** (E2a) plus a **new owner instruction**,
  which is exactly the registered reopen burden.

If this lane fails its gate it joins the same ledger and is not re-attempted.

## Estimand

Does a per-side monotone recalibration of predicted 6-year WAR, fitted on
EARLIER grade cohorts, reduce the pitcher-minus-hitter realized-WAR gap in the
FV 45 band on LATER cohorts, without degrading overall calibration?

**Frame.** Resolved pool, kind in (debuted, bust), busts at realized WAR 0. The
cohort axis is the YEAR THE SCORED GRADE WAS GIVEN: for a graduate that is the
last pre-debut snapshot, which is the debut year; for a bust it is the final
snapshot. Both are the same quantity ("when was this grade current"), which is
what makes them poolable on one axis.

**Folds.** Forward-chained. Fit on all cohorts up to year Y, evaluate on Y+1,
for every Y with at least 150 training rows and 60 evaluation rows a side. No
row is ever evaluated by a model that saw it.

**Correction.** Per-side isotonic regression (PAVA, `sklearn.isotonic`) of
realized WAR on predicted WAR, fitted on training folds only, applied to
predicted WAR before the grade map. Monotone by construction, so it is
rank-invariant WITHIN side and cannot re-open the closed rank frontier.

## Ship rule, fixed now

All three must hold on the pooled held-out folds:

1. **The band gap shrinks.** |gap| at FV 45 after correction is smaller than
   before, and the improvement's bootstrap interval (B=2000, seed 20260812)
   excludes zero.
2. **Overall calibration does not degrade.** Per-side mean absolute error of
   predicted vs realized WAR is no worse than the incumbent on either side,
   within a 0.02 WAR tolerance.
3. **The tail is not disturbed.** Mean absolute error on rows at eFV 55+ is no
   worse than the incumbent, on either side. This clause exists specifically
   because the 2026-06-25 rejection was a tail regression, and a correction that
   fixes the middle by breaking the top is that failure again under a new name.

**If any clause fails the correction is a NO-SHIP** and the result is recorded as
a loss on the registry row. A null here is a legitimate outcome and is the
expected one if the FV 45 effect is a single-band artifact rather than a
recoverable bias: it is 1 of 4 scored cells, and its interval nearly touches
zero.

## What ships either way

The measurement and its verdict. Nothing about the served grade changes unless
all three clauses hold, and if they hold the change is one coordinated epoch
with the rookie-window unlock already on this branch, since both re-anchor
served grades and neither should be regenerated twice.

## Results (2026-08-12, `data/xfv_side_correction_eval.json`)

**VERDICT: NO_SHIP.** All three clauses fail. 13 forward-chained folds, 4,300
rows evaluated by a model that never saw them.

| clause | before | after | verdict |
| --- | --- | --- | --- |
| 1. FV 45 band gap | 1.2663 | 0.0028 | **FAIL** (improvement CI [-0.636, 1.429] includes zero) |
| 2. overall MAE, hitters | 2.4373 | 2.5571 | **FAIL** (worse) |
| 2. overall MAE, pitchers | 1.6090 | 1.6442 | **FAIL** (worse) |
| 3. tail MAE, hitters (n=126) | 9.4960 | 12.2249 | **FAIL** (worse) |
| 3. tail MAE, pitchers (n=3) | 20.9500 | 23.6288 | **FAIL** (worse) |

### Clause 1 is the instructive one

The correction very nearly ERASES the band gap out of sample, 1.27 to 0.003.
Read alone that looks like a triumph. It is not: the bootstrap interval on the
improvement is **[-0.636, 1.429]** and includes zero, so a gap that size shrinks
to nothing about as often by chance on this sample. **A point estimate that
lands on zero is not evidence that the thing was fixed.** This is the same
demotion the rest of the site applies, and pre-registering the interval is what
stopped the headline number from being reported as a win.

### Clause 3 caught the exact failure it was written for

The 2026-06-25 rejection killed a global linear recalibration because it worsened
the FV55+ tail. Clause 3 existed because a correction that fixes the middle by
breaking the top is that failure wearing new clothes, and **that is precisely
what happened**: hitter tail error rises 9.50 to 12.22, a 29 percent
degradation, while the middle improves. Per-side and isotonic did not save it.

The mechanism is not mysterious. Fitting a monotone map on a pool where most
mass sits near zero WAR pulls the sparse high end toward the crowd, and the tail
is where the dollars and the board order live.

### What this means for the owner decision

The owner chose **narrow fix plus publish** after E2a. The publish half shipped
and stands. **The fix half is now a measured loss and does not ship.** The FV 45
under-grade is real in sample and is NOT recoverable by this correction family
out of sample, which is the honest end of this lane rather than a reason to try
a third family on the same cell.

### Registered as closed

`xfv_side_correction` is registered **deprecated** carrying this artifact as its
loss ledger. It joins the banned ledger beside the 2026-06-25 tail fix: **do not
re-attempt a WAR-recalibration correction for the FV 45 side gap.** The reopen
burden is new DATA (more resolved cohorts, which arrive on their own clock), not
a new functional form.

The served grade map is unchanged. eFV's low pitcher share remains what E2a
measured it to be: the more accurate reading of value at the top, with a real
but unrecoverable under-grade in one middle band.
