# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for hem_plus.py - the HEM+ hitter model core.

Covers the load-bearing properties: 100 = average qualified hitter, offense
scales the right way (more wOBA -> higher HEM+), small samples shrink, volume
(PA) stays OUT of the skill number, the PA-weighted team Offense+, qualified
tiering, and the shipped eval-artifact gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import hem_plus as H
from hem_plus import Hitter


def _hit(key, h=145, doub=26, trip=3, hr=17, bb=45, so=145, *, pa=600.0,
         ibb=4.0, hbp=4.0, sf=4.0, sb=0.0, cs=0.0, team=""):
    ab = pa - bb - hbp - sf
    return Hitter(key=key, name=key, team=team, pa=pa, ab=ab, h=h, doub=doub,
                  trip=trip, hr=hr, bb=bb, ibb=ibb, hbp=hbp, sf=sf, so=so, sb=sb, cs=cs)


def _avg_pool(n=12):
    return [_hit(f"avg{i}") for i in range(n)]


def test_scale_anchored_at_100():
    out = H.score_pool(_avg_pool())
    hems = [h["hem_plus"] for h in out["hitters"]]
    assert hems
    assert all(abs(x - 100) <= 1 for x in hems), hems


def test_direction_and_ratio():
    elite = _hit("elite", h=190, doub=42, trip=4, hr=44, bb=100, so=120)
    weak = _hit("weak", h=110, doub=15, trip=1, hr=6, bb=25, so=185)
    out = H.score_pool(_avg_pool() + [elite, weak])
    by = {h["key"]: h for h in out["hitters"]}
    assert by["elite"]["hem_plus"] > 115, by["elite"]["hem_plus"]
    assert by["weak"]["hem_plus"] < 90, by["weak"]["hem_plus"]
    assert by["elite"]["woba"] > by["weak"]["woba"]


def test_small_sample_is_shrunk():
    # identical ELITE rate line, one on a tiny sample and one on a full season.
    # The small sample regresses harder toward the pool -> lower + no blow-up.
    tiny = _hit("tiny", h=38, doub=8, trip=1, hr=9, bb=20, so=24, pa=120,
                ibb=1, hbp=1, sf=1)
    big = _hit("big", h=190, doub=40, trip=5, hr=45, bb=100, so=120, pa=600)
    out = H.score_pool(_avg_pool() + [tiny, big])
    by = {h["key"]: h for h in out["hitters"]}
    assert by["tiny"]["hem_plus"] < by["big"]["hem_plus"], (by["tiny"]["hem_plus"], by["big"]["hem_plus"])
    assert by["tiny"]["hem_plus"] < 160, by["tiny"]["hem_plus"]


def test_volume_does_not_move_the_skill_number():
    # same rate line, very different PA volume: HEM+ must be ~equal (volume is
    # context, not rate skill). Half the counts on half the PA = same rates.
    full = _hit("x", h=160, doub=30, trip=3, hr=25, bb=60, so=130, pa=600,
                ibb=4, hbp=4, sf=4)
    half = _hit("x", h=80, doub=15, trip=1.5, hr=12.5, bb=30, so=65, pa=300,
                ibb=2, hbp=2, sf=2)
    a = {h["key"]: h for h in H.score_pool(_avg_pool() + [full])["hitters"]}
    b = {h["key"]: h for h in H.score_pool(_avg_pool() + [half])["hitters"]}
    # the shrink pulls the smaller sample slightly more, but the rate skill is the
    # same line, so the two land within a couple points, not a volume-driven gap.
    assert abs(a["x"]["hem_plus"] - b["x"]["hem_plus"]) <= 4


def test_offense_plus_is_pa_weighted():
    good = _hit("good", h=185, doub=40, trip=4, hr=40, bb=90, so=125, pa=650, team="LAD")
    weak = _hit("weak", h=100, doub=13, trip=1, hr=5, bb=22, so=180, pa=300, team="LAD")
    out = H.score_pool(_avg_pool() + [good, weak])
    team = next(t for t in out["teams"] if t["team"] == "LAD")
    by = {h["key"]: h for h in out["hitters"]}
    assert by["good"]["hem_plus"] > by["weak"]["hem_plus"]
    assert team["offense_plus"] is not None
    assert team["heart_hem"] >= by["weak"]["hem_plus"]   # heart leans to the good bat


def test_qualified_tiering():
    small = _hit("small", h=45, doub=8, trip=1, hr=5, bb=15, so=45, pa=180,
                 ibb=1, hbp=1, sf=1)
    out = H.score_pool(_avg_pool() + [small])
    by = {h["key"]: h for h in out["hitters"]}
    assert by["small"]["qualified"] is False   # under 200 wOBA-PA
    assert by["avg0"]["qualified"] is True


def test_eval_artifact_present_and_gate_passes():
    doc = json.loads((Path(H.__file__).parent / "data" / "hem_plus_eval.json").read_text(encoding="utf-8"))
    assert doc["experiment"] == "X-H1"
    assert doc["model"] == "hem_plus"
    assert doc["gate"]["pass"] is True
    assert doc["verdict"]["status"] == "validated"
    fs = doc["forward_spearman_vs_wOBA_next"]
    # HEM+ beats AVG and is at least even with raw wOBA out of sample
    assert fs["hem_plus"] >= fs["avg"]
    assert fs["hem_plus"] >= fs["raw_woba"] - 0.01


def test_multiyear_eval_3yr_beats_1yr():
    doc = json.loads((Path(H.__file__).parent / "data" / "hem_plus_multiyear_eval.json").read_text(encoding="utf-8"))
    assert doc["experiment"] == "X-H2"
    assert doc["model"] == "hem_plus_3yr"
    # 3yr forward-predicts next-year offense better than 1yr on the same set
    assert doc["hem_3yr_forward_rho"] > doc["hem_1yr_forward_rho_on_3yr_set"]
    assert doc["gate"]["pass"] is True
    pv = doc["proposed_values"]
    assert pv["metric"] == "hem_plus_3yr" and pv["n_with_value"] > 0


def test_xhem_eval_xwoba_beats_actual_woba():
    doc = json.loads((Path(H.__file__).parent / "data" / "xhem_plus_eval.json").read_text(encoding="utf-8"))
    assert doc["experiment"] == "X-H3" and doc["model"] == "xhem_plus"
    fs = doc["forward_spearman_vs_wOBA_next"]
    # Savant xwOBA forward-predicts next-year wOBA better than actual wOBA
    assert fs["xwoba"] > fs["actual_woba"]
    assert doc["gate"]["pass"] is True
    assert doc["gap_ci_xwoba_minus_woba"]["lo95"] > 0
