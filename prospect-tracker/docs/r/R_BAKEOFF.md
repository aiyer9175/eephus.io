# R toolchain bake-off: registration (R_BAKEOFF)

Registration status: REGISTERED 2026-10-22, not read.

Committed ALONE, before `tools/rbridge.py`, any `.R` file, any lab, any artifact or any fitted
number of this document exists. Task R_TOOLCHAIN_BAKEOFF (owner 2026-10-19: "I just installed R
on this machine, is there anywhere across the site that R should be used in place of something
we're currently using / could be used to create something better?"; queued in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the 2026-10-19 queue line). Code citations are HEAD
9dd0f8d3; the anchor in brackets wins over a line number. No em-dashes.

## 0. The rule that binds everything here

R is an OFFLINE FITTING TOOL ONLY. No served path, exporter, nightly or monthly step, page or
test that a deploy depends on calls R. Every served path stays Python reading frozen JSON. A
bake-off that passes becomes an owner flip question whose answer would ship R-fitted
COEFFICIENTS as a JSON file read by Python; the live box and the port never need R. Nothing
served moves in this task: no exporter runs, no flag, registry verdict, glossary entry or served
artifact changes.

What was looked at before writing this: the code paths cited below, the section headings and
frame tables of `docs/AGING_V3_GATE.md`, `docs/PROJ_PATH_SHAPE_GATE.md`, `docs/xm/XM_GATE.md`,
`docs/efv-v2/EFV_X3_POOLED_MODEL.md` and its results, the field NAMES of a 2022 signing row and
of the X3 instance records, and row COUNTS of the cached X3 build. No candidate of this document
was fitted, and no outcome was read to write it.

## 1. The toolchain

- R 4.6.1 (`C:/Program Files/R/R-4.6.1`). Packages from CRAN only: mgcv, lme4, glmmTMB,
  survival, flexsurv, quantreg, jsonlite (renv for the lockfile). Versions pinned in
  `docs/r/R_ENV.md` with an renv lockfile beside it (`docs/r/renv.lock`).
- `tools/rbridge.py`: locates Rscript (PATH, then `C:/Program Files/R/R-4.6.1/bin/Rscript.exe`),
  runs one `.R` file with a JSON file in and a JSON file out, raises on a non-zero exit, and
  reports the R and package versions. Tests skip cleanly when R is absent.
- The `.R` scripts live in `tools/r/`. Each reads its input JSON, fits, and writes its output
  JSON; none reads or writes anything else.

## 2. Bans (each binds every item)

- Development frames only. No reserved eFV frame (R-LV, list vintages 2020 and 2021; R-VM, debut
  cohorts 2025 and later) is built, scored or used. The xM$ holdout (class years 2025 and 2026,
  `docs/xm/XM_GATE.md`, unread) is never loaded. No label season of 2026 is scored.
- Nothing is grouped, counted, averaged or stratified by consensus-FV level
  (`docs/PROSPECT_ANCHOR_GATE.md`); no FV-cell realized WAR mean, bust, debut or graduation rate
  is computed.
- `backtest.run_backtest` is never run. No projections retrain (`tools/train_proj_models.py`).
  No dark betting column is read.
- The shared `.cache` is never written: every lab wraps the projection fit cache read-only (a
  miss refits in memory and is not saved).
- Each item is READ ONCE. The lab refuses a second read once its artifact records one. A fixture
  dry run (synthetic data, no real outcome) precedes each read. The planted checks below run in
  the same session, before the real statistic is computed, and are reported whatever the real
  read shows.

## 3. Item (a): aging curves, a penalized GAM with player random effects

**Question.** Does an mgcv penalized GAM of the year-over-year change in WAR rate, with a
player random effect, predict next-season WAR rate better than the served aging curves?

**The served incumbent (INC).** The v2 champion WAR-rate curve: `fa_projection.fit_aging_curves`
[fit_aging_curves()] refit point-in-time with `max_season = L - 1` (pairs ending at or before
L - 1), read by `fa_projection.curve_delta(curves, side, role, "war_rate", age_t + 1)`
[curve_delta()], the role from `fa_projection.profile_role([row_t], side, base_role, league)`
[profile_role()] (the served lookup on a one-season history: pitcher K% cohorts, hitter
cohorts parked neutral). Aging v3 shipped no arm (`docs/AGING_V3_GATE.md` section 19), so this
is what serves.

**Rows (pairs).** From the fWAR corpus (`fa_projection.build_corpus()`, war_provider fwar,
seasons 2000 to 2026): a pair is (player, side, t) with exposure at least the fit's
`min_exposure_pair` (100 PA, 70 BF) in seasons t and t + 1 and age at t inside the fit's
`age_range` [21, 42]. Label season L = t + 1. The value at each season is the fit's own
regressed WAR rate `_val(r, "war_rate")` [fit_aging_curves(), def _val]: WAR per 600 PA
(hitters) or 250 BF (pitchers), regressed toward that season's league rate at
`war_rate_regression` (600 PA, 350 BF). Base role: hitters C or H, pitchers SP or RP (the
corpus row's role at t). Pair weight w: the fit's harmonic exposure weight
`2 / (1 / e_t + 1 / e_t+1)`. Season 2020 is never a label season.

**Frame.** Label seasons L in {2008, 2009, 2010, 2011}: the DEV frame of
`docs/PROJ_PATH_SHAPE_GATE.md` (4.6) and, for 2008 to 2010, of `docs/AGING_V3_GATE.md` (6).
Neither gate reads a verdict there. Forward-chained: for each L, every model is fitted on the
pairs with label season at most L - 1 (from L = 2001) and scored on the pairs with label season
L. A player's training pairs stay in training (that is the player effect's purpose); only
outcomes of season L are scored.

**Candidates.**
- GAM (the candidate): per side, `dv ~ role + s(age1, k = 10) + s(pid, bs = "re")`, where
  dv = v(t + 1) - v(t), age1 = age at t + 1, role the base role, pid the player; weights w scaled
  to mean 1; `mgcv::bam(method = "fREML")`. Prediction v(t) + the fixed part + the player's
  random effect when the player has a training pair, else 0.
- NULL N0 (no aging): v(t + 1) predicted as v(t).
- NULL N1 (one constant): v(t) + the w-weighted mean dv of the side's training pairs.

**Statistic.** Per side, the w-weighted mean absolute error of the predicted v(t + 1) over the
frame's scored pairs, in WAR per 600 PA (hitters) or 250 BF (pitchers).
D_X = MAE(X) - MAE(GAM), so a positive D favours the GAM.

**Intervals.** Player-cluster bootstrap over the scored pairs (players resampled with all their
pairs), B 2,000, seed 20261022, paired (the same draws for every D).

**Pass rule, per side (two sides, Bonferroni: one-sided 97.5 percent bounds).** PASS when ALL
of: (1) the lower bound of D_INC is above 0; (2) the lower bound of D_N0 is above 0; (3) the
lower bound of D_N1 is above 0; (4) the planted check passes. FAIL otherwise, worded "ties"
when the 97.5 percent interval of D_INC spans 0 and "trails" when its upper bound is below 0;
a run whose (4) fails is reported UNRESOLVED besides.

**Planted check (4), on the real design.** The frame's own pairs and their training sets (ages,
players, weights, roles, forward folds) with dv replaced by a planted truth:
f(age1) = 0.30 - 0.06 x (age1 - 26) per 600 PA (hitters) or per 250 BF (pitchers), plus a player
effect drawn N(0, 0.15^2), plus noise N(0, s^2 / w_rel) with s the side's w-weighted SD of the
real training dv and w_rel = w / mean(w); seed 20261022. PASS when the GAM's fitted curve is
within RMSE 0.10 of f over ages 23 to 35 in every fold, and D_N0 and D_N1 on the planted
outcome have lower bounds above 0.

**Reported, never adjudicated.** MAE by age band at t + 1 (24 and under, 25 to 27, 28 to 30,
31 to 33, 34 and over) for every rater; INC with the survivorship lambda set to 0 (the raw
smoothed delta), to show how much of any gap is the survivorship term; the GAM's curve and its
estimated player-effect SD per fold. The survivorship correction exists for players who drop
out, and a pair frame scores survivors only; that limit is disclosed with the result, whatever
it is.

## 4. Item (b): xM$ contract length as a censored duration

**Status of the comparator.** XM_1 registered the xM$ gate (70864a33) and its read STOPPED in
the holdout step (owner question XM1-Q1 open); its development step selected the incumbent
`fa_market.MarketModel` and no xM$ model is committed. So the comparator is fa_market's years
stage, as the task specifies for that case.

**The served incumbent (INC).** `fa_market.MarketModel(train, dpw_series)` [class MarketModel],
with `supply_by_year[W] = fa_market._supply(test, W)` as Gate 2 sets it
(`fa_backtest`, the Gate 2 loop [model.supply_by_year[W] = fm._supply(test, W)]); predicted
years = `predict(s)["proj_years"]` (the OLS log-years stage `_features_years`, rounded, clamped
to 1 to 15).

**Rows.** `fa_market.enriched_signings(2015, 2024)`: MLB deals with an as-of WAR path, class
years 2015 to 2024 only; 2025 and 2026 are never built. Scored rows: every row of a development
winter W in 2018 to 2024 (the xM$ gate's development frame) that has nearest comps
(`fa_market.comps_for(s, train)` non-empty, the Gate 2 row set). Training rows for winter W:
class year below W.

**Candidates.**
- SURV (the candidate): a parametric survival regression with years as an interval-censored
  duration, T in (Y - 1, Y] (a deal of Y guaranteed years is a duration that ended in year Y;
  one-year deals are left-censored on (0, 1]), `flexsurv::flexsurvreg(Surv(lo, hi, type =
  "interval2") ~ x, dist = "gengamma")`. The covariates x are the incumbent's own
  `_features_years` vector without its intercept, built by the same fold's MarketModel (comps
  stats from the training pool), z-scored on the training rows. If the generalized gamma fit
  fails or its Hessian is not positive definite in a fold, that fold uses `dist = "lnorm"` (the
  fallback is recorded per fold). Predicted years = ceil(median T), clamped to 1 to 15 (ceil
  because Y = ceil(T), and the median of Y is the ceiling of the median of T).
- NULL C: the training rows' median years (a constant per winter).
- NULL K: the nearest-comps median years (Gate 2's own baseline, `statistics.median(c["years"]
  for c in comps)`).

**Statistic.** Years MAE over the scored rows (integer predicted years against actual years),
pooled over the seven winters. D_X = MAE(X) - MAE(SURV). Reported: exact-match share and
log-years MAE for every rater, per winter.

**Intervals.** Player-cluster bootstrap (player_key), B 4,000, seed 20261022, paired.

**Pass rule.** PASS when ALL of: the one-sided 95 percent lower bounds of D_INC, D_C and D_K are
above 0, and the planted checks pass. FAIL otherwise, "ties" or "trails" as in item (a);
UNRESOLVED besides when a planted check fails.

**Planted checks, on the real design.** (P1) Signal: the true model is the lognormal AFT fitted on
the warm-up rows (class years 2015 to 2017, never scored); years are simulated for every row of
2015 to 2024 as ceil(T), clamped 1 to 15, seed 20261022, and the whole forward pipeline is rerun
on them. PASS when SURV's MAE is at most 1.10 x the oracle's (ceil of the true median) and D_C
has a lower bound above 0. (P2) Permuted null: actual years permuted within each class year
(seed 20261023) and the pipeline rerun; PASS when D_C's lower bound is NOT above 0 (no false
discovery).

## 5. Item (c): eFV hierarchy, crossed random effects on the X3 pooled frame

**Status of X3.** X3 (`docs/efv-v2/EFV_X3_POOLED_MODEL.md`) was read once on 2026-10-19 and
FAILED (ties consensus, unresolved); nothing of it is served. There is no "X3 served variant".
The served eFV is v5 COMBINED re-fit RT. This item therefore asks: does adding crossed random
effects to X3's own linear (ridge) staged model make an order that beats the served eFV and the
consensus null on X3's pool?

**Base (X3-ridge).** X3's class (a) staged model as X3's read fitted it, fold by fold:
`efv_x3_pooled.Staged("ridge", lam)` with lam the ridge configuration X3's nested selection
picked in that fold (`pick_class(inner, "ridge")` over the main run's recorded inner scores),
refitted on the fold's full training set on X3's cached build (a private copy of the read's
cache directory). Parity: the refit must reproduce the main run's X3-ridge test scores to 1e-9
on every fold, else nothing is read.

**The candidate (GLMM).** Each stage of the base keeps its fitted linear predictor as an
OFFSET, and crossed random intercepts are fitted on top on the same training rows and weights:
stage R `lme4::glmer(r3 ~ 1 + offset(eta) + (1 | org) + (1 | lvl_season) + (1 | entry_class),
family = binomial)`; stages T and Q `lme4::lmer` with the same terms (Gaussian, weighted, the
panel rows of the base). Groups, each SIDE-SPECIFIC (prefixed by side):
- org: the club on the instance's latest board point dated at or before its read
  (`efv_dataset.asof_records()` points), else UNK;
- lvl_season: the instance's `level_rank` feature value and its year;
- entry_class: the acquisition method and year (`acquisition.method`, `acquisition.year` on the
  universe record; a year after the read is set to UNK).
Scoring: each stage's base prediction plus the random effects of the instance's groups (0 for a
group not seen in the fold's training rows); the reach probability is sigmoid(eta + RE); the
inverse Mills ratio fed to T and Q stays the base's; the recombination is X3's (section 4.3 of
its document). If glmer fails to converge in a fold-stage, that fold-stage uses
`glmmTMB` with the same formula; if that fails too, the base stage is used and recorded.

**Statistic.** X3's: the size-weighted within (frame, side, year) Spearman W on X3's pool (3,096
rows after keep_lv, groups of at least 20 rows), `efv_beat_pooled_power.read_pool`, paired,
B 4,000, seed 20261020, player-clustered and club-clustered.

**Pass rule.** PASS when ALL of:
- (A) W(GLMM) - W(served eFV RT): one-sided 95 percent lower bound above 0, player-clustered
  AND club-clustered;
- (B) W(GLMM) - W(PROSPX consensus): the same (consensus is the null the whole program reads
  against);
- (C) the group null: W(GLMM) - W(X3-ridge) above the 95th percentile of the same delta over 20
  reruns with the three group labels permuted jointly within (side, instance kind, year)
  (seeds 20261024 to 20261043);
- (D) the planted check passes.
FAIL otherwise, "ties" or "trails" by (B)'s player-clustered interval; UNRESOLVED besides when
(D) fails.

**Planted check (D), on the real design.** In every fold, stage Q (Gaussian) and stage R
(binomial) are refitted with the outcome replaced by the base prediction plus planted org
effects (N(0, (0.25 s)^2) for Q, s the residual SD of the base on the stage's training rows;
N(0, 0.30^2) on the logit scale for R, the outcome drawn Bernoulli) plus noise (Q: N(0, s^2)),
seed 20261044. PASS when the correlation of the estimated org effects with the planted ones is
at least 0.70 in every fold for both stages.

**Reported, never adjudicated.** W(GLMM) - W(X3) and - W(X3-ridge), by side and per frame; the
random-effect SDs per fold and stage; the number of fold-stages that fell back.

## 6. Outputs

- `tools/rbridge.py`, `tools/r/*.R`, `tools/r_bakeoff_lab.py` (one lab, three items, each with
  `--dry-run` and `--read`), `test_rbridge.py`, `test_r_bakeoff.py`.
- Artifacts (off the webroot, role development, adjudicating nothing):
  `data/_labs/r_bakeoff/aging_gam.json`, `data/_labs/r_bakeoff/xm_years_surv.json`,
  `data/_labs/r_bakeoff/efv_glmm.json`.
- `docs/r/RESULTS.md`: the numbers and verdicts in plain language. A PASS becomes an owner flip
  question there (the fit runs in R, its coefficients ship as JSON, Python reads them). A FAIL
  stops the item.
- No registry row, glossary entry or served file changes in this task.

## 7. Defaults applied by this registration (named for the orchestrator)

- (a): the DEV label seasons 2008 to 2011 as the frame; the GAM models the year-over-year change
  with no term in v(t) (the incumbent's structure), so its gain can only come from the curve's
  shape and the player effect; Bonferroni over the two sides.
- (b): fa_market's years stage is the incumbent (XM_1's read stopped and selected it on
  development); MLB deals only (the xM$ censored minor-league floors are not years); the
  generalized gamma with a lognormal fallback.
- (c): X3's ridge staged model as the fixed part (X3 itself mixes in LightGBM, which takes no
  offset GLMM on top cleanly); side-specific groups; entry class from the acquisition record.

## 7a. Amendment A-1 (2026-10-22, before any read): item (c)'s group sources

**What was found.** Building item (c), a one-fold smoke (fold lv_dev 2017: the X3-ridge parity,
max difference 3.5e-13, and the R timing; no test row scored, no statistic computed) printed the
random-effect SDs of the stage R training fit: 2.34 on the logit scale for org. That size sent
the writer to a coverage audit of the registered group sources, by instance kind and with no
label: the board records behind `efv_dataset.asof_records()` (and the source-backtest universe,
checked as an alternative) hold only debuted players and players still on a board, so 2,743 of
5,962 LV instances and 1,449 of 2,887 MTX instances have no record at all, against 0 of 1,025
PIN instances (debut cohorts, all debuted). The universe's acquisition record has the same
coverage. A missing org or entry class there encodes "never debuted and not active", which is
the reach outcome itself. The registered sources leak the label; read as registered, item (c)
could pass on the leak.

**What changes (section 5 only).** Both groups are read through the instance's INPUT-side MLBAM
id (the list frame row's outcome-blind id for LV, the matrix row's id for MTX and PIN: the ids
X3's own inputs read through), from books that cover every player whatever his outcome:
- org: the parent organization (`efv_x2_revealed.team_info`) of the destination club of the
  player's latest league transaction dated strictly before the read
  (`efv_x2_revealed.TxBook`, the X2 development books loaded through 2024), else UNK;
- entry_class: `draft|Y` for the latest draft year in `.cache/draft_history` before the read (a
  draft year equal to the read year counts only for a read in August or later), else `milb|Y`
  for the player's first MiLB season before the read year (`MilbBook.first_season`), else UNK.
- lvl_season, the statistic, the comparators, the pass rule, the seeds and the planted check
  are unchanged.

Coverage of the amended sources, by kind and with no label: org UNK on 258 of 5,962 LV, 1,016
of 2,887 MTX (979 of them have no input id, the same rows whose X3 inputs are missing) and 2 of
1,025 PIN instances; entry class UNK on 253, 1,032 and 5. The latest transaction any instance
reads is dated 2023-04-26. LIVE instances are never trained on or scored here (UNK).

Nothing of items (a) and (b) changed, and no number of any item's statistic existed when this
amendment was written.

## 8. Results

(Appended by the reads. Nothing below this line exists at registration.)
