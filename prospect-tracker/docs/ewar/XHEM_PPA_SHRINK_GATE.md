# xHEM+ with a P/PA walk-shrink target: the forward test (xhem_ppa_shrink_v1)

Task XHEM_PPA_SHRINK_TEST (owner decision EW3-32, 2026-10-15, item 2, verbatim "Run it (owner
override)"). This document is committed ALONE, with its pin test
`test_xhem_ppa_shrink_registration.py`, before any number of its estimands is computed. It fixes
the data, the pair set, the variant's construction and frozen constants, the comparators, the
statistics, the pass rule and what a pass or a failure does. A change after the first number is a
dated note in part 9 that says what changed and why, never an edit above it.

STATUS: REGISTERED, RESULTS EMPTY.

## 0. Why this test exists, and the override it runs under

- **The registered trigger was missed.** `docs/ewar/PITCH_ECONOMY_LAB.md` part 8 registers this
  test only if item (h), the partial Spearman of P/PA(Y) with wOBA(Y+1) after BB%, K% and xwOBA(Y),
  has a pooled 95 percent interval that excludes 0. The lab's run (part 10 of that document,
  `data/_labs/pitch_economy_partials.json`) read +0.0563 with interval -0.0002 to +0.1161: a miss
  by 0.0002, applied as registered, and the lab's answer to the owner's question was no.
- **The owner overrode the miss** (EW3-32, 2026-10-15): "Run it (owner override)". This test runs
  under that override, and every record of it (this document's results, the artifact's
  `override` block, any registry row or owner question that follows) says so. The override waives
  the trigger only. Every rule below binds as written.
- **Scope: item (a) of the ewar-map plan's T6 only.** The starter test (b) was not triggered
  (items (s) and (r) of the lab were not near misses) and was not overridden, so it is not
  registered here.
- **Prior expectation:** a tie or a loss. HEM+ walks already shrink toward the league at K 120
  plate appearances and xwOBA carries the walks unshrunk; P/PA is mostly the walk rate (lab part
  A3: Spearman about 0.70 with BB%). The plan's stated ceiling is a tie under 0.005.

## 1. Data (read from caches; this task fetches nothing)

- **Savant expected statistics:** `.cache/savant_mlb/expected_batter_<Y>.csv`, columns `pa`,
  `woba` and `est_woba`, for Y in 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024 and 2025. The
  served xHEM+ source (`hitter_export._join_xhem_plus`).
- **StatsAPI season lines:** `.cache/fa_statsapi_hitting_<Y>.json`, one row per player-season (a
  traded player's row is his season total; a duplicate keeps the row with more PA), fields
  `numberOfPitches`, `plateAppearances`, `atBats`, `baseOnBalls`, `intentionalWalks`,
  `hitByPitch`, `sacFlies`, for Y in 2013, 2014 and 2015 (the slope fit, part 3) and 2016, 2017,
  2018, 2021, 2022, 2023 and 2024 (the predictor seasons).
- **League weights:** `league_constants.constants(Y)["woba_weights"]["ubb"]` for each predictor
  season; a season whose solved block is not its own refuses the run.
- **2026 never enters.** No 2026 file is opened. The 2025 Savant file is read for outcomes only.

## 2. The pair set

- **Pairs** (Y, Y+1) for Y in 2016, 2017, 2018, 2021, 2022, 2023, 2024 (2020 out on both sides;
  no 2025 to 2026 pair): Savant `pa` 200 or more in both seasons, the X-H3 floor.
- **Join:** the hitter's StatsAPI line in Y must exist with PA above 0, pitches above 0 and a wOBA
  denominator above 0. A pair without it is dropped from every arm and counted.
- **Complete outcome seasons only:** `plus_lab_harness.season_complete(Y+1)`; no season-complete
  override is set.
- **Outcome:** Savant `woba` in Y+1.

## 3. The variant's construction (frozen)

Per hitter-season in Y, from the StatsAPI line:

- uBB = BB - IBB; D = AB + BB - IBB + SF + HBP (the HEM+ wOBA denominator); r_raw = uBB / D.
- League values over every StatsAPI hitter row of Y with PA above 0 and pitches above 0:
  L_Y = (sum of pitches) / (sum of PA); lgBB_Y = (sum of uBB) / (sum of D).
- **Shrunk P/PA:** sPPA = (pitches + K_PPA * L_Y) / (PA + K_PPA), K_PPA = 100 (the lab's part 4
  prior P/PA shrink).
- **The walk target:** T = lgBB_Y + b * (sPPA - L_Y), floored at 0.
- **The shrunk walk rate:** r_shr = (uBB + K_UBB * T) / (D + K_UBB), K_UBB = 120
  (`hem_plus.K_UBB`, the frozen HEM+ unintentional-walk constant).
- **The variant's xwOBA:** xw' = est_woba + w_ubb,Y * (r_shr - r_raw). Savant's xwOBA counts each
  walk at its full weight, so this replaces the hitter's raw walk rate with the shrunk one and
  leaves the contact and strikeout parts as Savant has them.
- **The variant's xHEM+:** 100 + G * (100 * xw' / pool'_Y - 100), G = `hem_plus.HEM_SPREAD_GAIN`
  (2.28), pool'_Y the Savant-PA-weighted mean of xw' over the season's served pool (Savant `pa`
  100 or more and `est_woba` above 0, the `_XHEM_MIN_PA` floor). A served-pool hitter without a
  valid StatsAPI line keeps xw' = est_woba and is counted. Unrounded.
- **The slope b** is fitted once, inside the run and before any pair is formed, on the 2013, 2014
  and 2015 StatsAPI seasons only (no Savant, no pair season, no outcome): hitter-seasons with PA
  300 or more, position players only (position abbreviation not P); x = pitches / PA, y = r_raw;
  b = the pooled within-season least-squares slope, sum over seasons of sum((x - xbar_s)(y -
  ybar_s)) divided by sum over seasons of sum((x - xbar_s)^2). It is printed and written with its
  n before the first pair, and the run refuses if b is not finite or n is under 300.

## 4. The arms

- **N, the NULL comparator: the unmodified xHEM+.** 100 + G * (100 * est_woba / pool_Y - 100),
  pool_Y the Savant-PA-weighted mean est_woba over the same served pool, unrounded (the served
  `xhem_plus` before its integer rounding). HEM+ is deprecated (2026-10-15) and is not a baseline.
- **V, the variant:** part 3.
- **P, the permuted-P/PA twin:** part 3 with sPPA permuted within each predictor season across the
  season's served-pool hitters that have a valid StatsAPI line (one permutation per season,
  hitters ordered by MLBAM id, `random.Random(20261018)` shuffling season by season in ascending
  order). Everything else is V's.
- **M, reported only:** part 3 with b = 0 (the walk rate shrunk toward the league at K_UBB, no
  P/PA). It separates the shrink from P/PA. It carries no verdict and is not in the family.

## 5. Statistics (harness v2, `tools/plus_lab_harness.py`)

- **Rho:** Spearman of the arm's xHEM+(Y) with the outcome over the pair set.
- **v1:** the raw pooled wOBA(Y+1) target; iid paired bootstrap (`plus_lab_harness.iid_boot_gaps`
  draw construction), B = 2,000, seed 20261015.
- **v2:** wOBA(Y+1) z-scored within the outcome season; player-clustered, season-stratified
  bootstrap (`plus_lab_harness.cluster_boot_gaps` draw construction), B = 2,000, seed 20261015.
- **Gaps:** V minus N, P minus N and M minus N, the same draws for all three within a convention;
  percentile 95 percent interval (`plus_lab_harness.ci`).
- **MDE95:** 1.645 times the bootstrap sd of the gap, derived in the run for every gap and
  convention (`docs/EFV_GATE_STANDARD.md`), never a stored constant.
- **Holm:** the family is the one test registered here, V against N (k = 1), so Holm leaves the 95
  percent interval as it is. P and M are controls, not family members. Each gap also prints the
  share of its draws at or below 0.
- Per-predictor-season rhos of N, V, P and M are printed beside the pooled numbers.

## 6. The pass rule

- **VALIDATED** when all of: (1) V minus N has lo95 above 0 under v1; (2) V minus N has lo95 above
  0 under v2; (3) the twin fails: P minus N has lo95 at or below 0 under v1 and under v2.
- **VOID** when (1) and (2) hold and (3) does not: a permuted P/PA passing means the gain is not
  P/PA's, and nothing is built.
- **PROVISIONAL** when exactly one of (1) and (2) holds and (3) holds. Nothing is built.
- **NOT VALIDATED** otherwise. A null is a complete result.
- **If VALIDATED:** the variant is built dark (a module flag that defaults off; while off, nothing
  served moves and no exporter writes a served file), a registry row records the result and the
  override, and `OWNER_QUESTION.md` asks the owner whether to flip it. The flip is the owner's.
- **Otherwise:** P/PA stays a context column, nothing is built, and the owner's question (EW3-16,
  P/PA into HEM+ or xHEM+) is answered no on this test as well as on the lab.

## 7. The run

- **Tool:** `tools/xhem_ppa_shrink_lab.py`. `--dry-run --out PATH` runs the whole reporting path on
  a synthetic fixture with nulls (missing StatsAPI lines, zero pitches, a hitter in one season
  only) and a planted-recovery fixture (an outcome that carries the P/PA-implied walk signal, where
  V must beat N, and a null fixture, where it need not), writing only to PATH. `--run` is the one
  run; it writes `data/_labs/xhem_ppa_shrink_eval.json` (`data/_labs/` ships in neither deploy
  consumer) and nothing else under `data/`.
- **Order:** this document and its pin test are committed alone; then the tool and its tests; the
  dry run; then the run, once, with stdout and stderr teed to the task's output directory before
  anything else runs. An exception after scoring began stops the task without a rerun.
- **Recorded:** part 9 of this document, with the override disclosed, and a dated note in part 10
  of `docs/ewar/PITCH_ECONOMY_LAB.md`.

## 8. What it never does

- It reads no consensus FV, prospect list or FV cell (`docs/PROSPECT_ANCHOR_GATE.md`), no betting
  artifact, dark column, price, market capture or game result, and no 2026 row.
- It retrains no projection, refits no HEM+, xHEM+ or fwdHEM+ constant, and moves no served number.
- It runs once. A defect found after the run is stated in a dated note in part 9, and the corrected
  run is written beside the first.

## 9. Results

### 2026-10-15: the run (`python -u tools/xhem_ppa_shrink_lab.py --run`, at 6cd7ea56)

**Run under the owner's override.** This test was registered and run only because the owner
overrode the pitch-economy trigger miss (EW3-32 item 2, "Run it (owner override)"; item (h) read
+0.0563 with its lower bound 0.0002 below 0). The artifact carries the override in its `override`
block. Run once, stdout and stderr teed before anything else ran; the dry run on fixtures (nulls,
planted, null) ran first and recovered the planted signal under both conventions.

**Inputs.** The slope b, fitted on 2013 to 2015 StatsAPI lines only, is 0.08390 walks per wOBA
plate appearance per pitch per plate appearance (807 hitter-seasons; 0.0808, 0.0834 and 0.0878 by
season). 1,871 pairs, 649 hitters, 261 to 278 pairs per predictor season; no pair dropped for a
missing StatsAPI line or a partial outcome season; every served-pool hitter (435 to 469 a season)
joined. League P/PA 3.878 to 3.904, league unintentional-walk rate 0.0775 to 0.0838. The variant
moves xHEM+ by 2.4 points (sd) and at most 13.4 points; its rank agreement with the unmodified
xHEM+ is 0.9951. The harness reproduction held: the V minus N intervals match
`plus_lab_harness` exactly.

| Convention | Arm minus N | Rho arm | Rho N | Gap | 95 percent interval | MDE95 | Share of draws at or below 0 |
|---|---|---|---|---|---|---|---|
| v1 | V, the variant | 0.4592 | 0.4617 | -0.0025 | -0.0067 to +0.0018 | 0.0036 | 0.8745 |
| v1 | P, the permuted twin | 0.4549 | 0.4617 | -0.0068 | -0.0133 to -0.0001 | 0.0055 | 0.9760 |
| v1 | M, b = 0 (reported only) | 0.4546 | 0.4617 | -0.0071 | -0.0130 to -0.0014 | 0.0050 | 0.9910 |
| v2 | V, the variant | 0.4693 | 0.4708 | -0.0015 | -0.0063 to +0.0030 | 0.0038 | 0.7390 |
| v2 | P, the permuted twin | 0.4649 | 0.4708 | -0.0059 | -0.0130 to +0.0010 | 0.0058 | 0.9495 |
| v2 | M, b = 0 (reported only) | 0.4645 | 0.4708 | -0.0063 | -0.0126 to -0.0002 | 0.0053 | 0.9775 |

By predictor season (rho with wOBA(Y+1), N then V): 2016 0.3657, 0.3649; 2017 0.5014, 0.5057;
2018 0.4885, 0.4885; 2021 0.4764, 0.4799; 2022 0.5064, 0.5004; 2023 0.5027, 0.5010; 2024 0.4485,
0.4420. The variant is ahead in two seasons, level in one and behind in four.

**Verdict: NOT VALIDATED.** The variant does not beat the unmodified xHEM+ under either convention
(lower bounds -0.0067 under v1 and -0.0063 under v2; the point is below 0 under both). The twin
fails as required (no lower bound above 0), so the test is not void; it is a plain null. The
intervals put any gain under +0.0018 (v1) and +0.0030 (v2), inside the plan's expected "tie under
0.005", with MDE95 0.0036 and 0.0038, and the point estimate is a small loss. Reported only, not gated: shrinking the walk rate toward the league (M) loses about
0.007 to the raw walk rate, and the P/PA target recovers most of that loss without overtaking the
raw rate. On this pair set, Savant xwOBA's unshrunk walks are the better forward input.

**Consequence.** Nothing is built and no flag exists. P/PA stays a context column. The owner's
question (EW3-16, P/PA into HEM+ or xHEM+) is answered no on this test as well as on the
pitch-economy lab. No registry row, glossary entry or served number moves; the artifact
`data/_labs/xhem_ppa_shrink_eval.json` ships in neither deploy consumer.
