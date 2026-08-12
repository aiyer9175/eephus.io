# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""E2a, the per-side calibration audit, and the two properties that make it
worth citing.

The lane exists because of one owner constraint: source bias is judged against
REALIZED OUTCOMES, never against another source's grade. "eFV puts 8 pitchers in
its top 100 and the consensus puts 27" is not evidence about either of them.
These tests hold the two things that would quietly turn the audit back into a
source-versus-source comparison or into a survivor-biased one.

Pre-registration: docs/efv-2026-08-12/SIDE_CALIBRATION_GATE.md.
Artifact: data/xfv_side_calibration_eval.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ART = ROOT / "data" / "xfv_side_calibration_eval.json"


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("data/xfv_side_calibration_eval.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


def test_busts_are_in_the_frame(art):
    """Drop the busts and this measures survivors only.

    The bust rate differs by side (hitters 50.6%, pitchers 45.7%), so scoring
    only the players who reached the majors would compare two differently
    filtered populations and call the difference calibration.
    """
    basis = art["basis"]
    assert "bust" in basis["frame"], basis["frame"]
    assert basis["n"] > 4000, (
        f"pool is {basis['n']} rows; the resolved pool with busts included is "
        "about 4,600. A pool near 2,400 means the busts were dropped and the "
        "read is survivor-biased.")
    assert basis["n"] == basis["n_hit"] + basis["n_pit"]


def test_the_reference_is_outcomes_and_the_artifact_says_so(art):
    """The one claim the lane may not make is 'the other source disagrees'."""
    ref = art["basis"]["reference"].lower()
    assert "realized" in ref and "war" in ref, ref
    assert "no claim" in ref or "never" in ref, (
        "the basis block does not record that no claim here is made by "
        "comparing one source's grade to another's, which is the constraint "
        "this entire lane was built around")


def test_thin_cells_are_reported_but_never_scored(art):
    """A 6-row cell must not become a finding.

    The top pitcher cells are thin BY CONSTRUCTION (0 rows at eFV 60, 6 at 55),
    and that emptiness is the finding. Scoring them would manufacture a huge
    gap out of a handful of players.
    """
    floor = art["basis"]["min_cell"]
    for grader, blk in art["m1_realized_war_by_band"].items():
        for band, c in blk["cells"].items():
            thin = c["n_hit"] < floor or c["n_pit"] < floor
            if thin:
                assert c["scored"] is False, f"{grader} {band} scored a thin cell"
                assert c["resolvable"] is False
                assert c["ci95"] is None, (
                    f"{grader} {band} carries an interval for an unscored cell")


def test_a_gap_inside_its_interval_is_not_a_finding(art):
    """Same demotion the rest of the site uses: an unfloored gap is a tie."""
    for grader, blk in art["m1_realized_war_by_band"].items():
        for band, c in blk["cells"].items():
            if not c["scored"]:
                continue
            lo, hi = c["ci95"]
            spans_zero = lo <= 0 <= hi
            assert c["resolvable"] is (not spans_zero), (
                f"{grader} {band}: interval [{lo}, {hi}] and resolvable="
                f"{c['resolvable']} disagree")
            if spans_zero:
                assert "not resolvable" in c["verdict"], c["verdict"]


def test_the_forecast_check_covers_both_sides(art):
    """M2 rules out the simplest explanation and must not go missing.

    If the pitcher WAR forecast were badly biased, the grade map would not be
    the thing to fix, and the audit would be pointing at the wrong layer.
    """
    f = art["m2_per_side_forecast"]
    for side in ("H", "P"):
        assert side in f, f"m2 is missing side {side}"
        assert f[side]["bias_pred_minus_real"] is not None
        assert f[side]["slope_real_on_pred"] is not None
