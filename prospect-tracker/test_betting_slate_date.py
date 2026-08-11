# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A snapshot belongs to a SLATE, not to a UTC filename.

THE BUG THIS CLOSES (plan item F2.7, fixed 2026-08-06). Snapshot filenames are
stamped with the UTC capture date, but a slate is identified by its US-local
officialDate. A West Coast game with a 10:10pm ET first pitch closes at about
01:55 UTC the NEXT day, so its close snapshot lands under tomorrow's filename
while the slate it belongs to is today.

Two things break, and both are silent:

  * `closing_snapshot(slate)` filters on the filename date and never finds it,
    so CLV for that slate is unrecoverable. Worse than losing it, the grader
    added in eb53d46 then reports "the close job did not fire" for a job that
    fired perfectly, which sends whoever reads it to debug the wrong thing.
  * tools/betting_close_job.py asks the same question as its once-per-slate
    guard, so it can fire a SECOND paid capture for a slate already captured.
    That is 3 credits against a 500 credit monthly budget, every late slate.

An all-late card is not exotic. It is most of the West Coast schedule.

THREE MORE THINGS A SLATE HAS TO SURVIVE (2026-08-09).

  D6. `slate_games` takes min(date) over the BETTABLE rows, so one straggler
  Preview game on a date whose card is otherwise played wins the whole board.
  The 2026-08-08 local build priced 1 game of 15 and no field in the payload
  said so: `n_slate_games` read 1, which is what a one-game Monday reads like.
  Measured again on 2026-08-09 at 20:46Z: the 8/9 date held 15 games, 14 of them
  started or finished, and 4 of the 5 rows StatsAPI still called Preview had a
  first pitch in the past. That is why the clock is checked as well as the
  status.

  D5. `build` called `bi.latest_snapshot()` with no filter and joined it to
  whatever slate came back. Nothing compared the two, so a failed morning ingest
  prices tonight's board off last night's capture and the only thing that
  changes on the page is a timestamp.

  R3. `validation_state` filters the vintage coverage through an allowlist, and
  the allowlist did not grow when leaderboard_vintages.coverage() did. The
  provenance split (backfilled against live) and the age distribution were
  computed and silently dropped, so /betting/ kept serving one blended
  `n_vintages` that docs/diamond-betting.md section 6 says must never be quoted
  alone.

WHAT THESE TESTS HOLD
  1. The slate date comes from the earliest first pitch, in US Eastern.
  2. A capture that rolls past UTC midnight still resolves to its own slate.
  3. A snapshot written before slate_date existed still resolves by filename,
     so the fix cannot orphan the existing cache.
  4. The kind filter still applies, so an open snapshot is never served as a
     close.
  5. The board walks to the first date that is still a whole card, names every
     date it skipped and why, and stamps a fragment as a fragment.
  6. The snapshot is requested FOR the board slate, and one that cannot price it
     empties both slots instead of pricing the board against another day.
  7. The vintage provenance and age fields reach the payload.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")


def _cap(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_the_slate_comes_from_the_earliest_first_pitch():
    evs = [{"commence_time": "2026-08-07T02:10:00Z"},   # 10:10pm ET Aug 6
           {"commence_time": "2026-08-07T01:05:00Z"}]   # 9:05pm ET Aug 6
    assert bi.slate_date_of(evs, _cap(2026, 8, 7, 1, 55)) == "2026-08-06"


def test_a_capture_past_utc_midnight_keeps_its_own_slate():
    """THE REGRESSION. The filename says 2026-08-07; the slate is 2026-08-06."""
    cap = _cap(2026, 8, 7, 1, 55)
    assert cap.strftime("%Y-%m-%d") == "2026-08-07", "premise: filename rolls"
    assert bi.slate_date_of([{"commence_time": "2026-08-07T02:10:00Z"}],
                            cap) == "2026-08-06"


def test_an_afternoon_slate_is_unchanged():
    """The common case must not move. A 1:05pm ET first pitch is 17:05 UTC the
    same day."""
    assert bi.slate_date_of([{"commence_time": "2026-08-06T17:05:00Z"}],
                            _cap(2026, 8, 6, 16, 50)) == "2026-08-06"


def test_an_empty_board_falls_back_to_the_capture_date():
    assert bi.slate_date_of([], _cap(2026, 8, 6, 15, 19)) == "2026-08-06"
    assert bi.slate_date_of(None, _cap(2026, 8, 6, 15, 19)) == "2026-08-06"


def test_an_unparseable_commence_time_does_not_crash_the_write():
    assert bi.slate_date_of([{"commence_time": "not a time"}],
                            _cap(2026, 8, 6, 15, 19)) == "2026-08-06"


def _write(dirpath, name, wrapper):
    (dirpath / name).write_text(json.dumps(wrapper), encoding="utf-8")


def test_a_close_written_past_midnight_is_found_by_its_slate(tmp_path, monkeypatch):
    """End to end through the reader the CLV grader actually calls."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _write(tmp_path, "2026-08-07-0155.json", {
        "captured_at": "2026-08-07T01:55:00+00:00", "slate_date": "2026-08-06",
        "kind": "close", "events": []})
    got = bi.closing_snapshot("2026-08-06")
    assert got is not None, (
        "a close captured after UTC midnight must still belong to its slate; "
        "missing it makes CLV unrecoverable and re-fires a paid capture")
    assert got["kind"] == "close"


def test_a_legacy_snapshot_without_a_slate_date_still_resolves(tmp_path, monkeypatch):
    """The cache predates this field. The fix must not orphan it."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _write(tmp_path, "2026-08-06-1519.json", {
        "captured_at": "2026-08-06T15:19:00+00:00", "kind": "open", "events": []})
    assert bi.latest_snapshot(kind="open", on_date="2026-08-06") is not None


def test_the_kind_filter_still_applies(tmp_path, monkeypatch):
    """An open capture must never be served as a close: CLV graded against the
    morning price is not CLV."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _write(tmp_path, "2026-08-06-1519.json", {
        "captured_at": "2026-08-06T15:19:00+00:00", "slate_date": "2026-08-06",
        "kind": "open", "events": []})
    assert bi.closing_snapshot("2026-08-06") is None


def test_a_neighbouring_slate_is_not_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _write(tmp_path, "2026-08-07-0155.json", {
        "captured_at": "2026-08-07T01:55:00+00:00", "slate_date": "2026-08-06",
        "kind": "close", "events": []})
    assert bi.closing_snapshot("2026-08-07") is None, (
        "the widened filename window must not leak a neighbouring slate; the "
        "wrapper's own slate_date is authoritative")


# ===========================================================================
# D6: the board is the first WHOLE card, not the first date with a survivor
# ===========================================================================
NOW = datetime(2026, 8, 9, 18, 22, tzinfo=timezone.utc)


def _g(day, hh, mm, status="Preview", pk=0):
    return {"game_pk": pk, "date": day, "status": status,
            "datetime": datetime(2026, 8, int(day[-2:]), hh, mm,
                                 tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")}


def _schedule(monkeypatch, games):
    """Point `betting_export._load` at a schedule block and nothing else."""
    monkeypatch.setattr(be, "_load",
                        lambda name: ({"schedule": {"games": games}}
                                      if name == "fantasy.json" else None))


# The real 2026-08-09 shape: 15 games, 10 already under way, 5 still ahead,
# with a full 10-game card on the next day.
def _real_shape():
    return ([_g("2026-08-09", 16 + i // 4, 10, "Live", pk=i) for i in range(10)]
            + [_g("2026-08-09", 20, 10, "Preview", pk=100 + i) for i in range(5)]
            + [_g("2026-08-10", 23, 15, "Preview", pk=200 + i) for i in range(10)])


def test_a_started_card_does_not_win_the_board(monkeypatch):
    """THE REGRESSION. 10 of the 15 games on 8/9 are under way, so what is left
    of that date is a fragment; the board is the next whole card."""
    _schedule(monkeypatch, _real_shape())
    old = be.slate_games()
    assert old[0]["date"] == "2026-08-09" and len(old) == 5, (
        "premise: the unchanged rule takes the started date and 5 of its 15 games")
    stats = {}
    day, games = be.resolve_slate(now=NOW, stats=stats)
    assert day == "2026-08-10"
    assert len(games) == 10
    assert stats["slate_rule"] == "first_open_slate"
    assert stats["partial_slate"] is None


def test_the_board_names_every_date_it_skipped_and_why(monkeypatch):
    """A board that silently moved a day is as hard to read as a board that
    silently kept a fragment."""
    _schedule(monkeypatch, _real_shape())
    stats = {}
    be.resolve_slate(now=NOW, stats=stats)
    by_date = {c["date"]: c for c in stats["slate_candidates"]}
    skipped = by_date["2026-08-09"]
    assert skipped["open"] is False
    assert skipped["n_games"] == 15 and skipped["n_bettable"] == 5
    assert "10 have already started" in skipped["why_not"]
    assert by_date["2026-08-10"]["open"] is True
    assert by_date["2026-08-10"]["why_not"] is None


def test_a_first_pitch_in_the_past_closes_its_date_whatever_the_status_says(monkeypatch):
    """MEASURED, not hypothetical. At 20:46Z on 2026-08-09, 4 of the 5 rows the
    schedule block still called Preview had a first pitch behind them, because
    fantasy.json is refreshed on the pipeline's clock and not on StatsAPI's."""
    games = [_g("2026-08-09", 18, 10, "Preview", pk=i) for i in range(3)] + \
            [_g("2026-08-10", 23, 15, "Preview", pk=10 + i) for i in range(3)]
    _schedule(monkeypatch, games)
    late = datetime(2026, 8, 9, 20, 46, tzinfo=timezone.utc)
    is_open, why = be._slate_is_open("2026-08-09", games, late)
    assert is_open is False and "3 have already started" in why
    day, _ = be.resolve_slate(now=late)
    assert day == "2026-08-10"
    # and before first pitch the same date is open, on the same rows
    assert be._slate_is_open("2026-08-09", games,
                             datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc))[0] is True


def test_a_postponement_does_not_close_its_own_date(monkeypatch):
    """A called-off game is not evidence that the rest of the card is under way.
    `anchors_close_window` already turns on exactly this distinction, and
    treating one postponement as a started slate would push the board a day
    forward on a card that has not thrown a pitch."""
    games = [_g("2026-08-09", 23, 5, "Preview", pk=i) for i in range(14)] + \
            [_g("2026-08-09", 23, 5, "Postponed", pk=99)]
    _schedule(monkeypatch, games)
    stats = {}
    day, rows = be.resolve_slate(now=NOW, stats=stats)
    assert day == "2026-08-09"
    assert len(rows) == 14, "the postponed game is unbettable and still leaves the board"
    assert stats["slate_rule"] == "first_open_slate"


def test_an_open_date_with_nothing_bettable_is_skipped(monkeypatch):
    """Every game postponed. The date has not started, so it is open, and it is
    not a board either."""
    games = [_g("2026-08-09", 23, 5, "Postponed", pk=i) for i in range(4)] + \
            [_g("2026-08-10", 23, 15, "Preview", pk=10 + i) for i in range(6)]
    _schedule(monkeypatch, games)
    day, rows = be.resolve_slate(now=NOW)
    assert day == "2026-08-10" and len(rows) == 6


def test_no_open_date_falls_back_and_stamps_the_fragment(monkeypatch):
    """The 2026-08-08 case exactly: 15 games, 14 played, 1 left. The board is
    still that one game, because a fragment beats an empty page, and it says so
    in a field rather than leaving a reader to infer it from a count of 1."""
    games = [_g("2026-08-09", 17, 10, "Final", pk=i) for i in range(14)] + \
            [_g("2026-08-09", 23, 40, "Preview", pk=99)]
    _schedule(monkeypatch, games)
    stats = {}
    day, rows = be.resolve_slate(now=NOW, stats=stats)
    assert day == "2026-08-09" and len(rows) == 1
    assert stats["slate_rule"] == "earliest_bettable_partial"
    part = stats["partial_slate"]
    assert part["slate_date"] == "2026-08-09"
    assert part["n_games_on_date"] == 15 and part["n_bettable"] == 1
    assert "no date on the schedule is still a whole card" in part["reason"]


def test_an_explicit_date_bypasses_the_walk(monkeypatch):
    """`python betting_export.py --date` and the close job both mean the date
    they named, not the date the walk would prefer."""
    _schedule(monkeypatch, _real_shape())
    stats = {}
    day, rows = be.resolve_slate("2026-08-09", now=NOW, stats=stats)
    assert day == "2026-08-09" and len(rows) == 5
    assert stats["slate_rule"] == "explicit_date"


def test_an_empty_schedule_resolves_to_nothing_rather_than_raising(monkeypatch):
    _schedule(monkeypatch, [])
    stats = {}
    assert be.resolve_slate(now=NOW, stats=stats) == (None, [])
    assert stats["slate_candidates"] == []


# ===========================================================================
# D5: the snapshot has to be able to price THIS board
# ===========================================================================
def _raw_event(eid, commence, home="Atlanta Braves", away="New York Mets"):
    return {"id": eid, "commence_time": commence, "home_team": home,
            "away_team": away,
            "bookmakers": [{"key": "fanduel", "title": "FanDuel",
                            "last_update": commence,
                            "markets": [{"key": "h2h", "outcomes": [
                                {"name": home, "price": -130},
                                {"name": away, "price": 110}]}]}]}


def _snap(dirpath, name, slate_date, events, captured_at):
    (dirpath / name).write_text(json.dumps({
        "captured_at": captured_at, "slate_date": slate_date, "kind": "open",
        "events": events}), encoding="utf-8")


def test_a_snapshot_labelled_for_the_board_slate_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _snap(tmp_path, "2026-08-10-1500.json", "2026-08-10",
          [_raw_event("e1", "2026-08-10T23:15:00Z")], "2026-08-10T15:00:00+00:00")
    snap, events, state = be.resolve_snapshot(
        "2026-08-10", now=datetime(2026, 8, 10, 15, 1, tzinfo=timezone.utc))
    assert snap is not None and len(events) == 1
    assert state["matched"] is True and state["match_rule"] == "slate_label"
    assert state["mismatch"] is False


def test_a_snapshot_that_only_carries_the_board_slate_still_matches(tmp_path, monkeypatch):
    """THE ORDINARY EVENING BUILD, and the reason this is not a label
    comparison. A capture is labelled by its EARLIEST event, so an 18:22Z
    capture on 8/9 is stamped 2026-08-09 while carrying tomorrow's card. A board
    that has walked forward to 8/10 can never match that label, and the prices
    for those games are the market at capture time."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _snap(tmp_path, "2026-08-09-1822.json", "2026-08-09",
          [_raw_event("e1", "2026-08-09T20:10:00Z"),
           _raw_event("e2", "2026-08-10T23:15:00Z")],
          "2026-08-09T18:22:49+00:00")
    _, _, state = be.resolve_snapshot(
        "2026-08-10", now=datetime(2026, 8, 9, 18, 23, tzinfo=timezone.utc))
    assert state["match_rule"] == "carries_slate_events"
    assert state["n_pregame_events_on_board_slate"] == 1
    assert state["snapshot_slate"] == "2026-08-09"
    assert state["mismatch"] is False


def test_a_snapshot_that_cannot_price_the_board_slate_is_a_mismatch(tmp_path, monkeypatch):
    """THE REGRESSION. The morning ingest did not fire; the newest capture is
    two days old and every game in it has been played."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    _snap(tmp_path, "2026-08-07-1500.json", "2026-08-07",
          [_raw_event("e1", "2026-08-07T23:15:00Z")], "2026-08-07T15:00:00+00:00")
    _, _, state = be.resolve_snapshot(
        "2026-08-09", now=datetime(2026, 8, 9, 18, 22, tzinfo=timezone.utc))
    assert state["mismatch"] is True
    assert state["matched"] is False
    assert state["n_pregame_events_on_board_slate"] == 0
    assert "ODDS SLATE MISMATCH" in state["reason"]
    assert "2026-08-07" in state["reason"] and "2026-08-09" in state["reason"]
    assert state["snapshot_age_hours"] is not None


def test_no_snapshot_at_all_is_not_a_mismatch(tmp_path, monkeypatch):
    """"No feed" and "the wrong feed" are different facts. The first already has
    its own blocker and does not need a second, contradictory one."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    snap, events, state = be.resolve_snapshot("2026-08-09")
    assert snap is None and events == []
    assert state["mismatch"] is False
    assert "no odds snapshot is cached" in state["reason"]


def test_a_mismatch_empties_both_slots():
    """A pick against another slate's prices is worse than no pick. The board
    itself still renders: a fair line and a priced market are worth reading, and
    blanking them would send the page through the stale-board guard into a board
    that is older still."""
    board = [{"game_pk": 1, "start": "2026-08-09T23:15:00Z",
              "home": {"org": "ATL"}, "away": {"org": "NYM"},
              "moneyline": [{"side": "home", "label": "ATL", "edge": 0.20,
                             "odds": -110, "book": "fanduel", "model_prob": 0.70,
                             "ev_per_unit": 0.30}],
              "runline": None, "total": {"sides": None}}]
    free, _, meta0 = be.provisional_picks(board, odds_configured=True)
    assert free["pick_of_the_day"] is not None, "premise: this board has a pick"
    why = "ODDS SLATE MISMATCH: the board is the 2026-08-09 slate and ..."
    slots, reason, meta = be.provisional_picks(board, odds_configured=True,
                                               block_reason=why)
    assert slots["pick_of_the_day"] is None and slots["longshot_of_the_day"] is None
    assert reason == why
    assert meta["blocked"] is True and meta["blocked_reason"] == why
    for sm in meta["slots"].values():
        assert sm["present"] is False and sm["reason"] == why


# ===========================================================================
# R3: the vintage coverage fields have to reach the page
# ===========================================================================
def test_the_vintage_provenance_and_age_fields_survive_the_allowlist():
    """THE REGRESSION. All three were computed by leaderboard_vintages.coverage()
    and dropped by COVERAGE_KEYS, so the page served a blended count. Measured on
    the live store 2026-08-09: 15 vintages, 10 backfilled and 5 live, published
    as "15"."""
    cov = {"dir": "C:/build/box/path", "bytes": 131100, "schema": 2,
           "n_vintages": 15, "n_vintages_backfilled": 10, "n_vintages_live": 5,
           "n_vintages_unknown_provenance": 0,
           "n_vintages_with_parks": 14, "n_vintages_neutral_park": 1,
           "first": "2026-07-26", "last": "2026-08-09", "missing_dates": [],
           "span_days": 15, "latest_cutoff": "2026-08-09",
           "earliest_gradable_game_date": "2026-07-27",
           "vintage_age_days": {"basis": "calendar days inside the archive",
                                "n": 36, "median_days": 2, "p90_days": 9.5,
                                "max_days": 13, "mean_days": 3.86},
           "note": "15 vintages"}
    out = be.validation_state({"vintage_coverage": cov})["coverage"]
    assert out["n_vintages_backfilled"] == 10
    assert out["n_vintages_live"] == 5
    assert out["n_vintages_unknown_provenance"] == 0
    assert out["n_vintages_backfilled"] + out["n_vintages_live"] \
           + out["n_vintages_unknown_provenance"] == out["n_vintages"]
    assert out["vintage_age_days"]["median_days"] == 2


def test_the_build_box_path_and_the_store_size_still_do_not_ship():
    """Widening an allowlist is how a filesystem path reaches a public page.
    `dir` is not a fact about the model and `bytes` measures the store rather
    than the evidence."""
    cov = {"dir": "C:/build/box/path", "bytes": 131100, "n_vintages": 15,
           "n_vintages_backfilled": 10, "n_vintages_live": 5}
    out = be.validation_state({"vintage_coverage": cov})["coverage"]
    assert "dir" not in out and "bytes" not in out


def test_an_artifact_written_before_the_fields_existed_still_publishes():
    """data/betting_model_eval.json as it stands carries none of the three. The
    allowlist copies what is there and invents nothing."""
    cov = {"schema": 2, "n_vintages": 5, "n_vintages_with_parks": 4}
    out = be.validation_state({"vintage_coverage": cov})["coverage"]
    assert out == {"schema": 2, "n_vintages": 5, "n_vintages_with_parks": 4}
