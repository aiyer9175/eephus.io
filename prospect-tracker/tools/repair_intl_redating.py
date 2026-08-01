# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_intl_redating.py - stop the MLB Pipeline International board from
carrying "today" as its publication date.

THE DEFECT
----------
scrapers.MLB_INTERNATIONAL_INTERVALS stamped snapshot_date with
`date.today().isoformat()` on a FIXED interval label, and
storage.insert_snapshots' upsert does `snapshot_date = excluded.snapshot_date`.
So every monthly run re-dated all 50 rows of the 2026 international class to
whatever day the run happened to execute. Measured 2026-07-31: all 50 rows sat
at snapshot_date 2026-07-31, min == max, despite the board being unchanged.

Three consequences, all silent:

  1. POINT-IN-TIME HISTORY DESTROYED. The interval can only ever be "today",
     so the Time Machine has no international board for any earlier date.
  2. PERMANENT FRESHNESS ILLUSION. Consumers reading snapshot_date see a
     board published today, every day, whether or not MLB touched the page.
  3. YEAR-CYCLE MIGRATION. grade_normalization builds per-(source, role,
     YEAR) quantile offsets keyed on substr(snapshot_date, 1, 4). On the
     first run after New Year, the entire 2026 international class would
     have jumped into the 2027 normalization cohort and been de-biased
     against the wrong year's grader baseline - a scale change nobody asked
     for, on rows nobody re-published.

THE FIX IN CODE (already landed): scrapers.scrape_mlb_international_stable
holds the STORED date unless the parsed board's (player_key, rank, fv)
fingerprint actually changed.

WHAT THIS SCRIPT DOES
---------------------
Re-dates the already-corrupted rows to a stable publication date. The default
is {year}-01-15, which is
  * the exact convention every sibling year already uses on this same source
    ('MLB Pipeline 2021 International (2021-01-15)' through 2025), and
  * the date the international signing period opens, i.e. the real
    publication anchor for a class list.
The original per-run dates are unrecoverable (each run overwrote the last),
so a consistent, era-correct, machine-independent anchor is the best
available truth. Use --date to override.

THIS MOVES SERVED NUMBERS. Consensus events are keyed on snapshot_date, so
re-dating 50 international rows from 2026-07-31 to 2026-01-15 moves those
players' consensus event dates (and their forward-fill ordering against other
sources). The row COUNT, ranks and FVs are untouched. The script prints the
affected players before writing.

Usage:
    python tools/repair_intl_redating.py                     # dry run
    python tools/repair_intl_redating.py --apply             # write (backs up)
    python tools/repair_intl_redating.py --apply --no-backup
    python tools/repair_intl_redating.py --date 2026-01-15
    python tools/repair_intl_redating.py --label 'MLB Pipeline 2026 International'
    python tools/repair_intl_redating.py --db PATH

Run it on EVERY box that owns a prospects.db (dev AND the deploy box).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = _HERE.parent / "prospects.db"

SOURCE = "mlb_pipeline_international"
DEFAULT_LABEL = "MLB Pipeline 2026 International"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true",
                    help="Write the repair. Without this the script only reports.")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip the pre-write .bak copy (the DB is 1.4GB).")
    ap.add_argument("--label", default=DEFAULT_LABEL)
    ap.add_argument("--date", default=None,
                    help="Stable snapshot_date to write. Default {year}-01-15 "
                         "derived from the label's year, matching the 2021-2025 "
                         "sibling intervals on this source.")
    args = ap.parse_args()

    if not args.db.exists():
        print(f"ERROR: no database at {args.db}")
        return 2

    m = re.search(r"(20\d{2})", args.label)
    if not m and not args.date:
        print(f"ERROR: cannot derive a year from label {args.label!r}; pass --date")
        return 2
    target = args.date or f"{m.group(1)}-01-15"
    if not _DATE_RE.match(target):
        print(f"ERROR: --date {target!r} is not YYYY-MM-DD")
        return 2

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT player_key, player_name, rank, fv, snapshot_date "
        "FROM snapshots WHERE source = ? AND interval_label = ? "
        "ORDER BY rank IS NULL, rank", (SOURCE, args.label)).fetchall()

    print(f"db: {args.db}")
    print(f"interval: {args.label!r} on source {SOURCE!r}")
    print(f"rows: {len(rows)}")
    if not rows:
        print("nothing to repair")
        return 0
    dates = sorted({r["snapshot_date"] for r in rows})
    print(f"snapshot_date on file: {dates} "
          f"({'SINGLE value - consistent with the re-dating defect' if len(dates) == 1 else 'MIXED'})")
    print(f"target snapshot_date : {target}")
    print()

    stale = [r for r in rows if r["snapshot_date"] != target]
    if not stale:
        print("already stable at the target date - nothing to do")
        return 0

    # Sibling intervals on the same source, for the convention check.
    sibs = con.execute(
        "SELECT interval_label, MIN(snapshot_date) d, COUNT(*) n FROM snapshots "
        "WHERE source = ? AND interval_label <> ? GROUP BY interval_label "
        "ORDER BY d", (SOURCE, args.label)).fetchall()
    if sibs:
        print("sibling intervals on this source (the dating convention):")
        for s in sibs:
            print(f"    {s['d']}  {s['n']:>3} rows  {s['interval_label']}")
        print()

    print(f"PLAN: re-date {len(stale)} rows -> {target}")
    for r in stale[:60]:
        # rank / fv are nullable on this source (Pipeline publishes the
        # international list rank-only for some entries).
        print(f"    #{str(r['rank']):>4} fv {str(r['fv']):>5}  {r['player_name']}"
              f"   {r['snapshot_date']} -> {target}")
    if len(stale) > 60:
        print(f"    ... and {len(stale) - 60} more")
    print()
    print("BLAST RADIUS: consensus events key on snapshot_date, so these "
          "players' consensus event dates move. Ranks and FVs are untouched.")
    print()

    if not args.apply:
        print("DRY RUN - nothing written. Re-run with --apply to repair.")
        return 0

    if not args.no_backup:
        bak = args.db.with_suffix(f".db.bak-intldate-{int(time.time())}")
        print(f"backing up -> {bak} ...", flush=True)
        shutil.copy2(args.db, bak)

    with con:
        cur = con.execute(
            "UPDATE snapshots SET snapshot_date = ? "
            "WHERE source = ? AND interval_label = ? AND snapshot_date <> ?",
            (target, SOURCE, args.label, target))
    print(f"APPLIED: re-dated {cur.rowcount} rows")
    after = sorted({r[0] for r in con.execute(
        "SELECT DISTINCT snapshot_date FROM snapshots "
        "WHERE source = ? AND interval_label = ?", (SOURCE, args.label))})
    print(f"verify: snapshot_date now {after}")
    print()
    print("The scraper now HOLDS this date (scrapers."
          "scrape_mlb_international_stable) and only advances it when the")
    print("board's (player_key, rank, fv) fingerprint changes.")
    print("NEXT: rebuild to publish - python run_monthly.py --daily")
    return 0


if __name__ == "__main__":
    sys.exit(main())
