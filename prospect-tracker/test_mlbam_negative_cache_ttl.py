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


class _FakeIndex:
    """Minimal PlayerIndex stand-in: knows one player."""
    players: list = []

    def best_match(self, name, position=None, player_key=None):
        return ({"id": 800604, "birthDate": "2004-01-01"}
                if name == "Roch Cholowsky" else None)


@pytest.fixture
def fake_index(monkeypatch):
    monkeypatch.setattr(stats.PlayerIndex, "load_or_build",
                        staticmethod(lambda *a, **k: _FakeIndex()))
    monkeypatch.setattr(stats, "_cached_id_matches_request",
                        lambda *a, **k: True)
    monkeypatch.setattr(stats, "_search_mlbam_via_api", lambda name: (None, None))
    return _FakeIndex()


def test_bulk_resolver_honours_the_negative_ttl(isolated_cache, fake_index):
    """THE PRODUCTION PATH.

    run_monthly resolves ids ONLY through bulk_resolve_ids; the per-player
    resolve_mlbam_id loop was removed for performance (run_monthly.py:3201).
    So fixing the TTL in resolve_mlbam_id alone left the pipeline still
    skipping every null-cached draftee - the fix would have been dead code
    exactly where it was needed.
    """
    stats._save_id_cache({"roch_cholowsky": None})   # unstamped, pre-TTL entry

    ids, _bds, _idx = stats.bulk_resolve_ids([("roch_cholowsky", "Roch Cholowsky", "SS")])

    assert ids.get("roch_cholowsky") == 800604, (
        "bulk_resolve_ids must retry an expired negative cache entry; a null "
        "written at draft ingest otherwise starves the player forever")


def test_bulk_resolver_respects_a_fresh_miss(isolated_cache, fake_index):
    """The other half: a miss recorded moments ago must not be re-queried, or
    every run would hammer the people-search fallback for thousands of keys."""
    stats._save_id_cache({"roch_cholowsky": None})
    stats._record_miss("roch_cholowsky")

    ids, _bds, _idx = stats.bulk_resolve_ids([("roch_cholowsky", "Roch Cholowsky", "SS")])

    assert "roch_cholowsky" not in ids, "a fresh miss should still short-circuit"


def test_bulk_resolver_stamps_the_misses_it_writes(isolated_cache, fake_index):
    """Without stamping, the expiry check would re-query every cached miss on
    every run instead of once per NEG_ID_CACHE_TTL_DAYS."""
    stats._save_id_cache({})

    stats.bulk_resolve_ids([("nobody_at_all", "Nobody At All", None)])

    assert stats._miss_is_fresh("nobody_at_all"), (
        "bulk_resolve_ids wrote a null without stamping it")


def test_miss_stamp_is_cleared_once_resolved(isolated_cache, monkeypatch):
    """A player who resolves later must not keep a stale miss stamp around.

    The stand-in id is deliberately OUT OF RANGE (9,000,000+). This test used
    800604, which was fictional when written and became Roch Cholowsky's real
    id once the 2026 draft class was bound into player_photos - at which point
    the slug-collision guard correctly refused to rebind a durable id to a
    made-up key, and the test failed for a reason that had nothing to do with
    the TTL it exists to check. A fake id has to stay fake.
    """
    fake_id = 9_000_001
    stats._save_id_cache({"late_bloomer": None})
    stats._record_miss("late_bloomer")
    assert stats._miss_is_fresh("late_bloomer")

    # Expire it, then let the API path succeed on the retry.
    (isolated_cache / "mlbam_id_misses.json").write_text(
        json.dumps({"late_bloomer": time.time() - 99 * 86400}))
    monkeypatch.setattr(stats.PlayerIndex, "load_or_build",
                        staticmethod(lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("no index"))))
    monkeypatch.setattr(stats, "_search_mlbam_via_api", lambda name: (fake_id, None))

    assert stats.resolve_mlbam_id("late_bloomer", "Late Bloomer") == fake_id
    assert not stats._miss_is_fresh("late_bloomer")
    assert "late_bloomer" not in stats._load_miss_stamps(), (
        "the miss stamp should be dropped once the player resolves")
