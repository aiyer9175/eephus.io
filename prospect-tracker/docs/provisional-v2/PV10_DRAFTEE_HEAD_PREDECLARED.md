# PV-10 pre-declaration: the draftee head (players with no pro line) for provisional v2

Written 2026-10-02, before any first-grade label was joined to a draft record. Spec: the
research bundle _finalpass_2026-09-24/provisional/PROVISIONAL_V2.md, section 3 (Architecture,
"Draftees with no pro line") and section 5 (PV-10). Companion: PV11_ALEVEL_SIGNALS_PREDECLARED.md.

Read before this file, and nothing else: the draft cache layout and field coverage per class
(.cache/draft_bonus/2017.json to 2026.json: picks, rounds, slot value, signing bonus, school
class, pre-draft rank, birth date, position), and label-source capture volume by source and
month (prospects.db snapshots row counts, no player join). No first grade of any draftee, no
label rate and no FV of any drafted player has been read. No WAR is read, now or in the lab.

## 1. Why a separate head

The served provisional model and PV-06 (provisional_v2.py) cover only players with a MiLB line
in the feature season. Of the 217 players first graded after 2026-06-23 that the served model
had not graded first, 195 were draftees, mostly the 2026 class, with no pro line yet (PG1
section 3). PG2's pedigree-only T1 numbers (Pipeline AUC 0.759, ANY 0.625) were measured on
players WITH a line and are not evidence for this population. The head asks two questions of a
draftee on the day the draft closes: will a label source grade him by the next preseason lists
(T1, who), and at what first FV on that source's scale (T2, level).

## 2. Frames and labels

Label sources, sets and dating are PV-06's exactly: FanGraphs, MLB Pipeline (incl.
international), Baseball America, ESPN, Just Baseball; sets ANY, FG, MLBP; an opinion is dated
min(snapshot_date, UTC date of inserted_at); a set's first grade is its earliest dated opinion;
first FV is the mean FV on that date, FanGraphs 35+ / 40+ coded as the half step (+2.5).
Identity is provisional_v2.Inputs (snapshot player_key to mlbam, the same maps and the
unique-name-slug fallback). Opinions dated after the run date are never read.

Classes: the 2017 to 2025 drafts (.cache/draft_bonus). The universe of a class is every drafted
mlbam id with no MLB or MiLB line in any season before the draft year and no label-source
opinion dated on or before the frame's anchor. A player drafted in two classes is a row in
each; the bootstrap clusters by mlbam.

Frame DRAFT (primary). Anchor A = the last day of the draft (public calendar): 2017-06-14,
2018-06-06, 2019-06-05, 2020-06-11, 2021-07-13, 2022-07-19, 2023-07-11, 2024-07-16, 2025-07-14.
- G_PRE (primary label): the set's first grade in (A, Apr 15 of D+1], through the next
  preseason lists. Before 2026 the label sources were captured about once a cycle (Pipeline in
  January, FanGraphs in February and a July/August board, BA in February from 2023), so the
  in-season weeks after the draft are not backcastable; the window is chosen for that reason.
- G12 (secondary): first grade in (A, Oct 15 of D+1]; classes whose window is closed on the
  run date only (2025's closes 2026-10-15 and is left out).

Frame SIGNED (secondary). Anchor Aug 2 of D, the day after the latest signing deadline of the
nine classes, so the bonus is known; universe ungraded on or before Aug 2; label G_PRE from
that anchor.

Frame NOLINE_OCT (secondary). Anchor Oct 15 of D (the PV-06 Oct anchor); the class's draftees
with no MiLB line in season D either, ungraded on or before Oct 15; label first grade in
(Oct 15 of D, Apr 15 of D+1]. This is the exact population PV-06 cannot see at its own anchor.

Capture guard: PV-06's rule (provisional_v2.CAPTURE_FLOOR 0.5): a class is used by a head only
if every source of the head's set that was captured in earlier classes' windows has at least
half its median earlier volume inside this class's window. A class left out is listed with
its reason. This is expected to drop the 2025 class from the MLBP and ANY heads (48 Pipeline
rows dated in January 2026 against about 1,000 a year before).

## 3. Features (point in time)

PED0 (draft day; DRAFT and NOLINE_OCT frames): log overall pick; round as a number
(supplemental and competitive-balance rounds at the half step after their round: 1C, CB-A and
PPI 1.5; CB-B, 2C and SUP-2 2.5; SUP-3 3.5; 4C 4.5); log slot value (pickValue, bonus-pool picks
only, else missing); HS and JC flags from schoolClass (missing for the 2017 and 2019 classes,
whose records carry no school class; left missing, not inferred); age at the anchor from the
birth date; log pre-draft rank (the statsapi rank, MLB Pipeline's draft prospect rank) and a
ranked flag; pitcher flag.

PED1 (SIGNED frame only) = PED0 + log signing bonus (bonus > 0, else missing), bonus over slot
(slot > 0), signed flag (bonus > 0).

Known leak, stated and kept: the pitcher flag is statsapi's CURRENT primary position, not the
draft-day one; side conversions after the draft are a small share. Excluded as post-hoc or not
point in time: person.active, currentAge, the blurb and scouting-report text, the drafting
team, the class year.

## 4. Estimators

- T1 (primary estimator): one LightGBM classifier per head, the fixed PG2 params of
  provisional_v2.PARAMS (300 trees, lr 0.03, 15 leaves, min_child_samples 40, subsample 0.8,
  colsample 0.8, seed 7), both sides pooled with the pitcher flag as a feature. Forward-chained:
  each test class is scored by a model trained only on the usable classes before it; a class is
  a test class once at least two usable classes precede it (so 2019 onward). Transparent check
  (reported, not the claim): logistic regression (median impute, standard scale, C 1.0).
- Zero-fit nulls: draft order (minus overall pick); pre-draft rank (minus rank, unranked after
  every ranked pick in pick order).
- T2 (level): per source, FG and MLBP, ridge alpha 10 (provisional_v2.RIDGE_ALPHA; median
  impute, standard scale) on PED0, trained on earlier usable classes' rows graded by that source
  inside G_PRE, label that source's first FV; constant = the training rows' mean. A test class
  needs 30 training rows.

## 5. Metrics and claims

- T1: per test class and pooled: n, first graded, base rate, AUC, AP, Brier raw and the
  training-rate constant's Brier; pooled AUC and AP with CI95, and the paired deltas model
  minus draft-order null, by player-cluster bootstrap (B 1,000, seed 7, percentile).
- T2: pooled MAE, bias, Spearman, share within 2.5 FV, constant MAE, and MAE minus constant
  with its paired cluster-bootstrap CI95; by side; by class.
- Claim rule (primary, ANY G_PRE on DRAFT): "the head orders who is graded better than draft
  order" only if the pooled AUC delta and the AP delta against the draft-order null both have a
  CI95 above 0. Otherwise the result reads "draft order is the head": a zero-fit pick-order
  rank does as well, and no fitted head is proposed. A level claim for a source needs MAE minus
  constant with a CI95 below 0. Secondary heads are reported and claim nothing.
- No stratum is named after a consensus-FV cell, no FV-value distribution of the labels is
  reported (docs/PROSPECT_ANCHOR_GATE.md), and no eFV, consensus or source-accuracy score is
  computed (the reserved list vintages are untouched; first grades are labels, as in PV-06).

## 6. Output and what it cannot change

The lab is tools/provisional_draftee_lab.py. It writes one block, pv10_draftee, labelled
BACKCAST, into data/provisional_v2_eval.json; provisional_v2.build carries the block forward
when it rewrites the file. The block is a development read and adjudicates nothing. Nothing is
served: no page reads the block, data/provisional_v2.json is unchanged, the served grade and
the board section are unchanged, and no provisional number feeds eFV. Serving a draftee head
(or a pick-order rank) is an owner decision recorded after the read.
