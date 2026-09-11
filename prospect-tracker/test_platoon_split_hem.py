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
"""
from __future__ import annotations

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


# --- split_hem_plus ---------------------------------------------------------

def test_split_hem_plus_is_none_on_unusable_input():
    pool = _pool(_nine())
    assert H.split_hem_plus(None, pool) is None
    assert H.split_hem_plus({}, pool) is None
    assert H.split_hem_plus({"plateAppearances": 0, "atBats": 0}, pool) is None


def test_split_hem_plus_scales_with_offense():
    pool = _pool(_nine())
    weak = H.split_hem_plus(_counts(h=35, doub=4, hr=2), pool)
    strong = H.split_hem_plus(_counts(h=70, doub=18, hr=15), pool)
    assert weak is not None and strong is not None
    assert strong > weak


def test_split_hem_plus_shrinks_a_thin_sample_toward_the_pool():
    """The same rate on 20 PA must sit closer to 100 than on 400 PA. No new
    constant: the existing per-component reliability constants do this."""
    pool = _pool(_nine())
    big = H.split_hem_plus(_counts(pa=400, h=140, doub=36, hr=30, bb=36, so=80), pool)
    small = H.split_hem_plus(_counts(pa=20, h=7, doub=2, hr=2, bb=2, ibb=0,
                                     hbp=0, sf=0, so=4), pool)
    assert big is not None and small is not None
    assert abs(small - 100) < abs(big - 100)


def test_both_hands_share_one_pool_anchor():
    """Scoring each hand against its own pool would re-centre both to 100 and
    delete the league-wide platoon effect, which is the signal."""
    pool = _pool(_nine())
    counts = {"L": {1000: _counts(h=40, doub=5, hr=3)},
              "R": {1000: _counts(h=70, doub=18, hr=14)}}
    sh = H.build_split_hem(counts, pool)
    assert sh is not None and 1000 in sh
    assert sh[1000]["L"] < sh[1000]["R"]


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
