# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A cached MLBAM miss must expire; a cached hit must not.

THE INCIDENT (2026-08-03). resolve_mlbam_id cached a failed lookup as null
"to suppress retries on future runs", escapable only by hand-deleting
.cache/mlbam_ids.json. That is right for a wrong-identity binding and wrong
for a player who does not exist in StatsAPI YET.

Every 2026 draftee was resolved once at ingest, before any of them had signed
or been assigned to an affiliate, so every lookup missed and every miss was
cached permanently. Weeks later they were on affiliate rosters and playing,
but nothing ever asked again: all 199 active 2026 draftees carried no
mlbam_id, and with no id the stat fetch had nothing to key on. Measured on the
served board, the id was a perfect discriminator - of 4,550 active players all
4,296 with an id had stats and all 254 without one had none.

These tests pin the asymmetry: hits are permanent, misses expire, and a miss
recorded before the sidecar existed reads as expired so the poisoned entries
heal themselves on the next pass rather than needing a manual cache wipe.
"""

from __future__ import annotations

import json
import time

import pytest

import stats


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point both cache files at a temp dir so nothing touches .cache/."""
    monkeypatch.setattr(stats, "ID_CACHE_FILE", tmp_path / "mlbam_ids.json")
    monkeypatch.setattr(stats, "MISS_STAMP_FILE", tmp_path / "mlbam_id_misses.json")
    return tmp_path


@pytest.fixture
def no_resolvers(monkeypatch):
    """Count resolution attempts and make them all miss, so a test can tell
    'served from cache' apart from 're-resolved'."""
    calls = []

    def _index(*a, **k):
        calls.append("index")
        raise RuntimeError("no index in test")

    def _api(name):
        calls.append("api")
        return None, None

    monkeypatch.setattr(stats.PlayerIndex, "load_or_build", staticmethod(_index))
    monkeypatch.setattr(stats, "_search_mlbam_via_api", _api)
    return calls


def test_fresh_miss_is_not_retried(isolated_cache, no_resolvers):
    """Inside the TTL a miss is served from cache without hitting anything."""
    stats._save_id_cache({"someone_new": None})
    stats._record_miss("someone_new")

    assert stats.resolve_mlbam_id("someone_new", "Someone New") is None
    assert no_resolvers == [], (
        "a miss recorded moments ago should be served from cache, not re-queried")


def test_expired_miss_is_retried(isolated_cache, no_resolvers):
    """Past the TTL the miss is re-resolved rather than trusted forever."""
    stats._save_id_cache({"someone_new": None})
    stale = time.time() - (stats.NEG_ID_CACHE_TTL_DAYS + 1) * 86400
    (isolated_cache / "mlbam_id_misses.json").write_text(
        json.dumps({"someone_new": stale}))

    assert stats.resolve_mlbam_id("someone_new", "Someone New") is None
    assert no_resolvers, "an expired miss must trigger a fresh resolution attempt"


def test_unstamped_miss_reads_as_expired(isolated_cache, no_resolvers):
    """The healing property.

    Nulls cached before the sidecar existed carry no stamp. They must read as
    expired, so the 2026 draft class recovers on the next resolution pass
    instead of waiting for someone to delete the cache by hand.
    """
    stats._save_id_cache({"roch_cholowsky": None})   # no miss stamp written

    assert stats.resolve_mlbam_id("roch_cholowsky", "Roch Cholowsky", "SS") is None
    assert no_resolvers, (
        "a null with no miss stamp is a pre-TTL entry and must be retried")


def test_cached_hit_is_permanent(isolated_cache, no_resolvers):
    """Ids never change, so a hit must still short-circuit every resolver."""
    stats._save_id_cache({"jesus_made": 694361})

    assert stats.resolve_mlbam_id("jesus_made", "Jesus Made") == 694361
    assert no_resolvers == [], "a cached hit must never trigger re-resolution"


def test_miss_stamp_is_cleared_once_resolved(isolated_cache, monkeypatch):
    """A player who resolves later must not keep a stale miss stamp around."""
    stats._save_id_cache({"late_bloomer": None})
    stats._record_miss("late_bloomer")
    assert stats._miss_is_fresh("late_bloomer")

    # Expire it, then let the API path succeed on the retry.
    (isolated_cache / "mlbam_id_misses.json").write_text(
        json.dumps({"late_bloomer": time.time() - 99 * 86400}))
    monkeypatch.setattr(stats.PlayerIndex, "load_or_build",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("no index"))))
    monkeypatch.setattr(stats, "_search_mlbam_via_api", lambda name: (800604, None))

    assert stats.resolve_mlbam_id("late_bloomer", "Late Bloomer") == 800604
    assert not stats._miss_is_fresh("late_bloomer")
    assert "late_bloomer" not in stats._load_miss_stamps(), (
        "the miss stamp should be dropped once the player resolves")
