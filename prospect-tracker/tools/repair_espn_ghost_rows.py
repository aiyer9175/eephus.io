# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_espn_ghost_rows.py - retire duplicate-rank ESPN rows left under a
superseded player_key.

WHAT HAPPENED (found 2026-08-30 while wiring the ESPN 2026 Midseason list).
`insert_snapshots` upserts on (source, interval_label, player_key), so a
re-scrape can refresh a row but can never RETIRE one whose key the parser no
longer produces. When normalize_key started mapping "Leonardo" to "leo", the
2026-05 ingest wrote 'ESPN 2025 In-Season' rank 97 and 'ESPN 2026 Preseason'
rank 98 under leo_bernal while the older rows for the same rank, same FV, same
date stayed under leonardo_bernal (ids 926475 and 1598826). Both intervals hold
101 rows for a 100-row list. The identity layer merges the two keys at build
time and the OLDER row wins the same-date dedup, so the served ESPN preseason
writeup for Bernal was still the pre-2026-08-30 parse with its header leak
("98. Leonardo Bernal , C, St. Louis Cardinals Age: 21 | Bats: ..."), and every
future parser improvement would keep losing to it.

THE RULE. Within one ESPN interval, for every rank that appears more than
once, keep the row whose player_key equals normalize_key(player_name) (the
current key convention) and retire the others ONLY when they carry the same
FV and the same snapshot_date (a true ghost of the same list line). Anything
else is left alone and reported: two different humans at one rank would be a
parser bug, not a ghost.

Dry-run by default. Must ALSO run on the deploy box (same DB lineage).

    python tools/repair_espn_ghost_rows.py            # report only
    python tools/repair_espn_ghost_rows.py --apply    # delete the ghosts
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from scrapers import normalize_key  # noqa: E402


def find_ghosts(con: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    """Return (ghosts, unresolved). A ghost is a duplicate-rank ESPN row whose
    key is not the current convention for its own name and whose (fv, date)
    match the kept row."""
    cur = con.cursor()
    dup_groups = cur.execute(
        """SELECT interval_label, rank
             FROM snapshots
            WHERE source = 'espn' AND rank IS NOT NULL
            GROUP BY interval_label, rank
           HAVING COUNT(*) > 1"""
    ).fetchall()
    ghosts: list[dict] = []
    unresolved: list[dict] = []
    for label, rank in dup_groups:
        rows = cur.execute(
            """SELECT id, player_key, player_name, fv, snapshot_date, org
                 FROM snapshots
                WHERE source = 'espn' AND interval_label = ? AND rank = ?
                ORDER BY id""",
            (label, rank),
        ).fetchall()
        keep = [r for r in rows if r[1] == normalize_key(r[2] or "")]
        if len(keep) != 1:
            unresolved.append({"label": label, "rank": rank, "rows": rows,
                               "why": f"{len(keep)} row(s) match the current key convention"})
            continue
        k = keep[0]
        for r in rows:
            if r[0] == k[0]:
                continue
            if r[3] == k[3] and r[4] == k[4]:
                ghosts.append({"id": r[0], "label": label, "rank": rank,
                               "ghost_key": r[1], "kept_key": k[1],
                               "kept_id": k[0], "fv": r[3], "date": r[4]})
            else:
                unresolved.append({"label": label, "rank": rank, "rows": rows,
                                   "why": "fv/date differ from the kept row"})
    return ghosts, unresolved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(HERE / "prospects.db"))
    ap.add_argument("--apply", action="store_true", help="delete the ghost rows")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    ghosts, unresolved = find_ghosts(con)
    print(f"{len(ghosts)} ghost row(s), {len(unresolved)} unresolved duplicate group(s)")
    for g in ghosts:
        print(f"  ghost id={g['id']} {g['label']!r} rank {g['rank']} key {g['ghost_key']} "
              f"-> kept id={g['kept_id']} key {g['kept_key']} (fv {g['fv']}, {g['date']})")
    for u in unresolved:
        print(f"  UNRESOLVED {u['label']!r} rank {u['rank']}: {u['why']}")
        for r in u["rows"]:
            print(f"      id={r[0]} key={r[1]} name={r[2]!r} fv={r[3]} date={r[4]} org={r[5]}")
    if not args.apply:
        print("dry run; re-run with --apply to delete the ghost rows")
        return 0
    if not ghosts:
        return 0
    with con:
        con.executemany("DELETE FROM snapshots WHERE id = ?", [(g["id"],) for g in ghosts])
    left = con.execute(
        """SELECT COUNT(*) FROM (SELECT interval_label, rank FROM snapshots
              WHERE source='espn' AND rank IS NOT NULL
              GROUP BY interval_label, rank HAVING COUNT(*) > 1)"""
    ).fetchone()[0]
    print(f"deleted {len(ghosts)} row(s); duplicate-rank ESPN groups remaining: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
