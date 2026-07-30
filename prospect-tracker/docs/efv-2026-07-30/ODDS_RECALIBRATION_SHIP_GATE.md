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
