# The provisional grade map: should `efv_ungraded._grade` be re-pointed onto the board's map?

Lane: LANE-PROV-MAP. Owner decision 2026-07-30: **re-point the provisional grade map onto
the same map the flagship board uses, with a gate.**

Gate standard: `docs/EFV_GATE_STANDARD.md`. Predecessors:
* `docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md` - LANE-P2 moved the FLAGSHIP `xfv_grade`
  onto `value_framework.outcome_implied_fv` on 2026-07-30.
* `docs/efv-2026-07-30/ORPHAN_ROUTING.md` section 5(b) - found and registered the resulting
  two-map gap, explicitly **GATED, NOT FIXED**, and named this as the highest-value
  follow-up it found.
* `docs/EFV_FRONTIER_AUDIT.md` follow-up - the 2026-07-25 owner call that RESTORED the
  provisional soft cap (`UNCAPPED_GRADE = False`).
* `data/xfv_thin_pbust_eval.json` / `tools/pbust_thin/` - the 19,812-row cohort that
  measured this population's realized outcomes **as a function of this module's own grade**.

Lab: `tools/provisional_grade_map_lab.py`. Artifact: `data/provisional_grade_map_eval.json`.
Registry row: `xfv_provisional_grade_map`.

**PART 1 WAS WRITTEN AND COMMITTED TO DISK BEFORE ANY PRODUCTION MODULE WAS EDITED AND
BEFORE ANY CANDIDATE GRADE WAS SCORED.** What preceded it is the description of the two maps
in 1.1 and 1.3, which is arithmetic on two committed functions, not a result. PART 2 is
appended after.

---

# PART 1. Pre-registration

## 1.0 ONE CORRECTION TO THE BRIEF, MADE BEFORE ANYTHING ELSE

The brief says LANE-P2 "left `efv_ungraded._grade` on the retired `realized_implied_fv`".
**It never was on `realized_implied_fv`.** `git log -S"realized_implied_fv" -- efv_ungraded.py`
returns nothing: the module has carried its own bespoke, hand-calibrated linear map since it
was written (`efv_ungraded._GRADE_MAP`, `grade = BASE + SLOPE * war_pred`, hit 27.0 + 3.8w,
pit 25.0 + 4.5w, floored at 20, soft-ceilinged above a knee).

So the platform does not have two maps of predicted WAR. It has **three**:

| map | where | form |
|---|---|---|
| `vf.outcome_implied_fv` | flagship `xfv_grade` (all three scoring paths) | inverse of the empirical pooled curve E[6yr bWAR given consensus FV] |
| `vf.realized_implied_fv` | flagship `_odds_grade` (odds + the dollar seam) | inverse of the valuation core's own forward map; reads age and position |
| `efv_ungraded._GRADE_MAP` | provisional `xfv_grade` | a bespoke linear map with a soft ceiling, calibrated to a spec |

The SUBSTANCE of the brief is exactly right and is not weakened by this: the two maps that
both write a field called `xfv_grade` disagree by close to ten FV through the 1.5 to 3.5
predicted-WAR band, which is where prospects live. `ORPHAN_ROUTING.md` 5(b) measured it and
`jacob_friend` (43.5 flagship -> 35.1 provisional) is the case that surfaced it. This lane
adjudicates that gap. It is simply not a leftover from today's ship; it is older than that,
and it is a different shape of defect (a bespoke scale, not a retired one).

## 1.1 WHY THE GAP MATTERS: the two grades are compared directly, in two orderings

This is the whole case for a re-point and it is verified in code, not assumed.

1. **The client board sorts one joint pool on one field.** `prospx/index.html`:
   `buildEfvRankMap()` builds `pool = DATA.players.concat(provPlayers())` and sorts it on
   `efvRankValue -> efvBoardValue(x) = x.xfv_grade`. Provisional rows supply that field from
   `efv_ungraded._grade`; graded rows supply it from `vf.outcome_implied_fv`. The two maps
   meet inside one `sort` comparator.
2. **The platform explicitly decided NOT to demote provisional rows in that ordering.**
   `_PROV_RANK_PENALTY = 0`, the F2 repair of 2026-07-25, with the stated reason that the
   sort value must equal the displayed value. A ten-FV map gap through the prospect band is
   exactly the demotion that decision retired, applied silently through the scale instead of
   openly through a penalty.
3. **The farm score consumes both on one axis.** `storage._load_ungraded_by_org` feeds
   provisional rows into the org pool; `_top_end_points` / `_depth_points` rank that pool on
   `_eff_grade(p) = p["xfv_grade"]` and convert with `_fv_to_points`, whose tiers are steeply
   convex (FV 35 -> 0.3 points, 40 -> 1.0, 45 -> 3.5). A ten-FV shift there is a factor of
   three to ten in points.

So the coherence complaint is real and it reaches two served orderings.

## 1.2 WHAT THE RE-POINT DOES NOT BUY, stated before the measurement

`vf.outcome_implied_fv`'s own shipped documentation (`value_framework.py:2813-2820`, and
`POOLED_OUTCOME_REFIT.md` 1.2) says: the curve is fitted on rows with consensus FV >= 34.9,
it is nearly flat below 45, and **"a grade under about 45 is a display re-spread. Never
present it as calibrated."**

The provisional pool's grades today run 20.0 / 25.7 / 46.6 at min / median / max, with
92.3% at or below 30 and exactly ONE row at or above 45. **Essentially the entire
population sits under the outcome curve's data floor.** Therefore:

> **A re-point buys COHERENCE. It buys ZERO CALIBRATION for this population, by the target
> map's own documentation.** Any argument for it has to rest on the two orderings in 1.1,
> and any cost it carries has to be weighed against coherence alone.

That is written here so PART 2 cannot quietly promote the change into an accuracy win.

## 1.3 THE CAP INTERACTION, worked out and stated explicitly (the owner's first ask)

The soft cap is `g' = KNEE + (CEIL - KNEE) * (1 - exp(-(g - KNEE)/SOFT))` applied to the
LINEAR grade, plus a `min(grade, 30.0)` sub-floor cameo cap for lines under
`_MIN_EXPO_PA`/`_MIN_EXPO_BF`. Its constants are FV numbers. Under the incumbent LINEAR map
an FV constant is also a WAR constant, because `g = BASE + SLOPE*w` is invertible in one
step. **Under `outcome_implied_fv` it is not**, and the two readings come apart violently:

| constant | its FV value | binds at predicted WAR, INCUMBENT map | binds at predicted WAR, OUTCOME map |
|---|---|---|---|
| hit KNEE | 43.0 | **4.211** | **1.125** |
| hit CEIL | 49.0 | 5.789 (asymptote) | 4.698 |
| hit sub-floor | 30.0 | 0.789 | **0.028** |
| pit KNEE | 34.0 | **2.000** | **0.061** |
| pit CEIL | 38.0 | 2.889 (asymptote) | 0.176 |
| pit sub-floor | 30.0 | 1.111 | **0.028** |

**Read the pitcher row.** Keeping KNEE 34 / CEIL 38 as FV constants after a re-point turns
the soft cap from a bound that binds at 2.0 predicted WAR into one that binds at 0.061, and
turns CEIL 38 from an asymptote nothing reaches into a ceiling that every arm with more than
0.18 predicted WAR is compressed against. The cap would stop being a top-end bound and
become a near-universal compressor of the whole pitcher pool into a four-FV window. That is
not "the cap doing what it did"; it is a different instrument.

**The fork, named.** The cap's constants are simultaneously two things, and a nonlinear
re-point can preserve at most one:

* **The FV reading** - the words in the module: "a true 45+ would have been graded", "an
  un-scouted player still can't claim top-prospect status", "cap a cameo at org-filler". Keep
  the FV constants; the cap's ACTION changes completely (the table above).
* **The WAR reading** - what the cap actually does to the model's own quantity. It has an
  EXACT translation into WAR space, and the algebra is a one-liner because the incumbent map
  is affine: with `KNEE_W = (KNEE-BASE)/SLOPE`, `CEIL_W = (CEIL-BASE)/SLOPE`,
  `SOFT_W = SOFT/SLOPE`, applying the same exponential compression to `w` and then reading
  `BASE + SLOPE*w'` reproduces the incumbent grade **identically**. So
  `w' = KNEE_W + (CEIL_W-KNEE_W)*(1-exp(-(w-KNEE_W)/SOFT_W))` followed by
  `outcome_implied_fv(w')` binds on exactly the same players, at exactly the same predicted
  WAR, with exactly the same compression of the model's estimate. Its FV OUTPUTS, however,
  no longer say what the module's words say: a capped cameo would read FV 40.9 (hit) / 42.9
  (pit) instead of 30, and the hitter ceiling would sit at FV 50.2, above the CEIL 49 the
  2026-07-25 restoration used as the graded path's own asymptote.

**Neither branch is a no-op.** That is the finding the owner asked for, and it means "re-point
the map and leave the cap alone" is not a conservative option; it is the most destructive of
the three. Both branches are MEASURED in PART 2. A third branch, re-choosing the FV constants
so the cap's measured effect is preserved, is **excluded in advance**: that is tuning to a
target, the constants are an owner call with their own recorded rationale, and this gate has
no authority over them.

## 1.4 A SECOND INTERACTION THE BRIEF DID NOT NAME: a fitted head reads this grade

`efv_ungraded._THIN_PBUST_HEAD` is `logit p_bust = a + b*(grade - 30) + level_offset`, fitted
on 19,812 player-seasons where, in the lane's own words, "every row is re-scored through THIS
module's own grade map". Its slope is `b = -0.14875` (hit) / `-0.16981` (pit).

Re-pointing `_grade` moves that head's ARGUMENT by roughly +10 FV through the band, which
moves its output by `b * 10` in logit space with no refit: a DSL hitter at grade 35 goes from
p_bust 0.971 to 0.883 purely because the scale under him changed. **That is a fitted model
being evaluated off its fitted support, silently.**

Three further quantities on a provisional row read `grade` DIRECTLY, unlike the flagship path
where surplus re-prices off `xfv_grade_display`:

    surplus = vf.expected_surplus_usd(grade, ...)          # efv_ungraded.py:681
    dist    = vf.sv_distribution(grade, ...)               # :682
    probs   = vf.p_bucket_given_fv(grade, is_pit)          # :684

So the true blast radius of a naive re-point is not "3,404 grades". It is 3,404 grades PLUS
surplus dollars, PLUS the uncertainty band, PLUS `p_bucket`, PLUS a silent re-argument of a
fitted head. **This lane therefore PINS every one of those to the incumbent grade**, computed
alongside the new one as `_legacy_grade`, exactly as `efv_score` pins `_odds_grade` to the
retired map (`POOLED_OUTCOME_REFIT.md` 1.3). The blast radius of the candidate is then
`xfv_grade` and `xfv_history[].x` alone, which is what the coherence argument in 1.1 is about.

## 1.5 The candidates

| id | what it is |
|---|---|
| **V0** | re-point `_grade` onto `vf.outcome_implied_fv`, cap constants left as FV numbers (the literal reading of the brief) |
| **V1** | re-point, with the soft cap and the cameo sub-floor translated into WAR space by the exact algebra in 1.3 |
| **KEEP** | no-ship: the bespoke map stays, the three-map split is registered permanently |

In both V0 and V1 the surplus / band / `p_bucket` / thin-p_bust seam is PINNED to
`_legacy_grade` per 1.4.

## 1.6 What is measured

On the served pool (`data/xfv_ungraded.json`, 3,404 rows), for V0 and V1 against the
incumbent:

1. **Rows moved, mean and max |dFV|, per side and pooled**; the up/down split.
2. **The pool's grade distribution before and after**: min / median / p75 / p90 / p99 / max,
   share <= 30, count >= 35, count >= 40, count >= 45, and the count on the FV 20 floor.
3. **How many cross the FV 45 line**, in each direction, and what that line gates.
4. **The farm depth pool**: `_top_end_points` and `_depth_points` recomputed per org on the
   real graded + provisional pool, before and after, with the count of provisional rows
   entering each org's scored top 25.
5. **The client-side joint ordering**: the provisional pool's rank positions inside the
   graded + provisional board, before and after, and how far graded rows move as a result.
6. **The seven recently-routed orphans**, at the WAR values `ORPHAN_ROUTING.md` 3 replayed.
7. **The cap census**: how many rows the soft cap and the cameo cap bind on, before and after,
   under each branch. This is the direct test of 1.3.
8. **The epoch / fingerprint question, CONFIRMED not assumed** (see 1.8).

Method note, declared in advance: the counterfactual grades are computed from each served
row's stored `xfv_war_6yr` through the incumbent and the candidate maps, so both sides of
every delta use ONE WAR value and the delta is a pure map effect. Fidelity of that
reconstruction against the served `xfv_grade` is reported as a check (`xfv_war_6yr` is stored
at 2dp, so a 1dp grade can disagree by up to 0.1 FV). **No exporter, `run_monthly`,
`build_site`, scraper or matrix rebuild is run, and `data/xfv_ungraded.json` is not rewritten.**

## 1.7 WHAT WOULD MAKE THIS LANE STOP AND NOT SHIP

Written before the code change. Any one of these is a STOP-and-report, not a re-frame.

1. **The cap cannot be carried without re-tuning.** If neither branch of 1.3 leaves the cap a
   no-op on its own stated intent - V0 preserving the FV words, V1 preserving the WAR action -
   then a "re-point" is really a re-calibration of the provisional grade, and the cap
   constants are a 2026-07-25 owner call with their own recorded rationale. This gate has no
   authority to re-choose them.
2. **The module's own documented calibration is broken.** `efv_ungraded`'s docstring states
   the target this map was validated against on the real roster cohort: **"hitters median ~23
   / 77% <= 30; pitchers median ~24 / 87% <= 30"**, "MOST land 20-30 (org filler)", "a true
   45+ would have been graded". If a candidate's served distribution no longer satisfies those
   words, it has changed what a provisional grade MEANS, which is an owner decision and not a
   coherence repair.
3. **The change moves the grade in the direction this population's own outcome evidence says
   is wrong.** `data/xfv_thin_pbust_eval.json` gate G1 measured empirical-minus-served bust
   rate at provisional grade >= 35 at **+0.169 CI95 [0.128, 0.204] (hit)** and **+0.130 CI95
   [0.094, 0.150] (pit)**, positive on all eight side-by-cohort-year cells: the provisional
   grade is ALREADY too generous relative to what these players actually did. If a candidate
   raises the grade of that same cohort - so the graded-population curve reads them as safer
   still - it moves against the only outcome evidence this population has. That is a STOP,
   and it is the one measurement in this lane that is about accuracy rather than coherence.
4. **The pin does not hold.** Any served row whose `surplus_mm`, `band_p10_mm`,
   `band_p90_mm`, `p_bust` or `p_bucket` moves under a candidate. 1.4 pins them; a difference
   means the pin is not in force.
5. **The row set changes.** Any player graded before and ungraded after, on either branch.
6. **Order is not preserved within a side.** Both the incumbent map and `outcome_implied_fv`
   are strictly increasing in predicted WAR, so the provisional pool's WITHIN-SIDE ordering
   must be identical before and after. If it is not, one of the two maps is not what it is
   documented to be.

## 1.8 The epoch / fingerprint question, to be CONFIRMED

The brief says provisional grades do not enter `overall_rank` and asks for confirmation
rather than assumption, and says that if they reach any ordering a bump IS required. The
predicate to check, and the answer this lane must produce with evidence:

* `storage.BOARD_RANK_BASIS_EPOCH` gates `storage.load_rank_history`, which reads
  `metric_snapshots.overall_rank`. Provisional players carry no `metric_snapshots` row.
  **Question 1: does a provisional grade change move any GRADED player's server-side
  `overall_rank`?** `_board_grade` reads `_xfv_by_key`, i.e. `data/xfv.json` only, so the
  expected answer is NO - to be confirmed by tracing every consumer, not by assuming.
* The client-side `_EFV_RANK` IS a joint ordering (1.1) and it is described in the file as
  "the canonical board rank". **Question 2: is it covered by anything?** It is computed in
  the browser from the two artifacts, so no server epoch reaches it. What DOES reach it is
  `getEfvRankDelta`, which ranks the same joint pool a second time on ~30-day-old grades
  (`efvPrevGrade`) and publishes the difference. **Question 3: does a re-point create a
  phantom move there?** Provisional history (`xfv_history[].x`) is rebuilt by the same
  `_grade` call in the same run, so both sides of that delta should move together; that is a
  claim to verify against the artifact's shape, not to assume.
* `storage.BOARD_BASIS_FINGERPRINT` names the flagship grade scale. **Question 4: should it
  name the provisional scale too?** If the joint client ordering is a board ordering, the
  answer is yes and it is a deliverable; if not, it is a documented scope limit.

All four are answered in PART 2 with the code path that decides them.

## 1.9 Scope limits

No pytest (a concurrent lane edits the tree). No exporter, `run_monthly`, `build_site`,
scraper or matrix rebuild. Nothing under `data/` is `git add`ed that this lane did not
create. `bullpen_export.py`, `rem_plus.py`, `proj_export.py`, `efv_model.py` and
`fielding_positions.py` are not touched. A no-ship registers with verdict `deprecated`.

---

# PART 2. Results

*(Appended after the measurement. Everything above this line was on disk first.)*
