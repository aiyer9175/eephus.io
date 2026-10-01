# eFV driver program, 2026-08-07: six arms, six nulls

Lane C of `docs/master-plan-2026-08-07-omnibus3.md` (owner decision 4: run all four
programs). Protocol: `docs/EFV_GATE_STANDARD.md`. Driver: `tools/efv_driver_lab.py`,
whose fold arithmetic is `tools/efv_mde_lab.py`'s numpy replica of the shipped
`efv_model._run_eval` chain. The replica's bit-parity was re-verified at the start of
this session against the committed artifacts (hit n 755 cons .3919 blend .3993; pit
n 890 cons .2495 blend .2562, matching `data/xfv_eval*.json` exactly).

**Nothing in this program ships. `_FEATURES_HIT`, `_FEATURES_PIT`,
`_BLEND_LAMBDA_RESELECT` and `POS_PREMIUM_USES_OBSERVED` are all unchanged. No served
grade, rank or dollar moves.** The deliverable is the loss ledger.

## 0. How the registrations were fixed

Each arm's candidate list, imputation posture, stop clause and instrument set were
written into `tools/efv_driver_lab.py` and committed to the working tree **before any
fit ran**: the five gated pairs are the literal `_PAIRS` table, the handedness stop
clause is the `hand_mode` docstring, the elite-band "probably unresolvable" call is the
`elite_mode` docstring, and the wRC+ one-attempt rule is in `wrc_mode`. This prose
document was assembled from that source AFTER the runs. It does not predate them and
does not claim to. What predates them is the tool.

Nothing was relaxed after a result was seen. No threshold was searched, no arm was
added, no bar was moved.

## 1. The floors, re-derived on the basis that ships

`EFV_GATE_STANDARD.md` section 1a carries the model-vs-consensus floor on the 11-fold
pair-weighted basis (0.0440 hit / 0.0436 pit pooled, 0.0325 block). **A feature add is a
different statistic class** and its registered floor (0.017 hit / 0.016 pit, and 0.0149
on block-rho) is a RETIRED-basis number. So it was re-derived first, in the same
estimator the arms are then gated with.

Method: add one pure-noise N(0,1) column to the served feature set, paired bootstrap
B=2000 resampling train AND test with a ridge and consensus-OLS refit on every draw,
and take the sd of (rho with the column) minus (rho without it). Three independent
noise seeds per side; the floor is quoted at the MAX, because a floor is a bound and
the conservative seed binds. Ledger `data/xfv_driver_floors.json`.

| statistic class, 11-fold pair-weighted | hit | pit |
|---|---|---|
| feature add, pooled rho | **0.0193** | **0.0127** |
| feature add, side block-rho | **0.0216** | **0.0182** |
| lambda shift of 0.05, pooled rho | 0.0025 | 0.0030 |
| lambda shift of 0.10, pooled rho | 0.0046 | 0.0055 |
| elite band FV>=55, model vs consensus | 0.1598 (n 76) | 0.3543 (n 26) |

Three things in that table matter beyond their use as bars.

1. **The feature-add floor did not move.** 0.0193 / 0.0127 against the retired 0.017 /
   0.016: hit is marginally wider, pit marginally tighter, and neither difference is
   itself meaningful. This is the same finding wave 1 recorded for the
   model-vs-consensus row. Doubling the pool bought no power because the paired
   bootstrap resamples the training frame and the ridge's refit variance dominates.
2. **The lambda-shift floor is far tighter than the retired 0.0076-0.011 / 0.005-0.008**,
   and it scales with the size of the shift, which the old single number hid. Lambda is
   genuinely the one gate class the promotion made more resolvable.
3. **A pure-noise column costs pooled rho -0.0016 to -0.0078.** That is the
   regularization price of one more column, and it is the honest zero point for a
   feature add: a candidate that lands at +0.000 has not tied the baseline, it has
   beaten a noise column by its own dilution cost and nothing more.

## 2. Verdict table

| arm | instrument | delta | x its floor | folds won | zero-info control | perm p | verdict |
|---|---|---|---|---|---|---|---|
| C1a `sb_rate_rel` (hit) | pooled rho | +0.00268 | 0.13x | 4/11 | +0.00006 | 0.149 | **NO-SHIP** |
| | side block-rho | +0.00108 | 0.05x | | -0.00102 | | |
| C1b `positions_played` | not run | | | | | | **STAYS GATED** |
| C2a `is_lhp` (pit) | pooled rho | **-0.01958** | 0.90x | 3/11 | -0.00159 | 1.000 | **NO-SHIP** |
| | side block-rho | -0.01366 | 0.75x | | +0.00228 | | |
| C2b `bats` side (hit) | pooled rho | -0.00068 | 0.03x | 3/11 | +0.00103 | 0.413 | **NO-SHIP** |
| | side block-rho | -0.00217 | 0.10x | | -0.00603 | | |
| C3 P1 pwr60 x contact | pooled rho | -0.00395 | 0.14x | 4/11 | -0.00098 | 0.906 | **NO-SHIP** |
| C3 P2 hit60 x obp | pooled rho | -0.00151 | 0.09x | 3/11 | +0.00008 | 0.677 | **NO-SHIP** |
| C3 P3 pwr60 x hit55 | pooled rho | +0.00291 | 0.20x | 5/11 | -0.00153 | 0.149 | **NO-SHIP** |
| C3 P4 fb60 x k (pit) | pooled rho | -0.00683 | 0.49x | 3/11 | -0.00092 | 0.906 | **NO-SHIP** |
| C3 P5 fb60 x cmd55 (pit) | pooled rho | +0.00338 | 0.25x | 5/11 | -0.00192 | 0.080 | **NO-SHIP** |
| C4a band raise hit (dip -0.2 / -0.4) | pooled rho | -0.00027 / -0.00069 | 0.10x / 0.13x | 4/11 | n/a | n/a | **NO-SHIP** |
| C4a band raise pit (dip -0.2 / -0.4) | pooled rho | +0.00092 / +0.00123 | 0.71x / 0.53x | **0/11, 1/11** | n/a | n/a | **NO-SHIP** |
| C4b elite eval hit (n 76) | model vs consensus | -0.0655 | 0.41x | | | | **UNRESOLVABLE** |
| C4b elite eval pit (n 26) | model vs consensus | +0.1577 | 0.45x | | | | **UNRESOLVABLE** |
| C5 lambda hit 0.70 -> 0.35 | pooled rho | +0.00522 | 0.27x | | | | **NO MOVE** |
| C5 lambda pit 0.57 -> 0.40 | pooled rho | +0.00286 | 0.27x | | | | **NO MOVE** |
| C6 wRC+ A2 add (hit) | pooled rho | -0.00143 | 0.09x | 1/11 | **-0.00166** | 0.707 | **FAIL** |
| | side block-rho | -0.00434 | 0.26x | | -0.00450 | | |

"x its floor" is against the arm's OWN paired-bootstrap sd, measured in the same run,
not against the table in section 1. The two agree to within a few thousandths
everywhere; the per-arm number is the stricter and is what gates.

## 3. C1a: sb_rate_rel, the pre-authorized re-test

Ledger `data/xfv_driver_sb_rate.json`.

The column re-read from the committed matrix reproduces the 2026-08-05 driver's
in-memory recompute exactly: observed n 581, mean 6.3316, sd 12.857 against that run's
recorded 6.3316 / 12.8574. So this is the same column, re-gated, and the only thing
that changed is the fold basis.

**The 11-fold re-powering did not rescue the arm. It shrank the effect.** The 4-fold
run measured +0.0076 at 0.45x its floor. On 11 folds the same column measures **+0.00268
at 0.13x**, wins a fold MINORITY (4 of 11), and moves block-rho by +0.00108, which is
0.05x that instrument's floor. The permutation null puts it at p 0.149 against the
p 0.032 bar `seasons_at_level` cleared. The zero-information control is dead (+0.00006),
so the arm is honest, it is simply not there.

Per-fold deltas show why the pooled 4-fold number was larger: the gain is concentrated
in 2023 (+0.0203) and 2024 (+0.0151), the two folds the old basis weighted most, while
2016 (-0.0156) and 2017 (-0.0077) pull the other way and 2014/2015/2020 are exactly 0.0
because coverage there is near nil.

Independent of rank, the **live blast radius disqualifies it on its own**: fitting the
production stack with the column and scoring the live hitter matrix gives
Spearman(old, new) = 0.952, a median absolute rank shift of 71 places, a p99 of 672 and
a maximum of 1,247 places out of 2,129. Reordering half the served board that far for a
0.13x-floor claim is not a trade this codebase makes.

Arm SPENT. `_FEATURES_HIT` unchanged, and `efv_dataset.py` needs nothing either way.

## 4. C1b: the positions_played census. The premise was wrong in a useful direction

Ledger `data/xfv_driver_pos_census.json`.

The plan expected this to be a gate rather than a build, on the strength of a
2026-07-30 rebuild. **The rebuild exists and the eFV model cannot see it.**

- `data/positions_played.json` (2,756 players) is still the ORIGINAL per-player,
  career-to-date, pre-debut census. Measured on today's hitter matrix its coverage is
  33.5% overall, **5.1% of debuted rows and 55.9% of bust rows**, i.e. the 2026-07-30
  figures recorded in `efv_model.py` are intact and nothing about that artifact changed.
- `data/positions_played_seasons.json` (3,827 players, generated 2026-07-30) IS the
  leak-free rebuild: league-wide, per-season, no debut filter, with the `as_of` rule in
  `fielding_positions.season_visible_through`.
- **`efv_model._observed_pos_map()` reads the first file.** The as-of census is not
  wired into the model at any point. So the blocker was never only a data job; it is
  now a consumer-repoint job as well.

Coverage of the as-of route, measured here rather than quoted, using
`fielding_positions.observed_positions_as_of` with the census-scoped bindings in
`data/fielding_census_ids.json`:

| population | old artifact | as-of census |
|---|---|---|
| hitter training matrix | 33.5% | **91.8%** |
| ... debuted rows | 5.1% | **99.3%** |
| ... bust rows | 55.9% | **85.8%** |
| live hitter scoring pool | 93.9% | (unchanged consumer) |

**Debuted-minus-bust coverage gap: -50.8pp becomes +13.5pp, and +6.5pp restricted to
id-resolved rows.** That reproduces `docs/efv-2026-07-30/POSITION_CENSUS_ASOF.md`
section 4 to within a row or two of matrix drift.

The pre-registered success criterion for unblocking `POS_PREMIUM_USES_OBSERVED` is that
coverage no longer separates debuted rows from busts. **It still separates them, by
13.5pp, in the opposite direction from before.** A feature whose DEFINITION correlates
with the label is the leak shape the flag was gated for, and 13.5pp is a smaller lever
than 50.8pp but a ridge can still learn it.

So no fit was run. Running one would have measured the residual leak and reported it as
a feature. **The flag stays False and that is the finding**, not a deferral: what the
consumers are waiting on is now precisely identified as (a) the repoint and (b) either
dropping the 87 unresolvable rows or accepting a 6.5pp residual, both of which are
modelling decisions with their own gate.

For scale if it is ever unblocked: on the as-of route 414 of 1,759 covered training rows
would change `pos_prem` (355 gain the premium, 59 lose it), against 122 of 642 on the
old artifact.

## 5. C2: handedness, the one genuinely never-tested candidate

Ledger `data/xfv_driver_handedness.json`; sidecar `.cache/xfv_handedness.json`.

The sidecar is a StatsAPI `/people?personIds=` batch over every mlbam id in all four
matrices: **6,840 ids requested, 6,840 resolved**, 2 without a bats code and 2 without a
throws code. The `sports/1/players` season-roster pattern used by `hitter_export` and
`pal_export` would have been wrong here: it is the MLB roster for one season and would
miss every prospect who never debuted.

**Both arms fail, and neither needed the stop clause to fail.**

- **(a) pitcher `is_lhp`: -0.01958 pooled, -0.01366 on block-rho, 3 of 11 folds.** The
  effect is 0.90x its own floor, so it is formally a NULL and is reported as one, but
  every sign points the same way: the zero-information control (-0.00159) SCORES BETTER
  than the candidate, and the permutation null returns p = 1.000, meaning all 200 draws
  with the row link broken matched or beat the real column. A candidate that sits at the
  very bottom of its own null distribution has no case.
- **(b) hitter bats side (L and S indicators, R as reference): -0.00068 pooled, 3 of 11
  folds**, control +0.00103, permutation p 0.413. Zero, precisely.

The stop clause is recorded as satisfied-but-unfired: the id-missingness twin (a 0/1
column firing exactly where handedness was imputed) scores -0.00518 pit / +0.00024 hit,
so it did not reproduce a candidate margin, because there was no candidate margin to
reproduce. The twin was never in the candidate set; it is scored as its own arm, and the
handedness columns carry neutral imputation with no missing indicator, as registered.

One precision note on arm (b)'s control, stated rather than glossed: the bats-side
candidate is two columns (L and S) and the zero-information twin permutes the L column
only, keeping S intact. It is therefore a partial control, not a full one. With the
candidate at -0.00068, which is 0.03x its floor, no construction of the control can
change the verdict, but the asymmetry is recorded so the number is not read as stronger
than it is.

**The coverage finding is worth more than the arms.** The `_extras` cross-check the plan
suggested was expected to be a sanity check; measured, it is a coverage question with a
sharp answer. FanGraphs per-source `_extras` carries `bats` and `throws` for 5,384
player_keys, keyed by player_key rather than by mlbam id, so it is not bound by identity
resolution. On the training pools:

| | StatsAPI | FG `_extras` | union |
|---|---|---|---|
| hit debuted (n 845) | 69.3% | 65.6% | **69.3%** |
| hit bust (n 1072) | 56.3% | 68.8% | 82.2% |
| pit debuted (n 981) | 72.8% | 68.7% | **72.8%** |
| pit bust (n 1061) | 36.5% | 67.7% | 74.3% |

**The union equals StatsAPI exactly on both debuted pools.** FanGraphs covers no debuted
row that a resolved id does not already cover; it only lifts busts. Since the eval pool
IS the debuted pool, the second source cannot raise this gate's coverage at all, and
the 69/73% ceiling is a hard property of the eval rather than a fixable ingest gap. It
would matter only for the production fit, which trains on busts too.

Cross-source agreement where both speak: **4.34% disagreement on hitter bats** (44 of
1,014) and 0.81% on pitcher throws (8 of 991). The hitter rate is high enough to matter
if handedness is ever used for display; switch-hitter designations change over a career
and the FG snapshot is dated while StatsAPI is current.

Platoon-split PRODUCTION features remain banned and were not touched. This arm tested
handedness IDENTITY only, which was the authorized question, and identity does not
predict first-6yr WAR conditional on what the model already knows.

## 6. C3: gated pairs. The col_x_k lesson reproduced on five new arms

Ledger `data/xfv_driver_gated_pairs.json`.

Five interactions, registered in `tools/efv_driver_lab._PAIRS` before any fit:

| id | side | column | fires on |
|---|---|---|---|
| P1 | hit | `thr(tool_game_pwr,60) * (-k_rel)` | 6.4% of train rows |
| P2 | hit | `thr(tool_hit,60) * obp_rel` | 7.7% |
| P3 | hit | `thr(tool_game_pwr,60) * thr(tool_hit,55)` | 4.6% |
| P4 | pit | `thr(tool_fb,60) * k_rel` | 29.6% |
| P5 | pit | `thr(tool_fb,60) * thr(tool_cmd,55)` | 5.3% |

**All five are rank nulls.** The best, P3, is +0.00291 at 0.20x its floor on a 5-of-11
fold minority. P5 is the only other point-positive arm on pooled rho (+0.00338, 0.25x)
and it is NEGATIVE on block-rho (-0.00170), so it fails the two-metric gate on sign
before magnitude is even considered. P4, the arm with by far the widest coverage, is
the most negative (-0.00683).

**The live-robustness clause is the decisive one, and it fires on every arm.** Scoring
the live matrix with each column, maximum absolute rank shift:

| arm | live rho(old,new) | median shift | p99 | max | worst mover |
|---|---|---|---|---|---|
| P1 | 0.99911 | 7 | 60 | **629** | elijah_green, FV 37.7, +0.90 WAR |
| P2 | 0.98934 | 32 | 272 | **921** | nikau_pouakagrego, FV 32.9, -0.70 WAR |
| P3 | 0.99601 | 22 | 177 | **320** | juan_corniel, FV 35.0, +0.31 WAR |
| P4 | 0.99288 | 40 | 256 | **436** | ryan_forcucci, FV 38.8, -0.19 WAR |
| P5 | 0.99669 | 21 | 147 | **1644** | jesus_tillero, FV 33.3, +0.95 WAR |

Every worst mover is a low-FV, thin-sample player. That is the exact signature recorded
at `efv_model.py:351-358` for `col_x_k` in June 2026: standardizing a sparse mostly-zero
column against its own near-degenerate sd hands a handful of thin-record players extreme
LIVE boosts that no rank metric on a debuted pool can see. The family is now closed with
its own measurement rather than by inheritance, on five arms that were chosen to be the
most theoretically defensible ones available.

## 7. C4: elite-band conviction. Both arms null, and the reason is quantitative

Ledger `data/xfv_driver_elite_band.json`. Pre-registered as probably unresolvable; that
call was correct and the numbers say how badly.

**(a) lambda band RAISE on FV>=55.** Two dips, tested on both sides.

| side | dip | lambda in band | delta pooled | folds won |
|---|---|---|---|---|
| hit | -0.20 | 0.84 | -0.00027 | 4/11 |
| hit | -0.40 | 0.98 | -0.00069 | 4/11 |
| pit | -0.20 | 0.684 | +0.00092 | **0/11** |
| pit | -0.40 | 0.798 | +0.00123 | **1/11** |

Hitters go NEGATIVE: raising model trust in the elite band makes elite hitter ordering
worse, monotonically in the size of the raise. Pitchers go point-positive at 0.71x and
0.53x their floors while winning zero and one fold out of eleven. A pooled gain with no
fold majority behind it is a pooling artifact, and block-rho agrees it is nothing
(-0.00001 and +0.00034).

**(b) elite-cohort-restricted eval.** Train on everything, score only rows with
consensus FV >= 55.

| side | scored rows | consensus rho | blend rho | delta | MDE95 | ratio |
|---|---|---|---|---|---|---|
| hit | 76 | 0.2404 | 0.1750 | -0.0655 | 0.1598 | 0.41x |
| pit | 26 | 0.0914 | 0.2491 | +0.1577 | 0.3543 | 0.45x |

**This is the honest answer to the Witt / Julio ask.** The elite band's own minimum
detectable effect is **0.16 on hitters and 0.35 on pitchers**, which is 3.6x and 8.1x
the full-pool model-vs-consensus floor and roughly 10x to 25x the size of any feature
effect this program measured. At 76 and 26 scored rows the band cannot adjudicate a
change of the magnitude eFV work produces, in either direction. It is not that the
candidates failed there; it is that no candidate could pass there.

Note the two point estimates disagree with each other in sign, which is what a
0.41x-and-0.45x pair of ratios means in practice.

No monotone tail transform was attempted. They are committed losses, and Spearman is
invariant to monotone transforms by construction, so such a fix cannot move this gate at
all. The known context stands unchallenged by anything here: the top tier is
OVER-predicted in level (FV55+ hitters predicted 10.4 vs realized 7.7 first-6yr WAR), so
the gap is within-elite DISCRIMINATION, and discrimination is exactly what 76 rows
cannot measure.

Per the plan's own fallback, the deliverable degrades to a display-side conviction
annotation, which is not this lane's to build.

## 8. C5: lambda re-sweep. No move, and the curve says something the pins do not

Ledger `data/xfv_driver_lambda_sweep.json`. Grid 0.35 to 0.90 across the clamp,
per side, 11-fold pair-weighted.

Both curves are **monotone decreasing in lambda over the entire grid**, so the argmax on
each side is the grid edge, which is also the `_BLEND_LAMBDA_CLAMP` floor of 0.35:

| side | pin | argmax | delta pooled | floor at that step | ratio | CI95 |
|---|---|---|---|---|---|---|
| hit | 0.70 | 0.35 | +0.00522 | 0.0191 | 0.27x | [-0.0033, +0.0430] |
| pit | 0.57 | 0.40 | +0.00286 | 0.0107 | 0.27x | [-0.0042, +0.0216] |

**Neither pin moves.** Both candidates are at 0.27x their floor with a CI that straddles
zero, which is precisely what the reopening rule at `efv_model.py:480-483` exists to
refuse. The whole hitter band spans 0.0079 in pooled rho and the whole pitcher band
0.0160, so on hitters the entire admissible lambda range is smaller than a single
feature-add floor.

The block-rho leg disagrees with the pooled leg on hitters and is the reason to be
careful about reading the monotone curve as a finding: block-rho over the hitter grid is
FLAT and non-monotone (0.4014 at 0.35, 0.4002 at 0.70, 0.4011 at 0.60), so the
"less model weight is better" reading is an artifact of between-fold level differences
that block-normalization removes. On pitchers the two legs do agree.

Churn cost, quoted as the reopening rule requires: moving hit 0.70 to 0.35 would
re-blend and re-print every hitter grade on the board and halve the model's weight in
the headline, for a 0.27x-floor claim that one of the two required instruments does not
support. The 0.85-to-0.70 precedent was itself taken on churn grounds and explicitly NOT
as an accuracy claim; reversing that logic to chase a smaller unresolvable delta would
be incoherent.

Worth recording beside the C4 result: **the owner's elite-conviction ask wants MORE model
trust at the top, and the sweep's own argmax wants LESS model trust everywhere.** Both
are sub-floor. The eval cannot tell these two opposite prescriptions apart, which is the
most useful single sentence in this document.

## 9. C6: wRC+ add-arm, one attempt, confirmed FAIL

Ledger `data/xfv_driver_wrc.json`. The join, the zero-imputation posture and the
a-priori null are `tools/efv_wrc_lab.py`'s frozen protocol; only the fold basis and the
uncertainty machinery changed. The park layer was NOT built (W2 M-FAIL stands). The
existing `data/xfv_wrc_eval.json` was not overwritten; this run has its own ledger.

Join: 1,096 of 1,917 matrix rows on exact (mlbam_id, milb_season, milb_level).

**Result: -0.00143 pooled, -0.00434 on block-rho, 1 of 11 folds, permutation p 0.707.**
Both instruments point-negative on an ADD arm, which is the noise-column dilution cost
and nothing else.

The control is the sharpest part. The row-permuted twin scores **-0.00166** against the
candidate's -0.00143: the zero-information column reproduces the candidate's entire
margin and slightly overshoots it. By gate standard control 2 that is the definition of
"there is no result".

The a-priori null recorded in `docs/efv-2026-07-30/WRC_PROGRAM_DECISIONS.md` before the
July run is **CONFIRMED a second time on an independent fold basis**: the decomposed
k / bb / iso / obp / ops block already carries the linear-weight information, and a
wOBA-lite composite of the same events adds nothing. One attempt, marginal is FAIL, and
this was not even marginal. **Arm closed. Do not re-open on the 11-fold basis; that was
the re-open condition and it has now been spent.**

## 10. What a reader should take from six nulls

1. **The eval's power did not improve and will not improve by adding folds.** Two
   independent statistic classes now show it: model-vs-consensus (wave 1) and feature
   add (section 1). The binding term is ridge refit variance on a resampled training
   frame, not test n.
2. **Every arm here was chosen because its prior pointed positive.** SB volume for
   athleticism, handedness identity as a never-tested primitive, tool-threshold
   interactions as the classic scouting non-linearity, wRC+ as the canonical offensive
   summary. All six land inside the floor, four of them point-negative. That is what a
   feature set at the right complexity looks like from the outside, which is the same
   conclusion `EFV_GATE_STANDARD.md` section 6 reached from backward elimination.
3. **The live-robustness clause earned its place.** Two arms that were unremarkable on
   rank (C1a and C3 P5) move a served player 1,247 and 1,644 rank places. Rank metrics
   on a debuted pool are structurally blind to that, and it is the failure mode that
   reverted `col_x_k`.
4. **The elite band is not a modelling problem, it is a sample-size problem.** 76 hitter
   rows and 26 pitcher rows carry a floor of 0.16 and 0.35. Anything the site wants to
   say about elite conviction has to be said in display, with a disclosure, or not at
   all.

## 11. Artifacts

| path | what |
|---|---|
| `tools/efv_driver_lab.py` | the lab; every registration is in its source |
| `data/xfv_driver_floors.json` | re-derived feature-add and lambda-shift floors |
| `data/xfv_driver_sb_rate.json` | C1a |
| `data/xfv_driver_pos_census.json` | C1b coverage measurement |
| `.cache/xfv_handedness.json` | C2 sidecar, 6,840 ids, StatsAPI, rebuildable |
| `data/xfv_driver_handedness.json` | C2 both arms |
| `data/xfv_driver_gated_pairs.json` | C3 five arms with live movement |
| `data/xfv_driver_elite_band.json` | C4 both arms |
| `data/xfv_driver_lambda_sweep.json` | C5 |
| `data/xfv_driver_wrc.json` | C6 |

These are deliberately named outside the `data/*_eval*.json` glob. An eval artifact owes
a `data/model_registry.json` row and this lane does not own that file; see the follow-up
below.

## 12. Follow-ups this lane could not take

1. **Registry rows.** Every arm above deserves a `deprecated`-verdict registry row
   (`data/model_registry.json`) pointing at its ledger. That file belongs to another
   lane this wave.
2. **The positions_played consumer repoint.** `efv_model._observed_pos_map` should read
   the as-of census through `fielding_positions.observed_positions_as_of`, not
   `positions_played.json`. It is a real defect that the model is gated against the
   worse of two artifacts it already has on disk. It is NOT a free fix: the repoint
   changes what the flag would mean if it were ever flipped, and it needs the 87
   unresolvable-row decision taken first.
3. **Handedness for display.** The sidecar resolves 6,840 of 6,840 ids and nothing on
   the site currently shows a prospect's bats/throws. That is a display question with no
   model risk, and the 4.34% StatsAPI-vs-FanGraphs disagreement on hitter bats is the
   thing to resolve first.
4. **The handedness sidecar deliberately lives in `.cache/`, not `data/`.** Top-level
   `data/*.json` is published (`deploy/publish_paths.txt`), and 6,840 rows nothing serves
   should not ship to the web. `python tools/efv_driver_lab.py handbuild` rebuilds it in
   about ten seconds, and the committed ledger carries the join's provenance and code
   counts, so the gate stays auditable without the raw file. If the display follow-up is
   ever taken, that is the point at which it earns a served home.

## 13. C7: arms recorded closed WITHOUT building, per the plan

The plan's C7 lists candidates to ledger rather than gate. Recorded here so the ledger
lives beside the six that were run, and verified against the code before writing:

- **POW+ / HIT+ / PD+ / ISO+ as training drivers.** Frontend-only composites. Their
  trainable parts are already adjudicated in `_FEATURES_HIT`'s own comments (game power
  excluded on three independent refutations; `iso_rel` / `peak_iso_rel` rejected; the
  2026-06-22 conditional-power family all failed), and their Statcast parts have no
  pre-2023 history, so there is nothing to forward-chain them on. Not built.
- **SC+ components as training features.** No pre-2023 history, so a forward chain over
  2014-2024 folds would train nine of eleven folds on an absent column. The live overlay
  already carries whiff and velocity at component level, and the component reweight is
  queued to season close per `docs/archive/REVIEW_QUEUE.md` item 12 with its own pre-set
  trigger. Not built.

Neither is a null measured today. They are arms with no admissible measurement
available, which is a different status and is recorded as such.
