# College pitcher K% challenger gate (registered 2026-10-01, NOT SCORED)

Status: **registered, not scored.** Registry row `college_pitk_box_challenger`
(verdict `provisional`, provisional_kind `data_blocked_stub`). Scorer
`tools/college_pitk_challenger_lab.py`. Frozen pair list
`docs/college-pitk-challenger-2026-10-01/frozen_pairs.json`.

This file was committed before any fit, look or input fetch for the
challenger. Nothing in it was chosen after seeing a challenger number, because
no challenger number exists: the input is not in the database on the
registration date (`collegesavant_box_scores` holds 1 row, side batting, season
2026; no NCAA pitching line for any CollegeSavant pitcher).

## 1. Why

Owner answer M19-1 (2026-09-25, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
'more' batch 19): keep the no-skill legs flagged and muted, and pre-register a
pitcher K% challenger built on full-season NCAA box K% (census M03-05 and
M03-19).

The incumbent leg `pit_k` in `college_translation.py` maps a pitcher's tracked
college K% (CollegeSavant TrackMan, 2024 and 2025 rows) to Single-A K%. On its
own eval (`data/college_translation_eval.json`, factors.pit_k) it does not beat
predicting the Single-A mean: leave-one-out MAE 4.013 against 3.995 for the
mean, skill -0.018 (se 0.053), r2 0.033, n 232. The served leg is flagged
"low signal" and its cells are muted. The tracked K% in the 2024 national file
covers whatever share of each pitcher's season TrackMan saw; a full-season box
K% is the natural alternative input.

## 2. The pairs (frozen)

`frozen_pairs.json` lists the 232 incumbent `pit_k` pairs as
`college_translation.build()` constructs them on 2026-10-01:
`load_cs_pitchers()` (2024/2025 tracked rows carrying k_pct, the highest-pitch
row per name) joined by `norm_name` to `load_single_a()` pitchers (earliest A
or A+ season with at least 20 IP and a K%). By tracked season: 2024 224,
2025 8. The file stores identities only (name key, CollegeSavant name, pitcher
id, tracked year, team code, Single-A season); it stores no college or
Single-A rate.

A pair drops out of scoring if, on the look date, its tracked row or its
Single-A season no longer matches the frozen identity (counted as
`pair_drifted`). No pair is added after today.

## 3. The challenger input

For each frozen pair, the NCAA D-I pitching box line of the SAME season as the
tracked row, read from `collegesavant_box_scores` (side `pitching`, season =
tracked year, player_slug = `slugify_cs(cs_name)`), written by
`college_stats.refresh_collegesavant_stats`.

    box K% = 100 * SO / (outs + H + BB),   outs = round(3 * IP)

The NCAA payload carries SO, BB, H and IP but no batters-faced column, so the
denominator is this estimate (it omits HBP, errors and sacrifices). A line
under 20 NCAA innings, or missing SO, H, BB or IP, gives no input.

The scored subset **S** is every frozen pair with a box K%.

## 4. Models compared, on S only

All three are scored by the production leave-one-out protocol: for each pair,
fit on the other pairs in S, predict it, keep the absolute error.

1. **Challenger**: `college_translation._fit` (the shipped shrunk-slope
   regression to the Single-A mean, SLOPE_SHRINK_K unchanged) with x = box K%.
2. **Incumbent (production leg)**: the same `_fit` with x = tracked K%, refit on
   S, so both legs see identical pairs.
3. **Null**: the Single-A mean of the other pairs in S (the registry baseline of
   `college_translation`).

## 5. Metric

- MAE of each over S.
- Per-pair gains: null error minus challenger error, and incumbent error minus
  challenger error.
- Paired bootstrap over pairs: 2000 draws, seed 20261102, 95% percentile
  interval (2.5th, 97.5th) of the mean gain, one interval per comparison.
- Permutation band: the box K% column shuffled across S 200 times (same
  seed stream), each scored by the same protocol against the null; the 95th
  percentile of those skills is the band.

## 6. Pass rule (all four, stated before any number exists)

- **P0 coverage**: |S| >= 60. Otherwise the verdict is COVERAGE-STARVED and no
  skill clause is read.
- **P1**: challenger MAE below the null's, and the lower end of the 95%
  interval of the gain vs the null above 0.
- **P2**: challenger MAE below the incumbent's, and the lower end of the 95%
  interval of the gain vs the incumbent above 0.
- **P3**: the challenger's skill vs the null above the permutation band's 95th
  percentile.

PASS makes the challenger eligible; serving it is a separate owner-signed task
and nothing changes on the site from this gate alone. FAIL keeps the incumbent
flagged and muted, and the registry row goes to `deprecated`.

## 7. The one look

**Date: 2026-11-02.** One run of `python tools/college_pitk_challenger_lab.py`
on that date, which writes `docs/college-pitk-challenger-2026-10-01/result.json`
and nothing under `data/`; the registry row is then updated from the result.
The scorer refuses on any other date and refuses a second run.

Preconditions, both required before the look date and never on a registered
look date of another gate:

1. The NCAA pitching box lines for seasons 2024 and 2025 are fetched for the
   CollegeSavant pitchers (`college_stats.refresh_collegesavant_stats`,
   pitching side only, no team cap), writing `prospects.db` only. The fetch
   must not write batting rows, which feed the served hitter box panel.
2. The fetch is recorded (commit message or run log) with its row counts.

If a precondition fails, the look still happens on 2026-11-02 and records
NOT SCORED or COVERAGE-STARVED; a later date needs a new registration committed
before any look.

## 8. Earlier measurements on these pairs (disclosed)

Every measurement found that a lane already took on the pitcher pairs.
None used an NCAA box rate as the input: a search of `tools/` and the final-pass
lanes for a join of the Single-A pitcher pairs to an NCAA pitching line found
none, and the input does not exist in the database.

- `data/college_translation_eval.json` (production build): pit_k LOO MAE 4.013
  vs 3.995 for the mean, skill -0.018, se 0.053, r2 0.033, n 232.
- Final-pass census M03-05 and its verifier (2026-09-24,
  `_finalpass_2026-09-24/finalpass/M03_amateur_college/probe_translation_null.py`,
  `verify_M03-05/probe_m03_05.py`): the same skill, bootstrap interval -0.125 to
  0.085, Spearman 0.139 between tracked K% and Single-A K%, n 232; pair years
  2024 224, 2025 8.
- Census M03-04 verifier probes (`M03_amateur_college/verify/verify_m03_04*.py`,
  `verify_M03-04/probe_null.py`): the incumbent pit_k LOO against the mean, the
  same numbers.
- Census M03-13 judge probes (`judge_M03-13/probe_receipts.py`,
  `probe_residuals.py`): pair counts and residuals of the incumbent legs against
  career-stat labels.
- W4 COL-XRV (2026-07-23, `docs/wills-2026-07-23/GATES.md`, registry row
  `college_stuff_translation`, deprecated): college Stuff+ as a second covariate
  on 257 pairs then; Stuff+ vs first-pro K% r -0.005, same-season tracked K%
  r 0.232; LOO MAE 4.392 to 4.416, lo95 -0.056.
- `tools/milb_park_factors.py` counts the matched pitcher pairs (no rate).

Context on different pairs, not these: the hitter box K% leg `box_k`
(draft-prospect NCAA box K% to Single-A K%, n 86) reads skill +0.909 on the
same eval. That reading motivated the owner's choice and is why the challenger
is worth one look; it is not evidence about pitchers.

## 9. What this gate does not do

It does not refit, reweight or re-flag the served `pit_k` leg, change
`LOW_SIGNAL_R2`, or move any served number. It does not fetch anything today.

## 10. Amendment 2026-10-08: re-registered on the held NCAA K/9 lines

Appended on 2026-10-08, before any look, fit or rate read for the challenger.
Nothing above this heading was edited; no results section exists yet, so this
amendment sits directly after section 9 and any results section follows it.
Registry row `college_pitk_box_challenger` now reads registration_status
`registered, not read`.

### 10.1 Why the original frame cannot be scored

Owner answer M19CS-1 (2026-10-01, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
'the overnight writers' questions, batch 2'): **(c) re-register on the
draft-prospect NCAA K/9 lines already held** (a smaller subset scored as K per
9), re-registered now before any look.

The frame of sections 3 and 7 is unscoreable: its input is the NCAA pitching
box line in `collegesavant_box_scores`, and on 2026-10-08 that table still
holds 1 row (side batting, season 2026) and no pitching row. The fetch named
as precondition 1 in section 7 has not run, and no lane is scheduled to run it
before 2026-11-02, so under section 7 the look would record NOT SCORED. The
held NCAA pitching lines are in `draft_statlines` instead, and most of them
carry K/9 with no strikeout, hit or walk count (10.3), so the section 3 box K%
cannot be formed from them either.

What this amendment replaces and what it keeps:

- Replaced: the input (section 3), the scored subset S (section 3), the look
  preconditions (section 7, preconditions 1 and 2) and the scorer's input
  loader. The section 3 formula `100 * SO / (outs + H + BB)` is retired for
  this gate.
- Kept unchanged: the 232 frozen pairs (section 2) as the parent frame, the
  three models compared (section 4, with the challenger's input re-expressed
  in 10.3), the metric (section 5), the pass rule (section 6, see 10.4), the
  disclosures (section 8) and the limits (section 9).

### 10.2 The frame

Source: `draft_statlines` rows whose payload is a pitching line (no avg or obp,
a non-null `k_per_9`), the shape `college_translation._draft_statlines` reads
as a pitcher. On 2026-10-08 the table holds 268 such lines for 97 draft
prospects:

| source | level | seasons (lines) | counts carried |
|---|---|---|---|
| FanGraphs college (`fg`) | NCAA | 2022 3, 2023 35, 2024 72, 2025 77, 2026 47 | ip, k_per_9, bb_per_9; no SO, H, BB |
| NCAA box pull (`ncaa`) | (none stored) | 2026 34 | ip, so, h, bb, k_per_9 |

The frozen pair rule carries over where the lines exist:

1. S is a subset of the 232 frozen pairs in `frozen_pairs.json`. No pair is
   added after 2026-10-08, by this amendment or by any later fetch.
2. Identity: a frozen pair's `name_key` equals `college_translation.norm_name`
   of a `draft_players.player_name`. A pair qualifies when exactly one draft
   record of that name holds an NCAA pitching line (as above) of the pair's
   tracked season (`cs_year`, the same-season rule of section 3).
3. The line qualifies when its `ip` is at least 20 (section 3's floor, carried
   over) and its `k_per_9` is present.
4. A pair drops on the look date as `pair_drifted` when its tracked row or
   Single-A season no longer matches the frozen identity (section 2), as
   `no_k9_line` when its line is gone, and as `short_k9_line` when the line is
   under 20 innings or lacks K/9.

The count on 2026-10-08, from identities and the innings floor only (no K/9
value, Single-A rate or tracked K% was printed, compared or stored):

- 184 frozen pairs have no draft record by name; 38 have one but no NCAA
  pitching line of the tracked season; 10 hold a same-season line; 9 of those
  reach 20 innings.
- **|S| = 9**: tracked season 2024 8, 2025 1. Every one of the 9 has Single-A
  season 2026 and a FanGraphs college line, and on all 10 lines the line's team
  is the tracked row's school. Three names have two draft records each (Cade
  Obermueller, Malachi Witherspoon, Patrick Forbes); in each case only one of
  the two holds a same-season line, so the identity is unique.

The 9 pairs (name_key, tracked season, tracked team, draft record):

| name_key | tracked season | tracked team | draft record |
|---|---|---|---|
| ben jacobs | 2024 | ARI_SUN | draft_2025_ben_jacobs |
| cade obermueller | 2025 | IOW_HAW | draft_2025_cade_obermueller |
| jb middleton | 2024 | SOU_GOL | draft_2025_jb_middleton |
| kyson witherspoon | 2024 | OKL_SOO | draft_2025_kyson_witherspoon |
| landon beidelschies | 2024 | OSU_BUC | draft_2025_landon_beidelschies |
| malachi witherspoon | 2024 | OKL_SOO | draft_2025_malachi_witherspoon |
| marcus phillips | 2024 | TEN_VOL | draft_2025_marcus_phillips |
| michael lombardi | 2024 | TUL_GRE | draft_2025_michael_lombardi |
| patrick forbes | 2024 | LOU_CAR | draft_2025_patrick_forbes |

Dropped on the innings floor: aj russell (2024 line under 20 innings).

Context, not registered: dropping the frozen pair rule and taking every draft
prospect with a K/9 line of at least 20 innings before an earliest Single-A
pitcher season (the hitter `box_k` construction) gives 13 pairs on
2026-10-08, the 10 frozen-pair names among them. That frame is also under the
floor and is not the one the owner chose.

### 10.3 The statistic, re-expressed as K per 9

The challenger's input is the line's stored `k_per_9`, which is 9 * SO / IP.

Why K/9 is not K%: K% divides strikeouts by batters faced, K/9 by innings. A
pitcher who allows more baserunners faces more batters per inning and so
records more strikeouts per nine innings at the same K%; two pitchers with
equal K% differ in K/9 by their batters per inning. K/9 therefore mixes
strikeout skill with baserunners allowed, and it is not a rescaled K%. The held
lines cannot give K%: all 9 S lines are FanGraphs college lines, which carry
`ip`, `k_per_9` and `bb_per_9` but no strikeout, hit, walk or batters-faced
count, so neither a true K% nor the section 3 estimate exists for any pair in
S.

No conversion is applied. The production fallback that turns K/9 into a rate
divides by the constant `rate_stabilization.BF_PER_9` (38.0); a positive
constant rescale of x leaves `college_translation._fit`'s predictions
unchanged (the OLS slope scales by the inverse constant, and the shrink factor
n / (n + SLOPE_SHRINK_K) does not depend on x), up to the rounding of the
stored factor. The registration uses the stored K/9 so no conversion constant
enters the comparison.

The outcome is unchanged: the pair's Single-A K% (earliest A or A+ season with
at least 20 IP, section 2), and every error is in Single-A K% points.

How the comparator legs are re-expressed:

1. **Challenger**: `_fit` with x = NCAA K/9 of the tracked season, LOO on S.
2. **Incumbent**: `_fit` with x = the tracked K% (the served leg's own input,
   in K% units), refit LOO on the same 9 pairs. Its MAE on S, not the 4.013 of
   the 232-pair eval, is the comparison.
3. **Null**: the Single-A K% mean of the other pairs in S.

All three predict the same outcome in the same units, so each per-pair gain is
like for like although the two inputs are in different units.

### 10.4 Metric, pass rule and family

Unchanged from sections 5 and 6: LOO MAE; paired bootstrap of each mean gain,
2000 draws, seed 20261102, 95% percentile interval; permutation band from 200
shuffles of the K/9 column across S; P0 |S| >= 60; P1 gain vs the null with
its lower bound above 0; P2 gain vs the incumbent with its lower bound above
0; P3 skill vs the null above the band's 95th percentile. PASS makes the
challenger eligible only (serving is a separate owner-signed task); FAIL moves
the row to `deprecated`.

The family: section 6 tests one challenger with three skill clauses, P1, P2
and P3, and requires every one. It names no Holm step, and this amendment adds
none and drops no clause; the family stays those three clauses, each read at
its own level, all required.

Stated before any look: on the frame in hand |S| = 9, under the P0 floor of 60,
and no pair can be added (10.2 rule 1), so the look's verdict is
COVERAGE-STARVED and no skill clause is read. The look evaluates P0 from the
identity count first and joins no K/9 value, Single-A rate or tracked K% when
P0 fails. On COVERAGE-STARVED the registration closes without a skill reading:
the row stays `provisional` (`data_blocked_stub`) with registration_status
`closed, coverage-starved, not read`, the incumbent leg stays flagged and
muted, and any later challenger needs a new registration on a frame that can
reach the floor.

### 10.5 The one look

**Date: 2026-11-02, kept**, because the frame is in hand: the K/9 lines are in
the database today and S is fixed by 10.2.

Preconditions, both before 2026-11-02 and neither on a registered look date
of another gate:

1. The scorer's input loader is re-expressed to 10.2 and 10.3 (read
   `draft_statlines` as above, P0 from identities before any rate is joined)
   in a commit of its own, with tests on synthetic rows only. Until then
   `tools/college_pitk_challenger_lab.py` scores the retired box K% frame and
   must not be run for this look.
2. No fetch is needed and none is part of this gate.

If precondition 1 is not met, the look on 2026-11-02 records NOT SCORED
(scorer not re-expressed) in the results section below and closes; a later
date needs a new registration committed before any look. The look still
writes `docs/college-pitk-challenger-2026-10-01/result.json` and nothing under
`data/`.

### 10.6 Crash protocol

- A crash before `result.json` is written (an exception, a locked or missing
  database, a missing file) is recorded with its traceback in the results
  section. Nothing printed before the crash is used for any decision.
- One rerun is allowed on 2026-11-02 after a fix confined to the crash's cause,
  committed before the rerun, that changes no frame, statistic, rule, seed or
  date. If the rerun also crashes, or the fix would change anything
  registered, the look records NOT SCORED and closes.
- A crash after `result.json` is written leaves the file as the result; there
  is no rerun.
- No look runs on any other date, including a day after a crash.

### 10.7 Bans

- Before the look, nobody relates an NCAA K/9 value to a Single-A rate or to a
  tracked K% for any pitcher in S or in the wider 13-pair frame: no LOO, MAE,
  correlation, bootstrap, residual or plot, on any page, commit message, report
  or note. The 10.2 count used identities and the innings floor only.
- No pair is added after 2026-10-08, and no later fetch (NCAA box or
  FanGraphs) joins S.
- The frame, statistic, pass rule, seed and date change only by a further dated
  amendment committed before the look.
- The served `pit_k` leg stays flagged and muted; `LOW_SIGNAL_R2`,
  `SLOPE_SHRINK_K` and `BF_PER_9` are unchanged; nothing in
  `college_translation.py` is refit; no served number moves.
- The gate scores no eFV, consensus or source and forms no stratum by
  consensus FV cell.

### 10.8 Read to write this

Files read: this document (sections 1 to 9);
`docs/college-pitk-challenger-2026-10-01/frozen_pairs.json`;
`tools/college_pitk_challenger_lab.py`; `college_translation.py`
(`norm_name`, `_draft_statlines`, `load_single_a`, `_pairs`, `_fit`);
`rate_stabilization.py` (`BF_PER_9`); the registry row
`college_pitk_box_challenger`; owner answer M19CS-1 in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`; the M19 lane's fix report
(registration 09687bb2, methodology mapping 63837362).

Queries run on 2026-10-08, read-only on `prospects.db`:

- `collegesavant_box_scores` row count by side (batting 1).
- `draft_statlines` pitching lines: payload key sets, and line counts by
  season and source (10.2 table); `fetched_at` runs 2026-05-27 to 2026-10-02.
- The frozen pairs joined by name to `draft_players` and to same-season
  pitching lines: presence of a line, `ip >= 20` true or false, presence of
  SO, H and BB, the line's team (10.2 counts and list).
- The 13-pair context count: `load_single_a` keys and seasons only (the
  function returns rates in memory; they were discarded unprinted) against
  draft prospects with a qualifying earlier K/9 line.

No K/9 value, tracked K%, Single-A rate, fit, error or interval was computed,
printed or stored for this amendment.
