# eFV v2 registration: EFV_V2_GATE

Registration status: DRAFT

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
  disagreement. Never consensus-FV cell.
- Kill rules 1 to 8 of PROGRAM.md s4 apply verbatim; a guard trip or any score found on R-LV
  or R-VM before its look turns that frame into development permanently for v2.
- Served state (owner DS-Q1): V2 leads the board once built, labelled "ties consensus" until
  a reserved read says otherwise. The comparator stays today's served consensus (DS-Q4).

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
two pick columns read their values (the pick builder in place of the sidecar stand-in); every
name, side, head, kind and re-test flag is as `d9fe7db4` froze it. Nothing is added to wave 1
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
label) is a development read of the same kind and formed no verdict. At this commit the
exploratory run has not run. Both count in s6.

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
| College production for draftees | CollegeSavant covers the 2021 and later classes, `draft_statlines` 2022 on, `.cache/amateur_leagues` 2021 on | a count-only StatsAPI probe of the college sport id for 2005 to 2020 decides (EFV3_B9); otherwise the 2021 class resolves W3 about 2029 |
| AAA and FSL Statcast, A-ball signals | tracking begins 2021 (FSL) and 2023 (AAA); the DB tables hold 2026 only; `data/signal_snapshots/` holds 2023 on | FSL-era V 2022 at RT 2027; AAA-era V 2024 at RT 2029; the chain's second link is screenable now (wave 2) |
| Modern pitch-level data, pitch rates | AAA pitch files begin 2023; `data/milb_pitch_rates.json` is 2026 only | as AAA Statcast; pitch rates per Q10_11, which owns their admission |
| Tracked physical data | bat speed 2023 on (AAA), bat tracking 2024 on, sprint and arm MLB only | 2027 and later (program D6) |
| eBR runner record | not built (`.cache/ebr` is empty) | after the eBR plan's integration task |
| BA, ESPN, Just Baseball and TJStats report text | first published 2023, 2025, 2026 and 2026 | R-LV never; V 2023 at RT 2027 (W3) |
