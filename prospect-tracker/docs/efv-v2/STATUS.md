# eFV v2: where it stands (2026-09-25)

Every number below is copied from the `ds16` block of `data/efv_v2_dev_eval.json` (generated
2026-09-25T21:28:38Z by `tools/efv_v2_dev_read.py --ds16`, code at 0dbe3a4f), the one
pre-declared development read of the assembled Driver System V2 (DS-16). The read was declared,
with its statistic, in the DS-15 draft `docs/efv-v2/EFV_V2_GATE.md` s7, committed at 0dbe3a4f
before it ran. It is a DEVELOPMENT read on SPENT frames with the eWAR v2 label: it adjudicates
nothing, selects nothing (V2 is the one candidate), and is not the registered development number
(that is its re-run on the frozen fWAR label, gate precondition P5). No em-dashes.

2026-10-08: the `ds16` block now holds that re-run (the registered development number, P5),
and the numbers in the sections below are the 2026-09-25 eWAR v2 read, kept as written. The
re-run's numbers are in the dated log entry of 2026-10-08.

## The short answer

**V2 ties PROSPX consensus on both development frames, under both statistics.** It is level with
consensus to within a few thousandths, every interval spans zero by a wide margin, and nothing here
is a lead. On the list-vintage frame, where consensus is weakest and new information has room, V2
recovers the ground eFV v1 loses to consensus (v1 trails by about 0.015; V2 by 0.0005) but does not
pass consensus. On the vintage-matched frame V2 sits a hair under both consensus and v1.

## The numbers

Primary statistic: size-weighted within-(side, vintage) Spearman over groups of at least 20 rows
(`efv_v2_stat`, owner answer DS-Q3). Secondary: pooled Spearman after the identical output map (each
rater's order inside (side, vintage) placed onto consensus's values). Intervals: paired,
player-clustered bootstrap, B 2000, seed 20260906, E_cond (scores fixed, players resampled).
mde95 is 1.645 x the SD of the drawn deltas.

### List vintage, development (lv_dev): V 2017 to 2019, W3 label, n 2,862 (1,463 hit / 1,399 pit), 1,753 players, 6 groups

| rater | within | pooled | contributor AUC |
|---|---|---|---|
| V2 | 0.1619 | 0.1478 | 0.7477 |
| eFV v1 | 0.1477 | 0.1375 | 0.7388 |
| PROSPX consensus | 0.1624 | 0.1496 | 0.7476 |
| MLB Pipeline (own rows, n 2,574) | 0.1914 | 0.1609 | 0.7446 |
| FanGraphs (own rows, n 2,370) | 0.1398 | 0.1159 | 0.7030 |

| comparison | within delta (CI95) | mde95 | pooled delta (CI95) |
|---|---|---|---|
| V2 minus consensus | -0.0005 (-0.0197 to +0.0172) | 0.0155 | -0.0018 (-0.0199 to +0.0161) |
| V2 minus v1 | +0.0142 (-0.0134 to +0.0421) | 0.0233 | +0.0103 (-0.0140 to +0.0338) |
| v1 minus consensus | -0.0147 (-0.0416 to +0.0128) | 0.0231 | -0.0121 (-0.0355 to +0.0109) |
| V2 minus MLB Pipeline (n 2,574) | -0.0277 (-0.0558 to +0.0014) | 0.0240 | -0.0110 (-0.0374 to +0.0143) |
| V2 minus FanGraphs (n 2,370) | +0.0249 (-0.0063 to +0.0552) | 0.0264 | +0.0379 (+0.0073 to +0.0671) |

AUC, V2 minus consensus: +0.0001 (-0.0134 to +0.0143). Contributor threshold `w*` 1.19 W3 (labels
only). 29 rows whose player debuted in 2025 or later were kept at W3 = 0 under the gate's B9b
policy (their debut is outside V..V+3; no 2025+ season is read).

### Vintage-matched, development (vm_dev) at frame version vm2: debut years 2017 to 2023, career WAR, n 803 (388 hit / 415 pit), 14 groups

The rows are the served timing-pinned frame's rows: consensus reads 0.4129 pooled on them, the
served `pooled_efv_common_vintage_matched_vm2` value. The within statistic uses 788 rows in 13
groups (pitchers 2017 hold 15 rows, under the 20-row floor).

| rater | within | pooled | contributor AUC |
|---|---|---|---|
| V2 | 0.3755 | 0.4071 | 0.7511 |
| eFV v1 | 0.3852 | 0.4091 | 0.7523 |
| PROSPX consensus | 0.3813 | 0.4129 | 0.7492 |
| MLB Pipeline | 0.3760 | 0.4128 | 0.7559 |
| FanGraphs | 0.3341 | 0.3738 | 0.7283 |

| comparison | within delta (CI95) | mde95 | pooled delta (CI95) |
|---|---|---|---|
| V2 minus consensus | -0.0057 (-0.0231 to +0.0116) | 0.0146 | -0.0058 (-0.0215 to +0.0096) |
| V2 minus v1 | -0.0097 (-0.0346 to +0.0165) | 0.0209 | -0.0021 (-0.0233 to +0.0187) |
| v1 minus consensus | +0.0039 (-0.0206 to +0.0285) | 0.0202 | -0.0037 (-0.0235 to +0.0164) |
| V2 minus MLB Pipeline | -0.0005 (-0.0356 to +0.0333) | 0.0284 | -0.0057 (-0.0328 to +0.0213) |
| V2 minus FanGraphs | +0.0415 (+0.0039 to +0.0778) | 0.0314 | +0.0333 (+0.0012 to +0.0662) |

AUC, V2 minus consensus: +0.0020 (-0.0064 to +0.0106).

On this frame V2 is the consensus order on 295 of the 803 rows: the admission rule admits no
hitter driver in the 2017 to 2019 folds and no pitcher driver in the 2017 to 2020 folds, so there
V2 cannot differ from consensus by construction. It moves only on hitters from 2020 and pitchers
from 2021 (the K rate).

Note the pooled column for v1 on vm2: 0.4091 after the map against 0.3930 on its own raw scale
(the served headline-candidate figure). The 0.016 gap is the price v1 pays for pooling separately
fitted scales (bug B5); under the map it disappears, and v1 then trails consensus by 0.004 pooled
rather than 0.020.

## What it means

1. **No lead on development.** V2 minus consensus is -0.0005 (lv_dev) and -0.0057 (vm2) on the
   primary statistic, with intervals about 0.035 wide. The honest reading is a tie, which is the
   modal outcome DRIVER_SYSTEM_V2.md s4.4 predicted before the build.
2. **V2 repairs v1 where v1 was losing.** On the list-vintage frame V2 is +0.014 within over v1
   (not resolved: CI -0.013 to +0.042) and closes most of v1's -0.015 gap to consensus. On vm2 it
   is 0.010 under v1 within (not resolved). Both are consistent with the design intent: consensus
   sets the level, the drivers only reorder inside groups, and the self-inflicted losses (pooled
   scales, pinned 0.70 / 0.57 weight, the pitcher missingness proxy) are gone.
3. **The industry.** V2 is ahead of FanGraphs on both frames (the pooled intervals exclude zero on
   both; the within interval excludes zero on vm2 only), and behind MLB Pipeline on lv_dev by 0.028
   within (the interval just touches zero), level on vm2. These are secondary, uncorrected for
   testing several sources, and on spent frames: descriptive only.
4. **Reserved reads.** The R-LV floor is about 0.017 to 0.021 (to be measured by EV-05) and the
   R-VM look-1 floor about 0.060. A development delta of -0.0005 to -0.006 gives V2 almost no
   chance of clearing either; the expected reserved outcome is "ties consensus", which is also the
   label the board carries under owner answer DS-Q1. Protection status and the pitcher K rate, the
   two inputs consensus does not already hold, are in V2 on list vintages; on this read they did
   not move V2 past consensus.
5. **Forking paths.** This read adds 2 probes (one per frame) to the program's count
   (`data/xfv_arm_ledger.json` now lists 42 validity probes beside 80 arms). With about 275 to 347
   earlier looks at these frames, no single development CI here is evidence on its own.

## What happens next

- After the fWAR label freeze (about 2026-10-05): the DS-08 rule re-derives the weights once on the
  frozen label, DS-16 re-runs once (the registered development number), EV-05 measures the F-LV
  floors, and the gate's pending items (P1 to P7) are filled.
- The gate commits as REGISTERED, alone, with an empty results section; only then can R-LV
  (V 2020 and 2021) or R-VM (2025+ debuts) be read, once each, not before 2026-12-01.
- Serving V2 on the board (DS_F_serve_v2, owner answer DS-Q1) is a separate task; nothing here
  moves the served grade.

## 2026-10-08: the model-class screen (EFV3_C03), no arm admitted

Every number here is copied from `data/efv_v2_model_class_screen.json` (generated
2026-10-08T18:30:31Z by `tools/efv_v2_model_class_screen.py` at `ad521ba6`, one process, 259.5 s,
stdout and stderr teed before anything else ran), the ONE pre-declared screen of
`docs/efv-v2/MODEL_CLASS_SCREEN.md` (declared at `60373829`, 2026-10-02, before any read). Label
`fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026); V2 base at the P5 weights
(`data/efv_v2_assembly.json` sha256 `35fe32c7...2823`; hit w_skill 0.908861 w_time 0.202573, pit
w_skill 1.0 w_time 0.020473). Frames: lv_dev at list vintages 2017 to 2019 (W3, n 2,862, 1,753
players, 6 groups, 29 reserved_vm rows kept at W3 = 0) and vm_dev at frame version vm2 (debut years
2017 to 2023, career WAR to date, n 830, 14 groups). The V2 base was refit per fold on the same rows
and reproduced the DS-16 block before any arm was scored (V2 within 0.1676 lv and 0.3713 vm,
consensus 0.1792 and 0.3814, n and groups equal; `base_parity.reproduces` true). Guards asserted
first: list vintages read [2017, 2018, 2019], vm years read 2017 to 2023, `reserved_vm_pins()` empty,
rule years at most 2016; no list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is
grouped by consensus-FV level. Statistic: within (side, vintage) Spearman (primary), pooled after
the identical output map (secondary), contributor AUC (veto); `efv_v2_stat.paired_delta`, E_cond,
B 2000, seed 20260906; twin one draw at the seed; permutation null 500 draws; Holm m 5 on the vs-V2
within leg. This is a DEVELOPMENT read on SPENT frames: it adjudicates nothing, selects nothing,
moves no served number, and is not a claim. The frames are spent for every arm (`spent`, 10 reads);
no arm is re-run on them.

| arm | lv within vs V2 (CI95) | vm within vs V2 (CI95) | lv vs consensus (CI95) | vm vs consensus (CI95) | twin lv / vm | folds same sign lv / vm | perm p lv / vm | Holm p | verdict |
|---|---|---|---|---|---|---|---|---|---|
| MC-1 pairwise head | -0.0070 (-0.0129 to -0.0011) | -0.0027 (-0.0077 to +0.0023) | -0.0186 (-0.0448 to +0.0072) | -0.0127 (-0.0424 to +0.0141) | +0.0102 / +0.0070 | 3 of 3 (negative) / 4 of 7 | 0.998 / 0.886 | 1.0 | NOT ADMITTED (1, 2, 3, 4, 5 AUC veto fired, 6) |
| MC-2 reliability anchor | +0.0141 (-0.0003 to +0.0282) | -0.0188 (-0.0430 to +0.0053) | +0.0024 (-0.0192 to +0.0234) | -0.0288 (-0.0618 to +0.0043) | +0.0141 / -0.0191 | 3 of 3 / 5 of 7 (negative) | 0.048 / 0.950 | 1.0 | NOT ADMITTED (1, 2, 3, 4, 6) |
| MC-3 two-band weight | -0.0004 (-0.0129 to +0.0120) | +0.0005 (-0.0248 to +0.0243) | -0.0120 (-0.0256 to +0.0005) | -0.0096 (-0.0319 to +0.0121) | +0.0007 / -0.0057 | 1 of 3 / 3 of 7 | 0.541 / 0.499 | 1.0 | NOT ADMITTED (1, 2, 3, 4, 6) |
| MC-4a sign-constrained | -0.0001 (-0.0002 to 0.0) | 0.0 (0.0 to 0.0) | -0.0117 (-0.0331 to +0.0093) | -0.0101 (-0.0391 to +0.0160) | +0.0103 / +0.0082 | 1 of 3 / 0 of 7 | 0.906 / 1.0 | 1.0 | ADOPTABLE on non-inferiority alone; NOT ADMITTED (1, 2, 4, 6) |
| MC-4b I-spline | +0.0007 (-0.0053 to +0.0065) | -0.0073 (-0.0175 to +0.0027) | -0.0110 (-0.0337 to +0.0118) | -0.0174 (-0.0465 to +0.0102) | +0.0108 / +0.0082 | 2 of 3 / 3 of 7 | 0.377 / 0.966 | 1.0 | NOT ADMITTED (1, 2, 3, 4, 6) |

mde95 of the vs-V2 within leg, from this screen's own draws: MC-1 0.0051 lv / 0.0042 vm, MC-2 0.0119 /
0.0199, MC-3 0.0103 / 0.0207, MC-4a 0.0001 / 0.0, MC-4b 0.0050 / 0.0085 (the arms share V2's anchor,
so the paired SD sits below the DS-16 floors of 0.0180 lv and 0.0229 vm against consensus, as the
registration expected). Against MLB Pipeline, within, lv: MC-1 -0.0410, MC-2 -0.0152, MC-3 -0.0339,
MC-4a -0.0334, MC-4b -0.0321 (n 2,574); vm: -0.0130, -0.0290, -0.0098, -0.0103, -0.0176 (n 830).
Against FanGraphs, lv: -0.0015, +0.0152, +0.0051, +0.0061, +0.0072 (n 2,370); vm: +0.0323, +0.0162,
+0.0355, +0.0350, +0.0277 (n 830); every one of these intervals spans zero except MC-1 and MC-3 vs
Pipeline on lv (below zero). Holm (m 5, p = the larger of the two frames' shares of draws at or below
zero): MC-3 0.501, MC-4b 0.931, MC-2 0.935, MC-1 0.986, MC-4a 1.0; every adjusted p is 1.0.

What the screen says, in order:

1. **No arm is admitted; MC-4a is marked adoptable.** Clause 1 (+0.005 over V2 on BOTH frames)
   fails for every arm, and no arm survives Holm. MC-4a meets non-inferiority on both frames (its
   lower bounds are -0.0002 and 0.0) with no AUC veto, so the rule marks it ADOPTABLE under lane C
   E3-Q3 = A, with no margin claim: coded behind `V2_SIGN_CONSTRAINED = False`, read beside V2 by
   the look runner, the flag off until a registered look passes, flipped only through EV-15.
2. **MC-4a is V2.** The active-set rule zeroed one slope in 20 folds (lv pit 2017, the timing
   head's `milb_absent`, admitted sign -1, unconstrained slope +0.346) and none on the vm folds,
   which are the production fit's frame. Its vs-V2 deltas are -0.0001 lv and exactly 0.0 vm; its
   adoptable mark changes nothing a fold has fitted so far, which EFV3_C04 should say when it carries
   the mark.
3. **MC-2's list-vintage lift is the anchor, and its reliability weighting is inert there.** On
   lv_dev MC-2 reads +0.0141 over V2 (CI95 -0.0003 to +0.0282; mde95 0.0119; permutation p 0.048;
   positive on all 3 folds; contributor AUC +0.0200, CI95 +0.0076 to +0.0318) and +0.0024 over
   consensus (CI95 -0.0192 to +0.0234): it recovers the ground V2 gives up to consensus on this frame
   and no more. But every reliability weight in its lv table is exactly 1.0 (artifact
   `frames.lv_dev.reliability.table`): FanGraphs grades begin at list vintage 2017, so no source but
   Pipeline has history at vintages at most V - 3 for V 2017 to 2019, and one source with history is
   its own mean, shrunk to 1.0. The anchor is therefore the EQUAL-weight mean of the two sources'
   within percentiles (the single-source shrink applied), the twin (weights exchanged across sources)
   is the arm itself (+0.0141 = +0.0141) and clause 4 cannot hold by construction. On vm_dev, where
   both sources have history from 2020 (Pipeline weights 1.11 to 1.32 for hitters), MC-2 reads
   -0.0188 vs V2 (CI95 -0.0430 to +0.0053) and -0.0288 vs consensus, negative on 5 of 7 years. The
   registration's disclosure stands: the arm was designed after reconciliation S1 was seen, and its
   development read is not evidence; only R-LV is.
4. **The twins of the driver arms read ABOVE V2 on both frames.** With the driver columns permuted
   within vintage, the DS-06 rule refuses nearly every driver, the twin collapses to the consensus
   order, and that order beats V2 by +0.0102 lv / +0.0070 vm (MC-1 twin), +0.0103 / +0.0082 (MC-4a),
   +0.0108 / +0.0082 (MC-4b), inside their intervals but the same size and sign as the DS-16 gap
   (V2 minus consensus -0.0116 lv, -0.0101 vm). Read plainly: on the frozen fWAR label the
   admitted drivers subtract about 0.01 within on both development frames, which no change of
   estimator over the same drivers recovers (MC-1, MC-4a, MC-4b each stay at or below V2). The
   information set, not the class, is the bound (s0.2), on this label as on the last one.
5. **MC-1 is below V2 on lv_dev.** -0.0070 (CI95 -0.0129 to -0.0011), negative on all 3 folds, and
   its contributor AUC delta -0.0121 (CI95 -0.0187 to -0.0061) is below minus its own mde95 (0.0054),
   so the veto fired: the registered answer to "why not a ranking loss" is that the pairwise head
   loses to the squared-error head on these rows. The listwise weighting (a sensitivity, selected
   nowhere) reads -0.0169 lv (CI95 -0.0433 to +0.0121) and -0.0112 vm (CI95 -0.0388 to +0.0174).
6. **MC-3 and MC-4b sit inside their floors.** MC-3 -0.0004 / +0.0005 at band weights hit upper
   (0.027, 0.328) lower (0.556, 0.061), pit upper (1.0, 0.0) lower (0.321, 0.170), the rule reading
   years 2011 to 2016 only; MC-4b +0.0007 lv (all six folds splined) and -0.0073 vm (CI95 -0.0175 to
   +0.0027; the 2017 to 2019 vm folds fell back to MC-4a under 300 has-block training rows and the
   artifact says so).
7. **Outside the family.** The rank-consistent combiner weight (lane C E3-Q2 = A) chooses hit
   (w_skill 1.0, w_time 0.0) and pit (0.5, 0.1) on the rule rows; V2 at those weights against V2 at
   the DS-08 weights reads -0.0027 lv (CI95 -0.0079 to +0.0028) and +0.0054 vm (CI95 -0.0065 to
   +0.0186), selected nowhere. MC-5 (the pricing line with position family and age at the read,
   through `tools/efv_v2_pricing_calibration`'s own run at the P5 weights, order_idx bit-identical
   on every fold): MAE 0.9405 to 0.9501 on lv_dev (delta +0.0096, CI95 +0.0038 to +0.0157, a larger
   error) and 3.6982 to 3.7058 on vm_dev (+0.0076, CI95 -0.0128 to +0.0283); calibration in the
   large per family moves hit corner from -0.25 to +0.02 and hit middle from 0.00 to -0.12 on lv (mean
   residual, outcome minus price). An MAE diagnostic, no rank claim, no served price moves (EV-15).
8. **Forking paths.** The screen adds 10 reads (5 arms on 2 frames) to the denominator:
   `data/xfv_arm_ledger.json` now lists 59 validity probes beside 392 arms (was 49; the arm count is
   unchanged, a probe is not an arm). Ten development rows landed in `data/efv_progress.json`
   (model `efv_v2_mc_1` to `efv_v2_mc_4b`, role development, resolvable none, verdict the admission
   text). EFV3_C04 writes the count into the gate's s6.
9. **What EFV3_C04 carries into the gate.** No arm on the admission rule. MC-4a as ADOPTABLE (lane
   C E3-Q3 = A), with item 2 above. MC-2 is not admitted by the rule; whether it still enters as the
   labelled secondary that owner answer E3-Q4 = A names (s9 of the registration lists MC-2 beside
   "admitted arms") is for C04 and the owner, with item 3 above attached to any such row. The
   rank-rule sensitivity enters as a sensitivity only.

## Dated log

- 2026-10-08: the model-class screen (EFV3_C03) ran once on the frozen fWAR label (`tools/efv_v2_model_class_screen.py` at `ad521ba6`, rc 0, 259.5 s, after one `--check` pass that built the frames and reproduced the DS-16 base; artifact `data/efv_v2_model_class_screen.json`, generated 2026-10-08T18:30:31Z): no arm admitted on the registered rule, MC-4a marked adoptable on non-inferiority alone, the driver-permuted twins above V2 on both frames; ten probes in `data/xfv_arm_ledger.json` (49 to 59) and ten development rows in `data/efv_progress.json`. The dated section above carries every number. Nothing served moves.
- 2026-10-08: the screening lab's one registered run (EFV3_B7, gate s10) on the frozen fWAR label. `python tools/efv_screen_lab.py` from HEAD `b17c2027`, generated 2026-10-08T18:01:30Z, 259.2 s, after one `--check` pass (frame counts only) and the lab's 34 fixture tests. The process exited rc 1: the artifact was written in full (atomic replace; the `wrote` line precedes the traceback) and the console echo after it raised `TypeError` on the withheld arm's None verdict; the lab was not re-run, the echo is repaired in this commit (`verdict_line`), and the arm and progress ledgers were regenerated from the written artifact by the ledger tools (OWNER_QUESTION B7-Q1 in the task's output directory records the default taken). Inputs: label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026); `data/efv_v2_assembly.json` sha256 `35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823` (the P5 re-fit; weights hit w_skill 0.908861 w_time 0.202573, pit 1.0 / 0.020473); B 2000, seed 20260906, E_cond, player clusters, 500 permutation draws, floor mode forced (the admitted mode's receipt beside it under `floors_other`). Frame: lv_dev, list vintages 2017 to 2019, n 2,862 (hit 1,465 / pit 1,397), w_star_dev 1.10; 29 reserved_vm rows kept at W3 = 0 (gate s5 B9b). Guards asserted before any score: `reserved_vm_pins()` empty, folds [2017, 2018, 2019], the combiner rule's last year 2016; no list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is grouped by consensus-FV level; vm_dev not screened; no closed arm re-run. Floors derived before any arm (MAX mde95 over three N(0,1) noise columns; within / pooled / AUC): skill hit 0.0034 / 0.0065 / 0.0046, skill pit 0.0075 / 0.0103 / 0.0099, timing hit 0.0009 / 0.0025 / 0.0025, timing pit 0.0003 / 0.0010 / 0.0009, both sides pooled skill 0.0042 / 0.0070 / 0.0051 and timing 0.0005 / 0.0010 / 0.0009 (the coverage arm reads the larger of the two). Holm family m 7, alpha 0.05, formed after every arm. Arms (within delta candidate minus base, CI95, lb95, floor, permutation p, Holm p, verdict): `txt_skill_hit` not measured, withheld before any read (report_absent reads IMBALANCED on hitters under DS-03, `efv_text_features.offered_columns`, gate s10.7), counted in m, no verdict; `txt_skill_pit` 0.0 (0.0 to 0.0), lb95 0.0, floor 0.0075, p 0.874, Holm p 1.0, admitted in 0 of 3 folds (2017 mean |t| 0.866; 2018 and 2019 sign flipped between training vintages), NULL; `txt_time_hit` -0.00308 (-0.0074 to +0.0013), lb95 -0.00678, floor 0.0009, p 1.0, Holm p 1.0, admitted 3 of 3, fold deltas -0.00723 / -0.00219 / -0.00020, pooled -0.00337 against floor 0.0025, AUC -0.00065, report_absent IMBALANCED on hitters (partial -0.1039, CI95 -0.1609 to -0.0463), NULL; `txt_time_pit` -0.0001 (-0.0008 to +0.0007), lb95 -0.0007, floor 0.0003, p 0.970, Holm p 1.0, admitted 3 of 3, fold deltas -0.00022 / -0.00026 / +0.00015, pooled -0.00262 (-0.0056 to -0.0003) against floor 0.0010, NULL; `milb_floor_2005` (coverage, both sides pooled, n 2,862) +0.00358 (-0.0112 to +0.0184), lb95 -0.00892, floor 0.0042, bootstrap one-sided p 0.329 (the s10.5 substitution), Holm p 1.0, fold deltas hit +0.01885 / -0.00306 / +0.00499 and pit 0 / 0 / 0 (pitchers withheld at 2014), pooled +0.00071, AUC +0.00056, NULL; `pick_overall_time_hit` 0.0, floor 0.0009, p 0.986, Holm p 1.0, admitted 0 of 3 (sign flipped between training vintages in every fold), NULL; `pick_overall_time_pit` 0.0, floor 0.0003, p 0.990, Holm p 1.0, admitted 0 of 3, NULL. Twins: every measured column arm's twin reads delta 0.0, inside its floor. AUC: no arm adverse beyond its floor. Balance probes on the frozen label (DS-03): txt_skill_pit_absent BALANCED (-0.0598, CI95 -0.1235 to +0.0008), txt_time_hit_absent IMBALANCED (above), txt_time_pit_absent BALANCED (-0.0598, -0.1152 to +0.0020), pick_overall_time_hit_absent BALANCED (-0.0284, -0.0751 to +0.0198), pick_overall_time_pit_absent BALANCED (+0.0098, -0.0410 to +0.0639). Result: no arm is admitted; the candidate list of s4.2 is unchanged and no amendment is written; `efv_v2_model.V2_SCREEN_CANDIDATES_ON` is created at False with an empty `V2_SCREEN_ADMITTED` (test-pinned: with it off the candidate lists, the fitted heads of `efv_v2_serve.production_models()` and `data/efv_v2_assembly.json` are the committed module's); a NULL arm is not re-run on any other frame, estimator or seed (kill rule 2); wave 2 may now be registered in s10 as its own family. Downstream, same commit: `data/xfv_screen_wave1.json` (`screening.exploratory` false, `floors` before `arms`); six arm rows in `data/xfv_arm_ledger.json` (392 to 398 arms, 49 probes, 0 of 357 scoreable arms cleared their own floor; `xfv_screen_wave1.json` leaves the ledger's PENDING set); six development rows (model `efv_v2_screen:wave1:<arm>:<side>`, frame lv_dev, resolvable null) in `data/efv_progress.json` (66 to 72 rows; no served row appended: the lab now appends through `efv_progress.update_screening`, its own rows alone, and the served rows stay the nightly's). The Source Comparison page lists the six rows in its collapsed screening block and charts none. Nothing served moves: the served eFV grade reads neither this artifact nor the flag. Disclosure: the DS-03 receipts in `data/efv_identity_balance.json` that decide which text heads are offered (`text`, `pick`) were taken on the eWAR v2 label on 2026-10-03, before the freeze, and were not re-run here; the lab's own balance probes above are on the frozen label.
- 2026-10-08: P5, DS-16 re-run once on the frozen fWAR label (the registered development number). `python tools/efv_v2_dev_read.py --ds16 --no-ledger` (rc 0, 76 s, after one `--check` pass that built the frames and printed counts only), from HEAD `8e2361f4` with one uncommitted text-only change to the producer (the block's `note` and the `w_star_dev` convention string now name the label the read ran on; no frame, score or statistic code changed), generated 2026-10-08T17:39:23Z. Registration: `docs/efv-v2/EFV_V2_GATE.md` s7 and precondition P5 (DS-16 re-run ONCE on the frozen label), `DRIVER_SYSTEM_V2.md` DS-16 row; the producer names the gate draft at `72ac7098` (status DRAFT), and the first DS-16 read (2026-09-25, `82f69d5e`) is the only earlier one. Inputs: label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026); `data/efv_v2_assembly.json` sha256 `35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823` (the P5 re-fit, `c40c0dd0`; weights hit w_skill 0.908861 w_time 0.202573, pit w_skill 1.0 w_time 0.020473); `efv_v2_stat.py` sha256 `0a1db56a...07c3`; `efv_v2_model.py` sha256 `aaa002e8...daea`; B 2000, seed 20260906, E_cond, player clusters. Frames: lv_dev list vintages 2017 to 2019 (W3, contributor at w_star_dev 1.10, was 1.19 on eWAR v2) and vm_dev at vm2 (debut years 2017 to 2023, career WAR to date). Guards asserted before any score: lv vintages read [2017, 2018, 2019], vm years read 2017 to 2023, `reserved_vm_pins()` empty, the combiner rule's last year 2016 below the first scored year; 29 reserved_vm rows kept at W3 = 0 (gate s5 B9b). No list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is grouped by consensus-FV level. Primary (within (side, vintage) Spearman), V2 minus consensus, before (eWAR v2 label and weights) and after: lv_dev n 2,862 (hit 1,463 to 1,465, pit 1,399 to 1,397), V2 0.1619 to 0.1676, consensus 0.1624 to 0.1792, delta -0.0005 (CI95 -0.0197 to +0.0172) to -0.0116 (CI95 -0.0332 to +0.0095), mde95 0.0155 to 0.0180; vm_dev n 803 to 830 (within rows 788 to 814, 13 groups), V2 0.3755 to 0.3713, consensus 0.3813 to 0.3814, delta -0.00575 (CI95 -0.0231 to +0.0116) to -0.0101 (CI95 -0.0386 to +0.0159), mde95 0.0146 to 0.0229. Secondary (pooled after the identical output map): lv_dev -0.0018 (CI95 -0.0199 to +0.0161) to -0.0127 (CI95 -0.0354 to +0.0105); vm_dev -0.0058 (CI95 -0.0215 to +0.0096) to -0.00995 (CI95 -0.0356 to +0.0150). Contributor AUC: lv_dev +0.0001 to -0.0116 (CI95 -0.0290 to +0.0072); vm_dev +0.0020 to -0.0042 (CI95 -0.0193 to +0.0108). The other comparisons, within, after: lv_dev V2 minus v1 -0.0112 (CI95 -0.0353 to +0.0136), v1 minus consensus -0.0005 (-0.0234 to +0.0220), V2 minus Pipeline -0.0333 (-0.0641 to -0.0019, n 2,574), V2 minus FanGraphs +0.0061 (-0.0290 to +0.0402, n 2,370); vm_dev V2 minus v1 -0.0229 (-0.0533 to +0.0084), v1 minus consensus +0.0128 (-0.0104 to +0.0342), V2 minus Pipeline -0.0103 (-0.0528 to +0.0290), V2 minus FanGraphs +0.0350 (-0.0090 to +0.0775). Reading: every V2 versus consensus interval spans zero on both frames under all three statistics; on the frozen label V2 sits below consensus by about 0.01 on both frames and does not lead it. This is a development read on spent frames: it adjudicates and selects nothing and is not a claim. Downstream, same commit: two development rows (model efv_v2_ds_assembled, frames vm_dev and lv_dev) in `data/efv_progress.json` (64 to 66 rows; no other row appended); the two DS-16 probes in `data/xfv_arm_ledger.json` take the new numbers (49 probes, 392 arms, unchanged); `data/efv_label_pool_census.json` re-run (its floor curve copies this block's E_cond SDs: vm sd_ref 0.00886 to 0.01394 at n_ref 803 to 830, lv sd_ref 0.00944 to 0.01093; counts unchanged). Pins: `test_efv_v2_ds16.py::test_the_weights_are_the_registration` passes on the re-run; `test_efv_v2_gate.py::test_the_draft_carries_the_registered_weights` stays xfail because it needs the gate draft's s4.3 table re-taken, which belongs to the registration commit (EV-12, P4). Nothing served moves: the served eFV grade does not read this artifact.
- 2026-10-04: P5, the weights re-derived once on the frozen fWAR label. `python tools/efv_v2_assemble.py` (rc 0, 45 s, code at `487fb38e`, generated 2026-10-04T11:45:03Z) re-ran the DS-08 combiner rule and the DS-06 admission on label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026) on the lifted F-LV frame (EFV3_B3, `bfb73531`: hitters read the MiLB block from 2005, pitchers withheld at the served 2014). Weights, before (eWAR v2 label, RESOLVED_THROUGH 2025, 2026-09-25 build) and after: hitters w_skill 0.599508 to 0.908861, w_time 0.012287 to 0.202573 (rule rows 1,330 to 1,429); pitchers w_skill 1.0 to 1.0, w_time 0.107279 to 0.020473 (rule rows 1,038 to 1,158); the rule still reads years 2011 to 2016 only. Admitted over all development vintages, before: hit contact, tool_hit, milb_absent, nov_add; pit k_rel, nov_add. After: hit contact, is_college, milb_absent, nov_add; pit k_rel. Twenty arms and two probes, as before. `data/efv_v2_assembly.json` sha256 `422fc5439253ad13d867320b00b634a178e62a8b291025326056377d6d4436ec` to `35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823`; `data/xfv_arm_ledger.json` re-counted (its 20 assembly rows and 2 probes take the new verdicts; 392 arms, unchanged). No list vintage 2020 or 2021 and no 2025+ debut cohort was read (the assembler's guards ran first). The assembler's documented procedure does not re-run DS-16, so DS-16's one re-run on the frozen label (`tools/efv_v2_dev_read.py --ds16`, `data/efv_v2_dev_eval.json`) is OWED, and the gate draft's s4.3 table is re-taken at registration (P4). This is a refit, not a read: it scores no row and draws no accuracy conclusion. It moves the served eFV v2 grade (SERVE_EFV_V2 is on and `efv_v2_serve.production_models()` loads these weights) at the post-epoch landing rebuild.
- 2026-10-03: pricing. The MC-5 pricing read (EFV3_C05, `tools/efv_v2_pricing_calibration.py` at `0fcf9270`; artifact `data/efv_v2_pricing_calibration_eval.json`, generated 2026-10-04T02:37:47Z) ran on the frozen fWAR label (`fwar@2026-10-02-0341299c20ec`) after the epoch's step Z. It adds position family (the in-window listed position; pitchers by MiLB games-started share) and age at the read to the pricing line only. order_idx and the eFV grade are bit-identical with and without the term (asserted on every fold), so every Spearman and AUC delta is 0 and it carries no rank claim. MAE of efv_war, a labelled diagnostic, not a claim: lv_dev (n 2,862) 0.9323 base against 0.9423 with the term, delta +0.0100 (CI95 +0.004 to +0.016); vm_dev (n 830) 3.6728 against 3.6829, delta +0.0101 (CI95 -0.0101 to +0.0311). Out of fold the extended line prices no better on either frame and worse on lv_dev. Calibration in the large on lv_dev moves toward zero for corner hitters (mean residual -0.272 to +0.002) and relievers (-0.212 to -0.086) and away from it for middle-position hitters (-0.017 to -0.135) and starters (-0.180 to -0.280). Nothing served moves; the served price changes only through EV-15 after the reserved reads and the PROSPECT_ANCHOR look. Two development rows (model efv_v2_pricing_pos_age, metric mae) are in `data/efv_progress.json`.
- 2026-10-02: screening lab registered, no result. Section 10 of `docs/efv-v2/EFV_V2_GATE.md` (still DRAFT) registers wave 1, seven arms frozen at `d9fe7db4`; no lab number exists on the frozen label.
- 2026-10-02: the exploratory screening run (EFV3_B5, gate s10.11) was made on the eWAR v2 label at lab commit `9c541e92`, to a file outside the repository; no verdict, nothing admitted, no row under `data/`; its floors are advisory and the registered run derives its own. Still no lab number on the frozen label.
