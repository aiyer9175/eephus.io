# The odds grade basis: does p_bust belong on the retired map or the new one?

Lane: LANE-ODDS. Owner decision 2026-07-30: **measure before deciding**.
Gate standard: `docs/EFV_GATE_STANDARD.md` (all four section-2 controls are mandatory).
Predecessor lanes: `docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md` section 1.3 (the pin and
its recorded counterfactual) and the 2026-07-25 odds-dispersion lane
(`efv_odds_calibration.py`, `tools/_prem_odds*.py`, `data/xfv_odds_dispersion_eval.json`).

Lab: `tools/odds_grade_basis_lab.py`. Artifact: `data/odds_grade_basis_eval.json`.
Registry row: `xfv_odds_grade_basis`.

**PART 1 WAS WRITTEN AND COMMITTED TO DISK BEFORE ANY MEASUREMENT WAS RUN.** PART 2 is
appended after. This lane touches NO production module: it is a measurement lane, it
monkeypatches nothing into the served path, and its only possible outputs are this
document, the lab, the eval artifact and a registry row.

---

# PART 1. Pre-registration

## 1.0 The situation being adjudicated

On 2026-07-30 LANE-P2 moved the board grade from `value_framework.realized_implied_fv`
(the inverse of this platform's own valuation forward map, which reads predicted WAR
**plus age plus position**) to `value_framework.outcome_implied_fv` (the inverse of the
pooled empirical outcome curve, a **pure monotone function of predicted WAR**).

The outcome DISTRIBUTION was deliberately left behind. `efv_score.run`, `run_live` and
the backgrade path all compute a second grade, `_odds_grade`, on the retired map, and key
`p_bucket`, `p_bust` and `sv_distribution` off that (efv_score.py:1188, 1684, 2033). The
stated reason (POOLED_OUTCOME_REFIT.md 1.3) is that those probabilities are validated,
ground-truthed numbers and nothing had measured a re-key.

The platform therefore runs **two grade maps in one row**. That is coherent only if the
retired map is genuinely the better key for the odds. The recorded counterfactual of a
re-key is hitter `p_bust` mean **-0.0120** (448 of 1,971 rows moving more than one point)
and pitcher `p_bust` mean **-0.0400** (722 rows). A re-key therefore makes prospects look
LESS likely to bust across the board. If that direction is not earned by calibration it
is an unearned optimism shift on every published card, so this lane is written to catch a
level shift that improves nothing as the failure mode it is.

## 1.1 The question

Does `p_bust` (and `p_bucket['star']`) calibrate BETTER when keyed to the retired
`realized_implied_fv` grade or to the new `outcome_implied_fv` grade?

## 1.2 The frame

**Pool.** `data/xfv_hitter_matrix.json` / `data/xfv_pitcher_matrix.json`, minus rows with
`kind == "bust" and bust_recent` (the exact pool filter `efv_score.run` applies), prepped
through `efv_model._prep(pool, "target_censored", side)` so training matches production
row for row.

**Test restriction.** A row enters the evaluation frame only if `censored is False` and
`target_resolved` is numeric: resolved, uncensored, with an observed outcome.

**Folds.** Forward-chained on `efv_model._decision_year`, decision years **2014-2020**,
seven folds, each trained strictly on `decision_year < fold`. This is >= 4 splits as the
gate standard requires, and it is the identical frame the 2026-07-25 odds lane
pre-registered (`tools/_prem_odds.py:28-38`) for the identical reason:

* decision years 2021+ have a six-season window that has not closed, so every debuted row
  there is censored and the resolved rows that remain are 100% bust by construction. A
  fold whose base rate is 1.000 cannot test a probability at all. Measured on today's
  matrices: hit 2021/2022/2023/2024 bust rate 1.000/1.000/1.000/1.000, pit likewise.
* decision years 2011-2013 do not carry enough prior rows to fit the chain.

**Cuts.** Per side (hit, pit) and pooled. A SECONDARY cut restricted to served-comparable
rows (a resolved MiLB feature block, `milb.rates_missing == 0.0`) is reported alongside,
because that is the population `efv_score.run_live` actually abstains down to and it is
the frame the 2026-07-25 lane used.

## 1.3 The labels, and where they already live

**BUST.** The shipped bust event, taken unchanged from `tools/_prem_odds.py:41-43`:

> first-6yr TOTAL bWAR / 6 < 0.5 WAR per season, i.e. `target_resolved < 3.0`.

That traces to `value_framework_config.yaml:38`, `buckets.bust.band: "<0.5"`, evaluated
over `efv_dataset.TARGET_SEASONS = 6`. No new definition is invented here.

**STAR.** The same band convention at the other end of the same five-bucket ladder,
`value_framework_config.yaml:42`, `buckets.star.band: "4.0+"`:

> first-6yr TOTAL bWAR / 6 >= 4.0 WAR per season, i.e. `target_resolved >= 24.0`.

This is deliberately NOT the `star_odds` model's definition (2+ control seasons of >= 4
WAR over the clemens_2026 seven-season window, `tools/build_star_odds_artifacts.py:22-25`).
That is a different model on a different window and it is not what `p_bucket['star']`
means. The quantity under test here is bucket index 4 of the same vector that produces
`p_bust`, so it must be scored against the same ladder that defines that vector.

**PRE-REGISTERED POWER CAVEAT ON THE STAR ARM.** The frame contains **9 hitter stars and
2 pitcher stars** across all seven folds. That is counted here, in advance, so that the
star result is reported as UNPOWERED whatever it shows. No star verdict of any sign will
be treated as evidence.

## 1.4 The arms

Every arm scores the SAME out-of-fold `xfv_war` from the SAME refit chain
(`_fit_ridge` -> `_fit_linear_calibration` -> `xfv_war = max(-2, a + b*raw)`), which is
`efv_score.run`'s chain. Only the grade key and the post-map differ.

| arm | probability |
|---|---|
| **A. PIN (incumbent)** | `p_bucket_given_fv(realized_implied_fv(xfv_war, is_pit, age=_grade_map_age(age_at_debut, 0.0), position=pos, exposure_seasons=6), is_pit)` - efv_score.py:1188-1196 verbatim |
| **B. RE-KEY (candidate)** | `p_bucket_given_fv(outcome_implied_fv(xfv_war, exposure_seasons=6), is_pit)` |
| **C. ZERO-INFO CONTROL** | constant, the label base rate of the fold's TRAINING rows (climatology). Gate standard 2.2. |
| **D. RANK-IDENTICAL TWIN OF B** | B's ordering carrying A's marginal distribution (quantile match: sort B, assign A's sorted values). Contains B's ranking and none of B's levels. |
| **E. MIRROR TWIN OF A** | A's ordering carrying B's marginal distribution. Contains A's ranking and none of A's levels. |
| **F. A + PLATT, G. B + PLATT** | each arm passed through a forward-chained Platt map in logit space, `logit(p') = a + b*logit(p)`, fit on decision years < fold only. |

D and E are the gate standard's required zero-information control for a LEVEL change
("a rank-identical twin", section 2.2). They decompose the A-vs-B difference into a
ranking part and a level/shape part: if D scores like B, B's advantage is ranking; if D
scores like A, B's advantage is level.

F and G answer the owner's actual worry directly. If A and B are indistinguishable AFTER
an out-of-fold monotone recalibration, then everything separating them is a fixable
miscalibration that carries no information, and the honest fix is recalibration of
whichever key is retained, not a re-key.

## 1.5 The metrics

Per arm, per side, pooled, AND per fold:

* **Brier score** (mean squared error of the probability). Lower is better.
* **Log loss** (natural log, probabilities clipped to [1e-6, 1-1e-6]). Lower is better.
* **Expected calibration error (ECE)**: ten equal-count bins,
  `sum_b (n_b/N) * |mean_p_b - obs_b|`.
* **Reliability curve**: ten equal-count deciles of predicted probability, each with n,
  mean predicted, observed frequency and a Wilson 95% interval on the observed frequency.
* **Calibration slope and intercept**: logistic regression `y ~ a + b*logit(p)` by IRLS.
  Perfect is `(a, b) = (0, 1)`. `b < 1` means over-sharp, `b > 1` means under-sharp.
* **Calibration-in-the-large**: `mean(p) - mean(y)`. This is the pure LEVEL term.
* **Murphy decomposition** on the same ten bins: `Brier = reliability - resolution +
  uncertainty`. `resolution` is the information the forecast carries; `reliability` is its
  calibration error; `uncertainty` is common to every arm on a given frame. This is the
  instrument that separates "the re-key knows more" from "the re-key sits at a better
  level".
* **AUC** (label vs probability). SECONDARY and diagnostic only. Reported with the gate
  standard's section-3 carve-out attached: neither arm here is a missingness indicator and
  the comparison is paired on identical rows, but the debut/no-debut confound the carve-out
  describes is present in this pool, so the served-comparable (track-record) cut is the
  admissible version and is reported beside it.

## 1.6 The controls (gate standard section 2, all four)

1. **Paired bootstrap resampling TRAIN AND TEST with a full refit on every draw.** Clusters
   are `player_key` (one row per player per side). Each draw resamples the whole prepped
   pool with replacement at the player level, re-runs the entire seven-fold chain
   (`_fit_ridge` + `_fit_linear_calibration` + `_fit_ols_fv`) on the resampled training
   rows, re-scores the resampled test rows through both keyings, and records the PAIRED
   delta `d = metric(A) - metric(B)`. Positive `d` means the re-key is better. B = 1000,
   seeded. A test-only bootstrap is reported beside it only to document the understatement
   factor; it is not the gate.
2. **Zero-information control** (arm C) reported beside every claim.
3. **Permutation null band**: 1000 draws with the LABEL permuted within fold, recomputing
   the same paired `d`. Report the null mean and its [p2.5, p97.5] band. An observed `|d|`
   inside that band is a null regardless of its bootstrap CI.
4. **Per-split values** for every headline number, all seven folds, not just the pooled
   figure.

## 1.7 THE SHIP CRITERION (fixed here, not alterable afterwards)

A RE-KEY ships only if ALL of the following hold:

1. The NEW keying (arm B) is better on **Brier** AND on **log loss**, **for hitters** and
   **for pitchers** separately; and
2. the paired player-clustered bootstrap CI95 of `d` **excludes zero** on **at least the
   pooled cut**, on both metrics.

Anything less is a **NULL**, and the honest recommendation is to KEEP THE PIN and register
the two-map split permanently.

Two further pre-registered interpretation rules, written now so they cannot be chosen
after the fact:

3. **The level-shift trap.** If arm B's advantage on Brier and log loss does not survive
   forward-chained Platt recalibration of both arms (i.e. the paired CI95 of
   `metric(F) - metric(G)` includes zero), then the difference between the two keyings is a
   LEVEL/SHAPE effect and carries no information. In that case the verdict is NOT a re-key
   even if criteria 1 and 2 fire, because the same benefit is obtainable by recalibrating
   the key that is already shipped, at zero coherence cost and zero blast radius.
4. **The twin rule.** If the rank-identical twin D scores no better than arm A, then the
   re-key adds no ranking information and its whole effect is the marginal distribution.

## 1.8 What this lane will NOT do

It will not edit `efv_score.py`, `value_framework.py`, `storage.py` or any other
production module; it will not run pytest, any exporter, `run_monthly`, `build_site`, a
scraper or a matrix rebuild; it will not `git add` a data path it did not create; and it
will not build the refit option in 1.9, only cost it.

## 1.9 The third option, to be costed and not built

Nobody has priced **refitting the odds model on the new grade** rather than merely
re-keying it. PART 2 states what that would take and whether the data supports it. It is a
report, not a deliverable.

---

# PART 2. Results

*(Appended after the measurement. Everything above this line was on disk first.)*

Artifact: `data/odds_grade_basis_eval.json`. Lab runtime 615.5s, B = 1000 bootstrap draws
with a full refit each draw, B = 1000 permutation draws.

## 2.0 VERDICT: KEEP THE PIN

The re-key fails its pre-registered ship criterion on the primary frame, and every place it
appears to win is a place where it wins LESS than its own zero-information null.

* Criterion 1 FAILS. The re-key is not better on both metrics on both sides. On pitchers it
  is decisively WORSE (Brier +0.0294, log loss +0.0782), on hitters it is a null.
* Criterion 2 fires, in the WRONG DIRECTION. The pooled paired bootstrap CI95 excludes zero
  with the PIN ahead: Brier d = -0.0138 CI [-0.0200, -0.0065], log loss d = -0.0296 CI
  [-0.0476, -0.0090], P(re-key better) = 0.000 and 0.002.
* Criterion 3 (the level-shift trap) fires. After an out-of-fold Platt recalibration of both
  arms the two keyings are statistically indistinguishable on the primary frame (pooled
  Brier d = -0.0012 CI [-0.0054, +0.0030]).
* Criterion 4 (the twin rule) fires. The rank-identical twins reproduce each arm's score to
  four decimal places, so the re-key adds no ranking information whatsoever.

The observed shift is a LEVEL SHIFT, not a calibration improvement, and it moves in the
wrong direction on a curve that is already under-predicting bust.

## 2.1 The frame as built

| | hit | pit | pooled |
|---|---|---|---|
| resolved out-of-fold rows, decision years 2014-2020 | 923 | 1,002 | 1,925 |
| busts (WAR/6 < 0.5) | 775 (83.97%) | 880 (87.82%) | 1,655 (85.97%) |
| stars (WAR/6 >= 4.0) | 9 (0.98%) | 2 (0.20%) | 11 (0.57%) |
| served-comparable subset (MiLB track record) | 244 | 272 | 516 |

Five-bucket outcome census, i.e. the data a refit would have to fit (section 2.11):

| | bust | bench | regular | good | star |
|---|---|---|---|---|---|
| hit | 775 | 70 | 40 | 29 | 9 |
| pit | 880 | 83 | 26 | 11 | 2 |

**Provenance check.** On the served-comparable cut this lab reproduces the incumbent's
Brier at **0.23196** against the independently built 2026-07-25 odds lane's **0.23223**
(`data/xfv_odds_dispersion_eval.json`, `gates.point_estimates_served_comparable.INC`), and
its log loss at 0.73794 against 0.73947, on a different fold set and a since-regenerated
matrix. The replication of the served scoring chain is correct.

## 2.2 Brier and log loss, both keyings, per side (primary frame)

`uncertainty` is the Murphy base-rate term, common to every arm on a cut.

**Hitters** (n = 923, uncertainty 0.1346)

| arm | Brier | log loss | ECE | reliability | resolution | cal slope | cal intercept | mean p - obs | AUC |
|---|---|---|---|---|---|---|---|---|---|
| A PIN | 0.16048 | 0.52616 | 0.1962 | 0.0674 | 0.0395 | 0.524 | 1.496 | -0.1686 | 0.8193 |
| B RE-KEY | 0.16609 | 0.53195 | 0.2133 | 0.0700 | 0.0404 | 0.587 | 1.494 | -0.1986 | 0.8193 |
| C zero-info | 0.15054 | 0.47989 | 0.1600 | 0.0316 | 0.0170 | 0.582 | 1.108 | -0.1204 | 0.5628 |
| D twin (B rank, A level) | 0.16049 | 0.52606 | 0.1962 | 0.0671 | 0.0404 | 0.524 | 1.496 | -0.1686 | 0.8194 |
| E twin (A rank, B level) | 0.16618 | 0.53228 | 0.2133 | 0.0700 | 0.0395 | 0.586 | 1.494 | -0.1986 | 0.8192 |
| F PIN + Platt | 0.12571 | 0.41708 | 0.0930 | 0.0182 | 0.0286 | 0.571 | 0.865 | -0.0467 | 0.7811 |
| G RE-KEY + Platt | 0.12614 | 0.41923 | 0.0988 | 0.0165 | 0.0266 | 0.583 | 0.837 | -0.0469 | 0.7751 |

**Pitchers** (n = 1,002, uncertainty 0.1069)

| arm | Brier | log loss | ECE | reliability | resolution | cal slope | cal intercept | mean p - obs | AUC |
|---|---|---|---|---|---|---|---|---|---|
| A PIN | 0.12267 | 0.40076 | 0.1538 | 0.0334 | 0.0177 | 0.712 | 1.327 | -0.1393 | 0.7828 |
| B RE-KEY | 0.15207 | 0.47898 | 0.2284 | 0.0633 | 0.0175 | 0.789 | 1.533 | -0.2142 | 0.7833 |
| C zero-info | 0.11539 | 0.39597 | 0.1169 | 0.0176 | 0.0106 | 0.737 | 1.014 | -0.0915 | 0.5759 |
| D twin (B rank, A level) | 0.12260 | 0.40059 | 0.1538 | 0.0333 | 0.0175 | 0.713 | 1.326 | -0.1393 | 0.7830 |
| E twin (A rank, B level) | 0.15211 | 0.47906 | 0.2284 | 0.0633 | 0.0177 | 0.788 | 1.534 | -0.2142 | 0.7827 |
| F PIN + Platt | 0.10145 | 0.34324 | 0.0599 | 0.0077 | 0.0127 | 0.668 | 0.735 | -0.0273 | 0.7508 |
| G RE-KEY + Platt | 0.10581 | 0.36822 | 0.0690 | 0.0089 | 0.0087 | 0.503 | 1.030 | -0.0345 | 0.7155 |

**Pooled** (n = 1,925, uncertainty 0.1206)

| arm | Brier | log loss | ECE | reliability | resolution | cal slope | cal intercept | mean p - obs | AUC |
|---|---|---|---|---|---|---|---|---|---|
| A PIN | 0.14080 | 0.46088 | 0.1747 | 0.0483 | 0.0273 | 0.567 | 1.458 | -0.1533 | 0.7967 |
| B RE-KEY | 0.15879 | 0.50438 | 0.2202 | 0.0652 | 0.0274 | 0.636 | 1.546 | -0.2067 | 0.7969 |
| C zero-info | 0.13224 | 0.43621 | 0.1053 | 0.0134 | 0.0033 | 0.679 | 1.053 | -0.1053 | 0.5812 |
| F PIN + Platt | 0.11308 | 0.37864 | 0.0678 | 0.0113 | 0.0178 | 0.609 | 0.824 | -0.0366 | 0.7675 |
| G RE-KEY + Platt | 0.11556 | 0.39267 | 0.0754 | 0.0093 | 0.0161 | 0.557 | 0.905 | -0.0404 | 0.7482 |

## 2.3 The paired, player-clustered, refit-every-draw bootstrap (B = 1000)

`d = metric(PIN) - metric(RE-KEY)`. POSITIVE means the re-key is better.

| cut | metric | d | CI95 | P(re-key better) |
|---|---|---|---|---|
| hit | Brier | -0.00179 | [-0.01045, +0.00776] | 0.345 |
| hit | log loss | +0.00884 | [-0.01999, +0.04043] | 0.714 |
| hit | ECE | -0.01812 | [-0.03517, -0.00021] | 0.025 |
| pit | Brier | **-0.02476** | **[-0.03338, -0.01498]** | 0.000 |
| pit | log loss | **-0.06505** | **[-0.08774, -0.04016]** | 0.000 |
| pit | ECE | -0.06178 | [-0.08110, -0.04162] | 0.000 |
| **pooled** | **Brier** | **-0.01375** | **[-0.01998, -0.00651]** | **0.000** |
| **pooled** | **log loss** | **-0.02964** | **[-0.04762, -0.00901]** | **0.002** |
| pooled | ECE | -0.04221 | [-0.05475, -0.02873] | 0.000 |

After the out-of-fold Platt recalibration of BOTH arms:

| cut | metric | d | CI95 | P(re-key better) |
|---|---|---|---|---|
| hit | Brier | +0.00086 | [-0.00595, +0.00774] | 0.588 |
| hit | log loss | +0.00322 | [-0.01679, +0.02653] | 0.580 |
| pit | Brier | -0.00306 | [-0.00797, +0.00181] | 0.100 |
| pit | log loss | -0.02151 | [-0.04820, -0.00447] | 0.005 |
| pooled | Brier | -0.00118 | [-0.00539, +0.00300] | 0.298 |
| pooled | log loss | -0.00966 | [-0.02747, +0.00409] | 0.099 |

**The test-only bootstrap understates sd by 1.97x to 2.14x on every primary cut**, which is
at or above the 1.6-1.8x the gate standard cites. Reported as a diagnostic only.

## 2.4 Per split (all seven folds, gate standard 2.4)

`d_Brier` and `d_logloss` with the same sign convention.

| fold | hit n | hit d_Brier | hit d_ll | pit n | pit d_Brier | pit d_ll |
|---|---|---|---|---|---|---|
| 2014 | 96 | **+0.0465** | **+0.1498** | 89 | -0.0020 | -0.0044 |
| 2015 | 78 | -0.0065 | -0.0152 | 95 | -0.0375 | -0.0851 |
| 2016 | 95 | -0.0177 | -0.0289 | 118 | -0.0547 | -0.1349 |
| 2017 | 112 | -0.0217 | -0.0416 | 87 | -0.0453 | -0.1191 |
| 2018 | 174 | -0.0136 | -0.0319 | 215 | -0.0365 | -0.0991 |
| 2019 | 199 | -0.0106 | -0.0235 | 194 | -0.0217 | -0.0682 |
| 2020 | 169 | -0.0032 | -0.0054 | 204 | -0.0160 | -0.0445 |

**13 of 14 side-folds favour the pin.** The single exception is hitters 2014, the FIRST and
thinnest fold (trained on 2011-2013, 91 rows, where both arms score worse than a constant:
Brier 0.391 and 0.345 against the constant's 0.242). Fold 2014 alone is what turns the
hitter pooled log loss nominally positive. Drop it and hitters are 6 for 6 against the
re-key. This is exactly the single-split evidence the gate standard section 5 retires.

## 2.5 Reliability curves (pooled, ten equal-count deciles)

| decile | PIN predicted | RE-KEY predicted | OBSERVED | observed CI95 |
|---|---|---|---|---|
| 1 | 0.103 | 0.166 | 0.409 | [0.342, 0.480] |
| 2 | 0.331 | 0.386 | 0.746 / 0.741 | [0.680, 0.802] |
| 3 | 0.485 | 0.512 | 0.824 / 0.829 | [0.764, 0.876] |
| 4 | 0.677 | 0.580 | 0.896 | [0.845, 0.932] |
| 5 | 0.778 | 0.611 | 0.953 | [0.914, 0.975] |
| 6 | 0.845 | 0.665 | 0.964 | [0.927, 0.982] |
| 7 | 0.905 | 0.728 | 0.969 / 0.964 | [0.933, 0.986] |
| 8 | 0.972 | 0.914 | 0.932 / 0.938 | [0.888, 0.960] |
| 9 | 0.986 | 0.986 | 0.938 | [0.894, 0.964] |
| 10 | 0.988 | 0.988 | 0.969 | [0.933, 0.986] |

Read the OBSERVED column: it is the same column for both arms, decile by decile, because
the two keyings put almost exactly the same players in the same deciles. **Only the
PREDICTED column moves.** And it moves DOWN through deciles 4-7, precisely where the
observed bust rate is already 0.90 to 0.97 and both arms are already far too low. Both
curves are badly over-sharp and under-predict bust across the bottom seven deciles; the
re-key makes the middle of that worse.

## 2.6 The controls

**Zero-information control (arm C).** A constant at the fold's training base rate BEATS
BOTH KEYINGS on both proper scores, on both sides:

| cut | C Brier | PIN Brier | RE-KEY Brier | C log loss | PIN log loss | RE-KEY log loss |
|---|---|---|---|---|---|---|
| hit | **0.15054** | 0.16048 | 0.16609 | **0.47989** | 0.52616 | 0.53195 |
| pit | **0.11539** | 0.12267 | 0.15207 | **0.39597** | 0.40076 | 0.47898 |
| pooled | **0.13224** | 0.14080 | 0.15879 | **0.43621** | 0.46088 | 0.50438 |

This is the 2026-07-25 odds-dispersion finding restated on a wider frame, and it is the
most important number on this page. The served odds DO carry real information (resolution
0.0273 pooled against the constant's 0.0033, AUC 0.797 against 0.581), but they are
miscalibrated badly enough that a forecaster who knew nothing but the base rate would score
better. That defect belongs to the LINK, not to the KEY, and the choice this lane was asked
to adjudicate cannot touch it in either direction.

**Rank-identical twins (arms D, E).** D carries the re-key's ordering with the pin's
marginal; E carries the pin's ordering with the re-key's marginal.

| cut | PIN | D (re-key rank, pin level) | RE-KEY | E (pin rank, re-key level) |
|---|---|---|---|---|
| hit Brier | 0.16048 | **0.16049** | 0.16609 | **0.16618** |
| pit Brier | 0.12267 | **0.12260** | 0.15207 | **0.15211** |
| pooled Brier | 0.14080 | **0.14077** | 0.15879 | **0.15885** |

D scores as the PIN and E scores as the RE-KEY, to four decimal places, on every cut. The
gap between the two keyings is 100% marginal distribution and 0% ordering.

**Permutation null band (labels permuted within fold, predictions fixed).** Because the two
arms have different sharpness, a pure level difference produces a NON-ZERO delta even when
the labels carry no information. That makes this null the exact reference distribution for
"a level shift that improves nothing":

| cut | metric | observed d | null band95 | verdict |
|---|---|---|---|---|
| hit | Brier | -0.00561 | [+0.00788, +0.01592] | outside, BELOW |
| hit | log loss | -0.00579 | [+0.06865, +0.09903] | outside, BELOW |
| pit | Brier | -0.02940 | [-0.01623, -0.00902] | outside, BELOW |
| pit | log loss | -0.07822 | [-0.03994, -0.01739] | outside, BELOW |
| pooled | Brier | -0.01799 | [-0.00244, +0.00307] | outside, BELOW |
| pooled | log loss | -0.04349 | [+0.01990, +0.03846] | outside, BELOW |

Every observed delta sits BELOW its null band. Note what that means on hitters, where the
raw comparison reads as a null: under random labels the re-key's flatter marginal would beat
the pin by +0.012 Brier; with the real labels it LOSES by -0.006. The pin's extra sharpness
is earned. **There is no cut in this lane, primary or secondary, on which the re-key beats
its own zero-information null.**

## 2.7 Calibration or level? Four independent lines, one answer

1. **Discrimination is identical.** AUC 0.8193 vs 0.8193 (hit), 0.7828 vs 0.7833 (pit).
2. **Murphy resolution is identical.** 0.0395 vs 0.0404 (hit), 0.0177 vs 0.0175 (pit). The
   entire Brier gap sits in the RELIABILITY term: 0.0674 -> 0.0700 (hit), 0.0334 -> 0.0633
   (pit).
3. **The twins are exact** (section 2.6): swap the marginals and the scores swap with them.
4. **The reliability curve's observed column does not move** (section 2.5); only the
   predicted column does.

It is a level shift. It is not a calibration improvement. It is an unearned optimism shift,
and its size is largest exactly where the pool is thickest.

## 2.8 The secondary cut, and why it does not overturn the verdict

On the served-comparable subframe (rows with a MiLB track record, n = 516) the raw sign
FLIPS and the re-key looks better:

| cut | n | PIN Brier | RE-KEY Brier | d | CI95 | PIN log loss | RE-KEY log loss | d | CI95 |
|---|---|---|---|---|---|---|---|---|---|
| hit_served | 244 | 0.25022 | 0.23762 | +0.01260 | [+0.0048, +0.0288] | 0.82954 | 0.76693 | +0.06261 | [+0.0321, +0.1506] |
| pit_served | 272 | 0.21557 | 0.20960 | +0.00598 | [-0.0053, +0.0176] | 0.65577 | 0.63353 | +0.02224 | [-0.0090, +0.0704] |
| pooled_served | 516 | 0.23196 | 0.22285 | +0.00911 | [+0.0026, +0.0193] | 0.73794 | 0.69661 | +0.04133 | [+0.0231, +0.0937] |

Three reasons this does not carry the day, in ascending order of force:

1. It was pre-registered as SECONDARY, and criterion 1 still fails on it: pitchers are a
   null, not a win.
2. **It reverses under recalibration.** hit_served Brier d after Platt = -0.00651 CI
   [-0.01469, +0.00052] with P(re-key better) = 0.036, log loss d = -0.02003 CI
   [-0.04049, -0.00053]; pooled_served Brier d = -0.00546 CI [-0.01083, +0.00008], log loss
   d = -0.02890 CI [-0.08145, -0.00071]. Once both arms are recalibrated out of fold, the
   PIN wins the served cut too.
3. **It loses to its own permutation null.** The zero-information null for this exact
   comparison is +0.0247 Brier / +0.1188 log loss in the re-key's favour on the pooled
   served cut. The observed is +0.0091 / +0.0413. Every served cut is the same story:

   | cut | metric | observed | null band95 |
   |---|---|---|---|
   | hit_served | Brier | +0.01260 | [+0.02264, +0.03971] |
   | hit_served | log loss | +0.06261 | [+0.14107, +0.21060] |
   | pit_served | Brier | +0.00598 | [+0.00858, +0.02519] |
   | pit_served | log loss | +0.02224 | [+0.02926, +0.07872] |
   | pooled_served | Brier | +0.00911 | [+0.01854, +0.03081] |
   | pooled_served | log loss | +0.04133 | [+0.09812, +0.14034] |

   The re-key's apparent served-frame win is smaller than what a forecast with the same
   marginal and NO label information would deliver. It is not a win at all; it is the
   signature of the failure mode this lane was written to catch.

## 2.9 The star arm (declared unpowered in advance)

Reported for completeness and treated as evidence of nothing, per 1.3.

| cut | positives | PIN Brier | RE-KEY Brier | PIN log loss | RE-KEY log loss | PIN AUC | RE-KEY AUC |
|---|---|---|---|---|---|---|---|
| hit | 9 | 0.01645 | 0.01026 | 0.05956 | 0.04331 | 0.9472 | 0.9480 |
| pit | 2 | 0.00198 | 0.00197 | 0.01231 | 0.01215 | 0.8217 | 0.8215 |
| pooled | 11 | 0.00892 | 0.00594 | 0.03496 | 0.02709 | 0.9296 | 0.9273 |

The re-key reads better here, and it is the same artifact in mirror image: the re-key
predicts fewer stars (mean p 0.0132 against 0.0203, base rate 0.0057), AUC is unchanged to
three decimals, the zero-information constant essentially ties the re-key on Brier
(0.00591 vs 0.00594), the observed pooled Brier delta (+0.00298) sits BELOW its permutation
null band ([+0.00431, +0.00482]), and after Platt the delta collapses to +0.00072 CI
[-0.00227, +0.00235]. Level, again, on 11 events.

## 2.10 The mechanism

Predicted WAR required to reach a grade, under each map (hitter, age-neutral):

| FV | WAR needed, RETIRED map | WAR needed, NEW map | p_bust served at that FV |
|---|---|---|---|
| 25 | 0.054 | 0.006 | 0.971 |
| 30 | 0.250 | 0.028 | 0.934 |
| 35 | 0.615 | 0.069 | 0.855 |
| 40 | 1.166 | 0.453 | 0.710 |
| 45 | 1.915 | 2.265 | 0.505 |
| 50 | 4.138 | 5.566 | 0.299 |
| 60 | 8.894 | 10.942 | 0.069 |
| 70 | 15.565 | 27.473 | 0.013 |

The two maps cross at about FV 43. Below it the NEW map hands out the same grade for up to
NINE TIMES LESS predicted WAR; above it the new map is slightly stingier. The frame's mean
grade is 35.7 to 38.5, so the overwhelming majority of rows sit in the zone where the new
map is far more generous, and the realized bust rate down there is 84% to 88% against a
served p_bust that is already too low. Hence: mean p_bust moves -0.0301 (hit) and -0.0750
(pit) on this frame, sd of the grade falls 15.26 -> 13.92 (hit) and 10.15 -> 9.72 (pit), and
the calibration-in-the-large gets worse on both sides (-0.169 -> -0.199 hit,
-0.139 -> -0.214 pit).

**Reconciliation with LANE-P2's recorded counterfactual.** POOLED_OUTCOME_REFIT.md 2.3
recorded hit -0.0120 (448 of 1,971 rows) and pit -0.0400 (722 of 2,293) on the LIVE board.
This lane measures -0.0301 and -0.0750 on the RESOLVED out-of-fold cohort frame. Same sign,
same ordering, same magnitude class; the difference is population. The live board has 1,641
of 1,971 hitter rows under grade 35 where the two maps differ by only +0.61 FV, while the
resolved cohort frame is concentrated in the 35-45 band where the recorded per-band move is
+4.71 to +5.00 FV. Replaying arm B directly on the committed `xfv_scored*.json` (a third
population again, 1,882 hit / 1,988 pit) gives -0.0347 and -0.0736. Nothing here contradicts
LANE-P2; it prices the same change on the population that has outcomes.

## 2.11 The third option, costed: refitting the odds model on the new grade

Not built, as instructed. What it would take, and whether the data supports it.

**What `p_bucket_given_fv` actually is.** It is a model of P(outcome bucket | INDUSTRY
CONSENSUS FV), fit from the Clemens 2025 published tables committed in
`value_framework_config.yaml` (`p_bucket_given_fv_hitter` / `_pitcher`: five grade cells
each, n = 679 hitters and 436 pitchers, reconstructed to integer counts and fit as an
ordered logit into `data/value_framework_fitted.json`). Production evaluates that curve at
an argument that is not a consensus FV at all, but an inverted prediction. So "refit on the
new grade" is three different projects and only one of them is a refit.

**(a) Re-key.** Keep the borrowed curve, change its argument. This lane measured it. NULL at
best, worse in the aggregate. Cost to reject: zero, it is already paid.

**(b) Re-link.** Keep the curve, fit a monotone correction of its OUTPUT on our own resolved
outcomes. This already exists: `efv_odds_calibration.recalibrate_p_bust`, two parameters per
side (`_PLATT = {"hit": (0.7268, 0.3749), "pit": (0.7269, 0.3553)}`), gated 2026-07-25,
**still not wired in** (no module imports it). This lane's F and G arms rebuild it
independently from scratch on a wider frame and reproduce its size: pooled Brier
0.14080 -> 0.11308 (-0.0277) and log loss 0.46088 -> 0.37864 (-0.0823), out of fold, which
also finally beats the zero-information constant (0.13224 / 0.43621). That is **more than
1.5x the entire Brier difference between the two keys** and it points the other way from the
re-key: the fitted intercept +0.727 pushes p_bust UP, the slope 0.37 compresses the
over-sharp curve. The re-key would move p_bust DOWN.

**(c) True refit.** Discard the borrowed table and fit P(bucket | our grade) on our own
resolved cohort. Data available is exactly this lane's frame. Verdict on feasibility, from
the census in 2.1:

* The BUST / non-bust split IS refittable: 775 vs 148 (hit) and 880 vs 122 (pit) supports a
  two or three parameter ordered model comfortably.
* The TOP OF THE LADDER IS NOT. Pitcher `good` n = 11 and `star` n = 2. The top two
  cutpoints would be prior-driven, and those cutpoints are load-bearing for
  `expected_surplus_usd`, `survivor_expected_war`, `sv_distribution` and the published star
  odds. A true refit would produce a well-estimated bottom and an invented top, and it would
  silently reprice the top of the board.
* There is a POPULATION problem on top of the sample problem. Our cohort's bust rate is 84%
  to 88%; Clemens's table is 51% to 53% at FV45, because his pool is FV >= 45 published-list
  membership and ours is the whole eFV cohort matrix. A refit on our pool re-anchors P(bust)
  at OUR base rate, which is right for the eFV board and wrong for every other consumer of
  `p_bucket_given_fv` (the trade machine, /projections/, the FA surfaces) which reads it at
  a genuine consensus FV. `efv_odds_calibration`'s own SCOPE LIMIT already documents this:
  on the native consensus key the same curve shows a flat +0.11 to +0.17 gap and no slope
  error, so the eFV-side instrument is the wrong instrument there. A refit would therefore
  have to be a SECOND, seam-scoped curve, not a replacement.

**Conclusion on the third option: a refit is not needed to settle this question, is largely
redundant with a measured lever that is built and not wired in, and the data does not
support it above the `regular` bucket.** REFIT NOT NEEDED; RE-LINK IS.

## 2.12 What should actually happen

1. **KEEP THE PIN.** Register the two-map split permanently: `_odds_grade` stays on
   `realized_implied_fv`, the board grade stays on `outcome_implied_fv`, and the coherence
   cost is a measured, deliberate choice rather than an unexamined leftover. The comment at
   `efv_score.py:1183-1190` should cite this gate rather than describing the re-key as
   merely unmeasured.
2. **The real defect is the link, and it is not the one this lane was pointed at.** Both
   keyings lose to a constant on both proper scores. `efv_odds_calibration` is built, gated
   and inert. Wiring it is worth roughly 1.5x the whole re-key question and moves p_bust in
   the direction the data actually asks for. That is an owner call with its own blast radius
   (344 served rows move >= 0.10, all upward, per `data/xfv_odds_dispersion_eval.json`), and
   it belongs to that lane, not this one.
3. **Do not re-open the re-key on the served-comparable cut.** Section 2.8 already priced it
   against its own null.

## 2.13 What this lane shipped

Nothing served. No production module was edited, no exporter or pipeline was run, and no
served number moved. Deliverables: this document, `tools/odds_grade_basis_lab.py`,
`data/odds_grade_basis_eval.json`, the registry row `xfv_odds_grade_basis` and its
`MODEL_GLOSSARY` mapping.
