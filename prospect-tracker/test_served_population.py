"""A-CLAIM-12: the served population statement.

WHAT THIS PROTECTS. Every head-to-head cell in data/source_backtest.json compares
eFV against "the consensus". A reader hears that as a blend of published scouting
opinion. On a large share of the live board it is not one: when no rater published
an FV, the served consensus rests on a placeholder constant.

That gap has already produced one wrong published number. The C-6 lane
(2026-08-14) found a board-wide eFV deflation of -5.13 FV which turned out to be
an artifact of differencing against a fabricated constant on 59% of rows; on the
rows carrying a real opinion the sign reversed to +2.03. So the composition of the
population is not colour: it is load-bearing, and these tests keep it honest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import source_backtest as sb          # noqa: E402

ART = ROOT / "data" / "source_backtest.json"


@pytest.fixture(scope="module")
def block():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    j = json.loads(ART.read_text(encoding="utf-8"))
    sp = (j.get("accuracy") or {}).get("served_population")
    if not sp:
        pytest.skip("served_population is not in the artifact yet")
    return sp


# --------------------------------------------------------------------------
# The mirror. This module duplicates a constant that lives in consensus.py.
# --------------------------------------------------------------------------

def test_the_constant_anchor_mirror_matches_consensus():
    """source_backtest mirrors consensus.CONSTANT_ANCHOR_SOURCES rather than
    importing it, to keep this module's import graph light. A mirror that drifts
    is worse than no mirror: it would silently reclassify a placeholder as an
    opinion, which is the exact error this whole lane exists to prevent."""
    import consensus
    assert set(sb._CONSTANT_ANCHOR_SOURCES) == set(consensus.CONSTANT_ANCHOR_SOURCES), (
        "the constant-anchor mirror in source_backtest has drifted from "
        "consensus.CONSTANT_ANCHOR_SOURCES; a source on one list and not the "
        "other is counted as a published opinion in one place and a placeholder "
        "in the other")


def test_the_non_rater_set_still_contains_every_constant_anchor():
    assert set(sb._CONSTANT_ANCHOR_SOURCES) <= set(sb._NON_RATER_SOURCES), (
        "a constant-anchor source escaped the non-rater set, so it could be "
        "counted as a rater somewhere else in this module")


# --------------------------------------------------------------------------
# The classifier
# --------------------------------------------------------------------------

def _pt(per_source, **kw):
    p = {"per_source": per_source}
    p.update(kw)
    return p


def test_two_real_raters_is_multi_source():
    assert sb._population_category(_pt({
        "fangraphs": {"fv_published": 55.0},
        "mlb_pipeline": {"fv_published": 50.0}})) == "multi_source"


def test_one_real_rater_with_the_pull_on_is_shrunk():
    assert sb._population_category(_pt(
        {"fangraphs": {"fv_published": 45.0}},
        shrinkage_weight=0.6667)) == "single_source_shrunk"


def test_one_real_rater_with_the_pull_off_is_unshrunk():
    assert sb._population_category(_pt(
        {"fangraphs": {"fv_published": 45.0}},
        shrinkage_weight=1.0)) == "single_source_unshrunk"


def test_a_placeholder_alone_is_never_an_opinion():
    """The whole point. performance_ingest carries an FV, and it is not a grade."""
    cat = sb._population_category(_pt({"performance_ingest": {"fv_published": 35.0}}))
    assert cat == "constant_anchor_only", (
        f"a row whose only FV came from a placeholder classified as {cat!r}; "
        "consensus.py parks these sources precisely because they are not opinions")


def test_a_placeholder_does_not_dilute_a_real_rater():
    """A placeholder sitting beside one real grade must not read as two raters."""
    cat = sb._population_category(_pt({
        "fangraphs": {"fv_published": 50.0},
        "performance_ingest": {"fv_published": 35.0}}, shrinkage_weight=1.0))
    assert cat == "single_source_unshrunk", (
        f"classified as {cat!r}: the placeholder was counted toward the rater "
        "total, which would report a single-source row as a consensus")


def test_a_rank_only_row_is_not_counted_as_an_fv():
    """`fv_published: None` means the source APPEARED without grading. Counting
    it as an FV of zero, or as an FV at all, is the classic version of this bug."""
    cat = sb._population_category(_pt(
        {"fangraphs": {"fv_published": None}}, rank_implied_fv=42.0))
    assert cat == "rank_implied_only", f"got {cat!r}"


def test_nothing_at_all_is_reported_and_not_hidden():
    assert sb._population_category(_pt({})) == "no_basis"


def test_statcast_derived_pseudo_sources_are_excluded():
    cat = sb._population_category(_pt({
        "fangraphs_statcast_by_age": {"fv_published": 60.0},
        "fangraphs": {"fv_published": 50.0}}, shrinkage_weight=1.0))
    assert cat == "single_source_unshrunk", (
        f"got {cat!r}: a per-age statcast projection was counted as a rater")


# --------------------------------------------------------------------------
# The tallies
# --------------------------------------------------------------------------

def test_the_counts_partition_the_population(block):
    for view in ("latest_point", "common_set"):
        v = block[view]
        assert sum(v["counts"].values()) == v["n"], (
            f"{view}: the category counts do not sum to n, so the categories "
            "are not a partition and every share is wrong")


def test_the_opinion_rollup_is_its_categories(block):
    for view in ("latest_point", "common_set"):
        v = block[view]
        c = v["counts"]
        want = (c["multi_source"] + c["single_source_unshrunk"]
                + c["single_source_shrunk"] + c["rank_implied_only"])
        assert v["n_any_published_opinion"] == want, f"{view}: roll-up disagrees"
        assert v["n_no_published_opinion"] == v["n"] - want


def test_shares_agree_with_the_counts(block):
    for view in ("latest_point", "common_set"):
        v = block[view]
        if not v["n"]:
            continue
        for k, n in v["counts"].items():
            assert abs(v["share"][k] - n / v["n"]) < 5e-5, f"{view}/{k}"


def test_every_common_row_resolved_to_a_point(block):
    """A row the classifier could not place is not a category, it is a hole.
    A few would be tolerable; the count is published so nobody has to guess."""
    missed = block["common_set"].get("rows_not_resolvable_to_a_point")
    assert missed is not None, "the unresolvable count is not published"
    n = block["common_set"]["n"]
    assert missed <= 0.02 * max(n, 1), (
        f"{missed} of {n + missed} scored rows could not be traced back to a "
        "preseason point, so the common-set composition is measured on a subset "
        "of the rows the claim is actually computed on")


# --------------------------------------------------------------------------
# The derived copy
# --------------------------------------------------------------------------

def test_the_sentence_is_derived_and_not_typed(block):
    """Regenerating the sentence from the block's own numbers must reproduce it
    exactly. If a human ever edits the string, this goes red - which is the
    entire mechanism that stops a stale number reaching the page."""
    again = sb._population_sentence(block["latest_point"], block["common_set"])
    assert again == block["sentence"], (
        "the published sentence is not what the numbers derive:\n"
        f"  published: {block['sentence']}\n"
        f"  derived:   {again}")


def test_the_reading_is_derived_too(block):
    again = sb._population_reading(block["latest_point"], block["common_set"])
    assert again == block["reading"]


def test_the_reading_flips_when_the_gap_flips():
    """The reading is a derivation, not a fixed conclusion. Feed it the inverted
    world and it must say the inverted thing, or it is decoration."""
    good = {"share_no_published_opinion": 0.02}
    bad = {"share_no_published_opinion": 0.40}
    normal = sb._population_reading(bad, good)
    inverted = sb._population_reading(good, bad)
    assert "better-graded population" in normal
    assert "lower bound" in inverted, (
        "with the scored rows worse-graded than the board, the reading still "
        "reported the reassuring conclusion")
    assert normal != inverted


def test_the_block_states_that_it_moves_nothing(block):
    assert block.get("changes_no_published_number") is True
    assert "not a correction" in (block.get("what_this_is_not") or "").lower()


# --------------------------------------------------------------------------
# The finding itself, pinned so a regression in composition is visible
# --------------------------------------------------------------------------

def test_the_board_really_does_rest_heavily_on_placeholders(block):
    """Not a threshold anyone should tune. It records the state on 2026-09-06
    (38.6% of the live board with no published opinion) so that if a future
    ingest fixes it, somebody has to come here and say so deliberately."""
    lat = block["latest_point"]["share_no_published_opinion"]
    assert lat is not None
    assert 0.20 <= lat <= 0.60, (
        f"the share of the board resting on no published opinion is {lat:.3f}, "
        "outside the band recorded on 2026-09-06 (0.386). If coverage really "
        "changed, update this test and the accuracy copy together; if it did "
        "not, the classifier changed meaning and every cell that cites it is "
        "now describing a different population.")


def test_the_scored_population_is_the_better_graded_one(block):
    """This is what makes the head-to-head trustworthy, and it is not
    guaranteed by anything: it falls out of requiring every rater to have graded
    a row. If it ever inverts, the accuracy claim is running on the worse
    population and the reading above must change with it."""
    lat = block["latest_point"]["share_no_published_opinion"]
    com = block["common_set"]["share_no_published_opinion"]
    assert com <= lat, (
        f"scored rows rest on no published opinion {com:.3f} of the time "
        f"against {lat:.3f} on the live board")
