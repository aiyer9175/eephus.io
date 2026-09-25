# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M12-03 pins: the scoreboard's head-to-head cells sit on the verdict's frame.

tools/efv_scoreboard.py built head_to_head.vs from accuracy.pooled_efv_common
(every base year, n 3,272, eFV +0.044) and copied verdict_vs_consensus from the
vintage-matched frame (n 812, eFV -0.007). The Diamond card printed the first as
tiles over the second as a sentence. docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md
reads the verdict off the vintage-matched frame, so the cells follow it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_scoreboard as S  # noqa: E402


def _rater(sp, auc, n):
    return {"n": n, "spearman": sp, "auc": auc}


def _sb(with_vintage: bool = True) -> dict:
    acc = {
        "common_n": 4316, "common_n_efv": 3272,
        "pooled_efv_common": {
            "xfv": _rater(0.3607, 0.7574, 3272),
            "prospx_consensus": _rater(0.3163, 0.7243, 3272),
            "fangraphs": _rater(0.2768, 0.6860, 3272),
            "mlb_pipeline": _rater(0.3169, 0.7102, 3272)},
        "head_to_head_by_frame": {
            "vintage_matched": {"n": 812, "delta": -0.0071,
                                "basis_note": "base year equals the eFV decision year"},
            "all_vintages": {"n": 3272, "delta": 0.0444,
                             "basis_note": "every base year"}},
        "head_to_head_verdict": {"basis": "pooled_efv_common_vintage_matched",
                                 "n": 812, "delta": -0.0071, "resolvable": False},
        "by_archetype": [],
    }
    if with_vintage:
        acc["pooled_efv_common_vintage_matched"] = {
            "xfv": _rater(0.4064, 0.7564, 812),
            "prospx_consensus": _rater(0.4135, 0.7529, 812),
            "fangraphs": _rater(0.3682, 0.7183, 812),
            "mlb_pipeline": _rater(0.4117, 0.7430, 812)}
    return {"accuracy": acc}


def test_cells_are_scored_on_the_verdict_frame():
    h = S._head_to_head(_sb())
    vv = h["verdict_vs_consensus"]
    cell = h["vs"]["prospx_consensus"]["spearman"]
    assert h["vs_frame"] == "vintage_matched"
    assert cell["n"] == vv["n"] == h["vs_frame_n"] == 812
    assert (cell["margin"] > 0) == (vv["delta"] > 0)
    assert cell["margin"] == vv["delta"]
    for key in ("prospx_consensus", "fangraphs", "mlb_pipeline"):
        assert h["vs"][key]["auc_contributor"]["n"] == 812


def test_every_frame_is_published_beside_the_cells():
    h = S._head_to_head(_sb())
    assert set(h["head_to_head_by_frame"]) == {"vintage_matched", "all_vintages"}
    assert h["vs_frame_note"] == "base year equals the eFV decision year"
    assert h["by_archetype_basis"]


def test_a_backtest_without_the_vintage_frame_says_which_frame_it_used():
    h = S._head_to_head(_sb(with_vintage=False))
    assert h["vs_frame"] == "all_vintages"
    assert "tilted" in h["basis"]
    assert h["vs"]["prospx_consensus"]["spearman"]["n"] == 3272


def test_the_vm2_frame_rides_beside_the_vm1_verdict_and_moves_no_cell():
    """EV-01: a timing-pinned vm2 frame in the backtest is carried, and the
    cells and the verdict stay on vm1 until the owner promotes it."""
    sb = _sb()
    acc = sb["accuracy"]
    acc["head_to_head_verdict"]["frame_version"] = "vm1"
    acc["head_to_head_by_frame"]["vintage_matched_vm2"] = {
        "n": 803, "delta": -0.0213, "frame_version": "vm2",
        "basis_note": "timing-pinned"}
    acc["head_to_head_verdict_vm2"] = {
        "basis": "pooled_efv_common_vintage_matched_vm2", "n": 803,
        "delta": -0.0213, "frame_version": "vm2", "role": "headline_candidate"}
    acc["pooled_efv_common_vintage_matched_vm2"] = {
        "xfv": _rater(0.3916, 0.7471, 803),
        "prospx_consensus": _rater(0.4129, 0.7492, 803)}
    h = S._head_to_head(sb)
    assert h["vs_frame"] == "vintage_matched" and h["vs_frame_n"] == 812
    assert h["verdict_vs_consensus"]["frame_version"] == "vm1"
    assert h["verdict_vs_consensus_vm2"]["frame_version"] == "vm2"
    assert h["verdict_vs_consensus_vm2"]["role"] == "headline_candidate"
    assert "vintage_matched_vm2" in h["head_to_head_by_frame"]
    assert h["vs"]["prospx_consensus"]["spearman"]["n"] == 812
