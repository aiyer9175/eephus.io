# Review Queue

Deferred work with enough spec to pick up cold. Each item: what / why /
expected impact / rollback. Nothing here ships before Beta (2026-07-11)
unless explicitly pulled forward by the owner; items marked DO NOT ATTEMPT
PRE-LAUNCH are frozen harder than that. Curated by hand; landed items move
to CHANGELOG.md with their commit.

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

## 8. Overseas hitter wRC+ and CPBL factors

- What: extend overseas_translation with hitter wRC+-based factors and a
  measured CPBL set (current CPBL factors ride the smallest cohort).
- Why: hitter translations lean on rate stats with no park/league offense
  anchor; CPBL n is thin and shrunk hard, which the eval discloses but the
  display does not.
- Expected impact: better MLBe lines on the Overseas tab; updates
  data/overseas_translation_eval.json and the registry row.
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
