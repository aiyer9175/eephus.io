# Review Queue

Deferred work with enough spec to pick up cold. Each item: what / why /
expected impact / rollback. Nothing here ships before Beta (2026-07-11)
unless explicitly pulled forward by the owner; items marked DO NOT ATTEMPT
PRE-LAUNCH are frozen harder than that. Curated by hand; landed items move
to CHANGELOG.md with their commit.

## Dispositions from the 2026-07-02 review-queue round

Owner pulled items 2, 4, 5, 6, 7, 8, 9, 10 forward. Results (details in the
per-item sections and docs/audit-2026-07/AUDIT_FINDINGS.md):
- Item 4 (grade-scale eFV band): DONE. Shipped on the PROSPX player-detail hero.
- Item 5 (gradeBlock refactor): DONE. One helper, 5 sites routed byte-identically;
  6 sites intentionally left (distinct fallbacks) and flagged.
- Item 6 (ERA-shrink unification): RESOLVED as KEEP-TWO. Gated sweep found no single
  value beats both objectives; K_IP=50 and NEED_ERA_SHRINK_IP=45 stay. Closed.
- Item 7 (F-01 total bands): RESOLVED. The bands were miscalibrated beyond the summing
  bug (they under-cover, mis-centered high), so the owner-approved fallback was taken:
  total P10-P90 bands dropped from FA + Projections display. See new item 13 for the
  real long-term fix.
- Item 10 (farm-letter snapshotting): DONE. History now accrues (first snapshot 2026-07-02).
- Item 2 (MiLB park factors): CLOSED-INFEASIBLE on cached data (no venue dimension, no park
  join key). Re-open only after the minors ingest gains a venue dimension; spec retained below.
- Item 8 (overseas wRC+): UPGRADED to READY-TO-RUN (NPB); see below.
- Item 9 (Country/IFA entity pages): still open; the build lane failed on a structured-output
  error (not a data problem) and was deferred rather than re-run under launch pressure.
Items 1, 3, 11, 12 unchanged. New items 13, 14 added below.

## 1. proj_lgbm star-tail refit (DO NOT ATTEMPT PRE-LAUNCH)

- What: refit the WAR-path quantile heads so the star slice (base-year WAR
  at 4 or above) stops under-projecting the tail, without a mean head.
- Why: two documented failures already stand: the mean-head variant was
  reverted for overshooting Ohtani-class ceilings, and the star-slice bias
  persists in data/proj_horizon_eval.json. A third attempt needs a new idea
  (cohort-conditional tail calibration or a star-only residual model), not a
  rerun.
- Expected impact: star-slice MAE/bias improvement with pooled MAE flat;
  gate on the existing proj_eval.py horizon backtest before ship.
- Rollback: registry row `fa_war_paths_decay` pins the champion; revert to
  the committed model artifacts and re-run tools/train_proj_models.py at the
  prior config.

## 2. MiLB per-park factors (Savant minors 2023+)

- What: per-park run/HR/BABIP factors for the minors from Savant's minors
  feed (coverage starts 2023), applied where level norms are used today.
- Why: level norms treat every park in a level as identical; PCL vs FSL
  offense gaps leak into RPS+, eFV stat features, and translations. The same
  factor table also unlocks closing the college_translation SOS/park gap
  (college TrackMan lines are currently translated park-blind).
- Expected impact: modest MAE gain on translation-adjacent evals; honest
  scope note in glossary entries that lean on level-relative stats.
- Rollback: factors are a multiplicative layer; ship behind a flag defaulted
  off, revert = flag off, no data-shape change.

## 3. Aging-curve unification

- What: reconcile the three aging implementations (FA regressed-rate decay,
  value_framework FV paths, marcel components) or document the fork as
  intentional per surface. docs/aging-curves.md (landed in this pass, lane B)
  documents the three-way fork as defensible; unification is the follow-up.
- Why: three curves answering "how does a player age" invites cross-surface
  contradictions a reader can screenshot.
- Expected impact: consistency more than accuracy; run proj_eval.py after
  ANY curve change (standing rule).
- Rollback: keep per-surface curves; the doc alone already de-risks the
  contradiction complaint.

## 4. Grade-scale eFV confidence band

- What: an eFV uncertainty band expressed on the 20-80 grade scale.
- Why: the current band_p10_mm/band_p90_mm fields (efv_score.py) are SURPLUS
  DOLLARS, so every surface that wants "how sure is the model" has to talk
  money; a grade-space band is what scouts read.
- Expected impact: display/UX; no model change. Needs a rank-preserving map
  from the bucket distribution to grade quantiles.
- Rollback: additive fields only; drop the columns.

## 5. gradeBlock reusable component refactor

- What: one shared `gradeBlock(p)` renderer for the grade cluster (eFV,
  consensus FV, provisional/ungraded state, movement chip) used on every
  surface; spec is xfv-phase2 items B1/B2 (docs/xfv-phase2-plan.md).
- Why: the cluster is hand-copied across PROSPX board, detail pages, farm
  pages, and GFX; drift already produced one rounding inconsistency caught in
  the beta audit.
- Expected impact: no user-visible change on day one; deletes duplicated
  markup and makes the FV-ceil/eFV-nearest rounding rules single-sourced.
- Rollback: components are additive; revert the call sites.

## 6. ERA-shrink value unification (K_IP=50 vs NEED_ERA_SHRINK_IP=45)

- What: decide one pseudo-count for shrinking ERA-family rates; today
  RPS+ shrinks with K_IP=50 while PAL's need screen shrinks with
  NEED_ERA_SHRINK_IP=45. Both now live with provenance in
  rate_stabilization.py (F-05, lane B); the VALUES stay split.
- Why: same quantity, two shrink strengths, no documented reason; the
  constants module made the divergence visible, not correct.
- Expected impact: small published-number changes on whichever surface
  moves; requires an output-diff run and a one-line methodology note.
- Rollback: values are named constants now; flip back one literal.

## 7. warTotalP90 band remediation (finding F-01)

- What: stop displaying summed per-year quantile points as total-WAR bands.
  Sites: fa.js:506 and :798, projections.js:624, :954 and :1028, exported by
  proj_export.py/fa_export.py/mlb_player_export.py.
- Why: the sum of per-year P90s is only the P90 of the total under perfect
  year-to-year correlation; displayed bands are systematically too wide
  (overstated upside, understated floor). The methodology rule already bans
  this in backtests; the display violates the same statistics.
- Expected impact: visibly narrower bands on every FA/Projections total.
  BLOCKED ON AN OWNER DECISION: the dependence assumption (per-path
  simulation vs a fixed rank-correlation) changes published numbers and must
  be picked once, documented, and applied to both modules in the same
  release.
- Rollback: keep the summed fields in the payload during transition; the
  frontend can re-point at the old keys.

## 8. Overseas hitter wRC+ factor (READY-TO-RUN, NPB) + CPBL/Cuba (blocked)

- Status (2026-07-02 re-check, docs/audit-2026-07/overseas-factors-recheck.md):
  the wRC+ blocker has DISSOLVED. FanGraphs already publishes league+park-
  adjusted NPB/KBO/MLB wRC+ on one player page and overseas_stats.py already
  parses it (HITTER_KEYS wRC+ -> wrc_plus), so NO separate league-context
  scrape is needed. The refit is ready to run for NPB (n=6 hitters, matching
  the K% delta factor this module already shipped under k=8 shrink) and
  marginally KBO (rises to ~3-4 once FG resolves hitters B-Ref drops).
- Only new input needed: curate ~7-10 fg_player_ids for the graduated cohort
  hitters (Suzuki, Yoshida, etc. currently fg=None), an owner-extendable
  ledger task. This is the sole gate to running it.
- Gated experiment (pre-registered in the re-check doc): LOO-validated wRC+
  multiplier must beat the prior, SEED=8 bootstrap stability, coverage n>=5
  NPB, marginal=fail. Elite-selection caveat (every transition hitter is
  posting-caliber) surfaces in the note, same as the shipped pitcher ERA
  multiplier.
- CPBL: BLOCKED-ON-cohort-existence (zero CPBL->MLB transitions 2015-2026;
  CPBL is a destination, not a source). Cuba: BLOCKED-ON-source (no Serie
  Nacional wRC+ on FG, unreliable B-Ref, plus a 1-2 year defection-gap that
  breaks the "final foreign season" rule). Both stay hand-set prior-only;
  recommend marking them prior-only in the registry note.
- Rollback: factor table swap; keep the phase4b_refit_v2 table as fallback.

## 9. Country/IFA entity pages

- What: per-country pages plus IFA class pages in the entity-pages system
  (States/HS/Regions/Colleges shipped; countries are the approved remainder,
  including the US-states SVG map hook).
- Why: IFA content dead-ends at the tab; country pages close the loop with
  signing-class history and org tendencies.
- Expected impact: new static pages only; no model surface.
- Rollback: additive pages; drop the routes from build_site.

## 10. Farm-grade letter monthly snapshotting

- What: snapshot the composite farm LETTER grade (not just farm_rank, which
  already accrues via snapshot_farm_ranks) on the monthly cadence, starting
  January 2027.
- Why: the letter is currently unvalidatable forward; a letter history is
  the missing input for a "did A farms out-produce B farms" backtest. The
  registry row `farm_grades` is provisional for exactly this reason.
- Expected impact: none at ship (append-only history table); the payoff is a
  validated/refuted verdict circa 2028.
- Rollback: stop snapshotting; history keeps whatever accrued.

## 11. AgeRel+ (age-relative outperformance) owner decision

- What: decide whether the X-D2 AgeRel+ index ships as a PROSPX display chip.
  The gate-passing-on-its-face eval and 3,570 proposed per-player values sit in
  data/age_rel_outperformance_eval.json; wiring is a one-lookup join plus a
  glossary entry.
- Why it is a decision, not a ship: (a) the strict pre-registered no-blowups
  screen failed and the PASS reading leans on parity instruments formalized
  after inspecting the failure (disclosed in the artifact); (b) the plain
  level-relative comparator out-predicts the age-matched index (pooled r
  0.156 vs 0.124), so the index's value is context, not prediction; (c) at
  upper levels the same-age cohort is the promoted-elite subset, so 100 reads
  as "keeping pace with fast-track peers", not "level average" (e.g. an elite
  young prospect can read 100 on AgeRel+ while reading 107 on the shipped
  level-relative chip). The display semantics need an owner call.
- Expected impact: display-only chip; no model or rank surface.
- Rollback: drop the chip; the artifact stays as a loss-ledger/candidate.

## 12. SC+ composite reweight candidate (barrel + whiff 2-component blend)

- What: the X-C3 diagnostic's closed-outcome-season decision instrument now
  fires "reweight": the forward-chained top-2 blend (hitters Barrel%/BBE-led,
  pitchers SwingMiss%-led) beats the equal-weight 4-component composite by
  +0.14 (hit) / +0.28 (pit) pooled OOS r on closed cohorts. The shipped
  composite is unchanged: the diagnostic was never a pre-registered ship gate
  and the closed pools are n=23 per side.
- Why queued: changing published SC+ values requires its own pre-registered
  gated experiment (registry row + eval artifact + freshness map), and the
  decision flipped between "keep" and "reweight" depending on whether the
  in-progress 2026 outcome season is included, which is exactly the sample
  fragility a ship gate exists to absorb.
- Spec: after the 2026 season closes, re-run with three closed folds
  (2023->24, 23+24->25, 23+24+25->26), pre-register a gate (both-sides gain
  >= 0.05 at n >= 40/side, no cohort-year reversal), and ship through the
  standing triple if it passes.
- Rollback: none needed until attempted.

## 13. Per-year WAR quantile marginal recalibration (the real F-01 fix)

- What: recalibrate the per-year WAR quantile heads (fa_market.contract_war_path
  war_by_year_p10/p90, decayed from war1 + Gate-1 residual quantiles; and the
  proj_ml quantile heads) so the marginals carry league-attrition zero mass.
- Why: the R-BAND experiment (data/total_band_eval.json) proved the displayed
  total bands under-cover realized multi-year totals (incumbent 0.63 vs 0.80
  design), because ~26% of realized totals fall below the p10 path: washouts
  leave the league and realize ~0 WAR, but the strictly-positive decayed p10
  never reaches zero. This is a marginal-calibration defect, not a summing or
  width defect, so it also affects the per-year bands (survived-all coverage
  0.55). The total bands were dropped as the interim fix (item 7); this is the
  fix that would let calibrated bands (per-year AND total) come back.
- Expected impact: wider, lower-floored per-year bands that actually cover;
  gate on realized coverage in [0.75, 0.85] on holdout, on BOTH per-year and
  a dependence-aware total (the AR(1) copula machinery in tools/fit_total_band.py
  is ready, rho 0.345 estimated, and becomes correct once the marginals are
  fixed). Changes published band numbers: pre-registered gated experiment.
- Rollback: quantile-head change is a model artifact swap; revert to the
  committed proj_ml heads and the current decay in fa_market.

## 14. Country/IFA entity pages re-run

- What: same as item 9; the 2026-07-02 build lane failed on a structured-output
  error (the agent did the work but could not format its return), not a data or
  code problem, so nothing landed. Re-run the single lane against the shipped
  states/colleges entity-page generator pattern.
- Why: additive static pages, approved long ago; not launch-critical, which is
  why it was deferred rather than re-run under pre-launch pressure.
- Expected impact: new static pages only; no model surface.
- Rollback: drop the routes from build_site.
