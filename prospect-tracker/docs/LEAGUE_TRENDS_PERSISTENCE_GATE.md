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

### 2026-10-15: the one look, an OWNER-WAIVED EARLY READ (EW3-5)

**The look ran once, on 2026-10-15, under the owner's EW3-5 instruction of 2026-10-14** (registered look
days and dates waived; see the dated note below section 9). 2026-10-15 is a registered look day of other gates
(`docs/HEM_XWOBA_REGATE_GATE.md` ran its one read today; `docs/AGING_V3_GATE.md` names it as its section 13
rule's first free day), so this is an OWNER-WAIVED EARLY READ by section 7's own clock; it is not 2026-10-23,
11-06, 11-13 or 11-20, not the eFV reserved-read day, and the fWAR label epoch's step Z entry is dated 2026-10-03
in part 9 of `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`, so the state is not between step A and step Z.

**Producer and record.** `tools/league_trends_persistence.py` at `dc16d88b` (commit 1 of task
TR_P2_PERSISTENCE_LOOK, code only, with `test_league_trends_persistence.py`, 14 passed). The dry run on fixtures
with nulls ran first (`--dry-run`, exit 0); the look's stdout and stderr were teed to the task's output
directory (`look.log`) before anything else ran; one session, exit 0, no exception, no rerun. The record is
`docs/league-trends-2026-10-15/persistence_eval.json` (schema 1, generated_at 2026-10-15T15:47:51Z,
sha256 `bafa0d54594a345238f4e6986da6d89d34d71c3fecec3642da18c9bab0c51a9d`), committed with this entry. `data/league_trends_persistence_eval.json` is NOT written by
this task (section 5's honesty guard; section 8): it belongs to the one-commit flip the orchestrator queues on a
PASS, together with the registry row `league_trends_persistence`. Nothing served moves at this commit.

**Checks before scoring, all met**: the families and bars the look used equal section 2's table
(attack_angle 4.25, bat_speed 4, mix 6, rp_ext 5, rp_hb 4.25, rp_spin 5; excluded
sp_velo, rp_velo, rp_entry_li); `trend_detect.BARS['strict']` carries the same six bars; the eval artifact
on the look's day has sha256 `3ab21b3195850503c979ce4d6368b2f5566899c510829d9c7a0173cf0d911b90` (registered
`3ab21b3195850503c979ce4d6368b2f5566899c510829d9c7a0173cf0d911b90`, equal: True), generated_at 2026-10-14T18:34:01Z, with the same six bars;
every calibration lab memo's signature matched its frame (lab_version 2, R 20, seed 20261001), so the fits and
placebo SDs are the calibration's own, taken from earlier seasons only.

**Frame** (section 3): weekly Sundays from the third Sunday of May through the last one at least 30 days before
each season's last game, so every outcome window closes inside the season.

- 2021: covers through 2021-10-03, 2,429 games, content key `74c4d4e3fa62eba34a86`, 16 dates 2021-05-16 to 2021-08-29
- 2022: covers through 2022-10-05, 2,430 games, content key `cf5d5c372b89be6fabbf`, 17 dates 2022-05-15 to 2022-09-04
- 2023: covers through 2023-10-01, 2,430 games, content key `8fb92b5a2685f344e095`, 15 dates 2023-05-21 to 2023-08-27
- 2024: covers through 2024-09-30, 2,429 games, content key `4963f866615adefcb137`, 15 dates 2024-05-19 to 2024-08-25
- 2025: covers through 2025-09-28, 2,430 games, content key `2c554f39142ec1374006`, 15 dates 2025-05-18 to 2025-08-24

**Fits and placebo SDs per scored season** (earlier seasons only; a first season has no fit and applies the
floor on the raw change):

- `attack_angle`: 2024: phi 1, no fit (floor on the raw change); 2025: phi 0.992559, pi0 0.3494, tau 1.4685 on [2024]
- `bat_speed`: 2024: phi 1, no fit (floor on the raw change); 2025: phi 0.999218, pi0 0.2914, tau 0.5970 on [2024]
- `mix`: 2021: phi 1, no fit (floor on the raw change); 2022: phi 0.924428, pi0 0.5314, tau 0.0710 on [2021]; 2023: phi 0.926129, pi0 0.5509, tau 0.0707 on [2021, 2022]; 2024: phi 0.923081, pi0 0.5374, tau 0.0716 on [2021, 2022, 2023]; 2025: phi 0.922179, pi0 0.5367, tau 0.0702 on [2021, 2022, 2023, 2024]
- `rp_ext`: 2021: phi 1, no fit (floor on the raw change); 2022: phi 0.996617, no fit (floor on the raw change); 2023: phi 0.992298, no fit (floor on the raw change); 2024: phi 0.988281, no fit (floor on the raw change); 2025: phi 0.986382, no fit (floor on the raw change)
- `rp_hb`: 2021: phi 1, no fit (floor on the raw change); 2022: phi 0.985906, pi0 0.4022, tau 0.8812 on [2021]; 2023: phi 0.990453, pi0 0.4355, tau 0.8706 on [2021, 2022]; 2024: phi 0.989426, pi0 0.4448, tau 0.8767 on [2021, 2022, 2023]; 2025: phi 0.988832, pi0 0.4461, tau 0.8647 on [2021, 2022, 2023, 2024]
- `rp_spin`: 2021: phi 1, no fit (floor on the raw change); 2022: phi 0.992337, pi0 0.5399, tau 79.6059 on [2021]; 2023: phi 0.994557, pi0 0.6295, tau 73.0080 on [2021, 2022]; 2024: phi 0.989295, pi0 0.6079, tau 64.4111 on [2021, 2022, 2023]; 2025: phi 0.984006, pi0 0.5860, tau 59.7352 on [2021, 2022, 2023, 2024]

**Results, per family** (flags: flagged player-dates; episodes: runs of consecutive weekly flags, one each;
hit and control rates in percent; the gap is hit rate minus control rate with its 95 percent interval from
2,000 replicates with players resampled whole; p one-sided; Holm at 0.05 over the six registered families,
m = 6, a family with no episode at p = 1):

| family | bar | flags | episodes | players | hits | hit rate | flags, no game | controls | episodes short of 5 | control hits | control rate | controls, no game | gap | gap 95 percent | p | Holm rank | Holm threshold | clears Holm | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `attack_angle` | 4.25 | 21 | 14 | 14 | 9 | 64.3 | 0 | 70 | 0 | 11 | 15.7 | 3 | 0.4857 | 0.1711 to 0.7714 | 0.0025 | 6 | 0.05000 | yes | **INDETERMINATE** |
| `bat_speed` | 4 | 69 | 46 | 40 | 32 | 69.6 | 1 | 230 | 0 | 24 | 10.4 | 9 | 0.5913 | 0.4666 to 0.7167 | 0.0000 | 1 | 0.00833 | yes | **PASS** |
| `mix` | 6 | 81 | 47 | 42 | 33 | 70.2 | 1 | 235 | 0 | 10 | 4.3 | 12 | 0.6596 | 0.5000 to 0.8043 | 0.0000 | 2 | 0.01000 | yes | **PASS** |
| `rp_ext` | 5 | 39 | 22 | 17 | 10 | 45.5 | 1 | 110 | 0 | 5 | 4.5 | 4 | 0.4091 | 0.2091 to 0.6000 | 0.0000 | 3 | 0.01250 | yes | **INDETERMINATE** |
| `rp_hb` | 4.25 | 86 | 41 | 37 | 28 | 68.3 | 2 | 205 | 0 | 16 | 7.8 | 13 | 0.6049 | 0.4533 to 0.7512 | 0.0000 | 4 | 0.01667 | yes | **PASS** |
| `rp_spin` | 5 | 100 | 41 | 33 | 30 | 73.2 | 5 | 205 | 0 | 14 | 6.8 | 19 | 0.6634 | 0.5222 to 0.7950 | 0.0000 | 5 | 0.02500 | yes | **PASS** |

By season (episodes, hits, control hits over controls):

- `attack_angle`: 2024: 6 ep, 4 hit, 4/30 ctl; 2025: 8 ep, 5 hit, 7/40 ctl
- `bat_speed`: 2024: 20 ep, 16 hit, 14/100 ctl; 2025: 26 ep, 16 hit, 10/130 ctl
- `mix`: 2021: 3 ep, 1 hit, 1/15 ctl; 2022: 10 ep, 5 hit, 2/50 ctl; 2023: 12 ep, 8 hit, 4/60 ctl; 2024: 13 ep, 11 hit, 2/65 ctl; 2025: 9 ep, 8 hit, 1/45 ctl
- `rp_ext`: 2021: 3 ep, 1 hit, 3/15 ctl; 2022: 6 ep, 4 hit, 1/30 ctl; 2023: 7 ep, 3 hit, 0/35 ctl; 2024: 1 ep, 0 hit, 0/5 ctl; 2025: 5 ep, 2 hit, 1/25 ctl
- `rp_hb`: 2021: 10 ep, 7 hit, 1/50 ctl; 2022: 8 ep, 5 hit, 3/40 ctl; 2023: 13 ep, 10 hit, 5/65 ctl; 2024: 5 ep, 5 hit, 4/25 ctl; 2025: 5 ep, 1 hit, 3/25 ctl
- `rp_spin`: 2021: 24 ep, 19 hit, 11/120 ctl; 2022: 6 ep, 5 hit, 2/30 ctl; 2023: 5 ep, 4 hit, 1/25 ctl; 2024: 2 ep, 1 hit, 0/10 ctl; 2025: 4 ep, 1 hit, 0/20 ctl

**Verdicts**: 4 PASS, 0 FAIL, 2 INDETERMINATE: attack_angle INDETERMINATE, bat_speed PASS, mix PASS, rp_ext INDETERMINATE, rp_hb PASS, rp_spin PASS.
The lines a PASS family's cards may print, after the flip only: `bat_speed`: "Of the changes like this listed in 2021 to 2025, 70 percent were still at least half as large 30 days later (players with no listed change: 10 percent)." `mix`: "Of the changes like this listed in 2021 to 2025, 70 percent were still at least half as large 30 days later (players with no listed change: 4 percent)." `rp_hb`: "Of the changes like this listed in 2021 to 2025, 68 percent were still at least half as large 30 days later (players with no listed change: 8 percent)." `rp_spin`: "Of the changes like this listed in 2021 to 2025, 73 percent were still at least half as large 30 days later (players with no listed change: 7 percent)."

**What this entry does and does not say** (section 5's scope). It reports, per family, the measured share of
listed changes still at least half as large 30 days later and the same share among matched unflagged players,
with the gap's interval. It draws no conclusion about any family the measurement does not support: an
INDETERMINATE family (under 40 episodes) says only that the frame held too few episodes to judge, and a FAIL says
the gap did not clear Holm or the hit rate fell under 0.5 on this frame. The defaults the producer applied
where sections 4 and 5 are silent are printed in the artifact's `design` block and in commit `dc16d88b`'s
message: the flagged direction is the sign of d, the threshold half of |raw|; for mix the trait is the plain
pooled share of the selected pitch family; Holm runs over all six families; the control pool excludes every
player flagged at that date and a tercile short of five candidates gives what exists, counted. The only later
value read was the trait itself over the 30 days after a flag, which is this registered read's whole purpose;
no game result, price, ledger row, betting cache or vintage was read (the stop-list snapshot of the task's
output directory is byte-identical before and after the look).

**The 2027 kill rule** (section 5) binds any PASS family from 2027; a later re-calibration does not move these
bars or this verdict (section 2).

---

## Dated note, 2026-10-15 (appended below the document's last section, EW3-5)

The owner's instruction of 2026-10-14 (EW3-5, verbatim in the task preamble: registered look days and waits
are waived; wait only for data that does not exist yet) governs this look's timing. Section 7's clock clauses
were otherwise honoured as written above. The look is recorded in section 9 as an OWNER-WAIVED EARLY READ.
