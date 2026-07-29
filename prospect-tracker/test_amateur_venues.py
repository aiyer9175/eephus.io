# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline coverage for venue_meta.py + amateur_leagues.py.

Runs purely off the saved StatsAPI fixtures in data/sources/samples/ (no
network). It pins the three properties the two ingests depend on:

  1. Venues carry lat/lon + elevation for MLB and for at least one MiLB
     level (the park-factor / elevation feature needs both tiers).
  2. sportId 22 (college etc.) 2025 returns hundreds of hitters, every one
     on a native MLBAM player id, under playerPool=all.
  3. sportId 31 (NPB) and 32 (KBO) are documented-empty: the fixtures show
     totalSplits 0 and the module deliberately excludes them, so a future
     dev does not re-add them expecting data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import amateur_leagues
import venue_meta

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "data" / "sources" / "samples"

# sportId -> the level label the venue fetch was tagged with.
_MLB_SPORT = 1
_MILB_SPORTS = (11, 12, 13, 14, 16)


def _load_sample(name: str):
    path = SAMPLES / name
    if not path.exists():
        pytest.skip(f"fixture not present: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _venues(sport_id: int) -> list[dict]:
    return _load_sample(f"venues_sport{sport_id}.json").get("venues") or []


def _splits(doc: dict) -> tuple[list[dict], int]:
    block = (doc.get("stats") or [{}])[0]
    return (block.get("splits") or []), (block.get("totalSplits") or 0)


def _has_full_geo(v: dict) -> bool:
    loc = v.get("location") or {}
    coords = loc.get("defaultCoordinates") or {}
    return (coords.get("latitude") is not None
            and coords.get("longitude") is not None
            and loc.get("elevation") is not None)


# ---------------------------------------------------------------------------
# (1) Venues: geo coverage for MLB and at least one MiLB level
# ---------------------------------------------------------------------------

def test_mlb_venues_carry_latlon_and_elevation():
    venues = _venues(_MLB_SPORT)
    assert venues, "MLB venue fixture is empty"
    geo = [v for v in venues if _has_full_geo(v)]
    assert geo, "no MLB venue carried lat/lon + elevation"
    # sanity on the concrete values of one park
    v = geo[0]
    coords = v["location"]["defaultCoordinates"]
    assert -90 <= coords["latitude"] <= 90
    assert -180 <= coords["longitude"] <= 180
    assert isinstance(v["location"]["elevation"], (int, float))


def test_at_least_one_milb_level_carries_latlon_and_elevation():
    levels_with_geo = [
        venue_meta.SPORT_LEVEL[sp]
        for sp in _MILB_SPORTS
        if any(_has_full_geo(v) for v in _venues(sp))
    ]
    assert levels_with_geo, (
        "no MiLB level had a venue with lat/lon + elevation")


def test_venue_meta_module_sports_are_the_verified_set():
    assert venue_meta.SPORTS == (1, 11, 12, 13, 14, 16)
    assert venue_meta.SPORT_LEVEL[1] == "MLB"
    assert set(venue_meta.SPORT_LEVEL) == set(venue_meta.SPORTS)


def test_landed_venue_table_covers_mlb_and_milb_if_built():
    """If build() has run, the landed table exposes an MLB and a MiLB
    venue with elevation via venue_for(). Skips when unbuilt (offline CI)."""
    if not venue_meta.DATA_PATH.exists():
        pytest.skip("data/venue_meta.json not built")
    table = json.loads(venue_meta.DATA_PATH.read_text(encoding="utf-8"))
    rows = list(table.values())
    mlb = [r for r in rows if r.get("level") == "MLB"
           and r.get("lat") is not None and r.get("elevation_ft") is not None]
    milb = [r for r in rows if r.get("level") in ("AAA", "AA", "A+", "A", "CPX")
            and r.get("lat") is not None and r.get("elevation_ft") is not None]
    assert mlb, "landed table has no MLB venue with lat + elevation"
    assert milb, "landed table has no MiLB venue with lat + elevation"
    # venue_for() round-trips a real id
    some_id = next(iter(table))
    assert venue_meta.venue_for(int(some_id)) is not None


# ---------------------------------------------------------------------------
# (2) sportId 22 (amateur) 2025: hundreds of hitters, all native mlbam ids
# ---------------------------------------------------------------------------

def test_sport22_2025_has_hundreds_of_hitters_with_native_mlbam_ids():
    splits, total = _splits(_load_sample("amateur_sport22_hitting2025.json"))
    assert total >= 200, f"expected hundreds of hitters, got totalSplits={total}"
    assert len(splits) >= 200
    with_id = sum(1 for s in splits if (s.get("player") or {}).get("id"))
    assert with_id == len(splits), "some sportId-22 lines lack a native mlbam id"
    # ids are the native MLBAM person ids (6-digit range), not synthetic
    sample_id = (splits[0].get("player") or {}).get("id")
    assert isinstance(sample_id, int) and sample_id > 100000


def test_playerpool_all_returns_more_than_the_qualifier_default():
    """playerPool=all must be passed: it lifts the returned count above the
    qualifier default (the module hardcodes playerPool=all for this reason)."""
    _, total_all = _splits(_load_sample("amateur_sport22_hitting2025.json"))
    _, total_def = _splits(_load_sample("amateur_sport22_hitting2025_defaultpool.json"))
    assert total_all > total_def, (
        f"playerPool=all ({total_all}) should exceed default ({total_def})")


def test_amateur_module_targets_the_verified_sports():
    assert amateur_leagues.SPORTS == (22, 17, 23)
    assert set(amateur_leagues.SPORT_LABEL) == set(amateur_leagues.SPORTS)


# ---------------------------------------------------------------------------
# (3) NPB (31) / KBO (32): documented-empty, must never be ingested
# ---------------------------------------------------------------------------

def test_npb_kbo_are_excluded_from_the_fetch_set():
    for sp in (31, 32):
        assert sp not in amateur_leagues.SPORTS
    assert amateur_leagues.EMPTY_SPORTS == (31, 32)


def test_npb_fixture_is_empty():
    splits, total = _splits(_load_sample("negctl_sport31_npb_hitting2025.json"))
    assert total == 0, "NPB (sportId 31) unexpectedly returned splits"
    assert splits == []


def test_kbo_fixture_is_empty():
    splits, total = _splits(_load_sample("negctl_sport32_kbo_hitting2025.json"))
    assert total == 0, "KBO (sportId 32) unexpectedly returned splits"
    assert splits == []
