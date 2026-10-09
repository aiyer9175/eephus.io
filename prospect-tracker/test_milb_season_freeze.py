# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SG_1: the frozen 2026 MiLB season and its pins (tools/milb_season_freeze.py).

Pinned here: the frozen 2026 copy re-hashes to its pins and still equals the 2026-09-30
refetch in rows and PA or BF; the MLB event-id files hold ids and nothing else; the
transfer seasons' canonical content hashes recompute from the cache with fetch=False (a
drift fails, a box without the cache skips); the pure 2026 norms recompute from the frozen
copy with no blend; league_norms still reads the same helper; the files are -text in
.gitattributes and are withheld from the webroot. Nothing here reads an outcome, a score or
a label, and nothing writes under data/.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import milb_history as mh
from tools import milb_season_freeze as Z

ROOT = Path(__file__).parent
PINS = ROOT / "data" / "efv_surrogate_pins_2026.json"


def _pins() -> dict:
    return json.loads(PINS.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _never_fetch(monkeypatch):
    def boom(url):
        raise AssertionError(f"a pin test tried to fetch {url}")
    monkeypatch.setattr(mh, "_fetch", boom)


def test_the_frozen_2026_copy_rehashes_to_its_pins():
    frozen = _pins()["frozen_2026"]
    assert len(frozen) == len(Z.EXPECTED_2026) == 10
    for (sport, group), (n, expo) in Z.EXPECTED_2026.items():
        p = Z.frozen_path(group, sport)
        pin = frozen[p.name]
        raw = p.read_bytes()
        rows = json.loads(raw.decode("utf-8"))
        assert hashlib.sha256(raw).hexdigest() == pin["sha256"], f"{p.name} drifted"
        assert (len(rows), Z.exposure(rows, group)) == (pin["rows"], pin["exposure"])
        assert (pin["rows"], pin["exposure"]) == (n, float(expo)), p.name


def test_the_mlb_event_files_hold_sorted_ids_and_nothing_else():
    events = _pins()["mlb_event_ids_2026"]
    for group in Z.GROUPS:
        p = Z.event_ids_path(group)
        raw = p.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == events[p.name]["sha256"]
        ids = json.loads(raw.decode("utf-8"))
        assert isinstance(ids, list) and all(type(i) is int for i in ids)
        assert ids == sorted(set(ids)) and len(ids) == events[p.name]["ids"]
    # no sport-1 season file is frozen: the 2026 MLB lines stay out of the tree
    assert not list(Z.FROZEN_DIR.glob("*_1.json"))
    assert sorted(p.name for p in Z.FROZEN_DIR.iterdir()) == sorted(
        list(_pins()["frozen_2026"]) + list(events))


def test_the_transfer_season_hashes_recompute_from_the_cache():
    if not mh.CACHE_DIR.is_dir():
        pytest.skip("no .cache/milb_stats on this box")
    pinned = _pins()["transfer_seasons"]
    assert sorted(int(s) for s in pinned) == list(Z.TRANSFER_SEASONS)
    assert "2020" not in pinned and not [s for s in pinned if int(s) >= 2026]
    drift = []
    for season, groups in pinned.items():
        for group, sports in groups.items():
            for sport, pin in sports.items():
                rows = Z.read_cache(int(sport), int(season), group)
                if sport == "1":
                    got = {"rows": len(rows), "id_sha256": Z.id_column_hash(rows)}
                else:
                    got = {"rows": len(rows), "sha256": Z.canonical_hash(rows, int(sport))}
                if got != pin:
                    drift.append(f"{group}_{sport}_{season}")
    assert not drift, f"transfer-season cache files drifted from their pins: {drift}"


def test_the_canonical_hash_ignores_row_order_and_unread_fields():
    a = [{"mlbam": 2, "league": "INT", "level": "AAA", "pa": 100, "name": "B"},
         {"mlbam": 1, "league": "PCL", "level": "AAA", "pa": 50, "name": "A"}]
    b = [dict(a[1], name="renamed"), dict(a[0], team="x")]
    assert Z.canonical_hash(a, 11) == Z.canonical_hash(b, 11)
    assert Z.canonical_hash(a, 11) != Z.canonical_hash(a, 12)
    c = [dict(a[0], obp=".300"), a[1]]
    assert Z.canonical_hash(a, 11) != Z.canonical_hash(c, 11)
    fields = [n for n, _ in Z.HASH_FIELDS]
    for f in ("pa", "bf", "ab", "so", "bb", "obp", "slg", "avg", "ops", "era", "league",
              "level", "age", "ip", "g", "gs", "hbp", "sf", "h", "2b", "3b", "hr"):
        assert f in fields


def test_the_pure_norms_recompute_from_the_frozen_copy():
    doc = json.loads(Z.NORMS_PATH.read_text(encoding="utf-8"))
    assert hashlib.sha256(Z.NORMS_PATH.read_bytes()).hexdigest() == _pins()["pure_norms_sha256"]
    assert doc["pure"] == json.loads(json.dumps(Z.pure_norms_from_frozen()))
    for group in Z.GROUPS:
        for lv in Z.LEVELS:
            norm = doc["pure"][group][lv]
            assert norm and norm["n"] >= 30 and "norm_prior_blend_w" not in norm
            served = doc["served_blend_on_pin_date"]["norms"][group][lv]
            assert served["n"] == norm["n"]
            assert 0.0 < served["norm_prior_blend_w"] < 1.0


def test_league_norms_reads_the_same_unblended_helper():
    if not (mh.CACHE_DIR / "hitting_12_2019.json").exists():
        pytest.skip("no 2019 cache on this box")
    for group in Z.GROUPS:
        rows = [r for r in Z.read_cache(12, 2019, group) if r.get("level") == "AA"]
        mh.league_norms.cache_clear()
        assert mh.league_norms(2019, "AA", group, fetch=False) == \
            mh.level_norms_from_rows(rows, group)


def test_the_season_dates_are_pinned():
    d = _pins()["season_dates_2026"]
    ends = {k: v["end"] for k, v in d["by_sport"].items()}
    assert ends == {"1": "2026-09-27", "11": "2026-09-20", "12": "2026-09-13",
                    "13": "2026-09-06", "14": "2026-09-06", "16": "2026-08-18"}
    assert {k: v["end"] for k, v in d["by_league_sport16"].items()} == {
        "ACL": "2026-07-23", "FCL": "2026-07-23", "DSL": "2026-08-18"}


def test_the_frozen_files_are_binary_to_git_and_withheld_from_the_webroot():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    for line in ("data/milb_season_frozen/** -text", "data/efv_surrogate_*.json -text",
                 "data/milb_norms_2026_pure.json -text"):
        assert line in attrs
    excluded = (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8").splitlines()
    assert "efv_surrogate_pins_2026.json" in excluded
    assert "milb_norms_2026_pure.json" in excluded
