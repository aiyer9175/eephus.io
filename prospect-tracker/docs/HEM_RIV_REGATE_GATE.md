# Re-gate: the shipped HEM+ construction, and RIV+ against REM+ (pre-registered 2026-09-18)

Covers the two owner decisions of 2026-09-17/18: **"re-gate the shipped construction"**
(`xhem_plus`, `fwdhem_plus`) and **"re-gate against REM+"** (`riv_plus`). Both are
RE-GATES, so 5c rule 1 governs: this document is written and complete BEFORE a single
number is computed, and looking early disqualifies the result.

Producers: `tools/xhem_plus_lab.py` (X-H3 / X-H5), `tools/hem_plus_lab.py`,
`tools/rem_plus_lab.py` (X-R3), `tools/plus_lab_harness.py` (harness v2).
Artifacts under test: `data/xhem_plus_eval.json`, `data/riv_plus_eval.json`.
Registry rows under test: `xhem_plus` (validated), `fwdhem_plus` (validated),
`riv_plus` (provisional).

Written in the shape of `docs/SC_PLUS_RECALIBRATION_GATE.md`, `docs/ARBITRATION_GATE.md`
and `docs/HOF_BAKEOFF_GATE.md`. Where this document and a later measurement disagree,
**the measurement is what this gate uses**, and the disagreement is recorded rather than
edited away.

**NOTHING IN THIS DOCUMENT WAS COMPUTED.** No lab was run, no eval artifact was read for
its numbers, and the run happens after this file is committed. Every figure quoted below
is a PRIOR taken from the registry notes or from the 2026-09-17 bake-off brief, and every
prior is labelled as one in section 0.

---

## 0. HONESTY CLAUSE, and it comes first

Pre-registration is a claim about the ORDER of events, so the order is written down.

| object | status on 2026-09-18 | consequence |
|---|---|---|
| the published EVAL-normalized numbers for X-H3 and X-H5 (rho 0.4543 / 0.4108, gap lo95 +0.0173; blend 0.4658 vs 0.4543, gap mean +0.0114 lo95 +0.0038, `pass_under_v2` FALSE at mean +0.0015 lo95 -0.0069) | **READ**, they are in the registry notes and in `data/xhem_plus_eval.json` | D0 below is a REPRODUCTION CHECK, never pre-registration |
| "the normalizer difference accounts for about a third of the remaining v1 edge" (2026-09-17 bake-off) | **PARTIALLY READ**: an effect size for the served normalizer on the fwdHEM+ arm exists outside this document | arm A2 is a CONFIRMATORY re-gate with a recorded prior, not a virgin test, and it is labelled so in the artifact |
| the served-normalizer number for the xHEM+ arm (A1) | not quoted in the brief; the bake-off may have read it | if the run reproduces a number the bake-off already held, the artifact records A1 as confirmatory too. Absent evidence either way, A1 is treated as pre-registered and that assumption is printed |
| HEM+ losing to Savant xwOBA outright (0.4084 vs 0.4456, lo95 -0.0601 v1, -0.0705 v2) | **READ** | not a leg of this gate. Section R1-10 says what happens to it instead |
| RIV+ against REM+ at forecasting next-year RIV+ (0.2948 vs 0.2022, lo95 +0.0374) | **READ** | the repeatability leg is therefore a DISCLOSURE with zero verdict weight (R2-7), not the primary |
| the RIV+ market point rhos (0.576 vs 0.508 on 271 matched signings) | **READ as points** | the shipped artifact carries NO interval on this comparison (verified in code, R2-1). The PAIRED GAP with a bootstrap CI under either convention **has never been computed**, so the primary estimand B1 is pre-registered in the ordinary sense and only its point direction is a prior |

Calling any of the above pre-registered would be false. The rest of this document is
pre-registration in the ordinary sense.

---

## 1. Standing rules this document inherits, restated so they bind

1. **Harness v2** (`tools/plus_lab_harness.py`): complete-outcome-season pairs only
   (past Nov 15), unrounded `*_raw` predictors EXCEPT where the served object is itself
   rounded (R1-5 D4, declared in advance), both target conventions and both bootstrap
   designs emitted side by side.
2. **BOTH conventions are reported for every cell, always.** v1 = raw pooled target plus
   iid pair resample. v2 = within-outcome-season z target plus player-clustered,
   season-stratified resample. Quoting the one that passes while hiding the one that
   fails is the specific failure this document exists to prevent.
3. **The v1 grandfather clause ENDS for these three rows.** `convention_meta`
   interpretation rule 1 ("existing VALIDATED ships STAND even if v2 weakens them") was a
   one-cycle transition rule declared 2026-07-15. This re-gate spends that cycle. From
   this document forward, a re-gated row must clear BOTH conventions to hold a validated
   verdict, and R1-6 / R2-5 spell out what happens when it does not.
4. **Forward-chained and out of sample.** Same pair set for every candidate inside a
   comparison; coverage is reported SEPARATELY and never used to explain a gap.
5. **No floor is read from a stored constant.** Every MDE95 in this gate is derived in
   run as 1.645 times the bootstrap standard deviation of the gap, published with its
   sign, per `docs/EFV_GATE_STANDARD.md`. The hard-coded `- 0.02` slack at
   `tools/rem_plus_lab.py:422` is retired by R2-5.
6. **A NULL OR A LOSS IS A COMPLETE RESULT.** If a shipped construction fails its own
   gate, that is the finding, the registry verdict moves to match, and no third
   convention is invented afterwards.
7. **No re-tuning inside a re-gate.** The 0.7/0.3 blend weights, the 0.70/0.30 RIV+
   weights, `HEM_SPREAD_GAIN`, `RIV_SCALE`, the PA and TBF floors and the season lists
   are FIXED at their shipped values. A sweep over any of them is a new pre-registration
   with its own document, not a rescue of this one.
8. Seeds, declared now: `SEED_R1 = 20260918`, `SEED_R2 = 20260918`, `BOOT = 2000` for
   every new draw. D0 additionally re-runs under the original seeds (20260705 for X-H3,
   20260706 for X-H5), because reproducing a published number requires its own draw.

---

# RE-GATE 1: the shipped HEM+ family construction

## R1-0 What is under test, as code facts

These are properties of the source, not measurements. They are transcribed here so the
object under test cannot drift later.

**The eval construction (what passed the gate):**
`tools/xhem_plus_lab.py` builds the X-H3 pair set at `MIN_PA = 200.0` in BOTH the
predictor and the outcome season, over `SEASONS = [2016, 2017, 2018, 2019, 2021, 2022,
2023, 2024, 2025]`, and scores RAW Savant `est_woba` against RAW next-year `woba`. For
X-H5 it z-scores each leg WITHIN THE PREDICTOR SEASON over that pair set
(`plh.zscore_within(pys5, ...)`), blends 0.7/0.3, and scores the blend unrounded.

**The served construction (what is on the board):**

- `hitter_export._join_xhem_plus` (hitter_export.py:411-453): the pool is the served
  season's Savant batters at `_XHEM_MIN_PA = 100.0`; the anchor is that pool's PA-WEIGHTED
  mean xwOBA; the served value is
  `int(round(100 + HEM_SPREAD_GAIN * (100 * xwoba / pool - 100)))`.
- `hitter_export._join_fwdhem_plus` (hitter_export.py:456-514): the pool is the served
  season's Savant batters at `_FWDHEM_MIN_PA = 100.0` that ALSO carry a HEM core; each leg
  is z-scored over THAT pool (`mu_x, sd_x`, `mu_h, sd_h`); the 0.7/0.3 blend is then
  re-standardized by its own pool sd and mapped affinely onto the pool's HEM+ location and
  spread; the served value is `int(round(...))`.

**The four differences, named:**

1. **Normalizer pool membership.** PA >= 100 over the full served season pool, against
   PA >= 200 over the pair set. Different membership, different `mu` and `sd`.
2. **Normalizer recipe.** xHEM+ divides by a PA-weighted per-season pool mean; the eval
   compares raw xwOBA pooled across seasons. Within one season the served map is strictly
   monotone in xwOBA, so within-season order is untouched; **the gate's estimand is a
   POOLED forward Spearman across eight year-pairs, and a per-season divisor changes the
   pooled order.** That is the whole exposure.
3. **Leg weighting is not invariant for fwdHEM+.** The blend orders rows by
   `0.7 * (x - mu_x)/sd_x + 0.3 * (h - mu_h)/sd_h`, whose ranking depends on the RATIO
   `sd_h / sd_x`. The comment at hitter_export.py:499-503 ("Both steps are monotone, so
   the validated forward RANKING is exactly the shipped ranking") is true of the final
   re-standardize and the affine display map and **is not true of the leg normalizers**,
   which are computed over a different pool. A different pool is a different effective
   weight pair, and a different weight pair is a different ordering.
4. **Display rounding.** The board serves integers. The eval scores floats.

## R1-1 Estimand

Two arms, each a paired difference of Spearman rank correlations on one pair set.

- **A1 (xhem_plus).**
  `delta_A1 = rho(xHEM+_served(Y), wOBA(Y+1)) - rho(wOBA(Y), wOBA(Y+1))`,
  where `xHEM+_served` is the served recipe re-scored per predictor season over that
  season's full Savant pool at PA >= 100, then read on the pair-set rows.
- **A2 (fwdhem_plus).**
  `delta_A2 = rho(fwdHEM+_served(Y), wOBA(Y+1)) - rho(xwOBA(Y), wOBA(Y+1))`,
  where `fwdHEM+_served` is the served recipe (per-season leg z over the PA >= 100 pool
  with a HEM core, 0.7/0.3, re-standardize, affine map, round), read on the pair-set rows.

**The normalizer pool and the evaluation pool are different objects.** The normalizer is
fitted on the full season pool; the statistic is read on the pair-set rows only. Conflating
the two is the defect this re-gate exists to correct, so the separation is stated in the
estimand rather than left to the implementation.

## R1-2 Pair set and floors, frozen

The X-H3 pair set, unchanged: Savant PA >= 200 in Y AND in Y+1, seasons 2016-2025 ex-2020,
outcome season complete (past Nov 15), one row per (player, Y). A2 additionally requires an
unrounded `hem_plus_raw` for that (player, Y); the drop count is published. **The same pair
set carries every arm and every baseline in this comparison.** The published n for this set
is 1,871 pairs (a PRIOR, section 0); the run publishes its own n, and any deviation is
reported as a defect rather than absorbed.

**Approximation disclosed in advance.** The served normalizer is built at pipeline run time
from whatever Savant rows exist THEN, which mid-season is a smaller and differently shaped
pool than the completed season. The re-gate reconstructs the served recipe on COMPLETE
season pools, which is the best available proxy and is biased in one direction (complete
pools are larger and wider). This is written here so it cannot be produced afterwards to
explain away a loss.

## R1-3 Baselines

The baselines the ORIGINAL gate used, unchanged, raw, on the same rows: actual `wOBA(Y)`
for A1, `xwOBA(Y)` alone for A2. Only the CANDIDATE's normalizer changes, so one difference
moves at a time.

A labelled sensitivity with no verdict weight, A1s: served xHEM+ against served HEM+ (both
re-anchored per season), which is the comparison a reader of the board actually makes. It
informs the display lane; it does not move a registry verdict.

## R1-4 Conventions

v1 and v2 exactly as `plus_lab_harness` defines them, both published for every cell, at
`BOOT = 2000` and `SEED_R1 = 20260918`. v2 clusters on player and stratifies on first
predictor season. Each gap carries an in-run MDE95 (1.645 times the bootstrap sd of the
gap) published with its sign.

## R1-5 The decomposition ladder, declared before the run

Five rungs per arm, so that WHICH difference moved the number is a measurement and not a
story told afterwards:

| rung | construction | verdict weight |
|---|---|---|
| D0 | the eval construction, original seeds | none: reproduction check |
| D1 | D0 with the normalizer pool changed to the served PA >= 100 season pool | none |
| D2 | D1 with the served normalizer recipe (PA-weighted anchor for A1; per-season leg z plus re-standardize plus affine map for A2) | none |
| D3 | D2 unrounded | none |
| D4 | **the served column exactly, integers as served** | **THE VERDICT** |

D4 carries the verdict because integers are what ships and what a reader ranks. Harness
rule 2 keeps DISPLAY rounding out of a SKILL claim; here the object under test IS the
served column, so its rounding is part of the object and not a contaminant. D3 is published
beside it so the cost of rounding is visible, and the tie count at D4 is published.

If D0 fails to reproduce the published numbers, **the run stops and the reproduction
failure is the finding**; nothing downstream is reported as a verdict.

## R1-6 Decision rule, with the registry consequence fixed in advance

Per arm, after Holm (R1-7):

| outcome at D4 | registry consequence |
|---|---|
| gap lo95 > 0 under BOTH v1 and v2 | verdict stays **validated**, and the row's `champion` and `metric` lines are rewritten to name the SERVED normalizer, because today they describe the eval construction |
| gap lo95 > 0 under v1 only | **DEMOTE to provisional.** The one-cycle grandfather is spent (rule 3); the note records both reads and says the served construction is resolved under the legacy convention only |
| gap lo95 > 0 under v2 only | **DEMOTE to provisional.** A convention that was not pre-declared cannot promote a row |
| the gap CI straddles 0 under both | **DEMOTE to provisional**, and the claim text becomes "not separable from its baseline on the served construction at this n" |
| gap hi95 < 0 under either convention | **the claim is REFUTED.** Verdict moves to **deprecated** with a loss-ledger note; the column continues to ship until the display lane acts, and that is recorded as a display debt in section 9, not as a softened verdict |

Additional standing consequence, whatever the outcome: **the headline number on a served
column is the served construction's number.** The eval-normalized figure may appear only as
a labelled reproduction. This rule binds the whole +index family from this document forward.

## R1-7 Multiplicity family

The family is the **two primary arms, A1 and A2**, corrected by Holm through
`tools/efv_power_lab.holm_family` with k = 2, applied SEPARATELY within each convention
(the two conventions are two reads of one decision, not two chances at it, and rule 3
requires both). One-sided p per cell comes from the bootstrap gap distribution. The rungs
D0 to D3, the A1s sensitivity and every coverage figure sit OUTSIDE the family by
declaration and carry zero verdict weight. Total primary tests in this document: three
(A1, A2, B1). The families are declared per re-gate because the rows are independent
objects, and the total is printed here so no reader can suspect a larger family went
unmentioned.

## R1-8 Coverage, reported separately

Published beside the verdict, never inside it: pair-set n and its per-season split; the
served normalizer pool size per season at PA >= 100; and the count of players the BOARD
stamps (PA >= 100) who could never enter the eval pair set (PA >= 200 in both years).
**The gate speaks only about the PA >= 200 subset while the board shows more, and that
sentence travels with the verdict.**

## R1-9 What would make the shipped thing FAIL

Stated plainly, so the answer cannot be chosen after it is seen:

- A1 fails if served xHEM+ does not beat raw actual wOBA on the pair set at lo95 > 0 under
  both conventions.
- A2 fails if served fwdHEM+ does not beat raw xwOBA alone at lo95 > 0 under both
  conventions. **A2 is EXPECTED TO FAIL**, because `pass_under_v2` is already FALSE in its
  own published artifact (a PRIOR) and this document retires the rule that let it stand.
  The expectation is recorded up front so the demotion cannot be read afterwards as a
  surprise, and so nobody is tempted to hunt for a convention that rescues it.
- Either arm fails outright, at D4, if the normalizer difference eats the whole edge.

## R1-10 HEM+ against xwOBA is a PRIOR, and it is not a leg of this gate

The bake-off read HEM+ losing to Savant xwOBA outright. The shipped `hem_plus` row was
gated against AVG and raw wOBA, not against xwOBA, so that read does not fail the gate
`hem_plus` actually holds, and **adding a post-hoc baseline to an old row is exactly the
move this document forbids**. Two things happen instead: the number is recorded as a prior
in the `hem_plus` notes with its source and date, and a separate pre-registration for a
`hem_plus` re-gate against xwOBA is written at the next re-baseline (R1-12). The display
question that follows from it, whether HEM+ should remain the primary hitter skill column
beside xHEM+, belongs to the display lane and sits in section 9.

## R1-11 Pre-registered expectations

1. **A2 fails.** Its v2 read is already negative and the served normalizer is expected to
   cost it more. Wrong if A2 clears both conventions after Holm.
2. **A1 survives.** xHEM+ is a monotone map of xwOBA within a season, so only cross-season
   pooling and rounding are exposed, and the published edge is large. Wrong if A1's D4 gap
   loses its lower bound.
3. **The ladder localizes the damage at D1 and D2, not D3.** Rounding is expected to cost
   little next to the normalizer pool. Wrong if D3 to D4 moves more than D0 to D2.
4. **The bake-off's "about a third" survives as the fwdHEM+ order of magnitude.** Wrong if
   the served normalizer costs less than a tenth of the edge, or more than all of it.

## R1-12 Hard dates

- This document is frozen and committed **2026-09-18**, before any number is computed.
- The battery runs **2026-09-18**, on the pair set as frozen above.
- **If the battery has not run by 2026-09-25, both rows demote to provisional by default.**
  A clock with no teeth is not a clock.
- The pair set CANNOT be extended before **2026-11-15**, when the 2026 outcome season
  completes and the 2025 to 2026 block becomes admissible. Re-running before then to chase
  an n is a disqualifying look.
- Next re-baseline, including the separately pre-registered `hem_plus` against xwOBA
  re-gate: **2026-11-16 or later**, in its own document, written before its own numbers.
- The registry rows and the eval artifacts move in the SAME commit as the result. A verdict
  that lands without its artifact is a defect.

---

# RE-GATE 2: RIV+ against REM+

## R2-0 WHAT RIV+ IS FOR, written before anything is tested

**RIV+ is a VALUE RECORD, not a forecaster.** It is a leverage-weighted account of the wins
a reliever actually added: 0.70 z(WPA) plus 0.30 z(SD minus MD), standardized over the
season pool and re-standardized on the composite's own spread
(`rem_plus.score_riv_plus:272-308`). WPA is an OUTCOME. It already contains the leverage a
manager handed the pitcher, the sequencing he happened to meet and the defense behind him.
Nothing in that construction is a claim about next year.

Therefore this gate tests RIV+ **descriptively**, and the honest target is the one thing a
realized-value record can be checked against: **what clubs paid for it.** If a value index
does not track the market's own valuation of relievers at least as well as the pure skill
index it was built to complement, then it adds nothing REM+ did not already carry, and the
two-number design loses its second number.

Gating it as a forecaster would test a claim it never made. Gating it on its own noisiness,
which is what the shipped eval does, is worse than that: **a check that a number is LESS
repeatable than its baseline can be passed by adding noise to it**, so it cannot be a merit
condition, and it is removed from the pass set here.

## R2-1 Why the shipped eval cannot establish its claim, as code facts

`data/riv_plus_eval.json` and `tools/rem_plus_lab.py:398-500`:

1. **Two different targets.** `forward_stability_check` compares RIV+ predicting next-year
   RIV+ against REM+ predicting next-year REM+. Two predictors, two targets, two noise
   scales. Nothing follows from their difference about either index.
2. **The pass condition rewards noise.** `riv_less_stable_than_rem` is TRUE when RIV+ is
   the less repeatable number, and it is a required clause of the verdict.
3. **No interval anywhere.** `market_check_aav` emits point rhos only. The artifact carries
   no bootstrap, no CI and no floor on the one comparison that matters.
4. **A stored constant used as a floor.** `riv_market_ok` is `rho_riv >= rho_rem - 0.02`
   (tools/rem_plus_lab.py:420-422). The 0.02 is a literal, not a measured resolution, and it
   is exactly the kind of number `docs/EFV_GATE_STANDARD.md` forbids.
5. **Identity by normalized name.** `_riv_market_check` joins `fa_archive` signings to the
   walk-year pool through `_norm_name`. `fa_archive` signings carry a name slug and no
   MLBAM, so collisions and misses are possible and are currently uncounted.
6. **Un-clustered rows.** A reliever can sign in several winters; the rows are treated as
   independent.
7. **The eval reads a different object than the board.** The lab's `score_riv` leaves
   `riv_raw` as the raw weighted z (tools/rem_plus_lab.py:233-264) while the served
   `rem_plus.score_riv_plus` DIVIDES by the composite's own pool sd. Within one season both
   orders agree; the market check POOLS winters, so the served index and the evaluated index
   are not the same statistic on that frame. This is the same served-versus-eval normalizer
   defect as re-gate 1, and it is re-gated the same way.

## R2-2 Estimand B1, one target and one scale

`delta_B1 = rho(RIV+_served(walk year), AAV) - rho(REM+(walk year), AAV)`

- **One target:** the AAV of the free-agent contract the reliever signed in the winter
  following his walk year.
- **One scale:** Spearman rank correlation, the same statistic, on the SAME matched rows,
  for both candidates. Because the estimand is a RANK correlation, the log transform in the
  current code is a no-op; "one scale" here means the index-to-target pairing and the
  statistic, not the dollar transform, and that is said out loud because the log looks like
  a choice and is not one.
- **RIV+_served** is the served construction: the per-season composite re-standardized on
  its own pool spread, as `rem_plus.score_riv_plus` ships it. The served INTEGER value is a
  labelled sensitivity beside it.
- **Baseline: REM+**, named explicitly, unrounded `rem_plus_raw`, same rows.

The claim being tested is the one the row actually makes: **RIV+ aligns with reliever pay
better than REM+ does.** Superiority is the primary. Non-inferiority is a separate,
pre-declared fallback with a floor derived in run, not a slack constant.

## R2-3 Pair set, floors and identity

- Rows: `fa_archive.winters[*].signings[*]` with `pos` containing "RP" and a present `aav`,
  matched to the reliever pool of the walk year (winter `year` minus 1).
- Floors: walk-year TBF >= `MIN_TBF_Y` (100), the pool's own reliever definition
  (`is_true_reliever`, openers dropped), both `riv` and `rem` present. One row per
  (player, winter); a player appearing across winters is exactly why v2 clusters on player.
- **Identity:** MLBAM where the repo's canonical identity path can resolve the signing slug;
  otherwise normalized name, and then the gate publishes the matched count, the unmatched
  signing names, and the count of pool arms whose normalized names collide. Identity
  resolution is the binding constraint on this pair set, so it is reported, never assumed.
- **Support floor: 50 matched signings.** Below that the comparison is REFUSED and the lane
  publishes coverage only. The existing code's threshold of 20 is a shrug, not a gate.

## R2-4 Conventions

- **v1:** iid paired resample over matched signings, `BOOT = 2000`, `SEED_R2 = 20260918`.
- **v2:** player-clustered (all of a player's signings move together), **signing-winter
  stratified** (the market analogue of the predictor season, because pay levels differ by
  winter). Same reps, same seed. CIs are wider by design.
- Both published for every cell. Each gap carries an in-run MDE95 (1.645 times the
  bootstrap sd of the gap), published with its sign.

## R2-5 Decision rule, with the registry consequence fixed in advance

| outcome | registry consequence |
|---|---|
| `delta_B1` lo95 > 0 under BOTH conventions | **validated, descriptively.** The row's `predicts`, `baseline` and `metric` lines are rewritten to this market estimand, and the notes must carry the sentence "this is a realized-value record, not a forecast" |
| lo95 <= 0 but lo95 > -MDE95 under both conventions | **stays provisional**, and the claim text drops "better than REM+" for "not separable from REM+ on market alignment at this n" |
| lo95 <= -MDE95 under either convention, or hi95 < 0 | **the claim is REFUTED.** REM+ tracks reliever pay better than the value index built to capture deployed value, so RIV+'s only surviving claim is dead. The verdict moves to **deprecated** with a loss-ledger note, and whether the column stays on the board is an open question for the display lane (section 9) |
| matched n < 50, or identity resolution unpublishable | **REFUSED.** Coverage published, verdict stays provisional with "insufficient support", and the hard date moves to the next free-agent class |

Retired by this document regardless of outcome: the `- 0.02` slack constant, and the
`riv_less_stable_than_rem` clause as a PASS condition.

**The registry grades claims, not pixels.** A served column whose claim has been refuted
carries the refuted verdict and a display debt, because the alternative, holding the verdict
open until someone changes a page, is how a dead claim keeps its badge.

## R2-6 Multiplicity family

One primary test, B1, so k = 1 and Holm is the identity. It is declared anyway so the family
size is on the record and cannot be enlarged after the fact by promoting a disclosure leg.
The disclosure legs in R2-7 and the served-integer sensitivity sit outside the family by
declaration.

## R2-7 The repeatability leg: DISCLOSURE, zero verdict weight

Asked correctly this time, one target at a time, on the same pairs, under both conventions:

- target `RIV+(Y+1)`: does `REM+(Y)` or `RIV+(Y)` predict it better?
- target `REM+(Y+1)`: the same question.

The interpretation is fixed in advance, so the result cannot be spun either way:

- If REM+ beats RIV+ at forecasting next-year RIV+ (the PRIOR, section 0), that CONFIRMS
  RIV+ carries a large non-repeatable deployment and sequencing component, which is
  consistent with the two-number design and is **not** a failure under the descriptive
  frame. It does, however, **forbid any forward reading of the RIV+ column**, and the
  glossary and column copy must say so. That copy change is a display consequence
  (section 9).
- If RIV+ were to BEAT REM+ at forecasting next-year RIV+, the premise of the two-number
  design is wrong and a re-design question opens. It still does not pass this gate, because
  this gate is the market leg.

## R2-8 Pre-registered expectations

1. **REM+ beats RIV+ at forecasting next-year RIV+** (a prior, recorded, not a test).
2. **B1's point estimate favours RIV+** (a prior: 0.576 against 0.508). The open question is
   whether the gap survives an interval under player clustering. The honest expectation is
   that v1 clears and **v2 is a coin flip at this n**, because 271 signings over eleven
   winters cluster hard on repeat free agents.
3. **The canonical-identity pass changes the matched n.** A match count that reproduces 271
   exactly under a stricter identity rule would itself be surprising, and is reported as
   such.
4. If B1 clears under both conventions, RIV+ is a validated descriptive index and STILL not
   a forecaster; the row must say both things in one sentence.

## R2-9 Hard dates

- This document is frozen and committed **2026-09-18**, before any number is computed.
- The battery runs **2026-09-18** on the `data/fa_archive.json` vintage frozen at that
  commit, whose hash is recorded in the artifact.
- **If the battery has not run by 2026-09-25, `riv_plus` stays provisional and its notes
  record the missed clock.**
- The pair set CANNOT grow before the 2026-27 free-agent class closes. Next re-read:
  **2027-03-01**. Reading a partially signed winter is a disqualifying look, and a partial
  winter is also a biased sample, because the top of the market signs first.
- The registry row and `data/riv_plus_eval.json` move in the SAME commit as the result.

---

## 9. Open questions for other lanes, recorded and not decided

This lane owns the labs, the eval artifacts, `data/model_registry.json`, `MODEL_REGISTRY.md`
and this document. It owns no served page, so every display consequence is recorded here and
left to the lane that owns it.

1. **If A1 or A2 is demoted or refuted, what happens to the xHEM+ and xHEM+ Blend columns
   on /mlbstats/?** Pull, relabel or footnote. Not this lane's call.
2. **The gate covers PA >= 200 hitters; the board stamps PA >= 100.** Whether the column
   should gate at the population it was validated on is a display and product question.
3. **HEM+ beside xHEM+.** If HEM+ loses to xwOBA (a prior, R1-10), the ordering of the two
   columns and the word "skill" in the HEM+ header are a copy question for the display lane.
4. **If RIV+ is refuted, does the RIV+ column stay on the Bullpen board?** If it stays, the
   forward-reading prohibition of R2-7 needs column and glossary copy.
5. Any label or copy change these outcomes force belongs to the lane that owns
   `assets/mlbstats.js` and the /mlbstats/ surface copy, including the year-range
   presentation that lane is already revising. Nothing in this document edits a served page.

## 10. Stop rule

- If D0 does not reproduce the published X-H3 and X-H5 numbers, the run STOPS and the
  reproduction failure is the finding.
- If the RIV+ pair set falls below 50 matched signings, or identity resolution cannot be
  published with its drops, the market comparison is REFUSED and the lane ships a coverage
  receipt.
- If nothing separates anywhere, the lane ships three nulls and three verdict moves. That is
  a complete result, and it is the outcome this document is most prepared for.

## 11. What would falsify the shipped constructions, in one list

1. Served xHEM+ fails to beat raw actual wOBA at lo95 > 0 on the X-H3 pair set under either
   convention, at D4.
2. Served fwdHEM+ fails to beat raw xwOBA alone at lo95 > 0 under either convention, at D4.
3. Either arm's D4 gap has hi95 < 0, which refutes the claim rather than failing to
   establish it.
4. D0 fails to reproduce the published numbers, which falsifies the artifact rather than the
   model.
5. RIV+ fails to align with reliever AAV at least as well as REM+, with the margin derived
   in run, under either convention.
6. The RIV+ matched pair set cannot be identified and published, which falsifies the eval
   rather than the index.

---

## 2026-10-15: R1-12's next re-baseline ran as an OWNER-WAIVED EARLY READ (appended by HEM_XWOBA_REGATE_PREREG)

R1-12 registered the next re-baseline, including the `hem_plus` against xwOBA re-gate, for
2026-11-16 or later. The owner waived registered dates on 2026-10-14 (EW3-5) and supplied the
logged season-complete override (EW3-6, 2026 complete as of 2026-10-01). The re-baseline was
pre-registered in its own document, `docs/HEM_XWOBA_REGATE_GATE.md` (committed alone, 2026-10-15),
and run once the same day: 2,134 pairs (the 1,871 here plus 263 of the 2025 to 2026 block; the
1,871-row cells of `data/xhem_served_regate_eval.json` reproduce to four decimals). Verdicts at D4
after Holm k = 3: `xhem_plus` validated (stays), `fwdhem_plus` provisional (stays, straddle under
both), `hem_plus` REFUTED against Savant xwOBA (deprecated; the loss R1-10 carried as a prior is
now a gate result). Artifact `data/hem_xwoba_regate_eval.json`; results in that document's
section 12. Nothing in sections 0 to 11 above was edited.
