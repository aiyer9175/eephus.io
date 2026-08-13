# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M-1 pins: the head-to-head verdict may only be read off a SYMMETRIC frame.

Pre-registration: docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md.
Producer: tools/efv_headtohead_frame_lab.py -> data/xfv_headtohead_frame_eval.json.

The thing being guarded is a claim, not a number. eFV holds one grade per player,
fitted at that player's decision year, while the common set carries a consensus
read for every base year, so the comparison frame is a CHOICE and the choice
decides the answer:

    all base years      +0.0313 at 0.881x its floor   not resolvable
    pre-debut only      +0.0625 at 1.679x its floor   would read "beats consensus"
    base year == debut  +0.0040 at 0.131x its floor   dead tie

The middle frame is the only one that clears a floor, and it is the one a future
edit is most likely to promote by accident, because it is both the newest and the
most flattering. It removes the rows where the CONSENSUS is advantaged and keeps
the rows where eFV is, so its margin is earned partly by an asymmetry rather than
by better ordering. These tests exist so that promotion cannot happen quietly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
ARTIFACT = DATA / "xfv_headtohead_frame_eval.json"
BACKTEST = DATA / "source_backtest.json"


def _load(p: Path):
    if not p.exists():
        pytest.skip(f"{p.name} not built on this tree")
    return json.loads(p.read_text(encoding="utf-8"))


def test_all_three_frames_are_scored_and_each_carries_its_own_floor():
    d = _load(ARTIFACT)
    for frame in ("incumbent", "corrected", "vintage_matched"):
        cell = d.get(frame)
        assert cell, f"{frame} missing from the artifact"
        assert cell.get("mde95"), f"{frame} has no floor"
        assert cell.get("delta") is not None, f"{frame} has no delta"
        # A frame without its own floor is the exact failure mode this lane was
        # opened to fix: a fresh delta read against an inherited constant.
        assert isinstance(cell["mde95"], (int, float)) and cell["mde95"] > 0


def test_the_frames_are_scored_inside_the_same_draws():
    """The incumbent must be RE-DERIVED here, never read off a stored constant.

    Mixing a stored floor with a fresh delta has crossed a verdict boundary twice
    in this program, which is why the lab scores every frame in one bootstrap.
    """
    d = _load(ARTIFACT)
    assert d.get("B_used", 0) >= 500, "too few usable draws to floor anything"
    assert "paired_difference" in d, "frames were not paired inside the draws"
    pd_ = d["paired_difference"]
    assert pd_.get("sd") is not None and pd_.get("ci95")


def test_the_direction_control_holds():
    """The consensus must order the REMOVED rows better than the retained ones.

    That is the whole mechanism: on a post-debut read the consensus is grading a
    player it has already watched in the majors. If this ever flips, the stated
    reason for stripping those rows is wrong and the frame choice has to be
    re-argued from scratch.
    """
    d = _load(ARTIFACT)
    dc = d.get("direction_control") or {}
    assert dc.get("mechanism_holds") is True, dc
    assert dc["consensus_rho_removed"] > dc["consensus_rho_retained"]


def test_the_published_verdict_is_read_off_the_symmetric_frame():
    """The site's head-to-head verdict must sit on the vintage-matched basis.

    Not on the pre-debut basis, which is the flattering one, and not on the
    all-vintages basis, which hands the consensus the outcome.
    """
    bt = _load(BACKTEST)
    acc = bt.get("accuracy") or {}
    if not acc.get("head_to_head_by_frame"):
        pytest.skip("source_backtest.json predates the M-1 frame split")
    hh = acc.get("head_to_head_verdict")
    assert hh, "the frame split ran but published no verdict"
    assert hh.get("basis") == "pooled_efv_common_vintage_matched", (
        "the head-to-head verdict moved off the symmetric frame; if that is "
        "deliberate it needs its own gate, because the other two frames each "
        "hand one of the two graders an information edge")


def test_a_win_is_never_published_off_the_predebut_frame():
    """The load-bearing guard. `xfv_beats` may not be true on the tilted frame.

    Stated as a property of whatever the artifact currently holds rather than as
    a pinned number, so it keeps working after the next rebuild moves the
    decimals.
    """
    bt = _load(BACKTEST)
    frames = (bt.get("accuracy") or {}).get("head_to_head_by_frame") or {}
    if not frames:
        pytest.skip("source_backtest.json predates the M-1 frame split")
    pre = frames.get("predebut")
    if pre:
        assert "tilted TOWARD eFV" in (pre.get("basis_note") or ""), (
            "the pre-debut frame must keep disclosing which way it tilts")
    hh = (bt.get("accuracy") or {}).get("head_to_head_verdict") or {}
    if hh.get("xfv_beats"):
        assert hh.get("basis") == "pooled_efv_common_vintage_matched", (
            "a 'beats consensus' verdict was published off a tilted frame")


def test_every_frame_is_scored_on_identical_rows_within_itself():
    """Each frame re-scores EVERY rater on that frame's rows.

    A frame that scored eFV on one population and the consensus on another would
    reintroduce the 2026-08-07 defect that `pooled_efv_common` exists to fix.
    """
    bt = _load(BACKTEST)
    acc = bt.get("accuracy") or {}
    for key in ("pooled_efv_common", "pooled_efv_common_predebut",
                "pooled_efv_common_vintage_matched"):
        blk = acc.get(key)
        if not blk:
            continue
        ns = {r: (v or {}).get("n") for r, v in blk.items() if isinstance(v, dict)}
        ns = {r: n for r, n in ns.items() if n is not None}
        assert len(set(ns.values())) == 1, f"{key} scored raters on different rows: {ns}"
