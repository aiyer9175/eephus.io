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

Source: the modules-betting-audit workflow (9 census lanes, a completeness critic, adversarial verification of every new model and new metric proposal, and a synthesis stage that completed with all 72 agents green). Every number below is measured from a committed artifact, a gate document or code read during the census; anything marked PROPOSED is design, not measurement.

Basis note: every number below is MEASURED from a `data/*.json` artifact, a `docs/*.md` gate document, or code read during the census, with the citation attached. Everything labelled PROPOSED is design, not measurement. No claim in this document has been re-derived; the executor should not re-run the census.

---

### 1. State of each module

#### 1.1 Betting: the honest vintage numbers

MEASURED, `data/betting_model_eval.json` generated 2026-09-05.

The honest (vintage) mode graded 472 games over 2026-08-01 to 2026-09-04 and, for the first time, beats the home-constant baseline: Brier 0.24398 vs 0.2482, log loss 0.68104, accuracy 0.5678, total_mae 3.546, paired skill delta +0.004221, sd 0.04457, t 2.058, `beats_baseline_95` true (`betting_model.py:2310` `_paired_brier_skill`). Benchmark ladder on the same window: literature Elo 0.2442 (`tools/betting_elo.py:40-51`), home constant 0.2482 at p 0.5424. On the 239-game subsample with a cached open capture, market open de-vig reads 0.23175, Elo 0.24307, model 0.24462, home 0.24842. `market_close_devig` n 0.

Three qualifications the plan is built around.

1. The skill is carried by a near-constant predictor. 463 of 472 predictions lie inside 0.4-0.6; the model under-predicts home (mean_p_home 0.5162 vs a 0.5424 rate) and is under-confident in the 0.5-0.6 bin (pred 0.5336, actual 0.5773). Paired sd is 0.0446 against the contaminated mode's 0.0865.
2. The coefficients it grades with are wrong-signed. Vintage fit on 610 design rows: b1 (offense) -0.0372, b2 -0.0965, b3 0.5948, b4 0.1494, r2 0.0030, `diff_shrink` 1.28 (an EXPANSION), `home_field_runs_adj` -0.0443. The contaminated 4,248-row fit reads b1 +0.2603, b2 -0.3146, b3 3.4387, `diff_shrink` 0.78. Split sensitivity moves `diff_shrink` 0.76 to 1.28. Fit is unregularized `lstsq` with no sign constraint, window pinned at `VINTAGE_FIT_TARGET_GAMES = 300` (`betting_model.py:471`, `:1979-2010`).
3. The model is 0.0129 Brier behind the open market on the same games. No positive-EV moneyline claim is available from accuracy alone.

Gate states (`data/betting_model_eval.json -> min_edge_gate.gates`): `vintage_sample` 472/600, closed; `out_of_sample_skill` OPEN (t 2.058); `graded_price_history` closed, board_all n 214, ROI -0.12649, lower-95 -0.23428 at every threshold 0.005-0.06. The vintage clock ticks 8.81 graded games/day, ETA 15 days to 600 (`data/betting_learning.json latest.clocks.vintage_sample`).

Ledgers. Shadow: 255 rows, 223 settled, net -29.257 units, ROI -13.1%; moneyline 44 settled ROI -27.4%, runline 74 ROI -3.2%, total 105 ROI -14.1%; by slot board_all -15.3%, ev_rank -4.6%, potd_band -14.0%, longshot -22.5%. Model Brier on settled non-push rows 0.2706 vs market-fair 0.2461. Side skew: totals 102 over vs 19 under. Calibration ledger: 996 priced rows folding from 1,894 events, 890 settled, zero close prices, 15 slate days. Market gate on canonical sides: moneyline n 143 Brier 0.243233 t -0.987; runline 141, 0.268314, t +1.388; total 139, 0.269161, t +2.057, `worse_than_coin_95` TRUE, `ledger_closed` since 2026-09-03T15:21. The total's canonical OVER model probability is 0.5674 against a market 0.4993 and a 0.4654 hit rate, bias +0.102.

The level defect is separately visible on the live board: model fair total exceeds the posted consensus by +0.854 runs on average (n 15, median +0.92), with b0 4.4777 against `lg_rpg` 4.4809 and no calendar, weather, day/night, roof or umpire term anywhere in `expected_runs` (`betting_model.py:1160-1230`).

Dispersion (`run_dispersion`, alpha 0.2812-0.28413): moneyline lb95 -0.000231 PASS, runline both sides +0.009502 t 2.431 PASS, total +0.004875 t 1.41 FAIL, runs +0.198285 PASS, verdict INDETERMINATE, unserved. Shape facts: P(|margin|=1) observed 0.2721 vs Poisson 0.2503 vs NB2 0.1917; P(|margin|>=5) 0.2986 vs 0.1390 vs 0.2897; home -1.5 covers 0.3442 vs away -1.5 0.3768.

Plumbing. 22 odds snapshots, all `open`, 15 of 29 calendar days, capture times 15:16-23:19 UTC, 9 of 500 credits used this month, planned 186 (`data/betting_status.json`). Props machinery complete and INERT (`betting_export.py:2808`, `betting_settle.py:263`, `betting_ingest.py:97`), zero props rows anywhere. Public record empty: `record.jsonl` 0 lines, `betting_record.json` [].

#### 1.2 MLB Stats

MEASURED forward-chained Y to Y+1 Spearman: REM+ 0.2363 vs FIP 0.211 vs ERA 0.0901 (n 878, gap lo95 +0.0013); SEM+ 0.4167 vs FIP 0.3821 (n 592, lo95 +0.0177); HEM+ 0.4119 vs OPS 0.4108 and raw wOBA 0.4087 (n 3,372, gap lo95 -0.0126, i.e. HEM+ TIES the public-shaped baselines and beats only AVG); xHEM+ 0.4543 (n 1,871, lo95 +0.0173); fwdHEM+ 0.4658; pWOBA 0.5189 vs best incumbent 0.4939; gmLI Y to Y+1 0.4683, split-half 0.5294; aStuff+ pitcher-level r 0.2797. REM+ split-half by TBF bin 0.179 / 0.342 / 0.424 (`data/rem_plus_eval.json`, `sem_plus_eval.json`, `hem_plus_eval.json`, `xhem_plus_eval.json`, `phem_marcel_lite_eval.json`, `leverage_consistency_eval.json`, `stuff_plus_aaa_eval.json`).

Registry hygiene defects: WAR/IP+ (SP) 3yr serves while its gate is false (`data/war_rate_plus_multiyear_eval.json gates`); `war_pa_plus`, `war_ip_plus_sp`, `war_ip_plus_rp`, `xrem_plus`, `xsem_plus` are `unvalidated` with `eval_artifact` None; HEM+ has never been compared with the published wRC+ it displays beside.

What betting actually consumes: three team columns (`offense_plus`, `rotation_plus`, `bullpen_plus`), per-pitcher `sem_plus` and `ip_per_gs`, and a Savant park runs index (`betting_model.py:537-612`, `:1132-1158`, `:711`). Nothing else on the boards reaches a price. On honest features the offense term is null to negative (b1 -0.0372).

#### 1.3 PAL

Two frozen-prior weighted blends, no fitted weights (`pal_conversion.py:57-75`). Gate record: SP to RP PASSES (rho 0.2916 vs best baseline -0.097, gap lo95 +0.0745, n 61); RP to SP FAILS sign-wrong (-0.2062, n 25). Expanded game-log cohort: SP to RP 0.3607 (n 100, lo95 +0.4647), RP to SP -0.1736 (n 35). `docs/e3-rp-sp-closure.md` bans re-gating RP to SP by expanding the event set (MDE +0.356 at n 35; n 100 arrives ~2037).

Live defect: `pal_export.load_bref_pitcher_war` now reads eWAR v2, and `data/pal.json backtest.per_direction` reads RP to SP 0.025 and SP to RP 0.278, while `data/pal_eval.json`, the registry, the glossary and the closure doc all cite -0.2062 / 0.2916. The served scorecard copy is hard-coded (`assets/pal.js:632-660`), so it prints "does not validate ranking" regardless of payload. The failed direction is also the homepage teaser and the default tab (`build_site.py:2965-2980`, `assets/pal.js:27`).

#### 1.4 FA

Gate 1 (`data/fa_gate1_eval.json`): pooled WAR MAE 0.5736 vs 0.7279 baseline, n 20,721, all four gates true, but hitter bias -0.132 and the star cells LOSE to the naive 5/4/3 baseline (hitters actual >= 4 WAR: 2.96 vs 2.37, bias -2.93, n 424; pitchers 3.27 vs 2.94, n 186). Gate 2 (`fa_gate2_eval.json`, 2026-08-19): guarantee MAE 9.690 vs comps 11.120, AAV 2.909 vs 3.249, years 0.4329 vs 0.4871, megadeal slice 79.81 vs 95.27, n 1,199; loses to comps on guarantee in 2021 and 2022 and on the mega slice in five winters. Guarantee bias by predicted tier: lt10 -2.18, 10to20 -7.50, 20to50 -12.88, ge50 -23.46; by ACTUAL tier ge50 -43.0 (n 102). The twelve largest misses are all megadeal under-predictions (Seager -254.9, Cole -201.8, Harper -196.2). Gate 3 (`fa_gate3_eval.json`): live_analog MRR 0.1669 vs payroll_only 0.1350, fitted_full with incumbency 0.2679 (excluded by design); TEAMFIT CONDITIONAL is LIVE. Noise floor: pooled guarantee MAE ~0.16 $M; feature arms unresolvable below ~0.07 $M, level arms below ~0.33 $M (`data/fa_lane_eval.json noise_floor`).

Live defect: the committed gate-3 `concentration` block still carries the 2026-08-04 class (max_top1_share 0.5746 LAD, tripwire RED) while the served board reads 0.2371 with distinct_top1 15, GREEN on all four criteria. That is a regen, not model work.

#### 1.5 Projections and Trade Machine

Projections: `team_outlook_eval.json forward_gate` is pending, first scoreable end of 2027. A current-season simulator already ships: `proj_current.simulate_playoffs` (MC_SIMS 2000, MC_HOME_EDGE 0, seed 12345) over `remaining_pairs`, fed by `_attach_current_season` with a k = 40 pseudo-game blend (`proj_export.py:1715`, `:1807-1900`). It stops at the playoff field: no bracket, no pennant, no win-total PMF. It is fed the PURE talent prior (`proj_export.py:1887`) while the record-and-pythag blend computed at `proj_export.py:1784-1786` is a local that is thrown away. LAD `playoffPct` reads 1.001, a rounding artifact. `proj_lgbm` is the live challenger, row-matched edge h1 +0.014.

Trade Machine: `data/trade_machine_eval.json slice_a` pooled Spearman 0.3289 vs `baseline_consensus_fv` 0.3312, i.e. the board surplus does not beat consensus FV on rank; `docs/trade-2026-08-19/TRADE_FORWARD_GATE.md:146` records S2 |rho| 0.2635 BELOW a zero-information control band of about 0.63. `data/mlb_trade_players.json` prices 26 of 939 rows (`surplus_mm` non-null), `resolve_status == "found"` on 0. The veteran leg is effectively unpriced, which is why both market-implied lanes were killed.

---

### 2. The betting program

#### 2.0 Objective definition (lane B-OBJ, from bet_model-P01)

Owner decision 2 says accuracy AND ROI. Give it a definition the gates can read, per market, BEFORE any sub-model is fitted. Pre-register as section 7d of `docs/diamond-betting.md`, then compute a `per_market` block in `betting_model_eval.json`:

- ACCURACY leg: paired Brier and log loss on the vintage eval window against three ladder tiers, always including the same-games market-open tier (`benchmarks.tiers`, n 239 today).
- ROI leg: flat-stake ROI with the existing one-sided 95% lower bound (`sweep_min_edge` form), plus expected log growth at quarter-Kelly on the recorded price. CLV is written as a single key `clv_unavailable` with the reason "close job never installed; 0 of 898 settled ledger rows carry close_decimal", not as a null column.
- COMBINATION rule: a market may set a threshold only if its accuracy leg is non-inferior to the market-open tier on same games (paired Brier lb95 >= -0.002) AND its ROI leg clears lb95 > 0 at n >= 100 within one (market, rule) cell.
- FLOORS: 100 canonical games per market for the calibration leg (mirrors `GATE_MIN_GAMES`), 100 settled rows per (market, rule) for ROI.

Effort M, measurement only, no served number moves. It is the prerequisite for every other betting lane because it stops a totals-heavy pooled ROI standing in for the moneyline's.

#### 2.1 Wave 0, plumbing that starts clocks (do first, in parallel)

**B-CORPUS (bet_model-P11 merged with props_futures-01), effort M.** One pass over `.cache/win_prob` (19,132 files, 20.02 GB) emitting three durable tables: per-PA rows (game, date, inning, half, batter, pitcher, batSide, pitchHand, menOnBase, outs, score state, eventType, TB, earned flag, EV/LA/trajectory/spray, LI, times-through-order, inferred slot), per-game per-player lines (PA/H/TB/HR/K/BB; BF/outs/K/BB/H/HR/ER plus starter flag), and per-game rows (final score, per-inning runs for the F5 and NRFI labels, starters, first pitch). Join home/away org and venue from one cached StatsAPI schedule call per season. Acceptance: per-season counts match the census (2431/2429/2429/2430/2430/2429/2430/2124, no 2017 or 2020), and per-game K and HR totals reconcile exactly against box scores for every game that has both a feed and a play stream. TRAP, from `tools/prune_cache.py:52-56` and `run_monthly.py:955-975`: `win_prob` and `game_feeds` are both in `SAFE_CACHES` and can be pressure-pruned. The output must live outside `SAFE_CACHES` with a coverage manifest, and nothing served may depend on the raw cache surviving. This unblocks B-RUNLINE, B-TOTAL, B-F5, B-FORM, all props sub-models and the futures backtest.

**B-VERIFY-FEEDS, effort S, do before B-CORPUS finishes.** The census and two verifiers disagree about `.cache/game_feeds`. Census F06/F13 report MLB sportId 1 only for 2026 (2,108 games); one verifier's 150-file sample found MLB feeds in 2023 (19), 2024 (24), 2025 (20), 2026 (87) with a named Home Plate official in 150 of 150; another verifier's 60-file sample found NO `officials` key at all and a 400-file sample found every MLB feed dated 2026. Run one deterministic census (sportId and season per file, presence of `gameData.weather`, `boxscore.officials`, `battingOrder`) and write the counts into the corpus manifest. Every weather, umpire and lineup lane downstream is scoped by that answer, and no lane may assume a season the census does not show.

**B-CADENCE (bet_model-P14), effort S.** Register the open snapshot as its own daily job at a fixed early UTC time (before the earliest first pitch), with the nightly build's capture demoted to a same-day no-op fallback, and extend the `vintage_capture_gap` sentinel to count missing odds days. MEASURED motivation: 15 captured days of 29, capture times spread 15:16-23:19 UTC, in-progress events dropped from pricing. Cost 3 credits/day, 93/month, inside the 500 budget with 9 used. This roughly doubles the accrual rate of every gate clock and every sub-ledger.

**B-SUBLEDGERS (bet_model-P03), effort M.** Add a first-class market dimension to the existing append-or-settle store: `summary()` gains `by_market` and `by_market_by_tag`; `graded_bets_by_market_tag` feeds `sweep_min_edge` keyed (market, tag); `MAX_PER_SLATE_BY_TAG` becomes per market so totals cannot absorb the `ev_rank` budget (today 121 of 255 rows are totals); `min_edge_gate` reports a per-market table; `resolve_min_edge` returns `{market: threshold}` with the 0.06 provisional floor per market. Rows are never retagged, so the cap change date-splits the series and the artifact must print the split date. Tests pin that pooled or cross-market rows can never set a threshold.

**B-MODELID (props_futures-13), effort S.** Stamp `model_id` on every props shadow and calibration row at write time, and make the fair-line block and the value block read ONE PMF, which closes the F02 defect where `props_fair_lines` prices 1+ hits as `1 - (1-p)^exp_pa` while `props_value_bets` prices the same market as a Poisson (`betting_export.py:2925-2930` vs `:3025-3049`). Zero props rows exist, so no migration is needed. Do this before any props sub-model.

**B-SORT (bet_model-P15 / props_futures-16), effort S. SHIPPED 2026-09-06, in a different
form than this lane proposed; what remains is optional.** Owner decision 5 is satisfied:
`wireSortableTables` in `assets/betting.js` makes every table the client renders sortable
with `aria-sort`, `role=button` headers, tabindex and Enter or Space activation, a
sorted-column mark, nulls sinking in both directions, per-table persistence in
`localStorage` inside try/catch, and idempotent wiring so a re-paint cannot double-bind.
The parser and comparator are exported as `window.EEPHUS_BETTING_SORT` and pinned by unit
tests plus a browser test that clicks a real header twice.

The difference from the proposal, stated so nobody re-does the work: this helper sorts the
RENDERED cells (with a `data-sort` attribute as the override) rather than refactoring the
nine string-built tables to build from row arrays. One generic wiring covers twelve tables
built from a dozen payload shapes, where twelve column specs would drift. The array
refactor remains worth doing on the two tables that will gain server-side sorting anyway
(the props value block and the per-market ledger views in B-SUBLEDGERS), and only there.

#### 2.2 Wave 1, repairs and the selection rule

**B-ML-FIT (bet_model-P04), effort S, highest accuracy leverage per hour.** Replace plain `lstsq` with a ridge fit shrunk toward `LITERATURE_COEFFS` with sign constraints b1 > 0, b2 < 0, b3 > 0, penalty chosen on the fit half by log loss, and let the vintage FIT window grow (all gradable games before the eval cut) instead of anchoring at 300. Report coefficient and `diff_shrink` stability at 0.6 / 0.7 / 0.8 in the artifact. Gate: paired Brier on the vintage eval window, non-inferiority lb95 >= -0.001 AND superiority over the Elo tier at t >= 1.645, at all three splits, log loss not worse; ship only if the tripwire test, the persisted block and the flag move in one commit. Not Platt (no response-scale map), not a market blend.

**B-TOTAL-LEVEL (bet_model-P06 stage 0), effort S, do BEFORE any totals feature work.** Refit the total intercept and level on the vintage fit half alone and re-measure the canonical total bias. A board-wide +0.854 run gap is a constant, and month, weather and umpire terms are each second-order. If the intercept closes most of it, the totals feature stack is unnecessary. Report the canonical over bias (+0.102 today) and the shadow over/under skew (102/19) after the refit.

**B-BAKEOFF (bet_model-P02), effort M.** Four rules become three: R1 prob-max inside `POTD_ODDS_BAND` (incumbent), R2 EV-max any market, R4 quarter-Kelly expected-log-growth rank. R3 (shrink toward the market fair probability) is DROPPED: the calibration ledger holds 143 distinct game_pk, under the 150-distinct-game blend threshold, so a selection-only shrink is the closed lane at insufficient n. Replay bases: the calibration ledger (898 settled rows, all carrying `model_prob`, `market_fair_prob` and `best_decimal`, markets total 326 / moneyline 286 / runline 286, props 0) and, for a leak-free accuracy read, the vintage window joined to open captures, restricted to the moneyline leg unless the captures are verified to carry runline and total lines. The n >= 100 picks gate is UNREACHABLE (one pick per slate, 14 settled slate dates 2026-08-09 to 2026-09-03); replace it with a paired per-slate design: score every rule on the same slates, report the paired per-slate ROI difference and one-sided t, and ship only at t >= 1.645 across at least 40 slates with chosen-side Brier not worse. Print a slates-to-gate countdown and label the lab NO-VERDICT below that. The ledger's model probabilities are season-to-date, so chosen-side Brier is a rule-vs-rule RELATIVE statistic only. The -4.6% ev_rank vs -14.0% potd_band comparison is cross-tag motivation, never evidence (`docs/diamond-betting.md:1323-1330` forbids pooling slot tags).

**B-LOGGROWTH (bet_model-P16), effort S.** Ship `log_growth_expected = p*ln(1 + f*(dec-1)) + (1-p)*ln(1 - f)` at f = the already-served `kelly_quarter` (`betting_export.py:3195-3196`), computed on the RAW served probability. No market shrink, no fitted reliability slope: Platt failed at all three splits and `diff_shrink` already absorbs the response scale (`docs/diamond-betting.md:2137-2138`), and the ledger's `model_prob` is range-truncated by the 0.06 edge floor so an outcome-on-probability slope fitted there is not identified. Any reliability term is gated behind 150 settled rows in that market plus an explicit selection correction. Stake stays flat on every ledger and the record; a test pins that no stake reads these fields.

**B-DARK4 (bet_model-P08), effort M.** Schema-4 dark capture, nothing served: (a) bullpen availability per club from feeds (pitches and appearances on D-1 and D-2, rolled to available high-leverage REM+ innings); (b) starter inputs already on the board (`k_pct`, `bb_pct`, `gb_pct`, `xwoba_against`, `fip`, `strike_pct`); (c) `high_lev_core_rem` and `leverage_deploy_plus`; (d) per-slot vl/vr orders with `hem_plus` and `platoon_adv`; (e) weather, dayNight and roof from a nightly schedule hydrate. Each column carries a `feature_basis` string. Every candidate then runs the 5c protocol verbatim: own runbook section written first, permuted-team twin, contaminated screen that can only disqualify, two-criterion vintage gate. Weather carries a stated observed-vs-forecast bias note and may not serve until pregame-captured rows score it on their own.

#### 2.3 Wave 2, per-market sub-models

**B-RUNLINE (bet_model-P05), effort L.** Keep expected runs from the moneyline model, replace the independent-Poisson margin with a conditional kernel p(d | lam_h, lam_a, home): a multinomial over margin bands with an explicit home walk-off redistribution, moving home margin >= 2 mass into +1 when the home team scores to win in the ninth or later. Recover p_home from the same kernel so the two markets cannot disagree. This is the successor `docs/diamond-betting.md:1979-1983` names ("a bivariate model with a one-run atom"), not the closed symmetric NB2. Four binding constraints: (1) FIT ON PRE-2026 FINALS ONLY, because 2026 rows are both the honest eval set and the 141-game canonical runline ledger arm; a 2026 refit is a sensitivity arm scored on a season split it did not see. (2) Moneyline non-inferiority is scored on the vintage-honest rows with lb95 >= -0.001 plus a tripwire test that fails if `beats_baseline_95` flips false. (3) Re-solve `diff_shrink` inside the challenger arm; holding it fixed double-shrinks the challenger and fails it for the wrong reason (`docs/diamond-betting.md:1988-1993`, 0.70 to 1.08). (4) Report the one-run band as a diagnostic row against the observed 0.2721. Gate: held-out runline both-sides log loss vs served Poisson, delta > 0 at t >= 1.645 at ALL of 0.6/0.7/0.8, plus the ledger arm on the 141 canonical games. Ship flips `market_is_publishable` for the runline ONLY, with the tripwire test in the same commit, and runline rows keep accruing throughout.

**B-TOTAL (bet_model-P06 stages 1-2 plus props_futures-06), effort L, only after B-TOTAL-LEVEL.** Stage 1a: calendar-month EB offset fitted on pre-2026 finals, the one dated-results feature that is vintage-safe by construction. Stage 1b: weather as dark capture only. The umpire leg is REMOVED from this lane into its own S-effort re-fetch lane, gated on B-VERIFY-FEEDS actually landing named officials for a counted number of games. Stage 2: do NOT pre-scope NB2 to the total; fit alpha and run the criterion PER MARKET at all three split quantiles, because the current artifact says the total leg FAILS (t 1.41) and the runline leg PASSES (t 2.431), the inverse of the 2026-08-09 reading. If a direct total-runs model is built instead of an offset, score P(over) at FIXED canonical lines (8.5, 9.5, and a 7.5-10.5 grid), never at the model's own median, with the shipped Poisson `total_distribution` as the primary comparator and the coin as a secondary floor; state that no historical book total exists before 2026-08, so no historical CLV, ROI or edge claim is admissible. Re-open of publication runs the existing 7b rule: canonical total bias inside +/- 0.03 and `worse_than_coin_95` false on three consecutive evaluations. Keep the market id `total`; do not introduce `total_v2` as a way around `market_is_publishable`.

**B-PROPS (props_futures-02/03/04, bet_model-P10), effort L, HR first.** Build `betting_props_models.py` as the single PMF source for both surfaces (via B-MODELID).

- HR: per-PA Bernoulli mixture over an integer expected-PA distribution. p_HR = sigmoid(EB-shrunk batter HR/PA + barrel% and pull-air from hitData + pitcher HR/FB and FB% + platoon + park HR index BY BAT SIDE (`fa_sources.py:532` already returns `index_hr` per venue by bat side) + bullpen share of PA), then P(HR >= 1) = 1 - E_PA[prod(1-p_i)]. Restate the incumbent honestly: it is `1 - (1-p)^exp_pa` with a FRACTIONAL exponent (`betting_export.py:2932`), not a Poisson, so the integer-PA mixture must be scored as its OWN ablation arm. The pitcher HR/FB term enters as a pre-declared ablation arm citing the X-R5 null (`data/model_registry.json:1008-1016`, gap -0.0025, lo95 -0.0228). Baselines: the incumbent formula and a league-mean per-PA constant. There is no market baseline for props.
- K: expected BF distribution (fitted per start, keyed on ROLE so openers and bulk arms do not break the prior) times per-BF K probability from pitcher K% shrunk toward CSW-implied K%, opposing lineup K% vs hand, platoon, park. K | BF ~ Binomial, marginal by convolution, priced at every half point with push conditioning. All historical rates must be recomputed as-of from play-by-play with a cutoff timestamp and a leakage fence test; leaderboard vintages start 2026-07 and are TEAM level, so no per-player vintage basis exists.
- Hits and TB: per-PA multinomial (1B/2B/3B/HR/BB-HBP/K/other out), TB by convolution, sharing the HR head so the three hitter markets cannot disagree about one player's night. OAA enters only as PRIOR-season team values in a pre-registered ablation arm.

Splits: fit 2018-2019 and 2021-2023 (2020 absent from cache), tune 2024, hold out 2025 once, sourced from `.cache/win_prob`. The K lane's window is bounded by whatever B-VERIFY-FEEDS says about `game_feeds` seasons. Live legs are BLOCKED on the owner setting `EEPHUS_PROPS_CREDITS`; register them as blocked, not as passable gates. The 100-canonical-game publishability floor is reachable within a month of arming for hitter markets (~10 players x 3 games x 10 pull days) and about two months for `pitcher_strikeouts`.

**B-PA-DIST (props_futures-14), effort S, prerequisite to the hitter props.** Fit PA per game by slot 1-9 from the corpus, split by home/away (ninth-inning censoring), run environment and extra innings; replace `SLOT_PA = 4.65 - 0.10*(slot-1)` (`betting_export.py:230`) only if the fitted table beats it on PA MAE. Start probability from the posted card when present (`fantasy_schedule.fetch_lineups`, 3 of 30 sides posted at today's build), else the DFS `start_rate`.

**B-PROPS-HARNESS (props_futures-15), effort M.** One backtest harness scoring any per-prop PMF the same way: log loss and Brier of P(over) at the line grid, CRPS on the count, reliability deciles, per-season sign check, paired bootstrap vs the incumbent, which is itself registered as `props_fair_lines_v0` so the baseline has a number. Artifact `data/props_model_eval.json` with mode labels and split dates; it must refuse to score a model whose split dates are missing, and it must state that "vs book" is live-only.

**B-MARKETSPEC (props_futures-05), effort M.** A new market currently requires six declarations, three test-pinned (`betting_ingest.PROPS_MARKETS`, `betting_export.PROPS_MARKET_LAMBDAS`, `betting_settle.PROPS_STAT_KEYS`, `betting_calibration.PROPS_CAL_MARKETS`/`CANONICAL_SIDES`/`GATE_MARKETS`, `betting_shadow.PROPS_TAGS`/`MAX_PER_SLATE_BY_TAG`). Introduce one `MARKET_SPECS` table from which all six derive, keeping the pins on the derived copies. Then add outs, earned runs, hitter K and hitter BB (box keys already exist). Re-register the credit arithmetic: at 8 markets x 1 region x 4 credits per event, the owner's 120/month cap buys about 5 pull-days instead of 10. That trade is an owner decision (section 6).

**B-F5 (bet_model-P07), effort M, dark, sequenced after a provider probe.** Price F5 moneyline and F5 total from the starter-only leg (no bullpen term). Labels from `linescore.innings` and from plays with inning <= 5. Two corrections: F5 ends TIED in 12.33% of games, so the market is three-way or push-on-tie and a binary paired Brier is ill-posed until the outcome space is declared; and the honest features are the same <= 777-game 2026 vintage window the full-game model occupies, so the F5 dark gate OVERLAPS and must not be counted as a second clock. Historical feeds may calibrate the F5 outcome base rate only. Add F5 to `grade_side` and update the pin at `test_betting_learning.py:590` to the new refusal boundary rather than deleting the guard.

**B-NRFI (props_futures-07), effort M, measurement first.** P(0 runs) per half from starter TTO1 quality and the top three hitters vs hand, park, home/away, month; NRFI as the product with one scalar correlation term fitted on train only and a pre-registered no-ship fallback to the independent product. Labels 2018-2026 minus 2020. TTO1 inputs must be recomputed on a trailing, prior-games-only basis; `tools/win_prob_walker.py:96` aggregates per pitcher-SEASON and is therefore contaminated for in-season games. First-inning markets are per-event additional markets in the same budget class as props (`betting_ingest.py:429`), so this does NOT ride the 3-credit daily call and ships model-only with no POTD eligibility until keys and budget exist. Settlement rules for suspended and shortened games are written before the first row, with a unit test on a truncated feed.

**B-POTD (bet_model-P13 / props_futures-08), effort M.** Owner decision 1. Candidates = every side on every market that clears its own (market, rule) threshold and whose market passes both publishability legs; rank on a cross-market comparable statistic chosen by B-BAKEOFF (EV lower confidence bound, or quarter-Kelly log growth), ties by price nearest -110. Props and F5 enter the same pool once their markets pass. The binding constraint is NOT the rank, it is the two exclusions at `betting_export.py:3871-3915`: the runline and total sub-models must clear their gates before an any-market slot can ever pick them. The new rule gets a NEW tag `potd_any`; `potd_band` is never retagged and keeps accruing as the old rule's record. `pick_meta` publishes the rule text, the per-market candidate census and the score basis. Model Watch framing and JSON key names are unchanged.

#### 2.4 Wave 3, futures

**F-A, modelled board (props_futures-09 arm 1 plus bet_model-P12 F-A), effort L.** Upgrade the EXISTING simulator; do not build a second one. (1) Return `forward_pct` from `_current_blend` (`proj_export.py:1784-1786`) and feed it at `proj_export.py:1887` in place of the pure talent prior, behind a stamped switch, publishing the served-vs-new `playoffPct` delta. (2) Set the home edge from a 2026 home win rate DERIVED from the corpus and stamped in the artifact, applied as a log-odds shift, not the current additive form at `proj_current.py:246`. (3) Add the bracket: wild-card best-of-3, LDS best-of-5, LCS and WS best-of-7, home field by seed, head-to-head tiebreaks stated as coin flips. (4) Emit a full win-total PMF (P(W > k) for every k) rather than two percentiles. (5) Raise sim count above 2000 or publish Monte Carlo standard errors: 2000 sims cannot resolve a 2% WS probability. (6) Fix `playoffPct` 1.001 by computing it unrounded and deriving `wildcardPct = playoffPct - divisionPct`, keeping `test_proj_current.py:104-106` green. DEFERRED to arm 2, behind the backtest: the rotation overlay and the availability draw. `ilOut60` is contractually display-only (`proj_export.py:1717`) and there is no calibrated IL-to-WAR map; an invented haircut is exactly the failure the 2026-09-04 health lane had to reverse.

**F-B, backtest (props_futures-10), effort L.** Replay 2018-2019 and 2021-2025 at six cutoffs per season (Apr 15 through Sep 1) on the actual remaining schedule. Four required corrections to the design: (a) build the game and postseason tables from the free StatsAPI schedule endpoint (`betting_model.py:1723`) and freeze them as a committed fixture, dropping the hand-entered results table; (b) the Elo baseline must be OFFSEASON-CARRIED and regressed, because the shipped ladder Elo starts flat each season by design (`tools/betting_elo.py:25-30`) and beating it in April buys no information; (c) any shrink constant is fitted leave-one-season-out or pinned as a literature prior; (d) n is 7 seasons, not 1,260 independent rows: cluster by season, use a season-block bootstrap, demote the WS gate to descriptive (7 positive events), and widen or drop the 0.9-1.1 reliability-slope gate. Gate on division-winner Brier (210 club-seasons) and P10-P90 win-total coverage. State plainly that this validates the bracket and blend machinery under a results-only prior and does NOT validate k = 40 or the roster prior.

**F-C, outrights ingest (props_futures-11), effort M, blocked on a probe.** Verify which MLB outright keys exist (world series winner is documented; pennant, division, season win totals, awards, first-inning periods are UNVERIFIED anywhere in the repo). Weekly snapshots, one credit per key per call, about 20 credits/month inside the 500 budget, with a monthly guard modelled on `props_spend`. De-vig proportional over the full field (the module's `devig` raises on any other method); a logit-shrink field de-vig is a diagnostic column only. The hold band `DEVIG_HOLD_MAX_PCT` must be re-registered per market or every book is rejected on 20-40% field holds. Fixture-verified parser; no test spends a credit.

**F-D, futures ledger (props_futures-12), effort M.** Append-only rows keyed (season, market, club, line, snapshot date), flat 1u, settled once at season end from final standings and postseason `gameType`, with a weekly mark-to-market column explicitly labelled as such and no CLV claim. Tests pin append-only, per-tag budgets, no pooling with team or props tags, and that nothing settles before the season's final day. The 2026 vintage yields roughly 150 settled calibration rows and 15-30 shadow rows, so no tag can reach n 100 before 2027-11: the section is Model Watch for its whole first season by construction, and the docs table says so.

**F-E, awards (props_futures-18), effort M, defer behind F-A/F-C.** Ship an UNFITTED monotone rule: rank by (WAR to date + projected rest-of-season WAR), convert the WAR gap to P(award) with a fixed, pre-registered softmax temperature chosen a priori. A fitted logit on 14 positive labels per award with three-plus features is unfalsifiable and repeats the in-sample calibration failure already on the record. The 2018-2025 winner set is a display-side sanity count ("ranked the winner first in k of 14 seasons"), never a coefficient. No edge column without a captured market. Registry row `awards_futures`, verdict unvalidated, stop clause: no ledger rows until 30 settled season-awards, and no fitted parameters on award labels below that.

#### 2.5 Credit budget

MEASURED: 500/month plan, 9 used, 186 planned, 491 remaining (`data/betting_status.json`). PROPOSED allocation: daily open at 3 credits = 93; close job, if the owner installs it, +93 = 186; futures weekly at about 5 keys = 20; props at the owner's 120 cap. Total 326 of 500 with the props cap intact. Adding three F5 or alternate-line keys to both captures costs about 372/month on its own and does not fit beside props and futures. That is the owner decision in 6.2.

---

### 3. New MLB Stats metrics, ranked

Ranked by (betting or valuation consumer) x (evidence available now) / effort.

**M1. PA and pitch fact table (mlbstats_metrics.P01), plumbing, effort M.** Same artifact as B-CORPUS; build once, serve both lanes. Acceptance gates: byte-identical reliever gmLI/WPA vs `mlb_leverage.accumulate` on 200 sampled games; season K/BB/HBP/HR/PA per pitcher within 0.5% of `load_season_pitching` for 2024-2025; per-game pitch counts within 1 pitch MAE of 2026 box `numberOfPitches`; a coverage table per season published as `data/mlb_pa_archive_eval.json`. Consumers: everything below, plus every betting sub-model.

**M2. xwOBAcon fitted on the archive (P02), new model, effort M as MLB-only.** Replace the hand-set KNN cloud (`statcast_metrics.py:560-601`, EV and LA only, no spray, hand or season) with a fitted per-BBE model. Ship as its OWN labelled column, never coalesced into the Savant column where Savant is absent, plus a fourth gate: per-player-season mean bias vs Savant within +/- 0.005 wOBA on the overlap so the two columns are readable side by side. Coverage argument is the payoff: Savant covers 436/649 hitters, 274/504 relievers, 180/226 starters. DROP the prospect and S-XLINE consumer swap entirely: the measurement-upgrade-into-eFV mechanism is already a measured null at AAA and at A-ball (`docs/efv-2026-07-23/GATES.md:196-231`, M-A delta -0.0035, CI95 [-0.0502, +0.0440]). Fix the data premise before pre-registering: the local MLB game-feed history may be 2026-only, so either restate the corpus as MLB 2023-2026 with disclosed reduced power or make the 2018-2022 feed backfill an explicit prerequisite and re-bump effort to L.

**M3. dRA, deserved runs allowed, with 14/30-day rolling form (P03), new metric, effort L.** K and BB as events with observed-K shrink-to-pool (the ONLY treatment the closed K-prior ledger allows), contact valued by M2, converted through an archive-derived run-expectancy table and recentred so the league sums to actual RA. Rolling forms EB-shrunk toward season then pool. IMPORTANT CORRECTION to the standalone claim: the season-level headline duplicates X-S4, already TESTED and REJECTED (xwOBA-allowed 0.377 vs FIP 0.382 on the same n 592 pool, gap lo95 -0.053), so the standalone gate should be stated as non-inferiority, not as a win. What is genuinely new and unmeasured is GAME-LEVEL RESOLUTION: SEM+ and REM+ are season-only by construction, and the betting model consumes the probable's season-to-date SEM+ (`betting_model.py:1189-1191`). That is the claim to gate, through the 5c protocol with a permuted-pitcher twin. Consumer: the pitcher term is where the vintage model's skill lives (b2 -0.0965 while b1 is negative), so this is the highest-leverage feature swap in the tree.

**M4. Archive-derived daily rolling team form (P04), improvement, effort M.** Replace the git-anchor differencing in `build_xwoba_windows`, which produced a NULL `xwoba_14` on 2026-09-05 and populated only 205 of 777 gradable games. Plumbing gate: on nights where the git builder produced a value, the archive builder matches within 0.010 wOBA on 90% of orgs. Feature gate: the pre-registered B3 protocol verbatim. Blocked on owner ruling 6.5 (whether archive-reconstructed columns may be written into existing vintage records with provenance).

**M5. Margin and clumping structure measurement (P17), measurement only, effort S.** Extra-innings home win rate by era, P(home bats in the ninth), bottom-ninth censoring share, inning-level run distribution, within-game run autocorrelation, empirical margin distribution by expected-run gap. Feeds B-RUNLINE and B-TOTAL with era-correct structure instead of literature constants and an era-aware tie rate instead of the 100-game prior. No gate; the consumer carries it.

**M6. Plate-discipline board for MLB, new descriptive surface, effort S, PROPOSED.** The feed's native `pitchData.zone` and call codes need no classifier, yet no MLB board carries CSW%, whiff%, chase%, z-contact% or in-zone%; the only MLB whiff figure served is reliever SwStr% from a bref pull. SwStr% is already sanctioned as a displayed peripheral, so these ship descriptive. Consumers: the K-prop sub-model and the player pages. Constraint: they may NOT enter the REM+/SEM+ skill cores (X-R1/X-R1b closed the K-prior lane permanently).

**M7. Bullpen availability index, new metric, effort S, PROPOSED.** No usage, fatigue, days-rest or pitch-count field exists anywhere in the tree. Reweight tonight's pen toward arms who can actually pitch, using per-appearance dates and pitch counts. This is a NEW estimand, distinct from the closed leverage-in-skill question (`data/rem_plus_eval.json leverage_variant_bakeoff`, best damping d = 0.0). Captured dark under B-DARK4 (a).

**M8. Park factors by hand, improvement, effort S, PROPOSED.** Today park is one Savant three-year rolling RUNS index per home org, 29 orgs, applied identically to both sides, no handedness and no HR-vs-runs distinction. `fa_sources.fetch_savant_park_factors(year, bat_side)` already returns `index_hr` by bat side and is already consumed by `fa_fit.py:136-160`. Consumers: the HR prop and the totals model. This does NOT reopen the park-shrink lane, which closed only the use of park as a SKILL-CORE shrink target.

**M9. HEM+ vs published wRC+ head-to-head, plus registry hygiene (P18), measurement only, effort S.** Add wRC+ as a baseline in the X-H1 harness (2021-2024 predictor seasons, the feed's coverage), re-gate or relabel WAR/IP+ (SP) 3yr, and give `xrem_plus`, `xsem_plus`, `war_pa_plus` real eval artifacts or explicit descriptive labels. HEM+ may lose; publish it either way. The EV/LA-by-age table is display-only and carries the loss-ledger note; the age hinge and EV residual arms stay closed.

---

### 4. PAL, FA, Projections, Trade Machine

#### 4.1 PAL

**PAL-1, epoch re-stamp (pal-01), effort S, do first.** Re-run the pre-registered gate on the served eWAR v2 label with identical events, seeds and baselines, plus a role-neutral RA9 sensitivity arm because eWAR centres FIP within role and a cross-role `war_delta` is a difference of two role-centred scales. Emit gate pass, best-baseline rho and n_gate into `data/pal.json backtest.per_direction`, and make the scorecard READ them (`assets/pal.js:632-660` currently hard-codes both verdicts). Reconcile the registry metric text, the glossary and an addendum to `docs/e3-rp-sp-closure.md`. Expected under eWAR, from the live stamp: SP to RP 0.278 (n 61) still passes, RP to SP moves from -0.2062 to 0.025, i.e. from sign-wrong to null, and still fails against an MDE of +0.356.

**PAL-2, serve the recovered cohort (pal-10), effort S.** Call `pal_gamelogs.recover_events` inside `export()` and concatenate the 89 recovered events as TAGGED rows (mid_year, swing_bridge), keeping the legacy set byte-identical under the existing `_identity_check`, and serve both n. History grows 115 to about 204; Burnes 2019 to 2021, King 2023 and Suarez 2021 stop being absent. Labelled a tagged sensitivity cohort until PAL-1 decides whether it becomes the gate set.

**PAL-3, gate document (pal-14), effort S, precedes any new PAL measurement.** Season-out folds (train <= T-1, score T, T in 2022-2025), sign check first, player-clustered bootstrap, v1 and v2 conventions, labels per direction, the loss-ledger rule, and the RP-to-SP FIT-vs-`war_delta` re-gate by event expansion listed explicitly as BANNED.

**PAL-4, serving fixes (pal-13), effort S.** Gate-derived copy, the validated direction as the homepage teaser and default tab (owner decision 6.7), sortable card grids reusing the existing helper, `generated_at` and cadence printed.

**PAL-5, measured priors (pal-09, pal-11), effort S each.** Replace the 1.0-2.2 mph role velocity prior with a within-pitcher, shape-conditioned measurement with player-clustered CIs, shipping the measured value only if its CI excludes the prior (precedent: the relief K bump measured 0.0167 against a 0.025 prior). Shrink the platoon read toward the league platoon mean by min-side TBF and move the 100 TBF gate from the client into the model; the raw unshrunk OPS split currently enters RP-to-SP at weight 0.12 and is one plausible source of the anti-signal.

**PAL-6, prospect watch confirmer (pal-12), effort S.** Join `prospects.db pitch_arsenals` (653 rows) and `stuff_plus_aaa.json by_type` (1,379) as an independent usage-based depth read with a "confirmed by tracking" chip and a published agreement matrix by FV band. Report-only, no ranking claim. Coverage on FV <= 44 arms will be thin and must be shown as such.

**PAL-7, display columns on the validated direction (pal-04), effort M, flagged.** Measured TTO leakage and shape-based platoon as COLUMNS. Any scored component swap is pre-registered against a held-the-role target, never against the FIT-vs-`war_delta` rank, and the pre-registration text must name the ban. Expect nulls at n 13-25 and report them as underpowered.

#### 4.2 FA

**FA-1, re-establish baselines on the eWAR label (fa-P01), effort M, prerequisite.** Gate 1 and Gate 2 numbers above were computed before the 2026-09-04 label epoch. Nothing else in FA may be compared until both are re-persisted on the served label, with the deltas published. Losses committed.

**FA-2, gate-3 concentration regen, effort S, defect.** The committed tripwire block reads the 2026-08-04 class (LAD 0.5746, RED) while the served board reads 0.2371 with distinct_top1 15, GREEN on all four criteria. Re-run `run_fit_gate` and update the `fa_team_fit` registry note, which still narrates the 68% LAD failure. This is a regen, not model work.

**FA-3, term and tier structure by partial pooling, effort L, PROPOSED.** The market model is a pooled two-stage OLS whose only group structure is three position dummies (`fa_market.py:1396-1470`, `:1628-1700`). Hard splits already lost (`fit_group` 10.72, `POS_GROUP_MODE` v2 +0.392, both wrong-signed) BECAUSE they thin every neighbourhood, which is what partial pooling avoids, so a hierarchical model is a genuinely new class rather than a costume. Target: the ge50 tier, bias -23.46 by predicted tier and -43.0 by actual tier, and the years tail (Correa +11, Harper -8). Re-open terms are already written in `docs/fa-2026-08-19/PTIER_LEVEL_GATE.md`: paired bootstrap B >= 200, clauses stated against the bootstrap null band, and the ge50 sparsity (fitted in 3 of 9 outer folds) confronted head-on. Guardrails: the noise floor is ~0.16 $M pooled and ~0.33 $M for level arms, so any headline below that is a coin flip, and every arm needs the permuted-label control that caught P-1 (its control also improved mean|bias|).

**FA-4, hitter level regression, effort M, PROPOSED.** Gate 1 hitter bias -0.132 (mean pred 0.503 vs actual 0.635) is the disclosed level regression that has never been gated, and it flows into every served price through `war_y1`. Gate: pooled MAE not worse, hitter bias inside +/- 0.05, star-cell MAE not worse than the current 2.96.

#### 4.3 Projections

**PR-1, expose the blend seam, effort S.** Return `forward_pct` from `_current_blend` so the shared engine can consume the record-and-pythag blend instead of the pure talent prior. Publish the served-vs-new `playoffPct` delta.

**PR-2, the simulator upgrade** is F-A above; it belongs to the shared engine, not to a projections-only lane.

**PR-3, discipline unchanged.** Never sum ML quantile heads; team roll-ups sum champion means; star-blend h2 stays forbidden; `team_outlook_eval` forward gate remains pending and first scoreable end of 2027, so nothing in the futures section may claim it validates the projection prior.

#### 4.4 Trade Machine

**TM-1, price the veteran leg, effort M, prerequisite to everything else.** `data/mlb_trade_players.json` prices 26 of 939 rows and resolves 0. Until that is fixed, no two-sided package arithmetic is computable, which is why both market-implied lanes were killed. Deliverable: a resolution and pricing pass with a published coverage number, no new model.

**TM-2, state the rank verdict honestly, effort S.** `slice_a` pooled Spearman 0.3289 vs `baseline_consensus_fv` 0.3312, and the forward instrument reads S2 |rho| 0.2635 below a ~0.63 control band. The surplus board's rank claim should be labelled accordingly wherever it appears. No new TM model this cycle.

---

### 5. Cross-module shared engine

One team-strength and season-simulation engine, one artifact, three consumers.

Inputs: club strength = the `_current_blend` forward rate (talent prior at k = 40, actual record, Pythagenpat), the live remaining schedule from `proj_current.remaining_pairs`, and a home edge derived from the corpus and applied in log-odds. Outputs: per-game p, per-club win-total PMF, division, wildcard, playoff, pennant and World Series probabilities, and a seed distribution, at a sim count high enough to resolve 1-2% events, with Monte Carlo standard errors published.

Consumers:
1. Projections `team_outlook[].current`, which today reads a MC fed by the pure talent prior.
2. Futures F-A, F-C and F-D, which need the same numbers plus the bracket.
3. DFS, which already derives book-implied team totals per game (`data/dfs.json games[].vegas`) and can carry the engine's per-game p as a free cross-check tier.
4. Betting, as a benchmark tier only: the engine's per-game p is NOT a served price and must never enter `game_probabilities`. The honest betting model's offense coefficient is near zero, so the two objects are measuring different things and pooling them would launder a projection prior into a market price.

The failure mode to design against is two simulators disagreeing about the same club on the same night. Enforce it structurally: one module owns `simulate_playoffs`, one artifact carries the numbers, and any surface showing a playoff percentage reads that artifact. When F-A changes the served `playoffPct`, publish the delta rather than letting two versions coexist.

---

### 6. Owner decision queue, with defaults

**6.1 Capture set and credits.** Adding first-5-innings or alternate-line keys to both captures costs about 372 of 500 credits a month on its own. DEFAULT: do not add them; run the daily open at 3 credits (93/month), keep props at the 120 cap when armed, and take futures weekly at about 20. Revisit after the provider probe.

**6.2 Props arming.** `EEPHUS_PROPS_CREDITS` is unset on every box, so no props evidence can accrue and the props ROI leg is unscoreable. With the expanded market set at 8 markets, the 120 cap buys about 5 pull-days a month instead of 10. DEFAULT: arm at the existing 4 markets and 120/month first, add markets only after the HR model clears its dark gate.

**6.3 CLV.** The close cron has never been installed anywhere; it is an owner action and a closed lane. DEFAULT: treat CLV as optional in every ROI gate and print `clv_unavailable` with the reason, rather than a null column.

**6.4 Corpus location.** The reduced tables must not live in `tools/prune_cache.SAFE_CACHES`. DEFAULT: a new non-prunable cache directory plus a committed coverage manifest, not `data/` (size), and the prune list updated in the same commit.

**6.5 Archive-reconstructed dark columns.** 5c rule 2 counts accrual NIGHTS, but a column reconstructed from dated plays is leak-free by the same construction argument 5a used for the git backfill. DEFAULT: allow reconstruction into existing vintage records with provenance `archive-reconstruct` and `covers_through` = last play date, so the B3 and B4 first looks are not gated by the 2026-08-20 clock. If refused, M4 ships as a forward-only builder and the B3 look slips.

**6.6 Runline and total exclusion bar. ALREADY DECIDED BY THE OWNER AND SHIPPED, and the
analyst dissent is recorded rather than presented as a live default.** The owner's
instruction on 2026-09-05 was explicit: the Pick of the Day is not locked to the
moneyline, spread, moneyline, overs and unders and player props are all allowed, find the
best pick. That is implemented as `betting_model.SLOT_MARKET_POLICY = "any"` (Part 0.2,
docs/diamond-betting.md section 7d): no market is barred, and the dispersion caveat and
the section 7b ledger evidence ride the published row as disclosure.

THE DISSENT, worth having on the record because it is a real cost and not a quibble. The
markets now eligible are the ones with the worst measured evidence: the total's own
canonical settled games resolve worse than a coin (Brier 0.269161, t 2.057,
`worse_than_coin_95` true, ledger-closed since 2026-09-03) and carry a +0.102 over bias,
the runline sits at 0.268314, and the margin model that prices both is the underdispersed
Skellam whose correction is INDETERMINATE. The headline slot still selects on model
probability, and an underdispersed model is systematically over-confident near the middle,
so a runline or total can win that comparison on confidence it has not earned. The row
says so; the selection rule does not yet know it.

WHAT WOULD RESOLVE IT, and this is the plan's actual recommendation rather than a reversal:
ship B-SELECT (the reliability-adjusted selection rule) so the rule discounts a market's
probability by that market's own measured calibration, at which point the eligible pool
stays wide and the ranking stops being naive. Until B-SELECT lands, the caveats on the row
are the whole mitigation. Reverting to `"dispersion_gated"` is one constant and is pinned
by tests in both directions, so the owner can take that back at any time without a code
change beyond the flag.

**6.7 PAL emphasis.** DEFAULT: the homepage teaser and the default tab follow the validated SP-to-RP direction after PAL-1 restamps the verdicts.

**6.8 PAL label.** DEFAULT: report eWAR `war_delta` as primary with a role-neutral RA9 arm as sensitivity, and let the sensitivity decide if the two disagree on sign.

**6.9 Role value delta into surplus.** DEFAULT: display-only. Surplus is an expected value under the v6 evframe and a role delta assembled from FA $/WAR constants is not an EV.

**6.10 Feed backfill.** Umpire, weather, posted lineups and catcher identity for 2018-2025 need roughly 12,000-17,000 StatsAPI feed fetches. DEFAULT: run it in the background on the local machine after B-VERIFY-FEEDS says what is actually missing, respecting `feed_cache` throttling, and treat every column it produces as dark.

**6.11 Awards.** DEFAULT: defer behind F-A, F-B and F-C, then ship the unfitted monotone rule with the evidence gap stated.

**6.12 Catcher framing.** No source exists (`framing_2024.csv` is 0 bytes, OAA pos=2 returns zero rows). DEFAULT: the defense board ships without catchers and says so.

**6.13 HEM+ vs wRC+.** DEFAULT: measure it before the accuracy page or the glossary makes any claim about HEM+ improving on the public index, and publish whichever way it lands.

---

### 7. Do-not-reopen appendix

Killed this cycle, with the reason, so they are not re-proposed in another costume.

- **pal-03, SP-to-RP FIT v2 (outcome-fitted).** The direction already PASSES its gate; the proposal re-fits the one thing that works. The feature claim is false locally: tjStuff+ scores from MLB live feeds and the cached feed range does not cover the 2018-2021 pre-years, and TTO leakage has no implementation anywhere. Events with both a closed post-season label and a pre-year inside the feed cache number about 18, not 61 or 100. A ~7-feature ridge on 18 events cannot be scored honestly, and the need gate already dominates the rank.
- **fa-P16, agent and agency effects.** The data does not exist (0 of 1,615 rows carry an agent field; no `agent_name` or `agency` anywhere in `fa_*.py`), it is an L-effort manual curation feeding the ge50 slice that already failed its 5-fold sufficiency bar (`PTIER_LEVEL_GATE.md:160-182`, NO SHIP, loss-record), and agency effect is confounded with the talent the anchors already carry, on a signed-deals-only corpus. If wanted, it is a hand-curated display chip on the served class, with no lab arm, no gate and no registry row.
- **projections-P7, graduate bridge.** The translation module's own artifact states production-level rates do not survive the MiLB to MLB jump (r2 ~0.02) because of selection, and the stat-line challenger already lost on rank (0.1539 vs 0.1931). The map would be fitted on >= 40 G / >= 40 IP survivors and applied to < 100 PA / < 30 IP non-survivors. `_depth_pool` already serves those rows.
- **trade_surplus_P02, market-implied values.** The veteran leg is 2.8% priced (26 of 939), no as-of veteran vintage exists (`trade_value_history` starts 2026-06-25 and is board rows only), only 54 two-sided events postdate the epoch, and the objective (minimize |log sum_A - log sum_B|) is degenerate: a global shrink clears the 10% bar with zero economic content, and there is no permuted-partner placebo.
- **trade_surplus_P11, package non-linearity.** Two-sided trades are 1,214 all-time and 107 in 2026, of which about 18 sides are multi-piece on both sides; `n_side` counts TRACKED players only and 81.8% of rows are snapshot-inferred with a NULL description, so the regressor is "how much of this package we happen to track" and a null coefficient is indistinguishable from a truncation artifact.
- **trade_surplus_P12, deadline vs offseason regimes.** `proj_export.py:625-633` carries a written pre-registration BLOCKING this premium constant below 40 usable deadline trades; the proposal self-selects a floor of 20. `trade_value_history` covers one deadline and zero offseasons; deadline urgency is already a shipped priced term (`bayes_trade_value.py:2665-2705`); and the buyer/seller flag from a current or final-standings outlook is outcome knowledge injected into the trade date.

Standing closed lanes, unchanged and not re-opened by anything above: Platt calibration for the moneyline; market blend before 150 distinct games (the calibration ledger holds 143 distinct game_pk, so the bake-off's R3 arm is dropped); git vintage backfill of leaderboard columns; the symmetric NB2 margin correction (INDETERMINATE, and the runline successor here is the one-run-atom kernel the doc names, not the symmetric arm); the 600-game vintage gate opening by pooling 2026 with 2027; the close cron as anything but an owner action; dynasty weight re-derivation and the closer save-share model; the REM+ K-prior family (X-R1, X-R1b) permanently, including any CSW or whiff proxy as a season skill-core prior (descriptive peripherals and betting sub-model components are different estimands and are allowed); park as a skill-core shrink target; GB-adjusted SEM+; xwOBA-allowed as the REM+/SEM+ core; the HEM+ age hinge and the pWOBA EV/barrel arm; the RP-to-SP re-gate by event-set expansion; PAL stamina features; the FA recal `fit` and `fit_group` modes, `POS_GROUP_MODE` v2, ridge, TJ flags in the market stage, `BAND_SCALE_GUAR`, per-decile band widths, the LightGBM market challenger, and ML WAR paths as market-model inputs; summing ML quantile heads anywhere; star-blend h2; Statcast into projections (re-gate 2026-11-15 only); and the eFV feature frontier, which is out of scope for this document entirely.

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

## Part 4. Sequencing, owner decision queue, do-not-reopen

### 4.1 Binding rules for the executor

1. **One served-number change per rebuild epoch** until the per-row basis ledger
   (A-SERVE-7) ships. Without it the blast radius of a change cannot be attributed and
   clause (f) of every gate is void. The queue holds at least nine served-number changes,
   so this is the binding constraint on the whole eFV follow-through and A-SERVE-7 is
   worth doing early for that reason alone.
2. **Measurement before model, on the same object.** A-CLAIM-1 through A-CLAIM-14 before
   any eFV driver or class arm; A-CLAIM-5 (the served-leg block) is the only legitimate
   trigger for A-SERVE-2; the betting selection bake-off before any staking change; the
   futures backtest before any futures value flag; the In-Game Management placebo before
   any management plus metric is served.
3. **Shared plumbing first.** The play and pitch corpus (M-CORPUS-1) is consumed by the
   betting props and totals models, the new MLB Stats metrics, the Alchemy Lab pitch-type
   work and both new modules. The historical game-context sidecar, the close job, the
   per-market sub-ledgers and the Lahman drop are the same shape: they unlock several
   lanes each and block nothing.
4. **Every lane carries**: a gate doc with clauses and floors fixed before measurement, a
   permanent-close pre-commitment, a registry row plus a committed eval artifact, the test
   that pins the ship, and copy derived from the artifact rather than hand written.
   Losses are committed with the same care as wins.
5. **Never run pytest while an edit is in flight.** `conftest.py` git-checkouts anything
   the suite dirtied at session end, so a concurrent edit is silently reverted. The runner
   is `tools/run_suite.py` (8 files per subprocess; the chunk size is not negotiable). The
   baseline is two documented reds plus `test_betting_dispersion` pending owner decision 10.
6. **Credits.** The odds tier is 500 a month. Close (about 93), props (120) and futures
   (about 20) go through one credit ledger with a pre-request guard before any of them is
   armed, or the tier is exhausted mid-month by whichever job runs first.
7. **Do not fetch what is already on disk.** 20.02 GB of full play data is cached in
   `.cache/win_prob` and is prunable by the current nightly. Protect it (M-CORPUS-3)
   before building anything on it.

### 4.2 Waves

**Wave 0, hygiene and instruments (no served number moves).** eFV: A-CLAIM-1, A-CLAIM-11,
A-CLAIM-12, A-CLAIM-14, plus the floor-first regen tests. Betting: the objective frame,
per-market sub-ledger tags, the close-job install, the capture-cadence repair and the
credit ledger. Corpus: M-CORPUS-1 (offline, no network), M-CORPUS-3 (protect it before it
is deleted), M-CORPUS-7. Hall of Fame: H-DATA-1 contract and fixture so the Lahman drop
can be parsed the day it arrives. Also the eFV program arm ledger and the reserved 2025
confirmation fold (A-CLAIM-15), which changes what a future survivor is worth.

**Wave 1, measurement.** eFV: A-CLAIM-2 through A-CLAIM-10, A-SERVE-5, A-DRIVER-8.
Betting: the selection-rule bake-off on the settled ledger, the props backtest harness,
the futures fixed-date backtest on 2018-2025. Modules: M-CORPUS-2 (the context backfill,
one season at a time), M-CORPUS-5, M-ENG-1 and M-ENG-2 with their pins. Hall of Fame:
H-DATA-2 through H-DATA-4 and the benchmark bake-off (H-PRED-11), which sets the bar
every later model is judged against. Other modules: the PAL epoch re-stamp, the FA
baselines on the eWAR basis, the trade-events corpus.

**Wave 2, model arms, each in its own epoch.** eFV in order: A-LABEL-1 (A2 arm first),
A-LABEL-2, A-DRIVER-7, then E1 and E3 if A2 passes; A-SERVE-1 then A-SERVE-2 if it
resolves; A-SERVE-3, A-SERVE-4; A-SEAM-1, A-SEAM-2, then A-SEAM-3 and A-SEAM-4;
A-DRIVER-1 through A-DRIVER-6 inside the label epoch's frame, one family per Holm.
Betting: the moneyline coefficient repair, the runline and totals sub-models, the HR and
strikeout prop models graded dark, schema-4 capture. Other modules: the hierarchical FA
market model, the playing-time model, the shared team-season simulator, market-implied
trade values.

**Wave 3, the new modules.** In-Game Management: M-MWAR-2 (the manager entity, which
everything attributes through), then the lineup, pitching and running-game families in
that order, then M-MWAR-1 and the M-MWAR-4 battery. Hall of Fame: H-DATA-5 and H-DATA-6,
H-PRED-1 through H-PRED-4, H-LEAD-1 through H-LEAD-6, then the rest. Ship each module's
page only when its first family has passed its own gate, so neither launches with a
number nothing has scored.

**Wave 4, the epoch reads.** The 2027 `RESOLVED_THROUGH` unlock with the reserved-fold
confirmation, the first pitcher-stuff fold, and the V6 claim family read under the
alpha-spending clause.

### 4.3 Owner decision queue (defaults in parentheses)

1. **Claim family V6**: define "every public source" as externally published raters scored
   pairwise on each rater's own rows, register the block-normalized and bust-inclusive
   frames as the successor family, retire C4 and record C2 as undecidable at its negative
   point (default: yes, registered before the 2027 read, never as a post-hoc replacement).
2. **Serve the evaluated object for pitchers** if A-SERVE-1 resolves (default: yes, in its
   own grade-basis epoch, with the honest note that the blend-graded pitcher board still
   trails plain consensus by 0.0129).
3. **Age ramp** after its serve-rule gate (default: follow the gate; a labelled age-risk
   indicator on a null, which removes a 10 percent per year haircut from 1,937 rows).
4. **Fabricated FV 35 to an explicit UNGRADED state** (default: yes, own two-pass
   rebuild, after the anchor fix).
5. **Valuation unification epoch** (default: yes, sequenced behind the anchor fix; the
   elite table goes to the owner before it ships).
6. **Betting objective**: accuracy and ROI measured separately and gated
   lexicographically per market, accuracy floor first then an ROI lower bound (default:
   yes).
7. **Selection rule**: replace the in-band probability rule with the bake-off winner
   (default: yes, but only after the bake-off clears on the settled ledger; until then the
   current rule stands with the per-market caveats now on the row).
8. **Prop market set**: extend to outs, earned runs, hitter strikeouts and walks at the
   cost of fewer pulled games per month (default: extend after the HR and strikeout models
   have graded dark).
9. **Futures**: ship the section with model win totals and division odds now, value flags
   only after the backtest and a futures snapshot line exist (default: yes).
10. **`test_betting_dispersion`**: the total-over-9.0 criterion no longer passes on
    refreshed data (t 1.378 against a 1.645 bar). Retire the hard assertion to a dated
    reading (default: retire; the gate verdict is unchanged and the artifact still carries
    the grid).
11. **In-Game Management**: MWAR's headline baseline (default: the written-down heuristic
    manager, with league-average and replacement served beside it, because a heuristic is
    the only baseline a reader can argue with).
12. **Hall of Fame**: primary label BBWAA induction with any-route secondary; the
    character-clause and performance-enhancing-drug flags stay out of the merit model and
    appear only in the voter model (default: yes to both). Negro Leagues and pre-1901
    seasons are IN the frame with an era factor and a disclosure (default: in).
13. **The push**: the branch is far ahead of origin and every session has ended unpushed
    (default: push once this session's suite state is accepted).

### 4.4 Do-not-reopen additions from this session

In addition to the standing ledger (the 39 eFV feature arms, model class on squared loss,
lambda, the hitter serve basis, AUC floors, correction families, consensus weighting, BA
into SCORED_SOURCES, pre-Statcast stuff proxies, Statcast into eFV, volume, level weights,
age interactions, health as a driver, scout-report text traits, Platt for the moneyline,
the market blend below 150 games, the git vintage backfill, the closer share model, the
RP-to-SP expansion):

- The homepage re-sort on (primary FV, '+') as a rank source. Replaced by the baked rank;
  no surface may add a second ordering.
- Any slot-market lock by market type. `SLOT_MARKET_POLICY` is the only switch.
- The hit-and-run proxy as a management metric (it cannot separate a called hit-and-run
  from a straight steal with a swinging batter).
- The two-way simultaneous league-strength fit for era-neutral WAR (unidentified).
- Savant catcher framing as a fetched leaderboard (the endpoint ignores every year
  parameter and returns the current season only; framing must be modelled from pitches).
- The 60 eFV proposals the verifier killed, each with its citation in the Part 1 appendix.
