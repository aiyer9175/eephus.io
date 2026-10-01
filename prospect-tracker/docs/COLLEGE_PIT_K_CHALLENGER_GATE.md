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
