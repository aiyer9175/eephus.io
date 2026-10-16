# SDR_CATCHER_GATE: the catcher-only SDR measurement (registered 2026-10-16)

STATUS: REGISTERED 2026-10-16. This document is committed ALONE, before the gate's tool exists and
before any number of its estimands is computed. A change after the first number is a dated note in
part 11, never an edit above it.

Owner decision EW3-33 (2026-10-16, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): SDR-GA-Q1 answered
"re-register + catcher now". This is part 1 of that answer (task SDR_CATCHER_GATE): a catcher-only
SDR measurement under its own gate, read once, today, recorded as an OWNER-WAIVED EARLY READ (EW3-5).
Part 2 (SDR_POSCENTRED_REGISTER, the position-centred G-A re-check on the unseen 2026 to 2027 pairs)
is a separate registration and is not touched here.

## 0. What was read before this registration

Every number below was computed before this document by other reads; none of this gate's
estimands (parts 3 and 4) has been computed on any frame.

- **G-A's catcher cell** (`SDR_EVAL_GATE.md`, Results 2026-10-15, A5, reported never gated):
  consecutive pairs (Y, Y + 1), Y 2017 to 2025, catchers with 300+ innings at C in both seasons,
  321 pairs. Self-persistence of the per-inning rate: SDR 0.6145, B-Ref rfield 0.0248, d +0.5897,
  LB95 +0.451. Components on the same rows: framing (the drop's `framing_runs`, FanGraphs CFraming)
  0.6139 (321 pairs), blocking (the drop's `blocking_runs`, Savant) 0.5248 (277). C4's 2026 catcher
  names (Dingler +13.6, Raleigh -4.6, Bailey +5.5).
- **The fielding triangulation's catcher cell** (`docs/ewar/FIELDING_TRIANGULATION_GATE.md` part
  11, 234 pairs): its shrunk catcher components against FRP + CFraming on DRS per inning at C in
  Y + 1, 0.4812 against 0.5149. No SDR value was scored there.
- **Catcher value 2.0** (`docs/ewar/CATCHER_VALUE_2_GATE.md` part 8.1): the in-house pitch ledger's
  catcher measure on 2018 and 2019 only.
- **Census facts read for this document, no estimand:** catcher rows at 300+ innings per season in
  the FanGraphs fielding cache, 2016 to 2026: 62, 61, 59, 61, 11, 60, 59, 63, 56, 57, 57. FanGraphs'
  FRP on catcher rows equals fFRP + bFRP + tFRP (Statcast framing, blocking and throwing runs) to
  within one run of rounding on all 1,208 catcher rows 2016 to 2026 (848 exactly). bFRP is zero on
  every catcher row of 2016 and 2017 (Savant blocking starts in 2018). The adapter's `no_drs` and
  `no_statcast` variant files carry catcher rows.
- **Never computed on any frame before this document:** the self-persistence of Savant's catcher
  runs (FRP at C) or of the playing-time comparator; any statistic on two-season-apart pairs; any
  next-season cross-system statistic of SDR, of either SDR variant or of any incumbent at catcher.

## 1. The candidate, the incumbents and the comparators

- **Candidate SDR_C.** The accepted drop's `sdr_runs` on catcher rows (`sdr_defense_card__2026-10-15.csv`,
  sha256 8a41d1c2...358e): Will's card `def_runs`, 06_total_defense_plus.py's `dplus_runs`. For a
  catcher it is the reliability-weighted mean of the within (C, season) z-scores of DRS and FRP (OAA
  does not rate catchers), scaled to runs by the catcher DRS sd of the window and shrunk by
  Inn / (Inn + 269). The catcher skills enter through those two systems: DRS's catcher parts (Sports
  Info Solutions: stolen bases rSB, strike zone rSZ, good fielding plays rGFP and the rest of its
  catcher scope) and FRP's (Statcast framing fFRP, blocking bFRP, throwing tFRP). Rate: `sdr_runs`
  per inning at C. Nothing in Will's method is edited or refitted.
- **Components, reported, never inside SDR_C and never gated:** framing, blocking and throwing per
  inning at C as Statcast measures them (fFRP, bFRP, tFRP), and the drop's `framing_runs`
  (FanGraphs CFraming). Will's 25_catcher_components.py measures throwing by pop time, which is not
  in runs; tFRP is the runs reading of the same skill.
- **Incumbent I-R, B-Ref rfield.** `runs_field` / `Inn` per player-season, summed over stints, from
  `.cache/war_daily/bat.parquet` as it stands at the read (sha256 and modified time printed before
  any statistic), G-A's construction. Disclosed, as in G-A: it is per player-season, not specific to
  the player's catcher innings, and B-Ref's catcher fielding carries no framing.
- **Incumbent I-S, Savant's catcher runs.** FRP on the catcher row (Statcast framing plus blocking
  plus throwing, as FanGraphs hosts them) per inning at C. SDR_C reads it, disclosed: the comparison
  asks whether blending DRS into the Statcast reading, with Will's scaling and shrink, measures
  catchers better than the Statcast reading alone.
- **Zero comparator Z.** Every catcher at 0 runs. A constant has no ranks, so its Spearman with any
  target is 0 by definition; a cell clears Z when the candidate's statistic has LB95 above 0.
- **Playing-time comparator PT.** Innings at C in season Y, more innings ranking higher (sign fixed
  here, not chosen after). It holds no fielding reading. SDR_C is built from z-scores of season
  totals and shrunk by innings, so part of its rate can carry playing time; PT measures how much of a
  forward relation playing time alone explains.

## 2. Frame (fixed here)

- **Rows.** The drop's catcher rows: player-season rows whose `primary_position` is C, 300+ innings
  at C, seasons 2017 to 2026 (the drop's coverage). Each row is joined on (player_id, season,
  Pos C) to the FanGraphs fielding cache row (DRS, FRP, fFRP, bFRP, tFRP) and on (player_id,
  season) to I-R. A pair needs every metric of its cell defined on both ends; the counts left out
  for a missing value are printed.
- **E1 pairs (deciding): two seasons apart.** (Y, Y + 2), Y 2017 to 2024: a catcher with a frame row
  in Y and in Y + 2, whatever he did in Y + 1. G-A's catcher cell used only (Y, Y + 1) pairs, so no
  E1 pair unit was scored there. The seasons themselves were read by that cell; no catcher season
  unseen by it exists before the 2027 season is played (that is SDR_POSCENTRED_REGISTER's frame), and
  this is the disjoint pair set the owner's "where possible" allows today.
- **E2 pairs (deciding): next season.** (Y, Y + 1), Y 2017 to 2025, a frame row in Y and a FanGraphs
  catcher row at 300+ innings in Y + 1. These are G-A's catcher pair units; on them only SDR_C's
  and I-R's self-persistence was computed. The cross-system targets, the two SDR variants, I-S and
  PT were never scored on them.
- **2020.** Pairs touching 2020 are included (per-inning rates); each deciding cell is reported
  beside without them, deciding nothing.

## 3. E1: self-persistence on two-season-apart pairs (deciding)

```
rho_m   = Spearman(rate_m(Y), rate_m(Y + 2))            m in {SDR_C, I-R, I-S}
rho_PT  = Spearman(Inn_C(Y), rate_SDR(Y + 2))
d       = rho_SDR - max(rho_I-R, rho_I-S)              better incumbent fixed at the point
d_PT    = rho_SDR - rho_PT
```

Player-clustered bootstrap (catchers drawn with replacement with all their pairs), B = 2,000, seed
20261017; every statistic of the cell recomputed on each draw. LB95 = the 2.5th percentile; the
one-sided p = the share of draws with d <= 0. The bootstrap sd of d and MDE95 = 1.96 x that sd are
printed before the point estimates.

**E1 passes** when all hold: rho_SDR beats both incumbents at the point; LB95(d) > 0; LB95(rho_SDR)
> 0 (clears Z); LB95(d_PT) > 0 (clears PT); Holm (part 5) rejects; its twin does not pass.

## 4. E2: next-season realized catcher runs, the EW3-23 form (deciding)

EW3-23 (EBR_GATE.md part 11.2) makes next-season realized runs from a source the candidate does not
read the deciding fielding target, and 11.2.2 scores a blend by leaving one source out. SDR_C reads
two systems, DRS and Statcast (FRP). For each system S, SDR_C rebuilt without S (the adapter's
variant, Will's 06 with S removed from its source list and nothing else changed) is scored on S's
catcher runs per inning in Y + 1, against the incumbent that does not read S:

| System left out | Candidate, season Y | Incumbent, season Y | Target, season Y + 1 |
|---|---|---|---|
| DRS (Sports Info Solutions) | SDR_C without DRS (`no_drs`, the FRP reading) | I-S | DRS per inning at C |
| Statcast | SDR_C without Statcast (`no_statcast`, the DRS reading) | I-R | FRP per inning at C (I-S's series) |

```
gap    = mean over S of [ rho(SDR_C without S (Y), T_S(Y + 1)) - rho(incumbent_S (Y), T_S(Y + 1)) ]
g_Z    = mean over S of   rho(SDR_C without S (Y), T_S(Y + 1))
g_PT   = mean over S of [ rho(SDR_C without S (Y), T_S(Y + 1)) - rho(Inn_C(Y), T_S(Y + 1)) ]
```

One cell, inside the same player-clustered bootstrap (B = 2,000, seed 20261017); p = the share of
draws with gap <= 0. Bootstrap sd and MDE95 of the gap printed first.

**E2 passes** when all hold: gap > 0 at the point with LB95(gap) > 0; LB95(g_Z) > 0 (clears Z);
LB95(g_PT) > 0 (clears PT); Holm rejects; its twin does not pass.

Disclosed: at catcher the `no_drs` variant is a rescaled FRP and I-S is FRP itself, so the DRS row
compares Will's within-season z, scale and shrink with the raw rate on one Statcast reading; the
Statcast row compares DRS, as Will scales it, with B-Ref's catcher fielding runs (which B-Ref builds
from Sports Info Solutions data). The cell does not score the two-system blend on a third catcher
system: none exists in the caches apart from the in-house pitch ledger, whose forward statistics on
predictor seasons 2021 to 2025 are reserved (`docs/ewar/CATCHER_VALUE_2_GATE.md` part 6).

## 5. Holm, twins, verdict

- **Holm** across E1 and E2 (k = 2) at alpha 0.05 on the one-sided p.
- **The twin** of each clause: `sdr_runs` and both variants' runs permuted within season among the
  frame's catcher rows (each row keeps its own innings), seed 20261018, one draw, scored by the same
  rule (Holm across the two twins). A clause whose twin passes is not credited.
- **Verdict.** PASS when E1 and E2 both pass; PARTIAL when one passes; FAIL when neither does. A null
  is a complete result.

## 6. Before the read: dry run and planted recovery

- **Dry run** on a synthetic fixture with nulls (catchers without a B-Ref row, without a Y + 2 row,
  without a variant value) through the whole reporting path; it writes nothing.
- **Planted recovery on the real design.** The real frame's rows (players, seasons, innings at C),
  every metric value replaced by simulation (seed 20261019; no real metric value is read):
  - PLANTED: a talent t ~ N(0, 1) per catcher, fixed across seasons; per-inning rates SDR_C and
    both variants = t + noise sd 0.5, I-S = t + noise sd 1.5, I-R = noise only, targets = t + noise
    sd 1.0. The rule must read PASS.
  - NULL: every value noise (t = 0). The rule must read FAIL, and Z must not be cleared in either
    clause.
  - PLAYING TIME ONLY: every rate = 0.5 x z(innings) + noise sd 1.0, no talent. PT must stop both
    clauses (the rule must not read PASS).
  If any of the three misbehaves, the read does not run: the defect is fixed and recorded in part 11
  before the read.

## 7. Reported beside, deciding nothing

- **R1** consecutive pairs (Y, Y + 1), G-A's pair units: self-persistence of SDR_C, I-R, I-S, DRS,
  PT and the components fFRP, bFRP (2018 on), tFRP and CFraming. SDR_C's and I-R's values repeat
  G-A's catcher cell.
- **R2** full SDR_C, I-R, I-S and PT on each E2 target (SDR_C reads both systems, so it is favoured).
- **R3** the total cell: E2's per-system statistics on runs (rate x innings at C) in Y and target
  runs in Y + 1.
- **R4** E1 and E2 without pairs touching 2020.
- **R5** the components' persistence on E1's pairs.
- **R6** the 2026 catcher board: the top and bottom 10 by SDR_C, named.

## 8. What each result licenses

- **PASS.** A catcher SDR measurement row is served: SDR_C runs and rate for catchers in the MLB
  Stats catcher defense view, a glossary entry and a provisional registry row, described as a
  measurement with this gate's frames, never as a validated forecast or as better than Statcast
  beyond what the cells show. SDR_C is handed to EWAR_V3_ASSEMBLE as the catcher defense part
  candidate (it enters eWAR only through a dated EBR_GATE.md part 11 amendment and the skill look)
  and to EWAR_LADDER's catcher handling (`FIELDING_TRIANGULATION_GATE.md` part 3.6) as an
  alternative to its shrunk components.
- **PARTIAL or FAIL.** Nothing is served and nothing is handed on. The result is recorded in part 11
  and in the task report; SDR_C's catcher numbers may be quoted only as measurements with their
  frames. G-A's verdict and SDR_POSCENTRED_REGISTER are not affected.

## 9. Registered expectations (predictions, not measurements)

- E1: SDR_C beats I-R by a wide margin; against I-S the point lands within 0.05 either way and LB95(d)
  does not clear 0, because SDR_C is the Statcast reading blended with DRS, and DRS's window
  reliability is the lower of the two (G-A's adapter receipt: FRP 0.515, DRS 0.400, pooled over
  positions).
- E2: the DRS row near 0; the Statcast row positive (DRS reads the strike zone, B-Ref's catcher
  fielding does not); the gap's LB95 near 0.
- Verdict: FAIL or PARTIAL.

## 10. Tool, artifact and tests

`tools/sdr_catcher_gate.py` (`--dry-run` on the fixture; `--simulate` for part 6; the read, once,
its stdout and stderr teed to the task's output directory), `test_sdr_catcher_gate.py` (the fixture,
the planted, null and playing-time worlds, the rule). Artifact
`data/_labs/sdr_catcher/sdr_catcher_eval.json` (tracked; `data/_labs` ships in neither deploy
consumer). Read once; never rerun on the same frame.

## 11. Results and dated notes

### 11.1 2026-10-16: the tool, the dry run and part 6's worlds, before the read

- **Tool committed before the read:** `tools/sdr_catcher_gate.py` and `test_sdr_catcher_gate.py`
  (7 passed). Dry run on the fixture with nulls (`--dry-run`): every block reports; writes nothing.
- **One fact the build met, recorded, nothing re-chosen:** I-S in Y and E2's Statcast target in
  Y + 1 are the same series (FRP at C), so part 6's planted world draws both with noise sd 1.5; the
  DRS target keeps sd 1.0 as registered.
- **Part 6 on the real design** (`--simulate`, the real frame's catchers, seasons and innings, every
  metric value replaced, seed 20261019, B 2,000), all five checks behave:
  - PLANTED reads PASS. E1: SDR 0.8278, I-S 0.3178, I-R -0.0064, d +0.5100 (LB95 +0.3804), Z LB95
    +0.7434, PT LB95 +0.7851. E2: gap +0.3178 (LB95 +0.2313), g_Z LB95 +0.4772, g_PT LB95 +0.4728.
  - NULL reads FAIL; neither clause clears Z (E1 rho_SDR -0.0002, LB95 -0.1331; E2 g_Z -0.0047,
    LB95 -0.0836).
  - PLAYING TIME ONLY reads FAIL, and PT stops both clauses (E1 d_PT LB95 -0.1293; E2 g_PT LB95
    -0.1411). Disclosed: among catchers at 300+ innings, innings in Y relate weakly to innings in
    Y + 1 or Y + 2 on this design, so the playing-time world's rates carry little persistence
    (E1 rho_SDR 0.0834 there).
