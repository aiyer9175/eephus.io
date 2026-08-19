# V3: model-class re-adjudication on the 11-fold basis (registered 2026-08-19)

STATUS: REGISTERED, clauses frozen BEFORE the lab exists. Results section is PENDING and is
filled only with verbatim lab output.

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

PENDING.
