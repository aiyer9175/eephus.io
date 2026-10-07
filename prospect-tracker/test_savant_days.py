# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""savant_days offline (League Trends plan 5.1, TR-Q3 (a)).

Another date's row refused, a failed fetch keeps the cache, a 403 and a changed
column set stop the run with what landed kept, and the Swing+ cache never
written. No test opens a socket: every fetch goes through a fake getter.
"""
from __future__ import annotations

import hashlib
import urllib.error
from pathlib import Path

import pytest

import savant_days as S

HEADER = ("pitch_type,game_date,release_speed,batter,pitcher,description,game_pk,"
          "at_bat_number,pitch_number,bat_speed,swing_length,attack_angle,attack_direction")


def _csv(rows) -> bytes:
    lines = [HEADER]
    for day, batter, desc, bs in rows:
        lines.append(f"FF,{day},95.0,{batter},500,{desc},777001,3,1,"
                     f"{bs if bs is not None else ''},{'7.1' if bs else ''},"
                     f"{'10.5' if bs else ''},1.0")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _getter(payloads: dict):
    def get(url: str) -> bytes:
        for day, body in payloads.items():
            if f"game_date_gt={day}&game_date_lt={day}" in url:
                if isinstance(body, Exception):
                    raise body
                return body
        raise AssertionError(f"unexpected url {url}")
    return get


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_day_query_is_the_swing_plus_skeleton_with_date_bounds():
    url = S.day_url("2025-06-01")
    assert "game_date_gt=2025-06-01&game_date_lt=2025-06-01" in url
    assert "hfSea=2025%7C" in url and "hfGT=R%7C" in url
    assert "batters_lookup" not in url
    assert url.startswith("https://baseballsavant.mlb.com/statcast_search/csv?all=true")


def test_another_dates_row_refused(tmp_path):
    body = _csv([("2025-06-01", 101, "foul", 72.5), ("2025-06-01", 102, "ball", None),
                 ("2025-06-02", 103, "foul", 70.0)])
    r = S.fetch_day("2025-06-01", out_dir=tmp_path, getter=_getter({"2025-06-01": body}),
                    throttle_s=0)
    assert (r["status"], r["rows"], r["swings"], r["refused"]) == ("written", 2, 1, 1)
    text = S.day_path("2025-06-01", tmp_path).read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(S.KEEP_COLS)
    assert "2025-06-02" not in text and "103" not in text.split("\n", 1)[1]
    # a response holding only another date writes nothing
    r2 = S.fetch_day("2025-06-03", out_dir=tmp_path,
                     getter=_getter({"2025-06-03": _csv([("2025-06-04", 1, "foul", 70.0)])}),
                     throttle_s=0)
    assert r2["status"] == "empty" and r2["refused"] == 1
    assert not S.day_path("2025-06-03", tmp_path).exists()


def test_failed_fetch_keeps_the_cache(tmp_path):
    p = S.day_path("2025-06-01", tmp_path)
    S.fetch_day("2025-06-01", out_dir=tmp_path,
                getter=_getter({"2025-06-01": _csv([("2025-06-01", 1, "foul", 70.0)])}),
                throttle_s=0)
    before = _sha(p)
    for err in (TimeoutError("timed out"), OSError("connection reset"),
                urllib.error.HTTPError("u", 502, "bad gateway", {}, None)):
        r = S.fetch_day("2025-06-01", out_dir=tmp_path, getter=_getter({"2025-06-01": err}),
                        throttle_s=0)
        assert r["status"] == "failed"
        assert _sha(p) == before
    assert not list(tmp_path.glob("*.tmp"))


def test_403_stops_the_run_and_keeps_what_landed(tmp_path):
    days = ["2025-06-01", "2025-06-02", "2025-06-03"]
    payloads = {"2025-06-01": _csv([("2025-06-01", 1, "foul", 70.0)]),
                "2025-06-02": urllib.error.HTTPError("u", 403, "forbidden", {}, None),
                "2025-06-03": _csv([("2025-06-03", 1, "foul", 70.0)])}
    res = S.run([2025], out_dir=tmp_path, dates_for=lambda s: days,
                getter=_getter(payloads), throttle_s=0, echo=lambda *_: None)
    assert res["stopped"] and "403" in res["stopped"]
    assert S.day_path("2025-06-01", tmp_path).exists()
    assert not S.day_path("2025-06-03", tmp_path).exists()
    assert res["manifest"]["seasons"]["2025"]["dates"] == 1


def test_changed_column_set_stops(tmp_path):
    bad = b"game_date,batter,description,bat_speed\n2025-06-01,1,foul,70\n"
    with pytest.raises(S.SavantStop, match="column set changed"):
        S.fetch_day("2025-06-01", out_dir=tmp_path, getter=_getter({"2025-06-01": bad}),
                    throttle_s=0)
    assert not S.day_path("2025-06-01", tmp_path).exists()


def test_run_skips_dates_already_cached_and_counts(tmp_path):
    days = ["2025-06-01", "2025-06-02"]
    calls = []

    def get(url):
        calls.append(url)
        day = url.split("game_date_gt=")[1][:10]
        return _csv([(day, 101, "foul", 72.0), (day, 102, "swinging_strike", 66.0),
                     (day, 101, "ball", None)])
    res = S.run([2025], out_dir=tmp_path, dates_for=lambda s: days, getter=get,
                throttle_s=0, echo=lambda *_: None)
    assert len(calls) == 2 and res["stopped"] is None
    c = res["manifest"]["seasons"]["2025"]
    assert (c["dates"], c["rows"], c["swings"], c["hitters"], c["max_game_date"]) == \
        (2, 6, 4, 2, "2025-06-02")
    S.run([2025], out_dir=tmp_path, dates_for=lambda s: days, getter=get,
          throttle_s=0, echo=lambda *_: None)
    assert len(calls) == 2                       # nothing refetched


def test_swing_plus_cache_never_written(tmp_path, monkeypatch):
    swing = tmp_path / "swing_pitches"
    swing.mkdir()
    (swing / "660670_2025.csv").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(S, "SWING_CACHE", swing)
    before = {p.name: _sha(p) for p in swing.iterdir()}
    out = tmp_path / "savant_days"
    S.run([2025], out_dir=out, dates_for=lambda s: ["2025-06-01"],
          getter=_getter({"2025-06-01": _csv([("2025-06-01", 1, "foul", 70.0)])}),
          throttle_s=0, echo=lambda *_: None)
    assert {p.name: _sha(p) for p in swing.iterdir()} == before
    for target in (swing, swing / "days"):
        with pytest.raises(SystemExit):
            S.fetch_day("2025-06-01", out_dir=target,
                        getter=_getter({"2025-06-01": _csv([])}), throttle_s=0)
    assert {p.name: _sha(p) for p in swing.iterdir()} == before
    assert S.OUT_DIR.parts[-2:] == ("league_trends", "savant_days")
    src = Path(S.__file__).read_text(encoding="utf-8")
    for banned in (".cache/betting", "betting_model_context", "game_feeds", "lineup_captures",
                   "leaderboard_vintages", "weather_forecasts", ".cache/odds"):
        assert banned not in src
