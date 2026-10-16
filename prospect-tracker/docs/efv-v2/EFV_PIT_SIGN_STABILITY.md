# eFV pitcher slope signs: the stability read (EFV_PIT_SIGN_STABILITY)

Registration status: REGISTERED

Registered 2026-10-16, before any number below is computed. Owner decision EW3-36
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, 2026-10-16), after the pitcher eFV audit (Dylan
Jordan and the pitchers who grade high; its item R3 and owner decision 4): "signs TEST stability
first". The owner kept pitcher w_skill at 1.0; the drift re-basing (EFV_PIT_DRIFT_REBASE) and the
Baseball America grade question (BA_GRADE_IN_CONSENSUS) are their own lanes. This document is
committed ALONE, before the module `efv5_pit_sign.py` exists and before any slope, sign or
statistic of this read is computed. Sections 1 to 8 are written before the read; the run appends
section 9 (the numbers) and section 10 (the verdict).

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019, vm_dev
debut cohorts 2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts
2025 and later) is built, fitted or scored; nothing is grouped, counted or averaged by
consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`); `backtest.run_backtest` is never called; no
projections retrain; the fWAR label epoch's runbook is untouched; pitcher w_skill stays 1.0 and
w_time 0 (the served weights, `data/efv5_refit_weights.json`); hitters are not touched. No
em-dashes. With the flag of section 8 False, every served artifact is byte identical.

## 1. What is read

The served pitcher head is the registered re-fit's variant RT (`docs/efv-v2/EFV_V5_REFIT.md`,
flipped by owner EFV-REFIT-1 on 2026-10-15): one sign-bounded joint ridge of u_y on consensus and
21 candidate columns at lambda 1000. Six Single-A strikeout columns carry a sign bound (+1) from
the group atlas; the other fifteen are FREE-SIGNED (`efv5_combined.candidates()` sign 0), and
`efv5_combined._pens_and_bounds` lets each take either sign:

| key | family | registered prior sign (section 4) |
|---|---|---|
| `scr_g5_pit_A_all_SP_bf_per_g` (Single-A starter batters faced per game) | group | none |
| `scr_t5_pit_AAA_all_all_fb_fut` (Triple-A fastball future grade) | tool | + |
| `scr_w2i_stints_skill_pit` (IL stints before the read) | IL | - |
| `scr_w2i_days_skill_pit` (IL days, log1p) | IL | - |
| `scr_w2i_sixty_skill_pit` (60-day IL stints) | IL | - |
| `scr_w2i_open_skill_pit` (on the IL at the read) | IL | - |
| `scr_w2i_recur_skill_pit` (recurrent IL, 2 or more stints) | IL | - |
| `scr_w2p_cstr_p` (called strikes per pitch) | pitch event | + |
| `scr_w2p_csw_p` (called plus swinging strikes per pitch) | pitch event | + |
| `scr_w2p_k_resid_p` (strikeouts beyond the whiff rate) | pitch event | none |
| `scr_w2p_fstrike_p` (first-pitch strikes per batter) | pitch event | + |
| `scr_w2b_pu_p` (popups per ball in play) | pitch event (batted ball) | + |
| `scr_w4p_pop_pit` (population line translation, within-group rank) | popmle | + |
| `scr_w2s_brk_pit` (breaking-ball grade) | scouting | + |
| `scr_w2s_cmd_pit` (command grade) | scouting | + |

Every one of the fifteen is read; the task names the popup key, the five IL keys and the pitch
event keys, and the other five carry the same free sign. The V2 key `k_rel`, which sits in some
early fold heads through V2's admission (not a candidate column, absent from the production head),
is not read.

The folds: the ten pitcher development folds of the re-fit's own forward-chained build, lv_dev
pit|2017, 2018, 2019 and vm_dev pit|2017 to 2023, as cached by the re-fit's run (the
EFV_FIX_B_REFIT cache: `packs_RT.pkl`, each pack holding its fold model; `build1.pkl`;
`phase0.pkl`). The fit artifact's fold receipts (`data/_labs/efv5/efv5_refit_fit.json`
`fold_receipts.RT`) list each fold's nonzero keys but not the slopes; the slopes are read from
the cached fold models of the same folds, and the run first checks that each fold model's nonzero
list equals its receipt exactly (refuses otherwise). It also refits the unedited production
pitcher head from the cached production rows and checks that it equals the stored served head
(`data/efv5_refit_weights.json`) to 1e-9 on every slope (refuses otherwise).

## 2. The fold sign table

Per key and fold: the fitted standardized slope beta and beta over the fold's consensus slope
b_uc (percentile points of expected outcome per standard deviation of the column), its sign (+,
-, or 0 when the ridge and bounds put it at zero), or "not in head" when the fold's skill head
does not carry the candidate columns (a fold whose nested lambda is infinity). The production
fit's slope and sign stand beside them. A key FLIPS when its nonzero fold slopes take both signs.

## 3. The out-of-fold sign test

Per key k, on the scored pitcher test rows of every fold whose head carries k (each fold's
`ols` rows: u_c and u_y within the fold's scored rows, the fold model's out-of-fold terms):

- z_k: the row's standardized value under the fold head's own mean and SD (`efv_v2_model.skill_design`
  with the head's imputation; the RT rank transform applied as the head was fitted);
- part_k = beta_k z_k / b_uc and rest_k = e_skill minus part_k (the fold model's other drivers);
- OLS u_y ~ 1 + u_c + rest_k + z_k (+ e_time where it is nonzero, as DS-08's form carries it);
- the out-of-fold slope c_k is the coefficient on z_k: the direction the realized outcome took
  with the column, the fold model's other drivers and consensus held;
- CI95: player-clustered bootstrap (players drawn with replacement, all their fold rows
  together), B 2000, seed 20261016.

The key's sign is SUPPORTED out of fold when the CI95 excludes zero; it SPANS ZERO otherwise.

PLANTED RECOVERY of the sign test. On the same rows, u_y is replaced by u_c + rest_k + g z_k +
noise (Gaussian, SD 0.3, seed 20261016) for g = +0.02, -0.02 and 0 (0.02 per SD is about the
size of the board's largest free slopes); the same OLS and bootstrap run. The test RESOLVES key k
when g = +0.02 gives a CI95 above zero and g = -0.02 a CI95 below zero. The share of keys whose
g = 0 interval excludes zero is reported (about 5 percent expected).

A key is FLAGGED when any of: it flips across folds (section 2); its out-of-fold CI95 spans zero;
the sign test does not resolve it (planted recovery fails). A key that is not flagged is STABLE
and stays free-signed; nothing is built for it.

## 4. The arms (only for flagged keys)

For each flagged key k:

- B_k, sign-bounded: the key's slope bounded to its registered prior sign (section 1 table: the
  baseball direction, written here before any slope is read: IL keys hurt, strike, popup, grade
  and translation keys help; no prior for batters faced per game and the strikeout residual, whose
  direction is not a baseball given). No B arm for a key without a prior.
- D_k, dropped: the key removed from the pitcher skill head's candidate list.

When two or more IL keys are flagged, the family arms B_IL (every flagged IL key bounded at its
prior) and D_IL (every flagged IL key dropped) are also read, because the stint and day slopes
offset each other (the audit: +0.028 and -0.041) and a one-key edit moves the other.

Every arm is the re-fit's own fit with only that edit, in every fit (each development fold and
the production fit): `efv5_refit.fit_heads` on the fold's own rows as the re-fit built them
(forward chaining, twins in the vm_dev skill rows, the RT rank transform, the list-vintage timing
rows), the nested lambda re-selected by `efv5_combined.select_lambda` on the same grid, the same
dark list. The orders are read at the served weights: order = u_c + 1.0 x e_skill (w_time 0). The
pooled OLS weight ratio of each arm (DS-08's form) is reported beside it and decides nothing.

PARITY. Before any arm is read, the run refits the unedited RT pitcher folds and must
reproduce the cached fold models' e_skill on every test row to 1e-9 (refuses otherwise).

## 5. The statistic and the ship rule

The re-fit's instrument: within (frame, side, list year) Spearman of the order with the frozen
fWAR label (`fwar@2026-10-02-0341299c20ec`), groups of 20 or more rows, paired E_cond intervals
(players resampled, B 2000, seed 20260906, `efv_v3_backtest.paired`). Rows: the scored pitcher
test rows of the ten folds (lv_dev and vm_dev). Comparator: the SERVED head, RT at the served
weights (u_c + 1.0 x e_skill of the cached fold models), which the EFV_PIT_AUDIT_FIXES re-read
scored at +0.0107 against consensus on both frames.

An arm A PASSES when all four hold:

1. the re-fit's rule 1, pitchers: (n_lv x (A minus served on lv_dev) + n_vm x (A minus served on
   vm_dev)) / (n_lv + n_vm) > 0 (point estimates);
2. the re-fit's rule 2: A minus served >= -0.005 on lv_dev and on vm_dev;
3. NULL COMPARATOR: the arm's own change to the order (A's order minus the served order, row by
   row) permuted among each fold's scored rows, 1,000 permutations, seed 20261016: the pooled
   delta of the observed arm lies above the 97.5th percentile of the pooled deltas of the
   permuted changes (a change of the same size and shape that carries no information about the
   outcome must not do as well);
4. PLANTED RECOVERY: with the outcome replaced by the arm's own order plus noise (SD 0.3, seed
   20261016), A minus served has a CI95 above zero; with it replaced by the served order plus the
   same noise, A minus served is below zero. If recovery fails, the instrument cannot tell the
   arm from the served head and the arm is reported uninterpretable; it cannot pass.

The rule is read on pitchers only (the edit touches only the pitcher head; the re-fit's rule pools
over sides, which would dilute a pitcher difference by the unchanged hitters and make rule 2 looser).
Against consensus each arm's delta is reported (point, CI95) and does not enter the rule. An arm
whose orders equal the served orders on every row (no fold slope changes) is reported as identical
and fails rule 1.

## 6. The prepared arm

If no arm passes: nothing is prepared; the fold sign table and the reads are the result.

If one or more pass: the passing arm with the largest pooled delta is the BEST. The other passing
arms are taken in order of pooled delta and each one is added to a combined arm when its keys are
disjoint from the keys already in it. If the combined arm holds more than the best alone, it is
scored once by the full rule of section 5; it is prepared when it passes and its pooled delta
exceeds the best's, otherwise the best is prepared. Selection among several arms on the same
frames inflates the chance that one passes by noise; the run reports the number of arms read and
the results say so.

## 7. The board effect (for the owner)

For the prepared arm, its production pitcher fit (the re-fit's production rows, twins and timing
pool from the cache, weights 1.0 and 0) is scored on the live board as of the run date
(`efv5_refit.score_board`, list year 2026) against the served grades of `data/xfv.json`: Dylan
Jordan (eFV, rank), the mean of eFV minus consensus over the 50 highest-eFV pitchers, the mean
absolute eFV minus consensus, the count of pitchers moved by 1 or more and 3 or more, the 25
largest movers, and the share of the served top 50 still in the top 50. The eFV grade is printed to
one decimal (eFV rounds to nearest).

## 8. The flag and the artifacts

- `data/_labs/efv5/efv5_pit_sign_stability.json`: the parity receipts, the fold sign table, the
  sign tests and their planted recovery, every arm's read, the prepared arm and its board effect.
  Role development; adjudicates nothing; no row is written to `data/efv_progress.json`.
- If an arm is prepared: `efv5_pit_sign.PIT_SIGN_ARM_ON = False`, and
  `data/efv5_pit_sign_weights.json` holds the arm's production pitcher fit. With the flag True
  the serve path takes the pitcher model from that file (hitters unchanged); with it False every
  served artifact is byte identical to the code before this task. The owner flips it.
- Code `efv5_pit_sign.py` (one read: `--run` refuses when the artifact exists), tests
  `test_efv5_pit_sign.py`.

Defaults applied (the owner may choose differently): D-1 every free-signed key is read, not only
the named ones; D-2 the bounded arm uses the registered baseball prior, not the production sign
(a bound at the production sign cannot move the production fit, so it could never move the
board); D-3 the rule reads pitchers only; D-4 the null permutes the arm's own order change; D-5
planted slope 0.02 per SD and noise SD 0.3; D-6 the weights stay at the served 1.0 and 0.

## 9. The read (appended by the run, 2026-10-16; development frames)

Run: `python -u efv5_pit_sign.py --run --cache <re-fit cache> --work <scratch>` after the
registration commit 7a191e83 (artifact `data/_labs/efv5/efv5_pit_sign_stability.json`; label
`fwar@2026-10-02-0341299c20ec`; E_cond B 2000, seed 20260906; sign bootstrap B 2000, seed
20261016). The run was split into time-budgeted parts that resume from cached arms; after it a
copyright header (comment lines only) was added to the module and the artifact was re-assembled
from the same cached arms: every number is identical, only `generated_at`, `elapsed_s` and the
module hash moved. No reserved row was built; nothing was cut by consensus-FV level.

### 9.1 Receipts

- Each of the ten cached pitcher fold models' nonzero skill keys equals the fit artifact's fold
  receipt (`fold_receipts.RT`), all ten.
- The unedited production pitcher head refitted from the cache equals the stored served head on
  every slope (max difference 0.0).
- The unedited refit of the ten pitcher folds reproduces the cached e_skill on every test row
  (max difference 0.0); the key parts sum to e_skill to 2e-16.
- The served head on the scored rows: within Spearman 0.1714 (lv_dev, n 1,397), 0.3854 (vm_dev,
  n 424), 0.2198 (both, n 1,821), the EFV_PIT_AUDIT_FIXES re-read's own served values.

### 9.2 The fold sign table

Slope per standard deviation of the column, in order-index units (beta over the fold's consensus
slope; 0.01 is one percentile point of consensus rank). n/h: the fold's skill head does not carry
the candidate columns (vm_dev 2017, nested lambda infinity); +0.000 and -0.000 are nonzero slopes
under 0.0005. Prior: the registered baseball sign.

| key | prior | lv17 | lv18 | lv19 | vm17 | vm18 | vm19 | vm20 | vm21 | vm22 | vm23 | production | + / - | flips |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| g5_pit_A_all_SP_bf_per_g | none | -0.021 | -0.024 | -0.014 | n/h | +0.024 | +0.017 | +0.015 | +0.009 | +0.019 | +0.018 | +0.007 | 6 / 3 | yes |
| t5_pit_AAA_all_all_fb_fut | + | +0.000 | +0.013 | +0.039 | n/h | +0.000 | -0.000 | -0.000 | +0.007 | +0.006 | -0.001 | +0.017 | 6 / 3 | yes |
| w2i_stints_skill_pit | - | +0.023 | +0.002 | +0.021 | n/h | +0.002 | +0.001 | -0.004 | -0.001 | +0.007 | +0.016 | +0.028 | 7 / 2 | yes |
| w2i_days_skill_pit | - | +0.012 | -0.003 | -0.013 | n/h | +0.008 | -0.005 | -0.013 | -0.012 | -0.023 | -0.026 | -0.041 | 2 / 7 | yes |
| w2i_sixty_skill_pit | - | +0.051 | +0.035 | +0.048 | n/h | +0.019 | +0.017 | +0.016 | +0.023 | +0.008 | +0.003 | -0.018 | 9 / 0 | no |
| w2i_open_skill_pit | - | +0.046 | +0.019 | +0.003 | n/h | +0.012 | +0.008 | -0.009 | -0.001 | +0.006 | +0.004 | +0.005 | 7 / 2 | yes |
| w2i_recur_skill_pit | - | +0.014 | -0.001 | -0.002 | n/h | +0.004 | +0.008 | +0.003 | -0.003 | +0.015 | +0.021 | +0.017 | 6 / 3 | yes |
| w2p_cstr_p | + | +0.032 | +0.032 | +0.022 | n/h | +0.024 | +0.016 | +0.023 | +0.028 | +0.032 | +0.034 | +0.021 | 9 / 0 | no |
| w2p_csw_p | + | +0.003 | +0.014 | +0.003 | n/h | +0.011 | +0.034 | +0.042 | +0.055 | +0.054 | +0.065 | +0.067 | 9 / 0 | no |
| w2p_k_resid_p | none | +0.022 | +0.025 | +0.006 | n/h | +0.019 | +0.023 | +0.046 | +0.050 | +0.065 | +0.052 | +0.055 | 9 / 0 | no |
| w2p_fstrike_p | + | -0.000 | -0.002 | +0.017 | n/h | -0.010 | -0.019 | -0.015 | -0.020 | -0.004 | -0.011 | -0.008 | 1 / 8 | yes |
| w2b_pu_p | + | +0.027 | +0.003 | -0.032 | n/h | -0.006 | -0.017 | -0.024 | -0.036 | -0.060 | -0.077 | -0.067 | 2 / 7 | yes |
| w4p_pop_pit | + | +0.022 | +0.035 | +0.039 | n/h | +0.031 | +0.055 | +0.075 | +0.085 | +0.102 | +0.097 | +0.128 | 9 / 0 | no |
| w2s_brk_pit | + | -0.015 | +0.015 | -0.012 | n/h | +0.013 | +0.024 | +0.028 | +0.018 | +0.017 | +0.025 | +0.020 | 7 / 2 | yes |
| w2s_cmd_pit | + | +0.029 | +0.016 | +0.031 | n/h | +0.014 | +0.018 | +0.025 | +0.038 | +0.049 | +0.048 | +0.055 | 9 / 0 | no |

Read plainly:

- Six keys hold one sign in all nine folds that carry them, all +: called strikes, called plus
  swinging strikes, the strikeout residual, the population translation, the command grade and the
  60-day IL count.
- Nine keys flip: batters faced per game (- in the three list-year folds, + in the six debut-year
  folds), the fastball grade, IL stints, IL days, IL open, IL recurrence, first-pitch strikes, the
  popup rate and the breaking-ball grade. The fastball grade's three negative folds are slopes
  under 0.0005 (shown -0.000).
- The popup rate is + in the two earliest list-year folds and - in the seven later folds, growing
  more negative with more training years (-0.006 to -0.077); the production slope is -0.067.
- The 60-day IL count is + in every fold (more 60-day stints went with a better outcome, the other
  drivers held) but - in the production fit (-0.018), the only key whose production sign is
  opposite to every fold. The production fit adds decision years 2023 and 2024
  and their twins to the last fold's rows.
- IL stints and IL days offset each other in most folds, as the audit found in production.

### 9.3 The out-of-fold sign test

The partial slope of the realized outcome percentile on the key (per SD), with consensus, the fold
model's other drivers and e_time held; 1,805 scored rows (the nine folds whose head carries the
keys), player-clustered CI95. Planted: the same read with u_y replaced by u_c + rest + g z + noise.
At g = 0, no key's interval excluded zero (share 0.0).

| key | rows | out-of-fold slope | CI95 | sign | planted +0.02 CI95 | planted -0.02 CI95 | resolves | flagged |
|---|---|---|---|---|---|---|---|---|
| g5_pit_A_all_SP_bf_per_g | 1805 | +0.0051 | -0.0063 to +0.0170 | spans zero | +0.0068 to +0.0321 | -0.0332 to -0.0079 | yes | flips across folds; out-of-fold CI95 spans zero |
| t5_pit_AAA_all_all_fb_fut | 1805 | +0.0039 | -0.0082 to +0.0177 | spans zero | +0.0120 to +0.0351 | -0.0280 to -0.0049 | yes | flips across folds; out-of-fold CI95 spans zero |
| w2i_stints_skill_pit | 1805 | -0.0047 | -0.0198 to +0.0119 | spans zero | -0.0035 to +0.0249 | -0.0435 to -0.0151 | no | flips across folds; out-of-fold CI95 spans zero; sign test does not resolve the planted slope |
| w2i_days_skill_pit | 1805 | -0.0101 | -0.0265 to +0.0072 | spans zero | +0.0070 to +0.0346 | -0.0330 to -0.0054 | yes | flips across folds; out-of-fold CI95 spans zero |
| w2i_sixty_skill_pit | 1805 | +0.0029 | -0.0110 to +0.0150 | spans zero | -0.0022 to +0.0219 | -0.0422 to -0.0181 | no | out-of-fold CI95 spans zero; sign test does not resolve the planted slope |
| w2i_open_skill_pit | 1805 | -0.0018 | -0.0136 to +0.0096 | spans zero | +0.0138 to +0.0410 | -0.0262 to +0.0010 | no | flips across folds; out-of-fold CI95 spans zero; sign test does not resolve the planted slope |
| w2i_recur_skill_pit | 1805 | -0.0055 | -0.0209 to +0.0101 | spans zero | -0.0073 to +0.0209 | -0.0473 to -0.0191 | no | flips across folds; out-of-fold CI95 spans zero; sign test does not resolve the planted slope |
| w2p_cstr_p | 1805 | +0.0177 | +0.0012 to +0.0332 | + | +0.0032 to +0.0300 | -0.0368 to -0.0100 | yes | stable |
| w2p_csw_p | 1805 | -0.0034 | -0.0214 to +0.0145 | spans zero | +0.0031 to +0.0330 | -0.0369 to -0.0070 | yes | out-of-fold CI95 spans zero |
| w2p_k_resid_p | 1805 | +0.0034 | -0.0140 to +0.0209 | spans zero | -0.0029 to +0.0299 | -0.0430 to -0.0101 | no | out-of-fold CI95 spans zero; sign test does not resolve the planted slope |
| w2p_fstrike_p | 1805 | +0.0098 | -0.0062 to +0.0253 | spans zero | +0.0106 to +0.0356 | -0.0294 to -0.0044 | yes | flips across folds; out-of-fold CI95 spans zero |
| w2b_pu_p | 1805 | -0.0234 | -0.0391 to -0.0084 | - | +0.0002 to +0.0260 | -0.0398 to -0.0140 | yes | flips across folds |
| w4p_pop_pit | 1805 | +0.0271 | +0.0110 to +0.0424 | + | +0.0081 to +0.0405 | -0.0319 to +0.0005 | no | sign test does not resolve the planted slope |
| w2s_brk_pit | 1805 | -0.0049 | -0.0221 to +0.0118 | spans zero | +0.0024 to +0.0344 | -0.0376 to -0.0056 | yes | flips across folds; out-of-fold CI95 spans zero |
| w2s_cmd_pit | 1805 | +0.0314 | +0.0128 to +0.0500 | + | +0.0186 to +0.0472 | -0.0214 to +0.0072 | no | sign test does not resolve the planted slope |

Read plainly:

- Out of fold, four keys show a sign: called strikes +, the population translation +, the command
  grade + and the popup rate - (-0.023, CI95 -0.039 to -0.008). The popup rate's out-of-fold
  sign is the fitted one: with the other drivers equal, pitchers who allowed fewer popups did
  better. Its baseball prior (+) is not what the outcome shows.
- Every other key's interval spans zero. For the five IL keys, the strikeout residual, the
  population translation and the command grade, the read could not resolve a planted slope of
  0.02 per SD in one direction or the other (the IL columns are mostly zero; the others move with
  correlated keys), so for those the test cannot speak and the key is flagged by rule.
- Flagged: 14 of 15 keys. Stable: called strikes alone, which stays free-signed.

### 9.4 The arms

28 arms were read: a bounded and a dropped arm for each flagged key with a prior, a dropped arm for
the two without (batters faced per game, the strikeout residual), and the IL family pair. Three
bounded arms are identical to the served head (every fold already holds the prior sign). Orders at
the served weights (pitcher w_skill 1.0, w_time 0); within Spearman minus the served head, E_cond
CI95; pooled is the row-weighted mean of the two frames (n 1,397 and 424).

| arm | lv_dev minus served | vm_dev minus served | pooled | both CI95 | null q975 | planted | both minus consensus | passes |
|---|---|---|---|---|---|---|---|---|
| D:g5_pit_A_all_SP_bf_per_g | +0.0009 | -0.0044 | -0.0003 | -0.0032 to +0.0028 | +0.0023 | not recovered | +0.0104 (-0.014 to +0.034) | no |
| B:t5_pit_AAA_all_all_fb_fut | +0.0000 | -0.0000 | -0.0000 | -0.0001 to +0.0000 | +0.0001 | not recovered | +0.0107 (-0.013 to +0.035) | no |
| D:t5_pit_AAA_all_all_fb_fut | -0.0085 | +0.0002 | -0.0065 | -0.0122 to -0.0007 | +0.0043 | recovered | +0.0041 (-0.018 to +0.027) | no |
| B:w2i_stints_skill_pit | +0.0010 | -0.0013 | +0.0004 | -0.0009 to +0.0019 | +0.0012 | not recovered | +0.0111 (-0.012 to +0.035) | no |
| D:w2i_stints_skill_pit | +0.0010 | -0.0012 | +0.0005 | -0.0009 to +0.0019 | +0.0012 | not recovered | +0.0112 (-0.012 to +0.035) | no |
| B:w2i_days_skill_pit | +0.0005 | +0.0004 | +0.0005 | -0.0001 to +0.0011 | +0.0005 | not recovered | +0.0112 (-0.012 to +0.035) | no |
| D:w2i_days_skill_pit | +0.0008 | -0.0014 | +0.0003 | -0.0013 to +0.0021 | +0.0011 | not recovered | +0.0110 (-0.012 to +0.035) | no |
| B:w2i_sixty_skill_pit | -0.0087 | -0.0028 | -0.0074 | -0.0140 to -0.0005 | +0.0045 | recovered | +0.0033 (-0.019 to +0.025) | no |
| D:w2i_sixty_skill_pit | -0.0087 | -0.0028 | -0.0074 | -0.0140 to -0.0005 | +0.0045 | recovered | +0.0033 (-0.019 to +0.025) | no |
| B:w2i_open_skill_pit | +0.0007 | -0.0008 | +0.0003 | -0.0018 to +0.0026 | +0.0022 | recovered | +0.0110 (-0.012 to +0.035) | no |
| D:w2i_open_skill_pit | +0.0007 | -0.0001 | +0.0005 | -0.0017 to +0.0028 | +0.0022 | recovered | +0.0112 (-0.012 to +0.035) | no |
| B:w2i_recur_skill_pit | +0.0002 | +0.0019 | +0.0006 | -0.0007 to +0.0019 | +0.0008 | not recovered | +0.0112 (-0.012 to +0.035) | no |
| D:w2i_recur_skill_pit | +0.0001 | +0.0016 | +0.0005 | -0.0008 to +0.0018 | +0.0009 | not recovered | +0.0111 (-0.013 to +0.035) | no |
| B:w2p_csw_p | identical to served (every fold already at the prior sign) | | | | | | | no |
| D:w2p_csw_p | +0.0005 | +0.0022 | +0.0009 | -0.0024 to +0.0042 | +0.0023 | not recovered | +0.0116 (-0.011 to +0.034) | no |
| D:w2p_k_resid_p | +0.0014 | -0.0022 | +0.0006 | -0.0030 to +0.0041 | +0.0024 | not recovered | +0.0113 (-0.011 to +0.034) | no |
| B:w2p_fstrike_p | +0.0001 | -0.0012 | -0.0002 | -0.0018 to +0.0013 | +0.0009 | not recovered | +0.0104 (-0.013 to +0.034) | no |
| D:w2p_fstrike_p | -0.0008 | -0.0012 | -0.0009 | -0.0026 to +0.0007 | +0.0012 | not recovered | +0.0097 (-0.014 to +0.033) | no |
| B:w2b_pu_p | -0.0084 | -0.0094 | -0.0086 | -0.0148 to -0.0022 | +0.0041 | recovered | +0.0020 (-0.020 to +0.025) | no |
| D:w2b_pu_p | +0.0007 | -0.0094 | -0.0016 | -0.0056 to +0.0028 | +0.0030 | recovered | +0.0091 (-0.014 to +0.033) | no |
| B:w4p_pop_pit | identical to served (every fold already at the prior sign) | | | | | | | no |
| D:w4p_pop_pit | -0.0103 | -0.0024 | -0.0085 | -0.0160 to -0.0011 | +0.0043 | recovered | +0.0022 (-0.020 to +0.025) | no |
| B:w2s_brk_pit | +0.0003 | +0.0000 | +0.0002 | -0.0009 to +0.0014 | +0.0012 | not recovered | +0.0109 (-0.013 to +0.035) | no |
| D:w2s_brk_pit | +0.0003 | +0.0017 | +0.0006 | -0.0014 to +0.0028 | +0.0018 | not recovered | +0.0113 (-0.012 to +0.034) | no |
| B:w2s_cmd_pit | identical to served (every fold already at the prior sign) | | | | | | | no |
| D:w2s_cmd_pit | -0.0112 | -0.0050 | -0.0098 | -0.0161 to -0.0032 | +0.0044 | recovered | +0.0009 (-0.022 to +0.023) | no |
| B:IL | -0.0076 | -0.0007 | -0.0060 | -0.0142 to +0.0022 | +0.0052 | recovered | +0.0046 (-0.017 to +0.026) | no |
| D:IL | -0.0076 | -0.0003 | -0.0059 | -0.0140 to +0.0023 | +0.0053 | recovered | +0.0047 (-0.017 to +0.027) | no |

Read plainly:

- No arm passes. Twelve arms clear rule 1 and rule 2 (pooled +0.0002 to +0.0009: the IL stint,
  day, open and recurrence arms, dropping called plus swinging strikes, the strikeout residual or
  the breaking-ball grade), but none lies above its own null (an equal-size change carrying no
  information does as well), and for most of them planted recovery fails: the instrument cannot
  tell them from the served head.
- The arms that remove a key with an out-of-fold signal lose, and the losses resolve: dropping the
  command grade -0.0098 (CI95 -0.0161 to -0.0032), bounding the popup rate at its baseball sign
  -0.0086 (-0.0148 to -0.0022), dropping the population translation -0.0085 (-0.0160 to -0.0011),
  removing the 60-day IL count -0.0074 (-0.0140 to -0.0005), dropping the fastball grade -0.0065
  (-0.0122 to -0.0007). The IL family arms lose -0.0060 (bounded) and -0.0059 (dropped), CI95
  spanning zero.
- Dropping the popup rate: lv_dev +0.0007, vm_dev -0.0094; pooled -0.0016 (CI95 -0.0056 to
  +0.0028); fails rule 1 and rule 2.
- Every arm's DS-08 weight ratio is reported in the artifact; none decides anything.

## 10. The verdict

Nothing passes the rule, so nothing is prepared: no flag is built into the serve path, no weights
file is written, and no board effect is computed (section 7 reads only a prepared arm). The fifteen
free-signed pitcher keys stay as served. `efv5_pit_sign.PIT_SIGN_ARM_ON` stays False and is read by
nothing. Nothing served moved.

What the read says about the owner's question (audit R3, owner decision 4):

- The popup slope is positive only in the two earliest list-year folds (2017, 2018); the other
  seven folds and the production fit hold the negative sign, the out-of-fold test supports it, and forcing
  the baseball sign costs a resolvable -0.0086. The served sign is the one the outcome supports;
  the chip text (EFV_PIT_AUDIT_FIXES) already says a low popup rate grades up.
- The IL keys are unstable in sign and their signal is not resolvable out of fold; bounding or
  dropping them neither helps nor resolvably hurts, except the 60-day count, whose removal hurts.
  The 60-day count's production sign (-) is opposite to every development fold (+); that belongs
  with the 60-day drift question (EFV_PIT_DRIFT_REBASE, audit R1).
