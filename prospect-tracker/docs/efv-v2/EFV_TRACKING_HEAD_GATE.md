# eFV tracking-era head (EFV5_TRACKING_HEAD): registration

Registration status: REGISTERED (development head, dark; nothing served moves by this
document)

Written 2026-10-15, worktree lane 202, before any outcome of a tracked row was related to
any tracking metric, under decision EW3-1 of 2026-10-14
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): tracking-era metrics (2021 and later cohorts,
no six-season WAR yet) are fit against a SHORT-HORIZON label in a separate, clearly labelled
"tracking-era" head, scored against consensus on the same rows, entering eFV only if they
beat consensus AND served V2 on a held-out cohort, and upgraded to the six-season label as
the cohorts mature. The dates and look days are waived (EW3-5); the one read of the
held-out cohort runs the same day this document commits and is recorded as an owner-waived
early read. No em-dashes. Nothing here is cut by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`): consensus FV enters only as a continuous covariate.

Producer: `efv5_tracking_head.py` (`EFV_TRACKING_HEAD_ON = False`, imported by no served
module). Artifact: `data/efv5_tracking_head.json` (role development). Results in plain
language: `docs/efv-v2/EFV_TRACKING_HEAD_RESULTS.md`. Pins: `test_efv5_tracking_head.py`.

Where this document and the measurement disagree, the measurement is what the read uses
and the disagreement is recorded, never edited away.

## 0. What was read before this document was written

Nothing here relates a tracking metric to an outcome. Read during design: the published
coverage census of the tracking fetch (`data/_labs/efv5/tracking_coverage.json`: the levels
and seasons served, the field shares per season, bat speed empty on every pitch); the
published eFV v5 metric atlas (`data/efv5_metric_atlas.json`, 2026-10-14), whose tracking
family carries 951 pooled 2021 to 2025 cells on the horizon-censored labels and on reach3
with NO candidate clearing its rule (CI95 lower bound above zero with BH q at or below
0.1), so the atlas does not pick the candidates below and the candidate list is the one the
owner's task named; and a COUNT-ONLY census of rows per (side, season, level) with a
consensus read and the tracking metrics present (no label was joined to it): on the atlas's
qualified lines, listed tracked pitchers number 36 (2021 A), 39 (2022 A), 29 (2022 AAA),
28 (2023 A), 61 (2023 AAA); listed tracked hitters 55, 48, 19, 50, 55 on the same cells.
The head's own frame (section 3) uses the fetch's qualification rather than the atlas's
box-line one, so its rows are somewhat more numerous; its counts are published by the read.

The atlas's pooled cells include the rows of the held-out cohort below (its horizon-censored
labels read every season 2021 to 2025). That is disclosed here: the design decisions of this
document (the label, the split, the candidate list, the model, the rule) were fixed from the
task's text and from counts, not from those cells, and the atlas's development numbers are
not used to choose anything in sections 4 to 9.

## 1. The question

Does a head that combines PROSPX consensus FV with the tracking metrics of a prospect's
most recent tracked MiLB season order a held-out cohort of listed prospects better than
consensus alone and better than the served eFV v2, on a short label that the 2021 and
later cohorts can already resolve? Only a lead over BOTH comparators on the held-out cohort
can let the head into eFV; a lead over consensus alone admits nothing (EW3-1; the atlas's
distinction between a raw "reaches the majors" score and information consensus has not
priced).

## 2. The label (N fixed here)

N = 3. H = 2026, the last season with MLB lines and frozen fWAR on disk
(`data/fwar_vintage.json`, label `fwar@2026-10-02-0341299c20ec`, the epoch's own file; MLB
lines are the sport-1 season lines of `.cache/milb_stats`, hitting or pitching). For a row
(player, season S):

    reach3    1 if the player's first MLB line is in S+1 .. S+3, else 0
    rate3     fWAR summed over the player's MLB seasons inside S+1 .. S+3, divided by the
              count of those seasons (hitting plus pitching fWAR per season); 0 for a row
              with no MLB season in the window

Both resolve when S + 3 <= H, so S <= 2023. "Early WAR per MLB season" is rate3; "reached
MLB within N seasons" is reach3. Why N = 3: it is the longest window that leaves THREE
resolvable tracked cohorts (2021, 2022, 2023) at H = 2026, so a train set of two cohorts
and a held-out cohort both exist; N = 2 would resolve 2024 as well but makes a Single-A
cohort's positives rare, and N = 4 or more would leave a single training cohort. The
window is a structural choice; no outcome count was taken to make it.

## 3. Rows, cohorts, and the split

A row is one (player, S) with:

1. a tracked MiLB season line in the EFV5_TRACKING_FETCH tables
   (`.cache/efv5_savant_minors/tables/{pitcher,hitter}_season_level.csv.gz`) at the fetch's
   own qualification (pitchers 100 or more pitches, hitters 50 or more PA at that level
   and season); when a player has tracked lines at two levels in S, the HIGHER level's line
   is the row (AAA over A), the lower is not used;
2. a PROSPX consensus FV read inside the V = S + 1 preseason window, taken exactly as the
   atlas takes it (`efv5_atlas.consensus_reads`: the F-LV frame row of the outcome-blind id,
   `efv_vintage_frame.build_frame(side, V)`, consensus key `source_backtest.CONSENSUS_KEY`);
   the row's `player_key` is that frame row's key;
3. no MLB season line at or before S (not a prospect at S otherwise);
4. every registered CORE metric of its side present (section 4); the one NON-CORE metric
   (pitcher arm angle, mostly unserved before 2023) is imputed at the training mean when
   absent, and its absence carries no column.

Tracked seasons and levels are what the fetch verified: 2021 Single-A Florida State League
only; 2022 to 2025 Triple-A plus the Florida State League; AA and High-A never served.

Cohorts (S), fixed:

| cohort | levels tracked | role | label window (first MLB season) | reserved overlap |
|---|---|---|---|---|
| 2021 | A | TRAIN | 2022 to 2024 | clean |
| 2022 | A, AAA | TRAIN | 2023 to 2025 | reaches the 2025 debut cohort (R-VM, spent since the 10-08 confirmation): labelled SPENT |
| 2023 | A, AAA | HELD OUT, read once | 2024 to 2026 | reaches 2025 and 2026 (R-VM, spent): labelled SPENT |
| 2024, 2025 | A, AAA | not resolvable at H = 2026 | | upgrade path, section 10 |

Train on the earliest tracked cohorts (2021, 2022), hold out the latest with a usable
short label (2023). Every choice of section 5 is made on the training cohorts only, by
player-grouped cross-validation inside them. The held-out cohort is read ONCE, by the same
run, after the choices are frozen in the artifact's `selection` block; nothing is chosen on
it. The 2022 training cohort's window reaches the spent R-VM 2025 debut cohort; the owner
authorised short-horizon reads of the tracking era (EW3-1) and the atlas took the same
reads as owner-waived early reads (`docs/efv-v2/EFV_V2_GATE.md`, note of 2026-10-14). Every
number this read produces on a row whose window reaches 2025 or later is labelled "spent"
in the artifact and in the results, and no R-LV list vintage (2020, 2021) is built: the
consensus vintages used are V 2022, 2023 and 2024.

## 4. Inputs: the tracking candidates (as-of only)

Every metric is the row's own (player, S, level) season aggregate from the fetch tables,
so it is from a season finished before any label season (S + 1 and later). Nothing from
S + 1 or later enters a row.

Pitchers (6):

| metric | fetch column | core | the task's name |
|---|---|---|---|
| aStuff+ (stuff_plus_aaa v1, applied, never refit) | `astuff_plus` | yes | Stuff+ |
| top-end fastball velocity (95th percentile) | `fb_velo_p95` | yes | top-end velo |
| primary fastball induced vertical break | `fb_ivb` | yes | ride |
| arm angle (mean of Savant's column) | `arm_angle` | no (imputed when absent) | arm angle |
| xwOBA against | `xwoba_against` | yes | xwOBA against |
| exit velocity against, mean | `ev_against` | yes | EV against |

Hitters (5):

| metric | fetch column | core | the task's name |
|---|---|---|---|
| exit velocity, 90th percentile | `ev_p90` | yes | EV |
| hard-hit rate | `hard_hit` | yes | hard-hit |
| barrel rate | `barrel` | yes | barrel |
| chase rate | `chase` | yes | chase |
| zone contact rate | `zone_contact` | yes | z-contact |

Not available, by name: Pitching+ and Location+ (no in-repo model; fitting one on outcomes
is out of scope, `tracking_coverage.json` `not_available`); bat speed (the column is empty
on every fetched pitch of every season). They are named here so that a later fetch that
serves them re-registers rather than slips them in.

Consensus FV is the only non-tracking input. Level enters as one indicator (AAA against A).
Age, role and position do not enter the head; they are reporting strata (section 7).

## 5. The model, fixed before the read

Per side, two heads on the same design matrix X = [1, AAA indicator, z(consensus FV),
z(metric 1), ..., z(metric k)], every z standardised on the TRAINING rows (mean and sd
stored with the fit; the held-out rows take the training moments):

    reach head   P(reach3 | X) = sigmoid(X w_R), ridge-penalised logistic regression by
                 Newton steps from a zero start; the intercept, the level indicator and
                 the consensus column are unpenalised, the metric columns share one penalty
                 lambda_R
    rate head    E[rate3 | X, reached] = X w_W, ridge regression on the training rows with
                 reach3 = 1 only (rate3 is defined on reached rows; the hurdle form is
                 V2's); the same penalty structure with lambda_W
    the output   order_head = P(reach3 | X) * E[rate3 | X, reached], ONE number per row,
                 unclipped (a negative expected rate stays negative, V2's convention)

Penalty grid, both heads: lambda in {1, 3, 10, 30, 100, 300, infinity}. Infinity switches
the metric columns off, so "consensus plus level alone" is always a candidate and the
head cannot be forced to carry a metric. Selection: 5 player-grouped folds on the TRAINING
rows (seed 20261015, players shuffled once and dealt round robin), lambda_R by the
out-of-fold AUC of P(reach3) against reach3, lambda_W by the out-of-fold Spearman of the
rate head's value against rate3 on the reached training rows; ties go to the LARGER
penalty. The selected pair is written to the artifact before the held-out rows are scored.
That is the whole forking-path budget: 7 x 7 per side, no metric subset search, no
threshold, no weight. Nothing is refit on the held-out cohort.

"Which metrics carry the weight" is READ from the fit, not chosen: the artifact reports
each metric's standardised coefficient in each head at the selected penalty, the share of
the metric columns' summed absolute coefficient it carries, and whether its sign agrees
across the five training folds (sign-stable). A metric is reported as carrying weight for a
side when it is sign-stable in the head and holds at least 15 percent of that head's
metric weight. This is a description of the fitted head; it admits nothing by itself.

## 6. The comparators, on the same rows

    consensus   the row's consensus FV at V = S + 1 (section 3, item 2), as read
    served V2   eFV v2 as assembled (`efv_v2_model.fit_v2` at the P5 weights of
                `data/efv_v2_assembly.json`): the F-LV fold object for vintage V, fitted on
                the labelled development vintages 2011 to 2019 with every player of the V
                frame left out of training (`efv_v2_model.v2_lv_scores` on
                `efv_v2_model.lv_training_rows(side, tools/efv_v2_assemble.build_frames())`,
                the object SG_4B froze for V 2026), scoring the full F-LV frame of V
                (`efv_vintage_frame.build_frame(side, V)` with the V2 sidecars attached as
                `build_frames` attaches them), joined to the head's rows by `player_key`;
                the compared number is V2's `order_idx` (its one output, the order the
                board, the comparison and the price derive from)

V is 2022, 2023 or 2024; none is reserved (R-LV is 2020 and 2021 and is never built). A row
without a V2 score (a frame row V2 drops for want of a consensus does not exist here; a
join miss is a defect) is reported as such and left out of every three-way comparison; the
artifact counts them.

## 7. Statistics

Per side, on a set of rows: AUC of a score against reach3 (ties at one half) and the
Spearman rank correlation of a score against rate3 (one cohort, so no within-season
pooling is needed on the held-out read; on the training rows the within-cohort Spearman,
size-weighted, `efv5_atlas.within_rho`). Reported for order_head, consensus FV and V2's
order_idx, and the two paired deltas (head minus consensus, head minus V2) each with a
CI95 from a bootstrap over rows with B = 2000, seed 20261015 (a cohort holds one row per
player, so a row is a player cluster), scores fixed and rows resampled (E_cond). A read is
UNREADABLE for a side when its rows number fewer than 50, or its reach3 positives or
negatives fewer than 10; an unreadable side cannot ship and says so.

Development (training) numbers: the out-of-fold order_head on the training rows at the
selected penalties, against consensus and V2 on the same rows, the same statistics. They
are the selection frame and adjudicate nothing.

Group reports (reporting only, nothing chosen on them): the held-out statistics by level
(A, AAA), by pitcher role (SP, RP: the EFV3_C05 rule on the row's own box-score season
line, games started over games below 0.5 is RP) and by hitter position group (C, SS, CF,
other IF, corner OF, 1B/DH from the listing position inside the V window, the atlas's
map), for every group with at least 20 rows and at least 5 positives and 5 negatives.

## 8. Admission into eFV: the ship rule (fixed before the read)

A side SHIPS only if, on its held-out cohort, order_head beats BOTH consensus FV AND served
V2 on BOTH statistics as point estimates (AUC on reach3 and Spearman on rate3, four strict
inequalities), the CIs being reported beside them and binding nothing. A side whose read is
unreadable, or whose selected penalties are both infinity (the head is consensus plus
level), does not ship. The two sides are decided separately.

If a side ships (the default blend, section 8.1): for a prospect of that side whose
current read carries the head's inputs (a tracked line in the latest finished MiLB season
with every core metric present, at the fetch's qualification), the served eFV order inside
(side, list year) becomes

    u = 0.5 * u(V2 order_idx) + 0.5 * u(order_head)

with u the within-(side, list year) percentile over the tracked prospects of that group and
the result carried through V2's output map (`efv_v2_model.output_map`: consensus sets the
level, the model only reorders). Untracked prospects keep V2's order as served. Every
surface that shows such a grade carries the note "tracking-era head, short-horizon label
(reached MLB within 3 seasons; fWAR per MLB season over those seasons)". The flip is
`EFV_TRACKING_HEAD_ON = True` plus the served exporter's rebuild, listed under the
report's INTEGRATION NOTES; nothing in this task's own commits flips it.

If neither side ships: nothing served moves, the head stays dark, and the development and
held-out numbers are published in the artifact and in the results document so the owner
can see what the tracking metrics did and did not add over consensus and over V2.

### 8.1 Defaults the owner may want to choose differently

- D-1 the blend weight when a side ships: 0.5 / 0.5 (default; the head is a whole model
  on consensus plus tracking, not a single driver); alternatives: the head replaces V2's
  order for tracked prospects (1.0), or the head enters at a quarter (0.25, DS principle 2's
  small constant weight).
- D-2 the short label's window: N = 3 (default, section 2); alternatives: N = 2 (adds the
  2024 cohort now; rarer Single-A positives), N = 4 (one training cohort only).
- D-3 the candidate list: the task's named metrics (default, section 4); alternative: add
  the tracked K-BB%, CSW% and whiff rates the owner's chart scored highest, which are
  box-score and pitch-call quantities the atlas scores under its other families.

## 9. Bans and hygiene

- PROSPECT_ANCHOR_GATE: no mean, residual, count or cohort by consensus-FV cell anywhere
  in the producer, the artifact or the results; consensus FV is a continuous covariate and
  a comparator score, nothing else. `test_efv5_tracking_head.py` scans the source.
- Reserved frames: R-LV never built (V 2022 to 2024 only); R-VM overlap labelled spent on
  every row and number it touches (section 3); nothing selected on a spent row beyond what
  the training cohorts' windows contain, as disclosed.
- No projections retrain; `backtest.run_backtest` is never called; no served module
  imports the producer; no fetch (every input is on disk: the fetch tables, the season-line
  cache, the frozen fWAR file, `prospects.db` read-only for listing positions).
- Rounding: eFV and plus stats nearest; no grade is produced here.
- No em-dash in the producer, the tests, the artifact or the documents.

## 10. Upgrade path (EW3-1: "upgraded to the six-season label as cohorts mature")

- After the 2027 season (H = 2027): cohort 2024 resolves on reach3 and rate3; it becomes
  the held-out cohort and 2023 joins training, by a dated amendment below this section
  and one new read. The 2025 cohort follows a year later.
- The six-season label (the frozen fWAR label's own horizon, `l6` in the atlas) resolves
  for the 2021 cohort's debuts of 2022 to 2024 from 2027 to 2029; when a training cohort
  resolves it, the head re-registers on that label and the short label becomes a
  secondary read.
- Any new tracked level (AA, High-A) or new column (Pitching+, Location+, bat speed)
  re-registers the candidate list; it does not enter an existing read.

## 11. Dated notes

- 2026-10-15: written and committed alone, before the producer existed. The read follows
  the same day under EW3-5 (owner-waived; the only registered date is this one).
- 2026-10-15: THE READ (owner-waived early read, EW3-5; `python efv5_tracking_head.py --run`, B 2000,
  70.7 s, artifact `data/efv5_tracking_head.json` generated 2026-10-15T12:49:45Z, registration
  sha256 a3918d6565e9, HEAD at the run e1589ce3). Frame: hitters
  154 training rows (45 reached) and 124 held out (73 reached);
  pitchers 160 (74) and 122 (91); every row joined a served V2 score.
  Selection (training only): hitters lambda_R inf, lambda_W 300.0; pitchers lambda_R 30.0,
  lambda_W 10.0. Held-out cohort 2023 (spent, R-VM overlap):
  hitters: head AUC 0.6465 / rho 0.3258; consensus 0.5939 / 0.3318; V2 0.6052 / 0.3657; head minus consensus AUC +0.0526 (CI95 +0.0011 to +0.1083), rho -0.0060 (CI95 -0.0745 to +0.0663); head minus V2 AUC +0.0413 (CI95 -0.0181 to +0.1046), rho -0.0399 (CI95 -0.1333 to +0.0551).
  pitchers: head AUC 0.6324 / rho 0.2389; consensus 0.5635 / 0.1918; V2 0.5803 / 0.1772; head minus consensus AUC +0.0689 (CI95 -0.0183 to +0.1517), rho +0.0471 (CI95 -0.0758 to +0.1681); head minus V2 AUC +0.0521 (CI95 -0.0259 to +0.1280), rho +0.0617 (CI95 -0.0587 to +0.1796).
  VERDICT by the section 8 rule: hitters DO NOT SHIP (rate3 Spearman trails both comparators);
  pitchers SHIP (all four strict inequalities hold as point estimates). Recorded, not edited away:
  every one of the pitcher side's four CI95s includes zero, and the held-out group reports
  (section 7, reporting only) split: by level the head trails consensus on AUC at both A
  (0.677 vs 0.752, n 41) and AAA (0.446 vs 0.479, n 81; 72 of 81 reached),
  so part of the pooled AUC lead is the level indicator placing AAA above A; by role the head
  leads at both RP (0.634 vs 0.510; rho 0.307 vs 0.113, n 49) and SP (0.660 vs 0.624, n 73).
  The rule was fixed before the read and is applied as written; the flip stays with the
  integrator and the owner (report, INTEGRATION NOTES and OWNER-Q). The served path is built
  dark (`efv5_tracking_head.apply_to_live`, called by `efv_v2_serve.score_live`; the blend of
  section 8.1 D-1; the chip and the card note), and `EFV_TRACKING_HEAD_ON` is False in this tree.
  Which metrics carry weight (section 5, pitchers): reach head aStuff+ (+), exit velocity against (-)
  and arm angle (-, imputed where absent); rate head exit velocity against (-) and aStuff+ (+).
  Hitters: the reach head took lambda infinity (no tracking metric enters) and the rate head at
  lambda 300 carries the 90th-percentile exit velocity (-), a sign the owner should read as noise.
- 2026-10-15: CANDIDATE ADDENDUM (EFV5_ATLAS_TOOLS_STATCAST, owner EW3-7; an owner-waived
  early read under EW3-5). The atlas's method was rerun on each tracked Statcast component on
  its own (`efv5_atlas_tools.py`, `data/efv5_atlas_tools.json`): fastball mean and top-end
  velocity, ride, arm-side run, spin, vertical approach angle, release height, extension, arm
  angle, and whiff, called-strike and chase-induced rates by pitch class for pitchers; exit
  velocity (mean, 90th percentile, max), hard-hit, barrel, sweet-spot, launch-angle sd, chase,
  zone contact and whiff for hitters (bat speed is served on no tracked pitch). 653 tests; NO
  clean cell exists (the only clean windows, reach3 and w3 at S 2021, hold the 2021 Florida
  State League alone: 55 listed hitters and 36 listed pitchers, under the 150-player minimum),
  and none of the 152 spent cells with an incremental score passes the rule (the best q, 0.052, belongs
  to cells where adding the component LOWERS the out-of-fold score). So the addendum adds NO tracking candidate: section 4
  and D-3 stand as registered, and this note enters no existing read (section 10). Descriptive
  only, spent: the components that order reach-by-2026 best on the full Florida State League
  pitcher population are fastball chase induced (oriented AUC 0.704), fastball velocity mean
  and 95th percentile (0.687, 0.682), extension (0.615) and a flatter fastball approach angle
  (0.602), against consensus FV's 0.722 on the listed rows.
