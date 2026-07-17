# Data Dependencies

Inventory of everything the tool needs that is **NOT** in this repo. Per repo rules, raw
datasets, generated artifacts, and model binaries live in **external storage** (Drive / S3 / GCS).
Fetch them into the paths below (or regenerate via the listed commands) before running.

> Owner of the external data buckets: **@willclq**. Update the `Location` column with the real
> bucket/Drive URLs once provisioned.

## Raw datasets (external — never committed)

| Path | What | Size | Source | Location |
|---|---|---|---|---|
| `data/raw/statcast_2023_H2.parquet` … `2026_H1.parquet` | pitch-level Statcast (bat-tracking era) | ~285M | pybaseball `statcast()` | _TODO: S3/GCS/Drive URL_ |
| `data/raw/decision_plus/…` | external swing-decision model outputs (legacy 148-cohort) | small | external project | _TODO_ |

Pull command (chunk by week — `statcast()` is rate-limited):
```python
from pybaseball import statcast
df = statcast("2026-03-26", "2026-06-07")   # then write to data/raw/statcast_2026_H1.parquet
```

## Generated artifacts (external or rebuilt — never committed)

| Path | Produced by | Notes |
|---|---|---|
| `data/processed/leaderboard_{alltime,season,half}.parquet` | `run_leaderboard.py` | the served boards |
| `data/processed/trajectories.parquet` | rolling Swing+ pipeline | Drivers tab (Swing+) |
| `data/processed/swing_grades.parquet` | `swing_grade.py` | per-pitch swing grades (27M) |
| `data/processed/mlb_decision.parquet` | `mlb_decision.py` | Decision+ + drivers |
| `data/processed/decision_traj.parquet` | `decision_drivers.py` | rolling Decision+ |
| `data/processed/pitcher_arsenal.parquet` | `matchup.py` build | matchup tool |
| `data/processed/bat_to_ball_plus.parquet` | external Bat-to-Ball+ framework (+ `b2b_2026.py` for 2026) | B2B+ |
| `web/static/*_report_card.png` | `report_card_swing.py`, `report_card_decision.py` | model cards UI |

## Model artifacts (external — `*.joblib`, never committed)

| File | What | Source |
|---|---|---|
| `swing_plus_model_v1.joblib` | deployable Swing+ scorer (~4KB) | `pipeline/20_build_deployable.py` |
| `swing_grade_models.joblib` | per-pitch whiff+contact models (~2M) | `swing_grade.py` |
| `pa_value_models.joblib` | blended-xwOBA model | `train_pa_value.py` |
| `models/opportunity_*_v2.lgb.joblib`, `difficulty_*`, `swing_prob` | Bat-to-Ball+ LightGBM models | external framework bundle |

## APIs / external services

| Service | Used for | Where |
|---|---|---|
| **pybaseball** (Baseball Savant / Statcast) | raw pitch data ingest | `pipeline/01_ingest.py`, ad-hoc pulls |
| **MLB StatsAPI** (`statsapi.mlb.com`) | player birthdates (aging curve) | `aging.py` → cached `data/processed/birthdates.json` |
| **External Bat-to-Ball+ framework** | B2B+ artifact + LightGBM opp models | bundle (`bat_to_ball_plus_FULL.zip`) |

## Small sample data (committed, in-repo)

| Path | What |
|---|---|
| `data/samples/leaderboard_alltime_sample.csv` | 40-row leaderboard sample for schema/demo |

See `schemas/` for column definitions.
