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

## 8. RESULTS

```
STATUS: PART A COMPLETE (the section 7.5 obligation, discharged 2026-08-08).
        PART B COMPLETE (2026-08-09): X1 parity, X2 clustered coverage, X3, X4, the five
        floors under both estimators, and the B-L2 adjudication.
```

### Part A: the re-derivation obligation from section 6, DISCHARGED

Producer `python tools/efv_power_lab.py all 2000`, seed 20260807, 4,089s, artifact
`data/xfv_power_eval.json`, on matrices and evals regenerated 2026-08-08.

```
X2_coverage_two_sided:   PASS. refit sd_ratio 1.454 cov 0.970; cond_iid 1.000 cov 0.930;
                         cond_strat 0.995 cov 0.925; acceptance [0.920, 0.980].
                         E_cond_iid re-registers as primary, as pre-registered.
X3_detection:            PASS, unchanged. debuted.ridge on hitter `fv` DETECTS under all
                         three estimators (point +0.05721 against 0.0443 / 0.0322 / 0.0330);
                         the three weaker arms miss under all three. The instrument still
                         sees the known-real effect.
X4_resolves_losses:      NOT DEMONSTRABLE ON CURRENT DATA. E_cond now resolves NOTHING in
                         either direction, so the previous "it resolved one cell and it was
                         a loss" evidence for non-laundering no longer applies as written.
                         Recorded as a limitation, not papered over.

refit_share_of_variance: 0.541  (shipped sd 0.01848, test-only 0.01253, train-only 0.01112)

hit_full_pool_verdict:   delta -0.01894, E_cond MDE95 0.0206 -> 0.921x -> NULL
                         (was -0.02143 against 0.0204 -> 1.049x -> RESOLVABLE LOSS)
section_7_5_disposition: SUPERSEDED, with an EXPLICIT RETRACTION written into
                         docs/EFV_GATE_STANDARD.md section 7.5.
```

All four cuts are NULL under both estimators on the rebuilt basis:
hit full_pool 0.921x, pit full_pool 0.660x, hit debuted 0.536x, pit debuted 0.211x (E_cond).

**The pre-registered three-outcome clause resolves to the second branch**: the cell no
longer resolves, and the retraction is explicit because the claim had been published.
**The floor barely moved (0.0204 to 0.0206); the DELTA moved.** The verdict flipped on the
data, not on the instrument, and the instrument re-validated on the new basis.

### Part B: the statistic-class extension

Every step is DISCHARGED 2026-08-09: parity, the clustered coverage DGP, the floors, X3,
X4 and the B-L2 adjudication. **The single most consequential number in this part is not a
floor: the shipped head-to-head margin is a property of the FRAME, and on the like-for-like
one-row-per-player pre-debut frame the two legs are tied at +0.00567, 0.232x its floor. See
step 3.**

```
X1_parity_four_cuts:            PASS. 24,000 of 24,000 bootstrap draws identical,
                                max_abs_diff 0.0 on all 12 cut x leg arrays, verdict
                                rows identical key for key, row mode proven to be the
                                degenerate one-row-per-cluster case.
X2_clustered_coverage:          PASS on the CLUSTER estimator (0.965, accept [0.920,
                                0.980], sd ratio 1.004). The row-iid diagnostic FAILS
                                UNDER-COVERS at 0.800, which is the violation published.
X3_detection_per_class:         PASS. See step 4a.
X4_losses_vs_wins:              PASS on the registered clause (it resolves losses); FAIL
                                on this lab's own tighter 0.80-1.25 band at 0.769. The
                                gap is fully explained by unequal STANDARDIZED effects
                                and disappears once the arms are matched on truth/sd.
                                See step 4b, and do not read the band as passed.
floors, all under BOTH estimators, in step 3.
adjudication_holm + TOST:       see step 5. Holm is inert (nothing clears step 1);
                                TOST decides 4 of 13 family cells.
```

### Part B step 1: X1 parity, 2026-08-09

Producer `python tools/efv_power_lab.py parity_x1 2000`, seed 20260807 + 9, 1,045s,
artifact block `x1_parity` merged into `data/xfv_power_eval.json` by read-modify-write.
Frame shape block from `python tools/efv_power_lab.py h2hshape 2000`.

**X1 PASSES on all three checks, strongest first.**

```
draws identical:        12 of 12 (4 cuts x refit/cond_iid/cond_strat), B = 2000 each,
                        max_abs_diff 0.0 on every array. Not "within tolerance": equal.
verdict rows identical: True, json.dumps(sort_keys=True) equal, all keys including
                        mde95_bonferroni_k4 and the sd_ratio correction branch.
row mode == cluster:    True. mode="row" reproduces mode="cluster" on a frame whose
                        clusters are singletons, B = 300, same seed, exact.
incumbent unmoved:      HEAD's efv_power_lab.verdict and the edited file's verdict are
                        byte-identical at B = 400, so no draw was inserted into an
                        existing stream (section 3.4).
```

Parity is checked against **the incumbent code path run in the same process on the same
pools**, not against the stored artifact, for the reason in the next paragraph.

#### THE BASIS MOVED AGAIN, and this is the headline of step 1

`data/xfv_hitter_matrix.json` and `data/xfv_pitcher_matrix.json` were rebuilt
**2026-08-09 14:08**, after the Part A run (artifact stamped 2026-08-08T23:13:36Z). The
matrices are gitignored build artifacts, so nothing flagged it. Three of the four
registered cuts no longer reproduce their registered point legs:

| cut | registered n / delta | today n / delta | shift |
|---|---|---|---|
| hit.full_pool_km | 1792 / -0.01894 | 1786 / -0.01859 | +0.00035 |
| pit.full_pool_km | 1883 / +0.01398 | 1881 / +0.01491 | +0.00093 |
| hit.debuted_km | 755 / +0.01121 | 755 / +0.01121 | 0 |
| pit.debuted_km | 889 / +0.00612 | 890 / +0.00702 | +0.00090 |

`data/xfv_eval.json` is stamped 2026-08-08 18:02, so the evals are once again STALER
than the matrices, which is the same staleness that moved the section 7.5 verdict in
Part A. On today's basis the four E_cond floors are 0.0201, 0.0216, 0.0205, 0.0300 at
margins 0.927x, 0.689x, 0.548x, 0.234x. **All four are still NULL, so the drift does not
flip Part A's conclusion**, but the registered numbers are no longer reproducible from
this tree and any future re-derivation must restamp them.

#### The head-to-head frame, measured

```
rows 3224 over 1051 players, 3.068 rows per player, max 7
cluster sizes  1:178  2:224  3:264  4:185  5:144  6:46  7:10
sides          500 hitter clusters, 551 pitcher clusters
legs           consensus 0.32070, efv 0.35387, delta +0.03318 (n 3224, target `war`)
```

Clustering-violation size, B = 2000, seed 20260807 + 41, conditional estimator only:

```
cond sd, players resampled          0.01956
cond sd, players within side        0.01955   (side stratification buys nothing)
cond sd, rows i.i.d.  DIAGNOSTIC    0.01288
narrowing if clustering is dropped  1.519x, inside the pre-registered 1.27x-1.75x
```

The design effect is verified independently: bootstrapping the plain mean of the target
gives a cluster-over-row sd ratio of 1.723 against a theoretical sqrt(3.068) = 1.751.

**A structural fact step 2's DGP needs and section 3.3 did not name.** Inside a cluster
the eFV leg is constant in 1051 of 1051 players and the target is constant in 1051 of
1051; only the consensus leg varies, and it varies in just 848. `_h2h_pass` computes one
eFV grade per player in that player's test fold and repeats it against every vintage of
the consensus grade the common set holds, all against one career WAR. So the head-to-head
statistic scores the consensus on up to 7 vintages and eFV on one. A clustered DGP that
emits k i.i.d. rows per player would not be this frame; it must emit one grade, one
target, and k correlated consensus draws.

#### Multiplicity: Holm replaces the k=4 Bonferroni

`holm_family(cells, alpha)` is hand-rolled on the stdlib (`math.erfc` bisection), because
statsmodels is installed but undeclared in `requirements.txt` and therefore not
shippable. It orders the family on the p-value the program's own floor convention
already implies, p = P(Z > |delta|/sd), which reproduces `resolvable` at p <= 0.05 and
the incumbent's `Z_BONF4_ONE` at p <= 0.0125. Reduction check emitted with every block:
z(0.05) = 1.6449 = `Z95_ONE`, z(0.0125) = 2.2414 = `Z_BONF4_ONE`. Floors land under
`mde95_holm_k{k}`; the `mde95_bonferroni_k4` key is NOT reused for a different k.

On today's basis under E_cond the family is inert anyway: the smallest p is 0.0636 at
step 1 against 0.0125, so nothing is rejected and Holm's extra power changes no verdict.

#### An owned number the site misdescribes - RETRACTED IN FULL, 2026-08-09

`assets/diamond.js:125` ships, in the not-resolvable branch of the head-to-head verdict
copy, the sentence:

> More resolved cohorts, not a better model, is what settles it.

**Step 1 of this lane proposed replacing it. THAT PROPOSAL IS WITHDRAWN AND THE EDIT IS
BLOCKED.** It was a cross-statistic transfer, and the replacement would have put a number
on a served surface that is wrong by about 3x in the permissive direction. Recorded here
in full, because a blocked edit that is not written down gets re-proposed.

The proposed sentence was:

> Refit variance is 54.1% of this floor, so more resolved cohorts move it 11% to 27% at
> most and cannot settle it on their own.

Three separate errors, smallest first.

1. **Units.** "Refit variance is 54.1% of this floor" reads a VARIANCE share onto an sd.
   The floor is 1.645 sd. Driving test n to infinity with the training corpus held leaves
   sqrt(0.541) = **0.735** of the floor standing, so the floor share is 73.5%, not 54.1%.
2. **Wrong statistic.** The 54.1% comes from `variance_decomposition` in
   `data/xfv_power_eval.json`, measured on `hit.full_pool_km` / `target_censored` at
   B = 1,200. The number on that JS line is `vv.mde95` =
   `source_backtest.XFV_HEADTOHEAD_MDE95` = 0.0352 (source_backtest.py:628), which is the
   head-to-head CLUSTER bootstrap on target `war`, from
   `data/xfv_headtohead_gap.json`. source_backtest.py:622-627 says so verbatim:
   "Different statistic, different pool, so it needs its own floor and does not inherit
   the one above."
3. **Wrong magnitude, wrong direction.** Measured on the head-to-head statistic itself,
   2026-08-09, B = 2,000 both legs: E_refit sd 0.02095, E_cond (cluster) sd 0.01956, so
   the fit-fixed share is **0.872** and the refit share is **0.128** (0.174 at B = 600,
   where the refit sd reads 0.02152; the share is a small difference of two similar
   numbers, so read it as about 0.13 with a spread of roughly +/- 0.04 across B). The
   floor as test n goes to infinity is 1.645 * sqrt(0.02095^2 - 0.01956^2) = **0.0122**,
   which is **35%** of today's 0.0345. So on THIS statistic roughly **65% of the floor is
   removable by more resolved cohorts**, against 27% on the pooled cut.

**The shipped sentence is roughly RIGHT for the statistic it sits next to, and the
proposed replacement was roughly wrong.** Quantified: the cell needs the sd to fall from
0.02095 to 0.0332/1.645 = 0.02018, a 3.7% reduction, which the fit-fixed decomposition
puts at about 1.17x the current player count, i.e. **one to two more resolved cohorts**.

**NO EDIT IS OWED to `assets/diamond.js`.** If the owner wants the sentence quantified
rather than left qualitative, the following is the only version this lane can support, and
it is OPTIONAL, not a correction:

> More resolved cohorts, not a better model, is what settles it: about 17% more of them.

This lane does not own `assets/diamond.js` and did not edit it.

**The general lesson, which is bigger than this line.** "More cohorts cannot fix power" is
a statement about ONE statistic and it does not transfer. The refit share is 0.541 on
`hit.full_pool_km` and 0.128 on the head-to-head, a 4.2x spread, and the two claims sit
next to each other on the same page. Every future use of that argument has to name its
cut. It also assumes the training corpus is held FIXED: real accrual adds train rows too,
so 0.541 is an upper bound on the irreducible share, not a measurement of it. The
meta-regression on log(n_train) in section 8's B-L2 block is the instrument that speaks to
the other reading.

### Part B step 2: THE CLUSTERED COVERAGE DGP, 2026-08-09

Producer `python tools/efv_power_lab.py x2cover 200`, artifact block `x2_coverage_h2h`,
seed 20260807 + 49, dataset stream 20260807 + 5,000,000, 1,095s.

**This was the step that could have made the whole lane silently wrong.** `make_dgp` emits
one row per unit. A one-row-per-player simulator cannot check a clustered estimator, and
row-level resampling narrows this frame's sd by 1.519x in the anti-conservative direction
(measured in step 1). So the generator was extended, not reused.

`make_dgp_h2h` draws k_i once from the EMPIRICAL rows-per-player distribution and holds it
fixed across every draw, exactly as `make_dgp` holds the 11 fold sizes fixed. Per player it
emits ONE eFV grade, ONE target and k_i CORRELATED consensus reads, which is the structure
step 1 measured: the eFV leg is constant inside 1,051 of 1,051 clusters, the target inside
1,051 of 1,051, and only the consensus varies within a player.

Design match, fitted by bisection with common random numbers on four moments:

| moment | real frame | synthetic |
|---|---|---|
| rho(eFV, war) | 0.3539 | 0.3488 |
| rho(consensus, war) | 0.3207 | 0.3211 |
| rho(eFV, consensus) | 0.6971 | 0.6971 |
| consensus within-player rank ICC | 0.6599 | 0.6585 |

Loadings `pe` 0.3708, `pc` 0.3475, vintage noise `g` 0.5695, shared board component `qa`
0.7881 / `qc` 0.7449. The shared component is not decorative: the two legs correlate at
0.697 while each correlates with the target at about 0.33, because eFV is BUILT from the
consensus (0.30 of the blend, plus the ridge's first feature). Without it the delta's
variance is wrong by a large factor. Target values are resampled CONDITIONAL on k, so the
real -0.129 association between how many vintages a player was graded on and how he turned
out survives into the simulation.

**Result, n_check = 200, M = 300 fresh samples per dataset, B = 300:**

| estimator | boot sd / true conditional sd | coverage | acceptance | gate |
|---|---|---|---|---|
| **cluster (players resampled)** | **1.004** | **0.965** | [0.920, 0.980] | **PASS, REGISTERED** |
| row i.i.d. (DIAGNOSTIC) | 0.680 | 0.800 | [0.920, 0.980] | **FAIL UNDER-COVERS** |

The row leg is published because **publishing the size of the violation is the check that
clustering was preserved**. It under-covers by 15 coverage points and runs 32% narrow.
That is what a one-row-per-player simulator would have waved through.

The conditional estimand is defined per dataset: the eFV leg's loading is perturbed by
sigma_pe and held fixed across that dataset's 300 fresh samples and its 300 bootstrap
draws. sigma_pe is calibrated so the fit-only scatter reproduces the measured fit component
of this class, sqrt(sd_refit^2 - sd_cond^2) = 0.0075, giving sigma_pe 0.00623. Only the eFV
leg is fitted, which is why section 1 pre-registered a SMALLER conditional shrink here than
on the pooled cuts: 0.933x, against 0.45x-0.71x there. **The pre-registered limit held, and
a large shrink would have been evidence of an implementation error.**

**Calibration sensitivity, published rather than assumed away.** The same design was run
with the fit component set from a B = 600 refit sd instead (0.00896, sigma_pe 0.00746;
block `x2_coverage_h2h_sensitivity`). The coverage counts come out IDENTICAL, 193/200
cluster and 160/200 row. That is what conditional coverage is supposed to do (it should
hold at every training corpus, not on average over them), and it means the X2 verdict does
not rest on the calibration.

### Part B step 3: THE FIVE FLOORS, both estimators, 2026-08-09

Producer `python tools/efv_power_lab.py floors 1000 2000`, artifact block `partb_floors`,
353s. B = 1,000 on the pooled-chain classes (sd relative error 2.2%), B = 2,000 on the
head-to-head, whose E_refit leg reproduces a shipped constant and has to stay comparable to
it. **MDE95 is E_refit, MDE95_COND is E_cond, one-sided 1.645 sd in both columns, and no
cell is quoted without both.**

| cell | n | delta | MDE95 | MDE95_COND | E_refit | E_cond |
|---|---|---|---|---|---|---|
| **headtohead_common** | 3,224 rows / 1,051 players | **+0.03318** | 0.0345 | **0.0322** | 0.963x NULL | **1.031x RESOLVABLE WIN** |
| block_rho (debuted, both sides) | 1,645 | +0.00912 | 0.0317 | 0.0203 | 0.288x NULL | 0.450x NULL |
| feature_add `fv`, pooled, ridge leg | 1,786 | +0.02293 | 0.0302 | 0.0250 | 0.759x NULL | 0.918x NULL |
| feature_add `fv`, pooled, blend leg | 1,786 | -0.00408 | 0.0248 | 0.0205 | 0.165x NULL | 0.198x NULL |
| feature_add `fv`, block, ridge leg | 3,667 | +0.01549 | 0.0185 | 0.0166 | 0.839x NULL | 0.935x NULL |
| feature_add `fv`, block, blend leg | 3,667 | +0.00122 | 0.0136 | 0.0124 | 0.090x NULL | 0.099x NULL |
| lambda_shift 0.70 -> 0.65 | 1,786 | -0.00025 | 0.0014 | 0.0009 | 0.180x NULL | 0.281x NULL |
| lambda_shift 0.70 -> 0.60 | 1,786 | -0.00066 | 0.0028 | 0.0017 | 0.235x NULL | 0.384x NULL |
| lambda_shift 0.70 -> 0.51 | 1,786 | -0.00150 | 0.0056 | 0.0033 | 0.269x NULL | 0.454x NULL |
| pooled_rho hit full_pool_km | 1,786 | -0.01859 | 0.0295 | 0.0208 | 0.630x NULL | 0.894x NULL |
| pooled_rho pit full_pool_km | 1,881 | +0.01491 | 0.0265 | 0.0207 | 0.562x NULL | 0.719x NULL |
| pooled_rho hit debuted_km | 755 | +0.01121 | 0.0450 | 0.0204 | 0.249x NULL | 0.549x NULL |
| pooled_rho pit debuted_km | 890 | +0.00702 | 0.0431 | 0.0295 | 0.163x NULL | 0.238x NULL |
| control: feature_add `tool_speed`, pooled, ridge | 1,786 | +0.00490 | 0.0108 | 0.0045 | 0.452x NULL | 1.100x RESOLVABLE |

The four pooled cuts are RE-DERIVED here on today's basis at B = 1,000 so the adjudication
table is on ONE basis. They do NOT replace the part-A registration and are not
byte-comparable with it: new seed, smaller B, and the matrices moved on 2026-08-09 14:08.

#### The head-to-head cell, stated as carefully as it deserves

**It certifies under E_cond by 3%.** That is the pre-registered first branch of section 5,
and it is also the weakest possible version of it. Everything that qualifies it:

- **E_refit says NULL at 0.963x.** Not a contradiction (E_refit does not call it a loss),
  but not support either.
- **It does not survive multiplicity.** Holm over the 13-cell family puts the smallest
  p-value in the family at 0.0449 against a step-1 alpha of 0.00385. Nothing is rejected.
- **It is basis-fragile.** The site currently serves +0.0297 on n 3,210 (2026-08-07 basis,
  `data/xfv_scoreboard_eval.json`), which against this same 0.0322 floor is 0.923x, a NULL.
  The cell resolves only on the 2026-08-09 rebuild, which moved the delta to +0.03318.
- **It is inside the bootstrap's own noise.** At B = 2,000 the sd carries about 1.6%
  relative error, so 1.031x has a range of roughly 1.015x-1.047x from the resampling alone.
- **It is UNDECIDED at the owner's registered shipping margin.** The 90% interval is
  [+0.0010, +0.0654]; its lower edge is below 0.02, so the effect is resolvably above zero
  and NOT resolvably above the margin that would justify shipping a claim.

**The stop clause was not triggered and no third estimator was sought.** The E_cond floor
landed at 0.0322 against a margin of +0.03318, i.e. just BELOW it. Had it landed above, the
cell would have been closed. It is worth stating that the two numbers are 3% apart and that
this lane would have reported the opposite verdict on a two-day-old artifact.

#### AND THEN THE FRAME ITSELF TURNED OUT TO CARRY THE MARGIN

This was not in the brief and it is larger than anything else in this lane.

The head-to-head frame scores **one eFV grade per player against up to 7 consensus
vintages**. Step 1 recorded that as a structural fact. Step 3 measured what it is worth,
and the answer is: **all of it, and then some.**

| frame | rows | clusters | eFV | consensus | delta | E_cond verdict |
|---|---|---|---|---|---|---|
| pooled, all vintages **(SHIPPED)** | 3,224 | 1,051 | 0.35387 | 0.32070 | **+0.03318** | 1.031x resolves |
| pooled, pre-debut reads only | 2,680 | 1,051 | 0.36904 | 0.30355 | +0.06549 | resolves |
| one row per player, EARLIEST vintage | 1,051 | 1,051 | 0.37083 | 0.28025 | +0.09058 | |
| one row per player, LATEST vintage (any) | 1,051 | 1,051 | 0.37083 | 0.42001 | **-0.04918** | 1.732x resolves as a LOSS |
| **one row per player, latest PRE-DEBUT** | **1,003** | 1,003 | 0.36841 | 0.36273 | **+0.00567** | **0.232x NULL** (floor 0.0244) |

The last row is the like-for-like contest: each player once, each side read at the same
information moment, no post-debut grades. **eFV and the consensus are tied there, and the
margin is 0.23x its own floor.** The shipped +0.033 is a property of the frame geometry,
not of the model: pooling duplicates players in proportion to how many vintages they were
graded on, and mixes early consensus reads (which eFV beats easily) with late ones (which
beat eFV).

Two mechanisms, both measured:

1. **Vintage staleness, which flatters eFV.** Consensus rho against career WAR is 0.280 on
   each player's earliest read and 0.420 on the latest. eFV's grade is fixed at the
   debut-year decision. Pooling scores eFV's one late read against a mixture that includes
   the consensus's early ones.
2. **Post-debut hindsight, which flatters the CONSENSUS.** 554 of the 4,284 common-set rows
   (12.9%, 446 players) carry a consensus read taken AFTER the player debuted, and on those
   rows the consensus correlates with career WAR at 0.402 against 0.261 pre-debut.
   `source_backtest._xfv_vs_consensus_detail` already filters these out of the RECEIPTS
   table (audit fix 2026-07-15: "all 8 receipts were post-debut reads; Deivi Garcia's
   verdict was literally inverted"). **The pooled statistic that feeds the served verdict
   does not.**

The two mechanisms push in opposite directions and neither is controlled, which is why the
pooled number lands between them.

**Method note, because this joins two modules.** The frame was NOT rebuilt. Rows were
labelled by joining each cluster to its player on the exact (consensus-value sequence,
career WAR) key that `_load_h2h` emits in ascending-year order: 1,051 of 1,051 clusters
matched, 3 ambiguous, and those 3 are dropped when their debut years disagree. 48 players
have no pre-debut read at all in the common set, which is why the last frame carries 1,003
clusters rather than 1,051.

**This lane does not change the served statistic.** It owns three files and none of them is
`source_backtest.py`. Routed as a REPORTED FINDING, with the exact next measurement: rerun
`accuracy.pooled_efv_common` on one row per player at the latest PRE-DEBUT consensus read,
which is the dedup rule the same module already applies one function away, and re-derive
`XFV_HEADTOHEAD_MDE95` on that frame. On today's data that statistic is +0.00567 against a
floor of 0.0244.

#### What the floors say that nobody had measured

1. **Feature-add has no single floor.** Dropping `fv` gives an E_cond floor of 0.0250;
   dropping `tool_speed` gives 0.0045, **5.5x smaller**, because a feature that barely moves
   the model leaves the two legs nearly identical and the paired difference nearly constant.
   The retired 4-fold row in `EFV_GATE_STANDARD.md` section 1b quotes ~0.017 hit as if it
   were one number. **A driver lane must measure the floor for ITS candidate.**
2. **The lambda-shift floors are 2x-5x smaller than the retired 4-fold row** (0.0014-0.0056
   E_refit against the registered 0.0076-0.011), and the full 0.70 -> 0.51 move costs
   -0.0015 pooled rho. That question is now positively answered rather than open: see the
   TOST block.
3. **The block instrument is the tightest per row of the pooled family** (E_cond 0.0203 on
   1,645 rows against 0.0208 on 1,786), which is what "higher SNR instrument" was supposed
   to mean and had not been shown on this basis.
4. **The block normalization must be recomputed on every resample.** Freezing it at the
   observed sample gives sd 0.01141 against 0.01231, a floor of 0.0188 against 0.0203: 7.3%
   narrower, in the anti-conservative direction, for a transform a fresh sample would
   recompute.
5. **Class parity holds.** The block class's point delta reproduces
   `efv_mde_lab.stats_from`'s block leg exactly (+0.00912 on n 1,645), and the head-to-head
   class's legs reproduce `efv_mde_lab.headtohead`'s point exactly (+0.03318 on n 3,224).

### Part B step 4a: X3, does each class see a known-real effect

Producer `python tools/efv_power_lab.py x3detect 600`, block `x3_detection_classes`, 79s.

The contrast is the shipped spec against the spec MINUS `fv`, rendered in each class's own
frame geometry. **Pool choice is load-bearing and was corrected before the run:** the
known-real `fv` effect lives on the DEBUTED pool (gate standard section 6; part A's
`detect` measured debuted.ridge at +0.05721 detecting under all three estimators while
every full-pool arm missed under all three). Running X3 on the full pool would have scored
MISSES everywhere and passed this gate vacuously.

| class | contrast point | MDE95 | MDE95_COND | E_refit | E_cond |
|---|---|---|---|---|---|
| headtohead (cluster resampled, n 3,224) | +0.02115 | 0.0203 | 0.0192 | DETECTS | DETECTS |
| block instrument (debuted, n 1,645) | +0.02044 | 0.0250 | 0.0156 | MISSES | DETECTS |
| pooled ridge leg (debuted, n 755) | +0.05721 | 0.0464 | 0.0321 | DETECTS | DETECTS |

**X3 PASSES:** no class misses where E_refit detects. The block instrument detects where
E_refit does not, which the criterion allows and which is reported rather than buried.

Two things worth naming.

- The third row is an **exact reproduction of part A's detection cell through the
  generalized path**. The lambda parameter cancels out of the ridge leg (the ridge is
  recovered from the blend with the same lambda it was built with), so this cell IS part
  A's `debuted.ridge` cell: point +0.05721 identical to five decimals, floors 0.0464 at
  B = 600 against part A's 0.0443 at B = 2,000, and E_cond 0.0321 against 0.0322. That is a
  second, independent parity check on the generalization, on a different statistic from X1.
- The head-to-head class detecting the `fv` effect at all is the first evidence that the
  clustered estimator is not inert on real data, which matters because on the shipped
  contrast it sits at 1.03x and could otherwise be accused of never firing.

### Part B step 4b: X4, does the extension resolve losses as readily as wins

Producer `python tools/efv_power_lab.py x4sign 200`, block `x4_sign_symmetry`, 1,416s. Part A could
not answer this on real data, because E_cond resolved nothing in either direction. It is
answerable by construction on the clustered simulator: run the same generator with the
challenger leg better than the baseline and then worse, with **both true deltas solved by
bisection to +/- the real margin** rather than mirrored in the parameter, and compare fire
rates at each estimator's own floor.

| arm | true delta | mean floor | fire rate (cluster) | fire rate (row, diagnostic) |
|---|---|---|---|---|
| win | +0.03387 | 0.0312 | **0.585** | 0.770 |
| loss | -0.03213 | 0.0338 | **0.450** | 0.710 |

**The registered clause PASSES: the instrument resolves losses, it does not resolve only
wins** (section 4.4 refuses the extension only in the latter case). **This lab's own
tighter band FAILS: the ratio is 0.769 against a pre-declared 0.80-1.25.** The band was
self-added and it is not relaxed after the fact.

The shortfall is mechanically explained and the explanation is a finding about the design,
not a rescue of the result. **Matching two arms on |true delta| does not match them on
power**, because the delta's sd is itself a function of the eFV leg's loading: the loss arm
ended up testing a 5% smaller effect against an 8% larger floor. Standardized:

| arm | z_true = truth / sd | normal-theory fire rate | observed |
|---|---|---|---|
| win | 1.786 | 0.556 | 0.585 |
| loss | 1.564 | 0.468 | 0.450 |

Both arms land within 0.03 of the normal-theory rate at their own standardized effect,
inside the binomial se of 0.035 at n_sim = 200. **Once the arms are compared at equal
standardized effect the asymmetry disappears.** Anyone re-running X4 should match on
|truth| / sd, not on |truth|.

The row-i.i.d. diagnostic fires at 0.770 / 0.710 against the cluster estimator's 0.585 /
0.450, which is the clustering violation showing up a third way: it does not just narrow
the interval, it fires 20-26 points more often on the same data.

### Part B step 5: B-L2, the three-way adjudication

Producer `python tools/efv_power_lab.py adjudicate 500`, block `adjudication_bl2`, 8s.
Equivalence margin **0.02 Spearman, registered by the owner 2026-08-08**. The interval is
delta +/- 1.645 sd, the same one-sided alpha 0.05 the floors use, which is the TOST
interval at that alpha.

**Tally over the 13-cell family: 4 RULED_OUT, 9 UNDECIDED, 0 SHIP.**

| RULED OUT (interval entirely inside +/- 0.02) | 90% interval |
|---|---|
| lambda_shift 0.70 -> 0.65 | [-0.0011, +0.0006] |
| lambda_shift 0.70 -> 0.60 | [-0.0024, +0.0011] |
| lambda_shift 0.70 -> 0.51 | [-0.0048, +0.0018] |
| feature_add `fv`, block instrument, blend leg | [-0.0112, +0.0136] |

**The lambda pin is now settled, and that is the single most useful thing B-L2 bought.**
The distance between the shipped 0.70 and the selector's own argmax 0.51 is worth
-0.0015 pooled rho with a 90% interval inside +/- 0.005. It is not a null any more, it is a
measured non-difference, an order of magnitude below the margin that would justify moving
it. That question can be closed rather than re-opened every cycle.

**The brief's expectation that TOST would convert about half the nulls is NOT met: it
converts 4 of 13, 31%.** The reason is arithmetic and worth writing down. TOST can decide a
cell only when |delta| + floor < 0.02, and nine of these thirteen cells have an E_cond
floor of 0.0203 to 0.0322 on its own. **At the registered margin the instrument can only
decide cells whose floor is already well under the margin.** To decide the pooled cuts and
the head-to-head, the margin would have to sit near 0.045.

#### Decidability triage, converted to dates

Accrual is the median per-fold test n, i.e. one new decision-year cohort: 169 rows/yr on
hit full_pool, 194 pit, 62 / 76 on the debuted pools, 372 rows/yr on the head-to-head.

| cell | E_cond decidable by | E_refit |
|---|---|---|
| headtohead_common | **decided at current n** | asymptote 0.0123, still decidable |
| feature_add `fv` pooled ridge | 2028 | asymptote 0.0170, still decidable |
| feature_add `fv` block ridge | 2029 | asymptote 0.0081, still decidable |
| pooled hit full_pool_km | 2029 | **PERMANENTLY UNDECIDABLE** (asymptote 0.0209) |
| pooled pit full_pool_km | 2035 | **PERMANENTLY UNDECIDABLE** (0.0166) |
| pooled hit debuted_km | 2054 | **PERMANENTLY UNDECIDABLE** (0.0401) |
| block_rho | 2064 | **PERMANENTLY UNDECIDABLE** (0.0244) |
| lambda_shift 0.19 / 0.10 / 0.05 | 2067 / 2086 / 2149 | **PERMANENTLY UNDECIDABLE** |
| pooled pit debuted_km | 2221 | **PERMANENTLY UNDECIDABLE** (0.0315) |
| feature_add `fv` pooled blend | 2283 | **PERMANENTLY UNDECIDABLE** |
| feature_add `fv` block blend | 4247 | **PERMANENTLY UNDECIDABLE** |

**Ten of the thirteen cells can never be resolved under E_refit at any n**, because the
refit component of the floor exceeds the margin on its own and does not shrink with test n.
Six more are past 2050 even under E_cond. The honest disposition for those is to RETIRE
them, not to re-test them every cycle and re-report the same null.

**The caveat that keeps this honest.** "Permanently undecidable under E_refit" holds the
TRAINING corpus fixed. Real cohorts add train rows too, so the fit component itself shrinks
with accrual and these are upper bounds on the irreducible floor, not measurements of it.
The meta-regression below is the instrument that speaks to the other reading.

#### Per-fold series, REML with Hartung-Knapp-Sidik-Jonkman

The eval does not emit a per-fold delta series. It does now: 11 folds per pooled cut, 10
for the head-to-head (2015 carries too few clusters and is dropped), each with its own
within-fold bootstrap variance and its own n_train.

| cut | folds | tau2 (REML) | pooled | se_RE | se_HKSJ | HKSJ 95% |
|---|---|---|---|---|---|---|
| hit full_pool_km | 11 | 0.00124 | -0.01271 | 0.01490 | 0.01523 | [-0.0467, +0.0212] |
| pit full_pool_km | 11 | 0 | -0.00217 | 0.01043 | 0.00814 | [-0.0203, +0.0160] |
| hit debuted_km | 11 | 0.00048 | +0.01229 | 0.01377 | 0.01303 | [-0.0167, +0.0413] |
| pit debuted_km | 11 | 0.00028 | +0.00937 | 0.01508 | 0.01477 | [-0.0236, +0.0423] |
| headtohead_common | 9 | 0 | +0.03805 | 0.01869 | 0.01618 | [+0.0008, +0.0754] |

DerSimonian-Laird is computed alongside and is NOT shipped: it reads 0.00121 against REML's
0.00124 on the hitter full pool and 0.00032 against 0.00048 on hitter debuted, i.e. biased
low exactly where tau2 matters. I-squared is suppressed on purpose: at this per-fold n it
is near 0.99 mechanically and would be read as a finding.

**A brief claim that did not survive contact.** HKSJ was adopted for VALIDITY on the
expectation that it widens 15% to 40%. **It does not.** The t-for-z swap alone is +13.7% at
k = 11 (t_10 = 2.2281 against z = 1.960); the variance rescale then multiplies by sqrt(q),
and q ran 0.61 to 1.05 across these five cells. Net effect on the interval half-width:
**+16.2% on hit full_pool, +7.6%, +11.3%, +1.9%, and -11.3% on pit full_pool, where HKSJ
NARROWS the interval.** It is still the right choice, for the reason it was adopted (it is
valid at k = 11 where the normal approximation is not), but "it widens 15 to 40 percent" is
not a description of what it did here.

#### Meta-regression on log(n_train): the highest-value variant, and it says something

Every fold trains on a strict prefix of the chain. The DEPLOYED model trains on ALL
cohorts and is represented by no fold. Mandel-Paule tau2, Knapp-Hartung variance inflation,
t_(k-2) intervals.

| cut | slope per log(n_train) | slope 95% | n_train folds -> deployed | predicted delta at deployed n |
|---|---|---|---|---|
| **headtohead_common** | **+0.0813** | [-0.0026, +0.1652] | 543-3,359 -> 3,853 | **+0.0975, CI [+0.0288, +0.1662]** |
| pit debuted_km | +0.0278 | [-0.0123, +0.0679] | 91-862 -> 981 | +0.0376 [-0.0131, +0.0883] |
| pit full_pool_km | +0.0062 | [-0.0137, +0.0261] | 94-1,719 -> 1,976 | +0.0034 [-0.0226, +0.0293] |
| hit debuted_km | -0.0048 | [-0.0532, +0.0436] | 90-754 -> 845 | +0.0079 [-0.0452, +0.0611] |
| hit full_pool_km | -0.0119 | [-0.0544, +0.0307] | 91-1,640 -> 1,877 | -0.0247 [-0.0839, +0.0345] |

**The head-to-head margin GROWS with training size**, and the predicted delta for the
deployed training corpus, +0.0975, has an interval that excludes zero. Read it with all
three caveats and do not ship it as a number:

1. the SLOPE itself does not resolve (its interval straddles zero), and a prediction
   interval that excludes zero while the slope does not is a normal artifact of evaluating
   a fitted line near the data;
2. it is an extrapolation, though a mild one: 3,853 against a top fold of 3,359;
3. the slope is driven by the two early folds (2016 -0.1212, 2017 -0.2025 on 543-1,000
   train rows), and the sign flips per cut, so this is not a general law about eFV.

What it does establish is that **the pooled fold estimate is a biased summary of the
deployed model whenever the slope is non-zero**, and on the one statistic the site's claim
rests on, the bias runs against eFV, not for it.

#### Exhaustive sign enumeration: exact, seedless, and it agrees with the nulls

With 11 forward-chained folds there are 2^11 = 2,048 sign vectors, so the randomization
distribution is ENUMERATED, not sampled. No seed, no Monte-Carlo error.

| cut | vectors | p (inverse-variance weighted) | p (unweighted) |
|---|---|---|---|
| headtohead_common | 512 (k = 9) | 0.0859 | 0.7422 |
| hit full_pool_km | 2,048 | 0.2412 | 0.9180 |
| hit debuted_km | 2,048 | 0.4873 | 0.2158 |
| pit debuted_km | 2,048 | 0.5332 | 0.6016 |
| pit full_pool_km | 2,048 | 0.7930 | 0.7041 |

Nothing clears 0.05 under either weighting. **The gap between the two weightings is itself
a finding**: on the head-to-head the inverse-variance weighted fold mean is +0.0381 while
the unweighted mean is -0.0114, because the recent large folds are positive and the two
early tiny folds are strongly negative. Both weightings are published because the
inverse-variance weights are themselves estimated, and a claim that only survives one of
them is not a claim.

### Disposition against section 5's pre-committed branches

Section 5 pre-committed three acceptable outcomes. The result lands on the first one by the
letter and does not earn what the first one licenses.

1. **"head-to-head certifies under E_cond, contradicted by neither estimator: owner
   decision 7 applies and the site claim gains conditional wording."** The letter of this
   branch is met: 1.031x under E_cond, and E_refit calls it NULL rather than a loss.
   **This lane recommends against acting on it**, for four reasons that are all in step 3:
   it fails Holm, it is UNDECIDED at the registered 0.02 margin, it flips to NULL on the
   basis the site currently serves, and the like-for-like frame puts the margin at +0.00567
   and 0.232x. Conditional wording bought on a 3% margin that a frame choice controls would
   be a claim about the frame.
2. head-to-head stays null: not the outcome, though it is the outcome under E_refit, under
   Holm, under TOST, and on the deduplicated frame.
3. hitter `full_pool_km` resolves as a LOSS again: **it does not.** On today's basis it is
   -0.01859 at 0.894x its E_cond floor, still NULL, and section 7.5's retraction stands.

**What is owed to the owner, in order of value:**

- **Settle the head-to-head frame.** One row per player at the latest PRE-DEBUT consensus
  read is the contest the copy describes and the dedup rule `source_backtest` already
  applies one function away. It changes the answer from "eFV leads" to "tied".
- **Retire, do not re-test,** the ten cells that cannot resolve under E_refit at any n and
  the six whose E_cond date is past 2050.
- **Stop quoting a generic feature-add floor.** Measure the candidate.
- **Close the lambda question.** 0.70 against 0.51 is RULED OUT at the registered margin.
