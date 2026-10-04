# Master plan 2026-08-19: holistic model audit, calibration, and glossary program

PLAN ONLY. Written 2026-08-19 at HEAD 7bd18304 (== origin/main == origin/efv-conviction-2026-08-08,
0 ahead / 0 behind). Built from a 10-agent read-only census workflow over the live tree
(registry, evals, glossary, Diamond, Arkmetrics, FA, closed lanes, unnamed models, state, plus an
adversarial completeness critic), cross-checked against the execution memory back to 2026-06-11.
Owner ask: holistically audit, test, and improve/calibrate/measure ALL models and metrics
(eFV, consensusFV, FA projections, Arkmetrics, Diamond, and everything unnamed), and improve the
glossary to show where our models beat industry models in mathematical and economic language that a
casual reader can follow, with no LLM copy patterns.

## 0. The one drafting rule this plan is built on

Two of the nine census agents transcribed numbers wrong in opposite directions (one quoted figures
absent from artifacts, one quoted registry prose the artifacts have outrun). The evals, glossary,
diamond, and fa censuses verified clean on every spot check. Therefore: **artifacts are the single
source of truth for every number in this plan and in every lane it spawns.** Registry prose,
memory files, and census text are location hints only. This same rule becomes a shipped test in
W1 (claims-freshness), so it holds for future sessions too.

## 1. State pin (verified 2026-08-19)

- HEAD 7bd18304 pushed; local `main` is stale (behind 138), branch from HEAD.
- Working tree: 83 dirty paths, ALL standing regeneration churn (74 data/, registry counters,
  8 stamped hand pages + sitemap). Zero source files modified. One untracked file:
  `data/card_market_eval.json` (2026-08-18), already referenced by the modified
  `data/model_registry.json`. Do not interpret churn as uncommitted work.
- Suite ledger `tools/run_suite.py` still declares THREE baseline reds; the identity-collisions
  entry's leave condition is now satisfied on disk (positions_played.json regenerated 2026-08-16,
  invalidated_by gone), so the true expectation is TWO reds (xfv_golden_fingerprint, vet_surplus),
  both clearing only on a box rebuild_only.
- Registry: 262 rows (51 validated / 98 provisional / 33 unvalidated / 80 deprecated),
  validate() CLEAN. 33 rows behind 28 undated artifacts (unchanged since 08-14). Zero stale rows;
  a seven-row 2026-06-11 block crosses the 90-day line ~2026-09-09.
- RESOLVED_THROUGH = 2025 (efv_dataset.py:269). The 2026 advance is a calendar event (early 2027)
  that admits the 2025 cohort, opens the first pitcher-stuff fold, and makes the aStuff+ gate
  runnable. Shadow copy at tools/build_star_odds_artifacts.py:27 must move in the same commit.
- Standing owner/box actions (external dependencies, not plan work): close cron install,
  EEPHUS_PROPS_CREDITS=120 on the box, box rebuild_only, Supabase go-live + /auth/ route,
  Will's SDR data drop.

## 2. DO-NOT-REOPEN checklist (carry into every lane prompt verbatim)

The reopen standard is omnibus-2 section 2 (docs/master-plan-2026-08-05-omnibus2.md:84-143):
"the burden to reopen is a NEW data source or a NEW owner instruction, not a hunch."

eFV / consensus:
1. (Rewritten 2026-10-04; the original text read "Feature frontier CLOSED: 39 gated arms (D-1 free
   keys + D-2 _extras), zero survivors. No new functional forms over existing columns. Reopen = new
   LABELS (RESOLVED_THROUGH 2026).") Feature frontier RE-CLOSED on label build
   `fwar@2026-10-02-0341299c20ec`, 2026-10-04. The new-label reopen was spent once, by the Z1 driver
   re-test (docs/efv-2026-10-03/LABEL_V3_DRIVER_RETEST_GATE.md, Results): 312 arms in five
   families read once on the fWAR label at RESOLVED_THROUGH 2026, zero survivors, the `fv`
   liveness control live on both sides. No new functional forms over existing columns. Kill rule 6
   of that registration, verbatim: "**Program close.** If nothing passes, record the frontier as
   RE-CLOSED on label build X, rewrite do-not-reopen items 1, 8 and 17 with the date, and allow no
   driver re-test until either the 2027 RT advance or an owner-registered label DEFINITION change
   that moves the debuted label more than this one did (Spearman under 0.99 against the frozen
   label on either side)." Reopen = the 2027 RT advance or such an owner-registered label
   definition change, nothing else.
2. Serve-basis question collapsed to ridge-vs-blend; hitter gap RULED OUT by TOST; pitcher cell
   UNDECIDED and reading the A4 arm is floor-shopping, banned by name. The rank_war-grade remedy
   is recorded but NOT authorized (full grade-basis epoch if ever proposed).
3. AUC leg NULL on every admissible cell; full-pool AUC INADMISSIBLE (EFV_GATE_STANDARD.md:121-144).
   Copy may say indistinguishable on discrimination; may NOT say eFV discriminates better.
4. Blend lambda pinned (hit 0.70 / pit 0.57); all shifts RULED OUT by TOST; any correction routed
   through rank_war is a lambda change and is banned.
5. Correction families exhausted: dispersion repair REVERTED to identity (C-7, test-pinned across
   four call sites); tail-preserving refit NO_SHIP all five families; side-correction NO_SHIP
   (tail MAE +29%); no sixth family.
6. Distribution lanes: xfv_dist_recalibration NO_SHIP, label replacement NULL (all five gates),
   isotonic/grade_recal/joint_map/topquant all rejected on the record.
7. Consensus weighting FLAT since 2026-07-25 (both A/Bs ship=false as of 2026-08-18); reopen only
   via the vintage A/B with gain > 0.0068 MDE on BOTH legs. Recency decay NULL. Single-source
   shrink constant vindicated. BA stays OUT of SCORED_SOURCES.
8. (Rewritten 2026-10-04; the original text read "Pitcher stuff waits for the RESOLVED_THROUGH
   clock; pre-Statcast proxies (sits/tops/rpm) all negative and closed. K-prior closed
   PERMANENTLY.") 8a: pitcher stuff opens by its own clock in its own registration (Z1c,
   docs/efv-2026-10-03/Z1C_PITCHER_STUFF_GATE.md), not in Z1. 8b: the pre-Statcast proxies
   (`sits_mid`, `tops`, `rpm_fb`) were re-read once in Z1's P-MECH family on the fWAR label (13 arms,
   alpha 0.015), zero survivors: RE-CLOSED on label build `fwar@2026-10-02-0341299c20ec`,
   2026-10-04, under kill rule 6 as quoted in item 1. 8c: K-prior closed PERMANENTLY.
9. Hardcoded accuracy claims are a banned defect class; every accuracy claim derives from an
   artifact (test_dispersion_epoch ratchet, Diamond scaffold test).

FA:
10. AAV_CONSISTENT and reprice both refuted twice; AAV stays derived. BAND_SCALE_GUAR twice-null,
    fenced. ML paths as market inputs failed Gate 2; use_ml=False pins stay. Any new recal form
    must repeat the E5a overshoot check. Slope recal forms refuted twice; only the
    intercept/level family is open.

Diamond:
11. SERVE_PROB_CALIBRATION False (Platt failed 3/3 vintage splits; ledger arm needs 100 settled
    games, has ~49). SERVE_RUN_DISPERSION False (gate INDETERMINATE; runline/total excluded from
    slots and record via market_is_publishable; paper ledger deliberately NOT excluded).
12. Market blend: optimum on the w=1 boundary; revisit only at 150+ ledger games.
13. Market gate constants owner-signed 2026-08-18: NOT tunable.
14. Dynasty weight re-derivation measured WORSE (98 inversions); weights are stated conventions.
15. Closer share model RED; saves-only variant ships only via a fresh registration on unscored
    windows. Card scraping UA spoofing banned; module frozen pending a licensed source.

Other:
16. (Rewritten 2026-09-11; the original text read "eWAR site-basis flip REFUSED (loses team-wins
    gate permanently); D5 is an owner checkpoint; dollars stay bWAR-anchored".) The eWAR basis
    flip is SUPERSEDED by owner decision: eWAR primary on 2026-09-03, FanGraphs WAR as the frame
    on 2026-09-09. The label source for fitted consumers is decision O1 of docs/master-plan-
    2026-09-11-war-epoch-drivers-betting.md. The OAA/rfield grid still reopens ONLY through SDR
    gate G-B; SDR gates G-A/G-B/G-C are frozen and data-blocked, run only after a drop passes
    sdr_intake --validate.
17. (Rewritten 2026-10-04; the original text read "Defense-into-eFV closed (four refutations);
    reopen = the eWAR label change (D5/W4), one registered attempt.") Defense-into-eFV CLOSED
    PERMANENTLY on existing columns, 2026-10-04: the one registered attempt was Z1's H-MECH family
    on label build `fwar@2026-10-02-0341299c20ec` (11 arms, alpha 0.025), zero survivors, and its
    twins scored at least as well as its best candidate (kill rule 4). Plan 2.6: "A null is a
    result: it closes item 17 permanently on existing columns." MiLB SDR data is a new data source
    under its own registration, not a fourth look. Kill rule 6 as quoted in item 1 also binds.
18. STALE_DAYS may not be lowered (test-pinned); attack the undated-artifact ratchet only.
    Star-blend h2 never blends. Never sum ML quantile points. Statcast-into-projections rejected;
    only the dated pwoba re-gate after 2026-11-15 lives. Draft-anchor backfill retired.
    eta_age_continuous deprecated. B3 level-blend reopens only under the C3-repowered
    null-resolution shape. PAL: stamina lane and naive arm gates closed; RP->SP stays downgraded.

Gate discipline inherited wholesale from EFV_GATE_STANDARD.md: paired bootstrap with refit,
zero-information twin, permutation null band, >=4 time splits, named estimator on every claim,
two-sided coverage checks, Holm, no floor-shopping, no estimator-shopping, no threshold-shopping,
retired 4-fold floors may adjudicate nothing.

## 3. W0: baseline and ledger hygiene (half a day)

- W0.1 Run the suite (chunked runner, from prospect-tracker/, never piped). Expect the two
  stale-artifact reds plus identity_collisions going green. If green, remove its
  KNOWN_BASELINE_REDS entry and fix the "exactly three reds" docstring (run_suite.py:21-26).
  If still red, the repair is incomplete: the entry comes OUT, not re-baselined.
- W0.2 Commit data/card_market_eval.json with its registry pairing (a registry row currently
  points at an artifact that exists only untracked; a fresh checkout breaks the pairing).
- W0.3 Leave the owner's data/ churn alone. Record the five standing owner actions (section 1)
  in the session log; do not re-derive them.

## 4. W1: the truth layer (registry, artifacts, claims all agree)

This is the audit core. Nothing here changes a served model number; everything makes the
accountability surfaces match the evidence. Every later wave depends on it.

- W1.1 **P0 claims repair.** assets/glossary.js:383-387 renders, in is-good styling, "eFV
  out-predicts every public source" while its own artifact (source_backtest.json 2026-08-18)
  says head_to_head resolvable=false, xfv_beats=false, and MLB Pipeline leads eFV vintage-matched
  on BOTH Spearman (0.3966 vs 0.3944) and AUC (0.7386 vs 0.7364). This violates the AUC copy
  contract, and the honest derived hero renders one tab over, so the site contradicts itself on
  adjacent views. Also: :2453 ("ahead on Spearman in every archetype" - true in 2 of 6),
  :554/:568 and data/glossary.json:1531 (consensus-beats-inputs stated unqualified; the artifact
  resolves the AUC leg only: "Blending buys DISCRIMINATION, not ORDERING"). Migrate all five to
  the mature derived pattern (_methHeroBanner / _methEfvVerdict / _methConsensusVsInputsNote).
  The fix cites the tie; it never re-measures the closed question.
- W1.2 **Claims-freshness test.** Extend test_methodology_freshness.py with a
  quoted-number-vs-artifact diff for glossary.json entries that carry numbers (hem_plus:5210,
  milb_translation:4953, war_pa_plus:5324, consensus_fv:1531), and a registry-note-vs-artifact
  diff for headline fields. Known drifts it must catch on day one: fa_market card champion 9.83
  vs artifact 10.2067 (served on /models/); betting_game_prob and betting_elo_benchmark notes
  quoting 2026-08-16 numbers against the 2026-08-18 artifact; stuff_plus_aaa note citing forward
  ERA r +0.230 (n=17) while the restamped artifact reads -0.093 (n=20); eta_hazard_lite row
  saying "gated OFF" while eta.py:128-150 and storage.py:9853-9859 show it LIVE since 2026-07-29.
  copy_lint cannot see this defect class; this test is the instrument that keeps section 0's
  rule alive.
- W1.3 **Registry debt batch (8 + 2 rows).** Rows for: mock_draft (mock_draft.py:274),
  farm movement (movement.py:486), rank movement (movement.py:618), positional versatility
  (fielding_positions.py:107), multiposition bonus (bayes_trade_value.py:533, an unmeasured
  dollar additive flowing into trade_values), FA aging curves (fa_projection.py:416),
  milb_translation (served predictive claim, glossary-quoted numbers, validation embedded in
  data/milb_translation.json outside the freshness map: split into a stamped eval artifact),
  GRPO (see W2.1), plus Cmd+ (composite_cmd_plus, displayed unregistered) and OrgSur+
  (glossary + display, covered only via the farm tree row). Verdict unvalidated where nothing is
  measured; that is the honest state.
- W1.4 **Instrument boundary decision.** Document (in MODEL_REGISTRY.md preamble + a test
  comment) that instruments and policy are not models and carry no rows: shadow ledger,
  two-start ledger, market publishability gate, efv_alerts feed, amateur_leagues ingest,
  identity resolution. Alternative is rows for each; recommended default is the documented
  boundary, so "every model needs a row" stays crisp.
- W1.5 **Enum extension.** Add a machine-readable provisional_kind (or structured reason) field:
  shipped-partially-measured / measured-not-adopted / measurement-only / data-blocked-stub /
  inherits-parent-gate. Two rows state on the record that the enum cannot express their state
  (pal_conversion, fantasy_ros_rankings), and the war_rate_plus family cannot link its own
  artifacts. This does NOT re-judge any verdict (the 2026-08-14 lesson: the seven artifact-less
  provisionals are owner judgements; the field records kind, not verdict).
- W1.6 **RETIRED-BASIS stamping.** ~60 xfv_* artifacts generated 2026-07-01..08-05 measure the
  retired 4-fold basis; xfv_dispersion_repair_eval.json carries green PASS clauses for a
  correction C-7 reverted to identity. Add a basis/retired field to those artifacts' registry
  rows plus a test that no live gate constant sources a 4-fold artifact. This is the guard that
  prevents a future session from re-applying dead work off a green eval.
- W1.7 **Freshness wave.** Regenerate the 2026-06-11 block before ~2026-09-09 (draft_slot_curve,
  farm_grade_eval, prospect_path_eval, overseas_translation_eval, statcast_plus_eval,
  dpw_forecast_eval; trade_machine_eval rides W2.2). Add generated_at to undated writers on
  their next NATURAL regeneration, live four first (fa_gate1/2, proj_horizon,
  college_translation). Retro-stamping is banned as provenance falsification
  (model_registry.py:194-198); every date comes from a real re-run.
- W1.8 **Small coherence fixes.** PD+ scale drift (live code is sigma-scaled at
  prospx/index.html:54233-54244; glossary formula and registry note still describe the retired
  additive scale); glossary groups map missing industry-stat and Valuation categories (4 entries
  render raw slugs); glossary.js header says 4 views, there are 7; deferrals.json _doc references
  a nonexistent data/deferral_coverage.json (the audit lives in fa_gate2_eval).

## 5. W2: measurement wave (new evals where none exist, re-reads where the artifact outran the verdict)

- W2.1 **GRPO first forward eval** (the census hole). grpo_prospect.py is a monthly-retrained GBM
  scoring 4,685 prospects into the served breakout badge with NO row, NO eval, NO validation
  block. Register honestly (badge-only; the C3 pricing-zero stays), then build a
  maturation-window badge hit-rate eval vs a zero-information control and an FV-only control
  (the editorial_eval template already passed this exact design). GRPO never enters eFV features,
  so the closed frontier is not implicated.
- W2.2 **Trade-value forward backtest.** trade_value_history now holds 42 snapshot dates
  (2026-06-25..08-18, 247,962 rows): the first 30-day-forward windows exist for ~24 snapshot
  dates. Score whether snapshot surplus orderings predict 30-day realized value/grade movement;
  refresh trade_machine_eval (oldest live-module eval, undated, ship=false) in the same lane.
  This retires the stale "never snapshotted" limitation for good.
- W2.3 **ETA empirical-table challenger gate** (largest measured unshipped gain anywhere:
  challenger forward-chained MAE 0.869 / within-1y 0.811 on n=2,944 vs champion 1.422 / 0.589 on
  n=4,186). The current cells are NOT row-matched, so nothing may ship as-is: pre-register a
  row-matched gate under the same censoring-aware overdue guardrail that gated the v39 ship, with
  the selection caveat (MAE conditions on debuted rows) stated in the registration. Do not touch
  eta_age_continuous (deprecated) or the eta_hazard_lite owner history. Either promote or write
  the loss ledger; also restamp the 2026-06-11 ship_decision date and fix the hazard-lite row
  (W1.2 catches it; this lane closes it).
- W2.4 **Mock draft scorer.** A post-draft hit-rate eval vs the actual 2026 draft is cheap and
  has never run; it turns a rowless heuristic into a measured one in an afternoon.
- W2.5 **aStuff+ re-read.** The forward ERA leg flipped sign in the restamped artifact
  (-0.093, n=20). Decide the framing: K% leg holds (0.4842), ERA leg is unpowered AND sign-wrong.
  Copy constrains to K%/whiff claims; registry note re-read from the artifact.
- W2.6 **SC+ restamp** via arkmetric_forward_eval.py so published accuracy describes the
  post-2026-07-07 chase-fixed composite (the committed eval measures the chase-dead one).
- W2.7 **star_odds diagnostic.** Gate FAIL (max_abs_dev 0.6439 vs 0.1). Confirm no surface serves
  the model odds (displayed odds are the published table, exact), then recalibrate or formally
  retire the diagnostic. Owner call only if a surface is found serving it.
- W2.8 **total_band re-run.** Coverage 0.4055 vs 0.75-0.85 target, undated, un-rerun across the
  C-1/C-7 epochs that changed its inputs. First confirm whether any served band still derives
  from it; do NOT resurrect war_total_band_calibration's deprecated config.
- W2.9 **Farm letters archive.** Grades were never snapshotted (the backtest is a reduced
  analog). Start archiving the served letter per org per month so the literal v40 tree becomes
  gateable; refresh the 69-day-old farm_grade_eval (W1.7).
- W2.10 **Durable closer evidence.** fantasy_closer_gate_eval.json lives under .cache/ (box-local).
  Copy the verdict durably into docs/ or data/ so the RED gate and the saves-only re-open
  condition survive a cache prune.
- W2.11 **Identity residue batch.** 12 open c7 name-variant splits, 10 c4 side conflicts,
  22 null-id rows: the residue class that produced the jesus_lopez live defect. Batch-resolve
  with the garrett_wright/repair-script pattern.

## 6. W3: calibration and improvement lanes (each pre-registered, each inside measured-open room)

FA family (the largest cluster of open, admissible room):
- W3.1 **ptier bias regression diagnosis.** The committed Gate-2 artifact carries guarantee ptier
  biases -2.618 / -9.115 / -16.888 / -24.169, WORSE than the 2026-07-30 E5-recal state
  (-2.11/-6.27/-15.04/-3.70) even though RECAL_MODE="shift" still ships. Diagnose why the
  08-03/08-04 refreshes regressed the calibration BEFORE proposing any arm. Scope: intercept and
  level family ONLY (slope forms twice-refuted; every new form repeats the E5a overshoot check).
  Every tier under-prices, so the direction is a level lift. Restamp the /models/ card with it.
- W3.2 **fa_bands mid-decile coverage.** Deciles 5-7 cover 0.63-0.72 vs 0.80 nominal (z -8.9 to
  -17.1) while extremes over-cover; disclosed, never triaged. Pre-register a per-decile isotonic
  width correction on the WAR-side band only. The guarantee-side band is twice-null and fenced.
- W3.3 **fa_team_fit concentration repair.** The one registered, un-gated lever: make behavior's
  "recent" and "rich" components player-conditional (LAD tops 57% of the class because recent
  normalizes by league-max outlay). Everything else on this surface is ledgered as wasted effort.
- W3.4 **fa_penter winter readiness.** The 16 logged qo_offered events are suspect (stamped
  2026-08-12 pre-offseason with no window guard, names are prior-QO recipients). Guard or
  re-semanticize the stamping BEFORE the winter or the first live shakedown starts contaminated;
  pre-register the decision-level scoring (base-rate baseline per option type) now so Oct-Jan
  is not wasted.
- W3.5 **Arbitration.** Three items: (a) verify Gate C's C1-C6 were actually scored on the
  103-row priced population (the census could not find the scoring, only the ship); (b)
  adjudicate the retained-salary AAV semantics flagged in spotrac.py:502-503
  (Arenado/Castellanos); (c) the Swartz 2.66x deficit stands recorded: the only identified path
  is a counting-stats projection lane, a NEW model family and an owner decision (queue item),
  not a refit. arb-2+ stays a ledgered power-limited null.
- W3.6 **fa_rational_value tercile re-cut.** Verdict edges measured stale by the module's own
  numbers (44/29/27 vs the 33/33/33 design; served distribution 37/52/9). Re-cut is cheap and
  high-visibility; VERDICT_BAND_MODE "group" moves 19.7% of historical verdicts and is a product
  call. Both queued as owner decisions.
- W3.7 **dpw forecast re-challenge.** The FA family's most naturally re-runnable stale eval
  (2026-06-10; flat-5% champion won at MAPE 0.102 vs 0.122) with two more winters of drift now
  measured in R7.

Projections:
- W3.8 **Row-matched champion-vs-lgbm cut** in proj_horizon_eval (current challenger block sits
  on a different base set and invites a false win claim), plus a date stamp. Measurement only;
  the use_ml pins and star-blend h2 pin are not touched.
- W3.9 **team_outlook serve-vector tripwire.** Wire the served_recentered vs plain-recentered
  comparison into the eval refresh so if the serve vector ever reads worse, it flags itself.

## 7. W4: Diamond wave (clock-driven; almost nothing here is model-fitting)

- W4.1 **Close cron install** (owner action; the single highest-value operational item in the
  tree). One scheduler install unblocks four instruments at once: CLV, the market_close
  benchmark tier (n=0), the calibration ledger's market-move block, and the public record's
  first row (betting_record.json is literally "[]"). Both deploy artifacts exist; the two
  historical close-job defects are already fixed in code. Every day of delay destroys another
  slate's CLV evidence permanently.
- W4.2 **Nightly reliability.** The 2026-08-15 and 08-17 nightly snapshots missed entirely,
  costing two vintage nights, a DFS slate, and two days of schema-3 accrual. Diagnose and harden
  the daily run; snapshot reliability is now the binding constraint on the B3/B4 clock.
- W4.3 **Correct the schema-3 clock in the doc.** First schema-3 vintage on disk is 2026-08-18
  (not the pre-registered 08-16), so the earliest admissible B3/B4 look is ~2026-09-15, not
  09-13. Record it BEFORE anyone measures.
- W4.4 **Build the missing schema-3 builders.** xwoba_14 / xwoba_30 / lineup_strength / star_out
  are stated nulls with NO builder, so by rule 2 their candidate clocks have not started. Build
  them dark now or B3/B4 arrives with only off_vs_hand and throws populated.
- W4.5 **Props readiness.** Owner: EEPHUS_PROPS_CREDITS=120 on the box (machinery is inert by
  design until then). Plan: build the props box-score grader, the named unlock without which
  props evidence can never settle and the per-tag min_edge clocks never start.
- W4.6 **Pre-decide evidence-leg close copy.** The total market already reads t 1.767 > 1.645 and
  is held open only by the n>=100 floor; it will likely be the first market closed by the
  evidence leg while already excluded by the theory leg. Decide the page copy for that state now.
- W4.7 **Prose restamps.** betting_game_prob and betting_elo_benchmark registry notes against the
  2026-08-18 artifact (the deficit SHRANK: -0.001753 at t -0.559 on n=269; ladder Elo 0.24519 <
  home 0.24848 < model 0.25023; market-open 0.24449 on the n=126 subsample). W1.2's test then
  keeps them honest.
- W4.8 **Vintage-mode re-eval at ~900 gradable** (~2026-09-17 on the measured 12.4/day). Ladder
  re-read, no model changes. Platt stays closed below 100 settled ledger games; blend below 150;
  picks stay Model Watch until a gate opens on its own terms.
- W4.9 **Cards decision** (owner): send the SportsCardsPro permission email or formally park the
  module. Code-complete, blocked purely on a source; zero engineering either way.

## 8. W5: the glossary program (claims, receipts, and the industry comparison)

Framing that keeps this honest: the measured record contains real WINS over industry and naive
baselines, real TIES, and real LOSSES. The glossary's job is to present all three in mathematical
and economic language a casual can follow, with every number derived from an artifact. The tie on
the flagship is presentable as a strength: eFV matches the public consensus with a transparent,
auditable model, and the receipts page proves it either way.

- W5.1 **Claims ledger.** Build the WIN/TIE/LOSS bucket list from artifacts (evals census
  verified): WINS that may carry claims: FA Gates 1-3 (WAR MAE 0.574 vs 0.728; guarantee $10.21M
  vs comps $11.48M; team-fit MRR 0.167 vs random 0.133), HEM+ (0.4119 vs AVG 0.2347, CI>0), SEM+
  (0.4167 vs FIP 0.3821), xHEM+ (0.4543 vs 0.4108, lo95 +0.0173), REM+ (0.2363 vs FIP 0.211),
  pWOBA (0.5189 vs 0.4939), editorial vs matched control (faller h30 21.5% vs 0.0%),
  eta champion vs naive table (1.431 vs 1.971 on identical rows), farm financial core (rho 0.508
  vs count 0.240), ifa_step_prior, positional_ladder_recency, surplus isotonic calibration
  (held-out slope ~0.96 vs raw 0.64), sub-45 empirical FV anchors (published constants overstated
  2.2x at FV40, ~10x at FV35). TIES that must stay ties: eFV vs consensus (every rank cut, both
  estimators; AUC too), consensus weighting. LOSSES/UNPROVEN that stay published honestly:
  betting (last on its own ladder, self-declared contaminated), arbitration vs MLBTR/Swartz
  (2.66x), war_rate_plus g2, statcast_plus (weak r .12-.17), BA as a source (loses resolvably to
  FG: the pairwise block).
- W5.2 **Receipt block per model entry.** A shared renderer (extend the efv_scoreboard /
  _methHeroBanner pattern) that renders, per entry: the estimand in one plain sentence, the named
  baseline, the measured number with CI or floor, and the three-valued verdict
  (clears / inside floor / trails). No entry hand-codes a number; the W1.2 test enforces the few
  that legitimately remain prose.
- W5.3 **Formula + worked example backfill.** 59 of the 94 model-documenting entries lack both.
  Order: the FA money quartet first (fa_projection_engine, rational_value, winter_dpw, deal_plus:
  user-facing dollar claims, currently the weakest quadrant, winter_dpw has an empty methodology),
  then the WAR-rate+ 9-entry family (one shared worked example), then leverage/leaderboard
  metrics. Voice: terse, math-first, owner standard (2026-06-16); no em-dashes; ban list applies.
- W5.4 **The industry-comparison layer** (the "show we beat industry models in math/econ
  language" ask, done with receipts). Source basis is docs/reference/FANGRAPHS_FV_FRAMEWORK.md
  (industry tables are priors to TEST, never copy). Pages/blocks, each derived from its artifact:
  (a) the five industry FV->WAR tables measure five different quantities, and the Quantity A/B
  confusion misprices 2-3x: our two-table split (fv_to_prime_war vs bust-inclusive) is the fix,
  with a worked FV50 example in dollars; (b) our sub-45 anchors vs the published constants
  (2.2x/10x overstatement), the derive-not-copy precedent; (c) cross-side non-comparability: at
  consensus FV55+ hitters realize 11.07-13.4 WAR vs pitchers 4.8-5.8 (xfv_side_fairness), i.e.
  the industry over-grades top pitchers and our lower pitcher share is the more accurate read;
  (d) the BA era break (2023-25 raw vs 2026+ adjusted, recovered exactly, absorbed by cycle-keyed
  normalization) and BA's resolvable accuracy deficit; (e) the economics layer: surplus as an
  expected value (median-vs-mean, why the $0 floor was wrong on purpose), NPV deferrals (Ohtani
  $700M -> ~$197M at 9%), $/WAR by winter with the flat-5% champion. Each block: one plain-language
  paragraph for the casual, then the math, then the artifact link.
- W5.5 **Diamond/fantasy on-page claims lane.** The glossary freshness net deliberately does not
  reach Diamond/fantasy page copy ("the page IS the documentation"). Extend the
  no-banned-accuracy-claim test pattern from the Diamond scaffold to fantasy pages, and audit
  both for hand-written numbers that should be derived from betting_learning / eval payloads.
- W5.6 **Frozen-vintage disclosure check.** War-rate boards disclose that 3yr columns are frozen
  vintages; verify HEM/SEM/REM 3yr columns (same join pattern) carry the same disclosure.
- W5.7 **RPS+ three-scales resolution** (owner decision): unify to one scale, rename per surface,
  or populate statline.rps_plus so the inert TBS 0.22 term either works or is removed. Disclosed
  today, but three scales under one glossary name is the kind of defect the glossary program
  exists to end.
- W5.8 Publish through the existing gates: strip_emdashes/copy_lint clean, claims-freshness test
  (W1.2) green, MODEL_GLOSSARY documentation decisions for any new rows (the test forces them).

## 9. W6: clocks and re-open calendar (register, then stop thinking about them)

| Clock | Date/condition | What fires |
| --- | --- | --- |
| 2026-06-11 eval block | ~2026-09-09 | first-ever stale flags unless W1.7 refreshes |
| board_all shadow tag | ~100 settled rows (~days) | first per-tag min_edge sweep allowed |
| B3/B4 schema-3 look | ~2026-09-15 (corrected) | first admissible feature measurement |
| Betting 900 gradable | ~2026-09-17 | vintage-mode re-eval + ladder re-read |
| Platt ledger arm | 100 settled canonical ML games | calibration re-adjudication allowed |
| Market blend | 150+ distinct ledger games | blend re-visit allowed |
| pwoba re-gate | after 2026-11-15 | season_complete(2026) admits ~650 pairs |
| fa_penter decisions | Oct 2026-Jan 2027 | first decision-level eval (pre-registered in W3.4) |
| Draft weight A/B | 2027 | 2022 class resolves, one more vintage cell |
| RESOLVED_THROUGH -> 2026 | early 2027, one commit | 2025 cohort labels + first pitcher-stuff fold + aStuff+ gate + shadow constant in build_star_odds_artifacts.py:27 |
| SDR drop day | Will's data passes --validate | census commit, --accept, then G-A, G-B, G-C in order |
| Test rot watch | ~2026-12 and ~2027-01 | two farm tests cross their hardcoded-date cutoffs (flagged 2026-08-13) |

## 10. Owner decision queue (defaults recommended, none blocks W0-W2)

1. ETA challenger gate (W2.3): authorize the row-matched measurement now, ship decision after the
   gate returns. RECOMMEND authorize.
2. Arbitration counting-stats lane to attack the Swartz 2.66x deficit: new model family, real
   scope. RECOMMEND publish the deficit honestly now (W5.1 already does), queue the lane for a
   later cycle.
3. RPS+ three scales (W5.7): RECOMMEND rename per-surface + delete or feed the inert TBS term.
4. fa_rational_value: pooled tercile re-cut (RECOMMEND yes) and per-group banding (product call,
   moves 19.7% of historical verdicts).
5. Cards (W4.9): RECOMMEND send the SportsCardsPro permission email; park if refused.
6. Registry instrument boundary (W1.4): RECOMMEND documented boundary, no rows for instruments.
7. Enum extension (W1.5): RECOMMEND structured provisional_kind field; no verdict re-judging.
8. Claims policy (W5): derived-only accuracy claims EVERYWHERE including Diamond/fantasy page
   copy. RECOMMEND yes; W1.2 + W5.5 are the enforcement.
9. Deferral ledger: 26 marquee schedules (Soto, Ohtani, Judge, Tucker...) curated-unverified
   since June; the NPV basis of every Gate-2 number rides on them. Owner-only verification task.
10. Standing owner actions (not new decisions): close cron, props env line, box rebuild_only,
    Supabase + /auth/, SDR drop. Plus two open items already on the record: the KRP+
    zero-quadrant call and the xfv_repeat_level pitcher arm.

## 11. W7: the conviction program (owner instruction, 2026-08-19)

Owner instruction received 2026-08-19: find a way to make eFV's Spearman/AUC scores measurably
more accurate than every public source. Under the reopen standard (section 2, omnibus-2 s2) an
owner instruction is a named reopen condition, so this section reopens SPECIFIC lanes. It does
NOT repeal the gate standard: "measurably" means pre-registered cells clear their E_cond floors
under Holm, on the vintage-matched frame, against the named raters (FanGraphs, MLB Pipeline,
PROSPX consensus). No claim ships that an artifact does not derive; if the program ends null,
the copy stays on the tie frame and the program record becomes the public receipt.

Governing arithmetic (from the 2026-08-18 artifacts): vintage-matched Spearman delta +0.0017 vs
MDE95 0.0303 (0.056x); best admissible AUC cell 0.736x of its floor. Resolution requires some
combination of: the delta grows (model), the floor shrinks (labels/measurement), or the claim
family shrinks honestly (fewer pre-registered cells, smaller Holm penalty). Levers, in
expected-value order:

- V1 **Label pool** (the one mechanism the closed-frontier verdict itself names). Pre-register
  the RESOLVED_THROUGH-2026 epoch analysis NOW (exact cells, estimators, floor re-derivation
  protocol, claim frame) so unlock day is measurement day, not design day. Publish a power
  projection of the 2025-cohort admission (+243 debuts): the head-to-head cell is the one whose
  floor is majority-removable (refit share 0.128 per EFV_GATE_STANDARD s power ceiling).
- V2 **New data sources** (the sanctioned reopen class). (a) BA backfill: the named unblock for
  the B-L6 denoised-baseline control (registry efv_denoised_baseline_control). (b) BA risk
  ordinal into the p_bust chain, power-check FIRST (omnibus-4 open item 4; one resolvable base
  year). (c) Feasibility recon for additional public boards (Baseball Prospectus, Law/The
  Athletic, ESPN) as new FEATURE sources: identity-resolution cost measured before any ingest
  (the binding constraint per the data-sourcing runbook); note new sources also strengthen the
  consensus baseline, so the honest target is per-source signals (tool grades, risk tiers) the
  consensus mean discards.
- V3 **One registered model-class re-adjudication on the 11-fold basis.** The 22-challenger
  closure (xfv_model_class_sweep) is a RETIRED-BASIS verdict (4-fold, 2026-07). The 2026-08-14
  planning record shows the pitcher ensemble arm (mean of ridge+lgbm, 0.2612 vs blend 0.2584)
  was never adjudicated. One attempt, both sides, ridge vs monotone-lgbm vs ensemble, frozen
  clauses, permanent-close pre-commitment if null (the B3 shape).
- V4 **Consensus-input integrity that moves both legs honestly**: the C-4 era floor flip
  (owner-locked 2026-08-13, mechanism landed inert, STILL not flipped; one line + rebuild +
  margin re-read + golden restamp), the 2022 FG board per-board override, org canonicalization.
  These improve the baseline too; every margin re-reads after each, and a regen that does not
  move a number is treated as a failed regen.
- V5 **Floor side**: decidability triage (retire cells that cannot resolve at any feasible n
  from the claim family), E_cond primary everywhere, and a pre-registered claim frame naming
  the SMALLEST honest cell family for the public claim.

Stop clauses: no floor-shopping, no estimator-shopping, no post-hoc frame or arm selection,
no re-run of any of the 39 closed feature arms, every lane carries its permanent-close
pre-commitment in the registration before measurement.

## 12. Execution protocol (inherited, non-negotiable)

- Pre-register every gate before measuring; freeze clauses; report failures as written.
- Artifacts only for numbers (section 0). A regen that does not move a number is suspect: check
  that the artifact actually regenerated (the 2026-08-13b vacuous margin re-read).
- Mutation-prove every new test; adversarially verify every lane headline before it enters a
  commit message (the 2026-07-31 record: 3 of 5 single-pass agent verdicts were wrong).
- No pytest during agent batches; chunked runner; read the runner's summary block, never a piped
  exit code. Explicit cd in every shell call. Never edit tracked files while a suite runs.
- efv_ungraded.py writes on ANY invocation; never run it casually.
- Registry edits require tools/gen_audit_docs.py in the same change (generated-docs sync test).
- New data/*_eval.json trips the standing-rule test AND test_methodology_freshness (forces a
  documentation decision). That is by design; budget for it in every measurement lane.
- Copy: no em-dashes anywhere user-facing; terse math-first voice; ban list; scraped third-party
  scout text is cleaned, never re-voiced.
- Commit cadence: commit each lane's artifacts + doc + tests together; push only on owner's call.
