"""A-CLAIM-14: the candidate-year and newcomer ledger.

WHAT IT ANSWERS THAT NOTHING ELSE DOES. `classify_sources` asks whether a source
can be admitted against the COMMON SET. `pairwise_head_to_head` scores the pairs
that already can be. Neither says when a pair that cannot be scored today becomes
scoreable, or whether it ever does, and those are different questions with
different remedies: a vintage that has not resolved yet is fixed by waiting, and
an overlap that is too small is fixed by nothing, because the overlap is settled
the day the boards are published.

THIS FILE ALSO PINS A RETRACTION. The 2026-09-05 plan asserted the ESPN x MLB
Pipeline 2026 overlap stood at 11 rows and could "never clear the 100-row
pairwise minimum". Measured, it is 102 rows and clears it. The pair is blocked by
the CANDIDATE_YEARS tuple instead. The tests below assert the measured shape, so
the retracted figure cannot quietly return.
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
def led():
    if not ART.exists():
        pytest.skip("data/source_backtest.json has not been built")
    j = json.loads(ART.read_text(encoding="utf-8"))
    L = (j.get("accuracy") or {}).get("candidate_year_ledger")
    if not L:
        pytest.skip("candidate_year_ledger is not in the artifact yet")
    return L


def _pair(led, a, b):
    for c in led["pairs"]:
        if {c["a"], c["b"]} == {a, b}:
            return c
    return None


# --------------------------------------------------------------------------
# It must not change anything
# --------------------------------------------------------------------------

def test_the_ledger_declares_itself_an_additional_view(led):
    assert led["is_additional_view"] is True
    assert led["changes_no_published_verdict"] is True


def test_the_constants_are_the_ones_the_rest_of_the_module_uses(led):
    assert led["pairwise_min_rows"] == sb._PAIRWISE_MIN_ROWS
    assert led["min_lag_years"] == sb.MIN_LAG_YEARS
    assert led["candidate_years"] == list(sb.CANDIDATE_YEARS), (
        "the ledger reports a candidate-year tuple that is not the one the "
        "backtest filters on, so its decidability answers describe a different "
        "configuration than the one that runs")


# --------------------------------------------------------------------------
# The blocker taxonomy is the point of the file
# --------------------------------------------------------------------------

def test_every_pair_carries_a_blocker_or_is_decidable(led):
    for c in led["pairs"]:
        if c["decidable_now"]:
            assert c["blocked_by"] is None, (
                f"{c['a']} x {c['b']} is decidable and still names a blocker")
        else:
            assert c["blocked_by"] in ("lag", "overlap", "candidate_years"), (
                f"{c['a']} x {c['b']} has blocker {c['blocked_by']!r}, which is "
                "not one of the three the ledger documents")


def test_an_overlap_blocked_pair_really_has_no_big_enough_vintage(led):
    """`overlap` is the only verdict that says "never", so it has to be earned."""
    for c in led["pairs"]:
        if c["blocked_by"] != "overlap":
            continue
        biggest = max(c["overlap_by_base_year"].values())
        assert biggest < led["pairwise_min_rows"], (
            f"{c['a']} x {c['b']} is reported as permanently blocked on overlap "
            f"while holding a vintage of {biggest} rows, at or above the "
            f"{led['pairwise_min_rows']}-row minimum. That verdict tells a "
            "reader to stop waiting for a comparison that is actually available.")
        assert c["never_decidable_on_current_vintages"] is True
        assert c["first_decidable_run_year_if_candidate_years_extended"] is None


def test_a_tuple_blocked_pair_has_a_vintage_that_would_qualify(led):
    """`candidate_years` says the data is fine and the config is not. If that is
    true, extending the tuple must produce a real run year."""
    for c in led["pairs"]:
        if c["blocked_by"] != "candidate_years":
            continue
        assert c["base_years_blocked_by_candidate_years"], (
            f"{c['a']} x {c['b']} blames the candidate-year tuple but names no "
            "base year the tuple excluded")
        assert c["first_decidable_run_year_if_candidate_years_extended"] is not None, (
            f"{c['a']} x {c['b']} blames the tuple, yet extending the tuple "
            "still yields no run year, so the tuple was not the binding "
            "constraint and the blocker is mislabelled")
        assert c["overlap_best"] >= led["pairwise_min_rows"]


def test_the_two_run_year_fields_never_contradict_each_other(led):
    """Extending a constraint can only ever make a pair decidable SOONER."""
    for c in led["pairs"]:
        real = c["first_decidable_run_year"]
        ext = c["first_decidable_run_year_if_candidate_years_extended"]
        if real is None or ext is None:
            continue
        assert ext <= real, (
            f"{c['a']} x {c['b']}: relaxing the candidate-year tuple pushed the "
            f"first decidable run year later ({real} -> {ext}), which is not "
            "possible and means one of the two is computed wrong")


def test_overlap_never_exceeds_either_sources_own_footprint(led):
    """A shared-row count above one side's total row count is arithmetic proof
    the intersection is being computed on the wrong keys."""
    per = led["per_source_resolved_keys_by_base_year"]
    for c in led["pairs"]:
        for y, n in c["overlap_by_base_year"].items():
            ya = (per.get(c["a"]) or {}).get(str(y), (per.get(c["a"]) or {}).get(y, 0))
            yb = (per.get(c["b"]) or {}).get(str(y), (per.get(c["b"]) or {}).get(y, 0))
            assert n <= min(ya, yb), (
                f"{c['a']} x {c['b']} {y}: overlap {n} exceeds the smaller "
                f"source's own footprint (min({ya}, {yb}))")


# --------------------------------------------------------------------------
# The retraction
# --------------------------------------------------------------------------

def test_espn_x_pipeline_overlap_is_measured_not_assumed(led):
    """The plan said 11 rows and never decidable. Both halves were wrong."""
    c = _pair(led, "espn", "mlb_pipeline")
    if c is None:
        pytest.skip("espn has no overlap with mlb_pipeline in this universe")
    assert c["overlap_best"] >= led["pairwise_min_rows"], (
        f"ESPN x MLB Pipeline best overlap is {c['overlap_best']}, below the "
        f"{led['pairwise_min_rows']}-row minimum. If this is now genuinely "
        "true, the plan's retracted claim has become correct by accident and "
        "the header comment in source_backtest must be rewritten to say so.")
    assert c["blocked_by"] != "overlap", (
        "ESPN x MLB Pipeline is reported as permanently blocked on overlap, "
        "which is the plan's retracted claim reappearing")


def test_the_retraction_is_written_down_where_the_number_is_computed():
    src = (ROOT / "source_backtest.py").read_text(encoding="utf-8")
    i = src.index("A-CLAIM-14")
    head = src[i:i + 2200]
    assert "retracted" in head.lower(), (
        "the ledger's header no longer records that the plan's 11-row figure "
        "was retracted; a future reader will re-import it from the plan")


# --------------------------------------------------------------------------
# Coverage honesty
# --------------------------------------------------------------------------

def test_no_resolution_rate_can_be_derived_from_these_counts(led):
    """The counts are RESOLVED keys. A published row that never matched an
    identity is absent from the universe entirely, so there is no denominator
    here and any percentage computed from these numbers would be wrong."""
    note = led.get("resolution_denominator_is_not_visible_here") or ""
    assert "unresolved" in note.lower() and "rate" in note.lower(), (
        "the ledger publishes per-source counts without warning that the "
        "unresolved side is invisible to it; somebody will divide these")


def test_rank_only_rows_are_kept_out_of_overlap(led):
    """A rater that published a board with no grades cannot be compared on
    grades. Those appearances are counted separately, never as overlap."""
    assert "per_source_rank_only_rows_by_base_year" in led
    ranky = led["per_source_rank_only_rows_by_base_year"]
    graded = led["per_source_resolved_keys_by_base_year"]
    assert isinstance(ranky, dict)
    # A source appearing ONLY as rank-only must not appear in any pair.
    only_rank = set(ranky) - set(graded)
    for c in led["pairs"]:
        assert c["a"] not in only_rank and c["b"] not in only_rank, (
            f"{c['a']} x {c['b']} pairs a source that never published an FV")


def test_the_next_run_year_is_one_of_the_pairs_own_answers(led):
    nxt = led["next_run_year_that_adds_a_vintage"]
    if nxt is None:
        assert all(c["first_decidable_run_year"] is None for c in led["pairs"])
        return
    years = {c["first_decidable_run_year"] for c in led["pairs"]}
    assert nxt in years and nxt == min(y for y in years if y is not None)
    assert nxt > led["as_of_run_year"], (
        "the ledger advertises a future run year that is not in the future")
