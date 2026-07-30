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

Artifact: `data/provisional_grade_map_eval.json`. Lab runtime 0.5s (the candidates are closed
forms on a 3,404-row served artifact; no fit, no bootstrap, nothing under `data/` rewritten).

## 2.0 VERDICT: NO SHIP. KEEP the bespoke map, and register the three-map split.

Three of the six pre-registered STOP conditions fire, each on its own evidence:

| # | condition | result |
|---|---|---|
| 1 | the cap cannot be carried without re-tuning | **FIRES.** Neither branch is a no-op on its own stated intent (2.2) |
| 2 | the module's documented calibration is broken | **FIRES.** V1 makes the median un-scouted org PITCHER a 40.5 FV; the spec is "median ~24, 87% at or under 30" (2.3) |
| 3 | the change moves against this population's own outcome evidence | **FIRES.** The served-versus-empirical bust gap on the cohort G1 measured goes from +0.12/+0.13 to +0.43/+0.45 (2.6) |
| 4 | the pin does not hold | not reached: no code shipped, and both candidates are `xfv_grade`-only by construction |
| 5 | the row set changes | **PASS.** 3,404 of 3,404 rows carry a grade under both candidates |
| 6 | within-side order is not preserved | **PASS, and it corrects a suspicion** (2.7) |

**The coherence complaint the owner raised is real, and this lane does not dismiss it.** It is
re-registered, sharper than before, with the client-board and farm-score numbers that make it
concrete (2.4, 2.5). What the measurement says is that `vf.outcome_implied_fv` is the wrong
instrument for closing it, because the provisional pool lives almost entirely in the region
that map's own documentation disclaims.

## 2.1 The measurement is a pure map effect, and here is the check

Both candidates are computed from each served row's stored `xfv_war_6yr`, so every delta uses
one WAR value. Re-deriving the INCUMBENT grade the same way reproduces the served
`data/xfv_ungraded.json` value **exactly on 3,174 of 3,404 rows, with a maximum disagreement
of 0.1 FV** on the remaining 230. Every one of those is the 2dp storage of `xfv_war_6yr`
crossing a 1dp grade rounding boundary. The reconstruction is faithful.

Pool as measured: 3,404 rows, 1,317 hit / 2,087 pit, 511 of them carrying the cameo sub-floor
cap.

## 2.2 STOP 1: the cap, and why "leave it alone" was the destructive option

`tools/provisional_grade_map_lab._verify_v1_algebra` checks the claim in 1.3 numerically on a
0.01-WAR grid from -2 to +12 on both sides: **max |dFV| = 0.000000**. Capping in WAR space and
reading through the incumbent affine map reproduces `efv_ungraded._grade` identically. So V1's
cap is not an approximation of the incumbent cap; it IS the incumbent cap, in the other
variable.

Where each constant binds, measured:

| constant | FV | binds at predicted WAR, INCUMBENT | binds at predicted WAR, OUTCOME map |
|---|---|---|---|
| hit KNEE | 43.0 | 4.2105 | 1.1253 |
| hit CEIL | 49.0 | 5.7895 | 4.6984 |
| hit sub-floor | 30.0 | 0.7895 | 0.0281 |
| pit KNEE | 34.0 | 2.0000 | **0.0610** |
| pit CEIL | 38.0 | 2.8889 | **0.1756** |
| pit sub-floor | 30.0 | 1.1111 | 0.0281 |

Rows sitting ABOVE the soft-cap knee, which is the direct census of what the cap does:

| branch | hit | pit | share of the pitcher pool |
|---|---|---|---|
| incumbent | 5 | 176 | 8.4% |
| **V0** (FV constants kept) | 142 | **1,416** | **67.9%** |
| V1 (WAR translation) | 5 | 176 | 8.4% |

**V0 turns a bound that touches 8% of pitchers into one that touches 68% of them**, and the
result is visible in the distribution: the V0 pitcher pool has max 38.0, p90 37.9 and p99 38.0.
Nine hundred and eighty arms pile against a four-FV wall. That is not the cap doing what it
did; it is a different instrument wearing the same constants.

V1 preserves the cap's action exactly and pays for it at the other end: its hitter maximum is
**49.5**, above the CEIL 49 the 2026-07-25 restoration used as the graded path's own asymptote,
and a cameo row capped at "org filler" would print **FV 40.9 (hit) / 42.9 (pit)** instead of 30.

So the fork in 1.3 is confirmed by measurement and neither side of it is free. **STOP 1 fires.**

## 2.3 STOP 2: what a provisional grade would come to mean

`efv_ungraded`'s docstring states the calibration this map was validated against: *"MOST land
20-30 (org filler), only genuine production breakouts reach 35-43"*, *"a true 45+ would have
been graded"*, *"hitters median ~23 / 77% <= 30; pitchers median ~24 / 87% <= 30"*.

Pooled (3,404 rows):

| | median | share <= 30 | n >= 35 | n >= 40 | n >= 45 | n at the FV20 floor |
|---|---|---|---|---|---|---|
| incumbent | 25.7 | **0.923** | 71 | 8 | 1 | 716 |
| V0 | 30.0 | 0.641 | 1,185 | 151 | 32 | 1,650 |
| V1 | 33.9 | **0.491** | 1,696 | 1,340 | 62 | 1,650 |

Per side, which is where it is worst:

| side | branch | median | share <= 30 | n >= 40 | n >= 45 | n at floor 20 |
|---|---|---|---|---|---|---|
| hit | incumbent | 20.6 | 0.918 | 8 | 1 | 618 |
| hit | V0 | 20.0 | 0.836 | 151 | 32 | 1,019 |
| hit | V1 | 20.0 | 0.779 | 226 | 23 | 1,019 |
| pit | incumbent | 27.4 | 0.926 | 0 | 0 | 98 |
| pit | V0 | 30.0 | 0.518 | 0 | 0 | 631 |
| pit | **V1** | **40.5** | **0.309** | **1,114** | **39** | 631 |

**Under V1 the median un-scouted organizational pitcher is a 40.5 FV and 1,114 of 2,087 of them
are 40 or better, up from zero.** Under V0 the pitcher pool's median is 30.0 and only 51.8%
sit at or under 30 against a documented 87%. Both branches break the module's own words.
**STOP 2 fires.**

**The mechanism, and it is the single most important sentence in this document.** The
provisional pool is **48.5% non-positive predicted WAR** (1,650 of 3,404), and
`vf.outcome_implied_fv` returns **exactly 20.0** for every one of them. The bespoke linear map
exists to spread that range - a hitter at -1.5 WAR reads 21.3, at -0.5 reads 25.1, at 0.0 reads
27.0 - which is the org-filler ladder the module was commissioned to provide. Re-pointing
deletes the ladder and replaces it with a single point, then piles everything with any positive
prediction at 37-43. The served distribution stops being a distribution and becomes two spikes.
That is not a defect in the outcome curve; it is the curve's own documented behaviour below its
data floor (`value_framework.py:2813-2820`), applied to a population that is essentially
entirely below that floor.

## 2.4 Blast radius

| branch | side | rows | moved | up / down | mean dFV | mean abs dFV | max abs dFV |
|---|---|---|---|---|---|---|---|
| V0 | hit | 1,317 | 624 (47.4%) | 218 / 406 | +0.73 | 2.71 | 12.3 |
| V0 | pit | 2,087 | 1,553 (74.4%) | 1,020 / 533 | +3.63 | 5.16 | 11.6 |
| V0 | **all** | 3,404 | **2,177 (64.0%)** | 1,238 / 939 | **+2.50** | **4.21** | 12.3 |
| V1 | hit | 1,317 | 699 (53.1%) | 293 / 406 | +1.42 | 3.39 | 12.3 |
| V1 | pit | 2,087 | 1,989 (**95.3%**) | 1,456 / 533 | **+7.98** | 9.52 | 13.7 |
| V1 | **all** | 3,404 | **2,688 (79.0%)** | 1,749 / 939 | **+5.44** | **7.15** | 13.7 |

**The FV45 line.** Crossings are **31 up / 0 down (V0)** and **61 up / 0 down (V1)**; the pool
goes from **one** row at or above 45 to 32 / 62. What that line gates, enumerated from the
consumers rather than assumed: the client FV colour band (`fv-45`), the card rarity "shine"
tier (`card-rarity-shine`), the rarity-tier bucket the starfield linkage reads, and - the one
with real weight - `storage.FV_POINTS`, where the 40-to-45 step is **1.0 to 3.5 points**, a
3.5x jump. Sixty-one un-scouted players crossing into the shine tier and the 3.5-point band is
a served consequence, not a rounding artifact.

## 2.5 The two orderings the coherence argument rests on

**The farm depth/top-end pool** (`storage._top_end_points` / `_depth_points` over
`entry["prospects"] + _prov_by_org[org]`, ranked on `_eff_grade` = `xfv_grade`):

| | incumbent | V0 | V1 |
|---|---|---|---|
| orgs whose points change | - | **30 of 30** | **30 of 30** |
| league total top-end + depth points | 3,488.49 | 3,861.07 (**+10.7%**) | 4,412.57 (**+26.5%**) |
| provisional rows inside an org scored top 25 | 82 | **281** | **434** |

**The client-side joint board** (`prospx.buildEfvRankMap`: 4,520 graded ACTIVE rows plus 3,404
provisional rows, sorted together on the single `xfv_grade` field; pool 7,924):

| | V0 | V1 |
|---|---|---|
| graded rows whose joint rank moves | 4,348 of 4,520 | 4,393 of 4,520 |
| graded median / max abs rank move | 934 / 1,131 | 934 / 1,643 |
| top 10 / 25 / 50 / 100 membership | held, 0 in 0 out at every cut | held, 0 in 0 out at every cut |
| top 300 membership | 281 held, 19 in, 19 out | 276 held, 24 in, 24 out |
| provisional rows inside the top 300 | 1 -> 20 | 1 -> 25 |
| provisional rows inside the top 1,000 | 123 -> 388 | 123 -> 614 |

Two readings, both needed. The marquee end is untouched - no provisional row reaches the top
100 under any branch, and the top 100 is identical. But **a graded prospect's board rank would
move by a median of 934 places** because of a change to players he is not being compared
against on merit. That is the cost of the coherence repair, and it is paid by the graded board.

## 2.6 STOP 3: the direction of the change, against this population's own outcomes

This is the one measurement in the lane that is about accuracy rather than coherence, and it is
the reason the verdict is not simply "coherent but ugly".

The thin-sample lane rebuilt a 19,812-row historical cohort matched to the SERVED provisional
population and measured its realized bust rate **as a function of this module's own grade**.
Its G1 gate: at provisional grade >= 35 the empirical bust rate exceeds what the
graded-population curve served by **+0.169 CI95 [0.128, 0.204] (hit)** and **+0.130 CI95
[0.094, 0.150] (pit)**, positive on all eight side-by-cohort-year cells. Observed rates:
**0.881 (hit) / 0.940 (pit)**.

What the candidates do to exactly that cohort (the 71 served rows at incumbent grade >= 35):

| side | n | mean grade | `p_bucket_given_fv` p_bust | gap vs the MEASURED rate |
|---|---|---|---|---|
| hit | 29 | 38.17 -> **46.33** (V1) | 0.760 -> **0.448** | +0.121 -> **+0.433** |
| pit | 42 | 36.24 -> **45.51** (V1) | 0.810 -> **0.488** | +0.130 -> **+0.452** |

V0 is the same story on hitters (46.24, p_bust 0.452) and milder on pitchers only because the
FV-constant cap crushes them into the 38 wall (37.98, p_bust 0.764).

And if the thin head were re-argued rather than pinned - which is what a naive re-point would do
silently - its served p_bust on that cohort would fall from **0.914 to 0.784 (hit)** and from
**0.952 to 0.836 (pit)**, in both cases away from the measured 0.881 / 0.940.

**A grade that the platform has already measured to be too generous for this population would
become about ten FV more generous.** That is the direction the evidence forbids.
**STOP 3 fires.**

## 2.7 STOP 6 passes, and it corrects something the raw count suggested

The naive census reports 70 (V0) / 68 (V1) within-side order violations against predicted WAR -
and **69 under the INCUMBENT map**. Excluding the 511 cameo-capped rows, the count is **0 under
all three arms**. Every violation is the `min(grade, 30.0)` cameo cap, which is deliberately
non-monotone in WAR and has always been so. Both maps are strictly increasing exactly as
documented, and the ordering claim is confirmed rather than merely assumed. The 69 pre-existing
violations are a property of the cameo cap worth knowing about; they are not caused by, and are
not a reason to reject, a re-point.

## 2.8 The seven orphans, and the honest split

`KEEP` / `V0` / `V1` at the predicted WAR `ORPHAN_ROUTING.md` 3 replayed:

| player | predicted WAR | KEEP | V0 | V1 | flagship grade it replaced |
|---|---|---|---|---|---|
| `easton_shelton` | 3.505 | 40.3 | 47.1 | **47.6** | 40.8 |
| `braylon_whitaker` | 2.161 | 35.2 | 45.2 | **44.8** | 35.0 |
| `jacob_friend` | 2.144 | 35.1 | 45.2 | **44.8** | **43.5** |
| `michael_martinez` | 2.099 | 35.0 | 45.1 | **44.7** | 40.6 |
| `jake_cunningham` | 1.715 | 33.5 | 44.4 | **44.0** | 41.2 |
| `mason_guerra` | -0.200 | 26.2 | **20.0** | **20.0** | 37.5 |
| `jose_meza` | -1.464 | 21.4 | **20.0** | **20.0** | 21.6 |

**The owner's case player is real and the re-point does close his gap.** `jacob_friend` reads
35.1 today against the 43.5 he carried on the flagship board; under either branch he reads 44.8,
which is what `vf.outcome_implied_fv` says about 2.144 predicted WAR. On that single row the
re-point is exactly the right answer.

**And the same change makes `mason_guerra` worse, not better.** He carried 37.5 on the flagship
board, reads 26.2 on the provisional map today, and would read **20.0** after a re-point,
because his predicted WAR is -0.200 and the outcome map has one value for the whole negative
range. Five of the seven improve; two are pushed to the floor and lose their only
differentiation. That split is the 48.5% of the pool in 2.3, in miniature.

## 2.9 The epoch / fingerprint questions, answered with the code path

**Q1. Does a provisional grade change move any GRADED player server-side `overall_rank`? NO,
and it is structural rather than incidental.** `overall_rank_by_key` is built at
`storage.py:10379-10388` by enumerating `actives`, a list of `PlayerTimeseries` objects sorted
by `_active_key`. A provisional player has no consensus point, so `build_timeseries` emits him
with `points == []` and `export_timeseries_json:10016` routes him to `inactives` before any
other gate (`ORPHAN_ROUTING.md` 1.3). He can never be in `actives`. `_board_grade`, the sort
value, reads `_xfv_by_key` - `data/xfv.json` - and never `xfv_ungraded.json`. So
`metric_snapshots.overall_rank`, the rank-movement chip and the rank-trend arrow are all
untouched, and **`BOARD_RANK_BASIS_EPOCH` would NOT need to move for a provisional-map change.**

**Q2. Is the client-side joint ordering covered by anything? NO.** `_EFV_RANK` is built in the
browser from the two artifacts (`buildEfvRankMap`), and `prospx/index.html:45705` calls it "the
canonical board rank". No server epoch reaches it. 2.5 measures what a re-point would do to it:
a median 934-place move for 4,348 of 4,520 graded rows.

**Q3. Would a re-point create a phantom MOVE there? Probably not, and here is why the answer is
"probably".** `getEfvRankDelta` ranks the same joint pool a second time on ~30-day-old grades
via `efvPrevGrade`. For a provisional row that reads `_xfv_entry.xfv_history`, which
`efv_ungraded.build` regenerates through the SAME `_grade` call in the same run
(`efv_ungraded.py:713-732`). So both the current and the previous joint ranking would be
re-spread together and a graded player DELTA should be roughly preserved even though his rank
moves ~934. The residual risk is the one-run lag: if `xfv_ungraded.json` were regenerated while
a graded player `xfv_history` was not, the two sides of the delta would move asymmetrically
for one run. That is not measured here because no code shipped, and it would be a required
measurement for any future attempt.

**Q4. Should `BOARD_BASIS_FINGERPRINT` name the provisional scale? YES, and it currently does
not.** `storage.board_basis_fingerprint()` (storage.py:4650-4685) names the board grade field,
the per-side board scale and `outcome_pooled@<curve hash>` - the FLAGSHIP grade map only. The
client joint board is an ordering that provisional grades enter, so a change to the provisional
scale is a board-ordering change that the fingerprint would not notice, which is precisely the
failure class the fingerprint exists to prevent. **This is a real gap and it exists today,
independent of this lane verdict.** It is registered here as a follow-up rather than fixed,
because adding a term to the fingerprint changes the fingerprint, which suppresses the
eFV-delta movement signal for a run (`storage.xfv_history_is_on_board_basis`) - a served
consequence that should not be taken as a side effect of a no-ship.

## 2.10 What should happen instead

1. **KEEP the bespoke map. Register the three-map split permanently**, with 1.0's correction:
   the platform has three maps of predicted WAR, not two, and the provisional one is a
   deliberately-calibrated scale rather than a leftover.
2. **The coherence defect is real and is now sized.** If it is to be closed, the instrument has
   to be one that has display granularity below FV 45, because that is where 92% of the
   provisional pool lives and where `outcome_implied_fv` has none by its own documentation. The
   shape of a fix that could work: re-anchor the bespoke map BASE and SLOPE so it agrees with
   `outcome_implied_fv` in the region where both are defined (roughly 1.5 to 5 predicted WAR)
   while keeping a monotone spread below it. That is a re-calibration with its own gate and its
   own owner call, not a re-point, and it must be scored against
   `data/xfv_thin_pbust_eval.json`'s realized outcomes rather than against coherence alone.
3. **Fix the fingerprint gap in 2.9 Q4 on its own schedule**, with the one-run movement
   suppression it implies priced in advance.
4. **Do not re-open V0.** It is dominated: it breaks the module calibration AND destroys the
   cap meaning, where V1 at least preserves the cap exactly.
