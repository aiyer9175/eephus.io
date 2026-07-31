# Baseline scoreboard - 2026-07-29 (Phase 0)

Program: eFV / consensusFV / surplus + Arkmetric fix, upgrade and completion.
Baseline commits: `ec6431b` (baseline A, staged projection/FA workstream) and
`017d3bc` (baseline B, full 07-23..07-25 worktree) on top of `71ea151` (2026-07-19).

Suite run: `python -m pytest -q` from `prospect-tracker/`, tree quiescent, no data re-ingest
(the last `run_monthly` was 2026-07-28, inputs frozen for the program).

**Result: 42 failed, 2306 passed, 21 skipped (155s).**

The suite left ZERO tree churn (`git status --porcelain` empty afterwards), confirming the
conftest restore behaved and the baseline commits are the recovery point.

## Why this matters

The pre-program audit predicted three red clusters (sign declarations, orphan eval artifacts,
golden fingerprint). The real count is 42 across nine clusters, and several are genuine defects
that no prior program catalogued. The tree is less coherent than the audit implied. Every number
below is the program's starting scoreboard: any red not on this list at the end is program-induced,
and every red on this list must be either fixed or explicitly ledgered as accepted.

## Cluster 1 - surplus calibration incoherence (22 tests) - P0, REAL

The single largest cluster, and it is a live incoherence rather than a naming nit.

Two independent defects share this cluster:

**1a. Version-string convention violation (4 tests).** The shipped calibration version is
`linearmap-v5-todaypriced-2026-07-24`. Two guards require the prefix `isotonic-real-`
(`test_value_framework.py:62`) or one of `("isotonic-real-", "linear-real-")`
(`test_backtest.py:231`). These guards exist to prevent shipping a SYNTHETIC calibration. The v5
map IS a real fit, so this is a naming violation introduced by the 07-24 B1 ship and never
reconciled, not a synthetic-calibration leak. Fix direction: rename the version to the sanctioned
`linear-real-*` form (it is a real linear fit) rather than widening the guard, so the guard keeps
its meaning.
- `test_value_framework.py::test_calibration_layer_is_real_fit_and_monotone`
- `test_value_framework.py::test_calibration_layer_applies_to_public_api`
- `test_value_framework.py::test_disabling_timing_reproduces_flat_behavior`
- `test_backtest.py::test_calibration_config_never_ships_synthetic`

**1b. The frozen production table is STALE versus the engine (18 tests).** This is the serious one.
`config/valuation_sets/prospx_current.yaml` was re-frozen on 07-24 under v5 (captured 28.2 at FV50).
The engine now produces 32.8 at the same tier:
- `test_valuation_sets.py:78` - `50 hit: table 28.2 != engine 32.8` (16 parametrized tier cases
  fail across both table modes: 42.5, 45.0, 47.5, 50.0, 55, 60, 65, 70)
- `test_valuation_sets.py::test_clemens_default_applies_and_context_restores`
- `test_clemens_reconciliation.py::test_surplus_50_hitter_stays_model_scale_not_table` -
  `surplus_value_mm(50, False)` returns 29.6, expected 18.5 +- 0.6
- `test_clemens_reconciliation.py::test_cache_cleared_on_set_switch`

Something moved surplus pricing AFTER the v5 re-freeze without the mandated coordinated re-anchor.
The platform is currently serving surplus dollars that disagree with its own frozen production
table by roughly 16 percent at FV50. This elevates the Phase 5 surplus work from "finish a deferred
refactor" to "repair a live pricing incoherence", and it means the killed `dpw-reconcile-surplus-recal`
workflow was interrupted in the middle of exactly the reconciliation that would have caught this.

## Cluster 2 - eFV sign declarations (6 tests) - known, Phase 2

`docs/SIGN_AUDIT_PATCHES.md` registered four patches on 07-25 that were never applied.
- `test_efv_sign_declarations.py::test_flagship_fitted_signs_match_declarations[hit|pit]`
- `test_efv_sign_declarations.py::test_provisional_fitted_signs_match_declarations[hit|pit]`
- `test_efv_sign_declarations.py::test_provisional_features_are_declared[hit|pit]`

## Cluster 3 - board scale and export contract (4 tests) - Phase 2 / Phase 4

**Empirically confirmed: `xfv_grade_model_raw` is present on 0 of 9,318 rows in the served
`data/xfv.json`.** The 07-28 `run_monthly` regenerated the artifact without the board-scale stamp,
because `efv_board_scale.stamp_file` is not wired into `efv_export`. This is the predicted
unwired-stamp failure mode, now observed rather than inferred.
- `test_efv_export.py:96` - `dustin_harris: no xfv_grade_model_raw (scale anchor missing)`
- `test_efv_export.py::test_xfv_golden_fingerprint` - artifact hash moved (expected; needs a
  documented restamp at the end of each coordinated window)
- `test_efv_board_scale.py::test_disabled_is_exactly_the_identity`
- `test_efv_board_scale.py::test_coefficients_reproduce_from_the_labeled_artifacts`

## Cluster 4 - registry integrity (1 test) - known, Phase 2

`test_model_registry.py:78` names nine eval artifacts with no registry row, matching the audit
exactly: `_am_crossmodel_agelevel`, `xfv_generality{,2,3,4}`, `xfv_level_calibration`,
`xfv_odds_dispersion`, `xfv_pred_dispersion`, `xfv_thin_pbust`.

## Cluster 5 - identity collision (2 tests) - NEW, not in any prior audit

`carlos_castillo` is a merged identity covering two different humans, and it is ON THE ACTIVE BOARD.
This is the Jose Valdez bug class recurring with a new player.
- `test_identity_collisions.py:355` / `:365`
The test states the required remedy: split the NEWCOMER onto a discriminated key, never re-key the
incumbent. `data/identity_collisions.json` carries the mlbam ids. Needs a repair script in the
sanctioned dry-run/`--apply` pattern.

## Cluster 6 - team outlook calibration (2 tests) - NEW

- `test_team_outlook_calibration.py:50` - `worst team projects 53.6` wins (implausible)
- `test_team_outlook_calibration.py:55` - recenter remainder is 3.49 wins/team, but the level is
  supposed to come from the model (champion means + depth pool + cohort intercepts), not the
  recenter. Multi-year drift is far worse: 12.43 (2028), 25.03 (2029), 27.1 (2030), 28.1 (2031).
Likely provoked by the proj_lgbm retrain and mean-blend captured in baseline A. Needs triage
before it is assumed pre-existing.

## Cluster 7 - FA surfaces (2 tests) - NEW

- `test_fa_fit.py:129` - `assert 29 == 30`: team baselines do not agree with the projections
  outlook for one team (a missing or mis-keyed club).
- `test_fa_edges.py::test_team_fits_components_bounded_and_finite`

## Cluster 8 - trade value anchor (1 test) - NEW

- `test_bayes_trade_value_policy.py::test_mlb_hitter_500_pa_projection_anchor_grounds_middling_bat`
Plausibly downstream of Cluster 1b (trade values price off the shared surplus scale), so re-check
after the Phase 5 reconciliation before treating it as independent.

## Cluster 9 - glossary provenance (1 test) - Phase 3 Lane C

- `test_glossary_provenance.py:35` - `collegesavant_stuff_plus` does not name the platform in its
  arkmetric origin. Consistent with the audit's finding that three-plus incompatible Stuff+ scales
  are documented loosely.

## Independent confirmation of the unrecorded 07-25 finding

`data/xfv.json` currently carries **3,821 of 9,318 rows with a negative projected 6-year WAR**.
The 07-25 session reported 3,776 of 9,287; the 07-28 regen moved both counts slightly. The finding
is real, live, and still unrecorded anywhere in the repo before this document. It is direct
evidence that the FV-to-WAR anchor layer is mis-calibrated at the bottom of the scale, which is why
the anchors refit is treated as in scope for the Phase 5 surplus window.

## Standing interpretation rule for this program

A red on this list is a starting condition, not a regression. A red NOT on this list is a
regression and blocks its phase. Every fix must cite the cluster it closes.
