# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Three tool gates sit on a knife edge and decide what a third of the board reads.

WHAT THIS GUARDS (found 2026-08-06 while scoping Lane C3). `efv_tools._oos_validate`
decides whether a tool's MiLB-production blend is applied, using a bare strict
inequality:

    "validated": bool(br > gr)

No minimum detectable effect, no bootstrap, no confidence interval, no margin.
It is the only thing standing between a tool eFV being grade-only and being a
blend, and 3,007 of the 9,382 rows in data/xfv.json carry tool_xfv.

Measured margins on 2026-08-06:

    hit        +0.00790   validated   <- applied to served grades
    game_pwr   -0.00390   not
    speed      +0.00000   not         <- an EXACT TIE, resolved by `>`
    fb         +0.06370   validated
    cmd        -0.07180   not

Three of five are inside a hundredth of the line and one is a coin flip. A
routine rebuild on new data can flip any of them, and nothing anywhere would say
so: the board would simply re-grade.

WHY THE RULE IS NOT CHANGED HERE. Raising the bar to a real MDE would re-grade
served rows, and doing that without a measurement behind it is the move this
codebase exists to refuse. So the margin is published and this file alarms on a
flip. Fixing the gate properly is a pre-registered change of its own.

WHAT THESE TESTS HOLD
  1. Every gate publishes its margin, so the fragility is legible in the artifact
     rather than only in someone's head.
  2. The recorded verdicts do not change silently. A flip fails here first.
  3. A gate decided on an exact tie is called out, because `>` versus `>=` is
     doing real work at zero and neither choice is defensible on evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
ART = DATA / "xfv_tools.json"

pytestmark = pytest.mark.skipif(not ART.exists(), reason="tool artifact absent")

#: The verdicts as measured on 2026-08-06. This is a TRIPWIRE, not a target: if a
#: rebuild moves one, that is a real change to what the board serves and it needs
#: a human decision, not a quiet update to this dict.
RECORDED = {
    "hit":      {"validated": True,  "margin": 0.0079},
    "game_pwr": {"validated": False, "margin": -0.0039},
    "speed":    {"validated": False, "margin": 0.0},
    "fb":       {"validated": True,  "margin": 0.0637},
    "cmd":      {"validated": False, "margin": -0.0718},
}

KNIFE_EDGE = 0.01


def _tools():
    d = json.loads(ART.read_text(encoding="utf-8"))
    return (d.get("meta") or {}).get("modeled_tools") or {}


def test_every_gate_publishes_its_margin():
    tools = _tools()
    assert tools, "no modeled tools in the artifact"
    for name, t in tools.items():
        oos = t.get("oos_validation") or {}
        assert "margin" in oos, (
            f"{name}: the gate decides served grades on blend_rho > grade_rho and "
            "must publish the margin, or nobody can see how close it was")
        assert "knife_edge" in oos


def test_no_gate_verdict_flipped_silently():
    """THE TRIPWIRE. A flip re-grades part of the served board."""
    tools = _tools()
    moved = []
    for name, want in RECORDED.items():
        oos = (tools.get(name) or {}).get("oos_validation") or {}
        got = oos.get("validated")
        if got is None:
            moved.append(f"{name}: gate has disappeared from the artifact")
        elif bool(got) != want["validated"]:
            moved.append(
                f"{name}: validated {want['validated']} -> {got} "
                f"(margin was {want['margin']}, now {oos.get('margin')})")
    assert not moved, (
        "a tool gate flipped, which re-grades served rows:\n  "
        + "\n  ".join(moved)
        + "\n\nThis is not a test to update casually. Decide whether the new "
          "verdict is right, then update RECORDED with the reason.")


def test_the_knife_edge_gates_are_still_the_ones_we_know_about():
    """A NEW gate arriving inside the band is worth knowing about before it
    flips, not after."""
    tools = _tools()
    known = {n for n, w in RECORDED.items() if abs(w["margin"]) < KNIFE_EDGE}
    now = {n for n, t in tools.items()
           if abs(((t.get("oos_validation") or {}).get("margin") or 1.0)) < KNIFE_EDGE}
    surprise = now - known
    assert not surprise, (
        f"gates newly inside +/-{KNIFE_EDGE} of the line: {sorted(surprise)}. "
        "They can flip on any rebuild and re-grade the board.")


def test_an_exact_tie_is_called_out():
    """`speed` sits at exactly 0.00000, so the verdict is decided purely by the
    choice of `>` over `>=`. Neither is defensible on evidence, and the tie must
    not be mistaken for a measured negative."""
    oos = (_tools().get("speed") or {}).get("oos_validation") or {}
    if oos.get("margin") == 0.0:
        assert oos.get("validated") is False, (
            "an exact tie must resolve the conservative way, to grade-only")
        assert oos.get("knife_edge") is True


def test_the_served_footprint_is_what_we_think_it_is():
    """The stakes. If this number grows a lot, the knife-edge gates matter more,
    not less."""
    xfv = DATA / "xfv.json"
    if not xfv.exists():
        pytest.skip("xfv.json absent")
    d = json.loads(xfv.read_text(encoding="utf-8"))
    bp = d.get("by_player") or {}
    n = sum(1 for v in bp.values() if isinstance(v, dict) and v.get("tool_xfv") is not None)
    assert n > 0, "no served row carries tool_xfv; has the join broken?"
    assert n < len(bp), "every row carrying tool_xfv would be a change worth noticing"
