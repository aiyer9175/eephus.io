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

EMPTY AT REGISTRATION.
