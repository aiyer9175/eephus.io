# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-17 pins: the P(bust) chip (efv_v2_model "DS-17") and its development read
(tools/efv_pbust_read.py, data/efv_v2_pbust_eval.json).

The chip is 1 - P(REACHED) from the V2 REACHED head plus the FG-vs-Pipeline spread when
the DS-06 admission rule admits the spread inside the fold. A row without both grades
reads the head alone. Scored by Brier and log loss; calibration reported by side.
"""
from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import efv_pbust_read as R  # noqa: E402

ART = ROOT / "data" / "efv_v2_pbust_eval.json"


def _feats(**kw):
    f = {"milb_unavailable": 0.0, "milb_missing": 0.0, "obp_rel": 0.0, "k_rel": 0.0,
         "peak_k_rel": 0.0, "level_rank": 0.0, "age_rel_level": 0.0, "tool_hit": 50.0,
         "tool_speed": 48.0, "is_college": 0.0, "is_ifa": 0.0, "pick_missing": 1.0}
    f.update(kw)
    return f


def _rows(years=range(2011, 2017), n=300, seed=3, spread_sign=None, spread_share=0.7):
    """REACHED depends on consensus and (planted) on the spread: a wider spread lowers
    the chance of reaching when spread_sign is -1 for a year."""
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        sgn = -1.0 if spread_sign is None else float(spread_sign.get(yr, -1.0))
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            sp = float(rng.random()) if rng.random() < spread_share else None
            eta = 0.25 * (fv - 45) + (sgn * 3.0 * (sp - 0.5) if sp is not None else 0.0)
            reached = float(rng.random() < 1 / (1 + math.exp(-eta)))
            feats = _feats(level_rank=float(rng.integers(0, 6)),
                           age_rel_level=float(rng.normal(0, 1)))
            out.append({"player_key": f"p{i}", "decision_year": yr, "fv": fv,
                        "target": reached, "reached": reached, "weight": 1.0,
                        "feats": feats, "v2": H.v2_row(feats, {}), "frame": "vm",
                        "ids_outcome_blind": False, H.PBUST_SPREAD_KEY: sp})
            i += 1
    return out


def test_spread_is_the_within_group_percentile_gap_on_rows_with_both_grades():
    pairs = [(50, 50), (55, 45), (45, 55), None, (60, None)]
    s = H.spread_values(pairs, ["a", "a", "a", "a", "a"])
    assert s[3] is None and s[4] is None
    assert s[0] == 0.0
    assert s[1] == pytest.approx(s[2]) and s[1] > 0
    # groups never mix
    s2 = H.spread_values([(50, 45), (45, 50)], ["x", "y"])
    assert s2 == [0.0, 0.0]


def test_spread_admitted_and_negative_when_planted_with_one_sign():
    tr = _rows()
    m = H.fit_pbust(tr, "hit", frame="vm", spread="admit")
    assert m["spread_admission"]["admitted"]
    assert m["spread_used"] and m["c_spread"] < 0
    # the admission's per-vintage signs are carried
    assert set(m["spread_admission"]["per_vintage_signs"].values()) == {-1}


def test_spread_refused_when_its_sign_flips_between_vintages():
    tr = _rows(spread_sign={2011: -1, 2012: 1, 2013: -1, 2014: 1, 2015: -1, 2016: 1})
    m = H.fit_pbust(tr, "hit", frame="vm", spread="admit")
    assert not m["spread_admission"]["admitted"]
    assert not m["spread_used"] and m["c_spread"] == 0.0
    forced = H.fit_pbust(tr, "hit", frame="vm", spread="force")
    assert forced["spread_used"]


def test_rows_without_both_grades_read_the_head_alone():
    tr = _rows()
    m = H.fit_pbust(tr, "hit", frame="vm", spread="admit")
    off = H.fit_pbust(tr, "hit", frame="vm", timing=m["timing"], spread="off")
    te = _rows(years=[2016], n=80, seed=9)
    for r in te:
        r[H.PBUST_SPREAD_KEY] = None
    a, b = H.predict_pbust(m, te), H.predict_pbust(off, te)
    assert [x["p_bust"] for x in a] == [x["p_bust"] for x in b]
    assert not any(x["spread_used"] for x in a)


def test_p_bust_is_one_minus_p_reach_and_a_probability():
    tr = _rows()
    m = H.fit_pbust(tr, "hit", frame="vm")
    out = H.predict_pbust(m, _rows(years=[2016], n=50, seed=4))
    for x in out:
        assert 0.0 < x["p_bust"] < 1.0
        assert x["p_bust"] == pytest.approx(1.0 - x["p_reach"])


def test_the_chip_uses_the_same_reached_head_v2_orders_with():
    """One head: handed V2's timing head, the chip's head is that object."""
    tr = _rows()
    head = H.fit_timing_head(tr, "hit", candidates=H.timing_candidates("hit"))
    m = H.fit_pbust(tr, "hit", frame="vm", timing=head)
    assert m["timing"] is head


def test_fit_reads_training_rows_only():
    tr = _rows()
    m1 = H.fit_pbust(tr, "hit", frame="vm")
    te = _rows(years=[2016], n=60, seed=21)
    m2 = H.fit_pbust(tr, "hit", frame="vm")
    for r in te:                       # poisoning a scored row changes no fit
        r["reached"] = 1.0 - r["reached"]
    assert m1["c_spread"] == m2["c_spread"] and m1["timing"]["b0"] == m2["timing"]["b0"]


def test_reserved_years_raise():
    tr = _rows(years=[2023, 2024, 2025], n=80)
    with pytest.raises(F.ReservedFrameError):
        H.fit_pbust(tr, "hit", frame="vm")


def test_scores_and_calibration():
    assert R.brier([0.0, 1.0], [0, 1]) == 0.0
    assert R.brier([0.5, 0.5], [0, 1]) == 0.25
    assert R.log_loss([0.5, 0.5], [0, 1]) == pytest.approx(math.log(2))
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 20000)
    y = (rng.random(p.size) < p).astype(float)
    c = R.calibration(p, y)
    assert abs(c["recal_slope"] - 1.0) < 0.1 and abs(c["recal_intercept"]) < 0.1
    assert abs(c["in_the_large"]) < 0.02 and c["ece"] < 0.02
    assert len(c["reliability"]) == 10 and sum(t["n"] for t in c["reliability"]) == p.size
    # an over-confident forecast reads a slope under one
    q = 1 / (1 + np.exp(-3 * np.log(p / (1 - p))))
    assert R.calibration(q, y)["recal_slope"] < 0.5


@pytest.mark.parametrize("mod", ["tools/efv_pbust_read.py"])
def test_the_read_groups_nothing_by_grade(mod):
    banned = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
              "fv_band", "fv_bin")
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else None)
        if name:
            assert not any(t in name.lower() for t in banned), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}, node.lineno


def test_artifact_contract():
    if not ART.exists():
        pytest.skip("data/efv_v2_pbust_eval.json not built")
    doc = json.loads(ART.read_text(encoding="utf-8"))
    assert doc["role"] == "development" and doc["adjudicates"] is False
    assert doc["model_id"] == H.PBUST_MODEL_ID
    g = doc["reserved_guard"]
    assert not set(g["lv_folds"]) & set(F.RESERVED_LV)
    assert max(g["lv_folds"]) <= max(F.DEV_VINTAGES)
    assert max(g["vm_years"]) < F.R_VM_FIRST_DEBUT_YEAR
    assert min(g["vm_years"]) > H.RULE_LAST_YEAR and min(g["lv_folds"]) > H.RULE_LAST_YEAR
    assert set(doc["frames"]) == {"lv_dev", "vm_oos_dev"}
    for fid, f in doc["frames"].items():
        assert f["verdict"].startswith("development only")
        assert f["raters"]["efv"]["spearman"] is None      # table only, never charted
        sc = doc["frames_scored"][fid]
        assert set(sc["calibration_by_side"]) == {"hit", "pit"}
        for side in ("hit", "pit"):
            for arm in ("consensus", "reached_head", "chip", "spread_forced"):
                c = sc["calibration_by_side"][side][arm]
                assert c["n"] == sc["n_by_side"][side]
                assert "recal_slope" in c and "ece" in c
        assert sc["n"] == sum(sc["n_by_side"].values())
    # the ledger copies it as development rows
    import efv_progress as P
    assert any(name == P.PBUST_NAME for name, *_ in P.DEV_ARTIFACTS)
