# Hitter `age` sign declaration, adjudicated (2026-08-04)

**Verdict: KEEP the feature, MOVE the declaration to `0`.**
`efv_model._FEATURES_HIT`: `("age", -1)` -> `("age", 0)`.
Ledger: `data/xfv_hit_age_sign_gate.json`. Lab: `tools/_sweep_signs.py` (unmodified).
Gate standard: `docs/EFV_GATE_STANDARD.md` section 6.

## The red

`test_efv_sign_declarations::test_flagship_fitted_signs_match_declarations[hit]`.
Hitter `age` is declared `-1` (older is worse). On the matrix the pipeline rebuilt on
2026-08-04 (n 1883) the served ridge fits **+0.0420**, marginal weighted Pearson
**+0.0165**, classified `WRONG_SIGN` by `efv_sign_audit`.

This is the same latent class as the pitcher `age` (2026-07-25) and pitcher
`age_rel_level` (2026-07-30) corrections. It was adjudicated by the same four steps.
**Two of the four land differently on the hitter side and are recorded as such rather
than assimilated to the precedent.**

## Step 1: suppressor check (marginal vs fitted). NOT a suppressor.

| quantity | value | side |
| --- | --- | --- |
| served ridge weight (standardized) | **+0.0420** | against declaration |
| marginal weighted Pearson | +0.0165 | against declaration |
| marginal Spearman (rank) | **-0.0547** | *with* declaration |
| unregularized OLS partial | +0.0119 | against, below noise floor |
| `age_rel_level` served / marginal | -0.2159 / -0.2146 | with declaration |

`efv_sign_audit` calls SUPPRESSOR only when the MARGINAL agrees with the declaration
while the partial does not. Here the Pearson marginal is on the same side as the fit,
so the defence the pitcher case had (marginal -0.0543) **is not available**.

But the marginal is not reliably signed either way: the rank marginal is -0.0547, on
the declared side, and the OLS partial +0.0119 is **below the audit's own `NOISE_W`
0.02 floor**. The served +0.0420 is 2.1x that floor and the second-smallest weight in
the hitter set. Nothing measured supports `-1`; nothing measured supports `+1`.

The age block's declared negative direction is intact. It just does not live in this
column: `age_rel_level` carries it at -0.2159 served / -0.2146 marginal.

### Stability

Informative folds 2016..2024 (2014/2015 degenerate, excluded):

```
-0.1507  +0.0232  -0.2754  -0.0340  +0.0534  +0.1002  +0.1231  +0.0479  +0.0621
train n:  265  360  472  646  845  1014  1141  1392  1641
```

6 of 9 positive, **fold-weight mean NEGATIVE (-0.0056)**, range -0.2754 to +0.1231.
The same drift with sample size the pitcher case had (the 5 largest folds all
positive), but the magnitudes never leave the noise band. Unstable sign, not a stable
positive one.

### What moved, and what did NOT

The 2026-07-25 ledger has this column at served **-0.0619**, marginal -0.0506,
OLS -0.1305, negative in **9 of 9** folds, `sign_stable_across_folds: true`, on n 1882.
One matrix rebuild later it is +0.0420 on n 1883.

**It is not the C1 decimal-age ship**, which is what moved the pitcher side. Tested
directly on the same rows: rounding the age column back to integers does not restore
the declared sign, it goes MORE positive (**+0.0520**, and **+0.0668** with
`age_rel_level` also rounded), and the marginal stays positive (+0.0205). The feature
column is not what moved. The marginal correlation of age with realized WAR went
-0.0506 -> +0.0165 on the same pool, which is a **label-side** change out of the
2026-08-04 rebuild. Isolating which label change is outside this lane.

## Step 2: collinear split. CONFIRMED. (Divergence #1 from the precedent.)

| test | value |
| --- | --- |
| r(`age`, `age_rel_level`) | +0.518 |
| `age` refit with sibling removed | **-0.0502** (snaps back to declared) |
| `age_rel_level` refit with `age` removed | -0.1952 (barely moves from -0.2159) |

By `_sweep_signs`' own rule (`split = contradiction AND the partner-dropped refit no
longer contradicts`) this is a **COLLINEAR_SPLIT**: one age signal divided arbitrarily
across two columns, not an independent conditional effect.

**On pitchers the same test came out the opposite way**, and that is precisely what
earned the 2026-07-30 case its "independent conditional effect" reading: dropping `age`
pushed pitcher `age_rel_level` MORE positive (+0.0418 -> +0.0916). Here it snaps back.
The hitter contradiction is therefore *weaker* evidence for a real positive effect than
the pitcher one was.

**Merge remedy: already rejected**, 2026-07-25, `data/xfv_sign_merge_gate.json` key
`hit:age+age_rel_level`. Merging the pair into one z-mean column is itself a null
(+0.00033 = 0.02x the 0.017 floor, the smallest effect in that entire set, CI95
[-0.0256, +0.0121], p_merge_helps 0.374). Not re-run. It would also move served
numbers, which a correctness fix must not.

## Step 3: fresh drop gate. Sub-floor NULL.

Pit-`age` protocol, run fresh on the 2026-08-04 matrix: 11 forward-chained splits
(train = `decision_year < Y`), the shipped blend leg at lambda 0.70 with the consensus
OLS anchor refit on the same train rows, paired bootstrap B=2000 resampling TRAIN AND
TEST with a refit per draw, a zero-information control (same column row-permuted and
KEPT in the set), and a 1000-draw permutation null.

| | |
| --- | --- |
| pooled rho WITH `age` | 0.2717 |
| pooled rho WITHOUT `age` | 0.2784 |
| delta (drop minus keep) | **+0.00669** |
| vs 0.017 hit MDE95 | **0.393x** |
| bootstrap B=2000 mean / CI95 | +0.00249 / **[-0.00421, +0.01084]** |
| P(drop helps) | 0.824 |
| **zero-information control** | **+0.0062** (93% of the candidate) |
| permutation null p (two-sided) | 0.150 |
| folds where dropping helps | 6 of 11 |

Dropping HELPS, but at 0.393x the floor with a CI straddling zero, and **the
row-permuted control reproduces 93% of it**. Destroying the column's information while
leaving it in the model buys almost exactly what removing it buys, so the "gain" is not
a gain from removing information. The fold deltas are dominated by 2018 (+0.0601); the
other ten are inside +/-0.012.

EFV_GATE_STANDARD section 6: *"Do not add and do not remove features on sub-floor
evidence."* **The feature stays.**

## Step 4: the declaration moves to 0

* **not `-1`**: the served ridge fits +0.0420 against it. That is the red.
* **not `+1`**: would require a stable, theory-defensible "older hitters are better".
  Every probe refuses it. 6 of 9 folds positive but a negative fold mean; rank marginal
  -0.0547; OLS partial +0.0119 below the noise floor; the sign inverts to -0.0502 the
  moment the collinear sibling is removed; and it was -0.0619 and negative in 9 of 9
  folds one rebuild ago. A direction that inverts when the label is redefined is not
  theory.
* **`0`** = no directional claim, a legal LightGBM constraint. The declaration this
  codebase has used five times for exactly this situation (hit `k_rel` /
  `n_milb_seasons` / `milb_missing` and pit `age`, 2026-07-25; pit `age_rel_level`,
  2026-07-30).

**No served number moves.** The declaration is consumed only by
`efv_model._fit_lgbm_mono`'s `monotone_constraints`, which binds the eval-only LightGBM
challenger. The shipped ridge (`fit_production_stack` -> `prospect_path._fit_ridge`)
ignores it. Correctness fix, no accuracy claim, none required.

`test_efv_sign_declarations.py`: **15 passed.**

## Follow-ups OUTSIDE this lane (reported, not patched)

1. **`test_efv_model.py:142`** pins `("age", -1)` in `_EXPECTED_HIT` and will go RED.
   It needs `("age", 0)`, exactly as `_EXPECTED_PIT` was updated on 2026-07-25/30.
   **This is a hard blocker on the commit.**
2. **`efv_score.py:536-537`** asserts *"The hitter side keeps its Age chip: there `age`
   fits -0.0619, agreeing with its declaration"*. Both halves are now false. Separately,
   a **display decision**: with w +0.0420 and train mean 22.10, a hitter YOUNGER than
   the mean gets a NEGATIVE contribution, so the Age chip reaches ~150 of 2,128 live
   hitter cards and **134 of them read DOWN on young hitters**. Same defect class as the
   Ryan Sloan pitcher bug (1,058 of 2,393 cards, 44.2%), at 7.1% incidence. Whether
   hitters join `pit` in `_EXPLAINER_SKIP_SIDE` is an owner call.
3. **`data/model_registry.json`** needs a row for `data/xfv_hit_age_sign_gate.json`.
   Deliberately NOT named `*_eval.json`, so it does not trip
   `test_model_registry::test_every_eval_artifact_is_registered` mid-sweep, same
   convention as `xfv_sign_audit.json`.
4. **Open question for the orchestrator**, not adjudicable here: the hitter `age`
   marginal inverted on a fixed pool across the 2026-08-04 rebuild. If that rebuild
   changed the hitter WAR basis, every other age-linked declaration and every published
   sign table dated before it is quoting a retired label.
