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

WHAT THESE TESTS HOLD
  1. The slate date comes from the earliest first pitch, in US Eastern.
  2. A capture that rolls past UTC midnight still resolves to its own slate.
  3. A snapshot written before slate_date existed still resolves by filename,
     so the fix cannot orphan the existing cache.
  4. The kind filter still applies, so an open snapshot is never served as a
     close.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

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
