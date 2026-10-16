# Positional ladder v3: the corrected re-read of the position-switcher ladder

Task LADDER_V3_REREAD (owner decision EW3-29, 2026-10-15, under EW3-25's authority: "feel free to
re-derive our positional ladder/defensive adjustments and update the Alchemy Lab page with that.
Additionally, can you create an artifact for this and show it in the library?"). Predecessor:
docs/ewar/LADDER_V2_GATE.md, whose one read passed v2 against the Baseball-Reference inversion
(v1) and whose verification (part 9 there, `data/positional_ladder_v2_verify.json`) refuted it
pending a re-read: an all-zero fielding ladder tied v2, Statcast fielding runs were not centred
within position, the DH rung entered no scored row, and a few cross-group switchers set the
infield to outfield and first-base levels.

This document is committed ALONE, before any v3 number is computed. It fixes the candidate, the
data, the comparators, the pass rule, the simulation, the seeds, the C, DH and anchor rules, and
what is recorded. A change to any of them after the first real-data number is a dated amendment
under part 10, never an edit. The read runs ONCE (part 8).

What is already known (stated so the choices below are read against it): the v2 read printed the
offense-equalizing ladder on 2016-2026 (part 9 there) and the verification printed each source's
legs, the centred Statcast refit and the group-restricted networks. The EW3-29 ruling notes that
inside the infield the switcher data agree with v1 (2B to SS -2.96 against v1's -4.26, 3B to SS
-4.75 against -5.76), while across groups and at 1B the three fielding sources disagree with each
other. That is why this re-read takes only within-group gaps from fielding runs and anchors the
rest.

## 1. The candidate (v3), one, fixed now

v3 has four parts, each fit on a fold's training seasons only.

**(a) Within-group shapes from switchers.** (Superseded by amendment A1.) Two groups: the infield IF3 = {2B, 3B, SS} and the
outfield OF3 = {LF, CF, RF}. 1B is NOT in either group (its level is anchored, part 1 c). Per
fielding source S (part 2) and group G, one weighted least squares fit of a difficulty vector D
over the positions of G:

- across-season rows: the same player in seasons t-1 and t, at least 300 innings rated by S in
  each, at least 95% of the innings S rates in G in BOTH seasons (shares renormalised over G):
  `r_t = alpha + beta (age_{t-1} - 27) + k1 r_{t-1} + k2 rbar* + k3 miss + sum_p (s_{t,p} - s_{t-1,p}) D_p + e`
  r is S's fielding runs per 1,277.7 innings S rates, s the renormalised shares.
- **multi-season player type** (the EW3-29 ask, item 4): `rbar` is the innings-weighted mean of
  S's rate over seasons t-2 and t-3, each counted only when it has at least 150 innings rated by
  S and at least 95% of them in G; `sbar` the matching innings-weighted shares over G. It enters
  on the t-1 position reference: `rbar* = rbar - (sbar - s_{t-1}) . D`, so a glove measured
  earlier at another group position is read at the position played last season. When neither
  earlier season qualifies, `rbar* = 0` and `miss = 1`. Because `rbar*` contains D, the fit
  alternates: D from the fit with `rbar* = rbar`, then `rbar*` from that D, refit, until no
  coefficient moves by more than 1e-4 (cap 50 rounds; the round count is recorded).
- within-season rows (Statcast only): the same player in one season with at least 150 innings at
  each of two positions of G, `r_b - r_a = D_b - D_a + e` (centred rates, part 2).
- rows with no age are dropped from the fit. Weights: the harmonic mean of the two innings counts
  over 1,000. Identification: one appended row of weight 1,000 imposing `sum_{p in G} e_p D_p = 0`,
  e the exposure of part 5 renormalised over G.
- the source's group shape is `W_{S,G}(p) = -D(p)` (exposure-weighted mean zero over G). Shapes
  are pooled per position over sources by inverse analytic WLS variance: `W_G(p)`.

**(b) The anchor, chosen now: the offense-equalizing gap among regulars.** The alternative the
ask names (full-season bridges with an off-primary familiarity term) is not used; it is a
fielding-run estimate of the same cross-group gap the three sources disagree on. Per fold, on the
training seasons: regulars are player-seasons with at least 400 PA; primary position is the
fielding position with at least 75% of fielded innings, or DH when DH games are at least 75% of
games (DH plus fielded); `O_p` is the PA-weighted mean of Baseball-Reference `runs_bat` per 650 PA
of the regulars whose primary is p. This is ladder_v2.fit_offense's construction, unchanged.
`O_IF` and `O_OF` are the exposure-weighted means of `O_p` over IF3 and OF3.

**(c) Assembly.**

- `L(p) = W_IF(p) - O_IF` for p in IF3; `L(p) = W_OF(p) - O_OF` for p in OF3.
- `L(1B) = -O_1B`; `L(DH) = -O_DH`.
- So each group's exposure-weighted level, and the 1B and DH rungs, are the offense-equalizing
  values; inside each group the gaps are the switchers'.

**(d) C, carried and stated.** No catcher-specific fielding estimate is attempted: on the v2 read
13 rows had a catcher share change of 0.25 or more, against that gate's 30. C keeps v1's offset to
v1's exposure-weighted seven-position mean: `L(C) = mean7(L) + (v1(C) - mean7(v1))`, with the
fold's v1 refit in a fold and the served v1 vector in the recorded fit. The catcher rung is
therefore not a v3 claim.

Then the nine rungs are recentred on part 5's exposure.

## 2. Data (all on disk; nothing is fetched)

The v2 gate's part 2 with amendment A3, unchanged: StatsAPI innings (`data/fielding_innings.json`),
two-way rows (more than 20 innings at P) dropped; BREF `runs_field` and FG `fld` per
player-season; Statcast `frp` per position (`data/savant_oaa.json`, 2016 onward, rows with more
than 5% of fielded innings at C dropped); Baseball-Reference age, PA and `runs_bat`
(`.cache/war_daily/bat.parquet`). Unit: runs per 1,277.7 innings, so rungs read in runs per 650 PA.

**Statcast centred (the EW3-29 ask, item 2).** Before any row is built, every Statcast `frp` is
centred within (position, season): `frp_c = frp - inn_p x (sum frp / sum inn over every
player-season with a Statcast value at p in that season)`. This is applied to every Statcast row
everywhere in this read (fits, scored rows, simulation). Baseball-Reference and FanGraphs runs are
used as published; their implied league rates by position are printed as a check.

## 3. Comparators

Scored on the same rows and folds as v3, each fit on the fold's training seasons:

- **zero**: every fielding rung (1B, 2B, 3B, SS, LF, CF, RF) at 0; C and DH as the fold's v3.
- **v1**: the Baseball-Reference inversion refit in the fold (`ladder_v2.fit_inversion`).
- **the scaled-v1 family**: v1 x 0.25, 0.5, 0.75, 1.0, 1.25.
- **the FanGraphs table** (C +12.5, SS +7.5, 2B/3B/CF +2.5, LF/RF -7.5, 1B -12.5, DH -17.5 per
  162 games, rescaled by 1,277.7 / 1,458).
- printed, deciding nothing: the offense-equalizing ladder (every rung `-O_p`, C as in part 1 d),
  v3's within-group shapes on a zero level (v3 with every level set to 0: tests the shapes
  alone), and the v2 vector as read (fixed).

## 4. The scoring

Leave-one-season-out, held-out seasons t = 2016, ..., 2026 (11 folds). A fold's training data is
every row none of whose seasons (t-3 to t of a row, including the seasons its multi-season terms
read) is the held-out season.

- **(A) across-season switchers** of season t, per source: at least 300 innings rated by the
  source in t-1 and t, a total-variation distance of at least 0.25 between the source's innings
  shares in t-1 and t (all the positions the source rates, as in v2), Statcast centred. For
  ladder L: `y = r_t + (s_t - s_{t-1}) . L`, predicted by
  `a_L + k1_L r_{t-1} + k2_L rbar*_L + k3_L miss`, where `rbar*_L = rbar + (sbar - s_{t-1}) . L`
  over every position the source rates (the earlier seasons at least 150 rated innings each; the
  95%-in-group condition does not apply here), coefficients by WLS over the fold's training rows
  of that source (stayers and switchers). Loss `|y - y_hat|`. This is the v2 amendment A2
  predictor with the multi-season terms added.
- **(B) Statcast same-season pairs** of season t (at least 150 innings at each of two Statcast
  positions, centred): loss `|(r_b + L_b) - (r_a + L_a)|`.
- Weights: the harmonic-mean-innings weight. `MAE_L = sum w |loss| / sum w`.
- dMAE(a - b) = MAE(a) - MAE(b), positive favours b. CI95: paired player-cluster bootstrap (all
  of a player's rows in all sources and seasons together), 2,000 draws, seed 20261015.
- Printed, deciding nothing: the same tests with v2's A2 predictor (no multi-season terms), per
  source, per row kind, per fold, the squared-error versions.

## 5. Zero point

Every ladder is recentred so its exposure-weighted sum over the nine rungs is zero, with the
served v1 artifact's `identification.exposure_share`. Gaps do not depend on it.

## 6. The simulation (planted-ladder recovery, the verifier's t2 construction)

Real design, simulated fielding runs: every real player-season's innings by position, age,
source coverage and Statcast coverage are kept; only the runs are replaced.

- Planted q: the FanGraphs table ladder (part 3), recentred. Each player's career primary is the
  position of most career innings (2010-2026); his glove `a_m = q(primary) + N(0, 5)`.
- Season glove at position p: `a_m - 0.18 (age - 27) + N(0, 6 / sqrt(max(inn_p, 50) / 1,277.7))`
  (age 27 when missing).
- Runs at p: `(glove - its innings-weighted mean over every player at p in that season) x inn_p /
  1,277.7`. BREF and FG season totals: the sum over positions plus N(0, 2), where the real record
  has that source. Statcast: the per-position runs, at the positions the real record has.
- The target is the realized G(p), the innings-weighted mean simulated glove at p over 2016-2026
  (the verifier's 'true G'), which is what any switcher estimate can recover.
- v3's part 1 (a), run on all 2016-2026 rows of the simulated data (centring included, a no-op up
  to rounding), returns `W_IF` and `W_OF`. Recovery ratio per rung: `(W(p) - W(ref)) / (G(p) -
  G(ref))`, ref SS in the infield (2B, 3B) and CF in the outfield (LF, RF): four ratios.
- Seeds 7, 8, 9, 10, 11; the mean ratio over the five seeds is the recovery.
- The anchored rungs (group levels, 1B, DH) and the carried C do not come from fielding runs, so
  no fielding simulation can test them; the recovery bar applies to the four within-group ratios,
  which are everything v3 estimates from fielding runs.
- Printed, deciding nothing: the same with a selection stress (players with less than 75% of
  career innings at their primary 3 runs worse everywhere) and a familiarity stress (3 runs off
  primary); and the test's power: on seed 7, the part 4 scoring of G (planted, with C and DH from
  q) against zero, 11 folds, dMAE with its CI95.

## 7. The pass rule (all five, fixed now, nothing re-tuned after the read)

v3 passes iff ALL of:

1. dMAE(zero - v3), pooled, CI95 lower bound above 0.
2. dMAE(v1 - v3), pooled, CI95 lower bound above 0.
3. v3's pooled MAE is below each of v1 x 0.25, 0.5, 0.75, 1.0, 1.25 and the FanGraphs table.
4. On the (A) rows alone (next-season realized runs, the EW3-23 form), dMAE(zero - v3) has CI95
   upper bound at or above 0 (v3 not significantly worse than no ladder on next season).
5. Every one of the four recovery ratios (part 6) is between 0.80 and 1.25.

If v3 passes: it is built DARK (a ladder artifact kept off the webroot, nothing served reads it;
Position Fit stays on v1) and OWNER_QUESTION.md asks the Position Fit flip and eWAR use. If it
fails: v1 stays, and no ladder artifact is written or published (EW3-29: no ladder artifact until
a passing ladder exists).

## 8. The read

- Before it, `python tools/ladder_v3_lab.py --dry-run` runs the whole path (fits, folds,
  simulation, bootstrap, report writer) on the v2 lab's centred fixtures with null cells, and
  must finish clean. Nothing on real data is fitted or scored by the dry run.
- One run of `python tools/ladder_v3_lab.py --read`, stdout and stderr teed to the task's output
  directory. On any exception after scoring began: STOP, no rerun, OWNER_QUESTION.md.
- Recorded: `data/positional_ladder_v3_eval.json` (the read, for the Library's Positional Ladder
  view): every test, MAE table, per-fold MAE, the simulation, the v3 vector fit on 2016-2026 with
  CI95 per rung from 400 player-cluster refits of the whole pipeline (seed 11; the anchor refit in
  each draw), each source's group shapes, the offense values, the alternation round counts, the
  row counts. The result goes in part 9 the same day, whichever way it goes.

## 9. Results

### 2026-10-15, the one read

`python tools/ladder_v3_lab.py --read`, run once after amendment A1 (commit b4675e45), stdout and
stderr teed to the task's output directory (read.log). The fixture dry run finished clean first.
Exit 0, 13 s. Record: `data/positional_ladder_v3_eval.json`.

Rows: the v2 read's scored set (BREF 4,448 across-season rows, 1,450 switchers; FG 4,149, 1,364;
Statcast 2,294, 915, plus 1,192 same-season pairs), Statcast now centred; season rows for the
group fits BREF 10,777, FG 10,162, Statcast 5,722; 2,651 regulars for the anchor. Scored: 4,141
held-out rows, 611 players.

**Verdict (part 7): v3 FAILS (criteria 1, 3 and 5).**

| criterion | measured | result |
| --- | --- | --- |
| 1. zero minus v3, pooled | +0.037 runs per 650 PA, CI95 -0.076 to +0.150 | fail |
| 2. v1 refit minus v3, pooled | +0.438, CI95 +0.353 to +0.524 | pass |
| 3. pooled MAE v3 6.481 below v1 x 0.25 / 0.5 / 0.75 / 1 / 1.25 and the FanGraphs table | 6.403 / 6.445 / 6.626 / 6.918 / 7.311; 6.804 | fail (x 0.25 and x 0.5 lower) |
| 4. zero minus v3, next-season rows | -0.062, CI95 -0.178 to +0.050 | pass |
| 5. recovery ratios, mean of 5 seeds | 2B 0.88, 3B 1.03, LF 0.75, RF 0.87 | fail (LF) |

v1 stays on Position Fit; no v3 ladder artifact is written or published (EW3-29).

Printed, deciding nothing:

- By row kind: on the Statcast same-season pairs v3 beats zero by +0.633 (CI95 +0.340 to +0.934;
  MAE 9.087 against 9.720); on the across-season rows zero is lower (5.986 against 6.048). By
  source, zero minus v3: Baseball-Reference +0.049 (-0.092 to +0.192), FanGraphs -0.085 (-0.228
  to +0.055), Statcast +0.118 (-0.029 to +0.263). v3 is below zero in 7 of 11 held-out seasons.
- The shapes alone (every level at 0) against zero: +0.036 (-0.057 to +0.134). The offense ladder
  alone minus v3: +0.268 (+0.188 to +0.350). v1 refit minus zero: +0.400 (+0.232 to +0.565).
- v2's A2 predictor: zero minus v3 +0.002 (-0.119 to +0.119); v1 minus v3 +0.493.
- The v2 vector as read scores MAE 6.435 (zero minus it +0.083, CI95 +0.034 to +0.132), but it is
  one fixed vector fit on every season, the held-out ones included, so it is not a held-out result.
- Simulation: the five seeds spread widely (2B 0.53 to 1.49, 3B 0.58 to 1.37, LF 0.35 to 0.88, RF
  0.58 to 1.15): on the real design the movers inside a group (151 infield and 243 outfield
  players whose share at a position ranges by 0.25 or more) are too few to pin a gap to a fifth of
  its size. Selection stress 0.90, 1.03, 0.77, 0.88; familiarity stress 0.83, 0.88, 0.70, 0.84.
  Power: on seed 7 the scoring separates the planted ladder from zero by +0.191 (CI95 +0.060 to
  +0.323), so the test can see a ladder of the FanGraphs table's spread when it is there.

**The candidate as fit on 2016-2026** (recorded, not served; runs per 650 PA on the exposure-
weighted zero; CI95 from 400 player-cluster refits of the whole pipeline, the anchor included):

| Pos | v3 | CI95 | v1 served | offense anchor | FG table |
| --- | ---: | --- | ---: | ---: | ---: |
| C | +10.37 | +9.77 to +11.01 | +10.88 | +5.14 | +12.44 |
| SS | +4.61 | +2.49 to +6.83 | +9.38 | +5.89 | +8.06 |
| 2B | +0.90 | -1.10 to +2.96 | +5.12 | +4.53 | +3.67 |
| 3B | +0.22 | -1.90 to +2.33 | +3.62 | -2.56 | +3.67 |
| CF | +4.20 | +2.14 to +6.05 | +4.14 | +4.61 | +3.67 |
| LF | -3.81 | -5.98 to -1.86 | -6.39 | -0.61 | -5.09 |
| RF | -3.26 | -5.49 to -1.28 | -6.52 | -4.86 | -5.09 |
| 1B | -5.93 | -9.65 to -3.13 | -8.40 | -5.26 | -9.47 |
| DH | -8.44 | -15.05 to -2.18 | -13.70 | -7.77 | -13.85 |

- Gaps inside the groups: 2B to SS -3.71, 3B to SS -4.40 (v1 -4.26, -5.76); LF to CF -8.02, RF to
  CF -7.46 (v1 -10.53, -10.66). Anchored: 1B to SS -10.54; infield level minus outfield level
  +2.87.
- The three sources now agree on the shape inside each group (exposure-weighted zero within the
  group): infield SS +2.84 / +2.29 / +2.86, 2B -2.25 / -0.94 / -0.75, 3B -0.46 / -1.22 / -1.94;
  outfield CF +6.24 / +4.15 / +5.37, LF -3.77 / -2.85 / -2.64, RF -2.27 / -1.18 / -2.55
  (Baseball-Reference / FanGraphs / Statcast centred).
- Statcast league rates before centring, runs per 1,277.7 innings: CF +4.30, LF -3.14, RF -1.63,
  1B -0.93, SS +0.57, 2B +0.21, 3B -0.09.

**Reading.** Measured inside a group on the same players, with the player's own level held fixed,
shortstop and centre field are the hard spots and every source agrees, with gaps 0.70 to 0.87
times v1's. That is a shape, not a ladder this test can certify: the held-out scoring does
not separate it from an all-zero fielding ladder, v1 shrunk to a quarter or a half scores lower,
and the real design is too thin to recover a planted left-field gap to the registered tolerance.
The same-season Statcast pairs, the rows that see a within-group gap most directly, favour v3
clearly; the across-season rows, seven in ten of the scored rows, do not.

**What changes.** Nothing served moves. Position Fit values with v1 on one run scale, as since
LADDER_V2_REVERT. The registry gains `positional_ladder_v3` (not adopted), the Library's
Positional Ladder view prints this re-read, and no ladder artifact or standalone page is
published.

## 10. Amendments

### 2026-10-15, A1 and A2, before the read

Made after the fixture dry run (`tools/ladder_v3_lab.py --dry-run` on ladder_v2_lab's fixtures)
and before any fit or score on real data: no real fielding run has been fitted or scored, and no
simulation has been run on the real design. The probes are in the task's output directory.

- **A1. Part 1 (a), the within-group fit.** The registered persistence form attenuates the gaps.
  On the part 6 construction over the fixture design (no selection), seeds 7, 8 and 9, its
  recovery ratios were 2B 0.80 / 0.83 / 0.53, 3B 0.45 / 0.86 / 0.62, LF 1.09 / 0.81 / 1.01, RF
  0.82 / 0.85 / 0.73, and on the native fixture (moves after bad years) 0.66, 0.80, 0.73, 0.65.
  The cause: the form centres a player's glove on the rung of the position he played last season
  and shrinks his deviation from it by the persistence (k1 + k2 about 0.6 on the fixtures), so when
  his own level differs from that position's average (a career shortstop who played second base
  last season) the true part of his deviation is shrunk as well, and the gap reads at about the
  persistence times its size. Replaced by the player fixed-effects form, which conditions on the
  player's own level over every season of the fit (the multi-season player type of item 4):
  `r_{m,t} = a_m + beta (age_t - 27) + sum_{p in G} s_{t,p} D_p + e` over the player-seasons with
  at least 150 innings rated by S and at least 95% of them in G (shares renormalised over G), age
  present, players with at least two such seasons in the fit's seasons; weight innings / 1,000;
  solved by within-player weighted demeaning; plus the Statcast same-season pairs inside G as
  registered; the identification row, the shapes and the pooling unchanged. A fold drops the
  held-out season's rows. Same fixtures: ratios 2B 1.05 / 0.90 / 1.06, 3B 1.03 / 1.04 / 1.44, LF
  1.47 / 0.89 / 0.99, RF 0.96 / 0.89 / 0.81; native fixture 0.96, 1.24, 1.04, 0.93. The dry run's
  two-seed means: 1.02, 0.99, 1.20, 0.98; under the selection stress 1.02, 1.00, 1.19, 0.98; under
  the familiarity stress 0.84, 0.92, 1.09, 0.89. Part 8's "alternation round counts" become each
  fit's player and mover counts.
- **A2. Recorded, no change: the scoring's preference.** On the fixtures both the part 4
  predictor and v2's A2 predictor score 0.75 x a planted ladder slightly better than 1.0 x on the
  across-season rows (native fixture, part 4 predictor: 4.430 against 4.444; part 6 construction
  on the fixture design: 6.749 against 6.798), and 0 x worst (4.903, 7.225). The test separates a
  ladder from no ladder, with a mild lean toward compression that works against any candidate; it
  stays as registered.

Nothing else changes: the anchor, C, the comparators, the scoring, the simulation, the pass rule
and the seeds stand as registered.
