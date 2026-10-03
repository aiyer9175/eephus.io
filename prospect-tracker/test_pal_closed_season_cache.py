# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""The Alchemy Lab's closed-season disk cache (.cache/pal/, bloat finding RU09).

Pins the four promises the cache makes: the live season is never cached, a
schema-stamp mismatch refetches, a failed or empty fetch writes nothing, and a
closed season's payload comes back off disk without the network. Every test
points CLOSED_SEASON_CACHE_DIR at a tmp_path, so the real .cache is untouched.
"""
import io
import json
import sys
import types
from datetime import date

import pytest

import bullpen_export as be
import pal_export

CLOSED = 2000
LIVE = date.today().year


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(be, "CLOSED_SEASON_CACHE_DIR", tmp_path)
    return tmp_path


def test_live_season_is_never_cached(cache_dir):
    assert be.closed_season_cache_write("arsenal", LIVE, [{"a": 1}]) is False
    assert be.closed_season_cache_read("arsenal", LIVE) is None
    assert not list(cache_dir.rglob("*.json"))


def test_closed_season_round_trips_with_nan(cache_dir):
    payload = [{"player_id": 1, "est_woba": float("nan"), "pitch_type": "FF"}]
    assert be.closed_season_cache_write("arsenal", CLOSED, payload) is True
    back = be.closed_season_cache_read("arsenal", CLOSED)
    assert back[0]["player_id"] == 1 and back[0]["pitch_type"] == "FF"
    assert back[0]["est_woba"] != back[0]["est_woba"]     # NaN survives the trip
    assert be._num(back[0]["est_woba"]) is None


def test_stamp_mismatch_refetches(cache_dir):
    p = be.closed_season_cache_path("velo", CLOSED)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"schema": be.CLOSED_SEASON_CACHE_SCHEMA - 1, "kind": "velo",
                             "year": CLOSED, "payload": [{"pitcher": 1}]}), encoding="utf-8")
    assert be.closed_season_cache_read("velo", CLOSED) is None
    # the wrong kind under the right stamp is a miss too
    p.write_text(json.dumps({"schema": be.CLOSED_SEASON_CACHE_SCHEMA, "kind": "arsenal",
                             "year": CLOSED, "payload": [{"pitcher": 1}]}), encoding="utf-8")
    assert be.closed_season_cache_read("velo", CLOSED) is None


def test_empty_payload_is_never_written(cache_dir):
    assert be.closed_season_cache_write("arsenal", CLOSED, []) is False
    assert be.closed_season_cache_write("season_pitching", CLOSED, {}) is False
    assert not list(cache_dir.rglob("*.json"))


def test_failed_season_pitching_fetch_writes_nothing(cache_dir, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(be, "_get_json", boom)
    assert be.load_season_pitching(CLOSED) == []
    assert not list(cache_dir.rglob("*.json"))


def test_season_pitching_reads_a_closed_season_off_disk(cache_dir, monkeypatch):
    raw = {"stats": [{"splits": [{
        "player": {"id": 7, "fullName": "Cached Arm"}, "team": {"id": 1},
        "position": {"abbreviation": "P"},
        "stat": {"gamesPitched": 30, "gamesStarted": 0, "inningsPitched": "40.1",
                 "strikeOuts": 50, "baseOnBalls": 10, "battersFaced": 160}}]}]}
    be.closed_season_cache_write("season_pitching", CLOSED, raw)

    def boom(*a, **k):
        raise AssertionError("the network must not be asked for a cached closed season")
    monkeypatch.setattr(be, "_get_json", boom)
    monkeypatch.setattr(be, "_team_abbrev_map", lambda: {1: "NYY"})
    monkeypatch.setattr(be, "apply_current_team", lambda rows, label="": rows)
    rows = be.load_season_pitching(CLOSED)
    assert [(r["mlbam"], r["team"], r["IP"], r["SO"]) for r in rows] == [(7, "NYY", "40.1", 50)]


def test_live_season_pitching_still_fetches(cache_dir, monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append(params["season"])
        return {"stats": []}
    monkeypatch.setattr(be, "_get_json", fake_get)
    assert be.load_season_pitching(LIVE) == []
    assert calls == [LIVE]
    assert not list(cache_dir.rglob("*.json"))


def test_arsenal_reads_a_closed_season_off_disk(cache_dir, monkeypatch):
    records = [{"player_id": 11, "pitch_type": "SL", "pitch_usage": 40.0,
                "whiff_percent": 35.5, "est_woba": 0.250, "hard_hit_percent": 30.0}]
    be.closed_season_cache_write("arsenal", CLOSED, records)
    stub = types.ModuleType("pybaseball")

    def boom(*a, **k):
        raise AssertionError("Savant must not be asked for a cached closed season")
    stub.statcast_pitcher_arsenal_stats = boom
    stub.statcast_pitcher_pitch_arsenal = boom
    monkeypatch.setitem(sys.modules, "pybaseball", stub)
    pal_export.load_arsenal.cache_clear()
    out = pal_export.load_arsenal(CLOSED)
    pal_export.load_arsenal.cache_clear()
    assert out == {11: [{"pitch": "SL", "usage": 0.4, "whiff": 0.355,
                         "est_woba": 0.25, "hard_hit": 0.3}]}


def test_platoon_reads_a_closed_season_off_disk(cache_dir, monkeypatch):
    raw = {"stats": [{"splits": [
        {"split": {"code": "vl"}, "stat": {"ops": ".700", "battersFaced": 100}},
        {"split": {"code": "vr"}, "stat": {"ops": ".650", "battersFaced": 200}}]}]}
    be.closed_season_cache_write("platoon", CLOSED, raw, name="42")
    import urllib.request as U

    def boom(*a, **k):
        raise AssertionError("StatsAPI must not be asked for a cached closed season")
    monkeypatch.setattr(U, "urlopen", boom)
    assert pal_export._platoon_one((42, CLOSED)) == (42, 0.7, 0.65, 100)


def test_platoon_live_fetch_is_parsed_and_not_cached(cache_dir, monkeypatch):
    raw = {"stats": [{"splits": [
        {"split": {"code": "vl"}, "stat": {"ops": ".800", "battersFaced": 50}},
        {"split": {"code": "vr"}, "stat": {"ops": ".600", "battersFaced": 60}}]}]}
    import urllib.request as U

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(U, "urlopen", lambda req, timeout=20: _Resp(json.dumps(raw).encode()))
    assert pal_export._platoon_one((42, LIVE)) == (42, 0.8, 0.6, 50)
    assert not list(cache_dir.rglob("*.json"))


def test_pal_cache_is_prunable():
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent / "tools"))
    import prune_cache
    assert "pal" in prune_cache.SAFE_CACHES
    assert "pal" not in prune_cache.EXCLUDED
