# OPPORTUNITY DECOMPOSITION GATE (Lane B-L3, 2026-08-09): does WAR-per-opportunity open a new eFV driver?

**STATUS OF THIS FILE.** Sections 0 through 9 are the PRE-REGISTRATION, written in full
before `tools/efv_opportunity_lab.py` existed and before a single number in this lane was
computed. Section 10 is a placeholder filled in after the run. Nothing in sections 0 to 9 is
edited afterwards.

**THIS LANE IS A CLOSURE, NOT A FEATURE HUNT.** Zero model changes ship from it. No feature
enters `_FEATURES_HIT` or `_FEATURES_PIT`, no constant moves, `efv_model.py` and
`efv_dataset.py` are not edited by this lane, and `data/model_registry.json` is not edited by
this lane either (the rows it needs are REPORTED, and a later wave applies them). The lane
owns exactly four files:

    tools/efv_opportunity_lab.py
    docs/efv-2026-08-09/OPPORTUNITY_DECOMP_GATE.md   (this file)
    data/xfv_opportunity_eval.json
    test_opportunity_lab.py

---

## 0. The owner question, and why the answer is expected to be no

The ask: correlate eFV against WAR-per-opportunity metrics (WARPA+ for hitters, WARIP+ for
pitchers) and see whether a rate metric becomes a new eFV driver.

The mechanism behind the expected no is a decomposition. Cumulative first-six-season WAR is
a product of two things:

    WAR = OPPORTUNITY x QUALITY = (PA or IP accrued) x (WAR per PA or per IP)

A prospect board grades a player. If the board's grade correlates far more strongly with
OPPORTUNITY than with QUALITY, then the board and every model fit on top of the board are
principally forecasting playing time, and the label they are scored against is principally a
playing-time label. A rate metric is then not a NEW axis; it is the residual axis that
neither the board nor the model has ever been able to see.

That is a claim with a number attached, and section 2 fixes the number that would refute it.

## 1. Why this is not a banned re-analysis

The closed ledger cell that looks nearest is `data/xfv_rank_objective_eval.json`, lane I1,
target transforms, 20 of 20 rank cells failed. That cell tested `rank_normal`, `signed_log1p`,
`ipcw`, `sqrt` and `uniform`.

EVERY ONE OF THOSE IS A MONOTONE RELABEL OF THE SAME CUMULATIVE TARGET. A monotone relabel
cannot change a Spearman of the target against anything, and it introduces no new outcome
column. None of the five is a decomposition, and none of them ever saw a PA or an IP.

Six-year PA/IP accrual has NEVER been in either matrix. It is not derivable from
`target_censored`, `target_resolved`, `observed_seasons` or `weight`. It comes from a
different table entirely (Baseball Reference WAR daily, joined through MLBAM id). The closed
ledger's own reopening condition is NEW DATA rather than re-analysis, and a new outcome
column joined from a source the matrices have never carried is new data by that definition.

The banned re-analysis in the neighbourhood is a different one and this lane does not touch
it: `efv_reliability._realized_bucket` (efv_reliability.py:126-149) forbids re-running the
season-share-corrected relabel and re-reporting the same 3.1 percent pooled-bust-ECE
movement as new. That docstring's closing sentence is the boundary:

> The remaining miscalibration is real and belongs to the distribution (plan lane C2), not
> to the label.

This lane stays on the distribution side of that sentence. It measures label DISPERSION, not
bucket assignment. It reports no ECE. It re-runs no relabel. Section 8's diagnostic changes
the POOL (complete-window rows only) and reports a dispersion SLOPE, which is a statement
about the distribution, exactly the side of the line the docstring leaves open.

## 2. The decomposition read, and what would refute it

Fixed before the run. On the debuted pool with a successful opportunity join, unweighted
Spearman:

    R_opp     = rho(consensus_fv_raw, six-year OPPORTUNITY)
    R_war     = rho(consensus_fv_raw, six-year WAR)
    R_quality = rho(consensus_fv_raw, six-year QUALITY | exposure threshold)

The planning read, which this lane must reproduce or contradict:

| quantity | hit | pit |
|---|---|---|
| R_opp | 0.584 | 0.440 |
| R_war | 0.278 | 0.214 |
| R_quality | 0.316 | 0.140 |

REFUTATION CLAUSE. The decomposition read is refuted if `R_opp <= R_war` on either side, or
if `R_opp - R_quality < 0.10` on either side. Either would mean the board is not
predominantly an opportunity forecast and the rate axis is not a distinct residual.

MATERIAL-DIFFERENCE CLAUSE. A reproduced correlation is reported as MATCHED when it lands
within 0.05 of the planning figure, as CLOSE when within 0.10, and as DIFFERENT otherwise. A
DIFFERENT figure is reported as a finding in its own right and does not get quietly
rewritten to whatever this lane measures.

## 3. Hazard 1, pre-registered: the quality leg is conditioned on selection

`R_quality` is computed on the subpopulation that cleared an exposure threshold. PA is the
thing being divided out AND the thing the sample is selected on, and PA correlates with FV.
The number is therefore a CONDITIONAL-ON-SELECTION read.

It MUST NOT BE QUOTED UNCONDITIONALLY. Any sentence of the form "the board correlates 0.316
with quality" is false as stated; the true sentence carries "among players who reached the
threshold". The selection is on the numerator's own denominator, so the standard collider
argument applies: conditioning on high PA among low-FV players selects for the ones who
earned it with a high rate, which biases the within-stratum FV-to-rate association DOWNWARD.
The published direction of the bias is therefore pessimistic for the board, and the honest
reading is that `R_quality` is an UPPER-BOUNDED-BELOW quantity, not a point estimate of the
unconditional association.

The artifact carries this hazard as a field, not as prose, so a downstream consumer that
reads the JSON cannot miss it.

THRESHOLD, FIXED BEFORE THE RUN. Primary: 200 PA (hitters), 150 IPouts = 50.0 IP (pitchers).
Declared sensitivity, run and reported regardless of outcome, NOT a selection menu: 100 PA
and 300 PA; 90 IPouts and 300 IPouts. If the primary and the sensitivities disagree in sign
of the `R_opp` versus `R_quality` gap, the lane reports NO quality figure and says the
threshold is doing the work.

## 4. Hazard 2, pre-registered: the join source is not deploy-reachable

`.cache/war_daily/bat.parquet` and `.cache/war_daily/pit.parquet` are GITIGNORED and are
rebuilt from `pybaseball`. That is acceptable for a lab under `tools/` whose product is a
verdict.

IT MUST NEVER BECOME A MODEL INPUT WITHOUT A DURABLE DEPLOY-REACHABLE ARTIFACT. The deploy
box runs `git checkout -- .` nightly and has no guarantee that a `.cache` directory exists or
is current. A feature reading that path would silently impute to zero on the box and would
score fine in every local test. If any successor lane ever wants six-year PA/IP as a feature,
the first deliverable is a committed, dated, schema-tested `data/` artifact carrying the
accrual, and the second is a freshness row. Not the parquet.

This lane writes NO feature and reads the parquet only inside `tools/`.

## 5. The identity join, already solved

Not re-litigated here. `data/sources/mlbam_id_overrides.json` (735 entries) plus
`data/sources/mlbam_id_overrides_busts.json` (283) cover the debuted matrix rows that lack an
inline `mlbam_id`. Join through the same spine `arb_dataset.war_daily_spine` uses
(arb_dataset.py:119), collapsing stints by (mlb_ID, year_ID).

Coverage is REPORTED as a fact, not gated on: the lane records joined and unjoined counts per
side and per kind. Bust rows never reached MLB, so their opportunity is 0 by construction and
they need no join.

Pre-run expectation from planning: 250 of 259 hitter and 258 of 267 pitcher debuted rows
lacking an inline id are covered; 831 of 845 debuted hitter rows reach a full six-season PA
total, 98.3 percent.

CENSORING PARITY. The opportunity accrual is built on the SAME window and the SAME censoring
convention as `efv_dataset._label_6yr`: window `debut_year .. debut_year+5`, observed years
capped at `RESOLVED_THROUGH` (2025), and the censored tail projected at the observed
per-season rate. Using a different censoring rule for the numerator and the denominator of a
decomposition would manufacture the decomposition.

## 6. The cosine bound, and why it is the publishable result

Fit the shipped ridge specification twice on the same standardized design matrix: once on
the shipped WAR target, once on the opportunity target. Take the two standardized weight
vectors `w_war` and `w_opp` and compute

    cos(w_war, w_opp)

Planning read: 0.979 ON BOTH SIDES.

WHAT THAT NUMBER MEANS, stated before it is reproduced. Within the span of the existing
feature set, the best linear predictor of opportunity and the best linear predictor of WAR
point in very nearly the same direction. The component of the opportunity predictor that is
ORTHOGONAL to the WAR predictor has squared length `1 - cos^2`. At 0.979 that is 0.0416 of
the opportunity predictor's variance, a linear extent of `sqrt(1 - 0.979^2) = 0.204`.

So a reweighting of the existing features - which is what every one of the twenty closed
objective-lane cells was - has at most that much room to express an opportunity-specific
direction that is not already expressed. The cosine is a GEOMETRIC UPPER BOUND on what any
reweighting of the existing feature set can buy.

THIS IS THE POINT OF THE LANE. It converts "we tested twenty things and they all failed" into
"here is the reason they had to fail". The twenty nulls are not twenty independent
coincidences; they are twenty samples from a feature space that has one dominant direction
and 0.204 of a second one. It is published BESIDE the closed ledger for that reason.

BOUND HYGIENE. The cosine bounds REWEIGHTINGS OF THE EXISTING FEATURE SET. It does not bound
what a genuinely new feature could buy, it does not bound a nonlinear model, and it is a
statement about linear predictors of the two targets, not about the targets themselves. The
artifact says so in the same block that carries the number. A cosine quoted without that
scope note is a stronger claim than the measurement supports.

## 7. The four exploitation arms, all pre-registered, all expected to lose

If the decomposition is real, the obvious exploitation is to model the two factors
separately. Four arms, fixed before the run. Each is scored on the shipped headline metric
and floored.

ARM 1, MULTIPLICATIVE. Fit `E[opportunity]` and `E[WAR per opportunity]` as separate ridges
on the identical feature spec, and predict `E[PA] x E[rate]`. Scored in two forms: BLENDED,
substituted into the shipped blend in place of the ridge leg at the shipped lambda; and PURE
MODEL LEG, the product alone against the shipped ridge leg.

Planning read (delta against the corresponding shipped leg):

| | hit.full | hit.deb | pit.full | pit.deb |
|---|---|---|---|---|
| blended | -0.0164 | -0.0172 | -0.0271 | -0.0020 |
| pure model leg | -0.1284 | -0.0634 | -0.0920 | -0.0047 |

THE FAILURE IS DIAGNOSABLE AND UNFIXABLE IN THAT FAMILY, and the mechanism is pre-registered
because it is what makes the arm dead rather than merely unlucky. The rate leg is a
least-squares fit and goes NEGATIVE on part of the pool. A product with a negative factor is
not monotone in either factor: a row with a large predicted PA and a slightly negative
predicted rate sorts BELOW a bust with predicted PA of zero. Rank is destroyed at the top of
the board, which is exactly where the pure-leg collapse in the table above lives. Clipping
the rate at zero does not rescue it, it only replaces an inverted order with a tie, and a tie
at the top of the board is also a rank loss. The arm is reported as CLOSED FOR CAUSE.

ARM 2, HURDLE. `P(reach) x E[WAR | reach]`, the standard two-part model for a mass-at-zero
outcome. `P(reach)` is fit on the full pool including busts (whose reach indicator is 0);
`E[WAR | reach]` is fit on reachers only. Planning read, blended:

| hit.full | hit.deb | pit.full | pit.deb |
|---|---|---|---|
| +0.0014 | -0.0021 | -0.0085 | -0.0069 |

ARM 3, AUXILIARY MULTI-TASK. One shared weight vector fit against a convex combination of the
standardized WAR target and the standardized opportunity target, weight `gamma` on the
auxiliary. `gamma = 0` is the shipped ridge by construction, which is the arm's own parity
check. Planning read at `gamma = 1.0`:

| hit.full | hit.deb | pit.full | pit.deb |
|---|---|---|---|
| -0.0180 | -0.0190 | -0.0113 | +0.0086 |

MONOTONE-DEGRADATION CLAUSE, pre-registered: planning reports the auxiliary arm degrading
monotonically in gamma. The lane sweeps `gamma` in {0, 0.25, 0.5, 1.0, 2.0} and reports
whether the monotone claim holds. A NON-monotone sweep with an interior optimum would be a
genuine finding and is reported as one; it would not by itself promote the arm, which still
has to clear a floor.

ARM COUNT. Four arms as the brief names them: multiplicative-blended, multiplicative-pure,
hurdle, auxiliary. The multiplicative pure leg is counted as its own arm because it is scored
against a different incumbent leg.

## 8. Metric, floors and estimator labelling, fixed before the run

HEADLINE METRIC. Pair-weighted pooled Spearman on cumulative WAR (`target_censored`),
forward-chained over `SCORED_YEARS`, on both registered pools, `debuted_km` and
`full_pool_km`, plus `block_rho`. That is the shipped instrument, unchanged. No arm gets a
metric of its own.

INCUMBENT. Each arm's delta is `rho(arm) - rho(the shipped leg it replaces)` on the SAME rows
in the SAME folds. Blended arms are compared against the shipped blend; the multiplicative
pure leg is compared against the shipped ridge leg. The consensus baseline rho is carried in
every cell so a reader can recover the arm-versus-consensus delta without refitting anything.

FLOORS. Every delta is floored with the B-L1 published floors from
`data/xfv_power_eval.json`, block `partb_floors`:

| cell | MDE95 (E_refit) | MDE95_COND (E_cond) |
|---|---|---|
| pooled_rho.hit.full_pool_km | 0.0295 | 0.0208 |
| pooled_rho.pit.full_pool_km | 0.0265 | 0.0207 |
| pooled_rho.hit.debuted_km | 0.0450 | 0.0204 |
| pooled_rho.pit.debuted_km | 0.0431 | 0.0295 |
| block_rho | 0.0317 | 0.0203 |

NEITHER FLOOR IS QUOTED WITHOUT ITS ESTIMATOR LABEL. That is the `EFV_GATE_STANDARD.md`
section 1 convention and `data/xfv_power_eval.json.partb_floors.convention` restates it:
MDE95 is one-sided `1.645 * sd` on `|delta|`, MDE95 is E_refit, MDE95_COND is E_cond. Every
delta block in the artifact carries `mde95`, `mde95_cond`, `margin_over_mde95`,
`margin_over_mde95_cond` and an explicit `estimator` string on each. A margin below 1.0 is
NOT RESOLVABLE and the arm's verdict is NULL, not "small loss".

NO NEW FLOOR IS DERIVED IN THIS LANE. The floors are read from the B-L1 artifact and cited.
A lane that produces only losses has no business also producing the bar it is judged against.

PROMOTION BAR, for completeness and because it will not be met: an arm promotes only if it
gains at least 1.0x its floor under BOTH estimators on the PRIMARY cell
(`pooled_rho.hit.full_pool_km`) and does not resolvably lose any other cell. No arm is
expected to reach it.

## 9. The cheap diagnostic beside it: is the censoring defect the same defect as the
elite-tier under-dispersion?

`efv_dataset._label_6yr` (efv_dataset.py:911-916 in the current tree, the censored branch)
projects the unobserved tail at the OBSERVED per-season rate. That substitutes a conditional
mean for a draw. A conditional mean has no residual, so the fill REMOVES WITHIN-PLAYER
VARIANCE from the label of every censored row, and the censored rows are about 21 percent of
the pool, concentrated in the recent, higher-graded cohorts - exactly the tier where the
variance shortfall was measured.

DIAGNOSTIC. Recompute the within-cohort dispersion slope - OLS slope of realized target on
the forward-chained OOS prediction, both centered within decision-year cohort - on
COMPLETE-WINDOW ROWS ONLY (`censored == False`, a fully resolved six-season window), and
compare it against the same slope on the full pool.

DECISION RULE, fixed before the run, stated in both directions so the verdict cannot be read
off after the fact:

- If the slope MOVES MATERIALLY toward 1.0 when the censored rows are dropped, the flat-rate
  fill is causally implicated in the dispersion shortfall. The censoring defect and the
  elite-tier under-dispersion are then ONE defect with two symptoms, and fixing the label
  fill is a candidate fix for both.
- If the slope is UNCHANGED, the shortfall survives on rows whose label carries its full
  within-player variance. The fill is then not the cause and the two are TWO defects that
  have to be fixed separately.

MATERIAL is fixed before the run at an absolute slope movement of 0.05, and the direction has
to be toward 1.0 to count.

NOTE ON THE BRIEF. The lane brief states the rule as "IF THE SLOPE IS UNCHANGED, the
censoring defect and the elite-tier under-dispersion are ONE defect, not two." That reads
inverted against the mechanism the same brief describes: an unchanged slope on
full-variance-label rows is evidence that the fill is NOT doing the work, which separates the
defects rather than merging them. This file pre-registers the rule in the direction the
mechanism implies, records the discrepancy here rather than silently resolving it, and
reports the raw slopes so a reader can apply either rule. The measurement is the same either
way; only the label on the verdict differs.

CONFOUND, pre-registered: complete-window rows are OLDER cohorts. Dropping the censored rows
also drops the recent cohorts, so any slope movement is confounded with cohort era. The
diagnostic therefore ALSO reports the slope on complete-window rows restricted to the cohorts
that contain both censored and uncensored rows, and on the full pool restricted to the same
cohorts, which removes the era shift from the comparison. If the two comparisons disagree the
verdict is INDETERMINATE and is reported as such.

## 10. RESULTS

Run: `python tools/efv_opportunity_lab.py all`, 2026-08-10, seed 20260809, 40 seconds.
Ledger: `data/xfv_opportunity_eval.json`. Sections 0 through 9 above are unedited.

**VERDICT: CLOSED. Nothing ships. No arm promoted. The rate axis is not a new eFV driver.**

### 10.1 The join

| | hitters | pitchers |
|---|---|---|
| debuted rows | 845 | 981 |
| lacking an inline `mlbam_id` | 259 | 267 |
| of those, covered by the two override files | 250 | 258 |
| debuted rows joined | 836 (98.9%) | 972 (99.1%) |
| joined with a nonzero six-season accrual | 831 (98.3%) | 960 (97.9%) |
| bust rows, opportunity 0 by construction | 1,072 | 1,056 |
| bust rows found with ANY MLB exposure in the frame | 0 | 0 |

The planning coverage figures reproduce exactly: 250 of 259 and 258 of 267 covered by the
overrides, 831 of 845 hitter rows at a full six-season PA total, 98.3 percent. The zero
bust rows with MLB exposure is a clean structural check on the `kind` field: no row labelled
a bust has a plate appearance or an out recorded in the window.

### 10.2 The decomposition, section 2

Pre-registered primary pool (debuted rows with a join), unweighted Spearman:

| | hit | plan | grade | pit | plan | grade |
|---|---|---|---|---|---|---|
| R_opp | 0.5074 | 0.584 | CLOSE | 0.3803 | 0.440 | CLOSE |
| R_war | 0.3779 | 0.278 | CLOSE | 0.2669 | 0.214 | CLOSE |
| R_quality | 0.3014 | 0.316 | MATCHED | 0.1796 | 0.140 | MATCHED |

REFUTATION CLAUSE: SURVIVES on both sides. R_opp exceeds R_war by 0.130 (hit) and 0.113
(pit), and R_opp minus R_quality is 0.206 (hit) and 0.201 (pit), both far above the 0.10 bar.

FINDING: THE PRE-REGISTERED POOL WAS NOT THE PLANNING POOL. Section 2 registered the
debuted pool. On the FULL modelled pool (debuted plus busts, minus `bust_recent`),
unweighted, the planning read reproduces to three decimals:

| | measured | plan | gap |
|---|---|---|---|
| hit R_opp | 0.5822 | 0.584 | 0.0018 |
| hit R_war | 0.2766 | 0.278 | 0.0014 |
| pit R_opp | 0.4319 | 0.440 | 0.0081 |
| pit R_war | 0.2122 | 0.214 | 0.0018 |

So the planning basis is identified: full pool, unweighted, n 1,874 hit and 1,969 pit. The
pre-registered debuted read STANDS as the primary and is not rewritten; both are published
side by side in the artifact under `basis_sensitivity`. The reading is the same on either
basis, which is the point of publishing both. The gap between them is mechanical: on the
full pool the bust rows carry a structural zero on the numerator AND the target, so the
board's ability to separate a never-MLB player from a major leaguer counts as opportunity
skill and lifts R_opp from 0.507 to 0.582.

The quality threshold is not doing the work. R_quality moves 0.3014 / 0.3049 / 0.3005 across
200 / 100 / 300 PA and 0.1796 / 0.1783 / 0.1475 across 150 / 90 / 300 IPouts. The
`R_opp - R_quality` gap keeps its sign at every threshold on both sides.

The hazard stands as pre-registered and is carried as a JSON field, not prose:
`decomposition.sides.*.decomposition.SELECTION_HAZARD`.

### 10.3 The cosine bound, section 6

| | measured | plan | grade | orthogonal linear extent |
|---|---|---|---|---|
| hit | 0.9485 | 0.979 | MATCHED | 0.3169 |
| pit | 0.9605 | 0.979 | MATCHED | 0.2783 |

Both grade MATCHED under the pre-registered 0.05 band. THE DERIVED BOUND IS LOOSER THAN
PLANNING'S, and that is worth saying plainly because the bound, not the cosine, is the
publishable object: `sqrt(1 - 0.979^2) = 0.204`, while the measured hitter figure is 0.317,
55 percent more orthogonal room, and the measured pitcher figure is 0.278, 36 percent more.
The orthogonal variance share is 0.1004 (hit) and 0.0775 (pit) rather than planning's 0.0416.

The conclusion does not change. Roughly 90 to 92 percent of the opportunity predictor's
variance already lies along the WAR predictor inside the existing feature span. Twenty
reweightings of a space with one dominant direction and 0.28 to 0.32 of a second one is not
twenty independent experiments, and that is the mechanism behind the 20-of-20 objective-lane
ledger. Quote the measured 0.9485 / 0.9605 and the measured extents, not 0.979.

### 10.4 The four arms, section 7

Deltas against the shipped leg each arm replaces, on identical rows in identical folds.
Floors from `data/xfv_power_eval.json partb_floors`, both estimators on every cell.

POOL BASIS. The scored pool is the shipped pool minus the rows whose opportunity join
failed, because an arm and its incumbent must score identical rows: 1,783 of 1,786
(hit.full), 746 of 755 (hit.debuted), 1,874 of 1,881 (pit.full), 881 of 890 (pit.debuted).
The floors are therefore applied to a pool 0.2 to 1.2 percent smaller than the one they were
derived on. A floor scales as one over root n, so that is a 0.1 to 0.6 percent effect on the
bar, inside the rounding the published floors carry. Reported, not assumed.

MULTIPLICATIVE, blended - RESOLVABLE LOSS in all five cells:

| cell | delta | plan | E_refit margin | E_cond margin | verdict |
|---|---|---|---|---|---|
| hit.full_pool_km | -0.0565 | -0.0164 | 1.92x | 2.72x | RESOLVABLE LOSS |
| hit.debuted_km | -0.1045 | -0.0172 | 2.32x | 5.12x | RESOLVABLE LOSS |
| pit.full_pool_km | -0.1335 | -0.0271 | 5.04x | 6.45x | RESOLVABLE LOSS |
| pit.debuted_km | -0.1948 | -0.0020 | 4.52x | 6.60x | RESOLVABLE LOSS |
| block_rho | -0.0926 | n/a | 2.92x | 4.56x | RESOLVABLE LOSS |

MULTIPLICATIVE, pure model leg - RESOLVABLE LOSS in all five cells: -0.0892 (plan -0.1284),
-0.1452 (-0.0634), -0.1794 (-0.0920), -0.2174 (-0.0047), block -0.1090. Margins 3.0x to 8.7x.

The arm loses HARDER than planning on three of four blended cells and on three of four pure
cells; two blended cells and one pure cell grade DIFFERENT. Direction and verdict are
identical to planning, magnitude is not. The failure mechanism is measured, not asserted:
the rate leg's prediction is NEGATIVE on 32.8 percent of hitter rows and 50.5 percent of
pitcher full-pool rows, and 109 hitter and 158 pitcher rows sit in the top opportunity
quartile WITH a negative predicted rate, which is exactly the inversion pre-registered in
section 7. The arm is CLOSED FOR CAUSE.

The arm was also handed a scale calibration it was not owed (`multiplicative_blend_cal`, a
train-fit affine map onto the WAR scale before blending, so it enters the mixture at the
same effective lambda as the incumbent). It still loses: -0.0247, -0.0402, -0.0203, -0.0260,
block -0.0265; three of five cells resolve as losses under E_cond. The idea does not survive
being given its best shot.

HURDLE, blended - NULL in all five cells, and the closest reproduction in the lane:

| cell | delta | plan | E_refit margin | E_cond margin | verdict |
|---|---|---|---|---|---|
| hit.full_pool_km | -0.0039 | +0.0014 | 0.13x | 0.19x | NULL |
| hit.debuted_km | -0.0136 | -0.0021 | 0.30x | 0.67x | NULL |
| pit.full_pool_km | -0.0080 | -0.0085 | 0.30x | 0.39x | NULL |
| pit.debuted_km | -0.0014 | -0.0069 | 0.03x | 0.05x | NULL |
| block_rho | -0.0065 | n/a | 0.21x | 0.32x | NULL |

All four pooled cells grade MATCHED. Scale-calibrated: -0.0018, -0.0160, -0.0076, -0.0020,
block -0.0075, all NULL.

AUXILIARY MULTI-TASK at gamma 1.0 - NULL in all five cells: -0.0096 (plan -0.0180), -0.0150
(-0.0190), -0.0026 (-0.0113), +0.0025 (+0.0086), block -0.0092. All four pooled cells grade
MATCHED, largest margin 0.46x of its E_cond floor. Scale-calibrated is also NULL throughout.

GAMMA MONOTONICITY. Registered as a check, and it holds on three of four cells. Blend deltas
by gamma:

| cell | 0 | 0.25 | 0.5 | 1.0 | 2.0 | monotone |
|---|---|---|---|---|---|---|
| hit.full_pool_km | 0.0 | -0.0070 | -0.0086 | -0.0096 | -0.0112 | yes |
| hit.debuted_km | 0.0 | -0.0028 | -0.0127 | -0.0150 | -0.0226 | yes |
| pit.full_pool_km | 0.0 | -0.0003 | -0.0014 | -0.0026 | -0.0040 | yes |
| pit.debuted_km | 0.0 | +0.0021 | +0.0026 | +0.0025 | +0.0024 | NO |

The exception is the smallest cell, its largest excursion is +0.0026, which is 0.09x of its
own E_cond floor, and its neighbouring cells on the same side degrade monotonically. Read it
as noise, not as an interior optimum. The monotone-degradation claim is upheld.

A DEFECT IN MY OWN ARM, FOUND BY ITS OWN PARITY CHECK AND FIXED. The first implementation fit
the auxiliary on the convex combination `(z_y + g*z_o)/(1+g)`. At `g = 0` that is the
STANDARDIZED target, not the target: ridge weights scale with y, so the arm's model leg came
out on a z-scale (sd about 1) while the consensus leg it blends with is on the WAR scale (sd
about 5), and lam meant something different for the arm than for the incumbent. The
pre-registered `gamma = 0` parity check caught it - hit.full_pool_km read +0.0022 where it
must read exactly 0. The mixed target is now rescaled to the WAR target's own mean and sd,
parity is exact 0.0 on all four cells for both the blend and the pure leg, and the numbers
above are the post-fix ones. The pre-fix gamma-1.0 deltas were -0.0034 / -0.0055 / -0.0092 /
+0.0008; the verdicts did not change, but they were not interpretable as published.

HARNESS LIVENESS. Ten of the lane's cells resolve, all on the multiplicative arm, at 1.9x to
8.7x their floors under both estimators. The NULL verdicts on hurdle and auxiliary are
therefore informative rather than inert.

### 10.5 The dispersion diagnostic, section 9

THE PRE-REGISTERED CONTROL IS INFEASIBLE ON THIS DESIGN, AND THAT IS THE FIRST FINDING.
`censored` is a near-deterministic function of debut cohort: 2011-2020 fully resolved,
2021-2024 censored, with 2 exceptions in 755 scored hitter rows and 2 in 890 pitcher rows,
0.3 and 0.2 percent. The two cohorts that contain both kinds contribute 2 complete-window
rows each side, below the 8-row minimum. Dropping the censored rows IS dropping the recent
cohorts. The confound section 9 pre-registered CANNOT BE REMOVED BY RESTRICTION, so the
unrestricted comparison (hit 0.8302 full pool against 0.7803 complete-window, n 755 and 370;
pit 0.8632 against 0.7328, n 890 and 437) cannot adjudicate the question and is published
marked CONFOUNDED.

AN IDENTIFIED INSTRUMENT WAS BUILT INSTEAD, AND IT IS LABELLED AS NOT PRE-REGISTERED. Take
only fully-resolved rows, where the true six-season label is known. Truncate each row's
window at k observed seasons and apply `_label_6yr`'s own flat-rate fill. Rows, cohorts and
OOS predictions are held FIXED; only the label moves, so cohort era cannot confound it.
Per-season WAR comes from the same war_daily join, and its agreement with the shipped
`target_resolved` is reported rather than assumed: 365 of 367 hitter rows and 426 of 431
pitcher rows within 0.05, 99.5 and 98.8 percent. That agreement forced a correction of its
own - pitching-only WAR reproduces the shipped pitcher label on only 65 percent of rows (max
abs diff 19.57) because a pitcher's bWAR includes his batting, so the instrument uses
COMBINED bat plus pit WAR on both sides.

Within-cohort dispersion slope, predictions held fixed, label truncated and refilled:

| observed seasons k | hit slope | vs true | pit slope | vs true |
|---|---|---|---|---|
| true label (k = 6) | 0.7805 | - | 0.7278 | - |
| 5 | 0.7765 | -0.0040 | 0.6371 | -0.0906 |
| 4 | 0.7587 | -0.0218 | 0.5553 | -0.1725 |
| 3 | 0.7615 | -0.0189 | 0.4595 | -0.2683 |
| 2 | 0.6074 | -0.1730 | 0.4135 | -0.3143 |

VERDICT: ONE DEFECT, on both sides, in the direction section 9 registered as "the fill is
causally implicated". The movement is far above the 0.05 material bar (-0.173 hit, -0.314 pit
at k = 2) and it is monotone in k on the pitcher side. THE SIGN IS THE ACTIONABLE PART: the
fill DEPRESSES the slope. A meaningful share of the dispersion shortfall measured on the
recent, censored, higher-graded cohorts is manufactured by the label rather than by the
model. The label sd at k = 2 is 0.914 (hit) and 0.942 (pit) of the true label's, so the fill
does compress the label at the thinnest exposure, which is the mechanism section 9 named.

The censoring defect and the elite-tier under-dispersion are ONE defect with two symptoms.
Fixing the label fill is a live candidate fix for both, and any future dispersion measurement
on the 2021-2024 cohorts should be read as partly an artifact of `_label_6yr` until it is.

ON THE BRIEF'S DECISION RULE. Section 9 recorded that the brief's rule ("if the slope is
UNCHANGED the two are ONE defect") reads inverted against the mechanism, and pre-registered
the opposite direction. The measurement came out on the OTHER branch - the slope MOVES, and
moves a lot - so the two rules agree on the verdict here and the discrepancy did not decide
anything. It is left recorded rather than deleted.

This leg stays on the distribution side of `efv_reliability._realized_bucket:126-149`. It
assigns no bucket, reports no ECE, and re-runs no relabel of the shipped pool;
`test_opportunity_lab.py` enforces that by scanning the reported keys.

### 10.6 What is owed

`data/xfv_opportunity_eval.json` needs a registry row and a MODEL_GLOSSARY entry
("internal"). This lane does NOT edit `data/model_registry.json` or
`test_methodology_freshness.py`; the exact rows are reported in the lane handoff and a later
wave applies them. Until then `test_model_registry.test_every_eval_artifact_is_registered`
names this artifact, by design.
