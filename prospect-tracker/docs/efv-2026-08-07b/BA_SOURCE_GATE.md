# BA source gate (lane BA1)

Pre-registered 2026-08-08, BEFORE the lab was written or run. The
"## RESULT (appended after the run)" section at the bottom is the ONLY part
filled in afterwards. Everything above it is the contract.

Artifact: `data/ba_consensus_eval.json`
Lab: `tools/ba_consensus_lab.py`

## The question

Baseball America org Top 30 boards for 2023, 2024, 2025 and 2026 are in
`snapshots`. `consensus.compute_consensus_point` does not filter by source, so
BA is ALREADY a voting member of the consensus. Nothing needs enabling. The
question is therefore not "can we add it" but two separate questions:

1. Should BA vote in the DISPLAYED consensus (the board a reader sees)?
2. Should BA be allowed to move `consensus_fv_raw`, which is
   `_FEATURES_HIT[0]` / `_FEATURES_PIT[0]` (the dominant eFV feature), the
   consensus leg of the served blend, AND the baseline eFV is scored against?

These can be answered differently and the repo can implement them separately.

## The hazard being tested

BA org Top 30s are a quality-selected population. Coverage correlates with the
outcome (brief-supplied, to be reproduced): hitter pool debuted rate 44.1% vs
74.8% among BA-covered; pitcher 48.1% vs 82.6%. A source whose coverage tracks
survival can inject outcome information into the dominant feature without
anyone adding a BA feature. The repo has a recorded precedent: a MiLB deep
backfill regressed the ridge (debuted_km 0.3854 to 0.3678) because "has a
grade" correlated with survival. The pre-registered revival condition for that
class of change was era control OR symmetric bust-side coverage.

## Gates

### G1 NORMALIZATION (blocker gate)

`grade_normalization._paired_dists` pools a (source, role, cycle-year) cell
ACROSS ALL YEARS, including future ones, when the cycle overlap with FanGraphs
is under `_MIN_N = 30`. That is leak D1 reproduced on a new source.

PASS requires, for every (baseballamerica, role, year) cell that a live
consensus build would touch:
* paired n >= 30 on the cell's own year, AND
* `pooled == False` returned by `_paired_dists`, AND
* the cell present in `build_remapper`'s table (so the raw fallback is not
  silently carrying the grade).

ANY cell that pools across years is a BLOCKER and must be reported plainly as
one. The 2026 era change (BA Adjusted Grade replaces BA Grade, roughly a
-11.4 FV level shift) makes this load-bearing: if any cell pools, the era
break is smeared across vintages.

Also reproduced as an arithmetic check, from the artifact:
* same-player consecutive-board BA fv deltas for 2023>2024, 2024>2025,
  2025>2026 (expect roughly -0.6, -0.8, -11.9)
* BA minus contemporaneous FanGraphs fv by year (expect roughly +6.6, +6.8,
  +6.4, -5.0)

### G2 ORG-LIST GUARD (blocker gate)

`consensus._ORG_LIST_LABEL_RE = r"\bTop\s+(?:10|20|25|30)\b\s*$"` must match
every BA org-board label, or BA ranks feed `implied_fv_from_rank` and every
number-one org prospect becomes FV 70 (the Bryan Sanchez failure).

PASS requires:
* all 52 org-board `interval_label` values match the regex, AND
* zero BA org-board rows contribute to `rank_implied_fvs` in a real lab
  consensus computation over the full corpus.

Any BA row that is NOT an org board (for example the pre-existing 2026-06-03
Top 100) is reported separately with its rank-implied exposure, because a
global Top 100 is legitimately rank-implied-eligible and that is a different
decision.

### G3 CONSENSUS ACCURACY (ship gate for the DISPLAYED consensus)

Build the consensus twice in the lab, with and without BA snapshots, over the
full corpus. Score both against realized WAR with `source_backtest`'s two
instruments, forward-chained by year, on the COMMON set (players both arms
grade in that preseason window):
* Spearman(consensus FV, realized career WAR)
* AUC(consensus FV, contributor = career WAR >= 3.0)

`MIN_LAG_YEARS = 3` and `CANDIDATE_YEARS = (2017..2024)`. Forward-fill means
BA cannot touch any event date before 2023-02-15, so 2017 to 2022 are
identically scored in both arms by construction and only 2023 (lag 3, in
window) and 2024 (lag 2, marginal) can move.

SHIP requires BOTH d_rho >= 0 and d_auc >= 0 with a paired-bootstrap CI95 that
excludes zero, on the affected years, over the common set.
MARGINAL IS FAIL. If the affected-year n is too small to resolve an effect,
report the MDE floor and return NULL rather than a point estimate. A null here
is a successful lane outcome.

### G4 SELECTION CONTAMINATION (blocker gate for the TRAINING frame)

On the shipped hitter and pitcher matrix rows, join each row's
(player_key, cutoff) to the as-of consensus point in each arm and take
`delta = consensus_fv_raw(with BA) - consensus_fv_raw(without BA)`.

BA is DISQUALIFIED from the training frame if ANY of:
* (a) the correlation between `delta` and the label is positive with a CI95
  excluding zero, for either label (debuted, realized WAR), OR
* (b) mean `delta` on debuted rows exceeds mean `delta` on bust rows by more
  than the permuted control band's p95 (see C1), OR
* (c) the BA-covered subset's debuted rate exceeds the pool rate by more than
  10 points AND that coverage gap survives the within-league control (C2).

The 10-point figure in (c) is a threshold this lane is adding; the brief does
not contain it. It is a nuisance-level bound only, chosen because the brief's
own measured gaps are +30.7 and +34.6 points, i.e. three times it. If it ends
up determining the verdict on its own, that will be stated in the headline.

### C1 MANDATORY CONTROL, permuted coverage

The lane is VOID without this. Permute WHICH players receive BA coverage,
holding the number of covered players per board and the grade/rank
distribution fixed, then rebuild the with-BA arm and recompute every G4
quantity. Two donor pools, both reported:
* C1a: all players with any non-BA snapshot in the same cycle year
* C1b: the same, restricted to players whose org is one of the 13 BA-covered
  clubs (holds club, and therefore league, roughly fixed)

>= 20 seeds each. Report the p5/p50/p95 band. If the real assignment's
apparent consensus gain or debut-rate lift sits INSIDE the permuted band, the
effect is a coverage artifact rather than BA information, and any G3 "gain"
must be reported as such even though it cuts against shipping.

### C2 MANDATORY CONTROL, within-league

BA covers only American League clubs. Compare AL players WITH BA coverage
against AL players WITHOUT it (ranked below their org top 30 or on an
uncovered AL club), on debuted rate and realized WAR. This holds league fixed
and isolates the top-30 selection from the league-composition confound. Report
the number of voting sources per player by league, since a player's source
count now depends on his league.

## Out of scope

Re-fitting consensus outlet weights. That arm is CLOSED (reverted to equal
2026-07-25, ship gate hardened at `source_backtest.py:897-915`). Adding a
source is a different question and this lane does not touch weights.

## Non-negotiables

* No served artifact is written. `data/timeseries.json`, `data/xfv*.json` and
  `data/source_backtest.json` are read-only to this lane.
* Every number in the report reproduces from `data/ba_consensus_eval.json`.
* Multiplicity is reported whenever k of n cells are quoted as significant.

## RESULT (appended after the run)

Run 2026-08-08, `python tools/ba_consensus_lab.py`, 282.1 s, full corpus of
55,696 snapshots. Every number below reproduces from
`data/ba_consensus_eval.json`.

Headline: G2 PASS, G1 FAIL on one cell, G3 NULL and 20x underpowered, G4 NOT
a leak once the mandatory control runs. BA belongs in the DISPLAYED consensus
after the 2023 position defect is fixed. BA does NOT belong in the training
frame yet, and the reason is re-gating and mis-normalization, not outcome
leakage.

### G1 NORMALIZATION: FAIL (one cell), and the root cause is an ingest defect

The seven cells BA rows actually route into all pass cleanly. Own-year paired
overlap with FanGraphs, `_MIN_N = 30`, `pooled = False`, present in
`build_remapper`'s table, fitted offset (`mean(src) - mean(ref)`, subtracted
from the grade):

| role | year | BA rows w/ fv | paired n (own year) | pooled | offset |
|---|---|---|---|---|---|
| hitter | 2023 | 385 | 169 | no | +6.361 |
| hitter | 2024 | 225 | 175 | no | +6.686 |
| hitter | 2025 | 200 | 166 | no | +7.470 |
| hitter | 2026 | 192 | 171 | no | -5.175 |
| pitcher | 2023 | 0 | 0 | **YES (n 461)** | +1.920 |
| pitcher | 2024 | 158 | 134 | no | +6.754 |
| pitcher | 2025 | 184 | 159 | no | +5.094 |
| pitcher | 2026 | 191 | 168 | no | -4.940 |

The era break IS absorbed per year, as designed. The live remapper probe shows
BA 50 mapping to 43.6 in hitter 2023 and to 55.2 in hitter 2026, a 11.5 FV
swing that exactly tracks the Adjusted Grade change. The two arithmetic checks
reproduce the brief: consecutive-board deltas -0.644 (n 194), -0.833 (n 198),
-11.888 (n 196); BA minus contemporaneous FanGraphs +6.606 (n 302), +6.726
(n 310), +6.319 (n 326), -5.059 (n 339).

The failing cell is (baseballamerica, pitcher, 2023). Its own-year overlap is
ZERO, so `_paired_dists` falls back to the cross-year pool of 461 pairs
spanning 2023 to 2026, which averages the +6.7 / +5.1 pre-era offsets with the
-4.9 post-era one and lands at +1.920. `build_remapper` publishes it, because
it length-checks the POOLED array and never reads the `pooled` flag. That is
leak D1 reproduced on a new source.

Root cause, and it is worse than the pooled cell: the 2023 vintage carries no
usable position. Of 385 stored rows, 363 have `position IS NULL` and 22 carry
the token "CP", which is not in `grade_normalization._PITCHER_TOKENS` and, on
the row it appears on, belongs to a catcher (Logan O'Hoppe). The source CSVs
are already empty (`data/baseballamerica_imports/processed/ba__2023__*.csv`:
367 blank of 389), so this is a 2023-format parse miss, not a DB write bug.
Consequence: **167 of the 385 BA 2023 rows are pitchers per another source's
position, and all 167 are priced with the HITTER offset (+6.361) instead of a
pitcher-2023 offset.** The pooled pitcher cell is unreachable today only
because no 2023 BA row can be recognised as a pitcher, so the leak is latent
and the mis-normalization is live.

Wider context, out of this lane's ownership and reported for the record: 138
of the 176 live remapper cells across ALL sources are cross-year pooled. Most
are inert (own-year n = 0 for a year the source never published). The ones
that both pool and fire are (mlb_pipeline_international, hitter) 2021, 2022
and 2023, at own-year n 18, 19 and 28.

### G2 ORG-LIST GUARD: PASS

53 distinct BA interval labels, 52 of them org boards, 52 of 52 matched by
`_ORG_LIST_LABEL_RE`. All 1,535 org-board rows are excluded from `avg_rank`
and `rank_implied_fvs`. Zero org-board rows are rank-implied eligible, so
there is no Bryan Sanchez exposure from this ingest.

The one non-org label is the PRE-EXISTING `Baseball America 2026-06-03 Top
100`. Those 100 rows carry `fv IS NULL` and a rank, so they ARE rank-implied
eligible by design (a global Top 100 legitimately is). In a real full-corpus
consensus build, 0 of them reach `rank_implied_fv`, because every one of those
players already has an explicit FV from another source at that event date.

### G3 CONSENSUS ACCURACY: NULL, and the sign is negative

Forward-fill means BA cannot touch any event date before 2023-02-15, and the
lab confirms it as a built-in control: d_spearman and d_auc are EXACTLY 0.0 in
2017, 2018, 2019, 2020, 2021 and 2022, on n_common 442 to 964. Only 2023 is
both in `CANDIDATE_YEARS` and at `MIN_LAG_YEARS >= 3`. 2024 is at lag 2 and is
not scored.

On 2023, n_common 1,064, of which 301 rows moved and 298 are BA covered:

* d_spearman -0.00258, paired-bootstrap CI95 [-0.01491, +0.00925]
* d_auc -0.00531, CI95 [-0.01546, +0.00429]
* baseline Spearman without BA 0.2522
* MDE floor (zero-information placebo half-width) 0.0597

The observed effect is 0.043x the resolvable floor, i.e. roughly 23x
underpowered, and both point estimates are NEGATIVE. Under "marginal is FAIL"
this is a NULL with no ship claim available in either direction. The honest
statement is "no detected gain and no detected harm", not "no harm".

### G4 SELECTION CONTAMINATION: coverage bias CONFIRMED, leak NOT confirmed

3,446 matrix rows joined to both arms; 166 moved. delta mean -0.181,
sd 1.471, max abs 5.68 FV.

* debuted rows (n 134): mean delta -0.453
* bust rows (n 32): mean delta +0.955
* gap -1.407, CI95 [-1.970, -0.814]
* corr(delta, debuted) -0.3785, CI95 [-0.5148, -0.2152]
* corr(delta, realized target) -0.0215, CI95 [-0.1420, +0.1113]

Pre-registered disqualifier (a) fires only on a POSITIVE correlation. The
measured correlation is NEGATIVE and it is the debut flag, not the WAR target,
that moves. BA is not raising the consensus for players who went on to debut.
It is LOWERING it for them, because debuted rows take their as-of point from a
pre-2026 BA board (offset subtracts about 6 FV) while bust rows take their
final point from the 2026 Adjusted Grade board (offset adds about 5 FV). That
is an era-and-cutoff artifact, and C1 confirms it below.

Coverage bias reproduces the brief almost exactly. Hitters: pool 845/1917 =
44.08% debuted, BA covered 108/145 = 74.48%, lift +30.4 points. Pitchers: pool
981/2040 = 48.09%, BA covered 104/127 = 81.89%, lift +33.8 points.

Caveat on the join: the no-BA arm reproduces the SHIPPED matrix
`consensus_fv_raw` on 2,578 of 3,446 rows (74.81%, mean abs gap 0.516), and
the miss is concentrated in bust rows (debuted 93.59% match, bust 53.64%).
Bust rows take the LAST point, which moves whenever any source publishes a new
board, so the shipped matrices are simply older than the current corpus. The
with-minus-without contrast is computed inside one run and is unaffected, but
it also means the served eFV matrices were built on a consensus that no longer
matches the live one.

### C1 PERMUTED COVERAGE: the control kills the label correlation

24 seeds per donor pool. Real value against the permuted p5/p50/p95 band:

| statistic | real | pool "all" | pool "covered clubs" | verdict |
|---|---|---|---|---|
| corr(delta, debuted) | -0.3785 | -0.4497 / -0.3430 / -0.2286 | -0.3836 / -0.3177 / -0.2331 | INSIDE both |
| corr(delta, target) | -0.0215 | -0.3860 / -0.2945 / -0.2105 | -0.3086 / -0.2116 / -0.1478 | outside, benign side |
| debuted minus bust delta | -1.407 | -3.418 / -2.313 / -1.515 | -2.651 / -2.233 / -1.607 | outside, benign side |
| coverage lift, hitters (pts) | +30.4 | 15.40 / 19.95 / 25.59 | 19.86 / 24.14 / 26.75 | OUTSIDE, above |
| coverage lift, pitchers (pts) | +33.8 | 19.40 / 23.34 / 29.21 | 20.12 / 23.94 / 26.01 | OUTSIDE, above |
| rows moved | 166 | 181 / 193 / 209 | 182 / 195 / 207 | below both bands |

Read it plainly, including the part that cuts against a clean story. The
entire negative correlation between the consensus delta and the debut flag is
a COVERAGE ARTIFACT: a random reassignment of the same 1,635 grades to the
same number of same-cycle players produces the same correlation, median
-0.343, and the real value sits inside the band. So G4(a) and G4(b) are BOTH
unresolved rather than triggered, and no leak is demonstrated.

The control also deflates the coverage headline. About 20 of the 30.4 hitter
points and about 23 of the 33.8 pitcher points are reproduced by a random draw
of the same size from the same-cycle graded pool, because "graded by anybody in
a 2023 to 2026 cycle" already predicts debut on a matrix that spans 2011 to
2024. The INCREMENTAL selection attributable to being on a BA org top 30 is
about +10.5 points on each side, not +30 to +34.

### C2 WITHIN-LEAGUE: selection is real at about +11 points

BA covered vs the same 13 clubs NOT BA covered (the covered-club set is
derived from the 52 org-board labels only; deriving it from all BA rows
silently pulls in all 30 clubs via the 2026-06-03 Top 100, which was a lab
defect caught and fixed before this run):

| cycle | covered n | covered debut | uncovered n | uncovered debut | gap | mean WAR covered vs uncovered |
|---|---|---|---|---|---|---|
| 2023 | 331 | 69.79% | 263 | 59.32% | +10.5 | 1.024 vs 0.305 |
| 2024 | 374 | 51.07% | 309 | 39.81% | +11.3 | 0.543 vs 0.095 |
| 2025 | 382 | 39.79% | 371 | 28.03% | +11.8 | 0.289 vs 0.074 |

Consistent with C1: about +11 points of genuine top-30 selection, holding club
and therefore league fixed. Contributor rate separates harder than debut rate
(13.9% vs 4.9% in 2023).

League also changes how many voices a player gets. On points dated 2023-02-15
or later, players on the 13 BA-covered clubs average 1.723 contributing
sources against 1.471 for everyone else, a gap of +0.252 votes. Note the
covered set is 13 clubs, not 15: SEA and TEX are American League clubs with NO
BA coverage in this corpus, so "AL vs NL" is not the right frame and the
club-level contrast above is.

### VERDICT

* G1 FAIL (blocker, one cell plus a live mis-normalization of 167 rows)
* G2 PASS
* G3 NULL, 23x underpowered, point estimates negative
* G4 selection CONFIRMED at about +11 points incremental, leak NOT confirmed
  (the mandatory permuted control reproduces the whole label correlation)

DISPLAYED consensus: keep BA, CONDITIONAL on fixing the 2023 position parse
and reworking the pooled pitcher-2023 cell. It is already voting, its per-year
offsets are measured on 134 to 175 paired players each, the org guard holds,
and the measured accuracy cost is inside a band 23x wider than the effect.
More scouting opinion for a reader is an editorial good this lane cannot
price, and the measurement does not stand in its way.

TRAINING frame: do NOT let BA move `consensus_fv_raw` as consumed by
`efv_dataset` until the 2023 vintage is repaired and the matrices are rebuilt
and re-gated. The reason is NOT leakage. It is that (i) 167 of the 385 rows in
the 2023 vintage are mis-normalized today, (ii) BA moves the dominant feature
by up to 5.68 FV on 166 training rows, and (iii) the served matrices already
fail to reproduce from the current corpus on 25% of rows, so shipping a
feature change on top of that would land two uncontrolled changes at once.

Mechanism, if the two decisions are to be implemented separately: the display
path and the training path currently share ONE artifact, because
`efv_dataset._prior_features` reads `pt["consensus_fv_raw"]` straight out of
`data/timeseries.json`. Separating them needs a second consensus value
persisted on each point (a `consensus_fv_raw_train` computed from a
source-filtered `day_snaps`) with `efv_dataset` reading that key, or a second
source-filtered `build_timeseries` pass at matrix-build time. The second pass
costs about 6 seconds on the full corpus, measured in this lab, so cost is not
the obstacle. Neither file is owned by this lane, so both are reported as edit
requests rather than made.

Outlet weights were not touched. That arm stays closed.
