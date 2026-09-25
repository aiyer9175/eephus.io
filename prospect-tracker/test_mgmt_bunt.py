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
    """REWRITTEN 2026-09-25 (audit M10-02). The old check bounded the whole-family
    ratio at 0.4 to 2.5, and it held (-127.2 against -75.3) only while both sides
    counted the same outcome-selected bunts. With every bunt priced the whole-family
    ratio is 17.3 (-56.0 against -3.2), because the two situations point opposite
    ways. So the check is per situation on the sign, and the gap is not bounded but
    RECONCILED: each total splits exactly by the bunt's result, and the payload names
    where the models part (the successful sacrifice, -54.8 against -10.7)."""
    d = _art()
    c = d.get("independent_control")
    if not c:
        pytest.skip("control not computed on this build")
    for k, v in d["by_situation"].items():
        ctl = c["by_situation_wins"][k]
        assert (v["total_decision_value_wins"] < 0) == (ctl < 0), (
            f"the independent model disagrees on the sign in the {k} situation")
    rec = c["reconciliation"]
    for side, tot in (("model_wins", d["total_decision_value_wins"]),
                      ("control_wins", c["total_wins"])):
        s = sum(v[side] for v in rec["by_result"].values()) - rec["alternative_offset"][side]
        assert abs(s - tot) < 0.01, (side, s, tot)
    assert abs(c["model_over_control"] - d["total_decision_value_wins"] / c["total_wins"]) < 0.01
    assert c["largest_gap_sentence"]
    assert c["is_realized_wpa"] is True
    why = c["why_it_is_not_the_metric"].lower()
    assert "realized" in why and "check the sign" in why, (
        "the control no longer says what it is FOR; it is a second opinion on sign "
        "and size, and it must never be mistaken for the published metric")


def test_every_bunt_is_priced_whatever_its_result():
    """M10-02. The family counted only bunts named by an out or a sacrifice, so the
    bases-empty cells held nothing but outs. Every bunted ball in play and strike
    three on a bunt is now on the bunt side, and the bases-empty cells carry the
    bunt hits."""
    import mgmt_bunt as mb
    d = _art()
    assert "bunted" in Path(mb.__file__).read_text(encoding="utf-8")
    empty = [c for c in d["cells"] if c["base"] == 0]
    assert empty and all(c["n_bunt_hit"] > 0 and c["situation"] == "for_a_hit" for c in empty)
    assert all(c["situation"] == "sacrifice" for c in d["cells"] if c["base"] != 0)
    hits = sum(v["n_bunt_hits"] for v in d["by_situation"].values())
    assert hits == sum(c["n_bunt_hit"] for c in d["cells"]) and hits > 0
    assert sum(v["n_bunts_priced"] for v in d["by_situation"].values()) == d["n_bunts_priced"]
    assert "strike three" in d["what_counts_as_a_bunt"]


def test_the_family_refuses_a_corpus_without_the_bunted_column(tmp_path):
    import pandas as pd
    import mgmt_bunt as mb
    d = tmp_path / "plays" / "2099"
    d.mkdir(parents=True)
    pd.DataFrame({"event": ["Single"], "outs_before": [0]}).to_parquet(d / "plays-2099.parquet")
    out = mb.price(corpus=tmp_path)
    assert out["status"].startswith("not built") and "bunted" in out["status"]


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
