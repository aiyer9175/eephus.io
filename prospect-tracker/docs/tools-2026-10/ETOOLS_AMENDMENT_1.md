# eTools amendment 1: the review reads (promotion selection, sub-driver margins, the Part P re-run)

Registration status: REGISTERED

Task ETOOLS review fix, written 2026-10-15 on the eTools lane after the one look of
`docs/tools-2026-10/ETOOLS_GATE.md` (registered 3f240da6, look recorded dc271ac2). Docs only,
committed alone before any number named here is computed by this lane.

## 0. Why, and what was already seen

The review of the look (2026-10-15) found three defects:

- **R1, promotion selection in L_UM.** L_UM needs 300 translated Double-A or Triple-A PA (150 BF
  for pitchers) in seasons Y to Y + 2. Reaching that is itself an outcome (promotion). The
  reviewer counted the 4,550 hitter rows: L_UM present and debut by 2024, 1,900; present and no
  debut, 828; absent and no debut, 1,399; absent and debut, 423. The results doc said L_UM covers
  debuts and non-debuts alike without saying that non-debuts who stalled below Double-A are on
  neither label.
- **R2, sub-driver margins.** Gate 4.4 admits a candidate on its gain over the consensus grade
  ALONE plus a pairwise |r| cap; it never asks what the candidate adds alongside the others. The
  reviewer re-ran three eTools without one sub-driver each, outside any registration, and reported:
  P/PA PAR in eHIT d -0.0004 (LB -0.0029) on L_MLB and -0.0003 (LB -0.0016) on L_UM; P/BF in eFB
  +0.0041 (LB -0.0021) and +0.0065 (LB +0.0023); P/BF PAR in eCMD +0.0024 (LB 0.0000) and +0.0020
  (LB +0.0005). **Those figures were seen before this amendment was written.** The read in A2
  is therefore a registered reproduction of a seen number, not a blind test, and says so.
- **R3, test coverage.** The tests did not exercise admission, the eTool fit, the flag routing or
  the pitch-rate construction.

Writing the R3 tests surfaced a construction defect, **R4**: `etools.pitch_rate_lines` read a
pitcher's exposure (BF) off the majority-role line even on the season-line fallback basis, where
`pitch_rates.player_lines` computes the rate off the season line. Counted (no statistic): 381 of
47,983 pitcher lines, all Complex League 2024, 79 of them crossing the 100 BF floor. The look's
tool candidates read seasons through 2023 only, and recomputing every pitcher candidate in the
look's frame under the fix changes no value (0 of 4,348 pitcher rows). Part P.3 reads lines
through 2025: the fix changes the par shrink at seasons 2024 and 2025 and the presence of the 79
lines.

## A1. Promotion selection, disclosed (counts, then one descriptive read)

A1.1 Counts beside every L_UM number: per tool with an L_UM, the frame rows (rows carrying G_c)
split four ways by L_UM present or absent and debut by 2024 (first MLB season 2024 or earlier)
or not.

A1.2 **The non-debut read.** For each tool whose eTool was evaluated at the look (admitted set
non-empty and an L_UM exists: hit, game_pwr, raw_pwr, speed, pitch_sel, bat_ctrl, fb, cmd): the
look's out-of-fold eTool predictions (`etool_oof` with the look's admitted set, unchanged), and
d_E = rho_w(eTool) - rho_w(G_c) on L_UM over (a) the rows with no debut by 2024 and (b) the rows
with a debut by 2024. Statistic, interval and computable rule exactly as gate 5.2 and 4.2
(player-clustered bootstrap B 2000, seed 20261023, one-sided 95% lower bound). Before the split,
the runner reproduces the look's pooled L_UM d_E for each tool to 4 decimals or stops.

A1.3 **Rule.** Descriptive: no verdict changes. A PASS tool whose non-debut lower bound is not
above 0 (or whose non-debut pool is not computable) is labeled **PROMOTION-DEPENDENT** in the
results and in the EFV_X3 hand-off; that label must be resolved before any flip of `ETOOLS_ON`.

A1.4 Not done here, named for the follow-up: a promotion-free label for the rows L_UM drops (for
example the K% at the player's next MiLB level, or reaching Double-A). It needs its own
registration.

## A2. What each admitted sub-driver adds given the others

A2.1 For each tool with two or more admitted sub-drivers (hit, game_pwr, fb, cmd), and each
sub-driver j in its admitted set S: the out-of-fold eTool on S and on S without j (gate 5.1
construction, same folds), and d_j = rho_w(eTool_S) - rho_w(eTool_S-j) over the rows carrying
the label and both predictions, on both labels; paired player-clustered bootstrap B 2000, seed
20261023; one-sided 95% lower bound. Also reported: rho_w(eTool_S-j) - rho_w(G_c) with its
lower bound (the reduced eTool against consensus).

A2.2 **Rule.** Descriptive: the look's admitted sets and verdicts do not change. A sub-driver
whose lower bound is not above 0 on BOTH labels is labeled **NO ADDED EFFECT** given the
others; the EW3-15 answer and the EFV_X3 hand-off are restated from A2, not from the gains over
consensus alone. Whether the X3 arm carries a NO ADDED EFFECT sub-driver is decided in X3's own
registration (recommended: drop it).

A2.3 **For any future version of the forward-selection rule** (an eTools v2), clause 4.4.3
gains a step: a candidate is admitted only if, added to the sub-drivers already chosen, the
out-of-fold eTool's d on its qualifying label has a one-sided 95% lower bound above 0. That
version needs its own registration and look; it is not applied here.

## A3. The Part P.3 re-run (code defect R4)

A3.1 Part P.3 (pitch rates as direct eFV drivers) is re-run once with the R4 fix, every other
constant as registered (gate Part P; B 2000, seed 20261023, BH within label, the flag rule). It
is disclosed in the results as **a registered read re-run because of a code defect**; the
look's original P.3 rows stay in `etools_atlas.json` and `etools_eval.json`, unchanged, and the
re-run goes to `data/_labs/etools/etools_review_reads.json`. The re-run replaces the original as
the P.3 answer whatever it shows.

A3.2 The tool-candidate reads (gate 3 to 6, Part P.2) are NOT re-run: R4 changes none of their
inputs (0 of 4,348 pitcher rows move). P.5 (grade revisions) reads the same unchanged
candidates and is not re-run.

## A4. Output

All of A1 to A3 go to `data/_labs/etools/etools_review_reads.json` (with the inputs' sha256 at
start and end and this document's commit), and to a section of
`docs/tools-2026-10/ETOOLS_RESULTS.md`. Never `backtest.run_backtest`, `run_monthly` or
`build_site`; nothing served moves (`ETOOLS_ON` stays False).
