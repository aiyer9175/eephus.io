# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A priced row must describe THIS game, played from THIS moment forward.

TWO DEFECTS THIS PINS, both found on 2026-08-09 by replaying the real snapshot
.cache/odds/2026-08-09-0133.json through the live pipeline.

  D1. `match_event` took a single candidate with NO time check at all. The
      docstring called it a tolerance for a book posting a start time a few
      minutes off ours; the code was a bypass. A snapshot legitimately spans two
      slate dates (that file holds 11 events on the 8/8 slate and 12 on 8/9), so
      one candidate for an org pair means "the only event for this SERIES in the
      file", not "this game". Measured: TBR at SEA matched an event 1099 minutes
      (18h19m) from first pitch and HOU at SDP matched one 1504 minutes (25h04m)
      off. Both priced the wrong game and nothing on the row looked unusual.

  D2. An event that has already started still priced the board. A book keeps a
      game listed once it is under way, at an IN-GAME price, and the model
      probability beside it is a pregame number. Measured on the same file:
      FanDuel had HOU +1100 and a total of 4.5 on a game 2h17m old, which came
      out as +0.4609 on the Over, +0.4396 on the runline and +0.4089 on the
      moneyline - the three largest edges on the whole board, against a 0.06
      provisional floor.

The two are separate on purpose. Game one of a doubleheader being under way is a
genuine two-candidate case that D1's time match resolves to the started half, so
the pregame filter has to sit in `team_bets` where the events are indexed.

WHAT THESE TESTS HOLD
  1. A lone candidate outside EVENT_MATCH_MAX_MINUTES is refused, and the row
     goes out unpriced rather than mispriced.
  2. The tolerance survives: a lone candidate 45 minutes off is still taken.
  3. A candidate with no commence_time is still taken, because refusing on a
     missing stamp would blank healthy rows for no measured gain.
  4. An in-progress event never reaches the by-pair index, and the drop is
     counted where a reader can see it.
  5. On the real file, HOU at SDP is not priced.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")

ROOT = Path(__file__).parent
REAL_SNAPSHOT = ROOT / ".cache" / "odds" / "2026-08-09-0133.json"

FIRST_PITCH = datetime(2026, 8, 9, 20, 10, tzinfo=timezone.utc)


def _game(start: datetime | None = None, *, home="SEA", away="TBR", pk=1,
          double_header=False) -> dict:
    return {"game_pk": pk, "date": "2026-08-09",
            "datetime": (start or FIRST_PITCH).isoformat().replace("+00:00", "Z"),
            "status": "Preview", "double_header": double_header,
            "home": {"org": home, "team": home}, "away": {"org": away, "team": away}}


def _event(commence: datetime | None, *, home="SEA", away="TBR", eid="e1") -> dict:
    return {"event_id": eid,
            "commence_time": (commence.isoformat().replace("+00:00", "Z")
                              if commence else None),
            "home_team": home, "away_team": away,
            "home_org": home, "away_org": away,
            "books": {"fanduel": {"title": "FanDuel", "last_update": "2026-08-09T01:33:44Z",
                                  "h2h": {"home": -136, "away": 126}}}}


# ---------------------------------------------------------------------------
# D1: the single-candidate shortcut
# ---------------------------------------------------------------------------
def test_a_lone_candidate_eighteen_hours_off_is_a_different_game():
    """THE REGRESSION. This is the real TBR at SEA case: first pitch 20:10Z on
    8/9, the only event in the file for the pair commences 01:51Z the same day,
    which is the previous night's game of the same series."""
    ev = _event(datetime(2026, 8, 9, 1, 51, tzinfo=timezone.utc))
    gap_min = (FIRST_PITCH - datetime(2026, 8, 9, 1, 51,
                                      tzinfo=timezone.utc)).total_seconds() / 60.0
    assert gap_min == 1099.0, "the fixture must reproduce the measured 18h19m gap"
    assert be.match_event(_game(), [ev]) is None, (
        "one candidate for the org pair means one event for the SERIES, not "
        "for this game; pricing off it is a mispriced row and a mispriced row "
        "is invisible")


def test_the_posted_time_tolerance_is_kept():
    """The reason the shortcut existed is real and must not be lost to the fix:
    a book posting a start a few minutes off StatsAPI must not blank the row."""
    ev = _event(FIRST_PITCH + timedelta(minutes=45))
    got = be.match_event(_game(), [ev])
    assert got is ev
    assert 45 < be.EVENT_MATCH_MAX_MINUTES


def test_the_limit_is_inclusive_at_the_tolerance():
    at_limit = _event(FIRST_PITCH + timedelta(minutes=be.EVENT_MATCH_MAX_MINUTES))
    past_limit = _event(FIRST_PITCH + timedelta(minutes=be.EVENT_MATCH_MAX_MINUTES + 1))
    assert be.match_event(_game(), [at_limit]) is at_limit
    assert be.match_event(_game(), [past_limit]) is None


def test_a_candidate_with_no_commence_time_is_still_taken():
    """Nothing to compare. One event for the pair is still the ordinary case,
    and refusing it on a missing stamp buys nothing measured."""
    ev = _event(None)
    assert be.match_event(_game(), [ev]) is ev


def test_a_game_with_no_first_pitch_stamp_still_takes_a_lone_candidate():
    g = _game()
    g["datetime"] = None
    ev = _event(datetime(2026, 8, 9, 1, 51, tzinfo=timezone.utc))
    assert be.match_event(g, [ev]) is ev


def test_two_candidates_still_match_on_nearest_first_pitch():
    """The doubleheader path is untouched by the D1 fix."""
    early = _event(datetime(2026, 8, 9, 17, 10, tzinfo=timezone.utc), eid="g1")
    late = _event(FIRST_PITCH + timedelta(minutes=4), eid="g2")
    assert be.match_event(_game(), [early, late]) is late


# ---------------------------------------------------------------------------
# D2: in-progress events
# ---------------------------------------------------------------------------
# Minimal team inputs. `team_bets` uses whatever is passed, so no leaderboard
# needs to exist for these to run.
TEAMS = {
    "_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
    "SEA": {"z_off": 0.20, "offense_plus": 104.0, "bullpen_plus": 104.0,
            "rotation_plus": 104.0, "sp_ip_share": 0.60},
    "TBR": {"z_off": -0.10, "offense_plus": 98.0, "bullpen_plus": 99.0,
            "rotation_plus": 101.0, "sp_ip_share": 0.60},
}
PARKS = {"SEA": 0.96}


def _bets(games, events, now, stats):
    return be.team_bets(games, events, teams=TEAMS, parks=PARKS, starters={},
                        now=now, stats=stats)


def test_an_in_progress_event_is_dropped_and_counted():
    """The HOU at SDP case in shape: the only event for the pair started 2h17m
    ago, so its prices are in-game and cannot price a pregame board."""
    now = datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc)
    started = _event(now - timedelta(hours=2, minutes=17))
    stats = {}
    rows = _bets([_game()], [started], now, stats)
    assert stats["n_events_dropped_in_progress"] == 1
    assert len(rows) == 1
    assert rows[0]["odds_event_id"] is None, (
        "an in-game price reached a pregame row")
    assert rows[0]["moneyline"][0]["edge"] is None
    assert rows[0]["moneyline"][0]["model_prob"] is not None, (
        "the model fair line still ships; only the market is withheld")


def test_a_pregame_event_one_minute_out_is_kept():
    now = datetime(2026, 8, 9, 20, 9, tzinfo=timezone.utc)
    stats = {}
    rows = _bets([_game()], [_event(FIRST_PITCH)], now, stats)
    assert stats["n_events_dropped_in_progress"] == 0
    assert rows[0]["odds_event_id"] == "e1"


def test_an_event_exactly_at_first_pitch_is_dropped():
    """First pitch has been thrown. A price posted at that instant is in-game."""
    stats = {}
    rows = _bets([_game()], [_event(FIRST_PITCH)], FIRST_PITCH, stats)
    assert stats["n_events_dropped_in_progress"] == 1
    assert rows[0]["odds_event_id"] is None


def test_the_started_half_of_a_doubleheader_cannot_price_game_two():
    """Two candidates, one under way. The time match alone would take the
    started half for game one; the pregame filter removes it first, and game
    two still prices off its own event."""
    now = datetime(2026, 8, 9, 20, 30, tzinfo=timezone.utc)
    g1 = _game(datetime(2026, 8, 9, 20, 10, tzinfo=timezone.utc), pk=1,
               double_header=True)
    g2 = _game(datetime(2026, 8, 10, 0, 10, tzinfo=timezone.utc), pk=2,
               double_header=True)
    e1 = _event(datetime(2026, 8, 9, 20, 10, tzinfo=timezone.utc), eid="g1")
    e2 = _event(datetime(2026, 8, 10, 0, 10, tzinfo=timezone.utc), eid="g2")
    stats = {}
    rows = _bets([g1, g2], [e1, e2], now, stats)
    assert stats["n_events_dropped_in_progress"] == 1
    by_pk = {r["game_pk"]: r for r in rows}
    assert by_pk[1]["odds_event_id"] is None
    assert by_pk[2]["odds_event_id"] == "g2"


def test_an_event_with_no_commence_time_is_never_dropped_as_in_progress():
    stats = {}
    rows = _bets([_game()], [_event(None)], FIRST_PITCH, stats)
    assert stats["n_events_dropped_in_progress"] == 0
    assert rows[0]["odds_event_id"] == "e1"


def test_the_time_refusal_is_counted_separately_from_the_in_progress_drop():
    """Two different failures, two different numbers. TBR at SEA lost its event
    to the clock; HOU at SDP lost its only event to the pregame filter and never
    reached the clock at all."""
    now = datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc)
    stale = _event(datetime(2026, 8, 9, 1, 51, tzinfo=timezone.utc))
    stats = {}
    rows = _bets([_game()], [stale], now, stats)
    assert stats["n_events_dropped_in_progress"] == 0
    assert stats["n_games_unpriced_time_mismatch"] == 1
    assert rows[0]["odds_event_id"] is None


# ---------------------------------------------------------------------------
# the real file
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_events():
    if not REAL_SNAPSHOT.exists():
        pytest.skip(".cache/odds/2026-08-09-0133.json is not in this checkout "
                    "(.cache is gitignored)")
    return bi.parse_events(json.loads(REAL_SNAPSHOT.read_text(encoding="utf-8")))


def test_the_real_snapshot_does_not_price_hou_at_sdp(real_events):
    """HOU at SDP first pitch 2026-08-10T00:20Z, on the 2026-08-09 slate. The
    only event in the file for the pair commences 2026-08-08T23:16Z: 1504
    minutes earlier, and 2h17m INTO play at the 01:33:53Z capture. Before the
    fix it priced the row, and FanDuel's in-game HOU +1100 produced the largest
    edge on the board."""
    cands = [e for e in real_events
             if e["home_org"] == "SDP" and e["away_org"] == "HOU"]
    assert len(cands) == 1, "the file holds exactly one HOU at SDP event"
    assert cands[0]["commence_time"] == "2026-08-08T23:16:00Z"
    g = _game(datetime(2026, 8, 10, 0, 20, tzinfo=timezone.utc),
              home="SDP", away="HOU", pk=7)
    assert be.match_event(g, cands) is None


def test_the_real_snapshot_does_not_price_tbr_at_sea(real_events):
    """The second D1 case: 1099 minutes off, and NOT yet started at capture, so
    only the time check can catch it."""
    cands = [e for e in real_events
             if e["home_org"] == "SEA" and e["away_org"] == "TBR"]
    assert len(cands) == 1
    assert cands[0]["commence_time"] == "2026-08-09T01:51:00Z"
    assert be.match_event(_game(), cands) is None


def test_the_real_snapshot_drops_ten_in_progress_events(real_events):
    """Measured at the file's own capture stamp, 2026-08-09T01:33:53Z."""
    now = datetime(2026, 8, 9, 1, 33, 53, tzinfo=timezone.utc)
    stats = {}
    be.team_bets([], real_events, teams=TEAMS, parks=PARKS, starters={},
                 now=now, stats=stats)
    assert stats["n_events_dropped_in_progress"] == 10, (
        "10 of the 23 events in the file were already under way at capture")
