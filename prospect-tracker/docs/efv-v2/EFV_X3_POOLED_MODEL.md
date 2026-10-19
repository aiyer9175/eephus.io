# eFV X3: one pooled model in place of the cell drivers (EFV_X3_POOLED_MODEL): registration

Registration status: REGISTERED 2026-10-19

Registered 2026-10-19, committed ALONE, before the module `efv_x3_pooled.py` exists and before
any number of this task is computed. Owner decisions (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`):
EW3-12 (2026-10-15, the expert eFV program, item 3: "one pooled hierarchical or boosted model
replacing the cell drivers"), EW3-13 (train through the 2026 season; the 2026 holdout is spent),
EW3-21 (the eFV driver audit, scratchpad `efv_audit/AUDIT.md`: the timing term has no value
beyond consensus on development, the hitter skill weight was too large), EW3-26 (the tool arm
comes from EFV_ETOOLS_REWEIGHT), EW3-35 (the upside and volatility hand-off, scored on the full
outcome distribution), EW3-41 (the pitch rates enter as penalized candidates) and EW3-42
(2026-10-19: pitchers and relievers feel inflated; add censoring-aware labels, a survivorship
correction, consensus as a noisy measurement, covariate-shift weighting, the pitcher role path,
conformal intervals and pitcher-by-role reporting). The run appends section 13 (the numbers) and
section 14 (the verdict). The plain-language summary for the owner is
`docs/efv-v2/EFV_X3_POOLED_MODEL_RESULTS.md`. No em-dashes.

Rules that bind every part: development frames only for every number that selects anything;
no reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and later) is built,
scored or used to select; `backtest.run_backtest` is never called; no projections retrain; the
fWAR label epoch's runbook is not touched; nothing is grouped, counted, averaged or stratified
by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`, binding: the only groups are frame,
side, year, fold, hitter position group, pitcher usage role and outcome classes cut on WAR);
no fetch outside `.cache/EFV_X3_POOLED_MODEL/` (none is planned: every input is already
cached); nothing served moves unless the registered rule of section 9 passes AND the owner
answers the flip question.

## 1. What is known before this registration

- The served eFV is eFV v5 COMBINED as re-fit (variant RT, `efv5_refit.EFV_V5_REFIT_ON`,
  `docs/efv-v2/EFV_V5_REFIT.md`): hitters w_skill 0.297 and w_time 0, pitchers 1.0 and 0. Its
  out-of-fold development order reads within (side, year) Spearman 0.1683 (lv_dev) and 0.3937
  (vm_dev) against consensus 0.1792 and 0.3814 (`data/_labs/efv5/efv5_refit_fit.json`). Every
  pooled read so far ties consensus: v5 COMBINED pooled over the development frames -0.0103
  (lower bound -0.0335, mde95 0.0231; `docs/efv-v2/EFV_BEAT_POOLED_POWER.md`), the 2026 holdout
  +0.0121 (lower bound -0.0073). The binding constraint is the label pool (39 feature arms, zero
  survivors; `docs/efv-v2/MODEL_CLASS_SCREEN.md`: no estimator change over the same drivers
  beat V2).
- The hand-offs to this task, each read one feature at a time and none flagged: EFV_X1 (23
  translated, reliability-weighted rates, `docs/efv-v2/EFV_X1_MLE_TRANSLATION.md` s11);
  EFV_X2 (15 club-decision columns; options CARRY, Rule 5 selection and trades LEAN, the joint
  arm loses on both frames, `docs/efv-v2/EFV_X2_REVEALED_PREFERENCE_RESULTS.md`); the eTools
  (eHIT, ePOW, eSEL, eBAT, eFB, eCMD, `docs/tools-2026-10/ETOOLS_RESULTS.md` "What feeds
  EFV_X3"; amendment 1 found P/PA PAR in eHIT and the swinging-strike rate in eFB carry no added
  effect); EFV_ETOOLS_REWEIGHT (the eTools in the tool slots do not beat the served re-fit,
  pooled -0.0045; its re-estimated tool weights hit 0, game power 0.009, fastball 0.066,
  command 0.056); EFV_UPSIDE_VOLATILITY_DRIVERS (pass list NONE); EFV_X4 (no pitch tracking
  below Triple-A outside the Florida State League); EFV_X5 (995 pre-2011 list rows, a lab
  artifact, no PROSPX consensus before 2011).
- The development pool is small: under EFV_BEAT_POOLED_POWER's estimand the one-sided mde95 of
  a rater minus consensus is about 0.023. An edge of +0.005 to +0.01 cannot be resolved here.
  The modal outcome of this read is a tie.

Nothing about this task's outcome has been computed. No feature coverage has been counted.

## 2. Rows

### 2.1 Instances (one row of features per read)

Every row X3 reads is one INSTANCE, a (player, read) pair, with its features read as of the
read's own date and never later:

- LV: a list-vintage row (`efv_vintage_frame`, list vintages 2011 to 2019, the re-fit's pool
  `efv5_refit.lv_pool`), read at its preseason window start V-01-01 through its outcome-blind
  MLBAM id.
- MTX: a v1 matrix training row (`efv_v2_model.matrix_training_rows`), read at the matrix row's
  own as-of (its decision point) through the matrix id.
- PIN: a vm_dev test row, read at its pinned preseason as-of (`efv_v2_model.pinned_inputs`),
  the read the served vm_dev order reads.
- LIVE: a live board row (`efv_dataset.live_matrix_path`), read today (the 2026 season, read
  year 2027), used ONLY by the covariate-shift classifier (section 6.4) and, after a pass, the
  dark build.

The features of an instance are the same in every fold except the eTools (section 3.3), which
are rebuilt per fold by the re-weight's fold design.

### 2.2 The scored frames

- lv_dev: list vintages 2017, 2018 and 2019, the rows the served re-fit's development read
  scores (2,862 rows), label W3.
- vm_dev: debut cohorts 2017 to 2023 at frame version vm2 (830 rows), label career WAR to date.

These are exactly the rows of `tools/efv_beat_tilted_labels.build` (the served re-fit's
out-of-fold order rebuilt in memory with its parity guards), which this task reuses for the
comparator scores.

### 2.3 The fold design (forward-chained, the served comparator's)

The outer folds are the comparator's: one per (frame, test year): lv_dev V in 2017 to 2019,
vm_dev Y in 2017 to 2023. Every fold fits both sides jointly (section 5). A fold's training
instances, every player of the fold's test rows excluded:

- the REACH stage (section 4.1): LV instances of vintages up to min(2019, Y - 1);
- the CONDITIONAL stages and the direct arms (sections 4.2, 4.4): LV instances of vintages up to
  min(2019, Y - 1) and MTX instances of decision years before Y.

So no training instance is read at or after its fold's test year, as in the served re-fit's
FC design. Labels of training instances are read as resolved today (through 2026), as every
development fit of this program reads them. The live-timing twins of the re-fit (its arm A4) are
not used: the live board's timing regime is handled by the covariate-shift weights (6.4).

Each player's instances inside one stage's training set share a total weight of 1 (weight
1 / count), before the censoring, selection and covariate-shift weights below.

### 2.4 What is not used

- R-LV (list vintages 2020 and 2021) and R-VM (debut cohorts 2025 and later) are never scored.
  Under EW3-13 the 2025 and 2026 debut classes enter ONLY the production fit, with
  `efv_vintage_frame.EFV_TRAIN_THROUGH_2026` on (the fold matrices of
  `efv_2026_fold.py --build`); under the forward-chained design no development fold reads them.
  The production fit is built only after a pass (section 10).
- EFV_X5's pre-2011 list rows: not used. The model's anchor is PROSPX consensus (section 5),
  which does not exist before 2011; a row with no consensus cannot be anchored.
- The served cell drivers (the v5 COMBINED candidate columns, the group and tool cells, the
  population translation column) are not inputs: X3 replaces them.
- The tracking-era head's inputs (Savant Triple-A from 2022, Florida State League from 2021)
  cover no lv_dev list vintage and no training instance before 2021; they are not built.

## 3. The features (15 to 25 per side, fixed here)

### 3.1 The rule

The feature list of each side is fixed below, in priority order; no list is chosen from data.
One outcome-blind rule may shorten it inside a fold: a feature present (not missing) on fewer
than 20 percent of the fold's training instances of its side is dropped in that fold (its
coverage is counted on features only). The run reports, per fold and side, the features kept.
Missing indicators and the anchor columns (section 5) are not counted as features. Every
continuous feature is z-scored within (side, instance kind, year) on the instances that carry
it; a missing value is 0 with its missing indicator 1.

### 3.2 Hitters (24)

1. eHIT, the hit eTool on the reduced sub-driver set (k_rw, babip_rw): REPLACES the consensus
   hit grade (amendment 1 A2: P/PA PAR carries no added effect, dropped).
2. ePOW, the game power eTool (iso_rw, bb_fb): REPLACES the consensus game power grade.
3. eSEL, the pitch selection eTool (pbp_swing).
4. eBAT, the bat control eTool (pbp_contact).
5. Consensus run grade (`tool_speed`).
6. Consensus field grade (`tool_field`).
7. Consensus raw power grade (`tool_raw_pwr`, the row's prior features).
8. X1 `obp_rw`.
9. X1 `woba_rw`.
10. X1 `woba_yoy`.
11. X1 `age_rel_level`.
12. Level reached (`level_rank`).
13. Age at the read (`age`).
14. Draft route: overall pick (`pick_overall`, missing for an international signing).
15. International signing (`is_ifa`).
16. College draftee (`is_college`).
17. X2 `x2_options`.
18. X2 `x2_trades`.
19. X2 `x2_r5_selected`.
20. P/PA, season-normalized and reliability-shrunk (`ppa_raw`, the eTools construction).
21. P/PA PAR, level-relative and reliability-shrunk (`ppa_par`).
22. Consensus reliability lambda (section 6.3).
23. Grader disagreement (`fv_stddev`).
24. Position premium (`pos_prem`).

Dropped from X1 so a stat line is not counted twice (owner, eTools gate 7): `k_rw`, `bb_rw`,
`iso_rw`, `babip_rw` (the eTools carry them), and every other X1 hitter column not listed.

### 3.3 Pitchers (25)

1. eFB, the fastball eTool on the reduced sub-driver set (k_rw, pbf_raw): REPLACES the
   consensus fastball grade (amendment 1 A2: the swinging-strike rate carries no added effect,
   dropped).
2. eCMD, the command eTool (bb_rw, pbp_fstrike, pbf_par): REPLACES the consensus command grade.
3. Best consensus secondary pitch grade (the largest of `tool_sl`, `tool_cb`, `tool_ch`).
4. Arsenal depth (`arsenal_depth`).
5. X1 `hr9_rw`.
6. X1 `gb_rw`.
7. X1 `age_rel_level`.
8. Level reached (`level_rank`).
9. Age at the read (`age`).
10. Overall pick (`pick_overall`).
11. College draftee (`is_college`).
12. X2 `x2_options`.
13. X2 `x2_trades`.
14. X2 `x2_r5_selected`.
15. P/BF, season-normalized, shrunk (`pbf_raw`).
16. P/BF PAR, level-and-role-relative, shrunk (`pbf_par`).
17. P/IP, season-normalized, shrunk (`pip_raw`).
18. P/IP PAR, level-and-role-relative, shrunk (`pip_par`).
19. Starts share of appearances (GS / G at the read, section 6.5).
20. Innings per appearance (IP / G at the read).
21. Workload: log(1 + innings) in the read season.
22. P(ends a reliever) from the role sub-model (section 6.5).
23. Role interaction: P(ends a reliever) x the consensus percentile.
24. Consensus reliability lambda (section 6.3).
25. Grader disagreement (`fv_stddev`).

Dropped from X1: `k_rw`, `bb_rw` and `kbb_rw` (eFB and eCMD carry them) and the year-over-year
columns. The pitch rates 15 to 18 overlap eFB and eCMD on purpose (EW3-41: no separate gate,
the penalty decides); the run reports every pitch-rate weight (13.6).

### 3.4 The eTools arm (EW3-26, eTools gate 7, amendment 1)

The eTools are built exactly as EFV_ETOOLS_REWEIGHT builds its version E
(`efv_etools_reweight.Run.fold_values`: one cohort per board year; a training instance's fit
leaves out its own board year and the fold's test players, a test instance's fit reads the
eTools frame's board years before the fold's test year), on the eTools frame
(`efv_etools_reweight.build_bank`, the look's reproduction checked) and the row contexts
(`efv_etools_reweight.RowMeta`), with ONE change: eHIT and eFB are fitted on their reduced
sub-driver sets (3.2 item 1, 3.3 item 1), by `etools.etool_fit` on those columns. ePOW, eCMD,
eSEL and eBAT keep the look's sets. The other tools enter as consensus grades. The re-weight's
tool weights are not imported: X3's own penalty sets every weight, and the run prints the
re-weight's weights beside X3's. eRAW and eSPD enter only the sensitivity of 13.7 (in place of
items 7 and 5), never the primary fit.

### 3.5 Not carried, with the reason

- The upside and volatility markers: the hand-off pass list is NONE.
- MiLB fielding runs: one passing cell (High-A 2021 hitters on reaching MLB within three
  seasons, an arrival read); the 25-slot budget is filled by the arms the owner named.
- The tracking-era head: no coverage on the training instances (2.4).

## 4. The labels (the staged decomposition, recombined)

### 4.1 Stage R: P(reach)

REACH is R3 (a debut in V to V + 3), on LV instances only (the outcome-blind frame; the matrix
rows are read at a point aligned with the outcome, audit D1, so they never enter this stage).
Every LV instance of vintages up to 2019 has a closed R3 window.

### 4.2 Stages T and Q: playing time given reach, WAR rate given play

For every REACHED training instance (an LV instance with R3 = 1, debut year d from
`efv_labels.labels_for`; an MTX instance of kind `debuted`, d its decision year) the season
panel holds one row per season k = 0 to 5 after the debut with d + k <= 2026 (the label's
resolved-through season):

- PT_k: MLB plate appearances / 600 (hitters) or batters faced / 700 (pitchers) in season
  d + k (0 with no MLB line), from the cached StatsAPI season lines (`.cache` of EFV_X1, sport
  1), keyed by the record's MLBAM id (labels may read the outcome id; inputs never do).
- WAR_k: fWAR in season d + k (`efv_labels.war_seasons_table`, the frozen label
  `fwar@2026-10-02-0341299c20ec`).

Stage T fits E[PT_k | x, k, reach] on every panel row; stage Q fits E[WAR_k / PT_k | x, k, play]
on the panel rows with PT_k > 0, weighted by PT_k. The season index k enters both stages (class
(a): unpenalized dummies; class (b): a feature).

### 4.3 The recombination (the X3 score)

    E[L6 | x] = P(reach | x) * sum over k = 0..5 of max(0, E[PT_k | x, reach]) * E[rate_k | x, play]

This six-season WAR value is X3's score; its within (side, year) rank is X3's order.

### 4.4 The direct arms (reported, never in the rule)

- W3: ridge and boosted fits of the W3 label on LV instances (the lv_dev frame's own label).
- L6: fits of six-season WAR from the debut on every training instance with a resolved L6
  (`efv_labels.labels_for` l6 with its weight l6_weight for an LV instance; the matrix row's
  target and weight for an MTX instance), the label's own censoring rule (the observed-rate tail
  projection, weight = observed seasons / 6).

## 5. The two model classes (both registered, both fitted in every fold)

Consensus is the anchor: every stage models the outcome GIVEN consensus. The anchor columns
are unpenalized: per side, an intercept, the consensus percentile u_c (average ranks within
(side, instance kind, year)), and u_c x (lambda - mean lambda) (section 6.3); the panel stages
add unpenalized season dummies k = 0 to 5 per side.

(a) HIERARCHICAL RIDGE (partial pooling). One joint fit over both sides. Each shared feature
(everything but the eTools, the tool grades and the side-only items) carries a global slope,
a side deviation and a position-group deviation; each side-only feature a side slope and a
group deviation. Groups: hitters C, SS, CF, IF (2B, 3B), COF, 1B/DH (the listing position's
first token, `efv_upside_volatility.POS_GROUP`); pitchers the usage role at the read (STARTER,
SHORT-START, RELIEF, OTHER; 6.5). Penalties: lambda on global and side-only slopes, 4 x lambda
on every deviation (kappa = 4, fixed). Stage R is a penalized logistic (Newton), stages T and Q
penalized weighted least squares. Grid: lambda in {1, 3, 10, 30, 100}.

(b) GRADIENT BOOSTING (LightGBM 4.6, `lightgbm`), one joint fit over both sides with side and
group as categorical features, started from the anchor: the init score of every stage is the
anchor-only fit of the same stage (the class (a) fit with no feature), so the trees model the
residual given consensus. Monotone constraints where the direction is known: u_c +1; every eTool
and every consensus tool grade +1; age -1; age_rel_level -1; every other feature 0. Fixed:
num_leaves 7, learning_rate 0.05, min_data_in_leaf 40, feature_fraction 0.8, bagging_fraction
0.8 (freq 1), lambda_l2 1.0, num_threads 2, seed 20261020, deterministic. Grid: n_estimators in
{50, 100, 200}. Missing values go to LightGBM as missing.

Every stage of one configuration shares its grid point.

NESTED SELECTION (inside each outer fold, on its training instances only). The inner
validation set is the training LV instances of the latest two vintages the fold's reach stage
reads; the inner training set is every training instance read before the first of them. Each
of the 8 configurations (5 ridge, 3 boosted) is fitted on the inner training set (all three
stages) and scored by the size-weighted within (side, vintage) Spearman of its recombined
score against W3 on the inner validation set (groups of at least 20 rows). Ties go to the
larger lambda, then to fewer trees, then to ridge. The fold's:

- X3 (THE rater of the rule) is the best configuration over both classes, refitted on the
  fold's full training set;
- X3-ridge and X3-gbm (reported) are the best configuration of each class, refitted the same
  way.

## 6. The expert components (EW3-42), each with its null comparator and planted recovery

Every component is ON in X3. For each, the run reports (i) a NULL COMPARATOR on the
development pool: X3 rerun with the component replaced by a no-information version, the
pooled within delta against X3 (point estimate, player-clustered interval); and (ii) a
PLANTED RECOVERY on synthetic data with a known effect (seeded, section 13.8), with the
pass criterion fixed here. Neither enters the rule of section 9; a failed planted check is
printed beside the verdict.

### 6.1 Censoring-aware labels

The panel stages T and Q read only observed seasons (d + k <= 2026): a cohort whose six-season
window is open contributes the seasons it has played and nothing for the rest, so a recent
debut is neither dropped nor read as a bust (administrative censoring at the label's
resolved-through season, independent of the player given his features). Stage R reads R3,
closed for every training vintage.
- Null: the panel with every unobserved season counted as PT_k = 0 and WAR_k = 0.
- Planted: 4,000 synthetic players, debut years spread over 12 seasons, PT drawn with a known
  mean by season and a feature effect; the censoring-aware estimate of the six-season PT sum
  is within 5 percent of the truth and the zero-fill estimate is not.

### 6.2 Survivorship (selection into the conditional stages)

Stages T and Q see only players who reached. Control function (Heckman's two-step in its
probit form): each conditional row carries the inverse Mills ratio phi(Phi^-1(p)) / p of its
reach probability p from stage R, as one more (penalized, for class (a)) feature. An LV
instance's p is cross-fitted (five player folds of the stage R training set, seed 20261020);
an MTX instance, never in stage R's training set, is scored by the fold's stage R fit; a test
instance likewise. Identification rests on the nonlinearity of the ratio (no exclusion
restriction is claimed). Reported: the ratio's coefficient per stage and fold.
- Null: the ratio computed from p permuted within (side, year).
- Planted: synthetic selection with correlated errors (rho 0.5); the two-step slope on the
  outcome feature is closer to the truth than the uncorrected slope, in at least 90 of 100
  seeded replications.

### 6.3 Consensus as a noisy measurement (errors in variables)

Per instance, n = the number of real graders at the read (`n_sources`, at least 1) and s = their
standard deviation (`fv_stddev`). Inside each fold's training instances of a side (features
only, no label): sigma_e^2 = the mean of s^2 over instances with n >= 2; tau^2 = the variance of
the consensus grade minus the mean of sigma_e^2 / n (floored at 0.25 sigma_e^2). Per instance,
the shrunk noise sigma_i^2 = ((n - 1) s^2 + 2 sigma_e^2) / (n + 1) and the reliability
lambda_i = tau^2 / (tau^2 + sigma_i^2 / n). lambda enters as a feature (3.2 item 22, 3.3 item 24)
and as the shrinkage weight on u_c: the anchor's u_c x (lambda - mean lambda) column lets the
slope on consensus fall where the graders are few or disagree. Source accuracy weights are not
used (the reliability anchor screen measured every source's weight at 1.0 on these frames,
`docs/efv-v2/STATUS.md`, model-class screen point 3).
- Null: lambda permuted within (side, kind, year).
- Planted: synthetic consensus = truth + noise with variance falling in n; the fitted slope on
  u_c x lambda is positive with its 95 percent interval above 0.

### 6.4 Covariate-shift weighting toward the live board

Per fold and side, a penalized logistic (ridge 1.0, the features of section 3 standardized with
missing indicators, plus the raw consensus grade) separates the fold's training instances
(label 0) from the side's LIVE instances (label 1; their eTools from one fit on every eTools
board year, the production construction). Each training instance's weight is
w = p / (1 - p) x (training count / live count), clipped at 10, normalized to mean 1. If the
effective sample size (sum w)^2 / sum w^2 falls below 30 percent of the count, the weights are
tempered once to w^0.5 and renormalized. The weights multiply every stage's weights.
Diagnostics per fold and side: the classifier's AUC, ESS / n, the clip count, whether tempered,
and the three features with the largest standardized live-minus-training gaps.
- Null: uniform weights.
- Planted: synthetic training and target samples with a known density ratio; the estimated log
  weights correlate with the true ones at 0.8 or more.

### 6.5 The pitcher role path

Usage at the read (`efv_reliever_adj.usage`, the read season's affiliated lines, the season
before added under 5 appearances): GS / G, IP / G, the workload, and the usage role STARTER,
SHORT-START, RELIEF (FEW and NO-LINE are OTHER). The role sub-model: a penalized logistic
(ridge 1.0) of ENDS A RELIEVER (MLB games started under half of MLB games over seasons d to
d + 2, at least 5 MLB games) on GS / G, IP / G, the workload, arsenal depth, eCMD, eFB, the best
secondary grade and u_c, fitted per fold on the reached training pitchers; its prediction for
every pitcher instance is feature 3.3 item 22, and its product with u_c is item 23 (the role
interaction on the pitcher head; the boosted class also sees the role as the group feature).
- Null: the sub-model's prediction permuted within (year).
- Planted: synthetic pitchers whose reliever outcome follows GS / G; the sub-model's AUC on
  held-out synthetic rows is 0.8 or more.

### 6.6 Uncertainty: conformal intervals and calibration

Per outer fold, a split-conformal calibration set: the inner validation instances of section 5
scored by the inner fit of the selected configuration.
- The ORDER interval: nonconformity |u_y - u_hat| (u_y the label percentile, u_hat X3's
  percentile, both within (side, year)); q = the ceil(0.8 (m + 1)) / m quantile of the m
  calibration scores; interval u_hat +/- q.
- The SIX-SEASON WAR interval: nonconformity |L6 - E_hat[L6]| on calibration instances with a
  fully observed L6; interval E_hat[L6] +/- q (lower end at least the smallest observed L6).
- COVERAGE CHECK (registered): the share of development test rows inside their interval, pooled
  over the folds, for each interval (the WAR interval on rows with a fully observed L6). Nominal
  0.80; "covers" when inside 0.75 to 0.85.
- The FULL PREDICTIVE DISTRIBUTION of L6: a mass of 1 - P(reach) at 0 and, given reach, the
  point E_hat[L6 | reach] plus the empirical residuals of the reached calibration instances.
  PIT (randomized for the mass at 0) on development test rows with a fully observed L6, decile
  shares reported; "calibrated" when every decile share is inside 0.05 to 0.15. Its CRPS is
  reported beside the raters' (section 7.4).
- Null: the same intervals for the consensus-only anchor fit (coverage and width).
- Planted: exchangeable synthetic data, n 2,000; coverage inside 0.77 to 0.83.

### 6.7 Pitcher-by-role reporting

X3 minus consensus and X3 minus served eFV, within (frame, side, year) Spearman restricted to
the pitcher rows of one usage role at the read (STARTER, SHORT-START, RELIEF; groups of at
least 20 rows), pooled over the development pool, player-clustered B 4000 seed 20261020.
Never by consensus-FV level. Reported, never in the rule.

## 7. The statistic

### 7.1 The pool (EFV_BEAT_POOLED_POWER's registered estimand)

The lv_dev and vm_dev rows, de-duplicated by its rule keep_lv (a player with an lv_dev row
loses his vm_dev row), groups (frame, side, year) of at least 20 rows, the within statistic
W(r) = sum n_g rho_g(r) / sum n_g over the groups, a paired group counted only where both
raters have a rho (`tools/efv_beat_pooled_power.read_pool`, unchanged).

### 7.2 The raters

X3 (the rule's rater), X3-ridge, X3-gbm, the direct arms (W3 and L6, each class), the served
eFV (v5 COMBINED re-fit RT, its out-of-fold development order, `efv_beat_tilted_labels.build`
with its parity guards: RT within must reproduce 0.1683 lv_dev and 0.3937 vm_dev to 1e-4, else
nothing is read), eFV v5 COMBINED before the re-fit (the same build), eFV V2 (the frame rows'
own V2 order) and PROSPX consensus.

### 7.3 Intervals

Paired, E_cond (scores fixed, clusters resampled), B = 4000, seed 20261020; player-clustered
(primary) and club-clustered (`efv_beat_pooled_power.club_of`). mde95 = 1.645 x the SD of the
draws, printed before the point estimate.

### 7.4 The distributional scores (reported beside the rank statistic, never in the rule)

On the pool's rows, for every rater the same way: its within-group percentile, mapped to a
predictive distribution by the leave-one-year-out threshold logistic of
`efv_upside_volatility` (its WAR grid and lambda): the CRPS on six-season WAR (rows with a fully
observed L6) and the log loss of the bust (L6 at or below 0), middle and star (L6 above 10)
classes; and the log loss of REACH (R3, lv_dev rows) from a leave-one-year-out logistic of R3
on the rater's percentile. X3 minus consensus and X3 minus served eFV on each, with the
player-clustered interval (B 4000, seed 20261020; lower is better for every loss). X3's own
predictive distribution (6.6) is scored beside them.

## 8. The comparisons

The ESTIMAND: D = W(X3) - W(PROSPX consensus) on the pool, both sides. Also reported (never
in the rule): X3 - served eFV, X3 - v5 COMBINED, X3 - V2, X3-ridge and X3-gbm and each direct
arm against consensus and served eFV, every comparison by side and per frame.

## 9. The pass rule

PASS when ALL of:

- (A) D's one-sided 95 percent lower bound is above 0 under BOTH the player-clustered and the
  club-clustered intervals (the estimand's registered rule);
- (B) X3 does not trail served eFV on the pool by more than 0.005 (the point estimate of
  W(X3) - W(served) is at least -0.005);
- (C) the NULL COMPARATOR: D is above the 95th percentile of 20 null reruns of the whole
  pipeline, each with every feature permuted within (side, instance kind, year) across the
  instances (seeds 20261021 to 20261040);
- (D) the PLANTED RECOVERY: a planted feature (rho 0.20 with the percentile of the instance's
  own label within (side, instance kind, year): W3 for an LV instance, the L6 target for an MTX
  instance, career WAR to date for a PIN instance; standard normal noise, seed 20261041), added
  to both sides' lists, lifts X3 above consensus with a player-clustered lower bound above 0.

Otherwise FAIL, worded "trails" when the player-clustered upper bound of D is below 0 and "ties"
otherwise; a run whose (D) fails is reported as UNRESOLVED besides.

The owner's holdout clause ("not trailing served eFV on the holdout by more than 0.005"):
under EW3-13 the 2026 holdout is spent and a model trained with EFV_TRAIN_THROUGH_2026 is never
claimed on it, so the holdout is the 2027 FORWARD READ: the preseason 2027 lists scored on 2027
regular-season WAR, X3's production order (trained through 2026) against served eFV and
consensus, within (side) Spearman, read once after the 2027 season resolves under the same
statistic and seed. Its data does not exist until then. It is registered here as the
confirmation clause of any flip: a PASS on (A) to (D) builds the model dark and asks the flip
question; the flip question states that the forward clause is still open.

## 10. What happens under each verdict

- FAIL. Nothing served moves. No flag, no dark build, no flip question. The development rows
  of X3 (model `efv_x3_pooled`, role development, adjudicating nothing) are added to the Source
  Comparison progress ledger, drawn hollow like every development row. The results document may
  say: "Pooled over every development frame (N rows), the pooled model X3 minus PROSPX
  consensus reads D (one-sided 95 percent lower bound L); the read could detect an edge of M or
  larger."
- PASS. X3 is built DARK behind `efv_x3_pooled.EFV_X3_ON = False`: the production fit (both
  classes' selected configuration on every instance through 2026 with
  EFV_TRAIN_THROUGH_2026 on), live-board columns read as of today with the no-look-ahead
  assertion, card driver chips with plain-English labels (each feature's contribution to the
  live score), and `OWNER_QUESTION.md` in the task's output directory (options: keep the served
  re-fit; flip X3 behind its flag with the forward clause open; flip after the 2027 forward
  read). The production configuration is the one the nested selection chose in the most outer
  folds (ties to the simpler, as in section 5). The only copy allowed after a yes is the registered one of
  `docs/efv-v2/EFV_BEAT_POOLED_POWER.md` section 10 with X3's numbers.

## 11. No look-ahead, guards and bans

- Every input of an instance is asserted dated at or before its read: the X1 window seasons
  ended by the read (the module's own LookAheadError), every X2 input strictly before the read
  (the module's own assertion), the eTools' board year and sub-driver seasons, the usage read
  season, the pitch-rate seasons. The run records the number of checks and the latest input
  date per instance kind.
- Guards before any fit: no LV instance at vintage 2020 or 2021 or after 2019, no PIN instance
  at a debut year of 2025 or later, no MTX instance at a decision year of 2025 or later in any
  development fold; the comparator parity of 7.2.
- The source is scanned (test) for any grouping by consensus-FV level and for any reference to
  a reserved vintage outside the guards.

## 12. Outputs and tests

- `efv_x3_pooled.py` (the build and the read; refuses to overwrite an existing artifact),
  `test_efv_x3_pooled.py` (the ridge and Newton fits on fixtures, the anchor-only start of the
  boosted class, the recombination, the conformal quantile, every planted check of section 6,
  the guards and the source scans), `data/_labs/efv_x3/efv_x3_pooled.json` (off the webroot,
  role development), sections 13 and 14 below, `docs/efv-v2/EFV_X3_POOLED_MODEL_RESULTS.md`,
  two development rows in `data/efv_progress.json`, a dated note on the eFV row of
  `data/model_registry.json`, one line in `docs/efv-v2/STATUS.md`.
- Defaults applied by this registration (named for the orchestrator): forward-chained outer
  folds (the served comparator's); the reach stage on the list-vintage frame only; R3 as the
  reach label; the holdout clause read as the 2027 forward read; both clusterings in (A); the
  null and planted clauses (C) and (D) added to the owner's two clauses; X5 rows not used; the
  live-timing twins not used; the re-weight's eTool weights not imported.

## 13. The numbers (appended by the run)

## 14. The verdict (appended by the run)
