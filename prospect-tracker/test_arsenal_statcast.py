"""Tests for fetch_pitch_arsenal and fetch_statcast_metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from stats import (
    fetch_pitch_arsenal, fetch_statcast_metrics,
    PitchArsenal, StatcastMetrics,
    _HARD_PITCH_CODES,
)


def _mock_resp(data: dict, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


# ── Pitch Arsenal ──────────────────────────────────────────────────────────

class TestFetchPitchArsenal:
    def _arsenal_response(self, pitches: list[dict]) -> dict:
        """Build a fake pitchArsenal API response."""
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

    def test_basic_arsenal(self):
        fake = self._arsenal_response([
            {"code": "FF", "name": "4-Seam Fastball", "speed": 96.4, "pct": 0.45},
            {"code": "SL", "name": "Slider",           "speed": 87.1, "pct": 0.30},
            {"code": "CH", "name": "Changeup",          "speed": 84.2, "pct": 0.25},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("pitcher_key", 12345, 2026)

        assert pa is not None
        assert isinstance(pa, PitchArsenal)
        assert len(pa.pitches) == 3
        assert pa.pitches[0]["pitch_type"] == "FF"   # highest usage first
        assert pa.fb_velo == 96.4

    def test_fastball_velo_picks_highest_usage_hard_pitch(self):
        # Both FF and SI are hard pitches; FF has higher usage
        fake = self._arsenal_response([
            {"code": "FF", "name": "4-Seam",  "speed": 97.0, "pct": 0.40},
            {"code": "SI", "name": "Sinker",   "speed": 95.5, "pct": 0.20},
            {"code": "CB", "name": "Curveball","speed": 79.0, "pct": 0.40},
        ])
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            pa = fetch_pitch_arsenal("key", 1, 2026)

        assert pa.fb_velo == 97.0   # FF, not CB

    def test_no_fastball_gives_none_fb_velo(self):
        # Pitcher with only breaking balls (unusual but handle it)
        fake = self._arsenal_response([
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
        fake = self._arsenal_response([
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


# ── Statcast Metrics ───────────────────────────────────────────────────────

class TestFetchStatcastMetrics:
    def _sc_response(self, ev=88.5, hh=0.38, la=12.1, bp=0.08) -> dict:
        return {
            "stats": [{
                "splits": [{
                    "stat": {
                        "exitVelocity": ev,
                        "hardHitPercent": hh,
                        "launchAngle": la,
                        "barrelPercent": bp,
                    }
                }]
            }]
        }

    def test_hitter_metrics(self):
        fake = self._sc_response(ev=92.3, hh=0.44, la=14.2, bp=0.12)
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sc = fetch_statcast_metrics("hitter_key", 1, 2026, is_pitcher=False)

        assert sc is not None
        assert isinstance(sc, StatcastMetrics)
        assert sc.exit_velo == 92.3
        assert sc.hard_hit_pct == 44.0   # converted from 0.44 to percent
        assert sc.launch_angle == 14.2
        assert sc.barrel_pct == 12.0
        assert sc.is_pitcher is False

    def test_pitcher_metrics(self):
        fake = self._sc_response(ev=88.1, hh=0.31, la=10.0, bp=0.05)
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sc = fetch_statcast_metrics("pitcher_key", 1, 2026, is_pitcher=True)

        assert sc is not None
        assert sc.is_pitcher is True
        assert sc.exit_velo == 88.1
        assert sc.hard_hit_pct == 31.0

    def test_all_none_fields_returns_none(self):
        """When the API returns no Statcast data (e.g. A-ball), return None."""
        fake = {"stats": [{"splits": [{"stat": {}}]}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sc = fetch_statcast_metrics("key", 1, 2026)
        assert sc is None

    def test_empty_splits_returns_none(self):
        fake = {"stats": [{"splits": []}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sc = fetch_statcast_metrics("key", 1, 2026)
        assert sc is None

    def test_api_error_returns_none(self):
        with patch("stats.requests.get", side_effect=Exception("timeout")), \
             patch("stats.time.sleep"):
            sc = fetch_statcast_metrics("key", 1, 2026)
        assert sc is None

    def test_partial_metrics_accepted(self):
        """Some fields present, some missing — accept the partial data."""
        fake = {"stats": [{"splits": [{
            "stat": {"exitVelocity": 90.0, "hardHitPercent": 0.35}
        }]}]}
        with patch("stats.requests.get", return_value=_mock_resp(fake)), \
             patch("stats.time.sleep"):
            sc = fetch_statcast_metrics("key", 1, 2026)

        assert sc is not None
        assert sc.exit_velo == 90.0
        assert sc.hard_hit_pct == 35.0
        assert sc.launch_angle is None
        assert sc.barrel_pct is None


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

    def test_statcast_upsert_and_load(self, tmp_path, monkeypatch):
        import storage
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        sc = StatcastMetrics(
            player_key="hitter1", mlbam_id=222, season=2026,
            is_pitcher=False,
            exit_velo=92.5, hard_hit_pct=41.0,
            launch_angle=13.2, barrel_pct=9.8,
            fetched_at="2026-05-17",
        )
        storage.upsert_statcast_metrics({"hitter1": sc}, 2026)
        loaded = storage.load_statcast_metrics()
        assert "hitter1" in loaded
        assert loaded["hitter1"]["exit_velo"] == 92.5
        assert loaded["hitter1"]["hard_hit_pct"] == 41.0

    def test_export_includes_arsenal_and_statcast(self, tmp_path, monkeypatch):
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
            pitches=[{"pitch_type": "FF", "pitch_name": "4-Seam",
                      "avg_speed": 97.0, "usage_pct": 0.5}],
            fb_velo=97.0, fetched_at="2026-05-17",
        )
        sc = StatcastMetrics(
            player_key="test_pitcher", mlbam_id=1, season=2026,
            is_pitcher=True, exit_velo=88.1, hard_hit_pct=30.5,
            launch_angle=10.0, barrel_pct=5.5, fetched_at="2026-05-17",
        )
        out = tmp_path / "out.json"
        storage.export_timeseries_json(
            ts, out,
            pitch_arsenals={"test_pitcher": asdict(pa)},
            statcast_metrics={"test_pitcher": asdict(sc)},
        )
        payload = json.loads(out.read_text())
        p = payload["players"][0]
        assert p["pitch_arsenal"] is not None
        assert p["pitch_arsenal"]["fb_velo"] == 97.0
        assert p["pitch_arsenal"]["pitches"][0]["pitch_type"] == "FF"
        assert p["statcast"] is not None
        assert p["statcast"]["exit_velo"] == 88.1
        assert p["statcast"]["hard_hit_pct"] == 30.5
