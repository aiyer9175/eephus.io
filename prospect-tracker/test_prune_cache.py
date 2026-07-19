# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Tests for tools/prune_cache.py — the low-disk ops backstop."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import prune_cache  # noqa: E402


def _mk(path: Path, size: int, age_days: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))


class TestAgePrune:
    def test_prunes_only_old_files(self, tmp_path):
        _mk(tmp_path / "win_prob" / "fresh.json", 10, age_days=1)
        _mk(tmp_path / "win_prob" / "stale.json", 10, age_days=500)
        n, freed = prune_cache.prune_by_age(400, caches=("win_prob",), root=tmp_path)
        assert n == 1 and freed == 10
        assert (tmp_path / "win_prob" / "fresh.json").exists()
        assert not (tmp_path / "win_prob" / "stale.json").exists()

    def test_only_allowlisted_caches_touched(self, tmp_path):
        # A cache NOT in the requested set is never scanned/deleted.
        _mk(tmp_path / "efv_backup" / "old.db", 10, age_days=999)
        n, _ = prune_cache.prune_by_age(400, caches=("win_prob",), root=tmp_path)
        assert n == 0
        assert (tmp_path / "efv_backup" / "old.db").exists()

    def test_dry_run_deletes_nothing(self, tmp_path):
        _mk(tmp_path / "win_prob" / "stale.json", 10, age_days=500)
        n, freed = prune_cache.prune_by_age(400, caches=("win_prob",), root=tmp_path, dry_run=True)
        assert n == 1 and freed == 10
        assert (tmp_path / "win_prob" / "stale.json").exists()


class TestReport:
    def test_report_totals(self, tmp_path):
        _mk(tmp_path / "win_prob" / "a.json", 100, age_days=1)
        _mk(tmp_path / "zone_metrics" / "b.json", 50, age_days=1)
        rep = prune_cache.cache_report(caches=("win_prob", "zone_metrics"), root=tmp_path)
        assert rep["win_prob"]["bytes"] == 100
        assert rep["zone_metrics"]["bytes"] == 50
        assert rep["_total"]["bytes"] == 150
        assert rep["_total"]["files"] == 2


class TestTargetPrune:
    def test_min_keep_days_protects_recent(self, tmp_path, monkeypatch):
        # Two files: one old (prunable), one recent (protected). Force the loop
        # to believe the disk is always under target so it prunes everything it
        # is *allowed* to — the recent file must still survive the floor.
        _mk(tmp_path / "win_prob" / "old.json", 10, age_days=500)
        _mk(tmp_path / "win_prob" / "recent.json", 10, age_days=5)
        monkeypatch.setattr(prune_cache, "free_gb", lambda *a, **k: 0.0)
        n, _freed, reached = prune_cache.prune_to_target(
            999, caches=("win_prob",), root=tmp_path, min_keep_days=120)
        assert not reached  # 0 free can never reach 999
        assert not (tmp_path / "win_prob" / "old.json").exists()   # old pruned
        assert (tmp_path / "win_prob" / "recent.json").exists()    # recent protected

    def test_noop_when_already_above_target(self, tmp_path, monkeypatch):
        _mk(tmp_path / "win_prob" / "old.json", 10, age_days=500)
        monkeypatch.setattr(prune_cache, "free_gb", lambda *a, **k: 999.0)
        n, freed, reached = prune_cache.prune_to_target(
            50, caches=("win_prob",), root=tmp_path)
        assert n == 0 and freed == 0 and reached
        assert (tmp_path / "win_prob" / "old.json").exists()


def test_safe_caches_excludes_backups():
    # Guard: backups / non-refetchable scrapes must never be in the prune set.
    for name in prune_cache.EXCLUDED:
        assert name not in prune_cache.SAFE_CACHES
    assert "efv_backup" in prune_cache.EXCLUDED


class TestVersionedOrphans:
    """statcast_metrics/zone_metrics orphan prior-version files on a CACHE_VERSION
    bump; prune_versioned_orphans mtime-sweeps just those hash-keyed caches."""

    def test_prunes_old_hashed_files_keeps_fresh(self, tmp_path):
        # An orphaned prior-version file (old mtime) is reclaimed; the live
        # current-version file (recently re-written) survives the sweep.
        _mk(tmp_path / "statcast_metrics" / "oldhash.json", 10, age_days=90)
        _mk(tmp_path / "statcast_metrics" / "livehash.json", 10, age_days=1)
        _mk(tmp_path / "zone_metrics" / "oldzone.json", 10, age_days=90)
        n, freed = prune_cache.prune_versioned_orphans(30, root=tmp_path)
        assert n == 2 and freed == 20
        assert not (tmp_path / "statcast_metrics" / "oldhash.json").exists()
        assert (tmp_path / "statcast_metrics" / "livehash.json").exists()
        assert not (tmp_path / "zone_metrics" / "oldzone.json").exists()

    def test_never_touches_other_caches(self, tmp_path):
        # Only the hash-keyed caches are swept, never e.g. win_prob.
        _mk(tmp_path / "win_prob" / "old.json", 10, age_days=999)
        n, _ = prune_cache.prune_versioned_orphans(30, root=tmp_path)
        assert n == 0
        assert (tmp_path / "win_prob" / "old.json").exists()

    def test_dry_run_deletes_nothing(self, tmp_path):
        _mk(tmp_path / "statcast_metrics" / "old.json", 10, age_days=90)
        n, freed = prune_cache.prune_versioned_orphans(30, root=tmp_path, dry_run=True)
        assert n == 1 and freed == 10
        assert (tmp_path / "statcast_metrics" / "old.json").exists()

    def test_versioned_caches_are_subset_of_safe(self):
        for name in prune_cache.VERSIONED_CACHES:
            assert name in prune_cache.SAFE_CACHES


class TestScheduleCachesPrunable:
    """proj_current / fantasy_schedule accumulate one date-keyed file per day;
    they are now in SAFE_CACHES so the existing age/target sweeps evict them."""

    def test_schedule_caches_are_safe(self):
        assert "proj_current" in prune_cache.SAFE_CACHES
        assert "fantasy_schedule" in prune_cache.SAFE_CACHES

    def test_age_prune_sweeps_schedule_caches_by_default(self, tmp_path):
        _mk(tmp_path / "proj_current" / "sched_old.json", 10, age_days=90)
        _mk(tmp_path / "fantasy_schedule" / "old_R.json", 10, age_days=90)
        _mk(tmp_path / "proj_current" / "sched_today.json", 10, age_days=1)
        # Default SAFE_CACHES set now includes both schedule dirs.
        n, freed = prune_cache.prune_by_age(30, root=tmp_path)
        assert n == 2 and freed == 20
        assert (tmp_path / "proj_current" / "sched_today.json").exists()
