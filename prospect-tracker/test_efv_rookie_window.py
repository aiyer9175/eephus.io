# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The rookie-window unlock, and the three things that make it safe.

Owner, 2026-08-12: "We should no longer lock eFVs after a prospect debuts, as
source updates to a prospect's grade should still affect their eFV after debut.
eFV drivers should not, as they should only factor in MiLB stats / metrics /
measurements."

So the grade moves and the explanation does not, and neither of them is allowed
to move the WAG baseline. Each of those is one test here, because each fails
silently: a re-narrated driver chip looks like a fresh insight, and a drifting
WAG baseline feeds a regression whose regressand already sees the future and
whose only containment is a pair of pinned lambdas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SRC = (ROOT / "efv_score.py").read_text(encoding="utf-8")
EXPORT = (ROOT / "efv_export.py").read_text(encoding="utf-8")
STORAGE = (ROOT / "storage.py").read_text(encoding="utf-8")

es = pytest.importorskip("efv_score")


def test_the_window_reuses_the_existing_eligibility_rule():
    """A second copy of the rookie rule is how two definitions drift apart."""
    assert "rookie_exhausted" in SRC, (
        "the window no longer reads rookie_exhausted, the flag stats.py already "
        "computes from the AB, IP, active-day and options gates")
    # Re-implementation has a signature: reading the raw counters or declaring
    # the thresholds here rather than consuming the flag stats.py already
    # publishes. A bare number is NOT the signature (this file legitimately
    # mentions a 70-130 index elsewhere), and testing for one was a false
    # positive on the first draft of this test.
    for invented in ("career_mlb_ab", "career_mlb_ip",
                     "ROOKIE_AB_THRESHOLD", "ROOKIE_IP_THRESHOLD"):
        assert invented not in SRC, (
            f"efv_score references {invented!r}: the eligibility rule has one "
            "owner in stats.py and re-deriving it here is the drift this test "
            "exists to prevent")


def test_the_flag_exists_and_the_fingerprint_reads_it():
    """Flipping the rule must trip the movement coordination gate.

    board_basis_fingerprint encodes the grade field, scale, map, roles, feature
    spec, stale basis and floor routing, and until this was added NONE of them
    could see which snapshot a graduate is scored at. The unlock moves the
    served grade for every still-eligible graduate, so the device has to see it.
    """
    assert hasattr(es, "GRADUATE_ROOKIE_WINDOW")
    assert "GRADUATE_ROOKIE_WINDOW" in STORAGE, (
        "storage.board_basis_fingerprint does not read the anchor rule, so "
        "flipping it would re-grade graduates without tripping the gate")
    import storage
    assert "gradanchor=" in storage.board_basis_fingerprint()


def test_the_drivers_are_explained_from_the_debut_anchor():
    """The grade may move past the debut; the explanation may not.

    The MiLB legs freeze on their own (milb_yr is pinned to the debut year), so
    the leg that would move is the consensus prior, which is precisely the one
    the owner ruled out of the driver chips.
    """
    assert "fac_feats" in SRC, "the driver feature row is gone"
    body = SRC[SRC.index("def run_backgrade("):]
    assert re.search(r"factors\s*=\s*_factors\(ridge,\s*fac_feats", body), (
        "_factors is no longer computed from the debut-anchored row, so a "
        "graduate's driver chips will re-narrate on every regen as new board "
        "points land")


def test_the_wag_baseline_is_pinned_to_the_at_debut_grade():
    """Not to whatever grade the join happens to serve."""
    assert "xfv_grade_at_debut" in SRC, "the scorer no longer emits it"
    # ASSIGNED, not merely mentioned. The first draft of this test matched the
    # field name anywhere in the file, which the explanatory comment above the
    # whitelist entry satisfies all by itself: deleting the actual assignment
    # left the test green. Match the assignment.
    assert 'e["xfv_grade_at_debut"] = ' in EXPORT, (
        "the field is not ASSIGNED in the _entry whitelist, so it never reaches "
        "data/xfv.json and storage silently falls back to the served grade. "
        "This whitelist has dropped a field before and the file says so.")
    wag = STORAGE[STORAGE.index("WAG baseline"):]
    wag = wag[:wag.index("_debuted_value")]
    assert "xfv_grade_at_debut" in wag, (
        "storage does not pin the WAG baseline to the at-debut grade; it reads "
        "whatever xfv_grade the join serves, which the unlock now moves")


def test_the_window_is_scoped_to_graduates_only():
    """Busts share run_backgrade and must keep their final-point anchor."""
    body = SRC[SRC.index("def run_backgrade("):]
    m = re.search(r"rookie_open = bool\((.*?)\)\n", body, re.S)
    assert m, "the window predicate is gone"
    assert 'kind == "debuted"' in m.group(1), (
        "the rookie window is not scoped to kind=='debuted'; bust rows share "
        "this function and anchor on their FINAL point by design")
