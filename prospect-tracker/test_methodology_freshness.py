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
    "fa_projection_marcel": ["fa_projection_engine"],
    "fa_war_paths_decay": ["fa_projection_engine"],
    "proj_def_prior": "internal",   # a hit feature of fa_war_paths_decay; gate-artifact row
    "prospect_def_value": "internal",  # Will Cahoon def model (local reconstruction); eFV-swap loss ledger
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
    "consensus_fv": ["consensus_fv"],
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
    # PAL = the /pal/ Pitcher Alchemy Lab role-conversion screen; documented by its
    # FIT-score + conversion-model glossary entries.
    "pal_conversion": ["pal_conversion", "rp_sp_fit", "sp_rp_fit"],
    # Holistic pass 3 (2026-07-01) model-dev artifacts, rendered nowhere:
    # the rejected eFV isotonic candidate (loss ledger), the SC+ per-component
    # signal isolation, and the surplus $/WAR-level stress test.
    "xfv_isotonic_calibration": "internal",
    "sc_plus_component_diagnostic": "internal",
    "surplus_sensitivity_diagnostic": "internal",
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
    # Review-queue round (2026-07-02): the eFV bucket-calibration final
    # attempt under a production-relevant gate; rejected, loss ledger,
    # rendered nowhere.
    "xfv_grade_recal3": "internal",
    # Review-queue round loss ledgers, all rendered nowhere: the total-WAR
    # band replacement (rejected, bands dropped), MiLB park factors
    # (infeasible), ERA-shrink unification (keep two values).
    "war_total_band_calibration": "internal",
    "milb_park_factors": "internal",
    "era_shrink_unification": "internal",
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
