# fWAR label epoch: pre-registration (2026-09-17)

STATUS: REGISTERED, RESULTS EMPTY. This is the plan's E4. It is committed ALONE and BEFORE
the rebuild it governs. Nothing in this commit changes a model, an exporter, a flag or a
served artifact: the registration registers, it does not rebuild. Git timestamps it; part 9
is filled in afterwards and nothing above part 9 may be edited once results exist (the
`EPOCH_2026_PREREGISTRATION.md` pattern, carried through `EWAR_LABEL_EPOCH_GATE.md`).

- Plan: `docs/master-plan-2026-09-11-war-epoch-drivers-betting.md`, section 1. Lane tags
  [R1] to [R5] below are that plan's, and every number carrying one is a label-only
  descriptive measured on 2026-09-11 with no fit.
- Predecessor of this class: `docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md`. Clauses (a) to
  (h) in part 4 are its clauses, verbatim.
- Runbook: `docs/efv-2026-09-03/WAR_BASIS_RUNBOOK.md`. Its rules are unchanged and part 7
  carries the order with the fWAR-specific rows.
- Standard: `docs/EFV_GATE_STANDARD.md` (floors, controls, estimators, the 0.02 equivalence
  margin, seed convention 20260807).
- Pinned by `test_fwar_label_epoch_registration.py`, at the repository root beside the
  other gate pins. It asserts that every clause (a) to (l) is present, that (a) to (h) are
  byte-identical to the predecessor, and that part 9 records no result.
- The registration that follows this one: clause (k).
- History, 2026-10-02 (a location note, no clause changes): the 2026-09-04 epoch's evidence
  that part 3 and part 7 step A name as `../_pre_epoch_2026-09/` was MOVED, not deleted
  (owner answer 2026-09-25, batch 6), to `C:/Users/noah/baseball-projects/_archive_2026-09-25/_pre_epoch_2026-09/`,
  a sibling of the git root, beside a sha256 `MANIFEST.json`; `tools/efv_ewar_label_epoch_lab.py
  --blast` reads it there unless `EWAR_PRE_EPOCH_SNAPSHOT` names another directory. Step A's
  own destination and its refusal rule are unchanged.

## 0. What kind of decision this is

**The WAR label basis is an OWNER BASIS DECISION. It ships regardless of margin.**

That sentence is carried from the predecessor and it is still the whole frame. The owner is
not claiming that published fWAR makes eFV, the projections or any priced number more
accurate. The owner is choosing which quantity the site means by "WAR", and every model that
is labelled, anchored or priced in WAR follows the definition. So this gate has no SHIP or
NO_SHIP verdict on the flip itself.

What IS pre-committed is what gets MEASURED, how it is reported, what the epoch may and may
not carry, and which factor owns which movement.

One thing is new against the predecessor, and it is the reason clause (l) exists. The
2026-09-03 epoch measured a NULL on the accuracy question: for hitters the label barely
moved at all (change sd 0.049 WAR, zero rows over 1 WAR), and the pitcher move that did
happen could not be separated from zero at the registered margin. This epoch moves a label
that moves for real, hitters most of all (change sd 1.785 WAR). A larger movement is not
evidence of a better label. It is evidence of a different definition. The temptation to read
one as the other is much larger this time, so the prohibition is written as its own clause
instead of living inside the copy contract.

## 1. Decision record (owner, 2026-09-17, taken in chat)

1. **The label.** PUBLISHED fWAR, taken from MLB's StatsAPI sabermetrics feed and FROZEN
   PER SEASON, becomes the training and anchoring label for every fitted consumer named in
   plan section 1.1 (the plan's source S1, its O1 default). The eWAR v3 replica and the
   W1.3 arms stay display-only in this program.
2. **Bundled.** The fWAR label change and the `RESOLVED_THROUGH` advance from 2025 to 2026
   ship in ONE rebuild, at the close of the 2026 regular season (the plan's O2 default).
   `efv_dataset.RESOLVED_THROUGH` and `build_star_odds_artifacts._RESOLVED_THROUGH` move
   together.
3. **Why bundled, stated once.** They are the same event on the calendar. Doing them
   together rebuilds every fitted artifact once instead of twice in about three months, and
   one driver re-sweep afterwards answers both reopen conditions instead of two sweeps
   answering one each. The cost is attribution: with two factors in one rebuild, no number
   can be attributed to either by simple before-and-after. Clause (i) is the price paid for
   the bundle, and it is not optional.
4. **Date.** 2026-09-17. Three other answers were taken in the same sitting and none of them
   rides this epoch: the close job on the deploy box is SKIPPED, the dark lineup capture is
   armed, and slots move to publishable markets only. Those are betting-module decisions,
   registered in `docs/diamond-betting.md`, and this gate neither carries them nor depends
   on them. The one place the close-job answer touches this program is named in clause (j),
   point 6.

### What published fWAR is, stated so the copy cannot overclaim

- It is FanGraphs' WAR as MLB publishes it. Choosing it adopts every FanGraphs convention
  wholesale: the 57/43 position-player and pitcher replacement split, the runs-per-win
  closed form, FanGraphs' league pool and positional ladder, and Statcast fielding with
  framing inside it.
- It is therefore NOT our model and NOT our measurement. It is a definition we are adopting.
  It is exact in the sense that it reproduces its own source: [R1] matched the FanGraphs
  leaderboard at 0.0000 on 2011 and on 2025, the feed joins at 100.0% on MLBAM in every
  season 2011 to 2025, and both sides are cached 2011 to 2026. Exact reproduction of a
  source is not accuracy against an outcome, and no clause here measures the latter.
- What the choice buys is COHERENCE, and the mechanism is namable: for the first time the
  label, the five FanGraphs FV-to-WAR tables, the Clemens dollar-per-WAR kernel and the
  displayed number are one currency. Star-season disagreement against the Clemens tables
  falls from 37.8% to 0 and dollar-per-WAR tier disagreement from 9.76% to 0 [R1]. Both
  fall BY CONSTRUCTION, because the same definition now sits on both sides of the
  comparison, and any copy that reports them says so in the same sentence.
- What it does not buy is stated in clause (l), and clause (l) is absolute.

## 2. The measured blast radius already on the record

These are the label-only descriptives the plan carries [R1, R2]. They were measured on
2026-09-11 with no fit, no gate and no game outcome. They are PRIOR to this epoch and they
are not clause (f)'s blast radius: clause (f) is a separate, post-rebuild read of the served
artifacts against the step A snapshot, per arm, and it has not been taken.

| Quantity | Hitters | Pitchers |
| --- | --- | --- |
| The LAST epoch's move (bWAR to eWAR v2), resolved rows | n 459, r 1.0000, sd(d) **0.049**, 0 rows over 1 WAR | n 527, r 0.9534, sd(d) 1.435, 194 rows |
| THIS epoch's move (eWAR v2 to published fWAR), resolved rows | r 0.9716, mean -0.224, sd(d) **1.785**, 164 rows over 1 WAR, against a label sd of 7.47 | r 0.9850, mean +0.113, sd(d) **0.831**, 81 rows |
| New label variance, 1 - r^2 | 0.056, against 0.000 last time | 0.030, against the 0.091 move that was measured a null |
| All debuted rows, Spearman eWAR v2 against fWAR | 0.9402, mean abs 1.117 WAR, 302 of 842 move 1 WAR or more | 0.9404, mean abs 0.548 |
| Where the move lives | fielding: cross-frame window r 0.624, change sd 1.319 WAR, correlation 0.802 with the total change | starter careers (90+ IP per pitched season, n 131) gain +0.771 and carry 58% of the squared change; the other 839 move -0.024 |
| Clemens bucket-band crossings | 112 of 842 (13.3%) | 67 of 982 (6.8%) |
| Implied 5-grade through the shipped pooled curve | **288 change (34.2%)**, 119 move 2 grades or more, almost all in FV 20 to 40 | 282 change (28.7%), 117 move 2 or more |
| Clemens star label (2+ control seasons of 4+ WAR) | 60 to 48: 21 lose, 9 gain | 20 to 24: 1 loses, 5 gain |
| Label at or below 0 | 326 to 315 (45 leave, 34 enter) | 309 to 328 (45 leave, 64 enter) |

Two readings are registered now, before any fit, so that neither can be argued after one:

- **The registered pitcher prior is a null, and the reason is the FLOORS, not the size of
  the label move.** Nine of the thirteen standard cells carry E_cond floors of 0.0203 to
  0.0322 against a 0.02 margin (note 4), so most cells can only come back UNDECIDED whatever
  the label does. A pitcher cell that comes back UNDECIDED is the expected reading, not a
  disappointment. Beside that, as a descriptive and NOT as its cause: the pitcher move here
  (sd 0.831) is smaller than the bWAR to eWAR v2 pitcher move (sd 1.435) that the last epoch
  could not distinguish from zero. The sd of a label change is a fact about LABELS, while
  clause (d) adjudicates a delta between same-label MARGINS, a different quantity, and a
  smaller label move does not mechanically imply a smaller margin delta.
- **The hitter side is the new thing, and it is a fielding change.** Almost all of the hitter
  move is the fielding component (correlation 0.802). That is a definition swap from our
  fielding treatment to FanGraphs' Statcast-with-framing treatment. It is not new
  information about the players.

Busts who never reached MLB carry label 0 on every basis. They are 1,052 of 1,903 hitter
matrix rows, so the never-debuted half of the pooled curve's pool does not depend on the
basis at all [R1].

## 3. Preconditions E1 to E8, with today's status

The status column was read off the repository on 2026-09-17 at HEAD `710f8824`. The working
tree at that read carried 73 dirty entries: 71 under `data/`, plus a modified `sitemap.xml`,
which is a tracked served artifact and not generated churn, plus an untracked
`_pre_epoch_2026-09/` at the repository root, which is the PREVIOUS epoch's snapshot and is
step A's business (part 7), not this table's. Every status is a fact about the tree, not a
plan.

| # | Item | Status 2026-09-17 | Evidence read today |
| --- | --- | --- | --- |
| E1 | Owner decisions O1 to O13 | **PARTIAL.** O1 and O2 are answered (part 1). O3 (the D9 freeze date), O4 (the pre-2011 cache), O5 (displayed WAR at the flip), O6 (bust taxonomy), O7 (which label-definition arms ride) and O8 to O13 are OPEN | plan section 6; no answer for O3 to O13 is recorded in the tree |
| E2 | Identity repair, and the tripwire test that every nonzero window season has a feed row under its bound id | **NOT MET.** `career_war` reads 2,679 rows, 2,544 `ewar_v2` and 135 `bbref`, so the 135 rows that resolve to no MLBAM id are still there. No tripwire test exists: `test_career_war_ewar_funnel.py` pins the rebase funnel, not this. The 13 label players carrying 50 window seasons under a bound id with no feed row (for example `carlos_martinez`, bound to 830052, carrying 2013-2018 seasons worth 15.45 WAR [R1]) are unrepaired, and the identity lane that owns them is paused. That lane's running count, about 31 of 185 cases adjudicated, is an UNCOUNTED NOTE from its own cache: no source in this row's evidence column carries it, and it does not have the standing of the rest of the row. `data/identity_collisions.json` gained `myles_bailey` in the latest monthly run | read of the `career_war` payloads in `prospects.db`, 2026-09-17; the test listing; `data/identity_collisions.json` |
| E3 | Frozen per-season fWAR vintage with `fetched_at`; a pitching loader in `saber_feed`; provider `fwar` in `war_source` (servable, not default); a rebase tool with a provider parameter and one receipt schema; the pre-2011 cache per O4 | **NOT MET, in five parts.** (1) No frozen vintage artifact exists; `data/` holds only `fwar_replica_eval.json`. (2) `saber_feed.py` fetches `group=hitting` only and its `cache_key` is `statsapi_saber_hitting_<season>`; there is no production pitching loader. (3) `war_source.PROVIDERS` is `("bwar", "ewar_v2", "ewar_merged")` and `DEFAULT_PROVIDER` is `"ewar_v2"` (`war_source.py:133,136`), so `fwar` is not servable at all. (4) The only rebase tool is `tools/rebase_career_war_to_ewar.py`, eWAR-only, with no provider parameter. (5) The pre-2011 cache does not exist. What DOES exist is a local `.cache` of the hitting and pitching sabermetrics payloads for 2011 to 2026, written by `tools/fwar_replica_eval.py`. A gitignored cache written by an eval tool is not a frozen vintage and may not be used as one | `war_source.py`, `saber_feed.py`, the `tools/` and `data/` listings, the `.cache` listing |
| E4 | This registration, committed alone | **IN HAND at this commit**, results empty | this file |
| E5 | 5c's looks recorded and GRPO's first forward read taken, or amendments filed under their own rules before those looks | **NOT MET, and the dates have MOVED.** No 5c column looks on 2026-09-17. 5c-A (`xwoba_14`, `xwoba_30`) looks 2026-09-28; 5c-B (`lineup_strength`) and 5c-C (`star_out`) look 2026-10-05. Both B4 sections were revised 2026-09-16 and are FINAL AT COMMIT, so no amendment to either is admissible. GRPO's 2026-09-18 forward read has not been taken | `docs/diamond-betting.md` sections 5c-A, 5c-B and 5c-C |
| E6 | The 2026 regular season ended and the D9 freeze fetch taken | **NOT MET.** The regular season ends 2026-09-27; today is 2026-09-17. O3's freeze fetch (default about 2026-10-05) has not been taken, and O3 is itself unanswered | the calendar; plan O3 |
| E7 | An independent label rebuild matching the new matrices on at least 99% of debuted rows | **NOT MET.** The template (`label_shift_descriptive.py`, which reads 837 of 842 and 972 of 982 on v2) lives in the planning scratchpad under `plan3/R2_driver_ledger/`, not in `tools/`. No independent fWAR-frame rebuild receipt exists | the `tools/` listing; the R2 lane folder |
| E8 | The owner's 2026-09-11 answers that move served numbers have landed, each in its own epoch with its fingerprint term | **MET, with receipts.** `storage.WAG_UNIFIED = True` (`storage.py:5650`); the wOBA scale served from 2015 (`league_constants.SERVED_FROM = 2015`, commit `419811bb`); the F10-01 re-point in `bullpen_export.py`; and the A's and Rays parks, the runline tie split, Ohtani on the starter board and the DFS started-games removal at `497d667f`. Step A's snapshot is clean of all of them provided it is taken at or after HEAD `710f8824` | `git log`; the named files |

**The rule this table is for.** A precondition blocks the part 7 steps that DEPEND on it,
and the map is written out here so that the rule is executable rather than all-or-nothing.
Building what a precondition asks for is not a part 7 step and is not blocked by this table:
writing the E3 tool, repairing an E2 identity or taking the E6 freeze fetch is exactly how a
row stops reading NOT MET.

| Precondition | Blocks |
| --- | --- |
| E1 | O7 blocks step F, because clause (i) fixes the arm set at the moment O7 is answered; O4 blocks step K's `war_basis` stamp; O3 is carried by E6; the remaining open answers block no part 7 step |
| E2 | step C and every step after it, because a rebase onto a label whose identity join is unrepaired writes the defect into `career_war` |
| E3 | steps C and D + U: there is no vintage to rebase onto, no pitching loader, no `fwar` provider to flip to and no rebase tool with a provider parameter |
| E4 | every step. IN HAND at this commit |
| E5 | steps D + U, E and M, by clause (j) |
| E6 | steps A and C: the frozen vintage cannot be taken before the season it freezes has ended |
| E7 | step F, and therefore every margin, every arm and every clause (d) cell |
| E8 | step A, whose snapshot must be clean of the 2026-09-11 answers |

No step begins while a precondition that blocks it reads NOT MET. This gate does not waive a
precondition. A waiver is an owner decision, recorded here as a dated amendment BEFORE the
step it waives, naming what is unmet and what is lost by proceeding. An unmet precondition
discovered after a step has run does not become a waiver; it becomes a disclosure in part 9.

## 4. The eight carried clauses

### 4.1 How to read them on this epoch (the substitution rule, stated once)

The clauses in 4.2 are reproduced verbatim from
`docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md` part 3. They were written for the eWAR v2
epoch and they are NOT edited here, because an edited clause is a new clause. They are read
under the substitution and the six notes below, all fixed at this commit.

- **Substitution.** "bWAR" reads as "eWAR v2", the incumbent label of this epoch. "eWAR"
  reads as "published fWAR", the candidate. "the eWAR frame" reads as "the fWAR frame".
  Everything else is literal: `SCORED_YEARS`, the seed convention, the 0.02 margin, the
  estimator set and the fold structure are unchanged.
- **Note 1. Clause (a)'s regen control is VOID on this epoch, and is REPLACED.** Clause (a)
  makes the hitter cells the regen control because under eWAR v2 the hitter label did not
  move. On this epoch the hitter label is the side that moves MOST (change sd 1.785 against
  the pitchers' 0.831). There is no side that stands still, so there is no free control, and
  none may be improvised later. The replacement, registered now: the control is clause (e)'s
  zero-information twin, computed PER SIDE, together with the leave-one-out arms of clause
  (i). What clause (a)'s control existed to catch, a movement that is not the basis, is
  caught here by an arm that cannot account for it, and that residual is published under
  clause (i) rather than traced informally.
- **Note 2. Clause (b) on this epoch.** The incumbent column of the cross-label matrix is the
  eWAR v2 label, not bWAR. The reconstructibility requirement carries with the same
  mechanism and now binds the E3 rebase tool: after `career_war` is rebased to `fwar`, the
  eWAR v2 series must remain reconstructible from the table itself (the `seasons_<basis>`
  mechanism that `tools/rebase_career_war_to_ewar.py` established for `seasons_bwar`, plus
  `data/ewar.json`), with the pre-rebase sqlite backup as the cross-check and never as the
  only source. A rebase that cannot reconstruct the incumbent has destroyed the matrix's
  incumbent column, and that is a STOP.
- **Note 3. Clause (c) on this epoch.** The coverage census is re-taken on the fWAR join.
  The 90 percent cohort line, the per-side split, the per-fold reporting and the "report the
  number, never pool and never hide" rule are unchanged. What can fail has changed: the
  eWAR census was limited by the build (pre-2016 seasons the artifact did not carry), while
  the fWAR feed joins at 100.0% on MLBAM for 2011 to 2025 [R1]. The two failure modes left
  are identity (E2: the players with no id or a wrong id) and the pre-2011 seasons, which
  the feed reaches only if O4's cache is taken. A cohort served by a mixed basis is stamped
  `war_basis: mixed` per artifact and is never stamped `fwar` (O4).
- **Note 4. Clause (d) on this epoch.** The margin is 0.02 Spearman, unchanged, applied to
  the difference between the same-label margin on fWAR labels and the same-label margin on
  eWAR v2 labels. The known limit is unchanged and is restated because it is a fact about
  the registration and not about the label: nine of the thirteen standard cells carry E_cond
  floors of 0.0203 to 0.0322, so at a 0.02 margin most cells can only come back UNDECIDED.
  The pitcher prior is a null (part 2).
- **Note 5. Clause (f) on this epoch** is read PER ARM, not once: every blast-radius item is
  reported for E0, for E* and for each leave-one-out arm of clause (i). The pinned top-100
  side mix (`test_board_basis_coherence.PINNED_MIX`) is read against E* only.
- **Note 6. Clause (h)'s "Appendix A" reads, on this epoch, as PART 6 of this document.**
  Part 6 is the frozen ride list. A factor that is not in part 6 when the first matrix is
  built is out of the epoch, full stop.
- **Note 7. Clause (h)'s KIND restriction is OVERRIDDEN for exactly two named factors, by
  owner decision, and for no others.** Clause (h) says "no feature arm" and says the epoch
  may carry ONLY label-definition fixes. Part 6 admits two factors that clause (h) as
  written would bar: `RESOLVED_THROUGH`, which is an advance of the resolution clock and not
  a label-definition fix, and F-DEF, which part 6 itself calls a projections-only arm inside
  step M, that is, a feature arm. Each override is an OWNER DECISION and not a reading this
  gate took: `RESOLVED_THROUGH` by O2 of 2026-09-17 (part 1), F-DEF by the owner's answer of
  2026-09-11 ("in the WAR epoch"). The override is these two factors, named here, and no
  other factor may use it; a third factor claiming it is out of the epoch under note 6.
  Everything else in clause (h) stands: no lambda move, no correction family, and no feature
  arm other than F-DEF. Recording the override is the point. The predecessor's Appendix A
  was expressly a list of audit label-definition FIXES, part 6 is not, and a substitution
  that quietly widened the clause while claiming only to relocate its list is exactly the
  failure this mechanism exists to catch.
- **Note 8. Clause (g)'s MECHANISM carries; its frame-disclosure CONTENT does not.** Clause
  (g) requires that every basis claim on a served surface be replaced by the new frame's
  disclosure, and it then spells out the eWAR v2 frame: "B-Ref run frame, FIP pitching swap,
  fielding upgrade pending SDR, position players identical to bWAR until then". Substituting
  labels into that sentence produces a FALSE description of published fWAR, which is not a
  B-Ref run frame and whose position players are not identical to the incumbent (part 2:
  34.2% of hitter rows change implied grade). So the clause's mechanism carries verbatim and
  binds, including the eight named copy gates and the rule that a gate is updated in the
  SAME commit as the served string it asserts on; its frame sentence is replaced, for this
  epoch only, by the fWAR frame disclosure registered in part 1: FanGraphs' published WAR
  adopted wholesale, its 57/43 replacement split, its league pool and positional ladder, and
  Statcast fielding with framing inside it. The source line numbers clause (g) cites
  (`assets/glossary.js:618`, `:1301`, `:2653`; `assets/diamond.js:152`) are the
  predecessor's read of 2026-09-03; step X re-resolves them by name and never trusts a line
  number.

### 4.2 The clauses, verbatim

A clause is a measurement obligation, not a ship condition, except where it says STOP.

### (a) Same-label margins only, floors first, both sides

The decision quantity is the eFV-minus-consensus margin with BOTH scored on eWAR
labels. Absolute rho on the new label is reported but adjudicates nothing.

Order of operations, blocking: (1) `efv_dataset` matrices both sides on the rebased
`career_war`; (2) `efv_model` evals both sides; (3) `python tools/efv_mde_lab.py mde 2000`
and `python tools/efv_power_lab.py all 2000` on THAT frame, writing
`data/xfv_mde_floor.json` and `data/xfv_power_eval.json`; (4) only then the deltas.
E_cond is primary, E_refit is reported beside it, same seed convention (20260807) as the
standard. Both sides, all four pre-registered cuts (full_pool_km and debuted_km, hit and
pit), plus the head-to-head common set with the player-clustered estimator.

Pre-committed mechanism (from the sdr-ewar plan W3.4 and the hitter identity above): the
hitter label does not move, so the hitter cells are the REGEN CONTROL for this epoch.
Any hitter margin change larger than its E_cond floor is evidence that something other
than the WAR basis moved and must be traced before the pitcher cells are read.

### (b) The cross-label matrix

Four cells per side, all reported, none suppressed:

| model fitted on | scored on bWAR labels | scored on eWAR labels |
| --- | --- | --- |
| bWAR labels | the retired served frame (parity check) | cross cell |
| eWAR labels | cross cell | the new served frame |

Consensus is scored on each label beside the model in every cell, so every cell is a
MARGIN, not a rho. The diagonal difference (new same-label margin minus old same-label
margin) is the effect of the swap on the margin; the off-diagonal cells say how much of it
is "the model learned the new label" against "the label got easier for everyone". The
honest cell leads in any copy; the matrix is published whole in the eval artifact.

Requirement on the rebase: the bWAR label must remain RECONSTRUCTIBLE after
`career_war` is rebased. The L1 tool (`tools/rebase_career_war_to_ewar.py`) writes
`seasons_bwar` beside the served `seasons` on every rebased row, and `data/ewar.json`
carries `bw` beside `ew` per player-season, so the lab reads the bWAR label from the table
itself; the pre-rebase backup (`prospects.db.bak-ewar-<date>`, sqlite backup API) is the
cross-check, not the only source.

### (c) Coverage clause

Share of LABEL SEASONS (debut year through debut+5, capped at RESOLVED_THROUGH) served
by eWAR against bWAR fallback, by side and by debut cohort band (2011-2015, 2016-2019,
2020-2025), plus the count of debuted players with no mlbam id anywhere. **A pitcher
cohort below 90 percent eWAR coverage is REPORTED with its number, not hidden and not
pooled** (the pitcher-stuff 0.0-delta lesson). Coverage is reported per fold in the eval
artifact and the fold-level figures are what the matrix cells are read against.

Baseline census taken at registration (read-only, 2026-09-03, against the `data/ewar.json`
ON DISK, which is the 2026-08-04 build covering 2016-2026; the L1 rebuild to 2011 is what
lifts the first band):

| debut cohort | label seasons | join eWAR | share | no id | id, no eWAR row |
| --- | --- | --- | --- | --- | --- |
| 2011-2015 | 2,911 | 1,207 | 41.5% | 239 | 1,465 |
| 2016-2019 | 1,875 | 1,834 | 97.8% | 32 | 9 |
| 2020-2025 | 3,347 | 3,328 | 99.4% | 19 | 0 |

Method: `career_war` 2,666 rows; `debuts.json` 2,742 rows, 1,977 carrying `mlbam_id`;
ids completed from `data/sources/mlbam_id_overrides.json` and
`mlbam_id_overrides_busts.json`; 69 debuted players resolve to no id by any route. The
1,465 "id, no eWAR row" seasons in the first band are pre-2016 seasons, which the
`--first 2011` build supplies; the 290 no-id seasons are the identity floor no build
reaches. Pitching source inside the artifact today: 8,969 pitcher-seasons priced on FIP,
28 on B-Ref fallback (cells under `MIN_ROLE_CELL_ROWS` 20).

Second census, same method, same day, against L1's rebuilt artifact (`ewar.json`
generated 2026-09-03T12:35:09, seasons 2011-2026, 22,160 player-seasons, 5,136 players;
pitcher-seasons priced 12,457 on FIP, 35 on B-Ref fallback). `career_war` itself was still
all-bbref (2,666 rows) at this read; the rebase had not been applied:

| debut cohort | label seasons | join eWAR | share | no id | id, no eWAR row |
| --- | --- | --- | --- | --- | --- |
| 2011-2015 | 2,911 | 2,616 | 89.9% | 239 | 56 |
| 2016-2019 | 1,875 | 1,834 | 97.8% | 32 | 9 |
| 2020-2025 | 3,347 | 3,328 | 99.4% | 19 | 0 |
| all | 8,133 | 7,778 | 95.6% | 290 | 65 |

So the 2011 build closes 1,409 of the 1,465 build-limited seasons and the first band lands
at 89.9 percent POOLED across sides, one tenth of a point under the clause's line, with the
gap being the 239 no-id seasons (identity, not the build). Both censuses pool hitters and
pitchers; the per-side split is the lab's to compute (`debuts.json` rows carry no reliable
side flag; `efv_dataset._side_match` is the resolver to reuse).

Pre-committed expectation, restated on the second census: the 2016+ bands clear 90 percent
on any side split. The 2011-2015 band is expected to sit within a point of the line and
its pitcher half may fall under it; if it does, the clause REPORTS the number, the
affected folds (SCORED_YEARS 2014 and 2015) are read separately from the pooled headline,
and the remedy is identity work on the 69 no-id players, never pooling or silence.

### (d) TOST margin on the swap's effect

Delta = 0.02 Spearman (the owner's registered equivalence margin, `EFV_GATE_STANDARD.md`
part 8) applied to the DIFFERENCE between the same-label margin on eWAR labels and the
same-label margin on bWAR labels, per side, E_cond interval. Three dispositions:
interval entirely inside +/- 0.02 is RULED OUT (the swap does not change the accuracy
story); entirely above is a swap GAIN; entirely below is a swap LOSS; otherwise
UNDECIDED. Whatever it says, the flip ships (part 0); the disposition decides the COPY
(clause g), nothing else. Known limit, stated up front: nine of the thirteen standard
cells carry E_cond floors of 0.0203-0.0322, so at 0.02 most cells can only come back
UNDECIDED. That is a fact about the registration, not about eWAR.

### (e) Controls

1. **Zero-information twin.** Take each player-season's eWAR-minus-bWAR delta, permute
   the deltas ACROSS PLAYERS within (season, side), add them back to bWAR, and re-label.
   The twin has eWAR's marginal distribution and none of its information. If the twin's
   same-label margin matches the eWAR cell, there is no result to attribute to FIP.
2. **Permutation null band** for the same quantity (delta of margins), B >= 2,000.
3. **>= 4 independent time splits.** The delta of margins is averaged over the
   forward-chained folds of `efv_model.SCORED_YEARS` and the per-fold signs are
   published; a headline with fewer than 4 folds behind it is not a headline.
4. **Paired bootstrap** resampling both train and test with a refit per draw for the
   E_refit leg, scored rows only for E_cond (the standard, sections 2 and 7).

### (f) Blast radius, MEASURED and published

Captured against a pre-epoch snapshot taken BEFORE any rebuild step runs (runbook step
A). Nothing here is gated; a zero must be explained.

- Board re-rank: rows moved, max and median |rank delta|, p90; membership change at
  top 10 / 25 / 100 / 250 (the 2026-08-13 epoch measured 4,585 of 4,664 moved, top-10
  change 0; that is the scale to compare against).
- Top-100 side mix against `test_board_basis_coherence.PINNED_MIX`
  ({"top10": 0, "top25": 1, "top50": 2, "top100": 6}); re-record only if breached.
- Surplus dollar movement, BOTH channels named separately: the `_odds_grade` channel
  and the `rank_war` quantile channel (`GRADE_BASIS_EPOCH_GATE.md` condition 5).
- WAG label flips per org and per graduate (survivor anchors move with the curve).
- `star_label` flips in `data/star_label_view.json` (Clemens star: >= 2 team-control
  seasons of 4+ WAR; a pitcher whose FIP season crosses 4.0 in either direction flips).
- Arbitration: rows whose WAR spine changes, and the award-model re-read.
- Projections: the four pins (feature schema length, `meta.train_hash`, the ml_config
  gate, the `star_blend` pin) all move or the retrain did not happen.

### (g) Copy contract

The derived three-branch accuracy copy (`assets/glossary.js:618`, `:1301`, `:2653`;
`assets/diamond.js:152`; branches win / tie / lose off the served eval artifacts) is
UNCHANGED IN MECHANISM. Its inputs regenerate; nothing is hand-written. Every "bWAR"
claim on a served surface is replaced by the eWAR frame disclosure: B-Ref run frame,
FIP pitching swap, fielding upgrade pending SDR, position players identical to bWAR
until then. Copy gates that literally assert "bWAR" (`test_claims_freshness.py`,
`test_methodology_freshness.py`, `test_board_basis_coherence.py`, `test_fa_def_pin.py`,
`test_efv_sff_crosswalk.py`, `test_war_rate_plus.py`, `test_projections_smoke.py`,
`test_fa_projection.py`) are updated in the SAME commit as the served string. No copy
may say eWAR is more accurate; the R3a/R3b record and clause (d)'s disposition are the
only accuracy statements available, and the tie frame stands until a cell says
otherwise under Holm.

### (h) Stop clauses

Inside this epoch: **no lambda move** (blend lambda shifts are a banned lane; the 0.70
pin's TOST is RULED OUT), **no correction family** (no affine, no dispersion, no band
fix fitted to make a cell pass), **no feature arm** (the driver re-sweep is a later
program on the finished frame, owner decision 6). The combined label epoch may carry
ONLY the design audit's label-definition fixes, and only those named in Appendix A
BEFORE the rebuild starts. A fix that is not in Appendix A when the first matrix is
built is out of the epoch, full stop. If a cell fails a control, the lane records a
loss ledger and does not proceed to a second specification.

### 4.3 The predecessor's parts 5 and 7, each carried, void or replaced

The predecessor carries two things beside its clauses: its part 5, the pre-committed
interpretations that map a clause (d) disposition into copy, and its part 7, the abort
conditions for the rebuild. Neither is a clause, so neither is inside the verbatim block
above, and dropping them in silence would lose the half of a registration that decides what
a result MEANS before the result exists. Each is dispositioned here, fixed at this commit.

**Part 5, the pre-committed interpretations. CARRIED, with one replacement.** Every mapping
from a clause (d) disposition to copy carries as written, read under the substitution and
under clause (l), which is strictly stronger than the predecessor's own version of the same
prohibition:

- RULED OUT on both sides: the accuracy story is unchanged by the basis, the tie frame
  stands, and copy discloses the frame and says nothing about accuracy moving.
- UNDECIDED, the expected outcome at these floors: the same, with the cell logged with its
  interval and no "directional" language anywhere.
- GAIN on pitchers: the margin moved by the stated amount with its interval, and no "better"
  without the gate 1 loss beside it.
- LOSS on pitchers: the flip STILL SHIPS (part 0), the loss is disclosed with its interval,
  and the R3b mechanism is the stated explanation only if the cross-label matrix supports it;
  otherwise it is logged as unexplained.
- Coverage below 90 percent on a band: that band's folds are reported separately and
  excluded from the pooled headline, with the count.

REPLACED is the predecessor's "a hitter cell moving past its floor stops the epoch, because
the hitter label did not change". On this epoch the hitter label is the side that moves MOST
(part 2), so a hitter cell past its floor is the EXPECTED reading and stops nothing. What
replaces it is clause (i): a hitter movement that no arm accounts for lands in the
unattributed residual and is published there.

**Part 7, the abort conditions. Two carry, one is void, one is replaced.**

- CARRIED: abort if the `career_war` rebase leaves any season of any player with NEITHER an
  fWAR nor an eWAR v2 value. The merge-preserving upsert should make it impossible; assert
  it rather than assume it.
- CARRIED: abort if top-10 board membership changes. It is the 2026-08-13 tripwire, not a
  gate on size, and it is read against `PINNED_MIX` under note 5.
- VOID: the two conditions on the rescaled league eWAR sum for 2011-2015. There is no
  rescale on this epoch. Step B is SKIPPED and published fWAR is adopted as published, not
  fitted, so there is no replacement-wins target of ours for it to miss.
- REPLACED: "abort if the hitter margin moves past its floor for any reason OTHER than
  position-player pitching". Its premise was a hitter label that does not move. On this
  epoch the hitter label moves by design, so the condition has no content here and is
  replaced by the clause (i) reading above.

The predecessor's own record on that last condition is why this section exists at all: the
abort condition it wrote was FALSIFIED by the rebuild it governed, and it was restated on
2026-09-04 BEFORE the margins were read rather than after. That is the standard this
document is held to.

## 5. The four clauses this epoch adds

These are new. They are not in the predecessor, and they exist because this epoch is a
BUNDLE (two factors in one rebuild), because a dark betting column now takes input from the
artifacts it rebuilds, because a separate re-test registration follows it, and because the
last epoch of this class measured a null that copy must not be allowed to forget.

### (i) The attribution arms

Without arms, a bundled rebuild destroys clause (f). Two factors move on the same day and
every moved number has two possible owners, so "the basis did this" becomes unfalsifiable.
The arms are how a bundled rebuild can still say which factor moved a number.

**The matrix set, per side.**

- **E0, the incumbent.** eWAR v2 label, `RESOLVED_THROUGH` 2025, no label-definition arm.
  This is the served frame at HEAD on the day of step A.
- **E\*, the full candidate AS BUILT.** Published fWAR, `RESOLVED_THROUGH` 2026, and every
  factor the fixed arm set admits, all on.
- **One LEAVE-ONE-OUT arm per admitted factor:** E\* with exactly that factor reverted to
  its E0 value and everything else left at E\*.

**The factors, split by what an arm of each one actually is.** Part 6 admits six factors and
they are not the same kind of object, so one flat "matrices per side" count would be
executable for five of them and meaningless for the sixth:

| id | Factor | Arm kind | What its leave-one-out compares |
| --- | --- | --- | --- |
| F1 | Basis: published fWAR | matrix arm | the eFV matrices of step F, and every clause (f) item |
| F2 | `RESOLVED_THROUGH` 2025 to 2026 | matrix arm | the same |
| F3 | Arm R, the never-MLB resolution fix | matrix arm | the same |
| F4 | A1, the service-aligned window | matrix arm, admitted only if O7 admits it | the same |
| F5 | A2, the neutral MiLB imputation | matrix arm, admitted only if O7 admits it | the same |
| F6 | F-DEF on the feed's fielding and positional runs | BUNDLE arm, inside step M and downstream of step F | the projections bundle and the served surfaces that read it (`mlb_projections.json`, the Futures board win totals, `lineup_strength`'s `vets[].woba[0]` input). It is NOT an eFV matrix and no matrix is built for it |

**k is NOT frozen at this commit, and this clause says so rather than asserting a count.**
O7, which decides whether A1 and A2 ride, is OPEN at part 3's E1, so F4 and F5 are
undetermined today: the matrix arms are three, four or five, plus the one bundle arm. **The
arm set is FIXED at the moment O7 is answered, and in any case BEFORE the first matrix is
built at step F**, and part 9 records the set with the date it was fixed. The matrix count
is then 2 plus the number of matrix arms, per side. It is a leave-one-out set and never a
factorial: a factorial over m matrix arms is 2^m per side and buys nothing the leave-one-out
set does not buy under the reading registered below.

**The order of operations, because E\*'s definition would otherwise be circular.** E\*
cannot be defined as "every candidate that passes its own clauses", because a candidate's
pass is read from E\* itself. The registered order:

1. Fix the arm set, as above.
2. Build E0, and build the full candidate with every admitted factor ON. That object is
   **E\* AS BUILT**, and every leave-one-out arm is taken against it.
3. Read each candidate's own clauses from `Q(E*) - Q(E* minus f)` against E\* as built.
4. Name the **SHIPPED** configuration: the owner-decision factors (F1, F2 and F6, the last
   under note 7) plus each candidate whose clauses passed at point 3.
5. **E\* as built is not necessarily E\* as shipped.** If they differ, part 9 says so in
   those words and names every factor dropped. A rebuild of the shipped configuration is a
   NEW MEASUREMENT under point 7 below, not a re-labelling of arms already taken.

**The pre-registered reading, fixed before any arm is built.**

1. The attributable effect of factor f on a published quantity Q is
   `effect_f = Q(E*) - Q(E* minus f)`.
2. That is a MAIN EFFECT under an additivity assumption which this design does NOT test.
   The clause says so rather than hiding it.
3. The leave-one-out effects therefore do NOT sum to the total move. The residual
   `Q(E*) - Q(E0) - sum_f effect_f` is COMPUTED AND PUBLISHED, labelled "interaction,
   unattributed". Publishing it is the clause. Making it small is not, and no specification
   is changed to shrink it.
4. Every clause (f) blast-radius item is reported for E0, E\* and each arm (note 5).
5. An arm whose artifact cannot be built, matrix or bundle, is a FAILED ARM. Its factor still ships if it is an
   owner decision and still does not ship if it is a candidate that has not passed, and the
   attribution for that factor is recorded as UNAVAILABLE. It is never inferred from the
   total and never estimated from the other arms.
6. No arm is a ship condition for O1 or O2. The arms exist so that a number which moved can
   be named. They do not re-decide a decision that part 0 says ships regardless of margin.
7. Arms are built in the same run, on the same seed convention and the same folds as E\*.
   An arm rebuilt later on a different frame is not an arm; it is a new measurement and it
   goes to part 9 as one.

### (j) `star_out`, `lineup_strength` and the dark betting columns

**First, a correction this clause carries.** The census sentence "betting has zero WAR
readers" is FALSE and must be deleted wherever it appears (plan X3; runbook step X). Two
dark 5c columns take input from artifacts this epoch rebuilds, and the served Futures board
prices win totals from projected team WAR.

**The three columns, and what actually moves each one.**

- **`star_out` (5c-C, look 2026-10-05, section final at commit 2026-09-16).** It ranks each
  club's top five by `mlb_projections.json` `vets[].warY1Champ`. **The committed 5c-C text
  CORRECTS the plan here and the correction binds this gate:** `warY1Champ` moves at step D
  (the `DEFAULT_PROVIDER` flip) and step E (deleting `fa_corpus.pkl` and `fa_fits_*`), and
  it does NOT move at step M, because `tools/train_proj_models.py --final` trains and saves
  `proj_ml` only while `fa_market` writes the champion's own year 1 into the ML branch. Plan
  section 1.1 and E5 are read as "steps D and E" for this column.
- **`lineup_strength` (5c-B, look 2026-10-05).** It reads `vets[].woba[0]`, which step M
  does move.
- **The 5c-A xwOBA pair (look 2026-09-28)** reads no WAR and no projections input, and step
  M does not touch its inputs.

**Consequences, pre-registered.**

1. **Step M does not run before 2026-10-05**, the later of the two B4 looks. The plan's O11
   default of "not before 2026-09-27" predates the 2026-09-16 revisions that moved both B4
   columns to 2026-10-05, and those revisions supersede it here. If a later owner answer
   moves a look further out, the later date governs; an earlier date never does.
2. **Steps D and E do not run before the last vintage that prices a 5c-C window game has
   been written.** 5c-C's window is QUOTED here rather than summarised, from
   `docs/diamond-betting.md` section 5c-C, "The graded window". A game is in the window
   when: "`lv.as_of(date)` prices it on a vintage dated 2026-09-05 to 2026-10-04 (the newest
   same-season vintage whose `covers_through` is strictly before the game date)"; "it is
   dated before 2026-10-05"; "it is `gameType` R". The conclusion is DERIVED from that,
   not substituted for it: `lv.as_of` prices a game on the newest vintage whose
   `covers_through` is strictly before the game's own date, the last `gameType` R game is
   dated 2026-09-27 (E6), so no window game can be priced on a vintage written after
   2026-09-27, and E6's date already satisfies the constraint. Any D or E landing inside the
   window sends every game priced after it to 5c-C's bucket 2 (post-retrain), which is
   ungraded. That costs graded games and can never add them.
3. **No amendment.** 5c-B and 5c-C are final at their 2026-09-16 commits and their amendment
   cutoff has passed. This gate may not move a 5c criterion, threshold, window, split or
   bucket rule, and does not. It sequences only its own steps around them.
4. **The basis stamp.** 5c-C requires the `star_out` basis string to carry the projections
   bundle's mtime and content hash, the corpus `war_provider`, the champion fit key, the
   oldest and newest roster-cache mtime and the codes counted as out, from the 2026-09-19
   vintage onward, or the vintage is ungraded. Building that stamp is the betting lane's
   item (I9), not this gate's. This gate's obligation is narrower and absolute: the commit
   that carries step D or step E writes the corpus `war_provider` into the projections
   bundle, which carries no such key today, so that the stamp can SEE the basis change. A
   basis change the stamp cannot see is a silent construction change inside a registered
   dark column.
5. **The Futures board** (`proj_export` team WAR into win totals) is a SERVED surface and
   moves with step M during the postseason. It is inside clause (f)'s blast radius and is
   measured there, and O12's one-line changelog is published with it.
6. **Note on the same sitting's betting answers.** The close job on the deploy box is
   SKIPPED by owner decision of 2026-09-17, so there will be no close-price captures this
   season. No clause in this gate reads a price, so nothing here is blocked by it. It is
   named only so that a later reader of part 9 does not look for a price leg that was never
   available, and so that the honest record of that consequence lives in the betting
   documents where it bites, not here.

### (k) The registration that follows this one

The driver re-test is a SEPARATE registration: `docs/efv-<date>/LABEL_V3_DRIVER_RETEST_GATE.md`
(the plan's Z1, section 2). It is committed ALONE with an empty results section, AFTER this
epoch's label is frozen and BEFORE any new-label floor is read. Its blocking preconditions
are P1 (label freeze receipt with per-side coverage and E7 passed), P2 (floors first on the
new matrices, because the eWAR v2 floors adjudicate nothing there), P3 (the A0 parity
check), P4 (input pinning by sha256 at start and end with the nightly idle) and P5 (a
mechanically derived arm list).

This pointer exists so the two cannot be confused. Clause (h) forbids a feature arm inside
this epoch, with the single named exception note 7 records (F-DEF, by the owner's
2026-09-11 answer); (k) is where every other arm goes. No result of Z1 may be recorded in this document,
and no result of this epoch may be recorded in Z1.

Also downstream, each its own registration, none of which changes a label and none of which
rides this epoch: **Z1b** the model-class re-adjudication (its own reopen text names the
label pool, so O2's bundle opens it once), **Z1c** the pitcher-stuff first fold, **Z2** the
WAG baseline refit plus the realized-PIT gate, **Z3** the valuation-chain reconciliation,
**Z4** the eWAR v3 W1.3 departures (display only; a passer reaches the label at the 2027
epoch, which is the next label epoch).

**The honest prior for Z1, recorded here so that this gate cannot be read as promising it:
zero survivors.** The record is 0 of 48 arms and 0 of 177 in the 2026-09-04 families [R2].
The payoff of this program is coherence and a permanent close, not a driver that passes.

### (l) Copy may never claim an accuracy gain from a basis change

Absolute, and it outlives this gate.

**The reason it is a clause and not a preference.** The last basis epoch of this class
MEASURED THIS EXACT QUESTION AND FOUND A NULL. Its clause (d) came back ruled out or
undecided at the registered 0.02 margin, and its own copy contract already said no copy may
call the new basis more accurate. Nothing about a label that moves MORE makes the accuracy
statement available; a bigger definitional move is a bigger definitional move.

1. No served string, glossary entry, methodology page, changelog line, model registry note,
   article, commit message or release note may say that published fWAR makes eFV, the
   projections, WAG, the arbitration model, a farm grade, a surplus dollar figure or a board
   rank more accurate, better calibrated or closer to the truth.
2. The only accuracy statements available are the clause (d) disposition on THIS epoch's
   cells and the standing R3a and R3b record. A cell that comes back UNDECIDED is written as
   undecided; it is not a gain, and it is not rounded into one by omission.
3. The permitted claim is COHERENCE, with its mechanism named in the same sentence: one
   currency across the label, the FanGraphs FV-to-WAR tables, the dollar-per-WAR kernel and
   the displayed number. Where a coherence number falls to zero by construction (part 1),
   the copy says "by construction".
4. MOVEMENT IS NOT ACCURACY. That 34.2% of hitter rows change implied grade, that 288 grades
   move or that a star label flips are measurements of a DEFINITION CHANGE. Copy that
   reports any of them says so in the same sentence, and never presents the movement as
   players having been re-evaluated.
5. The clause is enforced, not merely stated. The copy sweep (step X) and `copy_lint --check` run before `build_site` (step T), and every copy gate that literally asserts a
   basis word is updated in the SAME commit as the served string it asserts on, which is the
   predecessor's clause (g) requirement carried forward.
6. This clause binds the results section of this document too. Part 9 may report what was
   measured and what the disposition was. It may not draw an accuracy conclusion the
   measurement does not support.

## 6. What may ride this epoch, and what may not

This list is FROZEN at this commit. It is what clause (h)'s "Appendix A" means on this epoch
(note 6). A factor that is not on it when the first matrix is built is out of the epoch,
full stop.

**May ride, each with its own ship rule and its own leave-one-out arm under clause (i):**

| Factor | Kind | Ship rule |
| --- | --- | --- |
| Basis: published fWAR, frozen per season | owner decision O1 | ships by decision; measured, never claimed as accuracy |
| `RESOLVED_THROUGH` 2025 to 2026 (with `build_star_odds_artifacts._RESOLVED_THROUGH`) | owner decision O2, the standing clock; clause (h) kind override, note 7 | ships by decision; measured |
| Arm R, the never-MLB resolution fix (203 hitter and 192 pitcher rows labelled a resolved 0.0 at full weight while still playing affiliated ball) | label-definition candidate | ships only if its own clauses pass on its own arm. The window reads as "no affiliated line in either of the two latest seasons with MiLB data on disk at the build" |
| A1 the service-aligned window and A2 the neutral MiLB imputation | label-definition candidates owed by the 2026-09-04 locked decision 1; flags off since then and no arm matrices exist on disk | same rule as Arm R, subject to O7 |
| F-DEF on the feed's fielding and positional runs | projections-only arm, inside step M; clause (h) kind override, note 7 | Gate 1 on the projections bundle (owner answer of 2026-09-11: in the WAR epoch) |

**May NOT ride.** Each of these gets its own later epoch or registration:

- any W1.3 departure of the eWAR v3 replica (display only; Z4);
- any blend lambda move and any correction family (no affine, no dispersion, no band fix
  fitted to make a cell pass) - this is clause (h) and it is unchanged;
- C-7's grade-seam affine;
- the star-odds measured-rates switch (2026-09-03 decision 7);
- BUST2 Arm S;
- any served-feature removal arising from Z1;
- the L1 flooring (O7's recommended refusal);
- the betting decisions of 2026-09-17 (clause (j) point 6).

## 7. The rebuild: each fitted artifact exactly once

`WAR_BASIS_RUNBOOK.md`'s rules are load-bearing and unchanged, with ONE exception, named in
step A's row below: that runbook hardcodes step A's destination to the PREVIOUS epoch's
snapshot directory, and this gate overrides it. Floors come before deltas,
the curve before the anchors, and the retrain before the rebuild passes. There are two
rebuild passes because of the one-run lag, and a third if any stamp is still pre-epoch.
Margins come LAST. One code commit carries the default flip, the epoch bump and the `label=`
fingerprint term. `prospects.db` is written only by step C and by the box's mirror of C.

| Step | What | fWAR-epoch specifics |
| --- | --- | --- |
| A | pre-epoch snapshot | taken at or after HEAD `710f8824` (E8); also snapshot `data/ewar.json` and the frozen fWAR vintage. **Destination `../_pre_epoch_fwar_2026-10/`, NOT the runbook's hardcoded `../_pre_epoch_2026-09/`** (`WAR_BASIS_RUNBOOK.md` lines 42 and 47). That directory exists on disk today holding the 2026-09-04 epoch's evidence: 18 files dated Sep 4, `prospects.db` at 1.77 GB, read from the filesystem on 2026-09-17. The two file lists are not identical, so the runbook's copy would overwrite it in place and leave a directory half one epoch and half the other. Clause (f) diffs every blast-radius statistic against the step A snapshot and clause (i)'s E0 is the served frame on the day of step A, so both would read the mixture. Step A REFUSES if its own destination already exists, and it never writes into `../_pre_epoch_2026-09/`, which is the previous epoch's evidence |
| B | `build_ewar.py` | **SKIPPED.** eWAR v2 retires to a frozen comparison provider, like `bwar` |
| C | rebase `career_war` | to `fwar` through the E3 tool; dry-run receipt first; the incumbent series stays reconstructible (note 2); box mirror |
| D + U | flip `DEFAULT_PROVIDER` to `fwar`; bump `storage.BOARD_RANK_BASIS_EPOCH` from `"2026-09-04"`; move the fingerprint's `label=` term from `ewar_v2@2026-09-03T12:35:09` to `fwar@<vintage id>` | ONE commit. Deploy so D never lands on the box without C: on 2026-09-04 the nightly pre-empted the epoch and wrote a mixed basis. Not before the 5c-C window closes (clause (j) point 2). Writes the corpus `war_provider` into the projections bundle (clause (j) point 4) |
| E | delete `fa_corpus.pkl`, `fa_fits_*`, `proj_ml_frame_*` | keep `.cache/war_daily`. Same date constraint as D |
| F | `efv_dataset.py` and `efv_model.py`, both sides | plus the E0, E\* and leave-one-out arm matrices of clause (i) |
| G | `efv_mde_lab.py mde 2000`; `efv_power_lab.py all 2000` THEN `partb` | the order is load-bearing: `all` erases `partb_floors` |
| H | the epoch lab (a copy of `tools/efv_ewar_label_epoch_lab.py`) | its twin permutes fWAR-minus-eWAR deltas within (season, side); re-run after P |
| I | `tools/fv_outcome_curve_pooled.py` | prior and label in one currency for the first time |
| J | `value_framework.py --fit`, then RE-APPLY the sub-45 knots; capture `prospx_current`; sync `FV_WAR_ANCHORS`; publish k(FV) | `--fit` silently reverts the knots to one 0.19 constant |
| K | `tools/fit_draft_slot_curve.py` | on `fwar`; pre-2011 per O4, and `war_basis: mixed` if the pre-2011 feed is absent |
| L | `tools/war_rate_plus_lab.py` | fix `conventions.war_source` (F-C7-3: the eval still declares bWAR) |
| M | `tools/train_proj_models.py --final` | corpus on `fwar`; the F-DEF arm; four pins move together (schema length, `train_hash`, the ml_config gate, `star_blend` h2 = 0). **Not before 2026-10-05** (clause (j) point 1) |
| N | `python -m tools.build_star_odds_artifacts` | star label on fWAR; refit `star_odds_model`; `_RESOLVED_THROUGH` moves with `efv_dataset`'s |
| O | `run_monthly.py --rebuild-only`, pass 1 | |
| P | `efv_export.py --all --eval` | production output for the golden |
| Q | `source_backtest.py` | the consensus vintage A/B re-scores against its unchanged 0.0068 bar; the C1-C4 confirmatory read, since O2 bundles RT |
| R | `run_monthly.py --rebuild-only`, pass 2 (a third if any stamp is pre-epoch) | |
| S | FA, arb, hitter, starter, bullpen, player and PAL exports | arb spine via `provider=` |
| T | `build_site.py` | after X's copy is in |
| V | golden restamp from P, outside pytest | cause "fWAR label epoch" |
| W | registry rows (the 128 rows naming WAR [R1]) and `tools/gen_audit_docs.py` | the `ewar` row demoted to a comparison provider; the concrete keys are in part 8 |
| X | copy sweep and `copy_lint --check` | 51 artifacts carry 223 bWAR mentions [R1]; `fa_backtest.py:375`; the Clemens `war_basis` key; and the census sentence "betting has zero WAR readers", which clause (j) deletes |
| Y | `tools/run_suite.py --out suite.json`, chunked | never concurrent with a lab |
| Z | margins re-read, then part 9 of this document | Holm across the registered cells |

**The letters name artifacts, not a running order.** They are the runbook's labels and plan
1.5 carries them unchanged, which is why step T sits above step X in the table while step
T's own note reads "after X's copy is in". The execution order of the last block is X, T, V,
W, and that is what clause (l) point 5 requires. A reader running the table top to bottom
would run `build_site` before the copy sweep and would violate clause (l) by following it.

**The box** pulls D + U, backs up its database, runs C, deletes the step E caches and
receives the committed artifacts (the frozen vintage, the pooled curve, the slot curve, the
war_rate evals, the fitted framework, `prospx_current.yaml`, `proj_lgbm`). Its first nightly
then does O through T.

## 8. Registry rows and artifacts this gate creates

- `data/xfv_fwar_label_epoch_eval.json`: the cross-label matrix (b), coverage (c), the TOST
  reading (d), the controls (e), the blast radius (f) and the clause (i) arm table with its
  unattributed residual. Producer: a copy of `tools/efv_ewar_label_epoch_lab.py`, to be
  written by the rebuild wave.
- `data/xfv_fwar_label_epoch_blast.json`: the served artifacts compared against the step A
  snapshot, per arm.
- The frozen per-season fWAR vintage artifact with its `fetched_at` (E3), which the `label=`
  fingerprint term names.
- `data/model_registry.json`, the concrete keys, in the predecessor's form: the eFV rows
  carry `label_basis: fwar` in place of `label_basis: ewar_v2`; the `ewar` row's `consumers`
  moves back to "NONE" and the row becomes a frozen comparison provider, which is what step
  W's demotion writes; a new `fwar` row carries the frozen vintage's id and points at this
  document; `fa_war_paths_decay` carries the step M retrain hash; the `star_odds_model` row
  carries the step N refit. Then `python tools/gen_audit_docs.py` (`MODEL_REGISTRY.md` is
  generated, never edited). Step W's re-read covers the 128 rows that name WAR [R1].
- `storage.BOARD_RANK_BASIS_EPOCH` and `storage.BOARD_BASIS_FINGERPRINT`, moved in the one
  step D + U commit. A fingerprint only guards what it NAMES, which is why the `label=` term
  exists at all.

## 9. Results

**EMPTY AT REGISTRATION.**

No matrix cell, margin, coverage share, control, arm effect, residual, blast-radius number
or disposition has been computed on the published fWAR label at this commit. None may be
written anywhere above this line, and nothing above this line may be edited once anything is
written below it.

The first entry here is dated, names the commit that produced it, and states which
preconditions of part 3 were met when the step ran. Clause (l) binds this section: it
reports what was measured, and it does not draw a conclusion the measurement does not
support.

---

Nothing in this document was measured against an fWAR-labelled fit. Every number above is
either a label-only descriptive taken from the planning lanes of 2026-09-11, tagged with its
lane, or a read of the repository on 2026-09-17, tagged with the file it was read from, with
two exceptions that are named where they appear: the identity lane's running count in E2,
which is an uncounted note and says so, and the previous epoch's snapshot sizes in part 7's
step A, which were read from the filesystem outside the repository on 2026-09-17.
