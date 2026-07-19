# 01 — Data-Lineage Audit

**Scope note:** hitters only. The ecosystem has no pitcher system (ecosystem audit G-series);
every source below is a hitting/fielding feed. Pitcher Advancement Pace+ waits on a pitcher data program.

## Authoritative sources

| Field | Source | Coverage | Cadence | Notes |
|---|---|---|---|---|
| player_id | MLBAM id (`batter`) everywhere | universal | — | same id space across all feeds; no crosswalk needed |
| season, level, PA, age | `projection_engine/data/deep_minors.parquet` (AAA/AA) + `career_outcome_plus/data/lower_minors.parquet` (A+/A/Rk) | 2008–2026, PA ≥ 1 | refreshed with `refresh_2026.py` cycle | statsapi season hitting lines, one call per season × sportId, `playerPool=all` |
| level taxonomy | statsapi `sportId` {11,12,13,14,16} | complete | — | see 02_level_ladder.md |
| DOB / name | `eephus_identity.parquet` | 26% of history players (current players ~100%) | production | display only |
| MiLB position (era-correct) | `milb_fielding_full.parquet` (261,809 rows, 2008–2026) | 85% of players, 99% of scoreable rows | production | innings-weighted primary position |
| MLB debut | `prospect_mlb_status.parquet` (statsapi, canonical) → fallback full bWAR cache `bwar_bat*.parquet` | universal for anyone with an MLB PA | prospect status daily; bWAR per refresh | **must be the full bWAR cache** — see defect below |
| Draft pathway | `playing_time_model/data/raw/draft_history.parquet` (38,387 rows, signed flag) | 1990s–present | static pull | drafted+signed vs not |
| Injury / IL (MiLB) | not available at season-line grain | — | — | active-time uses observed-play definition instead (04) |

Exact file SHAs are stamped per build in `data/lineage.json` and the provenance manifest.

## Duplicate handling
statsapi can emit multiple splits per player-level-season (team changes). The build
aggregates to **one authoritative row per player × season × level** (PA summed, min age).
Current build: 96,100 rows, 22,659 players, 2008–2026, 0 duplicate keys (asserted).

## Missingness / known issues
- 2020: zero MiLB rows (season cancelled) — verified in-data, asserted in tests.
- `age` missing on a negligible tail of statsapi lines; entry age uses min observed age.
- DOB coverage is only 26% (identity layer covers current players); the metric therefore
  uses **season age from statsapi lines**, never DOB math.
- Entry attributes are unobservable for players already in the system when the window
  opens: **2008-entry players are left-censored and excluded from scoring** (`scoreable=False`).

## Defect found and fixed during the audit
MLB debut originally came through `milb_outcome_panel` (PA ≥ 50 filtered). Veterans whose
only MiLB rows are short rehab stints (Josh Hamilton 2009, David Wright 2015, Delmon
Young 2011/13) carried no debut, leaked into scoring as fake AAA "entries". Fix: debut
from the **full bWAR cache**; debut coverage of history players rose 10.8% → 19.4%, and
all rehab-veteran rows now fall out of the scored population. Regression-guarded by the
post-debut exclusion + case-study checks.
