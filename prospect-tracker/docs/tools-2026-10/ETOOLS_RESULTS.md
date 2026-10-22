# eTools results (2026-10-15)

The one look of `docs/tools-2026-10/ETOOLS_GATE.md` (registered at 3f240da6, built at 7686d75c),
run once on 2026-10-15 with `python etools.py --run --gate-sha 3f240da6`. Artifacts:
`data/_labs/etools/etools_eval.json` (verdicts, weighting arm, pitch-rate read, spent marker) and
`data/_labs/etools/etools_atlas.json` (every test row: 189 pooled tests, 963 descriptive cell
tests, 232 pitch-rate eFV tests). Every input's sha256 matched at start and end. Nothing served
moved: `ETOOLS_ON` is False and the preview went to `.cache/etools/preview.json`.

**Survivorship, stated beside every number.** L_MLB is accuracy AMONG DEBUTS: only players who
reached the majors have an MLB outcome. L_UM (translated Double-A and Triple-A outcomes over
seasons Y to Y + 2, capped at 2024) does not need a debut, but it does need 300 Double-A or
Triple-A PA (150 BF), which is itself a promotion outcome. **L_UM is accuracy AMONG PROMOTED
players:** of the 2,157 hitter frame rows with no debut by 2024, 822 (38%) carry it, and 70% of
the L_UM pool debuted; non-debuts who stalled below Double-A are on neither label (review
finding R1, amendment 1; the per-tool split and a non-debut-only read are in the review section
below). Every verdict below needed both labels. (An earlier version of this paragraph said L_UM
"covers debuts and non-debuts alike"; that overstated it.)

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
4. **P/PA, P/IP, P/BF and PAR (restated after the review, amendment 1 A2):** alone, over the
   consensus grade, P/PA helps the hit grade and P/BF the fastball grade, but **once translated
   K% is in, P/PA adds nothing to eHIT** (d -0.0004 on MLB, -0.0003 on the minors label).
   Given the other sub-drivers, P/BF adds about +0.004 to +0.007 to eFB and P/BF PAR about
   +0.002 to eCMD. They are **not** direct eFV drivers: 232 atlas tests over consensus FV, none
   flagged (confirmed by the re-run, R4).
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
| hit | P/PA PAR | +0.099 (+0.051) | +0.042 (+0.022) | admitted to eHIT; adds NOTHING given k_rw and babip_rw (A2) |
| hit | P/PA raw | +0.089 (+0.043) | +0.038 (+0.018) | qualifies; dropped as a duplicate of PAR (r 0.99) |
| pitch selection | P/PA raw / PAR | +0.009 / -0.046 | +0.028 / +0.028 (q 0.041) | not admitted (MLB d not positive for PAR; r 0.68 with swing rate) |
| bat control | P/PA | -0.046 to -0.048 | +0.011 | no |
| fastball | P/BF raw | +0.064 (+0.019) | +0.133 (+0.094) | admitted to eFB; given the others +0.004 (LB -0.001) MLB, +0.007 (LB +0.002) minors (A2) |
| fastball | P/BF PAR, P/IP raw | +0.039, +0.037 | +0.087, +0.061 | qualify; over the cap of 3 |
| command | P/BF PAR | +0.009 (-0.017) | +0.017 (+0.007) | admitted to eCMD; given the others +0.002 (LB +0.0004) MLB, +0.002 (LB +0.0005) minors (A2) |
| slider, curveball, changeup | all four | -0.25 to +0.05 | -0.004 to +0.125 | no |

The gains in this table are over the consensus grade ALONE: gate 4.4 admits on that plus a
pairwise |r| cap and never asked what a candidate adds alongside the others. The review's
margin read (A2, below) is the right answer to EW3-15: P/PA's gain for the hit grade is the
strikeout information it shares with translated K%; P/BF carries a small residual for the
fastball and command grades.

**As direct eFV drivers** (gate Part P.3: the first atlas's rows, incremental over consensus FV
on reach3 and reach5 clean frames, w3 and l6): 232 tests, **none flagged** (smallest q 0.106).
The largest increments (P/PA PAR at Single-A on w3, +0.073, CI95 +0.012 to +0.137, q 0.51; on
the pitcher side P/IP PAR at Triple-A on reach3, +0.054, CI95 +0.004 to +0.103, q 0.24) did not
survive BH. This agrees with the DS-06 refusals of `ppa_rel` and `pbf_rel` (2026-10-14). This
read was re-run once because of a code defect (R4, below); the re-run is identical.

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
iso_rw, babip_rw) leave X3's own feature list so the same stat line is not counted twice. No
pitch rate enters as a separate eFV driver. **Restated after the review (A2):** P/PA PAR in eHIT
and the pitch-level swinging-strike rate in eFB carry NO ADDED EFFECT given the other
sub-drivers; X3's own registration decides whether its arm carries them (recommended: drop
them; the reduced eTools beat consensus by as much, eHIT without P/PA +0.302 / +0.274, eFB
without swinging strikes +0.065 / +0.176). So P/PA adds no information to X3, and P/BF adds at
most about 0.007 through eFB and eCMD. **Promotion caveat (A1):** every passing eTool still beats
consensus on the non-debut part of L_UM, but L_UM itself is promotion-selected; a
promotion-free label is the open follow-up before any flip. Served eFV does not move; the owner
decides any flip.

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

## Review reads (amendment 1, registered 8f369ae2, run once)

The review of the look found three defects (R1 to R3), and writing the tests found a fourth
(R4). Amendment `docs/tools-2026-10/ETOOLS_AMENDMENT_1.md` was committed alone before any of
these numbers; code at 7cf54071; artifact `data/_labs/etools/etools_review_reads.json`. The
runner first reproduced the look's d_E for all 8 evaluated tools on both labels (all within
0.00005), and every input sha256 matched the look's and was unchanged at the end. None of this
changes a verdict.

### A1. L_UM is promotion-selected (R1)

Frame rows by L_UM present and debut by 2024, and d_E (eTool minus consensus, on L_UM) over
the non-debut and debut parts:

| tool | L_UM, debut | L_UM, no debut | no L_UM, no debut | no L_UM, debut | non-debuts with L_UM | d_E non-debut (LB), n | d_E debut (LB), n |
|---|---|---|---|---|---|---|---|
| hit | 1,882 | 822 | 1,335 | 399 | 38% | +0.197 (+0.156), 822 | +0.323 (+0.288), 1,882 |
| game_pwr | 1,882 | 823 | 1,335 | 399 | 38% | +0.023 (+0.006), 823 | +0.043 (+0.032), 1,882 |
| pitch_sel | 367 | 282 | 601 | 40 | 32% | +0.059 (+0.027), 282 | +0.078 (+0.046), 367 |
| bat_ctrl | 370 | 293 | 621 | 40 | 32% | +0.067 (+0.040), 293 | +0.089 (+0.066), 370 |
| fb | 2,007 | 912 | 1,030 | 353 | 47% | +0.162 (+0.120), 912 | +0.176 (+0.149), 2,007 |
| cmd | 2,005 | 912 | 1,031 | 353 | 47% | +0.057 (+0.037), 912 | +0.082 (+0.067), 2,005 |
| raw_pwr (not passed) | 381 | 313 | 929 | 697 | 25% | +0.020 (-0.001), 313 | +0.018 (+0.004), 381 |
| speed (not passed) | 1,882 | 823 | 1,335 | 399 | 38% | +0.050 (+0.037), 823 | +0.053 (+0.045), 1,882 |

- **No passing eTool is PROMOTION-DEPENDENT** (A1.3): all six beat consensus among promoted
  non-debuts, lower bounds above 0. The gains are smaller there than among debuts (eHIT +0.20
  against +0.32; ePOW +0.02 against +0.04).
- **Still unmeasured:** 24% (fastball, command) to 47% (pitch selection, bat control) of each
  frame has no debut and no L_UM, so it is on neither label; for those players there is no
  evidence either way. A promotion-free label (K% at the next MiLB level, or reaching
  Double-A) needs its own registration (A1.4) and is the open item before any flip.

### A2. What each sub-driver adds given the others (R2)

The eTool with the sub-driver against the eTool without it (d, LB), both labels. The reviewer
saw the three pitch-rate rows before the amendment (it says so), so those three are
reproductions, not blind reads:

| tool | sub-driver | L_MLB given the others | L_UM given the others | label |
|---|---|---|---|---|
| eHIT | translated K% | +0.254 (+0.215) | +0.239 (+0.216) | adds |
| eHIT | P/PA PAR | -0.0004 (-0.003) | -0.0003 (-0.0015) | **NO ADDED EFFECT** |
| eHIT | translated BABIP | +0.023 (+0.009) | +0.023 (+0.017) | adds |
| ePOW | translated ISO | +0.015 (+0.005) | +0.028 (+0.022) | adds |
| ePOW | fly-ball rate | +0.008 (+0.003) | +0.002 (-0.002) | adds (MLB) |
| eFB | translated K% | +0.013 (-0.007) | +0.086 (+0.072) | adds (minors) |
| eFB | P/BF | +0.004 (-0.001) | +0.007 (+0.002) | adds (minors), small |
| eFB | swinging-strike rate | +0.004 (-0.001) | +0.001 (-0.003) | **NO ADDED EFFECT** |
| eCMD | translated BB% | +0.028 (+0.014) | +0.051 (+0.041) | adds |
| eCMD | first-pitch strike rate | +0.002 (-0.004) | +0.005 (+0.002) | adds (minors), small |
| eCMD | P/BF PAR | +0.002 (+0.0004) | +0.002 (+0.0005) | adds, small |

So eHIT is in effect translated K% plus translated BABIP. On the MLB label eFB's gain is not
attributable to any single sub-driver (they overlap). The reduced eTools beat consensus as well
as the full ones (eHIT without P/PA +0.302 / +0.274). Any future forward-selection rule gains a
"given the chosen sub-drivers" step (A2.3), by its own registration.

### A3. Part P.3 re-run because of a code defect (R4)

`pitch_rate_lines` read a pitcher's BF exposure off the majority-role line even when the rate
came from the season line (the season-line fallback basis): 381 pitcher lines, all Complex
League 2024. Fixed and pinned in `test_pitch_rate_lines_read_exposure_off_the_rated_line`. The
tool reads (gate 3 to 6, P.2) read seasons through 2023 and no candidate value moved (0 of 4,348
pitcher rows), so they were not re-run. Part P.3 reads lines through 2025 and was **re-run once
as a registered read re-run because of a code defect**: 232 tests, 0 flagged, smallest q 0.106,
and every one of the 232 rows identical to the original (the changed 2024 and 2025 lines enter
no scored row). The original P.3 rows stay in `etools_atlas.json`.

### R3. Tests

`test_etools.py` now pins: gate 4.4 admission clause by clause (q, lower bound, permuted floor,
other-label sign, |r| cap, cap of 3, other label absent); the eTool fit recovering a planted c
through each label's TIP inverse, with both labels stacked and the train mask honoured; exact
`etool_apply` values and the 20 to 80 clamp; `build_preview` writing the preview and never the
served path while `ETOOLS_ON` is False (and the served path only when it is True); the
pitch-rate construction (majority-role exposure, fallback-basis exposure, PAR = rate over the
role anchor, pitchers' own hitting lines skipped); the ZMetric as-of value exactly unchanged by
a board-year line and shrunk by E / (E + k); the bootstrap spread; and the amendment's runner
guards, promotion counts, non-debut split and margin read. 28 passed.

## Flip prep reads (amendment 2, registered 9121d710, run once)

`docs/tools-2026-10/ETOOLS_AMENDMENT_2.md` was committed alone before any of these numbers;
code at b988fdd7; `python etools.py --flip-prep --amend-sha 9121d710` ran once on 2026-10-15
(93 s); artifact `data/_labs/etools/etools_flip_prep_reads.json`. Every look d_E reproduced (all
16 within 5e-5) before any interval, and every input sha256 matched at start and end. No
verdict changes; `ETOOLS_ON` stays False.

### F3. The two fixes

- **Bootstrap re-ranking.** Each draw now re-ranks within the board year on the resampled set
  (weighted mid-ranks), so a draw is the Spearman of the resample; the look kept the full-sample
  ranks fixed. Point estimates do not change. Every lower bound moved by at most 0.0044, and all
  six passes hold on both labels: eHIT +0.256 / +0.247 (look +0.259 / +0.249), ePOW +0.017 /
  +0.030, eSEL +0.045 / +0.048, eBAT +0.059 / +0.062, eFB +0.036 / +0.153, eCMD +0.024 / +0.061
  (MLB / minors). **No eTool is FRAGILE UNDER RE-RANKING.** Raw power and speed still fail on
  the MLB label (-0.013, -0.002).
- **Baseball America's weight.** AW1 averaged BA's grade at an implicit 1.0. BA now carries an
  explicit weight from the same estimator over the three outlets (BA grades exist on board years
  2023 and 2024 only); the derived weights sit between 0.92 and 1.05, so the arm barely moves:
  **AW1 is still NULL on all 13 tools** (largest d +0.0033; every point d within 0.0002 of
  the look's), and AW1 with BA excluded is NULL on all 13 too. AW2 (outlets plus the stat reading)
  still BEATS CONSENSUS on hit, game power, bat control, fastball and command.

### F1. Drift and re-centring

Live cohort: the 2026 boards, 1,632 players with a tool grade (829 hitters with a hit grade, 803 pitchers with a
fastball grade). Shift = mean (eTool - consensus) on the cohort; the development reference is
the 12 out-of-fold board years.

| eTool | live shift | development years' range | z | drifted | what drives it |
|---|---|---|---|---|---|
| eHIT | +1.33 | -3.01 to +3.01 | +0.52 | no | translated K% +2.32 of it; translated BABIP residual drifted (its share -1.02) |
| ePOW | +0.13 | -0.71 to +0.92 | +0.29 | no | |
| eSEL | -0.30 | -0.48 to +0.30 | -0.45 | no | |
| eBAT | +0.13 | -0.66 to +1.29 | -0.25 | no | |
| eFB | **+2.92** | -2.02 to +1.49 | **+2.76** | **yes** | translated K% residual drifted, +2.65 of the +2.92 |
| eCMD | +0.49 | -0.93 to +0.78 | +1.15 | no | |

So one eTool is off its development distribution: **eFB**, because the 2026 cohort's translated
strikeout rates sit above what their fastball grades predict, by more than in any development
year. eHIT's +1.3 is inside the range the development years themselves span.

Re-centring (each sub-driver's residual shifted to the training mean within the scoring cohort)
costs almost nothing out of fold: against the uncentred eTool, d is between -0.0017 and +0.0013
and every lower bound is above -0.0046 (tolerance -0.01), and the re-centred eTool keeps its
pass on both labels for all six (eHIT +0.302 / +0.274, eFB +0.067 / +0.176). **By the F1.7 rule
the re-centred eTool is the served construction for all six.** In the preview the mean shift
falls to between -0.02 and +0.04 grade points for every tool (eFB +2.92 to -0.02, eHIT +1.33 to
+0.01).

### F2. A promotion-independent read

**L_ANY** (the X1-translated line at any Minor League level, seasons Y to Y + 2 capped at 2024,
300 PA or 150 BF) exists for 80% of the hitter rows that were on neither label (1,074 of 1,335)
and 74% of the pitcher rows (764 of 1,030).

| eTool | L_ANY, all rows (d, LB, n) | L_ANY, rows on neither earlier label (d, LB, n) | IPW on L_UM (d, LB, n) | label |
|---|---|---|---|---|
| eHIT | +0.314, +0.291, 4,035 | +0.271, +0.228, 1,074 | +0.256, +0.225, 2,704 | PROMOTION-CLEAR |
| ePOW | +0.109, +0.101, 4,036 | +0.059, +0.046, 1,074 | +0.041, +0.029, 2,705 | PROMOTION-CLEAR |
| eSEL | not covered (no chase measurement outside tracked parks) | | +0.061, +0.040, 649 | PROMOTION-CLEAR (IPW only) |
| eBAT | not covered | | +0.075, +0.054, 663 | PROMOTION-CLEAR (IPW only) |
| eFB | +0.265, +0.245, 3,899 | +0.145, +0.107, 764 | +0.165, +0.142, 2,919 | PROMOTION-CLEAR |
| eCMD | +0.134, +0.123, 3,897 | +0.099, +0.069, 764 | +0.077, +0.061, 2,917 | PROMOTION-CLEAR |
| eSPD (not a pass) | +0.057, +0.050, 4,037 | +0.056, +0.043, 1,075 | | |

**Every passing eTool is PROMOTION-CLEAR.** The gain holds on the players who were on neither
label before (the ones who stalled below Double-A and never debuted), and when the promoted rows
are re-weighted to stand for the whole frame. Caveats beside the numbers: L_ANY still needs 300 PA
in affiliated ball over three seasons (a released player is off it); the IPW read assumes
selection on the model's covariates only (grade, age, level, board year, sub-drivers); eSEL and
eBAT rest on the IPW read alone.

### What changes for a flip

Nothing is served. The dark preview now carries, per player and passing tool, the re-centred
eTool (`etool`), the uncentred one, the 80% band and each sub-driver's contribution in grade
points. The PROSPX card shows them beside the consensus grade only when the card flag is on
(default off, pinned to `ETOOLS_ON`). The Library's eTools view reads `data/etools_eval.json`.
The flip question is in `docs/tools-2026-10/OWNER_QUESTION.md`.

Data note: since the look's preview, the 2026 pitch-event family was lit (baf8b3be), so the
preview's eSEL and eBAT spreads grew (sd 5.1 and 5.4 grade points against 2.6 to 3.2 before);
the construction did not change.

## MiLB fielding runs for field and arm (amendment 3, registered e1c13320, run once)

Owner decision EW3-44 (2026-10-19). `docs/tools-2026-10/ETOOLS_AMENDMENT_3.md` tested the
MILB_FIELDING_RUNS range component as an eFLD sub-driver and its outfield arm component as an
eARM sub-driver, board years 2022 to 2024, with a new upper-minors analog label (the MFR
component at Double-A and Triple-A, seasons Y to Y + 2 capped at 2024). **Neither passes;
field and arm stay on the consensus grade.** The full read is the dated note in the amendment's
section 10; the verdicts:

- **eFLD: NO SUB-DRIVER.** L_MLB d -0.013 (LB -0.073, 137 players); minors analog d -0.014
  (LB -0.055, 481 players), where the planted check is recovered (a powered null). The MLB
  label is underpowered (planted not recovered).
- **eARM: NO SUB-DRIVER; UNDERPOWERED.** The MLB-label test is not computable (62 players);
  minors analog d +0.061 (LB -0.0004, q 0.13), short of admission, and the planted check fails.
- Null comparators do not clear; zero comparators read exactly 0. Nothing served moved.

## eTools for stale-graded players (amendment 4, registered dff62ea9, run once)

Owner decision EW3-46 (2026-10-19). The served eTools covered only players with a tool grade on a
2026 list (1,632); the eFV board carries older grades forward (justin_riemer: FanGraphs only,
2024-08-01, hit 70). `docs/tools-2026-10/ETOOLS_AMENDMENT_4.md` re-ran the eTool pass statistic on
development rows whose consensus grade predates the board-year lists (the latest grade of each
outlet before the window, never a 2020 or 2021 list grade), the fit trained on fresh rows and
re-centred on the fresh test-year rows (the served construction), deciding on rows whose grade was
12 or more months old at May 1 of the board year. Stale-graded players rarely debut, so the MLB
label is not computable for the hitters (63 players); there the second label is L_ANY (amendment 2
F2.1). The full read is the dated note in the amendment's section 8; the verdicts:

- **eHIT HOLDS:** L_UM +0.417 (LB +0.340, 365 players), L_ANY +0.476 (LB +0.404). The gain is
  larger than on fresh rows (+0.274) and grows with the grade's age.
- **ePOW HOLDS:** L_UM +0.094 (LB +0.067), L_ANY +0.153 (LB +0.126).
- **eFB and eCMD: DOES NOT HOLD; UNDERPOWERED.** Both gain on the minors labels (eFB +0.251, eCMD
  +0.159 on L_UM), but on the MLB label (125 players) eFB reads -0.047 (LB -0.179) and eCMD +0.025
  (LB -0.053), and a planted gain of the registered size is not recovered there.
- **eSEL and eBAT: NOT COMPUTABLE** (22 and 24 players on L_UM).
- Zero comparators read exactly 0; no null comparator clears; planted recovery succeeds for hit
  and game power.

Served: `data/etools.json` gains eHIT and ePOW for 287 eFV-board hitters (574 eTools), each with
`grade_date` and `grade_age_months`; the 1,632 fresh players' records are unchanged. eHIT moves
from the stale consensus by -1.33 on average (sd 7.17; 133 of 287 by 5 or more), ePOW by -0.43 (sd
2.67; 17 by 5 or more). justin_riemer: eHIT 62 (61.57, from 70), ePOW 34 (from 35). The card
tooltip and eTools block name the scouting grade's date ("scouting grade from Aug 2024"). eTools+
follows by its registered pool (every player in `data/etools.json`): 1,116 hitters (was 829); the
pool's ePOW mean falls from 47.25 to 46.49, so 755 of the 829 existing hitters' eTools+ rise by 1
or 2. Stale-graded pitchers keep the consensus fastball and command grades.

## MiLB eBR as an eSPD sub-driver (amendment 5, registered 3cc6a8e6, not computable, not spent)

Owner decision EBR-Q6R (2026-10-21, "Test via eSPD"): does level-relative MiLB baserunning
(steals, caught stealing and pickoffs, advancement on hits and outs, outs on base) sharpen the speed
grade beyond the current eSPD (stolen bases per PA)? The runner (`etools_spd_ebr.py`) counted first
and computed no statistic: the MiLB eBR record starts in 2023 (Rookie and Single-A; the upper levels
in 2026), so in the development frame only board year 2024 has an as-of season, and its 191
candidate rows carry 3 MLB sprint-speed labels and 17 upper-minors labels (each label needs 100
players over 3 board years). **NOT COMPUTABLE**; the read is not spent and runs unchanged when the
record covers 2021 to 2023 at every level. Speed keeps the consensus grade; nothing served moves.
The dated note is in the amendment's section 9.
