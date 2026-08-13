# Master plan 2026-08-13: the eFV / consensusFV accuracy program

Written 2026-08-13 on branch `efv-conviction-2026-08-08` (HEAD `e4246475`, ~77 ahead of
origin/main, NOT pushed). Written for Claude Opus 5 to execute. Built from two recon
agents against the live tree (2026-08-12/13) plus the full memory record. Owner ask:
holistically improve consensusFV/eFV accuracy, calibration, and precision; derive more
correlated drivers, especially for pitchers; fix bugs and measurement gaps along the way;
make eFV the most accurate FV grading system there is.

READ FIRST, in order:
1. This document, all of it, before any lane starts.
2. `docs/EFV_GATE_STANDARD.md` (floors, estimator policy, DO-NOT-REOPEN entries).
3. `docs/master-plan-2026-08-12-omnibus4.md` section 15 (banned ledger) and
   `docs/master-plan-2026-08-05-omnibus2.md` section 2 (consolidated bans).
4. `docs/efv-2026-08-12/PITCHER_BAND_CORRECTION_GATE.md` (the FV45 ban and its clauses).
5. Memory files: `execution-2026-08-12-omnibus4`, `execution-2026-08-10-bl6-denoised-baseline`,
   `master-plan-2026-08-08-efv-conviction`, `execution-2026-08-07b-efv-audit`.

---

## 1. Owner decisions LOCKED 2026-08-13 (AskUserQuestion, all answered)

1. **Pitcher lane = DRIVERS + FV45 ATTEMPT.** Full pitcher-driver derivation program
   (2025-fold stuff coverage, retrospective MiLB stuff probe, tool-grade vintages,
   provisional refit) PLUS a gated attempt to close the FV45 band gap via NEW DRIVERS,
   never the banned WAR-map family. Served grades move only on gated wins.
2. **Serve-path bases = RE-MEASURE, UNIFY IF SAFE.** Re-run the odds/dollars re-key
   measurement on the current tree. Unify all four bases in ONE coordinated epoch only if
   proper scores do not resolve against it; otherwise keep the pins and close the honesty
   gap (export the odds grade key, sync all copy).
3. **C-4 = ERA FLOOR AT 2017.** Pre-2017 grade-normalization cells pin to the 2017
   own-year offsets. Flip `GRADE_NORM_AS_OF = True` with the full call-site checklist,
   rebuild matrices, re-read every margin before adjudicating anything.
4. **Scope = ALL FOUR optional lanes**: pitcher provisional serve pack (M6), Phase-3
   leftovers + UI polish, archival infra R5 + registry clocks, betting-adjacent fixes.
5. **Claim frame = STRIP POST-DEBUT, KEEP POOLED.** The site's head-to-head claim
   re-registers on the pooled multi-vintage frame with the 554 post-debut consensus reads
   removed from the pooled served statistic. Floors re-derived on the corrected frame.
   Copy updates to whatever the corrected number honestly supports.
6. **Git = COMMIT PER PHASE + PUSH AFTER GREEN SUITE.** New policy, supersedes the
   commit-local-only precedent: at the end of each wave whose chunked suite is at the
   3-red baseline or better with no unexpected failures, push the branch
   (`git -c http.sslBackend=schannel push`). Durable local commits per phase/gate inside
   waves.

Standing decisions that REMAIN in force from prior programs: dual estimator with E_cond
gates and every claim naming its estimator; zero source weights; the E2a side audit is
WAG-relative (bias vs realized WAR, never vs another source's grade); grades ceil on
display except eFV which rounds nearest; no em-dashes anywhere commit-visible.

---

## 2. Current state (verified against the tree 2026-08-12/13)

### 2a. The model, one paragraph

`efv_dataset` builds labeled + live matrices; `efv_model` holds the feature spec, ridge,
and blend lambda; `efv_score` produces grades/odds/surplus and applies live overlays;
`efv_export.regen_all` writes `data/xfv.json` (field WHITELIST in `_entry`,
`efv_export.py:121-124`: a field not named there never ships). Core:
`xfv_war = clamp(-2, ridge)`, `rank_war = (1-lambda)*cons_war + lambda*xfv_war`,
`xfv_grade = vf.outcome_implied_fv(xfv_war)` (`efv_score.py:1913-1924`). Lambdas PINNED
`{"hit": 0.70, "pit": 0.57}` (`efv_model.py:598`); shifts TOST-RULED-OUT. Hitters carry 14
ridge features, pitchers 9; the `fv` anchor weight is 3.368 (hit) vs 1.708 (pit).
Floor routing serves `efv_ungraded` provisional grades on ~2,434 constant-anchor rows
(`efv_score.py:119,171-182`); `GRADUATE_ROOKIE_WINDOW = True` as of 2026-08-12 (~920
graduates re-anchor on the next rebuild). `SCORED_YEARS` = 2014-2024, 11 folds.

### 2b. Where every published number stands

- **Head-to-head vs consensus: NULL under BOTH estimators** (B-L6, `data/xfv_denoised_baseline_eval.json`):
  delta +0.03138 vs E_cond 0.0327 (0.960x) / E_refit 0.0353 (0.889x). 64% of the recent
  movement was frame drift from our own BA backfill. The precision-weighted baseline
  collapse verdict stands. Site copy already honest ("a margin we still cannot call a win").
- **The margin is frame-dependent** (`EFV_GATE_STANDARD.md:425-446`): pooled multi-vintage
  +0.033 (contains 554 post-debut consensus reads); latest-vintage one-row-per-player is a
  RESOLVABLE LOSS (-0.049, 1.732x); latest pre-debut is a tie (+0.006). Decision 5 fixes
  the frame.
- **All four flagship cuts NULL under both estimators** (`data/xfv_power_eval.json`).
  E_cond floors: hit full_pool 0.0206, pit full_pool 0.0212, hit debuted 0.0209, pit
  debuted 0.0290. Feature-add floors 0.0193 hit / 0.0127 pit pooled-rho.
- **E2a side calibration** (`data/xfv_side_calibration_eval.json`, registered validated):
  at consensus FV55 pitchers realize 4.84 vs hitters 13.41 six-year WAR (gap -8.58
  [-12.69, -4.46]): the industry OVER-grades top pitchers and eFV's low share is the more
  accurate read. At eFV 45 pitchers realize +1.13 [0.19, 2.04] MORE: a real band-local
  under-grade. Per-side WAR forecasts near-unbiased (hit -0.105, pit -0.008).
- **E2b-narrow FV45 correction: NO_SHIP, BANNED** (all three clauses failed; tail MAE
  +29%, the 2026-06-25 failure repeating). Reopen burden: new resolved cohorts, NOT a new
  functional form.
- **consensus.py EXONERATED** (0 of 200 admissible reweightings beat served; denoising
  worth +0.001 rho). Weights stay `{}`. Precision triad identified: sigma FG 3.15 /
  MP 3.00 / BA 4.81 (BA noisiest).
- **BA scored pairwise only** (D3): BA vs FG -0.1006, BA vs MP -0.0722, both resolved, BA
  worse. `SCORED_SOURCES` unchanged `("fangraphs","mlb_pipeline")`. BA scoreable in the
  common set from 2027.
- **consensus_vs_inputs**: Spearman -0.0001 (not resolvable), AUC +0.0108 vs MDE 0.0078
  (the blend wins DISCRIMINATION, not ordering).

### 2c. Open, already-identified defects this program must fix (verified at HEAD)

1. **C-4 leak, machinery built, OFF**: `consensus.py:243` `GRADE_NORM_AS_OF = False`;
   as-of threading exists in `grade_normalization.py` (`:170,:185,:316-317`, guarded,
   pinned by `test_grade_norm_asof.py`). Flip checklist at `consensus.py:206-224` names 5
   other direct `build_remapper` call sites; `surplus_backtest_real.py:133` is binding.
   Residuals documented in `grade_normalization.py:51-83`: within-cycle date-granular
   pooling (10,361 of 30,911 groups) and the pre-2017 exemption (~+3.9 FV at stake).
2. **DEFECT A** `xfv_pred_dispersion` (provisional): predicted WAR over-dispersed, slope
   0.654 hit / 0.587 pit. Repair pre-registered, never shipped.
3. **DEFECT B** `xfv_level_calibration` (provisional): anchor curve too flat, FV40 bias
   -0.883, no knot below FV40.
4. **Bust odds lose to a flat constant pooled** (Brier 0.13224 flat vs 0.14080 pinned)
   while carrying real information (AUC 0.797 vs 0.581): a reliability defect. IDR
   (B-L5) and the Platt wire both already measured NO_SHIP; see lane C-3 for what remains.
5. **Stale eval keys**: `data/xfv_eval.json` + `_pitcher.json` still publish retired
   `rank_win`/`beats_*` keys (21 occurrences each); `efv_model.py:1616-1636` emits the
   replacements. Clears on regen; verify.
6. **`tools/efv_cohort_floor_lab.py::nullcov` one-sided coverage check**: flagged a
   defect by the gate standard (7.4); fix where found.
7. **`_c1_controls` iterates a set**: control tables irreproducible, "must not be quoted"
   (`CONSENSUS_REPAIR.md:395-402`). Fix with sorted iteration.
8. **Name-merged players can carry two points on one date**; `points[-1]` reads one
   arbitrarily (`CONSENSUS_REPAIR.md:451-456`). Deterministic tie-break owed.
9. **2022 in-season FanGraphs board refused and contaminated** (1,288 rows, ~1,272 org
   ranks read as global). Repair = hand-verified per-board override, never a loosened
   `MIN_OFFSET_EXACT_FRAC`.
10. **Registry hygiene**: D3 `pairwise_head_to_head` block unregistered;
    `xfv_side_correction` row has null `last_checked`/`stale` (invisible to the staleness
    checker); revival clocks are prose, not registry rows with owners.
11. **UI honesty nits**: `build_site.py:4962` hardcodes "21 of 25";
    `source_cohort_accuracy.py:530-533` builds a note from the literal "three";
    `assets/site.css:3012` `.sacc-basis-in` has no rule; glossary counts unpinned.
12. **Betting-adjacent** (in scope by decision 4): `pushLine` called from one site
    (`assets/betting.js:779`), dead `/data/betting_clv.json` link rendered before the file
    exists, `.bt-prov` badge has no client test, hash-router comment names 3 dead ids.
13. **ba_tool_grade_weight is SHIP_SOME but was never adversarially verified** (workflow
    died mid-verification). Verify before anything rides it.
14. **t45 / MAE rows never re-measured on the 11-fold basis** (`EFV_GATE_STANDARD.md:79-80`).
15. **Suite baseline is 3 reds until the box rebuild** (golden fingerprint, vet_surplus,
    identity-collision stale-artifact red with a written leave condition).

### 2d. Owner actions owed (blockers tracked, not plannable work)

1. Box crontab install (`deploy/betting-crontab.example`), then
   `python tools/betting_close_job.py --selfcheck`.
2. `python run_monthly.py --rebuild-only` ON THE BOX: clears all 3 baseline reds,
   restamps golden, activates the rookie-window unlock in production.
3. `tools/repair_sabermetrics_stint_rows.py --apply` on the box.

---

## 3. The frame: where power exists, and where the frontier is closed

**The flagship rank frontier is measured closed.** Six programs agree; feature adds,
target changes, objective changes, sample weighting, pooling, regularization, ensembling
are all measured nulls with every resolving cell a loss. A naive feature hunt produces
nulls. Floors are an ESTIMAND problem (refit variance 53-78% of total): more cohorts do
not fix power. Ten of thirteen family cells sit below their own E_refit asymptote.

Power EXISTS in exactly five places, and the plan spends effort in proportion:

| Ground | Why power exists | Lanes |
| --- | --- | --- |
| Consensus input integrity | 4,299 common rows, 4.7x the fold pool; input fixes move the dominant feature AND the baseline | Wave 2 |
| Calibration / distribution chain | proper scores carry far more information per row than one rank correlation; two pre-registered defects already open | Wave 3 |
| The provisional / routed model | block-rho floors clear at 4x; the B5 dumb control is NULL = an unaudited frontier serving ~2,434 rows | Wave 4 (P-6) |
| New data with resolvable labels | the aStuff+ reopen condition is recorded and near; retrospective stuff sources unprobed; tool-grade vintages unpowered-checked | Wave 4 (P-1..P-5) |
| Measurement itself | frame correction, TOST, decidability triage, coverage-gate fix: converts nulls into knowledge at zero power cost | Wave 1 |

**The pitcher ask, reframed honestly (decision 1).** "Hitters are boosted more than
pitchers" is measured and CORRECT behavior at the top: the top-300-band eFV-minus-consensus
is hitters +1.96 / pitchers -0.17 because one shared WAR-to-FV curve spends a real value
difference (industry over-grades top pitchers by 8.58 WAR at FV55). Boosting pitchers
toward consensus at the top would make eFV LESS accurate. The legitimate pitcher upsides
are: (a) the FV45 band under-grade (+1.13 WAR), attackable ONLY via new drivers under the
E2b clauses; (b) new pitcher data with resolvable labels (stuff, tool grades); (c) the
pitcher provisional model, whose grade map is hand-set and whose control battery is open;
(d) within-side discrimination, which grows only with banked data (R5).

---

## 4. Banned ledger (do not re-propose; canonical copies govern)

Canonical: `docs/master-plan-2026-08-12-omnibus4.md:681-701`, omnibus-2 section 2,
`EFV_GATE_STANDARD.md` DO-NOT-REOPENs, `PITCHER_BAND_CORRECTION_GATE.md:130-136`.
Summary for this program's lanes:

- **WAR-recalibration for the FV45 side gap** in ANY functional form (per-side, isotonic,
  linear, whatever). Reopen = new resolved cohorts only. The FV45 attempt in this plan is
  a NEW-DRIVER route and every gate doc must cite this distinction explicitly.
- Cross-source quantile map / OT as the served consensus harmonization map. The
  continuous per-cell offset is the shipped design.
- Blend-lambda shifts (TOST ruled out 0.65/0.60/0.51); the `fv` feature-add (TOST ruled
  out); floor-shopping a third estimator; ECE-only calibration gates; the eFV tail fix;
  peak-WAR training target; ETA feature; consensusRank / Plackett-Luce (J1 NULL/FAIL).
- Consensus source reweighting (reopen only via the 2027 vintage-disciplined A/B beating
  MDE 0.0068). SINGLE_SOURCE_K refit (vindicated null). Recency decay (null; degenerate
  arm 6.8x worse). Drop-off shrink fitting (D-4 dead, zero overlap rows).
- W-PLATOON prospect-eFV platoon features (one-attempt-spent;
  `efv_model.py:456` records the ban). MiLB history backfill (regressed). TJ surgery
  feature (consensus prices it). Surrogate labels both sides (pitcher lane CLOSED with an
  economic bound). Statcast-into-projections blind port. K-prior. Handedness, sb_rate,
  wRC+, gated tool pairs, elite-band conviction, defense/athleticism arms (all closed,
  ledgers in `data/xfv_driver_*.json`).
- IDR/EasyUQ distribution recalibration (B-L5 NO_SHIP on Holm + a real DSC debit); the
  odds Platt wire (null vs the constant on the served population); p_bust re-key (pin
  kept on measurement).
- BA into `SCORED_SOURCES` on the current common-set basis (D3's pairwise view is the
  sanctioned alternative). Widening SCORED_SOURCES also CRASHES
  `source_cohort_accuracy.py:93` (tuple unpack): promotion is never a one-line edit.
- `advancement_pace` outputs into eFV (contractual, `advancement_pace_export.py:3-20`).
- Never sum ML quantile points. Never derive RNG or iteration order from a set/hash.

---

## 5. Wave 0: baseline integrity and fresh frames (serial, before everything)

W0.1 `python tools/run_suite.py` from `prospect-tracker/`. Expect EXACTLY 3 baseline reds
     and "No unexpected failures" (or fewer if the box rebuild has run).
     `test_atomic_artifact_write` is a known load flake: re-run alone before calling it a
     regression.
W0.2 Local `run_monthly.py --rebuild-only` for measurement freshness (~4.2 GB peak; NEVER
     during the nightly box window ~00:30-04:00 local; check `git status data/` and
     artifact mtimes first). This is the FIRST rebuild with `GRADUATE_ROOKIE_WINDOW`, so:
     verify ~920 graduates re-anchor, `xfv_grade_at_debut` + `xfv_rookie_window` reach
     xfv.json, `board_basis_fingerprint` carries `gradanchor=`, epoch reads 2026-08-12.
W0.3 Verify `test_no_new_merged_identity_on_the_active_board` goes green after W0.2's
     artifacts land. If not, the jesus_lopez repair is incomplete: pull its entry from
     `tools/run_suite.py` and repair, do not re-baseline.
W0.4 Verify the stale `rank_win` keys in `data/xfv_eval.json` / `_pitcher.json` were
     replaced by the `efv_model.py:1616-1636` emissions (defect 2c.5). If the regen does
     not clear them, find why the emission never reaches the artifact.
W0.5 RE-READ every margin this plan quotes (head-to-head, power cells, side calibration)
     from the fresh artifacts. The staleness lesson has fired three times: a margin two
     days stale can cross a verdict boundary. Record the fresh numbers in the wave record;
     they are the baseline every later lane compares against.
W0.6 Commit per phase. Suite green at baseline = push (decision 6).

---

## 6. Wave 1: measurement first (cheap, changes what every later gate means)

**M-1 Claim-frame correction (decision 5).** Remove the 554 post-debut consensus reads
from the pooled head-to-head statistic (the receipts table at
`source_backtest._xfv_vs_consensus_detail` already strips them; the pooled number does
not). Re-derive BOTH estimators' floors on the corrected frame in the SAME RUN at the same
B and seeds as the corrected delta (never mix vintages of floor and delta). Update
`XFV_HEADTOHEAD_MDE95` and the pooled numbers wherever artifact-driven; site copy is
already conditional, verify it renders the corrected values. Pre-register expectations:
stripping post-debut reads should REDUCE the margin (those reads let consensus see the
answer); if it instead grows, investigate before publishing. Registry row + gate doc.

**M-2 Coverage-gate fix.** `tools/efv_cohort_floor_lab.py::nullcov` becomes two-sided
(over-coverage fails like under-coverage). Re-run the lab's own validation after.

**M-3 11-fold t45/MAE re-measurement.** The retired 4-fold t45 and MAE rows have never
been re-measured on the 11-fold basis. Measure, publish, floor them (they are cited in
copy and in the scoreboard).

**M-4 Decidability triage + clocks as registry rows.** Publish the triage table: for each
family cell, its E_cond resolution year (2028-2283 range exists today); cells whose
asymptote can never resolve are RETIRED from the scoreboard with their reason. Convert
every revival clock into a registry row with an owner and a condition: aStuff+/whiff
(P-1's condition), BA risk (2027), BA common-set (2027), MiLB-Statcast vintages (2028-29),
consensus reweight A/B (2027), IL history (~2028).

**M-5 Alpha-spending declaration.** One paragraph in the gate standard: declared maximum
information per statistic family, Lan-DeMets spending for repeated looks. This program
re-reads the same margins repeatedly; the declaration is what keeps that honest.

**M-6 Hygiene batch.** Register the D3 pairwise block (registry row naming
`source_backtest.json` as its artifact); fix `xfv_side_correction` null
`last_checked`/`stale`; fix `_c1_controls` set iteration (2c.7); per-year offset drift
monitor (FG-MP offset by year, SE ~0.36 FV/yr) as a small standing artifact + test.

Adversarial verify the wave; suite; commit; push if green.

---

## 7. Wave 2: consensus input integrity (the baseline mover; run BEFORE driver work)

Everything here moves eFV's dominant feature AND the baseline eFV must beat, which is why
this wave precedes all driver gates. After W2 ships: rebuild matrices, re-read every
margin again (same discipline as W0.5), and only then open Wave 3/4 gates.

**A-1 C-4 flip with the 2017 era floor (decision 3).**
- Implement the era floor in `grade_normalization`: for as-of years < 2017, serve the
  2017 own-year offset for that (source, role) instead of returning None or pooling.
  No future data relative to 2017 enters a pre-2017 cell beyond that pin, and the pin is
  DISCLOSED in the artifact (a 2015 point is normalized on 2017 evidence; that is the
  accepted cost, chosen over a discontinuity).
- Flip `consensus.GRADE_NORM_AS_OF = True`. Execute the WHOLE checklist at
  `consensus.py:206-224`: every direct `build_remapper` call site moves to the capped
  basis in the same commit (binding: `surplus_backtest_real.py:133`;
  `tools/consensus_gate_lab.py:73-139` carries its own uncapped re-implementation, update
  or quarantine it).
- Gate: as-of violations 0 post-flip; measure how many normalized units changed and the
  eFV matrix delta (the 08-08 estimate was 58.12% of rows, mean +0.94 FV; re-measure, do
  not quote). Rebuild matrices; re-derive floors + margins; report the eFV margin delta as
  a FINDING (the baseline moved, so the margin moving is expected, not a regression).
- Blast radius report: grades, ranks, dollars moved on the live board; movement engine
  protected by epoch/fingerprint discipline if served consensus values shift.

**A-2 Within-cycle date-granular pooling.** Measure the residual (how many served points
ride a cell pooled across dates within a cycle, and the FV delta). Ship the date-granular
cap only if material; otherwise record measured-immaterial with the number.

**A-3 2022 FG board override.** Hand-verified per-board override marking the 2022
in-season board's rank column as org-scope (the value-level detector output is the
evidence; the canary pair from 2026-08-07 documents the method). Never loosen
`MIN_OFFSET_EXACT_FRAC`. Measure: rows re-admitted, consensus deltas, eFV matrix effect.

**A-4 Identity + org integrity batch.**
- Work the 12 OPEN pairs in `test_identity_collisions.KNOWN_MERGED_INACTIVE` per their
  written leave-conditions (repair or explicitly re-document).
- `players.org` canonicalization: 1,144 non-canonical values (1,033 "Office of the
  Commissioner", OAK->ATH, CWS/CHW, TAM/TBR, ~25 affiliate names) reaching 3,786 snapshot
  rows. Canonicalize via mapping at READ seams first (no blind DB rewrite); DB repair as
  its own reviewed script.
- Fix the name-merged duplicate-points-per-date defect (2c.8) with a deterministic
  tie-break (latest source timestamp, then source name), pinned by test.

**A-5 BA risk into the bust chain (power-check FIRST).** BA's resolvable outcome rows sit
in ONE base year (2023, ~750 rows). Compute the MDE for a risk-ordinal term in
`p_bust`/bucket calibration BEFORE building anything. If the MDE swamps the plausible
effect: wire the feature DARK (computed, logged, not served), record "underpowered until
<year>" in the registry clock, done. If powered: forward-chained gate under the proper-
score rules of Wave 3.

**A-6 BA tool votes + verification debt.** FIRST adversarially verify
`ba_tool_grade_weight` (SHIP_SOME shipped unverified; mutation-prove its tests). Then
re-run the tool gate with BA votes included (the 103 `_extras.ba_tool_variants` rows are
already ingested). Equal weight retains unless the gate says otherwise.

**A-7 C-3 org-rank detector decision pack.** The detector (`consensus_org_rank_split`,
C-3) defaults OFF; enabling moves 838 live grades. Gate it (does enabling improve the
consensus against outcomes / reduce known contamination?), produce the blast-radius table,
and bring the enable decision to the owner mid-program via AskUserQuestion.

**A-8 TJStats tool grids (bounded probe).** `tjstats_snapshots` (5,202 rows) carries
tools_json no consumer reads. Power-check as additional tool-consensus votes only (never
FV votes beyond what already votes); expect small; TOST to RULED OUT if null.

Adversarial verify; rebuild; re-read margins; suite; commit; push if green.

---

## 8. Wave 3: calibration and distribution (proper-score ground)

Run after Wave 2's rebuild so calibration fits sit on the corrected consensus basis.
All gates here use proper scores (RPS/Brier/log loss) WITH a Murphy decomposition;
a gate that a constant can pass is void (the C2 lesson: pooled ECE admits a constant at
152.7% of gain). Tail-MAE clauses mandatory on anything touching the WAR scale.

**C-1 DEFECT A: predicted-WAR over-dispersion (slope 0.654 hit / 0.587 pit).** Execute
its own pre-registration (registry `xfv_pred_dispersion`). The repair must be monotone
(rank-invariant) and gated on: calibration slope toward 1 on held-out folds, overall MAE
not worse, TAIL MAE not worse (the E2b clause-3 discipline, cited in the gate doc), and
the 2026-07-29 zero-info-twin standard (the hitter arm survived its twin then; re-run
both arms fresh). If the pitcher arm again fails its twin, ship hitter-only or nothing.
Downstream: dollars ride the display grade, so verify surplus byte-neutrality or gate the
dollar move explicitly with a blast radius.

**C-2 DEFECT B: flat low-end anchor (FV40 bias -0.883, no knot below 40).** Extends the
2026-07-29 sub-45 empirical anchors ship. Fit knots below FV40 on `target_censored` with
player-clustered CIs; keep the 45+ region untouched (its cells failed sign tests before);
verify which consumers move (`ctrl_war` yes; served dollars should not: prove
byte-neutrality like the sub-45 ship did, or gate).

**C-3 Bust-odds reliability (the constant defect).** The lawful remaining family after
the bans: per-side, bust-cutpoint-only reliability correction gated on proper score +
resolution, with Venn-Abers INTERVALS for the sparse cells (FV60 star: 10-25 events), fit
out-of-fold. The gate doc MUST cite its distinction from: IDR/EasyUQ (banned, B-L5), the
Platt wire (measured null vs constant on served population), and p_bust re-key (pin
kept). Pre-register the honest possibility that NO lawful family remains: if the gate
returns null vs the constant again, the finding ships as knowledge (the odds copy then
must disclose "bust odds are informative but not reliability-calibrated"), and the lane
closes with a TOST bound.

**C-4 Interval-censored partial identification.** Many censored rows are ALREADY
bucket-determined (their partial WAR already pins the outcome bucket). Use the
determination to tighten the distribution eval and the reliability tables at zero
modeling cost. Direct measurement, no serve change.

**C-5 One-defect hypothesis test.** Recompute the within-cohort elite-tier slope on
complete-window rows only. If the elite under-dispersion vanishes there, the censoring
projection and the elite-tier calibration gap are ONE defect and C-1/C-2 should be
re-scoped before shipping; if not, they are independent. Cheap, informative, run BEFORE
C-1 ships.

**C-6 Served-population honesty gate.** Kish ESS on the served board is ~19% (the DSL
third rests on ~55 labeled rows). Implement the refusal rule: no pooled served-population
accuracy claim when ESS/n < 0.25; publish strata instead. Check whether any current page
copy violates it.

Adversarial verify; suite; commit; push if green.

---

## 9. Wave 4: the pitcher driver program + FV45 attempt + provisional frontier

Order inside the wave: P-0 coverage census -> P-1/P-2/P-3/P-4 probes and power checks ->
P-5 FV45 attempt (only with a surviving new driver) -> P-6 provisional refit + serve pack
-> P-7 inert-column battery. Hitter drivers are NOT hunted (closed frontier); hitters
move only via Waves 2/3 upstream fixes.

**P-0 Coverage census (one script, read-only).** For every candidate pitcher data source,
count PRE-DECISION coverage on resolved pitcher rows per fold: aStuff+/SC+ (AAA 2023+),
prospecttilt (probe in P-2), Pipeline vintage tool grades 2015-2021, BA tool grades
2023+, PAL arsenal/velocity, `pitch_arsenals` (2026 only), swing/bat-tracking (hitters,
2026 only, census only for the record). The census is the power-check-before-fit
artifact every later lane cites. No model code touched.

**P-1 The 2025-fold frame extension (the recorded stuff-feature reopen).**
`data/xfv_pitcher_stuff_eval.json` records its own reopen condition: the first fold with
nonzero TRAIN coverage for AAA stuff/whiff features is TEST YEAR 2025, once 2024+ debut
cohorts are in the matrix. This is a FRAME CHANGE, not a quiet edit:
- Pre-register frame-v2: `SCORED_YEARS` extended to 2025 (censoring-aware labels; 2025
  debuts carry 1-2 observed seasons under the flat-rate label, which is measured optimal).
- The leak-guard cutoff pins (`test_efv_export.py:718,735`) exist to stop silent frame
  drift; they move ONLY inside the pre-registered frame-v2 commit, with the old frame
  kept runnable side by side for the transition.
- Re-derive ALL floors on frame-v2 in the same run (B-L6 discipline). Publish frame-v1
  and frame-v2 numbers side by side in the gate doc; adjudicate stuff features ONLY on
  frame-v2 with its own floors.
- Then: if P-0 shows nonzero train coverage, gate `stuff_z`/whiff features forward-
  chained. Expected honest outcome range: one fold of coverage is thin; a null with a
  TOST bound is a fine first result and starts the clock (2027 adds a second fold).

**P-2 prospecttilt retrospective probe.** `api.prospecttilt.com/*.json` bulk (verified
live 2026-07-24, B-ranked; robots clean, unlike the rejected sources: do not re-probe
those). The prize is `graduates.json` RETROSPECTIVE MiLB Stuff+/Filth+ for graduated
pitchers: if it carries pre-debut stuff for 2019-2024 debut cohorts, that is the first
trainable stuff feature with resolved labels. Probe: fetch, join via mlbam, count
pre-decision coverage on resolved pitcher rows. Pre-register the build floor BEFORE
looking (>= 150 resolved pitcher rows with strictly pre-decision stamps); below it,
record + clock. Above it: as-of discipline (their snapshot dates govern), one gated
forward-chained feature arm. Third-party model values: cache raw payloads under
`data/sources/samples/` and treat vintage stamps skeptically (verify a graduate's stuff
row predates his debut using two independent fields before trusting the file).

**P-3 Pipeline vintage tool grades (2015-2021).** `data/pipeline_vintages.json` carries
20-80 FB/CB/SL/CH/Control for top-100 vintages 2015-2021: exactly the pre-debut window of
resolved 2017-2023 cohorts, but top-100-only (thin). Power-check on the P-0 census; if
MDE swamps, record + clock; else one gated arm (pitcher tool features beyond `tool_fb`,
e.g. secondary-pitch max, control grade). Note the known cross-outlet tool-scale offsets
(MP runs hot on every tool): normalize within-source before use.

**P-4 BA pitcher tool grades.** 2023+ only, so resolved coverage is nearly nil today;
power-check, expect "underpowered until 2027+", wire nothing, set the clock. (BA tool
consensus votes are Wave 2 A-6's business; this item is about eFV FEATURES.)

**P-5 The FV45-band attempt (decision 1, the gated half).** Runs ONLY if P-1/P-2/P-3
produced at least one surviving or near-surviving pitcher driver, OR a band-local
information source exists that the model demonstrably does not carry (candidates strictly
from NEW information: stuff residual vs band peers, PAL arsenal-depth for the 40-45 band,
prospecttilt retrospective). Pre-registered gate BEFORE any fit, citing the E2b ban and
its distinction (new information vs new functional form), with E2b's three clauses
verbatim as hard ship conditions:
  1. the FV45 band gap improvement CI must EXCLUDE zero (a point estimate landing on
     zero is not evidence),
  2. overall per-side MAE not worse,
  3. TAIL MAE not worse (the clause that caught the 2026-06-25 failure twice).
Forward-chained, 13 folds, both estimators, Holm across the attempts. If nothing
survives: the band stays published knowledge, and the plan records which data source the
2027 cohort maturation makes decisive.

**P-6 Provisional model refit + pitcher serve pack (decision 4a).** The largest served
population on the least-validated map: ~2,434 routed rows through the hand-set
`_GRADE_MAP` (hit 27/3.8/43/49, pit 25/4.5/34/38; `efv_ungraded.py:107-115`), with the
flagship/provisional maps disagreeing -7 FV at WAR 0 and +11..+12 through 0.5-1.5
(`efv_score.py:93-94`).
- Refit the grade map on `target_censored` under the gate standard (respecting the
  2026-07-30 NO-SHIP lessons: an outcome-map re-point deletes the org-filler ladder;
  whatever ships must preserve a defensible sub-30 mass, stated as a design constraint,
  and any FV-denominated knee/cap must be re-derived as WAR-denominated first).
- Run the beat-the-dumb-control battery (B5 `level_rank`-only control is currently NULL
  at 0.921x: the model must beat it or the routing claim weakens).
- Importance-reweight the eval to the SERVED mix (served is 34.7% DSL / 10.9% AA; the
  labeled pool is 2.5% DSL / 34.1% AA). Publish both weighted and unweighted.
- Deliver the pitcher provisional SERVE decision pack (M6) to the owner: current pit
  provisional estimates disagree across estimators (0.854x refit / 1.312x conditional);
  the pack presents fresh both-estimator evidence + blast radius, owner decides serve.
- If the refit ships, resolve the flagship/provisional seam disagreement in the same
  epoch and add the provisional-scale term to `BOARD_BASIS_FINGERPRINT` (registered gap).

**P-7 Inert-column battery (bounded, one pass).** The pitcher matrix already emits
`starter_shape`, `arsenal_depth`, `relief_flag`, `tool_cmd/sl/ch/cb` at zero coefficient.
One battery on the post-Wave-2 baseline against feature-add floors (0.0127 pooled /
0.0182 block), TOST bounds on the nulls so each closes as RULED OUT rather than
unresolved. Do not add on sub-floor evidence; do not remove on sub-floor evidence.

Adversarial verify; suite; commit; push if green.

---

## 10. Wave 5: serve-path coherence (decision 2)

**S-1 Re-measure the re-key on the current tree.** Odds leg: p_bust/p_bucket keyed on
`_odds_grade` (retired `realized_implied_fv`) vs re-keyed on the served grade; per-side
Brier/log loss, cluster bootstrap, Murphy decomposition (the 07-30 result was
level-not-calibration; check that shape again post rookie-window + BA backfill). Dollar
leg: quantile-display pricing vs served-grade pricing on the forward-chained frame (NEVER
on the scored artifact: `efv_score.run()` fits calibration on the rows it scores, so
in-sample comparisons invert OOS; the 2026-07-29 dollar-basis trap).

**S-2 If proper scores do NOT resolve against unification: ship it in ONE epoch.**
Board, odds, dollars, history on the served grade. One coordinated commit: epoch bump +
fingerprint terms (any new basis fact gets NAMED in the fingerprint; three prior
incidents prove an unnamed term guards nothing), `prospx_current` re-capture INSIDE
`with vf.valuation_set("prospx_current")`, PINNED_MIX band check, copy sync
(`efv_export.meta.grade_scale`, glossary `xfv`, methodology page), golden restamp note.

**S-3 If the measurement resolves against: keep the pins, close the honesty gap.**
Export `xfv_grade_odds` through the `_entry` whitelist; methodology page documents the
bases; tests pin the export and the copy. Either branch ends the "nothing in xfv.json
identifies the odds grade" defect.

**S-4** `BOARD_BASIS_FINGERPRINT` names the provisional scale (if not already done in
P-6). **S-5** Re-audit: after this wave, count the distinct live grade bases and publish
the number on the methodology page; the target is 1 (unified) or an explicitly documented
2 (pinned odds), never a silent 3+.

Adversarial verify; suite; commit; push if green.

---

## 11. Wave 6: archival infra, hygiene, UI/UX polish, betting-adjacent fixes

**I-1 R5 archival (decision 4c).** Monthly dated dumps of the refetch-clobbered tables:
`statcast_metrics`, `zone_metrics`, `pitch_arsenals`, plus the swing/bat-tracking caches.
Dump the DB-summarized rows (NOT the 14.7 GB raw cache), dated directories, wired into
run_monthly fail-soft behind an env gate, excluded from deploy. This is what makes the
2028-29 vintage clocks real instead of aspirational. Verify `metric_snapshots` accrual
health (204,333 rows, daily) while there.

**I-2 UI/UX + honesty polish (decision 4b).**
- Derive `build_site.py:4962`'s "21 of 25" from the artifact; same for
  `source_cohort_accuracy.py:530-533`'s literal "three"; pin with tests.
- `.sacc-basis-in` gets a rule or the class dies.
- Glossary source-accuracy + accuracy pages: verify every number is artifact-driven after
  M-1's frame correction; the three-valued scoreboard stays; frame disclosure sentence
  added.
- Explainer/factors audit: `_EXPLAINER_SKIP` currently hides `fv`/cohort dummies; verify
  the surfaced factors match the fitted model post-Wave-4 (stale factor labels have
  shipped before).
- Sweep this program's new copy through `tools/copy_lint.py` (no em-dashes, ban list;
  watch baseball-term collisions).
- General pass over eFV-touching module pages (prospx board/detail, glossary, accuracy,
  methodology) for defects found along the way; fix small, gate anything that moves a
  grade/rank/dollar.

**I-3 Betting-adjacent fixes (decision 4d).** `pushLine` disclosure at every consumer or
document why one call site suffices; gate the `/data/betting_clv.json` link on file
existence; `.bt-prov` badge client test; fix the hash-router comment. Nothing else
betting-side in this program.

**I-4 Registry + docs close-out.** `gen_audit_docs.py` after every registry edit
(indent=1 discipline); every new eval artifact registered with a MODEL_GLOSSARY decision;
loss ledgers `deprecated`, measured-not-adopted `provisional`, `unvalidated` carries NO
artifact. Final wave record in `docs/efv-2026-08-13/`.

Final: full chunked suite, expect baseline or better; commit; push (decision 6).

---

## 12. Verification protocol (non-negotiable; this is where past programs earned or lost their results)

1. **Adversarial verification on EVERY lane.** Historical base rate: 12 of 24 lane
   headlines died under verification; the arithmetic usually held, the INTERPRETATION
   failed. A lane headline is not shippable until its verifier passes it. Never commit on
   a headline before verification (the -$0.117M incident).
2. **Pre-register before building.** Gate doc first, PASS clauses + literal result
   placeholders, committed alone with an empty Results section so git timestamps it.
   Any threshold added mid-lane that flips a verdict is disclosed in the headline.
3. **Mutation-prove every new test.** Two vacuous tests were caught in one session alone
   (a test matching a field name in a comment; a replayed-board test that dedupe made
   blind). A guard is only as good as its mutation run; verifiers report the table.
4. **Estimator + floor on every claim.** Two-sided coverage checks. Never mix a stale
   floor with a fresh delta: re-derive the incumbent in the same run at the same B and
   seeds. Holm across a lane's multiple cells. TOST (delta = 0.02) to convert nulls into
   RULED OUT wherever a bound closes a question.
5. **Vacuous-PASS audit.** Known classes: inspecting an empty set, f(X)==f(X), a control
   computed from the arm that cannot fail, an i.i.d.-guaranteed property, `... or True`.
6. **Controls that decide, not decorate.** Zero-information twins, permutation nulls,
   rank-identical level twins for any label/score claim. A gain a shuffled control
   reproduces is not a gain.
7. **Suite discipline.** No lane runs pytest EVER (conftest git-checkouts dirtied files;
   concurrent edits get destroyed). The orchestrator runs `tools/run_suite.py` serially
   between waves, keys on RETURN CODES, expects the 3-red baseline pre-box-rebuild.
   Crashed chunks report {} counts: read codes, not totals. Degraded-machine reds move
   between runs; verify targeted, re-run fresh.
8. **Data discipline.** No DB writes by lanes; no live ingests mid-audit; revert data/
   churn per wave EXCEPT artifacts that follow a shipped code change; matrices are
   gitignored (safe to rebuild), evals are tracked. Nightly box pipeline rewrites
   artifacts ~00:30-04:00: check `git status data/` + mtimes before diagnosing any red.
9. **Git discipline.** Commit explicit paths, never `git add -A` (check
   `.claude/worktrees/` for nested repo copies first). Commit per phase; push only on a
   green-baseline suite (decision 6) with `-c http.sslBackend=schannel`.
10. **Ship discipline.** A fix that is correct in isolation is out of scope if it moves a
    grade, rank, or dollar without its own gate. Fingerprints name every basis fact they
    guard; epoch bumps and restamps travel together. `prospx_current` re-captures run
    inside the valuation_set context. Anything contradicting a LOCKED owner decision is
    REFERRED BACK with evidence, not shipped (the E2a precedent).
11. **Environment.** PowerShell mangles `python -c`: use script files in the scratchpad.
    Windows paths for python; matrices ~GBs; the rebuild is the one monolithic multi-GB
    process. Agents get explicit no-DB-write, no-pytest, read-only-recon briefs.

---

## 13. In-flight owner decision queue (expected AskUserQuestion moments)

1. C-3 org-rank detector enable (838 live grades move) after its Wave-2 gate.
2. Pitcher provisional SERVE decision (M6 pack) after P-6.
3. FV45 driver ship if a P-5 candidate clears all three clauses (blast-radius table).
4. Serve-path unify vs keep-pins after S-1's evidence (only if the measurement is
   ambiguous; a clean read executes decision 2 directly).
5. Any BA-risk / tool-vote ship that moves served grades (A-5/A-6).
6. Anything that contradicts a locked decision: referred back with evidence.

## 14. Definition of done

- Every lane above executed, gated, adversarially verified, or explicitly recorded as
  measured-null/underpowered with a TOST bound and a registry clock.
- Fresh floors + margins on the corrected claim frame; site accuracy copy artifact-driven
  and honest under the corrected numbers.
- C-4 flipped with the era floor; consensus integrity batch shipped; matrices rebuilt on
  the corrected basis.
- Defects A and B adjudicated (shipped or refuted by their own gates); bust-odds
  reliability adjudicated; interval-censoring tightening shipped.
- Pitcher program: coverage census published; frame-v2 adjudicated; every probe either
  built+gated or clocked; FV45 attempt run or explicitly blocked-for-data; provisional
  refit adjudicated + serve pack delivered.
- Serve-path bases counted, unified or pinned+exported, copy synced.
- R5 archival running; revival clocks are registry rows; registry/docs/copy gates green.
- Suite at 3-red baseline or better after every wave, no unexpected failures, branch
  pushed per decision 6.
