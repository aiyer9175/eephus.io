# eFV side and role calibration (EFV_SIDE_ROLE_CALIBRATION): registration

Registration status: REGISTERED; READ ONCE 2026-10-19 (sections 11 and 12)

Registered 2026-10-19, committed ALONE, before any number of its read is computed. Owner
decision EW3-42 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, 2026-10-19), verbatim: "I feel like
pitchers are inflated across the board, especially relief pitchers." The task follows
EFV_X3_POOLED_MODEL, which failed its rule (`docs/efv-v2/EFV_X3_POOLED_MODEL.md` section 14), so
the model under test is the one that serves: eFV v5 COMBINED, re-fit variant RT
(`docs/efv-v2/EFV_V5_REFIT.md`; hitters w_skill 0.2965, pitchers w_skill 1.0, w_time 0 on both
sides). The run appends section 11 (the numbers) and section 12 (the verdict). No em-dashes.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019, vm_dev
debut cohorts 2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut
cohorts 2025 and later) is built or scored; `backtest.run_backtest` is never called; no model is
refitted (every head, weight and the order index stay as served); no projections retrain; the
fWAR label epoch's runbook is not touched; the served grade does not change under any outcome of
this read; the realized anchor is read as it stands and never re-fitted.

## 0. The PROSPECT_ANCHOR_GATE reading, stated before any number

`docs/PROSPECT_ANCHOR_GATE.md` forbids computing a realized-WAR mean, residual, cohort count or
anchor by consensus-FV cell (45/50/55/60/65+), and any stratum named after an FV cell. The owner's
question ("does a 55 pitcher realize what a 55 hitter does") is phrased on the grade, so the
reading is fixed here:

1. The x-axis is the served eFV GRADE, the model output under test, never consensus FV. No row is
   grouped, counted or averaged by consensus FV. Consensus enters only as it enters the served
   grade (the group's value set of the rank map) and as the reference of the rank guard.
2. No group of rows is defined by a grade value. The only groups are frame, fold (list year or
   debut year), side, pitcher usage role, X3's role path, and the top tenth of each (frame, fold,
   side) group by eFV grade (a within-group quantile, not a grade cell). The calibration error
   bins (section 5.2) are equal-count groups of each candidate's own implied value inside (frame,
   side), never grade cells.
3. The fitted object is a monotone curve of the realized label on the eFV grade (isotonic, its
   blocks set by the data, not by FV-cell edges), used only to build a grade-to-grade map. The
   artifact stores the MAP (g to g', section 8) and never the curve's realized levels; no table of
   realized WAR at any grade value is published, in the artifact, in this document or in the
   owner question.
4. The anchor `value_framework.fv_to_6yr_avg_war` is an INSTRUMENT read as it stands: every
   candidate's implied value is the served anchor at the candidate's grade. Its level is not
   tested, re-fitted or adjudicated here; that is the anchor gate's own question. The incumbent
   against a side-pooled isotonic fit (which would be an anchor read on the eFV grade) is not a
   candidate and is not computed.
5. The live-board effect evaluates the maps at live rows' grades and at each live side's own
   grade quantiles (the median, 90th and 98th percentile rows), never at a named grade value.

The tests pin points 2 and 3 by a source scan of the lab (no FV-cell constant names a group).

## 1. What is known before this registration

- The served value chain is side-pooled in WAR. `value_framework.expected_six_year_avg_war(fv,
  is_pitcher)` reconciles both sides to the same anchor (`_fv_war_scale`, `_war_anchor_scale_for`
  is 1.0 for both roles), so at every grade a pitcher and a hitter carry the same expected
  six-season WAR (read 2026-10-19 at grades 40 to 60: identical by side). Surplus differs by side
  only through the dollar layers (the pitcher bucket probabilities, the reliever-bucket blend
  `_pitcher_rp_by_bucket`, the reliever arbitration profile), not through expected WAR.
- `xfv_war_6yr` on the board is a per-side WLS line of the training target on consensus FV
  (`efv_v2_model.fit_war_map`), labelled "context only"; it prices nothing.
- Inside a (side, list year) group the served grade multiset IS the group's consensus multiset
  (`efv_v2_model.output_map`, DS-07), so any across-the-board side inflation sits in the grade
  scale, not in the model's re-ranking.
- Published priors read during design, recorded so the run cannot quietly beat them:
  `docs/efv-2026-07-30/CROSS_SIDE_WAR_FINDING.md` (consensus FV is not cross-side comparable;
  hitters out-realize pitchers at the top of the consensus scale, pitchers modestly out-realize
  hitters at the bottom, on the bWAR label); `docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md` (a
  per-side curve on consensus FV did not beat its side-label-permuted control on held-out MAE);
  `docs/efv-v2/EFV_OUTPUT_MAP_TEST.md` section 11 (calibration slopes of the label on the per-side
  curve under a per-side kappa: hitters 0.76, pitchers 0.75); `docs/efv-v2/EFV_RELIEVER_ADJ.md`
  (relievers' upward model shifts realized little, nothing resolved); `EFV_X3_POOLED_MODEL.md`
  13.8 (pitchers by usage role, every interval spanning zero). The direction of a side effect
  therefore has a published prior on a different axis and label; this read is confirmatory in the
  same sense as the anchor gate's G-0.1 and protects itself with a two-sided read, a permuted
  null, planted recovery and a frame check.
- An earlier display fix (F-SIDE-FIX, `efv_score._apply_side_fairness_fix`, 2026-07-24) reorders
  the joint top band of eFV v1 display grades; it does not price expected WAR by side and it is
  not a candidate here.

Nothing about this read's outcome has been computed. The lab's outcome-free `--check` ran once to
produce the counts of section 3 (it reads row identities, grades, usage lines and the X3 role
sub-model, and computes no statistic of any label).

## 2. The questions

- Q-SIDE: at the same eFV grade, does a pitcher realize the value a hitter realizes, as a
  fraction of what the served value chain implies?
- Q-ROLE: among pitchers at the same grade, do relievers (and short starters) realize less than
  starters?
- Q-FIX: does a calibration of the grade to a common expected-value scale, by side (b) or by side
  and pitcher usage role (c), predict realized value better than the incumbent (a, no mapping),
  without losing within-side rank accuracy?

## 3. Frames, rows and checks

Rows: the scored rows of both development frames that sit in a fold's test rows of the served RT
fold builds (the EFV_FIX_B_REFIT cache: `build1.pkl`, `packs_RT.pkl`), exactly the rows
`efv_output_map.prepare` builds. The served grade on each row is map A (`output_map` of the
served-weight order index inside its fold's test rows). Outcome-free counts (`--check`,
2026-10-19):

| frame | hitters | pitchers | STARTER | SHORT-START | RELIEF | OTHER (FEW, NO-LINE) | X3 relief path |
|---|---|---|---|---|---|---|---|
| lv_dev | 1,465 | 1,397 | 844 | 106 | 322 | 125 | 909 |
| vm_dev | 406 | 424 | 324 | 13 | 73 | 14 | 277 |

3,692 rows, 1,987 players, ten (frame, fold) groups (lv_dev 2017 to 2019, vm_dev 2017 to 2023).

Pitcher usage role at the read: `efv_reliever_adj.usage` through its `RoleBook` (the rule that
writes `data/efv_pitcher_roles.json` and prints on the card: RELIEF when GS / G < 0.5;
SHORT-START when GS / G >= 0.5 and IP / GS < 3.5; STARTER otherwise; FEW and NO-LINE are OTHER),
read as of each row's own read season. X3's role path: P(ends a reliever) from X3's role
sub-model (`efv_x3_pooled.role_model`, section 6.5 of its registration) refitted per outer fold
on that fold's reached training pitchers, exactly as X3's pipeline fits it, from the X3 read's
cache; RELIEF path when P >= 0.5, else STARTER path. Every development pitcher row joins (1,821).

Checks, before any outcome is read (the output map test's own, reused): Q1 every cached fold
model's nonzero skill list equals the re-fit artifact's receipt; Q2 (run only) the cross-fitted
RT within reproduces the fit artifact on each frame and side and the served-weight pitcher within
reproduces the pitcher re-read; Q3 no reserved fold; Q4 the live board reproduces (u_c to 1e-6,
map A to the served one-decimal grade within 0.05, every row). The label provider must be the
frozen fWAR provider.

## 4. The candidates

Notation. Row i in (frame, fold) group G: label y_i (lv_dev: fWAR over the first three seasons in
the window, 0 without a debut; vm_dev: career fWAR resolved through 2026), served grade g_i,
served order o_i. Instrument I(g) = 6 x `value_framework.fv_to_6yr_avg_war(g)` (the served,
side-pooled six-season anchor). Level scalar kappa_G = (sum of y over G) / (sum of I(g) over G),
ONE number per (frame, fold) pooled over both sides (a per-side kappa would absorb the side
effect under test). Scaled label z_i = y_i / kappa_G. The implied value of a map with grade g' is
v_i = kappa_G x I(g'_i).

Curves. F_S = the increasing isotonic fit (PAVA, rows weighted equally, tied grades pooled first,
equal adjacent blocks merged so the fit is strictly increasing) of z on g over a row set S,
evaluated by linear interpolation between block means and flat beyond the end blocks. Grade map:
g' = the point of the preimage {x : F_pool(x) = t} nearest to g, with t = F_S(g) clamped to
F_pool's range (so g' = g wherever t falls on a flat end of F_pool). F_pool is fitted on every
training row of both sides: the common expected-value scale.

| id | map | |
|---|---|---|
| a | g' = g | the incumbent (no mapping) and the no-side comparator: with S = all rows the map is the identity |
| b | t = F_side(g), side of the row | side-specific isotonic calibration to the common scale |
| c | hitters as b; pitchers t = F_pit,role(g) for STARTER, SHORT-START, RELIEF; OTHER uses F_pit; a role with fewer than 60 training rows uses F_pit | side x usage role |
| c_x3 | as c with X3's role path (STARTER path, RELIEF path) | sensitivity, decides nothing |

Cross-fitting: each (frame, fold) group is mapped by curves fitted on every other group's rows,
excluding every player who has a row in the held-out group. The production map (section 8) is
fitted on all rows. Because each map is non-decreasing in g inside a side (and, for c, inside a
role), b never reorders a side; c can reorder pitchers across roles.

## 5. Statistics (all rows of both sides, both frames pooled, rows weighted equally)

1. PRIMARY: delta MSE(X vs Y) = mean(e_Y - e_X), e_i = (y_i - v_i)^2 / var_F, var_F the label
   variance of the row's frame over all its rows (so each frame weighs by its rows, not by its
   label's scale). Paired player-clustered CI95 (`source_backtest`'s resampler, B 2000, seed
   20261020) and the one-sided p (share of draws at or below 0). Positive: X is closer. Squared
   error because the implied value is an expected value.
2. Calibration error: ECE_X = row-weighted mean over the four (frame, side) cells of the cell's
   mean abs(mean y - mean v) over 10 equal-count groups of rows sorted by v_X, in units of the
   frame's label SD. delta ECE = ECE_Y - ECE_X with a player-clustered CI95 (B 1000).
3. Calibration slope of y on v per side (OLS, CI95), reported.
4. Rank guard: within (frame, side, year) Spearman of the map's ordering (g', ties by the served
   order) minus the served ordering's, per side, pooled and per frame (`efv5_refit.within_of`,
   the registered within statistic; paired CI where the delta is nonzero).
5. Null comparators: SIDE-PERMUTED b (side labels shuffled within each (frame, fold) group before
   the curves are fitted; the mapped rows keep their true side), K 200 draws: the 95th percentile
   of delta MSE(b_perm vs a). ROLE-PERMUTED c (pitcher role labels shuffled likewise), K 200: the
   95th percentile of delta MSE(c_perm vs b) on the pitcher rows.
6. Planted recovery: y*_i = v_a,i x m_i + (y_pi(i) - mean y of the row's (frame, fold, side)
   cell), pi a permutation inside the cell (noise with the label's own spread; no residual is
   formed), and the whole pipeline (kappa, curves, maps) rerun on y*. SIDE: m = 1.15 hitters,
   0.85 pitchers; POWER_b = share of K 100 draws with delta MSE(b vs a) lower bound above 0
   (B 500); SIZE_b the same with m = 1 everywhere. ROLE: m = 0.75 on RELIEF pitchers, 1 elsewhere;
   POWER_c = share with delta MSE(c vs b) on the pitcher rows lower bound above 0; SIZE_c with
   m = 1.
7. Sensitivity instrument: the pooled outcome curve the board basis inverts
   (`data/fv_outcome_curves_pooled.json` `curve.value`) in place of I, kappa recomputed.

## 6. Reported, deciding nothing (answers Q-SIDE and Q-ROLE)

Under the incumbent, with player-clustered CI95 (B 2000), pooled and per frame: R_S = (sum y) /
(sum v_a) over a row set S; pitchers over hitters (R_pit / R_hit); the same inside the top tenth of
each (frame, fold, side) group by eFV grade and below it; by usage role (each role's R over the
hitters' R and over the starters' R); by X3's role path. R below 1 for one side and above for the
other says that side realizes less than the side-pooled value chain implies at its grades. Because
kappa is pooled over sides, R_pit / R_hit is the pitchers' realized share of a hitter's at matched
implied value.

## 7. The rule (fixed here)

b passes when all hold:

- B1 delta MSE(b vs a) pooled CI95 lower bound above 0;
- B2 delta MSE(b vs a) at or above 0 on each frame;
- B3 delta ECE(b vs a) pooled at or above 0;
- B4 rank guard at or above -0.002 for each side, pooled and on each frame (zero by
  construction; asserted);
- B5 delta MSE(b vs a) above the side-permuted null's 95th percentile;
- B6 delta MSE(b vs a) above 0 under the pooled-curve instrument;
- B7 SIZE_b at most 0.10.

c passes when all hold:

- C1 to C3 as B1 to B3 for c against a;
- C4 the pitcher rank guard of c at or above -0.002 pooled and on each frame;
- C5 delta MSE(c vs b) on the pitcher rows CI95 lower bound above 0 (the role adds to the side);
- C6 that delta above the role-permuted null's 95th percentile;
- C7 delta MSE(c vs a) above 0 under the pooled-curve instrument;
- C8 SIZE_c at most 0.10.

Prepared: c when c passes; else b when b passes; else nothing. A failure is worded by its planted
power: at or above 0.80 a NULL (an effect of the planted size would have been resolved), below it
UNRESOLVED (the frames cannot resolve an effect of that size), which says nothing in favour of the
incumbent beyond that. No Holm correction: c is read only together with b and against it.

## 8. What ships under each outcome

- Nothing passes: nothing is built. The artifact `data/_labs/efv5/efv_side_role_calibration.json`
  (role development, adjudicates false), sections 11 and 12 here, `EFV_SIDE_ROLE_CALIBRATION_RESULTS.md`
  (plain language) and one ledger line in `docs/efv-v2/STATUS.md` are the whole result; no served
  number moves.
- b or c passes: built DARK. `efv_side_role_calibration.SIDE_ROLE_CALIBRATION_ON` (default False,
  byte identical) gates a hook that prices the value chain (surplus_mm, band, dist, and the
  six-season WAR the card shows) at the calibrated grade g' from the production map (fitted on all
  development rows, stored as a grade-to-grade table on the grid 20.0 to 80.0 by 0.1 in a committed
  data file), per side and, for c, per usage role from `data/efv_pitcher_roles.json`. The displayed
  eFV grade, the rank and the order index do not change. Tests pin the default, the map's
  monotonicity inside each side and role, and byte identity with the switch off. `OWNER_QUESTION.md`
  in the task's output directory carries the board effect (pitchers against hitters at the same
  grade, relievers, the top 50 of each side, the joint top 100's pitcher count) for the owner to
  flip. The owner flips it; this task does not.

The live-board effect (section 8 of the artifact) is computed for b and c under every outcome and
decides nothing.

## 9. Gate compliance and stop rules

If any of Q1 to Q4 fails, or the label provider is not the frozen fWAR provider, no outcome is
read and the result is the refusal. The artifact is written once; a second `--run` refuses.

## 10. Defaults applied (named for the orchestrator)

- D-1: the served map A grade and the served weights; nothing refitted.
- D-2: the served side-pooled anchor is the primary instrument (it is what surplus reconciles
  to); the pooled outcome curve is the sensitivity.
- D-3: one kappa per (frame, fold), pooled over sides.
- D-4: squared error standardized by each frame's label variance is primary; ECE must not worsen.
- D-5: usage role at the read (the card's rule) is the role of c, because it exists on the live
  board; X3's role path is a sensitivity because X3 does not serve and has no live probability.
- D-6: constants seed 20261020, B 2000, B_ECE 1000, K_NULL 200, K_PLANT 100, B_PLANT 500, 10 ECE
  groups, top share 0.10, guard -0.002, SIZE at most 0.10, POWER 0.80, role minimum 60 training
  rows, X3 relief cut 0.5, planted side multipliers 1.15 / 0.85, planted relief multiplier 0.75.

Run: `python -u efv_side_role_calibration.py --run --cache <EFV_FIX_B_REFIT cache> --x3-cache
<EFV_X3_POOLED_MODEL cache> --work <scratch>` after this registration and the module's commit.

## 11. The read (2026-10-19, once; `python -u efv_side_role_calibration.py --run`)

Artifact: `data/_labs/efv5/efv_side_role_calibration.json` (role development, adjudicates false;
tool sha256 81749414, module commit 48fc666d, registration commit 3f60b82d, label
fwar@2026-10-02). Elapsed 87 s.

Checks, all held before any outcome was read: Q1 the 20 cached fold models match the fit
artifact's receipts; Q2 the cross-fitted RT within reproduces the fit artifact (lv_dev hit
0.1913, vm_dev hit 0.4021, lv_dev pit 0.1442, vm_dev pit 0.3853) and the served-weight pitcher
within reproduces the re-read (0.2198); Q3 no reserved fold; Q4 the live board reproduces (u_c to
5e-7, map A to the served one-decimal grade within 0.05 on all 1,055 hitters and 941 pitchers).
Rows as section 3; every pitcher row has a usage role and an X3 role path.

PRIMARY, delta MSE against the incumbent a (frame-standardized; positive: the candidate is
closer), pooled over both frames and sides, player-clustered CI95, B 2000:

| candidate | delta MSE | CI95 | lv_dev | vm_dev | hitters | pitchers | delta ECE (CI95) |
|---|---|---|---|---|---|---|---|
| b (side) | -0.0239 | -0.0386 to -0.0097 | -0.0117 | -0.0658 | -0.0361 | -0.0113 | -0.0086 (-0.0284 to +0.0149) |
| c (side x usage role) | -0.0231 | -0.0385 to -0.0087 | -0.0105 | -0.0667 | -0.0361 | -0.0098 | -0.0072 (-0.0289 to +0.0137) |
| c_x3 (X3 role path, sensitivity) | -0.0300 | -0.0450 to -0.0162 | -0.0214 | -0.0596 | -0.0361 | -0.0238 | -0.0178 (-0.0381 to +0.0063) |

The role over the side, on the pitcher rows: c minus b +0.0015 (CI95 -0.0053 to +0.0082;
lv_dev +0.0026, vm_dev -0.0018); c_x3 minus b -0.0124 (-0.0254 to +0.0019).

Comparators: the side-permuted b's delta MSE against a has mean -0.0142 and 95th percentile
+0.0003 over 200 draws, so the real side labels make the map worse than random side labels do
(-0.0239 against -0.0142); the role-permuted c's delta against b on pitchers has 95th percentile
+0.0097 (c reads +0.0015). Pooled-curve instrument: b -0.0300 (CI95 -0.0488 to -0.0122), c
-0.0282 (-0.0460 to -0.0112), c minus b +0.0017. Rank guard: b moves no within statistic (0 on
every side and frame, as built); c lowers the pitcher within by 0.0043 pooled (CI95 -0.0159 to
+0.0072; lv_dev -0.0054, vm_dev -0.0007), past the -0.002 guard. Calibration slope of the label on
the implied value (1 is calibrated): a hitters 0.81 (CI95 0.64 to 1.00), pitchers 0.79 (0.60 to
1.05); b hitters 0.69 (0.55 to 0.84), pitchers 0.80. The side map spreads the hitters' implied
value further when it is already wider than the label supports.

Planted recovery (K 100, B 500): SIDE (hitters x1.15, pitchers x0.85) POWER_b 0.02, SIZE_b 0.00;
ROLE (relievers x0.75) POWER_c 0.02, SIZE_c 0.00. On these frames a side or role effect of the
planted size moves the frame-standardized squared error by about 0.004, less than what fitting
two isotonic curves out of fold costs (about 0.005 to 0.014), so the registered statistic cannot
resolve an effect of this size.

Reported, deciding nothing (section 6): realized over implied value under the incumbent,
player-clustered CI95, B 2000.

| rows | pooled | lv_dev | vm_dev |
|---|---|---|---|
| hitters | 1.03 (0.88 to 1.19) | 1.11 (0.86 to 1.39) | 1.00 (0.85 to 1.14) |
| pitchers | 0.96 (0.81 to 1.13) | 0.85 (0.66 to 1.06) | 1.01 (0.84 to 1.20) |
| pitchers over hitters | 0.93 (0.74 to 1.17) | 0.77 (0.54 to 1.07) | 1.01 (0.80 to 1.27) |
| top tenth: hitters | 0.95 (0.72 to 1.19) | 1.27 (0.90 to 1.68) | 0.80 (0.59 to 1.03) |
| top tenth: pitchers | 0.80 (0.64 to 1.00) | 0.72 (0.50 to 0.97) | 0.85 (0.65 to 1.09) |
| top tenth: pitchers over hitters | 0.84 (0.61 to 1.20) | 0.57 (0.35 to 0.88) | 1.06 (0.73 to 1.60) |
| below the top tenth: pitchers over hitters | 0.98 (0.76 to 1.28) | 0.94 (0.63 to 1.46) | 1.01 (0.77 to 1.34) |
| STARTER over hitters (1,168 rows) | 0.88 (0.69 to 1.11) | 0.78 (0.54 to 1.10) | 0.93 (0.74 to 1.17) |
| SHORT-START over STARTER (119) | 1.08 (0.57 to 1.88) | 0.90 (0.37 to 1.59) | 1.41 (0.43 to 5.03) |
| RELIEF over STARTER (395) | 0.84 (0.43 to 1.37) | 0.53 (0.20 to 0.97) | 1.40 (0.59 to 2.67) |
| OTHER (FEW, NO-LINE) over STARTER (139) | 2.41 (1.28 to 3.42) | 1.95 (1.00 to 3.08) | 3.08 (1.00 to 4.67) |
| X3 STARTER path over hitters (635) | 0.86 (0.66 to 1.11) | 0.79 (0.54 to 1.12) | 0.89 (0.67 to 1.18) |
| X3 RELIEF path over hitters (1,186) | 1.04 (0.78 to 1.36) | 0.73 (0.46 to 1.09) | 1.22 (0.90 to 1.64) |

The live-board effect of the production maps (decides nothing): under b the joint top 100 by
grade would hold 13 pitchers instead of 31; the top 50 hitters would rise 1.78 grades on average
and the top 50 pitchers fall 1.25; under c relievers would fall 0.91 and short starters 1.16 on
average, 30 pitchers moving 3 grades or more. The top of each map rests on a few rows: the
highest pitcher block lifts Seth Hernandez from 59.0 to 67.2 and the highest hitter block lifts
Jesus Made from 61.5 to 67.5, while the pitcher at the side's 98th percentile (49.0) maps to
46.9. Those end blocks are why the maps lose out of fold.

## 12. The verdict

Nothing passes; nothing is built, no flag is added and no served number moves.
`SIDE_ROLE_CALIBRATION_ON` stays False and is read by nothing.

- b FAILS (B1, B2, B3, B5 and B6 fail; B4 and B7 hold) and c FAILS (C1 to C7 fail; C8 holds).
  The registered wording is UNRESOLVED for both (planted power 0.02): on these frames squared
  error cannot resolve a side or role effect of the planted size. The point estimates go further
  than a tie: both isotonic maps are worse than no mapping, with the whole CI95 below 0, on both
  instruments, and the side map is worse than its own side-permuted twin on average.
- Q-SIDE, reported: pooled over both frames pitchers realize 0.93 of what hitters realize at the
  same implied value (CI95 0.74 to 1.17), not resolved. The gap sits in the top tenth of each
  side's grades on the bust-inclusive list-vintage frame: there pitchers realize 0.57 of the
  hitters' share (CI95 0.35 to 0.88), and pooled over both frames the top tenth of pitchers
  realize 0.80 of their implied value (0.64 to 0.997). Among debuted players (vm_dev) the sides
  match (1.01). So the inflation the owner sees is real at the top of the pitcher board and runs
  through reaching the majors, not through value after a debut.
- Q-ROLE, reported: pitchers used in relief at the read realize 0.53 of what starters do on the
  list-vintage frame (CI95 0.20 to 0.97) and 0.84 pooled (0.43 to 1.37); among debuted pitchers
  the 73 relief rows point the other way (1.40, 0.59 to 2.67). Short starters match starters.
  Pitchers with no usage reading (FEW, NO-LINE) out-realize starters (2.41, 1.28 to 3.42).
- Why the calibration fails while the ratios show a gap: the isotonic map moves every grade by a
  curve fitted on a few hundred rows per side, and its end blocks rest on a handful of players, so
  out of fold it adds more error than the side effect removes. A smaller object (one scalar per
  side and role, or a tilt above a within-side quantile) is not tested here; it would need its
  own registration with a power read on the ratio statistic first.
