# eFV v2 registration: EFV_V2_GATE

Registration status: REGISTERED

THIS IS A DRAFT (DS-15, `docs/efv-v2/DRIVER_SYSTEM_V2.md` s5). It is committed so its text is
dated before any development read of the assembled V2 (DS-16), not as the registration. The
registration preconditions in s1 are unmet: the fWAR label freeze has not happened (about
2026-10-05), the F-LV floors (EV-05) do not exist, and three program questions are open. A
draft cannot open the reserved guard: `efv_vintage_frame.gate_sha_committed` accepts a commit
only when this file at that commit carries a status line that reads exactly REGISTERED, alone
on its line, and no other status line (`gate_doc_registered`; `test_efv_v2_gate.py`). The
final commit changes that one status line, fills the pending items named below, and is
committed ALONE with the results section empty (PROGRAM.md s4).

Drafted 2026-09-25 on branch `efv-conviction-2026-08-08`. Owner answers DS-Q1 to DS-Q4
(2026-09-25) are binding and recorded in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`. No
em-dashes. No statistic in this document, its code or its planned artifacts is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`).

---

## 1. Preconditions (all must hold before the status line changes)

| id | precondition | state at this draft |
|---|---|---|
| P1 | fWAR label freeze receipt with per-side coverage (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`) | UNMET (freeze about 2026-10-05) |
| P2 | Floors: F-LV mde95 by E_refit and E_cond on dev vintages (EV-05, `data/efv_lv_floor.json`), F-VM floors re-derived on the frozen label, `w*` on the frozen label | UNMET |
| P3 | Parity: the v2 lab reproduces v1's `xfv_eval*.json` bit for bit with V2 switched off | UNMET (not built) |
| P4 | Input sha256 pins on matrices, frames, floors, `efv_v2_model.py`, `efv_v2_stat.py`, `data/efv_v2_assembly.json`, taken at registration | PARTIAL (draft-time pins in s4.6) |
| P5 | Frozen candidate: V2 as s4, its weights re-derived ONCE by the DS-08 rule on the frozen label, and DS-16 re-run ONCE on the frozen label as the registered development number | UNMET (rule and spec frozen here; numbers pending the label) |
| P6 | Owner answers to PROGRAM.md Q2 (what ships under a tie), Q3 (F-LV co-primary) and Q4 (the prospective cohort) | UNMET (DS-Q1 to DS-Q4 answered; PROGRAM Q2 to Q4 open) |
| P7 | The look runner (EV-13, `tools/efv_v2_look.py`) refuses without this file's REGISTERED commit sha, pins inputs at start and end, and refuses a spent look | UNMET (the guard it calls is built and tested; the runner is not) |

---

## 2. Frames

### 2.1 Development frames (spent; read only as development rows that adjudicate nothing)

- **lv_dev.** F-LV (EV-04, `efv_vintage_frame.py`) on list vintages 2011 to 2019
  (`DEV_VINTAGES`). One row per (player, list vintage V): every prospect with a real-grader
  preseason read in V who had not debuted. Inputs dated inside the V preseason window
  (Jan 1 to May 1), MiLB through V - 1 on the OUTCOME-BLIND identity (DS-03, bug B4). Label
  W3 (`efv_labels.py`): WAR over the first three MLB seasons, 0 if no debut within V..V+3.
  V2 is scored only on V 2017 to 2019 (the DS-08 rule reads years up to 2016).
- **vm_dev at frame version vm2.** F-VM (EV-01): debuted players graded at the preseason read
  of their debut year, every eFV input pinned inside the raters' own window; window 2017 to
  2023; outcome career WAR to date; the rows `source_backtest` builds for
  `accuracy.pooled_efv_common_vintage_matched_vm2`, less any row V2 cannot score.

lv_dev, vm1 and vm2 share most of their players; they are not independent replications.

### 2.2 Reserved frames (read once, after this file is REGISTERED)

- **R-LV.** F-LV list vintages 2020 and 2021 (`efv_vintage_frame.RESERVED_LV`). Only counts
  have been read on it (V 2020: 821 hit / 478 pit rows; V 2021: 906 / 462; [E2]). W3 for
  V 2021 resolves at the 2026 freeze. Disclosures: a vintage hold-out, not a player hold-out
  (many 2020-2021 list players sit in F-VM rows already read); its W3 seasons 2020 to 2026
  include seasons used as training labels for OTHER players; one exposure of
  R-LV-overlapping rows is recorded in s5 (B9a).
- **R-VM.** The 2025 debut cohort and later (`R_VM_FIRST_DEBUT_YEAR = 2025`), looks at RT 2026,
  2027, 2028 with O'Brien-Fleming spending (z 3.205 / 2.141 / 1.694, one-sided alpha 0.05;
  recomputed by the gate's tool before the status line changes). Pinned by
  `reserved_vm_pins()`: `source_backtest.CANDIDATE_YEARS` and `efv_model.SCORED_YEARS` may not
  include 2025 or later until its look record exists.
- **Amendment, dated 2026-10-03 (made while this file reads DRAFT): the Z1c half of PROGRAM.md
  s4 clause (c).** The counterpart of the "Z1c" half of the joint text (Q4) is Z1c's own
  registration, `docs/efv-2026-10-03/Z1C_PITCHER_STUFF_GATE.md` (owner decision
  PROGRAM-Q4-REVISIT): one leg on the 2025 debut cohort inside this registration's one Holm
  family.

#### R-VM look sizes, counted (amendment A6, dated 2026-10-02, made while this file reads DRAFT)

This draft carried no n for an R-VM look. `PROGRAM.md` s2.5 sized each cohort at "about 210"
(210 / 420 / 630; mde95 0.0596 and delta needed 0.116 at look 1) before anyone counted it. The
counted sizes, by `efv_rvm_look_n.cohort_counts` on `data/debuts.json` (sha256
1368e28c699a27d64ac2db46086de697343931e95343fa6b73d427f086a69367, 2,767 records, written 2026-10-02):

| look | debut cohorts | rule | hit | pit | n | mde95 | z | delta needed |
|---|---|---|---|---|---|---|---|---|
| look 1 | 2025 | vm2 | 74 | 75 | 149 | 0.0707 | 3.205 | 0.1378 |
| look 1 | 2025 | consensus_present | 80 | 96 | 176 | 0.0651 | 3.205 | 0.1268 |
| look 2 | 2025, 2026 (2026 counted to date) | vm2 | 141 | 144 | 285 | 0.0511 | 2.141 | 0.0666 |
| look 2 | 2025, 2026 (2026 counted to date) | consensus_present | 159 | 191 | 350 | 0.0462 | 2.141 | 0.0601 |
| look 3 | 2025 to 2027 (2027 projected at the 2025-2026 mean cohort) | vm2 | | | about 428 | 0.0417 | 1.694 | 0.0430 |
| look 3 | 2025 to 2027 (2027 projected at the 2025-2026 mean cohort) | consensus_present | | | about 525 | 0.0377 | 1.694 | 0.0388 |

- **The rules.** vm2: FanGraphs and MLB Pipeline (`source_backtest.SCORED_SOURCES`) both
  published a grade at a point inside the debut year's preseason window
  (`efv_vintage_frame.window_bounds`, closed at the debut day), the common-set rule of the
  headline frame. consensus_present: a point inside that window carries a consensus grade (the
  vm3 rule of LANE_A.md G2). The 2025 cohort holds 243 debuts (110 hit / 133 pit).
- **The rule the look uses: vm2, 149 rows at look 1.** Lane A's E3-Q1 is taken at its
  recommended option by default (2026-10-02): vm2 stays the headline frame; consensus_present
  is reported beside it and is never the claim. This is not the unified E3-Q1 of the EFV3 owner
  questions (scrap or keep V2, default C). 149 is the ceiling of the vm2 look: vm2 also drops a
  row eFV cannot score or whose pinned read falls outside the window (on 2017 to 2023 it kept
  829 of a both-source ceiling of 858, LANE_A.md s1.3).
- **The floors** are the gate's tool, `efv_rvm_look_n.mde95` and `delta_needed`: the [S]
  arithmetic of `PROGRAM.md` s2.5 ported unchanged (mde95 0.0303 at n 812, scaled by
  sqrt(812 / n); delta needed = z x 0.0303 / 1.645 x sqrt(812 / n)). At n 210 it returns [S]'s
  0.0596 and 0.1161 (`test_efv_v2_gate.py`). It scales the pooled E_refit floor of the
  vintage-matched frame; the within statistic's E_refit floor on R-VM is unmeasured. LANE_A.md
  s1.3 and the EFV3 plan (F1) printed 0.0705 / 0.0648 from another reference sd (E_refit 0.01844
  at n 802 to 806); the gate uses its own tool's figures. The z's are [S]'s for three equally
  spaced looks and are unchanged; the counted spacing is 149 / 285 / about 428 (information
  fractions 0.348 / 0.666 / 1 under vm2), and the gate's tool recomputes the boundaries at the
  realized fractions before the status line changes. The look-1 floor of 0.0596 printed in
  `DRIVER_SYSTEM_V2.md` (s3 and s4.4) is superseded by this table.
- **What was read.** Counts only, from each record's debut date, its points' snapshot dates,
  grade PRESENCE (never a grade value) and the side routing fields
  (`efv_dataset._rec_is_pitcher`). Whether a player was graded in his debut year's preseason
  window is fixed before that season's games. No R-VM outcome, WAR, label or score was read;
  `reserved_vm_pins()` returns [] at this amendment; no R-LV row was built; nothing is grouped
  by consensus-FV level; no arm was run.
- **The label epoch.** R-VM's outcome is career WAR to date on the label frozen at the look;
  the fWAR label epoch (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`) moves that label from
  eWAR v2 to fWAR before any look. These counts read no WAR and do not move with the label. A
  look row also needs an outcome row: 219 of the 243 2025 debuts carry a career_war row on the
  retiring eWAR v2 provider (presence only, `data/efv_label_pool_census.json`), and that join is
  the epoch's (E2), re-counted at its freeze, not this table's.
- **The file version.** `data/debuts.json` is a gitignored build artifact rebuilt nightly; the
  sha256 above names the version counted. `test_efv_v2_gate.py` re-counts the look-1 rows on
  the file on disk and holds each side within 5 rows of this table.

---

## 3. The statistic (owner answer DS-Q3)

### 3.1 Primary: within (side, vintage)

For every rater r and every group g = (side, vintage) with at least 20 rows of the
comparison (`efv_v2_stat.MIN_GROUP_ROWS`, the S1 convention):

    rho_g(r)     Spearman rho of r's OWN score against the outcome on the rows of g
                 (average ranks for ties); V2's own score is its order index
    within(r)    sum over kept groups of n_g * rho_g(r), divided by the sum of n_g

"Vintage" is the list vintage V on F-LV and R-LV, and the base year (the debut year) on
F-VM and R-VM. The delta is within(V2) minus within(consensus) on identical rows. In a
bootstrap draw a group whose rho is undefined for either rater leaves the draw for both.

### 3.2 Secondary: pooled, after the identical output map

Spearman rho over every row of the comparison of each rater's MAPPED score (s3.3). Reported
beside the primary on every frame; never the claim alone.

### 3.3 The identical output map for every rater

Inside each group, each rater's own score is ranked (ties averaged) onto that group's
consensus FV values, on the rows the comparison scores: `efv_v2_model.output_map`, the map
V2 uses to turn its order into a grade (DS-07), applied the same way to V2, eFV v1, PROSPX
consensus, MLB Pipeline and FanGraphs, for the pooled statistic and the AUC. Consensus maps
onto itself. Under the map every rater carries consensus's own level per group and differs
only in its order inside groups (bug B5: pooling separately fitted scales cost eFV 0.007 to
0.016). The map keeps a rater's order inside a group but can tie rows the rater separates
(consensus values repeat), so the within statistic reads each rater's own score and never
the mapped one; a per-group shift or any order-preserving change of a rater's scale leaves
it unchanged.

### 3.4 Disclosure: the statistic was chosen after two spent reads

The within statistic was chosen AFTER the spent vintage-matched frame vm1 showed it favours
eFV (v1 against consensus: pooled -0.0131, within +0.0058; lane I3) and AFTER
reconciliation S1 showed the same Pipeline ordering reading +0.018 against consensus within
(V, side) and -0.008 pooled after the map (n 5,646, V 2011-2019). The owner chose it on
2026-09-25 knowing both. Its justification is structural (under it the level map is a
no-op and a candidate competes on ordering alone, which is the only thing drivers can
change), and the pooled statistic is reported beside it on every read so a reader can see
whether the two disagree.

### 3.5 Contributor AUC (veto only)

Contributor AUC of the mapped score, pooled. Positives: career WAR at or above
`source_backtest.CONTRIBUTOR_WAR` (3.0) on F-VM and R-VM; on F-LV and R-LV, W3 at or above
`w*`, the W3 value whose exceedance share equals the six-season contributor share on
vintages 2011 to 2016 (labels only; 1.19 on the eWAR v2 label, re-derived on the frozen
label, P2). AUC can only veto (PROGRAM.md s2.1); it does not enlarge the Holm family.

### 3.6 Intervals

Paired, player-clustered bootstrap, `source_backtest`'s resampler (`_cluster_layout`,
`_cluster_draw`), B 2000, seed 20260906. The reserved claim uses E_refit (every head, the
admission rule and the map refit per draw) with E_cond beside it; development reads use
E_cond only (scores fixed, players resampled) and say so. The claim is the one-sided 95%
lower bound of the delta, printed beside the point; mde95 = 1.645 x SD of the drawn deltas.

---

## 4. The candidate: Driver System V2 (`efv_v2_model`, "DRIVER SYSTEM V2 assembly")

### 4.1 Order, grade, price

For one side s and one group (list vintage V, or debut year on F-VM):

    u_c        within-(s, V) percentile of the consensus FV (no fit)
    e_skill    skill head's driver sum over its own consensus slope
    e_time     timing (REACHED) head's logit driver sum over its own logit consensus slope
    order_idx  u_c + w_skill * e_skill + w_time * e_time
    eFV grade  consensus FV value of (s, V) at order_idx's within-group rank, ties averaged
    eFV WAR    continuous least-squares line of the training target on consensus FV,
               evaluated at the eFV grade (pricing only, never ranked)

The scored object on every frame is order_idx: the within statistic reads it directly, and
the map of s3.3 turns it into exactly the eFV grade for the pooled statistic and the AUC.

### 4.2 Heads and candidates

- Skill head (ridge, has-block rows only, target the W3 percentile within (s, V) on F-LV,
  the six-season target percentile on the matrices). Hitter candidates: obp_rel, contact
  (k_rel and peak_k_rel merged, sign flipped), tool_hit, tool_speed, is_college,
  level_rank, pl_rev. Pitcher candidates: k_rel (DS-10), bmi (one pre-declared re-test),
  pl_rev.
- Timing head (penalized logistic, target R3 on F-LV, debuted on the matrices): age_rel_level,
  level_rank; on outcome-blind ids only, also milb_absent (admitted by
  `data/efv_identity_balance.json`), on_40man and nov_add (DS-09).
- Missingness (DS-04): a row without a MiLB block carries None on every block key and is
  imputed at the has-block TRAIN mean; the absence flag never enters a skill head; sidecars
  impute at the observed train mean.
- Admission (DS-06), inside every fold on the fold's own training vintages: a driver enters
  only if its coefficient's sign held in every training vintage that gives a t (at least 60
  rows, at least 2 such vintages) and its mean |t| is at least 1.0.
- Penalties: grid 1, 3, 10, 30, 100, 300, 1000, infinity (infinity switches a head off),
  chosen by nested forward-chained CV on training years only.
- Pitchers (owner DS-Q2): the consensus order in any fold where no pitcher SKILL driver is
  admitted; the pitcher factor chips leave the board.
- Scrapped (DS-05, `efv_v2_model.V2_SCRAPPED`): the v1 pitcher block, hitter age,
  milb_missing, n_milb_seasons, ops_rel, is_ifa as a slope, the pinned 0.70 / 0.57 blend,
  the pooled output remap.

### 4.3 Weights (DS-08), fixed before any read of V2

The rule: pooled forward-chained OLS `u_y ~ 1 + u_c + e_skill + e_time` over rule years up to
2016 (v1 matrices and F-LV list vintages up to 2016); w = clip(coefficient / c_uc, 0, 1).
Values on the eWAR v2 label (`data/efv_v2_assembly.json`, generated before any V2 score):

| side | w_skill | w_time | a = w_time / w_skill | rule n | c_uc (SE) | c_skill (SE) | c_time (SE) |
|---|---|---|---|---|---|---|---|
| hit | 0.599508 | 0.012287 | 0.0205 | 1,330 | 0.1946 (0.0252) | 0.1167 (0.0442) | 0.0024 (0.0337) |
| pit | 1.0 (ratio 1.2944) | 0.107279 | 0.1073 | 1,038 | 0.1427 (0.0269) | 0.1847 (0.0902) | 0.0153 (0.0140) |

Three stated adaptations, because the literal rule cannot run: (1) the matrices hold 3 rows
with a MiLB block per side at decision years up to 2016, so list vintages up to 2016 are
added and V2 is scored only from 2017; (2) admission is off inside rule folds (none has two
earlier vintages that give a t); (3) a rule head with no inner CV year takes the fixed
penalty 30. DISCLOSED: the upper bound of 1 on a weight was added after the first dry run
of the rule read 1.29 for pitchers; the unbounded ratios stay in the receipt. The skill
columns rest on one rule year (list vintage 2016).

### 4.4 What the admission rule admitted on the development folds (eWAR v2 label)

| fold | hitter skill | hitter timing | pitcher skill | pitcher timing |
|---|---|---|---|---|
| lv 2017 | obp_rel, tool_hit, tool_speed | level_rank, on_40man, nov_add | k_rel | age_rel_level, level_rank, on_40man, nov_add |
| lv 2018 | obp_rel, tool_hit, is_college | age_rel_level, nov_add | k_rel | age_rel_level, nov_add |
| lv 2019 | obp_rel, tool_hit | age_rel_level, nov_add | k_rel | age_rel_level, nov_add |
| vm 2017-2019 | none (consensus order) | none | none (consensus order) | none |
| vm 2020 | obp_rel, contact, tool_hit, tool_speed, is_college | age_rel_level, level_rank | none (consensus order) | none |
| vm 2021-2024 | a subset of obp_rel, contact, tool_hit | level_rank (and age_rel_level 2021) | k_rel | level_rank |

Refused on the list-vintage frame: pitcher bmi (0 of 3 folds), pl_rev both sides (no row
before list vintage 2022), on_40man both sides over the full window (sign flips). The rule
is what is frozen, not this table: on R-LV it runs inside the V 2020 and V 2021 folds on
their own training vintages.

### 4.5 Training for a reserved read

R-LV fold V: V2 fit on labelled F-LV rows at list vintages before V with every player in the
V frame left out, weights from s4.3 (re-derived on the frozen label, P5). R-VM: V2 fit on the
v1 matrices at decision years before the cohort, forward-chained, timing-pinned inputs.

### 4.6 Draft-time pins (re-taken at registration, P4)

- `data/efv_v2_assembly.json` sha256 422fc5439253ad13d867320b00b634a178e62a8b291025326056377d6d4436ec
- `efv_v2_model.py` sha256 f83c94316b701cd59eeea4914cf5f910bbd0f558b891f788dbbee50d348a4d0e
- `efv_v2_stat.py`: the commit that carries this draft

---

## 5. Disclosures (bug B9 and the label policy)

**B9a, one R-LV exposure.** Lane I4's first P5 run read 3,270 E1 rows without the
vintage-matched filter, 1,127 of them at list years 2020 and 2021, for three statistics
(the FanGraphs-minus-Pipeline spread and the Pipeline-minus-consensus partial correlations
given consensus). The run was voided and its numbers are unused (I4 PROBES line 6). No eFV,
V2 or consensus score was computed on R-LV. Consequence: the FG-vs-Pipeline spread may not
be credited on R-LV as a rank or P(bust) finding, and it is not a V2 input.

**B9b, the reserved_vm W3 = 0 row policy.** A list-vintage row whose player debuted in 2025
or later carries status `reserved_vm` (`efv_labels.labels_for`). Policy, registered here:

1. If the debut falls OUTSIDE the W3 window V..V+3 (every such row on V 2011 to 2021), the
   row is KEPT with W3 = 0. W3 is defined as 0 when there is no debut within three seasons
   of V, and that fact was fixed by the end of season V+3, before 2025. No 2025 or later
   season's WAR is read, and no R-VM outcome is scored. Dropping these rows would select
   the frame on a later outcome (the player who arrives late would leave, the player who
   never arrives would stay).
2. If the debut falls INSIDE the W3 window (possible only for V 2022 and later, so no
   current or reserved F-LV frame), W3 is None and the row leaves every read until the
   R-VM look that owns it has run.
3. Every read states how many kept `reserved_vm` rows it scored (32 on the EV-09 H0
   lv_dev read, per DRIVER_SYSTEM_V2.md B9b).

**Amendment to B9b, dated 2026-10-15 (made while this file reads REGISTERED; owner answer efv2026 OQ6 = A, 2026-10-01, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`; committed by the owner's explicit permission of 2026-10-15).** The record of R-VM look 3 (RT 2028, the registered final boundary) releases, for the label reads of registered long-run frames only, the in-window debut cohorts no R-VM look owns (the 2028 and 2029 cohorts inside the long-run reads of `docs/efv-v2/SURROGATE_2026_GATE.md` s6.3), and releases nothing to any served path.

---

## 6. Forking paths (the denominator every number here is read against)

- Driver System V2 lanes, 2026-09-24/25 (`_finalpass_2026-09-24/efv3/*/PROBES.jsonl`): 275
  logged probes, about 347 frame-level reads counting A1's three-frame lines three times
  (A1 40, I1 19, I2 38, I3 22, I4 16, I5 138, S0 2).
- The 39 closed arms of the v1 program scoreable against a floor (`data/xfv_arm_ledger.json`,
  0 cleared).
- One R-LV exposure (B9a).
- Since the synthesis, on the build (`data/xfv_arm_ledger.json` at this draft): 80 arms
  across 8 lanes (the 39 above plus the DS-06 and V2 admission arms) and 40 validity probes
  (identity balance 18, combiner rule 2, served overlays 8, P(bust) 12); the EV-09 H0
  development read (2 frames); and DS-16 (2 frames, s7), logged as probes when it runs.
- Owner-asked driver lanes of 2026-09-25 (frame projectability, 21 outcome probes; FanGraphs
  PV and PV-for-ETA) keep their own probe records and are added here at registration.
- The screening lab, wave 1 (s10), counted under its own names. Seven arms in one Holm
  family (m 7): four text arms, the MiLB floor coverage arm and two pick re-tests. The
  floors: three N(0,1) noise columns per head and per side (hitters, pitchers, both sides
  pooled), in the floor mode in force and again for the other mode's receipt. Per column
  arm, its twin and its 500-draw permutation null. The DS-03 balance probes, per side, on
  `report_absent` (text), `pick_missing` (pick), and `milb_absent` and `level_prev_missing`
  at both floors (the MiLB floor lift). EFV3_B1's floors-only dry run and the one exploratory
  run (EFV3_B5), both on the eWAR v2 label. Each is a look at lv_dev, and none is evidence on
  its own.

- The scoreboard matrix lane (EFV3 lane D, 2026-10-02):
  `_finalpass_2026-09-24/efv3/LANE_D_cells.json` (SP/efv3/LANE_D_cells.json, written by
  `lane_d_cells.py`), row counts by stratum on the vm2 proxy and on lv_dev at list vintages
  2017 to 2019, and EFV3_D1's reproduction of the same counts through `efv_strata` (commit
  `678598a6`). Counts only: no rater score was read and no grade was paired with an outcome,
  so they add no look to the count below. They are listed because they showed which cells
  clear the 40-row floor on the development frames before s8.1 fixed the cell list, and a
  cell list chosen after counting is a path.

At nominal 95% intervals, 14 to 17 spurious CI-excluding reads are expected from the 275 to
347 looks alone. No development CI is evidence on its own; only a reserved read can be.

---

## 7. The development read registered before it runs (DS-16)

ONE read of the assembled V2 on the eWAR v2 label, run after this draft is committed:

- frames: lv_dev at V 2017 to 2019 (rows with a consensus grade, a W3 label, a V2 and a v1
  score; W3 contributor at `w*` 1.19) and vm_dev at frame version vm2 (window 2017 to 2023).
  Guards asserted before any score: no list vintage above 2019 or in `RESERVED_LV`, no vm
  base year or debut year at or after 2025, `reserved_vm_pins()` empty, the combiner rule's
  years below the first scored year.
- raters: V2 (order_idx), eFV v1 (its forward-chained score, raw), PROSPX consensus, MLB
  Pipeline, FanGraphs, each on the rows it grades; every comparison on identical rows.
- comparisons: V2 vs consensus (the one that matters), V2 vs v1, v1 vs consensus, V2 vs
  Pipeline, V2 vs FanGraphs; each by the within statistic (primary), the pooled statistic
  and AUC, E_cond, B 2000, seed 20260906.
- output: `data/efv_v2_dev_eval.json` key `ds16`, development rows in `data/efv_progress.json`
  (model `efv_v2_ds_assembled`, role development, resolvable none), two probes in
  `data/xfv_arm_ledger.json`, and `docs/efv-v2/STATUS.md`.
- standing: adjudicates nothing. It selects nothing (V2 is the one candidate). The registered
  development number is its re-run on the frozen label (P5).

---

## 8. Hypotheses and decision rules (carried from PROGRAM.md s4; items marked PENDING)

- Primary, per reserved frame: V2 beats PROSPX consensus on the within statistic, one-sided;
  the claim is the 95% lower bound. Holm across frames: m = 2 if PROGRAM Q3 = A, else 1
  (PENDING P6).
- Secondary Holm family: V2 vs MLB Pipeline and vs FanGraphs on each frame.
- Non-inferiority to v1 on dev, TOST margin 0.02, on the within statistic (the rule of
  PROGRAM.md s3.1 on the frozen-label dev re-run).
- Controls on every reserved cell: E_refit B 2000 player-clustered; zero-information twin
  (non-consensus columns permuted within vintage); 500-draw permutation null; at least 4
  time splits with signs; mde95 stated before the read; the AUC veto.
- Descriptive strata only: side, age, last level, draft or IFA, bonus band, vintage, source
  disagreement. Never consensus-FV cell. Amended 2026-10-02 (EFV3_D5): the strata are the
  pre-registered cells of s8.1, which replace this list (bonus band is deferred, s8.1); on
  each reserved frame they form the secondary Family S of s8.2 under owner answer E3-Q4 = A.
- Kill rules 1 to 8 of PROGRAM.md s4 apply verbatim; a guard trip or any score found on R-LV
  or R-VM before its look turns that frame into development permanently for v2.
- Served state (owner DS-Q1): V2 leads the board once built, labelled "ties consensus" until
  a reserved read says otherwise. The comparator stays today's served consensus (DS-Q4).

### 8.1 The stratum matrix: pre-registered cells (amendment 2026-10-02, EFV3_D5)

Written 2026-10-02 into this DRAFT, before any matrix cell is scored on any frame, from
`EFV3_PLAN.md` s6 and s7 and `LANE_D.md` s3.1, s3.2, s3.4, s3.5 and s3.10 (the eFV frontier
v3 plan, `_finalpass_2026-09-24/efv3/`). It edits nothing in s1 to s7: the statistic, the
candidate, its weights and the frames stay as drafted. No number from any read appears in
s8.1 to s8.4; the counts quoted are row counts with no score attached. The matrix is the
evaluation surface FRAME x CELL x COMPARATOR x STATISTIC (`tools/efv_matrix.py`, EFV3_D2,
artifact `data/efv_matrix_eval.json`). The one module that defines a dimension is
`efv_strata.py` (EFV3_D1, commit `678598a6`); its `DIMENSIONS` and `CELLS` are the list
below, and adding a dimension is a registration, never an edit.

Frames: vm2 (the headline frame, a development frame for V2), lv_dev (development, spent),
lv_res (R-LV, s2.2), vm_pros (R-VM, s2.2) and bust_inclusive (a secondary panel for the AUC
tabs). Tilted frames never enter.

The cells, quoted verbatim from `LANE_D.md` s3.1. The "E3-Q" ids inside the quotations of
s8.1 are lane D's own: lane D E3-Q1 is the unified owner question E3-Q4 (Secondaries), and
lane D E3-Q2 and E3-Q4 are recorded under their lane ids (s8.4).

> | dim | cells | vm2 | lv_dev | note |
> |---|---|---|---|---|
> | overall | all | 1 | 1 | the headline cell; on vm2 it IS `head_to_head_verdict` and the matrix copies it rather than recomputing it (parity test) |
> | side | hit, pit | 2 | 2 | `efv_dataset._side_match` through the matrix side, as the floors do |
> | position family | C, IF, OF (hitters only) | 3 | 3 | F5; pitchers are the side cell |
> | level at list | AAA, AA, A+, A, CPX, DSL, none | 7 | 7 | the V-1 level from the outcome-blind MiLB block (F3); "none" is its own cell and is reported with its identity route beside it |
> | age band at list | <=18, 19-20, 21-22, 23-24, >=25, unknown | 6 | 6 | base year minus birth year; "unknown" scored as a cell and flagged (F4) |
> | list year | 2017 to 2023 (vm2); 2017 to 2019 (lv_dev); 2020, 2021 (lv_res) | 7 | 3 | on vm2 this is the debut cohort (F11) |
> | archetype | hs_bat, hs_arm, college_bat, college_arm, intl_bat, intl_arm, unknown_bat, unknown_arm | 8 | 8 | `source_backtest._archetype` on vm; `is_college`, `is_ifa`, `acq_known_at_v` on lv; unknown is the row whose acquisition is not known at V |
> | source disagreement | FG minus Pipeline gap at or above 10 FV; under 10 | 2 | 2 | the one grade-derived dimension, a DIFFERENCE of two sources and not a level; registered as "source disagreement" in `EFV_V2_GATE.md` s8; disclosed on the page as grade-derived |
>
> That is 36 cells per frame on paper; scored cells are those with n at or above the floor (E3-Q4,
> recommended 40, `source_backtest.ARCH_MIN_N`). Today: vm2 24 stratum cells at or above 40 (plus
> overall and two side cells), lv_dev 30. Not a dimension, by rule: anything keyed on consensus FV,
> eFV grade, any rater's FV, a tier, a top-N rank, a bonus band expressed through FV, or the outcome
> (debuted, reached, label status). Bonus band and draft slot are deferred: they are known at V on
> the list frame but are "priced into consensus FV" (glossary copy, C-A4) and the brief's Lane B owns
> whether they are a stratum or a driver.

Readings fixed here, as `efv_strata` implements them:

- The floor (lane D E3-Q4 = A): a cell is scored when it holds at least 40 rows
  (`source_backtest.ARCH_MIN_N`), B 2000, E_cond, player-clustered, seed 20260906. A cell
  under the floor prints its n and UNPOWERED and carries no interval. An AUC cell also needs
  at least 10 positives and 10 negatives inside the cell. The "Today" counts in the
  quotation are lane D's development-frame counts, taken before EFV3_D1's defaults (D1-a,
  D1-b, D1-c); they are not the size of any family, which is fixed when a frame's families
  block is written (s8.2).
- Level at list: the V-1 level from the outcome-blind MiLB block, `efv_vintage_frame.frame_row`
  (`milb` from `efv_dataset._milb_features` with cutoff V-01-01, keyed on the `efv_identity`
  id, DS-03, bug B4): the block's `milb_level` when its `milb_season` precedes the base year,
  otherwise "none". On a vm frame the matrix row's block is read only when its season
  precedes the debut year. "none" is its own cell and is printed with its identity route
  beside it.
- Age band: base year minus birth year, with "unknown" a scored cell, flagged on every frame.
  Disclosure (`LANE_D.md` F4): 789 of 2,862 lv_dev rows carry no birth date (317 hitters, 472
  pitchers); every vm2 row carries one. On R-LV the unknown cell is a selection on identity
  resolution, which bug B4 makes an outcome proxy, so it is scored as its own cell, flagged,
  and never read as a finding about age.
- Archetype: hs, college and intl crossed with bat and arm, plus `unknown_bat` and
  `unknown_arm` (a row whose acquisition is not known at V). The two unknown cells are
  scored cells.
- Source disagreement: the one grade-derived dimension, the absolute FanGraphs minus MLB
  Pipeline gap at or above 10 FV, or under 10. It is a DIFFERENCE of two sources and never a
  level, and it is disclosed as grade-derived wherever it is printed. A row that either
  source did not grade reads "unknown" (EFV3_D1 default D1-a).
- Position family is a hitter dimension (`LANE_D.md` F5); a hitter listed at a pitcher or an
  unlisted position reads "unknown" (EFV3_D1 default D1-b).
- An "unknown" from a dimension whose declared cells do not include it (position family,
  level at list, source disagreement) is counted and printed, so the cells of each dimension
  still partition the frame's rows, and it is never scored and never enters a family
  (default D5-a).
- List year: on a vm frame the debut cohort (`LANE_D.md` F11); 2017, 2018 and 2019 on
  lv_dev; 2020 and 2021 on lv_res; the look's cohort on vm_pros. A cell whose rows are the
  whole frame (the one list-year cell of R-VM look 1) is the overall cell and is not counted
  again as a stratum (default D5-c).

The statistic per cell, quoted verbatim from `LANE_D.md` s3.2:

>     rows(C)      the frame's rows whose assigner value is C and on which both eFV and R are scored
>     groups(C)    the (side, vintage) groups inside rows(C) with at least MIN_GROUP_ROWS (20) rows
>     primary      within(eFV) minus within(R) over groups(C) if |groups(C)| >= 2
>                  else pooled-after-map Spearman delta on rows(C), and the cell carries
>                  statistic = "pooled (within degenerate: k groups)"
>     interval     efv_v2_stat.paired_delta(..., B 2000, seed 20260906), E_cond, player-clustered;
>                  ci95, sd, mde95 = 1.645 x sd; p_one_sided = P(Z > |delta| / sd)
>     map          efv_v2_model.output_map inside each (side, vintage) group of the WHOLE frame,
>                  computed once per frame and never refit per cell (the cell is a subset, the map is
>                  the frame's)
>
> The map is a frame property so that a cell's pooled statistic is the frame's pooled statistic
> restricted to the cell, and the cells of one dimension partition the frame's rows exactly.

On every frame the cell's primary is the within statistic of s3.1 when at least 2 (side,
vintage) groups of at least 20 rows survive inside the cell, otherwise the pooled statistic
of s3.2 after the identical output map of s3.3, and the cell declares which one it read.

The closed vocabulary, quoted verbatim from `LANE_D.md` s3.4. A scored cell carries exactly
one reading from this list and no other word:

> | reading | rule | printed as |
> |---|---|---|
> | AHEAD | survives Family S (or P) and delta > 0 | "ahead" (colour), only where E3-Q2 allows a word |
> | BEHIND | survives Family S (or P) and delta < 0 | "behind" (colour) |
> | EQUIVALENT | CI95 lies inside plus or minus 0.02 (the registered equivalence margin, `EFV_GATE_STANDARD.md` s8) | "tie (within 0.02)" |
> | UNRESOLVED | none of the above; n at or above the floor | "no resolvable difference" (neutral) |
> | FLAGGED_UNCORRECTED | |delta| >= 1.645 sd but did not survive the family | "clears its own floor, not the family" (neutral, with k and k x 0.05 beside it) |
> | UNPOWERED | n under the floor, or AUC positives under 10, or mde95 > 2 x 0.02 (the anchor gate's underpowered rule) | "unpowered (n)" (hatched) |
> | NOT_SCORED | no rows for the comparator (BA on lv, ESPN) | "no rows" |
> | DEVELOPMENT | the cell sits on a spent frame (lv_dev, or vm2 for V2 if the owner chooses B on E3-Q2) | the reading above with the chip "development, not a claim" and no colour |
> | RESERVED_PENDING | a pre-registered cell on lv_res or vm_pros before its look | "pre-registered, not read" |
>
> "Ties are ties" means: UNRESOLVED and EQUIVALENT are two different readings and the page never
> rounds the first into the second or into a lead; the frame-level line prints "A ahead, B behind,
> C equivalent, D unresolved, E unpowered of K cells; K x 0.05 = X false flags expected by
> construction"; and a cell that FLAGGED_UNCORRECTED is drawn in the neutral style with its k, never
> in colour. On vm2 the overall cell's reading today is UNRESOLVED, which the hero already calls "a
> tie: the gap sits inside the floor"; the matrix keeps that sentence and adds the distinction in its
> legend.

Under lane D E3-Q2 = A, "where E3-Q2 allows a word" means: a vm2 stratum cell may carry
AHEAD or BEHIND inside the matrix grid only, after surviving its frame-wide family. lv_dev
cells read DEVELOPMENT. Cells on lv_res and vm_pros read RESERVED_PENDING until the look
runner reads them (s8.2).

### 8.2 Families, and Family S on the reserved frames

Every frame's families are written into the artifact BEFORE any cell is read (a `families`
block, then `cells`, then `summary`), each family with its cell list, each cell's n and the
floor it is read against:

- Family P, the claim: the overall cell, V2 versus PROSPX consensus, unchanged. On a reserved
  frame it is the primary of s8, copied from the look record; on vm2 it is copied from
  `accuracy.head_to_head_verdict`.
- Family I, the industry: unchanged. On a reserved frame it is the secondary Holm family of
  s8 (V2 versus MLB Pipeline and versus FanGraphs); on vm2 the FP3-3 family copied from
  `accuracy.head_to_head_vs_sources`.
- Family S, the strata: every cell of the s8.1 dimensions that holds at least 40 rows, the
  two side cells included (default D5-b), versus PROSPX consensus on the cell's declared
  primary statistic; ONE family per frame; Holm step-down, one-sided on |delta| / sd, alpha
  0.05 (`source_backtest._holm_family`). k is the number of cells at or above the floor when
  the families block is written. The per-dimension Holm (each dimension's own m) may be
  printed inside the artifact as a secondary reading; the word comes from the frame-wide
  family only, because a reader who can pick the partition can pick the finding.
- The AUC legs and the industry comparators on stratum cells belong to no family: they print
  intervals and the uncorrected floor line, labelled "uncorrected, not a claim". AUC never
  enlarges a family (`docs/EFV_GATE_STANDARD.md` s3.1).

**Family S clause.** Owner answer E3-Q4 = A (Secondaries; the unified question in
`SP/efv3/OWNER_QUESTIONS.json`, recorded 2026-10-02 under the owner's standing instruction in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`; the recommended default, taken as the design;
not E3-Q1, the scrap-or-keep question, which decides nothing here):

On each reserved frame the stratum cells of s8.1 form ONE secondary Holm family, Family S, at
alpha 0.05, V2 versus PROSPX consensus on the primary statistic under the cell rule of s8.1.
R-LV is one frame over list vintages 2020 and 2021; R-VM carries Family S at look 1, and a
later R-VM look carries it only by a dated amendment written before that look. The family is
read once, in the same look as the primary, on the same rows, by the look runner
(`efv_matrix.cells_for`, EFV3_D6), with E_cond, B 2000, seed 20260906, player-clustered; the
E_refit claim of s3.6 belongs to Family P alone. Family S has NO ship consequence: it adds no
condition to the primary, does not enlarge Family P or Family I, moves no served number and
is not a further attempt at the primary. It has no copy consequence beyond the matrix
itself: a cell that survives prints "ahead" or "behind" inside the matrix grid only, with k
and k x 0.05 beside it, and the hero, the share card, the Diamond tiles, the registry
verdicts and every methodology sentence read no matrix key. Kill rules 1 to 8 apply to it as
to the primary; a guard trip on a reserved frame turns that frame's cells into development
with the frame.

If E3-Q4 reads B or C when the status line changes, the paragraph above is void and the
clause reads instead: "On the reserved frames the stratum cells are descriptive only: they
print intervals and never a word, carry the chip 'descriptive by the gate', and form no
family."

### 8.3 No FV-level cell, and the three pre-existing tier reads

- No dimension is keyed on consensus FV, the eFV grade, any rater's FV, a tier, a top-N rank,
  a bonus band expressed through FV, or the outcome (debuted, reached, label status)
  (`efv_strata.BANNED_DIMENSIONS`, its AST test, and the ledger's `_FV_CELL` regex).
- An FV-tier dimension may be added only by a dated amendment to the matrix's registration
  that cites the anchor look record (`docs/PROSPECT_ANCHOR_GATE.md` s18), after the later of
  2026-11-20 and 14 days after the fWAR epoch's step Z entry (its s14), never by editing
  `DIMENSIONS`.
- Under lane D E3-Q3 = A, the three pre-existing FV-tier reads, `source_backtest._tier_table`
  (the glossary's "Cohort outcomes by FV tier"), the `by_fv_tier`, `t45` and `wm` blocks of
  `tools/efv_scoreboard.py`, and the `by_fv_tier` block of `source_cohort_accuracy.py`, serve
  their last committed values with the chip 'frozen pending the anchor look' until the anchor
  look record exists; the guards are served code and land with EFV3_D2.

### 8.4 Owner answers read, and the defaults this amendment applied

- Unified E3-Q4 = A (Family S, s8.2), recorded. Unified E3-Q1 = C, E3-Q2 = A and E3-Q3 = A
  are recorded and change nothing in s8.
- Lane D E3-Q2 = A (Holm-corrected words on vm2, inside the matrix only), E3-Q3 = A (the
  tier-read freeze, s8.3) and E3-Q4 = A (40 rows, B 2000, E_cond), each the recommended
  option, taken by default and recorded by lane id in `DECISIONS_FOR_OWNER.md`.
- D5-a: an undeclared "unknown" (position family, level at list, source disagreement) is
  counted, never scored. D5-b: the two side cells are members of Family S. D5-c: a cell
  equal to the whole frame is the overall cell. Each is reversible by a dated amendment
  before the status line changes.

---

## 9. Results

(Empty. Filled only by the look runner after the status line reads REGISTERED.)

---

## 10. Screening lab

Written 2026-10-02 into this DRAFT, before the lab's registered run and before its
exploratory run, from `EFV3_PLAN.md` s4 and `LANE_B.md` s4.5 and s7 (the eFV frontier v3
plan, `_finalpass_2026-09-24/efv3/`). This section is part of what P5 freezes: it changes
with the rest of this file and with nothing else. The lab is `tools/efv_screen_lab.py`. It
admits a column to the candidate list of s4.2 and to nothing else. It moves no served
number, reads no reserved frame (the R-LV list vintages 2020 and 2021 and the R-VM debut
cohorts from 2025 stay outside it, guard asserted before any score), and re-runs no closed
arm on the frame it was closed on. No number from any read appears in this section. No
statistic of the lab, its inputs or its artifacts is cut by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`); its only groupings are side, vintage and fold.

### 10.1 Frame, folds and label

- Frame: lv_dev only, `efv_vintage_frame.build_frame(side, V)` at list vintages 2017, 2018
  and 2019 (the vintages V2 is scored on, s2.1). Six (side, vintage) groups; three folds per
  side.
- Label: W3 (`efv_labels.labels_for_frame`). A B9b `reserved_vm` row is kept at W3 = 0 and
  counted in the run's receipt (s5).
- Training for fold V: `efv_v2_model.lv_training_rows`, labelled F-LV rows at vintages below
  V plus the v1 matrices at decision years below V, with every V-frame player excluded
  (s4.5).
- vm_dev is not a screening frame. Its rows sit at the debut year, where consensus has
  already absorbed the record, and every closed arm was read there. It may be shown beside
  the lv_dev result of an admitted candidate as a description, never as a verdict.

### 10.2 Base and candidate

- Base: V2 as assembled (s4), its `order_idx` per row, with the weights of
  `data/efv_v2_assembly.json` re-derived once on the frozen label (P5).
- Candidate: the same assembly with one extra column offered to one declared head (skill or
  timing), admitted or refused inside each fold by DS-06 (`efv_v2_model.admission_for_key`,
  the rule of s4.2). A refused column leaves the candidate equal to the base in that fold.
  That is a null, not an error. A row without a value imputes at the fold's observed
  training mean, as a sidecar driver does (DS-04).
- The coverage arm `milb_floor_2005` has no column. Its candidate is the base refit and
  scored on the F-LV frame built with the MiLB floor lifted to 2005
  (`efv_vintage_frame.MILB_FLOOR_LV`), paired row by row with the base. The per-side
  withhold that the DS-03 re-run set on the lifted frame
  (`efv_vintage_frame.MILB_FLOOR_LV_WITHHELD`, EFV3_B3) applies as committed.

### 10.3 Statistic and estimator

- Primary: `efv_v2_stat.within`, the within (side, vintage) statistic of s3.1, groups of at
  least 20 rows. Secondary: pooled after the identical output map (s3.2, s3.3). Contributor
  AUC at `w*` (s3.5) may veto and may not credit; it is not a member of the Holm family.
- Delta: `efv_v2_stat.paired_delta` with the within statistic, candidate minus base on
  identical rows. E_cond (scores fixed, players resampled), paired, player-clustered, B 2000,
  seed 20260906.
- The admission claim is the one-sided 95% lower bound of the within delta, lb95 = delta
  minus mde95 (mde95 = 1.645 x SD of the drawn deltas), printed beside the point.

### 10.4 The floor rule

- Floors are derived in the run that uses them, before any arm is read, and the artifact
  writes `floors` before `arms`.
- Three N(0,1) noise columns per head and per side (hitters, pitchers, and both sides pooled
  for the coverage arm) go through the identical pipeline. The MAX mde95 over the three is
  the head's feature-add floor on that side, for the within, pooled and AUC legs. The
  coverage arm reads against the larger of the two heads' floors on both sides pooled.
- Floor mode, disclosed (`--floor-mode`, default `forced`). In the floor derivation alone,
  the noise column is admitted without the DS-06 rule and refit, so the floor measures what
  a column that is admitted moves by chance. The literal reading (`admitted`: the noise
  column sent through DS-06 as well) leaves a floor undefined wherever no noise column is
  admitted in any fold. An undefined floor is recorded as none, never as 0, and every arm on
  that head and side then reads `NOT_ADJUDICATED_NO_RHO_FLOOR`. Every artifact writes the
  other mode's floors beside the mode in force (`floors_other`). The twin and the
  permutation null always go through the identical admission.
- No floor value is written here. The registered run's measured floor is the floor.

### 10.5 Controls

On every column arm:

- the zero-information twin: the column permuted within (side, vintage) and sent through the
  same admission and refit; a twin at or above the candidate is no result (kill rule 5);
- a 500-draw permutation null of the within delta (one-sided p), each draw through the
  identical admission and refit;
- the per-fold deltas with their signs (three folds per side) and the DS-06 per-vintage
  signs beside them;
- the contributor AUC delta against its own noise floor (veto only);
- the DS-03 balance probe on the missingness indicator of any column with a missing value
  (partial given the consensus percentile, player-clustered CI95, 500 draws, the
  `tools/efv_identity_balance.py` pattern): `report_absent` for the text family and
  `pick_missing` for the pick re-test.

The coverage arm has no column to permute. It carries no twin and no permutation null, and
its p for the Holm step is the bootstrap one-sided p of the within delta (the share of E_cond
draws at or below 0), disclosed in the arm. Its balance probes are the DS-03 re-run of
`milb_absent` and `level_prev_missing` on the lifted frame (EFV3_B3), which sets the per-side
withhold before the lab runs.

### 10.6 The Holm family

One family per wave over every registered (candidate, side) arm; wave 1 has m = 7. The family
is formed after every arm is measured, not inside the measuring loop (the
`apply_holm_verdicts` pattern, `docs/EFV_GATE_STANDARD.md` s3.1 point 3). An arm's p is the
one-sided permutation p of its within delta. m is the registered size even when an arm cannot
be measured: an absent arm never shrinks the correction. AUC does not enlarge the family
(PROGRAM.md s2.1). Alpha 0.05, Holm step-down.

### 10.7 The admission rule

Pre-registered, quoted verbatim from `LANE_B.md` s4.5:

> ADMITTED to the V2 candidate list (not to the served grade) only if all of: (a) within
> delta's one-sided 95% lower bound above 0 and point at or above the floor of its head and
> side; (b) Holm-adjusted permutation p below 0.05 inside the wave family; (c) the twin
> inside its floor; (d) DS-06 admitted the column in every one of the three folds and the
> fold deltas share a sign; (e) contributor AUC delta not adverse beyond its floor; (f) for a
> column with any missingness, the DS-03 balance probe reads BALANCED; (g) the pooled
> secondary is not adverse beyond its own floor (reported; a disagreement between the two
> statistics is disclosed, S1 reconciliation).

Readings fixed here, as the lab implements them:

- The coverage arm: (c) does not apply, (d) reads as "the fold deltas share a sign" (no
  column is admitted or refused), and (b) uses the substituted p of s10.5.
- (f): a probe whose indicator does not vary on the training rows reads CONSTANT and meets
  (f); a probe that reads IMBALANCED fails it.
- A column that its builder withholds, or that cannot be built on the run's tree, is not
  measured. It carries no verdict, still counts in m, and is never admitted.

### 10.8 The verdict vocabulary

A registered run emits the eight strings of `docs/EFV_GATE_STANDARD.md` s3.1 and no other:
`PASS` (read here as admitted to the candidate list, and still not a claim), `VETO_ON_AUC`,
`NULL`, `NULL_AUC_ONLY`, `NULL_HOLM`, `NOT_ADJUDICATED_NO_RHO_FLOOR`,
`NOT_ADJUDICATED_NO_AUC_FLOOR` and `NOT_ADJUDICATED_NO_HOLM`. The composite of (a), (c), (d),
(f) and (g) plays the role the standard gives "rho clears"; (e) is the AUC veto; (b) is the
Holm step. An absence never reads as `PASS`. A ninth string, `NOT_ADJUDICATED_EXPLORATORY`,
is reserved to the exploratory run of s10.11; the registered run never writes it, and
nothing under `data/` carries it.

### 10.9 Wave 1, frozen

Seven arms, one Holm family (m = 7), frozen in `tools/efv_screen_lab.py` `CANDIDATES` at
commit `d9fe7db4` (EFV3_B1, 2026-10-02). Commit `59fe8427` (EFV3_B4) changed only where the
two pick columns read their values (the pick builder in place of the sidecar stand-in). Commit
`9c541e92` (EFV3_B5) changed only where the four text columns read their values (the text
builder's fold fit, stacked out of vintage, in place of a function the builder never had) and
what the coverage arm pairs (frames built at the lifted floor against frames built at the served
default floor, in place of the lab's shared frame, which the tree already builds at the lift on
hitters); every name, side, head, kind and re-test flag is as `d9fe7db4` froze it, and the
artifact's `registration_echo.frozen_commit` names that commit. Nothing is added to wave 1
after this section is committed (kill rule 1).

| arm | side | head | kind | builder |
|---|---|---|---|---|
| `txt_skill_hit` | hit | skill | column | `efv_text_features` (EFV3_B2): fold-fitted tf-idf ridge scalar on the W3 percentile residual |
| `txt_skill_pit` | pit | skill | column | as `txt_skill_hit` |
| `txt_time_hit` | hit | timing | column | `efv_text_features`: the same scalar fitted on the R3 target |
| `txt_time_pit` | pit | timing | column | as `txt_time_hit` |
| `milb_floor_2005` | both, pooled | none | coverage | `efv_vintage_frame.MILB_FLOOR_LV` (EFV3_B3): the base refit on the lifted F-LV frame |
| `pick_overall_time_hit` | hit | timing | column, named re-test | `efv_pick_features` (EFV3_B4): log1p of the pick joined on the outcome-blind id with draft year strictly below V, else the sidecar pick known at V |
| `pick_overall_time_pit` | pit | timing | column, named re-test | as `pick_overall_time_hit` |

The text family's rules (EFV3_B2, `LANE_B.md` s3): list vintages 2011 and 2012 are dropped
(backfilled reports); a per-row anachronism filter runs from 2013; grade strings are
stripped before tokenizing; tokenizer, idf and ridge are fit per fold on vintages strictly
below V with every V-frame player excluded; consensus enters only as u_c. A skill text
column is offered on a side only where `report_absent` reads BALANCED under DS-03
(`efv_text_features.offered_columns`); a withheld column is recorded as s10.7 says.

### 10.10 The named re-test, and what is not screened

- `pick_overall_time_hit` and `pick_overall_time_pit` are a named re-test of the closed F-VM
  arm D-1 `pick_overall` on lv_dev, a frame it was never read on, timing head only
  (`DRIVER_SYSTEM_V2.md` D4: pick and bonus are never a rank feature). It is not
  re-shopping. It is named before any read, it carries its re-test flag in the artifact and
  in the arm ledger, it counts in s6 under its own name, it reads on a frame other than the
  one that closed it, and it may not be re-run on vm_dev.
- `seasons_at_level_pit` is not screened. `data/efv_v2_assembly.json` lists
  `seasons_at_level` under `scrapped.pit` as the pitcher block of owner answer DS-Q2 (a
  locked owner decision). `data/efv_v2_dev_eval.json` already carries it in H0's lv_dev
  pitcher candidate list, so it has been read on F-LV. Its record is
  `data/model_registry.json` `xfv_repeat_level` (E1, 2026-07-30). A re-test would be
  re-shopping.
- Also not screened: vm_dev, the 39 closed arms of `data/xfv_arm_ledger.json`, and any
  lambda, correction family or new grade source offered as a margin lever.

### 10.11 The exploratory run (disclosure)

One exploratory run of wave 1 on the eWAR v2 label, the label on disk before the fWAR
freeze (EFV3_B5), writes its floors, twins, per-fold signs and balance probes to a file
outside `data/`. It writes no `data/` file, no ledger row and no progress row, and it is not
committed. Its artifact carries `screening.exploratory` true. It forms no verdict: every arm
reads `NOT_ADJUDICATED_EXPLORATORY` and nothing is admitted. Its floors are advisory; the
registered run derives its own. EFV3_B1's floors-only dry run of the lab (scratchpad, eWAR v2
label) is a development read of the same kind and formed no verdict. The exploratory run was
made on 2026-10-02 (lab commit `9c541e92`, label `ewar_v2@2026-09-03T12:35:09`) to
`_finalpass_2026-09-24/efv3/xfv_screen_wave1_exploratory.json`, outside the repository and
untracked; six of the seven arms were measured and `txt_skill_hit` was withheld by the DS-03
verdict (s10.9); every arm reads `NOT_ADJUDICATED_EXPLORATORY`. No number from it is written
here. Both count in s6.

### 10.12 Calendar

1. The one registered run (EFV3_B7) reads the frozen fWAR label after EPOCH_RUN and Z1_RUN,
   with this section committed first: the same seven arms, family, seed and rule, and floors
   derived in that run.
2. Admitted candidates enter s4.2 by a dated amendment before the status line changes. Every
   other arm is recorded with its verdict string and its numbers in `docs/efv-v2/STATUS.md`
   and the arm ledger, not in this section.
3. Hard cutoff, owner answer E3-Q3 (the unified form of lane B's E3-Q21; option A, taken
   2026-10-02 under the standing instruction): EV-12 commits after both registered screens
   (this wave and the five-arm model-class screen of `docs/efv-v2/MODEL_CLASS_SCREEN.md`) or
   on 2026-11-15, whichever comes first. A survivor that arrives after the status line
   changes, or after 2026-11-15, waits for the 2027 registration. The reserved read date (not
   before 2026-12-01) does not move.
4. The registered run does not run on a registered look's date (`docs/*GATE*.md`), among
   them 2026-10-23, 2026-11-06 and 2026-11-13 (projections looks), 2026-11-20 (the Prospect
   Anchor look) and 2026-12-01 (the eFV reserved read).
5. Wave 2 (roster counts, the Statcast chain's second link, any FanGraphs-text-only column)
   runs only after wave 1's registered run is on the ledger, as its own family, registered in
   this section before it runs.

### 10.13 Publication

The registered run writes `data/xfv_screen_wave1.json` (the registration echo, the label id,
the guards, `floors` before `arms`, the Holm family, the probes). Its arms join
`data/xfv_arm_ledger.json` through `tools/efv_arm_ledger.py`. Each measured arm is a
development row of `data/efv_progress.json`: model_id
`efv_v2_screen:wave1:<candidate>:<side>`, resolvable null, `screening.exploratory` false. An
admitted column enters `efv_v2_model.skill_candidates` or `timing_candidates` behind a module
flag `V2_SCREEN_CANDIDATES_ON` that defaults off (EFV3_B7). With the flag off the served heads
and `data/efv_v2_assembly.json` stay byte-identical; only the look runner reads an admitted
column, inside the look.

### 10.14 Families with no vintage-matched source (recorded, not screened)

No source dated inside the row's window exists for these families at any labelled
development or reserved vintage, so the lab cannot screen them. They are recorded here so no
later lane re-discovers the absence (`LANE_B.md` s7).

| family | why there is no source at a labelled vintage | first possible read |
|---|---|---|
| IL stints | `il_history` begins 2017 and holds few stints a year before 2026 | when back-population reaches 100 pre-cutoff stints on the resolved cohort (the revival trigger of `data/xfv_injury_history_eval.json`) |
| Signing bonus before the 2017 classes | `acquisitions.bonus_usd` and `data/draft_bonus_slot.json` begin with the 2017 classes; `draft_history` carries picks only | never, unless a pre-2017 bonus table is ingested from a file the owner already has |
| College production for draftees | CollegeSavant covers the 2021 and later classes, `draft_statlines` 2022 on, `.cache/amateur_leagues` 2021 on. The count-only StatsAPI probe ran (EFV3_B9, 2026-10-02, `data/college_source_probe.json`, lane B E3-Q24 option A by default): sportId 22 returns 0 splits for 2005 to 2016 except 33 rows in 2009, then 477, 851, 981 and 547 rows (league CBB only) for 2017 to 2020; on the F-LV development frame 5 of 467 is_college rows carry a college line in a season below their draft year (3 of 110 hitters and 2 of 127 pitchers, all at V 2019; 0 of 230 at V 2011 to 2018); no stat was read | not screenable on any development vintage (5 rows); the 2017 to 2020 sport-22 seasons first precede a whole class at the 2019 draft, listed at V 2020 (R-LV, reserved) and later; the 2021 class (CollegeSavant and sport 22) resolves W3 about 2029 |
| AAA and FSL Statcast, A-ball signals | tracking begins 2021 (FSL) and 2023 (AAA); the DB tables hold 2026 only; `data/signal_snapshots/` holds 2023 on | FSL-era V 2022 at RT 2027; AAA-era V 2024 at RT 2029; the chain's second link is screenable now (wave 2) |
| Modern pitch-level data, pitch rates | AAA pitch files begin 2023; `data/milb_pitch_rates.json` is 2026 only | as AAA Statcast; pitch rates per Q10_11, which owns their admission |
| Tracked physical data | bat speed 2023 on (AAA), bat tracking 2024 on, sprint and arm MLB only | 2027 and later (program D6) |
| eBR runner record | not built (`.cache/ebr` is empty) | after the eBR plan's integration task |
| BA, ESPN, Just Baseball and TJStats report text | first published 2023, 2025, 2026 and 2026 | R-LV never; V 2023 at RT 2028 (W3; BA), V 2026 at RT 2031 for the other three (s10.15.7) |

### 10.15 Wave 2, draft: the Statcast chain's second link

Written 2026-10-03 into this DRAFT (EFV3_B10), from `EFV3_PLAN.md` s4 and `LANE_B.md` F-B9,
s3 (the S chain) and s7, before any wave-2 code exists and before any read of the column it
names. No number was computed for it and none appears in it. It registers two arms of wave 2
and nothing else: the rest of wave 2 (roster counts, any FanGraphs-text-only column) is
registered by its own dated amendment of this section, and wave 2 runs only as s10.12 item 5
says. Every rule of s10.1 to s10.8 and s10.13 applies to it unchanged, with the readings fixed
below. It moves no served number, reads no reserved frame (R-LV, R-VM), re-runs none of the 39
closed arms of `data/xfv_arm_ledger.json`, and groups nothing by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`, whose one look is not before 2026-11-20); its only groupings
are side, vintage, fold and the level-season pool that defines the column.

#### 10.15.1 The chain

- Link 1, on record, not re-run: S-XLINE-4 (`docs/efv-2026-07-23/GATES.md`, artifact
  `data/xfv_statcast_line4_eval.json`) read A-ball and complex tracking signals in the seasons
  2023 to 2025 against production in the following season, incremental on the stat line:
  `INC_2_whiff` PASS, `INC_3_fb_velo` PASS, `INC_1_p90ev` NULL. The production it predicts (the
  surrogate) is, for hitters, the wOBA proxy z and, for pitchers, the K%-against z, each inside
  the (destination level, season) pool of players whose own max-exposure row sits at that
  level, with the exposure floor of 150 PA or 150 BF and pools of at least 20
  (`tools/efv_statcast_line2_lab.py`, `_dest_z_maps`).
- Link 2, registered here: next-level production at V to W3. The column is the link-1
  surrogate itself, computed for the row's player from `.cache/milb_stats` seasons that ended
  before V-01-01 (the as-of rule of `_milb_features`), and screened as an ordinary column of
  the lab on lv_dev at list vintages 2017, 2018 and 2019 (s10.1) against the V2 base (s10.2).
  It reads no tracking data. No tracked season exists before 2021, so the link-2 column is the
  stat line that the link-1 legs predict, never a tracked signal.

#### 10.15.2 The column, exactly

- Arms: `chain2_hit` (hitters, skill head, the wOBA proxy z) and `chain2_pit` (pitchers, skill
  head, the K%-against z). Each is carried on the row's `v2` view under the lab's screening
  prefix (`efv_v2_model.V2_SCREEN_PREFIX`).
- A chain row is a (player, V) row whose outcome-blind `efv_identity` id has, in some season S
  that ended before V-01-01, a max-exposure row at or above the exposure floor, and in season
  S - 1 a row at level A or CPX at or above the same floor (the origin levels of link 1,
  `LEVELS` of the line-2 lab). The latest such S is the one used. The value is that season's
  z, built as `_dest_z_maps` builds it, with each pool drawn from every player in that (level,
  S) pool, never from the frame.
- Every other row carries no value and imputes at the fold's observed training mean (s10.2,
  DS-04). The missingness indicator `chain_absent` never enters a skill head. It is the
  column's DS-03 balance probe (s10.5), and clause (f) of s10.7 applies to it: a chain row
  exists only for a player who played a season above an A-ball or complex season, so its
  presence can stand in for promotion, which can stand in for the label.
- Level codes are each season's own (`milb_history.SPORT_LEVEL`). The 2021 reorganization
  moved leagues between the A and A+ codes and ended short-season A (sport 15, coded A), so
  the origin pool at V 2017 to 2019 is not the 2023 to 2025 pool of link 1. The shift is
  disclosed and not corrected: no era column, as the M1 rule of `LANE_B.md` s3 says.
- The builder is a wave-2 task. It imports the line-2 lab's surrogate functions rather than
  copying them, and its test pins that the link-2 value of a 2023 to 2025 origin row equals
  the link-1 surrogate for the same player and season.

#### 10.15.3 Overlap with existing columns, and why this is a named re-test

The surrogate is a production rate relative to its level and season. On hitters it overlaps
`obp_rel` (a V2 skill candidate), `ops_rel` (scrapped by DS-05 as collinear with `obp_rel`)
and the closed arms `C6:wrc_rel_add:hit`, `D-1:peak_obp_rel:hit`, `D-1:iso_rel:hit` and
`D-1:prod_trend:hit`. On pitchers it overlaps `k_rel`, the DS-10 pitcher skill candidate that
the V2 base already offers on lv_dev. It is none of them under a new name: it carries a value
only on chain rows, it is the destination-pool z that the link-1 legs were scored on rather
than a shrunk difference from the level norm, and its question is the chain's second link,
which no arm has asked. It is therefore a named re-test on the terms of s10.10: named before
any read, flagged as a re-test in the artifact and in the arm ledger, counted in s6 under its
own name, read on lv_dev only and never on vm_dev. The closed arms it overlaps are not re-run,
and no other production-rate variant is offered under the chain's name. Before an arm is
scored, the run writes per fold the rank correlation of the chain column with each overlapping
key on the training chain rows, as a description that bears no verdict; a chain column equal
to an overlapping key on every chain row is not measured (the last reading of s10.7). The
honest prior is no survivor: the base already carries the production rates it overlaps.

#### 10.15.4 Family, rule, label and publication

- The two arms belong to wave 2's one Holm family (s10.6). m is the number of wave-2 arms
  registered when the wave-2 list closes, by a dated amendment of this section made before the
  wave-2 run; these two arms are in m whatever else joins, and an arm that cannot be measured
  still counts.
- Floors per s10.4, derived in the wave-2 run on the skill head of each side. Controls per
  s10.5, with `chain_absent` as the balance probe. Admission per s10.7, clauses (a) to (g),
  verbatim. Verdicts per s10.8 only.
- Label: the frozen fWAR W3, after EPOCH_RUN and Z1_RUN and after wave 1's registered run is
  on the ledger (s10.12 item 5), never on a registered look's date (s10.12 item 4). An admitted
  arm reaches s4.2 only by amendment before the status line changes and before 2026-11-15
  (E3-Q3); after either, it waits for the 2027 registration.
- Publication as s10.13 with wave 2 in place of wave 1: `data/xfv_screen_wave2.json`, the arm
  ledger through `tools/efv_arm_ledger.py`, development rows
  `efv_v2_screen:wave2:<candidate>:<side>` in `data/efv_progress.json`, and an admitted column
  only behind `V2_SCREEN_CANDIDATES_ON`, which defaults off.

#### 10.15.5 No number from the two links is multiplied into a claim

The links are read on different players in different years: link 1 on A-ball and complex
seasons 2023 to 2025 against the following season, link 2 on list vintages 2017 to 2019
against W3. No number from the two links is multiplied, chained, pooled or composed into a
claim, and neither link, alone or with the other, supports a statement that a tracked signal
predicts W3. A tracked signal reaches W3 only through its own vintage-matched read. The first
W3-resolvable vintage with FSL tracking is V 2022 (RT 2027), and with AAA tracking V 2024 (RT
2029). Until those dates the tracked family (AAA and FSL Statcast, the A-ball signals, modern
pitch-level data, tracked physical data) reads "no vintage-matched source", whatever verdict
the link-2 arms receive.

#### 10.15.6 The retained input

`data/signal_snapshots/<season>/` (seasons 2023 to 2026, written append-only by
`tools/snapshot_modern_signals.py` under EV-03, one as-of-dated file per signal and season,
with `manifest.json`) is the retained input for those reads. The `prospects.db` tables
(`statcast_metrics`, `pitch_arsenals` and the others that tool names) are keyed by player
alone and hold 2026 only; each season overwrites the last, so they are never the source of a
vintage read. The snapshots and `.cache/savant_minors` begin with the 2023 season: the FSL
2021 and 2022 seasons that a V 2022 or V 2023 read needs are not on disk, so that read first
needs a registered, as-of-dated fetch of those two seasons.

#### 10.15.7 The other families with no vintage-matched source

Recorded here with the first possible date for each, so no later lane re-discovers the
absence; s10.14 carries the same families. A source whose first season or publication falls
inside V's window, or ends before V-01-01, first serves list vintage V, and W3 at V resolves
at RT V + 5 (`efv_labels.py`).

| family | why there is no source at a labelled vintage | first possible read |
|---|---|---|
| eBR runner record | `.cache/ebr` holds nothing (the directory is absent); the family exists only in plan text | none before the eBR plan's integration task; a record whose first season is Y first serves V = Y + 1, on W3 at RT Y + 6 |
| College production for draftees | CollegeSavant covers the 2021 and later classes, `draft_statlines` 2022 on, `.cache/amateur_leagues` 2021 on; EFV3_B9's count-only probe of 2005 to 2020 is recorded in s10.14 | the 2021 class, first listed at V 2022, resolves W3 no earlier than RT 2027 (s10.14 dates the class's read about 2029) |
| IL stints | `il_history` begins 2017 and holds 5 to 115 stints a year before 2026 (none dated 2020) | when back-population reaches 100 pre-cutoff stints on the resolved cohort (the revival trigger of `data/xfv_injury_history_eval.json`); the 2026 stints first serve V 2027, on W3 at RT 2032 |
| Signing bonus before the 2017 classes | `acquisitions.bonus_usd` and `data/draft_bonus_slot.json` begin with the 2017 classes; `draft_history` carries picks only | never for the classes before 2017, unless a pre-2017 bonus table is ingested from a file the owner already has; the 2017 and later classes are on disk and `D-1:bonus_log` is closed, so they are not re-shopped |
| BA report text | first published 2023 (dated 2023-02-15, inside the V 2023 window) | R-LV never; V 2023, on W3 at RT 2028 |
| ESPN report text | first published 2025 (dated 2025-08-20, outside every window); first inside a window 2026-01-27 | V 2026, on W3 at RT 2031 |
| Just Baseball report text | first published 2026 (dated 2026-03-04) | V 2026, on W3 at RT 2031 |
| TJStats report text | first published 2026 (the first `tjstats_snapshots` writeup is dated 2026-04-14) | V 2026, on W3 at RT 2031 |

---

## 11. Registration by decision EW2-6, with the preconditions it leaves unmet (2026-10-08)

Appended 2026-10-08 (EFV3_W3_SELECT_CONFIRM) below the last section; nothing above it is
edited except the status line at the top, which now reads REGISTERED. Decision EW2-6 of
2026-10-08 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`) moves the reserved read from
2026-12-01 to the same day: the owner judged that waiting a month would not change the
reading (eFV ties consensus on every development frame) and chose a same-day backtest of
every new eFV idea, with one rule kept, that the configuration is chosen on the
development frames only, committed, and then read ONCE on the reserved frames. Decision
EW2-7 fixes the reading in advance: eFV v3 is shippable if its within Spearman beats served
eFV (V2) on both reserved frames (point estimates, pooled over sides), and the copy can say
it beats consensus only if the CI95 lower bound against consensus is above 0.

### 11.1 What the status line opens, and for what

The guard (`efv_vintage_frame.gate_sha_committed`) opens for the sha of the commit that
carries this file with the status line REGISTERED. That sha is handed to
`tools/efv_v3_backtest.py --confirm --gate-sha`, the one tool run that reads R-LV (list
vintages 2020 and 2021) and R-VM (the 2025 debut cohort) under
`docs/efv-v2/EFV_V3_BACKTEST.md` s3. The R-VM leg opens on the same sha through
`efv_vintage_frame.guard_vm_request` and `efv_v2_model._check_years(gate_sha=...)`;
`reserved_vm_pins()` stays empty and the pinned constants are not widened. The tool refuses
without the sha, refuses a second run while `data/_labs/efv_v3/efv_v3_confirm.json` exists,
and is the look record this file's s2.2 names for R-VM look 1. The candidate it reads is eFV
v3 at the configuration committed in `data/efv_v3_spec.json` (sha256 88d46b4b00f601e46cd5c5aeee97b5e0b64da346ef6646c7e118d565b466babd) at commit
1a546ad4fc488dec9b9cd6681cf657626c000b1e, selected on the development frames by the rule of `EFV_V3_BACKTEST.md` s2; the
served eFV (V2 as assembled) is read beside it as a comparator, so the V2 number on the
reserved frames is also read once, by the same run. No served number moves: `efv_v3.EFV_V3_ON`
is False and the ship task (EFV3_W3_SHIP) reads the artifact.

### 11.2 The preconditions of s1 at this registration

| id | state at registration |
|---|---|
| P1 | MET: the fWAR label epoch's freeze (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`, step Z, label `fwar@2026-10-02-0341299c20ec`). |
| P2 | UNMET, waived by EW2-6: EV-05's F-LV floors (`data/efv_lv_floor.json`) do not exist. The confirmation read carries its own E_cond and E_refit intervals on the reserved frames themselves. |
| P3 | UNMET, waived by EW2-6: the v1 parity lab was not built. |
| P4 | RE-TAKEN HERE: `data/efv_v2_assembly.json` sha256 35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823; `efv_v2_model.py` sha256 3134c039922c463893c0930377d8b85f113f9e1f915137a47cd8537bb35b4929; `efv_v2_stat.py` sha256 0a1db56abe2cac3528563b1538291b3dabc994b5694b814c52824d9ce73c07c3; `data/efv_v3_spec.json` sha256 88d46b4b00f601e46cd5c5aeee97b5e0b64da346ef6646c7e118d565b466babd. The s4.3 table above keeps its draft-time eWAR v2 values; the P5 weights are hit w_skill 0.908861 w_time 0.202573, pit w_skill 1 w_time 0.020473 (`data/efv_v2_assembly.json`, 2026-10-04). |
| P5 | MET: the weights re-derived once on the frozen label (2026-10-04) and DS-16 re-run once on it (2026-10-08, `data/efv_v2_dev_eval.json` ds16). |
| P6 | SUPERSEDED by EW2-6 and EW2-7 (what ships, and on what reading, is fixed there); PROGRAM.md Q3 and Q4 stay open and decide nothing here. |
| P7 | UNMET, waived by EW2-6: the look runner EV-13 (`tools/efv_v2_look.py`) was not built; `tools/efv_v3_backtest.py --confirm` plays its part for this one read (refuses without the sha, refuses a spent read, pins its inputs by sha256 in the artifact). |

The s9 results section stays empty: the reserved numbers live in
`data/_labs/efv_v3/efv_v3_confirm.json` and in `EFV_V3_BACKTEST.md` s5, and the ledger rows
(frames lv_res and vm_pros, model efv_v3, trigger look) in `data/efv_progress.json`. The
forking-path denominator of s6 gains the selection's evaluated steps (every one recorded in
`data/_labs/efv_v3/efv_v3_select.json`) and the two reserved reads.

## Note 2026-10-14: the eFV v5 metric atlas reads spent R-VM debut cohorts (EW3-1, EW3-5)

EFV5_METRIC_ATLAS (`efv5_atlas.py`, artifact `data/efv5_metric_atlas.json`, development
only, nothing served) scores every MiLB metric raw and INCREMENTAL over PROSPX consensus FV
on (player, season S) rows. Its horizon-censored labels (reached MLB by 2026; fWAR per MLB
season through 2026) and its reach3 label at S 2022 and 2023 read first MLB seasons of 2025
and 2026, which are the R-VM debut cohorts this registration reserved and the 10-08
confirmation (s11) spent. The owner authorised these short-horizon, consensus-scored reads
for the tracking era (decision EW3-1, 2026-10-14) and waived the registered dates (EW3-5), so
the atlas takes them as an OWNER-WAIVED EARLY READ: every such cell is flagged
`reserved_overlap` and labelled spent, the candidates list keeps those cells apart from clean
cells, and nothing is selected or tuned on them. No R-LV list vintage (2020, 2021) was built:
`efv5_atlas.CONSENSUS_VINTAGES` leaves them out and `test_efv5_atlas.py` pins it. No cell is
cut by consensus-FV level.

## Note 2026-10-15: the eFV v5 group drivers read the spent R-LV and R-VM frames once (EW3-5, EW2-10)

EFV5_GROUP_DRIVERS (`efv5_group_drivers.py`, `docs/efv-v2/EFV_V5_BACKTEST.md`) selected a
configuration on lv_dev and vm_dev only (two Single-A hitter group columns, wOBA and
slugging, at the skill head; commit 50fb0e3b) and then read it once on R-LV (list vintages
2020 and 2021) and R-VM (the 2025 debut cohort), opened through this registration's committed
sha `e7931ce4e13110eebb53555bff455ff13ca7c502` exactly as the v4 spent read was. These frames
were spent by the 10-08 confirmation (s11); this is not a look: every block is labelled
"spent frame, read after the 10-08 confirmation", nothing was chosen or tuned on it, and no
progress-ledger row was written. The owner waived registered dates and look days (EW3-5,
2026-10-14), so the read is recorded as an OWNER-WAIVED read of spent frames. Result
(`data/_labs/efv5/efv5_group_spent.json`): v5 minus V2 within -0.0030 on R-LV (E_refit CI95
-0.0099 to +0.0001) and 0 on R-VM (identical rows); the ship rule EW2-10 fails and
`EFV_V5_ON` stays False. No cell is cut by consensus-FV level. The forking-path count of s6
gains the selection's 81 evaluated steps (28, 27 and 26 over three rounds) and this one spent
read.

## Note 2026-10-15: the eFV v5 atlas tool-grade and Statcast recheck reads spent R-VM debut cohorts (EW3-7, EW3-5)

EFV5_ATLAS_TOOLS_STATCAST (`efv5_atlas_tools.py`, artifacts `data/efv5_atlas_tools.json` and
`data/_labs/efv5/efv5_atlas_tools_cells.json`, development only, nothing served) reruns the
metric atlas's method on two new families: scouting tool grades as of each list (FanGraphs and
MLB Pipeline boards inside the V window, never a board of another list vintage) and the
individual tracked Statcast components (Triple-A 2022 to 2025, Florida State League 2021 to
2025). Like the first atlas it reads the horizon-censored labels and reach3 at S 2022 and 2023,
whose windows reach the R-VM debut cohorts this registration reserved and the 10-08
confirmation (s11) spent. Under the owner's EW3-1 and EW3-7 and the waiver of registered dates
(EW3-5) these are an OWNER-WAIVED EARLY READ: every such cell is flagged `reserved_overlap` and
labelled spent, the candidates list keeps them apart, and nothing is selected on them. No R-LV
list vintage (2020, 2021) was built and no tool grade from a 2020 or 2021 board was read
(`efv5_atlas.CONSENSUS_VINTAGES` and the V-window read, pinned in `test_efv5_atlas_tools.py`).
No cell is cut by consensus-FV level.

## Note 2026-10-15: eFV v5 COMBINED reads the spent R-LV and R-VM frames once (EW3-5, EW3-8, EW3-9)

EFV5_COMBINE_WEIGHT_SHIP (`efv5_combined.py`, `docs/efv-v2/EFV_V5_COMBINED.md`) fixed its method before
any fit (commit fa60063c), fit one jointly weighted model of every atlas driver on lv_dev and vm_dev with
the penalty chosen inside each fold's own training years, and then read it ONCE on R-LV (list vintages
2020 and 2021) and R-VM (the 2025 debut cohort), opened through this registration's committed sha
`e7931ce4e13110eebb53555bff455ff13ca7c502` exactly as the v4 and v5 spent reads were. These frames were spent by the 10-08
confirmation (s11); this is not a look: every block is labelled 'spent frame, read after the 10-08
confirmation', nothing was chosen or tuned on it, and no progress-ledger row was written. The owner waived
registered dates and look days (EW3-5), so the read is recorded as an OWNER-WAIVED read of spent frames.
Result (`data/_labs/efv5/efv5_combined_spent.json`): v5c minus V2 within -0.0032 on R-LV
(E_refit CI95 -0.0369 to +0.0171) and -0.0288 on R-VM (E_refit
-0.0744 to +0.0756); the ship rule EW3-9 fails and
`EFV_V5_COMBINED_ON` stays False. A first build of the read aborted inside a column
builder before any statistic was computed (section 11 of the document). No cell is cut by consensus-FV level.
The forking-path count of s6 gains this one joint fit and this one spent read.

## Amendment 2026-10-15: the 2026-season holdout reads the R-VM cohorts before look 2 (EW3-13, EW3-5)

Owner decision EW3-13 (2026-10-15, verbatim: "The 2026 season is resolved (we're only scoring
the regular season where WAR is accumulated), please use it to improve eFV further"; asked how:
TEST ONCE, THEN TRAIN) under the waiver of registered dates EW3-5 (2026-10-14). This
amendment is dated and committed BEFORE any 2026-season number is read. It WAIVES, for the
reads registered in `docs/efv-v2/EFV_2026_HOLDOUT.md` only, the rule of s2.2 that R-VM look 2
(the 2025 and 2026 debut cohorts) waits for the 2027 season: that document scores the current
raters once on the 2026 regular season (F-2026-LIST, the preseason 2026 lists; F-2026-DEBUT,
the 2025 debut class's 2026 season and the 2026 debut class's first season), every rater
frozen at the 2026 opening day (2026-03-25). The cohorts are opened through
`efv_vintage_frame.guard_vm_request` on this registration's committed sha
`e7931ce4e13110eebb53555bff455ff13ca7c502`, as the v3, v4 and v5 spent reads opened R-VM;
`source_backtest.CANDIDATE_YEARS` and `efv_model.SCORED_YEARS` are not widened and
`reserved_vm_pins()` stays empty. This is an OWNER-WAIVED EARLY READ of the R-VM cohorts on a
one-season label; it is not R-VM look 2 and spends none of look 2's alpha (the O'Brien-Fleming
schedule of s2.2 is untouched for the career-WAR looks). No R-LV list vintage (2020, 2021) is
built and nothing is cut by consensus-FV level. After the read a dated note below marks the
2026-season frames SPENT.
