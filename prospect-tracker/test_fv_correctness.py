"""Regression tests pinning the FV-correctness bug fix.

Three angles:
  1. Canonical case — Julio Rodriguez 2022 FG Report = FV 65 (was 37.5)
  2. Storage layer — UPSERT corrects a stale FV on re-ingest
  3. Join layer — name-key collisions keep the higher-FV row

Tests against the on-disk DB skip when `prospects.db` isn't present so a
fresh-checkout CI run still passes."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fangraphs_csv import _join_report_set
from storage import DB_PATH, Snapshot, init_db, insert_snapshots


# ---------------------------------------------------------------------------
# Canonical case
# ---------------------------------------------------------------------------

class TestJulioRodriguezCanonical:
    def test_2022_report_fv_is_65(self):
        # User-reported bug: Julio Rodriguez was showing FV 37.5 on the
        # 2022 FG report. Actual FanGraphs published value was 65 (he was
        # the #3 prospect in baseball). Root cause was a name-key collision
        # with a DIFFERENT Julio Rodriguez (SFG SIRP, FV 35+) plus an
        # INSERT OR IGNORE that prevented re-ingest from correcting the
        # stale snapshot.
        if not DB_PATH.exists():
            pytest.skip(f"prospects.db not at {DB_PATH}; skip")
        con = sqlite3.connect(str(DB_PATH))
        rows = con.execute(
            "SELECT fv FROM snapshots "
            "WHERE player_key='julio_rodriguez' "
            "  AND source='fangraphs' "
            "  AND interval_label='2022report'"
        ).fetchall()
        con.close()
        assert rows, "no 2022report snapshot for julio_rodriguez"
        assert rows[0][0] == 65.0, (
            f"Julio Rodriguez 2022report FV should be 65 (Mariners "
            f"superstar) — got {rows[0][0]}. Re-run "
            f"`python tools/audit_fg_fv.py` to find drift."
        )


# ---------------------------------------------------------------------------
# Storage-layer UPSERT behavior
# ---------------------------------------------------------------------------

class TestUpsertCorrectsStaleFV:
    def test_reinsert_overwrites_fv(self, tmp_path):
        # The previous INSERT OR IGNORE silently skipped re-runs, so a
        # snapshot with the wrong FV stayed wrong forever. UPSERT must
        # overwrite the FV on re-ingest of the same key.
        tmp_db = tmp_path / "test_prospects.db"
        with patch("storage.DB_PATH", tmp_db):
            init_db()

            # First insert — wrong value (simulates the old buggy state).
            insert_snapshots([
                Snapshot(source="fangraphs", snapshot_date="2022-02-24",
                         interval_label="2022report",
                         player_key="julio_rodriguez",
                         player_name="Julio Rodriguez",
                         position="CF", org="SEA",
                         rank=3, fv=37.5, status="active", tools=None),
            ])

            # Second insert — the CORRECT value (simulates re-running the
            # ingester after the CSV was fixed). UPSERT must overwrite.
            insert_snapshots([
                Snapshot(source="fangraphs", snapshot_date="2022-02-24",
                         interval_label="2022report",
                         player_key="julio_rodriguez",
                         player_name="Julio Rodriguez",
                         position="CF", org="SEA",
                         rank=3, fv=65.0, status="active", tools=None),
            ])

            con = sqlite3.connect(str(tmp_db))
            (fv,) = con.execute(
                "SELECT fv FROM snapshots "
                "WHERE player_key='julio_rodriguez' "
                "  AND interval_label='2022report'"
            ).fetchone()
            con.close()
            assert fv == 65.0

    def test_upsert_preserves_tools_when_new_row_omits_them(self, tmp_path):
        # If a re-ingest happens without tools (e.g. an ad-hoc summary-only
        # rerun), we should keep the previously stored tools rather than
        # wiping them.
        tmp_db = tmp_path / "test_prospects.db"
        with patch("storage.DB_PATH", tmp_db):
            init_db()

            insert_snapshots([
                Snapshot(source="fangraphs", snapshot_date="2025-04-01",
                         interval_label="2025report",
                         player_key="some_prospect",
                         player_name="Some Prospect",
                         position="SS", org="LAD", rank=10, fv=55.0,
                         status="active",
                         tools={"hit": 60.0, "raw_pwr": 55.0}),
            ])
            insert_snapshots([
                Snapshot(source="fangraphs", snapshot_date="2025-04-01",
                         interval_label="2025report",
                         player_key="some_prospect",
                         player_name="Some Prospect",
                         position="SS", org="LAD", rank=10, fv=55.0,
                         status="active", tools=None),
            ])

            con = sqlite3.connect(str(tmp_db))
            (tools_json,) = con.execute(
                "SELECT tools_json FROM snapshots "
                "WHERE player_key='some_prospect'"
            ).fetchone()
            con.close()
            assert tools_json is not None
            assert "hit" in tools_json


# ---------------------------------------------------------------------------
# Join-layer collision handling
# ---------------------------------------------------------------------------

class TestNameKeyCollision:
    def _mk_summary(self, player_key, fv, fg_player_id=None, org=None):
        return {
            "player_key":   player_key,
            "fg_player_id": fg_player_id,
            "player_name":  player_key.replace("_", " ").title(),
            "fv":           fv,
            "org":          org,
        }

    def test_julio_rodriguez_higher_fv_wins(self):
        # Mariners superstar (PID=23697, FV=65) collides with SFG SIRP
        # (PID=None after alphanumeric `sa3007992` is coerced to None,
        # FV=37.5). Higher FV must win the bare key.
        mariners = self._mk_summary("julio_rodriguez", 65.0,
                                    fg_player_id=23697, org="SEA")
        sirp = self._mk_summary("julio_rodriguez", 37.5,
                                fg_player_id=None, org="SFG")
        merged = _join_report_set([mariners, sirp], [], [], [])
        assert len(merged) == 1
        assert merged[0]["fv"] == 65.0
        assert merged[0]["org"] == "SEA"

    def test_collision_with_reverse_order_still_keeps_higher_fv(self):
        # Order in the CSV shouldn't matter — higher-FV row wins
        # regardless of which one appears first.
        sirp = self._mk_summary("julio_rodriguez", 37.5, org="SFG")
        mariners = self._mk_summary("julio_rodriguez", 65.0, org="SEA")
        merged = _join_report_set([sirp, mariners], [], [], [])
        assert merged[0]["fv"] == 65.0
        assert merged[0]["org"] == "SEA"

    def test_two_unrelated_players_with_none_pids_still_dedup(self):
        # Both Cristian Santanas had alphanumeric "sa…" PIDs, so both
        # got `fg_player_id=None`. The collision rule must trigger even
        # when both PIDs are None — there are still two distinct humans.
        det = self._mk_summary("cristian_santana", 45.0,
                               fg_player_id=None, org="DET")
        lad = self._mk_summary("cristian_santana", 40.0,
                               fg_player_id=None, org="LAD")
        merged = _join_report_set([det, lad], [], [], [])
        assert len(merged) == 1
        assert merged[0]["fv"] == 45.0
        assert merged[0]["org"] == "DET"
