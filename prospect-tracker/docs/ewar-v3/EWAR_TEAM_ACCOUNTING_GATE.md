# eWAR team accounting: do summed values track club runs and wins (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EWAR_TEAM_ACCOUNTING (owner decision EW3-50). This document
is committed ALONE, before any number of its estimands is computed: no club-season sum of eWAR
realized, fWAR or bWAR has been set beside a club's runs or wins for this read, and the code that
computes the read does not exist at this commit. Nothing in this commit changes a model, an
exporter, a flag or a served artifact. Part 14 is filled in afterwards; nothing above part 14 may be
edited once anything is written below it, and a change is a dated amendment under part 14,
committed alone. Its pin test is `test_ewar_team_accounting_gate.py`.

- eWAR realized: `docs/ebr-2026-09-30/EBR_GATE.md` amendment 11.10.3 (`data/ewar_v3.json`, the `dr`
  departures): the frozen fWAR vintage, with pitchers priced on the realized basis R2 (11.3.3: runs
  allowed, adjusted for park, defense and inherited runners) from 2016, plus the ABS part from 2026.
- The headline eWAR: the same file's `dh` departures (the ABS part from 2026; the xHEM+ half-weight
  part of 11.11 is built dark behind `ewar_v3.XHEM_HALF_LIVE`).

## 0. What kind of decision this is

- **A descriptive validity read of eWAR realized, decided once, and nothing served moves on it.**
  The question (owner, EW3-50): per club-season, does the sum of player value plus the
  replacement-level baseline track the club's run differential, runs scored and allowed by side,
  and wins better for eWAR realized than for fWAR and for bWAR? It is a same-season accounting
  question. It forecasts nothing and licenses no forecasting sentence.
- **Applied to eWAR realized only.** EBR_GATE.md 11.2.8 gives eWAR realized no forward target and no
  look, and this document does not give it one: the read is same-season. It is not a re-score of any
  predictive cell that failed (parts 12.2 and 12.3 of EBR_GATE.md stand as written), and no
  admission, guard, constant or claim of that document moves on it.
- **The headline eWAR is reported, deciding nothing** (part 2).
- **The yardstick is reusable.** Task EWAR_PITCHING_BLEND (owner decision EW3-50) consumes it: a
  later candidate is scored on this frame, these estimands and these bootstraps, against this read's
  recorded fWAR, bWAR and eWAR realized cells, under that task's own registration and pass rule
  (part 12).
- **Built dark.** The read writes its tracked record to `data/_labs/ewar_team_accounting/record.json`
  (`data/_labs/` ships in neither deploy consumer) and its numbers to part 14 of this document. No
  registry row, glossary entry, page or served artifact is added or moved by this task. On any PASS
  an owner question decides what, if anything, is served (part 11).

## 1. Decision record

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| EW3-50 | Make eWAR better than both fWAR and bWAR without redoing failed work | four arms approved: EWAR_TEAM_ACCOUNTING (this document), EWAR_PITCHING_BLEND, EWAR_UNCERTAINTY_BAND, EWAR_PEH_OLD_SEASONS | answered 2026-10-22 (`DECISIONS_FOR_OWNER.md`, EW3-50) |
| EW3-5 | Look days and registered dates | waived: the read runs on any date; a read before a registered date is an owner-waived early read | answered 2026-10-14 |
| EW3-20 | The two numbers | the headline eWAR (predictive) and eWAR realized (actual runs in the same frame) | answered 2026-10-15 |
| EW3-24 | Each series' runs per win | eWAR v3 carries `data/rpw_fit.json`'s candidate (c), `data/ewar_v3.json` `checks[season].rpw` | answered 2026-10-15; EBR_GATE.md 11.10.4 |

Defaults this document applies, named so the orchestrator records them: the 2020 season is out of
the primary frame (part 3); the replacement baseline of the deciding cells is the league-reconciled
one (part 4); the planted noise scales are 40 runs and 4 wins (part 6); the RS and RA side cells are
reported and do not decide (part 7).

## 2. The series

| Key | Series | Per player-season value | Role |
|---|---|---|---|
| E | eWAR realized | `f[side] + dr[side]` of `data/ewar_v3.json` (fWAR where the player-season is not listed) | the candidate |
| F | fWAR | the frozen vintage's `war` per group, `data/fwar_vintage.json` | comparator; also the no-change null (E with every departure 0) |
| B | bWAR | the `WAR` of every stint row of the site's Baseball-Reference copy (`war_source._load_last_good`, sides bat and pit) | comparator |
| H | the headline eWAR as served | `f[side] + dh[side]` of `data/ewar_v3.json` | reported, deciding nothing |
| Hx | the headline eWAR with the xHEM+ part (11.11, dark) | `f[side] + dh[side]` of `.cache/ewar_v3/preview/ewar_v3_xhem.json` | reported, deciding nothing; skipped and named when the preview is absent |
| E_perm | the permutation null | F plus E's pitching departures permuted within each season among the pitchers that carry one | null comparator (part 6) |

Side: `bat` is the hitting group (hitters, and pitchers who batted), `pit` the pitching group. The
read never edits a series. Before 2026 the headline departures are zero, so in the primary frame H
equals F on every row by construction; its cells are printed as that identity.

## 3. The frame

- **Club-seasons.** Primary: seasons 2016 to 2019 and 2021 to 2025, 30 clubs each, 270 club-seasons.
  2020 (60 games) is reported alone beside it, deciding nothing (default; the precedent of the team
  guard, EBR_GATE.md 11.2.4). 2026 is out: the owner's question names 2016 to 2025, and the ABS part
  enters eWAR realized only in 2026.
- **Outcomes,** from the cached StatsAPI standings through `ewar.standings` (never fetched): wins W,
  losses L, games G = W + L, runs scored RS, runs allowed RA, RD = RS - RA. Club key: the
  Baseball-Reference team id, the Athletics folded to one franchise (`ewar._fold_team`).
- **Allocation of a player-season to clubs.** The vintage carries one row per player-season (a traded
  player's total). Its value is split across his clubs by his share of exposure in the bWAR stint
  frames, joined on MLBAM id: plate appearances on the bat side, IPouts on the pit side; a player
  whose stints carry zero exposure on that side is split by games, and failing that equally across
  his stints. The same split applies to E, F, H and Hx. bWAR needs no split: each stint row carries
  its own club.
- **Refusals, checked before any statistic (a miss stops the read and writes nothing):**
  1. every primary season has 30 clubs, league RS equals league RA and league W equals league L;
  2. every bWAR stint club and every allocated club is one of the season's 30 standings clubs;
  3. a vintage row with no bWAR stint is unallocated and counted; the read stops if the unallocated
     absolute value exceeds 1.0 win in any season on any series;
  4. per season, the 30 club sums of each of E, F, H and Hx equal the series' league total of its
     allocated rows within 1e-6 wins, and the bWAR club sums equal the bWAR league total of the
     frame's stint rows within 1e-6;
  5. per season, E's league total equals F's within the rounding bound `data/ewar_v3.json` carries
     (EBR_GATE.md 11.10.3: R2 sums to zero), and H's equals F's exactly.

## 4. The estimands

For a series X and club c in season s, with T the club's total sum, Hs its bat-side sum and Ps its
pit-side sum (wins), and the sums over the season's 30 clubs written with a bar:

```
tau_s   = sum_c T_c / sum_c G_c                        the series' own above-replacement wins per team game
W_hat   = G_c / 2 + (T_c - tau_s * G_c)                wins
RD_hat  = RPW_c * (T_c - tau_s * G_c)                  run differential
r_s     = sum_c RS_c / sum_c G_c                       league runs per team game
RS_hat  = r_s * G_c + RPW_c * (Hs_c - eta_s * G_c),    eta_s = sum_c Hs_c / sum_c G_c     (bat side vs runs scored)
RA_hat  = r_s * G_c - RPW_c * (Ps_c - pi_s * G_c),     pi_s  = sum_c Ps_c / sum_c G_c     (pit side vs runs allowed)
RMSE(X, y) = sqrt(mean over the frame of (y - y_hat)^2)
Rsq(X, y)  = 1 - sum (y - y_hat)^2 / sum (y - mean(y))^2      (mean over the frame; nothing is fitted)
```

- **The replacement-level baseline.** tau_s reads each series' replacement level off its own league
  total, so a source is not charged for where its replacement line sits (FanGraphs and
  Baseball-Reference share 1,000 WAR per 2,430 games, but their bat and pit shares differ). The side
  baselines eta_s and pi_s do the same per side. These are one constant per season, series and
  outcome: they move every club of a season together and cannot fit a club. Reported beside, not
  deciding: the fixed published baseline `W0_hat = (0.5 - 1000 / 4860) * G_c + T_c`.
- **Runs per win, the one each source uses:** F at FanGraphs' closed form
  `league_constants.league_totals(s)["rpw"]`; E, H and Hx at the series' own `checks[s].rpw` of
  `data/ewar_v3.json` (EW3-24); B at Baseball-Reference's recovered per-club value
  `ewar.runs_per_win` (`by_team`, falling back to the season's value). Wins use no conversion.
  Reported beside, not deciding: E at F's runs per win, which separates R2 from the conversion, and
  the disclosure that candidate (c) was fitted on club wins against run differential over these
  club-seasons (`docs/ewar/RPW_GATE.md`).
- **The comparison statistic,** per outcome y and comparator X: `d(X) = RMSE(X, y) - RMSE(E, y)`.
  Positive favours eWAR realized. Rsq is printed beside each RMSE and decides nothing on its own.
- **The cells.** Deciding: wins and run differential on the total sums (T). Reported with the same
  intervals, deciding nothing: runs scored on the bat side and runs allowed on the pit side. In the
  primary frame E's bat side equals F's on every row (realized batting is fWAR's), so E against F on
  runs scored is printed as that identity.

## 5. The intervals

- **Three bootstraps, B = 4,000 each, seed 20261023,** each from its own generator seeded 20261023,
  one index draw per replicate shared by every series (paired):
  - season-clustered: the nine primary seasons drawn with replacement with all their club-seasons;
  - club-clustered: the 30 franchises drawn with replacement with all their club-seasons;
  - player-clustered: players (the union of MLBAM ids over every series and both sides; a bWAR row
    without an MLBAM id keys on its Baseball-Reference id) drawn with replacement with all their
    rows, every club sum recomputed from the drawn players with multiplicity, the season baselines
    tau, eta and pi recomputed from the drawn sums, outcomes fixed.
- Per cell and bootstrap: the sd of d over the replicates, the percentile 2.5 and 97.5 points, and
  `lo = d - 1.645 sd`, `hi = d + 1.645 sd`. The three bootstraps' sd are printed before any d.

## 6. The null comparators and the planted check

- **No-change null.** F is E with every departure set to zero. E must beat it (part 7).
- **Permutation null.** E_perm permutes E's nonzero pitching departures (E minus F on the pit side)
  within each season among the pitcher rows that carry one, so the departure's size, its season sums
  and its zero-sum hold and only who carries it changes. 1,000 permutations from a generator seeded
  20261023. E's d(F) must exceed the 95th percentile of the permutations' d(F) on both deciding
  outcomes. This is the check that a departure of this size, placed anywhere, does not by itself
  improve the fit.
- **The planted check, run before the read on the real design and on no real outcome.** It uses the
  frame's club-seasons, games, allocations, F's club sums, F's runs per win and the pool of E's real
  pitching departures, and draws synthetic outcomes. Twenty replicates from a generator seeded
  20261023; in each:
  - the truth departure is one within-season permutation of E's pitching departures, the fake
    departure and the rival departure are two more, drawn independently;
  - `T*_c` is the club sum of F plus the truth departure; `RD*_c = RPW^F_s * (T*_c - tau*_s * G_c) +
    e1`, e1 normal with sd 40 runs; `W*_c = G_c / 2 + RD*_c / RPW^F_s + e2`, e2 normal with sd 4 wins;
  - the truth candidate (F plus the truth departure) and the fake candidate (F plus the fake
    departure) are each scored by part 7's rule against F and against the rival (F plus the rival
    departure), every series at F's runs per win, with B = 500 per bootstrap and 200 permutations.
  - **PLANTED PASS** when the truth candidate reads PASS in at least 16 of 20 replicates and the fake
    candidate in at most 1 of 20. Printed beside, deciding nothing: the same counts with e1's sd at
    60 runs.
  - The identity check: F scored as its own candidate gives d = 0 exactly on every cell and does not
    PASS.
- The noise scales are defaults chosen from published magnitudes (club wins scatter about four wins
  around their run differential's expectation; 40 runs is about four wins of unmodelled spread
  between summed WAR and run differential), not read from these club-seasons. If the true spread is
  larger the check is optimistic about power, which the 60-run line shows.

## 7. The pass rule

Per comparator X in {F, B}:

- **WIN** when, on both deciding outcomes (wins and run differential), `lo > 0` under all three
  bootstraps;
- **LOSS** when, on either deciding outcome, `hi < 0` under all three bootstraps;
- **UNRESOLVED** otherwise.

**PASS** (eWAR realized tracks club outcomes better than both fWAR's and bWAR's sums) when E reads
WIN against F and WIN against B, E's d(F) clears the permutation null on both deciding outcomes, and
the planted check read PLANTED PASS. Each outcome, comparator and bootstrap must hold, so no
multiplicity correction applies. A read whose planted check failed cannot PASS: it is recorded with
its cells and the disposition "UNRESOLVED (the design did not recover a planted departure)". The
side cells (runs scored, runs allowed), H, Hx, E at F's runs per win, the fixed baseline and 2020
decide nothing.

## 8. Where each source misses (descriptive, deciding nothing)

For E, F and B (and Hx when present), the club-season residual `y - y_hat` of each of the four
outcomes, beside four club-season factors:

| Factor | Definition |
|---|---|
| park | FanGraphs' Basic (5yr) park factor / 100 - 1, from `.cache/fangraphs/park_factors_<Y>.json` (the latest complete file at or before the season, as `tools/build_rpw_fit.py` reads it) |
| defense | defensive efficiency from the club's season pitching line (`.cache/team_stats/<Y>_pit.json`): `1 - (H - HR) / (BF - SO - BB - HBP - HR)`, z-scored within season |
| leverage | the bullpen's Leverage Index: the outs-weighted mean of `gmli - 1` over the club's relievers (vintage pitching rows with gamesStarted / gamesPitched below 0.5), each reliever's outs split by part 3's allocation |
| sequencing | `W - Pythagenpat(RS, RA)` at the fixed exponent 0.287 (`rpw_fit.pythag_wins`): wins the run totals do not explain |

Printed per source, outcome and factor: the Pearson r of the residual with the factor, the OLS
slope, and the mean absolute residual in the factor's top tercile minus its bottom tercile; per
source and outcome, the Rsq of the residual on the four factors together; and per source the ten
club-seasons with the largest absolute wins residual. Point values only, no interval and no
verdict. A factor is a description of where a source's sum and the club's record part, not a cause.

## 9. Registered expectations

- **eWAR realized against fWAR.** eWAR realized prices pitchers on runs actually allowed (R2), which
  includes the hits on balls in play and the sequencing that FIP leaves out. Its pitching sums are
  therefore built closer to the runs a club allowed, and a gain over fWAR on runs allowed, run
  differential and wins is expected by construction. A WIN against F says the realized series keeps
  the club's own run accounting better; it is not evidence that eWAR realized measures pitcher
  talent better, and no sentence may say so (part 11).
- **eWAR realized against bWAR.** bWAR also prices pitchers on runs allowed, with its own defense
  and park adjustments and club-level runs per win. No prior is stated; this comparison carries the
  question.
- **Power.** 270 club-seasons in nine seasons. The season-clustered interval rests on nine clusters
  and will be the widest; the planted check states, before the read, whether the design can see a
  departure of R2's size.

## 10. The one read

1. Dry run on fixtures (`test_ewar_team_accounting.py`): every reporting path runs on a synthetic
   frame that includes null values, a missing Hx preview and a short season, and the planted
   machinery recovers a planted departure on a synthetic design.
2. The planted check (part 6) on the real design, which reads no outcome, printed and recorded.
3. The read, ONCE: `python tools/ewar_team_accounting_lab.py --read`, its stdout and stderr teed to
   the task's output directory before anything else runs. It checks the refusals of part 3, prints
   the bootstraps' sd, then the cells, the dispositions, the nulls and part 8's tables, and writes
   `data/_labs/ewar_team_accounting/record.json` (inputs with sha256, the frame counts, every cell,
   the planted check, the dispositions and part 8). A second `--read` refuses while the record
   exists.
4. **Crash protocol.** An exception before scoring began: fix and rerun, recorded. An exception after
   scoring began: STOP without rerunning, write the owner question, record VOID in part 14.
5. Part 14 records the result in a commit of its own.

## 11. What may and may not be claimed, and what a result licenses

- **A PASS licenses nothing served by itself.** It raises one owner question, recorded in the task
  report and `DECISIONS_FOR_OWNER.md`: EWTA-Q1 (a) record only, nothing served (default); (b) a
  registry row `ewar_team_accounting` (provisional, `measurement_only`) with an eval artifact
  copied from the record's cells, no copy sentence; (c) (b) plus one descriptive sentence on the
  eWAR realized glossary entry: "Summed by club, eWAR realized matched the clubs' run differential
  and wins more closely than fWAR or bWAR did over 2016 to 2025 (2020 out)", with its numbers. Any
  served change goes through the flip rule (owner AG4-Q): flag, registry, glossary, copy and tests
  in one commit, the regenerations listed for the integrator.
- **Not PASS:** the record and part 14 only; no owner question is required, the report states the
  dispositions.
- May (after (c)): the sentence above with its frame. May not, under any result: that eWAR realized
  measures talent or skill better; that it predicts anything; a club-level claim about any single
  season; any claim from the side cells, H, Hx or part 8; "validated" or "proven".

## 12. The yardstick for later candidates (EWAR_PITCHING_BLEND)

A later candidate series C (a different pitching basis inside eWAR realized) is scored by
`ewar_team_accounting.score` on the same frame, allocations, estimands, bootstraps (B 4,000, seed
20261023) and nulls, with C in place of E and the comparators F, B and E as recorded by this read.
Its own registration, committed before its read, names its pass rule; this document gives it the
yardstick and the recorded baseline cells, not a verdict.

## 13. Bans, and what was read before this registration

- **Bans.** The read relates no dark betting column to any game outcome or price
  (`docs/diamond-betting.md`); computes no realized MLB statistic by consensus-FV, FV or eFV cell
  (`docs/PROSPECT_ANCHOR_GATE.md`); reads no reserved eFV frame; runs no projections retrain and no
  `backtest.run_backtest`. It reopens nothing on the do-not-reopen lists of EBR_GATE.md parts 12.2
  and 12.3: HEM+ and xHEM+, the S2 shrunk rates, S2b, the global HR shrink, DEM+, S3t, S3c, PE-P,
  the positional ladders v1 to v3, runs per win (each source's own is used, none is fitted) and eBR
  against BsR.
- **What was read before this registration (disclosed).**
  - The eWAR v3 skill look's same-season team wins leg (EBR_GATE.md part 12.2, tracked record): the
    Pearson r of club-season sums of fWAR and of the skill parts' test values with wins, 120
    club-seasons 2021 to 2024. It did not include R2 or eWAR realized.
  - `docs/ewar/RPW_GATE.md`'s read: club wins against run differential, 2016 to 2026, and the
    pitcher leg's stint runs-allowed ledger (arms L and D). No WAR sum was related to an outcome
    there.
  - eWAR v2's own team gates (`ewar.gate_team_wins`, `ewar.gate_team_runs`): eWAR v2 (Baseball-
    Reference frame, FIP-priced pitching) against bWAR on club wins and runs, in eWAR v2's build
    record. eWAR v2 is not a series of this read.
  - The eWAR site-wide calibration's measurement band (`docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md`
    9.1): the player-level disagreement of published fWAR and bWAR. No club outcome.
  - To write this document the writer read the structure and coverage of the inputs only: the
    vintage rows of 2016 to 2025 all join a bWAR stint by MLBAM id on both sides (zero unallocated
    rows); the standings carry 30 clubs per season; `data/ewar_v3.json` carries runs per win
    10.6261 for every season. No club-season sum of any series was computed.

## 14. Results

### 14.1 2026-10-22: the read, run once (lab at 6c1e6162; local 2026-10-22 20:14, UTC 2026-10-23 00:14)

`python tools/ewar_team_accounting_lab.py --read`, stdout and stderr teed to the task's output
directory; the record is `data/_labs/ewar_team_accounting/record.json`. Inputs by sha256: the frozen
vintage `02232201...`, `data/ewar_v3.json` `40ea0196...`, the xHEM+ preview `36ba7b43...`, the bWAR copy
bat `e9571c42...` and pit `3279bfbd...`. Every refusal of part 3 held: 270 club-seasons, 3,760 players,
16,976 vintage rows (0 null, 0 unallocated), 18,809 bWAR stint rows, 7,035 R2 departure rows. No
exception; runtime 21 s.

**VERDICT: NOT PASS.** eWAR realized reads UNRESOLVED against fWAR and UNRESOLVED against bWAR. The
planted check read PLANTED PASS (truth 20 of 20, fake 0 of 20 at 40 runs; 20 of 20 and 0 of 20 at 60
runs; identity check all d zero, NOT PASS) and the permutation null was cleared on both deciding
outcomes, so the design could see a departure of R2's size and the read is not underpowered: eWAR
realized's team sums are not closer to club wins or run differential than fWAR's or bWAR's.

Points, primary frame (RMSE, Rsq; wins in wins, the rest in runs; each series at its own runs per
win):

| Series | Wins | Run differential | Runs scored (bat side) | Runs allowed (pit side) |
|---|---|---|---|---|
| E, eWAR realized | 5.353, 0.834 | 41.264, 0.903 | 48.279, 0.599 | 41.193, 0.782 |
| F, fWAR | 5.111, 0.849 | 39.267, 0.912 | 44.591, 0.658 | 51.845, 0.654 |
| B, bWAR | 4.852, 0.863 | 33.058, 0.938 | 49.690, 0.575 | 57.276, 0.578 |
| H, headline as served (reported) | 5.111, 0.849 | 39.988, 0.909 | 48.279, 0.599 | 51.004, 0.665 |
| Hx, headline with xHEM+ (reported) | 5.302, 0.837 | 42.487, 0.897 | 51.887, 0.537 | 51.004, 0.665 |
| E at fWAR's runs per win (reported) | 5.353, 0.834 | 36.524, 0.924 | 44.591, 0.658 | 40.782, 0.786 |

The fixed published baseline gives the same wins RMSE as the league-reconciled one for every series.

d = RMSE(comparator) - RMSE(E), positive favours eWAR realized; sd per bootstrap (season, club,
player), B 4,000:

| Comparator, outcome | d | sd season / club / player | lo (worst) | hi (best) |
|---|---|---|---|---|
| F, wins (deciding) | -0.243 | 0.234 / 0.312 / 0.339 | -0.801 | 0.315 |
| F, run differential (deciding) | -1.996 | 1.837 / 3.502 / 4.147 | -8.819 | 4.826 |
| F, runs scored (reported) | -3.688 | 0.608 / 0.388 / 0.915 | -5.193 | -2.184 |
| F, runs allowed (reported) | +10.652 | 2.401 / 4.121 / 3.646 | 3.874 | 17.431 |
| B, wins (deciding) | -0.501 | 0.106 / 0.365 / 0.419 | -1.191 | 0.188 |
| B, run differential (deciding) | -8.206 | 1.867 / 3.973 / 5.155 | -16.686 | 0.274 |
| B, runs scored (reported) | +1.411 | 1.818 / 2.839 / 3.216 | -3.879 | 6.701 |
| B, runs allowed (reported) | +16.083 | 2.357 / 4.386 / 3.665 | 8.869 | 23.297 |

(lo is the smallest d - 1.645 sd over the three bootstraps, hi the largest d + 1.645 sd.) Against bWAR
the season-clustered interval sits below zero on both deciding outcomes and the club- and
player-clustered ones reach just above it, so the cell is UNRESOLVED, not LOSS, by part 7's rule.

- **Permutation null:** E's d(F) -0.243 wins against the permutations' 95th percentile -0.620 (mean
  -0.902), and -1.996 runs against -10.242 (mean -13.020): cleared on both. R2 placed on the pitchers
  who earned it is far closer to the clubs' records than the same departures placed at random, yet
  not closer than fWAR without them.
- **Runs scored:** E's bat side equals fWAR's in this frame; its d against F (-3.688) is the runs-per-
  win conversion alone (10.6261 against FanGraphs' 9.52 to 10.30): at fWAR's runs per win the cell is
  exactly 0.
- **Runs allowed:** E's pit side is closer to the clubs' runs allowed than fWAR's (+10.652) and
  bWAR's (+16.083) under every bootstrap, as part 9 expected by construction (R2 prices runs allowed).
  The gain does not carry to the totals (below).
- **Reported, deciding nothing:** H equals F on wins exactly; its run-differential gap to F (-0.721)
  is the conversion. Hx reads LOSS against F and against B under part 7's rule (wins d -0.191 and
  -0.450; run differential -3.220 and -9.429): the xHEM+ part moves batting value away from the runs
  clubs scored, which is not its claim (it is a predictive part) and changes nothing about EW3-51. E at
  fWAR's runs per win: run differential d +2.744 against F and -3.466 against B, both UNRESOLVED.
- **2020 alone** (30 club-seasons, points only): wins RMSE E 2.813, F 3.413, H 3.413, Hx 3.493, B
  3.625; run differential E 21.099, F 24.423, H 25.109, Hx 28.032, B 31.761.

**Where each source misses (part 8, descriptive).** Pearson r of the club-season residual with each
factor (run differential residual; wins residual where named):

| Source | park | defense | bullpen Leverage Index | sequencing (wins) | joint Rsq, run differential |
|---|---|---|---|---|---|
| E | +0.492 | -0.364 | -0.219 | +0.720 | 0.293 |
| F | +0.092 | +0.451 | +0.088 | +0.651 | 0.297 |
| B | -0.148 | +0.339 | +0.122 | +0.727 | 0.137 |
| Hx | +0.270 | +0.355 | +0.024 | +0.597 | 0.332 |

- Every source's wins misses are mostly sequencing (wins the run totals do not explain; r 0.65 to
  0.73), which no WAR sum carries.
- fWAR's and bWAR's run-differential misses sit with defense (r +0.451 and +0.339: clubs with a high
  defensive efficiency outperform the sum), and almost not with park.
- eWAR realized's run-differential misses sit with park (r +0.492) and with defense in the opposite
  direction (r -0.364). Colorado is three of E's ten largest wins misses (2018 +14.3, 2024 +13.4,
  2023 +12.5, all under-credited). On the sides, E's runs-allowed residual carries less park (r
  +0.326) than fWAR's (+0.545) and bWAR's (+0.585) while its runs-scored side is fWAR's (+0.715 at
  the same conversion), so the two sides of eWAR realized are not on the same park footing; the
  defense sign flip says the pitching side's put-back of fielding runs (Fld + Frm, 11.3.3) and the
  hitting side's fielding runs do not net out by club. This read measures where the sums part from
  the records; it does not test R2's park factor or fielding put-back, and it records no defect.
- Largest wins misses (residual, wins): E 2023 SDP -16.7, 2021 SEA +15.8, 2016 TEX +15.5; F 2021 SEA
  +17.8, 2016 TEX +17.8, 2016 MIN -14.5; B 2021 SEA +16.4, 2025 CLE +15.9, 2018 BAL -13.8.

**What this licenses.** NOT PASS: nothing is served, no owner question is raised (part 11), and no
sentence comparing eWAR realized's team accounting with fWAR or bWAR may be written. The recorded
cells are the baseline EWAR_PITCHING_BLEND reads (part 12).
