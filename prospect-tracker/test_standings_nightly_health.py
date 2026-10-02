"""STANDINGS_9: the nightly standings read's health row and its WCGB sign.

Two things are pinned here, both on fixtures, none of them touching the
network, the repo's data/ or a real .cache/:

  * fa_fit_backtest.standings_now stores StatsAPI's wildCardGamesBack as SIGNED
    games back: '+9.5' (9.5 games AHEAD of the last wild-card spot) is -9.5,
    '4.5' (behind) is 4.5, '-' is None. standings_core's wcgb keeps the
    magnitude with a wc_ahead flag instead, on purpose (STANDINGS_PLAN 4.6
    item 2, conflict C20).
  * run_monthly files a `statsapi_standings` ingest row right after proj_export's
    current-season attach, on the SCHEDULED_EXPORTS watch list, ok on 30 clubs
    and a fresh cache in season, red on {} or fewer than 30 clubs, and it never
    fetches.
"""
from __future__ import annotations

import ast
import json
import os
from datetime import date
from pathlib import Path

import pytest

import fa_fit_backtest as fb
import run_monthly as rm

ROOT = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# the sign
# --------------------------------------------------------------------------- #
def _fake_fetch(payload):
    class FR:
        status = 200
        body = json.dumps(payload)
    return lambda *a, **k: FR()


def _tr(team_id, name, wcgb, wc_rank):
    return {"team": {"id": team_id, "name": name}, "wins": 90, "losses": 72,
            "winningPercentage": "0.556", "gamesPlayed": 162,
            "runsScored": 750, "runsAllowed": 690, "runDifferential": 60,
            "gamesBack": "3.0", "divisionGamesBack": "3.0",
            "wildCardGamesBack": wcgb, "divisionRank": "2",
            "wildCardRank": wc_rank}


THREE_ROWS = {"records": [{"league": {"id": 103}, "division": {"id": 201},
    "teamRecords": [
        _tr(147, "New York Yankees", "+9.5", "1"),   # ahead of the cutoff
        _tr(111, "Boston Red Sox", "-", "3"),         # holds the last spot
        _tr(141, "Toronto Blue Jays", "4.5", "4"),    # behind
    ]}]}


def test_wcgb_is_signed_games_back(monkeypatch):
    monkeypatch.setattr(fb, "_fetch", _fake_fetch(THREE_ROWS))
    out = fb.standings_now(2026)
    assert set(out) == {"NYY", "BOS", "TOR"}
    assert out["NYY"]["wcGb"] == -9.5
    assert out["BOS"]["wcGb"] is None
    assert out["TOR"]["wcGb"] == 4.5


def test_sign_helper_on_the_feed_spellings():
    assert fb._sn_wcgb("+9.5") == -9.5
    assert fb._sn_wcgb(" +2.0 ") == -2.0
    assert fb._sn_wcgb("4.5") == 4.5
    assert fb._sn_wcgb("2.5") == 2.5
    assert fb._sn_wcgb("-") is None
    assert fb._sn_wcgb(None) is None and fb._sn_wcgb("") is None
    assert fb._sn_wcgb("+") is None and fb._sn_wcgb("+x") is None
    z = fb._sn_wcgb("+0.0")
    assert z == 0.0 and str(z) == "0.0"


def test_each_convention_names_the_other():
    src = (ROOT / "fa_fit_backtest.py").read_text(encoding="utf-8")
    doc = ast.get_docstring(next(n for n in ast.parse(src).body
                                 if isinstance(n, ast.FunctionDef) and n.name == "_sn_wcgb"))
    assert "standings_core" in doc and "wc_ahead" in doc and "not unified" in doc


def test_the_read_records_how_many_clubs_it_returned(monkeypatch):
    monkeypatch.setattr(fb, "STANDINGS_NOW_CLUBS", {})
    monkeypatch.setattr(fb, "_fetch", _fake_fetch(THREE_ROWS))
    fb.standings_now(2026)
    assert fb.STANDINGS_NOW_CLUBS == {2026: 3}

    class FR0:
        status = 0
        body = ""
    monkeypatch.setattr(fb, "_fetch", lambda *a, **k: FR0())
    assert fb.standings_now(2026) == {}
    assert fb.STANDINGS_NOW_CLUBS == {2026: 0}

    class FRbad:
        status = 200
        body = "not json"
    monkeypatch.setattr(fb, "_fetch", lambda *a, **k: FRbad())
    fb.STANDINGS_NOW_CLUBS[2026] = 30
    assert fb.standings_now(2026) == {}
    assert fb.STANDINGS_NOW_CLUBS == {2026: 0}


# --------------------------------------------------------------------------- #
# the health row
# --------------------------------------------------------------------------- #
NOW = 1_790_000_000.0          # a fixed clock; the cache mtime is set from it


def _dirs(tmp_path, *, age_h=None, start="2026-03-25", end="2026-09-27"):
    cache = tmp_path / "cache"
    cal = tmp_path / "cal"
    cache.mkdir(parents=True)
    cal.mkdir(parents=True)
    if age_h is not None:
        p = cache / "statsapi_standings_2026.json"
        p.write_text("{}", encoding="utf-8")
        os.utime(p, (NOW - age_h * 3600, NOW - age_h * 3600))
    if start:
        (cal / "season_2026.json").write_text(json.dumps({"seasons": [
            {"seasonId": "2026", "regularSeasonStartDate": start,
             "regularSeasonEndDate": end}]}), encoding="utf-8")
    return cache, cal


def _run(tmp_path, *, n, age_h, today, start="2026-03-25"):
    cache, cal = _dirs(tmp_path, age_h=age_h, start=start)
    filed = []
    reads = {} if n is None else {2026: n}
    ok, rows, msg = rm._statsapi_standings_health(
        2026, reads=reads, cache_dir=cache, calendar_dir=cal, today=today,
        now_ts=NOW, record=lambda *a, **k: filed.append((a, k)))
    assert len(filed) == 1
    (src, f_ok, f_rows, f_msg), kw = filed[0]
    assert (src, f_ok, f_rows, f_msg) == ("statsapi_standings", ok, rows, msg)
    assert kw["scope"] == "2026"
    return ok, rows, msg, cache


IN_SEASON = date(2026, 7, 1)
OFFSEASON = date(2026, 10, 2)


def test_ok_on_thirty_clubs_and_a_fresh_cache_in_season(tmp_path):
    ok, rows, msg, cache = _run(tmp_path, n=30, age_h=5, today=IN_SEASON)
    assert ok and rows == 30
    assert str(cache / "statsapi_standings_2026.json") in msg
    assert "modified 20" in msg and "5.0 h old" in msg
    assert "in the regular season" in msg


@pytest.mark.parametrize("n, needle", [
    (0, "returned {}"),
    (29, "returned 29 of 30 clubs"),
    (None, "did not run in this pass"),
])
def test_red_when_the_read_came_back_short(tmp_path, n, needle):
    ok, rows, msg, _ = _run(tmp_path, n=n, age_h=5, today=IN_SEASON)
    assert not ok and needle in msg and "statsapi_standings_2026.json" in msg


def test_red_on_a_stale_cache_in_season_and_not_judged_after_it(tmp_path):
    ok, _, msg, _ = _run(tmp_path / "a", n=30, age_h=48.0, today=IN_SEASON)
    assert not ok and "48.0 h old during the regular season" in msg
    ok, _, msg, _ = _run(tmp_path / "b", n=30, age_h=47.9, today=IN_SEASON)
    assert ok
    ok, _, msg, _ = _run(tmp_path / "c", n=30, age_h=200, today=OFFSEASON)
    assert ok and "outside the regular season" in msg and "200.0 h old" in msg


def test_red_on_an_absent_cache_in_season(tmp_path):
    ok, _, msg, _ = _run(tmp_path, n=30, age_h=None, today=IN_SEASON)
    assert not ok and "absent" in msg


def test_no_calendar_on_disk_prints_the_age_without_judging_it(tmp_path):
    ok, _, msg, _ = _run(tmp_path, n=30, age_h=100, today=IN_SEASON, start=None)
    assert ok and "regular-season dates not on disk" in msg


def test_the_check_never_fetches(tmp_path, monkeypatch):
    import requests
    import scrapers

    def boom(*a, **k):
        raise AssertionError("the health row must not fetch")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(scrapers, "_fetch", boom)
    monkeypatch.setattr(fb, "_fetch", boom)
    monkeypatch.setattr(fb, "standings_now", boom)
    monkeypatch.setattr(fb, "STANDINGS_NOW_CLUBS", {2026: 30})
    cache, cal = _dirs(tmp_path, age_h=1)
    filed = []
    ok, rows, _ = rm._statsapi_standings_health(
        2026, cache_dir=cache, calendar_dir=cal, today=IN_SEASON, now_ts=NOW,
        record=lambda *a, **k: filed.append(a))
    assert ok and rows == 30 and filed[0][0] == "statsapi_standings"


def test_a_red_row_reaches_the_red_array(tmp_path, monkeypatch):
    """What the deploy shell prints as '!!! INGEST RED: statsapi_standings'."""
    import storage
    monkeypatch.setattr(rm, "_INGEST_HEALTH", [])
    monkeypatch.setattr(storage, "load_source_checks", lambda *a, **k: {})
    cache, cal = _dirs(tmp_path, age_h=1)
    rm._statsapi_standings_health(2026, reads={2026: 0}, cache_dir=cache,
                                  calendar_dir=cal, today=IN_SEASON, now_ts=NOW)
    out = tmp_path / "out"
    payload = rm.write_ingest_health(out, "daily")
    assert "statsapi_standings" in payload["red"]
    row = next(r for r in payload["sources"] if r["source"] == "statsapi_standings")
    assert row["kind"] == "export" and row["ok"] is False and row["scope"] == "2026"


# --------------------------------------------------------------------------- #
# the wiring
# --------------------------------------------------------------------------- #
def test_the_step_files_the_row_after_the_current_season_attach():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"statsapi_standings"' in src[i:src.index("\n)\n", i)]
    assert rm._ingest_kind("statsapi_standings") == "export"
    body = src[src.index("def rebuild_only("):src.index("\ndef ", src.index("def rebuild_only(") + 10)]
    proj = body.index("from proj_export import export as _export_proj")
    step = body.index('_step("d9-std. Nightly standings read health (statsapi_standings)"')
    assert proj < step < body.index("from bayes_trade_value import export_trade_values_json")
    assert "_statsapi_standings_health(_proj_first_season - 1, log=log)" in body
    assert '_record_ingest("statsapi_standings", False' in body
    # the step name is used once in the tree's pipeline
    assert src.count("d9-std. Nightly standings read health") == 1


def test_the_health_helper_reaches_no_fetcher():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "_statsapi_standings_health")
    called = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
              for c in ast.walk(fn) if isinstance(c, ast.Call)}
    for banned in ("_fetch", "standings_now", "standings_wins", "urlopen",
                   "request", "regular_season_dates", "_cached_get"):
        assert banned not in called, banned
    # dict .get is called; requests.get is not, because requests is never named
    assert "requests" not in ast.unparse(fn)
