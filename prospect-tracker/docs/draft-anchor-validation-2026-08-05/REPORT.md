# Draft-anchor backfill: dry-run validation

**Date:** 2026-08-05
**Module under review:** `draft_anchor_backfill.py`
**Status of the DB:** untouched. Every number came from a `sqlite mode=ro` handle.
**Harness:** `tools/draft_anchor_dryrun.py`

---

## Recommendation: RETIRE, or at minimum do not apply as written

Eight reasons, all measured today:

1. **It fixes 2.6% of the problem.** The gap is 2,608 active players on a fabricated FV 35. The backfill reaches 68. 2,540 stay exactly where they are.
2. **The "real published grade" is a board floor, not an opinion.** 53 of 68 would receive FV 40. FV 40 is the *minimum value MLB Pipeline's draft Top 250 assigns* (whole-board distribution 40:646, 45:743, 50:518, 55:140, 60:49, 65:11, with zero 35s). For 78% of the cohort this swaps one constant for another constant.
3. **The information is already in the model, in better form.** All 68 carry `pick_overall` AND `bonus_usd` in `acquisitions`; `efv_dataset` already attaches both and `efv_score`'s P1 draft-slot prior already consumes them as a continuous pedigree signal. Within this cohort the seeded grade has zero rank correlation with where the player was actually taken: Spearman +0.006, permutation p = 0.96 (n=68).
4. **The one relation I could measure runs the wrong way.** Spearman(seeded FV, served eFV) = **-0.26**, permutation p = 0.057, null 2.5/97.5 band -0.260 to +0.285. Not significant, so I claim no inversion. But there is no positive evidence that the players the draft board liked are the ones five years of pro performance now likes.
5. **The safety property the module advertises does not hold.** The docstring says the seed is dated at the board's own date "so anchor staleness stays honest." `efv_dataset._stale_anchor_discount` reads `row["asof_date"]`, which is the *consensus point's* date, not the source row's date, and that point is refreshed daily by the very `performance_ingest` stamp being replaced. Measured discount for all 68: **0.00 FV points.** A 2021 board opinion would serve as a fresh 2026 anchor. If the board date *were* honored, 38 of 68 take the full 10.00-point decay and 14 take 5.94, pushing them to 28.33, i.e. **below** today's 35.
6. **Every move is upward; there is no downward channel.** Deltas take exactly three values: +7 (10 players), +4 (53), 0 (5). Never negative. A coverage repair that can only raise grades is board inflation, not a correction.
7. **The price is a full regen plus a golden-fingerprint restamp**, for 0.46% of board surplus ($56.9mm of $12,247.9mm), plus an unmeasured rank re-sort across the whole board.
8. **The rows decay on their own.** One seed (Andrew Pérez, 2018) is already discarded silently by `consensus._prune_collision_cluster`: the 8.07-year gap to today's stamp exceeds `_GAP_BIG_DAYS` = 2920. The 2019 class crosses that line in July 2027.

### If you apply anyway, apply with these modifications

- **Write 62 rows, not 68.** Drop the 5 FV-35 seeds (pure no-ops) and the 1 pruned 2018 seed.
- **Settle the staleness question first.** Either make the discount read the contributing source's own date, or stop claiming the board date protects staleness. As shipped, honoring the board date moves these anchors DOWN, not up.
- **Re-run `find_candidates()` immediately before `--apply` and diff against the approved list.** The set drifts daily (71 on 2026-07-25, 70 earlier today, 68 now).
- **Pre-register the collateral.** Capture rank, `xfv_grade` and `surplus_mm` board-wide before and after, and publish the re-sort, not just the 68.

---

## 1. What exactly would change (all 68 rows)

**Current anchor is one row for every candidate**: `source=performance_ingest`, `fv=35.0`, `interval_label=2026_performance`. Dated 2026-08-05 for 66 of them, 2026-08-03 for Kyle DeGroat, 2026-01-01 for Ryan Brown. No candidate has any other FV-bearing snapshot. Org is non-null on all 68.

**The backfill would add** one row each: `source=draft_signing`, `fv` = mean of the latest board FV per source, `snapshot_date` = the board's date, `interval_label` = `"<year> Draft Class"`. The upsert key `(source, interval_label, player_key)` does not collide with the current-class seeder's `"2026 Draft Class"` rows, so this is 68 pure inserts.

`consensus FV` is measured, not estimated: the harness ran `consensus.build_timeseries(..., normalize=True)` baseline and treated. The baseline reproduced the served `consensus_fv` in `data/xfv.json` for **68 of 68**, so the treated column is production-faithful.

| # | Player | Class | Pick | Org | Current anchor | Anchor the backfill writes | Board source | consensus FV | Delta | Served eFV | Surplus |
|---:|---|---:|---:|---|---|---|---|---|---:|---:|---:|
| 1 | Chandler Pollard | 2022 | 139 | TEX | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2022-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.7mm |
| 2 | Luis Ramirez | 2022 | 199 | MIA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2022-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.7mm |
| 3 | Sean McLain | 2022 | 165 | LAD | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2022-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.7mm |
| 4 | Jack Payton | 2023 | 330 | SFG | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2023-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.7mm |
| 5 | Jared Dickey | 2023 | 319 | ATH | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2023-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $1.0mm |
| 6 | Julian Brock | 2023 | 231 | TEX | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2023-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $1.1mm |
| 7 | Michael Carico | 2023 | 149 | CHC | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2023-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.7mm |
| 8 | Cody Schrier | 2024 | 394 | MIA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2024-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.8mm |
| 9 | Woody Hadeen | 2024 | 176 | DET | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2024-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $0.7mm |
| 10 | Zander Darby | 2024 | 358 | SFG | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 45, 2024-07-01 | Pipeline Top 250 | 35 to 42 | +7 | 20.0 | $1.0mm |
| 11 | Cooper Johnson | 2019 | 172 | TEX | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2019-07-10 | fangraphs + Pipeline | 35 to 39 | +4 | 20.0 | $0.7mm |
| 12 | Drew Swift | 2021 | 248 | ATH | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 13 | Dru Baker | 2021 | 130 | CHW | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 14 | Jake Rucker | 2021 | 219 | MIN | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 15 | Jose Pena Jr. | 2021 | 175 | PHI | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 16 | Patrick Winkel | 2021 | 279 | TOR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 17 | Ryan Webb | 2021 | 125 | CLE | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 18 | Seth Lonsway | 2021 | 176 | SFG | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 19 | Tyler Miller | 2021 | 256 | PHI | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2021-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 20 | Bryce Osmond | 2022 | 448 | LAA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2022-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 21 | Chris Newell | 2022 | 405 | LAD | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2022-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.9mm |
| 22 | D'Andre Smith | 2022 | 149 | NYM | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2022-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 23 | Jorel Ortega | 2022 | 174 | MIN | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2022-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 24 | Luis Rujano | 2022 | 383 | CHC | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2022-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 25 | Nate Baez | 2022 | 354 | BOS | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2022-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 26 | Coleman Picard | 2023 | 169 | KCR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 25.6 | $0.7mm |
| 27 | Drew Conover | 2023 | 316 | CHW | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 28 | Jake Peppers | 2023 | 269 | CHW | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 29 | Jason Savacool | 2023 | 185 | STL | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 30 | Jay Driver | 2023 | 278 | CLE | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 31 | Joe Vetrano | 2023 | 163 | LAD | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 32 | Luke Shliger | 2023 | 180 | DET | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 33 | Nick Goodwin | 2023 | 214 | TOR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $2.5mm |
| 34 | Paulshawn Pasqualotto | 2023 | 357 | MIN | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 35 | Ryan Brown | 2023 | 466 | LAN | performance_ingest FV 35.0, 2026-01-01 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 39.2 | $0.7mm |
| 36 | Tommy Hawke | 2023 | 188 | CLE | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2023-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 37 | Ali Camarillo | 2024 | 346 | ATH | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 38 | Corey Collins | 2024 | 173 | NYM | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $1.0mm |
| 39 | Dub Gleed | 2024 | 274 | TOR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 37.7 | $2.7mm |
| 40 | Ivan Brethowr | 2024 | 212 | PIT | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $2.4mm |
| 41 | Jacob Jenkins-Cowart | 2024 | 244 | MIA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 42 | Jeremiah Jenkins | 2024 | 418 | SFG | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 43 | Josiah Romeo | 2024 | 166 | ATH | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 44 | Kyle DeGroat | 2024 | 407 | KCR | performance_ingest FV 35.0, 2026-08-03 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 45 | Kyle Robinson | 2024 | 316 | PIT | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 46 | Ryan Andrade | 2024 | 216 | TBR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 47 | Travis Smith | 2024 | 455 | MIL | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2024-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 48 | Anthony Martinez | 2025 | 252 | CLE | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.8mm |
| 49 | Brent Iredale | 2025 | 203 | PIT | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.9mm |
| 50 | Brody Donay | 2025 | 507 | TBR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 51 | Cam Maldonado | 2025 | 206 | SFG | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 52 | Damian Bravo | 2025 | 446 | SFG | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 53 | Isaiah Jackson | 2025 | 229 | BOS | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $1.9mm |
| 54 | Jack Anker | 2025 | 173 | PIT | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 55 | Jake Clemente | 2025 | 198 | MIA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 56 | Jake McCutcheon | 2025 | 288 | MIA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 57 | Kyle McCoy | 2025 | 234 | CIN | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 58 | Matt Klein | 2025 | 167 | COL | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 59 | Nelson Keljo | 2025 | 192 | CLE | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 37.9 | $0.8mm |
| 60 | Payton Graham | 2025 | 210 | STL | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 61 | Ryan DeSanto | 2025 | 372 | CLE | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 62 | Ryan Weingartner | 2025 | 240 | STL | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $0.7mm |
| 63 | Rylan Galvan | 2025 | 376 | CHW | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 40, 2025-07-01 | Pipeline Top 250 | 35 to 39 | +4 | 20.0 | $1.0mm |
| 64 | Andrew Pérez | 2018 | 228 | KCR | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 35, 2018-07-10 (PRUNED, never reaches consensus) | FG draft board | 35 to 35 | +0 | 34.5 | $0.7mm |
| 65 | Jack Ralston | 2019 | 215 | MIA | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 35, 2019-07-10 | FG draft board | 35 to 35 | +0 | 36.3 | $1.0mm |
| 66 | Jose Dicochea | 2019 | 254 | ATH | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 35, 2019-07-10 | FG draft board | 35 to 35 | +0 | 20.0 | $0.7mm |
| 67 | Luke Ritter | 2019 | 208 | PHI | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 35, 2019-07-10 | FG draft board | 35 to 35 | +0 | 20.0 | $0.7mm |
| 68 | Shane Sasaki | 2019 | 99 | CIN | performance_ingest FV 35.0, 2026-08-05 | draft_signing FV 35, 2019-07-10 | FG draft board | 35 to 35 | +0 | 20.0 | $0.7mm |

Note on row 35: Ryan Brown's org reads "LAN", not "LAD". Not in this lane, flagged in followups.

---

## 2. How far anchors move

| Delta | Players | Cause |
|---:|---:|---|
| +7 | 10 | board FV 45, shrunk to 41.67, ceiling-rounded to 42 |
| +4 | 53 | board FV 40, shrunk to 38.33, ceiling-rounded to 39 |
| 0 | 5 | board FV 35, identical to the constant it replaces |

Mean +4.15 across all 68, +4.48 across the 63 movers. No negative deltas. Min 0, max +7.

**Why the shrink.** `performance_ingest` sits in `consensus.CONSTANT_ANCHOR_SOURCES`, so it votes only when no real source published an FV. Adding `draft_signing` (a real source) removes the 35 from the average entirely. Then `total_fv_instances` = 1, because constant-anchor rows are deliberately not counted as observations, so the single-source pull fires: raw = (2/3) x FV + (1/3) x 35, then `snap_to_grade` ceiling-rounds.

**By draft class** (no 2020 class; that draft was 5 rounds):

| Class | n | mean | median | max |
|---:|---:|---:|---:|---:|
| 2018 | 1 | +0.00 | +0.0 | +0.0 |
| 2019 | 5 | +0.80 | +0.0 | +4.0 |
| 2021 | 8 | +4.00 | +4.0 | +4.0 |
| 2022 | 9 | +5.00 | +4.0 | +7.0 |
| 2023 | 15 | +4.80 | +4.0 | +7.0 |
| 2024 | 14 | +4.64 | +4.0 | +7.0 |
| 2025 | 16 | +4.00 | +4.0 | +4.0 |

**By pick band.** Pick range 99 to 507; 67 of 68 went at pick 125 or later. This is the day-2 and day-3 population.

| Band | n | mean | median |
|---|---:|---:|---:|
| 1 to 100 | 1 | +0.00 | +0.0 |
| 101 to 300 | 47 | +4.04 | +4.0 |
| 301+ | 20 | +4.60 | +4.0 |

**Is the direction systematic? Yes, and that is the problem.** It is systematically upward, and slightly *larger for later picks* (+4.60 for 301+ vs +4.04 for 101 to 300). Cody Schrier at pick 394 draws FV 45 while Jack Anker at pick 173 draws FV 40. That is the signature of a board whose bottom-tier grades track list position, not pick, which is exactly what the +0.006 rank correlation with `pick_overall` confirms.

**Biggest movers** (all +7, all board FV 45): Chandler Pollard (2022, 139, TEX), Luis Ramirez (2022, 199, MIA), Sean McLain (2022, 165, LAD), Jack Payton (2023, 330, SFG), Jared Dickey (2023, 319, ATH), Julian Brock (2023, 231, TEX), Michael Carico (2023, 149, CHC), Cody Schrier (2024, 394, MIA), Woody Hadeen (2024, 176, DET), Zander Darby (2024, 358, SFG).

---

## 3. Downstream cascade

```
snapshots  (+68 draft_signing rows)
  -> consensus.build_timeseries(normalize=ADOPT_NORMALIZED_CONSENSUS=True)
       consensus_fv, consensus_fv_raw, consensus_fv_pre_shrinkage, n_sources,
       fv_stddev, fv_spread, fv_trend                      [63 of 68 change]
  -> data/timeseries.json                                  (run_monthly, all three passes)
  -> efv_dataset live rows: _prior_features(), then
       fv_effective = consensus_fv_raw - _stale_anchor_discount(asof_date, ...)
       measured discount for all 68: 0.00
  -> efv_score live scoring: fv_effective feeds the _vec `fv` feature AND the
       consensus blend leg -> xfv_war
       xfv_grade   = vf.outcome_implied_fv(xfv_war)
       _odds_grade = vf.realized_implied_fv(...) -> p_bucket (Platt)
                                                 -> vf.expected_surplus_usd -> surplus_mm
  -> efv_board_scale: board = clamp(a_side + b_side * xfv_grade_model_raw, 20, 80)
  -> data/xfv.json                                         [GOLDEN FINGERPRINT LIVES HERE]
  -> build_site._load_xfv_grades, card_market_export, bayes_trade_value
       -> data/trade_values.json, data/mlb_projections.json (tier-2, gitignored),
          fantasy / dfs / projections exports, farm + prospect pages, the board rank
```

**Artifacts needing regeneration:** `data/timeseries.json`, `data/xfv.json`, `data/trade_values.json`, `data/mlb_projections.json`, plus every export downstream of the board rank (farm grades, card market, fantasy, dfs, projections) and the site build.

**Would the golden fingerprint fire? Yes.** `test_efv_export.test_xfv_golden_fingerprint` holds an exact sha256 of `data/xfv.json` at `test_efv_export.py:465`. Measured right now, the artifact's fingerprint **matches** `_GOLDEN_XFV_SHA256` (`f9d680b8...`), so the gate is currently green. Any regen after the backfill turns it red at dev time and needs a deliberate restamp. On the deploy box (`EEPHUS_DEPLOY_RUN=1`) it degrades to shape checks; note `_GOLDEN_XFV_ROWCOUNT` is 9,268 against a live 9,368, already 1.1% off but well inside the +/-20% band.

**The eFV floor is what to watch.** `vf.outcome_implied_fv(0.0)` = 20.0 and `(0.11)` = 37.5, so the WAR-to-grade map is a cliff at WAR = 0. 3,351 of 4,580 active players (73%) sit exactly at 20.0, and **62 of the 68 candidates are on that floor**. Whether a +4 anchor move pushes their `xfv_war` above zero **cannot be determined without a re-score, which this lane did not run.** The live-board association (consensus 35: 91.8% at floor; consensus 39: 23 to 29%; consensus 40: 17%) is heavily confounded, because a player carrying a 39 today has it *because a scout re-graded him*, which correlates with everything else the model reads.

**Do not trust the docstring's yield numbers.** The "66 of 71 moved, median +5.0, 44 left the floor, 197 collateral" figures were measured 2026-07-25, before four omnibus waves. The floor cohort alone grew from 2,879 to 3,351 since. They are unverified.

---

## 4. Is 2,789 right, and why only 68?

**The two numbers measure different populations, and both are slightly off.** Measured 2026-08-05:

| Population | Count |
|---|---:|
| player_keys DB-wide whose only FV rows are synthetic | **2,786** |
| ...of those, on the ACTIVE board (`xfv.json` kind == "active") | **2,608** |
| active board players carrying a real anchor | 1,972 |
| active board players total | 4,580 |
| active board players with no FV row at all | 0 |

So 2,789 is the **DB-wide** figure (I measure 2,786, a 3-key drift) and the docstring's 2,624 was the **active-board** figure (I measure 2,608). The right denominator for judging this backfill is **2,608**.

**The funnel from 2,608 to 68:**

| Stage | Count |
|---|---:|
| Gap: synthetic-only AND active | 2,608 |
| ...no `draft_results` link at all | 1,784 (68.4%) |
| ...signed 2015-2025 draftees present in `draft_results` | 804 |
| ...of those 804, carrying ANY draft-board FV row | **68** |
| ...never board-graded (below Pipeline's Top 250, off FG's board) | 736 |

By acquisition method the 2,608 split: 1,765 `international_fa`, 825 `draft`, 18 `unknown`.

**Two structural reasons, neither fixable by this module:**

1. **68% of the gap was never in a draft.** They are international free agents. There is no draft board to join on.
2. **Of the draftees in the gap, 91.5% (736 of 804) were never graded by anyone.** They went below the Pipeline Top 250 and off the FanGraphs board. There is nothing to lift.

The 68 are the residue: prior-class signed draftees who made a board, are still active, and were never re-graded after. Seeding all of them leaves **2,540 of 2,608 (97.4%)** on the fabricated 35.

The module's own SCOPE NOTE already established that MLB Pipeline org Top 30 cannot close the rest (899 of 900 org-Top-30 players already carry a real anchor). That null still holds. Combined with this funnel, the honest conclusion is that **the FV-35 constant is not a coverage bug a join can repair. It is what "nobody published a grade on this player" correctly looks like.**

**One more thing about that count.** 71 (docstring, 2026-07-25), 70 (this morning), 68 (now). The set is defined against two artifacts that both move daily: the active set in `data/xfv.json` and the `performance_ingest` re-stamp. Whatever list you approve, `--apply` will write a different one.

---

## 5. Methodology

**Read-only guarantee.** `tools/draft_anchor_dryrun.py` opens `prospects.db` as `file:...?mode=ro` and monkeypatches `storage.connect` onto that handle, so nothing in the process can write even by accident. `find_candidates()` and `build(apply=False)` are pure reads and were called directly; `build(apply=True)` was never called. No file under `data/` was modified. `draft_anchor_backfill.py` was not edited: the dry-run affordance the owner asked for already exists.

**How the treated column was produced.** The harness rebuilds the exact `Snapshot` objects `build(apply=True)` would insert (same source, snapshot_date, interval_label, fv, org via `trades.canonical_org`), appends them to the candidates' real snapshot rows, and re-runs `consensus.build_timeseries(normalize=consensus.ADOPT_NORMALIZED_CONSENSUS)` on both sets. Restricting the pool to these 68 players is safe: `_dropped_off_pairs` is per `(player, source)` and `grade_normalization.build_remapper` reads the whole DB independently. The proof it is production-faithful is that the baseline column matches served `consensus_fv` in `data/xfv.json` for 68 of 68.

**Statistics.** Spearman rho with mid-ranks; p-values by 20,000-draw two-sided permutation. n = 68 throughout, so only large effects are resolvable; read the -0.26 as "not distinguishable from zero," not as a measured inversion.

**Environment.** `prospects.db` 1.51 GB; `data/xfv.json` regenerated 2026-08-05 10:50 (`meta.generated_at` 2026-08-04), 9,368 `by_player` rows, 4,580 active. `vf.active_valuation_set()` = `clemens_2026`.

**What was not measured.** No eFV re-score, no `efv_score.run_live`, no export, no pytest, no `--apply`. The served-grade and surplus consequences of the consensus move are named precisely above but not quantified. Anyone who wants that number must run the paired re-score fresh rather than reuse the 2026-07-25 figures.

**Reproduce:** `python tools/draft_anchor_dryrun.py > dryrun.json` (reads only).