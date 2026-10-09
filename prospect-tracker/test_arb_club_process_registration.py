# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Club arbitration process REGISTRATION pins (docs/ARBITRATION_GATE.md section 13).

Section 13 is the registration the plan calls "section 12" (parts 12a to 12d,
renumbered because section 12 holds the 2026-10-04 Spotrac roll-off record),
plus 13e, the one club term in the point award the owner asked for under
ARB-CLUB-2 (c). It was committed alone, before the tracker re-capture and
before any club label existed.

This file pins the criteria a later result could tempt someone to edit: the
section's presence and numbering map, the scored-winter rule (the 2024 to 2026
winters were read to write it and are never scored), the label rule and its
thresholds, the power precondition, the look order, and the scope of the
section 4 amendment. It pins no RESULT: results land in 13f and their own
artifact, pinned elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import arb_model as M

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "ARBITRATION_GATE.md"
HEADING = ("## 13. Club arbitration process: a width term on the award band "
           "and one term in the point award (pre-registered 2026-10-08)")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _section() -> str:
    doc = _doc()
    assert HEADING in doc, "section 13 (the plan's section 12) is missing"
    return doc[doc.index(HEADING):]


def _norm(s: str) -> str:
    return " ".join(s.split())


def test_section_13_exists_with_every_part_and_the_numbering_map():
    sec = _section()
    for head in ("### Read to write this",
                 "### 13a. Band calibration (the plan's 12a): named here, registered later",
                 "### 13b. Club-process width (the plan's 12b)",
                 "### 13c. What never moves",
                 "### 13d. The response, and the look order",
                 "### 13e. One club-process term in the point award, and the "
                 "amendment to section 4 (ARB-CLUB-2 (c))",
                 "### 13f. Results"):
        assert head in sec, f"part dropped out of the registration: {head}"
    flat = _norm(sec)
    assert "13b is the plan's 12b" in flat
    assert "means 13a or 13b" in flat


def test_section_12_was_not_edited_to_make_room():
    """The registration takes a new number; the 2026-10-04 record stands."""
    doc = _doc()
    assert "## 12. 2026-10-04: the 2026 Spotrac column roll-off and the section 10 pins" in doc
    assert doc.index("## 12. 2026-10-04") < doc.index(HEADING)


def test_the_scored_winter_rule():
    flat = _norm(_section())
    assert "**Scored cases: only winters captured after this commit.**" in flat
    assert ("The January 2027 exchange-day capture and the February 2027 "
            "post-hearing capture are the first") in flat
    assert "No case from the 2024, 2025 or 2026 winters is scored, ever" in flat
    assert "were read to write this section" in flat
    assert "never scored cases" in flat
    # 13e scores the same frame.
    assert "The 2024 to 2026 winters may train beta and are never scored." in flat


def test_the_label_rule_and_its_thresholds():
    flat = _norm(_section())
    assert "**The label, exactly as FAA-4 defines it.**" in flat
    assert "(exchanged >= 2)" in flat
    assert "(settled after the exchange = 0)" in flat
    assert "over the captured winters strictly before W" in flat
    assert ("**Thresholds, fixed at this commit.** exchanged >= 2; settled after "
            "the exchange = 0; winters strictly before the case's.") in flat
    assert "never to the season-end club in `arb_history`" in flat


def test_the_power_precondition_comes_before_the_pass_rule():
    sec = _section()
    flat = _norm(sec)
    assert "at least 62 scoreable cases across the scored winters before the read is allowed" in flat
    assert "a coverage MDE95 of 0.10" in flat
    assert "Short of 62 the arm is a pre-committed NULL, the A6 single-season precedent." in flat
    b = sec[sec.index("### 13b."):sec.index("### 13c.")]
    assert b.index("**Power precondition, written first.**") < b.index("**Pass.**")


def test_the_look_order():
    """One look, in this order, fixed before any club label exists."""
    sec = _section()
    look = sec[sec.index("**Look order, fixed now.**"):sec.index("### 13e.")]
    steps = [
        "1. This registration (2026-10-08), committed alone.",
        "2. Q9_17 (FAA-3)",
        "3. Q9_18 (FAA-4)",
        "4. GATE C2 scored, then 13a registered by dated amendment (Q9_20)",
        "5. The January 2027 exchange-day capture",
        "6. After each February capture the scoreable labelled cases are COUNTED",
        "7. The one look:",
        "8. At that look 13b is scored only if step 4 shipped a calibrated band",
    ]
    pos = [look.find(s) for s in steps]
    assert all(p >= 0 for p in pos), dict(zip(steps, pos))
    assert pos == sorted(pos), "the look order was rearranged"
    flat = _norm(look)
    assert "no later than the February 2029 capture" in flat
    assert "recorded NULL without reading any outcome" in flat


def test_13a_is_named_and_13b_waits_on_it():
    flat = _norm(_section())
    assert "to follow by a dated amendment after GATE C2 is scored" in flat
    assert "Nothing in this section registers it." in flat
    assert "13b is recorded `NOT SCORED`, which is neither a pass nor a NULL" in flat


def test_the_section_4_amendment_admits_one_term_and_nothing_else():
    flat = _norm(_section())
    assert "admits exactly one club term, `club_file_and_trial`" in flat
    assert "no club identity or club fixed effect" in flat
    assert "The term never enters `CHAMPION_KEYS`" in flat
    assert "Until the re-run passes and the owner flips that flag, section 4 reads as written." in flat
    assert "**The GATE A re-run that must PASS before any serve.**" in flat
    assert "Section 4's ban on team effects stands in full." in flat


def test_no_club_process_key_reaches_the_champion_tuple():
    """13c, mechanically, for what exists today: the frozen tuple carries no
    club, team or process key. FAA-4 extends the banned-key test in
    test_arb_export.py to its own chip keys when it adds them."""
    for key in M.CHAMPION_KEYS:
        for frag in ("club", "team", "hearing", "filed", "exchange", "settle", "trial"):
            assert frag not in key, f"club-process key {key} reached CHAMPION_KEYS"
    assert "club_file_and_trial" not in M.CEILING_KEYS


def test_results_section_is_last():
    sec = _section()
    assert sec.index("### 13f. Results") > sec.index("### 13e.")
