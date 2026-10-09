# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fixture tests for the MiLB pitch-event fetch and census (EFV4_PBP_CENSUS_AND_PILOT_FETCH).
No network: every cache path is redirected to tmp_path and the network reader raises."""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import pytest

import milb_pbp_census as C
import milb_pbp_fetch as F


def _play(ab, batter, pitcher, event, codes, hit=None):
    evs = []
    b = s = 0
    for k, code in enumerate(codes, 1):
        if code in ("B", "*B"):
            b += 1
        elif code in ("C", "S", "W") or (code in ("F", "T") and s < 2):
            s += 1
        ev = {"isPitch": True, "pitchNumber": k, "details": {"call": {"code": code}, "code": code},
              "count": {"balls": b, "strikes": s, "outs": 0}}
        if code in ("X", "D", "E") and hit:
            ev["hitData"] = hit
        evs.append(ev)
    return {"atBatIndex": ab, "about": {"atBatIndex": ab, "inning": 1, "isTopInning": True},
            "result": {"eventType": event},
            "matchup": {"batter": {"id": batter, "fullName": "Name Hidden"},
                        "pitcher": {"id": pitcher, "fullName": "Name Hidden"}},
            "playEvents": evs}


HIT = {"trajectory": "line_drive", "hardness": "hard", "location": "8",
       "coordinates": {"coordX": 120.456, "coordY": 80.1}}
PLAYS = [
    _play(0, 101, 900, "strikeout", ["C", "B", "F", "S"]),
    _play(1, 102, 900, "single", ["B", "X"], HIT),
    _play(2, 103, 900, "walk", ["B", "B", "*B", "B"]),
]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "CACHE_DIR", tmp_path / "efv4_pbp")
    monkeypatch.setattr(F, "FEED_CACHE_DIR", tmp_path / "game_feeds")
    monkeypatch.setattr(F, "CENSUS_PATH", tmp_path / "pbp_census.json")
    monkeypatch.setattr(C, "OUT_PATH", tmp_path / "pbp_census.json")

    def _boom(*a, **k):
        raise AssertionError("network read in a fixture test")
    monkeypatch.setattr(F, "_get_json", _boom)


def test_reduce_plays_rows_and_pre_pitch_count():
    pas, pitches = F.reduce_plays(PLAYS)
    assert [p[:4] for p in pas] == [[0, 101, 900, "strikeout"], [1, 102, 900, "single"],
                                    [2, 103, 900, "walk"]]
    assert len(pitches) == 10
    cols = F.PITCH_COLS
    first_pa = [p for p in pitches if p[0] == 0]
    pre = [(p[cols.index("b0")], p[cols.index("s0")]) for p in first_pa]
    post = [(p[cols.index("b1")], p[cols.index("s1")]) for p in first_pa]
    assert pre == [(0, 0), (0, 1), (1, 1), (1, 2)]
    assert post == [(0, 1), (1, 1), (1, 2), (1, 3)]
    inplay = [p for p in pitches if p[cols.index("code")] == "X"][0]
    assert inplay[cols.index("traj")] == "line_drive"
    assert inplay[cols.index("hard")] == "hard"
    assert inplay[cols.index("loc")] == "8"
    assert inplay[cols.index("x")] == 120.46 and inplay[cols.index("y")] == 80.1


def test_rows_carry_ids_never_names():
    rec = F.game_record({"gamePk": 5, "date": "2016-06-20", "league": 117, "home": 1, "away": 2},
                        11, 2016, PLAYS, "playByPlay")
    blob = json.dumps(rec)
    assert "Name Hidden" not in blob and "fullName" not in blob
    assert "fullName" not in F.PBP_FIELDS


def test_fetch_game_is_resumable_and_reads_feed_cache(tmp_path):
    feed = {"gameData": {"status": {"abstractGameState": "Final", "detailedState": "Final"}},
            "liveData": {"plays": {"allPlays": PLAYS}}}
    F.FEED_CACHE_DIR.mkdir(parents=True)
    (F.FEED_CACHE_DIR / "77.json").write_text(json.dumps(feed), encoding="utf-8")
    g = {"gamePk": 77, "date": "2016-06-20", "league": 117, "home": 1, "away": 2}
    assert F.fetch_game(11, 2016, g) == ("feed_cache", 10)
    assert F.fetch_game(11, 2016, g) == ("cached", -1)
    rec = F.read_gz(F.game_path(11, 2016, 77))
    assert rec["level"] == "AAA" and rec["season"] == 2016 and rec["league"] == 117
    with pytest.raises(AssertionError, match="network"):
        F.fetch_game(11, 2016, {"gamePk": 78, "date": "2016-06-21"})


def test_fetch_window():
    ok, _ = F.fetch_window_open(datetime(2026, 10, 9, 2, 30, tzinfo=timezone.utc))
    assert ok
    ok, why = F.fetch_window_open(datetime(2026, 10, 9, 7, 0, tzinfo=timezone.utc))
    assert not ok and "blackout" in why
    ok, why = F.fetch_window_open(datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc))
    assert not ok and "fetch date" in why
    assert F.MAX_WORKERS <= 4


def test_census_classes_and_fetch_rule():
    full = {"pa": 70, "pitches": 270, "calls": {"B": 100}, "in_play": 40, "traj": 40,
            "coords": 40, "full": True}
    term = {"pa": 70, "pitches": 105, "calls": {"X": 50}, "in_play": 50, "traj": 50,
            "coords": 50, "full": False}
    assert C._klass(C._aggregate([full] * 6), 2000) == "full"
    assert C._klass(C._aggregate([term] * 6), 2000) == "result_only"
    agg = C._aggregate([full] * 2 + [term] * 4)
    assert C._klass(agg, 2000) == "mixed" and agg["full_game_share"] == pytest.approx(1 / 3, abs=1e-4)
    assert C._klass(C._aggregate([]), 0) == "no_games"
    assert 2020 not in C.PROBE_SEASONS and min(C.FETCH_SEASONS) == 2007


def test_game_full_rule_from_cached_record():
    rec = F.game_record({"gamePk": 5}, 12, 2012, PLAYS, "playByPlay")
    st = C._game_stats(rec)
    assert st["pa"] == 3 and st["pitches"] == 10 and st["full"]
    assert st["in_play"] == 1 and st["traj"] == 1 and st["coords"] == 1


def test_plan_orders_core_then_early_then_rest_level_by_level():
    census = {"probe": {"cells": [
        {"sportId": 12, "season": 2016, "fetch": True},
        {"sportId": 11, "season": 2016, "fetch": True},
        {"sportId": 11, "season": 2018, "fetch": True},
        {"sportId": 11, "season": 2024, "fetch": True},
        {"sportId": 11, "season": 2008, "fetch": True},
        {"sportId": 13, "season": 2012, "fetch": False},
        {"sportId": 12, "season": 2010, "fetch": True},
        {"sportId": 11, "season": 2012, "fetch": True},
    ]}}
    assert F.plan_cells(census) == [(11, 2018), (11, 2016), (12, 2016), (11, 2012), (12, 2010),
                                    (11, 2024), (11, 2008)]


def test_mexican_league_excluded_and_no_outcome_columns_read():
    assert 125 in F.EXCLUDED_LEAGUES
    for mod in (F, C):
        src = inspect.getsource(mod).lower()
        for banned in ("war_", "fwar", "debut_year", "prospects.db", "efv_labels", "efv_identity"):
            assert banned not in src, (mod.__name__, banned)


def test_cache_census_counts_full_and_result_only_games():
    full_rec = F.game_record({"gamePk": 1, "league": 117}, 11, 2016, PLAYS, "playByPlay")
    term = [dict(p, playEvents=p["playEvents"][-1:]) for p in PLAYS]
    term_rec = F.game_record({"gamePk": 2, "league": 112}, 11, 2016, term, "playByPlay")
    F._atomic_write_gz(F.game_path(11, 2016, 1), full_rec)
    F._atomic_write_gz(F.game_path(11, 2016, 2), term_rec)
    F._atomic_write_gz(F.CACHE_DIR / "schedule" / "11_2016.v2.json.gz",
                       [{"gamePk": 1}, {"gamePk": 2}, {"gamePk": 3}])
    cells = C.cache_census({(11, 2016)}, log=lambda *_: None)
    assert len(cells) == 1
    c = cells[0]
    assert c["games_cached"] == 2 and c["scheduled_final"] == 3 and not c["complete"]
    assert c["games_full"] == 1 and c["games_result_only"] == 1 and c["fetch_planned"]
    assert c["by_league_games_full"] == {"112": [1, 0], "117": [1, 1]}
