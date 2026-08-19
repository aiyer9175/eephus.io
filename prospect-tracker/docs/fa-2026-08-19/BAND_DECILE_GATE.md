# GATE: WAR band per-decile width correction (2026-08-19)

FROZEN BEFORE FITTING. Every number in section 5 is filled with verbatim lab
output after the lab runs, or stays PENDING. No arm, frame, floor, or
estimator changes after this doc is written.

## 1. Defect

data/fa_gate1_eval.json band_scale_conditional_coverage.by_pred_decile
(shipped fa_bands_v1, in-sample on the 24,394-row Gate-1 residual panel):

    decile  n     coverage  z
    0       2440  0.84098   +5.538
    1       2439  0.92210   +22.486
    2       2440  0.88893   +13.983
    3       2439  0.85937   +8.433
    4       2439  0.82083   +2.681
    5       2440  0.71926   -8.872
    6       2439  0.63797   -16.653
    7       2440  0.63320   -17.090
    8       2439  0.75605   -5.052
    9       2439  0.92046   +21.982

Marginal 0.79991 (n 24394). Deciles 5-7 under-cover 0.63-0.72; extremes
over-cover. The marginal hides a conditional miscalibration the served band
inherits row by row.

## 2. Mechanism located

- Band model: fa_bands.py fa_bands_v1. log sigma = z'gamma/2, two-step OLS,
  per-side empirical shape on taus 0.05..0.95. Cleared its floor 2026-07-25
  (pinball -0.00778, floor 0.00229); permuted control collapsed sigma_sd
  1.0614 to 0.00991.
- Fit site: fa_backtest._fit_band_scale on the Gate-1 panel (targets
  2013-2025 ex 2020, warmups included; n 24394).
- Serve site: fa_market._war_band_offsets -> fa_bands.offsets with the
  band_scale dict persisted in data/fa_gate1_eval.json.
- fa_mc.py VERIFIED: consumes (p10, point, p90) paths only; the band does
  not live there; it is not edited.
- Decile basis: PREDICTED year-1 WAR (panel field `pred`). Ex ante at serve
  time: the served row has war1 before the band is drawn. Realized WAR never
  enters the assignment.

## 3. Frozen candidate

Per-decile multiplicative width correction on top of the shipped model.
Corrected quantile: q'_tau = mu + c_d * s * shape_q(side, tau), i.e. the
factor scales the spread around the location, location untouched.

- Decile edges: the 10th..90th percentiles of `pred` over the full panel
  (9 edges, published). Assignment d(pred) = bisect_right(edges, pred).
  Fixed constants at serve time.
- Per-decile factor c_d: smallest c in [0.25, 4.0] with train coverage of
  [mu + c*s*q10s, mu + c*s*q90s] >= 0.80 in decile d, found by bisection
  (60 iterations). Deciles with under 200 train rows keep c_d = 1.
- Isotonic constraint (monotone widths, no crossing): the corrected typical
  width W_d = c_d * w_d, with w_d = train-median uncorrected width
  s*(q90s - q10s) in decile d, must be non-decreasing in d. If violated,
  W_d is projected by weighted PAV (weights n_d) and c_d = W_d_pav / w_d.
  A higher predicted-WAR decile never gets a narrower typical band.
- Validation: leave-one-season-out over the 12 panel seasons (2013-2019,
  2021-2025). Factors refit per fold; held-out rows pooled; the AFTER table
  is 100% fold-out. The BEFORE table is recomputed on the identical
  edge-based bins (c = 1) so before/after share the binning exactly.
- Base model is NOT refit per fold. The correction rides on the shipped
  full-panel band_scale; the LOO isolates the correction's own overfit.
- Reconciliation precondition: applying the artifact band_scale to the
  captured panel with c = 1 must reproduce the artifact decile table within
  0.01 per decile. If it does not (panel drift since last persist), the base
  model is refit once with fa_backtest._fit_band_scale semantics and the
  BEFORE table restated from that refit; the clauses then read against the
  restated BEFORE. Declared here, before running.
- Served factors (if shipped): the same fit on ALL panel rows, constraint
  applied, published in the artifact.

## 4. Frozen clauses (all must pass to ship)

- C1 marginal: pooled fold-out coverage after correction in [0.78, 0.82].
- C2 direction: every decile satisfies |after - 0.80| < |before - 0.80|
  OR |after - 0.80| <= 0.02.
- C3 no worsening: every decile satisfies
  |after - 0.80| <= max(|before - 0.80|, 0.02).
- C4 zero-info control: permute the decile assignment vector across rows
  (seed 1), run the IDENTICAL LOO pipeline on the permuted groups, score
  the resulting factors on the TRUE decile table. Improvement metric:
  reduction in RMSE over the 10 deciles of (coverage - 0.80). The control's
  reduction must be < 0.25x the real arm's reduction.
- C5 guarantee-side fence: the guarantee band (twice-null, fenced,
  gate-2026-08-07-fa-guarantee-band.md) is not touched. No edit to
  fa_market.py, fa_bands.py guar_z, or data/fa_guar_band_eval.json. The
  correction map lives only under band_scale (the WAR side). Asserted by
  test_fa_band_decile.py.

Ship = C1 & C2 & C3 & C4 & C5: width map helper into fa_projection.py,
band_scale.decile_width_correction + eval section + generated_at persisted
into data/fa_gate1_eval.json. Any failure = loss-record here, no ship,
artifact untouched.

## 5. Results (verbatim lab output, band_decile_lab.py, 2026-08-19)

Reconciliation check: PASS. Applying the artifact band_scale to the
recaptured 24,394-row panel reproduced the artifact decile table to within
0.00041 everywhere (max |gap| at d2/d4):

    == reconciliation (c=1, artifact equal-count bins) ==
      d0: recomputed 0.84098  artifact 0.84098  gap +0.00000
      d1: recomputed 0.92213  artifact 0.92210  gap +0.00003
      d2: recomputed 0.88852  artifact 0.88893  gap -0.00041
      d3: recomputed 0.85943  artifact 0.85937  gap +0.00006
      d4: recomputed 0.82124  artifact 0.82083  gap +0.00041
      d5: recomputed 0.71915  artifact 0.71926  gap -0.00011
      d6: recomputed 0.63797  artifact 0.63797  gap -0.00000
      d7: recomputed 0.63305  artifact 0.63320  gap -0.00015
      d8: recomputed 0.75605  artifact 0.75605  gap -0.00000
      d9: recomputed 0.92046  artifact 0.92046  gap -0.00000
      reconciliation PASS

BEFORE (c=1, frozen edge bins) and AFTER (LOO fold-out):

    edges: [-0.1391, -0.0864, -0.0409, 0.0156, 0.092, 0.2112, 0.3951, 0.7197, 1.4019]
    == AFTER (LOO fold-out, real decile assignment) ==
      d0: before 0.84098 -> after 0.56639  (n 2440, z -23.285)
      d1: before 0.92210 -> after 0.88028  (n 2439, z +12.213)
      d2: before 0.88889 -> after 0.83190  (n 2439, z +4.213)
      d3: before 0.85943 -> after 0.80000  (n 2440, z +0.000)
      d4: before 0.82083 -> after 0.80074  (n 2439, z +0.091)
      d5: before 0.71915 -> after 0.80074  (n 2439, z +0.091)
      d6: before 0.63811 -> after 0.79918  (n 2440, z -0.101)
      d7: before 0.63305 -> after 0.79992  (n 2439, z -0.010)
      d8: before 0.75605 -> after 0.79992  (n 2439, z -0.010)
      d9: before 0.92049 -> after 0.80000  (n 2440, z +0.000)
      marginal after: 0.78790 (n 24394)
      decile RMSE vs 0.80: before 0.10272 -> after 0.07876  reduction 0.02396

Clauses:

    C1 marginal in [0.78,0.82]: 0.78790 -> PASS
    C2 every decile toward 0.80 or within 0.02: FAIL
       C2 fail d0: 0.84098 -> 0.56639
    C3 no decile further from 0.80 (0.02 dead-band): FAIL
    C4 permuted-decile control (seed 1): true-decile RMSE after 0.10312,
       reduction -0.00040 vs real 0.02396 (ratio -0.0165) -> PASS
       control marginal 0.79970
    C5 fence: held. No edit to fa_market.py, fa_bands.py, or
       data/fa_guar_band_eval.json; no decile map persisted anywhere.

Full-panel served-factor fit (diagnostic, NOT shipped):

    factors: [0.591727, 0.598215, 0.559382, 0.571567, 0.889145, 1.383627,
              1.544121, 1.42778, 1.121373, 0.684741]
    corrected median widths: [0.2984, 0.2984, 0.2984, 0.3398, 0.6097,
                              1.2056, 1.8958, 2.7308, 3.7943, 5.0268]
    monotone: True
    in-sample per-decile: {0: 0.56639, 1: 0.87905, 2: 0.83231, 3: 0.8,
                           4: 0.79992, 5: 0.80033, 6: 0.8, 7: 0.80033,
                           8: 0.80033, 9: 0.8}
    in-sample marginal 0.78786

VERDICT: LOSS-RECORD. C2 and C3 fail on decile 0. Nothing ships:
fa_projection.py gets no width map, data/fa_gate1_eval.json is not
re-persisted, the served band is unchanged.

## 6. Failure mechanism (read from the frozen run, no new arms fit)

Deciles 5-8 are FIXED by the candidate (0.63-0.76 -> 0.799-0.801 fold-out)
and d9's over-cover is fixed too (0.920 -> 0.800). The single failure is the
frozen isotonic-width constraint at the bottom: uncorrected median widths
are NON-monotone across d0-d2 (w0 0.504 > w1 0.499; both bands sit near the
narrow end where the shipped sigma barely varies), so after the
unconstrained solve set c1, c2 to strong shrinks (d1 covers 0.922), the PAV
projection pooled W0-W2 to one value (0.2984) and dragged d0's factor to
0.592 when its coverage 0.841 wanted only a mild shrink. d0 collapses to
0.566, exactly the constraint's pooling, not the estimator.

The pooled-marginal cost is also visible: marginal 0.79991 -> 0.78790, all
of it d0's deficit.

Not attempted here (would be a post-hoc arm change): re-freezing the
constraint as ties-allowed only where UNCORRECTED widths are already
monotone, or exempting deciles whose uncorrected widths differ by under
some epsilon. That is a NEW gate with a new frozen doc if pursued. The
mid-decile fix itself is clearly available (d3-d9 all land within 0.001 of
nominal fold-out); the open question is purely the bottom-decile
constraint geometry.

