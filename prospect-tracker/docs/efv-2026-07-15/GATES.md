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

## RELIEF-SHAPE: PAL prospect-watch relief risk as a pitcher feature
## (registered 2026-07-15, BEFORE any arm ran)

Owner ask (verbatim intent): use the PAL Prospect Watch shape signal to wire
a relief risk into eFV and adjust pitcher grades; only ship on a gain.

Mechanism: pal_conversion.prospect_role_fit composes arsenal depth (count of
20-80 pitch grades >= 55) + command into starter_shape (0-100); thin-arsenal /
poor-command arms profile as relievers, and relievers deliver less first-6yr
WAR. The pitcher matrix carries tool_fb/sl/cb/ch/cmd at the pre-debut anchor
(fb+cmd 89% debuted / 98% eval-fold coverage; tool_ct is NOT captured at the
anchor, so the composite is fb/sl/cb/ch + cmd, recorded as a PAL divergence).
Ground-truth sanity (no outcomes touched): designated-RP rows mean shape 32.3
vs pool 38.9; never-debuted bust pool 32.4.

NOT a re-attempt of a ledgered loss: the 2026-06-23 "SP/RP role split"
NULL was pos_prem, a POSITION-DESIGNATION feature (SIRP/MIRP/SP cover ~6% of
debuted rows; near-constant column). This lane is tool-grade shape at 89%
coverage - a different data source and mechanism. It is also NOT the
xfv_role_ceiling overlay (a live-only, designation-gated owner policy dial);
this is a trained feature through the standard forward-chained protocol.

Arms (additive via efv_lab_runner, live lambda, censored primary target,
resolved reported as sensitivity, deltas vs SAME-RUN BASE pit arms; the
feature computation lives in efv_model._vec so the lab tests the production
code path; ONE attempt each):

- RS-1 `starter_shape`: PAL-faithful composite, None-aware on raw grades
  (depth counts OBSERVED grades >= 55; cmd missing -> neutral 50 exactly as
  PAL; zero observed pitch grades -> impute observed-train-mean 38.9 so
  tool-missing rows stay neutral under standardization - the 2026-07-14
  imputation-audit class; NEVER computed from the imputed tool_* feature
  values, where tool_fb=58 would fake depth 1 + cmd 45 would fake shape 19).
- RS-2 `arsenal_depth`: the raw observed depth count 0-4 (zero observed
  grades -> train mean 1.6).
- RS-3 `relief_flag`: 1.0 if observed starter_shape < 40 (PAL's RP-lean
  threshold), 0.0 otherwise incl. shape-missing (bounded-indicator class).

Ship bar per arm (the registered pit additive-feature bar, docs/
efv-2026-07-14 GATES.md as re-used by MC-PIT, plus the weakest-cells clause
this doc already binds pit levers to). SHIP iff ALL of:
1. pooled Spearman delta >= +0.0046
2. within-tier wm delta >= -0.0023
3. t45 delta >= -0.0023
4. no per-era cell drop > 0.01 (2019-2021 is the named weakest era)
5. weakest tiers: per_tier 45 and 50 rho drop no more than 0.01
Marginal counts as fail. If more than one arm passes, ship ONLY the highest
pooled delta (the others ledger as subsumed, not closed).

Fringe-signature record rule (level_rank precedent): an arm that FAILS the
pooled bar but shows t45 >= +0.015 with pooled AND wm >= -0.0011 is ledgered
FAIL with a keep-alive for a FUTURE pre-registered fringe re-gate at a new
vintage; no same-session re-gate (that would be gate shopping).

Honest caveat carried on any verdict: the debuted-only eval pool is
survivorship-censored - it cannot see never-debut RP-shape washouts, so this
gate can UNDER-credit the feature but not over-credit it (same caveat the
age feature shipped under).

Tool: tools/efv_relief_shape_lab.py. Artifact: data/xfv_relief_shape_eval.json.

### RELIEF-SHAPE verdict (run executed after the registration above): NO SHIP

All three arms FAIL the registered bar; no arm earns the fringe keep-alive
(every arm misses BOTH -0.0011 floors). Same-run BASE pit censored:
0.3020/0.1466/0.2056 (pooled/wm/t45), n=438.

- RS-1 starter_shape: pooled -0.0078, wm -0.0154, t45 -0.0456 (fails 1/2/3/5;
  tier-50 +0.0422 is the lone up cell). Resolved sensitivity agrees
  (-0.0062/-0.0126/-0.0175).
- RS-2 arsenal_depth: pooled -0.0038, wm -0.0143, t45 +0.0192 BUT tier-50
  -0.0374 (fails 1/2/5). Resolved t45 +0.0664 with pooled still negative.
- RS-3 relief_flag: pooled -0.0021, wm -0.0087, t45 +0.0314 BUT tier-50
  -0.0103 (fails 1/2/5, tier-50 marginal-counts-as-fail). Resolved t45
  +0.0764 with pooled still negative.

Reading: the shape signal is REAL univariately (spearman +0.147 vs the
censored target; designated-RP mean shape 32.3 vs pool 38.9) but the ridge
already prices it through tool_fb + peak_k_rel/bb_rel - adding any shape
composite only REDISTRIBUTES rank skill between the 45 and 50 tiers (RS-2/3
buy t45 by selling tier-50 and pooled; RS-1 the reverse) and every arm
degrades pooled + within-tier. Consistent with the ledgered "cmd does not
help pit OOS" finding and the structural lesson that the lean set is at its
trainable-data ceiling. The t45-vs-t50 tension replicates the joint-display-
map fairness-vs-pooled-accuracy tension at this data resolution.

Verdict verified by a 3-lens adversarial panel (lab-bug hunt reproduced
every number to 4dp + confirmed no silent-zero/sign error; protocol audit
recomputed all gate cells + confirmed thresholds match this registration;
production-inertness lens proved shipped eFV output bit-identical). Two
latent lab defects the audit flagged (fringe rule keyed on overall-fail
instead of pooled-fail; 4dp rounding before gate comparison) were fixed and
the lab re-run: verdict identical.

One attempt per arm is SPENT; the lane closes. Next new information =
resolved 2024+ cohorts (~2027 season end), same as every closed pit lane.
The _vec starter_shape/arsenal_depth/relief_flag keys stay emitted-but-inert
(the age_missing precedent) so the lab remains reproducible; _FEATURES_PIT
is unchanged. If the owner wants a relief-risk DISPLAY on the PAL prospect
watch or prospect cards, that is a UI ask, not a model change - the shipped
xfv_role_ceiling dial already covers designated-RP arms on the live board.
