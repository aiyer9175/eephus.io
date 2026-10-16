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
    # The 2026-09-04 eWAR label epoch and the four driver families swept beside it.
    # ALL FIVE ARE INTERNAL, and on a single consistent reason: not one of them moved a
    # served number or a line of page copy. The epoch lab measures the label swap and its
    # verdict is that the swap changed nothing a reader can see (hit equivalent, pit
    # undecided), which is why the eWAR frame disclosure on the served surfaces is a BASIS
    # statement and not an accuracy claim. The four driver families shipped no feature:
    # volume and cumulative counts, per-level and per-league weights, age-by-production
    # interactions and the health profile are all recorded nulls. If any of them is ever
    # promoted, the mapping graduates to the xfv entry with it.
    "xfv_ewar_label_epoch": "internal",
    "xfv_volume_drivers": "internal",
    "xfv_level_weights": "internal",
    "xfv_age_level_interaction": "internal",
    "xfv_health_profile": "internal",
    "arb_award": ["arb_award_model", "arb_market_residual"],
    "arb_label_set": "internal",
    "arb_fa_link": "internal",
    "arb_ladder": "internal",
    # Ask C, 2026-09-16: the control-window salary path. Mapped to the two
    # entries that document what it prices and what prices it, because the
    # dedicated `salary_path` entry lands with the copy pass in the same
    # program and joins this list then (it also joins prospect_surplus and
    # trade_machine_surplus, which serve the same number).
    "control_window_salary_path": ["surplus_value", "arb_award_model"],
    "xfv_label_replacement": "internal",
    "xfv_rank_objective": "internal",
    "surplus_decomposition_v6": "internal",
    "xfv_dist_recalibration": "internal",
    # A-CLAIM-6, forecast encompassing (2026-09-06). INTERNAL on the same reasoning as
    # the families above: it is a DIAGNOSTIC, its verdict is UNDECIDED on both sides,
    # and it moved no served number and no line of page copy. It exists so the question
    # "does the model leg add anything to consensus" has a recorded answer instead of an
    # assumption. If it ever resolves, the mapping graduates to the xfv entry with it.
    "efv_encompassing": "internal",
    # H-PRED-3 (2026-09-07). INTERNAL: the model LOST its gate, the /hof/ predictor
    # section stays dark, and no served number and no page copy rests on it. The
    # section's own copy reports the loss and reads it off the artifact.
    "hof_merit": "internal",
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
    # A-1, the AUC floor lane (2026-08-14). NOT internal: it is the first floor
    # ever derived for the AUC leg, and the accuracy copy is written to its
    # conclusion (indistinguishable on discrimination, not better).
    "xfv_auc_floor": ["xfv", "consensus_fv"],
    # S-1, the serve-basis lane (2026-08-14). INTERNAL: it measures the gap
    # between a published arm and the served ordering and promotes nothing. If
    # the remedy it points at is ever taken, the finding moves to the xfv entry
    # and this mapping changes with it.
    "xfv_serve_basis": "internal",
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
    "ba_risk": "internal",  # dark feature on a revival clock; no served surface
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
    "upgrade_option": ["opt_pct"],   # Tier 2 grade-option layer; surfaced as the PROSPX player-page PLUS% line
    # Tier 2 cross-source scale map; shapes the live consensus_fv scale. The
    # normalized_source_grade entry (2026-07-29) is the reader-facing version:
    # why a consensus can land outside the range of the grades on the card.
    "grade_normalization": ["consensus_fv", "normalized_source_grade"],
    "fa_projection_marcel": ["fa_projection_engine"],
    "fa_war_paths_decay": ["fa_projection_engine"],
    "proj_def_prior": "internal",   # a hit feature of fa_war_paths_decay; gate-artifact row
    # docs/PROJ_COMPONENTS_GATE.md (2026-10-08): registered, not read; nothing served
    # reads either row until a PJ-C pass and the PJ_8 flip carry a glossary term.
    "proj_components": "internal",
    "proj_component_stack": "internal",
    "prospect_def_value": "internal",  # Will Cahoon def model (local reconstruction); eFV-swap loss ledger
    # eephus WAR: the served WAR series from the 2026-09-03 epoch (war_source
    # default provider ewar_v2); the glossary entry carries the frame disclosure
    # and the gate record, so it is reader-facing and no longer internal.
    "ewar": ["ewar"],
    # The 2026-10-03 fWAR label epoch: published fWAR is the TRAINING label (the WAR
    # glossary entry carries the frame disclosure and names both series), while eWAR v2
    # stays the displayed WAR (owner answer EPOCH-Q4). The epoch lab measures the swap
    # and moves no page copy itself, like its 2026-09-04 predecessor.
    "fwar": ["war"],
    "xfv_fwar_label_epoch": "internal",
    # 2026-08-04 gated experiments, all three measured NO-SHIP (loss ledgers).
    "xfv_pace_from_entry": "internal",   # pre-registered kill criterion fired on the hitter weight sign
    "xfv_level_blend_arms": "internal",  # 17 of 18 cells negative; the anchor arm is a measured loss
    "eta_age_continuous": "internal",    # loses both legs of the criterion v39 was shipped on
    "fa_market": ["fa_projection_engine", "deal_plus"],
    "fa_rational_value": ["rational_value", "contract_surplus"],
    "fa_dpw_series": ["winter_dpw", "dpw_tier"],
    "fa_team_fit": ["fit_components"],
    "fa_penter": ["p_enter"],
    "fa_qo_pick_tax": ["qo_tax"],
    "mlb_projections_vets": ["mlb_projections"],
    "mlb_projections_prospects": ["mlb_projections", "proj_buckets"],
    "prospect_surplus": ["surplus_value"],
    "fv_to_war_anchors": ["fv_to_war_table"],
    "wag": ["wag", "warwag"],
    # TL_15: the Source Accuracy Tools tab prints look W; both rows are documented by the
    # two terms the tab defines.
    "tool_implied_production": ["tool_implied_production", "tool_above_grade"],
    "tool_source_accuracy": ["tool_above_grade", "tool_implied_production"],
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
    "statcast_tracked_parks_card": ["statcast_tracked_parks"],  # M25AAA-2 relabel: the PROSPX Statcast (tracked parks) card
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
    "college_pitk_box_challenger": "internal",  # registered 2026-10-01, not scored; serves nothing
    "college_translation_career_refit": "internal",  # registered 2026-10-02, not scored; serves nothing
    "college_translation_scorecard": ["single_a_equivalent"],  # the What-to-trust copy and receipts read it
    "collegesavant_stuff": ["collegesavant_stuff_plus"],  # W4 governance of the shipped display lineage
    "advancement_pace": ["advancement_pace_plus"],        # W5 descriptive display (contract: never a model input)
    # eFV holistic program 2026-07-24 (docs/efv-2026-07-24/GATES.md):
    "efv_scoreboard": ["xfv"],             # eFV accountability scoreboard (source-comparison panel)
    # eFV v2 champion H0 (1d6adb29). Not "internal": its development rows print on
    # the glossary Source Comparison progress ledger, the same panel as the
    # scoreboard above, so it takes the scoreboard's entry.
    "efv_v2_h0": ["xfv"],
    "efv_v2": ["xfv"],
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
    "eta_fg_blend": ["eta"],               # FanGraphs blend arm B, served 2026-09-30
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
    "xfv_thin_lane_surplus_odds": "internal",  # registered 2026-10-08, not read; serves nothing
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
    # The board grade for the constant-anchor floor cohort is SERVED from the
    # provisional map (efv_score.route_floor_grade), so the two entries that
    # document the two scales are what a reader needs: xfv for the flagship
    # outcome grade and xfv_ungraded for the provisional map that replaces it.
    "efv_board_floor_routing": ["xfv", "xfv_ungraded"],
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
    # Positional ladder v2 (EWAR_LADDER_REDERIVE, 2026-10-15): the position-switcher
    # ladder Position Fit values with, documented by its own entry and by the
    # Position fit entry that composes it.
    "positional_ladder_v2": ["positional_ladder", "position_fit"],
    "positional_ladder_v3": ["positional_ladder"],
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
    # Card Market: module REMOVED 2026-09-05 (owner decision); the deprecated
    # registry row stays as the record and keeps its internal mapping.
    "card_market_index": "internal",
    # 2026-08-16 betting-model lane. Neither is user-facing: the Platt
    # calibration is an UNSERVED seam behind SERVE_PROB_CALIBRATION whose
    # pre-registration lives in docs/diamond-betting.md section 11b, and the
    # Elo row is a validation-ladder baseline that no page renders. If the
    # calibration ever serves, the /betting/ methodology copy documents it
    # then, on the page, the same decision as betting_game_prob above.
    "betting_prob_calibration": "internal",
    "betting_elo_benchmark": "internal",
    # 2026-10-01 BRACKET_SIM_BUILD: the postseason bracket simulator serves the
    # Pennant and World Series columns on /betting/ and the Pennant tile on
    # /franchise/ during the postseason, so a reader looks it up.
    "postseason_bracket_sim": ["postseason_bracket_sim"],
    # 2026-08-18 SDR W0: registered-and-waiting rows (data-blocked intake).
    # They gain real glossary terms in the W2 display wave, where the copy
    # ships; until a surface exists there is nothing for a reader to look up.
    "sdr_mlb": "internal",
    "sdr_milb": "internal",
    # 2026-08-16 registry-hygiene wave: the five published fantasy surfaces
    # that had no registry row. Same documentation decision as the Diamond
    # trio above: each ships on a page that carries its method and its limits
    # in user-facing copy (the ROS boards mark every heuristic cell _est, the
    # buy/sell boards say they are a luck screen, the dynasty board states its
    # blend), and none of them is an Arkmetric the site glossary defines. The
    # dynasty blend's eFV INPUTS are documented by the xfv glossary entry;
    # the blend itself is a ranking convention, not a metric.
    "fantasy_dynasty_blend": "internal",
    "fantasy_ros_rankings": "internal",
    "fantasy_roto_valuation": "internal",
    "fantasy_buy_sell": "internal",
    "fantasy_closer_depth": "internal",
    # 2026-10-01 (owner answer M21-4): the Dynasty Fantasy Rank states its
    # design, its replacement level and its backtest reading on the page from
    # its own payload; a ranking on fantasy scoring, not an Arkmetric.
    "fantasy_combined_rank": "internal",
    # X-D1 gmLI deployment-context metric: gate passed and wired 2026-07-02
    # (bullpen_export join + /mlbstats/ column); documented by its glossary
    # entry.
    "leverage_consistency": ["gmli_3yr"],
    # X-D2 AgeRel+ candidate: numeric bar met but not a clear pass; NOT
    # wired, owner decision queued in docs/archive/REVIEW_QUEUE.md.
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
    # PAR (Q8_06, owner asks 10 to 12 and 17 of 2026-09-30): a descriptive pitch
    # rate index on the three boards and PROSPX, documented by its own entry.
    "par": ["par"],
    "hem_plus": ["hem_plus"],
    "hem_plus_3yr": ["hem_plus_3yr"],
    "dem_plus": ["dem_plus", "team_dem_plus"],
    "dem_plus_3yr": ["dem_plus_3yr"],
    "fwar_replica": "internal",
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
    "xfv_model_class_readjudication": "internal",  # loss ledger; rendered nowhere
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
    # 2026-10-14 owner flip NOV15-PWOBA-FLIP = (a): the re-gated blend is the
    # served pWOBA, documented by the pwoba entry.
    "pwoba_blend_regate": ["pwoba"],
    "bat_tracking_hitters": "internal",
    # 2026-10-14: the served construction of the bat-tracking blend (arm B)
    # passed its one re-read (docs/BAT_TRACKING_SERVED_GATE.md) and ships as
    # the BT Blend column with its own glossary entry.
    "btblend_plus": ["btblend_plus"],
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
    # PV-05 (2026-10-01): the served provisional grade scored against first source
    # grades. PV-08 (2026-10-02) built its surfaces, the Source Comparison Provisional
    # track record block and the PROSPX card receipt; the xfv_ungraded entry documents both.
    "provisional_first_grade": ["xfv_ungraded"],
    # PV-06 (2026-10-02): provisional v2 heads and their BACKCAST. PV-07 (2026-10-02) built
    # the board section that reads data/provisional_v2.json; documented in the same entry.
    "provisional_v2": ["xfv_ungraded"],
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
    "dvm_plus_org": ["dvm_plus"],             # org development index by window (incl. 7yDvM+ and the FVDvM+ bucket view)
    "dvm_plus_tools": ["tools_dvm_plus", "tool_specific_dvm_plus"],
    "dvm_plus_dollar": ["fin_dollar_dvm", "dvm_plus"],  # eFV-tier-anchored, unclamped since 2026-07-29 (the family's odd scale)
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
    # season WAR (the bWAR series, 2026-07 lab run; the lab re-runs on eWAR at the
    # 2026-09 epoch's rebuild wave) on all three pools, so every row is honestly `unvalidated` with
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

    # 2026-08-19 registry census: ten previously off-ledger served models.
    # Documentation decisions verified against data/glossary.json entry ids
    # the same date.
    "mock_draft": "internal",          # no glossary entry; the draft view labels its own basis
    # The stock / stock_arrow entries document the consensus-FV stock delta,
    # NOT the de-noised rank-movement engine these two rows register, so
    # neither may claim them; a movement entry would have to be written first.
    "farm_movement": "internal",
    "rank_movement": "internal",
    "versa_positions": ["versa"],      # the versa entry states the same 10-game / 5-start rule
    "multiposition_bonus": "internal",
    "fa_aging_curves": "internal",     # engine internals; the FA methodology copy covers the projection, not the curve fits
    # 2026-10-09 (AG_5_AGING_SERVICE_BUILD_DARK): aging v3 registered, not read, built dark;
    # nothing served reads it until docs/AGING_V3_GATE.md records a pass, so no
    # glossary entry exists yet; the flip that serves a consumer writes one.
    "aging_v3": "internal",
    "aging_v3_prospect_shape": "internal",
    "aging_v3_health": "internal",
    "milb_translation": ["milb_translation"],
    "grpo_prospect": ["breakout_indicator"],  # the badge the score serves is documented there
    # stuff_grade_plus documents FVStuff+ only; no Cmd+ entry exists, so the
    # command half of the same cohort pass stays internal until one is written.
    "composite_cmd_plus": "internal",
    "org_sur_plus": ["sur_plus"],      # the sur_plus entry IS OrgSur+ (scale + financial-branch role)

    # --- 2026-09-06 Wave 0 of the Opus program (docs/master-plan-2026-09-05-opus.md) ---
    #
    # Three of the seven touch a reader-visible surface, so the "internal" call on
    # them is a real decision rather than a default, and it rests on the same rule
    # the Diamond rows settled on 2026-08-05: THE SITE GLOSSARY DOCUMENTS BASEBALL
    # METRICS. A betting objective, a prop price and a shadow ledger tag are
    # products of the betting module, and the /betting/ page carries their method
    # and their limits in its own copy. Writing glossary stubs for them would put
    # gambling machinery in a glossary a reader opens to look up wRC+.
    #
    # betting_per_market_objective changes WHICH markets publish, which a reader
    # can see. It is internal because the thing a reader needs is the rule, and the
    # rule now rides the published row itself: every slot carries market_policy and
    # the evidence caveat, so the disclosure travels with the pick instead of
    # sitting in a glossary the reader would have to go find.
    "betting_per_market_objective": "internal",
    # betting_props_pmf sets the distribution each prop market is priced under. It
    # ships UNVALIDATED and names no artifact, deliberately: the sub-models have not
    # graded dark against base rates yet (owner decision 8). The method block on the
    # served row publishes the chosen distribution per market, which is the honest
    # place for it while the verdict is still open.
    "betting_props_pmf": "internal",
    # The two dark grades. Internal for the same reason every other betting
    # row is: the site glossary documents baseball metrics, and a prop
    # sub-model graded against a base rate is gambling machinery whose
    # limits belong in the /betting/ page copy. They serve nothing at all
    # today, so there is not even a number for a reader to look up.
    "betting_props_hr_dark": "internal",
    "betting_props_k_dark": "internal",
    # betting_shadow_subledger is measurement infrastructure. Nothing renders it;
    # it exists so a per-market verdict can be read later without re-deriving the
    # ledger, and its rows are unpriced by construction.
    "betting_shadow_subledger": "internal",
    #
    # The remaining four move no served number at all.
    #
    # claim_instruments_v6 is a REGISTRATION, not a reading. The V6 cells are signed
    # and dated before any number is computed (owner decision 1) precisely so they
    # cannot be swapped post hoc; until the 2027 read the accuracy page still states
    # the V5 frame, and the V5 claim cells are what the xfv entry documents. When V6
    # is read this mapping graduates to the xfv entry with it.
    "claim_instruments_v6": "internal",
    # A-CLAIM-4, the bust-inclusive frame. Internal on the same reasoning as
    # claim_instruments_v6 above: it is a receipt about the REACH of a claim
    # the xfv entry already documents, not a metric a reader looks up. If it
    # ever changes what the accuracy page says, that copy ships with it.
    "claim_bust_inclusive": "internal",
    # A-CLAIM-13, the rater scale view. Internal, and this one has to STAY
    # internal for a reason the other two do not share: its block rho is a
    # NARROWER statistic than the pooled Spearman the accuracy page publishes,
    # measured on percentile-normalized outcomes that throw away magnitude. Put
    # it in front of a reader beside the pooled number and it reads as a second,
    # disagreeing head-to-head. A test in test_rater_scale_view.py pins that no
    # page and no other module reads the artifact key at all.
    "claim_rater_scale_view": "internal",
    # A-CLAIM-3, the exposure-matched label. Internal, and this one is the most
    # tempting of the three to surface, because "eFV and the consensus differ by
    # 0.0001 on a like-for-like label" is a sentence anybody would want to
    # publish. It stays internal until the confirmatory read declared in the
    # alpha-spending clause, because a receipt taken at a time of our choosing
    # is not the same object as a pre-declared read, and the accuracy page
    # already states the tie from the frame it is entitled to.
    "claim_exposure_matched_label": "internal",
    # The Hall of Fame induction ledger. INTERNAL, and it will stay internal even
    # after /hof/ ships: it is a label substrate, not a metric a reader looks up.
    # What a reader WILL see from it is the induction column's disclosure copy,
    # which says that inducted-as-a-player-by-the-writers is the only induction
    # this data can verify and that every other route reads as unverified. That
    # sentence belongs to the page, and it is derived from
    # data/hof_ledger_eval.json rather than typed.
    "hof_induction_ledger": "internal",
    # The In-Game Management pair. BOTH internal, and the reason is the same one
    # that keeps the plus metric off the page: there is no reader-facing METRIC
    # here to look up. What renders is a league result and a style board, and
    # every sentence explaining them is derived into the payload rather than
    # written as a definition. If a management plus metric is ever gated in, it
    # earns a glossary entry then and this mapping graduates with it.
    # The playoff simulator. NOT internal: its numbers render on two surfaces,
    # the /projections/ team outlook and the Futures tab. It points at the
    # entries that carry the reader-facing method behind what it consumes and
    # what it emits.
    "playoff_odds_sim": ["mlb_projections", "fa_projection_engine"],
    "mgmt_running_game": "internal",
    "mgmt_board_export": "internal",
    # The bunt family (registered 2026-10-02, audit RFR02) is internal for the
    # same reason as the running game: a league result whose explaining
    # sentences are derived into the payload, and no plus metric.
    "mgmt_bunt_dv": "internal",
    # The decision ledger trio (2026-09-23, D2 Wave A). NOT internal: realized
    # mWPA, DVS and the five style z-scores are reader-facing figures on the
    # Clubs, Decisions and League tabs, and each has a glossary entry that says
    # in its own words what the number is and what it is not (skill).
    "mgmt_decision_ledger": ["realized_mwpa", "manager_agent"],
    "mgmt_state_baseline": ["dvs"],
    "mgmt_style_z": ["hook_z", "pen_z", "bench_z", "ibb_z", "visit_z"],
    "franchise_index": ["franchise_index"],
    "franchise_branch_score": ["franchise_branch_score"],
    # The public benchmark bake-off. NOT internal: its panel RENDERS on /hof/,
    # and it is the one comparison that page publishes. It points at the two
    # glossary entries that carry the reader-facing method behind the columns it
    # scores, because what a reader needs when they see "HoF Monitor beats our
    # WAR shelf" is what JAWS and WAR7 actually are.
    "hof_public_bakeoff": ["jaws", "war7"],
    # pbp_corpus_base_state is a data substrate under .cache/. No page reads it. It
    # earns a registry row because a reconstruction that is WRONG would silently
    # poison every In-Game Management number built on top of it, so its agreement
    # rate against the payload's own offense block belongs in the ledger.
    "pbp_corpus_base_state": "internal",
    # xfv_driver_auc_leg is the AUC half of the driver gate. It is a FLOOR
    # derivation and a veto, not a feature: it shipped nothing and, on the record,
    # its whole purpose is to stop arms that clear rho while failing discrimination.
    "xfv_driver_auc_leg": "internal",
    # hof_benchmark_shelf reproduces the public Hall of Fame yardsticks (JAWS, WAR7,
    # ink, Monitor, Standards) so our own numbers can be scored against them. It has
    # no surface yet; the Hall of Fame module is Part 3 of the plan and unbuilt. It
    # names no artifact because reproduction_check() computes the comparison in
    # process from the daily WAR cache rather than writing a file, which is why the
    # verdict is provisional and not validated.
    "hof_benchmark_shelf": "internal",

    # --- 2026-09-06 Wave 1, the claim program's two instruments ---
    #
    # xfv_program_arm_ledger is a COUNT of what this program has tested. It is
    # internal because a reader looking up a metric is not the audience: the
    # audience is whoever reads the NEXT survivor and needs to know it was found
    # against a 48-arm denominator. If a survivor ever ships, the count travels
    # with it in that claim's own copy, not as a glossary term.
    "xfv_program_arm_ledger": "internal",
    # xfv_disagreement_floor DOES change reader-facing copy on four Source
    # Comparison surfaces, and it is still internal for the same reason the eFV
    # entry already covers the head-to-head: the glossary documents the METRIC,
    # and this lane put an interval around a number the xfv entry already owns.
    # The qualifier now rides the rendered sentence itself, derived from the
    # artifact, which is the honest place for it: a share card gets screenshotted
    # away from any glossary a reader might otherwise consult.
    "xfv_disagreement_floor": "internal",
    # xfv_tilt_census measures the distance between what the board serves and
    # what the accuracy page scores. Internal because it names no metric a reader
    # looks up: it is a bound on the REACH of a claim the xfv entry already
    # carries. If its provisional-grade finding ever changes what the board
    # serves, that change ships with its own copy and this line moves with it.
    "xfv_tilt_census": "internal",

    # --- 2026-09-06: the In-Game Management substrate ---
    #
    # Both internal, and both will STAY internal even after /management/ ships,
    # on the same rule the Diamond rows settled: the site glossary documents
    # baseball metrics, and a win-expectancy engine is machinery rather than a
    # term a reader looks up. What the reader will need is what a decision value
    # MEANS, and that belongs in the module's own page copy beside the numbers,
    # not in a glossary entry they would have to go and find.
    #
    # If MWAR itself ever ships as a named metric, THAT gets a glossary entry
    # and this line changes with it. Neither of these two is MWAR: one is the
    # engine, the other is one decision family with no manager attribution at
    # all.
    "win_expectancy_state": "internal",
    "mwar_running_game": "internal",
    # The gate battery is machinery, not a term a reader looks up. It stays
    # internal even when /management/ ships, because what a reader needs is
    # the VERDICT, and the verdict rides the page copy beside the board it
    # governs rather than sitting in a glossary they would have to go find.
    "mwar_running_gate": "internal",

    # --- 2026-09-06: the Hall of Fame data shelf ---
    #
    # Internal for now and NOT permanently. Neither is a metric a reader looks
    # up: one is an ingest and the other is a label definition. But the label's
    # censoring rule IS something a reader of the eventual /hof/ page will need,
    # because "we do not score a player the voters have not finished deciding
    # on" is the difference between an honest Hall of Fame model and one that
    # quietly says every recent candidate is a no. When that page ships, the
    # rule ships with it in the page's own copy, and if a named metric comes out
    # of the predictor it gets a glossary entry and these lines move.
    "hof_ballot_panel": "internal",
    "hof_label_ledger": "internal",
    # starter_workload_xouts (2026-10-08) is the stage-1 workload read of the
    # betting section "Starter workload: expected outs and pitches per start".
    # Nothing served reads it and a stage-1 PASS licenses nothing served, so it
    # has no reader-facing term until a props or price flip names one.
    "starter_workload_xouts": "internal",
    # team_win_distribution and team_run_projection (2026-10-09, TM_2_TEAM_SCORER)
    # are the two team gate rows docs/TEAM_PROJECTIONS_GATE.md section 5.3
    # defines: registered, not read, nothing served, no candidate number yet.
    # A reader-facing term arrives with the flip that serves one (TM_8).
    "team_win_distribution": "internal",
    "team_run_projection": "internal",
    # game_intensity_effects (2026-10-09, Q10_07) is the stage-1 read of the
    # betting section "Game intensity: stakes, matchup quality and the
    # postseason". Nothing served reads it and stage 1 licenses no price; the
    # chip's own row and glossary terms arrive with the chip (Q10_09).
    "game_intensity_effects": "internal",
    # tool_tables_rederived (2026-10-14, TL_21_TOOL_TABLE_REDERIVE_LOOK) is the one
    # look T read of docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part T:
    # provisional, measured. Since TL_23_SCOUTING_PAGE_FLIP (2026-10-15) the
    # /scouting/ tool tiers print a passing cell, and tool-implied production
    # says how.
    "tool_tables_rederived": ["tool_implied_production"],
    # scouting_reference (2026-10-15, TL_23_SCOUTING_PAGE_FLIP): the /scouting/
    # page's transcription and served value tables; Future Value tiers and the
    # 20-80 scale document it.
    "scouting_reference": ["scouting_reference", "twenty_eighty"],
    # eTools (ETOOLS_FLIP_PREP, 2026-10-15): the six passing eTools, dark until the
    # owner flips ETOOLS_ON; each is documented by the eTools entry and its own.
    "etool_ehit": ["etools", "ehit"],
    "etool_epow": ["etools", "epow"],
    "etool_esel": ["etools", "esel"],
    "etool_ebat": ["etools", "ebat"],
    "etool_efb": ["etools", "efb"],
    "etool_ecmd": ["etools", "ecmd"],
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
