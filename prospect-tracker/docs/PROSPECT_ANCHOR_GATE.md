# Prospect realized-anchor calibration gate (pre-registered 2026-09-23)

Covers ONE question, ordered by the owner on 2026-09-23 ("open a gated calibration
lane" for the prospect realized anchor): does the realized anchor that every priced
prospect number reconciles to, `value_framework.fv_to_6yr_avg_war`, match what
graduated prospects of each FV actually delivered over their first six major-league
seasons, on the epoch label?

Producers, none of which exist yet: `tools/prospect_anchor_gate.py` (the one lab,
read-only over production modules, writes one artifact) and, only under one outcome,
a `--fit-v2` mode of the same tool. Artifact: `data/prospect_anchor_gate.json`. Pinned
by `test_prospect_anchor_gate.py`. Registry rows touched: `prospect_surplus` (only
under one outcome) and a new `prospect_anchor` row that points at this document.

Written and committed BEFORE any number is computed, in the shape of
`docs/ARBITRATION_GATE.md` and under the rules of `docs/diamond-betting.md` 5c. It is
the anchor slice of the Z3 valuation-chain reconciliation that
`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` clause (k) lists as a registration that
FOLLOWS the fWAR label epoch and does not ride it.

Where this document and a later measurement disagree, **the measurement is what this
gate uses**, and the disagreement is recorded rather than edited away.

---

## G-0. Honesty clause, first

**Nothing was scored to write this document.** No cell mean was computed, no residual
was taken, no bootstrap was run, no cohort was counted, no candidate anchor was
derived, and no served artifact was summed. Every number below is one of: a value in a
committed config or fitted file (`value_framework_config.yaml`,
`data/value_framework_fitted.json`); a figure already published in a committed eval
artifact (`data/fv_outcome_curves_pooled.json`, `data/fv_outcome_curves.json`,
`data/surplus_backtest_real.json`, `data/xfv_stale_anchor_eval.json`); a figure
already published in a committed document (`docs/efv-2026-09-03/ARKMETRIC_DESIGN_AUDIT.md`
findings F07 and F08, `docs/PROJ_PATH_SHAPE_GATE.md` section 9,
`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 2 and part 3); a figure in a commit
message (`c5167587`); or a line of code read for what it does. Where a published
figure is restated in different units below (a six-year total divided by six), the
restatement is arithmetic on the published figure and is labelled as such.

**Looking early disqualifies.** 5c rule 1 is in force: a number computed on the
outcome frame before the date fixed in section 14 voids this registration, whatever it
measured, and the question may return only as a new registration that discloses the
early read.

### G-0.1 The priors read during design, recorded so a run cannot quietly beat them

This is not a blind registration and it does not pretend to be one. The DIRECTION of
the answer has a published prior, and it is recorded here so that the tolerance,
the frame and the decision rule below can be checked against it by a later reader.

1. `data/value_framework_fitted.json` `empirical_anchors` (generated 2026-09-04, the
   eWAR v2 label epoch refit): the served anchor table and its per-tier diagnostics
   (`n`, `empirical_war_yr`, `reference_war_yr`, `blend_w_public`, `bust_pct`),
   `cohort_window [2014, 2020]`, `n_cohort 3462`, and the `anchors_provenance`
   string that records the sub-45 re-amendment.
2. `data/fv_outcome_curves_pooled.json` (generated 2026-09-04, eWAR v2 label, pool
   3,007 resolved rows, both sides): the published `value`, `cell_mean`, `n_cell`,
   `w_prior` and `ci90` lists at every knot, and the `top_end_is_prior` note.
3. `ARKMETRIC_DESIGN_AUDIT.md` F08 (c) and (d), verbatim: "At FV 45 the anchor serves
   0.31 against a cohort mean of 0.126 and a resolved curve of 0.378" and "the
   resolved evidence points **up** at every knot 45-65". Also F07 (c): "k(FV) is
   0.349 at hitter 45 and 0.535 at 60, so the star bucket at hitter 60 is 2.67
   WAR/season against its own band floor of 4.0, and `survivor_expected_war(60,
   hit)` is 1.546 against the bust-inclusive pooled curve's 1.824 at the same FV".
4. `data/surplus_backtest_real.json` (generated 2026-07-31, bWAR label, listing-FV
   frame, 2017-2019 listings): read for its existence and its frame, which is not
   this gate's frame. It is a prior on a different conditioning variable and two
   label epochs ago, and it is not a comparator here.
5. `data/xfv_stale_anchor_eval.json` (2026-07-14): read for the sub-45 stale-FV
   schedule it governs. Nothing here touches it.
6. Commit `c5167587` (2026-09-23): the owner's numbers (Jesus Made, eFV 61.9,
   expected 7.5 over five years against prime 15.4, "1.55 against 3.17 WAR a
   season") and the commit's own closing paragraph naming the realized anchor as
   the open model question.
7. `docs/PROJ_PATH_SHAPE_GATE.md` section 9.2, for the prospect-row baseline it
   published (183 rows, 683.1 five-year WAR, 2026-09-18) and its pin that no arm of
   that gate touches a prospect row.
8. `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 2 (the label-move
   descriptives, including the hitter label sd of 7.47), part 3 (preconditions, none
   of which this gate waives), clause (h), clause (k) and part 6.

Nothing else about the outcome was read, because nothing else exists. In particular
NO per-cell statistic on any frame was computed for this document, and the design-day
illustrations of the tolerance in section 5.4 are arithmetic on the served table, not
a read of any label.

**Consequence of the prior, stated once.** Because the direction is published, this
gate is CONFIRMATORY. It protects itself three ways: the test is two-sided and the sign
is published; the verdict-bearing frame is the one the anchor was NOT fitted on
(section 4); and the tolerance is derived from a constant that predates the question
(section 5.4), not from the size of the published gap.

**Stop rule.** If section 2 (label and frame integrity) fails, no number is read. If
the power block of the artifact (section 8) is not on disk, no criterion below may be
read.

---

## 0. What is being fixed, measured first

Every row was read from the repository on 2026-09-23 at HEAD `b6b6f089`, and every
line number cited in this document was re-verified at that commit. The rows
marked PLAN WAS WRONG are why this document is not the one the owner's report implies.

| claim | the report said | read 2026-09-23 | verdict |
|---|---|---|---|
| the realized anchor is a table the code carries | implied | `fv_to_6yr_avg_war` (value_framework.py:621-636) reads `empirical_anchors.anchors` from the fitted file whenever `anchor_calibration.use_empirical` is true, which it is; the config table `{45: 0.38, 50: 0.70, 55: 0.95, 60: 1.45, 65: 1.95, 70: 2.60, 80: 3.80}` is the SEED, not what serves | **PLAN WAS WRONG.** The served table is `{45: 0.32, 50: 0.68, 55: 0.98, 60: 1.44, 65: 2.01, 70: 2.49, 80: 3.5}` plus the amended sub-45 knots |
| the anchor is our measurement | implied | `empirical_anchors.derive_empirical_war_anchors`: per tier, `val = (1 - w) * cohort_mean + w * public_reference`, `w = 0.5` at n >= 40 rising to 0.95 as n falls to 0; pure reference where n = 0 (FV 80). Diagnostics on disk: 45 n 1417 emp 0.132 ref 0.50; 50 n 337 emp 0.51 ref 0.85; 55 n 122 emp 0.817 ref 1.15; 60 n 50 emp 1.384 ref 1.50; 65 n 19 emp 2.512 ref 1.80 w 0.71; 70 n 8 emp 2.913 ref 2.40 w 0.82; 80 n 0 ref 3.50 | **HALF ours, half an Edwards-implied public reference.** Above FV 60 it is mostly the reference |
| the anchor's cohort is the resolved pool | implied | `empirical_anchors._cohort`: every player with ANY snapshot dated inside `[reference_year - 12, reference_year - 6]` = [2014, 2020]; his FV is the MEAN of every window snapshot; his label is the first six `career_war` seasons with NO censoring rule; the tier is `round(fv / 5) * 5` (Python banker's rounding sends 47.5 to 50) | the fit frame is a different conditioning variable from the one the anchor is applied to (design audit F08 (d)), and it is in-sample for every player listed 2014-2020. Section 4 is built on this row |
| the anchor moves only when someone changes it | implied | it is re-derived by `value_framework.py --fit` (step J of the fWAR epoch runbook), and `reference_year` defaults to the CURRENT year, so a `--fit` run in 2027 slides the window to [2015, 2021] by itself. Rebuilds read the committed fitted file and do not re-derive | the served object is pinned by the fitted file's `generated_at` and `cohort_window`, which the artifact records (section 15) |
| the anchor is per side | implied by "per side" in the ask | `fv_to_6yr_avg_war(fv)` takes no role. `_fv_war_scale(fv_half, role)` reconciles each role's bucket mixture to the SAME anchor, so `expected_six_year_avg_war(fv, hit)` and `expected_six_year_avg_war(fv, pit)` both equal the anchor at every FV by construction, to within the 0.5-FV cache rounding of `_fv_war_scale` (`_war_anchor_scale_for` is 1.0 for both roles) | **the anchor is side-pooled.** A per-side verdict would adjudicate a quantity the served object does not represent, and the side split was already registered a NULL against a side-label-permuted control (`docs/efv-2026-07-30/FV_OUTCOME_CURVES_GATE.md`, owner's pooled choice). Per side is REPORTED here, never adjudicated (section 7) |
| the sub-45 knots are the same object | implied | `anchors_provenance`: FV 35 and 40 were RE-MEASURED 2026-09-04 on "the resolved matrix pool, both sides, target_censored over 6" (FV35 0.0069 CI95 [0.0012, 0.0149] n 704; FV40 0.0710 CI95 [0.0530, 0.0906] n 1201), unblended; 20/25/30 are an extrapolation ramp; "45 through 80 are the epoch refit's own output and are not touched here" | **the sub-45 knots are already as-of-frame measurements** on exactly this gate's frame and are in-sample there. They are OUT of this gate (section 5.1) |
| for FV 62 the realized anchor works out to 1.55 WAR a season | commit `c5167587` | linear interpolation of the served table between 60 (1.44) and 65 (2.01) at 61.9 is 1.66, which is arithmetic on the published table. The commit's 1.55 is the five-year mean of the served `war` path, which is the anchor run through `_bucket_season_wars` (trajectory shape [0.80, 0.95, 1.05, 1.10, 1.10, 1.00] and age placement), not the anchor itself | the two figures are on different bases. The artifact publishes, for the named row, the served anchor at his FV BESIDE the path mean, so the reconciliation is done by code and not by a reader (section 15). Nothing about the row is adjudicated |
| the prime anchor is a candidate for the same test | implied by "both paths" | `fv_to_prime_war` is a hand table (`{45: 1.1, 50: 1.7, 55: 2.3, 60: 3.0, 65: 3.8, 70: 4.7, 80: 6.5}`), display-only, estimating peak-season WAR IF the prospect sticks (the industry's Quantity A). The realized anchor estimates the bust-inclusive six-year mean (Quantity B). `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` records that A runs 2x B at FV 50 and 3x at 40-45 | **a 2.05x prime-to-realized ratio at FV 62 (3.17 / 1.55) is the EXPECTED relationship between the two quantities, not evidence about either.** The prime table is out of scope; Z3 measures it through `tools/efv_peak_war_lab.py` under its own registration |
| P(bucket given FV) is part of the reconciliation under test | the ask names it | `p_bucket_given_fv` is a proportional-odds fit whose only training rows are the Clemens 2025 published tables (training n 678 hit / 437 pit); the bucket LEVELS are `midpoint_war` shape times k(FV), and k(FV) is whatever makes the mixture reconcile to the anchor. P(bust) is therefore Clemens's and independent of the anchor | the mixture's SHAPE (F07) and its LEVEL (F08) are separable, and this gate tests the level only. Section 3 says what that means for the owner's number |
| every priced number sits on the realized anchor | the ask | consumers read through `_fv_war_scale`: `surplus_value_mm`, `expected_surplus_usd`, `point_estimate_surplus_usd`, `sv_distribution`, `sv_draws`, `sv_credible_interval`, `debuted_player_value` (bucket levels of the prior), `expected_war` and `wag` (through `survivor_expected_war`), `expected_six_year_avg_war`, `realized_implied_fv` (the `_odds_grade` inverse). Callers: `proj_export._prospect_rows`, `efv_score`, `efv_export`, `efv_ungraded`, `bayes_trade_value`, `mlb_trade_lookup`, `storage` (farm and org surplus leaves, WAG), `comps_engine`, `farm_grade_backtest`, `fa_market` and `bayes_trade_value` (each imports `fv_to_6yr_avg_war` and never calls it), `backtest`. Direct callers of the anchor function itself: `comps_engine.py:164`, `efv_score.py:439` and `:1896`, `farm_grade_backtest.py:165`, `tools/fv_outcome_curves_lab.py:487`. The glossary is NOT on this list; see the next row | CONFIRMED. Section 13 names them with bands |
| the glossary prints the served anchor | implied by "every priced number" | `assets/glossary.js:1908`, `:1993` and `:2203` read `window.VALUE_FRAMEWORK.fv_to_6yr_avg_war`, the emitted snapshot `data/value_framework.{json,js}`. The emitter (`value_framework.py:3962`) writes `cfg["fv_to_6yr_avg_war"]`, the config SEED, so the committed snapshot carries `{35: 0.12, 40: 0.22, 45: 0.38, 50: 0.7, 55: 0.95, 60: 1.45, 65: 1.95, 70: 2.6, 80: 3.8}` while the served anchor is `{45: 0.32, ...}`. Only `:2226` (the sub-45 block) reads `fitted.empirical_anchors` | **PRE-EXISTING DISCREPANCY, recorded here as a read with no disposition.** The glossary's printed FV-to-WAR table is the seed, not what prices, and has been since the empirical anchors first served. This gate does not adjudicate it and does not repair it in advance of the verdict; the flip commit of 10.2 repoints the emitter (12.1, 12.2), and until then the discrepancy stands as disclosed here |
| the eFV GRADE sits on the realized anchor | not claimed | `outcome_implied_fv` inverts the POOLED OUTCOME CURVE (`curve_hash 1f3fa0a970bd`, named by `storage.BOARD_BASIS_FINGERPRINT`), not the anchor. `_odds_grade` inverts the anchor and keys star odds and the served surplus, and is exported for display only (owner decision S-3) | **the board grade and rank do not move under any outcome of this gate**, and section 13.2 asserts it |
| the pooled outcome curve already answers the question | not claimed | it publishes E[first-6yr total label WAR given as-of consensus FV] at 2.5-FV knots with the Clemens 2026 prior shrunk in at `K/(K + n)`, K = 30; `w_prior` is 0.112 at 45, 0.199 at 50, 0.286 at 55, 0.588 at 60, 0.732 at 65. From 57.5 up "those knots are the Clemens 2026 table, not our measurement" (its own `top_end_is_prior`) | it is the closest published object to this estimand and it is a PRIOR here (G-0.1 item 2). It is side-pooled, prior-shrunk, on the eWAR v2 label, and it carries no bootstrap on the raw cell mean. This gate reads the raw rows it was built from, on the fWAR label, at the anchor's own knots, with the anchor's own cells |

### 0a. What this gate does NOT do, so the absence is a decision

- It does not fit a candidate anchor before the verdict. A candidate exists only
  under the MISCALIBRATED outcome (section 11), and it is fitted after the verdict is
  written into the artifact.
- It does not read the survivor level or the bust rate of any cell. Those are the
  shape question (F07) and the BUST2 lane, each with its own registration; reading
  them here would be a look on their frame before their section exists.
- It does not test the prime anchor, the dollar map (`calibration.version`
  `isotonic-real-v6-evframe-2026-07-31`, gated by `docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md`),
  the arbitration ladder, `P(bucket given FV)`, the reliever haircut, the trajectory
  shape or the aging placement.
- It does not run on the eWAR v2 label. Section 14 says why.

---

## 1. The estimand

> For a prospect who, at a pre-outcome decision point (the eFV matrix's as-of
> vintage: the latest consensus point strictly before his debut date, or his final
> prospect point if he never debuted), carried a raw consensus FV `fv` in cell `C`,
> the served realized anchor `fv_to_6yr_avg_war(fv)` is the framework's estimate of
>
> `E[ (sum of his first six major-league-season WAR on the label series) / 6  |  fv ]`,
>
> BUST-INCLUSIVE (a prospect who never reaches the majors contributes 0), side-pooled,
> on the calendar window `debut_year .. debut_year + 5` (or the service-aligned window
> if arm A1 ships in the fWAR epoch; whichever definition `efv_dataset._label_6yr`
> serves at the look is the one this gate reads and records).
>
> This gate estimates, per cell `C`, the conditional mean of the per-row residual
>
> `D_i = label_i / 6 - fv_to_6yr_avg_war(fv_i)`
>
> in WAR per season, over the resolved rows of `C`, and asks whether `|E[D_C]|` lies
> inside a tolerance fixed in section 5.4.
>
> It does NOT estimate: the survivor (non-bust) level of any cell; the bust rate of
> any cell; a per-side anchor (reported, never adjudicated); the prime anchor; the
> surplus dollar calibration that sits on top of the anchor; anything about any
> individual prospect's path; or what a prospect "should" be worth.
>
> The label is the epoch label: published fWAR frozen per season, adopted wholesale
> with FanGraphs' conventions (the FWAR_LABEL_EPOCH_GATE part 1 disclosure), read
> from the eFV matrices at `RESOLVED_THROUGH = 2026`. Every number this gate reports
> is a statement about that definition of WAR and no other, and clause (l) of the
> epoch gate binds every sentence of copy that results.

Units, stated so nobody divides twice: the anchor is WAR PER SEASON averaged over six
seasons; the matrix label `target_censored` is a SIX-SEASON TOTAL; `D_i` divides the
label by six once. Both are bust-inclusive. Both are side-pooled at the point of
comparison.

---

## 2. Label and frame integrity gates. Nothing is read if these fail.

- **L1 the label exists.** The look requires the fWAR epoch's step F to have run
  (matrices on `fwar` at `RESOLVED_THROUGH = 2026`) and step J to have run (the
  anchor refit on the same label). The artifact records the matrices' `war_basis`
  stamp, `RESOLVED_THROUGH`, the label-window rule in force (`SERVICE_ALIGNED_WINDOW`
  and `_SERVICE_YEAR_CUT_MMDD`), and the fitted file's `empirical_anchors.generated_at`
  and `cohort_window`. A run that cannot name all five is void.
- **L2 identity.** The lab reuses `tools/fv_outcome_curves_lab.py`'s pool loader
  and its identity checks unchanged (`target_censored_mismatches`,
  `consensus_fv_raw_mismatches`, `censored_flag_mismatches`,
  `cross_side_key_overlap`). Any mismatch count above the pooled curve's own
  published counts on the same label is reported and the run stops. Cross-side key
  overlap must be 0, or the bootstrap in 5.3 is not player-clustered and the run is
  void.
- **L3 resolution.** Only rows with `censored == False` enter any cell. At
  `RESOLVED_THROUGH = 2026` that is every debut cohort through 2021 on the calendar
  window (2021 + 5 = 2026), plus busts the matrix marks resolved. No tail-projected
  label enters: the flat-rate projection is measured to understate the six-year
  total (`efv_dataset` docstring, Lane B1), and the estimand is a level.
- **L4 the zero convention.** A never-debuted prospect is a 0, not a missing value,
  and a debuted prospect's absent season inside his window is a 0. Stated beside
  every cell mean.
- **L5 revision leakage, disclosed.** The label is frozen per season by the epoch
  (E3), so unlike the projections corpus it does not carry a 2026 value onto a 2012
  season. If the frozen vintage is missing for any season inside a row's window, the
  row is dropped and counted, never filled from a live pull.
- **L6 the anchor cohort is reproducible.** `empirical_anchors._cohort(db, y0, y1)`
  is called at scoring time with the `cohort_window` recorded in the fitted file,
  and the returned key set is what section 4 partitions on. If the DB on disk does
  not reproduce `n_cohort` within 1 percent of the fitted file's value, the partition
  is not the fit frame and the run stops.
- **L7 no projection input.** The artifact carries no field read from
  `data/mlb_projections.json`, no `proj_ml` output and no `warChamp`. Pinned. This is
  what keeps section 4.3's disjointness argument mechanical rather than asserted.

---

## 3. Which defect the owner's number can be, and which one this gate can see

The owner's row reads: eFV 61.9, P(bust) 5 percent, expected 7.5 WAR over five years,
prime 15.4. Two different defects produce a row that looks like that, and they have
different fixes. Naming them before the read is the point of this section.

**F08, the LEVEL.** The bust-inclusive mean the anchor assigns at FV 62 is too low
against what graduated prospects of that FV delivered. If so, the expected path is
low for everyone at that FV, the surplus dollar is low for everyone at that FV, and
the repair is a level correction to the anchor. This is what this gate tests.

**F07, the SHAPE.** The anchor is right, but the mixture that produces it is
population-inconsistent: P(bust) comes from the Clemens 2025 tables (a population
with roughly half our bust rate at the fringe: Clemens 51 to 53 percent at FV 45
against the anchor cohort's own 80.8 percent), while E[WAR] comes from our
bust-inclusive anchor, so the survivors are forced DOWN to make the mixture
reconcile (k(FV) 0.535 at hitter 60; the star bucket 2.67 WAR against its 4.0 band
floor; F07 (c), verbatim in G-0.1). A row that shows a 5 percent bust probability
beside a 1.55 WAR-per-season expectation is exactly what that inconsistency looks
like, and no level correction fixes it: raise the anchor and the survivors rise with
it, but the 5 percent stays Clemens's.

**What this gate can and cannot say about the row.**

- A CONFIRMED verdict at the cells that cover FV 62 means the EXPECTED VALUE the board
  prints is the calibrated bust-inclusive mean, and the remaining oddity of the row
  (a low bust probability beside a low expectation) is F07's, which has its own
  registration (design audit F07 step 2: one registration replacing
  `{P(b given FV), k(FV), band priors}` with a population-consistent object fitted on
  the resolved frame). CONFIRMED here closes the display debt of section 10.1 and
  opens nothing.
- A MISCALIBRATED verdict means the level is wrong and section 11's lever exists. It
  says nothing about the shape, and the artifact says so beside the verdict.
- This gate does NOT read the survivor mean or the bust rate of any cell, because
  those reads are F07's and BUST2's first looks. Refusing that read costs this gate
  the ability to say which of the two defects the owner is looking at when the level
  is CONFIRMED. That is the price of not spending someone else's look, and it is
  paid rather than argued around.

---

## 4. Frames, and how they stay disjoint

### 4.1 The two frames, cut by the anchor's own fit cohort

The served anchor was fitted, for half its weight, on the cohort
`empirical_anchors._cohort(db, y0, y1)`: every player with any snapshot dated in
`[y0, y1]` (the fitted file's `cohort_window`, `[2014, 2020]` at the 2026-09-04 fit and
expected unchanged at the step J refit because `reference_year` will still read 2026).
That is the fit half, and the house rule is that the fit half is never graded.

The resolved matrix pool (L3) is therefore partitioned by player key against that
cohort, MECHANICALLY, at scoring time:

| frame | rows | may it carry a verdict | what it can return |
|---|---|---|---|
| **H (holdout)** | resolved rows whose `player_key` is NOT in the anchor's fit cohort | **yes** | CONFIRMED, MISCALIBRATED, UNDECIDED, UNPOWERED per cell |
| **S (shared)** | resolved rows whose `player_key` IS in the anchor's fit cohort | **veto only** | MISCALIBRATED, or nothing. It can never return CONFIRMED |
| **H + S (pooled, read)** | every resolved row | **no** | reported per cell as a descriptive, labelled READ |

**Why S is veto-only and not excluded.** The fitted half of the anchor tracks its own
cohort mean under its own binning (multi-year-averaged snapshot FV, banker's rounding
to tier). Under this gate's binning (as-of consensus FV, half-width 2.5) the same
players are re-binned, so an S-frame read is not a pure re-read of the fit; F08 (d)
records that the two binnings put FV 45 at 0.126 and 0.378 on the same players. But
half the anchor's weight is a mean of these very labels, so agreement on S is biased
toward agreement and is not evidence; disagreement on S is disagreement DESPITE an
in-sample advantage and is evidence in the conservative direction. A frame that can
only fail the anchor cannot be gamed into confirming it. The same asymmetry the shape
gate registered for its Tier-2 frame (4.6a there).

**What H is expected to contain, pre-registered so the count cannot surprise anyone
into moving it.** Players with no snapshot in 2014-2020 are, in the main, the
2011-2013 decision cohorts who exhausted prospect status before 2014, plus any
resolved row first listed in 2021 or later (a bust marked resolved by inactivity;
these are expected to be few and nearly all at the fringe). H is expected to be
POWERED (section 5.2) at FV 45 and 50, marginal at 55, and UNPOWERED at 60 and 65+.

**What H is made of, disclosed before the read.** The config's own note
(`anchor_calibration`, dated 2026-06-21) records that the cohort window was widened to
12 years after "the MLB Pipeline 2011-2016 backfill" added about 1,000 resolved
players, and `efv_dataset.DEBUT_YEARS` starts at 2011. Rows with no snapshot in
2014-2020 are therefore, in the main, SINGLE-SOURCE rows whose only FV is
`fv_mlb_pipeline`, and F08 (d), quoted in G-0.1, records that the two sources sit on
different FV scales. H's verdict is thus a verdict on a largely Pipeline-scale FV,
while the anchor is applied today to a multi-source consensus. A source-scale offset
is a confound H cannot separate from anchor miscalibration, and this document says so
before the read rather than after. Two consequences are pre-registered: (i) the
artifact publishes, per cell and frame, the SOURCE CENSUS: mean `n_sources`, the share
of rows with `n_sources == 1`, and the share whose only source is the Pipeline
(`fv_fangraphs` null and `fv_mlb_pipeline` present, both fields of the matrix row as
`efv_dataset` writes them); (ii) the concordance rule of 6.2 applies, under which a
MISCALIBRATED on H cannot ship a lever on its own where S, powered at the same cell,
reads the opposite sign.
**That expectation is the honest reading of the design, and it is why the owner's
question at FV 62 is expected to resolve, if it resolves at all, on the S-frame veto
and not on a CONFIRMED.** The artifact publishes H's decision-year census and per-cell
n beside every verdict.

### 4.2 The resolved-cohort frame, in debut years

At the look, `RESOLVED_THROUGH = 2026` (epoch decision O2). On the calendar window a
debut cohort is fully resolved when `debut_year + 5 <= 2026`, so **debut years 2011
through 2021 are fully resolved** and 2022 onward are censored and excluded (L3). If
arm A1 (the service-aligned window) ships in the epoch, a post-cut 2021 debut takes
the window 2022 to 2027 and is CENSORED at this look; the artifact counts those rows
and they are excluded, never tail-projected. Busts resolve by the matrix's own
`censored` flag. Today, before the epoch, the resolved set would be debut years 2011
through 2020; the gate does not run there (section 14).

### 4.3 Overlap with `docs/PROJ_PATH_SHAPE_GATE.md`, stated and defended

That gate cut label seasons 2015-2025 as READ frames (its G-0.1: "every label season
from 2015 through 2025 has already been scored on the shipped challenger"), holds
2012-2014 as its GATE frame, 2008-2011 as DEV and 2026 as CONFIRM. This gate's rows
carry WAR from seasons 2011 through 2026 (H mostly 2011-2019; S 2014-2026). **The
calendar overlap is total, and no season is excluded on that account, for four reasons
that are each mechanical:**

1. That gate defines a burn as "a `proj_lgbm` challenger scored on that base"; a
   burned season is one on which a proj_lgbm CANDIDATE has been read. This gate
   scores no proj_lgbm quantity, reads no `proj_ml` bundle, and reads no field of
   `data/mlb_projections.json` (L7, pinned). Nothing it does can be a read of a
   proj_lgbm candidate on any season.
2. The estimands share nothing. That gate estimates per-player conditional quantiles
   of an MLB player's WAR at horizons 1-5 from a base season, on the veteran
   population. This gate estimates one population-level conditional mean over
   pre-debut prospects' first six seasons, on a pre-debut population, for a table in
   a different module. A season's WAR value is an INPUT to both, the way a batting
   line is an input to both; sharing an input is not sharing a frame.
3. The models are disjoint in code and that gate already pins it: its 9.2 records
   that `_prospect_rows` prices through `vf` and never calls `proj_ml`, so "the 183
   prospect rows and their 683.1 five-year WAR sum do not move under either arm".
   The reverse holds by L7 here.
4. This gate does not read a season "as a label season of base B". It reads the eFV
   matrix's `target_censored`, the label object the fWAR epoch gate governs, which is
   the object the next section addresses.

So the overlap is admissible because it is the same season's WAR entering a
different estimand for a different model, and this document says so rather than
claiming the seasons are fresh. They are not fresh. They are simply not that gate's.

### 4.4 The fWAR label epoch gate: what it reserved, and what this gate spends

The label pool is the platform's scarcest resource, and the epoch gate reserves
specific reads of it: clause (a)'s same-label MARGINS on the `SCORED_YEARS` folds,
clause (b)'s cross-label matrix, clause (d)'s TOST on the margin delta, clause (e)'s
controls, and clause (i)'s leave-one-out arms. Each is a read of an eFV PREDICTION
against the label, or of the consensus RANK against the label.

This gate reads none of them. It reads no eFV prediction, no consensus rank, no
fold, no cross-label cell and no arm. What it reads is E[label given as-of consensus
FV] at the anchor's knots, which is the SAME read the epoch's own step I takes when it
rebuilds the pooled outcome curve on the fWAR label, on the same rows, at finer knots,
with a prior shrunk in. This gate takes that read AFTER step I and after the epoch's
part 9 records its step Z entry (section 14), on a different statistic (raw cell mean
of a residual against a served table, with a bootstrap), so it opens no fold, and it
cannot be a look inside the epoch because it happens after the epoch has recorded its
own.

Under the MISCALIBRATED outcome, the lever (section 11) is fitted on the same rows
step J already fits the incumbent on, by a different rule; that spends no label look
step J does not already spend. Its out-of-fold check is a forward-chained fold
structure over rows this gate has already read, and its one fresh read is the 2022
decision cohort at the next clock, taken after the 2027 epoch's own read of that
cohort (11.4); neither is a read the 2026 epoch reserved.

What this gate does NOT do is ride the epoch. Clause (h) bars "any correction family"
inside it and part 6's may-not-ride list is frozen; the lever is a correction to the
anchor and waits for its own registration, which is this one, and this one waits for
the epoch to close.

---

## 5. Cells, floors, statistic, bootstrap, tolerance

### 5.1 Cells

Five cells on the raw as-of consensus FV, matching the anchor's own tier knots and
its own half-grade width:

| cell | FV range | anchor knot it tests |
|---|---|---|
| 45 | [42.5, 47.5) | 45 |
| 50 | [47.5, 52.5) | 50 |
| 55 | [52.5, 57.5) | 55 |
| 60 | [57.5, 62.5) | 60 |
| 65+ | [62.5, 80] | 65 (and 70, 80 by extension; reported as one cell because the pooled curve's own `n_cell` from 62.5 up reads 2 / 11 / 2 / 1 / 0 / 0) |

The sub-45 knots are OUT: FV 35 and 40 were re-measured on this exact frame on
2026-09-04 (section 0) and are in-sample here by construction; 20/25/30 are an
extrapolation ramp under them and are owned by that amendment's tripwire
(`test_empirical_anchors.test_low_end_anchors_are_present_and_measured`).

Each row's assigned level is the anchor at ITS OWN FV, `fv_to_6yr_avg_war(fv_i)`,
never the knot value; the artifact publishes both the cell mean of the assigned level
and the knot value so within-cell FV spread is visible.

### 5.2 Sample floors

- A cell carries a verdict only with **n >= 40 resolved rows** on the frame being
  read. 40 is `anchor_calibration.min_n_robust`, the anchor's own declared floor for
  trusting a tier's cohort mean, reused rather than invented. Below 40 the cell reads
  **UNPOWERED** and publishes its n and its point estimate without an interval.
- A per-side reading (section 7) needs n >= 40 on that side in that cell for an
  interval; otherwise counts only.
- Floors are applied per frame: a cell can be powered on S and unpowered on H, and
  the artifact says which.

### 5.3 The statistic and its bootstrap

Per cell and frame:

- `D_C` = mean over rows of `label_i / 6 - anchor(fv_i)`, WAR per season. The
  headline. Signed: positive means the realized level sits ABOVE the anchor (the
  owner's "calibrated low").
- `R_C` = mean(label_i / 6) / mean(anchor(fv_i)), the ratio, for readability.
  Reported, never adjudicated.
- Interval: **percentile bootstrap over rows, B = 2000, seed 20260923, two-sided 90
  percent**, so each one-sided bound sits at 95 percent and the equivalence reading
  is a TOST at alpha 0.05. Rows are players (L2 asserts cross-side overlap is 0, so
  row and player clustering coincide, as the pooled curve lab asserts for itself).
  Nothing is refit per draw because nothing is fitted; the anchor is a fixed table.
- The residual sd per cell and the resulting standard error are published, and so is
  the MDE (section 8).

### 5.4 The tolerance, and where it comes from

The equivalence margin at cell `C` is the anchor's own HALF-GRADE INCREMENT at that
knot:

> `m_C = ( anchor(k_C + 2.5) - anchor(k_C - 2.5) ) / 2`

evaluated on the served table at the look (for the 65+ cell, at k = 65).

The object under test sets its own tolerance through this formula: step J refits the
table before the look, a steeper refit widens `m_C`, a flatter one narrows it. The
formula is fixed, so that is not post hoc, but it is a degree of freedom the fitter
controls, and it is pinned three ways. The tool computes the look-day `m_C` from the
fitted file INSIDE THE POWER BLOCK, before any cell is read (section 8). The artifact
publishes the design-day values in the table below beside the look-day values and
their ratio. And a look-day `m_C` outside **0.75x to 1.25x** of the design-day figure
at any cell requires an amendment filed BEFORE the look under the 5c form, naming the
refit that moved it; without that amendment the look is not taken.

In words: the
anchor is CONFIRMED at a cell when the realized level is within the amount the anchor
itself moves for one "+" step of FV, which is the smallest grade distinction the
industry scale publishes and the smallest distinction a consensus FV carries. A level
error smaller than the input's own quantum is not a level error the grade can express.

This is derived from the FV scale, which predates the question, and it agrees in size
with the constant the engine already documents for its own reconciliation
(`anchor_calibration.reconcile_tol: 0.15` WAR per season "at the named FVs" 50/55/60:
0.15 is 15 percent of the FV 55 anchor). It is NOT derived from the published gap in
G-0.1. A reader who wants to check that can set items 1 and 2 of G-0.1 against the
table below; this document does not do that comparison, because it registers a
tolerance and does not read a result.

Design-day illustration, arithmetic on the served 2026-09-04 table (the values that
bind are recomputed on the table served at the look, after step J):

| cell | anchor(k - 2.5) | anchor(k + 2.5) | m_C (WAR/season) | m_C relative to the knot |
|---|---|---|---|---|
| 45 | 0.196 | 0.500 | 0.152 | 47 percent |
| 50 | 0.500 | 0.830 | 0.165 | 24 percent |
| 55 | 0.830 | 1.210 | 0.190 | 19 percent |
| 60 | 1.210 | 1.725 | 0.258 | 18 percent |
| 65+ | 1.725 | 2.250 | 0.263 | 13 percent |

The 45 cell's margin is wide in relative terms because the anchor's slope out of the
fringe is steep; that is a fact about the anchor's shape and is disclosed, not
corrected. A reader who thinks 47 percent is too loose at 45 should note that the
cell's expected n makes a far narrower margin resolvable, and that the gate reports
`R_C` and the interval in full, so the looseness costs nothing but the label on the
verdict.

---

## 6. The decision rule, and the multiplicity family

### 6.1 Per cell, per frame

| disposition | criterion |
|---|---|
| **CONFIRMED** | n >= 40 and the 90 percent interval on `D_C` lies entirely inside `[-m_C, +m_C]` |
| **MISCALIBRATED** | n >= 40 and the interval lies entirely outside the band on one side, after the Holm step in 6.3; the sign is published |
| **UNDECIDED** | n >= 40 and neither |
| **UNPOWERED** | n < 40, or the cell's MDE95 (section 8: 1.645 times the bootstrap standard error of `D_C`, the sd of the B draws, never the residual sd of the rows) exceeds `2 * m_C`, in which case the cell is labelled UNDECIDED_UNDERPOWERED and counts as unpowered for 6.2 |

### 6.2 The verdict on the anchor

- **MISCALIBRATED** if ANY powered cell on H is MISCALIBRATED under the Holm family
  and survives the concordance rule below, OR any powered cell on S is MISCALIBRATED
  under its own Holm family. Both frames can fail the anchor; S is expected to be the
  one that can at 60 and 65+.
- **Concordance rule, for the source-scale confound of 4.1.** A cell that reads
  MISCALIBRATED on H, where S is ALSO powered at that cell and S's 90 percent interval
  on `D_C` lies entirely on the opposite side of zero from H's point estimate `d_C`,
  reads **UNDECIDED** at that cell, with both frames' numbers published and the cell
  labelled `SOURCE_SCALE_SUSPECT`. The rule can only remove a cell from the
  MISCALIBRATED set; it can never place one in the CONFIRMED set, because CONFIRMED
  still requires H's interval inside the band. A MISCALIBRATED on S is untouched by it
  (S carries no source-scale confound: its rows are the consensus-era cohort the anchor
  is applied to). So a Pipeline-scale artefact cannot ship a lever on its own, and an S
  veto cannot be silenced by H.
- **CONFIRMED** if EVERY powered cell on H is CONFIRMED, no powered cell on S is
  MISCALIBRATED, AND the powered cells on H include at least 45, 50 and 55. The last
  condition exists because the prospect board is about 98 percent sub-50 FV
  (`docs/ARBITRATION_GATE.md` 0a) and a confirmation that skips the cells carrying
  the priced rows is not a confirmation of the priced anchor.
- **UNDECIDED** otherwise, with every cell's disposition published.

CONFIRMED is an intersection over cells (every one inside), which needs no
multiplicity correction. MISCALIBRATED is a union (any one outside), which does. The
asymmetry is deliberate and is the standard TOST-versus-difference structure.

### 6.3 The multiplicity family, declared before any number is read

- **Family H:** the powered cells on frame H, at most five. **Family S:** the powered
  cells on frame S, at most five. Two families, each under **Holm at family alpha
  0.10**, matching the two-sided 90 percent interval so that a single powered cell
  reduces to "the interval excludes the band".
- Per-cell relevant-difference p-value: if the point estimate `d_C > +m_C`, `p_C =
  2 * (fraction of bootstrap draws with D*_C <= +m_C)`; if `d_C < -m_C`, `p_C = 2 *
  (fraction with D*_C >= -m_C)`; otherwise `p_C = 1`. Holm step-down over the family
  on those p-values.
- The per-side layer (section 7) carries no verdict and is in no family. The pooled
  H + S read carries no verdict and is in no family. The lever's out-of-fold check and
  its one fresh read (section 11) carry their own registration and family.
- **`k` is published as the count of powered cells actually in each family, and a
  cell with `d_C` on the wrong side of the band reads UNDECIDED whatever its `p_C`.**
  The artifact records `k`, the ordered p-values and the step at which Holm stopped.
- **The combined rate, stated as a number.** Two families each at 0.10 give a
  family-wise false-MISCALIBRATED rate across H and S of at most `1 - 0.9^2 = 0.19`.
  That is accepted and not hidden: a false MISCALIBRATED ships nothing served (10.2),
  the lever it opens must pass its own out-of-fold check (11.4) before it exists
  behind a flag, and the concordance rule of 6.2 removes the H-only case that the
  confound of 4.1 makes the most likely false positive. The rate for a false CONFIRMED
  is the TOST's own 0.05 per cell and is not inflated by the union, because CONFIRMED
  is an intersection.

### 6.4 The one-parameter reading, registered so it cannot be improvised

If MISCALIBRATED, the artifact reports whether the powered cells' residuals are
consistent with a single multiplicative LEVEL error (all `R_C` inside one another's
intervals) or with a SHAPE error (they are not). This is a descriptive that section 11
turns into a criterion for the lever's form (the one-parameter twin). It is not part of
the verdict on the anchor.

---

## 7. Per side: reported, never adjudicated

For every cell and frame the artifact reports `D_C`, `R_C`, n and (at n >= 40 per
side) the 90 percent interval, separately for hitters and pitchers, using
`efv_dataset._side_match` as the resolver and the matrix's own side.

Pre-registered reading, fixed here:

- The served anchor is side-pooled by construction (section 0, row 5). A side whose
  interval sits outside the band while the pooled cell is CONFIRMED is NOT a
  miscalibration of the anchor; it is the known finding that consensus FV is not
  cross-side comparable in realized WAR (`docs/efv-2026-07-30/CROSS_SIDE_WAR_FINDING.md`:
  hitters realize 2.21x pitchers at consensus 55+, inverting below 45), which Phase 1
  registered as a NULL against a side-label-permuted control and the owner resolved
  by choosing the pooled curve. That question is closed on this frame and this gate
  does not reopen it.
- The per-side numbers are published so that a later per-side registration, if the
  owner ever wants one, starts from a disclosed read and not from a fresh one.
- No copy may cite a per-side number from this artifact as evidence about the
  anchor.

---

## 8. Power, published before any criterion is read

The lab writes a `power` block BEFORE the `cells` block, and `test_prospect_anchor_gate.py`
pins the order and the presence. Per cell and frame:

- the residual sd, n, and the standard error of `D_C`;
- **MDE95 = 1.645 times the bootstrap standard error of `D_C`**, the standard
  deviation of the B bootstrap draws of `D_C`, and NOT the residual sd of the rows,
  stated explicitly because the convention was implicit in this repository once and
  had to be recovered: the smallest `|E[D_C]|` the one-sided 95 percent bound would
  separate from the band edge. This is the MDE that 6.1's `2 * m_C` rule reads; read
  as the residual sd it would label every cell UNDECIDED_UNDERPOWERED, which is why
  the definition is spelled out here;
- the look-day `m_C` at every cell, computed from the fitted file on disk BEFORE any
  cell is read, beside the design-day value of 5.4 and the ratio between them (5.4's
  0.75x to 1.25x pin);
- the detection check: a design-matched simulation planting a residual of exactly
  `+m_C` at each powered cell with the cell's own residual sd and n, B = 1000, seed
  20260923; the fraction of simulated runs returning MISCALIBRATED is published, and
  a cell below 0.80 is labelled in the artifact as one where a MISCALIBRATED verdict
  would be a lucky read, without changing its disposition rule;
- a two-sided coverage check on the bootstrap interval itself, `n_check >= 200`, at
  the cell's n, because for an EQUIVALENCE verdict a too-NARROW interval is the
  permissive direction: it manufactures CONFIRMED. An over-wide interval manufactures
  UNDECIDED. The narrow direction is the one the check exists to catch.

Pre-registered expectation, so the reading cannot be argued after: on H, cells 60 and
65+ are expected to read UNPOWERED and cell 55 is expected to be marginal; on S, cell
60 is expected to be powered by n and unresolvable by MDE at the 5.4 margin unless the
residual is large. An UNDECIDED at 60 on S is the expected reading, not a
disappointment, and it is written as UNDECIDED and not rounded into anything.

---

## 9. What would falsify

Each is a claim someone has made or implied, and the reading that kills it.

1. **"The served realized anchor is the bust-inclusive first-six-season mean of
   graduated prospects at each FV."** Falsified by a MISCALIBRATED cell on H or on S.
2. **"The realized anchor is calibrated low"** (the owner's suspicion, 2026-09-23).
   Falsified by CONFIRMED, or by MISCALIBRATED with a NEGATIVE `D_C` at the cell in
   question. The sign is published so this can be read directly.
3. **F08's direction prior, "the resolved evidence points up at every knot 45-65."**
   Falsified by any powered cell whose interval lies below `+m_C`, or whose point
   estimate is negative.
4. **"The anchor's blend rule (a flat 0.5 toward the public reference) is
   shrinkage."** F08 (c) says it is not (`K/(K + n)` at n 1,415 would be 0.021). This
   gate does not test the rule; the lever in section 11 replaces it, and the lever's
   out-of-fold check and its one fresh read are what falsify the replacement.
5. **"A single scalar is enough"** (the level-not-shape reading of 6.4). Falsified by
   the one-parameter twin capturing under 75 percent of the lever's improvement
   (11.3).
6. **"The lever is a repair, not a refit to the noise of one cohort."** Falsified by
   the out-of-fold check on read rows, or by the one fresh read (the 2022 cohort, in
   2027), section 11.4.
7. **"The frames are disjoint."** Falsified mechanically if L6 finds the DB does not
   reproduce the fit cohort, or if any player key appears in both H and S; the test
   pins the partition.

---

## 10. What happens under each outcome, fixed in advance

### 10.1 CONFIRMED

Nothing moves. No flag is added, no table changes, no artifact regenerates, the
registry row `prospect_surplus` keeps its verdict. **The display debt closes**: the
open question that commit `c5167587` left ("if 7.5 over five years is still low for a
62-eFV shortstop ... the number to interrogate is the REALIZED anchor's calibration")
is answered in the accountability census with the cells, intervals and frame, and the
`/projections/` prospect sub-line's two anchors (expected on the realized level, prime
on the talent level) are recorded as two correct answers to two different questions.
The remaining oddity of the owner's row, if the owner still sees one, is routed to F07
by name (section 3) and this document says so in its results section.

**Reachability, stated so it cannot surprise the owner.** CONFIRMED requires H
powered at 45, 50 AND 55 (6.2), and 4.1 and section 8 both expect H to be MARGINAL
at 55. If H reads UNPOWERED at 55 on the day, CONFIRMED is structurally unreachable
at the 2026 look, the reachable verdict set is {MISCALIBRATED, UNDECIDED}, and the
display debt of `c5167587` cannot close before the 2027 re-registration (10.3). That
is the design and not a defect found on the day; the requirement is kept because a
confirmation of the anchor that skips the cell on which the priced board's top end
mostly sits would be a confirmation of something else.

Copy may say: "the expected path prices the bust-inclusive six-year mean, which the
resolved cohorts confirm within one grade step at FV 45 to 55". Copy may not say the
anchor is "accurate", "validated" above the cells that were powered, or anything about
FV 60 and up beyond the disposition those cells returned.

### 10.2 MISCALIBRATED

A recalibration lever is built as section 11 specifies, shipped behind
`SERVE_PROSPECT_ANCHOR_V2` defaulting to `False`, with its own out-of-fold check and
one fresh read (11.4). Until the
owner flips it, NOTHING served moves. The verdict, the cells and the sign are
published in the accountability census and in this gate's artifact. Whether the
served copy on the prospect sub-line discloses the open miscalibration before the flip
is the owner's call; the census disclosure is not.

The display debt does not close; it converts into a named, measured lever with a
flag, which is a different kind of debt from an open question.

### 10.3 UNDECIDED

Nothing moves. The display debt stays open. The question re-arms as a NEW
registration, disclosing this read, at the next resolution clock: when
`RESOLVED_THROUGH` advances to 2027 (the 2022 debut cohort resolves) and, if `--fit`
is run with `reference_year` 2027, the anchor's window slides to [2015, 2021], which
moves the 2014 cohort from S into H. The re-registration may not narrow the tolerance
or drop a cell that read UNDECIDED here. This includes the case of 10.1's reachability
note: an UNDECIDED produced because H was unpowered at 55 re-arms on the same terms,
and the window slide is what is expected to power it.

### 10.4 UNPOWERED at the cells the owner asked about

Expected at 60 and 65+ on H (section 4.1, section 8). Not a pass, not a failure. The
artifact prints the cell's n and point estimate, the S-frame disposition beside it,
and the sentence: "the resolved holdout carries too few prospects at this FV to
adjudicate the anchor there; the shared frame's reading is [disposition], which can
fail the anchor and cannot confirm it".

---

## 11. The lever, under MISCALIBRATED only

Nothing in this section exists until the verdict in 6.2 is written into the artifact.
A candidate anchor computed before that is an early look and voids the registration
(G-0).

### 11.1 Construction, following design audit F08 (e) as written

"Do not write a third estimator. Have one fitter own the estimand." The lever
therefore re-derives the anchor on the frame the anchor is APPLIED to, with the prior
the pooled curve already uses:

- rows: the resolved matrix pool, H + S, both sides, as-of `consensus_fv_raw`,
  `target_censored / 6`;
- per knot k in {45, 50, 55, 60, 65, 70}: the raw cell mean over `[k - 2.5, k + 2.5)`
  (the 70 cell runs to 80), shrunk toward the Clemens 2026 control-war prior in
  per-season units, side-averaged exactly as the pooled curve lab expresses it
  (`0.5 * (clemens_hit + clemens_pit)`, each with the lab's declared linear ramp below
  the table's bottom published row), with `K = 30` (the pooled curve's own `k_shrink`,
  reused so the lever introduces no free parameter);
- 80: the prior alone (no data, as today);
- 20 through 40: the amended sub-45 knots, carried byte for byte (the standing trap:
  `--fit` reverts them; the lever's tool writes a separate key and never calls `--fit`);
- monotone non-decreasing repair in FV, with the maximum repair move published (the
  pooled curve's was 0.4315 WAR over six years, that is 0.072 per season);
- rounded to three decimals, not two (the `round(v, 2)` collapse is one of the
  provenance string's four named defects);
- written to `data/value_framework_fitted.json` under a NEW key,
  `empirical_anchors_v2`, with `generated_at`, the seed, the label stamp, the row
  count per knot and the prior value per knot beside the fitted value.

### 11.2 Refusal caps, applied before the out-of-fold check

- Any knot 45 through 70 whose v2 value differs from the served value by a factor
  outside **[0.5, 2.0]** REFUSES the lever outright. A correction of 2x or more is the
  size of the Quantity A / Quantity B trap (`docs/reference/FANGRAPHS_FV_FRAMEWORK.md`:
  feeding the survivor quantity into the bust-inclusive slot overprices about 2x at
  50 and 3x at 40-45), and a lever that large is evidence the frame is measuring the
  wrong quantity, not evidence the anchor is wrong by that much. Refused, recorded,
  not shipped, and the question goes back to the owner with the numbers.
- A monotone repair moving any knot by more than **0.15 WAR per season** refuses the
  lever: the raw cells then disagree with each other by more than the tolerance and
  a monotone table fitted through them is a shape claim this gate did not register.

### 11.3 The one-parameter twin

The best single global scalar `s` on the served table (`s * anchor_incumbent(fv)`,
applied to the knots 45 and up), fitted on the same rows by cell-n-weighted least
squares against the raw cell means, is scored beside v2 on the same loss. **If the
scalar captures at least 75 percent of v2's improvement over the served table, the
lever ships as the scalar**, and the six-knot table is NOT shipped. The B2 rule of
`docs/ARBITRATION_GATE.md`, reused verbatim: a level correction ships as one parameter.

**One read site, whichever form wins.** The scalar is NOT shipped through the config's
`war_anchor_scale`. In code that multiplier is applied only inside `_fv_war_scale`
(value_framework.py:981) and never inside `fv_to_6yr_avg_war`, so a scalar shipped
there would move every mixture consumer while the direct readers of the anchor
(`comps_engine.py:164`, `efv_score.py:439` and `:1896`, `farm_grade_backtest.py:165`,
the `--emit-snapshots` table, `tools/fv_outcome_curves_lab.py:487`'s
`shipped_fv_to_6yr_avg_war` candidate) kept the old level; `expected_six_year_avg_war(fv)`
would no longer equal `fv_to_6yr_avg_war(fv)`, section 0 row 5's construction would
break, and the SERVE flag would gate a different consumer set depending on which form
won. `war_anchor_scale` therefore stays exactly what its docstring says it is, the
transient diagnostic of `fit_tier_reconciliation`, and the pins that guard that
(`test_clemens_reconciliation.py:16-21`, `:31` and `:102`: the key absent from the
config and from every shipped valuation set, before and after the diagnostic runs; and
`test_valuation_sets.py`: `config/valuation_sets/prospx_current.yaml` byte-identical to
the base config) stay green and untouched by this gate.

Instead the twin is stored under the SAME new key as the table form, as a scaled table:

```
empirical_anchors_v2:
  form: "scalar"                 # or "table"
  scale: s                       # 3 dp; absent under form "table"
  anchors:
    20, 25, 30, 35, 40:          # the served knots, byte for byte
    45, 50, 55, 60, 65, 70, 80:  # round(served_knot * s, 3)
```

so both forms flow through the one function every consumer reads, `fv_to_6yr_avg_war`,
and the flag has exactly one read site (12.1). The scalar applies to knots 45 and up
only, because the sub-45 knots are already as-of-frame measurements and out of this
gate (5.1); the slope of the 40-to-45 segment therefore changes under the scalar form,
by the factor `s` applied to the 45 knot alone. That is DISCLOSED, not repaired: a
repair would be a shape edit this gate did not register, and the artifact prints the
pre and post 40-to-45 slope beside the scalar.

### 11.4 The lever's own checks: one out-of-fold check on read rows, one fresh read

**Out-of-fold check on read rows, available at the verdict.** This is NOT a fresh
frame and is named so that nobody counts it as a look: its test folds (decision years
2016 through 2021) are S rows already read for the verdict, and its training rows
include H. It is an out-of-fold check of the LEVER'S FIT on rows this gate has read.
For each decision year Y in {2016, 2017, 2018, 2019, 2020, 2021} with resolved rows in
Y: fit v2 (and the twin) on resolved rows with decision year <= Y - 1, score cells on
decision year Y. Comparator: the incumbent RULE (the 0.5 public blend with the
thin-cell extra, `derive_empirical_war_anchors`'s arithmetic) applied to the same fold
rows on the same as-of frame, so the contrast isolates the shrinkage rule and prior
from the frame. The served table itself is ALSO scored on every fold and reported,
labelled partially in-sample for folds inside the fit window. Statistic:
cell-n-weighted mean absolute residual, pooled over folds, paired bootstrap over
players B = 2000 seed 20260923, **one-sided MDE95** (1.645 times the bootstrap
standard error of the paired difference). PASS requires v2 to beat the incumbent rule
pooled by more than the floor, with per-fold signs published and at least 4 of the 6
folds in v2's favour. A lever that does not pass this check is not shipped behind any
flag; it is recorded as a NULL in that word.

**The one fresh read, touched once, in 2027.** The decision-year 2022 cohort, which no
artifact in this repository has scored as resolved because it is not, is scored ONCE
when `RESOLVED_THROUGH` reaches 2027, on the same statistic against the served table
and v2. It may VETO a flag that is on (the owner is told, the flag is the mechanism)
and it may confirm one that is off. It is spent when read.

**Order of the two 2027 reads, pinned.** The 2027 label epoch (clause (k) Z4 of the
fWAR epoch gate names it "the next label epoch") will also read the 2022 decision
cohort in its own margin reads. This gate's one touch of that cohort comes AFTER the
2027 epoch's step Z (its margins re-read and the part 9 entry that records it),
mirroring the 2026 ordering of section 14, and never before it. A touch taken before
that entry is an early look on the 2027 epoch's frame and voids this gate's read of
the cohort, in the word VOID.

### 11.5 What the lever does NOT touch

`p_bucket_given_fv`, `midpoint_war`, `bucket_trajectory_shape`, aging, the reliever
haircut, `fv_to_prime_war`, the pooled outcome curve, the dollar map's FORM
(its refit is in 12.2), the arbitration ladder, the sub-45 knots. Enforced by the
tool writing exactly one key.

---

## 12. The SERVE flag, and the MODEL_VERSION consequence

### 12.1 The flag, default off, following the local idiom

```
# Whether the recalibrated realized anchor is SERVED. Set from the verdict in
# docs/PROSPECT_ANCHOR_GATE.md, never from the size of the correction, and a flip
# is the owner's call even on a PASS of the lever's out-of-fold check.
# False: fv_to_6yr_avg_war reads empirical_anchors.anchors, reproducing today's
# payload byte for byte. True: it reads empirical_anchors_v2.anchors, whichever
# form (table, or the scaled table of the one-parameter twin, section 11.3) that
# key records. ONE read site. war_anchor_scale is never the vehicle.
# Flipping it moves every priced prospect number (section 13.1) and no grade, no
# rank, no veteran projection, no betting number and no arbitration award.
# With it, in ONE commit: bump calibration.version, refit and re-stamp the dollar
# map, repoint --emit-snapshots at fv_to_6yr_avg_war() over the knot set so the
# glossary's table is the served anchor (12.2), re-emit data/value_framework.{json,js},
# re-capture prospx_current.yaml, move the pins, and re-run every export that
# stamps calibration_version().
SERVE_PROSPECT_ANCHOR_V2 = False     # env override EEPHUS_PROSPECT_ANCHOR_V2, read at call time
```

Read inside `fv_to_6yr_avg_war` at call time, and nowhere else. Every consumer in
13.1 reaches the anchor either directly through that function (`comps_engine.py:164`,
`efv_score.py:439` and `:1896`, `farm_grade_backtest.py:165`, the emitter once
repointed) or through the `lru_cache`d `_fv_war_scale` (value_framework.py:961-982),
which calls it; `proj_export._prospect_rows` (`:1425`) and `storage`'s farm and org
surplus leaves reach it through `vf._war_scale_for`, and `realized_implied_fv`,
`survivor_expected_war` (WAG) and `debuted_player_value` through the same cache.
`_reset_derived_caches` (`:264-270`) already clears `_fv_war_scale` along with
`_calibrated_midpoints` and `_prime_war_scale`; because those caches read the anchor
underneath, the flip commit adds the flag to that reset, and
`test_prospect_anchor_gate.py` pins that the OFF payload of every consumer in 13.1 is
byte-identical to the pre-change payload.

**A flip is the owner's call even on a PASS, and never a function of effect size.**

### 12.2 MODEL_VERSION, in this module's own vocabulary

`value_framework` carries no `MODEL_VERSION` constant. Its identity is stamped four
ways, and the house rule that a PRICER change bumps the version applies to each:

| stamp | today | on flip |
|---|---|---|
| `calibration.version` (`value_framework_config.yaml`), served by `calibration_version()` and embedded by `calibration_stamp()` into `xfv.json`, `trade_values.json`, `mlb_projections.json` and `timeseries.json` (commit `ad402add`) | `isotonic-real-v6-evframe-2026-07-31` | a v7 string carrying `anchor2` and the date. The v6 map was fitted on the incumbent raw WAR layer; F08 (e) requires the dollar map to be re-fit on the new raw layer, so the flip is anchor plus map plus version in one commit, and `test_calibration_vintage.py` then flags every artifact still carrying v6 as built on a superseded map, which is what it exists for |
| `config/valuation_sets/prospx_current.yaml`, the base-identity set, byte-identical to the base config by rule (`test_valuation_sets.py`) | captured at the 2026-09-04 epoch | re-captured in the flip commit |
| `data/value_framework.json` / `.js`, the emitted snapshot the glossary reads for its FV-to-WAR table (`assets/glossary.js:1908`, `:1993`, `:2203`) | carries the config SEED `{35: 0.12, 40: 0.22, 45: 0.38, 50: 0.7, 55: 0.95, 60: 1.45, 65: 1.95, 70: 2.6, 80: 3.8}`, because the emitter (`value_framework.py:3962`) writes `cfg["fv_to_6yr_avg_war"]` and not the fitted anchor; the glossary therefore prints a table that is NOT what prices, today and before this gate (section 0, a read with no disposition) | the flip commit repoints the emitter at `fv_to_6yr_avg_war()` over the knot set (12.1's one-commit list) and re-emits, so the glossary's table becomes the served anchor for the first time. A re-emit WITHOUT the repoint would still serve the seed and is not a flip. The glossary source needs no edit; `:2226` (the sub-45 block) already reads `fitted.empirical_anchors` and does not move |
| `storage.BOARD_BASIS_FINGERPRINT` | `xfv_grade|scale=off|grademap=outcome_pooled@1f3fa0a970bd ...` | **does NOT move.** The grade map is the pooled curve, not the anchor, and the flip commit asserts the board grade and rank byte-identical (13.2). A fingerprint only guards what it names, and this one correctly does not name the anchor |
| registry row `prospect_surplus` | `validated` | `provisional` at the moment of the flip, the ARBITRATION_GATE B7 precedent, until the lever's one fresh read (the 2022 cohort, 2027) is taken |
| registry row `prospect_anchor` (new) | absent | created at this registration with `verdict: registered`, pointing here; carries the gate verdict, the frame, the fitted-file hash scored and, under 10.2, the lever's second-look results |

`storage.FV_EXPECTED_WAR_PER_YR_*` are a stale primer fallback used only if the engine
is unavailable (storage.py:5617-5626 for the comment, `:5713` for the fallback branch)
and do not move. The frontend `FV_WAR_ANCHORS` mirror (`prospx/index.html:22471`,
pinned by `test_wag_l13_repairs.py:46`) is a HAND constant that the storage comment
says is "synced to the derived survivor curve"; it does not move with any snapshot,
and the flip commit states whether it was re-synced by hand and what the pin then
reads.

---

## 13. The served numbers that move under the lever, with bands, and the ones that must not

### 13.1 What moves, named in advance

Only under `SERVE_PROSPECT_ANCHOR_V2 = True`. Every quantity below is recounted at
the flip and published pre and post; design-day figures are quoted only where an
artifact already published them, because the served artifacts regenerate nightly and
an export chain is writing them as this document is committed.

| quantity | baseline | band before a SEPARATE owner decision is required |
|---|---|---|
| `/projections/` prospect rows: `war`, `warP10`, `warP90`, `warTotal`, `warTotalP10`, `warTotalP90`, `surNpv` | 183 rows, 683.1 five-year `warTotal` sum (2026-09-18, PROJ_PATH_SHAPE_GATE 9.2) | sum of prospect `warTotal` plus or minus **25 percent** |
| `/prospx/` board and cards: eFV surplus dollars (`expected_surplus_usd`, `sv_distribution` p10/p90, `sv_credible_interval`), consensus surplus, `Sur+` | recount at flip | sum of eFV-basis prospect surplus over the board plus or minus **25 percent** |
| any single prospect row's surplus | recount | plus or minus **50 percent or $15M, whichever is larger**; every row beyond it listed BY NAME in the flip commit; **more than 25 such rows is a separate owner decision** |
| `trade_values.json` and the Trade Machine: prospect prior values (`surplus_value_mm`) and debuted players' remaining value (`debuted_player_value`, whose prior bucket levels scale with the anchor) | recount | top-100 trade-value membership change of **more than 10 rows is a separate owner decision** |
| farm surplus, `OrgSur+`, Grad-Contract Surplus (org aggregates of the above) | recount | Spearman of the 30-org `OrgSur+` order pre versus post **below 0.95**, or any top-5 farm membership change, is a separate owner decision |
| WAG labels (`wag` reads `survivor_expected_war`, which scales with the anchor) | recount of graded players | label flips on **more than 10 percent** of graded players is a separate owner decision |
| `_odds_grade` (retired inverse of the anchor, exported per S-3) and every star-odds number keyed on it | recount | RECORDED; the star-odds measured-rates switch (2026-09-03 decision 7) has its own lane |
| `efv_score`'s consensus-implied WAR fields (`cons_implied`, `_p1_legacy_mix6`), `comps_engine` comp WAR, `farm_grade_backtest`, `fa_market`'s import | recount | asserted in the flip commit; any that moves is listed |
| Spearman(pre, post) over prospect surplus within side | RECORDED, not gated | expected 1.0000 for the scalar twin and near it for a monotone table; a level lever never reorders a side, so this is a regression guard in the sense of ARBITRATION_GATE 0a: below 0.99 means something broke, and unchanged order is not evidence the lever worked |
| the glossary's printed FV-to-WAR table (`assets/glossary.js:1908`, `:1993`, `:2203`, reading `window.VALUE_FRAMEWORK.fv_to_6yr_avg_war`) | the config seed, not the served anchor (section 0) | moves ONLY if the emitter is repointed at `fv_to_6yr_avg_war()` in the flip commit (12.1); recorded pre and post, no band, because a printed reference table carries no priced number |
| Made's row and the other rows named in commit `c5167587` | 7.5 expected / 15.4 prime / peak 3.8 / P(bust) 5 percent | reported pre and post; `pBust` and the prime figures must be UNCHANGED (13.2) |

A band is a trigger for an owner decision, not a criterion. Landing inside every band
is not evidence the lever worked, and the artifact says so.

**The 2x cap is not a band.** A knot moving by a factor outside [0.5, 2.0] refuses the
lever before any of the above is measured (11.2).

### 13.2 What must NOT move, asserted rather than believed

Each is an assertion in the flip commit, checked pre and post:

- **every eFV grade and every board rank**, on `/prospx/` and in `xfv.json`: the grade
  inverts the pooled curve, whose hash is unchanged, and `BOARD_BASIS_FINGERPRINT`
  does not move;
- **`pBust` on every prospect row** and every P(bucket given FV) probability: the
  mixture weights are Clemens's and the lever touches only the level;
- **`warPTH`, `warPTHP10`, `warPTHP90`, `warTotalPTH`, `warPeak` and the `prime` tag**
  on every prospect row: the prime anchor is a different table;
- **every veteran row on `/projections/`**, `warChamp`, `warY1Champ`, the Team Outlook
  roll-up and top-3 strip, `/fa/` current-class pricing and the future-class overlay:
  none reads the anchor;
- **`/arbitration/`** in its entirety: the award model and the ladder price salary,
  not prospect WAR;
- **every betting, DFS, fantasy and management number**: no reader;
- **the sub-45 anchor knots**, byte for byte, and the `test_empirical_anchors`
  tripwire stays green;
- **every route, hash and deep-link key.** No new one is introduced. `#g=prospect_anchor`
  is the only new glossary anchor, added only if the owner wants the disclosure on
  the sub-line.

---

## 14. The clock. One look, on a fixed condition and a fixed earliest date

**Looking early disqualifies.** A look after its date requires an amendment filed
before the look, saying what moved on disk since this document was committed (the 5c
amendment form).

| date | what | frame it may touch | may it be read before |
|---|---|---|---|
| this commit | this registration, results empty | none | - |
| **the LATER of 2026-11-20 and 14 days after `FWAR_LABEL_EPOCH_GATE.md` part 9 records the entry for step Z** (the margins re-read; a precondition DISCLOSURE entered under that gate's part 3 is a part 9 entry and is NOT that entry) | **THE LOOK. Once.** Requires L1: steps F, I and J of the epoch complete, matrices on `fwar` at `RESOLVED_THROUGH = 2026`, the fitted file's `empirical_anchors` regenerated by step J and its `generated_at` pinned in the artifact. The `power` block is written first, then `cells`, then the verdict | H, S | not before. If the condition is not met by **2026-12-31**, the look slips with the epoch and is NOT taken on the eWAR v2 label |
| same session, after the verdict is written | under MISCALIBRATED only: the lever fit (11.1), the caps (11.2), the twin (11.3) and the out-of-fold check on read rows (11.4) | H + S, forward-chained by decision year; no row this gate has not already read | not before the verdict exists in the artifact |
| **not before 2027-10-15, and after the 2027 label epoch's part 9 records its step Z entry** | the one fresh read (11.4): the 2022 decision cohort at `RESOLVED_THROUGH = 2027`, touched once, AFTER the 2027 epoch has taken its own read of that cohort | the 2022 cohort only | not before either condition |
| **after `RESOLVED_THROUGH` reaches 2027** | earliest admissible re-registration on an UNDECIDED verdict, as a NEW document disclosing this read | - | the new registration must disclose that this one was read |

**Where 2026-11-20 comes from.** It is one week after the last `PROJ_PATH_SHAPE_GATE.md`
look (ARM B, 2026-11-13), so that no lab of this gate runs in the window of that
adjudication (the epoch's own rule for its step Y, never concurrent with a lab,
applied to this one), and it sits six weeks after the epoch's step M floor of
2026-10-05. It is a floor and not the expected date: the part 9 condition is the
binding one, and the date exists only so that a fast epoch cannot pull this look into
the PROJ_PATH window.

**Why not now, on eWAR v2, when the owner's question is live today.** Three reasons,
each sufficient. First, the task names the epoch label, and the anchor that will price
money from the epoch onward is the one step J refits on that label; a verdict on the
eWAR v2 table would be a verdict on a table that stops serving within weeks. Second,
the hitter label moves for real at this epoch (change sd 1.785 WAR against a label sd
of 7.47, epoch gate part 2), so an eWAR v2 read of a hitter-heavy cell is not a read
of the fWAR quantity. Third, frame H is the only verdict-bearing frame this gate has,
and it is spent when read; spending it on a retiring table would leave the serving
table with nothing but the S veto.

**Interaction with the other clocks, stated so nothing collides.** The 5c-A look
(2026-09-28) and the 5c-B and 5c-C looks (2026-10-05) read betting columns this gate
never touches. The PROJ_PATH_SHAPE_GATE looks (2026-09-25, 10-02, 10-09, 10-23,
11-06, 11-13) read projection frames this gate never touches (L7). The epoch's step M
(not before 2026-10-05) and its 5c-C window constraint on steps D and E are the
epoch's business; this gate waits behind all of them by construction of its own
condition.

---

## 15. Pools, the artifact, and the test that stops a criterion being edited

- **Pools are counted at scoring time and published with their clause.** The
  matrices regenerate at the epoch and the DB is written by the box; every count in
  this document is a design-day expectation and is never quoted as the result.
- **`data/prospect_anchor_gate.json` carries each criterion VERBATIM beside its
  result**: per cell and frame, n, `D_C`, `R_C`, the interval, `m_C` and the two
  anchor values it was derived from, the disposition, the family it sat in, its
  `p_C` and the Holm step; the `power` block of section 8, including the look-day `m_C` beside the design-day
  value and their ratio; the label stamps of L1; the identity checks of L2; the H
  decision-year census; the source census of 4.1 per cell and frame; the
  `SOURCE_SCALE_SUSPECT` label wherever the concordance rule of 6.2 fired, with both
  frames' intervals; the per-side layer; the pooled read labelled READ; the seed, B and wall time; and, for the row commit
  `c5167587` named, the served anchor at that FV beside the served path mean, with no
  disposition attached to it.
- **`test_prospect_anchor_gate.py` pins the CRITERIA as well as the verdicts**, so a
  criterion cannot be edited after a result has been seen. It also pins: that H and S
  partition the resolved pool with no key in both; that the `power` block precedes the
  `cells` block; that no field of the artifact derives from `data/mlb_projections.json`
  (L7); that `SERVE_PROSPECT_ANCHOR_V2` defaults to `False` and the OFF payload of
  every 13.1 consumer matches the pre-change payload; that the sub-45 knots are
  byte-identical across the flag; that `empirical_anchors_v2` exists only if the
  verdict field reads MISCALIBRATED and, when it exists, carries a `form` of `table`
  or `scalar` and sub-45 knots byte-identical to `empirical_anchors`; that
  `war_anchor_scale` is absent from the config before and after the flag, both
  states; that the look-day `m_C` ratio of 5.4 is recorded at every cell; and that
  the verdict vocabulary is closed.
- **Every clause states its own direction.** Positive `D_C` is realized above anchor.
- **The verdict vocabulary is closed**: `CONFIRMED`, `MISCALIBRATED`, `UNDECIDED`,
  `UNPOWERED`, `UNDECIDED_UNDERPOWERED`, `NOT_AVAILABLE` (L1 unmet at the look date),
  `VOID` (an early read), `REFUSED` (lever caps), `NULL` (lever out-of-fold check or
  fresh read). One cell ANNOTATION, never a verdict: `SOURCE_SCALE_SUSPECT` (6.2). A
  gate that spells an absence of evidence the way it spells cleared evidence is worse
  than no gate.

---

## 16. Banned, and enforced mechanically

- Reading the survivor mean, the bust rate or any bucket-conditional statistic of a
  cell (F07's and BUST2's looks). The lab computes `label / 6` and the anchor and
  nothing conditional on the outcome.
- Any per-side verdict, or any copy citing a per-side number as evidence about the
  anchor (section 7).
- Any tolerance narrower or wider than 5.4, or any cell added or dropped after the
  look. The test pins the five cells and the margin formula.
- A candidate anchor computed before the verdict is written (G-0).
- A lever fitted with a free K, a free prior, a per-side table, or a knot set
  different from 11.1. The tool takes no such arguments.
- Shipping a six-knot table when the scalar captured 75 percent (11.3).
- Shipping the scalar twin through config `war_anchor_scale`, or through any read
  site other than `fv_to_6yr_avg_war` (11.3).
- Touching the 2022 decision cohort before the 2027 epoch's part 9 records its step
  Z entry (11.4, section 14).
- Running the lab on the eWAR v2 label, or before the epoch's part 9 records its
  step Z entry (section 14).
- Calling `value_framework.py --fit` from the lab or the lever tool (the sub-45
  revert trap).
- Any copy attributing a movement of the anchor to the fWAR basis being "more
  accurate" (epoch gate clause (l), absolute).
- Using this artifact to adjudicate the prime anchor, the dollar map, the arbitration
  ladder or the age placement.

---

## 17. Pre-commitments: the exact sentence each outcome publishes

- **CONFIRMED:** *"The realized anchor is CONFIRMED at FV cells [list] on the holdout
  frame: the bust-inclusive first-six-season mean of resolved prospects at each of
  those FVs sits within one grade step of the level the framework assigns. Cells
  [list] were unpowered on the holdout and read [dispositions] on the shared frame,
  which can fail the anchor and cannot confirm it. Nothing served moves. The open
  question of commit c5167587 is answered: the expected path is the calibrated
  bust-inclusive mean. If the row still reads low beside its bust probability, that
  is the mixture's shape (design audit F07), not its level, and it has its own
  registration."*
- **MISCALIBRATED, positive:** *"The realized anchor is MISCALIBRATED LOW at FV cells
  [list] on frame [H or S]: resolved prospects delivered [D_C] WAR per season more
  than the framework assigns, interval [lo, hi], beyond the one-grade-step tolerance
  [m_C]. A recalibration lever is built behind SERVE_PROSPECT_ANCHOR_V2, default off;
  its out-of-fold check on read rows reads [PASS or NULL]. Nothing served moves until
  the owner flips it. This is a statement about the level of the anchor, not about
  the shape of the mixture, and not about any player."*
- **MISCALIBRATED, negative:** the same sentence with HIGH and "less than", and the
  added clause: *"The owner's suspicion that the anchor is calibrated low is
  falsified at these cells."*
- **UNDECIDED:** *"The realized anchor is UNDECIDED at FV cells [list]: the interval on
  the realized-minus-assigned level crosses the tolerance band. Nothing served moves.
  The question re-arms when RESOLVED_THROUGH reaches 2027 under a new registration
  that discloses this read. UNDECIDED is not a confirmation and no copy may treat it
  as one."*
- **UNPOWERED at 60 and 65+ on H:** *"The resolved holdout carries [n] prospects at
  FV [cell], below the 40-row floor the anchor itself declares for trusting a tier.
  The anchor is not adjudicated there. The shared frame reads [disposition]."*
- **Lever REFUSED:** *"The recalibrated anchor moves knot [k] by a factor of [f],
  outside [0.5, 2.0]. A correction of that size is the shape of the Quantity A /
  Quantity B trap and is evidence the frame is measuring the wrong quantity, not
  evidence about the anchor. The lever is refused and nothing ships."*
- **Lever out-of-fold check NULL:** *"The recalibrated anchor does not beat the
  incumbent rule out of fold by more than the floor ([MDE95]) on the forward-chained
  decision years, [k] of 6 folds in its favour, on rows this gate had already read.
  Reported as a NULL. The flag stays off and the MISCALIBRATED verdict on the anchor
  stands unrepaired."*
- **UNDECIDED by the concordance rule:** *"Cell [k] reads MISCALIBRATED on the holdout
  frame, whose rows at that cell are [share] single-source MLB Pipeline-scale FV, and
  the opposite sign on the shared frame, interval [lo, hi]. The two frames disagree in
  direction, which is the signature of a source-scale offset and not of the anchor's
  level; the cell reads UNDECIDED and nothing ships from it."*
- **Unconditionally, in every artifact:** *"Every number here is on the published
  fWAR label frozen per season. It is a statement about that definition of WAR. The
  anchor's agreement or disagreement with it is not evidence that the label is more
  or less accurate than any other."*

---

## 18. Results

**EMPTY AT REGISTRATION.**

No cell mean, residual, interval, disposition, power figure, cohort census, candidate
anchor, twin, fold or blast-radius number has been computed at this commit. None may
be written anywhere above this line, and nothing above this line may be edited once
anything is written below it, except by a dated amendment filed BEFORE the look under
the 5c amendment form, which names what moved on disk and changes no threshold, frame,
cell or criterion.

The first entry here is dated, names the commit that produced it, records the five
stamps of L1, and states which frame each disposition came from. Section 17's
sentences bind it.

---

Nothing in this document was scored. Every number above is a value in a committed
config or fitted file, a figure already published in a committed artifact, document
or commit message, or arithmetic on such a figure labelled as such. The direction of
the answer has a published prior, recorded in G-0.1, and this gate is written as a
confirmatory registration that can fail in either direction.

### 2026-10-14: the look, taken once, as an OWNER-WAIVED EARLY READ (EW3-5)

This entry records the one look of section 14. It was taken on 2026-10-14, 37 days before
the registered floor of 2026-11-20, under the owner's waiver of registered look days and dates
(DECISIONS_FOR_OWNER.md EW3-5, owner 2026-10-14, verbatim: "Fuck the registered look days and
waiting, we don't have to wait for anything. Let's do everything today"). It is therefore an
OWNER-WAIVED EARLY READ, recorded in that word, and the "looking early disqualifies" clause of
G-0 and section 14 is set aside by the owner's decision and by nothing else. The step Z
condition held: `FWAR_LABEL_EPOCH_GATE.md` part 9 records its step Z entry dated 2026-10-03
(commit `73850ecc`), and the look-day margins of 5.4 sat inside the 0.75x to 1.25x pin at every
cell, so no 5c amendment was required and none was filed. The closing note below section 18's
registration text describes the document before this entry. Clause (l) of the epoch gate binds
every line: the numbers are statements about the published fWAR label and draw no accuracy
conclusion from the basis.

**The commit that produced it.** The numbers were produced from HEAD `a82bc17e` by
`python -u tools/prospect_anchor_gate.py --owner-waived-early-read` (rc 0, B 2000, seed
20260923, two-sided 90 percent, wall time 10.88 s, `generated_at` 2026-10-14T13:33:34), its
stdout and stderr tee'd before anything else ran, after a step 2 dry run of the whole reporting
path on a fixture frame with None values and an unpowered cell (35 tests passed, the fixture
artifact written only to the task's output directory). The artifact is
`data/prospect_anchor_gate.json`, sha256
`8032046e5a4de2609bfe96d8c6c9757ffe07fb3b0c8bf768d88e1523a9eec86a`, 62,160 bytes, with the
`power` block written before `cells` and `cells` before `verdict`. The commit that carries this
entry also carries the artifact, the `prospect_anchor` registry row pointed at it, and the
verdict pins in `test_prospect_anchor_gate.py`.

**The five stamps of L1.** `war_basis.provider` `fwar`, both matrix reports' target
`first-6-season summed WAR (fwar); resolved<= 2026`, the board label term
`label=fwar@2026-10-02-0341299c20ec`; `RESOLVED_THROUGH` 2026; the label-window rule
`SERVICE_ALIGNED_WINDOW` False with `_SERVICE_YEAR_CUT_MMDD` 04-15 (the calendar window, so no
post-cut 2021 debut was censored on that account); `empirical_anchors.generated_at`
2026-10-03T16:35:15 (step J, commit `70ae6f9d`, and `git log 70ae6f9d..HEAD` touches the fitted
file nowhere, so no `--fit` ran between step Z and the look); `cohort_window` [2014, 2020] with
`n_cohort` 3463. The served table scored: 45 0.31, 50 0.68, 55 0.98, 60 1.5, 65 1.99, 70 2.47,
80 3.5, with the sub-45 knots 20 0.0091, 25 0.0106, 30 0.012, 35 0.0143, 40 0.0703 (out of this
gate, 5.1). Fitted file sha256 `a36d22cefe5ff6eb479b5563144eb9c55d241d196cf61e23a7326b4c5dfdf8ee`.
`use_empirical` True, `min_n_robust` 40. `SERVE_PROSPECT_ANCHOR_V2` False, and
`fv_to_6yr_avg_war` reproduced the fitted table at every checked knot.

**L2 and L6.** The pooled curve lab's loader and identity checks, unchanged: hit 1,985 scored
rows (1,577 uncensored, 408 censored), pit 2,100 (1,636 uncensored, 464 censored),
`target_censored_mismatches` 0, `consensus_fv_raw_mismatches` 0, `censored_flag_mismatches` 0
on both sides, `unmatched_in_matrix` 0, `cross_side_key_overlap` 0, every count equal to the
pooled curve's own published counts on the same label. L6: `empirical_anchors._cohort` at
[2014, 2020] reproduced 3,463 keys against the fitted file's 3,463. L3 dropped 872 censored rows;
2,491 resolved rows sat below the 45 cell (sub-45, out); 722 resolved rows entered the five
cells. No row was dropped for a missing key, FV or label.

**The frames.** H (holdout, verdict-bearing): 610 resolved rows, 155 in cells; decision-year
census of the in-cell rows 2011: 11, 2012: 32, 2013: 105, 2015: 1, 2021: 2, 2022: 2, 2023: 2;
source census mean `n_sources` 0.89, share single-source 0.845, share Pipeline-only 0.832. S
(shared, veto only): 2,603 rows, 567 in cells; mean `n_sources` 1.68, single-source 0.319,
Pipeline-only 0.312. No key in both. H is what 4.1 said it would be: the 2011 to 2013 decision
cohorts on a largely Pipeline-scale FV, plus a handful of later rows resolved by inactivity.

**Power, written before any criterion was read.** Margin pin holds at every cell: m_C 45
0.152425 (ratio to design day 1.0028), 50 0.1675 (1.0152), 55 0.205 (1.0789), 60 0.2525
(0.9787), 65+ 0.2425 (0.9221). Powered by n: H at 45 only (n 91); S at 45 (289), 50 (157) and
55 (82). MDE95 (1.645 times the bootstrap se): H45 0.0798, S45 0.0712, S50 0.1438, S55 0.2124,
none above 2 m_C, so no cell read UNDECIDED_UNDERPOWERED. Residual sd: H45 0.462, S45 0.732,
S50 1.088, S55 1.182. Detection check (planting exactly +m_C, B 1000): H45 0.054, S45 0.051, S50
0.041, S55 0.061, every powered cell labelled a lucky read (below 0.80), disposition rules
unchanged. Recorded as measured and read for what it is: the registered check plants the
residual AT the band edge that the MISCALIBRATED criterion tests against, so the fraction it
returns is the criterion's own one-sided size at the edge, about 0.05 by construction, and not
a detection rate for any effect beyond the edge. That is a property of the registered design,
disclosed here, and not edited above this line. Coverage check (n_check 200): H45 0.865 (too
narrow; misses 0.03 above, 0.105 below), S45 0.89 (too narrow; 0.045, 0.065), S50 0.92, S55
0.92. The narrow direction manufactures CONFIRMED; no cell read CONFIRMED, so the two flags
cost nothing to the verdict and are recorded.

**The cells.** D_C in WAR per season, positive meaning realized above the anchor; the interval
is the two-sided 90 percent percentile bootstrap; the pooled H + S row is a READ with no
verdict.

| cell | frame | n | D_C | 90 percent interval | R_C | p_C | Holm step | disposition |
|---|---|---|---|---|---|---|---|---|
| 45 | H | 91 | -0.229006 | [-0.303316, -0.142321] | 0.367 | 0.134 | 1 of 1 (threshold 0.10) | UNDECIDED |
| 45 | S | 289 | +0.103374 | [0.034399, 0.177108] | 1.349 | 1.0 | 2 of 3 | UNDECIDED |
| 45 | H + S | 380 | +0.023778 | [-0.032064, 0.084203] | 1.076 | - | - | READ |
| 50 | H | 25 | +0.401808 | none (n below 40) | 1.629 | - | - | UNPOWERED |
| 50 | S | 157 | +0.252282 | [0.109001, 0.400676] | 1.381 | 0.322 | 1 of 3 (threshold 0.0333) | UNDECIDED |
| 50 | H + S | 182 | +0.272821 | [0.141975, 0.413724] | 1.414 | - | - | READ |
| 55 | H | 30 | +0.249804 | none | 1.238 | - | - | UNPOWERED |
| 55 | S | 82 | +0.032899 | [-0.176137, 0.24389] | 1.034 | 1.0 | 3 of 3 | UNDECIDED |
| 55 | H + S | 112 | +0.090999 | [-0.093527, 0.281089] | 1.092 | - | - | READ |
| 60 | H | 5 | +0.322333 | none | 1.215 | - | - | UNPOWERED |
| 60 | S | 26 | -0.036879 | none | 0.975 | - | - | UNPOWERED |
| 60 | H + S | 31 | +0.021058 | none | 1.014 | - | - | READ |
| 65+ | H | 4 | +1.044583 | none | 1.481 | - | - | UNPOWERED |
| 65+ | S | 13 | +0.469572 | none | 1.224 | - | - | UNPOWERED |
| 65+ | H + S | 17 | +0.604869 | none | 1.286 | - | - | READ |

Mean assigned anchor beside the knot value, so the within-cell FV spread is visible: H45 0.3619
(knot 0.31), S45 0.2962, S50 0.6619 (0.68), S55 0.9687 (0.98). Family H: k 1, p 0.134 against
0.10, Holm stopped at step 1, nothing rejected. Family S: k 3, ordered p 0.322 (50), 1.0 (45),
1.0 (55), stopped at step 1, nothing rejected. The concordance rule did not fire (it acts only
on a MISCALIBRATED H cell); no cell carries `SOURCE_SCALE_SUSPECT`. The one-parameter reading
of 6.4 is not published (it exists only under MISCALIBRATED). Per-side numbers, reported and
never adjudicated (section 7): H45 hit n 50 D -0.198 [-0.302, -0.076], pit n 41 D -0.266
[-0.361, -0.142]; S45 hit n 157 D +0.099 [0.001, 0.205], pit n 132 D +0.108 [0.015, 0.211];
S50 hit n 83 D +0.311 [0.101, 0.520], pit n 74 D +0.187 [0.012, 0.374]; S55 hit n 45 D +0.239
[-0.073, 0.582], pit n 37 (counts only) D -0.218. No copy may cite any of them as evidence about
the anchor.

**Dispositions by frame, in the gate's words.** H: 45 UNDECIDED, 50 UNPOWERED, 55 UNPOWERED,
60 UNPOWERED, 65+ UNPOWERED. S: 45 UNDECIDED, 50 UNDECIDED, 55 UNDECIDED, 60 UNPOWERED, 65+
UNPOWERED. H was UNPOWERED at 50 and 55, so by 10.1's reachability note CONFIRMED was
structurally unreachable at this look and the reachable set was {MISCALIBRATED, UNDECIDED}. No
powered cell on H or S read MISCALIBRATED. **The verdict on the anchor is UNDECIDED** (6.2).

**Section 17's sentence for the outcome, verbatim from the artifact.** "The realized anchor is
UNDECIDED at FV cells ['45']: the interval on the realized-minus-assigned level crosses the
tolerance band. Nothing served moves. The question re-arms when RESOLVED_THROUGH reaches 2027
under a new registration that discloses this read. UNDECIDED is not a confirmation and no copy
may treat it as one."

Section 17's UNPOWERED sentences, verbatim from the artifact: "The resolved holdout carries 25
prospects at FV 50, below the 40-row floor the anchor itself declares for trusting a tier. The
anchor is not adjudicated there. The shared frame reads UNDECIDED." "The resolved holdout
carries 30 prospects at FV 55, below the 40-row floor the anchor itself declares for trusting a
tier. The anchor is not adjudicated there. The shared frame reads UNDECIDED." "The resolved
holdout carries 5 prospects at FV 60, below the 40-row floor the anchor itself declares for
trusting a tier. The anchor is not adjudicated there. The shared frame reads UNPOWERED." "The
resolved holdout carries 4 prospects at FV 65+, below the 40-row floor the anchor itself
declares for trusting a tier. The anchor is not adjudicated there. The shared frame reads
UNPOWERED." And 10.4's sentence at 60 and 65+: "the resolved holdout carries too few prospects
at this FV to adjudicate the anchor there; the shared frame's reading is UNPOWERED, which can
fail the anchor and cannot confirm it".

Unconditionally: "Every number here is on the published fWAR label frozen per season. It is a
statement about that definition of WAR. The anchor's agreement or disagreement with it is not
evidence that the label is more or less accurate than any other."

**What the read showed and did not adjudicate, said once.** At 45 the two frames' point
estimates sit on opposite sides of zero: the holdout (83 percent Pipeline-only rows) reads below
the anchor, the shared frame (consensus-era rows, the anchor's own fit cohort re-binned) reads
above it, and the pooled read sits inside the band. That is the signature 4.1 pre-registered
for a source-scale offset between the two frames, and this gate adjudicates nothing from it: the
concordance rule exists to remove a MISCALIBRATED, and there was none. On S, the 45 and 50
intervals lie above zero and cross +m_C; they are UNDECIDED in that word and are not rounded
into a finding about the owner's suspicion. Section 9's falsification list: claim 2 is neither
confirmed nor falsified; claim 3 (the direction prior "up at every knot 45-65") is contradicted
on H at 45 (point estimate negative) and not contradicted on S at 45 and 50; claim 7 holds
mechanically (L6 within 1 percent, no key in both frames).

**The named row (section 0 row 6, section 15), published beside the anchor with no
disposition.** `jesus_made`: served `xfv_grade` 56.5 (pricing grade 56.5), served consensus FV
61.5; the served anchor at the commit's eFV 61.9 is 1.6862 WAR per season and at the served
grade 1.136; the commit's 7.5 over five years is 1.5 per season; the served path mean at the
pricing grade (P(bucket given FV) times the bucket season paths, five-season mean, no
calibration shift, no age) is 1.1694 per season. Nothing about the row is adjudicated.

**What happens now (10.3).** Nothing moves. `SERVE_PROSPECT_ANCHOR_V2` stays False;
`empirical_anchors_v2` does not exist; no lever was fitted, no twin, no out-of-fold check; the
2022 decision cohort was not touched; `value_framework.py --fit` was not called;
`prospect_surplus` keeps its verdict. The display debt of commit `c5167587` stays open. The
question re-arms as a NEW registration disclosing this read when `RESOLVED_THROUGH` reaches 2027
(the 2022 debut cohort resolves) and, if `--fit` runs with `reference_year` 2027, the window
slides to [2015, 2021] and moves the 2014 decision cohort from S into H, which is what is expected
to power H at 50 and 55. The re-registration may not narrow the tolerance or drop a cell that
read UNDECIDED here. Frame H is spent on this read. The registry row `prospect_anchor` now
points at the artifact and carries the verdict, the frame and the fitted-file hash scored.

**The run's output, verbatim** (the tee'd stdout and stderr, `anchor_look.txt`):

```
verdict: UNDECIDED
  cell  45  H n=   91 d=-0.229006 ci=[-0.303316, -0.142321] UNDECIDED  |  S n=  289 d=0.103374 ci=[0.034399, 0.177108] UNDECIDED  m_C=0.152425
  cell  50  H n=   25 d=0.401808 ci=None UNPOWERED  |  S n=  157 d=0.252282 ci=[0.109001, 0.400676] UNDECIDED  m_C=0.1675
  cell  55  H n=   30 d=0.249804 ci=None UNPOWERED  |  S n=   82 d=0.032899 ci=[-0.176137, 0.24389] UNDECIDED  m_C=0.205
  cell  60  H n=    5 d=0.322333 ci=None UNPOWERED  |  S n=   26 d=-0.036879 ci=None UNPOWERED  m_C=0.2525
  cell 65+  H n=    4 d=1.044583 ci=None UNPOWERED  |  S n=   13 d=0.469572 ci=None UNPOWERED  m_C=0.2425
margin pin holds: True
The realized anchor is UNDECIDED at FV cells ['45']: the interval on the realized-minus-assigned level crosses the tolerance band. Nothing served moves. The question re-arms when RESOLVED_THROUGH reaches 2027 under a new registration that discloses this read. UNDECIDED is not a confirmation and no copy may treat it as one.
Every number here is on the published fWAR label frozen per season. It is a statement about that definition of WAR. The anchor's agreement or disagreement with it is not evidence that the label is more or less accurate than any other.
```

### 2026-10-14: owner-waived early read, the dated note EW3-5 asks for

The look above ran 37 days before its registered floor (2026-11-20, the later of 2026-11-20 and
step Z 2026-10-03 plus 14 days) under owner decision EW3-5 of 2026-10-14, which waives registered
look days and dates for every task. It is recorded as an OWNER-WAIVED EARLY READ. The only other
condition of section 14, the step Z entry, held. The waiver was carried by an explicit switch of
the lab (`--owner-waived-early-read`, commit `a82bc17e`), never by default; without it the lab
still refuses before the floor, and neither the step Z condition nor another gate's look day is
waived by it. Nothing above section 18 was edited.
