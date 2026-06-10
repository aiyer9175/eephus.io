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

## Savant collision dataset — bat-ball collision geometry (NEW)
- **What:** Per-(batter, season) collision measurements from Savant's swing-timing-miss-distance leaderboard: avg miss distance, perfect/flawed contact %, horizontal alignment (tied-up/centered/flailed), timing (early/on-time/late), vertical alignment (over/lined-up/under) + engineered biases/entropies. Audited per the universal framework before any model use — full results in `COLLISION_REPORT.md`.
- **Inputs:** Savant `leaderboard/bat-tracking/swing-timing-miss-distance` CSV endpoint (2023 ASG onward; supports season + dateStart/dateEnd).
- **Outputs:** `data/processed/savant_collision.parquet` (full seasons) + `savant_collision_halves.parquet` (split-half reliability panels).
- **Definition of done:** reliability (split-half ≥ 0.5, y2y up to 0.82) ✅; projectability (next-whiff r up to 0.73) ✅; leakage LOW ✅; per-model incremental verdicts documented ✅.
- **Owner:** @willclq
- **Data deps:** Baseball Savant CSV endpoint (external API); `savant_collision.py`.

## Contact+ v2 — collision-aware contact-frequency axis
- **What:** Upgraded contact-FREQUENCY axis: ridge on [Contact+ v1, perfect/flawed %, vertical-alignment entropy, lined-up/over %, collision entropy, miss distance] fit to next-season whiff; 100 = avg, SD 10, shrunk K = 150 swings. Replaced v1 as the displayed/blended axis (v1 fallback where collision data missing).
- **Inputs:** `savant_collision.parquet` + v1 `contact_plus` (external framework artifact).
- **Outputs:** `data/processed/contact_v2.parquet` → `contact_axis` (+ `contact2_plus`) on boards; leaderboard "Contact+" column.
- **Definition of done:** beats champion v1 out-of-sample on next-whiff (ΔR² +0.089, leave-transition-year-out; r −0.854 vs −0.799) and next-K% (+0.032); robust per fold, archetype, bat side, strict thresholds; 2026 scored directly (463 hitters). ✅
- **Owner:** @willclq  (v1 external model owner: bat-to-ball / contact framework maintainer)
- **Data deps:** `savant_collision.parquet`, `bat_to_ball_plus.parquet` (external artifact); built by `contact_v2.py` (audit: `collision_audit.py`). Legacy 2026 v1 calibration: `contact_2026.py` + framework `difficulty_contact.lgb.joblib`.

## Hitter+ — complete-hitter metric (4-axis)
- **What:** OPS-optimal blend of all four orthogonal axes — Swing+ (0.37) · Decision+ (0.20) · B2B+ (0.24) · Contact+ v2 (0.18) — standardized to 100/SD 10; decomposes into the four axes.
- **Inputs:** `swing_plus`, `decision_plus_mlb`, `b2b_plus`, `contact_axis` on a board.
- **Outputs:** `hitter_plus` + `h_swing_part`, `h_dec_part`, `h_b2b_part`, `h_contact_part`.
- **Definition of done:** beats SEAGER, SwingDecision+, and the 3-axis version on overall production (next-OPS 0.52 vs SEAGER 0.34) out-of-sample; adding Contact+ lifts next-season K% prediction 0.45 → 0.81. ✅
- **Owner:** @willclq
- **Data deps:** all four axis columns on the board; computed by `hitter_plus.py` (and `combo_plus.py` for the 2-axis SwingDecision+).

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
