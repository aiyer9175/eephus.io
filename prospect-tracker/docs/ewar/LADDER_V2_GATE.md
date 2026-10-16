# Positional ladder v2: the position-switcher ladder against the Baseball-Reference inversion

Task EWAR_LADDER_REDERIVE (owner decision EW3-25, 2026-10-15, verbatim: "feel free to re-derive
our positional ladder/defensive adjustments and update the Alchemy Lab page with that.
Additionally, can you create an artifact for this and show it in the library?"). Program context:
EW3-16 and EW3-18 (an improved, data-derived positional ladder for eWAR), EW3-23 (next-season
realized runs as the part-selection target).

This document is committed ALONE, before any v2 number is computed. It fixes the candidates, the
data, the estimand, the pass rule, the seeds, the attachment rules for C and DH, the Position Fit
composition rule and what is recorded. A change to any of them after the first number is a dated
amendment under part 10, never an edit. The read runs ONCE (part 7).

## 0. The incumbent and why it is challenged

- v1 is `positional_fit.fit_ladder`: a no-intercept least squares of Baseball-Reference's
  `runs_position` per 650 PA on each player-season's innings shares, rolling six-season window,
  recentred so the exposure-weighted sum is zero. Served (2026-08-12 artifact): C +10.88,
  SS +9.38, 2B +5.12, CF +4.14, 3B +3.62, LF -6.39, RF -6.52, 1B -8.40, DH -13.70, R2 0.9737.
- v1 is an INVERSION: it recovers the constants Baseball-Reference uses. Its held-out dMAE of
  0.4819 against the folklore table (data/positional_ladder_eval.json) predicts
  Baseball-Reference's own runs_position, so it shows the inversion is exact, not that the
  pricing is right. EBR_GATE.md part S4 records that the ladder imports Baseball-Reference's
  positional pricing.
- No ladder has been scored against what players do when they change position. That is the
  test here.

## 1. Candidates

- **(a) v1**, the incumbent method. In each fold it is refit by the same inversion
  (`positional_fit._ladder_design`, min 200 PA, residual DH exposure) on the fold's training
  seasons. The served v1 vector (2021-2026) is scored as a second, fixed comparator.
- **(b) the position-switcher network ladder.** Per fielding source S (part 2), one weighted
  least squares fit of a difficulty vector D_S over the fielding positions S rates, from two row
  kinds:
  - across-season rows, the same player in adjacent seasons t-1 and t (stayers and switchers
    alike, so the persistence and aging terms are estimated on everyone):
    `r_t - k r_{t-1} = alpha + beta (age_{t-1} - 27) + sum_p (s_{t,p} - k s_{t-1,p}) D_p + e`
    where r is the source's fielding runs per 1,277.7 fielded innings, s the fielded-innings
    shares, k the persistence of the glove (grid 0.00 to 0.95 by 0.01, the value with the least
    weighted squared error), age Baseball-Reference's season age. (Superseded by amendment A1.) Conditioning on r_{t-1} is
    what keeps a move made after a bad year from being read as position difficulty (regression
    to the mean).
  - within-season rows (Savant only, the one source that splits fielding runs by position): the
    same player in the same season at positions a and b, `r_b - r_a = D_b - D_a + e`.
  - weights: the harmonic mean of the two innings counts, divided by 1,000. Identification: one
    appended row of weight 1,000 imposing sum_p e_p D_p = 0, e the exposure shares of part 4
    renormalised over the positions S covers.
  - the source ladder is L_S(p) = -D_S(p). Sources are aligned by shifting each so that its
    exposure-weighted mean over the seven Statcast positions (1B, 2B, 3B, SS, LF, CF, RF) is
    zero, then pooled per position by inverse variance (the analytic WLS variance in a fold; the
    bootstrap variance of part 6 for the served vector). C and DH are attached by part 3, then
    the nine rungs are recentred on part 4's exposure.
  - "Chained across positions": every position is linked to every other through the players who
    played both; the least squares fit resolves the whole network at once, so a 1B to SS gap is
    measured through 1B to 3B to SS players as well as direct ones.
- **(c) the offense-equalizing ladder (reference only, never served).** Baseball-Reference
  `runs_bat` per 650 PA by primary position among regulars (400+ PA; primary = the fielding
  position with at least 75% of fielded innings, or DH when DH games are at least 75% of games),
  PA-weighted, training seasons; L_c(p) = -(mean_p - PA-weighted grand mean), recentred on part
  4's exposure. The classic basis: a position's adjustment is the hitting the league tolerates
  there.
- **(d) the per-season shrunk version of the winner.** For held-out season t: the winner's fit on
  the training seasons, plus the empirical-Bayes shrunk mean deviation of the single-season fits
  of the seasons t-1 and t+1 that are in training. Per position, tau^2 = (between-season variance
  of the single-season deviations) minus (their mean sampling variance), floored at 0; shrink
  factor tau^2 / (tau^2 + v / m), v the mean sampling variance, m the number of neighbour seasons
  used (1 or 2). For the served vector the target season is the last one (2026), neighbour 2025.
- References scored and printed, never served: the FanGraphs inversion (FanGraphs `positional`
  runs from the StatsAPI sabermetrics feed per 650 PA, regressed on innings shares exactly as
  v1 regresses Baseball-Reference's), and the published FanGraphs table (C +12.5, SS +7.5,
  2B/3B/CF +2.5, LF/RF -7.5, 1B -12.5, DH -17.5 per 162 games) rescaled to per 650 PA by
  1,277.7 / 1,458.

## 2. Data (all on disk; nothing is fetched)

- Innings and games by position: `data/fielding_innings.json` (StatsAPI, 2000-2026). Fielded
  innings exclude P and DH. Rows with more than 20 innings at P are dropped (two-way players).
- Fielding sources, one row per player-season:
  - **BREF**: `.cache/war_daily/bat.parquet`, `runs_field` summed over stints, joined on
    `mlb_ID`. Rates C.
  - **FG**: the StatsAPI sabermetrics feed through `saber_feed.load_components`, `fld`
    (FanGraphs fielding runs, framing excluded). Rates C (blocking and throwing).
  - **SAVANT**: `data/savant_oaa.json`, `frp` per position (2016 onward). Does not rate C:
    a Savant row with more than 5% of fielded innings at C in either season is dropped, and
    Savant shares are over the seven Statcast positions.
- Ages: Baseball-Reference `age` (max over stints). A row with no age is dropped from the fit;
  ages are not used by the scoring predictor.
- Batting (candidate c only): Baseball-Reference `runs_bat`, `PA`.
- Unit: fielding runs per 1,277.7 fielded innings, the served v1 conversion
  (650 PA x 1.9657 innings per PA), so a rung reads in runs per 650 PA as v1's do.

## 3. C and DH (stated rules, fixed now)

- **DH.** No fielding source rates DH, so its rung comes from the same players who play both:
  L(DH) = L(1B) + mu_DH, where mu_DH is the mean fielding rate at 1B (runs per 1,277.7 innings,
  relative to the average first baseman) of DH-type player-seasons in the training seasons:
  DH games at least 25% of (DH games + fielded games), at least 90% of fielded innings at 1B,
  at least 150 fielded innings. Pooled over the sources by inverse variance (sample variance over
  n). Reading: a DH is priced at what the players who DH would be worth at first base.
- **C.** Savant does not rate catchers, and players who catch and play elsewhere are few and
  selected. The pooled network C rung from BREF and FG is used when, on the fit's own data, its
  analytic standard error is at most 1.5 runs AND at least 30 across-season rows have a C share
  change of at least 0.25; otherwise C is carried from v1, keeping v1's offset to v1's
  exposure-weighted seven-position mean. Which branch served is recorded.

## 4. Zero point

Every ladder (v1 refits, v2, the references) is recentred so that its exposure-weighted sum over
the nine rungs is zero, with ONE exposure vector for all: the served v1 artifact's
`identification.exposure_share` (2021-2026). Gaps between positions do not depend on this choice.

## 5. The estimand and the pass rule

Leave-one-season-out over held-out seasons t = 2016, ..., 2026 (11 folds). A fold's training
seasons are 2016-2026 minus t; an across-season row is indexed by its later season and is also
excluded when its earlier season is t. A fold's training data is every row whose seasons do not
include t. Ladders (v1 refit, b, c, d, the references) are
fit on the training data of the fold; nothing about season t is used to fit anything.

Scored rows of season t, per source S:

- **(A) across-season switchers**: a player with at least 300 fielded innings in both t-1 and t,
  source S rating both seasons, and a total-variation distance of at least 0.25 between his
  fielded-innings shares in t-1 and t. For ladder L: T = r + sum_p s_p L_p (fielding plus
  positional runs per 1,277.7 innings), predicted `T_t_hat = a_L + k_L T_{t-1}`, with a_L and
  k_L fit by WLS (weights as in part 1) on all training across-season rows of S (stayers and
  switchers). Loss |T_t - T_t_hat|.
- **(B) within-season pairs (SAVANT)**: a player in season t with at least 150 innings at each of
  two Statcast positions a and b (every pair). Loss |(r_b + L_b) - (r_a + L_a)|.
- Every row carries the harmonic-mean-innings weight. MAE_L = sum w |loss| / sum w.

**Primary statistic.** dMAE = MAE(v1 refit) - MAE(v2 candidate), pooled over every scored row of
every source and fold. CI95: paired cluster bootstrap over players (all of a player's rows in all
sources and seasons move together), 2,000 draws, seed 20261015.

**The EW3-23 form** (next-season realized runs of the component): the (A) rows alone are exactly
"season Y+1 realized fielding plus positional runs predicted from season Y". Its dMAE and CI95 are
computed the same way.

**Pass rule (fixed sequence, nothing re-tuned after the read).**

1. (b) replaces v1 iff the primary dMAE(v1 - b) has CI95 lower bound above 0 AND the EW3-23 form
   dMAE(v1 - b) has CI95 upper bound at or above 0 (b not significantly worse on next-season
   realized runs). Beating the folklore table is not enough and is not tested.
2. Only if 1 passed: (d) = per-season shrunk (b) replaces (b) iff dMAE(b - d), pooled, has CI95
   lower bound above 0. The served v2 vector is then (d) at target season 2026.
3. If 1 failed, v1 stays served. (d) built on v1 is printed as information and cannot serve.
4. (c), the FanGraphs inversion and the FanGraphs table are references: printed, never served.

Also printed, deciding nothing: dMAE against the served v1 vector, per source, per row kind, per
fold, and the squared-error version of every dMAE.

## 6. Recorded with the result

- The served v2 vector (if it passes) or the v2 candidate (if not): b fit on all of 2016-2026,
  each rung with a CI95 from 400 player-cluster bootstrap refits of the whole pipeline (sources,
  pooling, C and DH rules, recentring), seed 11.
- Era split: b fit on 2016-2020 and on 2021-2026; the BREF and FG legs on 2011-2015 (the
  pre-Statcast fielding frame) beside their 2016-2026 legs.
- The comparison table, per position: v2, v1 served, v1 refit on 2016-2026, each source leg,
  (c), the FanGraphs inversion, the FanGraphs table rescaled. Which C and DH branches served.
- Artifacts: `data/positional_ladder_v2_eval.json` (the read, served to the Library),
  `data/positional_ladder_v2.json` (the fitted ladder), `positional-adjustments/
  positional_ladder_v2.json` and `.csv` beside v1, the README regenerated.

## 7. The read

- One run of `python tools/ladder_v2_lab.py --read`, stdout and stderr teed to the task's output
  directory before anything else runs. Before it, `--dry-run` runs the whole path (fits, folds,
  bootstrap, report writer) on synthetic fixtures with null cells (missing ages, a source missing
  a season, a position with no rows) and must finish clean.
- On any exception after scoring began: STOP, no rerun, OWNER_QUESTION.md.
- The result is recorded in part 9 the same day, whichever way it goes.

## 8. Position Fit composition (the scale defect, fixed by rule)

- The defect (master-plan-2026-09-09 section 1.4): Position Fit values a hitter at p as
  `(D(p) + s(p) z) x 1.2777 + L(p)` with D the Statcast difficulty (runs per 1,000 innings) and
  L the Baseball-Reference ladder. The positional ladder exists to make a move value-neutral for
  an average glove, and these two price the same difficulty on different run scales, so an
  average glove gains or loses runs on a move. On the 2026-08-12 artifact the average-glove term
  D(p) x 1.2777 + L(p) runs from -7.51 (LF) to +6.06 (3B).
- The rule, whichever ladder serves: in the VALUE, the difficulty term is the served ladder's own,
  D_L(p) = (mean over the seven Statcast positions of L - L(p)) / 1.2777, so an average glove
  (z = 0) is worth the same at every fielding position, and a hitter's value at a fielding
  position is `mean7(L) + s(p) z x 1.2777`; DH is L(DH). The Statcast D(p) still reads the glove
  (z), predicts the fielding rate at a new position and carries the conversion-accuracy claim,
  unchanged. The ladder decides up and down the spectrum and the DH comparison; the glove decides
  the rest.
- Test: for z = 0 the composed value is equal at all seven Statcast positions to rounding, and the
  difference between two fielding positions equals (s(b) - s(a)) z x 1.2777.
- Position Fit reads v2 if part 5 passes, v1 otherwise. Other readers of `fit.ladder` (DEM+
  positional runs, the eWAR S4 candidate, prospect_def_value) are not moved by this task; v2 ships
  beside v1 for EWAR_V3_ASSEMBLE to take up under its own gate.

## 9. Results

### 2026-10-15, the one read

`python tools/ladder_v2_lab.py --read`, run once after the amendments (commit cdd3c3fd), stdout
and stderr teed to the task's output directory (read.log). The dry run on fixtures finished clean
first. Exit 0, 5.1 s. Record: `data/positional_ladder_v2_eval.json` (its production date was
added afterwards by `--restamp`, which copies the read's own date and changes nothing else).

Rows: BREF 4,448 across-season (1,450 switchers), FG 4,149 (1,364), SAVANT 2,294 (915) plus
1,192 same-season pairs; DH-type seasons 116 / 113 / 80. Scored: 4,141 held-out rows, 611 players.

**Verdict (part 5, fixed sequence).**

| test | dMAE, runs per 650 PA | CI95 |
| --- | ---: | --- |
| 1. v1 refit minus b, pooled (primary) | +0.886 | +0.717 to +1.059 |
| 1. v1 refit minus b, next-season rows (EW3-23 form) | +0.754 | +0.587 to +0.928 |
| 2. b minus d (per-season shrunk b), pooled | -0.026 | -0.055 to +0.003 |
| v1 as served minus b | +0.918 | +0.746 to +1.091 |
| v1 refit minus b, Savant same-season pairs | +1.683 | +1.256 to +2.110 |
| v1 refit minus b, BREF / FG / SAVANT rows | +0.433 / +0.709 / +1.343 | lower bounds +0.209 / +0.504 / +1.119 |
| v1 refit minus c (offense gap) | +0.336 | +0.208 to +0.462 |
| v1 refit minus the FanGraphs inversion | +0.105 | +0.071 to +0.140 |
| v1 refit minus the FanGraphs table | +0.179 | +0.141 to +0.218 |

Step 1 PASSES: (b) replaces v1. Step 2 FAILS: the per-season shrunk version does not beat the
pooled one, so the served v2 is (b) fit on 2016-2026. Lower MAE than v1 in 11 of 11 held-out
seasons. Pooled weighted MAE: b 6.524, d 6.550, c 7.074, FanGraphs table 7.231, FanGraphs
inversion 7.304, v1 refit 7.410, v1 served 7.442.

**The ladder** (runs per 650 PA, exposure-weighted zero; CI95 from 400 player-cluster refits of
the whole pipeline, seed 11), beside the references on the same zero:

| Pos | v2 | CI95 | v1 served | v1 refit 2016-2026 | FG inversion | FG table | offense gap |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| C | +10.19 | +10.00 to +10.40 | +10.88 | +10.97 | +13.19 | +12.44 | +5.14 |
| SS | +0.33 | -1.04 to +1.60 | +9.38 | +9.20 | +8.69 | +8.06 | +5.89 |
| 2B | -2.12 | -3.04 to -1.17 | +5.12 | +5.00 | +3.87 | +3.67 | +4.53 |
| 3B | -2.11 | -3.34 to -0.88 | +3.62 | +3.60 | +3.66 | +3.67 | -2.56 |
| CF | +1.42 | +0.05 to +2.63 | +4.14 | +3.97 | +3.87 | +3.67 | +4.61 |
| LF | +0.62 | -0.31 to +1.58 | -6.39 | -6.42 | -5.28 | -5.09 | -0.61 |
| RF | +0.32 | -0.74 to +1.40 | -6.52 | -6.33 | -5.42 | -5.09 | -4.86 |
| 1B | -3.37 | -4.53 to -2.23 | -8.40 | -8.36 | -9.84 | -9.47 | -5.26 |
| DH | -6.48 | -8.69 to -4.58 | -13.70 | -13.46 | -14.88 | -13.85 | -7.77 |

- C branch: carried from v1 (network C -0.89, SE 2.46 against the 1.5 bar; 13 C-switcher rows
  against the 30 bar). DH: 1B + mu_DH, mu_DH -3.11 (SE 0.55).
- Source legs (on the v2 zero): BREF SS -2.01 / CF +5.48 / 1B -4.47; FG SS -0.19 / CF +2.36 /
  1B -2.84; SAVANT SS +0.98 / CF +0.37 / 1B -3.31. Persistence k 0.42 / 0.47 / 0.50.
- Era split of b: 2016-2020 SS -0.49, 2B -1.60, CF +2.86, 1B -4.11; 2021-2026 SS +0.88, 2B -2.36,
  CF +0.27, 1B -2.83. The pre-Statcast legs (2011-2015, UZR and DRS) are flat as well (BREF SS
  -1.71, CF +6.09, 1B -3.06; FG SS -0.95, CF +2.93, 1B -2.46), so the flatness is not a
  Statcast convention.

**Reading.** Measured on the same players, the fielding positions sit within about five runs
of each other; the published ladders (Baseball-Reference, FanGraphs) spread them over 18. The
published spread is pricing, not what switchers do in any of the three fielding systems.

**Part 8, Position Fit.** Position Fit reads v2 and composes on one run scale. Attribution on the
current data (in memory, ladder by composition):

| | demotion AUC | raw OAA AUC | model minus raw OAA, CI95 | flagged misplaced |
| --- | ---: | ---: | --- | ---: |
| v1, composed (the 2026-08-12 method) | 0.477 | 0.614 | -0.138 (-0.178 to -0.096) | 81 |
| v1, one scale | 0.663 | 0.614 | +0.049 (+0.022 to +0.076) | 3 |
| v2, composed | 0.624 | 0.631 | -0.008 (-0.046 to +0.027) | 18 |
| v2, one scale (served) | 0.669 | 0.631 | +0.037 (+0.016 to +0.059) | 3 |

On v1's own labels the scale fix alone turns the demotion backtest from a null into a
separation: the old composition's league-wide constant (an average glove read -7.51 runs at LF
and +6.06 at 3B) swamped the glove. The conversion-accuracy claim is untouched by the fix
(Statcast D still predicts the rate at a new position). The flag count falls because a move
between two fielding positions is now the glove alone (mean absolute gain 0.55 runs per 650 PA).

### 2026-10-15, the verification: refuted pending re-read (LADDER_V2_REVERT, owner EW3-29)

An independent adversarial check of the read above, then `python tools/ladder_v2_verify.py`, which
records it on the read's own data, rows, folds, scoring (amendment A2) and draws (2,000, seed
20261015): `data/positional_ladder_v2_verify.json`. Nothing in the read or its record changes. The
read's v1-minus-b pooled dMAE reproduces exactly (+0.886, CI95 +0.717 to +1.059), so every number
below is on the same footing.

**Verdict: refuted as a ladder, pending a re-read.** Part 5's pass rule compared (b) only with the
v1 refit; it had no null comparator. Scored the same way, a ladder with every fielding rung at zero
(C and DH as the fold's b) ties b:

| test (pooled, 4,141 rows, 611 players) | dMAE, runs per 650 PA | CI95 |
| --- | ---: | --- |
| zero minus b | +0.049 | -0.005 to +0.103 |
| v1 refit minus zero | +0.837 | +0.659 to +1.026 |
| zero minus b, across-season rows | +0.037 | -0.020 to +0.096 |
| zero minus b, Savant same-season pairs | +0.120 | -0.004 to +0.232 |

Pooled weighted MAE: b 6.524, zero 6.572, v1 refit 7.410. The read's +0.886 is therefore v1's
spread costing error on this test, not b's ladder earning it.

- **Shrinkage profile.** Each ladder multiplied by 0, 0.25, 0.5, 0.75, 1, 1.25: v1 7.410 at 1 falls
  to 6.559 at 0 at every step (6.742 at 0.5); the FanGraphs table falls the same way (7.231 at 1);
  b is flat (6.559 at 0, 6.519 at 0.75, 6.524 at 1). On this test, less spread is never worse; the
  test cannot tell a right ladder from no ladder.
- **Rungs the test cannot see.** Rows are built from fielded-innings shares, so the DH rung enters
  no scored row (DH -6.48 was never tested), and C enters 13 rows with a C share change of 0.25 or
  more (about 1% of the Baseball-Reference and FanGraphs scored weight).
- **Savant FRP is not position-centred.** Summed over a position and season, Statcast fielding runs
  prevented come to +4.30 runs per 1,277.7 innings at CF, -3.14 at LF and -1.63 at RF (2016-2026
  pooled; CF and LF keep their sign in every season), where part 1 assumed every source centred within position.
  Centred, the refit is a different ladder (gaps to SS: CF +3.39, LF -1.99, RF -1.43, 1B -4.68,
  against the read's +1.09, +0.29, -0.01, -3.69) and it beats zero by +0.135 (CI95 +0.046 to
  +0.224) on the centred rows: a lead for the re-read, not a result.
- **Bridge rows.** The infield and outfield are placed on one ladder only by switchers who played
  both: 462 Baseball-Reference rows, of which 68 moved half or more of their innings across and
  carry 62% of that gap's information. Inside the infield alone the sources put 1B at -4.36, +0.74
  and -3.18 runs from SS (Baseball-Reference, FanGraphs, Statcast). CF reads above SS on the
  Baseball-Reference (+7.50), FanGraphs (+2.55) and centred Statcast (+2.77) legs; raw Statcast
  reads -0.62.

**What changes.** Position Fit values with v1 again (`positional_fit.POSFIT_LADDER = "v1"`), and
part 8's one-run-scale composition stays: on v1 it gives demotion AUC 0.6631 against raw OAA
0.6141, model minus raw OAA +0.049 (CI95 +0.022 to +0.076), so the demotion card still reads
SEPARATES. The registry row positional_ladder_v2 is provisional (measured_not_adopted) with a
refuted-pending-re-read line; `data/positional_ladder_v2.json` is a lab artifact kept off the
webroot; the Library's Positional Ladder view prints v1 as used, the read and this check.

**What a re-read needs** (a new registration, before any number): a zero ladder and scaled copies
in the pass rule, so a ladder must beat no ladder; Savant FRP centred within position and season;
a stated rule for rungs no scored row can see (DH, C); and a check that the infield to outfield
gap is not set by a handful of rows.

## 10. Amendments

### 2026-10-15, A1 to A4, before the read

Made after the fixture dry run and before any fit or score on real data (the only real-data output
so far is the loader smoke's row counts). The fixture code and the checks below are in the task's
output directory and in `tools/ladder_v2_lab.py --dry-run`.

- **A1. Part 1 (b), the across-season equation.** Registered:
  `r_t - k r_{t-1} = alpha + beta (age - 27) + sum_p (s_{t,p} - k s_{t-1,p}) D_p`, k on a grid.
  The dry run on fixtures built the way every real source is built (fielding runs centred within
  position and season) showed this form returns a compressed ladder whatever the truth: with runs
  centred, the average glove at every position reads zero, so the stayers (share change zero, most
  rows) pull every D_p to one value. On a centred fixture with planted target SS +7.93, 1B -8.85
  (moves following bad years) it returned SS +3.88, 1B -3.78; with random moves, SS +2.28 against
  +7.22. Replaced by the form that a glove prior centred on the player's previous position implies
  (centring makes that prior the position's own rung):
  `r_t = alpha + beta (age_{t-1} - 27) + k r_{t-1} + sum_p (s_{t,p} - s_{t-1,p}) D_p + e`,
  k a linear coefficient. Stayers set alpha, beta and k; switchers identify D. Same fixtures: SS
  +9.64, 1B -9.57 against +7.93, -8.85 (selection); SS +6.36, 1B -7.65 against +7.22, -8.13
  (random). The plain first difference (k = 1) was checked and rejected: SS +15.71 under
  selection, because a move made after a bad year reads as position difficulty.
- **A2. Part 5 (A), the scoring predictor.** Registered `T_t_hat = a_L + k_L T_{t-1}`. Replaced by
  the predictor the A1 model implies for a ladder L:
  `T_t_hat = a_L + k_L r_{t-1} + sum_p s_{t-1,p} L_p`, with (a_L, k_L) by WLS of
  `T_t - sum_p s_{t-1,p} L_p` on [1, r_{t-1}] over the fold's training rows. On the centred
  fixtures, scoring ladders at 0, 0.5, 0.8, 1.0, 1.2 and 1.5 times the planted target, the
  registered predictor's switcher MAE was lowest at 1.2 under selection (6.153 against 6.164 at
  1.0, a flat profile); the A2 predictor's was lowest at 1.0 under selection (5.718) and with
  random moves (5.800).
- **A3. Parts 1 (a) and 2, the v1 refit inputs.** Baseball-Reference `runs_position` and PA are read
  from `.cache/war_daily/bat.parquet` (the BREF file part 2 already names; position-player rows,
  stints summed) instead of `data/mlb_def_history.json`, whose 2026 rows are a June vintage
  (94,886 PA against 183,849 in the war_daily frame) while the StatsAPI innings are full-season.
  The construction is `_ladder_design`'s (min 200 PA, residual DH exposure) on those records.
- **A4. Part 7, the fixtures.** Rebuilt centred within position and season, with moves after bad
  years, DH regulars and the null cells part 7 lists.

Nothing else changes: candidates, sources, floors, folds, weights, the C and DH rules, the pass
rule and the seeds stand as registered.
