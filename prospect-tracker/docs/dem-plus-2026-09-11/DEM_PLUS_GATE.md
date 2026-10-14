# DEM+ (Defense Evaluation Metric +): pre-registration

Written 2026-09-11, BEFORE the lab exists and before any forward correlation of the
candidate or its shrink constants has been computed. Owner request of 2026-09-11: a
Defense leaderboard in the MLB Stats module with a new metric, named DEM+ to match
HEM+, REM+ and SEM+. Design lanes D1 to D4 of that request are the evidence behind
every choice below; this file fixes the choices so nothing is tuned after a look.

## 1. What DEM+ is

A sample-shrunk FIELDING RATE index on the `100 + 10z` ruler. 100 is the average
fielder in the pool (200 or more defensive innings that season); ten points is one
standard deviation of the pool's shrunk rates.

- **Input, one source.** FanGraphs' served fielding runs, read verbatim from MLB
  StatsAPI `stats=sabermetrics` (`fielding`), plus catcher framing recovered as the
  exact residual `rar - (batting + baseRunning + fielding + positional + wLeague +
  replacement)`. On 2025 that residual equals FanGraphs CFraming on 111 of 111
  catchers and is zero on all 654 non-catchers (lane D4 section 1.1). No OAA, no DRS,
  no SIS column enters the number. It is not a blend of anything.
- **Rate.** `(fielding + framing) * 1000 / defensive innings`, innings at C, 1B, 2B,
  3B, SS, LF, CF and RF from the StatsAPI season fielding feed. P and DH never enter.
- **Shrinkage.** `shrunk = (fielding + framing) * 1000 / (innings + k)`, with `k` the
  innings-weighted mean of the per-position constants over the positions played. The
  target of the shrink is zero, because FanGraphs zeroes fielding runs within each
  position and season.
- **Scale.** `raw = 100 + 10 * (shrunk - mu) / sd`, `mu` and `sd` the unweighted mean
  and sample sd of SHRUNK rates over the pool, so the served spread is the advertised
  one (the WAR/PA+ defect C3 lesson). Rounded to the nearest integer. No clamp.
- **Why not a ratio.** Fielding runs centre on zero and go negative; a ratio to the
  league average divides by zero. This is the WAR/PA+ convention, not the HEM+ one.
  A point of DEM+ is not a point of HEM+.
- **What does NOT move it.** The positional adjustment and innings are real value and
  ride as context columns (`pos_runs`, `def_runs`, `inn`). The two-number discipline
  of HEM+, REM+ and SEM+.

## 2. Shrink constants, fixed from a window the gate never scores

Per position, the rule of `positional_fit.fit_signal` applied to this series:
Pearson year-over-year r of the rate at a matched exposure, `k = hm_inn * (1 - r) / r`
with `hm_inn` the mean harmonic innings of the pairs and r clamped to [0.05, 0.95].

- **Unit.** A player-season whose innings at the position are at least 80 percent of
  his defensive innings (single-position rate, so the whole-season fielding total
  belongs to that position), 300 or more innings at the position in BOTH seasons.
- **Fit window.** Predictor seasons 2016, 2017, 2018 (outcomes 2017 to 2019). 2016 is
  the first season of the one Statcast frame FanGraphs made retroactive.
- **Fallback.** Fewer than 30 pairs at a position: that position keeps the
  `data/positional_fit.json` constant (range-only Savant FRP, which is FanGraphs'
  range basis).
- The constants are then FROZEN into `dem_plus.K_INN` before the gate window is read.

## 3. Gate X-D1 (primary)

- **Question.** Does season-Y DEM+ forecast season-Y+1 fielding rate better than the
  naive rate and a playing-time proxy, without losing to its own raw parent?
- **Predictor seasons.** 2021, 2022, 2023, 2024 (outcomes 2022 to 2025), all outside
  the constant-fit window. 2020 is excluded on both sides (60 games).
- **Floors.** 200 or more defensive innings in Y; 300 or more in Y+1.
- **Predictor.** `dem_plus_raw`, unrounded (harness v2 rule 2).
- **Target.** The published rate `(fielding + framing) * 1000 / innings` in Y+1.
- **Baselines.** The raw unshrunk rate in Y (the parent); fielding percentage in Y
  (`(PO + A) / (PO + A + E)` over the same positions, the AVG analogue); innings in Y
  (a playing-time proxy: good gloves play more).
- **Statistic.** Forward Spearman rho; gap = rho(DEM+) - rho(baseline); 2,000
  bootstrap replicates, seed 20260911. Convention v1 is primary (iid pairs, raw
  target); v2 (within-outcome-season z target, player-clustered season-stratified
  bootstrap) is emitted beside it and must agree in sign.
- **Zero-information twin.** DEM+ permuted across players within each predictor
  season, same seed family. It must FAIL the fielding-percentage clause; if it passes,
  the harness is broken and no clause is creditable.
- **PASS requires all of:** gap vs fielding percentage lo95 > 0; gap vs innings lo95 > 0;
  gap vs the raw parent lo95 >= -0.01 (the HEM+ parent rule); the twin fails.
- **Sensitivity, reported, never used to choose.** Predictor seasons 2016 to 2019
  (inside the constant-fit window, so labelled in-sample); non-catchers only;
  predictor floor 300.

## 4. Gate X-D2 (3-year companion)

Innings-weighted mean DEM+ over Y-2..Y against one-season DEM+ on the same pairs
(2 or more seasons and 1,000 or more innings in the window). PASS: 3-year rho greater
than 1-year rho and gap lo95 >= 0. Otherwise the 3-year column ships MARGINAL.

## 5. What the gate does not decide

- **Display** ships either way. A failing gate restricts the copy to "a sample-shrunk
  fielding rating on FanGraphs' published series" with no forecast claim, and the
  registry row reads provisional.
- **Consumers.** No model reads DEM+ in this program. Betting needs its own section in
  docs/diamond-betting.md written before any capture, and Team DEM+ carries framing,
  so nothing relates it to game outcomes before the `catch_frame_rate` read (5d-D).
  Projections read runs, never an index, through the F04-01 repair lane. eWAR stays on
  `fielding_blend_w = 0.0`; this verdict is inadmissible for any eWAR fielding weight
  (do-not-reopen 16). eFV never (do-not-reopen 17).
- **Claim frame.** DEM+ is a steadier read of FanGraphs' published fielding series. It
  is not "better defense than fWAR"; framing inside the catcher number is parity with
  fWAR, not an improvement.

## 6. Accountability

`tools/dem_plus_lab.py` writes `data/dem_plus_eval.json` and
`data/dem_plus_multiyear_eval.json`; registry rows `dem_plus` and `dem_plus_3yr`.
The constants fit writes its own block into `data/dem_plus_eval.json` under
`k_fit` so the frozen values are reviewable beside the verdict they fed.

## 7. Disclosure, added 2026-09-11 after the first and only run

Written after the lab ran, so nothing here is a pre-registered change; it records
what was known before the registration and what happened once.

- **A partial look at the parent before registration.** About twelve minutes before
  this file was committed, a design lane computed the year-over-year persistence of
  the candidate's raw PARENT on the gate window: served fielding runs per 600 PA,
  r 0.474 on 800 pairs 2021-2025 (PA 300+ both years; 0.476 on 729 non-catcher
  pairs), and Baseball-Reference `runs_defense` persistence 0.436 on 2,416 pairs
  2011-2025. Different exposure unit and floor from X-D1, and nothing above was chosen
  from them (the constants come from 2016-2018, the floors from the HEM+ precedent).
  Within-season spreads by position were also computed; they relate no season to the
  next.
- **The run.** `tools/dem_plus_lab.py` ran once, on 2026-09-11. The refit on the
  constant window reproduced every frozen constant. X-D1 PASSED on every clause under
  both conventions and the permuted twin failed as required (numbers in
  `data/dem_plus_eval.json`). X-D2 did not clear its bar, so the 3-year column ships
  provisional. No floor, target, constant or estimator changed after the run.
- **Not added after the fact.** A design lane proposed report-only baselines (raw OAA
  and raw DRS rates) and catcher-only and non-catcher-only legs as amendments to be
  committed before the first run. The run came first, so they were not added as
  pre-registered legs. The non-catcher and floor-300 sensitivities in section 3 ran as
  written. If the OAA and DRS comparisons are ever run, they are post-hoc and must be
  labelled so.
- **Confirmatory holdout.** The 2025 to 2026 pairs run once, after 2026-11-15, and are
  reported beside the verdict, never merged into it.
- **Club-level framing is withheld** (`dem_plus.TEAM_ROLLUP_FRAMING = False`) until the
  betting program's `catch_frame_rate` read is recorded: Team DEM+ and the club run
  totals roll over non-catchers, while each catcher's own DEM+ keeps his framing. A
  display choice, not a change to the metric or the gate.

## 8. Confirmatory holdout, run 2026-10-14 (an OWNER-WAIVED EARLY READ; section 7 registered it for after 2026-11-15)

Run once by NOV15_REGATES under the owner's waiver of look days (EW3-5) and the logged
season-complete override treating 2026 as complete as of 2026-10-01 (EW3-6; the 2026 regular
season ended in late September and this lab reads regular-season fielding; the Nov 15 default
of `tools/plus_lab_harness.py` is unchanged and the override is written into the block):
`python tools/dem_plus_lab.py --holdout --season-complete-asof 2026:2026-10-01`, after a dry
run of the reporting path on fixtures with None values. X-D1's estimator, floors, baselines,
seed and permuted twin, unchanged, on the 2025 to 2026 pairs alone; written as the block
`confirmatory_holdout_2025_to_2026` of `data/dem_plus_eval.json` BESIDE the verdict, which is
untouched.

- 301 pairs. DEM+ rho 0.4082 against the raw rate 0.4045, fielding percentage 0.0624 and
  innings 0.1845; the permuted twin reads 0.0220 and fails as required.
- Gap CIs (v1): vs fielding percentage +0.3452 (lo95 +0.2060); vs innings +0.2236 (lo95
  +0.0831); vs the raw rate +0.0037 (lo95 -0.0165, hi95 +0.0234).
- Clauses: beats fielding percentage and beats innings hold under both conventions; the
  raw-rate non-inferiority margin (lo95 >= -0.01) does NOT hold on this one-season set under
  either convention. The interval is about 0.04 wide at n 301 against 1,255 pairs in X-D1, so
  the holdout neither confirms nor contradicts the parent's tie with its raw-rate parent; it is
  what one season resolves.
- Consequence, as section 7 fixed in advance: none. X-D1 stays validated on 2021 to 2024 and
  X-D2 stays provisional; the registry row's notes carry the holdout numbers beside the verdict.
  Nothing served moved.
