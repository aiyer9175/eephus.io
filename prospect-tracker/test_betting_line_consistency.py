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

TWO MORE WAYS THE SIDES CAN DESCRIBE DIFFERENT BETS (2026-08-09, found by
replaying .cache/odds/2026-08-09-0133.json).

  D12. WHICH book supplied the de-vigged fair probabilities was decided by dict
  iteration order, which is API response order. That book sets the denominator
  of every edge in the game. Measured on that file: h2h hold ran from 1.00% to
  6.38% inside ONE game, and on CHC at KCR the first book (draftkings, 6.377%)
  gave fair_home 0.9277 while the tightest (fanduel, 1.000%) gave 0.9505. A 2.28
  point swing in the denominator, decided by nothing, against a 6 point floor.

  D3. The Under was priced as `1.0 - p_over`, and p_over is P(total >= L+1). On
  a whole-number line that hands the Under the entire push mass. Measured on COL
  at STL at lam_total 9.380: Under 9.0 read 0.53745 against a true P(<= 8) of
  0.40671. Four of the 23 events on the live board carried a whole number, and
  the published "Under 10.0 at -102, edge +0.1308" was this defect end to end:
  the honest number is +0.0783.

TWO MORE, FOUND BY THE ADVERSARIAL PASS OVER THE FIX ITSELF (2026-08-09).

  R1. The push reached `p_push` and the two side probabilities and stopped
  there. `ev_per_unit` still read p*(d-1) - (1-p), which charges a full unit for
  a refund, so every whole-number total's EV was overstated by exactly
  1 / (1 - p_push). Measured on the board replayed out of
  .cache/odds/2026-08-09-0133.json: 1.1422x on CHC at KCR's total of 10.0,
  1.1506x on NYM at PIT's 8.0 and 1.1617x on TOR at PHI's 8.0. Both slot rankers
  and the legacy `pick_of_the_day` select on that field, so a whole number
  outranked a half point at the same edge.

  R2. The min-hold rule rewards a book that has simply not reposted: hold
  measures two prices against each other and cannot see that they describe a
  market that has moved. A -105/-105 quote holds 2.439%, beats every live book
  in the game, and hands the de-vig a fair probability of 0.500 on a market
  whose consensus is 0.691.

WHAT THESE TESTS HOLD
  1. The line is chosen by book COUNT, before any price shopping.
  2. A book on a different line cannot supply a price for this one.
  3. A book on a different line cannot supply the de-vigged fair probabilities.
  4. Price shopping still works WITHIN the agreed line, which is the whole point
     of shopping and must not be lost to the fix.
  5. The exact NYM at CLE snapshot no longer produces a fabricated edge.
  6. The de-vig book is the tightest hold on the agreed line, not the first one
     the API happened to return, and a quote outside the hold band is refused.
  7. A whole-number total prices its push, and its two sides are conditional on
     the push not landing. A half-point total does not move by one bit.
  8. The published EV carries the push, the pre-push number ships beside it, and
     a whole number cannot outrank a half point at an identical edge.
  9. A quote that lags the market, or that sits far from the market's own
     consensus, cannot set the denominator. Neither guard touches a real book on
     either cached snapshot.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")
bm = pytest.importorskip("betting_model")

ROOT = Path(__file__).parent
REAL_SNAPSHOT = ROOT / ".cache" / "odds" / "2026-08-09-0133.json"


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


# ===========================================================================
# D12: the de-vig book is the tightest hold, not the first response
# ===========================================================================
def _h2h(home_price, away_price, title="B"):
    return {"title": title, "last_update": "2026-08-09T01:33:00Z",
            "h2h": {"home": home_price, "away": away_price}}


def _h2h_event(books):
    return {"event_id": "e3", "home_team": "Kansas City Royals",
            "away_team": "Chicago Cubs", "home_org": "KCR", "away_org": "CHC",
            "books": books}


def test_the_devig_book_is_the_tightest_hold_not_the_first_one_returned():
    """`aaa_wide` is first in response order AND first alphabetically, so
    neither the old rule nor a lazy tiebreak can produce the right answer by
    accident. The two books disagree about fair_home by 0.76 of a point, which
    is what the choice is worth on this fixture."""
    ev = _h2h_event({"aaa_wide": _h2h(-140, 110), "zzz_tight": _h2h(-132, 122)})
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["fair_book"] == "zzz_tight"
    assert mv["fair_book_rule"] == "min_hold"
    assert mv["hold_pct"] == pytest.approx(1.942, abs=5e-4)
    assert mv["fair"]["home"] == pytest.approx(0.55813, abs=5e-6)
    assert mv["n_books_on_line"] == 2 and mv["n_books_hold_rejected"] == 0
    assert mv["hold_range"] == [1.942, 5.952]
    wide = be._market_view(_h2h_event({"aaa_wide": _h2h(-140, 110)}),
                           "h2h", ("home", "away"))
    assert wide["fair"]["home"] == pytest.approx(0.55056, abs=5e-6), (
        "the book that used to win by arriving first prices this game 0.0076 "
        "lower, and every edge in the game rides that difference")


def test_a_tie_on_hold_breaks_by_book_key():
    """Two books at an identical hold must resolve the same way on every
    rebuild, or the whole board moves between runs for no reason."""
    ev = _h2h_event({"zzz": _h2h(-110, -110), "aaa": _h2h(-110, -110)})
    assert be._market_view(ev, "h2h", ("home", "away"))["fair_book"] == "aaa"


def test_a_book_at_an_impossible_hold_is_rejected():
    """-10000 against -950 is a 89.486% hold. That is a stale or bogus quote,
    not a market, and it cannot be allowed to set a denominator."""
    ev = _h2h_event({"aaa_bogus": _h2h(-10000, -950), "zzz_real": _h2h(-110, -110)})
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["fair_book"] == "zzz_real"
    assert mv["n_books_hold_rejected"] == 1
    assert mv["hold_range"] == [4.762, 89.486]
    assert mv["fair"]["home"] == pytest.approx(0.5, abs=1e-9)


def test_a_negative_hold_is_rejected_as_an_arbitrage():
    """+110 both ways sums to 0.952. No book posts an arb on purpose, so one of
    the two prices is stale and the pair is not a market."""
    ev = _h2h_event({"aaa_arb": _h2h(110, 110), "zzz_real": _h2h(-120, 100)})
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["fair_book"] == "zzz_real"
    assert mv["n_books_hold_rejected"] == 1


def test_every_book_rejected_falls_back_and_says_so():
    """The fallback is the OLD behaviour, first book in response order, and the
    block has to name it so a reader is not told a tight market exists."""
    ev = _h2h_event({"aaa_bogus": _h2h(-10000, -950)})
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["fair_book"] == "aaa_bogus"
    assert mv["fair_book_rule"] == "first_book_all_holds_rejected"
    assert mv["n_books_on_line"] == 1 and mv["n_books_hold_rejected"] == 1


def test_the_real_runline_snapshot_picks_the_tightest_of_the_five_on_the_line():
    """FanDuel is off the agreed line and is excluded before hold is even
    considered, so the two rules compose in the right order."""
    mv = be._market_view(REAL, "spreads", ("home", "away"))
    assert mv["fair_book"] == "lowvig"
    assert mv["n_books_on_line"] == 5, "fanduel is off the line and not counted"
    assert mv["hold_range"] == [2.948, 4.779]
    assert mv["n_books_hold_rejected"] == 0


# ===========================================================================
# D3: a whole-number total pushes, and the Under is not 1 - p_over
# ===========================================================================
def _pmf(lam=9.38):
    return bm.total_distribution(lam / 2.0, lam / 2.0)


def _legacy_over(pmf, line):
    """The `over` callable's expression, copied so drift is visible here."""
    need = math.floor(line) + 1 if line != int(line) else int(line) + 1
    return sum(pmf[k] for k in range(need, len(pmf)))


def test_a_half_point_total_is_unchanged_to_full_float_equality():
    """Every half-point row on the board must be byte-identical to what shipped
    before the fix, or this is a repricing rather than a repair."""
    pmf = _pmf()
    for line in (6.5, 7.5, 8.5, 9.5, 10.5, 11.5):
        r = bm.total_side_probabilities(pmf, line)
        over = _legacy_over(pmf, line)
        assert r["p_over"] == over, line
        assert r["p_under"] == 1.0 - over, line
        assert r["p_push"] == 0.0, line


def test_a_whole_number_total_prices_its_push():
    pmf = _pmf()
    r = bm.total_side_probabilities(pmf, 9.0)
    assert r["p_push"] == pmf[9], "the push is the pmf mass ON the line"
    assert r["p_push"] == pytest.approx(0.13073, abs=5e-6)


def test_the_two_sides_of_a_whole_number_sum_to_one_without_the_push():
    """They are conditional on no push, because the de-vigged two-way market
    they are scored against is a no-push market: the book refunds when the
    total lands."""
    pmf = _pmf()
    r = bm.total_side_probabilities(pmf, 9.0)
    assert r["p_over"] + r["p_under"] == pytest.approx(1.0, abs=1e-12)
    assert r["p_over"] + r["p_under"] + r["p_push"] > 1.0


def test_the_under_at_a_whole_number_is_strictly_less_than_one_minus_the_over():
    """THE REGRESSION, stated as the arithmetic. `1 - p_over` is P(<= L), which
    is the Under PLUS the push. The fixture pins lam_total at a round 9.38, so
    these sit a hair off the 0.53745 / 0.40671 measured on the live COL at STL
    row, whose lambda is 9.38 only to the printed digit."""
    pmf = _pmf()
    r = bm.total_side_probabilities(pmf, 9.0)
    naive = 1.0 - _legacy_over(pmf, 9.0)
    assert r["p_under"] < naive
    assert naive == pytest.approx(0.53747, abs=5e-6)
    unconditional_under = sum(pmf[k] for k in range(0, 9))
    assert unconditional_under == pytest.approx(0.40674, abs=5e-6)
    assert naive - unconditional_under == pytest.approx(r["p_push"], abs=1e-9)


def test_the_export_publishes_the_push_on_a_whole_number_total():
    """The page has to be able to say how often this bet is a refund."""
    teams = {"_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
             "KCR": {"z_off": 0.10, "offense_plus": 102.0, "bullpen_plus": 101.0,
                     "rotation_plus": 100.0, "sp_ip_share": 0.60},
             "CHC": {"z_off": 0.05, "offense_plus": 101.0, "bullpen_plus": 100.0,
                     "rotation_plus": 100.0, "sp_ip_share": 0.60}}
    ev = {"event_id": "e4", "home_team": "Kansas City Royals",
          "away_team": "Chicago Cubs", "home_org": "KCR", "away_org": "CHC",
          "commence_time": "2026-08-09T18:10:00Z",
          "books": {"lowvig": {"title": "LowVig", "last_update": "2026-08-09T01:33:00Z",
                               "totals": {"over": {"price": -113, "point": 10.0},
                                          "under": {"price": -102, "point": 10.0}}}}}
    g = {"game_pk": 3, "date": "2026-08-09", "datetime": "2026-08-09T18:10:00Z",
         "status": "Preview", "home": {"org": "KCR"}, "away": {"org": "CHC"}}
    from datetime import datetime, timezone
    rows = be.team_bets([g], [ev], teams=teams, parks={"KCR": 1.0}, starters={},
                        now=datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc))
    tot = rows[0]["total"]
    assert tot["line"] == 10.0
    assert tot["p_push"] is not None and tot["p_push"] > 0.05
    over, under = tot["sides"]
    assert over["model_prob"] + under["model_prob"] == pytest.approx(1.0, abs=2e-5)
    assert over["edge"] == pytest.approx(-under["edge"], abs=2e-5), (
        "a two-way no-push market must produce mirrored edges")


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


# ===========================================================================
# R1: a push is a refund, not a loss, and ev_per_unit is what gets ranked
# ===========================================================================
# One market, one price, one model probability. The only thing that differs
# between the two rows below is whether the posted number can land on the total.
_EV_MARKET = {"best": {"over": {"book": "b", "book_title": "B", "decimal": 1.9091,
                                "price": -110, "point": 9.0}},
              "fair": {"over": 0.50}}


def test_a_half_point_side_is_untouched_by_the_push_adjustment():
    row = be._priced_side("over", "Over 9.5", 0.56, _EV_MARKET)
    assert row["p_push"] is None
    assert row["ev_per_unit"] == pytest.approx(0.0691, abs=5e-6)
    assert row["ev_per_unit"] == row["ev_per_unit_if_no_push"], (
        "a line that cannot push must not move by one bit")


def test_a_whole_number_side_pays_the_push_out_of_its_ev():
    """THE REGRESSION. (1 - p_push) * [p_cond*(d-1) - (1-p_cond)]. The bracket is
    the EV given the bet resolves; the factor is how often it does."""
    row = be._priced_side("over", "Over 9.0", 0.56, _EV_MARKET, p_push=0.13)
    assert row["p_push"] == 0.13
    assert row["ev_per_unit_if_no_push"] == pytest.approx(0.0691, abs=5e-6)
    assert row["ev_per_unit"] == pytest.approx(0.06011, abs=5e-6)
    # Both fields ship rounded to 5 places, so the ratio of the published pair
    # sits a few parts in 10,000 off the exact factor. The tolerance is the
    # rounding and nothing else.
    assert (row["ev_per_unit_if_no_push"] / row["ev_per_unit"]
            == pytest.approx(1.0 / (1.0 - 0.13), abs=5e-4)), (
        "the overstatement is exactly 1 / (1 - p_push)")


def test_kelly_is_not_push_adjusted():
    """Kelly is a RATIO of the same two terms, so (1 - p_push) cancels out of
    it. Scaling it here would be a second, wrong adjustment."""
    half = be._priced_side("over", "Over 9.5", 0.56, _EV_MARKET)
    whole = be._priced_side("over", "Over 9.0", 0.56, _EV_MARKET, p_push=0.13)
    assert whole["kelly_full"] == half["kelly_full"]


def test_a_whole_number_cannot_outrank_a_half_point_at_the_same_edge():
    """THE PIN THE FIX EXISTS FOR. Same price, same model probability, same
    edge: the side that refunds part of the time is worth strictly less, and
    `_longshot_rank` and the legacy max-EV selector both have to say so."""
    half = be._priced_side("over", "Over 9.5", 0.56, _EV_MARKET)
    whole = be._priced_side("over", "Over 9.0", 0.56, _EV_MARKET, p_push=0.13)
    assert half["edge"] == whole["edge"]
    assert whole["ev_per_unit"] < half["ev_per_unit"]
    assert [r["label"] for r in sorted([whole, half], key=be._longshot_rank)] == \
           ["Over 9.5", "Over 9.0"]
    assert max([whole, half], key=lambda r: r["ev_per_unit"])["label"] == "Over 9.5"


def test_the_export_push_adjusts_a_whole_number_total_end_to_end():
    """The same KCR at CHC fixture the push test above uses, read through
    `team_bets` so the wiring is pinned and not just the primitive."""
    teams = {"_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
             "KCR": {"z_off": 0.10, "offense_plus": 102.0, "bullpen_plus": 101.0,
                     "rotation_plus": 100.0, "sp_ip_share": 0.60},
             "CHC": {"z_off": 0.05, "offense_plus": 101.0, "bullpen_plus": 100.0,
                     "rotation_plus": 100.0, "sp_ip_share": 0.60}}
    ev = {"event_id": "e4", "home_team": "Kansas City Royals",
          "away_team": "Chicago Cubs", "home_org": "KCR", "away_org": "CHC",
          "commence_time": "2026-08-09T18:10:00Z",
          "books": {"lowvig": {"title": "LowVig", "last_update": "2026-08-09T01:33:00Z",
                               "totals": {"over": {"price": -113, "point": 10.0},
                                          "under": {"price": -102, "point": 10.0}}}}}
    g = {"game_pk": 3, "date": "2026-08-09", "datetime": "2026-08-09T18:10:00Z",
         "status": "Preview", "home": {"org": "KCR"}, "away": {"org": "CHC"}}
    rows = be.team_bets([g], [ev], teams=teams, parks={"KCR": 1.0}, starters={},
                        now=datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc))
    tot = rows[0]["total"]
    for side in tot["sides"]:
        assert side["p_push"] == tot["p_push"], (
            "the push travels on the row, so a slot lifted out of the payload "
            "still says how often the bet is a refund")
        assert abs(side["ev_per_unit"]) < abs(side["ev_per_unit_if_no_push"]), (
            "both sides of a pushable total shrink toward zero")
        # Reconstructed from the two published, 5-place-rounded fields, so the
        # tolerance is the rounding of three numbers and nothing else.
        assert side["ev_per_unit"] == pytest.approx(
            (1.0 - tot["p_push"]) * side["ev_per_unit_if_no_push"], abs=1e-5)


def test_a_runline_carries_no_push_at_all():
    """A -1.5 runline cannot land on the number. A p_push that is anything but
    None there would be a claim about a game state that does not exist."""
    mv = be._market_view(REAL, "spreads", ("home", "away"))
    row = be._priced_side("home", "CLE -1.5", 0.55, mv)
    assert row["p_push"] is None
    assert row["ev_per_unit"] == row["ev_per_unit_if_no_push"]


# ===========================================================================
# R2: a tight hold can be a book that has not updated
# ===========================================================================
_LIVE = "2026-08-09T18:22:00Z"
_LAGGED = "2026-08-09T17:57:00Z"          # 25 minutes behind, past the 15 limit


def _q(home, away, last_update, title="B"):
    return {"title": title, "last_update": last_update,
            "h2h": {"home": home, "away": away}}


def _fabricated(stale_stamp):
    """Three live books agreeing the home side is about a 0.69 favourite, plus
    one -105/-105 quote. That quote holds 2.439%, which beats all three, and
    de-vigs to exactly 0.500."""
    return {"event_id": "e9", "home_team": "Milwaukee Brewers",
            "away_team": "Minnesota Twins", "home_org": "MIL", "away_org": "MIN",
            "books": {"live_a": _q(-260, 210, _LIVE),
                      "live_b": _q(-255, 205, _LIVE),
                      "live_c": _q(-265, 212, _LIVE),
                      "zzz_frozen": _q(-105, -105, stale_stamp)}}


def test_the_frozen_quote_would_have_won_on_hold_alone():
    """The premise, stated as arithmetic, so the guards below are measured
    against something rather than asserted into existence."""
    decs = {s: bi.american_to_decimal(-105) for s in ("home", "away")}
    assert bm.hold_pct(decs) == pytest.approx(2.439, abs=5e-4)
    assert bm.devig(decs)["home"] == pytest.approx(0.5, abs=1e-9)
    live = {"home": bi.american_to_decimal(-260), "away": bi.american_to_decimal(210)}
    assert bm.hold_pct(live) == pytest.approx(4.480, abs=5e-4), (
        "every live book in the fixture holds wider than the frozen one")


def test_a_lagging_quote_cannot_set_the_denominator():
    """THE REGRESSION. 25 minutes behind the freshest book on the same market."""
    mv = be._market_view(_fabricated(_LAGGED), "h2h", ("home", "away"))
    assert mv["fair_book"] == "live_a"
    assert mv["n_books_stale_rejected"] == 1
    assert mv["n_books_hold_rejected"] == 0 and mv["n_books_consensus_rejected"] == 0
    assert mv["max_book_lag_minutes"] == 25.0
    assert mv["fair"]["home"] == pytest.approx(0.69125, abs=5e-6)
    assert 0.72 - mv["fair"]["home"] == pytest.approx(0.02875, abs=5e-6), (
        "the frozen quote manufactured a +0.220 edge against a 0.06 floor; the "
        "honest number is +0.029")


def test_a_quote_far_from_consensus_cannot_set_the_denominator():
    """THE SECOND HALF, and the half a timestamp cannot see. Identical prices to
    the test above and an identical `last_update` on every book, so staleness has
    nothing to catch and only the consensus distance is left."""
    mv = be._market_view(_fabricated(_LIVE), "h2h", ("home", "away"))
    assert mv["fair_book"] == "live_a"
    assert mv["n_books_stale_rejected"] == 0
    assert mv["n_books_consensus_rejected"] == 1
    assert mv["max_book_lag_minutes"] == 0.0
    assert mv["fair"]["home"] == pytest.approx(0.69125, abs=5e-6)


def test_the_rejection_counts_are_published_and_add_up():
    """A rejection nobody can see is a rule nobody can check. The hold count was
    computed from the day the band shipped and published nowhere."""
    mv = be._market_view(_fabricated(_LAGGED), "h2h", ("home", "away"))
    rejected = (mv["n_books_hold_rejected"] + mv["n_books_stale_rejected"]
                + mv["n_books_consensus_rejected"])
    assert mv["n_books_on_line"] == 4 and rejected == 1
    assert mv["fair_book_lag_minutes"] == 0.0
    assert mv["fair_book_consensus_distance"] is not None


def test_a_book_with_no_last_update_is_never_called_stale():
    """The stamp is the book's own. Its absence is the parser's silence, not
    evidence, and refusing on it would blank healthy markets."""
    ev = _fabricated(_LAGGED)
    ev["books"]["zzz_frozen"] = {"title": "B", "h2h": {"home": -105, "away": -105}}
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["n_books_stale_rejected"] == 0
    assert mv["n_books_consensus_rejected"] == 1, (
        "the consensus guard still catches it, which is why there are two")


def test_the_consensus_guard_needs_three_books():
    """With two books the median IS the midpoint and both sit the same distance
    from it, so the test is vacuous and must not fire."""
    ev = {"event_id": "e10", "home_team": "H", "away_team": "A",
          "home_org": "MIL", "away_org": "MIN",
          "books": {"a": _q(-260, 210, _LIVE), "zzz": _q(-105, -105, _LIVE)}}
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert be.CONSENSUS_MIN_BOOKS == 3
    assert mv["n_books_consensus_rejected"] == 0
    assert mv["fair_book"] == "zzz", (
        "two books cannot outvote each other; the tightest hold still wins and "
        "n_books_on_line is how a reader sees the evidence is thin")


def test_a_lone_book_cannot_lag_itself():
    """The reference is the freshest book ON THIS MARKET. With one book that is
    the book itself, so a market with a single quote is never called stale and
    keeps the behaviour it had before the guard."""
    ev = {"event_id": "e11", "home_team": "H", "away_team": "A",
          "home_org": "MIL", "away_org": "MIN",
          "books": {"only": _q(-105, -105, _LAGGED)}}
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["n_books_stale_rejected"] == 0
    assert mv["fair_book_rule"] == "min_hold"
    assert mv["max_book_lag_minutes"] == 0.0


@pytest.fixture(scope="module")
def real_pregame_events():
    if not REAL_SNAPSHOT.exists():
        pytest.skip(".cache/odds/2026-08-09-0133.json is not in this checkout "
                    "(.cache is gitignored)")
    wrap = json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8"))
    cap = datetime.fromisoformat(str(wrap["captured_at"]).replace("Z", "+00:00"))
    out = []
    for e in bi.parse_events(wrap):
        t = e.get("commence_time")
        if t and datetime.fromisoformat(str(t).replace("Z", "+00:00")) > cap:
            out.append(e)
    return out


def test_neither_guard_rejects_a_real_book_on_the_real_board(real_pregame_events):
    """THE COST SIDE OF THE MEASUREMENT. Both thresholds sit above anything
    either cached snapshot contains on a pregame market: max lag 1.017 minutes
    against a 15 minute limit, max consensus distance 0.0253 against 0.05. If a
    future threshold is tightened until it starts refusing real books this is
    what fails, and it should: the books that WIN the min-hold rule are the
    reduced-juice books and they are also the slowest to repost."""
    assert real_pregame_events, "the file must hold pregame events to measure"
    n_markets = n_stale = n_consensus = 0
    worst_lag = 0.0
    for ev in real_pregame_events:
        for market, sides in (("h2h", ("home", "away")),
                              ("spreads", ("home", "away")),
                              ("totals", ("over", "under"))):
            mv = be._market_view(ev, market, sides)
            if not mv:
                continue
            n_markets += 1
            n_stale += mv["n_books_stale_rejected"]
            n_consensus += mv["n_books_consensus_rejected"]
            worst_lag = max(worst_lag, mv["max_book_lag_minutes"] or 0.0)
    assert n_markets >= 30, f"only {n_markets} pregame markets parsed"
    assert n_stale == 0, f"{n_stale} real books refused as stale"
    assert n_consensus == 0, f"{n_consensus} real books refused on consensus"
    assert worst_lag == pytest.approx(1.017, abs=5e-3), (
        "the measured worst lag on this file's pregame markets")
    assert worst_lag < be.STALE_BOOK_MAX_LAG_MINUTES
