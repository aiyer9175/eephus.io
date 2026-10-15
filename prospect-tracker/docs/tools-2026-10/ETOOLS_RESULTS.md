# eTools results (2026-10-15)

The one look of `docs/tools-2026-10/ETOOLS_GATE.md` (registered at 3f240da6, built at 7686d75c),
run once on 2026-10-15 with `python etools.py --run --gate-sha 3f240da6`. Artifacts:
`data/_labs/etools/etools_eval.json` (verdicts, weighting arm, pitch-rate read, spent marker) and
`data/_labs/etools/etools_atlas.json` (every test row: 189 pooled tests, 963 descriptive cell
tests, 232 pitch-rate eFV tests). Every input's sha256 matched at start and end. Nothing served
moved: `ETOOLS_ON` is False and the preview went to `.cache/etools/preview.json`.

**Survivorship, stated beside every number.** L_MLB is accuracy AMONG DEBUTS: only players who
reached the majors have an MLB outcome. L_UM (translated Double-A and Triple-A outcomes over
seasons Y to Y + 2, capped at 2024) covers debuts and non-debuts alike. Every verdict below
needed both.

Frame: development board years 2011 to 2019 and 2022 to 2024 only, 8,898 (board year, player)
rows after identity (outcome-blind) and the pre-debut rule. Statistic: within-board-year
Spearman of an out-of-fold model minus that of the consensus tool grade, folds by board year
with the test year's players removed from training; player-clustered bootstrap B 2000.

## The short answer

1. **Yes, stats sharpen tool grades, a lot for some tools.** Six eTools beat the consensus tool
   grade on both labels: **eHIT, ePOW, eSEL (pitch selection), eBAT (bat control), eFB, eCMD**.
2. **The hit tool is where the consensus leaves the most on the table.** Against MLB strikeout
   rate (the framework's hit estimand), the consensus hit grade orders debuts at 0.298; eHIT
   orders them at 0.600 (+0.302, lower bound +0.259). The same gain holds on the upper-minors
   label (+0.274). A prospect's own translated MiLB strikeout rate says more about his MLB
   strikeout rate than the hit grade does.
3. **Accuracy weighting the outlets by position group adds nothing** (13 of 13 tools NULL,
   every difference within 0.0033). That repeats look W. The gain comes from adding the stat
   reading as an input, not from reweighting FanGraphs against MLB Pipeline.
4. **P/PA, P/IP, P/BF and PAR:** useful as tool sub-drivers (P/PA for eHIT, P/BF for eFB and
   eCMD), **not** as direct eFV drivers: 232 atlas tests over consensus FV, none flagged.
5. **No sub-driver for field, throw, slider, curveball or changeup**, and raw power and speed
   improve only on the minors label, so those seven keep the consensus grade.

## Per tool

d = eTool minus consensus tool grade, within-year Spearman; LB = one-sided 95% lower bound.

| tool | key | admitted sub-drivers | L_MLB consensus to eTool (d, LB) | L_UM consensus to eTool (d, LB) | verdict |
|---|---|---|---|---|---|
| hit (K%) | eHIT | translated K% (k_rw), P/PA PAR, translated BABIP | 0.298 to 0.600 (+0.302, +0.259), n 1,385 | 0.436 to 0.710 (+0.274, +0.249), n 2,704 | **PASS** |
| game power (ISO) | ePOW | translated ISO, fly-ball rate | 0.539 to 0.573 (+0.034, +0.019), n 1,385 | 0.594 to 0.633 (+0.039, +0.030), n 2,705 | **PASS** |
| pitch selection (chase, 2026) | eSEL | pitch-level swing rate | 0.496 to 0.585 (+0.089, +0.049), n 234 | 0.556 to 0.628 (+0.072, +0.050), n 649 | **PASS** |
| bat control (zone contact, 2026) | eBAT | pitch-level contact rate | 0.383 to 0.474 (+0.091, +0.060), n 237 | 0.477 to 0.557 (+0.079, +0.062), n 663 | **PASS** |
| fastball (pitcher K%) | eFB | translated K%, P/BF, swinging-strike rate | 0.293 to 0.362 (+0.068, +0.037), n 1,932 | 0.294 to 0.471 (+0.176, +0.154), n 2,919 | **PASS** |
| command (pitcher BB%) | eCMD | translated BB%, first-pitch strike rate, P/BF PAR | 0.377 to 0.418 (+0.041, +0.024), n 1,931 | 0.539 to 0.613 (+0.074, +0.062), n 2,917 | **PASS** |
| raw power (avg EV) | eRAW | translated ISO | +0.005 (LB -0.012), n 678 | +0.038 (LB +0.026), n 694 | NOT PASS (MLB label) |
| speed (sprint speed) | eSPD | stolen bases per PA, level-relative | +0.007 (LB -0.001), n 2,015 | +0.055 (LB +0.048), n 2,705 | NOT PASS (MLB label) |
| field (OAA per 1,000) | eFLD | none (premium-position share d +0.024, LB -0.006) | | no minors label exists | NO SUB-DRIVER |
| throw (arm z) | eARM | none | | no minors label exists | NO SUB-DRIVER |
| slider, curveball, changeup (MLB whiff 2024+) | eSL, eCB, eCH | none | MLB pools 109 to 232 players | | NO SUB-DRIVER |

Notes on the table:
- **eHIT measures K% avoidance**, because the framework's hit estimand is K% (TL-Q2). Batting
  average was not re-tested here. The sub-drivers that tie with translated K% (pitch-level
  contact, two-strike contact, swinging strikes, each +0.16 to +0.24 alone) were dropped as
  near duplicates of it (|r| 0.66 to 0.77).
- **eSEL and eBAT read a single MLB season (2026)** and board years 2022 to 2024 only (pitch
  selection and bat control grades start in 2021), so their MLB pools are 144 players. Both
  passed anyway; they are the thinnest passes.
- **eFB's big minors gain** (+0.176) is larger than its MLB gain (+0.068).
- **Raw power and speed** are consensus-strong already (speed grade 0.75 against sprint speed)
  and the stats add only on the minors label. Tracked exit velocity (Triple-A 2022+) had only
  44 MLB-label rows, under the 100-player floor.
- **FanGraphs' own sits/tops velocity** adds nothing to the fastball grade (d -0.016 and
  -0.006 on MLB): the graders already price it (correlation 0.77 with the grade).
- **Slider, curveball and changeup** have no usable MLB label before 2024 and their minors
  tracked labels are 81 to 136 players, so nothing was admitted; P/BF and P/IP even read
  negative on changeup MLB whiff (d -0.18 to -0.25).

Descriptive cells (never admitting): translated K% helps the hit grade in every position
group, level and age band read; the largest MLB-label cell is shortstops (+0.40, LB +0.26),
the smallest first basemen and DHs on the minors label (+0.09, LB +0.03). For the fastball the
K% gain is concentrated in A+ and AA (+0.14 and +0.09 on MLB) and is near zero in Triple-A.

## Accuracy weighting (gate 6)

| arm | what it does | result |
|---|---|---|
| AW1 | FanGraphs and MLB Pipeline weighted by position group (BA2 estimator, k 150, clamp 0.6 to 1.5) | NULL on all 13 tools; largest d +0.0033 |
| AW2 | AW1 plus the stat reading as a third weighted input | BEATS CONSENSUS on hit (+0.254 MLB, +0.239 minors), game power (+0.032, +0.041), bat control (+0.022, +0.012), fastball (+0.063, +0.122), command (+0.039, +0.065); NULL elsewhere |

So the answer to "can we accuracy-weight tool grades" is: weighting the outlets against each
other does not help (the two outlets are about equally accurate in every position group), but
weighting the stat reading in as a third voice does. AW2 lands close to the eTool itself, which
is the simpler construction to serve.

## P/PA, P/IP, P/BF and PAR (EW3-15)

**As tool sub-drivers** (gate Part P.2; raw = the rate, PAR = the rate over its level-season
anchor):

| tool | rate | L_MLB d (LB) | L_UM d (LB) | status |
|---|---|---|---|---|
| hit | P/PA PAR | +0.099 (+0.051) | +0.042 (+0.022) | admitted to eHIT |
| hit | P/PA raw | +0.089 (+0.043) | +0.038 (+0.018) | qualifies; dropped as a duplicate of PAR (r 0.99) |
| pitch selection | P/PA raw / PAR | +0.009 / -0.046 | +0.028 / +0.028 (q 0.041) | not admitted (MLB d not positive for PAR; r 0.68 with swing rate) |
| bat control | P/PA | -0.046 to -0.048 | +0.011 | no |
| fastball | P/BF raw | +0.064 (+0.019) | +0.133 (+0.094) | admitted to eFB |
| fastball | P/BF PAR, P/IP raw | +0.039, +0.037 | +0.087, +0.061 | qualify; over the cap of 3 |
| command | P/BF PAR | +0.009 (-0.017) | +0.017 (+0.007) | admitted to eCMD |
| slider, curveball, changeup | all four | -0.25 to +0.05 | -0.004 to +0.125 | no |

More pitches per batter faced reads as more strikeouts to come (swing-and-miss stuff runs deep
counts), which is why P/BF helps the fastball grade. More pitches per plate appearance as a
hitter reads as fewer strikeouts and more patience, which helps the hit grade.

**As direct eFV drivers** (gate Part P.3: the first atlas's rows, incremental over consensus FV
on reach3 and reach5 clean frames, w3 and l6): 232 tests, **none flagged** (smallest q 0.106).
The largest increments (P/IP PAR at Triple-A on reach3, +0.054, CI95 +0.004 to +0.103) did not
survive BH. This agrees with the DS-06 refusals of `ppa_rel` and `pbf_rel` (2026-10-14).

**Redundancy:** P/PA correlates 0.61 to 0.64 with walk rate and 0.38 with strikeout rate; P/IP
0.65 with walk rate and near 0 with strikeouts; P/BF 0.47 with each. Pitch rates are mostly
walk and strikeout rates in another unit, which is why they help a tool grade (where the
consensus grade is the base) more than eFV (where consensus FV already reflects the stat line).

**Grade revisions (descriptive, no outcome):** a high P/PA goes with a later rise in the
consensus pitch-selection grade (Spearman +0.17, n 269); every other pairing is within 0.10.

## What feeds EFV_X3

Pre-declared as ONE arm of the EFV_X3 registration (gate 7): the six passing eTools
(eHIT, ePOW, eSEL, eBAT, eFB, eCMD, unrounded) replace the raw `tool_*` features in
`efv_dataset.py`, the `W2S_COLUMNS` and the `TOOL_CELLS` in `efv5_combined.py` for those tools;
the other seven tools enter as consensus. The X1 features that now feed an eTool (k_rw, bb_rw,
iso_rw, babip_rw) leave X3's own feature list so the same stat line is not counted twice. P/PA
and P/BF enter only through eHIT, eFB and eCMD, not as separate eFV drivers. Served eFV does not
move; the owner decides any flip.

## The dark preview

`python etools.py --preview` built 1,632 live prospects from the 2026 boards (seasons through
2026). eHIT moves most: standard deviation 6.3 grade points from the consensus, 350 of 829
hitters by 5 or more. eFB: sd 5.3, 299 of 803. ePOW, eSEL, eBAT and eCMD: sd 2.6 to 3.2.
Disclosure before any flip: the preview's mean shift is +2.7 for eFB and +1.3 for eHIT (zero by
construction on the development rows), so the 2026 inputs sit off the development
distribution. Run a drift check and a mean re-centring before a flip.

## Disclosures

- EFV_X1 (80915e33) was merged into this lane after the registration to supply the translated
  rates (gate 0.2).
- The `*_raw` pitch-rate candidates are normalized within season across levels and the `*_par`
  forms within (season, level, role): the implementation reading of gate 3.3 and P.1.
- 23 (tool, candidate) pairs were NOT COMPUTABLE on at least one label (tracked Statcast
  components 2021+, FanGraphs exit-velocity extras): under 100 players.
- Pitch selection and bat control MLB labels read the 2026 season only (gate 2.1).
