# Features

Each feature ships with a **spec** (what / inputs / outputs / definition of done), an
**owner**, and a **data-dependency list**. Template at the bottom — copy it for every new feature.

Default owner: **@willclq** (reassign per feature as the team grows).

---

## Swing+ — bat-path quality
- **What:** Grades a hitter's swing-generated power / contact-quality potential from 9 Statcast bat-tracking features. 100 = league avg, SD 10, reliability-shrunk by sample.
- **Inputs:** competitive swings with bat-tracking (`bat_speed`, `attack_angle`, `swing_length`, `attack_direction`, `swing_path_tilt`, contact-point intercepts, std terms).
- **Outputs:** `swing_plus` (+ `swing_plus_raw`, `reliability`) per (batter, window) on the leaderboards.
- **Definition of done:** half-to-half reliability ≥ 0.85; calibration slope ~1.0; no leakage (inputs only). ✅ audited B+.
- **Owner:** @willclq
- **Data deps:** `swing_plus_model_v1.joblib`; `data/raw/statcast_*.parquet`; produced by `run_leaderboard.py`.

## Decision+ — swing/take selection (MLB-native)
- **What:** Run value of each swing/take decision vs league, base-out-count aware (`delta_run_exp`), tailored to the hitter's own swing outcomes. 100 = avg.
- **Inputs:** all pitches (location, count, base-out, `delta_run_exp`, description); per-hitter whiff/contact rates by group×zone.
- **Outputs:** `decision_plus_mlb`, run-value drivers `dec100_chase/zone/2k/early`; rolling `decision_traj.parquet`.
- **Definition of done:** split-half r ≥ 0.75; face-valid (Belt/Choi top, Báez bottom); selectivity (not abstinence) explains ≥ 0.8 of the grade. ✅ audited A−.
- **Owner:** @willclq
- **Data deps:** `data/raw/statcast_*.parquet`; built by `mlb_decision.py` → `mlb_decision.parquet`; rolling graph by `decision_drivers.py` → `decision_traj.parquet`.

## B2B+ — bat-to-ball / contact quality
- **What:** External 12-module Bat-to-Ball+ framework's headline (= Bayesian damage-conversion). Third orthogonal axis (~r0 with Swing+/Decision+, +0.32 with OPS).
- **Inputs:** per-batter-season artifact from the external framework; for 2026, BIP scored through the framework's opportunity LightGBM models + calibration.
- **Outputs:** `b2b_plus` (+ `contact_plus_b2b`, `dc_plus_b2b`) joined onto the boards.
- **Definition of done:** joins by (batter, season); 2026 calibrated to framework scale (R²≥0.65) and low-sample-shrunk. ✅
- **Owner:** @willclq  (external model owner: bat-to-ball framework maintainer)
- **Data deps:** `data/processed/bat_to_ball_plus.parquet` (external artifact); `b2b_2026.py` also needs the framework's `models/opportunity_*_v2.lgb.joblib` (external) + `data/raw/statcast_2026_H1.parquet`.

## Hitter+ — complete-hitter metric
- **What:** OPS-optimal blend of Swing+ (0.39) · Decision+ (0.28) · B2B+ (0.33), standardized to 100/SD 10; decomposes into the three axes.
- **Inputs:** `swing_plus`, `decision_plus_mlb`, `b2b_plus` on a board.
- **Outputs:** `hitter_plus` + `h_swing_part`, `h_dec_part`, `h_b2b_part`.
- **Definition of done:** beats SEAGER & SwingDecision+ on ISO/BB%/OPS (same & next season), out-of-sample. ✅ (OPS next: 0.47 vs SEAGER 0.34).
- **Owner:** @willclq
- **Data deps:** all three axis columns on the board; computed by `hitter_plus.py` (and `combo_plus.py` for the 2-axis SwingDecision+).

## Per-pitch swing grades / Matchup / Aging / Model report cards
- **What:** swing-grade tab (per-swing 20-90 grades + percentiles), hitter-vs-pitcher arsenal matchup, aging projection, and in-app model audit cards.
- **Inputs:** `swing_grades.parquet`, `pitcher_arsenal.parquet`, drift estimates, board rows.
- **Outputs:** modal tabs in the web app; `web/static/*_report_card.png` (generated).
- **Definition of done:** endpoints return for all covered hitters; cards regenerate from `report_card_*.py`.
- **Owner:** @willclq
- **Data deps:** `swing_grades.parquet`, `pitcher_arsenal.parquet`, `swing_grade_models.joblib`, MLB StatsAPI (birthdates) — all external/generated.

---

## Feature template (copy for every new feature)

```
## <Feature name>
- **What:** one-line description.
- **Inputs:** data / params it consumes.
- **Outputs:** columns / files / endpoints it produces.
- **Definition of done:** measurable acceptance criteria (validation thresholds, coverage).
- **Owner:** @github-handle
- **Data deps:** tables / files / APIs / external datasets / services it needs (cross-ref DATA_DEPENDENCIES.md).
```
