# eWAR uncertainty band: a spread for every player-season, coverage-checked (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EWAR_UNCERTAINTY_BAND (owner decision EW3-50). This document
is committed ALONE, before any number of its estimands is computed: no split-half noise constant, no
source-disagreement constant on this document's seasons, no exposure multiplier, no coverage and no
interval score exists at this commit, and the code that computes them does not exist. Nothing in this
commit changes a model, an exporter, a flag or a served artifact. Part 13 is filled in afterwards;
nothing above part 13 may be edited once anything is written below it, and a change is a dated
amendment under part 13, committed alone. Its pin test is `test_ewar_uncertainty_band_gate.py`.

- The series: `docs/ebr-2026-09-30/EBR_GATE.md` amendment 11.10 (`data/ewar_v3.json`): the headline
  eWAR (the frozen fWAR vintage plus the ABS part from 2026) and eWAR realized (pitchers priced on the
  realized basis R2 from 2016, 11.10.3). The band is a spread around each served number; it changes
  neither number.
- The served band it sits beside: the Awards measurement band
  (`docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md` 4.2, `awards_core.band_constants`), which is the
  source-disagreement term alone at a 90 percent multiplier.

## 0. What kind of decision this is

- **A calibration read of a new served spread, decided once.** The question (owner, EW3-50): can every
  player-season eWAR from 2000 to 2026 carry a +/- whose nominal 80 percent band covers an independent
  same-season measure at its stated rate, in every exposure band? The read measures the band's
  calibration and nothing about either eWAR number's accuracy. It forecasts nothing and licenses no
  forecasting sentence.
- **Two terms.** The band's variance is a sampling term (how far a season's events could have fallen
  otherwise, measured from split halves of each component) plus a method term (how far two published
  WAR systems disagree on the same playing time). Part 2 defines both.
- **Built dark.** The read writes its tracked record to `data/_labs/ewar_uncertainty_band/record.json`
  (`data/_labs/` ships in neither deploy consumer) and its numbers to part 13 of this document. On a
  PASS the band is built dark behind a flag that defaults off, and one owner question decides the flip
  (part 10). On anything else nothing is built.
- **Not a re-score.** Parts 12.2 and 12.3 of EBR_GATE.md stand as written. The read admits no part
  into either eWAR series and moves no value of either; it uses eBR's priced events only as the
  baserunning component's noise proxy (part 2.2), which is not a comparison of eBR with BsR.

## 1. Decision record

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| EW3-50 | Make eWAR better than both fWAR and bWAR without redoing failed work | four arms approved: EWAR_TEAM_ACCOUNTING, EWAR_PITCHING_BLEND, EWAR_UNCERTAINTY_BAND (this document), EWAR_PEH_OLD_SEASONS | answered 2026-10-22 (`DECISIONS_FOR_OWNER.md`, EW3-50) |
| EW3-5 | Look days and registered dates | waived: the read runs on any date | answered 2026-10-14 |
| EW3-20 | The two numbers | the headline eWAR and eWAR realized; Awards reads eWAR realized with its band | answered 2026-10-15 |
| AG4-Q | What a flip commit carries | only the flag, registry, glossary, copy and tests; regenerations are listed for the integrator | answered 2026-10-22 |

Defaults this document applies, named so the orchestrator records them: the nominal rate is 80
percent (z80 = 1.2816); the season split is by season modulo 3 (part 3); the exposure bands and floors
of part 3; the fielding component's sampling noise is not measured separately and rides in the method
term (part 2.2); a band is recalibrated only where its raw coverage on the calibration seasons misses
[0.77, 0.83] (part 4); the equivalence range is [0.75, 0.85] (part 7); the owner question's default is
part 10's (a).

## 2. The band

### 2.1 The served form

For player p in season s, with PA the vintage hitting row's plate appearances, IP the vintage pitching
row's innings (outs / 3), RPW_s FanGraphs' runs per win (`league_constants.league_totals(s)["rpw"]`)
and x in {headline, realized}:

```
sigma_samp^2(p, s, x) = [ m_bat(PA)^2 * k_bat * PA + m_ebr(PA)^2 * k_ebr * PA + m_pit,x(IP)^2 * k_pit,x * IP ] / RPW_s^2
sigma_src^2(p, s)     = m_src,bat(PA)^2 * k_src,bat * PA + m_src,pit(IP)^2 * k_src,pit * IP
sigma(p, s, x)        = sqrt(sigma_samp^2 + sigma_src^2)
band(p, s, x)         = eWAR_x(p, s) +/- z80 * sigma(p, s, x),      z80 = 1.2816
```

- k_pit,headline = k_fip; k_pit,realized = k_ra for a pitcher-season that carries R2 (2016 on, not a
  nopp row) and k_fip otherwise. A side with no row carries no term.
- Each m is the sd multiplier of part 4 for that term's family and the exposure band the row falls
  in (m_pit,headline from C2-fip, m_pit,realized from C2-ra on R2 rows); m = 1 where part 4 applies
  none. Below the floors of part 3 a side carries no band: the row's band is
  absent, never a wider guess.
- The two terms are added as independent. Both systems read the same events, so the sampling noise is
  shared by fWAR and bWAR and cancels in their difference; the method term is therefore measured on
  their difference and the sampling term on split halves. The independence of the two is an
  assumption, disclosed, and no clause tests the combined band directly (no measure independent of
  both exists).

### 2.2 The terms

| Term | Component | Exposure | Per-half value of one player-season half | Source of the halves |
|---|---|---|---|---|
| k_bat | batting runs | PA | `sum v / PA_h`, v = w_event / wOBA scale for uBB, HBP, 1B, 2B, 3B, HR (the season's solved weights, `league_constants.load()`), 0 for every other plate appearance | the runner record `.cache/pbp_runners` plays, 2011 to 2025 |
| k_ebr | baserunning runs | PA | `sum of eBR credits / PA_h` (`ebr.season_credits`, all five parts, the frozen pool) | the runner record, 2011 to 2025 |
| k_fip | pitching runs, FIP basis | IP | `-(13 HR + 3 (BB + IBB + HBP) - 2 K) / (9 IP_h)` | the play corpus `.cache/pbp_corpus` plays (pitcher on the mound), 2018, 2019, 2021 to 2025 |
| k_ra | pitching runs, runs-allowed basis | IP | `-(runs scored on plays while he pitched) / IP_h` | the play corpus, the same seasons |
| k_src,bat | method disagreement, hitting | PA | not split: `d = fWAR_bat - bWAR_bat` per player-season | the frozen vintage and the bWAR copy, 2000 to 2025 |
| k_src,pit | method disagreement, pitching | IP | `d = fWAR_pit - bWAR_pit` | the same |

- **The halves.** Odd against even `game_pk` within a season, as EBR_GATE.md 5.5 splits them. IP_h is
  outs recorded on the half's plays divided by 3; PA_h the half's plate appearances. A player-season
  enters a sampling term only when both halves carry exposure.
- **The noise constant** of a sampling term, from the FIT seasons (part 3), with x_A and x_B the two
  halves' per-exposure values and e_A, e_B their exposures:

```
k_c = sum over rows of (x_A - x_B)^2 / sum over rows of (1 / e_A + 1 / e_B)       runs^2 per PA or per IP
```

  It is the per-exposure noise variance under a rate that is constant within the season; drift within
  a season inflates it, which errs wide. Reported beside it, deciding nothing: the split-half Pearson
  r of the halves' values and its Spearman-Brown full-season reliability, per FIT season, at PA 300+ or
  IP 60+.
- **The method constant,** from the FIT seasons, as the Awards band builds it: `k_src = sum d^2 /
  (2 * sum e)`, the halving on the assumption that the two systems' method errors are independent and
  equal (disclosed).
- **What is not measured.** Fielding runs have no play-level split in the cached record; their sampling
  noise is not measured, and fWAR's and bWAR's fielding systems differ most, so their disagreement sits
  in the method term. Positional, league and replacement runs follow playing time and carry no
  sampling noise. eBR stands in for BsR's noise only: both price the same steals, advances and double
  plays, and neither's value is read. The pitching halves count every run scored while the pitcher was
  on the mound, not the runs charged to him; the k_fip halves use FIP, not FanGraphs' ifFIP. Each is
  disclosed with the band and none is corrected.
- **Seasons the constants do not see.** The sampling constants are measured from 2011 (batting and
  baserunning) and 2018 (pitching) and applied to every season from 2000; the method constant is
  measured from 2000. That extrapolation is disclosed with the band.

## 3. The frame and the season split

- **Seasons.** 2020 (60 games) and 2026 (the ABS part enters, so the headline departs from fWAR) are
  out of every check; both seasons still carry a served band. Each other season is FIT when `s mod 3 = 0`, CAL when `s mod 3 = 1`
  and TEST when `s mod 3 = 2`:

| Family | FIT (constants) | CAL (multipliers) | TEST (the read) |
|---|---|---|---|
| C1-bat, C1-pit (method) | 2001, 2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025 | 2002, 2005, 2008, 2011, 2014, 2017, 2023 | 2000, 2003, 2006, 2009, 2012, 2015, 2018, 2021, 2024 |
| C2-bat, C2-ebr (sampling) | 2013, 2016, 2019, 2022, 2025 | 2011, 2014, 2017, 2023 | 2012, 2015, 2018, 2021, 2024 |
| C2-fip, C2-ra (sampling) | 2019, 2022, 2025 | 2023 | 2018, 2021, 2024 |

- **Rows.** C1: player-season-sides the frozen vintage carries with a non-null `war` and that join at
  least one bWAR stint on the same side by MLBAM id (bWAR summed over stints), exposure from the
  vintage. C2: player-season-sides with both halves' exposure above 0, exposure e = e_A + e_B from the
  halves.
- **Floors and exposure bands.** Hitting side (PA): floor 20; bands [20, 100), [100, 300), [300, 500),
  [500, up). Pitching side (IP): floor 5; bands [5, 20), [20, 60), [60, 120), [120, up). Rows below the
  floor are out of every check and carry no served band.
- **Clusters.** Player: MLBAM id. Club: the franchise (`ewar._fold_team` of the Baseball-Reference
  team id) of the bWAR stint with the most exposure on that side in that season; a C2 row with no bWAR
  stint takes `pbp:` plus the record's most frequent team id of the player that season.
- **Refusals, checked before any statistic (a miss stops the read and writes nothing):**
  1. the frozen vintage id of `data/ewar_v3.json` equals the vintage's;
  2. every FIT, CAL and TEST season of every family carries rows, and every cell of part 7 carries at
     least 100 TEST rows and 50 CAL rows;
  3. the solved wOBA weights exist for every season of C2-bat;
  4. the eBR frozen pool passes `ebr.check_frozen_pool`;
  5. every k is finite and positive.

## 4. The multipliers (recalibration by exposure, split conformal)

For a family f, a CAL row i with statistic D_i and predicted sd SD_i (part 5), in exposure band b:

```
raw coverage on CAL  c_b = share of CAL rows in b with |D_i| <= z80 * SD_i
if c_b is outside [0.77, 0.83]:   m_b = ( q_0.8 of |D_i| / SD_i over CAL rows in b ) / z80     (the split-conformal sd multiplier)
else:                             m_b = 1
```

m_b is an sd multiplier; part 2.1 squares it. The multipliers are fixed from CAL before any TEST row is read
and are never refitted on TEST.

## 5. The checks (what the band must cover)

| Family | Statistic D | Predicted sd SD | Meaning |
|---|---|---|---|
| C1-bat, C1-pit | `fWAR_side - bWAR_side` | `sqrt(2 * k_src * e)` | the other source falls inside the method band (both systems carry the method sd, so the difference carries it twice) |
| C2-bat, C2-ebr, C2-fip, C2-ra | `e * x_A - e * x_B` (each half rescaled to the full season) | `sqrt(k_c * e^2 * (1 / e_A + 1 / e_B))` | one half, rescaled, falls inside the other half's band |

A row is covered when `|D| <= z80 * m_b * SD`. The read's estimand per cell is the TEST coverage of the
final band (multipliers applied). In the TEST seasons the headline eWAR equals fWAR on every row, so
C1 is the headline's check; C1 on eWAR realized's pitching side (`fWAR_pit + Delta_r - bWAR_pit`) is
reported beside, deciding nothing.

## 6. The comparators, the interval score and the planted check

- **The interval score** of a symmetric band of half-width h for statistic D at alpha 0.2:
  `IS = 2 h + (2 / 0.2) * max(0, |D| - h)`. Lower is better. Per family, `d(N) = mean IS(N) - mean
  IS(candidate)` over TEST rows; positive favours the candidate.
- **N0, the exposure-blind null.** One half-width per family, the 80th percentile of |D| over its CAL
  rows: a band calibrated overall that ignores playing time.
- **N1, the no-change null.** What the site serves today: the Awards measurement band's constants as
  served (`data/awards_eval.json` `realized_read_band.band`, k_bat and k_pit), h = z80 *
  sqrt(2 * k * e) on C1, and no sampling term (h = 0) on C2. N1's constants were fitted on 2015 to
  2025, which includes TEST seasons; disclosed, and it favours N1.
- **The bootstraps.** Two, B = 4,000 each, seed 20261023, each from its own generator seeded 20261023:
  player-clustered (MLBAM ids drawn with replacement with all their TEST rows in every family) and
  club-clustered (franchises drawn with replacement with all their TEST rows). One draw per replicate
  is shared by every cell and family (paired). Per cell: the 5th and 95th percentiles of coverage. Per
  family and null: the sd of d over the replicates and `lo = d - 1.645 sd`.
- **The planted check, run before the read on the real design and on no real statistic.** It keeps
  every family's real rows (seasons, FIT/CAL/TEST, exposures e, e_A, e_B, clusters) and draws
  synthetic statistics. Twenty replicates from a generator seeded 20261023; in each, per family:
  - the truth: `D = SD_true * t`, SD_true the part 5 form with a planted constant k* = 1, multiplied by
    sqrt(2) on rows in the lowest exposure band (a planted excess the raw band misses), t a Student t
    with 5 degrees of freedom scaled to unit variance;
  - the truth candidate runs the whole design (k from FIT, part 4 on CAL, the cells and nulls on TEST)
    with B = 500 per bootstrap;
  - the broken candidate is the same design with part 4 switched off and every k multiplied by 0.6;
  - **PLANTED PASS** when the truth candidate reads PASS (part 7) in at least 16 of 20 replicates and
    the broken candidate in at most 1 of 20. Printed beside, deciding nothing: the number of
    replicates in which part 4 flagged the planted band.
  - The identity check: a candidate scored against itself as its own null gives d = 0 exactly.

## 7. The pass rule

The cells: C1-bat and C1-pit by four exposure bands each, C2-bat, C2-ebr, C2-fip and C2-ra by four
exposure bands each: 24 cells.

- **CALIBRATED** when, in every one of the 24 cells, the 5th to 95th percentile interval of TEST
  coverage lies inside [0.75, 0.85] under both bootstraps (an equivalence test at 0.05 each side).
- **SHARPER THAN THE NULLS** when `lo > 0` under both bootstraps for d(N0) in all six families and for
  d(N1) in the four C2 families. d(N1) on C1 is reported, deciding nothing: the candidate's method
  term is the served band's form refitted, and its gain there can only come from part 4.
- **PASS** when CALIBRATED, SHARPER THAN THE NULLS and the planted check read PLANTED PASS. Each cell,
  family and bootstrap must hold, so no multiplicity correction applies. A read whose planted check
  failed cannot PASS: it is recorded with its cells and the disposition "UNRESOLVED (the design did not
  recover a planted band)". Anything else is NOT PASS, with every failing cell named.

## 8. Reported beside, deciding nothing

- The raw band's TEST coverage per cell (before part 4), and each m with its CAL coverage.
- The split-half reliabilities of part 2.2.
- C1 on eWAR realized's pitching side.
- The served band's median half-width (wins) per exposure band and series over 2000 to 2026, and its
  sampling and method shares.
- A census: player-seasons 2000 to 2026 that would carry a band, per side and season.

## 9. Registered expectations

- The method term will dominate at high exposure (two systems disagree on fielding and on pitching
  basis by more than a season's events vary), the sampling term at low exposure.
- k_ra exceeds k_fip (runs allowed carry balls in play and sequencing that FIP leaves out).
- The Awards band's tercile k (EWAR_SITEWIDE_CALIBRATION.md 9.1) says the method variance is not
  proportional to PA for hitters at low playing time, so part 4 is expected to act on C1-bat's lowest
  band. No prior is stated on the sampling cells.

## 10. What may and may not be claimed, and what a result licenses

- **A PASS builds the band dark and raises one owner question,** EWUB-Q1, recorded in the task report:
  (a) flip the band on player cards and the eWAR board, and print it beside eWAR realized in Awards
  while the Awards realized read keeps its registered measurement band for its verdicts (default);
  (b) (a), and the Awards realized read's verdicts move to this band (an amendment to
  EWAR_SITEWIDE_CALIBRATION.md, registered alone first); (c) record only, nothing served. A flip goes
  through the flip rule (owner AG4-Q): flag, registry row (`ewar_band`, provisional,
  `measurement_only`), glossary entry, copy and tests in one commit, the regenerations listed for the
  integrator.
- **Not PASS:** the record and part 13 only; nothing is built, no owner question is required.
- May (after a flip): "the band covers the other published WAR and a split-half rescaled season at
  about its stated 80 percent rate in every playing-time band, on seasons held out from its
  constants", with the frame. May not, under any result: that the band is a confidence interval for
  talent; that a player's true value lies in it with 80 percent probability; that eWAR is more accurate
  than fWAR or bWAR; any forecast; "validated" or "proven".

## 11. The one read

1. Dry run on fixtures (`test_ewar_uncertainty_band.py`): every reporting path runs on a synthetic
   frame with null values, a short family and an empty exposure band, and the planted machinery
   recovers a planted band on a synthetic design.
2. The planted check (part 6) on the real design, printed and recorded.
3. The read, ONCE: `python tools/ewar_uncertainty_band_lab.py --read`, its stdout and stderr teed to
   the task's output directory before anything else runs. It checks part 3's refusals, prints the
   constants, the multipliers, the bootstraps' sd, then the cells, the families, the disposition and
   part 8, and writes `data/_labs/ewar_uncertainty_band/record.json` (inputs with sha256, frame counts,
   every constant, multiplier, cell and comparison, the planted check and the disposition). A second
   `--read` refuses while the record exists.
4. **Crash protocol.** An exception before scoring began: fix and rerun, recorded. An exception after
   scoring began: STOP without rerunning, write the owner question, record VOID in part 13.
5. Part 13 records the result in a commit of its own.

## 12. Bans, and what was read before this registration

- **Bans.** The read relates no dark betting column to any game outcome or price
  (`docs/diamond-betting.md`); computes no realized MLB statistic by consensus-FV, FV or eFV cell
  (`docs/PROSPECT_ANCHOR_GATE.md`); reads no reserved eFV frame; runs no projections retrain and no
  `backtest.run_backtest`. It reopens nothing on the do-not-reopen lists of EBR_GATE.md parts 12.2 and
  12.3: HEM+ and xHEM+, the S2 shrunk rates, S2b, the global HR shrink, DEM+, S3t, S3c, PE-P, the
  positional ladders v1 to v3, runs per win (FanGraphs' own converts the sampling runs) and eBR against
  BsR.
- **What was read before this registration (disclosed).**
  - The Awards measurement band as built (EWAR_SITEWIDE_CALIBRATION.md 9.1): k_bat 0.000525 wins^2
    per PA over 8,592 player-seasons and k_pit 0.003787 per IP over 8,221 (2015 to 2025, 2020 out),
    and its exposure terciles. Its seasons overlap this read's TEST seasons 2015, 2018, 2021 and 2024.
  - EBR_GATE.md 5.5 and 12.1: eBR's split-half reliabilities by part over 2018 to 2026 at PA 300+.
  - To write this document the writer read the structure and coverage of the inputs only: the runner
    record carries MLB plays 2011 to 2026 without a pitcher id; the play corpus carries plays with the
    pitcher for 2018, 2019 and 2021 to 2026; the solved wOBA weights cover 2011 to 2026; the bWAR copy
    and the vintage cover 2000 to 2026. No half, constant, coverage or disagreement was computed.

## 13. Results
### 13.1 2026-10-22: amendment before the read, committed alone (the planted check on the registered design failed)

`python tools/ewar_uncertainty_band_lab.py --planted` on the real design (every family's real rows,
seasons, exposures and clusters; synthetic statistics only, no real half, disagreement or coverage
computed) read PLANTED FAIL under the registered design: the truth candidate passed in 0 of 20
replicates (between 4 and 9 of the 24 cells outside [0.75, 0.85] in each), the broken candidate in 0
of 20. The failing cells were the pitching sampling cells and the high-exposure baserunning and batting
cells, the ones with the fewest rows: the play corpus gives C2-fip and C2-ra one CAL season (101 to
277 rows a band) and three TEST seasons (319 to 829 rows a band). Two causes, measured on the same
planted design before any real statistic:

- the "if off" rule of part 4 leaves a band whose CAL coverage sits inside [0.77, 0.83] by chance at
  its raw coverage, which for the planted t5 noise is 0.84 on TEST, and the 90 percent interval of a
  cell of 300 to 800 rows then reaches above 0.85;
- a multiplier set on one CAL season's 100 to 280 rows carries a coverage error of about 0.03 on its
  own, so with the TEST interval's half-width (0.02 to 0.04) a cell needs its point within about 0.015
  of 0.80 to lie inside [0.75, 0.85], and 24 such cells together almost never do.

Variants scored on the same planted design (20 replicates, B 500, seed 20261023; truth passes,
broken passes): registered, 0 and 0; multiplier always applied, CAL only, [0.75, 0.85], 0 and 0;
always, FIT and CAL, [0.75, 0.85], 0 and 0; always, FIT and CAL, [0.725, 0.875], 10 and 0; always,
FIT and CAL, [0.70, 0.90], 19 and 0; always, CAL only, [0.70, 0.90], 10 and 0.

**Amended, binding for the read** (the read has not run; nothing above part 13 is edited):

1. Part 3 and 4: the constants k and the multipliers m are both set on the training seasons, FIT and
   CAL together; TEST stays held out and is read once. The season split, rows, floors, bands and
   clusters are unchanged.
2. Part 4: the split-conformal multiplier is computed and applied in every band (the "if off" window
   [0.77, 0.83] is dropped). The record keeps each band's raw training coverage, so a band that was
   off is visible; where the raw band was on target the multiplier is near 1.
3. Part 6: N0's half-width is the 80th percentile of |D| over the training rows; N1 is unchanged. The
   broken candidate keeps k from the training rows, multiplied by 0.6, with no multiplier.
4. Part 7: the equivalence range is [0.70, 0.90]: CALIBRATED when in every one of the 24 cells the
   5th to 95th percentile interval of TEST coverage lies inside [0.70, 0.90] under both bootstraps.
   Everything else in part 7 stands, PLANTED PASS included, and the planted check is rerun on the
   amended design as the read's first step.
5. Part 10: the claim a flip may make reads "covers ... at a rate between 70 and 90 percent in every
   playing-time band" in place of "at about its stated 80 percent rate".

Defaults this amendment applies, named for the orchestrator: training seasons FIT and CAL together;
the multiplier always applied; the equivalence range [0.70, 0.90], the narrowest of the measured
variants whose planted truth reached 16 of 20.
