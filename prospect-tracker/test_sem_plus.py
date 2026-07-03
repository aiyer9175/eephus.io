# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for sem_plus.py - the SEM+ starter model core.

Covers the load-bearing properties: 100 = average qualified starter, run
prevention inverts (lower FIP -> higher SEM+), small samples shrink, the
starter population filter (GS-share), durability stays OUT of the skill number,
role assignment, and the starter-IP-weighted Rotation+.
"""
from __future__ import annotations

import sem_plus as sp
from sem_plus import Starter


def _st(key, so, bb, hr, *, tbf=600.0, ip=150.0, hbp=4.0, er=65.0, r=70.0,
        g=25, gs=25, pit=2400.0, strikes=1560.0, cg=0, go=250.0, ao=250.0, team=""):
    return Starter(key=key, name=key, team=team, g=g, gs=gs, ip=ip, tbf=tbf,
                   so=so, bb=bb, hbp=hbp, hr=hr, er=er, r=r, pit=pit,
                   strikes=strikes, cg=cg, go=go, ao=ao)


def _avg_pool(n=12):
    # league-average starter clones: ~21% K, ~7.5% BB, ~3% HR
    return [_st(f"avg{i}", so=126, bb=45, hr=18) for i in range(n)]


def test_scale_anchored_at_100():
    out = sp.score_pool(_avg_pool())
    sems = [s["sem_plus"] for s in out["starters"]]
    assert sems
    assert all(abs(x - 100) <= 1 for x in sems), sems


def test_inversion_direction_and_ratio():
    ace = _st("ace", so=210, bb=30, hr=12)     # elite K/BB/HR -> low FIP
    scrub = _st("scrub", so=90, bb=75, hr=30)  # worse everywhere
    out = sp.score_pool(_avg_pool() + [ace, scrub])
    by = {s["key"]: s for s in out["starters"]}
    assert by["ace"]["sem_plus"] > 112, by["ace"]["sem_plus"]
    assert by["scrub"]["sem_plus"] < 90, by["scrub"]["sem_plus"]
    assert by["ace"]["fip"] < by["scrub"]["fip"]


def test_small_sample_is_shrunk():
    # identical ELITE per-batter rates (~33% K, 5% BB, ~1.7% HR), one on a small
    # sample and one on a full season. The small sample is regressed harder
    # toward the pool, so it scores LOWER and does not blow up.
    tiny = _st("tiny", so=20, bb=3, hr=1, tbf=60, ip=15, gs=3, g=3, pit=240, strikes=156, er=5, r=5)
    big = _st("big", so=200, bb=30, hr=10, tbf=600, ip=150, gs=25, g=25, pit=2400, strikes=1560, er=50, r=54)
    out = sp.score_pool(_avg_pool() + [tiny, big])
    by = {s["key"]: s for s in out["starters"]}
    assert by["tiny"]["sem_plus"] < by["big"]["sem_plus"], (by["tiny"]["sem_plus"], by["big"]["sem_plus"])
    assert by["tiny"]["sem_plus"] < 160, by["tiny"]["sem_plus"]


def test_starter_population_filter():
    assert sp.is_true_starter(_st("sp", 126, 45, 18, g=30, gs=30))
    assert sp.is_true_starter(_st("swing", 126, 45, 18, g=30, gs=15))       # 0.50 share ok
    assert not sp.is_true_starter(_st("mostly_pen", 126, 45, 18, g=40, gs=10))  # 0.25 share
    assert not sp.is_true_starter(_st("reliever", 60, 20, 8, g=60, gs=0, ip=65))


def test_durability_does_not_move_the_skill_number():
    # two arms, same rate line, very different workload: SEM+ must be equal
    short = _st("x", so=126, bb=45, hr=18, ip=150, tbf=600, gs=25, g=25)
    deep = _st("x", so=126 * 2, bb=45 * 2, hr=18 * 2, ip=300, tbf=1200, gs=34, g=34,
               pit=4800, strikes=3120, er=130, r=140)
    a = {s["key"]: s for s in sp.score_pool(_avg_pool() + [short])["starters"]}
    b = {s["key"]: s for s in sp.score_pool(_avg_pool() + [deep])["starters"]}
    # identical per-batter rates -> identical SEM+ regardless of innings volume
    assert abs(a["x"]["sem_plus"] - b["x"]["sem_plus"]) <= 1


def test_rotation_plus_is_starter_ip_weighted():
    good = _st("good", so=210, bb=30, hr=12, ip=200, tbf=800, team="LAD", gs=32, g=32,
               pit=3200, strikes=2080, er=55, r=60)
    weak = _st("weak", so=95, bb=70, hr=28, ip=90, tbf=400, team="LAD", gs=16, g=16,
               pit=1500, strikes=950, er=60, r=64)
    out = sp.score_pool(_avg_pool() + [good, weak])
    team = next(t for t in out["teams"] if t["team"] == "LAD")
    by = {s["key"]: s for s in out["starters"]}
    assert by["good"]["sem_plus"] > by["weak"]["sem_plus"]
    # the front-3 read leans to the good arm
    assert team["front_sem"] >= by["weak"]["sem_plus"]


def test_roles_ace_to_spot():
    ace = _st("ace", so=210, bb=30, hr=12, team="ATL")
    mid = _st("mid", so=140, bb=48, hr=18, team="ATL")
    spot = _st("spot", so=90, bb=72, hr=30, team="ATL")
    out = sp.score_pool(_avg_pool() + [ace, mid, spot])
    role = {s["key"]: s["role"] for s in out["starters"]}
    assert role["ace"] == "Ace"
    assert role["spot"] == "Spot"


def test_provisional_tiering():
    small = _st("small", so=40, bb=15, hr=6, tbf=200, ip=48, g=8, gs=8, pit=800, strikes=520, er=22, r=24)
    out = sp.score_pool(_avg_pool() + [small])
    by = {s["key"]: s for s in out["starters"]}
    assert by["small"]["qualified"] is False    # under 10 GS and under 50 IP
    assert by["avg0"]["qualified"] is True
