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
