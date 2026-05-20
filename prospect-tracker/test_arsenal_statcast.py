"""Tests for fetch_pitch_arsenal and fetch_sabermetrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from stats import (
    fetch_pitch_arsenal, fetch_sabermetrics,
    PitchArsenal, Sabermetrics,
    _HARD_PITCH_CODES,
)


def _mock_resp(data: dict, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


# ── Pitch Arsenal ──────────────────────────────────────────────────────────
# The MLB Stats API renamed `pitchType` → `type` and `avgSpeed` →
# `averageSpeed`. The fetcher prefers the new field names and falls back
# to the legacy ones. Tests cover both shapes.

class TestFetchPitchArsenal:
    def _arsenal_response_new(self, pitches: list[dict]) -> dict:
        """Build a fake pitchArsenal response in the current API shape."""
        return {
            "stats": [{
                "splits": [
                    {
                        "stat": {
                            "type": {"code": p["code"], "description": p["name"]},
                            "averageSpeed": p["speed"],
                            "percentage": p["pct"],
                        }
                    }
                    for p in pitches
                ]
            }]
        }

    def _arsenal_response_legacy(self, pitches: list[dict]) -> dict:
        """Build a fake response in the pre-rename API shape (fallback path)."""
        return {
            "stats": [{
                "splits": [
                    {
                        "stat": {
                            "pitchType": {"code": p["code"], "description": p["name"]},
                            "avgSpeed": p["speed"],
                            "percentage": p["pct"],
                        }
                    }
                    for p in pitches
                ]
            }]
        }

    def test_basic_arsenal_current_api_shape(self):
        fake = self._arsenal_response_new([
            {"code": "FF", "name": "Four-seam FB", "speed": 96.4, "pct": 0.45},
            {"code": "SL", "name": "Slider",       "speed": 87.1, "pct": 0.30},
            {"code": "CH", "name": "Changeup",     "speed": 84.2, "pct": 0.25},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("pitcher_key", 12345, 2026)

        assert pa is not None
        assert isinstance(pa, PitchArsenal)
        assert len(pa.pitches) == 3
        assert pa.pitches[0]["pitch_type"] == "FF"   # highest usage first
        assert pa.fb_velo == 96.4

    def test_legacy_api_shape_still_parses(self):
        """Fallback path: handles the pre-rename `pitchType` / `avgSpeed` shape."""
        fake = self._arsenal_response_legacy([
            {"code": "FF", "name": "4-Seam Fastball", "speed": 95.0, "pct": 0.60},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("k", 1, 2026)
        assert pa is not None
        assert pa.pitches[0]["pitch_type"] == "FF"
        assert pa.fb_velo == 95.0

    def test_fastball_velo_picks_highest_usage_hard_pitch(self):
        fake = self._arsenal_response_new([
            {"code": "FF", "name": "4-Seam",  "speed": 97.0, "pct": 0.40},
            {"code": "SI", "name": "Sinker",   "speed": 95.5, "pct": 0.20},
            {"code": "CB", "name": "Curveball","speed": 79.0, "pct": 0.40},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("key", 1, 2026)

        assert pa.fb_velo == 97.0   # FF, not CB

    def test_no_fastball_gives_none_fb_velo(self):
        fake = self._arsenal_response_new([
            {"code": "SL", "name": "Slider",   "speed": 87.0, "pct": 0.55},
            {"code": "CB", "name": "Curveball","speed": 79.0, "pct": 0.45},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("key", 1, 2026)

        assert pa is not None
        assert pa.fb_velo is None

    def test_empty_splits_returns_none(self):
        fake = {"stats": [{"splits": []}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("key", 1, 2026)
        assert pa is None

    def test_api_error_returns_none(self):
        with patch("stats.requests.get", side_effect=Exception("timeout")), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("key", 1, 2026)
        assert pa is None

    def test_pitches_sorted_by_usage(self):
        fake = self._arsenal_response_new([
            {"code": "CH", "name": "Changeup", "speed": 84.0, "pct": 0.10},
            {"code": "FF", "name": "4-Seam",   "speed": 96.0, "pct": 0.55},
            {"code": "SL", "name": "Slider",   "speed": 87.0, "pct": 0.35},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("key", 1, 2026)

        usages = [p["usage_pct"] for p in pa.pitches]
        assert usages == sorted(usages, reverse=True)

    def test_hard_pitch_codes_coverage(self):
        # Verify the set includes the four main velocity pitch types
        assert "FF" in _HARD_PITCH_CODES  # 4-Seam
        assert "SI" in _HARD_PITCH_CODES  # Sinker
        assert "FC" in _HARD_PITCH_CODES  # Cutter
        assert "FT" in _HARD_PITCH_CODES  # 2-Seam


# ── Sabermetrics (wRC+ / xFIP / wOBA / FIP) ────────────────────────────────

class TestFetchSabermetrics:
    def _hitter_response(self, *, wrc=140.0, woba=0.365, war=3.5):
        return {"stats": [{"splits": [{"stat": {
            "wRcPlus": wrc, "woba": woba, "war": war,
        }}]}]}

    def _pitcher_response(self, *, xfip=3.45, fip=3.22, fip_minus=78.5,
                          era_minus=82.0, war=2.5):
        return {"stats": [{"splits": [{"stat": {
            "xfip": xfip, "fip": fip, "fipMinus": fip_minus,
            "eraMinus": era_minus, "war": war,
        }}]}]}

    def test_hitter_sabermetrics(self):
        fake = self._hitter_response(wrc=219.8, woba=0.476, war=11.33)
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sm = fetch_sabermetrics("hitter_key", 1, 2024, is_pitcher=False)

        assert sm is not None
        assert isinstance(sm, Sabermetrics)
        assert sm.is_pitcher is False
        assert sm.wrc_plus == 219.8
        assert sm.woba == 0.476
        assert sm.war == 11.33
        # Pitcher fields stay None on a hitter
        assert sm.xfip is None and sm.fip is None and sm.fip_minus is None

    def test_pitcher_sabermetrics(self):
        fake = self._pitcher_response(xfip=3.99, fip=3.69, fip_minus=88.4,
                                       era_minus=85.8, war=1.78)
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sm = fetch_sabermetrics("pitcher_key", 1, 2024, is_pitcher=True)

        assert sm is not None
        assert sm.is_pitcher is True
        assert sm.xfip == 3.99
        assert sm.fip == 3.69
        assert sm.fip_minus == 88.4
        assert sm.era_minus == 85.8
        assert sm.war == 1.78
        assert sm.wrc_plus is None and sm.woba is None

    def test_all_none_fields_returns_none(self):
        """When the API returns nothing useful (typical for MiLB seasons)."""
        fake = {"stats": [{"splits": [{"stat": {}}]}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sm = fetch_sabermetrics("key", 1, 2026)
        assert sm is None

    def test_empty_splits_returns_none(self):
        fake = {"stats": [{"splits": []}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sm = fetch_sabermetrics("key", 1, 2026)
        assert sm is None

    def test_api_error_returns_none(self):
        with patch("stats.requests.get", side_effect=Exception("timeout")), \
             patch("stats.time.sleep"):
            sm = fetch_sabermetrics("key", 1, 2026)
        assert sm is None

    def test_partial_metrics_accepted(self):
        """Some fields present, some missing — accept the partial data."""
        fake = {"stats": [{"splits": [{"stat": {"wRcPlus": 130.0}}]}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sm = fetch_sabermetrics("key", 1, 2026, is_pitcher=False)
        assert sm is not None
        assert sm.wrc_plus == 130.0
        assert sm.woba is None
        assert sm.war is None


# ── Storage round-trip ─────────────────────────────────────────────────────

class TestStorageRoundTrip:
    def test_arsenal_upsert_and_load(self, tmp_path, monkeypatch):
        import storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        pa = PitchArsenal(
            player_key="pitcher1", mlbam_id=111, season=2026,
            pitches=[{"pitch_type": "FF", "pitch_name": "4-Seam", "avg_speed": 96.0, "usage_pct": 0.5}],
            fb_velo=96.0, fetched_at="2026-05-17",
        )
        storage.upsert_pitch_arsenals({"pitcher1": pa}, 2026)
        loaded = storage.load_pitch_arsenals()
        assert "pitcher1" in loaded
        assert loaded["pitcher1"]["fb_velo"] == 96.0
        assert loaded["pitcher1"]["pitches"][0]["pitch_type"] == "FF"

    def test_sabermetrics_upsert_and_load(self, tmp_path, monkeypatch):
        import storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        sm = Sabermetrics(
            player_key="hitter1", mlbam_id=222, season=2026,
            is_pitcher=False,
            wrc_plus=140.0, woba=0.365,
            xfip=None, fip=None, fip_minus=None, era_minus=None,
            war=3.5, fetched_at="2026-05-17",
        )
        storage.upsert_sabermetrics({"hitter1": sm}, 2026)
        loaded = storage.load_sabermetrics()
        assert "hitter1" in loaded
        assert loaded["hitter1"]["wrc_plus"] == 140.0
        assert loaded["hitter1"]["woba"] == 0.365

    def test_export_includes_arsenal_and_sabermetrics(self, tmp_path, monkeypatch):
        import storage, json
        from scrapers import Snapshot
        from consensus import build_timeseries
        from dataclasses import asdict

        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report",
            player_key="test_pitcher", player_name="Test Pitcher",
            position="RHP", org="PIT", rank=1, fv=60.0, status="active",
        )
        storage.insert_snapshots([snap])
        ts = build_timeseries(storage.load_all_snapshots())

        pa = PitchArsenal(
            player_key="test_pitcher", mlbam_id=1, season=2026,
            pitches=[{"pitch_type": "FF", "pitch_name": "Four-seam FB",
                      "avg_speed": 97.0, "usage_pct": 0.5}],
            fb_velo=97.0, fetched_at="2026-05-17",
        )
        sm = Sabermetrics(
            player_key="test_pitcher", mlbam_id=1, season=2026,
            is_pitcher=True,
            wrc_plus=None, woba=None,
            xfip=3.42, fip=3.10, fip_minus=80.0, era_minus=78.0,
            war=2.4, fetched_at="2026-05-17",
        )
        out = tmp_path / "out.json"
        storage.export_timeseries_json(
            ts, out,
            pitch_arsenals={"test_pitcher": asdict(pa)},
            sabermetrics={"test_pitcher": asdict(sm)},
        )
        from storage import load_export_unified as _leu; payload = _leu(out)
        p = payload["players"][0]
        assert p["pitch_arsenal"] is not None
        assert p["pitch_arsenal"]["fb_velo"] == 97.0
        assert p["pitch_arsenal"]["pitches"][0]["pitch_type"] == "FF"
        assert p["sabermetrics"] is not None
        assert p["sabermetrics"]["xfip"] == 3.42
        assert p["sabermetrics"]["fip_minus"] == 80.0
