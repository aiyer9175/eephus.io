# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""D3: the pairwise head-to-head basis, and the four things that keep it honest.

WHY IT EXISTS. `run_source_backtest` admits a player to the common set only when
EVERY scored rater graded him, so adding a rater does not add a bar to the
chart, it redefines the population every other bar is computed on. Admitting
Baseball America takes the common set from 4,284 rows to 295 and flips the
incumbent ordering, so BA cannot be admitted and has been unscoreable.

That 93% cost is a property of insisting on ONE GLOBAL POPULATION, not of the
evidence. BA overlaps FanGraphs on 700 rows and MLB Pipeline on 696, and none of
those rows need to come out of the 4,299 the incumbents share. Scoring a PAIR on
the rows that pair shares measures the newcomer without taking anything from
anyone.

Pre-registration: docs/efv-2026-08-12/SOURCE_SCORING_BASIS_GATE.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ART = ROOT / "data" / "source_backtest.json"

sb = pytest.importorskip("source_backtest")


@pytest.fixture(scope="module")
def served():
    if not ART.exists():
        pytest.skip("data/source_backtest.json not built")
    return json.loads(ART.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def block(served):
    b = served.get("pairwise_head_to_head")
    if not b:
        pytest.skip("pairwise_head_to_head not in the served artifact yet")
    return b


def _cell(block, a, b):
    for c in block["cells"]:
        if {c["a"], c["b"]} == {a, b}:
            return c
    return None


def test_the_regression_control_reproduces_the_served_pooled_numbers(served, block):
    """THE control. If the new basis cannot reproduce the old answer where the
    two coincide, it is computing something else and nothing it says is worth
    reading."""
    cell = _cell(block, "fangraphs", "mlb_pipeline")
    assert cell is not None, "the incumbent pair has no cell"
    pooled = (served.get("accuracy") or {}).get("pooled") or {}
    for src, key in (("fangraphs", "rho_a"), ("mlb_pipeline", "rho_b")):
        want = (pooled.get(src) or {}).get("spearman")
        got = cell[key] if cell["a"] == src or key == "rho_b" else cell["rho_a"]
        got = cell["rho_a"] if cell["a"] == src else cell["rho_b"]
        assert want is not None and abs(got - want) < 5e-4, (
            f"{src}: pairwise basis says {got}, accuracy.pooled says {want}. The "
            "two bases coincide on this pair, so they must agree.")
    assert cell["n"] == pooled.get("fangraphs", {}).get("n"), (
        f"row count {cell['n']} does not match the served pooled n "
        f"{pooled.get('fangraphs', {}).get('n')}")


def test_the_incumbent_pair_never_gets_a_second_verdict(block):
    """Two verdicts for one pair is a contradiction, not a measurement.

    source_cohort_accuracy owns the source-versus-source question and scores
    this pair on a SMALLER population (1,520 rows against 4,299 here), where the
    same difference of about -0.03 does not clear its interval. Publishing
    'resolved' here beside 'not resolvable' there would leave a reader with two
    answers and no way to choose.
    """
    cell = _cell(block, "fangraphs", "mlb_pipeline")
    assert cell["role"] == "regression_control"
    assert cell["leader"] is None, (
        "the incumbent pair names a leader from this basis; it must defer")
    assert "source_cohort_accuracy" in (cell.get("defers_verdict_to") or ""), (
        "the incumbent cell does not point at the artifact that owns its verdict")
    assert "no verdict from this basis" in cell["verdict"]


def test_a_cell_whose_interval_spans_zero_is_not_a_winner(block):
    """The site's own language, applied here too."""
    for c in block["cells"]:
        if not c.get("ci95"):
            continue
        lo, hi = c["ci95"]
        spans = lo <= 0 <= hi
        if c.get("role") == "regression_control":
            continue
        assert c["resolvable"] is (not spans), (
            f"{c['a']} vs {c['b']}: interval [{lo}, {hi}] and resolvable="
            f"{c['resolvable']} disagree")
        if spans:
            assert "not resolvable" in c["verdict"]
            assert c["leader"] is None


def test_every_short_window_pair_carries_a_same_year_benchmark(block):
    """A one-year comparison is unreadable without one, and this is measured:
    restricted to 2023 alone FanGraphs leads MLB Pipeline, while pooled over the
    full window Pipeline leads. One year flips the incumbent ordering, so a
    reader shown a one-year result and no same-year yardstick cannot tell a
    rater difference from a year difference."""
    full = set(block["window_years"])
    for c in block["cells"]:
        if set(c["years"]) == full:
            continue
        key = c.get("same_year_benchmark")
        assert key, (
            f"{c['a']} vs {c['b']} spans only {c['years']} and carries no "
            "same-year benchmark")
        assert key in block["same_year_benchmarks"], (
            f"benchmark {key!r} is named but not published")


def test_the_block_is_additive_and_says_so(served, block):
    """SCORED_SOURCES is unchanged and no published verdict moved."""
    assert block.get("is_additional_view") is True
    assert block.get("changes_no_published_verdict") is True
    assert sb.SCORED_SOURCES == ("fangraphs", "mlb_pipeline"), (
        "SCORED_SOURCES changed. Promoting a rater restates every published "
        "accuracy number and is an explicit owner decision, not a side effect "
        "of adding a view.")
    # The keys the site actually reads must all still be present.
    acc = served.get("accuracy") or {}
    for k in ("pooled", "pooled_efv_common", "consensus_vs_inputs",
              "head_to_head_verdict", "by_archetype", "common_n"):
        assert k in acc, f"accuracy.{k} disappeared"
