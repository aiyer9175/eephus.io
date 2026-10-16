# MILB_FIELDING_RUNS_GATE: in-house MiLB fielding runs (registered 2026-10-16)

STATUS: REGISTERED 2026-10-16. This document is committed ALONE, before the measure's tool exists,
before the fielder-credit fetch runs and before any number of its estimands or of its coverage
census is computed. A change after the first number is a dated note in part 10, never an edit
above it.

Owner decision EW3-33 (2026-10-16, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): SDR-MILB-Q1 answered
"build MiLB fielding runs". Task MILB_FIELDING_RUNS commissions an in-house minor-league fielding
measurement in runs from MiLB play-by-play, reads it once under this gate, and serves it only if
estimand (b) passes. It is the MiLB defensive measurement in runs that MILB_SDR_EVAL_GATE.md
(Amendment 2026-10-15, "What would re-open it") asks for. EWAR_SDR_PROSPECT_DISPLAY is superseded
by this task (EW3-33). Timing: an OWNER-WAIVED EARLY READ under EW3-5 (no look day applies).

## 0. What was read before this registration

- G-A (`SDR_EVAL_GATE.md`, Results 2026-10-15): FAIL (pooled C1 persistence SDR 0.4031 vs OAA
  0.4696; C2 SDR 0.1499 vs rfield 0.1808). Post-hoc, deciding nothing: the pooled OAA rate carries
  persistent position-mean differences; centred within (primary position, season) SDR 0.3994, OAA
  0.3823, rfield 0.3516. That lesson is applied here BEFORE any number: every pooled statistic in
  this gate is computed on rates centred within position (part 4).
- G-C (`MILB_SDR_EVAL_GATE.md`): NOT RUN; no MiLB measurement in runs exists in Will's method.
- SDR_CATCHER_GATE.md (read 2026-10-16): B-Ref rfield carries no catcher framing.
- Payload shape only: three StatsAPI `playByPlay` payloads (game 721340, 751368, 642903) were
  opened to confirm that each play's `runners[].credits` names the fielder (MLBAM id, position code,
  credit type `f_putout`, `f_assist`, `f_fielded_ball`, `f_fielding_error`, ...), that substitution
  actions carry player and position, and that pitch events carry `pitchData` (pX, pZ, zone top and
  bottom) where tracked. No count, rate or coverage share was computed from them.
- The existing corpus `.cache/efv4_pbp/{sport}/{season}/{gamePk}.json.gz` (milb_pbp_fetch.py) keeps
  trajectory, hardness, fielder location code and field coordinates per ball in play but NO fielder
  identity, so it cannot attribute a play to a player. Never computed before this document: any
  coverage share, any fielding statistic by player, any statistic named in parts 4 to 6.

## 1. Data

- **Fetch (fielder credits).** For every final regular-season game of the in-scope cells (below)
  the StatsAPI `/api/v1/game/{gamePk}/playByPlay` payload with a `fields` filter, reduced to compact
  rows under `.cache/milb_fielding/pbp/{sport}/{season}/{gamePk}.json.gz` (resumable, one file per
  game). A game held by the shared `/feed/live` cache (`.cache/game_feeds`, final feeds) is reduced
  from that file instead of the network. Schedules are read from `.cache/efv4_pbp/schedule/` (the
  existing cached lists; the Mexican League excluded as there). Network rule: at most 4 concurrent
  requests, a descriptive User-Agent, retry with backoff on 429 and 5xx, never inside the 06:00 to
  11:00 UTC blackout. Dates are waived by EW3-5.
- **Reduced rows per game.** Plays: at-bat index, inning, half, event type, outs after the play,
  batter side; per runner movement: play index, runner id, origin base, start, end, out flag, the
  runner's event type; per credit: play index, the runner's event type, fielder id, position code,
  credit type; per substitution action: player id, position code; the ball in play's hitData
  (trajectory, hardness, location code, coordX, coordY); per taken pitch (call codes B, *B, C):
  balls and strikes before the pitch, pX, pZ, zone top, zone bottom.
- **Cells in scope.** Sports 11 (AAA), 12 (AA), 13 (A+), 14 (A) and 16 (ROK, complex and DSL
  leagues), seasons 2021 to 2026 (no 2020 season). A (level, season) cell is IN when at least 80%
  of its scheduled final games return a reduced play list; a cell below that is reported and left
  out (coverage census, part 2).
- **MLB side (targets).** B-Ref `runs_field` and `Inn` per player-season from
  `.cache/war_daily/bat.parquet` (G-A's construction); FanGraphs-hosted fielding per player-season-
  position from `.cache/sdr/home/defense_plus/data/raw/fg_field_full_{season}.csv` (Inn, OAA, UZR,
  DRS, FRP). MLB debut season: the first season with any StatsAPI MLB fielding line in
  `.cache/statsapi_field/fld_{season}.json` (2000 to 2026). The sha256 and modified time of each
  source are printed before any statistic.
- **Consensus field grade (estimand c).** `data/_labs/tool_tables_rederived/grade_rows_frozen.json`
  (committed ccec9eb7): the last pre-debut `tools_consensus` point of each debuts.json record,
  identity-resolved outcome-blind, R-LV grade-point years (2020, 2021) and R-VM debuts excluded; its
  `field` key is consensus.py's per-tool rule (unweighted mean over publishing outlets, rounded to
  0.5). Never grouped, stratified or binned by any future-value grade.

## 2. Coverage census (computed after this commit, before the measure)

Per (level, season): scheduled final games, games reduced, plays, balls in play, the share of balls
in play with a trajectory, with coordinates, with a credited fielder, and the share of taken
pitches with pX and pZ. Printed and committed with the tool (part 9 step 2). The census decides
only which cells are IN (part 1) and which construction each ball in play takes (part 3); it never
sees an estimand.

## 3. The construction (fixed here)

Positions: C, 1B, 2B, 3B, SS, LF, CF, RF (code 2 to 9). Pitchers are not rated. The defense is the
home team in a top half, the away team in a bottom half.

- **Alignment.** Who stands at position k at play i of a game: per (game, defensive team, position)
  a timeline of (play index, player) from every credit at k and every substitution action naming k;
  the holder at play i is the last timeline entry at or before i, else the first after i. A player's
  innings at k are the outs recorded while he holds k, divided by 3.
- **Balls in play.** Plays whose last pitch is in play with trajectory ground_ball, line_drive,
  fly_ball or popup (bunts excluded), not a home run, interference or fan interference. Out = at
  least one out recorded on the play and the event is not a hit or an error (field_out, force_out,
  grounded_into_double_play, double_play, triple_play, fielders_choice_out, sac_fly,
  sac_fly_double_play). Everything else (single, double, triple, field_error, fielders_choice) is a
  non-out. The initial fielder of an out is the position of the first credit on the play.
- **Located construction (expected outs by type, direction and level).** A ball in play with a
  trajectory and coordinates gets spray angle a = atan2(x - 125.42, 198.27 - y) in degrees (clamped
  to plus or minus 50) and distance 2.5 x the coordinate distance in feet. Cell c = (level,
  trajectory, hardness or "na", angle bin) with 5-degree angle bins, and for line drives, fly balls
  and popups also a 30-foot distance bin. Out rate p_c and the responsibility share w_ck (the share
  of the cell's outs whose initial fielder is k) are fitted per level on all IN seasons pooled. Run
  value per cell: delta_c = mean linear-weight value of the cell's non-outs minus the out's value,
  with fixed weights out -0.27, single +0.47, double +0.77, triple +1.04, error and fielder's choice
  +0.47. Fielder runs on one ball in play: each position k with w_ck > 0 gets
  (1[k made the out] - p_c w_ck) x delta_c, credited to the holder of k at that play.
- **Range-factor construction (location absent).** A ball in play without trajectory or coordinates
  is credited range-factor style: the holder of k gets (1[k made the out] - q_Lk) x delta_L, with
  q_Lk the level's share of unlocated balls in play turned into outs by k and delta_L the level's
  mean delta over located balls in play.
- **Double plays (1B, 2B, 3B, SS).** Opportunity: a ground-ball out whose initial fielder is an
  infielder, a runner on first, fewer than two outs before the play. DP turned = two or more outs on
  the play. The initial fielder gets (dp - r_Lk) x 0.40 runs, r_Lk the level-position DP rate.
- **Outfield arm (LF, CF, RF).** Opportunity: each runner on base at the start of a single or double
  whose `f_fielded_ball` credit is an outfielder. Outcome: kill (runner out on the play, any
  outfield assist on it), extra base (from first to third or home on a single, from second home on
  a single, from first home on a double), else hold. Offense value relative to a hold: kill -0.65,
  extra base +0.25. The fielding outfielder gets expected value minus observed value, expectations by
  (level, position, event, start base).
- **Catcher framing (proxy, tracked pitches only).** Taken pitches (B, *B, C) with pX, pZ and zone
  bounds: z = (pZ - bottom) / (top - bottom), x = pX signed so positive is away from the batter.
  Called-strike probability per level from a grid of 2-inch x bins and 0.1 z bins by count group
  (pitcher ahead, even, batter ahead), fitted on all IN seasons of the level. Framing runs =
  (called strike - p) x 0.13 per pitch, to the holder of C. Pitches without location give no framing
  run. No pitcher adjustment (disclosed).
- **Catcher throwing.** Steal attempts of second and third (stolen_base_2b/3b, caught_stealing_2b/3b,
  pickoffs excluded) with the holder of C: (cs - s_L) x 0.65, s_L the level's caught-stealing rate.
- **Level norms.** Every component's runs are centred to an innings-weighted mean of zero within
  (level, season, position).
- **Reliability shrinkage.** Per position, total runs per inning; split-half reliability on
  player-season-level rows with 200+ innings, halves by alternate games of the player's sequence,
  Spearman-Brown to full length r at the rows' mean innings n_bar, k = n_bar (1 - r) / r (k capped
  at 5,000 innings and set to the cap when r <= 0). Shrunk rate = runs / (innings + k).
- **Translation across levels (chained same-player, like EFV_X1).** For adjacent levels lo -> hi
  (ROK -> A -> A+ -> AA -> AAA), the linking rows are a player at the same position at both levels in
  the same season with 100+ innings at each. f(lo -> hi) = sum(w r_hi s_lo) / sum(w s_lo^2), with
  s_lo the shrunk rate at lo, r_hi the raw rate at hi and w = min(innings), clamped to [0.25, 2.0];
  fewer than 15 linking rows gives f = 1 (printed). AAA-equivalent factor F_L = the chained product.
- **The measure (MFR).** A player's MFR at position k over a set of seasons = sum over levels of
  F_L x runs_L / (sum of innings + k_k), in AAA-equivalent runs per inning, reported per 1,000
  innings. A player-season MFR uses that season's levels only.

## 4. Estimands and frames (pooled statistics always on rates centred within position)

- **(a) Persistence within MiLB.** Pairs (Y, Y + 1), Y 2021 to 2025: a player with 200+ MiLB innings
  at position k in both seasons (pooled across levels; MLB innings never enter). Statistic:
  Spearman of MFR(Y) and MFR(Y + 1), each centred within (position, Y). Per-position cells reported.
- **(b) Pre-debut MFR vs MLB fielding runs.** Players with MLB debut season D in 2022, 2023 or 2024
  (R-VM debuts 2025 on excluded by efv_vintage_frame.guard_vm_request); MLB primary position k = most
  FanGraphs innings over seasons D to 2026 (pitchers and DH-only excluded); predictor = MFR at k over
  MiLB seasons 2021 to D - 1 with 200+ MiLB innings at k. Targets over seasons D to 2026 pooled:
  T1 = B-Ref rfield per 1,000 innings (300+ innings), T2 = OAA per 1,000 innings at OAA positions
  (1B to RF, 300+ innings with OAA). Statistic: Spearman of predictor and target, each centred
  within k. Reported, never deciding: FRP per 1,000 innings at k (catchers included, the catcher
  cell on FRP), UZR (seasons to 2024), DRS, the per-position cells, and the predictor at the MiLB
  primary position instead of the MLB one.
- **(c) Incremental over the consensus field grade.** The (b) rows that carry a frozen consensus
  `field` grade. Statistic: rank partial correlation of the predictor and the target given the
  grade (each rank regressed linearly on the grade's rank; Pearson of the residuals). Reported: the
  grade's own Spearman with each target on the same rows.

## 5. Inference, comparators and pass rules

- Bootstrap: B = 2,000 resamples of players (a player's every pair or row together), seed 20261016;
  LB95 and UB95 are the 2.5th and 97.5th percentiles; one-sided p = (draws <= 0 + 1) / (B + 1).
- **Zero comparator.** A constant has no ranks; clearing zero means LB95 > 0.
- **Null comparators.** N-a: the whole pipeline on a fielder-shuffled corpus (within each (level,
  season, position), the player ids of the stints are permuted, seed 20261017), persistence
  rho_null with its bootstrap interval. N-b and N-c: the predictor permuted within position (seed
  20261018). A null that clears its own rule VOIDS the estimand's read (a leak), never a pass.
- **Planted recovery.** P-a: the located balls in play re-drawn with a planted per-player out
  probability s_p ~ N(0, 0.02) held across seasons (seed 20261019); the range component recomputed
  and its persistence must clear LB95 > 0. P-b: a synthetic target 0.25 z(predictor rank) +
  sqrt(1 - 0.0625) z(noise) (seed 20261020) must clear the (b) rule on the (b) rows. P-c: a synthetic
  target 0.5 z(grade rank) + 0.2 z(predictor rank) + noise scaled to unit variance must clear the
  (c) rule. A failed planted check makes its estimand UNDERPOWERED, not FAIL.
- **(a) PASS** if LB95(rho) > 0 and LB95(rho) > UB95(rho_null).
- **(b) PASS** if T1 or T2 clears LB95 > 0 with Holm at alpha 0.05 over {T1, T2} on the one-sided
  bootstrap p, N-b does not clear, P-b clears. Otherwise FAIL (or UNDERPOWERED, or VOID).
- **(c) PASS** if T1 or T2 partial clears LB95 > 0 with Holm over {T1, T2}, N-c does not clear,
  P-c clears.
- The read runs once. Before it, the whole reporting path is dry-run on fixtures carrying None
  values. Its stdout and stderr are kept. An exception after scoring began stops the read without a
  rerun.

## 6. What a pass licenses

- (b) PASS: serve MFR on PROSPX prospect pages (a defense block by position: runs per 1,000
  innings, a reliability band from the shrinkage, the levels it was measured at), a glossary entry,
  a registry row with verdict provisional. No accuracy claim beyond the cells of the eval artifact.
  Then the atlas-style eFV driver read by position group x level x age band, incremental over
  consensus FV, on development frames only, BH q, never by FV level; passing candidates go to
  EFV_X3 as candidates, nothing more.
- (b) FAIL, UNDERPOWERED or VOID: nothing is served; the eval artifact and registry row record the
  read; no MiLB fielding claim anywhere; the driver read is not run.
- (a) and (c) never serve on their own.

## 7. Never

No statistic by consensus-FV level or cell; no realized MLB statistic by consensus-FV cell; no R-LV
grade-point year or R-VM debut cohort; no betting column; no change to a served eFV, eWAR, SDR or
projection number by this gate.

## 8. Artifacts

`tools/milb_fielding_runs.py` (fetch, census, build, read, dry run); `.cache/milb_fielding/`
(reduced games, per-season tables); `data/milb_fielding_runs_census.json` (coverage);
`data/milb_fielding_runs_eval.json` (the read); a registry row `milb_fielding_runs`.

## 9. Order

1. This document, committed alone. 2. Fetch, coverage census committed with the tool and its tests
(fixture dry run). 3. The read, once, stdout and stderr kept; results in part 10; artifact and
registry row committed. 4. Serving and the driver read only under part 6.

## 10. Results

At registration (2026-10-16): nothing computed.

### Note N1 (2026-10-16): construction details fixed while writing the tool, before the census and before any estimand

Written after the registration commit (0ab2ed5f) and before the coverage census or any statistic of
parts 4 and 5. Each item fills a detail part 3 left open; none changes an estimand, a frame, a
comparator or a pass rule.

1. Sparse cells. A located cell with fewer than 30 balls in play falls back, in order, to (level,
   trajectory, angle bin, distance bin), (level, trajectory, angle bin), (level, trajectory), the
   first with 30 or more. The framing grid falls back from (level, count group, 2-inch x, 0.1 z) to
   (level, count group, 4-inch x, 0.2 z), then (level, 4-inch x, 0.2 z), then the level, the first
   with 20 or more taken pitches.
2. "1[k made the out]" counts outs only: on a hit or an error the fielder named by the first credit
   (`f_fielded_ball`, an error credit) is not credited with an out. A tool-building test on AAA 2026
   alone (the identity that a ball in play's runs over all positions sum to (out - p_c) x delta_c)
   caught the first draft crediting it; that test printed the part 3 shrinkage constants k for
   that one cell, a construction quantity, and no statistic of parts 4 and 5.
3. Split-half reliability is the Pearson correlation of the two halves' runs per inning.
4. Holders: a taken pitch's catcher is the holder of C at the start of the plate appearance; a
   steal's catcher is the holder at the steal's event; a play with no known holder at a position
   credits no player there (the runs stay out of every player's total).
5. Outfield arm: the kill rule's "any outfield assist on it" is any `f_assist_of` credit or any
   `f_assist` credit by an outfielder on the ball in play; a runner's end base is the end of his
   last movement on the play.
6. Pooled statistics are centred once on the full frame (within position, and within season for
   (a)); bootstrap draws are not re-centred.
7. Planted P-a uses the real run's k and level factors; the pitcher holds no planted skill; a
   planted out's initial fielder is drawn among positions with probability proportional to
   w_ck (p_c + s), floored at zero. N-b and N-c permute the predictor within the MLB primary
   position; P-c's noise is scaled so the synthetic target has unit variance.
8. The (b) predictor pools every MiLB level of seasons 2021 to D - 1; the read writes the (b) rows
   to `.cache/milb_fielding/tables/b_rows.parquet` (cache only) for the record.
