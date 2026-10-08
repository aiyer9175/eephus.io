# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_W2_DRIVER_DIAG pins: the driver-subtraction diagnosis (tools/efv_v2_driver_diag.py).

1. The variant fit with no restriction IS fit_v2 (same heads, weights and order on every
   synthetic fold); withholding a driver no fold admitted reproduces V2; leave-one-in
   offers exactly one driver; DS-Q2 holds unless relaxed.
2. The guards: a reserved list vintage or a 2025 year in a fold's training rows raises
   before any fit.
3. The pooled partial slope recovers the sign of a planted driver, and the label
   comparison flags a planted sign flip.
4. The (side, vintage) group split sums to the frame's within delta.
5. The board move: the counterfactual reconstructs the served order and counts rows
   that moved toward and away from consensus; the weight curve at k 1 is the V2 base and
   at k 0 the consensus order.
6. The whole path on SYNTHETIC rows (never a frame): every part present, the artifact
   free of dashes, no strata dimension keyed on a grade level, and a reduced bootstrap
   refused under data/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_v2_driver_diag as D  # noqa: E402
import test_efv_v2_model_class_screen as T  # noqa: E402

WEIGHTS = T.WEIGHTS


@pytest.fixture(scope="module")
def inputs():
    return T.synthetic_inputs(n=50, seed=5)


# ---------------------------------------------------------------------------
# 1. the variant fit
# ---------------------------------------------------------------------------

def test_unrestricted_variant_is_fit_v2(inputs):
    for fid in D.FRAMES:
        kind = D.FRAME_KIND[fid]
        fr = inputs["frames"][fid]
        for side in F.SIDES:
            for fold in fr["folds"]:
                blk = fr["by_side"][side][fold]
                m = D.fit_variant(blk["train"], side, kind, WEIGHTS, absent_ok=False)
                base = blk["v2_model"]
                assert m["w_skill"] == base["w_skill"] and m["w_time"] == base["w_time"]
                a = [p["order_idx"] for p in H.predict_v2(m, blk["test"])]
                b = [p["order_idx"] for p in blk["v2_pred"]]
                assert a == b


def test_withholding_a_never_admitted_driver_reproduces_v2(inputs):
    fid, side = "lv_dev", "hit"
    adm = D.base_admission(inputs, fid)[side]
    ever = {k for a in adm.values() for k in a["skill"]}
    never = [k for k in H.skill_candidates(side) if k not in ever]
    assert never, "the synthetic fixture should leave some skill driver unadmitted"
    v2o = D.base_orders(inputs, fid)
    o, _ = D.variant_orders(inputs, fid, side, {"drop": [("skill", never[0])]}, log=lambda m: None)
    assert all(o[k] == v2o[k] for k in o)


def test_leave_one_in_offers_one_driver_and_dsq2_holds(inputs):
    blk = inputs["frames"]["lv_dev"]["by_side"]["hit"][2019]
    m = D.fit_variant(blk["train"], "hit", "lv", WEIGHTS, only=[("skill", "tool_hit")],
                      absent_ok=False)
    assert m["skill_candidates"] == ["tool_hit"] and m["timing_candidates"] == []
    assert m["timing"] is None
    pblk = inputs["frames"]["lv_dev"]["by_side"]["pit"][2019]
    held = D.fit_variant(pblk["train"], "pit", "lv", WEIGHTS, only=[("timing", "level_rank")],
                         absent_ok=False)
    assert held["timing"] is None and held["consensus_only"]
    relaxed = D.fit_variant(pblk["train"], "pit", "lv", WEIGHTS,
                            only=[("timing", "level_rank")], dsq2=False, absent_ok=False)
    assert relaxed["timing"] is not None
    specs = D.variant_specs("pit", "lv", False)
    loi_t = [s for s in specs if s["kind"] == "leave_one_in" and s["head"] == "timing"]
    assert loi_t and all(s["dsq2_relaxed"] and s["spec"]["dsq2"] is False for s in loi_t)
    loi_s = [s for s in specs if s["kind"] == "leave_one_in" and s["head"] == "skill"]
    assert all(s["spec"]["dsq2"] is True for s in loi_s)


# ---------------------------------------------------------------------------
# 2. guards
# ---------------------------------------------------------------------------

def test_guards_raise_before_any_fit(monkeypatch):
    calls = []
    monkeypatch.setattr(H, "fit_skill_head", lambda *a, **k: calls.append(1))
    with pytest.raises(F.ReservedFrameError):
        D.fit_variant(T._rows("hit", [2019, 2020], 30, 1, "lv"), "hit", "lv", WEIGHTS,
                      absent_ok=False)
    with pytest.raises(F.ReservedFrameError):
        D.fit_variant(T._rows("hit", [2024, 2025], 30, 1, "vm"), "hit", "vm", WEIGHTS)
    with pytest.raises(F.ReservedFrameError):
        D.pooled_partial_slope(T._rows("hit", [2024, 2025], 30, 1, "vm"), "tool_hit")
    assert calls == []


# ---------------------------------------------------------------------------
# 3. slopes and the label comparison
# ---------------------------------------------------------------------------

def test_pooled_slope_sign_and_label_flip():
    rows = T._rows("hit", range(2011, 2017), 80, 9, "lv")
    up = D.pooled_partial_slope(rows, "tool_hit")
    assert up["slope"] > 0 and up["t"] > 2
    flipped = []
    for r in rows:
        th = r["feats"]["tool_hit"]
        flipped.append(dict(r, target=-0.16 * (th - 50) + 0.1 * (r["fv"] - 45)))
    a = D.slope_rows(rows, [("skill", "tool_hit")])
    b = D.slope_rows(flipped, [("skill", "tool_hit")])
    cmp_ = D.compare_labels(a, b, "ewar", "fwar")
    assert cmp_["skill.tool_hit"]["pooled_sign_relation"] == "SIGN FLIP"
    assert b["skill.tool_hit"]["pooled"]["slope"] < 0


# ---------------------------------------------------------------------------
# 4. the group split
# ---------------------------------------------------------------------------

def test_group_split_sums_to_the_frame_delta(inputs):
    import efv_v2_stat as S
    rows = D.MCS.scored_rows(inputs, "vm_dev")
    split = D.group_split(rows)
    d = S.paired_delta([c["key"] for c in rows], [c["group"] for c in rows],
                       [c["outcome"]["war"] for c in rows],
                       [bool(c["outcome"]["contributor"]) for c in rows],
                       [c["grades"][D.V2_KEY] for c in rows],
                       [c["grades"][D.CONS] for c in rows],
                       [c["grades"][D.CONS] for c in rows], statistic="within", B=0)
    assert split["sum_of_contributions"] == pytest.approx(d["delta"], abs=2e-5)


# ---------------------------------------------------------------------------
# 5. the board move
# ---------------------------------------------------------------------------

def _xfv(orders, w):
    bp = {}
    for i, (cons, e_s, e_t) in enumerate(orders):
        u_c = (i + 1) / len(orders)
        o = u_c + w["hit"]["w_skill"] * e_s + w["hit"]["w_time"] * e_t
        bp[f"p{i}"] = {"grade_basis": "efv_v2", "consensus_fv": cons,
                       "efv_v2": {"u_c": u_c, "e_skill": e_s, "e_time": e_t,
                                  "order_idx": o, "group": ["hit", 2026]}}
    return {"by_player": bp, "meta": {}}


def test_board_move_counterfactual_counts_rows():
    w_after = {"hit": {"w_skill": 1.0, "w_time": 0.0}, "pit": {"w_skill": 0.0, "w_time": 0.0}}
    w_before = {"hit": {"w_skill": 0.0, "w_time": 0.0}, "pit": {"w_skill": 0.0, "w_time": 0.0}}
    rows = [(40 + i, 0.0, 0.0) for i in range(10)]
    rows[0] = (40, 2.0, 0.0)            # the lowest consensus row pushed to the top
    doc = _xfv(rows, w_after)
    out = D.board_move(doc, w_before, w_after, before_doc=doc, after_doc=doc)
    cf = out["counterfactual"]
    assert cf["rows_not_reconstructed"] == 0
    tot = cf["by_side"]["hit"]["total"]
    assert tot["n"] == 10 and tot["rank_changed"] == 10
    assert tot["direction"] == "away from consensus"
    assert tot["farther_from_consensus_rank"] >= 1
    assert tot["spearman_with_consensus_before"] == pytest.approx(1.0)
    real = out["realized"]["by_side"]["hit"]["total"]
    assert real["rank_changed"] == 0 and real["direction"] == "unchanged"


# ---------------------------------------------------------------------------
# 6. the whole path on synthetic rows
# ---------------------------------------------------------------------------

def _cells(inputs):
    out = {}
    for fid in D.FRAMES:
        out[fid] = {}
        for c in D.MCS.scored_rows(inputs, fid):
            out[fid][(c["side"], int(c["year"]), c["key"])] = {
                "side": c["side"], "list_year": str(c["year"]),
                "level_at_list": "AA" if hash(c["key"]) % 2 else "A"}
    return out


@pytest.fixture(scope="module")
def synthetic_doc(inputs, tmp_path_factory):
    lv = {s: T._rows(s, range(2011, 2020), 50, 21 + i, "lv") for i, s in enumerate(F.SIDES)}
    vm = {s: T._rows(s, range(2011, 2024), 40, 31 + i, "vm") for i, s in enumerate(F.SIDES)}
    w = {"hit": {"w_skill": 0.6, "w_time": 0.01}, "pit": {"w_skill": 1.0, "w_time": 0.1}}
    w2 = {"hit": {"w_skill": 0.9, "w_time": 0.2}, "pit": {"w_skill": 1.0, "w_time": 0.02}}
    board = _xfv([(40 + (i % 7), 0.1 * (i % 3), 0.05 * (i % 5)) for i in range(30)], w2)
    real = {"inputs": inputs, "lv_rows": {"fwar": lv, "ewar_v2": lv},
            "vm_rows": {"current": vm, "E0": vm}, "epoch": {"dir": None, "arms": {}},
            "cells": _cells(inputs),
            "board": {"current": board, "w_before": w, "w_after": w2,
                      "before_doc": board, "after_doc": board}}
    doc = D.run(real, B=60, exploratory=True, log=lambda m: None)
    out = tmp_path_factory.mktemp("diag") / "diag.json"
    D.write_doc(doc, out)
    return doc, out


def test_synthetic_run_carries_every_part(synthetic_doc):
    doc, out = synthetic_doc
    for key in ("base", "drivers", "slopes", "strata", "board", "findings", "reserved_guard",
                "definitions"):
        assert key in doc
    assert doc["admits"] is False and doc["ledger_row"] is False
    for fid in D.FRAMES:
        for side in F.SIDES:
            ids = {r["id"] for r in doc["drivers"][fid][side]}
            assert "head:skill_only" in ids and "head:timing_only" in ids
            assert any(i.startswith("loo:") for i in ids) and any(i.startswith("loi:") for i in ids)
    for fid in D.FRAMES:
        curve = doc["weights_diag"]["scale"]["frames"][fid]
        assert curve["1.0"]["all"] == pytest.approx(doc["base"][fid]["all"]["delta"], abs=1e-9)
        assert curve["0.0"]["all"] == pytest.approx(0.0, abs=1e-9)
        assert "vs_consensus" in doc["weights_diag"]["pre_refit"][fid]["hit"]
    assert "push_by_head" in doc["board"]["counterfactual"]
    assert "E0_to_current" in doc["slopes"]["vm"]["compare"]
    assert "ewar_v2_to_fwar" in doc["slopes"]["lv"]["compare"]
    text = out.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text
    json.loads(text)


def test_no_stratum_is_a_grade_level():
    banned = ("fv", "grade", "tier", "rank", "consensus")
    for dim in D.STRATA_DIMS:
        assert not any(b in dim for b in banned), dim
    assert set(D.STRATA_DIMS) <= set(D.ST.DIMENSIONS)
    assert "source_disagreement" not in D.STRATA_DIMS


def test_reduced_bootstrap_refused_under_data(capsys):
    rc = D.main(["--B", "10", "--out", str(D.OUT_PATH)])
    assert rc == 2
    assert "refused" in capsys.readouterr().out
