# Development attribution: credit to the club that developed the player

Status: design for VAL_4 (writer queue 7). Written 2026-10-08, before the build.
Owner answer FP2-4 (2026-09-25, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md:378`), verbatim:
"Developing club, but make sure we're accurately describing this - you should give credit to
the club that actually develops the player, not just the club that signed/acquired them - we
should be able to accurately attribute development using DvM+ ?"

Census finding X03-11 (master plan 2026-09-24, line 1232): graduates and farm finance credit the
current club with another club's development and bonus.

## 1. What credits whom today

| Surface | Today | Where |
|---|---|---|
| Graduate leaves of the farm grade (WAG, WAR per $M, graduate contract surplus, MLB production, Conviction, HoF track, draft and IFA channel leaves) | every graduate counts in full at his CURRENT club, "per user's choice" | `storage.py` graduate pass (`grad_agg`, "All grouped by graduate's CURRENT org") |
| ToolDvM+ and the per-tool DvM+ | each active prospect's LIFETIME tool delta (latest minus first consensus tool grade) credited to his CURRENT org | `storage.py` actives loop (`_tool_dev_sums`, `_compute_tool_deltas`) |
| DvM+ (org development trajectory) | growth while owned, with trades as the only org changes; a player with no trade on file is placed at his CURRENT org for his whole history, so a graduate who left by free agency or waivers credits his new club | `storage._build_org_fv_history` |
| Front Office toolDev | same-source pairs inside one org, the org read off each snapshot row; non-FanGraphs rows stamp the org at ingest, not the org on the list date (Tarik Skubal's 2019 to 2021 Pipeline rows read LAD) | `org_tendencies.tool_dev_panel` |
| Front Office graduation panel (graduates per year, mean graduate WAR) | the `org` field on the debuts row, which is the current club | `org_tendencies.graduation_panel` |
| Club Ledger graduates block | the debuts rows whose current club is the club | `ledger_export.py` (`grads_by_club`) |
| PROSPX farm "Recent graduates" | the debuts rows whose current club is the club | `prospx/index.html` `makeFarmGraduates` |
| Franchise | the FARM branch reads the PROSPX farm letter, score and leaves; the Front Office block reads the graduation panel | `franchise_export.py` |

Example: Tarik Skubal, drafted and developed by Detroit (2018 to his 2020 debut), traded to the
Dodgers on 2026-08-02. Every surface above credits his career WAR to LAD today.

## 2. The org calendar (tenures)

Every player's dated history is cut into ORG TENURES `(org, start, end)`, end exclusive.

Source, in this order:

1. **Dated transactions** (`player_transactions`, the StatsAPI payload). A join opens a tenure with
   the receiving club: signed (SGN), signed as free agent (SFA), drafted (DR), trade (TR), waiver
   claim (CLW), Rule 5 (R5, R5M), returned (RTN), acquired or obtained (ACQ, OBT), purchase (PUR),
   contract purchased (CP). A release (REL), an election of free agency (DFA in this feed) or a
   retirement (RET) opens an UNAFFILIATED stretch (org None). A signing with a club outside
   affiliated ball (an independent or foreign club) is also unaffiliated. Assignments, options and
   recalls never change the club. The receiving club resolves from the team id through
   `staff_units` (the season's affiliation map), else from the team name. Releases before the first
   club (summer and college teams) are ignored. Before the first join the player sits with the first
   club the events name (a list can publish him before the signing posts).
2. **Trades** (the farm history's existing rule) when there is no usable payload, or when an active
   prospect's payload ends at a club other than his current one (a missed move).
3. **The listed org** (the last point-in-time org before the debut, `ConsensusPoint.org`) for a
   graduate with neither, then his current org.

The calendar ends at the end of development: the MLB debut date for a graduate, today otherwise.
What a graduate does after his debut is not development by a farm and is never apportioned again.

Why not `player_location_spells`: the Staff Gems stage 1 table carries a season-rollover artifact
(a player assigned to an affiliate in one season keeps that team id into January of the next, where
the next season's affiliation map can name another club; Trevor Rogers reads PIT for 2019-01-01 to
2019-03-31 while a Marlins prospect). Dated joins never consult the affiliate map for anything but
the receiving club of the join itself, so the calendar does not inherit it. Staff Gems keeps its own
unit calendar; section 9 states the interface.

## 3. Tenure growth

- **Pairs.** Same-source consecutive grade pairs: one outlet's list to that outlet's next list on
  the same player (FanGraphs, MLB Pipeline, Baseball America, ESPN, Just Baseball, TJStats). The
  rule org_tendencies' toolDev already keeps, so cross-source noise never reads as development.
- **Split.** A pair `(a, b]` that spans an org change is split by days across the tenures it spans,
  instead of being dropped (toolDev drops 1,341 such pairs today).
- **Scale.** Growth is measured on the expected-WAR scale of the FV grade, the FanGraphs primer
  table `storage.FV_EXPECTED_WAR` that DvM+ already uses, so a 55 to 60 jump (6 to 12) counts more
  than a 40 to 45 jump (0.5 to 1.5). Tools use the same table on the tool grade, as ToolDvM+ does.
- **Combining outlets.** A tenure's growth is the mean, over the outlets that observed any part of
  it, of each outlet's split growth in that tenure.

## 4. Shares and the apportionment formula

For player `i` with tenures `k = 1..K` at clubs `org(k)`:

- `V0` = expected WAR of the first listed grade (mean over the outlets listing him on that date):
  the value at acquisition.
- `g(k)` = the tenure growth of section 3.
- `credit(c) = V0 [c = signing club] + sum over tenures k at club c of max(g(k), 0)`.
- `share(c) = credit(c) / sum over clubs of credit`. The shares sum to one.

Rules: a tenure that lowered the grade earns zero, never a negative share; growth while
unaffiliated credits nobody; with no positive credit anywhere the signing club takes the whole
share. The signing club is the club of the first dated join; without a payload, the drafting or
signing club on the acquisitions row (a draft or IFA signing), else the first tenure's club. (The
acquisitions row is not trusted over a dated signing: Max Schrock's row is the unsigned 2012
Arizona pick; he signed with Washington in 2015.)

A graduate's realized MLB value is apportioned by these shares: club `c` is credited with
`share(c) x WAR` (and the same share of every other per-graduate outcome below).

Worked examples (prospects.db as of 2026-10-07):

| Player | Tenures | V0 | Growth by tenure | Shares |
|---|---|---|---|---|
| Tarik Skubal | DET 2018-06-20 to debut 2020-08-18 | 6.0 | DET +0.75 | DET 1.00 (current club LAD gets 0) |
| Jakob Marsee | SDP 2022-07-30 to 2024-05-04; MIA to debut 2025-08-01 | 1.5 | SDP 0.0; MIA +0.63 | SDP 0.70, MIA 0.30 |
| Enmanuel Valdez | HOU 2015-07-02 to 2022-08-01; BOS to debut 2023-04-19 | 0.1 | HOU +0.4; BOS +1.0 | BOS 0.67, HOU 0.33 |

This is accounting, not a causal estimate: it says where the measured grade growth happened, not
what a club added. No statistic here compares a grade with an outcome: grade changes only decide
the split, and no realized-WAR mean, residual, count or anchor is computed by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`). Nothing is fitted; no gate constant, blend weight or served
accuracy claim changes.

## 5. DvM+ and ToolDvM+ on tenures

- **DvM+** keeps its grade series (the eFV grade at each snapshot, consensus fallback) and its
  rule (the first snapshot at a club plants a baseline, later snapshots credit the expected-WAR
  delta). What changes: the club at each date comes from the calendar of section 2 instead of
  trades alone, and a snapshot-to-snapshot step that spans a club change is split by days between
  the two clubs instead of going wholly to the receiving club. Unaffiliated stretches credit
  nobody.
- **ToolDvM+** (and the per-tool and per-bucket DvM+ it feeds): each active prospect contributes,
  per tool, his tenure growth from section 3 to each club that held him, not his lifetime delta to
  his current club. The level weight is unchanged (the prospect's current level).
- **Front Office toolDev** keeps its rule (same-source pairs at least 60 days apart, grade points
  per prospect-year) with the club read off the calendar; a pair that spans a change is split by
  days, delta and exposure years alike.

## 6. Graduate leaves

A graduate counts in each club's graduate pool by his share. Sums are share-weighted (the WAR
credited to the club), counts are share-weighted (graduate-equivalents), means are share-weighted
means, and every sample gate (at least 3 graduates, at least 5 settled) reads the share-weighted
count. A single-club graduate (the large majority) counts 1.0 at that club, as before, but at the
club that developed him rather than the club he plays for now.

- **Development and production leaves** (WAG and its hitter and pitcher splits, career WAR and WAR
  per year by side and position bucket, boom and bust rates, graduate contract surplus, top-3
  graduates, Conviction stars, HoF track): every developing club, by share. Graduation pace and
  the graduation pipeline count a debut at the club that held him on his debut date, read off
  the calendar (the DvM+ event stream), not by share.
- **Acquisition-channel leaves** (draft and IFA WAG splits, IFA and draft WAR per year, draft pick
  value against slot, draft round and IFA bonus tiers, sleeper hit rates, acquisition-deviation star
  rates, draft-pool efficiency, IFA ROI): the signing club only, by its share. These grade the
  signing decision, so a club that traded for the player is not in them.
- **WAR per $M (the bonus channels)**: numerator the WAR credited to the signing club, denominator
  the bonus it paid (in full; the club that paid it is the only club with a cost). A developing club
  that did not sign the player has no bonus to divide by and takes its share in the production
  leaves instead.

## 7. Surfaces

- `debuts.json` and `debuts_lite.json` rows gain `dev_credit`: `{shares: [[org, share], ...],
  signing_org, basis, tenures: [[org, start, end], ...]}`; `org` stays the current club ("now
  with").
- Club Ledger graduates block: a club lists every graduate it holds a share of, with two new
  columns, `dev_share` and `now_with`.
- PROSPX farm detail, "Recent graduates": developed by the club (share above zero), with Share and
  Now with columns; the Development tab's per-tool DvM+ subtitle names the new attribution.
- Front Office graduation panel: graduates per year and mean graduate WAR by share.
- Franchise: no code change; its FARM branch and Front Office block move with the regenerated farm
  grade and tendencies.

## 8. Blast radius

Farm letters move. The build commit publishes, for all 30 clubs, the farm letter, farm rank and
Franchise index before and after, and the count of graduates whose credited club changes.

## 9. Interface for Staff Gems (staff_gems.md section 4.8)

`dev_attribution.build(...)` returns per player the tenure segments `(org, start, end)`, the
basis, the signing club and the club shares; per graduate `W(g, org) = share(org) x career WAR`.
Staff Gems splits `W(g, org)` inside a club's tenure by time on its own unit calendar.

## 10. Tests

A traded prospect's growth is credited to the club where it happened; shares sum to one; Tarik
Skubal credits DET, not LAD; a release opens an unaffiliated stretch that credits nobody; a pair
spanning a trade splits by days; the graduate leaves credit the developing club; the Ledger and
PROSPX surfaces carry the share and the current club.
