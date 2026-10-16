# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV pitcher slope sign stability pins (EFV_PIT_SIGN_STABILITY,
docs/efv-v2/EFV_PIT_SIGN_STABILITY.md).

1. The keys: the registered prior table is exactly the served head's free-signed pitcher
   columns; an arm's edit is undone after its block.
2. The machinery: the sign test recovers a planted slope; the arms and the combined arm
   follow the registration.
3. The read, when it has run: development only, the checks held, nothing passed, nothing is
   prepared and the flag is off.
4. Gate compliance: no FV-cell grouping, no dash characters.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

import efv5_combined as V5C
import efv5_pit_sign as X
import efv5_refit as RF

ROOT = Path(__file__).parent
SRC = ROOT / "efv5_pit_sign.py"
DOC = ROOT / X.DOC


def test_the_prior_table_is_the_free_signed_pitcher_keys():
    got = X.free_keys()
    assert sorted(got) == sorted(X.PRIOR)
    cands = V5C.candidates()
    for n in got:
        assert cands[n]["side"] == "pit" and cands[n]["head"] == "skill"
        assert int(cands[n]["sign"]) == 0
    assert set(X.IL_KEYS) <= set(X.PRIOR)
    assert all(X.PRIOR[n] == -1 for n in X.IL_KEYS)


def test_an_edit_is_undone_after_its_block():
    cands = V5C.candidates()
    before = {n: cands[n]["sign"] for n in X.PRIOR}
    names = RF.refit_candidates("pit", "skill")
    hit = RF.refit_candidates("hit", "skill")
    edit = {"bound": {"w2b_pu_p": 1}, "drop": ["w2i_days_skill_pit"]}
    with X.edited(edit):
        assert V5C.candidates()["w2b_pu_p"]["sign"] == 1
        inside = RF.refit_candidates("pit", "skill")
        assert "w2i_days_skill_pit" not in inside and "w2b_pu_p" in inside
        assert RF.refit_candidates("hit", "skill") == hit
    assert {n: V5C.candidates()[n]["sign"] for n in X.PRIOR} == before
    assert RF.refit_candidates("pit", "skill") == names


def _synthetic(n=600, slope=0.03, seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        z = float(rng.normal())
        u_c = float(rng.uniform())
        rest = float(rng.normal(0, 0.1))
        rows.append({"fold_id": f"f{i % 3}", "fid": "lv_dev", "player": f"p{i}", "u_c": u_c,
                     "u_y": u_c + rest + slope * z + float(rng.normal(0, 0.2)),
                     "e_s": rest + 0.01 * z, "e_t": 0.0, "z": {"k": z}, "part": {"k": 0.01 * z}})
    return rows


def test_the_sign_test_reads_a_planted_slope():
    pos = X.sign_test(_synthetic(slope=0.05), "k", B=200)
    assert pos["supported"] and pos["oof_sign"] == "+"
    neg = X.sign_test(_synthetic(slope=-0.05), "k", B=200)
    assert neg["supported"] and neg["oof_sign"] == "-"
    assert "planted" in pos and pos["resolves"] in (True, False)
    few = X.sign_test(_synthetic(n=10), "k", B=50)
    assert few["supported"] is False and few["status"] == "too few rows"


def test_the_arms_follow_the_registration():
    flags = {"w2b_pu_p": ["x"], "w2p_k_resid_p": ["x"], "w2i_days_skill_pit": ["x"],
             "w2i_sixty_skill_pit": ["x"]}
    arms = {a["name"]: a for a in X.arms_for(flags)}
    assert arms["B:w2b_pu_p"]["bound"] == {"w2b_pu_p": 1}
    assert "B:w2p_k_resid_p" not in arms and "D:w2p_k_resid_p" in arms   # no prior, no bound
    assert arms["D:IL"]["drop"] == ["w2i_days_skill_pit", "w2i_sixty_skill_pit"]
    assert arms["B:IL"]["bound"] == {"w2i_days_skill_pit": -1, "w2i_sixty_skill_pit": -1}
    assert not any(a["name"] in ("B:IL", "D:IL") for a in X.arms_for({"w2i_days_skill_pit": ["x"]}))


def test_the_combined_arm_takes_disjoint_passing_arms():
    def arm(name, keys, d, passes=True):
        return {"name": name, "keys": keys, "bound": {}, "drop": keys, "passes": passes,
                "rule": {"pooled_delta_vs_served": d}}
    res = [arm("D:a", ["a"], 0.003), arm("D:b", ["b"], 0.002), arm("D:IL", ["a", "c"], 0.001),
           arm("D:z", ["z"], 0.009, passes=False)]
    c = X.combined_arm(res)
    assert c["members"] == ["D:a", "D:b"] and c["keys"] == ["a", "b"]
    assert X.combined_arm(res[:1]) is None


def test_the_read_artifact():
    if not X.OUT_PATH.exists():
        pytest.skip("the read has not run in this tree")
    d = json.loads(X.OUT_PATH.read_text(encoding="utf-8"))
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["served_weights"]["w_skill"] == 1.0 and d["served_weights"]["w_time"] == 0.0
    c = d["checks"]
    assert c["production_max_abs_diff"] <= 1e-9 and c["fold_parity_max_abs_diff"] <= 1e-9
    assert all(v["matches_receipt"] for v in c["receipts"].values())
    assert sorted(d["sign_table"]["keys"]) == sorted(X.PRIOR)
    assert set(d["flagged"]) | set(d["stable"]) == set(X.PRIOR)
    assert d["arms_read"] == len(d["arms"]) + (1 if d["combined"] else 0)
    for a in d["arms"]:
        if a["passes"]:
            r = a["rule"]
            assert r["rule_pooled_above_zero"] and r["rule_no_frame_trails"]
            assert r["rule_null"] and r["rule_planted"]
    assert set(d["passing"]) == {a["name"] for a in d["arms"] if a["passes"]}
    if d["prepared"] is None:
        assert d["passing"] == [] and d["board"] is None
        assert not X.WEIGHTS_PATH.exists()
    for fid in d["sign_table"]["folds"]:
        frame, side, year = fid.split("|")
        assert side == "pit"
        assert not (frame == "lv_dev" and int(year) in X.F.RESERVED_LV)
        assert not (frame == "vm_dev" and int(year) >= 2025)


def test_the_flag_is_off():
    assert X.PIT_SIGN_ARM_ON is False


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
