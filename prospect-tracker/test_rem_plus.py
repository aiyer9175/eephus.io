# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for rem_plus.py - the REM+ model core.

Covers the load-bearing properties: the ratio scale is anchored at 100 = average
reliever, run prevention inverts correctly (lower FIP -> higher REM+), small
samples are shrunk (no blow-ups), the talent number ignores leverage (the
two-number design), the population filter, role assignment, and the relief-IP-
weighted Bullpen+.
"""
from __future__ import annotations

import copy

import rem_plus as rp
from rem_plus import Reliever


def _rel(key, so, bb, hr, *, tbf=200.0, ip=50.0, hbp=2.0, er=23.0, r=25.0,
         g=45, gs=0, pit=800.0, sts=120.0, sv=0.0, hld=0.0, team="", gmli=None):
    return Reliever(key=key, name=key, team=team, g=g, gs=gs, ip=ip, tbf=tbf,
                    so=so, bb=bb, hbp=hbp, hr=hr, er=er, r=r, pit=pit, sts=sts,
                    sv=sv, hld=hld, gmli=gmli)


def _identical_pool(n=12):
    # league-average clones: K 20%, BB 8.5%, HR ~3%, ERA ~4.14
    return [_rel(f"avg{i}", so=40, bb=17, hr=6) for i in range(n)]


def test_scale_anchored_at_100():
    out = rp.score_pool(_identical_pool())
    rems = [r["rem_plus"] for r in out["relievers"]]
    # an all-average pool scores exactly 100 across the board
    assert rems, "no relievers scored"
    assert all(abs(x - 100) <= 1 for x in rems), rems


def test_inversion_direction_and_ratio():
    pool = _identical_pool()
    ace = _rel("ace", so=80, bb=8, hr=2)      # far more K, fewer BB/HR -> lower FIP
    scrub = _rel("scrub", so=25, bb=30, hr=12)  # worse everywhere -> higher FIP
    out = rp.score_pool(pool + [ace, scrub])
    by = {r["key"]: r for r in out["relievers"]}
    assert by["ace"]["rem_plus"] > 110, by["ace"]["rem_plus"]
    assert by["scrub"]["rem_plus"] < 90, by["scrub"]["rem_plus"]
    # ratio read: better run prevention => higher index
    assert by["ace"]["fip"] < by["scrub"]["fip"]


def test_small_sample_is_shrunk():
    pool = _identical_pool()
    # identical elite rates, but one on a tiny sample and one on a big sample
    tiny = _rel("tiny", so=16, bb=1, hr=0, tbf=20, ip=5, pit=80, sts=14, er=1, r=1, g=8)
    big = _rel("big", so=160, bb=10, hr=2, tbf=400, ip=100, pit=1600, sts=280, er=30, r=33, g=70)
    out = rp.score_pool(pool + [tiny, big])
    by = {r["key"]: r for r in out["relievers"]}
    # the tiny-sample arm is pulled toward the mean; the big-sample arm earns its grade
    assert by["tiny"]["rem_plus"] < by["big"]["rem_plus"], (by["tiny"]["rem_plus"], by["big"]["rem_plus"])
    # and the tiny-sample line does not blow up to an absurd index
    assert by["tiny"]["rem_plus"] < 150, by["tiny"]["rem_plus"]


def test_leverage_does_not_move_the_talent_number():
    base = _rel("x", so=60, bb=12, hr=4, gmli=None)
    hi = copy.deepcopy(base); hi.key = "x"; hi.gmli = 3.0; hi.wpa = 5.0; hi.sd = 30; hi.md = 2
    pool = _identical_pool()
    a = {r["key"]: r for r in rp.score_pool(pool + [copy.deepcopy(base)])["relievers"]}
    b = {r["key"]: r for r in rp.score_pool(pool + [hi])["relievers"]}
    assert a["x"]["rem_plus"] == b["x"]["rem_plus"], "gmLI/WPA must not change REM+"


def test_population_filter():
    assert rp.is_true_reliever(_rel("pure", 40, 17, 6, g=60, gs=0))
    assert rp.is_true_reliever(_rel("spot", 40, 17, 6, g=50, gs=5))      # 0.10 share ok
    assert not rp.is_true_reliever(_rel("swing", 40, 17, 6, g=50, gs=8))  # 0.16 share
    assert not rp.is_true_reliever(_rel("starter", 120, 45, 20, g=32, gs=30, ip=190))


def test_opener_excluded_when_entry_data_present():
    op = _rel("opener", so=30, bb=10, hr=4, g=40, gs=0, ip=45)
    op.entry_inning = 1.0   # enters the 1st, short stints
    out = rp.score_pool(_identical_pool() + [op])
    assert "opener" not in {r["key"] for r in out["relievers"]}


def test_bullpen_plus_is_relief_ip_weighted_not_leverage():
    # two arms on one team: a great arm that throws a lot at low leverage, and a
    # weak arm used in high leverage. IP-weighted Bullpen+ leans to the great arm.
    good = _rel("good", so=80, bb=8, hr=2, ip=70, tbf=280, team="NYY", gmli=0.7, sv=0)
    weak = _rel("weak", so=25, bb=28, hr=11, ip=30, tbf=140, team="NYY", gmli=2.2, sv=15)
    out = rp.score_pool(_identical_pool() + [good, weak])
    team = next(t for t in out["teams"] if t["team"] == "NYY")
    by = {r["key"]: r for r in out["relievers"]}
    # Bullpen+ (IP-weighted) sits above the midpoint of the two arms because the
    # good arm throws more innings; the leverage-deploy version is dragged down
    # by the high-leverage weak arm.
    assert by["good"]["rem_plus"] > by["weak"]["rem_plus"]
    assert team["bullpen_plus"] > team["leverage_deploy_plus"], (
        team["bullpen_plus"], team["leverage_deploy_plus"])


def test_roles_closer_and_high_leverage():
    closer = _rel("cl", so=60, bb=10, hr=3, team="BOS", sv=25, gmli=1.9)
    setup = _rel("su", so=55, bb=12, hr=4, team="BOS", sv=0, gmli=1.25)
    mop = _rel("mop", so=30, bb=20, hr=8, team="BOS", sv=0, gmli=0.5)
    out = rp.score_pool(_identical_pool() + [closer, setup, mop])
    role = {r["key"]: r["role"] for r in out["relievers"]}
    assert role["cl"] == "Closer"
    assert role["su"] == "Setup"
    assert role["mop"] == "Mop-up"


def test_provisional_tiering():
    small = _rel("small", so=20, bb=6, hr=2, tbf=60, ip=15, g=15, pit=240, sts=45, er=6, r=7)
    out = rp.score_pool(_identical_pool() + [small])
    by = {r["key"]: r for r in out["relievers"]}
    assert by["small"]["qualified"] is False
    assert by["avg0"]["qualified"] is True
