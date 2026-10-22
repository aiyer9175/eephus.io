# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Build, and verify, the state-transfer bundle for the port (docs/port/PORT_RUNBOOK.md).

The repository is not the site: the seeded database, the non-refetchable part
of ``.cache/`` and the hand-dropped source CSVs live outside git. This tool
packs exactly that state, with a sha256 manifest, so the target host can be
seeded and checked file by file.

The cache rule is PORT_SPEC.md section 1.4.1: carry everything under ``.cache/``
that is NOT inside a top-level directory named in ``prune_cache.SAFE_CACHES``.
The tuple is imported, never transcribed, so a cache added to the allowlist
later changes the bundle without an edit here.

Bundle layout (``--out DIR``)::

    prospects.seed.db     VACUUM INTO copy of prospects.db (consistent, compacted)
    cache-carry.tar       .cache/ minus SAFE_CACHES, paths stored as .cache/<rel>
    data-imports.tar      gitignored hand-dropped inputs under data/ (FanGraphs and
                          Baseball America drops, data/drops/, ignored sample CSVs)
                          and the gitignored files inside published page
                          directories (collegesavant/logos/)
    served-data.tar       optional (--served-data): every other gitignored file under
                          data/, so the target can serve before its first full build
    MANIFEST.tsv          relpath, bytes, sha256 for every file inside the tars
    SHA256SUMS.txt        sha256sum -c compatible sums of the bundle files
    BUNDLE_INFO.json      git sha, date, counts and bytes per part

Usage::

    python tools/port_bundle.py --plan                       # counts only, writes nothing
    python tools/port_bundle.py --out /path/to/bundle [--served-data]
    python tools/port_bundle.py --verify /path/to/bundle/MANIFEST.tsv --root .

Read-only toward the module tree: it reads ``prospects.db`` through SQLite's
VACUUM INTO and reads ``.cache/`` and ``data/``; it writes only under ``--out``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from prune_cache import SAFE_CACHES  # noqa: E402  (imported, never transcribed)

# SAFE_CACHES means "the pruner may delete it", not "a new box can do without
# it". Two small SAFE directories hold files that registered fits pin by hash,
# measured 2026-10-22 on a clean clone seeded without them:
#   savant_mlb  expected_<side>_<season>.csv, read by prospect_statline: the
#               rebuild raised "the served fit does not reproduce the look's
#               fit: hit:xwoba" and kept the committed file;
#   milb_stats  the 2005 to 2013 season files milb_history reads cache-only
#               (FETCH_FLOOR_SEASON), pinned by efv_surrogate: 11 gate tests
#               raised "hitting sport 1 2013 drifted from its pin".
# So the port carries every SAFE directory except the four large feed caches
# below (54.7 GB of the 55.9 GB, per-game and per-player pulls that the nightly
# re-reads from StatsAPI and Savant); the rest come to about 0.8 GB.
LEAVE_BEHIND: tuple[str, ...] = ("win_prob", "statcast_metrics", "zone_metrics", "game_feeds")
ALSO_CARRY: tuple[str, ...] = tuple(d for d in SAFE_CACHES if d not in LEAVE_BEHIND)

# Hand-dropped, gitignored inputs under data/ that no build can recreate.
IMPORT_DIRS: tuple[str, ...] = (
    "data/fangraphs_imports",
    "data/baseballamerica_imports",
    "data/drops",
)
# Gitignored files under data/ that are never carried: empty strays and the
# two SQLite names the build does not read from data/.
NEVER_CARRY: frozenset[str] = frozenset({
    "data/prospects.db",
    "data/prospect_snapshots.sqlite",
})


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cache_carry_files(cache_root: Path, exclude_dirs: tuple[str, ...] = ()) -> list[Path]:
    """Every file under cache_root that is not inside a SAFE_CACHES top-level dir
    (ALSO_CARRY directories excepted: they are carried).

    exclude_dirs names further top-level directories the owner chose to leave
    behind (refetchable but slow, such as win_prob_hist); the default is none."""
    out: list[Path] = []
    if not cache_root.is_dir():
        return out
    for entry in sorted(os.scandir(cache_root), key=lambda e: e.name):
        p = Path(entry.path)
        if entry.is_dir(follow_symlinks=False):
            if entry.name in exclude_dirs:
                continue
            if entry.name in SAFE_CACHES and entry.name not in ALSO_CARRY:
                continue
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames.sort()
                for fn in sorted(filenames):
                    out.append(Path(dirpath) / fn)
        elif entry.is_file(follow_symlinks=False):
            out.append(p)
    return out


def _git_ignored_under_data(root: Path) -> list[str]:
    """Gitignored FILES under data/, as module-relative posix paths."""
    r = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--ignored",
         "--exclude-standard", "--", "data"],
        capture_output=True, text=True, check=True)
    return sorted(line.strip() for line in r.stdout.splitlines() if line.strip())


def _git_ignored_in_page_dirs(root: Path) -> list[str]:
    """Gitignored FILES inside the page directories deploy/publish_paths.txt ships.

    The rsync ships those directories whole, so a file there is served even when
    git ignores it. Measured 2026-10-22: collegesavant/logos/ (16 PNGs, 392 KB,
    ignored by the root .gitignore's `logos/` and `*.png`) is read by
    collegesavant/app.js, pitcher_app.js and team_names.js, and a clean clone
    has none of them (test_mlb_player_pages.py::test_collegesavant_logos_present)."""
    dirs = []
    manifest = root / "deploy" / "publish_paths.txt"
    if not manifest.is_file():
        return []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and (root / line).is_dir():
            dirs.append(line)
    if not dirs:
        return []
    r = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--ignored",
         "--exclude-standard", "--", *dirs],
        capture_output=True, text=True, check=True)
    return sorted(x.strip() for x in r.stdout.splitlines()
                  if x.strip() and "__pycache__" not in x)


def split_data_files(root: Path) -> tuple[list[str], list[str]]:
    """(imports, served) gitignored files; NEVER_CARRY and __pycache__ dropped.

    imports also carries the gitignored files inside published page directories."""
    imports: list[str] = list(_git_ignored_in_page_dirs(root))
    served: list[str] = []
    for rel in _git_ignored_under_data(root):
        if rel in NEVER_CARRY or "__pycache__" in rel:
            continue
        if any(rel == d or rel.startswith(d + "/") for d in IMPORT_DIRS):
            imports.append(rel)
        elif rel.startswith("data/sources/samples/"):
            imports.append(rel)
        else:
            served.append(rel)
    return imports, served


def plan(root: Path, exclude_dirs: tuple[str, ...] = ()) -> dict:
    cache_root = root / ".cache"
    carry = cache_carry_files(cache_root, exclude_dirs)
    carry_bytes = sum(p.stat().st_size for p in carry)
    imports, served = split_data_files(root)
    db = root / "prospects.db"
    vint = [p for p in carry if p.parent.name == "leaderboard_vintages"]
    return {
        "safe_caches": list(SAFE_CACHES),
        "excluded_dirs": list(exclude_dirs),
        "cache_carry_files": len(carry),
        "cache_carry_bytes": carry_bytes,
        "leaderboard_vintages": len(vint),
        "point_in_time_bundles": sum(1 for p in carry if p.parent == cache_root
                                     and p.name.startswith("proj_ml_pit_")),
        "fg_pages": sum(1 for p in carry if p.parent == cache_root
                        and p.name.startswith("fg_")),
        "data_import_files": len(imports),
        "data_import_bytes": sum((root / r).stat().st_size for r in imports),
        "served_data_files": len(served),
        "served_data_bytes": sum((root / r).stat().st_size for r in served),
        "db_bytes": db.stat().st_size if db.exists() else None,
    }


class _HashingReader:
    """File wrapper that hashes what tarfile reads, so each file is read once."""

    def __init__(self, f):
        self._f = f
        self.h = hashlib.sha256()

    def read(self, n=-1):
        chunk = self._f.read(n)
        self.h.update(chunk)
        return chunk


def _tar(out: Path, root: Path, rels: list[str], manifest) -> tuple[int, int]:
    n = b = 0
    with tarfile.open(out, "w", format=tarfile.PAX_FORMAT) as tf:
        for rel in rels:
            src = root / rel
            if not src.is_file():
                continue
            ti = tf.gettarinfo(str(src), arcname=rel)
            with open(src, "rb") as f:
                hr = _HashingReader(f)
                tf.addfile(ti, hr)
            manifest.write(f"{rel}\t{ti.size}\t{hr.h.hexdigest()}\n")
            n += 1
            b += ti.size
    return n, b


def build(root: Path, out: Path, served_data: bool, with_db: bool,
          exclude_dirs: tuple[str, ...] = ()) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    info: dict = {
        "built_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip(),
        "safe_caches": list(SAFE_CACHES),
        "excluded_dirs": list(exclude_dirs),
        "parts": {},
    }
    with open(out / "MANIFEST.tsv", "w", encoding="utf-8", newline="\n") as man:
        man.write("relpath\tbytes\tsha256\n")
        cache_rels = [p.relative_to(root).as_posix()
                      for p in cache_carry_files(root / ".cache", exclude_dirs)]
        # .cache may be a junction/symlink; relative_to works on the joined path.
        n, b = _tar(out / "cache-carry.tar", root, cache_rels, man)
        info["parts"]["cache-carry.tar"] = {"files": n, "bytes": b}
        imports, served = split_data_files(root)
        n, b = _tar(out / "data-imports.tar", root, imports, man)
        info["parts"]["data-imports.tar"] = {"files": n, "bytes": b}
        if served_data:
            n, b = _tar(out / "served-data.tar", root, served, man)
            info["parts"]["served-data.tar"] = {"files": n, "bytes": b}
    if with_db:
        seed = out / "prospects.seed.db"
        if seed.exists():
            seed.unlink()
        con = sqlite3.connect(str(root / "prospects.db"))
        try:
            con.execute("VACUUM INTO ?", (str(seed),))
        finally:
            con.close()
        con = sqlite3.connect(str(seed))
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0]
            tables = con.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        finally:
            con.close()
        info["parts"]["prospects.seed.db"] = {"bytes": seed.stat().st_size,
                                              "integrity_check": ok, "tables": tables}
    sums = []
    for name in sorted(info["parts"]) + ["MANIFEST.tsv"]:
        sums.append(f"{_sha256(out / name)}  {name}\n")
    (out / "SHA256SUMS.txt").write_text("".join(sums), encoding="utf-8", newline="\n")
    (out / "BUNDLE_INFO.json").write_text(json.dumps(info, indent=1) + "\n",
                                          encoding="utf-8", newline="\n")
    return info


def verify(manifest: Path, root: Path) -> dict:
    missing: list[str] = []
    mismatched: list[str] = []
    n = 0
    with open(manifest, encoding="utf-8") as f:
        next(f)
        for line in f:
            rel, size, digest = line.rstrip("\n").split("\t")
            n += 1
            p = root / rel
            if not p.is_file():
                missing.append(rel)
            elif p.stat().st_size != int(size) or _sha256(p) != digest:
                mismatched.append(rel)
    return {"checked": n, "missing": len(missing), "mismatched": len(mismatched),
            "missing_sample": missing[:20], "mismatched_sample": mismatched[:20],
            "ok": not missing and not mismatched}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="module root (the prospect-tracker directory)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="print counts, write nothing")
    g.add_argument("--out", type=Path, help="bundle directory to write")
    g.add_argument("--verify", type=Path, metavar="MANIFEST",
                   help="check every manifest row against --root")
    ap.add_argument("--served-data", action="store_true",
                    help="also carry the other gitignored data/ artifacts")
    ap.add_argument("--no-db", action="store_true", help="skip the database seed")
    ap.add_argument("--exclude-dir", action="append", default=[], metavar="NAME",
                    help="leave a further top-level .cache directory behind (repeatable)")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    if a.plan:
        print(json.dumps(plan(root, tuple(a.exclude_dir)), indent=1))
        return 0
    if a.verify:
        res = verify(a.verify, root)
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 1
    print(json.dumps(build(root, a.out, a.served_data, not a.no_db,
                           tuple(a.exclude_dir)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
