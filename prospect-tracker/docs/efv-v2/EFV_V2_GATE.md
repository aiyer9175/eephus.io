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
