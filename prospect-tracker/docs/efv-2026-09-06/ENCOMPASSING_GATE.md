# A-CLAIM-6: does the model leg add anything to consensus? UNDECIDED, both sides.

Date: 2026-09-06. Verdict: **UNDECIDED on both sides.** No served number moves; this lane
publishes a diagnostic and a refusal to claim.

## The question

The board's headline rank is a blend: `(1-lam) * cons_war + lam * model_war`. That is only
worth doing if the model leg carries information the consensus anchor does not. Forecast
encompassing asks it directly:

```
y = a + b1 * cons_war + b2 * model_war + fold fixed effects
```

fitted **out of fold** on `target_censored`, per side, on the `debuted_km` cut. If consensus
already contains everything the model knows, `b2` is zero and the model leg is decoration.

**Regressors are WAR-scale objects only**, never the 20-80 grade, and never the blend
beside its own components: `blend = (1-lam)*cons + lam*model` is an exact linear
combination of the two regressors, so including it is perfect collinearity rather than a
third opinion.

| regressor | definition |
|---|---|
| `cons_war` | `max(0, ols(consensus_fv))`, the consensus anchor, floored to match the baseline |
| `model_war` | `max(-2, a + b*ridge(feats))`, the **served** leg: calibrated per fold, clamped, which is what `oos_grades` blends and therefore what the board carries |

Fold fixed effects absorb the level shift between cohort years, so `b2` is a **within-fold**
statement and cannot be bought by the model tracking a cohort trend consensus misses.

## Verdict rule, fixed before the run

**A player-clustered bootstrap CI95 covering zero prints UNDECIDED.** Not "small but
positive". Not "trending". UNDECIDED.

## Result

| side | rows | players | b1 (consensus) | b2 (model) | CI95 | verdict |
|---|---|---|---|---|---|---|
| hit | 761 | 761 | +0.6749 | **+0.2203** | [-0.0987, +0.5952] | **UNDECIDED** |
| pit | 900 | 900 | +0.9558 | **+0.1301** | [-0.1509, +0.4191] | **UNDECIDED** |

`b2` is positive on both sides and neither interval excludes zero. On this frame, at this
sample size, **the model leg does not measurably add to the consensus anchor out of fold.**

Note `n_players == n_rows` on both sides: on `debuted_km` each player appears once, so the
player clustering is a no-op here and the interval is not being widened by it. That is
worth stating because a clustered interval that covers zero invites the suspicion that the
clustering did it. It did not.

## Both nulls, and they disagree with each other

| side | null | mean | band95 | reading |
|---|---|---|---|---|
| hit | permuted model residual within fold | -0.0278 | [-0.2546, +0.1793] | p(two-sided) **0.048** |
| hit | zero-information twin | +0.0006 | [-0.0899, +0.0862] | estimator is sound |
| pit | permuted model residual within fold | -0.0297 | [-0.2349, +0.1816] | p(two-sided) **0.248** |
| pit | zero-information twin | -0.0015 | [-0.1323, +0.1349] | estimator is sound |

**Null 1** regresses the model leg on `cons_war` inside each fold, permutes the residual
within that fold, and rebuilds `model = fit + permuted residual`. This destroys the model's
row-level information while preserving its marginal **and** its correlation with consensus,
so it is what "adds nothing beyond consensus" looks like at this n.

**Null 2** is a Gaussian covariate with the model leg's own mean and sd, independent of
everything. Both sides return ~0.000 with tight bands, so the estimator is not manufacturing
a coefficient out of the fixed-effect structure. Without this check the real number would
mean nothing.

### The hitter side disagrees with itself, and the pre-registered rule wins

The permutation null gives p = 0.048 on hitters, which would read as "significant" at the
usual bar, while the clustered bootstrap CI contains zero. **The CI is what was
pre-specified, so the verdict is UNDECIDED.** Switching to the permutation p because it
gives the nicer answer is precisely the fishing the rule exists to prevent.

They differ because they hold different things fixed. The permutation null holds the
**sample** fixed and destroys only the model's row-level information, so it prices one
question: given these 761 players, could this `b2` arise from a model that knows nothing
extra? The bootstrap resamples **players**, so it also carries uncertainty about which 761
players we drew, which is the question a claim about the model has to survive. The
bootstrap is the wider and more conservative statement, and it is the one on the record.

## What this does and does not say

It says: on `debuted_km`, out of fold, with fold fixed effects, the served model leg does
not measurably improve on the consensus anchor. It is consistent with
`docs/efv-2026-09-06/SERVED_LEG_BASIS.md`, where changing which model leg goes into the
blend also produced a null.

It does **not** say the model is worthless. `b2` is positive on both sides, the point
estimates are not small relative to `b1`, and an interval that covers zero is a statement
about power as much as about effect. It does not license removing the model leg, changing
`lam`, or publishing "the model adds nothing".

It also does not extend past this frame. The 802-row vintage-matched set named in the plan
is not scored here; that frame is built inside `source_backtest` and reaching it is a
separate piece of work, recorded as owed rather than quietly dropped.

## Reproduce

```
python tools/efv_encompassing.py data/xfv_encompassing_eval.json
```

B = 2,000 bootstrap draws, B = 500 per null, seed 20260906. One fit per fold; the
calibration `(a, b)` is fitted on the fold's TRAIN rows only, exactly as `oos_grades` does
it, so the regressor is the object the board carries and not a refit of it.
