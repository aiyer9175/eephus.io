# EXECUTION 2026-08-05: omnibus-2

Execution record for `docs/master-plan-2026-08-05-omnibus2.md`. That doc holds the lane
definitions, the banned-experiment ledger (section 2), the memory corrections (section 3)
and the owner decision queue (section 4). This one records what actually happened against
it. Where the two disagree, the plan is the intent and this is the outcome.

**Range:** `f20e85c..HEAD`, 22 commits at the time of writing (`1771eb1`), 17:08 to 23:00
ET on 2026-08-05. Other agents were still committing while this was written, so recount
at read time (`git rev-list --count f20e85c..HEAD`) rather than trusting the 22.

**Suite:** baseline expectation 3,395 (plan W0.1). Recorded 3,409 passed at `dc8c8f1`,
3,412 passed at `54474aa`. Cite the recorded number, do not re-run pytest to restamp an
artifact (plan K8).

**Honest summary in one paragraph.** The plan's wave order did not survive contact. The
owner reported six live defects during the session and correctness-first was the standing
instruction, so Wave 1 (Lane F) expanded to fill the day and Waves 2 through 5 barely
started. Lanes C, D, J and K are essentially untouched; G and H got only the pieces that
rode along with a bug fix. Two of the six bugs took more than one attempt, and in both
cases the first attempt failed for a reason worth more than the fix itself. A defect class
was found underneath three of the outages, swept across fifteen modules, and then found to
have been silently voided in production by an eleventh defect of the same family. The most
useful content below is the failures.

---

## 1. The six owner-reported bugs, with the root causes that were actually true

Ranked by how much the reported symptom misled the diagnosis.

### 1.1 Alexander Frias served as a Brewer. THREE attempts.

Symptom: days after St. Louis traded for him, `/prospx/` and the org pages showed
Alexander Frias as Milwaukee's 5th-best prospect. Nothing was missing from the data. MLB's
transaction feed carried the trade on 08-03 with a full description, and our own `trades`
table held the correct row.

- **Attempt 1** (`cf480ff`). Diagnosis: `consensus._latest_meta` resolves org as "whatever
  the newest snapshot says", and its own comment asserted that "no source has a meaningful
  claim to be more authoritative on org", which is false against MLB itself. On 08-04 the
  newest snapshot was MLB Pipeline's *Brewers* Top 30, which had not dropped him yet, so
  the losing club's freshly scraped page outranked the league's own record. **178 players
  were in that state.** Added `storage.authoritative_org_map()` reading
  `player_transactions`, applied at the export seam (consensus cannot do it; storage
  imports consensus). Frias did not move.
- **Attempt 2** (`2802a2f`). The override required the authoritative event to be STRICTLY
  newer than every snapshot behind the served org. Both sides are day-resolution and a tie
  was exactly the reported case: MLB recorded the trade 08-03 and his Palm Beach
  activation 08-05, a prospect list published the losing club on 08-05 too. Ties now go to
  MLB. Served artifact went from 5 correct players (none of them Frias) to 6 including
  him. Frias still did not move on the real board.
- **Attempt 3, the actual root cause** (`7deac20`). Neither `players.org` nor `_latest_meta`
  produces the served org. **`storage._active_display_org` does**, and nobody had found it
  through two fixes. Its trade branch took the most recent trade BY DATE regardless of
  source, and the `trades` table holds two different KINDS of row. `mlb_api` rows are
  parsed from MLB's feed and state a trade that happened. **`inferred` rows are DEDUCED
  from a player appearing under a different org across two prospect-list snapshots**, so a
  publisher slow to drop a traded player manufactures a phantom trade BACK to the club
  that traded him, dated later than the real one. Frias had exactly that: `mlb_api` 08-03
  MIL to STL, then `inferred` 08-04 STL to MIL written off the stale Brewers Top 30. **The
  fabrication was newer, so it won.** Now: if MLB's feed has ever recorded a trade for a
  player, the latest of THOSE decides and an inference cannot overrule it; inferred rows
  still settle the case the feed never saw, which is what they were added for.

Result after the attributed rebuild (`895c666`): **1,492 players** sit on the club MLB's
feed reports rather than the one a stale list last printed. Frias STL, aiden_may COL,
angel_rivero LAA, anthony_eyanson BAL, brayden_taylor MIA, each matching its `mlb_api`
destination. 30 orgs, no non-canonical codes, 4,584 players.

**The lesson, stated plainly: two fixes were shipped against resolvers that were not the
one producing the served value.** Both were real improvements and neither moved the
reported player. The cheap check that would have collapsed three attempts into one is to
trace the served field backwards from the artifact to its writer before touching any
resolver that looks plausible. `_active_display_org` is at `storage.py:9205` and its
precedence is now: cross-org transaction feed, then trades (mlb_api first, within 365
days), then `roster_org_by_key`, then `p.org`.

### 1.2 Clipped player names on the board. TWO attempts.

- **Attempt 1** (`11f643a`). `.mlb-name` carries `overflow:hidden` for its ellipsis, which
  makes it a grid item with an automatic minimum size of 0, so it was compressed to a
  17.66px box around a 22px line box and quietly ate 4px off the top of every name. The
  104px card promise had been set from a 40px measurement of an identity block that
  actually needs 44px. Fixed by tightening the name leading, centring the inline team logo,
  and giving the card 108px. Verified 0 clipped names across 25 rows in both themes.
- **The owner reported it clipped again.** That is the tell that the instrument was wrong,
  not the number. **The first fix tuned pixel values (leading 1.2, card 108px) against
  metrics measured in headless Chromium.** Real MS Gothic is a CJK face whose ascent plus
  descent exceed its em box, so its natural line box is taller than a Latin face at the
  same size, and it differs between this sandbox and a Windows machine with the font
  actually installed. **Any fixed height picked from one machine's metrics is a guess about
  every other machine.**
- **Attempt 2** (`2b6c286`). Made the rule metric-INDEPENDENT: 108px became a `min-height`
  rather than a height, the identity rows are min-content floored so `.mlb-name` cannot be
  compressed below its own line box, and the name keeps its natural leading.
  `overflow:hidden` stays because it drives the horizontal ellipsis, but it is never asked
  to clip vertically. Verified by STRESS test rather than measurement: forcing line-height
  2.1 at 19px, far beyond any real font, clips ZERO names and grows the card to 126px. The
  old rule sliced text under the same input. Same treatment for the FA board, which shares
  the primitive and the failure mode.

**Generalisable rule: a layout defect that depends on font metrics cannot be closed by a
number measured on one machine. Close it with a constraint and prove it with a stress test
that exceeds any real input.**

### 1.3 The whole site rendered in SF Mono on Apple devices (`11f643a`)

MS Gothic is the primary face for roughly **315 declarations**, so every Mac and iPhone
visitor read the entire site (body, headings, tables, even the nav wordmark) in SF Mono.
PixelMplus12 now sits behind MS Gothic in both copy tokens: an M+ bitmap-gothic
conversion, same genre as MS Gothic's embedded strikes, 12px-native to match the site's
12-14px copy. **The decisive filter was `font-synthesis:none`**, which means a
single-weight face silently flattens every bold, so the pick had to have a real 700.
**6.2KB + 5.4KB** subsets for two weights, less than the existing single-weight
DotGothic16 file. Windows renders byte-identically and never downloads it. The subset
lacks 6 symbols (compare glyphs, minus, check, command); not a regression, Apple already
rendered those from fallback.

### 1.4 Offense+ neutral everywhere, DFS slate empty. TWO commits, one wound.

- `0b579c7`: `bullpen_export._team_abbrev_map` returned `{}` on failure, which reads as
  safe and is not. The map joins onto every hitter and reliever row, so an empty map blanks
  every player's team, the team rollup then produces ZERO team offenses, and Offense+ falls
  back to the neutral 100 for every opponent. Measured: **30 team offenses in the committed
  artifact, 0 after a rebuild whose team fetch failed, and all 59 streamers carrying
  opp_off 100 with a matchup multiplier of exactly 1.0.** The opponent adjustment the page
  advertises was inert. Now persists the last good copy at `.cache/team_abbrev_map.json`
  and returns `{}` only if it has never succeeded.
- `7143e2c`: **the exporter fix stopped the bleeding but did not heal the wound.** A
  player's team is written by `fantasy_export._enrich`, which runs ONLY on the monthly path
  via `build_players`; `refresh_live` reuses the frozen players array. So the leaderboard
  healed (618/618 hitters carry a team) while `fantasy.json` still had 592 of 592 hitters
  blank, and `/dfs/`, which indexes hitters BY TEAM, served 15 games with 29 players and
  zero hitters. Rebuilt through the monthly path and re-priced:

  | quantity | before | after |
  | --- | --- | --- |
  | fantasy hitters with a team | 0 / 592 | 502 / 592 |
  | dfs players | 29 | 421 (392 hitters) |
  | dfs opp_off | 100 on 30/30 | spread 92..108 |
  | dfs matchup multiplier | 1.0 on 29/29 | 0.861..1.09 |

  The 90 hitters still without a team are genuine leaderboard join misses (low PA), not
  the blanking bug.

**Lesson: a cache written on one path and consumed on another needs the fix applied on
both. Fixing the producer while a frozen consumer copy survives leaves the user-visible
symptom fully intact.**

### 1.5 The betting board had no data (`f3bd611`, `fdddb27`)

`deploy/nightly-build.sh` had **ZERO references to `EEPHUS_ODDS_API_KEY`** and never
sourced `/etc/eephus.env`, so `run_daily` step 9e (betting odds snapshot) **has never once
fired on the box.** `data/betting_status.json` reported `configured: true` next to
`n_snapshots_cached: 0`: the key exists in the repo `.env`, which nothing loads. The
module was never waiting on a data source, it was waiting on one shell line. The gap
survived review because the close-job crontab already sourced the same file and looked
like proof the wiring was done.

Fixing the wrapper fixed ONE entry point. `fdddb27` moved secret loading into the pipeline
itself (`_load_env_files`: `/etc/eephus.env` first, then the gitignored repo `.env`), so a
direct `python run_monthly.py`, an `EEPHUS_FULL=1` one-off, or any cron line someone writes
later all get the key. Two tested properties: it NEVER overrides an already-set variable,
and it logs variable NAMES only, never values, because these logs are kept 30 days.

The betting lane also produced two measurements worth keeping:
- **The close job was firing SIX HOURS EARLY** because a FINAL game anchored the close
  window (18:10Z vs the correct 22:35Z). Every "closing" line it captured was worthless,
  and CLV is unrecoverable after the fact.
- The park leak (plan F1.1) was **materially** contaminating, not just theoretically: a
  poisoned-live-index test shows the old code used it, and with real vintage parks the
  Brier moves 0.25116 vs 0.25128.
- Today's board prices 11 games where the served artifact had 0.

### 1.6 Team charts showed departed players and their replacements at once (`939a076`)

StatsAPI season-stat rows carry the club a player's stats were EARNED with, so Tarik
Skubal stayed in Detroit's rotation chart after the Dodgers traded for him on 08-02 while
Detroit simultaneously showed the arms it had acquired. Teams accreted arrivals and never
lost departures. **56 rows were in that state (14 starters, 42 relievers).** Owner decision
and dissent are in section 4 below.

Two traps the remap handles: it compares CANONICALISED orgs, because a naive compare
reports 51 starter "moves" of which 36 are one club spelled two ways (TB/TBR, AZ/ARI,
CWS/CHW); and it emits in the artifact's OWN dialect, learned from the codes already
present, because `/mlbstats/` deliberately speaks StatsAPI and rewriting TB into TBR would
break its joins. Verified Skubal DET to LAD, Peralta NYM to TB (not TBR), Stratton PIT to
SD (not SDP).

### Also shipped while in there, not owner-reported

`0300437`: `--border-subtle` was referenced in nine places and **defined nowhere.** A
`var()` chain that resolves to nothing invalidates the whole declaration at
computed-value time, so those borders did not degrade to a default hairline, they fell
back to `currentColor` and painted at full text strength. Visible on the Trade Machine
search box and group panel, `.proj-viewnav`, and six PROSPX drawer rules. Defined as an
alias of `--border-light` in both token blocks; verified light `#E2DCC9`, dark `#1D1D21`,
neither equal to the element's color.

---

## 2. The single defect class behind three separate outages

**A fetch or join that fails into an EMPTY-BUT-VALID result, indistinguishable downstream
from "legitimately no data".** Nothing raises, nothing logs at error level, a served
artifact publishes blank or neutral, and it stays invisible until a human notices. Three
user-visible outages in one day were this one shape:

1. `fantasy_export.refresh_live` published a schedule with ZERO game days after a StatsAPI
   hiccup, which dark-started FOUR surfaces at once: redraft streamers, two-start, the DFS
   slate, and the betting board. Nothing errored, because an empty slate is legitimate in
   the off-season.
2. `bullpen_export._team_abbrev_map` returning `{}` (section 1.4).
3. Downstream of 2, `_start_score` did `(...).get("offense_plus") or 100`, so the fallback
   itself was invisible.

The sweep (`dc8c8f1`, 15 modules) used the two postures already proven in this tree:
**None-as-sentinel** (`bullpen_export._active_mlbam_ids` returns None on failure
specifically so the caller does not filter: "never break the board") and **keep-previous
plus an ingest-health RED**. Also closed in that pass: the park leak at its source
(`leaderboard_vintages` SCHEMA 1 to 2 stores the park index in each nightly record, and a
record predating the column yields None so the caller substitutes a NEUTRAL index rather
than reaching for the live one, which is the leak itself); doubleheaders no longer collapse
to one odds event; postponed games leave the slate and the closing window; the close job
refuses to fire on a stale slate date or an unreadable snapshot; `/ifa/` serves the board
eFV basis instead of a retired field.

The `/ifa/` number is the sharpest single measurement of the day. It had been reading the
retired `xfv_grade_quantile`, which ran roughly 2,000 rows **+12.3 FV hot** against the
served board. After re-export on the corrected basis (`35ed5e7`): fv vs board_value
**n=2,014, mean +0.000, max 0.00**, an exact match. The same player finally reads the same
grade on `/ifa/` and PROSPX.

Three cautions this sweep produced, each of which is a way the fix can be worse than the
bug:
- **"Honest but empty" can be worse than the bug.** Stripping the platoon `orders` block
  fired in exactly today's data state (bats null 618/618) and would have emptied BOTH the
  mlbstats lineup chart AND betting hitter props. Publish an availability flag BESIDE the
  data, never instead of it.
- **A guard can reintroduce the class it fixes.** The DFS `matchup_orgs_resolved` guard
  counted the PRODUCER's ctx rows, not whether the orgs the SLATE needs actually resolved.
- **Carrying a previous board with no CLIENT-VISIBLE staleness stamp is less honest than
  the empty state it replaces.**

---

## 3. THE GOTCHA: the RED ledger that never fired

Read this before trusting any "it files a RED" claim anywhere in this repo.

`deploy/nightly-build.sh` launches the pipeline as a SCRIPT (`python run_monthly.py`), so
the live pipeline is `sys.modules["__main__"]` and **the name `"run_monthly"` was
UNCLAIMED.** Every helper doing `from run_monthly import _record_ingest` therefore built a
**SECOND module object with its own empty ledger**, and `write_ingest_health` drained the
first. The record went into a throwaway.

**Measured: 0 of 1 filed rows reached the payload before the fix, 1 of 1 after.**

This silently voided most of the RED guards shipped earlier the same day, which is why it
is the most dangerous finding in this record: the sweep in section 2 looked complete and
was not. The fix (`54474aa`): `run_monthly` claims its own name in `sys.modules` on startup,
repairing all ten call sites at once, and `bullpen_export` gained an explicit live-module
resolver.

There was a **second half** to the same defect. `SCHEDULED_GRADE_SOURCES` is an ALLOW-LIST,
so a correctly filed record from a source not on it was dropped at drain time anyway. A new
`SCHEDULED_EXPORTS` tuple is now drained into `red[]` beside it. Exports are judged on `ok`
alone, not row count, because a healthy export can legitimately roll up zero.

**Standing rule from this: before believing any error-reporting path, prove it end to end
under the `__main__` launch shape the box actually uses.** A module-identity bug is
invisible to every test that imports the module normally.

---

## 4. Owner decisions taken, with dissent preserved

Eight decisions were taken live. The plan's section 4 queue is the source for the ones that
were pre-answered.

1. **Font: PixelMplus12.** Shipped.
2. **Diamond extras: build exports/API + alerts, cut the newsletter.** Partly done in
   `54474aa` (documented data catalog + CSV exports, an eFV movement alert FEED with
   delivery left unwired and SAID so, newsletter card reworded rather than left as an
   unbacked claim).
3. **RP to SP re-gate: run BOTH targets, report both.** NOT started (Lane E3).
4. **CLV storage: sidecar artifact.** NOT started (plan F2.2).
5. **Team basis: remap `team` everywhere.** OWNER OVERRODE the dual-field recommendation.
6. **Silent-failure sweep: full sweep plus guards.** Done (section 2), then repaired
   (section 3).
7. **Priority: correctness first.** This is why the lane order did not hold.
8. **Beta: KEEP HOLDING.** `origin/beta` still at `03c1428`, untouched.

### The dissent on decision 5, on the record

`bullpen_export.TEAM_BASIS="current_roster"` repoints `team` at the club MLB's transaction
feed reports today, for the charts AND the aggregates. The revert is that one constant.

**The aggregates are computed from these same rows, so an August acquisition now has his
entire season credited to his new club and removed from the one he actually pitched for.
Rotation+, Bullpen+ and Offense+ change basis. Those feed `betting_model` AND the nightly
`leaderboard_vintages` that the 600-game validation clock is accruing, so vintages captured
before 2026-08-05 are NOT on the same basis as vintages captured after it.** The
recommendation was to carry a second `current_team` field and leave the aggregate basis
alone; the owner chose the single remap.

Consequence for whoever reads the betting gate later: the vintage archive now has a basis
seam dated 2026-08-05. Either treat pre-seam vintages as a separate cohort, or accept that
the first 600 graded games straddle two definitions of team strength. This is not an
argument to revert; it is a fact the gate write-up must state.

---

## 5. What is still open

### 5.1 FA: 79 of 228 class members are unpriced, and it is NOT root-caused

Measured against the current `data/fa_class.json` (generated 2026-08-05, class_year 2027):

| quantity | value |
| --- | --- |
| members | 228 |
| n_projected | 149 |
| unpriced (verdict null) | 79 |
| of those, pitchers | 78 (51 SP, 26 RP, 1 P) |
| of those, non-pitchers | 1 (Tyler Austin, 1B) |
| pitchers in the class | 138 total, 60 priced, 78 unpriced |
| unpriced rows with `warPath` empty | 79 of 79 |
| unpriced rows with `totalSrc` null | 79 of 79 (priced rows are all `mc_copula`) |
| unpriced rows carrying `prevAav` | 78 of 79 |
| unpriced rows carrying `comps` / `fits` | 0 of 79 |

Names in the unpriced set include Skubal, Ray, Imanaga, Gallen, Woodruff, Gausman,
Bassitt, Flaherty, Taillon, McCullers, Scherzer, Bieber.

**This is IDENTICAL in the pre-session artifact, so it is a standing defect and not a
regression from anything shipped today.** What the numbers narrow it to: the rows exist,
identity resolved on the contract side (`prevAav` present on 78 of 79, `bt` on 79 of 79),
but **the WAR path is entirely absent, so the copula never runs and no price is produced.**
The gap is upstream of pricing, in whatever supplies `warY1`/`warPath`. It is
pitcher-concentrated but NOT wholesale: 60 of 138 pitchers do project, and SP is hit far
harder than RP (6 of 57 SP priced vs 54 of 80 RP). **Status is not the discriminator**:
unpriced splits 50 locked / 29 pending_option, priced splits 101 locked / 48 pending_option.

A correction to the earlier in-session note, which said 77 pitchers and 61 of 138: the
measured values are **78 and 60**.

Next session: start at the `warPath` producer, not at `fa_market`. A subset condition that
tracks SP much harder than RP smells like an innings or games-started threshold, or a
projection-source join that pitchers with a certain role history fall out of.

### 5.2 Five residual org violations behind a THIRD precedence layer

`test_org_authority` **stays red on five players and was deliberately left red rather than
weakened.** They share a different mechanism from the Frias case: very old snapshots plus a
transaction older than the 365-day trade window, so they fall through to
`roster_org_by_key` (`storage.py:9267`), a third precedence layer that also outranks the
reconciled value. That is real remaining work and the test should keep saying so. Do not
"fix" this by loosening the assertion.

### 5.3 Lanes not started

- **Lane C (eFV/consensus improvement):** untouched. Note the plan's C3 re-powered protocol
  is the ONLY route back for `sb_rate_rel`, and B3 is closed per the banned ledger.
- **Lane D (FA/AAV):** untouched. D1 (instrument the recal engagement before repairing) is
  still the correct first move and is now doubly motivated by 5.1.
- **Lane J (creative additions):** untouched.
- **Lane K (artifacts + registry):** two small pieces only. `d48b7fd` regenerated
  `MODEL_REGISTRY.md` after the Wave-0 monthly rewrote the registry's freshness stamps, and
  `f9e60bc` dropped a "PROPOSED ... Not applied; owner merges" marker from the
  `pal_conversion` row that was simultaneously carrying the merged content it proposed.
  **The ten published artifacts are all still describing a pre-session repo** (index,
  roadmap, how-eFV-works, SABR, monetization, webmaster runbook, beta-diff, private-plan,
  writers-guide, branding). Their stale suite counts and commit ranges are listed per
  artifact in the plan's Lane K; five of them have never been fetched by any recon.
- **Lanes E, G, H, I:** only what rode along with a bug fix. Notably Lane E1 confirmed the
  ladder is already correct and zero-summing (plan correction #5), and this session
  corrected the `/pal/` meta strings (section 6); the stale `pal.js:907-908` comment
  claiming R2 0.9779 / 9,101 is still there.
- **Lane A:** the prune dry-run is recorded in the plan (18.78 GB of versioned orphans,
  nothing age-prunable); the prune itself is not run.

### 5.4 Box actions still owed

Plan section 4 decision 9 is unchanged and none of it has run on the box. The two most
consequential: production stays inert on the fv_synthetic_only routing until the box
regenerates ITS OWN `rosters_by_org.json` (gitignored, cannot travel via git), and the
nightly cron line must source `/etc/eephus.env` or 9e never fires. `fdddb27` reduces the
blast radius of the second but does not remove the box work.

---

## 6. Smaller items with numbers

- **Golden fingerprint restamped twice**, both with the changelog entry the tripwire's
  contract requires. `35ed5e7` for the attributed routing regen (`by_player` 9,268 to
  9,379; the `fv_synthetic_only` fix changes no served number by itself, it stops 2,632
  constant-FV-35 players reading as "scouted" and routes them to the model built to grade
  them). `895c666` for the org rebuild, where **no eFV model input moved**: same 9,379 rows,
  same features, same lambda, same calibration, and the fingerprint changed only because
  org rides inside the hashed payload.
- **`/pal/` meta strings corrected** (this session, `build_site.py` `build_pal`). All three
  social strings come from one literal, which claimed the fitted positional ladder was
  "computed from Statcast". It is not: `positional_fit.fit_ladder` is a no-intercept least
  squares of Baseball-Reference's own `runs_position` per 650 PA on innings SHARES, which
  recovers the constants BRef used (r2 **0.9759**, **4,968** player-seasons 2012-2026, min
  200 PA; `data/positional_fit_ui.json` `ladder.method` states this and the Position Fit tab
  shows it). Statcast feeds arsenal shape, velocity, platoon splits and the OAA the fielding
  side reads, so the attribution is now split rather than deleted. The tab list was also
  stale: Pitch-Add Lab, Reverse-Platoon Radar and Prospect Watch all shipped after the copy
  was written. New string is 296 chars, down from 325. **The served `pal/index.html` still
  carries the old text until the next `build_site.py` run.**
- **Verified not broken, do not re-chase:** TJStats API fully healthy on all three
  endpoints (only `SOURCE_PAGE` was stale; the old URL 301s, ingestion never used the HTML
  page). MLB Pipeline daily re-scrape wiring is correct; the 08-04 capture simply predated
  MLB's own list update. A module and section health sweep over every route and tab found
  **no silently-dead sections**; PAL's seven tabs all render.
- **PROBE LESSON:** two successive "empty section" findings were FALSE POSITIVES from a
  probe counting only `tbody tr` and `.mlb-card`. Several modules render card grids under
  private classes (`.pal-mix-card`, `.rd-team-card`, `.rd-relief`). Any future health probe
  must enumerate a module's own class names, not the shared primitives.
- **Sandbox constraints that shaped the day:** SSL fails here for baseball-reference,
  tjstats and statsapi.mlb.com. `starter_export`/`bullpen_export` leaderboards could NOT be
  regenerated locally because `load_season_pitching` fetches live, while `hitter_export`
  goes through the CACHED `fa_sources.fetch_statsapi_season_stats`; the first two regenerate
  on the box. The ingest-health RED ledger correctly fired for tjstats, which is the one
  positive validation that mechanism got before the section-3 gotcha was found.

---

## 7. Process failures worth carrying forward

1. **`git add -u` is the same hazard as a pathless commit.** It swept 55 regenerated data
   files into `35ed5e7`, whose message described only the golden restamp and the IFA
   re-export. The CONTENT was coherent and belonged together; the MESSAGE was not honest
   about what landed. Disclosed in a follow-up commit (`e854253`) rather than quietly left.
   Commit with explicit paths, always, and doubly so while other agents are active.
2. **Two of my own regressions were caught only by adversarial review**, not by the suite:
   the platoon `orders` strip and the close job's refusal boundary reading the bettable-only
   slate (which EXCLUDES already-started games, so it could fire AFTER first pitch, the
   exact thing `test_it_refuses_at_and_after_first_pitch` exists to prevent). Both landed
   inside a commit whose stated purpose was fixing silent failures. **A correctness sweep is
   itself a source of correctness bugs and needs its own review pass.**
3. **A test pinned against the wrong contract hides a real regression.**
   `test_fantasy_split`'s DFS empty-slate test pinned the old one-message contract against a
   payload shape the exporter no longer emits. Updated to the real contract and given its
   inverse: a pipeline outage must NOT claim nothing is broken, and an unknown kind must not
   be styled as a confirmed outage either.
4. **The plan's wave order is a budget, not a schedule.** Six live bugs consumed it.
   Correctness-first was the right call and the record should not pretend the lanes were
   deferred for any cleverer reason.

---

Cross-references: `docs/master-plan-2026-08-05-omnibus2.md` (lanes, banned ledger section
2, memory corrections section 3, owner queue section 4, Lane K artifact list),
`docs/EXECUTION_2026-08-05-omnibus.md` (the prior omnibus), `docs/EFV_GATE_STANDARD.md`
(the gate any model change must clear; no model shipped this session, so none was invoked).
