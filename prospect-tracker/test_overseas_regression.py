# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression guards for the 2026-06 Overseas "0 prospects on file" bug.

ROOT CAUSE (see git 26b16f7): the monthly run executes draft + overseas + milb
pipelines concurrently against one SQLite DB. `load_overseas_snapshots` swallowed
`sqlite3.OperationalError` ("database is locked") into an empty list, and
`export_overseas_json` had no floor — so a single transient lock silently wrote
`leagues:[]` over a known-good sidecar (40 prospects) and it got committed.

These tests lock in the two-part fix so it can't silently regress:
  1. the loaders RE-RAISE a transient lock (only a missing table is a legit empty);
  2. the export REFUSES to overwrite when it computed 0 but snapshots exist;
  3. a real-DB smoke check that the Overseas count is > 0 and tracks the CSV.
"""

from __future__ import annotations

import contextlib
import csv
import json
import sqlite3
from pathlib import Path

import pytest

import overseas_export
import storage

ROOT = Path(__file__).resolve().parent
_OVERSEAS_CSV = (ROOT / "data" / "fangraphs_imports" / "processed"
                 / "2026overseas__2026-02-05" / "summary-2026overseas.csv")


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()


def _insert_overseas_snapshot(player_key="overseas_npb_test", league="NPB", fv=50.0):
    with storage.connect() as con:
        con.execute(
            "INSERT INTO overseas_snapshots "
            "(source, snapshot_date, interval_label, player_key, player_name, league, fv, status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("fangraphs", "2026-02-05", "2026overseas", player_key, "Test Player",
             league, fv, "overseas_active"),
        )


# ── Fix #1: loaders must re-raise a transient lock, not swallow it into empty ──

def test_loader_reraises_database_locked(monkeypatch):
    """A "database is locked" OperationalError must propagate — swallowing it into
    [] is what silently emptied the overseas export under the concurrent pipeline."""
    @contextlib.contextmanager
    def _locked_connect():
        class _Locked:
            def execute(self, *a, **k):
                raise sqlite3.OperationalError("database is locked")
        yield _Locked()

    monkeypatch.setattr(storage, "connect", _locked_connect)
    with pytest.raises(sqlite3.OperationalError):
        storage.load_overseas_snapshots()
    with pytest.raises(sqlite3.OperationalError):
        storage.load_overseas_players()


def test_loader_missing_table_is_legit_empty(tmp_path, monkeypatch):
    """A genuinely-missing table (fresh DB, never initialized) is a real empty
    result and must NOT raise — that path is how a brand-new DB boots."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "bare.db")  # no init_db()
    assert storage.load_overseas_snapshots() == []
    assert storage.load_overseas_players() == {}
    assert storage.overseas_snapshot_count() == 0


# ── Fix #2: the export floor — a 0 build must not clobber a good sidecar ──────

def test_floor_guard_refuses_to_overwrite_when_snapshots_present(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    _insert_overseas_snapshot()  # snapshots table is non-empty
    # Simulate the regression: the build transiently yields nothing.
    monkeypatch.setattr(overseas_export, "build_overseas_export",
                        lambda: {"generated_at": "now", "leagues": []})

    good = tmp_path / "overseas_timeseries.json"
    good.write_text('{"leagues":[{"league":"NPB","n_prospects":40}]}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        overseas_export.export_overseas_json(good)

    # The known-good sidecar is untouched — no silent empty-write.
    preserved = json.loads(good.read_text(encoding="utf-8"))
    assert preserved["leagues"][0]["n_prospects"] == 40


def test_empty_source_writes_zero_without_raising(tmp_path, monkeypatch):
    """A genuinely-empty source (no snapshots) writes 0 normally — the guard only
    fires when the build is empty BUT the table has rows (the bug signature)."""
    _fresh_db(tmp_path, monkeypatch)  # overseas_snapshots exists but is empty
    monkeypatch.setattr(overseas_export, "build_overseas_export",
                        lambda: {"generated_at": "now", "leagues": []})
    out = tmp_path / "overseas_timeseries.json"
    assert overseas_export.export_overseas_json(out) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["leagues"] == []


# ── Fix #3: real-DB smoke — Overseas is non-empty and tracks the source CSV ───

def test_real_db_overseas_nonzero_and_tracks_csv():
    """Against the live DB: the Overseas section must not be empty, and the
    snapshot count should track the FanGraphs Overseas CSV of record (every CSV
    row ingests 1:1; the export then drops only players with MLB activity)."""
    try:
        n_snaps = storage.overseas_snapshot_count()
    except sqlite3.OperationalError:
        pytest.skip("overseas_snapshots table unavailable")
    if n_snaps == 0:
        pytest.skip("no overseas snapshots in the working DB (run the ingest first)")

    payload = overseas_export.build_overseas_export()
    n_export = sum(b["n_prospects"] for b in payload["leagues"])
    assert n_export > 0, "Overseas export is empty despite snapshots on file (regression)"
    assert payload["leagues"], "Overseas export produced no league blocks"

    if _OVERSEAS_CSV.exists():
        with _OVERSEAS_CSV.open(encoding="utf-8-sig") as f:
            csv_rows = sum(1 for r in csv.DictReader(f) if (r.get("Name") or "").strip())
        # 1:1 ingest; allow a small drift for already-promoted players.
        assert n_snaps >= csv_rows * 0.8, f"snapshots {n_snaps} << CSV rows {csv_rows}"
        # Export keeps the large majority (only MLB-active players are filtered).
        assert n_export >= n_snaps * 0.5, f"export {n_export} << snapshots {n_snaps}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
