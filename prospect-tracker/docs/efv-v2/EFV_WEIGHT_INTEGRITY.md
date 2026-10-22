# eFV driver weight integrity: are the served weights real, and is a simpler head as good (EFV_WEIGHT_INTEGRITY)

Registration status: REGISTERED

Written 2026-10-22 under owner decision EW3-49 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`):
"make eFV's driver and sub-driver weights as accurate as possible to MLB outcomes WITHOUT redoing
what failed", all four arms answered. This document is committed ALONE, before the module
`efv_weight_integrity.py` exists and before any number of this read is computed. Sections 1 to 10
are written before the read; the run appends section 11 (the numbers) and section 12 (the
verdict). No em-dashes.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019, vm_dev
debut cohorts 2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts
2025 and later) is built, fitted or scored; nothing is grouped, counted, averaged or stratified by
consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`); `backtest.run_backtest` is never called; no
projections retrain; the fWAR label epoch's runbook is untouched. The served grade does not move
in this task: anything that passes is built dark behind a flag that defaults to False.

## 0. What is NOT reopened (owner, EW3-49)

New drivers (the feature frontier closed at 39 arms; pitch rates 0 of 232), new model classes
(X3 pooled failed), side, role or position calibrations (failed), labels (the headline eWAR is
served), older vintages (X5 done), the eTools reweight (failed) and pitcher sign bounds one key at
a time (EFV_PIT_SIGN_STABILITY: nothing passed). Every arm below re-weights the keys the served
heads already carry, on the rows the served heads were already fitted on.

## 1. The subject: the served heads, as they stand

The served model is eFV v5 COMBINED re-fitted, variant RT (`docs/efv-v2/EFV_V5_REFIT.md`, owner flip
EFV-REFIT-1; `efv5_refit.EFV_V5_REFIT_ON` True, `data/efv5_refit_weights.json`):

    order_idx = u_c + w_skill * e_skill + w_time * e_time        inside (side, list year)
    e_skill   = sum_k beta_k * z_k / b_uc                         (the skill head over its consensus slope)

The skill head is a weighted ridge of u_y (the within-year percentile of the training label) on
[1, u_c, z(keys)] over the has-block training rows, the V2 keys penalized at V2's alpha, the
candidate columns at one lambda chosen by nested forward-chained CV on the grid
(1, 3, 10, 30, 100, 300, 1000, infinity), candidate slopes bounded by the atlas sign.

- Pitchers: w_skill 1.0 (the DS-08 ratio 1.053, clipped at W_MAX 1), w_time 0; the skill head
  carries 21 candidate keys at lambda 1000 (the largest finite value of the grid) and no V2 key.
- Hitters: w_skill 0.2965, w_time 0. The nested CV chose lambda infinity, so the hitter skill head
  is V2's own: ONE key, the hit tool grade (`tool_hit`, alpha 100). The nine hitter keys the task
  text counts are the hitter TIMING head (age at Single-A, five IL keys, two non-roster keys),
  which carries weight 0 and moves no order. They are read in arm A as descriptive only.

The development folds of the re-fit (cached by its run, the EFV_FIX_B_REFIT cache: `build1.pkl`,
`packs_RT.pkl`, `phase0.pkl`) are the frames, rows, fold models and test terms this read starts
from. Parity first: (a) the module's own ridge solver reproduces the stored production skill head
of each side from the cached production rows (prod plus twins, the RT rank transform) to 1e-9 on
every slope; (b) the cached RT fold models reproduce the cached e_skill on every test row; (c) the
served comparator S of section 3 is recomputed from the cache. The run refuses on any miss.

## 2. Frames, label, statistic, intervals

- Frames: lv_dev (2,862 scored rows) and vm_dev (830), the scored rows of the re-fit's own
  development read, with the label the re-fit read (frozen fWAR, `fwar@2026-10-02-0341299c20ec`;
  lv_dev W3, vm_dev career WAR to date). Training rows keep their training label (lv frame W3; vm
  frame the six-season label with its censored projection and exposure weight).
- PRIMARY statistic: within (frame, side, list year) Spearman of the order with the label, groups
  of 20 or more rows, size weighted, per side; pooled over the two frames by row count:
  (n_lv x stat_lv + n_vm x stat_vm) / (n_lv + n_vm), the re-fit's rule-1 form. The rule reads each
  side on its own (an edit to one side's head moves only that side).
- SECONDARY (the re-fit's own): pooled Spearman after the identical output map and contributor
  AUC, per frame and side, reported; and for arm D the six-season WAR secondary (section 7).
- INTERVALS: paired bootstrap, B 4000, seed 20261022, two clusterings read separately: PLAYER
  (all a player's rows together, over both frames) and CLUB (all rows of one developing club
  together). A row's club is the organization of the player's minor league line in the row's
  read season with the most games (`efv_vintage_frame.load_universe` career lines), else the
  nearest earlier season's, else the record's signing organization (`dev_credit.signing_org`),
  else the record's organization; a row with none is its own cluster. The club is read from lines
  of the read season or earlier, never from an outcome. The one-sided 95 percent lower bound of
  a difference is the 5th percentile of its bootstrap draws; a CI90 and a CI95 are the 5/95 and
  2.5/97.5 percentiles.

## 3. The comparators (read in every arm)

- S, the SERVED heads: the cached RT fold models' e_skill on each fold's test rows; w_time 0 (the
  served arrival weight). The weight is the re-fit's rule applied to every head alike: per side,
  DS-08's OLS u_y ~ 1 + u_c + e_skill on the pooled scored rows of every fold of both frames,
  w_skill = clip(c_skill / c_uc, 0, 1), CROSS-FITTED (a fold's orders use the weight of the pool
  without that fold; the guard `efv5_refit.CROSSFIT_MIN_NONZERO`: a term nonzero on fewer than 100
  pool rows is held at 0). Sensitivity: S and every arm at the served constants (hitters 0.2965,
  pitchers 1.0), reported, deciding nothing.
- K, CONSENSUS-ONLY: w_skill 0, the order is u_c.
- P, the PLANTED-signal check through the same pipeline (per side): every training row's label
  and every scored row's outcome is replaced by truth + noise, where truth = the row's consensus
  percentile within its (frame, year) plus the served production head's own e_skill on the row
  (its keys, slopes, means and SDs; the RT transform), and the noise is Gaussian with the SD of
  the production fit's residual (u_y minus its fitted value), seed 20261022. S and every arm's
  configuration are then refitted in every fold on the planted rows (penalties re-selected) and
  read. The instrument RECOVERS on a side when S minus K under the plant has a one-sided 95
  percent lower bound above 0 (player clusters): the pipeline can see a signal of the size the
  served head claims. Each arm's own planted reading (arm minus S, arm minus K) is reported. If
  the instrument does not recover on a side, no adoption on that side is interpretable and none
  is made.

## 4. Arm A: how sure are the served weights (descriptive; adopts nothing)

A1. Slope intervals. Per side, the production skill head refitted on cluster bootstrap draws of
its own training rows (multiplicity weights on the WLS, every row of a drawn cluster together;
twins with their player), penalties held at the production values (lambda 1000 for pitchers;
alpha 100 on the hit tool for hitters), bounds as served, standardization at the production means
and SDs. Per key: the head slope per SD in order-index units, beta_k / b_uc, and the order weight
w_skill x beta_k / b_uc; CI90 and CI95 under player and under club clusters; the share of draws
at the production sign; the share at exactly 0 (a bound). A key is FLAGGED when its CI95 under
either clustering includes 0.

A2. The head weights. w_skill and w_time by DS-08's form as served (u_y ~ 1 + u_c + e_skill +
e_time over the RT packs' scored rows, both frames pooled per side): the ratio and the clipped
weight, CI90 and CI95 under player and club clusters, B 4000.

A3. Leave-one-cohort-out. Per side, the production fit refitted 14 times, each time without one
decision-year cohort (its matrix rows and its twins), by the re-fit's full procedure (V2 admission,
alpha and lambda re-selected by nested CV, dark list, RT transform). Per key: the 14 slopes, the
signs, whether the key FLIPS (nonzero slopes of both signs) or drops to 0, the lambda chosen.

A4. Effective degrees of freedom of each production head: the trace of the ridge hat matrix
Z_f (Z_f' W Z_f + P_f)^-1 Z_f' W over the free coefficients (intercept, consensus and every slope
not held at a bound), minus 2 for the intercept and the consensus slope.

A5. Planted recovery of A1: the production rows' u_y replaced by the head's fitted value plus
Gaussian noise at the fit's residual SD (seed 20261022), and by the fit's consensus-only value plus
the same noise; A1 rerun on both with player clusters, B 4000. Reported: the share of keys whose
CI95 covers its planted slope, the share of nonzero planted keys whose CI95 excludes 0, and under
the zero plant the share of keys whose CI95 excludes 0 (about 5 percent expected).

Reading per key: REAL when its CI95 excludes 0 under both clusterings and it never flips in A3;
NOISE when its CI90 includes 0 under either clustering; WEAK otherwise.

## 5. Arm B: simpler heads (Dawes' improper linear model test)

Each candidate head replaces the skill head of S in every development fold, fitted on that fold's
own skill training rows exactly as RT built them (forward chaining; twins in the vm_dev skill rows;
the RT rank transform; the fold's V2-admitted keys and RT's candidate columns minus the dark list),
and in the production fit. The timing head and w_time stay at the served 0.

Sign stability inside a fit (no outcome outside the fit's rows): the joint head refitted once per
decision year of the fit's training rows with that year left out, at the fit's own penalties
(the fold model's alpha and lambda). A key is SIGN-STABLE in that fit when every one of those
slopes is nonzero with one sign; its sign is that sign; its stability score is |mean slope| / SD of
the slopes.

- B1 UNIT weights: U = sum over the sign-stable keys of sign_k x z_k (z at the fit's own
  standardization); one fitted scale c >= 0 by the WLS u_y ~ 1 + u_c + c U on the fit's has-block
  rows; e_skill = c U / b_uc. No stable key: e_skill 0.
- B2 RIDGE toward zero: one common penalty on every slope (V2 keys and candidates; candidate
  bounds as served) chosen by the same nested forward-chained CV on the extended grid (1, 3, 10, 30,
  100, 300, 1000, 3000, 10000, 30000, 100000, infinity). The served pitcher lambda sits at the
  largest finite value of the served grid; this arm lets the CV shrink further.
- B3 SPARSE top-k: the sign-stable keys ranked by stability score (ties by name); the head on the
  top k keys, each bounded at its stable sign, penalty 1; k from (1, 2, 3, 5, 8, all stable) by
  nested forward-chained CV over the fit's training years, the ranking re-derived on each inner
  training set from its own left-out-year refits.

Simplicity order: B1 (one fitted scale), then B3 (k slopes), then B2 (every slope, shrunk); the
effective degrees of freedom of each production head (A4's formula) are reported beside it.

Variance reduction: per side and head, the production head refitted on B 4000 player-cluster
bootstrap draws of the production rows at its fixed structure (B1: the stable keys and signs, the
scale refitted; B2: its penalty; B3: its k keys; S: its penalties), and scored on the live board
rows of section 6; reported: the mean over board rows of the bootstrap variance of
w_skill x e_skill in percentile points squared, the head against S, and the ratio.

## 6. Arm C: live board against training, per driver

The live board: the served board's rows as read on 2026-10-16 (the date of `data/xfv.json`), built
by the served path (`efv_v2_serve.live_rows`, the live candidate columns with support_clip, the RT
transform); the run first checks that the served models score them to the served grade of every
row (refuses otherwise). Training: the production skill training rows (prod plus twins, has-block
rows). Compared on the has-block rows of each.

Per key of the served skill head of each side, and descriptively per candidate column of the side:
- SMD: (live mean minus training mean) over the training SD, on the head's design values (missing
  at the head's training mean, as the head reads them), and on the observed values only;
- KS: the two-sample Kolmogorov-Smirnov statistic and p value on the observed values;
- the live-against-training classifier: an L2 logistic (penalty 1 on standardized features,
  intercept free) on the head's design, 5-fold stratified cross-validated AUC (seed 20261022) and
  in-sample AUC; for each key, the cross-validated AUC with that key removed and the DROP.

A key CARRIES the shift when its drop is 0.01 or more, or its design SMD is 0.25 or more in
absolute value.

C, the re-standardized head (only when some key carries the shift): each carrying key re-read
within level x season. For a set of rows (a fit's training rows, a fold's test rows, the live
board), group g = (level band, read season): the level band is the row's level rank (none for a
row with no level), the read season is the minor league season the row reads (vm matrix rows and
their test rows: the matrix row's `milb_season`, else decision year minus 1; twins: their read
season; list-vintage rows: the vintage minus 1; the live board: its read season). Each non-missing
value v (for the group and tool cell families g5 and t5, nonzero values only; their zero means "no
line" and stays 0) becomes m_ref(L) + (v - m_g) x s_ref(L) / s_g, with m_g and s_g the moments of the
group's values in that set and m_ref(L), s_ref(L) those of the level band L over the fit's training
rows; a group under 20 values falls back to its read season over all levels, and under 20 again
the value is left as it is. On the live board the values are support-clipped as served before the
transform and clipped into the transformed training range after it. The RT procedure then refits
both heads on the transformed rows in every fold (penalties re-selected) and in production.
Reported with it: the classifier's cross-validated AUC on the transformed training and live rows
against the untransformed AUC.

## 7. Arm D: the objective

How the served heads are fitted (read from the code, before any number): a squared-error ridge
on the within-year percentile of the training label (a rank target with a squared loss), weighted
by the row's exposure weight; arrival a penalized logistic of REACHED. D refits the skill head with
a WITHIN-GROUP PAIRWISE LOGISTIC RANK LOSS on the same keys, rows and folds:

    loss = sum over decision-year groups, over pairs (i, j) with label_i > label_j, of
           w_i w_j log(1 + exp(-(s_i - s_j))) / (sum of pair weights)  +  0.5 lambda sum_k beta_k^2
    s = b_uc u_c + sum_k beta_k z_k                                  (no intercept: it cancels)

over the fit's has-block rows (twins in their decision year), tied labels forming no pair, b_uc
free, candidate slopes bounded as served, lambda by nested forward-chained CV on the held-out mean
pairwise log loss of the inner year over (0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3,
infinity). e_skill = sum beta_k z_k / b_uc (the head is unusable when b_uc <= 0).

The six-season WAR secondary: within (frame, side, year) Spearman against the six-season label
(L6: lv_dev rows `efv_labels` L6, its censored projection where not resolved; vm_dev rows the
matrix row's own six-season target), rows where it is defined; D minus S, CI95 under player
clusters.

## 8. The adoption rule and the multiplicity

For a candidate X (B1, B2, B3, C, D) on a side, with d = pooled within(X) minus pooled within(S):

1. NON-INFERIOR: the one-sided 95 percent lower bound of d is above -0.005 under player AND club
   clusters; its p value is the larger of the two bootstrap shares of draws at or below -0.005
   ((count + 1) / (B + 1)).
2. HOLM across every adoption test read (every X on every side whose configuration exists), at
   family alpha 0.05: X is non-inferior only if its p value clears Holm's step-down threshold.
3. NULL COMPARATOR: X does not trail consensus-only: pooled within(X) at or above pooled within(K)
   (point estimates).
4. PLANTED: the instrument recovers on the side (section 3).
5. Arm specific: B, the simplest passing head in the order B1, B3, B2 is the one adopted; C, the
   classifier's cross-validated AUC on the transformed rows is below the untransformed AUC; D, the
   six-season secondary's d is at or above -0.005 and its CI95 upper bound is at or above 0.

A side may have at most one adopted head; when more than one arm adopts on a side, the order is
B, then C, then D (simpler or input-only changes first), and the others are reported as passing
alternatives.

## 9. Outputs, the flag and the owner

- `data/efv_weight_integrity.json`: every receipt, table, read and verdict above. Role
  development; adjudicates nothing; no row is written to `data/efv_progress.json` unless an arm
  is adopted (then two development rows, hollow on the Source Comparison page).
- `docs/efv-v2/EFV_WEIGHT_INTEGRITY_RESULTS.md`: plain language (which weights are real, which
  are noise, what shift was found).
- A note on the efv rows of `data/model_registry.json`.
- If an arm is adopted: `efv_weight_integrity.EFV_WEIGHT_INTEGRITY_ON = False`, and
  `data/efv_weight_integrity_weights.json` holds the adopted production fit per side; with the flag
  True the serve path takes that side's model from the file, and the board fingerprint term gains
  the file's hash (prepared in code, not applied while the flag is False). With the flag False
  every served artifact is byte identical. The board effect (live board against `data/xfv.json`)
  and an OWNER QUESTION per passing arm close the results. Nothing is flipped here.

## 10. Defaults applied (the owner may choose differently)

- D-1 every head is read at DS-08's cross-fitted weight with w_time 0 (the re-fit's own rule);
  the served constants are a sensitivity.
- D-2 the two clusterings are read separately and both must clear the bound (not a two-way
  bootstrap).
- D-3 sign stability is read inside each fit at that fit's own penalties, so a key the served CV
  shrank to 0 in a fold is not stable there.
- D-4 the planted truth is the served production head's own e_skill (a dense signal of the size
  the served head claims).
- D-5 the C transform keeps level information (each level band keeps its pooled training moments)
  and removes season drift; structural zeros of the group and tool cell families stay 0.
- D-6 the D loss is normalized by the pair weight total, so its penalty grid is its own.
- D-7 consensus-only is the null comparator; the permuted-change null of EFV_PIT_SIGN_STABILITY is
  not repeated.

## 11. The read (appended by the run, 2026-10-22; development frames)

Run: `python -u efv_weight_integrity.py --run --cache <EFV_FIX_B_REFIT cache> --work <scratch>` after
the registration commit 88b91432 and the module commit ba64ee57 (artifact
`data/efv_weight_integrity.json`; label `fwar@2026-10-02-0341299c20ec`, the cache's, whose values
the later vintage id `fwar@2026-10-02-57bf90f7143e` leaves unchanged; B 4000, seed 20261022). No
reserved row was built; nothing was cut by consensus-FV level; `backtest.run_backtest` was not
called.

Disclosed before the read: a smoke run on three folds checked the solver parity and the timing
(it printed the folds' chosen penalties, no statistic), and a dry run at B 20 on four folds ran
every code path (its numbers were discarded unread). Disclosed after it: the first write did not
store the served-minus-consensus difference (S minus K) with its interval. The artifact was
re-assembled from the same cached parts with that one block added; against the first write, only
`generated_at`, `elapsed_s` and the module hash changed (a second re-assembly without the block
reproduced the first write exactly).

### 11.1 Receipts

- The module's solver reproduces both stored production skill heads exactly (largest slope
  difference 0.0; hitters 1 key, pitchers 21); the cached fold models reproduce the cached e_skill
  on every test row (0.0); the served skill procedure refitted on each of the 20 folds reproduces
  every fold head (0.0).
- The live board of 2026-10-16 (1,055 hitters, 941 pitchers) is scored by the served models to
  the served grade of every row (largest move 0.0).
- Clubs: every one of the 3,692 scored rows and 5,186 production rows has a club (30 to 33
  clusters per side; none is its own cluster). Players: 986 hitter and 1,001 pitcher clusters.
- The planted truth covers every training and scored row from its table (5,582 hitter and 5,566
  pitcher identities, none outside it); noise SD 0.286 (hitters) and 0.294 (pitchers).

### 11.2 Arm A: how sure the served weights are

Slope per SD in order-index units (0.01 is one percentile point of consensus rank); the order
weight is that times w_skill. CI95 under player and club clusters; LOCO is the 14 leave-one-cohort-
out production refits (+ / - / 0 counts).

Hitters (w_skill 0.2965; one key, alpha 100; effective degrees of freedom 0.93):

| key | per SD | order weight | CI95 player | CI95 club | LOCO | reading |
|---|---|---|---|---|---|---|
| tool_hit | +0.171 | +0.051 | +0.092 to +0.289 | +0.092 to +0.274 | 14 / 0 / 0 | real |

Pitchers (w_skill 1.0; 21 keys at lambda 1000, chosen again in 13 of the 14 LOCO refits;
effective degrees of freedom 9.37 over 19 free slopes):

| key | per SD | CI95 player | CI95 club | at bound 0 | LOCO | reading |
|---|---|---|---|---|---|---|
| w4p_pop_pit (population translation, rank) | +0.128 | +0.075 to +0.201 | +0.084 to +0.184 | 0 | 14 / 0 / 0 | real |
| w2p_csw_p (called plus swinging strikes) | +0.068 | +0.021 to +0.121 | +0.018 to +0.128 | 0 | 14 / 0 / 0 | real |
| w2b_pu_p (popups per ball in play) | -0.067 | -0.126 to -0.017 | -0.132 to -0.007 | 0 | 0 / 14 / 0 | real |
| w2p_k_resid_p (strikeouts beyond whiffs) | +0.055 | +0.013 to +0.108 | +0.023 to +0.088 | 0 | 14 / 0 / 0 | real |
| w2s_cmd_pit (command grade) | +0.055 | +0.014 to +0.110 | +0.020 to +0.102 | 0 | 14 / 0 / 0 | real |
| w2i_days_skill_pit (IL days) | -0.041 | -0.088 to +0.002 | -0.087 to -0.002 | 0 | 0 / 14 / 0 | weak |
| g5_pit_A_all_SP_k_pct | +0.030 | 0 to +0.058 | 0 to +0.060 | 0.05 | 14 / 0 / 0 | noise |
| w2i_stints_skill_pit (IL stints) | +0.028 | -0.011 to +0.069 | -0.011 to +0.068 | 0 | 14 / 0 / 0 | noise |
| w2p_cstr_p (called strikes) | +0.021 | -0.022 to +0.067 | -0.008 to +0.053 | 0 | 13 / 1 / 0 | noise |
| w2s_brk_pit (breaking-ball grade) | +0.020 | -0.023 to +0.069 | -0.023 to +0.062 | 0 | 14 / 0 / 0 | noise |
| w2i_sixty_skill_pit (60-day IL) | -0.019 | -0.071 to +0.027 | -0.068 to +0.032 | 0 | 0 / 14 / 0 | noise |
| w2i_recur_skill_pit | +0.018 | -0.024 to +0.059 | -0.016 to +0.062 | 0 | 14 / 0 / 0 | noise |
| t5_pit_AAA_all_all_fb_fut (Triple-A fastball) | +0.017 | -0.017 to +0.053 | -0.018 to +0.060 | 0 | 14 / 0 / 0 | noise |
| g5_pit_A_all_SP_k_minus_bb | +0.012 | 0 to +0.043 | 0 to +0.044 | 0.29 | 12 / 0 / 2 | noise |
| g5_pit_A_all_all_k_pct | +0.009 | 0 to +0.038 | 0 to +0.037 | 0.37 | 12 / 0 / 2 | noise |
| w2p_fstrike_p (first-pitch strikes) | -0.008 | -0.055 to +0.040 | -0.056 to +0.039 | 0 | 1 / 13 / 0 | noise |
| g5_pit_A_all_SP_bf_per_g | +0.007 | -0.026 to +0.042 | -0.033 to +0.043 | 0 | 12 / 2 / 0 | noise |
| w2i_open_skill_pit (on the IL at the read) | +0.005 | -0.037 to +0.044 | -0.032 to +0.047 | 0 | 12 / 2 / 0 | noise |
| g5_pit_A_young_all_k_pct | +0.001 | 0 to +0.035 | 0 to +0.030 | 0.50 | 10 / 0 / 4 | noise |
| g5_pit_A_all_all_k_minus_bb | 0 | 0 to +0.007 | 0 to +0.004 | 0.92 | 0 / 0 / 14 | noise |
| g5_pit_A_young_all_k_minus_bb | 0 | 0 to +0.018 | 0 to +0.024 | 0.80 | 0 / 0 / 14 | noise |

Head weights (DS-08 as served): hitters w_skill ratio 0.297 (CI95 0.080 to 0.590 player, 0.078 to
0.586 club), w_time ratio -0.242 (-0.550 to +0.042; -0.495 to +0.019), clipped to 0; pitchers
w_skill ratio 1.053 (0.528 to 1.870; 0.499 to 1.743), clipped to 1.0, so the served weight's CI95 is
0.53 to 1.0; w_time ratio -0.496 (-0.845 to -0.206; -0.780 to -0.174), clipped to 0.

Planted recovery (A5): hitters, the planted hit tool slope is covered and resolved. Pitchers, the
CI95 covers 76 percent of the planted slopes (the ridge shrinks them) and excludes 0 for 32 percent
of the nonzero planted slopes; under the zero plant 2 of 21 intervals exclude 0 (9.5 percent). A
head whose every slope is real at the served size would show about 6 resolved keys; the read shows
5 real and 1 weak. The 15 noise keys are not shown to be zero; they are below what 1,737 rows can
resolve one at a time.

The hitter timing head (nine keys) carries weight 0 and moves no order; its slopes are in the
artifact as read.

### 11.3 Arm C: the live board against training

| side | CV AUC (in-sample) | carrying keys (SMD on the design; KS; drop in CV AUC) | CV AUC after re-standardization |
|---|---|---|---|
| hitters | 0.621 (0.623) | hit tool -0.46 SD; KS 0.21; drop 0.121 | 0.509 |
| pitchers | 0.718 (0.736) | 60-day IL +1.23 SD (KS 0.27, drop 0.070); command grade -0.39 (0.18, 0.031); strikeout residual -0.10 (0.04, 0.011); IL stints +0.31 (0.09, drop under 0.01); IL open +0.26 (0.07, under 0.01) | 0.620 |

Every other served pitcher key moves under 0.25 SD and its drop is under 0.01; the Single-A group
columns show no location shift (their spread drift is EFV_PIT_DRIFT_REBASE's). Descriptively, the
hitter power-present grade (not in the served head) sits 0.69 SD lower on the live board. On the
served head's own inputs the live board is far easier to tell from training for pitchers than
for hitters, and far less separable than X3's feature set (0.94 to 0.997), whose shift ran mostly
through college draftees and consensus grade, inputs no served head reads.

### 11.4 The development read (pooled within Spearman, player clusters)

| side | consensus K | served S | B1 unit | B2 ridge | B3 top-k | C re-standardized | D rank loss |
|---|---|---|---|---|---|---|---|
| hitters (n 1,871) | 0.2384 | 0.2370 | 0.2316 | 0.2376 | 0.2353 | 0.2371 | 0.2382 |
| pitchers (n 1,821) | 0.2091 | 0.2186 | 0.2192 | 0.2188 | 0.2055 | 0.2138 | 0.2171 |

S minus K: hitters -0.0014 (CI95 -0.021 to +0.017 player, -0.018 to +0.017 club); pitchers +0.0095
(-0.013 to +0.032; -0.018 to +0.034).

Each arm minus S (CI95 player; one-sided 95 percent lower bound player / club; the larger
non-inferiority p value; Holm):

| test | minus S | CI95 | lower bounds | p | Holm threshold | Holm | not below K |
|---|---|---|---|---|---|---|---|
| hit C | +0.0002 | -0.002 to +0.002 | -0.0013 / -0.0013 | 0.0003 | 0.0050 | rejects | no (-0.0012) |
| hit B2 | +0.0006 | -0.006 to +0.007 | -0.0046 / -0.0037 | 0.038 | 0.0056 | no | no (-0.0008) |
| pit B2 | +0.0002 | -0.006 to +0.006 | -0.0048 / -0.0037 | 0.040 | 0.0063 | no | yes |
| hit D | +0.0013 | -0.008 to +0.011 | -0.0063 / -0.0065 | 0.088 | 0.0071 | no | no (-0.0001) |
| pit B1 | +0.0007 | -0.011 to +0.012 | -0.0091 / -0.0083 | 0.173 | 0.0083 | no | yes |
| pit D | -0.0015 | -0.012 to +0.009 | -0.0099 / -0.0092 | 0.247 | 0.0100 | no | yes |
| hit B3 | -0.0017 | -0.013 to +0.010 | -0.0114 / -0.0105 | 0.302 | 0.0125 | no | no |
| pit C | -0.0048 | -0.011 to +0.001 | -0.0100 / -0.0106 | 0.508 | 0.0167 | no | yes |
| hit B1 | -0.0054 | -0.013 to +0.002 | -0.0118 / -0.0115 | 0.566 | 0.0250 | no | no |
| pit B3 | -0.0131 | -0.032 to +0.005 | -0.0287 / -0.0295 | 0.796 | 0.0500 | no | no |

The fits: B2's nested CV chose a penalty above the served grid's 1000 in 2 of 20 folds (3000) and
the production pitcher B2 head is the served head (lambda 1000, 0 board movers). B3 chose 1 or 2
pitcher keys in every fold (the command grade and the population translation in production). D's
nested CV chose infinity (no driver) in 5 hitter and 6 pitcher folds and in the hitter production
fit. B1 kept 8 to 13 sign-stable pitcher keys per fold, 1 in vm_dev 2017 (13 in production, each at 0.072 per SD).

The planted check recovers on both sides: S minus K under the plant +0.049 (lower bound +0.040,
hitters) and +0.108 (+0.093, pitchers). Under the plant (a dense truth, the served head's own),
B1 reads -0.031 and -0.021 against S, B3 -0.002 and -0.034, D -0.008 and -0.004, C -0.001 and
-0.002, B2 -0.008 and 0.000: the instrument sees the loss a simpler head takes when the truth is
the served head's shape, and on the real outcomes B1 takes no such loss on pitchers (+0.0007).

Secondaries. The six-season WAR label (L6; 1,794 hitter and 1,763 pitcher rows): S 0.2506 and
0.2459, K 0.2420 and 0.2464, D 0.2470 and 0.2469; D minus S -0.0037 (CI95 -0.013 to +0.007) and
+0.0010 (-0.009 to +0.012), so D does not lose on it; S minus K +0.0086 (-0.012 to +0.028) and
-0.0005 (-0.025 to +0.023). Pooled after the map and contributor AUC: every arm minus S spans zero on
both frames except hitter B3 on vm_dev pooled (+0.015, CI95 +0.001 to +0.028). At the served constant
weights (sensitivity) no arm reads more than +0.0002 above S; pitcher C reads -0.0071 (CI95 -0.0135 to
-0.0013).

### 11.5 Simplicity and variance (production heads on the live board)

| head | hitters edf / w_skill / board variance (pp^2, ratio to S) | pitchers edf / w_skill / board variance (ratio) |
|---|---|---|
| S | 0.93 / 0.297 / 2.45 (1.00) | 9.37 / 1.0 / 137.96 (1.00) |
| B1 | 1.00 / 0.283 / 2.89 (1.18) | 1.00 / 0.734 / 28.03 (0.20) |
| B2 | 6.85 / 0.284 / 4.25 (1.73) | 9.37 / 1.0 / 137.96 (1.00) |
| B3 | 1.00 / 0.243 / 2.13 (0.87) | 2.00 / 0.963 / 158.78 (1.15) |
| C | 0.93 / 0.298 / 2.20 (0.90) | 9.44 / 0.804 / 57.11 (0.41) |
| D | 0 / 0.209 / 0 (consensus) | 8.92 / 0.610 / 77.11 (0.56) |

Board variance is the mean over the live rows of the bootstrap variance of the head's order
contribution, in percentile points squared (the served pitcher head: median 91.8, so a typical
pitcher's driver contribution carries a sampling SD near 10 percentile points; outliers on the
60-day IL count carry more). The unit-weight pitcher head would cut that to a fifth.

## 12. The verdict (section 8)

Ten adoption tests were read (B1, B2, B3, C, D on each side). Holm at family alpha 0.05 clears one:
hitter C (the hit tool re-standardized within level x season), non-inferior to S (p 0.0003). It
fails the null comparator: like S itself, it trails consensus alone (C minus K -0.0012). No other
test clears Holm. The planted check recovers on both sides, so the instrument could have seen a
real gain or loss of the served head's size; it found none.

NOTHING IS ADOPTED on either side. No flag is wired into the serve path, no weights file is written,
`efv_weight_integrity.EFV_WEIGHT_INTEGRITY_ON` stays False and is read by nothing; there is no
OWNER QUESTION per passing arm because no arm passes. No row is written to `data/efv_progress.json`.
Nothing served moved.

What the read says:

- Real weights. Hitters: the hit tool (the hitter head's only key) is real (CI95 excludes 0 under
  both clusterings, all 14 cohort refits +). Pitchers: five of 21 keys are real (the population
  translation, called plus swinging strikes, the strikeout residual, the command grade, and popups
  with a negative sign), one is weak (IL days), fifteen read as noise one at a time. The planted
  check shows that 1,737 rows resolve only about a third of slopes of the served size, so noise
  here means "not shown", not "shown to be zero".
- The head weights. Hitter w_skill 0.297 is real but uncertain (CI95 0.08 to 0.59); pitcher
  w_skill 1.0 rests on a ratio whose CI95 is 0.53 to 1.87 (clipped at 1); both arrival ratios are
  negative, so w_time 0 is supported.
- Against consensus. The served hitter head does not beat consensus alone on these frames (S
  minus K -0.0014, CI95 -0.021 to +0.017); the served pitcher head leads it by +0.0095 (CI95 -0.013
  to +0.032). Both are ties.
- Simpler heads. Unit weights on the pitcher side tie the served head in point (+0.0007) with one
  fifth of its sampling variance on the live board, but its interval is too wide to clear the
  registered margin, so it is not adopted. Sparse top-k loses on pitchers (-0.013). The extended
  ridge grid picks the served penalty back.
- Shift. The live board differs from training mostly through the pitcher 60-day IL count (+1.23
  SD), the pitcher command grade (-0.39 SD) and the hitter hit tool grade (-0.46 SD). Re-reading
  those within level x season removes most of the separability (pitchers 0.718 to 0.620, hitters
  0.621 to 0.509) but costs the pitcher order -0.0048 (not non-inferior).
- Objective. The pairwise rank loss ties the served squared loss on hitters (+0.0013) and pitchers
  (-0.0015) and does not lose on the six-season label; it is not non-inferior after Holm.
