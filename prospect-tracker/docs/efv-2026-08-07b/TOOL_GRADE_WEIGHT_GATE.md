# TOOL GRADE WEIGHT GATE (Lane BA2, 2026-08-07b): can a source be weighted PER TOOL?

**STATUS OF THIS FILE.** Sections 0 through 7 are the PRE-REGISTRATION. They were written
in full, including every PASS clause, every FAIL clause and every stop clause, BEFORE
`tools/ba_tool_grade_lab.py` existed and therefore before any number in section 8 could be
known. Section 8 is a placeholder filled in after the run. Nothing in sections 0 to 7 is
edited afterwards.

Artifact: `data/ba_tool_grade_eval.json`
Lab: `tools/ba_tool_grade_lab.py`
Read-only dependencies: `efv_tools.py`, `consensus.py`, `source_backtest.py`,
`grade_normalization.py`, `storage.py`.

---

## 0. THE PLAN PREMISE THIS LANE CORRECTS

Master plan Lane K0 records Baseball America as carrying ZERO tool grades and concludes
"the BA question and this lane are disjoint". **That premise is FALSE as of this session.**
It was true of the 100-row rank-only Top 100 at `2026-02-15`... in fact at `2026-06-03`,
which is the only BA snapshot that predates this session's org-board ingest and the only
one that carries no `tools_json`.

The corrected premise, to be reproduced by the lab as its first act:

> `snapshots` now holds 52 Baseball America preseason org Top 30 boards (13 American
> League clubs x 4 vintages 2023/2024/2025/2026) and every ingested row carries
> `tools_json`. The brief states 7,285 tool observations across 1,502 rows. The lab
> recomputes this and reports its own number; any disagreement is reported, not
> reconciled away.

The count matters only for the premise correction. It does not enter any gate.

## 0.1 The trap, stated so it can be checked against the result

The lane's stated expectation is that BA shrinks to equal. That expectation is the DEFAULT
and the safe outcome, and a lane that produces it is successful. The failure mode to guard
against is the opposite one: manufacturing a weight out of a thin cell by relaxing the
vintage rule, pooling tools, or accepting a margin the test cannot resolve.

- The criterion is NOT "is the weighted arm ahead". It is "is it ahead by more than this
  A/B can resolve, on BOTH metrics, with a permuted-source-label null that does not
  reproduce it".
- Marginal is FAIL.
- This lane SHIPS NO CONSTANT. Its output is a measurement and a recommendation.
  `consensus.py` line 1050 computes the per-tool consensus as an unweighted mean; changing
  that is out of scope for this lane and is not attempted.

---

## 1. What is actually being tested

`consensus.py` around line 1050:

```
# Per-tool consensus = unweighted mean across publishing sources.
```

That is EQUAL WEIGHT, unexamined. Lane K's parent question was whether accuracy weighting
can beat it. For FV grades that question was already answered NO and the weights were
reverted to equal: only 2 of 8 outlets had resolvable history and their precisions were
indistinguishable (residual variance 14.362 vs 14.462, difference CI95 [-0.649, +0.454]),
so `source_backtest.py:897-915` hardened the ship rule to require a gain larger than the
measured MDE on both metrics.

Four things differ for TOOLS and are why this lane is worth running:

1. five to seven observations per player instead of one;
2. each tool predicts a SPECIFIC directly measured quantity, not a six-year WAR total;
3. the label horizon is SHORT;
4. the machinery already exists (`efv_tools.py`).

## 1.1 REUSE, NOT REINVENTION

The tool-to-outcome mapping is taken **verbatim from `efv_tools._TOOLS`** and is imported,
not retyped, so the two analyses stay comparable:

| tool | realized MLB stat | orientation |
|---|---|---|
| `hit` | `avg` | higher better |
| `game_pwr` | `iso` | higher better |
| `speed` | `sb` | higher better |
| `fb` | `k_pct` | higher better |
| `cmd` | `bb_pct` | LOWER better |

`efv_tools._PASSTHROUGH` records the rest (`raw_pwr`, `field`, `throw`, and the individual
pitch shapes `sl` / `cb` / `ch` / `ct`) as having no clean realized MLB metric in this
data. **A tool with no realized target cannot carry a measured precision.** The lane
therefore CANNOT weight those tools at all, and this is a scope limit, not a null result.
The lab reports what fraction of each source's tool observations fall inside the scoreable
five.

## 1.2 One deliberate departure from `efv_tools`

`efv_tools._realized_mlb()` aggregates over ALL MLB seasons in `career_stats`, including
seasons that precede the board date. That is acceptable for its purpose (it scores a
resolved cohort). It is NOT acceptable here, because this lane is a forward-chained
accuracy test and a grade must not be scored against outcomes that were already visible
when it was published.

**This lab restricts the realized aggregate to MLB seasons with `season > Y`, strictly
after the board year Y.** The departure is registered here so it cannot be mistaken for a
reimplementation, and section 8 reports how much it changes the pool.

---

## 2. Universe construction

- **Grades.** `snapshots.tools_json`, canonical tool keys only, `_extras` stripped, grade
  kept only if it parses and lies in [20, 80].
- **Preseason window.** Board-year Y admits snapshot dates in `[Y-01-01, Y-05-01)`. This
  is `source_backtest._WINDOW_START_MMDD` / `_WINDOW_END_MMDD`, adopted unchanged so no
  in-season lookahead enters. All four BA org vintages are dated `Y-02-15` and are inside
  it.
- **One grade per (source, player, tool, year):** the earliest in-window board.
- **Common set.** For a given tool and year, only players graded on that tool by EVERY
  scored source in the arm. This is `source_backtest`'s fairness rule and is adopted so no
  source is advantaged by covering an easier slice.
- **Outcome.** Realized MLB quantity per section 1.1, seasons > Y only, rate stats
  weighted by `ab`/`bf`/`ip`, `sb` as a per-season mean (matching `efv_tools`).
  Sign-oriented so higher is always better.

### 2.1 Which sources are structurally scoreable

Pre-registered prediction, to be confirmed by the lab's own census: only `fangraphs`,
`mlb_pipeline` and `baseballamerica` carry tool grades in more than one year.
`tjstats`, `just_baseball` and `espn` carry tool grades in 2026 ONLY, so they have no
resolvable forward-chained history at any lag and must stay at weight 1.0. That is the
same structural fact that closed the FV weighting lane, and it is not a finding of this
lane so much as a re-observation of it on a second quantity.

### 2.2 THE TWO ARMS

**ARM A (the powered arm): `fangraphs` vs `mlb_pipeline`, per tool.**
Both have deep history; the common set is large. This is where the lane can actually
resolve anything, and the brief predicts as much ("the lane realistically weights
FanGraphs against MLB Pipeline").

**ARM B (the BA arm): `fangraphs` vs `mlb_pipeline` vs `baseballamerica`, per tool.**
BA's earliest vintage is 2023. Under `MIN_LAG_YEARS = 3` a board-year Y may only see base
years <= Y-3, so BA can first contribute a weight at Y = 2026, and Y = 2026 has no
`season > 2026` outcomes in this database. **The pre-registered expectation is therefore
that ARM B cannot produce a single evaluable board-year at the primary lag, and returns
NULL by construction rather than by measurement.** That is stated in advance precisely so
that a NULL here is not later read as evidence that BA grades are bad.

---

## 3. Precision estimator (mirrors `source_backtest.derive_source_weights`)

Per (tool, source), over common-set rows from base years <= `max_base_year`:

```
rho[s]   = pooled Spearman(source's grade, oriented realized quantity)
rho[s]   = max(SPEARMAN_FLOOR, rho[s])          SPEARMAN_FLOOR = 0.05
raw[s]   = rho[s] / mean(rho)
w[s]     = (n*raw[s] + WEIGHT_SHRINK_K) / (n + WEIGHT_SHRINK_K)   K = 150
w[s]     = clamp(w[s], 0.6, 1.5)
```

Constants imported from `source_backtest`, not retyped. Fewer than 60 common rows returns
all-equal, matching the source module. Sources with no resolvable history stay at 1.0:
new sources are never punished for being new.

**PER TOOL, NEVER POOLED.** Every weight in this lane is indexed by tool. Section 6.2
additionally runs the pooled estimator as a deliberately-wrong control, to measure how
much a pooled weight would have averaged away.

---

## 4. The A/B

For each board-year Y that has both a resolvable outcome and at least one usable base year:

- `vintage_max = Y - MIN_LAG_YEARS` (3, imported).
- Derive weights from base years <= `vintage_max` ONLY.
- If the derived weights are all 1.0 within 1e-9, the year cannot differentiate the arms
  and is SKIPPED (matching `source_backtest.run_consensus_weight_ab`).
- On year Y's common set, build both consensus grades:
  `equal = mean(grades)`, `weighted = sum(w*g)/sum(w)`.
- Pool across years, then compute both metrics.

### 4.1 The two metrics

**M1 pooled Spearman** of the consensus tool grade against the oriented realized quantity.

**M2 pooled AUC** of the consensus tool grade discriminating `oriented realized >= the
median of the oriented realized within that board-year`.

**SELF-ADDED THRESHOLD, DECLARED (rule 8).** `source_backtest` uses "career WAR >= 3.0
(contributor)" as its second-metric binary. There is no established analogue for a tool
quantity; nobody has registered "a good ISO" on this platform. The within-board-year
median split is therefore MY definition, chosen because it is distribution-free, has no
free parameter, and is computed within year so it cannot import cross-year drift. If a
gate verdict turns on M2 and would flip under a different binary, section 8 says so in its
first line and the finding is downgraded.

---

## 5. THE SHIP GATE

Structurally the same hardened gate `source_backtest.py:897-915` applies to FV weights: a
gain larger than the test can resolve, on BOTH metrics. The FV gate's literal constants
(`_SHIP_MIN_RHO_GAIN = 0.0068`, `_SHIP_MIN_AUC_GAIN = 0.0052`) were MEASURED on the FV A/B
and do not transfer to a different quantity on a different pool. This lane measures its
own floors.

**PER TOOL, a weighted per-tool consensus SHIPS only if ALL of the following hold:**

- **G1 (M1 resolvable gain).** `d_rho >= F_rho`, where `F_rho` is the p95 of `|d_rho|`
  under the permuted-source-label null of section 6.1.
- **G2 (M2 resolvable gain).** `d_auc >= F_auc`, same construction on M2.
- **G3 (M1 sign certainty).** the paired, player-clustered bootstrap one-sided 95% lower
  bound on `d_rho` is `> 0`.
- **G4 (M2 sign certainty).** same on `d_auc`.
- **G5 (not knife-edge).** `d_rho >= 2 x F_rho` OR the lane reports the result as
  MARGINAL. **Marginal is FAIL** (standing rule 12).

Bootstrap: 2000 draws, resampling PLAYERS (a player recurs across board-years, so the
cluster is the player, not the row), paired on the difference because both arms are scored
on identical rows. Seed 8641, matching `efv_tools._GATE_SEED`. Permutation null: 1000
draws.

**MULTIPLICITY (rule 9).** 5 tools x 2 arms = up to 10 gate cells, each with 2 primary
comparisons. Section 8 reports k of n and a Holm-adjusted read alongside the raw one. A
single tool clearing the gate out of five, with a Holm-adjusted p above 0.05, is reported
as NOT SHIPPING and labelled as such.

### 5.1 Stop clauses, binding

1. **No lag laundering.** If an arm has no evaluable board-year at `MIN_LAG_YEARS = 3`, it
   returns NULL. A shorter-lag sensitivity MAY be run and reported (the brief's own
   argument that the tool label horizon is short makes it worth reporting), but a
   shorter-lag result CANNOT satisfy G1-G5 and CANNOT produce a SHIP verdict. It is
   labelled SENSITIVITY everywhere it appears.
2. **No tool pooling to reach n.** Section 6.2's pooled run is a control, never a result.
3. **No dropping a tool that fails.** All five scoreable tools are reported.
4. **No served artifact is written.** Output is `data/ba_tool_grade_eval.json` only.
5. **This lane does not apply a weight.** Even a passing gate produces a recommendation,
   because the per-tool consensus feeds `tools_consensus`, and `consensus_fv_raw` is
   `_FEATURES_HIT[0]` / `_FEATURES_PIT[0]`. Changing an input to the dominant eFV feature
   is a separate, owned decision.

---

## 6. MANDATORY CONTROLS

### 6.1 PERMUTED-SOURCE-LABEL (the control whose absence produced the reverted FV weights)

Within each `(player, tool, board-year)` cell, randomly reassign which source each grade
is attributed to. The multiset of grades on that player is unchanged; only the source
labels move. Re-derive weights from scratch on the permuted data, re-run the full
forward-chained A/B, recompute `d_rho` and `d_auc`. 1000 permutations.

If the permuted null reproduces the observed `d`, there is no result. `F_rho` and `F_auc`
in G1/G2 ARE the p95 of `|d|` from this null. **This control is load-bearing, not
decorative: it is the gate's floor.**

### 6.2 POOLED-TOOL control (the anti-signal averaging demonstration)

Derive ONE weight per source from all five tools pooled, apply it to every tool, and score
it. Pre-registered claim to be tested: a source may read power well and hit badly, and
pooling averages a real signal against a real anti-signal and reports zero. Section 8
reports the per-tool `rho` spread per source and whether the pooled weight sits inside it.

### 6.3 SHUFFLED-OUTCOME null

Permute the realized quantity across players within board-year. Both arms should collapse
to `rho ~ 0` and `AUC ~ 0.5`. If they do not, the pipeline leaks and every other number in
the run is void.

### 6.4 FORCED-EQUAL identity check

Force all weights to 1.0 and confirm `d_rho == 0` and `d_auc == 0` exactly. Catches an
accidental asymmetry between the two arms' row construction.

### 6.5 SEED STABILITY

Re-run the bootstrap and permutation at seed 1337. A verdict that moves between seeds is
reported as unstable and treated as FAIL.

### 6.6 SURVIVORSHIP BOUNDARY (must be stated, not just handled)

Only players who reached MLB have a realized MLB quantity. Every number in this lane is
therefore **tool accuracy AMONG DEBUTS**, which is not tool accuracy overall. Section 8
reports, per arm and tool, the graded n, the with-outcome n, and the implied debut rate,
and states the boundary in the same sentence as the headline.

The brief asks that the pool be widened with AAA Savant coverage (2021+) where possible.
The lab CHECKS whether `statcast_metrics` actually carries pre-2026 seasons. If it does
not, the widening is reported as INFEASIBLE ON THIS DATABASE with the census that shows
it, and no widened number is invented.

---

## 7. BA-SPECIFIC ITEMS (descriptive; none of these gate anything)

**B1 Census.** Reproduce the tool-observation count by canonical key and report the delta
against the brief's 7,285 / 1,502.

**B2 Era scale break.** Reproduce, from the database:
same-player consecutive-board BA `fv` change for 2023->2024, 2024->2025, 2025->2026; and
BA minus contemporaneous FanGraphs `fv` for each of 2023-2026. The brief's numbers are
-0.64 / -0.83 / -11.89 and +6.57 / +6.80 / +6.38 / -4.98. BA introduced its Adjusted Grade
system for 2026, so 2026 `fv` is an Adjusted Grade and 2023-2025 `fv` is a BA Grade.

**B3 Does `grade_normalization` actually absorb the break?** It keys by
`(source, role, cycle-year)` and should fit a separate offset per year, so it SHOULD
absorb a level shift. `_MIN_N = 30`; a cell below that falls back to pooling the source
across years, **which would drag the 2026 Adjusted-Grade era into the 2023-2025 BA-Grade
era and re-open the break**. The lab reports, per (role, year), the FanGraphs-overlap n,
whether it clears `_MIN_N`, whether the cell was pooled, and the fitted offset against the
measured level shift. CONFIRM, do not assume.

**B4 BA Power: game or raw?** BA publishes ONE Power grade; FanGraphs splits raw and game;
the ingest maps BA Power to `game_pwr`. Two reads are reported:
(a) OUTCOME read: Spearman of BA Power against realized ISO, next to FanGraphs `game_pwr`
and FanGraphs `raw_pwr` on the same players;
(b) ALIGNMENT read: correlation and mean level of BA Power against FG `game_pwr` and FG
`raw_pwr` on the overlap.
If BA Power reads as raw power, that is a finding and is reported as one. Note in advance:
there is no realized MLB "raw power" quantity in `efv_tools._TOOLS` (max exit velocity
would be the natural one and `statcast_metrics` coverage is checked in 6.6), so read (a)
can only ever be indirect.

**B5 Does the sweeper/splitter fold cost anything?** `scrapers.JB_TOOL_KEY` folds sweeper
onto `sl` and splitter onto `ch`; BA ingest follows that precedent, and the untouched BA
labels survive in `tools._extras.ba_tools_raw`. The lab counts the folded observations and
compares folded against unfolded rows. Pre-registered: `sl` and `ch` are PASSTHROUGH tools
with no realized target, so this can only be a distributional comparison, and the folded
counts are expected to be small enough that the comparison is underpowered. Saying so is
the result.

**B6 League selection.** All 13 clubs are American League. The lab reports how many
players in the current cycle gain a BA vote, split by league, and the resulting change in
`n_sources` per player. Stated consequence: a player's number of voting sources depends on
his league, which makes the consensus's shrinkage-toward-the-mean depth league-dependent.

**B7 Selection hazard, reproduced.** Pool debut rate against BA-covered debut rate on the
shipped training matrices (brief: hitter 44.1% vs 74.8%, pitcher 48.1% vs 82.6%).

---

## RESULT (appended after the run)

Every number below reproduces from `data/ba_tool_grade_eval.json`, written by
`tools/ba_tool_grade_lab.py`. The run is deterministic: three consecutive full runs
produced byte-identical gate numbers.

**HEADLINE.** No self-added threshold determined any verdict: the pre-registered gate
(G1-G5) and the two self-added gates (G6, G7) agree on all five cells of the powered arm,
and the pre-registered gate is the binding one everywhere. One of ten gate cells ships:
`hit`, FanGraphs against MLB Pipeline, at 2.22x its permutation floor on Spearman and
2.14x on AUC, Holm-adjusted p 0.0050. Baseball America returns NULL BY CONSTRUCTION in
all five of its cells, as pre-registered in section 2.2. **And the control that most
embarrasses the ship: on four of the five tools, MLB Pipeline's grade ALONE beats both
the equal consensus and the weighted consensus. The weighting gain is a small fraction of
a gap that blending itself creates.**

### 8.1 B1 -- the corrected premise

Plan Lane K0's "Baseball America carries ZERO tool grades" is **FALSE**.

Measured: **7,410 tool observations across 1,535 rows** carrying `tools_json`, over 52
preseason org Top 30 boards (13 American League clubs x 4 vintages) plus one rank-only
Top 100 at `2026-06-03` that carries none.

| key | n | key | n |
|---|---|---|---|
| hit | 836 | fb | 696 |
| game_pwr | 836 | cmd | 695 |
| speed | 836 | ch | 647 |
| field | 836 | sl | 634 |
| throw | 835 | cb | 404 |
| | | ct | 155 |

The brief states 7,285 across 1,502 rows. **My count does not reproduce it** (+125
observations, +33 rows). It is not a filtering difference I could find: the delta survives
deduplication by (player, date) (7,400 / 1,527) and restriction to keys resolvable in
`players` (unchanged). The most likely explanation is that the brief's census predates the
final board of the ingest. **The premise correction does not depend on which number is
right**, and the count enters no gate.

**Only 3,899 of the 7,410 (52.6%) are on a scoreable tool.** `efv_tools._PASSTHROUGH`
records `raw_pwr`, `field`, `throw` and the individual pitch shapes as having no clean
realized MLB metric, so no per-source precision can exist for them. Half of BA's tool
content is outside this lane's reach by construction.

**Correction to my own section 2.1 prediction.** I predicted three multi-year tool
sources. There are four: `espn` publishes tool grades in 2025 and 2026 (205 observations
total, of which 5 rows in 2025 carry a realized outcome). `tjstats` (18,321 obs) and
`just_baseball` (622) are 2026-only. The practical conclusion is unchanged: only
`fangraphs` (2017-2026), `mlb_pipeline` (2011-2026) and `baseballamerica` (2023-2026)
have enough history to enter a common set, and ESPN's two years are one year of five
usable rows.

### 8.2 ARM A -- the powered arm. FanGraphs vs MLB Pipeline, per tool

Forward-chained at `MIN_LAG_YEARS = 3`. Evaluable board-years 2020-2025 for every tool
(2017-2019 skipped: no resolved base vintage, so weights are flat and the year cannot
differentiate the arms).

| tool | n | equal rho | wtd rho | d_rho | F_rho | x floor | d_auc | F_auc | x floor | boot lo95 rho | perm p_rho | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hit | 1260 | 0.2750 | 0.2884 | **+0.013416** | 0.006049 | **2.22** | **+0.006575** | 0.003078 | **2.14** | +0.007728 | 0.000999 | **SHIP** |
| game_pwr | 1256 | 0.3656 | 0.3695 | +0.003933 | 0.005136 | 0.77 | +0.002698 | 0.002697 | 1.00 | -0.000920 | 0.1359 | NO SHIP |
| speed | 1260 | 0.4249 | 0.4291 | +0.004258 | 0.003328 | 1.28 | +0.003521 | 0.001775 | 1.98 | +0.000501 | 0.0150 | MARGINAL -> FAIL |
| fb | 1180 | 0.2566 | 0.2498 | **-0.006744** | 0.005806 | -1.16 | -0.002765 | 0.003268 | -0.85 | -0.011016 | 0.0220 | NO SHIP (**resolved LOSS**) |
| cmd | 1185 | 0.2689 | 0.2730 | +0.004104 | 0.006618 | 0.62 | +0.002691 | 0.003404 | 0.79 | -0.001934 | 0.2368 | NO SHIP |

`hit` clears every gate: G1 2.22x, G2 2.14x, G3 lo95 +0.007728, G4 lo95 +0.003466,
G5 (2x floor) 2.22 >= 2.00. Its gain is positive in **all six** evaluable years
(+0.0128, +0.0102, +0.0055, +0.0109, +0.0208, +0.0126), and the derived weight is stable
after 2022 at roughly {FanGraphs 0.857, Pipeline 1.143}.

`speed` is the pre-registered marginal case and **FAILS on G5**, at 1.28x its floor
against the 2.00x knife-edge bar. Its permutation null is additionally flagged
DEGENERATE (median permuted weight spread 0.0184, below the 0.02 diagnostic line), so its
floor is the least trustworthy of the five. Both readings point the same way.

`fb` is the finding the brief predicted and it points the WRONG WAY: weighting the
fastball tool LOSES, by more than the floor, with a bootstrap interval that excludes zero
(lo95 -0.011016) on both metrics. This is a resolved loss, not a null.

**MULTIPLICITY (rule 9). 1 of 10 gate cells, 1 of 5 in the powered arm.** Holm-Bonferroni
across arm A's five tools on the primary metric:

| tool | perm p_rho | Holm-adjusted | survives 0.05 |
|---|---|---|---|
| hit | 0.000999 | **0.0050** | **yes** |
| speed | 0.014985 | 0.0599 | no |
| fb | 0.021978 | 0.0659 | no |
| game_pwr | 0.135864 | 0.2717 | no |
| cmd | 0.236763 | 0.2717 | no |

The permutation p is add-one corrected on 1000 draws, so 0.000999 is the floor of what
this null can report; `hit`'s observed d_rho of 0.013416 exceeds the largest of the 1000
permuted deltas (0.010387).

### 8.3 THE CONTROL THAT CUTS AGAINST THE SHIP (rule 10)

`context_single_source` scores each source ALONE on the same pooled scored rows:

| tool | FanGraphs alone | MLB Pipeline alone | EQUAL consensus | WEIGHTED consensus |
|---|---|---|---|---|
| hit | 0.2049 | **0.3215** | 0.2750 | 0.2884 |
| game_pwr | 0.3280 | **0.3738** | 0.3656 | 0.3695 |
| speed | 0.3905 | **0.4339** | 0.4249 | 0.4291 |
| fb | **0.2533** | 0.2257 | **0.2566** | 0.2498 |
| cmd | 0.2224 | **0.2842** | 0.2689 | 0.2730 |

On four of five tools the single best source beats BOTH consensus arms. For `hit`, the
shipped weighting recovers +0.0134 of a **+0.0465** gap to simply using Pipeline's grade.
The one tool where blending genuinely beats both singles is `fb` (equal 0.2566 above
FanGraphs 0.2533 and Pipeline 0.2257) -- and `fb` is exactly the tool where weighting
measurably HURTS. That is a coherent mechanism, not a coincidence: where one source
dominates, tilting toward it helps a little and blending is the wrong operation
altogether; where the sources are complementary, blending is right and tilting destroys
the complementarity.

**This does not invalidate the `hit` result, and it does bound what the result is worth.**
It is reported here because it is the strongest available argument against acting on it.

### 8.4 Controls

| control | result |
|---|---|
| **C6.1 permuted source label** (mandatory) | 1000 draws, all 1000 non-flat. Supplies F_rho / F_auc, the gate's floor. `hit` observed d_rho exceeds the permuted maximum. |
| **C6.1b null degeneracy** (self-added) | Median permuted weight spread 0.0184 (speed) to 0.0563 (fb) against real spreads of 0.030 to 0.321. NOT degenerate for four of five; `speed` flagged. |
| **C6.2 pooled-tool control** | Pooled weight {FanGraphs 0.9713, Pipeline 1.0287} on n=9,035. Per-tool rho spreads: FanGraphs 0.2178 (hit) to 0.4079 (speed); Pipeline 0.2036 (fb) to 0.4539 (speed). **The SIGN differs by tool**: on `fb` FanGraphs reads better (0.2251 vs 0.2036) while the pooled weight favours Pipeline, so a pooled weight would apply an ANTI-SIGNAL tilt to fb. The brief's mechanism, measured. |
| **C6.3 shuffled outcome** | Runs on all five tools (n 1180-1260). Equal rho collapses to -0.0299..+0.0374 and AUC to 0.488..0.529. Pipeline clean. |
| **C6.4 forced equal identity** | The naive form returns n=0 and passes VACUOUSLY, because `ab_pass` skips flat-weight years (inherited from `source_backtest`). The honest form (explicit all-ones override, flat-skip bypassed, n 1701-1878) returns d_rho and d_auc **exactly 0.0** on all five. |
| **C6.5 seed stability** | Seed 1337: `hit` lo95 0.007631 against 0.007728; every verdict unchanged. |
| **C6.6 survivorship** | Common-set graded rows 3,183-3,741 per tool, with-outcome 1,701-1,878, **implied debut rate 50.1% to 53.5%**. Every number in this lane is tool accuracy AMONG DEBUTS. |
| **C6.7 player-disjoint weights** (self-added) | Weight derivation restricted to players absent from the scored year. `hit` survives (d_rho +0.011754, lo95 +0.005925); `speed`, `fb` and `cmd` do not. |
| **C0 estimator equivalence** (self-added, forced by the environment) | The array path reproduces `source_backtest._spearman` / `_auc` to 0.0 absolute difference on all five cells, on both the row-level and A/B-level checks. |

**AAA Savant widening (section 6.6): INFEASIBLE ON THIS DATABASE.** `statcast_metrics`
holds 3,277 rows and **every one is season 2026** (A 518, A+ 219, AA 133, AAA 1,043,
CPX 409, MLB 955). There is no 2021+ history to widen into. No widened number is invented.

**Forward-chaining cost (the section 1.2 departure).** Restricting the realized aggregate
to seasons strictly after the board year removes 111 rows per hitter tool and 177-178 per
pitcher tool, about 5.6% to 9.4% of the pool `efv_tools`'s un-chained basis would have
used.

### 8.5 ARM B -- Baseball America. NULL BY CONSTRUCTION, exactly as pre-registered

All five BA cells return `NULL_NO_EVALUABLE_YEAR` with n = 0. The reason is arithmetic,
not evidential: BA's earliest vintage is 2023, `MIN_LAG_YEARS` is 3, so BA can first
contribute a weight at board-year 2026, and no player has an MLB season after 2026.
Common-set coverage with all three sources and a realized outcome exists (hit: 96 rows in
2023, 79 in 2024, 48 in 2025) but no year in which BA can also carry a derived weight.

**Lag SENSITIVITY (section 5.1: reported, CANNOT SHIP).** At lag 2 and lag 1 the BA arm
becomes evaluable and **all ten BA cells are null**: every bootstrap lo95 crosses zero,
every |d_rho| sits inside its permutation floor (largest ratio **0.81x**, at lag 2 on
`speed`; the other nine run 0.084x to 0.436x), and BA's
shrunk weight lands in **0.9267 to 1.1096** -- essentially equal, across every tool and
both lags. **This is the pre-registered expected honest result: Baseball America shrinks
to equal.**

The sensitivity also confirms `hit` is not a lag artifact (d_rho +0.0134 / +0.0141 /
+0.0132 at lag 3 / 2 / 1) and shows `cmd` is: it reaches p 0.0066 at lag 1 and p 0.0299 at
lag 2 but p 0.2368 at the primary lag 3. A result that only exists at a relaxed lag is not
a result, and section 5.1 forbids it shipping.

### 8.6 BA-specific items

**B2 era scale break -- REPRODUCED.** Same-player consecutive-board BA `fv` change:
2023->2024 n=194 mean **-0.6701** sd 4.4623; 2024->2025 n=198 mean **-0.8333** sd 4.5436;
2025->2026 n=196 mean **-11.8878** sd 5.6476. BA minus contemporaneous FanGraphs:
2023 n=302 **+6.5563**; 2024 n=310 **+6.8710**; 2025 n=324 **+6.4506**; 2026 n=251
**-4.9602**. Matches the brief to within rounding on the first three years. The 2026 n
(251 against the brief's 339) differs because this lab restricts FanGraphs to the
preseason window; the mean is unchanged at -4.96.

**B3 does `grade_normalization` absorb it? SEVEN OF EIGHT CELLS YES, ONE NO -- and the
one that fails is a defect, not a design limit.**

Seven of the eight (role, year) BA cells clear `_MIN_N = 30` on the FanGraphs overlap and
fit their own year: hitter 2023/2024/2025 (n 169/175/166, median shift -10.0 each),
pitcher 2024/2025 (n 134/159, -5.0 each), and both 2026 cells (n 171/168, **+5.0**). The
sign flip between the 2025 and 2026 cells is a 10 to 15 FV swing, which is the era break
being absorbed. Per-year keying works.

**The exception: `(baseballamerica, pitcher, 2023)` has ZERO overlap pairs, fails
`_MIN_N`, and falls back to POOLING BA ACROSS ALL YEARS** -- which drags the 2026
Adjusted-Grade era into the 2023-2025 BA-Grade era and re-opens inside that one cell the
~11.4 FV break the per-year keying exists to remove.

**B3b root cause (found while running B3; this is an INGEST DEFECT, reported to the
orchestrator).** The `2023-02-15` BA board carries `position = NULL` on **363 of 385
rows** and the non-token `'CP'` on the other 22 (Logan O'Hoppe, Edgar Quero, Yainer Diaz
-- all catchers). `grade_normalization._is_pitcher(None)` is False, so **all 385 rows land
in the hitter cell**. Two consequences:

1. the pitcher 2023 cell is empty, hence the cross-year pooling above;
2. **161 of the 385 rows are pitchers by their own `tools_json` signature** (they carry
   `fb`/`cb`/`sl`/`ch`/`cmd`, not `hit`/`game_pwr`/`speed`/`field`/`throw`), so the BA
   hitter 2023 quantile map is fitted on a role-MIXED distribution -- and BA grades
   pitchers lower than hitters (median raw 45 vs 50).

The other three vintages are clean: 2024 misroutes 1 row of 383, 2025 misroutes 4, 2026
misroutes 1. **The role is fully recoverable from `tools_json`.**

**B4 BA Power: game or raw? NO RESOLVABLE EVIDENCE THAT IT READS AS RAW.** On the 634-row
FanGraphs overlap, BA Power correlates 0.7706 with FG `raw_pwr` and 0.7426 with FG
`game_pwr` -- a difference of **+0.0280 with CI95 [-0.0019, +0.0588], which includes
zero** (2000-draw bootstrap, seed 8641). On level, BA Power's mean 50.16 sits **+2.15**
above FG game power (48.01) and **-3.76** below FG raw power (53.92), i.e. much nearer the
game-power scale. On the common-set outcome read against realized MLB ISO (n=228) BA Power
scores 0.3646 against FG `game_pwr` 0.3106 and FG `raw_pwr` 0.2560; the BA-minus-FG-game
difference is **+0.054 with CI95 [-0.0349, +0.1461], also including zero.**

**Conclusion: the `game_pwr` mapping is not contradicted, and I decline to call the raw
affinity a finding.** A bare inequality would have reported one here; the interval says
this test cannot tell. (Note also that no realized MLB raw-power quantity exists in
`efv_tools._TOOLS`, and B7 shows `statcast_metrics` has no pre-2026 seasons to build one
from, so the outcome read can only ever be indirect.)

**B5 sweeper/splitter fold: the ACCURACY question is unanswerable, but the fold is NOT
free and the cost is exactly countable.**

I pre-registered this as an underpowered distributional comparison and it is: folded
sweeper rows mean 52.19 sd 6.61 against plain slider 54.02 sd 6.02 (n=586); folded
splitter 50.47 sd 6.36 against plain changeup 48.29 sd 7.45 (n=604), at n=48 and n=43.
Both `sl` and `ch` are PASSTHROUGH tools with no realized MLB target, so **no accuracy
comparison is possible at all.**

**What the raw labels DO settle.** Reconciling `tools._extras.ba_tools_raw` against the
canonical counts closes every key exactly except the two folded ones:

| canonical | raw labels | canonical n | lost |
|---|---|---|---|
| hit | hit 759 + hitting 77 = 836 | 836 | 0 |
| speed | run 672 + speed 164 = 836 | 836 | 0 |
| field | field 672 + fielding 164 = 836 | 836 | 0 |
| throw | arm 834 + throw 1 = 835 | 835 | 0 |
| cmd | control 694 + comtrol 1 = 695 | 695 | 0 (the typo maps) |
| ct | cutter 152 + cut 3 = 155 | 155 | 0 |
| cb | curveball 402 + cb 2 = 404 | 404 | 0 (+ 1 `knuckleball` dropped, no key) |
| **sl** | slider 606 + sweeper 48 = 654 | **634** | **20** |
| **ch** | changeup 609 + ch 6 + split 38 + splitter 5 = 658 | **647** | **11** |

**The fold destroys 31 published observations.** 20 pitchers were graded on BOTH a slider
and a sweeper, and 11 on both a changeup and a splitter; each keeps ONE canonical grade
and the other is discarded at ingest. The kept grade averages 0.32 FV BELOW the mean of
the pair it replaced (n=31, sd 4.39), so the survivor is close to arbitrary rather than
systematically the better pitch. This is the fold's real cost: not bias, but the silent
loss of a second published opinion on 31 pitchers.

**B6 league selection.** All 52 boards are the same 13 American League clubs
(ATH BAL BOS CHW CLE DET HOU KCR LAA MIN NYY TBR TOR) in all four vintages. In the 2026
cycle, **383 of 1,660 players gain a BA vote**, and those players average **2.78 voting
sources against 1.45** for players without one. **A player's consensus is therefore
averaged over roughly twice as many opinions if he plays in the American League.** Since
the per-tool consensus is an unweighted mean, its sampling variance -- and so the depth of
its implicit shrinkage toward the crowd -- is league-dependent by construction. Nothing in
`consensus.py` corrects for this.

**B7 selection hazard -- REPRODUCED and slightly LARGER than the brief.** Hitter matrix:
pool 845/1,917 debuted = 44.08%, BA-covered 108/145 = **74.48%**, lift **+30.40 pts**.
Pitcher matrix: pool 981/2,040 = 48.09%, BA-covered 104/127 = **81.89%**, lift **+33.80
pts**. The brief's counts (104/139 and 100/121) are close; the direction and magnitude
stand. BA coverage tracks survival hard, and because `consensus_fv_raw` is
`_FEATURES_HIT[0]` / `_FEATURES_PIT[0]`, BA reaches the eFV model through the consensus
whether or not anyone adds a BA feature.

### 8.7 Environmental note, disclosed because it changed the code

Three separate full runs of the single-process lab died on this interpreter with Windows
access violations (`0xC0000005`) and, once, with a corrupted object surfacing as
`TypeError: 'int' object does not support item assignment` inside a numpy rank assignment.
Faulthandler tracebacks landed at `source_backtest.py:411` (a `sum()` generator inside
`_spearman`) and at the numpy rank write. The crash is stochastic and moves; free physical
memory at the time was 18.5 GB of 31.8 GB, so it is not memory pressure.

Two changes were made in response, **neither of which changes any estimator**:

1. the resampling loops were vectorized, with `C0` asserting the array path reproduces
   `source_backtest`'s own `_spearman` / `_auc` to 0.0 absolute difference before any
   bootstrap runs;
2. each gate cell and each sensitivity lag runs in its own subprocess, with up to six
   seeded retries. Every estimator is seeded, so a retry recomputes the same numbers.

Three consecutive end-to-end runs produced byte-identical gate numbers. This is recorded
so a verifier who reproduces the crash knows it is the environment, not the analysis.

### 8.8 SHIP RECOMMENDATION

**Do not change `consensus.py`. Equal weight retains on all eleven tool keys.**

- `hit` is the only cell that clears the gate, and section 8.3 shows the gain is 29% of
  the gap to simply using MLB Pipeline's hit grade. Shipping a 0.0134 Spearman tilt on one
  of eleven tool keys, into an input that feeds `consensus_fv_raw` and therefore the
  dominant eFV feature and the eFV baseline, is not worth the coupling.
- `fb` is a **resolved loss**. Any pooled or cross-tool weight would apply the wrong tilt
  there; C6.2 shows the pooled weight does exactly that.
- Baseball America shrinks to equal on every tool at every lag, which is the
  pre-registered successful outcome for this lane.

**Two things this lane found that are worth acting on and are NOT weighting:**

1. **The BA 2023 `position` defect (B3b).** 363 of 385 rows have no position, 161 of them
   are pitchers, all 385 route to the hitter normalization cell, and the resulting empty
   pitcher cell pools BA across the 2026 Adjusted-Grade era boundary. This is live in
   `grade_normalization` today and affects the served consensus, not just this lane.
2. **The AL-only coverage asymmetry (B6).** 383 players get a third voting source purely
   because of their league. Worth a disclosure line at minimum.
