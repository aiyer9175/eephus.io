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
    weighted squared error), age Baseball-Reference's season age. Conditioning on r_{t-1} is
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

(Recorded after the one read.)

## 10. Amendments

(None.)
