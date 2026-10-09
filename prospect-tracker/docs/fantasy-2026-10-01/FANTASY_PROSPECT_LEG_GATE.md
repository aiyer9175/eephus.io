# Fantasy Rank prospect leg gate: FANTASY_PROSPECT_LEG_GATE (registered 2026-10-08)

Registration status: REGISTERED

Covers one test, ordered by the owner on 2026-10-01 (M21FR-1, answer (b), recorded in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under "ANSWERED 2026-10-01 (AskUserQuestion), the
overnight writers' questions, batch 2"), verbatim: "Gate a grade-blended prospect leg:
register a pass/fail test for a leg that blends the eFV or consensus grade into the
translated lines, served only if it beats consensus on a fresh frame."

The context is commit `1e88c7bd` (M21_FANTASY_POOL_COMBINED_RANK, 2026-10-01), which built
the Fantasy Rank tab on /fantasy/ Dynasty: 631 MLB players and prospects ranked together on
projected fantasy production (`fantasy_rank.py`, served `data/fantasy_rank.json`). Its
prospect leg is a line built from minor league rates translated to MLB rates, with the
playing time past debut classes got, weighted by the ETA model's arrival odds. On its own
backtest (`python fantasy_rank.py --backtest`, `data/fantasy_rank_eval.json`, list vintages
2018 and 2019) that prospect order scored Spearman 0.2162 against 0.3085 for the consensus
FV order on realized fantasy value (difference -0.0923, player-clustered 95% interval
-0.1476 to -0.0378, 1,982 player-vintages, 1,329 players), and the tab prints that loss.

Producer, built AFTER this commit on fixtures only: `tools/fantasy_prospect_leg_gate.py`,
pinned by `test_fantasy_prospect_leg_gate.py`. Artifact, written ONLY by the one look:
`data/fantasy_prospect_leg_gate_eval.json`. Registry row: `fantasy_prospect_leg_blend`
(verdict `unvalidated`, `registration_status` "registered, not read", no eval artifact;
the registry's verdict enum has no word for registered).

This document is committed ALONE, before any number of the test is computed. Sections 0 to
14 are frozen at this commit. Section 15 is EMPTY and is filled only with the look's
verbatim output. No statistic here, in the lab or in its artifact is cut by consensus-FV
cell (`docs/PROSPECT_ANCHOR_GATE.md`), and no realized-WAR quantity is computed anywhere in
it. Nothing served moves at this commit or at the look; a pass makes an arm eligible, and
serving it is a separate task (section 13).

---

## 0. What was already seen

- **The spent backtest** (`1e88c7bd`, `data/fantasy_rank_eval.json`): the readings quoted
  above, per vintage 2018 0.2417 against 0.3043 (n 880) and 2019 0.2001 against 0.3193
  (n 1,102). It read the 2018 and 2019 classes' realized FanGraphs Points over 2018 to 2023,
  the realized replacement of season 2017, and the debut events of the 2018, 2019, 2022 and
  2023 list vintages (its Kaplan-Meier arrival curves, `fantasy_rank.KM_TRAIN_VINTAGES`).
- **Input availability, read for this registration on 2026-10-08, no outcome.**
  (a) Debuted rows of the eFV matrices that carry a MiLB block, by debut year: hitters 0 for
  every debut year 2011 to 2014 and 62 of 63 for 2015; pitchers 0 for 2011 to 2014 and 69
  of 72 for 2015 (`data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`, rows of
  kind `debuted`; the matrices read MiLB from `efv_dataset.MILB_FLOOR_DEFAULT` 2014).
  (b) Players holding a snapshot FV in the `snapshots` table by calendar year, before any
  pre-debut filter: 2015 894 (one source), 2016 896 (one source), 2017 970 (two sources),
  2018 1,325 (two), 2019 1,532 (two). No grade value, eFV, fantasy value, debut, playing
  time or realized quantity was read for any class.
- **Code facts read** (they shape section 4, and none is a measurement):
  F1. The incumbent is not grade-free in its arrival timing. `eta.estimate_eta` adds an
  FV adjustment of up to 0.75 years (`eta.py:664-676`); the live board passes the latest
  consensus FV (`storage.py:11395`) and `eta_backtest.build_cohort` passes the vintage FV
  (`eta_backtest.py:281`). The served copy "No WAR and no grade enters the rank"
  (`fantasy_rank.py`, the payload's `basis`) is therefore not exact; that copy is a separate
  repair and is not changed here.
  F2. The spent backtest read each prospect's MiLB block through the RECORD id
  (`fantasy_rank._mlbam_resolver`: matrix, `debuts.json` and `player_photos` ids), and
  `eta_backtest.build_cohort` reads the level and season line through `debuts.json` ids
  (`_vintage_inputs_statsapi`). Records gain ids mostly on reaching the majors, so an input
  keyed on them is a debut proxy (bug B4, `efv_identity`, DS-03). It touches the leg and not
  the consensus order.
  F3. `college_translation._fit2` is the house bivariate form of the translation template
  (both slopes shrunk by n / (n + SLOPE_SHRINK_K)).
  F4. `efv_v2_model.lv_scores(side, V, frame_rows)["v1"]` returns the served eFV v1 blend
  score for a list-vintage frame, fitted on matrix rows with decision year before V and
  excluding every player in the frame; `efv_v2_model.v1_fold_scorer(train, side)` is its
  per-fold scorer.

## 1. Preconditions

| id | precondition | state at registration |
|---|---|---|
| Z | the fWAR label epoch's step Z entry (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9) | RECORDED 2026-10-03 |
| L | `tools/fantasy_prospect_leg_gate.py` and `test_fantasy_prospect_leg_gate.py` committed, built and tested on fixtures only, before the look | NOT BUILT |
| G | `efv_vintage_frame.RESERVED_LV = {2020, 2021}` and `reserved_vm_pins()` empty at the look's HEAD | HOLDS at registration |
| C | every cache the look reads is on disk (section 9, feasibility block); the look never fetches | checked by the look |
| D | the look's date is admissible (section 10) | checked by the look |

## 2. The question

Does a prospect leg that blends a grade into the translated lines rank a prospect class by
the fantasy value it went on to produce better than the consensus FV order does, on classes
no earlier test has read?

## 3. The frame

**Fresh classes: list vintages 2016 and 2017.** Every other class is spent, reserved or
unusable:

| list vintages | state | why |
|---|---|---|
| 2018, 2019 | SPENT | scored by `1e88c7bd` (`data/fantasy_rank_eval.json` `frame.list_vintages` [2018, 2019]) |
| 2022, 2023 | SPENT | their debut events through 2024 trained the spent backtest's arrival curves (`KM_TRAIN_VINTAGES`) |
| 2020, 2021 | RESERVED | eFV R-LV (`efv_vintage_frame.RESERVED_LV`); never read here |
| 2024 and later | UNUSABLE | the five-season window has not happened, and every debut from 2025 on is the reserved R-VM cohort |
| 2011 to 2015 | UNUSABLE | no translation input: the matrices carry no MiLB block before the 2015 debuts (section 0) and a V of 2015 or earlier has at most one MiLB season at the default floor (`efv_v2_model.lv_model_row`'s unavailable rule) |

This look spends 2016 and 2017. No fresh class remains after it, so a later gate on this
question needs a frame that does not exist today (the 2024 class's window closes after the
2028 season, and its post-2024 debuts stay R-VM until the eFV looks release them).

**Unit.** One row per (player, list vintage Y), Y in {2016, 2017}: `eta_backtest`'s vintage
cohort for those years (`eta_backtest.VINTAGE_YEARS` overridden to (2016, 2017), as
`fantasy_rank._eta_cohort` does): a player with an FV snapshot in year Y who had not debuted
before that snapshot; FV = the median of each source's earliest same-year snapshot.

**Drops, applied before any score is computed, counted and printed:**
- a row whose player debuted in 2025 or later (R-VM; also removed from every frame passed to
  an eFV scorer, so no eFV is computed for him);
- a row with no record id to join realized value through (`fantasy_rank._mlbam_resolver`),
  as in the spent backtest;
- for arms that need it, a row with no eFV score (section 9 says when this drops the row for
  every order and when it voids arm A instead).

**Outcome.** As the spent backtest defined it: per realized season s = Y .. Y+4 (2016 to
2020, 2017 to 2021), FanGraphs Points of the realized line (corpus components through the
projection algebra; SB from the cached StatsAPI MLB rows; a pitcher's hits allowed at the
league BABIP, no saves or holds) minus that season's realized replacement (145th hitter,
121st pitcher), floored at zero, discounted 7% a season, summed over both sides. Every
window ends by 2021.

**Disclosures.** (1) A class hold-out, not a player hold-out: a player listed in 2016 or
2017 and again in 2018 or 2019 had his later row scored by `1e88c7bd`, and realized seasons
2017 to 2021 were read there for other rows. (2) Both windows hold the 60-game 2020 season;
replacement is per season, so it scales with it, as it did in the spent windows. (3) The
2016 consensus is one source's grade (section 0 (b)).

## 4. Shared inputs: one protocol for every order

Every leg (I, A, B) reads the same inputs, so the legs differ only where section 6 says.
The protocol departs from `1e88c7bd`'s in three named places (P1, P4, P5); each departure
is forced by the fresh frame or removes a debut proxy, and none is tuned on any reading.

- **P1. Translation and playing-time fits on a spent fit frame.** Forward-chained fits
  (debuts through Y-2) are empty for Y = 2016 and thin for 2017 (section 0 (a)). Every leg
  therefore fits its translation on `fantasy_rank.translation_pairs(corpus, 2023)` and its
  playing time on `fantasy_rank.pt_curves(corpus, 2024)`, each with every player listed in
  a fresh class removed (an exclusion argument the lab adds; the served call is unchanged).
  The fit frame is the 2015 to 2023 debuts with a MiLB block (targets through 2024) for
  translation and the matrices' debuted rows through the 2024 debuts for playing time.
- **P2. Aging curves, forward-chained as served:** `fa_projection.fitted_models(corpus, Y-1)`.
- **P3. Replacement for the leg's value:** season Y-1's realized replacement held flat, as
  served.
- **P4. MiLB inputs through the outcome-blind id (repairs F2).** The block is
  `efv_dataset._milb_features(person, Y, birth_date, side, cutoff=listing date,
  first_season_floor=efv_dataset.MILB_FLOOR_DEFAULT)`, where `person` is the id
  `efv_identity.resolve_record` gives the record at vintage Y (the F-LV rule). A row whose
  person does not resolve reads no block and lands on the fit's mean line, as served. The
  record id joins the outcome only.
- **P5. Level and ETA through the outcome-blind id (repairs F2).** Level = the block's
  `milb_level` (`fantasy_rank.level_key`); where none resolves, the career_stats level
  through Y-1 (`eta_backtest._highest_level_through`), for every row alike. ETA year =
  `eta.estimate_eta(current_level, age at the listing, is_pitcher, vintage FV, the season
  Y-1 line at that level, snapshot_date=listing date)` re-anchored to Y as
  `eta_backtest.build_cohort` does. The vintage FV stays in this call for every leg (F1),
  so the ETA's grade adjustment is common to I, A and B.
- **P6. Arrival:** zero before the ETA year, then 1 - S(t) on Kaplan-Meier curves by level
  fit on the spent list vintages 2018, 2019, 2022 and 2023 with every fresh-class player
  removed, levels read by P5's rule, debuts after 2024 censored at 2024, a level used only
  with 40 or more rows (`fantasy_rank.km_curve`, the spent backtest's estimator).

**Known leaks (disclosed, common to I, A and B, absent from the consensus order):** the
translation, playing-time and arrival fits read seasons after Y (later debut cohorts, later
list vintages); none reads a fresh-class player's own outcome. They can only flatter a leg
against the consensus order, which makes a pass harder to earn honestly and a fail more
credible.

## 5. The incumbent I: the stats-only leg as served

`fantasy_rank`'s prospect leg at HEAD, on the inputs of section 4: translated components by
`translate()` (univariate `college_translation._fit` per target), playing time from the 20
equal-mass bins, arrival from P6, value `total_value([expected_above(line, "fgp", side,
None, repl) * p_t])` over the horizon of 5 seasons at 7%. I is REPORTED beside the arms
(I minus C, and each arm minus I) and is not gated: the pass bar is the consensus order.

## 6. The candidates A and B: grade-blended lines

One candidate per grade. Each keeps I's arrival (P6), aging (P2), replacement (P3), horizon,
discount and value formula, and changes the line given arrival in two places, with the grade
g as one continuous centred covariate. g is never binned, never tabulated by FV cell and
never enters as a per-grade mean.

**Grades.**

| arm | g on a fresh-class row | g on a fit-frame row |
|---|---|---|
| A, eFV | the served eFV v1 blend score: `efv_v2_model.lv_scores(side, Y, rows)["v1"]`, `rows` = `efv_vintage_frame.build_frame(side, Y)` with the module's defaults at the look's HEAD, minus the R-VM drops | `efv_v2_model.v1_fold_scorer` fit on matrix rows with decision year before the row's decision year and with every fresh-class player removed, applied to the row |
| B, consensus FV | the vintage FV the row carries (the comparator's own number) | the matrix row's `consensus_fv_raw` (its last read before the debut) |

**Change 1, rates.** For each translation target (hitters k, bb, iso, hr, babip, sb;
pitchers k, bb, hr) the univariate fit is replaced by `college_translation._fit2` on
(x = the MiLB feature I reads, g, y = the first-two-season rate per 100) over the fit-frame
pairs that carry g, and the component is `max(0, _predict2(fit, x, g)) / 100`, x missing
reading the fit's x mean. A target whose `_fit2` returns None keeps I's fit for that arm
(printed).

**Change 2, playing time.** For each group (hit, sp, rp) and season k from the ETA year, the
slope `b_k = OLS slope of season-k MLB PA (IP for pitchers) on g` over the fit-frame
playing-time rows that carry g, shrunk by n / (n + SLOPE_SHRINK_K) as the translation is;
each of I's 20 bins becomes `max(0, bin + b_k * (g - gbar_k))`, gbar_k the mean g of those
rows. A k with no observed season carries the last observed slope forward, as `pt_curves`
carries its bins.

Arrival is not blended: the owner's words name the translated lines. Whether to add an arm
that blends the grade into arrival is an open owner question at registration; only an
amendment committed before the look can add one (section 10).

## 7. The comparator C: the consensus FV order

The vintage FV of each row, ranked, average ranks for ties, on the same rows as every leg.

## 8. The statistic

The spent backtest's own: pooled Spearman rank correlation (`fantasy_rank._spearman`,
average ranks for ties) of an order with the realized outcome of section 3, over the rows of
both classes together, plus each class alone. For arm j in {A, B}:
`D_j = rho(arm j) - rho(C)` on identical rows.

Uncertainty: a player-clustered bootstrap (resample players with replacement, every row of
a drawn player kept), B = 2000, seed 20261008, the SAME draws for every order, fits held
fixed (they are not refit per draw; disclosed). p_j = (1 + #{draws with D*_j <= 0}) /
(B + 1), one-sided. A lower bound at level q is the sorted draws' entry at index
int(q x number of draws), as `fantasy_rank._bootstrap` indexes.

## 9. Feasibility, then the pass rule

**Feasibility block, outcome-blind, printed before any realized value is joined.** Row
counts by class and side after each drop; caches present (MiLB ladders 2014 to 2022 at the
default floor, StatsAPI MLB hitting rows 2015 to 2024, the projection corpus); `lv_scores` status
for each (side, class) cell; fit-frame pair and playing-time row counts per target and
group for I, A and B; Kaplan-Meier levels used. A missing cache STOPS the look here (section
11). If any (side, class) cell of `lv_scores` is not `ok`, arm A is VOID, B is read alone on
the frame that does not need an eFV score, and the Holm family is m = 1. Otherwise every
order is read on the rows that carry an eFV score, and m = 2.

**Pass rule (Holm across the arms, one-sided alpha 0.05).** Order the arms by p_j. The
first is tested at 0.05 / m and, if it clears, the second at 0.05. Arm j PASSES only if:
1. p_j clears its Holm level, AND its lower bound at that level (q = 0.05 / m for the first
   arm, 0.05 for the second) is above zero: the resolvable margin, both required, and
2. D_j is above zero pooled and in each class alone (a sign veto; it does not enlarge the
   family).

**Outcomes.** PASS: at least one arm passes; if both pass, the one with the larger pooled
D_j is eligible (a tie goes to A). FAIL: the look completed and no arm passes. VOID: the
look could not complete (section 11), or fewer than 1,000 rows remain pooled, or a class
holds none. The look prints I's own reading (rho(I) - rho(C), its interval) and each
D_j - (rho(I) - rho(C)) as context, adjudicating nothing.

The honest prior is FAIL. The spent interval ran from -0.1476 to -0.0378 at about the fresh
frame's size, so a pass needs a candidate to lead the consensus order by roughly half that
interval's width or more, and a blend with the grade must carry information the grade
itself does not.

## 10. One look and its date

- ONE look, run once by `python tools/fantasy_prospect_leg_gate.py --look`, never before
  2026-10-17 (step Z 2026-10-03 plus 14 days), and never on a registered look day: on the
  registration date these include 2026-10-18, 2026-10-23, 2026-11-02, 2026-11-06,
  2026-11-09, 2026-11-13, 2026-11-17, 2026-11-20 and 2026-12-01; the look re-reads
  docs/*GATE*.md at its HEAD and refuses a date any of them names as a look.
- No partial look: the lab computes no realized value, no rho and no difference before the
  look, on any class, the spent ones included, and its tests run on fixtures only.
- Amendments: before the look, an amendment committed to this document may add arms (the
  family grows with them) or fix a defect in section 4's code; it must say it was made
  before any fresh-class reading. After the look nothing above section 15 changes.
- The look writes `data/fantasy_prospect_leg_gate_eval.json` (frame, accounting,
  feasibility block, per-class and pooled rho for I, A, B and C, D_j, p_j, Holm levels,
  lower bounds, verdict, HEAD sha) and pastes its printed output into section 15 verbatim.

## 11. Crash protocol

- **Stopped in the feasibility block** (a missing cache, a guard raising, an exception
  before any realized value is joined): nothing was read. Repair it in a commit that changes
  no frame, arm, statistic or rule above, name that commit in section 15, and run the look
  on a later admissible day.
- **Crash after a realized value was joined:** the printed output is the look. It is not
  rerun; section 15 records it, the verdict is VOID, and the served leg stays as it is.
- **Nondeterminism:** none is expected (seeded bootstrap, cache-only inputs). The lab draws
  the bootstrap twice in process from the same seed; if the two sets of draws differ, the
  verdict is VOID.

## 12. Bans

- No statistic by consensus-FV cell: no per-FV-grade bins, means, residuals, counts or
  strata anywhere in the lab, its tests or its artifact (`docs/PROSPECT_ANCHOR_GATE.md`).
- No realized-WAR quantity on any frame row; the outcome is fantasy points. The eFV score is
  a model input fitted on earlier cohorts' labels.
- Never `backtest.run_backtest`.
- Never a read of list vintages 2020 or 2021 (no `build_frame`, `lv_scores` or
  `eta_backtest` call with them) and never an eFV, consensus or source score of a player
  who debuted in 2025 or later.
- No network fetch during the look; no write to any served artifact (`data/fantasy.json`,
  `data/fantasy_rank.json`, `data/fantasy_rank_eval.json`, the board, the registry rows of
  other models).
- Never a sum of quantile points: every line is a mean projection and the bins are
  equal-mass bin means.
- Nothing here enters the eFV Source Comparison ledger or its progress chart, and no eFV
  claim is drawn from it.

## 13. What the tab and the registry say under each outcome

**Until the look, and under FAIL and VOID, the served leg stays stats-only** (`fantasy_rank`
as served) and the tab keeps printing its loss: the sentence `backtestNote` builds from
`data/fantasy_rank_eval.json` (the 2018 and 2019 classes, 0.22 against 0.31) is unchanged.

| outcome | Fantasy Rank tab | registry row `fantasy_prospect_leg_blend` |
|---|---|---|
| before the look | unchanged | unvalidated, "registered, not read" |
| FAIL | unchanged, plus one sentence derived from the gate artifact: neither grade-blended version beat the consensus FV order on the 2016 and 2017 classes, with each arm's difference and Holm-level lower bound | provisional, `measured_not_adopted`, eval artifact the gate's |
| VOID | unchanged | unvalidated, notes record the VOID and its cause |
| PASS | changes only through a separate serving task (FANTASY_PROSPECT_LEG_SERVE): the live leg takes the eligible arm (A reads the board's eFV v1 blend score, kept as `v1_rank_war` on a board that serves another eFV; B reads the board's consensus FV), its fits refit on the live fit frame by section 6's rules; the basis line names the grade it blends; the check sentence prints the gate's reading (arm minus consensus on the 2016 and 2017 classes) first and keeps the 2018 and 2019 stats-only loss as history | provisional, `shipped_partial_measurement` once served; `fantasy_combined_rank`'s champion text names the arm |

If at serving time the eligible arm's grade is no longer computed as tested (for example no
v1 blend score exists on the board), the pass lapses and the leg stays stats-only.

## 14. Read to write this

- `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, M21FR-1 and M21FR-2.
- The M21_FANTASY_POOL_COMBINED_RANK fix report (backtest, frame, the tab's copy) and commit
  `1e88c7bd`.
- `fantasy_rank.py` (module docstring; `translation_pairs`, `fit_translation`, `translate`,
  `pt_curves`, `arrival`, `km_curve`, `_spearman`, `_bootstrap`, `_eta_cohort`, `backtest`),
  `data/fantasy_rank_eval.json`, `assets/dynasty.js` (`backtestNote`, the rank board copy).
- `eta_backtest.py` (`VINTAGE_YEARS`, `build_cohort`), `eta.py` (`estimate_eta`, the FV
  adjustment), `storage.py:11395`.
- `college_translation.py` (`_fit`, `_fit2`, `_predict2`), `efv_dataset.py`
  (`_milb_features`, `MILB_FLOOR_DEFAULT`), `efv_identity.py` (`resolve_record`),
  `efv_vintage_frame.py` (`RESERVED_LV`, `R_VM_FIRST_DEBUT_YEAR`, `DEV_VINTAGES`,
  `build_frame`), `efv_v2_model.py` (`lv_model_row`, `lv_scores`, `v1_fold_scorer`),
  `efv_model.py` (`oos_grades`, `SCORED_YEARS`), `fa_projection.py` (`fitted_models`).
- `docs/efv-v2/PROGRAM.md` sections 2.2 and 2.4 (frames and reserved frames),
  `docs/PROSPECT_ANCHOR_GATE.md`, `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9
  (the step Z entry, 2026-10-03), `docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md` and the other
  docs/*GATE*.md dates, `docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md` (form).

## 15. Results

EMPTY AT REGISTRATION.
