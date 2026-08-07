# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The shadow ledger has to be evidence, or it is worse than nothing.

WHY IT EXISTS. The third validation gate wants settled bets carrying a taken
price; `sweep_min_edge` needs 100 of them. Nothing produced any, and
`min_edge_gate(..., graded_bets=None)` was never passed anything, so the loop
was closed against itself: publishing a pick needs min_edge, min_edge needs
settled picks, settled picks need a published pick.

A paper ledger breaks that circle only if it cannot be gamed. These tests are
the part that makes it worth citing.

WHAT THEY HOLD
  1. A bet is recorded at the price ACTUALLY ON THE BOARD, never at the model's
     own fair line. A paper bet at a price nobody offered is a lie.
  2. No slate without a captured odds snapshot may be recorded at all.
  3. The ledger is append-only except for settlement fields, and a settled
     result can never be revised.
  4. Settlement grades moneyline, runline and total correctly, including pushes.
  5. Pushes are excluded from the min-edge sweep rather than scored as losses.
  6. Rates are None over an empty set, never 0.0.
  7. Recording is idempotent per slate, so a re-run cannot inflate the sample.
  8. A PUBLISHED SLOT ALWAYS REACHES THE LEDGER, and carries the tag of the rule
     that chose it. The headline slot selects on model probability inside a
     price band, so it can sit below the top of the EV ranking by construction;
     if the EV ranking were the only way in, the site could publish a pick that
     never became evidence. The tag is what lets the future min-edge sweep
     condition on the selection rule instead of pooling three of them.
"""
from __future__ import annotations

import json

import pytest

bs = pytest.importorskip("betting_shadow")


def _payload(edge=0.10, odds=150, book="draftkings", feed="ok"):
    return {
        "slate_date": "2026-08-06",
        "status": {"odds_feed": feed},
        "team_bets": [{
            "game_pk": 900,
            "home": {"org": "PHI"}, "away": {"org": "WSN"},
            "moneyline": [
                {"side": "away", "label": "WSN", "edge": edge, "odds": odds,
                 "decimal": 2.5, "book": book, "model_prob": 0.40,
                 "market_fair_prob": 0.30, "ev_per_unit": 0.5},
                {"side": "home", "label": "PHI", "edge": -0.10, "odds": -180,
                 "decimal": 1.55, "book": book},
            ],
            "runline": [
                {"side": "away", "label": "WSN +1.5", "point": 1.5, "edge": 0.09,
                 "odds": -120, "decimal": 1.83, "book": book, "ev_per_unit": 0.2},
            ],
            "total": {"line": 9.0, "sides": [
                {"side": "under", "label": "Under 9.0", "point": 9.0,
                 "edge": 0.08, "odds": -115, "decimal": 1.87, "book": book,
                 "ev_per_unit": 0.1},
            ]},
        }],
    }


@pytest.fixture
def led(tmp_path):
    return tmp_path / "shadow.json"


def test_a_slate_with_no_odds_snapshot_is_never_recorded(led):
    """A paper bet needs a real captured price. Recording the model's own fair
    line here would be inventing the market, which is the one thing that would
    make this ledger worthless."""
    out = bs.record_slate(_payload(feed="no_snapshot"), min_edge=0.05, path=led)
    assert out["written"] == 0
    assert "no odds snapshot" in out["reason"]
    assert not led.exists()


def test_a_side_with_no_book_price_is_skipped(led):
    p = _payload()
    p["team_bets"][0]["moneyline"][0]["book"] = None
    out = bs.record_slate(p, min_edge=0.05, path=led)
    kept = [r["selection"] for r in out.get("rows", [])]
    assert "WSN" not in kept, "a side with no book cannot be paper-bet"


def test_only_sides_clearing_the_floor_are_recorded(led):
    out = bs.record_slate(_payload(), min_edge=0.095, path=led)
    assert out["written"] == 1, "only the 0.10 moneyline clears a 0.095 floor"
    assert out["rows"][0]["selection"] == "WSN"


def test_the_recorded_price_is_the_board_price(led):
    out = bs.record_slate(_payload(odds=175), min_edge=0.05, path=led)
    row = next(r for r in out["rows"] if r["selection"] == "WSN")
    assert row["odds_at_post"] == 175 and row["book"] == "draftkings"


def test_the_threshold_and_gate_state_are_frozen_onto_each_row(led):
    """A row logged under a policy floor must never later be mistaken for one
    logged under a measured threshold; otherwise the sample silently mixes two
    different selection rules."""
    out = bs.record_slate(_payload(), min_edge=0.06,
                          gate_state={"provisional": True, "basis": "floor"},
                          path=led)
    r = out["rows"][0]
    assert r["min_edge_used"] == 0.06
    assert r["provisional"] is True
    assert r["gate_state"]["basis"] == "floor"


def test_recording_is_idempotent(led):
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    again = bs.record_slate(_payload(), min_edge=0.05, path=led)
    assert again["written"] == 0, "a re-run must not inflate the sample"
    assert "already logged" in again["reason"]


def test_the_ledger_refuses_a_mutation(led):
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    rows = bs.load(led)
    rows[0] = {**rows[0], "odds_at_post": 9999}
    with pytest.raises(bs.ShadowLedgerError, match="odds_at_post"):
        bs.write(rows, path=led)


def test_the_ledger_refuses_a_deletion(led):
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    with pytest.raises(bs.ShadowLedgerError, match="shrink"):
        bs.write([], path=led)


def test_a_settled_result_cannot_be_revised(led):
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    bs.settle(games=[{"game_pk": 900, "home_runs": 1, "away_runs": 7}], path=led)
    rows = bs.load(led)
    assert rows[0]["result"] == "won"
    rows[0] = {**rows[0], "result": "lost"}
    with pytest.raises(bs.ShadowLedgerError, match="already settled"):
        bs.write(rows, path=led)


@pytest.mark.parametrize("hr,ar,ml,rl,tot", [
    (1, 7, "won", "won", "lost"),     # WSN wins 7-1: ML won, +1.5 won, total 8 under 9 -> under won...
    (7, 1, "lost", "lost", "lost"),   # PHI wins 7-1: total 8 -> under wins
])
def test_settlement_grades_each_market(led, hr, ar, ml, rl, tot):
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    bs.settle(games=[{"game_pk": 900, "home_runs": hr, "away_runs": ar}], path=led)
    by = {r["market"]: r for r in bs.load(led)}
    assert by["moneyline"]["result"] == ml
    assert by["runline"]["result"] == rl
    # total is 8 in both rows above, which is under 9.0
    assert by["total"]["result"] == "won"


def test_a_tie_on_the_total_is_a_push_and_leaves_the_stake(led):
    p = _payload()
    p["team_bets"][0]["total"]["sides"][0]["point"] = 8.0
    bs.record_slate(p, min_edge=0.05, path=led)
    bs.settle(games=[{"game_pk": 900, "home_runs": 4, "away_runs": 4}], path=led)
    tot = next(r for r in bs.load(led) if r["market"] == "total")
    assert tot["result"] == "push" and tot["profit_units"] == 0.0


def test_pushes_are_excluded_from_the_sweep_not_scored_as_losses(led):
    """A push returns the stake. Counting it as a loss would understate every
    threshold's ROI and make the gate harder to clear for a reason that has
    nothing to do with skill."""
    p = _payload()
    p["team_bets"][0]["total"]["sides"][0]["point"] = 8.0
    bs.record_slate(p, min_edge=0.05, path=led)
    bs.settle(games=[{"game_pk": 900, "home_runs": 4, "away_runs": 4}], path=led)
    graded = bs.graded_bets(path=led)
    assert all(isinstance(g["won"], bool) for g in graded)
    assert len(graded) == len([r for r in bs.load(led)
                               if r["result"] in ("won", "lost")])


# ---- slot tagging (2026-08-07, two published slots) ------------------------
def _slot_payload():
    """A board whose headline slot is NOT the top EV row.

    The moneyline at +450 has the best EV and the worst model probability; the
    runline is what the headline rule picks. That disagreement is the whole
    reason the slots are handed in separately."""
    p = _payload(edge=0.10, odds=450)
    p["team_bets"][0]["moneyline"][0].update(
        {"decimal": 5.5, "model_prob": 0.30, "ev_per_unit": 0.65})
    p["team_bets"][0]["runline"][0].update({"model_prob": 0.70})
    p["pick_of_the_day"] = dict(p["team_bets"][0]["runline"][0],
                                game_pk=900, market="runline",
                                slot="pick_of_the_day")
    p["longshot_of_the_day"] = dict(p["team_bets"][0]["moneyline"][0],
                                    game_pk=900, market="moneyline",
                                    slot="longshot_of_the_day")
    return p


def test_a_published_slot_is_logged_even_when_it_is_not_top_of_the_ev_board(led):
    out = bs.record_slate(_slot_payload(), min_edge=0.05, path=led)
    by_slot = {r["slot"]: r for r in out["rows"]}
    assert by_slot["potd_band"]["market"] == "runline"
    assert by_slot["longshot"]["odds_at_post"] == 450
    assert by_slot["ev_rank"], "the EV ranking still contributes rows"


def test_slot_tags_are_the_three_selection_rules(led):
    out = bs.record_slate(_slot_payload(), min_edge=0.05, path=led)
    assert set(out["by_slot"]) <= {"potd_band", "longshot", "ev_rank"}
    assert out["by_slot"]["potd_band"] == 1 and out["by_slot"]["longshot"] == 1


def test_a_slate_with_no_published_slots_tags_everything_by_ev(led):
    """The payload shape from before the two-slot builder. Nothing is tagged as
    a slot pick, because nothing was published as one."""
    out = bs.record_slate(_payload(), min_edge=0.05, path=led)
    assert {r["slot"] for r in out["rows"]} == {"ev_rank"}


def test_the_slate_budget_is_five(led):
    """Two slot picks plus the top three by EV. A slate may not log fewer rows
    than it publishes."""
    assert bs.MAX_PER_SLATE == 5
    cands = bs.candidates_from_board(_slot_payload(), min_edge=0.05)
    assert len(cands) <= bs.MAX_PER_SLATE


def test_summary_splits_by_slot_and_never_pools_the_rules(led):
    """The three tags select on three different quantities, so a pooled ROI
    across them measures a mixture nobody bet."""
    bs.record_slate(_slot_payload(), min_edge=0.05, path=led)
    bs.settle(games=[{"game_pk": 900, "home_runs": 1, "away_runs": 7}], path=led)
    s = bs.summary(path=led)
    assert set(s["by_slot"]) == {"potd_band", "longshot", "ev_rank"}
    assert s["by_slot"]["potd_band"]["n_settled"] == 1
    assert sum(v["n_rows"] for v in s["by_slot"].values()) == s["n_rows"]


def test_existing_rows_are_never_retagged(led):
    """Rows written before the tag existed carry none, and stamping one on now
    would assert a fact the writer did not know. They count as `untagged`."""
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    rows = bs.load(led)
    rows[0] = {k: v for k, v in rows[0].items() if k != "slot"}
    bs._write(rows, led)
    s = bs.summary(path=led)
    assert s["by_slot"]["untagged"]["n_rows"] == 1
    # And re-running the slate must not rewrite it, because a settled or
    # published row is frozen apart from its settlement fields.
    again = bs.record_slate(_payload(), min_edge=0.05, path=led)
    assert again["written"] == 0


def test_rates_over_an_empty_ledger_are_none(led):
    s = bs.summary(path=led)
    assert s["n_rows"] == 0
    assert s["roi"] is None and s["win_rate"] is None and s["net_units"] is None


def test_graded_bets_is_the_shape_sweep_min_edge_consumes(led):
    bm = pytest.importorskip("betting_model")
    bs.record_slate(_payload(), min_edge=0.05, path=led)
    bs.settle(games=[{"game_pk": 900, "home_runs": 1, "away_runs": 7}], path=led)
    rows = bs.graded_bets(path=led)
    assert rows and set(rows[0]) == {"edge", "decimal", "won"}
    out = bm.sweep_min_edge(rows)          # must not raise on real rows
    assert "min_edge" in out and "reason" in out


def test_the_gate_reads_the_ledger_when_no_rows_are_handed_in(monkeypatch):
    """THE CIRCLE-BREAKER. min_edge_gate was only ever called with None, so the
    third gate could never see any evidence at all."""
    bm = pytest.importorskip("betting_model")
    monkeypatch.setattr(bm, "_shadow_graded_bets",
                        lambda: [{"edge": 0.2, "decimal": 2.0, "won": True}] * 150)
    gate = bm.min_edge_gate({"n_graded": 0})
    g3 = next(g for g in gate["gates"] if g["id"] == "graded_price_history")
    assert g3["have"] == 150, (
        "the gate must consult the shadow ledger; passing None used to mean "
        "zero evidence forever")
