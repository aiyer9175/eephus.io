# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Delete the 2021-2026 FanGraphs draft-board leak from MiLB `snapshots`.

The FG draft boards (interval_label '2021draft' .. '2026draft') were ingested
into the MiLB `snapshots` table alongside the real org lists, leaking ~936
org-less rows (org IS NULL, status 'active') that were never MiLB snapshots at
all — they are draft-board rows that belong only in `draft_snapshots`. A seed
guard + regression test already pin NEW leaks (post-2026-06-01); this one-shot
removes the pre-existing rows.

The delete is the pre-registered one-liner:

    DELETE FROM snapshots
    WHERE source='fangraphs' AND interval_label GLOB '20[0-9][0-9]draft'

Safety rails:
  * dry-run by default — prints per-label counts + sample rows, changes nothing;
  * --apply requires a fresh backup of the DB (pass --backup PATH, or drop a
    copy named <db>.backup* / <db>.bak* next to the DB, mtime < 24h);
  * preflight asserts every matched row is org-less (the leak signature) and
    that the count sits near the expected ~936 (override with --expect);
  * runs inside a single transaction; post-apply recount must be 0;
  * idempotent — a second run finds nothing to delete and exits 0.

No other table references these rows (the DB has no foreign keys;
tjstats_snapshots.snapshot_id is a TJStats-internal id, not a snapshots.id).
The eFV dataset reads MiLB snapshots, so xfv.json rowcounts may shift on the
next rebuild — restamp the production golden after the serial phase.

Usage:
    python tools/delete_draft_board_leak.py                  # dry-run (default)
    python tools/delete_draft_board_leak.py --apply --backup prospects.db.backup-20260716
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEAK_WHERE = "source='fangraphs' AND interval_label GLOB '20[0-9][0-9]draft'"
DELETE_SQL = f"DELETE FROM snapshots WHERE {LEAK_WHERE}"
EXPECTED_ROWS = 936          # verified 2026-07-16 on the dev DB
COUNT_TOLERANCE = 0.25       # abort when count strays >25% from expected
MAX_BACKUP_AGE_HOURS = 24.0
MIN_BACKUP_SIZE_RATIO = 0.5  # a real backup of this DB can't be tiny


def _backup_hint(db_path: Path) -> str:
    stamp = date.today().strftime("%Y%m%d")
    dst = f"{db_path.name}.backup-{stamp}"
    return (
        "make one from the DB directory with either:\n"
        f'  sqlite3 {db_path.name} ".backup \'{dst}\'"\n'
        "or (no sqlite3 CLI needed):\n"
        f"  python -c \"import sqlite3; s=sqlite3.connect('{db_path.name}'); "
        f"d=sqlite3.connect('{dst}'); s.backup(d); d.close(); s.close()\""
    )


def find_fresh_backup(db_path: Path, explicit: str | None) -> Path | None:
    """Return a usable backup path, or None (with reasons printed)."""
    candidates: list[Path] = []
    if explicit:
        p = Path(explicit)
        if not p.exists():
            print(f"preflight: --backup {p} does not exist")
            return None
        candidates = [p]
    else:
        for pat in (f"{db_path.name}.backup*", f"{db_path.name}.bak*"):
            candidates.extend(db_path.parent.glob(pat))
        if not candidates:
            print(f"preflight: no {db_path.name}.backup* / .bak* file found next to the DB")
            return None
    db_size = db_path.stat().st_size
    now = time.time()
    for p in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
        age_h = (now - p.stat().st_mtime) / 3600.0
        if age_h > MAX_BACKUP_AGE_HOURS:
            print(f"preflight: {p.name} is {age_h:.1f}h old (> {MAX_BACKUP_AGE_HOURS:.0f}h) — too stale")
            continue
        if p.stat().st_size < db_size * MIN_BACKUP_SIZE_RATIO:
            print(f"preflight: {p.name} is {p.stat().st_size} bytes vs DB {db_size} — not a full backup")
            continue
        return p
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ROOT / "prospects.db"),
                    help="path to prospects.db (default: repo root)")
    ap.add_argument("--apply", action="store_true",
                    help="execute the delete (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only (the default; explicit flag for symmetry)")
    ap.add_argument("--backup", default=None,
                    help="path to a fresh backup of the DB (required with --apply)")
    ap.add_argument("--expect", type=int, default=EXPECTED_ROWS,
                    help=f"expected leak rowcount (default {EXPECTED_ROWS}); "
                         "the run aborts when the actual count strays >25%% from this")
    args = ap.parse_args(argv)
    if args.apply and args.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")
    apply = args.apply

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"no DB at {db_path} — nothing to do")
        return 1

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        # ---- scope report ------------------------------------------------
        total = con.execute(f"SELECT COUNT(*) FROM snapshots WHERE {LEAK_WHERE}").fetchone()[0]
        print(f"draft-board leak rows in snapshots: {total}")
        if total == 0:
            print("nothing to delete — the leak is already cleared (idempotent no-op)")
            return 0

        print("per interval_label:")
        for r in con.execute(
                f"SELECT interval_label, snapshot_date, status, COUNT(*) n FROM snapshots "
                f"WHERE {LEAK_WHERE} GROUP BY 1,2,3 ORDER BY 1"):
            print(f"  {r['interval_label']}  snapshot_date={r['snapshot_date']}  "
                  f"status={r['status']}  rows={r['n']}")
        print("sample rows:")
        for r in con.execute(
                f"SELECT id, interval_label, player_key, player_name, position, org, fv "
                f"FROM snapshots WHERE {LEAK_WHERE} ORDER BY interval_label, player_key LIMIT 5"):
            print(f"  id={r['id']} {r['interval_label']} {r['player_key']} "
                  f"({r['player_name']}, {r['position']}) org={r['org']} fv={r['fv']}")

        # ---- preflight assertions ---------------------------------------
        with_org = con.execute(
            f"SELECT COUNT(*) FROM snapshots WHERE {LEAK_WHERE} AND org IS NOT NULL"
        ).fetchone()[0]
        if with_org:
            print(f"ABORT: {with_org} matched rows carry an org — the GLOB is catching "
                  "rows outside the scoped org-less leak class; investigate before deleting")
            return 1
        lo = int(args.expect * (1 - COUNT_TOLERANCE))
        hi = int(args.expect * (1 + COUNT_TOLERANCE))
        if not (lo <= total <= hi):
            print(f"ABORT: count {total} is outside the expected band [{lo}, {hi}] "
                  f"(expected ~{args.expect}); re-scope or pass --expect")
            return 1
        print(f"preflight OK: {total} rows, all org-less, within expected band [{lo}, {hi}]")

        if not apply:
            print(f"\nDRY-RUN: would execute -> {DELETE_SQL}")
            print(f"DRY-RUN: would delete {total} rows; re-run with --apply (after a backup) to execute")
            return 0

        # ---- backup gate (apply only) -----------------------------------
        bkp = find_fresh_backup(db_path, args.backup)
        if bkp is None:
            print("\nABORT: --apply requires a fresh backup (<24h) of the DB;")
            print(_backup_hint(db_path))
            return 1
        print(f"backup accepted: {bkp}")

        # ---- apply inside one transaction --------------------------------
        con.execute("BEGIN IMMEDIATE")
        try:
            n = con.execute(DELETE_SQL).rowcount
            if n != total:
                raise RuntimeError(f"delete touched {n} rows, preflight counted {total}")
            remaining = con.execute(
                f"SELECT COUNT(*) FROM snapshots WHERE {LEAK_WHERE}").fetchone()[0]
            if remaining != 0:
                raise RuntimeError(f"{remaining} leak rows remain after delete")
            con.commit()
        except Exception as exc:  # noqa: BLE001 - roll back on ANY failure
            con.rollback()
            print(f"ABORT: rolled back — {exc}")
            return 1
        print(f"deleted {n} draft-board leak rows; verification recount = 0")
        print("next: rebuild exports (run_monthly rebuild-only hook) and restamp the "
              "production golden — xfv.json rowcounts may shift")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
