# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""StatsAPI-listed retirees leave the projections and Team Outlook (owner answer
Q3, 2026-10-22, 'Drop MLB-listed retirees').

A retiree is a player StatsAPI lists inactive who has not played this season
(Clayton Kershaw: active false, last played 2025-09-28; he was projected for 5Y
0.4 WAR with LAD). mlb_people_status caches the status; proj_export drops those
ids from the veteran rows and the depth pool. No network: the fetcher runs on a
fake transport and a tmp cache, and conftest keeps every other test offline."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import mlb_people_status as mps
import proj_export as pe

ROOT = Path(__file__).parent
_REAL_REFRESH = mps.refresh          # saved before conftest swaps it per test
SRC = (ROOT / "proj_export.py").read_text(encoding="utf-8")


def test_retired_needs_inactive_and_no_game_this_season():
    rows = {
        "477132": {"active": False, "lastPlayedDate": "2025-09-28"},   # Kershaw
        "1": {"active": False, "lastPlayedDate": "2026-05-01"},        # played this year
        "2": {"active": True, "lastPlayedDate": "2024-09-01"},         # on a roster, injured
        "3": {"active": False, "lastPlayedDate": None},
        "4": {},
    }
    assert mps.retired_mlbams(rows, 2026) == {477132, 3}


class _Resp:
    def __init__(self, people):
        self._people = people

    def raise_for_status(self):
        return None

    def json(self):
        return {"people": self._people}


def test_refresh_fetches_only_stale_ids_in_batches_and_writes_the_cache(tmp_path, monkeypatch):
    import requests
    calls = []

    def fake_get(url, params=None, timeout=None):
        ids = [int(x) for x in params["personIds"].split(",")]
        calls.append(ids)
        return _Resp([{"id": i, "active": i != 7, "lastPlayedDate": "2025-09-28"} for i in ids])

    monkeypatch.setattr(requests, "get", fake_get)
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"5": {"active": True, "fetched": 1000.0}}), encoding="utf-8")
    ids = list(range(1, 400))
    rows = _REAL_REFRESH(ids, path=path, now=1000.0 + 3600)
    # id 5 is fresh (an hour old), every other id is fetched, 150 per request
    assert sum(len(c) for c in calls) == 398 and all(len(c) <= mps.BATCH for c in calls)
    assert 5 not in {i for c in calls for i in c}
    assert rows["7"]["active"] is False and json.loads(path.read_text(encoding="utf-8"))["7"]["active"] is False
    calls.clear()
    _REAL_REFRESH(ids, path=path, now=1000.0 + 7200)
    assert calls == []                      # nothing stale an hour later


def test_refresh_keeps_the_cache_when_the_fetch_fails(tmp_path, monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"9": {"active": False, "lastPlayedDate": "2024-09-01", "fetched": 0}}),
                    encoding="utf-8")
    rows = _REAL_REFRESH([9, 10], path=path, now=10 ** 9)
    assert rows == {"9": {"active": False, "lastPlayedDate": "2024-09-01", "fetched": 0}}


def test_conftest_keeps_tests_offline():
    assert mps.refresh is not _REAL_REFRESH


def test_retired_ids_intersects_the_projectable_universe(monkeypatch):
    corpus = {"hit": [{"mlbam": 477132, "season": 2025}, {"mlbam": 11, "season": 2026},
                      {"mlbam": 12, "season": 2020}],
              "pit": [{"mlbam": 13, "season": 2024}]}
    rows = {"477132": {"active": False, "lastPlayedDate": "2025-09-28"},
            "12": {"active": False, "lastPlayedDate": "2020-09-01"},     # outside the window
            "13": {"active": False, "lastPlayedDate": "2024-07-01"},
            "11": {"active": True}}
    seen = {}

    def fake_refresh(ids, **k):
        seen["ids"] = set(ids)
        return rows

    monkeypatch.setattr(mps, "refresh", fake_refresh)
    assert pe._retired_ids(corpus) == {477132, 13}
    assert seen["ids"] == {477132, 11, 13}


def test_retired_ids_drops_nobody_on_failure(monkeypatch):
    def fail(ids, **k):
        raise RuntimeError("no cache")

    monkeypatch.setattr(mps, "refresh", fail)
    assert pe._retired_ids({"hit": [{"mlbam": 1, "season": 2026}], "pit": []}) == set()


def test_both_universe_loops_skip_the_retired_ids():
    assert pe.DROP_RETIRED is True
    lines = [ln.strip() for ln in SRC.splitlines()]
    src = " ".join(lines)
    guard = ('if (row.get("mlbam") and row["season"] >= FIRST_SEASON - 3 '
             'and row["mlbam"] not in _RETIRED):')
    vets = src[src.index("def _veteran_rows"):src.index("def _legacy_arbitration_paths")]
    depth = src[src.index("def _depth_pool"):src.index("def _record_farm_block_outage")]
    assert guard in vets and guard in depth
    body = src[src.index("def _build_payload_body"):src.index("vets = _veteran_rows(")]
    assert "_RETIRED.update(_retired_ids(corpus))" in body
