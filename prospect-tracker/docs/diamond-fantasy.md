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
| `/redraft/`, `/dynasty/`, `/dfs/` | retired addresses the 404 page forwards, hash carried (`build_site.RETIRED_ROUTES`) | none |

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

**The payload.** `data/fantasy.json` is ~585KB (561KB before the `team_next7`
bake of 2026-08-16; `test_fantasy_split` budgets it at 600KB and pins the new
section under 20KB at the 30-org worst case) and `data/dfs.json` is ~380KB.
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

`/redraft/`, `/dynasty/` and `/dfs/` were redirect stubs from 2026-08-07 to
2026-10-07. Their folders are gone now (owner answer LB-Q3): the box answers
each address with `404.html`, whose redirect map (`build_site.RETIRED_ROUTES`,
one constant beside the `/teams/` row) carries the incoming hash across the
way the stubs did, so `/redraft/#section=ros_sp&sys=sabr` lands on
`/fantasy/#m=redraft&section=ros_sp&sys=sabr` rather than on the module's
default tab. `test_fantasy_split` and `test_page_index` drive that map.

## One exporter, three clients

`fantasy_export.py` still builds `data/fantasy.json` on one corpus. That build is
the expensive, memory-budgeted part of the pipeline (run_monthly step 6b6, with
the cheap schedule-only refresh at 9d), and nothing about it changed here.

| sub-module | client | payload | sections |
|---|---|---|---|
| Dynasty | `assets/dynasty.js` | `data/fantasy.json` | `dynasty`, `callup_watch` |
| Redraft | `assets/redraft.js` | `data/fantasy.json` | `daily_streamers`, `two_start`, `ros_sp`, `ros_rp`, `ros_hitter`, `buy_low`, `sell_high`, `closer_depth` |
| DFS | `assets/dfs.js` | `data/dfs.json` | the daily slate (`dfs_export.py`) |
| the player card | `assets/fantasy-card.js` | the host's corpus | `team_next7` (2026-08-16) |

Eleven sections in `fantasy.json` as of 2026-08-16 (the ten above plus
`team_next7`). An earlier revision of this doc and the exporter docstring both
said "the 9 sections" while ten were being baked; count the keys in
`build_sections`, not a number in prose.

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

## Search and filters (2026-08-16)

Every board's data is already client-side, so filtering is a VIEW, never a
refetch and never a re-score. Each client carries its own small filter bar
(duplicated per client, the same trade the sort and card machinery already
made; a shared asset would be a fourth script tag on the shell):

* **Redraft**: name search, position chips off the served `elig` field (which
  was display-only until now) and a team dropdown, above the sort bar on the
  three ROS card boards. The SP and RP boards are all `P`, so they drop the
  chips rather than render a one-chip dead control. Buy/Sell and the Closer
  Grid take name search; a closer search keeps the WHOLE team card when the
  club or any arm matches, because a depth chart with its middle rung filtered
  out would misrepresent the pecking order. Roto values are pooled z-scores,
  so the pool scores FIRST and the filter narrows what renders; a test pins
  that a filtered board shows the same value as the unfiltered one.
* **Dynasty**: name search, org dropdown, ETA-year chips and a tier filter on
  the board; Keeper and Call-up Watch take name search (the keeper search
  narrows BEFORE the 150-row cap). The rank diamond keeps the model rank
  through any filter.
* **DFS**: name search, position (through `eligOf`, so the reader's own CSV
  positions count) and team, one bar above BOTH slate boards and on the value
  board. The OPTIMIZER POOL honors the active filters, and the panel says so:
  filtering shrinks the pool, and a filtered-out player cannot be drafted. A
  filter change resets the hitter page and invalidates a solved lineup.

URL state rides each client's existing validated-hash grammar: `q=` (percent-
encoded substring, capped at 40 chars), `pos=` and `team=` (validated against
the SERVED pool, the same rule `#sys=` follows against the served scoring
catalog), plus dynasty's `eta=` and `tier=` (a slug derived from the served
tier label). An invalid value degrades to no filter and is normalized out of
the address bar; the keys are read unconditionally, so a hash without them
clears the filter and the Back button undoes one. The coordinator's `#m=`
namespace and the legacy `#section=` table are untouched.

**DFS pagination.** The ~508-row hitter table renders its first 100 rows and a
"Show 100 more" control (the sticky-header `.mlbstats-scroll` dialect is
unchanged); filters reset the page. The pitcher board is ~30 rows and never
pages.

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
| HEM+/SEM+ season trend (2026-08-16) | `data/hitter_history.json` / `data/starter_history.json`, lazy |
| upcoming starts | `daily_streamers` rows, then `two_start` legs |
| bullpen role | the index into `closer_depth[org]` |
| next-7 schedule strip (2026-08-16) | `sections.team_next7`, baked into the corpus |
| dynasty block | the `dynasty` row, plus `callup_watch` membership |
| tonight's line | `data/dfs.json`, lazy |
| Full MLB card | `player_links.byMlbam` |

The two 2026-08-16 blocks:

* **Next-7 strip.** `fantasy_export.build_sections` bakes
  `sections.team_next7` as `{org: [{d, opp, home, opp_off, opp_bp}]}` for the
  next 7 days, off the 7-day probables fetch `_attach_schedule` used to
  DISCARD once two-start legs were derived (it now keeps a compact
  `schedule.team_sched7` view, ~9KB, and the baked section measures ~15KB at
  the 30-org worst case). Opponent context joins from the same
  `_teams_context` the streamer boards price against; an unresolvable
  opponent carries `null`, never a fabricated 100. The card renders 7 chips
  colored by opponent Offense+ (105 or tougher red, 95 or softer green,
  unmeasured neutral), in theme tokens only.
* **Season-trend sparkline.** On first card open per side, the card lazily
  fetches the committed per-season history board (the same pattern as the
  dfs.json fetch: once per session, cached whatever the outcome) and renders
  an inline-SVG HEM+/SEM+ sparkline with the artifact's own as-of date. The
  series is one point per QUALIFIED season, because that is what the artifact
  carries; there is no monthly series in any committed artifact, no game log
  and no L/R splits, and the card does not invent them. A player with fewer
  than two qualified seasons gets no block, which is the honest absence.

Two rules it inherits. The score line is NOT reimplemented here: the port lives
in `assets/redraft.js`, which `test_fantasy_split.py` drives against the frozen
`assets/fantasy.js` in a JS engine, and a second copy would be a third
implementation nobody is comparing. And a category value is a position in a
POOL, so a player the served board does not carry gets no roto row rather than a
z-score against a pool of one.

`data/dfs.json` is fetched once per session, on the first card a reader opens,
and cached whatever the outcome; the history boards follow the same rule, per
side, through one shared lazy loader (`test_fantasy_split` pins the single
fetch call site). A slate that will not load is a note on that block, because
a reader who knows the player is on tonight's slate and sees nothing would
read the silence as "not playing". A slate dated before the viewer's own today
is labelled with its date instead of "Tonight". A history that will not load
renders no trend block, because a missing sparkline claims nothing.

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

The dynasty RANKING drives on that same board grade since 2026-08-16. Until
then the blend's primary term was the retired `xfv_grade_quantile`, a scale the
site displays nowhere, while the row displayed the board grade beside it;
measured on the live board, swapping the driver with unchanged weights cut
visible adjacent inversions and lifted Spearman(rank, shown eFV) from 0.848 to
0.951 (`tools/dynasty_basis_probe.py` reproduces it). The blend weights and the
ETA-proximity decay live in the shared `dynasty_blend` module, one importable
copy for this exporter and `card_market_export.talent_score`, after the card
clone was caught decaying ETA at 0.25 against this module's 0.18.

## Keeper value calculator (Dynasty)

Pure client arithmetic over the served rank, persisted to `localStorage` and
sent nowhere. Four inputs: teams, your first-round slot, the round the keeper
costs, your contention window. The window only tags whether the ETA lands
inside it; the verdict does not read it.

The board ranks prospects only, so the verdict is for a prospects-only draft
(a farm or minors draft), and the page says so. Until 2026-09-25 it said a
round 5 keeper "costs pick 54 overall", which read as the main draft, where a
prospect goes far later than his prospect rank (M11-06). A combined MLB plus
prospect rank for the main draft is not served here.

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
* park factors: the Savant MLB park index off `fa_meta` through the venue map,
  with the MiLB table (`data/milb_park_factors.json`) behind it; every game
  labels its `park_source`, out-of-range factors are clamped and say so
* Vegas legs: game total and de-vigged implied team totals, read from the odds
  snapshots the betting module already pays for (`betting_ingest.latest_snapshot`);
  a snapshot from a different day's board is refused on first pitch, and a slate
  with no snapshot shows no total rather than an estimated one. A game that had
  already started when the snapshot was taken is refused too (2026-09-11; it
  served a live game's remaining-game total on 2026-09-10): the test is
  `betting_ingest.odds_event_started`, shared with `/betting/`, judged at the
  snapshot's `captured_at`, counted in `vegas_source.n_rejected_in_game` and
  marked on the game as `vegas_refused: "in_game"`
* active roster: the pool is FILTERED to the active roster after pricing.
  `integrity.n_hitters` and `n_pitchers` count the board as served (always equal
  to the rows in `players`), `n_*_priced` count what priced before the filter,
  and `n_*_removed_off_roster` is the difference. The join detector
  `orgs_without_hitters` reads the PRICED rows on purpose, so a club whose bats
  were all roster-removed is not reported as a join miss; both collapse guards
  read the served board
* confirmed lineups: posted cards set a hitter's spot and turn his start rate
  into a fact (the projection it replaced rides beside it); a posted card he is
  NOT on marks him `out`. Both joins are context and neither moves `pts`.

Re-pricing:

* Hitters. The ROS line already prices rest days, so dividing by the remaining
  team games gives an unconditional per-game line, which is the wrong number for
  a lineup slot. The two are split instead: `start_rate = min(1, pa_per_team_game
  / _PA_PER_START)` and the line is scaled to `pa_per_team_game / start_rate`
  plate appearances. An everyday bat comes out at a full start and rate 1.0; a
  strong-side platoon comes out at the same 4.02-PA game with a rate near 0.6.
  The anchor is MEASURED, not assumed: 4.0169 plate appearances per
  starting-lineup bat, 95% CI [4.0017, 4.0322] over 41,148 starter game rows in
  2,286 cached 2026 games (2026-09-17). It replaced a hand 4.15 that made every
  start-conditional line about 3.2% long, and the payload publishes the count
  beside it as `anchors.pa_per_start_basis`
* Hitter lines add up. The matchup and park multiplier moves the rate legs and
  leaves the plate appearance alone, so the AT BAT absorbs the walks and hit
  batsmen it adds: `ab + bb + hbp + sf = pa` closes on every served row (audit
  L17-F5, which found it broken on 14 of 109). The cost, stated because it is a
  real one: with the turns at the plate held fixed, the implied one-game batting
  average now responds to a matchup by MORE than the multiplier
* Starters. The ROS vector carries a projected start count, so the per-start
  line is a division. The matchup enters on the ALLOWED side (hits, earned runs,
  home runs), not as a blanket multiplier on the total: a weak opponent does not
  hand a pitcher strikeouts or innings.
* Relievers are not on the slate. Save and hold chances are not knowable before
  first pitch.
* Park factors are LIVE for MLB parks since 2026-08-07 (an earlier revision of
  this doc said they were neutral, which outlived the thing it described). The
  Savant run index resolves 29 of 30 clubs through the venue map; the park leg
  multiplies OUTSIDE the matchup clamp, a factor outside the plausible range is
  clamped with an `_out_of_range` suffix on its source, and every kind of miss
  keeps its own label (`neutral_site`, `no_factor_for_park`, `none`). The
  client derives its park sentence from the payload's own `park_sources`
  counts rather than hard-coding one.

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
  because both render on one tab. One filter bar sits above both boards, and the
  hitter board pages at 100 rows (see Search and filters above).
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

## Evidence accumulators (2026-08-16)

Two instruments started recording on 2026-08-16. Neither moves a served
number; both exist because a question kept being asked that no data on this
box could answer. Both live under `.cache/` because they are durable per-box
state and the deploy box runs `git checkout -- .` nightly.

**The two-start ledger** (`.cache/two_start_ledger.jsonl`,
`fantasy_export.update_two_start_ledger`). The two-start section serves
PROJECTED second legs, a rest-cycle guess (`fsched.projected_two_start`), and
nothing ever measured whether the guesses come true. Every daily refresh now
appends the projected legs it served (idempotent per pitcher, leg date and
day) and grades earlier projections against the real probable postings the
same fetch sees: `started` when a probable posts on the projected date,
`pushed` when it posts within 2 days of it, `skipped` when the date passes
with no matching posting. The grading basis is the POSTING, not the game
result, because the posting is what the projection claimed would happen. The
announced-starts view rides the payload as `schedule.announced7` (~2KB), kept
under the empty-fetch guard like the rest of the schedule so an outage day
cannot mis-grade a leg as skipped. Bounded by a documented compaction (120
days, then a hard line cap). `fantasy_export.two_start_ledger_summary()` is
the readout (distinct legs, outcomes, strict and with-pushed hit rates) for a
future page lane. After about four weeks the hit rate decides whether a
rotation-order model is worth building; until then nothing reads the ledger
at serve time.

**The DFS slate archive** (`.cache/dfs_history/<slate_date>.json`,
`dfs_export._archive_slate`). `data/dfs.json` is overwritten daily, so no
slate this module ever priced could be graded afterwards, and the registry
row for `dfs_slate_pricing` says so in its metric field. Every SUCCESSFUL
publish now archives a compact copy of the board as served: per player the
grading keys (mlbam, side, game_pk, team, opp) plus the served price
(`pts` in both systems) and the start-rate leg; per game the park and Vegas
context. Empty, refused and kept-previous payloads are never archived (the
kept board was archived on its own day; a same-day rebuild overwrites its own
file, keeping the last board a reader saw). Retention is ~120 days (~10MB, a
full season of gradeable history), pruned in the same write pass. This is
what makes the registry's planned-archive language truthful from the day it
runs; the matchup-multiplier backtest it enables is future work, not a claim.

## The closer save-share gate: RED (2026-08-16)

A save-share model (per-team share of forward saves from a trailing 30-day
window of saves and gmLI, fixed weights 0.65/0.35) was pre-registered against
the shipped pace rule in `docs/fantasy-closer-gate-2026-08-16.md` and run
once by `tools/fantasy_closer_lab.py` over 22 replayed 2026 window starts
(220 team-windows, 2,389 RP rows). It FAILED all three ship conditions:
pooled next-14-day saves MAE 9.1% WORSE than pace, mean within-team Spearman
worse (0.389 vs 0.416), and it won both metrics in 3 of 22 starts against a
70% bar. So the pace rule stays in `build_players`, the Closer Depth Chart
keeps its hand score, and no served number moved.

The instructive part: the non-decisive saves-only reference arm (w_sv = 1.0)
beat BOTH arms on both metrics. The gmLI term over-spreads the team's saves
across setup arms, whose entry leverage is also high. That is evidence a
better champion exists AND it is not shippable from this run: promoting the
reference after seeing the numbers would be fitting the champion to the test
set. A future wave may re-register a saves-only champion on data this run
never scored. Full numbers: `.cache/closer_lab/fantasy_closer_gate_eval.json`.

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
6. Filters, pagination and the filter half of the hash grammar (2026-08-16):
   the bar renders and narrows on all three clients, the filter never
   re-scores the roto pool, the optimizer pool honors the filters, the hitter
   board pages at 100 and a filter resets the page, the filter keys round-trip
   through the coordinator and an invalid value is normalized out of the URL,
   `_team_next7` bakes the right shape under its 20KB fixture bound, and
   `data/fantasy.json` stays under its 600KB budget.

`test_fantasy_cards.py` additionally drives `assets/fantasy-card.js` directly:
the next-7 strip is keyed by the player's club and colors by opponent Offense+,
the sparkline lazy-loads the right history board once per session and carries
its as-of label, and a missing history renders no trend block.

`test_fantasy_two_start.py` also covers the two-start ledger (2026-08-16):
append shape, per-day idempotency, all three grade outcomes, grade
idempotency, the first-leg-cannot-confirm-itself guard, compaction, corrupt
line tolerance and the summary readout. `test_dfs_history.py` covers the
slate archive: compact shape, refusal of empty and refused payloads, same-day
overwrite, retention pruning (standalone and in the write pass) and the
`refresh()` wiring. Both were mutation-checked in memory on 2026-08-16:
dropping the ledger dedupe, neutralizing the grader and neutralizing either
retention each fail their tests.
