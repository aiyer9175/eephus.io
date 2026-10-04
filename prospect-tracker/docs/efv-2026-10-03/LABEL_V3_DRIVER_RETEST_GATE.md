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

Empty at registration (`2aa9ce8d`). Filled on 2026-10-04 by the Z1_RUN task from the one run below. Every number in this section is copied from `data/xfv_driver_retest.json` (generated_at `2026-10-04T09:26:50Z`, produced_by `tools/efv_driver_lab.py`), committed with it; nothing here is recomputed. No result of the fWAR label epoch is recorded here: P1 was read from the epoch's step Z entry (`FWAR_LABEL_EPOCH_GATE.md` part 9, '2026-10-03: step Z', `73850ecc`), cited by name and commit only, as section 11 requires.

### R1. The run

- HEAD at the run: `24ea56e6` (branch `efv-conviction-2026-08-08`); date 2026-10-04, not a registered look date; tasklist clean (no `run_monthly.py`, no pytest, no other lab; the orchestrator's LANE_HOLD drained every lane); `git status --short data/` identical in two reads five minutes apart (01:42 and 01:47 local).
- The four commands of section 10, in order, stdout and stderr teed to the run task's `z1_run.txt` before anything else ran: `floor 2000` (rc 0, 430.5 s), `auc 2000` (rc 0, 434.0 s), `efv_mde_lab.py parity` (rc 0), then `retest docs/efv-2026-10-03/z1_arm_list.json 2000 --sha fb45f5fc... --old-label-dir ../_pre_epoch_fwar_2026-10` (rc 0, 12,223.8 s, one process). The retest was started after the P2 and P3 outputs were read, in the same teed log.
- B 2000, seed 20260807, arm list sha256 `fb45f5fccf1e7a0b55e232d921885e6b47458a0267a8c3a113390e82777c9c87` (the frozen list).

### R2. Preconditions P1 to P5, as checked at the run

- **P1 HELD.** `storage.BOARD_BASIS_FINGERPRINT` at HEAD carries `label=fwar@2026-10-02-0341299c20ec`, equal to the term and `vintage_id` the step Z entry's LABEL FREEZE RECEIPT records; `data/fwar_vintage.json` and the E7 receipt hash to the sha256 values that entry records; the per-side coverage receipt and the E7 receipt are the ones it records, and E7 is at or above its bar on both sides there.
- **P2 HELD.** `floor 2000` wrote `data/xfv_driver_floors.json`: hit rho 0.014, block 0.0158, contributor AUC 0.0084; pit rho 0.0115, block 0.0137, contributor AUC 0.0067. `auc 2000` wrote `data/xfv_driver_auc_floors.json` and printed `ALL CONTROLS PASS: True` (A0 parity True on contributor and star, both sides; A1 noise inside its floors; A2 twins NULL inside the floor; A3 label permutation centred with theoretical width; A4 rule table pass True).
- **P3 HELD.** `efv_mde_lab.py parity`: hit n 782, consensus 0.3883, blend 0.4208 against the shipped `xfv_eval.json` n 782, 0.3883, 0.4208; pit n 907, 0.3379, 0.3636 against the shipped `xfv_eval_pitcher.json` n 907, 0.3379, 0.3636; and the `auc` mode's A0 True.
- **P4 HELD, and kill rule 7 did not fire.** The retest's `z1_pins` at start equal its pins at end on every file:

| pin | sha256 at start | equal at end |
| --- | --- | --- |
| hit_matrix | `2559d7e9746661add19e7010ed7b77c6b801744dd0909931a8fec0a013827cdb` | True |
| pit_matrix | `71ea7b3974d7286aff90265262773ed314ff4a1b42e67d8b51fb423b0704d529` | True |
| floors | `bf27c656d1d1fb7074b471a02e6e2fe962661e6d9b0c1e0e6c3f6fb38c7e4823` | True |
| auc_floors | `57a8d554b427380414c9cae10dedacc7fca7ca199f1e2bc7bc474bc526667c3e` | True |
| efv_model | `01dacb910a2f92729105092f89830aab3dbc6891e32fa7b8319df55cada5853f` | True |
| driver_lab | `164ab015d3f98ccd2ed0eadf8b8652da48cd4883cd5624f756a1ddbcb9c75957` | True |
| arm_list | `fb45f5fccf1e7a0b55e232d921885e6b47458a0267a8c3a113390e82777c9c87` | True |

- **P5 HELD.** The list's sha256 equals section 9's; the retest's `--sha` guard accepted it.

### R3. The liveness control first (kill rule 5)

| control | rho delta | block-rho delta | contributor-AUC delta | floor rho | rho bootstrap sd | rho CI95 | resolves harmful |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ABL.hit.drop-fv` | -0.01424 | -0.00109 | -0.01032 | 0.014 | 0.01638 | [-0.05067, 0.01578] | True |
| `ABL.pit.drop-fv` | -0.02692 | -0.02696 | -0.01229 | 0.0115 | 0.01529 | [-0.05671, 0.00315] | True |

Kill rule 5: fired `False`. The instrument is live on both sides under section 4 item 9's rule (the drop lowers rho by at least the floor), so the run was not BLOCKED. The hitter drop clears its floor by 0.00024.

### R4. Floors per (side, frame, scope), derived before any arm

| side:frame:scope | rho | block-rho | contributor AUC | noise band (rho) | source |
| --- | --- | --- | --- | --- | --- |
| hit:deb11:debuted | 0.014 | 0.0158 | 0.0084 | 0.00367 | data/xfv_driver_floors.json (P2) |
| hit:deb11:debuted_observable | 0.019 | 0.0227 | 0.01 | 0.00896 | three N(0,1) noise arms in this run |
| hit:deb11:full_observable | 0.0192 | 0.0244 | 0.0189 | 0.01165 | three N(0,1) noise arms in this run |
| hit:deb11:readable | 0.0117 | 0.0134 | 0.0068 | 0.0058 | three N(0,1) noise arms in this run |
| hit:deb6:debuted | 0.0077 | 0.0097 | 0.0067 | 0.00128 | three N(0,1) noise arms in this run |
| pit:deb11:debuted | 0.0115 | 0.0137 | 0.0067 | 0.00772 | data/xfv_driver_floors.json (P2) |
| pit:deb11:debuted_observable | 0.0219 | 0.0218 | 0.0122 | 0.00414 | three N(0,1) noise arms in this run |
| pit:deb11:full_observable | 0.0166 | 0.0163 | 0.0093 | 0.00161 | three N(0,1) noise arms in this run |
| pit:deb11:readable | 0.0152 | 0.0164 | 0.0082 | 0.00821 | three N(0,1) noise arms in this run |
| pit:deb6:debuted | 0.0129 | 0.0132 | 0.0067 | 0.01153 | three N(0,1) noise arms in this run |

### R5. The families: Holm, kill rule 4, survivors

| family | alpha | arms read | Holm legs m | step-1 Holm alpha | legs surviving Holm | kill rule 4 (uninformative) | best rho delta (arm) | best twin rho delta | verdicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H-MECH | 0.025 | 11 | 22 | 0.00114 | 0 | True | 0.00209 (`H-MECH.hit.defense`) | 0.00614 | NULL 11 |
| P-MECH | 0.015 | 13 | 26 | 0.00058 | 0 | False | 0.00074 (`P-MECH.pit.kbb_rel`) | -6e-05 | NULL 13 |
| H-NOMECH | 0.005 | 161 | 322 | 2e-05 | 0 | False | 0.01309 (`H-NOMECH.hit.il_open_at_decision@debuted_observable`) | 0.01287 | NULL 161 |
| P-NOMECH | 0.005 | 106 | 212 | 2e-05 | 0 | False | 0.0099 (`P-NOMECH.pit.career_ip_ge_400@readable`) | 0.00787 | NULL 106 |
| ABL | 0.05 | 21 | 42 | 0.00119 | 0 | False | 0.00543 (`ABL.hit.drop-tool_hit`) | 0.00152 | NULL 21 |

Arms not built: 0. Arms whose rho delta reached even 1x its own floor: 0. Survivors: 0 of 312 arms, 0 removals supported. The attribution control runs for passers only; with no passer it was not run (`--old-label-dir` was supplied and read nothing). Kill rule 4 fired in H-MECH (its best twin, 0.00614, scored above its best candidate, 0.00209), so nothing in H-MECH could have been promoted in any case.

### R6. Every arm (the artifact's gate record, per family)

Columns: rho, block-rho and contributor-AUC deltas (E_refit, B 2000) with the rho and AUC bootstrap sd; the row-permuted twin's rho delta; fold wins of folds scored (needed); the Holm rank and step alpha of the rho leg and of the AUC leg within the family (m = 2 x arms); the pass conditions that FAILED (2x = rho at least 2x its floor, blk = block-rho positive, auc = no contributor-AUC veto, holm = survives Holm, twin = beats its twin by more than the noise band, folds = fold-win share, inf = family informative); the verdict.

#### H-MECH (11 arms, alpha 0.025)

| arm | frame:scope | n scored | rho d (sd) | block-rho d | AUC d (sd) | twin rho d | folds | Holm rho (rank, alpha) | Holm AUC (rank, alpha) | failed | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `H-MECH.hit.athl3` | deb11:debuted | 782 | 0.00173 (0.00716) | -0.00143 | 0.00033 (0.00439) | 0.0001 | 4/11 (7) | 2, 0.00119 | 7, 0.00156 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.athl_sf` | deb11:debuted | 782 | 0.00082 (0.00463) | -0.00048 | 0.00046 (0.00275) | 0.00098 | 5/11 (7) | 4, 0.00132 | 5, 0.00139 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.athl_st` | deb11:debuted | 782 | 0.0005 (0.00603) | 0.00014 | -0.00119 (0.00329) | -0.00108 | 6/11 (7) | 6, 0.00147 | 16, 0.00357 | 2x holm twin folds inf | NULL |
| `H-MECH.hit.defense` | deb11:debuted | 782 | 0.00209 (0.00988) | 0.00384 | 0.00036 (0.00514) | -0.00169 | 7/11 (7) | 3, 0.00125 | 8, 0.00167 | 2x holm inf | NULL |
| `H-MECH.hit.dtool_proxy` | deb11:debuted | 782 | -7e-05 (0.0057) | -0.00048 | 0.00016 (0.00324) | -0.00046 | 3/11 (7) | 12, 0.00227 | 9, 0.00179 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.field_x_pos` | deb11:debuted | 782 | -0.00285 (0.00626) | -0.00789 | -0.00086 (0.00354) | 0.00087 | 2/11 (7) | 19, 0.00625 | 13, 0.0025 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.physical` | deb11:debuted | 782 | -0.006 (0.00954) | -0.00607 | -0.00349 (0.00586) | 0.00614 | 5/11 (7) | 22, 0.025 | 21, 0.0125 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.pos_prem` | deb11:debuted | 782 | -0.00223 (0.00586) | -0.006 | -0.00086 (0.00331) | -4e-05 | 2/11 (7) | 17, 0.00417 | 14, 0.00278 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.tool_field` | deb11:debuted | 782 | -5e-05 (0.0059) | -0.00048 | 3e-05 (0.00341) | -0.00255 | 4/11 (7) | 11, 0.00208 | 10, 0.00192 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.tool_field+field_x_pos` | deb11:debuted | 782 | -0.00415 (0.0091) | -0.00744 | -0.00137 (0.00503) | 0.0034 | 2/11 (7) | 20, 0.00833 | 15, 0.00313 | 2x blk holm twin folds inf | NULL |
| `H-MECH.hit.tool_throw` | deb11:debuted | 782 | 0.00146 (0.00577) | 0.0005 | -0.00132 (0.00334) | -0.00202 | 7/11 (7) | 1, 0.00114 | 18, 0.005 | 2x holm twin inf | NULL |

#### P-MECH (13 arms, alpha 0.015)

| arm | frame:scope | n scored | rho d (sd) | block-rho d | AUC d (sd) | twin rho d | folds | Holm rho (rank, alpha) | Holm AUC (rank, alpha) | failed | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P-MECH.pit.arsenal_depth` | deb11:debuted | 907 | -0.00821 (0.00899) | -0.00284 | -0.00151 (0.00477) | -0.00472 | 5/11 (7) | 17, 0.0015 | 13, 0.00107 | 2x blk holm twin folds | NULL |
| `P-MECH.pit.era_rel` | deb11:debuted | 907 | -0.00015 (0.00396) | 0.00014 | 0.00025 (0.00269) | -0.00509 | 5/11 (7) | 4, 0.00065 | 3, 0.00063 | 2x holm twin folds | NULL |
| `P-MECH.pit.kbb_rel` | deb11:debuted | 907 | 0.00074 (0.00239) | 0.00047 | 0.00032 (0.00116) | -6e-05 | 6/11 (7) | 1, 0.00058 | 2, 0.0006 | 2x holm twin folds | NULL |
| `P-MECH.pit.peak_bb_rel` | deb11:debuted | 907 | -0.0103 (0.00587) | -0.0074 | -0.00387 (0.00293) | -0.00023 | 5/11 (7) | 24, 0.005 | 22, 0.003 | 2x blk holm twin folds | NULL |
| `P-MECH.pit.pos_prem` | deb11:debuted | 907 | -0.00283 (0.00238) | -0.00139 | -0.0022 (0.002) | -0.00379 | 1/11 (7) | 21, 0.0025 | 19, 0.00187 | 2x blk holm twin folds | NULL |
| `P-MECH.pit.relief_flag` | deb11:debuted | 907 | -0.00309 (0.00682) | 0.00191 | -0.00138 (0.00377) | -0.00397 | 6/11 (7) | 16, 0.00136 | 14, 0.00115 | 2x holm twin folds | NULL |
| `P-MECH.pit.rpm_fb@deb6` | deb6:debuted | 642 | -0.00218 (0.00891) | 0.00051 | -0.00076 (0.00332) | -0.00023 | 3/6 (4) | 12, 0.001 | 11, 0.00094 | 2x holm twin folds | NULL |
| `P-MECH.pit.sits_mid@deb6` | deb6:debuted | 642 | -0.00129 (0.00808) | -3e-05 | -0.00034 (0.00317) | -0.01139 | 3/6 (4) | 9, 0.00083 | 7, 0.00075 | 2x blk holm twin folds | NULL |
| `P-MECH.pit.starter_shape` | deb11:debuted | 907 | -0.01889 (0.0083) | -0.00877 | -0.0068 (0.00434) | -0.00073 | 5/11 (7) | 26, 0.015 | 23, 0.00375 | 2x blk auc holm twin folds | NULL |
| `P-MECH.pit.tool_ch` | deb11:debuted | 907 | -0.01035 (0.00952) | -0.00108 | -0.00046 (0.00509) | -0.00223 | 5/11 (7) | 18, 0.00167 | 6, 0.00071 | 2x blk holm twin folds | NULL |
| `P-MECH.pit.tool_cmd` | deb11:debuted | 907 | -0.00436 (0.01138) | 0.00088 | -0.0004 (0.00686) | -0.00035 | 6/11 (7) | 15, 0.00125 | 5, 0.00068 | 2x holm twin folds | NULL |
| `P-MECH.pit.tool_sl` | deb11:debuted | 907 | -0.01546 (0.00795) | -0.00901 | -0.00537 (0.00453) | -0.00467 | 5/11 (7) | 25, 0.0075 | 20, 0.00214 | 2x blk holm twin folds | NULL |
| `P-MECH.pit.tops@deb6` | deb6:debuted | 642 | -0.00138 (0.00804) | -4e-05 | -0.00039 (0.00315) | -0.00055 | 2/6 (4) | 10, 0.00088 | 8, 0.00079 | 2x blk holm twin folds | NULL |

#### H-NOMECH (161 arms, alpha 0.005)

| arm | frame:scope | n scored | rho d (sd) | block-rho d | AUC d (sd) | twin rho d | folds | Holm rho (rank, alpha) | Holm AUC (rank, alpha) | failed | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `H-NOMECH.hit.bats_l+bats_s` | deb11:debuted | 782 | -0.00359 (0.00909) | -0.00128 | -0.00248 (0.00504) | -0.00115 | 6/11 (7) | 249, 7e-05 | 267, 9e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.bb_rel` | deb11:debuted | 782 | -0.00044 (0.00504) | -0.00204 | 5e-05 (0.00355) | -0.00235 | 4/11 (7) | 176, 3e-05 | 153, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.bonus_log` | deb11:debuted | 782 | -0.01207 (0.00757) | -0.01211 | -0.00369 (0.00407) | -0.00167 | 2/11 (7) | 296, 0.00019 | 286, 0.00014 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.career_h` | deb11:debuted | 782 | 0.00191 (0.00454) | 0.00311 | 0.00175 (0.00263) | 2e-05 | 7/11 (7) | 72, 2e-05 | 44, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.career_h@readable` | deb11:readable | 666 | -0.00081 (0.00844) | -0.00104 | 0.00165 (0.00486) | 0.00916 | 4/9 (6) | 180, 3e-05 | 79, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.career_hr` | deb11:debuted | 782 | 0.00122 (0.00457) | 0.00146 | 0.00048 (0.00262) | -0.00014 | 6/11 (7) | 96, 2e-05 | 120, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.career_hr@readable` | deb11:readable | 666 | 0.0011 (0.00569) | 0.00116 | 0.00188 (0.00348) | 0.0056 | 6/9 (6) | 118, 2e-05 | 58, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.career_pa` | deb11:debuted | 782 | 0.00191 (0.00413) | 0.00205 | 0.00112 (0.00238) | -0.00118 | 6/11 (7) | 68, 2e-05 | 66, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.career_pa@readable` | deb11:readable | 666 | -0.00184 (0.00806) | -0.00018 | -0.00084 (0.00454) | 0.00632 | 4/9 (6) | 225, 5e-05 | 205, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.career_pa_ge_1000` | deb11:debuted | 782 | 0.00145 (0.00389) | 0.00278 | 0.00077 (0.00243) | -0.00036 | 6/11 (7) | 76, 2e-05 | 83, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.career_pa_ge_1000@readable` | deb11:readable | 666 | 0.00254 (0.00544) | -0.00041 | 0.00267 (0.00341) | 0.00034 | 5/9 (6) | 67, 2e-05 | 37, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.career_pa_ge_1500` | deb11:debuted | 782 | 0.00346 (0.00374) | 0.00633 | 0.0007 (0.00209) | 0.0014 | 6/11 (7) | 24, 2e-05 | 80, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.career_pa_ge_1500@readable` | deb11:readable | 666 | 0.00579 (0.0055) | 0.00765 | 0.00093 (0.00296) | 0.00513 | 5/9 (6) | 16, 2e-05 | 84, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.career_pa_ge_2000` | deb11:debuted | 782 | -0.0 (0.00324) | -0.00081 | -0.00028 (0.00143) | -0.00571 | 2/11 (7) | 157, 3e-05 | 209, 4e-05 | 2x blk holm folds | NULL |
| `H-NOMECH.hit.career_pa_ge_2000@readable` | deb11:readable | 666 | 0.0033 (0.00475) | 0.00335 | 0.00194 (0.00221) | 0.00046 | 2/9 (6) | 43, 2e-05 | 26, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.career_sb` | deb11:debuted | 782 | -0.0032 (0.0052) | -0.00448 | -0.00023 (0.00303) | -0.00012 | 2/11 (7) | 278, 0.00011 | 170, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.career_sb@readable` | deb11:readable | 666 | 0.00726 (0.00743) | 0.00688 | 0.00631 (0.00386) | 0.00103 | 6/9 (6) | 21, 2e-05 | 2, 2e-05 | 2x holm | NULL |
| `H-NOMECH.hit.career_tb` | deb11:debuted | 782 | 0.0025 (0.00407) | 0.00155 | 0.00161 (0.00242) | -0.00395 | 6/11 (7) | 50, 2e-05 | 45, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.career_tb@readable` | deb11:readable | 666 | 0.00185 (0.00718) | 0.00183 | 0.00255 (0.00424) | 0.00243 | 4/9 (6) | 98, 2e-05 | 52, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_back@debuted_observable` | deb11:debuted_observable | 448 | -0.01197 (0.01139) | -0.01122 | -0.00407 (0.00409) | -0.00336 | 1/5 (4) | 291, 0.00016 | 289, 0.00015 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_back@full_observable` | deb11:full_observable | 1025 | 0.00185 (0.00509) | -5e-05 | 0.0001 (0.00389) | 0.00259 | 2/5 (4) | 77, 2e-05 | 150, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_elbow@debuted_observable` | deb11:debuted_observable | 448 | -0.00677 (0.00728) | -0.0052 | -0.00305 (0.00348) | -0.00666 | 0/5 (4) | 287, 0.00014 | 285, 0.00013 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_elbow@full_observable` | deb11:full_observable | 1025 | -2e-05 (0.00344) | -0.00154 | -0.00064 (0.00406) | 0.00054 | 1/5 (4) | 159, 3e-05 | 198, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_forearm@debuted_observable` | deb11:debuted_observable | 448 | 0.00061 (0.01163) | 0.00021 | 7e-05 (0.00359) | -0.00028 | 1/5 (4) | 145, 3e-05 | 151, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_forearm@full_observable` | deb11:full_observable | 1025 | 0.00087 (0.00345) | 0.00088 | 2e-05 (0.0038) | 0.00034 | 2/5 (4) | 100, 2e-05 | 155, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_hamstring@debuted_observable` | deb11:debuted_observable | 448 | -0.00042 (0.01136) | 0.00215 | -0.00334 (0.00659) | -0.00014 | 3/5 (4) | 165, 3e-05 | 269, 9e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_hamstring@full_observable` | deb11:full_observable | 1025 | -0.00054 (0.00583) | -0.00291 | -0.00119 (0.00564) | -0.00157 | 3/5 (4) | 179, 3e-05 | 216, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_hip@debuted_observable` | deb11:debuted_observable | 448 | -0.00135 (0.00755) | -0.00102 | -0.00088 (0.00433) | -0.00749 | 1/5 (4) | 204, 4e-05 | 212, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_hip@full_observable` | deb11:full_observable | 1025 | -0.00507 (0.00529) | -0.00557 | -0.00166 (0.004) | 0.00057 | 1/5 (4) | 288, 0.00014 | 252, 7e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_knee@debuted_observable` | deb11:debuted_observable | 448 | 0.00084 (0.00642) | 0.00021 | 0.00192 (0.00544) | -0.00194 | 1/5 (4) | 133, 3e-05 | 78, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_knee@full_observable` | deb11:full_observable | 1025 | 0.00061 (0.00354) | -0.00011 | 0.00133 (0.00417) | -0.00034 | 1/5 (4) | 124, 3e-05 | 82, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.cat_oblique@debuted_observable` | deb11:debuted_observable | 448 | 0.00879 (0.00574) | 0.00405 | 0.0005 (0.00296) | -0.00614 | 2/5 (4) | 4, 2e-05 | 125, 3e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.cat_oblique@full_observable` | deb11:full_observable | 1025 | 0.00211 (0.00416) | 0.00485 | -0.00188 (0.00431) | -0.00593 | 3/5 (4) | 60, 2e-05 | 257, 8e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_shoulder@debuted_observable` | deb11:debuted_observable | 448 | 0.0073 (0.00722) | 0.00178 | 0.00054 (0.00353) | 0.00762 | 3/5 (4) | 18, 2e-05 | 129, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.cat_shoulder@full_observable` | deb11:full_observable | 1025 | 0.00034 (0.00523) | 0.00314 | -0.00198 (0.0056) | 0.00111 | 4/5 (4) | 140, 3e-05 | 240, 6e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.cat_wrist@debuted_observable` | deb11:debuted_observable | 448 | 0.01192 (0.01384) | 0.01889 | 0.0031 (0.00788) | 0.00137 | 3/5 (4) | 28, 2e-05 | 75, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.cat_wrist@full_observable` | deb11:full_observable | 1025 | 0.006 (0.00849) | 0.01177 | 0.0022 (0.00883) | -0.00057 | 3/5 (4) | 42, 2e-05 | 102, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.durable_zero_il@debuted_observable` | deb11:debuted_observable | 448 | 0.00047 (0.00896) | 0.00438 | -0.00036 (0.00475) | -0.00028 | 3/5 (4) | 144, 3e-05 | 169, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.durable_zero_il@full_observable` | deb11:full_observable | 1025 | 0.00224 (0.0082) | 0.00253 | 0.00231 (0.01029) | 0.00474 | 2/5 (4) | 93, 2e-05 | 107, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.eta_delta@deb6` | deb6:debuted | 523 | -0.00051 (0.00523) | -0.00318 | -0.00099 (0.00301) | -0.00029 | 2/6 (4) | 182, 4e-05 | 239, 6e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.fv_stddev` | deb11:debuted | 782 | -0.00298 (0.00477) | -0.00236 | -0.00128 (0.00254) | 0.00037 | 2/11 (7) | 279, 0.00011 | 268, 9e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.fv_trend` | deb11:debuted | 782 | -0.00117 (0.01159) | -0.00357 | 0.00203 (0.00649) | -0.00127 | 5/11 (7) | 183, 4e-05 | 85, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.health_index_oof@debuted_observable` | deb11:debuted_observable | 448 | -0.13057 (0.0493) | -0.04707 | -0.05668 (0.0229) | 0.01059 | 1/5 (4) | 314, 0.00056 | 312, 0.00045 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.health_index_oof@full_observable` | deb11:full_observable | 1025 | -0.12162 (0.05094) | -0.067 | -0.12126 (0.0597) | 0.00167 | 2/5 (4) | 311, 0.00042 | 305, 0.00028 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.height_in@deb6` | deb6:debuted | 523 | 0.00033 (0.00385) | -0.0009 | 0.00015 (0.00218) | 0.00018 | 2/6 (4) | 137, 3e-05 | 138, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.hit_sb_rel` | deb11:debuted | 782 | 0.00169 (0.00358) | 0.0004 | -0.00077 (0.00214) | -1e-05 | 4/11 (7) | 65, 2e-05 | 241, 6e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.hits_and_speed` | deb11:debuted | 782 | -0.00208 (0.0046) | -0.00256 | -0.00117 (0.00283) | -0.00024 | 4/11 (7) | 259, 8e-05 | 251, 7e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.hits_and_speed@readable` | deb11:readable | 666 | 0.00463 (0.00563) | 0.00383 | 0.003 (0.00356) | 0.0054 | 3/9 (6) | 32, 2e-05 | 30, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.hr_per_500pa_peak` | deb11:debuted | 782 | -1e-05 (0.00379) | 0.00014 | -0.00027 (0.00214) | 0.00133 | 4/11 (7) | 158, 3e-05 | 188, 4e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.hr_per_500pa_peak@readable` | deb11:readable | 666 | 0.00117 (0.00484) | -0.00037 | 0.0018 (0.00302) | 0.01287 | 4/9 (6) | 105, 2e-05 | 53, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_60day@debuted_observable` | deb11:debuted_observable | 448 | -0.02044 (0.01641) | -0.01303 | -0.01392 (0.00885) | 0.00775 | 1/5 (4) | 292, 0.00016 | 295, 0.00018 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.il_60day@full_observable` | deb11:full_observable | 1025 | -0.00437 (0.00848) | -0.00515 | -0.00473 (0.00732) | -0.00465 | 1/5 (4) | 270, 9e-05 | 281, 0.00012 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_days@debuted_observable` | deb11:debuted_observable | 448 | -0.0038 (0.0098) | -0.00329 | -0.00212 (0.00587) | -0.0052 | 1/5 (4) | 245, 6e-05 | 242, 6e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_days@full_observable` | deb11:full_observable | 1025 | -0.00474 (0.01131) | -0.00581 | -0.00504 (0.01155) | 0.00413 | 2/5 (4) | 254, 7e-05 | 258, 8e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_days_ge_120@debuted_observable` | deb11:debuted_observable | 448 | 0.00212 (0.00873) | 0.00215 | 0.00142 (0.00523) | 0.00121 | 3/5 (4) | 104, 2e-05 | 95, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_days_ge_120@full_observable` | deb11:full_observable | 1025 | 0.0019 (0.00904) | 0.00184 | 0.00276 (0.00991) | 0.0001 | 4/5 (4) | 112, 2e-05 | 91, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.il_days_ge_180@debuted_observable` | deb11:debuted_observable | 448 | 0.00673 (0.00879) | 0.00427 | 0.0016 (0.00587) | -0.00942 | 3/5 (4) | 38, 2e-05 | 94, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.il_days_ge_180@full_observable` | deb11:full_observable | 1025 | 0.00075 (0.0081) | 0.0016 | -0.00129 (0.00853) | 0.00048 | 3/5 (4) | 136, 3e-05 | 197, 4e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_days_ge_30@debuted_observable` | deb11:debuted_observable | 448 | 0.0084 (0.01337) | 0.00961 | 0.0061 (0.0074) | 0.00875 | 3/5 (4) | 48, 2e-05 | 31, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_days_ge_30@full_observable` | deb11:full_observable | 1025 | 0.01291 (0.01064) | 0.01115 | 0.022 (0.01161) | -0.0008 | 3/5 (4) | 14, 2e-05 | 1, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.il_days_ge_60@debuted_observable` | deb11:debuted_observable | 448 | 0.00132 (0.0088) | 0.00326 | 0.0014 (0.00504) | -0.00397 | 3/5 (4) | 131, 3e-05 | 92, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_days_ge_60@full_observable` | deb11:full_observable | 1025 | 0.00348 (0.00734) | 0.00439 | 0.00559 (0.00918) | 0.00545 | 4/5 (4) | 64, 2e-05 | 51, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.il_days_ge_90@debuted_observable` | deb11:debuted_observable | 448 | 0.00106 (0.00984) | 0.00352 | 0.00111 (0.00557) | -0.00669 | 3/5 (4) | 134, 3e-05 | 117, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_days_ge_90@full_observable` | deb11:full_observable | 1025 | 0.00152 (0.00949) | 0.00174 | 0.0017 (0.00976) | 0.00122 | 4/5 (4) | 127, 3e-05 | 123, 3e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.il_max_stint_days@debuted_observable` | deb11:debuted_observable | 448 | -0.00417 (0.00991) | -0.00306 | -0.00294 (0.00601) | 0.00537 | 1/5 (4) | 255, 7e-05 | 266, 9e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_max_stint_days@full_observable` | deb11:full_observable | 1025 | -0.00547 (0.01139) | -0.00712 | -0.00633 (0.01187) | 0.00201 | 1/5 (4) | 264, 8e-05 | 273, 0.0001 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_open_at_decision@debuted_observable` | deb11:debuted_observable | 448 | 0.01309 (0.00998) | 0.00636 | 0.00269 (0.00565) | 0.01022 | 3/5 (4) | 7, 2e-05 | 63, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_open_at_decision@full_observable` | deb11:full_observable | 1025 | 0.00319 (0.00767) | 0.00853 | -0.00065 (0.00791) | 0.00058 | 3/5 (4) | 73, 2e-05 | 173, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_stints@debuted_observable` | deb11:debuted_observable | 448 | 0.01044 (0.00821) | 0.01152 | 0.00106 (0.00414) | -0.00359 | 2/5 (4) | 10, 2e-05 | 99, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.il_stints@full_observable` | deb11:full_observable | 1025 | 0.00011 (0.00692) | 0.0028 | -0.00442 (0.00779) | 0.00043 | 2/5 (4) | 152, 3e-05 | 274, 0.0001 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_stints_ge_2@debuted_observable` | deb11:debuted_observable | 448 | -0.00077 (0.0088) | 0.00229 | 2e-05 (0.00454) | -0.0025 | 2/5 (4) | 177, 3e-05 | 156, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_stints_ge_2@full_observable` | deb11:full_observable | 1025 | -0.0009 (0.00746) | -0.00101 | -0.00234 (0.0102) | -0.00576 | 3/5 (4) | 187, 4e-05 | 226, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_stints_ge_3@debuted_observable` | deb11:debuted_observable | 448 | -0.00332 (0.00864) | 0.00086 | -0.00203 (0.00432) | 0.00973 | 3/5 (4) | 243, 6e-05 | 261, 8e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_stints_ge_3@full_observable` | deb11:full_observable | 1025 | -0.00131 (0.00679) | -0.00242 | -0.00144 (0.00665) | -0.00148 | 1/5 (4) | 208, 4e-05 | 219, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.il_stints_ge_4@debuted_observable` | deb11:debuted_observable | 448 | 0.01002 (0.00788) | 0.00714 | 0.00099 (0.00376) | 0.00243 | 3/5 (4) | 11, 2e-05 | 97, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.il_stints_ge_4@full_observable` | deb11:full_observable | 1025 | 0.0017 (0.00552) | 0.00289 | -0.00248 (0.00579) | -0.00073 | 2/5 (4) | 86, 2e-05 | 256, 7e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.iso_rel` | deb11:debuted | 782 | -0.00094 (0.00465) | -0.00223 | 4e-05 (0.00295) | -0.00254 | 5/11 (7) | 211, 4e-05 | 154, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.joint__all_products` | deb11:debuted | 782 | -0.04569 (0.02957) | -0.03815 | -0.02584 (0.0157) | -0.00246 | 5/11 (7) | 293, 0.00017 | 297, 0.00019 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.kbb_rel` | deb11:debuted | 782 | -0.00102 (0.00433) | -0.00223 | 0.00013 (0.003) | -0.00024 | 4/11 (7) | 229, 5e-05 | 147, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.level__k_rel` | deb11:debuted | 782 | -0.08571 (0.02352) | -0.05735 | -0.04444 (0.01236) | -0.00028 | 6/11 (7) | 322, 0.005 | 320, 0.00167 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.level__obp_rel` | deb11:debuted | 782 | -0.00347 (0.01525) | -0.00066 | -0.00178 (0.00853) | 0.00014 | 5/11 (7) | 224, 5e-05 | 214, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.level__ops_rel` | deb11:debuted | 782 | -0.0534 (0.02431) | -0.02979 | -0.02954 (0.0131) | -0.00591 | 4/11 (7) | 308, 0.00033 | 309, 0.00036 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.level__peak_k_rel` | deb11:debuted | 782 | -0.01666 (0.03481) | -0.00281 | -0.00389 (0.01766) | 0.00236 | 4/11 (7) | 263, 8e-05 | 221, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_h` | deb11:debuted | 782 | 0.00082 (0.00345) | 0.00071 | 0.00048 (0.00216) | -0.00023 | 5/11 (7) | 106, 2e-05 | 108, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_h@readable` | deb11:readable | 666 | 0.0029 (0.00525) | 0.00406 | 0.00085 (0.0034) | 0.00625 | 6/9 (6) | 56, 2e-05 | 101, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.max_h_ge_120` | deb11:debuted | 782 | 0.00431 (0.00492) | 0.00685 | 0.00216 (0.00299) | 0.0001 | 6/11 (7) | 27, 2e-05 | 41, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.max_h_ge_120@readable` | deb11:readable | 666 | 0.0112 (0.00709) | 0.01406 | 0.00591 (0.00422) | 0.00313 | 7/9 (6) | 3, 2e-05 | 5, 2e-05 | 2x holm | NULL |
| `H-NOMECH.hit.max_h_ge_140` | deb11:debuted | 782 | -0.00048 (0.00532) | -0.00032 | -0.0007 (0.0027) | -0.00086 | 6/11 (7) | 178, 3e-05 | 231, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_h_ge_140@readable` | deb11:readable | 666 | 0.00222 (0.0075) | -0.00044 | 0.00254 (0.0039) | -5e-05 | 5/9 (6) | 88, 2e-05 | 46, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_h_ge_160` | deb11:debuted | 782 | 0.00023 (0.0038) | -0.0003 | -0.00048 (0.00214) | -0.00185 | 3/11 (7) | 143, 3e-05 | 222, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_h_ge_160@readable` | deb11:readable | 666 | -0.00057 (0.00555) | 0.00118 | -0.00118 (0.00303) | 0.00248 | 6/9 (6) | 184, 4e-05 | 247, 7e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.max_h_ge_180` | deb11:debuted | 782 | -0.00187 (0.00183) | -0.00103 | -0.0009 (0.00135) | 0.00075 | 3/11 (7) | 290, 0.00015 | 282, 0.00012 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_h_ge_180@readable` | deb11:readable | 666 | 0.00076 (0.00311) | 0.00276 | -0.00048 (0.00208) | -2e-05 | 4/9 (6) | 103, 2e-05 | 227, 5e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_hr` | deb11:debuted | 782 | -0.00054 (0.0041) | -6e-05 | -0.00048 (0.00233) | -0.00256 | 3/11 (7) | 193, 4e-05 | 213, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_hr@readable` | deb11:readable | 666 | 0.00264 (0.00503) | 0.00149 | 0.0019 (0.00322) | -0.00032 | 4/9 (6) | 59, 2e-05 | 54, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_15` | deb11:debuted | 782 | -0.00075 (0.00356) | -0.0002 | -0.00046 (0.00209) | 0.00106 | 2/11 (7) | 215, 5e-05 | 220, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_15@readable` | deb11:readable | 666 | 0.00331 (0.0053) | 0.00277 | 0.00418 (0.00319) | -0.00162 | 6/9 (6) | 49, 2e-05 | 8, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.max_hr_ge_20` | deb11:debuted | 782 | -0.00244 (0.00535) | -0.00111 | -0.00177 (0.00298) | -0.00032 | 5/11 (7) | 260, 8e-05 | 276, 0.00011 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_20@readable` | deb11:readable | 666 | 0.00437 (0.00789) | 0.00818 | -0.00048 (0.00444) | -0.0053 | 7/9 (6) | 55, 2e-05 | 186, 4e-05 | 2x holm | NULL |
| `H-NOMECH.hit.max_hr_ge_25` | deb11:debuted | 782 | -0.00099 (0.00463) | -0.00327 | -0.00107 (0.00274) | -0.00055 | 3/11 (7) | 218, 5e-05 | 248, 7e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_25@readable` | deb11:readable | 666 | 0.00104 (0.00597) | -0.00075 | -0.00084 (0.00371) | 0.00134 | 4/9 (6) | 122, 2e-05 | 223, 5e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_30` | deb11:debuted | 782 | -0.00064 (0.00462) | -0.00063 | -0.00021 (0.00274) | 0.00307 | 5/11 (7) | 195, 4e-05 | 171, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_30@readable` | deb11:readable | 666 | -0.0001 (0.00657) | 0.00061 | 0.00175 (0.00402) | 0.00161 | 4/9 (6) | 160, 3e-05 | 70, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_35` | deb11:debuted | 782 | -0.0003 (0.00503) | 0.00295 | 0.00059 (0.00313) | -0.00013 | 6/11 (7) | 167, 3e-05 | 119, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_hr_ge_35@readable` | deb11:readable | 666 | 0.00108 (0.00719) | -0.0002 | 0.00371 (0.00467) | 0.00423 | 4/9 (6) | 130, 3e-05 | 35, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_pa` | deb11:debuted | 782 | -0.00026 (0.00328) | -5e-05 | -0.00041 (0.00205) | -0.00292 | 3/11 (7) | 172, 3e-05 | 210, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_pa@readable` | deb11:readable | 666 | 0.00048 (0.0047) | 0.00144 | 0.0001 (0.00308) | 0.00092 | 5/9 (6) | 135, 3e-05 | 149, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_pa_ge_400` | deb11:debuted | 782 | 0.00015 (0.00406) | 0.00238 | -0.00033 (0.00235) | -0.00057 | 5/11 (7) | 148, 3e-05 | 196, 4e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_pa_ge_400@readable` | deb11:readable | 666 | 0.00516 (0.00585) | 0.00386 | 0.00281 (0.00356) | -0.00067 | 4/9 (6) | 25, 2e-05 | 36, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.max_pa_ge_500` | deb11:debuted | 782 | 0.00031 (0.00465) | 0.00103 | 0.00018 (0.0029) | -0.00078 | 5/11 (7) | 139, 3e-05 | 141, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_pa_ge_500@readable` | deb11:readable | 666 | 0.0026 (0.00628) | 0.00089 | 0.00177 (0.00392) | 0.00116 | 6/9 (6) | 74, 2e-05 | 69, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.max_pa_ge_550` | deb11:debuted | 782 | 0.00098 (0.00485) | 0.00325 | -0.00043 (0.00264) | -0.00803 | 7/11 (7) | 116, 2e-05 | 199, 4e-05 | 2x holm | NULL |
| `H-NOMECH.hit.max_pa_ge_550@readable` | deb11:readable | 666 | 0.00616 (0.00648) | 0.00378 | 0.00352 (0.0035) | 0.00072 | 6/9 (6) | 23, 2e-05 | 19, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.max_sb` | deb11:debuted | 782 | 0.00083 (0.00409) | 0.00025 | -0.00051 (0.00239) | 0.00046 | 4/11 (7) | 115, 2e-05 | 217, 5e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_sb@readable` | deb11:readable | 666 | 0.00814 (0.00637) | 0.00588 | 0.00486 (0.00356) | 0.00241 | 5/9 (6) | 9, 2e-05 | 6, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_20` | deb11:debuted | 782 | -0.00036 (0.00489) | 0.00139 | -0.00128 (0.00245) | 0.00482 | 5/11 (7) | 168, 3e-05 | 272, 0.0001 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_20@readable` | deb11:readable | 666 | 0.00503 (0.00685) | 0.00359 | 0.0011 (0.00375) | 0.00342 | 6/9 (6) | 40, 2e-05 | 90, 2e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.max_sb_ge_30` | deb11:debuted | 782 | -0.00203 (0.00427) | -0.00145 | -0.00102 (0.00263) | 0.00117 | 4/11 (7) | 262, 8e-05 | 246, 6e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_30@readable` | deb11:readable | 666 | 0.00549 (0.00549) | 0.00476 | 0.00393 (0.00335) | 0.00571 | 4/9 (6) | 20, 2e-05 | 15, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_40` | deb11:debuted | 782 | -0.00116 (0.00468) | -0.00197 | -0.00196 (0.00287) | -0.00307 | 5/11 (7) | 230, 5e-05 | 283, 0.00013 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_40@readable` | deb11:readable | 666 | 0.00124 (0.00585) | -0.00248 | -0.00035 (0.00364) | 0.00793 | 5/9 (6) | 111, 2e-05 | 181, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_50` | deb11:debuted | 782 | -0.00208 (0.00332) | -0.00221 | -0.00097 (0.00243) | -0.00017 | 3/11 (7) | 280, 0.00012 | 250, 7e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_sb_ge_50@readable` | deb11:readable | 666 | 0.00431 (0.00451) | 0.00225 | 0.00403 (0.00332) | -0.00198 | 4/9 (6) | 22, 2e-05 | 13, 2e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.max_tb` | deb11:debuted | 782 | 0.00059 (0.00335) | -0.00114 | 0.00045 (0.00204) | 0.00151 | 3/11 (7) | 121, 2e-05 | 109, 2e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_tb@readable` | deb11:readable | 666 | 0.00106 (0.00491) | 0.00013 | 0.00206 (0.00317) | 0.0032 | 4/9 (6) | 110, 2e-05 | 47, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_tb_ge_250` | deb11:debuted | 782 | -0.00021 (0.00441) | -0.0017 | -6e-05 (0.00249) | 0.0055 | 2/11 (7) | 166, 3e-05 | 161, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_tb_ge_250@readable` | deb11:readable | 666 | 0.00517 (0.00646) | 0.00451 | 0.00295 (0.00367) | 1e-05 | 3/9 (6) | 34, 2e-05 | 33, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_tb_ge_300` | deb11:debuted | 782 | -0.00132 (0.00481) | -0.00164 | -0.00075 (0.00255) | 0.00102 | 4/11 (7) | 234, 6e-05 | 237, 6e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.max_tb_ge_300@readable` | deb11:readable | 666 | 0.00492 (0.00669) | 0.00404 | 0.00372 (0.00364) | 0.00829 | 3/9 (6) | 39, 2e-05 | 17, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_xbh` | deb11:debuted | 782 | 0.0006 (0.00371) | 0.00118 | 0.00033 (0.00221) | -0.00049 | 6/11 (7) | 126, 3e-05 | 132, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.max_xbh@readable` | deb11:readable | 666 | 0.00445 (0.00527) | 0.00329 | 0.00411 (0.00332) | 0.00519 | 4/9 (6) | 29, 2e-05 | 12, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.milb_readable` | deb11:debuted | 782 | -0.00016 (0.0019) | -0.00044 | -0.00011 (0.00107) | -0.00257 | 3/11 (7) | 174, 3e-05 | 185, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.milb_seasons` | deb11:debuted | 782 | 0.00061 (0.00205) | 0.00098 | 0.00023 (0.00112) | -0.00207 | 5/11 (7) | 87, 2e-05 | 113, 2e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.milb_seasons@readable` | deb11:readable | 666 | -0.00021 (0.00244) | 0.00067 | -4e-05 (0.00152) | 0.00376 | 5/9 (6) | 175, 3e-05 | 162, 3e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.n_sources` | deb11:debuted | 782 | -0.00682 (0.012) | -0.01522 | -0.00571 (0.00724) | -0.00353 | 2/11 (7) | 275, 0.0001 | 284, 0.00013 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.peak_iso_rel` | deb11:debuted | 782 | -0.00017 (0.00585) | -0.00171 | -0.0006 (0.00339) | -0.00317 | 3/11 (7) | 163, 3e-05 | 203, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.peak_obp_rel` | deb11:debuted | 782 | -0.00086 (0.00372) | 0.00127 | -0.0006 (0.00225) | -0.00023 | 5/11 (7) | 228, 5e-05 | 232, 5e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.peak_ops_rel` | deb11:debuted | 782 | -0.00093 (0.00348) | 0.00036 | -0.00062 (0.00207) | -0.00113 | 5/11 (7) | 233, 6e-05 | 238, 6e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.pick_overall` | deb11:debuted | 782 | -0.00521 (0.01006) | -0.00468 | -0.00212 (0.00508) | 0.001 | 3/11 (7) | 271, 0.0001 | 253, 7e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.prod_trend` | deb11:debuted | 782 | -0.00103 (0.00374) | -0.00062 | -0.00044 (0.00236) | -0.00025 | 3/11 (7) | 235, 6e-05 | 207, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.product__k_rel` | deb11:debuted | 782 | -0.06959 (0.02645) | -0.05201 | -0.04381 (0.01456) | -4e-05 | 6/11 (7) | 313, 0.0005 | 317, 0.00083 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.product__obp_rel` | deb11:debuted | 782 | -0.05474 (0.0239) | -0.04159 | -0.02606 (0.01212) | 5e-05 | 5/11 (7) | 310, 0.00038 | 307, 0.00031 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.product__ops_rel` | deb11:debuted | 782 | -0.05208 (0.02855) | -0.04258 | -0.02451 (0.01465) | 0.00132 | 4/11 (7) | 302, 0.00024 | 299, 0.00021 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.product__peak_k_rel` | deb11:debuted | 782 | -0.07728 (0.0255) | -0.06215 | -0.04945 (0.01373) | 0.0028 | 6/11 (7) | 318, 0.001 | 321, 0.0025 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.pwr_and_playing_time` | deb11:debuted | 782 | -0.0006 (0.0046) | -0.00286 | -0.00049 (0.00281) | -0.00097 | 3/11 (7) | 192, 4e-05 | 202, 4e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.pwr_and_playing_time@readable` | deb11:readable | 666 | 0.00124 (0.00608) | 0.00012 | -0.00067 (0.00388) | 0.00182 | 6/9 (6) | 114, 2e-05 | 200, 4e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.replace__age_rel_level_by_products-drop-age_rel_level` | deb11:debuted | 782 | -0.04591 (0.02925) | -0.03772 | -0.02617 (0.01558) | -0.00172 | 5/11 (7) | 294, 0.00017 | 300, 0.00022 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.risk_ord@deb6` | deb6:debuted | 523 | -0.00098 (0.00773) | -0.0016 | 0.00057 (0.00371) | 0.00034 | 2/6 (4) | 189, 4e-05 | 128, 3e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.sb_rate_rel` | deb11:debuted | 782 | 0.00175 (0.00348) | 0.00116 | -0.00084 (0.00217) | -0.00093 | 5/11 (7) | 61, 2e-05 | 244, 6e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.seasons_at_level` | deb11:debuted | 782 | 0.00116 (0.00363) | 0.00187 | -0.00026 (0.00203) | -0.00125 | 4/11 (7) | 81, 2e-05 | 191, 4e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.spd_sb_50` | deb11:debuted | 782 | 0.00177 (0.00365) | 0.00084 | -0.00063 (0.00227) | -0.00056 | 7/11 (7) | 62, 2e-05 | 236, 6e-05 | 2x holm twin | NULL |
| `H-NOMECH.hit.spd_sb_70` | deb11:debuted | 782 | 0.00136 (0.00323) | 0.00077 | -0.00036 (0.00194) | -0.00404 | 6/11 (7) | 71, 2e-05 | 206, 4e-05 | 2x holm folds | NULL |
| `H-NOMECH.hit.split__k_rel` | deb11:debuted | 782 | -0.07755 (0.02342) | -0.05842 | -0.03603 (0.01312) | -0.00364 | 6/11 (7) | 319, 0.00125 | 315, 0.00063 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.split__obp_rel` | deb11:debuted | 782 | -0.05367 (0.0254) | -0.03892 | -0.02419 (0.01288) | -0.00467 | 4/11 (7) | 306, 0.00029 | 303, 0.00025 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.split__ops_rel` | deb11:debuted | 782 | -0.03756 (0.02111) | -0.02955 | -0.02096 (0.01097) | -0.00061 | 3/11 (7) | 301, 0.00023 | 304, 0.00026 | 2x blk auc holm twin folds | NULL |
| `H-NOMECH.hit.split__peak_k_rel` | deb11:debuted | 782 | -0.0597 (0.0203) | -0.0465 | -0.01683 (0.0101) | -0.00156 | 7/11 (7) | 316, 0.00071 | 298, 0.0002 | 2x blk auc holm twin | NULL |
| `H-NOMECH.hit.tool_game_pwr` | deb11:debuted | 782 | -0.00411 (0.00685) | -0.00731 | -0.00188 (0.00389) | -0.00066 | 2/11 (7) | 277, 0.00011 | 265, 9e-05 | 2x blk holm twin folds | NULL |
| `H-NOMECH.hit.tool_gap@deb6` | deb6:debuted | 523 | 0.00158 (0.00534) | 0.00295 | 0.00182 (0.00336) | -0.00452 | 4/6 (4) | 89, 2e-05 | 57, 2e-05 | 2x holm | NULL |
| `H-NOMECH.hit.weight@deb6` | deb6:debuted | 523 | 0.00019 (0.00383) | -0.0003 | -8e-05 (0.00217) | -0.00062 | 4/6 (4) | 146, 3e-05 | 164, 3e-05 | 2x blk holm twin | NULL |
| `H-NOMECH.hit.wrc_comp` | deb11:debuted | 782 | -0.00057 (0.00446) | 0.00012 | -0.00041 (0.00236) | 0.00257 | 6/11 (7) | 190, 4e-05 | 201, 4e-05 | 2x holm twin folds | NULL |
| `H-NOMECH.hit.wrc_rel` | deb11:debuted | 782 | -0.00068 (0.00499) | -0.00297 | 0.00018 (0.00293) | -0.0002 | 3/11 (7) | 194, 4e-05 | 142, 3e-05 | 2x blk holm twin folds | NULL |

#### P-NOMECH (106 arms, alpha 0.005)

| arm | frame:scope | n scored | rho d (sd) | block-rho d | AUC d (sd) | twin rho d | folds | Holm rho (rank, alpha) | Holm AUC (rank, alpha) | failed | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `P-NOMECH.pit.bonus_log` | deb11:debuted | 907 | -0.00984 (0.00712) | -0.00868 | -0.00596 (0.00362) | -0.00807 | 2/11 (7) | 175, 0.00013 | 185, 0.00018 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.career_bf` | deb11:debuted | 907 | -0.01095 (0.0083) | -0.00013 | -0.00659 (0.00409) | -0.01309 | 5/11 (7) | 169, 0.00011 | 184, 0.00017 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.career_bf@readable` | deb11:readable | 768 | -0.00763 (0.01338) | 0.00491 | -0.00614 (0.00763) | 0.00426 | 5/9 (6) | 127, 6e-05 | 144, 7e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.career_ip` | deb11:debuted | 907 | -0.01102 (0.00842) | 0.00034 | -0.00652 (0.0041) | -0.01355 | 5/11 (7) | 167, 0.00011 | 182, 0.00016 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.career_ip@readable` | deb11:readable | 768 | -0.00818 (0.01349) | 0.00383 | -0.00639 (0.00764) | -0.00134 | 4/9 (6) | 132, 6e-05 | 145, 7e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.career_ip_ge_300` | deb11:debuted | 907 | 0.00033 (0.00729) | -0.0 | -0.00115 (0.00388) | -0.00536 | 3/11 (7) | 74, 4e-05 | 108, 5e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.career_ip_ge_300@readable` | deb11:readable | 768 | 0.00484 (0.00904) | 0.00667 | 0.00215 (0.00484) | -0.0127 | 7/9 (6) | 21, 3e-05 | 25, 3e-05 | 2x holm | NULL |
| `P-NOMECH.pit.career_ip_ge_400` | deb11:debuted | 907 | 0.00473 (0.00647) | 0.00347 | 0.00021 (0.00296) | -0.00665 | 4/11 (7) | 10, 2e-05 | 66, 3e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.career_ip_ge_400@readable` | deb11:readable | 768 | 0.0099 (0.00855) | 0.00871 | 0.00285 (0.00413) | 0.00335 | 5/9 (6) | 1, 2e-05 | 15, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.career_ip_ge_500` | deb11:debuted | 907 | 0.00275 (0.00354) | 0.00352 | 0.00032 (0.00164) | -0.00064 | 5/11 (7) | 8, 2e-05 | 47, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.career_ip_ge_500@readable` | deb11:readable | 768 | 0.00378 (0.00463) | 0.00389 | 0.0005 (0.00231) | 0.00413 | 5/9 (6) | 6, 2e-05 | 44, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.career_so` | deb11:debuted | 907 | -0.01347 (0.0081) | -0.00028 | -0.00751 (0.004) | -0.00201 | 5/11 (7) | 186, 0.00019 | 189, 0.00021 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.career_so@readable` | deb11:readable | 768 | -0.01051 (0.01229) | 0.00166 | -0.00693 (0.00665) | 0.00168 | 5/9 (6) | 147, 8e-05 | 153, 8e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.cat_back@debuted_observable` | deb11:debuted_observable | 564 | 0.00403 (0.00524) | 0.0031 | -0.00239 (0.00249) | -0.00153 | 2/5 (4) | 9, 2e-05 | 150, 8e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.cat_back@full_observable` | deb11:full_observable | 1084 | 0.0031 (0.00603) | 0.00171 | -0.00083 (0.00246) | -0.0001 | 4/5 (4) | 22, 3e-05 | 113, 5e-05 | 2x holm | NULL |
| `P-NOMECH.pit.cat_elbow@debuted_observable` | deb11:debuted_observable | 564 | -0.00267 (0.00713) | -0.00288 | -0.00014 (0.00365) | -0.00141 | 1/5 (4) | 118, 5e-05 | 80, 4e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.cat_elbow@full_observable` | deb11:full_observable | 1084 | -0.00135 (0.00606) | -0.00102 | -0.00048 (0.00381) | -0.00123 | 4/5 (4) | 105, 5e-05 | 93, 4e-05 | 2x blk holm twin | NULL |
| `P-NOMECH.pit.cat_forearm@debuted_observable` | deb11:debuted_observable | 564 | 0.00267 (0.00943) | 0.00054 | 0.00036 (0.0061) | 0.00728 | 3/5 (4) | 38, 3e-05 | 69, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.cat_forearm@full_observable` | deb11:full_observable | 1084 | 0.00363 (0.00616) | 0.00251 | 0.00062 (0.00361) | 5e-05 | 5/5 (4) | 18, 3e-05 | 48, 3e-05 | 2x holm | NULL |
| `P-NOMECH.pit.cat_lat@debuted_observable` | deb11:debuted_observable | 564 | 0.00534 (0.012) | 0.00506 | 0.00453 (0.00631) | 0.00034 | 3/5 (4) | 24, 3e-05 | 11, 2e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.cat_lat@full_observable` | deb11:full_observable | 1084 | 0.003 (0.00938) | 0.00085 | 0.00441 (0.00669) | 0.00407 | 3/5 (4) | 35, 3e-05 | 16, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.cat_oblique@debuted_observable` | deb11:debuted_observable | 564 | 0.00046 (0.00677) | 0.00285 | -0.00143 (0.0034) | -0.00027 | 2/5 (4) | 67, 3e-05 | 120, 5e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.cat_oblique@full_observable` | deb11:full_observable | 1084 | 0.00084 (0.00534) | 0.00203 | -0.00077 (0.00212) | 0.00034 | 4/5 (4) | 51, 3e-05 | 116, 5e-05 | 2x holm twin | NULL |
| `P-NOMECH.pit.cat_shoulder@debuted_observable` | deb11:debuted_observable | 564 | -0.00371 (0.00674) | -0.0045 | 0.0039 (0.00398) | -0.00536 | 3/5 (4) | 126, 6e-05 | 2, 2e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.cat_shoulder@full_observable` | deb11:full_observable | 1084 | 0.00248 (0.00663) | 0.00108 | -0.00085 (0.00306) | 0.00014 | 1/5 (4) | 32, 3e-05 | 107, 5e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.cat_wrist@full_observable` | deb11:full_observable | 1084 | -0.00084 (0.00428) | -0.00178 | -0.00107 (0.00217) | 0.0006 | 0/5 (4) | 104, 5e-05 | 123, 6e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.durable_zero_il@debuted_observable` | deb11:debuted_observable | 564 | -0.00433 (0.01265) | 0.00083 | 0.0 (0.00725) | -0.0165 | 2/5 (4) | 114, 5e-05 | 77, 4e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.durable_zero_il@full_observable` | deb11:full_observable | 1084 | 0.00395 (0.00926) | 3e-05 | 0.00212 (0.00516) | -0.00135 | 2/5 (4) | 28, 3e-05 | 29, 3e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.eta_delta@deb6` | deb6:debuted | 642 | 0.00274 (0.00812) | -0.00046 | 0.00441 (0.00511) | 0.00131 | 3/6 (4) | 34, 3e-05 | 4, 2e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.fv_stddev` | deb11:debuted | 907 | -0.00098 (0.00718) | -0.00032 | -0.00151 (0.00407) | -0.00068 | 3/11 (7) | 94, 4e-05 | 117, 5e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.fv_trend` | deb11:debuted | 907 | -0.00827 (0.00968) | -0.00632 | 0.00184 (0.0061) | -0.0031 | 6/11 (7) | 146, 7e-05 | 37, 3e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.health_index_oof@debuted_observable` | deb11:debuted_observable | 564 | -0.11006 (0.06175) | -0.0906 | -0.09112 (0.04157) | -0.00023 | 2/5 (4) | 188, 0.0002 | 195, 0.00028 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.health_index_oof@full_observable` | deb11:full_observable | 1084 | -0.01315 (0.04268) | -0.03995 | -0.06546 (0.03134) | -0.00123 | 3/5 (4) | 111, 5e-05 | 193, 0.00025 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.height_in@deb6` | deb6:debuted | 642 | -0.00964 (0.00691) | -0.00089 | -0.0026 (0.00362) | -2e-05 | 3/6 (4) | 177, 0.00014 | 141, 7e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_60day@debuted_observable` | deb11:debuted_observable | 564 | -0.01135 (0.01247) | -0.01317 | -0.0079 (0.00881) | -0.01168 | 2/5 (4) | 149, 8e-05 | 148, 8e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_60day@full_observable` | deb11:full_observable | 1084 | -0.0055 (0.00838) | -0.00831 | -0.00754 (0.00743) | -0.00059 | 1/5 (4) | 137, 7e-05 | 151, 8e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_days@debuted_observable` | deb11:debuted_observable | 564 | 0.00495 (0.01395) | 0.00761 | 0.00473 (0.00664) | 0.0033 | 3/5 (4) | 33, 3e-05 | 13, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_days@full_observable` | deb11:full_observable | 1084 | 0.00213 (0.00853) | 0.00633 | 0.0006 (0.00465) | -0.00216 | 3/5 (4) | 41, 3e-05 | 57, 3e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.il_days_ge_120@debuted_observable` | deb11:debuted_observable | 564 | 0.00205 (0.01488) | 0.00229 | 0.00669 (0.00787) | -0.00261 | 2/5 (4) | 54, 3e-05 | 5, 2e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.il_days_ge_120@full_observable` | deb11:full_observable | 1084 | -0.00168 (0.00908) | 0.00152 | 0.00051 (0.00502) | -0.00215 | 2/5 (4) | 102, 5e-05 | 64, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_days_ge_180@debuted_observable` | deb11:debuted_observable | 564 | 0.00199 (0.01426) | -6e-05 | 0.00496 (0.00692) | 0.00043 | 3/5 (4) | 53, 3e-05 | 12, 2e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_days_ge_180@full_observable` | deb11:full_observable | 1084 | -0.00288 (0.00956) | 0.00053 | -0.00038 (0.00511) | 0.00153 | 2/5 (4) | 109, 5e-05 | 88, 4e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_days_ge_30@debuted_observable` | deb11:debuted_observable | 564 | -0.00154 (0.01226) | 0.0044 | 0.00221 (0.00728) | 0.00487 | 4/5 (4) | 92, 4e-05 | 36, 3e-05 | 2x holm twin | NULL |
| `P-NOMECH.pit.il_days_ge_30@full_observable` | deb11:full_observable | 1084 | 0.001 (0.00832) | -0.00222 | 0.00043 (0.00414) | 0.00032 | 1/5 (4) | 59, 3e-05 | 62, 3e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_days_ge_60@debuted_observable` | deb11:debuted_observable | 564 | 0.00073 (0.01452) | 0.00016 | 0.00556 (0.00851) | 0.00129 | 2/5 (4) | 73, 4e-05 | 17, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_days_ge_60@full_observable` | deb11:full_observable | 1084 | -0.00166 (0.009) | 0.00196 | -0.00023 (0.00487) | 7e-05 | 3/5 (4) | 101, 4e-05 | 82, 4e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_days_ge_90@debuted_observable` | deb11:debuted_observable | 564 | 0.00197 (0.01473) | 0.00458 | 0.00422 (0.00787) | -0.00256 | 4/5 (4) | 56, 3e-05 | 20, 3e-05 | 2x holm | NULL |
| `P-NOMECH.pit.il_days_ge_90@full_observable` | deb11:full_observable | 1084 | -0.00062 (0.0087) | 0.00329 | -0.00028 (0.00459) | 0.00041 | 3/5 (4) | 87, 4e-05 | 86, 4e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_fullseason@full_observable` | deb11:full_observable | 1084 | 9e-05 (0.00085) | 1e-05 | 6e-05 (0.00059) | -0.00083 | 1/5 (4) | 61, 3e-05 | 63, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_max_stint_days@debuted_observable` | deb11:debuted_observable | 564 | 0.00584 (0.01329) | 0.00898 | 0.00495 (0.00635) | -0.0054 | 4/5 (4) | 26, 3e-05 | 7, 2e-05 | 2x holm | NULL |
| `P-NOMECH.pit.il_max_stint_days@full_observable` | deb11:full_observable | 1084 | 0.00305 (0.00808) | 0.00673 | 0.00112 (0.00438) | 0.00046 | 4/5 (4) | 30, 3e-05 | 40, 3e-05 | 2x holm | NULL |
| `P-NOMECH.pit.il_open_at_decision@debuted_observable` | deb11:debuted_observable | 564 | -0.00041 (0.01112) | 0.00524 | 0.00205 (0.00548) | 0.00168 | 3/5 (4) | 79, 4e-05 | 31, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_open_at_decision@full_observable` | deb11:full_observable | 1084 | -0.00089 (0.00831) | 0.00246 | 0.00077 (0.00457) | -0.00046 | 3/5 (4) | 90, 4e-05 | 50, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_stints@debuted_observable` | deb11:debuted_observable | 564 | -0.00599 (0.01212) | -0.0053 | 0.00167 (0.00714) | -0.0005 | 2/5 (4) | 124, 6e-05 | 42, 3e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_stints@full_observable` | deb11:full_observable | 1084 | -0.0034 (0.00842) | 0.00177 | -0.00134 (0.00405) | 0.00026 | 2/5 (4) | 119, 5e-05 | 112, 5e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_stints_ge_2@debuted_observable` | deb11:debuted_observable | 564 | -0.00658 (0.01553) | -0.00937 | 0.00661 (0.00932) | 0.00189 | 1/5 (4) | 121, 5e-05 | 14, 3e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_stints_ge_2@full_observable` | deb11:full_observable | 1084 | -0.00701 (0.01012) | 0.00022 | -0.00076 (0.00548) | -0.00074 | 1/5 (4) | 139, 7e-05 | 95, 4e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_stints_ge_3@debuted_observable` | deb11:debuted_observable | 564 | -0.01384 (0.01285) | -0.0189 | -0.00096 (0.00613) | -0.00298 | 0/5 (4) | 157, 9e-05 | 97, 4e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_stints_ge_3@full_observable` | deb11:full_observable | 1084 | -0.00758 (0.01056) | -0.00026 | -0.00388 (0.00527) | -0.0017 | 1/5 (4) | 140, 7e-05 | 142, 7e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.il_stints_ge_4@debuted_observable` | deb11:debuted_observable | 564 | -0.00047 (0.00974) | 0.00483 | 0.00065 (0.00433) | -0.00273 | 3/5 (4) | 83, 4e-05 | 52, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.il_stints_ge_4@full_observable` | deb11:full_observable | 1084 | -0.00012 (0.00761) | 0.00256 | -0.00132 (0.00364) | -0.00591 | 3/5 (4) | 78, 4e-05 | 115, 5e-05 | 2x holm folds | NULL |
| `P-NOMECH.pit.is_lhp` | deb11:debuted | 907 | -0.02074 (0.0107) | -0.01544 | -0.00637 (0.00472) | -0.00641 | 4/11 (7) | 191, 0.00023 | 172, 0.00012 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.joint__all_products` | deb11:debuted | 907 | -0.10251 (0.02419) | -0.07013 | -0.04003 (0.01621) | -0.00284 | 3/11 (7) | 212, 0.005 | 199, 0.00036 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.level_rank` | deb11:debuted | 907 | -0.006 (0.00396) | 0.00059 | -0.00257 (0.00215) | -0.00366 | 6/11 (7) | 180, 0.00015 | 163, 0.0001 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_bf` | deb11:debuted | 907 | -0.00656 (0.00453) | 4e-05 | -0.00258 (0.00237) | -0.00369 | 5/11 (7) | 178, 0.00014 | 158, 9e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_bf@readable` | deb11:readable | 768 | -0.00052 (0.00664) | 0.00171 | 0.00057 (0.00337) | -0.00052 | 3/9 (6) | 89, 4e-05 | 49, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_ip` | deb11:debuted | 907 | -0.00689 (0.00465) | 0.00029 | -0.0026 (0.00244) | -0.00281 | 5/11 (7) | 179, 0.00015 | 156, 9e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_ip@readable` | deb11:readable | 768 | -0.00432 (0.00685) | -0.0018 | -0.00203 (0.00345) | -6e-05 | 4/9 (6) | 134, 6e-05 | 131, 6e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_ip_ge_100` | deb11:debuted | 907 | -0.01425 (0.00596) | -0.00339 | -0.00535 (0.00316) | -0.00465 | 5/11 (7) | 197, 0.00031 | 187, 0.00019 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_ip_ge_100@readable` | deb11:readable | 768 | -0.00974 (0.0076) | -0.0035 | -0.00296 (0.00386) | 0.00091 | 4/9 (6) | 166, 0.00011 | 143, 7e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_ip_ge_130` | deb11:debuted | 907 | -0.00103 (0.00636) | 0.00072 | -0.00046 (0.00275) | 0.0018 | 7/11 (7) | 98, 4e-05 | 99, 4e-05 | 2x holm twin | NULL |
| `P-NOMECH.pit.max_ip_ge_130@readable` | deb11:readable | 768 | 0.00084 (0.00785) | 0.00158 | -0.00022 (0.00377) | -0.00383 | 6/9 (6) | 60, 3e-05 | 84, 4e-05 | 2x holm twin | NULL |
| `P-NOMECH.pit.max_ip_ge_150` | deb11:debuted | 907 | 0.00112 (0.00509) | 0.00067 | 0.00012 (0.00281) | -0.00532 | 6/11 (7) | 43, 3e-05 | 75, 4e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_ip_ge_150@readable` | deb11:readable | 768 | 0.00043 (0.00653) | -0.00062 | 0.00019 (0.00364) | -0.00224 | 5/9 (6) | 68, 3e-05 | 72, 4e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_so` | deb11:debuted | 907 | -0.00631 (0.00479) | 0.00242 | -0.00166 (0.00288) | 0.00592 | 5/11 (7) | 168, 0.00011 | 128, 6e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_so@readable` | deb11:readable | 768 | -0.00405 (0.0066) | -0.00029 | -0.00017 (0.00405) | 0.00029 | 5/9 (6) | 133, 6e-05 | 81, 4e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_so_ge_120` | deb11:debuted | 907 | -0.00614 (0.00543) | -0.00103 | -0.00093 (0.00349) | -0.00242 | 5/11 (7) | 162, 0.0001 | 106, 5e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_so_ge_120@readable` | deb11:readable | 768 | 0.00088 (0.00692) | 0.00384 | 0.00206 (0.00409) | -0.00284 | 4/9 (6) | 58, 3e-05 | 23, 3e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_so_ge_150` | deb11:debuted | 907 | -0.00084 (0.00783) | -0.00119 | 0.00024 (0.00456) | -0.00109 | 4/11 (7) | 91, 4e-05 | 71, 4e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.max_so_ge_150@readable` | deb11:readable | 768 | 0.00375 (0.00854) | 0.00301 | 0.00432 (0.00473) | 0.00787 | 6/9 (6) | 27, 3e-05 | 3, 2e-05 | 2x holm twin | NULL |
| `P-NOMECH.pit.max_so_ge_180` | deb11:debuted | 907 | -0.00107 (0.00185) | 4e-05 | -0.00119 (0.00114) | -0.0026 | 4/11 (7) | 129, 6e-05 | 154, 8e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.max_so_ge_180@readable` | deb11:readable | 768 | -0.00086 (0.00284) | -0.00015 | -0.001 (0.00145) | 0.00074 | 3/9 (6) | 110, 5e-05 | 138, 7e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.milb_readable` | deb11:debuted | 907 | -0.00645 (0.00402) | -1e-05 | -0.00266 (0.00214) | -0.00146 | 6/11 (7) | 183, 0.00017 | 164, 0.0001 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.milb_seasons` | deb11:debuted | 907 | -0.00964 (0.00859) | -3e-05 | -0.00602 (0.00449) | -0.00168 | 5/11 (7) | 160, 9e-05 | 171, 0.00012 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.milb_seasons@readable` | deb11:readable | 768 | -0.00583 (0.01103) | 0.00816 | -0.00375 (0.00586) | 0.00364 | 5/9 (6) | 125, 6e-05 | 135, 6e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.n_sources` | deb11:debuted | 907 | -0.00674 (0.00603) | -0.00059 | -0.00419 (0.00372) | 0.0004 | 5/11 (7) | 159, 9e-05 | 161, 0.0001 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.pick_overall` | deb11:debuted | 907 | -0.00455 (0.00781) | -0.00138 | 0.0023 (0.00421) | 0.00692 | 8/11 (7) | 130, 6e-05 | 19, 3e-05 | 2x blk holm twin | NULL |
| `P-NOMECH.pit.prod_trend` | deb11:debuted | 907 | -0.00091 (0.00485) | 0.00094 | -0.00118 (0.00258) | 0.00405 | 4/11 (7) | 103, 5e-05 | 122, 5e-05 | 2x holm twin folds | NULL |
| `P-NOMECH.pit.product__bb_rel` | deb11:debuted | 907 | -0.08661 (0.02745) | -0.05255 | -0.02879 (0.01489) | -0.0099 | 1/11 (7) | 204, 0.00056 | 190, 0.00022 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.product__k_rel` | deb11:debuted | 907 | -0.08878 (0.02643) | -0.0647 | -0.04498 (0.01573) | -0.00657 | 4/11 (7) | 205, 0.00063 | 203, 0.0005 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.product__peak_k_rel` | deb11:debuted | 907 | -0.05918 (0.02561) | -0.04825 | -0.02921 (0.01486) | -0.00512 | 5/11 (7) | 196, 0.00029 | 192, 0.00024 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.product__x_era_k` | deb11:debuted | 907 | -0.09397 (0.02359) | -0.07167 | -0.0546 (0.01514) | -0.00232 | 1/11 (7) | 209, 0.00125 | 208, 0.001 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.replace__age_rel_level_by_products-drop-age_rel_level` | deb11:debuted | 907 | -0.0943 (0.02336) | -0.05949 | -0.03326 (0.01523) | -0.0098 | 3/11 (7) | 210, 0.00167 | 194, 0.00026 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.risk_ord@deb6` | deb6:debuted | 642 | -0.00213 (0.01508) | 0.00177 | -0.00046 (0.00758) | -0.00717 | 4/6 (4) | 96, 4e-05 | 85, 4e-05 | 2x holm twin | NULL |
| `P-NOMECH.pit.so_per_150ip_peak` | deb11:debuted | 907 | -0.00584 (0.00425) | -0.00021 | -0.00238 (0.00226) | -0.00095 | 5/11 (7) | 174, 0.00013 | 155, 9e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.so_per_150ip_peak@readable` | deb11:readable | 768 | 0.00042 (0.00495) | -0.00098 | -0.00048 (0.00274) | -0.00108 | 4/9 (6) | 65, 3e-05 | 100, 4e-05 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.split__bb_rel` | deb11:debuted | 907 | -0.05415 (0.02027) | -0.04076 | -0.03618 (0.01286) | -0.004 | 2/11 (7) | 200, 0.00038 | 202, 0.00045 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.split__k_rel` | deb11:debuted | 907 | -0.04758 (0.0193) | -0.02916 | -0.01587 (0.01175) | -0.00913 | 5/11 (7) | 198, 0.00033 | 173, 0.00013 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.split__peak_k_rel` | deb11:debuted | 907 | -0.07363 (0.02045) | -0.05226 | -0.03371 (0.01233) | -0.0092 | 5/11 (7) | 207, 0.00083 | 201, 0.00042 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.split__x_era_k` | deb11:debuted | 907 | -0.09537 (0.02285) | -0.06513 | -0.05403 (0.01536) | -0.00754 | 2/11 (7) | 211, 0.0025 | 206, 0.00071 | 2x blk auc holm twin folds | NULL |
| `P-NOMECH.pit.tommy_john@debuted_observable` | deb11:debuted_observable | 564 | 0.00215 (0.01066) | 0.00478 | 0.00022 (0.00404) | -0.00292 | 4/5 (4) | 46, 3e-05 | 70, 3e-05 | 2x holm | NULL |
| `P-NOMECH.pit.tommy_john@full_observable` | deb11:full_observable | 1084 | 0.0022 (0.00779) | 0.00214 | 3e-05 (0.0035) | -6e-05 | 4/5 (4) | 39, 3e-05 | 76, 4e-05 | 2x holm | NULL |
| `P-NOMECH.pit.tool_gap@deb6` | deb6:debuted | 642 | -0.01026 (0.0067) | -0.00309 | -0.00491 (0.00354) | -0.00272 | 3/6 (4) | 181, 0.00016 | 176, 0.00014 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.weight@deb6` | deb6:debuted | 642 | -0.00933 (0.00697) | -0.00029 | -0.0023 (0.00351) | -0.00171 | 4/6 (4) | 170, 0.00012 | 136, 6e-05 | 2x blk holm twin | NULL |
| `P-NOMECH.pit.workload_and_missing_bats` | deb11:debuted | 907 | -0.00725 (0.00701) | -0.00357 | -0.00491 (0.00395) | -0.00209 | 3/11 (7) | 152, 8e-05 | 165, 0.0001 | 2x blk holm twin folds | NULL |
| `P-NOMECH.pit.workload_and_missing_bats@readable` | deb11:readable | 768 | 0.00109 (0.00815) | 0.00236 | 0.00088 (0.00408) | -0.00275 | 5/9 (6) | 55, 3e-05 | 45, 3e-05 | 2x holm twin folds | NULL |

#### ABL (21 arms, alpha 0.05)

| arm | frame:scope | n scored | rho d (sd) | block-rho d | AUC d (sd) | twin rho d | folds | Holm rho (rank, alpha) | Holm AUC (rank, alpha) | failed | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ABL.hit.drop-age` | deb11:debuted | 782 | -0.00015 (0.00697) | 0.00045 | -0.00021 (0.0036) | -0.00193 | 4/11 (7) | 10, 0.00152 | 11, 0.00156 | 2x holm twin folds | NULL |
| `ABL.hit.drop-age_rel_level` | deb11:debuted | 782 | -0.00042 (0.00563) | 0.00286 | -0.00062 (0.00305) | 0.0005 | 6/11 (7) | 14, 0.00172 | 18, 0.002 | 2x holm twin folds | NULL |
| `ABL.hit.drop-is_college` | deb11:debuted | 782 | -0.01477 (0.0099) | -0.01322 | -0.00852 (0.00587) | -0.01518 | 2/11 (7) | 41, 0.025 | 39, 0.0125 | 2x blk auc holm twin folds | NULL |
| `ABL.hit.drop-is_ifa` | deb11:debuted | 782 | -0.00042 (0.00548) | -0.00043 | 0.00121 (0.00319) | -0.00837 | 5/11 (7) | 15, 0.00179 | 3, 0.00125 | 2x blk holm folds | NULL |
| `ABL.hit.drop-k_rel` | deb11:debuted | 782 | -0.00025 (0.00413) | 0.00025 | 0.00078 (0.0024) | -0.00139 | 5/11 (7) | 12, 0.00161 | 5, 0.00132 | 2x holm twin folds | NULL |
| `ABL.hit.drop-level_rank` | deb11:debuted | 782 | 0.00142 (0.00451) | 0.00206 | 0.00045 (0.00231) | -0.00134 | 6/11 (7) | 6, 0.00135 | 7, 0.00139 | 2x holm twin folds | NULL |
| `ABL.hit.drop-milb_missing` | deb11:debuted | 782 | -0.00112 (0.00124) | -0.00222 | -0.00059 (0.00085) | -0.00236 | 0/11 (7) | 36, 0.00714 | 33, 0.005 | 2x blk holm twin folds | NULL |
| `ABL.hit.drop-n_milb_seasons` | deb11:debuted | 782 | -0.0058 (0.00712) | -0.00465 | -0.00238 (0.00379) | -0.00594 | 3/11 (7) | 35, 0.00625 | 31, 0.00417 | 2x blk holm twin folds | NULL |
| `ABL.hit.drop-obp_rel` | deb11:debuted | 782 | -0.00267 (0.00459) | 0.00216 | -0.00077 (0.00253) | -0.00311 | 5/11 (7) | 27, 0.00313 | 21, 0.00227 | 2x holm twin folds | NULL |
| `ABL.hit.drop-ops_rel` | deb11:debuted | 782 | 0.00133 (0.00365) | 0.00377 | 0.00033 (0.00211) | 0.00152 | 6/11 (7) | 4, 0.00128 | 8, 0.00143 | 2x holm twin folds | NULL |
| `ABL.hit.drop-peak_k_rel` | deb11:debuted | 782 | -1e-05 (0.0043) | 0.00074 | -0.00015 (0.00242) | 0.0001 | 5/11 (7) | 9, 0.00147 | 13, 0.00167 | 2x holm twin folds | NULL |
| `ABL.hit.drop-tool_hit` | deb11:debuted | 782 | 0.00543 (0.01135) | -0.00534 | 0.00584 (0.00671) | -0.00267 | 6/11 (7) | 2, 0.00122 | 1, 0.00119 | 2x blk holm folds | NULL |
| `ABL.hit.drop-tool_speed` | deb11:debuted | 782 | -0.00309 (0.00589) | -0.00239 | -0.00148 (0.00345) | -0.00754 | 3/11 (7) | 26, 0.00294 | 25, 0.00278 | 2x blk holm folds | NULL |
| `ABL.pit.drop-age` | deb11:debuted | 907 | -0.00174 (0.00547) | -0.00088 | -0.00228 (0.00345) | -0.00209 | 4/11 (7) | 22, 0.00238 | 32, 0.00455 | 2x blk holm twin folds | NULL |
| `ABL.pit.drop-age_rel_level` | deb11:debuted | 907 | -0.00045 (0.00446) | 0.00091 | -0.00051 (0.00223) | -0.00935 | 5/11 (7) | 16, 0.00185 | 19, 0.00208 | 2x holm folds | NULL |
| `ABL.pit.drop-bb_rel` | deb11:debuted | 907 | -0.01215 (0.00769) | -0.00304 | -0.00468 (0.00452) | -0.01316 | 3/11 (7) | 42, 0.05 | 38, 0.01 | 2x blk holm twin folds | NULL |
| `ABL.pit.drop-k_rel` | deb11:debuted | 907 | -0.00387 (0.00656) | -0.00211 | -0.0038 (0.00401) | -0.00828 | 4/11 (7) | 29, 0.00357 | 37, 0.00833 | 2x blk holm twin folds | NULL |
| `ABL.pit.drop-peak_k_rel` | deb11:debuted | 907 | -0.0006 (0.00519) | -0.00017 | -0.00075 (0.00321) | -0.00171 | 5/11 (7) | 17, 0.00192 | 20, 0.00217 | 2x blk holm twin folds | NULL |
| `ABL.pit.drop-seasons_at_level` | deb11:debuted | 907 | -0.00954 (0.0064) | -0.00128 | -0.00154 (0.00359) | -0.01355 | 4/11 (7) | 40, 0.01667 | 24, 0.00263 | 2x blk holm twin folds | NULL |
| `ABL.pit.drop-tool_fb` | deb11:debuted | 907 | -0.00261 (0.00636) | 0.00296 | -0.00201 (0.00339) | -0.0066 | 6/11 (7) | 23, 0.0025 | 30, 0.00385 | 2x holm twin folds | NULL |
| `ABL.pit.drop-x_era_k` | deb11:debuted | 907 | -0.00328 (0.0056) | -0.00366 | -0.00244 (0.00317) | -0.01484 | 3/11 (7) | 28, 0.00333 | 34, 0.00556 | 2x blk holm folds | NULL |

### R7. Kill rules, as they stand after the run

1. Frozen list: the run read the committed list (sha256 above) and nothing else.
2. One read per arm: each of the 312 arms and the two liveness controls was read once, in one process; no arm was re-read.
3. No second family: everything nulled, so no second family may be drawn over these columns.
4. Uninformative family: fired in H-MECH only (R5).
5. Dead instrument: did not fire (R3).
6. Program close: nothing passed. **The driver frontier is RE-CLOSED on label build `fwar@2026-10-02-0341299c20ec`, 2026-10-04.** Kill rule 6, verbatim: "**Program close.** If nothing passes, record the frontier as RE-CLOSED on label build X, rewrite do-not-reopen items 1, 8 and 17 with the date, and allow no driver re-test until either the 2027 RT advance or an owner-registered label DEFINITION change that moves the debuted label more than this one did (Spearman under 0.99 against the frozen label on either side)." Items 1, 8 and 17 of `docs/master-plan-2026-08-19-holistic-audit.md` section 2 are rewritten with the date in the same commit as this section.
7. Stale inputs: did not fire (R2, P4).
8. Denominator published: `python tools/efv_arm_ledger.py` regenerated `data/xfv_arm_ledger.json` with this registration as a new lane (`Z1 driver re-test (fWAR label)`, 312 arms): 392 arms across 9 lanes, 351 scoreable against a recorded floor, 0 at or above it on the point estimate.

The pre-registered expectation (section 8) was zero survivors; the run recorded zero. Section 0's suspension ends here: `CONVICTION_PROGRAM.md` stop clause 1 applies again in full. Section 5's confirmation leg has no passer and reads nothing. No served number moved.
