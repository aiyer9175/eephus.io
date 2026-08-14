# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Methodology freshness - the documentation companion to the registry
standing rule. Every model in data/model_registry.json must map to the
glossary entry (data/glossary.json) that explains it to users, or be
explicitly marked internal-only here. Adding a registry row without
touching this map fails the suite - the same forcing function the
eval-artifact rule uses, applied to user-facing documentation."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent

# model_id -> glossary entry id(s) that document it (or "internal" for
# models with no user-facing methodology surface). EVERY registry row
# must appear; a new model ships with its documentation decision.
MODEL_GLOSSARY = {
    "arb_award": ["arb_award_model", "arb_market_residual"],
    "arb_label_set": "internal",
    "arb_fa_link": "internal",
    "arb_ladder": "internal",
    "xfv_label_replacement": "internal",
    "xfv_rank_objective": "internal",
    "surplus_decomposition_v6": "internal",
    "xfv_dist_recalibration": "internal",
    # C-1b, the tail-preserving refit (2026-08-14). INTERNAL on the same reasoning
    # as the B-L3 lane below: all five declared families returned NO_SHIP, nothing
    # was promoted, and no served number and no page copy moved because of it.
    #
    # Worth being precise about WHY this is internal rather than reader-facing,
    # because it is a close call. The lane's finding IS reader-relevant in the
    # abstract (eFV runs below consensus at the top of the board, and no monotone
    # correction fixes that without breaking the level calibration). But the thing
    # a reader would actually be told is a property of the SHIPPED affine
    # correction, and that is already disclosed on the xfv entry, which carries the
    # tail cost in WAR terms. This row documents the failed search for an
    # alternative, which is model-dev history. If the elite question is ever
    # reopened with real power, the finding graduates to the xfv entry and this
    # mapping changes with it.
    "xfv_tail_preserving_refit": "internal",
    # C-1d, the fitting-frame lane (2026-08-14). INTERNAL: both frames returned
    # NO_SHIP and C-7 reverted the correction to identity the same night, so
    # nothing it measured reaches a reader and there is no claim to document.
    "xfv_served_frame": "internal",
    # C-1c, the powered elite lane (2026-08-14). INTERNAL for the same reason as
    # C-1b above: it adjudicates a shipped correction and promotes nothing. Its
    # reader-facing half (that the top of the board is the least resolved part of
    # the model) belongs on the xfv entry if it is ever stated, not here.
    "xfv_elite_band_accuracy": "internal",
    # Opportunity/quality decomposition of eFV (lane B-L3). Model-dev only:
    # 0 of 7 arms promoted, no feature and no constant moved, and nothing on
    # any page changed, so it takes the same "internal" decision the rest of
    # the eFV loss ledger does. The reader-facing consequence of the finding
    # (that eFV orders opportunity better than it orders rate) would need a
    # glossary entry of its own before it could be stated on a surface.
    "xfv_opportunity": "internal",

    # WAVE-Z 2026-08-10. Both of these RENDER at /glossary/#view=source-accuracy
    # and the verdict column of the source-comparison view, so neither may take
    # the "internal" decision. They point at the two entries that carry the
    # reader-facing method: consensus_fv states that the consensus is an
    # equal-weight mean and that accuracy weights were reverted as unearned,
    # which is exactly the claim these two measurements adjudicate, and
    # normalized_source_grade carries the cross-source scale step the label-free
    # precision route would reweight if it ever identified.
    "source_cohort_accuracy": ["consensus_fv"],
    "source_precision_label_free": ["consensus_fv", "normalized_source_grade"],

    # B-L6 2026-08-10. This one CANNOT take the "internal" decision either, and
    # for a stronger reason than the two above: it does not merely render, it is
    # the measurement the head-to-head conviction copy is now written to. The
    # hero headline on the source-comparison view was rewritten because of this
    # row's result, and its panel prints the gap-closure share. It points at
    # consensus_fv (what the rebuilt baseline is a rebuild OF) and at xfv (the
    # grade whose lead over that baseline is the thing being adjudicated).
    "efv_denoised_baseline_control": ["consensus_fv", "xfv"],

    # M-1. Not "internal": this row SELECTS the frame the published head-to-head
    # verdict is computed on, so the number a reader sees on the source-comparison
    # view is written to it. Same two entries as the row above and for the same
    # reason - it adjudicates eFV's grade against the consensus baseline.
    "xfv_headtohead_frame": ["consensus_fv", "xfv"],

    # C-1. Measurement plus an unshipped candidate correction to the published
    # WAR number; nothing serves it, and the ship decision is referred. Marked
    # internal rather than mapped to a glossary term because no reader-facing
    # definition changes while it stays unshipped.
    "xfv_dispersion_repair": "internal",

    "consensus_recency_decay": "internal",
    # measurement of the single-source shrinkage; nothing shipped, the incumbent
    # constant was tested against the mechanism it approximates and survived
    "consensus_coverage_shrinkage": "internal",
    "xfv_serve_path": "internal",

    # Audit 2026-08-07b measurement artifacts. All are model-dev only, rendered
    # on no surface, so they take the "internal" documentation decision the same
    # way war_cohort_diagnostic and surplus_sensitivity_diagnostic do. Each row's
    # own notes field carries what survived adversarial verification.
    "xfv_label_censoring": "internal",
    "consensus_contamination": "internal",
    "consensus_rank": "internal",
    "xfv_cohort_floors": "internal",
    "efv_conditional_floor": "internal",
    "xfv_dist_calibration": "internal",
    "xfv_feature_leak": "internal",
    "ba_consensus_integration": "internal",
    "ba_tool_grade_weight": "internal",
    # BA3 changes the /sources/ classification copy, and C-1 changes the served
    # avg_rank and the spotlight driver text, so both reach a reader.
    "ba_source_classification": ["consensus_fv"],
    "consensus_org_rank_split": ["consensus_fv"],

    # 2026-07-04 research-sweep Tier-1 features (each has its own glossary entry).
    "draft_war_room": ["draft_war_room"],
    "farm_window_alignment": ["window_alignment"],
    "fv_tape": ["fv_tape"],
    "surplus_downside_risk": ["risk_adjusted_surplus"],
    "prospect_greeks": ["prospect_greeks"],
    "star_odds": ["star_odds"],
    "upgrade_option": ["opt_pct"],   # Tier 2 grade-option layer; surfaced as the PROSPX OPT% column
    # Tier 2 cross-source scale map; shapes the live consensus_fv scale. The
    # normalized_source_grade entry (2026-07-29) is the reader-facing version:
    # why a consensus can land outside the range of the grades on the card.
    "grade_normalization": ["consensus_fv", "normalized_source_grade"],
    "fa_projection_marcel": ["fa_projection_engine"],
    "fa_war_paths_decay": ["fa_projection_engine"],
    "proj_def_prior": "internal",   # a hit feature of fa_war_paths_decay; gate-artifact row
    "prospect_def_value": "internal",  # Will Cahoon def model (local reconstruction); eFV-swap loss ledger
    "ewar": "internal",   # eephus WAR: measured, consumed by nothing, not a served metric
    # 2026-08-04 gated experiments, all three measured NO-SHIP (loss ledgers).
    "xfv_pace_from_entry": "internal",   # pre-registered kill criterion fired on the hitter weight sign
    "xfv_level_blend_arms": "internal",  # 17 of 18 cells negative; the anchor arm is a measured loss
    "eta_age_continuous": "internal",    # loses both legs of the criterion v39 was shipped on
    "fa_market": ["fa_projection_engine", "deal_plus"],
    "fa_rational_value": ["rational_value", "contract_surplus"],
    "fa_dpw_series": ["winter_dpw", "dpw_tier"],
    "fa_team_fit": ["fit_components"],
    "fa_penter": ["enter_prob"],
    "fa_qo_pick_tax": ["qo_tax"],
    "mlb_projections_vets": ["mlb_projections"],
    "mlb_projections_prospects": ["mlb_projections", "proj_buckets"],
    "prospect_surplus": ["surplus_value"],
    "fv_to_war_anchors": ["fv_to_war_table"],
    "wag": ["wag", "warwag"],
    "consensus_fv": ["consensus_fv", "normalized_source_grade"],
    "draft_consensus_weight": "internal",
    "source_track_record": ["single_source_mark"],
    "eta": ["eta"],
    "farm_grades": ["farm_report_card", "farm_rank"],
    "draft_slot_curve": ["slot_value"],
    "overseas_translation": ["overseas_posting_class"],
    "college_translation": ["single_a_equivalent"],
    "statcast_plus": ["statcast_plus"],
    "stuff_plus_external": ["stuff_grade_plus"],
    "stuff_plus_aaa": ["stuff_plus_aaa"],
    "swing_plus_external": ["swing_plus"],
    # Will's-metrics program 2026-07-23 (docs/wills-2026-07-23/GATES.md): loss ledgers
    # are internal; shipped display surfaces map to their glossary entries.
    "fa_pt_risk": "internal",              # W1/W1-B loss ledger (IL-history PT risk, era-transfer FAIL)
    # W2 loss ledger (park-neutralized eFV rates, clause M FAIL). No longer
    # internal: the park-factor entry it now maps to is where a reader is told
    # the table exists AND that the correction built on it did not earn a ship.
    "xfv_park_line": ["milb_park_factor"],
    "pal_stuff_xrv": ["stuff_plus_aaa"],   # W3: per-type aStuff+ sidecar + PAL pitch-add ranking (display)
    "college_stuff_translation": "internal",  # W4 loss ledger (college stuff+ K% covariate FAIL)
    "collegesavant_stuff": ["collegesavant_stuff_plus"],  # W4 governance of the shipped display lineage
    "advancement_pace": ["advancement_pace_plus"],        # W5 descriptive display (contract: never a model input)
    # eFV holistic program 2026-07-24 (docs/efv-2026-07-24/GATES.md):
    "efv_scoreboard": ["xfv"],             # eFV accountability scoreboard (source-comparison panel)
    "xfv_platoon": "internal",             # W-PLATOON loss ledger (platoon splits FAIL both sides)
    "xfv_wrc": "internal",                 # W-WRC/W-SB loss ledger (in-house wRC+ no ship)
    # consensus-basis counterfactual; normalization STAYS ON (turning it off is worse,
    # and no additive re-basing can change a gap between two players graded by the
    # same source set). Loss ledger, nothing user-facing to document.
    "xfv_gradenorm_basis": "internal",
    # 2026-07-30 coherence lane, both NO-SHIP measurement ledgers, nothing rendered.
    # xfv_provisional_grade_map: re-pointing the provisional engine onto the outcome
    # curve fires 3 of 6 stop conditions (the soft cap's FV constants stop being WAR
    # constants; 48.5% of the pool has non-positive predicted WAR and all of it collapses
    # to exactly FV20, deleting the org-filler ladder).
    # xfv_odds_index_basis: the consensus-vs-model index mismatch is REAL (2.7x dispersion)
    # but re-indexing is a null, because the binding defect is a 35-point base-rate gap
    # between a published-list table and the eFV matrix, not the units.
    "xfv_provisional_grade_map": "internal",
    "xfv_odds_index_basis": "internal",
    # LANE-CURVES Phase 1 measurement artifact: per-side FV -> outcome curves + the
    # industry bake-off. Not shipped, rendered nowhere, changes no served number; the
    # reader-facing glossary entry belongs to the Phase-2 grade re-scale, not here.
    "fv_outcome_curves": "internal",
    # LANE-P2 Phase 2: the SHIPPED grade map. xfv_grade is now the inverse of the pooled
    # empirical outcome curve, so grade G means "the industry FV whose realized outcome
    # distribution matches our prediction" rather than "the FV our valuation core expects
    # this WAR from". That is live eFV scoring behaviour a reader sees on every card, so
    # it documents to the xfv entry - and that entry's wording is OWED an update to match
    # (see docs/efv-2026-07-30/POOLED_OUTCOME_REFIT.md; data/glossary.json is another
    # lane's file this cycle).
    "fv_outcome_pooled_grade": ["xfv"],
    "xfv_tbs2": "internal",                # W-TBS2 loss ledger (tiebreaker stack FAIL)
    "xfv_ungraded_disc": "internal",       # W-DISC loss ledger (coverage-starved)
    "xfv_role_arg": "internal",            # W-SURPLUS S3 audit-only
    "eta_hazard_lite": ["eta"],            # W-SURPLUS S2 (PASS, gated OFF this cycle)
    "aaa_physics_screen": ["stuff_plus_aaa"],  # W-SCREEN physics forward screen + sidecar
    # eFV accuracy / true-to-model program 2026-07-24b (docs/efv-2026-07-24/GATES-ACCURACY.md):
    "xfv_lambda_reselect": ["xfv"],        # blend-weight re-select SHIP (hit 0.85, +Spearman/AUC)
    "xfv_weight_recal": "internal",        # attribute-weight/alpha re-open (no ship)
    "xfv_cap_sweep": "internal",           # input-cap sweep (caps are safety, not compression)
    # uncapped live overlay SHIP default-ON; the eFV entry covers the grade
    # effect, the A-ball signal entry covers the input the reader can see.
    "xfv_statcast_overlay_uncapped": ["xfv", "statcast_alevel_signal"],
    "xfv_ungraded_recal": ["xfv_ungraded"],    # provisional de-cap SHIP true-to-model
    # Wave G site-wide true-to-model sweep 2026-07-24b (GATES-ACCURACY C2/C3):
    "plus_metric_recal": ["krp_plus"],     # KRP+ de-clamp SHIP; family already true-to-model
    "c3_pal_fa_recal": "internal",         # PAL/FA audit, zero ships (measured on real gates)
    # Lane E4: a pre-registered TEST of three owner claims about body type and
    # infield position. Nothing is fitted and nothing is served, so there is no
    # glossary term to document; the deliverable is
    # docs/prereg-e4-anthro-position.md.
    "anthro_position_claims": "internal",
    "c3_proj_trans_recal": ["single_a_equivalent"],  # translation band de-cap SHIP
    # Round 2 2026-07-24e:
    "xfv_injury_history": "internal",   # injury-history overlay ledger (coverage-starved)
    # 2026-07-30 age-pipeline and IL-severity work. Both are live scoring behaviour of
    # the eFV model rather than surfaces of their own, so they document through the eFV
    # entry exactly as xfv_role_ceiling does.
    "efv_age_pipeline": ["xfv"],
    "efv_il_severity": ["xfv"],
    "xfv_peak_war": "internal",         # peak-WAR target measurement ledger (keep cumulative)
    "xfv_bughunt2": "internal",         # bug hunt r2 + scoreboard intl_bat dedup fix
    # 2026-07-25 calibration/diagnostic lanes, registered 2026-07-29. All are
    # measurement ledgers rather than user-facing models: they grade the eFV
    # model against its own declared meaning. The findings they carry are
    # written up in docs/efv-2026-07-29/CALIBRATION_FINDINGS.md, and the two
    # that drive a repair land their user-visible effect through the eFV grade
    # and surplus entries that already exist.
    "xfv_pred_dispersion": "internal",    # Defect A ledger: OOS WAR over-dispersion
    "xfv_level_calibration": "internal",  # Defect B ledger: grade-to-WAR anchor bias
    "xfv_odds_dispersion": "internal",    # p_bust dispersion candidate, patch INERT
    # 2026-07-30 LANE-ODDS: which grade map p_bust should be keyed to after the
    # board moved to outcome_implied_fv. A measurement lane that adjudicated the
    # _odds_grade pin and shipped NOTHING; keeping the pin means no reader-facing
    # number moved, so it has no glossary surface of its own.
    "xfv_odds_grade_basis": "internal",   # re-key vs the pin: measured NULL, pin kept
    "xfv_odds_recalibration_ship": "internal",  # re-link re-fit: NULL vs a flat base rate, not wired
    # Cohort conditioning of the odds: NO-SHIP, killed by its own zero-information
    # control (shuffled cohort labels reproduce the whole gain). Nothing wired, no
    # served p_bust moved, so no glossary surface of its own.
    "xfv_odds_cohort": "internal",
    # Slope recalibration: PRE-REGISTERED ONLY, never fitted. It gets a glossary
    # entry if and when it ships, not before.
    "xfv_odds_calibration_slope": "internal",
    "xfv_generality": "internal",         # stratum-generality audit, shipped nothing
    "am_crossmodel_agelevel": "internal", # cross-model age-for-level null
    # thin-sample p_bust DID ship and moves a number readers see on provisional
    # cards, so it points at the provisional entry rather than being internal.
    "xfv_thin_pbust": ["xfv_ungraded"],
    "spotlights_movement": ["spotlights", "spotlight_age_cap"],
    "org_tendencies": ["org_tendencies"],
    "team_win_projections": ["mlb_projections"],
    "xfv_hitter": ["xfv"],
    "xfv_pitcher": ["xfv"],
    "xfv_tools": ["xfv_tools"],
    # eFV proxy = the leading-indicator companion to the eFV family (predicts first-MLB
    # Statcast quality); documented under the eFV entry + self-documented on the detail tile.
    "xfv_proxy": ["xfv"],
    # eFV ungraded = the provisional production-only leading indicator for source-ungraded
    # roster players (DSL/CPX sleepers); its own glossary entry documents the methodology.
    "xfv_ungraded": ["xfv_ungraded"],
    # eFV backgrade = the eFV family applied retroactively so DEBUTED players keep a locked
    # eFV grade (frozen at their final pre-debut snapshot); user-facing on graduate cards +
    # the trade-machine backgrade surplus source, documented under the eFV glossary entry.
    "xfv_backgrade": ["xfv"],
    # Trade Machine surplus = the board/evaluator surplus ordering (= the platform surplus_value
    # the Trade Machine shows); first outcome-validated 2026-06-25. Documented under the trade
    # machine + surplus-value glossary entries.
    "trade_machine_surplus": ["trade_machine", "surplus_value"],
    # WAR cohort diagnostic = model-dev artifact rendered nowhere (audits the WAR engine's
    # per-cohort residuals); no user-facing methodology surface.
    "war_cohort_diagnostic": "internal",
    # REM+ = the /mlbstats/ Bullpen Leaderboards reliever metric; its glossary entry
    # (and the Bullpen+ / gmLI / WPA companions) documents the methodology.
    "rem_plus": ["rem_plus", "bullpen_plus"],
    # PAL = the /pal/ Alchemy Lab role-conversion screen; documented by its
    # FIT-score + conversion-model glossary entries.
    "pal_conversion": ["pal_conversion", "rp_sp_fit", "sp_rp_fit"],
    # Holistic pass 3 (2026-07-01) model-dev artifacts, rendered nowhere:
    # the rejected eFV isotonic candidate (loss ledger), the SC+ per-component
    # signal isolation, and the surplus $/WAR-level stress test.
    "xfv_isotonic_calibration": "internal",
    "sc_plus_component_diagnostic": "internal",
    "surplus_sensitivity_diagnostic": "internal",
    # --- 2026-07-25 ---
    # Positional ladder = the empirically recovered positional-adjustment table
    # (n=9,101 player-seasons, R2 0.982) that replaced the unsourced folklore one.
    # It is a CONSTANTS table consumed by prospect_def_value, the projection
    # pos_adj_prior and the eFV defensive prior rather than a surface of its own,
    # and it is rendered for the reader in the /pal/ Position Fit ladder view,
    # which is documented by the PAL conversion entry.
    # E2a is an audit with no served surface: nothing on the site reads it,
    # its output is a decision pack in its own gate doc.
    "xfv_side_calibration": "internal",
    # A loss ledger with no surface; the finding it tested lives on
    # xfv_side_calibration, which is where the reader is sent.
    "xfv_side_correction": "internal",
    # Measurement only, no served surface; the betting client reads none of it.
    "betting_market_blend": "internal",
    "positional_ladder": ["pal_conversion", "def_home_chip"],
    # eFV board side scale (W-SIDESCALE) = the per-side affine that puts a hitter
    # grade and a pitcher grade of the same number on the same realized-outcome
    # scale. It changes the DISPLAYED eFV, so the eFV entry documents it.
    "efv_board_side_scale": ["xfv"],
    # Projection calibration map = the internal recalibration seam of the MLB
    # projection engine; the projections entry documents the engine it calibrates.
    "proj_calibration_map": ["mlb_projections"],
    # eFV surrogate label = research lane, NO-SHIP on both sides (deprecated row,
    # loss ledger). Wired into no surface, so there is nothing to document.
    "xfv_surrogate_label": "internal",
    # 2026-08-05 pre-registered driver experiments, both NO-SHIP loss ledgers
    # (docs/efv-sb-athleticism-2026-08-05/): SB rate 0.45x its MDE floor on
    # 2/4 folds; every field-bearing composite regresses. The sb_rate_rel
    # plumbing exists but is inert (not in _FEATURES_HIT), so no surface
    # documents it.
    "xfv_sb_driver": "internal",
    "xfv_athleticism_blend": "internal",
    # 2026-08-07 driver program (docs/efv-drivers-2026-08-07/GATE_RECORD.md):
    # six arms re-gated on the 11-fold pair-weighted basis, six nulls. These four
    # had no prior registry home; the sb-rate and wRC+ re-gates and the lambda
    # re-sweep ride the existing xfv_sb_driver / xfv_wrc / xfv_lambda_reselect
    # rows instead of taking near-duplicate ids. Nothing shipped and no served
    # grade, rank or dollar moved, so none of the four names a number a reader
    # could look up. xfv_pos_census is the odd one and is internal for a
    # different reason: it measures a COVERAGE blocker rather than fitting
    # anything, and what it found is a wiring defect (efv_model._observed_pos_map
    # reads the pre-debut census, not the as-of rebuild). If that repoint is ever
    # taken and POS_PREMIUM_USES_OBSERVED flips, the premium becomes a live
    # scoring behaviour and this line changes with it.
    "xfv_handedness": "internal",
    "xfv_gated_pairs": "internal",
    "xfv_elite_band": "internal",
    "xfv_pos_census": "internal",
    # 2026-08-07 FA guarantee/AAV band gate (docs/gate-2026-08-07-fa-guarantee-band.md):
    # a measured no-ship, and the SECOND independent null on the same arm after
    # T1.2 (2026-07-25) on a pinball criterion. BAND_SCALE_GUAR stays False, so
    # the served band is still the flat one the fa_projection_engine entry
    # already describes and the >2.5x disclosure still fires; nothing new became
    # user-facing, which is what makes this internal rather than a doc owed.
    "fa_guar_band": "internal",
    # 2026-08-05 Diamond section. All three ship on their own pages, which
    # carry their method and their limits in user-facing copy, so the page IS
    # the documentation. None of them is a glossary term: the site glossary
    # documents baseball metrics, and a betting win probability, a DFS slate
    # price and a card index are products rather than Arkmetrics. Two of the
    # three ship deliberately unvalidated and say so on the page.
    "betting_game_prob": "internal",
    "dfs_slate_pricing": "internal",
    "card_market_index": "internal",
    # X-D1 gmLI deployment-context metric: gate passed and wired 2026-07-02
    # (bullpen_export join + /mlbstats/ column); documented by its glossary
    # entry.
    "leverage_consistency": ["gmli_3yr"],
    # X-D2 AgeRel+ candidate: numeric bar met but not a clear pass; NOT
    # wired, owner decision queued in REVIEW_QUEUE.md.
    "age_rel_outperformance": "internal",
    # eFV round (2026-07-02): three gated experiments, all rejected or
    # inconclusive at their pre-registered gates; loss ledgers, rendered
    # nowhere.
    "xfv_grade_recal": "internal",
    "xfv_cohort_lambda": "internal",
    "xfv_pitcher_stuff": "internal",
    # Pre-launch eFV round (2026-07-07, docs/prelaunch-2026-07/GATES.md):
    # four gated experiments. Three no-ships (lambda confirm hit boundary
    # censored, hierarchical cohort lambda blocked on 3 clauses, alpha
    # criterion hurts hitters) and one ship (ops_rel into the hitter lean
    # set, fringe-tier gate). All model-dev artifacts, rendered nowhere;
    # the shipped feature's user-facing methodology lives under the xfv
    # glossary entry.
    "xfv_lambda_confirm": "internal",
    "xfv_cohort_lambda_hier": "internal",
    "xfv_alpha_criterion": "internal",
    "xfv_ops_rel_fringe": "internal",
    # LR-FRINGE (2026-07-15, docs/efv-2026-07-15/GATES.md): level_rank shipped
    # into the hitter lean set via the pre-registered fringe re-gate at the
    # 2024-fold vintage; model-dev artifact, methodology under the xfv entry.
    "xfv_level_rank_fringe": "internal",
    # RELIEF-SHAPE (2026-07-15, docs/efv-2026-07-15/GATES.md): PAL prospect-
    # watch shape composite as pit features - all three arms failed the
    # pre-registered bar; loss ledger, rendered nowhere.
    "xfv_relief_shape": "internal",
    # eFV improvement sweep (2026-07-18, docs/audit-2026-07-18/): five gated
    # arms (fwd-cal, recency-decay, IPCW, OOF stacker, hurdle head) all
    # rejected on the forward-chained protocol; loss ledger, rendered nowhere.
    "xfv_improve_sweep": "internal",
    # eFV improvement pass (2026-07-14, docs/efv-2026-07-14/GATES.md): the
    # anchor-staleness decay + lambda band-raise + absolute-age feature
    # ledgers. Model-dev artifacts, rendered nowhere; the user-facing
    # methodology stays under the xfv glossary entry (the stale decay and
    # age penalty surface per-player as factor chips).
    "xfv_stale_anchor": "internal",
    "xfv_lambda_band": "internal",
    "xfv_age_feature": "internal",
    # Review-queue round (2026-07-02): the eFV bucket-calibration final
    # attempt under a production-relevant gate; rejected, loss ledger,
    # rendered nowhere.
    "xfv_grade_recal3": "internal",
    # Review-queue round loss ledgers, all rendered nowhere: the total-WAR
    # band replacement (rejected, bands dropped), MiLB park factors
    # (infeasible), ERA-shrink unification (keep two values).
    "war_total_band_calibration": "internal",
    # milb_park_factors stopped being internal on 2026-07-29: the 202-venue table
    # is now a reader-facing reference surface, so it documents through the park
    # factor entry (which also states that the eFV correction built on it failed).
    "milb_park_factors": ["milb_park_factor"],
    "era_shrink_unification": "internal",
    # E-ISO4: the final eFV bucket-calibration attempt (joint side-symmetric
    # map); rejected, closes the line, loss ledger, rendered nowhere.
    "xfv_grade_recal4": "internal",
    # E-LEAN1 (2026-07-05): lean+1 single-feature re-tests of every _vec
    # feature absent from the shipped lean sets, plus the A1 ops_rel swap; all
    # rejected at the pre-registered gate, loss ledger, rendered nowhere.
    "xfv_leanplus": "internal",
    # E-COLLEGE-BACKFILL (2026-07-05): eFV production-block imputation for
    # milb_missing college draftees; STOPPED at the trainability gate (college
    # TrackMan coverage post-dates the resolved cohort), loss ledger, nowhere.
    "xfv_college_backfill": "internal",
    # H-4 (2026-07-05): the shipped eFV distribution's reliability curves, split
    # out of the deprecated isotonic loss ledger into a live artifact that the
    # PROSPX eFV reliability diagram renders.
    "xfv_reliability": ["xfv"],
    # Follow-up Wave B1 reliever metrics (2026-07): RIV+ realized-impact index
    # and 3-year REM+ both surface on /mlbstats/ with their own glossary entries;
    # the SwStr xK skill-core candidate was rejected at its gate (loss ledger,
    # rendered nowhere).
    "riv_plus": ["riv_plus"],
    "rem_plus_3yr": ["rem_plus_3yr"],
    "rem_plus_swstr": "internal",
    # Follow-up Wave B2 starter metrics (2026-07): SEM+ (validated starter
    # run-prevention) + 3-year SEM+ on the /mlbstats/ Starter Leaderboards, each
    # with its own glossary entry.
    "sem_plus": ["sem_plus"],
    "sem_plus_3yr": ["sem_plus_3yr"],
    "hem_plus": ["hem_plus"],
    "hem_plus_3yr": ["hem_plus_3yr"],
    "xhem_plus": ["xhem_plus"],
    "xrem_plus": ["xrem_plus"],
    "xsem_plus": ["xsem_plus"],
    "leverage_board": ["wpa", "clutch", "pli"],
    # Improvement program 2026-07-15 (both workflow reports): wave-1 loss
    # ledgers (decayed multi-year xHEM+; decayed 3yr REM+/SEM+ blends), the
    # E-LAMBDA parity adjudication (restamp blocked, owner decision queued),
    # the per-side alpha-criterion close-out, and the two eFV measurement
    # instruments (F-SIDE standing side-fairness eval line; F-WATCH frozen
    # promoted-pitcher cohort with a kill rule). All model-dev artifacts,
    # rendered nowhere; user-facing methodology stays under the xfv /
    # xhem_plus / rem_plus_3yr / sem_plus_3yr glossary entries.
    "xhem_multiyear_decay": "internal",
    "rem_sem_3yr_decay": "internal",
    "xfv_lambda_parity": "internal",
    "xfv_alpha_criterion_perside": "internal",
    "xfv_side_fairness": "internal",
    "xfv_promo_watch": "internal",
    # Wave 3 (2026-07-15): fwdhem_plus SHIPS on the Hitter Leaderboards with
    # its own glossary entry; the K-strength sweep and pHEM+ Marcel-lite gate
    # (won by the existing FA engine; pWOBA display decision queued) and the
    # PAL game-log lanes are model-dev artifacts, rendered nowhere.
    "fwdhem_plus": ["fwdhem_plus"],
    "k_strength_sweep": "internal",
    # phem_marcel_lite SHIPPED 2026-07-15 as the pWOBA column (owner display
    # decision) - the FA-engine re-anchor; the pwoba glossary entry carries
    # the methodology.
    "phem_marcel_lite": ["pwoba"],
    "pal_gamelog_lanes": "internal",
    # Wave 3b loss ledgers (2026-07-15), all rendered nowhere: velo decline
    # adjustment, FB-HR + CSW shrink priors (K-prior lane closed permanently),
    # park-conditioned shrink targets, HEM+ age hinge (dominated by the FA
    # engine - aging lives in the projection layer).
    "velo_decline": "internal",
    "fbhr_csw_priors": "internal",
    "park_shrink_targets": "internal",
    "hem_age_layer": "internal",
    # Owner-directed reliever-ceiling overlay (2026-07-15, second Moore
    # directive): policy dial, not an accuracy claim; surfaces per-player as
    # the "Reliever ceiling" factor chip. Documented (2026-07-16) in the xfv
    # glossary methodology, so it maps there like the other live overlay chips
    # (injury / age / stale-anchor) rather than hiding behind "internal".
    "xfv_role_ceiling": ["xfv"],
    # Bucket-head calibration gate (2026-07-15): clean loss ledger (G4
    # monotone-sanity fail + ablation showed population-recal, not age);
    # rendered nowhere; mandatory re-run at 2024-fold trainability.
    "xfv_bucket_age_head": "internal",
    # TOP-QUANT (2026-07-15, owner-approved attempt): loss ledger - the top-25
    # cutoff sits below the 55 knee so pit-only remaps are structurally inert;
    # gated-inert hooks shipped; honest path = a JOINT cross-side display map
    # under a NEW owner registration. Rendered nowhere.
    "xfv_topquant": "internal",
    # Lambda adjudication tournament (2026-07-15): incumbent selector WON both
    # sides (parity protocol loses OOS; the C-vs-D stalemate was a lab leak).
    # Joint display map (owner-registered): loss ledger under the strict
    # ship-as-gains G1 (fairness gates passed; re-registration option queued).
    # Both rendered nowhere.
    "xfv_lambda_adjudication": "internal",
    "xfv_joint_display_map": "internal",
    # Owner-program loss ledgers (2026-07-15b): xwOBA output-blend on pWOBA
    # (knife-edge NO-SHIP, keep-alive at extended n), EV/barrel residual arm
    # (regresses; EV-on-pWOBA lane closed), eFV defensive tool grades and
    # physical-by-position (both regress; frame/athl untrainable). All
    # rendered nowhere.
    "pwoba_xwoba_blend": "internal",
    "pwoba_ev_arm": "internal",
    "xfv_defense_tools": "internal",
    "xfv_physical_position": "internal",
    # Owner-program wave 2 (2026-07-15): model-class/target sweep + feature
    # arms (both all-NO-SHIP with 2024-fold keep-alives) and the FA Gate-2
    # feature-arm harness (rate_line SHIPPED into fa_market; regime/age_pos/
    # qo_tier ledgered losses). All rendered nowhere.
    "xfv_model_class_sweep": "internal",
    "xfv_feature_arms_2026_07": "internal",
    "fa_market_feature_arms": "internal",
    "fa_market_supply_population": "internal",  # serve-side input alignment (wave-2 ship, 2026-07-16)
    "fa_market_class_age_anchor": "internal",   # serve-side input alignment (wave-2 ship, 2026-07-16)
    # 2026-07-23 program: S-XLINE Statcast measurement upgrade SHIPS live inside
    # the eFV pipeline (covered AAA 2023+ actives), so its methodology rides the
    # xfv glossary entry like the other live eFV layers.
    "xfv_statcast_line": ["xfv"],
    # S-XLINE-2/3/4 gate ledgers (2026-07-23), all rendered nowhere: the
    # sub-AAA feeds-proxy V0 STOP (yardstick mismatch, superseded by line3),
    # the S-XLINE-3 V0'-pass / primary-M-A-NULL run (AUX passes recorded as
    # inputs to S-XLINE-4), and the S-XLINE-4 incremental arms (whiff-K +
    # FB-velo overlay-ELIGIBLE per the registered ship rule; overlay not
    # implemented, nothing served changed).
    "xfv_statcast_line2": "internal",
    "xfv_statcast_line3": "internal",
    # line4 stopped being internal on 2026-07-29: its two INC reads are the
    # measurement a reader is shown next to the A-ball whiff / FB-velo pills.
    "xfv_statcast_line4": ["statcast_alevel_signal"],
    # S-XLINE-4 overlay (2026-07-23): implemented, FAILED its registered
    # post-flip 2-FV served ceiling (structural: fringe quantile-grid step is
    # 2.7 FV), reverted same day - defaults OFF, chip never renders, so no
    # user-facing methodology surface. Ledger in the line4 eval artifact.
    "xfv_statcast_overlay": "internal",
    # 2026-07-23 loss ledgers + diagnostics, all rendered nowhere: the
    # pwoba_xwoba_blend keep-alive re-gate (zero new resolved pairs, next
    # window 2026-11-15), the BT-1 bat-tracking hitter lane (both arms NULL),
    # the fantasy streamer-score arm sweep (no arm ships; join bug flagged to
    # the owner), the IFA bonus pedigree curve (7-tier LOCO gate FAIL; its one
    # robust structure later shipped as ifa_step_prior under a NEW gate),
    # and the provisional-penalty / ungraded-cap calibration diagnostic.
    "pwoba_blend_regate": "internal",
    "bat_tracking_hitters": "internal",
    "fantasy_startscore": "internal",
    "ifa_pedigree": "internal",
    # P1 V2 (2026-07-23): V1 FAILED same-day (committed loss in the same GATES
    # file); the V2 re-registration (bounded upward-only pull + bucket-mixture
    # baseline) passed all five clauses and SHIPS live inside the eFV
    # provisional path (run_backgrade + score_history), so its methodology
    # rides the xfv glossary entry like the other live eFV layers. The IFA
    # >= $1M step arm wired the same day under its own frozen gate rides it
    # too (it is a branch of the same served prior).
    "xfv_provisional_prior": ["xfv"],
    "ifa_step_prior": ["xfv"],
    "provisional_calibration": "internal",
    # F-SIDE-FIX (2026-07-23, owner-authorized fairness-fix attempt under the
    # queued G1-as-NO-HARM re-registration): the 07-23 attempt is a loss ledger
    # - the capped top-band joint recalibration fixes pit over-representation
    # (F1a) but fails the equal-slot gap clause F1b (pit tail has no
    # realized-WAR gradient, the TOP-QUANT root cause).
    # MAPPING CORRECTED 2026-08-07. This said "internal ... defaults OFF, hook
    # dead-by-default, rendered nowhere", which was true on 07-23 and stopped
    # being true on 07-24: the W-FSIDE-SHIP re-registration passed on repaired
    # labels and SHIPPED default ON (efv_score.py:1222
    # SIDE_FAIRNESS_FIX_DEFAULT = True), moving 467 board rows by up to 3.0 FV
    # (kade_anderson 62->59). It rewrites xfv_grade_display, so it is live eFV
    # scoring behaviour and documents through the eFV entry exactly like
    # efv_board_side_scale and xfv_role_ceiling, rather than hiding behind
    # "internal".
    "xfv_side_fairness_fix": ["xfv"],
    # --- 2026-07-29 display-index registration -----------------------------
    # The standing rule says every shipped model carries a registry row. These
    # rows close a long-standing gap for the user-facing plus-metrics: they are
    # DISPLAY INDICES rather than predictive models, so each is registered
    # 'unvalidated' with no eval artifact, and each points at the glossary
    # entry that carries its scale convention. The cross-family scale table
    # lives in docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md.
    "krp_plus": ["krp_plus"],                 # 100+10z, display pill decoupled from the eFV model feature
    "dvm_plus_org": ["dvm_plus"],             # org development index by window (incl. 6yDvM+ and the FVDvM+ bucket view)
    "dvm_plus_tools": ["tools_dvm_plus", "tool_specific_dvm_plus"],
    "dvm_plus_dollar": ["fin_dollar_dvm", "dvm_plus"],  # FV-tier-anchored, clamped 40-160 (the family's odd scale)
    "cs_plus": ["cs_plus"],                   # college cohort 100+10z, computed client-side
    "rps_plus": ["rps_plus"],                 # three variants under one name, all disclosed in the entry
    "tool_plus": ["tiebreaker_score"],        # not rendered directly; a draft/overseas TBS input term
    "draft_stock_plus": ["draft_stock_plus"],
    "tbs_prospect": ["tiebreaker_score"],
    "tbs_farm": ["farm_tiebreaker"],
    "iso_plus": ["iso_plus"],
    "pwr_plus": ["pwr_plus"],
    "hit_plus": ["hit_plus"],
    "pd_plus": ["pd_plus"],
    "stf_plus": ["stf_plus"],
    "fv_stuff_plus": ["stuff_grade_plus"],
    # --- 2026-07-29 display surfaces. All three are DISPLAY decisions, and each
    # one's glossary entry states in its own text how far the evidence goes.
    # A-ball / complex whiff + FB-velo pills: provisional, the two INC reads are
    # a forward correlation against a stat-line residual, not an outcome gate.
    "statcast_alevel_display": ["statcast_alevel_signal"],
    # Archetype comp panel: unvalidated with NO eval artifact, deliberately. The
    # entry carries the three caveats (search with no multiplicity correction,
    # a false health_warning in the source artifact, a missing generator).
    "archetype_comps": ["archetype_comps"],
    # The model lane behind that panel: measured, failed, deprecated. It maps to
    # the same entry because that entry is where the failure is written down for
    # a reader, which is the whole point of documenting a loss beside its display.
    "archetype_search": ["archetype_comps"],
    # --- WAR/PA+ and WAR/IP+ (2026-07-29 Arkmetric lane, master plan Phase G).
    # Descriptive display indexes: the forward gate was run and LOST to plain
    # season bWAR on all three pools, so every row is honestly `unvalidated` with
    # a null eval artifact and the ledger cited in its notes. Each maps to its own
    # glossary entry plus the trailing-window companion, because the entry text is
    # where a reader is told both what the number means AND that it is not a
    # forecast. The two WAR/IP+ entries are SEPARATE by design: the starter board
    # and the reliever board carry the same column title over two different anchor
    # pools, and the values are not comparable
    # (docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:77).
    # The `_adj` companions joined the family 2026-07-30, when the owner closed the
    # shrink call recorded OPEN in the ledger (docs/efv-2026-07-30/
    # WAR_RATE_SHRINK_OWNER_CALL.md). They map onto the SAME registry row rather
    # than taking their own: same anchor pool, same ledger, same `unvalidated`
    # verdict, same surface. What differs is the reading, which is exactly what a
    # glossary entry is for, so each got its own entry.
    # B3 level blend: a NO-SHIP loss ledger with no served number, so there is no
    # glossary term for a reader to look up. "internal" by construction, same as
    # the other candidate ledgers.
    "xfv_level_blend": "internal",
    # E1 repeat-level candidate: measured, default off, nothing served.
    "xfv_repeat_level": "internal",
    # Lane A measurement feeds: ingests with no served number yet.
    "savant_arm_strength": "internal",
    "savant_sprint": "internal",
    "war_pa_plus": ["war_pa_plus", "war_pa_plus_adj", "war_pa_plus_3yr"],
    "war_ip_plus_sp": ["war_ip_plus_sp", "war_ip_plus_sp_adj",
                       "war_ip_plus_sp_3yr"],
    "war_ip_plus_rp": ["war_ip_plus_rp", "war_ip_plus_rp_adj",
                       "war_ip_plus_rp_3yr"],
    # The trailing-window companion family across all three boards, one frozen
    # vintage artifact with three blocks.
    "war_rate_plus_3yr": ["war_pa_plus_3yr", "war_ip_plus_sp_3yr",
                          "war_ip_plus_rp_3yr"],
    # --- derived tool-grade measurement tables (2026-07-30, master plan Phase 4).
    # "internal" by construction: the row documents a REFERENCE TABLE, not a
    # served number. Nothing on the site reads data/tool_grade_tables.json, so
    # there is no glossary term for a reader to look up; the reader-facing
    # write-up is the Phase 6 explainer, built FROM this artifact, and the
    # methodology text is docs/efv-2026-07-30/TOOL_GRADE_TABLES.md. If any of
    # the three inventions is ever wired into a display or a weight, that lane
    # ships its own glossary entry and this line changes with it.
    "tool_grade_tables": "internal",
    # --- position + role assignment (2026-07-30, master plan Phase 5).
    # BOTH SHIPPED 2026-07-30 (owner decision): position_observed is now a served
    # payload field with live consumers, and pitcher_role_usage runs in both
    # directions. They stay "internal" anyway, and the reason is the same for both:
    # neither is a NUMBER a reader looks up. They are POSITION STRINGS - "SS", "RP" -
    # that feed cohorts, weights and role gates. The glossary is a dictionary of
    # metrics; adding "SS" to it would not answer any question a reader has.
    # What a reader could reasonably ask is why the card says 3B while the peer pool
    # says SS, and that belongs on the card as a labelled secondary line, not in the
    # glossary. Methodology text: docs/efv-2026-07-30/POSITION_ROLE_GATE.md.
    # If either ever becomes a displayed INDEX (say a "spectrum move" score), it
    # ships a glossary entry and this line changes with it.
    "position_observed": "internal",
    "pitcher_role_usage": "internal",
}


def _registry_ids() -> set[str]:
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    return {m["model_id"] for m in reg["models"]}


def _glossary_ids() -> set[str]:
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return {e["id"] for e in g["entries"]}


def test_every_registry_model_has_a_documentation_decision():
    missing = _registry_ids() - set(MODEL_GLOSSARY)
    assert not missing, (
        f"registry models without a methodology mapping: {sorted(missing)} - "
        "add each to MODEL_GLOSSARY in test_methodology_freshness.py, pointing "
        "at the glossary entry that documents it (write one if none exists)")


def test_no_stale_mappings_for_removed_models():
    stale = set(MODEL_GLOSSARY) - _registry_ids()
    assert not stale, f"mapped models no longer in the registry: {sorted(stale)}"


def test_mapped_glossary_entries_exist():
    gids = _glossary_ids()
    broken = {m: [g for g in targets if g not in gids]
              for m, targets in MODEL_GLOSSARY.items()
              if targets != "internal" and any(g not in gids for g in targets)}
    assert not broken, f"mappings point at missing glossary entries: {broken}"


def test_mapped_entries_carry_methodology_text():
    """The mapped entry must actually explain HOW (methodology field or a
    substantive definition), not just exist as a stub."""
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in g["entries"]}
    thin = []
    for m, targets in MODEL_GLOSSARY.items():
        if targets == "internal":
            continue
        if not any(len((by_id[t].get("methodology") or by_id[t].get("definition") or "")) >= 80
                   for t in targets):
            thin.append(m)
    assert not thin, f"models whose glossary docs are stubs (<80 chars everywhere): {thin}"
