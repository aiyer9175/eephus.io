# /fantasy/: Redraft, Dynasty and DFS

Module doc for the fantasy surfaces. They were one page with nine tabs until
2026-08-05, three pages until 2026-08-07, and are one page with three
sub-modules now. Both moves were deliberate and the current shape is the one
that satisfies both sets of reasons, so both are written down here.

## Why it split, and why the merge had to keep the split's shape

`/fantasy/` carried nine tabs for three different readers. A dynasty manager and
a DFS player share a data pipeline and nothing else: one is buying a 2029 ETA,
the other is buying tonight. The split named three defects:

1. one scoring selector governing surfaces it could not affect,
2. one flat hash namespace for three vocabularies,
3. the dynasty board buried behind seven rest-of-season tabs.

Owner decision 10 of the 2026-08-07 program is a FULL MERGE back into one
`/fantasy/` module. A merge that put nine tabs back in one row would have
brought all three defects back with it. So the merge is a merge of PAGES, not
of clients: one document, one nav entry, one masthead, and inside it three
sub-modules that each keep their own section nav, their own control slot and
their own hash namespace. The scoring selector still renders only on the three
Redraft tabs that read it, the hash is namespaced rather than flat, and the
dynasty board is one click from the top of the page rather than eight.

The split is still a client split. It is still not a second corpus.

## The shape, and the three things that stop being safe in one document

| surface | what it is | client |
|---|---|---|
| `/fantasy/` | the page | `assets/fantasy-hub.js` (coordinator) |
| `#m=redraft` | rest of season and daily | `assets/redraft.js` |
| `#m=dynasty` | keepers and prospects | `assets/dynasty.js` |
| `#m=dfs` | tonight's slate | `assets/dfs.js` |
| `/redraft/`, `/dynasty/`, `/dfs/` | hash-preserving redirect stubs | none |

**Mount ids.** Every client resolves its root, banner, control slot and section
nav through a candidate list that ends at the pre-split shared id
(`fantasy-app-root`, `fantasy-banner`, `fantasy-scoring`,
`data-fantasysection`). Across three pages that fallback was harmless
tolerance. In one document it is a TRIPLE-MOUNT: all three clients resolve to
the same node, all three paint into it, and the last one to finish loading
wins. Nothing about that failure looks like a bug in any one client. The
combined shell therefore emits per-module ids and none of the shared ones, and
`test_fantasy_split` asserts the absence rather than trusting it.

**The address bar.** Each client owns `#section=` over its own vocabulary and
rewrote `location.hash` from its own state, with its own `hashchange` listener.
Three of those in one window is three writers over one string.
`assets/fantasy-hub.js` owns the hash now: it is
`#m=<module>&<that module's own hash>`, the clients read and write only their
own half through the host, and only the ACTIVE module's half is in the URL.
Each client keeps its whole router; it just stops reaching for `location` and
`window` directly. With no host on the page every one of those calls falls back
to the plain browser one, which is not dead code: `test_fantasy_split` drives
`redraft.js` standalone in a JS engine against the frozen `assets/fantasy.js`.

**The payload.** `data/fantasy.json` is 576KB and `data/dfs.json` is 253KB.
Only the active client is downloaded, on first activation, off the `data-src`
stamps on the module bar, so a reader who opens the ROS board pays for neither
of the other two. The corpus load goes through one memoized loader, so Redraft
and Dynasty together cost one download and one parse rather than two.

## Every legacy hash still lands somewhere real

Four generations of link address these boards: the pre-split `/fantasy/` page
(nine sections), the aliases that page already accepted, the three split pages,
and the `#player=` card hash. The coordinator resolves an un-namespaced hash by
looking the section up in a table of every name any of the three has ever
carried. That works only because the three vocabularies are DISJOINT, which is
worth knowing before anyone adds a section name to one of them.

* redraft: `streamers`, `two_start`, `ros_sp`, `ros_rp`, `ros_hitter`,
  `buysell`, `closers`
* dynasty: `dynasty`, `callups`, `keeper`, plus the alias `board`
* dfs: `slate`, `value`, `stacks`, `optimizer`, plus the aliases `pitchers`,
  `hitters` (to `slate`) and `salaries` (to `value`, because the salary import
  form lives on the value board)

The table lookup uses `hasOwnProperty`: `#section=constructor` is inherited off
`Object.prototype`, truthy, and a plain lookup would have resolved it to a
module. A section nobody owns lands on the default module (Redraft) rather than
on a blank page, and the client then refuses it and rewrites the address bar to
its own default. Everything else in the hash rides across verbatim, because the
module's own client is what canonicalizes an alias and it cannot do that if the
coordinator ate it. `test_fantasy_split` enumerates every one of these.

`/redraft/`, `/dynasty/` and `/dfs/` are stubs on the `/teams/` template with
one addition: they carry the incoming hash across, so
`/redraft/#section=ros_sp&sys=sabr` lands on
`/fantasy/#m=redraft&section=ros_sp&sys=sabr` rather than on the module's
default tab. All four dirs stay in `deploy/publish_paths.txt`; a redirect that
does not ship is a 404.

## One exporter, three clients

`fantasy_export.py` still builds `data/fantasy.json` on one corpus. That build is
the expensive, memory-budgeted part of the pipeline (run_monthly step 6b6, with
the cheap schedule-only refresh at 9d), and nothing about it changed here.

| sub-module | client | payload | sections |
|---|---|---|---|
| Dynasty | `assets/dynasty.js` | `data/fantasy.json` | `dynasty`, `callup_watch` |
| Redraft | `assets/redraft.js` | `data/fantasy.json` | `daily_streamers`, `two_start`, `ros_sp`, `ros_rp`, `ros_hitter`, `buy_low`, `sell_high`, `closer_depth` |
| DFS | `assets/dfs.js` | `data/dfs.json` | the daily slate (`dfs_export.py`) |

`assets/fantasy.js` stays in the tree, frozen. It is the pre-split parity
reference that `test_fantasy_split` drives `redraft.js` against, and no page
loads it.

## Shell contract

The shell is `build_site.build_fantasy()`, one panel per sub-module through
`_fantasy_panel()`. Each client resolves its mount points through a candidate
list, and the shell gives it only the FIRST candidate:

| client | root | banner | top bar | section attribute |
|---|---|---|---|---|
| dynasty | `#dynasty-app-root` | `#dynasty-banner` | `#dynasty-scoring` holds the LENS control, on the board tab only | `data-dynastysection` |
| redraft | `#redraft-app-root` | `#redraft-banner` | `#redraft-scoring` holds the league-format selector, on the three ROS tabs only | `data-redraftsection` |
| dfs | `#dfs-app-root` | `#dfs-banner` | none, so the contest-format selector renders inline at the top of the section | `data-dfssection` |

The second candidate in each list is the fantasy-era shared id. It is still in
the clients so they mount on an older shell, and it must never appear in this
one. See the triple-mount note above.

The bar is a SLOT, not a fixture. Both clients empty it on the tabs their
control cannot move, and the emptied slot is removed from layout by a `:empty`
rule rather than left as a 10px band above the nav.

The nav attribute values ARE the canonical section names, because `syncTabs`
compares them directly: a client that canonicalizes a different string renders
the right board under a nav announcing the wrong tab.

* dynasty: `dynasty` (the board), `callups`, `keeper`
* redraft: `streamers`, `two_start`, `ros_sp`, `ros_rp`, `ros_hitter`, `buysell`, `closers`
* dfs: `slate`, `value`, `stacks`, `optimizer`

Each client also accepts pre-split aliases in the hash so an older link still
lands somewhere real: `board` maps to `dynasty`; `pitchers` and `hitters` map to
`slate`; `salaries` maps to `value` (the salary import form lives on the value
board, which is the one surface that is meaningless without it).

`test_fantasy_split.py` asserts every nav attribute value is a section its
client knows, that no client is a `<script>` tag on the shell (they ride
`data-src` and the coordinator injects one), and that `diamond-config.js` and
the player card are on the page before any client runs. It reads the BUILDER,
not the generated file: these pins used to read `dynasty/index.html` and skip
when it was absent, and a pin that skips on a fresh checkout is green for the
wrong reason.

Every client tolerates an absent payload and an absent section: it renders a
loud note saying what is missing, never a blank page.

## The league-format selector, and where it is allowed to appear

2026-08-07. The selector was reported as broken. It is not: switching to SABR
re-ranks 230 of the 250 rest-of-season starters, and switching to 5x5 re-ranks
342 of the 350 hitters. What was broken was where it rendered. The shell
reserves one bar above the section nav, `redraft.js` filled it once at boot, and
it then sat over all seven tabs, including the default landing tab.

Only three tabs read `S.system`: ROS SP, ROS RP and ROS Hitters. Daily Streamers
and Two-Start ride `per_start_fgp` and `total_fgp` off the server, Buy / Sell
sorts on the expected-stat gap, and the Closer Grid ranks on gmLI. A reader
landing on Daily Streamers therefore met a four-button control that did nothing
to the board under it, which is indistinguishable from a control that is dead.

The bar now renders on those three tabs and is emptied on the other four.
`test_fantasy_split.py` pins both halves per tab.

One thing the scoping does NOT fix, because it is not a defect: FanGraphs Points
and SABR Points produce the same hitter board. `fantasy.json` carries a single
`scoring.hitter` dict because the two Ottoneu formats differ only in how
PITCHERS are scored. ROS Hitters says that in a line above the board, and the
player card shows the two identical totals side by side, so a reader who
switches formats there knows why nothing moved. The two category formats do
re-rank the hitters.

## The player card

`assets/fantasy-card.js`, loaded by the `/fantasy/` shell before any client
runs. It is an overlay, addressed as `#player=<mlbam>` inside the host module's
own half of the hash, so a card is shareable and the browser Back button closes
it.

It is reachable from all THREE sub-modules now, and the third one is what the
merge bought. The card is a lookup into `data/fantasy.json`, which the DFS
client does not read and must not start reading: its sidecar is the slate. On
one page the coordinator already holds that corpus for the other two modules,
so a DFS row can open the card for the cost of a load that is either already
done or is taken once, on the first card, and never at all for a reader who
opens none. A DFS card carries no four-format league score line: that port
lives in `assets/redraft.js`, a copy here would be a third implementation
nobody is comparing, and a season points total is not what a DFS reader came
for.

It is not a client. It fetches no corpus and owns no payload: the host attaches
with accessors (`payload()`, `links()`, and optionally `scoreLine(rec)` and
`keeperRound(rank)`) and every block is a lookup into the payload already in the
browser. There is no new exporter and no page-per-player build.

| block | source |
|---|---|
| identity, eligibility, two-way mark | the player records in `players` |
| four-format score line | the HOST, through `scoreLine` |
| projected line | `ros`, with the exporter's own `_est` legs marked |
| HEM+ / SEM+ / REM+ / gmLI | `skill`, wrapped in glossary terms |
| luck gap, buy / sell, Swing+ trend | `skill` plus `buy_low` / `sell_high` membership |
| upcoming starts | `daily_streamers` rows, then `two_start` legs |
| bullpen role | the index into `closer_depth[org]` |
| dynasty block | the `dynasty` row, plus `callup_watch` membership |
| tonight's line | `data/dfs.json`, the one lazy fetch |
| Full MLB card | `player_links.byMlbam` |

Two rules it inherits. The score line is NOT reimplemented here: the port lives
in `assets/redraft.js`, which `test_fantasy_split.py` drives against the frozen
`assets/fantasy.js` in a JS engine, and a second copy would be a third
implementation nobody is comparing. And a category value is a position in a
POOL, so a player the served board does not carry gets no roto row rather than a
z-score against a pool of one.

`data/dfs.json` is fetched once per session, on the first card a reader opens,
and cached whatever the outcome. A slate that will not load is a note on that
block, because a reader who knows the player is on tonight's slate and sees
nothing would read the silence as "not playing". A slate dated before the
viewer's own today is labelled with its date instead of "Tonight".

Every name on both boards now opens the card rather than linking straight out.
That resolves for every row, where the outbound link only resolved for the 1,234
of 1,249 players `player_links` covers, and the card carries the outbound link
itself.

## The one eFV basis

Every eFV number on the Dynasty board is the served `efv` field, which
`fantasy_export._dynasty_prospects` produced through
`efv_board_scale.board_value`. The client does no grade arithmetic at all: no
scale, no quantile, no blend, only rounding to nearest. `test_fantasy_split.py`
greps all three clients AND the player card for a raw grade field or arithmetic
on a served grade and fails on either. This is the rule that `/fantasy/` broke in July, when
Call-up Watch read `xfv_grade` while the Dynasty column read the retired
`xfv_grade_quantile` and one prospect carried two grades a tab apart.

Display conventions, unchanged: eFV and plus-stats round to nearest, scouting
FV grades display as a ceiling.

## Keeper value calculator (Dynasty)

Pure client arithmetic over the served rank, persisted to `localStorage` and
sent nowhere. Four inputs: teams, your first-round slot, the round the keeper
costs, your contention window.

```
pick you spend keeping in round R = teams * (R - 1) + your slot
worth it when                     = that pick number >= his board rank
break-even round                  = ceil((rank - slot) / teams) + 1, floored at 1
```

There is deliberately no dollar valuation. Translating a dynasty rank into
auction dollars needs league-specific inflation data the site does not have, and
inventing that curve is exactly the kind of unmeasured constant the shop keeps a
loss ledger to avoid. The tool works in rank space and says so on the page.

The contend and rebuild lenses are presets over the served columns (ETA ascending
and star odds descending). They re-sort. They do not re-rank: the diamond chip
always shows the model rank.

## The DFS slate and dfs_export.py

`dfs_export.py` writes `data/dfs.json`, a daily slate payload. It imports
`fantasy_export` for the frames that module already loads and never builds a
second corpus.

Inputs:

* slate and probables: `fantasy_schedule.fetch_probables` (StatsAPI, one day)
* per-player counting vectors: `data/fantasy.json`
* opponent context: team Offense+ and Bullpen+ from `fantasy_export._teams_context`,
  and the opposing probable's SEM+ off the fantasy pool itself
* lineup eligibility: `data/mlb_fielding_positions.json` through
  `fantasy_export._elig_positions` (one definition of the rule, site-wide)

Re-pricing:

* Hitters. The ROS line already prices rest days, so dividing by the remaining
  team games gives an unconditional per-game line, which is the wrong number for
  a lineup slot. The two are split instead: `start_rate = min(1, pa_per_team_game
  / 4.15)` and the line is scaled to `pa_per_team_game / start_rate` plate
  appearances. An everyday bat comes out at a full start and rate 1.0; a
  strong-side platoon comes out at the same 4.15-PA game with a rate near 0.6.
* Starters. The ROS vector carries a projected start count, so the per-start
  line is a division. The matchup enters on the ALLOWED side (hits, earned runs,
  home runs), not as a blanket multiplier on the total: a weak opponent does not
  hand a pitcher strikeouts or innings.
* Relievers are not on the slate. Save and hold chances are not knowable before
  first pitch.
* Park factors are neutral today. The committed artifact
  (`data/milb_park_factors.json`) covers sportIds 11 to 16, so no MLB venue
  resolves. The lookup is interface-shaped and the payload labels every row
  `park_source: "none"`, which is the honest version of a leg we cannot fill.

What is a model and what is an estimate: the skill line rides the
Gate-1-validated FA projection engine through `fantasy.json`. Per-game playing
time, the matchup multiplier and the park leg are display-layer heuristics with
published league anchors, marked in each row's `est` list and stated on the page.
No served number moves and no model gate is triggered. There is no backtest
behind the matchup multiplier yet, and the payload says that out loud.

Scoring weights for the two classic contest formats are transcribed into
`dfs_export` and published in the payload, so the reader can audit every weight
rather than trust a bundle. Complete game, shutout and no-hitter bonuses are
deliberately absent: their per-start expectation rounds to under a tenth of a
point and carrying them would imply a projection this pool does not make.

Empty days are a supported, tested path. An off day, a missing corpus, or a dead
schedule endpoint all produce a valid payload carrying `empty_reason`, and the
page renders it loudly.

## The four DFS tabs

* **Today's Slate**: the games with both probables, then the starter board, then
  the hitter board. Each board carries its own sort state, named on the control,
  because both render on one tab.
* **Value Plays**: points per thousand dollars over everyone the reader has a
  price for, with the salary import form on top. Without an import it says so
  and shows the importer rather than an empty table.
* **Stacks**: clubs ranked by the summed projection of their four best bats, with
  the arm they face and that opponent's pitching index. The page states plainly
  that this is a SUM of independent projections and that the correlation which
  makes a stack worth building is not modelled. It is a shortlist of spots, not
  a stack projection.
* **Lineup Optimizer**: the solver.

## Salaries and the optimizer

Salaries come from the user. We do not scrape or republish any contest site's
salary feed. The client reads a pasted or uploaded CSV, finds its columns by
header name, joins on a folded name key (accents folded, suffixes dropped), and
reports exactly what it could not place. The reader's own Position column wins
over our fielding-games eligibility, because his site is authoritative about
what slot a player fills there. Everything lives in `localStorage`, keyed to the
slate date so yesterday's prices cannot price today's board.

The optimizer is a greedy build plus local search. The greedy fills slots
scarcest first and reserves the cheapest legal filling of the remaining slots
before each pick, which is the difference between a solver that fills nine slots
and one that spends the cap on eight. Local search then runs single swaps to a
local optimum and pairwise swaps to escape the obvious traps.
`test_fantasy_split.py` runs it against a pool small enough to brute force, on a
fixture where the greedy build alone reaches 24 points and the true optimum is
26. If the improvement pass ever stops working, that test drops to 24.

## Diamond preview

The page ships public with "Diamond preview" labelling, one chip on one
masthead rather than three. Each client reads
`window.EEPHUS_DIAMOND` (published by `assets/diamond-config.js`, owned by the
diamond-core lane) defensively, treats a missing config as gating OFF, and caps
its boards at `previewRows` only when gating is on and the reader is not a
member. Nothing in this lane turns gating on. Public framing is "Diamond funds
the free site".

## Pipeline

`dfs_export.refresh()` belongs on the DAILY tail, next to the existing 9d
fantasy schedule refresh, and must run AFTER it (it reads the fantasy payload
that step keeps current). It is best-effort by construction and returns 0 rather
than raising.

## Slate freshness, and the two ways it was invisible

2026-08-07. DFS served the 2026-08-05 slate at full confidence: the payload
carried no `stale_slate` flag, the banner never fired, and the only sign was a
date in the corner of the header. Two independent holes produced that.

FIRST, the exporter's crash path. `refresh()` wraps `build_payload` and returned
0 from the `except` without touching the file. The keep-previous rule right
below it exists precisely so that a board we cannot replace gets STAMPED before
it is served for another day, and the one route that skipped it was the route a
crash takes. A build that raised is now converted into a `build_failed` payload
and routed through that same decision: the carried board gets `stale_slate`, the
reason, the age and the bound, and a carry past `_MAX_STALE_CARRY_DAYS` publishes
the honest empty state instead of freezing the page on an old slate.

SECOND, the client trusted the stamp. `stale_slate` only exists on the paths
that REACHED a publish decision, so a daily job that never ran at all leaves an
unstamped payload behind and nothing downstream can tell. `assets/dfs.js` now
does its own check: a `slate_date` behind the VIEWER's calendar day renders the
banner, with its own wording, because nobody decided to keep that board and the
page must not claim otherwise. Both sides of the date comparison are built from
local date parts; a bare ISO string through `new Date()` is parsed as UTC and
would fire the banner a day early every North American evening.

The header chip and the banner read the same predicate, so they cannot disagree
about whether the board is today's.

## Tests

`test_fantasy_split.py`:

1. `dfs_export` offline: empty slate, missing corpus, `refresh()` writing a valid
   payload, a stubbed slate priced end to end, the playing-time split, the
   matchup direction, the scoring tables, and doubleheader de-duplication.
2. Source contracts on all three clients: one sidecar each, no em-dashes, no
   betting copy on a fantasy surface, no local eFV basis, the Diamond flag read
   but never asserted, no salary scraping.
3. Scoring parity: `assets/fantasy.js` and `assets/redraft.js` are driven in a
   real JS engine over one fixture payload and their rendered board scores are
   compared in all four league formats. A drift in the port fails the suite
   instead of quietly re-ranking somebody's league.
4. The DFS optimizer and CSV import, driven through the shipped client.
5. The dynasty board, its lenses, and the keeper calculator's arithmetic.
