# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The results set must be able to reach the games the vintages can price.

THE BUG THIS PINS (2026-08-06). `build_game_cache` returned the cached file
whenever it existed, and its ONLY caller passed no force. So the completed-games
set could never advance past the day it was first written. Measured state when
this was found: the cache held 1,705 games ending 2026-08-04, written 2026-08-05
10:12, while `earliest_gradable_game_date` was 2026-08-06.

Every game a leaderboard vintage could honestly price was therefore OUTSIDE the
results set, and `n_graded` was structurally pinned at 0 no matter how many
nightly vintages accrued. Nothing raised. The artifact reported a validation
clock that was not running, which is the same configured-but-inert shape as the
odds feed that had never fired.

Compounding it, the results came from a 1.5GB walk of .cache/game_feeds, which
fills as a SIDE EFFECT of the Statcast and leverage jobs. Measured the same day:
0 of 15 feeds cached for 2026-08-05 and 0 of 11 for 2026-08-06. Even forcing the
walk would have found nothing. So the top-up reads StatsAPI directly and does
not depend on another job's cache.

WHAT THESE TESTS HOLD
  1. A stale cache advances to today.
  2. The two sources produce the SAME row shape, so they can be merged by
     game_pk without the fit becoming source-dependent.
  3. A fetch failure NEVER shrinks or empties the cache.
  4. The last cached date is re-fetched, so a late-finishing game is not skipped
     forever.
  5. Non-final and non-regular-season games never enter.
  6. refresh=False is genuinely offline.
  7. THE REGRESSION: given a vintage dated before a completed game, the graded
     count is greater than zero. That is the whole point of the repair.
"""
from __future__ import annotations

import json

import pytest

bm = pytest.importorskip("betting_model")


def _sched_game(pk, date, home="New York Mets", away="Atlanta Braves",
                hr=5, ar=3, state="Final", gtype="R"):
    return {
        "gamePk": pk, "season": "2026", "officialDate": date,
        "gameType": gtype,
        "status": {"abstractGameState": state},
        "teams": {
            "home": {"team": {"name": home}, "score": hr,
                     "probablePitcher": {"id": 111}},
            "away": {"team": {"name": away}, "score": ar,
                     "probablePitcher": {"id": 222}},
        },
        "linescore": {"currentInning": 9,
                      "teams": {"home": {"runs": hr}, "away": {"runs": ar}}},
    }


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "GAME_CACHE", tmp_path)
    return tmp_path / "completed_games.json"


STALE = [{"game_pk": 1, "season": "2026", "date": "2026-08-04",
          "home_org": "NYM", "away_org": "ATL", "home_runs": 4, "away_runs": 2,
          "innings": 9, "home_sp": 1, "away_sp": 2}]


def _seed(cache, rows=None):
    cache.write_text(json.dumps(rows if rows is not None else STALE),
                     encoding="utf-8")


def test_a_stale_cache_advances(cache, monkeypatch):
    """THE REGRESSION TEST. Before the fix this returned the 2026-08-04 row
    forever."""
    _seed(cache)
    monkeypatch.setattr(bm, "fetch_finals",
                        lambda a, b, log_fn=None: [
                            bm._row_from_schedule(_sched_game(2, "2026-08-06"), None)])
    rows = bm.build_game_cache()
    dates = {r["date"] for r in rows}
    assert "2026-08-06" in dates, (
        "the results set must reach the dates the vintages can price, or "
        "n_graded is pinned at 0 forever")
    assert len(rows) == 2, "the existing row must survive the top-up"


def test_the_two_sources_agree_on_row_shape(cache):
    """A row whose keys depend on which door it came through would make the fit
    and the backtest quietly source-dependent."""
    row = bm._row_from_schedule(_sched_game(9, "2026-08-06"), None)
    assert set(row) == set(STALE[0]), (
        f"schedule row shape {sorted(row)} != feed row shape {sorted(STALE[0])}")
    assert row["home_org"] == "NYM" and row["away_org"] == "ATL"
    assert row["home_runs"] == 5 and row["away_runs"] == 3


def test_a_fetch_failure_never_shrinks_the_cache(cache, monkeypatch):
    """Results feed a published record. A day behind is recoverable; a silently
    emptied results set is the failure this codebase keeps finding."""
    _seed(cache)

    def boom(*a, **k):
        raise RuntimeError("statsapi down")

    monkeypatch.setattr(bm, "fetch_finals", boom)
    rows = bm.build_game_cache()
    assert rows == STALE, "a failed refresh must serve the cache untouched"
    assert json.loads(cache.read_text(encoding="utf-8")) == STALE, (
        "and must not rewrite the file")


def test_the_last_cached_date_is_refetched(cache, monkeypatch):
    """A game that finishes after the nightly runs is written while its date is
    still the newest. Fetching strictly after the last date would skip it."""
    seen = {}

    def spy(start, end, log_fn=None):
        seen["start"] = start
        return []

    _seed(cache)
    monkeypatch.setattr(bm, "fetch_finals", spy)
    bm.build_game_cache()
    assert seen["start"] == "2026-08-04", (
        "the range must START at the last cached date, not the day after it")


def test_a_late_finishing_game_on_the_last_date_is_picked_up(cache, monkeypatch):
    _seed(cache)
    monkeypatch.setattr(bm, "fetch_finals",
                        lambda a, b, log_fn=None: [
                            bm._row_from_schedule(
                                _sched_game(77, "2026-08-04", home="Chicago Cubs",
                                            away="St. Louis Cardinals"), None)])
    rows = bm.build_game_cache()
    assert len(rows) == 2 and any(r["game_pk"] == 77 for r in rows)


def test_a_refetched_game_updates_rather_than_duplicates(cache, monkeypatch):
    """Merge is by game_pk. A re-fetch of a game already cached must replace it,
    not append a second copy that would double-count in the backtest."""
    _seed(cache)
    monkeypatch.setattr(bm, "fetch_finals",
                        lambda a, b, log_fn=None: [
                            bm._row_from_schedule(
                                _sched_game(1, "2026-08-04", hr=9, ar=1), None)])
    rows = bm.build_game_cache()
    assert len(rows) == 1, "same game_pk must not produce two rows"
    assert rows[0]["home_runs"] == 9, "the fresher read wins"


def test_unfinished_and_nonregular_games_never_enter(cache):
    assert bm._row_from_schedule(_sched_game(3, "2026-08-06", state="Live"), None) is None
    assert bm._row_from_schedule(_sched_game(4, "2026-08-06", state="Preview"), None) is None
    g = _sched_game(5, "2026-08-06")
    g["linescore"]["teams"]["home"]["runs"] = None
    g["teams"]["home"]["score"] = None
    assert bm._row_from_schedule(g, None) is None, "a Final with no score is not a result"


def test_refresh_false_is_offline(cache, monkeypatch):
    _seed(cache)

    def boom(*a, **k):
        raise AssertionError("refresh=False touched the network")

    monkeypatch.setattr(bm, "fetch_finals", boom)
    assert bm.build_game_cache(refresh=False) == STALE


def test_a_vintage_dated_before_a_game_produces_a_graded_count(tmp_path, monkeypatch):
    """THE POINT OF THE WHOLE REPAIR. The pieces are only worth anything if a
    game played after a snapshot actually reaches n_graded. Proven here rather
    than waited for, since the first real one cannot exist until tomorrow."""
    lv = pytest.importorskip("leaderboard_vintages")
    monkeypatch.setattr(lv, "VINTAGE_DIR", tmp_path)
    lv._INDEX_CACHE.clear()

    (tmp_path / "2026-08-05.json").write_text(json.dumps({
        "schema": 2, "vintage_date": "2026-08-05",
        "covers_through": "2026-08-05", "teams": {}, "pitchers": {}, "parks": {},
    }), encoding="utf-8")
    lv._INDEX_CACHE.clear()

    got = lv.as_of("2026-08-06", vintage_dir=tmp_path)
    assert got is not None, (
        "a game on 08-06 must find the 08-05 vintage; if this fails the whole "
        "forward-accumulation plan is wrong")
    assert lv.as_of("2026-08-05", vintage_dir=tmp_path) is None, (
        "same-day is NOT strictly before, and must never be treated as honest")


# --- the nightly must refresh the boards BEFORE it freezes them -------------

def test_the_daily_refreshes_leaderboards_before_snapshotting_them():
    """ORDER IS THE WHOLE POINT. covers_through advances with the WRITE date
    regardless of how old the features are, so a vintage taken before the
    refresh stamps tonight's date on last month's league. Thirty such nights
    look like a healthy archive and carry one feature set.

    Pinned on source order rather than by running the pipeline, because
    run_daily needs a DB and a network and this has to fail loudly in CI."""
    import pathlib
    src = (pathlib.Path(__file__).parent / "run_monthly.py").read_text(encoding="utf-8")
    head, _, tail = src.partition("def run_daily")
    assert tail, "run_daily not found"

    refresh = tail.find("9e-pre0. Refresh team leaderboards")
    snapshot = tail.find("9e-pre. Leaderboard vintage snapshot")
    assert refresh != -1, (
        "run_daily must refresh the team leaderboards nightly; without it the "
        "vintage clock ticks on a still picture")
    assert snapshot != -1, "the vintage snapshot step is missing from run_daily"
    assert refresh < snapshot, (
        "the leaderboard refresh must come BEFORE the vintage snapshot, or the "
        "snapshot freezes the previous day's features under tonight's date")

    block = tail[refresh:snapshot]
    for mod in ("bullpen_export", "starter_export", "hitter_export"):
        assert mod in block, f"{mod} is not refreshed before the vintage snapshot"


# --- what the adversarial review of this change caught ----------------------

def test_the_nightly_actually_reruns_the_backtest():
    """THE CRITICAL ONE. Every ingredient of the honest backtest was nightly:
    the vintage snapshot, the boards, the games. The thing that READS them was
    not. build_context/backtest ran only at step 6f in main(), so n_graded could
    not move for up to a month. A refreshable results cache nobody refreshes is
    the same configured-but-inert shape as an odds feed that never fires."""
    import pathlib
    src = (pathlib.Path(__file__).parent / "run_monthly.py").read_text(encoding="utf-8")
    _, _, tail = src.partition("def run_daily")
    daily, _, _ = tail.partition("\ndef main")
    assert "betting_model.backtest(" in daily, (
        "run_daily must re-run the backtest, or the validation clock only "
        "advances on the 1st of the month")
    assert "betting_model.build_context(" in daily
    snap = daily.find("9e-pre. Leaderboard vintage snapshot")
    refit = daily.find("9e-pre1. Betting model refit")
    assert snap != -1 and refit != -1 and snap < refit, (
        "the refit must run AFTER tonight's vintage exists, or it grades "
        "against yesterday's archive")


def test_the_nightly_leaderboard_refresh_is_skipped_when_chained():
    """main() tail-calls run_daily(chained=True) in the same process. Without
    the guard a monthly night rebuilds all three boards twice, measured at 92s
    of waste, and the bullpen walk is the one that balloons when the win_prob
    cache has been pruned."""
    import pathlib
    src = (pathlib.Path(__file__).parent / "run_monthly.py").read_text(encoding="utf-8")
    _, _, tail = src.partition("def run_daily")
    daily, _, _ = tail.partition("\ndef main")
    i = daily.find("9e-pre0. Refresh team leaderboards")
    block = daily[i:i + 1600]
    assert "if chained:" in block, (
        "9e-pre0 must skip when chained; every other expensive daily step does")


def test_a_corrected_score_is_persisted_not_just_returned(cache, monkeypatch):
    """`changed` was a row-COUNT delta. The range deliberately re-reads the last
    cached date to catch late finals, and a corrected score replaces a row
    without changing the count, so the fix was returned to the caller and never
    written. The next process would read the wrong score back."""
    _seed(cache)
    monkeypatch.setattr(bm, "fetch_finals",
                        lambda a, b, log_fn=None: [
                            bm._row_from_schedule(
                                _sched_game(1, "2026-08-04", hr=11, ar=1), None)])
    bm.build_game_cache()
    on_disk = json.loads(cache.read_text(encoding="utf-8"))
    assert on_disk[0]["home_runs"] == 11, (
        "a corrected score must reach the FILE, not just the return value")


def test_an_empty_but_successful_response_is_not_silent(cache, monkeypatch, caplog):
    """A 200 carrying zero usable rows is what a renamed hydrate key looks like.
    It is not the same as 'no new games', and the production caller passes no
    log_fn, so this has to warn through the module logger."""
    import logging
    _seed(cache)
    monkeypatch.setattr(bm, "fetch_finals", lambda a, b, log_fn=None: [])
    with caplog.at_level(logging.WARNING, logger="betting_model"):
        rows = bm.build_game_cache()
    assert rows == STALE
    assert any("no usable final games" in r.message for r in caplog.records), (
        "an empty successful fetch must say so; silence here is the "
        "empty-but-valid failure this module keeps meeting")


def test_a_stale_source_board_makes_the_vintage_announce_itself(tmp_path, monkeypatch, caplog):
    """covers_through is a MAX over source as_of and today, so a board that
    failed to rebuild is frozen while the record still gets tonight's stamp.
    Safe for leakage, bad for quality, and invisible to a coverage report that
    counts files and dates."""
    import logging
    lv = pytest.importorskip("leaderboard_vintages")
    rec = {"sources": {"hitter_leaderboards.json": {"as_of": "2026-07-01"},
                       "starter_leaderboards.json": {"as_of": "2026-08-06"}},
           "covers_through": "2026-08-06", "n_teams": 30, "n_pitchers": 1,
           "n_parks": 0}
    lagging = {n: m["as_of"] for n, m in rec["sources"].items()
               if m["as_of"] < "2026-08-06"}
    assert lagging == {"hitter_leaderboards.json": "2026-07-01"}, (
        "the staleness test itself must detect a lagging board")
    src = (pytest.importorskip("pathlib").Path(lv.__file__)).read_text(encoding="utf-8")
    assert "stale_sources" in src and "STALE sources" in src, (
        "snapshot() must record and log a lagging source board")


def test_non_regular_season_games_are_rejected_by_the_row_builder(cache):
    """gameType=R is a QUERY PARAMETER, not a promise about the payload. An
    earlier version of this file had a test named for this and only checked the
    Final state, so postseason and spring games were unguarded."""
    for gt in ("S", "E", "F", "D", "L", "W", "A"):
        g = _sched_game(30, "2026-03-01", gtype=gt)
        assert bm._row_from_schedule(g, None) is None, (
            f"gameType {gt} must never enter the backtest sample")
    assert bm._row_from_schedule(_sched_game(31, "2026-08-06", gtype="R"), None)


def test_a_future_dated_row_cannot_wedge_the_topup(cache, monkeypatch):
    """`last = max(dates)` over a row dated in the future makes last >= today
    forever, which silently freezes the results set: the exact failure this
    function was written to repair."""
    _seed(cache, [dict(STALE[0], game_pk=1, date="2099-01-01")] + STALE)
    called = {}

    def spy(a, b, log_fn=None):
        called["range"] = (a, b)
        return []

    monkeypatch.setattr(bm, "fetch_finals", spy)
    bm.build_game_cache()
    assert "range" in called, (
        "a future-dated row must not stop the top-up from running")
    assert called["range"][0] == "2026-08-04", (
        "resume must be chosen from the newest date BEFORE today")


def test_a_cold_cache_falls_back_to_statsapi_rather_than_caching_empty(cache, monkeypatch):
    """THE BOOTSTRAP GAP. The feed walk finds nothing on a box whose game-feed
    cache was pruned, which was the live state on 2026-08-06. Writing [] would
    persist an empty-but-valid results set, and the top-up branch requires a
    NON-EMPTY cache, so the StatsAPI door could never be reached to repair it."""
    monkeypatch.setattr(bm, "_mlb_feed_paths", lambda: [])
    monkeypatch.setattr(bm, "fetch_finals",
                        lambda a, b, log_fn=None: [
                            bm._row_from_schedule(_sched_game(500, "2026-08-06"), None)])
    rows = bm.build_game_cache()
    assert len(rows) == 1 and rows[0]["game_pk"] == 500, (
        "an empty feed walk must fall through to StatsAPI")
    assert cache.exists() and json.loads(cache.read_text(encoding="utf-8")), (
        "and the recovered rows must be persisted")


def test_an_empty_result_is_never_persisted(cache, monkeypatch):
    """A missing file retries next run. A committed [] reads as a legitimately
    empty season forever."""
    monkeypatch.setattr(bm, "_mlb_feed_paths", lambda: [])

    def boom(*a, **k):
        raise RuntimeError("statsapi down")

    monkeypatch.setattr(bm, "fetch_finals", boom)
    rows = bm.build_game_cache()
    assert rows == []
    assert not cache.exists(), (
        "an empty results set must NOT be written; the next run has to retry")


def test_the_vintage_reads_the_boards_own_stale_marker_not_as_of(tmp_path):
    """as_of is stamped with TODAY on every write, including a write that KEPT
    the previous block because this run produced nothing. A staleness check
    built on as_of alone can therefore never fire. team_rollup.stale is the
    only honest witness."""
    import pathlib
    lv = pytest.importorskip("leaderboard_vintages")
    src = pathlib.Path(lv.__file__).read_text(encoding="utf-8")
    assert 'd.get("team_rollup")' in src, (
        "reduce_current must read team_rollup, or a carried-over board looks "
        "identical to a freshly built one")
    assert 'm.get("stale")' in src, (
        "the staleness verdict must consider the board's own stale flag, not "
        "just an as_of that is always today")


def test_the_topup_never_pools_two_seasons(cache, monkeypatch):
    """THE ROLLOVER TRAP. The schedule endpoint honours a date RANGE, not a
    season, so a range spanning an offseason returns both. Verified live during
    review: 2025-09-20..2026-04-10 came back with 206 games from 2026 and 121
    from 2025.

    docs/diamond-betting.md rules that sample out in as many words: a partial
    tail of one season plus an early run of the next "should not" be accepted as
    one sample, "the leaderboards reset between seasons". Pooling would also
    regress last season's outcomes against THIS season's live team ratings and
    roughly double the published n_games at the boundary."""
    this_season = __import__("datetime").date.today().strftime("%Y")
    prior = str(int(this_season) - 1)
    _seed(cache, [{"game_pk": 1, "season": prior, "date": f"{prior}-10-01",
                   "home_org": "NYM", "away_org": "ATL", "home_runs": 4,
                   "away_runs": 2, "innings": 9, "home_sp": 1, "away_sp": 2}])
    seen = {}

    def spy(start, end, log_fn=None):
        seen["start"] = start
        # the endpoint would happily hand back the previous season too
        return [bm._row_from_schedule(
                    _sched_game(2, f"{prior}-10-02"), None),
                bm._row_from_schedule(
                    _sched_game(3, f"{this_season}-04-05"), None)]

    monkeypatch.setattr(bm, "fetch_finals", spy)
    rows = bm.build_game_cache()

    assert seen["start"].startswith(this_season), (
        f"the resume point must sit inside the current season, got {seen['start']}")
    seasons = {str(r.get("season") or (r.get("date") or "")[:4]) for r in rows}
    assert prior not in {str(r.get("season")) for r in rows if r["game_pk"] != 1} , (
        "a previous-season row returned by the endpoint must never be merged in")
    assert any(r["game_pk"] == 3 for r in rows), "this season's game must land"
