# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The runline/total exclusion, then its policy override: BOTH states pinned.

HISTORY. betting_model's docstring said since the dispersion gate returned
INDETERMINATE that runline and total do not fill a published slot. Nothing enforced
it until 2026-08-14 (the published pick of the day WAS a runline at edge 0.123, and 62
of 80 shadow rows were runline or total, on the two markets whose own graded Brier
was worse than a flat 0.500). The exclusion then shipped at two seams: the slots and
the public record. The PAPER LEDGER was deliberately not excluded (it is the
instrument that accrues the settled outcomes that could resolve the gate).

OWNER DECISION 2026-09-05 (docs/diamond-betting.md 7d): the slots are no longer locked
to the moneyline. `betting_model.SLOT_MARKET_POLICY = "any"` makes every priced market
eligible for both slots and the record; the dispersion caveat and the section 7b
evidence ride the published ROW as disclosure instead of barring the market.
`"dispersion_gated"` restores the 2026-08-14 behaviour at both seams.

This file pins BOTH states so that neither the exclusion nor the override can be
silently lost: the served policy is asserted first, then the gated behaviour under a
monkeypatched policy, then the invariants that hold in either state (the theory leg
is still measured, the caveat still rides a runline/total row, the ledger is still
not excluded).
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


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setattr(bm, "SLOT_MARKET_POLICY", "dispersion_gated")
    monkeypatch.setattr(bm, "SERVE_RUN_DISPERSION", False)
    yield


@pytest.fixture
def any_policy(monkeypatch):
    monkeypatch.setattr(bm, "SLOT_MARKET_POLICY", "any")
    monkeypatch.setattr(bm, "SERVE_RUN_DISPERSION", False)
    yield


# ── the served state ──────────────────────────────────────────────────────────
def test_the_served_policy_is_any_market():
    """The owner decision of 2026-09-05, pinned. Flipping this constant is the
    documented way back to the 2026-08-14 exclusion; do it here and in 7d together."""
    assert bm.SLOT_MARKET_POLICY == "any"


def test_the_fixture_would_publish_all_three_markets(any_policy):
    """NON-VACUITY, FIRST. All three markets clear, so an absent market below is an
    exclusion and not a failure to clear."""
    cands = be._floor_clearing_sides(_board(), 0.06, ledger_closed=frozenset())
    assert {c["market"] for c in cands} == {"moneyline", "runline", "total"}, cands


def test_under_any_policy_every_market_is_publishable_and_the_theory_leg_still_says_no(any_policy):
    for m in ("moneyline", "runline", "total", "props_batter_home_runs"):
        assert bm.market_is_publishable(m) is True
    assert bm.market_theory_ok("moneyline") is True
    assert bm.market_theory_ok("runline") is False and bm.market_theory_ok("total") is False
    assert bm.market_is_dispersion_sensitive("Total") is True
    assert bm.market_is_dispersion_sensitive("moneyline") is False


def test_under_any_policy_a_ledger_closed_market_still_fills_a_slot_with_the_evidence_caveat(any_policy):
    cands = be._floor_clearing_sides(_board(), 0.06, ledger_closed=frozenset({"total"}))
    by = {c["market"]: c for c in cands}
    assert set(by) == {"moneyline", "runline", "total"}
    assert by["total"]["evidence_closed"] is True and by["moneyline"]["evidence_closed"] is False
    pub = be._publish_slot(by["total"], "pick_of_the_day", thr=0.06, prov=True)
    assert pub["evidence_caveat"] == be.EVIDENCE_CAVEAT
    assert pub["caveat"] == be.POISSON_CAVEAT, "a total still carries the Poisson caveat"
    assert pub["market_policy"] == "any"
    ml = be._publish_slot(by["moneyline"], "pick_of_the_day", thr=0.06, prov=True)
    assert "caveat" not in ml and "evidence_caveat" not in ml


def test_under_any_policy_the_record_keeps_every_market_and_stamps_both_legs(any_policy, tmp_path):
    p = tmp_path / "record.json"
    p.write_text("[]", encoding="utf-8")
    rows = [{"bet_id": "a", "market": "h2h", "side": "home"},
            {"bet_id": "b", "market": "spreads", "side": "home"},
            {"bet_id": "c", "market": "totals", "side": "over"}]
    out = be.append_record(rows, path=p, ledger_closed=frozenset({"total"}))
    assert [r["bet_id"] for r in out] == ["a", "b", "c"]
    by = {r["bet_id"]: r for r in out}
    assert by["a"]["dispersion_sensitive"] is False and by["a"]["evidence_closed"] is False
    assert by["b"]["dispersion_sensitive"] is True, "spreads is the runline in feed vocabulary"
    assert by["c"]["dispersion_sensitive"] is True and by["c"]["evidence_closed"] is True
    assert all(r["market_policy"] == "any" for r in out)


def test_props_value_rows_compete_for_the_slots_on_the_same_floor(any_policy):
    props = [{"market": "props_pitcher_strikeouts", "player": "Some Arm", "game_pk": 1,
              "matchup": "AAA at BBB", "start": "2026-08-14T23:05:00Z", "label": "Some Arm Over 6.5",
              "side": "over", "point": 6.5, "edge": 0.50, "odds": -115, "book": "testbook",
              "model_prob": 0.80, "market_fair_prob": 0.30, "ev_per_unit": 0.4, "kelly_full": 0.3},
             {"market": "props_pitcher_strikeouts", "player": "No Price", "game_pk": 1,
              "matchup": "AAA at BBB", "start": "x", "label": "No Price Over 5.5",
              "side": "over", "point": 5.5, "edge": 0.50, "odds": None, "book": None,
              "model_prob": 0.80, "market_fair_prob": 0.30, "ev_per_unit": 0.4}]
    cands = be._floor_clearing_sides(_board(), 0.06, ledger_closed=frozenset(), extra_rows=props)
    labels = [c.get("label") for c in cands]
    assert "Some Arm Over 6.5" in labels and "No Price Over 5.5" not in labels, (
        "a props row with no taken price is not a candidate; one with a price is")
    slots, _, meta = be.provisional_picks(_board(), odds_priceable=True, extra_candidates=props)
    assert slots["pick_of_the_day"]["market"] == "props_pitcher_strikeouts", (
        "the highest model probability in band wins regardless of market")
    assert meta["market_policy"] == "any"


# ── the gated state, still pinned ─────────────────────────────────────────────
def test_gated_predicate_excludes_exactly_the_two_dispersion_sensitive_markets(gated):
    assert bm.market_is_publishable("moneyline") is True
    assert bm.market_is_publishable("runline") is False
    assert bm.market_is_publishable("total") is False
    assert bm.market_is_publishable(None) is True


def test_gated_predicate_is_case_insensitive(gated):
    assert bm.market_is_publishable("Runline") is False
    assert bm.market_is_publishable("TOTAL") is False


def test_gated_predicate_lifts_itself_when_the_correction_is_served(gated, monkeypatch):
    monkeypatch.setattr(bm, "SERVE_RUN_DISPERSION", True)
    assert bm.market_is_publishable("runline") is True
    assert bm.market_is_publishable("total") is True
    assert bm.market_is_dispersion_sensitive("total") is False


def test_gated_slot_selection_emits_no_runline_or_total(gated):
    cands = be._floor_clearing_sides(_board(), 0.06, ledger_closed=frozenset())
    assert {c["market"] for c in cands} == {"moneyline"}, cands
    slots, _, _ = be.provisional_picks(_board(), odds_priceable=True)
    for row in slots.values():
        if row is not None:
            assert row["market"] == "moneyline"


def test_gated_append_record_refuses_an_excluded_market(gated, tmp_path):
    p = tmp_path / "record.json"
    p.write_text("[]", encoding="utf-8")
    rows = [{"bet_id": "a", "market": "h2h", "side": "home"},
            {"bet_id": "b", "market": "spreads", "side": "home"},
            {"bet_id": "c", "market": "totals", "side": "over"}]
    out = be.append_record(rows, path=p, ledger_closed=frozenset())
    assert [r["bet_id"] for r in out] == ["a"]
    assert [r["bet_id"] for r in json.loads(p.read_text(encoding="utf-8"))] == ["a"]


# ── invariants in either state ───────────────────────────────────────────────
def test_the_shadow_ledger_is_deliberately_not_excluded():
    """The ledger is the instrument that accrues the settled outcomes needed to
    resolve the dispersion gate. Excluding runline/total THERE would delete the only
    evidence that could ever lift the exclusion (owner decision 2026-08-14). A reader
    who 'completes' the exclusion by editing the ledger must confront this test."""
    src = (ROOT / "betting_shadow.py").read_text(encoding="utf-8")
    assert "market_is_publishable" not in src, (
        "betting_shadow must not consult the dispersion predicate; the ledger keeps "
        "recording every market on purpose")
    payload = {"slate_date": "2026-08-14", "status": {"odds_feed": "ok"},
               "team_bets": _board()}
    cands = bs.candidates_from_board(payload, min_edge=0.06)
    assert {c["market"] for c in cands} == {"moneyline", "runline", "total"}


def test_the_docstring_states_both_decisions():
    doc = bm.__doc__ or ""
    assert "2026-08-14" in doc and "2026-09-05" in doc
    assert "SLOT_MARKET_POLICY" in doc
