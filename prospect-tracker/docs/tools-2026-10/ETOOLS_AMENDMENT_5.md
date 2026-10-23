# eTools amendment 5: level-relative MiLB eBR as a sub-driver of eSPD (the speed eTool)

Registration status: REGISTERED

Task ETOOLS_SPD_MILB_EBR (owner decision EBR-Q6R, 2026-10-21, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`:
asked "Did we check eBR as a subdriver for eRUN / eFV?", answered "Test via eSPD"; it revises EBR-Q6
(2026-10-01: MiLB eBR on prospect cards, display only, never an eFV input) for this ONE registered
test), written 2026-10-21 on lane wt-ETOOLS_SPD_MILB_EBR (base f4b7dcfe). Docs only, committed alone
before any statistic named here is computed. It amends `docs/tools-2026-10/ETOOLS_GATE.md` (registered
3f240da6, look dc271ac2) and follows amendments 1 to 4. Timing: an OWNER-WAIVED EARLY READ under
EW3-5 (no look day applies). MiLB eBR stays out of every `efv_*` module: eFV can only ever see it
through a passing eSPD and the eTool re-weighting (`efv_etools_reweight`), never as a direct input.

## 0. Why, and what was already seen

At the look (2026-10-15) speed kept the consensus grade: eSPD on its one admitted sub-driver
(`sb_rel`, stolen bases per PA over the level-season mean) read +0.007 (LB -0.001, 2,015 rows, 849
players) on MLB sprint speed and +0.055 (LB +0.048) on the upper-minors label: NOT PASS on the MLB
label (`docs/tools-2026-10/ETOOLS_RESULTS.md`, `data/_labs/etools/etools_eval.json`). On 2026-10-20
EBR_Q6B_MILB_CARDS (`docs/ebr-2026-09-30/EBR_MILB.md`) built level-relative MiLB eBR from the
minor-league partition of the runner record (`.cache/pbp_runners/milb`, the permanent store),
previews `.cache/ebr/milb_preview/`.

**Seen before this document** (all published): the eSPD look and amendment 1 to 2 rows above; the
MiLB eBR build receipts (per level-season split-half reliability 0.14 to 0.50 stepped up, cross-level
continuity r 0.15). **No statistic pairing MiLB eBR with any tool grade or any outcome has been
computed by anyone.**

**Counted by this lane before writing** (presence only: rows, candidate coverage and label presence;
no grade or candidate was paired with a label value). The MiLB eBR record holds eleven level-season
units: Rookie and Single-A 2023 to 2026, Triple-A, Double-A and High-A 2026 only. A development board
year Y (gate 1.1, at most 2024) reads seasons up to Y - 1, so **only board year 2024 has any as-of
eBR season** (Rookie and Single-A 2023). The speed frame (hitters with a consensus speed grade,
identity and pre-debut rule of gate 1.3) holds 571 rows in 2024; 191 carry the candidate; of those, 3
carry the MLB sprint label and 17 the upper-minors label. **On the record as it stands the read is
NOT COMPUTABLE on every label** (section 3.4 needs 100 players and 3 board years of 20 or more rows).
This document still fixes the whole design, so the read runs once, unchanged, when the record covers
the as-of seasons (section 8): the minor-league partition would need the 2021 and 2022 seasons at
every level and High-A to Triple-A from 2021 to 2023 for board years 2022 to 2024.

## 1. Frame

1.1 **Board years**: the development years of gate 1.1 (2011 to 2019 and 2022 to 2024; 2020 and 2021
never) whose as-of window (seasons up to Y - 1) holds at least one complete MiLB eBR level-season unit
(`complete` in the build's unit list). Today: 2024. The runner asserts the years and that no
candidate season is at or after Y.

1.2 Grades, rows, identity, the pre-debut rule and the side exactly as gate 1.2 and 1.3
(`etools.load_board`, `etools.build_universe`, unchanged); hitters only. G_c is the consensus speed
grade, rounded to 0.5.

1.3 **Never** a stratum, cell, key, filter or weight by consensus FV or any source's FV
(`docs/PROSPECT_ANCHOR_GATE.md`). Tool grades are covariates only.

## 2. The candidate (fixed here; nothing is added after the read)

2.1 **Source.** Every player-season row of the level-relative MiLB eBR build
(`.cache/ebr/milb_preview/ebr_milb.json`, written by `tools/build_ebr_milb.py` from the runner record's
minor-league partition; fields `pa, sb, pk, xb_adv, xb_oob, dp, ebr`), complete units only, seasons up
to Y - 1 only, **150 or more PA per level-season** (the card's floor).

2.2 **Components.** The owner's list: stolen-base and caught-stealing runs with pickoffs (`sb + pk`),
advancement on hits and outs (`xb_adv`), and outs on base (`xb_oob`). The double-play part (`dp`) is
NOT in the candidate (it is not in the list and it mixes the batter's contact with his speed). Per
level-season line: r = (sb + pk + xb_adv + xb_oob) / PA.

2.3 **Level-relative z.** z = (r - mu) / sd within the unit (level, season), mu and sd PA-weighted over
every line of the unit at 150 or more PA (all players, not only board rows).

2.4 **Shrunk by reliability, as of.** Each unit's reliability constant k_u = n_bar (1 - R) / R, R the
unit's split-half reliability stepped up (Spearman-Brown, the build's receipt, odd against even games
inside the season, so it reads nothing after that season) and n_bar the unit's mean PA over its
150-PA players; R at or below 0.05 drops the unit. The candidate `ebr_milb` = the Marcel (5, 4, 3 by
recency over seasons Y - 1, Y - 2, Y - 3) and PA weighted mean of z over the player's qualifying lines,
times E / (E + k), E the Marcel-weighted PA and k the same-weighted mean of the k_u. Missing with no
qualifying line.

## 3. Labels (the estimands)

3.1 **L_MLB, sprint speed, unchanged from gate 2.1** (among debuts; first MLB season 2024 or earlier;
first three MLB seasons strictly after Y, to 2026; Savant qualifier). **Deciding.**

3.2 **L_BSR, MLB baserunning runs per 600 PA** (the frame eWAR keeps): FanGraphs BsR (`baseRunning`)
from the frozen fWAR vintage (`data/fwar_vintage.json`, hitting rows), summed over the same three
seasons and divided by the summed vintage PA, times 600; 300 PA. Among debuts. **Reported, deciding
nothing** (the speed tool's framework label is sprint speed; BsR asks whether the runner turns speed
into runs).

3.3 **L_UM, unchanged from gate 2.2**: stolen bases per PA over the level-season mean at Double-A and
Triple-A, seasons Y to Y + 2 capped at 2024, 300 PA. Accuracy AMONG PROMOTED players. **Deciding.**

3.4 **Computable.** A label is computable when the rows carrying G_c, the candidate and the label
number at least 100 players and at least 3 board years carry 20 or more such rows (gate 2.3 counted
on candidate rows: an eTool only moves where the candidate exists, so rows without it cannot carry the
test).

3.5 **Censoring, reported.** Per board year: frame rows; rows with the candidate; of those, debuts by
2024, rows carrying each MLB label, rows with no MLB line (censored for L_MLB and L_BSR), rows carrying
L_UM and rows below Double-A or under 300 PA (censored for L_UM).

## 4. Arms and statistics (gate 4 and 5 machinery, `etools.py` imported unchanged)

4.1 **Arms**, out of fold by player-disjoint leave one board year out (gate 4.1):
- **A0**, the consensus speed grade G_c;
- **A1**, the current eSPD: the gate 5.1 eTool on S = {`sb_rel`} (gate 3.3 construction, as of Y);
- **A2**, eSPD with the sub-driver: the gate 5.1 eTool on S = {`sb_rel`, `ebr_milb`}, both kept
  whatever their mutual Spearman (reported; gate 4.4's 0.6 cap and admission are reported beside it
  and decide nothing).
Each eTool is built and scored on the frame's rows (gate 5.1: TIP tables per deciding label on the
fold's training rows, c by OLS on L_MLB and L_UM stacked; L_BSR never enters a fit).

4.2 **Statistics.** d = rho_w(arm) - rho_w(comparator), rho_w the n-weighted within-board-year
Spearman (`etools.paired_d`); player-clustered bootstrap B 2000, seed 20261023, with the amendment 2
F3.2 re-ranked draws; one-sided 95% lower bound LB. Read on each label: A2 vs A1, A2 vs A0, A1 vs A0,
over the rows carrying the candidate and the label (3.4). Also the gate 4.1 incremental test of
`ebr_milb` over G_c (with its permuted floor, 200 draws, seed 20261024) on each label.

4.3 **Minimum detectable effect.** For each deciding d: MDE = (1.6449 + 0.8416) x the bootstrap sd
(one-sided 5% test, 80% power). When a label is not computable no sd exists; the runner then reports
the projection from the look's own eSPD read (sd 0.00464 at 849 players on L_MLB, 0.00426 at 1,334 on
L_UM) scaled by the square root of the player ratio, labelled a projection.

## 5. The rule

**PASS** when all three hold: (a) the LB of d(A2 vs A1) is above 0 on L_MLB (the sub-driver adds to
the current eSPD on the MLB label); (b) the LB of d(A2 vs A0) is above 0 on L_MLB; (c) the LB of
d(A2 vs A0) is above 0 on L_UM ((b) and (c) are the gate 5.2 eTool rule for the rebuilt eSPD). A
deciding label that is not computable makes the verdict **NOT COMPUTABLE**. Otherwise **NOT PASS**,
or **NOT PASS; UNDERPOWERED** when the planted check (6.3) also fails, or **VOID** (6.2).

## 6. Comparators (the pass needs them)

6.1 **Zero comparator.** `ebr_milb` set to 0 on every row carrying it: A2 equals A1 and d(A2 vs A1)
must be exactly 0 on every label (a plumbing identity, printed).

6.2 **Null comparator.** `ebr_milb` permuted within board year among the rows carrying it, seed
20261025, through 4.1, 4.2 and 5. If the null passes (a), (b) and (c), or its incremental LB is above 0
on a deciding label, the read is **VOID** (a leak), never a pass.

6.3 **Planted recovery.** A synthetic candidate 0.25 x (z of the within-board-year rank of L_MLB + z of
the rank of L_UM, 0 for a missing label) + sqrt(1 - 0.125) x z(noise), seed 20261026, with the real
candidate's missingness, in place of `ebr_milb` through 4.1, 4.2 and 5. Recovered when it passes. A
read that does not pass and whose planted check fails is **NOT PASS; UNDERPOWERED**: not evidence of
no gain.

## 7. What follows the verdict

- **PASS:** eSPD is rebuilt with the sub-driver in the dark preview only (`etools.build_preview` on
  S = {`sb_rel`, `ebr_milb`}; the live candidate reads the MiLB eBR seasons through 2026), the
  amendment 2 F1 drift and re-centring read runs once for speed before any flip, and the flip goes to
  the owner as a question. eFV sees the eTool only through the re-weighting (`efv_etools_reweight`).
- **Anything else** (NOT PASS, UNDERPOWERED, VOID, NOT COMPUTABLE): speed keeps the consensus grade
  as now; nothing served moves.

## 8. The one read

`python etools_spd_ebr.py --run --amend-sha SHA` refuses unless SHA names a commit carrying this file
as REGISTERED; it asserts the board years, no candidate season at or after Y, no incomplete unit, no
L_UM season outside Y to 2024, no MLB-label row with a first MLB season after 2024 and no FV-keyed
grouping; it reads every input's sha256 at start and end. `--check` counts (presence only); `--dry-run`
runs the reporting path on fixtures.

**Computability first.** The runner counts 3.4 and 3.5 before any statistic. If a deciding label
(L_MLB or L_UM) is not computable, it computes no statistic, writes
`data/_labs/etools/etools_spd_ebr_reads.json` with the counts, the projected MDE and the verdict NOT
COMPUTABLE, and **the read is not spent**: the same command runs the same registered read when the
record covers the as-of seasons, with no change to this document. Otherwise the read begins at the
first statistic that pairs a grade or candidate with a label; it runs once and the artifact carries a
spent marker. On an exception after that point: no rerun, the read is recorded as spent, and the
question goes to the owner. Never `backtest.run_backtest`, `run_monthly` or `build_site` from the
runner; no network request.

## 9. Results

(Empty at registration. Results go to this section as a dated note and to
`docs/tools-2026-10/ETOOLS_RESULTS.md`.)

### 2026-10-21: THE READ, NOT COMPUTABLE (not spent; OWNER-WAIVED EARLY READ, EW3-5)

`python etools_spd_ebr.py --run --amend-sha 3cc6a8e6` (code at 42afeb29) counted section 3.4 and
3.5 and stopped before any statistic, as section 8 requires: no grade or candidate was paired with
a label value, and `data/_labs/etools/etools_spd_ebr_reads.json` records `"spent": false`,
`"statistics_computed": 0` and every input's sha256 (equal at start and end).

The frame is board year 2024 alone: the MiLB eBR record's complete units are Rookie and Single-A
2023 to 2025, and only 2023 lies inside a development board year's as-of window. 571 speed rows
(571 players); 191 carry the candidate (487 carry sb_rel).

| label | rows with the candidate and the label (players) | board years with 20 or more | needs | status |
|---|---|---|---|---|
| L_MLB, sprint speed (deciding) | 3 (3) | 0 | 100 players, 3 board years | NOT COMPUTABLE |
| L_UM, SB per PA over the level-season mean (deciding) | 17 (17) | 0 | same | NOT COMPUTABLE |
| L_BSR, BsR per 600 PA (reported) | 3 (3) | 0 | same | NOT COMPUTABLE |

Censoring: of the 191 candidate rows, 188 have no MLB line by 2024 (censored for L_MLB and L_BSR)
and 174 carry no upper-minors line of 300 PA in 2024 (censored for L_UM; 2024 is the only label
season the cap allows for board year 2024). Projected minimum detectable effect (section 4.3, the
look's eSPD sd scaled by players): 0.194 on L_MLB (3 players) and 0.094 on L_UM (17 players),
against the look's whole eSPD gain over consensus of +0.007 on L_MLB.

**Verdict: NOT COMPUTABLE.** Speed keeps the consensus grade; nothing served moves. The read stays
registered and unspent: the same command runs it, unchanged, once the minor-league partition of the
runner record holds the as-of seasons (2021 and 2022 at every level, and High-A to Triple-A from 2021
to 2023, for board years 2022 to 2024). That backfill is a separate task and an owner call.

### 2026-10-22: THE READ, NOT PASS; UNDERPOWERED (spent; OWNER-WAIVED EARLY READ, EW3-5)

After the backfill of owner answer ETOOLS-SPD-EBR (2026-10-21; `docs/ebr-2026-09-30/EBR_MILB.md`, dated note
of 2026-10-22: the record now holds 2021 and 2022 at every level and 2023 at High-A to Triple-A),
`python etools_spd_ebr.py --run --amend-sha 3cc6a8e6` ran once, unchanged, on 2026-10-22 at 20:32 local
(2026-10-23 00:32 UTC), as task ETOOLS_SPD_MILB_EBR_BACKFILL. The fixture dry run and the presence counts
(`--check`) ran first; stdout and stderr were kept. `data/_labs/etools/etools_spd_ebr_reads.json` carries the
spent marker; every input's sha256 is equal at start and end.

Frame: board years 2022, 2023 and 2024 (complete as-of seasons 2021 to 2023). 1,716 speed rows; 1,275 carry
both the candidate and sb_rel (Spearman 0.35 between them). Units read: every complete level-season, AA 2021
included (it is withheld from the cards for a GIDP identity miss, which section 2.1 does not condition on);
Rookie 2022's reliability is 0.055, above the 0.05 floor.

| label | rows (players) | board years with 20 or more | status |
|---|---|---|---|
| L_MLB, sprint speed (deciding) | 347 (226) | 3 | computable |
| L_UM, SB per PA over the level-season mean (deciding) | 724 (479) | 3 | computable |
| L_BSR, BsR per 600 PA (reported) | 231 (158) | 3 | computable |

| comparison | L_MLB d (LB, MDE) | L_UM d (LB, MDE) | L_BSR d (LB) |
|---|---|---|---|
| A2 vs A1 (the sub-driver over the current eSPD) | -0.0058 (-0.0133, 0.0106) | +0.0006 (-0.0030, 0.0054) | -0.0109 (-0.0205) |
| A2 vs A0 (rebuilt eSPD over consensus) | +0.0106 (-0.0048, 0.0232) | +0.0631 (+0.0508, 0.0191) | -0.0093 (-0.0357) |
| A1 vs A0 (current eSPD over consensus, this frame) | +0.0165 (+0.0019, 0.0229) | +0.0625 (+0.0504, 0.0184) | +0.0016 (-0.0228) |

Incremental test of `ebr_milb` over the consensus grade: L_MLB d +0.0098 (LB -0.0056, p 0.146), L_UM +0.0045
(LB -0.0074, p 0.261), L_BSR +0.0300 (LB -0.0009, p 0.053, reported). Gate 4.4 admission (reported, deciding
nothing): sb_rel admitted (L_UM, q 0.000), ebr_milb not.

Comparators: zero comparator exact (A2 minus A1 0.0 on every row; d 0.0 on every label). Null comparator
(permuted within board year): (a) false, (b) true, (c) true, so it does not pass; its incremental LB is
-0.0088 on L_MLB and -0.0068 on L_UM: **not VOID**. Planted recovery: (a) false (d -0.0026, LB -0.0071),
(b) false (LB -0.0018), (c) true: **not recovered**.

Rule (section 5): (a) false, (b) false, (c) true. **Verdict: NOT PASS; UNDERPOWERED** (the planted check
fails, so this is not evidence of no gain). Speed keeps the consensus grade; eSPD is not rebuilt; nothing
served moves from this read; no flip question. Reported beside it and deciding nothing: on this smaller frame
the current eSPD (A1) clears consensus on L_MLB (LB +0.0019), which it did not on the look's whole frame
(+0.007, LB -0.001).
