# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the shared game-feed cache (feed_cache.py).

Pins the two behaviors the runtime win depends on:
  1. Completed games (older than RECENT_WINDOW_DAYS) get a permanent TTL;
     recent/unknown-date games stay at the safe 24h TTL.
  2. get_game_feed serves immutable games from disk without re-hitting the
     network on a later run, while a recent game past its short TTL re-fetches.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

import feed_cache


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


# ── TTL selection ───────────────────────────────────────────────────────────

class TestTtlForDate:
    def test_recent_game_gets_short_ttl(self):
        assert feed_cache._ttl_for_date(_iso(1)) == feed_cache.SHORT_TTL

    def test_old_game_gets_final_ttl(self):
        assert feed_cache._ttl_for_date(_iso(10)) == feed_cache.FINAL_TTL

    def test_boundary_is_inclusive_of_final(self):
        # Exactly RECENT_WINDOW_DAYS old counts as final (age >= cutoff).
        assert feed_cache._ttl_for_date(_iso(feed_cache.RECENT_WINDOW_DAYS)) == feed_cache.FINAL_TTL
        # One day short of the window stays short-TTL.
        assert feed_cache._ttl_for_date(_iso(feed_cache.RECENT_WINDOW_DAYS - 1)) == feed_cache.SHORT_TTL

    def test_missing_or_bad_date_falls_back_to_short(self):
        assert feed_cache._ttl_for_date(None) == feed_cache.SHORT_TTL
        assert feed_cache._ttl_for_date("") == feed_cache.SHORT_TTL
        assert feed_cache._ttl_for_date("not-a-date") == feed_cache.SHORT_TTL

    def test_datetime_string_is_truncated_to_date(self):
        assert feed_cache._ttl_for_date(_iso(10) + "T19:05:00Z") == feed_cache.FINAL_TTL


# ── get_game_feed caching ───────────────────────────────────────────────────

class TestGetGameFeed:
    def _patch(self, monkeypatch, tmp_path, payload):
        monkeypatch.setattr(feed_cache, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(feed_cache.time, "sleep", lambda *_: None)
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        session = MagicMock()
        session.get.return_value = resp
        monkeypatch.setattr(feed_cache, "SESSION", session)
        return session

    def test_first_call_fetches_then_second_is_cached(self, monkeypatch, tmp_path):
        payload = {"gameData": {"status": {"abstractGameState": "Final"}}}
        session = self._patch(monkeypatch, tmp_path, payload)

        out1 = feed_cache.get_game_feed(715000, game_date=_iso(10))
        assert out1 == payload
        assert session.get.call_count == 1
        assert (tmp_path / "715000.json").exists()

        # A completed game stays cached: no second network call.
        out2 = feed_cache.get_game_feed(715000, game_date=_iso(10))
        assert out2 == payload
        assert session.get.call_count == 1

    def test_recent_game_refetches_after_short_ttl(self, monkeypatch, tmp_path):
        payload = {"gameData": {}}
        session = self._patch(monkeypatch, tmp_path, payload)

        feed_cache.get_game_feed(715001, game_date=_iso(0))
        assert session.get.call_count == 1

        # Age the cache file past SHORT_TTL; a recent-date read must re-fetch.
        cache_file = tmp_path / "715001.json"
        old = time.time() - (feed_cache.SHORT_TTL + 60)
        import os
        os.utime(cache_file, (old, old))

        feed_cache.get_game_feed(715001, game_date=_iso(0))
        assert session.get.call_count == 2

    def test_corrupt_cache_file_is_refetched(self, monkeypatch, tmp_path):
        payload = {"gameData": {"ok": True}}
        session = self._patch(monkeypatch, tmp_path, payload)
        (tmp_path / "715002.json").write_text("{ not json", encoding="utf-8")

        out = feed_cache.get_game_feed(715002, game_date=_iso(10))
        assert out == payload
        assert session.get.call_count == 1


# ── pruning ─────────────────────────────────────────────────────────────────

class TestPrune:
    def test_prunes_only_stale_files(self, tmp_path):
        fresh = tmp_path / "1.json"
        stale = tmp_path / "2.json"
        fresh.write_text("{}", encoding="utf-8")
        stale.write_text("{}", encoding="utf-8")
        import os
        old = time.time() - 500 * 86400
        os.utime(stale, (old, old))

        removed = feed_cache.prune_old_feeds(max_age_days=400, cache_dir=tmp_path)
        assert removed == 1
        assert fresh.exists()
        assert not stale.exists()
