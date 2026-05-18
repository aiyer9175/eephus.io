#!/usr/bin/env python3
"""
One-time migration: fix mojibake player names and keys in the database.

The manual_rankings.csv was stored with incorrect encoding for several
seasons, so the DB contains entries like:
    player_key  = 'adolis_garcaa'
    player_name = 'Adolis GarcÃ\xada'

After the CSV was fixed to UTF-8, new snapshots started using the correct
    player_key  = 'adolis_garcia'
    player_name = 'Adolis García'

This migration:
  1. Detects all mojibake player names in the snapshots table.
  2. Applies the same fix_name() function used by fix_encoding.py.
  3. Recomputes the correct player_key from the fixed name.
  4. For each (old_key → new_key) pair:
       - If new_key already exists in the DB, merges old snapshots in
         (skipping conflicts from the UNIQUE constraint).
       - Otherwise, renames the old_key in place.
  5. Repeats for the players, statlines, pitch_arsenals, statcast_metrics,
     and trades tables.
  6. Reports a summary.

Safe to run multiple times (idempotent after first pass).
"""

import re
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent / "prospects.db"


# ---------------------------------------------------------------------------
# Same fix logic as fix_encoding.py
# ---------------------------------------------------------------------------

def fix_name(text: str) -> str:
    if not text:
        return text
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else None
        if nxt is not None and ch in ('\xc3', '�'):
            try:
                pair_bytes = ('\xc3' + nxt).encode('latin-1')
                fixed_char = pair_bytes.decode('utf-8')
                if len(fixed_char) == 1 and ord(fixed_char) > 127 and '�' not in fixed_char:
                    result.append(fixed_char)
                    i += 2
                    continue
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        if ch == '\xad':    # soft hyphen — never valid in a name
            i += 1
            continue
        result.append(ch)
        i += 1
    return unicodedata.normalize('NFC', ''.join(result))


def normalize_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


def needs_fix(name: str) -> bool:
    return '\xc3' in name or '�' in name or '\xad' in name


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def migrate():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Collect all bad (old_key, old_name) pairs from snapshots
    rows = cur.execute(
        """SELECT DISTINCT player_key, player_name
           FROM snapshots
           WHERE player_name LIKE '%Ã%'
              OR player_name LIKE '%�%'
              OR player_name LIKE '%\xad%'"""
    ).fetchall()

    if not rows:
        print("No mojibake names found — nothing to do.")
        con.close()
        return

    print(f"Found {len(rows)} distinct bad player keys to fix.")

    renamed = 0
    merged  = 0
    skipped = 0

    for row in rows:
        old_key  = row["player_key"]
        old_name = row["player_name"]

        new_name = fix_name(old_name)
        new_key  = normalize_key(new_name)

        if new_key == old_key:
            # Name display changed but key didn't — just update name fields
            for tbl in ("snapshots", "players"):
                try:
                    cur.execute(f"UPDATE {tbl} SET player_name = ? WHERE player_key = ?",
                                (new_name, old_key))
                except Exception as e:
                    print(f"  WARN: {tbl} name update failed for {old_key!r}: {e}")
            renamed += 1
            continue

        # Check whether new_key already exists
        existing = cur.execute(
            "SELECT 1 FROM snapshots WHERE player_key = ? LIMIT 1", (new_key,)
        ).fetchone()

        if existing:
            # Merge: move old snapshots to new_key, skip duplicates
            cur.execute(
                """INSERT OR IGNORE INTO snapshots
                   (source, snapshot_date, interval_label, player_key,
                    player_name, position, org, rank, fv, status, inserted_at)
                   SELECT source, snapshot_date, interval_label, ?, ?,
                          position, org, rank, fv, status, inserted_at
                   FROM snapshots WHERE player_key = ?""",
                (new_key, new_name, old_key),
            )
            cur.execute("DELETE FROM snapshots WHERE player_key = ?", (old_key,))
            merged += 1
        else:
            # Simple rename
            for tbl in ("snapshots",):
                cur.execute(
                    f"UPDATE {tbl} SET player_key = ?, player_name = ? WHERE player_key = ?",
                    (new_key, new_name, old_key),
                )
            renamed += 1

        # Update players table
        existing_p = cur.execute(
            "SELECT 1 FROM players WHERE player_key = ? LIMIT 1", (new_key,)
        ).fetchone()
        if existing_p:
            # Absorb: keep new_key entry, remove old
            cur.execute("DELETE FROM players WHERE player_key = ?", (old_key,))
        else:
            cur.execute(
                "UPDATE players SET player_key = ?, player_name = ? WHERE player_key = ?",
                (new_key, new_name, old_key),
            )

        # Update satellite tables that reference player_key
        for tbl in ("statlines", "pitch_arsenals", "statcast_metrics"):
            try:
                existing_sat = cur.execute(
                    f"SELECT 1 FROM {tbl} WHERE player_key = ? LIMIT 1", (new_key,)
                ).fetchone()
                if existing_sat:
                    cur.execute(f"DELETE FROM {tbl} WHERE player_key = ?", (old_key,))
                else:
                    cur.execute(
                        f"UPDATE {tbl} SET player_key = ? WHERE player_key = ?",
                        (new_key, old_key),
                    )
            except sqlite3.OperationalError:
                pass  # table may not exist yet

        # Trades — UNIQUE constraint on (player_key, trade_date, source)
        try:
            cur.execute(
                """INSERT OR IGNORE INTO trades
                   (player_key, trade_date, from_org, to_org, source,
                    description, date_range_start, date_range_end, inserted_at)
                   SELECT ?, trade_date, from_org, to_org, source,
                          description, date_range_start, date_range_end, inserted_at
                   FROM trades WHERE player_key = ?""",
                (new_key, old_key),
            )
            cur.execute("DELETE FROM trades WHERE player_key = ?", (old_key,))
        except sqlite3.OperationalError:
            pass

        print(f"  {old_key!r:40s} -> {new_key!r}  ({'merged' if existing else 'renamed'})")

    con.commit()
    con.close()

    print()
    print(f"Done: {renamed} renamed, {merged} merged into existing keys, {skipped} skipped.")
    print("Run 'python run_monthly.py --skip-stats' to rebuild the JSON.")


if __name__ == "__main__":
    migrate()
