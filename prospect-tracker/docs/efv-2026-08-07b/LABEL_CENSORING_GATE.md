# Lane B: label censoring gate (eFV first-6yr bWAR label)

Program: master plan 2026-08-07b, Lane B (defect D2).
Owner of this doc: the Lane B1 agent. Written BEFORE the measurement ran.

Status line is updated in place. Registration below is frozen: nothing in section 1
through 4 was edited after the first run.

---

## 1. What is being measured, and why

`efv_dataset._label_6yr` (`efv_dataset.py:894-914, pre-B4-edit :879-894`) right-censors the first-6-MLB-season
summed-bWAR label like this:

```python
rate = obs_sum / n_obs if n_obs else 0.0
n_missing = TARGET_SEASONS - n_obs
censored_target = round(obs_sum + n_missing * rate, 3)
weight = round(n_obs / TARGET_SEASONS, 3)
```

The module header (`efv_dataset.py:30`, pre-B4-edit) called this "KM-from-the-start". It is not a
Kaplan-Meier estimator: there is no survival function, no risk set and no hazard on this
path. It is an observed-rate tail projection with an exposure weight, and it assumes a
FLAT per-season WAR rate across the six-year window.

Two documented facts point in opposite directions and neither has ever been measured on
this label:

- for survivors, seasons 4 to 6 carry 58.9 percent of WAR mass
  (`docs/PITCHER_LABEL_LEDGER.md`), which makes a flat rate UNDER-state;
- a large share of debuted players stop accumulating before season 6, which makes a flat
  rate OVER-state.

`target_censored` is the eFV fit target (`efv_model.py:14`), so the sign and size of this
error propagates into the served grades, into `rank_calibration`, and into the realized
bucket the reliability chain scores against (`efv_reliability._realized_bucket:91-95`).

## 2. Design (pre-registered)

**Population.** Every FULLY RESOLVED debuted row in the shipped training matrices
(`data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`), i.e. `kind == "debuted"`
and `debut_year + 5 <= RESOLVED_THROUGH (2025)`, so `debut_year <= 2020`. Bust rows are
excluded: they carry a hardcoded 0.0 target and never ride the projection.

**Procedure.** For each row and for each n in {2, 3, 4, 5}:

1. set `efv_dataset.RESOLVED_THROUGH = debut_year + n - 1` (module global, read inside
   `_label_6yr`), which makes the shipped function observe exactly n seasons and take the
   censored branch;
2. call the SHIPPED `efv_dataset._label_6yr` on the player's real `career_war` season map.
   No reimplementation. A reimplementation that drifts from production measures the wrong
   thing;
3. compare `target_censored` (the projection) to the TRUE six-year total, which is the
   same function run at the real `RESOLVED_THROUGH`.

Error is defined as `err = projected - true`. Positive means the projection OVER-states.

**Strata, all reported separately.**

- n_obs = 2, 3, 4, 5.
- side (hit, pit).
- debut-year cohort.
- REALIZED MAGNITUDE, mandatory: bins of TRUE six-year WAR, cut on the shipped realized
  bucket edges so the bins mean something downstream: `(-inf, 0)`, `[0, 3)`, `[3, 9)`,
  `[9, 15)`, `[15, 24)`, `[24, inf)`. Those are `efv_reliability.BUCKET_EDGES`
  (0.5/1.5/2.5/4.0 annual) times `TARGET_SEASONS = 6`, with the negative tail split out.
  A pooled mean is known to hide a two-sided top-tail swap, so the pooled number is
  reported LAST and never alone.

**Uncertainty.** Every reported mean signed bias carries a percentile bootstrap 95 percent
band, B = 5000, resampled within the stratum, seeded for reproducibility. Strata with
n < 15 are reported but flagged `thin` and are not eligible to trigger the verdict.

**Secondary outputs, required by other lanes.**

- Realized-bucket changes under the projection versus the true label
  (`efv_reliability._realized_bucket`), counted and given as a confusion matrix. Lane C
  needs this: if the miscalibration it is chasing is partly the label's own error, that is
  the finding.
- Crossings of the two AUC bars, `efv_model._CONTRIB_WAR = 3.0` and
  `efv_model._STAR_WAR = 10.0` (`efv_model.py:598-600`), in both directions, with the
  induced base-rate shift. Lane I7 mechanism 1 needs this.
- Induced label noise, expressed so Lane I7 can multiply through it: SD of the error,
  Pearson and Spearman correlation between projected and true label per stratum, and the
  classical rank-attenuation multiplier `rho_observed / rho_true ~= corr(proj, true)`
  under the stated independent-noise assumption, with the measured `corr(err, true)`
  printed beside it so the reader can see how badly that assumption is violated.
- A production-weighted view (`weight = n_obs / 6`, the shipped `sample_weight`), because
  that is the leverage the censored block actually gets in the fit.
- The population-mix estimate: apply the per-n, per-side measured bias to the 833 rows the
  shipped matrices actually carry at `observed_seasons` 2 to 5, to state the total label
  distortion currently in the training frame.

**Diagnostic only, not a build.** The realized per-season-index share profile (mean share
of six-year WAR realized in season k) is reported to EXPLAIN the direction of any bias. It
is a diagnostic. Building a replacement label is B2, it is explicitly a wave-2 decision,
and it does not run in this wave under any circumstance.

## 3. Success criterion (pre-registered, frozen before the run)

Let `b` be a stratum's mean signed error and `SD_true` the SD of true six-year WAR in that
stratum.

- **NULL (the stop clause fires).** Every n_obs x side stratum AND every magnitude bin has
  a bootstrap 95 percent CI on `b` that contains 0. Then B2 does not run, the naming is
  fixed, and the result is handed to Lane C as "the flat-rate projection is unbiased at
  the resolution this data supports".
- **DETECTABLE BUT IMMATERIAL.** At least one eligible stratum's CI excludes 0, but no
  eligible stratum satisfies the materiality test below. B2 still does not run in this
  wave. The recommendation to Lane C is "carry the measured size as a known label error,
  do not rebuild".
- **MATERIAL BIAS.** At least one eligible n_obs x side stratum or magnitude bin has a CI
  excluding 0 AND satisfies materiality: `|b| >= 1.0` WAR absolute, or `|b| >= 0.25 *
  SD_true`. Then Lane B2 is RECOMMENDED for wave 2, with its own gate doc, a rank-identical
  level twin, a random-label null band and a permutation p-value. It is still not built
  here.

Marginal is FAIL. A point estimate inside its own bootstrap band is a NULL and recording a
null is a successful outcome.

## 4. B3, the lambda pin (asserted, not assumed)

`efv_model._BLEND_LAMBDA_RESELECT` (`efv_model.py:581`) must read `{"hit": 0.70,
"pit": 0.57}`. The pitcher entry used to be `None`, which meant served pitcher lambda was
re-derived every run by `rank_calibration("pit")`, whose target IS `target_censored`. The
lab asserts the pin and prints what it actually read. A label experiment run against an
unpinned lambda silently moves the served blend.

## 5. Artifacts

- lab: `tools/efv_label_censoring_lab.py`
- eval: `data/xfv_label_censoring_eval.json`
- this doc

The lab writes exactly one file under `data/`. It does not fit, rescore or rebuild
anything, and it restores `efv_dataset.RESOLVED_THROUGH` after every patch.

---

## 6. RESULT

Run: `python tools/efv_label_censoring_lab.py`. Artifact:
`data/xfv_label_censoring_eval.json`. Every number below is a key in that artifact.

### 6.0 Pool and reconciliation

988 fully resolved debuted rows (hit 460, pit 528), debut years 2011 through 2020, from
matrices stamped 2026-08-07T22:16Z (hitter 1,917 rows / 845 debuted, pitcher 2,040 / 981).
Ground truth was recomputed with the shipped function at the real horizon and reconciled
against the matrices' own `target_resolved`: **988 of 988 match, 0 mismatch**
(`ground_truth_reconciliation`). The measurement is on the production label, not a copy
of it.

### 6.1 B3, the lambda pin: CONFIRMED

`efv_model._BLEND_LAMBDA_RESELECT` reads `{"hit": 0.70, "pit": 0.57}`
(`b3_pin_check.read`, source `efv_model.py:581`). The pin holds, so pitcher lambda is not
re-derived per run against `target_censored` and nothing in this lab could have moved the
served blend. `b3_pin_check.pin_ok = true`.

### 6.2 Primary strata: the projection UNDER-states, monotonically in span

`by_n_obs_and_side`. Error is `projected - true`, in WAR.

| n_obs | side | n | mean bias | bootstrap CI95 | RMSE | SD(true) | bias / SD | material |
|---|---|---|---|---|---|---|---|---|
| 2 | hit | 460 | **-1.691** | [-2.091, -1.267] | 4.857 | 7.471 | -0.226 | **yes** |
| 2 | pit | 528 | **-0.839** | [-1.169, -0.522] | 3.898 | 4.726 | -0.177 | no |
| 3 | hit | 460 | **-0.964** | [-1.267, -0.658] | 3.447 | 7.471 | -0.129 | no |
| 3 | pit | 528 | **-0.450** | [-0.706, -0.208] | 2.928 | 4.726 | -0.095 | no |
| 4 | hit | 460 | **-0.340** | [-0.541, -0.135] | 2.221 | 7.471 | -0.046 | no |
| 4 | pit | 528 | **-0.184** | [-0.347, -0.028] | 1.874 | 4.726 | -0.039 | no |
| 5 | hit | 460 | -0.062 | [-0.168, +0.043] | 1.172 | 7.471 | -0.008 | no |
| 5 | pit | 528 | -0.047 | [-0.136, +0.039] | 1.040 | 4.726 | -0.010 | no |

Six of the eight primary strata have a bootstrap CI that excludes zero, all six negative.
Only n_obs = 5 is a null. The stop clause therefore does NOT fire.

The direction settles the question section 1 posed. The two documented facts do point in
opposite directions, and the season-mass effect wins outright: the realized per-season
share profile measured here (`season_share_profile_diagnostic`) is
0.080 / 0.138 / 0.185 / 0.215 / 0.202 / 0.179 pooled, so **seasons 4 to 6 carry 59.6
percent of WAR mass** (hit 60.07, pit 58.83). The `PITCHER_LABEL_LEDGER` figure of 58.9
percent reproduces to within 0.1 on the pitcher side.

Attrition is real and in fact LARGER than the plan's premise, and it still does not offset
the mass effect. On the same 988 rows (`attrition_diagnostic`), **46.4 percent have no MLB
season-6 line at all** (hit 40.9, pit 51.1) and 25.7 percent have no line in any of seasons
4 through 6, against the plan's quoted 32.8 percent vanish rate. The reason the flat rate
still under-states is that the players who vanish are near-zero contributors whose
projected tail was near zero anyway, while the players who survive are the ones whose real
seasons 4 to 6 are their best. Attrition removes small positive numbers; the mass effect
removes large ones.

### 6.3 Magnitude, the mandatory cut: this is where the damage is

`by_n_obs_and_magnitude`, n_obs = 2. Bins are the shipped realized-bucket edges in
six-year WAR.

| bin (true 6yr WAR) | side | n | mean bias | CI95 | mean true |
|---|---|---|---|---|---|
| neg | hit | 160 | -0.296 | [-0.525, -0.069] | -0.743 |
| 0 to 3 | hit | 108 | **+0.477** | [+0.011, +0.970] | +1.081 |
| 3 to 9 | hit | 87 | -2.547 | [-3.445, -1.608] | +5.644 |
| 9 to 15 | hit | 54 | -4.516 | [-5.943, -3.029] | +11.528 |
| 15 to 24 | hit | 36 | **-7.032** | [-9.354, -4.673] | +18.016 |
| 24+ | hit | 15 | -4.220 | [-8.075, -0.260] | +29.460 |
| neg | pit | 204 | -0.336 | [-0.509, -0.159] | -0.619 |
| 0 to 3 | pit | 168 | +0.196 | [-0.146, +0.545] | +1.017 |
| 3 to 9 | pit | 104 | -1.343 | [-2.189, -0.456] | +5.659 |
| 9 to 15 | pit | 37 | -3.106 | [-5.307, -0.760] | +11.276 |
| 15 to 24 | pit | 13 | -9.989 | [-13.555, -6.022] | +17.337 (thin, not eligible) |
| 24+ | pit | 2 | -11.430 | [-15.150, -7.710] | +34.620 (thin, not eligible) |

The pooled mean did hide the shape, exactly as the pitcher-label ledger warned. The label
is not uniformly shifted, it is **stretched toward zero at the top and away from zero at
the bottom**:

- negative-WAR rows get pushed FURTHER negative (a rough rookie rate extrapolated four
  more years, when in reality those players stop being given plate appearances);
- the 0 to 3 bin is the only positive bias on the board, small and marginal;
- from 3 WAR upward the under-statement grows with the truth, reaching -7.03 WAR for
  hitters in the 15 to 24 band and -9.99 for the (thin) pitcher band.

This is a top-tail compression of the training target, not noise around it.

### 6.4 Robustness

- **Debut cohort** (`by_n_obs_and_cohort`, n_obs = 2): negative in 19 of 20 side-by-year
  cells. The single positive is hit 2015 at +0.130 with a CI straddling zero.
- **Transferability** (`recent_cohort_2017_2020`): the cohorts closest to the rows that
  actually ride the projection today are WORSE, not better. n=2 hit -1.946
  [-2.557, -1.371], n=2 pit -1.003 [-1.462, -0.560]; both material.
- **Short-season confound** (`pre_covid_cohort_2011_2014`): the 60-game 2020 season
  depresses whichever window slot it lands in, so debut years 2011 to 2014, whose windows
  end 2016 to 2019, are the clean control. The bias survives: n=2 hit -2.062
  [-2.846, -1.285] (material), n=2 pit -0.958 [-1.607, -0.347]. Not a COVID artifact.
- **Production fidelity** (`terminal_resolution_sensitivity`): only 4 of the 988 pooled
  players carry a career-terminal transaction and only 1 exclusion is triggered across all
  spans, so the `build_matrix:1214-1220` terminal-resolution escape hatch does not
  meaningfully select the population that rides the projection. Every stratum's bias is
  unchanged to three decimals.
- The per-stratum `weighted_mean_bias` field is degenerate by construction: the fit weight
  `n_obs/6` is constant within an n_obs stratum. The weighting only matters across strata,
  and that is reported in 6.7.

### 6.5 Downstream 1: realized bucket changes (Lane C needs this)

`downstream`, comparing `efv_reliability._realized_bucket(projected)` with
`_realized_bucket(true)` on the same 988 players.

| n_obs | rows changing bucket | up | down |
|---|---|---|---|
| 2 | 299 of 988 (**30.3 percent**) | 101 | 198 |
| 3 | 256 (25.9 percent) | 93 | 163 |
| 4 | 162 (16.4 percent) | 67 | 95 |
| 5 | 86 (8.7 percent) | 43 | 43 |

Hitters at n=2 are worse than the pool: 165 of 460 change bucket (35.9 percent), 120 down
against 45 up. **Roughly a third of the recently censored training rows are in the wrong
outcome bucket, two to one in the pessimistic direction.** The reliability chain scores its
served distribution against this bucket, so some unknown part of the D3 miscalibration is
the label's own error, and Lane C1 should treat that as the leading hypothesis rather than
recalibrating on top of it.

### 6.6 Downstream 2: the AUC bars (Lane I7 mechanism 1 needs this)

`downstream.*.contributor_war_ge_3` and `.star_war_ge_10`, bars from
`efv_model._CONTRIB_WAR` and `._STAR_WAR` (`efv_model.py:598-600`).

| bar | n_obs | true positives | projected positives | false promote | false demote | flip rate |
|---|---|---|---|---|---|---|
| WAR >= 3 | 2 | 348 | 286 | 63 | 125 | 19.0 percent |
| WAR >= 3 | 3 | 348 | 310 | 46 | 84 | 13.2 percent |
| WAR >= 3 | 4 | 348 | 338 | 36 | 46 | 8.3 percent |
| WAR >= 3 | 5 | 348 | 352 | 18 | 14 | 3.2 percent |
| WAR >= 10 | 2 | 136 | 82 | 24 | 78 | 10.3 percent |
| WAR >= 10 | 3 | 136 | 112 | 28 | 52 | 8.1 percent |
| WAR >= 10 | 4 | 136 | 117 | 19 | 38 | 5.8 percent |
| WAR >= 10 | 5 | 136 | 131 | 15 | 20 | 3.5 percent |

The star bar loses **40 percent of its true positives at n_obs = 2** (136 down to 82;
hitters 95 down to 52). Any star-AUC computed on a frame containing 2023 and 2024 debuts is
computed against a positive class that is missing a large, non-random share of its members,
and the missing ones are the highest-WAR players in the pool. That is a class-definition
defect, not a discrimination result.

### 6.7 Induced label noise, in the form Lane I7 can multiply through

`induced_label_noise` (pooled, both sides).

| n_obs | SD(err) | SD(true) | noise/signal var | Pearson(proj, true) | Spearman(proj, true) | corr(err, true) |
|---|---|---|---|---|---|---|
| 2 | 4.195 | 6.255 | 0.450 | **0.7575** | 0.7123 | -0.4623 |
| 3 | 3.106 | 6.255 | 0.247 | 0.8720 | 0.8636 | -0.3370 |
| 4 | 2.028 | 6.255 | 0.105 | 0.9468 | 0.9406 | -0.2098 |
| 5 | 1.103 | 6.255 | 0.031 | 0.9844 | 0.9822 | -0.1062 |

Use `Pearson(proj, true)` as the attenuation multiplier: a correlation measured against the
projected label is roughly that fraction of the same quantity measured against the true
label. **Read the caveat**: `corr(err, true)` is -0.46 at n_obs = 2, so the noise is
strongly negatively correlated with the truth and the classical independent-noise
assumption is violated. The multiplier is an upper bound on retained information rather
than an exact correction, and the violation is itself the top-tail compression from 6.3.

### 6.8 The population estimate, on the rows that actually ride this today

`population_mix_estimate`. The shipped matrices carry **833 censored debuted rows** at
`observed_seasons` 2 to 5 (hit 91/92/127/72, pit 119/126/101/105), which reproduces the
plan's 833 (hit 382, pit 451) exactly.

Applying the measured per-n, per-side bias to that mix:

- expected total label deficit: **-470.4 WAR** across 833 rows;
- expected mean deficit: **-0.565 WAR per row**;
- after the shipped `sample_weight = n_obs/6`: **-206.4 WAR** of weighted deficit.

Those rows are the 2021 through 2024 debuts, which is the recent regime the board serves.

## 7. VERDICT against the section 3 criterion

**MATERIAL BIAS.** 29 of 48 eligible strata have a bootstrap CI excluding zero, and 12
satisfy the pre-registered materiality test (`strata_material` in the artifact): `n2_hit`
plus every hitter magnitude bin at n=2, `n2_pit_neg`, `n2_pit_3to9`, `n2_pit_9to15`,
`n3_hit_neg`, `n3_hit_0to3`. The stop clause does not fire.

Restating the pre-registered scale: the whole-stratum effect is material on hitters at
n_obs = 2 only (-1.69 WAR, above the 1.0 WAR absolute bar though below 0.25 * SD(true) =
1.87). The magnitude-conditional effect is much larger and is material on both sides. The
honest summary is: **the pooled mean bias is modest, and the conditional bias at the top of
the outcome distribution is severe.**

### 7.1 What this does and does not license

- **B2 is RECOMMENDED for wave 2 and is NOT built here.** The plan says so and this doc
  holds to it: a replacement label needs its own gate doc, a rank-identical level twin, a
  random-label null band and a permutation p-value. None of that ran.
- Do not over-read the rank consequence. `PITCHER_LABEL_LEDGER` bounds the whole censored
  pitcher block at Spearman 0.9441 on the served board (deleting it entirely), so a better
  label cannot move the pitcher ordering more than that. **The value of a corrected label
  is in the LEVEL and the BUCKET, not in the rank**, and that is where 6.5 through 6.8
  point. B2's gate should be scored on the truncation error measured here, which is direct,
  and should treat any rank delta as a secondary diagnostic against its own floor.
- The obvious candidate remains the per-season-index share profile in 6.2, forward-chained
  so a fold never sees its own cohort. The profile is nearly identical on the two sides
  (0.601 vs 0.588 for seasons 4 to 6), which is mild evidence that a pooled profile would
  be estimable without per-side thinning.

### 7.2 Hand-off to Lane C

C1 asked whether the D3 miscalibration is the diagnostic measuring its own label. The
answer this lane can give: **30.3 percent of censored-equivalent rows sit in the wrong
realized bucket at n_obs = 2 and 25.9 percent at n_obs = 3, skewed roughly two to one
pessimistic.** That is large enough to produce a real miscalibration on its own. Lane C
should re-run the reliability chain with the resolved-only pool before recalibrating
anything against the censored bucket.

## 8. B4, the naming

`efv_dataset.py` no longer calls this Kaplan-Meier. The module header CENSORING block now
reads "observed-rate tail projection with an exposure weight", carries the measured bias,
and states that the legacy artifact keys spelling `km_censored` are kept for consumers.
`_label_6yr` carries the same correction in its own docstring.

Artifact KEYS were deliberately not renamed. `full_pool_km_censored` and
`debuted_km_censored` (`efv_dataset.py:1406-1407`) are read by
`tools/efv_arias_replay_lab.py:485` and quoted in `docs/CURRENT_INGESTION.md`; renaming
them is a consumer-breaking change and is not part of a naming correction.

Remaining occurrences of the phrase, reported for the orchestrator rather than edited,
because they live in files this lane does not own: `efv_model.py:14`, `:2407`, `:2520`,
`:2536`; `efv_board_scale.py:34`, `:188`; `source_backtest.py:338`;
`tools/_sweep_calibration.py:43`, `:155`; `tools/efv_mde_lab.py:352`;
`tools/efv_isotonic_lab.py:22`; `tools/efv_cohort_lambda_lab.py:17`;
`tools/efv_scoreboard.py:517`; `tools/efv_pitcher_stuff_lab.py:515`;
`tools/efv_pitcher_label_harness.py:36`; `docs/EFV_EVAL_BASIS_LEDGER_2026-08-07.md:60`;
`docs/xfv-phase1-plan.md:152`, `:273`, `:298`, `:308`; `docs/SURROGATE_LABEL_PROGRAM.md:118`,
`:128`; `docs/CURRENT_INGESTION.md:26`, `:44`; `docs/master-plan-2026-08-04d-omnibus.md:461`;
`MODEL_REGISTRY.md:175`. (`eta.py`, `eta_backtest.py` and the `eta` registry row are
genuine Kaplan-Meier and must NOT be touched.)

## 9. Separate finding, out of lane

The same module header states `COHORT ... debut years 2017-2023` (`efv_dataset.py:14`)
while `DEBUT_YEARS = tuple(range(2011, 2025))` (`efv_dataset.py:253`) and the shipped
matrices carry 2011 through 2024 debuts. The header's cohort line is stale by six years on
one end and one on the other. Not fixed here: it is not the naming defect this lane owns.

