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
