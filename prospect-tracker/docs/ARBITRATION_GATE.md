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

### GATE C IS BLOCKED, and the blocker is upstream of the model

**Measured 2026-08-09. Not run, because its population is empty today.**

The arbitration board can price 619 players. The projection board has 356
unpriced veterans. **The overlap is ZERO.** (The board does overlap 514 of the
*priced* vets, so the join itself works.)

Root cause, traced to one player and confirmed: Anthony Volpe was optioned to
the minors on 2026-08-04, and Spotrac lists optioned players in a FOURTH table
(`id="table"`) that `spotrac.scrape_spotrac_team_contracts` never reads - it
parses `dataTable-active`, `dataTable-injured` and `dataTable-dead` only. So the
players with no contract dollars are exactly the players absent from the tables
the contract scraper consumes, and they are absent for the same reason they are
unpriced.

That is why the platform's own diagnostic says `service_time_source: "PROXY -
the pipeline carries no service time"` and reports `unpriceable 356`: the rows
are not merely unpriced, they are **not in the contract set at all**.

**Consequence for this gate.** GATE C cannot be adjudicated on the current
Spotrac cache. Extending the parser to the minors table would change
`scrape_spotrac_team_contracts` output for every consumer by adding
minor-league contract rows, which has its own blast radius and needs its own
gate; it is not a ride-along on this one. A pricing pass was written, measured
at **0 rows priced**, and REVERTED rather than shipped, because a pass that
prices nothing is not a deliverable and leaving it in the tree would suggest
otherwise.

**Registered next step, in order:** (1) widen the Spotrac table set behind its
own byte-diff guard and measure how many of the 356 it recovers; (2) only then
run C1-C6 below.

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

---

## 9. GATE C verification record (registered 2026-08-19, before the lab ran)

### 9a. Census: C1-C6 never ran

Commit `ea9cb564` (2026-08-09) shipped the pricing pass: the Spotrac STATUS
tables were split out (`STATUS_TABLE_IDS`, read for ARB / PRE-ARB tokens only),
the arbitration board grew 641 -> 909 rows, and `_apply_arbitration_paths`
priced **103 of the 356** unpriced veterans, adding ~$0.16B of surplus. Four
invariants were pinned in `test_arb_export.py`. **The C1-C6 battery was never
scored on that population**: no `tools/arb_gate_c.py` exists, no commit after
`ea9cb564` touches `data/arbitration_eval.json` or this document, and the eval
artifact carries no `gate_c` block. Section 6's "registered next step" reached
step (1) and stopped. This section closes the debt.

### 9b. Protocol, frozen before any number was read

Population: served rows with `salSrc == "arb_projection"` in
`data/mlb_projections.json`, counted at scoring time (the artifact regenerates
nightly, so the count can drift from the ship-day 103; both are reported).

- **C1** scores the SERVED per-player configuration - champion arb-1 +
  banded step multiplier arb-2+, chained so each rung's prediction is the next
  rung's prior, exactly `arb_export.build_board`'s estimator selection - against
  the fitted ladder and the `clemens_2026` incumbent, on the GATE B pool
  (players with an observed arbitration window), MAE of the discounted window
  total in nominal dollars, discount 0.07. All fitted estimators (stage 1,
  banded multipliers, deflator, fitted ladder) are fit in-sample on the pool,
  the same convention GATE B used for the fitted ladder; `clemens_2026` is a
  constant. Players where the served chain cannot produce a prediction for
  every window step are dropped from ALL arms (paired comparison) and counted.
  Floor: paired bootstrap clustered on PLAYER, refit every draw, B = 1000,
  one-sided MDE95, seed 20260819. PASS requires the served configuration to
  beat BOTH ladders by more than the floor of each contrast.
- **C2** `surplus_backtest_real.py` reads storage / value_framework / backtest /
  consensus; it never reads `data/mlb_projections.json` and never calls
  `_apply_arbitration_paths`, and `data/surplus_backtest_real.json` predates
  the ship (generated 2026-07-31, last commit `30054667`). No-degrade is
  established by pipeline independence plus the byte-unchanged artifact; the
  resolved-cohort MAE is recorded verbatim as both the pre and post value.
- **C3** M = the served configuration's per-player window MAE from C1;
  `E_const` = `clemens_2026`'s window MAE on the same players. Criterion:
  `M <= 1.25 * E_const`.
- **C4** Spearman(pre, post) of `surTotal` on the served vet board; pre is the
  board with the `arb_projection` rows removed (they carried no surplus before
  the ship), scored on the rows priced in both. `>= 0.97`, expected 1.0 by
  the runs-last invariant; retained as a regression guard.
- **C5** ladder-step violations (`usd < 0.80 * prev`) across the priced rows'
  served paths in `data/arbitration.json`; must be **0**.
- **C6** prospect rows carrying `salSrc == "arb_projection"` (or any arb
  pricing) in `data/mlb_projections.json`; must be **0**.

### 9c. Results

Scored 2026-08-19 (seed 20260819, B = 1000). Verbatim lab output. The panel
regenerates nightly, so the GATE B pool reads 269 players today against 285 on
2026-08-09, and the served population reads 95 rows against the ship-day 103;
both counts are recorded rather than reconciled. 5 of 269 pool players were
dropped because the served chain could not produce every rung (paired
comparison, all arms).

```
pool players with an observed arbitration window: 269
paired players (served chain complete): 264  dropped: 5
fitted ladder (in-sample, GATE B convention): [0.1554, 0.346, 0.5923, 0.5923]
  window MAE served   $   2.215M
  window MAE fitted   $   5.372M
  window MAE clemens  $   4.927M
  gain vs clemens $+2.712M   gain vs fitted $+3.158M
  B (successful draws): clemens 1000  fitted 1000
  MDE95 vs clemens $0.545M -> 4.98x  resolvable=True
  MDE95 vs fitted  $0.900M -> 3.51x  resolvable=True
C1: PASS
C3: M $2.215M vs 1.25*E_const $6.159M  ratio 0.450  PASS
C4: served vets 1337  priced post 1076  arb_projection rows 95  common 981  Spearman(pre, post) = 1.0000  PASS
C5: priced rows 95  ladder steps checked 190  violations 0  PASS
C6: prospects 194  arb-priced prospects 0  PASS
C2: surplus_backtest_real generated_at 2026-07-31  resolved n 2236  mae 10.477094771606316  (pre == post; producer independent of the gate C serve path)  PASS
POPULATION: served arb_projection rows today 95 (ship-day count 103, commit ea9cb564)
```

**All six clauses PASS.** Two reading notes, both anticipated by the
registration: C4's 1.0000 is the runs-last invariant doing its job and is a
regression guard, not evidence for the swap (section 0a's rule applies
unchanged); and C1's margin is the per-player salary anchor doing the work the
WAR-fraction ladders cannot, which is exactly why section 6 keeps the ladder
for never-debuted prospects - the anchor does not exist there. The
`gate_c_verification` block in `data/arbitration_eval.json` carries these
numbers; `test_arb_gatec_verify.py` pins them.

---

## 10. Retained-salary AAV adjudication (2026-08-19)

`spotrac.py` flagged, at the 2026-08-09 ship: "those two AAVs may be wrong
TODAY on the narrow set. The retained-salary semantics were never adjudicated."
Adjudicated here, from the cached pages, `_parse_team_contract_table` output
verbatim:

| player | table | club | per-year (USD) | AAV |
|---|---|---|---|---|
| Nolan Arenado | `dataTable-active` | ARI | 2026: 5,000,000 / 2027: 6,000,000 | **5,500,000 (served)** |
| Nolan Arenado | `dataTable-retained` | STL | 2026: 30,166,668 / 2027: 24,555,555 | 27,361,111 |
| Nick Castellanos | `dataTable-dead` | SD | 2026: 304,492 | **304,492 (served)** |
| Nick Castellanos | `dataTable-retained` | PHI | 2026: 19,695,508 | 19,695,508 |

The rows PARTITION the contract by paying club: Arenado's two rows sum to
$35.17M / $30.56M per year and Castellanos's to $20.0M, each player's actual
contract-year salary. Spotrac's retained table is the RETAINING club's
obligation; the active/dead row is the EMPLOYING (or releasing) club's.

**Verdict: the current read is CORRECT, and the narrow `CONTRACT_TABLE_IDS`
set is the fix, not the bug.** The consumers of `build_contracts_by_key` -
surplus on /projections/ and the trade board - price the obligation of the
club that controls the player. Under MLB rules a retained-salary obligation
stays with the retaining club and does not travel in a subsequent trade, so an
acquiring club assumes only the employing club's schedule: $5.5M AAV for
Arenado is exactly what an acquirer of his contract owes. Folding the STATUS
tables into the contract set (the counterfactual measured at the ship) would
have let the retained rows win the highest-AAV tiebreak and charged an
acquirer $27.36M/yr it would never owe - a $21.9M/yr error in the wrong
direction on a served trade value.

Two recorded caveats, neither a defect in the current serve:
1. `aav_usd` is an EMPLOYING-CLUB OBLIGATION AAV, not the player's income AAV.
   A future consumer wanting the player's market salary level (comps, FA
   anchoring) must not read this field as contract AAV for retained-salary
   players.
2. Castellanos serves off a dead-money row because he is on no active table in
   this cache; the $304,492 is SD's remaining obligation, not an employment
   contract. Harmless to the surplus consumers (the row is not a tradeable
   asset), recorded so nobody "fixes" it into the $19.7M retained row.

The `spotrac.py` OPEN flag is resolved to this section, and
`test_arb_gatec_verify.py` pins the semantics: the retained/status tables
never enter the contract set, and the served rows are the employing-club
rows.

---

## 11. GATE C2 - the control-window salary path (pre-registered 2026-09-16)

Scope: `salary_path.py`, the one module that prices every remaining season a
club controls a player for, and the surfaces that consume it (/projections/
Surplus and the open-row salary path, the MLB player card, the Trade Machine
board and evaluator). Registry row `control_window_salary_path`. Lab
`tools/arb_path_gate.py`, writing the `gate_c2` block of
`data/arbitration_eval.json`, pinned by `test_arb_path_gate.py`.

Sections 1-10 gate the arbitration AWARD model and the 2026-08-09 surplus
consumer that priced 108 no-contract rows. This section gates the COVERAGE
extension of that consumer: 408 more veterans and about 1,408 club-controlled
seasons that price at nothing today. GATE A, B, C and D are not re-opened, and
no clause here supersedes one of theirs.

### 11a. Order of events, stated plainly

**This gate scores a SERVED model, not a candidate.**

The owner asked ask C on 2026-09-16 and, the same day, BEFORE any acceptance
number for this gate existed, ordered the path served in full:
`SALARY_PATH_MODE` defaults to `"full"` rather than `"off"`, and the served
surplus moves in the same commit. Three consequences, written down rather than
left to be discovered later:

1. Every clause below is committed BEFORE the code that scores against it,
   which is the part of "pre-registered" that still holds here. The criteria
   cannot be tuned to a result nobody has seen yet.
2. It is NOT true that these numbers cleared a bar before they reached a
   reader. They did not. At the moment the path ships, no clause has been
   scored, and the registry verdict reads `provisional` for that reason and
   not as a formality.
3. A failure therefore cannot block a ship that has already happened. What a
   failure does instead is MOVE THE SERVED NUMBER BACK, and 11e fixes in
   advance which failure moves it how far.

The flag exists for exactly that. `SALARY_PATH_MODE = "off"` reproduces the
pre-change payload byte for byte, the off path keeps its own tests, and the
revert is one constant rather than a re-implementation. A gate whose failure
carries no mechanical consequence is a note; this one carries a constant.

Section 0a's standing rule applies unchanged: a number measured after the
decision is a receipt, not evidence for it. That rule is also why C4' RECORDS
whole-board Spearman and does not gate on it.

### 11b. What is claimed, and what is not

The claim, in the owner's words:

> A season a club controls is worth what the player produces minus what the
> club will owe him. We now price every such season we can name a price for,
> instead of pricing only the ones with a signed contract. Most of the new
> money is pre arbitration seasons at the league minimum, which is a CBA rule.
> The arbitration model supplies about a third of it. This is a coverage
> change, and the rank order of the trade board moves a lot because of it.

NOT claimed, and no clause below may be read as evidence for any of it:

- that the award model became more accurate. It is unchanged. MLBTR/Swartz is
  still 2.66x better on settled seasons (MdAPE 0.216 against 0.081, n = 261,
  section 9 and the `arb_award` row). C3' only checks that the gap does not
  widen.
- that the control WINDOW is known. Its length is read off Spotrac's status
  grid and, past the last priced grid step, off the class token, which flag
  bit 1 marks as inferred rather than read from published service time on 709
  of 852 rows. C9' is the only external check on the horizon and its n is
  small by construction.
- that the published surplus is the value of the club's tender option. The
  cliff is applied to the MEAN projection path, and `E[max(0, X)] >=
  max(0, E[X])`, so the served number is a LOWER BOUND on that option. That is
  the one remaining conservatism and the served copy names it.
- that arbitration seasons dominate the change. 61.3% of the added money is
  PRE-ARB seasons at the CBA league minimum, which is a rule and not a
  prediction. About a third is on-grid arbitration and about 6% comes through
  class closure.

### 11c. Protocol, frozen before any number is read

- **Seed 20260917, B = 1000.** Every interval is a paired bootstrap clustered
  on PLAYER, refitting any fitted arm on every draw: the convention sections 5
  and 9b already use.
- **Pools, counted at scoring time and published with their clause**, because
  the panel and the projection board both regenerate nightly and any count
  quoted from design day will drift:
  - C1', C3': the GATE B pool (players with an observed arbitration window),
    paired across arms, with the dropped count reported.
  - C2': players whose 2026 award is recorded in `data/arb_history.json` and
    whose 2026 step the path would have projected off the 2025 board.
  - C4' to C7': every served veteran row in `data/mlb_projections.json`.
  - C8': board rows whose grid carries at least 3 seasons (design-day pool 30
    rows, 29 of them with a prior arb token).
  - C9': board rows where the panel resolves a published MLBTR service-time
    string out of `data/_labs/arb_ledger.json` (moved from `data/` on
    2026-10-01, bytes unchanged; 2,032 entries, class years
    2022-2026, 501 in class 2026). Only 27 unique class-2026 entries carry an
    `mlbam` directly and 19 of those join the board, so the join runs through
    the panel's identity resolution and the shipped n is a MEASUREMENT, not a
    promise. The board's `sv` field is the input and is populated for this
    gate.
- **The artifact carries each criterion verbatim beside its result**, with the
  clause's n, its verdict and the arm it was scored against.
  `test_arb_path_gate.py` pins the CRITERIA as well as the verdicts, so a
  criterion cannot be edited after a result has been seen.
- **Every clause states its own direction.** Nothing is assumed to be
  higher-is-better.
- The lab is read-only over the served artifacts and writes one block. It never
  rebuilds `data/arbitration.json`: class closure lives in `salary_path.py`, so
  the board's published `tot` does not grow (decision D3).

### 11d. Clauses

| clause | claim | criterion | fails if |
|---|---|---|---|
| C1' | the served chain prices an arbitration window better than the incumbent ladder | re-run the 2026-08-19 C1 protocol on the current pool (window MAE of the discounted total, paired, clustered on player): the served chain must beat both `clemens_2026` and the fitted ladder by more than the one-sided MDE95 of each contrast. Prior: $2.215M against $4.927M and $5.372M, a 4.98x floor | the margin falls inside the floor |
| C2' | realized 2026 awards against what the path projected | on every player whose 2026 award is in `data/arb_history.json` and whose 2026 step the path would have projected from the 2025 board: MdAPE <= the MdAPE the board itself records for those rows, and the signed median residual inside [-0.05, +0.05]. **This is the owner's own check and it can kill the change** | either bound is missed |
| C3' | the MLBTR/Swartz gap does not widen | on the rows both cover, our MdAPE must not exceed the 2026-08-19 figure (0.216 against Swartz 0.081, a standing NULL) | it widens |
| C4' | replaces GATE C's old C4. The reordering is exactly the coverage and nothing else | Spearman(pre, post) on rows whose salary path is UNCHANGED must be 1.0000; every row moving by more than $1M must have at least one newly priced season; the count of moving rows must equal the count of rows with a newly priced season and a delta over tolerance. Whole-board Spearman is RECORDED, not gated | any untouched row moves, or any moving row has no new season |
| C5' | ladder monotonicity survives closure | violations of `usd < 0.80 * prev` across every served path, closure seasons included: 0 | any violation |
| C6' | no prospect is arb-priced | prospect rows carrying `salPath`: 0 | any |
| C7'a | the floor never lowers a total | floored NPV >= raw NPV on every row, and no floored season-surplus is negative on a cuttable season. Floored rows and dollars restored are recorded | any floored total below its raw total |
| C7'b | the shipped stopping rule is not beaten by the rule it replaced | recompute the forward stopping rule (`t* = min{t : C_t < 0}`) on every path: backward induction >= forward on 100% of rows, with the count of rows where it is strictly greater recorded (that count is the bug the repair fixed) | any row where backward < forward |
| C8' | closure's class CHAIN matches the grid | hold out the last season of every grid with >= 3 seasons, derive it by closure, compare the derived token and salary. Token accuracy 1.000 and salary MdAPE <= the board's arb-2+ MdAPE (0.158). **n must be published in the receipt**: the pool is 30 rows, 29 with a prior arb token, and Spotrac's grid increments the class by construction (0 non-consecutive chains measured), so this clause tests ARITHMETIC, not the horizon. A second tier is scored and reported: hide the last TWO seasons wherever the grid has >= 2 arb tokens | token accuracy < 1.000, or salary MdAPE above the board's own |
| C9' | **the horizon itself.** The closure rule's implied last controlled season matches published service time | on every board row where the panel resolves an MLBTR service-time string (`data/_labs/arb_ledger.json`), derive remaining arbitration years from service time and compare with `K - k_last`. Criterion: **0 rows off by more than one season**, with the disagreement count and n published. If **n < 25** the verdict is pre-registered as **UNDERPOWERED**: the clause has not been scored, closure does not advance past its flag on this clause alone, and it is re-scored when n reaches 25 | any row off by more than one season, or (soft) n < 25, which blocks promotion rather than failing the model |

C2', C7'b and C9' are the clauses that can fail on evidence. C1' and C3' are
re-runs of a battery that passed. C4' to C6' and C7'a are code invariants: they
fail on a bug, not on a measurement.

### 11e. The response to a failure, fixed in advance

Because the owner ordered the path served before this gate could run, a failure
does not withhold a ship. It reverts one. `SALARY_PATH_MODE` is the whole
mechanism: `"off"` restores the pre-change payload, `"ladder"` keeps the
on-grid arbitration seasons and drops class closure, `"closure"` keeps closure
and drops the tender cliff.

| failed clause | pre-registered response |
|---|---|
| C2' | `SALARY_PATH_MODE = "off"`. The owner named this the check that can kill the change, and it is the only clause scoring the salary leg against a realized award |
| C1' | `"off"`. If the served chain cannot beat `clemens_2026` on an arbitration window, the arb leg is priced by the wrong estimator and the question re-opens as which estimator prices it |
| C3' | no revert. The Swartz gap is a standing NULL this change does not claim to close; a widening is recorded and blocks the verdict leaving `provisional` |
| C4' | `"off"` until the bug is found. An untouched row that moves is an implementation defect, not a measurement |
| C5' | `"ladder"` (closure off) until it is fixed |
| C6' | `"off"` immediately. A prospect carrying `salPath` is out-of-population use, which is the failure mode section 6 exists to prevent |
| C7'a or C7'b | `"closure"` (cliff off) until the arithmetic is repaired |
| C8' | `"ladder"` (closure off) |
| C9' FAIL | `"ladder"` (closure off). The horizon is wrong by more than a season and closure is what sets it |
| C9' UNDERPOWERED (n < 25) | closure keeps serving under the owner's order, the registry verdict stays `provisional`, the horizon hole stays published in the accountability census, and the clause is re-scored when n reaches 25. It is NOT read as a pass |

A revert is the constant plus a re-run of the exports that consume the path
(`proj_export`, `export_trade_values_json`, `mlb_player_export`); it needs no
other edit. Keeping a failed clause serving is the owner's call, and either way
the failure is published in the accountability census and in this gate's block.

### 11f. Served numbers that must NOT move, asserted rather than believed

The change is a coverage extension of ONE consumer. Everything below prices
through a different path and must be byte-identical across the flag flip; each
is an assertion in the commit that moves the flag, not a belief about it:

- `/arbitration/`'s published `tot`, its `l` ladder and `ou_war` (closure lives
  in `salary_path.py` and `build_board` is untouched; decision D3).
- the 133 projection rows signed through 2028 or later (measured add exactly
  $0).
- the 277 veterans with no board row and no contract, who stay unpriced before
  and after.
- every prospect row, on both the projection board and the trade board.
- `/fa/` Contract Surplus, and farm surplus, `Sur+`, `OrgSur+`,
  Grad-Contract Surplus and every eFV number: they price through
  `value_framework`, which this change does not enter.

No route, hash or deep-link key is renamed. `#g=salary_path` is the only new
one.

### 11g. Non-degrade, and the successor question

`surplus_backtest_real.py` stays producer-independent of this path (it reads
`storage` / `value_framework` / `backtest` / `consensus` and never reads
`data/mlb_projections.json`), so the 2026-08-19 C2 argument carries verbatim.
The artifact hash is recorded as pre == post rather than re-derived.

**Registered successor question, deliberately not a clause here.** No clause
above scores SURPLUS accuracy out of sample, because this tree holds no
realized control-window surplus label set. Building one (realized WAR times the
realized winter $/WAR, minus money actually paid, over closed control windows)
is the successor gate. It is named here and in the eval artifact so the hole is
not rediscovered as a finding: what this gate asserts is that a club-controlled
season is worth its production minus its price, not that the number attached to
it has been validated against realized surplus.

### 11h. Pre-scoring amendment (2026-09-24): forward ARB 1 rungs are built the way training rows are

Registered before any clause of this gate was scored. On this date
`data/arbitration_eval.json` carries no `gate_c2` block and no C2 number has
been read, so this amendment cannot have been shaped by a result.

**The defect.** `arb_export.build_board` priced each forward ARB 1 rung off a
copy of the player's latest panel row. Three of the arb-1 champion's inputs did
not match their training definition on that copy:

- `war3` and `career_war` were attached only to `scored_rows` inside
  `export()`. The latest row of a pre-arb player is not a scored row, so both
  read 0.0 on every forward rung.
- `hem`, `sem` and `rem` were looked up under the rung's own season (2027 or
  2028), which `metric_panel` does not hold, so all three took the 100 default.
- a first trip with no salary on file (57 class-1 rows) carried no prior, while
  a rung after a PRE-ARB rung (145 rows) raised off the league minimum.

The served ARB 1 rungs ranked against projected WAR at Spearman 0.153 (n 187),
topped out at $2.0M and priced the four 3+ WAR rungs at $0.85M to $1.21M.

**The repair fills existing keys and refits nothing.** The GATE A champion
tuple, its coefficients, the deflator and every backtest row in
`data/arb_history.json` are unchanged.

- `war3` is the award season plus the two before it, and `career_war` runs
  through the award season inclusive: the training definition. Realized WAR is
  used through the last observed season and projected WAR after it.
- `hem`, `sem` and `rem` come from the latest observed season. This is a stated
  proxy: training reads the award season itself, which has not been played.
- a first trip with no salary on file raises off the prior season's league
  minimum, which is what a pre-arb player is paid. Age advances with the
  season. No rung is served below the league minimum (a rule; it binds on one
  rung).

**What moves:** `/arbitration/` `l` and `tot` on the 202 rows with an ARB 1
rung, and through them every salary path that runs through one (rule 2, and
rule 3 closure anchored on such a rung). ARB 1 median $1.342M to $1.542M, p90
$1.754M to $3.218M, max $2.001M to $12.106M, Spearman against projected WAR
0.153 to 0.844. Board `tot` sums $2,041.9M to $2,339.5M.

**What does not move:** `arb_history.json`, C3' (scored on those backtest
rows) and its 0.216 anchor, and the constant `C2_CHAIN_MDAPE_BOUND` (taken
from the same backtest record).

**Consequences for this gate.** 11f lists `/arbitration/` `tot` and `l` as
must-not-move ACROSS THE `SALARY_PATH_MODE` FLIP. That still holds: this repair
does not touch the flag, and `tot` still equals its own ladder. It moves them
in its own commit, with its own before and after, and C1', C2' and C10' score
the repaired chain. This section is the registration the C10' response in
`tools/arb_path_gate.py` names as the repair of the blocking defect on the
salary leg.

## 12. 2026-10-04: the 2026 Spotrac column roll-off and the section 10 pins

Recorded 2026-10-04. Nothing above this section is edited; section 10 and its
heading stand as written, and this section records new readings beside them.

**The cause.** The Spotrac refetch of 2026-10-03 is the first whose team-page
year columns start at 2027: the 2026 column rolled off. Every figure section 10
pinned was read over a grid that still carried 2026, so the pins moved with the
input, not with any change to the rule.

**The two adjudicated cases, re-read on the cached pages of 2026-10-03.**

| Player | Section 10 reading | Reading after the roll-off |
|---|---|---|
| Nolan Arenado, ARI active row (employing club, serves) | $5,500,000 AAV (2026: 5,000,000 / 2027: 6,000,000) | $6,000,000 AAV over the 2027 column |
| Nolan Arenado, STL retained row (status table, never competes) | $27,361,111 | $18,611,113 (2027 only) |
| Nick Castellanos, SD dead row (employing club, served) | $304,492 | no row: his SD obligation was 2026 only |
| Nick Castellanos, PHI retained row (never competes) | $19,695,508 | no row on the PHI page |

**The rule is unchanged.** The employing club's row serves and a retained row
never enters the contract set (`spotrac.CONTRACT_TABLE_IDS` excludes
`dataTable-retained`). `test_arb_gatec_verify.py::
test_served_aavs_are_the_employing_club_obligation` is re-pinned to the readings
in the right-hand column: Arenado's ARI AAV equals the figure the parser reads
now and is not the STL retained figure; Castellanos has no contract row on SD,
and no PHI row reaches the contract set.

**A second effect of the same roll-off, on the projections join.** A player
whose only money was his 2026 salary now parses as a status-only row (ARB or
PRE-ARB tokens, no money year, no signed_through): 987 of the 1,205
contract-table rows. `proj_export` had served such a row as a $0 AAV (716 of
1,400 veteran rows against 2 at the step A copy) and counted it as a contract
for the plain-key award. From 2026-10-04 the join (`proj_export._join_contract`,
`spotrac.is_status_only`) keeps the row's tokens, club and position, carries no
AAV, and never lets it move a plain key; the salary path prices those seasons
from the tokens through the arbitration board, as before. Served surplus did
not move (no row by more than $1M; none at all on the worktree regen).

---

## 13. Club arbitration process: a width term on the award band and one term in the point award (pre-registered 2026-10-08)

Registered 2026-10-08, docs only, committed alone. At this commit no code, flag,
column, label or number of either quantity registered here exists: the tracker
re-capture and its club-heading parser (task Q9_17, plan row FAA-3) and the club
labels and chips (Q9_18, FAA-4) come after it. Nothing above this section is
edited.

**Numbering.** The plan (master plan Part 8, row FAA-1; the lane design
`finance_to_fa_arb.md`, section 2.4) calls this registration "section 12", with
parts 12a to 12d. Section 12 was taken on 2026-10-04 by the Spotrac roll-off
record, so the registration is section 13 and its parts map one for one: 13a is
the plan's 12a, 13b is the plan's 12b, 13c is the plan's 12c, 13d is the plan's
12d. 13e is the point-award term the owner added. A later task that names
"section 12a" or "12b" of this gate means 13a or 13b.

**The ask and the answers.** Owner ask 3 (2026-09-30), verbatim: "Can we wire
the financial module into the Free Agency / arbitration modules to make them
more accurate? Ex. to make team fit projections more accurate based on which
teams actually spend money in free agency." ARB-CLUB-1 (b): descriptive chips
from the 2024-2026 trackers now, and a 2011-2023 backfill from Cot's Contracts
once its terms allow. ARB-CLUB-2 (c), the owner departing from the
recommendation: club process is tested in the point award itself, which collides
with section 4's ban on team effects and so needs its own amendment (13e) and a
GATE A re-run that must pass before any serve; the band width term (13b) is
registered as well.

### Read to write this

The 2024, 2025 and 2026 MLB Trade Rumors arbitration trackers were read to
design this item, and so were those winters' hearing outcomes, which are public.
No case from those three winters is ever scored under this section. What the
design read, as the lane design recorded it on 2026-09-30 (descriptive counts,
not a reading of any quantity registered here):

- the cached January trackers (`.cache/mlbtr/2024_01_2024-arbitration-tracker.html`,
  `2025_01_...`, `2026_01_...`): 30 club headings each; 22 exchanged cases
  across 14 clubs in 2024, 17 across 12 in 2025, 18 across 14 in 2026; 25 clubs
  exchanged at least once over the three winters, 5 never (ATH, ARI, CLE, COL,
  CHW), BAL the most with 8; the 2026 page's Rangers policy note ("As always,
  there will be no arb hearings for the team");
- the outcome classes in `data/_labs/arb_ledger.json` (agreed 564, exchanged 57,
  club_option 5, extension 4, split_deal 4, unknown 3; no hearing class fires,
  because the cached pages are January snapshots taken before the hearings);
- `data/arb_history.json` (766 rows, 2023 to 2026) and its season-end club
  attribution (Tarik Skubal's 2026 award reads LAD; the tracker lists him under
  Detroit);
- the award band in `arb_export.build_board` (22% at arb-1, widening 8 points a
  rung, not published as a calibrated interval) and the champion tuple
  `arb_model.CHAMPION_KEYS`.

The writer of this section opened none of the tracker pages and computed no
statistic relating any club to any award, residual, band or hearing result.

### 13a. Band calibration (the plan's 12a): named here, registered later

Band calibration, to follow by a dated amendment after GATE C2 is scored (task
Q9_20; also after the M11/M12 sequence and the B5 known-season registration).
The plan's sketch: out-of-fold residual quantiles by rung and chain depth from
the champion's forward-chained residuals, a coverage target of 0.80 for the P10
to P90 band, the interval score against today's fixed band, player-clustered
floors under the section 3 conventions, and the M12-4 league-minimum floor on
both bands. Nothing in this section registers it.

13b multiplies the band that 13a calibrates. If 13a is never registered, or is
registered and does not ship, 13b is recorded `NOT SCORED`, which is neither a
pass nor a NULL, and the band never reads club process.

### 13b. Club-process width (the plan's 12b)

**Treatment.** One scale multiplier `s` on the calibrated award band (13a's P10
to P90) for cases at clubs labelled "File and trial" from winters strictly
before the case's. The point award does not move: the two half-widths scale
about it, `low = point - s * (point - P10)` and `high = point + s * (P90 - point)`,
and the low end keeps the league-minimum floor. Cases at unlabelled clubs keep
the calibrated band unchanged (s = 1).

**The label, exactly as FAA-4 defines it.** A club is "File and trial" for a
case in winter W when, over the captured winters strictly before W, it
exchanged figures with at least 2 players (exchanged >= 2) and settled with
none of them after the exchange (settled after the exchange = 0). The other
label FAA-4 serves, "Settles before the exchange" (exchanged = 0 on at least 10
cases), is not a treatment here. The label reads process classes and counts
only: never a filed figure, an award amount or the dollars of a hearing result.

**Thresholds, fixed at this commit.** exchanged >= 2; settled after the
exchange = 0; winters strictly before the case's.

**Inputs the label reads, and only these.** The MLB Trade Rumors tracker
captures, attributed by the FAA-3 rule: a case belongs to the club under whose
heading the tracker lists the player on exchange day, never to the season-end
club in `arb_history`. The captured window starts with the 2024 tracker. The
Cot's Contracts backfill (ARB-CLUB-1 (b), 2011-2023) is not read by this label
unless a dated amendment written before the first count in 13d says so.

**The case.** The section 1 estimand: a tendered, arbitration-eligible
player-season settled or awarded at one year through the arbitration process,
with the settled or awarded figure on file. Extensions, multi-year deals, club
options, split deals and non-tenders are out, as the tracker classes already
separate them.

**Scored cases: only winters captured after this commit.** The January 2027
exchange-day capture and the February 2027 post-hearing capture are the first;
each later winter captured the same way joins the frame. No case from the 2024,
2025 or 2026 winters is scored, ever, because those pages and their hearing
outcomes were read to write this section. Those winters may supply labels and
training rows (a 2027 case's label reads 2024 to 2026), never scored cases.

**Fit.** `s` is one scalar, chosen on the fixed grid 0.50 to 2.00 in steps of
0.05 to minimize the mean interval score of the labelled group over the
training winters (every captured winter strictly before the scored winter that
holds labelled cases with figures on file), refit forward-chained for each
scored winter. The control is the same calibrated band with s = 1.

**Metric.** The interval score of the central 80% band (alpha = 0.20: the width
plus 2/alpha times each miss), in deflated dollars, within the labelled group,
paired against the control. Floors: a paired bootstrap clustered on player, B =
1000, seed 20261008, one-sided MDE95 (section 3).

**Power precondition, written first.** The labelled group must hold at least 62
scoreable cases across the scored winters before the read is allowed. That is
the count at which the 95% binomial half-width of a coverage reading at 0.80,
1.96 * sqrt(0.80 * 0.20 / n), reaches 0.10 (n = 61.5, rounded up): a coverage
MDE95 of 0.10. The two-sided form is registered on purpose, though section 3's
convention is one-sided (n = 44 at 1.645), because a band can miss its coverage
in either direction. Short of 62 the arm is a pre-committed NULL, the A6
single-season precedent.

**Pass.** All three: (1) the arm's interval score beats the control's by more
than the one-sided MDE95 of the paired contrast; (2) the arm's coverage inside
the group lies within 0.10 of 0.80; (3) a label-permuted twin (the File and
trial label reassigned at random across clubs within each winter, the count of
labelled clubs held fixed, `s` refit on every draw, B >= 500) gains less than
the real arm on at least 95% of draws. Anything else is a NULL.

### 13c. What never moves

The champion point award, the frozen feature tuple (`arb_model.CHAMPION_KEYS`)
and `projectable_keys`. 13b enters after the champion, on the band only. The
banned-key test in `test_arb_export.py` extends to every club-process key (the
chip keys FAA-4 adds and the label itself), so no such key can reach the
champion tuple or the serve path's projectable keys. The one exception the owner
asked for, a single club term in the point award, is registered in 13e with its
own amendment to section 4; until 13e passes and the owner flips its flag, this
paragraph binds the served award as written. 13b never admits it.

### 13d. The response, and the look order

**13b PASS:** the band carries the club term behind its own flag
(`ARB_BAND_CLUB_TERM`, off by default), flipped in one commit carrying the
multiplier, a chip on every widened band that says the band is wider because the
club takes its cases to a hearing, the registry row and the glossary entry. A
printed band digit moves, so it ships only after the owner's answer.

**13b NULL:** chips only, and the band stays as 13a ships it. Recorded
verbatim: *"The club process term is a NULL on the award band. Cases at File and
trial clubs were not priced better by a wider band than by the calibrated band
itself, or the group held fewer than 62 scoreable cases. The band does not read
club process."*

**Look order, fixed now.**

1. This registration (2026-10-08), committed alone.
2. Q9_17 (FAA-3): the club heading in the tracker parser and the one dated
   re-capture of the 2024 to 2026 trackers and filing-figure posts. Lab data
   only.
3. Q9_18 (FAA-4): the descriptive chips and the label function, behind
   `ARB_CLUB_PROCESS_CHIPS`.
4. GATE C2 scored, then 13a registered by dated amendment (Q9_20) and scored.
5. The January 2027 exchange-day capture and the February 2027 post-hearing
   capture; each later winter the same.
6. After each February capture the scoreable labelled cases are COUNTED (labels
   and case presence only; no award, band or residual is read).
7. The one look: the first February capture at which the count reaches 62, and
   no later than the February 2029 capture. If the count is still short at the
   February 2029 capture, 13b and 13e are recorded NULL without reading any
   outcome.
8. At that look 13b is scored only if step 4 shipped a calibrated band
   (otherwise `NOT SCORED`, per 13a), and 13e's GATE A re-run runs once.

If the collective bargaining agreement in force for a scored winter changes the
filing or hearing process, that winter joins the frame only by a dated amendment
written before its February count.

### 13e. One club-process term in the point award, and the amendment to section 4 (ARB-CLUB-2 (c))

**The term.** One indicator, `club_file_and_trial`: 1 when the case's club
carries 13b's File and trial label (the same rule, thresholds and inputs, winters
strictly before the case's), 0 otherwise. It enters the point award through one
coefficient on the log scale after the champion chain:
`log(award') = log(award) + beta * club_file_and_trial`. The champion's coefficients, its tuple and the
banded step multipliers are not refit; beta is the only fitted number. It is
fit by least squares on the champion's out-of-fold log residuals over the
training winters (every captured winter strictly before the scored winter),
forward-chained, and section 3's smearing correction is recomputed with it. Its
sign is not constrained.

**Frame.** The 13b frame: scored cases only from winters captured after this
registration (the January and February 2027 captures on). The 2024 to 2026
winters may train beta and are never scored.

**Power precondition.** The 13b count: at least 62 scoreable labelled cases
before the read. Before the contrast is read, the section 3 floor procedure measures
its floor (a paired bootstrap clustered on player with a refit on every draw, B =
1000, seed 20261008, one-sided MDE95) and runs a detection check with an effect
planted at the floor. If the count is short, or that procedure cannot see the
planted effect, the term is a pre-committed NULL.

**Pre-committed NULL:** *"The club process term is a NULL on the arbitration
point award. Its effect on the scored winters is below the measured floor, or
not separable from a club-permuted twin, or the group held fewer than 62
scoreable cases. Section 4's ban on team effects stands in full."*

**The GATE A re-run that must PASS before any serve.** Run once, at the 13d
look, on the scored winters: the champion plus the term against the champion
alone. Every line must hold:

- the increment: the champion plus the term beats the champion on MSE in
  deflated dollars by more than the contrast's one-sided MDE95, player-clustered,
  and does not lose on median absolute percentage error by more than 10%
  relative (section 3's guardrail);
- A1 and A2 still pass, reported separately for arb1 and arb2+;
- A3 in its club form: the label permuted across clubs within each winter, the
  count of labelled clubs held fixed, beta refit; the real term beats the
  permuted twin, and the twin's mean gain sits inside its own null band around
  zero;
- A4: a permutation null over the same cells, B >= 500; the real gain above the
  null's 95th percentile;
- A5: the deflator leak twin does not fire;
- A8: signed bias by predicted-salary decile within 5% of the decile mean;
- A10: every served row carries the term as its own factor in the explainer
  array, and the exact remainder still reconstructs the served figure.

A6 stays a standing NULL and is reported, not gated.

**The amendment to section 4, and its scope.** Section 4 bans team fixed
effects from the champion, as diagnostics only, because they correlate with
quality and are post-treatment for mid-season trades. This amendment admits
exactly one club term, `club_file_and_trial` as defined above, and nothing
else: no club identity or club fixed effect, no other club-process key (cases,
exchanged count or share, hearing count, hearing W-L, the "Settles before the
exchange" label), and no payroll, Ledger or spending figure. The two reasons
for the ban are answered by construction, not waived: the term is attributed to
the exchange-day club and reads only winters strictly before the case's, so
neither a mid-season trade nor the case's own hearing can reach it; and it
enters after the champion's quality features, with the club-permuted twin as
the control for a quality proxy. The case's own hearing occurrence, filed
figures and settlement date stay banned. The term never enters
`CHAMPION_KEYS`: it is a separate key on the award path, admitted by the
banned-key test as the one named exception and only while the flag
`ARB_AWARD_CLUB_TERM` is on. Until the re-run passes and the owner flips that
flag, section 4 reads as written.

**Response.** PASS: the term serves behind `ARB_AWARD_CLUB_TERM`, flipped by the
owner in one commit carrying the flag, beta, the explainer factor, the registry
row and the glossary entry, and naming every award that moves. FAIL or NULL:
the term never serves, the NULL sentence above is recorded here and in the eval
artifact, and any second club term needs a new registration.

### 13f. Results

Empty at registration. Nothing in this section has been read: no label
computed, no case counted, no band or award scored.

---

## 14. GATE K - a known-season arbitration arm against Swartz (pre-registered 2026-10-08)

Registered by owner answer 2026-09-25 (batch 5, census X05-03) BEFORE any
feature for it is built, any award is fetched or any row is fit. Nothing above
this section is edited, and GATE A, B, C, C2 and D are not re-opened by it.

**Why.** On identical rows the MLB Trade Rumors / Matt Swartz projection beats
our served estimator 2.66x on MdAPE (0.0811 against 0.2156, n = 261;
`data/arbitration_eval.json` `a6_swartz`, generated 2026-08-09; by step:
arb 1 n 135, 0.218 against 0.085; arb 2 n 76, 0.204 against 0.082; arb 3 n 50,
0.211 against 0.076). The artifact's own statement names the mechanism: Swartz
prices the platform season's counting stats and honours, which section 4 bans
from our champion because nothing projects them forward. Once the platform
season is over they are KNOWN. This gate asks whether an arm that reads them
closes the gap. It is a separate arm, not a change to the champion.

### 14a. What is claimed, and what is not

- Claimed only on a pass: on settled arbitration seasons, after the platform
  season is complete, the known-season arm prices the award more accurately
  than our incumbent (K1) and than the published Swartz figure (K2).
- NOT claimed under any verdict: anything about an UNPLAYED season. The forward
  board (`/arbitration/` ladder, the salary path, every surplus) keeps the
  section 4 champion and `CHAMPION_KEYS`; section 4's ban on counting stats in
  the champion stands. This arm never feeds `salary_path.py`.

### 14b. Inputs, a frozen tuple

`KNOWN_SEASON_KEYS` is a frozen tuple in `arb_model.py`, committed with the
producer and pinned by its test before the first fit:

1. Every key of `CHAMPION_KEYS`, with every production input read from the
   PLATFORM season (the season before the award season S) or earlier. No
   feature of a season-S row may read a season >= S (census M08-05); the test
   asserts it row by row.
2. Platform-season counting stats, the ones arbitration panels weigh: hitters
   HR, RBI, R, SB, H; pitchers W, SV, HLD, SO, IP; plus career-to-date HR and
   SV through the platform season. The four `CEILING_KEYS` additions (hr, sb,
   sv, hld) are a subset. Source: the season tables the panel already reads.
3. Platform-season honours: All-Star selection; BBWAA MVP, Cy Young and Rookie
   of the Year (top-10 finish indicator and vote share); Gold Glove; Silver
   Slugger. Source: a new season-stamped cache of the StatsAPI
   `people/<id>?hydrate=awards` feed (probed 200 by the census on
   2026-09-24). The award join rate is published with the result.

Fit: the GATE A two-stage form (`fit_stage1`, `fit_stage2`) with
`keys=KNOWN_SEASON_KEYS`, the same ridge, floor transform and smearing. No
penalty, key or transform is tuned after a score is read.

### 14c. The frame

- **Rows: the same 261 (player, class year) pairs as the `a6_swartz`
  comparison.** The block stores no row list, so the build's first act is to
  reconstruct the pairs with the A6 join as committed in a35ee272, write the
  sorted (mlbam, season) list and its sha256 into the eval artifact, and
  assert n = 261 BEFORE any feature is joined. If the reconstruction gives a
  different n, the delta and its cause are published and the reconstructed
  set is the frame; it is never re-chosen after a score is read.
- **Composition, measured 2026-10-08 and disclosed:** `data/arb_history.json`
  carries a Swartz figure on 287 settled rows, 236 of them class 2023 (18 in
  2024, 16 in 2025, 17 in 2026). The 261-row frame is therefore mostly one
  winter; see K3.
- **A second frame, reported beside it, never the headline:** if the Swartz
  loader repair (census M08-04) has landed when this gate is scored, the
  repaired pool is scored the same way and published side by side.
- **Protocol:** forward-chained by class year exactly as `forward_chain`
  (train on class years before the test year, deflator fit on train years
  only, every arm refit per fold). Seed 20261008, B = 1000, paired bootstrap
  clustered on PLAYER, refitting every fitted arm on every draw.

### 14d. Metric

MdAPE on deflated dollars. Every arm, Swartz included, is put on the SAME
scale: the actual award and each prediction are divided by the test fold's
deflator for that season. Because a common factor cancels in an absolute
percentage error, Swartz's error is equivalently his nominal figure against
the nominal award.

Recorded rather than fixed here: the A6 code (`tools/arb_gate_a.py`
`_swartz_head_to_head`) compares Swartz's NOMINAL figure with the DEFLATED
actual; its comment says the figure is scaled and the code does not scale it.
The 2.66x is therefore re-stated under this gate's scale on the frozen frame,
beside the published figure, and the restated number is the one K2 is scored
against. MSE in deflated dollars is reported alongside, as section 4 does.

### 14e. Clauses and the pass rule

| clause | claim | criterion | fails if |
|---|---|---|---|
| K1 | the arm beats our incumbent | on the frozen frame, identical rows: incumbent MdAPE minus arm MdAPE exceeds the one-sided MDE95 (1.645 sd) of that paired gap. The incumbent is the SERVED estimator as served when K is scored (after any registered GATE A amendment), named in the artifact | the gain sits inside its floor |
| K2 | the arm beats Swartz | arm MdAPE below Swartz MdAPE (restated, 14d) AND the paired player-clustered 95% interval on (Swartz minus arm) has a lower bound above 0. Raw published Swartz is the headline; recalibrated Swartz (section 4 A6 affine, train years only) is reported as the stronger secondary | either condition is missed |
| K3 | the K2 direction is not one winter | the sign of (Swartz minus arm) is reported per class year with n >= 15. If one class year holds >= 75% of the frame, a K2 pass is labelled ONE WINTER and no copy may say the arm beats Swartz without that label (section 4 pre-commits single-season Swartz comparisons as NULL) | reported, never a pass by itself |
| K4 | the gain is the new inputs, not structure | refit with the counting-stat and honours block permuted across players within (season x arb-step) cells, as A3: the real block must beat the permuted twin on the K1 gap | the permuted twin matches it |
| K5 | equal information | the twin without honours announced after the Swartz publication date (Gold Glove, Silver Slugger, BBWAA awards; All-Star stays) is scored on K2. A K2 pass without a K5 pass may only be described as beating Swartz WITH information published after his projection | reported, never a pass by itself |

**Verdicts.** K1, K2 and K4 pass: PASS. K1 and K4 pass, K2 fails: IMPROVES,
with the share of the gap closed, (incumbent minus arm) / (incumbent minus
Swartz), published; nothing may say the arm matches or beats Swartz. K1 or K4
fails: NULL. What a PASS may serve (a post-season known-season figure on the
History tab) is the owner's call after the result; nothing is served by this
registration.

### 14f. Artifacts, and one look

Producer `tools/arb_known_season.py`, artifact `data/arb_known_season_eval.json`
(a separate path, as section 4 requires of a model reading banned keys), test
`test_arb_known_season.py` pinning the criteria above verbatim and the frame
hash, registry row `arb_award_known_season`. Scored ONCE. A re-score after a
read is a new dated registration, not an edit of this one.

### 14g. Order, and the status on 2026-10-08

Build and score only AFTER GATE C2 (section 11) is scored, the census M08-06
default, which also places it after the GATE A platform-season amendment and
the Swartz loader repair that precede C2 in the owner's 2026-09-25 sequence.
"Scored" means `data/arbitration_eval.json` carries a `gate_c2` block with its
clause verdicts.

On 2026-10-08 it does not: the artifact (generated 2026-08-09) has no
`gate_c2` block, and section 11h records that no C2 number had been read on
2026-09-24. **The build of this gate WAITS ON GATE C2.** Nothing in 14b to 14f
has been built, fetched or fit.

---

## 15. GATE A amendment (registered 2026-10-08, before any re-run): production lagged to the platform season

Numbering note (integration, 2026-10-08): this section and sections 16 to 18
were written as sections 13 to 16 on their worktree branch and renumbered when
they merged after the club arbitration process (section 13) and GATE K
(section 14) registrations; only the section numbers changed.

Registered and committed alone, before `tools/arb_gate_a.py` was run under it.
Nothing above this section is edited. Owner answer M12-2 (2026-09-25,
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, final-pass 'more' batch 12):
register a GATE A amendment lagging production to the platform season and
re-run. Owner answer M12-1 holds GATE C2 (section 11) until this lands.

### 15a. The defect

Section 1 states the estimand as an award "given only information observable
as of the tender deadline". The battery scored on 2026-08-09 did not do that.
For a panel row whose award season is `s` (the season the award pays), the
champion read `war`, `pa`, `ipouts`, `gs`, `war3` (seasons s, s-1, s-2),
`career_war` (through s) and the `hem` / `sem` / `rem` block of season `s`
itself. Season `s` has not been played when the award is set in the winter
before it. The arb-1 PASS (3.25x its floor) and the A6 comparison were
therefore scored with production a club, an agent and a panel could not
see. The census recorded it as M08-05; `tools/arb_mde_lab.load_pool` and
`arb_export.export` build the same frame, so the served arb-1 model was fit
on it too.

### 15b. The platform frame

For an award season `s` the platform season is `p = s - 1`, the last season
complete when the award is set.

- `war`, `pa`, `ipouts`, `gs`: the panel's values for (player, p), and 0 when
  the panel holds no MLB season p for the player. `pa_share`, `ip_share`,
  `gs_share`, `is_pitcher` and `is_reliever` follow from them, as they did.
- `war3` is WAR in p, p-1 and p-2; `career_war` runs through p inclusive.
- `hem`, `sem`, `rem`: the arb_metrics block of season p (100 when absent, as
  before).
- Unchanged, because each is already known at the tender deadline: `arb_year`,
  `super_two`, the prior salary (season s-1, a platform figure by
  construction), `has_prior`, and `age` (the player's age in season s, fixed
  by his birth date).
- The arb-1 bars read the same platform WAR. A bar may not see what the
  champion cannot.
- The deflator is NOT changed. It is fit on train-year rows only, its
  production term reads each train row's own completed season, and no test
  row's information enters it. Leaving it alone keeps the banded arb-2+
  multipliers, the served arb-2+ rungs and `salary_path.board_raise_fn`
  byte-identical, which this amendment asserts rather than assumes.
- The `award` frame is kept in code (`arb_model.FRAMES`) so the 2026-08-09
  numbers stay reproducible. It adjudicates nothing from this date.

### 15c. Protocol, unchanged from section 4

`tools/arb_gate_a.py --write --B 1200 --frame platform`: the scored pool
(`arb_dataset.scored_rows`), forward-chained by class year, seed 20260808,
B = 1200 (the 2026-08-09 run's B), the player-clustered bootstrap refitting
the deflator and both stages every draw, A3 with 200 within-cell
permutations, A5, and A6 exactly as the 2026-08-09 lab computed it (the
MLBTR loader repair is section 16's and is registered separately, after this
re-run). The criteria are section 4's: a step PASSES when its gain is
resolvable against its one-sided MDE95, beats the A3 permuted p95, and the
A5 leak is smaller than the margin.

The pool regenerates nightly (1,043 rows on 2026-08-09). So the frame's own
effect can be told apart from pool drift, the same lab runs once more with
`--frame award` on the same day's pool, written beside the result as
`award_frame_same_day_twin`. The twin adjudicates nothing.

### 15d. What serves, fixed before the re-run

- **arb-1 PASS.** The /arbitration/ board's ARB 1 rungs and the History's
  arb-1 'Ours' serve the champion refit on the platform frame. A forward rung
  for season y reads platform season y - 1: realized WAR, PA, outs and starts
  where y - 1 has been played, the projection after it (the latest observed
  season's PA, outs and starts as the stated proxy); `hem` / `sem` / `rem`
  from season y - 1 where observed, else the latest observed season (the
  section 11h proxy, now one season closer).
- **arb-1 NULL.** The ARB 1 rungs serve the bar the champion failed to beat
  (A2: the arb-1 intercept plus one platform-WAR term, smearing-corrected,
  refit on the whole pool), the way arb-2 and later serve their baseline. The
  artifact verdict falls with the gate (provisional only while some step
  passes).
- **arb-2 and later, PASS or NULL.** The served estimator stays the banded
  step multiplier in this change. A PASS there would be recorded as licensing
  the stage-2 model, and switching to it is its own measured change.
- **The 2026-08-09 block stays as a labelled HINDCAST.** Its fields move
  verbatim under `hindcast_2026_08_09_award_frame` in
  `data/arbitration_eval.json`, labelled as scored on award-season production
  unavailable at award time, quoted for the record and adjudicating nothing.
  The top-level GATE A fields carry this re-run, so every surface that quotes
  the arb-1 margin or the Swartz ratio quotes the platform frame.
- Section 9's GATE C record (2026-08-19) was scored on the award-frame model
  and stands as a dated record of that model; it is not re-scored here.

### 15e. Not reopened

The champion key tuple, the ridge, the smearing, the deflator, the pool, the
seed, B and every criterion. This repairs the information set to the one the
section 1 estimand already documents; it is not a refit to a new target, and
no constant is tuned against the result.

### 15f. Result (scored 2026-10-08, after 15a to 15e were committed)

`tools/arb_gate_a.py --write --B 1200 --frame platform`, then the same-day
twin with `--frame award`. Pool 1,069 rows, 596 players, class years
2022-2026, 4 folds (1,043 rows on 2026-08-09). Read from
`data/arbitration_eval.json`.

| step | frame | n | MdAPE model | MdAPE bar | gain | MDE95 | x floor | A3 p95 | A5 delta | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| arb-1 | platform | 421 | 0.1844 | 0.3394 | +0.1550 | 0.0433 | 3.58 | +0.0841 | -0.0040 | PASS |
| arb-2+ | platform | 391 | 0.0990 | 0.1815 | +0.0825 | 0.0270 | 3.05 | +0.0121 | +0.0012 | PASS |
| arb-1 | award, same-day twin | 421 | 0.2396 | 0.4363 | +0.1967 | 0.0486 | 4.05 | +0.0795 | -0.0080 | PASS |
| arb-2+ | award, same-day twin | 391 | 0.1623 | 0.1815 | +0.0192 | 0.0270 | 0.71 | -0.0072 | -0.0026 | NULL |
| arb-1 | award, 2026-08-09 hindcast | 409 | 0.2545 | 0.4284 | +0.1739 | 0.0529 | 3.29 | +0.0836 | +0.0185 | PASS |
| arb-2+ | award, 2026-08-09 hindcast | 379 | 0.1580 | 0.1812 | +0.0232 | 0.0278 | 0.83 | -0.0101 | +0.0134 | NULL |

A6 on the 2026-08-09 loader (section 16 repairs it): ours 0.1734 against
Swartz 0.0815, n 262, a 2.13x gap (twin 2.71x; hindcast 2.66x, n 261), the
paired MdAPE gap -0.0918 with a player-clustered interval of -0.1277 to
-0.0656. Still a loss.

Reading, without upgrading it. Arbitration pays for the season before the
award, and the frame that reads that season is the better model at both
steps: the arb-1 model error falls from 0.2396 to 0.1844 on identical rows,
and arb-2 and later go from a NULL (0.71x) to a PASS (3.05x). The look-ahead
did not flatter the model; it fed it the wrong season. Under 15d the board
now serves the platform-frame champion at arb-1, and the banded multiplier
keeps serving arb-2 and later until a change of its own switches it. The
2026-08-09 block is `hindcast_2026_08_09_award_frame` and the twin is
`award_frame_same_day_twin`; neither adjudicates anything.

## 16. A6 / C3' amendment (registered 2026-10-08, before any re-score): the repaired MLBTR pool

Registered and committed alone, after section 15's re-run and before the
loader repair below is scored. Owner answer M12-3 (2026-09-25): repair the
Swartz loader now, register an amendment naming the repaired pool, and score
on BOTH the frozen and the repaired pool. Nothing above this section is
edited.

### 16a. The two defects

1. **The loader keeps one MLBTR entry per player and class year.**
   `arb_dataset.load_ledger` indexes `data/_labs/arb_ledger.json` as
   {key: {class_year: entry}}, so when MLBTR's arbitration TRACKER post
   (settled and filed figures) and its PROJECTION post (Matt Swartz's
   pre-settlement figure) both name a player for one class year, whichever
   is read last wins. For class years 2024 to 2026 the tracker wins for
   nearly every settled player: the census (M08-04, judge probe) counted 76,
   72 and 76 projection entries surviving the loader against 297, 273 and 288
   in the ledger. `build_history` and the A6 lab both read it, so the
   History's MLBTR column was filled on 18, 16 and 17 rows for 2024, 2025 and
   2026 against 236 for 2023, and the A6 pool (n 261 on 2026-08-09, 262 on
   2026-10-08) is about 90% one class year.
2. **A6 scores Swartz on a different scale from ours.** The lab compares the
   nominal Swartz figure with the ACTUAL salary deflated by the fold's
   train-only deflator. In the first fold (2023, trained on 2022) that
   deflator is 1.0, so the defect was invisible on a 2023 pool; from 2024 on
   the actual is divided by the carried deflator level and Swartz is not.
   The history's `Ours` column has the same unit defect against its nominal
   `Actual` (repaired in its own change, owner answer M11-4).

### 16b. The repair and the two pools

- **The repaired loader** is a separate function,
  `arb_dataset.load_swartz_projections()`: every `kind == "projection"` entry
  with a published figure, keyed by (Baseball Reference id or MLBAM id,
  class year), never overwritten by a tracker entry. `load_ledger` is NOT
  changed, because the panel's published-service-time votes read it and
  changing it would move the scored pool itself.
- The join is the one `build_history` already uses: the entry's own MLBAM id
  when it carries one, else the panel's Baseball Reference id to MLBAM map.
  An (MLBAM, class year) reached by two projection entries with different
  figures is a COLLISION: it is counted, published, and left out of the
  repaired pool rather than settled by a guess. Entries with neither id are
  counted and left out.
- **The frozen pool** is the row set the 2026-08-09 loader reaches
  (`load_ledger` plus the same join), unchanged.
- **The repaired pool** is the row set the repaired loader reaches.
- **The units repair applies to both pools**: Swartz is put on the actual's
  own scale (its figure divided by the same deflator level the fold divided
  the actual by), which is the comparison the lab's own comment describes.
  MdAPE is scale-free within a row, so this changes only rows after the
  first fold.

### 16c. What is scored, and what each pool is for

- **A6** (section 4): the served estimator (platform-frame champion at
  arb-1, banded multiplier at arb-2 and later) against the published Swartz
  figure on identical rows, MdAPE, by step where n >= 15, with the
  player-clustered gap interval, seed 20260808. Scored on the repaired pool
  and on the frozen pool, published side by side. The verdict rule is
  unchanged (PASS only if ours is below Swartz), and single-season
  comparisons stay pre-committed NULL: only the pooled figure adjudicates.
- **The repaired pool is the headline from this date.** It becomes the
  top-level `a6_swartz` block of `data/arbitration_eval.json`, which every
  surface quoting the Swartz ratio reads; the frozen pool is written beside
  it as `a6_swartz_frozen_pool`. Section 15f's 2.13x (frozen pool, unrepaired
  units) stays as the record of that run.
- **C3'** (section 11d) is scored on both pools when GATE C2 is scored, with
  its registered bound (0.216) unchanged: the frozen pool is the history rows
  whose MLBTR figure the frozen loader carries, the repaired pool is every
  history row with an MLBTR figure. Its response stays "no revert; recorded
  and blocks the verdict leaving provisional".
- The repaired join also fills the History's MLBTR column (and through it
  the Club Ledger's realized Swartz figure). A coverage check is pinned: for
  each class year 2023 to 2026, history rows with an MLBTR figure over
  history rows whose player has a projection entry for that year, at least
  0.95.

### 16d. Not reopened

The champion, the frame, the folds, the seed, the verdict rule and the C3'
bound. This restores the comparison section 4 already describes (identical
rows, the same scale) on the data the ledger already holds.

### 16e. Result (scored 2026-10-08, after 16a to 16d were committed)

`tools/arb_gate_a.py --a6-only --write --B 1200 --frame platform`, the
platform-frame served estimator, Swartz on the actual's scale in both pools.
Read from `data/arbitration_eval.json`.

| pool | n | by class year (2023 / 2024 / 2025 / 2026) | ours MdAPE | Swartz MdAPE | ratio | paired gap, 95% interval | verdict |
|---|---|---|---|---|---|---|---|
| repaired (`a6_swartz`, headline) | 808 | 222 / 209 / 185 / 192 | 0.1780 | 0.0769 | 2.31x | -0.1011 (-0.1216 to -0.0879) | NULL |
| frozen (`a6_swartz_frozen_pool`) | 262 | 222 / 15 / 14 / 11 | 0.1734 | 0.0815 | 2.13x | -0.0918 (-0.1278 to -0.0647) | NULL |

The repaired join read 1,393 projection entries and joined 1,270, with 0
collisions, 7 entries carrying no id and 116 whose player has no scored
row. By step on the repaired pool: arb-1 0.1846 against 0.0923 (n 419),
arb-2 0.1956 against 0.0725 (n 235), arb-3 0.1636 against 0.0588 (n 154).
Swartz is more accurate at every step on both pools; the units repair moved
the frozen pool's Swartz figure only past the fourth decimal, because 222 of
its 262 rows sit in the first fold. The History's MLBTR column fills 859 of
863 rows (was 287).

## 17. 2026-10-08: the board applies the CBA maximum cut after a contracted season

Recorded 2026-10-08 (owner answer M11-2, 2026-09-25). Nothing above this
section is edited.

The board chains each award off the panel's salary, so it cannot see a
contract the club has already signed for the next season. `salary_path`
floors an arbitration rung that follows a contracted season at 80% of the
signed salary (CBA Article VI) and the board did not, so the two printed
different figures for the same season: 17 rows on the 2026-09-24 census.
`arb_export.build_board` now runs the same walk
(`_apply_max_cut_after_contract`), reading the signed seasons from the
Spotrac contract tables it already reads status tokens from
(`arb_dataset.spotrac_salary_by_mlbam`; on all 880 board players they equal
the path's 2027-2031 contract seasons): a contracted season opens the carry, a rung below
0.80 x prior is raised to it and becomes the next rung's prior, a PRE-ARB
rung closes the carry. Later rungs are NOT re-predicted off a floored
figure, exactly as on the path. A floored row carries flag bit 64.

**Measured today it binds on 0 rows.** Since the 2026-10-03 Spotrac refetch
the 2026 column has rolled off, so no signed 2026 salary sits before a 2027
rung, and the two 2027-to-2028 contract junctions on the board (Cole Ragans
$4.417M to $6.590M, Vinnie Pasquantino $5.550M to $6.039M) already clear the
floor; the served path's own `cba_floored_steps` reads 0. The rule stays so
the board and the path cannot diverge when a signed season next sits below
one. Section 11f's must-not-move list is about the `SALARY_PATH_MODE` flip,
which this does not touch.

## 18. GATE C2 receipt (scored 2026-10-08, as section 11d registers each clause)

Recorded 2026-10-08. Nothing above this section is edited. Owner answer M12-1
held this gate until the GATE A look-ahead fix landed (section 15); the
MLBTR repair (section 16) landed before it as well. Scored on the served
model of that day: `SALARY_PATH_MODE = "full"`, the platform-frame award
model, board vintage 2026-10-08. `tools/arb_path_gate.py --write` writes the
`gate_c2` block of `data/arbitration_eval.json`; seed 20260917, B 1000.

### 18a. The registered clauses

| clause | result | verdict | response (11e) |
|---|---|---|---|
| C1' | served chain window MAE $2.088M against `clemens_2026` $8.336M (gain $6.248M, MDE95 $1.020M, 6.13x) and the fitted ladder $5.409M (gain $3.321M, MDE95 $0.873M, 3.80x); 286 paired of 291, 5 dropped | PASS | - |
| C2' | 193 realized 2026 awards: path MdAPE 0.1552 equals the board's own 0.1552 (the same figure by construction, see 18b); signed median residual -0.0255 | PASS | - |
| C3' | repaired pool n 808, ours 0.1780 against Swartz 0.0769; frozen pool n 262, ours 0.1735 against 0.0815; both under 0.216 | PASS | - |
| C4' | 221 rows move by more than $1M; 128 carry a newly priced season and 93 do not, every one of the 93 moved by the tender cliff (a cut season); Spearman on the 1,046 rows whose path is unchanged 1.0000; whole-board Spearman 0.9249 (recorded) | FAIL | `"off"` |
| C5' | 0 cuts below 80% of the season before, contract junctions included | PASS | - |
| C6' | 0 prospect rows carry `salPath` | PASS | - |
| C7'a | 0 rows whose floor lowered the total (874 scored, 278 cut, $980.4M restored); 2 kept cuttable seasons with negative surplus | FAIL | `"closure"` (cliff off) |
| C7'b | backward induction never below forward; strictly greater on 119 rows | PASS | - |
| C8' | 81 grids, closure derives the held season's token on 73 (0.901) and its salary exactly where it does (MdAPE 0.000); the 8 misses are grids listing ARB 4 with no Super Two marker after ARB 3, where closure ends the window at ARB 3 | FAIL | `"ladder"` (closure off) |
| C9' | n 149 rows with current service time, 1 off by one season, 0 off by more | PASS | - |

Three clauses fail. The modes nest (`off` < `ladder` < `closure` < `full`),
so the registered responses resolve to the lowest one named: **`"off"`**,
which the block records as `registered_response_mode`. Section 11e: "a
failure does not withhold a ship. It reverts one." Section 18c records why
that revert is not applied in this task and goes to the owner.

What the three failures are, read without upgrading or excusing them:

- **C4'** fails on the tender cliff, which the same change shipped. Its
  criterion reads "every row moving by more than $1M must have at least one
  newly priced season", and a row the cliff cuts moves with none. No row
  moved without either a new season or a cut, so nothing points at an
  implementation defect; the clause as registered still fails.
- **C7'a** fails on its second half, the conflict the lab published before
  scoring: backward induction keeps a negative season when a later one pays
  for it (R1), and 2 rows do.
- **C8'** fails on evidence: 8 Spotrac grids carry an ARB 4 season after a
  plain ARB 3, and closure, which reads a non-Super-Two class as ending at
  ARB 3, does not reproduce them. Either the grids omit the Super Two
  marker or closure ends those windows a season early; this clause cannot
  tell which, and C9' (1 row off by one of 149) does not settle it.

### 18b. Deviations added after registration, published beside it

These are the shapes `tools/arb_path_gate.py` gave the clauses on
2026-09-17, after section 11d was registered. Each is in
`gate_c2.deviations_added_after_registration` and none enters a verdict.

- **C2' chain split.** The lab replaced the registered MdAPE half, which
  compares the board's 2026 figure with itself, with the raise estimator
  re-derived off each row's realized 2025 salary against a frozen 0.171:
  0.1605 on 86 arb-2-and-later rows (124 skipped for no prior), PASS; level
  half -0.0255, PASS.
- **C4' lab shape.** Counts rows with an arbitration season (675) and
  contract-only rows (199) without a pre/post comparison: PASS.
- **C5' with contract junctions counted apart**: 0 violations, 0 unrepaired
  junctions, PASS.
- **C7'a on its first half only**: PASS, with the same count of 2 published.
- **C10'**, the star-tail clause the lab added: served ARB 1 rungs reach
  $11.673M against a realized arb-1 p90 of $4.200M (n 235 served, 421
  realized), PASS. It is published at the top level and is not one of
  section 11d's clauses.

The 2026-08-19 C1 lab was a scratchpad file; C1' runs the protocol text of
section 9b, implemented in `tools/arb_c1_window.py`. Its served-chain MAE on
the award frame ($2.185M on 286 players) reproduces the 2026-08-19 $2.215M;
the `clemens_2026` arm reads higher than its $4.927M because the value
framework's market prices moved with the fWAR label epoch.

`C2_CHAIN_MDAPE_BOUND` (0.171) was read off the History when its Ours column
was still in deflated dollars (fixed in this task, owner answer M11-4). It is
a registered constant and is not changed here.

### 18c. The registered response is NOT applied in this task, and why

Section 11e makes the revert mechanical and section 11a says it "needs no
other edit". Both stopped being true after registration, and applying the
constant today would break two served things that have nothing to do with
the failing clauses:

1. **The Club Ledger cannot export an "off" payload.** `ledger_export`
   (shipped 2026-09-23) reconciles each club's served surplus against its
   salary-path rows and asserts the match; under `"off"` the projection rows
   carry no `salPath`, the first club reads $640.5M served against $0.0M of
   rows, and the export raises. The nightly would keep the last Ledger file
   and file a red, so the Ledger would go on printing full-mode figures
   beside an off-mode trade board.
2. **"off" also switches off the contract tail** (owner answer M05-01,
   2026-09-25), which rides the same flag (`mode != "off"` in
   `salary_path`). Measured on today's inputs, "off" moves 286 projection
   rows and $1,042.8M of veteran surplus ($12,515.5M to $11,472.7M), the
   trade board from $31,318.9M to $30,276.1M, and the largest single moves
   are contract-tail rows the gate never scored (Vladimir Guerrero Jr.
   -$108.0M to +$30.9M, Juan Soto $83.9M to $196.7M), beside the
   arbitration rows it did (Junior Caminero $295.3M to $175.6M).

So `SALARY_PATH_MODE` stays `"full"` and the decision goes to the owner
(11e: "Keeping a failed clause serving is the owner's call, and either way
the failure is published"). The failure is published: the `gate_c2` block
records `registered_response_mode: "off"`, the /arbitration/ Model tab shows
the gate as FAIL with the registered response beside the served mode, and
the registry row stays `provisional`, which C3' and these failures block
from leaving.

---

## 19. Section 13a amendment (registered 2026-10-09, before any 13a number exists): the award band from out-of-fold residual quantiles

Registered 2026-10-09, docs only, committed alone with its pin test
(`test_arb_band_calibration_registration.py`). Nothing above this section is
edited: section 13, including 13a's own text ("named here, registered later")
and 13b to 13f, stands exactly as it was committed in 8df1a091. This section is
the dated amendment 13a names. At this commit no producer, flag, column,
quantile, coverage reading or interval score of any band exists, and none has
been computed.

**Numbering.** The plan (master plan Part 8, row FAA-1; the lane design
`finance_to_fa_arb.md`, section 2.4) calls this part "12a". Section 13's map
applies: the plan's 12a is 13a, and this section registers it. A later task
that names "12a" or "13a" of this gate means this section.

**Preconditions, as they stood on 2026-10-09.** GATE C2 scored (section 18,
f6d2bb0d); the M11/M12 sequence committed (sections 15 to 18); the B5
known-season gate registered (section 14). ARB-CLUB-2 reads (c); its
point-award term and the section 4 amendment it needs are 13e, registered
before this section, and nothing here touches the point award.

### 19a. What is calibrated, and why

The award band is the low and high figure beside every projected arbitration
award: the /arbitration/ board's rungs (`arb_export.build_board`, the low and
high of each step in the `l` ladder), the Club Ledger ladder that prints them,
and the salary path's closure seasons (`salary_path.board_raise_fn`, served as
`surSalLo` and `surSalHi`). Today it is one fixed rule,
`point x (1 -/+ (0.22 + 0.08 x (step - 1)))` (arb_export.py @64bf1bb3 lines
251-258, in `build_board()`; `salary_path.BAND_BASE` and `BAND_STEP`), with its
low end floored at the league minimum since 3fcdd4ee (owner answer M12-4). Its
constants were set from the champion's observed MdAPE, and the code, the
glossary entry `arb_award_band` and the salary-path entry all say it is not a
calibrated interval and never a P10 or P90.

13b scales a calibrated band, so this part comes first. The quantity: a central
80% predictive band, P10 to P90, for the award at a rung, given what the board
knows at its vintage.

### 19b. Read to write this

The writer read this gate (sections 0 to 18), the band code above,
`arb_model.forward_chain`, `tools/arb_c1_window.py` (the served chain C1'
scores), and the accuracy this gate already publishes: the MdAPE by step in
sections 15f and 16e and the realized arb-1 p90 that C10' publishes (section
18b). A median absolute percentage error says something about a band's
central width, so this frame is not blind to point accuracy. No residual
quantile, coverage reading, tail rate or interval score of any band, fixed or
calibrated, was computed or read; `data/arbitration_eval.json` carries none.

### 19c. The residuals

- **Estimator.** The SERVED estimator as section 15d fixes it: the
  platform-frame champion at arb-1, the banded step multiplier at arb-2 and
  later. Not a candidate.
- **Pool.** `arb_dataset.scored_rows` on the platform frame (class years 2022
  to 2026 at registration), the pool GATE A scores.
- **Rung.** The arbitration trip, `arb_year`; a Super Two first trip is arb-1.
  Rung groups: arb-1, arb-2, arb-3 and later.
- **Chain depth.** The number of predicted rungs from the last observed salary
  to the rung, inclusive: depth 1 when the season before the rung carries an
  observed salary, depth d when the d - 1 rungs before it are themselves
  predictions. On the board and the salary path, depth counts from the
  vintage's last completed season, so the coming winter's award is depth 1.
  Depth groups: 1, 2, 3 and deeper.
- **The chain.** For a rung in season Y at depth d, start from the player's
  observed salary in season Y - d and walk the served chain forward the way
  `tools/arb_c1_window.served_window` does: each rung raises off the previous
  prediction, with the league-minimum floor on the point. Every arm (deflator,
  champion, banded multipliers) is fit on class years up to Y - d only, under
  the `forward_chain` rule (a train set of at least 60 rows, a test set of at
  least 15), so the chain knows what a board built after season Y - d knew. A
  chain needs the player's trips in consecutive seasons and the target's
  salary on file; anything else is dropped and counted.
- **A stated proxy.** The arb-1 champion reads platform production. Inside a
  backtest chain an arb-1 rung reads the REALIZED platform season, as C1'
  does; on the board an arb-1 rung at depth 2 or deeper reads a PROJECTED
  season (section 15d). The backtest cannot see the projection's error, so a
  calibrated band on those rungs is expected to cover less than measured. They
  are counted, flagged on the board row, and named in the copy, and no
  coverage is claimed for them.
- **Residual.** `log(actual / point)`, with the served point
  (smearing-corrected, league-minimum floored) and the actual put on the same
  fold deflator level, the board's last train level carried forward.
  Scale-free inside a row.

### 19d. The calibrated band

- **Quantiles, forward-chained.** For a test winter Y, each (rung group, depth
  group) cell takes the empirical 10th and 90th percentiles of the residuals
  whose target season is strictly before Y. A residual from winter Y never
  sets winter Y's band, and no later winter sets an earlier one.
- **Thin cells, fixed now, from counts alone.** A cell with fewer than 40
  training residuals for winter Y borrows the next shallower depth group of
  the same rung group; a short depth-1 cell borrows the depth-1 residuals of
  all rung groups pooled. Which cell borrowed for which winter is written to
  the artifact before any quantile is computed. The depth 3 and deeper group
  serves every deeper rung; depths past 3 are not scored.
- **Band.** `low = point x exp(q10)` and `high = point x exp(q90)`, then
  `low = min(low, point)` and `high = max(high, point)`, so the band always
  holds the served point.
- **The M12-4 floor on both bands.** The calibrated band and the fixed control
  are each floored at the season's league minimum, in scoring and in serving,
  so neither is credited for a range no club may pay. In serving the floor
  holds on both printed bands, the board's and the salary path's. No other
  floor or cap is added; the CBA maximum cut stays a rule on the point
  (section 17), not a band edge.
- **What serves, if it ships.** One function in `arb_model` builds the
  quantile table. The lab scores it, `arb_export` and `salary_path` both read
  it, and a test pins the served table's hash to the artifact's (the lab and
  the export import one builder). Served quantiles come from every residual
  through the latest class year, under the same thin-cell rule.

### 19e. Metric, power and floors

- **Metric: the interval score** of the central 80% band (alpha = 0.20: the
  width plus 2/alpha times each miss), in deflated dollars, paired against
  today's fixed band (the control, M12-4 floored) on identical rows and
  identical points. 13b uses the same metric.
- **Guardrail.** Dollar interval score is owned by the largest awards, so the
  scale-free form (each row's interval score over its point) is reported too,
  and the calibrated band must not lose on it by more than 10% relative,
  section 3's guardrail form.
- **Scored winters.** 2024, 2025 and 2026 at depth 1 (2023 has no earlier
  residual to set its band), 2025 and 2026 at depth 2, 2026 at depth 3. This
  departs from section 3's ">= 4 independent splits", disclosed here: the arms
  keep their four forward splits and the quantile step adds one lag. A
  leave-one-winter-out quantile would let a later winter's error set an
  earlier winter's band, the look-ahead section 15 removed from the award.
- **Power precondition, written first.** The scored rungs, all cells, must
  number at least 246 before any residual is read: the count at which the 95%
  binomial half-width of a coverage reading at 0.80,
  1.96 x sqrt(0.80 x 0.20 / n), reaches 0.05 (n = 245.9, rounded up). The
  count reads presence only. Short of 246, 13a is a pre-committed NULL.
- **Floors, under section 3's conventions.** A paired bootstrap clustered on
  PLAYER, resampling train and test with a refit on every draw (deflator,
  arms, chains, residuals, quantiles), B = 1000, seed 20261009; the one-sided
  MDE95 (1.645 sd) of the paired contrast; the two-sided coverage check on the
  floor estimator itself, n_check >= 200; and a detection check: residuals
  drawn from the cells' own residuals, resampled by player, with the
  control's half-widths scaled until its expected interval score exceeds the
  calibrated band's by the MDE95. The procedure must detect that planted gap on
  at least 80% of the n_check draws, or the instrument is dead and the result
  is a NULL.
- **Frame frozen before scoring.** The sorted (mlbam, season, depth) list of
  scored rungs and its sha256 go into the artifact before any residual is
  computed, with the dropped count and its causes, the way 14c freezes GATE
  K's frame.

### 19f. Pass rule

All four, or 13a is a NULL:

1. **Interval score.** The calibrated band beats the fixed band on mean
   interval score by more than the one-sided MDE95 of the paired contrast,
   and does not breach the scale-free guardrail.
2. **Coverage.** Pooled out-of-fold coverage of the scored rungs lies within
   0.05 of 0.80, and each tail's miss share (below the low end, above the
   high end) lies between 0.05 and 0.15.
3. **No rung group pays for the pool.** Every rung group with at least 62
   scored rungs (the 13b count) has coverage within 0.10 of 0.80 and does not
   lose on mean interval score by more than its own one-sided MDE95. Smaller
   groups and every (rung, depth) cell are reported with their n and not
   gated.
4. **The instrument sees.** The detection check in 19e passes.

Reported beside the verdict, never a criterion: the fixed band's own coverage
and tail shares on the same rows, by cell; the borrowed cells; the proxy count
from 19c.

### 19g. The response

**PASS.** The calibrated band is built behind `ARB_BAND_CALIBRATED` (off by
default; off reproduces today's payloads byte for byte). A printed band digit
moves on the board, the Club Ledger ladder and the salary path's closure
seasons, so the flag flips only after the owner's answer, in one commit
carrying the flag, the regenerated artifacts, a registry row `arb_award_band`
and the rewritten glossary text (the `arb_award_band` entry and the
salary-path paragraph that says the band is not a calibrated interval, with
the measured coverage read from the artifact), naming every row that moves.
The point award and every `tot` do not move. For 13a's words "does not ship":
13a ships when its verdict is PASS and the flag is on.

**NULL.** The fixed band keeps serving and the copy keeps saying it is not a
calibrated interval. Recorded verbatim: *"The calibrated award band is a NULL.
Out-of-fold residual quantiles by rung and chain depth did not price
arbitration awards better than the fixed band by more than the measured
floor, or missed the 0.80 coverage target, or the frame held fewer than 246
scoreable rungs. The band stays the fixed spread and is not a calibrated
interval."* Under 13a, 13b is then recorded `NOT SCORED`. The fixed band's
measured coverage may be quoted beside it, read from the artifact only.

### 19h. What never moves

The champion and its tuple (`arb_model.CHAMPION_KEYS`), `projectable_keys`,
the banded multipliers, the deflator, every point award, every `tot`, every
surplus point figure, and section 13 itself. No club-process key enters this
band: club process reaches the band only through 13b, after this part ships.
Section 8's sentence on the CBA's 2026-12-01 expiry stands: the calibrated
band covers the model's error on past winters, not a change of the rules.

### 19i. The look order

1. This amendment (2026-10-09), committed alone with its pin test.
2. The producer `tools/arb_band_calibration.py`, the shared quantile function
   in `arb_model`, and `test_arb_band_calibration.py` pinning this section's
   criteria verbatim, committed before the run; a dry run on fixtures with
   null residuals exercises the whole reporting path.
3. The frame frozen and counted (19e): row list, sha256, drops, borrowed
   cells. Short of 246 scored rungs, the NULL is recorded without reading a
   residual.
4. The one look: the floors first (MDE95, the coverage check, the detection
   check), then the contrast and the coverage, written once to a
   `band_calibration` block in `data/arbitration_eval.json`, with stdout and
   stderr teed before anything else runs. Never on a registered look day. A
   re-score after the read is a new dated registration.
5. The response (19g) committed; on PASS the flag is built off and flips only
   on the owner's answer.

Timing against section 13: steps 2 to 5 run before the January 2027
exchange-day capture (13d step 5). If they slip, they still run before 13b's
look, and whether 13a has shipped at that look decides 13b exactly as 13a
says.

### 19j. Results

Empty at registration. No residual, quantile, coverage reading or interval
score has been computed.
