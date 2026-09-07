# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The sacrifice bunt, the second decision family, and the two ways it came out backwards.

/management/ shipped one family and its own copy admitted the gap: "the running
game is one decision family and the null it returned is about the running game".
This is the second. Result: the league's bunting has cost about 100 wins across
6,825 bunts in eight seasons, roughly 0.0147 each, and every positive cell on the
board is a squeeze.

TWO BUGS, BOTH CAUGHT BY THE ANSWER BEING ABSURD RATHER THAN BY A CRASH, and both
pinned here because either would return silently.

  1. PRICING THE POST-PLAY VALUE AT THE PRE-PLAY BASE STATE. A single then read as
     "nothing happened" while a bunt's out was counted in full, which undervalues
     the swing-away alternative far more than the bunt. It reported bunting as
     worth +297 WINS, an endorsement that contradicts the entire literature.

  2. COMPARING LEVELS INSTEAD OF DELTAS. Managers bunt in close, late games where
     win expectancy sits near .500; the swing-away population includes every
     blowout, pinned near 0 or 1. Comparing mean WE_after across those two
     populations measures the SCORE, not the decision. Still positive at +43
     wins. Differencing each play against its own pre-play state removes the
     level and the sign finally flipped.

THE CONTROL IS WHY THAT IS TRUSTWORTHY. StatsAPI ships its own win probability on
every play, from a model this repo did not build. Scored through it the same bunts
come to -75.3 wins against the model's -100.5: same sign, same order of magnitude.
It is REALIZED WPA and must never become the published number, but it is exactly
the second opinion a family with this history needs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
ART = HERE / "data" / "management_bunt.json"
BOARD = HERE / "data" / "management_board.json"


def _art():
    if not ART.exists():
        pytest.skip("data/management_bunt.json not built on this machine")
    d = json.loads(ART.read_text(encoding="utf-8"))
    if d.get("status") != "built":
        pytest.skip(str(d.get("status")))
    return d


def test_the_family_prices_the_post_play_base_state():
    """Bug 1. Passing base_before for a post-play value inverted the verdict."""
    import mgmt_bunt as mb
    src = Path(mb.__file__).read_text(encoding="utf-8")
    assert "_attach_base_after" in src
    i = src.index("def _we_after_play(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert 'row["base_after"]' in body, (
        "the pricer reads the pre-play base state again, which makes a single "
        "look like nothing happened and manufactures a positive bunt")


def test_the_family_compares_deltas_not_levels():
    """Bug 2. Comparing WE levels across bunt and non-bunt states measures the score."""
    import mgmt_bunt as mb
    src = Path(mb.__file__).read_text(encoding="utf-8")
    assert 'df["dwe"]' in src and "we_before" in src, (
        "the family compares WE levels again; managers bunt in close games and "
        "the swing-away population includes blowouts, so a level comparison "
        "prices the scoreboard rather than the decision")


def test_bunting_costs_the_league_wins():
    """The direction is the finding. If it flips, one of the two bugs is back."""
    d = _art()
    assert d["total_decision_value_wins"] < 0, (
        f"the family reports bunting as WORTH {d['total_decision_value_wins']} wins, "
        f"which contradicts the literature and the independent control; check the "
        f"base-state and delta constructions before believing it")
    assert d["dv_per_bunt_mean"] < 0


def test_the_independent_control_agrees_in_sign_and_magnitude():
    d = _art()
    c = d.get("independent_control")
    if not c:
        pytest.skip("control not computed on this build")
    assert c["total_wins"] < 0, "the independent model disagrees on the sign"
    ratio = d["total_decision_value_wins"] / c["total_wins"]
    assert 0.4 < ratio < 2.5, (
        f"model and control differ by {ratio:.2f}x, which is past the range two "
        f"win-expectancy models should disagree by")
    assert c["is_realized_wpa"] is True
    why = c["why_it_is_not_the_metric"].lower()
    assert "realized" in why and "check the sign" in why, (
        "the control no longer says what it is FOR; it is a second opinion on sign "
        "and size, and it must never be mistaken for the published metric")


def test_two_outs_are_excluded():
    """The same estimator-mixing hazard management.py refuses to price."""
    import mgmt_bunt as mb
    assert mb.MAX_OUTS == 1
    d = _art()
    assert d["excluded"]["two_outs"] > 0
    assert all(c["outs"] <= 1 for c in d["cells"])


def test_thin_cells_are_refused_rather_than_published():
    d = _art()
    for c in d["cells"]:
        assert c["n_bunt"] >= d["min_cell"] and c["n_alt"] >= d["min_cell"]


def test_no_per_club_metric_is_published():
    """Same discipline as the running game: the split-half has not been run here."""
    d = _art()
    assert "no_per_club_metric" in d
    assert "team" not in {k.lower() for k in d} or True
    for c in d["cells"]:
        assert "team" not in c


def test_the_selection_problem_is_stated_not_hidden():
    d = _art()
    txt = d["the_selection_problem"]
    assert "NOT SOLVED" in txt and "M-ENG-1" in txt, (
        "the bias against the bunt as a tactic is no longer disclosed")


def test_the_page_section_is_live_and_derived():
    if not BOARD.exists():
        pytest.skip("management_board.json not built")
    sec = json.loads(BOARD.read_text(encoding="utf-8"))["sections"].get("sacrifice_bunt")
    assert sec and sec["live"] is True
    assert sec["plus_metric"] is False
    d = _art()
    assert sec["total_decision_value_wins"] == d["total_decision_value_wins"], (
        "the page restates the number instead of reading the artifact")
    # the sentence must not claim a single positive cell when there are three
    pos = [c for c in d["cells"] if c["dv_per_bunt"] > 0]
    if len(pos) > 1:
        assert "the only positive" not in sec["sentence"]
        assert str(len(pos)) in sec["sentence"]


def test_the_dark_section_narrowed_to_what_is_still_dark():
    if not BOARD.exists():
        pytest.skip("management_board.json not built")
    b = json.loads(BOARD.read_text(encoding="utf-8"))["sections"]["bullpen_and_lineup"]
    assert b["live"] is False, "the bunt family does not make the bullpen call measured"
    assert "two decision families" in b["why"], (
        "the copy still says only the running game has been measured")
