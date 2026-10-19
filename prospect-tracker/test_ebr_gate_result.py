# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 gate RESULT pins (docs/ebr-2026-09-30/EBR_GATE.md part 12).

Part 12.1 holds the eBR outcome look (parts 5 and 6), run once on 2026-10-19 by
tools/ebr_gate.py as an OWNER-WAIVED EARLY READ (owner EW3-5). This file pins that
result so it cannot be edited after the fact. It lives apart from
test_ebr_gate_registration.py on purpose: a result pin that lives beside a
criterion pin invites editing the criterion to match the result (the reason
test_arb_gate_c2_registration.py gives). Parts 12.2 and 12.3 (the skill look and
its holdout) stay asserted EMPTY by the registration pin until their own runs,
which extend this file.

No correlation against runs or wins is pinned here; those stay in part 12.1 and
the preview look block only (EBR_GATE.md parts 5.3 and 5.10).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _part_12_1() -> str:
    doc = _doc()
    i = doc.index("### 12.1 The outcome look (parts 5 and 6)")
    return doc[i:doc.index("### 12.2 The skill look (parts 9.5 and 9.6)", i)]


def test_part_12_1_holds_exactly_one_run_dated_with_its_commit_and_the_waiver():
    sec = _part_12_1()
    assert sec.count("`python -u tools/ebr_gate.py` at") == 1, "the outcome look runs once"
    assert ("**2026-10-19, `python -u tools/ebr_gate.py` at `4924a5eb`, OWNER-WAIVED EARLY READ "
            "(owner EW3-5, 2026-10-14).**") in sec
    assert sec.count("eBR OUTCOME LOOK 2026-10-19 at 4924a5eb") == 1
    assert "EMPTY." not in sec


def test_the_inputs_it_read_are_stamped_before_any_statistic():
    sec = _part_12_1()
    vint = sec.index("fWAR vintage 2026-10-02-57bf90f7143e sha256 "
                     "c4de5ca2e4a1492167f2a47666503112c916a67dcfd38389de39f910187550fa")
    bref = sec.index("Baseball-Reference frame (cached, never fetched) sha256 "
                     "e9571c428cb4db444e4b8214bb9adc5834925529e7d10db4271993f79fc3fd55")
    assert vint < bref < sec.index("LEG E (5.2)")
    assert "substrate rows the record no longer reproduces, per season: {'2018': 0, '2019': 0, '2021': 0" in sec
    assert "FRAME (5.1): 1181 runner-pairs, 475 players" in sec
    assert "rows dropped for a missing series: none; vintage PA differing from the official line on 0" in sec


def test_leg_e_its_twin_and_its_guards():
    sec = _part_12_1()
    floors = sec.index("floors Leg E: bootstrap sd 0.0244, half-width 0.0402")
    leg = sec.index("Leg E: mean rho E +0.4449, mean rho B +0.6499, d -0.2050, interval [-0.2452, -0.1648], "
                    "disposition RESOLVED_LOSS")
    assert floors < leg, "the floors print before the estimate"
    assert "Leg E twin: mean rho E -0.0234, mean rho B +0.6499, d -0.6734" in sec
    assert re.search(r"Leg E twin: [^\n]*disposition RESOLVED_LOSS", sec)
    assert "frame U d -0.1746; club changers d -0.2089" in sec
    assert re.search(r"LEG T \(5\.3\): 240 club-seasons; [^\n]*passes True", sec)


def test_the_dp_leg():
    sec = _part_12_1()
    assert ("E-DP: mean rho G +0.4182, mean rho R +0.4909, d -0.0727, interval [-0.1196, -0.0258], "
            "disposition RESOLVED_LOSS") in sec
    assert re.search(r"E-DP twin: [^\n]*disposition RESOLVED_LOSS", sec)
    assert "E-DP frame U d_DP -0.0730; club changers d_DP -0.0359" in sec
    assert "floors DP-1: bootstrap sd 0.0283, half-width 0.0466" in sec
    assert "DP-1: mean rho of eGDP per opportunity +0.4211; estimate - 1.645 sd +0.3745; floor clears True" in sec
    assert "DP-1 passes True (the permuted eGDP must fail it: it fails)" in sec
    assert re.search(r"DP-2: [^\n]*passes True", sec)


def test_reliability_flags_and_bem_plus():
    sec = _part_12_1()
    for part in ("SB runs", "XB runs", "DP runs", "eBR", "sb", "pk", "xb_adv", "xb_oob", "dp"):
        assert re.search(rf"^  {re.escape(part)}: \[[^\n]*\]; NOISE False\r?$", sec, re.M), part
    assert "NOISE True" not in sec
    assert "BEM+ CONSTANTS (5.8, fit before any gate statistic, frozen here): SB k 5889.6" in sec
    assert sec.index("BEM+ CONSTANTS") < sec.index("LEG E (5.2)"), "BEM+'s constants are fit first"
    assert '"pass": false' in sec and '"twin_fails": true' in sec


def test_what_part_6_licenses():
    flat = _flat(_part_12_1())
    assert ("- candidate part 1: not admitted (Leg E RESOLVED_LOSS, Leg T pass True, d frame U -0.1746, "
            "d club changers -0.2089); eWAR v3 keeps FanGraphs' BsR") in flat
    assert ("- candidate part 2: not admitted (E-DP RESOLVED_LOSS, DP-1 True, DP-2 True); eWAR v3 carries no "
            "double-play part from 2016 on") in flat
    assert "- copy: repeats less from one season to the next than FanGraphs' BsR on the same runners" in flat
    assert ("- dp copy: repeats less from one season to the next than Baseball-Reference's double-play runs "
            "on the same runners") in flat
    assert "- dp repeatable word: allowed (DP-1 passes)" in flat
    assert "- bem_plus: not served (FAIL)" in flat
    assert "- noise flags: none" in flat


def test_the_owner_waived_early_read_note_follows_the_last_section():
    doc = _doc()
    note = "**Dated note, 2026-10-19: the outcome look of part 12.1 is an OWNER-WAIVED EARLY READ.**"
    assert doc.count(note) == 1
    assert doc.index(note) > doc.index("licenses under part 1's recorded answers.")
    flat = _flat(doc[doc.index(note):])
    assert "--owner-waived-early-read`, which lifts only part 7.2's date clauses" in flat
    assert "the look itself fetched nothing and read that cached copy as it stood" in flat
