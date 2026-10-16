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

## 2026-10-08: eFV v3, selected on the development frames and read once on the reserved frames (EFV3_W3_SELECT_CONFIRM)

Decision EW2-6 (2026-10-08) replaced the 2026-12-01 reserved read with a same-day backtest:
select a configuration on the development frames only, commit it, read it ONCE on the reserved
frames. The rule, the step log and the confirmation read are in `docs/efv-v2/EFV_V3_BACKTEST.md`
(s2 fixed at `fc5b9cc0` before any combined read; s4 and s5 appended by the runs); the code is
`efv_v3.py` (`EFV_V3_ON = False`, dark) and `tools/efv_v3_backtest.py`; the artifacts are
`data/_labs/efv_v3/efv_v3_select.json`, `data/efv_v3_spec.json` and
`data/_labs/efv_v3/efv_v3_confirm.json`; the registration `docs/efv-v2/EFV_V2_GATE.md` reads
REGISTERED at `e7931ce4` with its s11 waiver, the sha the reserved guards opened on. Every number
below is copied from those artifacts. Label `fwar@2026-10-02-0341299c20ec`; V2 base at the P5
weights (assembly sha256 35fe32c7...2823); within (side, vintage) Spearman primary.

**Selection (development frames, spent):** 44 steps on the menu (3 anchors, 12 weight factors, 20
driver removals, 9 wave-2 columns), greedy, a step admitted at lv_dev scope delta >= +0.0020 and
vm_dev >= -0.0020, cap 6. Four admitted: the hitter skill head at a quarter of its P5 weight
(+0.02102 lv / +0.00190 vm), the hitter timing head at a quarter (+0.00388 / +0.02133), the
scouting command grade offered to the pitcher skill head (+0.00257 / 0), the pitcher K rate
withheld (+0.00305 / 0); round 5 none. The three anchors lifted lv_dev (+0.014 to +0.017) and
lowered vm_dev (-0.011 to -0.025), outside the tolerance. The selected configuration's
development read: lv_dev (n 2,862) +0.0155 over V2 (CI95 -0.0020 to +0.0330), +0.0039 over
consensus (-0.0035 to +0.0110); vm_dev (n 830) +0.0116 (-0.0064 to +0.0303) and +0.0015 (-0.0116
to +0.0138). Two development rows (model efv_v3) in `data/efv_progress.json`.

**Confirmation (reserved frames, one read):** R-LV (list vintages 2020 and 2021, n 2,349: hit
1,195 / pit 1,154) v3 within 0.1419, V2 0.1511, consensus 0.1494, Pipeline 0.1988 (own rows),
FanGraphs 0.1469; v3 minus V2 -0.0092 (E_cond CI95 -0.0306 to +0.0110; E_refit B 200 -0.0312 to
+0.0128), v3 minus consensus -0.0076 (E_cond -0.0229 to +0.0069; E_refit -0.0347 to +0.0057;
hitters +0.0051, pitchers -0.0207), v3 minus Pipeline -0.0336 (E_refit -0.0825 to -0.0013), v3
minus FanGraphs +0.0007; V2 minus consensus +0.0016 (-0.0201 to +0.0226). R-VM (the 2025 debut
cohort, vm2 rule, n 147: hit 72 / pit 75; the gate counted 149) v3 0.3555, V2 0.3739, consensus
0.3333, Pipeline 0.3142, FanGraphs 0.3568; v3 minus V2 -0.0184 (E_cond -0.0685 to +0.0302;
E_refit -0.0725 to +0.0687), v3 minus consensus +0.0222 (E_cond -0.0020 to +0.0477; E_refit
-0.0156 to +0.0555; hitters +0.0454, pitchers the consensus order), v3 minus Pipeline +0.0413, v3
minus FanGraphs -0.0013; V2 minus consensus +0.0406 (E_refit -0.0830 to +0.1251). Position-group
cells (C, IF, OF, pitchers; never an FV cell) are in the artifact. Two reserved rows (model
efv_v3, frames lv_res and vm_pros, trigger look, labelled "eFV v3 backtest, reserved frames,
owner waiver 2026-10-08") in `data/efv_progress.json`; the served claim reads the served model's
rows only and does not move.

**Reading:** under decision EW2-7 eFV v3 is not shippable (it does not beat served eFV on either
reserved frame; both differences inside their E_refit intervals) and the copy may not say it
beats consensus (no lower bound above zero). The development lift (+0.012 to +0.016 over V2) did
not carry: the quarter weights are a wash on R-LV hitters and negative on the 72 R-VM hitters,
and the pitcher command grade costs -0.018 on R-LV pitchers. eFV v3 ties consensus on R-LV and
reads an unresolved +0.022 on the 147-row 2025 cohort. `EFV_V3_ON` stays False; nothing served
moves. The served V2's own first reserved numbers (+0.0016 R-LV, +0.0406 R-VM against consensus,
both unresolved) sit in the artifact as the comparator and are not a look row for the served
model.

## 2026-10-09: eFV v4, the new-source menu selected on the development frames and read once on the spent reserved frames (EFV4_SELECT_SHIP)

Decisions EW2-8 to EW2-12 (2026-10-08) made eFV v4 a NEW SOURCES ONLY build: seven research lanes
(MiLB IL stints from the transactions cache, non-roster invitations, pitch-event discipline and
batted ball from the StatsAPI game feeds, a population-fitted translation, a historical rater
panel, LLM extraction of the as-of scouting reports) each landed as a registered wave-2 family
with its own development read. The selection rule, the menu, the step log and the spent read are
in `docs/efv-v2/EFV_V4_BACKTEST.md` (s1 to s4 fixed at `0de6666c` before any combined read; s5
and s6 appended by the runs); the code is `efv_v4.py` (`EFV_V4_ON = False`, dark) and
`tools/efv_v4_backtest.py`; the artifacts are `data/_labs/efv_v4/efv_v4_select.json`,
`data/efv_v4_spec.json` and `data/_labs/efv_v4/efv_v4_spent.json`. Label
`fwar@2026-10-02-0341299c20ec`; V2 base at the owner-kept P5 weights (EW2-9); within (side,
vintage) Spearman primary. Every number below is copied from those artifacts.

**Selection (development frames, spent):** 40 columns on the menu (the v4 arms admitted in at
least one development fold, each at its registered head: 13 IL, 4 NRI, 8 pitch-event, 2 batted
ball, 2 population, 2 rater panel, 9 report fields), one ADD step each, greedy, admitted at lv_dev
scope delta >= +0.0020 and vm_dev >= -0.0020, cap 6, starting from the served V2. Round 1: two
steps qualify, the report extraction's writer-minus-stated field on the pitcher skill head
(+0.00806 lv / +0.00245 vm) and the pitch-event called-strike rate (+0.00282 / 0); the first is
admitted. Round 2: none (the called-strike rate falls to +0.00137; the population translation on
pitchers reads +0.00924 / -0.01425, outside the vm tolerance). Every hitter step reads 0 against
V2 on at least one frame and none clears +0.0020 on lv_dev. The selected configuration's
development read: lv_dev (n 2,862) +0.0039 over V2 (CI95 -0.0018 to +0.0100), -0.0077 against
consensus (-0.0308 to +0.0141); vm_dev (n 830) +0.0012 (-0.0060 to +0.0084) and -0.0088 (-0.0389
to +0.0182). Two development rows (model efv_v4) in `data/efv_progress.json`.

**Spent read (reserved frames, read once by v3 on 2026-10-08 and spent; no ledger row):** R-LV
(n 2,349) v4 within 0.1483, V2 0.1511, consensus 0.1494, Pipeline 0.1988, FanGraphs 0.1469; v4
minus V2 -0.0027 (E_cond -0.0061 to +0.0009; E_refit B 200 -0.0105 to 0.0), v4 minus consensus
-0.0011 (E_refit -0.0242 to +0.0163; hitters +0.0057, pitchers -0.0082), v4 minus Pipeline
-0.0422 (E_refit -0.0723 to -0.0034). The column carries a value on 506 of 1,155 R-LV pitcher
rows (the extraction corpus ends at V 2019) and was admitted in the pit 2021 fold only, where it
reads -0.0110 against V2. R-VM (n 147): the column reached 3 of 95 pitcher rows and no fold
admitted it, so v4 is V2 on every row (within 0.3739; +0.0406 against consensus, E_refit -0.0830
to +0.1251, V2's own unresolved number).

**Reading:** under the ship rule (EW2-10: beat served V2 on lv_dev, vm_dev, R-LV and R-VM) eFV v4
is not shippable (-0.0027 on R-LV, 0 on R-VM) and the copy may not say it beats consensus (no
lower bound above zero). `EFV_V4_ON` stays False; nothing served moves; the served claim stays
"ties consensus". The new-source frontier is closed on the frames that exist: 39 of 40 columns
never cleared the development bar, and the one that did cost on the reserved fold it entered.

## 2026-10-09: the 2026 level norms move on 2027-01-01 with no new data (disclosed; a data refresh)

The served 2026 MiLB rel-rates read against a norm that is about half 2025 until 2027-01-01.
`milb_history.league_norms` blends the current season's level median with the prior season's
at w = n_cur / (n_cur + n_prior) while the calendar reads the season, and at season end w sits
at 0.480 to 0.519 by level and side, not at 1. 2026 was a higher-offense year at A through AA
and in the complex leagues, so on 2027-01-01, when the blend stops, every 2026 rel-rate moves
with no new data: v1 grades, the provisional grades and the chips move; the V2 order does not
(obp_rel and contact are not admitted and `level_rank` reads no norm). Served blend today
against the pure 2026 norm (from `data/milb_norms_2026_pure.json`): hitting OPS AA .714 to
.749, A+ .729 to .767, A .710 to .744, CPX .743 to .776, DSL .754 to .782, AAA .764 to .768;
pitching ERA AA 4.27 to 4.74, A+ 4.41 to 4.87, A 4.44 to 4.87, CPX 5.06 to 5.76, DSL 5.05 to
5.40, AAA 4.75 to 4.78. The same step recurs every New Year's Day.

This is a data refresh, not model progress. When it happens the ledger records it as a data
refresh: no development or headline row of `data/efv_progress.json` and no arm or probe of
`data/xfv_arm_ledger.json` reads the move as a change in the model. Owner answer efv2026 OQ4
(recorded 2026-10-01): A, leave the blend, pin the pure norms, disclose; no served change. Its
12-20 fallback (a decision if the fWAR epoch's part 9 carried no step Z entry by 2026-12-20)
does not arise: part 9 carries the step Z entry of 2026-10-03.

The pins (task SG_1, `tools/milb_season_freeze.py`): the ten 2026 season files frozen byte for
byte under `data/milb_season_frozen/2026/` (rows and PA or BF equal to the 2026-09-30 refetch),
the 2026 MLB lines reduced to person-id sets, the pure 2026 norms, canonical content hashes of
the transfer seasons (2010 to 2019, 2021 to 2025) and the transaction feed months 2026-07 to
2026-09, all in `data/efv_surrogate_pins_2026.json`. Nothing here read an outcome, a score or
a label, and no served number moved.

## Dated log

- 2026-10-15: eFV v5 COMBINED (EFV5_COMBINE_WEIGHT_SHIP, decisions EW3-8 and EW3-9): every atlas driver (28 group drivers, 4 tool cells, 40 v4 columns, 5 wave-2 scouting columns; the tracking head for pitchers at its registered 0.5) weighted at once in one sign-bounded joint ridge per head beside V2's own drivers, the penalty chosen by nested CV inside each fold (`efv5_combined.py --fit` at d7240219, `data/_labs/efv5/efv5_combined_fit.json`; method `docs/efv-v2/EFV_V5_COMBINED.md` committed first). Development read: lv_dev +0.0009 over V2 (E_cond CI95 -0.0179 to +0.0193; hitters -0.0115, pitchers +0.0140), vm_dev -0.0102 (-0.0306 to +0.0095); two development rows (model efv_v5_combined) in `data/efv_progress.json`. The spent read (`--spent --gate-sha e7931ce4...`, `data/_labs/efv5/efv5_combined_spent.json`, labelled spent, no ledger row): R-LV -0.0032 (E_refit -0.0369 to +0.0171), R-VM -0.0288 (E_refit -0.0744 to +0.0756); against consensus R-LV -0.0015 (E_refit -0.0438 to +0.0218). Ship rule EW3-9 (pooled by row count -0.0028 over 6,188 rows; held-out trail at most 0.005): fails; `EFV_V5_COMBINED_ON` stays False; no served number moves. `docs/efv-v2/EFV_V5_COMBINED_RESULTS.md` carries the plain-language reading and the weights.
- 2026-10-15: the eFV tracking-era head (EFV5_TRACKING_HEAD, decision EW3-1; registration `docs/efv-v2/EFV_TRACKING_HEAD_GATE.md` committed alone first, then one read the same day as an owner-waived early read). Short label reach3 and rate3 at N 3 on tracked rows (FSL 2021+, AAA 2022+) with the V = S + 1 consensus; train 2021 and 2022, held out 2023 (spent, R-VM overlap). Verdict by the registered rule: hitters do not ship; pitchers ship on the four point estimates (held-out n 122: head AUC 0.6324 vs consensus 0.5635 vs V2 0.5803; rho 0.2389 vs 0.1918 vs 0.1772), every CI95 including zero and the by-level reports going the other way (recorded in the gate's dated note). Served path built dark behind `efv5_tracking_head.EFV_TRACKING_HEAD_ON = False`; the flip is an integrator step with an owner question. Artifact `data/efv5_tracking_head.json`, results `docs/efv-v2/EFV_TRACKING_HEAD_RESULTS.md`. No served number moves.
- 2026-10-15: eFV v5 group drivers (EFV5_GROUP_DRIVERS, decisions EW3-1 to EW3-5): the eFV v5 metric atlas's 47 clean long-label candidates built as 28 group-driver columns (the statistic times a level, age band and role indicator) and offered to V2 under the v4 selection rule (`efv5_group_drivers.py --select` at 5bfd913e, `data/_labs/efv5/efv5_group_select.json`): two Single-A hitter columns admitted (wOBA, then slugging), development read +0.0033 over V2 on lv_dev (CI95 -0.0007 to +0.0073) and 0 on vm_dev, -0.0083 and -0.0101 against consensus; two development rows (model efv_v5) in `data/efv_progress.json`; the spent read (`--spent --gate-sha e7931ce4...`, `data/_labs/efv5/efv5_group_spent.json`, labelled spent, no ledger row): R-LV v5 minus V2 -0.0030 (E_refit -0.0099 to +0.0001), R-VM identical to V2. Not shippable under EW2-10; `EFV_V5_ON` stays False; no served number moves. `docs/efv-v2/EFV_V5_BACKTEST.md` and `EFV_V5_RESULTS.md` carry every number.
- 2026-10-14: the eFV tool-feature sidecar (TL_9_EFV_TOOL_SIDECAR; Part 9 PLAN s9.4.5 'Tools as eFV drivers', LANE_C.md s1.3 and s2.7; owner asks of 2026-10-01, messages 1 and 2). Why this may run at all: the eFV feature frontier is closed (plan Part 2; the 2026-08-14 closure, 39 arms, zero survivors) and game power failed as an eFV driver four times (the Phase 1 partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds; `data/xfv_arm_ledger.json`); nothing here re-runs a spent arm. The columns are new (a power composite chosen on realized ISO by a registered look, a tool-implied ISO residual, the inputs of an accuracy-weighted hit consensus) and exist on the owner's 2026-10-01 asks; the served eFV grade does not change. Route: owner answer TL-Q1 (a) (`DECISIONS_FOR_OWNER.md`): build now, TL_16 runs the DS-06 admission diagnostic on development folds and pre-declares for the next registration. `python tools/efv_tool_sidecar.py` wrote `data/_labs/efv_tool_features.json` (data/_labs ships in neither deploy consumer), keyed (side, V, player_key) on the lv_dev frame rows of V 2011 to 2019, never a column in a pinned matrix. Columns: per-source hit, game_pwr and raw_pwr grades from each source's earliest in-window snapshot and their consensus; pwr_comp as the as-of game and raw consensus inputs only, marked not a candidate because look P served C0 (`data/power_composite_eval.json`), no a stored; tip_iso_resid, the PA-shrunk pre-V MiLB ISO at the block level minus `tool_implied.tip_level` for the game_pwr consensus, the TIP table fit on MLB ISO pooled to V - 1 of frame players who debuted before V and the level norms and AAA offset rebuilt per V from seasons V - 5 to V - 1 with an as-of date of December 31 of V - 1 (asserted: no input season at or after V or in 2026 or later); the tool_hit_w inputs (per-source hit grades only, no weight stored). Coverage by (V, side), counts only: hitters 3,033 frame rows (2,883 with an outcome-blind id, 20 R-VM rows dropped), hit consensus 2,584, game_pwr 2,585, raw_pwr 1,037, both pwr_comp inputs 1,037, tip_iso_resid 843 (the TIP table is computable only at V 2018 and 2019: 114 and 149 fit rows), hit grades from one source 1,667 and from two or more 917; pitchers 2,894 rows (15 R-VM dropped), hitter tool grades on 23 rows. Six probes with role development join `data/xfv_arm_ledger.json` (61 to 67 probes, 400 arms unchanged). No outcome, W3 or WAR of a frame row was read; no list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is grouped by consensus-FV level. Nothing served moves.
- 2026-10-14: the pitch-rate admission diagnostic (Q10_11_EFV_PITCH_RATE_ADMISSION, owner ask 19 of 2026-09-30, the eFV half; plan Part 8 lane pitch_metrics s7 step (c), checklist PM-13). Why this may run at all: the eFV feature frontier is closed (plan Part 2.2; the 2026-08-14 frontier closure), and for pitchers DS-Q2 keeps pitcher eFV in consensus order until pitch-quality or K-rate data passes the sign-stability admission rule; these two arms are reopened only by a new data field (MiLB pitch counts, never before a model input) plus the owner's ask 19, and pbf_rel goes beyond DS-Q2 on that authority alone. Registration path: the owner's PM-Q4 answer (b) of 2026-10-01 (add to V2's candidate list before the frozen-label DS-16 re-run and before REGISTERED) could not be executed, because this file's gate registered on 2026-10-08 (EW2-6) with DS-16 re-run on the frozen label the same day, before any amendment landed; the task's default (a), re-asked 2026-10-08 and taken 2026-10-14 under EW3-5 as the recommended option (`DECISIONS_FOR_OWNER.md`), ran instead: the candidates do NOT enter V2's registration (s4.2 is not amended), and the DS-06 rule alone (`efv_v2_model.admission_for_key`, target the W3 percentile within (side, V), has-block rows, an absent value imputed at the fold's observed training mean, no flag) ran once on lv_dev inside folds V 2017, 2018 and 2019, each on its own training vintages with every V-frame player excluded (gate s4.5), adjudicating nothing. `python tools/efv_pitch_rate_admission.py` from HEAD `9f4ab867` (the tool uncommitted at the run; rc 0, 82.7 s, after one `--check` pass), artifact `data/_labs/efv_pitch_rate_admission.json` (generated 2026-10-14T17:28Z; data/_labs ships in neither deploy consumer), label `fwar@2026-10-02-0341299c20ec` (provider fwar), the column off `data/_labs/efv_pitch_rate_features.json` (Q10_10, 2026-10-07T16:43:10Z) carried on the rows' v2 view under the screening prefix like a screening-lab candidate. Guards asserted before any frame was built: `reserved_vm_pins()` empty, folds [2017, 2018, 2019], the combiner rule's last year 2016, the gate REGISTERED; no list vintage 2020 or 2021 and no 2025+ debut cohort was read; no order index was fitted and no delta was read; nothing is grouped by consensus-FV level (the only groupings are side, fold and training vintage). Training rows: hitters 3,053 (2,871 with a MiLB block, 1,065 observing ppa_rel, 17 reserved_vm rows kept at W3 = 0 per B9b with no pitch-rate value), pitchers 2,909 (2,056 / 1,153 / 15); per fold (train / has-block / observing the column) hit 2017 1,038 / 1,005 / 189, 2018 1,474 / 1,412 / 331, 2019 1,922 / 1,842 / 536; pit 2017 965 / 339 / 140, 2018 1,468 / 749 / 358, 2019 1,882 / 1,118 / 559 (pitchers read the MiLB block from 2014, EFV3_B3's withhold). Result, no sign predicted: `PM19:hit.skill.ppa_rel` REFUSED in 0 of 3 folds, fold 2017 (t by training vintage 2015 -0.70, 2016 -1.12; mean abs t 0.914 below 1.0), fold 2018 (2015 -0.69, 2016 -0.85, 2017 +2.76; sign flipped between training vintages), fold 2019 (2015 -0.71, 2016 -0.49, 2017 +3.04, 2018 +0.31; sign flipped); `PM19:pit.skill.pbf_rel` REFUSED in 2 of 3 folds, fold 2017 (only 2015 gives a t, +3.10; fewer than 2 vintages), fold 2018 ADMITTED (2015 +3.32, 2016 +1.25, 2017 +1.56; mean abs t 2.04), fold 2019 (2015 +3.07, 2016 +1.08, 2017 +0.15, 2018 -1.18; sign flipped). Against the closed walk-rate arm (Q10_10 step (d), copied): ppa_rel x bb_rel Spearman 0.6045 (n 1,065), so the hitter arm is in large part the closed D-1 bb_rel arm again; pbf_rel x bb_rel 0.4194 (n 1,100). The honest expectation the lane design stated ("refused or a tie contribution under 0.005") is met on the first half: both arms are refused by the rule, no pre-declaration for the next registration (V3 or the prospective cohort, PROGRAM.md Q4) is owed, and neither column enters any candidate list; the rule's refusal is a development reading on a spent frame, not a verdict, and a NULL-like reading is not re-run on another frame, estimator or seed. Step (b) of the lane design (the W3 > 0 balance probe by has-block) stays Q10_10's re-arm. Downstream, same commit: two arm rows in `data/xfv_arm_ledger.json` (398 to 400 arms, 61 probes, every other row byte-identical; `_labs/efv_pitch_rate_admission.json` joins the ledger's SOURCES); no `data/efv_progress.json` row (no rater was scored). Nothing served moves.
- 2026-10-15: the tool-family admission diagnostic (TL_16_EFV_TOOL_DEV_ADMISSION; Part 9 PLAN s9.4.5 'Tools as eFV drivers', LANE_C.md s2.7 route (a); owner ask of 2026-10-01, message 2). Why this may run at all: the eFV feature frontier is closed (plan Part 2; the 2026-08-14 closure, 39 arms, zero survivors) and game power failed as an eFV driver four times (the Phase 1 partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds; `data/xfv_arm_ledger.json`); nothing here re-runs a spent arm, and the served eFV grade does not change. The sidecar (`python tools/efv_tool_sidecar.py --rebuild --gate-sha e7931ce4...`) now also carries list vintages 2020 and 2021 (the R-LV record is EFV_V3_BACKTEST.md s5.1 at 1c73c420, decision D-k3; V 2011 to 2019 rows unchanged; hitter frame rows 3,033 to 4,155, tip_iso_resid rows 843 to 1,753). `python tools/efv_tool_admission.py --gate-sha e7931ce4...` ran the DS-06 rule on the frozen fWAR label inside lv folds 2017 to 2021 and vm folds 2020 to 2024: `TL:hit.skill.tool_hit_w` REFUSED (admitted in 9 of 10 folds; vm 2024 flipped on its 2023 vintage, t -0.0548; on the lv folds it tracks the admitted `tool_hit` at Spearman 0.989 to 1.000), `TL:hit.skill.tip_iso_resid` REFUSED (0 of 10; mean abs t at most 0.758), `TL:hit.skill.pwr_comp` NOT RUN (look P served C0). `docs/efv-v2/NEXT_REGISTRATION_TOOL_CANDIDATES.md` records an empty candidate list; the owner's precondition (look W PASS for hit, look P PASS for the composite) is not met. Two arms with role development join the ledger (400 to 402 arms). Nothing served moves.
- 2026-10-09: the 2026 MiLB season freeze and pins (SG_1) and the disclosure of the 2027-01-01 norm step (section above; owner answer efv2026 OQ4 = A). No served number moves.
- 2026-10-09: eFV v4 (EFV4_SELECT_SHIP, decisions EW2-8 to EW2-12): the 40-column new-source menu selected on lv_dev and vm_dev (`tools/efv_v4_backtest.py --select` at 1d3c1274, `data/_labs/efv_v4/efv_v4_select.json`, 241.1 s) admitted one step, the report extraction's writer-minus-stated field on the pitcher skill head (+0.00806 / +0.00245 scope deltas), round 2 none; development read +0.0039 over V2 on lv_dev (CI95 -0.0018 to +0.0100) and +0.0012 on vm_dev (-0.0060 to +0.0084), -0.0077 and -0.0088 against consensus; committed dark as `data/efv_v4_spec.json` (df7ac703) with two development rows (model efv_v4) in `data/efv_progress.json`; the spent read (`--spent --gate-sha e7931ce4...`, `data/_labs/efv_v4/efv_v4_spent.json`, 1,153.8 s, E_cond B 2000 and E_refit B 200, labelled spent, no ledger row): R-LV n 2,349 v4 minus V2 -0.0027 (E_refit CI95 -0.0105 to 0.0), minus consensus -0.0011 (-0.0242 to +0.0163); R-VM n 147 v4 equals V2 on every row (the column reached 3 of 95 pitcher rows; +0.0406 against consensus, unresolved). Not shippable under EW2-10; `efv_v4.EFV_V4_ON` stays False; the served claim does not move. The section above carries every number.
- 2026-10-09: the Pipeline-only panel (EFV3_A5 part 2, EFV3_PLAN.md s3 G3): debut cohorts 2011 to 2016 with an in-window MLB Pipeline read, frame `vm_pipeline_2011_2016`, role development, defined in `source_backtest` (PIPELINE_PANEL_YEARS, `_pipeline_panel_rows`, `pipeline_panel_census`; counts published first in the nightly `data/source_backtest.json` under `accuracy.pipeline_panel_census`) and read by `python tools/efv_vm3_frame_read.py` from HEAD `cbcce615` (rc 0, 52 s; `data/efv_vm3_frame_eval.json` generated 2026-10-09T01:35:51Z, the vm3 block unchanged in content). Counts: 492 debut rows 2011 to 2016 with an in-window Pipeline read (by cohort 10, 43, 108, 103, 135, 93; the lane's prior 469), 0 with a FanGraphs grade in the window, 331 scoreable by eFV v1 (decision years from `efv_model.SCORED_YEARS`, 2014; V2 has no out-of-sample score before 2017), 330 panel rows (hit 155 / pit 175; one pin year differs), 6 groups. Consensus on these rows is MLB Pipeline alone: on every one of the 492 rows the consensus read's only contributing source is `mlb_pipeline`; its VALUE is the source-calibrated Pipeline grade, never the published one (0 of 492 equal), and the two columns agree in rank within cohort at 0.85 to 0.94 (no outcome read); the receipt says so (`receipt.consensus`). Never pooled with vm2 or vm3: no panel player is a vm3 row (guard `panel_pooled_with_vm` false) and the cohorts end before the vintage-matched window. Statistic as on vm3 (within (side, debut year) primary, pooled after the identical map secondary, contributor AUC veto; E_cond, B 2000, seed 20260906, player clusters), eFV v1 timing-pinned, consensus and Pipeline, nothing new. Within: v1 0.3944, consensus 0.3978, Pipeline 0.4359 (n 330). v1 minus consensus -0.0035 within (CI95 -0.0437 to +0.0361; mde95 0.0340), -0.0042 pooled (-0.0385 to +0.0324), AUC +0.0050 (-0.0145 to +0.0266); v1 minus Pipeline -0.0415 within (-0.0909 to +0.0009), +0.0045 pooled (-0.0526 to +0.0604), AUC +0.0087 (-0.0227 to +0.0416). Holm (k 6, the FanGraphs cells absent and kept in the family at p 1): no cell survives (the Pipeline pooled Spearman cell -0.0524, CI95 -0.1036 to -0.0056, Holm p 0.017 does not clear its step). Reading: on the pre-2017 cohorts v1 and the consensus tie and v1 sits under Pipeline's own order; a development read on a spent frame, not a claim, and it raises the DS-08 rule's evidence count only. Downstream: one development row (model efv_v1, frame vm_pipeline_2011_2016, resolvable null, provider stamped) in `data/efv_progress.json` (138 to 139 rows, through `efv_progress.update_vm3`); one probe `EFV3_A5:vm_pipeline_2011_2016.efv_vs_consensus` in `data/xfv_arm_ledger.json` (60 to 61 probes, 398 arms unchanged). Guards as on vm3; no list vintage read, no closed arm re-run. vm2 stays the headline. Nothing served moves.
- 2026-10-09: frame version vm3 (EFV3_A5, EFV3_PLAN.md s3 G2; lane A E3-Q1 = A, the recommended option under the owner's standing instruction of 2026-10-01): the vintage-matched frame under the CONSENSUS-PRESENT rule, built as a DEVELOPMENT frame beside the vm2 headline. The frame is defined in `source_backtest` (`_consensus_present_rows`, `_vm3_frame_rows`, VM3_BASIS `pooled_efv_common_vintage_matched_vm3`): every debut-cohort row (base year equal to the debut year, 2017 to 2023) with an in-window PROSPX consensus read and a timing-pinned eFV score, FanGraphs and MLB Pipeline optional columns scored on their own rows (the lv_dev convention), the Holm family of H2H_HOLM_RATERS x H2H_HOLM_METRICS (k 6) unchanged. Counts first (`python tools/efv_vm3_frame_read.py --check`, and `accuracy.vm3_census` in the nightly `data/source_backtest.json`): 1,065 consensus-present debut rows (the lane's prior 995 was counted on the 2026-10-02 inputs), 863 both-source rows, 1,022 vm3 rows (hit 481 / pit 541; 40 without a pinned score, 3 whose pin year differs) against the vm2 headline's 830 (hit 406 / pit 424; the 830 both-source rows inside vm3 are exactly vm2's). Floors next: E_cond by the registered resampler (B 2000, seed 20260906, player clusters) on the primary, V2 minus consensus within mde95 0.0204 (vm2's DS-16 read 0.0229); E_refit by `python tools/efv_headtohead_frame_lab.py vm3 2000` (`data/efv_vm3_frame_floor.json`, 514 s, seed 20260906, eFV v1 refit in every draw with the matrix consensus input, the vm1 convention the vm2 headline carries): vm3 mde95 0.0260 (sd 0.01581, n 1,025) against 0.0229 for the both-source rows re-derived on the same draws (the lane's scaled prior was 0.0273 against 0.030). Then the raters, on the frozen fWAR label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026; a read on any other provider is marked exploratory): `python tools/efv_vm3_frame_read.py` from HEAD `0f9fb164` (rc 0, 47 s; artifact `data/efv_vm3_frame_eval.json`, generated 2026-10-09T01:13:25Z after one re-run for the own-rows note, same content hash), the served eFV V2 (`efv_v2_serve.served_oos_scores`, timing-pinned, the vm2 headline's scored object), eFV v1 (timing-pinned), consensus, Pipeline and FanGraphs, nothing new; within (side, debut year) primary, pooled after the identical map secondary, contributor AUC veto, 14 groups. Within: V2 0.3418, v1 0.3835, consensus 0.3554, Pipeline 0.3855 (own rows, n 923), FanGraphs 0.3184 (own rows, n 928). V2 minus consensus -0.0136 within (CI95 -0.0384 to +0.0104), -0.0145 pooled (-0.0393 to +0.0095), AUC -0.0045 (-0.0187 to +0.0092); V2 minus v1 -0.0417 within (-0.0723 to -0.0107); v1 minus consensus +0.0281 within (+0.0053 to +0.0518); V2 minus Pipeline -0.0072 within (-0.0448 to +0.0269, n 923); V2 minus FanGraphs +0.0182 within (-0.0229 to +0.0615, n 928). Holm (k 6, own rows): one cell survives, V2 minus FanGraphs on AUC +0.0343 (CI95 +0.0131 to +0.0562, Holm p 0.0008); the consensus Spearman cell carries no word on a development frame. Reading: on the larger frame V2 sits about 0.014 under consensus and the interval spans zero; the v1 lead over consensus here is on a spent frame and is not a claim. Guards asserted before any score: `reserved_vm_pins()` empty, CANDIDATE_YEARS and SCORED_YEARS end at 2024, no list vintage read, nothing grouped by consensus-FV level, no closed arm re-run. Downstream: one development row (model efv_v2, frame vm3, resolvable null, provider stamped, the E_refit floor beside the E_cond one) in `data/efv_progress.json` (137 to 138 rows, appended through `efv_progress.update_vm3`, its own rows alone); one probe `EFV3_A5:vm3.efv_vs_consensus` in `data/xfv_arm_ledger.json` (59 to 60 probes, 398 arms unchanged). vm2 STAYS THE HEADLINE and both versions stay in the ledger; the headline switch to vm3 is a frame change only EFV_V2_RESERVED_READ's record and a later owner answer can make; the copy keeps 'ties consensus'. Nothing served moves.
- 2026-10-08: eFV v3 (EFV3_W3_SELECT_CONFIRM, decision EW2-6): the forward selection on lv_dev and vm_dev (`tools/efv_v3_backtest.py --select` at fc5b9cc0, `data/_labs/efv_v3/efv_v3_select.json`, 428.7 s) admitted four steps (hitter skill and timing weights at a quarter of P5, the scouting command grade offered to the pitcher skill head, the pitcher K rate withheld; the anchors lifted lv_dev and lowered vm_dev beyond the tolerance), reading +0.0155 over V2 on lv_dev and +0.0116 on vm_dev, +0.0039 and +0.0015 over consensus; committed as `data/efv_v3_spec.json` (1a546ad4); the gate flipped to REGISTERED with its s11 waiver (e7931ce4); the ONE reserved read (`--confirm --gate-sha e7931ce4...`, `data/_labs/efv_v3/efv_v3_confirm.json`, 2,583.9 s, E_cond B 2000 and E_refit B 200): R-LV n 2,349 v3 minus V2 -0.0092 (E_refit CI95 -0.0312 to +0.0128), minus consensus -0.0076 (-0.0347 to +0.0057); R-VM n 147 v3 minus V2 -0.0184 (-0.0725 to +0.0687), minus consensus +0.0222 (-0.0156 to +0.0555). Not shippable under EW2-7; `efv_v3.EFV_V3_ON` stays False; two development and two reserved rows (model efv_v3) in `data/efv_progress.json`; the served claim does not move. The section above carries every number.
- 2026-10-08: the driver-subtraction diagnosis (EFV3_W2_DRIVER_DIAG, owner answer EW2-1), a development DIAGNOSIS that admits nothing, removes nothing, changes no weight and writes no ledger or progress row. `python tools/efv_v2_driver_diag.py` from HEAD `ba4e8254` (rc 0, 903 s), artifact `data/_labs/efv_v2_driver_diag.json` (generated 2026-10-08T19:25:58Z; data/_labs ships in neither deploy consumer), label `fwar@2026-10-02-0341299c20ec`, assembly sha256 `35fe32c7...2823` (P5 weights hit 0.908861 / 0.202573, pit 1.0 / 0.020473); frames, folds and guards through `tools/efv_v2_model_class_screen.build_inputs`, the V2 base reproducing the DS-16 block before any read (lv_dev n 2,862, vm_dev n 830); within (side, vintage) Spearman, E_cond, B 2000, seed 20260906. No list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is grouped by consensus-FV level (the strata are `efv_strata` cells). Findings, development only and uncorrected: (1) the gap is hitters: V2 minus consensus, hitters -0.0209 lv_dev (CI95 -0.0596 to +0.0161) and -0.0202 vm_dev (-0.0759 to +0.0376); pitchers -0.0020 and exactly 0 (consensus order on every vm pitcher fold). (2) no driver's pooled partial slope changes sign between the eWAR v2 and fWAR labels (lv on the same rows, provider-only switch; vm E0 against the served matrices and F1 against Estar); the timing slopes are label-free by construction. (3) the size of the push: the same fold heads re-weighted at k times the P5 weights read, against consensus, +0.0028 / +0.0015 at k 0.25, -0.0015 / -0.0004 at 0.5, -0.0116 / -0.0101 at 1 and -0.0233 / -0.0171 at 1.5 (lv / vm); at the pre-refit weights (hit 0.599508 / 0.012287) they read +0.0133 over V2 on lv hitters (CI95 +0.0020 to +0.0255) and +0.0146 on vm hitters (CI95 -0.0105 to +0.0382). (4) per driver: on vm hitters the timing head's level_rank alone reads -0.0388 against consensus (CI95 -0.0771 to -0.0009) and withholding it gains +0.0109 over V2, while withholding tool_hit loses -0.0221; on lv hitters the skill head alone reads -0.0194 and the timing head alone -0.0039, no single withheld driver gains more than +0.0080 (is_college), and nov_add is the one driver whose removal costs (-0.0030, CI95 -0.0058 to 0.0). (5) subgroups: vm hit 2022 contributes -0.0099 of the frame's -0.0101; level at list A+ -0.0372 and no block -0.0231 on lv, AA -0.0433 on vm; outfield and catcher bats, college and international bats; 2 of 52 scored cells have an interval below zero, about chance. (6) the served board at the 10-04 refit (c40c0dd0) moved AWAY from consensus: on the 1,055 live V2-graded hitters the within-group Spearman with consensus went 0.953 to 0.840, 1,044 ranks changed (722 farther from the consensus rank, 320 closer, 13 same), the mean rank gap 73.7 to 132.8, 950 displayed grades changed and grades equal to consensus 157 to 106; the 941 pitchers did not move; the served artifacts before and after the rebuild (94ec6875, 44856cdd) give the same counts, the heads unchanged and only the weights moved. The weight curve and the cells were read on the spent frames they describe and select nothing; the registered DS-08 weights stand. The owner explanation, the per-driver table and six ranked wave-2 hypotheses (with owner question W2D-1) are in the task's DIAG.md. Nothing served moves.
- 2026-10-08: the model-class screen (EFV3_C03) ran once on the frozen fWAR label (`tools/efv_v2_model_class_screen.py` at `ad521ba6`, rc 0, 259.5 s, after one `--check` pass that built the frames and reproduced the DS-16 base; artifact `data/efv_v2_model_class_screen.json`, generated 2026-10-08T18:30:31Z): no arm admitted on the registered rule, MC-4a marked adoptable on non-inferiority alone, the driver-permuted twins above V2 on both frames; ten probes in `data/xfv_arm_ledger.json` (49 to 59) and ten development rows in `data/efv_progress.json`. The dated section above carries every number. Nothing served moves.
- 2026-10-08: the screening lab's one registered run (EFV3_B7, gate s10) on the frozen fWAR label. `python tools/efv_screen_lab.py` from HEAD `b17c2027`, generated 2026-10-08T18:01:30Z, 259.2 s, after one `--check` pass (frame counts only) and the lab's 34 fixture tests. The process exited rc 1: the artifact was written in full (atomic replace; the `wrote` line precedes the traceback) and the console echo after it raised `TypeError` on the withheld arm's None verdict; the lab was not re-run, the echo is repaired in this commit (`verdict_line`), and the arm and progress ledgers were regenerated from the written artifact by the ledger tools (OWNER_QUESTION B7-Q1 in the task's output directory records the default taken). Inputs: label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026); `data/efv_v2_assembly.json` sha256 `35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823` (the P5 re-fit; weights hit w_skill 0.908861 w_time 0.202573, pit 1.0 / 0.020473); B 2000, seed 20260906, E_cond, player clusters, 500 permutation draws, floor mode forced (the admitted mode's receipt beside it under `floors_other`). Frame: lv_dev, list vintages 2017 to 2019, n 2,862 (hit 1,465 / pit 1,397), w_star_dev 1.10; 29 reserved_vm rows kept at W3 = 0 (gate s5 B9b). Guards asserted before any score: `reserved_vm_pins()` empty, folds [2017, 2018, 2019], the combiner rule's last year 2016; no list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is grouped by consensus-FV level; vm_dev not screened; no closed arm re-run. Floors derived before any arm (MAX mde95 over three N(0,1) noise columns; within / pooled / AUC): skill hit 0.0034 / 0.0065 / 0.0046, skill pit 0.0075 / 0.0103 / 0.0099, timing hit 0.0009 / 0.0025 / 0.0025, timing pit 0.0003 / 0.0010 / 0.0009, both sides pooled skill 0.0042 / 0.0070 / 0.0051 and timing 0.0005 / 0.0010 / 0.0009 (the coverage arm reads the larger of the two). Holm family m 7, alpha 0.05, formed after every arm. Arms (within delta candidate minus base, CI95, lb95, floor, permutation p, Holm p, verdict): `txt_skill_hit` not measured, withheld before any read (report_absent reads IMBALANCED on hitters under DS-03, `efv_text_features.offered_columns`, gate s10.7), counted in m, no verdict; `txt_skill_pit` 0.0 (0.0 to 0.0), lb95 0.0, floor 0.0075, p 0.874, Holm p 1.0, admitted in 0 of 3 folds (2017 mean |t| 0.866; 2018 and 2019 sign flipped between training vintages), NULL; `txt_time_hit` -0.00308 (-0.0074 to +0.0013), lb95 -0.00678, floor 0.0009, p 1.0, Holm p 1.0, admitted 3 of 3, fold deltas -0.00723 / -0.00219 / -0.00020, pooled -0.00337 against floor 0.0025, AUC -0.00065, report_absent IMBALANCED on hitters (partial -0.1039, CI95 -0.1609 to -0.0463), NULL; `txt_time_pit` -0.0001 (-0.0008 to +0.0007), lb95 -0.0007, floor 0.0003, p 0.970, Holm p 1.0, admitted 3 of 3, fold deltas -0.00022 / -0.00026 / +0.00015, pooled -0.00262 (-0.0056 to -0.0003) against floor 0.0010, NULL; `milb_floor_2005` (coverage, both sides pooled, n 2,862) +0.00358 (-0.0112 to +0.0184), lb95 -0.00892, floor 0.0042, bootstrap one-sided p 0.329 (the s10.5 substitution), Holm p 1.0, fold deltas hit +0.01885 / -0.00306 / +0.00499 and pit 0 / 0 / 0 (pitchers withheld at 2014), pooled +0.00071, AUC +0.00056, NULL; `pick_overall_time_hit` 0.0, floor 0.0009, p 0.986, Holm p 1.0, admitted 0 of 3 (sign flipped between training vintages in every fold), NULL; `pick_overall_time_pit` 0.0, floor 0.0003, p 0.990, Holm p 1.0, admitted 0 of 3, NULL. Twins: every measured column arm's twin reads delta 0.0, inside its floor. AUC: no arm adverse beyond its floor. Balance probes on the frozen label (DS-03): txt_skill_pit_absent BALANCED (-0.0598, CI95 -0.1235 to +0.0008), txt_time_hit_absent IMBALANCED (above), txt_time_pit_absent BALANCED (-0.0598, -0.1152 to +0.0020), pick_overall_time_hit_absent BALANCED (-0.0284, -0.0751 to +0.0198), pick_overall_time_pit_absent BALANCED (+0.0098, -0.0410 to +0.0639). Result: no arm is admitted; the candidate list of s4.2 is unchanged and no amendment is written; `efv_v2_model.V2_SCREEN_CANDIDATES_ON` is created at False with an empty `V2_SCREEN_ADMITTED` (test-pinned: with it off the candidate lists, the fitted heads of `efv_v2_serve.production_models()` and `data/efv_v2_assembly.json` are the committed module's); a NULL arm is not re-run on any other frame, estimator or seed (kill rule 2); wave 2 may now be registered in s10 as its own family. Downstream, same commit: `data/xfv_screen_wave1.json` (`screening.exploratory` false, `floors` before `arms`); six arm rows in `data/xfv_arm_ledger.json` (392 to 398 arms, 49 probes, 0 of 357 scoreable arms cleared their own floor; `xfv_screen_wave1.json` leaves the ledger's PENDING set); six development rows (model `efv_v2_screen:wave1:<arm>:<side>`, frame lv_dev, resolvable null) in `data/efv_progress.json` (66 to 72 rows; no served row appended: the lab now appends through `efv_progress.update_screening`, its own rows alone, and the served rows stay the nightly's). The Source Comparison page lists the six rows in its collapsed screening block and charts none. Nothing served moves: the served eFV grade reads neither this artifact nor the flag. Disclosure: the DS-03 receipts in `data/efv_identity_balance.json` that decide which text heads are offered (`text`, `pick`) were taken on the eWAR v2 label on 2026-10-03, before the freeze, and were not re-run here; the lab's own balance probes above are on the frozen label.
- 2026-10-08: P5, DS-16 re-run once on the frozen fWAR label (the registered development number). `python tools/efv_v2_dev_read.py --ds16 --no-ledger` (rc 0, 76 s, after one `--check` pass that built the frames and printed counts only), from HEAD `8e2361f4` with one uncommitted text-only change to the producer (the block's `note` and the `w_star_dev` convention string now name the label the read ran on; no frame, score or statistic code changed), generated 2026-10-08T17:39:23Z. Registration: `docs/efv-v2/EFV_V2_GATE.md` s7 and precondition P5 (DS-16 re-run ONCE on the frozen label), `DRIVER_SYSTEM_V2.md` DS-16 row; the producer names the gate draft at `72ac7098` (status DRAFT), and the first DS-16 read (2026-09-25, `82f69d5e`) is the only earlier one. Inputs: label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026); `data/efv_v2_assembly.json` sha256 `35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823` (the P5 re-fit, `c40c0dd0`; weights hit w_skill 0.908861 w_time 0.202573, pit w_skill 1.0 w_time 0.020473); `efv_v2_stat.py` sha256 `0a1db56a...07c3`; `efv_v2_model.py` sha256 `aaa002e8...daea`; B 2000, seed 20260906, E_cond, player clusters. Frames: lv_dev list vintages 2017 to 2019 (W3, contributor at w_star_dev 1.10, was 1.19 on eWAR v2) and vm_dev at vm2 (debut years 2017 to 2023, career WAR to date). Guards asserted before any score: lv vintages read [2017, 2018, 2019], vm years read 2017 to 2023, `reserved_vm_pins()` empty, the combiner rule's last year 2016 below the first scored year; 29 reserved_vm rows kept at W3 = 0 (gate s5 B9b). No list vintage 2020 or 2021 and no 2025+ debut cohort was read; nothing is grouped by consensus-FV level. Primary (within (side, vintage) Spearman), V2 minus consensus, before (eWAR v2 label and weights) and after: lv_dev n 2,862 (hit 1,463 to 1,465, pit 1,399 to 1,397), V2 0.1619 to 0.1676, consensus 0.1624 to 0.1792, delta -0.0005 (CI95 -0.0197 to +0.0172) to -0.0116 (CI95 -0.0332 to +0.0095), mde95 0.0155 to 0.0180; vm_dev n 803 to 830 (within rows 788 to 814, 13 groups), V2 0.3755 to 0.3713, consensus 0.3813 to 0.3814, delta -0.00575 (CI95 -0.0231 to +0.0116) to -0.0101 (CI95 -0.0386 to +0.0159), mde95 0.0146 to 0.0229. Secondary (pooled after the identical output map): lv_dev -0.0018 (CI95 -0.0199 to +0.0161) to -0.0127 (CI95 -0.0354 to +0.0105); vm_dev -0.0058 (CI95 -0.0215 to +0.0096) to -0.00995 (CI95 -0.0356 to +0.0150). Contributor AUC: lv_dev +0.0001 to -0.0116 (CI95 -0.0290 to +0.0072); vm_dev +0.0020 to -0.0042 (CI95 -0.0193 to +0.0108). The other comparisons, within, after: lv_dev V2 minus v1 -0.0112 (CI95 -0.0353 to +0.0136), v1 minus consensus -0.0005 (-0.0234 to +0.0220), V2 minus Pipeline -0.0333 (-0.0641 to -0.0019, n 2,574), V2 minus FanGraphs +0.0061 (-0.0290 to +0.0402, n 2,370); vm_dev V2 minus v1 -0.0229 (-0.0533 to +0.0084), v1 minus consensus +0.0128 (-0.0104 to +0.0342), V2 minus Pipeline -0.0103 (-0.0528 to +0.0290), V2 minus FanGraphs +0.0350 (-0.0090 to +0.0775). Reading: every V2 versus consensus interval spans zero on both frames under all three statistics; on the frozen label V2 sits below consensus by about 0.01 on both frames and does not lead it. This is a development read on spent frames: it adjudicates and selects nothing and is not a claim. Downstream, same commit: two development rows (model efv_v2_ds_assembled, frames vm_dev and lv_dev) in `data/efv_progress.json` (64 to 66 rows; no other row appended); the two DS-16 probes in `data/xfv_arm_ledger.json` take the new numbers (49 probes, 392 arms, unchanged); `data/efv_label_pool_census.json` re-run (its floor curve copies this block's E_cond SDs: vm sd_ref 0.00886 to 0.01394 at n_ref 803 to 830, lv sd_ref 0.00944 to 0.01093; counts unchanged). Pins: `test_efv_v2_ds16.py::test_the_weights_are_the_registration` passes on the re-run; `test_efv_v2_gate.py::test_the_draft_carries_the_registered_weights` stays xfail because it needs the gate draft's s4.3 table re-taken, which belongs to the registration commit (EV-12, P4). Nothing served moves: the served eFV grade does not read this artifact.
- 2026-10-04: P5, the weights re-derived once on the frozen fWAR label. `python tools/efv_v2_assemble.py` (rc 0, 45 s, code at `487fb38e`, generated 2026-10-04T11:45:03Z) re-ran the DS-08 combiner rule and the DS-06 admission on label `fwar@2026-10-02-0341299c20ec` (provider fwar, RESOLVED_THROUGH 2026) on the lifted F-LV frame (EFV3_B3, `bfb73531`: hitters read the MiLB block from 2005, pitchers withheld at the served 2014). Weights, before (eWAR v2 label, RESOLVED_THROUGH 2025, 2026-09-25 build) and after: hitters w_skill 0.599508 to 0.908861, w_time 0.012287 to 0.202573 (rule rows 1,330 to 1,429); pitchers w_skill 1.0 to 1.0, w_time 0.107279 to 0.020473 (rule rows 1,038 to 1,158); the rule still reads years 2011 to 2016 only. Admitted over all development vintages, before: hit contact, tool_hit, milb_absent, nov_add; pit k_rel, nov_add. After: hit contact, is_college, milb_absent, nov_add; pit k_rel. Twenty arms and two probes, as before. `data/efv_v2_assembly.json` sha256 `422fc5439253ad13d867320b00b634a178e62a8b291025326056377d6d4436ec` to `35fe32c7a5448e8186259a8e4551be6f148d2f8346aa2016a40fb72f6afd2823`; `data/xfv_arm_ledger.json` re-counted (its 20 assembly rows and 2 probes take the new verdicts; 392 arms, unchanged). No list vintage 2020 or 2021 and no 2025+ debut cohort was read (the assembler's guards ran first). The assembler's documented procedure does not re-run DS-16, so DS-16's one re-run on the frozen label (`tools/efv_v2_dev_read.py --ds16`, `data/efv_v2_dev_eval.json`) is OWED, and the gate draft's s4.3 table is re-taken at registration (P4). This is a refit, not a read: it scores no row and draws no accuracy conclusion. It moves the served eFV v2 grade (SERVE_EFV_V2 is on and `efv_v2_serve.production_models()` loads these weights) at the post-epoch landing rebuild.
- 2026-10-03: pricing. The MC-5 pricing read (EFV3_C05, `tools/efv_v2_pricing_calibration.py` at `0fcf9270`; artifact `data/efv_v2_pricing_calibration_eval.json`, generated 2026-10-04T02:37:47Z) ran on the frozen fWAR label (`fwar@2026-10-02-0341299c20ec`) after the epoch's step Z. It adds position family (the in-window listed position; pitchers by MiLB games-started share) and age at the read to the pricing line only. order_idx and the eFV grade are bit-identical with and without the term (asserted on every fold), so every Spearman and AUC delta is 0 and it carries no rank claim. MAE of efv_war, a labelled diagnostic, not a claim: lv_dev (n 2,862) 0.9323 base against 0.9423 with the term, delta +0.0100 (CI95 +0.004 to +0.016); vm_dev (n 830) 3.6728 against 3.6829, delta +0.0101 (CI95 -0.0101 to +0.0311). Out of fold the extended line prices no better on either frame and worse on lv_dev. Calibration in the large on lv_dev moves toward zero for corner hitters (mean residual -0.272 to +0.002) and relievers (-0.212 to -0.086) and away from it for middle-position hitters (-0.017 to -0.135) and starters (-0.180 to -0.280). Nothing served moves; the served price changes only through EV-15 after the reserved reads and the PROSPECT_ANCHOR look. Two development rows (model efv_v2_pricing_pos_age, metric mae) are in `data/efv_progress.json`.
- 2026-10-02: screening lab registered, no result. Section 10 of `docs/efv-v2/EFV_V2_GATE.md` (still DRAFT) registers wave 1, seven arms frozen at `d9fe7db4`; no lab number exists on the frozen label.
- 2026-10-02: the exploratory screening run (EFV3_B5, gate s10.11) was made on the eWAR v2 label at lab commit `9c541e92`, to a file outside the repository; no verdict, nothing admitted, no row under `data/`; its floors are advisory and the registered run derives its own. Still no lab number on the frozen label.
- 2026-10-15: eFV v5 COMBINED SERVED BY OWNER OVERRIDE (decision EW3-10, verbatim 'Make eFV v5, its even with the ship rule so flip it'). The EW3-9 ship rule failed (pooled -0.0028 over 6,188 rows; R-VM -0.0288; every CI95 spans zero), and the owner flipped it anyway: `efv5_combined.EFV_V5_COMBINED_ON = True` (6560c01c), served artifacts regenerated (15ae05d2). 154 of 9,515 displayed eFV grades moved (77 hitters, 77 pitchers); pitchers now carry 27 drivers instead of the consensus order. Largest movers: Seth Hernandez 59.0 to 51.5 (surplus 111.2 to 64.0 million) and Thomas White 52.3 to 59.0 (69.6 to 117.6 million), a rank swap on the pitcher output map. The claim stays 'ties consensus'; setting the flag False and rebuilding restores V2.
- 2026-10-15 (correction to the EW3-10 entry above): the first flip served v5's joint fit WITHOUT its candidate columns on the live board, so only V2's own keys moved grades. efv5_combined.live_columns (e9fc3a3c, built and adversarially reviewed by the efv5-live-columns workflow, 7 defects fixed) now builds them as of today; regenerated at 92fbb4e9. 431 hitters and 443 pitchers change displayed eFV against this morning's V2; prospect-page chips name the v5 drivers. Seth Hernandez is 59.0 and Thomas White 49.0 (the earlier swap is gone).
- 2026-10-15: eFV v5 COMBINED RE-FIT (EFV_FIX_B_REFIT, decision EW3-21, after the eFV driver audit): registered alone at ed078e80 (`docs/efv-v2/EFV_V5_REFIT.md`), then read once on the development frames (`efv5_refit.py --run`, `data/_labs/efv5/efv5_refit_fit.json`). Arms: popmle norms repaired, live-dark columns dropped, the arrival head fitted on list vintages 2011 to 2019, twin rows read on 15 October, weights by DS-08's OLS ratio on forward-chained out-of-fold terms (hitters 0.297 and 0, pitchers 1.0 and 0; served 0.909 / 0.203 and 1.0 / 0.020). Within vs served v5: RT lv_dev -0.0002, vm_dev +0.0326 (CI95 +0.0056 to +0.0585), pooled +0.0072; R +0.0011, +0.0258, pooled +0.0066; both pass the registered rule, RT prepared. Against consensus a tie on both frames (RT -0.0109 and +0.0123); hitters now level with consensus. The flip is prepared DARK (`efv5_refit.EFV_V5_REFIT_ON` with `efv_w2_popmle.POP_REPAIR_ON`); nothing served moved; the owner question carries the board effect (Nelson Rada 55.6 to 46.9) and the re-derived claim. `docs/efv-v2/EFV_V5_REFIT_RESULTS.md` is the plain-language reading.
- 2026-10-15: eFV v5 COMBINED RE-FIT SERVED (owner EFV-REFIT-1, verbatim 'Flip everything that passed'): `efv5_refit.EFV_V5_REFIT_ON` and `efv_w2_popmle.POP_REPAIR_ON` True (8ae40518), served artifacts regenerated (c01ed62f). Variant RT serves: hitters w_skill 0.297, w_time 0, so the hitter order is consensus plus 0.30 of the hit tool term (every added hitter column shrank to zero); pitchers w_skill 1.0, w_time 0, on the 21-key joint skill head. `data/xfv.json` meta.served_model names model_id efv_v5_combined with the claim re-derived from the re-fit's read: ties consensus, vm_dev +0.0123 (CI95 -0.012 to +0.034, n 830) and lv_dev -0.0109 (CI95 -0.031 to +0.010, n 2862). Of the consensus-graded active rows, displayed eFV changed for 947 of 1,055 hitters and 659 of 941 pitchers; 599 hitters and 186 pitchers moved by a grade or more. Nelson Rada 55.6 to 46.9. The glossary entry, the registry row efv_v2 and the five tests that pinned the pre-flip state follow the served receipt (EFV_REFIT_POSTFLIP). Setting both flags False and rebuilding restores the first v5 fit.
- 2026-10-16: eFV TOOL INPUTS ON eTOOLS (EFV_ETOOLS_REWEIGHT, decision EW3-26): registered alone at 49ca37be (`docs/efv-v2/EFV_ETOOLS_REWEIGHT.md`), read once on the development frames (`efv_etools_reweight.py --run`, `data/_labs/efv5/efv_etools_reweight_fit.json`). The served re-fit RT recomputed to its committed read (0.1683, 0.3937). Candidate E (eHIT in the hit key, ePOW, eCMD, eFB on every graded pitcher) minus RT: lv_dev -0.0052 (CI95 -0.0100 to -0.0003), vm_dev -0.0021, pooled -0.0045; ED -0.0049, -0.0011, pooled -0.0040; neither passes. Against its null with consensus values in the same slots E reads -0.0005 pooled and against the permuted shift -0.0013: the eTool shift adds nothing for the WAR label. eHIT orders later WAR worse than the consensus hit grade (vm_dev -0.106, CI95 -0.165 to -0.048). Nothing prepared; nothing served moved. `docs/efv-v2/EFV_ETOOLS_REWEIGHT_RESULTS.md` is the plain-language reading.
