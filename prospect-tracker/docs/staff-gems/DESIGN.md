# Staff Gems (owner ask 7): data survey, attribution design, publication rule, module design, staged build

Committed 2026-10-03 as stage 0 commit 1 (queue task Q10_17_STAFF_GEMS_STAGE0). The source is
the `staff_gems` lane document of 2026-09-30 (`staff_gems.md` in the Part 8 bundle,
`C:/Users/noah/baseball-projects/_finalpass_2026-09-24/part8/`; probe evidence in
`staff_gems_work/` beside it), carried here with the two changes that plan Part 8 makes to it (P8.8
'Staff Gems' and 8.D 'Conflicts between lanes, resolved' rows 6 and 7), the three publication
additions of the stage 0 specification, and the owner's answers. The section "Changes from the lane
draft" below lists every edit; the body is the lane's text with those edits applied in place.

Every `file:line` below is pinned to commit `64bf1bb3` (the lanes' base); read it with
`git show 64bf1bb3:./<path>` and find the same code at a later HEAD by its function or string. The
lane was READ-ONLY: no repo write, no pytest, no exporter, no live `prospects.db` read, no registered
look, no reserved eFV frame, no realized statistic by consensus-FV cell. Network probes are logged
in Appendix A. Staff names that appeared in the lane's probe log are omitted here; a person is an
MLBAM id, and this document needs none.

Owner ask 7 (2026-09-30, verbatim): "Staff Gems" module that uses DvM+ / graduate WAR /
associated prospects and cross-references it with a list of player development personnel to
identify which staff members in each organization have been developing their position above
the mean? Could also extend to Club Tendencies to identify which 1B/3B coaches are best at
baserunning, etc.?

---

## Changes from the lane draft (read first)

| # | Source | Change | Where it lands below |
|---|---|---|---|
| C1 | plan P8.8 change (1); 8.D row 6 | The manager leg reads same-source FV grade pairs (overall FV, list to list, the unit every other role reads), never the per-snapshot eFV series. The eFV retrospective series is today's model re-scoring old lists (the DvM defect D-4), the wrong object for crediting past staff, and reading it would put eFV scores on the reserved 2020-2021 lists into a staff table. This removes the lane's only reason to wait for the fWAR epoch's step Z at the gate. | 0 item 6; 4.2; 4.7; 7; 9 |
| C2 | plan P8.8 change (2); 8.D rows 6 and 7; owner answer Q-DVM-1 (2026-10-01, "Exclude until then") | One reserved-frame rule for Part 8's research frames. Grade pairs with an endpoint in list vintage 2020 or 2021 (the eFV reserved frame R-LV) enter the gate's one look only if the R-LV look record exists when the look runs; if no R-LV record exists by 2027-01-31, the look runs on the complement frame (no 2020 or 2021 endpoint) and says so in its artifact. The look waits for that record or that date. DvM's frozen expectation table may enter the baseline only after DvM's own look has run, and only through a registration naming the artifact in its forking-paths count. | 4.4; 4.7; 7 |
| P1 | stage 0 specification, publication addition (i); owner answer SG-Q4 | A named manager or base-coach row carries style fields only: attempts, the share of steals of second and third, and the break-even faced. No success rate, realized value, mWPA or letter sits in the same row or leaf. The Franchise DUGOUT names move to a leaf with no realized figures: today's DUGOUT branch prints realized mWPA per decision family (`franchise_export.py@64bf1bb3:757-763`, at 'success_rate'), beside the `manager_skill` and `decision_quality` keys its NEVER list bans (`:105-106`, FORBIDDEN_KEYS). | 4.9; 5.2; 6.1 |
| P2 | publication addition (ii); owner answer SG-Q3 | Every org-by-role cell needs at least 4 distinct persons, with no person over half of the cell's exposure, besides the 20-player floor; a cell that misses it is shown unsigned (a magnitude with no direction). | 4.6; 5.2; 6.1 |
| P3 | publication addition (iii) | The opt-out list lives outside the webroot, in `config/staff_optout.json` or `.cache/staff/optout.json`, never under `data/`: every top-level `data/*.json` ships (`deploy/publish_paths.txt`; census X03-15). | 5.2 |
| S1 | owner answer SG-Q2 (StatsAPI only); plan P8.8 SG-Q2 | The source registry rates `statsapi_coaches` legal_risk 'ambiguous', as it rates `mlb_pipeline_graphql`, not 'low': about 15,000 requests is bulk use outside MLBAM's "individual, non-commercial, non-bulk" notice, and a paid tier would also breach its non-commercial term (the owner already moved weather to NWS over commercial terms, FP5-2). | 2.1; 6.4; 7 |
| A1 | owner answers SG-Q1 to SG-Q4 (2026-09-30) | Section 8 records each answer; every answer is the lane's default. | 8 |

The persistence gate itself is registered separately and alone in
`docs/staff-gems/STAFF_GEMS_GATE.md`; where this document and the gate differ, the gate wins.

---

## 0. The answer in brief

1. **The repo holds no personnel data.** The only staff-shaped object on disk is a validation
   fixture: 92 ejection rows in 2025 that name a manager with an MLBAM id, published as a count
   and never used as a source (`mgmt_decisions.py:1087-1110`, `:1640-1643`;
   `test_mgmt_managers.py:56-84`). The management export says it in its own words: "there is no
   manager entity anywhere on disk: no manager in any game feed, no manager transaction, no coach
   or staff cache" (`mgmt_export.py:493-499`).
2. **One public source carries dated, identified staff history: the MLB StatsAPI coaches
   endpoint** (`/api/v1/teams/{id}/coaches?season=` or `?date=`). 331 of 331 rows in a cross-org
   probe carried an MLBAM person id. MLB staffs are listed back to at least 1960; minor-league
   affiliate staffs from 2008 (Yankees affiliates: 0 to 2 per team in 2005, 0 to 4 in 2008, 4 to
   5 in 2017-2019, 4 to 9 since 2021). The `date` query resolves a mid-season change to the day
   (Nationals 2025: the manager through 07-06, the interim manager from 07-07, found in 9 requests).
3. **Not obtainable from any dated, identified source:** minor-league coordinators and roving
   instructors, directors of player development, analysts, strength, mental-performance and
   medical staff; who worked with which player; instructional-league and spring assignments;
   minor-league base coaches. Club press releases and the paid Baseball America Directory carry
   some of it, as names only.
4. **The grade history cannot see one coach cleanly.** Of 25,802 same-source, same-org
   tool-grade pairs (the unit org Tendencies already uses), 0.6% sit inside one April to
   September window and 64.2% touch an October to March offseason; the median pair spans 197
   days. Credit has to be apportioned by exposure (days with each staff member), with the
   offseason credited to the organization and to nobody by name.
5. **The signal may sit below detection.** Today's cross-org spread in tool development is 0.23
   to 0.64 grade points per prospect-year, noise included (committed `data/org_tendencies.json`).
   The design registers a persistence gate before any coach number exists and ships cleanly when
   it reads null. The In-Game Management running game read null on 13,973 attempts and withheld
   its plus metric; that is the precedent.
6. **Attribution:** role-matched traits (hitting coach: hit, power, pitch selection, bat
   control; pitching coach: pitch grades and command; defensive coach: field and arm; manager:
   overall FV growth on same-source grade pairs, change C1), exposure-weighted, against a level, age, source, season and park
   baseline, with empirical-Bayes shrinkage toward the org mean whose prior variance is
   estimated from the data, 90% bands from a player-clustered bootstrap, hard floors and a
   false-discovery rule. Graduate WAR enters only as VAL_4's club share, split inside the club
   by time under each staff member: an accounting line, never compared to an FV-cell expectation.
7. **Publication rule recommended:** name gems only, each with n, player-years and a band; never
   rank or list anyone below the mean; one indistinguishable state for "not measured" and "not
   above"; removal on request. Owner question SG-Q1.
8. **First- and third-base coaches:** the running game's club-season decision value does not
   repeat (split-half 0.1085 inside its null band [-0.1501, 0.1272]), and a coach inside a
   club-season cannot carry more of that signal than the club-season. Recommended: names as
   context beside the club's running-game style rows, no value, no ranking, and two registered
   2027 tests. Owner question SG-Q4.
9. **Build in four stages:** 0 data acquisition (the owner's source decision, the gate
   registration, then the raw fetch into `.cache/`; not served); 1 schema and identity (not
   served); 2 attribution and the one gate look (after VAL_4 lands, under the reserved-frame
   timing of C2); 3 pages behind `STAFF_GEMS_LIVE` default False. Four owner questions, one batch, in
   section 8.

---

## 1. What the repo holds today

### 1.1 Personnel data: none

| Search | What exists | Where |
|---|---|---|
| `coach` (12 hits outside `data/`) | the ejection parser's role vocabulary; the blocker sentence; "front-office and coaching salaries: not sourced"; coaching named as one reason prospects' outcomes co-move (the correlation is assumed, 0.10); one comment; one article; two plans | `mgmt_decisions.py:240-242`, `mgmt_export.py:497-498`, `ledger_export.py:2113`, `value_framework_config.yaml:466-479`, `bayes_trade_value.py:3181` |
| `coordinator` | only the ejection fixture's text ("Angels coordinator, run production" and a name), the same play text inside three management shards, and the /fantasy/ page "coordinator" (a script, not a person) | `test_mgmt_managers.py:96-98`, `mgmt_decisions.py:1061`, `build_site.py:146` |
| `manager` (the baseball entity) | a dark Managers block, blocked on "mgmt_managers ingest (M-MWAR-2)"; its test; the pinned split rule a mid-season change will use; `data/managers.json` does not exist | `mgmt_export.py:487-506`, `test_mgmt_managers.py:39-53`, `mgmt_decisions.py:1454`, `test_mgmt_managers.py:107-114` |
| `personnel`, `staff` | no table, file or cache; `.cache/` holds 40-man rosters (players only) and team lists | `.cache/statsapi_roster_40man_*`, `.cache/statsapi_teams_*` |
| prior plan item | M10-06 "Manager entity from Retrosheet game logs (per-game manager ids), StatsAPI coaches for 2026", **still open** (not in DECISIONS_FOR_OWNER.md) | master plan lines 939 and 961 |

### 1.2 What Staff Gems builds on

- **Org DvM+** already credits development to the org that held the player: "incoming
  acquisitions (trades, draft, IFA) contribute zero on the day they arrive", graduations never
  subtract (`storage.py:8635-8665`), on the per-snapshot eFV with a consensus fallback
  (`storage.py:8731-8737`), scored 100 + 10z across the 30 orgs (`storage.py:14833-14843`).
  Registry `dvm_plus_org`: descriptive, no forward test.
- **Tool development (org Tendencies `toolDev`)**: same-source consecutive snapshot pairs, the
  same org at both ends, at least 60 days apart; an org-tool cell needs 6 pairs; rates in grade
  points per prospect-year minus the league mean (`org_tendencies.py:74-75`, `:628-686`,
  same-org test `:646`, day floor `:651`, cell floor `:666`). This is the unit Staff Gems splits.
- **Per-tool DvM+ shrinkage** is n/(n + 2) toward the league (`storage.py:14042-14076`); fine for
  30 orgs with hundreds of pairs each, far too weak for one coach (section 4.4).
- **Tool groups**: hit, pwr, speed, field, arm (throw), pitch_sel, bat_ctrl, fb, sl, cb, ch, cmd,
  ct (`storage.py:8088-8102`).
- **Graduate WAR today** is credited to the org on the debut row (`org_tendencies.py:957-976`);
  the graduate leaves, the Club Ledger graduates block and Franchise credit the current club
  (census X03-11, master plan line 1232). **VAL_4** (writer queue 7, owner answer FP2-4,
  DECISIONS_FOR_OWNER.md:378) replaces this with org-tenure segmentation and apportionment by
  development share. Its design doc (`docs/farm-attribution-2026-09-25/DEVELOPMENT_ATTRIBUTION.md`)
  is not committed yet; section 4.8 states the interface Staff Gems needs from it.
- **Where a player was**: snapshots carry the parent org, never the affiliate or level
  (`storage.py:1043-1061`); career rows carry season, level and parent org per stint but drop
  the affiliate id (`stats.py:1688-1699`, `:1881-1882`, `:1901`); the transactions cache carries dated
  from/to team ids (`storage.py:1185-1189`, `stats.py:2262-2265`), which `derive_level_changes`
  turns into dated level moves against a season-aware affiliation map (`stats.py:2428-2447`,
  `:4730`); IL stints come from `derive_injury_history` (`stats.py:3104`).
- **The running game**: per steal attempt, the decision value DV (league-average runner) and the
  execution residual ER (the runner), club-season as the agent (`management.py:1-26`,
  `mgmt_decisions.py:1-17`), under a frozen gate that returned DESCRIPTIVE ONLY
  (`data/management_gate_eval.json` `verdict`; `docs/IN_GAME_MANAGEMENT_GATE.md:19-28`,
  `:110-113`).
- **Surfaces**: farm detail tabs Overview, Roster, Development, Tendencies, Finances,
  Transactions & Pipeline, Discussion (`prospx/index.html:53706-53718`); the Development tab's
  panels (`prospx/index.html:53572-53585`); Franchise's descriptive FRONT OFFICE and DUGOUT
  branches (`franchise_export.py:82-92`, `:726-765`); NAV_ITEMS (`build_site.py:338-378`).
- **MiLB park factors** for the baseline (`data/milb_park_factors.json`).

---

## 2. Public sources, surveyed

### 2.1 Coverage, format, terms

| Source | Coverage (seasons, levels) | Format, identifiers | Terms, robots.txt | Verdict |
|---|---|---|---|---|
| **MLB StatsAPI `teams/{id}/coaches`** (`?season=` returns every holder in the season; `?date=` who held each job that day) | MLB: Yankees list manager and coaches in 1960 (7 rows), 1975 (7), 1985 (13: pitching coach plus generic "Coach"), 1995 (8, with hitting, first-base and third-base coach titles), 2000 (10). MiLB, Yankees affiliates: 2005 0-2 per team (mostly the manager), 2008 0-4, 2012 1-4, 2015 2-5, 2017-2019 4-5, 2021-2026 4-9 (complex team 7-9). Four more orgs (TBR, LAD, COL, ATL): 2012 0-5 per affiliate, thinnest at the Venezuelan and Dominican teams (VSL Dodgers and VSL Rockies 0; DSL Rays, Rockies and Braves 1), 2024 3-12 | JSON. `person.id` = MLBAM on 331 of 331 rows; `job`, `jobId` (MNGR, COAT hitting, COAH batting, COAA, COAP, COPA, COAU, DEFC, COAC, COA1, COA3, COAB, BCAT) and a free-text `title` that varies by club ("First Base/Infield/Baserunning Coach", "Performance Coach"). Mid-season moves resolve with `date` at MLB and MiLB. Vacancies show as gaps | No robots.txt (404). Every payload carries MLBAM's notice: "Only individual, non-commercial, non-bulk use of the Materials is permitted" (`gdx.mlb.com/components/copyright.txt`). The site's source registry scores StatsAPI endpoints legal_risk low as "the same accepted risk as the StatsAPI we already run on" (`data/sources/registry.yaml:89`) | **Primary.** The only dated, identified history |
| StatsAPI `teams/{id}/personnel` | MLB clubs, CURRENT staff only: the season parameter is ignored (Yankees 2012 and 2026 return the same 27 names); LAD returns 0; the "Organization" pseudo-teams return 0 | JSON, MLBAM ids | same notice | Not a history source |
| StatsAPI `transactions` | players | JSON | same notice | Carries no staff moves: WSH 2025-07-01 to 07-20 returned 34 rows and none was the 07-06/07-07 manager change |
| MLB club sites (`mlb.com/{club}/team/coaches`, front-office directories) | current season only | HTML rendered from MLBAM data; names | robots.txt disallows `/api/`, `/search` and a few paths, not `/{club}/team/`; MLBAM notice | Duplicates the StatsAPI; no history |
| MiLB.com team pages (`milb.com/{team}/roster`) | "Coaching Staff", current season only | HTML; names | robots.txt `Disallow:` (allow all); MLBAM content | Same |
| MLB.com press releases (example: "Rays name Minor League coaching staffs for 2024", 2024-01-23) | per club, per winter, when the club publishes one. Names affiliate managers, coordinators and roving instructors ("Pitching Coordinator", "Roving Hitting Instructor"), player-development leadership, and a changes table (name, position, 2024 club, 2023 assignment) | Prose and tables that differ by club; DELTAS, not full rosters; names only | robots.txt does not disallow `/press-release/`; MLBAM notice | The only public place coordinators appear. Hand curation only |
| Baseball America Directory | annual paid book (2019, 2020, 2021 and 2023 editions listed by retailers): front office and player-development staff for every MLB and MiLB club | print or PDF; names only | paid; the source registry already records BA as "PAID + Cloudflare 403 ... do not scrape", legal_risk high (`data/sources/registry.yaml:284`) | License only |
| Wikipedia | MLB season articles carry the coaching staff in the roster box; MiLB is idiosyncratic (a "List of Nashville Sounds coaches" exists; most affiliates list current staff at best) | wikitext; names with wiki links | CC BY-SA 4.0 (share-alike on redistributed text); robots.txt allows article pages | An MLB cross-check, not a MiLB source |
| The Baseball Cube | "List of Minor League managers for the selected season for affiliated minor league teams since 1977" (its own words); MLB coaches by team; a premium tier | HTML; TBC-internal person ids, no MLBAM | robots.txt allows `/` except `/premium/`, `/data/` and others; the site refused the fetch tool (403) and no terms page was verified, so terms are UNVERIFIED; TBC sells data | Managers only for MiLB; license only |
| Retrosheet `coaches0.csv` and biofile | MLB coaches by team-season, "as compiled by Retrosheet volunteers"; the biofile gives first and last game as a coach for everyone who coached in MLB, through 2025 | CSV; retroIDs (the Chadwick register maps retroID to MLBAM) | robots.txt disallows `/boxesetc/` and `/gamelogs/` to crawlers (downloads are the documented route); "copyright 1996-2026 by Retrosheet", attribution required | The best free MLB cross-check for base coaches and managers; no MiLB |
| Baseball-Reference roster pages ("Coaching Staff") and BR Bullpen | MLB staffs by season; some MiLB managers on Bullpen pages | HTML; bbref ids | Crawl-delay 3, GPTBot disallowed; the source registry records "Sports-Reference ToS bars scraping/bulk", legal_risk high (`data/sources/registry.yaml:289`) | Not usable in bulk |
| FanGraphs RosterResource coaches | MLB only, 2026 and 2025 end of season | HTML; FanGraphs ids in links | Cloudflare blocks Python (`data/sources/registry.yaml:282`) | Current-season cross-check only |

### 2.2 Identity resolution

- **StatsAPI rows resolve by construction**: the MLBAM person id is on every row, and the site's
  spine is `mlbam_id` (`data/sources/registry.yaml:10`). A person is the id, never the name.
- **Every other source is names only** (press releases, BA, Wikipedia, TBC, club pages) or a
  foreign id (retroID, bbref id, FanGraphs id). Rule: a name-only row is used only when it
  matches exactly one StatsAPI person holding a spell at the same org in the same season;
  anything else goes to a review queue and is not used. A name never creates a person.
- **Why the rule is strict**: the site has already served two humans merged under one key
  (census X03-01: "Max Muncy ATH age 24.1" carried the Dodgers veteran's value). Staff names
  repeat across the game, and a merged coach would carry another man's record.
- **Retrosheet rows** map through the Chadwick register (key_retro to key_mlbam; the audit copy
  at `_audit_2026-09-09/chadwick_register.csv` has 26,108 rows). Unmapped retroIDs stay out.

### 2.3 What is NOT obtainable

1. Minor-league coordinators and roving instructors (hitting, pitching, field, catching, run
   production), directors of player development, analysts, strength, mental-performance and
   medical staff, historically. The affiliate lists omit them, the `personnel` endpoint is
   current-only and MLB-only, and the org pseudo-teams list 0 to 2 people.
2. Who worked with which player: assignments inside a staff, one-on-one work, pitch-design lab
   sessions, remote work.
3. Offseason development: instructional league, winter programs, spring-training groups, private
   trainers the player hires.
4. Minor-league base coaches. In 139 MiLB team-seasons probed, one lists a "First Base Coach"
   (FCL Rays 2024), none a third-base coach; the minor-league manager usually coaches third,
   unrecorded.
5. Complex and DSL staffs before about 2012, and most minor-league staff before 2008.
6. The third-base coach's send-or-hold decisions at MLB: no family on the site prices them.
7. Anything private (contracts, pay, reasons for a dismissal). Not obtainable and not wanted.

---

## 3. Feasibility measurements (structure only, no outcomes)

### 3.1 What was read, and what was not

The one database read used an ARCHIVED backup outside the repo
(`C:/Users/noah/baseball-projects/_archive_2026-09-25/prospects.db.bak-ewar-2026-09-04`, opened
`mode=ro&immutable=1`), never the live `prospects.db` the monthly run is writing. It counted
rows, pairs and dates (`staff_gems_work/db_coverage_probe.py`). No grade was differenced, no
development rate was computed for any coach, affiliate or org, no outcome (WAR, debut) and no eFV
value was read. The spreads in 3.3 are read from the committed `data/org_tendencies.json`.

### 3.2 Grade-pair structure (backup dated 2026-09-04)

| Quantity | Value |
|---|---|
| Snapshot rows / active with tools and org | 62,839 / 55,521 |
| Tool rows by source | FanGraphs 24,292; MLB Pipeline 20,104; TJStats 6,096; Baseball America 4,456; Just Baseball 426; ESPN 147 |
| Same-source, same-org pairs at least 60 days apart (the toolDev rule) | 25,802 pairs on 5,375 players |
| Consecutive same-source rows that cross an org change (dropped by toolDev; VAL_4 splits them) | 1,341 |
| Pair span, days, p10 / p50 / p90 | 159 / 197 / 366 |
| Pairs that touch an October-March window | 64.2% |
| Pairs inside one April-September window | 0.6% |
| Pairs by end year | 2012: 129; 2015: 465; 2017: 559; 2018: 1,471; 2019: 2,115; 2020: 2,611; 2021: 2,825; 2022: 2,601; 2023: 2,490; 2024: 2,783; 2025: 2,976; 2026 (to 09-04): 3,559 |
| Pair players with a transactions payload (dated affiliate moves) | 4,108 of 5,375 (76.4%); the rest fall back to season-level career rows |

Reading: lists publish before and during the season, so almost every pair mixes spring training
or the offseason with part of a season at one or more affiliates. There is no clean
"under this coach only" window; exposure weighting is not a refinement, it is the only honest way
to split credit.

### 3.3 The spread coach effects must show up against

Committed `data/org_tendencies.json` (generated 2026-09-25), `toolDev.league.tools`: league mean
and cross-org SD of tool development, grade points per prospect-year in org:

| Tool | Mean | SD across orgs | Tool | Mean | SD across orgs |
|---|---|---|---|---|---|
| hit | -1.08 | 0.41 | fb | -0.67 | 0.30 |
| game_pwr | -0.23 | 0.33 | sl | 0.08 | 0.24 |
| raw_pwr | 0.09 | 0.34 | cb | -0.34 | 0.24 |
| pitch_sel | -0.12 | 0.56 | ch | 0.01 | 0.26 |
| bat_ctrl | -0.84 | 0.64 | cmd | -0.54 | 0.33 |
| field | 0.01 | 0.23 | speed | 0.09 | 0.28 |

Three readings. (1) Future tool grades drift DOWN on average (hit -1.08 a year), so "above the
mean" will often mean "declined less than the league". (2) These SDs include sampling noise, so
the true org spread is smaller. (3) An org's rate averages over about seven affiliate staffs per
role plus the offseason, so a true coach SD as large as about 0.8 points a year (0.3 x sqrt 7) is
compatible with that spread, and so is zero.

Arithmetic on stated ASSUMPTIONS, to be replaced by the gate's own simulation: at a per-coach
standard error near 1 point per player-year and about 300 coaches past the floors, a split-half
correlation would be about 0.04 at a true coach SD of 0.3 and about 0.24 at 0.8, against a null
SD near 0.058. The gate can see coach effects about as large as today's whole org spread, not
smaller ones. A null is the likely result, and the design is built to ship under one.

### 3.4 Staff structure (Yankees affiliates, 9 sampled seasons 2008-2026)

146 distinct minor-league staff; 89 appear in more than one sampled season and 69 at more than
one affiliate. Moves are routine and within the org: a pitching coach at Pulaski (2017, 2019),
Hudson Valley (2021), Tampa (2023), Scranton/Wilkes-Barre (2025), Tampa (2026); a hitting coach
moved mid-2019 from Double-A Trenton (listed 04-10 and 06-01) to the GCL (listed 07-15 and
08-25), after which Trenton lists no hitting coach. So within-org movement across levels is
plentiful (it separates a coach from a level) and cross-org movement is the thin part (it
separates a coach from an org).

---

## 4. Attribution design

### 4.1 The objects

- **staff_spell**: person (MLBAM), team_id, parent org, level, season, role family, jobId, title,
  start, end, date resolution (day or season), source, fetched_at.
- **unit**: an affiliate-season (team_id, season, first and last game); one org-offseason unit
  per org per winter (last affiliate game to next first game: instructional league, winter,
  spring training); 2020 as one org-level unit (no minor-league season; the alternate training
  sites list no staff).
- **location_spell**: player_key, team_id, org, level, start, end, status (active, IL, rehab),
  resolution (day from transactions, season from career rows weighted by games).
- **pair**: player, source, dates a and b, org, per-trait grades at a and b, under org
  Tendencies' rule, except that a pair crossing an org change is split at the change date by
  VAL_4's segmenter instead of being dropped.

### 4.2 Role to trait map

| Role family (jobIds) | Traits credited | Players | Named credit |
|---|---|---|---|
| Hitting coach (COAT, COAH; assistant COAA) | hit, pwr (game and raw), pitch_sel, bat_ctrl | position players | yes, if a gem |
| Pitching coach (COAP; assistant COPA; bullpen COAU) | fb, sl, cb, ch, ct, cmd | pitchers | yes, if a gem |
| Defensive coach (DEFC; infield and catching titles mapped by hand) | field, arm | position players | yes, if a gem |
| Manager (MNGR, interim) | overall FV growth on same-source FV grade pairs (C1; never the per-snapshot eFV series) | all | yes, if a gem |
| Coordinators, rovers, directors (not in the source) | org-wide leg in their discipline | all | only under SG-Q2 (b) or (c) |
| Bench coach, generic "Coach", performance and strength titles, bullpen catcher | none | | no |
| First- and third-base coach (COA1, COA3; MLB only) | running-game context (4.9) | | name only, no value |

Speed stays with the org: it is mostly physical, and no minor-league affiliate lists a
baserunning coach. Unmapped titles go to a review queue, never to a guessed role.

**The identifying assumption, printed on the page.** Inside an affiliate-season the manager, the
hitting coach and the defensive coach see the same players on the same days, so the data cannot
say which of them moved a hitter's grades. The map assigns by job description. The ledgers are
therefore parallel and never summed across roles, the rule the management ledger already keeps
for its families (`mgmt_decisions.py:186`, OVERLAP_NOTE).

### 4.3 Exposure

For pair i and unit u, `e_iu` = active days of the player at u inside (a, b], divided by 365.25.
IL and rehab days are removed; MLB days are removed (not development staff); offseason days go to
the org-offseason unit. For staff member c in role r:

`e_ic` = sum over days of [player active at u] x [c holds r at u that day] / [holders of r at u that day].

Days with no holder of r at u go to "vacant" and are never assigned to a guess. **One splitter
serves VAL_4 (org calendar) and Staff Gems (unit and staff calendars)**, so the two can never
disagree about where a day went. Players without a transactions payload (23.6% of pair players)
get season-resolution location from career rows; the gate reads with and without them.

### 4.4 The model

For trait k in role r's family and pair i:

`delta_ik = sum_u e_iu * mu(level_u, k, source_i, season_u) + beta' x_i + sum_u e_iu * a(org_u, r) + sum_c e_ic * b_c + eps_ik`

- `mu`: the league development rate per exposure-year by level, trait, source and season, fixed
  effects fitted on every pair (including pairs with no staff data).
- `x_i`: age at a (spline), exposure-weighted park factor and league of the units, an IL-days
  indicator, the source's days between the two publications.
- `a(org, r)`: the organization's role effect, a random effect shrunk toward the league (0).
- `b_c`: the staff member's deviation from his org's mean, a random effect shrunk toward 0,
  which IS the org mean. This is the owner-requested shrinkage toward the org mean.
- `eps`: correlated within a player (several sources grade the same months). Each source pair
  is weighted 1/(number of that player's source pairs overlapping it), and every interval is
  player-clustered.
- **Estimation, v1, kept readable**: weighted least squares for the fixed part; raw `b_c` and
  its standard error within org; the prior variance
  `tau2_r = max(0, mean(b_c^2) - mean(SE_c^2))` across staff past the floors (a leave-out moment
  estimator; Kline, Saggio and Solvsten 2020 give the heteroskedastic version); posterior
  `b_c * tau2_r / (tau2_r + SE_c^2)`. The same for `a(org, r)` with its own prior. If `tau2_r` is
  estimated at zero, every staff member sits at his org mean and nobody is a gem: the shrinkage
  and the gate say the same thing.
- **Units**: grade points per player-year of exposure on the 20-80 scale. Tool grades mostly
  move in 5-point steps, so +1.0 reads as one extra 5-point step per five player-years with him.
  **No 100 + 10z index for individuals**: a ladder over named people invites reading its bottom,
  and the z of a shrunken estimate depends on the shrinkage. The org-by-role view uses the DvM+
  scale (orgs are institutions, and the site already prints org DvM+ in both directions).
- **Window**: pairs from 2017 (the org Tendencies `gradeHistory` window) to the frame's freeze;
  staff spells from 2008. Pairs with an endpoint in list vintage 2020 or 2021 follow the reserved-frame
  rule (C2). DvM's frozen expectation table enters the baseline only after DvM's look and only
  through a registration (8.D row 7); no realized outcome by rung, ever.

### 4.5 What "above the mean" means

- **Total effect** `T_c = a(org, r) + b_c`: development in role r's traits among the players he
  coached, against the league at the same level, age, source, season and park, in grade points
  per player-year.
- **Within-org effect** `B_c = b_c`: against his own organization's mean for the role.
- **A gem in role r** must: (1) pass the floors (4.6); (2) sit in a role whose persistence gate
  PASSED (4.7); (3) have the lower end of the 90% band above zero for both `T_c` and `B_c`, so
  an org-wide program is not credited to one person; (4) survive Benjamini-Hochberg at q = 0.10
  across every staff member in the role past the floors; (5) remain a gem when any single player
  is removed, so no gem rests on one breakout.
- A staff member who worked in more than one org pools his deviations from each org's mean.
- If the gate's movers leg is unpowered (fewer than 30 movers), a gem card says "above his
  organization's mean" and never that he beats another org's coaches.

### 4.6 Uncertainty and the minimum-n rule

- **Bands**: 90%, from a player-clustered bootstrap of the whole pipeline (fixed part, prior
  variances and posteriors re-estimated in every draw), B = 2,000, a fixed seed. Each card prints
  the band, P(T_c > 0) and the floors he clears.
- **Floors per staff member and role**, pre-registered and never tuned on outcomes: at least 12
  distinct players with 30 or more active days with him inside qualifying pairs; at least 3.0
  player-years of exposure; at least 2 seasons in the role; at least 30 effective pair-trait
  observations after source down-weighting. Below any floor no estimate is computed at all,
  internal or served. Org-by-role cells need 20 players AND at least 4 distinct persons with no
  person over half of the cell's exposure; a cell that misses the person floor is shown unsigned, a
  magnitude with no direction (P2).
- **Cadence**: rebuilt monthly for freshness; the gem label is re-decided twice a year (after the
  preseason lists, after the midseason updates) and needs two consecutive checkpoints to change,
  so a name cannot flicker month to month.

### 4.7 The persistence gate (registered first)

`docs/staff-gems/STAFF_GEMS_GATE.md`, committed alone before any staff spell meets a grade pair.
Its honesty clause records the design-day reads of section 3. Stage 1 may count exposure (no
grade deltas) to set power; those counts are disclosed in the doc before the look.

- **Leg 1, split-half persistence, per role.** Split each staff member's players by a hash of
  player_key into halves A and B (a player informs one half only); estimate `b_c` in each half;
  correlate across staff past the half-floors. Null: permute staff labels within (org, level,
  season) cells holding each cell's exposure fixed, 2,000 permutations, the construction the
  management gate uses (`data/management_gate_eval.json` `gate_1_split_half.null`). The role's
  one-sided permutation p-value enters the Holm family below.
- **Leg 2, pre-tenure placebo.** Give each staff member the exposure of the same affiliate in the
  season before he arrived. A coach cannot develop players he never coached; if the placebo
  clears its own null, the signal is the affiliate, the level or the assignment of players, and
  the role fails.
- **Leg 3, movers.** Staff past the floors in two orgs; correlate their deviations across orgs.
  Under 30 movers: UNPOWERED, and gems carry only the within-org claim.
- **Detection floor.** Inject coach effects of known SD into the real exposure design, residuals
  permuted within cells; publish the smallest SD detected at 80% power. A null without its floor
  says nothing (the management gate's `detection_floor` precedent).
- **Family**: four roles (hitting, pitching, defense, manager), Holm-corrected at family alpha
  0.05 (the smallest p is tested at 0.0125), on the owner's FP3-3 precedent
  (DECISIONS_FOR_OWNER.md:386).
- **PASS for a role** = Leg 1 clears its Holm threshold AND Leg 2 does not clear its own null.
  Leg 3 decides only the wording of the claim (4.5).
- **Frame**: pairs whose later snapshot is dated on or before 2026-09-30, rows inserted before
  the freeze stamp, a sha256 manifest in the artifact. Pairs with an endpoint in list vintage 2020
  or 2021 enter only if the R-LV look record exists when the look runs (C2); otherwise the look runs
  on the complement frame and its artifact says so.
- **One look**, after the R-LV look record exists, or on the complement frame if no record exists
  by 2027-01-31 (C2), never on a registered look date. The manager leg reads same-source FV grade
  pairs (C1), so the fWAR epoch's rebuild of the eFV series is no reason to wait. Looking early
  disqualifies (master plan Part 0.2).
- **Artifact**: `data/staff_gems_gate.json`, aggregate statistics only (correlations, bands,
  counts, floors, the manifest), **no person id**.
- **What a null decides**: no gem label for that role; the module ships under the owner's SG-Q3
  answer; the question may return only as a new registration on a new frame (after the 2027
  season), disclosing the overlap with this one.

### 4.8 Graduate WAR

- **Only through VAL_4.** VAL_4 gives each graduate's realized value per club: acquisition value
  to the signing club, the rest by each club's share of the growth in its tenure (FP2-4). Staff
  Gems takes the club-credited WAR `W(g, org)` as given. Interface needed from VAL_4: per player,
  the tenure segments (org, start, end) and the club shares; per graduate, `W(g, org)`.
- **Inside one club's tenure, time splits it**: `W(g, org, u) = W(g, org) x eligible days in u /
  eligible days in the tenure`; offseason days go to the org unit; in role r, the holders of r at
  u share `W(g, org, u)` by days held. Hitting and defensive coaches carry position players' WAR,
  pitching coaches pitchers', managers all. Role ledgers are parallel and never summed.
- **Why time and not growth** inside the club: a growth split would make the WAR line inherit
  every weakness of the grade model; a time split is exact accounting a reader can check. The
  card calls it "graduate WAR, time-weighted", an accounting share, not what he added.
- **Never compared to an expectation.** No "his graduates beat their FV cell"; no realized
  statistic by consensus-FV cell, before or after PROSPECT_ANCHOR_GATE's look (master plan Part
  2.3: "never compute an FV-cell realized mean before it"); no join of an as-of grade to a
  realized outcome, so no row of the reserved frames R-LV and R-VM is scored
  (`docs/efv-v2/EFV_V2_GATE.md` section 2.2).
- WAR is whatever VAL_4 serves: today's bWAR career rows (`storage.py:1133-1155`) until the
  fWAR epoch moves the label.
- **Identity**: for every graduate and club, the unit shares sum to VAL_4's club WAR exactly; per
  role, holders plus "vacant" sum to the unit share.

### 4.9 Base coaches and baserunning

- **Data**: MLB clubs list first- and third-base coaches (COA1, COA3) by 1995 in the probe, dated
  by the `date` query; Retrosheet's `coaches0.csv` is the MLB cross-check, the role the ejection
  fixture plays for managers today (`test_mgmt_managers.py:56-84`). Minor-league affiliates
  almost never list them (2.3 item 4).
- **What the management module measures**: the steal decision (DV, priced with a league-average
  runner) and its execution residual (ER, the runner beating the throw), per attempt, with the
  club-season as the agent (`management.py:1-26`; `mgmt_decisions.py:1-17`).
- **What its gate found**: DESCRIPTIVE ONLY. Season-controlled split-half 0.1085 on 238
  agent-seasons, inside the permutation band [-0.1501, 0.1272]; season-to-season Spearman of
  mean DV -0.098 on 179 pairs; 13,973 attempts (`data/management_gate_eval.json`). The gate doc
  already rules on anyone inside a club-season: "team-season persistence is an UPPER BOUND on
  manager persistence. If the team-season signal is null, the manager signal cannot be larger"
  (`docs/IN_GAME_MANAGEMENT_GATE.md:24-28`). A base coach is inside the same club-season.
- **Not measured anywhere on the site**: the third-base coach's send-or-hold on hits. It needs a
  new priced family (runner speed, fielder arm, ball location), inputs the play corpus may not
  carry, and its own gate.
- **Recommended now (SG-Q4 default)**: context only. Each MLB club-season row on Club Tendencies
  names the manager, first-base coach and third-base coach beside the club's running-game style
  fields ONLY (attempts, share of steals of second and third, mean break-even faced; three of the
  fields /franchise/ DUGOUT already reads, `franchise_export.py@64bf1bb3:757`; the success rate is
  left out, P1), sorted by season or by attempts (a style axis), never by success or value, with
  the gate sentence under it. No success rate, realized value, mWPA or letter sits in the same row
  or leaf as a name. Register, not run,
  two 2027 tests: a first-base-coach movers test on ER (does a club's ER move with an arriving
  coach, against clubs without a change) and a third-base send-or-hold family.
- **The attribution, if a 2027 test passes**, mirrors 4.4: the first-base coach is credited with
  the club's ER per attempt over the days he held the job, against the league and shrunk toward
  the club's own mean, under the same floors, bands and publication rule; the third-base coach
  with the new family's decision value per send opportunity. Until a test passes, neither number
  is computed for any person.
- **"Club Tendencies"** is read here as the org Tendencies module (`org_tendencies.py`; the farm
  Tendencies tab; /franchise/ FRONT OFFICE, `franchise_export.py:145-173`). The site has no page
  by that exact name; confirm in passing.

### 4.10 Confounds, and what the design does about each

| Confound | Why it biases | Design response |
|---|---|---|
| Assignment and promotion | clubs send ready players up, so a higher-level coach receives players who just grew | level baselines; exposure starts the day he arrives; the pre-tenure placebo |
| Evaluator timing | lists publish in batches and grade months of play | day-weighted exposure; publication-gap covariate; source effects |
| Parks and leagues | grades follow stats and stats follow parks | exposure-weighted park factor and league in the baseline |
| Age for level | young players move faster (the one org trait that separated in the roster-aware ETA work, DECISIONS_FOR_OWNER.md:344-345) | age spline |
| Unobserved staff and the offseason | coordinators, rovers, analysts, strength and medical staff, private trainers, the player | offseason to the org unit; in-season unobserved staff absorbed by the org effect; nobody named for either |
| Co-located roles | manager, hitting and defensive coach share every player-day | role map by job; parallel ledgers; the assumption printed |
| Injury | lost time and changed tools | IL and rehab days removed; IL indicator |
| Several sources on the same months | double counting a player | 1/(overlapping sources) weights; player-clustered intervals |
| Downward grade drift | tool grades fall on average (3.3) | inside the baseline; the card says "declined less than the league" when that is what happened |
| Many coaches, thin samples | chance winners | floors; empirical-Bayes shrinkage; BH at 0.10; leave-one-player-out |

---

## 5. Honesty and ethics

### 5.1 Why this module is different

Every other number on the site is about players, clubs or the site's own models. Players are
public performers measured in public. Minor-league staff are private employees, and a published
judgment of their work can follow them into hiring. This measurement is noisy (section 3),
cannot separate a coach from his org, his co-workers or his players (4.10), and may not repeat at
all (4.7). A wrong positive statement costs little; a wrong negative one can cost someone a job.

### 5.2 Recommended publication rule (SG-Q1 default)

1. **Name gems only** (4.5), each with players, player-years, seasons, the 90% band and the
   attribution caveat.
2. **Never rank, list, sort, colour, export or describe anyone below the mean**, by name or by
   any identifying combination (club, level, season and role together identify a person).
3. **One state for everyone else.** "Not measured", "not above the mean" and "below" render
   identically, and so do an unknown person id and a known non-gem id. The org view never counts
   staff measured, because "1 gem of 3 measured" names two people by elimination.
4. **Say who else developed the player.** The card's first caveat names coordinators, rovers,
   analysts, strength and medical staff, the offseason and the player.
5. **Removal and corrections on request** through /report/ (the site's "Report a bug" page,
   `build_site.py:6196`); an opt-out list (ids only), kept OUTSIDE the webroot in `config/staff_optout.json` or
   `.cache/staff/optout.json` and never under `data/` (every top-level `data/*.json` ships, P3), is
   applied before
   any payload is written, and a removed name is gone at the next build.
6. **Data minimization**: name, role, club and seasons from MLB's own listing. No photo, no age,
   no links to personal accounts, no contract detail.
7. **No news**: a gem's arrival or departure never produces a /news/ wire row.
8. **Retention**: per-person estimates for non-gems live only in gitignored `.cache/staff/` and
   are never committed; the committed gate artifact carries no person id. The repo moves to a new
   remote at the port, and a private remote today is not a promise about tomorrow.
9. **Language**: "players he coached developed faster than the league at the same levels", never
   "he developed them"; no superlatives; "gem" is the owner's module name and appears only as the
   label on gem rows.

### 5.3 Draft copy for the builder (lint-clean, no em-dashes)

- Page lede: "Staff Gems names minor-league coaches whose players developed faster than the
  league at the same levels, in the traits their job covers, with enough players to say so and a
  result that repeated in a second, separate group of players. A name missing from this page
  says nothing about that person."
- Card caveat: "Credit here follows time: these players spent these days with him. Coordinators,
  rovers, analysts, strength and medical staff, the offseason and the players themselves are
  part of every number on this card, and the data cannot separate them."
- WAR line: "Graduate WAR, time-weighted: his share of the time these players spent in the
  organization before they debuted, applied to the WAR the organization is credited with. An
  accounting share, not what he added."
- Role whose gate did not pass: "No {role} is named. The {role} result did not repeat in a
  second group of players (split-half {r} against a null band of {lo} to {hi}); the smallest
  coach effect this test could see is {floor} grade points per player-year."
- Neutral state: "No Staff Gems card for this person."
- What this page does not claim: that a named coach caused his players' development; anything
  about any person who is not named; that coordinators, rovers, analysts, strength and medical
  staff, the offseason or the players contributed nothing; that graduate WAR on a card was added
  by the coach; any skill of first- or third-base coaches; anything before 2017, or at complex
  and DSL levels before 2012, where the records are thin.

---

## 6. Module design

### 6.1 Pages and routes

- **/staff/** ("Staff Gems", an MLB Modules leaf after In-Game Management; `build_site.build_staff`,
  `assets/staff.js`, `assets/staff.css`, on the /ledger/ and /franchise/ pattern).
  - `#view=gems` (default): role chips Hitting, Pitching, Defense, Managers. Row: name (to
    `#person=`), role, clubs and seasons (club to `/franchise/#team=CODE`, affiliate to
    `/prospx/#farm-org=CODE`), players, player-years, above the league (band), above his org
    (band), graduates and time-weighted WAR. Default sort: the lower end of the above-league band;
    alternative: player-years. No ascending sort. A role whose gate did not pass shows the gate
    sentence and its floor instead of rows.
  - `#person=<mlbam>`: the gem card: band chart against the league and the org mean; tenure
    timeline (affiliate chips linking to farm pages); associated prospects with eFV now (eFV
    only, rounded nearest; owner ask 5) and months with him; associated graduates with the WAR
    accounting line; the caveat. Unknown and non-gem ids render the one neutral state.
  - `#view=orgs&org=CODE`: org-by-role development on the DvM+ scale (each cell past the 20-player
    and 4-person floors, else unsigned, P2) by level group (AAA-AA,
    A+-A, complex-DSL), the offseason share of exposure, the org's gems, links to the farm
    Development tab and /franchise/.
  - `#view=base`: MLB base coaches beside the running game's style fields only (4.9, P1).
  - `#view=method`: the gate by role with its numbers, the floors, the data source and MLBAM's
    notice, the identity rule, the publication rule, the does-not-claim list, removal requests.
- **PROSPX farm detail, Development tab**: a "Staff" panel after the tool development card
  (`prospx/index.html:53583`), lazy-fetching the org's slice: org-by-role chips and the org's
  gems, linking to `/staff/#view=orgs&org=CODE`. Restamp the hand pages afterwards (master plan
  Part 0.2).
- **/franchise/**: FRONT OFFICE gains a "Staff Gems" leaf (text: gems by role, or "none named";
  link to the org view) with the `staff_gems` verdict chip; DUGOUT gains a names leaf (manager, first-base
  and third-base coach) that carries no realized figure, apart from the leaves that print realized
  mWPA (P1), linking to the base-coach panel (`franchise_export.py:726-765`;
  `assets/franchise.js:353-366` OPEN_LINKS gains the staff links).
- **Club Tendencies** (`org_tendencies.py`): a `baseCoaches` panel (per season: manager, 1B and
  3B coach names, plus the running-game style fields from the management board's teams rows,
  attempts, share of steals of second and third and break-even faced only, P1),
  rendered on the farm Tendencies tab; no z, no label.
- **/management/**: the dark Managers tab stays M10-06's decision; the stage 1 ingest supplies
  the data it is blocked on.

### 6.2 Payloads

- `data/staff_gems_board.json`: gems, org-by-role cells, base-coach rows, the gate block, copy;
  budget 250 KB, test-enforced.
- `data/staff_gems/<mlbam>.json`: one shard per gem, 40 KB each, tracked on the ledger-shard
  precedent, with both deploy consumers shipping the directory.
- Nothing for non-gems anywhere under `data/`.

### 6.3 Links (owner ask 9)

Every club name links to `/franchise/#team=CODE`; every farm or affiliate reference to
`/prospx/#farm-org=CODE`; players to `/prospx/#player=KEY`; the base-coach panel to
`/management/#section=clubs&team=CODE` (`franchise_export.py:588`).

### 6.4 Registry, glossary, sources

- `staff_gems`: predicts nothing forward; a descriptive attribution of role-matched grade
  development to affiliate staff by exposure, shrunk toward the org mean, with a gem label only
  where the registered persistence gate passed. Verdict `provisional`, `provisional_kind:
  measurement_only`, eval artifact `data/staff_gems_gate.json` (the `mgmt_decision_ledger`
  precedent). Not a validated model, and the row says so.
- `org_role_development`: descriptive org-by-role index on the DvM+ scale; `provisional`,
  `measurement_only`; its eval artifact is the identity block of the same file.
- The base-coach context adds names, not numbers: the `org_tendencies` row's surface text gains
  the panel; no new model row.
- Glossary: `staff_gems`, `player_year_exposure`, `role_traits`, `org_role_development`,
  `base_coach_context`.
- Sources: `statsapi_coaches` in `data/sources/registry.yaml` (verified live 2026-09-30,
  legal_risk 'ambiguous' as the registry rates `mlb_pipeline_graphql`, S1), then
  `tools/gen_audit_docs.py` regenerates DATA_SOURCES.md.

### 6.5 Tests

| Test file | What it pins |
|---|---|
| `test_staff_ingest.py` | role map is total (every jobId and title maps to a role or "excluded" or the review queue); every row carries an MLBAM id; date bisection on saved fixtures (WSH 2025 boundary 07-06/07-07; the 2019 Trenton to GCL hitting-coach move); the season union equals the union of bisected spells; no network in tests |
| `test_staff_identity.py` | no name-only join creates or merges a person; a two-people-one-name fixture stays two |
| `test_staff_exposure.py` | per pair, unit exposures sum to eligible days; IL, rehab and MLB days excluded; co-holders sum to 1; the splitter matches VAL_4's segments exactly |
| `test_staff_gems_model.py` | synthetic recovery (known coach effects are recovered in order when their SD is large); at zero true SD the false-discovery rule names at most its expected share; floors block estimates; leave-one-player-out drops a single-breakout gem; the placebo flags a synthetic that sends the best prospects to one affiliate |
| `test_staff_gems_gate.py` | the gate doc is committed before the artifact (commit order); the look-date guard; Holm across the four roles; the artifact carries no person id |
| `test_staff_gems_war_share.py` | unit shares reconcile to VAL_4's club WAR exactly; static guards: no import of `fv_to_6yr_avg_war` or any FV-cell table, no grouping by consensus FV, no read of the reserved frames |
| `test_staff_publication.py` | served payloads name gems only; no numeric field on any non-gem person; the strings "worst", "bottom", "below the mean" and "least" never appear in `staff.js`, the payload or the copy; a non-gem id and an unknown id render identically; CSV rows equal gem rows; the opt-out list wins |
| `test_staff_render.py` | 1280 and 390, light and dark, zero console errors and failed fetches; every club cell links to /franchise/; no consensus-FV string on any staff surface |
| existing | `tools/copy_lint.py --check`, `tools/strip_emdashes.py --check`, `test_generated_docs_in_sync`, registry `validate()` |

---

## 7. Staged build

| Stage | What | Files | Tests | Gate or clock | Effort | Depends on |
|---|---|---|---|---|---|---|
| **0. Data acquisition** | ask SG-Q1 to SG-Q4 (the source is SG-Q2); commit this design as `docs/staff-gems/DESIGN.md`; register `docs/staff-gems/STAFF_GEMS_GATE.md` alone; add `statsapi_coaches` to the source registry with the probe samples; then `staff_ingest.py --fetch`: season lists for MLB clubs and every affiliate 2008-2026 via `teams/affiliates`, first- and last-game dates, and date bisection only where a role has two holders or a person two roles, all raw into `.cache/staff/` | docs, `data/sources/registry.yaml`, `data/sources/samples/`, `staff_ingest.py` (fetch half) | gate-doc presence test; fetch tests on saved fixtures, no network | docs and a cache fill; no served change, no database write | S to M (1 day plus about 80 minutes of fetching) | owner answers (SG-Q2 (d) stops here) |
| **1. Schema and identity** | parse the cache into `prospects.db` tables (persons, spells, units); the role map (`config/staff_roles.yaml`) with its review queue; identity rules and the name-only review queue; location spells from transactions and career rows; nothing under `data/` | `staff_ingest.py` (parse half), `staff_identity.py`, `config/staff_roles.yaml`, `storage.py` (tables) | `test_staff_ingest.py`, `test_staff_identity.py` | not served; hand-run, not in `run_monthly` until stage 3 | M (2 days) | stage 0 |
| **2. Attribution and the one look** | the exposure splitter shared with VAL_4 (built by whichever lands first); `staff_gems.py` (baseline, EB model, floors, bands, gem rule, WAR time-share); `tools/staff_gems_gate.py` run once; registry rows | `staff_exposure.py`, `staff_gems.py`, `tools/staff_gems_gate.py`, `data/staff_gems_gate.json`, `data/model_registry.json` | `test_staff_exposure.py`, `test_staff_gems_model.py`, `test_staff_gems_gate.py`, `test_staff_gems_war_share.py` | the look after the R-LV record, or on the complement frame from 2027-01-31 (C2); nothing served | L (3-4 days) | VAL_4 landed (for the WAR line); the R-LV rule (C2) |
| **3. Pages** | `staff_export.py`; `/staff/`; the farm Development panel; Franchise leaves; the Tendencies base-coach panel; nav leaf; glossary; `gen_audit_docs` regeneration; deploy lists; wire into `run_monthly` | `staff_export.py`, `build_site.py`, `assets/staff.js`, `assets/staff.css`, `prospx/index.html`, `franchise_export.py`, `assets/franchise.js`, `org_tendencies.py`, `data/glossary.json`, deploy publish lists | `test_staff_publication.py`, `test_staff_render.py`, export budget and identity tests | after step Z, behind `STAFF_GEMS_LIVE` default False; the owner flips it after the gate result and a private preview | M-L (3 days) | stage 2 |
| 4. Optional, 2027 | performance legs (park-adjusted MiLB rates; AAA and FSL Statcast pitch metrics for pitching coaches); the coordinator leg if SG-Q2 (b) or (c); the two base-coach tests (4.9) | each under its own registration | | own gates | per item | owner |

**Ingest budget (estimate, arithmetic):** about 570 MLB team-seasons plus about 4,600 affiliate
team-seasons (30 orgs, about 8.5 teams, 18 seasons without 2020) plus 570 affiliate-map calls,
so about 5,700 season-list requests; bisection at about 9 requests per change adds perhaps 9,000;
about 15,000 requests once (about 80 minutes at 3 per second), then about 800 a season. That is
bulk use in MLBAM's terms, on the same posture as the site's existing per-player transactions and
stats pulls. The owner chose it (SG-Q2, StatsAPI only) with the registry rating it 'ambiguous' (S1).

**Queue placement and hazards.** Stage 0 fits between queue 7 items: its documents are a docs
task and its fetch writes only the gitignored `.cache/staff/`. Stages 1 to 3 form a new queue
after queue 7's VAL_4, one writer at a time. Stage 1 writes `prospects.db`, so it never runs
during a monthly or nightly run or a pytest session (the conftest restore trap, master plan
Part 0.2). A new `data/` file ships to the webroot unless the deploy lists say
otherwise (census X03-15); per-person estimates never touch `data/`. After any `site.css` or
shared-runtime edit, restamp the hand pages; a JS comment naming a `.json` file lands in
SITE_MAP.md.

**Clock compliance.** Nothing here serves before 2026-10-04. Stage 3 serves after step Z behind
the flag. No fitted input is read: the manager leg reads same-source FV grade pairs (C1). No
other gate's registered look, no reserved frame outside the C2 rule and no FV-cell statistic is touched at
any stage; the only look is Staff Gems' own, once, under the C2 timing.

---

## 8. Owner questions (one batch of four; the most outward-facing first; defaults first)

**Answered 2026-09-30** (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, 'ANSWERED 2026-09-30
(AskUserQuestion), Part 8 batch 4 (Staff Gems)'): SG-Q1 gems only; SG-Q2 StatsAPI only, rated
'ambiguous' in the registry, coordinators stay out; SG-Q3 org view only for a role whose test
reads null, cells with at least 4 distinct staff and none over half the exposure, else unsigned,
nobody named for that role until a new registration after 2027; SG-Q4 style names and two 2027
tests, registered and not run. Every answer is the lane's default (a). The questions are kept
below as asked.

None of these re-asks an answered decision. FP2-4 (developing-club credit) is VAL_4's and is taken
as given. M10-06 (the management module's manager entity) stays open and is not asked here;
answering SG-Q2 (a) supplies its data and leaves only whether /management/ consumes it.

**SG-Q1. Who may be named, and how?**
- **(a) DEFAULT, recommended: gems only.** A person is named only when he clears the gem rule
  (role gate passed, floors met, above the league mean and above his own org's mean at 90%,
  false-discovery rate 10%, survives dropping any one player). Each card prints players,
  player-years, seasons, the band and the caveat. Nobody is ranked, listed, coloured or exported
  below the mean; no page separates "not measured" from "not above"; removal on request via
  /report/. Flipping away from (a) changes whether private individuals can read a negative
  judgment of their work on this site.
- (b) A full named ledger in both directions (every measured coach, sortable, CSV). Not
  recommended: it publishes reputational negatives about private people from a measurement that
  cannot separate a coach from his org, his co-workers or his players.
- (c) No individuals: org-by-role development only (hitting, pitching, defense and the manager
  leg, by level). Changes: /staff/ becomes an org view; no person is named anywhere.
- (d) Name MLB staff only; minor-league gems shown by role, affiliate and seasons without a name.
  Changes: nearly every gem is a minor-league coach, so the board would be mostly unnamed.

**SG-Q2. Which staff source (stage 0)?**
- **(a) DEFAULT: the MLB StatsAPI coaches endpoint only.** MLBAM ids on every row; MLB staffs
  back to 1960 with base-coach titles by 1995; minor-league affiliate staffs from 2008 (complex
  and DSL from about 2012); mid-season changes dated by the endpoint. Same posture as the site's
  other StatsAPI pulls (the lane rated it legal_risk low; the registry now rates it 'ambiguous', S1), under MLBAM's notice (individual,
  non-commercial, non-bulk). Coordinators, rovers, analysts and development directors stay out,
  because no dated source exists. About 15,000 requests once.
- (b) (a) plus hand-curated coordinator and roving-instructor lists from club press releases for
  recent winters. Names only, uneven by club and year, change lists rather than rosters, every
  name resolved by hand. Adds an org-wide coordinator leg and a recurring curation chore.
- (c) License the Baseball America Directory (annual, paid, names only, a written license); the
  source registry already rates BA "do not scrape", legal_risk high.
- (d) Build nothing now; Staff Gems waits.

**SG-Q3. If the persistence gate reads null for a role (the likely result), what ships?**
- **(a) DEFAULT: the descriptive module without gems for that role.** Org-by-role development
  (institutions, both directions, DvM+ scale), the gem board showing the gate sentence and its
  detection floor, no individual numbers; a new registration after the 2027 season. Changes:
  nobody is named for that role.
- (b) Name individuals anyway, labelled "descriptive, not repeatable". Not recommended: the
  In-Game Management module withheld its plus metric on the same kind of null, and a number that
  does not repeat, printed beside a person's name, is a ranking of noise.
- (c) Hold all of /staff/ until some role passes. Changes: nothing ships in 2026.

**SG-Q4. First- and third-base coaches and baserunning?**
- **(a) DEFAULT: context only, plus two registered 2027 tests.** Each MLB club-season's manager,
  first-base and third-base coach named beside the club's running-game style rows on Club
  Tendencies and the Franchise DUGOUT, sorted by season or volume, never by value, with the
  management gate sentence; register (not run) a first-base-coach movers test on the execution
  residual and a priced third-base send-or-hold family. Changes: names appear beside club
  numbers with no judgment.
- (b) Context only, no future tests.
- (c) Drop the extension: the running game's club-season decision value does not repeat (0.1085
  inside [-0.1501, 0.1272]), and a coach inside a club-season cannot carry more signal than it.
- (d) Rank base coaches by steal value now. Not recommended; listed so the conflict is visible:
  it contradicts the frozen management gate.

**Executor defaults taken without asking (reversible, display or method detail):** the nav slot
(after In-Game Management); "above the mean" as defined in 4.5; units in grade points per
player-year with no individual plus index; the label re-decided twice a year; "Club Tendencies"
read as the org Tendencies module; pairs from 2017 and staff spells from 2008; MLB-level staff in
v1 only as base-coach context.

---

## 9. Wiring notes and items handled elsewhere

- **Management (M-MWAR-2)**: the stage 1 ingest is exactly the network fetch the Managers tab is
  blocked on (`mgmt_export.py:493-499`); whether /management/ uses it remains M10-06.
- **Portfolio correlation**: `value_framework_config.yaml:466-479` assumes prospects in one org
  share development effects at rho 0.10. The org-by-role variance components from stage 2 could
  measure that instead of assuming it, under its own registration later.
- **Promotion timing** (queue 6, DECISIONS_FOR_OWNER.md:344): the farm Tendencies promotion panel
  could show manager tenure beside promotion pace, as context.
- **Ask 5** (eFV the only displayed FV): every Staff Gems surface shows eFV for players; the
  manager leg's same-source grade pairs (C1) are an input and are never displayed as a player's FV.
- **Ask 6** (difficulty-weighted DvM+): if that lane registers a weighting, Staff Gems adopts it in
  the baseline only in a compliant form (continuous eFV, never consensus-FV cells).
- **Handled outside this workflow, referenced only**: the projected $/WAR path (VAL_5), the
  PLUS% board column removal, and the 2026 MiLB season for eFV drivers. None is an input here;
  the 2026 grade lists enter the gate frame only as grade pairs.

---

## Appendix A. Probe log (2026-09-30, about 250 StatsAPI requests at 0.2-0.5 s spacing; saved under `_finalpass_2026-09-24/part8/staff_gems_work/`)

| # | Request | Result |
|---|---|---|
| A1 | `teams/147/coaches?season=2026` | 11 rows (manager, bench, hitting, 2 assistant hitting, pitching, 2 assistant pitching, first-base, third-base, a field coordinator titled "Coach"); every row has `person.id`; the MLBAM copyright line in the payload |
| A2 | `teams?sportId=11,12,13,14,16&season=2026` | 30 teams each at AAA, AA, A+, A; 81 at sportId 16 (complex and DSL); Yankees: 1 complex, 2 DSL |
| A3 | `teams/affiliates?teamIds=147&season=Y`, then each affiliate's coaches, Y = 2005, 2008, 2012, 2015, 2017, 2019, 2021, 2023, 2025, 2026 | staff per MiLB team: 0-2, 0-4, 1-4, 2-5, 4-5, 4-5, 4-9, 4-7, 4-8, 4-7; MLB 8-12; the Organization, Futures and Alternate Training Site pseudo-teams list 0 (2 in 2021) |
| A4 | Yankees coaches 1960, 1975, 1985, 1995, 2000 | 7, 7, 13, 8, 10 rows; two different managers in 1975 and in 1985 (season lists are unions); the 1960 list carries one manager twice, so the ingest de-duplicates |
| A5 | Nationals coaches `date=2025-05-01`, `date=2025-09-01`, `season=2025`; then bisection | in May the manager and the bench coach; in September the former bench coach as "Interim Manager" and the former catching coach as bench coach; the season list holds both; last day of the old staff 2025-07-06, first day of the new 2025-07-07, 9 requests |
| A6 | Scranton/Wilkes-Barre `date=` 2025-05-01, 2025-08-15, 2012-06-01; Trenton (567) and GCL Yankees East (475) on four 2019 dates | MiLB date queries work; a hitting coach at Trenton on 04-10 and 06-01 and at the GCL on 07-15 and 08-25; Trenton lists no hitting coach on 07-15 and 08-25 |
| A7 | affiliates and coaches for TBR, LAD, COL, ATL in 2012 and 2024 | 2012: 0-5 per affiliate (two VSL teams 0, three DSL teams 1); 2024: 3-12; 331 of 331 rows with a person id; titles include "Performance Coach", "Infield Coach", "Coordinator, Baserunning" (DSL Dodgers 2012) and one "First Base Coach" (FCL Rays 2024) |
| A8 | `teams/{id}/personnel` for NYY 2012, 2019, 2026; LAD 2026; TBR 2026; Yankees Organization 2021, 2025; SWB 2025 | NYY returns the same 27 names for every season (season ignored); LAD 0; TBR 21; Organization 0; SWB 1 |
| A9 | `transactions?teamId=120&startDate=2025-07-01&endDate=2025-07-20` | 34 rows (status change 8, optioned 8, signed 6, recalled 5, assigned 4, signed as free agent 3); no staff row |
| A10 | robots.txt: mlb.com, milb.com, statsapi.mlb.com, baseballamerica.com, thebaseballcube.com, en.wikipedia.org, baseball-reference.com, retrosheet.org | as summarized in 2.1; statsapi returns 404 |
| A11 | `gdx.mlb.com/components/copyright.txt` | "Only individual, non-commercial, non-bulk use of the Materials is permitted and any other use of the Materials is prohibited without prior written authorization from MLBAM." |
| A12 | page reads: milb.com Scranton/Wilkes-Barre roster; the Rays 2024 staff press release; TBC minor-league managers index; TBC terms (403 to the fetch tool); Retrosheet biofile page; FanGraphs RosterResource coaches | as summarized in 2.1 |
| A13 | archived DB backup, read-only and immutable (`db_coverage_probe.py`) | section 3.2; no grade deltas, no outcomes |
