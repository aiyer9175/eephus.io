# `signs` lane -- exact patches for the lead to apply

Lane: SYSTEMATIC DECLARED-VS-FITTED SIGN AUDIT (2026-07-25).
Evidence: `data/xfv_sign_audit.json`, `data/xfv_sign_merge_gate.json`,
labs `tools/_sweep_signs.py`, `tools/_sweep_signs_merge.py`,
verification `tools/_sweep_signs_verify_patch.py`.

**No patch below changes a single served number.** The declared monotone directions are
consumed ONLY by `efv_model._fit_lgbm_mono` (`monotone_constraints`), which feeds the
LightGBM challenger inside `_run_eval` / `_importances` -- eval-artifact rows, never a
served prediction. The shipped ridge (`fit_production_stack` -> `prospect_path._fit_ridge`)
ignores the declaration entirely. Verified by inspection of every `_feature_spec` caller:
`efv_score` (x2), `efv_proxy` (x2), `efv_reliability`, `efv_model` all discard `mono`.

Patches 3 and 4 are DISPLAY-ONLY label changes (chip copy). They move no ordering.

Applying patches 1 + 2 + 3 makes `test_efv_sign_declarations.py` pass; verified by
`python tools/_sweep_signs_verify_patch.py` -> `PATCH CLEAN: True`.

---

## PATCH 1 -- `efv_model.py`: stop declaring directions the served fit contradicts

`0` means "no directional claim" and is a legal LightGBM constraint. It is the correct
declaration for a measured suppressor: it stops the module asserting the opposite of what
it fits, without pretending the reverse claim is theory.

### 1a. line 63

```python
    ("k_rel",          -1),   # contact: more whiffs worse (under-priced by scouts)
```
->
```python
    # k_rel declared 0 = NO DIRECTIONAL CLAIM (sign audit 2026-07-25, owner bug
    # "why is Arias punished for contact when he has great contact?"). The theory
    # (-1, more whiffs worse) is true MARGINALLY: weighted corr with realized WAR
    # -0.0884. It is FALSE conditionally: the served ridge fits +0.1874, unregularized
    # OLS +0.2446, and the sign survives every conditioning tried - +0.0996 with
    # peak_k_rel removed, +0.2508 refit on production-bearing rows only, positive in
    # 8 of the 9 informative forward-chained folds. It is a genuine SUPPRESSOR
    # (conditional on FV + tools + the on-base/OPS block, residual contact reads as
    # a slap-hitter tell), not a collinear split: MERGING k_rel with peak_k_rel into
    # one z-mean column still fits POSITIVE (+0.0595, 9/11 folds).
    # Dropping it is a measured NULL: pooled forward-chained rho +0.00715 (0.42x the
    # 0.017 MDE95), paired-bootstrap CI95 [-0.0051, +0.0179], and the row-permuted
    # zero-information control scores +0.00718 - identical to the candidate, i.e. no
    # result. So it STAYS; only the declaration was wrong.
    # Ledger: data/xfv_sign_audit.json, data/xfv_sign_merge_gate.json.
    ("k_rel",           0),
```

### 1b. line 66

```python
    ("n_milb_seasons", +1),   # MiLB seasons before the read -- track record/persistence (OOS +.010)
```
->
```python
    # n_milb_seasons declared 0 (sign audit 2026-07-25). "Track record/persistence"
    # (+1) is true MARGINALLY (+0.0946) and FALSE conditionally: served ridge
    # -0.2324, unregularized OLS -0.5051, -0.2368 with milb_missing removed, -0.3231
    # on production-bearing rows only, negative in 7 of the 9 informative folds. The
    # conditional meaning is inverted by construction - holding level_rank and age
    # fixed, more MiLB seasons means MORE seasons used to reach the same level.
    # SUPPRESSOR, keep: dropping is a NULL (+0.00426 = 0.25x the 0.017 floor, CI95
    # [-0.0097, +0.0182], zero-information control +0.00386 = the same number).
    # NOTE the display consequence, fixed in patch 4: this weight put a
    # "Track-record depth DOWN" chip on 1,882 of the 1,886 live hitter cards that
    # show it (99.8%), mean magnitude 0.362.
    ("n_milb_seasons",  0),
```

### 1c. line 74

```python
    ("milb_missing",   -1),
```
->
```python
    ("milb_missing",    0),   # declared 0 (sign audit 2026-07-25): served fit is
                              # +0.0397 against a declared -1. Marginal -0.0302 agrees
                              # with the old declaration, so this is a suppressor by the
                              # letter, but the weight is at the noise scale and the
                              # feature is INERT in the served fit - dropping it moves
                              # pooled forward-chained rho by -0.00022 (0.013x the 0.017
                              # floor), the smallest effect measured anywhere in the set.
                              # Kept (gate standard section 6: do not remove on sub-floor
                              # evidence); the claim is what goes.
```

### 1d. line 125 (the PITCHER `age` entry, NOT the hitter one on line 96)

```python
    ("age",            -1),
```
->
```python
    # age declared 0 for PITCHERS (sign audit 2026-07-25, owner bug "Ryan Sloan, 20 in
    # Double-A, is PENALIZED for age"). Adjudicated under the full EFV_GATE_STANDARD:
    #   fitted sign   served ridge +0.0589 against a declared -1. Marginal -0.0543, so
    #                 the theory is true unconditionally and false conditional on FV +
    #                 K/BB + tool_fb (the consensus anchor already prices young arms).
    #   stability     NOT a stable wrong sign and NOT chatter - a monotone DRIFT with
    #                 sample size: fold weights -0.060 / -0.059 / -0.759 / -0.452 /
    #                 -0.182 / -0.082 / -0.061 / +0.047 / +0.050 across train<2016..2024
    #                 (the 2014/2015 folds are degenerate - pre-StatsAPI rows make every
    #                 production column constant - and are excluded, not counted as
    #                 disagreement). The two LARGEST folds (n=1473, n=1730) and the full
    #                 pool all fit it non-negative. "Negative in 9 of 11 folds" is a
    #                 small-and-old-data artifact.
    #   drop gate     pooled forward-chained rho over 11 splits: +0.00377 for dropping =
    #                 0.236x the 0.016 pit MDE95. Paired bootstrap (B=2000, resampling
    #                 TRAIN and TEST with a refit per draw) CI95 [-0.0089, +0.0175],
    #                 P(drop helps) 0.68. Zero-information control (the same column
    #                 row-permuted, kept in the set) +0.00252 - two thirds of the
    #                 "gain" is reproduced by destroying the column's information
    #                 without removing it. Permutation null p 0.382. Dropping is a NULL,
    #                 helps in only 4 of 11 folds, and gate standard section 6 forbids
    #                 removing on sub-floor evidence -> KEEP.
    #   merge gate    merging age with age_rel_level into one z-mean column does NOT
    #                 restore the declared direction (merged weight +0.0471, positive in
    #                 3 of 11 folds) and is itself a null (-0.00588 = 0.37x floor,
    #                 CI95 [-0.0231, +0.0167]) -> rejected as a remedy.
    # This is a CORRECTNESS fix, not an accuracy claim: no rank gain is claimed and none
    # is required. The hitter-side ("age", -1) on line 96 is untouched and correct
    # (served -0.0619, negative in all 9 informative folds).
    # Ledger: data/xfv_sign_audit.json, data/xfv_sign_merge_gate.json.
    ("age",             0),
```

---

## PATCH 2 -- `test_efv_model.py`: the pinned expectations must move with patch 1

### 2a. `_EXPECTED_HIT` (lines 129-135)

```python
_EXPECTED_HIT = [
    ("fv", +1), ("obp_rel", +1), ("k_rel", -1), ("peak_k_rel", -1),
    ("age_rel_level", -1), ("n_milb_seasons", +1), ("tool_hit", +1),
    ("tool_speed", +1), ("milb_missing", -1), ("is_ifa", 0), ("is_college", 0),
```
->
```python
_EXPECTED_HIT = [
    # k_rel / n_milb_seasons / milb_missing declared 0 = "no directional claim"
    # (sign audit 2026-07-25): all three fitted AGAINST their old declaration in the
    # served production fit. See efv_sign_audit.py + test_efv_sign_declarations.py.
    ("fv", +1), ("obp_rel", +1), ("k_rel", 0), ("peak_k_rel", -1),
    ("age_rel_level", -1), ("n_milb_seasons", 0), ("tool_hit", +1),
    ("tool_speed", +1), ("milb_missing", 0), ("is_ifa", 0), ("is_college", 0),
```

### 2b. `_EXPECTED_PIT` (lines 145-150)

```python
_EXPECTED_PIT = [
    ("fv", +1), ("peak_k_rel", +1), ("k_rel", +1), ("bb_rel", -1),
    ("age_rel_level", -1), ("x_era_k", +1), ("tool_fb", +1),
    # age: same owner-directed 2026-07-14 ship as the hitter side.
    ("age", -1),
]
```
->
```python
_EXPECTED_PIT = [
    ("fv", +1), ("peak_k_rel", +1), ("k_rel", +1), ("bb_rel", -1),
    ("age_rel_level", -1), ("x_era_k", +1), ("tool_fb", +1),
    # age: shipped 2026-07-14 owner-directed, declaration corrected to 0 on
    # 2026-07-25 (served ridge fits +0.0589 against the old -1; dropping it is a
    # measured NULL at 0.24x the pit MDE95). The feature stays; the claim goes.
    ("age", 0),
]
```

---

## PATCH 3 -- `efv_ungraded.py`: declare the provisional set's directions

The no-FV sets are BARE KEY LISTS, so three keys (`peak_obp_rel`, `iso_rel`, `era_rel`)
reach a served grade with no stated direction anywhere, and `n_milb_seasons` inherits the
flagship `+1` while fitting **-1.0063** (hitters) / **-0.1643** (pitchers). The hitter
value is the third-largest weight in that model and its marginal is -0.0075, so unlike
the flagship case this one is not even a suppressor -- the declaration was never true.

After line 73 (`_NOFV_PIT = [...]`), insert:

```python
# Declared monotone direction per provisional key (sign audit 2026-07-25). These sets
# used to be bare key lists, so nothing stated what any of them was supposed to do and
# the audit had to inherit the flagship declaration - which is how peak_obp_rel /
# iso_rel / era_rel shipped with no stated intent at all and n_milb_seasons shipped
# claiming +1 while fitting -1.0063. 0 = NO DIRECTIONAL CLAIM. Pinned by
# test_efv_sign_declarations.py; audit function in efv_sign_audit.audit_provisional.
_NOFV_MONO = {
    "obp_rel": +1, "peak_obp_rel": +1, "ops_rel": +1, "iso_rel": +1,
    "bb_rel": -1, "era_rel": -1, "x_era_k": +1,
    "age_rel_level": -1, "level_rank": +1,
    # n_milb_seasons: fitted -1.0063 (hit) / -0.1643 (pit) against the flagship's
    # inherited +1, and the marginal is -0.0075 on the provisional pool - the
    # "track record" reading is not true even unconditionally here. Conditional on
    # level_rank + age_rel_level it prices seasons USED to reach the level.
    "n_milb_seasons": 0,
}
```

(`k_rel` / `peak_k_rel` are deliberately absent: they are side-dependent -1 for hitters
and +1 for pitchers, and `efv_sign_audit.audit_provisional` correctly inherits the
per-side flagship declaration for them. Both fit in the declared direction here.)

---

## PATCH 4 -- display: the two chips whose direction reads backwards

Same defect class as the Arias card, found by this lane rather than by the owner.

### 4a. `efv_score.py` line 406, `_FACTOR_LABELS`

```python
    "bonus_log": "Signing bonus", "n_milb_seasons": "Track-record depth",
```
->
```python
    # n_milb_seasons label corrected 2026-07-25 (sign audit): the served weight is
    # NEGATIVE (-0.2324) because, holding level_rank and age fixed, more MiLB seasons
    # means more seasons USED to reach the same level. Labelled "Track-record depth"
    # it produced a DOWN chip on 1,882 of the 1,886 live hitter cards carrying it
    # (99.8%, mean magnitude 0.362) - telling a player with a long record that his
    # record is thin. The new label makes the DOWN direction read correctly.
    "bonus_log": "Signing bonus", "n_milb_seasons": "Seasons used to reach level",
```

Conservative alternative if the copy is disliked: add `"n_milb_seasons"` to
`_EXPLAINER_SKIP` (line 430) instead. That loses a real reason from the card, so the
relabel is preferred.

### 4b. `efv_ungraded.py` line 142, `_FACTOR_LABELS`

```python
    "peak_k_rel": "Peak K rate", "peak_obp_rel": "Peak on-base", "n_milb_seasons": "Track record",
```
->
```python
    "peak_k_rel": "Peak K rate", "peak_obp_rel": "Peak on-base",
    # see efv_score._FACTOR_LABELS: the provisional weight is -1.0063 (hit) /
    # -0.1643 (pit), so "Track record" rendered UP on 619 of 969 hitter and 615 of
    # 983 pitcher cards precisely BECAUSE those players have little track record.
    # Mean magnitude 1.300 on hitters (third-largest driver in that model).
    "n_milb_seasons": "Seasons used to reach level",
```

### 4c. `efv_score.py` lines 424-427, stale comment inside `_EXPLAINER_SKIP`

The justification quotes numbers that the served fit contradicts (it says the weight is
negative and the offset is "~+0.7"; the served weight is **+0.0397** and the live offset
is about **-0.005**). The skip decision is still right -- the term is inert -- but the
stated reason is wrong.

```python
#   milb_missing        - the imputed-production INDICATOR. eFV only grades players
#                         WITH a pro track record, so every live-scored prospect has
#                         milb_missing=0; it is a near-constant offset (~+0.7 on ~all
#                         of them) whose "Thin track record" label reads BACKWARDS (a
#                         real track record scores UP because the weight is negative
#                         and the training mean > 0). Carries no per-player signal.
```
->
```python
#   milb_missing        - the imputed-production INDICATOR. eFV only grades players
#                         WITH a pro track record, so every live-scored prospect has
#                         milb_missing=0 and the term is a CONSTANT offset carrying no
#                         per-player signal. (Magnitudes corrected 2026-07-25 by the
#                         sign audit: the served weight is +0.0397, not negative, and
#                         with train mean 0.017 / sd 0.129 the live offset is about
#                         -0.005 - far below the 0.05 explainer floor, not "~+0.7".
#                         Dropping the feature entirely moves pooled forward-chained
#                         rho by -0.00022 = 0.013x its floor.)
```

---

## FOLLOW-UPS (not patched here -- other lanes' files or a separate decision)

1. **The published diagnostics table is not the served model.**
   `data/xfv_eval.json.feature_diagnostics_full_window.ridge_std_weights` is fit by
   `_importances` on the **debuted-only** pool, while the served model
   (`fit_production_stack`) is fit on the **full pool minus recent busts**. The two
   disagree on SIGN for `age_rel_level` (published +0.076 vs served -0.173), `age`
   (hit: debuted-only +0.197 vs served -0.062) and `level_rank` (hit: debuted-only
   -0.050 vs served +0.426, against a declared +1). Anyone reading that table to answer
   "which way does this feature push?" gets the wrong answer for 5 of 14 hitter features.
   Recommend `run()` emit a `served_ridge_std_weights` block beside it (or rename the
   existing key to `debuted_only_ridge_std_weights`). Artifact churn, no served change.

2. **Register the lane's ledgers.** `data/xfv_sign_audit.json` and
   `data/xfv_sign_merge_gate.json` need `data/model_registry.json` rows under the
   standing rule. Deliberately NOT named `*_eval.json` so they do not trip
   `test_model_registry.py::test_every_eval_artifact_is_registered` mid-sweep.

3. **Unstable-but-not-yet-contradicting features.** `x_era_k` (pit) is served +0.0813
   while its informative-fold mean is -0.0480 and it is positive in only 5 of 9 folds;
   `age_rel_level` is served -0.0076 (pit) / -0.1730 (hit) and positive in 3 of 9 folds
   on both sides; `peak_k_rel` (pit) is served +0.1787 but flips to -0.1322 when refit
   on production-bearing rows only. None contradicts its declaration TODAY, so the guard
   passes, but each is one refit from doing so. A stability column belongs in the eval
   artifact; no action is justified on the measurement (all sub-floor).
