"""A-CLAIM-7: the served-versus-evaluated census.

WHAT IT SETTLES. "eFV ties the consensus on ordering" has been published without
anyone being able to check WHICH ordering. Four different objects are in play: the
predicted six-year WAR the accuracy cells score, the sort key the board bakes its
ranks from, the quantile grade a reader sees, and the pure-model grade. This
census measures the distance between them and the evaluated object, in discordant
pairs rather than correlation, because these fields are tie-heavy and a low rho
against a coarse scale is mostly granularity rather than disagreement.

THE FINDING, 2026-09-06. The ORDER is fine: the sort key inverts against the
evaluated object on 3.3% of untied hitter pairs and 3.9% of pitcher pairs. The
flagship grade map is EXACTLY monotone, zero inversions over roughly 880,000
untied pairs across both sides. The provisional map, served to 51% of hitters and
58% of pitchers, inverts on 25.4% and 48.8%; half is what independence looks
like. Every provisional row carries consensus FV exactly 35.0, so this basis is
the same no-published-opinion population A-CLAIM-12 counts, reached from the
other direction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_tilt_census as tc          # noqa: E402

ART = ROOT / "data" / "xfv_tilt_census.json"


@pytest.fixture(scope="module")
def cen():
    if not ART.exists():
        pytest.skip("data/xfv_tilt_census.json has not been built")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The statistic itself
# --------------------------------------------------------------------------

def test_discordance_is_zero_for_a_monotone_map():
    a = [1, 2, 3, 4, 5]
    b = [10.0, 20.0, 30.0, 40.0, 50.0]
    conc, disc, tied = tc.discordance(a, b)
    assert disc == 0 and conc == 10 and tied == 0


def test_discordance_is_total_for_a_reversed_map():
    a = [1, 2, 3, 4, 5]
    b = [50.0, 40.0, 30.0, 20.0, 10.0]
    conc, disc, tied = tc.discordance(a, b)
    assert conc == 0 and disc == 10


def test_ties_are_excluded_and_never_counted_as_disagreement():
    """The whole reason this census uses discordant pairs. Rounding to a coarse
    grade scale creates ties, and a tie is not an inversion."""
    a = [1, 1, 1, 1]            # every pair tied in the served field
    b = [4.0, 3.0, 2.0, 1.0]
    conc, disc, tied = tc.discordance(a, b)
    assert (conc, disc) == (0, 0)
    assert tied == 6


def test_a_coarse_but_monotone_map_reports_no_inversions():
    """A grade rounded to a 5-point scale: many ties, zero inversions. If this
    ever reported disagreement the census would be measuring granularity."""
    b = [float(i) for i in range(40)]
    a = [round(x / 5.0) * 5 for x in b]
    conc, disc, tied = tc.discordance(a, b)
    assert disc == 0, "rounding produced inversions, which is impossible"
    assert tied > 0 and conc > 0


def test_spearman_and_discordance_disagree_on_tie_heavy_input():
    """The reason both are published and the discordance is the one to read."""
    b = [float(i) for i in range(60)]
    a = [round(x / 20.0) for x in b]      # three distinct values, heavy ties
    rho = tc.spearman(a, b)
    _c, disc, _t = tc.discordance(a, b)
    assert disc == 0, "a monotone coarsening inverted nothing"
    assert rho is not None and rho < 0.99, (
        "rho was not attenuated by the ties, so this fixture does not "
        "demonstrate the problem the census exists to avoid")


# --------------------------------------------------------------------------
# The artifact
# --------------------------------------------------------------------------

def test_the_census_declares_that_it_moves_nothing(cen):
    assert cen["changes_no_served_number"] is True
    assert cen["is_additional_view"] is True


def test_it_names_the_evaluated_object(cen):
    assert cen["evaluated_object"] == "xfv_war_6yr", (
        "the census compares against something other than the object the "
        "accuracy cells score, so its distances answer a different question")


def test_both_sides_are_censused(cen):
    for side in ("H", "P"):
        assert cen["sides"][side]["n"] > 0


def test_pair_counts_are_internally_consistent(cen):
    for side, s in cen["sides"].items():
        for field, cell in s["served_vs_evaluated"].items():
            if "pairs_total" not in cell:
                continue
            n = cell["n"]
            assert cell["pairs_total"] == n * (n - 1) // 2, f"{side}/{field}"
            assert (cell["pairs_untied_in_both"] + cell["pairs_tied"]
                    == cell["pairs_total"]), f"{side}/{field}"
            assert cell["discordant"] <= cell["pairs_untied_in_both"]


def test_basis_counts_sum_to_the_side(cen):
    for side, s in cen["sides"].items():
        assert sum(s["grade_bases"].values()) == s["n"]
        assert sum(v["n"] for v in s["by_grade_basis"].values()) == s["n"]


# --------------------------------------------------------------------------
# The findings, pinned
# --------------------------------------------------------------------------

def test_the_flagship_map_is_exactly_monotone(cen):
    """efv_score.py's docstring claims xfv_grade is monotone in the prediction.
    On the flagship basis that claim is exactly true, and this is the check that
    keeps it true: a refit that broke it would otherwise be invisible."""
    for side, s in cen["sides"].items():
        pooled = s["by_grade_basis"].get("outcome_pooled")
        if not pooled:
            continue
        cell = pooled["grade_vs_evaluated"]
        assert cell["discordant"] == 0, (
            f"{side}: the flagship outcome map inverted {cell['discordant']} of "
            f"{cell['pairs_untied_in_both']} untied pairs against the model's "
            "own predicted WAR. efv_score.py states this map is monotone in the "
            "prediction; it is not, and every claim resting on that sentence "
            "needs re-reading.")


def test_the_board_order_tracks_the_evaluated_object(cen):
    """The sort key is what overall_rank is baked from. If it drifted from the
    evaluated object, the accuracy claim would stop describing the board."""
    for side, s in cen["sides"].items():
        cell = s["served_vs_evaluated"]["board_sort_key"]
        assert cell["spearman_vs_evaluated"] >= 0.95, (
            f"{side}: the board's ordering key correlates with the evaluated "
            f"object at only {cell['spearman_vs_evaluated']}")
        assert cell["discordant_share"] <= 0.10, (
            f"{side}: the ordering key inverts on "
            f"{cell['discordant_share']:.1%} of untied pairs")


def test_the_provisional_basis_is_the_constant_anchor_population(cen):
    """The join to A-CLAIM-12, asserted rather than asserted-in-prose. If a
    provisional row ever carries a real consensus grade, these are two different
    populations and both lanes' readings need revisiting."""
    for side, s in cen["sides"].items():
        prov = s["by_grade_basis"].get("provisional_capped")
        if not prov:
            continue
        assert prov["distinct_consensus_fv"] == 1, (
            f"{side}: provisional rows now carry "
            f"{prov['distinct_consensus_fv']} distinct consensus values; this "
            "basis is no longer identical to the no-published-opinion "
            "population A-CLAIM-12 counts")
        assert prov["consensus_fv_single_value"] == 35.0


def test_the_provisional_grade_divergence_is_recorded(cen):
    """Records the 2026-09-06 state. This is the finding; a silent change to it
    is a change to what more than half the board means."""
    seen = {}
    for side, s in cen["sides"].items():
        prov = s["by_grade_basis"].get("provisional_capped")
        if not prov:
            continue
        seen[side] = prov["grade_vs_evaluated"]["discordant_share"]
        assert prov["share_of_side"] > 0.40, (
            f"{side}: the provisional basis has dropped to "
            f"{prov['share_of_side']:.0%} of the side. If routing genuinely "
            "changed, say so deliberately; the census reading and the "
            "head-to-head's stated reach both depend on this share.")
    assert seen.get("H", 0) > 0.15 and seen.get("P", 0) > 0.35, (
        "the provisional grade now tracks the model's predicted WAR far more "
        f"closely than on 2026-09-06 ({seen}). That would be a real improvement "
        "and it changes the census reading, so confirm it and update this test.")


def test_routing_is_reported_apart_from_the_maps(cen):
    """Two maps can each be monotone and the composite not be. That is routing
    reorder, and folding it into either map would hide it."""
    for side, s in cen["sides"].items():
        r = s["routing"]
        assert r["cross_basis_pairs_untied"] > 0
        assert r["share_of_all_grade_discordance_that_is_cross_basis"] is not None
        assert "different maps" in r["what_this_measures"].lower()


def test_the_reading_says_the_gap_is_in_the_grade(cen):
    r = cen["reading"].lower()
    assert "grade" in r and "ranking" in r
    assert "provisional" in r


def test_census_does_not_write(cen):
    before = ART.read_bytes()
    tc.census()
    assert ART.read_bytes() == before, "census() wrote to the artifact"
