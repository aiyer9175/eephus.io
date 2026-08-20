# V3: model-class re-adjudication on the 11-fold basis (registered 2026-08-19)

STATUS: COMPLETE 2026-08-19. Clauses were frozen BEFORE the lab existed and were not
edited. Results below are filled only with verbatim lab output (the lab-written artifact).
Outcome: A0 passed, all controls held, ALL FOUR CELLS NULL, permanent close invoked.

## Why this is admissible

xfv_model_class_sweep closed the model-class question ("ridge survives all 22 challengers")
on the RETIRED 4-fold 2020-2023 basis (retired 2026-08-06, xfv_scoreboard_eval
legacy_4fold_footnote). The 2026-08-14 planning record notes the pitcher ensemble arm
(mean of ridge + monotone-lgbm predictions) read 0.2612 vs blend 0.2584 and was never
adjudicated. The reopen conditions are met twice over: retired-basis verdict plus a new owner
instruction (2026-08-19). This is ONE registered attempt.

## Arms (frozen)

Per side (hit, pit), against the shipped ridge configuration reproduced bit-exact:
- A1: monotone LightGBM (the existing _fit_lgbm_mono configuration, unchanged),
- A2: ensemble = mean(ridge, monotone-lgbm) OOS predictions,
- A0: reproduction control: the lab's ridge path must reproduce the shipped per-fold OOS
  predictions bit-exact (tolerance 1e-9 on pooled rho) or NOTHING below is read.

No other model class, no hyperparameter search, no feature changes (the 39-arm feature
closure stands; all arms consume the identical shipped feature matrix).

## Frame (frozen)

The current 11-fold pair-weighted chain, identical rows per side as the shipped eval
(data/xfv_eval.json / xfv_eval_pitcher.json basis). Primary population: debuted_km. The blend
is NOT touched: arms are compared at the MODEL LEG (the same leg the ridge occupies); lambda
stays pinned.

## Statistics and floors (frozen)

- Primary: pooled Spearman rho delta (arm minus ridge), player-clustered paired bootstrap,
  B=2000, E_cond primary. Floors derived ON THIS FRAME by the lab itself before any arm is
  read; no floor is borrowed.
- Secondary: E_refit at B=200 refit draws (LightGBM refit cost makes B=2000 infeasible; the
  reduced-B penalty is disclosed: bootstrap sd carries ~1/sqrt(2B) relative error, ~5% at
  B=200). Reported beside, never substituted for the registered primary.
- Diagnostics (non-gating but SHIP-BLOCKING if violated, clause S3): pooled MAE non-worse
  than ridge by more than its own bootstrap CI; tail MAE (top decile of realized WAR)
  non-worse (the 2026-06-25 and E2b-narrow failure class).
- Family: {hit, pit} x {A1, A2} = 4 cells, Holm.

## Controls (frozen)

- C-a: A0 reproduction as above.
- C-b: zero-information twin: an A1 trained on row-permuted features must NOT clear its floor
  on any cell; if it does, the harness is broken and nothing is read.
- C-c: fold-coverage check: every fold contributes OOS rows for every arm (no silent fold
  drops).

## Ship rule (frozen)

An arm ships only if: clears its E_cond floor under Holm on its side, AND passes S3
diagnostics, AND the shipped-config swap is implemented behind a registered flag with the
serve chain touched at ALL FOUR scoring sites (run, run_live, run_backgrade, score_history;
the 2026-08-13b lesson) plus epoch/fingerprint discipline if any served grade moves.

## Permanent-close pre-commitment (frozen)

If all four cells are null: model class on the current feature set and label pool is CLOSED
alongside the feature frontier, and the combined reopen burden is the LABEL POOL
(RESOLVED_THROUGH 2026), not another architecture. No third adjudication on these labels.

## Results

Filled 2026-08-19 from data/xfv_model_class_readjudication_eval.json, the artifact the lab
(tools/efv_model_class_gate.py, seed 20260819) wrote incrementally during the run. The run
completed in 11.0 min; the session that launched it died before this section was filled, so
the record quoted below is the lab-written artifact, verbatim, not a reconstructed console
transcript. Every number below is copied from that artifact.

### A0 reproduction (C-a): PASSED, both sides

Binding comparison = the in-process shipped chain (efv_model._run_eval on identical rows).
- hit: legs_equal_run_eval ridge/lgbm/ensemble all true; per_year_ridge_equal true;
  replica_pooled_rho_gap 0.0 (rowwise 0.3897278764977821 vs replica 0.3897278764977821);
  replica_max_abs_pred_gap 3.552713678800501e-15; lgbm_batch_max_abs_pred_gap 0.0.
- pit: legs_equal_run_eval all true; per_year_ridge_equal true; replica_pooled_rho_gap 0.0
  (0.24255761612303628 both paths); replica_max_abs_pred_gap 3.552713678800501e-15;
  lgbm_batch_max_abs_pred_gap 0.0.
- Disk-artifact disclosure: data/xfv_eval.json (hit) matches exactly (n 755, rho 0.3897,
  MAE 4.434). data/xfv_eval_pitcher.json (generated 2026-08-14) does NOT match: disk n 891 /
  rho 0.2428 / MAE 3.008 vs lab n 892 / 0.2426 / 3.006. The pit matrix gained one row since
  08-14 (the W2 identity merges). The frozen frame is the current basis and the binding A0
  leg (in-process shipped chain, same rows) is bit-exact, so A0 stands; the drift is
  disclosed here rather than hidden behind the pass flag.

### Controls: C-c PASSED, C-b PASSED

- C-c fold coverage: 11 folds scored per side (2014-2024), folds_missing_an_arm [] on both.
- C-b zero-information twin: hit twin delta -0.38972 vs floor +0.03564; pit -0.24996 vs
  +0.04208. Neither cleared. Harness clean.

### Floors (E_cond, B=2000, derived on this frame before any arm was read)

- hit_A1 MDE95 0.03564 (sd 0.021668), hit_A2 0.01474 (sd 0.008959),
  pit_A1 0.04208 (sd 0.025581), pit_A2 0.02231 (sd 0.013562).
- Frame: hit n_scored 755 (pool 845, 14 keys, lambda 0.70 pinned), pit n_scored 892
  (pool 983, 9 keys, lambda 0.57 pinned). player_key unique on both sides, so row
  resampling is player-clustered resampling.

### Cells (primary, E_cond, Holm over {hit,pit} x {A1,A2})

| cell   | delta rho | floor   | x_floor | E_cond | p (one-sided win) | Holm thr | reject | S3 pass | ship |
|--------|-----------|---------|---------|--------|-------------------|----------|--------|---------|------|
| hit_A1 | -0.03545  | 0.03564 | 0.995   | NULL   | 0.949064          | 0.05     | no     | yes     | no   |
| hit_A2 | -0.00419  | 0.01474 | 0.284   | NULL   | 0.679888          | 0.025    | no     | yes     | no   |
| pit_A1 | +0.00811  | 0.04208 | 0.193   | NULL   | 0.375566          | 0.016667 | no     | yes     | no   |
| pit_A2 | +0.01857  | 0.02231 | 0.833   | NULL   | 0.085401          | 0.0125   | no     | yes     | no   |

Holm survivors: none. S3 note: MAE actually IMPROVES under A2 on both sides (hit -0.1109,
pit -0.1412, both CIs below 0) and pit tail MAE improves (-0.3556, CI [-0.616, -0.117]),
but S3 is ship-blocking only, never ship-granting, and no cell cleared its rho floor.

### E_refit (secondary, B=200 as registered, 10.5 min)

All four cells NULL here too: hit_A1 sd 0.034944 / point -0.03545; hit_A2 0.016536 /
-0.00419; pit_A1 0.035205 / +0.00811; pit_A2 0.019900 / +0.01857. Reported beside the
registered E_cond primary, never substituted.

### Verdict (verbatim from the artifact)

"ALL FOUR CELLS ARE NULL UNDER THE REGISTERED PRIMARY. Per the frozen permanent-close
pre-commitment: the model class on the current feature set and label pool is CLOSED
alongside the feature frontier. The combined reopen burden is the LABEL POOL
(RESOLVED_THROUGH 2026), not another architecture. No third adjudication on these labels.
No cell that failed Holm or its E_cond floor may be quoted as a win."

The 2026-08-14 planning number (pitcher ensemble 0.2612 vs blend 0.2584) is hereby
adjudicated: on the registered frame the pit_A2 read is +0.01857 at 0.833x its floor,
p 0.085 vs Holm threshold 0.0125. It is NULL. It must not be cited as a pending win again.

Tests: prospect-tracker/test_model_class_readjudication.py pins artifact existence, A0
pass, controls, floor arithmetic, Holm re-derivation from stored p-values, ship-flag
conjunction, and verdict-cell agreement (7 checks, all green on this artifact).
