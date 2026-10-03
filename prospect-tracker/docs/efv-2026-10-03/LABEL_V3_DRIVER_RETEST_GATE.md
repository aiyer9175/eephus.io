# Z1: the driver re-test on the fWAR label (registration, 2026-10-03)

Registered 2026-10-03 on branch `efv-conviction-2026-08-08`, after the label freeze (EPOCH_D9_FREEZE,
`7e34799f`, vintage `2026-10-02-0341299c20ec`) and before any new-label floor exists (the epoch's
step A has not started: `../_pre_epoch_fwar_2026-10/` is absent and neither
`data/xfv_mde_floor.json` nor `data/xfv_power_eval.json` carries an fWAR stamp). It is committed
ALONE with an empty results section, as `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` clause (k)
requires. Authority, in order: clause (k); the plan
`docs/master-plan-2026-09-11-war-epoch-drivers-betting.md` section 2 (2.1 to 2.7); the owner's
answers O8 and O9 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, section "ANSWERED 2026-09-17
(evening)"); this document. The engineering it runs on landed first, alone: `d9c86d68` (the
`retest` mode, the `alpha` argument of `holm_family`, the derived arm list) and `8fff4657` (the list
is written as LF bytes and git never converts it).

## 0. Suspension of CONVICTION_PROGRAM stop clause 1, for this registration only

`docs/efv-2026-08-19/CONVICTION_PROGRAM.md` stop clause 1 reads "No re-run of any of the 39 closed
feature arms, in any costume." It is SUSPENDED for this registration only, and for nothing else.
The reason is the one legitimate reopen condition the record names: a new LABEL (2026-09-03 locked
decision 6; do-not-reopen items 1 and 17; plan 2.7). The owner fixed the scope at O8, verbatim:
"**Full re-test, one read per arm**" ("~4.5h lab; a null permanently re-closes items 1, 8b and 17
with a date"). Every closed arm keeps the verdict recorded in its own artifact; this
document re-reads the columns once, on the frozen fWAR label, and adds no arm, frame, estimator or
seed the plan does not name. When the run's results are recorded below, stop clause 1 applies
again in full.

## 1. Blocking preconditions (plan 2.1, verbatim)

- **P1 label freeze.** A named build in the `label=` term, a per-side coverage receipt, and
  E7 passed.

  *Registration note (orchestrator ruling EPOCH-Q4-IMPL as amended R1a).* Plan 2.1 writes P1 as
  above and the gate's clause (k) writes it as "label freeze receipt with per-side coverage and E7
  passed"; the two agree. The fingerprint's `label=` term names the TRAINING LABEL BUILD and flips
  to `fwar@<vintage id>` at the epoch's step D + U (gate part 7 row D + U, part 8); under the
  owner's answer EPOCH-Q4 only the display doors keep eWAR v2. This registration commits before
  step A, while the term still reads `ewar_v2@2026-09-03T12:35:09`, so P1 is checked when Z1 runs,
  not now. **P1 is read from the epoch's step Z entry in `FWAR_LABEL_EPOCH_GATE.md` part 9**, which
  records the frozen fWAR vintage's `vintage_id` with the `label=` term as committed
  (`fwar@<that vintage id>`), the per-side coverage receipt and the E7 receipt. The term in
  `storage.BOARD_BASIS_FINGERPRINT` at Z1's HEAD must equal the one that entry records; if it does
  not, or if the entry is absent, Z1 does not run.
- **P2 floors first.** `python tools/efv_driver_lab.py floor 2000` and `auc 2000` on the new
  matrices. The eWAR v2 floors (rho 0.0170 hit / 0.0121 pit) adjudicate nothing here.
- **P3 parity.** The driver lab reproduces the new `xfv_eval*.json` bit-exact (the A0 check).
- **P4 input pinning.** sha256 of both matrices, the floors files and `efv_model.py`,
  recorded at start and verified at end, with the nightly idle. A mismatch voids the run.
- **P5 a derived arm list.** Extend `tools/efv_arm_ledger.py` to emit every distinct add
  column from the loss-ledger artifacts, including the 4-fold era and the 09-04 families.
  Dedupe by column definition, apply the mechanism rule and the exclusions mechanically,
  and commit the list with the registration.

How each is met or checked, as the engineering commit implemented it:

| | Checked by | When |
|---|---|---|
| P1 | the step Z entry in gate part 9 and `storage.BOARD_BASIS_FINGERPRINT` at HEAD, read by the Z1_RUN task before any command below | at run |
| P2 | `python tools/efv_driver_lab.py floor 2000`, then `auc 2000` (its controls A0 to A4 must pass); the retest mode reads the 11-fold debuted floors from the `floor` output and derives every other (side, frame, scope) floor in the same run, before any arm | at run, first |
| P3 | `python tools/efv_mde_lab.py parity` (the replica against the shipped `efv_model._run_eval`, no writes) and the `auc` mode's control A0 | at run, after P2 |
| P4 | the retest mode's `z1_pins`: sha256 of `xfv_hitter_matrix.json`, `xfv_pitcher_matrix.json`, `xfv_driver_floors.json`, `xfv_driver_auc_floors.json`, `efv_model.py`, `tools/efv_driver_lab.py` and the arm list, at start and at end; a mismatch writes `VOID` (kill rule 7). The nightly idle is the Z1_RUN task's tasklist guard plus the runbook's two `git status --short data/` reads five minutes apart | at run |
| P5 | `docs/efv-2026-10-03/z1_arm_list.json`, committed with this document (section 9) | now |

## 2. Mechanism rule (plan 2.2, verbatim, frozen before any read)

A component is re-priced if its window value correlates under 0.90 across frames AND its
change sd is at least 0.5 WAR [R2]. For hitters that is fielding only (0.624, 1.319 WAR).
The positional arms stay in the hitter mechanism family because item 17's refutation record
names them, and the registration says so. For pitchers it is strikeout/walk/home-run skill
(runs-allowed to FIP) and starter-vs-reliever career shape.

**The positional arms stay in the hitter mechanism family because item 17's refutation record
names them.** That is said here, as 2.2 asks.

How the list applies it mechanically: every column carries the components it MEASURES, declared
once in `tools/efv_arm_ledger.py` (`_MECH_BY_VEC`, `_MECH_BY_EXTRAS` and the `mech` field of the
4-fold-era definitions). A hitter arm with a `fielding` or `position` tag goes to H-MECH; a
pitcher arm with a `k_skill`, `bb_skill`, `hr_skill`, `runs_allowed_to_fip` or `sp_rp_shape` tag
goes to P-MECH; every other arm goes to its side's no-mechanism family. A column that only shares
an input with a re-priced component carries no tag (`tool_gap` averages six bat and glove grade
gaps and is not a fielding measure). The 2026-09-04 volume, age-interaction and health families go
to the no-mechanism families whatever their tags, by O8 (plan 2.3, "in their original scopes").

## 3. Families, alpha and Holm (plan 2.3, verbatim)

| Family | Content | Alpha | Arms / reads |
|---|---|---|---|
| H-MECH | `tool_field`, `pos_prem`, the D-Tool proxy, `field x pos_prem`, `tool_throw` alone (never measured; 717 of 845 now covered), three mean-z tool composites, `prospect_def_value`, the Defense+ prior proxy, the p_hold base rate, bmi x mid-position. **This is the "one registered attempt" of item 17** | 0.025 | 12 |
| P-MECH | `tool_cmd`, `tool_sl`, `tool_ch`, `era_rel`, `starter_shape`, `arsenal_depth`, `sits_mid`, `tops`, `rpm_fb`, `relief_flag`, `pit_peak_bb_rel` | 0.015 | 11 |
| H-NOMECH | every other distinct add column gated on the flagship ridge on an old label and not killed for a label-independent reason, plus the 09-04 volume, age-interaction and health families in their original scopes (O8, R2 OD-7) | 0.005 | about 131 reads |
| P-NOMECH | the same, pitcher side | 0.005 | about 84 reads |
| ABL (removal) | drop tests on 21 served features. `fv` dropped per side as the LIVENESS control: if dropping `fv` does not resolve as harmful, the instrument is dead and the run is BLOCKED | 0.05, for removal only | 21 + 2 |

Holm is a one-sided normal approximation within each family, sized jointly: both legs of
every arm count in m. At alpha 0.025 over 24 legs the step-1 z is 3.08, about 1.9x the
one-sided floor, so the 2x repeat bar is the binding bar in H-MECH. In the no-mechanism
families Holm binds harder, at a step-1 z of about 4.1 [R2].

**The leg-count rule, as implemented.** Every arm enters its family's Holm with two legs, its
pooled rho delta and its contributor-AUC delta, each with its own bootstrap sd, so m is twice the
arm count (`holm_family(rows, alpha=<family alpha>)` in `tools/efv_driver_lab.py`). The two `fv`
liveness controls run first and sit outside the ABL family's m. A leg whose bootstrap sd is not
estimable does not enter m and its arm cannot pass.

**The derived counts (the list in section 9 is the authority; the 2.3 column above is the plan's
estimate, written before the derivation existed):**

| Family | Alpha | Arms (reads) | Holm legs m | Step-1 one-sided z |
|---|---|---|---|---|
| H-MECH | 0.025 | 11 | 22 | 3.05 |
| P-MECH | 0.015 | 13 | 26 | 3.25 |
| H-NOMECH | 0.005 | 161 | 322 | 4.17 |
| P-NOMECH | 0.005 | 106 | 212 | 4.07 |
| ABL | 0.05 (removal only) | 21 + 2 liveness controls | 42 | 3.04 |
| total | | 314 | | |

## 4. Identical rows, instrument, bars (plan 2.4, verbatim)

- **Identical rows** [R2]. Each arm runs on the frame and scope it was registered on. That
  is the 11-fold pair-weighted basis (SCORED_YEARS 2014-2024) for D-1, the C program and the
  4-fold-era arms (the retired 4-fold basis is not reproduced, because it adjudicates
  nothing); the six-fold 2019-2024 frame for the D-2 `tools_json` arms; and the original
  full, readable and debuted scopes for the 09-04 families. Baseline and candidate are
  scored on identical rows in every draw. Column definitions and imputation postures are
  copied verbatim. The reserved 2025 base-year cohort stays out of the frame.
- **Instrument.** E_refit (the lab's only estimator, named on every claim), B = 2000 paired
  bootstrap with the ridge and consensus OLS refit on each draw, a 200-draw permutation null
  per arm, a row-permuted zero-information twin, and three N(0,1) noise arms for the floor.
  Seed 20260807 (permutation stream seed + 7), noise seeds 0/1/2.
- **An arm passes only if all of these hold:** rho delta at least 2x its own floor (every arm
  is a registered repeat); positive on block-rho; no contributor-AUC veto; survives Holm in
  its family; beats its twin by more than the noise band; wins at least 7 of 11 folds (4 of 6
  on the six-fold frame); and stays inside the D-1 live-robustness limits [R2].
- **Attribution control** for passers only: re-run on the same rows with the OLD label. The
  pass is attributed to the label only if the old-label delta stays inside its floor.

**The run parameters 2.4 leaves open, as the engineering commit implemented them** (each is fixed
here, before any read):

1. *Frames and scopes.* `deb11` = the 11 years 2014 to 2024 (`efv_model.SCORED_YEARS`); `deb6` =
   2019 to 2024 (`EXTRAS_YEARS`). Scopes: `debuted` (`load_pool`); `readable` (the volume lab's
   rows with a readable MiLB season); `full_observable` and `debuted_observable` (the health
   lab's full and debuted pools restricted to its IL-observable cohort). No frame contains a 2025
   or later decision year; a test pins it.
2. *Columns.* Each 4-fold-era column is rebuilt from the producer's inputs by the producer's
   arithmetic and is bit-identical to the producer's own column on the same rows
   (`test_efv_driver_retest.py`, 26 passed: efv_lab_runner expressions, the deleted weight-recal
   producer read from git at `8fecb2f5^`, `run_lab.augment`, the `efv_ml_lab` extra joins with
   the fold list emptied so nothing was fitted, `efv_wrc_lab`). No arm failed parity. The D-2,
   handedness, volume, age-interaction and health columns are built by their own labs' functions.
   The one bit two producers disagree on is the sign of a zero (efv_lab_runner's `g()` reads
   -0.0 as 0.0); the list records each producer's read and the port reproduces it.
3. *Floors.* The 11-fold debuted floors per side are P2's `floor 2000` (`data/xfv_driver_floors.json`:
   rho, block-rho, contributor AUC). Every other (side, frame, scope), eight of them, gets its own
   three N(0,1) noise arms in the same run, before any arm: seeds 20260807 + 7300 + 10i + s
   (i the combination's sorted index, s in 0, 1, 2). The floor of each statistic is 1.645 times
   the largest of the three bootstrap sds. The noise band is the largest absolute noise-arm rho
   delta.
4. *The twin.* One row permutation of the arm's candidate columns (all of them jointly for a
   multi-column arm), seed 20260807 + 7700 + the arm's position in the list (list order, the two liveness controls
   skipped); for a removal arm, the
   dropped feature permuted in place. "Beats its twin by more than the noise band" is: rho delta
   minus the twin's rho delta greater than the noise band.
5. *The permutation null.* gate()'s 200 draws of the arm's first candidate column, stream seed
   20260807 + 7. Removal arms carry the twin and no permutation null.
6. *Fold wins.* At least 7 of 11 on `deb11` and 4 of 6 on `deb6`. On a scope whose rows do not
   score every fold (the IL archive starts in 2019), the same share of the folds that score:
   ceil(7/11 x scored) and ceil(4/6 x scored).
7. *The AUC veto.* An arm is vetoed when its contributor-AUC delta is at or below minus its
   contributor-AUC floor. An arm whose AUC floor is not estimable cannot pass.
8. *The live-robustness limit.* No numeric limit was ever registered; every arm the 2026-08-07
   record ruled a live blow-up moved a served player 320 or more rank places
   (`docs/efv-drivers-2026-08-07/GATE_RECORD.md` section 6). The limit is a maximum absolute rank
   shift of 300 on the live board (`live_move`), checked only for an arm that clears every other
   condition. A passer whose column the live matrix cannot build (a join or pool-level column)
   reads `NOT_ADJUDICATED_NO_LIVE`, never a pass.
9. *The removal family.* A removal is supported only if dropping the feature RAISES rho by at
   least 2x the floor, block-rho is positive, contributor AUC is not vetoed, the rho leg survives
   Holm at 0.05, the drop beats the permuted-in-place twin by more than the noise band, and the
   fold-win share holds. Liveness: dropping `fv` must lower rho by at least the floor on each side;
   if either side does not, the run stops BLOCKED before any arm (kill rule 5).
10. *Attribution.* For a passer, the same rows with the old label's `target_censored` from the
    pre-epoch matrices (`--old-label-dir`), the same columns, B = 2000; attributed to the label
    only if the absolute old-label rho delta is below the arm's floor. The pre-epoch matrices are
    not in the runbook's step A copy list and `data/xfv_*_matrix.json` is untracked, so they exist
    only if the epoch's step A copies them; without them the control reads `NOT_RUN` and the
    passer is reported unattributed.

## 5. Serving a passer (O9) and the confirmation leg on the reserved 2025 cohort

**O9, verbatim:** "**Provisional, own epoch, no accuracy copy, auto-removed on a failed 2028
confirmation**". Plan 2.4: "**Serving a passer** (O9): provisional, in its own grade-basis epoch,
with no accuracy copy. Its confirmation on the reserved 2025 fold at the 2028 run is
pre-registered, and a failed confirmation removes it automatically."

**The Z1-confirmation leg, with its own clauses.** It exists only for an arm that passes Z1;
with no passer it is empty and reads nothing.

- (C1) *Frame.* The 2025 debut cohort, as `docs/efv-v2/PROGRAM.md` section 2.4 defines R-VM (the
  2025 debut cohort, vm2 counting rule). The Z1 run itself never reads it: it is outside every
  frame above, and `efv_model.SCORED_YEARS` and `source_backtest.CANDIDATE_YEARS` keep excluding
  2025 and later until the R-VM look record exists (PROGRAM.md R-VM guard, test pin).
- (C2) *When.* Once, at the 2028 run (RT 2028), which is R-VM look 3 in PROGRAM.md's calendar.
  O9 names the 2028 confirmation, so this leg takes no look at RT 2026 or RT 2027.
- (C3) *Statistic.* The passer's pooled rho delta, the same column on the same instrument, with
  the 2025 fold scored forward from the earlier decision years; one-sided.
- (C4) *Family.* The leg is read inside the joint registration the owner chose at PROGRAM Q4 = A
  ("One joint registration with Z1c on the 2025 debut cohort, one Holm family, first look after
  the RT 2026 labels"): PROGRAM.md section 2.4, "Z1's serving confirmation for passers also names
  the 2025 fold at the 2028 run; the joint registration covers it." That registration (EV-12,
  `docs/efv-v2/EFV_V2_GATE.md`) sizes the one Holm family; this leg contributes one rho leg per
  passer to it.
- (C5) *Outcome.* A failed confirmation removes the passer automatically (O9). A passed one ends
  the provisional status only by its own later decision; no accuracy copy in either case.

**Z1c is not carried here.** The gate's clause (k) names "**Z1c** the pitcher-stuff first fold" as
its own registration downstream of this one, and plan 2.7 item 8a says pitcher stuff "opens BY ITS
OWN CLOCK ... own registration (Z1c), not Z1". A Z1c leg on the 2025 debut cohort would put a
pitcher-stuff column (excluded from this list by 8a) and a 2025-cohort read (excluded from this
frame by 2.4) inside Z1, so this document cannot carry it without breaking its own frame rules. The
Z1c half of EV-12 clause (c)'s joint text therefore has no counterpart in this registration; it
needs Z1c's own registration or an owner amendment.

## 6. Compute budget and process (plan 2.5, verbatim)

Measured cost per arm: 45 to 66 s on the 11-fold frame at B = 2000 with 200 permutations (the
26-arm D-1 run took 1,456 s), 28 to 33 s on the six-fold frame (641 s for 13 arms), and 739 s
for `auc 2000` [R2]. The core program is about 84 reads and roughly 85 minutes plus floors.
The full program, including the 09-04 families, is about 260 reads and roughly 4.5 hours
[R2]. Run one lab process at a time and never alongside the suite: `conftest.py` reverts
dirtied tracked files, and the single-process suite crashes on memory. The chunked suite
runs before the registration commit and after the results commit. No network, no credits.

At the derived 314 reads the same per-arm costs give about 4 to 5.5 hours for the arms, plus 24
noise reads for the eight derived floors and the two liveness reads (bootstrap only, no
permutations), plus P2 and P3. One process, no network, no credits; the handedness sidecar is
read from `.cache/xfv_handedness.json`, never rebuilt.

## 7. Kill rules (plan 2.6, verbatim)

1. **Frozen list.** Nothing may be added after the registration commit.
2. **One read per arm.** No friendlier frame, estimator or seed, and no smoke number cited.
3. **No second family** over the same columns if everything nulls.
4. **Uninformative family.** If its twins score at least as well as its best candidate,
   nothing in it is promoted.
5. **Dead instrument.** If the `fv` drop control fails, the run is BLOCKED.
6. **Program close.** If nothing passes, record the frontier as RE-CLOSED on label build X,
   rewrite do-not-reopen items 1, 8 and 17 with the date, and allow no driver re-test until
   either the 2027 RT advance or an owner-registered label DEFINITION change that moves the
   debuted label more than this one did (Spearman under 0.99 against the frozen label on
   either side).
7. **Stale inputs** (P4) void the run.
8. **Denominator published.** The arm ledger is regenerated with this registration as a new
   lane.

## 8. The pre-registered expectation (plan 2.6, verbatim)

**The pre-registered expectation.** Zero survivors. 5.6% new hitter label variance is small
against floors of about 0.016-0.019 [R1]. A null is a result: it closes item 17 permanently
on existing columns. MiLB SDR, if Will's data ever arrives, is a new data source under its
own registration, not a fourth look.

The gate's clause (k) records the same prior: "zero survivors. The record is 0 of 48 arms and 0 of
177 in the 2026-09-04 families [R2]. The payoff of this program is coherence and a permanent close,
not a driver that passes."

## 9. The frozen arm list (P5)

`docs/efv-2026-10-03/z1_arm_list.json`, committed with this document.

- **sha256 `fb45f5fccf1e7a0b55e232d921885e6b47458a0267a8c3a113390e82777c9c87`** (LF bytes;
  `.gitattributes` keeps git from converting them). The retest mode refuses any other file
  (`--sha`).
- Produced by `python tools/efv_arm_ledger.py --z1-arm-list docs/efv-2026-10-03/z1_arm_list.json`
  at `8fff4657`. It reads committed artifacts only, scores nothing, and never rewrites
  `data/xfv_arm_ledger.json`. Each source's sha256 is recorded in the list; one source is read at
  a pinned commit, `data/xfv_health_profile_eval.json` at `d500e8d1`, because the health lab was
  re-run describe-only at `fc24963d` and the HEAD file no longer carries the 94 arms it
  adjudicated.
- **314 arms**: H-MECH 11, P-MECH 13, H-NOMECH 161, P-NOMECH 106, ABL 23 (21 removals + the two
  `fv` liveness controls). By origin: 36 arms carry a 4-fold-era origin (15 of them also read on
  the 11-fold basis by D-1 or the C program), 14 more come from D-1 and the C program alone, 13
  from D-2, and 228 from the 2026-09-04 families (volume 110, age interaction 24, health 94).
- **Set aside by rule, listed in the file:** 29 arms (17 `R-DEGENERATE`, outside their original
  Holm family because the column was constant on its scope; 7 `R-SERVED`, the column is now a
  served feature and ABL reads it; 3 `R-27`, `il_stints_pre` by plan 2.7; 2 `R-SWAP`, a
  replacement and not an add) and 19 whole lanes (C3 threshold pairs, C1b positions, the lambda
  and elite sweeps, pace-from-entry, the B3 level blend, pitcher stuff (Z1c), model class (Z1b),
  the eFV v2 list-vintage lanes, calibration and target lanes, the 09-04 level weights).
- **Dedupe:** one arm per (side, frame, scope, column definition, dropped columns); a column read
  in several lanes is one arm carrying every origin.
- **Imputation posture:** where an artifact read one column under two postures
  (`xfv_weight_recal_eval.json`, mean and zero), the arm carries the shipped-convention zero
  posture every other lane reading the same column used; the train-fold-mean posture is
  fold-dependent and is not a column.

**Against the plan's 2.3 names.** H-MECH matches ten of the twelve arms the names describe (`tool_field`,
`pos_prem`, the D-Tool proxy, `field x pos_prem`, `tool_throw` alone, the three mean-z composites,
`prospect_def_value` as its registered two-column join `def_value` + `def_home_entropy`, bmi x
mid-position as its registered three-column join `bmi` + `bmi_x_mid` + `is_mid_pos`) and adds one
registered arm the names omit, `field_plus_interaction` (`tool_field` with `field x pos_prem`,
`xfv_defense_tools_eval.json`). **Two names have no arm: the Defense+ prior proxy and the p_hold
base rate.** Their only record is prose (the `xfv_pitcher` registry row, rejected item (d), and
commit `c30515e9`'s message, 2026-06-24: tested "via faithful proxies", "Defense+ also BLOCKED to
regenerate"); no committed artifact holds either arm's id, definition or values, and the
producer's extra-join file did not exist when they ran. A mechanical derivation from the
loss-ledger artifacts cannot emit them, and kill rule 1 forbids adding them after this commit.
P-MECH matches all eleven names and adds two by the tag rule: `pos_prem` for pitchers
(`efv_model._pos_premium`, "starters over relievers", a starter-versus-reliever measure) and
`kbb_rel` for pitchers (`k_rel - bb_rel`, strikeout and walk skill,
`xfv_weight_recal_eval.json`). The no-mechanism families are larger than 2.3's estimates mainly
because the health family's gated arms (94 reads at `d500e8d1`) are in them, as 2.7 directs.

## 10. The run (Z1_RUN), in order

On a day that is not a registered look date, after the epoch's step Z entry exists in gate part 9,
with the tasklist guard clean (no `run_monthly.py`, no pytest, no other lab, no epoch step) and the
nightly idle:

```
python tools/efv_driver_lab.py floor 2000
python tools/efv_driver_lab.py auc 2000
python tools/efv_mde_lab.py parity
python tools/efv_driver_lab.py retest docs/efv-2026-10-03/z1_arm_list.json 2000 \
    --sha fb45f5fccf1e7a0b55e232d921885e6b47458a0267a8c3a113390e82777c9c87 \
    --old-label-dir <the step A folder holding the pre-epoch xfv_hitter_matrix.json and xfv_pitcher_matrix.json>
```

The retest writes `data/xfv_driver_retest.json` (floors per frame and scope, the liveness reads,
every arm's gate record, each family's Holm, the verdicts, the kill-rule evaluations, the sha256
pins at start and end). Its stdout and stderr are teed to the run task's output folder before
anything else runs. The chunked suite (`python tools/run_suite.py`) runs after the results commit.
Then kill rule 8: `python tools/efv_arm_ledger.py` regenerates the ledger with this registration as
a new lane.

## 11. What this document and the epoch gate may say about each other

No result of Z1 may be recorded in `FWAR_LABEL_EPOCH_GATE.md`, and no result of the fWAR label
epoch may be recorded in this document. Each cites the other only by name and commit.

## Results

**EMPTY AT REGISTRATION.** No floor, arm delta, Holm row, verdict or attribution exists on the fWAR
label at this commit.
