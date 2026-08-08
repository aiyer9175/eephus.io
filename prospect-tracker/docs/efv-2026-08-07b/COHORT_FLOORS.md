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

---
---

# WAVE 2 EXTENSION (2026-08-07b, Lane B): the five cells wave 1 never floored

Producer: `python tools/efv_cohort_floor_lab.py waveb`
Ledger: the `waveb_*` blocks of `data/xfv_cohort_floors.json`
Everything below this line was added in wave 2. Parts 0-6 above are wave 1 and are
unedited except for the two corrections logged in Part 6B.

## PART 0B. PRE-REGISTRATION (written BEFORE the wave-2 lab existed)

Registered 2026-08-07, wave 2. The file `tools/efv_cohort_floor_lab.py` did not yet
contain a `waveb`, `capture`, `archcells` or `eracells` mode when this part was
written; the placeholder at PART 5B was the last line of this document at that moment,
and nothing in Part 0B was edited after a floor was seen.

### 0B.0 Why this part exists, and what wave 1 got wrong

`data/xfv_scoreboard_eval.json` `weak_cells` has **SIXTEEN** rows. Wave 1's Part 6
ledger row I5-a says "eleven weak cells ... ALL NULL, ALL CLOSED". Eleven is the
number wave 1 measured. Five rows were never floored and appear nowhere in Parts 1-6:

| cell | metric | n | eFV | consensus | margin |
|---|---|---|---|---|---|
| `capture.curve_area` | `war_capture` | 3,678 | 0.8148 | 0.8229 | **-0.0081** |
| `head_to_head.archetype.college_arm` | `auc_contributor` | 244 | 0.6514 | 0.7078 | -0.0564 |
| `head_to_head.archetype.hs_arm` | `auc_contributor` | 144 | 0.6903 | 0.7149 | -0.0246 |
| `pit.era.<=2018` | `auc_contributor` | 132 | 0.7740 | 0.7841 | -0.0101 |
| `head_to_head.archetype.hs_bat` | `auc_contributor` | 168 | 0.7705 | 0.7744 | -0.0039 |

Wave 1 also closed the three `head_to_head.archetype.*` **spearman** cells with a
`sqrt(n_pool / n_cell)` rescale of a DIFFERENT instrument's floor and no bootstrap of
their own. Those numbers remain admissible only as LOWER BOUNDS; wave 2 relabels them
so in the artifact and then replaces them with a real bootstrap.

`capture.curve_area` is the target. It is n = 3,678, an order of magnitude larger than
any cell wave 1 floored and about twice the pool whose floor came in at 0.0297, so it
is the one cell on the list with a real chance of being adjudicable. It is plan item
**D11**. The site sells surplus DOLLARS, a value-weighted quantity; `curve_area` is the
value-weighted instrument, and the published headline is a rank correlation, which is
not.

### 0B.1 What was already known when this was registered

Honesty about the timeline, because three wave-1 lanes could not support their
pre-registration claims. Before writing this part I ran read-only replica probes in a
scratchpad outside the repo. What they established, and nothing more:

- the capture pool reproduces exactly outside `source_backtest.py` (3,677 rows against
  the published 3,678; areas 0.8148 / 0.8229 to 4 dp);
- the `pit.era.<=2018` AUC pair reproduces exactly (0.7740 / 0.7841, n = 132) from
  `load_cellpool("pit")` plus the era chain;
- the three archetype cells reproduce at exactly the published n (168 / 144 / 244) with
  the consensus leg exact and the eFV leg 0.0016 to 0.0030 high, because the published
  eFV grade is rounded to 0.1 FV by a display remap and mine is not;
- `curve_area` is algebraically a WAR-weighted mean rank (see 0B.4 K2);
- the consensus board has 230 distinct values over 3,677 rows and its largest tie block
  is 462 rows.

**No floor, no bootstrap, no MDE, no coverage check and no verdict existed at
registration time.** The K3 tie control and the K1 permutation null were each run once
in that probe, which is why they are registered below as MANDATORY rather than
optional: they had already shown they were live, and registering them here removes any
option to drop them if they came back inconvenient.

### 0B.2 Quantities

| id | quantity | pool |
|---|---|---|
| Q4 | `curve_area` delta (eFV minus consensus) on the pooled hit+pit capture board | 3,677 OOS-graded matrix rows carrying a consensus FV |
| Q5a | `auc_contributor` delta on `pit.era.<=2018` | the scoreboard era chain, unweighted |
| Q5b | `auc_contributor` AND `spearman` delta on the three archetype cells | one row per player, latest pre-debut all-source common read |

### 0B.3 Estimators. Both are reported for every cell.

The lane brief requires both, and they can disagree.

- **E1 REFIT-INCLUSIVE.** The shipped gate-standard protocol
  (`docs/EFV_GATE_STANDARD.md` section 2.1): resample the WHOLE per-side eFV matrix pool
  with replacement, train and test together, refit consensus OLS plus weighted ridge plus
  the linear output calibration on every draw, re-run the forward chain, then recompute
  the statistic on whatever rows the resampled pool scores. Primitives imported from
  `tools/efv_mde_lab.py`, never reimplemented.
- **E2 FITS-HELD-FIXED.** The shipped OOS grades are frozen at their point values and
  only the scored rows are resampled with replacement.

E1 and E2 measure different things. E1 carries refit variance and E2 does not, so E1 is
expected to be the wider; `tools/efv_mde_lab.py:11-14` records a test-only bootstrap
understating sd by 1.6-1.8x on the rank instrument. Both are reported for every cell.
**Registered tie-break: E1 governs the verdict**, because it is the estimator the
shipped gate uses, and any disagreement goes in the headline rather than being resolved
silently.

Resampling unit, registered explicitly for Q4: **the PLAYER, not the pair.**
`curve_area` is a whole-board statistic, so a draw must resample the board's rows and
re-rank them; there is no pair to resample. Each matrix row is one player-cohort and
enters at most one fold, so a draw duplicates a player into the same fold and never
splits one across train and test.

### 0B.4 Mandatory controls. All six are reported whatever they say.

- **K1 PERMUTATION NULL (required by the brief).** Shuffle the eFV board order within
  the pool, R = 400. `curve_area` must collapse toward its no-information value. That
  value is derived, not guessed: under a uniformly random order E[area] = (n+1)/(2n),
  which is 0.50014 at n = 3,677. PASS if the permuted mean is within 0.01 of it.
- **K2 EXACT RANK IDENTITY.** area = (n+1)/n - (1/(n\*tot)) \* sum_i war_i \* rank_i, so
  delta_area = -(1/(n\*tot)) \* sum_i war_i \* (rank_i^eFV - rank_i^cons). Checked to
  1e-9. Every attribution in Part 3B rests on this identity; if it fails, the
  attribution is withdrawn.
- **K3 TIE-RESOLUTION CONTROL (rule D, the dumbest explanation).** `consensus_fv_raw` is
  coarse and `source_backtest.py:673` sorts with a STABLE sort, so inside a consensus tie
  block the arbitrary input order decides who ranks first. That input order is the
  `oos_grades` dict order, which is side then cohort year, and older cohorts have had
  more years to accumulate career WAR. Control: recompute both areas with a RANDOM
  within-tie order over R = 400 seeds, and report where the published value sits in that
  distribution. If the published consensus area sits above the top of the random
  distribution, part of the margin is a zero-information ordering credit and the honest
  comparison is the one at equal resolution.
- **K4 CROSS-SIDE POOLING CONTROL.** The pooled board interleaves hitters and pitchers.
  eFV enters on a WAR scale, which is cross-side comparable; consensus enters on raw FV,
  which the `efv-fa-execution-2026-07-30` record says is NOT cross-side comparable.
  Report the delta computed WITHIN each side. If the loss is absent within side, it is a
  side-mixing artifact and not an ordering defect.
- **K5 OUTCOME-DEFINITION CONTROL.** `source_backtest.py:641-652` gives a row the
  universe's FULL CAREER WAR when the player is in the universe and the matrix's
  first-six-season label otherwise: two different outcome variables in one pool. Report
  the split, and recompute the delta with the six-season label on every row.
- **K6 THE TOP-REORDERING TEST (the brief's directional ask).** Hypothesis: eFV
  re-orders the top of the board in a way that helps rank correlation and hurts value
  capture. Registered test, not an assertion: the K2 identity gives an EXACT per-player
  attribution war_i \* delta_rank_i. Bucket it by consensus-rank decile and report which
  deciles carry the loss. Plus hybrid boards, consensus order for the top q% with eFV
  below and the mirror, for q in 5 / 10 / 20 / 50%. The hypothesis is CONFIRMED only if
  the loss is concentrated in the top deciles AND the consensus-top hybrid closes most
  of it. If the loss is spread across the board the hypothesis is REFUTED and must be
  reported as refuted.

### 0B.5 Coverage gate, two-sided

Rule F: when the product is a NULL, a floor that is too WIDE is the permissive
direction. So the coverage check is registered with a BAND, not a floor.

`curve_area` is a new statistic for this bootstrap, so it may not quote a number until
it passes a nominal coverage check under a synthetic null where the truth is known by
construction: wave 1's `nullcov` design with the capture area substituted for the rank
delta. Registered PASS band, in advance:

- `coverage_95` >= 0.90 (under-coverage guard; would make a RESOLVABLE verdict too easy);
- `sd_ratio_boot_over_true` <= 1.60 (over-width guard; would make a NULL verdict too easy).

If coverage fails low, no floor may be quoted at all. If the sd ratio fails high, floors
may be quoted but any NULL from them is downgraded to **NULL AT AN OVER-WIDE FLOOR** and
the over-width is stated in the headline.

### 0B.6 Success criteria, registered in advance

Per cell, per estimator: **RESOLVABLE LOSS** if |point| >= MDE95 one-sided
(1.645 \* sd) and the point is negative; **NULL** otherwise. Combined verdict:

- **RESOLVABLE LOSS** if E1 and E2 both resolve;
- **CONTESTED** if exactly one resolves. E1 governs, and the disagreement goes in the
  headline;
- **NULL, CLOSED** if neither resolves.

**Multiplicity (rule C).** This lane tests five cells. Alongside every MDE95 the lane
reports the Bonferroni floor at k = 5, MDE_bonf = 2.326 \* sd (one-sided alpha 0.01),
and a `survives_bonferroni_k5` flag. A cell that resolves at MDE95 but not at MDE_bonf
is reported as resolving only unadjusted, in those words.

### 0B.7 What this wave may NOT do

- **BLOCKED, and not re-proposable in any form:** the wave-1 proposal to write into
  `tools/efv_scoreboard.py` `weak_cells_note` a sentence declaring that every cell was
  given its own paired-bootstrap floor and that all of them are NULLs, or any sentence
  closing the weak-cell experiment queue. Five of the sixteen rows had no floor when
  that sentence was drafted, including the one most likely to be adjudicable.
- May not write any file outside the OWNS block: `tools/efv_cohort_floor_lab.py`,
  `data/xfv_cohort_floors.json`, this document.
- May not run pytest, and may not run git.
- May not quote a number that does not reproduce from `data/xfv_cohort_floors.json`.
- Wave 1's `sqrt(n)` archetype bounds may not be quoted anywhere, in prose or in an
  artifact string, without the words LOWER BOUND attached.

### 0B.8 If `curve_area` resolvably loses

Registered in advance so the answer is not written after the number is seen. If Q4
resolves as a loss, then consensus beats eFV on the value-weighted instrument on the
largest pool on the scoreboard. Placement and wording are drafted in PART 4B and bind
this lane's recommendation whichever way the number falls.

---

## 5B. RESULT (appended after the run)

Run: `python tools/efv_cohort_floor_lab.py waveb 2000`, 143 s. Every number below is a
key of `data/xfv_cohort_floors.json` under `waveb`, and nothing in Part 0B was touched
after the run.

### 5B.1 Verdict table

| cell | metric | n | margin | E1 refit floor | E2 fixed floor | verdict |
|---|---|---|---|---|---|---|
| `capture.curve_area` | war_capture | 3,677 | -0.00814 | 0.0133 (0.61x) | 0.0084 (0.97x) | **NULL, CLOSED** |
| `head_to_head.archetype.college_arm` | auc_contributor | 244 | -0.05484 | 0.0481 (1.14x) | 0.0458 (1.20x) | **RESOLVABLE LOSS, unadjusted only** |
| `head_to_head.archetype.hs_arm` | auc_contributor | 144 | -0.02155 | 0.0612 (0.35x) | 0.0401 (0.54x) | NULL, CLOSED |
| `pit.era.<=2018` | auc_contributor | 132 | -0.01005 | 0.0873 (0.12x) | 0.0546 (0.18x) | NULL, CLOSED |
| `head_to_head.archetype.hs_bat` | auc_contributor | 168 | -0.00193 | 0.0276 (0.07x) | 0.0203 (0.10x) | NULL, CLOSED |

Bonus re-measurements, replacing wave 1's LOWER BOUNDS with real bootstraps:

| cell | metric | n | margin | E1 refit floor | E2 fixed floor | verdict |
|---|---|---|---|---|---|---|
| `head_to_head.archetype.hs_bat` | spearman | 168 | -0.02234 | 0.0529 (0.42x) | 0.0373 (0.60x) | NULL, CLOSED |
| `head_to_head.archetype.hs_arm` | spearman | 144 | -0.01804 | 0.0958 (0.19x) | 0.0685 (0.26x) | NULL, CLOSED |
| `head_to_head.archetype.college_arm` | spearman | 244 | -0.01184 | 0.0686 (0.17x) | 0.0607 (0.20x) | NULL, CLOSED |

**Four of the five never-floored cells are NULLs. One is not.** `college_arm`
`auc_contributor` clears its own floor under both estimators, at 1.14x (E1) and 1.20x
(E2). It does **NOT** survive the multiplicity adjustment registered in 0B.6: the
Bonferroni floor at k = 5 is 0.0681 (E1) and 0.0648 (E2), and the margin is 0.0548. It
therefore **resolves only unadjusted**, in those words, and that is how it must be
quoted.

### 5B.2 Reproduction, before any floor

| cell | published | replica | gap |
|---|---|---|---|
| `curve_area` | eFV 0.8148 / cons 0.8229, n 3,678 | eFV 0.81480 / cons 0.82294, n 3,677 | margin -4.2e-05 |
| `pit.era.<=2018` auc | 0.7740 / 0.7841, n 132 | 0.77400 / 0.78405, n 132 | exact |
| `hs_bat` auc | 0.7705 / 0.7744, n 168 | 0.77248 / 0.77441, n 168 | eFV +0.0020 |
| `hs_arm` auc | 0.6903 / 0.7149, n 144 | 0.69334 / 0.71489, n 144 | eFV +0.0030 |
| `college_arm` auc | 0.6514 / 0.7078, n 244 | 0.65297 / 0.70781, n 244 | eFV +0.0016 |

Two reproduction notes, both real and both worth someone's time:

1. The replica pool is 3,677 against a published 3,678, one row, on identical areas to
   4 dp. The matrix on disk has moved since the scoreboard was stamped.
2. Every archetype consensus leg is EXACT and every eFV leg is 0.0016 to 0.0030 HIGH.
   The cause is `source_backtest.py:588`: eFV's raw OOS score is remapped onto the
   consensus FV scale and **rounded to 0.1 FV** so it can be tier-binned for display.
   Spearman survives a monotone remap; a tie-corrected AUC does not survive the ROUNDING,
   because rounding manufactures ties and ties cost AUC. The published archetype AUCs
   understate eFV by roughly 0.002 to 0.003 for a display reason. That is small next to
   every floor here and changes no verdict, but it is a measurement being degraded by a
   presentation step.

### 5B.3 The coverage gate (0B.5), two-sided

`waveb.coverage_gate`, S = 100 synthetic datasets, 40 checked, B = 200, n = 900.

- truth -0.00159, true sampling sd 0.00441, mean bootstrap sd 0.00494
- `sd_ratio_boot_over_true` **1.119** (registered maximum 1.60): PASS the over-width guard
- `coverage_95` **0.95** (registered minimum 0.90): PASS the under-coverage guard

Both directions pass, so the `curve_area` floors are quotable as measured and the NULL at
5B.1 is not a NULL bought with an over-wide floor.

### 5B.4 Q4: the `curve_area` floor

`waveb.q4_capture_curve_area`. Point margin -0.00814 on n = 3,677.

| estimator | sd | MDE95 one-sided | \|margin\|/floor | CI95 | p(delta > 0) | Bonferroni k5 |
|---|---|---|---|---|---|---|
| E1 refit-inclusive | 0.00811 | **0.0133** | 0.61x | [-0.03096, +0.00039] | 0.031 | 0.0189 |
| E2 fits-held-fixed | 0.00509 | **0.0084** | 0.97x | [-0.01719, +0.00265] | 0.081 | 0.0118 |

**Both estimators return NULL, so there is no CONTESTED branch to report.** They agree on
the verdict and disagree on the width by a factor of 1.59, which is inside the 1.6-1.8x
that `tools/efv_mde_lab.py:11-14` predicted for a test-only bootstrap.

**A tension this lane will not paper over.** E2 misses by 3 percent of its own floor
(0.97x), and E1's percentile interval only just contains zero at +0.00039 with a
`p_gt_0` of 0.031. Read as a percentile test, E1 would call this significant. Read
against the registered criterion, |point| >= 1.645 \* sd, it is not. The two disagree
because the E1 bootstrap distribution is centred at -0.01369 while the point is
-0.00814, a bootstrap bias of -0.00555; a naive percentile interval inherits that shift,
and a bias correction would move it back UP, further from significance, not closer. The
registered criterion governs, and it was registered before the number existed.

**So `curve_area` is a NULL. It is also the closest thing to a resolvable cell anywhere
on the weak-cell list, and it should not be filed next to a 0.07x cell.**

### 5B.5 Q4 controls: what the -0.00814 is actually made of

All six ran. `waveb.q4_controls`.

**K1 permutation null: PASS.** The eFV board shuffled 400 times gives a mean area of
0.50040 against the derived no-information value (n+1)/2n = 0.50014, a gap of 0.00026.
The consensus board shuffles to 0.50404. The statistic collapses to no-information under
permutation, so it is measuring ordering and not an artifact of its own construction.

**K2 exact rank identity: PASS at machine zero.** area = (n+1)/n - sum_i war_i \* rank_i /
(n \* total). Maximum absolute error 0.0. Everything in K6 is licensed by this.

The identity is worth stating plainly because it changes what `curve_area` IS:
**`curve_area` is a WAR-weighted mean rank.** It is not a curve statistic that needs a
curve; it is one linear functional of the ranks, weighted by realized WAR. That is
exactly why it is the value-weighted instrument, and it is also why it is fragile: a
handful of high-WAR players carry it.

**K3 tie resolution: the published consensus number contains a zero-information credit.**
The consensus board has 230 distinct values over 3,677 rows, its largest tie block is
462 rows, and **3,636 of 3,677 rows sit inside a tie block.** `source_backtest.py:673`
sorts with a stable sort, so inside a tie block the input order decides who is ranked
first, and that input order is side then cohort year. Under 400 random within-tie
orderings the consensus area is 0.82186 (sd 0.000198, max 0.82249); as published it is
0.82294, which is **5.48 sd above the random mean and above the maximum of 400 draws.**
The eFV board, with 2,912 distinct values, gets a tie credit of 0.00002, i.e. none.

At equal resolution the margin is -0.00708 instead of -0.00814. **13.3% of the published
loss is the arbitrary order inside consensus tie blocks**, and it is arbitrary in a
direction that is not accidental: older cohorts sort first and older cohorts have had
more years to accumulate career WAR.

**K4 cross-side pooling: the loss survives within side, so it is not a side-mixing
artifact.** hit -0.00329 on n = 1,792, pit -0.01409 on n = 1,885, pooled -0.00814. This
control was run because eFV enters the pooled board on a WAR scale and consensus on raw
FV, which is not cross-side comparable, and the answer is that the confound is not the
explanation. It does relocate the loss: it is four times larger on the pitching side.

**K5 outcome definition: this is the largest single explanation, and it is definitional.**
`source_backtest.py:641-652` gives a row the universe's FULL CAREER WAR when the player
is in the universe and the matrix's first-six-season label otherwise. The split is 1,645
career-WAR rows and 2,032 label rows, and **the 2,032 label rows carry a total WAR of
exactly 0.0 under either definition.** So the published capture curve is scored, in
substance, on CAREER WAR, with 2,032 zero-value rows acting as rank ballast.

That is not the quantity eFV is fit to. eFV and its consensus OLS anchor are both fit to
`target_censored`, the first-six-season label. On the 1,645 rows that carry all of the
WAR:

| outcome variable | margin |
|---|---|
| career WAR (as published) | **-0.00883** |
| first-six-season label (the model's own target) | **-0.00090** |
| first-six-season label, full 3,677-row pool | **+0.00203** |

The correlation between the two outcome variables on those rows is 0.8896 and the means
are 3.251 against 2.848. **Changing the outcome variable, and nothing else, removes 90%
of the loss on the rows that carry the value, and flips the sign on the full pool.**

**K6 top reordering: the brief's hypothesis is REFUTED.** The registered test was whether
the loss is concentrated in the top deciles AND whether a consensus-top hybrid closes
most of it. Neither holds.

Attribution by consensus-rank decile (sums to -0.00814, which is the margin):

| consensus decile | n | share of pool WAR | contribution to margin | mean rank move, eFV minus consensus |
|---|---|---|---|---|
| 1 | 368 | 0.525 | -0.00490 | +54 |
| 2 | 368 | 0.191 | +0.00080 | +40 |
| 3 | 368 | 0.094 | **-0.01229** | +381 |
| 4 | 367 | 0.030 | -0.00090 | +300 |
| 5 | 368 | 0.051 | -0.00136 | +70 |
| 6 | 368 | 0.045 | +0.00069 | -109 |
| 7 | 367 | 0.019 | +0.00301 | -86 |
| 8 | 368 | 0.029 | +0.00413 | -134 |
| 9 | 368 | 0.009 | +0.00104 | -26 |
| 10 | 367 | 0.008 | +0.00165 | -492 |

The top two deciles carry 50.4% of the margin, but the single largest contributor is
**decile 3 at -0.01229, which is 151% of the entire margin on its own**, and deciles 6
through 10 hand +0.01052 back. The hybrid boards say the same thing more directly:

| hybrid | margin vs consensus |
|---|---|
| consensus order for the top 5%, eFV below | -0.00743 |
| consensus order for the top 10%, eFV below | -0.00744 |
| consensus order for the top 20%, eFV below | -0.00625 |
| consensus order for the top 50%, eFV below | **+0.00091** |
| eFV order for the top 5%, consensus below | +0.00123 |
| eFV order for the top 10%, consensus below | +0.00167 |
| eFV order for the top 20%, consensus below | +0.00060 |
| eFV order for the top 50%, consensus below | -0.00080 |

Handing consensus the top 20% and letting eFV order everything below still leaves 77% of
the loss. Handing eFV the top 20% and letting consensus order everything below is a
small eFV WIN. **eFV's ordering of the top of the board is not the problem; it is
marginally better than consensus's.** The loss lives between roughly the 20th and 50th
percentile of the consensus board, where eFV demotes decile-3 players by an average of
381 places and some of them turn out to be worth a lot.

**And it is ten players.** The ten single worst rows for eFV account for **136%** of the
whole margin. The worst is a player consensus ranked 824th and eFV ranked 2,599th who
went on to 19.11 career WAR, costing 0.00161 by himself, one fifth of the published
margin. A statistic that ten rows out of 3,677 can move by more than its own value is a
statistic whose 0.0133 floor is not surprising.

### 5B.6 Q5 cells

`waveb.q5a_pit_era_auc`: replica exact at 0.7740 / 0.7841 on n = 132, margin -0.01005,
E1 floor 0.0873 (8.7x the margin), E2 floor 0.0546. **NULL, CLOSED**, and not close.

`waveb.q5b_archetype_cells`: a real cluster paired bootstrap on 1,005 archetype rows
(one row per player, latest pre-debut all-source common read), resampling the eFV matrix
pool and refitting the forward chain on every draw. This is the first bootstrap these
cells have ever had.

`college_arm` `auc_contributor` is the exception on the list: margin -0.05484 against an
E1 floor of 0.0481 and an E2 floor of 0.0458. It resolves under both, at 1.14x and 1.20x.

**The control that could have killed it, and did not.** One cell out of eight clearing
its floor is what selection looks like, so an UNREGISTERED control was added after the
run (disclosed as unregistered here and in the artifact): draw random 244-row subsets
without replacement from all 1,005 archetype rows on the same fixed fits, and ask how
often a random cell of that size is at least that negative. The whole-pool AUC delta is
-0.00030, random 244-row subsets average -0.00016 with sd 0.01625, and **0.05% of 4,000
random subsets are at least as negative as -0.05484**. The same control puts `hs_arm` at
17.6% and `hs_bat` at 47.1%, which is what a nothing cell looks like. So `college_arm`
is not an artefact of cell size or of testing eight cells.

It still does not survive the registered Bonferroni floor. Reported as: **resolves only
unadjusted.** It is the first thing on the weak-cell list with a claim on the experiment
queue, and it is a college-pitcher discrimination problem, not a value-capture problem.

### 5B.7 Correction: wave 1's sqrt(n) bound was not a lower bound

`waveb.wave1_sqrt_bound_check`. Wave 1 closed the three archetype SPEARMAN cells with
`sqrt(n_pool / n_cell)` applied to a different instrument's floor, and Part 0.2 item 2
of this document claims that number is a LOWER BOUND on the true cell floor because it
ignores refit and composition variance. Q5b measured those same floors, so the claim is
now checkable:

| cell | wave 1 claimed lower bound | measured E1 floor | bound / measured |
|---|---|---|---|
| `hs_bat` spearman | 0.1539 | 0.0529 | **2.91x** |
| `hs_arm` spearman | 0.1662 | 0.0958 | **1.73x** |
| `college_arm` spearman | 0.1277 | 0.0686 | **1.86x** |

**It is not a lower bound. It OVERSTATES the measured floor by 1.7x to 2.9x**, and by
rule F that is the permissive direction for a NULL: it closes cells more easily than a
real floor does. The three verdicts happen to survive, because all three margins are
below the measured floors too. The METHOD does not survive and must not be reused. The
likely cause is that the base floor (0.0352 at n = 3,210, `data/xfv_headtohead_gap.json`)
was measured on 3,210 ROWS belonging to only 1,563 players, so it already carried the
repeat-measurement inflation that `sqrt(n)` then scaled up again, while these cells are
one row per player.

Every row of `i5_archetype_bounds` in the artifact now carries
`"floor_kind": "LOWER BOUND (NO bootstrap was run for this cell in wave 1)"` and a
`superseded_by` pointer, per the brief.

---

## PART 4B. WHERE THE `curve_area` RESULT GOES, AND IN WHAT WORDS

Registered at 0B.8 to be written whichever way the number fell. It fell NULL, so the
"resolvable loss" branch does not fire, and this lane does **not** get to say consensus
beats eFV on value capture. What it does get to say is bounded, and all four of these
are supported by `data/xfv_cohort_floors.json`:

1. **`curve_area` is a NULL at 0.61x its floor (E1).** It joins the closed list, but it
   is the only cell on that list within a factor of 1.7 of resolving, and the only one
   where a modest increase in pool size would change the answer. It should be recorded
   as CLOSED AT CURRENT n, not as CLOSED.
2. **The published -0.0081 overstates whatever is there.** 13.3% of it is a
   zero-information tie credit inside the consensus board (K3), and swapping the outcome
   variable to the model's own target removes 90% of the rest on the rows that carry the
   WAR (K5). What survives both is a small negative number well inside the floor.
3. **The instrument has two defects that are worth fixing regardless of the verdict**,
   because the site quotes this curve. They are listed as `edits_requested` for the
   owner of `source_backtest.py`, which this lane does not own: the stable-sort tie
   order, and the outcome variable.
4. **The brief's directional hypothesis is refuted and should not be repeated.** eFV
   does not lose value capture by re-ordering the top of the board. Its top-20% ordering
   beats consensus's. The loss sits at consensus ranks 700 to 1,800 and is carried by
   about ten players.

**Wording, if any of this reaches a page.** Not "eFV loses the value-capture
instrument". The supported sentence is: *"On the 3,677-player capture pool the two
boards are within the measurement floor of each other on value capture (margin -0.008
against a floor of 0.013); eFV's published rank win and its published capture loss are
both smaller than what this pool can measure."*

---

## PART 6B. CORRECTIONS TO WAVE 1, AND THE WAVE-2 LEDGER

Two corrections to Parts 1-6 above. Neither is re-litigated, both are recorded.

- **Part 6 row I5-a said "eleven weak cells ... ALL NULL, ALL CLOSED".** `weak_cells`
  has SIXTEEN rows. Eleven were measured, five were not, and one of the five is not a
  null. The row should read: eleven of sixteen, and see 5B.1 for the rest.
- **Part 0.2 item 2's "LOWER BOUND" claim is empirically false**, see 5B.7.

**BLOCKED AND NOT RE-PROPOSABLE.** The wave-1 draft sentence for
`tools/efv_scoreboard.py` `weak_cells_note`, asserting that every cell was given its own
paired-bootstrap floor, that all of them are nulls, that no cell can be adjudicated at
current n, and that no per-cohort fix may be proposed from the list, is wrong on all four
clauses as of this run. Five cells had no floor when it was drafted; one of the five
adjudicates; and the fix it would have foreclosed (`college_arm` discrimination) is the
one live item the weak-cell list has produced.

| id | claim | verdict | evidence |
|---|---|---|---|
| B-1 | `capture.curve_area` -0.0081 is resolvable | **FALSE, NULL** | 0.61x the E1 floor 0.0133; both estimators agree; `waveb.q4_capture_curve_area` |
| B-2 | the capture bootstrap covers nominally in both directions | **PASS** | coverage 0.95, sd ratio 1.119 against a registered band of 0.90 / 1.60 |
| B-3 | `curve_area` collapses to no-information under permutation | **CONFIRMED** | 0.50040 against (n+1)/2n = 0.50014, R = 400 |
| B-4 | part of the margin is a consensus tie-order credit | **NEW, CONFIRMED** | 3,636 of 3,677 rows in a tie block; +0.00108, z = 5.48; margin -0.00814 to -0.00708 |
| B-5 | the margin is an outcome-definition artifact | **NEW, CONFIRMED IN LARGE PART** | career WAR -0.00883 vs the model's own target -0.00090 on the same 1,645 value-carrying rows |
| B-6 | eFV loses value capture by re-ordering the TOP of the board | **REFUTED** | eFV-top-20% hybrid is +0.00060; consensus-top-20% hybrid still -0.00625 |
| B-7 | the loss is a cross-side pooling artifact | **FALSE** | survives within side: hit -0.00329, pit -0.01409 |
| B-8 | `pit.era.<=2018` auc is resolvable | **FALSE, NULL** | 0.12x the E1 floor 0.0873 |
| B-9 | `hs_bat` and `hs_arm` auc are resolvable | **FALSE, NULL** | 0.07x and 0.35x their E1 floors |
| B-10 | `college_arm` auc_contributor is resolvable | **CONFIRMED, UNADJUSTED ONLY** | 1.14x E1 / 1.20x E2; fails Bonferroni k5 (0.0681); 0.05% of random 244-row cells are this negative |
| B-11 | wave 1's sqrt(n) archetype number is a LOWER BOUND on the cell floor | **FALSE** | 1.73x to 2.91x ABOVE the measured floors; permissive direction for a NULL |
| B-12 | the published archetype eFV AUCs are degraded by a display rounding step | **NEW, CONFIRMED** | replica eFV legs +0.0016 to +0.0030 with the same consensus legs; `source_backtest.py:588` rounds the remapped grade to 0.1 FV |
