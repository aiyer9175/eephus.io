# Playing Time+ Expansion — Research Log

**Phase 1 = research/evidence. Phase 2 = integration, only after a feature
earns it.** Nothing enters Playing Time+ until it beats the existing champion
out of sample, survives leakage + org-stability audits, and justifies its
complexity. This log tracks the nine buckets and the evidence collected.

Parent model: `~/playing_time_model/` (champion: usage + talent + minors +
draft + tx + Opening-Day rosters + injury; beats Steamer on R²/RMSE/rho,
blend beats it on all four). Shared data reachable from `../data/`.

## Core questions → status

| # | Question | Status |
|---|---|---|
| Q1 | What predicts MLB debut timing? | v1 done (parent Module 15, AUC .865); upgrading to discrete-time hazard here |
| Q2 | What predicts MLB PA after debut? | **ANSWERED (E11): minors perf >> FV > draft/40-man/OD-roster; FV EARNS inclusion for prospects (rejected for incumbents)** |
| Q3 | What predicts full-time role? | **ANSWERED (E12/E13): full-time role prob AUC .881 (ships); platoon index stable+projectable+new-info (ships); bench share ~redundant w/ PA** |
| Q4 | How much does replacement pressure matter? | parent Module 4: same-team yr-t = NO-ADD; opportunity-cost reframe open |
| Q5 | Do orgs have persistent promotion tendencies? | **ANSWERED (E10): weak + fully mediated by 40-man → REJECT for debut** |
| Q6 | Does GM turnover change promotion behavior? | DEPRIORITIZED for debut (org itself mediated); needs GM data; test on platoon/rest |
| Q7 | Do managers matter? | **ANSWERED (E13): REJECT — 30.5% in-sample between-mgr platoon variance but +0.0000 OOS; player's own platoon history captures it** |
| Q8 | Does position mobility increase opportunity? | parent Module 5: flexibility no PA-lift; position lifecycle ALSO no-add (E15) |
| -- | Defensive Floor+ / speed / out-of-options (E15/E16) | **REJECTED both universes** — incumbents: mediated by usage history; prospects: redundant with FV (composite already bakes in defense) |
| -- | Contract / org investment (E06/E17) | **REJECTED** — pulled historical via Wayback Spotrac (1,627 recs 2023-25); LOYO CV no-add even on multiyear-guaranteed segment; mediated by OD roster + talent |
| Q9 | Can we beat conventional PA projections? | YES — FULL POPULATION (E20): ours beats Steamer R²(.792 v .772)/RMSE(92.2 v 96.5), ties rho; blend wins R²(.810)/RMSE(88.1)/ties rho/matches MAE |

## Role / platoon (E12/E13, 2026-06-13)
- Full-time role prob: SHIPS (AUC .881 vs naive .750).
- Platoon index (same-hand share − handedness/season baseline): stable
  (yoy r .56), projectable (R² .262 > naive .159), NEW info (PA-corr .47 vs
  bench .66) — SHIPS as a role output. data/processed/platoon_index.parquet.
- Bench share: stable but ~redundant with PA (corr −.66) — derived only.
- MANAGER (Q7): REJECT — 30.5% in-sample between-mgr platoon variance but
  +0.0000 OOS; player's own platoon history captures deployment. Same
  descriptive-not-predictive lesson as org (E10)/GM. No leadership FE enters.

## In-season rest-of-season updating (E14, 2026-06-13)
- Updating beats stale preseason hugely: ROS R² .426 → .548, MAE 80 → 67.
- Naive pace is a strong baseline; GBM ties (not beats) it → value is the
  UPDATE, not the model. Deployable = pace anchored + preseason shrinkage.
- Refinements to beat pace: start-rate-to-date + IL status + deadline trades.

## PHASE 2 — integration milestone (E20, 2026-06-13)
Full-population projection SHIPPED: incumbent champion (parent M02-21) +
prospect model (E11: perf+FV+draft+40man+OD-roster). 4,444 players/season
(1,990 incumbent + 2,454 prospect). data/processed/full_population_proj.parquet.
Deployable = blend w/ Steamer; Steamer-free unified is the no-dependency
fallback (still beats Steamer R²/RMSE). MAE-on-zero-mass: Steamer-free
calibration (calib-p × median) cut prospect MAE 19.5→18.0 w/ better ranking;
Steamer's residual MAE edge costs ranking → not chased; blend captures both.

## Data collection status

| Source | Status |
|---|---|
| Minor-league org affiliation (AAA/AA, 2009-25) | DONE — E01, 38,296 rows, 100% org-mapped |
| Manager history (team-season, 2009-26) | DONE — E02, 539 team-seasons, 19 with midseason changes captured |
| Debut dates | available (statsapi people.mlbDebutDate; tracker roster_status.mlb_debut_date) |
| Transactions (OPT/CU/SE/OUT/DFA, dated) | have (parent data/raw/transactions.parquet, 754k, 2002-26) |
| Call-up universe (AA/AAA pre-debut) | have (parent data/processed/callup_pairs.parquet) |
| **GM history** | **MISSING — not in statsapi; external collection (Wikipedia franchise GM tables / B-Ref). Q6 blocked until then.** |
| Position history (for mobility/lifecycle) | derivable from parent usage_spine fielding-by-position |

## Bucket deliverables

1. Debut Hazard — discrete-time monthly hazard (debut by May/Jun/.../next yr). Parent M15 = binary v1.
2. Role Hazard — competing risks (AAA/bench/platoon/regular/demotion/trade). Not started.
3. Opportunity Cost — Models A/B/C race. Parent M4 tested same-team replacement (NO-ADD); proper opp-cost (player − best alternative) open.
4. Organizational Behavior — **E10 (flagship this session): do org promotion tendencies persist + predict OOS?**
5. GM Effects — blocked on data.
6. Manager Effects — residual signal after org/talent controls. Data pulled.
7. Position Mobility — transition matrix + retention/cost. Not started.
8. Position Lifecycle — PA aging curves by position. Not started.
9. Prospect Pedigree — parent M6 (tracker FV) underpowered, M9 (draft) shipped. Re-test in call-up universe with org controls.

## Method notes (survival/hazard, grounded)

- Debut/role timing = right-censored time-to-event → discrete-time hazard
  (logistic per period) or Cox; competing risks for role. Discrete-time
  logistic chosen first: handles time-varying covariates (age, level, 40-man
  status by month), calibrates per-period, and slots into the existing GBM
  stack. Random Survival Forest as a challenger if linear hazard underfits.
- Org effect = hierarchical / partial-pooling intercept by org, OR the
  leakage-safe empirical route used in E10: residualize debut from PLAYER
  features, aggregate residual by org over a TRAILING window, test whether
  that prior predicts held-out future debut. Avoids fitting org dummies on
  the test period.

## Leakage rules (inherited, strict)

No future promotions / depth charts / rankings / contracts / GM changes /
position changes / role assignments. Every covariate timestamp-valid at the
prediction date (start of target season). Org tendencies use only seasons
strictly prior to the target year.
