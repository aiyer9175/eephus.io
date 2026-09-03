# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/repair_espn_ghost_rows.py: a duplicate-rank ESPN row under a
superseded player_key (leonardo_bernal beside leo_bernal, same fv, same date)
is a ghost and goes; anything that is not a byte-for-byte ghost of the kept
line is reported, never deleted."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from repair_espn_ghost_rows import find_ghosts  # noqa: E402


def _db(rows):
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE snapshots (
        id INTEGER PRIMARY KEY, source TEXT, interval_label TEXT, player_key TEXT,
        player_name TEXT, rank INTEGER, fv REAL, snapshot_date TEXT, org TEXT)""")
    con.executemany(
        "INSERT INTO snapshots (id, source, interval_label, player_key, player_name, rank, fv, snapshot_date, org) VALUES (?,?,?,?,?,?,?,?,?)",
        rows)
    return con


def test_ghost_under_superseded_key_is_found_and_only_it():
    con = _db([
        (1, "espn", "ESPN 2026 Preseason", "leonardo_bernal", "Leonardo Bernal", 98, 50.0, "2026-01-27", "STL"),
        (2, "espn", "ESPN 2026 Preseason", "leo_bernal", "Leonardo Bernal", 98, 50.0, "2026-01-27", "STL"),
        (3, "espn", "ESPN 2026 Preseason", "konnor_griffin", "Konnor Griffin", 1, 65.0, "2026-01-27", "PIT"),
        # Another source's duplicate rank is none of this script's business.
        (4, "fangraphs", "2026updated", "a_b", "A B", 5, 50.0, "2026-08-02", "PIT"),
        (5, "fangraphs", "2026updated", "c_d", "C D", 5, 50.0, "2026-08-02", "ARI"),
    ])
    ghosts, unresolved = find_ghosts(con)
    assert [g["id"] for g in ghosts] == [1]
    assert ghosts[0]["kept_key"] == "leo_bernal" and ghosts[0]["kept_id"] == 2
    assert unresolved == []


def test_different_fv_or_date_is_reported_not_deleted():
    con = _db([
        (1, "espn", "ESPN 2026 Preseason", "leonardo_bernal", "Leonardo Bernal", 98, 45.0, "2026-01-27", "STL"),
        (2, "espn", "ESPN 2026 Preseason", "leo_bernal", "Leonardo Bernal", 98, 50.0, "2026-01-27", "STL"),
    ])
    ghosts, unresolved = find_ghosts(con)
    assert ghosts == []
    assert len(unresolved) == 1 and "differ" in unresolved[0]["why"]


def test_two_different_humans_at_one_rank_is_unresolved():
    con = _db([
        (1, "espn", "ESPN 2026 Preseason", "john_smith", "John Smith", 40, 50.0, "2026-01-27", "NYY"),
        (2, "espn", "ESPN 2026 Preseason", "jane_doe", "Jane Doe", 40, 50.0, "2026-01-27", "BOS"),
    ])
    ghosts, unresolved = find_ghosts(con)
    assert ghosts == []
    assert len(unresolved) == 1 and "2 row(s) match" in unresolved[0]["why"]
