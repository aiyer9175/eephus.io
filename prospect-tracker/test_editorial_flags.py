# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Editorial-flag logging guards (model-audit WS-0c): emit-time persistence
with matched-control sampling keys, append-only per (player, flag, date) —
the 30/60-day forward cohorts (Phase 5) depend on these properties."""

from __future__ import annotations

import pytest

import storage


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    return tmp_path / "test.db"


def test_flags_persist_with_control_bands(tmp_db):
    n = storage.insert_editorial_flags("2026-06-01", [
        {"player_key": "a", "flag_type": "riser", "score": 7.5,
         "fv": 57.0, "level": "AA", "age": 20.2},
        {"player_key": "b", "flag_type": "faller", "score": -4.0,
         "fv": 44.0, "level": "A+", "age": 23.9},
        {"player_key": "", "flag_type": "riser"},          # invalid -> skipped
    ])
    assert n == 2
    rows = storage.load_editorial_flags()
    by_key = {r["player_key"]: r for r in rows}
    assert by_key["a"]["fv_band"] == "55" and by_key["a"]["age_band"] == "19-21"
    assert by_key["b"]["fv_band"] == "<45" and by_key["b"]["age_band"] == "23-25"
    assert storage.load_editorial_flags("riser")[0]["player_key"] == "a"


def test_rerun_same_day_is_noop(tmp_db):
    """Re-running an export the same day must not contaminate cohorts."""
    flag = [{"player_key": "a", "flag_type": "riser", "score": 1.0, "fv": 50.0,
             "level": "AA", "age": 21.0}]
    assert storage.insert_editorial_flags("2026-06-01", flag) == 1
    flag[0]["score"] = 99.0                                 # changed score
    assert storage.insert_editorial_flags("2026-06-01", flag) == 0
    assert storage.load_editorial_flags()[0]["score"] == 1.0  # first-seen wins
    # a NEW month is a new cohort row
    assert storage.insert_editorial_flags("2026-07-01", flag) == 1


def test_band_edges():
    assert storage._editorial_band(45.0, 19.0) == ("45", "19-21")
    assert storage._editorial_band(60.0, 25.0) == ("60+", "25+")
    assert storage._editorial_band(None, None) == (None, None)
