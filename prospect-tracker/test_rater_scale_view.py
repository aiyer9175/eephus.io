"""A-CLAIM-13: the rater scale view, and the controls that make it readable.

WHAT THIS LANE MEASURES. Each rater's ordering inside side x base-year blocks, beside its
pooled ordering on the same rows. The gap is how much of a rater's published Spearman is
block scale rather than within-cohort skill.

THE THREE MISTAKES THESE TESTS EXIST FOR, and the third was made:

  1. COMPARING TWO POPULATIONS. The pooled leg must be computed on the rows the block leg
     KEPT, or the delta mixes the normalization with the blocks that fell under the
     minimum.
  2. PUBLISHING FOUR NUMBERS SIDE BY SIDE WITH NO FLOOR. Four block rhos next to each other
     is a comparison whether or not it is labelled one.
  3. TRUSTING A ONE-DRAW PLACEBO. The first build permuted the block labels ONCE, and that
     single draw said the transform accounted for all of eFV's loss and none of the
     raters'. At 200 permutations that reading reverses. A placebo with no distribution
     cannot tell a mean from a draw.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "source_backtest.json"
DOC = ROOT / "docs" / "efv-2026-09-06" / "RATER_SCALE_VIEW.md"
RATERS = ("fangraphs", "mlb_pipeline", "prospx_consensus", "xfv")


@pytest.fixture(scope="module")
def view():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    v = (json.loads(ART.read_text(encoding="utf-8"))
         .get("accuracy", {}).get("per_year_scale_view"))
    if not v or v.get("status"):
        pytest.skip(f"scale view not computed: {(v or {}).get('status')}")
    return v


# --------------------------------------------------------------------------
# It is a view, and nothing reads it
# --------------------------------------------------------------------------

def test_it_is_marked_an_additional_view_that_changes_no_verdict(view):
    assert view["view"] == "additional"
    assert view["changes_no_verdict"] is True


def test_it_sits_beside_per_year_as_registered():
    if not ART.exists():
        pytest.skip("artifact not built")
    a = json.loads(ART.read_text(encoding="utf-8"))["accuracy"]
    assert "per_year" in a and "per_year_scale_view" in a


def test_no_served_surface_reads_the_scale_view():
    """The block rho is a narrower statistic than the pooled one and would be
    read as a head-to-head if it ever reached a page. Nothing may render it."""
    # The key, not the statistic name. `efv_model.block_rho_eval` is a different
    # and older lane (consensus against the blend, within base year) that has
    # every right to the phrase, and grepping for `block_rho` would flag it and
    # teach the next reader to ignore this test.
    hits = []
    allowed = {"source_backtest.py"}
    for f in list(ROOT.glob("assets/*.js")) + list(ROOT.glob("*.py")):
        if f.name in allowed or f.name.startswith("test_"):
            continue
        try:
            if "per_year_scale_view" in f.read_text(encoding="utf-8", errors="ignore"):
                hits.append(f.name)
        except OSError:
            pass
    assert not hits, f"the scale view is being read outside the backtest: {hits}"


# --------------------------------------------------------------------------
# The two legs sit on the same rows
# --------------------------------------------------------------------------

def test_the_pooled_leg_is_on_the_rows_the_block_leg_kept(view):
    """If a block fell under the minimum its rows leave BOTH legs. A pooled leg
    computed on all rows would mix the normalization with the population."""
    for r in RATERS:
        c = view["per_rater"][r]
        assert c["pooled_rho_same_rows"] is not None
        assert c["pooled_rho_all_rows"] is not None
    if not view["blocks_dropped_below_min"]:
        for r in RATERS:
            c = view["per_rater"][r]
            assert c["pooled_rho_same_rows"] == c["pooled_rho_all_rows"], (
                "no block was dropped, so the two pooled values must agree; "
                "they do not, which means the legs are not on the same rows")


def test_every_rater_carries_a_floor_and_a_call(view):
    for r in RATERS:
        c = view["per_rater"][r]
        assert (c["floor_E_cond_in_run"] or {}).get("mde95") is not None
        assert c["call_E_cond_in_run"]


def test_the_delta_is_block_minus_pooled_and_the_arithmetic_holds(view):
    for r in RATERS:
        c = view["per_rater"][r]
        want = round(c["block_rho"] - c["pooled_rho_same_rows"], 5)
        assert abs(c["delta_block_minus_pooled"] - want) <= 2e-4, (
            f"{r}: the published delta does not equal block minus pooled")


# --------------------------------------------------------------------------
# The gaps the view displays are floored
# --------------------------------------------------------------------------

def test_every_gap_the_view_displays_carries_a_floor(view):
    gaps = view["gaps_on_this_view"]
    for r in RATERS:
        if r == "xfv":
            continue
        g = gaps[f"xfv_vs_{r}"]
        assert (g["floor_E_cond_in_run"] or {}).get("mde95") is not None
        assert g["call_E_cond_in_run"]


def test_the_efv_versus_consensus_gap_does_not_resolve_on_this_view(view):
    """The registered expectation's surviving half. If this ever clears it is a
    real change to what the platform may say and must be confirmed first, not
    absorbed by editing this test."""
    f = view["gaps_on_this_view"]["xfv_vs_prospx_consensus"]["floor_E_cond_in_run"]
    assert abs(f["point_delta"]) <= f["mde95"], (
        f"eFV vs the consensus now CLEARS on the block view ({f['point_delta']} "
        f"against {f['mde95']}). That contradicts the registration and it would "
        "change a published claim from a description into a direction.")


def test_the_sign_flip_between_the_two_instruments_is_still_there(view):
    """The most useful thing this lane found: the eFV-vs-consensus gap changes
    SIGN depending on whether block scale is removed, and neither reading
    resolves. If both instruments ever agree in sign, the published copy should
    be revisited."""
    a = json.loads(ART.read_text(encoding="utf-8"))["accuracy"]
    pooled = a["head_to_head_by_frame"]["vintage_matched"]["delta"]
    block = (view["gaps_on_this_view"]["xfv_vs_prospx_consensus"]
             ["floor_E_cond_in_run"]["point_delta"])
    assert pooled * block < 0, (
        f"the pooled cell ({pooled}) and the block view ({block}) now agree in "
        "sign. That is a change in the evidence and the accuracy copy should be "
        "re-read before this test is updated.")


# --------------------------------------------------------------------------
# The placebo
# --------------------------------------------------------------------------

def test_the_placebo_is_a_distribution_not_a_single_draw(view):
    """THE MISTAKE THIS CATCHES was made. One permutation said the transform
    accounted for all of eFV's loss and none of the raters'; 200 say it costs
    every column about the same."""
    pl = view["placebo_permuted_blocks"]
    assert pl["B"] >= 100, "a placebo below 100 draws cannot separate a mean from noise"
    for r in RATERS:
        c = pl["per_rater"][r]
        assert c["B_used"] >= 100
        assert c["sd"] > 0
        assert len(c["ci95"]) == 2


def test_the_placebo_preserves_the_block_sizes(view):
    assert view["placebo_permuted_blocks"]["block_sizes_preserved"] is True


def test_every_rater_is_reported_net_of_its_own_placebo(view):
    """A single pooled placebo constant would subtract the wrong amount from at
    least one column, because a coarse 20-to-80 grade and a continuous model
    number are not tied to the same degree."""
    for r in RATERS:
        c = view["per_rater"][r]
        assert c["placebo_mean_delta"] is not None
        want = round(c["delta_block_minus_pooled"] - c["placebo_mean_delta"], 5)
        assert abs(c["delta_net_of_placebo"] - want) <= 2e-4


def test_the_three_raters_clear_the_placebo_and_efv_does_not(view):
    """The finding. If this ever inverts, the lane's whole claim inverts with it."""
    for r in ("fangraphs", "mlb_pipeline", "prospx_consensus"):
        assert view["per_rater"][r]["observed_inside_placebo_band"] is False, (
            f"{r} now sits INSIDE its permutation band, so its block-scale loss "
            "is no longer separable from what the transform costs by itself")
    # DS-02 (2026-09-25): the served eFV V2 grade is the consensus value at the order
    # rank inside (side, year), so it carries the block scale by construction (bug B5's
    # repair). The registration below was made on eFV v1.
    import efv_v2_serve
    if (efv_v2_serve.enabled()
            and view["per_rater"]["xfv"]["observed_inside_placebo_band"] is False):
        pytest.xfail("eFV V2 sits outside its placebo band: its grade is drawn from the "
                     "consensus values of each (side, year) group, so it carries block "
                     "scale by construction; the registration was made on eFV v1")
    assert view["per_rater"]["xfv"]["observed_inside_placebo_band"] is True, (
        "eFV now sits OUTSIDE its permutation band, which would mean eFV carries "
        "block scale too. Confirm before anything is said about the difference.")


# --------------------------------------------------------------------------
# The attribution
# --------------------------------------------------------------------------

def test_both_attribution_passes_ran(view):
    for tag in ("side_only", "year_only"):
        blk = view["attribution"][tag]
        assert not blk.get("status"), f"{tag}: {blk.get('status')}"
        assert set(blk["per_rater"]) == set(RATERS)


def test_the_effect_is_the_base_year_and_not_the_side(view):
    """The half of this lane anybody would have guessed was doing the work is the
    side scale, and it buys nothing measurable. Recorded as a test so a future
    frame that reverses it has to be noticed."""
    side = view["attribution"]["side_only"]["per_rater"]
    year = view["attribution"]["year_only"]["per_rater"]
    for r in RATERS:
        f = (side[r]["floor_E_cond_in_run"] or {})
        assert abs(side[r]["delta_block_minus_pooled"]) <= f["mde95"], (
            f"{r}: the SIDE scale now resolves on its own "
            f"({side[r]['delta_block_minus_pooled']} against {f['mde95']}). That "
            "is a new finding and the doc says the opposite; confirm it before "
            "the copy is changed.")
    for r in ("fangraphs", "mlb_pipeline", "prospx_consensus"):
        f = (year[r]["floor_E_cond_in_run"] or {})
        assert abs(year[r]["delta_block_minus_pooled"]) > f["mde95"], (
            f"{r}: the base-year scale no longer resolves, which is the lane's "
            "central measurement")


def test_the_side_only_pass_has_exactly_two_blocks(view):
    assert view["attribution"]["side_only"]["blocks_kept"] == 2


# --------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------

def test_the_gate_document_records_the_refuted_prediction():
    assert DOC.exists(), f"{DOC} is missing"
    txt = DOC.read_text(encoding="utf-8")
    assert "REFUTED" in txt, (
        "the registration predicted -0.0113 at 0.93x floor and the measurement "
        "is about three times that and resolves; a refuted prediction is written "
        "down, not edited")
    assert "receipt, not a claim" in txt, (
        "the eFV vs FanGraphs cell clears its floor on this view and the doc must "
        "say it is descriptive under the alpha-spending clause")


def test_the_gate_document_records_the_one_draw_placebo_mistake():
    txt = DOC.read_text(encoding="utf-8").lower()
    assert "single-draw placebo is not a placebo" in txt


def test_the_mechanism_was_marked_untested_and_then_corrected():
    """It was written down as a hypothesis, which is why A-CLAIM-3 could go and
    kill it. The doc has to carry BOTH halves: a reader who finds only the
    hypothesis would take it for a live explanation."""
    txt = DOC.read_text(encoding="utf-8")
    assert "hypothesis and has not been tested" in txt, (
        "the exposure explanation is a story about the numbers, not a "
        "measurement, and must be labelled as one")
    assert "falsified the same day" in txt, (
        "A-CLAIM-3 tested the exposure explanation and it lost; the correction "
        "belongs in this doc, not only in the one that ran the test")
