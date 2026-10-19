# eFV upside and volatility drivers (EFV_UPSIDE_VOLATILITY_DRIVERS): registration

Registration status: REGISTERED 2026-10-16; READ 2026-10-19 (sections 11 and 12)

Registered 2026-10-16, committed ALONE (with its dated addendum to the EFV_X3 candidate list,
`docs/efv-v2/EFV_X3_CANDIDATE_LIST.md`), before the code of this task exists and before any
number of its read is computed. Owner decision EW3-35 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
2026-10-16): eFV stays an expected value; injury history is already a driver (the IL family);
pitcher attrition is priced by the per-side outcome tables, so there is no blanket pitcher
penalty; upside and volatility enter eFV only if they predict the mean or the full outcome
distribution. The owner queued this task to find out which markers do, scored on both, and to
hand the ones that pass to EFV_X3_POOLED_MODEL. The run appends section 11 (the numbers) and
section 12 (the verdict). No em-dashes.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019,
vm_dev debut cohorts 2017 to 2023, as `tools/efv_v2_model_class_screen.build_inputs` scores
them); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and later) is
built or scored; `backtest.run_backtest` is never called; nothing is grouped, counted or averaged
by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`): the groups are frame, side, fold year,
hitter position group and pitcher role, and the outcome classes below are cut on the outcome,
never on a grade. No model is refitted and nothing served moves: this read is DESCRIPTIVE, its
artifact is role development and adjudicates nothing, and its only output is the hand-off list.

## 1. What is known before this registration

- The served pitcher head carries five IL keys (stints, days, 60-day, open, recurrent;
  `scr_w2i_*`), all free-signed; EFV_PIT_SIGN_STABILITY found the stint, day, open and
  recurrence keys flip sign across folds and the 60-day key hold +. The served hitter head
  carries no IL key and no body, speed or athleticism key (it collapsed to the hit tool,
  pitcher audit section 2(b)).
- EFV_X1_MLE_TRANSLATION read `age_rel_level` (built from the translated lines) one feature at
  a time against consensus: hitters lv_dev -0.0103, vm_dev -0.0046; pitchers -0.0026, +0.0010;
  not flagged. That read scored the mean only.
- The pitcher audit (scratchpad `efv_pit_audit/AUDIT.md`, 2026-10-16): the strikeout tail is
  under-credited out of fold (slope ratio above p90 3.88), the excess concentrates in young
  low-level high-K starters, and the 60-day IL column drifted on the live board. None of it
  reads a body, speed, velocity, workload or surgery marker.
- The development reads of this program score within (side, year) Spearman, a rank statistic
  that cannot see whether a marker moves the tails of the outcome distribution and not its
  center. This task adds two proper scores for that.

Nothing about this read's outcome has been computed. Marker coverage has not been counted.

## 2. Rows, labels and as-of dates

Rows: the scored rows of both development frames, per side, as `efv_x1_translate.build_rows`
returns them (lv_dev hitters and pitchers by list vintage, vm_dev by debut cohort), each with
its outcome-blind MLBAM id, its frame label and its year.

Labels:

- FRAME LABEL (the mean read): the frame's own registered label, lv_dev W3 (fWAR over the
  first three MLB seasons, 0 without a debut within three seasons of V), vm_dev career WAR to
  date (the screen's scored outcome).
- L6 (the distribution read): six-season fWAR from the debut, FULLY OBSERVED rows only. lv_dev:
  `efv_labels.labels_for` `l6` where `l6_censored` is False (a resolved never-MLB row reads 0;
  a censored-never row and a censored six-season window are excluded). vm_dev: the matrix row's
  `target_resolved` where `censored` is False. Rows without an L6 enter the mean read only.
- Outcome classes on L6, cut on the outcome only: BUST is L6 at or below 0; STAR is L6 above
  STAR_WAR = 10; MID is everything between.

As-of dates, per row, each the earliest the fact could be known:

- MiLB window: the seasons T, T - 1, T - 2 (2020 skipped), T = `efv_x1_translate.top_season`
  of the row's year and MiLB cutoff (lv_dev V-01-01, vm_dev the pinned preseason as-of); the
  affiliated season lines (sports 11 to 16) of `milb_history.season_splits`, cache only.
- Scouting as-of A: the row's consensus read date (the frame row's `asof_date` on lv_dev, the
  pinned as-of on vm_dev). FanGraphs board facts are read off the latest FanGraphs snapshot in
  `prospects.db` dated on or before A and at most LOOKBACK_DAYS = 730 days before it;
  consensus tool grades off the latest universe point (`tools_consensus`) dated on or before A
  within the same lookback; height and weight fall back to the latest dated listing of
  `data/_frozen/arch_bio_panel.json` on or before A.
- Injury cutoff C: `efv_w2_il_backfill.lv_cutoff(V)` on lv_dev and `vm_cutoff(raw, year)` on
  vm_dev (the served IL definitions); a surgery counts when its date is strictly before C.

## 3. The markers (pre-registered as EFV_X3 candidates)

UPSIDE family (U). Body frame and projectability, speed, athleticism, age for level and
statistical tails:

| id | side | marker | definition |
|---|---|---|---|
| U01 | both | `height_in` | height in inches (FanGraphs board, else the bio panel) |
| U02 | both | `weight_lb` | weight in pounds (same source) |
| U03 | both | `frame_resid` | weight minus its OLS prediction from height and age at A, fitted outcome-free on the cell's rows of the same (frame, side, year) group; negative is lighter than peers of that height and age (room to fill) |
| U04 | both | `fg_frame` | FanGraphs frame (-2 to 2) |
| U05 | both | `fg_athl` | FanGraphs athleticism (-2 to 2) |
| U06 | both | `fg_levers` | FanGraphs levers (Short -1, Med 0, Long 1) |
| U07 | hit | `run_grade` | consensus run (speed) tool grade at A |
| U08 | hit | `sb_rate` | stolen bases over (singles + walks + hit by pitch), window pooled, at least 100 PA |
| U09 | hit | `triple_rate` | triples over balls in play (AB - SO - HR + SF), window pooled, at least 100 PA |
| U10 | hit | `athl_comp` | mean of the within-group z of the consensus run, field and arm grades at A and FanGraphs athleticism, at least two present |
| U11 | both | `age_rel_level` | age in season T minus the exposure-weighted mean age of every affiliated line at the level of the player's largest exposure that season |
| U12 | hit | `iso_peak_z` | the best window season's ISO z against the qualified lines (100 PA) of the same level and season, read at the player's largest-exposure level that season (100 PA there) |
| U13 | hit | `contact_peak_z` | the same for minus K% (the lowest strikeout rate) |
| U14 | hit | `max_ev` | FanGraphs max exit velocity where tracked |
| U15 | pit | `k_peak_z` | the best window season's K% z against the qualified lines (100 BF) of the same level and season |
| U16 | pit | `bb_best_z` | the same for minus BB% |
| U17 | pit | `fb_tops` | FanGraphs fastball top velocity |
| U18 | pit | `fb_sits` | FanGraphs fastball sitting velocity, the midpoint of the printed range |

VOLATILITY family (V). Velocity change, workload, surgery, IL history, delivery:

| id | side | marker | definition |
|---|---|---|---|
| V01 | pit | `velo_change` | `fb_sits` on the latest FanGraphs board at A minus `fb_sits` on the latest FanGraphs board dated at least PRIOR_GAP_DAYS = 300 days before it (and within the lookback) |
| V02 | pit | `tops_change` | the same for `fb_tops` |
| V03 | pit | `workload_spike` | innings in season T (every affiliated line) minus the most innings in the two earlier window seasons; missing without both |
| V04 | pit | `workload_spike_flag` | 1 when `workload_spike` is at least SPIKE_IP = 30, else 0 (missing with it) |
| V05 | both | `surgery_count` | Tommy John and UCL procedures in `data/tj_surgery.json` for the MLBAM id dated before C (0 with an id and none listed) |
| V06 | both | `il_stints` | `il_stints_pre` as of C (`efv_w2_il_backfill.asof`) |
| V07 | both | `il_days` | log1p of `il_days_pre` |
| V08 | both | `il_recurrent` | `il_recurrent_pre` (two or more stints: repeated IL stints) |
| V09 | both | `il_60day` | `il_60day_pre` |
| V10 | pit | `fg_delivery` | FanGraphs delivery (-2 to 2), the delivery and effort marker where available |

A marker the sources do not carry for a cell's rows is not invented: it reads missing, and
the minimum cell (section 6) decides whether it is scored. A marker with no source at all
(none expected beyond the coverage the sources have) is recorded as absent.

## 4. The mean read (the expected outcome)

Per cell (marker, side, group) on the cell's scored rows: inside each (frame, side, year)
group, u_c is the consensus percentile (average ranks), u_y the frame label's percentile, z
the marker z-scored over the group's rows that carry it (0 where missing) and m its missing
indicator. Per frame, a leave-one-year-out ridge (alpha 1.0, intercept free) of u_y on
(u_c, z, m) predicts each held-out year (the `efv_x1_translate.loyo_score` design). The
statistic is `efv_v2_stat.paired_delta(statistic="within")`: the size-weighted within
(frame, side, year) Spearman of the score minus consensus's, groups of at least 20 rows,
E_cond paired player-clustered bootstrap, B 2000, seed 20261016. One-sided p = the share of
bootstrap draws at or below 0 (floored at 1 / (B + 1)).

## 5. The distribution read (the full outcome)

On the cell's rows with an L6 label. Per frame and held-out year, the predictive CDF of L6 is
fitted on the other years of the same frame by threshold logistic regression: at each
threshold t_j of the grid G = (-1, 0, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 22, 26, 30)
WAR, P(L6 <= t_j) = logistic(x b_j), ridge penalty LAMBDA_LOGIT = 1.0 on the slopes. The
baseline reads x = (1, u_c), the candidate x = (1, u_c, z, m), with u_c, z and m built inside
each (frame, side, year) group on the L6 rows of the cell. The fitted CDF is made monotone in t
by a running maximum; a threshold that every training row sits on one side of takes
(count + 0.5) / (n + 1).

Scores, per row (lower is better):

1. CRPS: the threshold-weighted CRPS on G, sum_j w_j (F(t_j) - 1{L6 <= t_j})^2, w_j the
   trapezoid weights of the grid (half gaps at its ends). A proper score of the distribution
   on [-1, 30] WAR.
2. LOG LOSS on the three outcome classes: P(BUST) = F(0), P(STAR) = 1 - F(10),
   P(MID) = F(10) - F(0), each floored at 1e-6; minus the log of the probability of the row's
   class.

delta = mean over rows of (baseline score minus candidate score), positive when the marker
helps; CI95 and one-sided p by player-clustered bootstrap of the paired row differences,
B 2000, seed 20261016.

## 6. Cells, families and the comparators

Groups: hitters all, C, SS, CF, IF (2B and 3B), COF (LF, RF, generic OF), 1B/DH from the
listing position (`efv5_atlas.POS_GROUP`; lv_dev the frame row's position, vm_dev the matrix
row's); pitchers all, SP and RP by the EFV3_C05 rule on season T (games started over games at
or above 0.5 is SP; no season-T line is in "all" only). Frames are pooled inside a cell (the
within statistic keeps its (frame, side, year) groups; the distribution scores average rows).

Minimum cell, declared before any read: at least MIN_ROWS = 150 rows, at least MIN_MARKER = 40
rows carrying the marker; for the distribution read also at least 150 L6 rows, 40 of them
carrying the marker, and at least MIN_CLASS = 15 STAR rows and 15 BUST rows. A cell below it is
listed as thin and not scored.

- ZERO COMPARATOR: consensus alone (the baseline of every delta: a marker that carries
  nothing scores 0 in expectation, minus the noise a fitted slope costs).
- NULL COMPARATOR: K_NULL = 20 permuted twins of the marker (its values, missing included,
  shuffled across the cell's rows inside each (frame, side, year) group, seed 20261017 +
  draw) through the same read, point estimates only; null95 = the 95th percentile of the twin
  deltas, per cell and score.
- BH q: Benjamini-Hochberg within each (family, score) over every scored cell of the family
  (all sides and groups), on the one-sided p.

## 7. The planted recovery check

Per side, on the "all" rows of both frames, K_PLANT = 40 draws (seed 20261016 + draw) of each
synthetic marker, full coverage, read by the mean and distribution reads with B_PLANT = 500:

- PM (mean plant): x = RHO_M e + sqrt(1 - RHO_M^2) eps, e the normal score of the frame label's
  within-group percentile, RHO_M = 0.20, eps standard normal.
- PT (tail plant): x = DELTA_T 1{L6 > STAR_WAR} + eps on L6 rows, eps elsewhere, DELTA_T = 1.0.
- P0 (no information): x = eps.

POWER(plant, score) = the share of draws with CI95 lower bound above 0 and delta above the 95th
percentile of the P0 draws' deltas (the planted null); SIZE(score) = the share of P0 draws with
CI95 lower bound above 0. The registered expectation (not a rule): PM is recovered by the mean
read; PT by the distribution reads.

## 8. The rule (descriptive; it ships nothing)

A (cell, score) PASSES when all hold: delta above 0; CI95 lower bound above 0; BH q at or below
CANDIDATE_Q = 0.10; delta above its null95; and on each frame that has at least MIN_MARKER
rows carrying the marker, the frame's own point delta for that score is at or above 0.

Each scored (marker, side, group) is classified:

- MEAN: the mean read passes and neither distribution score passes;
- BOTH: the mean read and at least one distribution score pass;
- TAILS ONLY: a distribution score passes and the mean read does not (the marker moves the
  shape of the outcome distribution, its bust or star mass, more than its center);
- NONE: nothing passes. A NONE on a side whose planted POWER for that score is at or above 0.80
  is a NULL; below 0.80 it is UNRESOLVED (the frames cannot resolve an effect of the planted
  size) and says nothing in favour of leaving the marker out beyond that.

Every passing (marker, side, group, score) is handed to EFV_X3_POOLED_MODEL by a dated line in
`docs/efv-v2/EFV_X3_CANDIDATE_LIST.md`, with this condition attached: X3's registration scores
the passing markers on the distributional score that passed them (CRPS on L6 and the class log
loss), not only on within Spearman. Every other marker stays available to X3, unflagged. No
outcome of this read changes a served number, a flag or a ledger row on the progress chart.

## 9. Gate compliance and stop rules

Consensus enters as the within-group percentile only. The outcome classes and the CRPS grid
are cut on WAR, never on a grade. The lab reads no realized-WAR mean, residual or count by any
grade level; a source scan in the tests pins that it names no FV-cell stratum. The run refuses,
before any outcome is read, when a fold year is reserved (`efv_vintage_frame.RESERVED_LV`,
debut years 2025 and later) or when an as-of input is dated after its row's as-of date (the
lab asserts each read: a MiLB season that ended after the MiLB cutoff, a board or point after A,
a surgery or IL fact on or after C).

## 10. Defaults applied (named for the orchestrator)

- D-1: L6 on fully observed rows only (no censored six-season window is projected).
- D-2: STAR above 10 six-season WAR, BUST at or below 0; the CRPS grid of section 5.
- D-3: scouting facts read at the consensus read date with a 730-day lookback; the velocity
  change compares boards at least 300 days apart.
- D-4: frames pooled inside a cell; BH within (family, score) over all sides and groups.
- D-5: constants MIN_ROWS 150, MIN_MARKER 40, MIN_CLASS 15, K_NULL 20, K_PLANT 40, B 2000,
  B_PLANT 500, RHO_M 0.20, DELTA_T 1.0, SPIKE_IP 30, CANDIDATE_Q 0.10, seeds 20261016 and
  20261017.
- D-6: EFV_X3_POOLED_MODEL has no registration document yet, so its candidate list starts as
  `docs/efv-v2/EFV_X3_CANDIDATE_LIST.md` with this task's dated addendum; earlier hand-offs
  stay where their own documents record them and are pointed to there.

## 11. The read (2026-10-19; `python efv_upside_volatility.py --run`)

Artifact: `data/_labs/efv5/efv_upside_volatility.json` (role development, descriptive,
adjudicates false, served false; registration commit 54da7049, module sha256 9f9c2234, label
fwar resolved through 2026). Elapsed 379 s. Rows: hitters 1,871 (lv_dev 1,465 in 2017 to 2019,
vm_dev 406 in 2017 to 2023), pitchers 1,821 (1,397 and 424); L6 rows hitters 1,432 (127 STAR,
945 BUST), pitchers 1,474 (46 STAR, 936 BUST). No reserved fold was built.

Coverage (rows carrying the marker, lv_dev / vm_dev): hitters height and weight 1,216 / 400;
U03 1,137 / 399; run grade and the athleticism composite 1,400 / 406; stolen-base and triple
rates 1,324 / 404; ISO and contact peaks 1,320 / 404; age for level 1,356 / 405; IL and surgery
1,369 / 406; FanGraphs frame, athleticism, levers and max EV 0 on lv_dev (the FanGraphs boards
in `prospects.db` start after the lv_dev read dates) and 147 to 215 on vm_dev. Pitchers: height
and weight 1,120 / 422; U03 1,049 / 418; age for level 1,309 / 420; K and BB peaks 1,179 / 406;
fastball tops and sits 366 / 360; velocity changes 0 / 245; workload spike 1,035 / 378; IL and
surgery 1,341 / 424; FanGraphs frame, athleticism, levers and delivery 0 / 129 to 219.

Cells: 196 (hitters 19 markers x 7 groups, pitchers 21 x 3). Scored: mean 160, CRPS and log
loss 115 each; 36 cells are thin on every read (every CF cell, 141 rows; the FanGraphs-scale
and max EV cells of the C, SS and 1B/DH groups; five RP cells) and 81 are thin on the
distribution read (also every RP cell, 6 STAR rows, and the cells short of 40 marker rows or 15
STAR rows).

Planted recovery (K 40, B 500, side "all" rows, full coverage):

| side | score | null95 (P0) | size | power PM | power PT |
|---|---|---|---|---|---|
| hit | mean | -0.0015 | 0.00 | 0.93 | 0.00 |
| hit | CRPS | 0.0029 | 0.00 | 0.43 | 1.00 |
| hit | log loss | 0.0006 | 0.00 | 0.35 | 1.00 |
| pit | mean | 0.0021 | 0.00 | 0.95 | 0.00 |
| pit | CRPS | 0.0009 | 0.00 | 0.40 | 0.30 |
| pit | log loss | 0.0007 | 0.00 | 0.45 | 0.88 |

As registered: the mean plant is recovered by the mean read and the tail plant by the
distribution reads on hitters; on pitchers the tail plant reaches 0.88 on the log loss and only
0.30 on CRPS (46 STAR rows carry the plant).

The side "all" reads (delta, positive helps; CI95 player-clustered, B 2000):

| side | marker | mean | CRPS | log loss |
|---|---|---|---|---|
| hit | U01 height | -0.0022 (-0.0107, +0.0059) | -0.0054 (-0.0158, +0.0038) | -0.0011 (-0.0059, +0.0040) |
| hit | U02 weight | -0.0112 (-0.0191, -0.0036) | -0.0108 (-0.0191, -0.0028) | -0.0024 (-0.0067, +0.0021) |
| hit | U03 frame residual | -0.0146 (-0.0229, -0.0067) | -0.0001 (-0.0131, +0.0134) | +0.0014 (-0.0053, +0.0082) |
| hit | U07 run grade | -0.0038 (-0.0111, +0.0034) | -0.0016 (-0.0085, +0.0049) | +0.0004 (-0.0044, +0.0052) |
| hit | U08 SB rate | -0.0002 (-0.0166, +0.0165) | -0.0039 (-0.0188, +0.0109) | -0.0037 (-0.0102, +0.0026) |
| hit | U09 triple rate | -0.0037 (-0.0145, +0.0073) | -0.0112 (-0.0215, -0.0019) | -0.0061 (-0.0124, +0.0002) |
| hit | U10 athleticism composite | +0.0012 (-0.0105, +0.0131) | -0.0066 (-0.0151, +0.0016) | +0.0015 (-0.0052, +0.0080) |
| hit | U11 age for level | -0.0093 (-0.0190, -0.0001) | +0.0070 (-0.0159, +0.0325) | -0.0002 (-0.0068, +0.0065) |
| hit | U12 ISO peak | -0.0045 (-0.0171, +0.0077) | -0.0043 (-0.0185, +0.0108) | -0.0017 (-0.0081, +0.0048) |
| hit | U13 contact peak | +0.0012 (-0.0156, +0.0157) | +0.0059 (-0.0237, +0.0340) | +0.0044 (-0.0076, +0.0157) |
| hit | V05 surgeries | -0.0028 (-0.0075, +0.0018) | -0.0048 (-0.0218, +0.0060) | -0.0016 (-0.0090, +0.0034) |
| hit | V06 IL stints | -0.0048 (-0.0104, +0.0006) | -0.0128 (-0.0229, -0.0034) | -0.0016 (-0.0063, +0.0033) |
| hit | V07 IL days | -0.0087 (-0.0143, -0.0033) | -0.0158 (-0.0248, -0.0076) | -0.0032 (-0.0059, -0.0008) |
| hit | V08 repeated IL | -0.0044 (-0.0085, -0.0001) | -0.0057 (-0.0166, +0.0036) | +0.0005 (-0.0047, +0.0057) |
| hit | V09 60-day IL | -0.0012 (-0.0071, +0.0048) | -0.0039 (-0.0119, +0.0020) | -0.0017 (-0.0069, +0.0022) |
| pit | U01 height | -0.0080 (-0.0162, +0.0002) | +0.0002 (-0.0093, +0.0096) | +0.0047 (-0.0013, +0.0107) |
| pit | U02 weight | -0.0052 (-0.0141, +0.0034) | -0.0020 (-0.0080, +0.0042) | +0.0027 (-0.0032, +0.0086) |
| pit | U03 frame residual | -0.0152 (-0.0271, -0.0033) | -0.0057 (-0.0151, +0.0035) | -0.0021 (-0.0073, +0.0029) |
| pit | U11 age for level | -0.0018 (-0.0128, +0.0091) | +0.0104 (+0.0008, +0.0214) | +0.0008 (-0.0054, +0.0072) |
| pit | U15 K peak | -0.0034 (-0.0119, +0.0052) | +0.0049 (-0.0047, +0.0159) | -0.0024 (-0.0070, +0.0027) |
| pit | U16 BB best | +0.0018 (-0.0124, +0.0155) | +0.0020 (-0.0133, +0.0185) | -0.0058 (-0.0130, +0.0017) |
| pit | U17 FB tops | -0.0045 (-0.0082, -0.0012) | +0.0032 (-0.0097, +0.0161) | +0.0011 (-0.0052, +0.0072) |
| pit | U18 FB sits | -0.0037 (-0.0072, -0.0001) | +0.0051 (-0.0078, +0.0176) | +0.0008 (-0.0052, +0.0066) |
| pit | V01 velocity change | -0.0030 (-0.0070, +0.0005) | +0.0035 (-0.0040, +0.0107) | +0.0037 (-0.0015, +0.0091) |
| pit | V03 workload spike | -0.0021 (-0.0191, +0.0145) | +0.0190 (-0.0011, +0.0402) | +0.0075 (-0.0025, +0.0174) |
| pit | V04 spike flag | -0.0102 (-0.0257, +0.0053) | +0.0133 (-0.0040, +0.0320) | +0.0037 (-0.0042, +0.0116) |
| pit | V05 surgeries | -0.0025 (-0.0234, +0.0175) | +0.0112 (-0.0082, +0.0313) | +0.0065 (-0.0041, +0.0174) |
| pit | V06 IL stints | -0.0052 (-0.0149, +0.0030) | +0.0055 (-0.0073, +0.0186) | +0.0016 (-0.0037, +0.0067) |
| pit | V07 IL days | -0.0077 (-0.0165, +0.0007) | +0.0041 (-0.0100, +0.0186) | +0.0008 (-0.0045, +0.0058) |
| pit | V09 60-day IL | -0.0032 (-0.0108, +0.0037) | -0.0028 (-0.0063, +0.0003) | -0.0033 (-0.0091, +0.0010) |

The FanGraphs-scale markers (U04 to U06, U14, V10) and V02 read on vm_dev only, 129 to 244
rows: every point estimate within 0.0076 of 0 and every CI95 spanning 0 or below it. Over all
scored cells: the mean read has no CI95 above 0 (27 below); CRPS has 2 above 0 (17 below); log
loss 1 above 0 (15 below). The mean deltas sit near the null twins' own mean (the cost of a
fitted slope that carries nothing), as the zero comparator expects.

The three closest cells, each failing one check: hitters SS U12 ISO peak on log loss +0.0747
(CI95 +0.0178 to +0.1333, BH q 0.320, above its null95, both frames +); hitters COF V05
surgeries on CRPS +0.0174 (+0.0046 to +0.0342, q 0.022, BELOW its null95 0.0264: the permuted
twins of a sparse count score as well); pitchers all U11 age for level on CRPS +0.0104
(+0.0008 to +0.0214, q 1.0). One cell is degenerate: hitters C V09 (no catcher in a kept group
carries a 60-day stint before the cutoff), delta exactly 0.

Classes: of the 160 scored cells, 160 NONE; no MEAN, no BOTH, no TAILS ONLY; 36 THIN. Of the
NONE cells, 122 read NULL (every scored hitter cell, where the better plant reaches 0.93 on the
mean and 1.00 on both distribution scores, and the 20 pitcher cells scored on the mean only)
and 38 UNRESOLVED (the pitcher cells with a distribution score, whose planted CRPS power is
0.40). 107 of the NULL cells carry `power_caveat` (a subgroup, or a marker covering under half
its rows, holds fewer informative rows than the full-coverage plant did).

### 11a. Defect found in the first run and repaired (disclosed)

The first run of the read (2026-10-19, kept outside the repository) built U03's age at A from
the frame row's `birth_date`. On lv_dev that field is present almost only for players who later
reached MLB: of 317 hitter rows without it, 312 have an L6 of 0 or below (the BUST class), and
461 of 472 pitcher rows; with it the BUST share is 59 and 49 percent. The missing indicator of
U03 therefore carried the outcome, and the first run showed it: hitters U03 CRPS +0.0554 (CI95
+0.0296 to +0.0819) and log loss +0.0420, pitchers +0.0481 and +0.0747, all from lv_dev (vm_dev,
where every row has a birth date, read -0.0174, -0.0093, -0.0035, -0.0066). The rule's
frames-not-negative check refused every one of those cells, so no leaked cell passed. The leak
did, however, put very small p values into the U family's BH, which let one cell (hitters SS U12
on log loss, its own p unchanged) through at q 0.064 in that first run.

Repair (a defect repair to the registered definition, which says "age at A" and names no
source; made after the first run and disclosed here): U03's age is the exposure-weighted MiLB
season age of the newest window season with a line, carried to season T, from the same
outcome-blind line ages U11 reads. The lab no longer reads the frame row's birth date. After
the repair the BUST share among rows without U03 is in line with height and weight (lv_dev
hitters 87 percent among the 264 rows without U03, against 88 among those without height).
Every number in section 11 is the repaired read; only U03's cells and the U family's q values
changed. Under the repaired read the SS U12 cell's q is 0.320 and it does not pass. The
missingness check is a probe kept in the lane's scratchpad.

Also before any run: the hitter position group reads the listing's first token, as
`efv5_atlas.position_group` does (SS/2B is SS), which the lab's first draft did not (29 hitter
rows stay ungrouped, against 297); the NONE reading follows section 8 as written (side power),
with `power_caveat` a separate field; and a cell thin on every read is classed THIN, not NONE.

## 12. Verdict (descriptive; adjudicates nothing)

No upside or volatility marker carries information beyond PROSPX consensus FV on the
development frames, for the expected outcome or for the shape of the six-season WAR
distribution. Answer to the owner's question (EW3-35): body frame and projectability, speed,
the athleticism composite, age for level, the statistical peaks, fastball velocity and its
change, workload spikes, prior surgeries and the IL history do not move the mean of later WAR
once consensus is known (hitters: a NULL at planted power 0.93), and none moves the bust or star
mass (hitters: a NULL at power 1.00 against a tail plant). On pitchers the mean read is a NULL
(power 0.95) and the distribution read is UNRESOLVED: with 46 STAR pitcher rows the frames
cannot resolve a tail effect of the planted size on CRPS (power 0.40), though the log loss
could (0.88) and found none. Where the IL markers lean, they lean against the marker (hitters IL
days -0.0087 on the mean, -0.0158 on CRPS): consensus already prices injury history. As far as
these frames can tell, the upside a scout describes (frame, speed, athleticism, statistical
profile) is already in the consensus grade.

Hand-off to EFV_X3_POOLED_MODEL: no marker passes; none is flagged. Every marker stays
available to X3 unflagged, as section 8 says. The FanGraphs-scale markers (frame, athleticism,
levers, delivery, max EV) and the velocity changes were scorable on vm_dev only (129 to 245
rows); they are the markers later FanGraphs board vintages could still resolve. Nothing served
moves.
