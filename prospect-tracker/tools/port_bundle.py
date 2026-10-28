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

THE SERVED BUNDLE (port Strategy D, docs/port/PORT_BUNDLE.md). The second job of
this tool: freeze what the site serves, so the box only publishes it::

    python tools/port_bundle.py --plan-served                 # counts only
    python tools/port_bundle.py --served-bundle OUT_ROOT [--no-strip] [--no-slim] [--keep 2]
    python tools/port_bundle.py --verify-served OUT_ROOT/<bundle-id>

``--served-bundle`` writes ``OUT_ROOT/<bundle-id>/``::

    site/                 the webroot image: every page and asset directory of
                          deploy/publish_paths.txt and every payload the
                          nightly rsync ships (data/*.json and data/*.js at
                          depth one minus deploy/data_exclude.txt, plus the
                          per-player directories), the set computed by
                          port_equivalence.page_files and payload_files, with
                          the nightly's two publish-time comment strips applied
                          (--no-strip ships the sources), minus the
                          SLIM_EXCLUDE payloads nothing fetches (--no-slim
                          keeps them), plus
                          site/data/bundle_info.json (bundle id, built_at)
    MANIFEST.tsv          relpath (under site/), bytes, sha256 for every file
    SHA256SUMS            the same sums in ``sha256sum -c`` form, so the box
                          verifies with coreutils and no Python
    BUNDLE.json           bundle id, git sha, counts, bytes, the withheld names,
                          the strip outcome per file, the MANIFEST.tsv sha256
    READY                 written last: "<bundle-id><TAB><MANIFEST.tsv sha256>"

The bundle id is ``<UTC build time YYYYMMDDTHHMMSSZ>-<12 hex of the content
sha256>``, so ids sort by build time and two builds of the same bytes share a
content suffix. The box's receive step may add exactly one file the manifest
does not list, site/data/bundle_receipt.json (received_at), which the
36-hour heartbeat reads (tools/port_live_check.py --heartbeat). The publisher's
own heartbeat, data/build_info.json, never travels in a bundle.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
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


# --------------------------------------------------------------------------- #
# The served bundle (port Strategy D)
# --------------------------------------------------------------------------- #
BUNDLE_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{12}$")
BUNDLE_INFO = "data/bundle_info.json"      # written into every served bundle
RECEIPT = "data/bundle_receipt.json"       # the one file the receiver may add
# The publisher's own heartbeat: written on the box at publish time, never shipped.
PUBLISHER_FILES: frozenset[str] = frozenset({"data/build_info.json"})


def _withheld_names(root: Path) -> list[str]:
    path = root / "deploy" / "data_exclude.txt"
    if not path.is_file():
        return []
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


# --------------------------------------------------------------------------- #
# Bundle slimming (port Stage 2 prep, 2026-10-27)
# --------------------------------------------------------------------------- #
# Served payloads that nothing on the site fetches: no page, asset or script in
# the page set names the file, its stem as a quoted string or a numbered
# prefix of it, no other served depth-one payload names it (a registry row a
# page might render as a link), the Go server's sidecar table does not read
# it, and a headless crawl of every page of the served worktree requested
# none of them (docs/port/PORT_BUNDLE.md section 9). They stay in the local
# tree and in the nightly rsync's set (port_equivalence.payload_files is
# unchanged); only the served bundle leaves them out. build_served refuses to
# build when something served has started to name one (slim_violations), so a
# page that begins fetching one fails the build instead of a 404 on the box.
_INPUT = "a hand-edited or fetched pipeline input; exporters fold it into served files"
_LAB = "a lab, gate or evaluation record; no page reads it"
_LEDGER = "a pipeline ledger; no page reads it"
_RENDERED = "build_site.build_model_updates renders it into /models/updates/ at build time"
_STRAY = "no code in this tree writes or reads it; no page reads it"
SLIM_EXCLUDE: dict[str, str] = {
    "data/_am_crossmodel_map.json":             _STRAY,
    "data/_av_agelevel_verify.json":            _LAB,
    "data/_c_agenorms.json":                    _LAB,
    "data/arb_blast_bound.json":                _LAB,
    "data/arb_mde_floor.json":                  _LAB,
    "data/arb_source_urls.json":                _INPUT,
    "data/college_source_probe.json":           _LAB,
    "data/collegesavant_team_map.json":         _INPUT,
    "data/contract_overrides.json":             _INPUT,
    "data/debut_redates.json":                  _INPUT,
    "data/draft_bonus_slot.json":               _INPUT,
    "data/draft_bonus_slot_report.json":        _LAB,
    "data/efv5_atlas_tools.json":               _LAB,
    "data/efv5_tracking_head.json":             _LAB,
    "data/efv_etools_reweight_weights.json":    _LAB,
    "data/efv_label_horizon_2026.json":         _LAB,
    "data/efv_surrogate_gate.json":             _LAB,
    "data/fa_overrides.json":                   _INPUT,
    "data/hof_public_benchmarks.json":          _INPUT,
    "data/intl_amateur_unmatched.json":         _LEDGER,
    "data/mlb_fielding_positions.json":         _INPUT,
    "data/model_updates.json":                  _RENDERED,
    "data/pipeline_vintages.json":              _LEDGER,
    "data/position_overrides.json":             _INPUT,
    "data/positional_shape_transfer_lab.json":  _LAB,
    "data/proj_shape_blast.json":               _LAB,
    "data/qo_history.json":                     _INPUT,
    "data/role_full_season_baselines.json":     _INPUT,
    "data/ros_talent_basis_probe.json":         _LAB,
    "data/sdr_intake_manifest.json":            _LEDGER,
    "data/tjstats_movers.json":                 _LEDGER,
    "data/venue_meta.json":                     _INPUT,
    "data/xfv_epoch2026_power_projection.json": _LAB,
    "data/xfv_ewar_label_epoch_blast.json":     _LAB,
    "data/xfv_grade_space_diag.json":           _LAB,
    "data/xfv_regen_digest.json":               _LEDGER,
    "data/xfv_regen_ledger.json":               _LEDGER,
}
# The files the webmaster's Go server reads from the bundle for its JSON
# sidecar routes (port PR 5, internal/httpserver/sidecar.go): never slimmed.
SIDECAR_FILES: frozenset[str] = frozenset({
    "data/xfv.json", "data/xfv_history.json", "data/xfv_ungraded.json",
    "data/xfv_proxy_eval.json", "data/player_links.json", "data/swing_plus.json",
    "data/stuff_plus_aaa.json", "data/photo_ctx.json", "data/draft_timeseries.json",
    "data/overseas_timeseries.json", "data/collegesavant_milb_equiv.json", "data/pal.json",
    "data/pal_prospect_watch.json", "data/timeseries.json",
    "data/hitter_leaderboards.json", "data/starter_leaderboards.json",
    "data/bullpen_leaderboards.json", "data/leverage_leaderboards.json",
    "data/hitter_history.json", "data/starter_history.json", "data/bullpen_history.json",
    "data/leverage_history.json", "data/fantasy.json", "data/mlb_projections.json",
    "data/mlb_player_detail.json", "data/trade_values.json",
})
SIDECAR_DIRS: tuple[str, ...] = ("data/pitch_plots/", "data/player_detail/")
_TEXT = (".html", ".js", ".mjs", ".css", ".json", ".txt", ".xml", ".svg")


class SlimError(RuntimeError):
    pass


def slim_violations(root: Path, exclude: dict[str, str] | None = None) -> dict[str, str]:
    """Each excluded payload present in this tree that something served now
    names, with what names it: a page-set file (its file name, its stem
    quoted, or a numbered prefix of it), another served depth-one payload (its
    file name), or the Go server's sidecar table. Empty is the precondition of
    a slimmed build."""
    import port_equivalence as pe
    exclude = SLIM_EXCLUDE if exclude is None else exclude
    live = {r for r in exclude if (root / r).is_file()}
    if not live:
        return {}
    out: dict[str, str] = {}
    for r in sorted(live):
        if r in SIDECAR_FILES or r.startswith(SIDECAR_DIRS):
            out[r] = "the Go server's sidecar table"
    names = {r.split("/", 1)[1]: r for r in live}
    stems = {n.rsplit(".", 1)[0]: r for n, r in names.items()}
    prefixes = {}
    for st, r in stems.items():
        pre = re.sub(r"\d+$", "", st)
        if pre != st and len(pre) >= 4:
            prefixes[pre] = r
    by_name = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))
    by_stem = re.compile(r"""['"`](""" + "|".join(re.escape(x) for x in sorted(stems, key=len, reverse=True))
                         + r""")['"`]""")
    by_prefix = re.compile("|".join(re.escape(x) for x in sorted(prefixes, key=len, reverse=True))) \
        if prefixes else None
    for rel in pe.page_files(root):
        p = root / rel
        if p.suffix.lower() not in _TEXT:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in set(by_name.findall(text)):
            out.setdefault(names[m], rel)
        for m in set(by_stem.findall(text)):
            out.setdefault(stems[m], rel)
        if by_prefix is not None:
            for m in set(by_prefix.findall(text)):
                out.setdefault(prefixes[m], rel + " (numbered prefix)")
    for rel in pe.payload_files(root):
        if rel.count("/") != 1 or rel in live:
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for m in set(by_name.findall(text)):
            out.setdefault(names[m], rel)
    return dict(sorted(out.items()))


def served_files(root: Path, slim: bool = False) -> list[str]:
    """Webroot-relative paths the nightly rsync would publish from this tree,
    and with slim=True the served bundle's set: the same minus SLIM_EXCLUDE.

    The set is port_equivalence's (imported, never transcribed), so the bundle,
    the Gate C snapshot and deploy/nightly-build.sh's include lines agree."""
    import port_equivalence as pe
    rels = set(pe.page_files(root)) | set(pe.payload_files(root))
    if slim:
        rels -= set(SLIM_EXCLUDE)
    return sorted(r for r in rels
                  if r not in PUBLISHER_FILES and r not in (RECEIPT, BUNDLE_INFO))


def plan_served(root: Path, slim: bool = True) -> dict:
    rels = served_files(root, slim=slim)
    by_top: dict[str, list[int]] = {}
    for r in rels:
        parts = r.split("/")
        top = parts[0] if parts[0] != "data" else (
            "data/" + parts[1] if len(parts) > 2 else "data (depth one)")
        n_b = by_top.setdefault(top, [0, 0])
        n_b[0] += 1
        n_b[1] += (root / r).stat().st_size
    left = sorted(r for r in SLIM_EXCLUDE if (root / r).is_file()) if slim else []
    return {"files": len(rels), "bytes": sum(v[1] for v in by_top.values()),
            "slimmed": {"files": len(left), "bytes": sum((root / r).stat().st_size for r in left)},
            "by_top": {k: {"files": v[0], "bytes": v[1]} for k, v in sorted(by_top.items())}}


def apply_strips(site: Path) -> dict[str, str]:
    """The nightly's publish-time comment strips, on the bundle's copies, fail-open."""
    import strip_asset_comments as sac
    import strip_prospx_comments as spc
    out: dict[str, str] = {}
    page = site / "prospx" / "index.html"
    if page.is_file():
        try:
            with contextlib.redirect_stdout(sys.stderr):
                rc = spc.main([str(page), "--in-place"])
            out["prospx/index.html"] = "stripped" if rc == 0 else f"kept: exit {rc}"
        except Exception as exc:  # fail-open, as deploy/nightly-build.sh is
            out["prospx/index.html"] = f"kept: {exc!r}"
    try:
        for row in sac.run(site):
            out[row["file"]] = row["status"]
    except Exception as exc:
        out["assets"] = f"kept: {exc!r}"
    return out


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def build_served(root: Path, out_root: Path, strip: bool = True,
                 now: _dt.datetime | None = None, strips=apply_strips,
                 slim: bool = True) -> dict:
    """Freeze the served set into OUT_ROOT/<bundle-id>/ and return BUNDLE.json.

    slim=True (the default) leaves SLIM_EXCLUDE out, after slim_violations
    shows nothing served names any of it; a violation raises SlimError and
    writes nothing."""
    if slim:
        bad = slim_violations(root)
        if bad:
            raise SlimError("the slimming list names files something served now reads: "
                            + json.dumps(bad) + "; drop them from SLIM_EXCLUDE")
    now = (now or _dt.datetime.now(_dt.timezone.utc)).astimezone(_dt.timezone.utc)
    out_root.mkdir(parents=True, exist_ok=True)
    stage = out_root / f".building-{os.getpid()}"
    if stage.exists():
        shutil.rmtree(stage)
    site = stage / "site"
    rels = served_files(root, slim=slim)
    slimmed = sorted(r for r in SLIM_EXCLUDE if (root / r).is_file()) if slim else []
    for rel in rels:
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    strip_rows = strips(site) if strip else {}
    rows = [(rel, (site / rel).stat().st_size, _sha256(site / rel)) for rel in rels]
    content = hashlib.sha256("".join(f"{r}\t{b}\t{s}\n" for r, b, s in rows)
                             .encode("utf-8")).hexdigest()
    bundle_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{content[:12]}"
    git_sha = _git(root, "rev-parse", "HEAD")
    built_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    total = sum(b for _, b, _ in rows)
    (site / BUNDLE_INFO).parent.mkdir(parents=True, exist_ok=True)
    (site / BUNDLE_INFO).write_text(json.dumps({
        "bundle_id": bundle_id, "built_at": built_at, "git_sha": git_sha,
        "content_sha256": content, "files": len(rows), "bytes": total,
    }, indent=1) + "\n", encoding="utf-8", newline="\n")
    rows.append((BUNDLE_INFO, (site / BUNDLE_INFO).stat().st_size, _sha256(site / BUNDLE_INFO)))
    rows.sort()
    with open(stage / "MANIFEST.tsv", "w", encoding="utf-8", newline="\n") as man:
        man.write("relpath\tbytes\tsha256\n")
        man.writelines(f"{r}\t{b}\t{s}\n" for r, b, s in rows)
    with open(stage / "SHA256SUMS", "w", encoding="utf-8", newline="\n") as sums:
        sums.writelines(f"{s}  site/{r}\n" for r, _, s in rows)
    manifest_sha = _sha256(stage / "MANIFEST.tsv")
    by_top: dict[str, int] = {}
    for r, _, _ in rows:
        top = r.split("/")[0] if not r.startswith("data/") or r.count("/") == 1 \
            else "data/" + r.split("/")[1]
        by_top[top] = by_top.get(top, 0) + 1
    info = {
        "bundle_id": bundle_id, "built_at": built_at, "git_sha": git_sha,
        "git_dirty": bool(_git(root, "status", "--porcelain", "-uno")),
        "source_root": str(root), "content_sha256": content,
        "manifest_sha256": manifest_sha, "files": len(rows),
        "bytes": sum(b for _, b, _ in rows), "files_by_top": dict(sorted(by_top.items())),
        "strip": strip, "strips": strip_rows,
        "withheld": _withheld_names(root),
        "left_out": sorted(PUBLISHER_FILES), "receipt": RECEIPT,
        "slim": slim, "slimmed": slimmed,
    }
    (stage / "BUNDLE.json").write_text(json.dumps(info, indent=1) + "\n",
                                       encoding="utf-8", newline="\n")
    (stage / "READY").write_text(f"{bundle_id}\t{manifest_sha}\n",
                                 encoding="utf-8", newline="\n")
    final = out_root / bundle_id
    if final.exists():
        shutil.rmtree(final)
    os.replace(stage, final)
    info["path"] = str(final)
    return info


def verify_served(bundle: Path) -> dict:
    """Every manifest row present with its bytes and sha256, nothing extra but
    the receipt, no withheld name, and READY, BUNDLE.json and the manifest agree."""
    site = bundle / "site"
    res: dict = {"bundle": str(bundle), "checked": 0}
    problems: list[str] = []
    info_p, ready_p, man_p = bundle / "BUNDLE.json", bundle / "READY", bundle / "MANIFEST.tsv"
    for p in (info_p, ready_p, man_p):
        if not p.is_file():
            problems.append(f"{p.name} is missing")
    if problems:
        res.update(ok=False, problems=problems)
        return res
    info = json.loads(info_p.read_text(encoding="utf-8"))
    res["bundle_id"] = bundle_id = info.get("bundle_id")
    manifest_sha = _sha256(man_p)
    ready = ready_p.read_text(encoding="utf-8").strip().split("\t")
    if ready != [bundle_id, manifest_sha]:
        problems.append("READY does not name this bundle id and manifest sha256")
    if info.get("manifest_sha256") != manifest_sha:
        problems.append("BUNDLE.json manifest_sha256 differs from MANIFEST.tsv")
    if not BUNDLE_ID_RE.match(str(bundle_id)):
        problems.append(f"bundle id {bundle_id!r} is not <YYYYMMDDTHHMMSSZ>-<12 hex>")
    if BUNDLE_ID_RE.match(bundle.name) and bundle.name != bundle_id:
        problems.append(f"directory {bundle.name} holds bundle {bundle_id}")
    missing: list[str] = []
    mismatched: list[str] = []
    listed: set[str] = set()
    with open(man_p, encoding="utf-8") as f:
        next(f)
        for line in f:
            rel, size, digest = line.rstrip("\n").split("\t")
            listed.add(rel)
            p = site / rel
            if not p.is_file():
                missing.append(rel)
            elif p.stat().st_size != int(size) or _sha256(p) != digest:
                mismatched.append(rel)
    res["checked"] = len(listed)
    present = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()} \
        if site.is_dir() else set()
    extra = sorted(present - listed - {RECEIPT})
    withheld = sorted(f"data/{n}" for n in info.get("withheld", [])
                      if f"data/{n}" in present)
    left_out = sorted(r for r in info.get("left_out", []) if r in present)
    try:
        bi = json.loads((site / BUNDLE_INFO).read_text(encoding="utf-8"))
        if bi.get("bundle_id") != bundle_id:
            problems.append("site/data/bundle_info.json names another bundle")
    except (OSError, ValueError):
        problems.append("site/data/bundle_info.json is missing or unreadable")
    res.update(missing=len(missing), mismatched=len(mismatched), extra=len(extra),
               withheld_present=withheld, left_out_present=left_out,
               missing_sample=missing[:20], mismatched_sample=mismatched[:20],
               extra_sample=extra[:20], problems=problems)
    res["ok"] = not (missing or mismatched or extra or withheld or left_out or problems)
    return res


def prune_served(out_root: Path, keep: int, protect: str | None = None) -> list[str]:
    """Delete all but the newest `keep` bundles (and stale staging dirs)."""
    if keep <= 0 or not out_root.is_dir():
        return []
    ids = sorted(p.name for p in out_root.iterdir()
                 if p.is_dir() and BUNDLE_ID_RE.match(p.name))
    doomed = [i for i in ids[:-keep] if i != protect]
    doomed += [p.name for p in out_root.iterdir()
               if p.is_dir() and p.name.startswith(".building-")
               and p.name != f".building-{os.getpid()}"]
    for name in doomed:
        shutil.rmtree(out_root / name, ignore_errors=True)
    return doomed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="module root (the prospect-tracker directory)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="print counts, write nothing")
    g.add_argument("--out", type=Path, help="bundle directory to write")
    g.add_argument("--verify", type=Path, metavar="MANIFEST",
                   help="check every manifest row against --root")
    g.add_argument("--plan-served", action="store_true",
                   help="count the served bundle's files, write nothing")
    g.add_argument("--served-bundle", type=Path, metavar="OUT_ROOT",
                   help="write the served bundle to OUT_ROOT/<bundle-id>/")
    g.add_argument("--verify-served", type=Path, metavar="BUNDLE_DIR",
                   help="verify a served bundle against its own manifest")
    ap.add_argument("--no-strip", action="store_true",
                    help="served bundle: ship the sources, skip the comment strips")
    ap.add_argument("--no-slim", action="store_true",
                    help="served bundle: keep the payloads SLIM_EXCLUDE leaves out")
    ap.add_argument("--keep", type=int, default=2,
                    help="served bundle: bundles to keep under OUT_ROOT (0 keeps all)")
    ap.add_argument("--served-data", action="store_true",
                    help="also carry the other gitignored data/ artifacts")
    ap.add_argument("--no-db", action="store_true", help="skip the database seed")
    ap.add_argument("--exclude-dir", action="append", default=[], metavar="NAME",
                    help="leave a further top-level .cache directory behind (repeatable)")
    a = ap.parse_args(argv)
    root = a.root.resolve()
    if a.plan_served:
        print(json.dumps(plan_served(root, slim=not a.no_slim), indent=1))
        return 0
    if a.served_bundle:
        out_root = a.served_bundle.resolve()
        try:
            info = build_served(root, out_root, strip=not a.no_strip, slim=not a.no_slim)
        except SlimError as exc:
            print(f"!!! port bundle: {exc}", file=sys.stderr)
            return 1
        res = verify_served(Path(info["path"]))
        info["verify"] = {k: res[k] for k in ("checked", "ok", "problems")}
        info["pruned"] = prune_served(out_root, a.keep, protect=info["bundle_id"]) \
            if res["ok"] else []
        print(json.dumps({k: v for k, v in info.items() if k != "strips"}, indent=1))
        return 0 if res["ok"] else 1
    if a.verify_served:
        res = verify_served(a.verify_served.resolve())
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 1
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
