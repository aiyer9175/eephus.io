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

## DCV+ — damage-geometry / pull-air axis
- **What:** External Damage Conversion+ framework's composite: converts contact into pulled-air damage (pull-air rate 0.20 / spray-SLG bonus 0.02 / HR-window 0.13 blend, 100±10). The ISO/HR-geometry axis; orthogonal to all other axes (max |r| 0.21 vs Swing+; B2B+ carries no pull-air info, r −0.14 — cannibalization check passed).
- **Inputs:** framework artifact (2023-25); for 2026, raw damage-geometry rates (pulled-air, pulled-barrel, HR-window, pull) computed from raw Statcast with the framework's exact cuts (replication r = 1.000), calibrated to the dcv_plus scale.
- **Outputs:** `data/processed/dcv_plus.parquet` → `dcv_plus` on boards; leaderboard "DCV+" column.
- **Definition of done:** OPS-optimal weight ≠ 0 in the 5-axis blend (0.13 ✅); lifts Hitter+ same-season ISO 0.69→0.81 and next-ISO 0.58→0.64 (5-fold CV); 2026 calibration R² ≥ 0.9 (0.985 ✅), K=100 BIP shrink.
- **Owner:** @willclq  (external model owner: damage-conversion framework maintainer)
- **Data deps:** `~/damage_conversion_plus/data/processed/{damage_conversion_plus,batter_season_damage}.parquet` (external artifacts); `data/raw/statcast_*.parquet`; built by `dcv_2026.py`.

## Hitter+ — complete-hitter metric (5-axis)
- **What:** OPS-optimal blend of all five orthogonal axes — Swing+ (0.31) · Decision+ (0.16) · B2B+ (0.23) · Contact+ v2 (0.17) · DCV+ (0.13) — standardized to 100/SD 10; decomposes into the five axes.
- **Inputs:** `swing_plus`, `decision_plus_mlb`, `b2b_plus`, `contact_axis`, `dcv_plus` on a board.
- **Outputs:** `hitter_plus` + `h_swing_part`, `h_dec_part`, `h_b2b_part`, `h_contact_part`, `h_dcv_part`.
- **Definition of done:** beats SEAGER, SwingDecision+, and the 3/4-axis versions out-of-sample (same-season ISO r 0.81, K% 0.88, OPS 0.69; next-OPS 0.51 vs SEAGER 0.34, next-ISO 0.64, next-K% 0.79). ✅
- **Owner:** @willclq
- **Data deps:** all five axis columns on the board; computed by `hitter_plus.py` (and `combo_plus.py` for the 2-axis SwingDecision+).

## Per-pitch swing grades / Matchup / Aging / Model report cards
- **What:** swing-grade tab (per-swing 20-90 grades + percentiles), hitter-vs-pitcher arsenal matchup, aging projection, and in-app model audit cards.
- **Inputs:** `swing_grades.parquet`, `pitcher_arsenal.parquet`, drift estimates, board rows.
- **Outputs:** modal tabs in the web app; `web/static/*_report_card.png` (generated).
- **Definition of done:** endpoints return for all covered hitters; cards regenerate from `report_card_*.py`.
- **Owner:** @willclq
- **Data deps:** `swing_grades.parquet`, `pitcher_arsenal.parquet`, `swing_grade_models.joblib`, MLB StatsAPI (birthdates) — all external/generated.

## Skill-vs-Luck layer — variance/regression model
- **What:** Per-batter-season skill estimates and luck decomposition from the external variance model (M0–M12): `skill = e2 + PA/(PA+k) × residual`, where e2 is a cross-fitted, PA-weighted expectation from the five composites + sprint speed, and k is the model's calibrated shrinkage table (posterior slopes 1.00–1.07). `luck = observed − skill` is the part projected to vanish. Defense/weather/pitcher-quality/lineup/teammates were adjudicated and EXCLUDED by the source model (≤1% of season-grain residual variance); park retained only inside BABIP.
- **Inputs:** variance-model handoff artifacts (`variance_model_output.parquet`, `shrinkage_constants.csv`, `engine_adjustments.json`); five composite columns + Savant sprint-speed leaderboard; observed 2026 stats from boards/`obs_rates.parquet`.
- **Outputs:** `data/processed/variance_layer.parquet` → `sk_woba`, `luck_woba`, `sk_iso`, `luck_iso` on boards (all-time view shows current-season values); "Skill vs luck" leaderboard group.
- **Definition of done:** beats naive stat-carry on the untouched 2025→2026 holdout — next-wOBA r 0.255→0.328, MAE −11%; next-ISO 0.435→0.491; next-AVG 0.205→0.310; 2026 e2 refit reproduces handoff expectations (wOBA r 0.91, ISO 0.99) and matches gold holdout performance. ✅ 397 hitters scored for 2026.
- **Owner:** @willclq  (external model owner: variance-model maintainer)
- **Data deps:** `~/variance_model_handoff.zip` artifacts (copied to `data/processed/variance_handoff/`); Savant sprint-speed CSV endpoint; built by `variance_layer.py`. Engine TODOs deferred by design: multi-year pooling, aging, league renorm, elite-tail (see `engine_adjustments.json`).

## Hitter+ next — future-skill projection (aging framework)
- **What:** Next-season projected skill per axis (`proj_next = a + b·current + f(age)`), blended into a projected Hitter+. Reversion `b` measured per axis (Swing+ 0.85, Contact+ 0.81, Decision+ 0.66, B2B+ 0.53, DCV+ 0.51); aging term included ONLY where it passed the incremental gate — Swing+ quadratic (+0.9 pts at 23 → −0.4 at 34, ages clipped 22–36). Decision+/Contact+/B2B+/DCV+ aging curves tested and REJECTED (OOS ΔRMSE ≤ 0.011); the frameworks' cross-sectional "ages up" findings shown to be survivor composition. Full audit trail (anti-overlap, reliability, survivorship, leakage, champion-challenger, uncertainty): `~/aging_curves/reports/AGING_REPORT.md`.
- **Inputs:** longitudinal skill panel (5 axes + subcomponents, 2023–26, ages from birthdates + MLB Stats API).
- **Outputs:** `data/processed/aging_projection.parquet` → `hitter_plus_proj` on boards; "Hitter+ next" column (all-time shows current-season projection).
- **Definition of done:** anti-overlap LOW for all five models ✅; aging terms ship only where OOS-positive (Swing+ 2/3 folds, 2-yr +0.063 RMSE ✅); survivorship documented (survival 86%→63% by 35+, skill-selected) ✅; reproducible (deterministic, transition-year CV) ✅.
- **Owner:** @willclq
- **Data deps:** `~/aging_curves/` pipeline + panel; `birthdates.json` + MLB Stats API; all five axis sources. Constraint: do NOT stack with the variance engine's outcome-aging bias terms (double-count) or sum with the app's feature-level Swing+ aging tab.

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
