# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Archive / restore the shared game-feed cache (.cache/game_feeds/).

The feed cache is the expensive thing to (re)build on a fresh machine, clone,
or CI runner: tens of thousands of immutable `/feed/live` payloads. Because a
completed game's feed never changes, the whole cache is portable — build it
once on a populated machine, ship a single compressed archive, and restore it
anywhere to skip the cold MLB re-fetch entirely.

Usage:
    # On a machine that has already run the pipeline:
    python tools/feed_cache_archive.py archive --out feed_cache_seed.tar.gz
    python tools/feed_cache_archive.py archive --out seed.tar.xz --xz   # smaller/slower

    # On a fresh machine / CI, after fetching the archive:
    python tools/feed_cache_archive.py restore --in feed_cache_seed.tar.gz

Where to host the archive (release asset, object-storage bucket, internal
share) is a deployment choice; this tool only builds and unpacks it.

restore() skips files that already exist locally (so it never clobbers feeds
you fetched more recently) unless --force is given, and stamps restored files
with the current mtime so the run_monthly prune (mtime > ~400d) does not
immediately delete a months-old seed.
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_cache

CACHE_DIR = feed_cache.CACHE_DIR


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def archive(out_path: Path, *, use_xz: bool) -> None:
    files = sorted(CACHE_DIR.glob("*.json"))
    if not files:
        print(f"nothing to archive: {CACHE_DIR} is empty")
        return
    raw = sum(f.stat().st_size for f in files)
    mode = "w:xz" if use_xz else "w:gz"
    print(f"archiving {len(files)} feeds ({_human(raw)} raw) -> {out_path} [{mode}]")
    t0 = time.monotonic()
    with tarfile.open(out_path, mode) as tar:
        for i, f in enumerate(files, 1):
            tar.add(f, arcname=f.name)
            if i % 5000 == 0:
                print(f"  {i}/{len(files)} added ({time.monotonic() - t0:.0f}s)")
    size = out_path.stat().st_size
    print(f"done: {out_path} = {_human(size)} "
          f"({100 * size / raw:.0f}% of raw, {time.monotonic() - t0:.0f}s)")


def restore(in_path: Path, *, force: bool) -> None:
    if not in_path.exists():
        sys.exit(f"archive not found: {in_path}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    added = skipped = 0
    now = time.time()
    print(f"restoring {in_path} -> {CACHE_DIR} (force={force})")
    with tarfile.open(in_path, "r:*") as tar:
        for member in tar:
            if not member.isfile():
                continue
            # Flatten to basename only; never honor absolute/parent paths.
            name = Path(member.name).name
            if not name.endswith(".json"):
                continue
            dest = CACHE_DIR / name
            if dest.exists() and not force:
                skipped += 1
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            dest.write_bytes(src.read())
            os.utime(dest, (now, now))  # fresh mtime so the seed survives pruning
            added += 1
            if (added + skipped) % 5000 == 0:
                print(f"  {added} restored, {skipped} skipped...")
    print(f"done: {added} restored, {skipped} skipped (already present)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("archive", help="tar the local feed cache into one file")
    a.add_argument("--out", type=Path, default=Path("feed_cache_seed.tar.gz"))
    a.add_argument("--xz", action="store_true", help="use xz (smaller, much slower) instead of gzip")

    r = sub.add_parser("restore", help="unpack a feed-cache archive into .cache/game_feeds/")
    r.add_argument("--in", dest="in_path", type=Path, required=True)
    r.add_argument("--force", action="store_true", help="overwrite feeds that already exist locally")

    args = ap.parse_args()
    if args.cmd == "archive":
        archive(args.out, use_xz=args.xz)
    else:
        restore(args.in_path, force=args.force)


if __name__ == "__main__":
    main()
