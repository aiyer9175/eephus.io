# eFV label horizon at RESOLVED_THROUGH 2026: the counts, the views, the admission rule (EFV3_A9, 2026-10-02)

Owner ask (2026-10-02, verbatim): "On the eFV stuff - we are in the epoch now, the 2026 regular
season is over, so we should be able to use more recent seasons for calibrating eFV vs. prospect
WAR". The recorded answer (`DECISIONS_FOR_OWNER.md`, row EFV-2026-LABEL) is that this is already the
epoch's content: the label is first-six-season WAR, right-censored with the observed-rate tail and
weighted by the observed fraction, and the fWAR label epoch bundles the `RESOLVED_THROUGH` advance
from 2025 to 2026 (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 1 item 2, the F2 arm), so every
open cohort gains its 2026 season at step D+U and the V2 re-derivation at P5 refits on it. This
document quantifies what that advance adds, designs the first-three and first-four-season label
views as SECONDARY labels, and lists where eFV is calibrated against prospect WAR and when each
surface reads 2026.

Producer: `tools/efv_label_horizon_2026.py`, artifact `data/efv_label_horizon_2026.json` (tracked,
development, nothing served reads it), test `test_efv_label_horizon_2026.py`. Every count here is
copied from that artifact. The read is a pre-epoch read on the served ewar_v2 label
(`ewar_v2@2026-09-03T12:35:09`, `RESOLVED_THROUGH` 2025); the frozen fWAR vintage
`2026-10-02-0341299c20ec` (`data/fwar_vintage.json`, frozen at 7e34799f; E3's other parts, the
pitching loader, the `fwar` provider and `tools/rebase_career_war.py`, are at HEAD) is read for
label-to-label arithmetic on seasons 2014 to 2024 only; the task permits that read once E3 landed,
and the freeze commit's "nothing reads it until step D" is kept for LABEL reads, which this is not. No served number moves. No rater is scored
against anything here. No statistic is grouped by a consensus-FV cell.

## 0. The short answer

- The 2026 season adds no row to the scored pool and no row to either development frame of the V2
  gate (lv_dev's W3 labels closed at V 2020; vm_dev's rows are fixed). What it adds is OBSERVED
  SEASONS: hitters' pair-weight mass goes 619.988 to 684.155 (+64.167, +10.4 percent) on 782 scored
  rows, pitchers' 709.958 to 785.509 (+75.551, +10.6 percent) on 904. 73 hitter and 107 pitcher
  rows, the 2021 debut cohort, move from censored (weight 0.833) to fully observed (weight 1.0);
  they are counted here and never read, because their windows are R-LV's W3 seasons.
- The floor arithmetic on that mass: the one-sided model-vs-consensus mde95 of
  `data/xfv_mde_floor.json` rescales from 0.0446 to 0.0425 (hitters) and from 0.0425 to 0.0404
  (pitchers), about 0.002 a side. Both stay above the 0.02 margin the gate standard adjudicates at,
  so the advance alone resolves nothing new; it is arithmetic on a published sd, not a floor
  measurement (that is the epoch's step G).
- The 2025 debut cohort (243 debuts, 176 with an in-window consensus read, 219 with a career_war
  row) is admitted by `DEBUT_YEARS` at 2026 at the builder's weight 0.333, and it is R-VM:
  `reserved_vm_pins` keep it out of `SCORED_YEARS` and `CANDIDATE_YEARS` until the look record
  exists, so it is not in any number above.
- The shorter views resolve rows without projection: at 2026, first3 covers every cohort through
  2024 (313 hitter and 347 pitcher rows beyond L6), first4 every cohort through 2023 (222 and 228).
  On the development cohorts 2014 to 2019, where both are fully observed, first3 correlates with
  the six-season label at Spearman 0.8756 (hitters, n 334) and 0.8563 (pitchers, n 342) on ewar_v2,
  first4 at 0.9508 and 0.9256; the frozen fWAR reading is a few thousandths higher. The cost is the
  quantity: the industry FV frame is six-year value, and the first three seasons carry about 40
  percent of six-season WAR mass, the first four about 62 to 64 percent. Both views are registered
  here as SECONDARY labels, reported beside the primary and never replacing it before a reserved
  read.

## 1. The label builder's own terms, per debut cohort

Every term below is `efv_dataset._label_6yr` called with an empty seasons dict while
`RESOLVED_THROUGH` is set to the column's year for the call (`SERVICE_ALIGNED_WINDOW` off, the pinned
regime). The terms are a function of the calendar only, so no outcome is read to produce them. The
shipped matrices' stored `observed_seasons`, `weight` and `censored` equal the 2025 column row for
row on every censored row (pins: 0 weight mismatches, 0 observed-season mismatches, 0 flag
mismatches across 838 censored rows).

| debut cohort | observed seasons at 2025 | fraction and weight at 2025 | observed seasons at 2026 | fraction and weight at 2026 | moves at 2026 |
|---|---|---|---|---|---|
| 2014 to 2020 | 6 | 1.0, resolved | 6 | 1.0, resolved | none |
| 2021 | 5 | 0.833, censored | 6 | 1.0, resolved | censored to resolved |
| 2022 | 4 | 0.667, censored | 5 | 0.833, censored | one more observed season |
| 2023 | 3 | 0.5, censored | 4 | 0.667, censored | one more observed season |
| 2024 | 2 | 0.333, censored | 3 | 0.5, censored | one more observed season |
| 2025 | not admitted (`DEBUT_YEARS` stops at 2024) | | 2 | 0.333, censored | enters; R-VM, counts only |

The 2020 cohort is fully observed under both clocks and its rows are not reserved for the terms
(the terms read no value); its outcomes are treated as reserved here with 2021's, because the two
cohorts' windows are the W3 seasons of R-LV (list vintages 2020 and 2021).

## 2. Rows and weight mass, per cohort and side

Rows are debuted matrix rows (`data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`) by
debut year; every row in cohorts 2014 to 2024 carries a consensus grade and sits in
`efv_model.SCORED_YEARS`, so the scored pool is the whole set. A censored row's mass is the
builder's weight for the clock; a row the matrix resolved while the calendar says censored is a
terminal event (retirement, lifetime ban: 2 and 1 rows at 2021, 1 and 1 at 2023) and keeps 1.0
under both clocks.

| cohort | hit rows | hit mass 2025 | hit mass 2026 | delta | pit rows | pit mass 2025 | pit mass 2026 | delta |
|---|---|---|---|---|---|---|---|---|
| 2014 | 50 | 50.0 | 50.0 | 0 | 53 | 53.0 | 53.0 | 0 |
| 2015 | 63 | 63.0 | 63.0 | 0 | 72 | 72.0 | 72.0 | 0 |
| 2016 | 43 | 43.0 | 43.0 | 0 | 51 | 51.0 | 51.0 | 0 |
| 2017 | 52 | 52.0 | 52.0 | 0 | 32 | 32.0 | 32.0 | 0 |
| 2018 | 51 | 51.0 | 51.0 | 0 | 56 | 56.0 | 56.0 | 0 |
| 2019 | 75 | 75.0 | 75.0 | 0 | 78 | 78.0 | 78.0 | 0 |
| 2020 | 60 | 60.0 | 60.0 | 0 | 107 | 107.0 | 107.0 | 0 |
| 2021 | 75 | 62.809 | 75.0 | +12.191 | 108 | 90.131 | 108.0 | +17.869 |
| 2022 | 128 | 85.376 | 106.624 | +21.248 | 100 | 66.7 | 83.3 | +16.6 |
| 2023 | 94 | 47.5 | 63.031 | +15.531 | 128 | 64.5 | 85.709 | +21.209 |
| 2024 | 91 | 30.303 | 45.5 | +15.197 | 119 | 39.627 | 59.5 | +19.873 |
| total | 782 | 619.988 | 684.155 | +64.167 | 904 | 709.958 | 785.509 | +75.551 |

Censored rows: 385 hitter and 453 pitcher at 2025, 312 and 346 at 2026. The rows that move from
censored to fully observed are the 2021 cohort's 73 hitter and 107 pitcher rows (lane A's "+194"
counted debuts.json rows with a career_war row, 194 at 2021; the matrices hold the 183 of them with
an in-window consensus read, 180 censored and 3 terminal-resolved).

The forward-chained folds (`efv_model.SCORED_YEARS`, train on cohorts below the fold, test on the
fold) see the mass where it matters least for the early folds and most for the late ones:

| fold | hit train mass 2025 | hit train mass 2026 | hit test mass 2025 | hit test mass 2026 | pit train mass 2025 | pit train mass 2026 | pit test mass 2025 | pit test mass 2026 |
|---|---|---|---|---|---|---|---|---|
| 2014 to 2020 | unchanged | unchanged | unchanged | unchanged | unchanged | unchanged | unchanged | unchanged |
| 2021 | 394.0 | 394.0 | 62.809 | 75.0 | 449.0 | 449.0 | 90.131 | 108.0 |
| 2022 | 456.809 | 469.0 | 85.376 | 106.624 | 539.131 | 557.0 | 66.7 | 83.3 |
| 2023 | 542.185 | 575.624 | 47.5 | 63.031 | 605.831 | 640.3 | 64.5 | 85.709 |
| 2024 | 589.685 | 638.655 | 30.303 | 45.5 | 670.331 | 726.009 | 39.627 | 59.5 |

The V2 gate's development frames do not move in rows: lv_dev (list vintages 2011 to 2019, W3)
closed at V 2020 and vm_dev (vm2, base years 2017 to 2023, career WAR to date) keeps its 829 rows
with one more season of outcome on every open row. Their re-read on the frozen label is P5's.

## 3. The resolvable-margin arithmetic

Source: `data/xfv_mde_floor.json` (`tools/efv_mde_lab.py mde 2000`: paired bootstrap over the whole
pool, train and test resampled together, refit every draw, seed 20260807; one-sided 95 percent =
1.645 x sd; pair-weighted, row weight = observed_seasons / 6). The rescaling is the sqrt rule
`PROGRAM.md` s2.5 and the census floor curve already use, applied to the pair-weight mass:
mde95_after = mde95_before x sqrt(W_before / W_after).

| side | n_ref rows (2026-08-07) | sd_ref | mde95 one-sided, before | W_before | W_after | ratio | mde95 one-sided, after |
|---|---|---|---|---|---|---|---|
| hit | 755 | 0.02712 | 0.0446 | 619.988 | 684.155 | 1.1035 | 0.0425 |
| pit | 892 | 0.02585 | 0.0425 | 709.958 | 785.509 | 1.1064 | 0.0404 |

Two cautions, stated once. The row count of the scored pool is unchanged by the clock, so a row-
count floor does not move at all; the mass version above is the generous reading. And a floor is
measured, not scaled: the floor that counts after the epoch is step G's re-run of the same lab on
the fWAR label, and clause (l) of the epoch gate bars any accuracy claim from the label move.

## 4. The 2025 cohort

`DEBUT_YEARS = range(2011, RESOLVED_THROUGH)` admits the 2025 cohort automatically when the clock
moves (`efv_dataset.py`, the comment above `DEBUT_YEARS`), at the builder's terms for 2026: 2 observed
seasons, weight 0.333, censored. The label pool census counts 243 debuts, 176 with an in-window
consensus read, 149 with both scored sources, 219 with a career_war row (presence only). The cohort
is R-VM (`efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR` 2025): `reserved_vm_pins()` is empty today and must
stay empty, so the cohort enters the matrices at step F and no fold scores it until the R-VM look
record exists. The weight it would carry (176 x 0.333 = 58.6 on the consensus-present rule) is not
in section 3.

## 5. The shorter-horizon label views

Definition: `first3` and `first4` are summed WAR over the first three and first four MLB seasons
from the debut year, the builder's window convention with `SERVICE_ALIGNED_WINDOW` off (so the same
start season as L6). A view resolves when debut_year + k - 1 is at or before `RESOLVED_THROUGH`, and
it projects nothing: a resolved view carries none of the flat-rate tail projection's bias, which
`docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md` s6.2 measures at n_obs 3 as -0.964 WAR (hitters, CI95
-1.267 to -0.658) and -0.450 (pitchers), and at n_obs 4 as -0.340 and -0.184. It also measures a
different quantity, which is the cost.

| view | resolves when | cohorts resolved at 2025 | at 2026 | rows beyond L6 at 2025 (hit / pit) | at 2026 (hit / pit) | debuts.json rows beyond L6 at 2026 (debuts / with career_war) |
|---|---|---|---|---|---|---|
| L6 (primary) | debut + 5 <= RT | 2014 to 2020 | 2014 to 2021 | | | |
| first4 | debut + 3 <= RT | 2014 to 2022 | 2014 to 2023 | 203 / 208 (2021, 2022) | 222 / 228 (2022, 2023) | 503 / 465 |
| first3 | debut + 2 <= RT | 2014 to 2023 | 2014 to 2024 | 297 / 336 (2021 to 2023) | 313 / 347 (2022 to 2024) | 743 / 682 |

Faithfulness to the six-season label, development debut cohorts 2014 to 2019 only (both fully
observed under both clocks; 2020 and 2021 reserved and not read; no 2025 or 2026 season line
read). Percentile bootstrap over rows, one row per player per side, B 2000, seed 20260906. The
ewar_v2 reading is the builder's own input (its six-season sum reproduces the matrix
`target_resolved` on 334 of 334 hitter and 342 of 342 pitcher rows); the frozen fWAR reading joins
by MLBAM id (330 of 334 and 337 of 342 rows carry one by the matrix, debuts.json or the override
asset) and is label-to-label arithmetic, not a label move.

| view | label | side | n | Spearman (CI95) | Pearson (CI95) | share of six-season mass |
|---|---|---|---|---|---|---|
| first3 | ewar_v2 | hit | 334 | 0.8756 (0.8361 to 0.9099) | 0.8888 (0.8548 to 0.9174) | 0.424 |
| first3 | ewar_v2 | pit | 342 | 0.8563 (0.8062 to 0.8947) | 0.8499 (0.7992 to 0.8951) | 0.429 |
| first3 | fwar frozen | hit | 330 | 0.8882 (0.8488 to 0.9172) | 0.8853 (0.8505 to 0.9147) | 0.421 |
| first3 | fwar frozen | pit | 337 | 0.8695 (0.8281 to 0.9045) | 0.8648 (0.8179 to 0.9047) | 0.439 |
| first4 | ewar_v2 | hit | 334 | 0.9508 (0.9273 to 0.9676) | 0.9543 (0.9392 to 0.9659) | 0.644 |
| first4 | ewar_v2 | pit | 342 | 0.9256 (0.8948 to 0.9499) | 0.9412 (0.9219 to 0.9575) | 0.641 |
| first4 | fwar frozen | hit | 330 | 0.9582 (0.9387 to 0.9713) | 0.954 (0.9398 to 0.9648) | 0.64 |
| first4 | fwar frozen | pit | 337 | 0.933 (0.9022 to 0.9565) | 0.944 (0.9275 to 0.9585) | 0.638 |

The prior on record agrees: lane E2's probe (`debuted_frame_firstk_vs_L6`, cohorts 2011 to 2020 on
ewar_v2, which includes the 2020 cohort) read first3 at 0.8711 (hitters, n 491) and 0.876
(pitchers, n 543), and first2 at 0.739 and 0.7051, the number `PROGRAM.md` s3.3 carries for the R-VM
look-1 label. The censoring gate's pooled season-share profile (0.080, 0.138, 0.185, 0.215, 0.202,
0.179 on 988 fully resolved debuts) puts 40.3 percent of six-season WAR in the first three seasons
and 61.8 percent in the first four, which the development rows reproduce (0.42 to 0.44 and 0.64).

What a view costs, said plainly. The industry FV frame is six-year value: the five FanGraphs
FV-to-WAR tables, the Clemens kernel and the served grade are all six-season quantities, and the
eFV gate adjudicates on that label. A first-k view is a different statistic: it rewards early
arrival and early peaks, it reads nothing of seasons k+1 to 6, which carry most of the WAR mass,
and a rank gain measured on it is not a rank gain on the six-year quantity the grade promises. Its
gain is honest and narrow: rows resolved without projection, free of the measured tail bias, two
(first4) or three (first3) cohorts earlier than L6. `PROGRAM.md` s3.3 already records that inside
the debuted frame a faster label adds nothing to the scoring label (the 2026-07-24 NO-SHIP,
`docs/SURROGATE_LABEL_PROGRAM.md`), and lane A's s4 lists every shorter view as a hazard component,
a veto leg or a measured loss. Nothing here reopens that: the views are secondaries, not scoring
labels.

## 6. The design: a label family for the screening lab, a label-view axis for the matrix

Registered standing: SECONDARY label views, reported beside the primary, never a frame change.
The primary stays L6 on the vintage-matched frames and W3 on the list-vintage frames.

The admission rule, as the artifact carries it:

1. A secondary view is reported beside the primary in the same table, with its own n, its own
   floor from the same resampler, and the word SECONDARY; it never replaces the primary before a
   reserved read, and no ship decision, weight, order or claim reads it.
2. Screening lab (EFV3_B1): the view enters as a label family `label_view` with members `first3` and
   `first4`. The candidate arm is the base assembly scored against the view instead of the primary,
   on the same development folds (lv_dev V 2017 to 2019 for a list-frame view, where the view is
   the first-k sum from the debut inside V..V+3 and 0 without one; the vm development rows for a
   debut-frame view), with the same statistic (`efv_v2_stat.within` primary, pooled secondary,
   contributor AUC veto), the same three noise-column floors and its own Holm family. It admits
   nothing to the assembly: a view arm's reading says how the base order relates to a shorter
   quantity, not whether a column enters.
3. Matrix (EFV3_D1 / D2): the view enters as a LABEL-VIEW axis beside the outcome thresholds (1, 2,
   3 and 4 career WAR). Every cell declares the label it was scored against; a cell on a secondary
   view carries the word SECONDARY and the target-validity note of section 5. The frame, cell,
   comparator and statistic axes are unchanged, and the axis adds no stratum by any grade.
4. Target validity is printed wherever a view is printed: the industry FV frame is six-year value,
   so a first-k view measures a different quantity, and its gain is rows resolved without
   projection, not accuracy.
5. On a reserved frame a view is read only by the look that owns the frame, in the same run, as a
   secondary row; a view never opens a reserved frame on its own. The one shorter label a reserved
   look uses is first2 on R-VM look 1, which is that look's own definition and not this family.
6. The 2026 season is a label season only after step D+U moves `RESOLVED_THROUGH`; before that no
   view reads a 2025 or 2026 line (this tool reads through 2024).

Why a label family and not a frame: the frames are populations and timings (`PROGRAM.md` s2.2);
a view changes the statistic computed on the same rows. Registering it as a family keeps the
frame counts, the reserved guards and the floors as they are, and keeps the one-look rule intact.

## 7. The calibration record: where eFV meets prospect WAR, and when each reads 2026

| surface | file | clock today | reads 2026 after the epoch | made by |
|---|---|---|---|---|
| the training label (`_label_6yr`; `efv_model` fits `target_censored`) | `efv_dataset.py` | `RESOLVED_THROUGH = 2025`; `DEBUT_YEARS` derived from it | yes: step D+U moves the constant, step F rebuilds both matrices | EPOCH_RUN (D+U, F) |
| W3, W2, R3 and never-resolution labels on the list-vintage frames; the V2 P5 re-derivation and the DS-16 re-run read them | `efv_labels.py` | `resolved_through()` returns `efv_dataset.RESOLVED_THROUGH` | yes, with `efv_dataset`; P5 re-derives `data/efv_v2_assembly.json` once on the frozen label | EPOCH_RUN, then EFV_V2_GATE P5 |
| the FV-to-WAR anchors (`fv_to_6yr_avg_war`, re-measured at step J, then the sub-45 knots re-applied and `FV_WAR_ANCHORS` synced) | `value_framework.py`, `empirical_anchors.py` | no `RESOLVED_THROUGH`: the cohort is snapshot years reference_year - 9 to - 6 (2017 to 2020 in 2026) and realized is the first six stored MLB seasons as the career_war table holds them | yes, once step C rebases career_war to fwar and step J runs `value_framework.py --fit`; the window is calendar-lagged rather than clock-gated, so a 2020 listing's late debut is summed short of six seasons | EPOCH_RUN (C, J) |
| the pooled FV to outcome curve, THE eFV grade map (`fv_outcome_pooled_grade`) | `tools/fv_outcome_curve_pooled.py` | no own clock: matrix rows with `censored == False` | yes, through the rebuilt matrices; the 2021 cohort joins the uncensored pool | EPOCH_RUN (I, after F) |
| the calibration knots (`backtest.fit_calibration_knots`, built at HEAD; the one knots-only refit at $17.14M) | `backtest.py` | no `RESOLVED_THROUGH`: realized seasons priced from the PlayerRecord's realized series as stored | yes, through the career_war table after step C; the refit must run after step C to read 2026 | CAL_KNOTS_REFIT_17M (after EPOCH_RUN step C) |
| the star label and `star_odds_model` | `tools/build_star_odds_artifacts.py` | `_RESOLVED_THROUGH = 2025`, moved with `efv_dataset`'s by decision O2 | yes, at step N | EPOCH_RUN (N) |
| the consensus accuracy backtest and the Source Comparison ledger stamp | `source_backtest.py`, `efv_progress.py` | stamp `efv_dataset.RESOLVED_THROUGH` into the receipt and `model_version` | yes, at step Q and the ledger refresh | EPOCH_RUN (Q) |
| the Clemens anchors (the `clemens_2026` valuation set: published FV-to-outcome and $/WAR tables) | `value_framework.py` | none: a published external table, never re-measured on our label | not applicable; coherence with the label is by construction once the label is published fWAR (gate part 1) | none |

So every fitted surface reads `RESOLVED_THROUGH` 2026 through the epoch's own steps, two of them
(the anchors and the knots) through the rebased career_war table rather than a clock, and the
Clemens tables are a definition, not a calibration. No surface needs a task this document creates.

## 8. The progress ledger

No row is appended to `data/efv_progress.json`. Its rule is "a row is added when a frame's measured
content changes", its rows are frame rows (`efv_progress.FRAMES`), and no label-pool frame or note
row type exists; the label pool census's row rode lv_dev with its counts. This read changes no
frame's measured content, so the artifact says `progress_ledger.appended: false` with that reason.

## 9. Read to write this, and not read

Read: `efv_dataset.py` (`RESOLVED_THROUGH`, `TARGET_SEASONS`, `DEBUT_YEARS`, `_label_6yr`,
`SERVICE_ALIGNED_WINDOW`), `efv_model.py` (`SCORED_YEARS`, `_prep`, `_decision_year`, the mde floor
notes), `efv_labels.py` (`resolved_through`, `provider`, `war_seasons_table`), `efv_vintage_frame.py`
(`RESERVED_LV`, `R_VM_FIRST_DEBUT_YEAR`, `reserved_vm_pins`), `fwar_vintage.py` (`war_by_group`),
`war_source.py`, `empirical_anchors.py`, `backtest.fit_calibration_knots`, `tools/fv_outcome_curve_pooled.py`,
`tools/build_star_odds_artifacts.py`; `data/xfv_hitter_matrix.json` and `data/xfv_pitcher_matrix.json`
(debuted rows), `data/efv_label_pool_census.json` (debut cohort counts, the label stamp),
`data/xfv_mde_floor.json`, `data/fwar_vintage.json` (seasons 2014 to 2024, side group only),
`data/debuts.json` and `data/sources/mlbam_id_overrides.json` (ids only); `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`
(parts 1, 3, 5, 7, 9), `docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md` (s6.2, the share profile),
`docs/efv-v2/PROGRAM.md` (s2.2, s2.4, s2.5, s3.3), `docs/efv-v2/EFV_V2_GATE.md` (s2, s4.5, P5),
`EFV3_PLAN.md` s3 and `LANE_A.md` s4, `DECISIONS_FOR_OWNER.md` (EFV-2026-LABEL, CLOCK-WT,
CLOCK-MERGE), lane E2's `probe_labels.json` (the first-k prior, copied).

Not read: any outcome of the 2020, 2021, 2025 or 2026 debut cohorts (the tool's `outcome_guard`
raises for them and the test proves it); any 2025 or 2026 season line of any player
(`max_season_read` 2024, asserted on every window sum); R-LV and R-VM frames (never built);
any statistic by consensus-FV cell; the 39 closed arms.

## 10. What this does not do

It registers no new scoring label, changes no frame, moves no served number, re-fits nothing,
appends no ledger row, and claims no accuracy from the label move (clause (l)). It does not run the
epoch, read the frozen label as a label, or score any rater against any view. A run after step D+U
is a new read on the fWAR label and a new section here, never an edit of the numbers above.
