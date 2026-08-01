# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_jb_chimera.py - split the Just Baseball 'JB 2026 Preseason' chimera.

THE DEFECT
----------
scrapers.JB_INTERVALS pinned Just Baseball's ROLLING permalink
(justbaseball.com/prospects/top-100-mlb-prospects/) to the FIXED label
'JB 2026 Preseason' at the FIXED date 2026-03-04. JB later rewrote that same
URL to its midseason board. storage.insert_snapshots upserts on
(source, interval_label, player_key), so the June scrape:

  * OVERWROTE rank + fv on every player who appeared on both boards, and
  * INSERTED the 26 players who were new to the June board,

all under the March label and the March date. Measured 2026-07-31 the stored
interval held 126 rows with 26 DUPLICATE ranks - two #1s (Konnor Griffin
FV 70, the real March leader, next to Jesus Made FV 60 from June), two #2s,
two #3s, and so on.

WHAT THE EVIDENCE SUPPORTS
--------------------------
The June content is ALSO stored correctly, in its own interval
'JustBaseball 2026 Midseason Top 100' dated 2026-06-04. Comparing the two
intervals on the live DB:

    JB 2026 Preseason                      126 rows
    JustBaseball 2026 Midseason Top 100    100 rows
    overlap                                100 rows
      of which rank AND fv identical       100  <- June content, exact dupes
    present only in the Preseason interval  26  <- genuine March survivors

The split is therefore unambiguous and needs no guessing: a Preseason row
whose (rank, fv) EXACTLY matches its Midseason twin is June content; the 26
that have no Midseason twin are the real March list. snapshots.inserted_at
corroborates it independently (all 26 survivors carry the original
2026-05-17 ingest stamp).

WHAT THIS SCRIPT CANNOT RECOVER
-------------------------------
74 of the original 100 March rows had their rank + fv DESTROYED in place by
the upsert. Those numbers are not in the database, not in .cache (the JB
cache file has been refetched since - it now parses to the June board), and
not on JB's site (the permalink no longer serves the March list). After this
repair 'JB 2026 Preseason' honestly holds the 26 March rows that survived,
instead of dishonestly holding 126 rows of two different boards. That is the
whole available truth; inventing the other 74 would be worse than losing
them.

WHAT IT DOES
------------
For each of the 100 June-content rows in 'JB 2026 Preseason':
  * if the target interval already holds that player with the SAME rank+fv
    (all 100 of them today), DELETE the duplicate - re-labelling would
    violate UNIQUE(source, interval_label, player_key) and would add nothing;
  * otherwise RE-LABEL it into --june-label, preserving the row.
Every decision is guarded by the exact values it expects, so the script is
idempotent and refuses to touch a row that has drifted since the evidence
was taken.

Usage:
    python tools/repair_jb_chimera.py                  # dry run (default)
    python tools/repair_jb_chimera.py --apply          # write (backs up first)
    python tools/repair_jb_chimera.py --apply --no-backup
    python tools/repair_jb_chimera.py --db PATH
    python tools/repair_jb_chimera.py --march-label 'JB 2026 Preseason' \
                                      --june-label 'JustBaseball 2026 Midseason Top 100'

Run it on EVERY box that owns a prospects.db (the dev machine AND the deploy
box), because the corruption is in the database, not in the code.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = _HERE.parent / "prospects.db"

SOURCE = "just_baseball"
DEFAULT_MARCH_LABEL = "JB 2026 Preseason"
DEFAULT_JUNE_LABEL = "JustBaseball 2026 Midseason Top 100"


def _rows(con: sqlite3.Connection, label: str) -> dict[str, sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return {r["player_key"]: r for r in con.execute(
        "SELECT id, player_key, player_name, rank, fv, snapshot_date, inserted_at "
        "FROM snapshots WHERE source = ? AND interval_label = ?",
        (SOURCE, label))}


def plan(con: sqlite3.Connection, march_label: str, june_label: str) -> dict:
    march = _rows(con, march_label)
    june = _rows(con, june_label)

    delete_ids: list[tuple[int, str]] = []
    relabel_ids: list[tuple[int, str]] = []
    keep: list[str] = []
    for key, r in march.items():
        twin = june.get(key)
        if twin is None:
            keep.append(key)                      # genuine March survivor
        elif twin["rank"] == r["rank"] and twin["fv"] == r["fv"]:
            delete_ids.append((r["id"], key))     # exact June duplicate
        else:
            # A row that IS on the June board but with different numbers. Not
            # observed today (0 of 100), but if JB re-edits the midseason
            # board before this is run, that row still belongs to June, not
            # March - move it rather than delete it.
            relabel_ids.append((r["id"], key))

    dupe_ranks = _duplicate_ranks(march)
    return {"march": march, "june": june, "delete": delete_ids,
            "relabel": relabel_ids, "keep": keep, "dupe_ranks": dupe_ranks}


def _duplicate_ranks(rows: dict[str, sqlite3.Row]) -> list[int]:
    seen: dict[int, int] = {}
    for r in rows.values():
        if r["rank"] is not None:
            seen[r["rank"]] = seen.get(r["rank"], 0) + 1
    return sorted(k for k, v in seen.items() if v > 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true",
                    help="Write the repair. Without this the script only reports.")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip the pre-write .bak copy (the DB is 1.4GB).")
    ap.add_argument("--march-label", default=DEFAULT_MARCH_LABEL)
    ap.add_argument("--june-label", default=DEFAULT_JUNE_LABEL)
    args = ap.parse_args()

    if not args.db.exists():
        print(f"ERROR: no database at {args.db}")
        return 2

    con = sqlite3.connect(args.db)
    p = plan(con, args.march_label, args.june_label)
    march, june = p["march"], p["june"]

    print(f"db: {args.db}")
    print(f"  {args.march_label!r:44} {len(march):4d} rows")
    print(f"  {args.june_label!r:44} {len(june):4d} rows")
    print(f"  duplicate ranks in the March interval: {len(p['dupe_ranks'])} "
          f"{p['dupe_ranks'][:12]}")
    print()
    if not march:
        print("nothing to repair (March interval is empty)")
        return 0
    if not p["delete"] and not p["relabel"]:
        print("nothing to repair (no June content found in the March interval)")
        return 0

    print("PLAN")
    print(f"  delete  {len(p['delete']):4d} rows  (exact duplicates of the "
          f"{args.june_label!r} interval)")
    print(f"  relabel {len(p['relabel']):4d} rows  (June content with different "
          f"numbers -> {args.june_label!r})")
    print(f"  keep    {len(p['keep']):4d} rows  (genuine March survivors)")
    print()
    print("  survivors that will remain as the March board:")
    for key in sorted(p["keep"], key=lambda k: march[k]["rank"] or 999):
        r = march[key]
        print(f"    #{r['rank']:>3} {r['fv']:>5} {r['player_name']}")
    print()
    after_ranks = sorted(march[k]["rank"] for k in p["keep"]
                         if march[k]["rank"] is not None)
    print(f"  post-repair March interval: {len(p['keep'])} rows, "
          f"{len(set(after_ranks))} distinct ranks "
          f"({'NO duplicates' if len(after_ranks) == len(set(after_ranks)) else 'STILL HAS DUPLICATES'})")
    print()

    if not args.apply:
        print("DRY RUN - nothing written. Re-run with --apply to repair.")
        return 0

    if not args.no_backup:
        bak = args.db.with_suffix(f".db.bak-jbchimera-{int(time.time())}")
        print(f"backing up -> {bak} ...", flush=True)
        shutil.copy2(args.db, bak)

    n_del = n_rel = 0
    with con:
        for row_id, key in p["delete"]:
            # Guarded: only delete if it still matches its June twin exactly.
            twin = june[key]
            cur = con.execute(
                "DELETE FROM snapshots WHERE id = ? AND source = ? "
                "AND interval_label = ? AND player_key = ? "
                "AND rank IS ? AND fv IS ?",
                (row_id, SOURCE, args.march_label, key, twin["rank"], twin["fv"]))
            n_del += cur.rowcount
        for row_id, key in p["relabel"]:
            cur = con.execute(
                "UPDATE snapshots SET interval_label = ?, snapshot_date = ? "
                "WHERE id = ? AND source = ? AND interval_label = ?",
                (args.june_label, june[key]["snapshot_date"], row_id, SOURCE,
                 args.march_label))
            n_rel += cur.rowcount

    print(f"APPLIED: deleted {n_del}, relabelled {n_rel}")
    after = _rows(con, args.march_label)
    dupes = _duplicate_ranks(after)
    print(f"verify: {args.march_label!r} now has {len(after)} rows, "
          f"{len(dupes)} duplicate ranks {dupes[:12]}")
    if dupes:
        print("WARNING: duplicate ranks remain - inspect before rebuilding.")
        return 1
    print()
    print("NEXT: the consensus is built from these rows, so rebuild to publish:")
    print("  python run_monthly.py --daily     (or the next nightly run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
