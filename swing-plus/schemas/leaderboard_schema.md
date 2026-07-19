# Leaderboard schema

Columns in `data/processed/leaderboard_{alltime,season,half}.parquet` (and the API
`/api/leaderboard/{view}`). One row per (batter[, stand][, season|half]).

## Identity
| Column | Type | Notes |
|---|---|---|
| `batter` | int | MLBAM id |
| `name` | str | display name (handedness suffix for switch hitters) |
| `stand` | str | L / R |
| `season` / `half` | str | window key (season board / half board) |
| `n_swings` | int | competitive swings in window |
| `n_bip` | int | balls in play in window |

## Core axes (100 = league avg, SD 10)
| Column | Meaning |
|---|---|
| `swing_plus` | Swing+ — bat-path power/contact-quality (reliability-shrunk) |
| `swing_plus_raw`, `reliability` | unshrunk score + shrink weight |
| `decision_plus_mlb` | Decision+ — swing/take selection run value |
| `dec100_chase`, `dec100_zone`, `dec100_2k`, `dec100_early` | Decision+ run-value drivers (runs/100 pitches vs league; sum ≈ Decision+−100 in RV) |
| `b2b_plus` | Bat-to-Ball+ — contact-quality / damage-conversion axis |
| `swingdecision_plus` | OPS-optimal blend of Swing+ (0.63) + Decision+ (0.37) |
| `hitter_plus` | **headline** — OPS-optimal blend of all 3 (Swing 0.39 / Dec 0.28 / B2B 0.33) |
| `h_swing_part`, `h_dec_part`, `h_b2b_part` | Hitter+ decomposition (sum ≈ Hitter+−100) |

## Value / predicted production
| Column | Meaning |
|---|---|
| `blended_xwoba` | sample-size blend of observed + model-predicted full-PA xwOBA |
| `obs_xwoba`, `pred_xwoba` | the two blend inputs |
| `pred_xwobacon`, `pred_avg_ev90`, `pred_barrel_pct` | predicted batted-ball quality from swing tracking |
| `obs_*`, `bbdiff_*` | observed + (observed−predicted) residuals |
| `obs_hr_pct_pn`, `obs_iso_pn` | park-neutral observed HR% / ISO |

## Swing-tracking means (the 9 model features + display)
`bat_speed_mean`, `bat_speed_std`, `attack_angle_mean`, `attack_angle_std`,
`swing_length_mean`, `attack_direction_mean` (pull-positive for display),
`swing_path_tilt_mean`, `intercept_ball_minus_batter_pos_x_inches_mean`,
`intercept_ball_minus_batter_pos_y_inches_mean`, `attack_angle_bip`.

> Note: `attack_direction_mean` is stored **pull-positive** for display; the model and
> aging drift use the raw Statcast sign (pull-negative) — flip before scoring.
