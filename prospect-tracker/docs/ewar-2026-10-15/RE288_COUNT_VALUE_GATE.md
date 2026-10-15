# RE288: the count-state run value table (count_value_v1)

Task EWAR_P1_RE288 (owner decisions EW3-16 to EW3-19, 2026-10-15; the ewar-map plan, task P1).
This document is committed ALONE, before any RE288 number is computed. It fixes the estimand, the
fit set, the shrink rule, the invariants and their tolerances, the receipts and every refusal. A
change to any of them after the first number is a dated amendment under part 11, never an edit.

## 0. What it is

- A measurement substrate: the mean runs scored from a pitch to the end of its half-inning, by the
  state before the pitch: balls (0 to 3), strikes (0 to 2), base occupancy (the 3-bit code of
  `ebr.base_code`, 0 to 7) and outs (0 to 2). 4 x 3 x 8 x 3 = 288 cells per season.
- Descriptive. It predicts nothing and carries no forward claim. Registry row `count_value`,
  verdict provisional, provisional_kind measurement_only.
- It is the run basis for later registered work (eABS challenge values, the pitch-economy
  decomposition, framing, swing decisions). None of those is computed here.
- Nothing served moves: no page reads the table. The artifact is `data/count_value.json`.

## 1. Source and the walk

- Pitches: `.cache/pbp_corpus/pitches/<Y>` (call_code in pitch_number order within at_bat_index).
- Non-pitch events: `.cache/pbp_corpus/events/<Y>` (index, type, description).
- Plays and the state inside a plate appearance: the runner record `.cache/pbp_runners/plays/<Y>`
  (the eBR record, EBR_GATE.md part 2.2: the one state walk, `states_json` per playIndex,
  `final_pitch_index`, the count before the final pitch, the end state, scheduled innings,
  runner_placed). The corpus `plays` table is read only for an agreement receipt.
- Seasons: 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026 (every season both stores hold).
- The playEvents index of each pitch: a play's events hold the indices of its non-pitch events;
  its pitches fill the remaining indices of 0 to (pitches + events - 1) in pitch_number order.
- The count walk, from 0-0 at play start, applied after each event at its index:
  - ball: B, *B, P (pitchout), I (intent ball), V (automatic ball); balls + 1.
  - strike: C, S, W, M, Q, T, O, L (foul tips and missed or foul bunts are strikes at any
    count); strikes + 1.
  - foul: F, R; strikes + 1 only below two strikes (a two-strike foul leaves the count).
  - terminal: X, D, E (ball in play), H (hit by pitch).
  - no_pitch events: a description starting "Automatic Ball" is a ball, "Automatic Strike" a
    strike (the pitch-clock and timeout violations, and the four automatic balls of an
    intentional walk); any other no_pitch (code N) leaves the count.
  - pickoff, stepoff and action events leave the count.
  - balls 4 or strikes 3 end the count (walk, strikeout). Any other code leaves the count and is
    counted in the receipts as unknown.
- The base-out state before an event at index i is the play's start state with every
  `states_json` group of index below i applied; a group at index i applies after the event at i.
  Once the count has ended, later states in the play are valued with the count ignored.

## 2. Observations and the fit set

- One observation per live pitch (a row of the pitches table) thrown with the count not ended and
  fewer than three outs: the state before the pitch and its runs to end of half,
  ros = (runs from the play's start to the end of its half-inning, the `ebr.runs_to_end` recipe on
  the record) minus (the runs of the play's `states_json` groups of index below the pitch's).
- Automatic balls and strikes and non-pitch events are not observations (no pitch is thrown);
  they move the count or the state that the next pitch is observed in. An intentional walk with
  no pitch adds no observation.
- Fit set: the play's own `ebr.fit_mask` (innings 1 to 8 and the top of the 9th, or 1 to 6 and the
  top of the 7th in a scheduled seven-inning game; half-innings that reached three outs; no
  half-inning with a runner_placed event). The same rule as eBR's RE24.

## 3. The estimand and the shrink (the eBR recipe, generalized to 288 cells)

```
raw_s(c)   = mean ros over fit-set observations of season s in cell c, with n_s(c) and var_s(c)
pool(c)    = the same over every season in P = {2018, 2019, 2021, ..., 2026}; refuse if a pool
             cell is empty
lambda_s   = sum_c n_s(c) raw_s(c) / sum_c n_s(c) pool(c)
K          = W / tau^2 by the method of moments of ebr.shrink_constant, over the cells present
             with n >= 2 in every season of P; clipped to [500, 5000]
RE288_s(c) = [ n_s(c) raw_s(c) + K lambda_s pool(c) ] / [ n_s(c) + K ]   (n 0 gives lambda pool)
```

- The pool, K and their inputs are computed ONCE on P and frozen with `count_value_v1`: the pool
  document's sha256 is pinned in `count_value.py` after its first computation, and a later build
  whose recomputed pool differs refuses. Adding a later season never moves a completed one.
- RE24_s is eBR's table exactly: `ebr.season_raw` on the record and `ebr.shrunk_table` with the
  frozen ebr_v1 pool (`.cache/ebr/frozen/ebr_v1_pool.json`, checked by `ebr.check_frozen_pool`).
- The 12-cell count marginal, per season and pooled: n, the raw mean of ros at the count, and
  rv_vs_00 = the occupancy-weighted mean of RE288_s(count, b, o) minus RE288_s(0-0, b, o), with
  weights the fit-set observation share of each base-out cell at that count. rv_vs_00(0-0) = 0.
- The called-pitch value, 12 cells, per season and pooled, the same weights: the value after a
  ball minus the value after a strike at that count. A ball at three balls is a walk (forced
  runners advance; a forced runner from third scores) valued at RE24_s of the new state plus the
  run; a strike at two strikes is a strikeout valued at RE24_s with one more out (0 at three).

## 4. The ledger convention and the per-event run value

- State value: a state whose count has ended, and a state at count 0-0, takes RE24_s(base, outs);
  any other state takes RE288_s; three outs take 0.
- The run value of an event (a pitch, an automatic call or a non-pitch runner event) is
  value(after) - value(before) + runs scored at its index.
- Over a plate appearance the values telescope to the play's RE24 change:
  runs_scored_on_play + RE24_s(end state) - RE24_s(start state).

## 5. Invariants (each refuses the whole build: nothing is written)

1. The 0-0 row equals RE24: for every season and each of the 24 base-out cells,
   |RE288_s(0-0, b, o) - RE24_s(b, o)| <= 0.03 runs, and the n-weighted mean absolute difference
   over the 24 cells <= 0.01 runs.
2. Monotone in the count at fixed base-out, in every season table and in the pool:
   RE288(B+1, S) >= RE288(B, S) for B 0 to 2, and RE288(B, S+1) <= RE288(B, S) for S 0 to 1. Any
   reversal refuses (ebr.py's monotone-or-refuse). Base-out monotonicity at a fixed count is
   reported, never refusing.
3. Per-event values sum to the play's RE24 change: |sum - change| <= 1e-6 on at least 99.9
   percent of fit-set plays in every season, the change computed from the record's own start
   state, end state and runs_scored_on_play.

## 6. Receipts (refusing where marked)

- R1 index (refusing below 0.999 per season): the reconstructed index of a play's last pitch
  equals the record's `final_pitch_index`.
- R2 count (refusing below 0.999 per season): the walked count before the final pitch equals the
  record's count before the final pitch (`fp_balls`, `fp_strikes`).
- R3 runs (refusing below 0.999 per season): the runs of a play's `states_json` groups sum to its
  runs_scored_on_play.
- R4 plays (reported): the corpus `plays` table and the record agree on the keys, the start state
  and runs.
- Reported per season: pitches, observations, fit-set observations, unknown call codes,
  automatic balls and strikes, intentional automatic balls, two-strike fouls, pickoff attempts,
  plays with no pitch, terminal kinds, invalid counts clamped.

## 7. Edge cases pinned by tests (test_count_value.py, on fixtures)

- a foul with two strikes leaves the count; a foul tip or a foul bunt with two strikes is a
  strikeout;
- pitch-clock automatic balls and strikes move the count without an observation, and an
  automatic strike three ends the plate appearance;
- an intentional walk of four automatic balls adds no observation and its values telescope;
- a pickoff attempt leaves the count; a pickoff out or a stolen base between pitches moves the
  state that the next pitch is observed in;
- terminal transitions (strike three, ball four, hit by pitch, ball in play) map to RE24 at the
  new base-out state, and a third out maps to 0;
- the per-event values of every fixture play sum to its RE24 change;
- the shrink, the monotone refusal and the 0-0 refusal fire on constructed tables.

## 8. Output, version, registry

- `data/count_value.json`: count_value_version, generated_at, the doc path, P, K and its inputs,
  the frozen pool digest, the RE24 basis digests, the pool table, and per season the 288 cells
  (value and n), lambda, its sha256, season_complete (November 1 rule), the 12-cell marginal, the
  called-pitch value and the receipts. Values in runs to four decimals.
- Built by `python tools/build_count_value.py`; pure core `count_value.py` (no network, no writes).
- Registry row `count_value`: provisional, measurement_only, eval_artifact data/count_value.json.
- A new version (pool, K rule, fit set, observation rule, tolerance) is a new frozen series with a
  new registration.

## 9. What it is not

- Not a skill estimate and not a WAR part. No player, team or umpire value is computed here.
- No year-to-year, split-half or forward statistic is computed. No FV-cell statistic, no betting
  column, no projections input.
- Not park-adjusted, not win expectancy.

## 10. Results

(Empty at registration. The build commit appends the receipts and the headline cells here.)

## 11. Amendments

### 11.1 2026-10-15: the estimator after the first build refused (the estimand is unchanged)

What was computed first. The build of parts 1 to 6 ran once (commit 737f3858's rules, the direct
estimator of part 3 on runs to the end of the half-inning) and REFUSED; nothing was written to
`data/`. Its log is kept in the lane's output directory and its pool document at
`.cache/count_value/refused/count_value_v1_pool_direct_refused_2026-10-15.json` (sha256
9ae6eee41103...). The numbers it showed, all disclosed here:

- K 500.0 (K_raw 487.7, clipped; W 1.607346, tau^2 0.00329576, all 288 cells used); season
  lambdas 0.9599 to 1.0558.
- Invariant 2 refused: the pool reversed 6 count steps, all in base-out cells 4|0, 4|1 and 7|0;
  each season reversed 9 to 14 steps, concentrated in the rare cells (runner on third, first and
  third, second and third, bases loaded).
- Invariant 1 refused in six seasons on the per-cell bound (max 0.0306 to 0.0628, at cells 4|0,
  5|0, 6|0 and 7|0); the weighted bound passed in every season (0.0011 to 0.0021).
- R1, R2, R3 and invariant 3 raised no refusal in any season.

Diagnosis. Runs to the end of the half-inning carry the variance of every later plate appearance
(W 1.61 runs squared within a cell). A rare base-out cell split twelve ways by count holds a few
hundred pitches a season, too few to order counts one step apart, and the low K that this noise
gives under the method of moments (500, against eBR's 1,654 on RE24) leaves the rare cells of the
0-0 row less shrunk than RE24's. The walk receipts did not fail; the estimator was too noisy.

The change (one change, registered before the second computation):

```
y_i        = (runs of the play from pitch i on) + RE24_s(the play's end state) - RE24_s(b_i, o_i)
             RE24_s(., 3) = 0; the end state is the record's (end_on_*, end_outs)
D_s(c)     = mean y over the season's fit-set observations in cell c, with n_s(c), var_s(c)
D_pool(c)  = the same over P
K'         = the method of moments of part 3 on D, with eBR's frozen season lambdas
             (the ebr_v1 pool document) as the run-level scale; clipped to [500, 5000]
D^_s(c)    = [ n_s(c) D_s(c) + K' lambda_s D_pool(c) ] / [ n_s(c) + K' ]
RE288_s(c) = RE24_s(b, o) + D^_s(c)
```

- Why the estimand does not move. RE24_s(state) is by definition the mean runs from a plate
  appearance that starts in that state to the end of the half-inning, so replacing the runs scored
  after the play by RE24_s of the play's end state leaves the expectation of runs to the end of the
  half-inning unchanged and removes the variance of the later plate appearances (a control
  variate; the usual construction of count run values).
- Unchanged: the walk, the observations, the fit set, P, the clip, the ledger, invariants 1 to 3 and
  their tolerances, and the receipts. Invariant 1 now checks that the season's own plays agree with
  its RE24 table at 0-0. The 12-cell marginal's re_mean stays the raw mean of runs to the end of the
  half-inning; rv_vs_00 and the called-pitch value read the amended table.
- The version stays count_value_v1: the refused computation was never pinned in code nor written
  to `data/`. The pool is written to `.cache/count_value/frozen/` only by a build that passes.
- This amended build runs once. If it refuses, nothing is written and the question goes to the
  owner.
