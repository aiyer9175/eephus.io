# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PV-10: the provisional v2 draftee head lab (tools/provisional_draftee_lab.py).

Pinned: the frame drops a draftee graded on or before the anchor or with a pro line before
his class and labels only first grades inside the window; the block in
data/provisional_v2_eval.json is a forward-chained BACKCAST whose verdict follows the
pre-declared rule; the lab writes only its own block, to the path the harness redirects;
provisional_v2.build carries the block forward; nothing reads WAR or names an FV cell.
No test here writes inside the checkout.
"""
from __future__ import annotations

import collections
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import provisional_v2 as P  # noqa: E402
import provisional_draftee_lab as L  # noqa: E402

EVAL = ROOT / "data" / "provisional_v2_eval.json"


def _block():
    if not EVAL.exists():
        pytest.skip("provisional_v2_eval.json not built")
    doc = json.loads(EVAL.read_text(encoding="utf-8"))
    if L.BLOCK not in doc:
        pytest.skip("pv10_draftee block not written")
    return doc[L.BLOCK]


# --- the frame ----------------------------------------------------------------------

def _pick(m, pick):
    return {"mlbam": m, "name": f"p{m}", "pick": pick, "round": 1.0, "slot": 1e6, "bonus": 1e6,
            "rank": None, "hs": 0.0, "jc": 0.0, "birth": "2002-01-01", "pitcher": 0.0}


def _fake_inputs(ev_raw, lines=()):
    inp = object.__new__(P.Inputs)
    inp.lines = collections.defaultdict(list)
    for m, season in lines:
        inp.lines[(m, season, "hit")].append({"lv": "A"})
    inp.mlb_seasons = collections.defaultdict(set)
    inp.ev_raw = ev_raw
    return inp


def test_the_draft_frame_drops_prior_opinions_and_prior_pro_lines():
    picks = {y: [] for y in L.CLASSES}
    picks[2023] = [_pick(1, 1), _pick(2, 2), _pick(3, 3), _pick(4, 4), _pick(5, 5)]
    ev = {1: [("2023-07-01", "fangraphs", 50.0, None)],          # graded before the draft closed
          2: [("2023-08-03", "fangraphs", 42.5, None)],          # first graded inside PRE
          3: [("2024-07-20", "mlb_pipeline", 45.0, None)],       # after PRE, inside G12
          5: [("2026-12-01", "fangraphs", 45.0, None)]}          # after the run date: never read
    df, counts = L.build_frame(_fake_inputs(ev, lines=[(4, 2022)]), picks, "2026-10-02", "DRAFT")
    got = {int(m): r for m, r in zip(df.mlbam, df.to_dict("records"))}
    assert set(got) == {2, 3, 5}
    assert counts["2023"]["out_opinion_on_or_before_anchor"] == 1
    assert counts["2023"]["out_pro_line_before_class"] == 1 and counts["2023"]["universe"] == 3
    assert (got[2]["PRE_ANY"], got[2]["PRE_FG"], got[2]["FV1_PRE_FG"]) == (1, 1, 42.5)
    assert (got[3]["PRE_ANY"], got[3]["G12_ANY"], got[3]["G12_MLBP"]) == (0, 1, 1)
    assert got[5]["PRE_ANY"] == 0 and got[5]["G12_ANY"] == 0


def test_the_noline_frame_keeps_only_draftees_without_a_line_in_their_class_season():
    picks = {y: [] for y in L.CLASSES}
    picks[2024] = [_pick(1, 1), _pick(2, 2)]
    df, counts = L.build_frame(_fake_inputs({}, lines=[(1, 2024)]), picks, "2026-10-02", "NOLINE_OCT")
    assert list(df.mlbam) == [2]
    assert counts["2024"]["out_line_in_class_season"] == 1
    assert set(df.anchor) == {"2024-10-15"}


def test_round_numbers_put_supplemental_rounds_at_the_half_step():
    assert L._round_num("1") == 1.0 and L._round_num("CB-A") == 1.5 and L._round_num("PPI") == 1.5
    assert L._round_num("CB-B") == 2.5 and L._round_num("SUP-3") == 3.5 and L._round_num("20") == 20.0


# --- the artifact block -------------------------------------------------------------

def test_the_block_is_a_forward_chained_backcast():
    b = _block()
    assert b["label"] == "BACKCAST" and b["reads_no_war"] is True
    assert b["served"] is False and b["feeds_efv"] is False
    assert b["predeclaration"] == L.PREDECLARATION and (ROOT / b["predeclaration"]).exists()
    as_of = b["as_of"]
    for frame in ("DRAFT", "SIGNED", "NOLINE_OCT"):
        for key, h in b[frame]["T1"].items():
            window = key.split("_")[1]
            left = {int(c) for c in h["classes_left_out"]}
            assert h["test_classes"], (frame, key)
            for t, m in h["by_class"].items():
                t = int(t)
                anchor = L.frame_anchor(frame, t)
                assert L.window_end(window, t) <= as_of, (frame, key, t)
                assert len(m["train_classes"]) >= L.MIN_TRAIN_CLASSES
                for c in m["train_classes"]:
                    assert c < t and L.window_end(window, c) <= anchor, (frame, key, t, c)
                assert t not in left and not left & set(m["train_classes"])
    for s, h in b["DRAFT"]["T2"].items():
        assert all(L.window_end("PRE", t) <= as_of for t in h["test_classes"]), s


def test_the_verdict_follows_the_predeclared_rule():
    b = _block()
    p = b["DRAFT"]["T1"]["ANY_PRE"]["pooled"]
    wins = p["auc_minus_draft_order_ci95"][0] > 0 and p["ap_minus_draft_order_ci95"][0] > 0
    assert b["verdict"]["selection"].startswith("the head orders" if wins else "draft order is the head")
    for s, h in b["DRAFT"]["T2"].items():
        below = h["pooled"]["mae_minus_const_ci95"][1] < 0
        assert b["verdict"]["level"][s].startswith("below the constant" if below else "no level claim"), s


def test_the_block_names_no_fv_cell_and_no_label_distribution():
    text = json.dumps(_block())
    assert "label_dist" not in text
    keys = re.findall(r'"([^"]+)":', text)
    assert not [k for k in keys if re.search(r"(fv|cell)[_ ]?(45|50|55|60|65)", k.lower())]


# --- writing ------------------------------------------------------------------------

def test_the_lab_writes_only_its_block_to_the_redirected_path(tmp_path, monkeypatch):
    assert P.EVAL_PATH.resolve() != EVAL.resolve()        # conftest redirects the eval path
    target = tmp_path / "ev.json"
    target.write_text(json.dumps({"schema": 1, "backcast": {"oct": {}}, "label": "BACKCAST"}), encoding="utf-8")
    monkeypatch.setattr(P, "EVAL_PATH", target)
    assert L.persist({"label": "BACKCAST", "x": 1}) == target
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["backcast"] == {"oct": {}} and doc["label"] == "BACKCAST"
    assert doc[L.BLOCK] == {"label": "BACKCAST", "x": 1}


def test_build_carries_the_lab_blocks_forward(tmp_path):
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"backcast": {}, "pv10_draftee": {"a": 1}, "stray": 2}), encoding="utf-8")
    assert P.carried_blocks(ev) == {"pv10_draftee": {"a": 1}}
    assert P.carried_blocks(tmp_path / "missing.json") == {}
    assert L.BLOCK in P.LAB_BLOCKS
    src = inspect.getsource(P.build)
    i = src.index("ev.update(carried_blocks(ep))")
    assert i < src.index("_write_json(ep, ev)")


def test_the_lab_reads_no_war():
    src = (ROOT / "tools" / "provisional_draftee_lab.py").read_text(encoding="utf-8")
    for tok in ("career_war", "realized_war", "xfv_war", "war6", "sabermetrics", "efv_ungraded"):
        assert tok not in src, tok
