# Phase D, the wRC+ program: what was measured, and the two calls that are yours

Measured 2026-07-31, then adversarially re-measured. Nothing in D1, D2 or D4 has shipped.
The one thing that DID ship out of this lane was a bug it uncovered, written up at the
bottom.

## D4: prospect FV to rate bridge. NO-SHIP, three independent measurements

Veterans ship `woba[]`/`wrc[]`/`fip[]`; prospects render a dash. Both proposed
constructions fail.

**(a) Invert `fa_projection.war_from_projection`.** Algebraically invertible, empirically
useless. Inverting back to wRC+ scores MAE **17.28** against the industry number, versus
**18.45** for just printing 100. Slope 0.541. And the error is ordered by GLOVE (Pete
Crow-Armstrong +76.4, Bobby Witt Jr +74.6, catchers +65/+61, 1B/DH -35 to -53) because the
map's 0.7576 wRAA coefficient parks defense, baserunning and position in the residual. It
also needs a PA denominator the prospect rows do not carry.

**(b) Fit p50 wRC+ by FV x age from resolved cohorts.** It fits, and it is flat: 1,467
player-seasons on 465 players, an honest pre-debut FV anchor gives R2 **0.0245** and MAE
**21.61** against **21.80** for the pool mean. Beating the pool mean by 0.19 runs of wRC+
is not a projection, it is a rounding error with a registry row.

A dash is more honest than either. Recorded as a loss ledger; do not re-run blind.

## D3: industry wRC+ column. GO, but not from the source the plan named

The plan said to surface the sqlite `sabermetrics` table. That table is **not an industry
feed**, it is a per-tracked-player cache, and it fails on four counts measured today:

- 1,120 rows, 525 hitters, **all season 2026** because the primary key carries no season.
- Covers **226 of 277** qualified board hitters (81.6%), and the 51 misses are Judge,
  Trout, Harper, Freeman, Machado and Schwarber. A column blank on exactly the players a
  reader opens the page for is not a column.
- 10 mlbam ids carry duplicate player_keys that DISAGREE (jackson_chourio 115.9 vs 109.9;
  the adversarial pass found 7 of 10 groups disagree, not 5, adding jeferson_quero and
  victor_mesa_jr).
- It carried the stint defect described at the bottom of this file.

**One bulk call replaces all of it:**

```
https://statsapi.mlb.com/api/v1/stats?stats=sabermetrics&group=hitting
    &season=2026&sportId=1&playerPool=All&limit=2000
```

Measured: 675 season-total rows, **609 of 609 board rows and 277 of 277 qualified at
100%**, plus 100% on all five history seasons, and it carries `numTeams` per player so
traded players are identifiable. One request instead of a per-player loop.

**Build D3 on the bulk call, not the table.** Two gate repairs are needed before it ships,
both found adversarially:

1. The proposed audit gate was a **20-player random sample** to catch stint values. Only
   29 of 609 board rows (4.8%) are multi-stint, and 4 of 277 qualified. Hypergeometric
   power of a random 20 is P=0.629 from all rows and **P=0.260** from the default qualified
   view. It misses its own defect three times in four. Audit the multi-stint set directly,
   which is small and enumerable.
2. The proposed byte-identical parity gate is unachievable as written, because
   `hitter_export` refetches live season data, so HEM+ and tier move between runs
   regardless of the change. It needs a same-fetch or stubbed comparison.

The `build_site.py` disclosure that "this site computes no wRC+" stays TRUE under this
design and should be sharpened rather than removed: we still compute none, we display the
published one. That distinction is the whole provenance story.

## D1 + D2: the MiLB chip swap. YOUR CALL, and it is not the call the plan describes

The plan framed D2 as a display-only rename of `ops_plus_level` to `wrc_plus_level`. It is
not. Three findings change the decision.

### 1. The dominant mover is the BASELINE, not the metric, and it carries no information

Decomposing the move on the 1,760-row common population:

| change | chips moving >5 pts | direction | mean |
|---|---|---|---|
| BASELINE convention only (same OPS metric) | 72 | 1,484 of 1,760 DOWN | -2.44 |
| OPS to wOBA only (same baseline) | 40 | 814 up / 586 down | +0.24 |

`level_norms.avg_ops` is an unweighted mean of TRACKED-PROSPECT rates over a two-season
window; `wrc_rates`' league wOBA is a PA-weighted single-season pool of the whole league.
The AA and A+ baselines run 7-8% low (AA .703 served against .752 true; A+ .708 against
.767).

**But the baseline change is a near-pure per-level recentering.** Measured: **zero** upward
moves out of 1,760, Spearman **0.9720**, and **0 of 13,218** discordant pairs. It moves
every number and reorders nothing. That is worth knowing before deciding it is the
important half.

### 2. The wOBA half depends on a cache with no producer in this repo

`.cache/milb_full_stats/` has exactly one code reader (`wrc_rates.py:54`) and **no writer
anywhere**. Its 2026 files are dated 2026-07-23, and **53.3% of 4,338 matched rows have
gained PA since**. Coverage from it is 1,760 of 1,972 (89.2%) against the 100% that
`ops_plus_level` ships today.

Shipping a headline chip off a frozen artifact nothing in the tree can regenerate is the
real risk in D2, and it is larger than the metric question. The baseline-only correction
does NOT need those components and reaches **97.9%** coverage with the CPX/DSL fallback.

### 3. D1 is not a safe enabler

Persisting PA lights up 12+ latent `pa or ab` fallbacks:

- `live_signal` sample_weight changes on **1,776 of 1,809** hitters (median +0.0386);
  live_signal is served on 2,050 players.
- **41 players flip** the `bayes_trade_value.py:196` gate (`if games < 45.0 and pa <
  175.0: return 1.0`), which controls a surplus multiplier. (The plan cited :195; that is
  the assignment, the gate is :196.)

So "persist the counting stats" is a served-number change wearing an enabler's clothes.

### What is safe, and what is not

- **eFV, rank and surplus do not read this field at all**: 0 hits across all 17 `efv_*.py`
  files and `value_framework.py`. Verified, not assumed.
- The `storage.py:587` breakout gate `_BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE = 150` is **dead**:
  0 of 1,972 served rows reach 150 today (max 127), and 0 reach it under any candidate.
- Switching the K=170 shrink denominator from AB to PA is **not material**: 843 of 1,808
  rows move >=1 point, exactly **one** moves more than 5.
- Named players, so nothing is promised undirected: **Bradfield 93 -> 94** (wOBA ratio) or
  **89** (runs-scaled) or **92** (OPS held, true baseline). **Taylor 118 -> 110 / 118 /
  113**.

### The three options

| | what it does | coverage | ordering | risk |
|---|---|---|---|---|
| **A. Baseline only** | fix `level_norms` to a PA-weighted league pool, keep OPS | 97.9% | unchanged (0 discordant pairs) | low; no dependency on the orphan cache |
| **B. Full wOBA swap** | A plus OPS to wOBA | 89.2% | small reorder | HIGH: depends on a cache with no producer |
| **C. Nothing** | keep the chip as is | 100% | unchanged | the AA/A+ baselines stay 7-8% low |

My reading, offered as a recommendation and not taken: **A**, and D1 stays unshipped until
its 41-player surplus flip is a deliberate decision rather than a side effect. B should
wait for a producer for `.cache/milb_full_stats/`, because a headline chip that no longer
regenerates is a worse defect than a slightly wrong baseline.

## What DID ship out of this lane

Scoping D3 uncovered a live served bug: `stats.fetch_sabermetrics` read `splits[-1]` on a
season-scoped request, so every TRADED player stored one stint as his season.
`prospx` renders that wRC+ as a headline chip, and 160 of 511 stored hitters (31.3%) were
off by more than 0.5. Fixed, tested, and the 50 affected stored rows repaired via
`tools/repair_sabermetrics_stint_rows.py`. The deploy box needs the same `--apply` run.
