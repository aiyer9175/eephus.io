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

Run 2026-08-14, `tools/efv_driver_lab.py freekeys 2000`, 1,456 s. Ledger
`data/xfv_driver_freekeys.json`. No clause amended.

### D0: THE FLOOR MOVED, AND ON THE PITCHER SIDE IT MOVED A LOT

Re-derived on this basis (`floors generated_at 2026-08-14T22:39:54Z`):

| side | feature-add MDE95 rho | previous (2026-08-07) | change |
| --- | --- | --- | --- |
| hit | 0.0194 | 0.0193 | +0.5% |
| pit | **0.0172** | 0.0127 | **+35%** |

Gating pitcher candidates on the stale file would have been **35% too
permissive**. D0 was blocking for this reason and it earned it.

### D1: THE NOISE BAND ON THIS BASIS

hit `[-0.00577, -0.00179, -0.00091]`, pit `[-0.00378, -0.00345, -0.00210]`.
Every delta below is read against that band, never against zero.

### THE VERDICT: 26 ARMS, ZERO SURVIVORS

**Only 7 of 26 candidates are positive on pooled rho at all.** Best in family:

| arm | d_rho | d_block | control | folds | x floor | both instruments + | Holm |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pit.fv_trend | +0.01028 | +0.01696 | -0.00578 | 7/11 | **0.598x** | yes | no (p 0.206) |
| pit.tool_ch | +0.00498 | +0.00579 | **+0.00902** | 7/11 | 0.290x | yes | no |
| pit.tool_cmd | +0.00288 | -0.00116 | +0.00122 | 8/11 | 0.167x | no | no |
| hit.peak_obp_rel | +0.00218 | -0.00369 | +0.00279 | 4/11 | 0.112x | no | no |
| pit.era_rel | +0.00218 | -0.00154 | -0.00679 | 4/11 | 0.127x | no | no |
| hit.il_stints_pre | +0.00096 | +0.00129 | -0.00129 | 4/11 | 0.049x | yes | no |
| hit.prod_trend | +0.00020 | -0.00265 | -0.00352 | 2/11 | 0.010x | no | no |

**Not one arm clears D4.** The best reaches 0.598x of its own floor. **NONE
survives Holm** over the 26-arm family (best p 0.206). `pit.tool_ch`'s
zero-information twin scored **better than the candidate** (+0.00902 against
+0.00498), which is D4.4 failing in the most direct way available.

### NINE ARMS ARE WORSE THAN PURE NOISE

`pit.arsenal_depth` -0.01476, `pit.starter_shape` -0.01319, `hit.fv_trend`
-0.01195, `hit.bonus_log` -0.01127, `hit.n_sources` -0.01096, `pit.fv_stddev`
-0.01052, `pit.pick_overall` -0.00759, `hit.iso_rel` -0.00639, `pit.n_sources`
-0.00505 all sit BELOW the worst noise seed on their side. These columns do not
merely fail to help; they cost more than adding a random column costs.

### THREE FINDINGS WORTH KEEPING BEYOND THE NULL

**1. `bb_rel` does nothing for hitters, and that closes an obvious-looking
gap by measuring it.** The pitcher side ships `bb_rel`; the hitter side does
not, which looks like an oversight. Measured: **-0.00043 on rho** with a
control of -0.01102 and 4/11 folds. It is not an oversight, it is a null.

**2. The power correction survives its fourth challenge.** Both registered
repeats fail again: `hit.iso_rel` -0.00639 **losing in 0 of 11 folds**, and
`hit.tool_game_pwr` -0.00470 at 4/11. Neither came near the 2x bar D4.6 set for
a prior-contradicting result. The omission of game power for hitters IS the
power-overpricing correction and it has now been re-tested and rejected four
times.

**3. `pit.il_stints_pre` was refused, not measured, and the refusal is the
finding.** The column is present on all 982 pitcher rows and has **sd exactly
0.0**: no pitcher in the debuted training pool carries a pre-decision IL stint.
Injury history is inert on the pitcher side of this pool BY CONSTRUCTION, which
is consistent with the registry's IL revival clock and is a coverage refusal
rather than a null.

### WHAT THIS MEANS, PER D5

Section 6 says do not add AND do not remove on sub-floor evidence, so none of
these columns is dropped from `_vec` on this result. Twenty-six nulls is a
complete answer, and stop clause 3 forbids a second family over the same
columns. **The free-keys frontier is CLOSED.** The reopen burden is new DATA,
which is lane D-2 (`snapshots.tools_json._extras`, where the present-vs-future
tool gap and the 2017-onward velo and spin bands live), not a transform over
what `_vec` already computes.
