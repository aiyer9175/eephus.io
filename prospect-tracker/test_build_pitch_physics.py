# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/build_pitch_physics.py on fixture payloads (League Trends plan 5.1).

Rows as expected, a re-run adds nothing, completed seasons byte-identical, the
play corpus untouched, and a pickoff caught stealing counted once as caught
stealing. Every payload here is a fixture written under tmp_path; nothing reads
or writes the real caches.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from tools import build_pitch_physics as B


def _pitch(n, *, pitcher=None, batter=None, ptype="FF", speed=95.1, ivb=16.2,
           hb=-8.5, spin=2350, ext=6.4, zone=5, call="C", launch=None, angle=None):
    ev = {"details": {"call": {"code": call}, "type": {"code": ptype},
                      "isInPlay": call == "X"},
          "pitchData": {"startSpeed": speed, "zone": zone, "extension": ext,
                        "breaks": {"breakVerticalInduced": ivb, "breakHorizontal": hb,
                                   "spinRate": spin}},
          "index": n - 1, "pitchNumber": n, "isPitch": True, "type": "pitch"}
    if pitcher:
        ev["defense"] = {"pitcher": {"id": pitcher}}
    if batter:
        ev["offense"] = {"batter": {"id": batter}}
    if launch is not None:
        ev["hitData"] = {"launchSpeed": launch, "launchAngle": angle}
    return ev


def _play(abi, half, inning, start, batter, pitcher, events, *, home=0, away=0,
          runners=(), event_type="field_out"):
    return {"result": {"type": "atBat", "eventType": event_type,
                       "homeScore": home, "awayScore": away},
            "about": {"atBatIndex": abi, "halfInning": half, "inning": inning,
                      "startTime": start},
            "matchup": {"batter": {"id": batter}, "batSide": {"code": "R"},
                        "pitcher": {"id": pitcher}, "pitchHand": {"code": "L"}},
            "runners": list(runners), "playEvents": events, "atBatIndex": abi}


def _runner(rid, event_type, play_index, *, out=False):
    return {"movement": {"start": "1B", "end": None if out else "2B", "isOut": out},
            "details": {"eventType": event_type, "runner": {"id": rid},
                        "playIndex": play_index}}


def _game(start, *, steals=True, extra_speed=95.1):
    """A two-play game: a top-half strikeout and a bottom-half lineout with the
    steal events on it."""
    p0 = _play(0, "top", 1, start, 101, 201,
               [_pitch(1, speed=extra_speed), _pitch(2, call="S"), _pitch(3, call="S")],
               event_type="strikeout", away=0, home=0)
    runners = []
    if steals:
        runners = [
            _runner(301, "stolen_base_2b", 0),
            # a pickoff caught stealing: two movement entries for one runner
            # event, and the play's own result names it too
            _runner(302, "pickoff_caught_stealing_2b", 1, out=True),
            _runner(302, "pickoff_caught_stealing_2b", 1, out=True),
            _runner(303, "pickoff_1b", 2, out=True),          # a pickoff: not counted
            _runner(304, "pickoff_error_2b", 3),              # not counted
            _runner(305, "caught_stealing_3b", 4, out=True),
        ]
    p1 = _play(1, "bottom", 1, start.replace(":00:", ":05:"), 102, 202,
               [_pitch(1, ptype="SL", speed=86.0, ivb=1.0, hb=5.0, spin=2600, call="B"),
                _pitch(2, ptype="SL", call="X", launch=101.3, angle=14, pitcher=203,
                       batter=104)],
               event_type="lineout", home=2, away=1, runners=runners)
    return [p0, p1]


def _write(wp: Path, pk: int, plays) -> Path:
    wp.mkdir(parents=True, exist_ok=True)
    p = wp / f"{pk}.json"
    p.write_text(json.dumps(plays), encoding="utf-8")
    return p


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tree(d: Path) -> dict:
    return {str(p.relative_to(d)): _digest(p) for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "win_prob", tmp_path / "pbp_physics"


def test_rows_as_expected(dirs):
    wp, od = dirs
    _write(wp, 777001, _game("2025-06-01T23:10:00.000Z"))
    res = B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert res["seasons"][2025]["status"] == "built"
    pit = pd.read_parquet(B.table_path(od, "pitches", 2025))
    gam = pd.read_parquet(B.table_path(od, "games", 2025))
    assert list(pit.columns) == B.PITCH_COLS
    assert list(gam.columns) == B.GAME_COLS
    assert len(pit) == 5
    first = pit.iloc[0]
    assert (int(first.game_pk), int(first.at_bat_index), int(first.pitch_number)) == (777001, 0, 1)
    assert first.half == "top" and int(first.inning) == 1
    assert (int(first.batter), int(first.pitcher)) == (101, 201)
    assert (first.bat_side, first.pitch_hand, first.pitch_type) == ("R", "L", "FF")
    assert first.start_speed == pytest.approx(95.1, abs=1e-4)
    assert first.ivb == pytest.approx(16.2, abs=1e-4)
    assert first.hb == pytest.approx(-8.5, abs=1e-4)
    assert first.spin == pytest.approx(2350)
    assert first.ext == pytest.approx(6.4, abs=1e-4)
    assert int(first.zone) == 5 and first.call_code == "C"
    assert first.start_time == "2025-06-01T23:10:00.000Z"
    assert pd.isna(first.launch_speed)
    # a mid plate appearance change: the pitch's own defense/offense names the players
    last = pit.iloc[-1]
    assert (int(last.pitcher), int(last.batter)) == (203, 104)
    assert last.launch_speed == pytest.approx(101.3, abs=1e-3)
    assert last.launch_angle == pytest.approx(14)
    assert last.half == "bottom"
    g = gam.iloc[0]
    # 23:10 UTC on June 1 is 19:10 on the US Eastern calendar, same date
    assert g.date == "2025-06-01"
    assert (int(g.home_score), int(g.away_score)) == (2, 1)
    assert (int(g.sb), int(g.cs), int(g.pitches)) == (1, 2, 5)
    man = json.loads(B.manifest_path(od).read_text(encoding="utf-8"))
    assert man["covers_through"] == "2025-06-01"
    assert man["seasons"]["2025"]["frozen"] is True
    assert man["seasons"]["2025"]["pitches"] == 5


def test_eastern_calendar_date(dirs):
    wp, od = dirs
    # 02:30 UTC on July 2 is a 10:30 pm Eastern start on July 1
    _write(wp, 777002, _game("2026-07-02T02:30:00.000Z", steals=False))
    B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    gam = pd.read_parquet(B.table_path(od, "games", 2026))
    assert gam.iloc[0].date == "2026-07-01"
    assert (int(gam.iloc[0].sb), int(gam.iloc[0].cs)) == (0, 0)


def test_pickoff_caught_stealing_counted_once():
    plays = _game("2025-06-01T23:10:00.000Z")
    sb, cs = B.steal_counts(plays)
    # stolen_base_2b once; pickoff_caught_stealing_2b (two entries) once and
    # caught_stealing_3b once as caught stealing; pickoff_1b and pickoff_error not
    assert (sb, cs) == (1, 2)
    only = [_play(0, "top", 1, "2025-06-01T23:10:00.000Z", 1, 2, [],
                  event_type="pickoff_caught_stealing_2b",
                  runners=[_runner(9, "pickoff_caught_stealing_2b", 0, out=True),
                           _runner(9, "pickoff_caught_stealing_2b", 0, out=True)])]
    assert B.steal_counts(only) == (0, 1)


def test_rerun_adds_nothing(dirs):
    wp, od = dirs
    _write(wp, 777003, _game("2026-05-01T23:10:00.000Z"))
    _write(wp, 777004, _game("2026-05-02T23:10:00.000Z"))
    first = B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert first["wrote"] and first["seasons"][2026]["added"] == 2
    before = _tree(od)
    mtimes = {p: p.stat().st_mtime_ns for p in od.rglob("*") if p.is_file()}
    again = B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert again["wrote"] is False
    assert again["seasons"][2026]["status"] == "unchanged"
    assert again["seasons"][2026]["added"] == 0
    assert _tree(od) == before
    assert {p: p.stat().st_mtime_ns for p in od.rglob("*") if p.is_file()} == mtimes


def test_live_season_incremental_and_pruned_payload_keeps_rows(dirs):
    wp, od = dirs
    p1 = _write(wp, 777005, _game("2026-05-01T23:10:00.000Z"))
    B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    _write(wp, 777006, _game("2026-05-03T23:10:00.000Z"))
    p1.unlink()                               # the box pruned an old payload
    res = B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert res["seasons"][2026]["added"] == 1
    gam = pd.read_parquet(B.table_path(od, "games", 2026))
    assert list(gam["game_pk"]) == [777005, 777006]
    assert res["covers_through"] == "2026-05-03"
    # a moved payload is re-flattened in place, not duplicated
    _write(wp, 777006, _game("2026-05-03T23:10:00.000Z", extra_speed=99.9))
    os.utime(wp / "777006.json", ns=(1, 1))
    res = B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert res["seasons"][2026]["added"] == 0 and res["seasons"][2026]["reflattened"] == 1
    pit = pd.read_parquet(B.table_path(od, "pitches", 2026))
    assert len(pit) == 10
    assert pit[pit.game_pk == 777006].iloc[0].start_speed == pytest.approx(99.9, abs=1e-3)


def test_completed_season_byte_identical(dirs):
    wp, od = dirs
    _write(wp, 777007, _game("2025-08-01T23:10:00.000Z"))
    _write(wp, 777008, _game("2026-04-01T23:10:00.000Z"))
    B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    frozen = {t: _digest(B.table_path(od, t, 2025)) for t in ("pitches", "games")}
    # a later payload change and a late-arriving game of the completed season
    _write(wp, 777007, _game("2025-08-01T23:10:00.000Z", extra_speed=80.0))
    os.utime(wp / "777007.json", ns=(2, 2))
    _write(wp, 777009, _game("2025-08-02T23:10:00.000Z"))
    _write(wp, 777010, _game("2026-04-02T23:10:00.000Z"))
    res = B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert res["seasons"][2025]["status"] == "frozen"
    assert {t: _digest(B.table_path(od, t, 2025)) for t in ("pitches", "games")} == frozen
    assert res["seasons"][2026]["added"] == 1


def test_season_freezes_when_the_year_turns(dirs):
    wp, od = dirs
    _write(wp, 777011, _game("2026-09-01T23:10:00.000Z"))
    B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    man = json.loads(B.manifest_path(od).read_text(encoding="utf-8"))
    assert man["seasons"]["2026"]["frozen"] is False
    res = B.build(win_prob_dir=wp, out_dir=od, live_season=2027)
    assert res["wrote"] is True
    man = json.loads(B.manifest_path(od).read_text(encoding="utf-8"))
    assert man["seasons"]["2026"]["frozen"] is True
    assert B.build(win_prob_dir=wp, out_dir=od, live_season=2027)["seasons"][2026]["status"] == "frozen"


def test_corpus_untouched(dirs, tmp_path, monkeypatch):
    wp, od = dirs
    corpus = tmp_path / "pbp_corpus"
    (corpus / "plays" / "2026").mkdir(parents=True)
    (corpus / "plays" / "2026" / "plays-2026.parquet").write_bytes(b"corpus bytes")
    (corpus / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(B, "CORPUS_DIR", corpus)
    before = _tree(corpus)
    _write(wp, 777012, _game("2026-06-01T23:10:00.000Z"))
    B.build(win_prob_dir=wp, out_dir=od, live_season=2026)
    assert _tree(corpus) == before
    with pytest.raises(SystemExit):
        B.build(win_prob_dir=wp, out_dir=corpus, live_season=2026)
    with pytest.raises(SystemExit):
        B.build(win_prob_dir=wp, out_dir=corpus / "physics", live_season=2026)
    assert _tree(corpus) == before


def test_default_paths_are_the_sidecar():
    assert B.OUT_DIR.name == "pbp_physics"
    assert B.OUT_DIR != B.CORPUS_DIR
    src = Path(B.__file__).read_text(encoding="utf-8")
    for banned in (".cache/betting", "betting_model_context", "game_feeds",
                   "lineup_captures", "leaderboard_vintages", "weather_forecasts"):
        assert banned not in src
