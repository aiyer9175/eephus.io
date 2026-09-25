# eFV v2: where it stands (2026-09-25)

Every number below is copied from the `ds16` block of `data/efv_v2_dev_eval.json` (generated
2026-09-25T21:28:38Z by `tools/efv_v2_dev_read.py --ds16`, code at 0dbe3a4f), the one
pre-declared development read of the assembled Driver System V2 (DS-16). The read was declared,
with its statistic, in the DS-15 draft `docs/efv-v2/EFV_V2_GATE.md` s7, committed at 0dbe3a4f
before it ran. It is a DEVELOPMENT read on SPENT frames with the eWAR v2 label: it adjudicates
nothing, selects nothing (V2 is the one candidate), and is not the registered development number
(that is its re-run on the frozen fWAR label, gate precondition P5). No em-dashes.

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
