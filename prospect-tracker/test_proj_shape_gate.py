# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins docs/PROJ_PATH_SHAPE_GATE.md section 14: the CRITERIA as well as the
verdicts, the frame partition, the power artifact's frame, the Holm mechanics, the
bootstrap provenance and the flag defaults, over the three artifacts the battery
wrote (data/proj_shape_blast.json, data/proj_shape_mde.json,
data/proj_shape_gate.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import proj_shape_gate as G  # noqa: E402

BLAST = ROOT / "data" / "proj_shape_blast.json"
MDE = ROOT / "data" / "proj_shape_mde.json"
GATE = ROOT / "data" / "proj_shape_gate.json"
DOC = ROOT / "docs" / "PROJ_PATH_SHAPE_GATE.md"


def _load(p: Path) -> dict:
    if not p.exists():
        pytest.skip("%s not written yet" % p.name)
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------ the registration
def test_thresholds_are_the_registered_ones():
    """Section 15: every numeric threshold is frozen."""
    assert (G.M, G.S1B, G.ASHAPE_RS2, G.ASHAPE_UAF) == (0.0065, 0.0130, 0.2617, 0.1192)
    assert (G.S3_BIAS, G.S4_DELTA, G.S4_BAND, G.S5_PINBALL, G.S6_STAR_MAE) == (
        0.0200, 0.0200, (0.75, 0.87), 0.0050, 0.0500)
    assert (G.A0_MAE_TOL, G.A0_BIAS_TOL, G.B3_POOLED, G.B4_DEEPEN) == (0.0050, 0.0100, 0.0100, 0.0500)
    assert (G.B2_RATIO, G.B2_FLOOR, G.TWIN_SHARE, G.CONFIRM_MIN_N) == (0.5, 0.01, 0.75, 1000)
    assert (G.VIF_REGISTERED, G.TRIPWIRE2_POINTS, G.HOLM_K) == (1.8, 10.0, 3)
    assert G.LAMBDA_GRID == (0.0, 0.05, 0.10, 0.20, 0.40, 0.80)
    assert (G.SEED_FIT, G.SEED_BOOT, G.B_TEST, G.B_FULL, G.PERM_DRAWS) == (
        20260611, 20260918, 1000, 200, 200)
    assert G.LEVERS == ("B-AGE", "B-C", "B-STAR")


def test_joint_hyperparameters_are_4_1a():
    import proj_ml
    want = {k: v for k, v in proj_ml.LGBM_PARAMS.items() if k != "objective"}
    assert G.JOINT_PARAMS == want
    assert want["n_estimators"] == 400 and want["num_leaves"] == 31


def test_frames_are_disjoint_and_match_4_6():
    sets = [set(G.DEV_LABELS), set(G.GATE_LABELS), set(G.CONFIRM_LABELS), set(G.TIER2_LABELS)]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert not (sets[i] & sets[j])
    assert G.DEV_LABELS == (2008, 2009, 2010, 2011)
    assert G.GATE_LABELS == (2012, 2013, 2014)
    assert G.CONFIRM_LABELS == (2026,)
    assert G.TIER2_LABELS == tuple(range(2015, 2026))


def test_penalty_hessian_is_exact_on_a_complete_group():
    """4.1 item 3: lam * [2, 10, 12, 10, 2] on a five-horizon group, pinball 1.0."""
    prv = np.array([-1, 0, 1, 2, 3])
    nxt = np.array([1, 2, 3, 4, -1])
    obj = G.make_objective(0.5, 1.0, prv, nxt)
    g, h = obj(np.zeros(5), np.zeros(5))
    assert list(h) == [3.0, 11.0, 13.0, 11.0, 3.0]
    # gradient of the penalty on a straight line is zero; on a kink it is not
    g2, _ = obj(np.zeros(5), np.array([0.0, 1.0, 2.0, 3.0, 4.0]))
    assert np.allclose(g2, np.where(np.array([0.0, 1, 2, 3, 4]) > 0, 0.5, -0.5))
    g3, _ = obj(np.zeros(5), np.array([0.0, 0.0, 1.0, 0.0, 0.0]))
    # a positive gradient lowers the score: the kink at h3 is pulled down, its
    # neighbours up (12 = 8 from its own triple + 2 + 2 as an endpoint, + 0.5 pinball)
    assert g3[2] == pytest.approx(12.5) and g3[1] == pytest.approx(-8.5)


def test_short_groups_carry_no_penalty_and_are_kept():
    prv = np.array([-1, 0, -1])
    nxt = np.array([1, -1, -1])
    obj = G.make_objective(0.5, 1.0, prv, nxt)
    _, h = obj(np.zeros(3), np.zeros(3))
    assert list(h) == [1.0, 1.0, 1.0]


def test_verdict_vocabulary_is_closed():
    assert G.VERDICTS == ("PASS", "NULL", "NULL_HOLM", "NULL_NO_ADMISSIBLE_LAMBDA",
                          "NO_EFFECT", "ABSORBED", "DEAD_ON_ARRIVAL", "UNDERPOWERED",
                          "UNDERPOWERED_NO_MARGIN", "NOT_ADJUDICATED_NO_HOLM",
                          "NOT_ADJUDICATED_NO_FLOOR", "NOT_AVAILABLE",
                          "PASS_BY_CONSTRUCTION", "VOID", "VOID_CLOSED")


def test_flags_default_off_and_model_version_unmoved():
    """8.2 and 8.3: nothing in this battery flips a flag; the OFF payload is the
    pre-change payload because neither flag exists in proj_ml until a flip commit."""
    import proj_ml
    assert getattr(proj_ml, "SERVE_SHAPE_REFIT", False) is False
    assert not getattr(proj_ml, "SERVE_BIAS_LEVERS", frozenset())
    assert proj_ml.MODEL_VERSION == "proj_lgbm_v1"


def test_rs2_uaf_on_a_hand_path():
    r = G.rs2_uaf([[1.0, 2.0, 1.0, 2.0, 1.0]])
    assert r["pool"] == 1 and r["uaf_steps"] == 4
    assert r["uaf_up"] == 1 and r["raf"] == 1          # 1->2 up, 2->1 fall, 1->2 up after fall
    assert abs(r["rs2_mean"] - 2.0) < 1e-9             # second differences -2, 2, -2


# ------------------------------------------------------------ the blast artifact
def test_blast_artifact_fits_nothing_and_reprices_exactly():
    b = _load(BLAST)
    assert b["fits_anything"] is False
    rep = b["repricer"]["identity_reproduces_served_surNpv"]
    assert rep["within_1_usd"] == rep["n"] == b["n_pool"]
    ident = b["results"]["identity"]
    assert ident["surNpv_abs_move_usd"]["max"] == 0
    assert ident["spearman_surTotal_pre_post"] == 1.0
    worst = min(b["results"][k]["spearman_surTotal_pre_post"] for k in ("maxsmooth", "ramp"))
    demoted = b["reordering_criterion"].startswith("DEMOTED")
    assert demoted == (worst >= 0.9990)
    assert "OWNER-WAIVED EARLY READ" in b["read"]
    assert any("SHAPE-ONLY" in s for s in b["reading"])


def test_doc_records_the_reads_below_section_23():
    t = DOC.read_text(encoding="utf-8")
    i23 = t.index("## 23. AMENDMENT A-2")
    i24 = t.index("## 24. RESULTS, 2026-10-14")
    assert i24 > i23
    assert t.count("OWNER-WAIVED EARLY READ") >= 2
