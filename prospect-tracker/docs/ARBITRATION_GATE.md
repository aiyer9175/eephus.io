# Arbitration model gate (pre-registered 2026-08-08)

Covers the `/arbitration/` program: a per-player arbitration award model (GATE A),
a fitted population arbitration ladder (GATE B), the surplus-engine consumers
(GATE C) and the free-agent-market increment (GATE D).

Written and committed BEFORE the adjudicating battery is read, in the shape of
`docs/SC_PLUS_RECALIBRATION_GATE.md`. Producers: `arb_dataset.py`,
`tools/arb_mde_lab.py`, `arb_model.py`. Artifacts: `data/arb_panel_audit.json`,
`data/arb_mde_floor.json`, `data/arbitration_eval.json`.

Where this document and a later measurement disagree, **the measurement is what
this gate uses**, and the disagreement is recorded rather than edited away.

---

## 0. What is being fixed, measured first

Every number in this section was measured before any model was written.

| claim | plan said | measured | verdict |
|---|---|---|---|
| Spotrac status cells stored as $0 salary | suspected | 700 of 1,405 rows (49.8%), $478.7M absolute AAV error | CONFIRMED, fixed 2026-08-08 |
| the incumbent arbitration ladder | `[0.40, 0.60, 0.80]` | production default is `clemens_2026`: `[0.15, 0.35, 0.50, 0.75]`, `control_years` 7, `arb_basis` prior_season | **PLAN WAS WRONG** |
| surplus backtest can adjudicate a ladder | assumed yes | `surplus_backtest_real._impute_seasons:216-231` computes the REALIZED salary from the same constant | **CANNOT**, see B4 |
| incumbent ladder on WAR <= 0 seasons | not considered | `value_framework.py:488-489` returns $0 | free win, A7 demoted |
| naive pool max-cut violations | not measured | 11.52% | CONFIRMED contaminated |
| panel after contamination removal | - | 25,892 rows, 8,154 labelled, 5,201 clean, max-cut 7.02% | **G3 FAILS** |
| war_daily 2020 salary basis | unknown | UNPRORATED (2019->2020 median ratio 1.311), i.e. the award | usable as a label basis |
| MLBTR entries carrying K not MM | not considered | 20 of 191 on the 2026 tracker | a MM-only regex drops the arb-1 population |
| MLBTR tracker contains non-arbitration rows | not considered | 1 extension, 3 club options, 4 split deals, 16 unresolved | must be classified out |

### 0a. GATE 0.1 - the blast-radius bound, run before any model was fit

`tools/arb_ladder_blast_lab.py` -> `data/arb_blast_bound.json`. It prices the
board grid under the two EXTREMES of the admissible ladder range
(`[0.10,0.20,0.35,0.50]` against `[0.55,0.75,0.90,0.95]`), both deliberately
beyond anything a fit could return, to bound the effect rather than guess it.

| quantity | extreme low vs extreme high | the two SHIPPING ladders |
|---|---|---|
| mean absolute move | $17.3M | $7.6M |
| median absolute move | $11.5M | $5.1M |
| max absolute move | $55.0M | $24.4M |
| mean relative move | 27.5% | 13.6% |
| **Spearman, before vs after** | **1.0000** | **1.0000** |

**GATE B is NOT closed on economic grounds.** This is the opposite of the
`PITCHER_LABEL_LEDGER` precedent, where the maximum possible perturbation moved
the board less than a rounding change. Here the admissible range is worth up to
$55M on a single top-FV cell and 27.5% in relative terms. The money is real and
the ladder is worth fitting.

**But the ladder is a pure LEVEL effect and never reorders anything.** Spearman
is exactly 1.0000 across the entire admissible range. Two consequences, both
binding:

1. **The C4 criterion (`Spearman >= 0.97`) is trivially satisfied and therefore
   cannot discriminate.** It is retained as a regression guard - a swap that DID
   reorder the board would mean something broke - but it is not evidence for the
   swap and must not be cited as such.
2. **Any claim about the fitted ladder must be denominated in DOLLARS, not in
   ordering.** The trade board's ranking is untouched by construction, so
   "improves the board" is only ever a pricing claim here.

**Scope, measured on the same grid: the ladder does not move FV 35 or FV 40 at
all** ($0.90M and $2.00M identical under all four ladders). Sub-45 prospects
never reach arbitration on the model's expected path - they bust first - so the
ladder never binds on them. The prospect board is about 98% sub-50 FV, so the
ladder's effect is concentrated in roughly the top 2% of that board plus the 356
unpriceable MLB veterans. Small population, large per-row dollars.

**The plan's headline incumbent was wrong and the correction matters.** GATE B is
scored against the ladder that actually ships (`clemens_2026`, four steps, prior
season basis, seven control years) AND against the base-identity
`prospx_current` three-step ladder. Both are reported. A ladder fitted on one
basis is not comparable to the other, so the basis is registered here, before
fitting: **the fit is on `arb_basis: prior_season`, matching production.**

---

## 1. The estimand

> For a player-season in which the player is under team control, is
> arbitration-eligible under the CBA in force, **is tendered a contract**, and
> receives a **one-year salary settled or awarded through the arbitration
> process** (so is *not* covered by a previously signed multi-year contract),
> this model estimates the **conditional expectation** of that salary, in dollars
> deflated by an index refit inside every fold, **given only information
> observable as of the tender deadline**.
>
> It does NOT estimate: the salary a non-tendered player would have received
> (absent by construction, concentrated at the bottom); the salary of a player
> who signed an extension covering that season (absent, concentrated at the top);
> the **unconditional** payroll obligation, which is a separately labelled
> deliverable and **may never be obtained by summing predictions of this
> quantity**; or what a player "should" be paid.
>
> Projections past 2026 additionally assume the 2022 CBA's arbitration structure
> survives its 2026-12-01 expiry unchanged. That is an assumption about rules
> that do not yet exist. It is not estimated from data and is not covered by any
> published interval.

---

## 2. Label-quality gates. The model does not ship if these fail.

These run on the panel, before any model exists.

- **G1 salary agreement.** war_daily `salary` vs the MLBTR settled figure on the
  overlap: **>= 90% agree within 1%**. Below that the two sources measure
  different quantities (war_daily is a payroll figure and includes amortized
  bonuses, split contracts and renewals; MLBTR is a settlement), and the artifact
  must name one as the label and demote the other to a covariate rather than
  averaging them.
- **G2 arb-step agreement.** Reconstructed step vs the step implied by MLBTR's
  printed service time: **>= 95%**, with the **confusion matrix published**, not
  a pooled rate. A pooled rate hides the two cells that matter, the
  pre-arb/Super-Two boundary and the arb3/arb4 boundary.
- **G3 maximum-cut meter.** A real award cannot cut more than 20%. Retained clean
  rows with `salary_t / salary_t-1 < 0.80` must be **< 1.0%**. Naive baseline
  11.52%; first reading after contamination removal **7.02%, FAILING**. If it
  does not clear, the reconstruction is wrong, not the model.
- **G4 identity census.** `fa_ident.resolve_with_reason` only, **no fallback for
  `IDENTITY_AMBIGUOUS`**. Any season below 90% RESOLVED is reported and not
  scored. The drop rate must be non-differential across side, position and debut
  age, because unresolved rows concentrate in common Hispanic surnames and
  suffixed names, which correlates with signing pathway and therefore with
  arb-step timing.
- **G5 coverage.** Any season below **70% label coverage** of the
  arbitration-eligible population is **reported and NOT scored**. Measured
  coverage among regulars is 80-90% (2015-2019), 49-63% (2020-2022), 80-84%
  (2023), 96% (2024), 53% (2025-2026), and 2011-2014 is unmeasured. Missingness
  is **not at random**: it concentrates on the arb-1 population, where
  identifiable arb-1 jumps number 57-80/yr in good years and **3 in 2021, 3 in
  2022, 3 in 2026**.
- **2020 is never a label year.** The paid figure is 60/162 = 37.04% of contract
  and the three sources disagree on basis. It may be a prior-salary feature only
  after conversion to a full-season equivalent, and that conversion must
  reproduce the multi-year-implied 2020 figure within 1% on >= 95% of players
  under deals spanning 2019-2021.
- **Super Two cutoffs are `curated-unverified`** (`arb_service.SUPER_TWO_VERIFIED
  = False`). Until the ledger confirms them against MLBTR's published table, a
  `super_two = True` call is a diagnostic, not a label.

---

## 3. Power, measured before anything is adjudicated

`tools/arb_mde_lab.py` -> `data/arb_mde_floor.json`. **No criterion below may be
read before this artifact exists.**

Protocol, matching `docs/EFV_GATE_STANDARD.md`:
- Paired bootstrap resampling **train AND test** with a refit on every draw. A
  test-only bootstrap understates sd by 1.6-1.8x.
- **Clustered on PLAYER, not row.** A player supplies arb1, arb2 and arb3 rows
  and his path is strongly autocorrelated; a row-level bootstrap would treat
  ~2,500 correlated rows as ~2,500 independent draws.
- Forward-chained by arbitration class year, **>= 4 independent splits**.
- The deflator is **refit inside every fold on train years only**.
- One floor per statistic class. Floors are basis-specific and are not
  transferable between them: **arb1**, **arb2+**, **vs recalibrated Swartz**,
  **ladder discounted-total**.
- `MDE95` is **one-sided (1.645 sd)**, stated explicitly because the convention
  was implicit in this repo once already and had to be recovered.
- **Two-sided coverage check on the floor estimator itself**, n_check >= 200.
  For a program whose product is null verdicts, over-wide is the PERMISSIVE
  direction: it manufactures nulls.
- **Detection check**: a design-matched simulation with a planted effect at the
  size being claimed. If the harness cannot see it, a null is a dead instrument,
  not a finding.

**Headline metric: MSE in deflated dollars**, player-clustered. It is a proper
scoring rule for the conditional MEAN, and the consumer (surplus) is linear in
salary and needs an expectation. This repo has already shipped one calibration
that was optimal on its own metric and wrong for its consumer.

**Guardrail:** dollar MSE is owned by the largest awards, so the champion must
also not lose to B1 on median absolute percentage error by more than 10%
relative.

**Served point estimate: the smearing-corrected conditional mean, never
`exp(mu_hat)`.** At a residual log-sd of 0.30 the correction is 1.046 - a 4.6%
systematic understatement of every award, which becomes a 4.6% OVERSTATEMENT of
surplus, roughly $1.2M of phantom surplus per player across three discounted
seasons, in the same direction for everyone. The smearing factor is published.

---

## 4. GATE A - the per-player model

Baselines, all three, on identical rows:
- **B0** prior salary carried forward, deflated. **A strawman**: carry-forward is
  biased low by exactly the mean raise and the max-cut rule floors the label, so
  an intercept beats it. Reported, never the headline.
- **B1** `s_t = m_k * s_t-1`, with `m_k` the median step multiplier for arb-step
  *k* fit **out-of-fold on train years only**, deflated, floored at both
  `0.80 * s_t-1` and the year's league minimum. **This is the baseline the
  champion must beat.**
- **B2** B1 plus one standardized prior-WAR term.

Criteria:
- **A1** champion beats **B1** on MSE in deflated dollars, reported **separately
  for arb1 and arb2+**, each against its own floor, player-clustered.
- **A2** champion beats **B2** by more than the arb2+ floor. If A1 passes and A2
  fails, the entire content of the model is one lagged variable and one WAR term,
  **and the artifact says so in those words**.
- **A3 zero-information control.** Refit with the **production block permuted
  across players within (season x arb-step) cells**, keeping prior salary,
  arb-step and season intact. A whole-matrix permutation is **NOT admissible**: it
  destroys the prior-salary link too and has no dynamic range, which is exactly
  why a previously registered control in this repo was recorded UNINFORMATIVE.
  Criterion: the real block beats the permuted on **>= 5 of 7** scored seasons,
  and the permuted twin's mean gain sits inside its own null band around zero.
- **A4 permutation null**, B >= 500, same cells, marginals preserved.
- **A5 deflator leak twin.** Report `delta = MSE(panel-wide deflator) -
  MSE(fold-refit deflator)`. **If `|delta| >= the A1 margin, A1 is a NULL.**
- **A6 Swartz, restated precisely.** The champion must beat **recalibrated
  Swartz** (a per-fold affine `a + b*swartz` fit on train years only), on a
  feature vector cut **as-of the Swartz publication date**, verified by an
  explicit assertion rather than a docstring claim. Beating a raw published
  pre-settlement projection on settled figures is a different and easier claim.
  **Single-season Swartz comparisons are pre-committed NULL** (n ~ 160 per winter
  gives a floor near $0.33M).
- **A7** the incumbent ladder comparison is a **diagnostic, not a ship
  criterion**, reported on WAR > 0 rows only, with WAR <= 0 rows shown separately
  beside the sentence that the incumbent structurally predicts $0 there.
- **A8 calibration**: signed bias by **PREDICTED**-salary decile within 5% of the
  decile mean.
- **A9 estimand honesty**: publish both the tender-conditional and unconditional
  forms, and `P(tender)` by predicted-salary decile. If the top-to-bottom decile
  tender ratio exceeds 1.15 the two estimands differ materially and **aggregate
  payroll may only be computed from the unconditional form**.
- **A10 reproducibility**: every served row carries `{label_set_hash, coef_hash,
  fold_config, deflator_vintage}`, and a **per-player explainer array with an
  exact remainder** so `sum(factors) + other + base` reconstructs the served
  figure.

**Banned from the champion**, diagnostics only: hearing occurrence, filed
figures, settlement date (post-treatment); team fixed effects (correlated with
quality, post-treatment for mid-season trades); counting stats. Enforced
mechanically - the champion feature list is a frozen tuple, the ceiling model
writes to a different artifact path, and the serve path raises on any key outside
`projectable_keys`.

---

## 5. GATE B - the fitted ladder

**Target is observed arbitration dollars. NEVER `surplus_backtest_real`.**

Primary metric: MAE of the **discounted arbitration-window salary total per
player**, deflated. The ladder is consumed inside a discounted sum, so a ladder
that is wrong per-year but right in total is fine for surplus and the reverse is
not.

- **B1** beats the incumbent by more than the measured floor, forward-chained
  over >= 4 splits, scored against **both** `clemens_2026` (production) and
  `prospx_current` (base identity). Both reported.
- **B2 one-parameter twin.** The best single **global scalar rescale** of the
  incumbent, fit out-of-fold on the same loss. **If a one-parameter rescale
  captures >= 75% of the fitted ladder's gain, the finding is a LEVEL correction
  and ships as one parameter, not as a fitted shape.**
- **B3 rank-identical twin.** A monotone ladder with the same ordering and
  different spacing. The specific numbers must beat it, or the finding is "the
  ladder should be monotone", which it already is by construction
  (`value_framework._arb_ladder:1179` clamps to keep it so).
- **B4 non-diagnostic proof.** 20 random monotone ladders scored on
  `surplus_backtest_real`. **Expected outcome: they move its MAE comparably to
  the fitted one**, confirming that artifact cannot adjudicate ladder questions,
  because `_impute_seasons` builds the realized side from the same constant.
- **B5 basis registered above**: `prior_season`, matching production.
- **B6 atomicity.** One commit: the config, `data/value_framework.json`,
  `data/value_framework.js`, `assets/glossary.js` (which hardcodes the ladder in
  JS), `test_valuation_sets.py`, `test_salary_discount.py`, `backtest.py`'s
  synthetic DGP, `surplus_backtest_real`'s realized side, `qo_tax_usd`, and a
  regenerated artifact. The `_arb_ladder` monotonicity invariant must still hold,
  verified rather than asserted.
- **B7** the calibration refit is part of the ship, and **`prospect_surplus`
  moves validated -> provisional at the moment of the swap.**

**The cancellation trap.** Both sides of the surplus backtest carry the ladder,
so it largely CANCELS in the residual. After a both-sides swap, the change in
bias must be substantially smaller than the change in prediction level:
**`|delta bias| < 0.4 * |delta level|`. If they are comparable, only one side was
swapped and there is a bug.** Note also that the calibration refit was already
run once and **LOST on held-out MAE on 3 of 3 folds (11.518 shipped vs 13.581
refit)**, because 86-90% of bottom bins realize nothing and MAE is minimized by
the median. After the swap the choice is between an invalid map and a
measured-worse one, and the resolution is an EV-consistent loss, which is a
separate and larger program.

---

## 6. GATE C - the surplus-engine consumer

Scope split by population, because the consuming populations are not the same:
- **MLB players with an observed prior salary and a resolved arb step**: the
  per-player path. This is the 356-unpriceable-veteran population, and it is
  where the model is in-sample.
- **Never-debuted prospects**: **keep the ladder**. Their arb seasons are 4-7
  years out, they have no prior salary, the arb2+ raise model cannot run at all,
  and extrapolating a model fit on observed awards onto them is the shape of a
  prior failure in this repo. **For that population Lane C reduces to GATE B.**

- **C1** per-player beats the fitted ladder and the incumbent on the eligible
  population by more than its floor.
- **C2** realized-surplus MAE on `surplus_backtest_real`'s resolved cohorts does
  **not degrade** after swap plus refit. Deliberately not "improves": surplus MAE
  is dominated by WAR error and pre-registering an improvement there would be
  pre-registering a null.
- **C3** blast radius `M <= 1.25 * E_const`, where `E_const` is the measured
  per-player error of the incumbent constant against observed salaries. Excess is
  the new model's extrapolation, not the constant's error.
- **C4** `Spearman(pre, post) >= 0.97` on the served board. The swap should be
  predominantly a LEVEL move; heavy reordering means the ladder became a new
  metric rather than a repair.
- **C5** served per-player paths are non-decreasing except where the max-cut
  binds; violation count must be **0**, verified in code.
- **C6** clamped-row count on the prospect board must be **0** (a nonzero count
  is proof of out-of-population use).

---

## 7. GATE D - the free-agent increment

Run as a **pre-registered null**, one feature, on the existing harness
(`tools/fa_market_feature_lab.py` toggles one `fa_market.X_FEATURES` flag and
re-runs the unchanged forward-chained Gate-2 folds; `fa_market._x_noise_feats`
is already a zero-information placebo). `persist_dpw=False` on every lab run, or
the lab rewrites the $/WAR level the whole valuation engine prices against.

**The raw correlation is not evidence.** Arbitration salary and free-agent price
are both monotone functions of the same production, which `fa_market` already
reads through its projected-WAR and rational-anchor terms.

Registered feature: **`arb_residual_final`** only - our own out-of-fold arb
residual, which is by construction orthogonal to the arb model's own features.
Mechanism: a player the arbitration panel overpaid relative to WAR is typically a
counting-stat player, which is exactly the profile the free-agent market prices
differently. A four-column block on ~200-500 usable rows against a $0.16M floor
is a fishing expedition and is not registered.

Two controls that must run:
- **D1 missingness-indicator-alone arm.** A bare binary "has an arbitration
  history", no salary value. **If it reproduces >= 60% of the lift, the
  arbitration salary contributes nothing and the arm is a NULL.** This is the AUC
  carve-out transplanted: an honest missingness indicator once scored +0.0792
  against a permuted twin at +0.0003 while the real metric went negative, and six
  arms of that program would have read as wins.
- **D2 complete-case arm.** Restrict the gate to rows that HAVE an arbitration
  history and refit the incumbent on the same rows. This is the only comparison
  where the feature is present on both sides.

Floor must be **re-measured on this basis**. The `0.0149` block-rho figure is a
different instrument entirely. The right precedent is the `rate_line` re-gate:
**MDE95 ~ $0.16M on pooled guarantee MAE**, and the currently shipped feature
ships at $0.065M and is documented as indistinguishable from a noise column.

Planning-stage measurement, recorded here so it cannot be quietly upgraded into
the result: on 495 first-time free agents 2018-2026, log walk-year salary against
log first-FA AAV is partial r = +0.423 controlling trailing-3yr WAR, walk-year
WAR, age and QO, incremental R-squared +0.086, permutation p = 0.0000; on the
cleanly arbitration-shaped cell partial r = +0.579, +0.168, n = 170. **That is a
4-variable control, not the incumbent feature set, and it is in-sample. It is a
reason to run the gate, not a result.**

---

## 8. Pre-commitments

An effect below its measured floor is reported as a **NULL**, in that word. Not a
small win, not a directional signal, not a fringe gain.

- **A3 fails:** *"The production block is a NULL over a baseline of prior salary,
  arbitration step and season. A row-permuted twin with identical marginals
  scored within its permutation band of the real block. The awards in this window
  are reproduced by the salary track and the CBA's own step structure, and this
  program measured no information beyond them."*
- **A5 fires:** *"The reported improvement is smaller than the effect of fitting
  the deflator on the rows being scored. The headline is a NULL and the measured
  quantity is deflator leakage, not model skill."*
- **A6 fails:** *"This model does not beat the MLB Trade Rumors / Swartz
  projection. Reported as a NULL. Single-season comparisons are unresolvable at
  n ~ 160 and none is published."*
- **B2 fires:** *"The fitted arbitration ladder is a LEVEL correction, not a
  shape correction. A single global scalar captures P% of the improvement. It
  ships, if it ships, as one parameter. The three-number ladder is NOT supported
  by this measurement."*
- **B4 confirms:** *"`data/surplus_backtest_real.json` is NOT diagnostic for
  arbitration-ladder questions, because `_impute_seasons` computes the realized
  salaries from the same `fractions_of_fa_value` constant the prediction uses.
  Any past or future claim adjudicated on this artifact about the arbitration
  ladder is withdrawn."*
- **G5 fires on the window:** *"The stated 2011-2026 window is not supported. The
  scored window is [list]. The 16-year backtest description is withdrawn."*
- **GATE D below floor:** *"The arbitration block is a NULL on the free-agent
  market gate. Its effect is below the re-measured floor and it is not separable
  from row-permuted placebo columns. The raw correlation is fully accounted for
  by the production both quantities measure, which the incumbent model already
  reads."*
- **Unconditionally, in every artifact:** *"The collective bargaining agreement
  in force through this window expires 2026-12-01. Every projected arbitration
  season from 2027 forward assumes its arbitration structure survives unchanged.
  That assumption is not estimated from data and is not covered by any interval
  published here."*
- **On every over/under surface:** *"A negative residual means this model
  expected a higher salary than the player received. It is a statement about the
  model, not a statement that the player is underpaid. Rows bin on PREDICTED
  salary; binning on actual salary would force this column negative at the top
  and positive at the bottom by regression to the mean regardless of any real
  effect."*

### Cross-gate rules

- **A wins, B loses.** Ship the module. **Do not touch the config.** A per-player
  model accurate on observed arbitration players is not evidence about a
  population constant applied to never-debuted prospects: different estimands,
  different populations, different metrics.
- **A loses, B wins.** **Ship the ladder anyway**, subject to B6/B7. GATE B fits
  three numbers on ~2,500 player-seasons and is far better powered; a null on A
  is not evidence against B.
- **Both lose.** Ship the **label set and the historical descriptive surface**
  (over/under on the observed market, no forward claim), record both nulls, close
  the modelling lane. That is still a complete deliverable.
- **Both win.** They ship as two artifacts with two evidence trails, and neither
  may cite the other's gate.
