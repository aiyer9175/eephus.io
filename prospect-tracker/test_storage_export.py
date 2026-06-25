# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the storage.export_timeseries_json output shape, focused on
the tool grades time-series fields (`tools.history`, `tools.source_history`,
`tools.source_recency`) introduced by the consensus-broadening plan."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scrapers import Snapshot
from consensus import build_timeseries
import storage


def _build_export(tmp_path, monkeypatch, snapshots: list[Snapshot]) -> dict:
    """Run a synthetic prospect through build_timeseries +
    export_timeseries_json and return the parsed JSON dict.

    Mocks the DB path so init_db / insert_snapshots write to a per-test
    sqlite file, mirroring TestStorageRoundTripPreservesExtras in
    test_fangraphs_csv.py.
    """
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    storage.insert_snapshots(snapshots)
    ts = build_timeseries(snapshots, single_source_k=0)
    out_path = tmp_path / "timeseries.json"
    storage.export_timeseries_json(ts, out_path)
    return json.loads(out_path.read_text(encoding="utf-8"))


def _player(out: dict, player_key: str) -> dict | None:
    for p in out.get("players", []):
        if p.get("player_key") == player_key:
            return p
    return None


# ---------------------------------------------------------------------------
# tools.source_history shape — every per-source publication should land
# as a list entry with the right keys.
# ---------------------------------------------------------------------------

class TestToolsSourceHistoryEmitted:
    def test_three_fg_intervals_yield_three_entries(self, tmp_path, monkeypatch):
        snaps = [
            Snapshot(source="fangraphs", snapshot_date="2024-02-14",
                     interval_label="2024report",
                     player_key="alpha", player_name="Alpha One",
                     position="SS", org="PIT", rank=10, fv=50.0,
                     status="active",
                     tools={"hit": 50.0, "game_pwr": 55.0,
                            "_extras": {"height": "6' 0"}}),
            Snapshot(source="fangraphs", snapshot_date="2024-07-31",
                     interval_label="2024updated",
                     player_key="alpha", player_name="Alpha One",
                     position="SS", org="PIT", rank=8, fv=55.0,
                     status="active",
                     tools={"hit": 55.0, "game_pwr": 55.0,
                            "_extras": {"height": "6' 0"}}),
            Snapshot(source="fangraphs", snapshot_date="2025-07-31",
                     interval_label="2025updated",
                     player_key="alpha", player_name="Alpha One",
                     position="SS", org="PIT", rank=5, fv=60.0,
                     status="active",
                     tools={"hit": 60.0, "game_pwr": 60.0,
                            "_extras": {"height": "6' 0"}}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "alpha")
        assert p is not None, "exported JSON missing the test prospect"
        sh = (p.get("tools") or {}).get("source_history") or {}
        assert "fangraphs" in sh, f"FG missing from source_history; got {list(sh.keys())}"
        fg_entries = sh["fangraphs"]
        assert len(fg_entries) == 3, f"expected 3 FG entries, got {len(fg_entries)}"
        # Each entry must carry these keys.
        for e in fg_entries:
            assert "snapshot_date" in e
            assert "interval_label" in e
            assert "grades" in e and isinstance(e["grades"], dict)
            assert "extras_present" in e
            assert isinstance(e["extras_present"], bool)
            # grades carry only numeric values, no _extras
            for k, v in e["grades"].items():
                assert k != "_extras"
                assert isinstance(v, (int, float))

    def test_extras_present_flag_reflects_data(self, tmp_path, monkeypatch):
        snaps = [
            # Has _extras
            Snapshot(source="fangraphs", snapshot_date="2025-01-01",
                     interval_label="with_extras",
                     player_key="beta", player_name="Beta Two",
                     position="CF", org="LAD", rank=20, fv=50.0,
                     status="active",
                     tools={"hit": 50.0, "_extras": {"height": "6' 1"}}),
            # No _extras
            Snapshot(source="fangraphs", snapshot_date="2025-06-01",
                     interval_label="without_extras",
                     player_key="beta", player_name="Beta Two",
                     position="CF", org="LAD", rank=18, fv=55.0,
                     status="active",
                     tools={"hit": 55.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "beta")
        fg_entries = (p.get("tools") or {}).get("source_history", {}).get("fangraphs", [])
        # Newest-first so [0] is 2025-06-01 (no extras), [1] is 2025-01-01 (with extras).
        by_date = {e["snapshot_date"]: e for e in fg_entries}
        assert by_date["2025-01-01"]["extras_present"] is True
        assert by_date["2025-06-01"]["extras_present"] is False


# ---------------------------------------------------------------------------
# tools.source_recency — must mark sources as stale when their latest
# publication is older than TOOL_FRESHNESS_DAYS.
# ---------------------------------------------------------------------------

class TestToolsSourceRecencyMarksStale:
    def test_old_source_marked_stale_new_source_fresh(self, tmp_path, monkeypatch):
        today = date.today()
        stale_date = (today - timedelta(days=storage.TOOL_FRESHNESS_DAYS + 30)).isoformat()
        fresh_date = (today - timedelta(days=30)).isoformat()
        snaps = [
            # Old FG snapshot — should be flagged stale
            Snapshot(source="fangraphs", snapshot_date=stale_date,
                     interval_label="ancient",
                     player_key="gamma", player_name="Gamma Three",
                     position="2B", org="HOU", rank=50, fv=50.0,
                     status="active", tools={"hit": 50.0}),
            # Fresh Pipeline snapshot — should NOT be stale
            Snapshot(source="mlb_pipeline", snapshot_date=fresh_date,
                     interval_label="MLB Pipeline Recent",
                     player_key="gamma", player_name="Gamma Three",
                     position="2B", org="HOU", rank=45, fv=55.0,
                     status="active", tools={"hit": 55.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "gamma")
        recency = (p.get("tools") or {}).get("source_recency") or {}
        assert "fangraphs" in recency and "mlb_pipeline" in recency
        assert recency["fangraphs"]["is_stale"] is True, \
            f"old FG snapshot should be stale, got {recency['fangraphs']}"
        assert recency["mlb_pipeline"]["is_stale"] is False, \
            f"fresh Pipeline snapshot should NOT be stale, got {recency['mlb_pipeline']}"
        # stale_days arithmetic — allow ±2 days for date.today() drift
        # between insert and export.
        assert abs(recency["fangraphs"]["stale_days"]
                   - (storage.TOOL_FRESHNESS_DAYS + 30)) <= 2
        assert abs(recency["mlb_pipeline"]["stale_days"] - 30) <= 2


# ---------------------------------------------------------------------------
# tools.source_history ordering — newest-first so the UI dropdown can
# stamp the LATEST pill on the top row of each per-source table.
# ---------------------------------------------------------------------------

class TestToolsHistoryOrdersNewestFirst:
    def test_source_history_newest_first(self, tmp_path, monkeypatch):
        snaps = [
            Snapshot(source="fangraphs", snapshot_date="2023-02-14",
                     interval_label="2023report",
                     player_key="delta", player_name="Delta Four",
                     position="3B", org="NYM", rank=99, fv=40.0,
                     status="active", tools={"hit": 40.0}),
            Snapshot(source="fangraphs", snapshot_date="2025-07-31",
                     interval_label="2025updated",
                     player_key="delta", player_name="Delta Four",
                     position="3B", org="NYM", rank=60, fv=55.0,
                     status="active", tools={"hit": 55.0}),
            Snapshot(source="fangraphs", snapshot_date="2024-02-14",
                     interval_label="2024report",
                     player_key="delta", player_name="Delta Four",
                     position="3B", org="NYM", rank=85, fv=45.0,
                     status="active", tools={"hit": 45.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "delta")
        fg_entries = (p.get("tools") or {}).get("source_history", {}).get("fangraphs", [])
        assert len(fg_entries) == 3
        dates = [e["snapshot_date"] for e in fg_entries]
        # Newest-first — strictly decreasing.
        assert dates == sorted(dates, reverse=True), \
            f"expected newest-first, got {dates}"
        assert dates[0] == "2025-07-31"
        assert dates[-1] == "2023-02-14"

    def test_consensus_history_newest_first(self, tmp_path, monkeypatch):
        """tools.history (the consensus timeline) must also be newest-first."""
        snaps = [
            Snapshot(source="fangraphs", snapshot_date="2024-02-14",
                     interval_label="2024report",
                     player_key="eps", player_name="Eps Five",
                     position="SS", org="PIT", rank=10, fv=50.0,
                     status="active", tools={"hit": 50.0}),
            Snapshot(source="fangraphs", snapshot_date="2025-07-31",
                     interval_label="2025updated",
                     player_key="eps", player_name="Eps Five",
                     position="SS", org="PIT", rank=5, fv=60.0,
                     status="active", tools={"hit": 60.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "eps")
        history = (p.get("tools") or {}).get("history") or []
        assert len(history) >= 2
        dates = [e["snapshot_date"] for e in history]
        assert dates == sorted(dates, reverse=True), \
            f"expected newest-first, got {dates}"


# ---------------------------------------------------------------------------
# Scout-report sidecar — verify the harvester collects writeups from each
# source key the scrapers can emit. Pre-Tier-2 only `fangraphs` populated
# `_extras.report`; now ESPN / Just Baseball / MLB Pipeline do too. The
# harvester is source-agnostic, so the assertion here is per-source
# round-trip from per_source._extras.report → scout_reports.json sidecar.
# ---------------------------------------------------------------------------

class TestScoutReportSidecarPerSource:
    def test_all_four_sources_round_trip_to_sidecar(
            self, tmp_path, monkeypatch):
        # One snapshot per source, each carrying a distinct report string
        # in `tools._extras.report`. The harvester should pick up all
        # four and key them by source in scout_reports.json.
        def snap(source: str, report_text: str) -> Snapshot:
            return Snapshot(
                source=source,
                snapshot_date="2025-07-31",
                interval_label="2025updated",
                player_key="multi_src_player",
                player_name="Multi Src Player",
                position="OF", org="BOS",
                rank=1, fv=60.0, status="active",
                tools={"hit": 55.0, "_extras": {"report": report_text}},
            )

        # Each report's text includes the source key verbatim so a
        # cross-contamination bug would show up as a mismatched tag.
        snaps = [
            snap("fangraphs",
                 "fangraphs tag — plus contact, plus raw power."),
            snap("mlb_pipeline",
                 "mlb_pipeline tag — emerging top-100 prospect."),
            snap("espn",
                 "espn tag — 70-grade bat speed, average defender."),
            snap("just_baseball",
                 "just_baseball tag — floor of an everyday corner OF."),
        ]
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        storage.insert_snapshots(snaps)
        ts = build_timeseries(snaps, single_source_k=0)
        out_path = tmp_path / "timeseries.json"
        storage.export_timeseries_json(ts, out_path)

        sidecar = json.loads(
            (tmp_path / "scout_reports.json").read_text(encoding="utf-8"))
        assert "multi_src_player" in sidecar, \
            f"sidecar missing player; keys={list(sidecar.keys())[:5]}"
        reports = sidecar["multi_src_player"]
        for src in ("fangraphs", "mlb_pipeline", "espn", "just_baseball"):
            assert src in reports, \
                f"sidecar missing source '{src}'; got {list(reports.keys())}"
            # Sidecar shape changed 2026-05: per-source value is now a
            # list of {date, label, text, hash} entries (newest first).
            entries = reports[src]
            assert isinstance(entries, list) and len(entries) >= 1, \
                f"{src} should be a non-empty list, got {entries!r}"
            entry = entries[0]
            assert entry.get("text"), f"empty report text for {src}"
            assert entry.get("date") == "2025-07-31"
            # Each source's text carries its source key verbatim — a
            # cross-source mix-up during harvest would land the wrong tag here.
            assert src in entry["text"], (
                f"{src} report text doesn't carry its own tag; got {entry['text']!r}"
            )
