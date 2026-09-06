# Master plan 2026-09-05: eFV conviction, betting on resolved games, new metrics, new modules

Written for Claude Opus to execute. Branch `efv-conviction-2026-08-08`. Every number below
comes from a committed artifact or a gate document; every lane carries a pre-registered
gate, a permanent-close pre-commitment and a blast-radius clause, per
`docs/EFV_GATE_STANDARD.md` and the registry standing rule (row + eval artifact + gate
doc before anything ships). No em-dashes, terse math-first voice.

The plan has five parts:

- Part 0: what shipped this session and the owner decisions it rests on.
- Part 1: eFV, the conviction program (win resolvably against every public source; new
  drivers and ideas).
- Part 2: Sports Betting on resolved-game data (accuracy and ROI, any-market slots,
  per-market and per-prop sub-models with sub-ledgers, Futures), new MLB Stats metrics
  that feed it, and the Alchemy Lab, Free Agency, Projections and Trade Machine lanes.
- Part 3: two new MLB Modules, In-Game Management (MWAR) and Hall of Fame Modelling.
- Part 4: sequencing, owner decision queue, do-not-reopen ledger.

---

## Part 0. Shipped 2026-09-05 (this session) and the decisions behind it

### 0.1 Rank uniformity: one board rank on one eFV file, on every surface

Defect: `run_monthly.rebuild_only` exported `data/timeseries.json` (which bakes
`overall_rank` off `data/xfv.json` ON DISK) and only then ran `efv_export.regen_all`,
which rewrites that file from the just-exported timeseries. So every surface reading the
baked rank (homepage Top Prospects, org ranks, the news tooltip, the GFX eyebrow) was on
the PREVIOUS run's grades while the PROSPX board sorted on the fresh ones. On 2026-09-05
Josue De Paula and Theo Gillen tied at 58.3 with `board_sort_key` 9.617 vs 9.670 (the
previous file had them 58.2 vs 58.1): homepage #4 / #5, board #5 / #4. A second defect
compounded it: `build_site._top_key` re-sorted on (primary FV, '+') with no sub-decimal
term, so an exact tie fell to list order.

Fix (tests in `test_board_rank_rebake.py`, 11 green including two artifact tests):

- `storage.board_rank_key` is THE ordering tuple (grade desc, board_sort_key desc, '+',
  TBS proxy, avg_rank asc), built by the export and by the new
  `storage.rebake_board_ranks`.
- The export serializes the non-model tail per active row as `board_key_tail`
  [fallback_fv, upside, tbs_proxy, avg_rank, org_key]; the re-bake re-applies the chain on
  the fresh xfv.json, rewrites overall_rank / org_rank / org_rank_total /
  prev_overall_rank / rank_movement atomically, stamps `board_rank_rebake`, and updates
  today's `metric_snapshots` rows when the monthly snapshot already exists.
- `rebuild_only` order is now export, eFV regen, tripwire, RE-BAKE, then every sidecar that
  reads overall_rank (ifa_export, identity_audit, org_tendencies); pinned by a source test.
- The homepage reads `overall_rank` and labels rows with it. CLI:
  `tools/rebake_board_ranks.py [--dry-run]`.
- Measured on the first rebuild: 4,690 active rows re-ranked, 4,366 moved (the stale
  basis was pervasive, not a two-row edge case).

Remaining known divergence: deep exact-tie blocks (server TBS proxy vs the client's JS
TBS), where the rank number is already withheld as not meaningful
(`RANK_TIE_BLOCK_MAX = 50`). A future lane can serialize the JS TBS inputs and close it.

### 0.2 Betting: any-market slots, and the honest model now beats the home constant

Owner decision 2026-09-05: `betting_model.SLOT_MARKET_POLICY = "any"`
(docs/diamond-betting.md 7d). Every priced market (moneyline, runline, total, props when
the pull is armed) is eligible for both published slots and the public record. The
dispersion caveat (`caveat`) and the section 7b ledger evidence (`evidence_caveat`,
`evidence_closed`) ride the ROW as disclosure; `market_theory_ok` still answers the
theory leg for the publishability table (`policy_override` says when the legs would have
barred a market). Props value rows are priced BEFORE the slots (first pass with
`slots=None`) so they compete on the same floor and rule; `"dispersion_gated"` restores
the 2026-08-14 / 2026-08-16 behaviour at both seams and both states are pinned
(`test_betting_dispersion_exclusion.py`, `test_betting_market_gate.py`). The selection
RULE is unchanged; the reliability-aware accuracy-and-ROI rule is Part 2 lane B1, not a
silent edit.

Measured fact that changes the betting narrative (`data/betting_model_eval.json`,
2026-09-05): vintage n=472, Brier 0.24398 vs home-base 0.2482, paired t 2.058,
`beats_baseline_95: true`, accuracy 0.5678; literature Elo 0.2442; market open de-vig
0.23175 on the 239-game subsample (model 0.24462 on those same games). The
`out_of_sample_skill` gate is OPEN. `vintage_sample` (472 / 600) and
`graded_price_history` (min_edge null; board_all 214 settled) are not. Every earlier
memory or copy that says the model loses to always-home is stale as of this artifact.

Column sorting shipped on every betting table (`wireSortableTables` in
`assets/betting.js`: role=button headers, aria-sort, keyboard, nulls sink, per-table
persistence; parser and comparator exposed as `window.EEPHUS_BETTING_SORT` and pinned by
tests).

### 0.3 Card Market removed; developer card rewritten

The Card Market module (surface, exporters, assets, data, pipeline steps 6g-pre / 6g /
9f, nav, sitemap, catalog row, tests) is removed. Registry row `card_market_index` is
deprecated with a dated note; the two runbook docs carry a retirement header. The owner's
developer card back (`content/team.json`) is a resume-style summary of the platform work
and the skills it used.

### 0.4 Owner decisions taken this session (treat as given)

1. Pick of the Day is not locked to the moneyline: any market, including props.
2. The betting model is optimized for BOTH accuracy and ROI (Part 2 defines how).
3. Per-market and per-prop sub-models with their own sub-shadow-ledgers.
4. A Futures section (win totals, division, pennant, World Series; awards if feasible).
5. Card Market removed.
6. Two new MLB Modules at the end of the plan: In-Game Management with MWAR, and Hall of
   Fame Modelling.

---

## Part 1. eFV: the conviction program

Sources: the efv-conviction-audit workflow (10 census lanes, 117 of 131 proposals
adversarially verified on a combined closed-or-banned plus data-and-effect lens: 57 kept
with revisions, 60 killed; 14 verifications died on the session limit and are marked
UNVERIFIED), the standing gate corpus (`docs/EFV_GATE_STANDARD.md`,
`docs/efv-2026-08-19/CONVICTION_PROGRAM.md`, `docs/efv-2026-09-03/*.md`) and the live
artifacts. Every lane below inherits the standard wholesale: paired bootstrap B=2000 with
a fixed seed, E_cond primary with E_refit beside, zero-information twin, permutation null,
Holm inside the family, floors derived at measurement time on the registered frame, no
floor or estimator shopping, permanent-close pre-commitment inside the gate doc.

### 1.1 State of the claim (artifacts, 2026-09-05)

| cell | frame | delta vs best rater | floor | verdict |
| --- | --- | --- | --- | --- |
| C1 hit Spearman | vintage-matched common set, n 755 hit (source_backtest xfv_vs_consensus) | +0.0104 vs consensus; pooled vintage-matched eFV 0.3998 vs Pipeline 0.3990 (n 803) | mde95 0.044 (E_refit); pooled head-to-head E_cond 0.0303 | not resolvable |
| C2 pit Spearman | same, n 892 pit | -0.0129 vs consensus | 0.044 | not resolvable, negative point |
| C3 hit AUC | debuted_km contributor | +0.00965 vs consensus | 0.736x of E_cond floor | null |
| C4 pit AUC | debuted_km contributor | +0.00403 vs consensus | 0.196x | null |
| block rho (both sides) | side x cohort-year normalized | +0.003 | 0.0182 E_cond | not resolvable |

Within base year the nominal leader flips: eFV 0.3928 vs Pipeline 0.3755 on the vintage
frame (+0.0173, about 0.55x a floor near 0.03). Per rater, pooled: eFV 0.4012 above
FanGraphs 0.3684, below Pipeline 0.4107. On AUC the consensus is the measured best rater
(consensus_vs_inputs +0.0155, resolvable), so the C3/C4 comparator is the consensus.

### 1.2 Diagnosis, five sentences

Features, model class on squared loss, lambda, correction families, consensus weighting
and the hitter serve basis are all measured closed, and the eWAR label epoch bought
nothing on accuracy. The two public frames carry construction defects that favour the
public raters: pooling across base years with different exposure (F06) and a universe
that never loads the never-debuted pool (F20). The served pitcher grade is the ridge leg
alone and sits 0.015 to 0.023 under the evaluated blend, which is the one served-number
gap on the table. The pitcher side trails structurally (role, attrition, FIP label noise)
and no feature lane has touched it; every pitcher-specific arm proposed this session was
killed as a costume of a measured null. The honest central expectation is that the four
frozen cells do not clear at the 2027 read either; what this plan can do is remove the
frame defects, close the serve gap, fix the label definition, run the surviving new
driver families, and register a successor claim family that is decidable.

### 1.3 Group A-CLAIM: the instruments and frame amendments (no served number moves)

These are measurement lanes. They change what can be claimed and how power is spent, not
what the board serves. Ship as one gate document `docs/efv-2026-09-06/CLAIM_INSTRUMENTS.md`
with every clause frozen before the first read.

- **A-CLAIM-1 Rebuild the claim instruments** (claim_math_P01, kept; effort M). Regenerate
  C3/C4 with the best rater resampled inside every bootstrap draw (publish per-draw
  argmax winner shares and the argmax-resampled minus fixed-argmax floor as the
  winner's-curse receipt), derive per-side C1/C2 E_cond floors in-run and retire the
  stored `XFV_HEADTOHEAD_VINTAGE_MDE95` constant (serve_vs_eval_P06, kept), and emit an
  AUC coverage certificate. Expected effect on C3/C4 margins: zero (the consensus is the
  best rater on AUC). Expected on C1/C2: floors widen per side versus the pooled 0.0303,
  so the cells may enter the V5 retirement branch. Files: `source_backtest.py`
  (`_xfv_vs_consensus`, `pairwise_head_to_head`), `tools/efv_power_lab.py`,
  `data/xfv_power_eval.json`. Tests: floor stamps compared on `generated_at` only, never
  mtime; the nested `partb_floors` block must be present (claim_math_P12, kept).
- **A-CLAIM-2 Within-base-year block leg** (claim_math_P03, serve_vs_eval_P04,
  model_class_P09; all kept as RECEIPTS). Add `within_year` (n-weighted, min 50
  vintage-matched rows per side per year) and `block` (year-percentile-normalized,
  reusing `efv_model._block_norm`) legs beside the pooled cell in
  `accuracy.pooled_efv_common_vintage_matched`, with per-year n and eFV coverage
  published and floors derived in-run by the stratified player-clustered E_cond
  bootstrap. Promotion to primary only by an owner sign-off that RECORDS the direction was
  already known (F06(d)); both legs then sit in one Holm family. Expected: eFV +0.0173
  within year, about 0.55x floor, still a tie.
- **A-CLAIM-3 Exposure-matched label** (serve_vs_eval_P05, kept). Score the head-to-head
  on first-six-season eWAR instead of career-to-date, in two cuts: fully resolved windows
  (debuts through 2021) as the clean receipt, and the censored full cut with
  `_label_6yr` weights and the censoring-bias direction from
  `data/xfv_label_censoring_eval.json` stated beside it. Pre-declared expectation: C1/C2
  remain unresolved; a nominal flip is not quotable.
- **A-CLAIM-4 Bust-inclusive universe** (serve_vs_eval_P03, model_class_P10; kept). Load
  `inactive.json` into the head-to-head universe under the frame's own rules: score
  eFV's bust rows at the preseason point of the last list year (or restrict to busts whose
  final list point is itself preseason, 375 of 794, publishing the 419 in-season-final
  rows as an asymmetry control), separate active-undebuted (censored) from inactive busts,
  and register the FanGraphs and Pipeline legs only (the consensus bust cell is the
  already-measured `full_pool_km`: hit -0.0164, pit +0.0112, both null). Pre-registered
  expectation: hitter nominal loss, pitcher null; the product is a coverage receipt.
- **A-CLAIM-5 Served-leg rater** (serve_vs_eval_P01, kept). A superseding gate S-2 under
  `docs/efv-2026-09-06/` with a `blend_war` helper that takes an explicit basis flag
  (`raw_ridge` for `_run_eval`, `calibrated_clamped` for `oos_grades` / `run_live`) and
  covers all five call sites; S0 must reproduce both objects to 0.0010 (pit blend 0.2828,
  ridge 0.2596, baseline 0.2957; hit 0.3925 / 0.3889 / 0.3821) before the helper lands.
  Publishes what the board serves on every public frame beside the blend.
- **A-CLAIM-6 Forecast-encompassing b2** (serve_vs_eval_P12, model_class_P11; kept).
  y = a + b1 cons_war + b2 model_war, out of fold with fold fixed effects on
  target_censored, player-clustered bootstrap CI, on debuted_km per side and the 802-row
  vintage-matched set; null = within-fold permutation of the model residual on cons_war
  plus the zero-information twin; regress on WAR-scale objects only (blend leg and the
  calibrated ridge, never the 20-80 grade). Registered as the leakage-clean successor to
  `lambda_calibration.wag`. An interval covering zero prints UNDECIDED.
- **A-CLAIM-7 Tilt and routing census** (serve_vs_eval_P08, kept). Whitelist `rank_war`
  in `efv_export._entry` (pin next to the :582 precedent), and publish the served-vs-
  evaluated divergence decomposed per side into tilt reorder (rho(xfv_war_6yr,
  board_sort_key), 0.988 H / 0.986 P today), map and routing reorder, and overlays.
- **A-CLAIM-8 Alpha-spending clause** (claim_math_P06, kept revised). Not Lan-DeMets: a
  one-paragraph clause in `EPOCH_2026_PREREGISTRATION.md` recording the reads already
  taken on C1-C4 (2026-08-14, 2026-08-19, 2026-09-05) as descriptive, declaring ONE
  confirmatory read of the family at a named RESOLVED_THROUGH, and stating that every
  other read is a receipt.
- **A-CLAIM-9 Bayesian companion, artifact only** (claim_math_P07, kept revised). Emit a
  posterior block (two hierarchies, one per metric family, joint-bootstrap covariance)
  into a companion artifact; NO served copy; extend `test_claims_freshness.py` to ban
  "probability eFV is better" strings on served surfaces.
- **A-CLAIM-10 Discordant-pair floor** (claim_math_P10, kept): bootstrap the 1,264-row
  cohort, average ranks for ties, publish the CI into
  `accuracy.xfv_vs_consensus_detail`, derive the copy in both `assets/glossary.js` and
  prospx from it.
- **A-CLAIM-11 Track-record AUC leg in the driver lab** (drivers-P12, kept). Contributor
  AUC (>= 3 WAR) as the sole co-primary AUC leg; star AUC a labelled sensitivity row with
  no verdict weight (46 pitcher stars in debuted_km, floor 0.0397). State the conjunction
  rule in the standard: AUC may veto an arm that clears rho, may sit in a jointly sized
  Holm family, can never credit an arm that fails the rho floor.
- **A-CLAIM-12 Served population statement** (consensus_sources.P08, kept). Four-category
  population block in `source_backtest.json` (constant-anchor-only, single-source shrunk,
  single-source unshrunk, multi-source) at the latest point and on the common set, with
  one derived sentence of accuracy-page copy.
- **A-CLAIM-13 Rater scale view** (consensus_sources.P11, kept): a side x year block-rho
  row per rater beside `accuracy.per_year`, marked additional view; measured expectation
  MP pooled -0.0113 (0.93x floor), no verdict change.
- **A-CLAIM-14 Candidate years and newcomer ledger** (consensus_sources.P04, kept):
  per-pair in-window overlap and first decidable run year (the ESPN x Pipeline 2026
  overlap at 11 rows can never clear the 100-row pairwise minimum), per-source key
  resolution counts; 2024 enters at the 2027 run.
- **A-CLAIM-15 (UNVERIFIED, critic lane) program arm ledger and reserved confirmation
  fold** (critic-07): tally every arm adjudicated on the 11-fold basis and hold the 2025
  decision cohort out of every exploratory read so the V1 unlock CONFIRMS survivors. Also
  unverified: train-pool parity (critic-03), label-component decomposition receipt
  (critic-05), top-weighted companion receipt (critic-06), consensus-composition parity
  (critic-08), covariate-shift census (critic-09), synthetic positive control for the
  driver lab (critic-10), identity Frankenstein screen on the label path (critic-04),
  multi-vintage out-of-fold head-to-head and training frames (critic-01, critic-02).
  Each is measurement-only; run the verification lens before building any of them.

### 1.4 Group A-SERVE: the served ordering (real ordering effects, own epochs)

- **A-SERVE-1 Pitcher serve-basis re-measure on the eWAR frame** (model_class_P08, kept;
  effort S; effect on public cells ZERO because C2/C4 already score rank_war through
  `efv_model.oos_grades`). Ship rule = the pre-registered S2 rule on A2a only: served
  LOSES iff rho(A2a) < rho(A0) - MDE95 (E_cond, B 2000, seed 20260814, floor in-run);
  the TOST 0.02 disposition reported, not decisive. If served loses, serve `rank_war`
  (the blend) as the pitcher board grade through the outcome map in its own grade-basis
  epoch (A-SERVE-2), described honestly as a return to the pre-2026-07-25 blend-headline
  regime, with an explicit re-decision of POOLED_OUTCOME_REFIT 2.7. Expected pitcher
  served ordering gain up to +0.023 (unfloored); still trails plain consensus by 0.0129.
- **A-SERVE-2 Serve the evaluated object** (serve_vs_eval_P02, kept revised): sequenced
  strictly after A-CLAIM-5 publishes the served_leg block with E_cond floors and TOST both
  sides; it is that gate's only legitimate trigger.
- **A-SERVE-3 Age-ramp serve-rule gate** (serve_vs_eval_P11 and arkmetric P05, both
  kept). Per side, paired Spearman delta = rho(served with ramp) - rho(served without) on
  full_pool_km, E_cond estimator, equivalence margin fixed in advance to that side's
  registered E_cond floor; sweep onset 23/24/25 x slope 0.05/0.10, Holm, B 2000. Coverage
  stated honestly: the 2018-2024 band only (298 hit / 459 pit rows), age-missing rows
  ramp-neutral, the above-26 class too thin to bound. The ramp stays in the grade only if
  the TOST no-harm test PASSES; on a null it moves to a labelled age-risk indicator,
  removing a 10 percent per year haircut from 1,937 live rows (1,378 above the floor).
- **A-SERVE-4 Statcast lean ceiling** (arkmetric P06, kept revised): apply the 4 FV
  ceiling to the served-grade delta versus the OFF counterfactual; scale BETA per leg
  from that leg's own lo95/rho ratio (A-ball whiff 0.287, A-ball velo 0.138, AAA velo
  0.225, spin 0.316, vaa 0.219); no per-row rank cap. Served-number change, own epoch,
  zero on public cells.
- **A-SERVE-5 Served-board overlay harness** (arkmetric P15, kept narrowed): execute
  A-SERVE-3 as the registered sweep; add the reliever-ceiling ablation as a reported cell
  (53 RP rows age >= 25); do NOT re-run the injury rule (settled measurement,
  `data/xfv_health_profile_eval.json`).
- **A-SERVE-6 Provisional thin-cohort calibration** (arkmetric P14, kept): ship the owed
  zero-risk items first (routed-share clause in `test_claims_freshness.py`, the G6
  tie-block re-measurement on the unrounded key), then re-register the calibration gate
  with the three 07-30 stop conditions verbatim plus a landing-distribution clause.
- **A-SERVE-7 Per-row basis ledger** (arkmetric P16, kept revised): keep `basis_terms`
  as a disclosure device; attribution per term comes from counterfactual scoring inside
  the lab (re-score with each overlay toggled, score-only, no rebuild) published as a
  sequential decomposition of the clause (f) statistics with a residual line. This is
  what lets more than one served-number change ride an epoch.

### 1.5 Group A-LABEL and A-SEAM: label definition, seams, valuation

- **A-LABEL-1 Appendix A arms** (labels-01, arkmetric P01; kept, split). Run A2 alone
  first: build E0 and E2 both sides with `tools/build_label_arms.py` (pitcher E0 must be
  built; a lab must override `efv_dataset.matrix_path` per arm and flip
  NEUTRAL_MILB_IMPUTE inside the lab), read the level_rank slope clause and the rank
  TOST at 0.02 E_cond. Before any E1/E3 build, add the placeholder-date clause to A1:
  a debut date equal to "{year}-04-01" produced by the fallback carries a provenance flag
  and must not shift the service window. Expected: rank-invariant (rho between labels
  0.9992); level +1.047 WAR hit / +0.496 pit on shifted rows; A2 level_rank slope 0.154
  to 0.209-0.253 per rung.
- **A-LABEL-2 Position-player-pitching label fix** (labels-02, arkmetric P11; kept as
  label hygiene, effect rank 1 on the cells). Implement inside `ewar.py`
  `pitching_component`: drop a pitching row from the FIP re-price when the same
  player-season batting row has PA >= 50 and pitching IP <= 15 (bounds frozen before the
  build, citing the lab's nopp basis); bundle with the same ewar.json rebuild, career_war
  re-rebase and site regen as A-LABEL-1; pre-register C1-C4 UNCHANGED (measured +0.0002
  hit / -0.00099 pit) and that no copy may cite an accuracy move.
- **A-LABEL-3 Ordinal outcome label for BREAKOUT** (labels-12, kept revised). ADD, never
  replace: `star_6yr` (2 seasons >= 4 eWAR within debut..debut+5, or the service-aligned
  window once A-LABEL-1 decides), `window_resolved_6yr` from
  `efv_dataset.RESOLVED_THROUGH` (not the shadow constant at
  `tools/build_star_odds_artifacts.py:38`), `contributor_6yr` = summed 6yr eWAR >=
  `efv_model._CONTRIB_WAR`; keep the 7-season Clemens `star` field for
  `star_odds_eval` and `test_star_odds.py:64`. Note: the BREAKOUT stacked P(star)/P(bust)
  driver itself (model_class_P07) was KILLED by the verifier as four measured nulls on
  this matrix; the owner's 2026-09-03 decision stands as a DISPLAY program (Star% / Bust%
  on cards), not as a rank driver, unless a new label pool reopens it.
- **A-LABEL-4 V1 unlock patch** (labels-13, kept revised): patch the existing prereg,
  fix the stale line references (shadow constant now at :38; `efv_dataset.py:272`
  primary), and add the weight-promotion component to the published power delta.
- **A-SEAM-1 Forward-chained affine at the grade seam** (model_class_P05 and arkmetric
  P02, kept; the F02 estimator and the C-7 re-apply). Affine arm ONLY (isotonic is
  NO_SHIP at TAIL_PRESERVING_REFIT_GATE.md:123): {hit, pit} x leave-one-fold-out affine,
  Holm on the paired full-pool MAE leg; the elite band clause is an E_cond-derived floor
  with n stated (165/110 at >= 50, 70/27 at >= 55); the elite table goes to the owner
  before it ships; reopen basis is the owner's Q2 answer (level outranks elite
  agreement). Spearman/AUC exactly zero by construction; full-pool MAE -0.28 hit / -0.14
  pit on bWAR, to be re-measured on eWAR.
- **A-SEAM-2 B_pooled(fv) as the ridge input** (model_class_P06, arkmetric P03; kept).
  Feed the isotonic pooled outcome curve evaluated at the consensus grade to the ridge in
  place of (and beside) linear fv, fold-chained, with an offset arm; primaries = signed
  bias per consensus band and a pre-registered floor-share target band per side (the
  realized share of rows with WAR <= 0 in the FV 35-40 cells), MAE diagnostic only, rank
  TOST guard. State coherence "to within the blend and calibration" and register the
  served round-trip table (FV 35/40/45/55 per side) as a diagnostic. Rank near-invariant;
  level large on the bottom third (487 of 495 live floor hitters).
- **A-SEAM-3 Abstention grade** (arkmetric P04, kept): after A-SEAM-2, serve the
  abstention as "at most 35" with an `abstain_floor` basis; blast radius = the floor set
  plus outcome-map rows at or below the knot (884 + 85 today); rank_war order, quantile,
  odds, surplus, p_bucket byte-identical. Owner override of the recorded default
  required before starting.
- **A-SEAM-4 Fabricated FV 35 to UNGRADED** (arkmetric P07, kept revised): record AF-Q2
  closed by measurement (zero constant-only anchors in either training matrix), keep
  consensus_fv_raw = 35 inside the live matrix, null only the SERVED consensus with an
  explicit state; live-scoring pass only, never a refit.
- **A-SEAM-5 Valuation unification epoch** (arkmetric P08, kept with five corrections):
  keep the audit's W2 order (F08 then F07 then F09); F07's bar is "beats the shipped
  Platt-linked incumbent on RPS and multinomial log loss, out of fold, both sides,
  player-clustered, label-shuffle control" scoped to the eFV seam as a SECOND curve; star
  odds served measured rates where n >= 30 with the published table as the shrink prior
  and the scale truncated at 70. Dollars, odds, WAG and star display only; board grade
  Spearman/AUC zero.
- **A-SEAM-6 Curve horizon factor** (arkmetric P13, kept reduced): a reported
  sensitivity column at factor 6/7 beside 1.0 on the pooled outcome curve, tied to the
  label-window arm; blast radius 7 active rows at or above the FV 57.5 knot.
- **A-SEAM-7 Consensus integrity, served-board coherence only** (arkmetric P10, kept
  re-scoped): F14 first (as-of date export, tri-state marker, delete the dead drop-off
  shrink; not an epoch), then F16; drop F34 (closed) and demote F35 to a note.

### 1.6 Group A-DRIVER: the new driver families that survived

Every arm runs in `tools/efv_driver_lab.py` on the registered frame with floors derived
first, the zero-information twin, a permutation null permuted WITHIN the stratum named
below, Holm inside the family, and the A-CLAIM-11 AUC leg as the co-primary. The honest
prior on every family is null; the plan runs them because they are the only unmeasured
mechanisms left, and because a null closes the lane on the record.

- **A-DRIVER-1 Pitcher FIP-component family** (drivers-P01, kept, effect rank 2). Refetch
  the full StatsAPI season stat for pre-decision seasons roughly 2008-2024 (the pitching
  lean row at `milb_history.py:176-181` drops homeRuns, groundOuts, airOuts, strikes)
  with a self-heal probe mirroring `:114-119`. Pitcher family: hr9_rel, gb_pct_rel
  (GO/(GO+AO)), strike_pct_rel; WHIP dropped. Hitter family SEPARATE with its own Holm:
  gb_ao_rel, GIDP per PA, pitches per PA. Mechanism: HR allowed is a label component no
  feature carries.
- **A-DRIVER-2 Promotion response** (drivers-P03, kept, effect rank 2): promo_delta and
  share_upper only (days_to_promo dropped as the closed pace-from-entry clock), from the
  cached per-level season rows, on the standard 11-fold frame or a coverage-defined frame
  no narrower than 2016-2024, permutation twin permuted within multi-level rows.
- **A-DRIVER-3 Org revealed preference** (drivers-P04, kept narrowed to ONE arm):
  on40_asof from dated SE transactions on the six-fold 2019-2024 frame with the floor
  re-derived; demoted_12m only after a real-demotion filter exists; rule5 and traded
  dropped.
- **A-DRIVER-4 Splits trajectory** (drivers-P07, kept re-ordered): away-only same-level
  rel-rate as the PRIMARY arm (the registered W2 park-line keep-alive, loss ledger
  `data/xfv_park_line_eval.json`), 2H-1H and monthly slope secondary; fetch league-wide
  by sitCodes into the `.cache/milb_platoon` pattern (about 10 requests per season).
- **A-DRIVER-5 FanGraphs extras remainder, pre-registered on a coverage clock**
  (drivers-P11, kept as pre-registration only): fb_type (primary token, 4 levels) and
  delivery pitcher-only, arm hitter-only, sign_market dropped; runs when the fourth fold
  arrives.
- **A-DRIVER-6 Tommy John measurements, pitchers only** (drivers-P13 and pitchers.P04,
  kept as read-only measurements): the named-surgery sheet joined to the full pitcher pool
  with the health lane's controls (grade, age, rostered exposure), standardised within
  decision year, tj_recent (36-month ramp) and tj_pre, bootstrap CI95, kill if the
  interval includes zero; no served `_injury_factor` change without an interval excluding
  zero on the negative side AND an owner sign-off. Coverage first: 220 pre-cutoff pitcher
  rows (160 debuted), 939 sheet rows without mlbam.
- **A-DRIVER-7 IL substrate repair** (pitchers.P12, kept): repoint `il_stints_pre` /
  `il_any_pre` to the backfilled `player_transactions` archive with the lab's IL regex
  (441 debuted pitchers carry a pre-cutoff placement, not 320), emit an `il_observable`
  coverage share against the 2017 reliability floor so 2011-2016 rows read unobserved.
- **A-DRIVER-8 C2 variance decomposition** (pitchers.P10, kept): realized GS-share role
  from war_daily per rater on the vintage-matched frame (892 pitchers; 267 of 981
  debuted matrix rows lack mlbam and are reported as excluded); sizes the C2 ceiling and
  supports retiring it under V5 triage if the oracle bound sits under the floor.

Creative families the census raised and the verifier killed (do not re-propose): rank
objectives on the same matrix (lambdarank, pairwise-offset, ordinal expected rank,
quantile heads, hierarchical year pooling, year-relative standardization, alpha regid),
BREAKOUT stacked P(star)/P(bust), re-censored busts, aging-carry tails, feature-informed
tail heads, cross-side pooling, reliability weights, cohort-centered targets, rung labels,
positional usage, FanGraphs '+' tier, cohort signing age, per-rater features, rater
momentum, BP OFP second moment as a feature, MiLB pitch-level re-crawl for TTO, usage and
workload columns, role two-head models, component-grade trajectories, pitcher age norms,
K-BB composites, contributor heads. Each has a measured null on the mechanism; the
appendix lists the citation the verifier gave.

### 1.7 Group A-DATA: new sources and vintages

- **A-DATA-1 FanGraphs 2015 and 2016 org-list FV vintages** (new_data_P01, kept). Two
  fully resolved base years, joined by player_key as the Pipeline rows already are;
  stamp to the base-year preseason convention (2015-02-01, 2016-02-01) or the
  `source_backtest.py:57-60` window drops them; extend CANDIDATE_YEARS to 2015; owner
  checkpoint on grade normalization (pre-2017 FG rows create a new reference cell).
  Largest pool increase from any single public source.
- **A-DATA-2 Pipeline 2026 preseason vintage recovery** (consensus_sources.P05, kept):
  capture-only repair from dated Wayback captures (Jan-24 vs Apr-11 top-100 overlap
  92/100 measured), gated on cross-capture self-consistency, 100 distinct ranks, 100/100
  "Overall:" grades, and a 2025 reproduction control; restores roughly 850-900 preseason
  rows for the 2029 run.
- **A-DATA-3 BP OFP / Likely pairwise backfill** (consensus_sources.P10, kept stripped):
  rater-only, dormant until the owner buys a subscription and drops files through a
  `baseballamerica_csv.py`-style inbox; the feature arm is killed.
- **A-DATA-4 TJStats training-vintage decision** (new_data_P13, kept): a source-license
  policy decision recorded in `docs/SOURCE_AUDIT.md` and `tjstats.py:31-34`, deadline the
  2027 flip or the first bust final point dated >= 2026-01-22; pin a test that counts
  tjstats-bearing points on both training loops.
- UNVERIFIED (verifier died): ESPN 2020-2024 top-100 tiers via Wayback (new_data_P05,
  a third grade-bearing comparator, raises the bar unless ESPN is also scored), the MiLB
  play-by-play process-metric availability probe (new_data_P10), college box lines for the
  served abstention set (new_data_P12). Run the lens before building.

### 1.8 Sequencing inside Part 1 and the honest expectation

Epoch 1 (measurement, no served number): A-CLAIM-1 through A-CLAIM-14, A-DRIVER-8,
A-DATA-4. Epoch 2 (label rebuild): A-LABEL-1 A2 arm, A-LABEL-2, A-LABEL-3, A-DRIVER-7,
then E1/E3 if A2 passes. Epoch 3 (serve): A-SERVE-1 then A-SERVE-2 if it resolves,
A-SERVE-3, A-SERVE-4 (each its own epoch unless A-SERVE-7 ships first). Epoch 4 (seams):
A-SEAM-1, A-SEAM-2, then A-SEAM-3/4, then A-SEAM-5/6. Drivers (A-DRIVER-1..6) run inside
the label epoch's frame after A-CLAIM-11 lands, one family per Holm. Data lanes run as
their sources arrive; A-DATA-1 before the next source_backtest regen.

What this buys, stated plainly: the served pitcher ordering can gain up to +0.023; the
public frames stop crediting raters for the year axis and start seeing the bust half of
the label space; the label stops pricing mop-up FIP; the bottom third of the board stops
being chord geometry. None of these is a promised claim-cell win. The V6 successor family
(pairwise per rater, block-normalized, exposure-matched, bust-inclusive) is what the
2027 read should be registered on, and the site claim stays on the tie frame until a
cell clears under Holm on the registered instrument.

### 1.9 Do-not-reopen appendix (killed this session, with the verifier's citation)

- drivers-P10 MiLB play-by-play re-crawl for TTO/CSW: `data/milb_pitch_rates.json`
  delta 0.0059 vs floor 0.016, csw_rel collinear with k_rel.
- new_data_P07 BP OFP-minus-Likely second moment: dispersion mechanism measured
  null-to-negative (fv_stddev, risk_ord).
- arkmetric P12 health dial hygiene: drops the only supported term (il_on, pit rho
  -0.1664 CI [-0.2228, -0.1087]).
- claim_math_P02 CUPED: no admissible label-free covariate; P04 frame enlargement:
  estimand already measured as full_pool_km; P05 triage: V5's own clause; P08 E_refit
  repair: already shipped as the coverage-sd ratio; P09 HKSJ: shipped; P11 weighting
  sensitivity: shipped as Q3.
- consensus_sources P01 '+' half grade: audit F10 in a driver costume; P02 V6 pairwise
  family AS A REPLACEMENT: post-hoc frame selection (register as successor, never
  replace); P03 fixed-composition rater: lane BA1 G3; P06 per-rater features: the
  reweighting oracle bound (+0.00021); P07 multi-rater matrix: the shipped backbone; P09
  quarter cells: master plan A-2 already; P12 rater momentum: fv_trend re-cut.
- drivers P02 rate shapes (iso_rel null, babip), P05 org-adjusted age (no data layer),
  P06 '+' tier (measured null), P08 positional usage (observed-position census lane),
  P09 signing-age clock (pace-from-entry family).
- labels P03 re-censoring (E-RECENCY / E-IPCW), P04 identity routing (DATA FIX C ceiling
  zero), P05 Statcast auxiliary label (rateanchored candidate), P06 tail heads (twopart
  NO_SHIP), P07 aging carry (same family), P08 cohort-centered target (measured, lost),
  P09 reliability weights (I3 lane), P10 cross-side pooling (measured), P11 bust-inclusive
  claim frame as a CLAIM (full_pool_km exists; the receipt survives as A-CLAIM-4), P14
  rung label (the forbidden survival classifier).
- model_class P01 lambdarank (sweep arm already had groups and constraints), P02
  pairwise offset (objective choice closed, row xfv_rank_objective), P03 ordinal rank,
  P04 quantile heads, P07 BREAKOUT stacking (four nulls), P12 year-relative
  standardization (denoised-baseline P1), P13 hierarchical pooling, P14 alpha grid
  (`data/xfv_alpha_criteria` measured).
- new_data P02 Chadwick crosswalk (run to exhaustion, ceiling zero), P03 BA handbook risk
  leg (underpowered ba_risk row), P04 MiLB backfill retest (R4c condition unmet), P06
  ZiPS/KATOH comparators (diagnostic already measured twice), P08 pos-player split (the
  nopp basis is A-LABEL-2), P09 BA rank-only wayback (recon precondition unmet), P11
  Prospects Live ask (SOURCE_AUDIT disposition stands).
- pitchers P01 usage columns (volume family), P02 role two-head (relief-shape gate NO
  SHIP), P03 MiLB feed kinematics (W-SCREEN-SUB), P05 strike-throwing (gated twice),
  P06 extra aStuff+ arms (W-SCREEN), P07 component trajectories (fv_trend class), P09
  hazard x magnitude label (ledger closes it), P11 pre-2019 deficit (TEST 1 null), P13
  pitcher age norms (published), P14 contributor head (I2), P15 label-vintage hygiene
  (pre-empted by the gate's own section).
- serve_vs_eval P07 per-rater AUC on the matrix frame (registration gap real, but the
  frame is inadmissible as written), P09 decidability rule (already registered), P10
  stale-anchor parity (re-litigates E-STALE).

---

## Part 2. Betting on resolved games, new metrics, and the module lanes

(Filled from the modules-betting-audit workflow synthesis below.)

PENDING_SYNTHESIS_B

---

## Part 3. New modules: In-Game Management (MWAR) and Hall of Fame Modelling

Source: the new-modules-design workflow (2 data-census lanes, 5 design lanes, 72 of 77
proposals adversarially verified on a combined data-feasibility plus measurement-validity
lens: 71 kept with revisions, 1 killed; the synthesis stage died on the usage limit and
this section is written from the lane outputs and their verdicts). Both modules are new
children of the MLB Modules nav group, built on the `build_pal` pattern, and both inherit
the standing rules: a registry row plus a committed eval artifact plus a pre-registered
gate document before anything ships, no em-dashes, Arkmetric attribution on every new
glossary entry, and losses committed beside wins.

### 3.0 The shared substrate: a play and pitch corpus that already exists on disk

This is the finding that makes both modules affordable, and it is measured, not assumed.

- `.cache/win_prob` holds **19,132 cached games, 20.02 GB**, seasons 2018-2026 (2020
  absent; about 2,430 games a season, 2,124 for 2026 in progress). The payload
  `mlb_leverage.get_win_probability` caches is **not** a slim leverage list: it is the
  full `allPlays` object per plate appearance plus `homeTeamWinProbability`,
  `awayTeamWinProbability`, `homeTeamWinProbabilityAdded`, `leverageIndex` and
  `dramaIndex`. The `/feed/live` `allPlays` block carries no leverage and no WPA, so the
  winProbability resource is a strict superset and the only carrier of both.
- Pitch level is fully present: every `playEvents` entry with `isPitch` carries
  `details.call.code`, `details.type.code`, and `pitchData` (start and end speed, zone
  top and bottom, coordinates). Non-pitch events per 300 sampled games: 2,056 pitching
  substitutions, 663 offensive substitutions, 537 defensive switches, 280 defensive
  substitutions, 291 stolen bases at second. Scaled to the cache: about **1.47 M plate
  appearances, 5.74 M pitches, 0.72 M events**.
- Two documented gaps. `leverageIndex` is null on exactly one play per game (the leadoff
  plate appearance), which `mlb_leverage` already handles. Substitution events carry the
  INCOMING player id; the outgoing player and the lineup slot exist only in the
  description text, so the lineage parser is a regex with per-season fixtures.
- `.cache/game_feeds` is **2026 MLB only** (2,108 files); everything else there is minors.
  So weather, home-plate umpire, batting order and bench/bullpen lists for 2018-2025 are a
  fetch: about 17,012 Final games at roughly 886 KB, **15.1 GB transferred, about 4.3 GB
  landed raw or 0.5 GB gzipped**. A stripped sidecar (gameData without the player bios,
  plus boxscore, linescore, decisions) is the landed shape.
- Environment: pyarrow 21, pandas 2.3.3, zstandard, lightgbm 4.6, scipy, sklearn; duckdb
  and polars absent; 704 GB free locally. A parquet star schema over the play stream lands
  **sub-GB** at normal zstd ratios, which is why the corpus is a build and not a purchase.

**M-CORPUS-1 Play and pitch star schema** (pbp_data-01, kept; effort M, no network).
Extend `tools/win_prob_walker.py` (which already walks the cache offline) into
`tools/build_pbp_corpus.py` writing partitioned parquet: `plays` (game_pk, season, date,
half, inning, outs, base state before and after, batter, pitcher, batter side, pitcher
hand, event type, LI, WP before, WPA, runners moved), `pitches` (play key, index, call,
type, speeds, zone, coordinates), `events` (substitutions, steals, pickoffs, challenges,
with the raw description retained). Pre-pitch base-out state is **not** a first-class
field (`matchup.postOnFirst` is post-play), so the builder reconstructs it from
`runners[].movement` and pins the reconstruction against `playEvents[].offense` on a
fixture set; that reconstruction is the single most load-bearing piece of the corpus and
carries its own test.

**M-CORPUS-2 Game-context backfill** (pbp_data-02, kept; effort M, network). Fetch
`/feed/live` for 2018-2025 MLB Final games through `feed_cache` and land the stripped
sidecar: `gameData.weather` (condition, temp, wind), `gameData.officials` (home-plate
umpire), `venue.fieldInfo` (turf, roof, dimensions), `boxscore.teams.*.battingOrder`,
`bench`, `bullpen`, `pitchers`, plus linescore and decisions. Rate-limited on the existing
3.5 s throttle, resumable, one season at a time.

**M-CORPUS-3 Durability** (pbp_data-03, kept; effort S). The corpus and the historical
feeds go **outside** the pruners: `run_monthly._maybe_prune_cache` and
`deploy/nightly-build.sh`'s disk preflight both prune `.cache/win_prob`, and
`feed_cache.prune_old_feeds(max_age_days=400)` deletes by mtime, so a 20 GB archive that
takes days to refetch is currently one disk-pressure night from deletion. Add the corpus
dir to the exclusion list and to the backup list, and add a coverage artifact plus an
ingest-health row (pbp_data-07) so a silent loss is visible.

**M-CORPUS-4 Nightly incremental** (pbp_data-04, kept; effort S). A new step 6b4i folds
new win_prob games into the corpus and fetches their context sidecar; the daily path
already refreshes `mlb_leverage.fetch_season_leverage` through `bullpen_export`, so the
new games are on disk before the step runs.

**M-CORPUS-5 Derived management-state tables** (pbp_data-05, kept; effort M): lineup
lineage (slot to player over time, from the substitution ledger), the substitution ledger
itself (kind, in, out, slot, position, inning, pre-state), bullpen availability by day
(appearances, pitch counts, back-to-backs), and the run-expectancy and win-expectancy
tables the value engines share.

**M-CORPUS-6 Savant baserunning and catcher boards** (pbp_data-06, kept; effort S):
probe-first fetchers for baserunning run value, basestealing run value, catcher throwing
and catcher blocking. Sprint speed (2015-2026), OAA (2016-2026) and arm strength
(2020-2026) are already landed. **Catcher framing is probed and BLOCKED**: the Savant
framing leaderboard ignores every year parameter and returns the current season only, so
framing is a per-pitch model of our own (Part 2's metric lane) or nothing.

**M-CORPUS-7 Umpire table** (pbp_data-08, kept; effort S): home-plate umpire per game from
the context sidecar joined to called-strike residuals from the pitch table. Automated ball
and strike calls exist only in 2026 feeds and are flagged as a regime break.

### 3.1 In-Game Management: the module

Route `/management/`, nav child in MLB Modules, `build_management()` on the `build_pal`
pattern, sidecar `data/management.json`, client `assets/management.js` with a
`.mlbstats-sectionnav` tablist. Sections: Manager Ladder, Lineup Card, Pitching Decisions,
Running Game, Platoon and Splits, Rest and Health, Method.

#### The two engines every metric shares

**M-ENG-1 Plate-appearance outcome model** (mgmt_lineup-01, mgmt_pitching-02; kept).
`mgmt_pa_model.py`: for any (batter, pitcher, hand, date) return probabilities over
{uBB+HBP, K, out in play, 1B, 2B, 3B, HR} using **only data dated before the game**. Batter
rates from a Marcel prior plus season-to-date, platoon-shrunk toward the league split with
`w = PA_hand / (PA_hand + K_hand)`; pitcher rates the same way through `asREM` (the REM+
empirical-Bayes recipe with K 70 / 170 / 400 batters faced, applied strictly as of the
date, prior mean the previous season); combined by the odds ratio (log5), which
`proj_current.log5` already implements. This is the leak-free spine: every counterfactual
in the module prices through it.

**M-ENG-2 Win-expectancy and rollout engine** (mgmt_lineup-02, mgmt_pitching-03,
mgmt_baserunning-01; kept). Fit `WE[half, inning, outs, bases, score diff]` from the
corpus per season (diff clipped to plus or minus 10, extra innings pooled with a placed
runner flag for 2021 and later), empirical cell means shrunk toward a monotone smoother
with `k = 50` fitted by leave-one-season-out log loss. On top of it a 24-state base-out
Markov chain per half inning whose per-plate-appearance transition vector comes from
M-ENG-1, and a nine-slot lineup chain for whole-game quantities. A leverage-linear fast
path is allowed **only** where it is pinned to reproduce the exact rollout on a fixture
set.

**THE WEIGHTING RULE, and it is the thing that makes this a management metric rather than
an outcome metric.** Every decision value is
`DV = E[WP | decision] - E[WP | alternative]`, evaluated at the **pre-decision state**,
never the realized win-probability change. Realized WPA is carried separately as `mWPA`
and never enters a plus metric. Leverage Index is **not** multiplied on top: a high-leverage
state already moves win probability more by itself, so LI is a column for cuts and
stratification, never a weight. Where a family's counterfactual is a rate over future
plays rather than a single state (defensive substitutions), the value is priced in runs
and converted through the season's runs-per-win, and that exception is stated on the
metric.

#### Lineup and roster families

| id | metric | what it measures | counterfactual |
| --- | --- | --- | --- |
| M-LINE-1 | **ORD+ / ordWAR** | batting-order optimality | the best order of the SAME nine by hill-climb from the posted order, platoon-adjusted for the probable starter |
| M-LINE-2 | **NINE+ / nineWAR** | roster selection | the best feasible nine from the day's active roster at feasible positions |
| M-LINE-3 | **PLT+ / pltWAR** | platoon usage | advantage share captured against the feasible maximum given that day's roster |
| M-LINE-4 | **HAND+** | team performance vs LHP and vs RHP against expectation | decomposed into talent, deployment and residual so the deployment term is the only one that can reach MWAR |
| M-LINE-5 | **PH+ / phWAR** | pinch-hit decisions | three ledgers: taken, missed opportunity, double switch, each a rest-of-game rollout |
| M-LINE-6 | **PR+ / prWAR** | pinch runners | speed upgrade through the running-game models minus the bat given up |
| M-LINE-7 | **DSUB+ / dsubWAR** | defensive substitution timing | the inning the glove should have entered against the inning it did |
| M-LINE-8 | **REST+ / restWAR** | rest and health management | fatigue effect **measured first** (consecutive starts, day after night, travel from venue coordinates, age), value claimed only if the effect survives |
| M-LINE-9 | **TAC+ / tacWAR** | in-inning tactics: intentional walks, sacrifice bunts, challenges | expected-value ledgers per decision |

Two verifier-imposed disciplines ride these. First, **REST+ may not claim value before the
fatigue effect is measured**: stage A is a within-player regression of performance against
the M-ENG-1 expectation on consecutive games, day-after-night, travel and age with player
fixed effects, and stage B prices rest decisions only with the coefficients stage A
actually found. Second, **HAND+ is a decomposition, not a value**: only its deployment term
can roll into MWAR, and the residual never does, because a team hitting better than
expected against left-handers is mostly hitting, not managing.

#### Pitching families

| id | metric | what it measures |
| --- | --- | --- |
| M-PIT-1 | **BAE** Bullpen Assignment Efficiency | expected WP under the arm actually used against the best **available** arm, league-centered at matched leverage decile |
| M-PIT-2 | **HTV** Hook Timing Value and the Deep Start Index | starter removal against a fitted in-game deterioration model (times through the order, pitch count, velocity delta, runs allowed, batter side, pitcher fixed effects); the crossover plate appearance is where the reliever's expected WP first exceeds the starter's |
| M-PIT-3 | **CSV** Closer Selection Value | is the best arm the closer, and where does the best arm actually pitch (peak-leverage spot capture) |
| M-PIT-4 | **LPX** Lead Protection Above Expectation | holds against win expectancy at the moment the lead was taken, decomposed into bullpen quality and a manager residual; the comeback board is the same statistic from the other side |
| M-PIT-5 | **IBBV** | each intentional walk against the pitch-to-him counterfactual, chained through the on-deck plate appearance |
| M-PIT-6 | **XIM** Extra-Innings Management | pitcher choice and walk policy under the placed runner, on its own win-expectancy table |
| M-PIT-7 | **OUV** Opener Usage Value | opener games (first pitcher at most 9 batters, second records at least 9 outs; 3.2 percent of sides) against the conventional-start counterfactual |
| M-PIT-8 | mound visit and pitchout ledger | **measurement only**, no counterfactual value claimed |

**M-PIT-9 Availability model** (mgmt_pitching-12, kept) is the precondition for BAE, CSV
and XIM: "best available arm" is meaningless without a defensible availability rule. Pen
membership from the structured bullpen list where the context sidecar has it, else the
proxy (appeared for the club in the prior 10 days, or on the roster per the transaction
archive, minus injured-list players), with a fitted fatigue penalty on back-to-backs and
prior-day pitch counts. Every BAE row states which availability source it used.

#### Running game and tactics

| id | metric | what it measures |
| --- | --- | --- |
| M-RUN-1 | **p_hat** stolen-base success model | logistic on runner sprint speed (Savant, season-matched, missing-flagged), shrunk runner rate, pitcher pickoff rate, catcher caught-stealing rate, hand, count, outs, score, with a rules-regime term for the 2023 bigger-base and pickoff-limit change |
| M-RUN-2 | **GLI** Green Light Index | attempt rate where the margin `m = p_hat - p_break_even` is positive, attempt rate where it is negative, summed decision value on attempts, and **foregone value on non-attempts** |
| M-RUN-3 | **Send or Hold** | first-to-third, second-to-home, tag-ups and the rest, priced at the moment of the send; an out at third with two outs is judged by the expected value of the attempt, not by the result |
| M-RUN-4 | **Bunt Ledger** | bunt **attempts** reconstructed from pitch level (bunt trajectories, bunt-foul calls, two-strike bunt strikeouts), not only the sacrifice result tag, priced against swinging away |
| M-RUN-5 | **Challenge Yield** | challenges, overturn rate, WP recovered, timing against reviewable leverage; the 2026 automated ball-strike challenges are a separate regime |
| M-RUN-6 | **AGI** Aggression Index | a **style** axis (team propensity to act, net of state and margin) held strictly separate from the value axis, so an aggressive team is not scored as a good or bad one |
| M-RUN-7 | player companions | Runner Decision Value and execution for runners, Battery Suppression for pitcher and catcher pairs, from the same ledgers |

The one killed proposal in the whole workflow is the **hit-and-run proxy**
(mgmt_baserunning-06): the play-id link exists, but the verifier ruled that a
runner-in-motion inference cannot separate a called hit-and-run from a straight steal with
a swinging batter, so the metric would attribute a manager decision that may not have
happened. Recorded in the do-not-build appendix.

#### MWAR

**M-MWAR-1 Composition** (mgmt_lineup-12, mgmt_baserunning-12, mgmt_pitching-13; kept).
Every family emits one interface row: `{game_pk, season, team, decision_id, family,
state_key, li, wp_before, dv, er, baseline_avg, baseline_rep, attribution}`. `dv` is
decision value at the pre-decision state; `er` is execution residual (what happened minus
what was expected given the decision), which belongs to the players, not the manager.
Three baselines, all served:

- **MWAP** = sum of decision value, against a pre-registered **heuristic manager** (a
  written-down policy: closer in the ninth with a lead, no pinch hit for a regular before
  the seventh, steal only when the break-even is cleared by a stated margin, hook at 100
  pitches or the third time through).
- **MWAA** = against the league-average policy at matched states.
- **MWAR** = against a replacement policy, with the replacement offset pre-registered and
  scaled by games managed.

`mWPA` (realized) is a companion column and never a plus metric. Uncertainty is a nested
bootstrap over games. Attribution splits shared families (a defensive substitution is
partly a front-office roster fact) at a stated weight rather than silently assigning all
of it to the manager.

**M-MWAR-2 Manager entity** (mgmt_pitching-14, mgmt_lineup-13, mgmt_baserunning-13; kept).
`manager_source.py` queries `/teams/{id}/coaches?date=` on opening day and the last game
date per team-season 2018-2026 and **bisects on schedule dates** when the manager differs
(about 8 calls per change), landing `data/managers.json` keyed by mlbam person id with
interim flags and a hand-curated fallback file for any season the endpoint cannot answer.
Mid-season changes split the season at the correct game.

**M-MWAR-3 Change-point test** (mgmt_pitching-15, kept). The honest validation that a
manager metric is measuring a manager: interrupted time series and difference in
differences around the 20 to 35 mid-season manager changes in 2018-2025, on BAE per game,
hook pitch count, intentional-walk rate, closer peak-share and mound visits. A metric that
does not move at a change point is measuring the roster.

**M-MWAR-4 Validation battery and gate** (mgmt_lineup-14, mgmt_baserunning-14; kept).
`docs/IN_GAME_MANAGEMENT_GATE.md` in the ARBITRATION_GATE shape (gates written before the
battery runs, a measured-first table, a later measurement overrides the doc and the
disagreement is recorded), `tools/mgmt_validation_lab.py` writing
`data/management_eval.json`. Four registered gates:

1. **Split-half stability**: odd against even games per team-season, Spearman, with the
   null band from shuffled decisions. A metric below its own null band does not ship.
2. **Manager persistence**: the same manager across team changes; the change-point test
   above.
3. **Placebo**: shuffle the decisions within matched states and confirm the metric
   collapses to zero. This is what separates decision quality from outcome luck.
4. **Captured share**: `(actual - heuristic) / (optimal - heuristic)`, reported so a
   reader can see how much of the available value the family even spans.

Any family failing 1 or 3 ships as **descriptive only**, with its board rendered and its
plus metric withheld, exactly as `leverage_board` does today.

### 3.2 Hall of Fame Modelling: the module

Route `/hof/`, nav child in MLB Modules, `build_hof()` on the same pattern, sidecars
`data/hof.json`, `data/hof_watch.json`, `data/hof_seasons.json`, `data/hof_careers.json`.
Sections: Predictor, Deserved vs Inducted, Cooperstown Leaderboards, Franchises,
Cooperstown Watch, Method.

**The provider pin that governs the whole module**: eWAR exists only from 2011
(`data/ewar.json` seasons 2011-2026), so every Hall of Fame number is on **bWAR**
(`war_source.stint_frame(side, provider='bwar')`), stated on the page and pinned by test.
The cached `war_daily` parquet is the spine: **126,518 batting stint rows across 49
columns and 57,849 pitching rows, 1871-2026, 23,650 distinct bbref ids**, with the full
B-Ref run decomposition. It carries **no counting stats and no positions**, so hits, home
runs, saves, wins and position come from Lahman or StatsAPI. Negro Leagues and the
nineteenth-century leagues are inside the frame (8,072 batting and 3,171 pitching rows
over 2,263 players) and are a policy decision, not an accident.

#### The data shelf

- **H-DATA-1 Lahman ingest** (hof_data.P01, kept; effort M). `pybaseball` 2.2.7 is
  installed and exposes the Lahman tables, but the mirrors are the constraint: SABR hosts
  the database behind share links (an owner file drop) and CRAN carries the R package.
  Ship it as a **file-drop source** on the `baseballamerica_csv.py` inbox pattern,
  bbref-keyed, joined through the Chadwick register, with a fixture so the parser is
  testable before the drop arrives.
- **H-DATA-2 Ballot panel** (hof_data.P02, kept; effort M). Every candidate, every year,
  1936-2026: `StatsAPI /awards/MLBHOF/recipients` is live and returns 354 rows over 85
  election seasons (inductees only); the **full ballot** with vote shares for
  non-inductees comes from the Baseball-Reference election pages, which are fetchable
  (`/awards/hof_2025.shtml`, 238 KB, 38 vote cells) and carry B-Ref's own HoF Monitor and
  HoF Standards columns as an answer key for H-DATA-4.
- **H-DATA-3 Career frame** (hof_data.P03, kept; effort L): per player-season WAR summed
  across sides from the parquet, plus the awards ladder from StatsAPI (MVP, Cy Young,
  Rookie of the Year, All-Star; winners only, no vote shares for non-winners) and
  positions from Lahman appearances. JAWS already reproduces from the parquet alone (Ruth
  182.6 career, 84.4 WAR7, 133.5 JAWS), which is the reproduction control.
- **H-DATA-4 The public benchmark shelf** (hof_data.P04, kept): JAWS, WAR7, Hall Rating
  and wWAR, Black Ink, Gray Ink, HoF Monitor, HoF Standards and the Keltner rubric fields,
  implemented in house so the module is **benchmarked against the public work rather than
  asserted over it**.
- **H-DATA-5 Flags** (hof_data.P06, kept): performance-enhancing-drug suspensions, Mitchell
  report, admitted or confirmed, banned, posthumous. A separate hand-maintained source with
  provenance URLs, **never inside the merit model**, only in the voter model where they
  belong.
- **H-DATA-6 Era, schedule and role adjustments** (hof_data.P07, kept): fitted on training
  years only, with a placebo that applies the fitted adjustment under permuted eras.

#### The Predictor

- **H-PRED-1 Label ledger** (hof_predictor-01, kept). Two labels with explicit resolution
  rules: `L_bbwaa` (elected by the writers inside the player's own ballot window, resolved
  when the window closes by election, by falling under five percent, or by exhausting the
  ballot) and `L_any` (inducted by any route, including the veterans committees). **A
  censored player never carries a zero**, pinned by test, and a censoring sensitivity table
  ships beside the model.
- **H-PRED-2 Point-in-time feature frame** (hof_predictor-02, kept). `as_of(player,
  cutoff)` computed strictly from seasons at or before the cutoff: career WAR, WAR7, JAWS,
  WAA, positive-WAA sum, in-house WAR ink (four points a league-leading season, one a
  top-ten season), awards rate, milestone counts, position class, era columns. The
  point-in-time test is that `as_of(player, Y)` equals the same call against a frame
  physically truncated at Y.
- **H-PRED-3 Merit model** (hof_predictor-03, kept). L2 logistic champion against a
  monotone LightGBM challenger, per label, forward-chained **by election year**, with a
  calibration-first gate: discrimination non-inferiority against the best public baseline
  (measured today: JAWS AUC 0.959, career WAR 0.962, positive-WAA sum 0.963, so the bar is
  high and the honest expected outcome is a tie on AUC with a calibration win), then Brier
  and expected calibration error, then class-wise tables.
- **H-PRED-4 Voter model** (hof_predictor-04, kept). Vote share and election probability
  with the merit logit frozen per fold and the flags entering as **separate disclosed
  terms**, so the module can say "this is the on-field case, and this is what the ballot
  did with it" and quantify each flag as a discount in vote points.
- **H-PRED-5 Ballot trajectory hazard** (hof_predictor-05, kept): discrete-time hazard over
  ballot years for candidates already on the ballot, giving probability of election within
  the remaining window and an expected election year, against the persistence null
  (carry-forward of last year's percentage).
- **H-PRED-6 Career arc** (hof_predictor-06, kept; effort L): 2,000 Monte Carlo careers per
  active player, a continuation hazard (age, recent rate, exposure, role, health) then
  conditional WAR steps from the `fa_projection` aging curves and the `fa_market` decay
  path, validated on retired cohorts (birth years 1945-1985) by projecting at ages 27, 30
  and 33 with curves fit only on prior seasons.
- **H-PRED-7 Health as hazard covariates only** (hof_predictor-07, kept): games-share is
  the only all-era health proxy available from `war_daily`; injured-list days exist from
  2015 and Tommy John from the surgery sheet, both entering the **continuation hazard**
  and never the merit score, with a placebo and a coverage disclosure.
- **H-PRED-8 Path and counterfactual** (hof_predictor-08, kept): years to eligibility,
  milestone distances, the WAR needed to reach the positional standard and to reach
  probability one half, and the seasons that would take. Monotonicity is a test, not a
  hope.
- **H-PRED-9 Cooperstown Watch** (hof_predictor-09, kept): active players aged 32 or under
  with at least three seasons whose cumulative WAR through their current age clears the
  inductee twenty-fifth percentile curve, or whose modelled probability clears five
  percent. The served number is **Cooperstown Pace**, the percentile of the player's
  cumulative WAR against the inductee curve at the same age.
- **H-PRED-10 Age-conditional comparables** (hof_predictor-10, kept): k nearest players
  through the same age with their final outcomes, which doubles as the **nonparametric
  null the model must beat** on Brier to serve.
- **H-PRED-11 Benchmark bake-off** (hof_predictor-11, kept): every public rule scored twice
  in the same folds, raw (AUC) and Platt-scaled on training years only (Brier, log loss,
  calibration error), so the gate is defined against the best public rule rather than
  against nothing.

#### Leaderboards, deserved-vs-inducted, franchises

- **H-LEAD-1 The frame** (hof_leaderboards-01, kept): eligible universe = at least ten
  seasons with a WAR row and last season at least five years back (**3,552 players** on the
  proxy cut), position classes {C, MI, 1B/DH, OF, SP, RP} with relievers split at a 0.7
  relief-innings share, and a Hall-sized line per class shrunk toward the pool. The JAWS
  line reproduction (**183 inductees above 44.2, 84 below, 102 non-inductees above**) is
  pinned as a fixture so a frame refresh that moves it is visible.
- **H-LEAD-2 WAR162** (hof_leaderboards-02, kept): schedule-neutral season WAR, prorated on
  an empirical-Bayes **rate** rather than on the raw total, so 1981, 1994 and 2020 are
  handled without inventing production. Bounded and monotone by test.
- **H-LEAD-3 nWAR** (hof_leaderboards-03, kept): era-neutral season WAR = WAR162 times a
  league-strength factor from the **dispersion estimator** (the qualified pool's robust
  spread against a modern reference), normalized to 1.0 on 2000-2019. The two-way
  simultaneous fit was **refused as unidentified**; the sign checks are pre-registered
  rather than fitted: the factor must dip in 1943-1945, 1884, 1890 and 1914-1915, and dip
  less at each expansion.
- **H-LEAD-4 DOM** (hof_leaderboards-04, kept): a season's standing against its own
  contemporaries (robust percentile, shrunk for thin early pools, plus the crown margin
  over the second-best season).
- **H-LEAD-5 PWV** (hof_leaderboards-05, kept): Peak-Weighted Value, a concave rank-decay
  kernel over career nWAR (weights from 1.0 at the best season to an asymptote of 0.5) that
  **nests JAWS as a special case**, and must beat JAWS, career WAR and positive-WAA sum on
  forward-chained induction AUC to ship.
- **H-LEAD-6 CIX** (hof_leaderboards-06, kept): the **Cooperstown Index**, PWV expressed
  against the Hall-sized class line, 100 = the line. The model-implied Hall is
  `CIX >= 100`, and because the line is Hall-sized by construction the roster difference
  with the actual Hall is a like-for-like swap list rather than a wish list.
- **H-LEAD-7 IRES and the over/under-rated lists** (hof_leaderboards-07, kept): the residual
  of induction against the merit probability, with performance-enhancing-drug and ban flags
  kept **out** of the merit number and shown beside it, so the module distinguishes "the
  voters disagreed with the record" from "the voters applied the character clause".
- **H-LEAD-8 Cooperstown Seasons and Careers** (hof_leaderboards-08, -09; kept): the
  greatest-seasons and greatest-careers boards including non-inductees, with era, side,
  class and franchise filters, and a stack-up view comparing up to four players or seasons
  against the class line.
- **H-LEAD-9 Keltner fields** (hof_leaderboards-10, kept): the Bill James rubric answered
  from the frame as display columns (best in baseball seasons, best at class, MVP-type
  seasons), never summed into a score.
- **H-LEAD-10 OCT** (hof_leaderboards-11, kept): the October layer, postseason win
  probability added from the corpus for 2018-2026 and a lighter runs-above-average proxy
  before that, **disclosed beside the index and never inside it**, registered
  measurement-only on the `leverage_board` precedent.
- **H-LEAD-11 FHP** (hof_leaderboards-12, kept): Franchise Hall Production on a StatsAPI
  franchise spine (151 season calls, 179 of 179 bbref team ids mapped, with the 1901
  Baltimore club explicitly not the modern Orioles), crediting by team-seasons and by nWAR
  share, and splitting **developed against acquired** on debut organization.
- **H-LEAD-12 Gate and battery** (hof_leaderboards-13, kept):
  `docs/HOF_LEADERBOARDS_GATE.md` written before the battery is read, with induction
  agreement, era stability, JAWS and Hall Rating sanity, and a **documented departure
  list** where the new index disagrees with the public ones and why. A metric that cannot
  say why it disagrees does not ship.

### 3.3 What these two modules give back to the rest of the platform

The corpus is not a private input. `mgmt_pa_model` is the same matchup engine Part 2's
props sub-models need; the win-expectancy tables are what a live-game surface would price
against; the umpire table and the availability model feed the betting totals and strikeout
props; the run-expectancy matrix is the missing piece under the Trade Machine's contention
window work; and the era-neutral nWAR from the Hall of Fame lane is the first
league-strength adjustment on the platform, which is directly reusable by the projections
module's cross-era comparisons. Both modules are therefore sequenced so the shared pieces
land first (M-CORPUS and M-ENG before any metric family), and both are listed in Part 4's
wave plan accordingly.

---

## Part 4. Sequencing, decisions, do-not-reopen

PENDING_PART_4
