# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Per-hand HEM+ and the off_vs_lhp / off_vs_rhp capture (audit finding F08-02).

THE DEFECT THESE PIN. `_platoon_adj` re-lenses the ORDER vs L and vs R and never
the published number, so both hand-labelled orders carried each hitter's SEASON
hem_plus. A PA-weighted mean over a permutation of the same nine bats is
permutation-invariant, so `off_vs_lhp` and `off_vs_rhp` came out bit-identical on
all 30 clubs across all 480 captured rows, with the batSide lens reported
available and the two orders genuinely different permutations. The pre-registered
handedness gate (docs/diamond-betting.md 5e) would have measured its own twin.

The regression test that matters is test_split_breaks_the_permutation_identity:
without a per-hand value the two means are equal BY CONSTRUCTION, and that is the
state this repair exists to leave behind.

The per-hand estimator is platoon_ratio_v1 (census M06-05, owner answer
2026-09-25): the season level times the hitter's platoon ratio regressed toward
the league ratio for his bat side. Its own regression test is
test_the_two_hands_average_back_to_the_season_number_at_any_sample.
"""
from __future__ import annotations

import json
from pathlib import Path

import hem_plus as H
import leaderboard_vintages as lv
from hem_plus import Hitter


def _hit(key, *, pa=600.0, h=150, doub=30, trip=2, hr=20, bb=50, so=120,
         ibb=2.0, hbp=5.0, sf=5.0, bats="R", team="AAA", mlbam=None):
    ab = pa - bb - hbp - sf
    return Hitter(key=key, name=key, team=team, mlbam=mlbam, pa=pa, ab=ab, h=h,
                  doub=doub, trip=trip, hr=hr, bb=bb, ibb=ibb, hbp=hbp, sf=sf,
                  so=so, bats=bats)


def _counts(*, pa=200, h=50, doub=10, trip=1, hr=7, bb=18, ibb=1, hbp=2, sf=2, so=40):
    ab = pa - bb - hbp - sf
    return {"plateAppearances": pa, "atBats": ab, "hits": h, "doubles": doub,
            "triples": trip, "homeRuns": hr, "baseOnBalls": bb,
            "intentionalWalks": ibb, "hitByPitch": hbp, "sacFlies": sf,
            "strikeOuts": so}


def _pool(hitters):
    for x in hitters:
        H.derive_rates(x)
    return H.build_pool(hitters)


def _nine(prefix="p", bats_cycle=("L", "R")):
    out = []
    for i in range(9):
        out.append(_hit(f"{prefix}{i}", pa=600.0 - i * 10, mlbam=1000 + i,
                        bats=bats_cycle[i % len(bats_cycle)]))
    return out


# --- the per-hand estimator, platoon_ratio_v1 (census M06-05) ----------------

def _scored_one(hi, pool):
    H.derive_rates(hi)
    H.hem_plus(hi, pool)
    return hi


def _raw_pair(season, cl, cr, pool, mu=None):
    """The two hands' UNROUNDED HEM+ and their wOBA denominators, rebuilt from
    the module's own pieces, for invariants that rounding would blur."""
    ll, lr = H._line_hitter(cl), H._line_hitter(cr)
    q, n = H.platoon_ratio(ll, lr)
    qs = H.shrink_platoon_ratio(q, n, H.platoon_side(season.bats), mu or H.MU_PLATOON_FROZEN)
    dl, dr = H._woba_denom(ll), H._woba_denom(lr)
    ml, mr = H.hand_multipliers(qs, dl, dr)

    def hem(w):
        return 100.0 + H.HEM_SPREAD_GAIN * (100.0 * w / pool.mean_woba - 100.0)
    return hem(season.woba_skill * ml), hem(season.woba_skill * mr), dl, dr


def test_the_estimator_id_is_the_one_the_dark_clocks_read():
    """The 5e / 5f clocks start at a vintage carrying this id; a rename on one
    side only would leave both clocks unstartable, or start them on the wrong
    construction."""
    assert H.SPLIT_ESTIMATOR == lv.SPLIT_ESTIMATOR_ID == "platoon_ratio_v1"


def test_split_pair_is_none_on_unusable_input():
    pool = _pool(_nine())
    s = _scored_one(_hit("x", mlbam=1, bats="L"), pool)
    assert H.split_hem_pair(s, None, None, pool) == {"L": None, "R": None}
    assert H.split_hem_pair(s, {}, {"plateAppearances": 0, "atBats": 0}, pool) == \
        {"L": None, "R": None}


def test_a_missing_hand_serves_the_season_level_on_the_other():
    """One line only: no ratio sample, so the served hand is the season number."""
    pool = _pool(_nine())
    s = _scored_one(_hit("x", mlbam=1, bats="R"), pool)
    got = H.split_hem_pair(s, None, _counts(h=70, doub=18, hr=14), pool)
    assert got["L"] is None and got["R"] == s.hem_plus


def test_the_two_hands_average_back_to_the_season_number_at_any_sample():
    """THE M06-05 REGRESSION TEST. The old construction re-shrank each hand toward
    the pool, so a strong hitter's thin split fell toward 100 and the two-hand
    mean sat below his season number (125+ hitters lost 4.7 points). Now the
    d-weighted mean of the unrounded hands IS the season number, thin or thick,
    strong or weak."""
    pool = _pool(_nine())
    for kw in ({"h": 190, "doub": 45, "hr": 45, "bb": 90},       # a star
               {"h": 120, "doub": 18, "hr": 6, "bb": 30}):       # a weak bat
        s = _scored_one(_hit("x", mlbam=1, bats="L", **kw), pool)
        for cl in (_counts(pa=25, h=4, doub=1, hr=0, bb=2, ibb=0, hbp=0, sf=0, so=8),
                   _counts(pa=180, h=40, doub=8, hr=6)):
            hl, hr, dl, dr = _raw_pair(s, cl, _counts(pa=500, h=150, doub=32, hr=30), pool)
            assert abs((hl * dl + hr * dr) / (dl + dr) - s.hem_plus_raw) < 1e-9


def test_a_thin_split_regresses_toward_the_league_gap_not_toward_100():
    """A lefty with a 25 PA line against lefties: his vs-LHP number sits his
    season level times the league ratio for left-handed batters, nowhere near
    100, and a bigger sample moves it toward his own gap."""
    pool = _pool(_nine())
    s = _scored_one(_hit("x", mlbam=1, bats="L", h=190, doub=45, hr=45, bb=90), pool)
    assert s.hem_plus >= 140
    cr = _counts(pa=500, h=150, doub=32, hr=30)
    thin = H.split_hem_pair(s, _counts(pa=25, h=4, doub=1, hr=0, bb=2, ibb=0, hbp=0,
                                       sf=0, so=8), cr, pool)
    # 4 hits in 25 PA scored alone would read far below 100; here the number is
    # within a point of the season level times the league lefty ratio
    ll, lr = H._line_hitter(thin_l := _counts(pa=25, h=4, doub=1, hr=0, bb=2, ibb=0,
                                               hbp=0, sf=0, so=8)), H._line_hitter(cr)
    ml0, _ = H.hand_multipliers(H.MU_PLATOON_FROZEN["L"], H._woba_denom(ll), H._woba_denom(lr))
    assert abs(thin["L"] - H._hem_from_woba(s.woba_skill * ml0, pool)) <= 1, thin
    assert thin["L"] > 100 and H._raw_woba(ll) < 0.25
    assert thin["L"] < s.hem_plus < thin["R"]
    assert H.split_hem_pair(s, thin_l, cr, pool) == thin
    # the ratio itself: no sample -> the league ratio; a sample of n K moves it halfway
    mu = H.MU_PLATOON_FROZEN
    assert H.shrink_platoon_ratio(None, 0.0, "L", mu) == mu["L"]
    k = H.K_PLATOON["L"]
    assert abs(H.shrink_platoon_ratio(-0.30, k, "L", mu) - (-0.30 + mu["L"]) / 2) < 1e-12
    assert H.platoon_side(None) == "ALL" and H.platoon_side("s") == "S"


def test_hand_multipliers_hold_the_season_level():
    for q in (-0.2, 0.0, 0.07):
        for dl, dr in ((100.0, 400.0), (1.0, 600.0), (300.0, 300.0)):
            ml, mr = H.hand_multipliers(q, dl, dr)
            assert abs(dl * ml + dr * mr - (dl + dr)) < 1e-9
            assert abs(ml / mr - (1.0 + q)) < 1e-12
    assert H.hand_multipliers(-0.1, 0.0, 250.0) == (0.9, 1.0)


def test_the_league_ratio_is_this_seasons_pool_with_a_frozen_fallback():
    big = {"L": {i: _counts(pa=400, h=80, doub=15, hr=8) for i in range(10)},
           "R": {i: _counts(pa=400, h=110, doub=22, hr=16) for i in range(10)}}
    bats = {i: "L" for i in range(10)}
    mu = H.league_platoon_ratios(big, bats)
    assert mu["L"] < 0 and mu["L"] != H.MU_PLATOON_FROZEN["L"]
    assert mu["ALL"] == mu["L"]                     # every bat here is a lefty
    assert mu["R"] == H.MU_PLATOON_FROZEN["R"]      # no right-handed pool
    small = {"L": {1: _counts()}, "R": {1: _counts()}}
    assert H.league_platoon_ratios(small, {1: "L"})["L"] == H.MU_PLATOON_FROZEN["L"]


def test_both_hands_share_one_pool_anchor():
    """Scoring each hand against its own pool would re-centre both to 100 and
    delete the league-wide platoon effect, which is the signal."""
    hitters = _nine()
    pool = _pool(hitters)
    for x in hitters:
        H.hem_plus(x, pool)
    counts = {"L": {1000: _counts(h=40, doub=5, hr=3)},
              "R": {1000: _counts(h=70, doub=18, hr=14)}}
    sh = H.build_split_hem(counts, pool, hitters)
    assert sh is not None and 1000 in sh
    assert hitters[0].bats == "L"
    assert sh[1000]["L"] < hitters[0].hem_plus < sh[1000]["R"]


def test_build_split_hem_is_none_without_a_feed():
    pool = _pool(_nine())
    assert H.build_split_hem(None, pool) is None
    assert H.build_split_hem({}, pool) is None


# --- the order and the served numbers --------------------------------------

def test_order_carries_split_without_touching_the_season_number():
    hitters = _nine()
    pool = _pool(hitters)
    for x in hitters:
        H.hem_plus(x, pool)
    counts = {"L": {h.mlbam: _counts(h=40, doub=5, hr=3) for h in hitters},
              "R": {h.mlbam: _counts(h=70, doub=18, hr=14) for h in hitters}}
    sh = H.build_split_hem(counts, pool)
    plain = H.build_batting_order(hitters, "L")
    split = H.build_batting_order(hitters, "L", sh)
    assert plain and split
    # the season number, the identity and the slot are untouched
    for a, b in zip(plain, split):
        assert a["key"] == b["key"] and a["slot"] == b["slot"]
        assert a["hem_plus"] == b["hem_plus"]
        assert "hem_plus_split" not in a
        assert b["hem_plus_split"] is not None


def test_split_breaks_the_permutation_identity():
    """THE REGRESSION TEST. Without a per-hand value the two hand means are equal
    by construction; with one they are not."""
    hitters = _nine()
    pool = _pool(hitters)
    for x in hitters:
        H.hem_plus(x, pool)
    counts = {"L": {h.mlbam: _counts(h=40, doub=5, hr=3) for h in hitters},
              "R": {h.mlbam: _counts(h=70, doub=18, hr=14) for h in hitters}}
    sh = H.build_split_hem(counts, pool)

    before = {"orders": {"vl": H.build_batting_order(hitters, "L"),
                         "vr": H.build_batting_order(hitters, "R")}}
    after = {"orders": {"vl": H.build_batting_order(hitters, "L", sh),
                        "vr": H.build_batting_order(hitters, "R", sh)}}
    vl0, vr0 = lv.off_splits_from_hitter_team(before)
    vl1, vr1 = lv.off_splits_from_hitter_team(after)
    assert vl0 == vr0, "the permutation identity is what the repair exists to break"
    assert vl1 is not None and vr1 is not None
    assert vl1 != vr1
    assert vl1 < vr1        # the vs-LHP line here is the weaker one


def test_capture_falls_back_per_slot_when_a_split_is_missing():
    """A partial feed must stay servable: a slot with no split uses its season
    number rather than dropping out of the mean."""
    hitters = _nine()
    pool = _pool(hitters)
    for x in hitters:
        H.hem_plus(x, pool)
    only_one = {"L": {hitters[0].mlbam: _counts(h=40, doub=5, hr=3)},
                "R": {hitters[0].mlbam: _counts(h=70, doub=18, hr=14)}}
    sh = H.build_split_hem(only_one, pool)
    order = H.build_batting_order(hitters, "L", sh)
    assert order
    n_split = sum(1 for s in order if s.get("hem_plus_split") is not None)
    assert n_split == 1
    assert lv._pa_weighted_hem(order) is not None


def test_team_offense_plus_is_untouched_by_the_split():
    """Offense+ feeds betting_model and the 600-game clock's vintages, so the
    split must not move it."""
    hitters = _nine(bats_cycle=("L", "R", "S"))
    pool = _pool(hitters)
    for x in hitters:
        H.hem_plus(x, pool)
    counts = {"L": {h.mlbam: _counts(h=40, doub=5, hr=3) for h in hitters},
              "R": {h.mlbam: _counts(h=70, doub=18, hr=14) for h in hitters}}
    sh = H.build_split_hem(counts, pool)
    a = H.team_offense("AAA", hitters)
    b = H.team_offense("AAA", hitters, None, sh)
    assert a["offense_plus"] == b["offense_plus"]
    assert a["offense_plus_raw"] == b["offense_plus_raw"]
    assert a["team_pa"] == b["team_pa"]


def test_the_served_price_cannot_see_the_per_hand_values():
    """The served model reads z_off (Offense+) only. Two team-input sets that
    differ in nothing but off_vs_lhp / off_vs_rhp price every game identically."""
    import betting_model as bm
    off = {"AAA": 105.0, "BBB": 95.0, "CCC": 100.0}
    rots = {"AAA": 100.0, "BBB": 103.0, "CCC": 97.0}
    pens = {"AAA": 98.0, "BBB": 101.0, "CCC": 100.0}
    ip = {o: 800.0 for o in off}
    rip = {o: 550.0 for o in off}

    def extras(shift):
        out = {}
        for i, o in enumerate(sorted(off)):
            e = {c: None for c in bm.DARK_TEAM_COLUMNS}
            e["off_vs_lhp"], e["off_vs_rhp"] = off[o] - 6 + shift * i, off[o] + 3 - shift
            out[o] = e
        return out
    a = bm._assemble_team_inputs(off, rots, pens, ip, rip, extras(0.0))
    b = bm._assemble_team_inputs(off, rots, pens, ip, rip, extras(9.0))
    assert a["AAA"]["off_vs_lhp"] != b["AAA"]["off_vs_lhp"] or \
        a["CCC"]["off_vs_lhp"] != b["CCC"]["off_vs_lhp"]
    for o in off:
        assert a[o]["z_off"] == b[o]["z_off"]

    def strip(gp):
        return json.dumps({k: v for k, v in (gp or {}).items() if not callable(v)},
                          sort_keys=True, default=str)
    for h, aw in (("AAA", "BBB"), ("CCC", "AAA")):
        pa = bm.game_probabilities(h, aw, teams=a, parks={})
        pb = bm.game_probabilities(h, aw, teams=b, parks={})
        assert pa and strip(pa) == strip(pb)


def test_served_board_two_hand_mean_matches_season_hem():
    """The pass condition the estimator was registered with (docs/diamond-betting.md
    5e), on the served artifact: for 300+ PA hitters with both hands in the
    constructed orders, the split-PA weighted two-hand mean is within 1 point of
    season HEM+, and the gap has no slope on (season - 100) (it was -0.15)."""
    import pytest
    board = Path(__file__).parent / "data" / "hitter_leaderboards.json"
    if not board.exists():
        pytest.skip("hitter_leaderboards.json not generated")
    d = json.loads(board.read_text(encoding="utf-8"))
    if (d.get("platoon_splits") or {}).get("estimator") != H.SPLIT_ESTIMATOR:
        pytest.skip("served board predates estimator platoon_ratio_v1")
    xs, ys = [], []
    for t in d["teams"]:
        vl = {r["key"]: r for r in (t.get("orders") or {}).get("vl") or []}
        vr = {r["key"]: r for r in (t.get("orders") or {}).get("vr") or []}
        for k in set(vl) & set(vr):
            a, b = vl[k], vr[k]
            if a.get("hem_plus_split") is None or b.get("hem_plus_split") is None:
                continue
            wl, wr = a.get("split_pa") or 0, b.get("split_pa") or 0
            if a["pa"] < 300 or wl + wr <= 0:
                continue
            m = (a["hem_plus_split"] * wl + b["hem_plus_split"] * wr) / (wl + wr)
            xs.append(a["hem_plus"] - 100.0)
            ys.append(m - a["hem_plus"])
    assert len(xs) >= 100, len(xs)
    assert max(abs(y) for y in ys) <= 1.0, max(abs(y) for y in ys)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
             / sum((x - mx) ** 2 for x in xs))
    assert abs(slope) <= 0.03, slope


# --- the availability block -------------------------------------------------

def test_availability_block_flags_the_degenerate_state():
    """The tripwire: the lens reported available while every club still serves an
    identical mean is the exact broken state, and it must WARN, never raise, or
    the nightly vintage write the 600-game clock runs on would stop."""
    import hitter_export as he
    hitters = _nine()
    pool = _pool(hitters)
    for x in hitters:
        H.hem_plus(x, pool)
    orders = {"vl": H.build_batting_order(hitters, "L"),
              "vr": H.build_batting_order(hitters, "R")}
    teams = [{"team": "AAA", "orders": orders}]
    meta = he._platoon_split_availability(teams, {"L": {1: {}}, "R": {1: {}}})
    assert meta["n_teams_split_equal"] == 1
    assert meta["available"] is False        # no slot resolved a split value
    assert meta["n_slots"] == 18 and meta["n_slots_split"] == 0


def test_availability_block_reports_no_feed_distinctly():
    import hitter_export as he
    meta = he._platoon_split_availability([], None)
    assert meta["available"] is False
    assert "reason" in meta
    assert meta["n_rows_vs_lhp"] == 0 and meta["n_rows_vs_rhp"] == 0
