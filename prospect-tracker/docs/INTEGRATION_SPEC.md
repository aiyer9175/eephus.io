# Integration Spec - top 5 eFV data sources (2026-07-24)

Implementation spec for the five shortlisted sources in `docs/SOURCE_AUDIT.md`.
Each was verified live; runnable probes are in `scripts/probes/`. Join spine is
`mlbam_id`. This spec is design-only; nothing here is wired into the pipeline yet.

---

## 1. tj_surgery_list (Tier I, ~1 day)

- **Endpoint**: `https://docs.google.com/spreadsheets/d/1gQujXQQGOVNaiuwSN680Hq-FDVsCwvN-3AazykOBON0/export?format=csv`
- **Schema**: header on ROW 2 (row 1 is a donations banner). Columns include
  `Player, TJ Surgery Date, Level, Position, Throws, College(s), Age, Recovery Time (months),
  mlbamid, fgid, Post-TJ MLB G, Post-TJ MLB IP/PA, Active, Year, Month, Day`.
- **Grain**: one row per surgery (a player can appear more than once).
- **Join**: `mlbamid` -> spine, 99% native fill; 2511 distinct players, 2696 surgeries.
- **Cadence**: monthly refresh is ample; the archive is append-mostly.
- **eFV feature (as-of, leakage-safe)**: `tj_pre` = any surgery `Year` strictly before
  the row's decision cutoff year; `tj_count_pre`; optionally `months_since_last_tj`. Pitcher
  matrix primarily. Attach in `efv_dataset._injury_features` alongside `il_stints_pre`.
- **Failure modes**: (a) the sheet id or share settings could change -> pin the id, fail
  soft to the prior cache; (b) `mlbamid` blanks for ~1% (amateurs pre-draft) -> those stay
  `tj_pre=0` not null; (c) surgery-date day is sometimes blank -> key on `Year`.
- **Open question before ship**: the conditional signal is survivorship-positive on the
  resolved cohort. Run the censored full-pool eval with symmetric bust-id coverage first.

## 2. draft_statsapi (Tier D+H, ~1 day)

- **Endpoint**: `https://statsapi.mlb.com/api/v1/draft/{year}` (+ `/draft/prospects/{year}`).
- **Schema**: `drafts.rounds[].picks[]` with `pickNumber, round, pickValue` (official slot $),
  `signingBonus` (actual $), `team`, `school{name,class,state,country}`, `person{id,fullName}`.
- **Grain**: one row per pick.
- **Join**: `person.id` -> spine, ~100%. `pickValue`/`signingBonus` populated 2017+; picks
  back to 1965.
- **Cadence**: annual (July), plus a September pass for late signings.
- **eFV / PROSPX use**: fill `bonus_usd` and `pick_overall` on rows currently missing them
  (28% / 40% coverage), and give PROSPX the authoritative slot ladder. NOTE: on the 2011-2016
  rows the fill is gated by the same mlbam-id wall (`mlbam_id_overrides.json` unlocks it).
- **Failure modes**: MLBAM copyright (`gdx.mlb.com/components/copyright.txt`) is the same
  accepted risk we already run under; schema is stable but undocumented.

## 3. statsapi_venues_meta (Tier F, ~1 day)

- **Endpoint**: `https://statsapi.mlb.com/api/v1/venues?hydrate=location,fieldInfo,timezone&sportId={11..16}`.
- **Schema**: `venues[]` with `location.defaultCoordinates{latitude,longitude}`,
  `location.elevation`, `fieldInfo{capacity,turfType,roofType, leftLine..rightLine}`,
  `timeZone`, park `azimuthAngle`.
- **Grain**: one static row per venue.
- **Join**: `venueId` -> already linked to our teams/games. ~100%.
- **Cadence**: yearly (parks rarely move); refresh at season start.
- **Use**: feed the physical drivers behind `milb_park_factors.json` (elevation, dims). Does
  NOT include weather; a lat/lon-keyed weather API is a separate, later add.
- **Failure modes**: a MiLB affiliate relocating mid-season leaves a stale venue map until
  the yearly refresh (low impact).

## 4. mlb_pipeline_graphql (Tier C, ~2 days incl. grade-subfield capture)

- **Endpoint**: `POST https://data-graph.mlb.com/graphql`, no auth.
  Query `getPlayerRankingsFromSelection(limit:100, slug:"sel-pr-{YEAR}-top100")`.
- **Schema (verified)**: `rank`, `playerEntity{position, eta, player{id, fullName}}`. Tool-grade
  values (`PlayerEntityGrades`) are a lazy subfield with hidden names (introspection disabled).
- **Grain**: one row per player x list x season.
- **Join**: `player.id` -> spine, ~99%.
- **Vintage**: NATIVE, slug `sel-pr-YYYY-top100` for 2011-2026 (verified: 2021 #1 Franco,
  2026 #1 Jesus Made). This is the point-in-time capability - build grade features as-of a
  past date and calibrate each grader's bias/precision vs realized WAR (runbook 3b).
- **Cadence**: boards update through the season; capture on the existing daily Pipeline path.
- **Remaining work**: one browser/XHR capture (~0.5d) to enumerate the grade subfield names,
  then wire team Top-30 / draft / intl slugs.
- **Failure modes**: undocumented endpoint could change or lock without notice -> treat as
  breakable, keep the manual-board fallback; MLBAM ToS applies (attribution where a grade
  drives a displayed number).

## 5. statsapi_sport22_college (Tier E, ~2.5 days)

- **Endpoint**: `https://statsapi.mlb.com/api/v1/stats?stats=season&group={hitting|pitching}&sportId=22&season={Y}&playerPool=all`
  (+ `/teams?sportId=22&season={Y}` for the league/team map; per-game PBP via game feeds).
- **Schema**: standard StatsAPI `stats[0].splits[]` player-season lines, same shape as the
  MiLB ladder we already parse in `milb_history.py`.
- **Grain**: player-season (PBP available for finer grain).
- **Join**: `player.id` is the mlbam spine id for MLB-tracked players (~100% of the
  prospect-relevant subset). Non-prospect roster players may lack an id (coverage ceiling,
  not a join failure).
- **Coverage**: leagueId 107 NCAA D1 + 565 Cape Cod + 120 Appalachian + 5536 Draft League;
  populated 2018-2026 (2013 empty). Northwoods is NOT covered (not MLB-partnered).
- **Cadence**: monthly in-season; a final post-College-World-Series pass.
- **Use**: give CollegeSavant a join-clean spine (replacing name-matched `college_stats.py`)
  and eFV a real pre-professional prior for recent draftees.
- **Failure modes**: `playerPool=all` roughly triples row counts vs the qualifier-filtered
  default - always pass it; pre-2018 seasons return empty (no backfill available here).

---

## Sequencing

Land the three cheap StatsAPI/CSV items first (tj, draft, venues; ~3 days, all native
joins, low legal risk). Then Pipeline vintages (~2 days) because they unlock the
grader-calibration program, which is the highest-leverage eFV work that a source can
enable. sportId 22 (~2.5 days) is a CollegeSavant/PROSPX breadth win more than an eFV-core
win. Total ~7 engineering-days. The label-horizon trap (see the audit) is not closed by any
of these; the surrogate-label program is the separate, larger next investment.
