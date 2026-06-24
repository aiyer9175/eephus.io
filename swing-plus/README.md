# Swing+ / Hitter+ — MLB bat-tracking analytics

A FastAPI + single-page tool that scores MLB hitters on three orthogonal bat-tracking-era
axes and blends them into one complete-hitter metric.

| Axis | Measures | Source |
|---|---|---|
| **Swing+** | bat-path power / contact-quality potential | 9 Statcast bat-tracking features |
| **Decision+** | swing/take selection (run value, base-out-count aware) | `mlb_decision.py` |
| **B2B+** | bat-to-ball / contact-quality (damage conversion) | external Bat-to-Ball+ framework |
| **Hitter+** | OPS-optimal blend of all three (the headline) | `hitter_plus.py` |

**Hitter+ beats SEAGER on ISO, BB%, and OPS** (same- and next-season) and stays fully
decomposable into its three axes (see the Drivers tab).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# fetch/regenerate artifacts (NOT in git) — see DATA_DEPENDENCIES.md
python run_leaderboard.py            # Statcast -> scored leaderboard_* parquets
uvicorn web.app:app --port 8000      # http://127.0.0.1:8000
```

## ⚠️ Repository rules

- **No raw datasets in git.** Full Statcast exports (285M), generated leaderboards/
  trajectories (57M), and model artifacts (`*.joblib`) live in **external storage**
  (Drive / S3 / GCS). The repo holds **source, schemas, configs, docs, and small sample
  data only.** Enforced by `.gitignore`; inventory in `DATA_DEPENDENCIES.md`.
- **Every new feature** must ship with a **spec, an owner, and a data-dependency list** —
  see `FEATURES.md` (template at the bottom of that file).

## Layout

```
web/app.py            FastAPI app + endpoints           web/templates, web/static  UI
swing_plus.py         deployable Swing+ scorer (loads swing_plus_model_v1.joblib)
run_leaderboard.py    end-to-end: Statcast -> leaderboards (calls the modules below)
mlb_decision.py       Decision+ (swing/take run value)  decision_drivers.py  rolling drivers
bat_to_ball.py        B2B+ board join                   b2b_2026.py  2026 calibrated scorer
combo_plus.py         SwingDecision+ (2-axis)           hitter_plus.py  Hitter+ (3-axis)
swing_grade.py        per-pitch swing grading           matchup.py   hitter-vs-arsenal
aging.py              aging projection                  report_card_*.py  audit graphics
schemas/              column schemas        data/samples/  small committed sample data
FEATURES.md           per-feature specs / owners / data deps
DATA_DEPENDENCIES.md  all tables / files / APIs / services required
pipeline/             numbered modules that built the Swing+ artifact (01-20)
```

## What's the model

Two regression pipelines (`StandardScaler` → `PolynomialFeatures(degree=2)` → `RidgeCV`) fitting:
1. **P(BIP)** — probability a competitive swing produces a ball in play
2. **E[RV | BIP]** — expected run value given a ball in play

Combined as `xRV = P(BIP) * RV|BIP + (1 - P(BIP)) * RV_nonbip` then linearly rescaled so league mean = 100, SD = 10. Reliability-weighted toward 100 with k = 360 swings.

Trained on Statcast bat-tracking data 2023-H2 through 2025-H2, ~754K competitive swings, 1,724 player-half profiles.

## Reproducing the pipeline

The pipeline directory contains numbered scripts that produced the final model in order. To rebuild from scratch:

```bash
pip install pybaseball duckdb scikit-learn joblib pandas numpy scipy

# Pull data (slow, ~5 min total, cached after first run)
cd pipeline
python 01_ingest.py     # pulls 2024 H2 by default; edit to pull all halves

# Build features and fit models
python 02_features.py
python 04_driveline_model.py
python 07_adjusted_model.py
python 09_leaderboard.py

# Package as deployable artifact
python 20_build_deployable.py
```

Each script is self-contained and can be re-run independently. Outputs go to `data/processed/` (gitignored).

## Phase history (honest)

**Phase 1 (modules 01-11):** Built and validated the contact-point model. Final metric stability r=0.88 half-to-half. Top of board (Judge, Stanton, Schwarber, Ohtani) and bottom (Kwan, Arráez, Wilson) check out. Marginal predictive lift over bat-speed-only and over last-half xwOBAcon.

**Phase 2 attempt (modules 12-19):** Tried to add path-reconstruction features following the Driveline article method.
- 3D reconstruction (12-14) had geometric bugs: attack-angle recovery errors up to 70° on some swings, ~2.5% of paths went below ground. Abandoned.
- 2D side-view reconstruction (15-16) was geometrically clean — fully determined math, 100% exact attack-angle recovery, within-player consistency improved 40% vs 3D.
- 2D top-down reconstruction (17) was clean but produced features that were deterministic functions of `attack_direction` under the circular-arc model.
- Augmented model with top-down features (18) showed +3.5pp CV R² on P(BIP) but stability dropped (0.905 → 0.881) and predictive lift on next-half xwOBAcon was flat (0.650 → 0.645). The R² gain was overfitting.

**Conclusion:** Phase 1 is the production metric. Phase 2 work is preserved in the pipeline for transparency and possible future use (visualization or richer path models if non-public data becomes available).

## Honest limitations

- **Contact-point measurements only.** No in-flight bat path. Disagreements with Driveline's "Best Swing Grade" on specific players (Matt Wallner, James Wood ranking higher there) are real and unresolvable without richer data.
- **xwOBAcon-style target.** Rewards damage-on-contact. Contact-first hitters with strong approach (Kwan, Arráez) grade low here even though they're productive in actual offensive value. This is a feature, not a bug — but worth documenting.
- **Calibration anchored to 2023-2025.** Annual retraining recommended to keep the 100-mean anchor honest if league-wide bat speed distributions drift.

## Adding 2026 data

When 2026 Statcast bat-tracking is available, no retraining is required to *score* it:

```python
from swing_plus import SwingPlusModel
import pandas as pd

model = SwingPlusModel("swing_plus_model_v1.joblib")
df_2026 = pd.read_parquet("statcast_2026_H1.parquet")  # raw pitch data
df_2026["half"] = "2026_H1"
leaderboard_2026 = model.score_pitch_level(df_2026)
```

See `MODEL_README.md` for the full input schema and API.

## Validation results (key numbers)

| Test | Result | Interpretation |
|---|---|---|
| Half-to-half stability | r = 0.88 | Measures a real, repeatable skill |
| Swing-change cohort ΔSwing+ vs ΔxwOBAcon | r = 0.45 | Catches real swing changes when they happen |
| Q1 vs Q5 next-half xwOBAcon | 0.318 vs 0.421 | Monotonic, meaningful discrimination |
| Predicting next-half xwOBAcon | r = 0.65 | Beats bat speed (0.58) and last-half xwOBAcon self-prediction (0.62) |
| Predicting next-half RV/swing | r = 0.31 | Beats all alternatives, modestly |

## Disclaimers

This is a personal/research project. The metric is descriptive of swing-derived run value, not of overall offensive value. Do not use Swing+ as a sole input to player evaluation decisions.
