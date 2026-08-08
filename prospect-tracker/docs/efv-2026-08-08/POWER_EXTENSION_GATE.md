# M1 pre-registration: extend the conditional floor to the statistic classes that carry the claims

**Sections 0 through 7 were written BEFORE the extension lab existed and BEFORE any new
floor was computed.** Section 8 holds literal placeholders the lab fills in.

Plan: `docs/master-plan-2026-08-08-efv-conviction.md` lane M1 and section 9.1.
Incumbent registration: `docs/efv-2026-08-07b/POWER_GATE.md`, `docs/EFV_GATE_STANDARD.md`
section 7. Wave-0 input: `docs/efv-2026-08-08/WAVE0_RECORD.md` section 6.

---

## 0. Why this lane exists

Two estimators are registered. Only one is wired, and it is wired for only four cuts.

| estimator | resamples | estimand |
|---|---|---|
| E_refit (shipped) | whole pool, train AND test, refit per draw | what would we conclude from a different dataset |
| E_cond (registered, unwired) | scored rows only, per-fold fits held FIXED | given THIS training corpus, is this margin real |

E_cond floors exist for exactly four cuts (hit/pit x full_pool_km/debuted_km). **They do
not exist for the head-to-head common set, block-rho, incremental feature-add, or
lambda-shift, which are the statistics the site's actual claims are made on.**

Owner decision 1 (2026-08-08) adopted the dual-estimator policy: every claim names its
estimator, ship gates clear E_cond and must not be contradicted by E_refit.

## 1. The measured fact that motivates the extension, and its limit

Refit variance is **54.1%** of shipped variance on the hitter full pool (measured on our
own data 2026-08-08: shipped sd 0.01848, test-only 0.01253, train-only 0.01112). So driving
test n to infinity cannot remove roughly half the floor, and **more cohorts cannot fix
power.** This is also the analytic explanation for the 4-to-11-fold promotion moving the
floor by zero.

**The limit, stated before the result so it cannot be spun afterwards:** the head-to-head
statistic refits only the eFV leg (the consensus leg is the raw published grade), so its
conditional shrink should be SMALLER than the 0.45x-0.71x seen on the pooled-rho cuts.
A large shrink there would be evidence of an implementation error, not of power.

## 2. Statistic classes to floor

1. `headtohead_common` (n about 3,210 rows over about 1,050 players) - carries the site claim.
2. `block_rho` (n about 1,644) - the registered higher-SNR instrument.
3. `feature_add` - the gate every driver lane needs.
4. `lambda_shift` at steps 0.05, 0.10 and 0.19 (the 0.70 to 0.51 distance between the pin
   and the selector's own argmax).
5. `pooled_rho` for the existing four cuts, recomputed for byte-comparability with the
   incumbent registration.

## 3. Binding design constraints (violating any one invalidates the lane)

1. **Clustering is preserved.** The head-to-head class MUST resample BY PLAYER (about 3.06
   rows per player). Switching to i.i.d. rows would narrow the floor by roughly 1.27x-1.75x
   in the ANTI-CONSERVATIVE direction. **Any width "gain" that appears when clustering is
   dropped is a defect, not a result.** Wave 0 verified the incumbent labs already cluster
   correctly and that both matrices are one row per player.
2. **The registered four cuts must reproduce byte-for-byte** under the generalized
   estimator in row mode, same seed, same draws. If they do not, the generalization is
   wrong and nothing else in this lane is trustworthy.
3. **Two-sided coverage per class.** A new statistic class does NOT inherit E_cond's
   registration. Each needs its own coverage check against its own conditional estimand,
   with a central binomial acceptance region and n_check sized so the upper edge is
   strictly below 1.000. One-sided coverage is the named defect in gate standard 7.4.
   For the head-to-head class this requires extending the simulator to emit k rows per
   player; a single-row-per-player DGP cannot check a clustered estimator.
4. **No RNG stream may be derived from a set or `hash()`**, and no draw may be inserted
   into an existing function: the incumbent `verdict()` shares one generator across three
   estimators sequentially, so an inserted consumption silently moves every published
   number. Use unused seed offsets.
5. **Do not reuse the `k=4` Bonferroni label.** `Z_BONF4_ONE` and the literal
   `mde95_bonferroni_k4` are hardcoded for a four-member family. A larger family needs a
   parameterized k, and the plan calls for Holm.
6. **Use the unrounded Spearman primitive.** The shipped `_weighted_spearman` rounds to 4
   decimals, which quantizes a bootstrap sd at the scale of the effect being measured.
7. **Read-modify-write the artifact.** The incumbent writes the whole file in one shot;
   a new sub-command that clobbers `verdict` or `coverage` destroys the registration.

## 4. PASS clauses for the EXTENSION ITSELF (not for eFV)

This lane ships an instrument, so its gate is about the instrument:

1. **X1 parity.** The four registered cuts reproduce exactly.
2. **X2 coverage.** Each new class passes its own two-sided coverage gate at its own
   estimand.
3. **X3 detection.** Each new class detects the known-real hitter `fv` effect wherever the
   shipped estimator does. An instrument that cannot see a known effect is not tighter, it
   is broken.
4. **X4 it can resolve losses.** The check that E_cond is not power laundering is that it
   resolves losses as readily as wins. If the extension resolves only wins, it is refused.

## 5. Adjudication, after the instrument passes

Cells adjudicated with Holm across the family, each reported under BOTH estimators, on the
REBUILT basis. Pre-committed and all acceptable:

- head-to-head certifies under E_cond, contradicted by neither estimator: owner decision 7
  applies and the site claim gains conditional wording.
- head-to-head stays null: the honest tie stands and the gate standard records it as
  unresolvable under both estimators at current n.
- hitter `full_pool_km` resolves as a LOSS again: it is published as one.

## 6. THE OBLIGATION WAVE 0 CREATED

`EFV_GATE_STANDARD.md` section 7.5 currently publishes hitter `full_pool_km` as the one
cell E_cond resolves, at 1.049x its floor with bootstrap p 0.0415. **On the rebuilt basis
the delta is -0.0190, which is 0.93x of the REGISTERED floor.** Because floors are
functions of the data, that comparison is incomplete until the floor is re-derived here.

This lane MUST publish one of exactly three outcomes, and section 7.5 is superseded in all
three:

- **still resolves** on freshly derived floors: 7.5 is restated with new numbers.
- **no longer resolves**: 7.5 is superseded and the retraction is explicit, because the
  claim was published and other work may have relied on it.
- **the floor moved enough to change the verdict in either direction**: reported as the
  headline, since it would mean the registration was basis-dependent.

## 7. Stop clauses

- **No floor shopping.** If the head-to-head E_cond floor lands above the observed margin,
  record it and close the cell. A third estimator is NOT sought, and this clause exists
  because the temptation is strongest exactly here.
- If X1 parity fails, the lane stops and reports the parity failure. Nothing downstream is
  reported from a generalization that cannot reproduce its own incumbent.
- If a class cannot be given an honest coverage check (the clustered DGP being the live
  risk), that class is reported as UNFLOORED rather than floored on the incumbent's
  registration.

## 8. RESULTS (literal placeholders; the lab fills these in)

```
STATUS: NOT RUN
X1_parity_four_cuts:            <PENDING>
X2_coverage_per_class:          <PENDING>
X3_detection_known_effect:      <PENDING>
X4_resolves_losses:             <PENDING>

floors_refit:                   <PENDING>
floors_cond:                    <PENDING>
  headtohead_common:            <PENDING>
  block_rho:                    <PENDING>
  feature_add:                  <PENDING>
  lambda_shift_0.05/0.10/0.19:  <PENDING>

adjudication_holm:              <PENDING>
hit_full_pool_verdict:          <PENDING>
section_7_5_disposition:        <PENDING>
VERDICT:                        <PENDING>
```
