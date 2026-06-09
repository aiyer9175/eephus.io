# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Collapse duplicated FanGraphs draft-board snapshots.

The 2017-2020 FG draft CSVs sit FLAT in data/fangraphs_imports (no slug
subfolder), so draft_csv historically stamped them with date.today(): every
re-ingest on a new calendar day minted a fresh `FG <year> Draft (<today>)`
interval_label and inserted a whole duplicate board. The export reads only the
latest snapshot per source, so draft_timeseries.json was never wrong, but
draft_snapshots grew one copy of each board per ingest day.

draft_csv now pins flat-file snapshots to the CSV's mtime (stable), so no NEW
duplicates appear. This script removes the duplicates already accumulated,
keeping only the canonical mtime-dated board for each flat-imported year. It
only touches the flat-imported years (those with a loose <type>-<year>draft.csv
in the drop dir) and never the slug-folder boards (2021-2025), which already
carry real publish dates. Idempotent — a second run finds nothing to delete.

Usage:
    python tools/dedupe_draft_snapshots.py --dry-run   # report only
    python tools/dedupe_draft_snapshots.py             # apply
"""
from __future__ import annotations

import datetime
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from draft_csv import DROP_DIR, _group_flat  # noqa: E402


def _canonical_dates() -> dict[int, str]:
    """{draft_year: mtime-date-iso} for every flat <type>-<year>draft.csv set."""
    out: dict[int, str] = {}
    for grp in _group_flat(DROP_DIR):
        year = grp.get("draft_year")
        summ = grp.get("summary")
        if year and summ:
            out[year] = datetime.date.fromtimestamp(summ.stat().st_mtime).isoformat()
    return out


def main(dry_run: bool = False) -> None:
    canon = _canonical_dates()
    if not canon:
        print("no flat draft sets in the drop dir — nothing to do")
        return
    print("canonical (mtime) snapshot_date per flat-imported year:")
    for y, d in sorted(canon.items()):
        print(f"  {y}: keep {d}")

    con = sqlite3.connect(str(ROOT / "prospects.db"))
    total = 0
    for year, cdate in sorted(canon.items()):
        rows = con.execute(
            "SELECT snapshot_date, COUNT(*) c FROM draft_snapshots "
            "WHERE source='fangraphs' AND draft_year=? "
            "AND interval_label LIKE 'FG % Draft (%' AND snapshot_date != ? "
            "GROUP BY snapshot_date ORDER BY snapshot_date",
            (year, cdate),
        ).fetchall()
        n = sum(r[1] for r in rows)
        if n:
            print(f"  {year}: removing {n} duplicate rows across "
                  f"{[r[0] for r in rows]}")
            if not dry_run:
                con.execute(
                    "DELETE FROM draft_snapshots WHERE source='fangraphs' "
                    "AND draft_year=? AND interval_label LIKE 'FG % Draft (%' "
                    "AND snapshot_date != ?",
                    (year, cdate),
                )
        total += n
    if not dry_run:
        con.commit()
    con.close()
    print(f"{'DRY-RUN would delete' if dry_run else 'deleted'} {total} duplicate rows")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
