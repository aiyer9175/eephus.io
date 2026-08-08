# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
repair_asterisk_names.py: strip FanGraphs draft-eligibility asterisk markers
out of the stored player_name columns.

THE BUG (verified 2026-08-07): the FanGraphs Board CSV export encodes draft
eligibility INSIDE the Name column instead of in a column of its own. A
single TRAILING asterisk means draft-eligible sophomore, a leading "**"
means senior. The CSV paths (fangraphs_csv.py:304, draft_csv.py:134,
overseas_csv.py:129) clean the Name field with scrapers.fix_mojibake only,
which is a latin-1 round trip plus a whitespace collapse and has no concept
of a marker, so the character carried straight into Snapshot.player_name and
from there onto the served board. Measured in prospects.db before this
repair:

    table                        rows  distinct  trailing "*"  leading "**"
    snapshots.player_name           7         4             4             0
    players.player_name             3         3             3             0
    draft_snapshots.player_name    51        47             5            42
    draft_players.player_name      38        38             0            38
    (7 other name-bearing tables)   0         0             0             0

The three names that reach the PROSPX active prospects list are Derek
Curiel* (overall_rank 87), Ty Head* (145) and Chris Rembert* (454), all
2026 draftees, all status=active. Note timeseries.json carries rank=None
for all three, so a regression test must assert on overall_rank. The 42
leading-"**" draft_snapshots names are the 2018-2020 draft classes and
are exactly the 42 that reached draft_timeseries.json.

It never tripped an identity guard because scrapers.normalize_key() strips
every non-alphanumeric, so the player_key was always clean. Only the display
string was dirty.

THE REPAIR: rewrite each affected row through scrapers.strip_name_markers(),
the SAME helper storage.load_all_snapshots() / load_draft_snapshots() /
load_draft_players() now apply at the read boundary. Importing it rather
than re-implementing the regex here is deliberate: if the read boundary and
this repair ever disagreed, a row would look clean on disk and dirty when
served (or the reverse), which is the exact class of bug that hid this one.

Why this script exists, stated accurately. The read-boundary strip already
covers every SNAPSHOT surface, but the `players` table is a separate identity
row and has no strip on its read path, so a marker stored there survives into
anything that reads that column directly.

What that is NOT: a match failure. An earlier draft of this docstring claimed
a marker in `players.player_name` silently broke the name-matching consumers
at college_translation.py:142 and intl_amateur.py:62. Measured, and FALSE.
Both normalize before matching -- college_translation.norm_name strips
[^a-z ] at :93 and intl_amateur._player_index calls normalize_key at :66 --
so normalize_key("Derek Curiel*") == normalize_key("Derek Curiel") and the
marker was invisible to both. The `players` rows are swept here for hygiene:
the column is a DISPLAY string, a stored marker renders verbatim wherever it
is shown, and leaving the table half-clean would mean a row that looks clean
when served through a snapshot and dirty when read straight off `players`.

Conservative by construction: only asterisk runs at the very start or the
very end of a name are removed, because an interior asterisk would be a
different and unknown case. Measured: zero interior-asterisk rows across
every table below. A name that is nothing but markers is left alone.

Every row touched is printed. Idempotent: re-running after --apply reports
0 dirty rows and changes nothing.

Usage:
    python tools/repair_asterisk_names.py            # dry run (default)
    python tools/repair_asterisk_names.py --apply    # write changes
    python tools/repair_asterisk_names.py --db PATH  # non-default DB
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_DB = _HERE.parent / "prospects.db"
sys.path.insert(0, str(_HERE.parent))

from scrapers import strip_name_markers  # noqa: E402

# (table, name_column, key_column_for_reporting)
#
# Every table in prospects.db that stores a human-readable player name. The
# four with measured dirty rows are listed first; the rest are swept anyway
# because the marker enters through a shared CSV cleaner, so any board that
# FanGraphs annotates next lands in one of them. A table that does not exist
# on this DB is skipped, not an error.
NAME_TABLES: list[tuple[str, str, str]] = [
    ("snapshots",         "player_name", "player_key"),
    ("players",           "player_name", "player_key"),
    ("draft_snapshots",   "player_name", "player_key"),
    ("draft_players",     "player_name", "player_key"),
    ("overseas_snapshots", "player_name", "player_key"),
    ("overseas_players",  "player_name", "player_key"),
    ("draft_mocks",       "player_name", "player_key"),
    ("draft_results",     "player_name", "player_key"),
    ("source_events",     "player_name", "player_key"),
    ("mlb_trade_players", "player_name", "name_slug"),
    ("tjstats_snapshots", "name",        "player_key"),
]


def _p(action: str, *detail):
    print(f"  [{action}] " + " ".join(str(d) for d in detail))


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def repair(db_path: Path, apply: bool) -> int:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== repair_asterisk_names [{mode}] db={db_path} ===")
    if not db_path.exists():
        print(f"FATAL: db not found: {db_path}")
        return 2

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    total_rows = 0        # rows that were (or would be) written
    interior: list[str] = []   # left alone, reported for a human to look at

    for table, name_col, key_col in NAME_TABLES:
        if not _table_exists(con, table):
            print(f"\n-- {table} -- (no such table on this DB, skipped)")
            continue

        rows = con.execute(
            f"SELECT rowid AS _rid, {key_col} AS _key, {name_col} AS _name "
            f"FROM {table} WHERE {name_col} LIKE '%*%'"
        ).fetchall()
        if not rows:
            print(f"\n-- {table}.{name_col} -- clean (0 rows carry an asterisk)")
            continue

        # Collapse to distinct old -> new so the printout is readable when a
        # name repeats across snapshot dates. The row count is what actually
        # gets written.
        pairs: dict[str, tuple[str, int]] = {}
        for r in rows:
            old = r["_name"]
            new = strip_name_markers(old)
            if new == old:
                # strip_name_markers is a no-op here, which means the
                # asterisk is INTERIOR (or the name is markers only). Do not
                # guess at it.
                interior.append(f"{table}.{name_col} {r['_key']}: {old!r}")
                continue
            seen = pairs.get(old)
            pairs[old] = (new, (seen[1] if seen else 0) + 1)

        writable = sum(n for _, n in pairs.values())
        print(f"\n-- {table}.{name_col} -- {len(rows)} rows carry an asterisk, "
              f"{writable} rewritable across {len(pairs)} distinct names")
        for old in sorted(pairs):
            new, n = pairs[old]
            _p("strip", f"{old!r} -> {new!r}  ({n} row{'s' if n != 1 else ''})")

        if apply and pairs:
            for old, (new, _n) in pairs.items():
                con.execute(
                    f"UPDATE {table} SET {name_col} = ? WHERE {name_col} = ?",
                    (new, old),
                )
        total_rows += writable

    if interior:
        print("\n-- interior asterisks (NOT touched: unknown case) --")
        for line in interior:
            _p("advisory", line)

    if apply:
        con.commit()
        # Re-query rather than trusting the UPDATE rowcounts. A repair that
        # reports success off its own bookkeeping is how the sawyer_strosnider
        # row stayed dirty on one snapshot date and clean on another without
        # anyone noticing.
        print("\n-- verification (re-queried after commit) --")
        left = 0
        for table, name_col, _key in NAME_TABLES:
            if not _table_exists(con, table):
                continue
            n = con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {name_col} LIKE '%*%'"
            ).fetchone()[0]
            left += n
            print(f"  {table}.{name_col}: {n} rows still carry an asterisk")
        print(f"\nWROTE {total_rows} rows. {left} asterisk rows remain "
              f"(expect {len(interior)}, the interior-asterisk advisories).")
        con.close()
        return 0 if left == len(interior) else 1

    con.close()
    print(f"\nDRY RUN. {total_rows} rows would be rewritten. "
          f"Re-run with --apply to write.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"path to prospects.db (default {DEFAULT_DB})")
    args = ap.parse_args()
    return repair(args.db.resolve(), args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
