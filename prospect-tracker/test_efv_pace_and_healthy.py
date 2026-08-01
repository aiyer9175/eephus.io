# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Two 2026-07-31 owner asks that share no code but do share a discipline:
publish the counterfactual instead of leaving the reader to invert it.

  * pace from entry - n_milb_seasons counts seasons without knowing where the
    player STARTED, and DSL is rank 0, so a DSL climber carries a bigger "slow"
    penalty than a college draftee who covered half the ladder.
  * healthy eFV - the injury factor multiplies the model leg of a blend and then
    passes through a nonlinear grade map, so no consumer can divide it back out.
"""

from __future__ import annotations

import efv_dataset as ed
import efv_model as em
import efv_score as es
import value_framework as vf


# ---- pace from entry ---------------------------------------------------------

def _ladder(*pairs):
    """(season, level_rank) newest-first, the order efv_dataset builds."""
    return [{"season": s, "level_rank": r} for s, r in pairs]


def test_pace_ranks_a_dsl_climber_above_a_stalled_repeater():
    """The whole point of the feature: reaching AA from the DSL is not slow."""
    arias = _ladder((2026, 4), (2025, 4), (2024, 2), (2023, 0))
    stalled = _ladder((2026, 4), (2025, 4), (2024, 4))
    a = ed._pace_from_entry(arias, arias[0])
    s = ed._pace_from_entry(stalled, stalled[0])
    assert a["pace_from_entry"] > s["pace_from_entry"]
    assert a["entry_level_rank"] == 0.0 and s["entry_level_rank"] == 4.0
    assert s["pace_from_entry"] == 0.0


def test_pace_does_not_punish_the_low_starter_for_the_extra_rungs():
    """A DSL bat at AA in 3 elapsed years and a college bat at AA in 1 both
    climbed; the DSL bat covered MORE ladder and must not read slower per
    season than a player who sat still."""
    dsl = _ladder((2026, 4), (2025, 4), (2024, 2), (2023, 0))
    college = _ladder((2026, 4), (2025, 2))
    assert ed._pace_from_entry(dsl, dsl[0])["pace_from_entry"] >= 1.0
    assert ed._pace_from_entry(college, college[0])["pace_from_entry"] >= 1.0


def test_pace_degenerate_inputs_are_neutral_not_crashes():
    assert ed._pace_from_entry([], {})["pace_from_entry"] == 0.0
    one = _ladder((2026, 2))
    got = ed._pace_from_entry(one, one[0])
    assert got["pace_from_entry"] == 0.0 and got["entry_level_rank"] == 2.0


def test_left_censored_entry_is_flagged():
    """A first observed season at the StatsAPI coverage floor may not be the
    player's real entry, so the pace is a lower bound and must say so."""
    censored = _ladder((2018, 4), (2015, 0))
    assert ed._pace_from_entry(censored, censored[0])["entry_observed"] == 0.0
    clean = _ladder((2026, 4), (2023, 0))
    assert ed._pace_from_entry(clean, clean[0])["entry_observed"] == 1.0


def test_pace_columns_are_emitted_unconditionally():
    """_fit_lgbm_mono indexes feats[k] with NO default, so a key that exists
    only on some rows is a crash, not a missing value."""
    for row in ({"milb": {}}, {}, {"milb_unavailable": True}):
        feats = em._vec(row, "hit")
        for k in ("pace_from_entry", "entry_level_rank", "entry_observed"):
            assert k in feats, (k, row)


def test_pace_is_not_in_the_shipped_feature_sets_yet():
    """Pre-registered and default OFF: it has not been gated."""
    assert em.PACE_FROM_ENTRY is False
    for spec in (em._FEATURES_HIT, em._FEATURES_PIT):
        names = [k for k, _sign in spec] if spec and isinstance(spec[0], tuple) else list(spec)
        assert "pace_from_entry" not in names


# ---- the chip narration ------------------------------------------------------

_SLOW = es._FACTOR_LABELS["n_milb_seasons"]


def test_fast_riser_chip_is_relabelled():
    factors = [{"label": _SLOW, "dir": "down", "mag": 0.3}]
    out = es._relabel_pace_factor(factors, {"pace_from_entry": 1.33,
                                            "entry_level_rank": 0.0})
    assert out[0]["label"] != _SLOW and "fast riser" in out[0]["label"]
    assert "low start" in out[0]["label"], "a DSL entry should be named"
    # direction and magnitude are the MODEL's and must not be edited
    assert out[0]["dir"] == "down" and out[0]["mag"] == 0.3


def test_slow_mover_chip_is_left_alone():
    factors = [{"label": _SLOW, "dir": "down", "mag": 0.3}]
    out = es._relabel_pace_factor(factors, {"pace_from_entry": 0.4,
                                            "entry_level_rank": 4.0})
    assert out[0]["label"] == _SLOW


def test_relabel_is_inert_without_a_ladder():
    factors = [{"label": _SLOW, "dir": "down", "mag": 0.3}]
    assert es._relabel_pace_factor(factors, None) == factors
    assert es._relabel_pace_factor(factors, {}) == factors


def test_relabel_never_touches_other_factors():
    factors = [{"label": "Production (OPS) vs level", "dir": "up", "mag": 0.9},
               {"label": _SLOW, "dir": "down", "mag": 0.3}]
    out = es._relabel_pace_factor(factors, {"pace_from_entry": 2.0,
                                            "entry_level_rank": 2.0})
    assert out[0] == factors[0]


# ---- healthy eFV -------------------------------------------------------------

def test_healthy_grade_is_above_the_injured_grade():
    """An injury penalty can only cost grade, so removing it can only add."""
    for cons_war, war, inj in ((3.0, 4.0, 0.90), (2.0, 2.5, 0.70), (1.0, 0.5, 0.82)):
        tilted = es._apply_war_tilt(war, inj)
        healthy = es._apply_war_tilt(war, 1.0)
        g = vf.outcome_implied_fv(tilted, exposure_seasons=es.TARGET_SEASONS)
        gh = vf.outcome_implied_fv(healthy, exposure_seasons=es.TARGET_SEASONS)
        assert gh > g, (war, inj, g, gh)


def test_healthy_counterfactual_keeps_the_other_tilts():
    """It answers "what if he were healthy", NOT "what with no adjustments":
    a Statcast or age tilt must survive into the counterfactual."""
    war, inj, sc = 4.0, 0.70, 0.90
    healthy = es._apply_war_tilt(war, sc)          # injury dropped, statcast kept
    none_at_all = es._apply_war_tilt(war, 1.0)
    assert healthy < none_at_all
    assert healthy > es._apply_war_tilt(war, inj * sc)


def test_healthy_tilt_is_sign_safe_on_a_negative_projection():
    """_apply_war_tilt divides below zero so a penalty always moves DOWN;
    the counterfactual has to inherit that or a fringe arm inverts."""
    war, inj = -1.0, 0.70
    assert es._apply_war_tilt(war, inj) < war
    assert es._apply_war_tilt(war, 1.0) == war
