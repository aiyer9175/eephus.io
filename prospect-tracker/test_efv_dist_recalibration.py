# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE B-L5. Tests for the IDR / EasyUQ recalibration lab.

These pin the STRUCTURAL claims the lane is built on, not its numbers:

  1. ordinality is structural (four PAVA fits on pointwise-ordered responses cannot cross),
  2. the CORP decomposition is an identity, not an approximation,
  3. a zero-information constant scores UNC exactly and gets skill EXACTLY 0, which is the
     property that makes this gate immune to the failure mode where a constant reached
     152.68 percent of the candidate gain under ECE,
  4. the recalibration cannot feed back into rank_war,
  5. the lab's scratch directory is not a dead per-session path.

Nothing here builds the OOF frame, runs the gate, or writes any file. Fast and offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

L = pytest.importorskip("efv_dist_recalibration_lab")
pytest.importorskip("sklearn.isotonic")


def _synth(n=400, seed=0):
    """Ordered outcomes whose bucket probability rises with the score."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(20.0, 70.0, n)
    lin = (x - 45.0) / 8.0
    p = 1.0 / (1.0 + np.exp(-(lin[:, None] - np.array([1.0, 2.0, 3.0, 4.5]))))
    u = rng.uniform(size=n)[:, None]
    y = (u < p).sum(axis=1)
    return x, y.astype(int)


# ---------------------------------------------------------------------------
# 1. ordinality is STRUCTURAL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2, 3, 7, 11])
def test_idr_fits_cannot_cross(seed):
    """The four responses 1{y >= k} are pointwise ordered and PAVA is monotone in its
    response, so the fitted survivor curves cannot cross. No projection, no clipping,
    no renormalization: the raw fits themselves."""
    x, y = _synth(seed=seed)
    fit = L.fit_idr(x, y)
    grid = np.linspace(x.min(), x.max(), 257)
    S = np.column_stack([fit["iso"][j].predict(grid) for j in range(4)])
    assert float(np.max(np.diff(S, axis=1))) <= 0.0


def test_ordinality_claim_flag_is_asserted_not_assumed():
    assert L.IDR_ORDINALITY_STRUCTURAL is True
    assert L.IDR_THRESHOLDS == (1, 2, 3, 4)


def test_each_fit_is_monotone_in_the_score():
    x, y = _synth(seed=5)
    fit = L.fit_idr(x, y)
    grid = np.linspace(x.min(), x.max(), 129)
    for j in range(4):
        v = fit["iso"][j].predict(grid)
        assert float(np.min(np.diff(v))) >= -1e-12


# ---------------------------------------------------------------------------
# 2. the survivor -> simplex map
# ---------------------------------------------------------------------------
def test_q_from_surv_is_a_valid_ordered_simplex():
    x, y = _synth(seed=3)
    fit = L.fit_idr(x, y)
    S = np.column_stack([fit["iso"][j].predict(x) for j in range(4)])
    Q = L._q_from_surv(S)
    assert np.allclose(Q.sum(axis=1), 1.0, atol=1e-12)
    assert float(Q.min()) > 0.0
    assert float(np.max(np.diff(L._surv(Q), axis=1))) <= 1e-9


def test_rps_matches_a_hand_computation():
    # one row, S = (0.8, 0.5, 0.2, 0.05), y = 2 -> indicators (1, 1, 0, 0)
    Q = L._q_from_surv(np.array([[0.8, 0.5, 0.2, 0.05]]))
    got = L.rps(Q, np.array([2]))
    want = (0.8 - 1) ** 2 + (0.5 - 1) ** 2 + (0.2 - 0) ** 2 + (0.05 - 0) ** 2
    assert got == pytest.approx(want, abs=2e-5)


# ---------------------------------------------------------------------------
# 3. CORP is an identity, and a constant is structurally skill-free
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [0, 4, 9])
def test_corp_identity_holds_exactly(seed):
    x, y = _synth(seed=seed)
    fit = L.fit_idr(x, y)
    Q = L._q_from_surv(np.column_stack([fit["iso"][j].predict(x) for j in range(4)]))
    c = L.corp(Q, y)["total"]
    assert c["identity_residual"] == pytest.approx(0.0, abs=1e-9)
    assert c["mean_rps"] == pytest.approx(c["MCB"] - c["DSC"] + c["UNC"], abs=1e-6)
    assert c["mean_rps"] == pytest.approx(L.rps(Q, y), abs=1e-6)


def test_zero_information_constant_gets_exactly_zero_skill():
    """THE structural fix. A constant forecast set to the evaluation marginal has
    DSC = 0 and MCB = 0 and scores UNC exactly, so its skill score is exactly 0. Under the
    ECE regime this lane replaces, a constant reached 152.68 percent of the candidate's
    gain; under RPS + CORP it cannot reach any of it."""
    _x, y = _synth(n=600, seed=8)
    marg = np.array([float((y >= k).mean()) for k in L.IDR_THRESHOLDS])
    Q = L._q_from_surv(np.tile(marg, (len(y), 1)))
    c = L.corp(Q, y)["total"]
    assert c["DSC"] == pytest.approx(0.0, abs=1e-5)
    assert c["MCB"] == pytest.approx(0.0, abs=1e-5)
    assert c["mean_rps"] == pytest.approx(c["UNC"], abs=1e-5)
    assert c["skill_score"] == pytest.approx(0.0, abs=1e-4)


def test_any_constant_has_zero_discrimination_even_when_miscalibrated():
    """A constant that is NOT the marginal still has DSC = 0; it just carries MCB > 0 and
    therefore NEGATIVE skill. There is no constant with positive skill."""
    _x, y = _synth(n=600, seed=12)
    Q = L._q_from_surv(np.tile(np.array([0.5, 0.3, 0.15, 0.05]), (len(y), 1)))
    c = L.corp(Q, y)["total"]
    assert c["DSC"] == pytest.approx(0.0, abs=1e-5)
    assert c["MCB"] > 0.0
    assert c["skill_score"] < 0.0


# ---------------------------------------------------------------------------
# 4. out-of-fold discipline and the H2 extension
# ---------------------------------------------------------------------------
def _frame(n_per=200):
    rng = np.random.default_rng(21)
    rows = []
    for side in ("hit", "pit"):
        for yr in (2019, 2020, 2021, 2022):
            for _ in range(n_per):
                rows.append({"side": side, "decision_year": yr, "provisional": False,
                             "odds_grade": float(rng.uniform(20, 70)),
                             "fv": float(rng.uniform(35, 60)),
                             "y": int(rng.integers(0, 5)),
                             "p_ship": [0.6, 0.2, 0.1, 0.07, 0.03],
                             "target": float(rng.uniform(0, 20))})
    return rows


def test_folds_are_forward_chained_and_disjoint():
    fr = _frame()
    folds = L.idr_folds(fr)
    assert folds, "expected at least one evaluable fold"
    for side, t, tr, te in folds:
        assert not (set(tr.tolist()) & set(te.tolist()))
        assert all(fr[i]["decision_year"] < t for i in tr)
        assert all(fr[i]["decision_year"] == t for i in te)
        assert all(fr[i]["side"] == side for i in list(tr) + list(te))
        assert len(tr) >= L.IDR_MIN_TRAIN


def test_provisional_rows_never_enter_a_fold():
    fr = _frame()
    for r in fr[::7]:
        r["provisional"] = True
    for _side, _t, tr, te in L.idr_folds(fr):
        assert not any(fr[i]["provisional"] for i in list(tr) + list(te))


def test_extension_is_continuous_at_the_training_maximum(monkeypatch):
    """H2. The log-odds shift is anchored at x_max, so the extended curve agrees with the
    raw PAVA clip in the limit and is monotone above it."""
    x, y = _synth(seed=6)
    fit = L.fit_idr(x, y)

    def fake_inc(_side, xs):
        xs = np.asarray(xs, dtype=float)
        lin = (xs - 45.0) / 8.0
        return 1.0 / (1.0 + np.exp(-(lin[:, None] - np.array([1.0, 2.0, 3.0, 4.5]))))

    monkeypatch.setattr(L, "_incumbent_surv", fake_inc)
    xm = fit["xmax"]
    probe = np.array([xm + 1e-9, xm + 1.0, xm + 5.0, xm + 12.0])
    S, diag = L.predict_idr(fit, probe, "hit")
    assert diag["n_above_train_max"] == 4
    base = np.column_stack([fit["iso"][j].predict([xm])[0] for j in range(4)])
    assert np.allclose(S[0], base[0], atol=1e-6)
    assert float(np.min(np.diff(S, axis=0))) >= -1e-9      # monotone in x
    assert float(np.max(np.diff(S, axis=1))) <= 1e-9       # still ordinal


def test_predict_reports_the_raw_ordinality_check_separately():
    x, y = _synth(seed=2)
    fit = L.fit_idr(x, y)
    _S, diag = L.predict_idr(fit, x, "hit")
    assert diag["n_above_train_max"] == 0
    assert diag["raw_max_survivor_increase"] <= 0.0


# ---------------------------------------------------------------------------
# 5. multiplicity and the thin-cell interval
# ---------------------------------------------------------------------------
def test_holm_is_step_down_and_monotone():
    out = L.holm({"a": 0.01, "b": 0.02, "c": 0.04})
    assert out["a"]["p_holm"] == pytest.approx(0.03)
    assert out["b"]["p_holm"] == pytest.approx(0.04)
    assert out["c"]["p_holm"] == pytest.approx(0.04)
    assert out["a"]["p_holm"] <= out["b"]["p_holm"] <= out["c"]["p_holm"]


def test_holm_caps_at_one_and_is_never_looser_than_raw():
    raw = {"a": 0.4, "b": 0.6, "c": 0.9}
    out = L.holm(raw)
    for k, v in out.items():
        assert v["p_holm"] <= 1.0
        assert v["p_holm"] >= raw[k] - 1e-12
        assert not v["reject_at_0.05"]


@pytest.mark.parametrize("seed", [0, 5])
def test_venn_abers_interval_is_ordered(seed):
    rng = np.random.default_rng(seed)
    x_tr = rng.uniform(20, 70, 300)
    z_tr = (rng.uniform(size=300) < (x_tr - 20) / 60.0).astype(float)
    p0, p1 = L.venn_abers(x_tr, z_tr, np.array([25.0, 45.0, 65.0]))
    assert np.all(p0 <= p1 + 1e-12)
    assert np.all((p0 >= 0.0) & (p1 <= 1.0))


def test_venn_abers_widens_when_the_cell_is_thin():
    """The whole point of H3: the interval is an honest width, so a thin training set must
    produce a wider one than a thick one at the same test point."""
    rng = np.random.default_rng(4)
    x = rng.uniform(20, 70, 2000)
    z = (rng.uniform(size=2000) < (x - 20) / 60.0).astype(float)
    thin0, thin1 = L.venn_abers(x[:40], z[:40], np.array([45.0]))
    thick0, thick1 = L.venn_abers(x, z, np.array([45.0]))
    assert (thin1[0] - thin0[0]) > (thick1[0] - thick0[0])


# ---------------------------------------------------------------------------
# 6. the binding design constraint: no feedback into rank_war
# ---------------------------------------------------------------------------
def test_odds_seam_cannot_reach_rank_war():
    """PAVA blocks are ties and ties destroy rank. The recalibration is only safe because
    it lives strictly downstream of rank_war. This is the executable proof, both
    directions of the assignment graph, on the real efv_score.py."""
    a = L.rank_feedback_audit()
    assert a["n_functions"] >= 3, "expected the three efv_score scoring seams"
    assert a["seam_cannot_reach_rank"] is True
    for f in a["functions_examined"]:
        assert f["seam_name_in_rank_dependency_closure"] is False
        assert f["rank_assigned_before_seam"] is True
        assert f["downstream_of_seam_intersects_rank_or_grade"] == []


# ---------------------------------------------------------------------------
# 7. the scratch path regression
# ---------------------------------------------------------------------------
def test_scratch_is_not_a_dead_per_session_directory():
    """It used to be a hard-coded agent scratchpad that died with its session."""
    s = str(L.SCRATCH).replace("\\", "/").lower()
    assert "/claude/" not in s and "scratchpad" not in s
    assert not s.startswith(str(ROOT).replace("\\", "/").lower())


def test_lab_writes_only_the_registered_artifact():
    assert L.OUT.name == "xfv_dist_recalibration_eval.json"
    assert L.OUT.parent.name == "data"
