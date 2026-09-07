# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A constructed lineup is a claim about tonight, so it cannot contain injured players.

REPORTED, then measured: Nick Kurtz was batting SECOND for the Athletics while out
for the season. hem_plus.team_offense built the order from
`[h for h in hitters if h.hem_plus is not None and h.pa > 0]` -- every hitter with a
plate appearance this year, no roster filter, no IL check. Kurtz has 434 PA, so he
ranked, and he was in the nine.

Against the live active rosters, before the fix:

    hitter constructed lineups   37 of 270 slots  13.7%
    hitter bench                 66 of 180        36.7%
    starter rotation charts      78 of 226        34.5%
    bullpen depth                 9 of 238         3.8%   <- already filtered

The bullpen number is the control: that path has had the filter all along and its
residual is roster drift since the last build. The machinery existed; the hitter and
starter charts were never wired to it.

WHAT IS FILTERED AND WHAT IS NOT. The constructed `orders`, `lineup`, `bench` and
`rotation` take the active roster. Offense+, Rotation+ and every other aggregate do
NOT: a player's HEM+ over the plate appearances he actually took is real whether or
not he is hurt today, and those aggregates feed betting_model and the leaderboard
vintages the 600-game clock is accruing against, so re-basing them would be a model
change wearing a display fix's clothes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DATA = HERE / "data"


def _load(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def _active_ids(payload):
    rf = payload.get("roster_filter") or {}
    if not rf.get("applied"):
        pytest.skip("roster filter was not applied on this build (feed unavailable)")
    return rf


def test_the_hitter_board_publishes_what_the_filter_did():
    rf = _active_ids(_load("hitter_leaderboards.json"))
    assert rf["n_active_roster_ids"] and rf["n_active_roster_ids"] > 700
    assert rf["n_dropped_from_constructions"] >= 0
    assert "aggregate" in rf["scope"] or "Offense+" in rf["scope"], (
        "the disclosure no longer says the aggregates are unfiltered, which is the "
        "one thing a reader has to know to interpret Offense+")


def test_the_starter_board_publishes_what_the_filter_did():
    rf = _active_ids(_load("starter_leaderboards.json"))
    assert rf["n_active_roster_ids"] and rf["n_active_roster_ids"] > 700


def test_a_failed_roster_walk_filters_nothing():
    """The failure mode must be an unfiltered chart, never an empty one."""
    import hem_plus, sem_plus
    h = hem_plus.Hitter(key="1", name="A", team="ATH", mlbam=1, pa=400.0)
    h.hem_plus = 120.0
    out = hem_plus.team_offense("ATH", [h], None)          # None == feed failed
    assert out.get("lineup"), "a failed roster feed emptied the lineup"
    assert out.get("n_off_roster_dropped", 0) == 0


def test_an_unreadable_player_id_is_kept_never_dropped():
    """Over-filtering is the worse error: it removes a real player silently."""
    import hem_plus
    h = hem_plus.Hitter(key="x", name="No Id", team="ATH", mlbam=None, pa=400.0)
    h.hem_plus = 120.0
    out = hem_plus.team_offense("ATH", [h], frozenset({999}))
    assert out.get("lineup"), "a hitter with no mlbam was dropped by the roster filter"


def test_an_empty_result_falls_back_rather_than_serving_no_lineup():
    """If nothing matches, show the unfiltered nine and say so.

    A club mid-teardown, or a roster set that came back for other clubs but not
    this one, must not produce a card with no players on it.
    """
    import hem_plus
    h = hem_plus.Hitter(key="2", name="B", team="ATH", mlbam=2, pa=400.0)
    h.hem_plus = 120.0
    out = hem_plus.team_offense("ATH", [h], frozenset({999999}))
    assert out.get("lineup"), "every bat was filtered and the card went empty"
    assert out.get("roster_filter_skipped")


def test_the_aggregates_are_not_filtered():
    """Offense+ must be identical with and without the roster filter."""
    import hem_plus
    hs = []
    for i, (pa, hem) in enumerate(((400.0, 130.0), (350.0, 90.0)), start=1):
        h = hem_plus.Hitter(key=str(i), name=f"P{i}", team="ATH", mlbam=i, pa=pa)
        h.hem_plus = hem
        hs.append(h)
    full = hem_plus.team_offense("ATH", hs, None)
    filt = hem_plus.team_offense("ATH", hs, frozenset({1}))     # drops player 2
    assert full["offense_plus"] == filt["offense_plus"], (
        "the roster filter moved Offense+, which feeds betting_model and the "
        "600-game validation clock; only the CONSTRUCTED objects may change")
    assert full["team_pa"] == filt["team_pa"]
    assert filt["n_off_roster_dropped"] == 1


def test_a_partial_roster_walk_refuses_to_filter():
    """One club answering is not a roster set.

    The old guard returned as soon as a single club came back, so five failed
    fetches produced a set missing five rosters and every caller then dropped
    those clubs' players as off-roster: the board does not go blank, it goes
    wrong, on exactly the clubs whose feed failed.
    """
    import bullpen_export as be
    assert be.MIN_CLUBS_FOR_ROSTER_FILTER >= 28
    src = Path(be.__file__).read_text(encoding="utf-8")
    assert "n_clubs_ok" in src and "any_ok" not in src, (
        "the single-club guard is back")
