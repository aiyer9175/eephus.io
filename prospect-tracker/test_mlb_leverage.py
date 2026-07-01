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


def test_plays_of_handles_list_and_dict():
    assert ml._plays_of([{"a": 1}]) == [{"a": 1}]
    assert ml._plays_of({"winProbability": [{"a": 1}]}) == [{"a": 1}]
    assert ml._plays_of(None) == []
