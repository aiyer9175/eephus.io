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

FP3-1 / FP3-3 (owner answers 2026-09-25): the headline moved to the
timing-pinned frame vm2 and the scoreboard names no frame of its own; the cells
read the block head_to_head_verdict.basis names, and the per-source Holm
reading is copied beside each cell when it sits on the same basis.
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
                                "basis": "pooled_efv_common_vintage_matched",
                                "basis_note": "base year equals the eFV decision year"},
            "all_vintages": {"n": 3272, "delta": 0.0444,
                             "basis": "pooled_efv_common",
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


def _vm2_headline(sb: dict, with_holm: bool = True) -> dict:
    """The artifact after FP3-1: head_to_head_verdict is read off vm2, vm1 is a
    superseded frame in head_to_head_by_frame."""
    acc = sb["accuracy"]
    acc["head_to_head_by_frame"]["vintage_matched"]["role"] = "superseded"
    acc["head_to_head_by_frame"]["vintage_matched_vm2"] = {
        "n": 803, "delta": -0.0055, "frame_version": "vm2", "role": "headline",
        "basis": "pooled_efv_common_vintage_matched_vm2",
        "basis_note": "timing-pinned"}
    acc["head_to_head_verdict"] = {
        "basis": "pooled_efv_common_vintage_matched_vm2", "n": 803,
        "delta": -0.0055, "frame_version": "vm2", "role": "headline",
        "resolvable": False, "mde95": 0.0303, "mde95_status": "carried"}
    acc["pooled_efv_common_vintage_matched_vm2"] = {
        "xfv": _rater(0.4074, 0.7505, 803),
        "prospx_consensus": _rater(0.4129, 0.7492, 803),
        "fangraphs": _rater(0.3662, 0.7153, 803),
        "mlb_pipeline": _rater(0.4116, 0.7392, 803)}
    if with_holm:
        def leg(d, verdict):
            return {"delta": d, "ci95": [d - 0.02, d + 0.02], "verdict": verdict,
                    "holm": {"reject_holm": verdict is not None, "mde95_holm": 0.03}}
        acc["head_to_head_vs_sources"] = {
            "basis": "pooled_efv_common_vintage_matched_vm2",
            "holm": {"family": ["prospx_consensus.spearman"], "k": 6, "alpha": 0.05,
                     "procedure": "Holm", "rule": "r"},
            "sources": {
                "prospx_consensus": {"spearman": leg(-0.0055, None), "auc": leg(0.0013, None)},
                "fangraphs": {"spearman": leg(0.0412, "beats FanGraphs"),
                              "auc": leg(0.0352, "beats FanGraphs")},
                "mlb_pipeline": {"spearman": leg(-0.0042, None), "auc": leg(0.0113, None)}}}
    return sb


def test_the_cells_follow_the_verdict_basis_to_the_vm2_headline():
    """FP3-1: with the verdict on vm2 every cell and the frame id follow it, and
    no second verdict key rides beside it."""
    h = S._head_to_head(_vm2_headline(_sb()))
    assert h["vs_frame"] == "vintage_matched_vm2" and h["vs_frame_n"] == 803
    assert h["verdict_vs_consensus"]["frame_version"] == "vm2"
    assert "verdict_vs_consensus_vm2" not in h
    assert h["vs_frame_note"] == "timing-pinned"
    for key in ("prospx_consensus", "fangraphs", "mlb_pipeline"):
        assert h["vs"][key]["spearman"]["n"] == 803
        assert h["vs"][key]["auc_contributor"]["n"] == 803
    assert h["vs"]["prospx_consensus"]["spearman"]["margin"] == h["verdict_vs_consensus"]["delta"]
    assert "vintage_matched" in h["head_to_head_by_frame"]


def test_holm_readings_are_copied_only_from_the_same_basis():
    h = S._head_to_head(_vm2_headline(_sb()))
    fg = h["vs"]["fangraphs"]
    assert fg["spearman"]["holm_verdict"] == "beats FanGraphs"
    assert fg["auc_contributor"]["holm_verdict"] == "beats FanGraphs"
    assert h["vs"]["prospx_consensus"]["spearman"]["holm_verdict"] is None
    assert h["holm_family"]["k"] == 6 and h["holm_family"]["alpha"] == 0.05
    # A per-source block on another basis is not copied onto these cells.
    sb = _vm2_headline(_sb())
    sb["accuracy"]["head_to_head_vs_sources"]["basis"] = "pooled_efv_common_vintage_matched"
    h2 = S._head_to_head(sb)
    assert "holm_verdict" not in h2["vs"]["fangraphs"]["spearman"]
    assert h2["holm_family"] is None


def test_the_scoreboard_names_no_frame_block_of_its_own():
    """ONE KEY: _head_to_head reads the block through head_to_head_verdict.basis."""
    import inspect
    src = inspect.getsource(S._head_to_head)
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    code = code.split('"""', 2)[-1]
    assert "pooled_efv_common_vintage_matched" not in code
    assert "head_to_head_verdict" in code and 'hv.get("basis")' in code
