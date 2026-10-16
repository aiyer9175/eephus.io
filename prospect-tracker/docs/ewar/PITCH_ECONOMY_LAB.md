# Pitch economy: the descriptive lab and the decomposition (pitch_economy_lab_v1)

Task EWAR_T1_PITCH_ECON (owner asks EW3-16 and EW3-18, 2026-10-15: the run value of seeing extra
pitches and of pitch efficiency, as a WAR input and inside HEM+, SEM+ and REM+; owner answer EW3-19:
register both a hitter and a pitcher part for the eWAR v3 skill look). This document is committed
ALONE, with the eWAR v3 amendment `docs/ebr-2026-09-30/EBR_GATE.md` part 11.3, before any number of
its estimands is computed. It fixes the data, the frames, the statistics, the decomposition, the fit
of the frozen constants the pitch-economy parts PE-P and PE-H read, and the trigger for the owner's
question about pitch counts inside HEM+, SEM+ and REM+. A change after the first number is a dated
note in part 10 that says what changed and why, never an edit above it. Its pin test is
`test_pitch_economy_registration.py`.

STATUS: REGISTERED, RESULTS EMPTY.

## 0. What it is

- **Measurement only.** The lab decides nothing about eWAR: PE-P and PE-H are admitted or not by
  the eWAR v3 skill look under part 11.3 of the eWAR v3 gate, never by this lab. Nothing served
  moves: the outputs are `data/_labs/pitch_economy_partials.json` and
  `data/_labs/pitch_economy_constants.json` (`data/_labs/` ships in neither deploy consumer), and no
  page, registry row, glossary entry or exporter reads them.
- **Three products.** (1) Step 1 of the owner's ask: raw and partial correlations of pitch rates
  with run value, hitters and pitchers, and the team-game read (parts 3 to 5). (2) Step 2: the
  decomposition of pitch economy into count lift, starter wear and the bullpen cost of
  efficiency, same season only (part 6). (3) The frozen constants of PE-P and PE-H (part 7). Part 8
  decides, from step 1 alone, whether the owner's HEM+, SEM+ and REM+ question gets a test.
- **Tool:** `tools/pitch_economy_lab.py`, with `--dry-run` on a synthetic fixture with nulls before
  the run, and the pure module `pitch_economy.py` for the arithmetic PE-P and PE-H share with the
  later skill build. Tests: `test_pitch_economy.py` and `test_pitch_economy_lab.py`.

## 1. Data (read from caches; this task fetches nothing)

- **StatsAPI season lines:** `.cache/fa_statsapi_hitting_<Y>.json` and
  `.cache/fa_statsapi_pitching_<Y>.json`, one row per player-season (a traded player's row is his
  season total). Hitters: `numberOfPitches`, `plateAppearances`, walks, intentional walks, hit by
  pitch, strikeouts and the wOBA counts. Pitchers: `numberOfPitches`, `battersFaced`, `outs`, `runs`,
  `gamesPlayed`, `gamesStarted` and the FIP counts.
- **Start and relief split lines:** `.cache/pitch_rates/pitching_sprp_1_<Y>.json` (pitches,
  appearances, batters faced, outs and starts per role; stints summed per player).
- **Savant xwOBA:** `.cache/savant_mlb/expected_batter_<Y>.csv`, `est_woba` at Savant PA 100 or more,
  the source and floor the served xHEM+ column reads (`hitter_export._join_xhem_plus`).
- **League constants:** `league_constants.constants(Y)` (the solved wOBA weights, scale and league
  wOBA) and `league_constants.league_totals(Y)` (the FIP constant, runs per win).
- **The corpus:** `.cache/pbp_corpus` plays, pitches and events for 2018, 2019 and 2021 to 2025, and
  eBR's runner record `.cache/pbp_runners` (states and end states per play); RE288 and RE24 season
  tables from `data/count_value.json`.
- **The frozen fWAR vintage** `data/fwar_vintage.json`: pitchers' fWAR in Y+1, reported only.
- **2026 never enters.** No pair's outcome season is 2026 (the eWAR v3 skill holdout's outcome
  season stays unread), and no 2026 row is read.

## 2. Statistics

- **Correlation:** Spearman rho. **Partial correlation:** the Pearson r of the residuals of rank(x)
  and rank(y), each regressed by least squares (with intercept) on the ranks of the controls.
- **Intervals:** a player-clustered bootstrap (part 4: game-clustered), B = 2,000, seed 20261015,
  percentile 95 percent interval; every interval is pooled over the part's pairs, and the per-season
  point estimates are printed beside it.
- Each statistic prints its n (pairs or rows). A row missing a control is dropped from that
  statistic only, and the drop is counted.

## 3. Part A: hitters (step 1)

- **Pairs** (Y, Y+1) for Y in 2016, 2017, 2018, 2021, 2022, 2023, 2024; 2020 out on both sides;
  hitters with 300 or more PA in both seasons; pitcher-batters out.
- **In Y:** P/PA = pitches seen / PA; BB% = (walks - intentional walks) / PA; K% = strikeouts / PA;
  xwOBA (Savant); wOBA on the season's solved weights; wRAA = ((wOBA - lgwOBA) / scale) * PA. In Y+1:
  wOBA and wRAA the same way.
- **A1** raw Spearman of P/PA(Y) with wOBA(Y), wRAA(Y), wOBA(Y+1) and wRAA(Y+1).
- **A2** partial Spearman of P/PA(Y) with each of the four, after BB%(Y), K%(Y) and xwOBA(Y).
- **A2b** for the two Y+1 targets, also after wOBA(Y) (residual value beyond the hitter's own wOBA).
- **A3** Spearman of P/PA(Y) with BB%(Y), K%(Y) and xwOBA(Y) (the collinearity, made visible).

## 4. Part B: team-game (step 1)

- **Rows:** every regular-season game in the corpus seasons 2018, 2019 and 2021 to 2025, one row per
  batting side. The opposing starter is the first pitcher of the fielding half (owner decision O22);
  the opposing bullpen is every later pitcher of that side.
- **Quantities:** the lineup's same-game P/PA (pitches the side saw / its plate appearances); the
  lineup's prior P/PA (the PA-weighted mean, over the side's batters in the game, of each batter's
  previous-season P/PA shrunk as (pitches + 100 * L) / (PA + 100) with L the previous season's league
  P/PA); the opposing starter's outs; the opposing bullpen's outs; the opposing starter's
  previous-season pitches per out, shrunk with K_o = 120 toward that season's league starter value.
- **B1** Spearman of the same-game lineup P/PA with the starter's outs and with the bullpen's outs.
- **B2** Spearman of the lineup's prior P/PA with the same two, and the partial after the starter's
  prior pitches per out.
- No run, win, total, price, market, posted lineup or betting artifact is read; the rows relate a
  lineup's pitch rate to the opposing starter's length only. Intervals are game-clustered.

## 5. Part C: pitchers (step 1)

- **Pairs** as part A; pitchers with 50 or more IP in both seasons; position players who pitch out.
  Roles by Y: starters GS / G at or above 0.50, relievers GS / G at or below 0.10; each role read
  alone and pooled.
- **In Y:** P/BF = pitches / batters faced; P/IP = pitches / (outs / 3); K% and BB% per batter
  faced; the EM+ shrunk FIP of the role (`sem_plus.fip_skill` on the season's SEM+ pool for
  starters, `rem_plus.fip_skill` on the season's REM+ pool for relievers; a pooled row takes its
  role's, and a swingman is read only in the pooled block with the start-share blend's FIP, the
  shrink of part 9.4's S2); IP(Y); IP / GS(Y) for starters.
- **In Y+1:** RA9 = 9 * runs / IP; IP; IP / GS (starters with 5 or more starts in Y+1); published
  fWAR (reported only).
- **C1** raw Spearman of P/BF(Y) and of P/IP(Y) with each Y+1 quantity.
- **C2** the partials after K%(Y), BB%(Y) and the EM+ shrunk FIP(Y).
- **C2b** IP(Y+1) also after IP(Y); IP / GS(Y+1) also after IP / GS(Y); fWAR(Y+1) after the EM+
  shrunk FIP(Y) and IP(Y).
- **C3** Spearman of P/BF(Y) with K%(Y) and BB%(Y).

## 6. Part D: the decomposition (step 2; same season only)

- **D1, hitters** (corpus seasons 2018, 2019, 2021 to 2025). Per hitter-season, the quantities of
  part 11.3.3 of the eWAR v3 gate: CL (count lift), the class means CLbar and pbar, CLres, Pres
  against starters, starter wear W = w_s * Pres, and g_PEH and d_PEH on the frozen constants of part
  7. Printed: the class tables per season; the sd of each term in runs at 300 or more PA; the
  same-season Spearman and Pearson of CL per PA and of CLres per PA with wRAA per PA (count lift
  sits inside wOBA, its residual should not); the RE288 receipt (the share of plate appearances whose
  pitch-step values sum to their RE24 change within 1e-6, over the steps CL reads and the rest).
- **D2, pitchers** (seasons 2016 to 2019 and 2021 to 2025). The times-through-order table per corpus
  season (mean RE24 run value per plate appearance against starters by pass 1, 2, 3 and 4 or more,
  and the within starter-season decay of part 7); F_SP,s, F_RP,s, pi_s, T9_s and w_s per season; per
  pitcher-season the efficiency chain of part 11.3.2 (X~, G, c, g) and Delta_PE, same season; the
  sd and range of Delta_PE by role and season, the zero-sum receipts, and the ten largest movers of
  2024 and 2025 by |Delta_PE|.
- Part D reads no Y+1 quantity of any kind.

## 7. Part E: the frozen constants of PE-P and PE-H

- **delta_TTO.** Per starter-season in the 2018 and 2019 corpus seasons with 30 or more plate
  appearances at the third or later pass: (mean RE24 run value per plate appearance at the third and
  later passes) minus (his mean over every pass), where a plate appearance's run value is the runs
  scored on the play + RE24(end state) - RE24(start state) on the season's RE24 table, and a batter's
  pass is his nth plate appearance against that starter in the game. delta_TTO is the mean of those
  differences weighted by each starter-season's third-and-later plate appearances, pooled over the
  two seasons.
- **K_CL and K_P.** Over hitter-seasons in 2018 and 2019 with 200 or more counted plate appearances
  (for K_P: 150 or more against starters): the per-plate-appearance residual (CL_a - CLbar, and
  p_a - pbar against starters) averaged over the hitter's odd-numbered and even-numbered games in
  date order; rho_half = the Pearson of the two halves across hitters, pooled over both seasons;
  rho_full = 2 * rho_half / (1 + rho_half); K = nbar * (1 - rho_full) / rho_full with nbar the mean
  full-season count (counted plate appearances for K_CL, plate appearances against starters for K_P)
  among those hitters; K clamped to 50 to 20,000; rho_half at or below 0 sets K to infinity.
- Written once to `data/_labs/pitch_economy_constants.json` with their inputs (n, rho_half,
  rho_full, nbar) and frozen in `pitch_economy.py` in the same commit as the lab's result; the eWAR
  v3 skill look reads them and refits nothing.

## 8. Part F: the trigger for the owner's HEM+, SEM+ and REM+ question

- **The question** (owner ask EW3-16): should P/PA go into HEM+, or P/IP into SEM+ and REM+? HEM+ was
  deprecated on 2026-10-15 (it lost to xwOBA), so a hitter test baselines on xHEM+ or xwOBA, never on
  HEM+.
- **Residual value is shown** when any of these 95 percent intervals, pooled, excludes 0:
  - (h) part A2: the partial Spearman of P/PA(Y) with wOBA(Y+1) after BB%, K% and xwOBA(Y);
  - (s) part C2, starters: the partial Spearman of P/BF(Y) with RA9(Y+1) after K%, BB% and the SEM+
    shrunk FIP(Y);
  - (r) part C2, relievers: the same with the REM+ shrunk FIP(Y).
- **If (h):** the xHEM+ shrink-target test (the X-R1 construction: shrunk P/PA sets the unintentional
  walk rate's shrink target in a frozen-constant xHEM+ variant; Savant PA 200 or more in both
  seasons, 2016 to 2025 without 2020, forward on wOBA(Y+1); convention v2 of `tools/plus_lab_harness.py`;
  a permuted P/PA twin must fail) is registered in its own document, committed alone before its one
  run. **If (s) or (r):** the SEM+ or REM+ variant (shrunk P/BF as the prior of the strikeout and
  walk shrinks, forward on -RA9(Y+1), the role's own frame) likewise. Validated means lo95 above 0
  under both v1 and v2 after Holm over the tests registered; MDE95 is reported.
- **If none:** the record says no residual value was shown and no test is run; the answer to the
  owner's question is no, on this lab's numbers.

## 9. What it never does

- It computes no year-to-year, forward or split-half statistic of Delta_PE or d_PEH; the one
  split-half statistic it computes is part 7's, on the 2018 and 2019 seasons, for the constants.
- It reads no consensus FV, prospect list or FV cell (`docs/PROSPECT_ANCHOR_GATE.md`), no betting
  artifact, dark column, price, market capture or game result, and no 2026 row.
- It writes nothing under `data/` except the two `data/_labs/` files, and nothing under `docs/`
  except part 10 of this document.
- It runs once. A defect found after the run is stated in a dated note in part 10, the corrected run
  is written beside the first, and parts 7 and 8 read the corrected run.

## 10. Results

### 2026-10-15: the run (`python -u tools/pitch_economy_lab.py --run`, at e05e51ed)

**Note on the first run (dated 2026-10-15, under part 9).** The first run read the runner record's
empty bases, which the record stores as pandas' NA, as occupied in the corpus walk. Its RE288
telescoping receipt held on 0.2546 to 0.2577 of plate appearances in every corpus season, which is
how the defect was found; no other number of that run was read before the fix. Parts A, B, C and F
never read the walk's base states and are identical in both runs. Part D, delta_TTO (0.0305 in the
first run) and K_CL (171.71) were wrong; K_P (110.95) was not affected. The fix: `_missing()` in the
walk, a pandas NA regression in `test_pitch_economy_lab.py`, and a run guard that refuses to write
unless the RE288 identity holds on 0.999 of plate appearances in every season. The first run's
outputs stay beside the corrected ones (`data/_labs/pitch_economy_partials_run1.json`,
`data/_labs/pitch_economy_constants_run1.json`). The corrected run's identity receipt is 1.0 in all
seven corpus seasons, and parts 7 and 8 read the corrected run. Bootstrap B = 2,000, seed 20261015,
percentile intervals.

**Part A, hitters** (1,415 pairs, 538 hitters, 187 to 219 pairs per predictor season; every pair
has a Savant xwOBA).

| Statistic | P/PA(Y) against | Point | 95 percent interval |
|---|---|---|---|
| A1 raw | wOBA(Y) | +0.2004 | +0.1360 to +0.2644 |
| A1 raw | wRAA(Y) | +0.2020 | +0.1371 to +0.2684 |
| A1 raw | wOBA(Y+1) | +0.1832 | +0.1198 to +0.2480 |
| A1 raw | wRAA(Y+1) | +0.1908 | +0.1267 to +0.2570 |
| A2 after BB%, K%, xwOBA | wOBA(Y) | +0.0224 | -0.0373 to +0.0808 |
| A2 after BB%, K%, xwOBA | wRAA(Y) | +0.0308 | -0.0303 to +0.0908 |
| A2 after BB%, K%, xwOBA | wOBA(Y+1) | +0.0563 | -0.0002 to +0.1161 |
| A2 after BB%, K%, xwOBA | wRAA(Y+1) | +0.0563 | -0.0021 to +0.1178 |
| A2b also after wOBA(Y) | wOBA(Y+1) | +0.0541 | -0.0018 to +0.1113 |
| A2b also after wOBA(Y) | wRAA(Y+1) | +0.0540 | -0.0034 to +0.1129 |
| A3 | BB% | +0.7044 | +0.6663 to +0.7396 |
| A3 | K% | +0.4025 | +0.3324 to +0.4646 |
| A3 | xwOBA | +0.2469 | +0.1767 to +0.3167 |

Raw P/PA tracks wOBA at about 0.2 because it is mostly the walk rate (0.70 with BB%). Once BB%, K%
and xwOBA are held, the same-season partial is near 0 and the next-season partial is +0.056 with an
interval whose lower end sits just below 0. By predictor season, the wOBA(Y+1) partial reads +0.030,
+0.073, +0.152, +0.083, +0.080, -0.057 and +0.014 (2016, 2017, 2018, 2021, 2022, 2023, 2024).

**Part B, team-game** (34,016 batting sides in 17,008 games, game-clustered).

| Statistic | Against | Point | 95 percent interval |
|---|---|---|---|
| B1 same-game lineup P/PA | starter outs | -0.2013 | -0.2116 to -0.1907 |
| B1 same-game lineup P/PA | bullpen outs | +0.1970 | +0.1866 to +0.2071 |
| B2 prior lineup P/PA | starter outs | -0.0650 | -0.0747 to -0.0543 |
| B2 prior lineup P/PA, after the starter's prior pitches per out | starter outs | -0.0565 | -0.0663 to -0.0457 |
| B2 prior lineup P/PA | bullpen outs | +0.0484 | +0.0373 to +0.0593 |
| B2 prior lineup P/PA, after the starter's prior pitches per out | bullpen outs | +0.0410 | +0.0298 to +0.0518 |

The same-game rows are mostly mechanical (pitches seen in the game are pitches the starter threw). A
lineup that saw more pitches the season before shortens the opposing starter by a small amount
(about -0.06). The starter-workload lab's T1 asked a different question (whether the lineup term
lowered the outs forecast's error) and gave it no credit; both readings stand.

**Part C, pitchers** (1,536 pairs, 654 pitchers; 900 starter pairs, 535 reliever pairs, swingmen in
the pooled block only). The rows that answer the ask:

| Block | Statistic | Point | 95 percent interval |
|---|---|---|---|
| starters | C1 P/BF, RA9(Y+1) | -0.1584 | -0.2261 to -0.0863 |
| starters | C1 P/IP, IP/GS(Y+1) | -0.2008 | -0.2686 to -0.1283 |
| starters | C2 P/BF, RA9(Y+1) | +0.0150 | -0.0516 to +0.0806 |
| starters | C2 P/IP, RA9(Y+1) | -0.0027 | -0.0695 to +0.0647 |
| starters | C2 P/IP, IP(Y+1) | -0.0821 | -0.1539 to -0.0150 |
| starters | C2 P/IP, IP/GS(Y+1) | -0.0729 | -0.1431 to -0.0008 |
| starters | C2 P/BF, IP/GS(Y+1) | -0.1078 | -0.1782 to -0.0349 |
| starters | C2b P/IP, IP/GS(Y+1) also after IP/GS(Y) | +0.0052 | -0.0658 to +0.0763 |
| starters | C2b P/IP, fWAR(Y+1) after the SEM+ FIP and IP(Y) | +0.0762 | +0.0126 to +0.1416 |
| relievers | C2 P/BF, RA9(Y+1) | +0.0772 | -0.0086 to +0.1657 |
| relievers | C2 P/IP, fWAR(Y+1) | +0.0943 | +0.0108 to +0.1775 |
| pooled | C2 P/BF, RA9(Y+1) | +0.0487 | -0.0047 to +0.0977 |
| pooled | C3 P/BF, K% | +0.5374 | +0.4871 to +0.5825 |
| pooled | C3 P/BF, BB% | +0.4376 | +0.3821 to +0.4902 |

Once K%, BB% and the EM+ shrunk FIP are held, pitch rates say nothing measurable about next-season
runs allowed. Efficiency speaks to length: a starter who needs fewer pitches per inning goes deeper
the next season (partial -0.073 on IP/GS), and that is his own length repeating (after IP/GS(Y) the
partial is +0.005). The positive partials on fWAR(Y+1) are reported, not interpreted. Every row of
the three blocks is in the artifact.

**Part D, the decomposition** (same season only).

- Count lift. The league mean count lift by terminal class (2024): walk +0.0979, strikeout -0.0471,
  hit by pitch -0.0224, out in play -0.0113, single -0.0122, double -0.0070, triple -0.0084, home
  run +0.0023 runs. Pitches per plate appearance against starters (2024): walk 5.87, strikeout 4.89,
  balls in play 3.27 to 3.47.
- Same season, at 300 or more PA: count lift per PA against wRAA per PA, Spearman 0.32 to 0.45 by
  season; the class residual per PA against wRAA per PA, 0.19 to 0.34. Conditioning on the terminal
  class removes part, not all, of count lift's overlap with wOBA (the registration expected the
  residual not to track wRAA; it does, more weakly).
- Sizes at 300 or more PA: the count-lift residual sd 2.6 to 3.1 runs, starter wear W sd 0.26 to
  0.34 runs, d_PEH sd 1.75 to 2.06 runs; d_PEH sums to 0 every season.
- Starter wear. w is -0.0046 to -0.0065 runs per pitch in every season 2018 to 2025: the league
  bullpen's FIP is below a starter's at his third time through the order, so a pitch a hitter makes
  the opposing starter throw costs his own side about 0.006 runs.
- Times through the order, mean RE24 run value per plate appearance against starters (2024): pass
  1 -0.0078, pass 2 +0.0024, pass 3 +0.0173 (pass 4 and later under 1,100 plate appearances a
  season and noisy). The within-starter-season decay reads 0.0112 to 0.0223 by season.
- PE-P, same season, 2016 to 2025: Delta_PE sd 0.29 to 0.39 runs for starters and 0.12 to 0.15
  runs for relievers; the largest single value is 3.5 runs (0.37 WAR); 0 to 1.6 percent of
  starters, under 0.3 percent of relievers and up to 4.0 percent of swingmen move 0.1 WAR or more,
  and none moves 0.5 WAR. Every
  season and role sums to 0 within 1e-9 runs. The shrink of pitches per out at K_O 120 moves few
  outs, as the registration expected.

**Part E, the frozen constants** (`data/_labs/pitch_economy_constants.json`; frozen in
`pitch_economy.py`): delta_TTO 0.01847965 runs per plate appearance (384 starter-seasons, 47,079
plate appearances at the third and later pass; T9 0.70 to 0.71 runs per nine); K_CL 236.41 plate
appearances (rho_half 0.484356 on 714 hitter-seasons, nbar 444.12); K_P 110.95 plate appearances
against starters (rho_half 0.561812 on 607 hitter-seasons, nbar 284.51).

**Part F, the trigger.** No item excludes 0: (h) +0.0563, interval -0.0002 to +0.1161; (s) +0.0150,
-0.0516 to +0.0806; (r) +0.0772, -0.0086 to +0.1657. No X-R1-style test is registered or run, and
the answer to the owner's question (P/PA into HEM+ or xHEM+, P/BF or P/IP into SEM+ or REM+) is no
on this lab's numbers. Item (h) is a near miss: its lower bound sits 0.0002 below 0, so it is
recorded as one, and the rule is applied as registered.

Nothing here is a forward statistic of PE-P or PE-H; the skill look scores them under the eWAR v3
gate's part 11.3.
