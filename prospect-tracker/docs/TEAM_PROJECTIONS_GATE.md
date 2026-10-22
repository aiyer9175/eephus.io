# Team projections gate (registered 2026-10-08, GATE read once 2026-10-14)

Status: **GATE read once 2026-10-14 (an owner-waived early read, EW3-5): TM-A FAIL, TM-B FAIL, TM-C RS FAIL and RA PASS; no flag eligible; FORWARD (2027) unread.** Gate document for the team family of the
projections program (Part 9 section 9.5 'Team projections'; LANE_A sections 2.6
'Team expansion options' and 3.3 'TM gates'). Registration task
TM_1_TEAM_GATE_REGISTRATION. Owner ask of 2026-10-01 (message 1, verbatim):
"Can we expand upon team projections further?"

No candidate number exists at this commit: no talent sd, no PA or IP budget
constant, no projected runs scored or allowed, no CRPS, no coverage, no MAE for
any candidate, no 2026 team residual, and no shadow record entry. No code,
payload, flag, registry row, glossary entry or test for any candidate exists.
Every rule below was written before any such number existed. This file is
committed alone (round 4, mechanics 3); the two registry rows of section 5.3
are written by TM_2_TEAM_SCORER after step Z, not here.

## 0. Honesty clause and verification

### 0.1 Honesty clause

The 2026 club season is unread as a projection target. The module first
projected 2027; the retro backtest's targets are 2022 to 2025; the 2026
standings entered the site only as the in-season blend's input
(`proj_export._current_blend`) and the Franchise season tiles, never as a label
against which a projection was scored. This registration claims the 2026 club
season as the GATE frame and asserts below that the claim still holds at HEAD.

Reads made to write this file, and nothing else of the kind:

- `proj_backtest.py` at 'TARGETS = ' and the names in its team block;
- `data/team_outlook_eval.json`: its top-level keys, `retro_backtest.design`,
  the seasons and the per-season MAE keys of
  `retro_backtest.team_level_per_season` (the DEV record already published in
  LANE_A A13), and `forward_gate`;
- a path-only scan of the 234 files matched by `data/*eval*.json`,
  `data/futures*.json` and `data/bracket_sim*.json` (section 0.2 (b));
- the metadata of `data/futures.json` (`ledger`, `win_total_basis`), of
  `data/futures_ledger.json` (`_meta`, entry keys) and of
  `data/bracket_sim_record.json` (entry keys);
- the four team rows of `data/model_registry.json` (verdict and status only);
- the code anchors of section 0.2 (c).

The file `.cache/statsapi_standings_2026.json` was checked for existence only
and not opened. No 2026 win total, runs scored, runs allowed or standing was
related to any projection. No dark betting column was read. No statistic was
computed by consensus-FV cell.

### 0.2 Verification at HEAD 0f9fb164 (worktree branch wt-TM_1_TEAM_GATE_REGISTRATION)

**(a) TARGETS and the retro block.** `proj_backtest.py` line 54:

    TARGETS = (2022, 2023, 2024, 2025)      # last one = the held-out gate season

`data/team_outlook_eval.json` `retro_backtest.team_level_per_season` carries
the seasons [2022, 2023, 2024, 2025] and no 2026 row;
`retro_backtest.design.targets` is [2022, 2023, 2024, 2025] with holdout 2025;
`retro_backtest.generated_at` is 2026-08-04. There is no
`team_projection_gate` key in the file. PASS.

**(b) No artifact scores a 2026 team season.** A path scan of 234 files
(`data/*eval*.json`, `data/futures.json`, `data/futures_ledger.json`,
`data/bracket_sim.json`, `data/bracket_sim_record.json`) for any path that
joins a scoring word (mae, rmse, crps, brier, resid, coverage, bias, error,
corr, scored) with a team word (team, club, win, runs, pythag, standing,
outlook, division, playoff) and the season 2026, and for any object with
season 2026 that carries scoring and team keys, returned three files, none a
team score:

- `data/fwar_replica_eval.json` `seasons/2026/...`: the player-level replica
  of FanGraphs' WAR on realized inputs; `single_team` and `multi_team` split
  players by stints, and `war_wins_mae` is a player WAR error. No club total.
- `data/bat_tracking_eval.json` `data_source/coverage/2026`: data coverage.
- `data/riv_market_regate_eval.json` `coverage/matched_n_by_winter/2026`: FA
  market coverage.

The futures ledger records published probabilities, not scores:
`data/futures.json` `ledger` reads n_entries 23, n_resolved 0, "Nothing in it
is scored yet"; `data/futures_ledger.json` `_meta` reads n_resolved 0,
entries_by_season {"2026": 23}, and "No entry has been graded and no accuracy
claim rests on this file." `data/bracket_sim_record.json` holds 2 postseason
bracket entries (series and pennant probabilities, no win totals).
`team_outlook_eval.json` `forward_gate` is status "pending", first scoreable
"end of the 2027 season". PASS.

**(c) The inventory (LANE_A section 1 A12), each anchor re-read at HEAD.**
Citations in LANE_A are pinned @0d4892bb; the HEAD line is the line the anchor
sits on at this commit.

| what | producer (anchor) @0d4892bb | at HEAD 0f9fb164 | where it shows | registry row / artifact |
|---|---|---|---|---|
| 2027 projected W-L, roster WAR, depthWar, top-3 | `proj_export._team_outlook` (:2151); `_depth_pool` (:1962); uniform remainder to 2,430 per season | `def _team_outlook(` proj_export.py:2359; `def _depth_pool(` :2170; `"depthWar"` :2489; `LEAGUE_WINS = 2430.0` proj_backtest.py:55 | /projections/ Team Outlook (`function renderTeams()` assets/projections.js:926, was :865); GFX `function _teamOutlookBoardSpec(rows)` :3837 (was :3296) | `team_win_projections` (provisional); data/team_outlook_eval.json |
| byYear 2027-2031 controlled WAR and wins | same | `"byYear": by_year` proj_export.py:2520 | payload only (owner 2026-06-19) | same, `multi_year` block |
| Core Control `lockedPct`, `ctrlWar5y`, `fullWar5y` | same | proj_export.py:2522-2524 | Team Outlook column (`hasControl`, projections.js:957) | same |
| Window alignment | `_org_farm_blocks` + `_team_outlook` | `def _org_farm_blocks()` proj_export.py:2291 | CHANGED since @0d4892bb: surfaced by default, `const WINDOW_DEFAULT = true` projections.js:961 (`#window=0` hides) | `farm_window_alignment` (provisional) |
| 2026 in-season blend, SOS, remaining wins | `_current_blend` (:2535, k = 40), `_attach_current_season` (:2588, log5 SOS) | `def _current_blend(` proj_export.py:2743; `CURRENT_PRIOR_PSEUDO_GAMES = 40` :2704; `def _attach_current_season(` :2826 | `team_outlook[].current` (Team Outlook current slate behind `#now=1`, projections.js:966); Franchise season tiles | `playoff_odds_sim` (provisional) |
| season simulator: division, playoff, bye, pennant, WS, win band | `proj_current.simulate_playoffs` (:580), talent = the pure prior; `build_futures` (:2759) | `def simulate_playoffs(` proj_current.py:580 (MC_SIMS 20000 :53, MC_SEED 12345 :68); talent is `prior_by_team` from `_talent_prior_pct` (proj_export.py:2734, :2855, :2895); `def build_futures(` proj_export.py:3027; `win_total_basis` :3126 | /betting/ Futures; Franchise ODDS | `playoff_odds_sim` (provisional); data/futures.json; futures ledger (23 entries, 0 resolved) |
| postseason bracket odds | `bracket_sim.py` (bracket_v1) | `METHOD_VERSION = "bracket_v1"` bracket_sim.py:61 | /betting/ Pennant and WS, Franchise Pennant tile, postseason only | `postseason_bracket_sim` (unvalidated; "registered, forward record running, not read") |
| Franchise OUTLOOK leg and Index | `franchise_export.build` (:575, at 'v_outlook') | `def build()` franchise_export.py:576; `v_outlook = ` :653 | /franchise/ | quotes `team_win_projections` |
| F-SCORE (planned) | SP/part8/XWAR_FSCORE_PLAN.md; outlook leg 0.05 of the index | not built: no `FSCORE_LIVE` in any .py at HEAD | Franchise, Teams tab (planned) | FS_* tasks |
| Cost+ and $ per projected win | `ledger_export` (at 'usd_per_win') | `"usd_per_win":` ledger_export.py:1865 | /ledger/, Franchise | |
| FA Fit window baseline | `fa_fit._outlook_wins` (:750) | `def _outlook_wins(class_year: int)` fa_fit.py:750 | /fa/ team fits | Gate 3 |
| winter frame (owner answer OUTLOOK (a)) | Q9_03_TEAM_OUTLOOK_WINTER_FRAME | not landed: the queue result records STOPPED, 'BLOCKER: task M15_PROJECTIONS_FREEZE_TRIPWIRE' | Team Outlook, Franchise, Cost+ | monthly freezes Q9_03a-e |
| forward vintage freeze | M15_PROJECTIONS_FREEZE_TRIPWIRE: docs/PROJ_FORWARD_VINTAGE_GATE.md | not landed: the file is absent at HEAD | none | scored at the 2027 close |
| Pythagenpat (used by T3) | `proj_export._pythag_pct` | `def _pythag_pct(` proj_export.py:2710; exponent ((RS+RA)/G)^0.287 (`_PYTHAGENPAT_EXP` :2703) | in-season blend only | none |
| Team Outlook banner (LANE_A A14 (g)) | "projected roster eWAR to wins" (projections.js:877) | CHANGED: "projected roster WAR (fWAR basis) to wins at the 47.7 replacement baseline" projections.js:938; A14 (g) is closed at HEAD | Team Outlook | |

DEV record as published (LANE_A A13, re-read at HEAD): served_recentered MAE
9.60, 9.63, 7.23, 7.18 wins for 2022 to 2025 against the prior-wins
carry-forward 10.41, 11.38, 9.45, 7.24; `assigned_level_deficit` -131.6, -83.7,
-114.9, -88.1 WAR. This block predates the epoch (generated 2026-08-04); section
2.1 names which retro run the DEV freeze uses.

The registry rows `team_win_distribution` and `team_run_projection` are absent
at HEAD, as expected (section 5.3).

## 1. The candidates

Each candidate is built dark by TM_3_TEAM_CANDIDATES_DARK behind its own flag
defaulting False, with `aging="v2"` passed explicitly in both arms (PLAN 9.7,
'Display doors: Team Outlook wins'), so no TM verdict depends on the aging
program.

### 1.1 T1, talent ranges (flag `TEAM_TALENT_RANGE_LIVE`, class 3, gate TM-A)

Per simulation, each club's win probability is drawn once, before the games,
from Normal(p_prior, sigma_T / 162), clipped to [0.20, 0.80], where p_prior is
the incumbent's talent rate (`_talent_prior_pct` of the club's projected wins).

    sigma_T = sqrt(max(0, s_res^2 - s_sched^2))

- s_res: the RMSE, over all club-seasons of the DEV seasons 2022-2025, of the
  served_recentered retro residual (projected wins minus actual wins).
- s_sched: the mean, over the same club-seasons, of the sd of the schedule-only
  simulated win total (each club at its served_recentered p_prior, that
  season's actual schedule).
- In season, sigma_T is multiplied by k / (k + G), with k = 40
  (`proj_export.CURRENT_PRIOR_PSEUDO_GAMES`) and G the club's games played. In a
  preseason projection (G = 0) the factor is 1.
- sigma_T, s_res and s_sched are frozen by TM_3 in
  `model/team_projection/params.json` before the GATE look (section 8).
- With sigma_T = 0 the simulator consumes exactly the random draws it consumes
  today (TM_3's identity test on the same seed).

### 1.2 T2, club PA and IP budget (flag `TEAM_PT_BUDGET_LIVE`, class 3, gate TM-B)

- Constants: the 2022-2025 league means of team PA and team IP per 162 games,
  frozen by TM_3 before the look.
- Each rostered hitter's projected PA is allocated, capped at the player's own
  projection. When the club's sum exceeds the budget, every allocation is scaled
  down pro rata to the budget. A shortfall is filled at replacement (0 WAR).
- The same for IP with the club's pitchers.
- Then the existing 2,430-win pin (`LEAGUE_WINS`) is applied.
- The un-budgeted wins stay available to fa_fit under their own key (section
  6.2), so `data/fa_class.json` is byte-identical with the flag on and off.

### 1.3 T3, runs scored, runs allowed, run differential, Pythag wins (flag `TEAM_RUNS_LIVE`, class 2, gate TM-C)

    RS = league runs per game x 162 + the roster's batting runs + baserunning runs, at T2's PA
    RA = league runs allowed per game x 162 + the staff's FIP runs above average, at T2's IP,
         minus the club's fielding runs

- The club's park factor (`.cache/fangraphs/park_factors_<season>.json`) is
  applied to RS and RA at the team level.
- Pythagenpat wins = 162 x `proj_export._pythag_pct(RS, RA, 162)`, shown beside
  the WAR wins, never replacing them.
- Run differential = RS - RA. It never enters F-SCORE (PLAN 9.7, 'F-SCORE').
- The batting, baserunning and fielding runs come from the component heads of
  docs/PROJ_COMPONENTS_GATE.md (family PJ, FanGraphs frame); a head that fails
  PJ-C is not served there, and its runs ride in that gate's gap line.

### 1.4 T4, the 2027 preseason season simulation (forward record only)

From the Q9_03 as-of-signings frame; class 3 under owner answer TM-Q2 (flag
`FUTURES_2027_PRESEASON_LIVE`). No gate verdict in this document; its forward
entries are what TM-D's served side reads in 2027.

### 1.5 T5, blended talent (TM-D, dark shadow, 2027)

The simulator's per-game win probability is `proj_export._current_blend`'s
forward rate (prior plus Pythag) instead of the pure prior. It runs as a
shadow only (section 3.4); served only after its look and a new owner answer.

### 1.6 Not proposed

- cohort intercepts (three consecutive losses, registry `team_win_projections`);
- a team-level mean recalibration (the 2,430 pin already fixes the level);
- T6, out-year W-L (stays hidden, owner 2026-06-19);
- T7, the per-club drill-down, is descriptive (class 2, TM-Q4), not gated here.

## 2. Frames

| frame | seasons | status |
|---|---|---|
| DEV | the retro seasons 2022-2025 | read (the published DEV record) |
| GATE | the 2026 club season, 30 clubs | unread; read once at the GATE look |
| FORWARD | the 2027 club season | the frozen frames of M15 (Opening Day 2027) and Q9_03, plus this gate's shadow record |

### 2.1 DEV

The DEV quantities of section 1 (s_res, s_sched, the PA and IP constants) come
from TM_2's `proj_backtest.team_frame` on 2022-2025 on the retro engine current
when TM_3 freezes, which is the run M15_PROJECTIONS_FREEZE_TRIPWIRE part (4)
commits after step Z (TM_2's precondition 6), not the 2026-08-04 block quoted
in section 0.2. TM_3 records which retro run it read. The 2025 holdout of the
retro backtest is part of DEV here; it is no longer held out.

### 2.2 GATE: how the 2026 projection is made

- The 2026 projection is proj_backtest's point-in-time retro design: every
  input dated 2025 or earlier (curves and the WAR map refit on data through
  2025, the frozen fWAR vintage seasons through 2025), with actual-roster
  assignment by the existing primary-stint rule on the 2026 war_daily stints.
- The stint read uses exposure only. The 2026 team frame computes no
  `assigned_actual_war`, no `assigned_level_deficit` and no player-level 2026
  residual, cohort or MAE (the player-level 2026 label is the path-shape gate's
  CONFIRM frame).
- Point-in-time inputs for T3 on GATE: league runs per game is the 2025 league
  mean; the park factor file is `park_factors_2025.json`. On FORWARD, the
  last completed season before 2027 (2026).
- Actual 2026 wins, runs scored and runs allowed come from
  `.cache/statsapi_standings_2026.json` through `franchise_export._standings`
  (the one standings parser, master plan 8.E), read only at the look.
- The schedule-only incumbent and the T1 candidate run through
  `proj_current.simulate_playoffs` on the 2026 regular-season schedule with
  n_sims 20,000 (MC_SIMS), home edge 0 (MC_HOME_EDGE) and the same simulator
  seed (MC_SEED 12345) in both arms, so the arms share random numbers. The
  schedule is a fixture, not an outcome.

### 2.3 FORWARD

The 2027 projections are read from the frozen Opening Day 2027 frame (M15, as
amended by PJ_10) and the Q9_03 frames; the TM-D shadow from
`.cache/team_projection/shadow/record.json`; the served side of TM-D from the
futures ledger entries for 2027. Actual 2027 wins, RS and RA come from the
cached final 2027 standings through the same parser.

## 3. Statistics

Common: deltas are candidate minus comparator per club, paired over the 30
clubs; the bootstrap resamples clubs with replacement, B 2000, with
`numpy.random.default_rng(seed)`; the one-sided 95% upper bound (UB95) is the
95th percentile of the 2,000 resampled mean deltas. Each statistic governs
only its own flag, so no multiplicity correction is applied across TM-A, TM-B
and TM-C. Thresholds are frozen here and never loosened.

### 3.1 TM-A (T1), seed 20261208

- Statistic: mean CRPS of the win-total distribution against actual 2026 wins,
  candidate (T1) minus incumbent (schedule-only), paired over 30 clubs.
- CRPS of a club's empirical distribution X_1..X_n against the actual y:
  mean|X_i - y| - (1 / (2 n^2)) sum_i sum_j |X_i - X_j|, computed exactly from
  the sorted samples.
- Pass: UB95 < 0.
- Reported, no verdict: 80% range coverage (actual wins inside [P10, P90],
  inclusive) for both arms with a Wilson 95% interval over 30 clubs; DEV
  coverage for both arms (the candidate's DEV coverage is in-sample, because
  sigma_T is fitted on DEV, and is labelled so).

### 3.2 TM-B (T2), seed 20261208

- Statistic: team wins MAE, the T2 budgeted roll-up (after the 2,430 pin) minus
  served_recentered, on identical clubs, paired.
- Pass: UB95 < 0.
- Registered expectation: unresolvable. The three 2025 retro arms differed by
  at most 0.09 wins (7.18 / 7.21 / 7.27), and team-level differences under
  about a win are not resolvable at 30 clubs a season (LANE_A A13). A null
  keeps the served roll-up.

### 3.3 TM-C (T3), seed 20261208

- Statistic: RS MAE and RA MAE against actual 2026 RS and RA.
- Comparators, both required: prior-season carry-forward (each club's 2025
  actual RS and RA) and league average (the 2025 league mean runs per club,
  for every club, both sides).
- Pass per side: UB95 < 0 against both comparators. A side that fails keeps
  RS or RA off the page; RS, RA and run differential are served together only
  if both sides pass, and Pythag wins only with them.
- Reported beside, no verdict: Pythag wins MAE and served wins MAE on the same
  clubs.

### 3.4 TM-D (T5, forward 2027), seed 20271116

- Statistic: Brier of `divisionPct` and `playoffPct` at six checkpoints
  (Opening Day, May 1, June 1, July 1, August 1, September 1), blended-talent
  shadow minus served, paired over clubs (cluster = club), B 2000.
- At each checkpoint both sides read their latest entry dated on or before it;
  a checkpoint with no entry on either side is dropped and reported. Outcomes:
  division winner (divisionPct), the postseason field (playoffPct).
- The served side is the served configuration on that date; the shadow differs
  from it only in the talent input.
- Pass: UB95 < 0 on the pooled Brier (6 checkpoints x 2 markets x 30 clubs,
  resampled by club).
- The shadow record is chain-hashed, first write wins, one entry per date,
  kept under `.cache/team_projection/shadow/` in the pattern of
  `.cache/bracket_sim/record.json`. A record that fails its chain check STOPs
  the look (OWNER_QUESTION.md).

### 3.5 The 2027 re-read of TM-A, TM-B and TM-C

On 2027, from the frozen Opening Day frames, each re-read once as a forward
confirmation, same statistics and seeds as 3.1 to 3.3. It is a veto only for a
served flag: a UB95 at or above 0 on 2027 reverts that flag by its one
constant, in its own class 3 commit naming every moved number. It never makes
an unserved flag eligible.

## 4. Looks

### 4.1 GATE look (TM_4_TEAM_LOOK_2026), once

The GATE look runs on the first day after TM_3_TEAM_CANDIDATES_DARK lands
(its DEV freeze entry, with the sha256 of `model/team_projection/params.json`,
recorded in section 8) on which the GATE frame named in section 2 is complete
(final 2026 standings with RS and RA for 30 clubs cached) and no other
registered look is recorded that day, nor is the day one the program's
calendar rule (U1) holds for another task. The 2026 regular season is final,
so the frame is complete now; the binding condition is TM_3. The queue's
planned date 2026-12-08 is not a floor (owner decision EPOCH-NOW, 2026-10-02).
A look is early only if it runs before that condition holds.

### 4.2 FORWARD look (TM_9_TEAM_LOOK_2027), once

On the later of 2027-11-16 and seven days after the 2027 regular season's
final standings are cached, never on another gate's look date (a 2027 forward
read, kept by EPOCH-NOW).

### 4.3 Procedure, both looks

- Tee stdout and stderr to the task's output directory before anything else
  runs.
- Dry-run the whole reporting path on fixtures with nulls first (a club with
  no rows, a missing RS).
- One run. An exception after scoring began STOPs without a rerun and writes
  OWNER_QUESTION.md.
- Verdicts by the registered rules only. A null is a finding.
- The result is appended verbatim to section 8, and written by
  read-modify-write as `team_projection_gate.gate_2026` (or `.forward_2027`)
  in `data/team_outlook_eval.json`, keeping every other key.

## 5. Ship rules and registry rows

### 5.1 Ship rules

- A pass makes its flag eligible; it never flips it by itself.
- Class 3 flips (T1 `TEAM_TALENT_RANGE_LIVE`, T2 `TEAM_PT_BUDGET_LIVE`) also
  need owner answer TM-Q1 (answered 2026-10-01: "Serve each that passes",
  recommended option under the standing instruction). T4's switch needs TM-Q2
  (answered: "Switch Futures to 2027"). T3 (class 2) serves where TM-Q4 says
  (answered: "Team Outlook, linked").
- A null or a fail keeps the incumbent.
- Each served flag's revert is one constant.
- A flip is one commit carrying the flag, the new data/ files, the registry
  rows and the glossary entries together, naming every new key, file and row
  count, and every moved number with before and after.
- A TM-D pass changes nothing served: the switch to blended talent is a new
  owner question.

### 5.2 Verdicts

The two new rows stay `provisional` after the GATE look whatever the outcome
(TM_4), with dated notes carrying the numbers read from the artifact.

### 5.3 Registry rows (defined here, written by TM_2_TEAM_SCORER after step Z)

`team_win_distribution`:

- surface: "none yet (registered, not served); on a pass, the win range and
  odds on /betting/ Futures, the Franchise ODDS section and Team Outlook"
- predicts: "each club season win-total distribution with talent and schedule
  uncertainty"
- champion: "none"
- baseline: "the schedule-only distribution of playoff_odds_sim"
- metric: "TM-A, docs/TEAM_PROJECTIONS_GATE.md section 3"
- eval_artifact: null; verdict: "unvalidated"; registration_status:
  "registered, not read"
- depends_on: ["playoff_odds_sim", "team_win_projections"]

`team_run_projection`:

- surface: "none yet (registered, not served); on a pass, RS, RA, run
  differential and Pythag wins on Team Outlook"
- predicts: "club runs scored and allowed for the first projected season"
- champion: "none"
- baseline: "prior-season carry-forward and league average"
- metric: "TM-C"
- eval_artifact: null; verdict: "unvalidated"; registration_status:
  "registered, not read"
- depends_on: ["proj_components", "team_win_projections"]

TM_2 checks test_model_registry.py and test_methodology_freshness.py and marks
a row internal if those require it.

## 6. Blast radius per flag

### 6.1 Table (LANE_A section 2.8)

| flag | moves | never moves |
|---|---|---|
| `TEAM_RUNS_LIVE`, `TEAM_DRILLDOWN_LIVE` | adds Team Outlook keys | wins, Franchise, Cost+, Fit |
| `TEAM_TALENT_RANGE_LIVE` | Futures probabilities and win band, Franchise ODDS, `team_outlook[].current` odds | `wins`, OUTLOOK leg, Cost+, Fit |
| `TEAM_PT_BUDGET_LIVE` | Team Outlook `wins`, `depthWar`, byYear wins; Franchise OUTLOOK letters and Index (or F-SCORE and its OUTLOOK leg when `FSCORE_LIVE` is True at HEAD); Cost+ and $ per projected win | player rows, surplus, trade values, the FA Fit input wins, `data/fa_class.json` |
| `FUTURES_2027_PRESEASON_LIVE` | data/futures.json season and every club row; Franchise ODDS | bracket_sim's postseason surfaces while the postseason runs |

### 6.2 The FA Fit under T2

`fa_fit._outlook_wins` reads one field: the pre-free-agency frame's wins that
Q9_03 emits under their own name for fa_fit, always on the aging="v2",
uncapped, un-budgeted engine (PLAN 9.7, round 5). T2 never changes that field.
If Q9_03 emitted no separate field, T2 emits the un-budgeted wins under their
own key (`byYear[].winsFaFit`, same frame) and fa_fit reads that; no second key
is added otherwise. TM_3 proves fa_fit's per-club input wins equal and
`data/fa_class.json` byte-identical with the flag on and off.

## 7. Bans

- No cohort intercepts and no team-level recalibration.
- No team statistic by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md).
- No edit of proj_backtest's TARGETS, main() or the retro_backtest block.
- No 2026 club season read before the GATE look: nothing relates any 2026
  projected team quantity, of any arm, to 2026 actual wins, runs scored, runs
  allowed or standings before it, and no DEV constant is chosen with any 2026
  outcome in view. The served in-season blend's existing use of 2026 standings
  is an input, not a score, and continues.
- No player-level 2026 residual, cohort or MAE; no `assigned_actual_war` for
  2026.
- No look early, no second look, no rerun after an exception, no grid or
  candidate added after the look.
- Labels: FanGraphs' WAR or run parts from the frozen fWAR vintage only, never
  the live StatsAPI sabermetrics cache; a house eWAR v3 part is never a label
  here (U2).
- No age adjustment outside `aging_v3.py`; both arms pass `aging="v2"` (U3).
- No dark betting column related to an outcome or a price; no management
  figure on a priced cell; T3's run differential never enters F-SCORE.
- Never score the reserved eFV frames R-LV (list vintages 2020 and 2021) or
  R-VM (the 2025 and later debut cohorts).

## 8. The append-only record

Entries are dated, appended in order, first write wins, never edited. Expected
entries: the DEV freeze (TM_3: s_res, s_sched, sigma_T, the PA and IP
constants, DEV coverage, the retro run read, and the sha256 of
`model/team_projection/params.json`, which TM_4 checks before it runs); the
GATE result (TM_4, verbatim); the FORWARD result (TM_9, verbatim). A late look
first appends a dated amendment naming the new date and the reason, committed
alone.

### 2026-10-14: the DEV freeze (TM_3_TEAM_CANDIDATES_DARK)

DEV frozen 2026-10-14 at 1444d9f9, params sha256 8d20d629c79d4996b5c8db266f721eacb3de0be771eb90c749b69705dad7a929.
The sha is the HEAD the run read (the branch base; `model/team_projection/params.json` records it
as `head`); the freeze itself is committed by this task's commit on branch
wt-TM_3_TEAM_CANDIDATES_DARK. The run: `PYTHONHASHSEED=0 python tools/team_projection_dev.py --write`
(the hash seed is part of the record because `proj_current.simulate_playoffs` takes its tie-break
draws while iterating a set of division names, so two processes with different string hash seeds
consume the stream in a different order; measured 2026-10-14 as sigma_T 7.6765 against 7.6766 across
two unpinned runs on the same schedules and seed; pre-existing, not changed here).

**The retro run read (section 2.1).** `proj_backtest.team_frame(target, aging="v2")` for 2022 to
2025 on the retro engine at 1444d9f9 (curves and WAR map refit per target on data through target - 1,
actual-roster assignment by the primary-stint rule). Its served_recentered MAE by season is 9.026,
9.586, 6.768, 7.118 wins, which reproduces the published DEV record (`data/team_outlook_eval.json`
`retro_backtest`, generated 2026-10-09: 9.03, 9.59, 6.77, 7.12) to the printed digit. 120 club-seasons;
no 2026 club quantity was read. The season schedules are StatsAPI /schedule, played games by gamePk
(2,430, 2,430, 2,429, 2,430), cached write-once under `.cache/team_projection/schedules/`.

**T1 constants.** s_res 9.9379 wins (the RMSE of the served_recentered residual over the 120
club-seasons); s_sched 6.3131 wins (the mean sd of the schedule-only simulated win total at p_prior
over each season's actual schedule, n_sims 20,000, seed 12345, home edge 0, bracket off: 6.3191,
6.3034, 6.3065, 6.3235 by season); sigma_T = sqrt(9.9379^2 - 6.3131^2) = 7.6751 wins; k 40; clip
[0.20, 0.80].

**T2 constants.** The club budget is PA 6,096.7 and IP 1,436.4 per 162 games (the 2022 to 2025 league
means of actual club exposure x 162 / games played: PA 6,068.4, 6,136.8, 6,084.1, 6,097.5; IP 1,435.8,
1,436.2, 1,437.8, 1,435.8).

**T3.** No constant of its own: the park factor column is Basic (5yr) from
`.cache/fangraphs/park_factors_<target - 1>.json` (2021 to 2024 on DEV, every club named), the
Pythagenpat exponent 0.287, BF per IP 4.3, and the PJ-C params sha256
da2d5114fe2c05a1cceed883a625ddb63060e45c8fc848c385860694b02cf9b6 for the heads.

**DEV tables (in-sample for T1, because sigma_T is fitted here; paired club bootstrap B 2000, seed
20261014, candidate minus comparator, ub95 the 95th percentile of the resampled mean delta).**

| candidate | statistic | 2022 | 2023 | 2024 | 2025 | pooled (120) |
|---|---|---|---|---|---|---|
| T1 incumbent (schedule only) | mean CRPS | 6.439 | 7.227 | 4.817 | 5.123 | 5.902 |
| T1 candidate (sigma_T) | mean CRPS | 5.975 | 6.684 | 4.803 | 5.058 | 5.630 |
| T1 | CRPS delta mean / ub95 | -0.464 / -0.206 | -0.543 / -0.248 | -0.014 / +0.230 | -0.066 / +0.185 | -0.272 / -0.136 |
| T1 incumbent | 80% coverage | 0.467 | 0.400 | 0.667 | 0.667 | 0.550 (66 of 120; Wilson 0.461 to 0.636) |
| T1 candidate (in-sample) | 80% coverage | 0.767 | 0.700 | 0.900 | 0.833 | 0.800 (96 of 120; Wilson 0.720 to 0.862) |
| T2 served_recentered | wins MAE | 9.026 | 9.586 | 6.768 | 7.118 | 8.124 |
| T2 budgeted (after the 2,430 pin) | wins MAE | 8.837 | 9.055 | 6.487 | 6.689 | 7.767 |
| T2 | abs-error delta mean / ub95 | -0.190 / +0.032 | -0.531 / -0.221 | -0.280 / +0.119 | -0.430 / +0.015 | -0.358 / -0.172 |
| T2 | clubs over the PA / IP budget | 2 / 16 | 6 / 21 | 7 / 22 | 10 / 19 | |
| T3 | RS MAE (runs) | 51.9 | 70.8 | 52.3 | 49.3 | 56.1 |
| T3 | RS vs carry-forward: comparator MAE / ub95 | 69.6 / -2.10 | 80.1 / +3.58 | 75.8 / -7.28 | 57.1 / +3.38 | pooled mean -14.57 / ub95 -6.99 |
| T3 | RS vs league average: comparator MAE / ub95 | 65.0 / -2.18 | 74.8 / +4.91 | 65.6 / -0.43 | 53.1 / +6.19 | pooled mean -8.52 / ub95 -3.10 |
| T3 | RA MAE (runs) | 63.4 | 48.2 | 51.3 | 55.0 | 54.5 |
| T3 | RA vs carry-forward: comparator MAE / ub95 | 78.1 / +1.22 | 65.8 / -4.54 | 60.1 / +4.17 | 47.2 / +19.71 | pooled mean -8.34 / ub95 -1.58 |
| T3 | RA vs league average: comparator MAE / ub95 | 80.2 / -2.77 | 69.2 / -5.34 | 67.1 / -2.42 | 66.7 / -0.95 | pooled mean -16.33 / ub95 -9.70 |
| T3 | Pythag wins MAE (served wins MAE beside) | 8.30 (9.03) | 9.03 (9.59) | 7.42 (6.77) | 6.46 (7.12) | 7.80 (8.12) |
| T3 | league identity, sum RS minus sum RA (runs; 1% tolerance, reported only) | -884 | -541 | -1,001 | -875 | outside tolerance every season |

The T3 league identity fails every DEV season: the summed RS of the 30 assigned rosters sits 1% to
4% under 30 x the league mean and RA 2% above it (the assigned universe's batting runs sum below
average while its FIP runs sum above the league), the engine's level deficit on the runs side.
Section 7 bans a team-level recalibration, so it is reported and not corrected; the GATE look scores
it as built. Nothing here is a verdict: TM-A, TM-B and TM-C are read once at the GATE look (TM_4) on
the 2026 season, which remains unread.

Written by TM_3_TEAM_CANDIDATES_DARK. The tables, the per-club accounting and the residuals are in
`model/team_projection/dev_receipt.json` (params_sha256 as above).

### 2026-10-14: the GATE look (TM_4_TEAM_LOOK_2026), verdicts TM-A FAIL, TM-B FAIL, TM-C RS FAIL RA PASS

Run once on 2026-10-14 at 95102285 (branch wt-TM_4_TEAM_LOOK_2026), `PYTHONHASHSEED=0 python tools/team_projection_look.py --out <dir> --write`, stdout and stderr teed to the task's output directory before anything else ran, the reporting path dry-run first on fixtures with nulls. An OWNER-WAIVED EARLY READ (EW3-5, owner 2026-10-14): registered for 2026-12-08 and for the first day after the DEV freeze landed on which no other look is recorded; both waived, the frame itself complete (the 2026 regular season is final).

**Preconditions.** The DEV params hashed to the freeze entry above (8d20d629c79d4996b5c8db266f721eacb3de0be771eb90c749b69705dad7a929); gate_2026 was absent from the artifact; the 2026 frame was complete (30 clubs with wins, RS and RA through franchise_export._standings, games played [161, 162]).

**The frame (section 2.2).** proj_backtest.team_frame(2026, look=True, aging="v2"): 2201 point-in-time rows (inputs 2023 to 2025; curves and the WAR map refit on data through 2025), 1276 assigned to 30 clubs by the primary-stint rule on the 2026 stints (exposure only), 925 unassigned (50.8 WAR); no row carries a 2026 actual WAR. Roster WAR sum 865.0; served_recentered recenters to 2,430. Schedule: 2429 played regular-season games (statsapi), n_sims 20000, seed 12345, home edge 0.0, bracket off, both arms on the same stream. Actual 2026 wins, RS and RA read once from `.cache/statsapi_standings_2026.json`; the prior season for TM-C is 2025 (carry-forward per club; league mean RS 720.5, RA 720.5 per club).

**Bootstrap.** Paired over clubs, B 2000, seed 20261208, candidate minus comparator, ub95 the 95th percentile of the resampled mean delta; pass is ub95 < 0.

| gate | statistic | 2026 |
|---|---|---|
| TM-A incumbent (schedule only) | mean CRPS | 5.916 (win sd 6.308) |
| TM-A candidate (sigma_T 7.6751) | mean CRPS | 5.694 (win sd 9.929) |
| TM-A | CRPS delta mean -0.222 / ub95 0.068 (n 30, dropped 0) | **FAIL** |
| TM-A incumbent | 80% coverage | 0.600 (18 of 30; Wilson 0.423 to 0.754) |
| TM-A candidate | 80% coverage | 0.800 (24 of 30; Wilson 0.627 to 0.905) |
| TM-A DEV coverage beside (section 3.1) | incumbent / candidate (in-sample) | 0.550 (66 of 120; Wilson 0.461 to 0.636) / 0.800 (96 of 120; Wilson 0.720 to 0.862) |
| TM-B served_recentered | wins MAE | 7.804 (bias 0.033, r 0.438) |
| TM-B budgeted (PA 6096.7, IP 1436.4; after the 2,430 pin) | wins MAE | 7.437 (bias 0.033, r 0.498) |
| TM-B | abs-error delta mean -0.368 / ub95 0.001 (n 30, dropped 0) | **FAIL** |
| TM-B | clubs over the PA / IP budget | 8 / 21 |
| TM-C | RS MAE (runs) | 42.6 (n 30) |
| TM-C | RS vs carry-forward: comparator MAE / delta / ub95 | 61.9 / -19.30 / -3.49 |
| TM-C | RS vs league average: comparator MAE / delta / ub95 | 39.2 / 3.37 / 13.59 |
| TM-C | RS verdict (ub95 < 0 against both) | **FAIL** |
| TM-C | RA MAE (runs) | 47.7 (n 30) |
| TM-C | RA vs carry-forward: comparator MAE / delta / ub95 | 66.4 / -18.70 / -6.01 |
| TM-C | RA vs league average: comparator MAE / delta / ub95 | 62.2 / -14.50 / -1.37 |
| TM-C | RA verdict (ub95 < 0 against both) | **PASS** |
| TM-C | Pythag wins MAE (served wins MAE beside, same clubs; no verdict) | 7.54 (7.80; n 30) |
| TM-C | league identity, sum RS minus sum RA (runs; 1% tolerance, reported only) | -856.5 (RS minus 30 x league -480.2, RA minus 30 x league 376.3; outside tolerance) |

**Clubs scored nowhere (named, never imputed):** none.

**Verdicts by the registered rules only (section 3; a null is a finding).** TM-A FAIL; TM-B FAIL; TM-C RS FAIL, RA PASS. TEAM_TALENT_RANGE_LIVE not eligible; TEAM_PT_BUDGET_LIVE not eligible; TEAM_RUNS_LIVE not eligible. A pass makes its flag eligible and flips nothing (section 5.1); the class 3 flips also need owner answer TM-Q1 (answered: serve each that passes) and land as TM_8's own commits; a null or a fail keeps the incumbent. Nothing served moves at this look.

**Bans kept (section 7).** No player-level 2026 residual, cohort or MAE (the frame rows carry no actual WAR, asserted by team_frame); no team statistic by consensus-FV cell; both arms aging v2; the labels and run parts are the frozen fWAR vintage (FanGraphs frame); no cohort intercept and no team-level recalibration (the T3 league identity is reported, not corrected); no second look.

The block is `team_projection_gate.gate_2026` in `data/team_outlook_eval.json` (per-club table, both arms' CRPS, the T2 accounting, the bootstraps); the registry rows team_win_distribution and team_run_projection point at it and stay provisional whatever the outcome (section 5.2); team_win_projections carries TM-B's dated note. Elapsed 62.4 s.


### 2026-10-21: the team flips (TM_8_TEAM_FLIPS), commit 1 of the flips: TEAM_DRILLDOWN_LIVE True, TEAM_RUNS_LIVE stays False

Written by TM_8_TEAM_FLIPS. No look ran and no verdict is written here; this entry records which flags the 2026-10-14 look makes eligible and what served.

- **TEAM_DRILLDOWN_LIVE set True** (class 2, descriptive, no gate; owner answer TM-Q4 (a)). Every Team Outlook row carries a `drill` block (30 clubs, 1,400 veteran lines, 43 arrived prospects, the foot residual at most 0.05 WAR against Roster WAR) and every Franchise club carries the `team_drilldown` link. Nothing else in `data/mlb_projections.json` moved (0 existing keys moved on 30 rows), and `trade_values.json`, `fa_class.json`, `futures.json` (timestamp only), `fscore.json`, `ledger_board.json`, the 30 ledger club files and the 30 franchise grades are byte-identical in content.
- **TEAM_RUNS_LIVE stays False.** The look records TM-C RS FAIL and RA PASS, and section 3.3 serves RS, RA, run differential and Pythag wins together only if both sides pass, so the look's own record reads TEAM_RUNS_LIVE not eligible. Runs allowed alone does not print. Owner question recorded in the task report: whether to serve RA alone.
- **TEAM_TALENT_RANGE_LIVE and TEAM_PT_BUDGET_LIVE stay False.** TM-A FAIL and TM-B FAIL at the look, so neither flag is eligible and the class 3 flips (commits 2 and 3 of the plan) are not made; each keeps the incumbent (section 5.1).
