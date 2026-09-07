# A-CLAIM-5: the eval blend and the served blend are two objects, and the difference is nil

Date: 2026-09-06. Status: **MEASURED. The false claim is corrected; the refactor is NOT
shipped, and section 5 says why.** No served number moves.

## 1. The two objects

```
_run_eval   (efv_model.py)   (1-lam) * max(0, ols(fv)) + lam * _predict(ridge, feats)
oos_grades  (efv_model.py)   (1-lam) * max(0, ols(fv)) + lam * max(-2, a + b*_predict(ridge, feats))
```

`a, b` come from `_fit_linear_calibration` fitted on that fold's training rows. So the eval
scores the **raw** ridge inside the blend and the served path scores the **calibrated,
clamped** ridge inside it.

The eval's own comment read:

> `# blend == the SHIPPED headline rank: (1-lam)*consensus_OLS + lam*model`

That is false, and it is the thing this pass fixes.

A linear calibration is monotone, so it cannot reorder the ridge on its own. What it does
is re-scale the model leg **relative to the consensus leg it is blended against**, and that
does reorder the blend. Measured on the `debuted_km` cut:

| side | rows | rows where the two blends are identical |
|---|---|---|
| hit | 761 | **0** |
| pit | 900 | **0** |

Stated plainly: **0 of 761** hitter rows and **0 of 900** pitcher rows carry the same blend
value under the two bases. Not "few". None.

## 2. What the difference costs

Paired, on identical rows, one fit per fold, fold-clustered bootstrap, B = 2,000:

| side | eval basis | served basis | delta | CI95 | P(served higher) |
|---|---|---|---|---|---|
| hit | 0.3952 | 0.3996 | **+0.0044** | [-0.0026, +0.0117] | 0.889 |
| pit | 0.2948 | 0.2945 | **-0.0003** | [-0.0072, +0.0065] | 0.490 |

Both intervals contain zero and the two sides point in opposite directions. **No published
rho is wrong by a measurable amount.** The defect was the claim of identity, not the number
beside it.

This is the specific pair that memory has carried as "rank-equivalence verdict UNRESOLVED,
must not be cited". For THIS pair, on THIS cut, it is now resolved as a null. It says
nothing about the separate served-vs-blend question on the 20-80 grade, which is a
different object again (`xfv_grade` maps from `xfv_war`, the model leg, while `rank_war` is
the blend).

## 3. Two published rho families, on two bases and two frames

Worth stating plainly, because they get quoted next to each other:

| artifact | figure | basis | n |
|---|---|---|---|
| `data/source_backtest.json` `accuracy.pooled.xfv` | 0.3596 | SERVED (oos_grades) | 3,270 |
| `data/xfv_eval.json` `evals.debuted_km.pooled_oos.blend` | 0.3925 | EVAL (raw ridge) | 755 |

Different bases **and** different frames. They were never comparable and neither is wrong;
they answer different questions.

## 4. Why S0 could not pass, and it is not the harness

The plan gates the helper on reproducing six published numbers to 0.0010 first. Run today:

| side | leg | published | reproduced | delta |
|---|---|---|---|---|
| hit | baseline | 0.3821 | 0.3817 | 0.0004 |
| hit | ridge | 0.3889 | 0.3886 | 0.0003 |
| hit | blend | 0.3925 | 0.3952 | 0.0027 |
| pit | baseline | 0.2957 | 0.2998 | 0.0041 |
| pit | ridge | 0.2596 | 0.2736 | 0.0140 |
| pit | blend | 0.2828 | 0.2948 | 0.0120 |

**The frames are not the same frames.** `xfv_eval.json` and `xfv_eval_pitcher.json` are both
dated 2026-09-04; both feature matrices were rebuilt 2026-09-06. The `debuted_km` cut has
moved by **6 rows on the hitter side** (755 to 761) and **8 on the pitcher side** (892 to
900). The hitter baseline and ridge legs still reproduce to 0.0004 and 0.0003 through the
drift, which is the harness being faithful, not failing.

S0 is runnable the moment the eval artifacts are regenerated on the current matrices. It
was not run here because regenerating them is a pipeline step with its own downstream
consumers, not a measurement.

## 5. Why the helper did not ship

The plan asks for a `blend_war(cons, model, lam, basis)` helper across five call sites, with
`raw_ridge` for `_run_eval` and `calibrated_clamped` for `oos_grades` / `run_live`, gated on
S0 passing first.

Three things argue against landing it in this pass, and the first is decisive:

1. **The gate cannot run.** S0 fails on stale artifacts, so the helper would land unverified
   against the objects it is supposed to preserve. That is the exact shape of change this
   repo gates for a reason.
2. **The measured payoff is zero.** Section 2 is a null on both sides. A five-site refactor
   of the arithmetic behind every published eFV number, for a difference measured at zero,
   is risk with nothing on the other side of it.
3. **The arithmetic is already identical at every site**; only the leg fed to it differs.
   The helper would centralise a one-line expression, not a divergence. What was actually
   divergent was the DOCUMENTATION, and that is what has been fixed.

The reproduction is small enough to re-run from section 4 whenever the artifacts are fresh.
`test_blend_basis.py` pins the two bases apart so neither can quietly become the other, and
fails if the corrected comment is replaced by the claim it replaced.

## 6. Reproduce

One fit per fold on `debuted_km`, both legs evaluated on the same test rows, weighted
Spearman (a censored 2024 row carries 0.333, matching `_score`), fold-clustered bootstrap.
`em._fit_linear_calibration` is fitted on the fold's TRAIN rows only, exactly as
`oos_grades` does it.
