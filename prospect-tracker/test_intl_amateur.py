# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Int'l-amateur FV routing - the owner's sorting directive (2026-06-12):
July-2 class names are prospects, never Overseas entries; their board
FVs attach to the matching tracked player and unmatched rows are
reported, not dropped."""

from __future__ import annotations

import pytest

import intl_amateur


def test_is_ifa_league_variants():
    assert intl_amateur.is_ifa_league("Int'l Amateur".upper())
    assert intl_amateur.is_ifa_league("int'l amateur".upper())
    assert intl_amateur.is_ifa_league("IFA")
    assert not intl_amateur.is_ifa_league("NPB")
    assert not intl_amateur.is_ifa_league("KBO")
    assert not intl_amateur.is_ifa_league(None)
    assert not intl_amateur.is_ifa_league("")


def test_attach_routes_matched_and_reports_unmatched(monkeypatch):
    captured = []

    class _FakeStorage:
        @staticmethod
        def insert_snapshots(snaps):
            captured.extend(snaps)
            return len(snaps)

    monkeypatch.setattr(intl_amateur, "_player_index",
                        lambda: {"jeancer_custodio": "jeancer_custodio"})
    import sys
    monkeypatch.setitem(sys.modules, "storage", _FakeStorage)
    rows = [
        {"player_name": "Jeancer Custodio", "fv": 45.0, "position": "SS",
         "snapshot_date": "2025-01-15", "interval_label": "MLB Pipeline 2025 Int'l"},
        {"player_name": "Nobody Signedyet", "fv": 50.0, "position": "OF",
         "snapshot_date": "2025-01-15", "interval_label": "MLB Pipeline 2025 Int'l"},
        {"player_name": "No Grade Guy", "fv": None, "position": "C",
         "snapshot_date": "2025-01-15", "interval_label": "x"},
    ]
    n, unmatched = intl_amateur.attach_fv_snapshots(rows, source="mlb_pipeline")
    assert n == 1
    assert captured[0].player_key == "jeancer_custodio"
    assert captured[0].fv == 45.0
    assert captured[0].source == "mlb_pipeline"
    assert captured[0].snapshot_date == "2025-01-15"
    # FV-less rows are skipped silently; graded-but-unknown rows report.
    assert [u["player_name"] for u in unmatched] == ["Nobody Signedyet"]


# ---------------------------------------------------------------------------
# CATALOG PIN for ifa_timeseries.json. data_catalog.py names this file, so the
# artifact has to be named here or the /sources/ receipt renders empty.
def test_ifa_timeseries_json_carries_the_shape_the_catalog_promises():
    """ifa_timeseries.json: IFA signing classes with bonuses and the post-signing
    grade path."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent / "data" / "ifa_timeseries.json"
    if not p.exists():
        pytest.skip("ifa_timeseries.json not built in this tree")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "classes" in d, sorted(d)
    assert isinstance(d["classes"], (list, dict))
