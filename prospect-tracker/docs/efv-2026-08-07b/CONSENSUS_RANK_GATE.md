# Lane J1: the consensusRank gate-opening measurement

Date: 2026-08-07b. Lane J1 of `docs/master-plan-2026-08-07b-efv-audit.md` (:882).
Tool: `tools/consensus_rank_lab.py`. Artifact: `data/consensus_rank_eval.json`.

**Sections 1 through 4 of this document were written BEFORE the outcome statistic was
computed.** Only the reproduction table (section 2) and the sizing counts in section 4
existed at registration time; neither of those is the measured quantity. Section 5 and
below were appended after the run. The repo driver ledger says a registration that
postdates its result is worthless, so the ordering is recorded here explicitly.

---

## 1. The question

Within a single `(source, snapshot_date, interval_label, fv)` cell, does that source's own
published `rank` predict realized WAR?

This is a gate, not a build. Lane J2 (build consensusRank) does not run in this wave under
any circumstance, glowing result or not.

---

## 2. J0 reproduction: does the motivating table hold? (run before registration)

Query is against `snapshots` in `prospect-tracker/prospects.db` (NOT `data/prospects.db`,
which is a zero-table stub). 54,061 rows total.

The plan's "ranked rows" column means rows carrying **both** a `rank` and an `fv`; its
grouping for the median columns is `(source, snapshot_date)`. Under that exact reading:

| source | ranked rows | in an FV tie | tie w/ distinct ranks | med distinct FV | med distinct rank | med n | rank-only |
|---|---|---|---|---|---|---|---|
| fangraphs | 24,300 | 24,274 (99.9%) | 24,274 | 7 | 100 | 1,005 | 0 |
| mlb_pipeline | 18,240 | 18,232 (100.0%) | 18,226 | 3 | 100 | 100 | 538 |
| tjstats | 4,498 | 4,498 (100.0%) | 4,498 | 3 | 100 | 100 | 4 |
| espn | 252 | 251 (99.6%) | 251 | 3 | 100 | 101 | 0 |
| just_baseball | 126 | 125 (99.2%) | 125 | 4 | 63 | 63 | 0 |
| baseballamerica | 0 | -- | -- | -- | 100 | 100 | 100 |

**VERDICT: J0 REPRODUCES EXACTLY, every cell.** Largest single tie cell also reproduces:
**626 FanGraphs players at FV 40 on 2026-08-02, spread across 42 distinct ranks.**

The premise is therefore live: consensus FV, which is `_FEATURES_HIT[0]`, `_FEATURES_PIT[0]`,
the consensus OLS leg of the blend and the baseline eFV is scored against, is built from
inputs whose own published ordering is discarded on 99.9 percent of rows.

### 2b. The two owner premises the data corrects

1. **JustBaseball DOES publish FV grades. CONFIRMED.** 126 rows, all 126 carry an `fv`,
   `rank-but-no-fv` = 0. Two dates: 2026-06-04 (100 rows) and 2026-03-04 (26 rows). Both
   rank-1 rows carry real and differing grades: `konnor_griffin` 2026-03-04 rank 1 FV 70;
   `jesus_made` 2026-06-04 rank 1 FV 60.
2. **The genuinely rank-only population is small. CONFIRMED, 642 rows exactly.**
   Baseball America 100 (all on the single date 2026-06-03, zero FVs), MLB Pipeline 538,
   tjstats 4. No other source contributes a rank-only row.

So the payoff of this lane is NOT "admit rank-only outlets" (642 rows). It is recovering
the discarded within-tier ordering from outlets that already contribute: 47,416 rows carry
both a rank and an FV. The prize is roughly 74x the stated rationale and in a different place.

### 2c. The org-list trap, and a correction to the plan's own J0 grouping

`consensus._ORG_LIST_LABEL_RE` (`consensus.py:336`) is imported, not re-derived. Applied to
`interval_label` on the 47,416+642 ranked rows:

| segment | ranked rows |
|---|---|
| mlb_pipeline ORG (Top 10/20/25/30) | 13,051 |
| mlb_pipeline GLOBAL | 5,727 |
| fangraphs GLOBAL | 24,300 |
| tjstats GLOBAL | 4,502 |
| espn / just_baseball / baseballamerica GLOBAL | 252 / 126 / 100 |

**69.5 percent of MLB Pipeline's ranked rows are org Top-30 lists.** The plan's own J0
grouping key `(source, snapshot_date)` pools them with the global Top-100 on the same date.
That is the exact pooling the Bryan Sanchez canary forbids (rank 30 on a 2021 Nationals
Top-30 inflated to FV 55 and sorted him 19th overall with zero published FVs). J0's headline
counts survive it because they are marginal counts, but **this measurement segments org and
global into separate populations everywhere and never pools them**, and the cell key here is
`(source, org|global, snapshot_date, interval_label, fv)`, which is strictly finer than the
plan's.

---

## 3. Pre-registered protocol

**Label basis.** The same resolved-outcome basis the eFV training matrix uses:
`efv_dataset.run` `full_pool_resolved` (`efv_dataset.py:1372`), read off the on-disk labeled
matrices `data/xfv_hitter_matrix.json` (1,917 rows) and `data/xfv_pitcher_matrix.json`
(2,040 rows), 3,957 distinct `player_key`s. Concretely:

- **HEADLINE, fully resolved:** `target_resolved`, keeping debuted rows with `censored ==
  False` plus bust rows with `bust_recent` falsy. This deliberately excludes every
  right-censored row, because `target_censored` rides the flat-rate tail projection
  (`_label_6yr`, `efv_dataset.py:879-894`) that Lane B is measuring in parallel.
- **SECONDARY, censored-inclusive:** `target_censored` on `full_pool_censored` (censored
  debuted rows included, `bust_recent` still excluded).

**As-of discipline.** A snapshot row is kept only when `snapshot_date <= cutoff`, where
`cutoff` is the eFV decision point on that player's matrix row. For debuted players that is
the pre-debut decision date, so post-debut board rows (a source re-ranking a player after
seeing MLB performance) cannot enter. For busts `cutoff` is today, so all their rows enter.
This drops 3,347 of 22,512 labeled ranked rows.

**Cells.** Group by `(source, org|global, snapshot_date, interval_label, fv)`. Keep cells
with `n >= 5` after the label filter.

**Statistic.** Sign convention: `score = -rank`, so a better (lower-numbered) rank is a
higher score and a positive statistic means rank predicts WAR in the expected direction.

- **Headline `gamma_pooled`**: over all qualifying cells, count concordant and discordant
  `(score, WAR)` pairs *within* cells only, then
  `gamma = (n_conc - n_disc) / (n_conc + n_disc)`. Pairs tied on either axis are excluded
  from both numerator and denominator. Pair-pooling is the cell-size weighting: a cell of
  n contributes n(n-1)/2 pairs. Ties matter here because the bust pool concentrates a large
  mass at exactly WAR 0.0.
- **Secondary `spearman_wmean`**: n-weighted mean of the per-cell Spearman rho. Reported so
  the headline is not an artifact of the n-squared pair weighting.

**Mandatory control (the gate).** The identical statistic with `rank` **permuted within each
cell**. Identical marginal, zero ordering information. 1,000 permutations, reported as a
null band (mean, sd, and the 2.5 / 50 / 97.5 / 99 percentiles), plus an empirical one-sided
p-value.

**Cluster-aware uncertainty.** 2,911 distinct players supply the 10,427 headline rows, so
cells are heavily correlated across dates and the within-cell permutation null understates
the real statistic's variance. A **player-cluster bootstrap** (resample distinct
`player_key`s with replacement, rebuild cells from scratch, recompute, 500 draws) supplies
the honest CI on the real statistic. Reporting only the permutation p-value would be the
same class of error as the omnibus-3 MDE premise that resampled the train frame.

**Segmentation.** FanGraphs and MLB Pipeline reported separately, org and global reported
separately, and a per-FV-tier breakdown (<=40 / 45 / 50 / 55+) because the elite tiers are
where the claim matters and where cells are smallest.

---

## 4. Pre-registered success criterion

Standing rule 9: marginal is FAIL. A point estimate inside its own noise floor is a NULL,
and recording a null is a successful lane outcome.

**PASS (Lane J stays open for a future wave) requires ALL of:**

1. `gamma_pooled` on the headline (fully resolved, fangraphs/global) is **strictly above the
   99th percentile** of its 1,000-draw within-cell permutation null.
2. The **player-cluster bootstrap 2.5th percentile** of `gamma_pooled` is **above the 97.5th
   percentile of the permutation null**. This is the clause that makes the clustering count.
3. The sign is **consistent and positive in at least two independent segments** (fangraphs
   global plus at least one of mlb_pipeline global / mlb_pipeline org), so the result is not
   one outlet's artifact.
4. `spearman_wmean` agrees in sign with `gamma_pooled`, so the headline is not a pure
   pair-weighting artifact.

**FAIL / NULL if any of the four is not met.** In that case: record the null, close Lane J,
and do not build.

**A PASS does NOT authorize a build in this wave** (plan `:882` stop clause). A PASS also
does not establish incremental value over the eFV feature set; the marginal question
measured here and the incremental question are different, and the incremental one is Lane
J3 Route 1's job, gated at the feature-add floor (0.0193 hit / 0.0127 pit).

**Sizing, counted before the statistic was computed** (no outcome quantity involved):
headline basis yields **493 cells, 10,427 rows, 2,911 distinct players**
(fangraphs/global 56 cells / 5,949 rows; mlb_pipeline/global 36 / 614; mlb_pipeline/org
401 / 3,864). Censored-inclusive basis yields 735 cells / 16,836 rows / 3,768 players.
tjstats, ESPN, JustBaseball and Baseball America contribute **zero** labeled cells: their
snapshots are 2026-only and every ranked player on them is still a live prospect with no
resolved outcome. Those four outlets are therefore unmeasurable in this gate and must not be
weighted on the basis of it.

---

## 5. RESULT

All numbers below carry an artifact key into `data/consensus_rank_eval.json`.
Seed 20260807, 1,000 permutations, 500 cluster-bootstrap draws.

### 5a. The pre-registered headline: NULL, and very slightly negative

`results.resolved.by_segment["fangraphs/global"]`

| quantity | value |
|---|---|
| cells (n >= 5) | 56 |
| rows | 5,949 |
| distinct players | 1,784 |
| comparable pairs | 173,717 (of 591,058; 417,341 tied) |
| **gamma_pooled** | **-0.00985** |
| spearman_wmean | -0.00443 |
| permuted null | mean +0.00049, sd 0.02107, p50 +0.00099, p97.5 +0.04071, **p99 +0.04762** |
| one-sided perm p | **0.690** |
| player-cluster bootstrap | p2.5 **-0.06724**, p50 -0.00786, p97.5 +0.04931 |

The point estimate sits half a null standard deviation on the **wrong side** of the
permuted control's median. The cluster bootstrap CI is 2.8x wider than the permutation
null's, which is exactly the clustering penalty the registration anticipated: 1,784
players supply 5,949 rows.

### 5b. Every other segment, resolved basis

`results.resolved.by_segment`

| segment | cells | rows | players | gamma | perm p | perm p99 | cluster boot [2.5, 97.5] |
|---|---|---|---|---|---|---|---|
| fangraphs / global | 56 | 5,949 | 1,784 | -0.00985 | 0.690 | +0.0476 | [-0.0672, +0.0493] |
| mlb_pipeline / global | 36 | 614 | 357 | **+0.0934** | 0.0080 | +0.0879 | [+0.0151, +0.1641] |
| mlb_pipeline / org | 401 | 3,864 | 2,043 | +0.0255 | 0.0999 | +0.0433 | [-0.0294, +0.0702] |

tjstats, ESPN, JustBaseball and Baseball America produced **zero qualifying cells** on both
bases: their snapshots are 2026-only and every ranked player is still unresolved. They are
not measurable in this gate and must not be weighted on it.

### 5c. Gate clauses

`gate_clauses`

| clause | requirement | result |
|---|---|---|
| c1 | headline gamma > permuted p99 | **FAIL** (-0.00985 vs +0.04762) |
| c2 | bootstrap p2.5 > permuted p97.5 | **FAIL** (-0.06724 vs +0.04071) |
| c3 | positive in >= 2 independent segments | **FAIL** (FanGraphs is negative) |
| c4 | spearman_wmean agrees in sign | pass (both negative) |

**GATE VERDICT: NULL. Lane J closes. Do not build consensusRank.**

Applying the same four clauses to the best-looking segment, `mlb_pipeline/global`, it
clears c1 (+0.0934 > +0.0879) but **fails c2** (bootstrap p2.5 +0.0151 is below the
permutation p97.5 +0.0719). Standing rule 9: marginal is FAIL.

### 5d. Secondary, censored-inclusive basis

`results.censored.by_segment`. Same conclusion, and the extra rows do not rescue it:
FanGraphs global gamma -0.00377 (p 0.647), MLB Pipeline global +0.0317 (p 0.123),
MLB Pipeline org +0.0326 (p 0.0070, and this is the segment the resolved basis puts at
+0.0255 with p 0.0999, so the censored basis is mildly more favourable, consistent with
`target_censored`'s flat-rate tail projection adding correlated structure rather than
signal). Nothing here changes a clause.

---

## 6. THE FINDING THAT MATTERS MORE THAN THE GATE

Post-hoc, not pre-registered, and it does **not** change the verdict above. It was found
while inspecting the plan's own largest tie cell.

### 6a. FanGraphs stores two different quantities in one `rank` column

`posthoc.fangraphs_rank_semantics`

On the 2026-08-02 board (`2026updated`, 1,384 ranked+FV rows):

| FV | n | rank range | distinct ranks |
|---|---|---|---|
| 65 | 1 | 1..1 | 1 |
| 60 | 8 | 2..9 | 8 |
| 55 | 21 | 10..30 | 21 |
| 50 | 84 | 31..114 | 84 |
| 45 | 174 | **1..23** | 23 |
| 40 | 626 | **5..46** | 42 |
| 35 | 470 | **18..72** | 55 |

The rank **restarts** below FV 50. Rows at FV >= 50 carry THE BOARD's global rank, unique
1..114 across 29 orgs. Rows below carry a **per-organization** rank: ARI's sub-50 players
run 1..59 contiguously, ATH's 2..38, ATL's 3..40. Both live under the same
`interval_label`, so `_ORG_LIST_LABEL_RE` cannot possibly separate them.

**The canary, and it is exactly the Bryan Sanchez shape one level down:** the 2026-08-02
board contains **two rows at rank 1** -- Jesus Made (MIL, FV 65, genuinely the number one
prospect in baseball) and JD Dix (ARI, FV 45, Arizona's best player below the global cut).
They are indistinguishable in the `rank` column.

Across all FanGraphs history: **22,367 of 24,300 ranked+FV rows (92.0 percent) carry an
org rank, not a global rank.** Only 1,933 are globally ranked. Per-snapshot the global
block is 9 to 137 rows.

### 6b. Consequence 1: the plan's stated prize does not exist at the stated size

The plan (`:882` rationale) values this lane at "roughly 47,000 ranked rows" of discarded
within-tier **global** ordering. The genuinely global-ranked population is:

| source | globally-ranked rows |
|---|---|
| fangraphs | 1,933 |
| mlb_pipeline (global, non-org label) | 5,727 |
| tjstats | 4,502 |
| espn | 252 |
| just_baseball | 126 |
| baseballamerica | 100 |
| **total** | **12,640** |

and 4,980 of those are 2026-only outlets with no resolved outcome. The prize is 3.8x
smaller than stated, and its labeled, measurable portion is smaller still. The plan's claim
that the payoff is "about 70x larger than the stated rationale" is **FALSE as stated**; the
correct multiple against the 642 rank-only rows is about 20x, and that 20x turns out to
carry no measurable ordering information (6c).

### 6c. Consequence 2: measuring org ranks correctly does not rescue the lane

`posthoc.measurements.resolved`. Re-segmenting FanGraphs by actual rank semantics, with org
ranks compared **only within the same org** (cell = date, label, org, fv):

| segment | cells | rows | players | gamma | perm p | cluster boot [2.5, 97.5] |
|---|---|---|---|---|---|---|
| fangraphs GLOBAL_RANK | 18 | 269 | 132 | +0.0903 | 0.0400 | **[-0.0428, +0.2241]** |
| fangraphs ORG_RANK (within org) | 538 | 4,516 | 1,563 | **-0.0317** | 0.888 | [-0.1003, +0.0457] |

The 22,367-row org-ranked population, measured the only way it is defined, is a **hard
null with a negative point estimate**. The 1,933-row global block is positive but its
labeled portion is 269 rows and its cluster bootstrap spans zero. Correcting the defect
sharpens the diagnosis and does not change the verdict.

### 6d. The one residue worth recording for a future wave

`posthoc.measurements.resolved["mlb_pipeline/global fv55+ (bootstrapped)"]`

MLB Pipeline's global Top-100 rank, within FV 55+ tie cells: 24 cells, 469 rows, 269
players, **gamma +0.1118**, permutation p **0.0040** (null p99 +0.0924), cluster bootstrap
**[+0.0255, +0.1140, +0.1968]**. This is the only segment anywhere in the study whose
cluster bootstrap excludes zero.

It still **FAILS pre-registered clause c2** (+0.0255 is below the permutation p97.5 of
+0.0786), and it is one of 11 tier-level comparisons, so multiplicity applies. It is
recorded as a lead, not a result. It is also the one place the frontier audit's "genuine
gap is within-elite-tier discrimination" would predict a signal, which is why it is worth
a note rather than silence. Re-open only with a fresh, pre-registered, single-hypothesis
test on new data, never by re-reading this artifact.

### 6e. Consequence 3: a live, latent org-list defect in `consensus.py`

Two distinct problems, reported for the orchestrator to apply since Lane J1 does not own
`consensus.py`:

1. **`_ORG_LIST_LABEL_RE` (`consensus.py:336`) misses "Top 50" org lists.** Three labels
   escape it: `FanGraphs 2026 Pirates Top 50`, `FanGraphs 2026 Twins Top 50`, `SFG Top 50`
   (150 rows). Three more escape every rule via slug labels: `miami_marlins_2026`,
   `tampa_bay_rays_2026`, `bos2026may` (163 rows). 313 rows total.
2. **The 22,367 in-board FanGraphs org ranks pass the guard entirely** (`consensus.py:693`),
   because their `interval_label` is `2026updated`. They enter `ranks` and therefore
   `avg_rank` (`consensus.py:732`), where an ARI org rank 1 is averaged against an MLB
   Pipeline global rank 1. 5,282 distinct players are affected. `spotlights.py:407` reads
   `avg_rank` to build a rank-jump driver, so a "riser" can be manufactured purely by a
   player's mix of org-ranked and globally-ranked snapshots changing between windows.

**Severity is LATENT, not live, for the FV path.** `implied_fv_from_rank` is a fallback
used only when a player has zero explicit FVs (`consensus.py:757`), and all 313 + 22,367
affected rows carry an `fv`, so no current player is priced off a bad rank-implied FV. It
is one FV-less org list away from repeating Bryan Sanchez exactly. The `avg_rank` and
spotlights path IS live today.

---

## 7. Verdict and disposition

- **J0 premise: REPRODUCES EXACTLY.** The FV lattice does discard published ordering on
  99.9 percent of rows.
- **Owner premise 1 (JustBaseball publishes FVs): CONFIRMED.** 126 of 126.
- **Owner premise 2 (rank-only population is small): CONFIRMED.** 642 rows exactly.
- **Plan premise that the prize is ~47,000 rows and ~70x: FALSE.** The globally-ordered
  population is 12,640 rows, about 20x, and it does not measure.
- **J1 GATE: NULL on every pre-registered clause.** Close Lane J. Do not build
  consensusRank. Do not build it on the 6d lead either.
- **Route 3 (rank as a pure display tiebreaker) is NOT rescued by this.** It carries no
  accuracy gate by design, but tiebreaking on a column that is an org rank 92 percent of
  the time would order the board by "best in his own farm system" inside a tie. If Route 3
  is ever wanted, it must consume only the global-rank block identified in 6a.
- **Carry forward:** the `consensus.py` defect in 6e, and the 6d lead.

_Cost of this lane: one day, as the plan budgeted. Recording a null is the successful
outcome (standing rule 9)._

