# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""fielding_innings.refresh_current: one live season, one key, atomically.

The artifact sat at 2026-07-24 while the season ran on, so the Defense board, the
fWAR replica's positional component and Position Fit paired September runs with
July innings. The nightly refresh rewrites only the live season.
"""
from __future__ import annotations

import json

import fielding_innings as fi

DOC = {"stats": [{"splits": [
    {"player": {"id": 7}, "position": {"abbreviation": "SS"},
     "stat": {"games": 100, "gamesStarted": 98, "innings": "850.2"}},
    {"player": {"id": 8}, "position": {"abbreviation": "C"},
     "stat": {"games": 90, "gamesStarted": 85, "innings": "760.1"}},
]}]}


def _setup(tmp_path, monkeypatch, doc):
    out = tmp_path / "fielding_innings.json"
    out.write_text(json.dumps({"seasons": {"2025": {"1": {"SS": {"g": 1, "gs": 1, "inn": 9.0}}},
                                           "2026": {"stale": {}}},
                               "last_season": 2026, "generated_at": "2026-07-24"}),
                   encoding="utf-8")
    monkeypatch.setattr(fi, "OUT", out)
    monkeypatch.setattr(fi, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fi, "fetch_season", lambda y, force=False: doc)
    return out


def test_only_the_live_season_is_rewritten(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch, DOC)
    n = fi.refresh_current(2026, log=None)
    d = json.loads(out.read_text(encoding="utf-8"))
    assert n == 2
    assert set(d["seasons"]["2026"]) == {"7", "8"}
    assert d["seasons"]["2026"]["7"]["SS"]["inn"] == round(850 + 2 / 3, 1)
    assert d["seasons"]["2025"] == {"1": {"SS": {"g": 1, "gs": 1, "inn": 9.0}}}
    assert d["generated_at"] != "2026-07-24"
    assert not (tmp_path / "fielding_innings.json.tmp").exists()


def test_an_empty_fetch_leaves_the_artifact_alone(tmp_path, monkeypatch):
    out = _setup(tmp_path, monkeypatch, {})
    before = out.read_text(encoding="utf-8")
    assert fi.refresh_current(2026, log=None) == 0
    assert out.read_text(encoding="utf-8") == before


def test_the_daily_path_refreshes_before_the_card_bake():
    from pathlib import Path
    src = (Path(__file__).parent / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("d9b1. Refresh current-season fielding innings")
    j = src.index('with _step("d9b2. Re-bake MLB player detail')
    assert i < j
