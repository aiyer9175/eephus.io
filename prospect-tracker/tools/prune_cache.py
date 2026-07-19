#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Bound the refetchable ``.cache/`` so a low-disk box never dies mid-build.

The nightly pipeline caches immutable game/player data (winProbability,
Statcast, zone metrics, ``/feed/live`` game feeds, Savant pulls) one file per
game or player-season, effectively forever (final games are immutable, so the
TTL is ~10 years). On a big dev disk that is fine; on a small VPS the cache
(``win_prob`` ~19 GB + ``statcast_metrics`` ~15 GB + ``zone_metrics`` ~5 GB +
...) grows without bound and eventually fills the disk. A disk-full **mid-build**
is the dangerous case: it leaves a half-written ``data/*.json`` that then poisons
the rsync'd deploy. This tool is the ops backstop that keeps that from happening.

Every directory in :data:`SAFE_CACHES` is **refetchable** from the MLB StatsAPI /
Baseball Savant, so pruning oldest-first is safe: the only cost is a slower future
run that re-pulls what it needs (a slow build beats a dead/corrupt one). The
non-refetchable ``fangraphs_imports`` live under ``data/``, never in ``.cache/``,
and directories that are backups or rate-limited scrapes (``efv_backup``,
``bref_register``, ``draft_history``) are deliberately excluded.

Two modes:

* ``--max-age-days N`` -- delete files older than N days by mtime. A steady-state
  bound you can cron independently of a build.
* ``--target-free-gb G`` -- prune globally-oldest-first across the safe caches
  until the cache filesystem has >= G GB free (or only within-floor files
  remain). This is the disk-pressure relief the deploy shell calls in its
  preflight. ``--min-keep-days`` (default 120) protects the trailing window that
  the every-night current-season exports still read, so pressure pruning never
  deletes actively-used data out from under the running build.

Always best-effort and side-effect-isolated: a permission error on one file is
skipped, never fatal.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

_log = logging.getLogger("prune_cache")

CACHE_ROOT = Path(__file__).resolve().parent.parent / ".cache"

# Refetchable game/player caches, safe to prune oldest-first. Kept explicit
# (allowlist, not "everything under .cache") so a future cache holding
# non-refetchable state is never pruned by accident.
SAFE_CACHES: tuple[str, ...] = (
    "win_prob",           # winProbability feeds (leverage / REM+); biggest
    "statcast_metrics",   # per-player Statcast pulls
    "zone_metrics",       # plate-discipline / zone pulls
    "game_feeds",         # /feed/live game feeds (also mtime-pruned by feed_cache)
    "savant_mlb",         # Baseball Savant MLB CSVs
    "savant_minors",      # Baseball Savant MiLB CSVs
    "aaa_pitches",        # AAA pitch-level pulls
    "aaa_ball_by_ball",   # AAA ball-by-ball
    "swing_pitches",      # swing+ pitch pulls
    "season_pitching",    # season pitching splits
    "milb_stats",         # bulk MiLB season stats (current season TTL-refreshed)
)

# Never pruned: backups + rate-limited/small provenance scrapes.
EXCLUDED = ("efv_backup", "bref_register", "draft_history")


def free_gb(path: Path | None = None) -> float:
    """GB free on the filesystem holding ``path`` (the cache root by default)."""
    target = path or CACHE_ROOT
    # disk_usage needs an existing path; walk up to the first that exists.
    while not target.exists() and target != target.parent:
        target = target.parent
    return shutil.disk_usage(target).free / 1e9


def _cache_files(caches=SAFE_CACHES, root: Path | None = None):
    """Yield (mtime, size, path) for every regular file in the given caches."""
    base = root or CACHE_ROOT
    for name in caches:
        d = base / name
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            try:
                if not p.is_file():
                    continue
                st = p.stat()
            except OSError:
                continue
            yield (st.st_mtime, st.st_size, p)


def cache_report(caches=SAFE_CACHES, root: Path | None = None) -> dict[str, dict]:
    """Per-cache {files, bytes} plus a _total row. For --report / diagnostics."""
    base = root or CACHE_ROOT
    out: dict[str, dict] = {}
    tot_f = tot_b = 0
    for name in caches:
        d = base / name
        f = b = 0
        if d.is_dir():
            for p in d.rglob("*"):
                try:
                    if p.is_file():
                        f += 1
                        b += p.stat().st_size
                except OSError:
                    continue
        out[name] = {"files": f, "bytes": b, "gb": round(b / 1e9, 2)}
        tot_f += f
        tot_b += b
    out["_total"] = {"files": tot_f, "bytes": tot_b, "gb": round(tot_b / 1e9, 2)}
    return out


def _unlink(p: Path, dry_run: bool) -> int:
    """Delete p, returning its byte size (0 on failure). No-op if dry_run."""
    try:
        sz = p.stat().st_size
    except OSError:
        return 0
    if dry_run:
        return sz
    try:
        p.unlink()
        return sz
    except OSError:
        return 0


def prune_by_age(max_age_days: float, caches=SAFE_CACHES, *,
                 root: Path | None = None, dry_run: bool = False) -> tuple[int, int]:
    """Delete files older than max_age_days by mtime. Returns (count, bytes)."""
    cutoff = time.time() - max_age_days * 86400
    n = freed = 0
    for mtime, _size, p in _cache_files(caches, root):
        if mtime < cutoff:
            sz = _unlink(p, dry_run)
            if sz or not p.exists():
                n += 1
                freed += sz
    if n:
        _log.info("%spruned %d files (%.2f GB) older than %.0fd",
                  "[dry-run] " if dry_run else "", n, freed / 1e9, max_age_days)
    return n, freed


def prune_to_target(target_free_gb: float, caches=SAFE_CACHES, *,
                    root: Path | None = None, min_keep_days: float = 120,
                    dry_run: bool = False) -> tuple[int, int, bool]:
    """Prune globally-oldest-first until >= target_free_gb GB free.

    Never deletes files newer than ``min_keep_days`` (the trailing window the
    every-night current-season exports still read). Returns (count, bytes,
    reached) -- ``reached=False`` means the target could not be met without
    touching protected recent files, and the caller should treat that as a real
    low-disk condition.
    """
    base = root or CACHE_ROOT
    if free_gb(base) >= target_free_gb:
        return 0, 0, True
    protect_after = time.time() - min_keep_days * 86400
    # Oldest first; skip anything inside the protected recent window.
    candidates = sorted(
        (t for t in _cache_files(caches, base) if t[0] < protect_after),
        key=lambda t: t[0],
    )
    n = freed = 0
    for _mtime, size, p in candidates:
        if free_gb(base) >= target_free_gb:
            break
        sz = _unlink(p, dry_run)
        if sz or not p.exists():
            n += 1
            freed += sz
        if dry_run:
            # free_gb won't move in a dry run; account against the estimate so
            # the loop still terminates at the projected target.
            if (free_gb(base) + freed / 1e9) >= target_free_gb:
                break
    reached = (free_gb(base) + (freed / 1e9 if dry_run else 0)) >= target_free_gb
    _log.info("%sprune-to-target %.1f GB: removed %d files (%.2f GB); free now %.1f GB; reached=%s",
              "[dry-run] " if dry_run else "", target_free_gb, n, freed / 1e9,
              free_gb(base), reached)
    return n, freed, reached


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print-free", action="store_true",
                    help="Print GB free on the cache filesystem and exit (for shell preflights).")
    ap.add_argument("--report", action="store_true",
                    help="Print per-cache size report and exit.")
    ap.add_argument("--max-age-days", type=float, default=None,
                    help="Delete cached files older than N days (steady-state bound).")
    ap.add_argument("--target-free-gb", type=float, default=None,
                    help="Prune oldest-first until this many GB are free (disk-pressure relief).")
    ap.add_argument("--min-keep-days", type=float, default=120,
                    help="Never prune files newer than this under --target-free-gb (default 120).")
    ap.add_argument("--dry-run", action="store_true", help="Report what would be removed; delete nothing.")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    if args.print_free:
        print(f"{free_gb():.1f}")
        return 0
    if args.report:
        rep = cache_report()
        for name, r in rep.items():
            print(f"  {name:20s} {r['gb']:8.2f} GB  ({r['files']} files)")
        print(f"  {'free on fs':20s} {free_gb():8.1f} GB")
        return 0

    if args.max_age_days is not None:
        prune_by_age(args.max_age_days, dry_run=args.dry_run)
    if args.target_free_gb is not None:
        _n, _b, reached = prune_to_target(
            args.target_free_gb, min_keep_days=args.min_keep_days, dry_run=args.dry_run)
        if not reached:
            _log.warning("could not reach %.1f GB free without pruning the last %.0f days "
                         "of cache; lower --min-keep-days or free disk elsewhere.",
                         args.target_free_gb, args.min_keep_days)
            return 2
    if args.max_age_days is None and args.target_free_gb is None:
        ap.error("nothing to do: pass --print-free, --report, --max-age-days, or --target-free-gb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
