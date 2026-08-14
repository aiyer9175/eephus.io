"""Repair the MLB Pipeline vintage labels. DRY RUN unless --apply is passed.

Built from the full 2011-2026 audit recorded in
docs/efv-2026-08-13/PIPELINE_VINTAGE_CONTAMINATION.md. The audit found THREE
distinct defects wearing one symptom (rows > distinct ranks), and they need three
different treatments, so this tool reports them separately and refuses to treat
them alike.

  CLASS A  current-year accretion
           /prospects/{y}/top100/ serves the LIVE board for the current year, so
           the archive loop wrote today's board under the preseason label with a
           hardcoded {y}-01-22 date. insert_snapshots upserts on
           (source, interval_label, player_key) and never touches inserted_at, so
           a player who was not on the first capture INSERTS a new row and the
           label accretes. Safe to delete: these rows are duplicates of correctly
           dated rows under "MLB Pipeline Live YYYY-MM-DD" or an org label.
           The scrape-side guard shipped separately (scrapers.scrape_all).

  CLASS B  wrong-list orphans (2011, 2014, 2016 Top 100)
           On 2026-06-22 those pages parsed from a cache holding the YANKEES ORG
           BOARD. 10/20/30 rows went in; a forced re-run 48s later wrote the true
           boards over them but could only correct the Yankees who were ALSO
           genuine Top-100 players. The rest are orphans carrying an org rank
           under a Top-100 label. Safe to delete: they were never on that board.

  CLASS C  name-variant duplicates (2022 jose_miranda/jose_f_miranda, and the
           2024/2025 Rangers pair)
           NOT a vintage defect and NOT deleted here. Two keys for one human is
           an identity problem and belongs in consensus.PLAYER_KEY_ALIASES, where
           the merge is applied everywhere rather than in one label. Reported so
           it is not mistaken for accretion and quietly dropped.

Read-only by default. --apply takes a table backup first.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

PT = Path(__file__).resolve().parent.parent
DB = PT / "prospects.db"
WRONG_LIST_YEARS = (2011, 2014, 2016)
WRONG_LIST_RUN_DAY = "2026-06-22"


def _con(readonly: bool):
    if readonly:
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    return sqlite3.connect(str(DB))


def class_a(con, year: int):
    """Rows in a CURRENT-YEAR archive label inserted after that label's first day."""
    out = []
    labels = [r[0] for r in con.execute(
        "SELECT DISTINCT interval_label FROM snapshots WHERE source='mlb_pipeline' "
        "AND (interval_label = ? OR interval_label LIKE ?)",
        (f"MLB Pipeline {year} Top 100", f"MLB Pipeline {year} % Top 30"))]
    for lab in sorted(labels):
        first = con.execute(
            "SELECT MIN(substr(inserted_at,1,10)) FROM snapshots WHERE interval_label=?",
            (lab,)).fetchone()[0]
        rows = con.execute(
            "SELECT id, player_key, player_name, rank, fv, substr(inserted_at,1,10) "
            "FROM snapshots WHERE interval_label=? AND substr(inserted_at,1,10) > ? "
            "ORDER BY rank", (lab, first)).fetchall()
        if rows:
            out.append((lab, first, rows))
    return out


def class_b(con):
    """Orphans from the wrong-list write: early-batch rows sitting on a rank that a
    later row in the same label also holds."""
    out = []
    for y in WRONG_LIST_YEARS:
        lab = f"MLB Pipeline {y} Top 100"
        rows = con.execute(
            "SELECT id, player_key, player_name, rank, fv, inserted_at "
            "FROM snapshots WHERE interval_label=? ORDER BY rank, inserted_at", (lab,)
        ).fetchall()
        by_rank = defaultdict(list)
        for r in rows:
            by_rank[r[3]].append(r)
        orphans = []
        for rank, group in sorted(by_rank.items()):
            if len(group) < 2:
                continue
            # the EARLIEST insert on a duplicated rank is the wrong-list row; the
            # later one is the true board. Guard the assumption rather than assume it.
            group.sort(key=lambda r: r[5])
            if not group[0][5].startswith(WRONG_LIST_RUN_DAY):
                continue
            orphans.extend(group[:-1])
        if orphans:
            out.append((lab, orphans))
    return out


def class_c(con):
    """Two keys, one human. Reported, never deleted here."""
    out = []
    rows = con.execute(
        "SELECT interval_label, rank, GROUP_CONCAT(player_key,'|'), COUNT(*) c "
        "FROM snapshots WHERE source='mlb_pipeline' "
        "GROUP BY interval_label, rank HAVING c > 1").fetchall()
    for lab, rank, keys, _c in rows:
        ks = keys.split("|")
        # a name-variant pair shares a surname token and differs by an initial
        norm = {k.replace("_", "") for k in ks}
        if len(ks) == 2 and (ks[0] in ks[1] or ks[1] in ks[0] or
                             len({k[:4] for k in ks}) == 1 and len(norm) == 2):
            out.append((lab, rank, ks))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete class A and class B rows (default: dry run)")
    ap.add_argument("--year", type=int, default=date.today().year,
                    help="current year for the class-A sweep")
    args = ap.parse_args()

    con = _con(readonly=not args.apply)
    con.row_factory = None

    a = class_a(con, args.year)
    b = class_b(con)
    c = class_c(con)

    a_ids = [r[0] for _lab, _f, rows in a for r in rows]
    b_ids = [r[0] for _lab, rows in b for r in rows]

    print(f"CLASS A  current-year accretion ({args.year})")
    tot = 0
    for lab, first, rows in a:
        tot += len(rows)
        print(f"  {lab:44s} first capture {first}  +{len(rows)} rows")
        for r in rows[:3]:
            print(f"      rank {str(r[3]):>4s}  {r[2][:28]:30s} fv {r[4]}  ins {r[5]}")
        if len(rows) > 3:
            print(f"      ... and {len(rows) - 3} more")
    print(f"  TOTAL class A: {tot} rows across {len(a)} labels")
    print()

    print("CLASS B  wrong-list orphans")
    for lab, rows in b:
        print(f"  {lab:44s} {len(rows)} orphans")
        for r in rows[:3]:
            print(f"      rank {str(r[3]):>4s}  {r[2][:28]:30s} fv {r[4]}  ins {r[5]}")
        if len(rows) > 3:
            print(f"      ... and {len(rows) - 3} more")
    print(f"  TOTAL class B: {len(b_ids)} rows")
    print()

    print("CLASS C  name-variant duplicates (REPORTED ONLY, not deleted)")
    for lab, rank, ks in c:
        print(f"  {lab:44s} rank {rank}: {ks[0]} / {ks[1]}")
    print(f"  TOTAL class C: {len(c)} rank collisions -> route via "
          f"consensus.PLAYER_KEY_ALIASES, not a delete")
    print()

    if not args.apply:
        print(f"DRY RUN. Would delete {len(a_ids) + len(b_ids)} rows "
              f"({len(a_ids)} class A + {len(b_ids)} class B). Re-run with --apply.")
        return 0

    if not (a_ids or b_ids):
        print("nothing to do")
        return 0
    backup = DB.with_suffix(f".db.bak-vintage-{date.today().isoformat()}")
    if not backup.exists():
        print(f"backing up to {backup.name} ...")
        shutil.copy2(DB, backup)
    ids = a_ids + b_ids
    con.executemany("DELETE FROM snapshots WHERE id=?", [(i,) for i in ids])
    con.commit()
    print(f"deleted {len(ids)} rows; backup at {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
