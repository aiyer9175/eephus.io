# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Invariants of pitch_economy.py, the arithmetic of the eWAR v3 candidate parts PE-P and
PE-H (docs/ebr-2026-09-30/EBR_GATE.md part 11.3). Pure: no file but the frozen constants'
log is read."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import pitch_economy as pe

ROOT = Path(__file__).resolve().parent
CONST_LOG = ROOT / "data" / "_labs" / "pitch_economy_constants.json"


def test_terminal_classes():
    assert pe.terminal_class("intent_walk") is None
    assert pe.terminal_class("walk") == "walk"
    assert pe.terminal_class("strikeout_double_play") == "strikeout"
    assert pe.terminal_class("grounded_into_double_play") == "out_in_play"
    assert pe.terminal_class("field_error") == "other"
    assert pe.terminal_class("catcher_interf") == "other"
    assert set(pe._CLASS_OF.values()) <= set(pe.CLASSES)


def test_recentre_is_zero_sum_per_group_and_leaves_an_empty_group():
    vals = {"a": 3.0, "b": -1.0, "c": 2.0, "d": 5.0}
    expo = {"a": 100, "b": 300, "c": 50, "d": 0}
    grp = {"a": "SP", "b": "SP", "c": "RP", "d": "X"}
    rc = pe.recentre(vals, expo, grp)
    assert abs(rc["a"] + rc["b"]) < 1e-12
    assert abs(rc["c"]) < 1e-12
    assert rc["d"] == 5.0
    assert abs(rc["a"] - (3.0 - 100 * 2.0 / 400)) < 1e-12


def test_no_shrink_gives_back_the_actual_outs():
    # with K_O = K_B = 0 the skill arm equals the actual arm: X~ = O
    assert abs(pe.implied_outs(30, 2700, 540, 5.5, 88, k_o=0, k_b=0) - 540) < 1e-9
    # and a pitcher at the league rates is untouched by any shrink
    x = pe.implied_outs(30, 30 * 88.0, 30 * 88.0 / 5.5, 5.5, 88.0)
    assert abs(x - 30 * 88.0 / 5.5) < 1e-9


def test_implied_outs_caps_at_27_per_appearance_and_zero_appearances():
    assert pe.implied_outs(1, 100, 30, 3.0, 100, k_o=0, k_b=0) == 27.0
    assert pe.implied_outs(0, 0, 0, 5.5, 88) == 0.0


def test_an_efficient_starter_gains_outs_under_the_shrink_only_toward_the_league():
    # 10 starts, efficient (4.5 pitches per out) on a 5.5 league: the shrink pulls ppo up,
    # so the skill arm records fewer outs than he did
    blk = pe.pe_p_raw({"SP": {"n": 10, "pitches": 900, "outs": 200}}, f_skill=3.5, f_rp=4.0,
                      t9_s=0.3, league={"SP": {"l_ppo": 5.5, "l_pa": 90.0}})
    assert blk["SP"]["gap_outs"] < 0
    assert abs(blk["SP"]["c"] - (4.0 - 3.5 - 0.3) / 27) < 1e-12
    assert abs(blk["SP"]["g"] - blk["SP"]["gap_outs"] * blk["SP"]["c"]) < 1e-12


def test_pe_p_delta_is_zero_sum_per_role():
    lg = {"SP": {"l_ppo": 5.5, "l_pa": 88.0}, "RP": {"l_ppo": 5.6, "l_pa": 17.0}}
    raw = {
        1: pe.pe_p_raw({"SP": {"n": 30, "pitches": 2800, "outs": 520}}, 3.8, 4.1, 0.25, lg),
        2: pe.pe_p_raw({"SP": {"n": 12, "pitches": 1000, "outs": 170},
                        "RP": {"n": 9, "pitches": 300, "outs": 40}}, 4.6, 4.1, 0.25, lg),
        3: pe.pe_p_raw({"RP": {"n": 60, "pitches": 1000, "outs": 190}}, 3.2, 4.1, 0.25, lg),
        4: pe.pe_p_raw({"RP": {"n": 20, "pitches": 420, "outs": 60}}, 5.0, 4.1, 0.25, lg),
    }
    d = pe.pe_p_delta(raw)
    assert abs(sum(d.values())) < 1e-9
    for role in ("SP", "RP"):
        g = {p: v[role]["g"] for p, v in raw.items() if role in v}
        o = {p: v[role]["outs"] for p, v in raw.items() if role in v}
        assert abs(sum(pe.recentre(g, o).values())) < 1e-9


def test_price_and_wear_signs():
    assert pe.price_per_out("SP", 4.0, 3.0, 0.5) == pytest.approx(0.5 / 27)
    assert pe.price_per_out("RP", 4.0, 3.0, 0.5) == pytest.approx(1.0 / 27)
    # a bullpen better than the tiring starter: making the starter throw costs the batting side
    assert pe.wear_price(4.0, 4.2, 0.3, 5.5) < 0
    assert pe.t9(1.4, 0.01) == pytest.approx(27 * 1.4 * 0.01)


def test_reliability_and_split_half_k():
    assert pe.reliability(100, None) == 0.0
    assert pe.reliability(100, math.inf) == 0.0
    assert pe.reliability(100, 100) == 0.5
    assert pe.split_half_k(None, 400) == math.inf
    assert pe.split_half_k(0.0, 400) == math.inf
    assert pe.split_half_k(-0.1, 400) == math.inf
    rho = 2 * 0.25 / 1.25
    assert pe.split_half_k(0.25, 400) == pytest.approx(400 * (1 - rho) / rho)
    assert pe.split_half_k(0.999, 400) == pe.K_CLAMP[0]
    assert pe.split_half_k(0.0001, 400) == pe.K_CLAMP[1]


def test_pe_h_with_infinite_k_carries_nothing():
    assert pe.pe_h_raw(5.0, 400, 80.0, 300, -0.004, None, None) == 0.0
    v = pe.pe_h_raw(5.0, 400, 80.0, 300, -0.004, 400.0, 300.0)
    assert v == pytest.approx(5.0 * 0.5 + (-0.004) * 80.0 * 0.5)


def test_s2_skill_fip_equals_raw_fip_at_the_pool_rates():
    nu = {"k": 0.22, "bb": 0.08, "hbp": 0.01, "hr": 0.03}
    tbf, ip = 700.0, 160.0
    m = {c: nu[c] * tbf for c in nu}
    raw = pe.fip9(m["hr"], m["bb"], m["hbp"], m["k"], ip, 3.1)
    assert pe.s2_skill_fip(m, tbf, ip, nu, 3.1) == pytest.approx(raw)
    assert pe.s2_targets(nu, {c: 0 for c in nu}, 1.0) == nu
    assert pe.s2_targets({c: 0 for c in nu}, nu, 0.0) == nu
    assert pe.s2_skill_fip(m, 0, ip, nu, 3.1) is None


def test_delta_tto_weights_and_floor():
    rows = [{"late_n": 40, "late_sum": 4.0, "all_n": 100, "all_sum": 5.0},     # +0.05
            {"late_n": 60, "late_sum": 0.0, "all_n": 120, "all_sum": -6.0},    # +0.05
            {"late_n": 10, "late_sum": 50.0, "all_n": 30, "all_sum": 0.0}]     # under the floor
    d = pe.delta_tto(rows, 30)
    assert d["starter_seasons"] == 2 and d["late_pa"] == 100
    assert d["delta_tto"] == pytest.approx(0.05)
    assert pe.delta_tto([], 30) is None


def test_frozen_constants_match_their_log_once_fitted():
    if not CONST_LOG.exists():
        assert pe.DELTA_TTO is None and pe.K_CL is None and pe.K_P is None
        return
    log = json.loads(CONST_LOG.read_text(encoding="utf-8"))
    assert pe.DELTA_TTO == pytest.approx(log["delta_tto"]["value"], abs=1e-12)
    for name in ("K_CL", "K_P"):
        blk = log[name]
        frozen = getattr(pe, name)
        if blk["K_infinite"]:
            assert frozen == math.inf
        else:
            assert frozen == pytest.approx(blk["K"], abs=1e-9)
    assert log["fit_seasons"] == list(pe.FIT_SEASONS)
