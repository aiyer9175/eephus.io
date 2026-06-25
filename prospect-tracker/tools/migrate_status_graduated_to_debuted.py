# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-shot DB migration: rename status enum 'graduated' -> 'debuted'.

Runs against `prospects.db` in the project root. Idempotent — running
it twice does nothing on the second pass.

Why: v25 renames the player-state enum from 'graduated' (legacy term
inherited from rookie-eligibility era) to 'debuted', matching the
user-facing 'Debuted' tab and 'debut_date' field that already permeate
the rest of the codebase. The internal enum was the last graduation-
named primitive; this script flips it in-place across:

  * snapshots.status     (the canonical enum)
  * Any future enum columns we add

After this runs, the Python source must already use 'debuted' as the
canonical status value (otherwise reads from the migrated DB will
return rows that don't match the post-migration code).

Usage:
    python tools/migrate_status_graduated_to_debuted.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "prospects.db"


def main() -> int:
    if not DB_PATH.exists():
        print(f"no DB at {DB_PATH} — nothing to migrate")
        return 0
    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        n_before_grad = cur.execute(
            "SELECT COUNT(*) FROM snapshots WHERE status = 'graduated'"
        ).fetchone()[0]
        n_before_debut = cur.execute(
            "SELECT COUNT(*) FROM snapshots WHERE status = 'debuted'"
        ).fetchone()[0]
        print(f"before: {n_before_grad} rows status='graduated', "
              f"{n_before_debut} rows status='debuted'")
        n = cur.execute(
            "UPDATE snapshots SET status = 'debuted' WHERE status = 'graduated'"
        ).rowcount
        con.commit()
        n_after_grad = cur.execute(
            "SELECT COUNT(*) FROM snapshots WHERE status = 'graduated'"
        ).fetchone()[0]
        n_after_debut = cur.execute(
            "SELECT COUNT(*) FROM snapshots WHERE status = 'debuted'"
        ).fetchone()[0]
        print(f"migrated {n} rows")
        print(f"after:  {n_after_grad} rows status='graduated', "
              f"{n_after_debut} rows status='debuted'")
        return n
    finally:
        con.close()


if __name__ == "__main__":
    main()
