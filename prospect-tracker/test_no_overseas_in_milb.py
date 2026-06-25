# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Firewall — overseas (KBO/NPB/CPBL) prospects must NEVER leak into
MiLB-side tables. RPS+ / age-vs-level / consensus FV all key on the
MiLB schema; if an `overseas_<league>_<name>` key surfaces in
`snapshots`/`players`/`statlines`/`sabermetrics`, the cohort
comparisons start mixing NPB / KBO / NCAA performance with MiLB —
that's the bug this test exists to catch.

Promoted overseas players appear in MiLB tables under their canonical
MiLB key, NOT under the `overseas_*` namespaced key (which stays only
in the overseas_* tables + the canonical_keys bridge).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).parent / "prospects.db"


from contextlib import contextmanager


@contextmanager
def _conn():
    """Yields a sqlite3 connection that's properly closed (sqlite3's own
    `with` only manages the transaction, not the connection lifetime)."""
    if not DB_PATH.exists():
        pytest.skip(f"no prospects.db at {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()


def test_no_overseas_keys_in_snapshots():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key, source, snapshot_date FROM snapshots "
            "WHERE player_key LIKE 'overseas_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"overseas_ keys leaked into snapshots: {leaks}"


def test_no_overseas_keys_in_players():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key FROM players WHERE player_key LIKE 'overseas_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"overseas_ keys leaked into players: {leaks}"


def test_no_overseas_keys_in_statlines():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key FROM statlines WHERE player_key LIKE 'overseas_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"overseas_ keys leaked into statlines: {leaks}"


def test_no_overseas_keys_in_sabermetrics():
    with _conn() as con:
        leaks = con.execute(
            "SELECT player_key FROM sabermetrics WHERE player_key LIKE 'overseas_%' LIMIT 10"
        ).fetchall()
    assert not leaks, f"overseas_ keys leaked into sabermetrics: {leaks}"


def test_overseas_canonical_keys_use_milb_target():
    """The MiLB target side of the canonical-key map must NOT be another
    overseas_ key (no chained namespaces)."""
    with _conn() as con:
        leaks = con.execute(
            "SELECT overseas_key, milb_key FROM overseas_canonical_keys "
            "WHERE milb_key LIKE 'overseas_%' OR milb_key LIKE 'draft_%' LIMIT 10"
        ).fetchall()
    assert not leaks, (
        f"overseas_canonical_keys.milb_key should target the canonical "
        f"MiLB namespace. Leaks: {leaks}"
    )


def test_overseas_snapshots_keyed_correctly():
    """Sanity: every row in overseas_snapshots SHOULD have an overseas_ key."""
    with _conn() as con:
        rows = con.execute(
            "SELECT player_key FROM overseas_snapshots "
            "WHERE player_key NOT LIKE 'overseas_%' LIMIT 10"
        ).fetchall()
    assert not rows, (
        f"overseas_snapshots has rows with non-overseas keys: {rows}"
    )
