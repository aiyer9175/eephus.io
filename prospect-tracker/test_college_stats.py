# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Offline tests for the NCAA D-I college-stats pipeline (college_stats.py).

The only network parts (HTTP team-map + headless render) are isolated; these
tests exercise the pure parsers/mappers against saved stats.ncaa.org grid
HTML fixtures so they run without a browser or network.
"""

import pathlib

import college_stats as cs

FIX = pathlib.Path(__file__).parent / "test_fixtures"
BATTING = (FIX / "ncaa_batting_alabama.html").read_text(encoding="utf-8")
PITCHING = (FIX / "ncaa_pitching_alabama.html").read_text(encoding="utf-8")


def test_batting_grid_parses_known_hitter():
    roster = cs.parse_team_grids(BATTING, None, 2026)
    assert len(roster) > 20
    neal = roster["brady_neal"]
    assert neal["ncaa_id"] == "9676954"
    b = neal["batting"]
    assert b["is_pitcher"] is False
    assert b["avg"] == 0.328 and b["obp"] == 0.440 and b["slg"] == 0.550
    assert b["ops"] == 0.990 and b["hr"] == 8 and b["ab"] == 180
    # derived rate stats
    assert b["pa"] == 227 and b["bb_pct"] == 14.1 and b["k_pct"] == 18.5
    assert b["iso"] == 0.222


def test_pitching_grid_parses_pitcher():
    roster = cs.parse_team_grids(None, PITCHING, 2026)
    pitchers = [v for v in roster.values()
                if v.get("pitching") and v["pitching"].get("ip")]
    assert pitchers, "expected at least one pitcher with innings"
    p = pitchers[0]["pitching"]
    assert p["is_pitcher"] is True
    assert p["era"] is not None and p["ip"] is not None
    # rate stats are derived from counting lines (vs the TRUE innings, not the
    # rounded display ip) — just assert they're present + sane here.
    if p.get("so"):
        assert p["k_per_9"] is not None and p["k_per_9"] > 0
    assert "whip" in p


def test_two_way_player_gets_both_sides():
    roster = cs.parse_team_grids(BATTING, PITCHING, 2026)
    # The fixture has players appearing in both grids (e.g. position players
    # who pitched). At least one entry should carry both batting + pitching.
    both = [v for v in roster.values() if v.get("batting") and v.get("pitching")]
    assert both


def test_ip_baseball_notation():
    assert round(cs._ip_to_float("12.1"), 3) == round(12 + 1 / 3, 3)
    assert round(cs._ip_to_float("12.2"), 3) == round(12 + 2 / 3, 3)
    assert cs._ip_to_float("12.0") == 12.0
    assert cs._ip_to_float("") is None


def test_school_normalization_conservative():
    # Generic boilerplate is stripped...
    assert cs._norm_school("University of Alabama") == cs._norm_school("Alabama")
    # ...but distinguishing tokens are preserved (must NOT collide).
    assert cs._norm_school("Michigan") != cs._norm_school("Michigan State")
    assert cs._norm_school("Boston College") != cs._norm_school("Boston University")


def test_empty_grid_is_safe():
    assert cs.parse_team_grids(None, None, 2026) == {}
    assert cs._grid_rows("<html><body>no table</body></html>") == ([], [])
