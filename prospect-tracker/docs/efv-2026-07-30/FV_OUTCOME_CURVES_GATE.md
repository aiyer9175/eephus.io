# Per-side FV-to-outcome curves: pre-registration and results

Lane: LANE-CURVES, Phase 1 only, of `docs/master-plan-2026-07-30-fv-calibration.md`.
Gate standard: `docs/EFV_GATE_STANDARD.md`. Lab: `tools/fv_outcome_curves_lab.py`.
Artifact: `data/fv_outcome_curves.json`. Registry row: `fv_outcome_curves`.

**Everything in PART 1 below was written and committed to disk BEFORE the first fit ran.**
PART 2 is appended after. Phase 2 (the actual grade re-scale) is out of this lane's scope;
this lane produces a curves artifact and a bake-off and changes no served number.

---

# PART 1. Pre-registration

## 1.0 What this lane is for

`value_framework.realized_implied_fv` inverts a SIDE-NEUTRAL expected-WAR map to produce
`xfv_grade`. Two measured facts motivate replacing it (plan section "The two measured
facts"): consensus FV is not cross-side comparable (`CROSS_SIDE_WAR_FINDING.md`), and the
served map is side-neutral to within 0.12 FV across the whole WAR range. This lane fits the
replacement per side and TESTS it against every published industry table rather than
adopting one.

## 1.1 Pool, target, and vintage

**Rows.** `data/xfv_scored.json` (hitters, 1,882 rows) + `data/xfv_scored_pitcher.json`
(pitchers, 1,988 rows), joined by `player_key` to `data/xfv_hitter_matrix.json` /
`data/xfv_pitcher_matrix.json` for the decision-year, censoring and weight columns. The join
is exact: 0 unmatched keys on either side, `player_key` is unique within each file (1,882 /
1,988 unique), and no key appears on both sides, so a player-clustered bootstrap is
arithmetically identical to a row bootstrap at this grain. That equality is asserted in the
lab rather than assumed.

**x = `consensus_fv`.** Verified identical to the matrix column `consensus_fv_raw` to 0.05 FV
on all 3,870 rows.

**y = `realized_war_6yr`.** Verified identical to the matrix column `target_censored` to
0.005 WAR on all 3,870 rows. This is the label `efv_score.run` scores
(`_prep(pool, "target_censored", side)`) and the label the sub-45 anchor amendment was
measured on, so the curves and the shipped anchors are on one basis.

**Vintage discipline.** `consensus_fv_raw` is the PRE-DEBUT anchor. Verified by reading the
producer, not by assertion: `efv_dataset._decision_rows` calls
`_asof_point(rec, dd)` with `dd` = the debut date, and `_asof_point` keeps only
`p["snapshot_date"] < cutoff` (strict inequality, `efv_dataset.py:278`). Never-MLB bust rows
pass `cutoff=None` and take the final list point, which is pre-outcome by construction
because the outcome is "never debuted". This is the discipline the disagreements-table defect
(`source_backtest._xfv_vs_consensus_detail`) violated by re-reading a post-debut vintage.
The lab re-asserts the strict-inequality property on a sample of rows and records the
verification in the artifact.

**Decision year** = `int(asof_date[:4])` from the matrix, the same definition
`tools/efv_board_scale_lab.py:50` uses. Range 2011-2024 (one 2026 pitcher row, dropped as a
degenerate fold member).

**Censoring.** PRIMARY pool = `censored == False` (1,500 hit / 1,537 pit), which is the pool
behind FACT 1. SENSITIVITY pool = all rows on `target_censored` with `weight` =
`observed_seasons / 6` (0.333-1.0), the production fit weighting. Both are fit and both are
reported. Censored rows are never silently dropped; the sensitivity is a first-class
deliverable and the artifact carries both curve sets.

## 1.2 Fitting method (declared before the fit)

1. **Monotone fit.** Weighted PAVA isotonic regression of y on x, per side, increasing.
   Isotonic rather than a constrained spline because the FV grid is quasi-discrete (the
   pooled multi-source consensus produces clusters at 35.0, 35.5, 38.0, 40.5, ... with a
   genuine data hole between 43.0 and 45.5) and a spline would interpolate across that hole
   with basis functions instead of with a stated prior.
2. **Knot grid.** FV 20, 25, 30, 35, 37.5, 40, 42.5, 45, 47.5, 50, 52.5, 55, 57.5, 60,
   62.5, 65, 67.5, 70, 75, 80. Curve value at each knot = the isotonic fit evaluated there.
3. **Cell n per knot** = the number of pool rows with `|consensus_fv - knot| <= 1.25`. This
   is the number reported, and the number the shrinkage rule reads. A knot with cell n
   under 30 is a SHRINKAGE CELL, not a measurement, and is labelled as such in the artifact.
4. **Shrinkage rule.** `w_prior(knot) = K / (K + n_cell)` with **K = 30**, so n_cell = 30 is
   exactly a 50/50 blend, n_cell = 300 is 9% prior, n_cell = 0 is 100% prior. Shrunk value
   = `(1 - w_prior) * isotonic + w_prior * prior`. The weight is recorded per knot in the
   artifact.
5. **The prior is the Clemens 2026 per-side expected-WAR table** (framework doc Part 7.2),
   linearly interpolated in FV. It is the only published per-side table that measures the
   same QUANTITY as our label: a bust-inclusive mean total WAR over the control window with
   the zeros left in. The four Quantity-A tables (McDaniel, both primer bands) are talent
   statements about realised big leaguers and would be a wrong prior by a factor of two to
   three (framework doc 7.1 numerical proof), so they are bake-off candidates, never the
   prior.
6. **Re-monotonize.** Shrinkage can break monotonicity where a thin high knot shrinks below
   a dense lower knot. After shrinkage, re-run PAVA over the knot values (unit weights) and
   then enforce a minimum increment of **0.01 WAR per knot step** so the curve is STRICTLY
   increasing. Strictness is load-bearing: Phase 2 inverts this curve, and a PAVA plateau
   would make the inverse a set rather than a value. Any knot the eps-step moves by more
   than 0.05 WAR is flagged in the artifact.
7. **Below the data floor.** The pool has no rows below consensus FV 34.9. Knots 20, 25, 30
   are therefore EXTRAPOLATION, produced as a monotone ramp under the fitted FV35 value,
   exactly as the shipped sub-45 anchors handle the same hole
   (`empirical_anchors.anchors_provenance`). They are labelled `extrapolation: true` in the
   artifact and must be treated as a floor, not a finding.
8. **CI bands.** Player-clustered bootstrap, B = 2000, seed 20260730, resampling the pool
   and REFITTING the whole pipeline (isotonic + shrinkage + re-monotonize) on every draw.
   Percentile CI90 per knot. Bootstrap CI of the curve VALUE (a conditional mean), not a
   predictive interval for one player.

## 1.3 P(bust) and P(star): thresholds declared explicitly

Our label is UNDISCOUNTED total bWAR over the first six seasons from debut. No published
table uses that exact quantity, so the thresholds below borrow published threshold VALUES
and are stated as such. Both a primary and a secondary definition are fit, per side, as
monotone curves (isotonic, decreasing for bust, increasing for star, same knot grid, same
shrinkage rule with the prior taken from the matching published rate table where one exists
and from a logistic-in-FV fallback where none does).

| curve | definition on our label | borrowed from |
| --- | --- | --- |
| `p_bust` PRIMARY | first-6yr total bWAR **< 1.0** | Edwards 2019 bust threshold value (his quantity is 9-season arb-discounted present-day WAR, ours is not: the value is borrowed, the quantity is not) |
| `p_star` PRIMARY | first-6yr total bWAR **>= 10.0** | Edwards 2019 star threshold value, same caveat |
| `p_bust_bucket` SECONDARY | first-6yr total bWAR **< 3.0** | `value_framework` bucket band `bust = <0.5 WAR/season`, x 6 seasons |
| `p_star_bucket` SECONDARY | first-6yr total bWAR **>= 24.0** | `value_framework` bucket band `star = 4.0+ WAR/season`, x 6 seasons |

**Outcome-bucket distribution** (cheaply derivable, so it is delivered): the five
`value_framework` per-season bands multiplied by 6 seasons, giving bust `<3.0`, bench
`3.0-9.0`, regular `9.0-15.0`, good `15.0-24.0`, star `>=24.0`, as a row-wise probability
distribution per knot per side, with cell n. Not monotonized (a distribution over five bins
has no single monotone direction); reported as an empirical cell table with its n so a thin
cell cannot be mistaken for a measurement.

## 1.4 The bake-off: candidates, and every conversion, declared up front

Five industry tables measure five different quantities (framework doc Part 6.3 and Part 10).
Every conversion below is OUR arithmetic and is stated in full. Each candidate is scored in
two modes:

- **RAW**: the table as published, converted to an implied first-6yr WAR total by the stated
  conversion, with no fitting. Measures LEVEL and SHAPE together.
- **SHAPE**: one free scalar multiplier fit by weighted least squares on the TRAINING fold
  only, applied to the held-out fold. Measures SHAPE alone. This mode exists because
  framework doc D5 is explicit that scoring a descriptive or talent-frame table against a
  bust-inclusive target makes it look catastrophically over-optimistic purely by
  construction. Scoring RAW only would be a strawman; scoring SHAPE only would hide that the
  levels are incompatible. Both are reported.

| # | candidate | source quantity | conversion to implied first-6yr total bWAR |
| --- | --- | --- | --- |
| 1 | **McDaniel 2014** combined | WAR per season, true talent, side-neutral, rows 30-80 only | `table(FV) x 6`. Rows 20/25 do not exist in the source (McDaniel says so); held flat at the FV30 value with `extrapolated_rows: [20, 25]` recorded. FV35 = 0.0 and FV30 = -1.0 in the source, so the raw curve is non-monotone against a floor-at-zero target only if clipped; it is NOT clipped, the negative value is carried. |
| 2 | **Primer bands** (2018 S2 / 2022 L7) | average annual WAR over first six service years, PER SIDE (hitter table, SP table) | band MIDPOINT x 6. Midpoints: open-ended `<-0.1` read as -0.1; open-ended `>7.0` read as 7.5. hit 40 = 0.35, 45 = 1.15, 50 = 2.0, 55 = 2.9, 60 = 4.15, 70 = 6.0, 80 = 7.5. SP 40 = 0.45, 45 = 1.35, 50 = 2.15, 55 = 3.0, 60 = 4.2, 70 = 6.0, 80 = 7.5. Rows 25/35/65/75 are absent from the source and are linearly interpolated between the published neighbours; recorded as `interpolated_rows`. The pitcher table is a STARTER table and is applied to all pitchers, which is a known mismatch for reliever-outcome rows and is disclosed, not corrected. |
| 3 | **Clemens 2026 totals** | TOTAL undiscounted WAR over the whole team-control span, bust-inclusive, PER SIDE | `table(FV) x 1.000`. Clemens' span is "6 to 7-plus years" of team control; our window is 6 calendar seasons from debut. The primary conversion is 1.000 on the argument that both quantities are "everything the club got from the prospect" and our 6-season window is the closest available proxy. A `x 6/7 = 0.857` sensitivity is computed and reported beside it. `+` tiers (35+, 40+, 45+) are placed at 37.5, 42.5, 47.5 for interpolation, per framework doc 4.3. No 75/80 row exists; held flat at the 70 value. |
| 4 | **Shipped `fv_to_6yr_avg_war`** incl. the 2026-07-29 sub-45 anchors | expected (bust-inclusive) average annual WAR over 6 years, SIDE-NEUTRAL | `vf.fv_to_6yr_avg_war(FV) x 6`. Read live from the production valuation set (`clemens_2026`, the bare-import default) with `anchor_calibration.use_empirical = true`, so the values used are the fitted `empirical_anchors.anchors`, not the config seed. |
| 4b | **Shipped `expected_war` core** (diagnostic, not one of the six) | the exact forward map `realized_implied_fv` inverts to produce `xfv_grade` | `vf.expected_war(FV, is_pitcher, position, service_years=6, age=grade_map_age)["mean"]`, per row, with the row's own debut age and position. Included because Phase 2 replaces THIS, not `fv_to_6yr_avg_war x 6`; the two differ by the aging discount over the window. |
| 5 | **Shipped `fv_to_prime_war`** converted via the aging machinery | prime/talent anchor; used in code as the P(bucket)-weighted per-season level under the prime scale | `sum(vf.prospect_prime_path(FV, is_pitcher, debut_age)["mean"][:6])`, i.e. the prime path run through the shipped aging curve and summed over the six-season window, per row with the row's own debut age. A flat `vf.fv_to_prime_war(FV) x 6` sensitivity is reported beside it. |
| 6 | **NEW per-side empirical curves** (1.1-1.3) | our label, by construction | none. Fit on the TRAINING fold only, per fold, then evaluated on the held-out fold. |
| 6b | **Side-neutral empirical curve** (diagnostic control) | our label, sides pooled | none. Same pipeline, one pooled curve. This is the direct comparator for the per-side claim. |
| 6c | **Side-label-permuted empirical curve** (zero-information control) | our label, side labels shuffled within the training fold | none. Same pipeline, permuted side labels. Gate-standard mandatory control 2: if 6c scores as well as 6, the per-side split carries no information. |

## 1.5 Held-out protocol

Forward-chained by decision year, train strictly earlier than test, refit per fold. Six
folds; five are informative and the sixth is disclosed-degenerate:

| fold | train years | test years |
| --- | --- | --- |
| F1 | <= 2013 | 2014-2015 |
| F2 | <= 2015 | 2016-2017 |
| F3 | <= 2017 | 2018 |
| F4 | <= 2018 | 2019 |
| F5 | <= 2019 | 2020 |
| F6 | <= 2020 | 2021-2024 (DEGENERATE, see below) |

**F6 is disclosed as structurally degenerate before it runs.** Uncensored rows with
consensus FV >= 47.5 by decision year: 2020 is the LAST year with any (28 hit / 13 pit);
2021, 2022 and 2023 have 0 / 1 / 0 hit and 0 / 0 / 0 pit. The reason is mechanical: a high-FV
prospect debuts, and a 2021+ debut cannot have a resolved six-season window in 2026, so every
uncensored 2021+ row is a never-MLB bust. F6 therefore measures the sub-45 range only. It is
reported with that label and is EXCLUDED from the headline per-band comparison above FV 45.

**Metrics, per candidate x side x FV band, pooled over held-out folds:**

- **calibration slope** and **bias**: OLS of realized on implied, `realized = a + b*implied`.
  Ideal `b = 1.0`, `a = 0.0`. Bias is also reported as the plain mean signed residual
  `mean(realized - implied)`, because a slope-and-intercept pair on a narrow band is
  unstable and the mean residual is not.
- **MAE**: `mean|realized - implied|`.
- **coverage_90**: fraction of (fold x band) cells whose 90% bootstrap CI for the HELD-OUT
  realized cell mean contains the candidate's implied cell value. Defined at the cell-mean
  level rather than per player because five of the nine candidates publish no interval at
  all, and a definition that only the empirical curves can satisfy is not a comparison.
  Cells with fewer than 10 held-out rows are excluded from coverage and counted separately.

FV bands: `[20,40)`, `[40,45)`, `[45,50)`, `[50,55)`, `[55,80]`. The 43.0-45.5 data hole sits
inside the `[40,45)` / `[45,50)` boundary and is disclosed.

## 1.6 What result would make this lane REJECT the per-side approach

Written before the fit. Any one of these is a reject or a downgrade, and will be reported as
such rather than reframed:

1. **The zero-information control ties the candidate.** If the side-label-permuted curve
   (6c) matches the per-side curve (6) on held-out MAE within the F-fold spread, the side
   split carries no information and Phase 2 must not be built on it. This is the check whose
   absence invalidated the pitcher-label program.
2. **The pooled curve is not beaten.** If the side-neutral empirical curve (6b) is not beaten
   by the per-side curve (6) on held-out MAE on BOTH sides, per-side is unjustified
   complexity and the honest recommendation is a single re-fit pooled curve.
3. **An industry table wins.** If any of candidates 1-3 beats candidate 6 on held-out
   calibration slope AND MAE in the FV >= 50 band on both sides, the industry table is the
   better Phase-2 basis and this lane will say so. Per the plan and the owner's directive,
   that is a valuable and acceptable outcome.
4. **The top band is unmeasurable.** If pooled cell n at FV >= 60 is under 15 per side, the
   60+ knots are declared prior-dominated and Phase 2 must read the prior there, not a
   fitted value. (Expected: `CROSS_SIDE_WAR_FINDING.md` reports 29 hit / 11 pit rows at
   consensus 60+, so the pitcher arm is expected to trip this. Stating the expectation
   in advance so the result cannot be dressed up.)
5. **Monotonicity fails.** If the strictly-increasing enforcement (1.2 step 6) has to move
   any knot by more than 0.5 WAR on either side, the fitted curve is fighting its own prior
   and the shrinkage rule is wrong, not the data.
6. **Grade movement is implausible.** If the per-side inversion moves any of the ten named
   players by more than 10 FV, or moves the top-100 pitcher share past 40, the result is
   reported as-is but flagged as requiring an owner call before Phase 2, because a change
   that large is a semantics change the site copy cannot silently absorb.

## 1.7 Scope limits of this lane

No production module is edited. No pytest run (a concurrent lane is editing `efv_score.py` /
`efv_dataset.py` and `conftest.py` git-checkouts files dirtied during a run). No exporter,
scraper, matrix rebuild or `run_monthly` invocation. The re-scaled grades reported for the
ten named players and the implied board mix are COUNTERFACTUALS computed in the lab from the
committed live artifacts; nothing served moves.

---

# PART 2. Results (appended after the fit)

Lab run 2026-07-30. Artifact `data/fv_outcome_curves.json` (160 KB, self-describing
`schema` block). Registry row `fv_outcome_curves`, verdict `provisional`, `MODEL_GLOSSARY`
entry `"internal"`, `MODEL_REGISTRY.md` regenerated.

## 2.0 Identity and vintage verification (run before the fit)

| check | hit | pit |
| --- | --- | --- |
| scored rows / unique `player_key` | 1,882 / 1,882 | 1,988 / 1,988 |
| rows unmatched in the as-of matrix | 0 | 0 |
| `realized_war_6yr` vs matrix `target_censored` mismatches (0.005 WAR) | 0 | 0 |
| `consensus_fv` vs matrix `consensus_fv_raw` mismatches (0.05 FV) | 0 | 0 |
| `censored` flag mismatches | 0 | 0 |
| uncensored / censored | 1,500 / 382 | 1,537 / 451 |

Cross-side `player_key` overlap 0, so a player-clustered bootstrap is arithmetically a row
bootstrap here (asserted in the lab, recorded in the artifact). Vintage:
`efv_dataset._asof_point` keeps only `snapshot_date < cutoff` and the debuted branch passes
the debut date as the cutoff, both re-asserted against the source at run time. The pool is
the same 1,500 / 1,537 behind `CROSS_SIDE_WAR_FINDING.md`.

## 2.1 Deviations from the pre-registration

Five, all recorded in the artifact's `deviations_from_pre_registration` block. Four are
repairs to the shrinkage and monotonization rule that the first run exposed as defective,
one adds a statistic the reject criteria needed. None changes what was measured.

1. **Re-monotonization weights.** Pre-registered as PAVA over the knot values with UNIT
   weights and centroid interpolation. That let the three ZERO-DATA knots (FV 20 / 25 / 30)
   pool one-for-one with the measured FV35 and FV37.5 knots and inflate the measured hit
   FV35 value **12x** (0.024 to 0.295 total 6yr WAR), and the centroid shift dragged the hit
   FV70 knot **5.25 WAR** off its own shrunk value. Shipped: PAVA weighted by
   `n_cell + K`, taking the direct projection at each knot.
2. **Prior extension below the table's bottom row.** Clamping the Clemens prior flat below
   its bottom published row (35+, placed at 37.5) put the prior at 0.30 hit / 0.25 pit,
   which is ABOVE the measured value at FV35 (0.07 / 0.01), at `w_prior = 1.0`. Shipped: a
   linear ramp from the bottom published row down to 0.0 at FV 20.
3. **Knot estimate.** Evaluating the isotonic step function AT the knot reads whichever
   exact-FV tie group sits there (hit FV35.0 alone is 165 rows at mean -0.004) while the
   shrinkage weight reads the +/-1.25 cell (332 rows, mean +0.072). Shipped: the mean of the
   isotonic FITTED values over the rows in the knot cell, so the estimate and its own sample
   size agree. Both readings are carried per knot (`isotonic`, `cell_mean`).
4. **Sub-floor extrapolation.** See 2.6. Shipped: the production concave re-spread; the
   prior-ramp variant is retained per knot as `value_sub_floor_prior_ramp_variant`.
5. **Head-to-head statistics added.** Criteria 1 to 3 are comparative and a table of
   separate point estimates cannot adjudicate them. Added a paired, player-clustered
   bootstrap on the held-out rows with a per-fold sign count for every contest a criterion
   is written on.

## 2.2 The curves

`E[first-6yr total bWAR | consensus FV]`. `value` is the shippable curve. CI90 is the
player-clustered bootstrap with a full refit on each of 2,000 draws.

### Hitters (n = 1,500)

| FV | n_cell | w_prior | cell mean | isotonic | prior | **VALUE** | CI90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | 332 | 0.083 | 0.07 | 0.06 | 0.26 | **0.10** | 0.06 - 0.20 |
| 37.5 | 200 | 0.130 | 0.08 | 0.14 | 0.30 | **0.16** | 0.09 - 0.43 |
| 40 | 559 | 0.051 | 0.40 | 0.45 | 0.75 | **0.47** | 0.27 - 0.58 |
| 42.5 | 93 | 0.244 | 0.87 | 0.45 | 1.20 | **0.63** | 0.54 - 1.45 |
| 45 | 146 | 0.170 | 2.74 | 2.74 | 2.50 | **2.70** | 1.90 - 3.22 |
| 47.5 | 20 | 0.600 | 3.98 | 3.98 | 3.20 | **3.51** | 2.90 - 4.15 |
| 50 | 57 | 0.345 | 5.79 | 5.79 | 7.00 | **6.21** | 5.15 - 7.32 |
| 52.5 | 18 | 0.625 | 9.73 | 9.73 | 7.50 | **8.34** | 6.84 - 9.22 |
| 55 | 39 | 0.435 | 10.28 | 10.09 | 8.00 | **9.18** | 8.09 - 10.33 |
| 57.5 | 7 | 0.811 | 9.04 | 10.09 | 10.25 | **10.22** | 9.75 - 10.75 |
| 60 | 17 | 0.638 | 11.70 | 11.15 | 12.50 | **12.01** | 11.38 - 13.13 |
| 62.5 | 2 | 0.938 | 7.43 | 12.05 | 13.00 | **12.94** | 12.65 - 13.18 |
| 65 | 8 | 0.789 | 15.94 | 15.94 | 13.50 | **14.01** | 12.89 - 15.23 |
| 67.5 | 1 | 0.968 | 21.16 | 21.16 | 20.50 | **20.52** | 20.50 - 20.56 |
| 70 | 1 | 0.968 | 47.54 | 47.54 | 27.50 | **27.72** | 27.50 - 28.15 |
| 75 / 80 | 0 | 1.000 | n/a | 47.54 | 27.50 | **27.73 / 27.74** | prior only |

Sub-floor policy knots (NOT measurement, see 2.6): FV 20 / 25 / 30 = 0.000 / 0.009 / 0.041.

### Pitchers (n = 1,537)

| FV | n_cell | w_prior | cell mean | isotonic | prior | **VALUE** | CI90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | 362 | 0.077 | 0.01 | 0.00 | 0.21 | **0.05** | 0.04 - 0.13 |
| 37.5 | 153 | 0.164 | 0.08 | 0.22 | 0.25 | **0.22** | 0.07 - 0.37 |
| 40 | 653 | 0.044 | 0.42 | 0.39 | 0.55 | **0.40** | 0.27 - 0.54 |
| 42.5 | 96 | 0.238 | 1.25 | 1.25 | 1.00 | **1.19** | 0.65 - 1.59 |
| 45 | 128 | 0.190 | 1.77 | 1.77 | 1.60 | **1.74** | 1.37 - 2.17 |
| 47.5 | 16 | 0.652 | 3.45 | 3.86 | 2.60 | **3.04** | 2.29 - 3.34 |
| 50 | 59 | 0.337 | 5.17 | 4.34 | 5.00 | **4.57** | 3.98 - 5.30 |
| 52.5 | 15 | 0.667 | 3.93 | 4.72 | 6.00 | **5.57** | 5.10 - 5.92 |
| 55 | 43 | 0.411 | 4.41 | 4.72 | 7.00 | **5.66** | 5.21 - 6.30 |
| 57.5 | 1 | 0.968 | -0.11 | 4.72 | 9.00 | **8.86** | 8.62 - 9.00 |
| 60 | 6 | 0.833 | 6.00 | 6.86 | 11.00 | **10.31** | 9.78 - 10.85 |
| 62.5 | 0 | 1.000 | n/a | 8.35 | 12.25 | **12.25** | prior only |
| 65 | 4 | 0.882 | 7.28 | 9.01 | 13.50 | **12.97** | 12.25 - 13.50 |
| 67.5 | 1 | 0.968 | 34.59 | 34.59 | 20.25 | **20.71** | 20.25 - 21.55 |
| 70 / 75 / 80 | 0 | 1.000 | n/a | 34.59 | 27.00 | **27.00 / 27.01 / 27.02** | prior only |

Sub-floor policy knots: FV 20 / 25 / 30 = 0.000 / 0.005 / 0.021.

**Say it plainly: the pitcher curve above FV 55 is the Clemens table.** `w_prior` runs
0.97 / 0.83 / 1.00 / 0.88 / 0.97 at 57.5 / 60 / 62.5 / 65 / 67.5 on 1 / 6 / 0 / 4 / 1 rows.
The hitter curve above 60 is 0.64 to 0.97 prior on 17 / 2 / 8 / 1 / 1 rows. Neither top end
is a measurement, and the single-row knots are single PLAYERS (hit FV70 is Mike Trout at
47.54 realized; pit FV67.5 is Shohei Ohtani at 34.59). The shrinkage is doing exactly the
job it was declared to do, which is to stop one career from becoming a scale.

The measured hit/pit ratio the curves carry: **1.62x at FV 55** (9.18 vs 5.66) and **1.36x
at FV 50** (6.21 vs 4.57), against the raw uncensored bucket ratio of 2.21x at 55-plus that
`CROSS_SIDE_WAR_FINDING.md` reports. The gap is the shrinkage: Clemens' own hit/pit ratio
at 55 is 8/7 = 1.14, and it carries 41% of the weight at that knot.

**Censoring sensitivity** (all rows, `target_censored`, weighted by `observed_seasons/6`),
selected knots, primary curve in parentheses: hit 35 0.13 (0.10), 45 3.05 (2.70), 50 6.43
(6.21), 55 8.90 (9.18), 60 12.05 (12.01); pit 35 0.10 (0.05), 45 1.73 (1.74), 50 4.73
(4.57), 55 5.77 (5.66), 60 10.53 (10.31). Every knot moves by less than its own CI90 width.
Including the censored rows does not change the curve.

## 2.3 Odds curves and outcome buckets

Thresholds as declared in 1.3. `p_bust` = P(first-6yr total bWAR < 1.0), `p_star` =
P(>= 10.0). Bucket versions use the `value_framework` per-season bands times 6.

| FV | hit p_bust | hit p_star | pit p_bust | pit p_star |
| --- | --- | --- | --- | --- |
| 35 | 0.983 | 0.001 | 0.978 | 0.000 |
| 40 | 0.919 | 0.015 | 0.921 | 0.006 |
| 45 | 0.654 | 0.102 | 0.621 | 0.052 |
| 50 | 0.435 | 0.213 | 0.479 | 0.112 |
| 55 | 0.304 | 0.334 | 0.410 | 0.164 |
| 60 | 0.244 | 0.334 | 0.224 | 0.232 |
| 65 | 0.201 | 0.393 | 0.156 | 0.232 |
| 70 | 0.047 | 0.576 | 0.000 | 0.444 |

Above FV 55 these are prior-dominated in the same way the WAR curve is (Edwards 2019 is the
prior from 50 up); the 65 and 70 rows are the Edwards table almost verbatim.

**Outcome-bucket distribution**, cells with n >= 30 only (every other cell is in the
artifact with its n and a `measured: false` flag):

| FV | side | n | bust | bench | regular | good | star |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | hit | 332 | 0.991 | 0.006 | 0.003 | 0.000 | 0.000 |
| 40 | hit | 559 | 0.948 | 0.034 | 0.014 | 0.004 | 0.000 |
| 45 | hit | 146 | 0.712 | 0.164 | 0.082 | 0.034 | 0.007 |
| 50 | hit | 57 | 0.456 | 0.281 | 0.070 | 0.175 | 0.018 |
| 55 | hit | 39 | 0.308 | 0.103 | 0.256 | 0.231 | 0.103 |
| 35 | pit | 362 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 40 | pit | 653 | 0.943 | 0.048 | 0.006 | 0.002 | 0.002 |
| 45 | pit | 128 | 0.797 | 0.164 | 0.023 | 0.016 | 0.000 |
| 50 | pit | 59 | 0.475 | 0.254 | 0.170 | 0.102 | 0.000 |
| 55 | pit | 43 | 0.442 | 0.302 | 0.233 | 0.023 | 0.000 |

Note the 55 row: 10.3% of consensus-55 hitters cleared 24 WAR over six years and **0% of
consensus-55 pitchers did**, on 39 and 43 rows. That is the cross-side finding in bucket
form.

## 2.4 The bake-off

Held out, forward-chained, pooled over folds. Fold sizes:

| fold | train (hit/pit) | test (hit/pit) | test rows at FV >= 47.5 (hit/pit) |
| --- | --- | --- | --- |
| F1 (<=2013 to 2014-15) | 151 / 150 | 199 / 222 | 31 / 20 |
| F2 (<=2015 to 2016-17) | 350 / 372 | 275 / 297 | 34 / 34 |
| F3 (<=2017 to 2018) | 625 / 669 | 161 / 165 | 15 / 12 |
| F4 (<=2018 to 2019) | 786 / 834 | 174 / 170 | 21 / 16 |
| F5 (<=2019 to 2020) | 960 / 1004 | 108 / 138 | 28 / 13 |
| F6 (<=2020 to 2021-24) | 1068 / 1142 | 432 / 394 | **1 / 0 DEGENERATE** |

F6 behaved exactly as pre-registered: 826 test rows, one of which carries a grade above
47.5. It contributes to the sub-45 bands only.

### RAW mode (tables as published, converted, no fitting)

Hitters, n = 1,349 held-out rows:

| candidate | slope | bias | MAE | cov90 | MAE by band (<40 / 40-45 / 45-50 / 50-55 / 55+) |
| --- | --- | --- | --- | --- | --- |
| McDaniel 2014 | 0.536 | -4.137 | 4.614 | 0.00 | 2.22 / 6.24 / 7.49 / 9.36 / 8.68 |
| primer bands | 0.529 | -2.454 | 3.060 | 0.00 | 1.31 / 2.96 / 6.44 / 9.72 / 12.64 |
| Clemens 2026 | 1.027 | -0.248 | 1.604 | 0.68 | 0.48 / 1.35 / 4.37 / 6.83 / 7.19 |
| shipped `fv_to_6yr_avg_war` | **1.453** | +0.148 | **1.476** | 0.55 | 0.37 / 1.21 / 4.25 / 6.35 / 7.43 |
| shipped `fv_to_prime_war` via aging | 0.752 | -3.216 | 3.874 | 0.09 | 2.56 / 4.14 / 6.18 / 8.45 / 8.52 |
| **empirical per-side** | **1.001** | -0.195 | 1.567 | 0.64 | 0.47 / 1.28 / 4.29 / 6.83 / 7.15 |
| _diag_ shipped `expected_war` core | 1.445 | +0.125 | 1.492 | 0.59 | 0.38 / 1.23 / 4.26 / 6.37 / 7.46 |
| _diag_ Clemens x 6/7 | 1.198 | -0.039 | 1.530 | 0.68 | 0.43 / 1.25 / 4.28 / 6.60 / 7.27 |
| _diag_ empirical pooled | 1.082 | -0.037 | 1.502 | 0.64 | 0.39 / 1.23 / 4.26 / 6.66 / 7.21 |
| _ctrl_ empirical side-permuted | 1.026 | -0.116 | 1.524 | 0.64 | 0.41 / 1.24 / 4.30 / 6.77 / 7.26 |

Pitchers, n = 1,386:

| candidate | slope | bias | MAE | cov90 | MAE by band |
| --- | --- | --- | --- | --- | --- |
| McDaniel 2014 | 0.321 | -4.182 | 4.430 | 0.00 | 2.40 / 6.27 / 7.70 / 8.42 / 11.48 |
| primer bands | 0.330 | -2.384 | 2.986 | 0.00 | 1.24 / 3.69 / 7.40 / 9.66 / 15.62 |
| Clemens 2026 | 0.922 | -0.167 | 1.179 | 0.53 | 0.46 / 1.26 / 3.66 / 4.88 / 6.09 |
| shipped `fv_to_6yr_avg_war` | 1.119 | -0.097 | **1.148** | 0.53 | 0.41 / 1.29 / 3.62 / 4.73 / 5.72 |
| shipped `fv_to_prime_war` via aging | 0.526 | -3.301 | 3.675 | 0.05 | 2.60 / 4.18 / 6.13 / 7.60 / 11.10 |
| **empirical per-side** | **0.959** | -0.123 | 1.153 | 0.53 | 0.41 / 1.29 / 3.63 / 4.80 / 5.75 |
| _diag_ shipped `expected_war` core | 1.096 | -0.116 | 1.157 | 0.53 | 0.42 / 1.31 / 3.63 / 4.74 / 5.75 |
| _diag_ Clemens x 6/7 | 1.076 | -0.035 | **1.116** | 0.63 | 0.42 / 1.19 / 3.59 / 4.75 / 5.63 |
| _diag_ empirical pooled | 0.823 | -0.250 | 1.210 | 0.58 | 0.43 / 1.34 / 3.73 / 5.15 / 6.30 |
| _ctrl_ empirical side-permuted | 0.890 | -0.147 | 1.159 | 0.53 | 0.40 / 1.29 / 3.66 / 4.93 / 6.09 |

### SHAPE mode (one free scalar fit on the training fold only)

| candidate | hit slope / bias / MAE | pit slope / bias / MAE |
| --- | --- | --- |
| McDaniel 2014 | 1.227 / -1.062 / 2.420 | 1.443 / -0.330 / 1.444 |
| primer bands | 1.079 / -0.573 / 1.857 | 1.354 / +0.017 / 1.184 |
| Clemens 2026 | 0.954 / -0.346 / 1.642 | 1.373 / +0.153 / 1.054 |
| shipped `fv_to_6yr_avg_war` | 0.985 / -0.348 / 1.648 | 1.418 / +0.100 / 1.077 |
| shipped `fv_to_prime_war` via aging | 1.375 / -1.142 / 2.449 | 1.888 / -0.368 / 1.480 |
| **empirical per-side** | 0.935 / -0.285 / **1.601** | 1.351 / +0.155 / **1.048** |
| _diag_ empirical pooled | 0.914 / -0.257 / 1.584 | 1.298 / +0.138 / 1.046 |
| _ctrl_ empirical side-permuted | 0.922 / -0.262 / 1.577 | 1.335 / +0.173 / 1.032 |

The SHAPE ordering is stable and it is the ordering the framework doc predicts: empirical
curves, then Clemens, then the shipped anchor, then the primer, then McDaniel, then
`fv_to_prime_war`. A free scalar recovers most of what the talent-frame tables lose, which
is the point of running both modes: their LEVEL is wrong by construction (Quantity A into a
Quantity B slot, framework doc 7.1), and their SHAPE is merely worse, not absurd. Note that
every pitcher SHAPE slope sits at 1.30 to 1.89: after a free scalar every table
under-predicts the pitcher gradient, because the scalar is fit where the n is (below FV 45)
and the top of the pitcher curve then falls short.

### Head-to-head, paired player-clustered bootstrap on the held-out rows

Negative favours the per-side empirical curve. MAE MDE95 from the gate standard is 0.20 hit
and 0.06 pit; a delta inside that band is a NULL.

| contest (RAW) | side | dMAE | dMAE CI90 | d abs(slope-1) | d slope CI90 | folds won |
| --- | --- | --- | --- | --- | --- | --- |
| per-side vs pooled | hit | **+0.065** | [+0.051,+0.078] | -0.081 | [-0.104,+0.076] | 1/6 |
| per-side vs pooled | pit | **-0.058** | [-0.071,-0.045] | -0.135 | [-0.146,+0.143] | 6/6 |
| per-side vs side-PERMUTED | hit | **+0.043** | [+0.033,+0.052] | -0.025 | [-0.039,+0.031] | 0/6 |
| per-side vs side-PERMUTED | pit | -0.007 | [-0.015,+0.001] | -0.069 | [-0.084,+0.080] | 4/6 |
| per-side vs Clemens 2026 | hit | -0.037 | [-0.050,-0.025] | -0.026 | [-0.037,+0.034] | 4/6 |
| per-side vs Clemens 2026 | pit | -0.026 | [-0.033,-0.020] | -0.037 | [-0.047,+0.044] | 4/6 |
| per-side vs shipped anchor | hit | +0.091 | [+0.053,+0.130] | **-0.452** | **[-0.519,-0.114]** | 1/6 |
| per-side vs shipped anchor | pit | +0.004 | [-0.011,+0.018] | -0.078 | [-0.218,+0.150] | 4/6 |
| per-side vs primer bands | hit | -1.493 | [-1.614,-1.380] | -0.469 | [-0.468,-0.264] | 6/6 |
| per-side vs primer bands | pit | -1.834 | [-1.955,-1.712] | -0.629 | [-0.651,-0.414] | 6/6 |
| per-side vs McDaniel 2014 | hit | -3.047 | [-3.187,-2.897] | -0.463 | [-0.471,-0.262] | 6/6 |
| per-side vs McDaniel 2014 | pit | -3.277 | [-3.412,-3.136] | -0.637 | [-0.667,-0.425] | 6/6 |
| per-side vs `fv_to_prime_war` | hit | -2.308 | [-2.395,-2.212] | -0.246 | [-0.252,-0.011] | 6/6 |
| per-side vs `fv_to_prime_war` | pit | -2.522 | [-2.609,-2.427] | -0.433 | [-0.450,-0.193] | 6/6 |

## 2.5 The pre-registered reject criteria, scored

Scored mechanically in the artifact's `gate_verdicts` block so this section and the artifact
cannot drift apart.

**C1, zero-information control. THE MAE ARM FIRES.** The side-label-permuted curve is
+0.043 MAE BETTER than the real per-side split on hitters (CI90 excludes zero) and -0.007
on pitchers. Both deltas are inside the MAE MDE95, so the honest reading is that **MAE
cannot separate the real side split from a permuted one on either side.** The slope arm does
not fire (per-side is closer to slope 1 on both sides), but its CI90 straddles zero on both
sides ([-0.039,+0.031] hit, [-0.084,+0.080] pit), so that advantage is not measured either.
**The side split is a NULL against its own zero-information control.**

**C2, pooled comparator. NOT SATISFIED.** Per-side loses to the pooled curve on hitter MAE
(+0.065, 1 of 6 folds) and wins on pitcher MAE (-0.058, 6 of 6 folds). Both are inside the
MDE. The pre-registered rule was "reject if per-side does not beat pooled on BOTH sides",
and it does not.

**C3, an industry table wins at FV >= 50. NOT TRIGGERED.** On the FV >= 50 subset (n = 108
hit / 76 pit, one to two folds, so this is weak evidence in both directions) the per-side
curve is better or tied on MAE against every industry table and no table beats it on both
slope and MAE on both sides. Clemens is the nearest: dMAE -0.018 hit CI90 [-0.103,+0.069],
-0.152 pit CI90 [-0.220,-0.081], with d abs(slope-1) marginally in Clemens' favour on both
sides (+0.014 hit, +0.074 pit). Read plainly: **at FV 50 and above, our per-side curve and
the Clemens 2026 table are the same instrument to within the resolution of 184 rows.**

**C4, top band measurable. FIRES ON PITCHERS, as predicted in advance.** Pooled cell n at
FV >= 60 is 29 hit (passes the 15 threshold) and **11 pit (fails)**. The pitcher 60-plus
knots are 83 to 100% prior. Phase 2 must describe them as the Clemens table, not as our
measurement.

**C5, monotone repair. PASSES.** Max knot move from the strictly-increasing enforcement is
0.4262 WAR hit and 0.1008 pit, both under the 0.5 threshold. (The first, defective rule
produced 5.25 hit. That is deviation 1, not a finding.)

**C6, grade movement. WITHIN BOUNDS, owner sign-off still required.** Largest named-player
move is 5.5 FV; top-100 pitcher count 6 to 17, far short of the 40 tripwire.

## 2.6 The low end: the curve cannot produce FV 20-45 granularity

The measured curve is nearly flat below FV 45: hit 0.10 at FV35 to 0.47 at FV40, pit 0.05 to
0.40. Inverting a flat curve is a near-vertical jump, so the outcome basis carries **no FV
20-45 display granularity of its own**. On the live board, 1,569 hit and 1,648 pit active
rows have a predicted WAR6 below the curve value at the data floor (consensus FV 35), which
is 71% of the board.

The pre-registration said knots 20 / 25 / 30 would be "a monotone ramp under the fitted FV35
value". Shipped instead: the production concave re-spread,
`value(fv) = value(35) * ((fv-20)/15) ** (1/0.45)`, the exact inverse of
`value_framework._LOWEND_FG_EXP = 0.45`. That reproduces the behaviour
`realized_implied_fv` already has, so Phase 2 keeping the low-end re-spread is a no-op
against this curve rather than a departure from it. The prior-ramp alternative is retained
per knot (`value_sub_floor_prior_ramp_variant`: hit 0.000 / 0.081 / 0.091, pit 0.000 / 0.032
/ 0.042 at FV 20 / 25 / 30, versus the shipped 0.000 / 0.009 / 0.041 and 0.000 / 0.005 /
0.021).

3,140 of 4,520 live board rows have a predicted WAR6 of 0 or less and read exactly 20.0
under the new inversion. Under the SERVED map that number is 3,132, so this is not a change
the re-scale introduces. **Recommendation to Phase 2: keep the concave re-spread, and do not
present any grade below about 45 as outcome-calibrated. It is not.**

## 2.7 Phase-2 inputs (report only, nothing served moves)

### The ten named players

`current` is the served `xfv_grade` from `data/xfv.json` (generated 2026-07-30).
`rescaled` inverts the player's own `xfv_war_6yr` through his side's curve.

| player | side | xfv_war_6yr | consensus | current | rescaled | delta |
| --- | --- | --- | --- | --- | --- | --- |
| caden_hunter | pit | 3.60 | 45.3 | 48.7 | **48.4** | -0.3 |
| kade_anderson | pit | 8.12 | 57.8 | 58.8 | **56.9** | -1.9 |
| seth_hernandez | pit | 6.71 | 58.8 | 56.3 | **55.8** | -0.5 |
| joseph_dzierwa | pit | 3.56 | 48.7 | 48.7 | **48.4** | -0.3 |
| franklin_arias | hit | 11.17 | 58.1 | 64.2 | **58.8** | -5.4 |
| jesus_made | hit | 11.48 | 60.1 | 64.8 | **59.3** | -5.5 |
| leo_de_vries | hit | 11.06 | 59.1 | 64.0 | **58.7** | -5.3 |
| enrique_bradfield_jr | hit | 4.76 | 45.6 | 51.6 | **48.7** | -2.9 |
| luis_hernandez | hit | 5.70 | 49.4 | 54.9 | **49.5** | -5.4 |
| roch_cholowsky (provisional) | hit | 10.84 | 57.5 | 62.8 | **58.4** | -4.4 |

**This is not what the Caden Hunter case predicted, and it is the most important single
result in this section.** The plan's FACT 2 expected caden_hunter to read 48.6 today and
"~50-51 against the empirical pitcher outcome curve". He reads **48.4**, i.e. 0.3 LOWER, not
2 higher. The mechanism: the re-scale does not lift pitchers, it **deflates hitters**. Every
hitter drops 2.9 to 5.5 FV while pitchers barely move. Pitchers rise on the BOARD only
because the hitters above them come down. The direction of the owner's ask is delivered; the
mechanism is the opposite of the one the plan describes, and the site copy will have to say
so, because a grade that falls while its board rank rises is exactly the pattern the
movement engine mis-reports.

### The implied board side mix (report only, NOT validation)

| cut | current (served) | per-side curve | POOLED curve |
| --- | --- | --- | --- |
| top 10 | 10 H / 0 P | 7 H / **3 P** | 10 H / 0 P |
| top 25 | 24 H / 1 P | 20 H / **5 P** | 24 H / 1 P |
| top 50 | 48 H / 2 P | 44 H / **6 P** | 47 H / 3 P |
| top 100 | 94 H / 6 P | 83 H / **17 P** | 92 H / 8 P |

The third column is the decisive one and it is why it was computed. A side-NEUTRAL outcome
curve is a single monotone map of predicted WAR, so it reproduces the board that already
exists (6 to 8 pitchers per 100). **The entire cross-side movement, 6 to 17, comes from the
side split and from nothing else in this lane.** And the side split is precisely the
component C1 and C2 report as a measured null. Per the plan's own instruction, a higher
pitcher share is NOT validation; Phase A's finding stands. For reference, consensus itself
is 28 pitchers per 100.

### Within-side monotonicity: CONFIRMED

| side | live rows | order violations | ties from clamping | strictly monotone off the clamps |
| --- | --- | --- | --- | --- |
| hit | 2,104 | **0** | 196 | yes |
| pit | 2,416 | **0** | 181 | yes |

The curve is strictly increasing by construction (minimum +0.01 WAR per knot step), so its
inverse is single-valued and the re-scaled grade is a strictly increasing function of
`xfv_war_6yr` within each side. Zero order violations on 4,520 live rows. The only ties are
at the FV20 clamp, where predicted WAR6 <= 0, and the served map already ties there.
**Phase 2.2's shippability condition holds: within-side ordering, the per-side quantile
display map and therefore surplus pricing are untouched.**

## 2.8 What argues AGAINST the per-side approach

Stated plainly, because the lane's job is to report the null:

1. **The side split does not beat its own zero-information control.** Permuting the side
   labels in training produces a curve that is BETTER on hitter MAE and equal on pitcher MAE,
   and the slope advantage CI90 straddles zero on both sides. By the gate standard's
   mandatory control 2, that is not a result.
2. **It does not beat a pooled refit of the same data** on both sides (C2 not satisfied),
   and a pooled refit delivers none of the cross-side movement the owner asked for.
3. **The entire visible effect is the deflation of the hitter top end**, driven by the FV
   50-65 hitter knots, which rest on 57 / 18 / 39 / 7 / 17 / 2 / 8 rows.
4. **The pitcher top end is not ours.** Above FV 55 the pitcher curve is the Clemens 2026
   table at 83 to 100% weight on 12 rows total. Shipping it means shipping FanGraphs' table
   under our name in the range where the owner most wants an independent number.
5. **Clemens 2026 is statistically indistinguishable from our fitted curve** at FV >= 50
   (dMAE -0.018 hit, CI90 crossing zero), and it is a published table with a much larger
   cohort behind it. A defensible alternative to this whole lane is: adopt Clemens per side
   as the map, and keep our fit as the audit of it.
6. **The measured cross-side gap is unstable in the same way `efv_board_scale`'s was.** Our
   curves put the hit/pit ratio at 1.62x at FV55; the raw uncensored buckets say 2.21x;
   Clemens says 1.14x. Three defensible numbers spanning 2x, on 39 and 43 rows.

What survives all of that: **refitting the WAR-to-grade map on resolved outcomes at all is a
real, measured improvement over the shipped anchor on hitter calibration slope** (1.001 vs
1.453, d abs(slope-1) -0.452, CI90 [-0.519,-0.114], zero excluded). That is the only contest
in the whole bake-off that clears its floor with a CI excluding zero, and it is available
with or without the side split.

## 2.9 Unrelated finding, handed to the orchestrator

`test_board_basis_coherence.PINNED_MIX` expects a top-100 pitcher count of 8. The served
`data/xfv.json` (regenerated 2026-07-30) now yields **6**, on the same basis
(`BOARD_GRADE_FIELD = xfv_grade`, fingerprint `xfv_grade|scale=off`, both matching their
pins). So the pin is currently red for an artifact refresh, not a basis change. Not touched
by this lane: the file is outside its scope and the fix is a deliberate re-pin decision.
