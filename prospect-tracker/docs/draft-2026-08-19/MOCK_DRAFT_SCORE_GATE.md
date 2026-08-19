# MOCK DRAFT SCORE GATE (2026-08-19)

First-ever accuracy score for the deterministic, board-anchored mock draft
(mock_draft.py) against the actual 2026 MLB draft. Clauses below were frozen
BEFORE the lab ran. Results section starts PENDING and is filled with verbatim
lab output only.

## 1. Archaeology (recon, pre-freeze)

- Actual results: YES. `prospects.db` table `draft_results` holds 613 rows for
  `draft_year = 2026`, source `mlb_stats_api` (rows re-inserted 2026-08-19 by
  the regular ingest). The draft ran 3 days mid-July (homepage fix cd4546ae,
  2026-07-11, "MLB Draft is 3 days"); results were ingested in commit
  689c10d0 dated 2026-07-15 ("2026 draft completed: results ingested").
- Pre-draft mock: YES, genuinely pre-draft. The mock's output artifact is
  `data/draft_timeseries.json` (attach_mock_draft bakes `mock_draft` onto the
  2026 class block). Its last archived pre-draft version is commit
  `725143899a5a80d4ffc0f590012c54e5aa7bee20` dated 2026-07-07 19:01:42 -0400
  ("Pre-launch final validation"). At that commit the 2026 class has
  `mock_draft.n_picks = 75` (rounds 1-2), `used_tendencies = true`, and the
  613-row `draft_order` has ZERO picks with a `player_key` or `signed` flag,
  i.e. no real result had landed. The next commit touching the file
  (13d77283, 2026-07-14) DELETED it from tracking (repo diet), so 72514389 is
  the terminal archive.
- Consensus baseline source: the SAME commit's 2026 class block carries 260
  prospects with `consensus_pick` set. Same vintage as the mock by
  construction.
- `draft_mocks` DB table: 0 rows (dead, see 6b9c3f90). Not usable.

## 2. Frozen inputs

- Mock: `git show 72514389:prospect-tracker/data/draft_timeseries.json`,
  2026 class, `mock_draft.picks` (75 rows: pick_overall, player_key,
  player_name).
- Actual: `prospects.db` `draft_results` WHERE draft_year = 2026 (613 rows);
  if a player_key appears twice, min(pick_overall) wins.
- Consensus board: same commit, 2026 class `prospects` with a non-null
  `consensus_pick`, sorted exactly as mock_draft.py sorts its board
  (consensus_pick asc, draft_stock_plus desc, consensus_fv_raw desc, name).

## 3. Frozen matching rule

1. Primary: `player_key` string equality.
2. Fallback for keys with no match: player_name equality after NFKD
   accent-strip, casefold, period-strip, whitespace-collapse.
3. Still unmatched = treated as undrafted: EXCLUDED from MAE and Spearman,
   COUNTED AS MISSES in the exact-pick clauses. Unmatched names are listed in
   the artifact.

## 3a. Amendment A1 (post-run-1, pre-run-2)

Run 1 left 7 mock players unmatched. A DB check on each name showed 2 of the
7 WERE drafted; the archived board spells the first name differently than
the MLB Stats API feed, so both frozen tiers missed them:

- Christopher Hacopian (board) = Chris Hacopian, actual pick 11
- Kaeden Waechter (board) = Kaden Waechter, actual pick 55

The other 5 (Braydon Wisener, James Clark, Archer Horn, Joseph Contreras,
Carson Bailey) have no 2026 draft_results row under any spelling; the Horn /
Contreras / Bailey surname hits are different players. Neither alias is in
consensus.py PLAYER_KEY_ALIASES.

Amendment: a two-entry KEY_ALIASES table in the scorer, applied identically
to mock and B1. Run 1 output is preserved below unaltered; run 2 (with A1)
is the scored result and feeds the artifact, which records the alias table
in provenance.

## 4. Frozen metrics

Slots = the 75 pick_overall values in the archived mock, ascending.

- M1 top-10 exact: #(picks 1..10 where mock player at that pick_overall ==
  actual player at that pick_overall) / 10.
- M2 top-30 exact: same over picks 1..30, / 30.
- M3 MAE: mean |mock pick_overall - actual pick_overall| over the matched
  intersection (mock players drafted anywhere in the 613).
- M4 Spearman rho of (mock pick_overall, actual pick_overall) on the same
  intersection (no ties possible; scipy p-value, t-approx fallback).

Baselines, identical metric code:

- B1 consensus board: board rank k (k = 1..75) assigned to slot k. Same
  matching rule, same four metrics.
- B2 random (analytic, no simulation): exact-pick expectation = 1/75 per pick
  for both M1 and M2; MAE expectation = mean over matched mock players of
  mean over all 75 slots of |slot - actual pick|; Spearman expectation = 0.

## 5. Frozen gate clauses

- C1 VALIDITY: at least 50 of the 75 mock players match an actual drafted
  player. FAIL = no artifact is written, section 6 records the failure.
- C2 SKILL VS RANDOM: mock M4 rho > 0 with p < 0.05, AND mock M2 > 1/75.
- C3 TENDENCY LAYER VS BOARD: informational, no ship bar. Report mock minus
  B1 on all four metrics; the registry note MUST state plainly whether the
  tendency layer beat, tied, or lost to the straight consensus board.

Artifact `data/mock_draft_eval.json` is written iff C1 passes, and carries:
generated_at, provenance (mock commit sha + date, results source), n counts,
all four metrics for mock / B1 / B2, unmatched names, clause verdicts.

## 6. RESULTS (verbatim lab output)

Lab: `tools/mock_draft_scorer.py`, run 2026-08-19.

### Run 1 (frozen rules exactly as written, no aliases)

```
== MOCK DRAFT SCORE 2026 ==
mock commit: 725143899a5a80d4ffc0f590012c54e5aa7bee20 (2026-07-07T19:01:42-04:00)
n_mock=75  matched=68 (key=68, name=0)  unmatched=7
unmatched (undrafted per frozen rule, misses for M1/M2): Christopher Hacopian, Braydon Wisener, James Clark, Kaeden Waechter, Archer Horn, Joseph Contreras, Carson Bailey
actual pool: 613 unique keys (draft_year=2026, source=mlb_stats_api)

METRIC                MOCK        B1_CONSENSUS  B2_RANDOM
M1 top-10 exact       0.4000      0.4000        0.0133
M2 top-30 exact       0.1667      0.1333        0.0133
M3 MAE (matched)      34.0147     34.0735       48.0506
M4 spearman rho       0.7389      0.7383        0.0000
M4 p-value            6.289e-13   6.748e-13     n/a
M4 n                  68          68            n/a

mock minus B1: M1 +0.0000  M2 +0.0333  M3 -0.0588 (negative = mock better)  M4 rho +0.0006

CLAUSE VERDICTS
C1 VALIDITY: PASS (68 matched, floor 50)
C2 SKILL VS RANDOM: PASS (rho=0.7389, p=6.289e-13, M2=0.1667 vs random 0.0133)
C3 TENDENCY LAYER VS BOARD: BEAT (wins 3, losses 0 of 4 metrics vs B1)
```

### Run 2 (Amendment A1 aliases, the scored result)

```
== MOCK DRAFT SCORE 2026 ==
mock commit: 725143899a5a80d4ffc0f590012c54e5aa7bee20 (2026-07-07T19:01:42-04:00)
n_mock=75  matched=70 (key=70, name=0)  unmatched=5
unmatched (undrafted per frozen rule, misses for M1/M2): Braydon Wisener, James Clark, Archer Horn, Joseph Contreras, Carson Bailey
actual pool: 613 unique keys (draft_year=2026, source=mlb_stats_api)

METRIC                MOCK        B1_CONSENSUS  B2_RANDOM
M1 top-10 exact       0.4000      0.4000        0.0133
M2 top-30 exact       0.1667      0.1333        0.0133
M3 MAE (matched)      33.2714     33.3000       47.4072
M4 spearman rho       0.7413      0.7407        0.0000
M4 p-value            2.166e-13   2.307e-13     n/a
M4 n                  70          70            n/a

mock minus B1: M1 +0.0000  M2 +0.0333  M3 -0.0286 (negative = mock better)  M4 rho +0.0006

CLAUSE VERDICTS
C1 VALIDITY: PASS (70 matched, floor 50)
C2 SKILL VS RANDOM: PASS (rho=0.7413, p=2.166e-13, M2=0.1667 vs random 0.0133)
C3 TENDENCY LAYER VS BOARD: BEAT (wins 3, losses 0 of 4 metrics vs B1)

artifact written: data\mock_draft_eval.json
```

## 7. Reading

- C1 PASS (70 of 75 matched), C2 PASS: the mock carries real ordering
  signal. rho = 0.7413 at p = 2.2e-13; top-30 exact 0.1667 vs a 0.0133
  random floor; MAE 33.3 picks vs a 47.4 random floor.
- Absolute level: 4 of the first 10 picks called exactly, 5 of 30 overall.
  A mocked player landed a mean 33.3 picks from his mocked slot. 5 mocked
  players were not drafted at all (scored as misses per the frozen rule).
- C3 BEAT, but barely: the tendency layer wins 3 of 4 metrics against the
  straight consensus board and ties the fourth, yet every margin is thin
  (top-30 +1 pick exact, MAE -0.03, rho +0.0006). Honest read: the tendency
  nudges did not hurt and added roughly one extra correct top-30 call; the
  board does nearly all the work, as designed (board is the anchor, window
  7, max tendency pull ~3.4 slots).
- Both runs agree on every clause verdict; Amendment A1 moved n from 68 to
  70 and no verdict.
- Conclusion for the registry: verdict provisional (first score, one draft
  class, n = 70). 2027 needs a pre-draft archive commit of
  data/draft_timeseries.json; this year's survived only by luck (the 07-14
  repo diet deleted the file from tracking one week after the last
  pre-draft archive).

