# Pre-registration: price the prospect surplus dollar range from the calibrated odds

REGISTERED 2026-09-30, BEFORE any number on the frame below exists. This document is
committed alone; the flag, the scorer and the tests land in later commits, and the one
read runs after them. Where this document and the later read disagree, the read is what
this gate uses, and the disagreement is recorded in section 9 rather than edited away.

Owner answer (2026-09-25, final-pass batch 2): price the prospect surplus dollar range
from the calibrated odds under a new registered gate; a pass ships.

## 0. Honesty clause

Nothing was scored to write this document. No realized surplus was priced, no PIT was
taken, no regression was run on the frame, no frame row was counted. Every number below
is one of: a count over a served artifact (`data/xfv.json`, which carries no outcome); a
constant in committed code or config (`efv_odds_calibration._PLATT`,
`value_framework_config.yaml`); a figure in a commit message (`4f8d57f5`, `707bdabd`); or
a line of code read for what it does.

## 1. What is being fixed, and what already changed since the census

Census M01-08 (2026-09-24): on 146 of 4,688 graded PROSPX pages the eFV P(bust), read
from the calibrated outcome odds (for example 35 percent), sat beside a surplus fan whose
P10 was $11M to $27M. Both cannot hold: the fan prices the bust bucket at the calibration
floor, so a P(bust) of 10 percent or more puts P10 on that floor if the two read one
mixture. Commit `4f8d57f5` labelled the conflict on the card ("Two bases") and moved no
number.

**The active board changed after the census.** Commit `707bdabd` (2026-09-25) made eFV V2
the served eFV. A V2 row reads `p_bucket`, `p_bust` and the dollars off ONE grade through
ONE curve (`efv_score._v2_entry`: `vf.p_bucket_given_fv(grade)`, then
`_reprice_surplus_on_display` at that grade), and the Platt map is not applied there (its
scope limit excludes a consensus-scale key). So on the served V2 rows P(bust) and the
dollar range are already one object. Measured on `data/xfv.json` (2026-09-30) with the
page's own rule (`efvFanBasisConflict`: P(bust) >= .10 with P10, >= .25 with P25, >= .50
with P50 above $1.0M):

| served rows with a fan | rows | rule trips |
|---|---|---|
| active, `efv_v2` | 1,993 | 0 |
| active, `provisional_capped` (thin-sample odds, `efv_ungraded`) | 2,684 | 2 |
| active, no grade basis | 9 | 0 |
| debuted (run_backgrade) | 2,614 | 717 |
| bust (run_backgrade) | 2,209 | 70 |

The two bases survive where the served odds are the Platt-calibrated odds read at the
realized-implied ODDS grade while the dollars are priced at the DISPLAY grade: the three
efv_score seams `run` (resolved, `data/xfv_scored*.json`), `run_live` (the v1 live rows,
superseded on the board by V2 but still written) and `run_backgrade` (the graduate and bust
rows in `data/xfv.json`). This gate covers those seams only. The thin-sample provisional
odds (`efv_ungraded`) are a different calibration, measured on a different population,
and are out of scope (owner question in section 8).

## 2. The incumbent and the candidate

Both arms price the same row at the same DISPLAY grade G_d, the same timing (age, ETA),
the same per-bucket dollar values and the same served dollar calibration
(`vf.apply_calibration`, v6 EV-frame map applied in its fit unit, VAL_1). They differ in
ONE thing, the mixture weights.

- **Incumbent (served today).** weights = `vf.p_bucket_given_fv(G_d)`; bucket dollar
  values `vf._effective_bucket_sv` at G_d rescaled so the mixture mean equals
  `vf.expected_surplus_usd(G_d)`; draws per `vf._sv_draws_mm`; surplus_mm, the band and
  the fan are the calibrated mean and percentiles.
- **Candidate.** weights = the row's SERVED odds vector (the one P(bust) is read from:
  `recalibrate_bucket(p_bucket_given_fv(G_odds))`, or the raw curve at G_odds where the
  seam's provisional guard withholds the map). The per-bucket dollar values are the
  incumbent's, unchanged; the mixture mean is the sum of weight times bucket value, NOT
  re-pinned to `expected_surplus_usd` (re-pinning would inflate the non-bust buckets to
  hold the old mean and defeat the point). surplus_mm, the band and the fan are the
  calibrated mean and percentiles of that one mixture, so the fan's bust share equals the
  served P(bust) exactly. The candidate does not floor its mean at the low-tier anchor
  (the C6 floor is a grade-monotonicity rule; this mixture is not a function of the grade
  alone); disclosed, not hidden.

Code, built after this commit: `value_framework.sv_distribution(..., bucket_probs=...)`
and `value_framework.mixture_surplus_usd(...)` (the candidate mixture);
`efv_score.SURPLUS_FROM_SERVED_ODDS_DEFAULT = False` with the env override
`EEPHUS_SURPLUS_FROM_SERVED_ODDS` ("1"/"0"), read in `_reprice_surplus_on_display` and
passed the served odds only by the three Platt seams. V2 rows never receive odds, so they
are byte-identical under either flag value (a test pins it).

## 3. The frame

**Why not the surplus_backtest_real listing cohorts as they stand.** Those cohorts
(listing years 2017-2019) carry a CONSENSUS FV and no eFV odds. On a consensus key the
served odds are the raw curve (the Platt scope limit in `efv_odds_calibration.py`
excludes it: "the wrong instrument there"), so on that frame the candidate would equal
the incumbent row for row, or would test an object that is never served. The frame
therefore keeps surplus_backtest_real's REALIZED side and its resolved rule, and takes its
prediction side from the rows where the calibrated odds live.

**Rows.** The eFV resolved matrix pool exactly as `efv_score.run` builds it (both sides,
never-MLB recent busts dropped, `_prep(pool, "target_censored", side)`), scored
FORWARD-CHAINED: for each test decision year Y the ridge, its linear output calibration
and the consensus OLS anchor are fit on rows with `decision_year < Y` only (the
`efv_reliability._oof_rows` chain, `MIN_TRAIN 60`, `MIN_TEST 10`). Test decision years
**2016, 2017, 2018, 2019**. Each test row is then priced as `run` prices it:
`G_odds = vf.realized_implied_fv(apply_dispersion_correction(xfv_war), ...)` at
`_grade_map_age(age, 0.0)`, age at `debut_year or 2020`; odds per section 2 with `run`'s
provisional guard (`not src.get("milb")`); `rank_war = (1 - lam) * cons_war + lam *
model_war` with the pinned `blend_lambda(side)`; G_d = the rank-preserving quantile map of
`rank_war` onto the consensus FV distribution of the same (side, test year) fold, which is
`run`'s map applied per fold (no outcome enters it); dollars at `eta = 1.0`.

**Realized surplus.** surplus_backtest_real's construction per row: `career_war` seasons ->
`_impute_seasons` (league-minimum schedule, then arbitration fractions of the tiered
season value) -> `backtest.realized_sv_pv` discounted at the config rate to the decision
year, production valued at the LIVE flat $/WAR (`vf.dollars_per_war_flat()`), which is the
unit the served dollars are in (the v6 map's today-priced targets, scaled by VAL_1).
Classification, surplus_backtest_real's rules verbatim: WAR rows -> resolved when `debut +
5 <= 2025`; MLB time with no WAR rows -> excluded, never zeroed; no MLB time and pro
activity in 2024 or later -> censored, excluded; no MLB time and none since -> washed out,
realized 0. A row with an MLB season before its decision year is excluded.

**Reserved frames.** No decision year from 2020 on is read, so no row touches list
vintages 2020 or 2021 (R-LV, `efv_vintage_frame.RESERVED_LV`), and every debut in the
frame is 2020 or earlier (resolved means `debut + 5 <= 2025`), far from the 2025+ debut
cohorts (R-VM). The scorer asserts both.

**PROSPECT_ANCHOR guard.** Every statistic is POOLED over the whole frame. Nothing is
computed, stored or printed by consensus-FV cell or by any FV band, tier or stratum; no
per-side verdict. `backtest.run_backtest` is NEVER called (it always builds
`by_fv_tier`, `backtest.py:682`), nor `tools/fit_surplus_calibration.py`. The scorer is
`surplus_odds_gate.calibration_metrics` (pooled bias, slope, intercept, PIT coverage, PIT
KS statistic), and a test pins that no key of its output, or of the artifact, contains
"fv" or "tier" as a stratum. No calibration refit is part of this gate: both arms go
through the served map unchanged, so `backtest.fit_calibration_knots` is not needed here.

**Known in-sample advantages, stated before the read.** (i) The Platt constants were fit
on the forward-chained resolved frame over decision years 2014-2020, which contains these
rows, so the candidate's bust weight is partly in sample on the bust event. (ii) The v6
dollar map was fit on the surplus_backtest_real consensus listing pool 2017-2019, which
shares players with this frame; both arms go through it. (iii) The chain's as-of point is
the eFV frame's own (debut year for a debuted row, cutoff plus one for a bust), which is
outcome-dependent by construction; both arms share it. None of these differ by arm except
(i), and (i) favours the candidate.

## 4. The statistics

Per arm, pooled, in served $M:

- `pred_mm`: the arm's calibrated mixture mean (its surplus_mm, unrounded).
- **bias** = mean(realized - pred_mm).
- **slope**, intercept: OLS of realized on pred_mm.
- **PIT**, randomized, over N = 4,000 draws per row (the arm's calibrated draws, seed per
  `vf._sv_draws_mm`). The served map sends the raw bust atom ($0) to its floor
  f = `vf.apply_calibration(0.0)`, so a realized value at or below f is the bust event:
  PIT = U * F(f). Otherwise PIT = F(y-) + U * (F(y) - F(y-)). U ~ Uniform(0,1), one draw per
  row, the SAME U for both arms (seed 20260930).
- **coverage** = share of PIT in [0.10, 0.90] (0.80 nominal). **KS** statistic of PIT
  against Uniform(0,1), descriptive only.

Paired bootstrap, B = 2,000, seed 20260930, resampling PLAYERS (a player on both sides
moves as one cluster), percentile CI95, on:

- `D_cov  = |cov_inc - 0.80| - |cov_cand - 0.80|` (positive favours the candidate)
- `H_bias = |bias_cand| - |bias_inc|` (positive is harm)
- `H_slope = |slope_cand - 1| - |slope_inc - 1|` (positive is harm)

## 5. The pass rule

All four, else FAIL:

1. **G1 one object (structural).** On every frame row the candidate's fan puts exactly
   the served P(bust) on the bust atom (weights equal the served odds to 1e-9). A miss is
   a bug and STOPS the read without a verdict.
2. **G2 primary, coverage.** `D_cov > 0` and its CI95 lower bound `> 0`.
3. **G3 do no harm, bias.** The CI95 lower bound of `H_bias` is `<= 0` (the candidate is
   not resolvably further from zero bias).
4. **G4 do no harm, slope.** The CI95 lower bound of `H_slope` is `<= 0`.

Stop without a verdict (UNPOWERED) if the frame holds fewer than 200 rows.

## 6. What a pass does, and the landing rule

A pass ships per the owner's answer, subject to the landing rule: only before 2026-10-04,
or after the fWAR label epoch's step Z (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`
part 9). If neither holds on the day of the read, the flag stays off and this gate waits.
Shipping = flip `SURPLUS_FROM_SERVED_ODDS_DEFAULT` to True, regenerate the eFV scorer
artifacts and every surplus-dependent artifact downstream of them, and publish the blast
radius (rows moved, before and after totals, named examples) in the commit.

The served GRADE never moves under this gate (odds and dollars only). The odds never move
either: the candidate reads them, it does not change them.

## 7. What a fail does

The flag stays False, nothing served moves, the failing clauses and their numbers are
written into section 9, and the owner question list gets the result.

## 8. Owner questions recorded at registration

- The thin-sample provisional rows (`efv_ungraded`, 2 visible conflicts today) carry a
  different calibrated P(bust). Default: out of scope here, the card keeps its "Two
  bases" note there. Alternative: a separate registration on that lane's own frame.

## 9. Results

(Filled in after the one read. Nothing above this line may be edited once results exist.)

**Verdict: FAIL (G2).** The flag stays False and nothing served moves. Read 2026-09-30,
code `79a637e3` (the build commit; the registration is `fc90703d`, and `79a637e3` also
carries the one pre-read correction to section 3: a frame debut can be 2020). Artifact:
the `surplus_odds_gate` block of `data/surplus_backtest_real.json`.

**Frame.** 8 folds (hit and pit, test decision years 2016 to 2019), 1,214 rows priced;
surplus_backtest_real's rules resolved 438 debuted and 747 washed-out rows and excluded 29
as censored-active. n = 1,185 rows (hit 585, pit 600), 1,185 players. Served bust floor
$0.9784M; realized valued at the live flat $17.1436M per WAR, discounted at the live
config's 0.07 to the decision year.

| pooled, served $M | incumbent | candidate |
|---|---|---|
| PIT coverage, [0.10, 0.90] (0.80 nominal) | 0.7544 | 0.7401 |
| bias, mean(realized - pred) | -0.574 | +1.020 |
| slope, realized on pred | 0.997 | 0.891 |
| intercept | -0.532 | +2.441 |
| PIT KS statistic (descriptive) | 0.104 | 0.055 |

| clause | point | CI95 (B 2,000, player clusters) | result |
|---|---|---|---|
| G1 one object | every row | | pass |
| G2 `D_cov` | -0.0143 | [-0.0295, +0.0000] | **FAIL** |
| G3 `H_bias` | +0.447 | [-1.785, +1.908] | pass (not resolvably worse) |
| G4 `H_slope` | +0.106 | [-0.124, +0.157] | pass (not resolvably worse) |

The landing rule held on the day (before 2026-10-04) and is moot.

**What the read says, without adjudicating beyond the rule.** Drawing the fan from the
served odds makes the PIT histogram flatter overall (KS 0.055 against 0.104) but puts
fewer realized outcomes inside the registered 80 percent band (0.740 against 0.754), and
it moves the mean on 1,163 of 1,185 rows, from an incumbent that sat at slope 0.997 and
bias -0.57 to one that under-predicts realized surplus (bias +1.02, slope 0.89), neither
resolvably. It fails although the Platt odds were partly in sample on the bust event
(section 3 (i)), the one advantage that favoured it.

**Disclosures.** (1) The result was first written as a standalone
`data/surplus_odds_gate_eval.json`. The house rule puts a failed challenger in its
parent artifact, so the same code, unchanged except for where it persists, was re-run
once to write the block; every field of the frame, both arms, the bootstrap, the
decision and the landing record is identical between the two runs (checked field by
field) and the standalone file was removed. That is a persistence move, not a second
look. (2) The frame's display grade is the per-fold quantile map of section 3; the
F-SIDE-FIX top-band re-anchor that `efv_score.run` also applies is not in it, because
its crosswalk is built from the pool's realized WAR. (3) `surplus_backtest_real.run`
now carries this block over when it rewrites its artifact.

**What stays served.** The "Two bases" note keeps showing where the page's rule trips:
717 debuted and 70 bust run_backgrade rows and 2 thin-sample provisional rows (section
1). The active V2 board is one object already (`707bdabd`).

**Owner question.** How should the graduate and bust eFV cards reconcile P(bust) and the
dollar fan now that the registered read failed?
(a) DEFAULT: keep the incumbent pricing and the "Two bases" note (nothing moves).
(b) Ship the candidate anyway as a coherence choice, against a failed read (moves
surplus_mm, the band and the fan on the run_backgrade rows and in `xfv_scored*.json`;
needs a new registration or an explicit owner waiver).
(c) Copy only: print the fan's own bust share beside the calibrated P(bust).
(d) Hide the eFV fan on graduate and bust cards (a debuted player's card already leads
with the Trade Machine value).

## 10. VOID (owner, 2026-09-30; recorded 2026-10-08)

Appended after section 9; nothing above this section was edited.

**The owner declares the read of section 9 VOID.** Owner answer VAL3-Q3, 2026-09-30,
recorded in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under 'ANSWERED 2026-09-30
(AskUserQuestion), Cot's terms, the ETA FanGraphs entry, VAL_3 follow-ups', verbatim:
"**(b) Void and re-register on another frame**: the read is declared VOID in the gate doc
and registry; a new registration names a different admissible frame or reports that none
exists."

**The reason: the frame was substituted.** The task that asked for this gate named
surplus_backtest_real's resolved listing cohorts as the frame. On those rows the candidate
equals the incumbent (a consensus key carries no eFV odds, section 3), so this document
registered a different frame instead: surplus_backtest_real's realized side and resolved
rules on the eFV resolved matrix, forward-chained over test decision years 2016 to 2019.
The substitution was disclosed in section 3 and committed before the read, but the owner
did not choose that frame, and the owner rules that a read on a frame the owner did not
choose does not adjudicate the question.

**What the void means.**

- The verdict of section 9 (FAIL on G2) and every number in it adjudicate nothing. They
  are kept as the record of what was run, not as evidence for or against the candidate.
- `efv_score.SURPLUS_FROM_SERVED_ODDS_DEFAULT` stays False (`efv_score.py:1501`). Nothing
  served moves: no surplus_mm, band, fan, grade or odds. The "Two bases" card note keeps
  showing where the page's rule trips (section 9, 'What stays served').
- The void read's frame is spent for this question. The forward-chained decision years
  2016 to 2019 of the eFV resolved matrix may not be the frame of any later read of this
  candidate, because their numbers on it are known.
- The `surplus_odds_gate` block of `data/surplus_backtest_real.json` carries
  `"void": true` and the reason; nothing in the block was recomputed.
- The registry row `efv_surplus_from_served_odds` records the void as its
  `registration_status`, "void (owner 2026-09-30, frame substituted)". VAL_3 created no
  registry row for this gate, so the row is new here; its verdict is `unvalidated`
  because the registry's verdict field takes only the four enum values
  (`model_registry.VERDICTS`) and a void read leaves the candidate with no measurement.
- `surplus_odds_gate.py` must not be run again. It has no second-run guard, and a re-run
  would overwrite the void block through `persist_block`.

**What follows.** A new registration on another frame, committed alone and before any
number on that frame exists: `docs/efv-2026-09-25/SURPLUS_ODDS_GATE_2.md`. The owner
questions of section 9 (how graduate and bust cards reconcile P(bust) and the fan) and
of section 8 (the thin-sample provisional rows: answered VAL3-Q2 (b), a separate
registration, task SURPLUS_ODDS_THIN_LANE_GATE_REG) keep their defaults until a valid
read exists.
