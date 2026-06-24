# Swing+ — Deployable Inference Package

A two-model regression that scores MLB hitters' swing path quality from
Statcast bat-tracking data. Trained on 2023 H2 — 2025 H2.

## Files

- `swing_plus_model_v1.joblib` — the trained artifact (fitted pipelines +
  feature names + calibration constants). About 4 KB.
- `swing_plus.py` — standalone inference module. Loads the artifact and
  exposes `SwingPlusModel`.

## Dependencies

Python 3.10+ with `joblib`, `numpy`, `pandas`, `scikit-learn`. That's it.
No training-time dependencies.

## Quick start

```python
from swing_plus import SwingPlusModel
import pandas as pd

model = SwingPlusModel("swing_plus_model_v1.joblib")

# Load pitch-level Statcast data (e.g., via pybaseball.statcast for a date range)
pitches = pd.read_parquet("statcast_2026_H1.parquet")
pitches["half"] = "2026_H1"   # add a season-half label

leaderboard = model.score_pitch_level(pitches)
print(leaderboard.head(20))
```

Output is a DataFrame ranked by `swing_plus`, with columns:
- `batter` — MLBAM ID
- `swing_plus` — final score, reliability-weighted toward 100
- `swing_plus_raw` — score before reliability weighting
- `reliability` — weight (0–1) of player's raw score vs. league mean
- `p_bip_pred`, `rv_bip_pred`, `xrv_per_swing` — model intermediates
- `n_swings`, `n_bip`, `bip_rate_obs` — sample counts
- The tracking feature means and standard deviations used as inputs

## Required input columns (per pitch)

| Column | Type | Notes |
|---|---|---|
| `batter` | int | MLBAM player ID |
| `bat_speed` | float | mph; only populated on real swings |
| `swing_length` | float | feet |
| `attack_angle` | float | degrees, + up |
| `attack_direction` | float | degrees, + toward pull |
| `swing_path_tilt` | float | degrees |
| `intercept_ball_minus_batter_pos_x_inches` | float | lateral contact offset |
| `intercept_ball_minus_batter_pos_y_inches` | float | depth contact offset |
| `type` | str | 'X' = ball in play, 'S' / 'B' otherwise |

## Optional columns

- `half` or `season` — passed to `group_by` for season-half or season rollups
- `name` — player display name (passes through to output)

## Scoring 2026 data

When 2026 Statcast data becomes available:

1. Pull pitch-level data via pybaseball or Baseball Savant CSV export
2. Ensure the columns above are present
3. Add a `half` column with the season-half label (e.g., `"2026_H1"`)
4. Run `model.score_pitch_level(df)`

You don't need to retrain. The model is fitted on 2023–2025 and produces
calibrated scores on any new bat-tracking data with the same column schema.

## Model methodology (one paragraph)

Two regression pipelines (StandardScaler → PolynomialFeatures(degree=2) →
RidgeCV) predict P(BIP) and expected run value given BIP, respectively,
from player-half profiles (mean and SD of 7 Statcast bat-tracking
variables over ≥180 competitive swings). The two predictions are
combined as `xRV = P(BIP) * RV|BIP + (1-P(BIP)) * RV_nonbip` and
linearly rescaled so the training mean = 100 and SD = 10. Final scores
are reliability-weighted toward 100 with k=360 swings.

## Honest limitations

- **Trained on contact-point measurements only.** No access to the
  in-flight bat path. Disagreements with metrics that use richer
  representations (e.g., Driveline's 18-point reconstruction) on
  specific players are expected and not a bug.
- **xwOBAcon-style target.** Rewards swings that generate run value
  through contact damage. Contact-first hitters (Steven Kwan,
  Luis Arráez, Jacob Wilson) will grade low here even though they
  are productive MLB hitters via approach and BABIP.
- **Calibration anchored to 2023H2-2025H2.** If the league-wide
  distribution of bat-tracking values shifts meaningfully (e.g.,
  league-wide bat speed increases), the 100-anchor will drift.
  Retrain seasonally to keep the anchor honest.
- **Marginal predictive lift over simpler metrics.** Beats bat speed
  alone by ~0.07 r and last-half xwOBAcon by ~0.03 r on next-half
  outcome prediction. Real but small.

## Validation

- Half-to-half stability: r = 0.88 (high — measures a real skill)
- Movers-cohort delta correlation (ΔSwing+ vs ΔxwOBAcon): r = 0.45 (real
  changes are captured when they happen)
- Top quintile vs bottom quintile next-half xwOBAcon spread: 0.421 vs
  0.318 (meaningful discrimination)

## Versioning

Current version: 1.0.0. The `version` field in the artifact identifies
which training run / methodology was used. If you upgrade to a future
version, prior scores are not directly comparable until a re-anchoring
pass.
