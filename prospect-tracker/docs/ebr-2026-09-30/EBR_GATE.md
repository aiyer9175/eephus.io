# eWAR v3 gate: eBR and the skill parts

Pre-registration of eWAR v3, the house WAR on FanGraphs' frame: its base, its six candidate parts
(two outcome parts from eBR, our positional ladder, and three shrunk-skill parts from HEM+ and
xHEM+, SEM+ and REM+, and DEM+), the BEM+ index test, and the two looks that decide which parts
enter.

STATUS: REGISTERED, RESULTS EMPTY. Committed 2026-10-08 by queue task EBR_1_REGISTRATION. This
document only registers: it computes nothing, and nothing in it is a result.

Written on the commit date, before any year-to-year, split-half or forward statistic of eBR, of any
of its parts, or of any eBR-like construct exists, before any forward statistic of a skill delta, a
ladder delta or any WAR rebuilt from shrunk components exists, and before the code that computes
any of them exists.

Owner asks, verbatim:

- 2026-09-30, baserunning: "Can we build our own baserunning metric for WAR (our own version of
  BsR, call it eBR (eephus baserunning), and use it for eWAR?"
- 2026-09-30, ask A: "Can we also look to potentially use our own metrics in eWAR further (some
  cummulative version of HEM+ for hitting, SEM+ for starters, REM+ for relievers, DEM+/will's
  defensive metrics/our in-house calculated positional adjustments for position players, etc?"

The owner's answers of 2026-10-01 (part 1) make the two asks ONE series: eWAR v3, "ONE house WAR,
part outcome (eBR) and part shrunk skill, which exists whatever eBR's look says, each part admitted
only on a clear win under its own clause".

This file fixes the base, every candidate part's definition, the identity checks, the descriptive
checks, the two looks, what each outcome licenses and what may be claimed, so that nothing is tuned
after a look. It is pinned by `test_ebr_gate_registration.py`. The evidence behind every choice is
the eWAR v3 plan bundle (`_finalpass_2026-09-24/part8/ebr/`: `PLAN.md`, `UNIFY_LOG.md`,
`ebr_metric.md`, `integration.md`, `ewar_internals.md` and their scripts), the Baserunning plan
(`part8/baserunning.md`) and the skill lane (`part8/xwar.md`, whose framing as a separate series is
superseded by the owner's answers and whose formulas and clauses this file carries as amended).

## 0. What kind of decision this is

- **eWAR v3 is one house WAR on FanGraphs' frame** (owner answers EBR-Q0 (a), SWAR-Q0 (b) and
  SWAR-Q1 (b), 2026-10-01). Its base is FanGraphs' published WAR per season, read from the fWAR
  label epoch's frozen per-season vintage. Each admitted candidate part is a named, zero-sum
  departure from that base. eWAR v3 EXISTS whatever the looks say: the served column is fWAR with
  the admitted parts swapped in, a candidate part that is not admitted leaves FanGraphs' own number
  in place, and when no part is admitted the column equals fWAR on every row and its label says so
  (part 9.7). It is display only, a column beside the displayed WAR, and never labelled plain
  "eWAR".
- **The candidate parts and the index test.** Each has its own named clause, pre-committed null,
  frame, statistic, margin, Holm family and disposition. No correction is made across parts: each
  part decides only its own admission.

| # | Candidate part | Kind | Clauses | Pre-committed null | Frame | Statistic | Margin | Holm family | Admitted when (under part 1's answers) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Baserunning: eBR's steal and extra-base runs in place of FanGraphs' BsR | outcome | 2, 3, 5.1 to 5.3, 6.1 | d is not above +0.02 | the six season pairs of 5.1, 300 PA in both seasons | Leg E: mean per-pair Spearman self-persistence of (SB + XB runs) per PA minus BsR's | 0.02, interval d +/- 1.645 sd | its own, one test | Leg E SHIP, Leg T passes, the twin RESOLVED_LOSS, d above 0 on frame U and on the club changers (EBR-Q1 (a)) |
| 2 | Double plays: eBR's DP runs added (FanGraphs' served WAR has no double-play part since 2016) | outcome | 2, 5.4, 6.2 | d_DP is not above +0.02 | as 1 | E-DP: the same statistic, eGDP per PA against Baseball-Reference's `runs_dp` per PA | as 1 | its own, one test | E-DP SHIP with its guards, DP-1 and DP-2 pass, the E-DP twin RESOLVED_LOSS (EBR-Q2 (a) under EBR-Q1 (a)) |
| 3 | Position: our per-season ladder in place of FanGraphs' positional adjustment | forward (a convention) | 9.4 S4, 9.5, 9.6 | the gap is not above 0 | predictor seasons 2021 to 2024, hitters 200 PA in both seasons | Spearman gap of fWAR + the part's delta over fWAR(Y) in ranking fWAR(Y+1), per PA and in total | point gap +0.02 | {H-rate, H-cum}, k = 2 | WIN (components) on H-rate, H-cum not LOSS (SWAR-Q0 (b), EWV3-Q1) |
| 4 | Batting: two arms, HEM+'s shrunk event rates and xHEM+'s Savant xwOBA | skill | 9.4 S1, 9.5, 9.6 | per arm, the gap is not above 0 | as 3 | as 3 | as 3 | {HEM+ H-rate, HEM+ H-cum, xHEM+ H-rate, xHEM+ H-cum}, k = 4 | an arm's H-rate WIN (components), its H-cum not LOSS; both arms qualifying go to EWV3-Q2's rule (SWAR-Q3 (c)) |
| 5 | Pitching: SEM+'s and REM+'s shrunk strikeout, walk, hit-by-pitch and home-run rates, starters and relievers on the start-share blend | skill | 9.4 S2, 9.5, 9.6 | the gap is not above 0 | predictor seasons 2021 to 2024, pitchers 50 IP in both seasons | as 3, per IP and in total | as 3 | {P-rate, P-cum}, k = 2 | P-rate WIN (components) with era transport, P-cum not LOSS; the home-run term set first by its own transport clause (EWV3-Q1) |
| 6 | Fielding: DEM+'s shrunk fielding runs | skill | 9.4 S3, 9.5, 9.6 | the gap is not above 0 | as 3 | as 3 | as 3 | {H-rate, H-cum}, k = 2 | WIN (components) on H-rate, H-cum not LOSS (EWV3-Q1) |
| BEM+ | A 100-scale baserunning index | index | 5.8 | its PASS clauses fail | 5.8 | forward Spearman gaps, gate X-B1 | 5.8 | its own | served only on PASS (EBR-Q3 (a)); never a part of eWAR v3 |

  In parts 2 to 6, "part" alone means one of eBR's display parts (SB, XB and DP runs, part 2.7); a
  "candidate part" is a row of this table.
- **Two kinds of candidate part, two kinds of test, and why.** Candidate parts 1 and 2 are OUTCOME
  parts: they record what a runner did on the bases in one season, so their claim is about the
  season that happened. Baserunning has no next-season outcome independent of a construct (the only
  next-season targets are the rival series, and forecasting next season's BsR favours BsR's own
  construct, part 5.2), so each series' own persistence on the same runners decides, with the
  club-changers guard covering persistence's blind spot, a bias that repeats (the outcome look,
  part 5). Candidate parts 4, 5 and 6 are SKILL parts: each is a shrunk estimate of a rate, which is
  a forecast by construction, and its only claim is about the next season. Shrinkage raises
  self-persistence mechanically, so persistence would reward the shrink and test nothing; the honest
  test of a forecast is whether it ranks the next season's published fWAR better than fWAR itself
  did (the skill look, part 9.5). Candidate part 3, our positional ladder, is a convention, not an
  event record and not a shrink; it has no construct-free same-season target either, and the owner's
  ruling puts it on the skill look's forward test. Its target, published fWAR(Y+1), carries
  FanGraphs' own positional adjustment, so that test leans toward the incumbent and its honest prior
  is a LOSS or UNRESOLVED (part 9.5, registered expectations).
- **eBR is descriptive.** It counts the runs a player added or cost on the bases in one season
  against an average runner in the same spot. It predicts nothing. Its registry rows are
  `provisional` with `provisional_kind` `measurement_only`.
- **eBR ships first as its own stat** (the Baserunning section on MLB Stats and a section on player
  cards), after the outcome look and the section build, under every answer below.
- **What rides on this gate:** which candidate parts eWAR v3 carries, and BEM+. Every admission is
  display only. The displayed WAR stays eWAR v2 (the owner's EPOCH-Q4 answer of 2026-09-30, "Keep
  eWAR v2 shown"), and nothing in this file changes it. Under every outcome no training label,
  fitted artifact, priced number, board rank, Franchise grade, F-SCORE input or betting input reads
  eBR, a skill delta, a ladder delta or eWAR v3.
- **Copy** comparing eBR with FanGraphs' BsR follows from the outcome look (part 6.3); copy about a
  skill or position part follows from the skill look (part 9.6).
- **Not the fWAR epoch.** The TRAINING label basis is published fWAR, the owner's basis decision of
  2026-09-17 (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 0); under EPOCH-Q4 and the
  orchestrator's implementation ruling EPOCH-Q4-IMPL (R1a) the epoch flips the label and the
  fingerprint's `label=` term to `fwar@<vintage id>` at step D + U, while every display door keeps
  provider `ewar_v2`, eWAR v2's nightly keeps running, and fWAR appears as a reference column beside
  eWAR v2 only after step Z (task EPOCH_FWAR_REFERENCE_COLUMN). No candidate part is on that epoch's
  ride list ("any W1.3 departure of the eWAR v3 replica (display only; Z4)" may not ride, its part
  6). Every candidate part is that document's clause (k) item Z4: display only. Only a Leg E SHIP
  with its guards (candidate part 1) makes a departure eligible for the 2027 label epoch's own
  registration; candidate parts 2 to 6 never become label candidates under this registration (for
  the skill parts, a more persistent label helps the naive baseline more than the model, the R3b
  lesson, `ewar.py:68-76`, which any later label registration must pre-state).
- **Not the Management number.** /management/ prices the steal DECISION on win expectancy with a
  league-average runner and leaves out two-out attempts. eBR prices the runner's realized runs on run
  expectancy, where the third out is worth zero runs exactly, so no attempt is left out. The two are
  never summed, combined or shown as one number.
- **The standing rule this gate implements** (owner, 2026-09-09,
  `docs/master-plan-2026-09-09-fangraphs-ewar-betting.md` Part 1): "Every departure from fWAR is an
  IMPROVEMENT CLAIM carrying its own pre-registered gate; where no gate resolves, the component stays
  fWAR-faithful." Every candidate part of this file is such a departure with such a gate. Part 1
  records that the owner kept that rule for baserunning (EBR-Q1 (a)) and for the skill and position
  parts (SWAR-Q1 (b): "each part admitted only on a clear win under its own clause"), and that a
  double-play part (which FanGraphs' served WAR no longer carries) is added, which is a recorded
  relaxation of that rule whatever part 5.4's contrast reads.

## 1. Decision record

The writer re-reads `C:/Users/noah/baseball-projects/_audit_2026-09-09/DECISIONS_FOR_OWNER.md` on
the commit date and fills the "Status" cells. The eight answers of 2026-10-01 below were recorded
before this draft; a recorded answer that differs from the one written here stops the commit. An
unanswered question that carries a default is recorded as its default and marked UNANSWERED; the
default rows are also written to `DECISIONS_FOR_OWNER.md` under a dated heading. A recorded default
counts as answered wherever a later task requires one of those questions to be answered. Re-read on
2026-10-08: every row below holds a recorded owner answer, so no row is marked UNANSWERED and no
default was recorded.

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| BR-Q1 | A site-built baserunning value, or published values only | eBR is built and served | answered by the owner's ask of 2026-09-30 (quoted above) |
| EPOCH-Q4 | Which WAR the site displays after the fWAR label epoch | "Keep eWAR v2 shown": eWAR v2 stays the displayed WAR with fWAR as a reference column; the training label is fWAR either way | answered 2026-09-30 (`DECISIONS_FOR_OWNER.md`, 'Part 8 batch 2 and the ETA multipliers'); implemented by EPOCH-Q4-IMPL (R1a) |
| EBR-Q0 | Where eBR enters eWAR | (a) eWAR v3 on FanGraphs' frame, a column labelled eWAR v3 and never plain eWAR (parts 9.2 and 9.7); part 9.3 not requested | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eBR batch 1') |
| EBR-Q1 | When eBR's steal and extra-base parts enter eWAR v3 (candidate part 1) | (a) only if they repeat clearly more: a Leg E SHIP with its guards, club changers included (the 2026-09-09 rule as written) | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eBR batch 1') |
| EBR-Q2 | Whether eBR's double-play part is a candidate part (candidate part 2) | (a) yes, admitted by the E-DP contrast of part 5.4 under the EBR-Q1 rule; a recorded relaxation of the 2026-09-09 rule | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eBR batch 1') |
| EBR-Q3 | A 100-scale baserunning index | (a) BEM+, registered in part 5.8, tested in the outcome look, served only on PASS | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eBR batch 1') |
| EBR-Q4 | Fetch 2011 to 2017 and 2020 | (b) fetch them first, into a separate cache the play-by-play corpus never reads (task EBR_Q4B_HISTORY_BACKFILL); before 2016 eBR on FanGraphs' frame replaces UBR and double-play runs (part 9.2's 2011-2015 counterparts), a different construct from the tested one, disclosed; the frames of parts 5.1 and 9.5 are the same under either answer | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 1 (after the unification)') |
| EBR-Q5 | Where eWAR v3 shows | a custom answer, verbatim: "Use the latest/best version of eWAR for all eWAR displays"; once EBR_3_EWAR_V3 assembles eWAR v3 (not before 2026-11-18) it becomes the displayed eWAR on every eWAR display door behind its own flag, with eWAR v2 a reference; until then eWAR v2 stays shown (EPOCH-Q4); read by EBR_3_EWAR_V3; it binds no look | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 2') |
| EBR-Q6 | Level-relative eBR on prospect cards | (b) show it on prospect cards, per level and season at 150 or more PA, display only, never an eFV input, never summarised by FV grade (task EBR_Q6B_MILB_CARDS); nothing in this file reads MiLB | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 2') |
| SWAR-Q0 | Which WAR series our positional ladder reaches | (b) a named candidate part of eWAR v3 (candidate part 3) with its own admission clause | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), sWAR batch 1 (the owner departed from every recommendation: one house series)') |
| SWAR-Q1 | Where HEM+, SEM+, REM+ and DEM+ go in a WAR | (b) inside eWAR v3: one house WAR, part outcome and part shrunk skill, which exists whatever the looks say, each part admitted only on a clear win under its own clause; no separate skill series | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), sWAR batch 1 (the owner departed from every recommendation: one house series)') |
| SWAR-Q2 | The displayed name of the shrunk-skill parts | (c) "eWAR skill", the displayed label and glossary term of candidate parts 4, 5 and 6; files and ids stay `swar` | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), sWAR batch 1 (the owner departed from every recommendation: one house series)') |
| SWAR-Q3 | The hitting input the batting part shrinks | (c) both, HEM+ and xHEM+ as two arms in one Holm family (candidate part 4); the skill look waits for the 2026-11-16 HEM+ versus xwOBA re-gate's result (part 7) | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), sWAR batch 1 (the owner departed from every recommendation: one house series)') |
| SWAR-Q4 | How eWAR v3 shows which parts moved it | (c) also in valuations: each admitted part named on the card's eWAR v3 reference as under (a), and eWAR v3 a comparison input for Trade Machine and free-agent value only after its own registered valuation test passes (task EWV3_VALUATION_GATE_REGISTRATION); nothing in this file feeds a valuation; read by EBR_3_EWAR_V3; it binds no look | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 2') |
| EWV3-Q1 | The bar a skill or position part must clear | (a) WIN (components) on its rate cell with its cumulative cell not LOSS (part 9.6) | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 1 (after the unification)') |
| EWV3-Q2 | Which batting arm enters when both qualify | (a) HEM+, unless the xHEM+ arm beats the HEM+ arm with lo95 above 0 on the same pairs (part 9.6) | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 1 (after the unification)') |
| EWV3-Q3 | Whether the two looks may share a session | (a) no: each look runs on its own day in its own writer session (part 7) | answered 2026-10-01 (`DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-10-01 (AskUserQuestion), eWAR v3 batch 1 (after the unification)') |
| settled | Chance scope | every chance on a ball in play plus steals, caught stealing and pickoffs (part 2.5) | design default, changed only by a new eBR version and a new registration |
| settled | Park and fielder arm | not in the number; arms P and F measured and reported beside it (part 2.8) | design default |
| settled | Double-play pricing | by base-out state (part 2.5) | design default |
| settled | Leverage in the pitching part | L-A: the published gmLI levers both arms of the delta; L-B (gmLI 1 in both arms) computed as a disclosure, never served (part 9.4) | design default, changed only by a new registration |
| settled | Seasons of the skill and position deltas | 2016 to the last complete season; the live season nightly once eWAR v3 serves | design default |
| settled | Shrink constants and pool targets | the EM+ modules' own, taken by reference, none refit here | design default |
| settled | The ladder's window | per season, the six seasons ending at that season; the served ladder a sensitivity only | design default |
| settled | Swingmen, position players who pitch, pitchers who bat | the start-share target blend; the nopp and pitcher-batter rules (zero delta) | design default |
| settled | The pitcher chain | the replica's feed-only arm `plain_fip_loo_pf`, used only as the difference of two runs | design default |
| settled | Cells | rate cells decide admission; total (cumulative) cells sit in the same Holm family | design default |
| settled | B1 | one k per side fitted on 2016 to 2018 predictor pairs before the skill look | design default |
| settled | The home-run term of the pitching part | its own arm, decided first in the skill look by its own transport clause (part 9.5) | orchestrator ruling X8 |
| 2026-09-09 | FanGraphs is the primary framework; eWAR v2 "becomes the incumbent to beat, not the base to extend" | no candidate part ever enters eWAR v2's own artifact or provider (`data/ewar.json`, `ewar.py`, `tools/build_ewar.py`, `ewar_v2`; part 9.1); eWAR v3 is "fWAR plus departures, each carrying its own pre-registered gate", and this file is those gates; the plan's "the eWAR positional component reads OUR ladder" becomes candidate part 3, admitted only on its own clause (SWAR-Q0 (b)) | answered; part 1 records how it applies |

An owner answer that arrives after this commit replaces its default by a dated amendment under part
11, committed alone BEFORE the look whose clauses it touches, never after it.

## 2. What eBR is

### 2.1 Unit, pool, seasons

- Runs above average per player-season, MLB regular season only. Shown in runs, one decimal, signed.
- Seasons: every season with a complete runner record (identity gate I3). At registration that is
  2018, 2019, 2021, 2022, 2023, 2024, 2025 and 2026: 19,437 games of play-by-play on disk. The same
  endpoint serves 2011 to 2017 and 2020 in the same shape; they are not on disk (EBR-Q4).
- Pool: every runner and batter in the season's regular-season play-by-play, pitchers who batted and
  pinch runners included, which is the pool of FanGraphs' hitting feed and of Baseball-Reference.
  Every part sums to zero over this pool each season.
- No shrinkage of player values (the shrink in 2.3 acts on the league table, not on runners), no
  minimum opportunities for runs, no park term and no fielder-arm term in the number.

### 2.2 The source: the runner record

- **MLB payloads:** `.cache/win_prob/<game_pk>.json` (the winProbability resource, the endpoint and
  cache of `mlb_leverage.get_win_probability`).
- **Games:** a payload carries no game type, so the games are EXACTLY the final games returned by
  `mlb_leverage.season_game_pks(season, game_type="R")`, frozen into the record's manifest per
  season. Any other cached payload is counted and skipped. No postseason play enters any table,
  credit or league constant.
- **One row per `runners[]` entry:** game_pk, season, at_bat_index, play_index, runner id,
  is_batter, origin base, start, end, out base, is_out, out number, `details.movementReason`,
  `details.eventType`, is_scoring, error credit (any `f_throwing_error` or `f_fielding_error` credit
  on the entry), credited fielder ids.
- **One row per plate appearance:** batter, batting team (from the game's clubs and the half),
  venue (from the schedule), scheduled innings, event type, trajectory, hit location, Gameday
  coordinates, exit velocity (stored, never used in the number), the in-play outfielder ids (the MLB
  `defense` block), the count at the final pitch, the state at plate-appearance start, and the state
  at every `playIndex` inside the plate appearance.
- **One state walk:** the state at plate-appearance start comes from `reconstruct_plays` in
  `tools/build_pbp_corpus.py` (`:441`), imported with `tools/` on `sys.path` as
  `test_pbp_corpus.py` does. Inside the plate appearance the PA's runner
  entries are applied NET per playIndex, in order (reference implementation: the eBR bundle's
  `ebr_census.py`, 0 outs mismatches in every season).
- **Steal events are keyed on `details.movementReason`**, never on `details.eventType`. On the event
  type, 17 to 41 entries a season would score a caught stealing where the runner was safe.
- **Where it lives:** `.cache/pbp_runners/`, never `.cache/pbp_corpus` (whose manifest is a
  registered artifact with exactly three tables, and whose rebuild moves /management/'s vintage
  stamp). `pbp_runners` is added to `tools/prune_cache.EXCLUDED`. A payload re-fetched to resolve an
  identity miss (part 3) is stored under `.cache/pbp_runners/refetch/`; nothing here writes
  `.cache/win_prob/`.

### 2.3 Run basis: per-season RE24, shrunk toward a frozen pool

```
Fit set F_s (season s, regular season):
  innings 1-8 (both halves) and the top of the 9th; for a scheduled seven-inning game, innings
  1-6 and the top of the 7th (scheduledInnings from the schedule call); only half-innings that
  reached three outs; no half-inning carrying a runner_placed event; states at plate-appearance
  start, occupancy read with notna() (the recipe of win_expectancy.run_expectancy).
raw_s(b,o) = mean over F_s plays in base-out cell (b,o) of the runs from that play to the end of
             the half-inning, inclusive (that recipe, re-implemented per season on the fit set).
pool(b,o)  = the same over F of every season in the pool set P.
             P = {2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026}, FROZEN with ebr_v1, so adding a
             later season never moves a completed one.
lambda_s   = sum_c n_s(c) raw_s(c) / sum_c n_s(c) pool(c)          (the season's run level)
RE_s(c)    = [ n_s(c) raw_s(c) + K lambda_s pool(c) ] / [ n_s(c) + K ],   RE_s(., 3) = 0
K          = W / tau^2 by the method of moments over the 24 cells: W the n-weighted within-cell
             variance of runs-to-end, tau^2 the between-season variance of the lambda-adjusted
             cell means net of sampling variance; clipped to [500, 5000]; computed once on P and
             frozen with ebr_v1.
```

- `ebr.py` re-implements the recipe and never calls `win_expectancy.run_expectancy`, which refuses
  any cell under `MIN_RE_N` 500 (`win_expectancy.py:108`, `:275-286`); the runner-on-third,
  none-out cell holds 229 to 303 fit-set plays a season, so that refusal would fire in every season.
- K is ONE pooled constant over the 24 cells, whose within-cell variance of runs-to-end runs from
  0.17 to 3.96 across the 192 season-cells (the eBR bundle's `_re24_cells.json`), so a
  high-variance cell is shrunk less, relative to its noise, than a cell-specific K would shrink it.
  This is a design choice, recorded here, changed only by a new eBR version.
- Each season's table has 24 cells and is MONOTONE (adding a runner never lowers RE, adding an out
  never raises it). The build asserts this and refuses otherwise. Each table ships with its sha256.
- The count is ignored (the RE24 convention). Win expectancy is not used: WAR is runs and context
  neutral, and run expectancy prices the third out exactly.

### 2.4 Value of a transition

```
RV = R + RE_s(b', o') - RE_s(b, o)          RE_s(., 3) = 0
```

Every state is taken at the event's own `playIndex`, never at the plate appearance's start. An event
on the plate appearance's final pitch is valued AFTER the batter's own outcome on that pitch (a
strikeout's out comes first, so a caught stealing on that pitch can be the third out).

### 2.5 The five parts

```
eSB (steals, caught stealing, pickoff-caught-stealing)
  attempts j of runner r: entries with movementReason r_stolen_base_*, r_caught_stealing_* or
                          r_pickoff_caught_stealing_*
  RV_j   = R_j + RE_s(b'_j, o'_j) - RE_s(b_j, o_j)    (b'_j, o'_j): the state after THIS runner's
                                                       attempt only; R_j = 1 on a steal of home
  eSB_r  = sum_j RV_j - sum over base in {1B, 2B, 3B} of m_{s,base} * E_{r,base}
  m_{s,base} = league sum of RV over attempts from that base / league sum of E_base
  E_{r,1B} = plate-appearance starts with r on 1B and 2B empty; E_{r,2B}: on 2B, 3B empty;
  E_{r,3B}: on 3B
  Double steals: the lead runner is valued first with the trail runner still on his base; the
  trail runner is then valued from that intermediate state, so the two sum to the event's RE change.
  An error that carries the runner past his target base is excluded: the steal is valued to its
  target, the rest is the fielder's. Two-out caught stealing is priced. Attempts outside a counted
  opportunity are valued; the centring holds because m is league value over league opportunities.

ePK (pickoffs of a runner not attempting)
  RV     = RE_s(b', o + 1) - RE_s(b, o)             (third out: -RE_s(b, 2))
  ePK_r  = sum of RV over r's pickoffs (movementReason r_pickoff_1b, r_pickoff_2b, r_pickoff_3b
           with isOut) - sum over base of mPK_{s,base} * P_{r,base}
  mPK_{s,base} = league sum of pickoff RV from that base / league sum of P_base
  P_{r,base} = plate-appearance starts with r on that base. Pickoff errors are excluded.

eXB (advancement and outs on the bases), split exactly into eXB_adv and eXB_oob
  Classes, runner r at contact on play p, contact state (b, o) from the record:
    H  every runner on base on a single or double (runners on 3B on a double and every runner on
       a triple are excluded: they score every time)
    B  the batter-runner on a single or double (his minimum base is the hit's base)
    A  every runner on base on a caught air ball (fly_ball, line_drive or popup) with fewer than
       two out at contact; events field_out, sac_fly, double_play, sac_fly_double_play
    G  an unforced runner on 2B or 3B on a ground ball with fewer than two out, where the play ends
       in an out or a fielder's choice (field_out, force_out, fielders_choice,
       fielders_choice_out, grounded_into_double_play, double_play)
  Outcomes Y(x) = {m, m+1, ..., home, OUT}; m = the forced base (H), the hit's base (B), his own
    base (A, G). Outcomes a runner ahead makes infeasible are removed. G has two out outcomes: OUT
    (he is retired, the batter reaches) and DP (he and the batter are both retired).
  Value of outcome y, on a fixed reference so a teammate's extra base is never credited to r:
    v(y | x) = R(y, x) + RE_s( B(y, x), O(y, x) )
    runners AHEAD of r at their actual end (context, their runs counted as the play scored them);
    r at y; behind r: H the batter at the hit's base and trailing runners at their forced base;
    A trailing runners at their base and the batter out; G the batter OUT when r is safe, SAFE at
    first when r is retired, OUT when y = DP, a forced trailing runner at his actual end; B no one.
    O = outs at contact + the batter's out where the reference has one + outs among runners ahead
    + outs in y; O >= 3 gives RE = 0.
  Context x = (s, c, k, o, L, z): c the class, k r's base, o outs at contact, L what the runners
    ahead did (none; scored; stopped on a named base; out), z the batted ball:
    H, B: location group (LF, CF, RF, infield) x trajectory group (ground, air) x depth tercile
          (outfield only: distance from the plate from Gameday coordinates, terciles within
          (s, c, location group)), plus a flag for two out and a full count
    A:    location group x trajectory (fly, line, popup) x depth tercile
    G:    the fielder who fielded it (location 1-6)
    A ball with no coordinates backs off one level. Exit velocity and total distance are not used.
  League outcome distribution, hierarchical backoff with kappa = 20 pseudo-counts:
    pi(y | x) = [ n(x, y) + kappa * pi(y | parent(x)) ] / [ n(x) + kappa ]
    chain: full z -> drop depth -> drop trajectory -> drop location -> (s, c, k, o, L) -> the
    frozen pool P
  Credit, exact split, centring:
    E(x_i)   = sum_y pi(y | x_i) v(y | x_i);        e_i = v(y_i | x_i) - E(x_i)
    D(y | x) = v(y | x) - v(m | x)
    e_i^oob  = sum over out outcomes y of [ 1(y_i = y) - pi(y | x_i) ] D(y | x_i)
    e_i^adv  = e_i - e_i^oob
    eXB_adv_i = e_i^adv - mean(e^adv over opportunities in (s, c)); the same for oob
    eXB_r    = sum over r's opportunities of (eXB_adv_i + eXB_oob_i)
  Error advances: r's outcome is the end of his last movement segment without an error credit; if
  his first segment carries the error, his outcome is m. The rest is the fielder's.

eGDP (double-play avoidance, the batter)
  opportunity q: a plate appearance whose state at its final pitch has a runner on 1B and fewer
                 than two out (the plate-appearance-start count, FanGraphs' definition, is
                 reported beside it)
  GIDP_q       : result.eventType == grounded_into_double_play
  p_s(b, o)    = league GIDP / league opportunities in state (b, o)   (8 states: 1B, 1B2B, 1B3B,
                 loaded, each with 0 or 1 out)
  c_s(b, o)    = mean[R + RE_after | ground-ball outs and fielder's choices in (b, o) that were not
                 double plays] - mean[R + RE_after | GIDP in (b, o)]; RE_after = RE_s of the next
                 plate-appearance-start state
  eGDP_r       = - sum_q [ GIDP_q - p_s(b_q, o_q) ] * c_s(b_q, o_q)
```

### 2.6 Excluded from the number, and counted in the eval

Advances on wild pitches, passed balls and balks (the battery's); defensive indifference (not scored a
steal); pickoff errors and every advance credited to an error (the opportunity is kept, the outcome
truncated before the error); runners forced on ground balls (the double-play pivot is the batter's
eGDP and the defense's); no-choice opportunities (runners on 3B on doubles, every runner on a triple);
interference and hit-by-batted-ball entries. A sub-total for advances on balls in the dirt is
reported for MiLB only and never enters the number.

### 2.7 Display parts and totals

- **SB runs** = eSB + ePK (FanGraphs' wSB is its counterpart). **XB runs** = eXB_adv + eXB_oob
  (BsR minus wSB, which since 2016 is Savant's runner XB runs). **DP runs** = eGDP (FanGraphs' served
  BsR has no counterpart since 2016; Baseball-Reference's Rdp is the nearest).
- **eBR** = SB runs + XB runs + DP runs. Published sub-totals: outs on the bases (eXB_oob + ePK) and
  XB by class family (hits, batter-runner, air, ground).
- Credits carry the batting team, so eBR sums by (player, team, season) exactly; a traded player's
  season is the sum of his stints. A multi-season value is the sum of per-season runs, never re-priced
  on a pooled table; its rate is 600 x runs / PA.

### 2.8 Park and fielder arm: measured beside the number, never in it

- **Arm P (park):** a venue x location-group level at the top of the backoff chain, estimated from
  VISITING runners only over the three prior seasons, venue from the schedule.
- **Arm F (fielder):** the fielding outfielder's arm tercile from his PRIOR season's Savant arm
  strength, a level for outfield-fielded balls, 2021 on (Savant arm starts in 2020).
- Reported every build: the correlation of each runner's eBR under the arm with the primary, and the
  count of the largest movers (never names in the eval). The primary changes only through a new eBR
  version and a new registration.

### 2.9 Version, freezing, stamps

- `ebr_version` = `ebr_v1`. A completed season freezes on November 1 of its year (the eWAR rule,
  `war_source.EWAR_FREEZE_MONTH_DAY`) with a sha256 digest; adding a later season never changes it.
- A new version (pool, K rule, kappa, a class, a bucket, a counterpart) is a new frozen series: a hand
  build, a changelog line and a new registration before any look on it.
- Every artifact stamps `ebr_version`, each season's RE24 sha256, K, kappa, P, the record's
  `built_at` and `generated_at`.

## 3. Identity gates (hard: a miss blocks serving that season)

| Id | Check | Pass |
|---|---|---|
| I1 | league SB and CS (pickoff-caught-stealing included), keyed on `movementReason`, against the StatsAPI season hitting lines (playerPool=All) cached and hashed in the record's manifest, per completed season; league GIDP from `result.eventType` | SB and CS exact; GIDP within 0.5 percent |
| I2 | per player-season, completed seasons | SB and CS exact for every player with any; GIDP exact for 97 percent or more of players with any |
| I3 | completeness | every final regular-season game of `season_game_pks` is in the record; otherwise the season does not serve |
| I4 | league sum of each of the five parts per season, all-runner pool | 0 within 0.01 run |
| I5 | RE24 | 24 cells per season, monotone, K inside [500, 5000], sha256 stamped |
| I6 | row identity | parts sum to eBR within 0.011 (rounding); no NaN; per-season absolute eBR at most 30 runs |
| I7 | coverage | 99 percent or more of eligible opportunities priced; the share priced from a context cell with n of 50 or more reported by class; 99 percent or more of the feed's hitting rows with a nonzero `baseRunning` in a runner-record season carry an eBR row |
| I8 | determinism and freezing | a rebuild is byte-identical; a completed season is unchanged when a later season is added |
| I9 | isolation | no fitted consumer (`efv_*`, `proj_*`, `fa_*`, `arb_*`, `betting_*`, `leaderboard_vintages`) imports `ebr` or reads its artifacts; no betting module reads a baserunning file or an `ebr` key |

**Re-fetch rule.** An I1 or I2 miss on a completed season triggers ONE re-fetch of that season's
games of the mismatched players into `.cache/pbp_runners/refetch/` (a cached payload can predate an
official scoring change) and one re-check. The eval lists every re-fetched game. A miss that survives
blocks the season.

## 4. Descriptive agreement, every build (bug bands; never a gate on validity)

- **Comparators.** FanGraphs' published BsR and wSB (MLB's StatsAPI sabermetrics feed through
  `saber_feed`; `ubr` is never read, `wGdp` only as the double-play comparator for 2016 to 2024);
  Baseball Savant's runner XB runs, runner total and basestealing run value (`savant_running`);
  Baseball-Reference `runs_br` and `runs_dp` (read through `war_source.stint_frame(side,
  provider="bwar")`, `war_source.py:554`, and summed over a player-season's stints); Savant sprint
  speed.
- **A fact this gate rests on.** Through 2015 the feed's `baseRunning` equals `wSb + ubr + wGdp` on
  every row. From 2016 it does not, on 544 to 726 rows a season, because the served BsR is wSB plus
  Savant's runner XB runs: BsR minus wSB equals Savant `runner_runs_XB` at r 1.000 (MAE 0.001 runs in
  2016, 0.008 in 2025, 0.024 in 2026), and it carries no double-play part. For the non-steal part,
  "agrees with FanGraphs" and "agrees with Savant" are one target.
- **Statistics,** per season at PA 300+ and PA 502+: Pearson and Spearman r, SD ratio, OLS slope and
  mean difference. Aggregates only: no per-player FanGraphs, Savant or Baseball-Reference value enters
  an eval artifact.
- **Comparisons:** SB + XB runs against BsR; eBR against B-Ref `runs_br + runs_dp`; SB + XB runs
  against Savant's runner total; SB runs against wSB (the wSB-parity check, FanGraphs' own linear
  weights recomputed on the record's counts); XB runs against Savant XB; DP runs against B-Ref
  `runs_dp` and the feed's `wGdp` (2018 to 2024); XB opportunities per runner against Savant's
  `N_runner_moved_XB` (a scope check).
- **Bug bands.** A miss means "find the bug", never "invalid". They were set after a sibling
  construct's same-season agreement was seen (part 10) and sit well below every value seen:
  r(eBR, B-Ref br + dp) at least 0.60 at PA 502+; r(SB runs, wSB) at least 0.80; r(XB runs, Savant
  XB) at least 0.50; r(DP runs, B-Ref dp) at least 0.60; SD ratio of SB + XB runs to BsR inside
  [0.5, 2.0]; absolute mean difference at most 1 run at PA 502+; r(sprint speed, (SB + XB runs) per
  600 PA) at least 0.40 at PA 300+ every season (a sign and plumbing check; speed is a cause, not a
  definition).

## 5. The outcome look (candidate parts 1 and 2, and BEM+)

`tools/ebr_gate.py` computes everything in this part ONCE, on the day part 7.2 allows. No other code
path computes a year-to-year, split-half or forward statistic of eBR or of any of its parts, at any time.

### 5.1 The frame

- **Pairs:** 2018-2019, 2021-2022, 2022-2023, 2023-2024, 2024-2025, 2025-2026. 2020 enters no pair;
  2019-2021 is not a pair.
- **Rows:** players with 300 or more plate appearances in BOTH seasons of a pair (StatsAPI season
  hitting lines, playerPool=All), one row per player-season (a multi-club player's season total; on
  FanGraphs' side the combined row, `numTeams` above 1), identical rows for every series compared.
- **Frames:** U = the four pairs no sealed file can form (2018-2019, 2021-2022, 2022-2023,
  2023-2024); X = 2024-2025 and 2025-2026 (formable from the sealed prototype files of part 10, never
  formed). Verdicts read all six pairs; frame U carries the SHIP guard.
- **Incumbent values:** FanGraphs' published `baseRunning` (BsR), `wSb`, `ubr`, `wGdp`, `batting`,
  `plateAppearances` and `numTeams` per hitting row, as frozen in the fWAR epoch's per-season
  vintage: the artifact task EPOCH_E3 builds and EPOCH_D9_FREEZE fills (proposed name
  `data/fwar_vintage.json`; the look reads the artifact the epoch committed and records its
  `vintage_id` and sha256). The orchestrator handed EPOCH_E3 the requirement to store those fields
  beside the run parts (2026-09-30, from this gate's review). The look STOPS with 'BLOCKER: other
  fwar vintage lacks <fields>' if any is absent for a frame season. Never a fresh fetch, and never
  the `.cache/statsapi_saber_*` payloads, which "may not be used as" a frozen vintage
  (`FWAR_LABEL_EPOCH_GATE.md:139`).
- **Baseball-Reference values** for part 5.4's E-DP contrast: `runs_dp` per player-season from
  `war_source.stint_frame("bat", provider="bwar")`, read from the cached `.cache/war_daily` copy as
  it stands on look day (never fetched), its sha256 and `fetched_at` printed before any statistic.
- At registration the public-series analogue of this frame held 1,181 runner-pairs and 475 players
  (187, 192, 202, 207, 199 and 194 per pair).

### 5.2 Leg E: may eBR's steal and extra-base parts stand in for FanGraphs' BsR?

| Item | Registered value |
|---|---|
| Candidate | E = (eSB + ePK + eXB) / PA, approximately scope-matched to BsR since 2016 (steals and extra bases, no double plays; ePK's 145 to 222 pickoff outs a season of runners not attempting and the ground-ball class G have no BsR counterpart) |
| Incumbent | B = BsR / PA from the frozen vintage |
| Statistic | per pair, rho_E = Spearman(E_Y, E_Y+1) and rho_B = Spearman(B_Y, B_Y+1) on that pair's rows; each averaged over the six pairs; d = mean(rho_E) - mean(rho_B) |
| Precedent, stated exactly | eWAR v2's gate 2 (`ewar.gate_pitcher_persistence`, `ewar.py:1387-1445`) runs year-to-year self-persistence AND a forecast leg (this year's value against next year's actual runs prevented), and its docstring calls the forecast "the one that actually matters". This gate keeps persistence alone, for the reason below |
| Interval | player-clustered bootstrap (players drawn with replacement, each carrying all his pairs), B = 2,000, seed 20260807; sd = the bootstrap sd of d; interval d +/- 1.645 sd (the one-sided 95 percent bounds of `docs/EFV_GATE_STANDARD.md` part 8, and the "player-clustered 95 percent lower bound" of the 2026-09-09 plan's W1.3 arms) |
| Floors first | the look prints the bootstrap sd, the half-width and the dispositions it can reach BEFORE it prints d |
| Dispositions | `EFV_GATE_STANDARD.md` part 8 at Delta = 0.02: SHIP, the interval entirely above +0.02; RULED OUT, entirely inside +/-0.02; RESOLVED_LOSS, entirely below -0.02; UNDECIDED otherwise |

**Why persistence alone decides** (the eBR bundle's `integration.md` 1.8). Baserunning has no
"actual" next-season outcome independent of a construct: the only next-season targets are the rival
series themselves, and predicting next season's BsR favours BsR's own construct. On public series
Baseball-Reference's `runs_br` predicts next season's BsR at 0.5297 against BsR's own 0.6488 (sd of
the difference 0.0182), a gap that is partly the shared construct and not the runner. Each series'
own persistence avoids asking eBR to reproduce the rival's model. Its known weakness is that a
stable bias (a home park or a team context that inflates the same runner every year) also repeats;
the club-changers guard of 5.3 is the one check that can see it. Persistence measures how much a
number repeats, not whether it is true: no outcome of this leg licenses "more accurate" (part 6.3).

### 5.3 The guards

- **Leg T, team runs (non-inferiority; required for every admission).** Club-seasons 2018, 2019 and
  2021 to 2026 (240): off_B = FanGraphs batting runs + BsR; off_E = FanGraphs batting runs + (eSB +
  ePK + eXB); both summed to clubs by stint plate-appearance share (the stints of
  `war_source.stint_frame("bat", provider="bwar")`), against the club's runs scored (StatsAPI team
  season hitting lines, cached with `fetched_at` before the look). Pearson r, as
  `ewar.gate_team_runs` scores its offense arm. Passes when r(off_E, runs) is at least r(off_B,
  runs) - 0.005 (the floor of `_audit_2026-09-09/feasibility/C2_fwar_baserunning.md` IC1 leg (i)).
  Computed only inside the look. Its r values (and DP-2's) are written ONLY to part 12.1 and to the
  look block of `.cache/ebr/preview/ebr_eval.json`, never to a `data/` file: the served
  `data/ebr_eval.json` carries Leg T's and DP-2's pass or fail, never an r against runs (Part 8's
  8.A; part 5.10). No exporter relates eBR to runs or wins.
- **The permuted twin (the zero-information control).** E permuted across runners within each season,
  each season independently, seed 20260807, rows unchanged; Leg E recomputed. The twin must come back
  RESOLVED_LOSS. If it does not, the look is VOID (part 6.5).
- **Frame U.** A SHIP also needs the point estimate of d on frame U alone above 0.
- **Club changers.** A SHIP also needs the point estimate of d above 0 on the club-changers subset
  (runners whose primary club by plate appearances differs between Y and Y+1, pooled over the six
  pairs, the same rows and statistic). It is the one check in this look that can see a park or team
  bias that repeats, because a runner who changes clubs leaves it behind. The look prints the
  subset's size per pair before d.

### 5.4 The DP leg: the E-DP contrast decides; DP-1 is a plumbing floor

FanGraphs' served BsR has carried no double-play part since 2016, so no FanGraphs series exists to
beat. Adding the part at all is the owner's call (EBR-Q2), and a yes is a recorded relaxation of the
2026-09-09 rule for a part FanGraphs no longer carries. What this leg decides is whether eBR's
version earns admission against the nearest published series, Baseball-Reference's `runs_dp`.

**The prior, disclosed.** Avoiding double plays already repeats on public series: year over year at
PA 300+ in both seasons, Baseball-Reference `runs_dp` per PA at Pearson 0.428 to 0.576 and the
feed's `wGdp` at 0.36 to 0.43 (part 10 item 2). A test of whether eGDP repeats at all (DP-1) is
therefore expected to pass and decides nothing about admission. The E-DP contrast's power was not
measured; eGDP and `runs_dp` count the same events, so a tie (UNDECIDED) is the honest prior there
too.

- **E-DP (deciding).** On the frame of 5.1: per pair, rho_G = Spearman(eGDP per PA in Y, in Y+1)
  and rho_R = Spearman(`runs_dp` per PA in Y, in Y+1) on that pair's rows; each averaged over the
  six pairs; d_DP = mean(rho_G) - mean(rho_R); the player-clustered bootstrap of 5.2 (B 2,000, seed
  20260807), d_DP +/- 1.645 sd, floors printed before d_DP, `EFV_GATE_STANDARD.md` part 8
  dispositions at Delta = 0.02 (SHIP, RULED OUT, UNDECIDED, RESOLVED_LOSS) as in 5.2. Its SHIP
  guards are 5.3's applied to d_DP: d_DP on frame U above 0 and on the club changers above 0.
- **E-DP twin.** eGDP permuted within each season (seed 20260807, rows unchanged) must come back
  RESOLVED_LOSS on E-DP, else the DP leg is VOID.
- **DP-1, a plumbing floor, not an admission gate.** Per pair, Spearman(eGDP per opportunity in Y,
  in Y+1), averaged over the six pairs, with the bootstrap of 5.2: estimate - 1.645 sd must be above
  0. A miss means the part is broken (find the bug); it never admits anything. The permuted eGDP
  must fail it.
- **DP-2 (guard).** Leg T with eGDP added: r(off_B + eGDP, runs) at least r(off_B, runs) - 0.005,
  its r values kept as Leg T's are (5.3).
- **Reported, never deciding:** the feed's `wGdp` per PA persistence (pairs inside 2016 to 2024
  only) and its difference from eGDP's.

### 5.5 Reliability, split-half (reported)

Odd against even `game_pk` within each season, per part and in total, Spearman-Brown to a full
season, runners with 300+ PA, per season. A part whose full-season reliability is 0.10 or lower in
five or more of the eight seasons is flagged NOISE: it stays counted in eBR and in the eval, and no
copy describes it as a trait or a skill.

### 5.6 Reported beside, never deciding

- d on frame U and on frame X separately; the six per-pair signs; Pearson versions; the PA 502+
  subset.
- The balanced forecast: Z_Y+1 = the mean of the within-pair standardised ranks of E_Y+1 and B_Y+1;
  dX = rho(E_Y, Z_Y+1) - rho(B_Y, Z_Y+1), with its bootstrap interval.
- The 2 x 2 cross-forecasts (E to E, E to B, B to E, B to B).
- Third-party targets in Y+1: Baseball-Reference `runs_br` per PA; Savant's runner total per runner
  opportunity where cached.
- The club-changers subset per pair (its d is a SHIP guard in 5.3; its per-pair d and sizes are
  reported here).
- Per part: rho of SB runs per PA against wSB per PA, and of XB runs per PA against (BsR - wSB) per PA.
- Leg E's d with arm P on and with arm F on (part 2.8).

### 5.7 Power, stated before the look

On the public analogue of this frame (part 10, item 3) FanGraphs' BsR repeats at a mean Spearman of
0.6488 and Baseball-Reference's `runs_br` at 0.4794; their difference has a bootstrap sd of 0.0223, a
half-width of 0.0367. At that sd RULED OUT is not expected to be reachable (it needs a half-width
under 0.02), SHIP needs d above about +0.057 and RESOLVED_LOSS falls below about -0.057. These are
projections from the BsR and `runs_br` pair, whose same-season r is 0.77; a candidate more
correlated with BsR has a smaller sd of d, so the floors the look prints first, not these figures,
decide which dispositions are reachable. **The honest prior is a tie**
(UNDECIDED): eBR shares BsR's steal counts and models the same extra-base chances. A SHIP is not the
expected reading, and part 6 says what a tie licenses.

### 5.8 BEM+ (rides only if part 1 records EBR-Q3 answer (a))

Exactly the Baserunning plan's section 2.6 (`part8/baserunning.md`), bound here as follows:

- **Parts** map onto part 2.7: SB runs with chances = steal opportunities plus plate-appearance starts
  on base (pickoffs); XB runs with eXB opportunities; DP runs with GIDP opportunities.
- **Constants** `k_p = hm * (1 - r) / r` (the `positional_fit.fit_signal` rule), r the year-over-year
  correlation of the part's rate at matched exposure on pairs 2018-2019 and 2021-2022, fit inside the
  look BEFORE any gate statistic, then frozen.
- **Gate X-B1.** Predictor seasons 2022, 2023 and 2024 (outcomes 2023 to 2025); floors 100 starts on
  base in Y and 150 in Y+1; predictor the unrounded BEM+; target the eBR rate per 100 starts on base
  in Y+1; baselines sprint speed in Y, stolen bases in Y, starts on base in Y and the raw unshrunk rate
  in Y; forward Spearman; 2,000 bootstrap replicates, player-clustered and season-stratified (the DEM+
  gate's convention v2), seed 20260807; the twin, BEM+ permuted within predictor season, must FAIL the
  stolen-base clause.
- **PASS needs all:** gap against sprint speed, against stolen bases and against starts on base each
  with lo95 above 0, and against the raw parent lo95 at least -0.01, computed as
  `docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md` section 3 computes lo95; the twin fails.
- **Holdout:** the 2025-2026 pairs, read in the same run, reported beside the verdict, never merged.
- **On FAIL** BEM+ is not served. Leg E and BEM+ answer different questions with different
  consequences; each reads only its own clauses, and no correction is made across them.

### 5.9 Crash protocol

Before the look the whole reporting path runs on synthetic fixtures with nulls
(`tools/ebr_gate.py --dry-run`). The look's stdout and stderr are teed to the writer's output
directory before anything else runs. On any exception after scoring began: STOP, no rerun, an owner
question. A second run is forbidden whatever the first printed.

### 5.10 What the look reads and writes

It reads the runner record, the substrate, the frozen fWAR vintage, the cached Baseball-Reference
frame, the cached StatsAPI lines and the Savant caches; it fetches nothing on look day. It writes the
Results text of part 12.1 and the look block of `.cache/ebr/preview/ebr_eval.json`, and nothing under
`data/`. The flip commit copies into `data/ebr_eval.json` only the look block's dispositions, guard
pass or fail flags, floors, NOISE flags and identity receipts: never a Leg T or DP-2 r, nor any
other correlation against runs or wins, which stay in part 12.1 and the preview (Part 8's 8.A). The
flip's `test_ebr_served_eval.py` asserts that the served eval carries no such figure.

## 6. What each outcome-look result licenses

### 6.1 eBR's steal and extra-base parts in eWAR v3 (candidate part 1)

| EBR-Q1 answer recorded in part 1 at the look | The steal and extra-base parts enter eWAR v3 when |
|---|---|
| (a) only if it repeats clearly more (the 2026-09-09 rule) | Leg E is SHIP, Leg T passes, the twin is RESOLVED_LOSS, and d is above 0 on frame U and on the club changers |
| (b) unless it repeats clearly less | Leg E is not RESOLVED_LOSS, Leg T passes and the twin is RESOLVED_LOSS |
| (c) once its data checks pass | I1 to I9 pass (the look still runs; it decides copy only) |
| (d) never | never |

Part 1 records EBR-Q1 (a), so the first row binds. In every row an admitted part enters eWAR v3 for
display only (part 9). Only a SHIP with its guards makes the departure a Z4 passer, eligible for the
2027 label epoch's own registration; an admission that is not a Leg E SHIP with its guards (possible
only under a later amendment to EBR-Q1 (b) or (c)) never is. Not admitted, eWAR v3 keeps FanGraphs'
BsR.

### 6.2 eBR's double-play part in eWAR v3 (candidate part 2)

It enters when part 1 records EBR-Q2 answer (a), EBR-Q1 is not (d), DP-1 (the plumbing floor) and
DP-2 pass, the E-DP twin is RESOLVED_LOSS, and the E-DP disposition meets the EBR-Q1 row of 6.1 with
d_DP in place of d: SHIP with d_DP above 0 on frame U and on the club changers under (a); not
RESOLVED_LOSS under (b); any disposition under (c). On FanGraphs' frame its counterpart is 0 from
2016 and wGdp before (part 9.2). It never becomes a label candidate under this registration. Not
admitted, eWAR v3 carries no double-play part from 2016 on, as FanGraphs' served WAR does not.

### 6.3 Copy

| Leg E disposition | The one comparative sentence copy may carry |
|---|---|
| SHIP | "repeats more from one season to the next than FanGraphs' BsR on the same runners" |
| RULED OUT | "repeats about as much from one season to the next as FanGraphs' BsR on the same runners" |
| UNDECIDED | none |
| RESOLVED_LOSS | "repeats less from one season to the next than FanGraphs' BsR on the same runners" |

The DP part may be called repeatable only on a DP-1 pass, and compared with Baseball-Reference's
double-play runs only by the E-DP disposition, in the same four sentences with "Baseball-Reference's
double-play runs" in place of "FanGraphs' BsR". A part flagged NOISE in 5.5 gets no trait word. No
disposition licenses "better", "more accurate" or "closer to the truth": a number that repeats more
is not shown to be more accurate.

### 6.4 Registry

- `pbp_runner_moves`: `provisional`, eval `.cache/pbp_runners/manifest.json` (the I1 to I3
  receipts), in the form of `pbp_corpus_base_state`.
- `ebr` and `team_ebr`: `provisional`, `provisional_kind` `measurement_only`, eval
  `data/ebr_eval.json`; predicts "nothing forward; DESCRIPTIVE runs above average on the bases from
  MLB's per-runner play-by-play on per-season RE24"; notes carry the outcome look's dispositions,
  the DP leg and the NOISE flags.
- `bem_plus` (only if it rode): `validated` on PASS; `provisional` with `measured_not_adopted` on FAIL,
  and not served.
- `swar_bat`, `swar_pit`, `swar_fld` and `swar_pos` (candidate parts 4, 5, 6 and 3; ids stay `swar`
  by SWAR-Q2 (c)), eval `data/swar_eval.json`, a byte copy of the tracked record
  `docs/ebr-2026-09-30/swar_eval.json` (part 9.5): `validated` for an admitted part; `provisional`
  with `measured_not_adopted` for a part the skill look did not admit. Each row's notes carry its
  cells' dispositions, the B1 and twin clauses, MDE95 and the holdout block; `swar_pit`'s notes name
  the home-run term the HR-arm clause chose; `swar_bat`'s notes name the arm that entered, if any.
- `ewar_v3` (written by EBR_3_EWAR_V3): `provisional`, `provisional_kind` `measurement_only`,
  baseline published fWAR; notes list every admitted candidate part with its clause, disposition and
  the part 1 answer that admitted it, or say that no part is admitted and the series equals fWAR.
- `ewar_v2_ebr`: not requested (EBR-Q0 (a)); no row.
- The `ewar` row (eWAR v2, the displayed WAR) is not edited by any task of this plan.
- Rows land in flip commits, never before: `pbp_runner_moves`, `ebr`, `team_ebr` and `bem_plus` in
  EBR_2F_FLIP; `swar_*` and `ewar_v3` in EBR_3_EWAR_V3's flip. A season that fails an identity gate
  does not serve.

### 6.5 VOID

A twin that is not RESOLVED_LOSS, a crash after scoring began, or a precondition found broken after
the run makes the outcome look VOID: neither outcome part is admitted, no comparative copy is
written, BEM+ is not served; the skill look and its parts are unaffected.
A new look needs an owner answer and runs only on an unseen frame (the 2026-2027 pair, after the 2027
regular season).

## 7. The clock

### 7.1 This document

Commits alone (with its test), before any year-to-year number of eBR and before any forward number
of a skill or position part, on or after 2026-10-04, only with part 1's rows for EBR-Q0 to EBR-Q3
and SWAR-Q0 to SWAR-Q3 holding recorded owner answers, and never between the fWAR epoch's step A and
its step Z entry (step A has started when `../_pre_epoch_fwar_2026-10/` exists; the step Z entry is
the dated part 9 entry of `FWAR_LABEL_EPOCH_GATE.md` that names step Z, not any part 9 entry).

### 7.2 The outcome look (parts 5 and 6; task EBR_LOOK)

Runs once, by `python -u tools/ebr_gate.py`, only when every one of these holds:

1. the build of part 2 is committed and I1 to I9 pass on every season of the frame, 2026 included
   and frozen (built on or after 2026-11-01);
2. the step Z entry exists and the epoch's frozen per-season fWAR vintage is committed and carries
   the fields of part 5.1 for every frame season;
3. the date is on or after 2026-11-17 (2026 freezes on 11-01; BEM+'s holdout needs 11-15 or later;
   11-16 holds the November re-gates);
4. the date is not 2026-10-23, 11-06, 11-13, 11-16, 11-20 or 12-01, not the Z1 day and not the skill
   look's day (7.3), and no other registered look or lab has run that day (the one exception is the
   shared session of 7.5, only if part 1 records EWV3-Q3 (b));
5. no pipeline, suite, pytest session, other lab or other writer is running.

### 7.3 The skill look (part 9.5; task EWV3_SKILL_LOOK)

Runs once, by `python -u tools/swar_lab.py --out docs/ebr-2026-09-30/swar_eval.json`, only when
every one of these holds:

1. the skill build of part 9.4 and the lab of part 9.5 are committed, the invariants of part 9.4 pass
   on a fresh preview build, and B1's constants are committed with their fit log;
2. the step Z entry exists and the frozen per-season fWAR vintage is committed and carries published
   fWAR, plate appearances, innings and the pitchers' gmLI for 2016 to 2025 (the frame, B1's fit
   and the transport block);
3. the date is on or after 2026-11-17;
4. the November re-gates have recorded DEM+'s confirmatory holdout AND the result of the 2026-11-16
   HEM+ versus xwOBA re-gate (the HEM+ re-baseline document of `docs/HEM_RIV_REGATE_GATE.md` R1-12
   with its results filled and its registry rows moved in the same commit). SWAR-Q3 (c) makes the
   batting part's read wait for that re-gate, and the skill look is one run, so the whole look waits;
5. the date is not 2026-11-16, 11-20 or 12-01, not the Z1 day and not the outcome look's day (7.2),
   and no other registered look or lab result was committed that day (the one exception is the
   shared session of 7.5);
6. no pipeline, suite, pytest session, other lab or other writer is running.

### 7.4 The skill holdout (part 9.5; task EWV3_SKILL_HOLDOUT)

Runs once, by `python -u tools/swar_lab.py --holdout`, on a later day than the skill look, not
before 2026-11-17, only after the November re-gates have recorded DEM+'s confirmatory holdout, never
on 2026-11-20 or 12-01, the Z1 day, the outcome look's day or another registered look's day, with the
same idle rule. It is reported beside the skill look's verdict and never merged into it. If the
skill look is VOID, the holdout does not run and part 12.3 records one dated line saying so.

### 7.5 One session or two (EWV3-Q3)

Under the default (a), each look runs on its own day in its own writer session, and neither runs on
the other's day. Under (b), the two looks run back to back in one writer session on one day, the
outcome look first; that day counts as one registered look day for both, each look is still exactly
one run under its own crash protocol, and a crash in the outcome look ends the session before the
skill look starts (the skill look then takes a later day).

### 7.6 Both looks

The frames do not expire: if a look has not run by Opening Day 2027 it still runs on its registered
frame. Exporters compute same-season numbers only, at every build; no exporter, page or lab other
than `tools/ebr_gate.py` and `tools/swar_lab.py` on their look days computes a year-to-year, forward
or split-half statistic of eBR, of a skill delta or of a ladder delta.

## 8. What may and may not be claimed

**May claim,** once the identity gates pass: "eBR counts what happened on the bases, in runs above an
average runner in the same spot, from MLB's play-by-play. Its steal and caught-stealing counts match
MLB's official ones for every player, and each part adds to zero across the league every season." The
agreement r values of part 4, read from the eval. After the outcome look, the one sentence part 6.3
licenses. After the skill look, for each skill or position part, the one sentence part 9.6 licenses,
with its numbers. Of eWAR v3: "FanGraphs' published WAR with our own admitted parts swapped in, each
named; a column beside the site's WAR (eWAR v2), not a correction of FanGraphs' WAR; it trains no
model." When no part is admitted: "eWAR v3 equals FanGraphs' WAR: no candidate part passed its
test." Of an eWAR skill part: "a shrunk skill read of [batting | pitching | fielding] inside eWAR
v3", with the word "shrunk" or "skill", never "regressed".

**May NOT claim,** whatever the outcome:

- that eBR is more accurate than BsR, Savant's baserunning run value or Baseball-Reference's numbers;
- that eWAR v3 or any of its parts is more accurate than fWAR or eWAR v2, "better than FanGraphs",
  "true talent", "what a player was worth", or that a WAR with eBR or a skill part in it is "better"
  WAR;
- that eBR, a skill part, the ladder or eWAR v3 makes eFV, the projections, a surplus figure, a trade
  value or any priced number more accurate (`FWAR_LABEL_EPOCH_GATE.md` clause (l), read as binding
  here);
- that eBR or any of its parts forecasts anything (BEM+ only within its own gate's words), or that a
  skill part forecasts anything beyond the sentence part 9.6 licenses;
- anything causal about speed, or a forecast word (luck, due, regress, trending, will, clutch,
  sleeper) on an eBR number;
- anything from a descriptive leg (part 9.5), and any team-wins relation outside part 12.

## 9. eWAR v3: the series, its candidate parts, and what it never touches

### 9.1 What never moves

- **The displayed WAR is eWAR v2** (the owner's EPOCH-Q4 answer, "Keep eWAR v2 shown", 2026-09-30,
  and the orchestrator's ruling EPOCH-Q4-IMPL (R1a)): every display door keeps provider `ewar_v2`
  after step D + U, `bullpen_export.served_war_basis` keeps returning `war_provider` `ewar_v2`, eWAR
  v2's nightly (`run_monthly.py` steps d8b and 3-pre) keeps running, the `ewar` registry row is not
  demoted, and fWAR shows as a reference column beside eWAR v2 after step Z (task
  EPOCH_FWAR_REFERENCE_COLUMN). eWAR v2 is NOT frozen or retired, and there is no frozen
  comparison slot for a new series to take.
- **Never written by any task of this plan:** `data/ewar.json`, `ewar.py`, `tools/build_ewar.py`,
  the provider `ewar_v2`, the glossary and registry entries named `ewar`, `career_war`,
  `war_source.DEFAULT_PROVIDER`, or any display door's provider. eWAR v2 is also the fWAR epoch's E0
  ("the served frame at HEAD on the day of step A"), which must stay reconstructible from
  `career_war` and `data/ewar.json` (`FWAR_LABEL_EPOCH_GATE.md` note 2, `:190-197`).
- **Never read by a fitted consumer:** eWAR v3, eBR, a skill delta and a ladder delta are never a
  training label, a driver or an input to a fitted consumer in this program (the 2026-09-11 plan's
  standing rule 4). `war_source` refuses `ewar_v3` on the `arb_spine` door, and no `efv_*`, `proj_*`,
  `fa_*`, `arb_*` or `betting_*` module reads them. They never enter eFV, projections, valuations,
  Team Outlook, Futures, HoF, Franchise, F-SCORE, the Teams tab, farm grades or WAG, and nothing is
  ever stratified by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`).
- **One word, one series.** On the site "eWAR" names eWAR v2. The new series shows only as a column
  labelled "eWAR v3", never plain "eWAR"; its shrunk-skill parts are labelled "eWAR skill" (SWAR-Q2
  (c)), its ladder part "position (our ladder)", and its eBR parts by their eBR names.

### 9.2 The base and the outcome parts (candidate parts 1 and 2)

- **eWAR v3** = the frozen published fWAR vintage plus named, zero-sum departures; provider
  `ewar_v3`, servable, never `DEFAULT_PROVIDER`; built only after the step Z entry; display only, a
  column beside eWAR v2. It is the only frame with a label path, and only for candidate part 1: a
  Leg E SHIP with its guards makes the steal and extra-base departure eligible for the 2027 label
  epoch's own registration (clause (k) item Z4); nothing else here does.
- **Outcome construction**, for player i in season s over every hitting-group row of the frozen
  vintage (pitchers who batted included), over the outcome parts admitted under part 6:

```
g_i       = sum over admitted outcome parts c of (eBR_c,i - FG_c,i)
            counterparts, 2016 on:   sb (eSB + ePK) vs wSb;  xb vs baseRunning - wSb;  dp vs 0
            counterparts, 2011-2015 (only if EBR-Q4 (b) put those seasons in the record):
                                     sb vs wSb;  xb vs ubr;  dp vs wGdp
d_i       = g_i - PA_i * (sum_j g_j) / (sum_j PA_j)       (MLB-wide per PA, every hitting-group row)
eWAR_v3_i = fWAR_i + d_i / RPW_s                          RPW_s = league_constants.league_totals(s)["rpw"]
```

  `wSb`, `ubr`, `wGdp`, `baseRunning` and `plateAppearances` are read from the frozen vintage
  (part 5.1), never fetched. Part 9.7 adds the skill and position parts to the same `d_i`.
- **Identities, tested:** the departures sum to zero each season, so the batting-side eWAR v3 total
  equals the batting-side fWAR total; RAR' = batting + (baseRunning + g) + fielding + framing +
  positional + (league - PA x D_s / PA_s) + replacement exactly; eWAR v3 minus fWAR is attributable to
  the named departures alone.
- Seasons without a runner record, every pitcher's pitching and every outcome part not admitted carry
  fWAR unchanged, marked `fg` per block. A player-season the record does not cover has g = 0 and is
  counted as a coverage gap; a runner with eBR and no feed row is counted, never added as a row; a
  pinch runner with no plate appearance takes no re-centring. The per-league residual of FanGraphs'
  league term is reported, never corrected.
- **The name.** "eWAR v3" names the fWAR-frame series in the 2026-09-09 and 2026-09-11 plans and in
  `fwar_frame.py`. `docs/sdr-2026-08-18/EWAR_V3_MERGE_GATE.md` used the same words for `ewar_merged`,
  which never landed; if its data ever arrives, that merge re-registers as a fielding departure on this
  series.

### 9.3 A new provider on eWAR v2's Baseball-Reference frame: NOT REQUESTED (EBR-Q0 (a))

The owner answered EBR-Q0 (a) on 2026-10-01, so `ewar_v2_ebr` is not built, has no task, no artifact
and no registry row, and nothing below binds. The text stays as registered so the alternative remains
on the record.

- **`ewar_v2_ebr`** = a copy of eWAR v2's player-seasons with eBR's admitted parts in place of
  Baseball-Reference's baserunning and double-play runs; servable, never `DEFAULT_PROVIDER`, its own
  artifact `data/ewar_v2_ebr.json`; built only after the step Z entry; display only, a column beside
  eWAR v2 labelled "eWAR v2 + eBR".
- **Construction**, for player i in season s over every batting row of
  `war_source.stint_frame("bat", provider="ewar_v2")` (read only), over the parts admitted under
  part 6 (6.1 for steals and extra bases, 6.2 for double plays):

```
h_i        = sum over admitted parts c of (eBR_c,i - BR_c,i)
             counterparts, every runner-record season:  sb + xb vs runs_br;  dp vs runs_dp
             (runs_br and runs_dp from war_source.stint_frame("bat", provider="bwar"), summed per player-season)
d_i        = h_i - PA_i * (sum_j h_j) / (sum_j PA_j)      (MLB-wide per PA, every batting row)
ewar_v2_ebr_i = eWAR_v2_i + sum over i's stints k of (d_i * PA_k / PA_i) / RPW_team(k)
             RPW_team: the per team-season runs per win eWAR v2 already recovers (ewar.py:703-743),
             imported, never edited
```

- **No label path:** fWAR is the training label either way. **Becoming the displayed WAR** would
  need its own registered gate against eWAR v2's baserunning, a pass and an owner decision, all after
  the fWAR epoch; Leg E's verdict against FanGraphs' BsR is not that gate.

### 9.4 The skill and position parts (candidate parts 3 to 6): definitions

The formulas are `part8/xwar.md` section 2's, verbatim where quoted, with its base replaced by the
frozen fWAR vintage (the former skill plan's row X1 and its R1: never the replica's own total, and
no eBR term inside a skill delta). Four rules:

1. **Never sum or scale an index.** HEM+ is a ratio with a spread gain, SEM+ and REM+ are inverted
   FIP ratios on pool constants, DEM+ is a z-score. Each delta comes from the shrunk RATES beneath
   the index, which each module already computes (`woba_skill`, `fip_skill`, `rate_shrunk`).
2. **Delta = skill arm minus actual arm, through the same function.** Everything common to both arms
   (the park term, the framing charge, IFFB, replacement, the league pool) cancels, so a delta needs
   no FanGraphs leaderboard input and carries no replica residual.
3. **Re-centre every delta to zero per season and side,** so a part moves wins between players and
   never creates them.
4. **Shrink with each EM+ module's own constants and pool targets, unchanged.** No constant is refit
   here; a change to any constant is a new registration.

**S1, candidate part 4, the HEM+ arm** (`hem_plus` constants by reference):

```
D_i        = AB + BB - IBB + SF + HBP                       (hem_plus._woba_denom)
n_i,e      = counts of e in {uBB, HBP, 1B, 2B, 3B, HR}      (uBB = BB - IBB; 1B = H - 2B - 3B - HR)
mu_s,e     = sum_pool n_k,e / sum_pool D_k,  pool = {D_k >= 50}          (hem_plus.build_pool)
r~_i,e     = (n_i,e + K_e * mu_s,e) / (D_i + K_e)           K = uBB 120, HBP 240, 1B 290, 2B 1000, 3B 1600, HR 170
wOBA_i     = sum_e W_s,e * n_i,e / D_i                      actual, on the season's SOLVED weights (league_constants)
wOBA~_i    = sum_e W_s,e * r~_i,e                           skill, same weights
g_bat,i    = ((wOBA~_i - wOBA_i) / scale_s) * PA_i          (the wRAA difference, fwar_frame.wraa)
```

**S1x, candidate part 4, the xHEM+ arm** (SWAR-Q3 (c); registered here, no number of it exists):

```
for a hitter-season with a Savant xwOBA and PA >= 200 (the subset the xHEM+ gate speaks for):
  xbar_s     = the PA-weighted mean Savant xwOBA of season s's Savant pool at PA >= 100
               (the normalizer the served xHEM+ column uses, hitter_export._join_xhem_plus, by reference)
  xwOBA~_i   = xwOBA_i * lgwOBA_s / xbar_s
  g_batx,i   = ((xwOBA~_i - wOBA_i) / scale_s) * PA_i
every other hitter-season: g_batx,i = g_bat,i (the HEM+ arm's value)
```

  The Savant xwOBA is read from the source the served xHEM+ column reads, never re-fetched for this
  file; a season 2016 or later that the source lacks stops the build.
- **Pitcher-batters are not shrunk** (g_bat = g_batx = 0 on rows the replica marks `is_pitcher`).
  Two-way players are shrunk as hitters. HEM+ excludes steals, so S1 never overlaps candidate part 1.

**S2, candidate part 5** (`rem_plus` and `sem_plus` constants by reference):

```
TBF_j, IP_j, G_j, GS_j, m_j,c for c in {K, BB, HBP, HR}       (the StatsAPI season pitching line)
nu_SP,c   = sum m / sum TBF over the SEM+ pool                  (sem_plus.build_pool)
nu_RP,c   = sum m / sum TBF over the REM+ pool                  (rem_plus.build_pool)
sigma_j   = start innings / IP                                  (the replica's role innings)
nu_j,c    = sigma_j * nu_SP,c + (1 - sigma_j) * nu_RP,c
q~_j,c    = (m_j,c + K_c * nu_j,c) / (TBF_j + K_c),   K = (70, 170, 170, 400)
m~_j,c    = TBF_j * q~_j,c
dFIP_j    = (13*(m~_HR - m_HR) + 3*((m~_BB - m_BB) + (m~_HBP - m_HBP)) - 2*(m~_K - m_K)) / IP_j
pFIPR9 arm   = FIPR9 / PF   and   pFIPR9 + dFIP / PF          PF: the leave-one-out FIP- back-solve
war0 arm     = (RAAP9 / dRPW + RepLvl) * IP_role / 9 per role, RepLvl 0.12 start / 0.03 relief
               relief lines x (1 + gmLI_j) / 2, gmLI = the published feed value, the same in both arms
dwar0_j      = war0(skill) - war0(actual)                 on the replica's feed-only arm plain_fip_loo_pf
Delta_j      = dwar0_j - IP_j * (sum_k dwar0_k / sum_k IP_k)   the WARIP re-pin: pitchers' deltas sum to 0
```

- `dFIP` is exact: the FIP constant and IFFB are common to both arms and cancel; no 1.0 floor applies
  to a runs delta. sigma = 1 and sigma = 0 reproduce SEM+'s and REM+'s targets exactly (starters on
  SEM+'s pool, relievers on REM+'s).
- **Position players who pitch** (the nopp rule): Delta = 0, outside the re-pin.
- **Leverage L-A:** the published gmLI levers both arms; L-B (gmLI 1 in both arms) is computed as a
  disclosure and never served.
- **The home-run term is its own arm** (orchestrator ruling X8). S2 is computed in two variants: HR
  shrunk with REM+'s and SEM+'s shipped K_HOMERUN (400 batters faced), and HR left at fWAR's own
  home-run term. Part 9.5's HR-arm clause picks one.

**S3, candidate part 6** (`dem_plus` constants by reference):

```
inn_i,p     = innings at p from data/fielding_innings.json
Fld_i       = saber_feed fld;  Frm_i = saber_feed frm, counted only if inn_i,C > 0   (dem_plus.fld_total)
K_i         = sum_p K_INN[p] * inn_i,p / sum_p inn_i,p                                (dem_plus.shrink_k)
rel_i       = inn_i / (inn_i + K_i)
g_fld,i     = rel_i * (Fld_i + Frm_i) - (Fld_i + Frm_i)  =  -(1 - rel_i) * (Fld_i + Frm_i)
```

- 2016 on only. Pitchers carry no fielding. Runs come through `saber_feed.load_components`, never
  the Defense board path. This is the construction of the 2026-09-09 plan's W1.3 arm 6
  ("Reliability-shrunk fielding"), registered here as a candidate part of eWAR v3 for display only.

**S4, candidate part 3** (`positional_fit` by reference):

```
L_s       = positional_fit.fit_ladder(feeds, last = s)   rolling 6-season window ending at s
I_s, a_s  = that fit's innings per 650 PA and innings per PA
DH_i      = max(0, PA_i * a_s - sum_p inn_i,p)             the ladder's own DH exposure spec
Pos~_i    = sum_p L_s[p] * inn_i,p / I_s + L_s[DH] * DH_i / I_s
g_pos,i   = Pos~_i - Pos_FG,i                              Pos_FG = the feed's published positional
```

- Pitcher-batters keep the frame's credit (g_pos = 0). The served-ladder variant (the window [2021,
  2026]) is a sensitivity only. The ladder is an inversion of Baseball-Reference's `runs_position`,
  so S4 imports Baseball-Reference's positional pricing into FanGraphs' frame; totals are unaffected.

**Each candidate part alone** (the object the skill look scores):

```
hitter i:   d_c,i = g_c,i - PA_i * (sum_k g_c,k) / (sum_k PA_k)     c in {pos, bat, batx, fld}
            test value  fWAR_i + d_c,i / RPW_s
pitcher j:  test value  fWAR_j + Delta_j                            (on the HR term the HR-arm clause chose)
```

**Invariants** (`test_swar.py`, built by EWV3_SKILL_BUILD_CORE): (1) every K at 0 gives every delta 0,
so every test value equals fWAR; (2) with HEM+'s frozen weights, wOBA~ equals `hem_plus.woba_skill`;
(3) with the pool constant and no IFFB, the skill-arm FIP equals `fip_skill`, the floor aside; (4)
`rel x (Fld + Frm)` equals DEM+'s `rate_1000_shrunk x inn / 1000` for every board fielder; (5) the
fielding part of Pos~ equals `dem_plus.ladder_pos_runs`; (6) every part's re-centred delta sums to 0
per season and side within 1e-9 runs, under both HR variants; (7) nopp and pitcher-batter rows carry
zero delta; (8) a build leaves the sha256 of `data/ewar.json` unchanged and imports no
`fg_leaderboards`.

### 9.5 The skill look (candidate parts 3 to 6)

`tools/swar_lab.py` computes everything in this part ONCE, on the day part 7.3 allows, and the
holdout ONCE, on the day part 7.4 allows. No other code path relates a skill or ladder delta, or any
WAR rebuilt from them, to a next-season quantity, at any time.

| Item | Registered value |
|---|---|
| Question, per candidate part | does fWAR(Y) + the part's re-centred delta rank published fWAR(Y+1) better than fWAR(Y) does? |
| Pairs | (Y, Y+1) for predictor seasons Y = 2021, 2022, 2023, 2024; 2020 excluded on both sides |
| Population | MLB player-seasons by MLBAM; candidate parts 3, 4 and 6 on hitters, candidate part 5 on pitchers; a two-way player is on each side |
| Floors | hitters 200 PA in both seasons; pitchers 50 IP in both seasons |
| Target | published fWAR(Y+1) per PA (hitters) or per IP (pitchers), from the frozen vintage; for pitchers that is FanGraphs' FIP-based WAR, so no pitching disposition is an RA9 claim |
| Cells | per part, a rate cell (per PA or per IP, unrounded) and a total cell (season totals on the same pairs): candidate part 3 {H-rate, H-cum}; candidate part 4 {HEM+ H-rate, HEM+ H-cum, xHEM+ H-rate, xHEM+ H-cum}; candidate part 5 {P-rate, P-cum}; candidate part 6 {H-rate, H-cum} |
| Holm families | one per candidate part, over that part's cells (k = 2, 4, 2, 2); no correction across parts |
| Statistic | Spearman; gap = rho(test value, target) - rho(B0, target); convention v2 primary (player-clustered, season-stratified bootstrap, within-outcome-season z target), v1 reported and required to agree in sign; Pearson reported beside, no weight |
| Pre-committed null, per cell | gap <= 0, one-sided bootstrap p |
| Baselines | B0 = fWAR(Y) (rate or total); B1 = a uniformly shrunk fWAR, (x * n + m * k) / (n + k), one k per side fitted on 2016 to 2018 predictor pairs by EWV3_SKILL_BUILD_LAB before the look, on published fWAR only; bWAR(Y) reported, never deciding |
| Twin | the part's delta permuted across players within (season, side, exposure decile), added back to fWAR; it must not reproduce the gain (the twin's gap lo95 <= 0) |
| Era transport (candidate part 5) | the P-rate gap point estimate against B0 is positive in BOTH the 2016 to 2018 block and the 2021 to 2024 block |
| HR-arm clause (candidate part 5, computed FIRST) | the P-rate gap of the pitching part with the home-run shrink over the pitching part with fWAR's own home-run term must be positive in both blocks, under convention v2. The single global HR-shrink k was closed for eWAR on 2026-09-09 ("a single global HR-shrink k (R2e.2 no-ship, did not transport)", `docs/master-plan-2026-09-09-fangraphs-ewar-betting.md` negative list; `ewar.py@64bf1bb3:312-336`); this clause is that closure's transport test applied to this arm. If it fails, the home-run term reverts to fWAR's in both pitcher cells and in the served series, and the record says "consistent with R2e.2's closure"; it licenses no HR-shrink proposal for eWAR v2, and R2e.2 is not re-run |
| MDE95 | computed in the run and printed beside every gap; where it exceeds 0.02, EQUIVALENT is unreachable for that cell, stated here in advance |
| Bootstrap | B = 2,000; seed 20261008, the commit date of this document as YYYYMMDD |
| Floors first | the run prints each cell's bootstrap sd, half-width and MDE95 before any gap |

**Dispositions, per cell, against B0 (orchestrator ruling X1).** Each cell takes the first
disposition that holds in the order WIN, SMALL WIN, LOSS, EQUIVALENT, UNRESOLVED, so exactly one
applies.

- **WIN:** Holm rejects on the one-sided bootstrap p of the gap, lo95 > 0, and the point gap is at
  least the registered margin +0.02. **WIN (components)** when also: lo95 > 0 against B1 (candidate
  parts 4, 5 and 6; not applicable to candidate part 3, a ladder being no shrink), the twin's gap
  lo95 <= 0, and for candidate part 5 the era transport holds. **WIN (regression only)** otherwise.
- **SMALL WIN:** Holm rejects and lo95 > 0, but the point gap is under +0.02. It counts as
  EQUIVALENT for admission and copy.
- **LOSS:** hi95 < 0.
- **EQUIVALENT:** the 90 percent interval of the gap lies inside -0.02 to +0.02.
- **UNRESOLVED:** anything else.
- Beside every WIN the record prints, with no weight, whether the 1.645-sd interval lies entirely
  above +0.02 (`docs/EFV_GATE_STANDARD.md` part 8's SHIP).
- The precedence is pinned by a fixture test in the lab (`test_swar_lab_dispositions.py`): a
  Holm-rejected gap +0.008 on an interval +0.002 to +0.014 is SMALL WIN, among others.

**Descriptive legs (no verdict weight, each labelled descriptive in the record):** delta sizes per
part and season (sd, max, share of rows moving 0.1, 0.5 and 1.0 WAR, top movers); agreement of each
test value with fWAR and bWAR; team-season sums against same-season wins and, on full-schedule pairs
only, next-season wins (computed only inside the look run and printed only in part 12.2, never by an
exporter, on a page, in the served copy of the record or in copy); self-persistence (reported, never
a win: shrinkage raises it mechanically); exposure-band bias (mean test value minus fWAR by PA and IP
band); the starter-heavy (sigma >= 0.5) and reliever (sigma <= 0.10) subsets of candidate part 5; the
L-B leverage disclosure; split-half calibration of the batting and pitching constants on the
play-by-play corpus (alternate games per player within a season, Spearman-Brown corrected, against
n / (n + K)); the coverage census (rows, ambiguous ids, nopp and pitcher-batter rows, swingmen).

**Registered expectations** (predictions drawn from the priors part 10 lists, not measurements):
the HEM+ arm's H-rate is EQUIVALENT, SMALL WIN or UNRESOLVED; the xHEM+ arm's H-rate point gap is
positive; candidate part 5's P-rate point gap is positive and larger on starter-heavy pairs;
candidate part 6 is EQUIVALENT or UNRESOLVED; candidate part 3 is LOSS or UNRESOLVED, because its
target carries FanGraphs' own positional adjustment; on every skill part the gap against B1 is
smaller than the gap against B0; every twin fails; on same-season team wins every skill test value
scores below fWAR; short samples are flattered (mean test value minus fWAR is positive below 200 PA
and below 40 IP).

**The holdout.** The 2025 to 2026 pairs (predictor season 2025), the same floors, cells, statistics,
precedence and home-run term as the look, run once on the day part 7.4 allows, reported beside the
verdict and never merged into it; it changes no admission.

**The record.** The look writes its machine-readable result into the TRACKED file
`docs/ebr-2026-09-30/swar_eval.json` beside this document, in the same commit as part 12.2
(`docs/HEM_RIV_REGATE_GATE.md` R1-12: a verdict that lands without its artifact is a defect), never
only into a gitignored cache; the holdout appends its block to that file in its own commit with part
12.3; EBR_3_EWAR_V3's flip copies the file byte for byte to `data/swar_eval.json`. A second run of
either is forbidden whatever the first printed.

**Crash protocol.** Before the look the whole reporting path runs on synthetic fixtures with nulls
(`tools/swar_lab.py --dry-run`). The run's stdout and stderr are teed to the writer's output
directory before anything else runs. On any exception after scoring began: STOP, no rerun, an owner
question.

### 9.6 What each skill-look result licenses

**Admission (under part 1's EWV3-Q1 and EWV3-Q2 answers).** A candidate part enters eWAR v3 only when
its rate cell is WIN (components) and its total cell is not LOSS (EWV3-Q1 (a); under EWV3-Q1 (b) any
WIN on the rate cell with the total cell not LOSS). For candidate part 4, each arm is judged on its
own two cells; when both arms qualify, the HEM+ arm enters unless the xHEM+ arm's rate gap over the
HEM+ arm's (rho of the xHEM+ test value minus rho of the HEM+ test value, same pairs, same bootstrap,
computed only when both qualify and outside the Holm family) has lo95 above 0, in which case the
xHEM+ arm enters (EWV3-Q2 (a); under (b) the arm with the larger point gap against B0 enters; under
(c) the xHEM+ arm enters whenever it qualifies). A candidate part not admitted leaves FanGraphs' own
component in place. A VOID skill look (a crash after scoring began, or a precondition found broken after
the run) admits nothing.

| Disposition of the part's rate cell | The one comparative sentence copy may carry, with its numbers |
|---|---|
| WIN (components) | "ranked the next season's fWAR better than fWAR itself did, and better than a uniformly shrunk fWAR" (for candidate part 3, without the second clause) |
| WIN (regression only) | "ranked the next season's fWAR better than fWAR itself did" (no credit to the EM+ component) |
| SMALL WIN or EQUIVALENT | "ranked the next season's fWAR about as well as fWAR itself did" |
| LOSS | "ranked the next season's fWAR less well than fWAR itself did" |
| UNRESOLVED | none |

Each sentence names its frame: "on 2021 to 2024 seasons, hitters with 200 or more PA (pitchers with
50 or more IP) in both seasons, Spearman gap +x (95 percent interval a to b, n pairs)". No sentence
claims "more accurate WAR", "better than FanGraphs" or "true talent".

### 9.7 The assembled series

```
hitter i:   g_i  = sum over admitted outcome parts (9.2) of (eBR_c,i - FG_c,i)
                   + [g_pos,i if part 3 admitted] + [g_bat,i or g_batx,i if part 4 admitted, per 9.6]
                   + [g_fld,i if part 6 admitted]
            d_i  = g_i - PA_i * (sum_k g_k) / (sum_k PA_k)
            eWAR_v3_i = fWAR_i + d_i / RPW_s
pitcher j:  eWAR_v3_j = fWAR_j + [Delta_j if part 5 admitted, on the chosen home-run term]
```

- Re-centring is linear, so the assembled d_i equals the sum of the admitted parts' own re-centred
  deltas. The league totals equal fWAR's (570 hitters and 430 pitchers per 2,430 games), and each
  player's eWAR v3 minus fWAR is the sum of named admitted departures, published per player and
  part.
- The admitted parts were each scored alone; their combination is never scored, and copy claims
  nothing about it beyond each part's own sentence.
- A season a part does not cover (eBR before 2018 without EBR-Q4 (b), 2020's runner record, the skill
  and position deltas before 2016) carries FanGraphs' component for that part, marked `fg`.
- **When no part is admitted,** eWAR v3 equals fWAR on every row, the artifact says so in its meta,
  and the column's label reads "eWAR v3 (equals FanGraphs WAR: no part admitted)".
- The column is labelled "eWAR v3"; on the card's reference (SWAR-Q4 (a)) each admitted part is
  named: "eBR steals and extra bases", "eBR double plays", "position (our ladder)", "eWAR skill:
  batting (HEM+)" or "(xHEM+)", "eWAR skill: pitching", "eWAR skill: fielding".
- Completed seasons freeze on November 1 with sha256 digests; the live season rebuilds nightly; a
  new eBR version, a changed EM+ constant, a changed ladder module, a changed replica pitcher chain or
  a new part is a new construction and a new registration.

## 10. Disclosure: what was computed before this registration

1. **A sibling construct's same-season agreement.** The Baserunning plan's prototype (five advancement
   classes, steals keyed on `eventType`, one double-play cost a season, raw per-season RE24) computed
   per-player values for 2024, 2025 and 2026 and published concurrent correlations at PA 300+: against
   BsR 0.756, 0.756, 0.672; against B-Ref Rbaser + Rdp 0.833, 0.842, 0.820; SB runs against wSB 0.849,
   0.776, 0.758; XB runs against Savant XB 0.727, 0.675 (2025, 2026); SDs 3.47 to 3.66 runs against
   BsR's 2.65 to 2.79. Its per-player files are sealed by sha256 prefix and were never joined across
   seasons: `proto_brr_2024_runners.csv` 4f1d4632f874b8f5, `proto_brr_2025_runners.csv`
   f77ba2030c72dfbc, `proto_brr_2026_runners.csv` e99930bbaec2039e, `proto_brr_2024.json`
   d91b0635d3052025, `proto_brr_2025.json` 078871abb5989e25, `proto_brr_2026.json` 3bc4de32c738c256.
2. **Public-versus-public baselines** (Pearson): r(BsR, B-Ref br + dp) 0.745 to 0.858 at PA 502+ and
   0.750 to 0.841 at PA 300+ (2016 to 2026 without 2020); r(feed wGdp, B-Ref dp) 0.708 to 0.782; year
   over year at PA 300+ in both seasons, pairs 2016-2017 to 2025-2026: BsR 0.624 to 0.734, BsR minus
   wSB 0.565 to 0.670, wSB 0.365 to 0.608, B-Ref br + dp 0.545 to 0.640, B-Ref dp 0.428 to 0.576;
   r(sprint speed, BsR per 600) 0.645 to 0.731; r(sprint speed, B-Ref br per 600) 0.462 to 0.564.
   Same season, B-Ref `runs_br + runs_dp` against BsR (PA 300+, 2011 to 2025): r 0.67 to 0.89 per
   season, sd of the difference 1.5 to 1.9 runs.
3. **A power estimate on public series, on this frame:** BsR self-persistence 0.6488, B-Ref `runs_br`
   0.4794, difference -0.1694, bootstrap sd 0.0223, half-width 0.0367; B-Ref `runs_br` to next season's
   BsR 0.5297 against BsR's own 0.6488 (sd 0.0182); same-season r between the two 0.7686.
4. **League tables:** RE24 cells per season, K = 1,714 plays (W 1.541, tau^2 0.00090), lambda 0.962 to
   1.058, the steal break-evens, the double-play costs by state (0.30 to 1.54 runs), the park
   descriptive (2,310 chances at 34 venues in 2026, venue SD 5.09 points against a binomial 5.45) and
   the arm descriptive (1.5 to 4.5 points, tangled with field location). None is a runner value.
5. **Census counts:** SB and CS keyed on `movementReason` equal StatsAPI's for every player in every
   completed season 2018 to 2025; GIDP exact for 97.4 to 100 percent of players, the league total 0 to
   15 short. I2's GIDP line therefore has little margin: 97.37 percent exact in 2021 against its 97
   percent bar (the bundle's `_player_repro.json`), and the one re-fetch of part 3 is the only relief
   before a miss blocks that season.

No year-to-year, split-half or forward number of eBR or of any eBR-like construct exists at this
commit. If one is found before the outcome look, every year-to-year leg moves to the 2026-2027 pair and
the outcome look moves after the 2027 regular season, by amendment, before any look.

### Read to write this: the skill and position parts

Orchestrator ruling X3 of the former skill plan, carried here. Every component prior below was
already read on pairs identical to or overlapping the skill look's, so the skill look is NOT a blind
read on those components; the registered expectations of part 9.5 are drawn from them, the twin and
B1 carry the blind weight, and every admission clause stays. Each is related and none is a skill-part
forward statistic.

- **DEM+** (`data/dem_plus_eval.json`): predictor seasons 2021 to 2024, 1,255 pairs, exactly the skill
  look's hitter frame; 0.4597 against the raw rate's 0.4531, gap +0.0067, 95 percent interval -0.0039
  to +0.0172.
- **SEM+** (`data/sem_plus_eval.json`): seasons 2018 to 2025 without 2020, 592 pairs, next-season
  RA9; 0.4167 against raw FIP's 0.3821, gap +0.0342 (+0.0177 to +0.0508) under v1, +0.0264 (lower
  bound +0.0098) under v2.
- **REM+** (`data/rem_plus_eval.json`): 878 pairs, next-season RA9, rho 0.2363 against raw FIP's
  0.211, gap lo95 +0.0013 under v1; the registry restamp's v2 lower bound -0.0043.
- **HEM+** (`data/hem_plus_eval.json`): seasons 2012 to 2024 without 2020, 3,372 pairs, a tie with raw
  wOBA (0.4119 against 0.4087, gap lo95 -0.0096).
- **xHEM+** (registry `xhem_plus`, `data/xhem_served_regate_eval.json`): 1,871 pairs of hitters with
  200 or more PA (2016 to 2025 without 2020), 0.4619 against actual wOBA's 0.4108 on next-season
  wOBA; the gate speaks for that subset only.
- **The HEM+ versus xwOBA prior** (registry `hem_plus` notes, 1,871 pairs, 0.4084 against 0.4456): a
  prior, not a gate; its registered re-gate is the 2026-11-16 one the skill look waits for.
- The pitcher target here is FanGraphs' FIP-based WAR per inning, not the RA9 those pitcher gates
  read, so no pitching disposition is an RA9 claim.
- **Census of skill-like statistics** (the former skill plan's R12): no file relates a sum of EM+
  skill deltas, a ladder delta or any WAR rebuilt from shrunk components to a next-season quantity.
  The search ran only over named paths and globs (`<part8>/` and its subfolders, `docs/`, `tools/`,
  `.cache/swar*`, and names matching `*swar*` or `*skill*war*`), never a walk of `.cache`. The eBR
  lane's `ebr/_ewar_leg_power.json` and `_ewar_leg_power2.json` read BsR only, on public series:
  related, not skill-like.

No forward number of a skill or position part exists at this commit. If one is found before the skill
look that this document cannot exclude, the skill look moves to the unseen frame (predictor season
2026, outcome 2027, after the 2027 regular season) by amendment, before any look on it.

## 11. Amendments

A dated amendment, committed alone, may only: (i) record in part 1 an owner answer that arrived, or
changed, after this commit; (ii) fix a definition defect that an identity gate, a bug band or a part
9.4 invariant exposed, stating the defect, its evidence and the fix, never chosen by reference to any
year-to-year or forward number; (iii) move the outcome look's year-to-year legs to the 2026-2027 pair
under part 10's rule; (iv) move the skill look to its unseen frame under part 10's rule. An amendment
lands BEFORE the look whose clauses it touches: before the outcome look for parts 2 to 6 and the
outcome rows of part 1; before the skill look for parts 9.4 to 9.6 and the rows of part 1 those parts
read (SWAR-Q0 to SWAR-Q3, EWV3-Q1 to EWV3-Q3). Frames, statistics, thresholds, margins, Holm
families, twins, guards, the dates and the claims never change. After a look, nothing it read
changes; after both looks, nothing above part 12 changes.

### 11.1 2026-10-14: the SB-runs bug band compares like with like (clause (ii))

- **Defect.** Part 4's band "r(SB runs, wSB)" compares SB runs, which part 2.7 defines as eSB +
  ePK, with FanGraphs' wSB, whose scope is steals and caught stealing (pickoff caught stealing
  included). ePK, the pickoffs of runners who were not attempting, has no wSB counterpart, so the
  band compares two scopes. The defect is in the band's comparison, not in eBR.
- **Evidence** (task EBR_2A_CORE_DARK's preview build of 2026-10-09, kept under `.cache/ebr/preview/`;
  same-season aggregates only; no year-to-year, split-half or forward number was computed): at PA 300+
  r(eSB + ePK, wSB) read 0.745 to 0.815 over the eight seasons, under 0.80 in 2018, 2019, 2022, 2024
  and 2026, while r(eSB, wSB) read 0.855 to 0.919 in every season. wSB recomputed with FanGraphs' own
  linear weights on the record's steal and caught-stealing counts equals the feed's `wSb` at r 1.000
  (mean absolute difference at most 0.0006 runs) and I1 and I2 hold exactly, so the counts are right.
  ePK's sd among those runners is 0.38 to 0.51 runs a season. The sibling prototype of part 10 item 1
  had already read this comparison at 0.776 and 0.758 (2025 and 2026), under the band.
- **Fix** (owner answer EBR-2A (a), 2026-10-14, the recommended option under the standing
  instruction, `DECISIONS_FOR_OWNER.md`): part 4's "SB runs against wSB" comparison and its bug band
  read eSB against wSB, at the same 0.80 and the same PA cuts; ePK's sd and r(ePK, wSB) are reported
  beside it every build. Nothing else changes: eBR, its five parts, the display parts and sub-totals of
  part 2.7 (SB runs stays eSB + ePK), Leg E's E = (eSB + ePK + eXB) / PA, the other bands, the frames,
  statistics, thresholds, guards and dates.
- Committed alone, before the outcome look (part 12.1 is empty at this commit).

### 11.2 2026-10-15: the skill look's target becomes next-season realized runs (clause (i), owner decision EW3-23)

- **Owner answer, verbatim** (2026-10-15, `DECISIONS_FOR_OWNER.md` EW3-23): "Yes, do your
  recommendation, with next-season realized runs becoming the target rule." Part 1 gains this row,
  recorded here because part 1 is not edited in place:

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| EW3-23 | What the skill look scores candidate parts 3 to 6 against | next-season realized runs of each part's own component decide (11.2.1 to 11.2.3); team runs and wins in Y+1 are a non-inferiority guard (11.2.4); published fWAR(Y+1) is reported as a secondary estimand that decides nothing (11.2.5) | answered 2026-10-15 (`DECISIONS_FOR_OWNER.md`, EW3-23); registered by queue task EWV3_TARGET_AMEND |

- **What this amendment departs from, disclosed.** Clause (i) lets an amendment record an owner
  answer; the sentence above it says that frames, statistics, thresholds, margins, Holm families,
  twins, guards, the dates and the claims never change. This amendment changes the skill look's
  target, its base, its B1 baseline, candidate part 3's statistic, adds one guard and replaces part
  9.6's copy sentences. It does so only because the owner decided it (EW3-23) before the skill look
  ran, and it is recorded as an owner override of that sentence for these items alone. Unchanged:
  the frame (predictor seasons 2021 to 2024, 2020 out on both sides), the floors (hitters 200 PA,
  pitchers 50 IP, in both seasons), the cells of candidate parts 4 to 6 and their Holm families (k =
  4, 2, 2), the margin +0.02, the twin, the dispositions and their precedence, convention v2
  primary with v1 required to agree in sign, B = 2,000 and seed 20261008 for the cells, MDE95 and
  floors printed first, the era transport and HR-arm clauses, the admission rules EWV3-Q1 (a) and
  EWV3-Q2 (a), the holdout, the record and every clock of part 7. Parts 2 to 6 (the outcome look,
  candidate parts 1 and 2 and BEM+) are not touched.
- **Why.** The registered target, published fWAR(Y+1), carries FanGraphs' own construction: its
  positional adjustment (part 0 already expected the ladder to lose for that reason), its FIP-based
  pitching and its fielding source. Ranking fWAR(Y+1) rewards a part for agreeing with FanGraphs'
  construction a season later, not for forecasting what the player does. The runs a part's own
  component records in Y+1 are the quantity the part claims to forecast.

#### 11.2.1 The primary target, per component (deciding)

| Component | Candidate part | Base B0, season Y | Test value | Target, season Y+1: rate cell; total cell |
|---|---|---|---|---|
| Batting | 4 (both arms) | wRAA_i(Y) = ((wOBA_i - lgwOBA_s) / scale_s) * PA_i on the season's solved weights (`league_constants`, `fwar_frame.wraa`): actual events, the actual arm of S1 | B0 + the arm's re-centred delta (d_bat or d_batx) | batting runs above average from actual PA events in Y+1 on Y+1's solved weights, the same construction: per PA; in runs |
| Pitching | 5 | war0 of the actual arm of S2 on the replica's feed-only arm `plain_fip_loo_pf`: FanGraphs' FIP-based pitching runs as the frame carries them | B0 + Delta_j on the home-run term the HR-arm clause chose | RA9* (below) in Y+1, sign reversed so that fewer runs rank higher: per IP; runs prevented above average (lgRA9*_s - RA9*_j) * IP_j / 9 in total |
| Fielding | 6 | Fld + Frm in Y (the actual arm of S3, `saber_feed`) | B0 + d_fld, re-centred | fielding runs in Y+1 from an independent source (11.2.2): per PA; in runs |
| Baserunning | none in this registration | eBR's realized runs in Y (part 2) | B0 + the part's re-centred delta | realized eBR runs in Y+1 on part 2's RE24 record (eSB + ePK + eXB; eGDP for a double-play part): per PA; in runs |
| Position | 3 | see 11.2.3 | see 11.2.3 | see 11.2.3 |

- **The base.** B0 is the actual arm of the part's own delta function in season Y: what eWAR v3
  carries for that component when the part is not admitted. Each cell therefore compares admitting
  the part with not admitting it, and a part must add forward signal beyond the player's own
  realized component. For batting and fielding B0 is the player's realized runs in Y on the part's
  own source. For pitching it is the frame's FIP-based runs (realized strikeouts, walks, hit
  batters and home runs), because the pitching part departs from FanGraphs' FIP chain, not from
  runs allowed. Beside every cell the record prints, with no weight, B0r, the target's own
  construction in season Y (RA9* in Y for pitching; the independent source in Y for fielding; for
  batting B0r is B0), and the test value's Spearman gap over B0r.
- **Baserunning.** Candidate parts 1 and 2 stay decided by the outcome look's persistence legs and
  guards (parts 5 and 6), whose reason, that no next-season baserunning target is free of a rival
  construct (part 5.2), stands; Leg E, Leg T, the E-DP contrast and BEM+'s gate X-B1 (whose target
  is already eBR's rate in Y+1) are unchanged. The baserunning row binds only a skill part on
  baserunning registered later.
- **The pitching target, RA9*.** Context-neutral runs allowed, adjusted for park, the club's
  defense and inherited and bequeathed runners:

```
RA*_j    = R_j - BQS_j + E_BQ_j + (IRS_j - E_IR_j)
           R_j     runs charged to pitcher j (the StatsAPI season pitching line)
           BQS_j   runners j left on base who later scored (charged to j)
           E_BQ_j  sum over those runners of p_s(base, outs at j's exit)
           IRS_j   runners j inherited who scored (charged to the pitcher who left them)
           E_IR_j  sum over j's inherited runners of p_s(base, outs at j's entry)
           p_s(base, outs): the season's share of runners on that base with that many outs who
                   scored before the half-inning ended, on the fit set of part 2.3
RA9*_j   = 9 * (RA*_j / PF_j + BF_j * F_t / BF_t) / IP_j
           PF_j    the park factor of the S2 chain (the leave-one-out back-solve), applied to runs
                   as pFIPR9 applies it to FIP
           F_t     club t's fielding runs in Y+1 from the frozen vintage (Fld + Frm summed over its
                   fielders; positive when the defense saved runs), shared by batters faced; a
                   pitcher with two clubs sums his stints
lgRA9*_s = the season's league RA9*
```

  Runners are tracked through the bases on the runner record (part 2.2). If a season of the era
  transport block (outcomes 2017 to 2019) lacks the play-by-play the runner terms need, RA9* for
  that season drops the two runner terms and keeps park and defense, and the record says so.
  The gmLI weighting (L-A) stays in both arms of Delta and the target carries none; the L-B
  disclosure stays.
- **B1, amended.** The uniformly shrunk base, (x * n + m * k) / (n + k): x the B0 rate, n the
  exposure, m the season's exposure-weighted mean B0 rate at the floor, one k per component
  (batting, pitching, fielding), k = hm (1 - r) / r with r the pooled Pearson of the B0 rate in Y
  and the component's target rate in Y+1 on the 2016 to 2018 predictor pairs at the floors (the
  rule and clamp of `swar_lab.fit_b1`). It is fitted from B0 and the target only, with no candidate
  part, delta or test value read, and frozen with its log before the look. The constants frozen at
  a32ff1bb (k 662 PA for hitters and 244 IP for pitchers, fitted on published fWAR) serve only the
  secondary estimand of 11.2.5. WIN (components) reads lo95 above 0 against this B1.
- **The twin, era transport and HR-arm clause** are computed as registered with B0 in place of
  fWAR(Y) and the primary target in place of fWAR(Y+1): the delta permuted within (season, side,
  exposure decile) and added back to B0; the transport blocks 2016 to 2018 and 2021 to 2024; the
  HR-arm clause first.

#### 11.2.2 The independent fielding source

- A part that reads FanGraphs' Fld (candidate part 6, through `saber_feed`) is scored on
  Baseball-Reference's `runs_field` per player-season (`war_source.stint_frame("bat",
  provider="bwar")`, summed over stints, read from the cached `.cache/war_daily` copy as it stands
  on look day, never fetched, its sha256 and `fetched_at` printed before any statistic).
- A part led by Savant OAA is scored on DRS, and a part led by DRS on Savant OAA or fielding run
  value (2016 on). A part that blends several sources (the triangulation of task EWAR_LADDER) is
  scored leaving one source out: for each source S it reads, the part rebuilt without S is scored
  on S in Y+1, and the cell's gap is the mean of the per-source gaps, one cell inside the same
  bootstrap.
- Before any statistic the record prints, per season, which fielding system each source's runs
  come from, citing the source's own documentation. Where the part's source and its target share a
  system in a season, that season's target is the next source in the order Baseball-Reference
  `runs_field`, Savant fielding run value that the part does not read, and the record says so.
- Catchers are scored on whatever catcher scope the target source carries; the C rows' gap is
  reported beside, with no weight. This follows the SDR gates' practice of measuring a fielding
  number against more than one incumbent source (`docs/sdr-2026-08-18/SDR_EVAL_GATE.md` C1 and C2);
  the rule that the target never comes from the part's own source is new here.

#### 11.2.3 Candidate part 3, the position part: the ladder's out-of-sample rule

- A positional adjustment is a convention with no realized run total of its own to forecast, so
  candidate part 3 keeps the ladder's own out-of-sample rule in place of the Spearman cells. Its
  one test (Holm family k = 1) is the held-out mean absolute error difference (dMAE) registered in
  `docs/ewar/LADDER_V2_GATE.md` (task EWAR_LADDER_REDERIVE: leave one season out, predicting the
  realized defensive plus positional runs of players who switched positions), comparing the ladder
  that gate leaves standing (v2 if it passed, else v1) with FanGraphs' published positional
  adjustment, the base S4 departs from, entered as a fixed comparator on the same rows.
- Admitted when the dMAE in the ladder's favour has a bootstrap lo95 above 0 under that gate's
  bootstrap and seed, that gate's permuted control fails, and the team guard of 11.2.4 is
  NON-INFERIOR. If that gate's read does not carry the FanGraphs comparator, the skill look
  computes this one comparison on that gate's registered estimand, rows and bootstrap, once, in the
  same run.
- The position part's H-rate and H-cum cells are reported under the secondary estimand only. Part
  9.5's registered expectation for candidate part 3 (LOSS or UNRESOLVED, because the target carried
  FanGraphs' own adjustment) no longer binds a deciding test; none is registered for the dMAE
  comparison.

#### 11.2.4 The team guard (non-inferiority, deciding)

- **Question.** Does the part keep roster-weighted WAR at least as informative about the next
  season's club runs and wins as the frame without it?
- **Club-seasons.** Outcome seasons 2022 to 2025 (predictor seasons 2021 to 2024; 2020 out), 30
  clubs a season, 120 club-seasons; the five seasons 2021 to 2025 enter.
- **Roster weighting, turnover handled.** For club c in Y+1, S_c = sum over every player i who
  played for c in Y+1 of (v_i(Y) / n_i(Y)) * n_ic(Y+1): v_i(Y) the series value in Y (fWAR(Y) for
  the frame; fWAR_i + d_c,i / RPW_s or fWAR_j + Delta_j for the part's series; bWAR(Y) for the
  reference), n_i(Y) his exposure in Y (PA for hitters, IP for pitchers), n_ic(Y+1) his exposure
  with club c in Y+1. A player with no MLB exposure in Y enters at 0 in every series. No floor
  applies. Hitter and pitcher sides are summed separately, and the total is their sum. Y+1 playing
  time is known only after the fact; it is the same in every series, so it favours none.
- **Outcomes,** from the cached StatsAPI standings and team season lines, never fetched on look
  day: every part on run differential and wins (total sums); batting also on runs scored (hitter
  side) and pitching also on runs allowed (pitcher side, sign reversed). Fielding and position
  parts sit on the hitter side, whose sum is mostly batting, so they carry run differential and
  wins only.
- **Statistic,** per outcome: dT, the Pearson r of the part's roster sum with the outcome minus the
  Pearson r of the frame's roster sum with it (the form of Leg T, part 5.3).
- **Intervals.** Two bootstraps, B = 2,000 each, seed 20261024: player-clustered (players drawn
  with replacement with all their rows, every club sum recomputed from the drawn players, outcomes
  fixed) and club-clustered (franchises drawn with replacement with all their club-seasons). Both
  bootstraps' sd and half-width per outcome are printed before any dT.
- **NON-INFERIOR** when dT - 1.645 sd is above -0.02 under both bootstraps, for every outcome the
  part carries. Each outcome must pass, so no multiplicity correction applies. A part that is not
  NON-INFERIOR is not admitted, whatever its primary cells read.
- **Power, stated honestly.** No power figure was computed for this amendment, because computing
  one relates WAR sums to club outcomes, which happens only inside the look. 120 club-seasons is a
  small sample: the guard can see only a large loss of team information and can pass a part that
  costs a little. A part is a small zero-sum departure, so the two roster sums sit close together,
  which narrows the interval of dT. Where a printed half-width exceeds 0.02 the guard cannot reach
  NON-INFERIOR even at a true difference of 0; the part is then not admitted, and the record says
  the guard was underpowered, not that the part did harm.
- **bWAR** enters as a reference: the r of the bWAR roster sum with each outcome, and its difference
  from the part's, are reported beside, deciding nothing (the frame's choice of fWAR over bWAR is
  not a part's to decide).
- **Where its numbers go.** As for Leg T (parts 5.3 and 5.10): the r values and dT only in part 12.2
  and the tracked record's look block; the flip's served copy `data/swar_eval.json` carries the
  guard's NON-INFERIOR flag per outcome and the margin, never an r against runs or wins, so that
  copy is a filtered copy of the tracked record, not a byte copy (Part 8's 8.A rule wins over part
  9.5's byte-copy sentence). No exporter computes the guard.
- This guard replaces part 9.5's descriptive next-season wins leg for the parts it decides; the
  same-season wins leg stays descriptive.

#### 11.2.5 The secondary estimand (reported beside, deciding nothing)

Part 9.5's cells as first registered: B0 = fWAR(Y), B1 at the constants frozen at a32ff1bb, the
target published fWAR(Y+1), the same frame, floors, bootstrap and precedence. Their dispositions
are printed beside the primary ones, labelled secondary. No admission, guard or copy sentence reads
them.

#### 11.2.6 Admission and copy, amended

- A candidate part 4, 5 or 6 enters eWAR v3 only when, on the primary target, its rate cell is WIN
  (components) and its total cell is not LOSS (EWV3-Q1 (a)), and its team guard is NON-INFERIOR.
  Candidate part 4's choice between arms (EWV3-Q2 (a)) is computed on the primary target. Candidate
  part 3 enters as 11.2.3 states. Candidate parts 1 and 2: part 6, unchanged. A VOID skill look
  admits nothing.
- The one comparative sentence copy may carry, in place of part 9.6's table; [component's runs] is
  "batting runs", "runs allowed (adjusted for park, defense and inherited runners)" or "fielding
  runs (from <the target source>)":

| Disposition of the part's rate cell on the primary target | The sentence, with its numbers |
|---|---|
| WIN (components) | "ranked the next season's realized [component's runs] better than the season's own [component's runs] did, and better than a uniformly shrunk version of them" |
| WIN (regression only) | "ranked the next season's realized [component's runs] better than the season's own [component's runs] did" (no credit to the EM+ component) |
| SMALL WIN or EQUIVALENT | "ranked the next season's realized [component's runs] about as well as the season's own [component's runs] did" |
| LOSS | "ranked the next season's realized [component's runs] less well than the season's own [component's runs] did" |
| UNRESOLVED | none |

  For candidate part 3 on a pass: "on held-out seasons, our ladder matched position switchers'
  realized defensive and positional runs more closely than FanGraphs' positional adjustment did";
  otherwise none. Each sentence names its frame as part 9.6 requires. No sentence cites the
  secondary estimand or the team guard's r values, and part 8's may-not list stands.

#### 11.2.7 Parts registered after this amendment

The pitch-economy parts PE-P and PE-H (task EWAR_T1_PITCH_ECON), the pitching-basis challenger (task
EWAR_PITCH_BASIS) and the fielding triangulation (task EWAR_LADDER) each name in their own
registration, committed before any number, the component target of 11.2.1 they are scored on, their
B0 and their cells. A part whose value lies outside the four components (pitch economy's innings and
bullpen cost) defines there its realized Y+1 run quantity from actual Y+1 events. None uses a
published WAR total as its deciding target. Each carries the team guard of 11.2.4 and reports the
secondary estimand.

#### 11.2.8 eWAR realized has no forward target

The companion series "eWAR realized" (owner decision EW3-20) records actual runs in the frame. This
amendment gives it no forward target and no look scores it. Its only checks are accounting checks at
every build: each realized part sums to zero per season and side, and the series' league-season run
totals reconcile with the frame's. It licenses no forecasting sentence.

#### 11.2.9 What was read before this amendment

No number of any target of this amendment exists for any candidate part at this commit: no lab ran
on them, and tools/swar_lab.py at this commit computes the fWAR(Y+1) target only. The new targets
sit closer than fWAR(Y+1) to targets the component gates already read on overlapping pairs (part
10, 'Read to write this'): HEM+ and xHEM+ on next-season wOBA, SEM+ and REM+ on next-season RA9,
DEM+ on its own source's next-season rate. On batting and pitching the skill look is therefore even
less blind than part 10 states; the twin, B1 and the team guard carry the blind weight. The
independent fielding target, the dMAE comparison against FanGraphs' positional adjustment and the
team guard have no prior read. Registered expectations on the primary target, in place of part
9.5's for candidate parts 3 to 6 (predictions from those priors, not measurements): the xHEM+ arm's
H-rate point gap is positive and a WIN (components) is plausible (its gate read 0.4619 against
actual wOBA's 0.4108 on next-season wOBA); the HEM+ arm's H-rate is EQUIVALENT, SMALL WIN or
UNRESOLVED (its gate tied raw wOBA); candidate part 5's P-rate point gap is positive (SEM+ read
+0.0264 over raw FIP under v2 on next-season RA9; REM+ near 0) and larger on starter-heavy pairs;
candidate part 6 is EQUIVALENT or UNRESOLVED, with a smaller point gap than DEM+'s own-source read;
every twin fails; every team guard is NON-INFERIOR.

#### 11.2.10 Before the skill look

- The skill look (part 7.3) does not run until `tools/swar_lab.py` implements this amendment (the
  primary targets, B0, B0r, the amended B1, the independent fielding source, the team guard, the
  dMAE fallback of 11.2.3 and the secondary block), its fixture test pins them, B1's component
  constants are fitted and frozen with their log, and a dry run on fixtures with nulls passes. That
  lands in its own commit, with no number of a candidate part computed, and part 7.3's precondition
  1 reads it.
- Committed alone, docs and its pin test only, before the skill look (part 12.2 is empty at this
  commit). No served number moves.

### 11.3 2026-10-15: the pitch-economy candidate parts PE-P and PE-H (clause (i), owner decisions EW3-19 and EW3-23)

- **Owner answer, as recorded** (2026-10-15, `DECISIONS_FOR_OWNER.md` EW3-19): "pitch economy =
  register BOTH a hitter and a pitcher part for the v3 skill look". Part 1 gains this row, recorded
  here because part 1 is not edited in place:

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| EW3-19 (pitch economy) | Whether pitch economy is a candidate part of eWAR v3 | both: a pitcher part PE-P and a hitter part PE-H, registered here before the skill look and scored in it on the amended estimand of 11.2 | answered 2026-10-15 (`DECISIONS_FOR_OWNER.md`, EW3-19); registered by queue task EWAR_T1_PITCH_ECON |

- **What this amendment departs from, disclosed.** Clause (i) lets an amendment record an owner
  answer; adding two candidate parts goes beyond recording one. 11.2.7 named these parts as parts
  registered after 11.2 and requires each registration to name its target, its B0 and its cells
  before any number. This amendment does that, before the skill look ran, and is recorded as an
  owner-decided addition (EW3-19) on the footing of 11.2. Nothing registered for candidate parts 1
  to 6 changes: their definitions, frames, statistics, thresholds, margins, Holm families, twins,
  guards, dates and claims stand as part 9 and 11.2 leave them.
- **Pinned by** `test_pitch_economy_registration.py`, beside `test_ebr_gate_registration.py`. The
  descriptive lab, the decomposition and the fit of this amendment's frozen constants are
  registered in `docs/ewar/PITCH_ECONOMY_LAB.md`, committed with this amendment.

#### 11.3.1 What the two parts are, and why neither adds a pitch count to WAR

- Realized WAR already counts what pitches buy: a hitter's walks and strikeouts are in his batting
  runs, and a pitcher's innings are in his innings. A pitch count added on top would count twice.
  Each pitch-economy part is therefore a SKILL departure in the form of part 9.4's rule 2: a skill
  arm minus an actual arm through the same function, shrunk with constants frozen before the look,
  re-centred to zero per season and side (rule 3), and scored on next-season realized runs (11.2).
  Neither part is a raw P/PA, P/BF, P/IP or PAR term.
- **PE-P (pitchers)** replaces the outs a pitcher actually recorded by the outs his shrunk
  efficiency implies through the passed starter-workload chain, and prices the difference against
  the bullpen that covers the outs he does not, with a times-through-order decay for starters.
- **PE-H (hitters)** credits two shrunk residuals that wOBA's events do not carry: the count
  lift a hitter gains beyond what his plate-appearance outcomes imply (RE288), and the pitches
  he makes the opposing starter throw beyond what his outcomes imply, priced as starter wear.
- **Inputs, read from caches, never fetched by this part:** the StatsAPI season lines
  (`.cache/fa_statsapi_pitching_<Y>.json`, `.cache/fa_statsapi_hitting_<Y>.json`); the StatsAPI
  start and relief split lines (`.cache/pitch_rates/pitching_sprp_1_<Y>.json`, the files
  `pitch_rates.py` keeps); the play-by-play corpus (`.cache/pbp_corpus`) and eBR's runner record
  (`.cache/pbp_runners`); RE288 (`data/count_value.json`, `count_value_v1`); the season constants
  of `league_constants`; the starter-workload model's frozen priors (`data/starter_workload_eval.json`
  `burn_in.priors`). The arithmetic lives in the pure module `pitch_economy.py`, built after this
  commit, which also holds the frozen constants of 11.3.6.

#### 11.3.2 PE-P, the pitcher part

```
for pitcher j in season s and role r in {SP, RP}       (the start and relief split lines, stints summed)
  n_j,r      appearances: GS for SP, G - GS for RP
  P_j,r      pitches in role r;  O_j,r  outs in role r
  L_ppo,s,r  = sum P / sum O over the season's role-r lines (pooled)
  L_pa,s,r   = sum P / sum n over the season's role-r lines (pooled)
  ppo~_j,r   = (P_j,r + K_o * L_ppo,s,r) / (O_j,r + K_o)            K_o = 120 outs
  b~_j,r     = (P_j,r + k_b * L_pa,s,r) / (n_j,r + k_b)             k_b = 2 appearances
  X~_j,r     = n_j,r * min(27, b~_j,r / ppo~_j,r)                   efficiency-implied outs (skill arm)
  G_j,r      = X~_j,r - O_j,r                                       skill arm minus actual arm, in outs
  F~_j       = (13*m~_HR + 3*(m~_BB + m~_HBP) - 2*m~_K) / IP_j + cFIP_s
               the S2 skill arm's FIP per nine (part 9.4, the start-share blend), before the park term,
               on the home-run term part 9.5's HR-arm clause chose
  F_RP,s     = the season's pooled FIP per nine of true relievers (GS / G at or below 0.10), on cFIP_s
  pi_s       = the season's league batters faced per out
  T9_s       = 27 * pi_s * delta_TTO                                times-through-order decay, runs per nine
  c_j,SP     = (F_RP,s - F~_j - T9_s) / 27                          runs per out: the starter against the bullpen
  c_j,RP     = (F_RP,s - F~_j) / 27                                 runs per out: the reliever against the bullpen
  g_j,r      = G_j,r * c_j,r
  Delta_PE,j = sum over r of ( g_j,r - O_j,r * (sum_k g_k,r) / (sum_k O_k,r) )   zero-sum per season and role
  test value = B0_j + Delta_PE,j / RPW_s                            RPW_s as part 9.2
```

- K_o and k_b are the starter-workload model's frozen priors, taken by reference: the model whose
  stage 1 PASSED (`data/starter_workload_eval.json`, outs MAE 2.918 against A0's 3.442), whose
  candidate is xouts = min(27, budget / (ppo x r_L)). The lineup ratio r_L is 1 here: the opposing
  lineup's P/PA earned nothing in that lab (its T1), and a season line has no single opponent. The
  priors were chosen on starts; relief appearances use them unchanged, disclosed.
- delta_TTO is the one constant fitted for this part (11.3.6), on the 2018 and 2019 corpus seasons,
  frozen before any look; every other quantity above is a same-season league aggregate or a frozen
  constant taken by reference.
- A position player who pitches (the nopp rule) carries Delta_PE = 0, outside the re-centring. A
  pitcher with no split line carries 0 and is counted as a coverage gap. A pitcher with both roles
  carries each role's own terms.

#### 11.3.3 PE-H, the hitter part

```
for hitter i in season s, over his corpus plate appearances a
(intentional walks with no pitch thrown, plays with no pitch, and pitcher-batter rows excluded)
  e(a)       the terminal class of a: walk, hit by pitch, strikeout, single, double, triple, home run,
             out in play, other
  CL_a       = count lift: sum, over the pitches of a before its last pitch whose step leaves the bases and outs
               unchanged, of [V(after) - V(before)]     V: the RE288 ledger's state value (count_value), season s
  CLres_i    = sum over a of (CL_a - CLbar_s,e(a))      CLbar_s,e: the season's league mean CL_a by class
  Pres_i     = sum over a faced against the opposing starter of (p_a - pbar_s,e(a))
               p_a: pitches thrown in a; pbar_s,e: the season's league mean by class, plate appearances against starters
  w_s        = (F_RP,s - F_SP,s - T9_s) / (27 * L_ppo,s,SP)     starter-wear runs per pitch, to the batting side
               F_SP,s: the season's pooled FIP per nine of true starters (GS / G at or above 0.50)
  g_PEH,i    = CLres_i * n_i / (n_i + K_CL) + w_s * Pres_i * m_i / (m_i + K_P)
               n_i: his counted plate appearances; m_i: those against the opposing starter
  d_PEH,i    = g_PEH,i - PA_i * (sum_k g_PEH,k) / (sum_k PA_k)   zero-sum per season, MLB-wide per PA, every hitting row
  test value = B0_i + d_PEH,i                                    runs, on the batting B0 of 11.2.1
```

- The starter is the first pitcher of each fielding half (the starter-workload lab's unit, owner
  decision O22). K_CL and K_P are fitted for this part (11.3.6). PA_i is the StatsAPI season line's.
- The corpus holds 2018, 2019 and 2021 on; every season of the frame and its outcome seasons is a
  corpus season. A season outside the corpus carries d_PEH = 0, marked `fg`.
- Pitcher-batters carry 0; two-way players are hitters here.
- **Why residuals and not P/PA.** P/PA largely restates the walk and strikeout rates wOBA already
  prices (relative P/PA correlates 0.624 with the relative walk rate and 0.450 with the relative
  strikeout rate, `data/_labs/efv_pitch_rate_features.json`). Measuring each plate appearance against
  the league mean for its own terminal class removes the event mix, so neither term restates an
  event wOBA counts.

#### 11.3.4 Targets, bases and cells (as 11.2.7 requires)

| Part | Component | Base B0, season Y | Test value | Target, season Y+1: rate cell; total cell | Exposure; floors |
|---|---|---|---|---|---|
| PE-P | pitching: innings and bullpen cost, outside the four components of 11.2.1 | the pitching B0 of 11.2.1 (war0 of the actual arm of S2 on `plain_fip_loo_pf`) | B0 + Delta_PE / RPW_s | RSB in Y+1: per game pitched; in runs | games pitched; pitchers 50 IP in both seasons |
| PE-H | batting plus starter wear | wRAA_i(Y), the batting B0 of 11.2.1 | B0 + d_PEH | wRAA_i(Y+1) + W_i(Y+1): per PA; in runs | PA; hitters 200 PA in both seasons |

```
RSB_j(Y+1) = (O_j(Y+1) / 27) * (lgRA9*_RP,Y+1 - RA9*_j(Y+1))
             runs saved over a league-average reliever across the outs he actually recorded;
             RA9* as 11.2.1 defines it (park, the club's defense, inherited and bequeathed runners);
             lgRA9*_RP the season's pooled RA9* of true relievers
W_i(Y+1)   = w_Y+1 * Pres_i(Y+1)
             realized starter wear: the pitches he actually made opposing starters throw beyond his
             outcomes' league means, priced at the season's league rate, unshrunk
```

- **Frame, population and statistics** as part 9.5 amended by 11.2: predictor seasons 2021 to 2024
  (2020 out on both sides); MLB player-seasons by MLBAM; Spearman gaps; convention v2 primary with
  v1 required to agree in sign; B = 2,000 and seed 20261008; MDE95 and the floors printed first;
  the dispositions and their precedence.
- **Holm families:** {PE-P rate, PE-P total}, k = 2; {PE-H rate, PE-H total}, k = 2; one per
  candidate part, as part 9.5 has it; no correction across parts.
- **B1, the amended rule of 11.2.1,** one k per part, fitted from B0 and the part's own target
  only, frozen with its log before the look: PE-P on the 2016 to 2018 predictor pairs at the floors
  (RA9* dropping its runner terms where 11.2.1 says so); PE-H on the 2018 to 2019 pair, the only
  corpus pair before the frame.
- **The twin:** the part's delta permuted across players within (season, side, exposure decile)
  and added back to B0; its gap's lo95 must be at or below 0.
- **Era transport (PE-P):** the rate cell's point gap against B0 is positive in BOTH the 2016 to
  2018 block and the 2021 to 2024 block (part 5's clause, applied to this pitcher part; its delta
  needs no corpus season, and delta_TTO is frozen).
- **The sensitivity guard (PE-H, deciding):** W is the part's own construct in Y+1, so a gain on W
  is partly persistence. The rate cell's gap on wRAA_i(Y+1) alone, W left out, must not be LOSS
  (hi95 below 0); it is computed in the same bootstrap and printed beside the cell.
- **The team guard of 11.2.4,** unchanged: PE-P on the pitcher side (runs allowed, run differential,
  wins), PE-H on the hitter side (runs scored, run differential, wins).
- **The secondary estimand of 11.2.5,** unchanged: published fWAR(Y+1) per IP or per PA and in
  total, B1 at the constants frozen at a32ff1bb; it decides nothing.
- **Reported beside, no weight:** PE-P on 11.2.1's pitching target (RA9* per IP; runs prevented
  above average in total); the starter-heavy (sigma at or above 0.5) and reliever (sigma at or below
  0.10) subsets; PE-H's two terms scored one at a time; the delta sizes per season (sd, max, share
  of rows moving 0.1, 0.5 and 1.0 WAR, top movers).

#### 11.3.5 Admission, assembly and copy

- **Admission.** PE-P or PE-H enters eWAR v3 only when, on its primary target, its rate cell is WIN
  (components) (Holm rejects, lo95 above 0 and the point gap at least +0.02 against B0; lo95 above
  0 against its B1; the twin fails; for PE-P the era transport holds), its total cell is not LOSS,
  its team guard is NON-INFERIOR and, for PE-H, the sensitivity guard is not LOSS. Each part is
  scored alone; their combination with each other or with candidate parts 1 to 6 is never scored
  and copy claims nothing about it. A part not admitted leaves FanGraphs' own number, with no
  pitch-economy term. A VOID skill look admits neither.
- **Assembly** (part 9.7, extended): a hitter's g_i gains g_PEH,i when PE-H is admitted, before the
  per-PA re-centring (re-centring is linear, so the result equals adding d_PEH,i); a pitcher's
  eWAR v3 gains Delta_PE,j / RPW_s when PE-P is admitted.
- **Headline only.** Both are predictive parts (owner decision EW3-20): an admitted part enters the
  headline eWAR. "eWAR realized" (11.2.8) carries no pitch-economy term under this registration.
- **Labels** on the card's reference (SWAR-Q4): "eWAR skill: pitch economy (pitching)" and "eWAR
  skill: pitch economy (batting)".
- **Copy.** The sentence table of 11.2.6, with [component's runs] read as "runs saved over a
  league-average reliever (adjusted for park, defense and inherited runners)" for PE-P and "batting
  runs plus starter-wear runs" for PE-H; each sentence names its frame as part 9.6 requires; part
  8's may-not list stands.

#### 11.3.6 Frozen constants, the lab, and what was read before this amendment

- **The constants.** delta_TTO (PE-P and PE-H's w_s), K_CL and K_P (PE-H) are fitted ONCE by
  `tools/pitch_economy_lab.py` under `docs/ewar/PITCH_ECONOMY_LAB.md` part 7, on the 2018 and 2019
  corpus seasons only (outside the frame's predictor and outcome seasons), from same-season data,
  and frozen in `pitch_economy.py` with their log in `data/_labs/pitch_economy_constants.json`
  before any look. K_CL and K_P come from a split-half reliability of the two residuals, which is a
  split-half statistic of an input to a skill delta; part 7.6 reserves such statistics to the look
  tools, and this one fit is allowed as part of the owner-decided addition, on the footing of B1's
  pre-look fit. A split-half correlation at or below 0 sets that K to infinity (the term carries 0),
  never re-chosen. The skill look reads the frozen values and refits nothing.
- **Read before this amendment** (each related, none a statistic of either part):
  `data/pitch_rates.json` `stability` (consecutive-season pairs 2021 to 2026): hitter P/PA 0.778,
  starter P/BF 0.692, starter P/IP 0.489, reliever P/IP 0.362; the eFV pitch-rate arms `ppa_rel`
  and `pbf_rel`, refused at DS-06 on 2026-10-14 (`data/xfv_arm_ledger.json`); `ppa_rel` against
  `bb_rel` 0.624 and against `k_rel` 0.450; the starter-workload stage 1 (PASS; the pitcher's own
  pitches per out earned credit for length, its T2; the opposing lineup's P/PA earned nothing, its
  T1); RE288 (`data/count_value.json`, built 2026-10-15), which values no player. None relates a
  pitch rate or a pitch-economy delta to a next-season quantity on this frame's pairs.
- **What the lab reads after this commit.** `docs/ewar/PITCH_ECONOMY_LAB.md` (owner ask T1, steps 1
  and 2) relates raw pitch rates to next-season wOBA, wRAA, RA9, innings and innings per start on
  pairs overlapping the frame (2016 to 2025 without 2020), and computes the decomposition, the PE
  deltas included, for the same season only. It computes no year-to-year, forward or split-half
  statistic of Delta_PE or d_PEH, and no 2026 outcome. The skill look is therefore not blind on the
  raw rates, as part 10 says of the components; the twin, B1 and the team guard carry the blind
  weight. Nothing in 11.3.2 to 11.3.5 changes after the lab: a change is a new registration on the
  unseen frame (predictor season 2026, outcome 2027).
- **Registered expectations** (predictions, not measurements): PE-H's rate cell is EQUIVALENT or
  UNRESOLVED (pitches seen mostly restate events wOBA prices); PE-P's rate point gap is small,
  EQUIVALENT or UNRESOLVED most likely, because a shrink of pitches per out at K_o 120 moves few outs
  for a 50-IP pitcher and B1 captures most of any shrink; every twin fails; each team guard is
  NON-INFERIOR or underpowered.

#### 11.3.7 Before the skill look

- The skill look (part 7.3) does not run until `tools/swar_lab.py` implements this amendment (both
  parts, their targets RSB and W, their B1 fits, the twin, PE-P's era transport, PE-H's sensitivity
  guard, the team guard and the secondary block), its fixture test pins them, and a dry run on
  fixtures with nulls passes. The fixture test carries a null comparator and a planted recovery: a
  delta planted as a fixed share of the target's own Y+1 deviation reads WIN on both cells, an
  all-zero delta never reads WIN, and the planted delta's twin fails. That lands in its own commit,
  with no number of a candidate part computed, and part 7.3's precondition 1 reads it.
- Committed alone, docs and their pin test only, before the skill look (part 12.2 is empty at this
  commit). No served number moves.

## 12. Results

**EMPTY AT REGISTRATION.**

### 12.1 The outcome look (parts 5 and 6)

EMPTY.

### 12.2 The skill look (parts 9.5 and 9.6)

EMPTY.

### 12.3 The skill holdout (part 9.5)

EMPTY.

No identity receipt of the final build, agreement figure of the final build, persistence,
reliability, forward gap, disposition, admission or BEM+ clause has been computed on eBR, on a skill
or position part, or on eWAR v3 at this commit. None may be written anywhere above this line. Once a
block below holds an entry, nothing above this line changes except a dated amendment that part 11
still allows for the look not yet run. Each entry is dated, names the commit that produced it and the
output of `tools/ebr_gate.py` or `tools/swar_lab.py` verbatim, and states what part 6 or part 9.6
licenses under part 1's recorded answers.
