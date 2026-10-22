# Null comparator sweep: results

Registration: `docs/NULL_COMPARATOR_SWEEP.md`. Lab: `tools/null_comparator_sweep_lab.py`. Artifact: `data/null_comparator_sweep.json`. Run at 2026-10-22T04:31:36Z (the one registered run).

delta = loss(null) minus loss(model): positive means the model beats the null. BEATS: CI95 above zero. TIES: CI95 contains zero. LOSES: CI95 below zero. A cell whose planted-better or planted-worse instrument check fails is VOID.

## Census

- action:COVERED: 68
- action:DEFERRED: 7
- action:NA: 23
- action:RUN: 4
- planted_recovery_yes: 3
- provisional:ANALYTIC: 3
- provisional:MISSING: 2
- provisional:PRESENT: 42
- validated:MISSING: 6
- validated:NA: 13
- validated:PRESENT: 36

## Runs

### S3

Frame: tools/fit_draft_slot_curve.py: first-8 curve fit on 2005-14 picks 1-500, scored on the 2015-18 holdout; metric = the artifact's holdout_mae (unweighted mean over buckets of |bucket prediction - realized bucket mean|); bootstrap stratified by bucket. Label: fwar.

Reproduction: {"holdout_mae_fitted_first8": 2.73}; stored {"label": "fwar", "holdout_mae_fitted_first8": 2.73}.

- holdout_bucket_mae: n 1968, model 2.7299; instrument PASS
  - FLAT: null 1.7123, delta (null minus model) -1.0176, CI95 -2.3103 to +0.6581: TIES
    - secondary per-pick MSE: null 7.6951, delta -0.4249, CI95 -1.4382 to +0.8385: TIES
  - ZERO: null 2.3852, delta (null minus model) -0.3446, CI95 -1.7112 to +1.2894: TIES
    - secondary per-pick MSE: null 7.9012, delta -0.2188, CI95 -1.3840 to +1.1907: TIES

Disclosed confound: the holdout is right-censored (a 2018 pick debuting 2022 has 4 observed seasons by 2025) and every window holds 2020, so its level reads low; the artifact names it a diagnostic, not the ship criterion.

### S1

Frame: fa_backtest.run_projection_gate(persist=False) WAR pool, targets [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025], absent target season = 0 for every arm. Label: fwar.

Reproduction: {"war_mae_model": 0.492364893126252, "war_mae_base": 0.5874022151850201, "n": 20721}; stored {"label": "ewar_v2", "war_mae_model": 0.5156555204307136, "war_mae_base": 0.6242164570411276, "n": 20721}.

- pooled: n 20721, model 0.4924; instrument PASS
  - ZERO: null 0.5784, delta (null minus model) +0.0861, CI95 +0.0682 to +0.1046: BEATS
  - POP_MEAN: null 0.766, delta (null minus model) +0.2737, CI95 +0.2600 to +0.2877: BEATS
- hit: n 8833, model 0.6171; instrument PASS
  - ZERO: null 0.7862, delta (null minus model) +0.1692, CI95 +0.1355 to +0.2057: BEATS
  - POP_MEAN: null 0.9371, delta (null minus model) +0.3200, CI95 +0.2950 to +0.3466: BEATS
- pit: n 11888, model 0.3997; instrument PASS
  - ZERO: null 0.424, delta (null minus model) +0.0243, CI95 +0.0053 to +0.0423: BEATS
  - POP_MEAN: null 0.6389, delta (null minus model) +0.2392, CI95 +0.2261 to +0.2527: BEATS

### S2

Frame: proj_eval row-matched frame, bases [2017, 2018, 2019, 2021], horizons 1-5, label seasons <= 2025, absent target season = 0 for every arm. Label: fwar.

Reproduction: {"1": {"n": 8053, "champion_mae": 0.5142, "challenger_mae": 0.4925}, "2": {"n": 8053, "champion_mae": 0.4637, "challenger_mae": 0.428}, "3": {"n": 8053, "champion_mae": 0.4103, "challenger_mae": 0.3743}, "4": {"n": 8053, "champion_mae": 0.3604, "challenger_mae": 0.3305}, "5": {"n": 8053, "champion_mae": 0.3287, "challenger_mae": 0.3128}}; stored {"block": "rowmatch_champion_vs_challenger", "label": "pre-epoch (2026-08-19)", "champion_mae": {"1": 0.5988, "2": 0.5188, "3": 0.4635, "4": 0.3957, "5": 0.3692}, "challenger_mae": {"1": 0.5846, "2": 0.4917, "3": 0.4356, "4": 0.3758, "5": 0.3586}, "n": 8053}.

challenger_proj_lgbm:
- h1: n 8053, model 0.4925; instrument PASS
  - ZERO: null 0.6177, delta (null minus model) +0.1252, CI95 +0.1045 to +0.1488: BEATS
  - CARRY_543_FLAT: null 0.6252, delta (null minus model) +0.1327, CI95 +0.1205 to +0.1462: BEATS
- h2: n 8053, model 0.428; instrument PASS
  - ZERO: null 0.4683, delta (null minus model) +0.0403, CI95 +0.0267 to +0.0547: BEATS
  - CARRY_543_FLAT: null 0.6488, delta (null minus model) +0.2207, CI95 +0.2047 to +0.2356: BEATS
- h3: n 8053, model 0.3743; instrument PASS
  - ZERO: null 0.4034, delta (null minus model) +0.0291, CI95 +0.0162 to +0.0424: BEATS
  - CARRY_543_FLAT: null 0.646, delta (null minus model) +0.2717, CI95 +0.2523 to +0.2906: BEATS
- h4: n 8053, model 0.3305; instrument PASS
  - ZERO: null 0.3378, delta (null minus model) +0.0073, CI95 -0.0051 to +0.0198: TIES
  - CARRY_543_FLAT: null 0.6532, delta (null minus model) +0.3227, CI95 +0.2999 to +0.3459: BEATS
- h5: n 8053, model 0.3128; instrument PASS
  - ZERO: null 0.3273, delta (null minus model) +0.0145, CI95 +0.0028 to +0.0265: BEATS
  - CARRY_543_FLAT: null 0.6569, delta (null minus model) +0.3441, CI95 +0.3186 to +0.3692: BEATS
- pooled_h1_h5: n 40265, model 0.3876; instrument PASS
  - ZERO: null 0.4309, delta (null minus model) +0.0433, CI95 +0.0309 to +0.0562: BEATS
  - CARRY_543_FLAT: null 0.646, delta (null minus model) +0.2584, CI95 +0.2405 to +0.2755: BEATS

champion_decay:
- h1: n 8053, model 0.5142; instrument PASS
  - ZERO: null 0.6177, delta (null minus model) +0.1035, CI95 +0.0811 to +0.1285: BEATS
  - CARRY_543_FLAT: null 0.6252, delta (null minus model) +0.1111, CI95 +0.1000 to +0.1228: BEATS
- h2: n 8053, model 0.4637; instrument PASS
  - ZERO: null 0.4683, delta (null minus model) +0.0046, CI95 -0.0118 to +0.0213: TIES
  - CARRY_543_FLAT: null 0.6488, delta (null minus model) +0.1850, CI95 +0.1707 to +0.1986: BEATS
- h3: n 8053, model 0.4103; instrument PASS
  - ZERO: null 0.4034, delta (null minus model) -0.0069, CI95 -0.0234 to +0.0097: TIES
  - CARRY_543_FLAT: null 0.646, delta (null minus model) +0.2357, CI95 +0.2181 to +0.2522: BEATS
- h4: n 8053, model 0.3604; instrument PASS
  - ZERO: null 0.3378, delta (null minus model) -0.0226, CI95 -0.0369 to -0.0074: LOSES
  - CARRY_543_FLAT: null 0.6532, delta (null minus model) +0.2928, CI95 +0.2708 to +0.3145: BEATS
- h5: n 8053, model 0.3287; instrument PASS
  - ZERO: null 0.3273, delta (null minus model) -0.0014, CI95 -0.0159 to +0.0141: TIES
  - CARRY_543_FLAT: null 0.6569, delta (null minus model) +0.3282, CI95 +0.3049 to +0.3522: BEATS
- pooled_h1_h5: n 40265, model 0.4154; instrument PASS
  - ZERO: null 0.4309, delta (null minus model) +0.0154, CI95 +0.0010 to +0.0312: BEATS
  - CARRY_543_FLAT: null 0.646, delta (null minus model) +0.2306, CI95 +0.2141 to +0.2467: BEATS

## Row findings

- fa_projection_marcel (S1): BEATS_EVERY_NULL; {"ZERO": "BEATS", "POP_MEAN": "BEATS"}
- fa_war_paths_decay (S2): BEATS_EVERY_NULL; {"ZERO": "BEATS", "CARRY_543_FLAT": "BEATS"}
- mlb_projections_vets (S2): BEATS_EVERY_NULL; {"ZERO": "BEATS", "CARRY_543_FLAT": "BEATS"}
- draft_slot_curve (S3): TIES_OR_LOSES_NULL; {"FLAT": "TIES", "ZERO": "TIES"}

