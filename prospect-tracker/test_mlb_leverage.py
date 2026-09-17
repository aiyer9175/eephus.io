# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for mlb_leverage.accumulate (the pure winProbability fold).

No network: synthetic plays exercise the home/away WPA sign flip, gmLI entry
detection, the SD/MD per-appearance thresholds, WPA/LI, and the leadoff-play
leverage-missing fallback.
"""
from __future__ import annotations

import mlb_leverage as ml


def _play(pid, half, inning, li, added, name="P"):
    return {"about": {"halfInning": half, "inning": inning},
            "matchup": {"pitcher": {"id": pid, "fullName": name}},
            "leverageIndex": li, "homeTeamWinProbabilityAdded": added}


def test_accumulate_core_metrics():
    game1 = [
        _play(100, "top", 8, 2.0, 3.0, "One"),      # home pitcher, enters at LI 2.0
        _play(100, "top", 8, 1.5, 2.0, "One"),
        _play(200, "bottom", 9, 1.8, -5.0, "Two"),  # away pitcher: sign flips -> +0.05
        _play(300, "top", 9, 1.0, -8.0, "Three"),   # home pitcher meltdown -> -0.08
    ]
    game2 = [
        _play(100, "top", 9, 2.5, 7.0, "One"),       # +0.07 -> a shutdown appearance
    ]
    out = ml.accumulate([(1, game1), (2, game2)])

    one = out[100]
    assert one["gmli"] == 2.25                        # mean entry LI (2.0, 2.5)
    assert round(one["wpa"], 3) == 0.12               # 0.05 + 0.07
    assert one["sd"] == 1 and one["md"] == 0          # only game2 clears +0.06
    assert one["appearances"] == 2
    assert one["entry_inning"] == 8.5                 # median of innings 8, 9
    assert round(one["wpa_li"], 3) == 0.056           # 0.03/2 + 0.02/1.5 + 0.07/2.5

    two = out[200]
    assert round(two["wpa"], 3) == 0.05               # away sign flip of -5.0
    assert two["gmli"] == 1.8

    three = out[300]
    assert round(three["wpa"], 3) == -0.08
    assert three["md"] == 1 and three["sd"] == 0


def test_entry_li_falls_back_when_leadoff_missing():
    # first play for pid 400 has no leverageIndex (leadoff PA); the next does
    game = [
        {"about": {"halfInning": "top", "inning": 7},
         "matchup": {"pitcher": {"id": 400, "fullName": "Four"}},
         "leverageIndex": None, "homeTeamWinProbabilityAdded": 1.0},
        _play(400, "top", 7, 1.3, 2.0, "Four"),
    ]
    out = ml.accumulate([(1, game)])
    assert out[400]["gmli"] == 1.3                     # took the next available LI


def test_start_games_excluded_from_relief_fold():
    # pid 500 STARTS game1 (first appearance in the 1st inning, a big +WPA that
    # would clear the SD threshold) and RELIEVES game2 (enters inning 8). The
    # start must not pollute relief gmLI / SD-MD / WPA / appearances.
    game1 = [
        _play(500, "top", 1, 0.9, 8.0, "Swing"),     # inning-1 entry => a start
        _play(500, "top", 2, 0.8, 2.0, "Swing"),
    ]
    game2 = [
        _play(500, "top", 8, 2.2, 3.0, "Swing"),     # true relief entry, +0.03
    ]
    out = ml.accumulate([(1, game1), (2, game2)])
    sw = out[500]
    assert sw["appearances"] == 1                      # only the relief game counts
    assert sw["gmli"] == 2.2                            # inning-8 entry LI only
    assert round(sw["wpa"], 3) == 0.03                  # only the relief WPA
    assert sw["sd"] == 0 and sw["md"] == 0             # the start's +0.10 is excluded
    assert sw["entry_inning"] == 8


def test_plays_of_handles_list_and_dict():
    assert ml._plays_of([{"a": 1}]) == [{"a": 1}]
    assert ml._plays_of({"winProbability": [{"a": 1}]}) == [{"a": 1}]
    assert ml._plays_of(None) == []


# ---- batter + starter folds (S-1 Leverage Leaderboards) --------------------- #
def _bplay(bid, half, inning, li, added, name="B"):
    # one PA: a pitcher (id 99) plus the batter under test. halfInning fixes who
    # is home -- batter bats in the half opposite the fielding (pitching) team.
    return {"about": {"halfInning": half, "inning": inning},
            "matchup": {"pitcher": {"id": 99, "fullName": "P"},
                        "batter": {"id": bid, "fullName": name}},
            "leverageIndex": li, "homeTeamWinProbabilityAdded": added}


def test_batter_fold_wpa_sign_pli_and_clutch():
    # 900 is an AWAY batter (top half): his WPA is the negation of the home WPA
    # the play records. 901 is a HOME batter (bottom half): same home WPA number
    # flips the OTHER way -- the sign-mirror the fold has to get right.
    games = [(1, [
        _bplay(900, "top", 8, 2.0, 4.0, "Away"),      # home WPA +0.04 -> batter -0.04
        _bplay(900, "top", 9, 1.0, -6.0, "Away"),     # home WPA -0.06 -> batter +0.06
        _bplay(901, "bottom", 9, 1.8, 9.0, "Home"),   # home WPA +0.09 -> batter +0.09
    ])]
    out = ml.accumulate_batters(games)

    a = out[900]
    assert a["pa"] == 2
    assert a["wpa"] == 0.02                            # -0.04 + 0.06
    assert a["pli"] == 1.5                             # mean LI faced (2.0, 1.0)
    assert a["wpa_li"] == 0.04                         # -0.04/2.0 + 0.06/1.0
    # Clutch = WPA/pLI - WPA/LI = 0.02/1.5 - 0.04
    assert a["clutch"] == -0.027

    h = out[901]
    assert h["wpa"] == 0.09                            # home batter: opposite sign of an away batter
    assert h["pli"] == 1.8
    assert h["clutch"] == 0.0                          # 0.09/1.8 - 0.09/1.8


def test_starter_fold_keeps_only_starts_and_averages_per_start():
    # 500 STARTS game1 + game3 (first appearance in the 1st inning) and RELIEVES
    # game2 (enters inning 8). Only the two starts count; the relief game is the
    # reliever board's, not this one -- the mirror of the reliever exclusion test.
    game1 = [
        _play(500, "top", 1, 0.9, 8.0, "Ace"),        # start: home pitcher, +0.08
        _play(500, "top", 2, 0.8, 2.0, "Ace"),        # +0.02  (wpa_li 0.08/0.9 + 0.02/0.8)
    ]
    game2 = [
        _play(500, "top", 8, 2.2, 3.0, "Ace"),        # relief entry -> excluded from starts
    ]
    game3 = [
        _play(500, "bottom", 1, 1.0, 5.0, "Ace"),     # start: away pitcher, home WPA +0.05 -> -0.05
    ]
    out = ml.accumulate_starters([(1, game1), (2, game2), (3, game3)])
    a = out[500]
    assert a["starts"] == 2                            # game2 (relief) excluded
    assert a["wpa"] == 0.05                            # 0.10 + (-0.05)
    assert a["wpa_per_start"] == 0.025                 # 0.05 / 2
    assert a["wpa_li"] == 0.064                        # (0.08/0.9 + 0.02/0.8) + (-0.05/1.0)


# ---- yearly history export (leverage_history.json) -------------------------- #
def test_export_history_keeps_only_qualified_per_season(monkeypatch):
    """export_history folds each season off the (stubbed) cached feed and stores
    only qualified batters/starters, one block per season. No network."""
    import leverage_export as lev

    def fake_fetch(season, **kw):
        bat = {
            10: {"name": "Reg Ular", "pa": 300, "wpa": 2.0, "pli": 1.1, "clutch": 0.3, "wpa_li": 1.8},
            11: {"name": "Thin Bat", "pa": 100, "wpa": 0.4, "pli": 1.0, "clutch": 0.0, "wpa_li": 0.4},
        }
        strt = {
            20: {"name": "Ace", "starts": 12, "wpa": 1.5, "wpa_per_start": 0.125, "wpa_li": 1.1},
            21: {"name": "Spot", "starts": 3, "wpa": 0.1, "wpa_per_start": 0.033, "wpa_li": 0.1},
        }
        return {}, bat, strt, {"games": 2430, "games_total": 2430}

    # No network: the eWAR join (E3) reads the shared side map, which falls back
    # to a Baseball-Reference pull on a cold cache. An empty map keeps this test
    # on disk and leaves every row's `war` absent, which is what it asserts.
    import bullpen_export
    monkeypatch.setattr(bullpen_export, "_side_war_by_season", dict)

    monkeypatch.setattr(lev.mlb_leverage, "fetch_season_all_leverage", fake_fetch)
    monkeypatch.setattr(lev, "load_season_hitting", lambda y: [
        {"mlbam": 10, "name": "Reg Ular", "team": "NYY"},
        {"mlbam": 11, "name": "Thin Bat", "team": "BOS"}])
    monkeypatch.setattr(lev, "load_season_pitching", lambda y: [
        {"mlbam": 20, "name": "Ace", "team": "NYY", "GS": 12},
        {"mlbam": 21, "name": "Spot", "team": "BOS", "GS": 3}])

    payload = lev.export_history([2024, 2025], write=False, log=lambda *a: None)

    assert payload["seasons"] == [2024, 2025]
    assert set(payload["history"].keys()) == {"2024", "2025"}
    yr = payload["history"]["2025"]
    assert yr["season"] == 2025
    # qualified-only: the 300-PA regular is kept, the 100-PA bat is dropped
    assert [b["name"] for b in yr["batters"]] == ["Reg Ular"]
    assert yr["n_batters"] == 1
    # QUAL_STARTS=5: Ace (12 starts) kept, Spot (3 starts) dropped
    assert [s["name"] for s in yr["starters"]] == ["Ace"]
    assert yr["n_starters"] == 1
    assert yr["coverage"]["games"] == 2430


def test_export_history_skips_a_season_that_fails(monkeypatch):
    """A season whose fold raises is logged and skipped, never aborting the run."""
    import leverage_export as lev

    def fake_fetch(season, **kw):
        if season == 2024:
            raise RuntimeError("boom")
        bat = {10: {"name": "Reg", "pa": 300, "wpa": 1.0, "pli": 1.0, "clutch": 0.0, "wpa_li": 1.0}}
        return {}, bat, {}, {"games": 1, "games_total": 1}

    # No network: the eWAR join (E3) reads the shared side map, which falls back
    # to a Baseball-Reference pull on a cold cache. An empty map keeps this test
    # on disk and leaves every row's `war` absent, which is what it asserts.
    import bullpen_export
    monkeypatch.setattr(bullpen_export, "_side_war_by_season", dict)

    monkeypatch.setattr(lev.mlb_leverage, "fetch_season_all_leverage", fake_fetch)
    monkeypatch.setattr(lev, "load_season_hitting", lambda y: [{"mlbam": 10, "name": "Reg", "team": "NYY"}])
    monkeypatch.setattr(lev, "load_season_pitching", lambda y: [])

    payload = lev.export_history([2024, 2025], write=False, log=lambda *a: None)
    assert payload["seasons"] == [2025]                # 2024 skipped, run survives
    assert "2024" not in payload["history"]


# ---------------------------------------------------------------------------
# Leverage board team fallback (2026-07-31)
# ---------------------------------------------------------------------------

def test_batter_team_falls_back_to_the_pitcher_map():
    """The leverage fold walks the winProbability feed and sees anyone with a
    single plate appearance, while the hitting/pitching name-team maps carry
    their own row thresholds. So a batter can be in the fold and absent from the
    hitting rows, which served exactly one null-team row on the live board."""
    import leverage_export as L
    bat = {1: {"name": "Two Way", "pa": 1, "wpa": 0.0},
           2: {"name": "Regular", "pa": 300, "wpa": 1.0}}
    rows = L._build_batters(bat, {2: ("Regular", "NYY")}, {1: ("Two Way", "TB")})
    by = {r["mlbam"]: r for r in rows}
    assert by[2]["team"] == "NYY", "hitting map must still win"
    assert by[1]["team"] == "TB", "pitcher map must cover the fold-only batter"


def test_batter_team_stays_null_rather_than_invented():
    """A player in neither map keeps his name and a null team. Guessing a team
    would be worse than admitting we do not have one."""
    import leverage_export as L
    rows = L._build_batters({9: {"name": "Ghost", "pa": 1, "wpa": 0.0}}, {}, {})
    assert rows[0]["name"] == "Ghost"
    assert rows[0]["team"] is None


def test_build_batters_still_works_without_the_pitcher_map():
    """The parameter is optional so existing callers are unaffected."""
    import leverage_export as L
    rows = L._build_batters({1: {"name": "A", "pa": 5, "wpa": 0.1}}, {1: ("A", "SEA")})
    assert rows[0]["team"] == "SEA"
