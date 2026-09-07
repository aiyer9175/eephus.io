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


# --------------------------------------------------------------------------
# Fantasy, DFS and betting: the SAME data, three different correct answers
# --------------------------------------------------------------------------

def test_fantasy_flags_off_roster_players_and_never_drops_them():
    """A rest-of-season board is where you most need to see that your man is out.

    Removing him here would be the bug, which is why fantasy takes the opposite
    treatment from the lineup charts on the same underlying fact.
    """
    d = _load("fantasy.json")
    rs = d.get("roster_status") or {}
    if not rs.get("applied"):
        pytest.skip("roster walk unavailable on this build")
    rows = d.get("players") or []
    off = [r for r in rows if r.get("roster_status") == "off_roster"]
    assert off, "no player is flagged off_roster; the flag is not being written"
    assert len(off) == rs["n_off_roster"]
    assert all(r.get("roster_status") in ("active", "off_roster", "unknown")
               for r in rows)
    assert "NEVER FILTERED" in rs["policy"]


def test_dfs_removes_off_roster_players_from_the_draftable_pool():
    """A DFS pool is who you can draft tonight. An off-roster player cannot score."""
    d = _load("dfs.json")
    rf = d.get("roster_filter") or {}
    if not rf.get("applied"):
        pytest.skip("roster walk unavailable on this build")
    assert rf["n_removed"] >= 0
    assert isinstance(d.get("off_roster"), list), (
        "removed players are not ledgered; a silent drop is how a pool shrinks "
        "without anyone noticing")
    ledger_ids = {r.get("mlbam") for r in d["off_roster"]}
    served = {r.get("mlbam") for r in d.get("players") or []}
    assert not (ledger_ids & served), "a player is both removed and served"


def test_the_two_policies_are_deliberately_opposite_and_say_so():
    fan = (_load("fantasy.json").get("roster_status") or {}).get("policy", "")
    dfs = (_load("dfs.json").get("roster_filter") or {}).get("policy", "")
    if not fan or not dfs:
        pytest.skip("policy blocks absent on this build")
    assert "FLAGGED" in fan and "FILTERED" in dfs
    # each names the other, so a reader hitting one is told why the other differs
    assert "lineup" in fan.lower() or "tonight" in fan.lower()
    assert "fantasy" in dfs.lower()


def test_no_prop_is_priced_for_an_off_roster_player():
    """You cannot bet a hits line on someone who is not on the roster tonight."""
    import betting_export as bx
    src = Path(bx.__file__).read_text(encoding="utf-8")
    i = src.index("def _fantasy_index(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert 'roster_status' in body and 'off_roster' in body, (
        "the props index no longer skips off-roster projections, so a prop can be "
        "priced for a player who cannot play")
    assert '"unknown"' in body or "unknown" in body, (
        "a failed roster walk must KEEP players rather than emptying the props board")


def test_the_daily_path_re_stamps_roster_status():
    """"Daily" is the whole requirement, and refresh_live reuses monthly players.

    fantasy_export.refresh_live deliberately skips the projection rebuild, which
    is what makes it cheap enough to run nightly. Roster status is the one field
    on those reused rows that goes stale in HOURS, so without an explicit
    re-stamp the flag would only refresh on the monthly build: a player who hit
    the IL on the 3rd would read "active" until the 1st of the next month, which
    is exactly the staleness the flag exists to remove.
    """
    import fantasy_export as fx
    src = Path(fx.__file__).read_text(encoding="utf-8")
    i = src.index("def refresh_live(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "roster_status" in body and "_active_roster_ids" in body, (
        "the daily refresh no longer re-stamps roster status, so the flag is only "
        "as fresh as the last monthly build")
    d = _load("fantasy.json")
    rs = d.get("roster_status") or {}
    if rs.get("applied"):
        assert rs.get("refreshed") == "daily"


def test_every_roster_aware_surface_is_on_the_nightly_path():
    """A one-off fix is not what "updated daily" means.

    run_monthly --daily is what deploy/nightly-build.sh runs most nights. All
    five surfaces have to be reached by it, or the roster data is only as fresh
    as the last monthly.
    """
    src = (HERE / "run_monthly.py").read_text(encoding="utf-8")
    for name in ("bullpen_export", "starter_export", "hitter_export",
                 "fantasy_export", "dfs_export"):
        assert name in src, f"{name} is not reached by run_monthly at all"
    # the daily leaderboard block that rebuilds the three team boards
    assert "daily leaderboards" in src
    assert "refresh_live" in src and "dfs_export" in src
