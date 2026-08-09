# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Guards on the arbitration label set.

The rules pinned here are the ones whose violation would be INVISIBLE: a wrong
arb step or a contaminated label does not raise, it just quietly trains a model
on the wrong thing. Every assertion below corresponds to a measurement that has
already caught something real.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import arb_dataset as A
import arb_service as S

ROOT = Path(__file__).parent


# --------------------------------------------------------------------------- #
# Service time and arbitration step
# --------------------------------------------------------------------------- #

def test_service_days_are_days_not_a_decimal_fraction():
    # 5.045 is five years and FORTY-FIVE DAYS. Parsing it as a float loses that
    # and moves players across the Super Two cut.
    assert S.parse_service_token("5.045") == (5, 45)
    assert S.parse_service_token("2.170") == (2, 170)
    # A service year is 172 days, so 172+ cannot appear in the day field.
    assert S.parse_service_token("5.172") is None
    assert S.parse_service_token("not-a-token") is None


@pytest.mark.parametrize("token,expected", [
    ("3.000", 1), ("4.085", 2), ("5.045", 3),
])
def test_three_plus_service_maps_to_the_standard_ladder(token, expected):
    y, d = S.parse_service_token(token)
    assert S.arb_year_from_service(y, d, 2026)["arb_year"] == expected


def test_six_service_years_is_a_free_agent_not_an_arb_four():
    y, d = S.parse_service_token("6.010")
    got = S.arb_year_from_service(y, d, 2026)
    assert got["arb_year"] is None and got["reason"] == "free_agent"


def test_super_two_is_decided_by_the_published_cut():
    cut = S.super_two_cut(2026)
    assert cut is not None
    over = S.arb_year_from_service(2, cut[1] + 20, 2026)
    under = S.arb_year_from_service(2, cut[1] - 20, 2026)
    assert over["arb_year"] == 1 and over["super_two"] is True
    assert under["arb_year"] is None and under["super_two"] is False


def test_an_unknown_super_two_cut_returns_none_not_false():
    # "we cannot say" and "measured not Super Two" are different claims, and a
    # wrong Super Two call shifts the entire raise chain.
    assert S.super_two_cut(1998) is None
    got = S.arb_year_from_service(2, 150, 1998)
    assert got["super_two"] is None
    assert got["reason"] == "super_two_cut_unknown"


def test_super_two_cutoffs_are_marked_unverified():
    # They were entered from recall, not a source document. The flag is what
    # keeps a curated guess from being read as a measurement.
    assert S.SUPER_TWO_VERIFIED is False


# --------------------------------------------------------------------------- #
# Back-propagation
# --------------------------------------------------------------------------- #

def test_backpropagation_walks_the_grid_backwards():
    # Hunter Brown's real Spotrac grid: 2027 ARB 2 means 2026 was ARB 1.
    got = S.backpropagate({2027: "ARB 2", 2028: "ARB 3", 2029: "UFA"},
                          appearance_seasons=set(range(2023, 2030)))
    assert got[2026]["arb_year"] == 1
    assert got[2027]["arb_year"] == 2
    assert 2029 not in got          # UFA is not an arbitration year


def test_super_two_marker_travels_to_every_rung():
    got = S.backpropagate({2027: "ARB 2 (S2)", 2028: "ARB 3 (S2)"},
                          appearance_seasons=set(range(2023, 2030)))
    assert all(v["super_two"] for v in got.values())


def test_a_gap_in_appearances_stops_the_walk():
    # Service does not accrue in a season the player was not in the majors, so
    # the decrement stops rather than guessing through the hole.
    got = S.backpropagate({2028: "ARB 3"}, appearance_seasons={2027, 2028})
    assert 2026 not in got


def test_spotrac_is_inadmissible_before_its_fence():
    """The cached grid is a 2026 snapshot and spotrac.py:376 skips rows with no
    future salary, so back-propagating it to an old season labels only players
    still rostered years later - the elite survivor tail."""
    vote = {"spotrac_backprop": {"arb_year": 3, "super_two": False}}
    assert S.reconcile(vote, season=2026)["arb_year"] == 3
    assert S.reconcile(vote, season=2015)["arb_year"] is None


def test_mlbtr_service_outranks_every_other_source():
    votes = {"mlbtr_service": {"arb_year": 2, "super_two": False},
             "spotrac_backprop": {"arb_year": 3, "super_two": False},
             "debut_heuristic": {"arb_year": 1, "super_two": None}}
    got = S.reconcile(votes, season=2026)
    assert got["arb_year"] == 2
    assert got["arb_year_source"] == "mlbtr_service"
    # The disagreement is RECORDED, not resolved away.
    assert got["agree"] is False
    assert got["votes"]["spotrac_backprop"] == 3


# --------------------------------------------------------------------------- #
# Contamination
# --------------------------------------------------------------------------- #

def _flags(season=2026, mlbam=1, fa_rows=None, span=None, posted=()):
    return A.contamination({"season": season, "mlbam": mlbam, "n_stints": 1},
                           fa_rows=fa_rows, spotrac_span=span or {},
                           posted=set(posted))


def test_a_multiyear_contract_year_is_not_an_arbitration_award():
    f = _flags(fa_rows=[{"class_year": 2024, "years": 5}])
    assert f["multiyear_extension"] is True
    assert f["exclude_reason"] == A.EXCL_EXTENSION


def test_a_one_year_deal_to_avoid_a_hearing_is_KEPT():
    # The settlement IS the award. Excluding it would delete the majority of the
    # label set.
    f = _flags(fa_rows=[{"class_year": 2026, "years": 1}])
    assert f["multiyear_extension"] is False
    assert f["exclude_reason"] is None


def test_a_posted_foreign_free_agent_is_excluded():
    # Jung Hoo Lee / Shota Imanaga: an MLB free-agent contract with zero MLB
    # service, so there is no pre-arb ladder and no arbitration year at all. A
    # naive service proxy reads their salary as an enormous arb award.
    f = _flags(posted=[1])
    assert f["exclude_reason"] == A.EXCL_POSTED_FA


def test_2020_is_never_a_label_year():
    assert _flags(season=2020)["exclude_reason"] == A.EXCL_SEASON_2020


def test_the_max_cut_rule_is_a_definition_not_a_diagnostic():
    """CBA Article VI caps an arbitration cut at 20%, so a ratio below 0.80 is
    not an award - it is a new deal after a non-tender. Ty France 2025 went
    $6,775,000 -> $1,000,000 (ratio 0.15) and sat in the fit pool as an
    arbitration outcome until this rule existed."""
    assert A.MAX_CUT_RATIO == 0.80


# --------------------------------------------------------------------------- #
# The committed audit artifact
# --------------------------------------------------------------------------- #

def _audit():
    p = ROOT / "data" / "arb_panel.json"
    if not p.exists():
        pytest.skip("data/arb_panel.json not built")
    return json.loads(p.read_text("utf-8"))


def test_panel_audit_carries_a_generated_at():
    assert _audit().get("generated_at")


def test_the_post_filter_violation_rate_is_labelled_as_meaningless():
    # It is 0 by construction. Publishing it without that sentence would invite
    # a reader to treat a definitional exclusion as a passing quality gate.
    t = _audit()["audit"]["totals"]
    assert t["post_filter_violation_rate"] == 0.0
    assert "by construction" in t["post_filter_note"]
    assert t["max_cut_removal_rate"] > 0


def test_the_scored_window_is_only_the_ground_truth_seasons():
    """Substitute sources measured 0.66 and 0.70 agreement against MLBTR service
    time, so seasons that depend on them are reported and NOT scored."""
    doc = _audit()
    assert doc["scored_seasons"] == list(A.SCORED_SEASONS)
    assert min(doc["scored_seasons"]) >= 2022
    pairs = doc["audit"]["disagreement"]["by_pair"]
    weak = pairs.get("mlbtr_service|debut_heuristic")
    if weak:
        assert weak["rate"] < 0.95, (
            "if the heuristic ever clears 0.95 the window can widen; until then "
            "the plan's 2011-2026 backtest description stays withdrawn")


def test_super_two_verification_state_is_published():
    assert _audit()["super_two_verified"] is False
