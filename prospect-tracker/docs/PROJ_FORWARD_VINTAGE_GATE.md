# MLB Projections forward vintage gate (pre-registered 2026-10-09)

Registers the one forward test the `/projections/` engine can take that no backtest
can stand in for: the preseason projection, frozen before the season it predicts,
scored against that season once it is over.

Owner answers executed here (final-pass 'more' batch 15, answered 2026-09-25,
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`):

- **M15-2.** The 2027 preseason projections are frozen as the LAST nightly before the
  first 2027 regular-season game, committed by hand, hash-pinned, holding through a
  lockout, and scored forward at season end.
- **M15-3.** The first projected season (`proj_export.FIRST_SEASON`) stays a MANUAL,
  dated flip, with a guard that refuses to move it past a season whose frozen file does
  not exist.

Written and committed alone, BEFORE any frozen file, producer or score exists. Nothing
in this document moves a served number. Where a later measurement and this document
disagree, the disagreement is recorded in section 9 and never edited away.

---

## 1. Why a freeze is needed at all

`data/mlb_projections.json` is gitignored and rewritten by every nightly. Nothing keeps
a copy of yesterday's projection: `prospects.db` keeps surplus history only, and no
table or file snapshots the WAR projection itself (census M05, served_state item 24).
So on the day a season ends there is no record of what the engine said before it
started, and every "forward" number would be a replay by a model that has since been
retrained, re-blended or re-labelled. The Team Outlook forward gate
(`data/team_outlook_eval.json` `forward_gate`, "pending, first scoreable end of 2027")
has had no forecast to grade for the same reason.

The freeze is the forecast. Its git commit, made before the first pitch it predicts,
is the timestamp.

## 2. The freeze rule

**F1. Which file.** The served `data/mlb_projections.json` of the last nightly build
that completed before the scheduled first pitch of the first 2027 regular-season game
(StatsAPI `gameType = R`, the earliest `gameDate` of the 2027 schedule, international
openers included). "Served" means the copy the public site served at that moment; when
the box and a local build disagree, the box copy is the one frozen and the freeze log
says where it came from.

**F2. Preconditions, each checked by the freeze tool and refused if it fails.**

1. The file's `first_season` is 2027 and its `horizon` is 5.
2. Its `generated_at` date is on or before the date of that first game.
3. Its `vets` rows each carry `mlbam`, `war`, `warP10` and `warP90`, and every
   `team_outlook` row carries `byYear[0].wins`.
4. No frozen file for 2027 exists yet. The freeze is WRITE-ONCE.

**F3. By hand.** The freeze is taken and committed by a person (or a session acting for
the owner), never by the nightly: a nightly step that wrote it would rewrite it the next
night, and the box nightly reverts tracked files (`git checkout -- .`) before it builds.

**F4. Through a lockout.** The trigger is the first regular-season game actually
played, not a calendar date. If the 2027 season is delayed, the nightly keeps serving
the 2027 projections and the freeze waits for the delayed first game. If the season is
shortened, section 5's pro-rating applies. If no 2027 regular-season game is played at
all, the freeze log records a `no_season` entry for 2027 in a dated amendment to this
document (section 9), and that entry is what the section 4 guard accepts in place of a
file. A freeze, once committed, is never re-taken, whatever happens after it.

**F5. Missed.** If the first game passes with no freeze, the season is recorded as
MISSED in section 9 and is not scored. A replay of a later build is not a substitute
and may not be published as one.

## 3. The files and the hash pin

All under `data/proj_forward_vintage/`, which is below `data/` depth one and therefore
ships in neither deploy consumer (evidence, not a page).

| file | what |
|---|---|
| `mlb_projections_2027_preseason.json` | the frozen file, BYTE-IDENTICAL to the served file of F1 |
| `FREEZE_LOG.json` | one entry per frozen season: `season`, `file`, `sha256` (of the frozen file's bytes), `source` (where the bytes were taken from), `source_generated_at`, `first_game` (`gamePk`, `gameDate`), `frozen_at`, `status` (`frozen` or `no_season`), and an `extract` with its own `extract_sha256` |

The `extract` carries, for every veteran row, `mlbam`, `key`, `war[0]`, `warP10[0]`
and `warP90[0]`, and for every Team Outlook row, `team` and `byYear[0].wins`, so a
reader can verify the numbers it uses against the frozen file's hash without parsing
the whole payload. The Awards plan's AWARDS_13 preseason reader
(`_finalpass_2026-09-24/awards/AWARDS_PLAN.md`) reads these fields and never writes the
freeze.

Producer: `tools/freeze_proj_forward_vintage.py` (`--season`, `--source`,
`--first-game-pk`, `--first-game-date`; `--check` re-verifies every logged hash and
writes nothing). Pinned by `test_proj_forward_vintage.py`: every log entry's `sha256`
equals the hash of its file, every `extract_sha256` equals the hash of its extract, the
extract equals the fields read from the file, and the folder is not in the publish
manifest. The freeze commit adds the season's hash to the test as a literal, as
`test_provisional_freeze_pin.py` does for the provisional freeze, so any later rewrite
fails the suite.

## 4. The first-season flip guard

`proj_export.FIRST_SEASON` (2027 since 2026-06-10) moves by hand, in its own dated
commit, never by the calendar. `proj_export.FIRST_SEASON_SET_ON` carries the date of
the last flip and moves with it.

`proj_export.assert_first_season_flip_allowed()` runs at the start of every payload
build and refuses (raises) when `FIRST_SEASON` is later than 2027 and any season from
2027 through `FIRST_SEASON - 1` has no `frozen` or `no_season` entry in
`FREEZE_LOG.json` whose file hash still matches. So the board cannot roll to 2028 until
the 2027 forecast is on record, and it cannot roll at all if the record was edited.
Pinned by `test_proj_forward_vintage.py` (refuses without the entry, refuses on a hash
mismatch, accepts a matching entry, accepts `no_season`, is a no-op at 2027).

## 5. The forward score, at season end

**Producer and artifact (neither exists yet):** `tools/proj_forward_vintage_score.py`
writes `data/proj_forward_vintage_eval.json`, one block per scored season.

**When.** Once per season, after the last regular-season game and after that season's
fWAR vintage is frozen under the fWAR label epoch's rules
(`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`). Never on a registered look day of any
gate in `docs/*GATE*.md`; such a day is skipped to the next free one. One run; a re-run
is a new block that keeps the first and says why.

**The forecast scored** is the frozen file and nothing else: never the nightly, never a
replay.

**The labels.** Player WAR on the label the frozen file was trained on (the training
label at freeze time, recorded in the freeze log; `fwar` as of this writing), from that
season's frozen vintage. A veteran with no appearance in the season scores actual WAR 0
(the convention of `proj_backtest` and FA Gate 1). Team wins from final standings.

**Pro-rating (lockout or shortened season).** Counting forecasts are scaled by
`G / 162`, where `G` is the regular-season games each club was scheduled to play.
Team wins are scored as `W / games played * 162` against the frozen wins.

**Population.** Every veteran row of the frozen file and every Team Outlook row. The
prospect rows are frozen but NOT scored here: scoring them by any consensus-FV stratum
is banned by `docs/PROSPECT_ANCHOR_GATE.md`, and a pooled prospect score needs its own
registration.

**Primary statistics, each with its comparator named now.**

| block | statistic | forecast | comparator | direction |
|---|---|---|---|---|
| P1 | year-1 WAR MAE over every frozen veteran | `war[0]` | 5/4/3 weighted carry-forward of the player's three prior seasons' WAR on the same label (FA Gate 1's baseline, `fa_backtest`) | lower is better |
| T1 | team wins MAE | `team_outlook[].byYear[0].wins` | prior-season wins carried forward (the `forward_gate` baseline) | lower is better |

Each primary gap (comparator error minus forecast error) carries a paired 95% interval
from `gap_intervals.paired_cluster_interval` at its `SEED`, clustered by player for P1
and by club for T1. The verdict vocabulary is closed: `AHEAD` (interval wholly above
zero), `BEHIND` (wholly below), `NOT_RESOLVED` (straddles zero), `NOT_SCORED`
(MISSED, `no_season`, or a precondition failed). A gate that spells an absence the way
it spells a result is not a gate, so `NOT_RESOLVED` is never printed as a pass.

**Descriptive, never a verdict:** bias (actual minus forecast) and Pearson r for P1 and
T1; P10-P90 coverage of `warP10[0]`/`warP90[0]`, pooled and on players who appeared;
the league sum of `war[0]` against the realized league WAR.

**What the score may say.** That the frozen forecast was ahead of, behind, or not
resolvable from its named comparator on that one season. It is one season: no score
here re-fits, re-blends, re-gates or re-ranks anything, and no served accuracy claim
may quote it beyond its own block, its season and its verdict word.

## 6. What this gate does not do

- It moves no served number and changes no model, blend, gate constant or flag.
- It touches no frame of `docs/PROJ_PATH_SHAPE_GATE.md` (DEV 2008-2011, GATE 2012-2014,
  CONFIRM 2026, Tier-2 2015-2025). Label season 2027 is read here once, at the section 5
  score; any later registration that uses label season 2027 must disclose that read.
- It computes no realized-WAR mean, residual, anchor or count by consensus-FV cell.
- It does not replace the Team Outlook retro backtest (`proj_backtest`), which scores
  2022-2025 on actual rosters; the forward score is the first-season test that backtest
  cannot be.

## 7. Readers

- `data/team_outlook_eval.json` `forward_gate` names the frozen file as the forecast it
  will grade.
- The glossary entry `forward_gate` says the graded copy is this freeze.
- AWARDS_13 ("Furthest above / below the preseason projection", the Manager card's
  projection column) reads the extract, lit only after every registered look on that
  label season is recorded. Nothing reads a 2026 preseason projection: none was saved.

## 8. Clock

| date | what |
|---|---|
| 2026-10-09 | this registration, alone |
| the 2027 first-game day (about late March 2027; later under a lockout) | the freeze, by hand, before first pitch |
| after the last 2027 regular-season game and the 2027 fWAR vintage freeze | the section 5 score, once |
| after the last 2027 regular-season game | the earliest dated commit that may flip `FIRST_SEASON` to 2028, and only with the freeze on record (section 4) |

## 9. The append-only record

Entries are appended below, dated, and never edited. A missed freeze, a `no_season`
entry, an amendment, and each score are recorded here.

- 2026-10-09: registered. No frozen file, producer or score exists.
- 2026-10-09: amendment A1 (section 10) registered after the owner's OUTLOOK answer (a): the Team Outlook winter frames are frozen monthly from 2026-11-01 to 2027-03-01 and scored once as a separate arm. Sections 2 to 5 are unchanged. No winter-frame code, frozen file or score exists.
- 2026-10-09: amendment A2 (section 11) registered for task PJ_10_FORWARD_FREEZE_AMENDMENT: the Opening Day 2027 freeze also carries the component lines of docs/PROJ_COMPONENTS_GATE.md (H8, P3 and the gap line included), W2's paths and the 2027 team frames of docs/TEAM_PROJECTIONS_GATE.md, each hash-pinned in the same commit or recorded absent. Sections 2 to 5 and 10 are unchanged. No element file, element writer or score exists.

## 10. Amendment A1 (2026-10-09): the Team Outlook winter frames

Owner answer **OUTLOOK (a), as of signings** (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
'Part 8 batch 2 and the ETA multipliers', 2026-09-30); plan Part 8, P8.6 'New
cross-module wirings' (W03) and 8.D 'Conflicts between lanes, resolved' rows 4 and 5.

Written and committed alone, after that answer and BEFORE the winter frame's code
(`proj_export.TEAM_OUTLOOK_WINTER_FRAME`) exists, before any winter-frame number is
computed and before any 2027 game. It adds one separate arm and five dated freezes. It
changes nothing in sections 2 to 5: the Opening Day freeze (owner answer M15-2) stays the
primary read, and P1 and T1 keep their forecast fields, comparators, intervals and verdict
vocabulary.

### 10.1 The two frames

- **Pre-free-agency frame.** Team Outlook as built through 2026-10: every veteran counts
  on the club that holds him today for the first projected season, including a locked
  free agent whose contract has ended (`proj_export._last_controlled_season`, the age
  proxy that never drops the first season).
- **As-of-signings frame.** The same roll-up after the FA module's class status is
  applied. An unsigned locked free agent leaves his 2026 club for one labelled
  unassigned pool line; his WAR stays visible there and is never assigned to a club by
  fit probability (the Fit's MRR is 0.167). A signed member counts on the club the
  signing log names, from the night the signing posts. A pending option counts at his
  club weighted by the FA export's P(exercise), 1 minus `enterProb` where the
  band-priced option model set it (`enterProbSrc`), with the rest of his WAR in the
  pool; with no such probability he is held at his club at full weight and labelled. A
  locked member whose projection row carries a contract, or club control, through 2027
  or later stays on his club and is named in the payload: the contract table wins over
  the class list. Club wins plus the pool's WAR sum to the 2,430-win league pin; the
  uniform remainder is the pre-free-agency frame's, so no pool WAR is spread across the
  clubs.

**Fields.** While the flag is on, `team_outlook[].byYear[0].wins` carries the
as-of-signings frame, `team_outlook[].preFa.byYear[0].wins` the pre-free-agency frame,
and the payload's `team_outlook_frame` block the pool. While the flag is off,
`byYear[0].wins` is the pre-free-agency frame and no as-of-signings frame exists. T1
reads `byYear[0].wins` of the Opening Day file as registered; under OUTLOOK (a) that is
the as-of-signings frame from the flip on, and the same file's `preFa` field is the
pre-free-agency frame. The FA Fit reads the pre-free-agency frame under every flag
state and `data/fa_class.json` stays byte-identical; repointing the Fit's WINDOW input
is a Gate 3 lever that needs its own registration (plan P8.5, findings F-1 and F-2).

### 10.2 The five monthly freezes

| task | not before | what it freezes |
|---|---|---|
| Q9_03a | 2026-11-01 | both frames, first winter freeze |
| Q9_03b | 2026-12-01 | both frames |
| Q9_03c | 2027-01-01 | both frames |
| Q9_03d | 2027-02-01 | both frames |
| Q9_03e | 2027-03-01 | both frames, last winter freeze |

**W1. When.** Each task freezes at the first writer slot on or after its date, never on
a registered look day of any gate in `docs/*GATE*.md` (such a day is skipped to the
next free one), and records the date it actually froze. A freeze is never back-dated
and never re-taken.

**W2. Which bytes.** The served `data/mlb_projections.json` of the last nightly build
that completed before the freeze (the box copy when the box and a local build
disagree; the log says which). Preconditions, each refused if it fails: `first_season`
2027; every `team_outlook` row carries `byYear[0].wins`; with the flag on, every row
carries `preFa.byYear[0].wins` and the payload carries `team_outlook_frame`.

**W3. The file.** `data/proj_forward_vintage/team_outlook_frames_<YYYY-MM-DD>.json`,
named by the date it actually froze, WRITE-ONCE, holding `source`,
`source_generated_at`, the flag state, the pool's year-1 WAR and member count, the
named reconciled members, and per club `team`, `wins0` (the as-of-signings frame,
`byYear[0].wins`; null with `not_built` when the flag was off) and `preFaWins0` (the
pre-free-agency frame: `preFa.byYear[0].wins` with the flag on, `byYear[0].wins` with
it off). It sits under `data/proj_forward_vintage/`, which ships in neither deploy
consumer.

**W4. Missed.** A month with no freeze by the next month's date is recorded as MISSED in
10.5 and is not scored. A later build is never a substitute.

### 10.3 The score: arm W, once, at the 2027 close

**When.** Section 5's rules: after the last 2027 regular-season game and the 2027 fWAR
vintage freeze, never on a registered look day, one run; a re-run is a new block that
keeps the first and says why. Section 5's producer writes arm W as its own block,
`winter_frames`, in `data/proj_forward_vintage_eval.json`, and never changes the P1 or
T1 block.

**Labels.** Final 2027 standings, pro-rated as in section 5.

**Statistics.** For each frozen month and each frame: team wins MAE over the 30 clubs
(the registered `forward_gate` metric), and the same comparator as T1 (prior-season
wins carried forward), each gap with its paired 95% interval clustered by club.
**The arm's one verdict** compares the two frames: per club, the pre-free-agency
frame's absolute error minus the as-of-signings frame's, averaged over that club's
frozen months; the mean over the 30 clubs with its 95% interval from
`gap_intervals.paired_cluster_interval` at its `SEED` (the club is the unit). The
vocabulary is closed: `AS_OF_SIGNINGS_CLOSER` (interval wholly above zero),
`PRE_FA_CLOSER` (wholly below), `NOT_RESOLVED` (straddles zero), `NOT_SCORED` (fewer
than two frozen months with both frames, or a precondition failed). The per-month
gaps are descriptive and carry no verdict.

**What the score may say.** Which frame sat closer to final 2027 standings over the
winter freezes, on one season, or that one season cannot tell them apart. It flips no
flag and re-fits nothing; a later frame decision needs its own registration or an
owner answer. The pool is never scored: its players have no club in either frame.

### 10.4 What this amendment does not do

- It moves no served number; the frame flag flips in its own commit.
- It changes no section 2 to 5 rule, field, comparator or verdict word.
- It assigns no pool WAR by probability. A probability form is a later upgrade of the
  pool, only after the FA destination model passes its own gate.
- It computes no realized-WAR mean, residual, anchor or count by consensus-FV cell, and
  touches no frame of `docs/PROJ_PATH_SHAPE_GATE.md`; label season 2027 is read once,
  at the 10.3 score (section 6's disclosure applies to it).

### 10.5 The winter-frame freeze log (append-only)

One row per task, filled by the task that freezes; a row is never edited once filled.

| task | not before | froze on | file | sha256 | source | source generated_at | flag |
|---|---|---|---|---|---|---|---|
| Q9_03a | 2026-11-01 | pending | | | | | |
| Q9_03b | 2026-12-01 | pending | | | | | |
| Q9_03c | 2027-01-01 | pending | | | | | |
| Q9_03d | 2027-02-01 | pending | | | | | |
| Q9_03e | 2027-03-01 | pending | | | | | |

## 11. Amendment A2 (2026-10-09): the component lines, W2's paths and the team frames

Task PJ_10_FORWARD_FREEZE_AMENDMENT, plan Part 9 section 9.2 'Component projections' and
LANE_A sections 3.2 (the frozen rows of PJ-W) and 3.3 (FORWARD); owner answer **M15-2**
(this document's opening) is the freeze this amendment extends. The two gates whose 2027 reads need
these elements are `docs/PROJ_COMPONENTS_GATE.md` (PJ-W, section 6) and
`docs/TEAM_PROJECTIONS_GATE.md` (sections 2.3, 3.4 and 3.5); each names this document "as
amended by PJ_10" as the source of its 2027 rows.

Written and committed alone, BEFORE any component line, W2 bundle, team candidate or element
writer exists (at this commit `proj_components.py`, `tools/proj_component_stack.py`,
`model/proj_lgbm_components/`, `model/team_projection/` and
`data/proj_forward_vintage/FREEZE_LOG.json` are all absent), before the Opening Day freeze and
before any 2027 game. It adds elements to the one Opening Day freeze. It changes no threshold,
frame, date, comparator, verdict word or precondition of sections 2 to 5 and 10.

### 11.1 What the Opening Day 2027 freeze also commits

In the same commit as the frozen file of section 3, each beside it under
`data/proj_forward_vintage/`, each WRITE-ONCE and hash-pinned like that file:

| element | file | what it holds | where the bytes come from |
|---|---|---|---|
| E1, the component lines | `proj_components_2027_preseason.json` | for every veteran row of the frozen file, keyed by `mlbam` and `key`, the component lines for seasons 2027 to 2031 exactly as the exporter computed them on the night of the frozen file: every head of `docs/PROJ_COMPONENTS_GATE.md` section 1 the exporter emits (H0 to H7 and P0 to P5 as built), H8 and P3 (the component WAR), the gap line ("rest of the served projection", served `war` minus component WAR), and each component's 80% range where the exporter emits one | `data/` (the player detail's `comp` blocks and the board's PA and IP scalars) when `proj_export.PROJ_COMPONENTS_LIVE` is True that night, else `.cache/proj_components/preview/` |
| E2, W2's paths | `proj_component_stack_2027_preseason.json` | for the same veteran rows, W2's WAR path for 2027 to 2031 (the dark twin bundle of `docs/PROJ_COMPONENTS_GATE.md` section 6), with the sha256 of each file of the bundle that produced it and the bundle's `max_label_season` | `model/proj_lgbm_components/`, only when PJ_9_STACK_ARM_DARK built it and its veto read did not veto it |
| E3, the 2027 team frames | `team_frames_2027_preseason.json` | per club: the 2027 win-total distribution with the talent range (T1, `sigma_T` from `model/team_projection/params.json`, whose sha256 is recorded) and without it (schedule-only), each as the full histogram of simulated win totals (lossless for the CRPS of `docs/TEAM_PROJECTIONS_GATE.md` section 3.1); the T2 budgeted wins and the served wins on both of Q9_03's frames (the as-of-signings frame and the pre-free-agency frame of section 10.1); projected runs scored and runs allowed (T3) | `data/` for each candidate whose flag (`TEAM_TALENT_RANGE_LIVE`, `TEAM_PT_BUDGET_LIVE`, `TEAM_RUNS_LIVE`) is True that night, else `.cache/team_projection/preview/` |

Every element file records `source` (the path it was read from), `source_generated_at`, the
state of each flag named above, and the HEAD commit of the build that wrote it.

**W2's retrain.** If the twin bundle's `max_label_season` differs from the served bundle's
(`model/proj_lgbm/meta.json` `max_label_season`), the bundle is first retrained by
`python tools/proj_component_stack.py --final` (PJ_9's command) to the served bundle's value,
and E2's paths are computed from the retrained bundle on the inputs the last nightly used. If
the command is absent, fails, or cannot finish before the first pitch, E2 is recorded absent
with that reason. The retrain and the path computation never run on a registered look day of
another gate (docs/*GATE*.md); if that leaves no admissible day before the first game, E2 is
recorded absent with that reason.

### 11.2 Hash pin and log

The freeze's `FREEZE_LOG.json` entry for 2027 gains an `elements` list, one item per element
E1 to E3: `element`, `file` (null when absent), `sha256` of the file's bytes (null when
absent), `source`, `source_generated_at`, the flag states, `status` (`present` or `absent`)
and `reason` (required when absent). `--check` re-verifies each present element's hash with
the frozen file's. The freeze commit adds each present element's sha256 to
`test_proj_forward_vintage.py` as a literal, as section 3 does for the frozen file.

The element writer is not part of this registration. If `tools/freeze_proj_forward_vintage.py`
has no element step at the freeze, the person taking the freeze copies each element's bytes
from the source named in 11.1, records the `elements` list by hand in the same commit and
says so in the log; an element that can be neither written nor copied is recorded absent.

### 11.3 Absent elements

- An element missing at the freeze (its producer never landed, its flag and its preview both
  empty, PJ_9 not built or vetoed, the retrain failed, a precondition below failed) is recorded
  `absent` with its reason. It is never back-filled, re-computed from a later build, or
  replaced by a replay; a later build is not a substitute (section 2, F5).
- An element's preconditions, each recorded and never a refusal of the frozen file: its rows
  cover the frozen file's veteran rows (E1, E2) or the 30 clubs (E3); its source was written by
  the same nightly as the frozen file (E1, E3) or from the inputs that nightly used (E2); its
  `source_generated_at` is on or before the first game's date. A failed precondition makes
  that element `absent`, never the freeze.
- An absent element never blocks, delays or invalidates the frozen file of section 3, its
  extract, the section 4 flip guard, the section 5 score or the section 10 winter frames.

### 11.4 Where these elements are scored

Not here. E1 (H8 and P3) and E2 are scored only by PJ-W (`docs/PROJ_COMPONENTS_GATE.md`
section 6, task PJ_11_WAR_LOOK_2027); E3 only by `docs/TEAM_PROJECTIONS_GATE.md` section 3
(TM-A to TM-C re-read on 2027, section 3.5; TM-D reads its own shadow record), task
TM_9_TEAM_LOOK_2027. Section 5's producer does not read them, and P1, T1 and arm W keep their
forecast fields, comparators, intervals and verdict words. The freeze computes no realized
2027 number. The component lines are on FanGraphs' frame (Part 9 rule U2) and say so in E1's
header; the realized seasons they are later scored against are the frozen fWAR vintage's.

### 11.5 What this amendment does not do

- It moves no served number, writes nothing under `data/` and flips no flag.
- It changes no section 2 to 5 or section 10 rule, field, comparator, threshold, frame, date or
  verdict word, and does not re-date the Opening Day freeze.
- It computes no realized-WAR mean, residual, anchor or count by consensus-FV cell; the frozen
  prospect rows stay unscored (section 5, 'Population').
- It touches no frame of `docs/PROJ_PATH_SHAPE_GATE.md`; label season 2027 is read only by the
  section 5 score and the two gates named in 11.4, each once (section 6's disclosure applies).
