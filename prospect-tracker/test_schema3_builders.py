# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Unit tests for the schema-3 dark-capture builders (2026-08-19):
xwoba_14 / xwoba_30 (cumulative-difference rolling xwOBA off a git board
anchor), lineup_strength (captured orders joined to projected year-1 wOBA),
and star_out (top-N projected players against cached 40-man IL codes).

Everything here is synthetic: no git subprocess, no network, no real caches.
The git anchor is injected through `anchor_loader`; the IL read points at a
tmp cache dir; the projections file is written by hand. The one property
every test in section 4 pins is the section-5c convention: a null column
always carries its basis, and a basis is never an invented value.
"""
from __future__ import annotations

import json
import os
import time

import pytest

import leaderboard_vintages as lv


ORGS = ("NYM", "PHI", "ATL", "WSN")


@pytest.fixture(autouse=True)
def _no_network_pitch_hand(monkeypatch):
    """reduce_current's throws join must never reach the network from a test."""
    import pal_export
    monkeypatch.setattr(pal_export, "load_pitch_hand",
                        lambda season: {101: "L", 102: "R", 103: "R", 104: "L"})


# ===========================================================================
# helpers: synthetic boards
# ===========================================================================
def _board(hitters, season="2026", as_of="2026-08-19"):
    return {"season": season, "as_of": as_of, "hitters": hitters, "teams": []}


def _h(mid, team, xwoba, pa):
    return {"mlbam": mid, "team": team, "xwoba": xwoba, "pa": pa}


def _write_fake_leaderboards(data_dir, *, with_order_keys=False):
    """The three-side minimum reduce_current needs, plus optional orders whose
    slots carry the mlbam `key` the lineup builder joins on."""
    def orders(i):
        if not with_order_keys:
            return {}
        return {"orders": {
            "vl": [{"slot": s, "key": str(900 + 10 * i + s), "hem_plus": 100,
                    "pa": 400} for s in range(1, 10)],
            "vr": [{"slot": s, "key": str(900 + 10 * i + s), "hem_plus": 100,
                    "pa": 380} for s in range(1, 10)],
        }}
    (data_dir / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-08-04",
        "teams": [{"team": o, "offense_plus": 110.0 - 2 * i, **orders(i)}
                  for i, o in enumerate(ORGS)],
        "hitters": [],
    }), encoding="utf-8")
    (data_dir / "starter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-08-04",
        "teams": [{"team": o, "rotation_plus": 104.0, "starter_ip": 560.0}
                  for o in ORGS],
        "starters": [{"mlbam": 101 + i, "team": o, "sem_plus": 110 - 5 * i,
                      "ip_per_gs": 5.5, "role": "SP"}
                     for i, o in enumerate(ORGS)],
    }), encoding="utf-8")
    (data_dir / "bullpen_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-08-04",
        "teams": [{"team": o, "bullpen_plus": 101.0, "relief_ip": 380.0}
                  for o in ORGS],
        "relievers": [],
    }), encoding="utf-8")


# ===========================================================================
# 1. the xwOBA window arithmetic (pure, no git)
# ===========================================================================
def test_xwoba_window_is_a_cumulative_difference():
    """One hitter, both endpoints known: the window value is
    (xw_now*pa_now - xw_then*pa_then) / (pa_now - pa_then), exactly."""
    cur = _board([_h(1, "NYM", 0.400, 300)])
    anchor = _board([_h(1, "NYM", 0.350, 250)])
    vals, diag = lv.xwoba_window_from_boards(cur, anchor)
    # (0.400*300 - 0.350*250) / 50 = (120 - 87.5) / 50 = 0.65
    assert vals == {"NYM": 0.65}
    assert diag["n_hitters"] == 1
    assert diag["n_skipped_no_anchor_xwoba"] == 0


def test_xwoba_window_pools_teammates_by_window_pa():
    """Two bats pool on window PA, not a flat mean of their window rates."""
    cur = _board([_h(1, "NYM", 0.400, 200), _h(2, "NYM", 0.300, 400)])
    anchor = _board([_h(1, "NYM", 0.400, 100), _h(2, "NYM", 0.300, 100)])
    vals, _ = lv.xwoba_window_from_boards(cur, anchor)
    # windows: bat 1 num 80-40=40 over 100 PA; bat 2 num 120-30=90 over 300 PA
    assert vals == {"NYM": round((40 + 90) / 400, 4)}


def test_xwoba_new_arrival_contributes_his_full_cum():
    """A bat absent from the anchor board (call-up, new acquisition) has his
    whole season inside the window."""
    cur = _board([_h(1, "NYM", 0.320, 60)])
    anchor = _board([])
    vals, _ = lv.xwoba_window_from_boards(cur, anchor)
    assert vals == {"NYM": 0.32}


def test_xwoba_anchor_row_without_xwoba_is_excluded_not_zeroed():
    """A bat below the Savant PA floor at the anchor has an UNKNOWABLE anchor
    cum. He is excluded from numerator AND denominator; treating his anchor as
    zero would invent window production he may not have had."""
    cur = _board([_h(1, "NYM", 0.400, 300), _h(2, "NYM", 0.500, 90)])
    anchor = _board([_h(1, "NYM", 0.350, 250),
                     {"mlbam": 2, "team": "NYM", "xwoba": None, "pa": 40}])
    vals, diag = lv.xwoba_window_from_boards(cur, anchor)
    assert vals == {"NYM": 0.65}          # bat 1 alone
    assert diag["n_skipped_no_anchor_xwoba"] == 1


def test_xwoba_nonpositive_window_pa_is_skipped():
    """A data revision can shrink season PA. That bat's window is undefined
    and he is skipped, never differenced into a negative denominator."""
    cur = _board([_h(1, "NYM", 0.400, 200)])
    anchor = _board([_h(1, "NYM", 0.380, 250)])
    vals, _ = lv.xwoba_window_from_boards(cur, anchor)
    assert vals == {}


def test_xwoba_traded_bat_rides_his_current_club():
    """Team assignment comes off TONIGHT'S board: a bat traded inside the
    window credits his whole window to the current club. Stated in the basis."""
    cur = _board([_h(1, "PHI", 0.400, 300)])
    anchor = _board([_h(1, "NYM", 0.350, 250)])
    vals, _ = lv.xwoba_window_from_boards(cur, anchor)
    assert "PHI" in vals and "NYM" not in vals


def test_xwoba_min_window_pa_floor_drops_the_team():
    """A team whose summed window PA is under the floor is omitted (null),
    not published on a handful of PA."""
    cur = _board([_h(1, "NYM", 0.400, 300)])
    anchor = _board([_h(1, "NYM", 0.350, 260)])       # 40 window PA
    vals, diag = lv.xwoba_window_from_boards(cur, anchor, min_window_pa=100.0)
    assert vals == {}
    assert diag["n_below_pa_floor"] == 1


# ===========================================================================
# 2. build_xwoba_windows: anchor discipline (loader injected, no git)
# ===========================================================================
def test_no_anchor_is_a_stated_null():
    cur = _board([_h(1, "NYM", 0.400, 300)])
    loader = lambda target, season: (None, None, "no board commit on or before " + target)  # noqa: E731
    out = lv.build_xwoba_windows(cur, "2026-08-19", "2026", anchor_loader=loader)
    for col in lv.XWOBA_WINDOWS:
        assert out[col]["values"] == {}
        assert "ABSENT" in out[col]["basis"]
        assert "no board commit" in out[col]["basis"]


def test_anchor_past_tolerance_is_a_stated_null_naming_the_gap():
    """An anchor 8 days behind the 14d target would be a ~22d window wearing
    a 14d label: a different feature. Refused, with the gap in the basis."""
    anchor = _board([_h(1, "NYM", 0.350, 250)])
    stale_date = "2026-07-28"                    # target 2026-08-05, gap 8d
    loader = lambda target, season: (anchor, stale_date, None)  # noqa: E731
    out = lv.build_xwoba_windows(_board([_h(1, "NYM", 0.400, 300)]),
                                 "2026-08-19", "2026", anchor_loader=loader)
    assert out["xwoba_14"]["values"] == {}
    assert "ABSENT" in out["xwoba_14"]["basis"]
    assert "8d" in out["xwoba_14"]["basis"]


def test_anchor_inside_tolerance_fills_and_names_the_true_window():
    """Window PA must clear the per-column floor (100 for 14d), so the bat
    adds 250 PA inside the window: num 0.400*500 - 0.350*250 = 112.5 over
    250 PA = 0.45."""
    anchor = _board([_h(1, "NYM", 0.350, 250)])
    loader = lambda target, season: (anchor, "2026-08-03", None)  # gap 2d  # noqa: E731
    out = lv.build_xwoba_windows(_board([_h(1, "NYM", 0.400, 500)]),
                                 "2026-08-19", "2026", anchor_loader=loader)
    assert out["xwoba_14"]["values"] == {"NYM": 0.45}
    assert "16d" in out["xwoba_14"]["basis"]     # 14 + 2, stated
    assert "2026-08-03" in out["xwoba_14"]["basis"]


def test_empty_board_short_circuits_without_calling_the_loader():
    """No hitter carries an xwoba: there is nothing to difference and git is
    never touched. The null names the builder so a reader knows one exists."""
    calls = []
    loader = lambda target, season: calls.append(target)  # noqa: E731
    out = lv.build_xwoba_windows(_board([]), "2026-08-19", "2026",
                                 anchor_loader=loader)
    assert calls == []
    for col in lv.XWOBA_WINDOWS:
        assert out[col]["values"] == {}
        assert "ABSENT" in out[col]["basis"]
        assert "rolling-xwOBA builder" in out[col]["basis"]


def test_a_raising_loader_costs_a_stated_null_never_a_crash():
    def loader(target, season):
        raise RuntimeError("boom")
    out = lv.build_xwoba_windows(_board([_h(1, "NYM", 0.400, 300)]),
                                 "2026-08-19", "2026", anchor_loader=loader)
    for col in lv.XWOBA_WINDOWS:
        assert out[col]["values"] == {}
        assert "ABSENT" in out[col]["basis"]
        assert "RuntimeError" in out[col]["basis"]


# ===========================================================================
# 3. lineup_strength
# ===========================================================================
def _order_team(vl_keys, vr_keys=None):
    mk = lambda ks: [{"slot": i + 1, "key": k, "hem_plus": 100, "pa": 400}  # noqa: E731
                     for i, k in enumerate(ks)]
    return {"team": "NYM",
            "orders": {"vl": mk(vl_keys), "vr": mk(vr_keys or vl_keys)}}


def test_lineup_strength_is_the_mean_of_side_means():
    wmap = {str(k): 0.300 + 0.001 * k for k in range(1, 10)}
    t = _order_team([str(k) for k in range(1, 10)])
    v = lv.lineup_strength_from_orders(t, wmap)
    expect = round(sum(0.300 + 0.001 * k for k in range(1, 10)) / 9, 4)
    assert v == expect                       # identical sides -> the side mean


def test_lineup_side_below_the_join_floor_is_dropped_not_zero_filled():
    """vl joins 5 of 9 (below the floor of 7) and is dropped; the value is the
    vr side alone. A missing bat never enters as a zero wOBA."""
    wmap = {str(k): 0.320 for k in range(1, 10)}
    vl = [str(k) for k in range(1, 6)] + ["x1", "x2", "x3", "x4"]
    t = _order_team(vl, [str(k) for k in range(1, 10)])
    assert lv.lineup_strength_from_orders(t, wmap) == 0.32


def test_lineup_with_no_usable_side_is_none():
    wmap = {"999": 0.320}
    t = _order_team([str(k) for k in range(1, 10)])
    assert lv.lineup_strength_from_orders(t, wmap) is None
    assert lv.lineup_strength_from_orders({"team": "NYM"}, wmap) is None


def test_build_lineup_strength_without_projections_is_a_stated_null(tmp_path):
    hit = {"teams": [_order_team([str(k) for k in range(1, 10)])]}
    blk = lv.build_lineup_strength(hit, data_dir=tmp_path)
    assert blk["values"] == {}
    assert "ABSENT" in blk["basis"]
    assert "mlb_projections.json" in blk["basis"]


def test_build_lineup_strength_joins_vets_year1_woba(tmp_path):
    (tmp_path / "mlb_projections.json").write_text(json.dumps({
        "generated_at": "2026-08-10T02:00:00",
        "vets": [{"mlbam": k, "team": "NYM", "woba": [0.310 + 0.001 * k]}
                 for k in range(1, 10)],
    }), encoding="utf-8")
    hit = {"teams": [_order_team([str(k) for k in range(1, 10)])]}
    blk = lv.build_lineup_strength(hit, data_dir=tmp_path)
    expect = round(sum(0.310 + 0.001 * k for k in range(1, 10)) / 9, 4)
    assert blk["values"] == {"NYM": expect}
    assert "2026-08-10" in blk["basis"]
    assert "woba[0]" in blk["basis"]


# ===========================================================================
# 4. star_out
# ===========================================================================
def _cache_with_rosters(tmp_path, season="2026", *, stale_hours=0.0):
    """A tmp cache dir shaped like the nightly's StatsAPI roster cache: NYM
    with two IL players (one a star), PHI all active."""
    cd = tmp_path / "cache"
    cd.mkdir()
    (cd / f"statsapi_teams_{season}.json").write_text(json.dumps({
        "teams": [{"id": 121, "name": "New York Mets"},
                  {"id": 143, "name": "Philadelphia Phillies"}],
    }), encoding="utf-8")
    (cd / f"statsapi_roster_40man_121_{season}.json").write_text(json.dumps({
        "roster": [{"person": {"id": 1}, "status": {"code": "D60"}},
                   {"person": {"id": 2}, "status": {"code": "A"}},
                   {"person": {"id": 9}, "status": {"code": "D10"}},
                   {"person": {"id": 3}, "status": {"code": "RM"}}],
    }), encoding="utf-8")
    (cd / f"statsapi_roster_40man_143_{season}.json").write_text(json.dumps({
        "roster": [{"person": {"id": 11}, "status": {"code": "A"}}],
    }), encoding="utf-8")
    if stale_hours:
        old = time.time() - stale_hours * 3600
        for p in cd.glob("statsapi_roster_40man_*.json"):
            os.utime(p, (old, old))
    return cd


def _vets(org, n, *, start_id=1):
    """n vets ranked by descending warY1Champ, ids start_id.. in rank order."""
    return [{"mlbam": start_id + i, "team": org, "warY1Champ": 6.0 - i}
            for i in range(n)]


def test_il_by_org_reads_d_codes_and_only_d_codes(tmp_path):
    cd = _cache_with_rosters(tmp_path)
    il, note = lv._il_by_org("2026", cd)
    assert il["NYM"] == {1, 9}               # D60 + D10; A and RM are not IL
    assert il["PHI"] == set()                # fresh cache, empty IL is a fact
    assert "2 orgs" in note


def test_il_by_org_stale_cache_is_excluded_not_trusted(tmp_path):
    cd = _cache_with_rosters(tmp_path, stale_hours=60.0)
    il, note = lv._il_by_org("2026", cd)
    assert il == {}
    assert "2 stale" in note


def test_star_out_counts_top_n_against_the_il_set():
    vets = _vets("NYM", 8) + _vets("PHI", 8, start_id=11)
    il = {"NYM": {1, 9}, "PHI": set()}
    out = lv.star_out_from_projections(vets, il, top_n=5)
    # NYM: ids 1..5 are the top 5; id 1 is on IL, id 9 is NOT top-5.
    assert out == {"NYM": 1, "PHI": 0}


def test_star_out_zero_is_a_value_and_no_fresh_cache_is_absence():
    vets = _vets("NYM", 8) + _vets("ATL", 8, start_id=21)
    out = lv.star_out_from_projections(vets, {"NYM": set()}, top_n=5)
    assert out == {"NYM": 0}                 # populated zero: stars healthy
    assert "ATL" not in out                  # no fresh IL read -> null


def test_star_out_needs_top_n_rankable_vets():
    out = lv.star_out_from_projections(_vets("NYM", 3), {"NYM": {1}}, top_n=5)
    assert out == {}


def test_build_star_out_end_to_end(tmp_path):
    cd = _cache_with_rosters(tmp_path)
    (tmp_path / "mlb_projections.json").write_text(json.dumps({
        "vets": _vets("NYM", 8) + _vets("PHI", 8, start_id=11),
    }), encoding="utf-8")
    blk = lv.build_star_out("2026", data_dir=tmp_path, cache_dir=cd)
    assert blk["values"] == {"NYM": 1, "PHI": 0}
    assert "top-5" in blk["basis"]


def test_build_star_out_without_projections_is_a_stated_null(tmp_path):
    blk = lv.build_star_out("2026", data_dir=tmp_path,
                            cache_dir=tmp_path)
    assert blk["values"] == {}
    assert "ABSENT" in blk["basis"]


def test_build_star_out_with_only_stale_caches_is_a_stated_null(tmp_path):
    cd = _cache_with_rosters(tmp_path, stale_hours=60.0)
    (tmp_path / "mlb_projections.json").write_text(json.dumps({
        "vets": _vets("NYM", 8),
    }), encoding="utf-8")
    blk = lv.build_star_out("2026", data_dir=tmp_path, cache_dir=cd)
    assert blk["values"] == {}
    assert "ABSENT" in blk["basis"]
    assert "stale" in blk["basis"]


# ===========================================================================
# 5. the nulls-carry-basis property, and the capture integration
# ===========================================================================
def test_every_dark_column_always_carries_a_nonempty_basis(tmp_path):
    """The section-5c convention as a property: whatever the environment
    (here: no projections, no caches, no anchor), all four builder-backed
    columns come back with a values dict AND a non-empty basis, and an empty
    values dict always states ABSENT. A silent zero has nowhere to hide."""
    loader = lambda target, season: (None, None, "no anchor in this fixture")  # noqa: E731
    out = lv.build_dark_team_columns(
        _board([]), on_date="2026-08-19", season="2026",
        data_dir=tmp_path, cache_dir=tmp_path, anchor_loader=loader)
    assert set(out) == {"xwoba_14", "xwoba_30", "lineup_strength", "star_out"}
    for col, blk in out.items():
        assert isinstance(blk["values"], dict)
        assert isinstance(blk["basis"], str) and blk["basis"].strip()
        if not blk["values"]:
            assert "ABSENT" in blk["basis"], col


def test_reduce_current_stores_builder_values_and_counts_them(tmp_path, monkeypatch):
    """Integration seam: builder output lands in the stored rows, only on
    clubs the three-side intersection kept, and feature_basis.n counts the
    STORED fills, never the builder's claim."""
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data)
    fake = {
        "xwoba_14": {"values": {"NYM": 0.333, "PHI": 0.311, "COL": 0.399},
                     "basis": "fixture xwoba_14"},
        "xwoba_30": {"values": {}, "basis": "ABSENT: fixture says so"},
        "lineup_strength": {"values": {"NYM": 0.320}, "basis": "fixture lineup"},
        "star_out": {"values": {"NYM": 0, "WSN": 2}, "basis": "fixture star_out"},
    }
    monkeypatch.setattr(lv, "build_dark_team_columns",
                        lambda *a, **k: {c: dict(b) for c, b in fake.items()})
    rec = lv.reduce_current(on_date="2026-08-19", data_dir=data)
    cols = rec["team_columns"]
    i14, ils, iso = (cols.index(c) for c in
                     ("xwoba_14", "lineup_strength", "star_out"))
    assert rec["teams"]["NYM"][i14] == 0.333
    assert rec["teams"]["ATL"][i14] is None
    assert "COL" not in rec["teams"]          # not on the fake boards
    assert rec["teams"]["NYM"][ils] == 0.32
    assert rec["teams"]["NYM"][iso] == 0      # a stored zero is a VALUE
    assert rec["teams"]["WSN"][iso] == 2
    fb = rec["feature_basis"]
    assert fb["xwoba_14"] == {"basis": "fixture xwoba_14", "n": 2}
    assert fb["xwoba_30"] == {"basis": "ABSENT: fixture says so", "n": 0}
    assert fb["lineup_strength"]["n"] == 1
    assert fb["star_out"]["n"] == 2


def test_dry_run_reports_fills_and_writes_nothing(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    _write_fake_leaderboards(data)
    store = tmp_path / "vintages"
    store.mkdir()
    monkeypatch.setattr(lv, "VINTAGE_DIR", store)
    lv.reset_cache()
    r = lv.dark_capture_dry_run(on_date="2026-08-19", data_dir=data)
    assert r["ok"] is True and r["written"] is False
    assert set(r["columns"]) == set(lv.SCHEMA3_TEAM_COLUMNS) | {"throws"}
    for c in lv.SCHEMA3_TEAM_COLUMNS:
        assert r["columns"][c]["of"] == len(ORGS)
        assert r["columns"][c]["basis"]
    assert not list(store.glob("*.json"))
    lv.reset_cache()
