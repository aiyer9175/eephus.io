"""C-6: a published eFV-minus-consensus delta must be a real comparison.

Gate: docs/efv-2026-08-13/CONSENSUS_DELTA_HONESTY_GATE.md.

The board-wide "eFV is deflated across the board" reading was -5.13 FV, of which
76% came from 2,651 rows differenced against the performance_ingest placeholder
constant and a further 35% from 509 rows differenced against the outcome curve's
abstention knot. These pins keep both suppressions, and they assert the CONSEQUENCE
rather than a flag: a pin on a boolean would go green again the moment someone
restored the delta while leaving the boolean set.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import efv_score as E
import value_framework as vf
from efv_export import _entry

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PROSPX = ROOT / "prospx" / "index.html"


def _floor_knot() -> float:
    return float(vf._outcome_curve()["knots"][0])


# ── the shipped predicate ────────────────────────────────────────────────────

def test_a_real_comparison_still_publishes_its_delta():
    """NON-VACUITY. If this fails the other pins prove nothing, because a
    predicate that suppresses everything would satisfy all of them."""
    d, ph, fl = E.consensus_delta(48.3, 45.0, anchor_constant_only=False)
    assert d == 3.3
    assert ph is False and fl is False


def test_placeholder_consensus_publishes_no_delta():
    """consensus.py parks CONSTANT_ANCHOR_SOURCES as 'a placeholder constant, not
    an opinion'. There is nothing to disagree with."""
    d, ph, fl = E.consensus_delta(28.0, 35.0, anchor_constant_only=True)
    assert d is None
    assert ph is True


def test_grade_at_the_abstention_knot_publishes_no_delta():
    """vf.outcome_implied_fv returns ks[0] for EVERY non-positive prediction, so
    the served number is the bottom of the scale rather than a level."""
    d, ph, fl = E.consensus_delta(_floor_knot(), 36.0, anchor_constant_only=False)
    assert d is None
    assert fl is True


def test_a_routed_grade_on_the_same_number_is_not_an_abstention():
    """TWO DIFFERENT 20.0s. efv_ungraded._GRADE_MAP["hit"]["FLOOR"] is also 20.0, so
    a routed row can serve the outcome curve's knot VALUE while the number came from
    the provisional model, where it is a resolved answer rather than an abstention.
    The first version of the predicate marked 275 such rows 'not a resolved level'."""
    from efv_ungraded import _GRADE_MAP
    assert _GRADE_MAP["hit"]["FLOOR"] == _floor_knot(), (
        "the collision this guards is gone; re-read the predicate before deleting")
    _, _, fl = E.consensus_delta(_floor_knot(), 35.0, anchor_constant_only=True,
                                 grade_from_outcome_map=False)
    assert fl is False
    _, _, fl = E.consensus_delta(_floor_knot(), 35.0, anchor_constant_only=True,
                                 grade_from_outcome_map=True)
    assert fl is True


def test_scoping_the_floor_marker_moves_no_delta():
    """The refinement is about the REASON, never the suppression. A routed row is
    constant-anchor by construction, so it stays suppressed either way."""
    for from_map in (True, False):
        d, ph, _ = E.consensus_delta(_floor_knot(), 35.0, anchor_constant_only=True,
                                     grade_from_outcome_map=from_map)
        assert d is None and ph is True


def test_the_knot_is_read_from_the_curve_not_hardcoded():
    """A curve refit that moves the first knot must move this predicate with it,
    or the suppression silently stops matching the map it describes."""
    assert E.consensus_delta(_floor_knot(), 36.0,
                             anchor_constant_only=False)[2] is True
    assert E.consensus_delta(_floor_knot() + 0.2, 36.0,
                             anchor_constant_only=False)[2] is False


def test_the_map_really_does_collapse_the_whole_sub_zero_range():
    """The justification for suppressing at the knot, asserted rather than
    quoted: distinct negative predictions are indistinguishable in the grade."""
    grades = {vf.outcome_implied_fv(w, exposure_seasons=6)
              for w in (-0.86, -0.60, -0.25, -0.001, 0.0)}
    assert grades == {_floor_knot()}


# ── the export seam ──────────────────────────────────────────────────────────

def test_export_carries_the_two_markers():
    """prospx decides whether to render a chip from these. Drop them from the
    export and the page falls back to subtracting the two displayed numbers."""
    s = {"player_key": "p", "xfv_grade": 20.0, "xfv_grade_display": 20.0,
         "consensus_fv": 36.0, "xfv_minus_consensus": None,
         "xfv_minus_consensus_display": -16.0,
         "consensus_is_placeholder": True, "xfv_grade_is_floor": True}
    e = _entry(s, "hit", "active")
    assert e["xfv_minus_consensus"] is None
    assert e["consensus_is_placeholder"] is True
    assert e["xfv_grade_is_floor"] is True


def test_export_markers_default_false_not_missing():
    """A missing key reads as falsy in JS too, but an explicit False keeps the
    artifact schema stable for anything that enumerates fields."""
    s = {"player_key": "p", "xfv_grade": 48.0, "xfv_grade_display": 48.0,
         "consensus_fv": 45.0, "xfv_minus_consensus": 3.0,
         "xfv_minus_consensus_display": 3.0}
    e = _entry(s, "hit", "active")
    assert e["consensus_is_placeholder"] is False
    assert e["xfv_grade_is_floor"] is False


# ── the surface, which is where this change is either real or a no-op ────────

def test_prospx_does_not_re_manufacture_a_suppressed_delta():
    """THE RATCHET THAT MATTERS. Both delta functions had a path that computes
    the number from consensus_fv when the pre-baked field is absent:

        efvMinusConsensus        falls back to efvBoardValue(x) - x.consensus_fv
        efvMinusConsensusDisplay never read the pre-baked field at all

    So suppressing the artifact field alone changed nothing on screen. Each must
    consult the guard BEFORE its own computation."""
    src = PROSPX.read_text(encoding="utf-8")
    assert "function efvComparisonSuppressed(x)" in src
    for fn in ("function efvMinusConsensus(x) {",
               "function efvMinusConsensusDisplay(x) {"):
        i = src.index(fn)
        body = src[i:i + 400]
        assert "efvComparisonSuppressed(x)" in body, f"{fn} does not consult the guard"

    guard = src[src.index("function efvComparisonSuppressed(x)"):][:300]
    assert "consensus_is_placeholder" in guard and "xfv_grade_is_floor" in guard


def test_prospx_discloses_the_floor_rather_than_printing_a_bare_grade():
    src = PROSPX.read_text(encoding="utf-8")
    assert "not a resolved level" in src
    assert "no source grade published" in src


# ── the served artifact, when one is present ─────────────────────────────────

@pytest.mark.parametrize("art", ("xfv_scored_live.json", "xfv_scored_live_pitcher.json"))
def test_served_board_suppresses_exactly_the_two_cohorts(art):
    p = DATA / art
    if not p.exists():
        pytest.skip(f"{art} not built")
    rows = [r for r in json.loads(p.read_text(encoding="utf-8"))
            if r.get("kind") == "active"]
    if not rows:
        pytest.skip("no active rows")
    suppressed = [r for r in rows if r.get("xfv_minus_consensus") is None]
    marked = [r for r in rows
              if r.get("consensus_is_placeholder") or r.get("xfv_grade_is_floor")]
    assert {r["player_key"] for r in suppressed} == {r["player_key"] for r in marked}
    # and the ones that DO publish are genuine comparisons
    for r in rows:
        if r.get("xfv_minus_consensus") is not None:
            assert not r.get("consensus_is_placeholder")
            assert not r.get("xfv_grade_is_floor")
            assert abs(r["xfv_minus_consensus"]
                       - round(r["xfv_grade"] - r["consensus_fv"], 1)) < 0.051


def test_the_divergence_aggregate_declares_what_it_left_out():
    """`run_live` returns its report rather than persisting one, so this drives
    the block directly. It is the aggregate that carried the -5.13 headline: it
    must now report its own n and split the suppression by reason, because an
    average whose denominator silently changes is how the number misled in the
    first place."""
    scored = [{"xfv_minus_consensus": 3.0},
              {"xfv_minus_consensus": 1.0},
              {"xfv_minus_consensus": None, "consensus_is_placeholder": True},
              {"xfv_minus_consensus": None, "xfv_grade_is_floor": True}]
    blk = E._divergence_block(scored)
    assert blk["n_compared"] == 2
    assert blk["n_suppressed"] == 2
    assert blk["n_suppressed_placeholder_consensus"] == 1
    assert blk["n_suppressed_grade_at_floor"] == 1
    assert blk["mean_signed_delta"] == 2.0          # not (3+1+0+0)/4
    assert blk["n_compared"] + blk["n_suppressed"] == len(scored)


def test_the_divergence_aggregate_survives_a_fully_suppressed_side():
    """An all-suppressed pool must report None rather than divide by zero."""
    blk = E._divergence_block([{"xfv_minus_consensus": None,
                                "consensus_is_placeholder": True}])
    assert blk["n_compared"] == 0
    assert blk["mean_signed_delta"] is None
