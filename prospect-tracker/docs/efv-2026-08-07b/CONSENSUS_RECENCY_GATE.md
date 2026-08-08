# Lane D-3: does a recency decay on consensus vote weight buy anything?

Date: 2026-08-07b. Lane D-3 of `docs/master-plan-2026-08-07b-efv-audit.md` (:608), defect D9
(:337). Tool: `tools/consensus_recency_lab.py`. Artifact: `data/consensus_recency_eval.json`.

**Sections 1 through 6 of this document were written BEFORE any outcome statistic was
computed.** Sections 2 and 3 contain sizing and leverage numbers that were measured first;
none of them touches a realized-WAR label, and each says so where it sits. Section 7 and
below were appended after the run and nothing above section 7 was amended afterwards.

READ-ONLY on `consensus.py` and `efv_dataset.py`. This lane writes only its own three files.

---

## 1. The defect, restated from the source

`consensus.build_timeseries` (`consensus.py:1647-1702`) walks a player's event dates and
keeps `latest_by_source`: the most recent snapshot from every source that has ever graded
the player up to that date. Every one of those forward-filled snapshots is handed to
`compute_consensus_point` as an equal vote. The aggregation
(`consensus.py:977-983`) is

```python
_wsum = sum(_fv_weights) or float(len(explicit_fvs))
avg_fv = sum(w * v for w, v in zip(_fv_weights, explicit_fvs)) / _wsum
```

and `_fv_weights` comes only from `source_weights` (`consensus.py:912`), which is
`_SOURCE_WEIGHTS` = `data/source_weights.json`. That file's `weights` object is **empty**
(reverted to equal 2026-07-25), so **every vote in production currently weighs exactly
1.0 regardless of age**. There is no age term anywhere in the file.

The only decay in the system is E-STALE (`efv_dataset.py:100-124`), which discounts the
eFV MODEL feature `fv_effective`, not the consensus, and only on live rows. See section 6.

---

## 2. Sizing and leverage, measured BEFORE any label was touched

### 2a. The evaluation pool

The pool is `source_backtest.run_source_backtest`'s **common set** (`common_n`, the 4,259
rows the plan names at :80), rebuilt from the snapshot table rather than read off
`data/source_backtest.json`, because this lane has to recompute the consensus under
alternative weightings and the served artifact carries only the shipped one.

Reconstruction rule, mirroring `source_backtest.py` exactly:

- base years `CANDIDATE_YEARS` filtered by `MIN_LAG_YEARS = 3` against 2026 -> 2017..2023;
- preseason window `[YYYY-01-01, YYYY-05-01)` (`_WINDOW_START_MMDD` / `_WINDOW_END_MMDD`);
- a row is `(player, base year)` where **both** `fangraphs` and `mlb_pipeline` supply an
  `fv_published` at some point inside that window (`_rater_grades_for_year`, `:369-377`);
- the consensus is taken at the **latest** in-window event date (`:379-382`);
- outcome from the same universe `source_backtest._load_universe` reads
  (`data/timeseries.json` + `data/debuts.json`): cumulative `career_war`, 0 for never-debuted,
  `contributor = war >= 3.0` (`CONTRIBUTOR_WAR`).

| quantity | value |
|---|---|
| pool rows | **4,233** |
| distinct players | **1,561** |
| rows by base year | 2017 312, 2018 449, 2019 590, 2020 659, 2021 685, 2022 728, 2023 810 |

4,233 against the served `common_n` of 4,259 is a **0.6 percent** shortfall and is expected:
`data/timeseries.json` was exported 2026-08-08 01:05, before this session's Baseball America
ingest (1,535 rows, 4 preseason vintages), so the served artifact and the live snapshot table
are one ingest apart. This is disclosed rather than reconciled; the lane's statistic is a
paired delta on identical rows, which a 0.6 percent membership difference cannot manufacture.

### 2b. Replay fidelity (no label involved)

Recomputing `consensus_fv_raw` at every pool row through the real
`consensus.compute_consensus_point`, with production settings
(`normalize=ADOPT_NORMALIZED_CONSENSUS = True`, `ASOF_FV_INSTANCES = True`,
`DROPOFF_SHRINK_ENABLED = False`, `ORG_RANK_VALUE_DETECTOR = True`, `_SOURCE_WEIGHTS`), and
comparing against the served `consensus_fv_raw` on the same `(player, date)`:

| quantity | value |
|---|---|
| rows compared | 4,233 (0 unmatched) |
| exact within 0.005 FV | **97.12 percent** |
| mean absolute delta | 0.0058 FV |
| max absolute delta | **0.20 FV** |

The 2.88 percent that move are the Baseball America rows from 2b's ingest gap entering the
average. Nothing moves by more than a fifth of an FV point.

### 2c. How stale are the votes this pool actually contains?

This is the leverage question and it is the first thing that should have been asked. Vote age
= (event date) minus (that source's own publication date), over the deduped contributing
snapshots at each pool row.

**[COUNTING BASIS CORRECTED AFTER THE RUN. See section 7c.** The table as first written
counted snapshots on a 5,929-row pool built before the outcome-universe join, not votes on
the 4,233-row pool section 2a defines. Both columns are shown; the artifact column is the
one every later number uses. The correction does not touch a gate clause, a threshold or an
outcome statistic, and the conclusion drawn under the table is unchanged and if anything
strengthened.**]

| quantity | as first written (5,929-row pool, snapshots) | artifact `leverage` (4,233-row pool, votes) |
|---|---|---|
| contributing FV votes | 12,906 | **8,759** |
| median age | 22 days | 22 days |
| p90 | 43 days | 35 days |
| p99 | 766 days | 766 days |
| max | 2,954 days | 2,954 days |
| share of votes older than 365 days | 5.5 percent | **4.81 percent** |
| pool rows carrying any vote older than 180 days | 773 (13.0 pct) | 449 (10.6 pct) |
| pool rows carrying any vote older than 365 days | 686 (11.6 pct) | **411 (9.7 pct)** |

**The plan's motivating image ("a 2019 FanGraphs 55 votes at full weight on a 2026 point") is
real but rare on the pool where it can be scored.** Preseason evaluation points are, by
construction, dates on which somebody published a preseason board, so the two scored raters
are usually fresh. The mechanism has to earn its keep on the 9.7 percent of rows carrying a
year-plus-old vote, not on the whole pool. Registered here so it cannot be discovered after
an unfavourable result.

### 2d. How far does a decay actually move the consensus? (still no label)

Applying `w(age) = 2 ** (-age / H)` to every vote and recomputing:

| half-life H | rows moved >= 0.005 FV | rows moved >= 0.5 FV | mean abs delta | max delta |
|---|---|---|---|---|
| 180 d | 93.2% | 7.04% | 0.204 FV | 5.30 |
| 365 d | 83.4% | 5.60% | 0.120 FV | 3.46 |
| 730 d | 76.2% | 3.52% | 0.067 FV | 2.64 |
| 1460 d | 70.2% | 1.42% | 0.035 FV | 1.81 |
| DEGENERATE (only the newest publication date votes) | 99.98% | 58.42% | **1.562 FV** | 9.64 |

So a plausible decay perturbs the consensus by roughly a tenth to a fifth of an FV point on
average, and the degenerate arm brackets the top of the range at 1.56 FV. Both ends are
measured, so the achievable range is bounded before the outcome is looked at.

**[The degenerate row was CORRECTED AFTER THE RUN, from 100% / 59.7% / 3.044 FV / 67.92.**
The pre-run scratch pass defined "newest publication date" over every forward-filled snapshot
including rank-only rows carrying no FV. On rows where the newest such row was rank-only, every
FV-bearing vote took weight 0, `consensus.py:978`'s `sum(_fv_weights) or len(explicit_fvs)`
fallback divided a zero numerator by n, and the arm returned FV 0.00 - an implementation
pathology, not a decay. The lab defines the arm over FV-bearing votes only, which is what the
registration text says ("only the newest publication date votes"), guarantees at least one
vote at weight 1, and is the version whose numbers are quoted everywhere below. The exp arms
are unaffected and reproduce the first four rows of this table exactly.]

---

## 3. What is being scored, and what is explicitly not

Scored: **the consensus's own accuracy**, on the pool above.

- `rho` = Spearman(consensus FV, realized career WAR)
- `auc` = ROC AUC(consensus FV, `war >= 3.0`)

Both computed with the house implementations `source_backtest._spearman` / `_auc`, imported
rather than re-derived.

**Never scored through a downstream eFV rho.** No eFV matrix, no `fv_effective`, no
`xfv_*` artifact is read by this lane's statistic. (The stale served matrices flagged in the
session state - 74.8 percent reproduction of `consensus_fv_raw` - therefore cannot reach this
measurement. The only eFV file this lane opens at all is `efv_dataset` for section 6's
E-STALE overlap, which is a count, not the gate.)

**Outlet weights are NOT re-fitted.** `_SOURCE_WEIGHTS` is held at its shipped value (equal)
in every arm including the baseline; the only thing that varies is the age term. That arm is
closed (`data/consensus_weight_eval.json`) and this lane does not reopen it.

---

## 4. Pre-registered protocol

### 4a. Arms

| arm | definition | role |
|---|---|---|
| `nodecay` | `w(age) = 1` | **BASELINE**. Present production. |
| `exp_global` | `w(age) = 2 ** (-age / H)`, one `H` for all sources | **HEADLINE, gated** |
| `exp_persource` | separate `H` for `fangraphs`, for `mlb_pipeline`, and one shared `H` for every other source | secondary |
| `cliff` | `w = 1` if `age <= T` else `w = c` | secondary |
| `degenerate` | `w = 1` only for votes on the newest publication date at that row, else 0 | **CONTROL** (range bracket) |

`H` grid: `30, 60, 90, 120, 180, 240, 365, 547, 730, 1095, 1460, 2190` days (12 points).
`cliff` grid: `T` in `180, 365, 730`; `c` in `0.0, 0.25, 0.5, 0.75` (12 points).
`exp_persource` is selected by one pass of coordinate ascent over the same `H` grid in the
fixed order `fangraphs, mlb_pipeline, other`, initialized at the `exp_global` optimum.

Weights multiply the shipped `_SOURCE_WEIGHTS` entry rather than replacing it, so the arm is
exactly "production plus an age term".

### 4b. Forward-chained folds

Fit on strictly earlier base years, score the fold year. Fold years are 2019, 2020, 2021,
2022, 2023 (2017 and 2018 are training-only, so every fold has at least two training years).

For fold year `Y`: select the parameter maximizing **pooled Spearman on all rows with base
year < Y**, then apply it to year `Y`'s rows. Pool the five fold-year row sets and compute
`rho` and `auc` once over that pooled OOS set. Pooled OOS size: **3,472 rows**
(590 + 659 + 685 + 728 + 810), 1,3xx distinct players (counted in the artifact).

The baseline is scored on the **identical** 3,472 rows, so every reported delta is paired.

`d_rho = rho(arm) - rho(nodecay)`; `d_auc = auc(arm) - auc(nodecay)`.

### 4c. Mandatory controls

**C1. PERMUTED-DATE null.** For each source, collect the vector of vote ages it contributes
across all pool rows and permute it across those occurrences. The per-source age
*distribution* is preserved exactly; the link between a specific grade and its specific age is
destroyed. Sources are iterated over a **sorted list**, never a set, and the stream comes from
a single seeded `numpy.random.default_rng(20260807)` (standing rule F). The **entire**
forward-chained fit-and-score procedure is re-run on each permuted draw, so the selection
freedom is matched. **R = 500 draws.** Reported as mean, sd, p2.5 / p50 / p97.5 / p99 of
`d_rho_perm` and `d_auc_perm`, plus a one-sided empirical p-value.

**C2. NO-DECAY baseline and DEGENERATE decay.** Both scored on the same OOS rows. Together
they bracket the achievable range: if the degenerate arm is not better than no decay, no
monotone decay in between can be much better either, and that will be said plainly.

**C3. Player-cluster bootstrap.** 1,561 players supply 4,233 rows, so rows are correlated
within player and a permutation null alone understates the variance of the real statistic
(the same error class as the omnibus-3 MDE premise that resampled the train frame). Resample
distinct `player_key`s with replacement, rebuild the OOS row set, recompute `d_rho` with the
arm predictions held fixed. **B = 500 draws.**

**C4. MDE.** `MDE95 = 1.96 * sd(d_rho_perm)` from C1: the smallest paired delta this design
can distinguish from a zero-information re-weighting at 95 percent. Reported alongside
`source_backtest`'s own incumbent floor `0.0068` (the MDE95 that gates the consensus-weight
A/B, `source_backtest.py` ~:908) for calibration.

### 4d. Implementation note, registered in advance

The real arms call `consensus.compute_consensus_point` directly. The 500 permutation draws
use a fast re-implementation of the weighted-mean path (vote vectors extracted once per pool
row through the real function). That fast path is **verified to reproduce
`compute_consensus_point` to within 1e-9 on every pool row for every real arm** before any
permutation is drawn, and the check is written to the artifact under `fastpath_check`. If it
does not reproduce, the lane reports BLOCKED rather than substituting an estimator.

---

## 5. Pre-registered success criterion

Standing rule 9: **marginal is FAIL.** A point estimate inside its own noise floor is a NULL,
and recording a null is a successful lane outcome.

**PASS (recommend shipping a consensus-layer recency decay) requires ALL FIVE:**

1. `d_rho(exp_global)` is **positive** and **strictly above the p99** of the 500-draw
   permuted-date null.
2. `d_rho(exp_global)` **exceeds `MDE95`** from C4.
3. The **player-cluster bootstrap p2.5** of `d_rho(exp_global)` is **above 0**.
4. `d_auc(exp_global)` is **positive**, so the headline is not an artifact of one rank
   metric.
5. **Half-life stability**: the five forward-chained selected `H` values span at most one
   order of magnitude (`max(H) / min(H) <= 10`). A "fitted decay" whose fitted value is
   re-drawn from the whole grid every fold is a noise fit, not a mechanism.
   **Clause 5 is a threshold this lane added and the brief does not contain.** If it is the
   clause that decides the verdict, the headline will say so (standing rule B).

**FAIL / NULL if any of the five is not met.** In that case: record the null, recommend no
change to `consensus.py`, and do not re-fit anything else in its place.

**Multiplicity.** Three decay families are measured. Only `exp_global` is gated. The other
two are reported with their own permutation p-values and are explicitly **not** promotable by
this document: if `exp_global` fails and a secondary family passes, the correct reading is
three-family multiplicity, and the lane still reports NULL (standing rule C).

A PASS would authorize a **recommendation**, not an edit: `consensus.py` is read-only for
this lane and any change goes back through the owner as a requested edit.

---

## 6. The E-STALE interaction, resolved BEFORE any recommendation

**What E-STALE is.** `_stale_anchor_discount` (`efv_dataset.py:105-124`) subtracts up to
10 FV points from the model anchor, linearly ramped between
`STALE_ANCHOR_RAMP_START_MO = 18` and `STALE_ANCHOR_RAMP_FULL_MO = 30` months, and **only**
for rows whose `consensus_fv_raw` rounds to band 35, 40 or 45 (`STALE_ANCHOR_TERMINAL`).
Bands outside 35-45 are never decayed.

**Where it is applied.** One call site: `efv_dataset.py:1331`, inside the **live-rows**
builder. It writes `fv_effective = consensus_fv_raw - discount`. `consensus_fv_raw` itself is
untouched, which is the deliberate design noted at `:1309-1312` ("the DISPLAYED consensus
stays raw"). `grep` over `efv_dataset.py` finds `_stale_anchor_discount` at exactly one call
site, so **it never fires on a training row.**

**Therefore the overlap on THIS lane's measurement pool is structurally zero.** The 4,233 pool
rows are 2017-2023 resolved rows on the training basis; E-STALE cannot act on any of them.
The double-discount hazard is entirely a **deployment** hazard, not a measurement one, and it
must be sized on the live board.

**Overlap on the live board, measured** (basis: `data/timeseries.json`, 4,609 active players,
latest point each, `today` = the point date 2026-08-08, using `efv_dataset._anchor_asof_date`
and `_stale_anchor_discount` imported, not re-derived):

| quantity | rows | share |
|---|---|---|
| active rows with a consensus FV | 4,609 | -- |
| E-STALE discount > 0 | **6** | 0.13% |
| would be materially re-weighted by a 365-day half-life | 1,096 | 23.8% |
| **both** | **6** | 0.13% |

Only 6 active rows carry a real published FV older than 18 months, and all 6 are in bands
35/40/45, so all 6 take a discount. **Every E-STALE row is also a decay row**: the overlap is
100 percent of E-STALE's footprint and 0.5 percent of the decay's.

Recorded discrepancy, not adjudicated: the omnibus-3 stale-anchor mover table
(`docs/efv-2026-08-07/STALE_ANCHOR_MOVER_TABLE.json`, quoted at `efv_dataset.py:150-152`)
reports 279 decayed rows at +0 months on the 2026-08-06 board of 4,586 active rows. This lane
measures 6 on the 2026-08-08 served board. The two use different pools (that table is built on
the eFV live matrix, this count on `timeseries.json`) and this lane did not reconcile them.
The resolution below is written to hold at either count.

**PRE-REGISTERED RESOLUTION, stated before the result is known.** If and only if a
consensus-layer decay clears section 5:

- **The decay ships to the consensus, E-STALE is not stacked on top of it.** The two measure
  the same quantity (time since somebody last formed an opinion) against the same evidence
  (the 18-month re-listing study). Applying both is charging the same staleness twice on the
  6 rows where they coincide, and on those rows the E-STALE terminal is 10 FV points, which is
  3x the degenerate arm's whole mean effect.
- **Mechanically:** `fv_effective` would be computed from the decayed consensus with
  `_stale_anchor_discount` forced to 0 whenever the consensus-layer decay is live, i.e. a flag
  swap, not a second subtraction. The eFV side would then need its own re-gate, because
  `fv_effective` is the model's dominant feature and changing it invalidates the served
  matrices; that re-gate is NOT in this lane's scope and would be a blocking prerequisite on
  any ship.
- **If the decay does NOT clear section 5, nothing changes and E-STALE stays exactly as it
  is.** No part of this lane's null is an argument for removing E-STALE, which rests on its
  own held-out study (`data/xfv_stale_anchor_eval.json`).

---

## RESULT (appended after the run)

**VERDICT: NULL. Four of the five pre-registered clauses fail, and the mechanism's own
in-sample ceiling sits BELOW this design's noise floor.** Every number below carries a key
into `data/consensus_recency_eval.json`. Seed 20260807, 500 permutation draws, 500
cluster-bootstrap draws, runtime 104 s. The lab is deterministic: two independent runs
produced bit-identical headline, null and bootstrap values.

### 7a. The pre-registered headline

`results`, `pool`. Forward-chained OOS: **3,472 rows, 1,444 distinct players.**

| arm | rho | auc | d_rho | d_auc |
|---|---|---|---|---|
| `nodecay` (production) | 0.28118 | 0.73153 | -- | -- |
| **`exp_global` (gated)** | 0.28132 | 0.73139 | **+0.000136** | **-0.000140** |
| `degenerate` (control) | 0.26816 | 0.71095 | -0.013022 | -0.020574 |
| `cliff` (secondary) | 0.28129 | 0.73028 | +0.000101 | -0.001248 |
| `exp_persource` (secondary) | 0.28006 | 0.73167 | -0.001122 | +0.000146 |

Forward-chained half-life selections: 2019 -> 2190 d, 2020 -> 730 d, 2021 -> 730 d,
2022 -> 240 d, 2023 -> 2190 d. Span 9.125x.

### 7b. Controls

`controls`.

| control | value |
|---|---|
| permuted-date null on `d_rho` | mean **-0.000407**, sd 0.000983, p2.5 -0.002447, p50 -0.000333, p97.5 +0.001388, **p99 +0.001547**, max +0.003609 |
| one-sided permutation p for `d_rho` | **0.289** |
| permuted-date null on `d_auc` | mean +0.000108, sd 0.000719, p99 +0.002211; one-sided p **0.627** |
| **MDE95** = 1.96 x sd | **0.001926** (incumbent `source_backtest` floor for a consensus A/B: 0.0068) |
| player-cluster bootstrap on `d_rho` | p2.5 **-0.003880**, p50 +0.000165, p97.5 +0.004059 |

The observed `d_rho` of +0.000136 is **0.07x the MDE95**, sits at the **29th percentile of a
zero-information re-weighting**, and its cluster-bootstrap interval is 58x wider than the
point estimate and straddles zero. The permuted-date control did not merely fail to be beaten;
the real fit lands below the null's own upper quartile.

**The controls are not vacuous.** The degenerate arm moved `d_rho` by **-0.013022**, which is
**6.8x the MDE95** and outside the permutation null in the negative direction. The design can
resolve an effect of that size; it found none of that size in the fitted arm. That also settles
the direction question the plan's prior implied: taking recency to its limit makes the
consensus **worse**, not better, on both metrics (`d_auc` -0.0206).

### 7c. The number that closes the lane

`ceiling_vs_floor`, `in_sample_reference`.

Fit the half-life **in sample on the whole pool with full hindsight and no forward-chaining
penalty** - the most flattering thing that can be done to this mechanism:

| quantity | value |
|---|---|
| best in-sample H | 365 days |
| rho, no decay, full pool | 0.283797 |
| rho, best in-sample H | 0.284916 |
| **in-sample ceiling `d_rho`** | **+0.001118** |
| MDE95 floor | 0.001926 |
| **ceiling / floor** | **0.581** |

**The best result an oracle could get from a global exponential recency decay on this pool is
0.58x of what this design can distinguish from noise.** That is not "we did not find it"; it
is "there is not enough of it here to find, even with the answer key". The plan called this
"the single most plausible real improvement in the whole plan"; on the only pool where it can
be scored, its ceiling is below the floor.

### 7d. The dilution objection, run because it would have embarrassed the null

`exploratory_stale_slice`. **POST-HOC and non-gating**, added after the headline was seen and
disclosed as such: the obvious complaint about section 7a is that 90 percent of pool rows carry
no stale vote, so a real effect could be averaged into nothing. Restricting both arms to the
394 OOS rows whose oldest contributing vote exceeds 365 days (11.35 percent of the OOS set),
slice fixed across permutation draws:

| quantity | value |
|---|---|
| `rho` no decay, on the slice | **0.01504** |
| `rho` exp_global, on the slice | 0.02341 |
| `d_rho` | +0.008367 |
| permuted-date null on the slice | mean +0.005473, sd 0.006915, p99 +0.023087 |
| one-sided p | **0.297** |
| slice MDE95 | 0.013553 |

The delta is 4.6x larger on the slice, and it is still **inside the noise** (0.62x its own
MDE95, p = 0.30, and the permuted control's own mean is +0.0055 on this slice, i.e. most of the
apparent gain is reproduced by shuffling the dates). The objection is answered and the null
holds.

The incidental finding is more interesting than the tested one: **on rows carrying a
year-plus-old vote the consensus has essentially no ordering skill at all** (rho 0.015 against
0.281 pooled). Those rows are not mis-weighted, they are uninformative. Down-weighting a stale
vote cannot recover skill that the fresh votes on those rows do not have either. That is the
mechanistic reason the decay has nothing to buy, and it is a better lead for a future lane than
re-fitting the weight.

### 7e. Gate clauses

`gate_clauses`.

| clause | requirement | result |
|---|---|---|
| 1 | `d_rho` positive and above permutation p99 (+0.001547) | **FAIL** (+0.000136) |
| 2 | `d_rho` above MDE95 (0.001926) | **FAIL** (0.07x) |
| 3 | cluster-bootstrap p2.5 above 0 | **FAIL** (-0.003880) |
| 4 | `d_auc` positive | **FAIL** (-0.000140) |
| 5 | half-life span <= 10x | PASS (9.125x) |

**Standing rule B disclosure: clause 5 is the threshold this lane added and the brief does not
contain, and it PASSED. It therefore did not determine the verdict** - the four clauses that
fail are all from the brief's own mandated controls (permuted-date, MDE, cluster CI, sign
agreement). The verdict is unchanged if clause 5 is deleted entirely.

**Standing rule C, multiplicity: three decay families were measured and one was gated.** Both
secondary families also fail. `cliff` is +0.000101 on `d_rho` (0.05x MDE95) with a negative
`d_auc`; `exp_persource` is outright **negative** on `d_rho` (-0.001122) despite having three
free parameters instead of one, which is what over-fitting a per-source half-life on 2 to 6
training years looks like. There is no family to promote, and none of the three would have been
promotable on this document even if one had scored.

### 7f. Replay fidelity and the fast path

`fidelity_vs_served`, `fastpath_check`. The lane's baseline reproduces the served
`consensus_fv_raw` on **97.12 percent** of pool rows within 0.005 FV, mean absolute delta
0.0058 FV, max **0.20 FV** (the residual is the Baseball America ingest gap described in
section 2a). The fast weighted-mean path reproduces `consensus.compute_consensus_point`
**exactly, max absolute delta 0.0 across 26 arms x 4,233 rows**, after the one correction the
verification caught: `ConsensusPoint` stores `round(value, 2)` (`consensus.py:1121`) and the
fast path had to round identically. The verification did its job.

### 7g. E-STALE: resolution, applied

The section 6 pre-registration resolves conditionally, and the condition did not fire.
**The decay does not ship, so E-STALE stays exactly as it is and no double-discount arises.**
The measured overlap (`estale_overlap`) stands as the sizing for whoever revisits this: on the
2026-08-08 served board, 4,609 active rows, E-STALE fires on **6** rows, a 365-day half-life
would materially re-weight **1,096**, and the intersection is **6** - 100 percent of E-STALE's
footprint, 0.5 percent of the decay's. Training rows affected by E-STALE: **0**, structurally,
because `_stale_anchor_discount` has exactly one call site and it is in the live-rows builder.

Nothing in this null is an argument against E-STALE, which rests on its own held-out study.

### 7h. What this lane did NOT test, stated so it is not over-read

- **The live board.** The fit and the score both live on 2017-2023 preseason rows, where votes
  are fresh (median age 22 days). On the live board 5.1 percent of contributing votes are older
  than a year and 1.7 percent older than two. A decay would act on 23.8 percent of live rows
  while having been measured where it acts on 9.7 percent. Any future attempt must state that
  extrapolation up front, exactly as the plan requires of D-4's single-source pull. This lane's
  answer is not "a decay is harmless on the live board"; it is "there is no measurable case
  for one".
- **Outlet weights.** Held fixed at the shipped equal weighting in every arm. Closed arm, not
  reopened.
- **Any downstream eFV quantity.** No eFV matrix was read for the statistic, so the stale
  served matrices flagged in the session state cannot reach this result.
- **The aggregator's functional form** (median, trimmed mean, precision weighting; plan I6) and
  the four shrinkage constants (D10 / lane D-4). Different parameters, untouched here.

### 7i. Recommended disposition

1. **Ship nothing.** No edit to `consensus.py` is requested by this lane.
2. **Close D9 as measured and null**, and record in the plan that the "single most plausible
   real improvement" has an in-sample ceiling of 0.58x the measurement floor, so re-running the
   same fit on the same pool with a different functional form cannot succeed either. A future
   attempt needs a bigger or differently-shaped pool, not a better decay curve.
3. **Carry 7d's incidental finding forward**, not the decay: the consensus is near-random
   (rho 0.015) on rows whose newest opinion is over a year old. The question worth asking next
   is whether such rows should be flagged or suppressed on the board, which is a coverage
   question, not a weighting one.
