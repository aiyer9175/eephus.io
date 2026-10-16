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

**(a) Within-group shapes from switchers.** Two groups: the infield IF3 = {2B, 3B, SS} and the
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

(empty until the read)

## 10. Amendments

(none)
