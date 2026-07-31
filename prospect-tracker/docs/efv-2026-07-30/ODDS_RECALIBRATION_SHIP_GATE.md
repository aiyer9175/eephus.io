# Wiring the odds recalibration: re-fit and re-measure on the current tree

Lane: LANE-ODDS-SHIP. Owner decision 2026-07-30: **re-fit and re-measure on the CURRENT
tree first, then wire it.**

Gate standard: `docs/EFV_GATE_STANDARD.md` (all four section-2 controls are mandatory).
Predecessors:
* `docs/efv-2026-07-30/ODDS_GRADE_BASIS_GATE.md` section 2.11(b) and 2.12(2), which named
  the re-link as the real lever and costed it at roughly 1.5x the whole re-key question.
* the 2026-07-25 odds-dispersion lane: `efv_odds_calibration.py`, `tools/_prem_odds*.py`,
  `data/xfv_odds_dispersion_eval.json`, and the unapplied patch `tools/_prem_odds.patch`.

Lab: `tools/odds_recalibration_ship_lab.py`. Artifact:
`data/xfv_odds_recalibration_ship_eval.json`. Registry row: `xfv_odds_recalibration_ship`.

**PART 1 WAS WRITTEN AND COMMITTED TO DISK BEFORE ANY FIT WAS RUN.** PART 2 is appended
after. PART 3 records the wiring and its measured blast radius, and exists only if PART 2
returns a SHIP.

---

# PART 1. Pre-registration

## 1.0 Why re-verification is mandatory and not ceremony

`efv_odds_calibration.py` has been on the tree since 2026-07-25 and **nothing imports it**.
Its two per-side constants were fitted on a tree that has since moved underneath them:

1. LANE-P2 re-scaled the board grade (`realized_implied_fv` -> `outcome_implied_fv`) on
   2026-07-30. The odds seam itself was deliberately PINNED to `realized_implied_fv` by
   the basis gate, so the map's ARGUMENT is nominally unchanged - but that is a claim to
   verify, not to assume.
2. The eFV matrices have been regenerated repeatedly since (the nightly box is rewriting
   `data/` right now). `xfv_war` comes out of a refit ridge plus a refit linear
   calibration on those matrices, so the p_bust input DISTRIBUTION moves whenever they do,
   even with the key held fixed.

A calibration fitted on a stale input scale is exactly the failure mode this program has
been correcting all week. So the constants are re-derived from scratch here, and the
incumbent's published values are treated as a provenance check, not as an input.

## 1.1 The question

Does a forward-chained monotone Platt recalibration of the served eFV `p_bust`, re-fitted
on the tree as it stands today, beat BOTH the incumbent uncalibrated `p_bust` AND a flat
base-rate constant, on Brier and on log loss, out of fold?

## 1.2 WHICH QUANTITY IS RECALIBRATED (declared in advance)

**`p_bust` ONLY.**

The four non-bust buckets are rescaled proportionally by `(1 - p_bust') / (1 - p_bust)` so
the five-vector still sums to 1. That is `efv_odds_calibration.recalibrate_bucket`'s
existing convention and it matches `efv_ungraded.thin_sample_p_bust`'s, so the two lanes
describe `p_bucket` the same way. Consequences, stated now:

* `p_bucket['star']` MOVES, but only as a proportional rescale of the non-bust mass. It is
  NOT independently recalibrated and no separate star map is fitted.
* The reason is power, and it is the basis gate's own pre-registered finding: the resolved
  out-of-fold frame carries **9 hitter stars and 2 pitcher stars**. A star-specific Platt
  map would be fitted on 11 events. It is not measurable, so it is not built.
* The sum-to-1 property is algebraic (`p' + (1-p')/(1-p) * (1-p) = 1`), but it will be
  PROVEN numerically on every served row in PART 3 rather than asserted, to floating-point
  tolerance 1e-9, and renormalized if any row fails.

## 1.3 The frame

Identical to the basis gate's, which is identical to the 2026-07-25 odds lane's.

**Pool.** `data/xfv_hitter_matrix.json` / `data/xfv_pitcher_matrix.json`, minus rows with
`kind == "bust" and bust_recent`, prepped through `efv_model._prep(pool, "target_censored",
side)` so training matches `efv_score.run` row for row.

**Test restriction.** `censored is False` and `target_resolved` numeric.

**Folds.** Forward-chained on `efv_model._decision_year`, decision years **2014-2020**,
seven folds, each trained strictly on `decision_year < fold`. 2021+ is excluded because the
six-season window has not closed there and every resolved row is a bust by construction
(base rate 1.000, which cannot test a probability); 2011-2013 does not carry enough prior
rows to fit the chain.

**Label.** The shipped bust event, unchanged: first-6yr TOTAL bWAR / 6 < 0.5, i.e.
`target_resolved < 3.0` (`value_framework_config.yaml:38`, `tools/_prem_odds.py:41`).

## 1.4 The cuts, and which one is the APPLIED population

The production guard in `tools/_prem_odds.patch` is `provisional=not src.get("milb")`, so
the recalibration reaches only rows that carry a MiLB feature block. Measured on today's
matrices, that guard is almost exactly the served-comparable (track-record) cut:

| side | pool | `milb` truthy | `rates_missing == 0` |
|---|---|---|---|
| hit | 1,882 | 907 | 906 |
| pit | 1,988 | 920 | 920 |

So the **served-comparable cut is the APPLIED population**, not a secondary curiosity, and
it is gated as such below. Cuts reported: `hit`, `pit`, `pooled` (primary frame, all
resolved rows) and `hit_served`, `pit_served`, `pooled_served` (the applied population).
A `no_track` cut is reported for information: it is the population the guard EXCLUDES, and
it exists to show what is being left uncorrected.

## 1.5 The arms

Every arm scores the SAME out-of-fold `xfv_war` from the SAME refit chain
(`_fit_ridge` -> `_fit_linear_calibration` -> `xfv_war = max(-2, a + b*raw)`), keyed
through `p_bucket_given_fv(realized_implied_fv(...))` exactly as `efv_score.py:1188-1196`
does. Only the post-map differs.

| arm | probability |
|---|---|
| **INC (incumbent)** | `p_bucket_given_fv(realized_implied_fv(xfv_war, is_pit, age=_grade_map_age(age_at_debut, 0.0), position=pos, exposure_seasons=6))[bust]`, verbatim |
| **CAL (candidate)** | INC through a forward-chained Platt map in logit space, `logit(p') = a + b*logit(p)`, fit by IRLS on the out-of-fold rows of decision years STRICTLY BEFORE the test fold, **and fit within the cut's own population** so the served arm reproduces production exactly |
| **CONST (zero-info)** | a constant at the base rate of the same cut's prior folds (the honest climatology available at decision time for THAT population) |
| **CONST_all** | the basis gate's arm C: the fold's full resolved-training base rate, reported alongside |

**The constant is deliberately fitted WITHIN the cut.** On the served-comparable population
the bust base rate is far below the full frame's, so scoring the served cut against the
full frame's 0.86 constant would hand the candidate a free win against a strawman. The
gate uses the within-cut constant, which is the stronger baseline.

Fold 2014 is the first fold and has no prior out-of-fold rows to fit a Platt map on. CAL
falls back to INC unchanged there, and CONST falls back to `CONST_all`. This is recorded,
not hidden: it makes fold 2014 a tie by construction and therefore costs the candidate.

## 1.6 The metrics

Per arm, per cut, AND per fold: **Brier**, **log loss** (natural log, clipped to
[1e-6, 1-1e-6]), **ECE** (ten equal-count bins), the **Murphy decomposition**
(`Brier = reliability - resolution + uncertainty`), **calibration slope and intercept**
(`y ~ a + b*logit(p)` by IRLS; perfect is `(0, 1)`), **calibration-in-the-large**
(`mean(p) - mean(y)`), the **reliability curve** with Wilson intervals, and **AUC**.

AUC is secondary and diagnostic. A per-fold Platt map is globally non-monotone across
folds, so CAL's AUC is not guaranteed to equal INC's; the proper scores are the quantities
of interest. The SHIPPED map is a single global monotone transform per side and DOES
preserve AUC and every ranking exactly - that is verified separately in PART 3.

## 1.7 The controls (gate standard section 2, all four)

1. **Paired bootstrap resampling TRAIN AND TEST with a full refit on every draw.** Clusters
   are `player_key`. Each draw resamples the prepped pool with replacement at the player
   level, re-runs the entire seven-fold chain (`_fit_ridge` + `_fit_linear_calibration` +
   `_fit_ols_fv`) on the resampled training rows, re-scores the resampled test rows,
   **re-fits the forward-chained Platt maps on the resampled rows**, and records the paired
   deltas. B = 1000, seeded. A test-only bootstrap is reported beside it only to document
   the understatement factor; it is not the gate.
2. **Zero-information control**: arm CONST, reported beside every claim, and it is half of
   the ship criterion rather than a footnote.
3. **Permutation null band**: 1000 draws with the LABEL permuted within fold. This control
   is load-bearing here in a way it was not for the re-key. A Platt map SHRINKS toward the
   base rate, and under random labels a shrunk forecast beats a sharp one automatically, so
   `metric(INC) - metric(CAL)` has a POSITIVE null. An observed delta inside that band is a
   null no matter what its bootstrap CI says. The `CONST - CAL` delta has the mirror
   property: its null is NEGATIVE, because under random labels the constant is optimal.
4. **Per-split values** for every headline number, all seven folds.

## 1.8 THE SHIP CRITERION (fixed here, not alterable afterwards)

The recalibration is WIRED only if ALL of the following hold. `d = metric(baseline) -
metric(CAL)`; POSITIVE means the recalibration is better.

1. **Beats the INCUMBENT** on Brier AND log loss, with the paired player-clustered
   refit-every-draw bootstrap CI95 of `d` EXCLUDING ZERO, on the **pooled** cut; and
2. **Beats the flat within-cut base-rate CONSTANT** on Brier AND log loss, with the same
   CI95 excluding zero, on the **pooled** cut; and
3. both 1 and 2 also hold on **`pooled_served`**, the population the guard actually applies
   the map to. A map that wins only on rows it will never touch is not a ship.
4. Both observed deltas sit OUTSIDE their permutation null bands, in the correct direction.

**If it beats the incumbent but NOT the constant, that is a NULL and it is not wired.**
That is the owner's instruction and it is restated here so it cannot be softened later:
the 2026-07-25 lane's own headline was only ever "incumbent - recalibrated", and the basis
gate then showed that BOTH keyings lose to a constant. Beating a broken incumbent is not
evidence of a good forecast.

Two further pre-registered rules:

5. **Sides are reported separately and a side that regresses is reported as a regression**,
   even if the pooled cut passes. Criterion 1-3 are pooled by the owner's wording, so a
   single-side regression does not by itself block the ship, but it is disclosed in the
   headline rather than buried.
6. **The shipped constants must come from the same protocol as the measurement.** The
   production map is a single global per-side fit (it has to be: production scores one row
   at a time with no fold to belong to). The gate measures a forward-chained fit. The
   global fit is therefore reported WITH its per-fold trajectory, and if the per-fold
   slopes trend away from the global value the global value is taken from the
   CONSERVATIVE end of the measured range - the same rule the 2026-07-25 lane applied.

## 1.9 The blast radius that will be measured if it ships

Pre-declared so the measurement cannot be scoped to flatter the result:

* served rows whose `p_bust` moves >= 0.10, by side, with the direction and the extremes;
* the named players this program tracks, before and after;
* every downstream consumer that keys off a p_bust THRESHOLD, enumerated from a repo-wide
  search, with the count crossing each threshold:
  - `assets/trademachine.js:628,814` colour bands at `pb >= 0.25` and `pb <= 0.10`;
  - `prospx/index.html:32530` colour band at `x.p_bust >= 0.4`;
  - `fantasy_export.py:448` composite `- 6*p_bust + 10*p_bucket['star']`, which is NOT a
    threshold but IS a served ORDERING, so the fantasy rank churn is measured;
  - `bayes_trade_value.py:4002,4136` (`_sortino_fields`), where p_bust is carried but does
    not enter `sortino`, `risk_mm` or `downside_mm` - to be confirmed, not assumed;
  - `prospx` sort keys `surplus_pbust` - a monotone map cannot reorder them, to be
    confirmed;
* whether the board ORDER moves. It must not: the map is strictly monotone and every
  dollar figure, grade and rank is computed independently of `probs`.
* whether `BOARD_BASIS_FINGERPRINT` / `BOARD_RANK_BASIS_EPOCH` need to move. The odds are
  a board-visible number but not a board-ordering input, so the expectation is NO - and
  that is CONFIRMED by measurement in PART 3, not assumed.

## 1.10 What this lane will NOT do

It will not run pytest, any exporter, `run_monthly`, `build_site`, a scraper or a matrix
rebuild; it will not `git add` a `data/` path it did not create; it will not touch
`efv_ungraded`'s provisional rows or the consensus-keyed p_bust readers (the trade machine
engine, `/projections/`, the FA surfaces), whose scope limit `efv_odds_calibration`'s
docstring already records; and it will not fit a star map.

---

# PART 2. Results

*(Appended after the measurement. Everything above this line was on disk first.)*

Artifact: `data/xfv_odds_recalibration_ship_eval.json`. Lab runtime 283.5s, B = 1000
bootstrap draws with a full refit of the ridge, the linear calibration, the consensus OLS
AND the forward-chained Platt maps on every draw; B = 1000 permutation draws.

## 2.0 VERDICT: NULL. NOT WIRED.

The recalibration beats the incumbent overwhelmingly and does not beat a flat base rate.
That is the exact case the owner named in advance, and the answer is the one that was
pre-registered for it: do not wire it.

* **Criterion 1 PASSES, decisively.** Pooled Brier d = +0.03114 CI95 [+0.01894, +0.04641],
  log loss d = +0.09295 CI95 [+0.05631, +0.13530], P(recalibrated better) = 1.000 on both.
  Every cut in the lane, including both sides separately and the served cut, has the
  recalibration ahead of the incumbent with the CI excluding zero.
* **Criterion 2 FAILS on every cut.** Pooled Brier d = +0.01021 CI95 [-0.00223, +0.02290]
  P = 0.933; log loss d = +0.02967 CI95 [-0.01286, +0.06781] P = 0.916. The point estimates
  favour the recalibration; the intervals do not exclude zero.
* **Criterion 3 FAILS worse, and this is the one that matters.** On `pooled_served`, the
  population the production guard would actually apply the map to, Brier
  d = +0.02447 CI95 [-0.01335, +0.06228] P = 0.890 and log loss
  d = +0.00372 CI95 [-0.12097, +0.11434] **P = 0.544**. On log loss, against a constant, on
  the rows it would touch, it is a coin flip.
* **Criterion 4** is reported in 2.6 and is DEGENERATE against the incumbent by
  construction. It is not what decides this.

## 2.1 Provenance: the module was NOT stale

This was the stated reason re-verification was mandatory, so it is answered first.
Re-fitting from scratch on today's matrices, on the same served-comparable frame the
2026-07-25 lane used, reproduces its published constants:

| side | 2026-07-25 shipped `_PLATT` | re-fit today, same frame | n |
|---|---|---|---|
| hit | (0.7268, 0.3749) | (0.7371, **0.3749**) | 244 |
| pit | (0.7269, 0.3553) | (0.7531, 0.3591) | 272 |

The slope, which is the whole mechanism (a 2.7x over-steep curve), comes back identical to
four decimals on hitters and within 0.004 on pitchers. **The input distribution did not
move underneath the module.** That is the expected result once you notice that the odds
seam was PINNED to `realized_implied_fv` by the basis gate, so LANE-P2's re-scale never
reached this map's argument; but it was a claim to check, and it checked out. The
re-verification is therefore not what killed this. What killed it is the second baseline,
which the 2026-07-25 lane never ran.

Fitted on other frames, for the record: hit `all` (1.4955, 0.5242) n = 923, hit `no_track`
(1.9599, 0.5067) n = 679; pit `all` (1.3267, 0.7117) n = 1,002, pit `no_track`
(1.5195, 1.1419) n = 730. The slope rises steadily as the frame moves away from the served
population, which is itself a warning that one global map would be doing different work on
different sub-populations.

## 2.2 The frame as built

| | hit | pit | pooled |
|---|---|---|---|
| resolved out-of-fold rows, decision years 2014-2020 | 923 | 1,002 | 1,925 |
| bust base rate | 0.8397 | 0.8782 | 0.8597 |
| served-comparable (the APPLIED population) | 244 | 272 | 516 |
| served-comparable bust base rate | 0.6230 | 0.7353 | 0.6822 |
| excluded by the guard (no track record) | 679 | 730 | 1,409 |

## 2.3 The three arms

| cut | arm | Brier | log loss | ECE | reliability | resolution | cal slope | cal intercept | mean p - obs | AUC |
|---|---|---|---|---|---|---|---|---|---|---|
| hit | INC | 0.16048 | 0.52616 | 0.1962 | 0.0674 | 0.0395 | 0.524 | 1.496 | -0.1686 | 0.8193 |
| hit | CAL | 0.12571 | 0.41708 | 0.0930 | 0.0182 | 0.0286 | 0.571 | 0.865 | -0.0467 | 0.7811 |
| hit | CONST | 0.14252 | 0.45834 | 0.1410 | 0.0234 | 0.0162 | 1.280 | 0.543 | -0.0687 | 0.5531 |
| pit | INC | 0.12267 | 0.40076 | 0.1538 | 0.0334 | 0.0177 | 0.712 | 1.327 | -0.1393 | 0.7828 |
| pit | CAL | 0.10145 | 0.34324 | 0.0599 | 0.0077 | 0.0127 | 0.668 | 0.735 | -0.0273 | 0.7508 |
| pit | CONST | 0.11103 | 0.38177 | 0.0900 | 0.0103 | 0.0084 | 1.144 | 0.949 | -0.0534 | 0.5560 |
| **pooled** | **INC** | **0.14080** | **0.46088** | 0.1747 | 0.0483 | 0.0273 | 0.567 | 1.458 | -0.1533 | 0.7967 |
| **pooled** | **CAL** | **0.11308** | **0.37864** | 0.0678 | 0.0113 | 0.0178 | 0.609 | 0.824 | -0.0366 | 0.7675 |
| **pooled** | **CONST** | **0.12637** | **0.41966** | 0.0738 | 0.0085 | 0.0036 | 1.218 | 0.740 | -0.0613 | 0.5608 |
| pooled_served | INC | 0.23196 | 0.73794 | 0.2096 | 0.0535 | 0.0392 | 0.370 | 0.741 | -0.1414 | 0.7386 |
| pooled_served | CAL | 0.20277 | 0.63595 | 0.0859 | 0.0127 | 0.0300 | 0.438 | 0.592 | -0.0684 | 0.7149 |
| pooled_served | CONST | 0.23292 | 0.65975 | 0.1384 | 0.0295 | 0.0157 | 0.415 | 0.663 | -0.1187 | 0.5907 |
| pooled_no_track | INC | 0.10742 | 0.35942 | 0.1678 | 0.0498 | 0.0084 | 0.618 | 1.909 | -0.1577 | 0.7862 |
| pooled_no_track | CAL | 0.08292 | 0.29288 | 0.0928 | 0.0225 | 0.0065 | 0.569 | 1.591 | -0.0856 | 0.7831 |
| pooled_no_track | **CONST** | **0.07874** | **0.29292** | 0.1148 | 0.0154 | 0.0081 | 1.181 | 1.035 | -0.1246 | 0.7894 |

The pooled `CAL` row reproduces the basis gate's independently built F arm (Brier 0.11308,
log loss 0.37864) exactly, which is the second provenance check.

Read the last block. **On the population the guard EXCLUDES, the constant beats the
recalibration outright.** The guard is doing real work, and it was not put there for this
reason.

## 2.4 The paired, player-clustered, refit-every-draw bootstrap (B = 1000)

`d = metric(baseline) - metric(CAL)`. POSITIVE means the recalibration is better.

| cut | baseline | metric | d | CI95 | P(CAL better) |
|---|---|---|---|---|---|
| hit | incumbent | Brier | +0.03907 | [+0.02016, +0.06077] | 1.000 |
| hit | incumbent | log loss | +0.12471 | [+0.06949, +0.18732] | 1.000 |
| hit | **constant** | Brier | +0.01447 | [-0.00851, +0.03677] | 0.883 |
| hit | **constant** | log loss | +0.03373 | [-0.04113, +0.10189] | 0.816 |
| pit | incumbent | Brier | +0.02384 | [+0.00732, +0.04743] | 1.000 |
| pit | incumbent | log loss | +0.06372 | [+0.01885, +0.12227] | 0.993 |
| pit | **constant** | Brier | +0.00629 | [-0.00640, +0.01975] | 0.833 |
| pit | **constant** | log loss | +0.02511 | [-0.01575, +0.06392] | 0.899 |
| **pooled** | incumbent | Brier | **+0.03114** | **[+0.01894, +0.04641]** | **1.000** |
| **pooled** | incumbent | log loss | **+0.09295** | **[+0.05631, +0.13530]** | **1.000** |
| **pooled** | **constant** | **Brier** | **+0.01021** | **[-0.00223, +0.02290]** | **0.933** |
| **pooled** | **constant** | **log loss** | **+0.02967** | **[-0.01286, +0.06781]** | **0.916** |
| **pooled_served** | incumbent | Brier | +0.03104 | [+0.00961, +0.05356] | 0.998 |
| **pooled_served** | incumbent | log loss | +0.12439 | [+0.03706, +0.21104] | 0.990 |
| **pooled_served** | **constant** | **Brier** | **+0.02447** | **[-0.01335, +0.06228]** | **0.890** |
| **pooled_served** | **constant** | **log loss** | **+0.00372** | **[-0.12097, +0.11434]** | **0.544** |
| pooled_no_track | **constant** | Brier | -0.00534 | [-0.01742, +0.00742] | 0.212 |
| pooled_no_track | **constant** | log loss | -0.00897 | [-0.05712, +0.03517] | 0.370 |

The test-only bootstrap understates sd by 1.32x to 2.37x, at or above the 1.6-1.8x the gate
standard cites on the cuts that matter. Reported as a diagnostic only.

## 2.5 Per split (gate standard 2.4)

Pooled cut, `d = metric(baseline) - metric(CAL)`:

| fold | n | base rate | Platt fitted | d_inc Brier | d_inc log loss | d_const Brier | d_const log loss |
|---|---|---|---|---|---|---|---|
| 2014 | 185 | 0.789 | NO | 0.0000 | 0.0000 | **-0.0992** | **-0.3576** |
| 2015 | 173 | 0.734 | yes | -0.0215 | -0.0368 | +0.0095 | +0.0257 |
| 2016 | 213 | 0.845 | yes | +0.0045 | +0.0297 | +0.0473 | +0.1341 |
| 2017 | 199 | 0.899 | yes | +0.0502 | +0.1528 | +0.0286 | +0.0899 |
| 2018 | 389 | 0.918 | yes | +0.0643 | +0.1736 | +0.0164 | +0.0595 |
| 2019 | 393 | 0.863 | yes | +0.0378 | +0.1036 | +0.0213 | +0.0603 |
| 2020 | 373 | 0.877 | yes | +0.0169 | +0.0529 | +0.0316 | +0.1270 |

Fold 2014 carries no Platt map (no prior out-of-fold rows), so CAL ties the incumbent there
and loses heavily to the constant. That was pre-registered in 1.5 as a cost to the
candidate. Section 2.7 prices exactly how much it costs and shows the verdict survives
without it.

Served cut, where the first fitted fold is 2018:

| fold | n | base rate | Platt fitted | d_const Brier | d_const log loss |
|---|---|---|---|---|---|
| 2016 | 21 | 0.333 | NO | +0.1434 | +0.1680 |
| 2017 | 56 | 0.661 | NO | +0.0025 | **-0.1963** |
| 2018 | 83 | 0.651 | yes | +0.0090 | **-0.0973** |
| 2019 | 161 | 0.671 | yes | +0.0232 | +0.0502 |
| 2020 | 189 | 0.767 | yes | +0.0493 | +0.1183 |

The served log-loss comparison against the constant is not merely wide, it changes SIGN
fold to fold, including on a fitted fold. That is the honest picture behind P = 0.544.

## 2.6 The permutation null, and why it is degenerate against the incumbent

Labels permuted within fold, all three forecasts held fixed. B = 1000.

| cut | comparison | metric | observed d | null band95 | reading |
|---|---|---|---|---|---|
| pooled | vs incumbent | Brier | +0.0277 | [+0.0685, +0.0783] | observed BELOW the null |
| pooled | vs incumbent | log loss | +0.0822 | [+0.2114, +0.2463] | observed BELOW the null |
| pooled | **vs constant** | Brier | **+0.0133** | **[-0.0283, -0.0192]** | **observed ABOVE, correct side** |
| pooled | **vs constant** | log loss | **+0.0410** | **[-0.1098, -0.0727]** | **observed ABOVE, correct side** |
| pooled_served | vs constant | Brier | +0.0363 | [-0.0330, -0.0024] | above, correct side |
| pooled_served | vs constant | log loss | +0.0370 | [-0.1797, -0.0672] | above, correct side |

**The incumbent comparison's null is POSITIVE and LARGER than the observed delta**, exactly
as 1.7.3 predicted. That is not evidence against the recalibration; it is a degenerate
control. A Platt map is pure shrinkage toward the base rate, and under labels that carry no
information a base-rate-shrunk forecast beats a sharp one automatically. The control asks
"does this map add INFORMATION"; the map provably does not add information (it is monotone,
and its whole purpose is calibration), so the control cannot answer the question it was
pointed at.

**That is a mis-specification in PART 1's own criterion 4, and it is recorded here rather
than quietly dropped.** The criterion is left as written; it simply is not what decides the
lane, because criterion 2 already fails on its own terms. The CONSTANT comparison's
permutation null is the well-posed one (negative null, positive observed, correct side on
every cut), and it says the recalibration does carry real information relative to
climatology. It just does not carry enough of it, on the population it would touch, to
clear a 95% interval.

## 2.7 Post-hoc sensitivity: is the NULL an artifact of the unfitted first fold?

**No.** Production has no unfitted fold: it would carry one map fitted on all history.
Restricting to folds where a Platt map was actually fitted is therefore the friendliest
frame the candidate can ask for. It is POST-HOC, it is not part of the criterion, and it is
run because if the verdict flipped on it that would be worth knowing.

| cut | n | comparison | metric | d | CI95 | P |
|---|---|---|---|---|---|---|
| pooled | 1,740 | vs constant | Brier | +0.02131 | [+0.01167, +0.03103] | 1.000 |
| pooled | 1,740 | vs constant | log loss | +0.06811 | [+0.03713, +0.09865] | 0.999 |
| **pooled_served** | **433** | **vs constant** | **Brier** | **+0.01954** | **[-0.00581, +0.04372]** | **0.943** |
| **pooled_served** | **433** | **vs constant** | **log loss** | **+0.03510** | **[-0.04906, +0.09606]** | **0.861** |

The pooled cut is rescued. **The applied population is not.** On the frame chosen to be as
kind as possible, the rows the production guard would hand this map to still do not beat a
flat base rate at the 95% bar, on either metric. The verdict stands and is not a fold-2014
artifact.

## 2.8 What was NOT wired, and what that leaves standing

`efv_score.py` is unchanged. `efv_odds_calibration.py` remains on the tree and remains
inert: no module imports it. `tools/_prem_odds.patch` remains unapplied. No served number
moved, the board did not move, and no epoch or fingerprint question arises, because nothing
shipped.

For completeness, since the pre-registration promised it and the answer belongs on the
record rather than in an assumption: **had it shipped, no epoch or fingerprint bump would
have been needed.** `storage.board_basis_fingerprint()`'s terms are the board GRADE basis,
the scale flag, the grade map and the role mode; `p_bust` and `p_bucket` are computed
downstream of `rank_war` and enter no ordering. `prospx`'s `surplus_pbust` sort key is the
one place p_bust orders anything, and a strictly monotone per-side map cannot reorder it.
That confirmation is worth keeping because it is the shape of the answer for any FUTURE
odds change, and the basis gate's third instance of the fingerprint lesson makes it worth
writing down rather than re-deriving under time pressure.

The blast radius that WOULD have moved, enumerated in 1.9 and left unmeasured because there
is nothing to measure: `fantasy_export.py:448`'s `-6*p_bust + 10*p_star` composite is the
only served ORDERING downstream of p_bust, and `assets/trademachine.js` (0.25 / 0.10) and
`prospx/index.html:32530` (0.40) are the only threshold consumers. `bayes_trade_value`'s
`_sortino_fields` carries p_bust but computes `sortino`, `risk_mm` and `downside_mm` from
the percentile fan alone, so no trade-value floor keys off it. Recorded so the next lane
does not have to re-find them.

## 2.9 What this actually means, and what would move it

The eFV odds are informative and miscalibrated, and both of those are now measured twice.
Murphy resolution 0.0273 against a constant's 0.0036 pooled, AUC 0.797 against 0.561: the
ranking is real. Reliability 0.0483 with a calibration slope of 0.567: the levels are not.

The 2026-07-25 lane's finding was correct as far as it went, and the basis gate's
recommendation to wire it was reasonable on the evidence then available. What neither had
was the second baseline. With it, the honest statement is:

> A monotone re-link of the served p_bust is a large improvement over the incumbent and is
> not distinguishable from climatology on the population it would be applied to.

The binding constraint is the size of the resolved served-comparable cohort: 516 rows, of
which 433 sit in a fold with a fitted map. That is not enough to establish a two-parameter
recalibration against a one-parameter baseline at 95%, even when the recalibration is
right. Two things would move it, and neither is a modelling choice:

1. **More resolved rows in the applied population.** The frame grows by roughly one decision
   year per year. At the observed effect size the served cut needs somewhere near double its
   current n to clear the interval.
2. **A forecast with more resolution.** Recalibration cannot manufacture information; it can
   only stop existing information being expressed at the wrong level. The gap between
   resolution 0.030 and a constant's 0.016 on the served cut is the entire budget a re-link
   has to work with.

Re-opening this before either has changed would be re-running the same measurement.
