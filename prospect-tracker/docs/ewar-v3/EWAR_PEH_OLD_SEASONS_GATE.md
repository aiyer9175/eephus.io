# PE-H on the old seasons: one registered read of the hitter pitch-economy part on 2002 to 2015 (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EWAR_PEH_OLD_SEASONS (owner decision EW3-50). This document is
committed ALONE, before any number of its estimands is computed: no PE-H residual, delta, test value,
target, rank correlation or club-season sum exists for any season of its frame, and the code that
computes the read is not committed at this commit. Nothing in this commit changes a model, an exporter,
a flag or a served artifact. Part 11 is filled in afterwards; nothing above part 11 may be edited once
anything is written below it, and a change is a dated amendment under part 11, committed alone. Its
pin test is `test_ewar_peh_old_seasons_gate.py`.

## 0. What kind of decision this is

- **One more read of an already registered part, on seasons it has never touched.** The owner's
  question (EW3-50): can eWAR be made better than fWAR and bWAR without redoing failed work? One of the
  four approved arms is PE-H, the hitter pitch-economy part of `docs/ebr-2026-09-30/EBR_GATE.md` part
  11.4.3, scored on the fresh seasons 2002 to 2015. In the skill look (EBR_GATE.md 12.2) PE-H read
  SMALL WIN on both cells, a positive gap under the +0.02 margin, and in the holdout (12.3) EQUIVALENT
  on both; it was not admitted. Thirteen fresh season pairs carry about three times the look's pairs,
  so this read asks whether the look's small positive gap holds on seasons no PE-H number has touched
  and whether it reaches the margin there.
- **The part is not changed.** Its definition (11.4.3), its frozen constants (`pitch_economy.py`:
  DELTA_TTO 0.01847965, K_CL 236.41, K_P 110.95, fitted once on the 2018 and 2019 corpus seasons) and
  its arithmetic (`tools/pitch_economy_lab.py`'s walk, class means and residuals;
  `tools/swar_targets.py`'s `pe_h_deltas`) are the skill look's, unchanged. Nothing is refitted on the
  old seasons.
- **Not a reopened arm.** EBR_GATE.md parts 12.2 and 12.3 stand as written. This read does not rescore
  HEM+ or xHEM+, the S2 shrunk rates, S2b, the global home-run shrink, DEM+, the S3t triangulation,
  S3c, PE-P, the positional ladders v1 to v3, the runs-per-win fit or eBR against BsR (part 9).
- **Built dark.** The read writes its tracked record to `docs/ewar-v3/peh_old_seasons_eval.json` and
  its numbers to part 11. No registry row, glossary entry, page, flag or served artifact is added or
  moved by this task. A pass is an OWNER QUESTION (part 6), never an automatic admission.

## 1. Decision record

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| EW3-50 | Make eWAR better than both fWAR and bWAR without redoing failed work | four arms approved: EWAR_TEAM_ACCOUNTING, EWAR_PITCHING_BLEND, EWAR_UNCERTAINTY_BAND, EWAR_PEH_OLD_SEASONS (this document) | answered 2026-10-22 (`DECISIONS_FOR_OWNER.md`, EW3-50) |
| EW3-19 | Whether pitch economy is a candidate part of eWAR v3 | both PE-P and PE-H registered (EBR_GATE.md 11.4) | answered 2026-10-15 |
| EW3-23 | What a skill part is scored against | next-season realized runs of the part's own component; team runs and wins as a non-inferiority guard (EBR_GATE.md 11.2) | answered 2026-10-15 |
| EW3-5 | Look days and registered dates | waived: the read runs on any date once its data exists | answered 2026-10-14 |
| AG4-Q | What a flip commit carries | the flag, registry, glossary, copy and tests only; regenerations are listed for the integrator | answered 2026-10-22 |

Defaults this document applies, named so the orchestrator records them: the frame's predictor seasons
2002 to 2014 (every pair inside 2002 to 2015); B1 at the look's frozen PE-H constant k = 427 PA (not
refitted on the old seasons); the club-clustered companion interval and its pass clause (part 3.5);
the season admission thresholds of part 3.3; the planted share 0.5 of part 4; the record path above.

## 2. What is cited, not re-scored

From EBR_GATE.md part 12, on predictor seasons 2021 to 2024 (the look, 2026-10-19) and 2025 (the
holdout, 2026-10-21), hitters 200 PA in both seasons, B = 2,000, seed 20261008:

| Read | Pairs | PE-H rate | PE-H total | Team guard | Admitted |
|---|---|---|---|---|---|
| Skill look | 1,071 | SMALL WIN, gap +0.01304 (+0.00604 to +0.02029) | SMALL WIN, gap +0.01341 (+0.00659 to +0.02069) | NON-INFERIOR | no |
| Holdout | 263 | EQUIVALENT, gap +0.00216 (-0.01311 to +0.01624) | EQUIVALENT, gap -0.00226 (-0.01899 to +0.01375) | NON-INFERIOR | no |

These numbers are quoted from the record as written. No cell of either read is recomputed here, and
the frame below shares no season with either.

## 3. The frame and the statistic

### 3.1 Seasons, population, floors

- **Pairs (Y, Y+1)** for predictor seasons Y = 2002 to 2014, outcome seasons 2003 to 2015. MLB
  player-seasons by MLBAM id. Hitters with 200 or more PA in both seasons (the StatsAPI season line's
  PA, `.cache/fa_statsapi_hitting_<Y>.json`). Pitcher-batters (position P on the season line) carry
  d_PEH = 0, as 11.4.3 has it; two-way players are hitters.
- No season of the frame is a season of the skill look, its holdout, its B1 fit (2018 to 2019) or the
  constants' fit (2018 and 2019).

### 3.2 B0, the target and the season's solved weights

```
B0_i     = wRAA_i(Y) = ((wOBA_i - lgwOBA_Y) / scale_Y) * PA_i       on season Y's solved weights
test_i   = B0_i + d_PEH,i(Y)                                       11.4.3, unchanged
tgt_i    = wRAA_i(Y+1) + W_i(Y+1)                                  11.4.4, unchanged
W_i(Y+1) = w_Y+1 * Pres_i(Y+1)                                     realized starter wear, unshrunk
rate cell: per PA (test / PA in Y against tgt / PA in Y+1); total cell: in runs
```

- **The solved weights.** For 2011 to 2015 they are `data/league_constants.json`'s (solved, published,
  unserved before 2015). For 2002 to 2010, which that artifact does not carry, they are solved by the
  same function (`league_constants.solve_season`, the wRAA and wOBA identities) on the frozen fWAR
  vintage's `woba` and `wRaa` rows (`data/fwar_vintage.json`, vintage 2026-10-02-a020cf64844a, the
  same StatsAPI sabermetrics feed, frozen per season). **Receipt, before any number:** the vintage
  solve must reproduce the artifact's 2011 to 2015 scale and league wOBA within 0.0005 and every
  weight within 0.002, else STOP.
- wOBA_i is computed from the season line's counts on those weights (`pitch_economy_lab.woba_of`, the
  arithmetic of `swar.woba_actual`).

### 3.3 The part's inputs, and which seasons enter

- **Play-by-play.** The winProbability payloads of every final regular-season game: 2011 to 2015 from
  `.cache/win_prob_hist` (eBR's history fetch); 2002 to 2010 fetched for this read by
  `tools/fetch_win_prob_old.py` into `.cache/win_prob_old`, through the paced receipt fetcher of
  `tools/fetch_win_prob_hist.py` (one request a second, the house User-Agent, a receipt per game, no
  request inside the 06:00 to 11:00 UTC nightly window). The payloads are flattened by
  `tools/build_pbp_corpus.py` into a separate corpus under `.cache/peh_old/corpus` (never
  `.cache/pbp_corpus`, which the win-expectancy table pools).
- **The runner record.** 2011 to 2015: `.cache/pbp_runners` as eBR built it. 2002 to 2010:
  `tools/build_runner_moves.py`'s `build_season` on the new payloads into `.cache/peh_old/runners`,
  with no re-fetch.
- **RE24 and RE288 per season.** RE24_s is eBR's shrink of the season's raw table toward its frozen
  pool (`ebr.shrunk_table`, K from `.cache/ebr/frozen/ebr_v1_pool.json`), lambda_s is
  `ebr.season_lambda` of the season against that pool, and RE288_s = RE24_s + lambda_s x the frozen
  pooled count departure (`.cache/count_value/frozen/count_value_v1_pool.json`), exactly as
  `tools/build_count_value.py` builds a season. **Receipt, before any number:** the same code path
  rebuilds 2019 from the live corpus and record and must reproduce `data/count_value.json`'s 2019
  RE288 and RE24 to the fourth decimal, else STOP.
- **The starter-wear price w_s** = (F_RP,s - F_SP,s - T9_s) / (27 * L_ppo,s,SP) from the season's
  pitching lines and start and relief split lines (`.cache/pitch_rates/pitching_sprp_1_<Y>.json`; 2002
  to 2007 fetched for this read through `pitch_rates.fetch_role_splits`) and `league_constants
  .league_totals` (FIP constant, league PA and IP), as `swar_targets.Readers.pitch_economy_wear`
  computes it.
- **Season admission.** A season enters only when (a) the RE288 ledger identity holds on at least
  0.999 of its walked plate appearances (11.4.6's `IDENTITY_SHARE`), (b) the corpus holds at least
  0.99 of the pitches its season pitching lines record, and (c) the runner record holds at least 0.99
  of its listed games net of cancelled games. A season that fails leaves the frame on both sides (as
  Y and as Y+1), and the record lists it with its receipt before any statistic. Fewer than 6
  surviving predictor seasons is a STOP.

### 3.4 The cells

- **Holm family {PE-H rate, PE-H total}, k = 2.** Spearman gap of the test value over B0 against the
  target, convention v2 primary (players resampled with all their pairs, stratified by predictor
  season, the target z-scored within outcome season), convention v1 (an iid pair resample on the raw
  target) required to agree in sign. B = 4,000, seed 20261023. MDE95 = 1.645 bootstrap sd, printed
  with the sd, the half-width and n for every cell before any gap.
- **The dispositions and their precedence** are EBR_GATE.md part 9.5's as amended by part 11, computed
  by `swar_lab.disposition` unchanged: WIN (Holm rejects, lo95 above 0, the gap at least +0.02; WIN
  (components) when also lo95 above 0 against B1 and the twin fails), SMALL WIN, LOSS, EQUIVALENT,
  UNRESOLVED, the first that holds.
- **B1** = (B0 + m k) / (PA + k) with k = 427 PA, the PE-H constant the look froze (fitted on the 2018
  to 2019 pair from B0 and the target only), and m the predictor season's PA-weighted mean B0 rate at
  the floor.
- **The twin**: the delta permuted across players within (predictor season, PA decile) and added back
  to B0; its gap's lo95 must be at or below 0.
- The cells are computed by `swar_lab.prep_primary`, `finish_primary` and `decide_family`, the look's
  own code, called with this read's frame, B and seed.

### 3.5 The club-clustered companion interval

Beside each cell, the same gap's 95 percent interval under a club-clustered bootstrap: franchises
(the franchise of the player's club with the most PA in Y+1, `swar_targets.franchise`) drawn with
replacement with all their pairs, B = 4,000, seed 20261023 + 202. It decides one clause of part 5 and
nothing else.

### 3.6 The sensitivity guard

The rate cell's gap on wRAA(Y+1) alone, W left out, in the same bootstrap; it must not be LOSS (hi95
below 0), as 11.4.4 has it.

### 3.7 The team guard

EBR_GATE.md 11.2.4 unchanged except its seasons, B and seed: club-seasons 2003 to 2015 (outcome
seasons), runs scored, run differential and wins; the frame series is fWAR(Y) from the frozen vintage,
the part's series fWAR(Y) + d_PEH / RPW_Y (RPW_Y from `league_constants.league_totals`), bWAR as a
reference; roster weighting by Y+1 PA and IP by club from `war_source`'s last-good Baseball-Reference
stint cache; NON-INFERIOR when dT - 1.645 sd is above -0.02 under both the player-clustered and the
club-clustered bootstrap for every outcome. B = 4,000 each, seed 20261023, through
`swar_targets.team_guard`. The stint cache's club codes of these seasons are read under the
standings' franchise codes (ANA as LAA, FLA as MIA, TBD as TBR, MON as WSN), and the Montreal Expos'
standings rows (2002 to 2004), which `ewar.standings` cannot name, are read as WSN. Every outcome
season must carry 30 clubs, else STOP. The share of the frame's Y+1 PA that lands on a standings
club is printed beside.

### 3.8 Reported beside, deciding nothing

The secondary estimand of 11.2.5 (published fWAR(Y+1), B0 fWAR(Y), B1 at k = 662 PA); PE-H's two terms
scored one at a time (point gaps); the season receipts (identity share, pitch and game coverage, w_s,
the zero-sum check).

## 4. Controls: the null comparator and the planted recovery

Run on the real frame, after the floors and before any real cell, through the same cell code, B and
seed:

- **Null comparator.** The delta set to 0 for every pair (the test value equals B0). It must not read
  WIN or SMALL WIN on either cell.
- **Planted recovery.** The delta set to 0.5 x PA_i(Y) x (tgt_i / PA_i(Y+1) - the outcome season's
  PA-weighted mean target rate) for every pair: half of each pair's own Y+1 deviation, in Y's
  exposure. It must read WIN (components) on both cells, and its twin must fail.
- **A failed control stops the read before any real cell is scored**; the record is written VOID with
  the controls' dispositions, and nothing is admitted. The controls run once, inside the read.

## 5. Admission rule

PE-H's read PASSES only when, together: the rate cell is WIN (components); the rate cell's
club-clustered lo95 is above 0; the total cell is not LOSS; the sensitivity guard is not LOSS; and the
team guard is NON-INFERIOR. Anything else is NOT PASS, and PE-H stays out of eWAR, which carries no
pitch-economy term (EBR_GATE.md 11.4.5).

## 6. What a result licenses

- **NOT PASS.** Nothing changes. The record and part 11 carry the numbers; no copy sentence is
  licensed.
- **PASS.** Nothing is served by this task. PE-H's admission is an OWNER QUESTION, because the look
  (SMALL WIN) and the holdout (EQUIVALENT) did not pass and this read would be the only pass: (a) keep
  PE-H out (the default until answered); (b) build PE-H into eWAR v3 dark behind a flag that defaults
  off, flipped later by a flip commit under AG4-Q; (c) register a fresh confirmation on the 2026
  predictor season first. The copy sentence a later flip may carry is 11.2.6's table with
  [component's runs] read as "batting runs plus starter-wear runs", naming this frame.
- **VOID** (a failed control or an exception after scoring began): nothing is admitted and the read is
  not rerun.

## 7. Power, stated before the read

No statistic of the frame exists at this commit. The look's MDE95 was 0.0060 on 1,071 pairs; the old
seasons carry about 260 qualifying pairs a season, about 3,400 over the thirteen pairs, so MDE95
should fall near 0.0035. That is far below the +0.02 margin a WIN needs: a NOT PASS on this frame
reflects the size of the effect, not a lack of pairs. The registered expectation (a prediction,
not a measurement): the rate cell's point gap is positive and near the look's +0.013, so the cell
reads SMALL WIN or EQUIVALENT, not WIN; the planted control passes; the null control does not read
WIN; the team guard is NON-INFERIOR.

## 8. Crash protocol and clock

- The operator tees stdout and stderr to the writer's output directory before the run. An exception
  after scoring began writes a VOID record and exits 3; no rerun. A second run of the read is refused.
- Look days are waived (EW3-5). The read runs once the 2002 to 2010 payloads are on disk and the
  inputs are built, which is the only wait (data that does not exist yet).

## 9. Do not reopen

EBR_GATE.md parts 12.2 and 12.3 close HEM+ and xHEM+, the S2 shrunk rates, S2b, the global home-run
shrink, DEM+, S3t, S3c, PE-P, the positional ladders v1 to v3, the runs-per-win fit and eBR against
BsR. None of them is computed, scored or cited as evidence by this read, and none of PE-H's constants
or definitions changes. A NOT PASS here closes PE-H on the old seasons; it is not rerun with another
frame, floor, constant or margin.

## 10. What was read before this registration

- The fetch receipts and counts of `.cache/win_prob_old` (2002 to 2010, in progress) and a probe of
  one game in each of 2002, 2005, 2008 and 2010 showing that the payloads carry pitch-level events.
- The corpus rows of 2011 to 2015 built from `.cache/win_prob_hist` (plays, pitches, events per
  season; the corpus pitches equal the season pitching lines' pitches in each of the five seasons).
- The season-table receipt (2019 rebuilt by part 3.3's path reproduces `data/count_value.json` to the
  fourth decimal) and the season tables' lambda_s for 2011 to 2015 (0.9493, 0.9626, 0.9248, 0.9054,
  0.9568) with no count-monotone violation.
- The start and relief split lines of 2002 to 2007 and their pitch totals against the season lines
  (equal in 2002, 2005 and 2007, the seasons checked).
- A fixture dry run of the read's code on synthetic rows.

None of these is a PE-H residual, delta, wRAA pair, target or statistic of the frame. The look's and
the holdout's PE-H numbers (part 2) were read, as part 0 states.

## 11. Results

(empty at registration)
