# eFV output map test (EFV_OUTPUT_MAP_TEST): registration

Registration status: REGISTERED

Registered 2026-10-16, committed ALONE, before the code of this task exists and before any
number of its read is computed. Owner decision EW3-35 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
2026-10-16): eFV stays an expected value; the owner queued this test of the map that turns the
model's order into a grade ("fix the top-of-board mapping"), with Sebastian Walcott as the case.
The run appends section 11 (the numbers) and section 12 (the verdict). No em-dashes.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019, vm_dev
debut cohorts 2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut
cohorts 2025 and later) is built or scored; `backtest.run_backtest` is never called; nothing is
grouped, counted or averaged by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`): the groups
are side, frame and fold (list year or debut year), and no grade-to-WAR table is fitted (the
instruments below are committed artifacts read as they stand). No model is refitted: every
head, slope, weight and the order index stay as served (`data/efv5_refit_weights.json`,
variant RT; hitters w_skill 0.2965, pitchers w_skill 1.0, w_time 0 on both sides). Only the
map from the order index to the grade is under test.

## 1. What is known before this registration

- The served map (`efv_v2_model.output_map`, DS-07): inside each (side, list year) group the
  row at order rank k takes the k-th smallest of the group's own consensus values, ties
  averaged. The grade multiset of a group IS its consensus multiset.
- Sebastian Walcott on the served board (`data/xfv.json`, generated 2026-10-16): consensus 55.6,
  hitter consensus rank 7 of 1,055, u_c 0.993839, e_skill -0.004107, so his order index is
  0.992621 (a shift of -0.12 percentile points at the hitter weight 0.2965). His order rank is
  33 and his served eFV 49.3 (-6.3). Hitters below him moved up by up to about 2.5 percentile
  points on the hit tool term, and consensus percentiles sit about 0.1 point apart per rank at
  the top, so 26 ranks are crossed by rows whose own shifts are small.
- The pitcher audit (scratchpad `efv_pit_audit/AUDIT.md`, 2026-10-16) section 2(b): the average
  gain of any top-K list equals (mean of the K highest consensus values) minus (mean consensus
  of the K rows selected), which is never negative; pitcher shift SD 0.238 on the live board,
  hitters 0.049; top-decile pitcher calls realize 0.40 to 1.05 of their implied lift (wide CIs).
- The development reads score the order index by within (side, year) Spearman, a rank
  statistic that cannot see the grade magnitude the map produces.

Nothing about this read's outcome has been computed.

## 2. The maps

Notation, per group G (one side and one fold year on a development frame; one side and the
list year on the live board): consensus values c_i (the values the served map draws from: the
fold's test-row `fv`, the live board's `consensus_fv_raw`), u_i = `efv_v2_model.within_pct`(c),
order o_i (the served order index), shift s_i = o_i - u_i. Sorted values v_(1) <= ... <= v_(n)
sit at positions t_r = r / n.

The group quantile function, smoothed: v~_r = mean(v_(r-k_r) ... v_(r+k_r)) with
k_r = min(k, r - 1, n - r) and k = max(1, round(H_SMOOTH x n)), then a running maximum so v~ is
nondecreasing. Q~(u) = linear interpolation of (t_r, v~_r), held at v~_1 below t_1 and at v~_n
above t_n. Q0 is the same with k = 0 (no smoothing; Q0(u_i) = c_i exactly, ties included).
The local slope D(u) = (Q~(min(u + H_SLOPE, t_n)) - Q~(max(u - H_SLOPE, t_1))) / (min(u +
H_SLOPE, t_n) - max(u - H_SLOPE, t_1)), in grade points per unit of percentile.

| id | map | role |
|---|---|---|
| A | `output_map(o, G, c)` | the incumbent (served) |
| B | g_i = clip(c_i + s_i x D(u_i), min c, max c) | candidate (b): the shift on the grade scale through the local slope |
| C | `output_map(u + lambda x s, G, c)`, lambda_i = min(1, D_med / D(u_i)) (1 where D(u_i) = 0), D_med = the median of D(u_i) over the group's rows with D > 0 | candidate (c): the density-damped rank map |
| D | g_i = Q~(o_i) | candidate (d): the monotone smoothed quantile map |
| D0 | g_i = Q0(o_i) | decomposition of D (no smoothing); never prepared |
| Z | g_i = c_i | the zero comparator (consensus itself) |
| N_X | `output_map(u + m_X x s, G, c)`, m_X in [0, 1] chosen per side so that the mean of abs(g - c) over the side's development test rows equals candidate X's | the null comparator of X: a rank map that moves as little as X |

Constants: H_SMOOTH = 0.01, H_SLOPE = 0.02. m_X is found by bisection (60 steps) on the test
rows, outcome-free; when X moves more than A, m_X = 1 (N_X = A) and the receipt says so.
None of these invents a grade outside the group's consensus range [min c, max c]. A fitted
grade-units model (the alternative the task names under (b)) is NOT registered: fitting grade
on outcome would be a refit on the label by grade, which the anchor gate and the do-not-reopen
list rule out.

The rank guard reads each map's own ordering: the within statistic of map X is computed on the
lexicographic rank of (g_X, o) inside the group, so a tie in g is broken by the served order
(for A this is the order index itself, the registered statistic; D's grade is monotone in o, so
D's within equals A's by construction).

## 3. Frames, rows and parity

Heads, test rows and scored rows: the re-fit's own forward-chained RT fold builds (the
EFV_FIX_B_REFIT cache: `build1`, `packs_RT`, `phase0`), as `efv5_pit_sign.py` and
`efv5_pit_rebase.py` read them. Orders at the SERVED weights: o = u + w_skill x e_skill inside
(frame, side, fold) over the fold's test rows (u over the test rows, as `predict_v2`). Each map
runs on the fold's test rows (the group); the statistics read the fold's scored rows. The run
refuses before reading any outcome when:

- Q1: a cached fold model's nonzero skill list differs from the fit artifact's fold receipt;
- Q2: the within Spearman at the cross-fitted weights does not reproduce the fit artifact's RT
  rater on each frame and side (`frames.<fid>.per_side.<side>.raters.efv_v5_rt.within`, to
  0.0001), or the pitcher within at the served weights does not reproduce
  `data/_labs/efv5/efv5_refit_pit_reread.json` `read.both.raters.rr_served` (0.2198, to 0.0001);
- Q3: any fold year is reserved (`efv_vintage_frame.RESERVED_LV`, debut years 2025 and later);
- Q4 (live, outcome-free): `within_pct` of the live `consensus_fv_raw` does not reproduce the
  served `efv_v2.u_c` to 1e-6, or map A on the served order index does not reproduce the served
  `xfv_grade` to 0.05 (one-decimal rounding), on every row of both sides.

Reported receipts: the number of scored rows whose test-row `fv` differs from the scored
consensus grade (the read uses the test-row value, the map's own value set).

## 4. The magnitude estimand

Instrument (PRIMARY): the per-side expected first-six-season total WAR curve
`data/fv_outcome_curves.json` `curves.<side>.war.value` at its knots, linear between knots and
flat beyond the end knots, T_side(g). Sensitivity instruments: the pooled curve the served basis
inverts (`data/fv_outcome_curves_pooled.json` `curve.value`) and the Clemens 2026 per-side table
(`data/fv_outcome_curves.json` `conversions.clemens_2026.table_<side>`, with (20, 0.0) added
below its first row, flat above 70).

The frames' labels are not six-season totals (lv_dev: fWAR over the first three seasons within
the window, 0 without a debut; vm_dev: career fWAR resolved through 2026). Each group G's implied
value is put on its own label's scale by one scalar from the zero comparator:
kappa_G = (sum of y over G's scored rows) / (sum of T(c) over the same rows), one number per
(frame, side, fold) and never by grade. The implied value of map X on row i is
v_X,i = kappa_G x T(g_X,i); the same kappa_G serves every map.

Statistics on the scored rows, per side (pooled over both frames, rows weighted equally) and
per frame:

1. PRIMARY: delta MSE(X) = mean((y - v_A)^2) - mean((y - v_X)^2) (positive: X is closer than
   the incumbent), paired player-clustered CI95 (resample players, keep every row of a drawn
   player; B 2000, seed 20261016) and the one-sided bootstrap p = share of draws at or below 0.
   Squared error because eFV is an expected value (EW3-35) and the mean is what squared error
   rewards; absolute error rewards the median, which on a zero-inflated WAR label rewards
   shrinking every grade.
2. delta MAE(X) = mean(abs(y - v_A)) - mean(abs(y - v_X)), the same interval.
3. Calibration slope: OLS of y on v_X with an intercept, with the same bootstrap CI95;
   reported, it does not decide.
4. The rank guard: within (side, year) Spearman of map X's ordering minus A's
   (`tools/efv_v3_backtest.paired`, statistic within, B 2000, the backtest seed), each frame and
   row-weighted pooled.
5. The comparators: delta MSE of X against N_X (N_X's MSE minus X's) and of A and X against Z,
   with intervals.

## 5. The planted check

On each side's scored rows, for truth T_true in {A, X}: y*_i = v_T_true,i + (y_pi(i) - mean_G y),
pi a random permutation inside the row's group G (noise with the label's own spread; no
residual is formed). K_PLANT 100 draws (seed 20261016 + draw), each read with the primary
instrument at B_PLANT 1000. POWER(X) = share of draws with truth X whose delta MSE(X) CI95 lower
bound is above 0; SIZE(X) = share of draws with truth A whose lower bound is above 0.

## 6. The ship rule (per side, per candidate B, C, D)

X passes on a side when all hold:

1. delta MSE(X) pooled over both frames has CI95 lower bound above 0, and its one-sided p
   survives Holm's step-down at 0.05 over the six (candidate, side) tests;
2. delta MSE(X) is at or above 0 on each frame;
3. delta MAE(X) pooled is at or above 0;
4. the rank guard: X minus A within Spearman is at or above -0.002 pooled and on each frame;
5. the null comparator: delta MSE(X) against N_X is above 0 pooled (X beats a rank map that
   moves as little);
6. delta MSE(X) pooled is above 0 under both sensitivity instruments;
7. SIZE(X) is at most 0.10.

When more than one candidate passes a side, the one with the largest pooled delta MSE is
prepared for that side. A failure is worded by POWER: with POWER at or above 0.80 a failure is
a NULL (a map difference of the planted size would have been resolved); below 0.80 it is
UNRESOLVED (the frames cannot resolve a difference of this size) and says nothing in favour of
the incumbent beyond that.

## 7. What ships under each outcome

- Nothing passes: nothing is built. The artifact, sections 11 and 12 here and one ledger line in
  `docs/efv-v2/STATUS.md` are the whole result; no served number moves.
- A candidate passes a side: it is built DARK. `efv_v2_model.OUTPUT_MAP_ARM` (default
  `{"hit": "A", "pit": "A"}`, byte identical) selects the map per side inside `predict_v2`; the
  prepared map is a function beside `output_map`; tests pin the default and the map's
  properties. `OWNER_QUESTION.md` in the task's output directory carries the board effect. The
  owner flips it; this task does not.

## 8. The board effect (outcome-free; computed for every candidate)

On the live board (`data/xfv.json` efv_v2 rows and the live matrices' `consensus_fv_raw`), per
side and candidate: Sebastian Walcott (A, X, consensus, ranks); the top 50 by consensus and the
top 50 by X (mean grade under A, X and consensus, mean X minus A); the whole side's mean
abs(eFV - consensus), mean (eFV - consensus), rows moving 3 or more grades against A, the
largest moves up and down, and the rows tied at the group's top value.

## 9. Gate compliance and stop rules

Consensus enters as the within-group percentile and as the value set the grade is drawn from;
the instruments are committed curves evaluated at a grade, never re-fitted; kappa_G is one
scalar per (frame, side, fold). A source scan in the tests pins that the lab names no FV-cell
stratum. If any of Q1 to Q4 fails, no outcome is read and the result is the refusal.

## 10. Defaults applied (named for the orchestrator)

- D-1: the served weights (not the cross-fitted ones) build the orders; the map is what is
  tested, and the served weights are what the board maps.
- D-2: the per-side outcome curve is the primary instrument; the pooled curve and the Clemens
  table are sensitivities.
- D-3: kappa_G per (frame, side, fold) puts the six-season implied value on each frame's label
  scale.
- D-4: squared error is primary (eFV is an expected value); MAE must not get worse.
- D-5: verdicts per side; the map may change on one side only.
- D-6: constants H_SMOOTH 0.01, H_SLOPE 0.02, B 2000, K_PLANT 100, B_PLANT 1000, seed 20261016,
  guard 0.002, SIZE at most 0.10, POWER 0.80, Holm at 0.05 over six tests.
