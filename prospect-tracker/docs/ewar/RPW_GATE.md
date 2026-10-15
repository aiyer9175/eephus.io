# Runs per win fitted from team outcomes (rpw_fit_v1)

Task EWAR_RPW_FIT (owner decision EW3-24, 2026-10-15, verbatim "Yes, queue that"). This document
is committed ALONE, before any number of its estimand is computed. It fixes the candidates, the
data, the frame, the estimand, the bootstrap, the pass rule, the refusals and the output. A change
to any of them after the first number is a dated amendment under part 11, never an edit. Its pin
test is `test_rpw_gate_registration.py`.

## 0. What it decides

- **The conversion in question.** eWAR v3 divides its runs by `RPW_s =
  league_constants.league_totals(s)["rpw"]` (`docs/ebr-2026-09-30/EBR_GATE.md` part 9.2), the
  FanGraphs closed form `9 x (R / IP) x 1.5 + 3` on the season's league totals
  (`league_constants.py`, in `league_totals()` at `"rpw":`): 2016 9.78, 2017 10.05, 2018 9.71,
  2019 10.30, 2020 10.28, 2021 9.97, 2022 9.52, 2023 10.03, 2024 9.68, 2025 9.77, 2026 9.82. It is
  the INCUMBENT. Nothing in the repository fits a runs-per-win from game outcomes: `ewar.py`
  `runs_per_win()` recovers Baseball-Reference's conversion per team-season from its published
  runs and wins above average (8.0 to 11.2, fallback 9.7), and `fwar_frame.py` `dynamic_rpw()` is
  FanGraphs' per-pitcher form. Neither is fitted on wins.
- **The decision.** Whether a conversion fitted on team outcomes replaces the incumbent in eWAR v3
  (part 9.2's `RPW_s`). Only eWAR v3 can change. The FanGraphs replica (`fwar_frame.py`) keeps
  FanGraphs' own conversion because its job is to reproduce published fWAR; eWAR v2 keeps
  Baseball-Reference's recovered values; `league_constants` is not edited.
- **Nothing served moves.** The artifact is `data/rpw_fit.json`; no page reads it. The registry row
  `rpw_fit` is provisional, `measurement_only`, until a candidate is admitted. The consumer is task
  EWAR_V3_ASSEMBLE, which reads the admitted candidate's per-season values or, if none is admitted,
  keeps the incumbent.

## 1. Data (read from caches, never fetched by this task)

- **Team-seasons.** `.cache/statsapi_standings_<Y>.json` (MLB regular-season standings): per club
  `wins`, `losses`, `runsScored`, `runsAllowed`. Games G = wins + losses. Run differential RD = RS -
  RA. The club code comes from the StatsAPI team id through `.cache/team_stats/<Y>_pit.json`.
- **Primary frame.** Seasons 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026: ten seasons,
  30 clubs each, 300 team-seasons. 2026's regular season is complete (every club has 161 or 162
  decisions in the cache, last updated 2026-10-13).
- **2020 is excluded from the primary frame** (60 games, seven-inning doubleheaders, a runner placed
  on second base in extra innings). It is reported as a sensitivity: each candidate fitted on all
  ten primary seasons predicts 2020's 30 clubs; MAE in wins and MAE scaled to 162 games are printed;
  it decides nothing.
- **League constants.** `league_constants.league_totals(s)`: `rpw` (the incumbent) and `lg_ra9`.
- **Park.** FanGraphs Guts `Basic (5yr)` per club from `.cache/fangraphs/park_factors_<Y>.json`,
  divided by 100. A season whose file is not marked complete reads the latest complete earlier
  season (the rule of `team_projection.park_factors`); at this commit 2026 reads 2025.
- **Baseball-Reference.** `.cache/war_daily/bat.parquet` and `.cache/war_daily/pit.parquet` as
  cached; their sha256 and modification times are printed before any statistic. Club code ATH and
  OAK are the same franchise.
- **Pitcher stints** (part 5 only): `pit.parquet` rows with `year_ID`, `team_ID`, `mlb_ID`, `G`,
  `IPouts` and `RA`.

## 2. The candidates

Every linear candidate predicts a club's wins from its run differential as

```
W_hat_i = G_i / 2 + RD_i / RPW_i
```

- **(a) The FanGraphs closed form, the incumbent.** RPW_i = `league_totals(s)["rpw"]` for the
  club's season. Nothing is fitted.
- **(b) Pythagenpat with a fitted exponent.**

```
W_hat_i = G_i * RS_i^x / (RS_i^x + RA_i^x),     x = ((RS_i + RA_i) / G_i)^z
```

  z minimizes the sum of squared wins errors over the training seasons, by a grid over 0.1000 to
  0.5000 in steps of 0.0005 (a tie takes the smaller z). Reported beside: the implied marginal runs
  per win at each club's run environment, 2 / (W(RS + 0.5, RA - 0.5) - W(RS - 0.5, RA + 0.5)), and
  at the league environment, 2 x L_s^(1 - z), where L_s is part 2(d)'s league runs per game.
- **(c) The linear slope of wins on run differential.** W_i - G_i / 2 = beta x RD_i, ordinary least
  squares through the origin on the training seasons; RPW = 1 / beta, one value for every club. The
  slope fitted on each season alone (all eleven seasons, 2020 included) is reported beside and
  decides nothing: a held-out season's own slope needs that season's wins.
- **(d) A run-environment model.**

```
W_i - G_i / 2 = RD_i * (b0 + b1 (L_s - 9) + b2 (T_i - L_s) + b3 (PF_i - 1))
L_s = 2 * sum_i RS_i / sum_i G_i     league runs per game, both clubs
T_i = (RS_i + RA_i) / G_i            the club's runs per game, both clubs
PF_i = the club's park factor (part 1)
RPW_i = 1 / (b0 + b1 (L_s - 9) + b2 (T_i - L_s) + b3 (PF_i - 1))
```

  Ordinary least squares with no intercept on the four columns RD, RD (L - 9), RD (T - L) and
  RD (PF - 1). At the league environment RPW_s = 1 / (b0 + b1 (L_s - 9)).
- **(e) Baseball-Reference's recovered values.** `ewar.runs_per_win(bat, pit)` on the cached
  frames: the club's team-season value, else its season value, else 9.7. Nothing is fitted on wins.
- **Reference rows (deciding nothing).** (r0) no run differential: W_hat = G / 2. (r1) Pythagenpat
  at the repository's fixed exponent 0.287 (`team_projection.PYTHAGENPAT_EXP`).
- A linear candidate whose RPW_i is not finite and positive for some held-out club is VOID: it
  is reported and cannot pass.

## 3. The estimand

- **Leave one season out.** For each held-out season h of the ten primary seasons, candidates (b),
  (c) and (d) are fitted on the other nine and predict h's 30 clubs. (a), (e), (r0) and (r1) fit
  nothing, so their held-out predictions are their only predictions.
- **Error.** e_i = W_hat_i - W_i in wins, one per team-season, 300 per candidate.
- **Statistics.** MAE (the mean absolute error, deciding) and RMSE (reported), in wins, over the 300
  team-seasons, and per season. Player-free: only club totals enter.
- **Contrast.** dMAE_c = MAE(a) - MAE(c); positive means candidate c predicted wins more closely
  than the incumbent.

## 4. The bootstrap and the pass rule

- **Paired bootstrap over team-seasons.** One index matrix, `numpy.random.default_rng(20261025)
  .integers(0, 300, size=(2000, 300))`, drawn once, B = 2000, seed 20261025, used for every
  contrast in the order (b), (c), (d), (e), then part 5. Each draw recomputes dMAE on the drawn
  rows of the held-out errors; the fits are not redone inside the bootstrap. Printed per contrast:
  the point dMAE, the bootstrap sd, lo95 (the 5th percentile, numpy's linear rule) and hi95 (the
  95th percentile).
- **PRIMARY PASS** when lo95 of dMAE_c is above 0. No multiplicity correction applies: the owner's
  rule names one lower bound per candidate. A Holm read over the four challengers (bootstrap p =
  the share of draws with dMAE at or below 0) is printed beside and decides nothing.
- **More than one PRIMARY PASS.** The candidate with the largest point dMAE is the one carried
  forward; a tie takes the earlier letter.
- **The team guard (EW3-23).** A candidate that passes is admitted to eWAR v3 only if it is also
  NON-INFERIOR on the team guard of `EBR_GATE.md` 11.2.4 for run differential and wins, with v_i(Y)
  the eWAR v3 frame value carrying the candidate's per-season RPW in place of the incumbent's. That
  guard relates roster WAR sums to next-season club outcomes, which 11.2.4 places inside the skill
  look's record (`EBR_GATE.md` part 12.2), under its own bootstraps and seed 20261024. This task does
  not compute it. A candidate that passes here is recorded PRIMARY PASS, GUARD PENDING, and
  EWAR_V3_ASSEMBLE (or the skill look's run, whichever comes first) computes the guard once; only on
  NON-INFERIOR does it replace the incumbent. If no candidate passes, the record is INCUMBENT
  HOLDS and no guard runs for this task.
- **What an admitted candidate supplies.** Its league-environment RPW for every season 2016 to 2026,
  2020 included, from its fit on all ten primary seasons: (b) 2 x L_s^(1 - z); (c) 1 / beta; (d)
  1 / (b0 + b1 (L_s - 9)); (e) Baseball-Reference's season value. eWAR v3 reads that value where
  part 9.2 reads `league_totals(s)["rpw"]`. A season after 2026 is computed from its own L_s by the
  same frozen parameters ((e) has no rule for a season Baseball-Reference has not published, so (e)
  cannot be admitted for a future season).

## 5. The pitcher leg: does a per-pitcher conversion beat a league constant? (reported)

- **The question** (EW3-24): converting pitching runs, does FanGraphs' per-pitcher dynamic form beat
  one league constant, on the same outcome (club wins)?
- **Pitching runs per stint.** P_j = lg_ra9_s x IP_j / 9 - RA_j, IP_j = IPouts_j / 3, over every
  pitching stint of the club-season (position players who pitched included). Offense runs O_i =
  RS_i - lg_ra9_s x (sum of the club's IP_j) / 9, so that O_i + sum_j P_j = RD_i exactly.
- **Arm L (league constant).** W_hat_i = G_i / 2 + (O_i + sum_j P_j) / RPW_s. It equals candidate (a)
  identically (refusing beyond 1e-9 wins).
- **Arm D (dynamic).** W_hat_i = G_i / 2 + O_i / RPW_s + sum_j P_j / dRPW_p, with the FanGraphs form
  of `fwar_frame.dynamic_rpw()` evaluated on runs allowed, on the pitcher's season totals over all
  his stints (ipg = IP / G, RA9 = 9 RA / IP):

```
dRPW_p = (((18 - ipg_p) * lg_ra9_s + 9 * RA_p / G_p) / 18 + 2) * 1.5
```

  `9 * RA_p / G_p` is ipg_p x RA9_p written so that a pitcher with no outs has a finite value. RA9
  stands where FanGraphs puts FIPR9 because the outcome is wins from actual runs.
- **Statistic.** dMAE = MAE(L) - MAE(D) on the same 300 team-seasons with the same index matrix (part
  4). The record says "beats" when lo95 is above 0, "does worse" when hi95 is below 0, and "does not
  separate" otherwise. Nothing is fitted, so leave-one-season-out does not apply.
- **What it licenses.** A reported finding for EWAR_V3_ASSEMBLE and the pitching-basis registration
  (EWAR_PITCH_BASIS). It changes no conversion by itself.

## 6. Refusals (nothing is written)

1. A season without exactly 30 clubs, or whose league runs scored differ from its runs allowed, or
   whose wins differ from its losses.
2. A club-season whose Baseball-Reference stint runs allowed do not sum exactly to the standings'
   runs allowed (part 5's ledger).
3. Arm L differing from candidate (a) by more than 1e-9 wins on any club.
4. A non-finite prediction from (a), (b), (e), (r0) or (r1).

## 7. Output, version, registry

- `data/rpw_fit.json`: `rpw_fit_version` (`rpw_fit_v1`), `generated_at`, this document's path,
  the input digests (standings, war_daily, park files), the frame, per candidate the held-out MAE
  and RMSE (pooled and per season), the full-fit parameters and league-environment RPW per season,
  the contrasts and their bootstrap figures, the Holm read, the 2020 sensitivity, the reference
  rows, part 5's arms and contrast, and the verdict: INCUMBENT HOLDS, or PRIMARY PASS, GUARD PENDING
  with the candidate named and its `rpw_by_season`.
- Built by `python tools/build_rpw_fit.py`; pure core `rpw_fit.py` (no network, no writes), tested by
  `test_rpw_fit.py` on fixtures.
- Registry row `rpw_fit`: provisional, `measurement_only`, eval_artifact `data/rpw_fit.json`, until
  EWAR_V3_ASSEMBLE admits a candidate.

## 8. Registered expectations (predictions from priors, not measurements)

- Every linear candidate lands within about 0.1 wins of the incumbent's MAE, and no lo95 is above 0:
  the incumbent already tracks the run environment, and ten seasons of league run levels between
  roughly 8.7 and 9.7 runs per game give a fitted environment term little to work with.
- (e) does worse than (a): its per-club values carry the rounding of published WAA.
- Part 5: arm D does not separate from arm L.

## 9. What it is not

- No player value is published. No FV-cell statistic, no betting column, no projections input, no
  next-season statistic of any player.
- It does not edit `league_constants`, `fwar_frame`, `ewar` or any served artifact.

## 10. Disclosure: what was read before this registration

- The incumbent's per-season values (part 0), which the owner's ask quoted.
- Data shape only: each season 2016 to 2026 has 30 clubs in the standings cache; 2020's clubs played
  58 to 60 games and every other season's 161 to 163; league runs scored equal runs allowed and wins
  equal losses in every season; the Baseball-Reference stint runs allowed sum exactly to each club's
  standings runs allowed in all eleven seasons; FanGraphs' park-factor files are complete for 2016 to
  2025 and not for 2026.
- No predicted wins, error, slope, exponent, correlation or contrast of any candidate was computed.

## 11. Amendments

A dated amendment, committed alone before the first build, may fix a definition defect that a
refusal of part 6 exposes, stating the defect, its evidence and the fix, chosen without reference to
any error or contrast. The frame, the estimand, the bootstrap, the seed, the pass rule and the team
guard never change. After the first build nothing above part 12 changes.

## 12. Results

### 12.1 Build 1, 2026-10-15: PRIMARY PASS, GUARD PENDING (candidate (c))

Run once by `python tools/build_rpw_fit.py` on the commit after the registration (5d6f592b); the
log is kept in the lane's output directory. No refusal fired: 30 clubs and balanced runs and wins in
all eleven seasons; Baseball-Reference stint runs allowed reconcile with the standings on all 300
primary club-seasons; arm L equals candidate (a) to 2.8e-14 wins; no candidate was VOID and no
Baseball-Reference club fell back to a season value. war_daily pit sha256 3279bfbdc5bc, bat
e9571c428cb4 (both cached 2026-10-15 19:33 UTC). 2026 read the 2025 park-factor file.

Held-out (leave one season out) errors over the 300 team-seasons, in wins:

| Candidate | MAE | RMSE | dMAE vs (a) | sd | lo95 | hi95 | bootstrap p | Disposition |
|---|---|---|---|---|---|---|---|---|
| (a) closed form, incumbent | 3.2976 | 4.2528 | | | | | | incumbent |
| (b) Pythagenpat, z fitted | 3.2113 | 4.1775 | +0.0863 | 0.0562 | -0.0014 | +0.1810 | 0.0540 | no pass |
| (c) slope of wins on RD | 3.1968 | 4.1578 | +0.1008 | 0.0551 | +0.0135 | +0.1910 | 0.0300 | PRIMARY PASS |
| (d) run environment | 3.2767 | 4.2387 | +0.0209 | 0.0634 | -0.0782 | +0.1267 | 0.3615 | no pass |
| (e) Baseball-Reference recovered | 3.3354 | 4.3055 | -0.0379 | 0.0226 | -0.0749 | -0.0007 | 0.9535 | no pass (worse) |
| (r0) G / 2, reference | 10.3867 | 12.9134 | | | | | | reference |
| (r1) Pythagenpat 0.287, reference | 3.2980 | 4.2764 | | | | | | reference |

- **Verdict: PRIMARY PASS, GUARD PENDING, candidate (c).** Only (c) has lo95 above 0. Its fit on all
  ten primary seasons is beta 0.094108 wins per run, RPW 10.6261 for every season (held-out fits
  10.5293 to 10.7133). Against the incumbent's 9.52 to 10.30 it sets 0.33 to 1.10 more runs per
  win. It replaces `league_totals(s)["rpw"]` in eWAR v3 part 9.2 only if the team guard
  of `EBR_GATE.md` 11.2.4 reads NON-INFERIOR (EWAR_V3_ASSEMBLE or the skill look); until then the
  incumbent stands and nothing served moves.
- **Holm, reported and deciding nothing:** the four bootstrap p values (c 0.030, b 0.054, d 0.3615,
  e 0.9535) reject nothing at 0.05 (c's Holm threshold is 0.0125). Under a multiplicity correction
  no candidate would pass.
- **Fitted parameters, all ten seasons:** (b) z 0.251 (held-out 0.2445 to 0.2545; league-environment
  RPW 9.99 to 10.94); (d) b0 0.094554, b1 -0.001725, b2 -0.002491, b3 -0.003428 (league-environment
  RPW 10.49 to 10.71). Per-season slopes of wins on RD alone (reported): RPW 9.97 (2024) to 11.69
  (2025).
- **2020 sensitivity (deciding nothing),** MAE per 162 games: (a) 4.66, (b) 4.40, (c) 4.62, (d) 4.54,
  (e) 4.65, (r1) 4.42.
- **Part 5, the pitcher leg:** arm L (league constant) MAE 3.2976, arm D (FanGraphs' per-pitcher form
  on runs allowed) 3.3564 over 9,496 pitching stints; dMAE L - D -0.0588, sd 0.0552, lo95 -0.1486,
  hi95 +0.0318. The per-pitcher form does not separate from the league constant (its point estimate
  is worse; its RMSE is worse with dRMSE hi95 -0.0049).
- **Against the registered expectations (part 8):** the first was wrong for (c), which passed; (e) did
  worse than (a), as expected; part 5 did not separate, as expected.
