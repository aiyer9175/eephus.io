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
