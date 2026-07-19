# Setup — running swing-plus from a fresh clone

## 1. Install
```bash
cd swing-plus
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. Get the data
The trained **models are in git** (`*.joblib`, ~2.2 MB). The **generated data is not**
(~56 MB of leaderboards/trajectories — per repo rules it lives in external storage).
Pick one:

**A) Fetch the prebuilt bundle (fast — recommended):**
```bash
export SWING_PLUS_DATA_URL="https://.../swing_plus_data.tar.gz"   # ask the maintainer for the link
.venv/bin/python fetch_data.py
```

**B) Regenerate from scratch (slow — pulls Statcast):**
```bash
.venv/bin/python run_leaderboard.py     # raw Statcast pull + leaderboards/trajectories (hours, rate-limited)
.venv/bin/python mlb_decision.py        # Decision+ + driver components
.venv/bin/python decision_drivers.py    # rolling decision driver trajectory
.venv/bin/python swing_grade.py         # per-pitch swing grades
.venv/bin/python swing_by_pitch.py      # Swing+ by pitch type
.venv/bin/python matchup.py             # pitcher arsenal + hitter skill + scale
# merge B2B+/Hitter+ onto boards:
.venv/bin/python -c "import pandas as pd, bat_to_ball, hitter_plus, combo_plus, mlb_decision; \
[ (lambda v,p=f'data/processed/leaderboard_{v}.parquet': pd.read_parquet(p)) for v in ['half','season','alltime'] ]"
```
(The bundle path A is far easier — B is only for a full rebuild on new data.)

## 3. Run
```bash
.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000      # dev
# or keep it always-on as a service (macOS) — see LOCAL_SERVER.md
```
Open **http://localhost:8000**.

## What's in git vs not
| In git | Not in git (external) |
|---|---|
| All source (`.py`, `web/`) | Raw Statcast (`data/raw/`, ~285 MB) |
| Trained models (`*.joblib`, 2.2 MB) | Generated data (`data/processed/`, ~56 MB) |
| Model report-card PNGs | `.venv/` |
| `requirements.txt`, schemas, sample CSV | |

## Required external dependencies
See `DATA_DEPENDENCIES.md` for the full list of tables, files, APIs (MLB Stats API,
Baseball Savant via `pybaseball`), and the external Bat-to-Ball+ model the B2B+/Hitter+
axes depend on.

## Troubleshooting
- **`swing_plus_model_v1.joblib not found`** → you're on an old clone from before the
  models were committed; `git pull`.
- **`leaderboard_*.parquet not found` / empty board** → run step 2 (fetch or regenerate).
