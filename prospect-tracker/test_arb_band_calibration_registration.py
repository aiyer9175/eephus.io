# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Award band calibration REGISTRATION pins (docs/ARBITRATION_GATE.md section 19).

Section 19 is the dated amendment that section 13a names: the plan's 12a, band
calibration from out-of-fold residual quantiles by rung and chain depth. It was
committed alone, after GATE C2 was scored (section 18) and before any producer,
quantile, coverage reading or interval score of any band existed.

This file pins what a later result could tempt someone to edit: the section's
presence and its link to 13a, section 13 left as committed, the forward-chained
quantile rule, the M12-4 floor on both bands, the power precondition written
before the pass rule, the pass rule, the NULL sentence and the look order. It
pins no RESULT.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "ARBITRATION_GATE.md"
HEADING = ("## 19. Section 13a amendment (registered 2026-10-09, before any 13a "
           "number exists): the award band from out-of-fold residual quantiles")
SEC13 = ("## 13. Club arbitration process: a width term on the award band "
         "and one term in the point award (pre-registered 2026-10-08)")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _section() -> str:
    doc = _doc()
    assert HEADING in doc, "section 19 (the plan's 12a, section 13a) is missing"
    return doc[doc.index(HEADING):]


def _part(sec: str, head: str, nxt: str | None) -> str:
    a = sec.index(head)
    return sec[a:sec.index(nxt)] if nxt else sec[a:]


def _norm(s: str) -> str:
    return " ".join(s.split())


PARTS = (
    "### 19a. What is calibrated, and why",
    "### 19b. Read to write this",
    "### 19c. The residuals",
    "### 19d. The calibrated band",
    "### 19e. Metric, power and floors",
    "### 19f. Pass rule",
    "### 19g. The response",
    "### 19h. What never moves",
    "### 19i. The look order",
    "### 19j. Results",
)


def test_section_19_exists_with_every_part_in_order():
    sec = _section()
    pos = [sec.find(p) for p in PARTS]
    assert all(p >= 0 for p in pos), dict(zip(PARTS, pos))
    assert pos == sorted(pos), "a part of the registration moved"


def test_it_is_the_amendment_13a_names_and_follows_gate_c2():
    doc = _doc()
    assert doc.index(SEC13) < doc.index(HEADING)
    assert doc.index("## 18. GATE C2 receipt") < doc.index(HEADING)
    flat = _norm(_section())
    assert "This section is the dated amendment 13a names." in flat
    assert "the plan's 12a is 13a, and this section registers it" in flat
    assert "GATE C2 scored (section 18, f6d2bb0d)" in flat


def test_section_13_stands_as_committed():
    """12b, 12c and 12d (13b to 13d) stay exactly as Q9_17a registered them;
    13a keeps its own words and the amendment is a new section."""
    doc = _doc()
    s13 = doc[doc.index(SEC13):doc.index("## 14. GATE K")]
    flat = _norm(s13)
    assert "### 13a. Band calibration (the plan's 12a): named here, registered later" in s13
    assert "Nothing in this section registers it." in flat
    assert "13b is recorded `NOT SCORED`, which is neither a pass nor a NULL" in flat
    assert "## 19." not in s13


def test_the_residuals_are_the_served_estimators_forward_chained():
    flat = _norm(_part(_section(), "### 19c.", "### 19d."))
    assert "The SERVED estimator as section 15d fixes it" in flat
    assert "Rung groups: arb-1, arb-2, arb-3 and later." in flat
    assert "Depth groups: 1, 2, 3 and deeper." in flat
    assert "is fit on class years up to Y - d only" in flat
    assert "no coverage is claimed for them" in flat


def test_quantiles_are_out_of_fold_and_the_floor_holds_on_both_bands():
    flat = _norm(_part(_section(), "### 19d.", "### 19e."))
    assert "the empirical 10th and 90th percentiles of the residuals whose target season is strictly before Y" in flat
    assert "A residual from winter Y never sets winter Y's band" in flat
    assert "fewer than 40 training residuals" in flat
    assert "**The M12-4 floor on both bands.**" in flat
    assert "The calibrated band and the fixed control are each floored at the season's league minimum" in flat
    assert "the board's and the salary path's" in flat


def test_metric_power_and_floors():
    sec = _section()
    e = _part(sec, "### 19e.", "### 19f.")
    flat = _norm(e)
    assert "the interval score** of the central 80% band (alpha = 0.20" in flat
    assert "paired against today's fixed band" in flat
    assert "must number at least 246 before any residual is read" in flat
    assert "Short of 246, 13a is a pre-committed NULL." in flat
    assert "B = 1000, seed 20261009" in flat
    assert "one-sided MDE95 (1.645 sd)" in flat
    assert "n_check >= 200" in flat
    # The power precondition is written before the pass rule.
    assert sec.index("**Power precondition, written first.**") < sec.index("### 19f. Pass rule")


def test_the_pass_rule():
    flat = _norm(_part(_section(), "### 19f.", "### 19g."))
    assert "All four, or 13a is a NULL:" in flat
    assert "by more than the one-sided MDE95 of the paired contrast" in flat
    assert "Pooled out-of-fold coverage of the scored rungs lies within 0.05 of 0.80" in flat
    assert "lies between 0.05 and 0.15" in flat
    assert "at least 62 scored rungs (the 13b count) has coverage within 0.10 of 0.80" in flat
    assert "The detection check in 19e passes." in flat


def test_the_response_and_the_null_sentence():
    flat = _norm(_part(_section(), "### 19g.", "### 19h."))
    assert "`ARB_BAND_CALIBRATED` (off by default" in flat
    assert "the flag flips only after the owner's answer" in flat
    assert "13a ships when its verdict is PASS and the flag is on" in flat
    assert ("*\"The calibrated award band is a NULL. Out-of-fold residual quantiles "
            "by rung and chain depth did not price arbitration awards better than "
            "the fixed band by more than the measured floor, or missed the 0.80 "
            "coverage target, or the frame held fewer than 246 scoreable rungs. "
            "The band stays the fixed spread and is not a calibrated interval.\"*") in flat
    assert "13b is then recorded `NOT SCORED`" in flat


def test_what_never_moves():
    flat = _norm(_part(_section(), "### 19h.", "### 19i."))
    for item in ("`arb_model.CHAMPION_KEYS`", "`projectable_keys`",
                 "every point award", "every `tot`", "section 13 itself",
                 "No club-process key enters this band"):
        assert item in flat, item


def test_the_look_order():
    look = _part(_section(), "### 19i.", "### 19j.")
    steps = [
        "1. This amendment (2026-10-09), committed alone with its pin test.",
        "2. The producer `tools/arb_band_calibration.py`",
        "3. The frame frozen and counted (19e)",
        "4. The one look:",
        "5. The response (19g) committed",
    ]
    pos = [look.find(s) for s in steps]
    assert all(p >= 0 for p in pos), dict(zip(steps, pos))
    assert pos == sorted(pos), "the look order was rearranged"
    flat = _norm(look)
    assert "Never on a registered look day." in flat
    assert "A re-score after the read is a new dated registration." in flat
    assert "run before the January 2027 exchange-day capture (13d step 5)" in flat


def test_results_are_last_and_empty_at_registration():
    sec = _section()
    assert sec.index("### 19j. Results") > sec.index("### 19i.")
    assert "Empty at registration." in _part(sec, "### 19j.", None)
