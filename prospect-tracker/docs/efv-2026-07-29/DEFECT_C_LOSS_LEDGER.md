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

## What stays true regardless

The open P0 in `docs/EFV_GATE_STANDARD.md` (map fit on raw, applied to normalized) is real
and remains open. This ledger closes only the question of whether the proposed refit answers
it. It does not.
