# Swing-decision value: the measure and its two tests (swing_decision_v1)

Task EWAR_INNOVATE_LEDGER, item (b) (owner decisions EW3-16 to EW3-23, 2026-10-15; the ewar-map
plan's innovator item 2, "the right version of seeing extra pitches"). This document is committed
ALONE, with its pin test `test_ewar_innovate_registration.py`, before the measure's code exists
and before any number of its estimands is computed. A change after the first number is a dated
note in part 8 that says what changed and why, never an edit above it.

STATUS: REGISTERED; TEST X READ 2026-10-16 (NOT VALIDATED); TEST E WAITS FOR DATA (part 8).

## 0. What it is and what it is for

- **The measure.** For every pitch a batter decides on, the run value of the decision he made
  minus the run value of the one he did not make, each valued at what the league gets from that
  decision on that pitch (its location, the count, the pitch type, the base-out state). It credits
  the choice, never the contact: a hitter who swings at a hittable pitch is credited with the
  league's value of swinging there, whatever he then did with it. Per batter-season: runs per 100
  decisions, centred on the season's league mean.
- **Why not pitches seen.** P/PA mixes patience with whiff and foul behaviour and largely restates
  the walk and strikeout rates wOBA already prices (`data/_labs/efv_pitch_rate_features.json`:
  relative P/PA against the relative walk rate 0.624). The xHEM+ P/PA walk-shrink test read NOT
  VALIDATED (`docs/ewar/XHEM_PPA_SHRINK_GATE.md`, 2026-10-15). Decision value measures the skill
  P/PA only proxies.
- **Two tests, each registered here:** X, the measure as a shrink input to xHEM+ (part 4); E, the
  measure as an eFV feature at AAA under the atlas rules (part 5). Neither moves a served number.
  A pass of X on the development frame makes swing-decision value a candidate batting arm for the
  eWAR v3 skill look, entered by a dated amendment to `docs/ebr-2026-09-30/EBR_GATE.md` part 11,
  committed alone before that look (part 6).
- **Development frames for selection.** The eWAR v3 skill look's frame (predictor seasons 2021 to
  2024) and its holdout (2025 to 2026) are never read by test X. Test X reads the one corpus pair
  outside them, 2018 to 2019. Its power is low (part 4.5), stated before any number.

## 1. Data (read from caches)

- **The corpus pitches and plays** (`.cache/pbp_corpus`, 2018, 2019; 2021 to 2026 for the
  descriptive census of part 3 only): call code, pitch type, plate_x, plate_z, sz_top, sz_bot,
  batter side, pitcher hand, base-out state, bunt flag.
- **The pitch-level ledger** (`docs/ewar/PITCH_LEDGER_GATE.md`): the league called-strike model
  p0 (its part 4.1), the step values dRE and the batted-ball expectation x_x (its part 5.1), by
  reference. RE288 and RE24 from `data/count_value.json`.
- **Savant expected statistics** `.cache/savant_mlb/expected_batter_<Y>.csv` (`pa`, `woba`,
  `est_woba`), 2018 and 2019, the served xHEM+ source (`hitter_export._join_xhem_plus`).
- **StatsAPI season lines** `.cache/fa_statsapi_hitting_<Y>.json`, 2018: AB, BB, IBB, HBP, SF, PA.
- **League weights** `league_constants.constants(2018)["woba_weights"]["ubb"]`.

## 2. The measure

**2.1 Decisions.** A pitch with a decision is one thrown with the count not ended and fewer than
three outs, whose call code is a take (`B`, `*B`, `C`) or a swing (`S`, `W`, `F`, `T`, `X`, `D`,
`E`), and that is not a bunt (codes `L`, `M` and in-play plays the corpus marks bunted are out).
Hit batters, pitchouts, intentional balls, automatic calls and pitches without location are out.

**2.2 The value of taking:** VT = p0 * V(strike) + (1 - p0) * V(ball) at the pre-pitch state,
p0 the ledger's league called-strike probability for that pitch, V the state value after the call
(`count_value.state_value`; ball four a forced walk on RE24, strike three a strikeout on RE24).
VT - V(before) is the expected value of a take.

**2.3 The value of swinging:** VS - V(before) = the season's league mean of (V(after) -
V(before)) over swings in the pitch's cell, with a ball in play valued at the ledger's x_x (its
expected value given the contact) rather than its result. Cell: xm (plate_x mirrored for a
left-handed batter) in 0.25 ft bins over -2.0 to 2.0, zn in 0.15 bins over -1.0 to 2.0 (edges
clipped), the count (12), the pitch group (FB, BR, OS, other, as the ledger's part 5.2). A cell's
mean is shrunk toward its parent (the same location and pitch group, strikes 0, 1 or 2) with
weight n / (n + 25), and the parent toward the location cell alone with weight n / (n + 25).

**2.4 Per pitch:** DV = (VT - VS) if the batter took, (VS - VT) if he swung. **Per batter-season:**
SD = sum over his decisions of (DV - DVbar_s), DVbar_s the season's league mean DV; SD100 = 100 *
SD / decisions. Pitcher-batters are out. **Shrunk:** SD~ = SD / (decisions + K_SD), the
per-decision rate shrunk toward 0, with K_SD fitted once (part 2.5).

**2.5 The frozen constant K_SD.** On 2018 only: split-half reliability of SD100 over alternate
plate appearances within the season (odd and even at-bat order per batter), batters with 1,000
or more decisions, Spearman-Brown corrected, r_sh; K_SD = d_med * (1 - r_sh) / r_sh, d_med the
median decisions of those batters. r_sh at or below 0 sets K_SD to infinity (SD~ = 0), never
re-chosen. Frozen in `swing_decision.py` before test X reads any outcome.

## 3. Descriptive census (same season only; no verdict)

Per season 2018, 2019, 2021 to 2026: league DVbar, the sd of SD100 at 1,000 or more decisions,
the share of decisions that are takes, the top and bottom ten batters by SD100 (written only to
the gitignored cache), Spearman of SD100 with BB%, K%, chase rate (swings outside the rulebook
zone over pitches outside it) and P/PA, same season. No year-to-year or forward statistic of SD
is computed outside test X.

## 4. Test X: swing-decision value as an xHEM+ shrink input (deciding for the candidate)

**4.1 Pairs.** (2018, 2019): Savant `pa` 200 or more in both seasons, a StatsAPI 2018 line with
PA above 0 and a wOBA denominator above 0, and 2018 corpus decisions. Outcome: Savant `woba` 2019.

**4.2 Arms.**

- **N, the null comparator: the unmodified xHEM+.** 100 + G * (100 * est_woba / pool - 100), G =
  `hem_plus.HEM_SPREAD_GAIN`, pool the Savant-PA-weighted mean est_woba over the served pool
  (Savant `pa` 100 or more, est_woba above 0), unrounded.
- **V, the variant: the walk rate shrunk toward a decision-implied target.** uBB = BB - IBB; D =
  AB + BB - IBB + SF + HBP; r_raw = uBB / D; lgBB = sum uBB / sum D over every 2018 StatsAPI hitter row with PA above 0;
  T = lgBB + b * SD~ (floored at 0); r_shr
  = (uBB + 120 * T) / (D + 120) (K_UBB 120, `hem_plus.K_UBB`); xw' = est_woba + w_ubb * (r_shr -
  r_raw); V = 100 + G * (100 * xw' / pool' - 100), pool' the same pool's mean xw'. b is the
  least-squares slope of r_raw on SD~ over 2018 hitters with 300 or more PA (same
  season, no outcome), fitted once before any pair is formed, printed with its n; it refuses if
  b is not finite or n is under 200.
- **P, the permuted twin:** V with SD~ permuted across the 2018 served-pool hitters ordered by
  MLBAM id, `random.Random(20261016)`.
- **M, reported only:** V with b = 0 (the walk shrink without the measure).

**4.3 Statistics.** Spearman of each arm with the outcome; gaps V - N, P - N, M - N on the same
draws; v1: iid pair bootstrap; v2: outcome z-scored within the season (one outcome season, so the
same ranks) and the player-clustered bootstrap (one pair per player, so the same draws as v1);
both are printed. B = 2,000, seed 20261016, percentile intervals, MDE95 = 1.645 times the
bootstrap sd of the gap, printed before any gap. Holm family: V against N alone (k = 1).

**4.4 Pass rule (DEV PASS):** V - N has lo95 above 0, and the twin fails (P - N lo95 at or below
0). VOID when V passes and the twin passes too. Otherwise NOT VALIDATED, a complete result. A
planted fixture (part 7) must read DEV PASS and the all-zero measure must not, before the run.

**4.5 Power, stated before the look.** About 250 to 330 pairs; at that n a Spearman gap of +0.01
between two arms correlated above 0.95 is unlikely to clear its interval. The registered
expectation is NOT VALIDATED (the P/PA walk-shrink read -0.0025 on seven pairs of seasons), and
a null here says the development frame could not see a gain, not that none exists.

**4.6 What a DEV PASS licenses:** a dated amendment to `docs/ebr-2026-09-30/EBR_GATE.md` part 11,
committed alone before the skill look, registering candidate part 4's arm "xHEM+ with the
decision walk target" (S1x with xw' of part 4.2 in place of xwOBA~, b and K_SD frozen), its own
Holm family {rate, total} k = 2 on 11.2.1's batting target, the twin, B1, the team guard and the
secondary estimand, entering only if it qualifies and its rate gap over the xHEM+ arm's has lo95
above 0 on the same pairs. Nothing else. NOT VALIDATED or VOID registers nothing.

## 5. Test E: swing-decision value as an eFV feature at AAA (the atlas rules)

- **Rows and labels:** `efv5_atlas.py`'s rows, groups and labels as that module defines them
  (every MiLB level-season line at QUAL for a player with no MLB line at or before S; reach3,
  reach5, w3 and l6; never a cell by FV level), restricted to AAA, with SD100 of the AAA season as
  the metric; incremental score only (the lift over consensus FV out of fold, Benjamini-Hochberg
  q within the family). The atlas's own pass bar applies unchanged.
- **The AAA decision record:** AAA pitch-level location, count and call for season S, read from
  cached MiLB game feeds (sport id 11). On disk at this commit: 2026 only. AAA 2023 to 2025 are
  fetchable (StatsAPI MiLB live feeds, polite, into `.cache/ewar_innovate_ledger/aaa_feeds/`).
- **Runs only when at least two AAA seasons have a resolved label.** reach3 for S resolves when S
  + 3 is at most the last complete season: S = 2023 resolves now and S = 2024 after the 2027
  season. Until then test E does not run, and the record says it waits for data that does not
  exist yet. The RE288 table used at AAA is the MLB table of the same season, disclosed.

## 6. What is never done

- No served number, page, registry row or glossary entry reads the measure under this document.
- No year-to-year, split-half or forward statistic of SD on any pair with a predictor season 2021
  to 2025 (the skill look's frame and holdout), except inside the skill look itself after an
  amendment.
- SD is never summed with batting runs into a WAR here; it enters eWAR v3, if ever, only as the
  registered arm of part 4.6 through the skill look.

## 7. Tool and tests

`swing_decision.py` (pure), `tools/swing_decision_lab.py` (with `--dry-run` on a synthetic
fixture with nulls; stdout and stderr teed to the output directory before the run),
`test_swing_decision.py`. The fixture's planted measure (the outcome built from a known share of
SD) must read DEV PASS; an all-zero measure must not; its twin must fail. Output:
`data/_labs/ewar_innovate/swing_decision_eval.json` (tracked, never shipped), per-batter values
only in `.cache/ewar_innovate_ledger/swing_decision/`.

## 8. Results and dated notes

### 8.1 2026-10-16: the swing value at the pitch's own base-out state, fixed before any number

- **Defect.** Part 0 values each decision at the pitch's location, count, pitch type and base-out
  state; part 2.3's cell mean of (V(after) - V(before)) pools base-out states, while part 2.2's
  take value is state-specific. Comparing the two would credit a decision with the state mix of
  the cell. No number of the measure existed when this note was written.
- **Fix.** The cell of part 2.3 (location, count, pitch group, with the registered shrink toward
  its parents) carries outcome shares instead of a run mean: P_w (swinging strike or foul tip),
  P_f (foul) and P_ip (in play), and r_loc, the cell's mean of (x_x - m_bo) over its balls in
  play (m_bo the ledger's season mean of in-play dRE from the state, its part 5.1). Then VS -
  V(before) = P_w (V(strike) - V(before)) + P_f (V(foul) - V(before)) + P_ip (m_bo(state) +
  r_loc), with V(foul) = V(strike) below two strikes and V(before) at two strikes, every V at the
  pitch's own state. Part 2.2 is unchanged. Nothing else changes.

### 8.2 2026-10-16: K_SD, the census and test X (tools/swing_decision_lab.py)

- **K_SD (part 2.5), fitted once on 2018:** 307 batters with 1,000 or more decisions, half r
  0.7236, Spearman-Brown 0.8396, median 1,869 decisions, K_SD 357.03 (frozen in
  `swing_decision.py`; log `data/_labs/ewar_innovate/swing_decision_k_fit.json`). The league
  mean decision value DVbar is 0.050 runs per decision in 2018.
- **Census (part 3, same season, no verdict):** about 0.68 to 0.71 million decisions a season;
  sd of SD100 among batters with 1,000 or more decisions 0.78 to 0.94 runs per 100 decisions (14.4
  to 17.5 runs a season). Spearman of SD100 with, same season: walk rate 0.65 to 0.76, chase rate
  -0.75 to -0.80, strikeout rate 0.08 to 0.17, P/PA 0.51 to 0.58. The measure is mostly plate
  discipline, as the walk-rate and chase-rate correlations show.
- **Test X (part 4), once, 2018 to 2019:** b = 3.1415 on 278 hitters (2018, same season); 262
  pairs; MDE95 of V - N 0.0104. Spearman with 2019 wOBA: N 0.4885, V 0.4880, P 0.4825, M 0.4845.
  V - N -0.0005 (95 percent -0.0131 to +0.0113); twin P - N -0.0061 (-0.0240 to +0.0112); M - N
  -0.0040 (-0.0194 to +0.0106). v2 equals v1 here (one outcome season, one pair per player).
  **NOT VALIDATED**, as registered expected (part 4.5): a complete result. Nothing is registered
  for the skill look under part 4.6.
- **Test E (part 5): not run.** AAA pitch-level location and count records exist on disk for 2026
  only, and only one AAA season (S = 2023) could have a resolved reach3 label even after fetching
  2023 to 2025. The second resolved season (S = 2024) exists after the 2027 season. The test waits
  for that data.
