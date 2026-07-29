# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""THE GUARD: no shipped eFV feature may carry a fitted sign that contradicts its
DECLARED monotone direction without that contradiction being acknowledged in writing.

This is the regression test for the 2026-07-25 owner bugs (the Arias "punished for
contact" card and the Sloan "penalized for being 20 in Double-A" card). Both were the
same latent class: `efv_model._FEATURES_HIT` / `_FEATURES_PIT` DECLARE a monotone
direction per feature, that declaration binds only the LightGBM challenger (an
eval-only model), and the shipped ridge was free to fit the opposite sign with nothing
checking. Four shipped features were fitted against their own declaration and had been
for months.

The tests below are CORRECTNESS tests, not accuracy tests. They do not claim any rank
gain and no rank claim is required to justify them: a module that states an intent the
served fit contradicts is simply wrong about itself, and the per-prospect explainer
reads its direction off that fit.

To make a failure go away, do ONE of:
  * correct the declaration (0 = "no directional claim" is the right declaration for a
    measured suppressor - see efv_sign_audit.audit's classification rules), or
  * add an entry to efv_sign_audit.ACKNOWLEDGED citing the evidence artifact.
Do NOT relax the rule.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import efv_sign_audit as sa

_MATRICES = [Path(__file__).resolve().parent / "data" / n
             for n in ("xfv_hitter_matrix.json", "xfv_pitcher_matrix.json")]

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in _MATRICES),
    reason="eFV training matrices absent (Pass-1 build has not run)")


# ---------------------------------------------------------------------------
# the rule itself (pure logic, no data)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("declared,fitted,expected", [
    (-1, +0.5, True),    # declared down, fitted up
    (+1, -0.5, True),    # declared up, fitted down
    (-1, -0.5, False),
    (+1, +0.5, False),
    (0, +0.5, False),    # 0 = no directional claim, can never contradict
    (0, -0.5, False),
    (-1, 0.0, False),    # an exactly-zero weight asserts nothing
])
def test_contradiction_rule(declared, fitted, expected):
    assert sa.contradicts(declared, fitted) is expected


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("side", ["hit", "pit"])
def test_flagship_fitted_signs_match_declarations(side):
    """Every feature in the SHIPPED flagship set, fitted on the SERVED production pool
    (the same fit efv_score._fit_production serves), must agree with its declaration."""
    bad = {k: v for k, v in sa.contradictions(side).items()
           if ("flagship", side, k) not in sa.ACKNOWLEDGED}
    assert not bad, (
        "shipped eFV feature(s) fitted AGAINST their declared monotone direction "
        f"(side={side}): " + json.dumps(bad, indent=1) +
        "\nFix the declaration in efv_model._FEATURES_* (0 = no directional claim, "
        "the correct declaration for a measured suppressor) or acknowledge it in "
        "efv_sign_audit.ACKNOWLEDGED with its evidence artifact.")


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_provisional_fitted_signs_match_declarations(side):
    """Same guard for the efv_ungraded no-FV sets. Those sets are bare key lists, so
    they inherit the flagship declaration for shared keys; a key that is declared
    NOWHERE is caught by test_provisional_features_are_declared below."""
    rows = sa.audit_provisional(side)
    bad = {k: v for k, v in rows.items()
           if v["contradiction"] and ("provisional", side, k) not in sa.ACKNOWLEDGED}
    assert not bad, (
        "provisional (no-FV) eFV feature(s) fitted AGAINST their declared direction "
        f"(side={side}): " + json.dumps(bad, indent=1))


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_provisional_features_are_declared(side):
    """A served model may not carry a feature whose intended direction is stated
    nowhere - that is how peak_obp_rel / iso_rel / era_rel shipped unchecked."""
    missing = {k for k, v in sa.audit_provisional(side).items()
               if v["declared"] is None} - sa.UNDECLARED_OK[side]
    assert not missing, (
        f"provisional {side} features with no declared monotone direction anywhere: "
        f"{sorted(missing)}. Declare them (0 is a legitimate declaration).")


def test_acknowledged_entries_are_not_stale():
    """An ACKNOWLEDGED entry that no longer contradicts must be REMOVED, otherwise the
    allowlist quietly grows into a place where a real regression can hide."""
    live = set()
    for side in ("hit", "pit"):
        live |= {("flagship", side, k) for k in sa.contradictions(side)}
        live |= {("provisional", side, k)
                 for k, v in sa.audit_provisional(side).items() if v["contradiction"]}
    stale = set(sa.ACKNOWLEDGED) - live
    assert not stale, f"stale ACKNOWLEDGED sign entries (no longer contradict): {sorted(stale)}"


def test_acknowledged_entries_cite_evidence():
    for key, note in sa.ACKNOWLEDGED.items():
        assert note and len(note) > 20, f"ACKNOWLEDGED[{key}] must cite its evidence"
