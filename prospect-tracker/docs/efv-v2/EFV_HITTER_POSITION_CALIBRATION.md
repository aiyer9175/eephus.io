# eFV hitter position calibration (EFV_HITTER_POSITION_CALIBRATION): registration

Registration status: REGISTERED; READ ONCE 2026-10-19 (sections 12 and 13)

Registered 2026-10-19, committed ALONE, before any number of its read is computed. Owner
decisions (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, 2026-10-19): EW3-47, verbatim "Should we
also do EFV_SIDE_ROLE_CALIBRATION on hitter positions/roles?" (orchestrator: yes, as a separate
registered follow-up), and the amendment EW3-48, verbatim "Can we factor MiLB defensive runs for
each prospect into the role factor, as well as positional versa?", folded in here before
registration. The task follows EFV_SIDE_ROLE_CALIBRATION (`docs/efv-v2/EFV_SIDE_ROLE_CALIBRATION.md`,
read once 2026-10-19, nothing passed) and reuses its frames, rows, instrument and level scalar.
The model under test is the one that serves: eFV v5 COMBINED, re-fit variant RT
(`docs/efv-v2/EFV_V5_REFIT.md`). The run appends section 12 (the numbers) and section 13 (the
verdict). No em-dashes.

Rules that bind every part: development frames only (lv_dev list vintages 2017 to 2019, vm_dev
debut cohorts 2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut
cohorts 2025 and later) is built or scored; `backtest.run_backtest` is never called; no model is
refitted (every head, weight and the order index stay as served); no projections retrain; the
fWAR label epoch's runbook is not touched; the served grade does not change under any outcome of
this read; the realized anchor is read as it stands and never re-fitted; `data/positions_played.json`
is never read.

## 0. The PROSPECT_ANCHOR_GATE reading, stated before any number

`docs/PROSPECT_ANCHOR_GATE.md` forbids computing a realized-WAR mean, residual, cohort count or
anchor by consensus-FV cell (45/50/55/60/65+), and any stratum named after an FV cell. Here:

1. The x-axis is the served eFV GRADE (map A of the served RT order inside each fold's test
   rows), never consensus FV. No row is grouped, counted or averaged by consensus FV or by any
   grade value.
2. The only groups are frame, fold (list year or debut year) and the position listed at the grade
   date (five groups, section 3). The as-of terms (section 5) are continuous covariates, never
   strata.
3. The fitted object is one multiplicative factor per listed-position group (and, for a term, a
   slope); no curve of realized value on the grade is fitted and no table of realized WAR at any
   grade value is published.
4. The anchor `value_framework.fv_to_6yr_avg_war` is an INSTRUMENT read as it stands, exactly as
   in the side and role read (its section 0, point 4).

The tests pin points 1 to 3 by a source scan of the lab (no FV-cell constant names a group).

## 1. What is known before this registration

- The side and role read (2026-10-19) found that isotonic grade maps fitted on a few hundred rows
  per cell lose out of fold to no mapping, and that its planted side effect (x1.15 / x0.85) was
  resolved 2 times in 100. Its section 13 names the smaller object tested here: one scalar per
  cell. This read therefore fits ONE partially pooled factor per position group, never a curve
  and never five free factors, and reads its own planted power.
- The fWAR label carries the positional adjustment (runs per 162 games: C +12.5, SS +7.5, 2B,
  3B and CF +2.5, LF and RF -7.5, 1B -12.5, DH -17.5), so a hitter who plays a premium position
  in the majors banks more WAR per unit of offence. Whether that shows up as realized value over
  the grade's implied value depends on whether the graders already priced it into the FV.
- DOUBLE COUNT, checked 2026-10-19 against the artifacts. The LIVE served eFV has no defence or
  position input: the served RT hitter skill head (`data/efv5_refit_weights.json`,
  `models_by_candidate.RT.hit.skill.keys`) is `["tool_hit"]`; the field and arm grade columns,
  eFLD and MFR enter no served number (X3, `docs/efv-v2/EFV_X3_POOLED_MODEL.md` section 14, and
  eFLD failed and do not serve). So no correction here double counts a served input. One caveat
  the spec did not state: the DEVELOPMENT fold models that produce the read's grades carry
  `scr_w2s_posval_hit` (the listed position's positional adjustment at the as-of read,
  `efv_w2_scout.py`) as a nonzero skill key in 5 of the 10 hitter folds (lv_dev 2017, 2018, 2019;
  vm_dev 2017 and 2020; fit receipts in `data/_labs/efv5/efv5_refit_fit.json`). On those folds the
  served order already tilts by listed position, so the offset estimated here is the position
  effect left over after that tilt; it can only understate the effect relative to the live grade,
  which carries none. The factor per frame is reported so the owner can see it.
- MiLB fielding runs (MFR, `docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md`) passed persistence
  and MLB transfer; the measure's season and game tables cover MiLB 2021 to 2026
  (`.cache/milb_fielding/tables/`, built 2026-10-16). The development frames' grade dates run
  2017 to 2023 (preseason windows, January 1 to April 30), and the 2021 MiLB season opened after
  the 2021 window closed, so an AS-OF MFR exists only for vm_dev debut cohorts 2022 and 2023.
- `data/positions_played.json` is career-to-date and leaks later positions: it is never read.
  `data/positions_played_seasons.json` (the as-of season census) is read on the OUTCOME side only
  (where a listed SS or CF later played, section 7), never as a frame input: its coverage is keyed
  by stored ids, which a bust is more likely to lack, so as an input it would sort rows by outcome.

Nothing about this read's outcome has been computed. The lab's outcome-free `--check` ran once to
produce the counts of section 3 (it reads row identities, grades, listings, clubs and the MiLB
fielding game rows dated before each grade date, and computes no statistic of any label).

## 2. The questions

- Q-POS: at the same eFV grade, does a hitter's realized value, as a fraction of what the served
  value chain implies, depend on the position he was listed at on the grade date?
- Q-MOVE: how often does a hitter listed at SS or CF later play mainly lower on the spectrum, and
  how does his realized value compare with those who stay?
- Q-TERMS: on the grade dates with MiLB fielding data, do as-of fielding runs, as-of positional
  versatility, or fielding runs at a listed premium position add to the group factor?

## 3. Frames, rows, listings and clubs

Rows: the HITTER rows of both development frames that sit in a fold's test rows of the served RT
fold builds (the EFV_FIX_B_REFIT cache: `build1.pkl`, `packs_RT.pkl`), exactly the hitter rows the
side and role read used, with the served grade (map A) and the served order.

Grade date of a row: the latest `points[]` snapshot inside its window (lv_dev:
`efv_vintage_frame.window_bounds`, the window `frame_row` reads; vm_dev: the preseason window
`efv_dataset.preseason_consensus_asof` reads). Club: the org on that point
(`trades.canonical_org`); a row without one is its own club cluster.

Listed position: each source's latest board listing (FanGraphs, MLB Pipeline) dated on or before
the grade date and within 400 days of it (`efv_w2_scout.SnapshotIndex.asof`, the as-of reader the
posval column uses). Tokens split on "/". Rule:

1. Specific tokens (C, SS, CF, 2B, 3B, RF, LF, 1B, DH), with MIF and MI listing SS and 2B and CI
   listing 3B and 1B: the MOST DEMANDING on the spectrum C > SS > CF > 2B > 3B > RF > LF > 1B > DH
   wins, across positions and across sources.
2. A generic token alone (OF; IF, INF; UT, UTIL) names some member of its set without saying
   which: the most demanding member found in the player's own earlier listings (any date on or
   before the grade date) wins; else the default (OF to LF/RF, the infield and utility tokens to
   2B/3B).
3. No hitter token: UNLISTED (the row keeps the pooled factor, no adjustment).

Groups: C | SS/CF | 2B/3B | LF/RF (corner OF) | 1B/DH.

Outcome-free counts (`--check`, 2026-10-19):

| frame | rows | C | SS/CF | 2B/3B | LF/RF | 1B/DH | UNLISTED | listed | generic, by history | generic, default |
|---|---|---|---|---|---|---|---|---|---|---|
| lv_dev | 1,465 | 184 | 496 | 297 | 353 | 105 | 30 | 1,162 | 5 | 268 |
| vm_dev | 406 | 57 | 154 | 92 | 65 | 35 | 3 | 376 | 3 | 24 |

1,871 rows, 986 players, 30 clubs (no row without a club), ten (frame, fold) groups. 292 rows
(15.6 percent) carry only a generic OF listing and sit in LF/RF by the default; a sensitivity
(section 7) gives them their own pooled cell.

Term frame (section 5): the rows with a grade date in 2021 or later, vm_dev debut cohorts 2021 to
2023, 227 rows (C 30, SS/CF 95, 2B/3B 51, LF/RF 29, 1B/DH 19):

| grade year | rows | a MiLB game before the grade date | MFR chances at the listed position | 200 or more such chances | 2 or more qualifying positions |
|---|---|---|---|---|---|
| 2021 | 51 | 0 | 0 | 0 | 0 |
| 2022 | 100 | 99 | 94 | 24 | 69 |
| 2023 | 76 | 76 | 73 | 51 | 59 |

## 4. The candidate: one partially pooled group factor

Notation. Row i in (frame, fold) group G: label y_i (lv_dev: fWAR over the first three seasons in
the window, 0 without a debut; vm_dev: career fWAR resolved through 2026), served grade g_i,
instrument I_i = 6 x `value_framework.fv_to_6yr_avg_war(g_i)`. The incumbent (zero adjustment)
implies v_i = kappa_G I_i, kappa_G = (sum of y over G) / (sum of I over G), one number per
(frame, fold) over the group's hitters. With a factor f per row the implied value is
v_i = (sum of y over G) x I_i f_i / (sum of I f over G): the factors only re-allocate the group's
realized total between positions, so the level is never re-fitted.

The factor. On a training row set: per position group j, R_j = (sum y) / (sum v) under the
incumbent, theta_j = log max(R_j, 0.05), and its player-clustered delta-method variance
s2_j = sum over players of (sum of y - R_j v over the player's rows in j) squared, over
(R_j sum v)^2. The between-group variance tau2 is the DerSimonian-Laird estimate over the five
groups (weights 1 / s2_j, Q against the precision-weighted mean theta_bar, floored at 0). The
partially pooled offset is theta*_j = theta_bar + tau2 / (tau2 + s2_j) (theta_j - theta_bar),
f_j = exp(theta*_j); an UNLISTED row takes exp(theta_bar). One variance component decides how
far every group moves: with tau2 = 0 every factor equals the pool and the correction IS zero
adjustment; the small catcher cell is pulled hardest.

Cross-fitting: each (frame, fold) group is corrected by factors fitted on every other group's
rows, excluding every player who has a row in the held-out group, exactly as the side and role
read cross-fits. The production factors (section 9) are fitted on all rows.

## 5. The as-of terms (amendment EW3-48), on the term frame only

All from the MFR build's game rows (`.cache/milb_fielding/tables/game_rows.parquet` with the
game dates of `games.parquet`), restricted to games dated BEFORE the row's grade date; the player
is matched by the record's MLBAM id (every term-frame row is a debuted player, so the id exists
for all and its presence carries no outcome).

1. MFR at the listed position: the gate's AAA-equivalent runs (component runs centred within
   level, season and position, times the level factor F_L of the build) at the row's listed
   token, summed over the player's games before the grade date, per 1,000 CHANCES (range
   chances, double-play, arm, framing and catcher-throw opportunities), shrunk to the position
   mean (0) by its reliability: rate = 1000 x runs / (chances + k_ch), k_ch = the gate's
   split-half k for the position (innings) times the position's chances per inning. Scaled by the
   position's SD of the same rate over MiLB player-position aggregates with 200 or more innings
   from the seasons BEFORE the row's grade year. A DH listing, or no chance at the position,
   reads 0 (the position mean).
2. Positional versatility, rebuilt as of the grade date with the `fielding_positions` rule: a
   position qualifies with 10 or more games or 5 or more starts there (a start: a game with 5 or
   more innings at the position, the play-by-play's proxy; DH, PH and PR are not positions).
   Two columns: the count of qualifying positions, and the share of the player's position-games
   at C, SS or CF. Each column is centred and scaled on the fitting rows; a row with no game
   before the grade date reads the fitting rows' mean (0).
3. Listed SS/CF x MFR: the MFR column times 1 for a row listed SS/CF, else 0 (weak defenders
   listed at a premium position are the likely movers down the spectrum).

Each term model is the group-only model times exp(x beta), re-allocated inside each (frame, fold)
group. beta (one slope; two for versatility) is the Poisson quasi-likelihood estimate on the
fitting rows with the log group-only implied value as offset (the score is
sum x (y - mu), valid for a label that can be negative; ridge 0.001). Cross-fit: for each held-out
term-frame (frame, fold) group k, the group factors are those fitted without k (section 4), beta
is fitted on the other term-frame groups' rows excluding k's players, and k's rows are compared
under the group-only and the term model. The 2021 rows carry no term value (no MiLB game before
their grade date), so they enter both models identically.

## 6. Statistics

1. PRIMARY: delta = mean(e_zero - e_corr), e_i = (y_i - v_i)^2 / var_F, var_F the label variance
   of the row's frame over its hitter rows. Positive: the correction is closer. For a term:
   mean(e_group - e_term) over the term-frame rows.
2. Uncertainty: the PLAYER- AND CLUB-CLUSTERED bootstrap (pigeonhole: players and clubs resampled
   independently with replacement, each row weighted by its player's count times its club's
   count), B 4000, seed 20261021. The one-sided 95 percent lower bound is the 5th percentile of
   the draws; the share of draws at or below 0 is reported.
3. Null comparators: zero adjustment is the incumbent every delta is taken against. Reported
   beside it, deciding nothing: a GROUP-PERMUTED twin (listed groups shuffled within each
   (frame, fold) before the factors are fitted; the corrected rows keep their own group), K 200,
   its delta's 95th percentile; for each term a TERM-PERMUTED twin (term values shuffled within
   each term-frame group), K 200.
4. Planted recovery: y*_i = v_i x m_i + (y_pi(i) - mean y of the row's (frame, fold) group), pi a
   permutation inside the group (noise with the label's own spread; no residual is formed), with
   the whole pipeline (kappa, factors, cross-fit, terms) rerun on y*, K 100 draws, B 500 each.
   GROUP: m = 1.25 on SS/CF rows, 1 elsewhere. POWER = share of draws whose lower bound is above
   0; RECOVERED when the median over draws of the production fit's SS/CF factor over the
   precision-weighted mean of the other groups' factors lies within 50 percent of the planted
   log effect (between 1.12 and 1.40). SIZE: the same with m = 1 everywhere. TERMS: m =
   exp(0.30 x each standardized term column) on the term-frame rows (re-allocated inside each
   group), RECOVERED when the median production slope of every column lies within 50 percent of
   0.30; SIZE with no plant.
5. Minimum detectable effect, reported: per group, 2.486 x the delta-method SE of theta_j
   (one-sided 5 percent, 80 percent power); per term, 2.486 x the two-way clustered bootstrap SE
   (B 1000) of the production slope. Censoring of the term frame: seasons observed through 2026
   per grade year (2022: 5; 2023: 4). A failed term is worded UNDERPOWERED when its planted power
   is below 0.80, never "no effect".

## 7. Reported, deciding nothing

Under the incumbent, with two-way clustered CI95 (B 4000), pooled and per frame: realized over
implied value per group, and per group over all hitters. Q-MOVE: among rows listed SS/CF, the
eventual position (OUTCOME SIDE: the most-played non-DH position in games, MLB and MiLB, over the
seasons from the grade year on, from the as-of season census), the share whose eventual position
sits in 2B/3B, LF/RF or 1B/DH (the move rate, among rows whose eventual position is known), and
realized over implied for movers, stayers and movers over stayers. A move is read after the
fact, so this explains, it does not predict. Sensitivity: the generic-OF rows of section 3 as a
sixth pooled cell, its delta against zero adjustment. The production factors (fitted on all rows)
and the board effect: the factors applied at each live hitter's current listed position (the
listing that is ex ante for the live grade), the live hitters' total implied value kept, per
group the value factor and the mean change in implied six-season WAR, and the top 50 hitters by
grade.

## 8. The rule (fixed here)

The group factor passes when all hold:

- G1 delta (section 6.1) pooled over both frames has its one-sided 95 percent lower bound above 0
  (two-way clustered, B 4000);
- G2 the planted SS/CF effect is RECOVERED (section 6.4);
- G3 SIZE at most 0.10.

A term enters when the group factor passes and all hold:

- T1 delta (term against the group-only model, term frame) has its one-sided 95 percent lower
  bound above 0 (two-way clustered, B 4000);
- T2 its planted slope is RECOVERED;
- T3 its SIZE at most 0.10.

A failure is worded by its planted power: at or above 0.80 a NULL (an effect of the planted size
would have been resolved), below it UNRESOLVED for the group factor and UNDERPOWERED for a term.
The three terms are read separately against the same base and are not Holm-corrected (each must
also recover a planted effect, and none can ship unless the group factor passes).

## 9. What ships under each outcome

- The group factor fails: nothing is built. The artifact
  `data/_labs/efv5/efv_hitter_position_calibration.json` (role development, adjudicates false),
  sections 12 and 13 here, `EFV_HITTER_POSITION_CALIBRATION_RESULTS.md` (plain language) and one
  ledger line in `docs/efv-v2/STATUS.md` are the whole result; no served number moves and
  `HITTER_POSITION_CALIBRATION_ON` stays False, read by nothing.
- The group factor passes: built DARK. `efv_hitter_position_calibration.HITTER_POSITION_CALIBRATION_ON`
  (default False, byte identical) gates a hook that prices the hitter value chain (the six-season
  WAR and surplus the card shows) at the production factor of the hitter's current listed group
  (and each passing term's slope), stored in a committed data file. The displayed eFV grade, the
  rank and the order index do not change. Tests pin the default and byte identity with the switch
  off. `OWNER_QUESTION.md` in the task's output directory carries the board effect for the owner
  to flip. The owner flips it; this task does not.

## 10. Gate compliance and stop rules

If any of the output map test's checks Q1 to Q4 fails, or the label provider is not the frozen
fWAR provider, no outcome is read and the result is the refusal. The artifact is written once; a
second `--run` refuses.

## 11. Defaults applied (named for the orchestrator)

- D-1: the served map A grade and the served weights; nothing refitted.
- D-2: the served side-pooled anchor is the instrument; one kappa per (frame, fold) over hitters.
- D-3: a multiplicative factor (the group's realized over implied ratio) on the expected-value
  scale, re-allocated inside each (frame, fold); an additive WAR offset is not tested (most rows
  realize near zero, where an additive offset would move busts and regulars alike).
- D-4: partial pooling by DerSimonian-Laird (one between-group variance), shrinking to the
  precision-weighted mean.
- D-5: the listing rule of section 3 (most demanding across tokens and sources; a generic token
  by the player's own earlier listings, else OF to LF/RF and the infield tokens to 2B/3B).
- D-6: MFR per 1,000 chances with the reliability shrink of section 5; the start proxy of 5 or
  more innings at a position.
- D-7: constants seed 20261021, B 4000, B_MDE 1000, K_NULL 200, K_PLANT 100, B_PLANT 500, one-sided
  5th percentile, SIZE at most 0.10, POWER 0.80, recovery tolerance 50 percent, ratio floor 0.05,
  planted SS/CF x1.25, planted slope 0.30, term frame from grade year 2021, versatility 10 games
  or 5 starts.

Run: `python -u efv_hitter_position_calibration.py --run --cache <EFV_FIX_B_REFIT cache> --work
<scratch>` after this registration and the module's commit.

## 12. The read (2026-10-19, once; `python -u efv_hitter_position_calibration.py --run`)

Artifact: `data/_labs/efv5/efv_hitter_position_calibration.json` (role development, adjudicates
false; tool sha256 b67e9c3e, module commit 5608cc0b, registration commit 9a08d9eb, label
fwar@2026-10-02). Elapsed 71 s.

Checks, all held before any outcome was read: Q1 the 20 cached fold models match the fit
artifact's receipts; Q2 the cross-fitted RT within reproduces the fit artifact (lv_dev hit 0.1913,
vm_dev hit 0.4021; pitchers 0.1442, 0.3853, served 0.2198); Q3 no reserved fold; Q4 the live board
reproduces (u_c to 5e-7, map A to the served one-decimal grade within 0.05 on all 1,055 hitters
and 941 pitchers). Rows, listings and clubs as section 3.

THE GROUP FACTOR. Pooled over all 1,871 rows, the groups' realized over implied ratios relative
to the pool (the production fit, player-clustered delta-method SE of the log ratio, and the
one-sided minimum detectable log effect at 80 percent power):

| group | rows | ratio over the pool | SE (log) | MDE (log) | MDE as a factor |
|---|---|---|---|---|---|
| C | 241 | 1.04 | 0.18 | 0.46 | x1.58 |
| SS/CF | 650 | 1.05 | 0.11 | 0.26 | x1.30 |
| 2B/3B | 389 | 0.82 | 0.18 | 0.46 | x1.58 |
| LF/RF | 418 | 0.99 | 0.16 | 0.41 | x1.51 |
| 1B/DH | 140 | 1.01 | 0.32 | 0.79 | x2.21 |

The heterogeneity statistic Q is 1.44 on 4 degrees of freedom, below its null expectation of 4,
so the DerSimonian-Laird between-group variance is 0 and every partially pooled factor is 1.000:
the correction IS zero adjustment. In the cross-fit the between-group variance is 0 in nine of the
ten held-out folds and 0.00002 in the tenth (vm_dev 2017, factors within 0.0002 of 1).
PRIMARY, delta against zero adjustment (frame-standardized squared error; positive: the
correction is closer), two-way clustered, B 4000: -0.00000 (one-sided 95 percent lower bound
-0.00001; lv_dev -0.00000, vm_dev -0.00001); on the term frame 0.00000. The group-permuted twin's
delta has mean -0.0014 and 95th percentile +0.0029 over 200 draws.

Planted recovery (K 100, B 500): SS/CF x1.25 POWER 0.02, the median recovered SS/CF factor 1.07
(10th to 90th percentile 1.00 to 1.28; the band was 1.12 to 1.40), so NOT RECOVERED; SIZE 0.00
(median recovered factor 1.00). On these frames a 25 percent SS/CF effect moves the log ratio by
about two standard errors, which the five-group heterogeneity test does not separate from noise
in most draws, so the pooled factor stays at 1.

Sensitivity (decides nothing): the 259 rows whose only listing is a generic OF (by the default in
LF/RF) as a sixth pooled cell: Q 3.81 on 5 degrees of freedom, between-group variance 0, every
factor 1.000; delta against zero adjustment -0.0010 (lower bound -0.0027). Raw ratios over the
pool: the generic-OF cell 1.24, the specific LF/RF listings 0.80.

THE AS-OF TERMS (term frame: 227 rows, vm_dev debut cohorts 2021 to 2023; 2021 rows carry no
term value; seasons observed through 2026: 2021 six, 2022 five, 2023 four). Each against the
group-only model, two-way clustered, B 4000:

| term | delta | one-sided 95 percent lower bound | production slope (per SD) | two-way SE | MDE (one-sided) | planted 0.30: power, recovered slope | size |
|---|---|---|---|---|---|---|---|
| MFR at the listed position | -0.0086 | -0.0430 | +0.17 | 0.19 | 0.48 | 0.05, 0.28 | 0.00 |
| versatility (positions; premium share) | -0.0031 | -0.0493 | +0.15; +0.19 | 0.15; 0.17 | 0.37; 0.42 | 0.04, 0.25 and 0.24 | 0.00 |
| listed SS/CF x MFR | -0.0010 | -0.0250 | +0.17 | 0.29 | 0.73 | 0.01, 0.27 | 0.00 |

Each slope is positive (better defenders, more versatile players and players with a larger share
of games at C, SS or CF realize more of their implied value), but every slope sits within about
one standard error of 0, and out of fold every term model is farther from the label than the
group-only model. The planted slopes are recovered (the estimator is close to unbiased) but
resolved in at most 5 of 100 draws: 175 rows with fielding data cannot resolve a slope of 0.30
per SD. The term-permuted twins' 95th percentiles: MFR +0.0081, versatility +0.0087, SS/CF x MFR
+0.0042.

Reported, deciding nothing (section 7): realized over implied under zero adjustment, two-way
clustered CI95, B 4000.

| group | pooled | lv_dev | vm_dev |
|---|---|---|---|
| C | 1.05 (0.42 to 1.78) | 0.94 (0.09 to 1.78) | 1.11 (0.49 to 1.95) |
| SS/CF | 1.07 (0.72 to 1.45) | 1.07 (0.49 to 1.79) | 1.07 (0.73 to 1.45) |
| 2B/3B | 0.83 (0.41 to 1.36) | 0.83 (0.24 to 1.55) | 0.83 (0.42 to 1.38) |
| LF/RF | 1.01 (0.51 to 1.57) | 1.20 (0.44 to 2.15) | 0.89 (0.43 to 1.43) |
| 1B/DH | 1.03 (0.09 to 2.01) | 0.68 (-0.26 to 2.17) | 1.20 (0.25 to 2.27) |

Q-MOVE (outcome side): of the 650 rows listed SS/CF, 540 have a later position in the season
census; 194 of them (35.9 percent; lv_dev 36.4, vm_dev 34.7) played mainly at 2B/3B, LF/RF or
1B/DH from the grade year on. Movers realized 1.27 of their implied value (CI95 0.61 to 2.05),
stayers 1.04 (0.63 to 1.48), movers over stayers 1.22 (0.54 to 2.37; lv_dev 1.82, vm_dev 1.06).
The 110 rows with no later position realized 0.04 of implied: they are mostly prospects who never
played again under a tracked id, which is why the census stays an outcome-side read and never a
frame input. A move is observed only for a player who kept playing, so movers are hitters whose
bat carried them to another position; the comparison explains, it does not predict.

Board effect of the production factors (decides nothing): every factor is 1.000, so no live
hitter's implied six-season WAR changes (top 50 hitters by grade: 4.666 served, 4.666 calibrated).

## 13. The verdict

Nothing passes; nothing is built, no flag is added and no served number moves.
`HITTER_POSITION_CALIBRATION_ON` stays False and is read by nothing.

- The group factor FAILS (G1 and G2 fail; G3 holds), worded UNRESOLVED (planted power 0.02): the
  partial pooling finds no between-group variance (Q 1.44 on 4 degrees of freedom), so the
  correction collapses to zero adjustment and ties it exactly. The frames can resolve only a group
  effect of about x1.30 for SS/CF and x1.5 to x2.2 for the other groups.
- Q-POS, reported: at the same eFV grade, no listed-position group realizes a resolved share
  different from the others; the largest point gap is 2B/3B at 0.83 of implied (CI95 0.41 to
  1.36), and SS/CF realizes 1.07 (0.72 to 1.45). Within what these frames can check, the graders'
  FV and the served grade already price the listed position.
- Q-MOVE, reported: about 36 percent of listed SS and CF who keep playing move down the spectrum;
  their realized value is not lower than the stayers' (1.22 of the stayers' share, not resolved).
- Q-TERMS: all three terms FAIL T1 and are worded UNDERPOWERED (planted power 0.05, 0.04, 0.01);
  their slopes point the expected way (+0.15 to +0.19 per SD) inside one standard error. The MFR
  and versatility data reach only 175 development rows with a fielding history before their grade
  date; the read gains power only when more debut cohorts with 2021+ MiLB fielding history have
  outcome windows (the 2024 cohort is outside the development frames and the 2025+ cohorts are
  reserved).
