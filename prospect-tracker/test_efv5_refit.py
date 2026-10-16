# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 COMBINED re-fit pins (EFV_FIX_B_REFIT, docs/efv-v2/EFV_V5_REFIT.md).

1. The flags: the re-fit is dark, the population norms flag moves with it, and the served
   path refuses an unprepared or half-flipped re-fit.
2. The arms: the dark list is the registration's; the rank transform is monotone,
   bounded, grouped and keeps None; a twin keeps its row's MiLB block and label and reads
   the consensus point the registration names.
3. The fit: fit_heads with both heads on the same rows is fit_combined; the weight rule is
   DS-08's OLS ratio, clipped, and cross-fitting leaves each fold out.
4. The claim rule; the stored weights file agrees with the read.
5. Gate compliance: no FV-cell grouping, no dash characters.
"""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest

import efv5_combined as V5C
import efv5_refit as X
import efv_v2_model as H
from test_efv5_combined import _attach_noise
from test_efv_v3 import _rows

ROOT = Path(__file__).parent
SRC = ROOT / "efv5_refit.py"
DOC = ROOT / X.DOC


# ---------------------------------------------------------------------------
# 1. the flags
# ---------------------------------------------------------------------------

def test_the_refit_is_dark_and_the_norms_flag_moves_with_it():
    import efv_w2_popmle as PM
    # EFV-REFIT-1 (owner 2026-10-15, 'Flip everything that passed'): RT flipped on
    assert X.EFV_V5_REFIT_ON is True
    assert bool(PM.POP_REPAIR_ON) == bool(X.EFV_V5_REFIT_ON)


def test_the_served_hook_sits_inside_the_v5_branch():
    src = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    i5 = src.index("if V5C.EFV_V5_COMBINED_ON:")
    ir = src.index("if R5.EFV_V5_REFIT_ON:")
    assert i5 < ir < src.index("if V5.EFV_V5_ON:")


def test_the_served_path_refuses_a_half_flip_or_an_unprepared_read(monkeypatch, tmp_path):
    import efv_w2_popmle as PM
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"prepared": False, "models": {}}), encoding="utf-8")
    monkeypatch.setattr(X, "EFV_V5_REFIT_ON", True)
    monkeypatch.setattr(PM, "POP_REPAIR_ON", False)
    with pytest.raises(RuntimeError, match="POP_REPAIR_ON"):
        X.production_models(p)
    monkeypatch.setattr(PM, "POP_REPAIR_ON", True)
    with pytest.raises(RuntimeError, match="nothing is prepared"):
        X.production_models(p)
    p.write_text(json.dumps({"prepared": True, "candidate": "RT", "passing": ["RT"],
                             "models_by_candidate": {}}), encoding="utf-8")
    monkeypatch.setattr(X, "SERVE_CANDIDATE", "R")
    with pytest.raises(RuntimeError, match="did not pass"):
        X.production_models(p)


# ---------------------------------------------------------------------------
# 2. the arms
# ---------------------------------------------------------------------------

def test_the_dark_list_is_the_registrations_and_leaves_the_candidates():
    doc = DOC.read_text(encoding="utf-8")
    cands = V5C.candidates()
    for n in X.DARK:
        assert n in cands, n
        assert f"`{n}`" in doc, n
    for side in ("hit", "pit"):
        kept = X.refit_candidates(side)
        assert not set(kept) & set(X.DARK)
        assert set(kept) | {n for n in X.DARK if cands[n]["side"] == side} == set(
            V5C.side_candidates(side))
        assert X.refit_candidates(side, dark=False) == V5C.side_candidates(side)


def test_the_rank_transform_is_monotone_bounded_and_keeps_none():
    vals = [3.0, None, -1.0, 3.0, 10.0]
    got = X.rank_values(vals)
    assert got[1] is None
    assert got[2] < got[0] == got[3] < got[4]
    assert all(-0.5 < v <= 0.5 for v in got if v is not None)
    assert got[4] == 0.5
    assert X.rank_values([None, None]) == [None, None]


def test_the_rank_transform_groups_by_decision_year():
    k = X.pop_key("hit")
    rows = [{"decision_year": y, "player_key": f"p{i}", "v2": {k: float(v)}}
            for i, (y, v) in enumerate([(2017, 1.0), (2017, 2.0), (2018, 100.0), (2018, 50.0)])]
    got = X.rank_transform(rows, "hit")
    assert [r["v2"][k] for r in got] == [0.0, 0.5, 0.5, 0.0]
    live = X.transform_live(rows, "hit")
    assert [r["v2"][k] for r in live] == [-0.25, 0.0, 0.5, 0.25]
    assert rows[0]["v2"][k] == 1.0          # the input rows are untouched


def test_the_twin_read_day():
    assert X.twin_day(2023) == "2023-10-15"


def test_a_twin_keeps_its_rows_block_and_label_and_reads_the_named_point():
    rows = [r for r in H.matrix_training_rows("hit") if r["v2"]["has_block"]][:400]
    twins, rec = X.build_twins("hit", rows)
    assert rec["twins"] == len(twins) > 0
    by = {r["player_key"]: r for r in rows}
    import efv_dataset as D
    recs = D.asof_records()
    for t in twins[:60]:
        r = by[t["player_key"]]
        for k in ("decision_year", "target", "reached", "weight", "kind"):
            assert t[k] == r[k], k
        for k in ("obp_rel", "level_rank", "age_rel_level", "contact", "has_block"):
            assert t["v2"][k] == r["v2"][k], k
        assert t["twin_read_day"] == X.twin_day(t["twin_read_season"])
        pts = [p for p in recs[t["player_key"]]["points"]
               if str(p.get("snapshot_date") or "")[:10] <= t["twin_read_day"]
               and p.get("consensus_fv_raw") is not None]
        last = sorted(pts, key=lambda p: p["snapshot_date"])[-1]
        assert t["twin_point"] == str(last["snapshot_date"])[:10]
        assert t["fv"] == float(last["consensus_fv_raw"])


# ---------------------------------------------------------------------------
# 3. the fit and the weights
# ---------------------------------------------------------------------------

def test_fit_heads_on_one_row_set_is_fit_combined():
    train = _attach_noise(_rows(years=range(2011, 2017), n=150), "hit")
    lam = {"skill": 100.0, "timing": 100.0}
    w = {"hit": {"w_skill": 0.5, "w_time": 0.2}}
    m5 = V5C.fit_combined(train, "hit", frame="lv", weights=w, absent_ok=False, lam=lam)
    m = X.fit_heads(train, "lv", train, "lv", "hit",
                    cands_skill=V5C.side_candidates("hit", "skill"),
                    cands_timing=V5C.side_candidates("hit", "timing"),
                    timing_outcome_blind=True, absent_ok=False, lam=lam)
    for h in ("skill", "timing"):
        assert m[h]["keys"] == m5[h]["keys"]
        assert np.allclose(m[h]["beta"], m5[h]["beta"], atol=1e-10)
        assert m[h]["b_uc"] == pytest.approx(m5[h]["b_uc"], abs=1e-10)


def test_the_weight_rule_is_ds08s_ratio_clipped():
    rng = np.random.default_rng(3)
    n = 4000
    u_c = rng.random(n)
    e_s = rng.normal(0, 0.2, n)
    e_t = rng.normal(0, 0.2, n)
    u_y = 0.2 + 0.4 * u_c + 0.2 * e_s - 0.1 * e_t + rng.normal(0, 0.05, n)
    w = X.ols_ratios(u_c, u_y, e_s, e_t)
    assert w["w_skill_ratio"] == pytest.approx(0.5, abs=0.02)
    assert w["w_skill"] == pytest.approx(w["w_skill_ratio"])
    assert w["w_time_ratio"] < 0 and w["w_time"] == 0.0
    big = X.ols_ratios(u_c, 0.4 * u_c + 0.8 * e_s, e_s, np.zeros(n))
    assert big["w_skill"] == H.W_MAX and big["w_time"] == 0.0
    assert "e_time" not in big["live_columns"]


def test_cross_fitting_leaves_each_fold_out():
    rng = np.random.default_rng(5)
    packs = []
    for i in range(4):
        n = 300
        u_c = rng.random(n)
        e_s = rng.normal(0, 0.2, n)
        slope = 0.1 if i == 0 else 0.3
        u_y = 0.5 * u_c + slope * e_s + rng.normal(0, 0.05, n)
        ols = {"keys": [f"k{i}_{j}" for j in range(n)], "u_c": u_c, "u_y": u_y,
               "e_s": e_s, "e_t": np.zeros(n)}
        packs.append({"fold_id": f"f{i}", "side": "hit", "ols": ols})
    cf = X.cross_fitted(packs)
    allw = X.weights_from(packs)["w_skill"]
    assert cf["f0"]["w_skill"] == pytest.approx(X.weights_from(packs[1:])["w_skill"])
    assert cf["f0"]["w_skill"] > allw and cf["f1"]["w_skill"] < cf["f0"]["w_skill"]


# ---------------------------------------------------------------------------
# 4. the claim and the stored read
# ---------------------------------------------------------------------------

def test_the_claim_rule():
    frames = {"vm_dev": {"x": {"delta": -0.03, "ci95": [-0.06, -0.001], "n": 830}},
              "lv_dev": {"x": {"delta": -0.01, "ci95": [-0.04, 0.02], "n": 2862}}}
    c = X.claim_from(frames, "x", date_="2026-10-15", source="t")
    assert c["word"] == "trails" and c["model_id"] == X.SERVED_MODEL_ID
    frames["vm_dev"]["x"]["ci95"] = [-0.05, 0.01]
    assert X.claim_from(frames, "x", date_="2026-10-15", source="t")["word"] == "ties"
    frames["vm_dev"]["x"].update(delta=0.03, ci95=[0.01, 0.05])
    c = X.claim_from(frames, "x", date_="2026-10-15", source="t")
    assert c["word"] == "ties"                 # a development frame never reads "leads"
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in c["text"]


def test_the_stored_weights_agree_with_the_read():
    if not (X.FIT_PATH.exists() and X.WEIGHTS_PATH.exists()):
        pytest.skip("the registered read has not run in this tree")
    fit = json.loads(X.FIT_PATH.read_text(encoding="utf-8"))
    w = json.loads(X.WEIGHTS_PATH.read_text(encoding="utf-8"))
    assert w["prepared"] == bool(fit["ship"]["prepared"])
    cand = fit["ship"]["prepared"] or "R"
    assert w["candidate"] == cand and w["passing"] == fit["ship"]["passing"]
    assert X.SERVE_CANDIDATE is None
    for side in ("hit", "pit"):
        ws = w["weights"][side]
        assert 0.0 <= ws["w_skill"] <= H.W_MAX and 0.0 <= ws["w_time"] <= H.W_MAX
        assert ws["w_skill"] == fit["weights"][cand][side]["w_skill"]
        assert ws["w_time"] == fit["weights"][cand][side]["w_time"]
        m = X.model_in(w["models_by_candidate"][cand][side])
        assert m["model_id"] == V5C.MODEL_ID
        assert m["w_skill"] in (0.0, ws["w_skill"]) and m["w_time"] in (0.0, ws["w_time"])
        for h in ("skill", "timing"):
            head = m.get(h)
            if head is None:
                continue
            assert not set(head["keys"]) & {V5C.candidates()[n]["key"] for n in X.DARK}
            assert len(head["keys"]) == len(head["beta"]) == len(head["mu"]) == len(head["sd"])
        assert m["timing"] is None or m["timing"]["trained_frame"] == "lv"
    assert w["claim"] == fit["claim_prepared"] == w["claims_by_candidate"][cand]


# ---------------------------------------------------------------------------
# 5. gate compliance
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


def test_no_reserved_vintage_reaches_the_timing_pool():
    assert X.LV_POOL_LAST < min(X.F.RESERVED_LV)
    assert math.isfinite(X.MAX_TRAIL) and X.MAX_TRAIL == 0.005
