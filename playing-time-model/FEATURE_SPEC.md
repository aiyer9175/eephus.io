# Feature Spec — Playing Time Model

## What it is
A fully-owned (no third-party projection dependency) system that projects MLB
hitter **playing time** for the entire player population, plus role and
in-season variants. Three deliverables:

1. **Preseason full-population PA projection** — every hitter (incumbents +
   pre-debut prospects) gets projected next-season plate appearances.
2. **In-season rest-of-season (ROS) PA refresh** — re-projects remaining PA at
   any midseason date using what has actually happened (usage to date, current
   IL status).
3. **Role outputs** — full-time-role probability and a platoon-usage index.

Built research-first: every feature earns inclusion only by beating the prior
champion out of sample (see `reports/` and `expansion/research/` for the full
audit trail of what shipped vs what was rejected).

## Inputs
- Historical MLB usage (PA / games / starts by position), 2000–present
- Talent rates (projection-engine backbone; swing_plus rate projections)
- Minor-league stat lines + org affiliation
- Draft pedigree (pick, bonus), prospect FV/scouting grades
- Roster economics: 40-man / option / Opening-Day roster status, transactions
- Injury history + dated IL timeline (from transaction log)

## Outputs (per player-season)
- `pred` — projected PA (preseason)
- ROS PA (in-season, by cutoff date)
- full-time-role probability; `platoon_index` (same-hand share vs handedness
  baseline; negative = platoon-protected)
- All written to `data/processed/` (external storage, NOT in git)

## Definition of done
- Preseason model beats prior champion OOS on R²/RMSE and is competitive with
  the public benchmark (Steamer) on the full population, with **zero external
  projection inputs**. ✅ (full-pop R² .791 vs Steamer .772; rho .838 vs .843)
- Every shipped feature survives leakage + stress audits and beats the
  historical-usage + talent baseline. ✅ (validation ladder, `reports/03`+)
- In-season ROS refresh beats stale-preseason and naive pace. ✅ (E14 + E30)
- Reproducible from the documented pipeline against the listed data sources. ✅

## Headline results (holdout targets 2023–2025)
| Universe | Metric | Ours (owned) | Steamer (benchmark) |
|---|---|---|---|
| Full population (n=4,309) | R² / MAE / RMSE / rho | .791 / 54.4 / 92.5 / .838 | .772 / 49.4 / 96.5 / .843 |
| Incumbents (n=1,985) | R² / MAE / rho | .714 / 94.5 / .861 | .674 / 90.3 / .848 |
| Prospects (n=2,324) | R² / MAE / rho | .353 / 20.1 / .452 | .459 / 14.4 / .415 |
| In-season ROS (n≈3,270) | R² / MAE | .573 / 70.9 | (pace .545 / 66.7) |

We win R²/RMSE and rank-order as well as Steamer with no dependency; we beat it
outright on aging/established players; Steamer keeps a small MAE edge on
young/role-contested players (its curated playing-time info — a projection we
deliberately don't consume). See `expansion/research/E25_winloss_map.md`.

## Owner
**Will Cahoon (@willcolqhn)** — design, modeling, maintenance.

## Status
Preseason full-population model + in-season ROS refresh + role outputs SHIPPED.
Open: discrete-time debut hazard upgrade; productionization.
