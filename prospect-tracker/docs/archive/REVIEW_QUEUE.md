# Review Queue

> **ARCHIVED 2026-09-25. Historical record, not current status.** This queue
> was written for the Beta launch of 2026-07-11 ("nothing here ships before
> Beta") and has not been maintained since. Known drift: item 2 (MiLB park
> factors) is recorded as CLOSED-INFEASIBLE below, but the minors ingest gained
> a venue dimension and `/parks/` serves the factors (201 venues plus 1 pooled
> row). Current deferred work and owner decisions live in
> `docs/master-plan-2026-09-24-final-pass.md` and the dated master plans under
> `docs/`. Moved here from the repository root on 2026-10-01 (owner answer M23-4).

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
- Item 9 (Country/IFA entity pages): CLOSED as already-shipped. prospx has client-side
  per-country pages (goToCountry / renderCountryDetail) AND an IFA signing-class tab
  (#tab=ifa); both halves of the item exist. A parallel static build was written and
  discarded as redundant (owner decision 2026-07-02). What is NOT done is a static,
  crawlable/shareable entity-page layer, but every entity type (states, colleges,
  countries) is client-side-only, so that is a site-wide SEO project (item 14), not a
  countries-only bolt-on.
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
- MEASUREMENT-BASIS WARNING, added 2026-08-07. The +0.14 / +0.28 above were
  measured against the SC+ composite as it stood then: an unshrunk, equal-weight
  mean of the component z-scores, rescaled by a nominal 10 points per sigma
  (statcast_plus.py compute_statcast_plus). omnibus-3 lane E is recalibrating
  that composite in two gated steps, an empirical-Bayes shrink with volume
  gates first and then a true 10-per-sigma re-standardization
  (docs/master-plan-2026-08-07-omnibus3.md lane E). Whichever of those lands,
  the thing being reweighted here is no longer the thing that was measured, so
  whoever picks this item up after the season closes must RE-MEASURE the top-2
  blend against the composite that is live at that point. Do not read the
  queued deltas forward. Two reasons they will not carry: shrink changes each
  component's spread, and therefore its weight inside an equal-weight mean of
  z-scores, before any reweight is applied; and the decision already flipped
  between "keep" and "reweight" on whether the in-progress 2026 season was
  included, at n=23 per side, which is not a sample that survives a basis
  change either. Re-derive the floor in the same run rather than reusing one.
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

## 14. Static crawlable entity-page layer (all entity types) - SEO/sharing

- What: expose the entity pages (states, colleges, countries, and the IFA
  signing classes) as static, individually-crawlable, shareable URLs, with
  prospx linking out to them. Today all entity pages are client-side routes
  inside prospx (goToCountry / renderCountryDetail / _renderColleges / the
  IFA tab), so none of them has a clean shareable URL or a social preview.
- Why: launch-surface reach. The content is strong and international-prospect
  and college pages are the kind of thing that gets linked from X/LinkedIn;
  client-side-only routes are invisible to crawlers and share unfurlers.
- Scope note: this is a site-wide decision, not a per-type bolt-on. A
  countries-only static build was written in the 2026-07-02 round and
  DISCARDED specifically because shipping static pages for one entity type
  while the others stay client-side is incoherent (owner decision). Do all
  types together, sharing one generator, with prospx routes linking to the
  static canonical URLs (needs a prospx edit for the inbound links).
- Expected impact: new static pages + sitemap entries; no model surface; the
  client-side routes can stay as the in-app fast path or redirect to static.
- Rollback: drop the routes from build_site and the sitemap.

## 15. Overseas translated stats -> eFV features (the Yamamoto low-eFV concern)

- What: for overseas (NPB/KBO) prospects, populate the eFV production-block
  features (efv_model._vec: k_rel / bb_rel / age_rel_level, currently taken from
  r["milb"]) from the VALIDATED overseas-to-MLB statline translation
  (overseas_stats._mlb_translate + the shipped overseas_translation model,
  data/overseas_translation_eval.json: era_factor + k_pct_delta, shrunk k=8),
  instead of leaving milb empty so milb_missing=1 and the model imputes the block
  and leans on consensus FV. Owner motivation: Yamamoto-type arms get a low eFV
  despite an elite overseas K rate because their real stat signal never reaches
  the model.
- Why deferred (NOT a pre-launch change): eFV writes data/xfv.json, a GOLDEN
  artifact the whole 2026-07 pass has kept byte-neutral, and the eFV calibration
  line was DEFINITIVELY CLOSED after four loss ledgers (at the trainable-data
  ceiling). This is a change to published eFV numbers for a subpopulation and so
  needs a pre-registered gate, but the graduated-overseas-with-outcome cohort is
  too thin to validate one: the overseas translation cohort is 28 resolved
  NPB/KBO transitions total (data/overseas_translation_eval.json accounting), and
  the intersection with (had a prospect eFV grade) AND (has a realized eFV outcome
  target) is far smaller, on the order of ten. That cannot carry the per-side,
  no-degradation, bootstrap-CI rigor the other eFV experiments were held to. The
  reassuring half is that feeding overseas features only touches the handful of
  overseas prospects and cannot degrade the main OOS metric (no overseas players
  in it), so the only real question is whether it moves those players sensibly.
- Method when the cohort matures (2024+ overseas graduates resolve): translate
  each overseas prospect's last qualifying foreign season to an MLB-equivalent
  line, derive k_rel/bb_rel against the MLB level, set milb_missing=0, re-score,
  and gate on (a) a directional check (elite-overseas-K arms move UP; verified
  intent: Yamamoto), (b) no absurd outputs, (c) the thin-cohort eFV-vs-outcome
  rho not worse. Ship provisional with the caveat disclosed; xfv.json golden diff
  will CHANGE for overseas rows only, documented in the changelog.
- Interim, zero-risk alternative (not yet built): surface the validated overseas
  MLB-equivalent line (translated K% / ERA) as CONTEXT on the overseas prospect's
  card WITHOUT changing eFV, so the quality signal is visible even while the
  number stays put. Lower blast radius; a candidate Wave C display item.
- Rollback: feature feed is a dataset-assembly change; revert efv_dataset to the
  empty-milb path for overseas rows and re-score.

## 16. Payload weight trim (post-beta)

- What: shrink the two heaviest browser payloads - the debuts payload (~122MB on
  disk) and the boot payload (~62MB) - so cold loads are lighter, without
  dropping any surface.
- Status (2026-07-18): SUBSTANTIALLY DONE. The 07-16/17 payload-slimming surge
  executed most of this item - debuts lite/full split + per-player `debuts_full/`
  shards, scout-report chunking, prospx payload sharding, CollegeSavant year-split
  payloads, and the publish diet (data_exclude additions). A latent bug from that
  work was found and fixed in the 2026-07-18 audit (A1): the `debuts_full` shard
  fetch read the wrong key and the shards were shipped by neither deploy path, so
  the per-player lazy-load silently fell back to the monolith; both are now fixed.
  Remaining tail: an explicit before/after wire-weight measurement of the sharded
  boot path (the e2e boot check is green post-A1). Prior status below.
- Status (2026-07-07): ACCEPTED-FOR-BETA as-is. `gzip_static` serves the `.gz`
  twins (deploy/README.md nginx block), so wire weight is already far below the
  on-disk figures and the numbers are a page-weight optimization, not a
  correctness or availability risk. Deferred so it does not gate launch.
- Why deferred: a real trim (shard by cohort/era, lazy-load the debuted-backgrade
  and ungraded tails, or move the heaviest tables behind an on-demand fetch)
  touches the PROSPX boot path and several exporters; it wants its own before/after
  wire-weight measurement and an e2e boot check, not a rushed pre-launch change.
- Expected impact: faster cold load; no change to any published number or surface.
- Rollback: additive shards / lazy-load flags; revert to the single-payload fetch.
