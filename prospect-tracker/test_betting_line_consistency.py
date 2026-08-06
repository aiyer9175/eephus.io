# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Both sides of a priced market must describe the SAME bet.

THE DEFECT THIS PINS (2026-08-06, found by turning the Pick of the Day on).
`_market_view` shopped each side of a market for its best price independently.
Books do not all post the same runline side, and on the live snapshot for
NYM at CLE eight books had the home side at -1.5 while FanDuel had it at +1.5.

The row that came out took its LINE from Bovada (home -1.5, so the away side is
NYM +1.5, model probability 0.7255) and its PRICE from FanDuel (whose away side
is NYM -1.5 at +184, implied 0.3521). Those are opposite bets. The resulting
"edge" was 0.38839, the largest number on the board, and it was the first thing
the provisional Pick of the Day selected.

Totals carry the same exposure: Over 8.5 at one book and Under 9.5 at another
are not two sides of one wager.

Nothing raised. The row was structurally perfect, every field populated, and the
only symptom was an edge too good to be true, on a page whose entire purpose is
to show honest edges.

WHAT THESE TESTS HOLD
  1. The line is chosen by book COUNT, before any price shopping.
  2. A book on a different line cannot supply a price for this one.
  3. A book on a different line cannot supply the de-vigged fair probabilities.
  4. Price shopping still works WITHIN the agreed line, which is the whole point
     of shopping and must not be lost to the fix.
  5. The exact NYM at CLE snapshot no longer produces a fabricated edge.
"""
from __future__ import annotations

import pytest

be = pytest.importorskip("betting_export")


def _ev(books):
    return {"event_id": "e1", "home_team": "Cleveland Guardians",
            "away_team": "New York Mets", "home_org": "CLE", "away_org": "NYM",
            "books": books}


def _sp(home_price, home_point, away_price, away_point, title="B"):
    return {"title": title, "last_update": "2026-08-06T15:19:00Z",
            "spreads": {"home": {"price": home_price, "point": home_point},
                        "away": {"price": away_price, "point": away_point}}}


# The real snapshot, reduced: eight books on home -1.5, FanDuel inverted.
REAL = _ev({
    "bovada":      _sp(180, -1.5, -220, 1.5),
    "lowvig":      _sp(179, -1.5, -204, 1.5),
    "betonlineag": _sp(177, -1.5, -205, 1.5),
    "draftkings":  _sp(170, -1.5, -208, 1.5),
    "betmgm":      _sp(170, -1.5, -210, 1.5),
    "fanduel":     _sp(-225, 1.5, 184, -1.5),
})


def test_the_line_is_decided_by_book_count():
    assert be._consensus_point(REAL, "spreads", ("home", "away")) == -1.5, (
        "five books post home -1.5 and one posts +1.5; the majority line wins")


def test_a_book_on_the_other_line_cannot_supply_the_price():
    """THE REGRESSION. FanDuel's +184 is the best away price in the event, but it
    is a price for NYM -1.5, not the NYM +1.5 the agreed line implies."""
    away = be._best_price_on_line(REAL, "spreads", "away", 1.5)
    assert away is not None
    assert away["book"] != "fanduel", (
        "FanDuel prices the opposite side of the runline here; taking its price "
        "for this line is what manufactured a 38.8 point edge")
    assert away["point"] == 1.5
    assert away["price"] == -204, "best available price ON THE AGREED LINE"


def test_shopping_still_happens_within_the_agreed_line():
    """The fix must not cost the reason for shopping in the first place."""
    home = be._best_price_on_line(REAL, "spreads", "home", -1.5)
    assert home["book"] == "bovada" and home["price"] == 180, (
        "the longest price among books on the agreed line must still win")


def test_the_market_view_pairs_one_line_on_both_sides():
    mv = be._market_view(REAL, "spreads", ("home", "away"))
    assert mv is not None
    hp = mv["best"]["home"]["point"]
    ap = mv["best"]["away"]["point"]
    assert hp == -ap, f"sides must mirror one line, got home {hp} away {ap}"
    assert mv["best"]["away"]["book"] != "fanduel"


def test_the_devig_book_must_also_be_on_the_agreed_line():
    """A book pricing a different line cannot supply this line's fair
    probabilities: its two-sided market is a different bet, and de-vigging it
    would put a fair number on a wager nobody is offering."""
    mv = be._market_view(REAL, "spreads", ("home", "away"))
    assert mv["fair_book"] != "fanduel"
    assert 0.0 < mv["fair"]["home"] < 1.0 and 0.0 < mv["fair"]["away"] < 1.0
    assert abs(sum(mv["fair"].values()) - 1.0) < 1e-6, "de-vig must sum to one"


def test_a_totals_line_mismatch_is_rejected_the_same_way():
    """Over 8.5 and Under 9.5 are not two sides of one bet."""
    ev = {"event_id": "e2", "home_team": "H", "away_team": "A",
          "home_org": "CLE", "away_org": "NYM",
          "books": {
              "a": {"title": "A", "totals": {"over": {"price": -110, "point": 8.5},
                                             "under": {"price": -110, "point": 8.5}}},
              "b": {"title": "B", "totals": {"over": {"price": 140, "point": 9.5},
                                             "under": {"price": -170, "point": 9.5}}},
          }}
    assert be._consensus_point(ev, "totals", ("over", "under")) == 8.5, (
        "ties break to the lower point, deterministically")
    over = be._best_price_on_line(ev, "totals", "over", 8.5)
    assert over["book"] == "a", (
        "book b's +140 is a price for the 9.5 total and must not be shopped "
        "into an 8.5 row")


def test_a_pointless_market_is_unaffected():
    """h2h carries no point and must keep shopping every book."""
    ev = _ev({"a": {"title": "A", "h2h": {"home": -120, "away": 100}},
              "b": {"title": "B", "h2h": {"home": -130, "away": 115}}})
    assert be._consensus_point(ev, "h2h", ("home", "away")) is None
    away = be._best_price_on_line(ev, "h2h", "away", None)
    assert away["book"] == "b" and away["price"] == 115


def test_the_real_snapshot_no_longer_yields_a_fabricated_edge():
    """End to end on the reduced real event: whatever edge survives must be of a
    plausible size. 0.388 was the tell that two different bets had been fused."""
    mv = be._market_view(REAL, "spreads", ("home", "away"))
    # model probability for the away side ON THE AGREED LINE (NYM +1.5)
    p_away_plus = 0.7255
    edge = p_away_plus - mv["fair"]["away"]
    assert edge < 0.15, (
        f"edge {edge:.4f} is still implausibly large; the sides are not on one "
        "line")
