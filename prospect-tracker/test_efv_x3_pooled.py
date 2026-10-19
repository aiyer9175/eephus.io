# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV X3 pooled model (EFV_X3_POOLED_MODEL, docs/efv-v2/EFV_X3_POOLED_MODEL.md).

Fixtures only; nothing real is scored here.
1. The switch is dark and the registered constants hold (features, grid, seeds, pass rule).
2. The fits: weighted ridge, the penalized Newton logistic, the anchor-only start of the
   boosted class, the hierarchical design's penalties.
3. The staged recombination and the inverse Mills ratio.
4. Every planted check of section 6 passes on its synthetic data.
5. The conformal quantile, the predictive distribution and its PIT.
6. The guards (reserved frames) and the verdict rule.
7. Gate compliance: no FV-cell grouping, no reserved vintage outside the guards, no dashes.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

import efv_vintage_frame as F
import efv_x3_pooled as X

ROOT = Path(__file__).parent
SRC = ROOT / "efv_x3_pooled.py"


# ---------------------------------------------------------------------------
# 1. the switch and the registered constants
# ---------------------------------------------------------------------------

def test_the_model_is_dark():
    assert X.EFV_X3_ON is False


def test_registered_constants():
    assert X.B == 4000 and X.SEED == 20261020
    assert X.NULL_SEEDS == tuple(range(20261021, 20261041)) and len(X.NULL_SEEDS) == 20
    assert X.PLANT_SEED == 20261041 and X.PLANT_RHO == 0.20
    assert X.LAM_GRID == (1.0, 3.0, 10.0, 30.0, 100.0) and X.KAPPA == 4.0
    assert X.TREES == (50, 100, 200)
    assert X.MAX_TRAIL == 0.005 and X.COVER_MIN == 0.20
    assert X.CONF_NOMINAL == 0.80 and X.CONF_BAND == (0.75, 0.85)
    assert X.W_CLIP == 10.0 and X.ESS_MIN == 0.30
    p = X.GBM_PARAMS
    assert (p["num_leaves"], p["learning_rate"], p["min_data_in_leaf"]) == (7, 0.05, 40)
    assert (p["feature_fraction"], p["bagging_fraction"], p["bagging_freq"], p["lambda_l2"]) == (0.8, 0.8, 1, 1.0)
    assert p["num_threads"] == 2 and p["seed"] == 20261020 and p["deterministic"] is True


def test_feature_lists_are_the_registered_ones():
    assert len(X.FEATURES["hit"]) == 24 and len(X.FEATURES["pit"]) == 25
    # eHIT and eFB on the reduced sets (amendment 1 A2), the stat lines not counted twice
    assert X.ETOOL_SUBDRIVERS["hit"] == ("k_rw", "babip_rw")
    assert X.ETOOL_SUBDRIVERS["fb"] == ("k_rw", "pbf_raw")
    for f in ("x1_k_rw", "x1_bb_rw", "x1_iso_rw", "x1_babip_rw", "x1_kbb_rw"):
        assert f not in X.FEATURES["hit"] and f not in X.FEATURES["pit"]
    # the pitch rates as penalized candidates (EW3-41)
    assert {"ppa_raw", "ppa_par"} <= set(X.FEATURES["hit"])
    assert {"pbf_raw", "pbf_par", "pip_raw", "pip_par"} <= set(X.FEATURES["pit"])
    # eRAW and eSPD only in the sensitivity
    assert "e_raw" not in X.FEATURES["hit"] and "e_spd" not in X.FEATURES["hit"]
    sens = X.features_of("hit", sensitivity=True)
    assert "e_raw" in sens and "e_spd" in sens and "c_raw_pwr" not in sens
    assert set(X.SHARED) == {"x1_age_rel_level", "level_rank", "age", "pick_overall", "is_college",
                             "x2_options", "x2_trades", "x2_r5_selected", "lam", "fv_stddev"}


def test_monotone_directions():
    assert "age" in X.MONO_DOWN and "x1_age_rel_level" in X.MONO_DOWN
    for f in ("e_hit", "e_pow", "e_fb", "e_cmd", "c_speed", "c_field", "c_best_sec"):
        assert f in X.MONO_UP
    assert "arsenal_depth" not in X.MONO_UP and "level_rank" not in X.MONO_UP


# ---------------------------------------------------------------------------
# 2. the fits
# ---------------------------------------------------------------------------

def test_wls_recovers_a_line_and_shrinks_penalized_columns():
    rng = np.random.default_rng(1)
    n = 2000
    x = rng.standard_normal(n)
    y = 1.0 + 2.0 * x + 0.1 * rng.standard_normal(n)
    X_ = np.column_stack([np.ones(n), x])
    b = X.wls(X_, y, np.ones(n), np.zeros(2))
    assert abs(b[0] - 1.0) < 0.02 and abs(b[1] - 2.0) < 0.02
    b2 = X.wls(X_, y, np.ones(n), np.array([0.0, 1e7]))
    assert abs(b2[1]) < 0.01


def test_newton_logistic_matches_the_truth_and_is_weighted():
    rng = np.random.default_rng(2)
    n = 20000
    x = rng.standard_normal(n)
    y = (rng.random(n) < X.sigmoid(-0.5 + 1.2 * x)).astype(float)
    X_ = np.column_stack([np.ones(n), x])
    b = X.logistic(X_, y, np.ones(n), np.zeros(2))
    assert abs(b[0] + 0.5) < 0.06 and abs(b[1] - 1.2) < 0.06
    w = np.where(x > 0, 2.0, 1.0)
    bw = X.logistic(np.column_stack([np.ones(n), x]), y, w, np.zeros(2))
    assert abs(bw[1] - 1.2) < 0.08


class _T:
    """A minimal instance table for the design builders."""

    def __init__(self, n=400, seed=3):
        rng = np.random.default_rng(seed)
        self.n = n
        self.side = np.asarray([0] * (n // 2) + [1] * (n - n // 2))
        self.u_c = rng.random(n)
        self.grp = np.asarray(["hit:SS" if i % 2 else "hit:C" for i in range(n // 2)]
                              + ["pit:STARTER" if i % 2 else "pit:RELIEF" for i in range(n - n // 2)],
                              dtype=object)


def _fx(T, seed=4):
    rng = np.random.default_rng(seed)
    Zf = {"age": rng.standard_normal(T.n), "e_hit": np.where(T.side == 0, rng.standard_normal(T.n), np.nan),
          "e_fb": np.where(T.side == 1, rng.standard_normal(T.n), np.nan)}
    Zf["age"][:10] = np.nan
    kept = {"hit": ["e_hit", "age"], "pit": ["e_fb", "age"]}
    lam = rng.random(T.n)
    return X.FoldX(T, Zf, kept, lam, {"hit": float(lam[T.side == 0].mean()),
                                      "pit": float(lam[T.side == 1].mean())})


def test_hierarchical_design_penalties():
    T = _T()
    fx = _fx(T)
    rows = np.arange(T.n)
    Xa, mult, names = fx.design_a(rows)
    assert Xa.shape == (T.n, len(names)) == (T.n, mult.size)
    pen = dict(zip(names, mult))
    # anchors unpenalized
    for s in X.SIDES:
        assert pen[f"{s}:intercept"] == 0 and pen[f"{s}:u_c"] == 0 and pen[f"{s}:u_c_x_lam"] == 0
    # a shared feature: global slope lam, side and group deviations KAPPA * lam
    assert pen["age"] == 1.0 and pen["age|hit"] == X.KAPPA and pen["age|pit:STARTER"] == X.KAPPA
    # a side-only feature: side slope lam, group deviations KAPPA * lam; missing indicators lam
    assert pen["e_hit|hit"] == 1.0 and pen["e_hit|hit:SS"] == X.KAPPA
    assert pen["age|hit|missing"] == 1.0
    assert "e_hit|pit" not in pen
    Xk, _m, nk = fx.design_a(rows, k=np.zeros(T.n, dtype=int))
    assert "hit:k0" in nk and "hit:intercept" not in nk
    Xo, mo, no = fx.design_a(rows, anchor_only=True)
    assert all(m == 0 for m in mo) and len(no) == 6


def test_boosted_class_starts_from_the_anchor():
    T = _T(n=600)
    fx = _fx(T)
    rng = np.random.default_rng(5)
    rows = np.arange(T.n)
    y = 2.0 * T.u_c + 0.1 * rng.standard_normal(T.n)
    anc = X.fit_anchor(fx, rows, y, np.ones(T.n), "reg")
    g = X.fit_gbm(fx, rows, y, np.ones(T.n), "reg", trees=50)
    # the boosted raw prediction is the anchor's plus the trees'
    Xb, _n, _m, _c = fx.design_b(rows)
    trees = g.booster.predict(Xb, raw_score=True)
    assert np.allclose(g.predict(rows), anc.raw(rows) + trees)
    # the anchor alone already carries the consensus slope; the trees add little here
    assert np.corrcoef(anc.raw(rows), y)[0, 1] > 0.97
    assert np.abs(trees).mean() < 0.1


# ---------------------------------------------------------------------------
# 3. the recombination and the control function
# ---------------------------------------------------------------------------

class _Fit:
    def __init__(self, f):
        self.f = f

    def predict(self, rows, *, k=None, extra=None):
        return self.f(rows, k)


def test_recombination_is_p_times_the_sum_of_clipped_pt_times_rate():
    st = X.Staged("ridge", 1.0)
    st.R = _Fit(lambda r, k: np.full(r.size, 0.5))
    st.T_ = _Fit(lambda r, k: np.where(k == 0, -1.0, 0.5))
    st.Q = _Fit(lambda r, k: np.full(r.size, 2.0))
    sc = st.score(np.arange(3))
    # k = 0 clipped to 0; k = 1..5: 0.5 * 2.0 each
    assert np.allclose(sc["cond"], 5.0) and np.allclose(sc["e"], 2.5) and np.allclose(sc["p"], 0.5)


def test_inverse_mills_ratio():
    from scipy.stats import norm
    p = np.array([0.1, 0.5, 0.9])
    assert np.allclose(X.imr(p), norm.pdf(norm.ppf(p)) / p)
    assert X.imr(np.array([0.5]))[0] == pytest.approx(0.7979, abs=1e-4)


def test_player_weights_sum_to_one_per_player():
    class T:
        pk = np.asarray(["a", "a", "b", "c", "c", "c"], dtype=object)
    w = X.player_weights(T, np.arange(6))
    assert np.allclose(w, [0.5, 0.5, 1.0, 1 / 3, 1 / 3, 1 / 3])


# ---------------------------------------------------------------------------
# 4. the planted checks of section 6
# ---------------------------------------------------------------------------

def test_planted_censoring():
    assert X.synth_censoring()["pass"]


def test_planted_survivorship():
    r = X.synth_heckman(reps=30)
    assert r["two_step_closer"] >= 27


def test_planted_consensus_reliability():
    assert X.synth_eiv()["pass"]


def test_planted_covariate_shift():
    assert X.synth_shift()["pass"]


def test_planted_role_path():
    assert X.synth_role()["pass"]


def test_planted_conformal():
    assert X.synth_conformal()["pass"]


# ---------------------------------------------------------------------------
# 5. conformal and the predictive distribution
# ---------------------------------------------------------------------------

def test_conformal_quantile():
    res = np.arange(1, 11, dtype=float)       # m 10: ceil(0.8 * 11) = 9
    assert X.conformal_q(res) == 9.0
    assert X.conformal_q([]) is None
    assert X.conformal_q(np.arange(1, 4, dtype=float)) == 3.0


def test_predictive_cdf_and_pit():
    grid = (-1.0, 0.0, 1.0, 2.0, 5.0)
    F_ = X.predictive_cdf(0.4, 1.0, np.array([-0.5, 0.5]), grid)
    # mass 0.6 at 0; given reach 0.5 and 1.5
    assert np.allclose(F_, [0.0, 0.6, 0.8, 1.0, 1.0])
    rng = np.random.default_rng(0)
    u = [X.pit_value(0.4, 1.0, np.array([-0.5, 0.5]), 0.0, rng) for _ in range(200)]
    assert min(u) >= 0.0 and max(u) <= 0.6


def test_eiv_lambda_falls_with_disagreement():
    class T:
        n = 6
        side = np.zeros(6, dtype=int)
        n_src = np.array([1.0, 2.0, 3.0, 3.0, 4.0, 4.0])
        sd_src = np.array([0.0, 1.0, 1.0, 5.0, 2.0, 2.0])
        fv = np.array([40.0, 45.0, 50.0, 55.0, 60.0, 45.0])
    lam, rec = X.eiv_lambda(T, np.arange(6))
    assert np.all((lam > 0) & (lam <= 1))
    assert lam[2] > lam[3]                    # same n, more disagreement
    assert rec["hit"]["tau2"] > 0


# ---------------------------------------------------------------------------
# 6. guards and the verdict
# ---------------------------------------------------------------------------

def test_guards_refuse_reserved_rows():
    for V in sorted(F.RESERVED_LV):
        with pytest.raises(F.ReservedFrameError):
            X.guard_instance("LV", V)
    with pytest.raises(F.ReservedFrameError):
        X.guard_instance("PIN", F.R_VM_FIRST_DEBUT_YEAR)
    with pytest.raises(F.ReservedFrameError):
        X.guard_instance("MTX", F.R_VM_FIRST_DEBUT_YEAR + 1)
    X.guard_instance("LV", 2019)
    X.guard_instance("PIN", F.R_VM_FIRST_DEBUT_YEAR - 2)
    X.guard_instance("LIVE", 2027)


def _leg(lp, lc, ub, d):
    return {"delta": d, "player": {"lb95": lp, "ub95": ub, "ci95": [lp, ub]}, "club": {"lb95": lc}}


def test_verdict_rule():
    ok = {"recovered": True}
    v = X.verdict(_leg(0.01, 0.005, 0.05, 0.03), -0.004, 0.02, ok)
    assert v["pass"] and v["word"] == "beats"
    assert not X.verdict(_leg(0.01, -0.001, 0.05, 0.03), 0.0, 0.02, ok)["pass"]     # club bound
    assert not X.verdict(_leg(0.01, 0.005, 0.05, 0.03), -0.006, 0.02, ok)["pass"]    # trails served
    assert not X.verdict(_leg(0.01, 0.005, 0.05, 0.03), 0.0, 0.04, ok)["pass"]       # under the null
    v = X.verdict(_leg(0.01, 0.005, 0.05, 0.03), 0.0, 0.02, {"recovered": False})
    assert not v["pass"] and v["unresolved"]
    v = X.verdict(_leg(-0.05, -0.05, -0.01, -0.03), 0.0, 0.02, ok)
    assert v["word"] == "trails"
    assert X.verdict(_leg(-0.02, -0.02, 0.01, -0.005), 0.0, 0.02, ok)["word"] == "ties"


def test_plant_feature_correlates_with_its_label():
    class T:
        n = 4000
        zgroup = np.asarray(["hit|LV|2015"] * 2000 + ["pit|LV|2015"] * 2000, dtype=object)

        def plant_label(self):
            return np.random.default_rng(9).standard_normal(4000)
    t = T()
    p = X.plant_feature(t)
    r = np.corrcoef(p, t.plant_label())[0, 1]
    assert 0.15 < r < 0.25


def test_the_pick_rule_breaks_ties_as_registered():
    s = {c: 0.1 for c in X.CONFIGS}
    assert X.pick(s) == ("ridge", 100.0)
    s = {("gbm", 50.0): 0.2, ("gbm", 100.0): 0.2, ("ridge", 1.0): 0.1}
    assert X.pick(s) == ("gbm", 50.0)
    assert X.pick_class({("ridge", 3.0): 0.3, ("ridge", 10.0): 0.2, ("gbm", 50.0): 0.9}, "ridge") == ("ridge", 3.0)


# ---------------------------------------------------------------------------
# 7. gate compliance
# ---------------------------------------------------------------------------

def test_no_fv_cell_grouping_in_the_source():
    src = SRC.read_text(encoding="utf-8")
    for pat in (r"fv_cell", r"FV_CELL", r"fv_band", r"by_fv", r"fv_bucket", r"\b45\s*/\s*50\b",
                r"cell\s*=\s*\(?\s*45", r"consensus_level"):
        assert not re.search(pat, src), pat
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            seg = ast.get_source_segment(src, node) or ""
            if re.search(r"\bfv\b", seg) and re.search(r"\b(45|50|55|60|65)\b", seg):
                raise AssertionError(f"a comparison of fv against a grade cell: {seg}")


def test_reserved_vintages_appear_only_through_the_guards():
    """A literal 2020 or 2021 names a season (the panel skip) or the guards' documentation,
    never a list vintage the code reads."""
    src = SRC.read_text(encoding="utf-8")
    for m in re.finditer(r"(?<!\d)(2020|2021)(?!\d)", src):
        line = src[src.rfind("\n", 0, m.start()) + 1: src.find("\n", m.start())]
        assert ("season" in line or "PANEL_SKIP" in line or "vintage" in line), line
    assert "RESERVED_LV" in src and "R_VM_FIRST_DEBUT_YEAR" in src


def test_no_dashes_or_marketing_words():
    for p in (SRC, Path(__file__)):
        t = p.read_text(encoding="utf-8")
        assert chr(0x2014) not in t and chr(0x2013) not in t
    words = ("leverage", "seamless", "robust", "delve", "comprehensive", "crucial", "essential",
             "powerful", "showcase", "utilize", "unlock", "elevate", "cutting-edge", "meticulous")
    low = SRC.read_text(encoding="utf-8").lower()
    for w in words:
        assert w not in low, w
