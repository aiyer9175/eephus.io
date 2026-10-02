# College translation career-label refit gate (registered 2026-10-02, NOT SCORED)

Status: **registered, not scored.** Registry row `college_translation_career_refit`
(verdict `provisional`, provisional_kind `data_blocked_stub`, registration_status
`registered, not scored`). One look: **2026-11-09**.

This file was committed before any fit on the career label. No refit, no
leave-one-out score and no pair count on the label defined below exists on the
registration date. Nothing here was chosen after seeing a career-label number.

## 1. Why

Owner answer M20-3 (2026-09-25, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
'more' batch 20; census M03-13): ship per-player receipts and an out-of-sample
scorecard on the served fit, and pre-register a refit of the translation on
`career_stats` labels.

The served translation (`college_translation.py`, eval
`data/college_translation_eval.json`) is fit on one label: the earliest A or
A+ season `load_single_a` finds in `statlines`. `statlines` holds one row per
player, his current season, so the fit only ever sees players whose current
row is still at A or A+. A player who passed through Single-A and moved on
(Charlie Condon: 2024 A+, now AAA) is not in the fit, which selects the pool
toward players who stalled at the level. `career_stats` holds every MiLB
season a player has logged.

## 2. The label (defined here, not measured)

For one CollegeSavant player with college source season Y (the season the
served projection is built from: the latest tracked season for a hitter, the
most-pitched season carrying K% and BB% for a pitcher):

* **Rows.** Every `career_stats` row of his MiLB player_key with level `A` or
  `A+`, season >= Y, and the matching side (`is_pitcher` false for the hitter
  legs, true for the pitcher legs).
* **Career Single-A line.** The rows pooled into one line:
  * hitters: K% and BB% averaged with at-bat weights; OPS averaged with at-bat
    weights. `career_stats` carries no plate appearances, so at-bats are the
    weight and the sample unit.
  * pitchers: K% and BB% averaged with innings weights (IP converted from
    baseball notation, `.1` = 1/3, `.2` = 2/3).
* **Minimum sample.** Hitters at least **100 AB** pooled (about 115 PA);
  pitchers at least **20 IP** pooled (about 84 BF at the shared BF_PER_9 of
  38). A player under the minimum gives no pair.

The target level stays Single-A, as the served "Projected Single-A" names it;
the change is the label's span (every Single-A season on or after the college
season) and its source (`career_stats`, not `statlines`).

## 3. The frame

* College side: `load_cs_hitters()` and `load_cs_pitchers()` as on the look
  date, the same rows the served build reads.
* Identity: the draft record from `resolve_draft_keys` (the census M03-06
  join: earliest non-prep record of draft year >= Y), then that record's
  `draft_players.promoted_key`, then `career_stats` by that key. A player
  with no resolved draft record, no promoted_key or no `career_stats` row
  gives no pair. No name-only fallback.
* Legs: `hit_k` (college K% to career A K%), `hit_bb`, `hit_ops` (college xwOBA
  to career A OPS), `pit_k`, `pit_bb`. The box legs (`box_k`, `box_bb`) are
  outside this gate.
* Frame F_L for leg L: every pair with a non-null college input and a career
  label for that leg. Fixed at the look; nothing is added afterwards.

## 4. Models compared, on F_L only

* **C, the career refit.** `college_translation._fit` (shrunk-slope
  regression to the mean, SLOPE_SHRINK_K unchanged) on the career labels,
  scored leave-one-out: each pair predicted from a fit without it.
* **P, the production fit.** The served factor for leg L as
  `college_translation.build()` fits it on the look date (statlines labels).
  Where a scored pair is also a production pair, P is refit without it, so P
  is out of sample on every pair too. P is scored against the career label.
* **N, the null.** The mean career label of the other pairs in F_L.

## 5. Metric and pass rule

Per leg: leave-one-out MAE of C, P and N against the career label; the paired
per-pair gains |err_P| - |err_C| and |err_N| - |err_C|; a paired bootstrap 95%
interval of each mean gain (2,000 resamples of F_L, seed 20261109); C's
P10-P90 band coverage on the held-out pairs; Spearman rank correlation of C's
held-out prediction with the label (reported, not gating).

**PASS for leg L** requires all of:

1. n(F_L) >= 100;
2. the lower bound of the gain over P is above 0;
3. the lower bound of the gain over N is above 0;
4. C's held-out P10-P90 coverage is between 0.75 and 0.85.

PASS makes leg L **eligible** to replace the served factor; serving it is a
separate owner-signed task that also moves the served LOO MAE, coverage and
the What-to-trust copy, and it waits for the served-change window to reopen.
A leg that fails stays on the production fit; the registry row records the
failed legs, and if every leg fails the row moves to `deprecated`.

## 6. The one look

* Date: **2026-11-09**, once. Not before. Running a career-label fit, score or
  pair count before that date disqualifies the challenger. A second look is
  not allowed; a new label needs a new registration.
* Output: an eval artifact under `docs/college-career-refit-2026-11-09/`
  (not served), the registry row updated with the verdict, and nothing on any
  served page.
* Precondition: the M03-06 identity join is in the build (commit 61b75abd).

## 7. Earlier measurements, disclosed

These were made before this registration on related labels; none is a career
pooled A/A+ line, and none fit a translation on one.

* Production eval (`data/college_translation_eval.json`, 2026-10-02): hit_k
  r2 0.172, LOO MAE 5.323; pit_k r2 0.033, LOO MAE 4.013 against 3.995 for the
  mean (n 217 hitters, 232 pitchers).
* Census M03-13 judge probes (2026-09-24, read only): served projected K%
  against the EARLIEST A/A+ season in `career_stats` for players outside the
  fit: hitters n 186, mean residual -3.68, MAE 6.88; pitchers n 217, mean
  +2.21, MAE 5.04. Unique-name earliest-season receipts: 386 hitters, 470
  pitchers.
* The out-of-sample scorecard `data/college_translation_scorecard.json`,
  published after this registration, scores the production fit on its own
  statlines labels only and never reads `career_stats`.
