# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the storage.export_timeseries_json output shape, focused on
the tool grades time-series fields (`tools.source_history`,
`tools.source_recency`) introduced by the consensus-broadening plan.

v47 payload-slim: `tools.history` is NO LONGER shipped - its only
consumer (bayes _has_top100_pedigree) reads the baked `top100_pedigree`
player flag instead. Pins below cover the strip, the baked flag, the
debuts_full/ per-player shard dir, the intermediate (mid-monthly) export
mode, and the compare-before-write skip."""

from __future__ import annotations

import json
import os
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


def _extras_vintages(today: date | None = None) -> tuple[str, str]:
    """The two snapshot dates of test_extras_present_flag_reflects_data, derived
    from today so the fixture cannot rot.

    They used to be the literals 2025-01-01 and 2025-06-01. `export_timeseries_json`
    drops a player from the active pool when `fv_stale and play_stale`; with no
    career_stats `play_stale` is always True, so the player rode on the newest
    date staying inside `_inactive_cutoff()` = today minus INACTIVE_MONTHS (18).
    2025-06-01 would have left that window on 2026-12-02 (docs/TIME_ROT_BACKLOG.md).

    The newer date sits 60 days back and the older one 151 days before it, the
    literals' original spacing, so their order is kept and both stay well inside
    the 18-month window. Returns (older, newer) as ISO strings.
    """
    newer = (today or date.today()) - timedelta(days=60)
    older = newer - timedelta(days=151)
    return older.isoformat(), newer.isoformat()


_EXTRAS_OLDER, _EXTRAS_NEWER = _extras_vintages()


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
            # Has _extras (the older snapshot)
            Snapshot(source="fangraphs", snapshot_date=_EXTRAS_OLDER,
                     interval_label="with_extras",
                     player_key="beta", player_name="Beta Two",
                     position="CF", org="LAD", rank=20, fv=50.0,
                     status="active",
                     tools={"hit": 50.0, "_extras": {"height": "6' 1"}}),
            # No _extras (the newer snapshot)
            Snapshot(source="fangraphs", snapshot_date=_EXTRAS_NEWER,
                     interval_label="without_extras",
                     player_key="beta", player_name="Beta Two",
                     position="CF", org="LAD", rank=18, fv=55.0,
                     status="active",
                     tools={"hit": 55.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "beta")
        assert p is not None, "exported JSON missing the test prospect"
        fg_entries = (p.get("tools") or {}).get("source_history", {}).get("fangraphs", [])
        # Newest-first so [0] is the newer date (no extras), [1] the older (with extras).
        by_date = {e["snapshot_date"]: e for e in fg_entries}
        assert by_date[_EXTRAS_OLDER]["extras_present"] is True
        assert by_date[_EXTRAS_NEWER]["extras_present"] is False


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

    def test_consensus_history_not_shipped(self, tmp_path, monkeypatch):
        """v47: `tools.history` must NOT ship (payload slim); the
        per-source timeline (`source_history`) still must."""
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
        tools = p.get("tools") or {}
        assert "history" not in tools, \
            "tools.history is stripped in v47 - the baked top100_pedigree flag replaced its only reader"
        assert tools.get("source_history"), "source_history must still ship"


# ---------------------------------------------------------------------------
# v47 - baked Top-100 pedigree flag. The export must OR the Top-100 label
# match across the (unshipped) consensus history AND every source_history
# row, exactly like bayes_trade_value._has_top100_pedigree's legacy walk,
# and bake `top100_pedigree: true` on the player payload (omitted when
# False).
# ---------------------------------------------------------------------------

class TestTop100PedigreeBaked:
    def test_top100_interval_label_bakes_flag(self, tmp_path, monkeypatch):
        snaps = [
            Snapshot(source="mlb_pipeline", snapshot_date="2026-01-22",
                     interval_label="MLB Pipeline 2026 Top 100",
                     player_key="ped_yes", player_name="Ped Yes",
                     position="SS", org="PIT", rank=40, fv=55.0,
                     status="active", tools={"hit": 55.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "ped_yes")
        assert p.get("top100_pedigree") is True

    def test_no_top100_label_omits_flag(self, tmp_path, monkeypatch):
        snaps = [
            Snapshot(source="fangraphs", snapshot_date="2026-02-14",
                     interval_label="2026report",
                     player_key="ped_no", player_name="Ped No",
                     position="SS", org="PIT", rank=40, fv=55.0,
                     status="active", tools={"hit": 55.0}),
        ]
        out = _build_export(tmp_path, monkeypatch, snaps)
        p = _player(out, "ped_no")
        assert "top100_pedigree" not in p, \
            "flag must be OMITTED (not false) when no Top-100 label exists"


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


# ---------------------------------------------------------------------------
# Farm grade / rank determinism: building the tree twice from the SAME fixed DB
# must yield identical farm_rank + letter + farm_score for every org. This is the
# guard behind "why does the farm ranking move each run_monthly": the answer is
# 100% INPUT drift (consensus / pool / graduations), NEVER stochasticity -- there
# is no RNG anywhere in the farm-tree math, and this pins that invariant.
# ---------------------------------------------------------------------------

_DET_ORGS = ["ARI", "ATL", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL", "DET",
             "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "OAK",
             "PHI", "PIT", "SD", "SF", "SEA", "STL", "TB", "TEX", "TOR", "WSH"]


def _det_vintages() -> tuple[tuple[str, str], ...]:
    """The two snapshot vintages, derived from TODAY so this fixture cannot rot.

    They used to be the literals 2024-02-14 and 2025-02-12, and that made the test
    time-dependent in a way that failed silently. `export_timeseries_json` drops a
    player from the active pool when `fv_stale and play_stale` (storage.py:10924).
    `play_stale` is unconditionally True here because the test passes no
    career_stats, so the whole fixture rode on `fv_stale`, which compares the latest
    grade against `_inactive_cutoff()` = today minus INACTIVE_MONTHS (18).

    On 2026-08-12 that cutoff was 2025-02-12 and `2025-02-12 < 2025-02-12` is False,
    so the pool survived. On 2026-08-13 the cutoff became 2025-02-13, the newest
    vintage fell one day behind it, all 60 players went inactive, and org_summary
    came back EMPTY. The determinism assertions still passed at that point, because
    two empty dicts are trivially equal; only the `len(a) >= 20` guard caught it.
    That guard is the reason this was a red and not a silent pass forever.

    Anchoring on today keeps both vintages inside the 18-month window, and taking
    the older one exactly 365 days back guarantees the two interval_labels land in
    different calendar years so they stay distinct publications.
    """
    recent = date.today() - timedelta(days=45)
    older = recent - timedelta(days=365)
    return ((older.isoformat(), f"{older.year}report"),
            (recent.isoformat(), f"{recent.year}report"))


def _det_snaps() -> list[Snapshot]:
    """Two graded fangraphs prospects per org across two vintages, FV spread so the
    30 orgs get distinct farm scores (a mid-pack tie would still be deterministic,
    but distinct scores exercise the ordinal rank + letter buckets)."""
    snaps: list[Snapshot] = []
    for i, org in enumerate(_DET_ORGS):
        for j in range(2):
            fv = 40.0 + (i % 8) * 3 + j * 5
            key = f"{org.lower()}_p{j}"
            for sd, lbl in _det_vintages():
                snaps.append(Snapshot(
                    source="fangraphs", snapshot_date=sd, interval_label=lbl,
                    player_key=key, player_name=f"{org} Prospect {j}",
                    position="SS", org=org, rank=10 + i, fv=fv, status="active",
                    tools={"hit": fv, "game_pwr": fv - 5.0}))
    return snaps


class TestFarmTreeDeterminism:
    def test_farm_rank_and_letter_are_deterministic(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        snaps = _det_snaps()
        storage.insert_snapshots(snaps)

        def _build(name: str) -> dict:
            ts = build_timeseries(snaps, single_source_k=0)
            out = tmp_path / name
            storage.export_timeseries_json(ts, out)
            data = json.loads(out.read_text(encoding="utf-8"))
            return {o["org"]: o for o in data.get("org_summary", [])}

        a = _build("a.json")
        b = _build("b.json")
        assert set(a) == set(b), (sorted(a), sorted(b))
        assert len(a) >= 20, f"expected the synthetic 30-org pool, got {len(a)}"
        for org in a:
            assert a[org].get("farm_rank") == b[org].get("farm_rank"), (org, "farm_rank", a[org].get("farm_rank"), b[org].get("farm_rank"))
            assert a[org].get("farm_score") == b[org].get("farm_score"), (org, "farm_score")
            la = (a[org].get("letter_by_window") or {}).get("7y")
            lb = (b[org].get("letter_by_window") or {}).get("7y")
            assert la == lb, (org, "letter_7y", la, lb)
        # ranks form a proper 1..N permutation (no dupes / gaps from the ordinal sort)
        ranks = sorted(o.get("farm_rank") for o in a.values() if o.get("farm_rank") is not None)
        assert ranks == list(range(1, len(ranks) + 1)), ranks


# ---------------------------------------------------------------------------
# v47 - debuts_full/{player_key}.json shards, the intermediate (mid-monthly)
# export skip list, and the compare-before-write dump path.
# ---------------------------------------------------------------------------

def _mixed_snaps() -> list[Snapshot]:
    """One debuted graduate + one active prospect."""
    return [
        Snapshot(source="fangraphs", snapshot_date="2025-02-12",
                 interval_label="2025report",
                 player_key="grad_one", player_name="Grad One",
                 position="SS", org="PIT", rank=12, fv=55.0,
                 status="debuted", tools={"hit": 55.0}),
        Snapshot(source="fangraphs", snapshot_date="2026-02-14",
                 interval_label="2026report",
                 player_key="active_one", player_name="Active One",
                 position="CF", org="PIT", rank=30, fv=50.0,
                 status="active", tools={"hit": 50.0}),
    ]


class TestDebutsFullShards:
    def test_every_graduate_gets_a_full_shard(self, tmp_path, monkeypatch):
        out = _build_export(tmp_path, monkeypatch, _mixed_snaps())
        grads = json.loads((tmp_path / "debuts.json").read_text(encoding="utf-8"))
        assert grads, "synthetic debuted prospect missing from debuts.json"
        # Advertised on the dir contract, mirroring player_detail/.
        assert out["_slices_dir"]["debuts_full"] == "debuts_full/"
        for g in grads:
            shard = tmp_path / "debuts_full" / f"{g['player_key']}.json"
            assert shard.exists(), \
                f"missing debuts_full shard for {g['player_key']}"
            # The shard IS the complete debuts.json record for the player.
            assert json.loads(shard.read_text(encoding="utf-8")) == g

    def test_departed_graduate_shard_removed(self, tmp_path, monkeypatch):
        stale_dir = tmp_path / "debuts_full"
        stale_dir.mkdir(parents=True)
        (stale_dir / "ghost_grad.json").write_text("{}", encoding="utf-8")
        _build_export(tmp_path, monkeypatch, _mixed_snaps())
        assert not (stale_dir / "ghost_grad.json").exists(), \
            "stale debuts_full shard for a departed graduate must be removed"
        assert (stale_dir / "grad_one.json").exists()


class TestIntermediateExportSkipsSidecars:
    def test_intermediate_writes_only_boot_debuts_rosters(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        snaps = _mixed_snaps()
        storage.insert_snapshots(snaps)
        ts = build_timeseries(snaps, single_source_k=0)
        out_path = tmp_path / "timeseries.json"
        storage.export_timeseries_json(ts, out_path, intermediate=True)
        # Kept: boot + debuts + rosters (monthly-tail readers exist).
        assert out_path.exists()
        assert (tmp_path / "debuts.json").exists()
        assert (tmp_path / "rosters_by_org.json").exists()
        # Skipped: frontend-only sidecars the chained d9 rewrites.
        for skipped in ("debuts_lite.json", "inactive.json",
                        "scout_reports.json", "scout_reports_0.json",
                        "mlb_trade_players.json"):
            assert not (tmp_path / skipped).exists(), \
                f"{skipped} must be skipped on the intermediate export"
        for skipped_dir in ("pitch_plots", "player_detail", "debuts_full"):
            assert not (tmp_path / skipped_dir).exists(), \
                f"{skipped_dir}/ must be skipped on the intermediate export"


class TestCompareBeforeWrite:
    def test_unchanged_payloads_not_rewritten_boot_still_is(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
        storage.init_db()
        snaps = _mixed_snaps()
        storage.insert_snapshots(snaps)
        out_path = tmp_path / "timeseries.json"
        storage.export_timeseries_json(
            build_timeseries(snaps, single_source_k=0), out_path)
        shard = tmp_path / "debuts_full" / "grad_one.json"
        assert shard.exists()
        sentinel = 946684800  # 2000-01-01, unmistakably old
        os.utime(shard, (sentinel, sentinel))
        os.utime(tmp_path / "debuts.json", (sentinel, sentinel))
        os.utime(out_path, (sentinel, sentinel))
        # Re-export from the same DB state: identical bytes -> writes
        # skipped, mtimes untouched (this is what lets rsync quick-check
        # and the deploy box's nightly gzip skip unchanged files).
        storage.export_timeseries_json(
            build_timeseries(snaps, single_source_k=0), out_path)
        assert shard.stat().st_mtime == sentinel, \
            "unchanged per-player shard must not be rewritten"
        assert (tmp_path / "debuts.json").stat().st_mtime == sentinel, \
            "unchanged debuts.json must not be rewritten"
        # The boot payload carries a per-run stamp (meta.generated_at) and
        # must keep writing unconditionally.
        assert out_path.stat().st_mtime != sentinel, \
            "boot timeseries.json must still write every export"
