# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV output map test pins (EFV_OUTPUT_MAP_TEST, docs/efv-v2/EFV_OUTPUT_MAP_TEST.md).

1. The maps: A is the served map; Z is consensus; at zero shift D0, B and C return each
   row's own consensus; D is monotone in the order and never leaves the group's range; B and
   C follow their registered formulas; on a Walcott-shaped group A drops the top row many
   grades for a tiny shift and D does not.
2. The machinery: the lexicographic guard score, the movement-matched null comparator,
   Holm's step-down, the paired mean's sign, the planted check's power and size, the
   instruments as committed.
3. The read, when it has run: development only, the checks held, the rule as registered.
4. Gate compliance: no FV-cell grouping, no dash characters.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

import efv_output_map as X
import efv_v2_model as H

ROOT = Path(__file__).parent
SRC = ROOT / "efv_output_map.py"
DOC = ROOT / X.DOC


def _group(n=200, seed=0):
    rng = np.random.default_rng(seed)
    c = np.round(rng.normal(45, 5, n) * 2) / 2      # repeated half-grade values, as consensus
    u = H.within_pct(c, [0] * n)
    return c, u


def test_A_is_the_served_map_and_Z_is_consensus():
    c, u = _group()
    o = u + np.random.default_rng(1).normal(0, 0.05, c.size)
    assert np.array_equal(X.map_group("A", c, o), H.output_map(o, [0] * c.size, c))
    assert np.array_equal(X.map_group("Z", c, o), c)


def test_every_map_returns_consensus_at_zero_shift_where_registered():
    c, u = _group()
    assert np.allclose(X.map_group("D0", c, u), c)
    assert np.allclose(X.map_group("B", c, u), c)
    assert np.allclose(X.map_group("C", c, u), c)
    assert np.allclose(X.map_group("A", c, u), c)


def test_D_is_monotone_in_the_order_and_stays_in_range():
    c, u = _group()
    o = u + np.random.default_rng(2).normal(0, 0.3, c.size)
    g = X.map_group("D", c, o)
    srt = np.argsort(o, kind="mergesort")
    assert np.all(np.diff(g[srt]) >= -1e-12)
    assert g.min() >= c.min() - 1e-12 and g.max() <= c.max() + 1e-12
    for name in ("B", "D0"):
        h = X.map_group(name, c, o)
        assert h.min() >= c.min() - 1e-12 and h.max() <= c.max() + 1e-12


def test_smoothed_quantile_is_nondecreasing_and_k0_is_the_sorted_values():
    c, _u = _group(n=97, seed=3)
    t, v = X.smoothed_quantile(c, 0.0)
    assert np.array_equal(v, np.sort(c)) and np.allclose(t, np.arange(1, 98) / 97)
    t2, v2 = X.smoothed_quantile(c, 0.05)
    assert np.all(np.diff(v2) >= 0)
    assert v2[0] == np.sort(c)[0] and v2[-1] == np.sort(c)[-1]


def test_B_moves_by_the_local_slope_and_C_damps_where_grades_are_steep():
    c = np.linspace(40, 60, 101)
    c[-10:] = np.linspace(60, 75, 10)                 # a steep top
    u = H.within_pct(c, [0] * c.size)
    s = np.zeros(c.size)
    s[50] = 0.01
    gb = X.map_group("B", c, u + s)
    t, v = X.smoothed_quantile(c, X.H_SMOOTH)
    d = X.local_slope(t, v, u[50:51])[0]
    assert gb[50] == pytest.approx(c[50] + 0.01 * d)
    # one row near the steep top shifted up a long way: C moves it less than A
    s2 = np.zeros(c.size)
    s2[85] = 0.1
    ga = X.map_group("A", c, u + s2)
    gc = X.map_group("C", c, u + s2)
    assert gc[85] - c[85] <= ga[85] - c[85] + 1e-12


def test_a_walcott_shaped_group_drops_under_A_and_holds_under_D():
    n = 1000
    c = np.linspace(35, 60, n)
    u = H.within_pct(c, [0] * n)
    s = np.zeros(n)
    top = n - 7                                      # the seventh-best row
    s[top] = -0.0012
    s[n - 60:top] = 0.025                            # rows below him pushed up 2.5 points
    o = u + s
    ga, gd = X.map_group("A", c, o), X.map_group("D", c, o)
    assert c[top] - ga[top] > 0.5
    assert abs(gd[top] - c[top]) < 0.1


def test_the_guard_score_orders_by_grade_then_order():
    g = np.array([50.0, 50.0, 55.0, 40.0])
    o = np.array([0.2, 0.3, 0.1, 0.9])
    sc = X.lex_score(g, o)
    assert list(np.argsort(sc)) == [3, 0, 1, 2]
    same = X.lex_score(np.array([1.0, 1.0]), np.array([0.5, 0.5]))
    assert same[0] == same[1]


def test_the_null_comparator_matches_the_movement():
    c, u = _group(seed=4)
    o = u + np.random.default_rng(5).normal(0, 0.05, c.size)
    groups = [(c, o)]
    target = 0.5 * X.movement(groups, "A")
    got = X.matched_m(groups, target)
    assert 0.0 <= got["m"] <= 1.0 and not got["capped"]
    assert got["movement"] == pytest.approx(target, abs=0.02)
    big = X.matched_m(groups, 10 * X.movement(groups, "A"))
    assert big["m"] == 1.0 and big["capped"]


def test_holm_steps_down():
    got = X.holm({"a": 0.001, "b": 0.02, "c": 0.04}, alpha=0.05)
    assert got == {"a": True, "b": True, "c": True}
    got = X.holm({"a": 0.001, "b": 0.03, "c": 0.04}, alpha=0.05)
    assert got == {"a": True, "b": False, "c": False}


def test_paired_mean_sign_and_interval():
    keys = [f"p{i}" for i in range(200)]
    draws = X.boot_draws(keys, B=300, seed=1)
    d = np.random.default_rng(0).normal(0.5, 1.0, 200)
    got = X.paired_mean(d, draws)
    assert got["delta"] > 0 and got["ci95"][0] < got["delta"] < got["ci95"][1]
    assert 0 <= got["p_le_0"] <= 0.05


def test_the_planted_check_has_power_and_size():
    rng = np.random.default_rng(7)
    n = 400
    rows = [{"key": f"p{i}", "fold_id": "f", "y": float(rng.normal(0, 0.1))} for i in range(n)]
    vA = np.zeros(n)
    vX = rng.normal(0, 1.0, n)
    got = X.planted(rows, {"A": vA, "X": vX}, "X", K=10, B=200, seed=3)
    assert got["power"] >= 0.9 and got["size"] <= 0.1


def test_the_instruments_are_the_committed_curves():
    inst = X.instruments()
    assert set(inst) == set(X.INSTRUMENTS)
    for name, by in inst.items():
        for side in ("hit", "pit"):
            k, v = by[side]
            assert np.all(np.diff(k) > 0) and np.all(np.diff(v) >= 0), (name, side)
    cur = json.loads(X.CURVES_PATH.read_text(encoding="utf-8"))
    assert list(inst["perside"]["hit"][1]) == cur["curves"]["hit"]["war"]["value"]
    assert X.t_eval(inst["clemens"]["pit"], 50.0) == pytest.approx(5.0)


def test_the_read_artifact():
    if not X.OUT_PATH.exists():
        pytest.skip("the read has not run in this tree")
    d = json.loads(X.OUT_PATH.read_text(encoding="utf-8"))
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["served_weights"]["pit"] == {"w_skill": 1.0, "w_time": 0.0}
    c = d["checks"]
    assert len(c["Q1_fold_receipts"]) == 20
    for v in c["Q2_published_within"].values():
        assert abs(v["within"] - v["artifact"]) <= X.PARITY_TOL
    for side in ("hit", "pit"):
        assert c["Q4_live_board"][side]["max_abs_u"] <= 1e-6
        for fold_id in d["reads"][side]["kappa"]["perside"]:
            frame, s, year = fold_id.split("|")
            assert s == side
            assert not (frame == "lv_dev" and int(year) in X.F.RESERVED_LV)
            assert not (frame == "vm_dev" and int(year) >= 2025)
        for x in X.CANDIDATES:
            r = d["rules"][side][x]
            assert r["passes"] == all(r["checks"].values())
    prepared = d["prepared"] or {}
    for side, x in prepared.items():
        assert d["rules"][side][x]["passes"]
    assert getattr(H, "OUTPUT_MAP_ARM", {"hit": "A", "pit": "A"}) == {"hit": "A", "pit": "A"}


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
        assert ch not in Path(__file__).read_text(encoding="utf-8")
