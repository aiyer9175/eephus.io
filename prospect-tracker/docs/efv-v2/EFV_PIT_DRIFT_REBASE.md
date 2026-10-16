# eFV pitcher drift rebase (EFV_PIT_DRIFT_REBASE): registration

Registration status: REGISTERED

Registered 2026-10-16, committed ALONE, before the code of this task exists and before any
number of its read is computed. Owner decision EW3-36 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
2026-10-16), after the pitcher eFV audit (Dylan Jordan and the pitchers who grade high): pitcher
w_skill stays 1.0; the drifted columns are REBASED (the audit's re-reads R2, and R1 in its rebuild
form); the sign question goes to EFV_PIT_SIGN_STABILITY and the BA grade to BA_GRADE_IN_CONSENSUS.
The run appends section 10 (the numbers) and section 11 (the verdict). No em-dashes.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019, vm_dev
debut cohorts 2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut
cohorts 2025 and later) is built or scored; `backtest.run_backtest` is never called; nothing is
grouped, counted or averaged by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`): the groups
are side, frame, fold (list year or decision year), column and read season. No model is
refitted: every head, slope, penalty, weight and the output map stay as served
(`data/efv5_refit_weights.json`, variant RT). The training columns are never changed; both
corrections act on the SERVED read only (the live board and the FV-history snapshots, the two
callers of `efv5_combined.support_clip`).

## 1. What the audit found (known before this registration)

- DRV-3. The Single-A group z columns of the pitcher skill head are wider on the live board than
  in training: the SD among nonzero values is 1.22x to 1.40x the training SD
  (`receipt.support[key].spread_ratio`, live read 2026-10-16). The spread report flags only
  above 2x (`SPREAD_RATIO`), so nothing acts on it.
- DRV-4. The pitcher 60-day IL count `scr_w2i_sixty_skill_pit` is nonzero on 33.6 percent of the
  live board against 8.8 percent of the production training rows, with board contribution SD 4.38
  against 1.85 percentile points; the receipt names it "drift" and serves it clipped.
- Outcome-blind probes of the stint table (`data/_labs/efv_w2/milb_il_stints.json`) before this
  registration, which fix the R1 definition below: the transaction feed changed its bookkeeping
  after 2020. Zero-length severe stints (a placement followed by a second placement of the same
  person on the same day) number 0 to 3 a year in 2009 to 2019 and 163 to 188 a year in 2024 to
  2026; a severe placement in spring after a severe stint activated in the autumn before (the
  same injury carried over the winter) numbers 10 to 32 a year before 2020 and 88 to 202 a year
  in 2024 to 2026. One live pitcher reads 6 severe stints in four seasons. The share of stints
  that are severe also rose (about 10 percent before 2020, 22 to 24 percent in 2021 to 2023, 35
  to 39 percent in 2024 to 2026) as the minor league 60-day and full-season lists came into use;
  that part is a change in league practice, not in the feed's bookkeeping.

## 2. R2: the Single-A group columns rebased to their training spread

REBASE_KEYS (pitchers, the served skill head's Single-A group z columns, seven):
`scr_g5_pit_A_all_all_k_pct`, `scr_g5_pit_A_all_all_k_minus_bb`, `scr_g5_pit_A_young_all_k_pct`,
`scr_g5_pit_A_young_all_k_minus_bb`, `scr_g5_pit_A_all_SP_k_pct`,
`scr_g5_pit_A_all_SP_k_minus_bb`, `scr_g5_pit_A_all_SP_bf_per_g`.

Rule, per key, on the values of one served read (one `support_clip` call):

    factor = training nonzero SD / served nonzero SD        (both SD ddof 1)
    v' = v * factor   for every nonzero served value v;     0.0 and None unchanged

with the training nonzero SD of `training_support` (the production training rows, the field
`nonzero_sd`) and the served nonzero SD over the call's non-None nonzero values BEFORE the clip.
No factor (the key is left as built) when either side has fewer than SPREAD_MIN_NONZERO (20)
nonzero values. A group z column is centered inside its group (the in-group mean is 0), so a
rescale about 0 changes its spread and keeps its center. The clip into the training
[min, max] then runs on the rebased values, as before. The factor is computed from the served
call itself, so it needs no stored constant and a later season re-derives it.

## 3. R1: the live 60-day IL count rebuilt on the training definition

`il_60day_pre` counts the stints in the read window placed on, or transferred before the cutoff
to, the 60-day or full-season list (`efv_w2_il_backfill.asof`). The rebuild counts INJURY
EPISODES the way the training-era feed recorded them. Inside the read window, in placement
order, a severe stint is not counted when:

1. DUPLICATE: it ended by a following placement ("next_placement") on its own start day (the
   feed reported one placement twice; the following stint of that day is the same stint), or
2. CARRY-OVER: it was placed (start day) from 1 January to 30 April, and the person's previous
   COUNTED severe stint in the window ended by activation on or after 1 October of the year
   before (the same injury re-placed in spring after the winter's paperwork).

Every other column of the IL family (stints, days, open, recurrent) is unchanged, and no
training column is recomputed. The rebuild touches only the served as-of read (`live_columns`,
`history_columns`); the twin rows and every training builder keep the stored definition.
Receipts the run reports (outcome-blind): the share of production training rows on which the
rebuilt count equals the stored training value (a probe of the rule over the full stint list
read 1,334 of 1,345 pitcher rows, 99.2 percent: on training-era data the rule IS the training
definition), the live nonzero share and nonzero SD before and after (the probe read 30.1 to
30.0 percent and 0.985 to 0.444, training 0.525). What the rebuild cannot remove (the league's
wider use of the 60-day lists) is reported as the residual share drift; it is not tuned away.

## 4. The rule generalized in support_clip (behind one flag)

`efv5_combined.DRIFT_REBASE_ON = False`. With it True:

- `support_clip` rebases (section 2) every key in REBASE_KEYS and every key the spread report
  flags (`spread_ratio` above SPREAD_RATIO, the existing 2x rule), so any future column whose
  served spread drifts past the report's own threshold is rebased with no new registration.
  A key flagged only for SHARE drift (`drift`) is not rescaled: a spread factor cannot correct a
  share, and such a column needs a definition rebuild (as R1) or a withhold, an owner choice.
  Each rebased key's receipt entry carries `rebase_factor` and `rebased: true`;
  `receipt["rebased"]` lists them.
- the served as-of read counts `il_60day_pre` by section 3.

With it False every served artifact is byte identical to the code before this task. Tests pin:
the factor's arithmetic on a synthetic support (planted 1.4x and 3x spreads recover the training
SD; a share-only drift is not rescaled; under 20 nonzero values nothing moves; flag off is the
identity), the episode rule on synthetic stints (duplicate, carry-over, a genuine second injury
still counted), and the training columns untouched.

## 5. The development read (pitchers; once)

Heads: the re-fit's own forward-chained RT fold heads and test rows (the EFV_FIX_B_REFIT cache:
`build1` and `packs_RT`), which reproduce the cached e_skill exactly before anything is read
(the run refuses otherwise). Orders at the SERVED weights (w_skill 1.0, w_time 0):
order = u_c + e_skill, inside (frame, side, fold). The dev analog of the served rule: a fold's
TEST rows are the served read and its skill TRAINING rows (without twins, as `training_support`
reads the production rows without twins) are the training support.

| id | test rows | role |
|---|---|---|
| S | as built | the served head; the zero-change comparator |
| C | R2 + R1 | the registered candidate |
| C2 | R2 only | decomposition |
| C1 | R1 only | decomposition |
| W | the seven Single-A keys and the 60-day count withheld (None, the head's training mean) | null arm: the strongest change of the same columns (the audit's R1 withhold) |

R2 on a fold: per key, factor = the fold's training nonzero SD over its test nonzero SD, both
with 20 or more nonzero values, else no factor. R1 on a fold: the test row's count recomputed by
section 3 at the row's own cutoff (lv_dev: the outcome-blind id at V-01-01; vm_dev: the matrix id
at `vm_cutoff`); parity first: the stored definition must reproduce every stored test value.

Statistics, pitchers, lv_dev, vm_dev and pooled:

1. PRIMARY: within (side, list year) Spearman (`efv_v2_stat`, groups of 20 or more), paired E_cond
   CI95 against S (`tools/efv_v3_backtest.paired`, B 2000, the backtest seed): C minus S, C2 minus
   S, C1 minus S, W minus S; C minus consensus and S minus consensus beside them.
2. Top-decile realization (the audit's validation (a) measure): shift = e_skill centered within
   (frame, fold); deciles of the centered shift within frame; expected outcome percentile from a
   quadratic of u_y on u_c within frame; realized share = mean residual over mean implied lift in
   the top decile (linear and bounded forms), for S and for C, and C minus S, player-clustered
   bootstrap B 2000, seed 20261016. Reported; it does not enter the ship rule.
3. NULL (placebo): 1,000 draws, seed 20261016; in each, every (fold, key) factor of C is replaced
   by itself or its reciprocal with equal probability (a rescale of the same size in a random
   direction), R1 kept; the pooled within delta against S. Reported: the 2.5 and 97.5 percentiles
   and the share of draws at or above C's delta.
4. PLANTED RECOVERY: on the scored pitcher rows the outcome is replaced by u_c + e_skill(X) +
   Gaussian noise (SD 0.3, seed 20261016) for X = C and for X = S, and C minus S is read with the
   instrument of 1. Recovery holds when planting C gives a delta whose CI95 lower bound is above 0
   and planting S gives a delta at or below 0. If it fails, the read cannot resolve a change of
   this size: the result is reported as such and nothing is flipped.

## 6. The ship rule and the flip

The re-fit's rule (`docs/efv-v2/EFV_V5_REFIT.md` section 6) with S in V5's place, pitchers: C
passes when (1) the row-weighted pooled within delta (n_lv x (C minus S on lv_dev) + n_vm x (C
minus S on vm_dev)) / (n_lv + n_vm) is above 0, and (2) C minus S is at least -0.005 on each
frame. The flip (DRIFT_REBASE_ON True, in the same commit as the build) happens only when C
passes, the planted recovery holds, and C does not lose rank accuracy, read as: neither frame's
within delta against S is below 0. Otherwise the rule is built dark (flag False) and the owner
question carries the read and the board effect.

## 7. The board effect (reported either way)

On the live board as of the run date through the served path (`efv_v2_serve.score_live` rows
and the served pitcher model), flag off against flag on: Dylan Jordan's eFV and rank; the mean
eFV minus consensus of the top 50 pitchers by eFV order; pitchers whose eFV moves by 1 or more and
by 3 or more; the 20 largest movers; per rebased key the factor; the 60-day share and nonzero SD
before and after. eFV prints to one decimal (nearest). Hitters are checked unchanged.

## 8. Artifacts and code

- `efv5_pit_rebase.py` (the read, `--run --cache <EFV_FIX_B_REFIT cache>`), writes
  `data/_labs/efv5/efv5_pit_rebase.json` (role development, adjudicates false);
- `efv5_combined.py` (REBASE_KEYS, DRIFT_REBASE_ON, the rule in support_clip, the flag on the
  served as-of read), `efv_w2_il_backfill.py` (the episode count, off by default);
- tests `test_efv5_pit_rebase.py`, `test_efv5_live_columns.py`, `test_efv_w2_il_backfill.py`;
- `data/xfv.json` regenerated only if the flag flips.

## 9. Defaults applied (the owner may choose differently)

- D-1 the factor is the ratio of nonzero SDs (the owner's words), applied about 0, per key, per
  served call; not a location-scale map.
- D-2 the generalized rule rebases spread-flagged keys at the existing 2x threshold; share-only
  drift is reported, not rescaled.
- D-3 R1 removes same-day duplicates and winter carry-overs only; the full-season list stays
  severe (it is in the registered SEVERE_LISTS), and the stints column keeps its definition.
- D-4 the dev analog reads a fold's test rows as the served read and its training rows without
  twins as the support.
- D-5 one flag for R1 and R2 together (the owner chose both).
