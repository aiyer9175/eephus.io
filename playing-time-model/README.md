# Playing Time Model

Role-based PA projection: talent claim × roster opportunity × replacement
pressure × defensive utility × position lifecycle/mobility × org incentives.
Injuries excluded (separate medical model later). Full spec: FRAMEWORK.md.

## Status (2026-06-11)

| Module | Status |
|---|---|
| 00 data inventory + join validation | DONE — all sources pass with caveats |
| 01 usage spine pull (statsapi 2000-2026) | DONE — hitting + fielding-by-position |
| 02 spine build + cross-validation | DONE — 99.2% exact PA match vs deep_mlb |
| 03 validation ladder rungs A0/A/B | DONE — benchmark set |
| 04 rung C replacement pressure (same-team year-t) | DONE — **NO ADD** (redundant with own usage share) |
| 05 rung D defensive flexibility ablation | DONE — no PA lift; keep in A (free); retest vs role targets |
| 06 rung E prospect pedigree | DONE — **UNDERPOWERED** in incumbent universe (1 train yr coverage); defer to call-up module |
| 07 rung F' minors usage / shuttle | DONE — **ADD, new champion** |
| 08-09 draft pedigree (statsapi draft 1990-2025) | DONE — **ADD, champion = E2** (fixes pedigree coverage: every train year) |
| 10-11 public benchmark vs preseason Steamer/ZiPS archives | DONE — Steamer MAE 90.3 beats champ 115.1 (info-date gap); ZiPS PA not a real PT system (R² −.30) |
| 12 Steamer stack (preseason frame) | DONE — **stack beats Steamer on R²/RMSE** (.695/128.2 vs .674/132.5); 50/50 blend best overall (R² .703, rho .852); Steamer still best MAE 90.3 |
| 13a league-wide transactions pull 2002-2026 | DONE — 754k events (OPT/CU/DFA/TR/SGN...) |
| 13b transaction features | DONE — **ADD both frames**: champ R² .599→.604; blend → R² .704/rho .854/MAE 91.3. Winter-DFA segment diagnosed: Steamer MAE 40 vs ours 59 → OD rosters targeted |
| 14 Opening Day rosters (40-man Mar 25 + active Apr 2, 2004-2026) | DONE — **ADD, big**: standalone beats Steamer on R²/RMSE/rho (.715/123.8/.859); blend beats Steamer on ALL FOUR (R² .718, RMSE 123.3, MAE 88.7, rho .861); winter-DFA hole MAE 59→56 |
| 15 call-up universe + debut hazard (Model D v1) | DONE — 21,508 AA/AAA pre-debut seasons; AUC ladder PERF .832 → +draft .846 → **+40-man-selected .865** (service-time tell) → +FV .874 pooled but FV HURTS on covered rows (1 train yr) — needs historical top-100 backfill. Calibration: overconfident at top; era shift (debut rate 7.2%→12.2%) → isotonic recal in v2 |
| 16 curated benchmark: ATC + Depth Charts via Wayback (target 2025 only) | DONE — ours beats ATC outright (rho .825 vs .771); ours+Steamer blend tops all five systems on every metric |
| 17 Steamer dependency ablation | DONE — **ARCHITECTURE DECISION: champion = Steamer-FREE model** (beats Steamer R²/RMSE with zero FG inputs); best system = blend(no-Steamer ours, Steamer) R² .724/rho .863 — diversity beats stacking; Steamer demoted to optional blend partner |
| 18 engine-talent backfill (walk-forward backbone, 2004-2026) | DONE — backfill built + leakage-clean (shipped backbone_scores was in-sample for 2023 targets — refit per-year); ablation = WASH (R² .688→.686, MAE 99.6→99.1) → **trailing rates stay** (teams allocate PA on coarse signals); engine_talent.parquet kept for hazard v2 (minors translation built in — the universe where it should actually win) |
| 19 registered forward test vs FG Depth Charts, season 2026 | FROZEN 2026-06-12 — ours (Steamer-free, trained ≤2025) vs DC (Feb 26 Wayback) vs ATC (Jan 31); steamer_2026/zips_2026 archives not yet served. **Provisional rho vs PA-to-date (n=538): ours .825 > DC .760 > ATC .737.** Final scoring after season: rerun 01 pull, join realized PA to forward_test_2026.parquet |
| 20 injury model integration (from ~/injury_model handoff) | DONE — **ADD, new champion**: clean IL-history block (stint count/days through t, career cumsum, on-IL-at-OD flag) lifts R² .687→.716, MAE 99.7→93.6. Blend w/ Steamer now beats Steamer on **all four** incl MAE (.734 / 119.7 / 87.0 / .870). Rate-table cols (p_any_il_next etc.) DROPPED as leaky (full-window fit + recode of career_il_stints; inflated R² to .761). Gains land age≥32 (MAE 79.7→68.9), got-hurt-last-yr (125→111) |
| 21 injury severity / duration | DONE — **ADD (targeted)**: D-level ordinal (D10/15/60 from our pull) + walk-forward region-median days (impact_windows_v2, region known at OD, lookup uses only prior seasons; handoff availability CSV NOT used — full-window leak). Pooled ~wash (.7155→.7164) BUT closes the last Steamer-edge segment: on-IL-at-OD MAE 108.8→100.8 (≈Steamer 99.6), rho .635→.686. Clean, no harm elsewhere → ships |
| Decomposed targets (roster prob, call-up timing, platoon share) | TODO |
| Historical Pipeline top-100 backfill (pre-2021) for FV training depth | TODO (chip pending) |

## Curated-system shootout (target 2025 only, common universe n=542)

| System | R² | RMSE | MAE | Spearman |
|---|---|---|---|---|
| **blend ours+Steamer** | **.682** | **129.5** | **101.6** | **.832** |
| Ours (F-pre+OD) | .659 | 134.1 | 106.9 | .825 |
| Steamer preseason | .664 | 133.1 | 102.0 | .820 |
| ATC (Mar 7 2025 Wayback) | .567 | 151.2 | 114.8 | .771 |
| DC (Dec 2 2024 Wayback*) | .344 | 186.0 | 139.9 | .722 |
| ZiPS preseason | −.145 | 245.8 | 197.5 | .568 |

*DC vintage predates the offseason (Soto still teamless) — handicapped.
FG findings (authenticated member session): DC/ATC/THE BAT archives DO NOT
EXIST server-side (member API 500s; /projections-archive is 404) — FG only
archives Steamer (2010+) and ZiPS (2023+). Wayback live-API captures are the
only preseason DC/ATC vintages; usable ones exist for 2025/2026 only.
DC Dec-2024 payload predates xMLBAMID → join via FG-playerids bridge
(data/raw/fg_id_bridge from ATC capture + archive pulls).

## Data sources (validated in reports/00_join_validation.md)

- **Prospect tracker** `~/Desktop/eephus.io/prospect-tracker/prospects.db` —
  timestamped FV/rank/tool snapshots (Pipeline 2021-2026 incl. org Top 30s,
  ESPN, TJ, JB), roster_status (40-man/options/service — CURRENT snapshot
  only, leakage-flagged), transactions, career_war. Slug↔MLBAM bridge built
  from statlines (93% coverage; 6 colliding mlbam_ids dropped).
- **Deep history** `~/projection_engine/data/deep_mlb|deep_minors.parquet` —
  rates + age, 2000-2026 MLB / 2008-2026 minors.
- **Talent layer** `~/swing_plus/data/processed/stat_projections.parquet` —
  engine v2 projections (2023+), batter×season.
- **Usage spine** (this repo) `data/processed/usage_spine.parquet` —
  17,074 hitter-seasons 2000-2026: PA, G, starts (incl. DH), games/starts by
  position, primary pos, n_positions, premium flag, DH share.

## Benchmark to beat (holdout = target years 2023-2025, n=1,990)

| Rung | R² | RMSE | MAE | Spearman | Verdict |
|---|---|---|---|---|---|
| A0 persistence (pa_t) | .457 | 171.1 | 125.8 | .696 | floor |
| A usage-history GBM | .574 | 151.6 | 120.5 | .749 | |
| B + talent GBM | .590 | 148.7 | 116.9 | .769 | |
| C + replacement (same-team yr-t) | .589 | 148.8 | 116.5 | .768 | NO ADD |
| E + pedigree (tracker) | .590 | 148.7 | 116.9 | .769 | underpowered |
| **F' + minors usage (CHAMPION)** | **.596** | **147.6** | **115.8** | **.775** | ADD |

F' gains concentrate where intended: pa_t<200 R² .268→.292, age≤25 .410→.423,
shuttle players rho .624→.643; regulars unchanged. E2 (+draft pedigree) adds
on top: pooled R² .599, top-10 picks MAE 131→126, recent draftees R² .30→.35.
Remaining hole: incumbent top-100 prospects (n≈11/yr) MAE ~226, rho .13 —
the Holliday/Chourio class. That segment, plus everyone with zero MLB
history, belongs to the call-up module where tracker pedigree is dense.

## Public benchmark (targets 2023-25, common universe n=1,985)

| System | R² | RMSE | MAE | Spearman |
|---|---|---|---|---|
| Steamer preseason (archived) | .674 | 132.5 | 90.3 | .848 |
| ZiPS preseason (archived) | −.297 | 264.4 | 218.4 | .588 |
| Champion E2 (October info) | .599 | 147.0 | 115.1 | .776 |
| Steamer-free preseason: + tx (13b) | .696 | 127.9 | 97.6 | .847 |
| + Opening Day rosters (14b) | .715 | 123.8 | 93.4 | .859 |
| + injury history (20, CHAMPION) | .716 | 123.8 | 93.6 | .862 |
| **blend (ours + Steamer)/2** | **.734** | **119.7** | **87.0** | **.870** |

**The blend beats Steamer on all four metrics, including MAE** (as of
Module 20). With injury history integrated, our STANDALONE Steamer-free model
beats Steamer on R²/RMSE/rho and is within ~3 PA on MAE — the residual MAE
edge is spring-injury *severity/duration* (we know who's on IL Opening Day,
Steamer also knows how long). Injury integration closed ~6 of the ~9 PA gap.

Read: Steamer's edge is the information date (it's frozen near Opening Day —
knows offseason moves, depth charts, spring injuries; we predict from
October, injuries excluded by design). Moving to the preseason frame and
stacking, our layer ADDS value over Steamer on R²/RMSE/rho — it fixes big
misses; Steamer stays sharper on the median player (MAE). ZiPS PA is a rate
system with idealized PA — scoring it badly validates the harness.
FG API notes: `season` param is IGNORED (returns current run — trap);
archives live under type suffixes `steamer_YYYY` (2010+ public), `zips_YYYY`
(2023+); Team field in archives is refreshed (don't use); vintage
authenticated via retired players (Votto/Cabrera present in steamer_2023).

## Conventions

- Python: `~/swing_plus/.venv/bin/python`
- Era scaling: counting features × (median 2000-2019 league PA / season league
  PA); target years 2020 and 2026 excluded.
- Universe so far: MLB incumbents (≥1 MLB PA in feature year). Call-up /
  debut universe enters with the hazard modules.
- Every feature must beat rung B out of sample or it doesn't ship
  (FRAMEWORK.md governing rule).

## Pipeline

```
pipeline/00_inventory.py    # source audit + key bridge + grades_long + roster_status
pipeline/01_pull_usage.py   # statsapi season pulls (hitting, fielding) 2000-2026
pipeline/02_build_spine.py  # player-season usage table + PA cross-check
pipeline/03_baselines.py    # ladder rungs A0/A/B
```
