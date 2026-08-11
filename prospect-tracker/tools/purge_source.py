# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
purge_source.py - remove every row a named source owns, so it can be re-ingested
from scratch.

WHY THIS EXISTS. An outlet that republishes a board (a re-grade, a scale change,
a mid-cycle correction) makes the stored vintage wrong rather than stale, and
there is no upsert that fixes it: the new board can carry FEWER players, so
re-ingesting on top leaves orphan rows from the old one that nothing will ever
overwrite. The honest repair is to drop the source and re-ingest.

WHAT IT TOUCHES. Only tables carrying a literal `source` column, discovered at
runtime rather than hardcoded, so a new table cannot silently escape the purge.
Today that is `snapshots` and `draft_snapshots`.

WHAT IT DELIBERATELY DOES NOT TOUCH, and why:
  players / statlines / career_stats / metric_snapshots / player_photos
      These are keyed by player, not by source. A prospect who appears on a
      Baseball America board is not a Baseball America ROW: he is a player the
      database knows, with statlines from MLBAM and grades from several outlets.
      Deleting him because one outlet is being re-ingested would destroy data no
      other source can restore.
  consensus.PLAYER_KEY_ALIASES and scrapers._SPLIT_KEYS
      Identity decisions are source-agnostic and are what make the RE-ingest
      safe. Purging them would re-open every merge the last ingest closed.
  data/*.json artifacts
      Derived. Rebuild them after the purge; do not hand-edit.

ALWAYS BACK UP FIRST. `--backup PATH` writes every row it is about to delete as
JSON, and is the difference between a reversible purge and a destructive one.

Usage:
    python tools/purge_source.py --source baseballamerica --backup bak.json
    python tools/purge_source.py --source baseballamerica --backup bak.json --apply
    python tools/purge_source.py --source fangraphs --vintage 2026-08-02 --apply
    python tools/purge_source.py --source baseballamerica --exact --apply

`--source` matches the source and any suffixed variant of it (so
`baseballamerica` also takes `baseballamerica_statcast_by_age`), which is
usually what you want when an outlet ships more than one feed. Pass `--exact`
to match the one literal source string only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "prospects.db"


def _tables_with_source(con: sqlite3.Connection) -> list[str]:
    out = []
    for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({name})")]
        if "source" in cols:
            out.append(name)
    return sorted(out)


def purge(db_path: Path, source: str, *, apply: bool, exact: bool,
          vintage: str | None, backup: Path | None) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    match = "=" if exact else "LIKE"
    pattern = source if exact else f"{source}%"
    print(f"=== purge_source [{mode}] db={db_path} ===")
    print(f"    source {match} {pattern!r}"
          + (f"  vintage={vintage}" if vintage else "  (all vintages)"))
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    tables = _tables_with_source(con)
    print(f"    tables carrying a source column: {', '.join(tables) or '(none)'}")

    where = f"source {match} ?"
    params: list = [pattern]
    total = 0
    doomed: dict[str, list[dict]] = {}

    print("\n-- what would go --")
    for t in tables:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
        w, p = where, list(params)
        if vintage and "snapshot_date" in cols:
            w += " AND snapshot_date = ?"
            p.append(vintage)
        rows = [dict(r) for r in con.execute(
            f"SELECT * FROM {t} WHERE {w}", p)]
        if not rows:
            continue
        doomed[t] = rows
        total += len(rows)
        if "snapshot_date" in cols:
            by_v: dict[tuple, int] = {}
            for r in rows:
                by_v[(r.get("source"), r.get("snapshot_date"))] = \
                    by_v.get((r.get("source"), r.get("snapshot_date")), 0) + 1
            for (s, d), n in sorted(by_v.items(), key=lambda kv: str(kv[0][1])):
                print(f"  [{t}] {s} {d}: {n} row(s)")
        else:
            print(f"  [{t}] {len(rows)} row(s)")

    if not total:
        print("\n=== nothing matched; database unchanged ===")
        con.close()
        return 0

    if backup:
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps(doomed, indent=1, ensure_ascii=False),
                          encoding="utf-8")
        print(f"\n  [backup] {total} row(s) -> {backup}")
    elif apply:
        print("\nREFUSING: --apply without --backup. A purge you cannot undo is "
              "not a purge, it is data loss. Pass --backup PATH.")
        con.close()
        return 2

    # Players the source is the ONLY witness for. Not deleted (their players
    # row is real and other tables may reference it), but named, because after
    # the purge they carry no grade from anyone and will vanish from the board.
    if "snapshots" in doomed:
        keys = {r["player_key"] for r in doomed["snapshots"] if r.get("player_key")}
        if keys:
            qs = ",".join("?" * len(keys))
            survivors = {r[0] for r in con.execute(
                f"SELECT DISTINCT player_key FROM snapshots "
                f"WHERE player_key IN ({qs}) AND NOT ({where})",
                (*keys, pattern))}
            orphans = sorted(keys - survivors)
            print(f"\n-- {len(orphans)} player(s) lose their ONLY grade source --")
            for k in orphans[:15]:
                print(f"  [orphan] {k}")
            if len(orphans) > 15:
                print(f"  ... and {len(orphans) - 15} more")
            print("  (players rows are KEPT: they are real humans other tables "
                  "reference. They simply carry no grade until a re-ingest.)")

    if apply:
        for t in doomed:
            cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
            w, p = where, list(params)
            if vintage and "snapshot_date" in cols:
                w += " AND snapshot_date = ?"
                p.append(vintage)
            con.execute(f"DELETE FROM {t} WHERE {w}", p)
        con.commit()
        print(f"\n=== APPLIED: {total} row(s) deleted ===")
        print("    NEXT: rebuild the derived artifacts, in this order:")
        print("      python run_monthly.py --rebuild-only")
        print("      python -c \"from source_backtest import run_source_backtest as r; r(write=True)\"")
        print("      python -c \"from source_cohort_accuracy import run_source_cohort_accuracy as r; r(write=True)\"")
    else:
        con.rollback()
        print(f"\n=== DRY-RUN: {total} row(s) would be deleted; re-run with "
              "--apply ===")
    con.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Delete every row a named source owns, for re-ingest.")
    ap.add_argument("--source", required=True,
                    help="source name; matches suffixed variants unless --exact")
    ap.add_argument("--exact", action="store_true",
                    help="match the literal source string only")
    ap.add_argument("--vintage", default=None,
                    help="restrict to one snapshot_date")
    ap.add_argument("--backup", type=Path, default=None,
                    help="write the doomed rows here as JSON (required by --apply)")
    ap.add_argument("--apply", action="store_true",
                    help="write the deletion (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    return purge(args.db, args.source, apply=args.apply, exact=args.exact,
                 vintage=args.vintage, backup=args.backup)


if __name__ == "__main__":
    sys.exit(main())
