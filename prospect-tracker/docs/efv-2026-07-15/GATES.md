# eFV 2024-fold unlock program (2026-07-15, successor to docs/efv-2026-07-14/GATES.md)

Owner-approved next-session queue (stats<->projections program): unlock the
2024 debut fold, discharge the mandated governance re-runs, re-baseline, then
re-gate the pre-registered keep-alives at the new vintage. No loss ships.

## The vintage change (this session, one matrix rebuild)

1. `efv_dataset.DEBUT_YEARS` widened `range(2011, 2024)` -> `range(2011, 2025)`.
   241 dated-2024 debuts enter as censored weight-0.333 rows through the
   existing censoring machinery (hit +91 debuted rows -> 845; pit +119 -> 981).
   SCORED_YEARS stays (2020, 2021, 2022, 2023): the new rows enrich the
   training pools of the existing folds; no 2024 eval fold is added.
2. Label-integrity fix in the SAME rebuild (audit residue item a): career-
   terminal transactions (lifetime DEI ban / retirement, raw
   player_transactions payloads, last terminal event with no later activating
   move) now RESOLVE censored debuted rows at the observed sum with weight 1.0
   instead of extrapolating seasons the player cannot play, and unflag
   recent-bust retirees ("may still be developing" no longer applies).
   Boundary: any event through RESOLVED_THROUGH, or a pre-season (<= Apr 1)
   event in the first unresolved season. Resolved this run: hit
   tucupita_marcano (lifetime ban; censored -1.296 -> resolved -1.08),
   jake_alu, alex_kirilloff; pit riley_pint, stephen_ridings; 1 bust-pool
   retiree upweighted (joe_elbis). Saalfrank/Groome (1-year bans, later
   reinstated) correctly untouched.

## Governance re-runs (F-SIDE S5 + the bucket-head rerun marker) - DISCHARGED

Mandate: the FIRST run where the 2024 decision fold becomes trainable in the
DEBUTED frame trips a named re-run of E-ISO4-path, M3 and E-STUFF (S5), plus
BUCKET-AGE-HEAD per its own registered marker, BEFORE any baseline reset.
All four ran on the rebuilt matrices with their registered gates unchanged:

- **E-ISO4-path** (tools/efv_grade_recal4_lab.py): **FAIL**, both
  formulations, same binding cell as the registered close (condition 1: pit
  BENCH log-loss materially worse, +1.4% rel form a / +2.5% form b; form b
  also degrades both star cells). Conditions 2/3/4 pass. The bucket-
  calibration line close STANDS at the 2024-fold vintage.
- **M3** (tools/efv_cohort_lambda_hier_lab.py): **FAIL**, now 5 of 6 clauses
  (2026-07-07 run failed 3). Pit pooled goes negative (-0.0013); pit:ifa
  captures only +0.0068 (bar +0.01); hit:ifa still degrades (-0.0087); c6
  fold stability still fails. This SETTLES two queue keep-alives as clean
  NO-SHIPs: "pit:ifa shrink" and "M3 cohort-lambda c6". The cohort-lambda
  hierarchy line stays closed; a pit:ifa-ONLY shrink would need its own new
  pre-registered gate and is NOT re-opened by this run.
- **E-STUFF** (tools/efv_pitcher_stuff_lab.py): **FAIL** (inconclusive by the
  insufficient-n rule, as its ledger predicted): every train fold still has
  zero tracking coverage, all gate deltas exactly 0.0. Artifact future-
  coverage block: the first trainable fold arrives with 2025 debuts AND 2025
  in SCORED_YEARS (2024 strict-covered 48; 2025 strict-covered 64).
- **BUCKET-AGE-HEAD** (tools/bucket_age_head/gate_lab.py, copied into the
  repo from the registered session scratchpad so the mandated lab survives
  temp cleanup; identical pre-registered gates): **FAIL** on G4 exactly as
  registered (grade-monotone seam violations, worst +0.07621 P(bust) jump);
  G1/G2/G3 pass but the post-hoc ablation again attributes the gain to
  population recalibration (grade-band-only head 0.1786 dominates the age
  head 0.30655). Incumbent p_bucket_given_fv stands.

F-SIDE consequence: baselines may now be reset; the S3 reference floats to
the refreshed E-ISO4 artifact on the next eval regen (intended - that is the
re-baselining S5 guards).

## New baselines (python tools/efv_ml_lab.py --selftest, post-unlock matrices)

- hit: blend_rho 0.3765 / pure 0.3830 / wm 0.1652 / t45 0.0795,
  era 2019-2021 0.2932 / 2022-2023 0.4230
- pit: blend_rho 0.3028 / pure 0.3047 / wm 0.1488 / t45 0.2023,
  era 2019-2021 0.2034 / 2022-2023 0.3936

(2026-07-14 corrected-label baselines for reference: hit
0.3458/0.3556/0.1631/0.1138; pit 0.2926/0.2963/0.1375/0.1477.)

## Pre-registered keep-alive re-gates (registered BEFORE any arm ran)

All deltas judged against SAME-RUN BASE arms at the new vintage, never the
ledgered numbers. Pit levers additionally judged on the weakest cells:
pitchers FV45-50 and the 2019-2021 era. Marginal counts as fail. No loss
ships; every verdict is ledgered into the existing artifact + registry row.

### LR-FRINGE: hit_level_rank fringe re-gate (one attempt)

The xfv_feature_arms_2026_07 keep-alive, re-run under the M5 fringe-gate
template (docs/prelaunch-2026-07/GATES.md section M5), verbatim thresholds:
add level_rank to the hitter lean set (additive, efv_lab_runner protocol,
live lambda). SHIP iff ALL of:
1. t45 tier Spearman delta >= +0.015
2. pooled delta >= -0.003
3. within-tier wm delta >= -0.003
4. no per-era cell drops > 0.01
Primary target censored; resolved reported as sensitivity. ONE attempt; on
failure, ledger and the arm closes for good (no second fringe re-gate).
Tool: tools/efv_level_rank_fringe_lab.py (thresholds hard-coded in header).
Artifact: data/xfv_level_rank_fringe_eval.json.

### MC-PIT: pit model-class keep-alives (elasticnet + residual-target)

The xfv_model_class_sweep keep-alive pair, re-run through tools/efv_ml_lab.py
with the registered ship bar (docs/efv-2026-07-14/GATES.md): pooled rho >=
BASE + 0.0046 AND within_tier_wm >= BASE - 0.0023 AND t45 >= BASE - 0.0023,
same-run BASE_pit arm, lean features, target censored eval truth, live
lambda. Specs identical to the ledgered arms: elasticnet (ElasticNetCV,
random_state 7) and ridge-on-residual scored as consensus + correction.
Weakest-cells read (per_tier 45/50, era 2019-2021) reported alongside.

### E-LEAN1 re-open (the ledgered five)

The xfv_leanplus do_not_retry five, re-opened at the 2024-fold vintage per
the owner queue (NB the ledger asked for RESOLVED 2024 cohorts; the queue
re-opens at the censored-2024 vintage - recorded honestly here). Identical
registered 4-condition gate: pooled gain must EXCEED the identity-variant
noise floor RE-MEASURED at this vintage (identity = fv duplicated as an
extra ridge column, per side per target); within-tier wm no-degrade both
targets; t45 no-degrade both targets; no new per-year sign flips. Arms: hit
prod_trend / fv_trend / pos_prem / il_stints_pre / n_sources; pit prod_trend
/ fv_trend / il_stints_pre / n_sources (pit il_stints_pre expected to no-op
again: IL tracking is append-only since 2026-06). Additive arms via
tools/efv_lab_runner.py; verdicts appended to data/xfv_leanplus_eval.json.

## Keep-alive verdicts (runs executed after the registrations above)

- **LR-FRINGE: PASS -> SHIPPED.** t45 +0.0192 (bar +0.015), pooled +0.0003,
  wm -0.0003, era clean; resolved sensitivity agrees (t45 +0.0132, wm +0.005).
  level_rank enters _FEATURES_HIT (kept last), pinned by test_efv_model;
  ledger data/xfv_level_rank_fringe_eval.json, registry row
  xfv_level_rank_fringe (validated). The one pre-registered attempt is spent
  either way; it happened to clear.
- **MC-PIT: both FAIL again.** elasticnet pooled +0.0033, residual-target
  +0.0030 - under the +0.0046 bar at the new vintage; weakest cells (t50,
  era 2019-2021) flat. Keep-alive spent; ridge stands. Next new information
  = resolved 2024+ cohorts.
- **E-LEAN1 re-open: all nine arms FAIL** at the re-measured identity noise
  floors (hit 0.0011 / pit 0.0006). Closest: hit_il_stints_pre, positive on
  every metric both targets but pooled +0.0003/+0.0008 inside noise
  (marginal counts as fail). pit_il_stints_pre an exact no-op again. Line
  closed pending resolved 2024+ cohorts.
- **pit:ifa shrink + M3 c6:** consumed by the M3 governance FAIL above.

Net: one ship (hit level_rank), every other lever honestly ledgered as a
loss at the new vintage.

## Binding constraints (carried forward from 2026-07-14)

- No re-attempt of ledgered losses outside the keep-alives named above.
- Anything that ships gets: its own lab tool under tools/, a committed
  data/*_eval.json ledger, a model_registry row/verdict update, and a golden
  bump. Losses get the eval ledger committed anyway.
