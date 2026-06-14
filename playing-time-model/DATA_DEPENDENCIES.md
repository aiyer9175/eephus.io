# Data Dependencies — Playing Time Model

Raw datasets and generated artifacts are **not** committed (see `.gitignore`).
Store them in external storage (Drive / S3 / GCS). This documents everything
the pipeline requires to reproduce those artifacts.

## APIs / endpoints
| Source | Used for |
|---|---|
| `statsapi.mlb.com/api/v1/stats` (season, byDateRange, statSplits) | usage (PA/G/starts by pos), as-of-date cumulative, platoon vs L/R |
| `statsapi.mlb.com/api/v1/teams`, `/teams/{id}/roster?date=` | minor-league parent-org map; Opening-Day 40-man / active rosters |
| `statsapi.mlb.com/api/v1/teams/{id}/coaches` | manager history |
| `statsapi.mlb.com/api/v1/draft/{year}` | draft pedigree (pick, bonus) |
| `statsapi.mlb.com/api/v1/transactions` | OPT/CU/SE/OUT/DFA + dated IL placements/activations/transfers |
| `statsapi.mlb.com/api/v1/people` | debut dates, handedness |
| `baseballsavant.mlb.com/leaderboard/outs_above_average`, `/sprint_speed` | defense (OAA/FRV), sprint speed (tested, NOT shipped) |
| `fangraphs.com/api/projections` (`steamer_YYYY`, `zips_YYYY`) | **BENCHMARK ONLY** — external yardstick, NOT a model input |
| `web.archive.org` (Wayback) | historical preseason projections, depth charts, contracts for backtest validation |

> NOTE on FanGraphs: used strictly to score against (Steamer/ZiPS). The
> deployed model consumes **no** third-party projections. `season` param on the
> FG/statsapi endpoints is ignored — historical vintages require type suffixes
> or Wayback.

## External datasets (sibling projects / local; not in this repo)
| Source | Used for |
|---|---|
| `~/projection_engine/data/deep_mlb.parquet`, `deep_minors.parquet` | rates + age history (MLB 2000–, minors 2008–); backbone talent |
| `~/swing_plus/data/processed/stat_projections.parquet` | engine talent-rate projections |
| `~/injury_model/data/processed/playing_time_handoff/` + `risk_panel_yoy.parquet`, `impact_windows_v2.parquet` | injury history, severity, IL risk |
| `Desktop/eephus.io/prospect-tracker/prospects.db` | FV / scouting grades / rank snapshots (timestamped) |

## Generated artifacts (produced by pipeline → external storage, gitignored)
| File | Producer |
|---|---|
| `data/raw/usage_hitting.parquet`, `usage_fielding.parquet` | `pipeline/01_pull_usage.py` |
| `data/processed/usage_spine.parquet` | `pipeline/02_build_spine.py` |
| `data/raw/{draft_history,transactions,od_rosters,public_projections}.parquet` | `pipeline/08,13,14,10` |
| `data/processed/{tx_features,od_features,injury_features,injury_severity}.parquet` | modules 13b,14b,20,21 |
| `expansion/data/raw/{minors_affiliation,managers,platoon_splits,asof_hitting,savant_oaa,sprint_speed,contracts_raw,depth_charts_raw}.parquet` | `expansion/pipeline/E01–E07` |
| `expansion/data/processed/{full_population_proj,platoon_index,role_targets,depth_rank,...}.parquet` | `expansion/pipeline/E11–E30` |

Small illustrative samples of the key tables are in `samples/` (schema only).

## Services
None beyond the public HTTP APIs above. Python env: see `requirements.txt`
(pandas, numpy, scikit-learn, scipy, requests, pyarrow; brotli for Wayback).
