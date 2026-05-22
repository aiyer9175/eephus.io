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

from fangraphs_csv import _compute_fg_canonical_owners, _disambiguate_key, _join_report_set
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


# ---------------------------------------------------------------------------
# Cross-CSV disambiguation (different humans sharing a name across cycles)
# ---------------------------------------------------------------------------

class TestCrossCsvDisambiguation:
    """Two distinct humans normalize to the same player_key across
    multiple FG CSVs. The within-CSV collision rule alone can't fix it
    because each cycle only has one row for the lesser player. The
    canonical-owner precomputation routes the lesser human to a suffixed
    player_key so the prominent prospect's timeline stays clean.

    Real example: Julio Rodriguez (Mariners CF, PID 23697) appears in
    2021report, 2021updated, 2022report. The 2022updated CSV omits him
    (he had already graduated to MLB) but DOES contain a different Julio
    Rodriguez — SFG SIRP, PID sa3007992, FV 35+. Without disambiguation,
    that pitcher's snapshot ends up on the Mariners CF's timeline,
    showing a phantom FV=37.5 entry plus FB/CB/sits-velo pitcher tools
    on a hitter's profile."""

    def _slug_grp(self, slug, *rows):
        """Build the {summary: path, ...} shape `_compute_fg_canonical_owners`
        expects — for these tests we'll bypass file I/O by patching
        `_read_csv_rows` (see fixtures below)."""
        return {"summary": slug, "_rows": rows}

    def test_canonical_owner_picks_most_frequent_pid(self, monkeypatch):
        # Build a 4-cycle history: pkey=julio_rodriguez appears with
        # PID 23697 in 3 cycles and PID sa3007992 in 1. Canonical = 23697.
        from fangraphs_csv import _read_csv_rows
        cycles = {
            "2021report":  [{"Name": "Julio Rodríguez", "PlayerId": "23697",     "FV": "60"}],
            "2021updated": [{"Name": "Julio Rodríguez", "PlayerId": "23697",     "FV": "60"}],
            "2022report":  [{"Name": "Julio Rodríguez", "PlayerId": "23697",     "FV": "65"},
                            {"Name": "Julio Rodriguez", "PlayerId": "sa3007992", "FV": "35+"}],
            "2022updated": [{"Name": "Julio Rodriguez", "PlayerId": "sa3007992", "FV": "35+"}],
        }
        def fake_read(path):
            return cycles[path]
        monkeypatch.setattr("fangraphs_csv._read_csv_rows", fake_read)
        groups = [{"summary": slug} for slug in cycles]
        owners = _compute_fg_canonical_owners(groups)
        assert owners.get("julio_rodriguez") == "23697"

    def test_disambiguate_key_bare_when_pid_matches_canonical(self):
        owners = {"julio_rodriguez": "23697"}
        assert _disambiguate_key("julio_rodriguez", "23697", owners) \
            == "julio_rodriguez"

    def test_disambiguate_key_suffixed_when_pid_differs(self):
        owners = {"julio_rodriguez": "23697"}
        assert _disambiguate_key("julio_rodriguez", "sa3007992", owners) \
            == "julio_rodriguez__sa3007992"

    def test_disambiguate_key_passthrough_when_no_collision(self):
        # Player_key not in owners map → no disambiguation, bare key.
        owners = {"some_other_player": "12345"}
        assert _disambiguate_key("aaron_judge", "592450", owners) \
            == "aaron_judge"

    def test_disambiguate_key_all_noid_sentinel(self):
        # Edge case: every colliding row is PID-less. Each row gets a
        # suffix; canonical owner is the literal sentinel.
        owners = {"todd_peterson": "__all_noid__"}
        assert _disambiguate_key("todd_peterson", None, owners) \
            == "todd_peterson__noid"
        assert _disambiguate_key("todd_peterson", "sa1234", owners) \
            == "todd_peterson__sa1234"

    def test_julio_rodriguez_2022updated_not_under_canonical_key(self):
        """Top-level integration: after the cross-CSV fix runs, the
        Mariners CF (canonical julio_rodriguez) must NOT have a 2022updated
        FG snapshot — the only "Julio Rodriguez" in that cycle is the SFG
        SIRP, and his data belongs under a different player_key."""
        if not DB_PATH.exists():
            pytest.skip(f"prospects.db not at {DB_PATH}; skip")
        con = sqlite3.connect(str(DB_PATH))
        rows = con.execute(
            "SELECT fv FROM snapshots "
            "WHERE player_key='julio_rodriguez' "
            "  AND source='fangraphs' "
            "  AND interval_label='2022updated'"
        ).fetchall()
        con.close()
        assert not rows, (
            f"Mariners Julio Rodriguez should have no 2022updated FG "
            f"snapshot (he had graduated to MLB by August 2022). "
            f"Found: {rows}. The SFG SIRP's snapshot should live under "
            f"julio_rodriguez__sa3007992 instead."
        )
