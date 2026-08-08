# PROVISIONAL GATE (Lane F, 2026-08-07b): the provisional model under the gate standard

**STATUS OF THIS FILE.** Parts 0 through 6 are the PRE-REGISTRATION. They were written in
full, including every PASS clause, every disclosed self-added threshold and every stop
clause, BEFORE `tools/efv_ungraded_gate_lab.py` existed and therefore before any effect
estimate in part 7 could be known. Part 7 is a placeholder filled in after the run. Nothing
in parts 0 to 6 is edited afterwards. This is the Lane J1 discipline.

**What WAS looked at before this file was written, and it is disclosed because a verifier
would otherwise have to guess.** Only STRUCTURAL quantities: the labeled-matrix pool sizes
(1,115 hitter / 1,005 pitcher production-bearing rows), the per-year decision counts and
therefore which forward-chained folds clear the 60-train / 15-test floors (hit 2018-2024,
seven folds; pit 2019-2024, six folds), the served provisional artifact's grade and level
histogram, the size of the routed-cohort analog (570 hit / 411 pit), the shipped value of
`_PROV_RANK_PENALTY` and of `UNCAPPED_GRADE`, and per-draw runtime. **No Spearman, no
delta, no AUC, no p-value was computed before this file was complete.**

---

## 0. What is actually in dispute

`efv_ungraded` grades 5,993 players in the live artifact. Since floor routing shipped
(`efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT = True`, 2026-08-07) roughly 2,434 of
them SERVE that provisional grade as their board grade, in place of a flagship grade that
was the constant FV 20.0.

Its entire eval, `data/xfv_ungraded_eval.json`, is four Spearman numbers dated 2026-07-14:

| side | cohort | n | rho |
|---|---|---|---|
| hit | low_minors_age_le21 | 105 | 0.2369 |
| hit | all_levels | 621 | 0.2985 |
| pit | low_minors_age_le21 | 62 | 0.0867 |
| pit | all_levels | 627 | 0.1854 |

There is no paired bootstrap, no zero-information control, no permutation null, no MDE, and
no cross-split average. `docs/EFV_GATE_STANDARD.md` section 2 requires all four for any
result that is shipped, and a grade printed on the board is shipped. The four numbers also
predate the pitcher ceiling de-rate and the routing flip, and they score a quantity the
board does not serve (below, part 2).

**This lane does not change any shipped constant, does not flip any switch, and does not
own `efv_ungraded.py`, `efv_score.py` or `prospx/index.html`.** It measures.

## 0.1 The trap, stated so it can be checked against the result

The routed comparison has an obvious way to be vacuous. The grade routing replaced is the
constant 20.0 on every routed row, and a constant carries zero rank information by
construction, so ANY positive Spearman "wins". A lane that reports "provisional rho 0.21
beats constant rho 0.00" has run `f(X) > 0` and called it a gate. Part 4 exists to stop
that, and part 4.2 states the two independent routes by which the comparison can FAIL.

Second trap: a tighter floor never creates a win. Two floors are reported for every cut
(part 3) and neither is treated as authoritative alone.

## 1. Population, and the mapping caveat that bounds everything below

The only labeled outcomes available are the eFV matrix rows (`data/xfv_*_matrix.json`):
players who debuted or who resolved as busts. The provisional model's own fit and eval pool
is the production-bearing subset minus recent busts, which is what `efv_ungraded.fit_nofv`
and `efv_ungraded.evaluate` already use, so this lane inherits it unchanged.

**THE MAPPING CAVEAT, stated once and carried into every claim.** That pool is not the
served population. Measured level mix:

| level | labeled pool (hit+pit) | served provisional artifact |
|---|---|---|
| DSL | 54 (2.5%) | 2,080 (34.7%) |
| CPX | 164 (7.7%) | 772 (12.9%) |
| A | 323 (15.2%) | 1,038 (17.3%) |
| A+ | 377 (17.8%) | 840 (14.0%) |
| AA | 722 (34.1%) | 651 (10.9%) |
| AAA | 480 (22.6%) | 612 (10.2%) |

The labeled pool is AA/AAA-heavy because reaching a labeled outcome requires climbing; the
served population is DSL/CPX-heavy org filler. **Every number this lane produces is measured
on the pool that has outcomes and applied to a population that skews two rungs lower.** That
is the same pool-mapping limitation `data/provisional_calibration_eval.json` already
records, it is not repairable inside this lane, and no verdict here may be read as if it
were measured on the served population.

**Second caveat, the corpus moved.** Baseball America ingested 1,535 rows this session and
the served eFV matrices reproduce `consensus_fv_raw` on only 74.8% of rows against the
current corpus. This lane rebuilds every model it scores from the matrix on disk at run
time, so it is internally consistent; but its routed-analog construction (part 4.1) depends
on the FLAGSHIP consensus anchor, and a 25% anchor drift bounds how precisely the historical
analog reproduces today's routed membership. Reported, not ignored.

## 2. The statistic. It is the SERVED GRADE, not the model's WAR.

The incumbent eval scores `efv_ungraded._war()`. The board serves `efv_ungraded._grade()`.
These are NOT rank-identical: `_grade` clamps at `FLOOR` 20.0 and (with `UNCAPPED_GRADE`
False, which is the shipped state) compresses above `KNEE` with an order-preserving soft
ceiling. The floor clamp is a TIE-MAKER: 953 of 5,993 served grades sit exactly on 20.0 and
another 494 sit exactly on the 30.0 sub-floor cap, so 24.1% of the served population is
inside a clamp tie block that the WAR-based eval does not see.

**PRIMARY statistic, pre-registered:** pair-weighted pooled Spearman of the SERVED GRADE
against `target_censored`, pooled over the forward-chained test folds, pair weight
`observed_seasons/6` (the row `weight` field), matching the 11-fold pair-weighted basis of
`EFV_GATE_STANDARD.md` section 1a so the floors are comparable.

**Also reported, always:** the unweighted pooled Spearman, and the same two on `_war()`, so
the incumbent's four numbers can be located inside the new artifact.

**DISCLOSED SELF-ADDED THRESHOLD 1.** Changing the scored quantity from `_war` to `_grade`
and the pooling from unweighted to pair-weighted are BOTH changes this lane makes and the
brief does not specify. If either determines a verdict, part 7 says so in its headline.

**DISCLOSED LIMITATION, not a threshold.** The served grade also carries the exposure
sub-floor clamp (`min(grade, 30.0)` when the primary-level line is under `_MIN_EXPO_PA` 80
or `_MIN_EXPO_BF` 90). The labeled matrix carries no PA or BF column, so that clamp CANNOT
be reproduced historically. The served-grade analog therefore applies the FLOOR and the soft
ceiling and NOT the exposure clamp. Direction of the error is stated in part 7 by measuring
how many rows the clamp would plausibly touch; it is not assumed benign.

## 2.1 The two-metric gate (section 3 of the standard)

- **block-rho**: (side x fold-year) block-normalized pooled Spearman, both sides pooled.
- **AUC**: debut / no-debut discrimination. `EFV_GATE_STANDARD.md` section 3 carves this
  out for any candidate that can sense whether a row has a MiLB production block. This pool
  is production-bearing BY CONSTRUCTION (`r.get("milb")` is the pool filter), so the
  missingness proxy is constant within it and this is exactly the carve-out's named
  admissible substitute, "AUC computed on the TRACK-RECORD population only". It is reported
  on that basis and on no other.

## 3. Two floors, both reported, neither authoritative alone

Per `EFV_GATE_STANDARD.md` section 7 and `docs/efv-2026-08-07b/POWER_GATE.md`:

- **E_refit** (section 1, shipped): resample the whole side pool with replacement, refit the
  provisional ridge and its linear output calibration on every draw, rerun the forward
  chain, recompute the statistic. Estimand: variance over redraws of the training corpus AND
  the scored sample.
- **E_cond** (section 7, registered wave 2, `E_cond_iid`): fit the chain once, hold every
  per-fold fit FIXED, resample the pooled scored rows i.i.d. Estimand: variance over redraws
  of the scored sample given this training corpus.

MDE95 is ONE-SIDED (1.645 sd), the convention of section 1 and section 7. The two-sided
figure (1.96 sd) is printed beside every one-sided one.

**Where the two estimators DISAGREE about a verdict, part 7 says so in the row, in the
summary table and in the headline.** Neither is quoted alone.

**DISCLOSED SELF-ADDED THRESHOLD 2.** B = 2,000 draws, seed 20260808. B matches
POWER_GATE.md; the seed is new and is fixed now. No RNG stream anywhere in the lab is
derived from a set iteration order or from `hash()` of a string.

## 4. THE ROUTED-COHORT QUESTION

### 4.1 Constructing the historical routed cohort

`efv_score.route_floor_grade` routes a live row when BOTH hold:

1. its consensus anchor is constant-only (`fv_synthetic_only`: nobody published an opinion,
   so `consensus.CONSTANT_ANCHOR_SOURCES` folded the FV 35.0 placeholder back in), AND
2. its flagship board grade equals the outcome curve's first knot, FV 20.0, which
   `vf.outcome_implied_fv` returns for every non-positive predicted WAR.

The labeled matrix carries no `anchor_constant_only` column (it is stamped only on live
rows), so the analog is built FUNCTIONALLY, reproducing the shipped predicate rather than
approximating the population:

> For each forward-chained fold, fit the FLAGSHIP stack (consensus OLS on `fv` plus the
> weighted production ridge) on the real training rows, exactly as `efv_model._run_eval`
> does. Then score each TEST row with its anchor REPLACED by what a constant-anchor row
> actually presents: `fv := 35.0`, and the scout tool columns in the flagship spec
> (`tool_hit`, `tool_speed` on hitters, `tool_fb` on pitchers) set to their missing-value
> imputes, because a player nobody has graded has no published tools. Compute the shipped
> blend `(1-lam)*max(0, OLS(35.0)) + lam*ridge`. A row whose blend is <= 0 maps to FV 20.0
> and IS the historical routed row.

Condition 1 is imposed by construction (every row is scored with the constant anchor).
Condition 2 is the shipped inequality. Structural check already run: at fv 35.0 the fold
OLS floors at 0.0 WAR, so the condition reduces to `ridge <= 0`, and the analog is 570 of
1,032 scored hitter rows and 411 of 895 scored pitcher rows.

**DISCLOSED SELF-ADDED THRESHOLD 3.** The substitution constants (`fv := 35.0`, tools set to
`efv_model._TOOL_IMPUTE`) are this lane's choice. `35.0` is read from
`consensus.CONSTANT_ANCHOR_SOURCES` behaviour and is verified against the live matrix in
part 7 rather than asserted. A sensitivity at `fv := 30.0` and `fv := 40.0` is reported,
because the whole cohort definition hangs on it.

**The membership is itself estimated,** so under E_refit the selection redraws with the fit
on every bootstrap draw. It is not held fixed at its point value. Under E_cond it is held
fixed, which is what "conditional on this training corpus" means.

### 4.2 HOW THIS COMPARISON CAN FAIL. Two independent routes, both pre-registered.

The incumbent on a routed row is the constant 20.0. Its Spearman against any outcome is
undefined (zero variance in the predictor); this lane adopts the convention
`rho_constant := 0.0` and VERIFIES the constancy in code rather than asserting it
(clause B0). So the comparison is `rho_prov - 0`, and if the bar were "is it positive" the
lane would be vacuous. The bar is not that. It is:

**ROUTE 1, the sampling floor.** `rho_prov` on the routed analog must clear its OWN MDE95,
derived here from the paired bootstrap of part 3, under both estimators. A positive but
sub-floor rho is a NULL and is reported as one. The published pitcher low-minors number is
0.0867, so this route can plainly fail.

**ROUTE 2, the null band, which is the sharper one and the honest model of the incumbent.**
A constant does not sit at rho exactly 0 in the world; it sits in a TIE BLOCK that the
board's sort resolves by a tiebreak chain, so the ordering the 2,434 routed players actually
received before routing is one arbitrary draw from the permutation null. The correct
incumbent is therefore `Null(0, sd_null)`, not the point 0. `rho_prov` must exceed the
permutation null's 95th percentile on the SAME rows. This is a strictly harder bar than
route 1 at these n and it is the direct answer to "design the comparison so it can fail".

Both routes are reported for every cut. A cut that clears one and not the other is reported
as split, never as a pass.

### 4.3 Clauses

**Part A, the model's own gate on its own eval pool.** Per side.

- **A1 PASS** if pooled weighted rho of the served grade >= MDE95 under E_refit.
- **A2 PASS** if the same holds under E_cond.
- **A3 PASS** (zero-information control) if a row-permuted twin of the served grade, scored
  on the identical rows with the identical marginal, does NOT clear the same floor. A twin
  that clears indicts the harness, not the model.
- **A4 PASS** (permutation null) if the share of 2,000 label-permuted replicates with
  `|rho_null| >= |rho_obs|` is <= 0.05.
- **A5 PASS** (>= 4 independent time splits) if the fold mean rho > 0 AND strictly more than
  half the folds are positive. Seven folds hit, six pit; both exceed the four the standard
  requires. **Non-independence is disclosed:** forward-chained folds share training rows, so
  they are sequentially nested, not independent, and this clause is a stability check rather
  than a replication.
- **A6 PASS** (two-metric) if the block-rho E_refit CI95 excludes 0 AND the track-record AUC
  E_refit CI95 excludes 0.5.

**Part B, the routed cohort.** Per side. PRIMARY cut named now, before measurement:
**hitter routed analog.** Chosen because it is the larger analog (570 against 411) and
because the hitter side carries the stronger published provisional signal (0.2985 against
0.1854), so a failure there closes the question and a pass there is the weakest possible
evidence for the pitcher side. Pitcher routed, hitter full pool and pitcher full pool are
SECONDARY.

- **B0** (verification, not a gate): the incumbent grade is exactly 20.0 on every routed
  row, computed and counted, and its rho is recorded as the degenerate case it is.
- **B1 PASS** if `rho_prov` on the routed analog >= MDE95 under E_refit (route 1).
- **B2 PASS** if the same holds under E_cond (route 1).
- **B3 PASS** if `rho_prov` exceeds the permutation null p95 on the same rows (route 2).
- **B4 PASS** if the row-permuted zero-information twin does NOT clear the floor.
- **B5 DIAGNOSTIC, the control that would embarrass this lane.** The dumbest explanation for
  a positive rho on a routed cohort of org filler is that it is a LEVEL LOOKUP: an AAA arm
  outranks a DSL arm and the model is an expensive way to read `level_rank`. So the same
  rows are also ranked by `level_rank` alone and by `-age_rel_level` alone, single columns
  requiring no fit, and the PAIRED bootstrap delta `rho_prov - rho_level` is reported with
  its own floor. If that delta is a null, the lane states that the provisional model's
  advantage over the constant is reproducible by a one-column lookup. This is reported
  whatever it says; it does not veto B1-B4, and it is not permitted to be omitted.
- **B6 MULTIPLICITY.** Four pre-registered cuts (2 sides x {full pool, routed analog}).
  Bonferroni k = 4 floors (one-sided alpha 0.0125, z = 2.2414) printed beside every
  unadjusted floor. No secondary cut is described as resolvable on its unadjusted floor
  alone. The primary is not required to clear the adjusted floor, being pre-registered, but
  the adjusted number is published so nobody has to ask. Every "k of n significant cells"
  statement in part 7 carries n.

**Part C, `_PROV_RANK_PENALTY`.**

- **C0** (fact check, reported whatever it says): read the shipped constant and its line out
  of `prospx/index.html`, and read `UNCAPPED_GRADE` out of `efv_ungraded.py`. The brief
  states the constant is "hardcoded 4 at prospx/index.html:31243" and that "the de-cap moved
  the grade distribution the penalty was fitted against". Both premises are checked against
  the tree before anything is re-derived, and the check is reported first.
- **C1** re-derive `data/provisional_calibration_eval.json` ESTIMATOR B on the CURRENT grade
  distribution: the rank-optimal display penalty `delta` maximizing cross-pool pair
  concordance of adjusted-grade order against realized-WAR order. The two pools are the ones
  routing actually creates: pool P = routed rows displaying `provisional_grade - delta`,
  pool G = non-routed rows displaying the flagship grade. Grid `delta` in [-4, 16] step
  0.25. Concordant pairs only across pools, ties excluded. Bootstrap CI by row resampling
  within pool, B = 1,000, seed 20260808. Report argmax, the plateau within 1e-4 of the
  maximum, CI95, and the concordance at the shipped value.
- **C1 is an ESTIMATION, not a gate.** It has no PASS clause and none is invented. Whatever
  it returns becomes an `edits_requested` entry with exact old and new text, addressed to
  the owner of `prospx/index.html`, and nothing else.

**DISCLOSED SELF-ADDED THRESHOLD 4.** The A5 rule ("fold mean > 0 and strictly more than
half the folds positive"), the A6 rule ("both CI95 exclude their null"), the A4/B3 alpha of
0.05, and the C1 grid range and step are all this lane's choices. The brief specifies none
of them. If any one of them determines a verdict, part 7 states it in the headline.

## 5. STOP CLAUSE, pre-registered

**If the provisional model does not clear its floor against the constant it replaced on the
routed cohort, that is a finding about the ROUTING and not a licence to revert it.** Record
it, report it, hand the decision to the owner. Do NOT:

- revert or recommend reverting `SERVE_PROVISIONAL_FOR_CONSTANT_COHORT` on this evidence
  alone, because routing also shipped on a COHERENCE argument (serving a fabricated constant
  as a grade is incoherent regardless of its rank skill) that this lane does not measure and
  cannot overturn;
- swap the estimator, the statistic, the pool or the fold set after seeing an unfavourable
  answer. One wave-2 lane did that and its recommendation was blocked unanimously. If a
  pre-registered clause fails, it is reported failed.
- widen B, re-seed, or add a bias correction to move a margin across its floor.

Symmetrically: if part A or part B PASSES, that does not license raising `KNEE`/`CEIL`,
un-capping the grade, widening routing to the 184 above-floor rows, or any other change.
This lane's product is a measurement and a gate verdict.

## 6. What gets written

- `tools/efv_ungraded_gate_lab.py`, the only producer.
- `data/xfv_ungraded_eval.json`, REGENERATED. It keeps the incumbent's four numbers under
  `legacy_2026_07_14` so the old artifact's claims stay locatable, and adds the full battery.
- This file, part 7 only.

Nothing else is written. `efv_ungraded.py`, `efv_score.py` and `prospx/index.html` are
READ-ONLY to this lane and every proposed change to them is an `edits_requested` entry.

---

## 7. RESULT (appended after the run)

Producer `python tools/efv_ungraded_gate_lab.py all 2000`, seed 20260808, ledger
`data/xfv_ungraded_eval.json`. Every number below is a key in that file. Runtime 180.2s.

### 7.0 Harness parity, before any claim

`harness_parity`. The lab's vectorized chain against `efv_ungraded`'s own python fit, same
fold, same rows, both sides: linear calibration identical to the fourth decimal
(hit -0.0628 / 1.1112, pit -0.1653 / 1.1450), `max_abs_war_diff` **0.0**,
`max_abs_grade_diff` **0.0**, and the fold rho agrees to six decimals (hit 0.054233, pit
-0.018927). The harness is the shipped model, bit for bit, not a reimplementation of it.

### 7.1 Part C0 first, because it changes what part C means

**Both premises the brief gives for the `_PROV_RANK_PENALTY` re-derivation are FALSE
against the tree.** They are reported before the re-derivation, not after. `penalty.shipped`:

| premise (brief) | tree | key |
|---|---|---|
| `_PROV_RANK_PENALTY` is 4 | **0** | `penalty.shipped.value` |
| at `prospx/index.html:31243` | **line 32495** | `penalty.shipped.file_line` |
| the de-cap moved the grade distribution the penalty was fitted against | `UNCAPPED_GRADE` is **False** | `penalty.shipped.uncapped_grade` |

The constant was RETIRED to 0 on 2026-07-25 by the F2 repair, whose reason sits in the
comment above it: "the sort value must equal the displayed value or the board grade column
is not monotonic". The de-cap was reverted the same day ("PROVISIONAL CAP RESTORED
2026-07-25"), so the distribution the 2026-07-23 estimator B was fitted against is the
CAPPED one, which is the one shipping now. The stated reason to re-derive does not exist.

The re-derivation was run anyway, because routing changed something the brief did not name
and that DOES invalidate the old measurement: estimator B was fitted on `efv_score`
provisional rows (consensus-only, prior-anchored), and the board now serves `efv_ungraded`
production-only grades to the routed cohort. Different pool, different scale. Result in 7.7.

### 7.2 The pools, the mapping caveat as numbers, and the legacy reproduction

`population`. Labeled pool 2,120 rows (1,115 hit + 1,005 pit) against 5,993 served:

| level | labeled pool | served provisional |
|---|---|---|
| DSL | 54 (2.55%) | 2,080 (34.71%) |
| CPX | 164 (7.74%) | 772 (12.88%) |
| A | 323 (15.24%) | 1,038 (17.32%) |
| A+ | 377 (17.78%) | 840 (14.02%) |
| AA | 722 (34.06%) | 651 (10.86%) |
| AAA | 480 (22.64%) | 612 (10.21%) |

**Every verdict below is measured two rungs above the population it is applied to.** Part 1
said this would be the binding limitation and it is.

`legacy_2026_07_14.reproduced_on_current_code_and_corpus`. The incumbent protocol re-run on
current code and the current corpus:

| cut | published 2026-07-14 | re-run 2026-08-08 | n now |
|---|---|---|---|
| hit low_minors_age_le21 | 0.2369 | **0.1122** | 163 |
| hit all_levels | 0.2985 | **0.2807** | 740 |
| pit low_minors_age_le21 | 0.0867 | **0.1012** | 58 |
| pit all_levels | 0.1854 | **0.1496** | 678 |

The all-levels cuts reproduce. **The hitter low-minors cut does not: 0.2369 has become
0.1122, less than half.** That is the number `efv_ungraded.py`'s own docstring advertises as
"~0.22" and the model registry advertises as "~0.22". The corpus moved (part 1), so this is
a fresh measurement rather than a failed replication, but the published claim no longer
holds on current data.

**A separate documentation defect, found while reproducing.** The module docstring and the
registry row both claim the pitcher low-minors Spearman "jumps 0.09 -> 0.24". The artifact
they cite as the source has always said **0.0867**, and the re-run says 0.1012. The 0.24 has
never been in the file it is sourced to. Edit requested.

### 7.3 Part A: the section-2 battery on the model's own pool

`battery.by_side`. Primary statistic: pair-weighted pooled Spearman of the SERVED GRADE.

| | hit | pit |
|---|---|---|
| n scored | 1,032 | 895 |
| folds | 7 (2018-2024) | 6 (2019-2024) |
| **rho, served grade, weighted** | **0.26729** | **0.11476** |
| rho, served grade, unweighted | 0.24715 | 0.11409 |
| rho, `_war`, weighted | 0.26772 | 0.11461 |
| rho, `_war`, unweighted | 0.24757 | 0.11384 |
| share on the 20.0 floor | 8.91% | 2.01% |
| E_refit sd / MDE95 | 0.03514 / **0.0578** | 0.04273 / **0.0703** |
| E_cond sd / MDE95 | 0.03504 / **0.0576** | 0.03503 / **0.0576** |
| MDE95 two-sided (refit / cond) | 0.0689 / 0.0687 | 0.0838 / 0.0687 |
| Bonferroni k=4 floor (refit / cond) | 0.0788 / 0.0785 | 0.0958 / 0.0785 |
| margin / floor, E_refit | **4.625x** | **1.632x** |
| margin / floor, E_cond | **4.637x** | **1.991x** |

| clause | hit | pit |
|---|---|---|
| A1 E_refit >= MDE95 | **PASS** | **PASS** |
| A2 E_cond >= MDE95 | **PASS** | **PASS** |
| A3 zero-information twin sub-floor | **PASS** (twin 0.04446, 0.769x) | **PASS** (twin 0.00414, 0.059x) |
| A4 permutation null p <= 0.05 | **PASS** (p = 0.0000, null p95 0.04753) | **PASS** (p = 0.0015, null p95 0.05349) |
| A5 fold mean > 0, majority positive | **PASS** (mean 0.2516, 7/7) | **PASS** (mean 0.09991, 5/6) |
| A6 block-rho CI excludes 0 AND AUC CI excludes 0.5 | **PASS** | **PASS, by 0.0034** |

`battery.two_metric`: block-rho, (side x fold-year) block-normalized, both sides pooled,
n = 1,927: **0.17633**, E_refit CI95 [0.11847, 0.22204], MDE95 0.0433, 4.075x. Track-record
AUC on the production-bearing pool (the section-3 carve-out's named admissible substitute):
hit **0.78010** CI95 [0.70370, 0.82624], pit **0.57634** CI95 [0.50344, 0.63442].

**The provisional model passes the full section-2 battery on both sides.** The estimators
agree on every part-A cell; the conditional floor is tighter on the pitcher side (0.0576
against 0.0703) and the verdict does not turn on it.

Three things in that table are worth reading rather than skipping:

- **The pitcher AUC interval clears 0.5 by 0.0034.** A6 is a rule this lane added (threshold
  4) and on the pitcher side it is decisive at the third decimal. Disclosed in 7.8.
- **The hitter zero-information twin scored 0.04446, which is 0.769x of the floor.** It
  passed, but a single permuted draw landing that close is a reminder that the floor is
  0.0578 and not 0.005. The twin sits inside its own null band (p95 0.04753), so it is an
  ordinary draw and not a leak.
- **Per-fold the hitter model runs 0.05423 (2024) to 0.45769 (2019)** and the pitcher model
  0.28812 (2022) to -0.01893 (2024). Both sides' weakest fold is the most recent one, which
  is also the most censored. A5 is a stability check, not a replication, because
  forward-chained folds share training rows.

### 7.4 Part B: the routed cohort, the question routing never asked

`routed`. B0 first, verified rather than asserted: on **570 of 570** hitter and **411 of
411** pitcher routed rows the incumbent flagship grade is a single distinct value, **20.0**,
with predictor variance **0.0**. Its Spearman is undefined; the convention names it 0.0.

| | **hit (PRIMARY)** | pit (secondary) |
|---|---|---|
| n routed / n scored | 570 / 1,032 (55.23%) | 411 / 895 (45.92%) |
| **rho_prov, served grade, weighted** | **0.20500** | **0.10858** |
| rho_prov, unweighted | 0.19800 | 0.12061 |
| E_refit sd / MDE95 | 0.06789 / **0.1117** | 0.07728 / **0.1271** |
| E_cond sd / MDE95 | 0.04933 / **0.0812** | 0.05032 / **0.0828** |
| Bonferroni k=4 (refit / cond) | 0.1522 / 0.1106 | 0.1732 / 0.1128 |
| margin / floor, E_refit | **1.836x** | **0.854x** |
| margin / floor, E_cond | **2.526x** | **1.312x** |
| E_refit CI95 | [0.04238, 0.31056] | [-0.06580, 0.23628] |
| bootstrap p(rho <= 0), refit / cond | 0.0045 / 0.0000 | 0.1165 / 0.0165 |
| permutation null p95 | 0.06967 | 0.08358 |

| clause | **hit (PRIMARY)** | pit (secondary) |
|---|---|---|
| B1 route 1, E_refit | **PASS** | **FAIL, NULL at 0.854x** |
| B2 route 1, E_cond | **PASS** | **PASS, 1.312x** |
| B3 route 2, above the permutation p95 | **PASS** (0.20500 > 0.06967) | **PASS** (0.10858 > 0.08358) |
| B4 zero-information twin sub-floor | **PASS** (twin -0.07346, 0.658x) | **PASS** (twin 0.02713, 0.213x) |
| B6 clears Bonferroni k=4 | **PASS** both estimators | FAIL both estimators |
| estimators agree | yes | **NO** |

**THE ANSWER, hitters, the pre-registered primary: YES, the routing is earned on rank.**
On the routed cohort itself the provisional grade orders realized WAR at rho 0.20500. It
clears its sampling floor under both estimators (1.836x and 2.526x), it clears the
permutation null band that models the incumbent tie block honestly (route 2), and it clears
the Bonferroni-adjusted floor it was not required to clear. The two floors agree.

**THE ANSWER, pitchers: UNRESOLVED, and the two registered estimators disagree about it.**
Under E_refit rho 0.10858 is 0.854x of a 0.1271 floor, a NULL. Under E_cond it is 1.312x of
a 0.0828 floor, a RESOLVABLE WIN. This is exactly the split `POWER_GATE.md` 7.1 warned a
published claim must name, and it is the only cell in this lane where the instrument choice
decides the verdict. **Neither number may be quoted alone.** It clears route 2 (0.10858
against a null p95 of 0.08358, two-sided p = 0.0250) and fails Bonferroni under both.

The honest one-sentence pitcher verdict: given this training corpus the pitcher routed
ordering is real, and over redraws of the corpus it is not resolvable.

### 7.5 B5, the control that would have embarrassed this lane, and it did

`routed.*.B5_dumb_controls`. Paired bootstrap, identical rows:

| | hit | pit |
|---|---|---|
| rho, provisional grade | 0.20500 | 0.10858 |
| rho, `level_rank` alone | 0.13436 | 0.06130 |
| rho, `-age_rel_level` alone | 0.13476 | **0.14331** |
| paired delta, prov minus level_rank | +0.07064 | +0.04728 |
| paired sd / MDE95, E_refit | 0.04665 / 0.0767 | 0.06265 / 0.1031 |
| paired CI95 | [-0.02302, 0.16215] | [-0.07507, 0.16969] |
| margin / floor | **0.921x** | **0.459x** |
| verdict | **NULL** | **NULL** |

**On NEITHER side can this lane resolve that the provisional model beats a one-column
lookup available with no fit at all.** On hitters the model is ahead by +0.0706 and that is
0.921x of its own paired floor, so close and still a null. On pitchers a single column,
age-for-level with the sign flipped, scores **0.14331 against the model's 0.10858** on the
same rows.

That does not overturn 7.4: routing replaced a CONSTANT, not a level lookup, and against the
constant the hitter result stands. But the natural follow-up question, "is the model doing
anything a sort by level or by age would not", is **not answered in the affirmative by this
evidence on either side**, and on the pitcher side the sign points the other way. This is
reported because it was measured, and it is the single most useful thing in this document
for whoever works on the provisional model next.

### 7.6 The sensitivity that DOES move a verdict, and the analog's own limits

`routed.*.anchor_sensitivity`, B = 500 (so the 35.0 row's floor differs from 7.4's B = 2,000
row by Monte-Carlo noise; both are published):

| anchor | hit n / rho / refit / cond | pit n / rho / refit / cond |
|---|---|---|
| 30.0 | 951 / 0.21084 / 2.775x WIN / 3.579x WIN | 854 / 0.09299 / 1.298x WIN / 1.656x WIN |
| **35.0 (shipped)** | 570 / 0.20500 / 1.931x WIN / 2.477x WIN | 411 / 0.10858 / **0.855x NULL** / 1.313x WIN |
| 40.0 | 73 / 0.11983 / 0.393x NULL / 0.533x NULL | 27 / 0.26598 / 0.570x NULL / 0.859x NULL |

**Threshold 3 determines the pitcher verdict.** At 30.0 the pitcher cut is a resolvable win
under BOTH estimators; at 35.0 they split; at 40.0 the cohort collapses to 27 rows and
nothing resolves. The hitter verdict is stable across 30.0 and 35.0 and is lost at 40.0 only
to sample size (n 73). **35.0 is not a free parameter:** it is the value
`consensus.CONSTANT_ANCHOR_SOURCES` actually stamps, verified in-repo in two places
(`efv_ungraded.flagship_owns`, "2,632 of the 2,720 constant-only players ... every one of
them at fv_raw exactly 35.0"; and the `efv_score` FLOOR ROUTING block). The primary answer
is the 35.0 row. The disclosure is that the pitcher answer does not survive moving it.

**How much of a hypothetical the analog is, quantified.** `routed.*.B0_incumbent`. The
analog rows DO carry real scout anchors in the labeled matrix; they are being scored as if
they did not. Their REAL-anchor flagship grade ranks the same rows at **0.26998** (hit) and
**0.21316** (pit), i.e. better than the provisional grade does. That column does not exist
for a live routed player, so it is not a competitor; it is the size of the selection. Debut
rate in the analog is **34.91%** (hit) and **63.99%** (pit), against a served routed cohort
that is org filler. Read 7.4 with that in front of it.

### 7.7 Part C1: `_PROV_RANK_PENALTY` re-derived on the partition routing creates

`penalty.estimator_b`. Pool P = 981 routed rows displaying `provisional_grade - delta`,
pool G = 946 non-routed rows displaying the flagship grade, **793,763** non-tied cross-pool
pairs. Grid [-4, 16] step 0.25 as pre-registered.

| quantity | value |
|---|---|
| argmax delta | **-4.00, WHICH IS THE GRID'S LOWER BOUNDARY** |
| concordance at argmax | 0.57311 |
| concordance at the shipped 0 | 0.56362 |
| concordance at the retired 4 | 0.55515 |
| concordance at the 2026-07-23 argmax 3.75 | 0.55566 |
| bootstrap CI95 on argmax (B = 1,000) | [-4.00, -4.00] |
| share of draws with argmax <= 0 | 0.999 |
| shipped 0 inside CI95 | **no** |

**The pre-registered grid did not contain the optimum.** Disclosed post-hoc widening to
[-20, 16], run once, both published: interior argmax **-10.00**, concordance 0.58922. The
concordance curve is monotone decreasing in delta over the entire pre-registered range
(-4: 0.57311, 0: 0.56362, 4: 0.55515, 8: 0.54782, 16: 0.54217), so the two grids say the
same thing and the widening changes no conclusion.

**This lane declines to act on that number, and says why rather than burying it.**
`penalty.estimator_b.pool_diagnostics`: pool P mean display grade 29.63 against pool G's
43.63, mean realized WAR 1.046 against 2.105, **debut rate 0.471 against 0.732**. Pool P
here is real-anchored labeled prospects re-scored as if nobody had graded them, not the org
filler routing serves. The estimator is being asked which of two grade scales orders
outcomes better, and it answers with the selection built into its own pool. A -10 display
bonus for provisional rows on the live board has no support from this measurement.

What the measurement DOES support, and it is not nothing:

- **The shipped 0 is better than the retired 4** by 0.00847 of concordance over 793,763
  pairs, and better than the 2026-07-23 argmax of 3.75 by 0.00796.
- **No positive penalty is supported anywhere on the grid.** The 2026-07-23 lab's closing
  instruction, "if ever revised, the direction is UP (5-6), never down", does not hold on the
  pool routing created.
- **Recommendation: KEEP 0.** No edit to `prospx/index.html` is requested. The F2
  monotonicity argument that set it to 0 is independent of, and stronger than, this rank
  argument, and it is the reason the recommendation does not depend on the pool defect above.

### 7.8 What determined what: the self-added thresholds, checked

| threshold | determined a verdict | evidence |
|---|---|---|
| 1, statistic = served grade, pair-weighted | **no** in part A; **not fully checkable** in part B | part A: all four variants (grade or `_war`, weighted or unweighted) clear every floor on both sides, largest spread 0.02057. Part B: the pitcher routed point moves 0.10858 to 0.12061 unweighted and stays below the weighted-statistic E_refit floor, but **no floor was derived for the unweighted statistic**, so this check is indicative and not conclusive. Stated as a gap. |
| 2, B = 2,000 and seed 20260808 | **no** | every part-A and part-B margin is 0.85x or further from its floor; none sits inside a Monte-Carlo width. |
| 3, routed-analog anchor 35.0 | **YES, for the pitcher routed cut** | 7.6. Disclosed in the headline. The value is verified in-repo, not chosen. |
| 4a, A5 rule (mean > 0, majority positive) | no | 7/7 and 5/6. |
| 4b, A6 rule (both CI exclude their null) | **YES, for the pitcher side, by 0.0034 of AUC** | pit AUC CI95 lower bound 0.50344. Disclosed in the headline. |
| 4c, alpha 0.05 for A4 and B3 | no | p = 0.0000 and 0.0015. |
| 4d, C1 grid range | **YES, the argmax hit its boundary** | 7.7, widened once and disclosed; conclusion unchanged. |

**Multiplicity, with n.** Four pre-registered cuts (2 sides x {full pool, routed}).
Unadjusted: **4 of 4** clear under E_cond, **3 of 4** under E_refit. Bonferroni k = 4
(z = 2.2414): **3 of 4** under each estimator. The cut that fails is pitcher routed, under
both. The primary cut, hitter routed, clears every one of those six bars.

### 7.9 What this lane did NOT establish

- **Nothing about the served population.** 7.2's level table is the reason.
- **Nothing about the grade LEVEL.** Every statistic here is a rank statistic. Calibration
  to FV units, surplus dollars and `p_bust` are out of scope.
- **Nothing about the exposure sub-floor clamp**, which cannot be reproduced historically.
- **Nothing about the 184 above-floor rows** routing deliberately does not touch.
- **No licence to widen routing, un-cap the grade, or move KNEE/CEIL.** Part 5 stands.

### 7.10 Headline, with its disclosures

**The provisional model clears the full section-2 battery on both sides of its own labeled
pool (rho 0.26729 hit at 4.63x its floor, 0.11476 pit at 1.63x, all four mandatory controls
passing under both registered estimators). On the ROUTED cohort the hitter side is earned on
rank (0.20500, 1.84x refit and 2.53x conditional, above the permutation null band, clearing
Bonferroni k=4), and the pitcher side is UNRESOLVED with the two estimators disagreeing
(0.10858: NULL at 0.85x under E_refit, RESOLVABLE WIN at 1.31x under E_cond). Two self-added
thresholds determined verdicts and are disclosed: the routed-analog anchor value 35.0 decides
the pitcher routed cut, and this lane's A6 rule clears the pitcher AUC by 0.0034. On NEITHER
side can the model be resolved above a one-column lookup, and on pitchers age-for-level alone
outscores it 0.14331 to 0.10858.**

Per part 5 the pitcher result is a finding about the ROUTING and the decision is the
owner's. It is not a recommendation to revert: routing also rests on a coherence argument
this lane cannot measure, and the honest statement is that on the pitcher side that
coherence argument is currently the stronger of the two supports.

`_PROV_RANK_PENALTY` is already 0 and stays 0.
