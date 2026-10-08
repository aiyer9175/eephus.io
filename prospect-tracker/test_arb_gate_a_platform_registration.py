# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Registration pins for the GATE A platform-season amendment
(docs/ARBITRATION_GATE.md section 13, registered 2026-10-08).

The amendment was committed alone before the re-run it governs. These pins
hold the frame, the protocol and the served response to each verdict in
place, so none of them can be edited after the result is visible. Results
are pinned elsewhere (test_arb_gate_a_platform.py), on purpose.
"""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).parent / "docs" / "ARBITRATION_GATE.md"


def _sec13() -> str:
    doc = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    head = "## 13. GATE A amendment (registered 2026-10-08, before any re-run)"
    assert head in doc, "section 13 is missing"
    body = doc.split(head, 1)[1]
    return body.split("\n## ", 1)[0]


def test_the_frame_is_the_platform_season():
    s = _sec13()
    assert "the platform season is `p = s - 1`" in s
    assert "`war3` is WAR in p, p-1 and p-2; `career_war` runs through p inclusive" in s
    assert "The deflator is NOT changed." in s


def test_the_protocol_is_section_4_unchanged():
    s = _sec13()
    assert "`tools/arb_gate_a.py --write --B 1200 --frame platform`" in s
    assert "seed 20260808" in s
    assert "`award_frame_same_day_twin`" in s


def test_each_verdict_has_a_served_response_fixed_in_advance():
    s = _sec13()
    for clause in ("**arb-1 PASS.**", "**arb-1 NULL.**",
                   "**arb-2 and later, PASS or NULL.**",
                   "**The 2026-08-09 block stays as a labelled HINDCAST.**"):
        assert clause in s, clause
    assert "`hindcast_2026_08_09_award_frame`" in s
