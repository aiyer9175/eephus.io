# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_B3 pins: the MiLB floor lift on the list-vintage frame (lane B M1, E3-Q22).

1. efv_dataset._milb_features at its default floor reads exactly the seasons it read
   before the parameter existed (2014 up), through the same calls, so the v1 matrices
   and the live board cannot move; no served builder passes another floor.
2. The F-LV frame reads back to efv_vintage_frame.MILB_FLOOR_LV on the lifted sides: a
   row at V 2013 for a player with a 2012 AA line carries a block whose season is at
   most 2012, and no block season is at or after V anywhere.
3. milb_history.player_index never fetches a season before FETCH_FLOOR_SEASON; a
   missing file is empty, never a network call.
4. The reserved guard trips on 2020 whatever floor is asked for.
5. The withheld side reads the served default unless a floor is named; the coverage
   receipt's DS-03 reading agrees with the code's withheld set.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import efv_dataset as D
import efv_identity as ID
import efv_vintage_frame as F
import milb_history as mh

ROOT = Path(__file__).parent
DATA = ROOT / "data"
_HAVE_DATA = all((DATA / f).exists() for f in ("debuts.json", "inactive.json",
                                                "timeseries.json"))
COVERAGE = DATA / "efv_milb_floor_coverage.json"


# ---------------------------------------------------------------------------
# 1. the default is the shipped walk
# ---------------------------------------------------------------------------

def test_constants():
    assert D.MILB_FLOOR_DEFAULT == 2014
    assert mh.FETCH_FLOOR_SEASON == D.MILB_FLOOR_DEFAULT
    assert F.MILB_FLOOR_LV == 2005
    assert F.MILB_FLOOR_LV < D.MILB_FLOOR_DEFAULT
    assert F.MILB_FLOOR_LV_WITHHELD <= set(F.SIDES)
    for side in F.SIDES:
        want = D.MILB_FLOOR_DEFAULT if side in F.MILB_FLOOR_LV_WITHHELD else F.MILB_FLOOR_LV
        assert F.lv_milb_floor(side) == want


def _trace_seasons(monkeypatch, **kw):
    seen = []

    def fake_index(season, group, fetch=True):
        seen.append((int(season), bool(fetch)))
        return {}
    monkeypatch.setattr(D.mh, "player_index", fake_index)
    assert D._milb_features(1, 2019, "1998-01-01", "hit", cutoff="2019-01-01", **kw) is None
    return seen


def test_default_floor_reads_the_shipped_seasons_only(monkeypatch):
    seen = _trace_seasons(monkeypatch)
    assert [s for s, _f in seen] == [2018, 2017, 2016, 2015, 2014]
    assert all(f is True for _s, f in seen)
    seen = _trace_seasons(monkeypatch, first_season_floor=D.MILB_FLOOR_DEFAULT)
    assert [s for s, _f in seen] == [2018, 2017, 2016, 2015, 2014]


def test_lifted_floor_walks_to_2005_without_a_fetch(monkeypatch):
    seen = _trace_seasons(monkeypatch, first_season_floor=2005)
    assert [s for s, _f in seen] == list(range(2018, 2004, -1))
    for s, f in seen:
        assert f is (s >= D.MILB_FLOOR_DEFAULT), (s, f)


def test_no_served_builder_passes_a_floor():
    """The v1 matrices, the live board, efv_score, efv_ungraded and efv_proxy call
    _milb_features without first_season_floor; only the list-vintage frame names one."""
    pat = re.compile(r"first_season_floor\s*=")
    for mod in ("efv_dataset.py", "efv_score.py", "efv_ungraded.py", "efv_proxy.py"):
        src = (ROOT / mod).read_text(encoding="utf-8")
        calls = [m.start() for m in re.finditer(r"_milb_features\(", src)]
        for pos in calls:
            if src[max(0, pos - 4):pos].endswith("def "):
                continue
            window = src[pos:pos + 400]
            assert not pat.search(window), (mod, src[pos:pos + 80])
    frame = (ROOT / "efv_vintage_frame.py").read_text(encoding="utf-8")
    assert "first_season_floor=floor" in frame


def test_entry_observed_guard_slides_with_the_floor():
    def seasons(first, last):
        return [{"season": y, "level_rank": 2.0} for y in range(last, first - 1, -1)]
    final = {"season": 2018, "level_rank": 4.0}
    # the shipped rule: an entry at 2014 or 2015 is left-censored
    assert D._pace_from_entry(seasons(2015, 2018), final)["entry_observed"] == 0.0
    assert D._pace_from_entry(seasons(2016, 2018), final)["entry_observed"] == 1.0
    # the lifted rule slides the same two-season guard to 2005 and 2006
    assert D._pace_from_entry(seasons(2006, 2018), final, 2005)["entry_observed"] == 0.0
    assert D._pace_from_entry(seasons(2007, 2018), final, 2005)["entry_observed"] == 1.0
    assert D._pace_from_entry(seasons(2015, 2018), final, 2005)["entry_observed"] == 1.0


# ---------------------------------------------------------------------------
# 2. the frame at V 2013
# ---------------------------------------------------------------------------

def _pt(date, per_source, cons=45.0):
    return {"snapshot_date": date, "consensus_fv_raw": cons,
            "sources_contributing": sorted(per_source),
            "per_source": {s: {"fv_published": v, "snapshot_date": date}
                           for s, v in per_source.items()}}


def _synthetic_ladder(monkeypatch, mlbam=4242, group="hitting"):
    """One player with an AA line in 2012 and a line in 2013 (the V season, which a
    V 2013 row must not read), nothing else on the ladder."""
    lines = {
        2012: {"mlbam": mlbam, "name": "Syn Player", "season": 2012, "level": "AA",
               "league": "Eastern League", "age": 21, "pa": 450, "ab": 400, "ops": 0.8,
               "obp": 0.36, "slg": 0.44, "avg": 0.28, "so": 90, "bb": 45, "hr": 12,
               "sb": 5},
        2013: {"mlbam": mlbam, "name": "Syn Player", "season": 2013, "level": "AAA",
               "league": "International League", "age": 22, "pa": 500, "ab": 450,
               "ops": 0.9, "obp": 0.4, "slg": 0.5, "avg": 0.3, "so": 80, "bb": 50,
               "hr": 20, "sb": 8},
    }

    def fake_index(season, g, fetch=True):
        assert not (fetch and int(season) < mh.FETCH_FLOOR_SEASON), season
        row = lines.get(int(season))
        return {mlbam: [row]} if (row and g == group) else {}
    monkeypatch.setattr(D.mh, "player_index", fake_index)
    monkeypatch.setattr(D, "_resolved_norms",
                        lambda season, level, group: {"k_pct": 0.2, "bb_pct": 0.09,
                                                      "iso": 0.14, "obp": 0.33,
                                                      "ops": 0.72, "era": 4.3})
    monkeypatch.setattr(F, "_mlb_ids", lambda season: frozenset())
    idx = ID.NameIndex()
    idx.add("Syn Player", mlbam, 2012)
    return idx


def _rec(position="SS"):
    return {"player_key": "syn_player", "player_name": "Syn Player", "mlbam_id": None,
            "position": position, "birth_date": "1991-03-01", "debut_date": None,
            "points": [_pt("2013-02-01", {"fangraphs": 50.0})], "statline": {}}


def test_synthetic_v2013_row_reads_the_2012_aa_line_and_not_the_v_season(monkeypatch):
    idx = _synthetic_ladder(monkeypatch)
    row = F.frame_row(_rec(), "hit", 2013, excl=frozenset(), index=idx, milb_floor=2005)
    assert row is not None and row["milb"], row
    assert row["milb_floor"] == 2005
    assert row["milb"]["milb_season"] == 2012 and row["milb"]["milb_level"] == "AA"
    assert row["milb_last_season"] <= 2012
    assert row["milb"]["n_milb_seasons"] == 1.0
    # the same record at the served default floor carries no block at V 2013
    base = F.frame_row(_rec(), "hit", 2013, excl=frozenset(), index=idx,
                       milb_floor=D.MILB_FLOOR_DEFAULT)
    assert base is not None and base["milb"] is None
    assert base["milb_floor"] == D.MILB_FLOOR_DEFAULT


def test_synthetic_default_floor_follows_the_side(monkeypatch):
    for side, pos in (("hit", "SS"), ("pit", "RHP")):
        idx = _synthetic_ladder(monkeypatch, group="pitching" if side == "pit" else "hitting")
        row = F.frame_row(_rec(pos), side, 2013, excl=frozenset(), index=idx)
        assert row is not None
        assert row["milb_floor"] == F.lv_milb_floor(side)
        if side in F.MILB_FLOOR_LV_WITHHELD:
            assert row["milb"] is None
        else:
            assert row["milb"] and row["milb"]["milb_season"] == 2012


@pytest.mark.skipif(not _HAVE_DATA, reason="served data files absent")
@pytest.mark.parametrize("V", [2011, 2013])
def test_real_frame_blocks_end_before_v_on_every_side(V):
    universe = F.load_universe()
    for side in F.SIDES:
        rows = F.build_frame(side, V, universe=universe, sidecars=False,
                             milb_floor=F.MILB_FLOOR_LV)
        assert rows
        blocks = [r["milb"] for r in rows if r.get("milb")]
        assert blocks, (side, V)
        assert max(int(b["milb_season"]) for b in blocks) <= V - 1
        assert min(int(b["milb_season"]) for b in blocks) >= F.MILB_FLOOR_LV
        assert all(r["milb_floor"] == F.MILB_FLOOR_LV for r in rows)
        if V == 2013 and side == "hit":
            aa = [r for r in rows if r["milb"] and r["milb"]["milb_season"] == 2012
                  and r["milb"]["milb_level"] == "AA"]
            assert aa, "no hitter at V 2013 with a 2012 AA line"
        built = F.build_frame(side, V, universe=universe, sidecars=False)
        assert all(r["milb_floor"] == F.lv_milb_floor(side) for r in built)
        if side in F.MILB_FLOOR_LV_WITHHELD:
            assert not any(r.get("milb") for r in built)


# ---------------------------------------------------------------------------
# 3. no fetch below the floor
# ---------------------------------------------------------------------------

def test_player_index_never_fetches_before_the_floor(monkeypatch, tmp_path):
    """On an empty cache a season below the floor makes no request whatever the caller
    passes; the floor season itself still fetches (season_splits swallows a failed
    request and logs it, so the probe counts calls rather than expecting a raise)."""
    monkeypatch.setattr(mh, "CACHE_DIR", tmp_path)
    calls = []

    def no_network(url):
        calls.append(url)
        raise OSError(f"network call for {url}")
    monkeypatch.setattr(mh, "_fetch", no_network)
    mh.player_index.cache_clear()
    try:
        assert mh.player_index(2010, "hitting") == {}
        assert mh.player_index(2005, "pitching", fetch=True) == {}
        assert mh.season_splits(12, 2010, "hitting", fetch=False) == []
        assert calls == []
        assert mh.player_index(mh.FETCH_FLOOR_SEASON, "hitting") == {}
        assert calls and all(f"season={mh.FETCH_FLOOR_SEASON}" in u for u in calls)
    finally:
        mh.player_index.cache_clear()


# ---------------------------------------------------------------------------
# 4. the reserved guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("V", sorted(F.RESERVED_LV))
def test_reserved_guard_trips_whatever_the_floor(V):
    for floor in (None, F.MILB_FLOOR_LV, D.MILB_FLOOR_DEFAULT):
        with pytest.raises(F.ReservedFrameError):
            F.build_frame("hit", V, universe={}, milb_floor=floor)


# ---------------------------------------------------------------------------
# 5. the receipt
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def receipt():
    if not COVERAGE.exists():
        pytest.skip("data/efv_milb_floor_coverage.json not built")
    return json.loads(COVERAGE.read_text(encoding="utf-8"))


def test_receipt_floors_match_the_code(receipt):
    fl = receipt["floors"]
    assert fl["default"] == D.MILB_FLOOR_DEFAULT and fl["lifted_lv"] == F.MILB_FLOOR_LV
    assert fl["withheld_sides"] == sorted(F.MILB_FLOOR_LV_WITHHELD)
    assert fl["floor_by_side"] == {s: F.lv_milb_floor(s) for s in F.SIDES}
    assert receipt["role"] == "development"
    g = receipt["guards"]
    assert not set(g["vintages_read"]) & set(F.RESERVED_LV)
    for side in F.SIDES:
        assert receipt["totals"][side]["every_block_season_before_v"] is True
        for V, b in receipt["by_vintage"][side].items():
            assert int(V) in F.DEV_VINTAGES
            assert b["latest_block_season"] is None or b["latest_block_season"] <= int(V) - 1
            assert b["with_milb_block"]["lifted_floor"] >= b["with_milb_block"]["default_floor"]


def test_receipt_ds03_reading_agrees_with_the_withheld_set(receipt):
    rr = receipt["ds03_rerun"]
    assert rr, "the receipt was written without the DS-03 re-run"
    assert rr["reading"]["code_agrees"] is True
    assert rr["reading"]["withheld_sides"] == sorted(F.MILB_FLOOR_LV_WITHHELD)
    for side in F.SIDES:
        for name in rr["withhold_indicators"]:
            for lab in ("default_floor", "lifted_floor"):
                blk = rr["runs"][lab]["balance"][side][name]
                assert blk["verdict"] in ("BALANCED", "IMBALANCED", "CONSTANT")
                if blk["verdict"] != "CONSTANT":
                    lo, hi = blk["ci95"]
                    assert (lo <= 0 <= hi) is (blk["verdict"] == "BALANCED")
        if side not in F.MILB_FLOOR_LV_WITHHELD:
            for name in rr["withhold_indicators"]:
                d = rr["runs"]["default_floor"]["balance"][side][name]["verdict"]
                lft = rr["runs"]["lifted_floor"]["balance"][side][name]["verdict"]
                assert not (d == "BALANCED" and lft != "BALANCED"), (side, name)
