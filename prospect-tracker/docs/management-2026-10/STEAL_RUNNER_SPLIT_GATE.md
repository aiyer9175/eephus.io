# Steal runner split gate (registered 2026-10-08, read once 2026-10-14: NULL)

Status: **read once 2026-10-14 (an owner-waived early read), NULL; never served.** Results
in section 11. The text from here to section 10 is the registration as committed on
2026-10-08, unchanged: registry row `steal_runner_split` (then verdict `unvalidated`,
registration_status `registered, not read`, no eval artifact). One look: **2026-10-20**,
on 2025 attempts.

This file was committed alone, before any code it describes exists and before
any number it governs is computed. No runner-aware success model has been fit,
tuned or scored on any season, and no relation between a runner's sprint speed,
a catcher's pop time or a pitcher's hand and the outcome of a steal attempt has
been computed in this repository on the registration date. Nothing here was
chosen after seeing such a number.

## 1. Why

Owner answer W-OQ3 (2026-10-01, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
'early answers for the wiring lanes and deploy'): **(b) Also a registered
split**. Context columns (sprint-speed percentile, catcher pop time) AND a
runner-aware success model registered as a split of the execution value, fit on
2018-2023, scored once on 2025.

Plan: `docs/master-plan-2026-09-24-final-pass.md` Part 8, section 8.F P8.6
'Wiring', the W11 row and the paragraph 'The nine not built now, what each would
need' (W11 stage 2). Stage 1, the two context columns on the /management/ steal
family view, landed as W11_1_STEAL_SPEED_CONTEXT (commit 629672d7, merged at
44148769). This document is stage 2's registration (W11_2). The build and the
one read are W11_3.

The module prices the decision with a league-average runner ON PURPOSE.
`management.py` header (`management.py@64bf1bb3:14-34`, at HEAD under 'WHY
LEAGUE-AVERAGE AND NOT THE RUNNER'S OWN RATE', unchanged): DV is the decision,
priced with a league-average success rate; ER is the execution residual,
realized minus expected; DV + ER is the realized win-probability change exactly.
"The runner's speed is a roster fact, and crediting a manager for having Ronald
Acuna is the confound this module exists to avoid." So the runner-aware model
never touches DV. It can only divide ER into the part a runner of this speed
explains and the rest.

## 2. The candidate

### 2.1 The model (named now, features fixed here)

A regularized logistic regression of attempt success on the features below,
with the incumbent's log-odds as a fixed OFFSET and no free intercept:

    logit P(success) = logit(league_p[season, target]) + sum_j beta_j * x_j

`league_p[season, target]` is the column `management.attempts()` already
computes (`management.py`, in attempts(), at '.rename("league_p")'): the league
success rate of that season and target base over the attempts the table keeps,
the rate DV is priced with. With every beta at zero the candidate IS the incumbent, so the
comparison in section 4 asks only whether the features add anything to the rate
the module already uses, and a season-level shift (the 2023 rule changes
included) is absorbed by the offset for both models alike.

The features, eleven coefficients, each fixed here with its constant:

| id | feature | definition |
|---|---|---|
| R1 | runner speed | sprint-speed percentile / 100 - 0.5 when the runner is on that season's Savant sprint speed leaderboard, else 0 |
| R2 | runner not listed | 1 when the runner is not on that season's leaderboard (under 10 competitive runs, or no id), else 0 |
| R3 | runner speed, 2023 rules | R1 x [season >= 2023] (bigger bases and the disengagement limit) |
| C1 | catcher pop time | the catcher's average pop time to second that season, seconds, minus 2.00, when on file, else 0 |
| C2 | pop time missing | 1 when no catcher is named or he has no pop time on the throwing board, else 0 |
| P1 | left-handed pitcher | 1 when the plays row's `pitch_hand` is `L`, else 0 |
| P2 | lefty, steal of second | P1 x [target == 2B] |
| S1 | one out | 1 when `outs_before` == 1 (two-out attempts are not in the frame), else 0 |
| S2 | another runner on | 1 when any base other than the runner's origin base is occupied (`base_before` minus the origin bit is non-zero), else 0 |
| S3 | score state | the batting team's pre-play margin, clipped to [-4, 4], divided by 4 (`score_diff` is home minus away before the play, `win_expectancy.pre_play_score_diff`; negated in the top half) |
| S4 | late and close | 1 when `inning` >= 7 and the absolute pre-play margin is at most 1, else 0 |

The percentile is the one stage 1 serves (`mgmt_steal_context.PCT_DEFINITION`:
the midrank share of that season's leaderboard runners who are slower, times
100, rounded to nearest). The pop time is the one stage 1 serves
(`mgmt_steal_context.POP_DEFINITION`), to second base, used for steals of third
and home too, as stage 1 labels it. No further scaling: every feature is already
of order one, and the centring constants (0.5, 2.00 s) are fixed numbers, not
frame means, so nothing is estimated before the fit.

**Pitcher time to plate is not on file.** No ingest of Savant's pitcher running
game board exists in the repository on the registration date (no reader, no
cache), so the model carries no time-to-plate term. Adding one needs a new
registration on a frame not yet read; this one does not reserve it.

**Not a feature, ever:** the runner's own stolen-base success rate or attempt
count, the catcher's caught-stealing rate or arm value, or anything else built
from steal outcomes. Each would carry the label into the inputs.

### 2.2 The fit

Penalized maximum likelihood with the offset: minimize

    (1 / n) * sum_i NLL_i(beta) + (lambda / 2) * sum_j beta_j^2

over the fit frame (section 3), every coefficient penalized, by L-BFGS
(`scipy.optimize.minimize`, method `L-BFGS-B`, tolerance 1e-10, start at
beta = 0). The penalty is chosen from the grid lambda in {0.0001, 0.001, 0.01,
0.1, 1} by mean log loss on the tuning frame; a tie within 1e-6 goes to the
larger lambda. The scored model is the fit-frame fit at the chosen lambda,
frozen (coefficients, lambda and the frame hashes written) before any 2025 row
is read.

A twin is fit the same way on the same frame with the runner terms R1, R2 and
R3 removed (its own lambda chosen on the same grid and tuning frame). It exists
only for pass condition 4: whether the runner terms add anything once the
battery and the state are in.

### 2.3 The split it would serve

For one priced attempt with swing = `we_success` - `we_fail`, the model's
probability `p_hat` and the runner-only probability

    p_runner = sigmoid(logit(league_p) + beta_R1 * R1 + beta_R2 * R2 + beta_R3 * R3)

(the scored model's own coefficients, every other term held at zero, that is the
league-average battery and state the offset already prices):

    ER_runner = swing * (p_runner - league_p)
    ER_other  = ER - ER_runner

so ER_runner + ER_other = ER and DV + ER_runner + ER_other = the realized
win-probability change, exactly, on every row. **DV is untouched**: it stays
`(we_success - we_fail) * (league_p - p*)` as `management.py` computes it.
ER_other holds the battery and state part and the unexplained remainder; a
finer split needs its own registration.

## 3. The frame

* **The attempts table.** `management.attempts()` as the module builds it: every
  steal attempt from the corpus events table and the plays table's own results
  (the 2026-09-11 census repair), less the counted exclusions (a prior
  state-changing event in the plate appearance, an empty origin base, no play
  row, two outs, an unpriceable state). The frame is its rows with a non-null
  `dv`, the same rows `mgmt_decisions.detect_steals` writes to the steal family
  of the decision shards.
* **The runner.** The plays row's origin-base column for the target (`on_first`
  for a steal of second, `on_second` for third, `on_third` for home), the column
  `mgmt_decisions.detect_steals` stores as the row's `in_id`; joined to the
  season's sprint block of `mgmt_steal_context` (`runners[str(id)]`, percentile
  first).
* **The catcher.** The `defense.catcher` the MLB feed names on the steal's own
  playEvent, or on the last event of a plate appearance the steal ended
  (`mgmt_steal_context.catcher_of`), keyed `game_pk:at_bat_index` in the
  season's `att` map; joined to that season's throwing board
  (`catchers[str(id)]`, pop time first).
* **The pitcher.** `pitch_hand` of the plays row on (`game_pk`,
  `at_bat_index`): the pitcher of record for the plate appearance. A pitching
  change inside a plate appearance before the attempt is not separated; it is
  disclosed here, not repaired.
* **Seasons.** Fit: 2018, 2019, 2021, 2022, 2023 (2018-2023; the corpus has no
  2020 shards). Tuning: 2024. Score: 2025, once. 2026 is in no part of this
  gate.
* The context blocks are the ones `data/management_steal_context.json` carries
  on the look date for those seasons (stage 1; the season's leaderboard, so a
  runner's percentile describes his season, not the day of the attempt, for the
  incumbent's and the candidate's frames alike). The look records the code
  commit, the payload's sha256 and each season's row count before it scores.

## 4. The statistic

On the 2025 frame, for each attempt i, with y_i the success flag, the incumbent
q_i = `league_p` and the candidate p_i:

* log loss: LL(p)_i = -[y_i ln p_i + (1 - y_i) ln(1 - p_i)], probabilities
  clipped to [1e-6, 1 - 1e-6];
* Brier: B(p)_i = (p_i - y_i)^2.

The paired gains, positive when the candidate is better, on identical attempts:

    dLL    = mean_i [LL(q)_i - LL(p)_i]
    dBrier = mean_i [B(q)_i - B(p)_i]
    dLL_runner = mean_i [LL(twin)_i - LL(p)_i]

**Resolvable margin.** A paired bootstrap, B = 2000 resamples, seed 20261020,
resampling GAMES (`game_pk`) with replacement so that attempts in one game stay
together, each statistic recomputed on the same draws. The margin is the
one-sided 95% lower bound, the 5th percentile of the 2000 resampled means; a
gain resolves when that bound is above zero. Point values and the two-sided 90%
interval are reported beside it.

Reported, not gating: the coefficients and the chosen lambda of both fits, the
tuning-frame log loss per lambda, the 2025 calibration by decile of p, and the
2025 sums of ER_runner and ER_other by target base.

## 5. The pass rule and what a null means

**PASS** requires all four:

1. at least 1,000 scored 2025 attempts;
2. the lower bound of dLL above 0;
3. the lower bound of dBrier above 0;
4. the lower bound of dLL_runner above 0.

Requiring every condition is an intersection test, so no multiplicity
correction is applied.

PASS makes the split **eligible** to serve. Serving it is a separate flip task:
class 2, a new served column behind a module flag that defaults off
(`STEAL_RUNNER_SPLIT_LIVE`), flipped in one commit carrying the flag, the data,
the registry row and the glossary entries. DV, every manager or club figure and
the gate battery (`docs/IN_GAME_MANAGEMENT_GATE.md`) stay as they are.

**A NULL** (any condition fails): the split stays dark and is never served; the
stage 1 context columns stay exactly as served; ER is served whole as today; the
registry row moves to `deprecated` with the eval artifact and the failed
conditions named. There is no second look on 2025. A new feature set or a new
model needs a new registration on a frame not yet read.

## 6. The one look

* **Date: 2026-10-20**, once, after W11_1_STEAL_SPEED_CONTEXT has landed (it has:
  629672d7) and after W11_3 has built the lab and dry-run its whole reporting
  path on fixtures with nulls. Not before 2026-10-20. Never on a registered
  look day of another gate (`docs/*GATE*.md`, `docs/diamond-betting.md`, plan
  Part 8 section 8.B and Part 9's list); 2026-10-20 is this gate's own day in
  that list. If the look cannot run that day, it runs on the first later day
  that is no other gate's look day.
* One read. The look's stdout and stderr are teed to
  `docs/management-2026-10/look-steal-runner-split/` before anything else
  runs. The fit and the tuning run first and are frozen; the 2025 frame is read
  last.
* A crash after scoring began is reported as it happened (the log, the
  traceback, an `OWNER_QUESTION.md` beside it) and is **never rerun**.
* Output: `data/steal_runner_split_eval.json`, the registry row's eval artifact
  (the publish manifest forbids listing a registry eval artifact in
  `deploy/data_exclude.txt`), the registry row's verdict per section 5, and a
  results entry in section 11 of this file. Nothing on any served page.

## 7. The bans

* The split **never changes DV** or any manager, club or team-season grade, rank
  or figure, before its own look or after it.
* It **never prices a steal in the Diamond**: no betting row, priced cell,
  market feature or dark betting column reads it, and it relates nothing to a
  game outcome or a price.
* It **never enters a served number before the flip task**: no column, card,
  tooltip, glossary entry or summary on /management/, /franchise/ or anywhere
  else prints ER_runner or ER_other until that commit.
* No relation between the section 2 features and steal outcomes on 2025
  attempts is computed by anyone before the look; doing so disqualifies the
  candidate.
* No plus metric, quality rank or skill claim for a manager or a runner rides on
  it (the Management NEVER list).

## 8. The registry row

`steal_runner_split` in `data/model_registry.json`, rendered in
`MODEL_REGISTRY.md` (generated by `tools/gen_audit_docs.py`, never edited):
verdict `unvalidated` (a predictive claim with no measurement yet; the enum has
no word for registered), registration_status `registered, not read`, eval
artifact none. At the look it gains `data/steal_runner_split_eval.json` and moves
per section 5.

## 9. Earlier measurements, disclosed

None relates a section 2 feature to an outcome.

* Stage 1 (629672d7) published join coverage only, by season (priced steal rows
  / runner percentile / catcher named / pop time): 2018 1606/1594/1606/1602,
  2019 1399/1392/1399/1394, 2021 1354/1346/1354/1353, 2022 1522/1501/1522/1521,
  2023 2081/2068/2081/2081, 2024 2081/2069/2081/2078, 2025 2122/2105/2122/2120.
  The /management/ steal view prints each row's context beside its outcome; no
  aggregate of the two exists in the repository.
* The incumbent's league rates are served (`data/management_running.json`):
  the league steals second at 75.00% against a 75.03% swing-weighted
  break-even. Those are the offset, not a candidate result.
* The family's gate battery found no repeatable manager signal (split-half
  0.1085 inside its null band -0.1501 to 0.1272,
  `data/management_gate_eval.json`). That is about agents, not about runners,
  and nothing here reopens it.

## 10. Read to write this

* `docs/master-plan-2026-09-24-final-pass.md` Part 8, 8.F P8.6 (the W11 row,
  'The nine not built now', 'Honesty status') and the base-coach paragraph that
  names W11 as the substrate of SG-Q4's 2027 tests.
* `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the W-OQ3 row.
* `management.py` (the header and `attempts()`), `mgmt_decisions.py`
  (`detect_steals`), `mgmt_steal_context.py` (the header, `catcher_of`,
  `context_for`, `steal_rows_on_disk`), `win_expectancy.py`
  (`pre_play_score_diff`), the corpus `plays` and `events` columns.
* `docs/IN_GAME_MANAGEMENT_GATE.md`; the registry rows `mgmt_running_game`,
  `mwar_running_game`, `mwar_running_gate`; commit 629672d7's message.
* `docs/COLLEGE_CAREER_REFIT_GATE.md` and `docs/dpw-2026-09-25/DPW_PATH_GATE.md`
  for the registration form; `deploy/data_exclude.txt` for the eval artifact
  rule; `_finalpass_2026-09-24/part9/PLAN.md` (U-8 and the TM_3 row) for the
  2026-10-20 date.

## 11. Results

**Read once, 2026-10-14: NULL.** An OWNER-WAIVED EARLY READ (EW3-5, owner 2026-10-14,
'Fuck the registered look days and waiting, we don't have to wait for anything. Let's do
everything today'), six days before the registered date 2026-10-20; see the dated
note below. Pass condition 4 fails, so the split stays dark and is never served (section 5).

* The run: `python -u tools/mgmt_steal_runner_split.py --look --owner-waived-early-read`, once,
  at code commit 91a43a596b051f0cd1d767c4e7a6023d14164233 (lab blob 23d4994518dab17a839291c13ae1b20cdd6de1b4), Python 3.13.9,
  numpy 2.3.5, scipy 1.16.3, pandas 2.3.3; stdout and
  stderr teed to `look-steal-runner-split/look_stdout_stderr.log` before anything ran; exit 0.
  The reporting path was dry-run on fixtures with nulls first (`--dry-run-fixtures`).
* Context payload `data/management_steal_context.json`, sha256 980cfc83899b39dd0c5a3d178952ce9f4c24c70ced2ba3fd741540ad7452f961
  (generated 2026-10-03T21:29:50+00:00); rows by season 2018 1606, 2019 1399, 2021 1354, 2022 1522, 2023 2081, 2024 2081, 2025 2122.
* Frames: fit 2018 1,606, 2019 1,399, 2021 1,354, 2022 1,522, 2023 2,081 (7,962, sha256 6f45006947c1c059e66984c3f09d31b5a6a67fdac79a488fe1b4b2bbab6c70b9); tune 2024
  2,081 (sha256 cb878be47e3baaa1e26a8e1a7c132cedf107fd98c94fcde37e608a0fc6163d35); score 2025 2,122
  (sha256 d43c43ed689ee672bb1caa18fff2ea40ab79c61945d3a1e801f10f83f115ee57) in 1,350 games. The fit and the tuning
  were frozen to `look-steal-runner-split/frozen_fit.json` before the 2025 frame was read.
* Chosen lambda: candidate 0.0001, twin 0.0001. Tuning-frame mean log loss by lambda
  (candidate / twin): 0.0001 0.52990449 / 0.53030328; 0.001 0.53002310 / 0.53059664; 0.01 0.53082714 / 0.53162962; 0.1 0.53291722 / 0.53329621; 1.0 0.53437135 / 0.53441340; incumbent 0.53463469.
* Candidate coefficients: R1 +0.858033, R2 +0.344923, R3 +0.105154, C1 +2.032669, C2 +0.556049, P1 -0.041592, P2 -0.248839, S1 -0.113526, S2 +0.434293, S3 -0.051827, S4 +0.007880.
* Twin coefficients: C1 +1.433668, C2 +0.645866, P1 -0.000953, P2 -0.208221, S1 -0.005076, S2 +0.459050, S3 -0.036274, S4 +0.085329.

| statistic | point | one-sided 95% lower bound | two-sided 90% interval | resolves |
|---|---|---|---|---|
| dLL | +0.007898 | +0.002508 | [+0.002508, +0.012903] | yes |
| dBrier | +0.002415 | +0.000275 | [+0.000275, +0.004358] | yes |
| dLL_runner | +0.000099 | -0.003645 | [-0.003645, +0.003622] | no |

Pass conditions: 1 (n 2,122 >= 1,000) met; 2 (dLL) met; 3 (dBrier) met; 4 (dLL_runner) FAILED.

Mean log loss on 2025: incumbent 0.544464, candidate 0.536566,
twin 0.536665; Brier: incumbent 0.179498, candidate 0.177082.
The candidate beats the league rate, and the twin without the runner terms scores within
0.0001 of it: once the battery and the state are in, the runner terms add no resolvable gain.

Reported, not gating: 2025 calibration by decile of p (n, mean candidate p, mean incumbent q,
success rate): 1: 213, 0.6172, 0.7577, 0.7230; 2: 212, 0.6845, 0.7653, 0.6509; 3: 212, 0.7139, 0.7653, 0.7453; 4: 212, 0.7353, 0.7647, 0.7170; 5: 212, 0.7523, 0.7655, 0.7264; 6: 213, 0.7676, 0.7650, 0.7700; 7: 212, 0.7818, 0.7658, 0.7783; 8: 212, 0.7961, 0.7654, 0.7783; 9: 212, 0.8114, 0.7656, 0.8443; 10: 212, 0.8426, 0.7635, 0.9104.
2025 sums of the split by target base, wins (ER / ER_runner / ER_other): 2B n 1841: +1.6870 / +4.2617 / -2.5747; 3B n 279: +0.1654 / +0.7509 / -0.5855; HOME n 2: +0.0000 / +0.0000 / -0.0000; identity max abs error 6.94e-18. Never served.

What the NULL does (section 5): the split stays dark and is never served; the stage 1 context
columns stay exactly as served; ER is served whole; the registry row `steal_runner_split` moves
to `deprecated` with `data/steal_runner_split_eval.json` and condition 4 named. No second read on
2025. DV, every manager or club figure and the gate battery are unchanged; nothing prices a steal
in the Diamond.

## Note 2026-10-14: an owner-waived early read

The one look was taken on 2026-10-14, before its registered date of 2026-10-20, under the
owner's instruction of 2026-10-14 (EW3-5) that waives registered look dates. It is recorded as an
OWNER-WAIVED EARLY READ. Nothing else about the read changed: the frame, the features, the
grid, the statistic, the seed and the pass rule are the ones registered above, the fit and the
tuning were frozen before 2025 was read, and the read ran once.
