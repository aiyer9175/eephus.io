"""Tests for stats.compute_age_decimal and the age pipeline."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stats import compute_age_decimal


class TestComputeAgeDecimal:
    def test_exact_year(self):
        # Born exactly 20 years ago today
        assert compute_age_decimal("2006-05-15", as_of=date(2026, 5, 15)) == 20.0

    def test_six_months(self):
        # Born exactly 6 months before as_of -> ~0.5 years
        bd = "2006-05-15"
        assert compute_age_decimal(bd, as_of=date(2006, 11, 15)) == 0.5

    def test_prospect_age_range(self):
        # Realistic prospect ages
        assert compute_age_decimal("2008-01-15", as_of=date(2026, 5, 15)) == 18.3
        assert compute_age_decimal("2003-08-20", as_of=date(2026, 5, 15)) == 22.7
        assert compute_age_decimal("2006-05-03", as_of=date(2026, 5, 15)) == 20.0

    def test_none_input(self):
        assert compute_age_decimal(None) is None
        assert compute_age_decimal("") is None

    def test_malformed_date(self):
        assert compute_age_decimal("not-a-date") is None
        assert compute_age_decimal("2026/05/15") is None  # wrong separator
        assert compute_age_decimal("2026-13-99") is None  # invalid month/day

    def test_future_birth_date(self):
        # Data error: birth date in the future should not return a negative age
        assert compute_age_decimal("2030-01-01", as_of=date(2026, 5, 15)) is None

    def test_leap_year_handling(self):
        # 4 years includes one leap year. 365.25 average should give exactly 4.0
        # for any 4-year span:
        assert compute_age_decimal("2022-05-15", as_of=date(2026, 5, 15)) == 4.0

    def test_rounds_to_one_decimal(self):
        # 100 days = 100/365.25 = 0.27..., rounds to 0.3
        from datetime import timedelta
        as_of = date(2026, 5, 15)
        bd = (as_of - timedelta(days=100)).isoformat()
        age = compute_age_decimal(bd, as_of=as_of)
        assert age == 0.3


class TestAgeInExport:
    def test_age_emitted_with_birth_date(self, tmp_path, monkeypatch):
        """End-to-end: a CSV row with birth_date should produce age in the export."""
        from scrapers import load_manual_rankings, MANUAL_CSV
        import storage
        import json

        # Point storage at a temp DB
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")

        # Write a CSV with one row including birth_date
        csv = tmp_path / "rankings.csv"
        csv.write_text(
            "source,snapshot_date,interval_label,player_name,position,org,rank,fv,status,birth_date\n"
            "fangraphs,2026-02-16,FG 2026 Report,Test Player,SS,PIT,1,70,active,2006-05-03\n"
        )
        rows, birth_dates = load_manual_rankings(csv)
        assert len(rows) == 1
        assert birth_dates == {"test_player": "2006-05-03"}

        # Insert and verify birth date round-trips through storage
        storage.init_db()
        storage.insert_snapshots(rows)
        for key, bd in birth_dates.items():
            storage.upsert_birth_date(key, bd)
        loaded = storage.load_birth_dates()
        assert loaded == {"test_player": "2006-05-03"}

        # Build timeseries and export
        from consensus import build_timeseries
        ts = build_timeseries(storage.load_all_snapshots())
        out = tmp_path / "out.json"
        storage.export_timeseries_json(ts, out, top_n_active=10)
        from storage import load_export_unified as _leu; payload = _leu(out)

        assert payload["active_count"] == 1
        p = payload["players"][0]
        assert p["birth_date"] == "2006-05-03"
        assert p["age"] is not None
        # Player was born May 3 2006 — at any time in 2026 they're 19-20
        assert 19.0 <= p["age"] <= 20.5

    def test_age_none_without_birth_date(self, tmp_path, monkeypatch):
        """Players without a known birth_date should have age=None."""
        import storage, json

        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        from scrapers import Snapshot
        from consensus import build_timeseries
        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report", player_key="unknown_player",
            player_name="Unknown Player", position="SS", org="PIT",
            rank=1, fv=70.0, status="active",
        )
        storage.insert_snapshots([snap])
        ts = build_timeseries(storage.load_all_snapshots())
        out = tmp_path / "out.json"
        storage.export_timeseries_json(ts, out)
        from storage import load_export_unified as _leu; payload = _leu(out)

        p = payload["players"][0]
        assert p["birth_date"] is None
        assert p["age"] is None
