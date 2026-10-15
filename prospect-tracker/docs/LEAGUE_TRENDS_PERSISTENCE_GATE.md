# League Trends: the persistence read (registered 2026-10-14)

Owner ask, 2026-09-30, verbatim: "maybe also add a 'League Trends' section to the MLB Stats page that tracks
specific developing trends for both teams and individual players?"

Owner answer TR-Q2, 2026-10-01 (DECISIONS_FOR_OWNER.md, 'ANSWERED 2026-10-01 (AskUserQuestion), League Trends
batch 1'), verbatim: "**Register the read, velocity left out** until the betting candidate G4-02 is registered or
dropped". That is option (a) of TR-Q2. This document is the registration that answer commits to; it is not a
default (plan section 10: a default never registers).

Plan: `LEAGUE_TRENDS_PLAN.md` section 8 'The persistence read (TR-Q2; ruling T12)', fix rounds 1 and 2 of
2026-10-01, in the Part 8 bundle `C:/Users/noah/baseball-projects/_finalpass_2026-09-24/part8/`; the lane design is
`league_trends.md` section 3 'Honesty' in the same bundle, which takes the design from `editorial_eval.py`'s
header (COHORT, HIT, CONTROL, METRIC, KILL RULE and HONESTY GUARD). Where the lane and the plan differ, the plan
governs; Part 8 of `docs/master-plan-2026-09-24-final-pass.md` governs both.

**NOTHING IN THIS DOCUMENT WAS COMPUTED ON A LATER VALUE OF A TRAIT.** No persistence module, test, preview file
or number exists at this commit. The only figures below are copied from the League Trends calibration artifact
(the bars and their placebo tails), which scores the same player's games shuffled in time and reads no game
after its evaluation date. The look runs after this file is committed, under section 7.

---

## 1. The question

The read measures the share of the changes League Trends lists in a player's own measured trait (a recent window
against his earlier games of the same season, at the family's calibrated bar) that are still at least half as
large 30 days later, against matched players with no listed change. The served Trends tab is descriptive and
makes no such claim; until this read passes for a family, its fold says "whether these changes last is not
measured here".

## 2. The families, at their frozen bars

Copied from the preview eval artifact `.cache/league_trends/preview/league_trends_eval.json`, written by
`tools/league_trends_calibrate.py` (TR_2B_CALIBRATE_DARK, commit `4484b24b`, integrated at `7b8c1143`),
`generated_at` 2026-10-14T18:34:01Z, schema 1, 453682 bytes, sha256 `3ab21b3195850503c979ce4d6368b2f5566899c510829d9c7a0173cf0d911b90`. The policy is the strict one (TR-Q1 (a)); the swing
pool is every tracked hitter from the Savant day files (TR-Q3 (a), `pool.source` `savant_days`). The bar applies to
`|z / phi|`; tail is the per-test placebo tail at the bar; real is the pooled share of flags above the placebo;
worst is the lowest share real over the seasons judged; the held-out column is the 2026 quasi-Poisson rule's
verdict (phi 5.569).

Registered families (6):

| key | family | group | drift removed | bar | pooled flags | tail per test | real | worst (seasons judged) | 2026 held-out |
|---|---|---|---|---|---|---|---|---|---|
| `attack_angle` | Attack angle, last 30 days | swing | yes | 4.25 | 51 | 1.082e-04 | 0.9755 | 0.9741 (2024, 2025) | kept |
| `bat_speed` | Bat speed, last 30 days | swing | yes | 4 | 132 | 1.428e-04 | 0.9875 | 0.9839 (2024, 2025) | kept |
| `mix` | Pitch-family mix, last 3 starts or 8 outings | pitch | yes | 6 | 93 | 1.448e-04 | 0.9694 | 0.9440 (2023, 2024, 2025) | kept |
| `rp_ext` | Fastball extension, last 6 outings | pitch | yes | 5 | 22 | 1.806e-04 | 0.9000 | 0.9083 (2023, 2025) | kept |
| `rp_hb` | Fastball horizontal break, last 6 outings | pitch | yes | 4.25 | 66 | 1.600e-04 | 0.9705 | 0.9364 (2023, 2024, 2025) | kept |
| `rp_spin` | Fastball spin, last 6 outings | pitch | yes | 5 | 45 | 1.974e-04 | 0.9467 | 0.8538 (2023, 2024, 2025) | kept |

Served families excluded from this read:

| key | family | bar | why |
|---|---|---|---|
| `sp_velo` | Fastball velocity, last 3 starts | 4.5 | velocity family: excluded until G4-02 is registered or dropped (below) |
| `rp_velo` | Fastball velocity, last 6 outings | 4.25 | velocity family: excluded until G4-02 is registered or dropped (below) |
| `rp_entry_li` | Entry Leverage Index, last 8 outings | 4.25 | entry Leverage Index: excluded for good (plan section 8), a usage and betting close variant |

Velocity families are excluded from this read until the betting candidate G4-02 (velocity form, docs/master-plan-2026-09-11-war-epoch-drivers-betting.md) is registered or dropped; adding them needs a new dated registration.

Also excluded for good (plan section 8): every club and league series, the rotation, new-pitch and lineup rules
(events, not estimates; plan section 8 names the statistical families only), and anything pitch-count or
innings-based. No family is added or removed after this commit without a new dated registration appended to
this document, written before that family's first persistence number exists.

The bars are frozen at the values above. A later re-calibration that moves a served bar does not move this
read's bar: the look takes its families and bars from this table, not from a later artifact or from
`trend_detect.py`'s live bar table, and records the sha256 above beside the sha256 of the eval artifact present
on the look's day, printing any family or bar that differs.

## 3. Frame

- **Seasons**: completed seasons 2021 to 2025, as of each season's League Trends frame
  (`.cache/league_trends/frames/<season>/`; covers_through 2021 2021-10-03, 2022 2022-10-05, 2023 2023-10-01, 2024 2024-09-30, 2025 2025-09-28). The swing families
  (attack angle, bat speed) have bat tracking from 2024 only, so their frame is 2024 and 2025.
- **Dates**: weekly dates (the calibration's Sundays, from the third Sunday of May) through the last one at
  least 30 days before the season's last game, so every outcome window closes inside the season.
- **Flags**: the detector `trend_detect.py` at HEAD, as of each date D, at the frozen bar of section 2 and the
  family's floor; every input as of D (plan 3.1).
- **Episodes, not dates**: a run of consecutive weekly flags of one player in one family counts once; its flag
  date is its first date, and its flagged raw change and direction are the ones at that date.

## 4. Hit, control, metric

- **Hit**: over the 30 days after the flag date, the same trait (for mix, the share of the pitch family the
  flag selected), net of the league drift over those days, still differs from the flag-date baseline in the
  flagged direction by at least half the flagged raw change. A player with no eligible game in those 30 days
  is scored as no hit, on both sides, and the count is printed per family.
- **Control (the base rate)**: 5 unflagged eligible players of the same family, role, date AND baseline
  game-SD tercile (so noisier players get no head start), drawn at random with a seed per flag, scored with the
  same threshold (half the flagged raw change) in the same direction against their own flag-date baseline.
- **Metric**: hit rate of the episodes against the hit rate of their controls; the gap (flag minus control) and
  its 95 percent interval with players resampled whole (2,000 reps). The one-sided p of a family is the share
  of the 2,000 replicates whose gap is at or below zero.

## 5. Verdict

- **Holm** across the registered families at 0.05 one-sided on the gap.
- **PASS**: the gap clears Holm and the family's own hit rate is 0.5 or more.
- **FAIL**: the family has 40 or more episodes and does not pass.
- **INDETERMINATE**: under 40 episodes (the floor), whatever the gap; also every family when an exception
  occurs after scoring began (section 7).
- **Consequence**: only a PASS family's cards may print one line, "Of the changes like this listed in 2021 to
  2025, P percent were still at least half as large 30 days later (players with no listed change: Q percent)",
  and only after a separate one-commit flip (queued by the orchestrator on a PASS, not in the plan's tasks) with
  the registry row `league_trends_persistence`. FAIL and INDETERMINATE print nothing new; the fold keeps
  "whether these changes last is not measured here".
- **The 2027 kill rule** (lane section 3 'Honesty', from `editorial_eval.py`'s KILL RULE): from 2027 the
  matured monthly cohorts of a passing family are re-scored with the same hit, control and metric, and a family
  whose gap fails to clear its control in 2 matured monthly cohorts withdraws its line in one commit that the
  registry row records.
- **The honesty guard** (lane section 3, from `editorial_eval.py`'s HONESTY GUARD): the artifact
  `data/league_trends_persistence_eval.json` is written only once the look has scored; until then nothing is
  written and no `league_trends_persistence` row exists, because an empty artifact would let the row pass as
  measured.

## 6. Disclosure

Plan section 3.5 'What the probes read (ruling T3; replaces the lane's "What no probe did")', verbatim (its
section numbers are the plan's: 3.1, 3.2, 5.1 and 8 there):

> The probes' REAL tests used windows and baselines that end at D. Six inputs were whole-season, so the provisional
> bars carry information from games after D:
>
> 1. **The placebo permutation**: each player's values were shuffled across his whole season before windows were cut
>    (`shuffle_rows` on the full-season frame, `p7_calibrate.py:565`); the mix and new-pitch placebos permuted
>    whole-season dates (`:637-649`, `:666-677`). A game after D could land in a placebo window or baseline at D.
> 2. **Sigma**: pooled from deviations around each player's whole-season mean (`p7_calibrate.py:595-602`, `:714-717`;
>    `p11_hitters.py:82-85`; `p13_sp_physics.py:72-76`).
> 3. **The competitive-swing cut**: each hitter's whole-season 10th percentile of bat speed (`p11_hitters.py:43`).
> 4. **Role (SP or RP) and the primary fastball**: whole-season labels.
> 5. **The two-group shrinkage fits**: each season's tests at every date of that season.
> 6. **Club identity**: `mgmt_teams.build_map(validate=False)` votes with war_daily whole-season PA shares by club.
>
> Also read, and disclosed: 2026 through 2026-09-24 as a held-out check, now used by the pre-stated held-out rule
> (3.2); the lane's inventory reads near the betting lane (the row keys and coverage of
> `.cache/betting/completed_games.json`, no runs value printed or kept; the published dispersion constants of
> `data/betting_model_context.json`, which this plan no longer uses, D8). No probe read a game after a window on the
> real side, a later value of a trait as an outcome, a price, a vintage, a lineup capture or a grade. In the build's
> calibration and in production, items 1 to 4 use only games on or before D (3.1). For item 5: The shrink fit for
> season S uses only completed seasons before S, never S itself or a later season: in the lab, 2021 and 2022 for
> 2023, 2021 to 2023 for 2024 and 2021 to 2024 for 2025 for the pitcher families, and 2024 for 2025 for the swing
> families, whose first season 2024 has no earlier season and is scored with the floor on the raw change (which can
> only add flags, real and placebo alike); in production in season Y, the pinned seasons in shrink.seasons, all
> before Y; so no bar carries information from after the evaluation date D. Item 6, club identity, enters no bar: it
> labels cards and Teams rows only, and the build takes it from the payload vote (5.1), never `build_map`. The bars
> are re-measured that way before any registration commits (section 8).

The bars of section 2 are that re-measure: TR_2B_CALIBRATE_DARK (`4484b24b`, 2026-10-14) re-measured every
family as of each date D before this registration committed (placebo, sigma, the competitive-swing cut, role and
primary fastball from games on or before D; shrink fits from completed seasons before the scored season), and
chose every bar in code by plan 3.2's policy. Also disclosed: the frame's seasons 2023 to 2025 are the bars'
calibration seasons. The bars were chosen on placebo false rates and the share of flags above the placebo, never
on a later value of a trait, so no outcome of this read entered a bar; the overlap is stated so a reader can
weigh it.

## 7. Clock and crash protocol

- **One look**, outside step A to step Z of any fWAR label epoch, never on 2026-10-23, 2026-11-06, 2026-11-13,
  2026-11-20, the eFV reserved-read day or any registered look's date. The owner's EW3-5 instruction of
  2026-10-14 waives registered look days; a look taken on a listed date under it is recorded in section 9 as an
  owner-waived read.
- **Dry run first**: the whole reporting path runs on fixtures with nulls before the look.
- **Tee**: the look's stdout and stderr go to the task's output directory before anything else runs.
- **Checks before scoring**: the families and bars the look uses equal section 2's table; a failure stops the
  look before any outcome is read, and the look has not run.
- **Crash**: an exception after scoring began makes the look INDETERMINATE for every family; it is not rerun,
  and the task writes OWNER_QUESTION.md.

## 8. Producer and artifact

The look's producer is written by TR_P2_PERSISTENCE_LOOK, after this commit. It never reads `.cache/betting/`,
`.cache/leaderboard_vintages/`, `.cache/lineup_captures/`, `.cache/odds/`, `.cache/weather_forecasts/`,
`.cache/game_feeds/` or `data/betting_model_context.json`, imports no betting module, names none of the strings
section 5l or 5m of `docs/diamond-betting.md` bans, and relates no trait to a game result, a price or a ledger
row. The artifact is `data/league_trends_persistence_eval.json` (the honesty guard of section 5 applies).

## 9. Results

