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
