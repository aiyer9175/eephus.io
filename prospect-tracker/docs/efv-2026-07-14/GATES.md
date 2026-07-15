# eFV improvement pass 2026-07-14 - pre-registered gates

Registered BEFORE any experiment ran. Baselines re-measured same-day on the
fresh (2026-07-14 run) matrices via `python tools/efv_ml_lab.py --selftest`:

| side | blend_rho | pure_rho | within-tier wm | t45 |
|------|-----------|----------|----------------|-----|
| hit  | 0.3458    | 0.3556   | 0.1631         | 0.1138 |
| pit  | 0.2926    | 0.2963   | 0.1375         | 0.1477 |

Noise floor: 0.0023 (identity-refit movement, per the ops_rel ledger).
All experiments run on the standard forward-chained OOS protocol
(tools/efv_ml_lab.py / efv_lab_runner.py). Ship decisions are per-side.

## E-AGE: absolute age as a hitter/pitcher feature

Motivation: the model carries only age_rel_level; a 26.6yo AAA player reads
as "+2 vs level" - mild - while absolute age is the dominant clock on a
6-year outcome window (Nathan Hickey case). Feature: milb.age (age at the
production read) + age_missing indicator, mean-imputed via standardization.

SHIP iff (blended, per side): pooled rho >= baseline + 2x noise (+0.0046)
AND within-tier wm >= baseline - noise AND t45 >= baseline - noise.
Secondary report: era split stability (no single-era carry).

## E-LAMBDA: blend-weight cap-raise (the queued owner decision)

The registered [0.50, 0.70] hit sweep censored its optimum at the band
ceiling (xfv_lambda_confirm ledger). Sweep lam in {0.75, 0.80, 0.85, 0.90}
for hit and {0.45, 0.60, 0.65, 0.70} for pit on the SHIPPED feature set.

SHIP iff: blended pooled rho >= baseline + 2x noise at some lam, the
rho-vs-lam curve is concave-ish around the pick (not a boundary spike),
AND both era splits move >= -noise (no era trade).

## E-STALE: anchor-staleness discount (serve-time, outcome-calibrated)

Motivation: 274 active players (~7%) carry consensus anchors >1y stale
(fv/tools frozen at last listing, stats/age current) - a train/serve
mismatch; training rows always have staleness 0. Mechanism: a serve-time
decay of the consensus anchor for long-unlisted players, calibrated ONLY
from the dropped-cohort ground-truth study (last listed 2021/2022, outcomes
observable) - fit on the 2021 half, validated on the 2022 half.

SHIP iff, on the held-out drop-year: mean |implied_FV - realized_implied_FV|
improves vs the undecayed anchor AND the decayed grades' bust-rate
calibration (predicted p_bust vs realized bust share in FV bands) is no
worse. If the ground-truth study shows dropped players do NOT
underperform same-FV re-listed controls, E-STALE does not ship (null
result recorded as a loss ledger).

## Results (recorded post-run; the gates above were frozen first)

- **E-AGE: mechanical NO SHIP -> OWNER-DIRECTED SHIP of age-only, both
  sides** (data/xfv_age_feature_eval.json). Best variant missed the pooled
  auto-ship bar by 0.0003, but age-only moves every metric >= -noise (a
  non-loss) and the debuted-only eval pool is structurally blind to the
  never-debut risk absolute age targets (the explicit owner ask: a 26.9yo
  AA reliever ranked ~#77). The age_missing indicator variant stays
  rejected (pit t45 -0.23, sparse-column class).

## Addenda (2026-07-14 owner asks, evaluated in-pass)

- **x_era_k double-bad quadrant** (audit finding): 730 live pitchers carry
  a spurious positive "K-backed run prevention" when era AND K-rate are
  both worse than level. BOTH fixes tested and REVERTED under the
  no-losses rule: flip costs pit t45 -0.044, zero costs -0.023 (the
  debuted-only pool credits the boost via survivorship). Deferred with
  evidence in the _x_era_k docstring; mitigated by the age ship (the
  double-bad class skews old).
- **Exit velocity into eFV**: already present via the SC+ live overlay
  (_statcast_factor) - SC+ is built from avg EV, barrels (98mph+ band) and
  EV/LA expected-wOBA-on-contact. A dedicated ridge EV feature is
  UNTRAINABLE: statcast coverage on training rows is 0/800 (MiLB Statcast
  is public-AAA-2023+ only; the 2011-2023 decision cohorts predate it).
  No-ship by data boundary; revisit when 2023+ cohorts resolve (~2029).
- **Owner-directed live prospect-age penalty** (efv_score._age_factor):
  the shipped age FEATURE is honest but small (the debuted-only training
  pool is survivorship-censored, so the data cannot price never-debut
  risk), leaving Andrew Moore at ~#77. Shipped the injury-penalty-pattern
  overlay instead: LIVE-only multiplicative tilt on the model WAR term,
  1.0 through age 25, -0.10/yr after, floor 0.75; transparent "Prospect
  age penalty" factor chip. Policy dial, not an empirical claim - exactly
  the _injury_factor precedent. No eval-measured loss (the overlay never
  touches the resolved eval path).
- **AA-over-AAA production weighting** (owner intuition): REFUTED by the
  training data - spearman(ops_rel, WAR6) is HIGHER at AAA (0.144, n=182)
  than AA (0.071, n=211) among debuted rows; age dominates both (-0.27 /
  -0.32). The Moore class is an AGE problem, not a level-weighting one;
  no level re-weighting ships.
- **E-LAMBDA: HIT SHIPS, PIT DOES NOT** (data/xfv_lambda_band_eval.json).
  Hit composite rises monotonically past 0.70 to pure model (swept best
  0.975); clamped pick 0.90: composite +0.0253, bootstrap P=0.866, both
  eras + all four fold-years up. c5 interior-optimum fails BY CONSTRUCTION
  (censored at pure model) -> shipped as the owner-authorized cap-raise the
  M2 lab queued, ceiling = the 0.90 hard clamp (retained 10% consensus
  guard is a design floor, not an empirical optimum). Pit d_comp -0.0003,
  bootstrap 0.233: band stands at [0.50, 0.70].
- **E-STALE: SHIPS** (data/xfv_stale_anchor_eval.json). Dropped cohorts
  bust 91.9%/93.8% (2021/2022) vs ~55% re-listed controls, realized implied
  ~FV20-23 vs FV35-45 anchors. Held-out per-band clauses all pass (incl.
  45, validate n=20). Shipped schedule: 0 to 18mo, linear ramp to 30mo,
  terminal 10 FV pts, bands 35-45 only, active players only, display
  consensus untouched. Constants test-pinned to the artifact.

## Repair pass (same day, second session): the audit's findings implemented

The 5-agent audit's findings were verified inline and fixed. Label
integrity first: (1) 41 veteran re-appearances mislabeled as MLB debuts
(decline-tail labels on prospect anchors) - dropped with accounting;
(2) career_war sliding-window refetch was DELETING early-career seasons
(Correa's 2015 ROY year) - window floored at 2011, upsert made
merge-preserving, 1,628 payloads healed; (3) postseason-only debuts
re-dated; (4) ~20 real pitchers routed out of the hitter cohort
(0-AB batting statlines no longer count as side evidence). Model
mechanics: x_era_k double-bad quadrant ZEROED (owner-directed);
tool imputation moved to observed train means (tool_fb 58.0 - the flat
45.0 was a ~1.3 SD live penalty on the 56-65% tool-missing majority);
milb_missing no longer fires for data-availability (2011-2015 rows are
neutral via milb_unavailable); n_milb_seasons capped at the train
support (8); eval guard-order crash fixed; sign-preserving tool-blend
clamp. Ungraded model: production-only fit/eval pools, cold-cache
cameo sub-floor fail-open. Scoring/display: backgrade injury penalty
un-deadened (live IL fields populated), no-track-record backgrades
prior-anchored per contract, ~2,200 bust rows moved onto the live
quantile scale, post-debut anchors tagged, KRP+ gated on real exposure,
mid-season league norms blended with the prior season by qualified
count, live lambda stamped into xfv.json meta, four stale docstrings
corrected.

**RETRACTION: the E-LAMBDA hit cap-raise.** On the repaired labels the
raise's evidence evaporated (interior optimum ~0.8875, composite gain
+0.0082, bootstrap P=0.677 - below every gate): the corrupted labels
had been making consensus look artificially weak. Band restored to
[0.50, 0.70], ledger + registry + pin updated. The corrected-label
baselines: hit blend 0.3808 / wm 0.1725 / t45 0.0766; pit 0.3002 /
0.1390 / 0.1891. E-STALE re-validated unchanged ({35,40,45}: 10.0);
E-AGE re-measured, still a non-loss, now positive on every metric.

## Binding constraints

- No re-attempt of ledgered losses: alpha criterion, cohort-lambda
  hierarchy, pitcher cohort interactions, hitter game power.
- Anything that ships gets: its own lab tool under tools/, a committed
  data/*_eval.json ledger, a model_registry row/verdict update, and a
  golden bump. Losses get the eval ledger committed anyway.
