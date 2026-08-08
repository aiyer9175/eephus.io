# SERVE-PATH INTEGRITY GATE (Lane G, 2026-08-07b)

**Pre-registered 2026-08-08, BEFORE `tools/efv_board_serve_probe.py` grew its serve-path
mode and before any arm was run. Clauses below are frozen. The only text added after the
run is under `## RESULT (appended after the run)`. No clause is amended after it answers.**

Artifact: `data/xfv_serve_path_eval.json`. Lab: `python tools/efv_board_serve_probe.py serve`.

---

## THE QUESTION

`data/xfv_eval.json` publishes a pooled out-of-sample rank claim about an arm it calls
`blend`:

    blend = (1 - lambda) * max(0, OLS(consensus_fv)) + lambda * ridge_prediction

and the artifact's own `conventions.shipped_model` calls that "the headline RANK driver".

The board does not serve `blend`. `efv_score.run_live` serves
`storage.BOARD_GRADE_FIELD == "xfv_grade"`, which is

    xfv_grade = round(vf.outcome_implied_fv(max(-2.0, a + b * ridge_prediction)), 1)

taken from the MODEL leg alone, after the live tilts, and then possibly replaced outright
by `route_floor_grade`. The consensus leg that `blend` carries never reaches it. Nothing in
`data/` scores the number at the end of that chain, so the published accuracy figure may
describe a quantity no user ever sees.

## SCOPE, AND WHAT THIS GATE CANNOT MEASURE

The resolved cohort carries labels; the live board does not. So the chain is replayed on the
resolved cohort under the SAME protocol the published claim uses. Three chain steps have no
resolved-cohort analogue and are therefore OUT of G1 to G4 and handled by G5 instead:

* the live multiplicative tilts (injury, Statcast+, age, role) and the S-XLINE-4 A/CPX
  additive overlay, whose input fields do not exist on a training row;
* `route_floor_grade`, which needs `anchor_constant_only` plus a live provisional sidecar;
* the E-STALE `fv_effective` discount, likewise live-only.

Every one of those is a PENALTY or a SUBSTITUTION applied on top of the graded model leg, so
G2's measured gap is a LOWER BOUND on the served-vs-published divergence, not the whole of
it. That is stated in the result rather than left to be inferred.

## KNOWN CORPUS HAZARD

Session state: the served eFV matrices reproduce `consensus_fv_raw` on 74.8 percent of rows
against the current corpus (53.6 on busts), and Baseball America landed 1,535 rows this
session. This lane replays the model on the COMMITTED training matrices
(`data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`), which is exactly the frame
the published `xfv_eval.json` was computed on. So the corpus drift affects my numbers and the
published numbers IDENTICALLY, and G1 is the check that this is true. A G1 pass means the
comparison is internally valid on the published frame; it does not certify the frame.

---

## CLAUSES

### G1 REPRODUCTION CONTROL (blocking)

The lab's own fold replay must reproduce the published pooled-OOS weighted Spearman for the
`baseline` and `blend` arms of `evals.debuted_km.pooled_oos` in `data/xfv_eval.json` (hit)
and `data/xfv_eval_pitcher.json` (pit).

* **PASS**: all four figures agree within 0.0010 absolute, and both `n` agree exactly.
* **FAIL**: report the lane BLOCKED. Every downstream clause is void, because a serve arm
  measured on a frame that cannot reproduce the published arm proves nothing about the
  published claim.

### G2 SERVE-PATH EQUIVALENCE (the lane question)

Arm `served_grade`, computed out of fold with the fold's OWN output calibration
`(a_f, b_f)` fit on train only via `prospect_path._fit_linear_calibration`:

    served_grade = round(vf.outcome_implied_fv(max(-2.0, a_f + b_f * ridge_pred),
                                               exposure_seasons=6), 1)

scored by the identical instrument (`prospect_path._score` with the same pair weights) on the
identical rows.

* **PASS** on a side if `rho(served_grade) >= rho(blend) - MDE95`, with
  `MDE95 = efv_model.MDE95_POOLED_RHO[side] = 0.044`. The 0.044 is the repo's own measured
  floor for this protocol; it is not a number this lane chose.
* **FAIL** on a side otherwise. A FAIL on either side is the finding: the published claim
  describes a quantity the board does not serve, by more than the protocol can resolve, and
  the served path needs its own scoreboard cell.

Reported alongside, not gated on: the sign, and `rho(served_grade)` against
`rho(baseline)`. If `rho(served_grade) < rho(baseline)` the served number loses to consensus
FV, which is a strictly stronger statement than G2 and is reported as such.

### G3 ATTRIBUTION (read only if G2 fails)

Two counterfactual arms separate the two candidate causes. Neither is a ship proposal.

* `blend_graded` = the identical grade map, clamp and 1dp rounding applied to the BLEND WAR
  instead of the model WAR. Isolates the tie/clamp/rounding cost.
* `ridge` = the pure model leg, ungraded. Isolates the dropped consensus leg.

An attribution claim ("the loss is X, not Y") is permitted ONLY when the two arms separate by
more than MDE95 on the side being discussed. Otherwise the report says the two causes are not
separable at this power and stops.

### G4 CONTROLS THAT COULD EMBARRASS ME

Each control is written so that it CAN fail; a control that cannot fail is not reported as a
pass.

* **C-a PERMUTATION.** `served_grade` values permuted WITHIN fold, RNG
  `random.Random(20260808)`, iteration over a sorted list of integer indices. Never a set,
  never `hash()` of a string. **PASS if `abs(rho) < 0.05` on both sides.** A permuted arm that
  reproduces the served rho would mean the instrument, not the model, is producing the number.
* **C-b TIE MASS.** Share of pooled test rows whose `served_grade` sits exactly on the
  `outcome_implied_fv` floor knot (`efv_score._outcome_floor_knot()`), and the count of
  DISTINCT served values. If the floor share exceeds 0.50, a near-constant arm is a live
  explanation and the report must say the rho is substantially a tie artifact rather than a
  ranking. Reported unconditionally, gated at 0.50.
* **C-c AFFINE INVARIANCE.** `rho(a_f + b_f * ridge_pred)` UNCLAMPED must equal `rho(ridge)`
  to 4dp on both sides, since a strictly increasing affine map cannot change Spearman. This
  fails if any fold fits `b_f <= 0`, and it is the check that my per-fold calibration is
  wired the way production's is.
* **C-d NULL-STEP INVARIANCE.** Applying the chain to the BLEND (`blend_graded`) must leave
  `rho` unchanged from `blend` up to the tie cost alone. Reported as the tie cost, and it is
  the quantity C-b's share is supposed to explain. If C-b's floor share is small AND
  `blend_graded` still loses materially to `blend`, my chain replay is suspect and I say so.

**MULTIPLICITY.** G2 is 2 tests (one per side). G4 is 4 controls x 2 sides. Every quoted "k of
n significant" is stated with its n.

### G5 LIVE-ONLY CONTAINMENT

* **L1 FIELD CONTAINMENT.** The ten live-only fields
  `statcast_plus, age_now, il_on, il_type, il_days_12mo, il_stints_12mo, eta_years,
  fv_effective, anchor_stale_discount, anchor_constant_only`
  must appear on ZERO rows of `data/xfv_hitter_matrix.json` and `data/xfv_pitcher_matrix.json`,
  and on at least one row of each live matrix. Checked over ALL rows, not a sample.
* **L2 CALL-SITE CONTAINMENT (AST, not grep).** Parse `efv_score.py` with `ast` and collect,
  for each of `_injury_factor, _age_factor, _role_factor, _statcast_factor, overlay_fv,
  route_floor_grade`, the set of enclosing function names of every call. That set must be a
  subset of `{run_live, run_backgrade}`. In particular `run` and any eval path must not appear.
  A string grep would match comments; the AST cannot.
* **L3 S-XLINE IS THE DECLARED EXCEPTION, VERIFIED NOT ASSUMED.** `XLINE_HIT_DEFAULT` and
  `XLINE_PIT_DEFAULT` are read live from `efv_statcast_line`. Then, for training-matrix
  players with AAA 2023+ coverage, `efv_dataset._milb_features` is recomputed twice in one
  process with `EEPHUS_XLINE_HIT`/`EEPHUS_XLINE_PIT` forced to "1" and to "0".
  **PASS** requires BOTH: (i) at least one training player's recomputed MiLB block DIFFERS
  between the two settings, proving S-XLINE reaches training rows at all; and (ii) on those
  differing players the COMMITTED training-matrix MiLB block matches the flag-ON
  recomputation and not the flag-OFF one. Clause (i) alone would be vacuous about what
  shipped; clause (ii) alone would be vacuous if nothing ever differs.
* **L4 E-STALE CONTAINMENT.** `fv_effective` and `anchor_stale_discount` present on live
  matrices, absent from training matrices (subsumed by L1, reported separately because the
  brief names it separately).

### G6 ABSTENTION ON NO-TRACK-RECORD ROWS

* **A1 ARITHMETIC.** Per side, `len(live_matrix) - count(rows with falsy milb)` must equal
  `len(xfv_scored_live*.json)` EXACTLY. An off-by-any is a second exclusion path nobody
  documented.
* **A2 DISJOINTNESS.** No `player_key` of a falsy-`milb` live row may appear in the scored
  live artifact for that side.
* **A3 LOAD-BEARING.** `efv_model.served_ridge_weights` must expose `milb_missing` as a
  served feature with a NEGATIVE standardized weight on at least one side. If the weight were
  zero or positive, the abstention would be protecting draftees from nothing and the docstring
  claim would be stale. This clause can fail.

### G7 POOL-RELATIVE DISPLAY GRADE

`xfv_grade_display` is a per-side rank-quantile map of `rank_war` onto the LIVE pool's own
`consensus_fv` distribution (`efv_score.py:1526-1559`, `:2184-2200`). It is exported as
`xfv_grade_quantile` and it prices `surplus_mm`, `band_p10_mm`, `band_p90_mm` and the
`dist` fan. So a player's dollars are a function of other players.

**THE CONFOUND, AND HOW IT IS REMOVED.** Two adjacent vintages differ in BOTH pool
composition and player performance. Rather than diff and attribute, the primary measurement is
restricted to a subset where the confound is absent BY CONSTRUCTION:

    UNCHANGED SUBSET = players in both vintage pools whose replayed rank_war is
    bit-identical across the two vintages.

For a member of that subset nothing about him changed, so 100 percent of his
`xfv_grade_display` movement is pool composition. No decomposition, no attribution, no
assumption. Vintages: D1 = 2026-08-02, D2 = 2026-08-07, the two adjacent full board
refreshes in `data/timeseries.json`, replayed as-of with the same machinery
`efv_score.score_history` uses.

* **P1 MAGNITUDE.** Report `n_unchanged`, and median / P90 / max of the absolute display-grade
  move on that subset, plus the count and share exceeding **0.5 FV, which is `movement._EPS`,
  the repo's OWN published movement dead-band**. Not a threshold this lane invented.
* **P2 DOLLARS.** Re-price `vf.expected_surplus_usd` at both display grades holding position,
  age and eta fixed. Report median / P90 / max absolute dollar move on the unchanged subset.
* **P3 REPLAY FIDELITY (a control that can fail).** The replay's D2 display grades must reach
  Spearman >= 0.80 against the committed `xfv_grade_display` in
  `data/xfv_scored_live*.json` on the intersecting players. **FAIL** means the replay does not
  describe production, and P1/P2 are then reported explicitly as replay-only quantities with
  that stated in the headline.
* **P4 FULL DECOMPOSITION (secondary, for magnitude context only).** On all players in both
  pools, with `G(r; P)` the explicit quantile map:
  `own_i = G(r_i2; P1 with i set to r_i2) - G(r_i1; P1)`,
  `pool_i = G(r_i1; P2 with i set to r_i1) - G(r_i1; P1)`,
  `resid_i = D_i - own_i - pool_i`. Separable by construction because `G` is an explicit
  function evaluable at any `(r, P)`. Report the share of total absolute movement carried by
  the pool term.
* **MATERIALITY, AND IT IS MINE.** The pool term is called MATERIAL iff at least **5 percent**
  of the unchanged subset moves by more than `movement._EPS`. The 0.5 FV is the repo's; the
  **5 percent is a threshold this lane added and the brief does not contain**. If it decides
  the verdict it is disclosed in the headline, per the standing rule.
* **UNDERPOWER.** If `n_unchanged < 100`, P1/P2 are reported as underpowered and no
  materiality verdict is issued.

---

## RESULT (appended after the run)

Run 2026-08-08, `python tools/efv_board_serve_probe.py serve`. Every figure below
reproduces from `data/xfv_serve_path_eval.json`; no number in this section exists only in
prose.

### Verdict

**G2 PASSES on both sides. The serve chain does not measurably degrade the ranking on the
resolved cohort, and on the hitter side it very slightly improves it. The lane's own prior
was wrong and the artifact says so.** What the run did find is smaller in effect and
larger in consequence: the published gate is decided by margins far below its own
measurement floor, on a population that is not the board.

### G1 REPRODUCTION CONTROL: PASS

| side | arm | replay | published | n |
|---|---|---|---|---|
| hit | baseline | 0.3919 | 0.3919 | 755 |
| hit | blend | 0.3993 | 0.3993 | 755 |
| pit | baseline | 0.2494 | 0.2495 | 890 |
| pit | blend | 0.2561 | 0.2562 | 890 |

All four inside the 0.0010 tolerance, both `n` exact. The comparison is internally valid
on the published frame.

### G2 SERVE-PATH EQUIVALENCE: PASS on both sides (2 of 2 tests)

| side | rho(baseline) | rho(blend) | rho(served_grade) | served minus blend | bound |
|---|---|---|---|---|---|
| hit | 0.3919 | 0.3993 | **0.4001** | +0.0008 | -0.044 |
| pit | 0.2494 | 0.2561 | **0.2389** | -0.0172 | -0.044 |

The board grade is not a materially different ranking from the published `blend` at this
protocol's resolving power. On the hitter side it is fractionally better, because the
`outcome_implied_fv` clamp ties together rows the blend ordered on noise.

**The reportable observation, which G2 does not gate:** on the PITCHER side the served
grade falls BELOW consensus FV (0.2389 vs 0.2494) while the published blend sits above it
(0.2561). `xfv_eval.json` names its flagship criterion "beat consensus FV on pooled-OOS
Spearman". That criterion is satisfied by an arm the board does not serve and is not
satisfied by the one it does.

**And the margins are all below the floor.** Against `MDE95 = 0.044`: blend beats baseline
by 0.0074 on hit (0.17x the floor) and 0.0067 on pit (0.15x). The served grade trails
baseline by 0.0105 on pit (0.24x). None of the three is resolvable. So the sign flip above
is not evidence that the served number is worse than consensus; it is evidence that the
published gate is being decided inside its own noise, which is the same frontier the
master plan already recorded as CLOSED.

**This gap is a LOWER BOUND.** See the census below for what the resolved cohort cannot see.

### LIVE-BOARD CENSUS (descriptive, no pass clause, committed artifacts only)

This is the part the published claim is silent about, and it needed no modelling.

| | hit | pit | combined |
|---|---|---|---|
| rows scored live | 2,061 | 2,353 | 4,414 |
| flagship grade sat exactly on the FV20 floor knot | 1,590 (77.2%) | 1,729 (73.5%) | 3,319 (**75.2%**) |
| served on the PROVISIONAL grade map instead (`grade_basis = provisional_capped`) | 1,096 (53.2%) | 1,332 (56.6%) | 2,428 (**55.0%**) |
| served flat at 20.0 | 494 | 397 | 891 |
| carrying a Statcast+ tilt | 1,591 | 1,861 | 3,452 (78.2%) |
| carrying an injury tilt | 199 | 320 | 519 |
| distinct served grade values across the whole side | 324 | 284 | |

Three quarters of the live board has a flagship model grade of exactly the floor knot, and
**55.0 percent of served rows are not on the flagship grade map at all**: they are served
through `efv_ungraded._GRADE_MAP`, which the eval never evaluates. By contrast the eval
cohort's own floor share is 17.2 percent (hit) and 13.6 percent (pit), measured by C-b.

So the published accuracy figure is computed on a population where the served quantity is
informative and served to a board where, for most rows, it is not. That is the lane's
finding, and it is a coverage gap rather than an accuracy error.

### G3 ATTRIBUTION: NOT SEPARABLE, and the clause is honoured

| side | baseline | ridge | blend | cal_affine | grade_unrounded | served_grade | blend_graded |
|---|---|---|---|---|---|---|---|
| hit | 0.3919 | 0.3959 | 0.3993 | 0.3963 | 0.4006 | 0.4001 | 0.3999 |
| pit | 0.2494 | 0.2387 | 0.2561 | 0.2369 | 0.2388 | 0.2389 | 0.2551 |

Tie-and-round cost vs blend: +0.0006 (hit), -0.0010 (pit). Total serve cost vs blend:
+0.0008 (hit), -0.0172 (pit). The two arms separate by 0.0002 and 0.0162, both under
MDE95 = 0.044, so `causes_separable_at_mde` is **false on both sides** and the
pre-registered clause forbids an attribution claim. It is tempting to say "the pitcher
loss is the dropped consensus leg, not the grade map", and the numbers point that way, but
the clause was written before the numbers and it is not amended now. Not separable at this
power.

MAE is reported in the artifact for every arm and is meaningless for the graded arms: they
are on the 20-80 FV scale and the target is WAR, so `served_grade` shows MAE around 40 by
construction. Only Spearman is comparable across these arms.

### G4 CONTROLS: 6 of 8 pass (4 controls x 2 sides)

* **C-a PERMUTATION: PASS both sides.** rho = 0.0396 (hit), 0.0407 (pit), bound 0.05.
  Supplementary, added after C-a passed and deciding nothing: 200 further draws give a null
  centred at **+0.0138 / +0.0134**, not at zero, with P95 at +0.0705 / +0.0753. The offset is
  the between-fold component that within-fold permutation preserves by construction. The
  single pre-registered draw therefore sits in the body of its own null, which is what the
  control needed to show.
* **C-b TIE MASS: PASS both sides.** Floor share 0.1722 (hit) / 0.1360 (pit), bound 0.50;
  235 / 176 distinct served values. The eval-cohort served arm is not a near-constant. As
  the census above shows, the LIVE board is a different story and C-b does not cover it.
* **C-c AFFINE INVARIANCE: FAIL both sides.** 0.3963 vs 0.3959 (hit), 0.2369 vs 0.2387
  (pit). The clause required exact equality and is reported failed.
  **Post-hoc diagnosis, not a substitute clause:** `within_fold_affine_invariance_holds` is
  **true on both sides**, and no fold fit a non-positive slope
  (`folds_with_nonpositive_calibration_slope` empty). So the failure is entirely the pooling
  of folds that each carry their OWN `(a_f, b_f)`, the same cross-fold reordering
  `efv_model._lofo_calibrate`'s corrected docstring already records. The clause was
  mis-specified by me: the invariance it asserts holds within fold, not pooled.
  **Consequence, bounded:** production fits ONE `(a, b)` on the full pool, so the live board
  has no cross-fold artifact at all; my replay adds one, of magnitude 0.0004 (hit) and
  0.0018 (pit). That is 10 percent of the pit serve gap of 0.0172 and cannot explain it.
* **C-d:** `blend_graded` 0.3999 / 0.2551, reported into G3.

### G5 LIVE-ONLY CONTAINMENT: PASS (L1, L2, L3, L4)

* **L1 PASS.** Of the ten live-only fields, **zero** appear on any of the 1,917 hitter or
  2,040 pitcher TRAINING rows. All ten appear on all 2,136 / 2,465 LIVE rows. Checked over
  every row, not a sample.
* **L2 PASS (AST).** `_injury_factor`, `_age_factor`, `_role_factor` are called only from
  `run_live` and `run_backgrade`; `_statcast_factor`, `overlay_fv` and `route_floor_grade`
  only from `run_live`. `run` and the eval paths appear nowhere. Note that `_age_factor` and
  `_role_factor` would fire on a training row if they were ever called there, because both
  fall back to `milb.age` which training rows DO carry. Containment here is by call site, not
  by data, and L2 is the clause that actually holds it.
* **L3 PASS, and it is the declared exception, verified.** `XLINE_HIT_DEFAULT` and
  `XLINE_PIT_DEFAULT` both read True. Toggling `EEPHUS_XLINE_HIT` / `EEPHUS_XLINE_PIT` in
  one process over debuted training rows changed the recomputed MiLB block on **25 of 229
  hitters and 23 of 400 pitchers**, and on **every one of those 48 rows the committed
  training matrix matches the flag-ON recomputation and none matches flag-OFF**
  (`committed_matches_flag_off = 0` on both sides). So S-XLINE does reach the training
  matrix, by design, and the shipped matrix carries the adjusted values. Confirmed, not
  assumed.
  **Correction recorded rather than hidden:** the first execution of this clause
  reconstructed `_milb_features` with `decision_year = int(cutoff[:4])` and no `cutoff`
  argument, which is not what `efv_dataset.py:1127` passes. Under that wrong reconstruction
  1 of 23 hitter and 4 of 22 pitcher differing rows matched neither branch. The clause text
  was not changed; the reconstruction was corrected to `(debut_year, cutoff=cutoff)` and
  re-run, and both runs are recorded here.
* **L4 PASS.** `fv_effective` and `anchor_stale_discount` are on every live row and no
  training row, so the E-STALE discount is live-only.

### G6 ABSTENTION: PASS (A1, A2, A3)

* **A1 PASS.** hit 2,136 live minus 75 with no MiLB block = 2,061 scored, exactly.
  pit 2,465 minus 112 = 2,353, exactly. No undocumented second exclusion path.
* **A2 PASS.** Zero no-MiLB player_keys appear in either scored-live artifact.
* **A3 PASS, with two qualifications the clause surfaced.** `milb_missing` is a served
  hitter feature with standardized weight **-0.0174**, so the sign is right and the
  abstention is load-bearing on the hitter side.
  (i) The magnitude is not large. `run_live`'s docstring says milb_missing carried a "large
  negative weight"; -0.0174 is the smallest-magnitude weight of the 14 hitter features, next
  to `fv` at 2.5022. The abstention is still correct, but the docstring overstates the
  penalty it is avoiding.
  (ii) **`milb_missing` is not a pitcher feature at all.** The served pitcher ridge has nine
  keys and that is not one of them. So on the pitcher side the abstention is preventing a
  trained penalty that does not exist, and its 112 skipped rows are being withheld for a
  reason the pitcher model cannot express. That is not a defect, but the docstring's stated
  rationale is hitter-only and reads as if it were both sides.

### G7 POOL-RELATIVE DISPLAY GRADE: MATERIAL AT REFRESHES, NEGLIGIBLE ON QUIET DAYS

Replay fidelity (P3) passes everywhere: Spearman against the committed production
`xfv_grade_display` is 0.8832 (hit) and 0.8880 (pit) on the primary pair, 0.8869 / 0.8669 on
the sensitivity pair, against a 0.80 bound.

**Primary pair, 2026-08-02 to 2026-08-07** (pre-registered). Unchanged subset = players whose
replayed `rank_war` AND `consensus_fv` are bit-identical across both vintages, so 100 percent
of their display movement is other players moving. No decomposition, no confound.

| | hit | pit |
|---|---|---|
| n unchanged | 1,045 | 970 |
| median abs pool-only display move | 0.0 FV | 0.0 FV |
| P90 | 0.7 FV | 0.9 FV |
| max | 1.3 FV | 1.5 FV |
| n over `movement._EPS` = 0.5 FV | 219 (**21.0%**) | 185 (**19.1%**) |
| P90 abs surplus move | $0.100M | $0.154M |
| max abs surplus move | $0.397M | **$1.456M** |

Pool composition carries **88.2 percent (hit) and 81.7 percent (pit)** of all absolute
display-grade movement between the two vintages (own-rank 12.7 / 20.3, interaction residual
1.8 / 3.6).

**Sensitivity pair, 2026-08-05 to 2026-08-06** (supplementary, added after the primary pair
returned, decides nothing). A routine adjacent day:

| | hit | pit |
|---|---|---|
| n unchanged | 1,084 | 1,016 |
| max abs pool-only display move | 0.3 FV | 0.5 FV |
| n over 0.5 FV | **0** (0.0%) | **1** (0.1%) |
| max abs surplus move | $0.042M | $0.063M |
| total abs display movement across the pool | 4.2 FV | 2.6 FV |

versus 202.7 FV and 272.6 FV on the primary pair. The share split is degenerate on this pair
(pool = 1.000 because nobody's own rank moved at all) and is not quoted as a finding; the
MAGNITUDE is the finding.

**Verdict: MATERIAL, and the self-added threshold did not decide it.** The materiality rule
is "at least 5 percent of the unchanged subset moves more than 0.5 FV". The measured shares
are 21.0 and 19.1 percent, roughly 4x the bar, so the verdict is unchanged for any threshold
up to 19 percent. The 0.5 FV is `movement._EPS`, the repo's own dead-band.

**Scope, stated because it changes what should be done about it.** The pool term is not a
constant nuisance tax; it is concentrated at board-refresh events, where the reconstructed
pool nearly doubled (1,064 to 2,055 hitters). On quiet days it is essentially nil. So
de-noising and disclosure should be refresh-scoped, not always-on.

**One honest limitation on the SHARE figures only.** The replay holds within-season MiLB
features fixed across the two vintages (both dates are in the same season, which is what
makes the unchanged subset exact), so it sees less own-rank movement than production does.
The 88.2 / 81.7 percent pool SHARE is therefore an upper bound. The pool-term MAGNITUDES in
the tables above are not affected by this, because they are a property of the quantile map
and the pool, measured on players whose own inputs did not move.

**Which surfaces this reaches.** `xfv_grade_display` is exported as `xfv_grade_quantile` and
was retired as the board headline on 2026-07-25, so the BOARD grade is not pool-relative. It
still prices `surplus_mm`, `band_p10_mm`, `band_p90_mm` and the `dist` fan, and it is still
read as a displayed grade by `fantasy_export` (dynasty board eFV column and score),
`card_market_export`, and `fa_fit` (`blocker_fv_min`). The brief's framing that "a player's
displayed grade and his surplus dollars move" is right about the dollars and about those
three surfaces, and out of date about the main board.

### Self-added thresholds, disclosed

| threshold | mine? | did it decide a verdict? |
|---|---|---|
| G7 materiality at 5 percent of the subset | yes | **no**, measured 19.1 to 21.0 percent |
| G1 reproduction tolerance 0.0010 | yes | no, max observed deviation 0.0001 |
| C-a permutation bound 0.05 | yes | **yes**, and it was close: 0.0396 and 0.0407 are 0.79x and 0.81x of the bound. A bound of 0.03 would have failed this control. The supplementary 200-draw null is the reason I still believe the pass |
| G7 fidelity bound 0.80 | yes | no, measured 0.8669 to 0.8880 |
| G7 underpower floor n >= 100 | yes | no, n = 970 to 1,084 |

Everything else is the repo's own: `MDE95_POOLED_RHO = 0.044`, `movement._EPS = 0.5`.

### Multiplicity

G2: 2 tests, 2 pass. G4: 8 tests (4 controls x 2 sides), 6 pass, 2 fail (C-c, both sides,
diagnosed above). G5: 4 clauses, 4 pass. G6: 3 clauses, 3 pass. G7: 2 sides, both material
on the primary pair, neither material on the sensitivity pair.
