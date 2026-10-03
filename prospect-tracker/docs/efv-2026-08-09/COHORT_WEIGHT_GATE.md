# COHORT WEIGHT GATE (Lane C-A1, 2026-08-09): is "which source is best for THIS kind of prospect" an answerable question?

**STATUS OF THIS FILE.** Sections 0 through 7 are the PRE-REGISTRATION. They were written
in full, including every PASS clause, every FAIL clause and every stop clause, BEFORE
`source_cohort_accuracy.py` existed and therefore before any number the module reports could
be known. Section 8 is a placeholder filled in after the run. Nothing in sections 0 to 7 is
edited afterwards.

**ZERO WEIGHTS SHIP FROM THIS LANE.** `data/source_weights.json` and
`data/draft_source_weights.json` are not touched. `consensus.py` is not touched. The
deliverable is a MEASUREMENT of whether a cohort-conditioned weight could ever be justified,
published with its confidence intervals, plus the artifact that says which cells are
unanswerable. A gate that fails is a result, not a non-delivery.

---

## 0. The owner question, restated as an estimand

The question is "which prospect source is most accurate for each position, for pitchers
versus hitters, for draft versus international, for each archetype".

Made precise: for a partition cell `c`, let

    d_rho(c) = rho_fangraphs(c) - rho_mlb_pipeline(c)

where `rho_s(c)` is the Spearman rank correlation between source `s`'s preseason published
FV and realized cumulative bWAR, computed on the rows of cell `c` in the COMMON set (both
sources graded the player). Negative `d_rho` means MLB Pipeline orders that cell better.

The owner question is answered for cell `c` only if `d_rho(c)` is distinguishable from zero
at the power the data affords. It is NOT answered by the sign of a point estimate.

## 1. Basis, fixed before the run

- Universe: `source_backtest._load_universe`, i.e. `data/timeseries.json` plus
  `data/debuts.json`. No new ingest.
- Resolved preseason window: `source_backtest._resolved_years`, `MIN_LAG_YEARS = 3`,
  `CANDIDATE_YEARS` filtered to years present. On the 2026-08-09 export that is 2017 to 2023.
- Grades: `source_backtest._rater_grades_for_year` unmodified. Preseason window Jan 1 to
  May 1, max across in-window points, consensus taken from the latest in-window point.
- Common set: a player enters a base year only when FanGraphs, MLB Pipeline and the PROSPX
  consensus all graded him that preseason (the `all(r in grades for r in raters)` rule).
- DEDUP: ONE ROW PER PLAYER, the latest PRE-DEBUT read, byte-identical in rule to
  `source_backtest.py:952-967`. The pooled common set carries one row per base year, which
  weights stable prospects up to 2.4x in the international bat cell and has already flipped
  one head-to-head AUC cell (OBS-1, 2026-07-24e). Every cell in this lane is a per-player cell.
- Outcome: `source_backtest._outcome`, cumulative bWAR censored at run date, undebuted = 0.

REPRODUCTION REQUIREMENT. Where this lane and `data/source_backtest.json` overlap, the
numbers must be IDENTICAL, not merely close. The per-source `spearman` in
`accuracy.by_archetype` is the overlap, and the test asserts equality to 4 decimals on all
six archetypes and both sources. If it does not reproduce, this lane is BLOCKED and reports
that instead of a result.

## 2. Partitions, fixed before the run

Six partitions. Every cell reports `n`, per-source rho, consensus rho, `d_rho`, `d_rho_ci`,
`mde95`, `answerable`, `winner`, and a per-rater `basis` field.

1. `by_side`: bat vs arm, from `source_backtest._PITCH_POS` on the first position token.
2. `by_acquisition`: draft-HS, draft-college, international. Same derivation as
   `source_backtest._archetype`, which splits HS from college on age at draft <= 19.
3. `by_archetype`: the six `_ARCH_ORDER` cells. `ARCH_MIN_N = 40`.
4. `by_position_group`: C, IF, OF, SP, RP, from the position token. Reported with `n` and
   scored only at n >= 40, the same floor `ARCH_MIN_N` sets for archetypes.
5. `by_fv_tier`: `source_backtest.FV_TIERS` on the CONSENSUS FV.
6. `by_age_at_grading`: base year minus birth year, bucketed 18-, 19-20, 21-22, 23-24, 25+.

STATED LIMITATION, pre-registered because it will be tempting to paper over after the run.
LEVEL AT GRADING DOES NOT EXIST on this data. `snapshots` carries no level column,
`statlines` holds only season 2026, and `timeseries` `current_level` is a TODAY value that
would leak the player's subsequent development into a supposedly preseason cut. There is no
level-at-grading field to be recovered without a new ingest. AGE AT GRADING is the
substitute and the artifact says so in the block. A level cut will NOT be invented from
`current_level`, and if it appears in a later revision of this artifact it is a defect.

STATED LIMITATION 2, also pre-registered. `by_fv_tier` bins on the CONSENSUS, which is a
function of BOTH graders. Conditioning on a function of both predictors is range
restriction: within a tier the two grades are nearly equal by construction and every
within-tier rho collapses toward zero. The block is emitted WITH a
`range_restriction_warning` field carrying that sentence and the observed within-tier rho
range. It is not read as evidence about tier-specific accuracy.

## 3. Uncertainty, fixed before the run

- PLAYER bootstrap, B = 2000, seed 20260809, resampling players with replacement and
  recomputing `d_rho` per draw within the cell.
- `d_rho_ci` = the 2.5 and 97.5 percentiles of the bootstrap `d_rho` distribution.
- `mde95 = 1.96 * sd(bootstrap d_rho)`.
- `answerable = abs(d_rho) >= mde95`.

The test asserts the PROPERTY, not the values: `answerable` is False on every cell where
`abs(d_rho) < mde95`. A future data vintage may move any number and must not move the rule.

Bootstrap draws are generated from `numpy.random.default_rng(20260809)` with a fixed cell
iteration order taken from an explicit tuple, never from a set and never from `hash()`.

## 4. Multiplicity, fixed before the run

Roughly 40 cells are tested across six partitions. At alpha 0.05 that is about 2 false
positives by construction, so a list of "significant" cells is not a result on its own.

1. FAMILY-WISE CORRECTION INSIDE EACH PARTITION. Holm-Bonferroni on the per-cell two-sided
   bootstrap p, family = the cells of that partition. Report `survives_holm` per cell and
   the surviving list per partition. Cells that survive are reported WITH the note that
   partitions overlap: HS arms, draft-HS and the young age buckets are largely the same
   players, so three survivors is not three independent findings.
2. THE CORRECT FAMILY-LEVEL TEST is heterogeneity, not a survivor count. Cochran Q over the
   six archetype `d_rho` values with inverse-bootstrap-variance weights, referenced to
   chi-square on 5 df. PASS for "cohort conditioning has something to condition on" requires
   Q p < 0.05.
3. PERMUTATION on the archetype LABELS, shuffling the label across rows and recomputing Q,
   2000 draws, seed 20260809. This is the assumption-free version of leg 2 and is binding
   where the two disagree.
4. `tau2` (DerSimonian-Laird) and `I2` reported alongside. `I2` under 50 percent is
   consistent with one common `d_rho` plus sampling noise.
5. BASE-YEAR STABILITY. `d_rho` recomputed per base year 2017 to 2023 on the same two
   sources. Report the sign per year and the count of sign flips across adjacent vintages.
   A weight fitted on a quantity whose SIGN is not stable across adjacent vintages is
   fitting noise, and this leg alone is disqualifying regardless of anything above.

## 5. The cohort A/B, fixed before the run

Six pre-registered variants of a cohort-conditioned weight, no others, no post-hoc seventh:

| variant | description |
|---|---|
| `archetype_shrunk` | per-archetype accuracy weights, shipped shrink k = 150, shipped clamp (0.6, 1.5) |
| `archetype_eb` | archetype plus empirical-Bayes partial pooling toward the global weight |
| `archetype_recentre` | archetype plus cross-cohort recentering so cohort means do not drift apart |
| `archetype_eb_recentre` | archetype plus EB plus recentering |
| `side_shrunk` | bat vs arm only, shipped shrink |
| `side_recentre` | bat vs arm plus recentering |

VINTAGE RULE, identical to `source_backtest.run_consensus_weight_ab`: weights usable for
board year Y see only base years <= Y - `MIN_LAG_YEARS`. A cohort weight that peeks at the
cohort it scores is not an A/B.

SHIP GATE, the INCUMBENT constants, not new ones: `d_rho >= +0.0068` AND `d_auc >= +0.0052`,
both against the equal-weight blend, both on the pooled A/B rows. These are
`source_backtest.run_consensus_weight_ab`'s `_SHIP_MIN_RHO_GAIN` and `_SHIP_MIN_AUC_GAIN`.
This lane does not get to invent a friendlier floor for its own arm.

CONTROL, pre-registered because a positive point estimate on a fitted weight is worthless
without one: permutation of the COHORT LABELS across rows, 200 draws, REFITTING the weights
per draw, seed 20260809. Report the null mean, sd, p95 and the observed arm's p against it.
If random cohort labels do as well as real ones, the arm is measuring the fitting procedure,
not the cohort.

SHRINK SENSITIVITY: k in {0, 25, 50, 150, 400, 1000} on the best arm, both estimands. A
result that is MONOTONE in k, improving as k grows toward equal weight, is the signature of
zero signal: the best amount of the weight is none of it.

ALPHA PARAMETERISATION, recorded because it is nowhere in the repo today. For a two-source
blend, only the ratio matters: `alpha = w_fg / (w_fg + w_mp)`. The shipped clamp (0.6, 1.5)
therefore maps to `alpha` in [0.6/(0.6+1.5), 1.5/(1.5+0.6)] = [0.2857, 0.7143]. The artifact
records that mapping.

## 6. The oracle ceiling, fixed before the run

The A/B can fail for two different reasons and they have different consequences:

- the weight is estimated badly (fixable with more data), or
- no weight exists to estimate (not fixable).

Separating them requires an ORACLE: fit `alpha` on the SAME rows it is scored on, maximising
the objective directly. That is maximal cheating and therefore an upper bound. Report:

- `global_oracle_gain`: best single alpha, scored in-sample, minus the equal blend.
- `cohort_oracle_pooled`: every cohort's own oracle alpha applied, scored POOLED.
- `corr_fg_mp` (Pearson) and the two grade sds.

PRE-REGISTERED READING. If `global_oracle_gain` is BELOW the +0.0068 ship gate, then no
weight, however well estimated, can pass the gate on this data, and every A/B arm below it is
explained without appeal to estimation error. If `cohort_oracle_pooled` is NEGATIVE while
each cohort's within-cohort oracle is non-negative, that is Simpson-style incomparability:
consensus FV is a globally comparable number and cohort-specific mixing breaks the
comparability faster than it buys within-cohort ordering. Two near-collinear predictors of
similar scale have a nearly flat response surface in the mixing weight, so a flat oracle is
GEOMETRY, and more base years cannot fix geometry.

## 7. Coverage selection, fixed before the run

The common set is an INTERSECTION. Rows only one source graded are discarded before any rho
is computed. Report:

- `rows_own`, `rows_common`, `rho_own`, `rho_common`, `delta` per source.
- the discarded counts, rows and distinct players, per source.
- the covariate imbalance between kept and cut rows: mean consensus FV and debut rate.

DO NOT BUILD A SELECTION MODEL. The cut rows carry ZERO paired contrast: no second source
graded them, so they contain no information about `d_rho` under any model that does not
assume the missingness is ignorable. An 8-FV mean-grade imbalance between kept and cut rows
makes that assumption not credible. Naming the exclusion and publishing its size IS the
honest form of recovering this evidence. A selection-model arm appearing in a later revision
is a defect.

## 8. RESULTS

Run 2026-08-09, `python source_cohort_accuracy.py`, artifact
`data/source_cohort_accuracy.json` (71,075 bytes). Basis: 4,284 pooled common rows,
1,517 deduped players, window 2017 to 2023. A second run reproduces the artifact
byte-for-byte apart from `generated_at`.

### 8.0 Reproduction, and a stale served artifact

LEG 1, BINDING: `source_backtest._archetype_accuracy` recomputed unmodified on this lane's
deduped rows matches every cell and every source to the last decimal. 0 diffs.

LEG 2, INFORMATIONAL: the SERVED `data/source_backtest.json` does NOT match. Its HS versus
college split differs: served `hs_bat` n 294, `hs_arm` 292, `college_bat` 178,
`college_arm` 265 against 240 / 217 / 233 / 340 here. The international cells match (195,
290 against 291). The cause is file times, not code: `source_backtest.json` was written
13:56, `debuts.json` 14:07, `timeseries.json` 14:24, so the served archetype table was built
on a universe that no longer exists. Same failure mode as
docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md section 6.0.1, and handled the same way: the
live recompute is binding, the served comparison is a staleness flag. It is emitted as
`reproduction.served_artifact_stale = true`.

### 8.1 Accuracy: 4 of 25 scored cells clear their own floor

Pooled, n 1,517: FanGraphs 0.2748, MLB Pipeline 0.3040, consensus 0.3037. d_rho -0.02920,
CI95 [-0.06624, +0.00380], MDE95 0.03571. **THE GLOBAL HEAD-TO-HEAD IS ITSELF NOT
RESOLVABLE.**

| cell | n | d_rho | CI95 | MDE95 | verdict |
|---|---|---|---|---|---|
| bat | 764 | -0.0290 | [-0.0804, +0.0188] | 0.0490 | not resolvable |
| arm | 753 | -0.0267 | [-0.0855, +0.0289] | 0.0568 | not resolvable |
| draft-HS | 457 | -0.0709 | [-0.1266, -0.0144] | 0.0571 | Pipeline |
| draft-college | 573 | -0.0327 | [-0.1007, +0.0343] | 0.0668 | not resolvable |
| international | 485 | +0.0240 | [-0.0389, +0.0904] | 0.0643 | not resolvable |
| hs_bat | 240 | -0.0356 | [-0.1093, +0.0350] | 0.0726 | not resolvable |
| hs_arm | 217 | -0.1195 | [-0.2187, -0.0202] | 0.0989 | Pipeline |
| college_bat | 233 | -0.0456 | [-0.1556, +0.0627] | 0.1082 | not resolvable |
| college_arm | 340 | -0.0060 | [-0.0930, +0.0839] | 0.0883 | not resolvable |
| intl_bat | 290 | +0.0069 | [-0.0707, +0.0800] | 0.0757 | not resolvable |
| intl_arm | 195 | +0.0607 | [-0.0747, +0.1893] | 0.1310 | not resolvable |
| C | 84 | -0.0146 | [-0.1483, +0.1100] | 0.1284 | not resolvable |
| IF | 371 | -0.0285 | [-0.0916, +0.0361] | 0.0644 | not resolvable |
| OF | 292 | -0.0278 | [-0.1148, +0.0596] | 0.0862 | not resolvable |
| RP | 74 | +0.1567 | [+0.0687, +0.2546] | 0.0962 | FanGraphs |
| P_unspecified | 629 | -0.0433 | [-0.1022, +0.0164] | 0.0610 | not resolvable |
| age 23-24 | 605 | -0.0979 | [-0.1544, -0.0399] | 0.0578 | Pipeline |

Four cells clear their floor: draft-HS, hs_arm, RP, age 23-24. 1.25 are expected by
construction at alpha 0.05 over 25 scored cells.

TWO CAVEATS ON THE RP CELL, both found in the run and not anticipated in sections 0 to 7.
First, SP / RP / SIRP / MIRP are FanGraphs-authored ROLE designations, so the pitcher cut of
`by_position_group` conditions on a judgment made by one of the two graders being compared.
Second, the RP rows are 27.0 percent debuted, so the tag is projected role, not realized
role. Emitted as `accuracy.by_position_group_selection_caveat`. The SP cell (n 50) cannot be
scored at all: every one of its deduped rows carries WAR 0, so no rank correlation exists on
either source. It is reported as a degenerate cell, not silently dropped.

FV TIER, as pre-registered in section 2: emitted WITH the range-restriction warning. Within
tier the per-source rhos run -0.1029 to +0.2679 against pooled 0.2748 / 0.3040, and outside
the `<45` bucket they sit between -0.04 and +0.08. MDE95 blows out to 0.20, 0.27 and 0.53 on
the three thin tiers, so nothing in this partition can be resolved. The `60+` tier (n 22) is
not scored at all. Not read as evidence about tier-specific accuracy.

LEVEL AT GRADING: not available, age at grading substituted, recorded in
`accuracy.level_at_grading`.

2026-10-02 (EFV3_D5, a dated note to these results, not to the pre-registration): level at
grading now exists through the outcome-blind MiLB block of the list-vintage frame
(`efv_vintage_frame.frame_row`, whose `milb` block carries the V-1 `milb_level` from
`efv_dataset._milb_features` with cutoff V-01-01), so the artifact's
`level_at_grading.available: false` describes the 2026-08 data this lane read, not today's;
this lane's partitions are unchanged, and the level cut is registered in
`docs/efv-v2/EFV_V2_GATE.md` s8.1.

### 8.2 Multiplicity: no survivor survives the family-level test

Holm inside each partition leaves 2 of the 4: `by_position_group:RP` (p 0.001) and
`by_age_at_grading:23-24` (p 0.001). `hs_arm` (p 0.017, family m 6) and `draft_hs`
(p 0.019, family m 3) do NOT survive. The two survivors overlap heavily with each other and
with the raw flags, so this is not two independent findings.

FAMILY-LEVEL TEST, which is the binding one: Cochran Q 6.2307 on 5 df, chi2 p 0.2844;
label permutation p 0.2529 over 2,000 draws; tau 0.0232; I2 19.8 percent. The six archetype
d_rho values are consistent with ONE common difference plus sampling noise. There is nothing
for a cohort weight to condition on.

BASE-YEAR STABILITY: d_rho by vintage is -0.1149, -0.0549, -0.0516, -0.0325, -0.0095,
-0.0755, +0.0456 for 2017 through 2023. ONE sign flip across seven adjacent vintages, at
2023, where the quantity moves +0.121 in a single cycle. The pre-registered reading holds:
the most recent vintage disagrees in sign with all six before it.

### 8.3 The cohort A/B: six arms, six losses

Pooled n 2,907 over board years 2020 to 2023, weights from base years <= Y - 3.

| arm | d_rho | d_auc | ship |
|---|---|---|---|
| archetype_shrunk (k 150) | -0.00592 | -0.00030 | false |
| archetype_eb | -0.00127 | +0.00245 | false |
| archetype_recentre | -0.00460 | +0.00040 | false |
| archetype_eb_recentre | -0.00057 | -0.00087 | false |
| side_shrunk | -0.00081 | +0.00217 | false |
| side_recentre | -0.00231 | +0.00116 | false |

Every arm is NEGATIVE on d_rho against a +0.0068 gate. Best arm archetype_eb_recentre, as
pre-registered.

CONTROL, 200 draws, cohort labels permuted and weights refit per draw: null mean -0.00034,
sd 0.00167, p95 +0.00267. Observed -0.00057 gives p 0.5522. **Random cohort labels do
better than real ones on the majority of draws.**

SHRINK SENSITIVITY on the best arm: d_rho -0.00101, -0.00061, -0.00069, -0.00057, -0.00013,
-0.00010 for k 0, 25, 50, 150, 400, 1000 (rank correlation with k +0.943); d_auc -0.00040,
-0.00027, -0.00048, -0.00087, -0.00115, -0.00121 (rank correlation -0.943). d_rho improves
monotonically toward equal weight, which is the pre-registered signature of zero signal.
d_auc trends the other way. The whole grid spans about 1e-3 against a 0.0068 gate, so
neither trend is a result on its own; the two together are the plainest possible statement
that there is nothing here.

ALPHA MAPPING, recorded because it is nowhere else in the repo: the shipped clamp
(0.6, 1.5) is alpha in [0.2857, 0.7143].

### 8.4 Oracle ceiling: estimation error is not the binding constraint

Deduped common set, n 1,517: equal-weight rho 0.3035, best single alpha 0.205 giving rho
0.3048. **GLOBAL ORACLE GAIN +0.00130, against a +0.0068 gate.** On the A/B pooled rows
(n 2,907) the gain is +0.00023. Fitting the weight on the rows it is scored on, which is
maximal cheating, does not reach the floor. Every A/B arm below it is therefore explained
without appeal to estimation error.

COHORT ORACLE, deduped: the n-weighted within-cohort oracle gain is +0.01132, and scoring
the same six alphas POOLED yields +0.00137. **12.1 percent of the within-cohort gain
survives pooling.** That is the comparability mechanism measured directly: consensus FV is a
globally comparable number and cohort-specific mixing destroys 88 percent of what it buys.
On the A/B pooled rows the cohort oracle reaches +0.00775, just over the gate, and that
headroom IS the overfit: the honest A/B on the same rows is -0.00057.

GEOMETRY: Pearson corr(FG, MP) 0.7498, sds 6.3626 and 6.0956. Two near-collinear predictors
of similar scale give a nearly flat response surface in the mixing weight. More base years
cannot change a flat surface.

### 8.5 Coverage selection: the exclusion is named, not modelled

Strict intersection keeps 4,284 of 5,418 player-year slots (79.07 percent) and 75.10 percent
of players. Discarded: 719 FanGraphs-only rows (506 players) and 415 Pipeline-only rows
(356 players).

| source | rows own | rows common | rho own | rho common | delta |
|---|---|---|---|---|---|
| fangraphs | 5,003 | 4,284 | 0.2208 | 0.2476 | -0.02676 |
| mlb_pipeline | 4,699 | 4,284 | 0.2712 | 0.2810 | -0.00981 |

Scoring each source on its OWN rows LOWERS its rho, for both sources. The cut rows are worse
prospects: FanGraphs-only cut rows mean FV 37.72 and debut rate 0.736 against a pooled kept
mean of 45.61 and 0.894. That is a 7.9 FV covariate imbalance. Pipeline-only cut rows are
different again (mean FV 44.59, debut 0.834), which is itself evidence the two exclusions
are not the same mechanism.

NO SELECTION MODEL WAS BUILT, as pre-registered. The cut rows carry zero paired contrast.

### 8.6 Verdict

The owner question is UNANSWERABLE in most cells, and in the cells where it is answerable
the answer does not generalise: the family-level heterogeneity test does not reject a single
common difference, the sign is not stable across the most recent vintage, every
cohort-conditioned weight loses, random cohort labels beat real ones, and the in-sample
ceiling sits below the ship gate. ZERO WEIGHTS SHIP. `data/source_weights.json` and
`data/draft_source_weights.json` are untouched and `consensus.py` is unchanged.
