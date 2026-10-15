# eTools amendment 2: flip prep (drift and re-centring, a promotion-independent label read, the BA weight and bootstrap ranking fixes)

Registration status: REGISTERED

Task ETOOLS_FLIP_PREP (owner asks EW3-15 and the eTools ask, 2026-10-15; queued in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under "eTools result"), written 2026-10-15 on lane
wt-ETOOLS_FLIP_PREP (base 0a3d3867). Docs only, committed alone before any number named here
is computed. It amends `docs/tools-2026-10/ETOOLS_GATE.md` (registered 3f240da6, look
dc271ac2) and follows amendment 1 (`ETOOLS_AMENDMENT_1.md`, 8f369ae2, reads bcbfb92a).

## 0. Why, and what was already seen

The results review (`ETOOLS_RESULTS.md`) lists three open items before any flip of `ETOOLS_ON`:

1. **Drift.** The dark preview's mean shift (eTool minus consensus tool grade) is +2.7 grade
   points for eFB and +1.3 for eHIT, against about zero on the development rows. **Seen before
   this document**: those two figures and the preview's spread figures in the results doc.
2. **Promotion.** L_UM needs 300 Double-A or Triple-A PA (150 BF), so it is accuracy among
   promoted players; 24% (fastball, command) to 47% (pitch selection, bat control) of each
   frame is on neither label (amendment 1, A1). **Seen**: every A1 figure.
3. **Two code notes.** (a) The weighting arm AW1 averages Baseball America's grade with an
   implicit weight: `weighted_grade` reads `w.get(s, 1.0)`, and the weights are derived over
   FanGraphs and MLB Pipeline only, so every BA grade enters at 1.0 without being measured.
   (b) `within_rho` on bootstrap draws keeps the full-sample ranks fixed and takes a weighted
   Pearson of them, so a draw is not the Spearman of the resampled set.

**Counted by this lane before writing (no statistic, no label value read):** BA tool grades
exist on development board years 2023 and 2024 only: 750 of 4,438 hit frame rows, 557 carrying
all three outlets, 38 carrying BA alone, 155 BA and one other; fastball 626 of 4,302 (473 all
three); pitch selection, bat control and raw power carry no BA grade. Nothing else was computed.

## F1. Drift check and re-centring

F1.1 **Tools.** The six PASS eTools of the look (hit, game_pwr, pitch_sel, bat_ctrl, fb, cmd),
each with the look's admitted set and the look's `final_fit` (lines a_j + b_j G_c, weights c,
sigma) unchanged.

F1.2 **The live cohort.** The preview's rows: `build_preview`'s universe (each source's latest
snapshot dated on or after 2026-01-01, candidates read through season 2026). Per tool, over
the cohort rows carrying G_c:
- shift s = mean of (eTool - G_c), eTool clamped to [20, 80] as served;
- per admitted sub-driver j: m_j = mean of u_j over rows carrying j (u_j = z_j - a_j - b_j G_c),
  its coverage, and its share of the shift, c_j x (sum of u_j over all rows, 0 where missing) / n.

F1.3 **The development reference.** Per development board year Y, the same statistics from the
out-of-fold construction (`etool_oof` with the look's set; the lines and c of the fold that
scores Y): s_Y and m_j,Y. The reference is the 12 values (one per board year).

F1.4 **Drift rule.** A tool is DRIFTED when s lies outside [min_Y s_Y, max_Y s_Y]; a sub-driver
is DRIFTED when m_j lies outside [min_Y m_j,Y, max_Y m_j,Y]. Reported with
z = (s - mean_Y s_Y) / sd_Y s_Y. Descriptive: a flag changes no verdict.

F1.5 **Re-centring.** For a scoring cohort C (one development test board year out of fold; the
live cohort for the preview), delta_j = (mean of u_j over C's rows carrying j) - (mean of u_j over
the fit's training rows carrying j). The re-centred eTool is
eTool_rc = clamp(G_c + sum_j c_j (u_j - delta_j), 20, 80), the sum over the sub-drivers the row
carries (a missing sub-driver still contributes 0). The band is unchanged (+/- 1.2816 sigma).

F1.6 **Re-centring read (once).** Out of fold on the development rows, eTool_rc (C = the test
board year) against G_c on both labels (gate 4.2 statistic with the F3.2 bootstrap), and
eTool_rc against the uncentred eTool (paired, same interval).

F1.7 **Serving rule.** The re-centred eTool is the construction the preview (and, after a flip,
`data/etools.json`) serves as `etool`, with the uncentred value kept as `etool_uncentred`, when
both hold on both labels: (a) eTool_rc against G_c has a one-sided 95% lower bound above 0;
(b) eTool_rc against the uncentred eTool has a one-sided 95% lower bound above -0.01 (the
tolerance is fixed here). Otherwise the uncentred eTool is served and its F1.4 drift is
disclosed beside it. Either way the preview carries both values and the drift report.

## F2. A promotion-independent label read

F2.1 **L_ANY, the translated line at any level.** Seasons Y to Y + 2 capped at 2024, Minor
League lines at ANY level (DSL, CPX, A, A+, AA, AAA), same construction as L_UM otherwise:
- hit: X1-translated K% negated; game_pwr: X1-translated ISO; fb: X1-translated pitcher K%;
  cmd: X1-translated pitcher BB% negated (league factor, park factor and environment scale as
  `um_tables`, pooled from counts); exposure floor 300 PA (150 BF);
- speed (reported, not a PASS tool): stolen bases per PA over the level-season mean at any
  level, 300 PA;
- pitch_sel and bat_ctrl: NOT COVERED. There is no chase or zone-contact measurement outside
  the tracked parks, and the pitch-event rates at other levels are these eTools' own
  sub-driver metrics; F2.3 covers them.

F2.2 **Statistic.** The look's out-of-fold eTool (`etool_oof`, the look's set) against G_c on
L_ANY (gate 5.2 statistic, gate 4.2 interval with the F3.2 bootstrap, gate 2.3 computable rule)
over (a) all rows carrying L_ANY and (b) the UNMEASURED rows: no debut by 2024 and no L_UM. Also
counted: rows carrying L_ANY, and the share of the unmeasured rows L_ANY covers.

F2.3 **The selection model (inverse probability weighting on L_UM).** For each of the six PASS
tools, a logistic regression of "L_UM present" on all frame rows (rows carrying G_c), with
[1, G_c, age_rel_level (missing: the frame mean and an indicator), the level cell at Y - 1 as
indicators (low, A+, AA, AAA; no line is the base), board year indicators, and each admitted
sub-driver's residual u_j against the final fit's line (missing: 0 and an indicator)], fit by
Newton iterations with an L2 penalty 1.0 on the non-intercept terms. Weight w = 1 / max(p, 0.05).
The statistic is the gate 5.2 d_E on L_UM with each row's bootstrap count multiplied by w (the
point estimate uses w alone): the promoted rows re-weighted to stand for the whole frame, under
selection on these covariates only (disclosed beside the number).

F2.4 **Rule.** Per PASS eTool: PROMOTION-CLEAR when every F2 read computable for it (L_ANY
pooled, L_ANY on the unmeasured rows, IPW on L_UM) has a one-sided 95% lower bound above 0;
otherwise PROMOTION-UNRESOLVED, naming the read. Descriptive: no verdict moves; the label goes
into the flip question.

## F3. The two fixes and their re-reads

F3.1 **BA weight.** `weighted_grade` takes an explicit weight for every outlet it averages and
raises on a missing one (no implicit default). The arm of record, AW1: FanGraphs and MLB
Pipeline keep their registered two-outlet weights (gate 6.1); Baseball America's weight is
derived by the same estimator (`ba_tool_grade_lab.derive_weights`, k 150, clamp 0.6 to 1.5, its
own under-60-row rule of all weights 1.0) over the three outlets on the fold's training rows
carrying all three, by position group with the gate 6.1 pooled fallback (under 100 players),
and its three-outlet BA value is the weight used. AW2 uses the same BA weight beside its own
(FanGraphs, MLB Pipeline, stat) weights. Sensitivity, reported and not of record: AW1-B, BA
excluded (FanGraphs and MLB Pipeline only; a row carrying neither takes G_c).

F3.2 **Bootstrap ranking.** On a bootstrap draw, `within_rho` ranks each board year's values on
the drawn sample: a row's rank is (the drawn count of values below it) + (the drawn count of its
own value + 1) / 2, so each draw's statistic is exactly the Spearman of the resampled set
(ties at mid-rank). The point estimate (no draws) is unchanged.

F3.3 **Re-reads (once).** With both fixes: AW1, AW1-B and AW2 on all 13 tools (gate 6.3 rule:
BEATS CONSENSUS when the lower bound is above 0 on both labels), and the eTool d_E intervals of
the 8 evaluated tools re-derived with the F3.2 bootstrap. Before any interval the runner
reproduces each look d_E to 5e-5 or stops. A PASS whose re-derived lower bound is not above 0
on a label is recorded FRAGILE UNDER RE-RANKING and named in the flip question; the look's
verdict stands as recorded.

## F4. The dark display (built, no read, no flip)

`ETOOLS_ON` stays False. The builder writes `.cache/etools/preview.json`; with the flag on it
writes `data/etools.json`. Each PASS eTool row carries the eTool (F1.7 construction), its 80%
band, the uncentred value, and each sub-driver's contribution c_j (u_j - delta_j) in grade
points under a plain label. The PROSPX card shows them beside the consensus tool grade only when
the card flag is on (default off, matched to `ETOOLS_ON` by a test). The Library's eTools view
reads `data/etools_eval.json`, a summary derived by `python etools.py --library` from the lab
artifacts (no number computed there). Glossary entries per eTool; registry rows, provisional.

## F5. Output and guards

`python etools.py --flip-prep --amend-sha SHA` runs F1.3 to F1.6, F2 and F3.3 once and writes
`data/_labs/etools/etools_flip_prep_reads.json` (spent marker, this document's commit, the
inputs' sha256 at start and end); it refuses unless SHA names a commit carrying this file as
REGISTERED, and asserts no board year 2020 or 2021, no L_ANY season after 2024 and no FV-keyed
grouping. B 2000, seed 20261023. Never `backtest.run_backtest`, `run_monthly` or `build_site`
from the runner; nothing served moves; no FV cell, mean or residual by consensus FV
(`docs/PROSPECT_ANCHOR_GATE.md`).
