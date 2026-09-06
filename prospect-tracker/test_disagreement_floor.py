"""A-CLAIM-10: the disagreement share, its interval, and the copy that carries it.

THE DEFECT THIS CLOSES. "eFV was closer on 55% of the biggest disagreements" was
published in four places, twice in bold and once as a headline tile, as a bare
percentage with no interval. Measured on 2026-09-06 it is 54.8% over 283 resolved
disagreements with a 95% CI of 49.1% to 60.8%, which contains the 50% coin, at a
one-sided p of 0.058. The site was publishing a coin flip as a finding, and the
scoreboard artifact went further and recorded `win: true` for it.

"Closer" is a two-way comparison decided per row, so a model with no skill at
picking its spots lands at 50% by construction. 50% is the null, and a point
estimate above it means nothing on its own at this sample size.

A SECOND DEFECT, found while building the first. The percentile helper the
cohort is cut with assigned tied values DIFFERENT percentiles, decided by nothing
but their position in the sorted list. Consensus FV lives on the 20-80 scale in
5-point steps with a large block sitting on the FV 35 constant anchor, so the old
code spread one grade across a wide band and manufactured disagreement between
players the consensus had graded identically. Ties now share the mean of the
positions they occupy.
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
def det():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    j = json.loads(ART.read_text(encoding="utf-8"))
    d = (j.get("accuracy") or {}).get("xfv_vs_consensus_detail")
    if not d:
        pytest.skip("xfv_vs_consensus_detail is not in the artifact")
    return d


# --------------------------------------------------------------------------
# Tie-averaged percentiles
# --------------------------------------------------------------------------

def _rows(pairs):
    """Synthetic common-set rows. `pairs` is [(xfv_grade, consensus_grade, war)].

    _xfv_vs_consensus_detail refuses a cohort under 40 rows, so callers build at
    least that many; the refusal is correct and is not what these tests probe.
    """
    out = []
    for i, (x, c, w) in enumerate(pairs):
        out.append({
            "key": "p%d" % i, "name": "P%d" % i, "year": 2020,
            "grades": {"xfv": float(x), sb.CONSENSUS_KEY: float(c)},
            "outcome": {"war": float(w), "debuted": True, "debut_year": 2021,
                        "contributor": w >= 3.0, "star": w >= 10.0,
                        "war_per_yr": None, "regular_pace": False,
                        "allstar_pace": False},
            "archetype": None,
        })
    return out


def test_tied_grades_get_the_same_percentile():
    """The core of the fix. A block of players graded identically must not be
    spread across the percentile scale by nothing but their list position.

    Built so that eFV and consensus give every player the SAME grade. Identical
    inputs can only produce identical percentiles, so a correct implementation
    finds zero disagreement. The old code found plenty, because it walked the
    sorted order and handed out distinct percentiles to equal values.
    """
    # 30 players on the FV 35 constant anchor plus 20 spread above it: exactly
    # the shape of the real board, where the anchor block is the biggest tie.
    pairs = [(35.0, 35.0, float(i % 4)) for i in range(30)]
    pairs += [(40.0 + i, 40.0 + i, float(i)) for i in range(20)]
    out = sb._xfv_vs_consensus_detail(_rows(pairs))
    assert out is not None, "the cohort was refused; it should hold 50 rows"
    assert out["n_disagreements"] == 0, (
        "rows whose eFV and consensus grades are IDENTICAL were recorded as "
        "disagreeing, which can only happen if tied values are being given "
        "different percentiles")


def test_a_real_gap_is_still_detected():
    """The tie fix must not flatten genuine disagreement into nothing."""
    pairs = []
    for i in range(50):
        # Opposed placements: eFV ranks ascending, consensus descending.
        pairs.append((20.0 + i, 70.0 - i, float(i % 7)))
    out = sb._xfv_vs_consensus_detail(_rows(pairs))
    assert out is not None
    assert out["n_disagreements"] > 0, (
        "no disagreement found on a cohort built entirely out of opposed "
        "grades; the tie averaging has flattened real signal")


def test_the_anchor_block_no_longer_manufactures_disagreement():
    """The board-shaped case, stated as the regression it is.

    A third of the live board sits on the FV 35 constant anchor. Under the old
    percentile code that block alone spanned a wide percentile range, so a
    player at the top of it and a player at the bottom of it looked far apart to
    the disagreement cut despite carrying the same grade.
    """
    # Every consensus grade is the anchor; eFV separates them. The disagreement
    # that survives must come from the eFV side alone, not from the anchor being
    # fanned out.
    pairs = [(30.0 + i, 35.0, float(i % 5)) for i in range(50)]
    out = sb._xfv_vs_consensus_detail(_rows(pairs))
    assert out is not None
    cons_pcts = set()
    # Re-derive the consensus percentiles the same way the function does, to
    # assert the anchor block collapses to a single value.
    rows = _rows(pairs)
    vals = [r["grades"][sb.CONSENSUS_KEY] for r in rows]
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    n = len(vals)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        cons_pcts.add((i + j) / 2.0 / (n - 1))
        i = j + 1
    assert len(cons_pcts) == 1, (
        "the 50-row anchor block resolved to more than one percentile: "
        + repr(sorted(cons_pcts)))


# --------------------------------------------------------------------------
# The interval
# --------------------------------------------------------------------------

def test_the_share_ships_with_an_interval(det):
    assert "xfv_right_share_ci95" in det, (
        "the disagreement share is published with no interval; it is rendered "
        "in four places and at this sample size the point estimate alone "
        "cannot be distinguished from a coin flip")
    if det["n_disagreements"] >= 30:
        ci = det["xfv_right_share_ci95"]
        assert ci and len(ci) == 2 and ci[0] < ci[1]


def test_the_point_lies_inside_its_own_interval(det):
    ci = det.get("xfv_right_share_ci95")
    if not ci:
        pytest.skip("no interval on this cohort")
    pt = det["xfv_right_share_on_disagreements"]
    assert ci[0] <= pt <= ci[1], (
        f"the published share {pt} sits outside its own 95% interval {ci}")


def test_resolvable_means_the_interval_clears_the_coin(det):
    ci = det.get("xfv_right_share_ci95")
    if not ci:
        pytest.skip("no interval on this cohort")
    assert det["xfv_right_share_resolvable"] is (ci[0] > 0.5), (
        "the resolvable flag disagrees with its own interval, so the copy "
        "derived from it is telling the reader something the numbers do not")


def test_the_null_is_stated_and_is_a_half(det):
    assert det.get("disagreement_null") == 0.5, (
        "the null for a two-way closer-than comparison is 0.5 by construction "
        "and must be published beside the share")


def test_the_verdict_is_consistent_with_the_flag(det):
    v = (det.get("xfv_right_share_verdict") or "").lower()
    assert v, "no verdict string was derived"
    if det.get("xfv_right_share_resolvable"):
        assert "clears" in v
    else:
        assert "coin" in v and "not" in v, (
            "the share does not clear its null and the verdict does not say so: "
            + v)


def test_the_verdict_is_marginal_and_must_not_be_quoted_as_settled(det):
    """THE READING FLIPS ON ONE PLAYER, and that is the finding.

    This test used to pin `resolvable is False`. It went red the same day, and
    for an instructive reason. The cohort is derived from data/timeseries.json,
    which is GITIGNORED, so conftest's revert cannot see it; a suite chunk
    regenerated it and added ONE player to the universe. On the build before
    that, the share read 54.8% with a 95% interval of [49.1%, 60.8%] which
    CONTAINS the 50% coin. On the build after, 57.3% with [51.4%, 62.9%] which
    EXCLUDES it. Same code, same method, one extra player, opposite verdicts.

    So the honest thing to pin is not which side of the coin today's cohort
    lands on. It is that the share sits close enough to the coin for a single
    row to move it across, which is the strongest possible argument for the fix
    this lane shipped: a number this marginal must never be published as a bare
    percentage, and the interval must travel with it.

    If the share ever moves far from 0.5 in either direction, this test should
    be replaced by one that pins the settled verdict.
    """
    if det["n_disagreements"] < 30:
        pytest.skip("cohort too small")
    pt = det["xfv_right_share_on_disagreements"]
    lo, hi = det["xfv_right_share_ci95"]
    assert 0.45 < pt < 0.65, (
        f"the share has moved to {pt}, well away from the coin. That is a real "
        "change in the finding: confirm it and replace this test with one that "
        "pins the settled verdict in whichever direction it settled.")
    assert lo < 0.5 + 0.06, (
        f"the interval's lower bound is {lo}, comfortably clear of the coin. "
        "The reading is no longer marginal and this test no longer describes it.")
    assert det["xfv_right_share_resolvable"] is (lo > 0.5)


# --------------------------------------------------------------------------
# The scoreboard must not call it a win
# --------------------------------------------------------------------------

def test_the_scoreboard_win_flag_requires_the_interval():
    src = (ROOT / "tools" / "efv_scoreboard.py").read_text(encoding="utf-8")
    assert '"win": (share is not None and share > 0.5)' not in src, (
        "tools/efv_scoreboard.py still decides `win` from the point estimate. "
        "A share of 0.548 over 283 rows whose interval runs 0.491 to 0.608 is "
        "not a win, and a boolean that says otherwise travels further than the "
        "number it came from.")
    assert "efv_right_share_resolvable" in src, (
        "the scoreboard does not carry the resolvable flag, so no downstream "
        "surface can qualify the share it publishes")


# --------------------------------------------------------------------------
# The copy
# --------------------------------------------------------------------------

def test_every_render_site_goes_through_the_shared_reader():
    """Four surfaces render this share. They must not each decide for
    themselves what it means, or they will drift, and the one that drifts is
    the one that gets screenshotted."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert "function _disagreementRead(" in js, (
        "the shared reader is gone; each surface is formatting the share itself")
    # The bare pattern that was there before: a percentage with no interval and
    # no qualifier anywhere near it.
    bad = 'label: "closer on the biggest disagreements",\n    sub: nDis != null ? nDis + " resolved eFV vs consensus splits"'
    assert bad not in js, "the unqualified share tile is back"
    assert js.count("_disagreementRead(") >= 4, (
        "fewer call sites than expected go through the shared reader; one of "
        "the four render sites is formatting the share on its own")


def test_the_copy_qualifier_is_derived_not_typed():
    """The qualifier must disappear by itself when the interval clears. A
    hardcoded "(inside the noise)" would be wrong on exactly the day it matters."""
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    i = js.index("function _disagreementRead(")
    body = js[i:i + 1800]
    assert "resolvable" in body and "?" in body, (
        "the shared reader does not branch on resolvability, so its output "
        "cannot change when the finding does")
    # The share-card sentence branches on the artifact flag rather than a string.
    j = js.index("biggest resolved disagreements")
    around = js[max(0, j - 600):j + 200]
    assert "efv_right_share_resolvable" in around, (
        "the share-card sentence hardcodes its qualifier instead of reading the "
        "artifact, so it will keep saying the same thing after the finding "
        "changes")
