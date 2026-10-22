# R bake-off: results in plain language

Read once each on 2026-10-22, under `docs/r/R_BAKEOFF.md` (registered alone at de58ce9e, amended
before any read at 13cdf34b; the lab committed at eda93727 before the reads). Artifacts:
`data/_labs/r_bakeoff/aging_gam.json`, `data/_labs/r_bakeoff/xm_years_surv.json`,
`data/_labs/r_bakeoff/efv_glmm.json` (development, off the webroot). Every read ran after a
fixture dry run, in one session, with no rerun. Nothing served moved.

## The short answer to the owner's question

You asked whether R should replace something the site uses, or could build something better. The
three places where R's tools had the best case (smooth aging curves with player effects, contract
length as a duration, and partial pooling of prospects by club, level and draft class) were each
tested against what the site serves and against a no-information null, on development frames only.

- **None of the three beat what the site serves.** Two tie it (aging, contract years) and one
  loses (the eFV random effects).
- So no flip question comes out of this task. The served paths stay Python.
- R is installed, pinned (`docs/r/R_ENV.md`, `docs/r/renv.lock`) and wired through
  `tools/rbridge.py` as an offline fitting tool. The next model that needs a mixed model, a GAM
  or a survival fit can be registered and read through it without new plumbing. Anything it
  produced would ship as JSON read by Python, so the live box and the port never need R.

## (a) Aging curves: an mgcv GAM with player random effects

Frame: label seasons 2008 to 2011 (the development frames of the path-shape and aging v3 gates),
forward-chained, fWAR corpus. Statistic: weighted mean absolute error of next season's
(regressed) WAR rate, per side. Interval: player-cluster bootstrap, B 2,000, one-sided 97.5
percent bounds.

Hitters (1,389 player-seasons, 518 players; WAR per 600 PA):

| rater | error |
|---|---|
| GAM (R) | 0.7905 |
| served v2 curve | 0.7890 |
| no aging | 0.8018 |
| one constant change | 0.7960 |

- Served minus GAM: -0.0015 (97.5 percent bounds -0.0047 to +0.0014): a tie, the point on the
  served curve's side.
- The GAM beats both nulls: no aging by +0.0113 (bound +0.0063), the constant by +0.0054
  (bound +0.0015).
- Verdict: FAIL (ties the served curve)

Pitchers (1,456 player-seasons, 616 players; WAR per 250 BF):

| rater | error |
|---|---|
| GAM (R) | 0.2456 |
| served v2 curve | 0.2450 |
| no aging | 0.2488 |
| one constant change | 0.2467 |

- Served minus GAM: -0.0006 (-0.0036 to +0.0025): a tie.
- The GAM beats no aging (+0.0032, bound +0.0010) but only ties the constant (+0.0011, bound
  -0.0007).
- Verdict: FAIL (ties the served curve)

The planted check passed on both sides. A known curve was recovered within an RMSE of 0.033 to
0.048 (hitters) and 0.013 to 0.020 (pitchers) in every fold, against a bar of 0.10, and it was
detected against both nulls. So this is a real tie, not a blind instrument.

Reported, never adjudicated:
- The GAM's curve: hitters gain about +0.14 to +0.21 WAR per 600 PA moving into age 22, cross
  zero near 26 to 27, then lose about 0.17 at 33 and 0.27 at 40.
- Pitchers gain +0.08 per 250 BF into 22, cross zero near 28, and lose about 0.05 a year from
  33 on.
- The served curve with its survivorship correction switched off scored 0.7897 (hitters) and
  0.2433 (pitchers).
- The player-effect SD was not recorded: the script's variance-component read returned
  nothing, a reporting defect that touched no prediction.

On this frame, the served curve beats no aging by 0.0128 for hitters and 0.0038 for pitchers
(point values, no interval). It is a working curve, and a smoother with player effects adds
nothing to it.

## (b) xM$ contract years as an interval-censored duration

Frame: the xM$ development winters 2018 to 2024, forward-chained. Class years 2025 and 2026 (the
unread xM$ holdout) were never built. Rows: 893 MLB deals, 569 players. Statistic: years MAE.
Interval: player-cluster bootstrap, B 4,000.

| rater | years MAE | exact share | log-years MAE |
|---|---|---|---|
| flexsurv duration model (R) | 0.4815 | 66.7% | 0.2331 |
| served years stage (fa_market) | 0.4770 | 67.4% | 0.2291 |
| comps median | 0.5174 | 65.7% | 0.2504 |
| training median (constant) | 0.6349 | 68.6% | 0.3109 |

- Served minus R: -0.0045 (95 percent interval -0.0286 to +0.0190; one-sided bound -0.0247): a
  tie.
- R beats the constant by +0.1534 (bound +0.1084) and the comps median by +0.0358 (bound
  +0.0047).
- The generalized gamma converged in six of seven winters; 2018 used the registered lognormal
  fallback.
- Both planted checks passed:
  - On simulated years, the model came within 1.048 times the true model's error (bar 1.10) and
    beat the constant.
  - On permuted years, it found nothing (bound -0.0346).
- Verdict: FAIL (ties the served years stage)

The constant one-year guess has the highest exact-match share (68.6 percent), because one-year
deals dominate. That is why exact match is reported and never used as the rule.

## (c) eFV: crossed random effects on X3's model

Frame and statistic: X3's own. The pool has 3,096 rows (3,062 in groups of 20 or more), scored by
the within-(frame, side, year) Spearman. The fixed part is X3's ridge staged model, refitted fold
by fold; it reproduced X3's stored scores to 9.7e-13.

Random intercepts were added by side for:
- the club (from the transaction feed);
- level by season;
- the entry class (draft or first MiLB season).

These sources replaced the registered board records before the read (amendment A-1), because the
board records' coverage encoded whether a player reached the majors.

| rater | within Spearman |
|---|---|
| GLMM (R) | 0.1372 |
| X3 ridge (its fixed part) | 0.1741 |
| X3 | 0.1810 |
| PROSPX consensus | 0.2011 |
| served eFV | 0.2041 |

- GLMM minus served eFV: -0.0669 (95 percent interval -0.1086 to -0.0245).
- GLMM minus consensus: -0.0639 (-0.1075 to -0.0206). By side: hitters -0.0359 (-0.0837 to
  +0.0125), pitchers -0.0929 (-0.1664 to -0.0187).
- GLMM minus its own fixed part: -0.0368 (-0.0637 to -0.0094). The random effects made the order
  worse.
- The group null: 20 reruns with the club, level-season and entry-class labels shuffled scored
  -0.0291 to -0.0054 against the same fixed part (95th percentile -0.0100). The real groups did
  worse than every shuffled run.
- The fitted effects are large (org SD about 0.6 to 0.9 on the reach logit), but they do not
  carry forward to the next year's prospects.
- Planted check: an org effect planted in the playing-rate stage was recovered in eight of ten
  folds (correlations 0.61 to 0.88, bar 0.70), and in the reach stage in none (0.32 to 0.53).
  The instrument is weak for a reach effect of that size.
- Verdict: FAIL (trails PROSPX consensus), UNRESOLVED (planted check failed)

## What changes

Nothing served. No flag, registry row, glossary entry or served file moved, and no owner flip
question arises: under the registered rules each item stops at its FAIL.
