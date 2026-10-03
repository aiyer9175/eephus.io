"""storage.upsert_birth_dates: the batched twin of upsert_birth_date.

Pins that the batch runs the same UPDATE as the per-row function (same WHERE,
same overwrite semantics, same updated_at stamp) so run_monthly's two
birth-date loops (CSV fill, PlayerIndex overwrite) can use one connection
and one commit without moving a single birth_date.
"""
import sqlite3

import pytest

import storage


def _seed(db_path, rows):
    """rows: (player_key, birth_date or None)."""
    storage.init_db()
    with storage.connect() as con:
        for key, bd in rows:
            con.execute(
                "INSERT INTO players (player_key, player_name, birth_date, "
                "updated_at) VALUES (?, ?, ?, '2020-01-01 00:00:00')",
                (key, key.replace("_", " ").title(), bd),
            )


def _rows(db_path):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(
            "SELECT player_key, birth_date, updated_at FROM players "
            "ORDER BY player_key").fetchall()
    finally:
        con.close()


SEED = [
    ("empty_guy", None),
    ("blank_guy", ""),
    ("known_guy", "2001-01-01"),
    ("untouched_guy", "2002-02-02"),
]
PAIRS = {
    "empty_guy": "2005-05-05",
    "blank_guy": "2006-06-06",
    "known_guy": "2007-07-07",
    "nobody_here": "2008-08-08",      # no players row: UPDATE matches nothing
    "skipped_guy": "",                # empty date: skipped, like the single call
}


@pytest.mark.parametrize("overwrite", [False, True])
def test_batch_matches_per_row_loop(tmp_path, monkeypatch, overwrite):
    """Two temp DBs seeded alike: the old per-row loop on one, the batch on
    the other, and the players table reads the same (updated_at compared
    only as stamped-or-not)."""
    loop_db = tmp_path / "loop.db"
    batch_db = tmp_path / "batch.db"

    monkeypatch.setattr(storage, "DB_PATH", loop_db)
    _seed(loop_db, SEED)
    for key, bd in PAIRS.items():
        storage.upsert_birth_date(key, bd, overwrite=overwrite)

    monkeypatch.setattr(storage, "DB_PATH", batch_db)
    _seed(batch_db, SEED)
    n = storage.upsert_birth_dates(PAIRS, overwrite=overwrite)

    loop_rows = _rows(loop_db)
    batch_rows = _rows(batch_db)
    assert [(k, bd) for k, bd, _ in loop_rows] == [(k, bd) for k, bd, _ in batch_rows]
    # updated_at: the batch stamps exactly the rows the loop stamped.
    seeded = "2020-01-01 00:00:00"
    assert [u != seeded for _, _, u in loop_rows] == [u != seeded for _, _, u in batch_rows]
    # The rowcount is the number of player rows the UPDATE touched.
    assert n == sum(1 for _, _, u in batch_rows if u != seeded)


def test_fill_only_writes_null_or_blank(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    _seed(tmp_path / "t.db", SEED)
    n = storage.upsert_birth_dates(PAIRS, overwrite=False)
    got = {k: bd for k, bd, _ in _rows(tmp_path / "t.db")}
    assert got == {
        "empty_guy": "2005-05-05",
        "blank_guy": "2006-06-06",
        "known_guy": "2001-01-01",      # fill mode never overwrites
        "untouched_guy": "2002-02-02",
    }
    assert n == 2


def test_overwrite_replaces_known_dates(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    _seed(tmp_path / "t.db", SEED)
    n = storage.upsert_birth_dates(list(PAIRS.items()), overwrite=True)
    got = {k: bd for k, bd, _ in _rows(tmp_path / "t.db")}
    assert got == {
        "empty_guy": "2005-05-05",
        "blank_guy": "2006-06-06",
        "known_guy": "2007-07-07",
        "untouched_guy": "2002-02-02",
    }
    assert n == 3


def test_empty_batch_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    _seed(tmp_path / "t.db", SEED)
    before = _rows(tmp_path / "t.db")
    assert storage.upsert_birth_dates({}) == 0
    assert storage.upsert_birth_dates({"empty_guy": ""}) == 0
    assert storage.upsert_birth_dates([]) == 0
    assert _rows(tmp_path / "t.db") == before
