# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV upside and volatility driver read pins (EFV_UPSIDE_VOLATILITY_DRIVERS,
docs/efv-v2/EFV_UPSIDE_VOLATILITY_DRIVERS.md).

1. Parsing and as-of reads: heights, velocity ranges, levers; a board after the read date or
   outside the lookback is never read; the velocity change compares boards 300 days apart.
2. The machinery: the grid weights, the threshold logistic CDF, CRPS and the class log loss,
   the clustered bootstrap, the permuted twin, BH, the rule and the classes.
3. The read, when it has run: development only, the rule as registered, the hand-off list.
4. Gate compliance: no FV-cell grouping, no dash characters.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

import efv_upside_volatility as UV

ROOT = Path(__file__).parent
SRC = ROOT / "efv_upside_volatility.py"
DOC = ROOT / UV.DOC


def test_parsers():
    assert UV.parse_height("6' 2") == 74.0
    assert UV.parse_height("5' 11\"") == 71.0
    assert UV.parse_height(73) == 73.0
    assert UV.parse_height("tall") is None
    assert UV.parse_velo("92-95") == 93.5
    assert UV.parse_velo("94") == 94.0
    assert UV.parse_velo("n/a") is None
    assert UV.parse_levers("Long") == 1.0 and UV.parse_levers("Short") == -1.0
    assert UV.parse_levers("") is None
    assert UV.parse_scale(3) is None and UV.parse_scale(-1) == -1.0
    assert UV.outs_of("12.2") == 38.0


def test_board_reads_are_as_of_and_inside_the_lookback():
    boards = [("2015-01-01", {"sits": "90-92"}), ("2017-03-01", {"sits": "93-95"}),
              ("2018-02-01", {"sits": "95-97"}), ("2019-06-01", {"sits": "99-100"})]
    got = UV.board_asof(boards, "2018-03-01", "sits", UV.parse_velo)
    assert got == ("2018-02-01", 96.0)
    # the 2015 board is outside the 730-day lookback of 2017-06-01
    assert UV.board_asof(boards[:1], "2017-06-01", "sits", UV.parse_velo) is None
    # change: the 2018-02-01 board against the latest one at least 300 days before it
    assert UV.change_asof(boards, "2018-03-01", "sits", UV.parse_velo) == pytest.approx(2.0)
    assert UV.change_asof(boards[1:3], "2017-12-01", "sits", UV.parse_velo) is None


def test_the_grid_weights_are_trapezoid_and_the_class_cuts_sit_on_the_grid():
    w = UV.grid_weights()
    g = np.asarray(UV.GRID)
    assert w.sum() == pytest.approx(g[-1] - g[0])
    assert UV.GRID[UV.J_BUST] == UV.BUST_WAR and UV.GRID[UV.J_STAR] == UV.STAR_WAR
    assert list(UV.class_of(np.array([-1.0, 0.0, 0.1, 10.0, 10.1]))) == [0, 0, 1, 1, 2]


def test_the_threshold_logit_recovers_a_location_shift_and_stays_monotone():
    rng = np.random.default_rng(0)
    n = 3000
    x = rng.standard_normal(n)
    y = 4.0 + 3.0 * x + rng.standard_normal(n) * 2.0
    X = np.column_stack([np.ones(n), x])
    F = UV.predict_cdf(X, y, np.array([[1.0, -1.0], [1.0, 1.0]]))
    assert np.all(np.diff(F, axis=1) >= 0)
    assert np.all(F[0] >= F[1])                     # higher x, less mass below each cut
    # the candidate with the informative column scores better than the intercept only
    one = X[:, :1]
    Fi = UV.predict_cdf(one, y, one)
    Fx = UV.predict_cdf(X, y, X)
    assert UV.crps_rows(Fx, y).mean() < UV.crps_rows(Fi, y).mean()
    assert UV.logloss_rows(Fx, y).mean() < UV.logloss_rows(Fi, y).mean()


def test_crps_is_zero_for_a_perfect_step_and_the_log_loss_is_floored():
    y = np.array([3.0])
    ind = (y[:, None] <= np.asarray(UV.GRID)[None, :]).astype(float)
    assert UV.crps_rows(ind, y)[0] == 0.0
    F = np.zeros((1, len(UV.GRID)))
    F[0, :] = 1.0                                   # all mass at or below -1: BUST certain
    assert UV.logloss_rows(F, np.array([20.0]))[0] == pytest.approx(-np.log(1e-6))


def test_the_clustered_bootstrap_sign():
    keys = [f"p{i // 2}" for i in range(400)]
    d = np.random.default_rng(1).normal(0.3, 1.0, 400)
    got = UV.cluster_boot(d, keys, B=300, seed=2)
    assert got["delta"] > 0 and got["ci95"][0] < got["delta"] < got["ci95"][1]
    assert got["n_clusters"] == 200 and got["p"] < 0.05


def test_the_permuted_twin_keeps_each_group_multiset():
    rows = [{"rk": f"r{i}", "group": "a" if i < 10 else "b"} for i in range(20)]
    vals = {f"r{i}": (None if i % 3 == 0 else float(i)) for i in range(20)}
    tw = UV.permute_within(rows, vals, np.random.default_rng(3))
    for g, lo, hi in (("a", 0, 10), ("b", 10, 20)):
        a = sorted(str(vals[f"r{i}"]) for i in range(lo, hi))
        b = sorted(str(tw[f"r{i}"]) for i in range(lo, hi))
        assert a == b, g


def test_bh_rule_and_classes():
    q = UV.bh([0.01, 0.04, 0.03, 0.5])
    assert q[0] == pytest.approx(0.04) and q[3] == pytest.approx(0.5)
    assert q[1] == pytest.approx(0.04 * 4 / 3) and q[2] == pytest.approx(0.04 * 4 / 3)
    ok = UV.passes({"delta": 0.01, "ci95": [0.001, 0.02]}, 0.005, 0.05, True)
    assert ok["passes"]
    assert not UV.passes({"delta": 0.01, "ci95": [0.001, 0.02]}, 0.02, 0.05, True)["passes"]
    assert not UV.passes({"delta": 0.01, "ci95": [0.001, 0.02]}, 0.005, 0.2, True)["passes"]
    assert not UV.passes({"delta": 0.01, "ci95": [0.001, 0.02]}, 0.005, 0.05, False)["passes"]
    assert UV.classify(True, False, False) == "MEAN"
    assert UV.classify(True, True, False) == "BOTH"
    assert UV.classify(False, False, True) == "TAILS ONLY"
    assert UV.classify(False, False, False) == "NONE"


def test_frame_resid_is_fitted_inside_each_group():
    rng = np.random.default_rng(4)
    rows, facts = [], {}
    for i in range(40):
        rk = f"r{i}"
        g = "g1" if i < 20 else "g2"
        h = 70 + rng.integers(0, 8)
        a = 18 + rng.random() * 4
        w = 30 + 2.5 * h + (20 if g == "g2" else 0) + (5 if i in (3, 25) else 0)
        rows.append({"rk": rk, "group": g})
        facts[rk] = {"height_in": float(h), "weight_lb": float(w), "_age_A": float(a)}
    facts["r7"]["weight_lb"] = None
    got = UV.cell_values(rows, facts, "frame_resid")
    assert got["r7"] is None
    assert got["r3"] > 3 and got["r25"] > 3
    assert abs(np.mean([v for k, v in got.items() if v is not None])) < 1e-6


def test_markers_and_groups_as_registered():
    assert len([m for m in UV.MARKERS if m.startswith("U")]) == 18
    assert len([m for m in UV.MARKERS if m.startswith("V")]) == 10
    assert UV.groups_for("hit") == ("all", "C", "SS", "CF", "IF", "COF", "1B/DH")
    assert UV.groups_for("pit") == ("all", "SP", "RP")
    import efv5_atlas as A
    assert UV.POS_GROUP == A.POS_GROUP


def test_the_read_artifact():
    if not UV.OUT_PATH.exists():
        pytest.skip("the read has not run in this tree")
    d = json.loads(UV.OUT_PATH.read_text(encoding="utf-8"))
    assert d["role"] == "development" and d["adjudicates"] is False and d["served"] is False
    import efv_vintage_frame as F
    for k, v in d["rows"].items():
        fid, _side = k.split("|")
        for y in v["years"]:
            assert not (fid == "lv_dev" and y in F.RESERVED_LV)
            assert not (fid == "vm_dev" and y >= F.R_VM_FIRST_DEBUT_YEAR)
    for cid, e in d["cells"].items():
        for s in e["scored"]:
            r = e["reads"][s]
            assert r["rule"]["passes"] == all(r["rule"]["checks"].values()), (cid, s)
    want = sorted(f"{cid}|{s}" for cid, e in d["cells"].items() for s in e["scored"]
                  if e["reads"][s]["rule"]["passes"])
    assert d["handoff_x3"] == want


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, str)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
        assert ch not in Path(__file__).read_text(encoding="utf-8")
