# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Why does the snapshots table hold 128 'draft_signing' rows when
seed_signed_draftees() seeds 49?

test_draft_promotion.SeedSignedDraftees::test_idempotent_and_current_class_only
asserts len(rows) == first, i.e. that the TABLE equals the LAST RUN's seed count.
That invariant only holds if the eligible set never shrinks. It has shrunk, so
either:
  (a) the test encodes a wrong invariant for an accumulating table, or
  (b) 79 players carry a stale synthetic draft_signing anchor they are no longer
      eligible for, and are therefore serving a synthetic grade over whatever
      they should serve now -- a real data defect.
Which one it is depends on WHY each extra row is no longer seeded. Read-only.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage                       # noqa: E402
from draft_promotion import seed_signed_draftees   # noqa: E402


def main() -> int:
    seeded_n = seed_signed_draftees()
    con = sqlite3.connect(f"file:{Path(storage.DB_PATH)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT player_key, org, fv, snapshot_date FROM snapshots "
        "WHERE source='draft_signing' ORDER BY snapshot_date, player_key").fetchall()
    print(f"seed_signed_draftees() -> {seeded_n}    table rows -> {len(rows)}")

    by_date = {}
    for r in rows:
        by_date.setdefault(r["snapshot_date"], []).append(r)
    print("\nrows by snapshot_date (the seed re-stamps its OWN rows in place, so a"
          "\ndate that is not the newest means that row was NOT re-seeded):")
    for d in sorted(by_date):
        print(f"  {d}  n={len(by_date[d]):4d}")

    newest = max(by_date)
    stale = [r for r in rows if r["snapshot_date"] != newest]
    print(f"\nnewest stamp {newest}: {len(by_date[newest])} rows re-seeded this run")
    print(f"NOT re-seeded (stale): {len(stale)}")

    # do the stale ones have a real published anchor now, or only this synthetic one?
    if stale:
        keys = [r["player_key"] for r in stale]
        qs = ",".join("?" * len(keys))
        real = {r["player_key"] for r in con.execute(
            f"SELECT DISTINCT player_key FROM snapshots WHERE player_key IN ({qs}) "
            "AND source NOT IN ('draft_signing','performance_ingest','auto_detect') "
            "AND fv IS NOT NULL", keys)}
        print(f"  of those, {len(real)} now carry a REAL graded source "
              f"(their synthetic row is harmless, outvoted)")
        orphan = [r for r in stale if r["player_key"] not in real]
        print(f"  {len(orphan)} have NO real grade -> the stale synthetic row is "
              f"their ONLY anchor")
        for r in orphan[:15]:
            print(f"     {r['player_key']:30s} fv {r['fv']}  org {r['org']}  {r['snapshot_date']}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
