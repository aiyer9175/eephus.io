# Franklin Arias: why the model leg lost 0.13 WAR on 2026-08-04

Lane N7 of the omnibus-3 program, owner-commissioned. Measurement only. Nothing here
changed a served grade, rank or dollar, and no artifact under `data/` was written.

Lab: `tools/efv_arias_replay_lab.py` (read-only, single process).
Reproduce with `python tools/efv_arias_replay_lab.py` from `prospect-tracker/`.

---

## 0. The short version

The owner asked why Arias sits at #3 when he is (he believed) a level above Made and
de Vries and hitting better than both.

1. **The level premise is false.** All three are at Double-A. Arias is the OLDEST of
   the three, not the most advanced.
2. **The hitting premise is true**, and it is priced: his OPS-vs-level is 0.251
   against 0.118 for Made and 0.123 for de Vries, and the model pays him +2.0 FV over
   consensus while paying Made +1.0 and de Vries +1.1.
3. The 08-04 drop is **100 percent a refit**. Not one of his own numbers changed.
   The regen re-priced the MiLB production block for everybody, and the single largest
   term in his ledger is the level premium, which he shares identically with the other
   two.
4. The reason he lost *relative* to them is the irony in the question. The refit moved
   weight OFF production-vs-level (the thing the owner is pointing at, where Arias is
   far ahead) and ONTO age-for-level (the thing he thinks is not in play, where Arias
   is behind, because he is the oldest of the three).
5. Nothing in the model will move him. His deficit is a 2.0 FV consensus anchor gap,
   and the reason for that gap is now visible in one line: **all five sources have
   Arias at 60, while Made has two 65s and de Vries has one.** One source going to 65
   is worth about +0.43 WAR of model leg, which is four times what he needs to pass
   de Vries.

---

## 1. What actually moved, from the committed artifacts

Read out of `data/xfv.json` at each SHA with `git show`, all five vintages held in one
process. `war` is `xfv_war_6yr`, the model leg, which is what the board grade
(`xfv_grade`) is a monotone map of.

| SHA | vintage | Arias grade / war | de Vries | Made | Arias's rank of the three |
|---|---|---|---|---|---|
| 297d7eb | 07-30 | 60.4 / 11.21 | 60.1 / 10.99 | 60.8 / 11.44 | 2nd |
| fe670dd | 08-01 | 60.3 / 11.14 | 60.2 / 11.08 | 60.8 / 11.49 | 2nd |
| 7626fd0 | 08-03 | 60.3 / 11.14 | 60.3 / 11.11 | 61.0 / 11.63 | tied |
| d50c1af | 08-04 | 60.1 / **11.01** | 60.2 / 11.05 | 61.0 / 11.60 | **3rd** |
| HEAD | 08-06 | 60.1 / 10.98 | 60.2 / 11.09 | 61.1 / 11.66 | 3rd |

Consensus FV is 58.1 / 59.1 / 60.1 at every one of the five vintages, byte-identical.
The 08-03 FanGraphs re-grade of 1,384 prospects did not move any of the three anchors.
So the flip is entirely on the model leg, and the decisive step is 08-04 taking 0.13
WAR off Arias while taking 0.06 off de Vries and 0.03 off Made.

### It is not a code change

Every module that reads or transforms a MiLB feature is byte-identical between the two
SHAs: `efv_dataset.py`, `level_norms.py`, `age_level.py`, `value_framework.py`,
`milb_history.py`, `wrc_rates.py`, `grade_normalization.py`, `consensus.py`.

`efv_model.py` changed in three ways, none of which can touch a hitter's model leg:
`("age", -1)` became `("age", 0)`, which binds only `_fit_lgbm_mono`'s monotone
constraints on the eval-only LightGBM challenger and never the served ridge; the
PITCHER lambda pin moved to 0.57, and lambda enters `rank_war`, not `xfv_war`; and
`rank_calibration` gained a reporting argument. `efv_score.py` changed only the hitter
`age` explainer skip and a display-side disagreement instrument.

So the -0.13 is a data change and the refit it caused.

---

## 2. Method, and what could NOT be replayed

`data/xfv_hitter_matrix.json` and `data/xfv_live_hitter_matrix.json` are gitignored and
the nightly box overwrites them, so the 08-03 and 08-04 feature matrices do not exist
anywhere any more. **Rebuilding them from the current database would not reproduce
those vintages** (the identity repair, the negative-cache fix and a further two days of
MiLB games all landed inside and after the window), so that route was refused rather
than presented as a faithful replay.

What IS committed at every SHA is each player's explainer array, and that array is not
a summary. It is literally the model's own per-feature terms:

```
_predict(ridge, feats) = ridge.b + SUM_k  w_k * (x_k - mu_k) / sd_k
efv_score._factors     = those same w_k * (x_k - mu_k)/sd_k, collinear-grouped,
                         with fv / milb_missing / is_ifa / is_college / age dropped,
                         top 4 by magnitude, rounded to 2dp
xfv_war                = max(-2.0, a + b * _predict(...)) then the multiplicative tilts
```

So a committed factor array is an exact (truncated) slice of the served prediction at
that vintage, in ridge units, and one multiplication by the calibration slope `b` puts
it in WAR. Both vintages are loaded and scored in ONE process, per the standing rule:
measuring before and after as two processes is unsound here because the box regenerates
inputs mid-measurement and the two runs then do not share a corpus.

### Machinery validation, before any of it is trusted

Fitting the production stack on the matrices that are on disk and re-deriving the HEAD
row from scratch:

```
production stack: n_train=1883  alpha=100.0  a=0.0319  b=1.0448  ridge intercept=1.6976
pred 10.3690  ->  untilted 10.8655  ->  x statcast 1.011  =  10.98
served at HEAD                                            =  10.98      MATCH
factors replayed = factors served, byte for byte                         MATCH
```

That fixes the ledger's denominator: **1 ridge unit = b * statcast = 1.0448 * 1.014 =
1.0594 WAR** at Arias's 08-04 tilt.

### The refit map, fitted affinely

For a refit with the feature VALUE held, `c = (w/sd)(x - mu)` gives
`c_new = p*c_old + q` exactly, with `p = (w_new*sd_old)/(w_old*sd_new)` and
`q = (w_new/sd_new)(mu_old - mu_new)`. So an affine fit of new contribution on old
contribution across the whole board is not a smoothing convenience, it is the exact
form of the thing being measured, and its residual is a direct measurement of how much
feature movement there was.

| feature | p | q | n | r2 | median abs err | rows over 0.03 |
|---|---|---|---|---|---|---|
| level_rank | 0.6772 | -0.0356 | 1387 | 0.99989 | 0.0003 | 0 |
| age_rel_level | 1.4639 | +0.0131 | 990 | 0.99974 | 0.0043 | 0 |
| ops_rel | 0.8794 | -0.0045 | 1357 | 0.99925 | 0.0029 | 28 |
| tool_hit | 1.0458 | -0.0046 | 817 | 0.99996 | 0.0010 | 0 |
| obp_rel | 0.6433 | +0.0005 | 128 | 0.99857 | 0.0024 | 0 |
| tool_speed | 1.0434 | +0.0005 | 297 | 0.99979 | 0.0038 | 0 |
| n_milb_seasons | 0.8288 | +0.0284 | 946 | 0.99987 | 0.0003 | 0 |
| k_rel + peak_k_rel | 0.8773 | -0.0172 | 652 | 0.99418 | 0.0081 | 41 |

Eight two-parameter maps reproduce 6,574 committed contributions over the 1,981 hitters
scored at both vintages, at r2 0.994 to 0.99996 and a median absolute error of 0.0003 to
0.0081 ridge units, which is the scale of the 2dp rounding in the committed arrays
themselves. **That is what "the 08-04 regen was a refit" means quantitatively.** The 28
ops_rel and 41 k_rate rows that miss by more than 0.03 are the players whose actual
production line moved between the two dates.

---

## 3. (a) The attribution table

`c` columns are ridge units. `d WAR` is `b * statcast * (c_0804 - c_0803)`. A value is
taken from the COMMITTED explainer array wherever the top-4 cut showed it; underneath
that cut it comes from the current full contribution vector, which is licensed for this
player because his 08-04 explainer array and his HEAD explainer array are identical and
his untilted model leg agrees to 0.008 WAR. The 08-03 side of a feature the cut hid is
the affine map inverted onto the 08-04 value.

| feature | c(08-03) | c(08-04) | d ridge | **d WAR** | refit slope, and what it means |
|---|---|---|---|---|---|
| level_rank | +0.5400 | +0.3300 | -0.2100 | **-0.2225** | 0.677: level premium cut 32 percent |
| ops_rel | +0.8500 | +0.7400 | -0.1100 | **-0.1165** | 0.879: production-vs-level cut 12 percent |
| obp_rel | +0.1738 | +0.1123 | -0.0614 | **-0.0651** | 0.643: on-base-vs-level cut 36 percent |
| k_rel + peak_k_rel | -0.0773 | -0.0850 | -0.0078 | **-0.0082** | 0.877: contact net cut 12 percent |
| tool_speed | -0.0360 | -0.0370 | -0.0011 | **-0.0011** | 1.043: speed tool up 4 percent |
| tool_hit | +0.6400 | +0.6700 | +0.0300 | **+0.0318** | 1.046: hit tool up 5 percent |
| n_milb_seasons | -0.3000 | -0.2256 | +0.0744 | **+0.0788** | 0.829: seasons-used penalty cut 17 percent |
| age_rel_level | +0.2711 | +0.4100 | +0.1389 | **+0.1472** | 1.464: age-for-level up 46 percent |
| | | | **explainer subtotal** | **-0.1557** | |
| | | | **anchor block** | **+0.0257** | see below |
| | | | **OBSERVED** | **-0.1300** | 11.14 to 11.01 |

**The table sums to the observed -0.13 exactly.** The Statcast tilt is 1.014 at both
vintages and contributes nothing.

Two of the twelve numbers in the `c` columns are not committed values. `n_milb_seasons`
at 08-04 is the current full vector (the top-4 cut hid it that day) and `obp_rel` is the
current full vector at 08-04 with the affine inverse at 08-03 (the cut hid it on both
days). Their combined sensitivity is small and lands in the anchor row, not in a feature
row: running `n_milb_seasons` at the map's own forward prediction of -0.2202 instead
moves that row to +0.0845 and the anchor row to +0.0200. The conclusion below does not
turn on either.

### The anchor block, and why it is one row

The ledger cannot split the last +0.026. It is the sum of the ridge intercept move, the
consensus-FV term's own re-standardization, the two cohort dummies, the skipped `age`
term, and the `(a, b)` output recalibration. Those are all functions of the consensus
anchor and the cohort flags. Not one of them knows anything about his Double-A line,
his tools or his level, so splitting them further would add precision without adding
meaning.

It is small and it points the OTHER way: the global part of the regen gave Arias +0.026
WAR. Computed identically for all 72 anchor-stable, tilt-stable hitters at consensus FV
48 or above, the block runs median -0.071 with an interquartile range of -0.173 to
+0.041. Arias at +0.026 is an ordinary draw from that, not an outlier.

---

## 4. (b) Refit that touched everyone, versus signal specific to him

**None of the -0.13 is a change in Franklin Arias's data. All of it is the refit.**

The direct test is his residual against the population maps, which is the only place a
feature-value change can show up:

| feature | population map predicts | actual 08-04 | error | population p90 error |
|---|---|---|---|---|
| level_rank | +0.3301 | +0.3300 | -0.0001 | 0.0044 |
| ops_rel | +0.7430 | +0.7400 | -0.0030 | 0.0072 |
| tool_hit | +0.6648 | +0.6700 | +0.0052 | 0.0040 |

Every residual is inside or at the population's own error band, which is set by 2dp
rounding of the committed arrays. Two consistency checks on the features the top-4 cut
hid, neither of which the maps were fitted on:

* His `age_rel_level` contribution was below the cut at 08-03 and reads +0.41 at 08-04.
  Inverted, the map puts his 08-03 value at +0.2711, which has to be under the +0.30
  that occupied the fourth slot that day. It is.
* His `n_milb_seasons` contribution was -0.30 at 08-03 and dropped below the cut at
  08-04. The map's forward prediction is -0.2202, which has to be under the 0.33 that
  occupied the fourth slot. It is. The current full vector reads -0.2256, which is 0.005
  away; that gap sits inside the 08-04-to-HEAD slack rather than being a clean test, so
  it is reported as agreement in sign and size, not as a fourth-decimal match.

**But a common refit does not move everyone equally.** It rescales each player's own
exposure, so the same weight change costs the player who leans hardest on that feature
the most. That is the whole story of Arias versus the two ahead of him, and it is worth
stating separately because it is where the owner's intuition and the model collide.

Context first: over the same tier (consensus FV 48 or above, anchor-stable and
tilt-stable, n=72) the 08-04 regen moved the model leg by a **median of -0.140**, p10
-0.320, p90 -0.030. **Arias's -0.130 is better than the tier median.** He did not get
singled out. He got beaten by two specific players.

### The relative move, which is what actually reordered the board

| versus | observed | explainer | anchor |
|---|---|---|---|
| Made | -0.100 | -0.194 | +0.094 |
| de Vries | -0.070 | -0.108 | +0.038 |

The anchor column is the consensus-keyed part, and it moved in Arias's favor: the
re-standardized fv term treats a 58.1 anchor slightly better than a 60.1 one after the
refit, which cancelled roughly half his explainer loss to Made. The feature side is
therefore doing MORE than the -0.100 he actually gave up. Note also that the peer
ledgers use the current-vector stand-in for the features under their top-4 cut and their
08-04 explainer arrays are not identical to HEAD, so their anchor rows carry more error
than Arias's; the feature rows below are committed values on both sides for the two that
matter.

Per feature, Arias minus the peer, in WAR:

| feature | vs Made | vs de Vries |
|---|---|---|
| **age_rel_level** | **-0.0953** | **-0.0529** |
| **ops_rel** | **-0.0638** | **-0.0638** |
| obp_rel | -0.0361 | -0.0193 |
| k_rel + peak_k_rel | -0.0165 | (below 0.005) |
| tool_speed | -0.0069 | -0.0077 |
| tool_hit | +0.0107 | +0.0213 |
| n_milb_seasons | +0.0154 | +0.0155 |

Two features carry it, and they carry it in opposite directions from what the question
assumes. The inputs, off the current live matrix, with all three at `level_rank` 4.0:

| | Arias | Made | de Vries |
|---|---|---|---|
| level | AA | AA | AA |
| age at the production read | **20.6** | 19.1 | 19.7 |
| age_rel_level | **-1.90** | -3.40 | -2.80 |
| ops_rel | **+0.251** | +0.118 | +0.123 |
| obp_rel | +0.069 | +0.033 | +0.050 |
| tool_hit | 62 | 60 | 56 |

* **age_rel_level was amplified 46 percent.** It pays out in proportion to how young
  for the level you are. Made is 3.4 years young for Double-A, de Vries 2.8, Arias 1.9.
  So the same amplification handed Made +0.243 WAR, de Vries +0.200, and Arias only
  +0.147. Arias lost 0.095 to Made on a term where his own number went UP.
* **ops_rel was cut 12 percent, and obp_rel 36 percent.** These pay out in proportion
  to how far above level you are hitting, which is exactly where Arias is ahead. The cut
  cost him 0.117 + 0.065 = 0.182 WAR against 0.082 for Made and 0.098 for de Vries.

So the regen took value away from Arias's strongest edge and added value to his weakest
relative attribute. Everything else in the table is a rounding-scale wash.

---

## 5. Why the fit moved at all

The hitter TRAINING matrix's own report, per vintage:

| SHA | vintage | rows | rows with a real MiLB production block | consensus baseline rho |
|---|---|---|---|---|
| 297d7eb | 07-30 | 1927 | 925 / 1927 (48.0%) | 0.2777 |
| fe670dd | 08-01 | 1927 | 925 / 1927 | 0.2777 |
| 7626fd0 | 08-03 | 1927 | 925 / 1927 | 0.2777 |
| **d50c1af** | **08-04** | 1917 | **1135 / 1917 (59.2%)** | 0.2776 |
| HEAD | 08-06 | 1917 | 1134 / 1917 | 0.2776 |

**210 labeled hitters gained a MiLB production block in one regen**, a 22.7 percent
expansion of the pool that carries any MiLB-derived feature at all, after being
byte-stable across three prior vintages. Every mean, standard deviation and fitted
weight on `level_rank`, `age_rel_level`, `ops_rel`, `obp_rel`, `k_rel` and
`n_milb_seasons` is a function of that pool. That is the refit.

The mechanism is in the window and is documented in its own commits: 367eb3a
(2026-08-03 19:45) fixed `resolve_mlbam_id` caching a miss forever, and its dry-run
healed 227 of 254 statless players; 608bdd2 (2026-08-03 22:01) persisted those
resolutions into `player_photos` so they survive to the export, taking production id
resolution from 4,296 to 4,521 and career-stats coverage from 4,296 to 4,343. Nothing
else in the window adds MiLB blocks at scale.

Note the consensus baseline barely moved (0.2777 to 0.2776). The board did not get a
new opinion. The model got a better look at the pool it learns from, and re-weighted
accordingly.

---

## 6. (c) The answer, in plain language

You have Arias behind Made and de Vries and you think the model is missing something.
Two corrections and then the actual mechanism.

**All three are at Double-A.** Arias is not a level ahead. He is the OLDEST of the
three at that level: 20.6 against de Vries 19.7 and Made 19.1. When the model says
"age for level", that is what it is reading, and Arias is 1.9 years young for Double-A
where Made is 3.4.

**Your read on the bat is right, and it is already in the number.** Arias is hitting
0.251 of OPS above his level; Made and de Vries are at 0.118 and 0.123, less than half.
That is why the model carries Arias 2.0 FV above his consensus grade while carrying
Made 1.0 and de Vries 1.1. The model likes him more than the industry does by twice as
much as it likes either of them.

**What happened on 08-04 is not about him.** A pipeline fix that landed the night before
gave 210 previously blind training rows their minor-league statlines, and the next
morning's regen re-fit the model on that better look. It came out believing less in
"how far above your level you hit" (down 12 percent
on OPS, 36 percent on on-base) and more in "how young you are for your level" (up 46
percent). It also cut the flat premium for reaching Double-A by a third, which every
Double-A hitter on the board got equally.

That re-weighting is exactly wrong for Arias relative to those two. It shrank the thing
he is best at and grew the thing he is worst at, so even though the day cost the whole
FV-48-and-up tier a median 0.14 WAR and cost Arias only 0.13, it cost Made 0.03 and
de Vries 0.06. Arias fell from tied to third on 0.04 WAR, which is one tenth of one FV
point.

None of his own numbers changed. Not the level, not the line, not the tools, not the
grade any source has him at. Only the model's weights.

---

## 7. (d) What would actually change his rank

He is 0.11 WAR of model leg from passing de Vries and 0.68 from passing Made:

| | consensus | model leg | board grade | premium over consensus |
|---|---|---|---|---|
| Arias | 58.1 | 10.98 | 60.1 | +2.0 |
| de Vries | 59.1 | 11.09 | 60.2 | +1.1 |
| Made | 60.1 | 11.66 | 61.1 | +1.0 |

### The model side is spent

The board grade is a monotone map of the model leg alone, and the model leg's dominant
term is the consensus anchor: the `fv` ridge term is worth **0.4110 ridge units per
consensus FV point, which is 0.4341 WAR of model leg per FV point**. Arias's fv term is
6.803 against Made's 7.625, so the 2.0 FV anchor gap alone accounts for 0.868 WAR while
he trails by only 0.68. Everything else in his vector is already clawing back 0.19 of
that deficit, which is the same thing the +2.0 premium over consensus is saying in FV
units. Asking the model for more means either his production changes, which is baseball,
or a weight changes, which is a gated model change that would have to clear MDE95 and
would re-rank the entire board. Neither is an Arias lever.

### Both consensus-side levers were already refuted

The stale-anchor lever is empty: his anchor is byte-stable at 58.1 across the whole
window, so there is nothing stale to refresh. The source re-basing lever measured
exactly 0.000, and the source table shows why it had to:

Latest published FV per source, out of `prospects.db`:

| source | Arias | Made | de Vries |
|---|---|---|---|
| ESPN (2026-05-22) | 60 | 60 | 60 |
| FanGraphs (2026-08-02) | 60 | **65** | 60 |
| Just Baseball (2026-06-04) | 60 | 60 | 60 |
| MLB Pipeline (2026-08-06) | 60 | **65** | **65** |
| TJStats (2026-08-07) | 60 | 60 | 60 |
| MLB Pipeline International (2024-01-15) | none | 55 | 55 |
| consensus anchor | **58.1** | **60.1** | **59.1** |

All three are carried by the same five current sources, so any per-source recalibration
moves all three by the same amount and the gaps survive it. The gap is not in how the
sources are weighted. It is in what they published.

### What is left is a published re-grade, and it is a small one

Count the 65s: Arias has zero, de Vries one, Made two, and their anchors come out exactly
1.0 FV apart in that order. So in this machinery **one source moving Arias from 60 to
65 is worth about +1.0 consensus FV, which is +0.43 WAR of model leg**. The stale 2024
International row sits on the two players WITH 65s and not on Arias, and it is a 55, so
if it is being counted at all it is dragging them down and the +1.0 per upgrade is a
lower bound. That is:

* **four times** what he needs to pass de Vries (+0.11), and
* **64 percent** of what he needs to pass Made (+0.68).

Two sources going to 65 puts him first of the three (10.98 + 0.87 = 11.85 against
Made's 11.66).

For scale, the entire 08-04 regen that started this question moved his model leg by
-0.13, and its largest single feature term was -0.22. **One published upgrade is worth
more than three of those regens.** The model has already said its piece about Franklin
Arias, twice as loudly as it has about either player ahead of him. What it is waiting
for is a board.

---

## 8. Limits of this document

* The 08-03 and 08-04 feature matrices are gone and were NOT rebuilt. The decomposition
  is anchored on committed per-player contributions plus a fit on the current matrix,
  and every place that substitution is used is labelled in the lab output's `source`
  column.
* The 08-04 to HEAD stand-in is licensed for Arias (identical explainer array, model leg
  agreeing to 0.008 WAR) and is NOT licensed board-wide: only 337 of 2,127 live hitters
  have an identical explainer array at those two dates. Peer ledgers built with it carry
  more error than his, and their anchor rows should be read as approximate.
* The anchor block is obtained by difference. It is characterized against 72 tier peers
  and bounded, not decomposed. Splitting it would require the 08-03 calibration
  constants, which are not recoverable.
* The 210-row training-pool expansion is measured; its attribution to commits 367eb3a
  and 608bdd2 is inference from the commit record and from the absence of any other
  mechanism in the window that adds MiLB blocks at scale.
* Nothing here was gated as a change, because nothing here proposes one. The lane's
  deliverable is this document.
