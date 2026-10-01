# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Bench-aware, platoon-aware lineup cards (owner ask 2026-09-11).

The card gains the bench's per-hand HEM+, positions, a platoon-option marker and
an Out block of regulars off the active roster. All of it rides SIBLING keys of
`teams[].orders`, and that fence is the first thing pinned here: `orders` feeds
leaderboard_vintages' off_vs_lhp / off_vs_rhp and betting_export prices
order[:5], so the new inputs must leave `orders` and Offense+ byte-identical.

Each test names the mutation it exists to catch.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import hem_plus as H
from hem_plus import Hitter

ROOT = Path(__file__).parent
BOARD = ROOT / "data" / "hitter_leaderboards.json"


def _hit(key, *, pa=500.0, h=130, doub=25, trip=2, hr=15, bb=45, so=110,
         bats="R", mlbam=None, primary_pos=None, team="AAA"):
    ab = pa - bb - 10.0
    return Hitter(key=key, name=key, team=team, mlbam=mlbam, pa=pa, ab=ab, h=h,
                  doub=doub, trip=trip, hr=hr, bb=bb, ibb=2.0, hbp=5.0, sf=5.0,
                  so=so, bats=bats, primary_pos=primary_pos)


def _counts(*, pa=200, h=50, doub=10, trip=1, hr=7, bb=18, so=40):
    return {"plateAppearances": pa, "atBats": pa - bb - 4, "hits": h,
            "doubles": doub, "triples": trip, "homeRuns": hr, "baseOnBalls": bb,
            "intentionalWalks": 1, "hitByPitch": 2, "sacFlies": 2,
            "strikeOuts": so}


def _club():
    """Nine regulars (alternating L/R) plus a bench of four: two position bats,
    a two-way player and a pitcher with one PA."""
    nine = [_hit(f"s{i}", pa=600.0 - i * 10, mlbam=100 + i,
                 bats=("L", "R")[i % 2]) for i in range(9)]
    bench = [_hit("b0", pa=250.0, mlbam=200, bats="R"),
             _hit("b1", pa=180.0, mlbam=201, bats="L"),
             _hit("twp", pa=120.0, mlbam=202, bats="L", primary_pos="TWP"),
             # one PA, one single: scored, active, and last by PA
             Hitter(key="pit", name="pit", team="AAA", mlbam=203, pa=1.0, ab=1.0,
                    h=1.0, bats="R", primary_pos="P")]
    return nine + bench


def _scored(hitters, platoon_counts=None, positions=None, active=None):
    return H.score_pool(hitters, active, platoon_counts, positions)


def _feed(hitters):
    """Both hands for every bat, the lefty line weaker for every hitter."""
    return {"L": {h.mlbam: _counts(h=40, doub=5, hr=3) for h in hitters},
            "R": {h.mlbam: _counts(h=70, doub=18, hr=14) for h in hitters}}


def _positions(hitters):
    return {h.mlbam: {"LF": 400.0, "1B": 40.0} for h in hitters}


# --- T1: the fence around `orders` -----------------------------------------

def test_orders_and_offense_plus_are_byte_identical_with_and_without_the_new_inputs():
    """Mutation: a new key added to a slot, or a bench bat swapped into the nine."""
    a = _scored(_club(), _feed(_club()))["teams"][0]
    b = _scored(_club(), _feed(_club()), _positions(_club()))["teams"][0]
    assert json.dumps(a["orders"], sort_keys=True) == json.dumps(b["orders"], sort_keys=True)
    assert a["offense_plus"] == b["offense_plus"]
    assert a["offense_plus_raw"] == b["offense_plus_raw"]
    assert json.dumps(a["lineup"]) == json.dumps(b["lineup"])
    slot_keys = {k for side in b["orders"].values() for s in side for k in s}
    for new in ("pos", "mlbam", "slot_meta", "platoon_options"):
        assert new not in slot_keys, f"{new} leaked into an order slot"


def test_the_off_split_capture_does_not_move():
    import leaderboard_vintages as lv
    a = _scored(_club(), _feed(_club()))["teams"][0]
    b = _scored(_club(), _feed(_club()), _positions(_club()))["teams"][0]
    assert lv.off_splits_from_hitter_team(a) == lv.off_splits_from_hitter_team(b)


# --- bench membership and values --------------------------------------------

def test_pitchers_never_reach_the_bench_and_a_two_way_player_stays():
    """Mutation: the pitcher rule inverted, or dropped."""
    t = _scored(_club(), _feed(_club()))["teams"][0]
    keys = [r["key"] for r in t["bench"]]
    assert "pit" in {r["key"] for r in t["lineup"]}, "the fixture pitcher must be scored and active"
    assert "pit" not in keys
    assert "twp" in keys
    assert H.is_pitcher(_hit("p", primary_pos="P"))
    assert not H.is_pitcher(_hit("t", primary_pos="TWP"))
    assert not H.is_pitcher(_hit("n", primary_pos=None))


def test_bench_per_hand_value_equals_split_hem_pair_on_the_same_pool():
    """Mutation: the bench scored on a different anchor or league ratio than the
    slots."""
    hs = _club()
    counts = _feed(hs)
    counts["L"][201] = _counts(pa=90, h=30, doub=8, hr=6)      # a distinct line
    out = _scored(hs, counts, _positions(hs))
    pool_in = [h for h in hs if H._woba_denom(h) > 0]
    pool = H.build_pool(pool_in)
    mu = H.league_platoon_ratios(counts, {h.mlbam: h.bats for h in hs})
    by_id = {h.mlbam: h for h in hs}
    row = next(r for r in out["teams"][0]["bench"] if r["key"] == "b1")
    want = H.split_hem_pair(by_id[201], counts["L"][201], counts["R"][201], pool, mu)
    assert row["hem_plus_split"] == want
    assert row["split_pa"] == {"L": 90, "R": 200}
    # and the slots read the same map: a nine bat's slot value matches too
    slot = out["teams"][0]["orders"]["vl"][0]
    mid = int(slot["key"][1:]) + 100
    assert slot["hem_plus_split"] == H.split_hem_pair(
        by_id[mid], counts["L"][mid], counts["R"][mid], pool, mu)["L"]


def test_a_missing_hand_is_null_never_a_season_number():
    """Mutation: a silent season fallback written into the per-hand field."""
    hs = _club()
    counts = _feed(hs)
    del counts["L"][200]
    t = _scored(hs, counts, _positions(hs))["teams"][0]
    row = next(r for r in t["bench"] if r["key"] == "b0")
    assert row["hem_plus_split"]["L"] is None and row["split_pa"]["L"] is None
    assert row["hem_plus_split"]["R"] is not None


# --- positions ----------------------------------------------------------------

def test_positions_follow_the_innings_floor_and_the_dh_label():
    pos = {1: {"SS": 500.0, "2B": H.PLATOON_OPTION_MIN_POS_INN,
               "3B": H.PLATOON_OPTION_MIN_POS_INN - 0.1}}
    assert H.player_positions(_hit("a", mlbam=1), pos) == ["SS", "2B"]
    assert H.player_positions(_hit("d", mlbam=1, primary_pos="DH"), pos) == ["DH", "SS", "2B"]
    assert H.player_positions(_hit("n", mlbam=9), pos) == ["DH"]          # no fielding
    assert H.player_positions(_hit("p", mlbam=1, primary_pos="P"), pos) == ["P"]
    assert H.player_positions(_hit("x", mlbam=1), None) is None           # lens down


# --- the marker rule, on served-shape rows -----------------------------------

def _pair(**kw):
    """One starter, one bench bat, set up to fire vs LHP at the thresholds."""
    f = H.PLATOON_OPTION_MIN_SPLIT_PA
    s = {"key": "S", "bats": kw.get("s_bats", "L"), "hem_plus_split": kw.get("sv", 80),
         "split_pa": kw.get("spa", f)}
    b = {"key": "B", "bats": kw.get("b_bats", "R"), "pos": kw.get("b_pos", ["LF"]),
         "hem_plus_split": {"L": kw.get("bv", 80 + H.PLATOON_OPTION_MARGIN), "R": 100},
         "split_pa": {"L": kw.get("bpa", f), "R": 200}}
    meta = {"S": {"pos": kw.get("s_pos", ["LF"])}}
    return [s], [b], meta


def test_the_marker_fires_exactly_at_every_threshold():
    order, bench, meta = _pair()
    opts, withheld = H.platoon_options(order, bench, meta, "L")
    assert len(opts) == 1 and withheld == 0
    o = opts[0]
    assert (o["starter_key"], o["bench_key"], o["pos"]) == ("S", "B", "LF")
    assert o["delta"] == H.PLATOON_OPTION_MARGIN


@pytest.mark.parametrize("change, why", [
    ({"s_bats": "R"}, "rule 1: the starter already holds the edge vs LHP"),
    ({"s_bats": "S"}, "rule 1: a switch-hitting starter never lacks the edge"),
    ({"b_bats": "L"}, "rule 2: the bench bat lacks the edge"),
    ({"b_pos": ["C"]}, "rule 3: the bench bat has not played the position"),
    ({"b_pos": ["P"]}, "rule 3: a pitcher is never an option"),
    ({"sv": None}, "rule 4: no real split for the starter"),
    ({"bv": None}, "rule 4: no real split for the bench bat"),
    ({"bv": 80 + H.PLATOON_OPTION_MARGIN - 1}, "rule 6: one point short of the margin"),
])
def test_each_rule_binds(change, why):
    order, bench, meta = _pair(**change)
    opts, _ = H.platoon_options(order, bench, meta, "L")
    assert opts == [], why


@pytest.mark.parametrize("change", [{"spa": H.PLATOON_OPTION_MIN_SPLIT_PA - 1},
                                    {"bpa": H.PLATOON_OPTION_MIN_SPLIT_PA - 1},
                                    {"bpa": 4, "bv": 107, "sv": 85}])
def test_the_floor_binds_on_either_side_and_is_counted(change):
    """Mutation: the floor checked on one side only, or deleted. The last case is
    the Kenny Piper shape (107 on 4 PA against 85) the floor exists for."""
    order, bench, meta = _pair(**change)
    opts, withheld = H.platoon_options(order, bench, meta, "L")
    assert opts == [] and withheld == 1


def test_dh_is_open_to_every_non_pitcher():
    order, bench, meta = _pair(s_pos=["DH"], b_pos=["C"])
    assert len(H.platoon_options(order, bench, meta, "L")[0]) == 1


def test_the_rule_mirrors_for_the_other_hand():
    order, bench, meta = _pair(s_bats="R", b_bats="L")
    for b in bench:
        b["hem_plus_split"]["R"], b["split_pa"]["R"] = 95, 150
    order[0]["hem_plus_split"], order[0]["split_pa"] = 80, 150
    assert len(H.platoon_options(order, bench, meta, "R")[0]) == 1
    assert H.platoon_options(order, bench, meta, "L")[0] == []


def test_team_offense_serves_markers_only_with_positions():
    """T14. Mutation: an outage that fakes markers, or blanks the orders."""
    hs = _club()
    counts = _feed(hs)
    counts["L"][200] = _counts(pa=150, h=60, doub=16, hr=12)   # b0 (R) mashes lefties
    with_pos = _scored(hs, counts, _positions(hs))["teams"][0]
    without = _scored(_club(), counts, None)["teams"][0]
    assert with_pos["platoon_options"]["vl"], "the fixture should fire vs LHP"
    for o in with_pos["platoon_options"]["vl"]:
        assert o["bench_key"] == "b0" and o["starter_bats"] == "L"
    assert without["platoon_options"]["vl"] == [] and without["platoon_options"]["vr"] == []
    assert all(r["pos"] is None for r in without["bench"])
    assert json.dumps(with_pos["orders"]) == json.dumps(without["orders"])


# --- T9: regulars off the active roster -------------------------------------

def test_a_regular_off_the_active_roster_is_out_and_nowhere_else():
    hs = _club()
    active = frozenset(h.mlbam for h in hs if h.key != "s0")
    t = _scored(hs, _feed(hs), _positions(hs), active)["teams"][0]
    assert [r["key"] for r in t["regulars_out"]] == ["s0"]
    assert "s0" not in {s["key"] for side in t["orders"].values() for s in side}
    assert "s0" not in {r["key"] for r in t["bench"]}
    for side in ("vl", "vr"):
        assert all("s0" not in (o["starter_key"], o["bench_key"])
                   for o in t["platoon_options"][side])
    # no filter (a failed walk) means nobody is out
    assert _scored(_club(), _feed(_club()))["teams"][0]["regulars_out"] == []


def _roster_file(d: Path, tid: int, rows: list, age_hours: float = 1.0):
    p = d / f"statsapi_roster_40man_{tid}_2026.json"
    p.write_text(json.dumps({"roster": rows}), encoding="utf-8")
    t = time.time() - age_hours * 3600.0
    os.utime(p, (t, t))


def test_status_labels_come_from_the_cached_40_man_and_are_never_guessed(tmp_path):
    import hitter_export as he
    _roster_file(tmp_path, 1, [
        {"person": {"id": 10}, "status": {"code": "D10", "description": "Injured 10-Day"}},
        {"person": {"id": 11}, "status": {"code": "RM", "description": "Reassigned to Minors"}},
        {"person": {"id": 12}, "status": {"code": "A", "description": "Active"}}])
    _roster_file(tmp_path, 2, [], age_hours=he.ROSTER_STATUS_MAX_AGE_HOURS + 1)
    teams = [{"team": "AAA", "regulars_out": [{"mlbam": 10}, {"mlbam": 11}, {"mlbam": 12},
                                              {"mlbam": 13}]},
             {"team": "BBB", "regulars_out": [{"mlbam": 20}]},
             {"team": "CCC", "regulars_out": [{"mlbam": 30}]}]
    meta = he.stamp_regulars_out(teams, 2026, team_ids={"AAA": 1, "BBB": 2},
                                 cache_dir=tmp_path)
    got = [(r["status_code"], r["status_label"]) for t in teams for r in t["regulars_out"]]
    assert got == [("D10", "IL-10"), ("RM", "Minors"), ("A", "Not active"),
                   (None, "Off 40-man"),
                   (None, "Not active"),       # stale cache: no reason
                   (None, "Not active")]       # no team id: no reason
    assert meta["n_labelled"] == 3 and meta["n_unlabelled"] == 3
    assert meta["available"] is True


# --- the exporter's lenses -----------------------------------------------------

def test_positions_lens_down_is_none_not_empty(monkeypatch):
    import hitter_export as he
    import defense_export as de
    monkeypatch.setattr(de, "load_season_innings", lambda s: {"players": {}})
    pos, meta = he.load_positions(2026)
    assert pos is None and meta["available"] is False and meta["reason"]

    def boom(s):
        raise RuntimeError("feed down")
    monkeypatch.setattr(de, "load_season_innings", boom)
    pos, meta = he.load_positions(2026)
    assert pos is None and "RuntimeError" in meta["reason"]

    monkeypatch.setattr(de, "load_season_innings",
                        lambda s: {"players": {7: {"inn": {"C": 90.0}}}, "fetched_at": "x"})
    pos, meta = he.load_positions(2026)
    assert pos == {7: {"C": 90.0}} and meta["available"] is True


def test_the_primary_position_label_rides_into_the_hitter():
    import hitter_export as he
    hs = he.build_hitters([{"mlbam": 5, "name": "Arm", "team": "AAA", "PA": 1,
                            "primary_pos": "P"}])
    assert hs[0].primary_pos == "P" and H.is_pitcher(hs[0])


def test_the_meta_block_echoes_the_constants_and_says_why_nothing_fired():
    import hitter_export as he
    t = _scored(_club(), _feed(_club()), None)["teams"]
    lc = he._lineup_cards_meta(t, {"available": False, "reason": "fielding feed down"},
                               {"available": False}, True)
    assert lc["constants"] == {"min_split_pa": H.PLATOON_OPTION_MIN_SPLIT_PA,
                               "margin": H.PLATOON_OPTION_MARGIN,
                               "min_pos_innings": H.PLATOON_OPTION_MIN_POS_INN}
    assert "fielding feed down" in lc["reason"]
    assert lc["n_platoon_options"] == {"vl": 0, "vr": 0}


# --- T8: display policy never becomes a feature -------------------------------

def test_no_betting_or_vintage_module_reads_the_display_keys():
    """Mutation: a later betting column reading the markers as a feature. Keys
    are matched as quoted strings, the only way a module reads a JSON key
    (betting_export has an unrelated local helper named _slot_meta)."""
    import re
    for mod in ("leaderboard_vintages.py", "betting_model.py", "betting_export.py"):
        src = (ROOT / mod).read_text(encoding="utf-8")
        for key in ("platoon_options", "regulars_out", "slot_meta", "lineup_cards"):
            assert not re.search(r"""["']%s["']""" % key, src), f"{mod} reads display key {key}"


# --- T3 / T4: the served board, when it carries the blocks ---------------------

def _served_teams():
    if not BOARD.exists():
        pytest.skip("hitter_leaderboards.json not generated")
    d = json.loads(BOARD.read_text(encoding="utf-8"))
    if "lineup_cards" not in d:
        pytest.skip("served board predates the lineup-card blocks")
    return d["teams"]


def test_every_served_marker_is_recomputable_from_served_numbers():
    """T3 + T4: the served set equals the rule applied to the served rows, so a
    marker is never justified by a number the page does not show."""
    for t in _served_teams():
        po = t.get("platoon_options") or {}
        for side, hand in (("vl", "L"), ("vr", "R")):
            want, _ = H.platoon_options((t.get("orders") or {}).get(side),
                                        t.get("bench") or [], t.get("slot_meta") or {}, hand)
            assert (po.get(side) or []) == want, (t["team"], side)


def test_served_bench_holds_no_pitcher_and_no_regular_out():
    for t in _served_teams():
        bench = {r["key"] for r in t.get("bench") or []}
        assert not any("P" in (r.get("pos") or []) for r in t.get("bench") or [])
        assert not bench & {r["key"] for r in t.get("regulars_out") or []}
