# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV driver weight integrity pins (EFV_WEIGHT_INTEGRITY,
docs/efv-v2/EFV_WEIGHT_INTEGRITY.md).

1. The machinery: Holm, the paired cluster bootstrap and its statistic, the pairwise rank
   loss, sign stability, the level x season re-standardization, the club rule.
2. The read, when it has run: development only, the parity checks held, every adoption
   followed the registered rule, and the flag is off.
3. Gate compliance: no FV-cell grouping, no dash characters.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest

import efv_v2_stat as S
import efv_weight_integrity as X

ROOT = Path(__file__).parent
SRC = ROOT / "efv_weight_integrity.py"
DOC = ROOT / X.DOC


def test_holm_steps_down():
    got = X.holm({"a": 0.001, "b": 0.015, "c": 0.04, "d": 0.5})
    assert got["a"]["rejects"] and got["a"]["threshold"] == pytest.approx(0.0125, abs=1e-5)
    assert got["b"]["rejects"] and got["b"]["threshold"] == pytest.approx(0.05 / 3, abs=1e-5)
    assert not got["c"]["rejects"] and not got["d"]["rejects"]
    # once a test fails, every larger p value fails
    got = X.holm({"a": 0.06, "b": 0.001, "c": 0.02})
    assert got["b"]["rejects"] and got["c"]["rejects"] and not got["a"]["rejects"]
    got = X.holm({"a": 0.03, "b": 0.001, "c": 0.04})
    assert got["b"]["rejects"] and not got["a"]["rejects"] and not got["c"]["rejects"]


def _frame(n=240, seed=3):
    rng = np.random.default_rng(seed)
    frame = np.asarray(["lv_dev"] * (n // 2) + ["vm_dev"] * (n - n // 2))
    year = rng.integers(0, 3, n)
    codes = np.asarray([f"{f}|g{y}" for f, y in zip(frame, year)])
    y = rng.normal(size=n)
    good = y + rng.normal(0, 0.5, n)
    bad = rng.normal(size=n)
    player = np.asarray([f"p{i // 2}" for i in range(n)])
    return frame, codes, y, good, bad, player


def test_the_pooled_statistic_is_the_program_within():
    frame, codes, y, good, _bad, _player = _frame()
    kept = X._groups(codes, frame)
    got = X.pooled_stat({"g": good}, y, codes, frame, kept, np.arange(y.size))["g"]
    for f in ("lv_dev", "vm_dev"):
        ix = np.flatnonzero(frame == f)
        want = S.within(good, y, codes, S.kept_groups(codes[ix]), ix)[0]
        assert got[1][f] == pytest.approx(want)


def test_the_bootstrap_reads_a_real_difference():
    frame, codes, y, good, bad, player = _frame()
    bt = X.boot({"good": good, "bad": bad}, y, codes, frame, player, B=300, seed=1)
    d = X.diff(bt, "good", "bad")
    assert d["delta"] > 0.3 and d["ci95"][0] > 0 and d["lower95_one_sided"] > 0
    assert d["p_noninferior"] < 0.01
    same = X.diff(bt, "good", "good")
    assert same["delta"] == 0 and same["p_noninferior"] < 0.01


def test_the_pairwise_rank_loss_recovers_a_planted_direction():
    rng = np.random.default_rng(5)
    n = 400
    Fm = rng.normal(size=(n, 3))
    truth = np.asarray([1.0, 0.6, -0.4])
    y = Fm @ truth + rng.normal(0, 0.3, n)
    D, pw, hi, lo = X.pair_matrix(Fm, y, np.ones(n), rng.integers(0, 4, n))
    assert pw.sum() == pytest.approx(1.0) and np.all(y[hi] > y[lo])
    b = X.pair_fit(D, pw, np.asarray([0.0, 0.01, 0.01]), np.full(3, -np.inf), np.full(3, np.inf))
    assert b[0] > 0 and b[1] / b[0] == pytest.approx(0.6, abs=0.15)
    assert b[2] / b[0] == pytest.approx(-0.4, abs=0.15)
    assert X.pair_loss(D, pw, b) < X.pair_loss(D, pw, np.zeros(3))
    # a sign bound holds
    bb = X.pair_fit(D, pw, np.asarray([0.0, 0.01, 0.01]), np.asarray([-np.inf, -np.inf, 0.0]),
                    np.full(3, np.inf))
    assert bb[2] >= 0.0


def test_sign_stability_and_the_ranking():
    loco = {2011: {"a": 0.2, "b": 0.1, "c": 0.0}, 2012: {"a": 0.25, "b": -0.1, "c": 0.0},
            2013: {"a": 0.21, "b": 0.1}}
    st = X.stability(loco, ["a", "b", "c", "d"])
    assert st["a"]["stable"] and st["a"]["sign"] == 1
    assert not st["b"]["stable"] and not st["c"]["stable"] and not st["d"]["stable"]
    loco2 = {1: {"a": 0.2, "e": -0.5}, 2: {"a": 0.21, "e": -0.1}, 3: {"a": 0.22, "e": -0.9}}
    st2 = X.stability(loco2, ["a", "e"])
    assert X.ranked(st2) == ["a", "e"] and st2["e"]["sign"] == -1


def _row(i, lvl, season, v, frame="vm", dy=None):
    return {"player_key": f"p{i}", "decision_year": dy or season + 1, "frame": frame,
            "v2": {"level_rank": lvl, "k": v, "scr_g5_x": (0.0 if i % 2 else v)}}


def test_the_restandardization_removes_season_drift_and_keeps_level():
    rng = np.random.default_rng(9)
    rows = []
    for i in range(400):
        season = 2015 if i < 200 else 2019
        lvl = 2.0 if i % 4 else 4.0
        shift = 0.0 if season == 2015 else 1.5
        rows.append(_row(i, lvl, season, float(rng.normal(shift + lvl, 1.0))))
    def season_of(r):
        return int(r["decision_year"]) - 1
    keys = ["k", "scr_g5_x"]
    ref = X.restd_reference(rows, keys)
    new, rec = X.restandardize(rows, keys, ref, season_of)
    for lvl in (2.0, 4.0):
        a = [r["v2"]["k"] for r in new if r["v2"]["level_rank"] == lvl and int(r["decision_year"]) == 2016]
        b = [r["v2"]["k"] for r in new if r["v2"]["level_rank"] == lvl and int(r["decision_year"]) == 2020]
        assert np.mean(a) == pytest.approx(np.mean(b), abs=1e-9)
    hi = np.mean([r["v2"]["k"] for r in new if r["v2"]["level_rank"] == 4.0])
    lo = np.mean([r["v2"]["k"] for r in new if r["v2"]["level_rank"] == 2.0])
    assert hi - lo > 1.0
    # a structural zero of the group family stays zero
    assert all(r["v2"]["scr_g5_x"] == 0.0 for r, o in zip(new, rows) if o["v2"]["scr_g5_x"] == 0.0)
    assert rec["k"]["values"] == 400 and rec["k"]["unchanged"] == 0


def test_the_club_rule():
    rec = {"career_stats": [{"season": 2016, "level": "A", "org": "SEA", "games": 40},
                            {"season": 2016, "level": "A+", "org": "SEA", "games": 10},
                            {"season": 2017, "level": "AA", "org": "NYY", "games": 50},
                            {"season": 2018, "level": "MLB", "org": "NYY", "games": 5}],
           "dev_credit": {"signing_org": "BOS"}, "org": "TEX"}
    assert X.club_of(rec, 2016, "p") == "SEA"
    assert X.club_of(rec, 2017, "p") == "NYY"
    assert X.club_of(rec, 2015, "p") == "BOS"
    assert X.club_of(None, 2016, "p") == "solo:p"


def test_multiplicity_draws_keep_clusters_together():
    cl = np.asarray(["a", "a", "b", "c", "c", "c"])
    m = X.mult_draws(cl, 50, 4)
    assert m.shape == (50, 6)
    assert np.all(m[:, 0] == m[:, 1]) and np.all(m[:, 3] == m[:, 5])
    assert np.all(m.sum(axis=1) > 0)


def test_the_read_artifact():
    if not X.OUT_PATH.exists():
        pytest.skip("the read has not run in this tree")
    d = json.loads(X.OUT_PATH.read_text(encoding="utf-8"))
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["B"] == X.B and d["seed"] == X.SEED and d["margin"] == X.MARGIN
    par = d["parity"]
    assert par["stored_heads"]["hit"]["production_max_abs_diff"] <= 1e-9
    assert par["stored_heads"]["pit"]["production_max_abs_diff"] <= 1e-9
    assert par["stored_heads"]["fold_e_skill_max_abs_diff"] <= 1e-9
    assert par["procedure"]["max_abs_slope_diff"] <= 1e-8
    for s in ("hit", "pit"):
        assert d["live_board"][s]["parity"]["max_move"] in (0, 0.0)
        for nm, v in d["verdict"][s].items():
            if nm == "passing" or not v.get("read"):
                continue
            if v["passes"]:
                assert v["holm"]["rejects"] and v["lower_bounds_clear"]
                assert v["not_below_consensus"] and v["planted_recovers"]
        assert d["adopted"][s] in (None,) + X.ARMS
        if d["adopted"][s] is not None:
            assert d["verdict"][s][d["adopted"][s]]["passes"]
    for nm, f in d["fits"].items():
        for fid in f:
            frame, _side, year = fid.split("|")
            assert not (frame == "lv_dev" and int(year) in X.F.RESERVED_LV)
            assert not (frame == "vm_dev" and int(year) >= 2025)
    if not any(d["adopted"].values()):
        assert not X.WEIGHTS_PATH.exists()


def test_the_flag_is_off():
    assert X.EFV_WEIGHT_INTEGRITY_ON is False


def test_the_grids_are_registered():
    assert X.GRID_B2[-1] == math.inf and 1000.0 in X.GRID_B2 and max(
        v for v in X.GRID_B2 if math.isfinite(v)) == 100000.0
    assert X.GRID_D[-1] == math.inf and X.K_GRID == (1, 2, 3, 5, 8, None)
    assert X.ADOPT_ORDER == ("B1", "B3", "B2", "C", "D")


def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    assert "run_backtest" not in src
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
        assert ch not in Path(__file__).read_text(encoding="utf-8")
