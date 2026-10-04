# Z1c: the pitcher-stuff first fold, one leg on the 2025 debut cohort (registration, 2026-10-03)

Registration status: DRAFT

Drafted 2026-10-03 on branch `efv-conviction-2026-08-08`. This file registers ONE leg: Z1c, the
pitcher-stuff first fold, read on the 2025 debut cohort inside the one Holm family of the eFV v2
registration (EV-12, `docs/efv-v2/EFV_V2_GATE.md`). It carries definitions, rules and dates
only. No row of any frame was read, built or counted to write it, and it states no number from
any frame.

**When it becomes REGISTERED.** This file is REGISTERED at the first commit at which both of
these hold: `docs/efv-v2/EFV_V2_GATE.md` carries its REGISTERED status line and names this file
as the Z1c counterpart of `docs/efv-v2/PROGRAM.md` section 4 clause (c); and this file's status
line reads REGISTERED with every pending item of section 9 filled. The status line change and
the pending items are committed ALONE, immediately before EV-12's commit, and EV-12's commit
names that commit. A DRAFT takes part in no look. Pinned by `test_z1c_registration.py` at the
module root.

## 1. Purpose and lineage

- **Clause (k).** `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` clause (k) lists, among the
  registrations downstream of the fWAR label epoch, "each its own registration, none of which
  changes a label and none of which rides this epoch", "**Z1c** the pitcher-stuff first fold".
  This is that registration. It changes no label and rides no epoch.
- **Plan section 2.7 item 8a.** `docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`
  section 2.7, item 8a: pitcher stuff "opens BY ITS OWN CLOCK if O2 bundles RT; own registration
  (Z1c), not Z1". The epoch admits the `RESOLVED_THROUGH` advance from 2025 to 2026 by owner
  decision (the gate's part 1, O1 and O2), so the clock item 8a names is the one this leg reads.
- **The clock.** Do-not-reopen item 8 (`docs/master-plan-2026-08-19-holistic-audit.md`
  section 2) reads "Pitcher stuff waits for the RESOLVED_THROUGH clock". This registration is
  the reopen that item names, and only that. `docs/efv-2026-08-13/PITCHER_STUFF_CLOCK.md`
  records why the clock binds: AAA pitch tracking begins in 2023, so the 2024 debut cohort is
  the first with pre-debut stuff coverage under the strict as-of rule, and test year 2025 is the
  first fold whose training rows carry the column at all.
- **Owner answer PROGRAM Q4 = A** (`docs/efv-v2/PROGRAM.md` section 6): "One joint registration
  with Z1c on the 2025 debut cohort, one Holm family, first look after the RT 2026 labels."
- **The revisit, PROGRAM-Q4-REVISIT** (2026-10-03, the recommended option taken under the
  owner's standing instruction of 2026-10-01; recorded in DECISIONS_FOR_OWNER.md in the
  `_audit_2026-09-09` folder beside the git root, under 'ANSWERED 2026-10-03 (standing
  instruction), PROGRAM-Q4-REVISIT (the Z1c leg)'). The Z1c leg cannot live inside Z1:
  `docs/efv-2026-10-03/LABEL_V3_DRIVER_RETEST_GATE.md` section 5 records that Z1's frame keeps
  the reserved 2025 base-year cohort out (plan section 2.4) and that Z1's list excludes pitcher
  stuff (item 8a). So Z1c gets this registration of its own, written before EV-12 commits, and
  it carries the owner's Q4 = A intent unchanged: one leg on the 2025 debut cohort, inside
  EV-12's one Holm family, first look after the RT 2026 labels on the registered R-VM schedule,
  never earlier. Option B (the 2026 debut cohort alone, first look at RT 2027) was rejected
  because it changes the owner's substantive choice.
- **The counterpart it completes.** `docs/efv-v2/PROGRAM.md` section 4 clause (c) asks EV-12 for
  "the Z1c and Z1-confirmation joint text (Q4)". The Z1-confirmation half is Z1's section 5,
  clauses C1 to C5. This file is the Z1c half, and section 5 below writes its leg in the shape
  of C1 to C5.

## 2. The frame

- **Rows.** The 2025 debut cohort, exactly as `docs/efv-v2/PROGRAM.md` section 2.4 defines the
  first cohort of R-VM ("F-VM prospective: the 2025 debut cohort (joint with Z1c, owner Q4)"),
  on the rows the R-VM look rule of `docs/efv-v2/EFV_V2_GATE.md` section 2.2 scores at R-VM
  look 1, pitcher side only, routed by the side rule EV-12 uses. This file states no count of
  it.
- **Outcome.** R-VM's outcome as `EFV_V2_GATE.md` section 2.2 states it: career WAR to date on
  the label frozen at the look, which after the epoch's step Z entry is the frozen fWAR label.
- **The guard stands.** `source_backtest.CANDIDATE_YEARS` and `efv_model.SCORED_YEARS` keep
  excluding 2025 and later until the R-VM look record exists (`PROGRAM.md` section 2.4, the
  R-VM guard and its test pin, `efv_vintage_frame.reserved_vm_pins`). The step of
  `PITCHER_STUFF_CLOCK.md` that extends `SCORED_YEARS` to 2025 is superseded for this cohort by
  this registration: the cohort is scored once per look, as this leg, and never as a training
  or development fold before its look.
- **Training rows.** The column's head is fit only on decision years before 2025, the folds the
  R-VM guard allows, on the frozen label.

## 3. The column the leg reads

- **Registered ids: none exist.** `data/xfv_arm_ledger.json` holds no pitcher-stuff arm.
  Driver System V2 (`docs/efv-v2/DRIVER_SYSTEM_V2.md` section 4.3) gives the pitcher skill head
  nothing by default, or the admitted K-rate residual, and names no stuff column. Z1's frozen
  list sets the E-STUFF lane aside (`docs/efv-2026-10-03/z1_arm_list.json`, `excluded_lanes`,
  artifact `xfv_pitcher_stuff_eval.json`, reason plan item 8a).
- **The leg is defined on a column that does not exist yet.** Its definition is the E-STUFF
  overlay, variant `both`, strict as-of convention, as `tools/efv_pitcher_stuff_lab.py` builds
  it inside its own lab run (`overlay_for`, `build_rows`): the in-house AAA aStuff+ per
  (pitcher, season), centered and zero when uncovered, with its coverage flag; the AAA
  swing-and-miss z within the season's qualified AAA pitcher pool, zero when uncovered, with
  its coverage flag; tracking seasons strictly before the debut year. The lab's local names
  (`x_astuff_c`, `x_astuff_has`, `x_whiff_z`, `x_whiff_has`) are not registered ids.
- **The producer named to create it.** The overlay builder of `tools/efv_pitcher_stuff_lab.py`,
  extended to write the column as a V2 pitcher input for the pitcher skill head of
  `efv_v2_model.py`, with the id it receives entered in `data/xfv_arm_ledger.json` by
  `tools/efv_arm_ledger.py`. Today that builder writes no column to any matrix or ledger.
- **One rule this file adds to the definition.** No input to the column is dated on or after
  the opening of the 2025 preseason window, and that includes the fit of the stuff model that
  scores the pitches. The shipped stuff model's fit window, which the E-STUFF artifact discloses
  under `method.astuff_selfscore_caveat` in `data/xfv_pitcher_stuff_eval.json`, does not meet
  it, so the producer fits the stuff model on earlier pitches for this column.
- **If the column never gets its id.** If no registered id exists when EV-12 commits, the leg
  does not enter EV-12's family and takes no look, and the Results section records VOID with
  that reason.

## 4. The statistic and its direction

- **Statistic.** The paired delta on the within (side, vintage) statistic of
  `docs/efv-v2/EFV_V2_GATE.md` section 3.1, which on this frame is one group, the pitchers of
  the 2025 debut cohort: the registered V2 pitcher order with the column minus the same order
  without it, each read against the frame's outcome on the same rows.
- **The two orders.** The order without the column is the V2 pitcher order EV-12 freezes
  (`docs/efv-v2/DRIVER_SYSTEM_V2.md` section 4.3). The order with it adds the column through
  the pitcher skill head of that section, the slot it gives a pitcher skill driver, with the
  head's slope fit on the training rows of section 2 and its weight fixed by the rule EV-12
  registers, before any read (section 9, pending item 2).
- **Direction.** One-sided: the leg passes only if the order with the column reads higher. A
  delta at or below zero is a failure.
- **Instrument and controls,** by reference to EV-12, as for every R-VM cell: E_refit with the
  paired, player-clustered resampler, B and seed of `EFV_V2_GATE.md` section 3.6; the
  zero-information twin (the column permuted within the cohort); the permutation null; mde95
  stated before the read; and the contributor-AUC veto of section 3.5, under which an adverse
  AUC beyond its floor is a failure. The claim is the one-sided lower bound, printed beside the
  point.
- **A test, not an admission.** The leg reads the column whether or not the DS-06 admission
  rule would admit it. DS-06 decides what a served candidate carries; a passed leg admits
  nothing by itself (section 7).

## 5. The leg in EV-12's one Holm family

Written in the shape of Z1's clauses C1 to C5 (`LABEL_V3_DRIVER_RETEST_GATE.md` section 5).

- (Z1c-1) *Frame.* Section 2. Z1 never reads it, and this leg reads it only inside its looks.
- (Z1c-2) *When.* Section 6: first at R-VM look 1, never earlier.
- (Z1c-3) *Statistic.* Section 4: one rho leg, one-sided.
- (Z1c-4) *Family.* The leg is read inside the one Holm family that PROGRAM Q4 = A names and
  EV-12 sizes when its status line changes. This leg adds exactly one to that family's m,
  beside Z1's confirmation legs (one per Z1 passer, Z1 section 5 clause C4) and EV-12's own
  legs. Its alpha share is the one EV-12's rule gives every leg of that family: Holm step-down
  at the look, inside the R-VM spending of `PROGRAM.md` section 4 clause (e). This file fixes
  no alpha, boundary or information fraction of its own; EV-12's look runner computes them and
  EV-12's commit writes them down (section 9, pending item 3).
- (Z1c-5) *Outcome.* A failed leg removes the column automatically: it enters no served
  candidate and no candidate of EV-12's, with no owner decision, no accuracy copy and no second
  attempt on this cohort. The leg fails on any of these: it does not clear its boundary by its
  final look; the AUC veto; its twin scores at least as well as the column (no result under
  `PROGRAM.md` section 4 kill rule 5, which for this leg counts as a failure); an early read
  (section 6). A passed leg changes nothing served by itself (section 7). No accuracy copy in
  either case.

## 6. The look

- **First look.** R-VM look 1: the first look after the RT 2026 labels on the R-VM schedule of
  `docs/efv-v2/PROGRAM.md` section 3.5, so not before 2026-12-01, after the PROSPECT_ANCHOR
  look, and after EV-12 is REGISTERED. It runs once, in R-VM's own session, through the look
  runner EV-13 names (not built at this draft).
- **Later looks.** If look 1 does not decide the leg, it is read again at R-VM look 2 (the RT
  2027 run) and at R-VM look 3 (the RT 2028 run, the final boundary), each once and in R-VM's
  session, on the same 2025-cohort rows with the label as frozen at that look. No other look
  exists.
- **Looking early disqualifies the leg.** Any read of the column against a 2025-cohort outcome
  before look 1, any build of the column on a 2025-cohort row outside a look session, a guard
  trip, or any score found on these rows before the look turns the leg VOID permanently, in the
  manner of `PROGRAM.md` section 4 kill rule 3, and the Results section records it.
- **Calendar.** The look never runs on another gate's registered look date (`docs/*GATE*.md`).

## 7. The serving consequence

None by itself. The leg feeds EV-12's decision: a passed leg is evidence that EV-12's decision
reads under its outcome table (`PROGRAM.md` section 4, 'What ships under each outcome'). A
served change needs EV-12's own decision, a new grade-basis epoch and the DS-06 admission of the
column. A failed leg removes the column (Z1c-5). No page, copy, registry row or served number
reads this file.

## 8. What this registration does not do

- It reads, builds and counts no row of R-LV or R-VM, and it states no number from any frame.
- It builds no column and runs no lab, exporter or fetch. Nothing under `data/` is written.
- It changes nothing in Z1 (`docs/efv-2026-10-03/LABEL_V3_DRIVER_RETEST_GATE.md`): not its
  frame, its families or its sha256-pinned arm list.
- It re-runs none of the 39 closed eFV feature arms and does not suspend CONVICTION_PROGRAM stop
  clause 1. The reopen it carries is do-not-reopen item 8's pitcher-stuff clock alone; the
  pre-Statcast proxies are Z1's (item 8b, P-MECH) and the K-prior stays closed permanently
  (item 8c).
- It computes no realized MLB statistic and no bust, debut or graduation rate by consensus-FV
  cell, and it groups nothing by FV level (`docs/PROSPECT_ANCHOR_GATE.md`).
- It changes no label, rides no epoch, and edits no clause and no part 9 entry of the fWAR gate.
- It moves no served number and adds no flag.

## 9. Pending items (filled in the commit that changes the status line)

1. The column's registered id (section 3).
2. The head arithmetic and the weight rule EV-12 registers for the column (section 4).
3. The family's m, this leg's place in Holm, and its boundary at each look, as EV-12's commit
   writes them (section 5).
4. The commit of EV-12 that names this file.

## Results

(Empty. Nothing is recorded here before the leg's first look.)
