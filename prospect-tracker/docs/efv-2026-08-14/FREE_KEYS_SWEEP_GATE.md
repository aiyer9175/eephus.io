# FREE-KEYS SWEEP GATE (Lane D-1, 2026-08-14)

Pre-registered 2026-08-14, committed ALONE with the Results section EMPTY so git
timestamps it, BEFORE any candidate arm is run. Clauses are frozen from this
commit. No clause is amended after it answers.

Lab: `tools/efv_driver_lab.py` (existing, reused). Ledger:
`data/xfv_driver_freekeys.json`, deliberately outside the `data/*_eval*.json`
glob because this lane does not own a `model_registry.json` row.

---

## THE CANDIDATES, AND WHY THEY ARE FREE

`efv_model._vec` (`:1193-1301`) already EMITS a set of keys that neither
`_FEATURES_HIT` nor `_FEATURES_PIT` consumes. They cost nothing to test: no
sidecar, no network, no new join, no schema change. Every one is already
computed on every training and live row.

**Both sides:** `fv_trend`, `n_sources`, `fv_stddev`, `prod_trend`, `pos_prem`,
`pick_overall`, `bonus_log`, `il_stints_pre`.

**Hitters only:** `bb_rel` (SHIPPED for pitchers, absent for hitters),
`tool_game_pwr`, `tool_field`, `peak_obp_rel`, `iso_rel`.

**Pitchers only:** `tool_cmd`, `tool_sl`, `tool_ch`, `era_rel`,
`starter_shape`, `arsenal_depth`.

`game_pwr` for HITTERS is a special case and is tested with its history
attached, not blind: `efv_model.py:110-111,267-268` records that its omission IS
the power-overpricing correction, and it has been re-tested and rejected three
times (`iso_rel`, `peak_iso_rel`, conditional-power interactions). It enters
this sweep as a REGISTERED REPEAT, and a positive point estimate on it is
treated as prior-contradicting evidence requiring the stronger bar in clause
D4, not as a new finding.

## D0 THE FLOOR IS RE-DERIVED FIRST, ON THIS BASIS (blocking)

`data/xfv_driver_floors.json` is stamped **2026-08-07**. Since then the C-4 era
floor flipped on (2026-08-13), C-7 reverted the dispersion correction to
identity (2026-08-14), and the matrices were rebuilt (2026-08-14 15:51).
**Gating a fresh delta against that floor is precisely the staleness that has
crossed a verdict boundary twice in this programme.**

`python tools/efv_driver_lab.py floor 2000` is re-run FIRST and its output is
the only floor this lane may cite. The registered 0.017 hit / 0.016 pit numbers
are 4-fold-basis figures and are forbidden here by name.

**The floor is a property of the CANDIDATE, not a constant.** `fv` carries an
E_cond feature-add floor of 0.0250 and `tool_speed` 0.0045 on the same pool. Each
candidate is gated against a floor derived for a column of its own variance, and
the noise-column arms are what calibrate that.

## D1 THE NOISE FLOOR IS PART OF THE RESULT, NOT A FOOTNOTE

Measured 2026-08-07: **adding a pure-noise column costs -0.0016 to -0.0078
pooled rho.** So a candidate whose point estimate is +0.000 has not "done
nothing"; it has paid its own dilution and returned it. The noise arms are
re-derived on this basis and every candidate's delta is reported BESIDE the
noise band, never against zero.

## D2 THE STATISTIC AND THE PROTOCOL

Per `docs/EFV_GATE_STANDARD.md` section 2, all four are mandatory and none is
optional:

1. Paired bootstrap resampling **train AND test together**, ridge and consensus
   OLS **refit on every draw**, baseline and candidate scored on identical rows.
2. A **row-permuted zero-information control kept in the result set**, not run
   and discarded.
3. A **permutation null band**.
4. **At least 4 independent time splits** (the 11-fold basis supplies 11).

Both instruments are reported for every candidate: pooled rho AND block-rho.
B=2000, seed declared in the ledger.

## D3 MULTIPLICITY

This is a **sweep of about 19 arms**, which is the multiplicity regime where
sweeps manufacture winners. **Holm across the whole family, both sides pooled
into one family.** A candidate that clears its own floor but not Holm is
reported as NOT SHIPPABLE and said so plainly.

## D4 SHIP CONDITIONS (all required)

A candidate ships only if ALL hold:

1. Point delta **positive on BOTH instruments** (pooled rho and block-rho).
2. Delta **>= its own re-derived MDE95** on the primary instrument.
3. **Survives Holm** across the 19-arm family.
4. **Beats its zero-information twin** by more than the noise band.
5. Wins in **>= 7 of the 11 folds** (a majority that is not a single-fold
   artifact).
6. For `game_pwr` and any other REGISTERED REPEAT, additionally: the point
   estimate must exceed the floor by **2x**, because a prior-contradicting
   result on a thrice-rejected column needs more than a threshold crossing.

## D5 WHAT A FAILURE MEANS, DECIDED IN ADVANCE

`EFV_GATE_STANDARD.md` section 6: **do not add AND do not remove on sub-floor
evidence.** A null here is a null, not a licence to drop the column, and not a
licence to add it "because the sign is right". Every arm's result is committed
to the ledger including the losses, and a sweep that returns 19 nulls is a
complete and publishable answer.

## STOP CLAUSES

1. D0 fails or cannot run -> BLOCKED, no candidate is gated.
2. If the zero-information control scores as well as the best candidate, the
   sweep is reported as UNINFORMATIVE for that side and no arm is promoted.
3. **No second family.** If every arm nulls, this lane does not go looking for a
   transform, an interaction, or a re-parameterisation of the same columns. The
   reopen burden is new DATA, which is lane D-2 (`snapshots.tools_json._extras`),
   not a new functional form over these.

## RESULT (appended after the run)

*(empty at pre-registration)*
