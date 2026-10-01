# Postseason bracket simulator gate (registered 2026-10-01, NOT READ)

Status: **registered, not read.** Model id `postseason_bracket_sim`, method
`bracket_v1`. Build task BRACKET_SIM_BUILD. No code, payload, registry row,
glossary entry or test for the simulator exists at this commit, and no
simulator number has been computed: no Elo rating, no series probability, no
pennant or World Series probability, no Brier and no calibration bin. Every
rule below was written before any such number existed, so none of it was
chosen after seeing one.

## 1. Why

Two owner answers of 2026-10-01, recorded in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`:

- **INT-A2 (b)** under 'links and postseason betting': postseason odds on
  /betting/ come from a registered bracket-state simulator with its own
  registry row and a daily forward record, labelled implied, with no market.
  The answer named the 2027 postseason.
- **Q901-1 (c)** under 'the overnight writers' questions, batch 3': build a
  series-by-series simulator now. This brings INT-A2's simulator forward to
  the 2026 postseason now under way; the 2027 forward record then continues.

The problem it answers (Part 8 intensity lane, finding F1): the season
simulator behind the Futures panel (`playoff_odds_sim`, `proj_current.py`
`simulate_playoffs` and `_bracket_once`) reads the gameType R schedule only
and plays the bracket from final standings, so from the first postseason game
it republishes pre-bracket odds. Since 547cdd08 the Futures panel and the
Franchise ODDS section say so in one line, the end-of-season stamp:
"As of the end of the regular season (2026-10-01): postseason results are not
in these odds." (`proj_export.futures_as_of_note`). This gate registers the
simulator that replaces that stamp for the Pennant and World Series columns.

## 2. Disclosed reads before this registration

Read to write this file, and nothing else of the kind:

- the served `data/futures.json` top level and its first club row (the season
  simulator's own LAD row, `pennantPct` and `wsPct` as served on 2026-10-01),
  and its `ledger` block (19 entries, 0 resolved);
- the served `data/betting.json` top level and its one postseason card (game
  849844, NL Wild Card Series, `model.p_home` as served), to learn the key
  paths in section 3.1;
- the `benchmarks.tiers.elo_literature` block of `data/betting_model_eval.json`
  (its config, n and Brier on regular-season games) and
  `tools/betting_elo.py`, for the constants in section 3.2;
- the Scores plan (`part8/scores/SCORES_PLAN.md`, sections 1.6, 2.1, 4, 5.2
  and 8.5, and `data_sources.md` 1.2 and 1.3) for how the bracket is read;
- the intensity lane (`part8/intensity_index.md` 4.2 and its draft 5m), which
  sketched the same construction for a Postseason tab that Part 8 8.D row 8
  then dropped.

No postseason result was related to any probability. No Elo rating was
computed for any club. No dark betting column was read.

## 3. Inputs

### 3.1 Game probability where the board prices the game

For a scheduled postseason game that is not yet final, the simulator uses the
served `betting_game_prob` number when, and only when, every condition holds:

1. the served board written by the same build (`data/betting.json`, the
   `team_bets` list) carries a card whose `game_pk` equals the game's `gamePk`;
2. the card's `game_type` is F, D, L or W (the INT-A1 scope of
   `docs/diamond-betting.md` 8a);
3. the card's `home.org` and `away.org` equal the game's host and visitor as
   the bracket resolves them through `trades.canonical_org_from_id` (a
   placeholder club such as "ATL/PHI" never matches);
4. `model.p_home` is a finite number strictly between 0 and 1.

The value is taken verbatim as P(host wins this game). It is never
recalibrated, shrunk, blended or adjusted (`SERVE_PROB_CALIBRATION` and
`SERVE_RUN_DISPERSION` stay False and are not read). The card's
`postseason_label` ("never graded on a postseason game") rides into the day's
record beside the number. A game that fails any condition falls to 3.2, and
the record names the condition that failed.

The board prices only the games on its own slate window, so in practice the
next game or two of a series reads the board and every later game reads the
prior.

### 3.2 The strength prior, for every other game

The literature Elo of `tools/betting_elo.py`, with zero parameters touched by
this repository's data:

- base rating 1500, K = 4, home advantage 24 Elo points
  (`LITERATURE_K`, `LITERATURE_HOME_ADV_ELO`, `BASE_RATING`, `:40-42`);
- ratings are `final_ratings(games)` (`:85`) over the 2026 regular-season
  finals that `betting_model.completed_games()` returns (gameType R only;
  postseason scores never enter it, `docs/diamond-betting.md` 8a);
- the walk runs once, at the build's first run, and the ratings are frozen
  into the record's header with the count of games walked and the SHA-256 of
  the sorted game list. Every later day reuses the frozen header; a
  postseason result never moves a rating. A club missing from the walk is a
  crash (section 9).

The Elo update already carries the 24-point home term, so a rating is a
neutral-site strength. A game's prior is

    P(host wins) = 1 / (1 + 10 ^ (-(R_host - R_visitor + 24) / 400))

and a game at a neutral site, if MLB ever schedules one, drops the 24. At equal
ratings this gives the host 1 / (1 + 10 ^ (-0.06)), about 0.5345.

This reads the benchmark's construction, not its served tier: the per-game
Elo probabilities in `data/betting_model_eval.json` stay a validation ladder
tier that no price, slot or record row reads. BRACKET_SIM_BUILD amends the
`betting_elo_benchmark` row's surface text to name this one consumer.

### 3.3 The bracket state

Read exactly as the Scores plan reads it, through two StatsAPI calls per run:

- `/api/v1/schedule/postseason/series?sportId=1&season=2026`: the eleven
  series `F_1` to `F_4`, `D_1` to `D_4`, `L_1`, `L_2` and `W_1`, every
  scheduled game including if-necessary ones, and MLB's placeholders
  ("HOU/CWS", "NL Lower Seed", "Lower Seed League Champion"), which never
  resolve to a club;
- `/api/v1/schedule` with `gameType=F,D,L,W` and `hydrate=team,seriesStatus`
  over the season's postseason dates: per game `gamePk`, `officialDate`,
  `gameDate`, `status.codedGameState`, `teams.{home,away}.team.id`, `score`,
  `isWinner`, `seriesGameNumber`, `gamesInSeries`, `ifNecessary`, and
  `seriesStatus {wins, losses, isOver, winningTeam, losingTeam}`.

A game counts as played only when `codedGameState` is F or O (a postponed or
cancelled game is abstract Final but is not played; Scores plan 1.2 and
`data_sources.md` 1.2). A suspended or in-progress game counts as unplayed. A
series is decided when its winner reaches the round's requirement or
`seriesStatus.isOver` is true on its clinching game. MLB deletes an unneeded
if-necessary game from the schedule rather than marking it (Scores plan 8.5
rule 8); the simulator never needs it, because a decided series is not
simulated.

Clubs resolve by StatsAPI team id through `trades.canonical_org_from_id`.

### 3.4 Seeds

Seeds are read off the posted bracket: the two clubs with byes in each league
are seeds 1 and 2, the Wild Card Series hosts are 3 and 4, their visitors 6
and 5, told apart by the pairing rule (3 hosts 6, 4 hosts 5; seed 1 meets the
4/5 winner and seed 2 the 3/6 winner, with no reseeding). The build checks
them against the final 2026 standings (division winners by
`franchise_export.division_champions`, wild cards by record); any disagreement
is a crash.

## 4. Formats and home field

The 2026 format (the one `proj_current._bracket_once` documents):

| Round | gameType | Format | Host order |
|---|---|---|---|
| Wild Card Series | F | best of 3 | every game at the higher seed |
| Division Series | D | best of 5 | 2-2-1: the higher seed hosts games 1, 2 and 5 |
| League Championship Series | L | best of 7 | 2-3-2: the higher seed hosts games 1, 2, 6 and 7 |
| World Series | W | best of 7 | 2-3-2: the club with the better regular-season winning percentage hosts games 1, 2, 6 and 7 |

Rules, in order:

1. **The posted host wins.** Whenever StatsAPI lists a game with both clubs
   resolved, its `teams.home` is the host, whatever the table says. The
   record logs any posted host that disagrees with the table.
2. **Otherwise the table.** In the LCS the higher seed hosts. The season
   simulator gives the LCS to the better record (`proj_current.py:569`); the
   two rules can differ when a wild card out-wins the other bracket's division
   winner, and this simulator follows the seed rule until a host is posted.
3. **A World Series record tie.** When two possible pennant winners finished
   with the same winning percentage, MLB's tiebreak is not modelled: each
   club takes home field with weight one half, and the record says so.
   Posting replaces the rule (rule 1).

## 5. The computation

Exact, with no random draws, so there is no seed and no simulation error.

- **A series.** From the current wins (a, b) the simulator walks every
  remaining game in order: game k = a + b + 1 takes its host from section 4
  and its probability from 3.1 or 3.2; the walk stops when either club
  reaches the round's requirement (2, 3 or 4). P(club wins the series) is the
  sum over the walk's terminal states.
- **The bracket.** Each slot's occupant is a distribution over clubs. The two
  sides of a series come from disjoint sub-brackets, so P(X wins round r) is
  the sum over possible opponents Y of P(X holds its slot) x P(Y holds the
  other) x P(X beats Y from the series' current state). A decided series
  contributes its winner with probability 1.
- **State changes.** The simulator conditions on every played game, so a
  game won inside a series moves its odds at the next run, and a completed
  series moves the bracket. It runs once a day (section 6.2), so the served
  odds change the morning after each game.

## 6. Outputs

### 6.1 Per club, per day

For each of the twelve postseason clubs: its seed, its league, the round it is
in, and P(win each remaining round): `adv.F` (Wild Card clubs only), `adv.D`
(reaches the LCS), `adv.L` (the pennant, served as `pennant_pct`) and `adv.W`
(the title, served as `ws_pct`). A round already won reads exactly 1, an
eliminated club reads exactly 0 in every later round, and a club outside the
postseason reads 0 for both served columns. Stored to six decimals; printed
as a percentage to one decimal, rounded to nearest, as the Futures panel
prints its own.

Every served number carries the label **"implied, no market"** and its as-of
date. No key named `pennants` or `titles` is emitted (the Franchise writer's
`FORBIDDEN_KEYS`, `franchise_export.py:108-109`).

### 6.2 When it runs

Inside the nightly pipeline, as one isolated step after the betting export
(it reads the board that export wrote) and after `write_futures`, never as a
scheduled task of its own. On the box that is the 03:10 ET nightly. The as-of
date is the America/New_York calendar date of the run.

### 6.3 Consistency checks, every run

Before anything is written: P(title) sums to 1 over the clubs within 1e-9;
P(pennant) sums to 1 per league within 1e-9; for each round, P(win round)
sums to the number of that round's series (per league 2, 2 and 1, and 1 for
the World Series); each club's probabilities never rise from one round to
the next; decided clubs sit at exactly 0 or 1; every value is finite. A
failure is a crash (section 9).

## 7. The daily forward record

### 7.1 What is frozen

One entry per as-of date and machine, written first-write-wins and never
edited: `as_of`, `generated_at`, `machine` (`box` or `local`),
`method_version` (`bracket_v1`), the bracket state (per series: round, clubs
or placeholders, wins, decided flag, winner), the input of every game the
computation used (game_pk or hypothetical slot, host, source `board` with the
board's `generated_at`, or `prior` with the reason the board was not used,
and the probability), the per-club outputs of 6.1, the 6.3 check results,
`late` (6.2: true when any postseason game of the as-of date had begun at
`generated_at`), the SHA-256 of the entry's canonical bytes and the previous
entry's hash. A same-day re-run writes nothing to the record, and the page
serves the day's frozen entry, so the page never shows a number the record
does not hold. A missed date stays missing: no entry is ever written later for
an earlier date.

The header, written once at the first run: the frozen Elo ratings and their
game count and hash (3.2), the constants of sections 3 and 4, and
**`decided_at_start`**, the series already decided when the record began
(with the 2026 Wild Card Series scheduled 2026-09-29 to 2026-10-01, those four
series will be decided on any first run from 2026-10-02 on).

### 7.2 Where it lives

The record starts the day the build first runs. The source of truth is
`.cache/bracket_sim/record.json` on the machine that writes it, for the
reason `proj_export.py:3252-3265` gives for the futures ledger: the box's
nightly runs `git checkout -- .` before every pipeline, so an accruing file
inside `data/` that is tracked is reverted every night (what killed the first
public betting record), while `.cache/` escapes the checkout and is on the
backup list. Each run re-renders the whole record to
`data/bracket_sim_record.json` (gitignored, published by the nightly rsync),
so every day's entry is public the morning it is frozen and its hash chain can
be checked by anyone holding an earlier copy. At the one look (section 10)
the scorer commits the full record, verified against its hash chain, as the
tracked artifact `docs/betting-2026-10/bracket_sim_record_2026.json`, in the
same commit as the eval artifact. Owner question BS-1 asks whether git should
witness each day instead.

The box's entries are the served record. Entries a local run wrote on dates
before the box's first entry (the build's own first run, before the owner
pushes it) are kept and labelled `local`; for each date the scorer reads the
box entry when one exists, else the local one, and says which.

The Futures ledger (`.cache/futures/ledger.json`) keeps recording the season
simulator's own numbers and never this simulator's.

## 8. The serve rule

From the first nightly that carries the build, while the 2026 postseason is
undecided and the latest entry is good:

- **Futures panel on /betting/** (`assets/betting.js` `renderFutures`): the
  Pennant and World Series cells read this simulator's `pennant_pct` and
  `ws_pct` for every club, headed "(implied, no market)", with one line above
  the table: "Pennant and World Series: implied by the postseason bracket
  simulator as of <date>, no market." Below it, a postseason table: club,
  seed, series now, P(win this round), P(reach the LCS), Pennant, World
  Series. Division, Playoffs, Bye, Proj W and Win band keep the end-of-season
  stamp, reworded to name only those columns. The WS interval cell prints a
  dash for these rows (exact computation, no simulation error) and the Model
  price (implied) cell prints a dash (section 11; owner question BS-3).
- **Franchise ODDS section** (`assets/franchise.js` `secOdds`, fed by
  `franchise_export`): the Pennant tile and its World Series line read this
  simulator with the same label and date and the verdict chip of the
  `postseason_bracket_sim` row; the Playoffs tile, its division and bye
  lines, and Projected wins keep the stamp and the `playoff_odds_sim` chip.
- A flag, `SERVE_BRACKET_SIM`, turns both off and restores today's panel and
  section byte for byte. When the build lands by 2026-10-03 it lands with the
  flag True (the owner decided to serve); if it cannot land by then it lands
  only after the fWAR epoch's step Z entry, under the same rule, and never in
  the gap between.
- After the World Series the served entry is the final one (the champion at
  1); the columns return to the season simulator, with its stamp, when the
  next season's first regular-season build runs.

Nothing else changes: `/projections/` team outlook keeps the season simulator,
and section 12 lists where these numbers never go.

## 9. The crash protocol

A crash is any of: a StatsAPI call fails or does not parse; seeds fail 3.4; a
posted club does not resolve to one of the 30 clubs; the Elo walk lacks a
club; a 6.3 check fails; the record's write guard refuses (an entry shorter,
edited, or out of order). On a crash:

1. No probability is written for the date. A `crash` entry (as-of date,
   machine, reason, no numbers) is appended, so the gap is visible in the
   record.
2. The step runs inside its own try and files
   `_record_ingest("bracket_sim", False, 0, reason)`, so the nightly prints a
   red row and carries on; no other export waits on it.
3. The page shows the last good entry with its own as-of date only when no
   game has been played since that entry was frozen; otherwise the Pennant and
   World Series columns go back to the end-of-season stamp with the sentence
   "The postseason odds did not update on <date>."
4. A repair may not change any number the method produces from stored
   inputs: every stored entry, recomputed from its own recorded inputs, must
   reproduce its outputs byte for byte (the replay test). A change that fails
   the replay is a new method version, registered by amendment to this file
   before it serves; the pass rule reads `bracket_v1` entries only, and later
   versions are reported beside them.
5. Never a back-fill, never a stale bracket read from a cache older than the
   last played game, never a guessed host.

## 10. The one look

The 2026 record is scored exactly once, by a scorer that refuses any other
date and refuses a second run, on the first date that is:

- at least two days after the officialDate of the World Series' final game;
- on or after the fWAR epoch's step Z entry
  (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9), because the look
  writes an artifact under `data/`;
- not a registered look date of any `docs/*GATE*.md` or of the orchestrator's
  calendar (among them 2026-11-02, 2026-11-06, 2026-11-13, 2026-11-20 and
  2026-12-01).

Before the look, nobody computes or publishes a Brier, a calibration bin, a
hit count ("favourites won x of y"), a log loss or any comparison of these
probabilities with series results, on any page, commit message, report or
note; the page and the record state counts only (days logged, crash days,
series decided, 0 scored). An early look disqualifies the 2026 record as the
basis of section 11's pass rule, and 2027 serving then waits on the owner.

### 10.1 What the look computes

The scored unit is a pair (admissible entry, club, round) where the round's
outcome for that club was not already determined at the entry's freeze. An
entry is admissible when it is `bracket_v1`, not `late` and not a crash.

- **Brier per round**: for each of F, D, L and W, the mean of (p - y)^2 over
  its pairs, where y is 1 when the club won that round's series; with n
  entries, n pairs and n distinct series beside it.
- **The coin bracket**: the same state, the same formats and hosts, every
  unplayed game at 0.5, scored on the identical pairs; per round and pooled.
- **Pooled Brier** over every pair of every round, and the difference from
  the coin bracket.
- **Calibration table**: ten equal-width bins of p over all pairs pooled, with
  n, mean p and the observed rate in each.

Daily entries share series and outcomes, so these numbers are not independent
draws and no p-value or interval is reported for them; about eleven series a
year cannot resolve skill of the size at stake, and the look says so.

Output: `data/bracket_sim_eval.json`, and the record committed as 7.2 says.

## 11. The pass rule for serving in 2027

The simulator stays served into the 2027 postseason when the 2026 record
shows all four:

1. **Integrity.** The hash chain verifies end to end; no entry was edited;
   every date from the first entry to the World Series final on which a
   postseason game was scheduled has an admissible entry, except at most two
   dates, each covered by a crash entry.
2. **Consistency.** Every admissible entry passed 6.3.
3. **Not worse than a coin.** The pooled Brier is no more than 0.020 above the
   coin bracket's pooled Brier on the same pairs. This is a guard against a
   broken build (a host or sign error moves it by more), not a skill claim.
4. **One look.** No early look (section 10).

A pass keeps it served with the same label and adds no claim: the verdict
becomes `provisional`, never `validated`, and the page quotes the 2026 numbers
only from the eval artifact. A fail, or no look by 2027-02-15, keeps the
simulator running in 2027 with its forward record but unserved: the 2027
Futures panel carries the end-of-season stamp until the owner decides.

## 12. Bans

- Never a market price: no futures or outright odds are captured for this, no
  de-vigged number sits beside it, and no American, decimal or fractional
  price is derived from these probabilities (owner question BS-3).
- Never a slot, a record row, a shadow or paper ledger row, a calibration
  ledger row or a sub-ledger row from these numbers.
- Never an edge, an expected value, a Kelly figure, a value flag or "fair".
- Never an input to the betting pricer or to any other model, and never on a
  priced cell or a game card.
- Never a dark betting column (the 5c to 5l families, the intensity block, or
  any management figure) as an input.
- Never on the Scores bracket: it stays without odds (Part 8 8.D row 8; Scores
  plan 1.6 and 5.2). No betting Postseason tab is built.
- Never on `/projections/`, the DFS or fantasy boards, or PROSPX.

## 13. The registry row

Lands in BRACKET_SIM_BUILD, in the commit that first serves the columns
(a registry row never lands before the surface it names), with
`MODEL_REGISTRY.md` regenerated:

| Field | Value |
|---|---|
| `model_id` | `postseason_bracket_sim` |
| `surface` | the Pennant and World Series columns and the postseason table of the Futures panel on /betting/, and the Pennant tile of the Franchise ODDS section, during the postseason only, labelled implied, no market; `data/bracket_sim.json` |
| `predicts` | per postseason club, P(win each remaining round), P(pennant) and P(World Series), from the bracket state |
| `champion` | `bracket_v1`: exact series recursion over the posted bracket; per game the served `betting_game_prob` p_home where the board prices the game, else the literature Elo (1500, K 4, 24 points home) over the 2026 regular-season finals, frozen at the first run; formats and home field per this file |
| `baseline` | the coin bracket: the same state, every unplayed game at 0.5 |
| `metric` | Brier per round and pooled, and a ten-bin calibration table, on the daily forward record, read once after the World Series (this file, sections 10 and 11) |
| `eval_artifact` | null until the look, then `data/bracket_sim_eval.json` |
| `verdict` | `unvalidated` until the look, then `provisional` whatever the outcome |
| `registration_status` | `registered, not read` |
| `notes` | the owner answers INT-A2 (b) and Q901-1 (c); evidence regular-season only (both input sources); the stamp it replaces; this file's path |

The verdict enum has four words and no "registered", so the wording rides
`registration_status`, as on `college_pitk_box_challenger`.

## 14. What the build must pin

BRACKET_SIM_BUILD adds `test_bracket_sim_registration.py` (this file's
constants, dates, label and bans, against the code), fixture tests for the
series recursion (a 2-0 Wild Card lead, a 3-3 seventh game, a decided
series), the 6.3 checks, the record's write guard and the replay test, a
fence that no slot, record, ledger or pricer path reads the payload, and a
render check of both surfaces at 1280 and 390 px in both themes. Fixtures
only: no test computes a number from the real 2026 bracket.

## 15. Owner questions (defaults applied in this file)

- **BS-1, where the record is witnessed.** (a) Default: `.cache` source of
  truth, the public `data/bracket_sim_record.json` re-rendered daily with a
  hash chain, and the whole record committed under `docs/` at the look.
  (b) Also commit each day's published entry under
  `docs/betting-2026-10/bracket_sim_record/` the same day: git witnesses every
  day, but it needs a writer every day, including through the epoch gap.
  (c) A tracked file under `data/` appended by the nightly: rejected, because
  the box's `git checkout -- .` reverts it every night.
- **BS-2, the strength prior.** (a) Default: the literature Elo of 3.2, zero
  fitted parameters. (b) The betting pricer itself on a hypothetical game with
  rotation-average starters: one model for every game, but it extends a
  pricer graded on no postseason game to games it was never asked to price.
  (c) A regressed Pythagorean record with log5: simple, but its regression
  constant is a new choice no artifact supports.
- **BS-3, the Model price (implied) column in October.** (a) Default: a dash
  while these columns serve, since section 12 bans any price from these
  numbers. (b) Keep the season simulator's price: it would sit beside a World
  Series column it no longer matches. (c) Derive the price from this
  simulator: lifts the ban in section 12 for this one column.

## 16. Build record (BRACKET_SIM_BUILD, 2026-10-01)

Appended by the build. No rule above changes.

- **Code.** `bracket_sim.py`: a pure core (`parse_bracket`, `derive_seeds`,
  `build_structure`, `resolve_inputs`, `compute`, `outputs_from`) and `run()`,
  the nightly step. It runs as step `d10f` of `run_monthly.py`, after 9e (the
  board export) and d9 (`write_futures`) and before 6b7d (the Franchise board,
  which reads its payload); a crash files
  `_record_ingest("bracket_sim", False, 0, reason)` and `bracket_sim` is on
  `SCHEDULED_EXPORTS`.
- **Flag.** `bracket_sim.SERVE_BRACKET_SIM = True`, landed 2026-10-01, inside
  the window of section 8. False keeps the record running and restores both
  surfaces byte for byte.
- **Paths.** The record is `.cache/bracket_sim/record.json`. Its derived copy
  `data/bracket_sim_record.json` and the payload `data/bracket_sim.json` are
  gitignored and published by the nightly rsync, like `data/futures.json`. The
  two StatsAPI responses of each run are kept as receipts under
  `.cache/bracket/<as_of>_series.json` and `<as_of>_schedule.json` with
  `fetched_at`, and are never read back as a source.
- **Choices where this file was silent** (defaults, recorded so the scorer can
  read them):
  1. `machine` is `box` when the nightly shell's `EEPHUS_SKIP_INPROC_BUILD=1` is
     set (or `EEPHUS_MACHINE=box`), else `local`.
  2. The schedule call's window is `<season>-09-15` to `<season>-11-30`.
  3. A posted team that does not resolve through `canonical_org_from_id` is a
     placeholder only when its name carries a slash or one of seed, champion,
     winner, TBD or TBA; any other unresolved club is a crash (section 9).
  4. Seed 3 is the Wild Card host that is a division champion; seed 1 is the
     bye whose posted Division Series opponent, or placeholder such as
     "ATL/PHI", is the 4/5 series. The standings check is exact on winning
     percentage: equal records pass, since MLB's tiebreak is not modelled.
  5. A neutral site is a posted game whose venue id differs from the posted
     host's home venue id.
  6. `late` is true when a game of the as-of officialDate has a codedGameState
     other than S, P, D or C at `generated_at`.
  7. On a crash, "no game played since the last good entry" is read from the
     played game ids when the bracket was fetched, else from the last good
     entry's `next_game_start`.
  8. Once the World Series is decided the step writes no further entry and
     serves the final one. A run in a season other than the record's writes no
     entry: a new season's record is a later registration.
  9. Outputs are stored to six decimals; the 6.3 checks run on the unrounded
     values and are stored with the entry, and the replay test compares the
     canonical bytes of the recomputed outputs and checks.
- **Where the task text differed from this file.** The build task asked for a
  seeded simulation count and a tracked `data/bracket_sim_record.json`. This
  file registers an exact computation with no seed (section 5) and a gitignored
  derived copy (section 7.2, BS-1 (a)); the build follows this file.
