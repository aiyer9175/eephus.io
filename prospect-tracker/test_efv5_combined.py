# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 COMBINED pins (EFV5_COMBINE_WEIGHT_SHIP, docs/efv-v2/EFV_V5_COMBINED.md).

1. The flag and the served hook (the hook sits ahead of every other eFV flag).
2. The candidate list is the document's: 77 columns, the tool cells are clean atlas
   candidates, the excluded MiLB-profile columns never enter, every name is in the document.
3. The sign rule on the atlas interval; the tool cells' declared signs.
4. The joint fit at lambda infinity is V2 bit for bit on every order; a sign bound zeroes a
   slope that wants the other sign; the bounded solver equals V2's ridge when nothing binds.
5. The tracking head applies on the 2025 cohort's 2024 season only.
6. The ship rule as the document fixes it.
7. Gate compliance: no FV-cell grouping, no dash characters.

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest

import efv5_combined as X
import efv5_group_drivers as G
import efv_v2_model as H
import efv_v3 as V3
import efv_v4 as V4
from test_efv_v3 import WEIGHTS, _orders, _rows

ROOT = Path(__file__).parent
SRC = ROOT / "efv5_combined.py"
DOC = ROOT / X.DOC
N_CANDIDATES = 77


def _attach_noise(rows, side, seed=5, *, strong: str | None = None, strong_sign: float = 1.0):
    """Every candidate key of the side on the rows' v2 view as noise; `strong` gets a
    column that follows the target with the given sign."""
    rng = np.random.default_rng(seed)
    out = []
    for r in rows:
        v2 = dict(r["v2"])
        for n in X.side_candidates(side):
            key = X.candidates()[n]["key"]
            if n == strong:
                v2[key] = strong_sign * float(r["target"]) + float(rng.normal(0, 0.3))
            else:
                v2[key] = float(rng.normal(0, 1))
        out.append(dict(r, v2=v2))
    return out


# ---------------------------------------------------------------------------
# 1. the flag and the hook
# ---------------------------------------------------------------------------

def test_the_flag_is_off_and_the_hook_is_first():
    assert X.EFV_V5_COMBINED_ON is False
    src = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    assert "if V5C.EFV_V5_COMBINED_ON:" in src
    assert src.index("if V5C.EFV_V5_COMBINED_ON:") < src.index("if V5.EFV_V5_ON:")


# ---------------------------------------------------------------------------
# 2. the candidate list
# ---------------------------------------------------------------------------

def test_the_candidate_list_is_the_documented_77():
    c = X.candidates()
    assert len(c) == N_CANDIDATES
    assert len(X.side_candidates("hit")) == 42 and len(X.side_candidates("pit")) == 35
    assert len(X.side_candidates("hit", "timing")) == 15
    assert len(X.side_candidates("pit", "timing")) == 8
    assert sum(1 for s in c.values() if s["source"] == "group") == len(G.menu_columns())
    assert sum(1 for s in c.values() if s["source"] == "tool") == len(X.TOOL_CELLS)
    assert sum(1 for s in c.values() if s["source"] == "v4") == len(V4.menu_columns())
    assert sum(1 for s in c.values() if s["source"] == "w2s") == len(X.W2S_COLUMNS)
    for n in X.EXCLUDED_W2:
        assert n not in c and n in V3.W2_COLUMNS
    assert all(s["key"] == f"{H.V2_SCREEN_PREFIX}{n}" for n, s in c.items())
    text = DOC.read_text(encoding="utf-8")
    for n in c:
        assert f"`{n}`" in text, n
    assert all(X.tool_cells_are_atlas_candidates().values())
    assert X.LAMBDAS == H.V2_ALPHAS
    assert "{1, 3, 10, 30, 100, 300, 1000, infinity}" in text


# ---------------------------------------------------------------------------
# 3. the signs
# ---------------------------------------------------------------------------

def test_group_sign_rule_on_a_synthetic_cells_file(tmp_path):
    cols = ["metric", "side", "level", "age_band", "group", "label", "frame", "raw_full_ci95"]
    menu = G.menu_columns()
    rows = []
    want = {}
    for i, (n, s) in enumerate(menu.items()):
        ci = [[0.6, 0.7], [0.3, 0.4], [0.45, 0.55]][i % 3]
        want[n] = [1, -1, 0][i % 3]
        rows.append([s["metric"], s["side"], s["level"], s["band"], s["group"],
                     s["atlas"]["label"], "clean", ci])
    p = tmp_path / "cells.json"
    p.write_text(json.dumps({"columns": cols, "rows": rows}), encoding="utf-8")
    assert X.group_signs(p) == want


def test_the_declared_signs():
    c = X.candidates()
    assert all(c[n]["sign"] == -1 for n in X.TOOL_CELLS if n.endswith("_sl_gap"))
    assert c["t5_pit_AAA_all_all_fb_fut"]["sign"] == 0
    assert c["g5_hit_A_all_all_k_pct"]["sign"] == -1
    assert c["g5_pit_A_all_all_k_minus_bb"]["sign"] == 1
    assert c["g5_pit_A_all_SP_bf_per_g"]["sign"] == 0
    assert all(c[n]["sign"] == 0 for n in V4.menu_columns())
    assert all(c[n]["sign"] == 0 for n in X.W2S_COLUMNS)


# ---------------------------------------------------------------------------
# 4. the joint fit
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def frame():
    train = _attach_noise(_rows(years=range(2011, 2017), n=150), "hit")
    test = _attach_noise(_rows(years=[2017], seed=99), "hit", seed=7)
    return train, test


def test_lambda_infinity_is_v2_bit_for_bit(frame):
    train, test = frame
    v2 = H.fit_v2(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False)
    inf = {"skill": math.inf, "timing": math.inf}
    m = X.fit_combined(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False, lam=inf)
    assert m["model_id"] == X.MODEL_ID and m["base_model_id"] == H.V2_ASSEMBLED_ID
    assert m["skill"]["v2_keys"] == v2["skill"]["keys"]
    assert m["skill"]["keys"] == v2["skill"]["keys"] and m["skill"]["beta"] == v2["skill"]["beta"]
    assert len(m["skill"]["zero_candidates"]) == len(X.side_candidates("hit", "skill"))
    assert len(m["timing"]["zero_candidates"]) == len(X.side_candidates("hit", "timing"))
    assert _orders(X.predict_combined(m, test)) == _orders(H.predict_v2(v2, test))
    assert (m["w_skill"], m["w_time"]) == (v2["w_skill"], v2["w_time"])


def test_pitchers_without_a_usable_head_take_the_consensus_order():
    train = _attach_noise(_rows(side="pit", years=range(2011, 2017), n=150), "pit")
    test = _attach_noise(_rows(side="pit", years=[2017], seed=99), "pit", seed=7)
    inf = {"skill": math.inf, "timing": math.inf}
    m = X.fit_combined(train, "pit", frame="lv", weights=WEIGHTS, absent_ok=False, lam=inf)
    v2 = H.fit_v2(train, "pit", frame="lv", weights=WEIGHTS, absent_ok=False)
    assert m["consensus_only"] == v2["consensus_only"]
    assert _orders(X.predict_combined(m, test)) == _orders(H.predict_v2(v2, test))


def test_a_sign_bound_zeroes_a_slope_that_wants_the_other_sign(monkeypatch):
    name = "g5_hit_A_all_all_k_pct"           # constrained to -
    train = _attach_noise(_rows(years=range(2011, 2017), n=150), "hit", strong=name,
                          strong_sign=+1.0)   # the column follows the target: wants +
    skill_names = X.side_candidates("hit", "skill")
    head = X.joint_skill(train, ("tool_hit",), 10.0, skill_names, 10.0)
    key = X.candidates()[name]["key"]
    assert head["beta"][head["keys"].index(key)] == 0.0
    # the same column with the bound lifted takes a positive slope
    c = X.candidates()
    monkeypatch.setitem(c[name], "sign", 0)
    head2 = X.joint_skill(train, ("tool_hit",), 10.0, skill_names, 10.0)
    assert head2["beta"][head2["keys"].index(key)] > 0.0
    monkeypatch.setitem(c[name], "sign", -1)
    # and a column the data points the constrained way keeps its slope
    train3 = _attach_noise(_rows(years=range(2011, 2017), n=150), "hit", strong=name,
                           strong_sign=-1.0)
    head3 = X.joint_skill(train3, ("tool_hit",), 10.0, skill_names, 10.0)
    assert head3["beta"][head3["keys"].index(key)] < 0.0


def test_bounded_solvers_equal_the_unbounded_fits_when_nothing_binds():
    rng = np.random.default_rng(3)
    Z = np.column_stack([np.ones(300), rng.normal(size=(300, 4))])
    y = Z[:, 1] - 0.5 * Z[:, 2] + rng.normal(size=300) * 0.3
    w = np.ones(300)
    pen = np.array([0.0, 0.0, 3.0, 3.0, 3.0])
    free = np.full(5, -np.inf), np.full(5, np.inf)
    assert np.allclose(X.bounded_wls(Z, y, w, pen, *free), H._wls(Z, y, w, pen), atol=1e-9)
    yb = (y > 0).astype(float)
    b = X.bounded_logistic(Z, yb, pen, *free)
    ref = H._logistic(Z, yb, np.zeros(300), pen)
    assert np.allclose(b, ref, atol=1e-5)


def test_the_nested_rule_can_choose_v2(frame):
    train, _test = frame
    lam = X.select_lambda(train, "skill", ("tool_hit",), 10.0, X.side_candidates("hit", "skill"))
    assert lam in X.LAMBDAS


def test_standard_errors_cover_every_slope(frame):
    train, _test = frame
    m = X.fit_combined(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False,
                       lam={"skill": 30.0, "timing": 30.0}, with_se=True)
    for h in ("skill", "timing"):
        head = m[h]
        assert head is not None and set(head["se"]) == set(head["keys"])
        tbl = X.weights_table(m)["heads"][h]
        assert len(tbl["drivers"]) == len(head["keys"])
        assert all(r["beta"] == 0.0 for r in tbl["drivers"] if r["zero"])
    inf = X.fit_combined(train, "hit", frame="lv", weights=WEIGHTS, absent_ok=False,
                         lam={"skill": math.inf, "timing": math.inf}, with_se=True)
    tbl = X.weights_table(inf)["heads"]["skill"]
    assert len(tbl["drivers"]) == len(inf["skill"]["keys"]) + len(X.side_candidates("hit", "skill"))
    assert set(tbl["zero_drivers"]) >= set(X.side_candidates("hit", "skill"))


# ---------------------------------------------------------------------------
# 5. the tracking head, 6. the ship rule
# ---------------------------------------------------------------------------

def test_the_head_applies_on_the_2025_cohort_only():
    assert X.blend_season("vm_pros", 2025) == 2024
    assert X.blend_season("vm_dev", 2023) is None
    assert X.blend_season("lv_dev", 2019) is None
    assert X.blend_season("lv_res", 2021) is None


def _doc(fids_deltas):
    return {"frames": {fid: {"n": n, "deltas": {"v5c_vs_efv_v2": {"spearman": {"delta": d}}},
                             "e_refit": {"legs": {"both": {"v5c_vs_prospx_consensus": {
                                 "spearman": {"delta": 0.0, "ci95": [-0.01, 0.01]}}}}}}
                       for fid, (n, d) in fids_deltas.items()}}


def test_the_ship_rule_as_the_document_fixes_it():
    fit = _doc({"lv_dev": (2862, 0.0033), "vm_dev": (830, 0.0)})
    spent = _doc({"lv_res": (2349, -0.0030), "vm_pros": (147, 0.0)})
    r = X.ship_reading(fit, spent)
    assert r["ships"] is True and r["pooled_delta_vs_v2"] > 0
    spent2 = _doc({"lv_res": (2349, -0.0051), "vm_pros": (147, 0.0)})
    r2 = X.ship_reading(fit, spent2)
    assert r2["ships"] is False and r2["rule_held_out_trail"] is False
    fit3 = _doc({"lv_dev": (2862, 0.0010), "vm_dev": (830, 0.0)})
    spent3 = _doc({"lv_res": (2349, -0.0030), "vm_pros": (147, 0.0)})
    r3 = X.ship_reading(fit3, spent3)
    assert r3["ships"] is False and r3["rule_pooled_above_zero"] is False
    assert r3["vs_consensus_spent"]["lv_res"]["beats_consensus_resolved"] is False


# ---------------------------------------------------------------------------
# 7. gate compliance
# ---------------------------------------------------------------------------

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
