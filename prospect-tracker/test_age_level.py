"""Tests for age_level.score_age_vs_level."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from age_level import score_age_vs_level, LEVEL_BASELINES


class TestScoreAgeVsLevel:
    def test_very_young(self):
        # 18-year-old at AA (baseline 23): -5.0, very young
        r = score_age_vs_level(18.0, "AA")
        assert r.tier == "very-young"
        assert r.diff == -5.0

    def test_young(self):
        # 22-year-old at AA: -1.0, young
        r = score_age_vs_level(22.0, "AA")
        assert r.tier == "young"
        assert r.diff == -1.0

    def test_neutral_at_baseline(self):
        # Exactly the baseline
        r = score_age_vs_level(23.0, "AA")
        assert r.tier == "neutral"
        assert r.diff == 0.0

    def test_neutral_just_under(self):
        # 22.6 at AA: -0.4, still neutral (cutoff is -0.5)
        r = score_age_vs_level(22.6, "AA")
        assert r.tier == "neutral"

    def test_old(self):
        # 24-year-old at AA: +1.0, old for level
        r = score_age_vs_level(24.0, "AA")
        assert r.tier == "old"
        assert r.diff == 1.0

    def test_too_old(self):
        # 25-year-old at A+ (baseline 22): +3.0, too old
        r = score_age_vs_level(25.0, "A+")
        assert r.tier == "too-old"
        assert r.diff == 3.0

    def test_realistic_prospects(self):
        # Jesús Made at 18.8 in AA → very young
        assert score_age_vs_level(18.8, "AA").tier == "very-young"
        # Konnor Griffin at 20.0 in AAA → very young (-4.0)
        r = score_age_vs_level(20.0, "AAA")
        assert r.tier == "very-young"
        assert r.diff == -4.0
        # Eli Willits at 18.4 in A → young (-2.6)
        assert score_age_vs_level(18.4, "A").tier == "very-young"
        # Coby Mayo at 24.4 in AAA → neutral (+0.4)
        assert score_age_vs_level(24.4, "AAA").tier == "neutral"

    def test_unknown_level(self):
        # Rookie complex level isn't in the static baseline table (CPX
        # is intentionally excluded — mixed-age league). Post-rename of
        # Rk → CPX, the same "unknown" disposition should hold for the
        # CPX label.
        r = score_age_vs_level(19.0, "CPX")
        assert r.tier == "unknown"
        assert r.diff is None

    def test_missing_age(self):
        r = score_age_vs_level(None, "AA")
        assert r.tier == "unknown"
        assert r.diff is None

    def test_missing_level(self):
        r = score_age_vs_level(20.0, None)
        assert r.tier == "unknown"
        assert r.diff is None

    def test_diff_rounded_to_one_decimal(self):
        # Tests the diff is rounded — important for display consistency
        r = score_age_vs_level(20.27, "A+")
        assert r.diff == -1.7  # 20.27 - 22 = -1.73, rounds to -1.7


class TestExportIncludesAgeVsLevel:
    def test_export_carries_avl(self, tmp_path, monkeypatch):
        import storage, json
        from scrapers import Snapshot
        from consensus import build_timeseries
        from stats import StatLine

        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()

        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report", player_key="young_aaa_guy",
            player_name="Young AAA Guy", position="SS", org="PIT",
            rank=1, fv=70.0, status="active",
        )
        storage.insert_snapshots([snap])
        # 19-year-old at AAA: very young
        storage.upsert_birth_date("young_aaa_guy", "2007-05-15")
        sl = StatLine(
            player_key="young_aaa_guy", mlbam_id=1, level="AAA", games=20,
            avg=".300", obp=".400", slg=".500", ops=".900",
            hr=5, sb=5, bb_pct=12.0, k_pct=18.0,
            era=None, fip=None, ip=None, k_per_9=None, bb_per_9=None,
            is_pitcher=False, fetched_at="2026-05-16",
        )
        storage.upsert_statlines({"young_aaa_guy": sl}, season=2026)

        ts = build_timeseries(storage.load_all_snapshots())
        out = tmp_path / "out.json"
        from dataclasses import asdict
        storage.export_timeseries_json(
            ts, out,
            statlines={"young_aaa_guy": asdict(sl)},
            top_n_active=10,
        )
        payload = json.loads(out.read_text())
        p = payload["players"][0]
        assert p["age"] is not None
        assert p["age_vs_level"]["tier"] == "very-young"
        # 19-year-old at AAA: diff is ~-5
        assert p["age_vs_level"]["diff"] < -4.5

    def test_export_avl_unknown_without_milb(self, tmp_path, monkeypatch):
        """No stat line → age_vs_level tier is 'unknown'."""
        import storage, json
        from scrapers import Snapshot
        from consensus import build_timeseries

        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        snap = Snapshot(
            source="fangraphs", snapshot_date="2026-02-16",
            interval_label="FG 2026 Report", player_key="il_guy",
            player_name="IL Guy", position="SS", org="PIT",
            rank=1, fv=70.0, status="active",
        )
        storage.insert_snapshots([snap])
        storage.upsert_birth_date("il_guy", "2005-05-15")

        ts = build_timeseries(storage.load_all_snapshots())
        out = tmp_path / "out.json"
        storage.export_timeseries_json(ts, out)
        payload = json.loads(out.read_text())
        p = payload["players"][0]
        assert p["age_vs_level"]["tier"] == "unknown"
