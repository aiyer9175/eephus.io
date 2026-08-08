# Lane I4 + I5: the hitter full-pool loss, and a floor per cohort cell

Producer: `python tools/efv_cohort_floor_lab.py all`
Ledger: `data/xfv_cohort_floors.json`
Basis: `docs/EFV_GATE_STANDARD.md` section 1a (11-fold, pair-weighted) and section 2
(mandatory controls).

---

## PART 0. PRE-REGISTRATION (written BEFORE any fit or measurement was run)

Registered 2026-08-07, before the first `efv_cohort_floor_lab.py` run. Nothing below
this line in Part 0 was edited after a result was seen. The results live in Parts 1-5.

### 0.1 What is being measured

Three quantities, all under ONE estimator, the paired bootstrap that already ships:

| id | quantity | pool |
|---|---|---|
| Q1 | model-vs-consensus pooled-rho delta on `full_pool_km`, hit and pit | full pool (debuted + busts minus recent busts) |
| Q2 | model-vs-consensus pooled-rho delta restricted to one scoreboard cell | debuted pool, `efv_lab_runner.data_for` rows |
| Q3 | the same delta, pair-weighted vs unweighted, reported side by side | both of the above |

### 0.2 The estimator, and the rule that governs changing it

The estimator is the one registered in `docs/EFV_GATE_STANDARD.md` section 2.1 and
implemented in `tools/efv_mde_lab.py`: **a paired bootstrap that resamples the WHOLE
pool, train and test together, and refits consensus OLS plus the weighted ridge on
every draw.** This lab imports `ridge_fit`, `ridge_pred`, `ols_fit` and `wrho`
directly from `tools/efv_mde_lab.py` rather than re-implementing them, so the
primitives are bit-identical to the shipped floor.

MDE95 one-sided = 1.645 \* sd(delta), the convention recorded in section 1.

**THE POWER-LAUNDERING RULE.** A change that makes a floor SMALLER looks like
progress and is usually not. A tighter floor makes an improvement CERTIFIABLE; it does
not create one. Therefore:

> No estimator other than the shipped paired bootstrap may contribute a single number
> to this document until it has passed a NOMINAL COVERAGE CHECK under a null where the
> truth is known by construction: many independently generated datasets, the true
> sampling sd measured across them, and the bootstrap's own interval required to cover
> the truth at >= 95%. An estimator that UNDER-COVERS is rejected regardless of how
> much power it appears to buy.

Two estimator variants appear below and both are declared here in advance:

1. **Cell restriction (Q2).** Same resample, same refit, delta computed on the subset
   of resampled rows that land in the cell. This is a restriction of the statistic,
   not a new estimator, but it is put through the coverage check anyway because cell n
   is small and a bootstrap can under-cover in thin cells.
2. **A conservative floor BOUND for the two head-to-head archetype cells.** Those cells
   live on the `source_backtest` common set, a different instrument with its own
   measured floor (`data/xfv_headtohead_gap.json`, MDE95 0.0352 at n = 3,210). Scaling
   that by sqrt(3210 / n_cell) IGNORES refit variance and cell-composition variance,
   both of which are strictly positive, so it is a LOWER BOUND on the true cell floor.
   It is admissible for one purpose only: **closing a cell.** If the lower bound
   already exceeds the margin, the cell is a null and no tighter measurement can
   rescue it. It may never be used to OPEN a cell or to certify a win.

### 0.3 Success criteria, registered in advance

**I4 (Q1).** The cell is ADJUDICATED if |point delta| >= MDE95 one-sided on its own
full-pool floor. Three registered outcomes:

- **RESOLVABLE LOSS**: hitter delta <= -MDE95. Then the loss is real and must be
  PUBLISHED, with proposed placement and wording in Part 2.
- **NULL**: |delta| < MDE95. Then the cell is closed and the -0.0215 must stop being
  quotable in either direction.
- **INADMISSIBLE**: the carve-out at `docs/EFV_GATE_STANDARD.md:110-133` is found to
  taint the statistic. Then the cell cannot be published either way, and THAT is the
  finding. Registered test for this branch, in advance:
  - (a) the share of the INFORMATIVE pair mass of `full_pool_km` Spearman that is a
    bust-vs-debuted pair. The busts are tied at target 0, so those pairs carry no
    ordering information at all and must be removed from the denominator. If the
    bust-vs-debuted share of the remaining pairs exceeds 50%, the statistic is
    majority a debut / no-debut discrimination and the carve-out reaches it.
  - (b) whether the shipped feature spec can SENSE a missing MiLB block, per side.
  - (c) the empirical debut rate conditional on that sensor, in the full pool.
  - The branch fires if (a) is over 50% AND (b) is true for the side in question.
- Predicted before running: I expect (a) to be over 50% because busts are roughly half
  the full pool and are all tied at the bottom. I have NOT yet checked (b) or (c).

**I4 mechanism.** The plan hypothesizes the loss is concentrated at the debut margin.
Registered test, run on the SAME full-pool forward chain: split the pooled delta into
(i) a bust-vs-debuted discrimination leg, scored as AUC, and (ii) a within-debuted rank
leg, scored as Spearman on the debuted subset of the full-pool fit. The hypothesis is
CONFIRMED only if leg (i) is negative for hitters and leg (ii) is not, and if pitchers
show the mirror. Asserting the hypothesis without this split is not permitted.

**I5 (Q2).** For each of the nine cells in the plan, report MDE95 and compare to the
published margin. Registered classification:

- **ADJUDICATED**: |margin| >= MDE95. Only these may carry a per-cohort claim or a
  per-cohort fix proposal.
- **NULL, CLOSED**: |margin| < MDE95. No fix may be proposed. The cell is removed from
  the experiment queue as unmeasurable at current n.

Registered prediction: most cells will close. A lane that closes eight of nine has
succeeded. **No per-cohort fix will be proposed for any cell classified NULL**, and
this rule binds even if the point estimate is large, because a large point estimate in
a thin cell is what noise looks like.

**Elite band.** Confirmed from the existing ledger only (`data/xfv_driver_elite_band.json`).
Not re-derived.

**Q3 (weighting diagnostic).** Report the pair-weighted and unweighted floor AND point
for every quantity above. Registered as REPORT-ONLY: nothing is switched in this wave.
The question asked is whether `observed_seasons/6` is the right estimator for a RANK
statistic, and the answer is argued, not acted on.

### 0.4 What this lane may NOT do

- May not write any file outside its OWNS block.
- May not change `efv_model.SCORED_YEARS`, the weighting, the lambda, or the feature
  spec. Feature-drop runs in Part 2 are DIAGNOSTIC probes and are labelled as such;
  none of them is a ship proposal.
- May not run pytest.
- May not report a number without a `file:line` or an artifact key.

---

## PART 1. REPRODUCTION. Every number the plan asserts, reproduced.

`python tools/efv_cohort_floor_lab.py repro`. The replica is this lab's own forward
chain built on the shipped bootstrap primitives, run against the frames in
`efv_model.run:2514-2516`.

| cut | artifact n | artifact cons | artifact blend | artifact delta | replica delta | gap |
|---|---|---|---|---|---|---|
| hit `debuted_km` | 755 | 0.3919 | 0.3993 | +0.0074 | +0.00741 | +0.00001 |
| hit `full_pool_km` | 1,792 | 0.3002 | 0.2787 | **-0.0215** | -0.02143 | +0.00007 |
| pit `debuted_km` | 890 | 0.2495 | 0.2562 | +0.0067 | +0.00669 | -0.00001 |
| pit `full_pool_km` | 1,886 | 0.2013 | 0.2171 | **+0.0158** | +0.01571 | -0.00009 |

Artifact keys: `data/xfv_eval.json` and `data/xfv_eval_pitcher.json`,
`evals.<cut>.pooled_oos.{baseline,blend}.spearman`.

**BOTH I4 PREMISES REPRODUCE.** The hitter full pool is -0.0215 on n = 1,792 and the
pitcher full pool is +0.0158 on n = 1,886, and -0.0215 is indeed larger in magnitude
than any margin eFV wins by anywhere on this eval.

One honest discrepancy: the pitcher replica scores 1,885 rows where the artifact
records 1,886. The artifact carries `generated_at` 2026-08-06 and the matrix on disk
has moved since, so one row entered or left. It is 0.05% of the pool and it moves the
delta by 9e-5. Recorded, not chased.

All nine weak cells reproduce verbatim from `data/xfv_scoreboard_eval.json weak_cells`,
and the replica margin matches the published margin to 5e-4 or better on every one
(Part 4).

**Elite band, CONFIRMED not re-derived**, from `data/xfv_driver_elite_band.json`
`arms.<side>.b_elite_eval`:

| side | n scored | delta | own MDE95 | floor / margin |
|---|---|---|---|---|
| hit | 76 | -0.0655 | 0.1598 | 2.44x |
| pit | 26 | +0.1577 | 0.3543 | 2.25x |

Unresolvable, as the plan states. Closed, no further work.

---

## PART 2. I4. THE VERDICT: NULL, AND THE CELL IS ALSO INADMISSIBLE.

### 2.1 The floor. The plan's prediction is right; its conclusion is not.

`python tools/efv_cohort_floor_lab.py fullpool 2000`, ledger
`data/xfv_cohort_floors.json i4_full_pool`. Same estimator as
`data/xfv_mde_floor.json`: whole pool resampled, ridge and consensus OLS refit every
draw, B = 2000, seed 20260807.

| side | basis | point delta | sd | MDE95 (1-sided) | margin / floor | verdict |
|---|---|---|---|---|---|---|
| hit | pair-weighted | **-0.02143** | 0.01806 | **0.0297** | **0.72x** | **NULL** |
| hit | unweighted | -0.01879 | 0.01646 | 0.0271 | 0.69x | NULL |
| pit | pair-weighted | +0.01571 | 0.01613 | 0.0265 | 0.59x | NULL |
| pit | unweighted | +0.01676 | 0.01509 | 0.0248 | 0.68x | NULL |

The plan predicted the full-pool floor would be smaller than the 0.0440 debuted floor
because n is 2.4x. **CONFIRMED**: 0.0297 against 0.0440, a 32% tightening. This is the
first place on this eval where more rows actually bought power, and the reason is
visible in the mechanism the gate standard already records: the bootstrap's variance is
dominated by the ridge REFIT, and the full-pool frame trains the ridge on 1,792 rows
instead of 755.

**And the loss still does not clear it.** -0.0214 is 72% of its own floor. eFV does not
resolvably lose the hitter full pool. `hit.full_pool_km` is a **NULL**, and the
symmetric statement holds for the pitcher: the +0.0158 is not a win either, at 59% of
its floor. The 95% bootstrap interval on the hitter delta is [-0.0541, +0.0174] and
crosses zero; P(delta > 0) = 0.156.

Registered outcome fired: **NULL**, not RESOLVABLE LOSS. The -0.0215 must stop being
quotable in either direction.

### 2.2 The carve-out DOES reach this cut, on the hitter side only.

`python tools/efv_cohort_floor_lab.py carveout`, ledger key `carveout_test`.

The registered test was whether `full_pool_km` Spearman is majority the same
debut / no-debut contrast the carve-out at `docs/EFV_GATE_STANDARD.md:110-133` bans.

**Every bust target in the full pool is EXACTLY 0.0** (verified, both sides; only 3
debuted rows share that value). So the bust block is one enormous tie in the target,
and bust-against-bust pairs carry no ordering information at all. Removing them from
the denominator:

| side | n | busts | debuted | informative pairs that are BUST x DEBUTED | uninformative bust x bust pairs |
|---|---|---|---|---|---|
| hit | 1,792 | 1,037 | 755 | **73.3%** (782,935 of 1,067,570) | 537,166 |
| pit | 1,885 | 995 | 890 | **69.1%** (885,550 of 1,281,155) | 494,515 |

`full_pool_km` Spearman is therefore roughly three quarters a debut / no-debut
discrimination statistic wearing a rank correlation's clothes.

And the hitter feature set carries the sensor. `efv_model._feature_spec("hit")` includes
**`milb_missing`**; `_feature_spec("pit")` does not (9 pitcher features, none of them a
missingness indicator). In the hitter full pool `milb_missing` fires on 51 rows whose
debut rate is **5.9%** against **46.0%** for the rest, which is the carve-out's
near-deterministic-label-proxy signature at small scale.

> **THE CARVE-OUT REACHES `hit.full_pool_km`. That cell cannot be published as a
> model-vs-consensus verdict in either direction, independently of its floor.** It is
> majority the banned statistic, and the candidate being scored can sense the missing
> block. The pitcher cut fails only the first half of the test (69.1% debut-margin
> pairs, no sensor in the spec), so the carve-out does not reach `pit.full_pool_km`.

**This is itself the finding, and it is louder than the loss would have been.** The
audit plan and the eval artifact both treat `full_pool_km` as a co-equal cut with
`debuted_km`. It is not. It is 73% a statistic the gate standard already retired for
this candidate class, and it has been sitting in the headline pair since the 11-fold
promotion.

Magnitude, honestly: the sensor is thin, and dropping or permuting it barely moves the
RANK number (`i4_mechanism.hit.sensor_probe`: shipped rho delta -0.02143, sensor
dropped -0.02196, sensor row-permuted -0.02139). It moves the AUC leg exactly as the
carve-out describes, +0.0082 shipped against +0.0056 for the row-permuted twin, so 32%
of the hitter debut-margin AUC edge is missingness rather than prediction. So the
contamination is real and small. Admissibility is not a magnitude question: the cell is
already a NULL, and the carve-out means it would not have been publishable even if it
had cleared its floor.

### 2.3 The mechanism. The plan's obvious hypothesis is FALSE.

The plan hypothesized the model is worse than the consensus at the debut / no-debut
margin specifically. Registered test (part 0.3), run on the same full-pool chain,
ledger key `i4_mechanism`:

| hitter leg | consensus | blend | delta |
|---|---|---|---|
| pooled full-pool rho | 0.3002 | 0.2787 | **-0.0214** |
| debut / no-debut AUC | 0.7784 | 0.7866 | **+0.0082** |
| within-debuted rho, same full-pool fit, n 755 | 0.4076 | 0.4032 | -0.0044 |

**FALSE.** The model BEATS the consensus at the debut margin by +0.0082 AUC, and its
within-debuted rank deficit is -0.0044. Neither leg is anywhere near -0.0214. The
pitcher mirror the hypothesis predicts does not appear either: pitcher AUC +0.0234 and
within-debuted +0.0157, both positive, same sign as its pooled +0.0157.

The hypothesis was asserted in the plan and it does not survive contact. It is recorded
here as FALSE so no later lane re-opens it.

### 2.4 What actually produces the -0.0214: a TIE BLOCK the consensus gets for free.

`python tools/efv_cohort_floor_lab.py ties`, ledger key `i4_tie_structure`.

The consensus leg is `max(0.0, a + b*FV)` (`efv_model._run_eval:1481`). In the full
pool that clamp collapses **701 of 1,792 hitter rows onto exactly 0.0**, and 562 of
those 701 are busts, whose target is also exactly 0.0. Two aligned tie blocks. Inside a
tie block a rater makes no ordering claim, so it cannot be scored wrong. The blend has
1,642 distinct values on the same rows, because the model term is continuous: it is
scored on orderings the consensus is excused from.

Zero-information control, in the idiom of `EFV_GATE_STANDARD.md` section 2.2: add noise
1e-9 of the range to the consensus leg. It carries no information whatsoever; it only
breaks exact ties.

| side | pool | cons rows clamped to 0 | cons rho | cons rho, ties broken by noise | tie credit | delta as published | delta at equal resolution |
|---|---|---|---|---|---|---|---|
| hit | full | 701 (562 busts) | 0.3002 | 0.2904 | **+0.0098** | -0.0214 | **-0.0117** |
| hit | debuted | 57 (0 busts) | 0.3919 | 0.3918 | +0.0001 | +0.0074 | +0.0075 |
| pit | full | 548 (400 busts) | 0.2015 | 0.1987 | +0.0028 | +0.0157 | +0.0185 |
| pit | debuted | 49 (0 busts) | 0.2494 | 0.2494 | +0.0000 | +0.0067 | +0.0067 |

**46% of the hitter full-pool gap is a tie-structure artifact of the baseline's own
zero-clamp, not a property of either predictor's ordering.** The control moves the
debuted-pool consensus by 0.0001 and the full-pool consensus by 0.0098, a factor of
98, which is what a pool-specific artifact looks like rather than a measurement quirk.
At equal resolution the hitter gap is -0.0117, which is 0.39x its floor: further inside
the noise than the published number, in the same direction.

This is the second reason the cut is not a clean model-vs-consensus instrument, and it
is independent of the carve-out. It also explains the side split the plan flagged
without explaining: the hitter consensus collapses 39% of its rows onto one value and
the pitcher consensus 29%, so the hitter baseline draws more than three times the tie
credit.

### 2.5 WHERE THIS SHOULD BE PUBLISHED, AND IN WHAT WORDS.

The plan said a resolvable loss must be published, not buried. It is not a resolvable
loss, so what must be published is the reason the cell cannot adjudicate. Three
placements, in the voice the eFV head-to-head already uses.

**(a) `docs/EFV_GATE_STANDARD.md` section 1a, the floor table.** The table has no
full-pool row, so `efv_model.MDE95_POOLED_RHO` (0.044, a DEBUTED-pool constant) is
currently applied to the full-pool cut by `_honest_note:1682`. Add:

> | model vs consensus, pooled rho, FULL POOL, pair-weighted | **0.0297 hit / 0.0265 pit** | 0.0181 / 0.0161 | 1,792 / 1,885 |
> | model vs consensus, pooled rho, FULL POOL, unweighted | 0.0271 hit / 0.0248 pit | 0.0165 / 0.0151 | 1,792 / 1,885 |
>
> Measured 2026-08-07b by `python tools/efv_cohort_floor_lab.py fullpool 2000`; ledger
> `data/xfv_cohort_floors.json i4_full_pool`. This is the ONE row on this eval where
> more rows bought power: the full-pool frame trains the ridge on 1,792 rows instead of
> 755, and the bootstrap's variance is refit-dominated. Do not gate a full-pool claim
> against 0.044.

**(b) `docs/EFV_GATE_STANDARD.md`, extending the carve-out block at :110-133.** Append:

> **THE CARVE-OUT ALSO REACHES `full_pool_km` POOLED SPEARMAN ON THE HITTER SIDE
> (measured 2026-08-07b).** Every bust target in the full pool is exactly 0.0, so
> bust-against-bust pairs carry no ordering and 73.3% of the hitter cut's INFORMATIVE
> pair mass is a bust against a debuted player. That makes the cut three quarters the
> same debut / no-debut discrimination this carve-out bans, and `_feature_spec("hit")`
> carries `milb_missing` (fires on 51 rows, debut rate 5.9% against 46.0%). A
> row-permuted twin of that column gives back 32% of the hitter debut-margin AUC edge
> (+0.0082 shipped, +0.0056 permuted). `full_pool_km` pooled rho is therefore NOT
> admissible as a hitter model-vs-consensus verdict in either direction.
> `_feature_spec("pit")` carries no missingness indicator, so the pitcher cut is
> admissible, at a floor of 0.0265.
>
> Second, independent defect on the same cut, either side: the consensus leg's
> `max(0.0, ...)` clamp collapses 701 of 1,792 hitter rows (562 of them busts) onto one
> value that the target also holds. A pure-noise tie-break lowers the hitter consensus
> from 0.3002 to 0.2904 while moving the debuted-pool consensus by 0.0001. Roughly half
> the hitter full-pool gap is that tie credit. Ledger `data/xfv_cohort_floors.json
> i4_tie_structure`.

**(c) `efv_model._honest_note`, the sentence that ships into the artifact.** The hitter
note it renders today reads "eFV does not beat consensus FV on out-of-sample rank on
every cut (debuted_km +0.0074, full_pool_km -0.0215), and no gap reaches the 0.044 this
eval can resolve either way." Two things are wrong with it: 0.044 is the debuted floor
quoted against both cuts, and it leaves the reader thinking the -0.0215 is a real but
unresolved loss. Proposed replacement, same voice:

> eFV does not beat consensus FV on out-of-sample rank on every cut (debuted_km
> +0.0074, full_pool_km -0.0215), and neither gap reaches the floor its own cut can
> resolve (0.0440 debuted, 0.0297 full pool), so neither is a result. Read the full-pool
> cut with more care than that: 73% of its informative pairs are a bust against a
> debuted player, which makes it mostly the debut / no-debut discrimination the gate
> standard carves out for any candidate that can sense a missing MiLB block, and the
> hitter feature set carries one. Half the gap is also the consensus baseline's own
> zero-clamp tie block. That cut cannot settle a hitter rank claim in either direction.

**A SEPARATE DEFECT FOUND WHILE DOING THIS, owned by nobody in this wave.** The shipped
`data/xfv_eval.json` and `data/xfv_eval_pitcher.json` (`generated_at` 2026-08-06) still
carry the OLD HARDCODED `honest_note`: "lets eFV BEAT consensus FV on out-of-sample
rank for both cuts". That sentence is contradicted by the numbers in the same file
(hitter `full_pool_km` -0.0215). `_honest_note` was written precisely to make that
impossible and renders correctly when called today, but the artifacts predate it. **The
eval artifacts need a regen.** This lane owns no `data/` file but its own and did not
touch them.

---

## PART 3. THE NULL COVERAGE CHECK, RUN BEFORE ANY CELL FLOOR WAS QUOTED.

`python tools/efv_cohort_floor_lab.py nullcov`, ledger key `null_coverage_check`.

**Say it plainly, because this is the trap that makes this lane dangerous: any change
that makes a floor SMALLER looks like progress and is usually power laundering. A
tighter floor makes an improvement certifiable; it does not create one.** The only
estimator variant this lane introduces is restricting the delta to a cohort cell, and a
bootstrap can under-cover in a thin cell, so it had to earn its numbers under a null
where the truth is known by construction before a single cell floor was quoted.

Construction: 120 independently generated datasets with the eval's skeleton (n = 700, 6
forward-chained cohort-years, a consensus column carrying the signal, 4 model features
that are noisy copies of it, so the model has NO information the consensus lacks). The
truth is the Monte-Carlo sampling distribution across those 120 datasets. For 40 of
them the full paired bootstrap runs and its 95% percentile interval is checked against
that truth.

| statistic | true sampling sd | mean bootstrap sd | ratio | coverage of the truth | verdict |
|---|---|---|---|---|---|
| pooled delta | 0.01526 | 0.01794 | **1.175** | **97.5%** | PASS |
| cell-restricted delta (20% tag) | 0.03329 | 0.04299 | **1.292** | **100%** | PASS |

The estimator over-covers, by 18% on the pooled statistic and 29% on the cell
restriction. **That is the safe direction.** Every floor in Part 4 is therefore, if
anything, slightly too WIDE, so every cell this lane closes is closed conservatively
and no cell is closed by an estimator that bought power it had not earned. An estimator
that under-covered would have been rejected here regardless of how much power it
appeared to buy, and the cell floors would not have been reportable at all.

---

## PART 4. I5. A FLOOR PER CELL. ELEVEN OF ELEVEN CLOSE.

`python tools/efv_cohort_floor_lab.py cells 2000`, ledger key `i5_cells`. Same paired
bootstrap, resampling the whole `efv_lab_runner.data_for` pool and refitting; the delta
is then read on the resampled rows that land in the cell, so cell membership varies
draw to draw exactly as it would in a new sample. Every cell is read off the SAME draw,
which is why eight floors cost one bootstrap. Protocol matches
`tools/efv_scoreboard.py:_side_block` per cell type: pooled cells on `SCORED_YEARS` with
floors 50/12 and pair-weighted, the era cell on 2016-2023 with floors 60/10 and
unweighted, because that is how the published margin was computed.

| cell | n | published margin | replica | sd | MDE95 (1-sided) | floor / margin | boot cell n (p05-p95) | verdict |
|---|---|---|---|---|---|---|---|---|
| `hit.fv_tier.55` | 46 | -0.2271 | -0.2271 | 0.2004 | **0.3297** | 1.5x | 36-58 | **NULL, CLOSED** |
| `hit.fv_tier.60` | 34 | -0.0209 | -0.0209 | 0.2342 | **0.3853** | 18.4x | 25-44 | **NULL, CLOSED** |
| `hit.cohort.hs` | 201 | -0.0182 | -0.0183 | 0.0464 | **0.0764** | 4.2x | 181-222 | **NULL, CLOSED** |
| `hit.cohort.other` | 170 | -0.0195 | -0.0193 | 0.0568 | **0.0934** | 4.8x | 152-189 | **NULL, CLOSED** |
| `pit.fv_tier.50` | 101 | -0.0508 | -0.0505 | 0.1233 | **0.2029** | 4.0x | 86-116 | **NULL, CLOSED** |
| `pit.cohort.college` | 324 | -0.0023 | -0.0023 | 0.0406 | **0.0668** | 29.0x | 298-348 | **NULL, CLOSED** |
| `pit.cohort.hs` | 190 | -0.0211 | -0.0206 | 0.0614 | **0.1009** | 4.8x | 169-210 | **NULL, CLOSED** |
| `pit.era.<=2018` | 132 | -0.0202 | -0.0202 | 0.0852 | **0.1401** | 6.9x | 114-150 | **NULL, CLOSED** |

The two archetype cells the plan lists live on the `source_backtest` common set, a
different instrument. They are closed by the conservative LOWER BOUND registered in
part 0.2 item 2: sqrt-n scaling of the measured common-set floor (0.0352 at n = 3,210,
`data/xfv_headtohead_gap.json`), which ignores refit variance and cell-composition
variance and therefore UNDER-states the true cell floor. Admissible for closing a cell
only, never for opening one.

| cell | n | margin | floor LOWER BOUND | floor / margin, at least | verdict |
|---|---|---|---|---|---|
| `head_to_head.archetype.hs_bat` | 168 | -0.0277 | >= 0.1539 | >= 5.6x | **NULL, CLOSED** |
| `head_to_head.archetype.hs_arm` | 144 | -0.0183 | >= 0.1662 | >= 9.1x | **NULL, CLOSED** |
| `head_to_head.archetype.college_arm` | 244 | -0.0120 | >= 0.1277 | >= 10.6x | **NULL, CLOSED** |

Plus the elite band (Part 1), 2.44x / 2.25x, confirmed unresolvable.

### 4.1 WHICH CELLS CAN BE ADJUDICATED AT ALL: **NONE OF THEM.**

Zero of the nine cells the plan lists, zero of the eleven measured here, and neither
elite band arm. The tightest cell in the set is `hit.fv_tier.55`, whose spectacular
-0.2271 margin is still only 69% of its own 0.3297 floor: 46 rows cannot resolve a
0.2271 rank swing. `pit.cohort.college` is the extreme in the other direction at 29x.

**NO PER-COHORT FIX IS PROPOSED FOR ANY CELL, and this is not a hedge.** A per-cohort
lambda, a per-cohort feature, a per-cohort recalibration: none of them can be evaluated
on the instrument that would have to judge them, so shipping one would be shipping an
unmeasured change. The registered rule binds hardest exactly where the point estimate
is biggest, because a -0.2271 on 46 rows is what noise looks like, not what a defect
looks like.

**Recommendation to the scoreboard.** `weak_cells` currently publishes eleven negative
margins with a note pointing readers at the 0.044 POOLED floor. That floor is 4x to 12x
too small for these cells and reading a cell against it is how an unmeasurable cell
becomes an experiment queue item. Each `weak_cells` row should carry its own
`mde95_onesided` and an `adjudicable` boolean from `data/xfv_cohort_floors.json`. The
correct experiment queue derived from this lane is EMPTY.

---

## PART 5. THE WEIGHTING DIAGNOSTIC. REPORTED, NOT SWITCHED.

The plan asks whether `observed_seasons/6` is the right estimator for a rank statistic.
Three findings, all report-only in this wave.

**5.1 The unweighted floor is tighter everywhere, and it is tighter here too.** The
plan cites 0.0376 unweighted against 0.0440 pair-weighted on the debuted pool
(`data/xfv_mde_floor.json`). The full pool reproduces the pattern independently:

| pool / side | pair-weighted floor | unweighted floor | tightening |
|---|---|---|---|
| debuted hit | 0.0440 | 0.0376 | 15% |
| debuted pit | 0.0436 | 0.0376 | 14% |
| full hit | 0.0297 | 0.0271 | 9% |
| full pit | 0.0265 | 0.0248 | 6% |

The verdict does not change on any of the four: every cell is a NULL on both bases, and
the margin-over-floor ratio moves by at most 0.08. **The basis decision is not what is
holding any eFV claim back**, which is worth saying because it is the kind of knob that
attracts a re-litigation it cannot repay.

**5.2 The efficiency cost is roughly triple what the weights themselves imply.** Kish
effective n, (sum w)^2 / sum w^2, on the scored rows:

| pool | n | sum of weights | Kish n_eff | design effect | predicted sd inflation |
|---|---|---|---|---|---|
| hit debuted | 755 | 594.0 | 688.4 | 1.097 | 4.7% |
| pit debuted | 890 | 696.5 | 806.4 | 1.104 | 5.1% |
| hit full | 1,792 | 1,631.0 | 1,716.7 | 1.044 | 2.2% |
| pit full | 1,885 | 1,691.5 | 1,792.1 | 1.052 | 2.6% |

A design effect of 1.097 predicts a 4.7% wider sd. The measured widening on hit debuted
is 15%, and on hit full 9%. The weighting costs three to four times what a simple
variance-inflation account predicts. Something other than unequal weights is going on,
and it is the next paragraph.

**5.3 The estimator is a HALF-weighting, and that is the substantive objection.**
`prospect_path._weighted_spearman` (replicated bit-for-bit in `efv_mde_lab.wrho:151`)
computes the ranks **unweighted** over all rows, then takes a **weighted** covariance
and variance of those ranks. A 0.333-weight 2024 row therefore still displaces every
other row on the rank scale by a full unit; only its contribution to the moment is cut
to a third. For a rank statistic the row's rank footprint is the primary channel, so
this is not a coherent down-weighting of a censored row, it is a partial one. A
coherent version would build the ranks from the cumulative weight so a third-weight row
occupies a third of a rank slot.

Related bookkeeping error, worth fixing by whoever owns it:
`pooled_oos.*.n_effective` in `data/xfv_eval*.json` publishes the SUM OF WEIGHTS (594.0
hit), not the variance-based effective n (688.4). It understates the effective sample by
16% and it is the number a reader will use to sanity-check a floor.

**Recommendation: do not switch, and do not re-open this as a power question.** The
unweighted basis is 6-15% tighter and every verdict is identical on both, so switching
buys nothing that matters and re-opens a settled owner decision (2026-08-06). If it is
ever revisited, the reason should be 5.3, coherence, not 5.1, power. Chasing 5.1 is
exactly the power laundering part 0.2 bans.

---

## PART 6. SUMMARY LEDGER

| id | claim | verdict | evidence |
|---|---|---|---|
| I4-a | hit `full_pool_km` is -0.0215 on n 1,792; pit is +0.0158 on n 1,886 | **CONFIRMED** | `data/xfv_eval*.json evals.full_pool_km.pooled_oos`; replica gap 9e-5 or better |
| I4-b | the full-pool floor is smaller than the 0.0440 debuted floor | **CONFIRMED** | 0.0297 hit / 0.0265 pit, `i4_full_pool` |
| I4-c | eFV RESOLVABLY LOSES the hitter full pool | **FALSE** | -0.0214 is 0.72x its 0.0297 floor; CI95 [-0.0541, +0.0174] crosses zero |
| I4-d | the loss is concentrated at the debut / no-debut margin | **FALSE** | debut-margin AUC is +0.0082 FOR the model; within-debuted rho -0.0044 |
| I4-e | the `EFV_GATE_STANDARD.md:110-133` carve-out taints this cut | **CONFIRMED, hit only** | 73.3% of informative pairs are the debut margin; `milb_missing` in `_feature_spec("hit")`, 5.9% vs 46.0% debut rate; permuted twin returns 32% of the AUC edge |
| I4-f | 46% of the hitter gap is the baseline's own zero-clamp tie block | **NEW, CONFIRMED** | +0.0098 tie credit full pool vs +0.0001 debuted, pure-noise control |
| I5-a | eleven weak cells, each against its own floor | **ALL NULL, ALL CLOSED** | floors 1.5x to 29x the margins, `i5_cells` + `i5_archetype_bounds` |
| I5-b | the elite band is unresolvable | **CONFIRMED, not re-derived** | 2.44x hit / 2.25x pit, `data/xfv_driver_elite_band.json` |
| I5-c | the cell-restricted bootstrap covers nominally | **PASS, conservative** | coverage 100%, boot sd 1.29x the truth |
| Q3 | pair-weighted vs unweighted | **REPORTED, NOT SWITCHED** | unweighted 6-15% tighter, zero verdicts change |
| side | the shipped eval artifacts assert a claim their own numbers contradict | **DEFECT, regen owed** | `data/xfv_eval*.json honest_note` says "BEAT consensus for both cuts", the file's own hitter `full_pool_km` is -0.0215 |
