# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The runline/total exclusion the module documented and never implemented.

betting_model's docstring has said since the dispersion gate returned
INDETERMINATE that these markets do not fill a published slot. Nothing enforced
it. Measured 2026-08-14: the published pick of the day WAS a runline at edge
0.123, and 62 of 80 shadow rows (78%) were runline or total, on the two markets
whose own graded Brier (0.26301, 0.26522) is worse than a flat 0.500.

SCOPE IS DELIBERATE AND IS PINNED HERE. The slots and the public record are
excluded; the PAPER LEDGER IS NOT. The ledger is the instrument that accrues
the settled outcomes needed to resolve the dispersion gate, so excluding them
there would delete the only evidence that could ever lift the exclusion. That
is an amendment to the docstring's third clause, taken as an owner decision on
2026-08-14, and `test_the_shadow_ledger_is_deliberately_not_excluded` exists so
a later reader cannot "complete" the exclusion without confronting the reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import betting_export as be
import betting_model as bm
import betting_shadow as bs

ROOT = Path(__file__).resolve().parent


def _board():
    """One game carrying a clearing side in ALL THREE markets.

    Every market's edge is far above any floor, so a market that is absent from
    the output is absent because it was EXCLUDED and not because it failed to
    clear. That is what makes the exclusion tests non-vacuous.
    """
    row = lambda side, edge: {          # noqa: E731
        "side": side, "edge": edge, "odds": -110, "book": "testbook",
        "model_prob": 0.60, "market_fair_prob": 0.60 - edge, "kelly_full": 0.2,
    }
    return [{
        "game_pk": 1, "start": "2026-08-14T23:05:00Z",
        "away": {"org": "AAA"}, "home": {"org": "BBB"},
        "moneyline": [row("home", 0.20)],
        "runline": [row("home", 0.30)],
        "total": {"sides": [row("over", 0.40)]},
    }]


def test_the_fixture_would_publish_all_three_markets_without_the_guard():
    """NON-VACUITY, FIRST. With the predicate forced open, all three markets
    clear. Without this, every assertion below could pass on a fixture that
    never had a runline or total to exclude."""
    cands = [c for c in _all_markets_unguarded()]
    assert {c["market"] for c in cands} == {"moneyline", "runline", "total"}, cands


def _all_markets_unguarded():
    orig = bm.SERVE_RUN_DISPERSION
    try:
        bm.SERVE_RUN_DISPERSION = True          # the flag the predicate reads
        return be._floor_clearing_sides(_board(), 0.06)
    finally:
        bm.SERVE_RUN_DISPERSION = orig


def test_predicate_excludes_exactly_the_two_dispersion_sensitive_markets():
    assert bm.SERVE_RUN_DISPERSION is False, (
        "this file's premise is that the correction is UNSERVED; if the flag "
        "has flipped, the exclusion should lift and these tests must be re-read")
    assert bm.market_is_publishable("moneyline") is True
    assert bm.market_is_publishable("runline") is False
    assert bm.market_is_publishable("total") is False


def test_predicate_is_case_insensitive():
    assert bm.market_is_publishable("RunLine") is False
    assert bm.market_is_publishable("TOTAL") is False


def test_predicate_lifts_itself_when_the_correction_is_served():
    """The guard may not outlive the defect it guards."""
    orig = bm.SERVE_RUN_DISPERSION
    try:
        bm.SERVE_RUN_DISPERSION = True
        assert bm.market_is_publishable("runline") is True
        assert bm.market_is_publishable("total") is True
    finally:
        bm.SERVE_RUN_DISPERSION = orig


def test_slot_selection_emits_no_runline_or_total():
    """SEAM 1: the two published slots."""
    cands = be._floor_clearing_sides(_board(), 0.06)
    assert cands, "guard removed everything; the moneyline side should survive"
    assert {c["market"] for c in cands} == {"moneyline"}, cands


def test_append_record_refuses_an_excluded_market(tmp_path):
    """SEAM 2: the public record, guarded at the FUNNEL.

    append_record documents itself as the only sanctioned way in, so the guard
    lives there and no future call site can bypass it by not knowing about it.
    """
    p = tmp_path / "record.json"
    p.write_text("[]", encoding="utf-8")
    rows = [
        {"bet_id": "a", "market": "moneyline", "side": "home"},
        {"bet_id": "b", "market": "runline", "side": "home"},
        {"bet_id": "c", "market": "total", "side": "over"},
    ]
    out = be.append_record(rows, path=p)
    assert [r["market"] for r in out] == ["moneyline"], out
    assert json.loads(p.read_text(encoding="utf-8")) == out


def test_the_shadow_ledger_is_deliberately_not_excluded():
    """THE AMENDMENT, PINNED SO IT CANNOT BE SILENTLY "COMPLETED".

    The ledger keeps recording runline and total on purpose: it is the only
    place settled outcomes for those markets accumulate, and the dispersion
    gate cannot ever be resolved without them. If someone later extends the
    exclusion here, this test fails and makes them read the reason first.
    """
    src = (ROOT / "betting_shadow.py").read_text(encoding="utf-8")
    assert "market_is_publishable" not in src, (
        "betting_shadow.py now consults market_is_publishable. That extends the "
        "exclusion to the PAPER LEDGER, which deletes the only evidence that "
        "could ever lift it. See betting_model.market_is_publishable and the "
        "owner decision of 2026-08-14 before changing this.")


def test_the_docstring_no_longer_claims_the_ledger_is_excluded():
    """The prose and the code must agree, which is the whole point of the lane."""
    doc = bm.__doc__ or ""
    head = doc[:4000]
    assert "market_is_publishable" in head, (
        "the module docstring should name the predicate that enforces the "
        "exclusion rather than asserting the exclusion happens")
