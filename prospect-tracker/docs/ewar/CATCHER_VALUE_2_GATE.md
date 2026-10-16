# Catcher value 2.0: the measure and its two validations (catcher_value_v2)

Task EWAR_INNOVATE_LEDGER, item (c) (owner decisions EW3-16 to EW3-23, 2026-10-15; the ewar-map
plan's innovator item 3; `docs/roadmap/post_launch_frontier.md` "Catcher Value 2.0 + Challenge
Value", whose premise of zero ABS data is wrong: the 2026 feeds carry every challenge). This
document is committed ALONE, with its pin test `test_ewar_innovate_registration.py`, before the
measure's code exists and before any number of its estimands is computed. A change after the
first number is a dated note in part 8, never an edit above it.

STATUS: REGISTERED, RESULTS EMPTY.

## 0. What it is

- **The measure, per catcher-season, in runs saved (fielding side positive),** read from the
  pitch-level ledger (`docs/ewar/PITCH_LEDGER_GATE.md`) over the steps he caught:

```
FRM   = - sum of x_frm                 framing, on our own called-strike model with umpire,
                                       pitcher and batter effects held apart, fitted on the call
                                       that stood (in 2026, net of challenge exposure)
BLK   = - sum of (x_babs + x_blk)      blocking: expected wild-pitch and passed-ball cost of the
                                       pitches he caught minus the cost that happened
THR   = - sum of x_sres                throwing: steal events against him beside the season's
                                       mean outcome of the same event from the same base-out state
CV2   = FRM + BLK + THR
eABS  = - sum of x_ch on the challenges he made, minus eABS v0's option cost of his failed ones
        (2026 only; reported beside CV2, never inside it, part 0.1)
```

  Rates: per 1,000 pitches caught. The catcher is the feed's defense alignment at each step.
- **eABS is the owner's call** (EW3-19: "eABS = run the stability check, then the owner chooses
  whether it enters eWAR"). The stability check read NULL for catchers (rho 0.122, lo95 -0.003,
  `data/_labs/eabs`, 11b36571). CV2 therefore never carries eABS under this document; the
  catcher's challenge runs are reported beside it, and the owner's question is restated in this
  task's report with the numbers.
- **Measured, never served, under this document.** CV2 is a candidate for the eWAR v3 skill look
  only through a dated amendment to `docs/ebr-2026-09-30/EBR_GATE.md` part 11, committed alone
  after both validations of part 3 pass and before that look (part 5).

## 1. Data

The ledger's inputs (its part 1) and its outputs for 2018 and 2019 (the development seasons) and
2021 to 2026 (the descriptive census of part 2 only). FanGraphs' catcher fielding and framing per
season from `saber_feed.load_components` (fld and frm) and innings at catcher from
`data/fielding_innings.json`, as comparators. Savant's catcher blocking (`.cache/savant_catcher/
blocking_2026.csv`) and throwing (`throwing_<Y>.csv`) as descriptive comparators. eABS v0's
per-challenge values (`data/_labs/eabs`) for the 2026 eABS column.

## 2. Descriptive census (same season; no verdict)

Per season: catchers at 2,000 or more called pitches caught, the sd of FRM, BLK, THR and CV2 in
runs and per 1,000 pitches, the share of CV2's variance from each part, Pearson r of FRM with
FanGraphs' frm and of THR with Savant's catcher stealing runs, and for 2026 BLK with Savant's
blocking runs and the eABS column beside CV2.

## 3. The two validations (development seasons 2018 and 2019 only)

The eWAR v3 skill look's frame (predictor seasons 2021 to 2024) and holdout are never read here.

**3.1 V-P, self-persistence.** Pairs (2018, 2019): catchers with 2,000 or more called pitches
caught in both seasons. Statistic: Spearman of CV2 per 1,000 pitches in 2018 with the same in
2019. Comparator reported beside, no weight: FanGraphs' catcher runs (fld + frm of catcher rows,
per 1,000 innings at catcher) on the same catchers. Null comparator: CV2 permuted across the 2018
catchers (`random.Random(20261016)`); its rho must have lo95 at or below 0. **Passes** when CV2's
rho has lo95 above 0 under a catcher bootstrap (B = 2,000, seed 20261016) and the permuted twin
fails. Power: about 40 to 60 catchers; MDE95 printed before the rho.

**3.2 V-S, catcher switches and the team's runs allowed (same season, held out).** For each team
season in 2018 and 2019, the team's games are split by the parity of the team's game number
(dates ordered, doubleheaders by game_pk). For a catcher c with 300 or more plate appearances
caught in each half:

```
CV2_h(c)  = his CV2 per plate appearance caught, measured on half h
WOWY_h(c) = sum over pitchers j of w_j * (y_j,c - y_j,other) / sum w_j,   on half h
            y_j,c      the mean of -dRE per plate appearance (runs saved, every step of the plate
                       appearance) when j pitched and c caught; y_j,other the same with any other
                       catcher of the team
            w_j        1 / (1 / n_j,c + 1 / n_j,other), the plate-appearance counts; pitchers
                       with a plate appearance on both sides only
```

  CV2_h is read from a ledger whose person effects (the ledger's part 4.2) are refitted on half
  h's games alone, with the frozen sigma values and the season's league model p0 and cell models
  unchanged (league quantities, not the catcher's). Each catcher-team-season gives two
  observations: (CV2 on the even half, WOWY on the odd half) and (CV2 on the odd half, WOWY on the
  even half), so the measure never sees the games it is scored on. Statistic: Pearson r over all observations of CV2_h with WOWY_other-h, each centred on the
  team-season's plate-appearance-weighted mean. Bootstrap: catchers drawn with replacement with
  all their observations, B = 2,000, seed 20261016. Null comparator: CV2_h permuted among the
  catchers of the same team-season (team-seasons with one qualifying catcher drop from the twin
  and are counted), r lo95 at or below 0. Planted recovery on a simulated copy of 2018 (part 7)
  must pass and its null must fail. Reported beside, no weight: the same r for FanGraphs' season
  catcher runs per inning (not held out, so favoured) and for each of FRM, BLK and THR alone.
  **Passes** when r has lo95 above 0 and the twin fails.

**3.3 The verdict.** DEV PASS when V-P and V-S both pass; NOT VALIDATED otherwise (a complete
result). A VOID is a twin that passes: nothing is registered.

## 4. Registered expectations (predictions, not measurements)

FRM carries most of CV2's spread; V-P passes (framing is among the most persistent fielding
skills); V-S is positive and may not clear its interval at about 60 to 100 catcher-team-seasons;
BLK and THR are small; the 2026 eABS column is under 2 runs for most catchers.

## 5. What a DEV PASS licenses

A dated amendment to `docs/ebr-2026-09-30/EBR_GATE.md` part 11, committed alone before the skill
look, registering a catcher candidate part "C2" on 11.2.1's footing: for catcher rows, the
departure CV2 minus FanGraphs' catcher fielding runs (fld + frm on catcher innings), re-centred
to 0 per season over catchers; its target the next season's pitcher-matched runs saved while
catching (the WOWY of 3.2 over the whole season, per plate appearance caught; total: times plate
appearances caught), a construct neither series reads; its B0 FanGraphs' catcher runs per plate
appearance caught; cells {C-rate, C-total}, Holm k = 2; the twin, B1, the team guard of 11.2.4 on
the hitter side, the secondary estimand; frame predictor seasons 2021 to 2024 at 2,000 called
pitches caught in both seasons. Never eABS inside C2 unless the owner admits eABS.

## 6. What is never done

- No served number, page, registry row or glossary entry reads CV2 under this document.
- No year-to-year, split-half or forward statistic of CV2 or its parts on any season pair with a
  predictor season 2021 to 2025.
- No claim that CV2 is "true talent" or better than any public catcher metric; V-P and V-S speak
  only for their frames.

## 7. Tool and tests

`catcher_value.py` (pure: the sums, WOWY, the halves), `tools/catcher_value_lab.py` (with
`--dry-run` on a synthetic fixture with nulls; stdout and stderr teed to the output directory),
`test_catcher_value.py`. The fixture plants catcher effects that move runs saved; V-P and V-S read
pass on it, an all-zero CV2 reads neither, and the twins fail. Output: `data/_labs/ewar_innovate/
catcher_value_eval.json` (tracked, never shipped); per-catcher values only in
`.cache/ewar_innovate_ledger/catcher_value/`.

## 8. Results and dated notes

EMPTY.
