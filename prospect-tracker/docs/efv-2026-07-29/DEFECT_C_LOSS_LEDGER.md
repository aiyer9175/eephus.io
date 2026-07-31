# Defect C loss ledger: the surplus map refit is a NO-SHIP

Registered under `docs/EFV_GATE_STANDARD.md`. Companion to
`docs/efv-2026-07-29/CALIBRATION_FINDINGS.md`.

## What was proposed

Refit the surplus calibration map on the normalized FV scale, to close the open P0 in the
gate standard (the map is fit on a raw per-source median FV while production prices a
normalized consensus) and to repair the degenerate bottom block, where 6,384 of 9,318
served rows (68.5%) price at exactly $0.

## Verdict: REFUTED. Do not ship.

The refit coefficient is **unidentified from its own fit pool**, and the direction of the
error is the opposite of what Defect C needs.

- 75.5% of the fit rows have no MiLB level record and take the eta-3.5 fallback, which
  carries `a = +1.810`.
- The 24.5% that DO have a real record carry `a = -0.074`, CI95 [-0.180, +0.032].
- Gap `+1.884`, CI95 [+1.630, +2.176], p = 0.000. It survives FV-matching and ETA-forcing,
  so it is not a confound of grade or timing; the two strata are simply different objects.
- `run_live` serves **only** the has-record stratum. On that stratum the candidate raises
  held-out bias from -$2.77M to -$5.66M, i.e. it over-prices, in the same direction Defect
  C exists to correct.

A coefficient fit predominantly on rows production never scores, then applied to rows it
does, is not a calibration. Shipping it would have made the served bottom of the board
worse while reporting a better pooled number.

## What is deliberately left red

`test_value_framework::test_calibration_layer_is_real_fit_and_monotone` and three sibling
guards stay FAILING, on purpose:

- `test_value_framework::test_calibration_layer_is_real_fit_and_monotone`
- `test_value_framework::test_calibration_layer_applies_to_public_api`
- `test_value_framework::test_disabling_timing_reproduces_flat_behavior`
- `test_backtest::test_calibration_config_never_ships_synthetic`

Two distinct things make them red, and both should stay red until the map is genuinely
repaired:

1. `ys[0] > 0` is violated by the shipped knots `[0.0, 0.0, 25.33, 80.63, 550.68]`. The
   guard's own comment reads "the v1 per-player fit zeroed every FV35-40 prospect, never
   again". It is correctly detecting a live degeneracy. **It is a standing tripwire, not
   a stale assertion.**
2. The version string `linearmap-v5-todaypriced-2026-07-24` matches neither sanctioned
   prefix (`isotonic-real-`, `linear-real-`).

**The version string was NOT renamed.** Renaming it would turn two guards green while the
degeneracy they exist to catch is still live, which is exactly the papering-over that
`CALIBRATION_FINDINGS.md` pre-committed against. Cheap greens on a pricing layer are how a
defect like this survives five days in production in the first place.

## The successor candidate: C-prime. Recommended, NOT gated, needs an owner decision

Verification found the actual mechanism, which is better targeted than a refit.

`value_framework.expected_surplus_usd` does not return a pipeline prediction at the bottom
of the board at all. For `fv <= lowtier_anchor.cutover_fv` (40) it returns a FIXED published
dollar anchor, `2.0e6 * exp(-0.16 * (40 - fv))` with a 0.90 pitcher factor. The engine's own
CI code describes it in terms: "Pure Edwards anchor, a fixed dollar figure with NO parameter
uncertainty", and it returns a degenerate interval there. For `fv` in (40, 45) it is a linear
bridge from that anchor to the pipeline evaluated at `bridge_to`.

The v5 calibration was fit on pipeline predictions and is applied to that anchor anyway,
which it has no fitted support for. Measured consequences:

- An FV40 position player: declared anchor $2.0M, served **$0.4M**
  (`1.382491 * 2.0 - 2.318551 = 0.446`).
- Every anchor row below the $1.677M zero-cross goes to exactly $0. **That single branch
  owns 6,038 of the 6,384 zero rows.**
- The one test that would have caught this runs with the calibration disabled.

**C-prime**: ramp the calibration weight linearly from 0 at `cutover_fv` to 1 at
`bridge_to_fv`, so the correction is not applied where it has no support and the served
ladder stays continuous. It is a single localized edit in `apply_calibration`, which already
accepts `fv` and `is_pitcher` and currently ignores both.

Measured over the 9,318 served quantile grades (timing-naive re-price):

| variant | board total | rows at $0 | monotone |
|---|---|---|---|
| shipped | $33,981.6M | 6,006 | yes |
| exempt at cutover only | $41,151.8M | 0 | **NO** (40 -> $2.00, 40.5 -> $1.44) |
| exempt through bridge | $42,707.0M | 0 | yes |
| **ramp (recommended)** | **$42,423.5M** | **0** | **yes** |

This is an owner decision because it moves total board surplus by about +24.8%. It is not
shipped here. What it would do is make the site serve the $2.0M an FV40 position player has
been declared to be worth all along, instead of $0.4M.

## C-prime was gated on 2026-07-29 and is ALSO a NO-SHIP

C-prime is the candidate this ledger recommended. It was specified, patched, and gated. It
fails, and the recommendation above is withdrawn. Three of six gates fail and, worse, **the
premise of this ledger is wrong**.

**The premise was false.** This ledger argued the v5 map "has no fitted support" below the
bridge. Measured: **77.2% of the v5 fit pool (normalized scale), 47.0% (raw), sits BELOW
bridge_to.** The correction does have fitted support there. The whole "applied where it was
never fit" framing collapses, and with it the reason to exempt the region.

**Held-out accuracy gets WORSE, decisively.** Pooled n=2,236: MAE 9.808 -> 10.514, bootstrap
dMAE +0.705 CI95 [+0.670, +0.741], P(better) = 0.000, **0 of 6 time folds better**, and the
candidate is **worse than its own permutation null band** [10.193, 10.298]. Bias does improve
(2.017 -> 1.114) but a naive 17.3% uniform uplift reproduces that at LOWER MAE cost, and the
bias improvement **flips sign on the raw FV scale** (|bias| 1.646 -> 2.113). In the gate
standard's own currency the cost is about -0.100 pooled eFV Spearman, 2.2x the MDE95.

**Monotonicity fails, and it exposed a separate live defect.** 5 of 35 role-by-timing curves
are non-monotone under the candidate, all reliever tags. Root cause is NOT the candidate: the
Edwards bridge is **inverted for RP/SIRP/MIRP at every timing** (anchor at cutover $1.8000M
against pipeline at bridge_to $1.6680M, and 1.5722/1.5621, 1.8000/1.7884, 1.3732/1.3644), so
the bridge interpolates downhill and price falls as grade rises. **The v5 zero floor is the
only thing hiding it.** Independently reproduced: 4 of 20 role-by-position curves are
non-monotone at HEAD, pre-existing, with the first violation between exactly FV40 and FV40.5.

**Ladder sanity fails.** 402 served rows would price above their same-side, same-position
FV45, worst excess $1.8M (an FV40 MIRP at $1.8M against an FV45 MIRP at $0.0M). The shipped
baseline is 85 rows at $0.2M. Position-naive, this check returns zero violations, which is why
it was missed.

Passing gates, for the record: continuity at both knots, the FV40 anchor serving its declared
$2.0M/$1.8M, and the exactly-$0 share going to zero.

### Two corrections to this ledger's own numbers

- The anchor branch owns **6,336 of 6,384 zero rows (99.2%)**, not 6,038. The bridge owns 48
  and the pipeline owns 0. The substance is stronger than originally stated, not weaker.
- The tier table above is captioned as displayed grade but only reproduces when binned on
  `xfv_grade`, the realized grade, NOT the `xfv_grade_quantile` that actually prices.

### What remains open

The bottom of the board still prices at $0 for 68.5% of rows, and that is still wrong. What is
now established is that exempting the anchor regime from the calibration is not the fix: it
buys a better bias at a clearly worse MAE, on a premise that does not hold. Two narrower and
genuinely promising leads came out of the gate:

1. **The reliever bridge inversion** is a real, live, pre-existing monotonicity defect with a
   small blast radius. It needs its own gate because any fix moves reliever dollars below FV45.
   Registered in `docs/efv-2026-07-29/GATED_CANDIDATES.md`.
2. **`test_value_framework::test_expected_sv_monotonic_in_fv` is position-blind**, which is why
   a four-curve monotonicity defect has been shipping undetected. Parametrizing it by position
   is free and catches this class permanently.

## The dollar-basis unification is a DO-NOT-FLIP

Also gated 2026-07-29, also refuted, and this one refutes a claim I made myself.

I argued that "as close to model as possible" favours pricing off the raw model grade rather
than the quantile remap. That reasoning is wrong, for a reason that is obvious in hindsight:
**the anchor curve and the surplus map are functions whose DOMAIN is consensus-scale FV.**
`empirical_anchors.py:55-59` builds its cohort from published per-source scout FV in
`snapshots`, blended toward the Edwards public ladder; `tools/fit_surplus_calibration.py:50`
fits on the grade-normalized per-source median; `lowtier_anchor.anchor_usd_40fv_position:
2.0e+6` is a published dollar figure attached to a scouting FV 40. Feeding raw grades to those
functions is a category error, not a purity gain.

The empirics agree. The quantile grade's marginal distribution IS the consensus marginal (hit
mean 36.79 against 36.79, sd 3.61 against 3.59); the raw grade's is not (mean 25.07, sd 10.25,
median 20.0). And on the forward-chained OOS frame, in the band where dollars actually exist
(either grade >= 45, n=353), the raw basis is **worse in level**: bias -1.338 CI95 [-1.930,
-0.737] and slope 0.707, against the quantile's +0.759 CI95 [+0.161, +1.405] and slope 1.199,
with paired dMAE +0.539 CI95 [+0.233, +0.843] and 5 of 5 folds favouring the quantile. Raw
per-tier bias grows monotonically with grade (-1.902 at 55, -5.647 at 65, -7.794 at 70), which
is Defect A's over-dispersion expressed in grade units. The raw basis wins only where both
grades sit under 45, and every row there prices at $0 anyway.

`proj_export.py:421-427` already records that this exact flip "inflated the projected prospect
pool ~+60% vs consensus" and was reverted. Independent re-measurement here: +60.4%. It has been
tried once and it did not work.

**A trap for the next attempt, worth more than the verdict:** `efv_score.run()` fits both the
ridge and the linear output calibration on the rows it scores, so measured on
`data/xfv_scored*.json` the raw grade's bias is near zero BY CONSTRUCTION (-0.038 CI95
[-0.150, +0.076]) and paired dMAE reads -0.052 in raw's favour. That reverses out of sample.
Any future basis comparison must be run on a forward-chained frame, never on the scored
artifact.

## What stays true regardless

The open P0 in `docs/EFV_GATE_STANDARD.md` (map fit on raw, applied to normalized) is real
and remains open. This ledger closes only the question of whether the proposed refit answers
it. It does not.
