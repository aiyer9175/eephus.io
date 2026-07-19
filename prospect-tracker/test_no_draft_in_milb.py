# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Firewall test — draft prospects must NEVER leak into the MiLB-side
tables. RPS+ + farm-system queries + consensus FV all key on the MiLB
schema; if a draft_<year>_<name> key ever appears in `snapshots` /
`players` / `statlines` / `sabermetrics`, the level-relative metrics
will start comparing NCAA performance to MiLB cohorts. That's the bug
this test exists to catch on every CI run.

The promoted players (post-draft, status='drafted') are allowed in the
MiLB-side `acquisitions` table — that's the bridge between the two
schemas. Their MiLB snapshot row (when one exists) uses the canonical
MiLB key, not the draft_<year>_<name> key.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).parent / "prospects.db"


from contextlib import contextmanager


@contextmanager
def _conn():
    """Yields a sqlite3 connection that's properly closed after use.

    NOTE: `with sqlite3.connect(...) as con` only manages the TRANSACTION
    (commit/rollback) — it does NOT close the connection. Using a custom
    contextmanager so the connection is released after each test,
    silencing the ResourceWarning that GC otherwise raises later."""
    if not DB_PATH.exists():
        pytest.skip(f"no prospects.db at {DB_PATH}; run `python -c \"from storage import init_db; init_db()\"`")
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()


def test_no_draft_keys_in_snapshots():
    """No row in `snapshots` should have a player_key starting with 'draft_'."""
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key, source, snapshot_date "
            "FROM snapshots WHERE player_key LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not leaks, (
        f"{len(leaks)} draft_ keys leaked into snapshots — first few: {leaks}"
    )


def test_no_draft_keys_in_players():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key FROM players WHERE player_key LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"draft_ keys leaked into players: {leaks}"


def test_no_draft_keys_in_statlines():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key FROM statlines WHERE player_key LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"draft_ keys leaked into statlines: {leaks}"


def test_no_draft_keys_in_sabermetrics():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key FROM sabermetrics WHERE player_key LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"draft_ keys leaked into sabermetrics: {leaks}"


def test_draft_canonical_keys_use_milb_target():
    """When a draft prospect is promoted, the canonical mapping's
    milb_key must NOT itself look like a draft key (no chained drafts)."""
    with _conn() as con:
        leaks = con.execute(
            "SELECT draft_key, milb_key FROM draft_canonical_keys "
            "WHERE milb_key LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not leaks, (
        f"draft_canonical_keys.milb_key should map to a MiLB-style key, "
        f"not another draft_ key. Leaks: {leaks}"
    )


def test_no_new_draft_board_intervals_in_snapshots():
    """The FG DRAFT boards must never land in the MiLB snapshots table.
    Historical flat `<type>-<year>draft.csv` drops leaked org-less
    amateur rows under interval_label='<year>draft' (2021-2026 boards,
    ~936 rows — cleanup pending as an owner decision). draft_csv routes
    draft slugs now, so any NEW leak (dated after the 2026 board's
    2026-05-22 ingest) is a router regression."""
    with _conn() as con:
        leaks = con.execute(
            "SELECT interval_label, snapshot_date, COUNT(*) FROM snapshots "
            "WHERE interval_label GLOB '20[0-9][0-9]draft' "
            "AND snapshot_date >= '2026-06-01' "
            "GROUP BY interval_label, snapshot_date LIMIT 10"
        ).fetchall()
    assert not leaks, (
        f"NEW draft-board intervals leaked into MiLB snapshots: {leaks}"
    )


def test_draft_snapshots_keyed_correctly():
    """Sanity: every row in draft_snapshots SHOULD have a draft_ key."""
    with _conn() as con:
        rows = con.execute(
            "SELECT player_key FROM draft_snapshots "
            "WHERE player_key NOT LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not rows, (
        f"draft_snapshots has rows with non-draft keys (key shape broken): {rows}"
    )
